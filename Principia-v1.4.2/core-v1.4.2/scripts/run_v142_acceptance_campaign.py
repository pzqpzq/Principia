#!/usr/bin/env python3
"""Run the immutable 21-scenario v1.4.2 acceptance campaign.

All derived state is written to the supplied working directory and output
receipt. The numbered and TJ roots are only opened for read-only inventory and
analysis. Corpus verification is serialized before every launch, after every
terminal run, and after the full campaign.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from frozen_corpus import scan_v2

from principia import Principia
from principia.data_discovery.rule_engine import registry_identity
from principia.persistence.migrations import RULE_ENGINE_MIGRATION_VERSION
from principia.providers.token_budget import TokenBudget, load_credential_environment

TERMINAL = {"succeeded", "partial", "failed", "cancelled", "interrupted"}


def _tree_digest(
    root: Path, paths: tuple[str, ...], *, exclude_built_ui: bool = False
) -> str:
    """Hash a release projection without including build caches or evaluation state."""

    entries: list[dict[str, Any]] = []
    for relative in paths:
        candidate = root / relative
        members = [candidate] if candidate.is_file() else sorted(candidate.rglob("*"))
        for member in members:
            if not member.is_file():
                continue
            parts = member.relative_to(root).parts
            if (
                "__pycache__" in parts
                or "node_modules" in parts
                or (
                    exclude_built_ui
                    and parts[:3] == ("src", "principia", "ui_dist")
                )
                or member.suffix == ".pyc"
            ):
                continue
            payload = member.read_bytes()
            entries.append(
                {
                    "path": member.relative_to(root).as_posix(),
                    "size": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )
    encoded = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _release_projection(root: Path) -> dict[str, str]:
    return {
        "source_tree_digest": _tree_digest(
            root,
            (
                "src/principia",
                "frontend/src",
                "scripts",
                "tests",
                "pyproject.toml",
                "frontend/package.json",
                "frontend/pnpm-lock.yaml",
            ),
            exclude_built_ui=True,
        ),
        "frontend_build_digest": _tree_digest(root, ("src/principia/ui_dist",)),
        "schema_version": RULE_ENGINE_MIGRATION_VERSION,
        "executor_registry_identity": registry_identity(),
    }


def _assert_frozen(numbered: Path, tj: Path, expected: dict[str, Any]) -> dict[str, Any]:
    actual = scan_v2(numbered, tj)
    # Finder may rewrite ordinary .DS_Store files merely because a user opens a
    # folder.  v2 deliberately records that drift as telemetry, but it is not
    # part of either integrity gate.  Everything else in each root projection
    # remains exact, including paths, kinds, modes, mtimes, sizes, and hashes.
    def critical_projection(receipt: dict[str, Any]) -> dict[str, Any]:
        roots = []
        for root in list(receipt.get("roots") or []):
            roots.append(
                {
                    key: value
                    for key, value in dict(root).items()
                    if key != "finder_drift"
                }
            )
        return {
            "schema": receipt.get("schema"),
            "comparison_policy": receipt.get("comparison_policy"),
            "roots": roots,
        }

    if critical_projection(actual) != critical_projection(expected):
        raise RuntimeError(
            "frozen corpus mismatch; outstanding runs must be cancelled without restoration"
        )
    return {
        item["root_id"]: {
            "content_digest": item["content_digest"],
            "strict_digest": item["strict_digest"],
        }
        for item in actual["roots"]
    }


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _supported_finding_contract_violations(
    product: Principia, study_id: str
) -> list[dict[str, Any]]:
    """Validate release-critical lineage for every supported candidate.

    The campaign gate must not disagree with the evidence-package audit.  This
    check intentionally uses the public service projection plus the repository
    detail record so missing tests or evidence cannot be hidden by aggregate
    coverage counts.
    """

    violations: list[dict[str, Any]] = []
    for finding in product.data_discovery.findings(study_id):
        if str(finding.get("status") or "") != "supported_candidate":
            continue
        finding_id = str(finding.get("finding_id") or "")
        detail = product.repository.data_finding(study_id, finding_id) or {}
        tests = [dict(item) for item in list(detail.get("tests") or [])]
        evidence = [dict(item) for item in list(detail.get("evidence") or [])]
        test_ids = [str(item) for item in list(finding.get("test_ids") or [])]
        evidence_ids = [str(item) for item in list(finding.get("evidence_ids") or [])]
        reasons: list[str] = []
        if not test_ids or len(tests) != len(test_ids):
            reasons.append("broken_test_lineage")
        if not evidence_ids or len(evidence) != len(evidence_ids):
            reasons.append("broken_evidence_lineage")
        if not any(dict(item.get("uncertainty") or {}) for item in tests):
            reasons.append("missing_uncertainty")
        if not any(dict(item.get("units") or {}) for item in evidence):
            reasons.append("missing_computed_evidence_units")
        for field in ("confounders", "falsifiers", "limits"):
            if not list(finding.get(field) or []):
                reasons.append(f"missing_{field}")
        if not str(finding.get("next_validation") or ""):
            reasons.append("missing_next_validation")
        if reasons:
            violations.append(
                {
                    "finding_id": finding_id,
                    "reasons": reasons,
                }
            )
    return violations


def scenarios(numbered: Path, tj: Path, prefixes: tuple[str, ...]) -> list[tuple[str, Path]]:
    values = [
        (path.name, path)
        for path in sorted(numbered.iterdir())
        if path.is_dir() and len(path.name) >= 3 and path.name[:2].isdigit() and path.name[2] == "_"
    ]
    values.append(("TJ-SHD", tj))
    if prefixes:
        values = [item for item in values if item[0].startswith(prefixes)]
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--numbered-corpus", required=True, type=Path)
    parser.add_argument("--tj-corpus", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--working-directory", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--scenario-prefix", action="append", default=[])
    parser.add_argument("--reasoning-model", default="deepseek-ai/DeepSeek-V4-Flash")
    parser.add_argument("--vision-model", default="auto")
    parser.add_argument("--poll-seconds", default=2.0, type=float)
    parser.add_argument("--canary", action="store_true")
    parser.add_argument("--offline", action="store_true", help="Audit deterministic execution without provider calls; never counts as acceptance.")
    parser.add_argument("--credential-env", type=Path, help="Explicitly authorized dotenv file, loaded without copying or echoing.")
    parser.add_argument("--token-ledger", type=Path, help="Shared cumulative token ledger for every remote phase and campaign.")
    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Continue an interrupted receipt without rerunning terminal scenarios. "
            "An incomplete in-flight study is preserved and replaced by a new run "
            "inside the same canonical project."
        ),
    )
    args = parser.parse_args()
    if not args.offline and args.reasoning_model != "deepseek-ai/DeepSeek-V4-Flash":
        parser.error("Acceptance requires exactly deepseek-ai/DeepSeek-V4-Flash")
    if args.credential_env and not args.offline:
        load_credential_environment(args.credential_env)
    if not args.offline and not args.token_ledger:
        parser.error("Remote evaluation requires --token-ledger (shared 3,000,000-token cap)")
    token_budget = None
    if args.token_ledger:
        os.environ["PRINCIPIA_TOKEN_BUDGET_FILE"] = str(args.token_ledger.resolve())
        os.environ["PRINCIPIA_TOKEN_BUDGET_LIMIT"] = "3000000"
        token_budget = TokenBudget(args.token_ledger, 3_000_000)

    numbered = args.numbered_corpus.expanduser().resolve(strict=True)
    tj = args.tj_corpus.expanduser().resolve(strict=True)
    expected = json.loads(args.receipt.read_text(encoding="utf-8"))
    if expected.get("schema") != "principia.frozen-corpus/v2":
        parser.error("--receipt must use principia.frozen-corpus/v2")
    selected = scenarios(numbered, tj, tuple(args.scenario_prefix))
    if args.canary and not args.scenario_prefix:
        selected = [item for item in selected if item[0].startswith("02_")]
    if not selected:
        parser.error("no scenarios matched")

    release_root = Path(__file__).resolve().parents[1]
    initial_release = _release_projection(release_root)
    initial_digests = _assert_frozen(numbered, tj, expected)
    if args.resume:
        if not args.output.is_file():
            parser.error("--resume requires an existing --output receipt")
        campaign = json.loads(args.output.read_text(encoding="utf-8"))
        if campaign.get("schema_version") != "principia.v142-acceptance-campaign/v1":
            parser.error("the existing campaign receipt has an incompatible schema")
        if str(campaign.get("reasoning_model") or "") != args.reasoning_model:
            parser.error("--reasoning-model must match the interrupted campaign")
        if str(campaign.get("vision_model") or "") != args.vision_model:
            parser.error("--vision-model must match the interrupted campaign")
        if list(campaign.get("selected_scenarios") or []) != [name for name, _ in selected]:
            parser.error("the selected scenarios do not match the interrupted campaign")
        if dict(campaign.get("initial_corpus_digests") or {}) != initial_digests:
            raise RuntimeError("frozen corpus changed since the campaign began")
        if dict(campaign.get("initial_release_projection") or {}) != initial_release:
            raise RuntimeError("source or frontend build changed since the campaign began")
        resuming_incomplete = any(
            not bool(item.get("terminal")) for item in list(campaign.get("rows") or [])
        )
        campaign.pop("finished_at", None)
        campaign.pop("final_corpus_digests", None)
        campaign.pop("accepted_count", None)
        campaign.pop("corpus_unchanged", None)
        campaign["state"] = "running"
        campaign.setdefault("resume_history", []).append(
            {
                "resumed_at": datetime.now(timezone.utc).isoformat(),
                "reason": (
                    "campaign process interrupted"
                    if resuming_incomplete
                    else "terminal receipt reconciliation"
                ),
            }
        )
    else:
        campaign = {
            "schema_version": "principia.v142-acceptance-campaign/v1",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "reasoning_model": args.reasoning_model,
            "vision_model": args.vision_model,
            "budget": "deep",
            "worker_capacity": 4,
            "selected_scenarios": [name for name, _ in selected],
            "initial_corpus_digests": initial_digests,
            "initial_release_projection": initial_release,
            "rows": [],
            "terminal_count": 0,
            "state": "running",
            "evaluation_mode": "offline_audit" if args.offline else "remote_acceptance",
        }
    _atomic_json(args.output, campaign)

    product = Principia.open(working_directory=args.working_directory)
    safe_profile = product.local.provider_profile("siliconflow").model_dump(
        mode="json",
        exclude={"base_url", "configured", "credential_source", "saved_at"},
    )
    profile_digest = hashlib.sha256(
        json.dumps(safe_profile, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    cloud_digest = product.content_digest()
    if not args.resume:
        campaign["provider_profile_digest"] = profile_digest
        campaign["cloud_content_digest"] = cloud_digest
        _atomic_json(args.output, campaign)
    elif (
        campaign.get("provider_profile_digest") != profile_digest
        or campaign.get("cloud_content_digest") != cloud_digest
    ):
        raise RuntimeError("provider profile or Cloud content changed since campaign launch")
    launched: dict[str, dict[str, Any]] = {}
    try:
        if args.resume:
            for saved in list(campaign.get("rows") or []):
                row = dict(saved)
                study_id = str(row.get("study_id") or "")
                if bool(row.get("terminal")):
                    # Re-read terminal evidence so additive acceptance metrics
                    # can be reconciled without rerunning scientific work.
                    if product.repository.data_study(study_id) is None:
                        raise RuntimeError(f"missing terminal study: {study_id}")
                    row["terminal"] = False
                    launched[study_id] = row
                    continue
                previous = product.repository.data_study(study_id)
                if previous is None:
                    raise RuntimeError(f"missing interrupted study: {study_id}")
                persisted_state = str(previous.get("state") or "")
                if persisted_state in TERMINAL:
                    launched[study_id] = row
                    continue

                # Preserve the interrupted attempt and every artifact it reached.
                # A replacement run avoids mixing old and new model outputs in one
                # immutable evidence lineage.
                previous_report = dict(previous.get("report") or {})
                previous_report["interruption"] = {
                    "type": "campaign_process_interrupted",
                    "message": "The process ended before this run reached a terminal receipt.",
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                }
                product.repository.update_data_study(
                    study_id,
                    state="failed",
                    report=previous_report,
                )
                source_id = f"acceptance:v142:{row['scenario'][:2] if row['scenario'] != 'TJ-SHD' else 'tj'}"
                replacement = product.data_discovery.create(
                    source_ids=[source_id],
                    objective="",
                    provider="" if args.offline else "siliconflow",
                    reasoning_model=args.reasoning_model,
                    vision_model=args.vision_model,
                    knowledge_scope="combined",
                    prior_art="survivors",
                    budget="deep",
                    session_id=str(row.get("session_id") or ""),
                    egress_confirmed=not args.offline,
                    defer=True,
                )
                for key in (
                    "accepted",
                    "test_count",
                    "finding_count",
                    "supported_finding_count",
                    "validated_rule_count",
                    "provider_attempt_count",
                    "successful_exact_model_attempts",
                    "successful_exact_reasoning_attempts",
                    "failed_exact_reasoning_attempts",
                    "vision_successful_attempts",
                    "vision_failed_attempts",
                    "exact_model_verified",
                    "repeated_canary_provider_failure",
                    "limitations",
                ):
                    row.pop(key, None)
                row.setdefault("interrupted_study_ids", []).append(study_id)
                row.update(
                    {
                        "study_id": str(replacement["study_id"]),
                        "state": "queued",
                        "phase": "inventory",
                        "terminal": False,
                        "recovery_count": int(row.get("recovery_count") or 0) + 1,
                    }
                )
                launched[str(replacement["study_id"])] = row
            campaign["rows"] = list(launched.values())
            campaign["terminal_count"] = sum(
                bool(item.get("terminal")) for item in launched.values()
            )
            _atomic_json(args.output, campaign)
        else:
            for index, (name, root) in enumerate(selected, start=1):
                _assert_frozen(numbered, tj, expected)
                source_id = f"acceptance:v142:{name[:2] if name != 'TJ-SHD' else 'tj'}"
                product.repository.register_source(
                    source_id,
                    root,
                    f"frozen-scenario://{name}",
                    name,
                    f"v1.4.2 acceptance/{name}",
                )
                home = product.research_sessions.create_data_discovery_home(
                    source_ids=[source_id],
                    title=f"Discovery · {name}",
                    provider_profile_id="siliconflow",
                    model=args.reasoning_model,
                )
                study = product.data_discovery.create(
                    source_ids=[source_id],
                    objective="",
                    provider="" if args.offline else "siliconflow",
                    reasoning_model=args.reasoning_model,
                    vision_model=args.vision_model,
                    knowledge_scope="combined",
                    prior_art="survivors",
                    budget="deep",
                    session_id=str(home["session_id"]),
                    egress_confirmed=not args.offline,
                    defer=True,
                )
                launched[str(study["study_id"])] = {
                    "scenario": name,
                    "session_id": str(home["session_id"]),
                    "study_id": str(study["study_id"]),
                    "launch_sequence": index,
                    "terminal": False,
                }
                campaign["rows"] = list(launched.values())
                _atomic_json(args.output, campaign)

        while any(not item["terminal"] for item in launched.values()):
            progressed = False
            for study_id, row in launched.items():
                if row["terminal"]:
                    continue
                study = product.data_discovery.get(study_id)
                state = str(study.get("state") or "")
                row.update(
                    {
                        "state": state,
                        "phase": str(study.get("phase") or ""),
                        "updated_at": str(study.get("updated_at") or ""),
                    }
                )
                if state not in TERMINAL:
                    continue
                _assert_frozen(numbered, tj, expected)
                coverage = dict(study.get("coverage") or {})
                scientific_program_execution = dict(
                    coverage.get("scientific_program_execution") or {}
                )
                attempts = product.repository.provider_attempts(str(study.get("job_id") or ""))
                successful_exact = [
                    item
                    for item in attempts
                    if str(item.get("state") or "") == "succeeded"
                    and str(item.get("model") or "") == args.reasoning_model
                ]
                exact_reasoning = [
                    item
                    for item in attempts
                    if str(item.get("model") or "") == args.reasoning_model
                    and str(item.get("endpoint_class") or "")
                    in {"typed_reasoning", "generated_code_planning"}
                ]
                successful_exact_reasoning = [
                    item
                    for item in exact_reasoning
                    if str(item.get("state") or "") == "succeeded"
                ]
                failed_exact_reasoning = [
                    item
                    for item in exact_reasoning
                    if str(item.get("state") or "") != "succeeded"
                ]
                vision_attempts = [
                    item
                    for item in attempts
                    if str(item.get("endpoint_class") or "") == "vision_reasoning"
                ]
                test_count = int(coverage.get("executed_test_count") or 0)
                law_records = product.data_discovery.laws(study_id)
                qualifying_laws = [
                    item
                    for item in law_records
                    if bool(item.get("promoted"))
                    and bool(dict(item.get("gate_summary") or {}).get("passed"))
                ]
                finding_contract_violations = _supported_finding_contract_violations(
                    product, study_id
                )
                repeated_canary_failure = bool(
                    args.canary and len(failed_exact_reasoning) >= 2
                )
                row.update(
                    {
                        "terminal": True,
                        "asset_count": int(coverage.get("asset_count") or 0),
                        "test_count": test_count,
                        "finding_count": int(study.get("finding_count") or 0),
                        "supported_finding_count": int(
                            coverage.get("surviving_finding_count") or 0
                        ),
                        "validated_rule_count": int(coverage.get("validated_rule_count") or 0),
                        "formula_first_rule_count": int(
                            len(qualifying_laws)
                        ),
                        "qualifying_rule_executor_ids": sorted(
                            {
                                str(item.get("executor_id") or "")
                                for item in qualifying_laws
                                if str(item.get("executor_id") or "")
                            }
                        ),
                        "scientific_program_count": len(
                            list(coverage.get("scientific_programs") or [])
                        ),
                        "law_candidate_count": int(
                            scientific_program_execution.get("candidate_count") or 0
                        ),
                        "provider_attempt_count": len(attempts),
                        "successful_exact_model_attempts": len(successful_exact),
                        "successful_exact_reasoning_attempts": len(
                            successful_exact_reasoning
                        ),
                        "failed_exact_reasoning_attempts": len(failed_exact_reasoning),
                        "vision_successful_attempts": sum(
                            str(item.get("state") or "") == "succeeded"
                            for item in vision_attempts
                        ),
                        "vision_failed_attempts": sum(
                            str(item.get("state") or "") != "succeeded"
                            for item in vision_attempts
                        ),
                        "exact_model_verified": bool(successful_exact_reasoning),
                        "repeated_canary_provider_failure": repeated_canary_failure,
                        "supported_finding_contract_violations": finding_contract_violations,
                        "accepted": state in {"succeeded", "partial"}
                        and test_count >= 1
                        and bool(successful_exact_reasoning)
                        and not repeated_canary_failure
                        and not finding_contract_violations,
                        "limitations": list(coverage.get("analysis_limitations") or []),
                    }
                )
                campaign["terminal_count"] = sum(
                    bool(item["terminal"]) for item in launched.values()
                )
                campaign["rows"] = list(launched.values())
                _atomic_json(args.output, campaign)
                print(
                    json.dumps(
                        {
                            "scenario": row["scenario"],
                            "state": state,
                            "tests": test_count,
                            "exact_model": bool(successful_exact_reasoning),
                            "exact_reasoning_failures": len(failed_exact_reasoning),
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
                progressed = True
            if token_budget:
                campaign["token_budget"] = token_budget.snapshot()
            if not progressed:
                time.sleep(max(0.5, args.poll_seconds))

        final_digests = _assert_frozen(numbered, tj, expected)
        campaign["finished_at"] = datetime.now(timezone.utc).isoformat()
        campaign["final_corpus_digests"] = final_digests
        campaign["corpus_unchanged"] = final_digests == initial_digests
        campaign["final_release_projection"] = _release_projection(release_root)
        campaign["release_projection_unchanged"] = (
            campaign["final_release_projection"] == initial_release
        )
        campaign["provider_profile_unchanged"] = (
            hashlib.sha256(
                json.dumps(
                    product.local.provider_profile("siliconflow").model_dump(
                        mode="json",
                        exclude={
                            "base_url",
                            "configured",
                            "credential_source",
                            "saved_at",
                        },
                    ),
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            == profile_digest
        )
        campaign["cloud_unchanged"] = product.content_digest() == cloud_digest
        campaign["accepted_count"] = sum(bool(row.get("accepted")) for row in launched.values())
        campaign["formula_first_rule_count"] = sum(
            int(row.get("formula_first_rule_count") or 0)
            for row in launched.values()
        )
        tj_row = next(
            (row for row in launched.values() if row.get("scenario") == "TJ-SHD"),
            {},
        )
        campaign["tj_formula_rule_gate"] = bool(
            int(tj_row.get("formula_first_rule_count") or 0) >= 1
        )
        numbered_rows = [
            row
            for row in launched.values()
            if str(row.get("scenario") or "")[:2].isdigit()
        ]
        campaign["numbered_scenarios_with_qualifying_rules"] = sum(
            int(row.get("formula_first_rule_count") or 0) >= 1
            for row in numbered_rows
        )
        campaign["qualifying_rule_executor_ids"] = sorted(
            {
                str(executor)
                for row in numbered_rows
                for executor in list(row.get("qualifying_rule_executor_ids") or [])
                if str(executor)
            }
        )
        campaign["rule_yield_gate"] = (
            campaign["numbered_scenarios_with_qualifying_rules"] >= 10
            and len(campaign["qualifying_rule_executor_ids"]) >= 5
        )
        campaign["supported_finding_contract_violation_count"] = sum(
            len(list(row.get("supported_finding_contract_violations") or []))
            for row in launched.values()
        )
        campaign["supported_finding_contract_gate"] = (
            campaign["supported_finding_contract_violation_count"] == 0
        )
        if args.canary:
            accepted = (
                campaign["accepted_count"] == len(selected)
                and campaign["corpus_unchanged"]
                and campaign["release_projection_unchanged"]
                and campaign["provider_profile_unchanged"]
                and campaign["cloud_unchanged"]
                and campaign["supported_finding_contract_gate"]
                and not any(
                    bool(row.get("repeated_canary_provider_failure"))
                    for row in launched.values()
                )
            )
        else:
            accepted = (
                len(numbered_rows) == 20
                and len(selected) == 21
                and campaign["accepted_count"] == len(selected)
                and campaign["corpus_unchanged"]
                and campaign["release_projection_unchanged"]
                and campaign["provider_profile_unchanged"]
                and campaign["cloud_unchanged"]
                and campaign["tj_formula_rule_gate"]
                and campaign["rule_yield_gate"]
                and campaign["supported_finding_contract_gate"]
            )
        campaign["state"] = "offline_audit_complete" if args.offline else "accepted" if accepted else "completed_with_failures"
        if token_budget:
            campaign["token_budget"] = token_budget.snapshot()
        campaign["rows"] = list(launched.values())
        _atomic_json(args.output, campaign)
    except Exception:
        for study_id, row in launched.items():
            if not row["terminal"]:
                try:
                    product.data_discovery.cancel(study_id)
                except Exception:
                    pass
        campaign["state"] = "stopped"
        campaign["stopped_at"] = datetime.now(timezone.utc).isoformat()
        campaign["rows"] = list(launched.values())
        _atomic_json(args.output, campaign)
        raise
    finally:
        product.close()
    return 0 if campaign["state"] in {"accepted", "offline_audit_complete"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
