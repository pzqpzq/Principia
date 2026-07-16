from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .global_store import GlobalStore
from .models import utc_now
from .storage import BUCKETS
from .utils import stable_id


class DemoToV1Migration:
    def __init__(self, global_store: GlobalStore):
        self.global_store = global_store

    def migrate_from_legacy_store(self, data: dict[str, Any], *, project_id: str = "default", source: str = "legacy_store") -> dict[str, Any]:
        migration_id = stable_id("MIG", source, project_id, utc_now())
        self._mark(migration_id, source, "running", {"project_id": project_id})
        try:
            counts = self.global_store.sync_legacy_data(data, project_id=project_id, source=source)
            self._mark(migration_id, source, "complete", counts, completed=True)
            return {"ok": True, "migration_id": migration_id, "counts": counts}
        except Exception as exc:
            self._mark(migration_id, source, "error", {"error": str(exc)}, completed=True)
            raise

    def migrate_from_sqlite(self, path: str | Path, *, project_id: str = "default") -> dict[str, Any]:
        source_path = Path(path)
        if not source_path.exists():
            raise FileNotFoundError(source_path)
        data = self._read_records_table(source_path)
        return self.migrate_from_legacy_store(data, project_id=project_id, source=str(source_path))

    def _read_records_table(self, path: Path) -> dict[str, Any]:
        data = {"meta": {}, **{bucket: {} for bucket in BUCKETS}}
        with sqlite3.connect(path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT bucket, id, payload FROM records").fetchall()
            for row in rows:
                if row["bucket"] not in data:
                    data[row["bucket"]] = {}
                data[row["bucket"]][row["id"]] = json.loads(row["payload"])
        return data

    def _mark(self, migration_id: str, source: str, status: str, detail: dict[str, Any], *, completed: bool = False) -> None:
        with self.global_store._connect() as conn:
            started = utc_now()
            conn.execute(
                """
                INSERT INTO migration_status(migration_id, source, status, detail_json, started_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(migration_id) DO UPDATE SET
                    status=excluded.status,
                    detail_json=excluded.detail_json,
                    completed_at=excluded.completed_at
                """,
                (migration_id, source, status, json.dumps(detail, ensure_ascii=False), started, utc_now() if completed else None),
            )
