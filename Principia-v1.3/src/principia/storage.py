from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from .ids import normalize_key, short_hash
from .models import (
    Idea,
    IdeaComparison,
    RunStatus,
    WorkFeatures,
    WorkItem,
    normalize_arxiv_identifier,
    normalize_doi_identifier,
    normalize_openalex_identifier,
    utc_now,
)

WORK_IDENTITY_COLUMNS = (
    "doi",
    "arxiv_id",
    "openalex_id",
    "semantic_scholar_id",
    "pmid",
)

WORK_IDENTITY_INDEXES = {
    "doi": "idx_works_doi",
    "arxiv_id": "idx_works_arxiv",
    "openalex_id": "idx_works_openalex",
    "semantic_scholar_id": "idx_works_semantic_scholar",
    "pmid": "idx_works_pmid",
}


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
                    semantic_scholar_id TEXT DEFAULT '',
                    pmid TEXT DEFAULT '',
                    abstract_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._migrate_work_identity_columns(conn)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_works_title_hash ON works(title_hash)")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS source_assets (
                    id TEXT PRIMARY KEY,
                    work_id TEXT NOT NULL,
                    corpus_name TEXT NOT NULL,
                    portable_uri TEXT NOT NULL UNIQUE,
                    relative_path TEXT NOT NULL,
                    absolute_path TEXT NOT NULL,
                    mime_type TEXT DEFAULT '',
                    parser_name TEXT NOT NULL,
                    parser_fingerprint TEXT NOT NULL,
                    byte_sha256 TEXT NOT NULL,
                    text_sha256 TEXT NOT NULL,
                    byte_size INTEGER NOT NULL,
                    character_count INTEGER NOT NULL,
                    chunk_count INTEGER NOT NULL,
                    normalized_text TEXT NOT NULL,
                    status TEXT NOT NULL,
                    warnings_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(work_id) REFERENCES works(id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_source_assets_work ON source_assets(work_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_source_assets_byte_hash ON source_assets(byte_sha256)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS source_asset_chunks (
                    asset_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    model TEXT NOT NULL,
                    chunk_hash TEXT NOT NULL,
                    extractor_fingerprint TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(asset_id, chunk_index, model, chunk_hash, extractor_fingerprint),
                    FOREIGN KEY(asset_id) REFERENCES source_assets(id)
                )
                """
            )
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
            self._reconcile_work_identity_duplicates(conn)
            self._ensure_work_identity_indexes(conn)

    def _migrate_work_identity_columns(self, conn: sqlite3.Connection) -> None:
        """Add and canonicalize v1.3.3 identifiers in rows and payloads.

        SQLite has no ``ADD COLUMN IF NOT EXISTS`` on the Python versions we
        support, so migrations are driven by ``PRAGMA table_info`` and are safe
        to run whenever an existing v1.3.0-v1.3.2 workspace is opened. Managed
        indexes are temporarily removed only when an indexed value must change,
        because previously distinct URL/case or arXiv-version spellings can
        canonicalize to the same identity. A fully migrated workspace therefore
        remains physically unchanged when it is opened again.
        """

        columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(works)").fetchall()}
        for name in WORK_IDENTITY_COLUMNS:
            if name not in columns:
                conn.execute(f"ALTER TABLE works ADD COLUMN {name} TEXT DEFAULT ''")
        select_columns = ", ".join(WORK_IDENTITY_COLUMNS)
        rows = conn.execute(f"SELECT id, {select_columns}, payload_json FROM works").fetchall()
        updates: list[tuple[dict[str, str], str, str]] = []
        indexed_value_changed = False
        for row in rows:
            raw_payload = str(row["payload_json"] or "{}")
            try:
                payload = json.loads(raw_payload)
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            raw_metadata = payload.get("metadata")
            metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
            values = {
                "doi": normalize_doi_identifier(
                    _first_text(
                        row["doi"], payload.get("doi"), metadata.get("doi"), metadata.get("DOI")
                    )
                ),
                "arxiv_id": normalize_arxiv_identifier(
                    _first_text(
                        row["arxiv_id"],
                        payload.get("arxiv_id"),
                        metadata.get("arxiv_id"),
                        metadata.get("arxivId"),
                    )
                ),
                "openalex_id": normalize_openalex_identifier(
                    _first_text(
                        row["openalex_id"],
                        payload.get("openalex_id"),
                        metadata.get("openalex_id"),
                        metadata.get("openalexId"),
                    )
                ),
                "semantic_scholar_id": _first_text(
                    row["semantic_scholar_id"],
                    payload.get("semantic_scholar_id"),
                    metadata.get("semantic_scholar_id"),
                    metadata.get("s2_id"),
                    metadata.get("paperId"),
                ),
                "pmid": _first_text(row["pmid"], payload.get("pmid"), metadata.get("pmid")),
            }
            payload.update(values)
            payload.setdefault("pdf_url", "")
            serialized_payload = json.dumps(payload, ensure_ascii=False)
            current_values = {
                column: str(row[column] or "") for column in WORK_IDENTITY_COLUMNS
            }
            identity_changed = any(
                current_values[column] != values[column] for column in WORK_IDENTITY_COLUMNS
            )
            if not identity_changed and raw_payload == serialized_payload:
                continue
            indexed_value_changed = indexed_value_changed or identity_changed
            updates.append((values, serialized_payload, str(row["id"])))

        if indexed_value_changed:
            for index_name in WORK_IDENTITY_INDEXES.values():
                conn.execute(f"DROP INDEX IF EXISTS {index_name}")

        for values, serialized_payload, work_id in updates:
            assignments = ", ".join(f"{column} = ?" for column in WORK_IDENTITY_COLUMNS)
            conn.execute(
                f"UPDATE works SET {assignments}, payload_json = ? WHERE id = ?",
                (
                    *(values[column] for column in WORK_IDENTITY_COLUMNS),
                    serialized_payload,
                    work_id,
                ),
            )

    def _reconcile_work_identity_duplicates(self, conn: sqlite3.Connection) -> None:
        """Resolve canonicalization collisions before unique indexes are built.

        Matching strong identifiers normally identify one work, so compatible
        rows are merged and dependent extraction rows are moved. If two rows
        share one provider identifier but carry conflicting strong identifiers,
        both works are preserved and only the suspect duplicate value is removed
        from the less-preferred row.
        """

        while True:
            duplicate: tuple[str, str] | None = None
            for column in WORK_IDENTITY_COLUMNS:
                row = conn.execute(
                    f"""
                    SELECT {column} AS value
                    FROM works
                    WHERE {column} != ''
                    GROUP BY {column}
                    HAVING COUNT(*) > 1
                    ORDER BY {column}
                    LIMIT 1
                    """
                ).fetchone()
                if row:
                    duplicate = (column, str(row["value"]))
                    break
            if duplicate is None:
                return

            column, value = duplicate
            ids = [
                str(row["id"])
                for row in conn.execute(
                    f"SELECT id FROM works WHERE {column} = ? ORDER BY id",
                    (value,),
                ).fetchall()
            ]
            works = [work for item in ids if (work := self._get_work_with_conn(conn, item))]
            if not works:
                for item in ids[1:]:
                    self._clear_work_identifier(conn, item, column, value)
                continue
            canonical = max(works, key=_migration_work_preference_key)
            merge_ids: list[str] = []
            for item in ids:
                if item == canonical.id:
                    continue
                candidate = self._get_work_with_conn(conn, item)
                if candidate is None or _known_distinct_identity(
                    canonical, candidate, shared=column
                ):
                    self._clear_work_identifier(conn, item, column, value)
                else:
                    merge_ids.append(item)
                    canonical = merge_stored_work(canonical, candidate).model_copy(
                        update={"id": canonical.id}
                    )
            if merge_ids:
                self._merge_existing_work_rows(conn, canonical.id, merge_ids)

    def _clear_work_identifier(
        self,
        conn: sqlite3.Connection,
        work_id: str,
        column: str,
        duplicate_value: str,
    ) -> None:
        row = conn.execute("SELECT payload_json FROM works WHERE id = ?", (work_id,)).fetchone()
        if row is None:
            return
        try:
            payload = json.loads(str(row["payload_json"] or "{}"))
        except (TypeError, json.JSONDecodeError):
            payload = {}
        payload[column] = ""
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        aliases = {
            "doi": ("doi", "DOI"),
            "arxiv_id": ("arxiv_id", "arxivId"),
            "openalex_id": ("openalex_id", "openalexId"),
            "semantic_scholar_id": ("semantic_scholar_id", "s2_id", "paperId"),
            "pmid": ("pmid",),
        }
        for alias in aliases[column]:
            metadata.pop(alias, None)
        warning = f"Discarded conflicting duplicate {column} identity {duplicate_value}."
        existing_warnings = metadata.get("identity_migration_warnings")
        if not isinstance(existing_warnings, list):
            existing_warnings = [existing_warnings] if existing_warnings else []
        metadata["identity_migration_warnings"] = unique_strings([*existing_warnings, warning])
        payload["metadata"] = metadata
        conn.execute(
            f"UPDATE works SET {column} = '', payload_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(payload, ensure_ascii=False), utc_now(), work_id),
        )

    def _ensure_work_identity_indexes(self, conn: sqlite3.Connection) -> None:
        for column, index_name in WORK_IDENTITY_INDEXES.items():
            conn.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} "
                f"ON works({column}) WHERE {column} != ''"
            )

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
                    self._merge_existing_work_rows(
                        conn, existing_id, [item for item in existing_ids if item != existing_id]
                    )
                existing_work = self._get_work_with_conn(conn, existing_id)
                if existing_work:
                    work = merge_stored_work(existing_work, work).model_copy(
                        update={"id": existing_id}
                    )
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
            INSERT INTO works(
                id, title_norm, title_hash, doi, arxiv_id, openalex_id,
                semantic_scholar_id, pmid, abstract_hash, payload_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title_norm=excluded.title_norm,
                title_hash=excluded.title_hash,
                doi=COALESCE(NULLIF(excluded.doi, ''), works.doi),
                arxiv_id=COALESCE(NULLIF(excluded.arxiv_id, ''), works.arxiv_id),
                openalex_id=COALESCE(NULLIF(excluded.openalex_id, ''), works.openalex_id),
                semantic_scholar_id=COALESCE(NULLIF(excluded.semantic_scholar_id, ''), works.semantic_scholar_id),
                pmid=COALESCE(NULLIF(excluded.pmid, ''), works.pmid),
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
                work.semantic_scholar_id,
                work.pmid,
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

    def _recover_work_identity_conflict(
        self, conn: sqlite3.Connection, work: WorkItem, exc: sqlite3.IntegrityError
    ) -> WorkItem:
        message = str(exc)
        identity_errors = tuple(f"works.{column}" for column, _ in self._identity_columns(work))
        if not any(marker in message for marker in identity_errors):
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

    def _existing_work_ids_for_identity(
        self, conn: sqlite3.Connection, work: WorkItem
    ) -> list[str]:
        ids: list[str] = []
        for column, value in self._identity_columns(work):
            if not value:
                continue
            row = conn.execute(
                f"SELECT id FROM works WHERE {column} = ? LIMIT 1", (value,)
            ).fetchone()
            if row and str(row["id"]) not in ids:
                ids.append(str(row["id"]))
        # Private local documents have a stable portable-URI id. A title is not
        # an identity: two lab notes named ``README`` must remain separate, and
        # a local manuscript must not collapse into a public record unless a
        # strong scholarly identifier matched above.
        if _is_local_work(work):
            return ids
        title_norm = normalize_key(work.title)
        title_hash = short_hash(title_norm, length=16)
        rows = conn.execute(
            "SELECT payload_json FROM works WHERE title_hash = ?",
            (title_hash,),
        ).fetchall()
        title_candidates: list[WorkItem] = []
        for row in rows:
            try:
                candidate = WorkItem.model_validate_json(row["payload_json"])
            except (TypeError, ValueError):
                continue
            if _is_local_work(candidate):
                continue
            if candidate.id not in ids and _cautious_title_identity_match(candidate, work):
                title_candidates.append(candidate)
        if not _strong_identity_values(work):
            identified_candidates = [
                set(values)
                for candidate in title_candidates
                if (values := _strong_identity_values(candidate))
            ]
            if len(identified_candidates) > 1 and not set.intersection(*identified_candidates):
                title_candidates = []
        ids.extend(candidate.id for candidate in title_candidates if candidate.id not in ids)
        return ids

    def _canonical_existing_work_id(
        self, conn: sqlite3.Connection, incoming: WorkItem, ids: list[str]
    ) -> str:
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
        return (
            ("doi", work.doi),
            ("arxiv_id", work.arxiv_id),
            ("openalex_id", work.openalex_id),
            ("semantic_scholar_id", work.semantic_scholar_id),
            ("pmid", work.pmid),
        )

    def _get_work_with_conn(self, conn: sqlite3.Connection, work_id: str) -> WorkItem | None:
        row = conn.execute("SELECT payload_json FROM works WHERE id = ?", (work_id,)).fetchone()
        return WorkItem.model_validate_json(row["payload_json"]) if row else None

    def _merge_identity_conflicts(self, conn: sqlite3.Connection, work: WorkItem) -> None:
        conflicts = [
            item for item in self._existing_work_ids_for_identity(conn, work) if item != work.id
        ]
        if conflicts:
            self._merge_existing_work_rows(conn, work.id, conflicts)

    def _merge_existing_work_rows(
        self, conn: sqlite3.Connection, canonical_id: str, duplicate_ids: list[str]
    ) -> None:
        canonical = self._get_work_with_conn(conn, canonical_id)
        if not canonical:
            return
        for duplicate_id in duplicate_ids:
            duplicate = self._get_work_with_conn(conn, duplicate_id)
            if not duplicate:
                continue
            canonical = merge_stored_work(canonical, duplicate).model_copy(
                update={"id": canonical_id}
            )
            self._move_or_drop_duplicate_extractions(conn, canonical_id, duplicate_id)
            conn.execute(
                "UPDATE source_assets SET work_id = ?, updated_at = ? WHERE work_id = ?",
                (canonical_id, utc_now(), duplicate_id),
            )
            conn.execute("DELETE FROM works_fts WHERE id = ?", (duplicate_id,))
            conn.execute("DELETE FROM works WHERE id = ?", (duplicate_id,))
        now = utc_now()
        title_norm = normalize_key(canonical.title)
        conn.execute(
            """
            UPDATE works
            SET title_norm = ?, title_hash = ?, doi = ?, arxiv_id = ?, openalex_id = ?,
                semantic_scholar_id = ?, pmid = ?, abstract_hash = ?, payload_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                title_norm,
                short_hash(title_norm, length=16),
                canonical.doi,
                canonical.arxiv_id,
                canonical.openalex_id,
                canonical.semantic_scholar_id,
                canonical.pmid,
                short_hash(canonical.abstract, length=16),
                json.dumps(canonical.model_dump(), ensure_ascii=False),
                now,
                canonical_id,
            ),
        )
        self._refresh_work_fts(conn, canonical)

    def _move_or_drop_duplicate_extractions(
        self, conn: sqlite3.Connection, canonical_id: str, duplicate_id: str
    ) -> None:
        rows = conn.execute(
            "SELECT id, model, content_hash, payload_json FROM extractions WHERE work_id = ?",
            (duplicate_id,),
        ).fetchall()
        for row in rows:
            existing = conn.execute(
                "SELECT id FROM extractions WHERE work_id = ? AND model = ? AND content_hash = ? LIMIT 1",
                (canonical_id, row["model"], row["content_hash"]),
            ).fetchone()
            if existing:
                conn.execute("DELETE FROM extractions WHERE id = ?", (row["id"],))
            else:
                try:
                    payload = json.loads(str(row["payload_json"] or "{}"))
                except (TypeError, json.JSONDecodeError):
                    payload = {}
                payload["work_id"] = canonical_id
                conn.execute(
                    """
                    UPDATE extractions
                    SET work_id = ?, payload_json = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (canonical_id, json.dumps(payload, ensure_ascii=False), utc_now(), row["id"]),
                )

    def save_works(self, works: list[WorkItem]) -> list[WorkItem]:
        return [self.save_work(work) for work in works]

    def list_works(self, limit: int = 200) -> list[WorkItem]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM works ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [WorkItem.model_validate_json(row["payload_json"]) for row in rows]

    def save_source_asset(self, asset: dict[str, Any]) -> dict[str, Any]:
        """Persist private source text and its absolute path only in hidden SQLite state."""

        now = utc_now()
        created_at = str(asset.get("created_at") or now)
        payload = dict(asset)
        payload_json = {key: value for key, value in payload.items() if key != "normalized_text"}
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO source_assets(
                    id, work_id, corpus_name, portable_uri, relative_path,
                    absolute_path, mime_type, parser_name, parser_fingerprint,
                    byte_sha256, text_sha256, byte_size, character_count,
                    chunk_count, normalized_text, status, warnings_json,
                    payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(portable_uri) DO UPDATE SET
                    id=excluded.id,
                    work_id=excluded.work_id,
                    corpus_name=excluded.corpus_name,
                    relative_path=excluded.relative_path,
                    absolute_path=excluded.absolute_path,
                    mime_type=excluded.mime_type,
                    parser_name=excluded.parser_name,
                    parser_fingerprint=excluded.parser_fingerprint,
                    byte_sha256=excluded.byte_sha256,
                    text_sha256=excluded.text_sha256,
                    byte_size=excluded.byte_size,
                    character_count=excluded.character_count,
                    chunk_count=excluded.chunk_count,
                    normalized_text=excluded.normalized_text,
                    status=excluded.status,
                    warnings_json=excluded.warnings_json,
                    payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at
                """,
                (
                    payload["id"],
                    payload["work_id"],
                    payload["corpus_name"],
                    payload["portable_uri"],
                    payload["relative_path"],
                    payload["absolute_path"],
                    payload.get("mime_type", ""),
                    payload["parser_name"],
                    payload["parser_fingerprint"],
                    payload["byte_sha256"],
                    payload["text_sha256"],
                    int(payload.get("byte_size") or 0),
                    int(payload.get("character_count") or 0),
                    int(payload.get("chunk_count") or 0),
                    payload.get("normalized_text", ""),
                    payload.get("status", "accepted"),
                    json.dumps(payload.get("warnings") or [], ensure_ascii=False),
                    json.dumps(payload_json, ensure_ascii=False),
                    created_at,
                    now,
                ),
            )
        payload["created_at"] = created_at
        payload["updated_at"] = now
        return payload

    def get_source_asset(self, asset_id: str) -> dict[str, Any] | None:
        return self._get_source_asset("id", asset_id)

    def get_source_asset_for_work(self, work_id: str) -> dict[str, Any] | None:
        return self._get_source_asset("work_id", work_id)

    def get_source_asset_by_uri(self, portable_uri: str) -> dict[str, Any] | None:
        return self._get_source_asset("portable_uri", portable_uri)

    def get_source_asset_by_byte_hash(self, byte_sha256: str) -> dict[str, Any] | None:
        return self._get_source_asset("byte_sha256", byte_sha256)

    def _get_source_asset(self, column: str, value: str) -> dict[str, Any] | None:
        allowed = {"id", "work_id", "portable_uri", "byte_sha256"}
        if column not in allowed:
            raise ValueError(f"Unsupported source asset lookup column: {column}")
        with self.connect() as conn:
            row = conn.execute(
                f"SELECT * FROM source_assets WHERE {column} = ? ORDER BY updated_at DESC LIMIT 1",
                (value,),
            ).fetchone()
        return _source_asset_from_row(row) if row else None

    def get_source_chunk_extraction(
        self,
        asset_id: str,
        chunk_index: int,
        model: str,
        chunk_hash: str,
        extractor_fingerprint: str,
    ) -> WorkFeatures | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json FROM source_asset_chunks
                WHERE asset_id = ? AND chunk_index = ? AND model = ?
                  AND chunk_hash = ? AND extractor_fingerprint = ?
                """,
                (asset_id, chunk_index, model, chunk_hash, extractor_fingerprint),
            ).fetchone()
        return WorkFeatures.model_validate_json(row["payload_json"]) if row else None

    def save_source_chunk_extraction(
        self,
        asset_id: str,
        chunk_index: int,
        model: str,
        chunk_hash: str,
        extractor_fingerprint: str,
        features: WorkFeatures,
    ) -> None:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO source_asset_chunks(
                    asset_id, chunk_index, model, chunk_hash,
                    extractor_fingerprint, payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(asset_id, chunk_index, model, chunk_hash, extractor_fingerprint)
                DO UPDATE SET payload_json=excluded.payload_json, updated_at=excluded.updated_at
                """,
                (
                    asset_id,
                    int(chunk_index),
                    model,
                    chunk_hash,
                    extractor_fingerprint,
                    json.dumps(features.model_dump(), ensure_ascii=False),
                    now,
                    now,
                ),
            )

    def prune_source_text_cache(self) -> int:
        """Clear cached private text while retaining resumable file metadata."""

        with self.connect() as conn:
            count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM source_assets WHERE normalized_text != ''"
                ).fetchone()[0]
            )
            rows = conn.execute("SELECT id, payload_json FROM source_assets").fetchall()
            for row in rows:
                try:
                    payload = json.loads(str(row["payload_json"] or "{}"))
                except (TypeError, json.JSONDecodeError):
                    payload = {}
                payload.pop("normalized_text", None)
                conn.execute(
                    "UPDATE source_assets SET normalized_text = '', payload_json = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(payload, ensure_ascii=False), utc_now(), row["id"]),
                )
        return count

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

    def content_hash(
        self, work: WorkItem, extra_text: str = "", extractor_fingerprint: str = ""
    ) -> str:
        """Hash all extraction content and the prompt/schema fingerprint.

        v1.3.2 considered only the first 2,000 characters, which could silently
        reuse a cache entry when later sections or the extraction schema changed.
        The longer v1.3.3 digest intentionally invalidates those legacy keys.
        """

        return short_hash(work.title, work.abstract, extra_text, extractor_fingerprint, length=40)

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
                (
                    idea.id,
                    idea.mode,
                    idea.model,
                    json.dumps(idea.model_dump(), ensure_ascii=False),
                    idea.created_at,
                    now,
                ),
            )
        return idea

    def save_comparison(self, comparison: IdeaComparison) -> IdeaComparison:
        comparison_id = short_hash(
            comparison.idea_id, comparison.model, comparison.created_at, length=16
        )
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
                (
                    status.run_id,
                    json.dumps(status.model_dump(), ensure_ascii=False),
                    status.started_at,
                    status.updated_at,
                ),
            )
        return status

    def update_run(self, status: RunStatus) -> RunStatus:
        status.updated_at = utc_now()
        with self.connect() as conn:
            conn.execute(
                "UPDATE runs SET payload_json = ?, updated_at = ? WHERE id = ?",
                (
                    json.dumps(status.model_dump(), ensure_ascii=False),
                    status.updated_at,
                    status.run_id,
                ),
            )
        return status

    def get_run(self, run_id: str) -> RunStatus | None:
        with self.connect() as conn:
            row = conn.execute("SELECT payload_json FROM runs WHERE id = ?", (run_id,)).fetchone()
        return RunStatus.model_validate_json(row["payload_json"]) if row else None

    def log_event(
        self, run_id: str, stage: str, message: str, payload: dict[str, Any] | None = None
    ) -> None:
        created = utc_now()
        event_id = short_hash(run_id, stage, message, created, time.time_ns(), length=16)
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO run_events(id, run_id, stage, message, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    event_id,
                    run_id,
                    stage,
                    message,
                    json.dumps(payload or {}, ensure_ascii=False),
                    created,
                ),
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
        names = [
            "works",
            "source_assets",
            "extractions",
            "ideas",
            "comparisons",
            "runs",
            "run_events",
        ]
        with self.connect() as conn:
            return {
                name: int(conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
                for name in names
            }

    def compact(self) -> None:
        with self.connect() as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.execute("VACUUM")


def merge_stored_work(left: WorkItem, right: WorkItem) -> WorkItem:
    preferred, secondary = (
        (right, left)
        if stored_work_preference_key(right) > stored_work_preference_key(left)
        else (left, right)
    )
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
    if (
        secondary.metadata.get("is_preprint")
        or preferred.metadata.get("is_preprint")
        or secondary.metadata.get("has_preprint")
        or preferred.metadata.get("has_preprint")
    ):
        metadata["has_preprint"] = True
    return preferred.model_copy(
        update={
            "authors": preferred.authors or secondary.authors,
            "abstract": preferred.abstract
            if len(preferred.abstract) >= len(secondary.abstract)
            else secondary.abstract,
            "published_at": preferred.published_at or secondary.published_at,
            "year": preferred.year or secondary.year,
            "venue": preferred.venue or secondary.venue,
            "source": preferred.source or secondary.source,
            "source_type": preferred.source_type or secondary.source_type,
            "url": preferred.url or secondary.url,
            "doi": preferred.doi or secondary.doi,
            "arxiv_id": preferred.arxiv_id or secondary.arxiv_id,
            "openalex_id": preferred.openalex_id or secondary.openalex_id,
            "semantic_scholar_id": preferred.semantic_scholar_id or secondary.semantic_scholar_id,
            "pmid": preferred.pmid or secondary.pmid,
            "pdf_url": preferred.pdf_url or secondary.pdf_url,
            "source_urls": unique_strings(
                [preferred.url, secondary.url, *preferred.source_urls, *secondary.source_urls]
            ),
            "citation_count": max_optional_int(preferred.citation_count, secondary.citation_count),
            "content_sha256": preferred.content_sha256 or secondary.content_sha256,
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
    return {
        "crossref": 5,
        "europepmc": 4,
        "openalex": 3,
        "semantic_scholar": 2,
        "arxiv": 1,
    }.get(str(source or "").lower(), 0)


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


def _cautious_title_identity_match(left: WorkItem, right: WorkItem) -> bool:
    """Match title-only records without collapsing known-distinct publications."""

    if _is_local_work(left) or _is_local_work(right):
        return False
    left_title = normalize_key(left.title)
    right_title = normalize_key(right.title)
    if not left_title or left_title != right_title:
        return False
    strong_fields = ("doi", "arxiv_id", "openalex_id", "semantic_scholar_id", "pmid")
    for field in strong_fields:
        left_value = normalize_key(getattr(left, field, ""))
        right_value = normalize_key(getattr(right, field, ""))
        if left_value and right_value and left_value != right_value:
            return False
    if left.year is not None and right.year is not None and abs(left.year - right.year) > 2:
        return False
    left_author = normalize_key(left.authors[0]) if left.authors else ""
    right_author = normalize_key(right.authors[0]) if right.authors else ""
    if left_author and right_author and left_author != right_author:
        return False
    if left_author and right_author:
        return True
    # Exact long titles are sufficiently discriminative for sparse title-only
    # source records. Short generic titles still fall back to their stable ID.
    return len(left_title) >= 24 or len(left_title.split()) >= 5


def _strong_identity_values(work: WorkItem) -> tuple[str, ...]:
    values = (
        work.doi,
        work.arxiv_id,
        work.openalex_id,
        work.semantic_scholar_id,
        work.pmid,
    )
    return tuple(normalize_key(value) for value in values if str(value or "").strip())


def _known_distinct_identity(left: WorkItem, right: WorkItem, *, shared: str) -> bool:
    """Return true when another strong identifier proves two rows distinct."""

    for field in WORK_IDENTITY_COLUMNS:
        if field == shared:
            continue
        left_value = normalize_key(getattr(left, field, ""))
        right_value = normalize_key(getattr(right, field, ""))
        if left_value and right_value and left_value != right_value:
            return True
    return False


def _migration_work_preference_key(work: WorkItem) -> tuple[int, int, int, int, int, int, str]:
    """Choose a deterministic, information-rich canonical row in migrations."""

    identifiers = sum(bool(getattr(work, field, "")) for field in WORK_IDENTITY_COLUMNS)
    return (
        *stored_work_preference_key(work),
        identifiers,
        len(work.abstract),
        work.id,
    )


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _is_local_work(work: WorkItem) -> bool:
    return (
        work.source == "local"
        or work.source_type == "local_document"
        or work.url.startswith("local://")
    )


def _source_asset_from_row(row: sqlite3.Row) -> dict[str, Any]:
    try:
        payload = json.loads(str(row["payload_json"] or "{}"))
    except (TypeError, json.JSONDecodeError):
        payload = {}
    try:
        warnings = json.loads(str(row["warnings_json"] or "[]"))
    except (TypeError, json.JSONDecodeError):
        warnings = []
    payload.update(
        {
            "id": str(row["id"]),
            "work_id": str(row["work_id"]),
            "corpus_name": str(row["corpus_name"]),
            "portable_uri": str(row["portable_uri"]),
            "relative_path": str(row["relative_path"]),
            "absolute_path": str(row["absolute_path"]),
            "mime_type": str(row["mime_type"] or ""),
            "parser_name": str(row["parser_name"]),
            "parser_fingerprint": str(row["parser_fingerprint"]),
            "byte_sha256": str(row["byte_sha256"]),
            "text_sha256": str(row["text_sha256"]),
            "byte_size": int(row["byte_size"]),
            "character_count": int(row["character_count"]),
            "chunk_count": int(row["chunk_count"]),
            "normalized_text": str(row["normalized_text"] or ""),
            "status": str(row["status"]),
            "warnings": warnings if isinstance(warnings, list) else [],
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }
    )
    return payload
