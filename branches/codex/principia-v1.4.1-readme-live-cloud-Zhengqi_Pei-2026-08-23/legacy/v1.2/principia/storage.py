from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from .config import STORE_DB_PATH, STORE_PATH
from .models import utc_now
from .schema import ensure_artifact_dirs, ensure_v1_schema
from .utils import enrich_query, lexical_score, tokenize, validation_number


BUCKETS = [
    "goals",
    "source_works",
    "principles",
    "principle_relations",
    "ideas",
    "estimates",
    "prompt_plans",
    "runs",
    "feedback",
    "field_profiles",
    "project_memberships",
    "work_facts",
    "benchmark_records",
    "baseline_records",
    "result_records",
    "gap_cards",
    "frontier_snapshots",
    "assistant_exports",
    "existed_ideas",
    "takeaway_messages",
    "my_ideas",
    "evidence_links",
    "research_runs",
]

EMPTY_STORE: dict[str, Any] = {
    "meta": {"created_at": None, "updated_at": None, "backend": "sqlite"},
    **{bucket: {} for bucket in BUCKETS},
}

RICH_SCALAR_FIELDS = [
    "principle_type",
    "abstraction_level",
    "abstract_signature",
    "mechanism",
    "problem_pressure",
    "objective",
    "validation_level",
]

RICH_LIST_FIELDS = [
    "scarce_resources",
    "assumptions",
    "constraints",
    "invariants",
    "tradeoffs",
    "failure_modes",
    "feedback_loop",
    "transfer_hooks",
    "empirical_claims",
    "validation_notes",
    "domain_tags",
    "relation_hints",
    "compatible_principles",
    "contradiction_links",
]


