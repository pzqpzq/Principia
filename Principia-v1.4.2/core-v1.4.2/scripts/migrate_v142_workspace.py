#!/usr/bin/env python3
"""Apply the explicit v1.4.2 data-project consolidation migration.

The schema migrator runs when the workspace is opened. This command adds the
separate, auditable consolidation step that turns duplicate data sessions into
aliases while preserving every session, study, artifact, timestamp, and URL.
It must be run with the Principia server stopped.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from principia import Principia


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_backup(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as source_connection, sqlite3.connect(target) as target_connection:
        source_connection.backup(target_connection)
        check = target_connection.execute("PRAGMA quick_check").fetchone()
        if not check or str(check[0]).casefold() != "ok":
            raise RuntimeError("workspace backup failed SQLite quick_check")


def migrate(
    *,
    working_directory: Path,
    receipt_path: Path,
    cloud_root: Path | None,
) -> dict[str, Any]:
    working_directory = working_directory.expanduser().resolve(strict=True)
    database = working_directory / "workspace" / ".principia" / "principia.sqlite"
    if not database.is_file():
        raise FileNotFoundError(database)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = receipt_path.parent / "backups" / f"principia-pre-v142-consolidation-{timestamp}.sqlite"
    before_sha256 = _sha256(database)
    _sqlite_backup(database, backup)

    product = Principia.open(
        working_directory=working_directory,
        cloud_root=cloud_root,
    )
    try:
        consolidation = product.research_sessions.consolidate_data_sessions()
        diagnostics = product.diagnostics()
    finally:
        product.close()

    with sqlite3.connect(database) as connection:
        check = connection.execute("PRAGMA quick_check").fetchone()
        quick_check = str(check[0]) if check else "missing"
        if quick_check.casefold() != "ok":
            raise RuntimeError(f"migrated workspace failed SQLite quick_check: {quick_check}")
        counts = {
            "sessions": int(connection.execute("SELECT COUNT(*) FROM research_sessions").fetchone()[0]),
            "aliases": int(
                connection.execute("SELECT COUNT(*) FROM research_session_aliases").fetchone()[0]
            ),
            "data_runs": int(
                connection.execute("SELECT COUNT(*) FROM data_discovery_runs").fetchone()[0]
            ),
        }

    receipt = {
        "schema_version": "principia.workspace-root-cause-remediation/v1",
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "working_directory_role": "local_acceptance_workspace",
        "database_name": database.name,
        "database_sha256_before": before_sha256,
        "database_sha256_after": _sha256(database),
        "backup_name": backup.name,
        "backup_sha256": _sha256(backup),
        "quick_check": quick_check,
        "consolidation": consolidation,
        "counts": counts,
        "migration": diagnostics.get("workspace", {}).get("migration", {}),
        "path_policy": "absolute paths intentionally omitted",
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--working-directory", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--cloud-root", type=Path)
    args = parser.parse_args()
    receipt = migrate(
        working_directory=args.working_directory,
        receipt_path=args.receipt.expanduser().resolve(),
        cloud_root=args.cloud_root.expanduser().resolve() if args.cloud_root else None,
    )
    print(json.dumps(receipt, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
