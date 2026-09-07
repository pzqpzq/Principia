"""Run independent public-data discoveries and retain auditable, resumable receipts.

This campaign does not select or promote demo projects automatically. Scientific
acceptance gates remain in the product; editorial review happens after all runs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from principia import Principia
from principia.providers.token_budget import TokenBudget, load_credential_environment

MODEL = "deepseek-ai/DeepSeek-V4-Pro"
TERMINAL = {"succeeded", "partial", "failed", "cancelled", "interrupted"}


def write(path, value):
    temporary = path.with_suffix(".partial")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def inventory(root):
    rows = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == ".DS_Store":
            continue
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        rows.append({"path": path.relative_to(root).as_posix(),
                     "bytes": path.stat().st_size, "sha256": digest.hexdigest()})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--working-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--credential-env", type=Path, required=True)
    parser.add_argument("--scenario-prefix", action="append", default=[])
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    load_credential_environment(args.credential_env)
    os.environ["PRINCIPIA_LLM_MODEL"] = MODEL
    os.environ["PRINCIPIA_TOKEN_BUDGET_FILE"] = str(args.output.parent / "token-ledger.sqlite")
    os.environ["PRINCIPIA_TOKEN_BUDGET_LIMIT"] = "3000000"
    ledger = TokenBudget.from_environment()
    roots = sorted(p for p in args.corpus.iterdir()
                   if p.is_dir() and p.name[:2].isdigit() and (p / "SCENARIO.md").is_file())
    if len(roots) != 20 or [int(p.name[:2]) for p in roots] != list(range(1, 21)):
        raise ValueError("Expected exactly the twenty numbered public scenarios, excluding TJ")
    selected = [p for p in roots if not args.scenario_prefix
                or any(p.name.startswith(prefix) for prefix in args.scenario_prefix)]
    frozen_path = args.output.with_name(args.output.stem + "-source-manifest.json")
    source_manifest = inventory(args.corpus)
    scientific_source = inventory(Path(__file__).resolve().parents[1] / "src/principia/data_discovery")
    if args.resume:
        campaign = json.loads(args.output.read_text())
        if json.loads(frozen_path.read_text()) != source_manifest:
            raise ValueError("Public source corpus changed; refusing to resume")
        if campaign["scientific_source"] != scientific_source:
            raise ValueError("Scientific implementation changed; use a separately versioned campaign")
        if campaign["scenarios"] != [p.name for p in selected]:
            raise ValueError("Scenario selection changed")
    else:
        if args.output.exists():
            raise ValueError("Receipt already exists; use --resume")
        write(frozen_path, source_manifest)
        campaign = {"schema": "principia.public-demo-campaign/v1", "model": MODEL,
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "scenarios": [p.name for p in selected], "scientific_source": scientific_source,
                    "state": "running", "rows": [], "depth": "deep",
                    "review_criteria": ["Executable, gate-passing laws with frozen holdout evidence",
                                        "Compact equations with meaningful baselines and adequate independent units",
                                        "Physical or domain interpretation, visible limitations and non-causal caveats",
                                        "Readable, distinctive presentation and complete portable evidence"],
                    "selection_boundary": "Editorial demo curation, not a claim of uniform benchmark success"}
        write(args.output, campaign)
    product = Principia.open(working_directory=args.working_directory)
    try:
        catalog = product.local.provider_model_catalog("siliconflow")
        # Catalog shape may vary between provider adapters; demand the exact ID.
        if MODEL not in json.dumps(catalog):
            raise RuntimeError("Requested Pro model is absent from the live provider catalog")
        campaign["exact_model_in_live_catalog"] = True
        saved = {row["scenario"]: row for row in campaign["rows"]}
        for root in selected:
            previous = saved.get(root.name)
            if previous and previous.get("terminal"):
                continue
            if previous:
                study = product.repository.data_study(previous["study_id"])
                if study and study["state"] in TERMINAL:
                    continue
                raise RuntimeError("An interrupted active run needs explicit reconciliation; receipts preserved")
            brief = (root / "SCENARIO.md").read_text()
            challenge = brief.split("## Intended analysis challenge\n", 1)[1].split("\n##", 1)[0].strip()
            source_id = "public-demo:" + root.name[:2]
            title = brief.splitlines()[0].removeprefix("# ")
            product.repository.register_source(source_id, root, "public-corpus://" + root.name,
                                               title, "Public v1.4.2 Pro demo evaluation")
            home = product.research_sessions.create_data_discovery_home(
                source_ids=[source_id], title=title, provider_profile_id="siliconflow", model=MODEL)
            objective = (challenge + " Identify concise, scientifically interpretable quantitative rules. "
                         "Enumerate diverse candidate expressions and select on development data; "
                         "evaluate frozen held-out data against meaningful baselines. Prefer compact "
                         "laws over flexible fits, account for dependence and confounders, and state "
                         "the limits of each finding. Do not treat supplied context as measured evidence.")
            study = product.data_discovery.create(
                source_ids=[source_id], objective=objective, provider="siliconflow", reasoning_model=MODEL,
                vision_model="Qwen/Qwen3-VL-32B-Instruct", knowledge_scope="combined", prior_art="survivors",
                budget="deep", session_id=home["session_id"], egress_confirmed=True, defer=True)
            campaign["rows"].append({"scenario": root.name, "session_id": home["session_id"],
                                     "study_id": study["study_id"], "terminal": False})
            write(args.output, campaign)
            print(json.dumps({"launched": root.name}), flush=True)
        while any(not row.get("terminal") for row in campaign["rows"]):
            for row in campaign["rows"]:
                if row.get("terminal"):
                    continue
                study = product.repository.data_study(row["study_id"])
                row.update(state=study["state"], phase=study["phase"])
                if study["state"] not in TERMINAL:
                    continue
                laws = product.data_discovery.laws(row["study_id"])
                attempts = product.repository.provider_attempts(study["job_id"])
                exact = [a for a in attempts if a.get("model") == MODEL and a.get("state") == "succeeded"]
                reasoning = [a for a in exact if a.get("endpoint_class") in {"typed_reasoning", "generated_code_planning"}]
                row.update(terminal=True, coverage=study["coverage"],
                           law_count=len(laws), promoted_law_count=sum(bool(law.get("promoted")) for law in laws),
                           exact_pro_successful_calls=len(exact), exact_pro_reasoning_successes=len(reasoning),
                           provider_attempt_count=len(attempts))
                print(json.dumps({k: v for k, v in row.items() if k != "coverage"}), flush=True)
            campaign["token_budget"] = ledger.snapshot()
            campaign["updated_at"] = datetime.now(timezone.utc).isoformat()
            write(args.output, campaign)
            if any(not r.get("terminal") for r in campaign["rows"]):
                time.sleep(5)
        campaign["source_corpus_unchanged"] = inventory(args.corpus) == source_manifest
        campaign["scientific_source_unchanged"] = scientific_source == inventory(
            Path(__file__).resolve().parents[1] / "src/principia/data_discovery")
        campaign["state"] = "completed_pending_quality_review"
        campaign["finished_at"] = datetime.now(timezone.utc).isoformat()
        write(args.output, campaign)
    finally:
        product.close()


if __name__ == "__main__":
    main()
