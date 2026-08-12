from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from principia.cloud.registry import CloudRegistry
from principia.persistence.workspace import V14WorkspaceRepository
from principia.storage import WorkspaceStorage


def _assert_closed(connection: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        connection.execute("SELECT 1")


def test_legacy_workspace_transaction_closes_connection(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path / "legacy-workspace")
    with storage.connect() as connection:
        assert connection.execute("SELECT 1").fetchone()[0] == 1
    _assert_closed(connection)


def test_v14_repository_transaction_closes_connection(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path / "v14-workspace")
    repository = V14WorkspaceRepository(storage.db_path)
    with repository.connect() as connection:
        assert connection.execute("SELECT 1").fetchone()[0] == 1
    _assert_closed(connection)


def test_cloud_registry_transaction_closes_connection(tmp_path: Path) -> None:
    registry = CloudRegistry(tmp_path / "cloud")
    with registry.connect() as connection:
        assert connection.execute("SELECT 1").fetchone()[0] == 1
    _assert_closed(connection)
