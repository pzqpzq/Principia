#!/usr/bin/env python3
"""Transactionally project hypothesis-planning Principles into saved studies.

This is an explicit derived-state repair. It never changes source assets,
Findings, Tests, hypotheses, or evidence anchors. Run it with the Principia
server stopped so the database backup and projection replacement are auditable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from principia import Principia
from principia.models import utc_now


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--working-directory", required=True, type=Path)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--backup", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args()

    if not args.database.is_file():
        parser.error("database does not exist")
    if args.backup.exists():
        parser.error("backup already exists; choose a fresh immutable target")
    args.backup.parent.mkdir(parents=True, exist_ok=True)
    before_sha256 = _sha256(args.database)
    with sqlite3.connect(args.database) as source, sqlite3.connect(args.backup) as backup:
        source.backup(backup)
    backup_sha256 = _sha256(args.backup)

    product = Principia.open(working_directory=args.working_directory)
    rows: list[dict[str, Any]] = []
    try:
        with product.repository.connect() as connection:
            study_ids = [
                str(row[0])
                for row in connection.execute(
                    "SELECT study_id FROM data_studies "
                    "WHERE state IN ('succeeded','partial') ORDER BY created_at, study_id"
                ).fetchall()
            ]
        for study_id in study_ids:
            study = product.repository.data_study(study_id)
            if study is None:
                continue
            findings = product.repository.data_findings(study_id)
            linked = product.data_discovery.linked_principles(study_id)
            graph_principles = [
                *list(linked.get("principles") or []),
                *list(linked.get("foundations") or []),
            ]
            graph_receipt = product.repository.seed_data_discovery_graph(
                str(study.get("session_id") or ""),
                findings,
                graph_principles,
                product.repository.data_extra_principles(study_id),
                used_principle_ids=list(linked.get("used_principle_ids") or []),
            )
            workspace = product.data_discovery.workspace_records(study_id)
            product.repository.replace_workspace_projection(
                session_id=str(study.get("session_id") or ""),
                run_id=study_id,
                records=list(workspace.get("records") or []),
                edges=list(workspace.get("edges") or []),
            )
            coverage = dict(study.get("coverage") or {})
            coverage["graph_seed"] = graph_receipt
            coverage["workspace_record_counts"] = dict(workspace.get("counts") or {})
            coverage["planning_grounding_projection"] = {
                "schema_version": "principia.planning-grounding-repair/v1",
                "applied_at": utc_now(),
                "used_principle_count": len(
                    list(linked.get("used_principle_ids") or [])
                ),
            }
            product.repository.update_data_study(study_id, coverage=coverage)
            rows.append(
                {
                    "study_id": study_id,
                    "state": str(study.get("state") or ""),
                    "used_principles": len(
                        list(linked.get("used_principle_ids") or [])
                    ),
                    "foundations": len(list(linked.get("foundations") or [])),
                    "workspace_counts": dict(workspace.get("counts") or {}),
                    "graph_state": str(graph_receipt.get("state") or ""),
                }
            )
    finally:
        product.close()

    with sqlite3.connect(args.database) as connection:
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
    receipt = {
        "schema_version": "principia.planning-grounding-repair/v1",
        "applied_at": utc_now(),
        "database_before_sha256": before_sha256,
        "database_after_sha256": _sha256(args.database),
        "backup_sha256": backup_sha256,
        "backup_name": args.backup.name,
        "integrity_check": integrity,
        "study_count": len(rows),
        "studies": rows,
        "mutation_scope": (
            "derived graph/workspace projections and coverage receipts only; "
            "source assets, hypotheses, tests, findings, and evidence unchanged"
        ),
    }
    _write_json(args.receipt, receipt)
    print(json.dumps({"status": "repaired", "studies": len(rows), "integrity": integrity}))
    return 0 if integrity == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
