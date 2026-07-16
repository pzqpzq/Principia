from __future__ import annotations

import json
import sqlite3
from typing import Any


class ConceptIndexer:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def index_work(self, work_id: str, title: str, abstract: str, metadata: dict[str, Any] | None = None) -> None:
        if not self._fts_enabled("work_fts"):
            return
        self.conn.execute("DELETE FROM work_fts WHERE work_id = ?", (work_id,))
        self.conn.execute(
            "INSERT INTO work_fts(work_id, title, abstract, metadata) VALUES (?, ?, ?, ?)",
            (work_id, title or "", abstract or "", json.dumps(metadata or {}, ensure_ascii=False)),
        )

    def index_concept(self, concept_id: str, concept_type: str, label: str, summary: str, payload: dict[str, Any]) -> None:
        if not self._fts_enabled("concept_fts"):
            return
        self.conn.execute("DELETE FROM concept_fts WHERE concept_id = ?", (concept_id,))
        self.conn.execute(
            "INSERT INTO concept_fts(concept_id, concept_type, label, summary, payload) VALUES (?, ?, ?, ?, ?)",
            (concept_id, concept_type, label or "", summary or "", json.dumps(payload or {}, ensure_ascii=False)),
        )

    def _fts_enabled(self, table: str) -> bool:
        try:
            self.conn.execute(f"SELECT rowid FROM {table} LIMIT 1").fetchone()
            return True
        except sqlite3.OperationalError:
            return False
