from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from principia.storage import WorkspaceStorage
from principia.storage_maintenance import compact_database, database_usage, reclaim_deleted_pages


def populated_database(path: Path, *, incremental: bool = False) -> Path:
    with sqlite3.connect(path) as conn:
        if incremental:
            conn.execute("PRAGMA auto_vacuum=INCREMENTAL")
        conn.execute("CREATE TABLE evidence(id INTEGER PRIMARY KEY, payload BLOB)")
        conn.executemany("INSERT INTO evidence(payload) VALUES(?)", [(b"science" * 2000,)] * 256)
        conn.execute("DELETE FROM evidence WHERE id > 8")
    return path


def test_new_workspace_enables_incremental_reclamation(tmp_path):
    storage = WorkspaceStorage(tmp_path / "working")
    assert database_usage(storage.db_path)["incremental_reclamation"]


def test_delete_reclaims_pages_without_changing_surviving_evidence(tmp_path):
    database = populated_database(tmp_path / "new.sqlite", incremental=True)
    before = database_usage(database)
    result = reclaim_deleted_pages(database)
    assert result["reclaimed_bytes"] > 0
    assert database_usage(database)["allocated_bytes"] < before["allocated_bytes"]
    with sqlite3.connect(database) as conn:
        assert conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == 8
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_legacy_compaction_is_explicit_and_preserves_evidence(tmp_path):
    database = populated_database(tmp_path / "legacy.sqlite")
    original = database.read_bytes()
    assert not database_usage(database)["incremental_reclamation"]
    assert database.read_bytes() == original
    assert reclaim_deleted_pages(database)["reclaimed_bytes"] == 0
    assert database.read_bytes() == original
    result = compact_database(database)
    assert result["after"]["incremental_reclamation"]
    assert result["after"]["allocated_bytes"] < result["before"]["allocated_bytes"] / 4
    with sqlite3.connect(database) as conn:
        assert conn.execute("SELECT payload FROM evidence").fetchall() == [(b"science" * 2000,)] * 8


def test_maintenance_failure_does_not_undo_committed_delete(tmp_path):
    result = reclaim_deleted_pages(tmp_path / "missing.sqlite")
    assert result["maintenance_pending"]
    assert not (tmp_path / "missing.sqlite").exists()


@pytest.mark.parametrize("live_process", [True, False])
def test_compaction_refuses_active_server_or_job(tmp_path, live_process):
    database = populated_database(tmp_path / "busy.sqlite")
    with sqlite3.connect(database) as conn:
        if live_process:
            conn.execute("CREATE TABLE workspace_runtime_leases(process_id INTEGER)")
            conn.execute("INSERT INTO workspace_runtime_leases VALUES(?)", (os.getpid(),))
        else:
            conn.execute("CREATE TABLE v14_jobs(state TEXT)")
            conn.execute("INSERT INTO v14_jobs VALUES('running')")
    before = database.read_bytes()
    with pytest.raises(ValueError):
        compact_database(database)
    assert database.read_bytes() == before
