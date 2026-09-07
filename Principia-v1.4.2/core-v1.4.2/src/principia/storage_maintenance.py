"""Explicit space maintenance; never deletes scientific records or raw files."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from ._sqlite import connect_sqlite


def database_usage(database: Path) -> dict[str, Any]:
    if not database.is_file():
        raise FileNotFoundError(database)
    with connect_sqlite(database.resolve().as_uri() + "?mode=ro", uri=True) as conn:
        page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
        pages = int(conn.execute("PRAGMA page_count").fetchone()[0])
        free = int(conn.execute("PRAGMA freelist_count").fetchone()[0])
        mode = int(conn.execute("PRAGMA auto_vacuum").fetchone()[0])
    wal = Path(str(database) + "-wal")
    return {"database_bytes": database.stat().st_size, "page_bytes": page_size,
            "allocated_bytes": pages * page_size, "reusable_bytes": free * page_size,
            "incremental_reclamation": mode == 2,
            "wal_bytes": wal.stat().st_size if wal.is_file() else 0}


def reclaim_deleted_pages(database: Path, *, maximum_pages: int = 4096) -> dict[str, Any]:
    """Bounded reclamation after explicit deletion, without a legacy DB rebuild."""
    before: dict[str, Any] = {}
    try:
        before = database_usage(database)
        if not before["incremental_reclamation"] or not before["reusable_bytes"]:
            return {"reclaimed_bytes": 0, "remaining_reusable_bytes": before["reusable_bytes"]}
        with connect_sqlite(database, timeout=0.1) as conn:
            conn.execute(f"PRAGMA incremental_vacuum({max(1, min(int(maximum_pages), 16384))})").fetchall()
            conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
        after = database_usage(database)
        return {"reclaimed_bytes": max(0, before["allocated_bytes"] - after["allocated_bytes"]),
                "remaining_reusable_bytes": after["reusable_bytes"]}
    except (sqlite3.Error, OSError):
        # Deletion has already committed. Maintenance contention must not turn
        # a successful delete into an error or invite a duplicate retry.
        return {"reclaimed_bytes": 0, "remaining_reusable_bytes": before.get("reusable_bytes"),
                "maintenance_pending": True}


def compact_database(database: Path) -> dict[str, Any]:
    """Explicit offline compaction also enables incremental mode in legacy DBs."""
    before = database_usage(database)
    with connect_sqlite(database, timeout=1) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "workspace_runtime_leases" in tables:
            for (pid,) in conn.execute("SELECT process_id FROM workspace_runtime_leases"):
                if int(pid) <= 0:
                    raise ValueError("Invalid runtime lease; inspect it before offline maintenance.")
                try:
                    os.kill(int(pid), 0)
                except ProcessLookupError:
                    continue
                except PermissionError:
                    pass
                raise ValueError("Stop the Principia server before compacting its workspace.")
        if "v14_jobs" in tables and conn.execute(
            "SELECT 1 FROM v14_jobs WHERE state IN ('running','queued','pausing','cancelling') LIMIT 1"
        ).fetchone():
            raise ValueError("Finish or cancel active jobs before compacting this workspace.")
        result = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        if result and result[0]:
            raise ValueError("Workspace is busy; stop its other processes before compacting.")
        conn.execute("PRAGMA auto_vacuum=INCREMENTAL")
        conn.execute("VACUUM")
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise RuntimeError("Database integrity check failed after compaction")
    return {"before": before, "after": database_usage(database)}
