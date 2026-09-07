#!/usr/bin/env python3
"""Run read-only v1.4.2 inventory or Deep discovery over the frozen 20-scenario corpus."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from principia import Principia
from principia.data_discovery import AssetInventory

sys.path.insert(0, str(Path(__file__).resolve().parent))
from frozen_corpus import scan  # noqa: E402


def _assert_frozen(corpus: Path, expected: dict[str, Any]) -> None:
    actual = scan(corpus)
    comparable = {key: value for key, value in expected.items() if key != "created_at"}
    if actual != comparable:
        raise RuntimeError(
            "frozen corpus mismatch; evaluation stopped without attempting restoration"
        )


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--working-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("inventory", "deep"), default="inventory")
    parser.add_argument("--provider", choices=("", "siliconflow"), default="")
    parser.add_argument("--reasoning-model", default="auto")
    parser.add_argument("--vision-model", default="auto")
    parser.add_argument("--egress-confirmed", action="store_true")
    parser.add_argument(
        "--scenario-prefix",
        action="append",
        default=[],
        help="Evaluate only scenario folders beginning with this prefix; may be repeated.",
    )
    args = parser.parse_args()

    corpus = args.corpus.resolve(strict=True)
    expected = json.loads(args.receipt.read_text(encoding="utf-8"))
    _assert_frozen(corpus, expected)
    scenarios = [corpus / name for name in expected["scenario_names"]]
    if args.scenario_prefix:
        prefixes = tuple(dict.fromkeys(args.scenario_prefix))
        scenarios = [scenario for scenario in scenarios if scenario.name.startswith(prefixes)]
        if not scenarios:
            parser.error("--scenario-prefix did not match any frozen scenario")
    rows: list[dict[str, Any]] = []
    product: Principia | None = None
    if args.mode == "deep":
        product = Principia.open(
            working_directory=args.working_directory,
            cloud_root=args.working_directory / "cloud-cache",
        )
    try:
        for index, scenario in enumerate(scenarios, start=1):
            _assert_frozen(corpus, expected)
            source_id = f"frozen:{scenario.name[:2]}"
            if product is None:
                inventory = AssetInventory().inventory(
                    root=scenario,
                    source_id=source_id,
                    study_id=f"inventory:{scenario.name[:2]}",
                )
                row = {
                    "scenario": scenario.name,
                    "source_digest": inventory.source_digest,
                    "coverage": inventory.coverage,
                    "study_id": "",
                    "state": "inventoried",
                    "finding_count": 0,
                }
            else:
                product.repository.register_source(
                    source_id,
                    scenario,
                    f"frozen-scenario://{scenario.name[:2]}",
                    scenario.name,
                    f"Frozen evaluation/{scenario.name}",
                )
                study = product.data_discovery.create(
                    source_ids=[source_id],
                    objective="",
                    provider=args.provider,
                    reasoning_model=args.reasoning_model,
                    vision_model=args.vision_model,
                    knowledge_scope="combined",
                    prior_art="survivors",
                    budget="deep",
                    session_id="",
                    egress_confirmed=args.egress_confirmed,
                    defer=False,
                )
                test_count = int(study["coverage"].get("executed_test_count") or 0)
                status_counts = dict(study["coverage"].get("status_counts") or {})
                accounted_assets = sum(int(value) for value in status_counts.values())
                report_root = product.workspace.outputs_dir / str(study["study_id"])
                required_report_files = {
                    "report.md",
                    "report.json",
                    "findings.json",
                    "tests.json",
                    "provenance.json",
                }
                retained_report_files = {
                    item.name for item in report_root.iterdir() if item.is_file()
                } if report_root.is_dir() else set()
                if study["state"] not in {"succeeded", "partial"}:
                    raise RuntimeError(
                        f"{scenario.name}: Deep discovery did not complete ({study['state']})"
                    )
                if test_count < 1:
                    raise RuntimeError(
                        f"{scenario.name}: Deep discovery executed no valid scientific test"
                    )
                if accounted_assets != int(study["coverage"].get("asset_count") or 0):
                    raise RuntimeError(
                        f"{scenario.name}: inventory statuses do not account for every asset"
                    )
                if not required_report_files <= retained_report_files:
                    raise RuntimeError(
                        f"{scenario.name}: derived report export is incomplete"
                    )
                row = {
                    "scenario": scenario.name,
                    "source_digest": study["source_digest"],
                    "coverage": study["coverage"],
                    "study_id": study["study_id"],
                    "state": study["state"],
                    "finding_count": study["finding_count"],
                    "test_count": test_count,
                    "report_files": sorted(retained_report_files),
                    "accepted": True,
                }
            rows.append(row)
            _assert_frozen(corpus, expected)
            _atomic_json(
                args.output,
                {
                    "schema_version": "principia.frozen-corpus-evaluation/v1",
                    "mode": args.mode,
                    "provider": args.provider,
                    "corpus_digest": expected["corpus_digest"],
                    "completed_scenarios": index,
                    "selected_scenarios": len(scenarios),
                    "rows": rows,
                },
            )
            print(
                json.dumps(
                    {
                        "scenario": scenario.name,
                        "state": row["state"],
                        "assets": row["coverage"].get("asset_count", 0),
                        "tests": row["coverage"].get("executed_test_count", 0),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
    finally:
        if product is not None:
            product.close()
    _assert_frozen(corpus, expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
