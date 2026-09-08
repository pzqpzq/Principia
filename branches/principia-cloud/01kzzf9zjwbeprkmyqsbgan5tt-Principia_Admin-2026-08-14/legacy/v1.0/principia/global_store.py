from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .concept_canonicalizer import ConceptCanonicalizer, canonical_label, summarize_payload
from .concept_indexer import ConceptIndexer
from .config import STORE_DB_PATH
from .identity_resolver import WorkIdentityResolver, clean_external_id, extract_arxiv_id
from .models import utc_now
from .schema import ensure_v1_schema
from .utils import compact_text, stable_id
from .work_versioning import normalize_title, text_hash, work_content_signature, work_version_id


LEGACY_CONCEPT_BUCKETS = {
    "existed_ideas": "existed_idea",
    "principles": "principle",
    "takeaway_messages": "takeaway_message",
    "benchmark_records": "benchmark",
    "baseline_records": "baseline",
    "result_records": "result_fact",
    "ideas": "generated_idea",
    "my_ideas": "generated_idea",
    "gap_cards": "failure_mode",
    "work_facts": "takeaway_message",
}


class GlobalStore:
    def __init__(self, path: Path = STORE_DB_PATH):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            ensure_v1_schema(conn)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def vacuum(self) -> None:
        with sqlite3.connect(self.path, timeout=60) as conn:
            conn.execute("VACUUM")

    def counts(self) -> dict[str, int]:
        names = [
            "global_work",
            "work_version",
            "extraction_run",
            "concept_card",
            "concept_version",
            "evidence_link",
            "symbol_registry",
            "derivation_run",
            "derivation_node",
            "derivation_edge",
            "project_record_membership",
        ]
        with self._connect() as conn:
            return {name: int(conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]) for name in names}

    def all_works(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM global_work").fetchall()
        return [self._row_work(row) for row in rows]

    def upsert_work(self, work: dict[str, Any]) -> dict[str, Any]:
        resolver = WorkIdentityResolver()
        with self._connect() as conn:
            ensure_v1_schema(conn)
            candidates = [self._row_work(row) for row in conn.execute("SELECT * FROM global_work").fetchall()]
            resolution = resolver.resolve(work, candidates)
            title = compact_text(str(work.get("title") or work.get("canonical_title") or "Untitled work"), 320)
            title_norm = normalize_title(title)
            sig = work_content_signature({**work, "title": title})
            now = utc_now()
            source_urls = self._ordered_unique([*(work.get("source_urls") or []), work.get("url_or_doi") or work.get("paper_link") or ""])
            existing = resolution.existing or {}
            payload = {
                "authors": work.get("authors") or (existing.get("metadata") or {}).get("authors") or [],
                "citation_count": work.get("citation_count"),
                "community_signals": work.get("community_signals") or {},
                "source_updated_at": work.get("source_updated_at") or work.get("source_modified_at") or "",
                "legacy_work_id": work.get("work_id") or "",
            }
            conn.execute(
                """
                INSERT INTO global_work(
                    work_id, canonical_title, title_norm, title_hash, doi, arxiv_id, openalex_id,
                    crossref_id, semantic_scholar_id, year, venue_or_source, source_type,
                    source_urls_json, identity_confidence, identity_status, metadata_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(work_id) DO UPDATE SET
                    canonical_title=excluded.canonical_title,
                    title_norm=excluded.title_norm,
                    title_hash=excluded.title_hash,
                    doi=COALESCE(NULLIF(excluded.doi, ''), global_work.doi),
                    arxiv_id=COALESCE(NULLIF(excluded.arxiv_id, ''), global_work.arxiv_id),
                    openalex_id=COALESCE(NULLIF(excluded.openalex_id, ''), global_work.openalex_id),
                    crossref_id=COALESCE(NULLIF(excluded.crossref_id, ''), global_work.crossref_id),
                    semantic_scholar_id=COALESCE(NULLIF(excluded.semantic_scholar_id, ''), global_work.semantic_scholar_id),
                    year=COALESCE(excluded.year, global_work.year),
                    venue_or_source=COALESCE(NULLIF(excluded.venue_or_source, ''), global_work.venue_or_source),
                    source_type=COALESCE(NULLIF(excluded.source_type, ''), global_work.source_type),
                    source_urls_json=excluded.source_urls_json,
                    identity_confidence=excluded.identity_confidence,
                    identity_status=excluded.identity_status,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                (
                    resolution.work_id,
                    title,
                    title_norm,
                    sig["title_hash"],
                    clean_external_id(work.get("doi") or work.get("DOI") or ""),
                    clean_external_id(work.get("arxiv_id") or extract_arxiv_id(work)),
                    clean_external_id(work.get("openalex_id") or ""),
                    clean_external_id(work.get("crossref_id") or ""),
                    clean_external_id(work.get("semantic_scholar_id") or ""),
                    work.get("year"),
                    work.get("venue_or_source") or work.get("source") or "",
                    work.get("source_type") or "paper",
                    json.dumps(source_urls, ensure_ascii=False),
                    resolution.confidence,
                    resolution.status,
                    json.dumps(payload, ensure_ascii=False),
                    existing.get("created_at") or now,
                    now,
                ),
            )
            version = self.ensure_work_version_for_conn(conn, resolution.work_id, {**work, "title": title})
            ConceptIndexer(conn).index_work(resolution.work_id, title, work.get("abstract") or "", payload)
            saved = self._row_work(conn.execute("SELECT * FROM global_work WHERE work_id = ?", (resolution.work_id,)).fetchone())
            saved["work_version_id"] = version["work_version_id"]
            saved["identity_reason"] = resolution.reason
            return saved

    def ensure_work_version_for_conn(self, conn: sqlite3.Connection, work_id: str, work: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        sig = work_content_signature(work)
        version_id = work_version_id(work_id, work)
        row = conn.execute("SELECT * FROM work_version WHERE work_version_id = ?", (version_id,)).fetchone()
        if not row:
            conn.execute(
                """
                INSERT INTO work_version(
                    work_version_id, work_id, source_provider, source_record_id, title, abstract,
                    title_hash, abstract_hash, content_hash, source_modified_at, source_updated_at,
                    metadata_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version_id,
                    work_id,
                    work.get("source_provider") or (work.get("community_signals") or {}).get("source") or "",
                    work.get("source_record_id") or work.get("work_id") or "",
                    compact_text(str(work.get("title") or ""), 320),
                    compact_text(str(work.get("abstract") or ""), 6000),
                    sig["title_hash"],
                    sig["abstract_hash"],
                    sig["content_hash"],
                    work.get("source_modified_at") or "",
                    work.get("source_updated_at") or "",
                    json.dumps(work, ensure_ascii=False),
                    now,
                ),
            )
        return self._row_dict(conn.execute("SELECT * FROM work_version WHERE work_version_id = ?", (version_id,)).fetchone())

    def latest_work_version(self, work_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM work_version WHERE work_id = ? ORDER BY created_at DESC LIMIT 1",
                (work_id,),
            ).fetchone()
        return self._row_dict(row) if row else None

    def ensure_extraction_run(
        self,
        work_id: str,
        work_version_id: str,
        *,
        llm_provider: str,
        llm_model: str,
        model_mode: str = "auto",
        prompt_version: str,
        schema_version: str,
        extraction_task_type: str = "work_concepts",
    ) -> dict[str, Any]:
        run_id = stable_id("XRUN", work_version_id, llm_provider, llm_model, prompt_version, schema_version, extraction_task_type)
        now = utc_now()
        with self._connect() as conn:
            ensure_v1_schema(conn)
            conn.execute(
                """
                INSERT INTO extraction_run(
                    extraction_run_id, work_id, work_version_id, llm_provider, llm_model,
                    model_mode, prompt_version, schema_version, extraction_task_type,
                    extraction_status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?)
                ON CONFLICT(work_version_id, llm_provider, llm_model, prompt_version, schema_version, extraction_task_type)
                DO NOTHING
                """,
                (run_id, work_id, work_version_id, llm_provider, llm_model, model_mode, prompt_version, schema_version, extraction_task_type, now),
            )
            row = conn.execute("SELECT * FROM extraction_run WHERE extraction_run_id = ?", (run_id,)).fetchone()
            if row is None:
                row = conn.execute(
                    """
                    SELECT * FROM extraction_run
                    WHERE work_version_id = ? AND llm_provider = ? AND llm_model = ?
                    AND prompt_version = ? AND schema_version = ? AND extraction_task_type = ?
                    """,
                    (work_version_id, llm_provider, llm_model, prompt_version, schema_version, extraction_task_type),
                ).fetchone()
            return self._row_dict(row)

    def complete_extraction_run(self, extraction_run_id: str, *, result: dict[str, Any] | None = None, error: str = "") -> dict[str, Any]:
        status = "error" if error else "complete"
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE extraction_run
                SET extraction_status = ?, result_json = ?, error_message = ?, completed_at = ?
                WHERE extraction_run_id = ?
                """,
                (status, json.dumps(result or {}, ensure_ascii=False), error, utc_now(), extraction_run_id),
            )
            return self._row_dict(conn.execute("SELECT * FROM extraction_run WHERE extraction_run_id = ?", (extraction_run_id,)).fetchone())

    def upsert_concept(
        self,
        concept_type: str,
        payload: dict[str, Any],
        *,
        key_text: str = "",
        source_origin: str = "literature_extracted",
        validation_level: str = "extracted_unverified",
        verification_status: str = "extracted_unverified",
        public_scope: str = "project_private",
        extraction_run_id: str = "",
        llm_provider: str = "",
        llm_model: str = "",
        model_mode: str = "auto",
        prompt_version: str = "",
        schema_version: str = "",
        evidence: list[dict[str, Any]] | None = None,
        is_manual_edit: bool = False,
    ) -> dict[str, Any]:
        canonicalizer = ConceptCanonicalizer()
        evidence = evidence or []
        canonical_key = canonicalizer.canonical_key(concept_type, payload, key_text)
        concept_id = payload.get("concept_id") or canonicalizer.concept_id(concept_type, canonical_key, public_scope)
        label = canonical_label(concept_type, payload, key_text)
        summary = summarize_payload(payload)
        version_id = canonicalizer.version_id(
            concept_id,
            payload,
            extraction_run_id=extraction_run_id,
            model_mode=model_mode,
            llm_model=llm_model,
            is_manual_edit=is_manual_edit,
        )
        quality = canonicalizer.quality_score(payload, evidence_count=len(evidence), is_manual_edit=is_manual_edit)
        now = utc_now()
        with self._connect() as conn:
            ensure_v1_schema(conn)
            conn.execute(
                """
                INSERT INTO concept_card(
                    concept_id, concept_type, canonical_key, canonical_label, source_origin,
                    validation_level, verification_status, confidence_score, public_scope,
                    active_version_id, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(concept_type, canonical_key, public_scope) DO UPDATE SET
                    canonical_label=excluded.canonical_label,
                    source_origin=excluded.source_origin,
                    validation_level=excluded.validation_level,
                    verification_status=excluded.verification_status,
                    confidence_score=MAX(concept_card.confidence_score, excluded.confidence_score),
                    active_version_id=CASE
                        WHEN excluded.confidence_score >= concept_card.confidence_score THEN excluded.active_version_id
                        ELSE concept_card.active_version_id
                    END,
                    updated_at=excluded.updated_at
                """,
                (
                    concept_id,
                    concept_type,
                    canonical_key,
                    label,
                    source_origin,
                    validation_level,
                    verification_status,
                    float(payload.get("confidence_score", quality) or quality),
                    public_scope,
                    version_id,
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT concept_id FROM concept_card WHERE concept_type = ? AND canonical_key = ? AND public_scope = ?",
                (concept_type, canonical_key, public_scope),
            ).fetchone()
            concept_id = row["concept_id"]
            existing_active = conn.execute("SELECT active_version_id FROM concept_card WHERE concept_id = ?", (concept_id,)).fetchone()
            active_id = existing_active["active_version_id"] if existing_active else version_id
            conn.execute(
                """
                INSERT OR REPLACE INTO concept_version(
                    concept_version_id, concept_id, extraction_run_id, llm_provider, llm_model,
                    model_mode, prompt_version, schema_version, payload_json, summary_text,
                    text_hash, quality_score, is_active, is_manual_edit, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version_id,
                    concept_id,
                    extraction_run_id or None,
                    llm_provider,
                    llm_model,
                    model_mode,
                    prompt_version,
                    schema_version,
                    json.dumps(payload, ensure_ascii=False),
                    summary,
                    text_hash(summary or json.dumps(payload, ensure_ascii=False)),
                    quality,
                    1 if version_id == active_id else 0,
                    1 if is_manual_edit else 0,
                    now,
                ),
            )
            conn.execute("UPDATE concept_version SET is_active = CASE WHEN concept_version_id = ? THEN 1 ELSE 0 END WHERE concept_id = ?", (active_id or version_id, concept_id))
            conn.execute("UPDATE concept_card SET active_version_id = ? WHERE concept_id = ?", (active_id or version_id, concept_id))
            for link in evidence:
                self._insert_evidence_for_conn(conn, concept_id, version_id, link)
            ConceptIndexer(conn).index_concept(concept_id, concept_type, label, summary, payload)
            return self.get_concept(concept_id, conn=conn) or {}

    def _insert_evidence_for_conn(self, conn: sqlite3.Connection, concept_id: str, concept_version_id: str, link: dict[str, Any]) -> str:
        work_id = str(link.get("work_id") or "").strip()
        work_version_id = str(link.get("work_version_id") or "").strip()
        if work_id and not conn.execute("SELECT 1 FROM global_work WHERE work_id = ?", (work_id,)).fetchone():
            work_id = ""
            work_version_id = ""
        if work_version_id and not conn.execute("SELECT 1 FROM work_version WHERE work_version_id = ?", (work_version_id,)).fetchone():
            work_version_id = ""
        evidence_id = link.get("evidence_id") or stable_id(
            "EV",
            concept_id,
            concept_version_id,
            work_id,
            link.get("evidence_span") or link.get("evidence") or "",
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO evidence_link(
                evidence_id, concept_id, concept_version_id, work_id, work_version_id,
                evidence_type, evidence_span, source_url, confidence, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                evidence_id,
                concept_id,
                concept_version_id,
                work_id or None,
                work_version_id or None,
                link.get("evidence_type") or "source_span",
                str(link.get("evidence_span") or link.get("evidence") or ""),
                link.get("source_url") or "",
                float(link.get("confidence", 0.5) or 0.5),
                utc_now(),
            ),
        )
        return evidence_id

    def add_project_membership(self, project_id: str, record_type: str, record_id: str, *, source: str = "manual", display_order: int = 0, hidden: bool = False) -> dict[str, Any]:
        membership_id = stable_id("PM", project_id, record_type, record_id)
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO project_record_membership(
                    membership_id, project_id, record_type, record_id, source, display_order,
                    hidden, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, record_type, record_id) DO UPDATE SET
                    source=excluded.source,
                    display_order=excluded.display_order,
                    hidden=excluded.hidden,
                    updated_at=excluded.updated_at
                """,
                (membership_id, project_id, record_type, record_id, source, display_order, 1 if hidden else 0, now, now),
            )
            return self._row_dict(conn.execute("SELECT * FROM project_record_membership WHERE membership_id = ?", (membership_id,)).fetchone())

    def delete_project(self, project_id: str, *, delete_local_data: bool = False) -> dict[str, int]:
        if not project_id:
            return {}
        deleted: dict[str, int] = {"project_record_membership": 0}
        with self._connect() as conn:
            ensure_v1_schema(conn)
            memberships = [
                self._row_dict(row)
                for row in conn.execute(
                    "SELECT * FROM project_record_membership WHERE project_id = ?",
                    (project_id,),
                ).fetchall()
            ]
            conn.execute("DELETE FROM project_record_membership WHERE project_id = ?", (project_id,))
            deleted["project_record_membership"] = len(memberships)
            if not delete_local_data:
                return deleted

            remaining = {
                (row["record_type"], row["record_id"])
                for row in conn.execute("SELECT record_type, record_id FROM project_record_membership").fetchall()
            }
            candidate_concepts = {
                str(row.get("record_id") or "")
                for row in memberships
                if row.get("record_type") not in {"work"} and row.get("record_id")
            }
            candidate_works = {
                str(row.get("record_id") or "")
                for row in memberships
                if row.get("record_type") == "work" and row.get("record_id")
            }
            still_referenced_concepts = {record_id for record_type, record_id in remaining if record_type != "work"}
            for concept_id in sorted(candidate_concepts - still_referenced_concepts):
                if not conn.execute("SELECT 1 FROM concept_card WHERE concept_id = ?", (concept_id,)).fetchone():
                    continue
                conn.execute("UPDATE derivation_node SET concept_id = NULL WHERE concept_id = ?", (concept_id,))
                symbol_count = conn.execute("SELECT COUNT(*) FROM symbol_registry WHERE concept_id = ?", (concept_id,)).fetchone()[0]
                evidence_count = conn.execute("SELECT COUNT(*) FROM evidence_link WHERE concept_id = ?", (concept_id,)).fetchone()[0]
                version_count = conn.execute("SELECT COUNT(*) FROM concept_version WHERE concept_id = ?", (concept_id,)).fetchone()[0]
                conn.execute("DELETE FROM symbol_registry WHERE concept_id = ?", (concept_id,))
                conn.execute("DELETE FROM evidence_link WHERE concept_id = ?", (concept_id,))
                conn.execute("DELETE FROM concept_version WHERE concept_id = ?", (concept_id,))
                conn.execute("DELETE FROM concept_card WHERE concept_id = ?", (concept_id,))
                deleted["symbol_registry"] = deleted.get("symbol_registry", 0) + int(symbol_count)
                deleted["evidence_link"] = deleted.get("evidence_link", 0) + int(evidence_count)
                deleted["concept_version"] = deleted.get("concept_version", 0) + int(version_count)
                deleted["concept_card"] = deleted.get("concept_card", 0) + 1

            derivations = [
                row["derivation_id"]
                for row in conn.execute("SELECT derivation_id FROM derivation_run WHERE project_id = ?", (project_id,)).fetchall()
            ]
            for derivation_id in derivations:
                edge_count = conn.execute("SELECT COUNT(*) FROM derivation_edge WHERE derivation_id = ?", (derivation_id,)).fetchone()[0]
                node_count = conn.execute("SELECT COUNT(*) FROM derivation_node WHERE derivation_id = ?", (derivation_id,)).fetchone()[0]
                conn.execute("DELETE FROM derivation_edge WHERE derivation_id = ?", (derivation_id,))
                conn.execute("DELETE FROM derivation_node WHERE derivation_id = ?", (derivation_id,))
                conn.execute("DELETE FROM derivation_run WHERE derivation_id = ?", (derivation_id,))
                deleted["derivation_edge"] = deleted.get("derivation_edge", 0) + int(edge_count)
                deleted["derivation_node"] = deleted.get("derivation_node", 0) + int(node_count)
                deleted["derivation_run"] = deleted.get("derivation_run", 0) + 1

            still_referenced_works = {record_id for record_type, record_id in remaining if record_type == "work"}
            for work_id in sorted(candidate_works - still_referenced_works):
                if conn.execute("SELECT 1 FROM evidence_link WHERE work_id = ? LIMIT 1", (work_id,)).fetchone():
                    continue
                if not conn.execute("SELECT 1 FROM global_work WHERE work_id = ?", (work_id,)).fetchone():
                    continue
                extraction_count = conn.execute("SELECT COUNT(*) FROM extraction_run WHERE work_id = ?", (work_id,)).fetchone()[0]
                version_count = conn.execute("SELECT COUNT(*) FROM work_version WHERE work_id = ?", (work_id,)).fetchone()[0]
                conn.execute("DELETE FROM extraction_run WHERE work_id = ?", (work_id,))
                conn.execute("DELETE FROM work_version WHERE work_id = ?", (work_id,))
                conn.execute("DELETE FROM global_work WHERE work_id = ?", (work_id,))
                try:
                    conn.execute("DELETE FROM work_fts WHERE work_id = ?", (work_id,))
                except Exception:
                    pass
                deleted["extraction_run"] = deleted.get("extraction_run", 0) + int(extraction_count)
                deleted["work_version"] = deleted.get("work_version", 0) + int(version_count)
                deleted["global_work"] = deleted.get("global_work", 0) + 1
        return deleted

    def get_concept(self, concept_id: str, *, conn: sqlite3.Connection | None = None) -> dict[str, Any] | None:
        owns = conn is None
        conn = conn or self._connect()
        try:
            row = conn.execute("SELECT * FROM concept_card WHERE concept_id = ?", (concept_id,)).fetchone()
            if not row:
                return None
            concept = self._row_dict(row)
            versions = [dict(item) for item in conn.execute("SELECT * FROM concept_version WHERE concept_id = ? ORDER BY created_at DESC", (concept_id,)).fetchall()]
            for version in versions:
                version["payload"] = self._loads(version.pop("payload_json", "{}"))
            concept["versions"] = versions
            active = next((version for version in versions if version["concept_version_id"] == concept.get("active_version_id")), versions[0] if versions else {})
            concept["active_version"] = active
            concept["payload"] = active.get("payload", {})
            concept["evidence_links"] = [self._row_dict(item) for item in conn.execute("SELECT * FROM evidence_link WHERE concept_id = ?", (concept_id,)).fetchall()]
            symbol = conn.execute("SELECT * FROM symbol_registry WHERE concept_id = ? AND status = 'active' ORDER BY created_at DESC LIMIT 1", (concept_id,)).fetchone()
            if symbol:
                concept["symbol"] = self._row_dict(symbol)
            return concept
        finally:
            if owns:
                conn.close()

    def concepts(self, concept_type: str | None = None, *, project_id: str = "", limit: int = 200) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if concept_type:
                rows = conn.execute("SELECT concept_id FROM concept_card WHERE concept_type = ? ORDER BY updated_at DESC LIMIT ?", (concept_type, limit)).fetchall()
            else:
                rows = conn.execute("SELECT concept_id FROM concept_card ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
            concepts = [self.get_concept(row["concept_id"], conn=conn) for row in rows]
            concepts = [item for item in concepts if item]
            if project_id:
                memberships = {
                    (row["record_type"], row["record_id"])
                    for row in conn.execute(
                        "SELECT record_type, record_id FROM project_record_membership WHERE project_id = ? AND hidden = 0",
                        (project_id,),
                    ).fetchall()
                }
                concepts = [
                    item
                    for item in concepts
                    if ("concept", item["concept_id"]) in memberships or (item.get("concept_type", ""), item["concept_id"]) in memberships
                ]
            return concepts

    def sync_legacy_data(self, data: dict[str, Any], *, project_id: str = "default", source: str = "legacy_sync") -> dict[str, int]:
        counts = {"works": 0, "concepts": 0, "evidence_links": 0, "memberships": 0}
        work_id_map: dict[str, str] = {}
        for work in (data.get("source_works") or {}).values():
            saved = self.upsert_work(work)
            old_id = work.get("work_id") or saved["work_id"]
            work_id_map[old_id] = saved["work_id"]
            counts["works"] += 1
            self.add_project_membership(project_id, "work", saved["work_id"], source=source)
            counts["memberships"] += 1
        for bucket, concept_type in LEGACY_CONCEPT_BUCKETS.items():
            for item in (data.get(bucket) or {}).values():
                payload = dict(item)
                source_work_ids = payload.get("source_work_ids") or payload.get("source_works") or ([payload.get("work_id")] if payload.get("work_id") else [])
                evidence: list[dict[str, Any]] = []
                for legacy_work_id in source_work_ids:
                    global_work_id = work_id_map.get(str(legacy_work_id), str(legacy_work_id))
                    if global_work_id:
                        evidence.append(
                            {
                                "work_id": global_work_id,
                                "evidence_span": payload.get("evidence") or payload.get("abstract_signature") or payload.get("idea_text") or payload.get("text") or payload.get("message_text") or "",
                                "evidence_type": "legacy_payload",
                                "confidence": payload.get("confidence_score", 0.5),
                            }
                        )
                key_text = (
                    payload.get("canonical_key")
                    or payload.get("title")
                    or payload.get("name")
                    or payload.get("idea_text")
                    or payload.get("message_text")
                    or payload.get("text")
                    or ""
                )
                source_origin = "user_generated" if bucket in {"ideas", "my_ideas"} else "literature_extracted"
                concept = self.upsert_concept(
                    concept_type,
                    payload,
                    key_text=key_text,
                    source_origin=source_origin,
                    validation_level=payload.get("validation_level") or payload.get("feedback_status") or "extracted_unverified",
                    verification_status="speculative_unverified" if bucket in {"ideas", "my_ideas"} else "extracted_unverified",
                    evidence=evidence,
                    model_mode=payload.get("model_mode", "legacy"),
                    llm_model=payload.get("model_name", ""),
                )
                counts["concepts"] += 1
                counts["evidence_links"] += len(evidence)
                self.add_project_membership(project_id, concept_type, concept["concept_id"], source=source)
                counts["memberships"] += 1
        return counts

    def log_run_event(self, run_id: str, event_type: str, message: str = "", payload: dict[str, Any] | None = None) -> dict[str, Any]:
        event_id = stable_id("RE", run_id, event_type, message, utc_now())
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO run_event(event_id, run_id, event_type, message, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (event_id, run_id, event_type, message, json.dumps(payload or {}, ensure_ascii=False), utc_now()),
            )
            return self._row_dict(conn.execute("SELECT * FROM run_event WHERE event_id = ?", (event_id,)).fetchone())

    def _row_work(self, row: sqlite3.Row) -> dict[str, Any]:
        item = self._row_dict(row)
        item["source_urls"] = self._loads(item.pop("source_urls_json", "[]"))
        item["metadata"] = self._loads(item.pop("metadata_json", "{}"))
        return item

    def _row_dict(self, row: sqlite3.Row | None) -> dict[str, Any]:
        if row is None:
            return {}
        item = dict(row)
        for key in ("metadata_json", "result_json", "warnings_json", "detail_json", "payload_json"):
            if key in item:
                item[key.removesuffix("_json")] = self._loads(item.pop(key, "{}"))
        return item

    def _loads(self, text: str) -> Any:
        try:
            return json.loads(text or "{}")
        except Exception:
            return {}

    def _ordered_unique(self, values: list[Any]) -> list[str]:
        output: list[str] = []
        seen: set[str] = set()
        for value in values:
            text = str(value or "").strip()
            if text and text not in seen:
                seen.add(text)
                output.append(text)
        return output
