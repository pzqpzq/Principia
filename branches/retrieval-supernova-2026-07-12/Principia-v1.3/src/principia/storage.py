from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from .ids import normalize_key, short_hash
from .models import Idea, IdeaComparison, RunStatus, WorkFeatures, WorkItem, utc_now


class WorkspaceStorage:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.meta_dir = self.root / ".principia"
        self.db_path = self.meta_dir / "principia.sqlite"
        self.artifacts_dir = self.meta_dir / "artifacts"
        self._ensure_layout()
        self._init_db()

    def _ensure_layout(self) -> None:
        for relative in (
            "",
            "artifacts/pdfs",
            "artifacts/source_json",
            "artifacts/runs",
            "artifacts/exports",
            "artifacts/cache",
        ):
            (self.meta_dir / relative).mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS works (
                    id TEXT PRIMARY KEY,
                    title_norm TEXT NOT NULL,
                    title_hash TEXT NOT NULL,
                    doi TEXT DEFAULT '',
                    arxiv_id TEXT DEFAULT '',
                    openalex_id TEXT DEFAULT '',
                    abstract_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_works_doi ON works(doi) WHERE doi != ''")
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_works_arxiv ON works(arxiv_id) WHERE arxiv_id != ''")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_works_title_hash ON works(title_hash)")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS extractions (
                    id TEXT PRIMARY KEY,
                    work_id TEXT NOT NULL,
                    model TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(work_id, model, content_hash),
                    FOREIGN KEY(work_id) REFERENCES works(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ideas (
                    id TEXT PRIMARY KEY,
                    mode TEXT NOT NULL,
                    model TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS comparisons (
                    id TEXT PRIMARY KEY,
                    idea_id TEXT NOT NULL,
                    model TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS run_events (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    message TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._ensure_fts(conn)

    def _ensure_fts(self, conn: sqlite3.Connection) -> None:
        try:
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS works_fts
                USING fts5(id UNINDEXED, title, abstract, authors, venue)
                """
            )
        except sqlite3.OperationalError:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS works_fts (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    abstract TEXT,
                    authors TEXT,
                    venue TEXT
                )
                """
            )

    def save_work(self, work: WorkItem) -> WorkItem:
        now = utc_now()
        with self.connect() as conn:
            existing_ids = self._existing_work_ids_for_identity(conn, work)
            existing_id = self._canonical_existing_work_id(conn, work, existing_ids)
            if existing_id:
                if len(existing_ids) > 1:
                    self._merge_existing_work_rows(conn, existing_id, [item for item in existing_ids if item != existing_id])
                existing_work = self._get_work_with_conn(conn, existing_id)
                if existing_work:
                    work = merge_stored_work(existing_work, work).model_copy(update={"id": existing_id})
                elif existing_id != work.id:
                    work = work.model_copy(update={"id": existing_id})
            self._merge_identity_conflicts(conn, work)
            payload = work.model_dump()
            payload["updated_at"] = now
            work = WorkItem.model_validate(payload)
            title_norm = normalize_key(work.title)
            title_hash = short_hash(title_norm, length=16)
            abstract_hash = short_hash(work.abstract, length=16)
            try:
                self._write_work_row(conn, work, title_norm, title_hash, abstract_hash, now)
            except sqlite3.IntegrityError as exc:
                work = self._recover_work_identity_conflict(conn, work, exc)
                payload = work.model_dump()
                payload["updated_at"] = now
                work = WorkItem.model_validate(payload)
                title_norm = normalize_key(work.title)
                title_hash = short_hash(title_norm, length=16)
                abstract_hash = short_hash(work.abstract, length=16)
                self._write_work_row(conn, work, title_norm, title_hash, abstract_hash, now)
            self._refresh_work_fts(conn, work)
        return work

    def _write_work_row(
        self,
        conn: sqlite3.Connection,
        work: WorkItem,
        title_norm: str,
        title_hash: str,
        abstract_hash: str,
        now: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO works(id, title_norm, title_hash, doi, arxiv_id, openalex_id, abstract_hash, payload_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title_norm=excluded.title_norm,
                title_hash=excluded.title_hash,
                doi=COALESCE(NULLIF(excluded.doi, ''), works.doi),
                arxiv_id=COALESCE(NULLIF(excluded.arxiv_id, ''), works.arxiv_id),
                openalex_id=COALESCE(NULLIF(excluded.openalex_id, ''), works.openalex_id),
                abstract_hash=excluded.abstract_hash,
                payload_json=excluded.payload_json,
                updated_at=excluded.updated_at
            """,
            (
                work.id,
                title_norm,
                title_hash,
                work.doi,
                work.arxiv_id,
                work.openalex_id,
                abstract_hash,
                json.dumps(work.model_dump(), ensure_ascii=False),
                work.created_at,
                now,
            ),
        )

    def _refresh_work_fts(self, conn: sqlite3.Connection, work: WorkItem) -> None:
        conn.execute("DELETE FROM works_fts WHERE id = ?", (work.id,))
        conn.execute(
            "INSERT INTO works_fts(id, title, abstract, authors, venue) VALUES (?, ?, ?, ?, ?)",
            (work.id, work.title, work.abstract, " ".join(work.authors), work.venue),
        )

    def _recover_work_identity_conflict(self, conn: sqlite3.Connection, work: WorkItem, exc: sqlite3.IntegrityError) -> WorkItem:
        message = str(exc)
        if "works.doi" not in message and "works.arxiv_id" not in message:
            raise exc
        conflict_ids = self._existing_work_ids_for_identity(conn, work)
        if not conflict_ids:
            raise exc
        canonical_id = self._canonical_existing_work_id(conn, work, conflict_ids) or conflict_ids[0]
        if not self._get_work_with_conn(conn, canonical_id):
            canonical_id = conflict_ids[0]
        duplicate_ids = [item for item in conflict_ids if item != canonical_id]
        if work.id != canonical_id and self._get_work_with_conn(conn, work.id):
            duplicate_ids.append(work.id)
        if duplicate_ids:
            self._merge_existing_work_rows(conn, canonical_id, unique_strings(duplicate_ids))
        existing_work = self._get_work_with_conn(conn, canonical_id)
        if existing_work:
            work = merge_stored_work(existing_work, work).model_copy(update={"id": canonical_id})
        else:
            work = work.model_copy(update={"id": canonical_id})
        self._merge_identity_conflicts(conn, work)
        return work

    def _existing_work_id_for_identity(self, conn: sqlite3.Connection, work: WorkItem) -> str:
        ids = self._existing_work_ids_for_identity(conn, work)
        return ids[0] if ids else ""

    def _existing_work_ids_for_identity(self, conn: sqlite3.Connection, work: WorkItem) -> list[str]:
        ids: list[str] = []
        for column, value in self._identity_columns(work):
            if not value:
                continue
            row = conn.execute(f"SELECT id FROM works WHERE {column} = ? LIMIT 1", (value,)).fetchone()
            if row and str(row["id"]) not in ids:
                ids.append(str(row["id"]))
        return ids

    def _canonical_existing_work_id(self, conn: sqlite3.Connection, incoming: WorkItem, ids: list[str]) -> str:
        if not ids:
            return ""
        candidates: list[WorkItem] = []
        for item in ids:
            candidate = self._get_work_with_conn(conn, item)
            if candidate is not None:
                candidates.append(candidate)
        if not candidates:
            return ids[0]
        candidates.append(incoming)
        preferred = max(candidates, key=stored_work_preference_key)
        if preferred.id in ids:
            return preferred.id
        return ids[0]

    def _identity_columns(self, work: WorkItem) -> tuple[tuple[str, str], ...]:
        return (("doi", work.doi), ("arxiv_id", work.arxiv_id), ("openalex_id", work.openalex_id))

    def _get_work_with_conn(self, conn: sqlite3.Connection, work_id: str) -> WorkItem | None:
        row = conn.execute("SELECT payload_json FROM works WHERE id = ?", (work_id,)).fetchone()
        return WorkItem.model_validate_json(row["payload_json"]) if row else None

    def _merge_identity_conflicts(self, conn: sqlite3.Connection, work: WorkItem) -> None:
        conflicts = [item for item in self._existing_work_ids_for_identity(conn, work) if item != work.id]
        if conflicts:
            self._merge_existing_work_rows(conn, work.id, conflicts)

    def _merge_existing_work_rows(self, conn: sqlite3.Connection, canonical_id: str, duplicate_ids: list[str]) -> None:
        canonical = self._get_work_with_conn(conn, canonical_id)
        if not canonical:
            return
        for duplicate_id in duplicate_ids:
            duplicate = self._get_work_with_conn(conn, duplicate_id)
            if not duplicate:
                continue
            canonical = merge_stored_work(canonical, duplicate).model_copy(update={"id": canonical_id})
            self._move_or_drop_duplicate_extractions(conn, canonical_id, duplicate_id)
            conn.execute("DELETE FROM works_fts WHERE id = ?", (duplicate_id,))
            conn.execute("DELETE FROM works WHERE id = ?", (duplicate_id,))
        now = utc_now()
        title_norm = normalize_key(canonical.title)
        conn.execute(
            """
            UPDATE works
            SET title_norm = ?, title_hash = ?, doi = ?, arxiv_id = ?, openalex_id = ?,
                abstract_hash = ?, payload_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                title_norm,
                short_hash(title_norm, length=16),
                canonical.doi,
                canonical.arxiv_id,
                canonical.openalex_id,
                short_hash(canonical.abstract, length=16),
                json.dumps(canonical.model_dump(), ensure_ascii=False),
                now,
                canonical_id,
            ),
        )

    def _move_or_drop_duplicate_extractions(self, conn: sqlite3.Connection, canonical_id: str, duplicate_id: str) -> None:
        rows = conn.execute("SELECT id, model, content_hash FROM extractions WHERE work_id = ?", (duplicate_id,)).fetchall()
        for row in rows:
            existing = conn.execute(
                "SELECT id FROM extractions WHERE work_id = ? AND model = ? AND content_hash = ? LIMIT 1",
                (canonical_id, row["model"], row["content_hash"]),
            ).fetchone()
            if existing:
                conn.execute("DELETE FROM extractions WHERE id = ?", (row["id"],))
            else:
                conn.execute("UPDATE extractions SET work_id = ?, updated_at = ? WHERE id = ?", (canonical_id, utc_now(), row["id"]))

    def save_works(self, works: list[WorkItem]) -> list[WorkItem]:
        return [self.save_work(work) for work in works]

    def list_works(self, limit: int = 200) -> list[WorkItem]:
        with self.connect() as conn:
            rows = conn.execute("SELECT payload_json FROM works ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        return [WorkItem.model_validate_json(row["payload_json"]) for row in rows]

    def list_latest_extractions(
        self,
        *,
        limit: int = 200,
        model: str | None = None,
        work_ids: list[str] | None = None,
    ) -> list[WorkFeatures]:
        clauses: list[str] = []
        params: list[Any] = []
        if model:
            clauses.append("model = ?")
            params.append(model)
        if work_ids:
            placeholders = ", ".join(["?"] * len(work_ids))
            clauses.append(f"work_id IN ({placeholders})")
            params.extend(work_ids)
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT payload_json FROM (
                SELECT payload_json, work_id, updated_at,
                       ROW_NUMBER() OVER (PARTITION BY work_id ORDER BY updated_at DESC) AS row_number
                FROM extractions
                {where_sql}
            )
            WHERE row_number = 1
            ORDER BY updated_at DESC
            LIMIT ?
        """
        params.append(max(1, int(limit)))
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [WorkFeatures.model_validate_json(row["payload_json"]) for row in rows]

    def list_extractions(
        self,
        *,
        limit: int = 200,
        model: str | None = None,
        work_ids: list[str] | None = None,
    ) -> list[WorkFeatures]:
        clauses: list[str] = []
        params: list[Any] = []
        if model:
            clauses.append("model = ?")
            params.append(model)
        if work_ids:
            placeholders = ", ".join(["?"] * len(work_ids))
            clauses.append(f"work_id IN ({placeholders})")
            params.extend(work_ids)
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, int(limit)))
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT payload_json FROM extractions {where_sql} ORDER BY updated_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [WorkFeatures.model_validate_json(row["payload_json"]) for row in rows]

    def get_work(self, work_id: str) -> WorkItem | None:
        with self.connect() as conn:
            row = conn.execute("SELECT payload_json FROM works WHERE id = ?", (work_id,)).fetchone()
        return WorkItem.model_validate_json(row["payload_json"]) if row else None

    def existing_work_ids(self) -> set[str]:
        with self.connect() as conn:
            return {row["id"] for row in conn.execute("SELECT id FROM works").fetchall()}

    def search_works(self, query: str, limit: int = 20) -> list[WorkItem]:
        try:
            with self.connect() as conn:
                rows = conn.execute(
                    """
                    SELECT w.payload_json FROM works_fts f
                    JOIN works w ON w.id = f.id
                    WHERE works_fts MATCH ?
                    ORDER BY rank LIMIT ?
                    """,
                    (query, limit),
                ).fetchall()
        except sqlite3.OperationalError:
            needle = f"%{normalize_key(query).replace(' ', '%')}%"
            with self.connect() as conn:
                rows = conn.execute(
                    "SELECT payload_json FROM works WHERE title_norm LIKE ? ORDER BY updated_at DESC LIMIT ?",
                    (needle, limit),
                ).fetchall()
        return [WorkItem.model_validate_json(row["payload_json"]) for row in rows]

    def content_hash(self, work: WorkItem, extra_text: str = "") -> str:
        return short_hash(work.title, work.abstract, extra_text[:2000], length=20)

    def get_extraction(self, work_id: str, model: str, content_hash: str) -> WorkFeatures | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json FROM extractions
                WHERE work_id = ? AND model = ? AND content_hash = ?
                """,
                (work_id, model, content_hash),
            ).fetchone()
        return WorkFeatures.model_validate_json(row["payload_json"]) if row else None

    def save_extraction(self, features: WorkFeatures, content_hash: str) -> WorkFeatures:
        now = utc_now()
        payload = features.model_dump()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO extractions(id, work_id, model, content_hash, payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(work_id, model, content_hash) DO UPDATE SET
                    id=excluded.id,
                    payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at
                """,
                (
                    features.extraction_id,
                    features.work_id,
                    features.model,
                    content_hash,
                    json.dumps(payload, ensure_ascii=False),
                    features.created_at,
                    now,
                ),
            )
        return features

    def latest_extraction_for_work(self, work_id: str) -> WorkFeatures | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM extractions WHERE work_id = ? ORDER BY updated_at DESC LIMIT 1",
                (work_id,),
            ).fetchone()
        return WorkFeatures.model_validate_json(row["payload_json"]) if row else None

    def save_idea(self, idea: Idea) -> Idea:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO ideas(id, mode, model, payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET payload_json=excluded.payload_json, updated_at=excluded.updated_at
                """,
                (idea.id, idea.mode, idea.model, json.dumps(idea.model_dump(), ensure_ascii=False), idea.created_at, now),
            )
        return idea

    def save_comparison(self, comparison: IdeaComparison) -> IdeaComparison:
        comparison_id = short_hash(comparison.idea_id, comparison.model, comparison.created_at, length=16)
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO comparisons(id, idea_id, model, payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET payload_json=excluded.payload_json, updated_at=excluded.updated_at
                """,
                (
                    comparison_id,
                    comparison.idea_id,
                    comparison.model,
                    json.dumps(comparison.model_dump(), ensure_ascii=False),
                    comparison.created_at,
                    now,
                ),
            )
        return comparison

    def create_run(self, status: RunStatus) -> RunStatus:
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO runs(id, payload_json, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (status.run_id, json.dumps(status.model_dump(), ensure_ascii=False), status.started_at, status.updated_at),
            )
        return status

    def update_run(self, status: RunStatus) -> RunStatus:
        status.updated_at = utc_now()
        with self.connect() as conn:
            conn.execute(
                "UPDATE runs SET payload_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(status.model_dump(), ensure_ascii=False), status.updated_at, status.run_id),
            )
        return status

    def get_run(self, run_id: str) -> RunStatus | None:
        with self.connect() as conn:
            row = conn.execute("SELECT payload_json FROM runs WHERE id = ?", (run_id,)).fetchone()
        return RunStatus.model_validate_json(row["payload_json"]) if row else None

    def log_event(self, run_id: str, stage: str, message: str, payload: dict[str, Any] | None = None) -> None:
        created = utc_now()
        event_id = short_hash(run_id, stage, message, created, time.time_ns(), length=16)
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO run_events(id, run_id, stage, message, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (event_id, run_id, stage, message, json.dumps(payload or {}, ensure_ascii=False), created),
            )

    def list_run_events(self, run_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT stage, message, payload_json, created_at FROM run_events WHERE run_id = ? ORDER BY created_at",
                (run_id,),
            ).fetchall()
        return [
            {
                "stage": row["stage"],
                "message": row["message"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def counts(self) -> dict[str, int]:
        names = ["works", "extractions", "ideas", "comparisons", "runs", "run_events"]
        with self.connect() as conn:
            return {name: int(conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]) for name in names}

    def compact(self) -> None:
        with self.connect() as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.execute("VACUUM")


def merge_stored_work(left: WorkItem, right: WorkItem) -> WorkItem:
    preferred, secondary = (right, left) if stored_work_preference_key(right) > stored_work_preference_key(left) else (left, right)
    metadata = {**secondary.metadata, **preferred.metadata}
    metadata["merged_sources"] = unique_strings(
        [
            *(secondary.metadata.get("merged_sources") or []),
            *(preferred.metadata.get("merged_sources") or []),
            secondary.source,
            preferred.source,
        ]
    )
    if secondary.metadata.get("is_peer_reviewed") or preferred.metadata.get("is_peer_reviewed"):
        metadata["is_peer_reviewed"] = True
    if secondary.metadata.get("is_preprint") or preferred.metadata.get("is_preprint") or secondary.metadata.get("has_preprint") or preferred.metadata.get("has_preprint"):
        metadata["has_preprint"] = True
    return preferred.model_copy(
        update={
            "authors": preferred.authors or secondary.authors,
            "abstract": preferred.abstract if len(preferred.abstract) >= len(secondary.abstract) else secondary.abstract,
            "published_at": preferred.published_at or secondary.published_at,
            "year": preferred.year or secondary.year,
            "venue": preferred.venue or secondary.venue,
            "source": preferred.source or secondary.source,
            "source_type": preferred.source_type or secondary.source_type,
            "url": preferred.url or secondary.url,
            "doi": preferred.doi or secondary.doi,
            "arxiv_id": preferred.arxiv_id or secondary.arxiv_id,
            "openalex_id": preferred.openalex_id or secondary.openalex_id,
            "source_urls": unique_strings([preferred.url, secondary.url, *preferred.source_urls, *secondary.source_urls]),
            "citation_count": max_optional_int(preferred.citation_count, secondary.citation_count),
            "metadata": metadata,
        }
    )


def stored_work_preference_key(work: WorkItem) -> tuple[int, int, int, int]:
    return (
        1 if bool(work.metadata.get("is_peer_reviewed")) else 0,
        venue_preference(work.venue),
        source_preference(work.source),
        int(work.citation_count or 0),
    )


def venue_preference(venue: str) -> int:
    normalized = normalize_key(venue)
    if not normalized or normalized in {"arxiv", "openalex", "crossref"}:
        return 0
    return 2


def source_preference(source: str) -> int:
    return {"crossref": 3, "openalex": 2, "arxiv": 1}.get(str(source or "").lower(), 0)


def max_optional_int(left: int | None, right: int | None) -> int | None:
    values = [value for value in (left, right) if value is not None]
    return max(values) if values else None


def unique_strings(values: list[Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        output.append(text)
        seen.add(text)
    return output