class Store:
    """SQLite-backed object store for the local-first Principia app.

    The public methods intentionally match the original JSON store so the CLI,
    server, and engine can keep using typed dictionaries. SQLite gives us
    incremental writes, simple indexes, and a migration path toward larger
    principle pools without rewriting the whole app.
    """

    def __init__(self, path: Path = STORE_DB_PATH):
        if path.suffix == ".json":
            path = path.with_name("principia.sqlite")
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        ensure_artifact_dirs(self.path.parent.parent)
        self._lock = threading.Lock()
        self._init_db()
        self._migrate_json_once()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS records (
                    bucket TEXT NOT NULL,
                    id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (bucket, id)
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_records_bucket_updated ON records(bucket, updated_at)")
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_records_bucket_canonical_key
                ON records(bucket, json_extract(payload, '$.canonical_key'))
                WHERE json_extract(payload, '$.canonical_key') IS NOT NULL
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_records_membership_field_bucket
                ON records(
                    json_extract(payload, '$.field_id'),
                    json_extract(payload, '$.bucket'),
                    json_extract(payload, '$.hidden'),
                    json_extract(payload, '$.display_order'),
                    created_at
                )
                WHERE bucket = 'project_memberships'
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_records_membership_record
                ON records(
                    json_extract(payload, '$.bucket'),
                    json_extract(payload, '$.record_id'),
                    json_extract(payload, '$.field_id')
                )
                WHERE bucket = 'project_memberships'
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_records_run_field_updated
                ON records(json_extract(payload, '$.field_id'), updated_at DESC)
                WHERE bucket = 'research_runs'
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_records_evidence_source_target
                ON records(
                    json_extract(payload, '$.source_id'),
                    json_extract(payload, '$.target_bucket'),
                    json_extract(payload, '$.target_id')
                )
                WHERE bucket = 'evidence_links'
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS principle_search (
                    principle_id TEXT PRIMARY KEY,
                    body TEXT NOT NULL,
                    validation_level TEXT NOT NULL,
                    confidence_score REAL NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_principle_search_updated ON principle_search(updated_at)")
            now = utc_now()
            conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES('created_at', ?)", (now,))
            conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('backend', 'sqlite')")
            conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('updated_at', ?)", (now,))
            ensure_v1_schema(conn)

    def _migrate_json_once(self) -> None:
        if not STORE_PATH.exists():
            return
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]
        if count:
            return
        try:
            data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return
        for bucket in BUCKETS:
            items = list((data.get(bucket) or {}).values())
            if items:
                id_key = self._id_key(bucket)
                self.upsert_many(bucket, items, id_key)
        legacy = STORE_PATH.with_suffix(".legacy.json")
        if not legacy.exists():
            STORE_PATH.replace(legacy)

    def _id_key(self, bucket: str) -> str:
        return {
            "goals": "goal_id",
            "source_works": "work_id",
            "principles": "principle_id",
            "principle_relations": "relation_id",
            "ideas": "idea_id",
            "estimates": "estimate_id",
            "prompt_plans": "prompt_plan_id",
            "runs": "run_id",
            "feedback": "feedback_id",
            "field_profiles": "field_id",
            "project_memberships": "membership_id",
            "work_facts": "fact_id",
            "benchmark_records": "benchmark_id",
            "baseline_records": "baseline_id",
            "result_records": "result_id",
            "gap_cards": "gap_id",
            "frontier_snapshots": "snapshot_id",
            "assistant_exports": "export_id",
            "existed_ideas": "canonical_id",
            "takeaway_messages": "canonical_id",
            "my_ideas": "idea_id",
            "evidence_links": "link_id",
            "research_runs": "run_id",
        }[bucket]

    def _touch_meta(self, conn: sqlite3.Connection) -> None:
        conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('updated_at', ?)", (utc_now(),))

    def _meta(self, conn: sqlite3.Connection) -> dict[str, Any]:
        rows = conn.execute("SELECT key, value FROM meta").fetchall()
        meta = {row["key"]: row["value"] for row in rows}
        meta.setdefault("backend", "sqlite")
        return meta

    def read(self) -> dict[str, Any]:
        return self.snapshot(limit_per_bucket=None)

    def snapshot(self, limit_per_bucket: int | None = 80) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            data = {"meta": self._meta(conn), **{bucket: {} for bucket in BUCKETS}}
            for bucket in BUCKETS:
                if limit_per_bucket is None:
                    rows = conn.execute(
                        "SELECT id, payload FROM records WHERE bucket = ? ORDER BY updated_at, id",
                        (bucket,),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT id, payload FROM (
                            SELECT id, payload, updated_at FROM records
                            WHERE bucket = ?
                            ORDER BY updated_at DESC, id DESC
                            LIMIT ?
                        )
                        ORDER BY updated_at, id
                        """,
                        (bucket, limit_per_bucket),
                    ).fetchall()
                data[bucket] = {row["id"]: json.loads(row["payload"]) for row in rows}
            return data

    def counts(self) -> dict[str, int]:
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT bucket, COUNT(*) AS count FROM records GROUP BY bucket").fetchall()
            counts = {bucket: 0 for bucket in BUCKETS}
            counts.update({row["bucket"]: int(row["count"]) for row in rows})
            return counts

    def list_items(self, bucket: str, *, query: str = "", limit: int = 100) -> list[dict[str, Any]]:
        if bucket not in BUCKETS:
            raise KeyError(f"Unknown store bucket: {bucket}")
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT payload, updated_at FROM records WHERE bucket = ? ORDER BY updated_at DESC, id DESC",
                (bucket,),
            ).fetchall()
        items = [json.loads(row["payload"]) for row in rows]
        if query:
            terms = set(tokenize(enrich_query(query)))
            if terms:
                scored: list[tuple[float, dict[str, Any]]] = []
                for item in items:
                    body = json.dumps(item, ensure_ascii=False)
                    score = lexical_score(query, body)
                    if score > 0:
                        scored.append((score, item))
                scored.sort(
                    key=lambda pair: (
                        bool(pair[1].get("highlighted")),
                        pair[1].get("usage_count", 0),
                        pair[0],
                    ),
                    reverse=True,
                )
                return [item for _, item in scored[:limit]]
        items.sort(
            key=lambda item: (
                bool(item.get("highlighted")),
                int(item.get("usage_count", 0) or 0),
                item.get("last_used_at") or item.get("updated_at") or item.get("created_at") or "",
            ),
            reverse=True,
        )
        return items[:limit]

    def get_item(self, bucket: str, item_id: str) -> dict[str, Any] | None:
        if bucket not in BUCKETS:
            raise KeyError(f"Unknown store bucket: {bucket}")
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM records WHERE bucket = ? AND id = ?",
                (bucket, item_id),
            ).fetchone()
        return json.loads(row["payload"]) if row else None

    def get_items_by_ids(self, bucket: str, item_ids: list[str]) -> list[dict[str, Any]]:
        if bucket not in BUCKETS:
            raise KeyError(f"Unknown store bucket: {bucket}")
        ids = [str(item_id) for item_id in item_ids if item_id]
        if not ids:
            return []
        items: dict[str, dict[str, Any]] = {}
        with self._lock, self._connect() as conn:
            for index in range(0, len(ids), 400):
                chunk = ids[index : index + 400]
                placeholders = ",".join("?" for _ in chunk)
                rows = conn.execute(
                    f"SELECT id, payload FROM records WHERE bucket = ? AND id IN ({placeholders})",
                    (bucket, *chunk),
                ).fetchall()
                items.update({row["id"]: json.loads(row["payload"]) for row in rows})
        return [items[item_id] for item_id in ids if item_id in items]

    def find_by_canonical_key(self, bucket: str, canonical_key: str) -> dict[str, Any] | None:
        if bucket not in BUCKETS:
            raise KeyError(f"Unknown store bucket: {bucket}")
        key = str(canonical_key or "")
        if not key:
            return None
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload FROM records
                WHERE bucket = ?
                AND json_extract(payload, '$.canonical_key') = ?
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (bucket, key),
            ).fetchone()
        return json.loads(row["payload"]) if row else None

    def list_project_memberships(self, field_id: str, bucket: str | None = None, *, include_hidden: bool = False) -> list[dict[str, Any]]:
        clauses = ["bucket = 'project_memberships'", "json_extract(payload, '$.field_id') = ?"]
        params: list[Any] = [field_id]
        if bucket:
            clauses.append("json_extract(payload, '$.bucket') = ?")
            params.append(bucket)
        if not include_hidden:
            clauses.append("COALESCE(json_extract(payload, '$.hidden'), 0) = 0")
        sql = f"""
            SELECT payload FROM records
            WHERE {' AND '.join(clauses)}
            ORDER BY CAST(COALESCE(json_extract(payload, '$.display_order'), 0) AS INTEGER), created_at, id
        """
        with self._lock, self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def count_project_memberships_by_bucket(self, field_id: str) -> dict[str, int]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT json_extract(payload, '$.bucket') AS record_bucket, COUNT(*) AS count
                FROM records
                WHERE bucket = 'project_memberships'
                AND json_extract(payload, '$.field_id') = ?
                AND COALESCE(json_extract(payload, '$.hidden'), 0) = 0
                GROUP BY record_bucket
                """,
                (field_id,),
            ).fetchall()
        return {str(row["record_bucket"]): int(row["count"]) for row in rows if row["record_bucket"]}

    def list_evidence_links_for_source(self, source_id: str) -> list[dict[str, Any]]:
        source_id = str(source_id or "")
        if not source_id:
            return []
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload FROM records
                WHERE bucket = 'evidence_links'
                AND json_extract(payload, '$.source_id') = ?
                """,
                (source_id,),
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def list_research_runs_for_field(self, field_id: str, *, limit: int = 1000) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload FROM records
                WHERE bucket = 'research_runs'
                AND json_extract(payload, '$.field_id') = ?
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
                """,
                (field_id, int(limit)),
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def last_research_run_for_field(self, field_id: str) -> dict[str, Any] | None:
        runs = self.list_research_runs_for_field(field_id, limit=1)
        return runs[0] if runs else None

    def delete_project_memberships(self, field_id: str) -> int:
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                DELETE FROM records
                WHERE bucket = 'project_memberships'
                AND json_extract(payload, '$.field_id') = ?
                """,
                (field_id,),
            )
            self._touch_meta(conn)
            return int(cursor.rowcount or 0)

    def delete_research_runs_for_field(self, field_id: str) -> int:
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                DELETE FROM records
                WHERE bucket = 'research_runs'
                AND json_extract(payload, '$.field_id') = ?
                """,
                (field_id,),
            )
            self._touch_meta(conn)
            return int(cursor.rowcount or 0)

    def update_item_flags(
        self,
        bucket: str,
        item_id: str,
        *,
        highlighted: bool | None = None,
        validated: bool | None = None,
    ) -> dict[str, Any]:
        if bucket not in BUCKETS:
            raise KeyError(f"Unknown store bucket: {bucket}")
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM records WHERE bucket = ? AND id = ?",
                (bucket, item_id),
            ).fetchone()
            if not row:
                raise KeyError(f"{bucket}:{item_id} not found")
            item = json.loads(row["payload"])
            if highlighted is not None:
                item["highlighted"] = highlighted
            if validated is not None:
                item["validated"] = validated
                if bucket == "ideas":
                    item["feedback_status"] = "validated" if validated else "unvalidated"
            item["updated_at"] = utc_now()
            self._upsert_one(conn, bucket, item, self._id_key(bucket))
            self._touch_meta(conn)
            return item

    def delete_item(self, bucket: str, item_id: str) -> None:
        if bucket not in BUCKETS:
            raise KeyError(f"Unknown store bucket: {bucket}")
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM records WHERE bucket = ? AND id = ?", (bucket, item_id))
            if bucket == "principles":
                conn.execute("DELETE FROM principle_search WHERE principle_id = ?", (item_id,))
                conn.execute(
                    """
                    DELETE FROM records
                    WHERE bucket = 'principle_relations'
                    AND (
                        json_extract(payload, '$.source_principle_id') = ?
                        OR json_extract(payload, '$.target_principle_id') = ?
                    )
                    """,
                    (item_id, item_id),
                )
            self._touch_meta(conn)

    def vacuum(self) -> None:
        with self._lock:
            with sqlite3.connect(self.path, timeout=60) as conn:
                conn.execute("VACUUM")

    def delete_principle_links_for_works(self, work_ids: set[str]) -> int:
        if not work_ids:
            return 0
        changed = 0
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT id, payload FROM records WHERE bucket = 'principles'").fetchall()
            for row in rows:
                principle = json.loads(row["payload"])
                sources = list(principle.get("source_works") or [])
                if not work_ids.intersection(sources):
                    continue
                remaining = [wid for wid in sources if wid not in work_ids]
                changed += 1
                if remaining:
                    principle["source_works"] = remaining
                    self._upsert_one(conn, "principles", principle, "principle_id")
                    continue
                pid = principle["principle_id"]
                conn.execute("DELETE FROM records WHERE bucket = 'principles' AND id = ?", (pid,))
                conn.execute("DELETE FROM principle_search WHERE principle_id = ?", (pid,))
                conn.execute(
                    """
                    DELETE FROM records
                    WHERE bucket = 'principle_relations'
                    AND (
                        json_extract(payload, '$.source_principle_id') = ?
                        OR json_extract(payload, '$.target_principle_id') = ?
                    )
                    """,
                    (pid, pid),
                )
            if changed:
                self._touch_meta(conn)
        return changed

    def touch_usage(self, references: dict[str, list[str]]) -> None:
        with self._lock, self._connect() as conn:
            for bucket, ids in references.items():
                if bucket not in BUCKETS:
                    continue
                for item_id in set(ids):
                    row = conn.execute(
                        "SELECT payload FROM records WHERE bucket = ? AND id = ?",
                        (bucket, item_id),
                    ).fetchone()
                    if not row:
                        continue
                    item = json.loads(row["payload"])
                    item["usage_count"] = int(item.get("usage_count", 0) or 0) + 1
                    item["last_used_at"] = utc_now()
                    self._upsert_one(conn, bucket, item, self._id_key(bucket))
            self._touch_meta(conn)

    def prune_least_used(
        self,
        *,
        max_works: int = 500,
        max_principles: int = 1000,
        max_ideas: int = 100,
    ) -> dict[str, Any]:
        targets = {
            "source_works": max_works,
            "principles": max_principles,
            "ideas": max_ideas,
        }
        deleted: dict[str, list[str]] = {bucket: [] for bucket in targets}
        with self._lock, self._connect() as conn:
            for bucket, keep_count in targets.items():
                rows = conn.execute(
                    "SELECT id, payload FROM records WHERE bucket = ?",
                    (bucket,),
                ).fetchall()
                items = [(row["id"], json.loads(row["payload"])) for row in rows]
                if len(items) <= keep_count:
                    continue
                items.sort(
                    key=lambda pair: (
                        bool(pair[1].get("highlighted")),
                        int(pair[1].get("usage_count", 0) or 0),
                        pair[1].get("last_used_at") or pair[1].get("updated_at") or pair[1].get("created_at") or "",
                    ),
                    reverse=True,
                )
                for item_id, _ in items[keep_count:]:
                    deleted[bucket].append(item_id)
                    conn.execute("DELETE FROM records WHERE bucket = ? AND id = ?", (bucket, item_id))
                    if bucket == "principles":
                        conn.execute("DELETE FROM principle_search WHERE principle_id = ?", (item_id,))
            self._touch_meta(conn)
        return {"deleted": {bucket: len(ids) for bucket, ids in deleted.items()}, "deleted_ids": deleted}

    def replace(self, data: dict[str, Any]) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM records")
            conn.execute("DELETE FROM principle_search")
            for bucket in BUCKETS:
                for item in (data.get(bucket) or {}).values():
                    self._upsert_one(conn, bucket, item, self._id_key(bucket))
            self._touch_meta(conn)

    def upsert_many(self, bucket: str, items: list[dict[str, Any]], id_key: str) -> None:
        if bucket not in BUCKETS:
            raise KeyError(f"Unknown store bucket: {bucket}")
        with self._lock, self._connect() as conn:
            for item in items:
                self._upsert_one(conn, bucket, item, id_key)
            self._touch_meta(conn)

    def upsert(self, bucket: str, item: dict[str, Any], id_key: str) -> None:
        self.upsert_many(bucket, [item], id_key)

    def _upsert_one(self, conn: sqlite3.Connection, bucket: str, item: dict[str, Any], id_key: str) -> None:
        item_id = str(item[id_key])
        now = utc_now()
        existing = conn.execute(
            "SELECT payload, created_at FROM records WHERE bucket = ? AND id = ?",
            (bucket, item_id),
        ).fetchone()
        existing_payload = json.loads(existing["payload"]) if existing else {}
        created_at = existing_payload.get("created_at") or (existing["created_at"] if existing else now)
        item.setdefault("created_at", created_at)
        item["updated_at"] = now
        conn.execute(
            """
            INSERT OR REPLACE INTO records(bucket, id, payload, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (bucket, item_id, json.dumps(item, ensure_ascii=False), created_at, now),
        )
        if bucket == "principles":
            self._index_principle(conn, item, now)

    def _index_principle(self, conn: sqlite3.Connection, principle: dict[str, Any], updated_at: str) -> None:
        body = self._principle_body(principle, {})
        conn.execute(
            """
            INSERT OR REPLACE INTO principle_search(
                principle_id, body, validation_level, confidence_score, updated_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                principle["principle_id"],
                body,
                principle.get("validation_level", "L0"),
                float(principle.get("confidence_score", 0.0)),
                updated_at,
            ),
        )

    def merge_principles(self, principles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        saved: list[dict[str, Any]] = []
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT id, payload FROM records WHERE bucket = 'principles'").fetchall()
            target = {row["id"]: json.loads(row["payload"]) for row in rows}
            signatures = {self._principle_signature(existing): pid for pid, existing in target.items()}
            for principle in principles:
                signature = self._principle_signature(principle)
                existing_id = signatures.get(signature)
                if existing_id:
                    existing = target.get(existing_id)
                    if existing is None:
                        existing_row = conn.execute(
                            "SELECT payload FROM records WHERE bucket = 'principles' AND id = ?",
                            (existing_id,),
                        ).fetchone()
                        existing = json.loads(existing_row["payload"]) if existing_row else None
                    if existing is None:
                        self._upsert_one(conn, "principles", principle, "principle_id")
                        target[principle["principle_id"]] = principle
                        saved.append(principle)
                        continue
                    merged = self._merge_principle_payload(existing, principle)
                    self._upsert_one(conn, "principles", merged, "principle_id")
                    target[merged["principle_id"]] = merged
                    saved.append(merged)
                else:
                    self._upsert_one(conn, "principles", principle, "principle_id")
                    signatures[signature] = principle["principle_id"]
                    target[principle["principle_id"]] = principle
                    saved.append(principle)
            self._touch_meta(conn)
        return saved

    def _merge_principle_payload(self, existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        merged = dict(existing)
        for field in RICH_SCALAR_FIELDS:
            value = incoming.get(field)
            if not value:
                continue
            current = merged.get(field)
            incoming_size = len(json.dumps(value, ensure_ascii=False))
            current_size = len(json.dumps(current, ensure_ascii=False)) if current else 0
            if not current or incoming_size > current_size:
                merged[field] = value
        for field in RICH_LIST_FIELDS:
            merged[field] = self._ordered_union(merged.get(field, []), incoming.get(field, []))
        merged["source_works"] = self._ordered_union(
            merged.get("source_works", []), incoming.get("source_works", [])
        )
        merged["evidence_spans"] = self._merge_evidence_spans(
            merged.get("evidence_spans", []), incoming.get("evidence_spans", [])
        )
        merged["confidence_score"] = max(
            float(merged.get("confidence_score", 0)),
            float(incoming.get("confidence_score", 0)),
        )
        merged["updated_at"] = utc_now()
        return merged

    def _ordered_union(self, left: list[Any], right: list[Any]) -> list[Any]:
        result: list[Any] = []
        seen: set[str] = set()
        for item in [*(left or []), *(right or [])]:
            key = json.dumps(item, ensure_ascii=False, sort_keys=True)
            if key not in seen:
                seen.add(key)
                result.append(item)
        return result

    def _merge_evidence_spans(self, left: list[dict[str, Any]], right: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return self._ordered_union(left or [], right or [])[:12]

    def _principle_signature(self, principle: dict[str, Any]) -> str:
        model_key = str(principle.get("model_mode") or "") + " " + str(principle.get("model_name") or "")
        name = principle.get("name", "").lower().strip()
        mechanism = principle.get("mechanism", "").lower().strip()
        return " ".join((model_key + " " + name + " " + mechanism).split())[:260]

    def _principle_body(self, principle: dict[str, Any], works: dict[str, dict[str, Any]]) -> str:
        source_titles = " ".join(
            works.get(wid, {}).get("title", "") for wid in principle.get("source_works", [])
        )
        return " ".join(
            [
                principle.get("name", ""),
                principle.get("mechanism", ""),
                principle.get("problem_pressure", ""),
                principle.get("abstract_signature", ""),
                principle.get("objective", ""),
                principle.get("principle_type", ""),
                " ".join(principle.get("scarce_resources", [])),
                " ".join(principle.get("assumptions", [])),
                " ".join(principle.get("constraints", [])),
                " ".join(principle.get("invariants", [])),
                " ".join(principle.get("tradeoffs", [])),
                " ".join(principle.get("failure_modes", [])),
                " ".join(principle.get("feedback_loop", [])),
                " ".join(principle.get("transfer_hooks", [])),
                " ".join(principle.get("empirical_claims", [])),
                " ".join(principle.get("domain_tags", [])),
                " ".join(principle.get("relation_hints", [])),
                source_titles,
            ]
        )

    def search_principles(
        self,
        query: str,
        top_k: int = 8,
        min_validation: str = "L0",
    ) -> list[dict[str, Any]]:
        data = self.snapshot(limit_per_bucket=None)
        min_level = validation_number(min_validation)
        works = data.get("source_works", {})
        query_terms = set(tokenize(enrich_query(query)))
        min_lexical = 0.2 if len(query_terms) >= 3 else 0.08
        scored: list[tuple[float, dict[str, Any]]] = []
        for principle in data.get("principles", {}).values():
            if validation_number(principle.get("validation_level", "L0")) < min_level:
                continue
            body = self._principle_body(principle, works)
            lexical = lexical_score(query, body)
            if query_terms and lexical < min_lexical:
                continue
            score = lexical
            score += 0.15 * float(principle.get("confidence_score", 0.0))
            score += 0.04 * validation_number(principle.get("validation_level", "L0"))
            item = dict(principle)
            item["_score"] = round(score, 4)
            item["_lexical_score"] = round(lexical, 4)
            scored.append((score, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in scored[:top_k]]

    def search_works(self, query: str, top_k: int = 20) -> list[dict[str, Any]]:
        data = self.snapshot(limit_per_bucket=None)
        scored: list[tuple[float, dict[str, Any]]] = []
        for work in data.get("source_works", {}).values():
            body = " ".join(
                [
                    work.get("title", ""),
                    work.get("abstract", ""),
                    " ".join(work.get("work_principles", [])),
                    " ".join(work.get("work_insights", [])),
                    " ".join(work.get("work_novelty", [])),
                    " ".join(work.get("authors", [])),
                    work.get("venue_or_source", ""),
                ]
            )
            score = lexical_score(query, body)
            if score <= 0:
                continue
            score += 0.08 if work.get("highlighted") else 0
            score += 0.01 * min(int(work.get("usage_count", 0) or 0), 20)
            item = dict(work)
            item["_score"] = round(score, 4)
            scored.append((score, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in scored[:top_k]]

    def reset(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM records")
            conn.execute("DELETE FROM principle_search")
            self._touch_meta(conn)
