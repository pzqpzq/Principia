#!/usr/bin/env python3
"""Build path-free v1.4.2 acceptance matrices from a terminal campaign.

The command reads only the isolated acceptance workspace and campaign receipt.
It never opens the frozen corpus. Outputs contain aggregate scientific and
provider receipts, not raw data or absolute paths.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any


def _json(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _rules_for_study(campaign_path: Path, study_id: str) -> list[dict[str, Any]]:
    """Read the canonical Rule projection written with each study report.

    ScientificLawFamily is the sole evidence-bearing Rule source. The campaign
    writer freezes its public projection beside the other no-raw-data exports,
    and this audit verifies the persisted gate contract rather than rebuilding
    Rules from finding text.
    """

    legacy_root = campaign_path.with_name(
        campaign_path.stem.removesuffix("-report")
    )
    candidates = (
        campaign_path.parent / "workspace" / "outputs" / study_id / "rules.json",
        campaign_path.parent / "outputs" / study_id / "rules.json",
        legacy_root / "outputs" / study_id / "rules.json",
    )
    path = next((item for item in candidates if item.is_file()), None)
    if path is None:
        raise RuntimeError(f"campaign has no canonical Rule export for {study_id}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [dict(item) for item in list(payload.get("items") or [])]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", required=True, type=Path)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    args = parser.parse_args()

    campaign = json.loads(args.campaign.read_text(encoding="utf-8"))
    rows = list(campaign.get("rows") or [])
    if campaign.get("state") == "running" or len(rows) != 21:
        parser.error("campaign must be terminal and contain exactly 21 scenario rows")
    output = args.output_directory
    output.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(args.database)
    connection.row_factory = sqlite3.Row
    evidence_rows: list[dict[str, Any]] = []
    global_insights: Counter[str] = Counter()
    global_novelty: Counter[str] = Counter()
    global_states: Counter[str] = Counter()
    provider_failures: Counter[str] = Counter()
    supported_lineage_violations: list[dict[str, Any]] = []
    try:
        for campaign_row in rows:
            study_id = str(campaign_row.get("study_id") or "")
            scenario = str(campaign_row.get("scenario") or "")
            study = connection.execute(
                "SELECT * FROM data_studies WHERE study_id=?", (study_id,)
            ).fetchone()
            if study is None:
                raise RuntimeError(f"campaign row has no durable study: {scenario}")
            coverage = _json(study["coverage_json"])
            findings = [
                _json(row[0])
                for row in connection.execute(
                    "SELECT payload_json FROM data_findings WHERE study_id=?", (study_id,)
                ).fetchall()
            ]
            rules = _rules_for_study(args.campaign, study_id)
            tests = [
                _json(row[0])
                for row in connection.execute(
                    "SELECT payload_json FROM data_tests WHERE study_id=?", (study_id,)
                ).fetchall()
            ]
            tests_by_id = {
                str(item.get("test_id") or ""): item for item in tests
            }
            evidence_by_id = {
                str(row["evidence_id"]): _json(row["payload_json"])
                for row in connection.execute(
                    "SELECT evidence_id, payload_json FROM data_evidence_links "
                    "WHERE study_id=?",
                    (study_id,),
                ).fetchall()
            }
            attempts = [
                _json(row[0])
                for row in connection.execute(
                    "SELECT payload_json FROM provider_attempts WHERE job_id=? ORDER BY created_at",
                    (str(study["job_id"]),),
                ).fetchall()
            ]
            blueprint_row = connection.execute(
                "SELECT payload_json FROM study_blueprints WHERE study_id=?", (study_id,)
            ).fetchone()
            blueprint = _json(blueprint_row[0]) if blueprint_row is not None else {}
            reasoning_model = str(campaign.get("reasoning_model") or "")
            exact_reasoning = [
                attempt
                for attempt in attempts
                if str(attempt.get("model") or "") == reasoning_model
                and str(attempt.get("endpoint_class") or "")
                in {"typed_reasoning", "generated_code_planning"}
            ]
            vision = [
                attempt
                for attempt in attempts
                if str(attempt.get("endpoint_class") or "") == "vision_reasoning"
            ]
            for finding in findings:
                global_insights[str(finding.get("insight_level") or "unspecified")] += 1
                global_novelty[str(finding.get("novelty_status") or "not assessed")] += 1
            for attempt in attempts:
                if str(attempt.get("state") or "") != "succeeded":
                    provider_failures[str(attempt.get("error_category") or "unspecified")] += 1
            state = str(study["state"])
            global_states[state] += 1
            status_counts = Counter(str(item.get("status") or "unknown") for item in findings)
            for finding in findings:
                if str(finding.get("status") or "") != "supported_candidate":
                    continue
                reasons: list[str] = []
                test_ids = [str(item) for item in list(finding.get("test_ids") or [])]
                evidence_ids = [
                    str(item) for item in list(finding.get("evidence_ids") or [])
                ]
                linked_tests = [tests_by_id[item] for item in test_ids if item in tests_by_id]
                linked_evidence = [
                    evidence_by_id[item] for item in evidence_ids if item in evidence_by_id
                ]
                if not test_ids or len(linked_tests) != len(test_ids):
                    reasons.append("broken_test_lineage")
                if not evidence_ids or len(linked_evidence) != len(evidence_ids):
                    reasons.append("broken_evidence_lineage")
                if not any(dict(item.get("uncertainty") or {}) for item in linked_tests):
                    reasons.append("missing_uncertainty")
                if not any(dict(item.get("units") or {}) for item in linked_evidence):
                    reasons.append("missing_computed_evidence_units")
                for field in ("confounders", "falsifiers", "limits"):
                    if not list(finding.get(field) or []):
                        reasons.append(f"missing_{field}")
                if not str(finding.get("next_validation") or ""):
                    reasons.append("missing_next_validation")
                if reasons:
                    supported_lineage_violations.append(
                        {
                            "scenario": scenario,
                            "finding_id": str(finding.get("finding_id") or ""),
                            "reasons": reasons,
                        }
                    )
            formats = connection.execute(
                "SELECT format, COUNT(*) count FROM data_assets WHERE study_id=? "
                "GROUP BY format ORDER BY format",
                (study_id,),
            ).fetchall()
            evidence_rows.append(
                {
                    "scenario": scenario,
                    "state": state,
                    "phase": str(study["phase"]),
                    "assets": int(coverage.get("asset_count") or 0),
                    "tests": len(tests),
                    "findings": len(findings),
                    "supported_findings": status_counts["supported_candidate"],
                    "inconclusive_findings": status_counts["inconclusive"],
                    "held_back_findings": status_counts["held_back"],
                    "projected_rules": len(rules),
                    "validated_rules": sum(
                        bool(dict(rule.get("gate_summary") or {}).get("passed"))
                        and bool(list(rule.get("gate_receipts") or []))
                        for rule in rules
                    ),
                    "rule_executor_ids": "; ".join(
                        sorted(
                            {
                                str(rule.get("executor_id") or "")
                                for rule in rules
                                if bool(dict(rule.get("gate_summary") or {}).get("passed"))
                                and str(rule.get("executor_id") or "")
                            }
                        )
                    ),
                    "exploratory_expressions": sum(
                        str(rule.get("validation_status") or "")
                        == "exploratory_expression"
                        for rule in rules
                    ),
                    "all_rules_passed_gate": bool(rules) and all(
                        bool(_json(json.dumps(rule.get("test") or {})).get("passed"))
                        for rule in rules
                    ),
                    "exact_reasoning_successes": sum(
                        str(item.get("state") or "") == "succeeded"
                        for item in exact_reasoning
                    ),
                    "exact_reasoning_failures": sum(
                        str(item.get("state") or "") != "succeeded"
                        for item in exact_reasoning
                    ),
                    "vision_successes": sum(
                        str(item.get("state") or "") == "succeeded" for item in vision
                    ),
                    "vision_failures": sum(
                        str(item.get("state") or "") != "succeeded" for item in vision
                    ),
                    "blueprint_confidence": blueprint.get("confidence", ""),
                    "domain_candidates": "; ".join(
                        str(item.get("domain") or "")
                        for item in list(blueprint.get("domain_candidates") or [])[:3]
                        if isinstance(item, dict)
                    ),
                    "formats": "; ".join(
                        f"{row['format']}:{int(row['count'])}" for row in formats
                    ),
                    "explicit_limitations": len(
                        list(coverage.get("analysis_limitations") or [])
                    ),
                    "accepted_by_campaign": bool(campaign_row.get("accepted")),
                }
            )
    finally:
        connection.close()

    matrix_path = output / "evidence-matrix.csv"
    with matrix_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(evidence_rows[0]))
        writer.writeheader()
        writer.writerows(evidence_rows)

    numbered_with_rules = sum(
        str(row["scenario"])[:2].isdigit() and int(row["validated_rules"]) >= 1
        for row in evidence_rows
    )
    qualifying_executors = sorted(
        {
            executor
            for row in evidence_rows
            if str(row["scenario"])[:2].isdigit()
            for executor in str(row["rule_executor_ids"]).split("; ")
            if executor
        }
    )
    rule_yield_gate = numbered_with_rules >= 10 and len(qualifying_executors) >= 5
    quality = {
        "schema_version": "principia.v142-scientific-quality-scorecard/v1",
        "campaign_state": campaign.get("state"),
        "scenario_count": len(evidence_rows),
        "terminal_state_counts": dict(sorted(global_states.items())),
        "total_assets": sum(int(row["assets"]) for row in evidence_rows),
        "total_tests": sum(int(row["tests"]) for row in evidence_rows),
        "total_findings": sum(int(row["findings"]) for row in evidence_rows),
        "supported_findings": sum(
            int(row["supported_findings"]) for row in evidence_rows
        ),
        "projected_rules": sum(
            int(row["projected_rules"]) for row in evidence_rows
        ),
        "validated_rules": sum(int(row["validated_rules"]) for row in evidence_rows),
        "exploratory_expressions": sum(
            int(row["exploratory_expressions"]) for row in evidence_rows
        ),
        "insight_distribution": dict(sorted(global_insights.items())),
        "novelty_distribution": dict(sorted(global_novelty.items())),
        "provider_failure_categories": dict(sorted(provider_failures.items())),
        "scenarios_without_supported_findings": [
            row["scenario"] for row in evidence_rows if not row["supported_findings"]
        ],
        "scenarios_without_validated_rules": [
            row["scenario"] for row in evidence_rows if not row["validated_rules"]
        ],
        "rule_gate_violations": [
            row["scenario"]
            for row in evidence_rows
            if int(row["projected_rules"]) > 0 and not row["all_rules_passed_gate"]
        ],
        "supported_lineage_violations": supported_lineage_violations,
        "numbered_scenarios_with_qualifying_rules": numbered_with_rules,
        "qualifying_rule_executor_ids": qualifying_executors,
        "rule_yield_gate": rule_yield_gate,
        "scientific_release_gate": (
            "failed" if supported_lineage_violations or not rule_yield_gate else "passed"
        ),
        "claim_policy": (
            "Counts describe retained candidate evidence, not confirmed novelty or "
            "publication readiness. No positive-result quota was enforced."
        ),
    }
    _write_json(output / "scientific-quality-scorecard.json", quality)

    residuals = []
    if any(int(row["vision_failures"]) for row in evidence_rows):
        residuals.append(
            {
                "risk": "vision_provider_availability",
                "severity": "medium",
                "evidence": "At least one bounded vision request failed; quantitative work continued.",
            }
        )
    if quality["scenarios_without_supported_findings"]:
        residuals.append(
            {
                "risk": "information_or_operator_coverage",
                "severity": "high",
                "evidence": (
                    f"{len(quality['scenarios_without_supported_findings'])} scenarios retained no "
                    "supported candidate; inspect their negative evidence before expanding operators."
                ),
            }
        )
    if quality["scenarios_without_validated_rules"]:
        residuals.append(
            {
                "risk": "symbolic_law_yield",
                "severity": "high",
                "evidence": (
                    f"{len(quality['scenarios_without_validated_rules'])} scenarios produced no Rule "
                    "passing the held-out symbolic-law gate."
                ),
            }
        )
    if supported_lineage_violations:
        residuals.append(
            {
                "risk": "supported_finding_contract",
                "severity": "high",
                "evidence": (
                    f"{len(supported_lineage_violations)} supported candidates violate at "
                    "least one uncertainty, units, or lineage requirement. The prospective "
                    "engine was tightened; historical receipts remain unchanged."
                ),
            }
        )
    _write_json(
        output / "prioritized-residual-risks.json",
        {
            "schema_version": "principia.v142-residual-risks/v1",
            "items": residuals,
        },
    )

    summary = [
        "# Principia v1.4.2 21-scenario acceptance summary",
        "",
        f"- Campaign state: `{campaign.get('state')}`",
        f"- Terminal scenarios: {len(evidence_rows)}/21",
        f"- Assets inventoried: {quality['total_assets']}",
        f"- Executed tests retained: {quality['total_tests']}",
        f"- Supported candidate findings: {quality['supported_findings']}",
        f"- Projected symbolic Rules: {quality['projected_rules']}",
        f"- Held-out validated Rules: {quality['validated_rules']}",
        f"- Numbered scenarios with a qualifying Rule: {numbered_with_rules}/20",
        f"- Qualifying executor classes: {len(qualifying_executors)}",
        f"- Scientific release gate: `{quality['scientific_release_gate']}`",
        "- Frozen corpus unchanged: " + str(bool(campaign.get("corpus_unchanged"))).lower(),
        "",
        "These are hypothesis-generation receipts. `supported_candidate` is not a novelty claim, "
        "and the campaign did not manufacture findings to meet a quota.",
    ]
    (output / "acceptance-summary.md").write_text(
        "\n".join(summary) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
