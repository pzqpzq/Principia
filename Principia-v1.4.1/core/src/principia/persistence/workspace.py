from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .._sqlite import connect_sqlite
from ..domain import (
    CandidatePrinciple,
    EvidenceClaimAtom,
    JobRecord,
    PrincipleCapsule,
    PublicationChangeset,
    QualityEvaluation,
    ScenarioEvent,
    ScenarioRecord,
    ScientificArgument,
    concise_principle_title,
)
from ..domain.hashing import canonical_sha256
from ..models import utc_now

_PRIVATE_PATH = re.compile(r"(?:(?:[A-Za-z]:\\)|/(?:Users|home|private|var|tmp)/)[^\s\"']+")
_SECRET_VALUE = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|password|passwd|pwd|bearer)\b\s*[:=]\s*([^\s,;]+)"
)


def _redact_diagnostic(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _redact_diagnostic(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_diagnostic(item) for item in value]
    if isinstance(value, str):
        redacted = _PRIVATE_PATH.sub("[PRIVATE_PATH]", value)
        return _SECRET_VALUE.sub(lambda match: f"{match.group(1)}: [REDACTED]", redacted)
    return value


def _public_reference_url(work: dict[str, Any]) -> str:
    url = str(work.get("url") or "").strip()
    if url.startswith("https://"):
        return url
    doi = str(work.get("doi") or "").strip()
    if doi:
        return f"https://doi.org/{doi}"
    arxiv_id = str(work.get("arxiv_id") or "").strip()
    if arxiv_id:
        return f"https://arxiv.org/abs/{arxiv_id}"
    pmid = str(work.get("pmid") or "").strip()
    if pmid:
        return f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    return ""


def _encode_cursor(updated_at: str, identifier: str) -> str:
    raw = json.dumps([updated_at, identifier], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[str, str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(padded).decode())
        if (
            not isinstance(value, list)
            or len(value) != 2
            or not all(isinstance(item, str) for item in value)
        ):
            raise ValueError
        return value[0], value[1]
    except Exception as exc:
        raise ValueError("invalid pagination cursor") from exc


class V14WorkspaceRepository:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        conn = connect_sqlite(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def list_candidates(self, *, limit: int = 100) -> list[CandidatePrinciple]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM local_candidates ORDER BY updated_at DESC, candidate_id LIMIT ?",
                (max(1, min(int(limit), 100)),),
            ).fetchall()
        return [CandidatePrinciple.model_validate_json(row[0]) for row in rows]

    def save_candidate(
        self,
        candidate: CandidatePrinciple,
        *,
        source_kind: str = "discovery",
        discovery_job_id: str = "",
        dataset_id: str = "",
        goal_id: str = "",
        source_id: str = "",
        eligibility_status: str = "eligible",
        candidate_fingerprint: str = "",
        quarantine_reason: str = "",
        scientific_contract_version: str = "",
        quality_gate_version: str = "",
        quality_state: str = "legacy_needs_revalidation",
        extraction_mode: str = "focus_guided",
        context_relevance: str = "not_evaluated",
    ) -> None:
        payload = candidate.model_dump(mode="json")
        digest = canonical_sha256(payload)
        fingerprint = candidate_fingerprint or canonical_sha256(
            {
                "claim": " ".join(candidate.claim.casefold().split()),
                "kind": candidate.kind.value,
                "scope": " ".join(candidate.scope.statement.casefold().split()),
            }
        )
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO local_candidates(
                    candidate_id, area, title, claim, assessment_status, source_kind,
                    payload_json, content_digest, created_at, updated_at,
                    discovery_job_id, dataset_id, eligibility_status,
                    candidate_fingerprint, source_count, relation_count, quarantine_reason,
                    goal_id, source_id, scientific_contract_version,
                    quality_gate_version, quality_state, extraction_mode,
                    context_relevance
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(candidate_id) DO UPDATE SET
                    title=excluded.title, claim=excluded.claim,
                    assessment_status=excluded.assessment_status,
                    payload_json=excluded.payload_json, content_digest=excluded.content_digest,
                    discovery_job_id=excluded.discovery_job_id,
                    dataset_id=excluded.dataset_id,
                    eligibility_status=excluded.eligibility_status,
                    candidate_fingerprint=excluded.candidate_fingerprint,
                    source_count=excluded.source_count,
                    relation_count=excluded.relation_count,
                    quarantine_reason=excluded.quarantine_reason,
                    goal_id=excluded.goal_id, source_id=excluded.source_id,
                    scientific_contract_version=excluded.scientific_contract_version,
                    quality_gate_version=excluded.quality_gate_version,
                    quality_state=excluded.quality_state,
                    extraction_mode=excluded.extraction_mode,
                    context_relevance=excluded.context_relevance,
                    updated_at=excluded.updated_at
                """,
                (
                    candidate.candidate_id,
                    candidate.area,
                    candidate.title,
                    candidate.claim,
                    candidate.assessment_status,
                    source_kind,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    digest,
                    candidate.created_at,
                    candidate.updated_at,
                    discovery_job_id,
                    dataset_id,
                    eligibility_status,
                    fingerprint,
                    len(candidate.source_references),
                    len(candidate.relations),
                    quarantine_reason,
                    goal_id,
                    source_id,
                    scientific_contract_version,
                    quality_gate_version,
                    quality_state,
                    extraction_mode,
                    context_relevance,
                ),
            )
            conn.execute(
                "DELETE FROM local_candidate_relations WHERE source_candidate_id=?",
                (candidate.candidate_id,),
            )
            for index, relation in enumerate(candidate.relations):
                conn.execute(
                    """
                    INSERT INTO local_candidate_relations(
                        source_candidate_id, relation_index, target_principle_id,
                        target_area, minimum_package_version, relation_type,
                        provenance, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, 'model_proposed', ?)
                    """,
                    (
                        candidate.candidate_id,
                        index,
                        relation.target_principle_id,
                        relation.target_area,
                        relation.minimum_package_version,
                        relation.relation_type.value,
                        relation.model_dump_json(),
                    ),
                )
            if goal_id and context_relevance != "outside_focus":
                conn.execute(
                    """
                    INSERT OR IGNORE INTO candidate_goal_memberships(
                        candidate_id, goal_id, created_at
                    ) VALUES (?, ?, ?)
                    """,
                    (candidate.candidate_id, goal_id, utc_now()),
                )
            if source_id:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO candidate_source_memberships(
                        candidate_id, source_id, created_at
                    ) VALUES (?, ?, ?)
                    """,
                    (candidate.candidate_id, source_id, utc_now()),
                )
            conn.execute(
                "DELETE FROM local_principle_fts WHERE principle_id=?", (candidate.candidate_id,)
            )
            if eligibility_status == "eligible" and quality_state == "eligible":
                conn.execute(
                    "INSERT INTO local_principle_fts(principle_id, version, title, claim, area, tags) "
                    "VALUES (?, 0, ?, ?, ?, '')",
                    (candidate.candidate_id, candidate.title, candidate.claim, candidate.area),
                )

    def browse_candidates(
        self,
        *,
        limit: int = 50,
        cursor: str = "",
        query: str = "",
        area: str = "",
        assessment: str = "",
        eligibility: str = "",
        discovery_id: str = "",
        dataset_id: str = "",
        goal_id: str = "",
        source_id: str = "",
        quality_state: str = "",
    ) -> dict[str, Any]:
        resolved_limit = max(1, min(int(limit), 100))
        clauses: list[str] = []
        values: list[Any] = []
        for column, value in (
            ("area", area),
            ("assessment_status", assessment),
            ("eligibility_status", eligibility),
            ("discovery_job_id", discovery_id),
            ("dataset_id", dataset_id),
            ("quality_state", quality_state),
        ):
            if value:
                clauses.append(f"{column}=?")
                values.append(value)
        if goal_id:
            clauses.append(
                "EXISTS (SELECT 1 FROM candidate_goal_memberships gm "
                "WHERE gm.candidate_id=local_candidates.candidate_id AND gm.goal_id=?)"
            )
            values.append(goal_id)
        if source_id:
            clauses.append(
                "EXISTS (SELECT 1 FROM candidate_source_memberships sm "
                "WHERE sm.candidate_id=local_candidates.candidate_id AND sm.source_id=?)"
            )
            values.append(source_id)
        if query.strip():
            clauses.append("(title LIKE ? ESCAPE '\\' OR claim LIKE ? ESCAPE '\\')")
            escaped = query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            values.extend([f"%{escaped}%", f"%{escaped}%"])
        count_where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as conn:
            total = int(
                conn.execute(
                    f"SELECT COUNT(*) FROM local_candidates{count_where}", tuple(values)
                ).fetchone()[0]
            )
            page_clauses = list(clauses)
            page_values = list(values)
            if cursor:
                cursor_updated, cursor_id = _decode_cursor(cursor)
                page_clauses.append("(updated_at < ? OR (updated_at = ? AND candidate_id > ?))")
                page_values.extend([cursor_updated, cursor_updated, cursor_id])
            page_where = f" WHERE {' AND '.join(page_clauses)}" if page_clauses else ""
            rows = conn.execute(
                f"""
                SELECT candidate_id, area, title, claim, assessment_status,
                       eligibility_status, source_kind, discovery_job_id, dataset_id,
                       goal_id, source_id, scientific_contract_version,
                       quality_gate_version, quality_state, source_count,
                       relation_count, quarantine_reason, updated_at,
                       COALESCE((SELECT ar.claim_class
                                 FROM candidate_argument_revisions ar
                                 WHERE ar.candidate_id=local_candidates.candidate_id
                                 ORDER BY ar.revision DESC LIMIT 1), '') AS claim_class,
                       COALESCE((SELECT ar.generalization_level
                                 FROM candidate_argument_revisions ar
                                 WHERE ar.candidate_id=local_candidates.candidate_id
                                 ORDER BY ar.revision DESC LIMIT 1), '') AS generalization_level,
                       COALESCE((SELECT GROUP_CONCAT(gm.goal_id)
                                 FROM candidate_goal_memberships gm
                                 WHERE gm.candidate_id=local_candidates.candidate_id), '')
                                 AS goal_ids,
                       COALESCE((SELECT GROUP_CONCAT(sm.source_id)
                                 FROM candidate_source_memberships sm
                                 WHERE sm.candidate_id=local_candidates.candidate_id), '')
                                 AS source_ids
                FROM local_candidates{page_where}
                ORDER BY updated_at DESC, candidate_id ASC LIMIT ?
                """,
                (*page_values, resolved_limit + 1),
            ).fetchall()
        has_more = len(rows) > resolved_limit
        rows = rows[:resolved_limit]
        items = [dict(row) for row in rows]
        next_cursor = (
            _encode_cursor(str(rows[-1]["updated_at"]), str(rows[-1]["candidate_id"]))
            if has_more and rows
            else None
        )
        return {"items": items, "next_cursor": next_cursor, "total": total}

    def save_capsule(self, capsule: PrincipleCapsule) -> None:
        payload = capsule.model_dump(mode="json")
        digest = capsule.content_digest or canonical_sha256(
            {key: value for key, value in payload.items() if key != "content_digest"}
        )
        payload["content_digest"] = digest
        with self.connect() as conn:
            exists = conn.execute(
                "SELECT 1 FROM local_principles WHERE principle_id=? AND version=?",
                (capsule.principle_id, capsule.version),
            ).fetchone()
            if exists:
                raise ValueError("Principle revisions are immutable")
            conn.execute(
                """
                INSERT INTO local_principles(
                    principle_id, version, area, status, title, claim, payload_json,
                    content_digest, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    capsule.principle_id,
                    capsule.version,
                    capsule.area,
                    capsule.status,
                    capsule.title,
                    capsule.claim,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    digest,
                    capsule.created_at,
                    capsule.updated_at,
                ),
            )
            for index, relation in enumerate(capsule.relations):
                relation_payload = relation.model_dump(mode="json")
                conn.execute(
                    """
                    INSERT INTO local_relations(
                        source_principle_id, source_version, relation_index,
                        target_principle_id, target_area, minimum_package_version,
                        relation_type, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        capsule.principle_id,
                        capsule.version,
                        index,
                        relation.target_principle_id,
                        relation.target_area,
                        relation.minimum_package_version,
                        relation.relation_type.value,
                        json.dumps(relation_payload, ensure_ascii=False, sort_keys=True),
                    ),
                )
            for index, trace in enumerate(capsule.generation_trace):
                conn.execute(
                    "INSERT INTO local_generation_trace VALUES (?, ?, ?, ?, ?)",
                    (
                        capsule.principle_id,
                        capsule.version,
                        index,
                        trace.event_id,
                        trace.model_dump_json(),
                    ),
                )
            conn.execute(
                "DELETE FROM local_principle_fts WHERE principle_id=?", (capsule.principle_id,)
            )
            conn.execute(
                "INSERT INTO local_principle_fts(principle_id, version, title, claim, area, tags) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    capsule.principle_id,
                    capsule.version,
                    capsule.title,
                    capsule.claim,
                    capsule.area,
                    " ".join(capsule.tags),
                ),
            )

    def search_local(
        self,
        query: str,
        *,
        limit: int = 50,
        area: str = "",
        goal_id: str = "",
        source_id: str = "",
    ) -> list[dict[str, Any]]:
        terms = re.findall(r"[\w-]+", query, flags=re.UNICODE)
        if not terms:
            return []
        fts_query = " AND ".join(f'"{term.replace(chr(34), "")}"' for term in terms[:20])
        resolved_limit = max(1, min(int(limit), 100))
        filters: list[str] = []
        values: list[Any] = [fts_query]
        if area:
            filters.append("f.area=?")
            values.append(area)
        if goal_id:
            filters.append(
                "EXISTS (SELECT 1 FROM candidate_goal_memberships gm "
                "WHERE gm.candidate_id=f.principle_id AND gm.goal_id=?)"
            )
            values.append(goal_id)
        if source_id:
            filters.append(
                "EXISTS (SELECT 1 FROM candidate_source_memberships sm "
                "WHERE sm.candidate_id=f.principle_id AND sm.source_id=?)"
            )
            values.append(source_id)
        filter_sql = "" if not filters else " AND " + " AND ".join(filters)
        values.append(resolved_limit)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT f.principle_id, f.version, f.title, f.claim, f.area, f.rank
                FROM local_principle_fts AS f
                LEFT JOIN local_candidates AS c ON c.candidate_id=f.principle_id
                WHERE local_principle_fts MATCH ?
                  AND (f.version != 0 OR (
                      c.eligibility_status='eligible' AND c.quality_state='eligible'
                  ))
                  {filter_sql}
                ORDER BY rank LIMIT ?
                """,
                values,
            ).fetchall()
        return [dict(row) for row in rows]

    def register_source(
        self,
        source_id: str,
        root: Path,
        portable_uri: str,
        display_name: str,
        display_location: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        canonical_root = str(root.resolve())
        display_location = display_location or display_name
        payload = {
            "source_id": source_id,
            "portable_uri": portable_uri,
            "display_name": display_name,
            "display_location": display_location,
            "status": "ready",
            "created_at": now,
            "updated_at": now,
        }
        existing_id = ""
        with self.connect() as conn:
            existing = conn.execute(
                """
                SELECT s.source_id
                FROM local_sources_v14 s
                WHERE s.absolute_root=? AND s.status!='removed'
                ORDER BY (SELECT COUNT(*) FROM local_source_documents d
                          WHERE d.source_id=s.source_id) DESC,
                         CASE s.source_kind WHEN 'managed' THEN 0 ELSE 1 END,
                         s.updated_at DESC, s.source_id
                LIMIT 1
                """,
                (canonical_root,),
            ).fetchone()
            if existing is not None:
                existing_id = str(existing["source_id"])
                conn.execute(
                    "UPDATE local_sources_v14 SET status='ready', updated_at=? WHERE source_id=?",
                    (now, existing_id),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO local_sources_v14(
                        source_id, portable_uri, absolute_root, display_name, status,
                        payload_json, created_at, updated_at, source_kind, revision,
                        display_location
                    ) VALUES (?, ?, ?, ?, 'ready', ?, ?, ?, 'connected', 1, ?)
                    ON CONFLICT(source_id) DO UPDATE SET absolute_root=excluded.absolute_root,
                        display_name=excluded.display_name, status='ready',
                        display_location=excluded.display_location,
                        payload_json=excluded.payload_json, updated_at=excluded.updated_at,
                        revision=local_sources_v14.revision+1
                    """,
                    (
                        source_id,
                        portable_uri,
                        canonical_root,
                        display_name,
                        json.dumps(payload, ensure_ascii=False, sort_keys=True),
                        now,
                        now,
                        display_location,
                    ),
                )
        if existing_id:
            return self.source(existing_id) or payload
        return payload

    def reconcile_duplicate_source_roots(self) -> dict[str, int]:
        """Hide empty aliases for a folder that already has an authoritative source.

        Older UI flows could connect a managed folder a second time and create a
        path-derived source ID.  We only collapse an alias when it has no indexed
        documents, memberships, datasets, or Goals; therefore no scientific or
        user data is discarded.  Non-empty duplicates stay visible for explicit
        reconciliation instead of being merged speculatively.
        """

        hidden = 0
        with self.connect() as conn:
            roots = conn.execute(
                """
                SELECT absolute_root FROM local_sources_v14
                WHERE status!='removed'
                GROUP BY absolute_root HAVING COUNT(*) > 1
                """
            ).fetchall()
            for root_row in roots:
                rows = conn.execute(
                    """
                    SELECT s.source_id, s.source_kind,
                           (SELECT COUNT(*) FROM local_source_documents d
                            WHERE d.source_id=s.source_id) AS document_count,
                           (SELECT COUNT(*) FROM candidate_source_memberships m
                            WHERE m.source_id=s.source_id) AS membership_count,
                           (SELECT COUNT(*) FROM research_datasets ds
                            WHERE ds.source_id=s.source_id) AS dataset_count,
                           (SELECT COUNT(*) FROM local_research_goals g
                            WHERE g.source_id=s.source_id) AS goal_count
                    FROM local_sources_v14 s
                    WHERE s.absolute_root=? AND s.status!='removed'
                    ORDER BY document_count DESC, membership_count DESC,
                             CASE s.source_kind WHEN 'managed' THEN 0 ELSE 1 END,
                             s.updated_at DESC, s.source_id
                    """,
                    (root_row["absolute_root"],),
                ).fetchall()
                if not rows:
                    continue
                canonical_id = str(rows[0]["source_id"])
                for duplicate in rows[1:]:
                    if any(
                        int(duplicate[column] or 0)
                        for column in (
                            "document_count",
                            "membership_count",
                            "dataset_count",
                            "goal_count",
                        )
                    ):
                        continue
                    duplicate_id = str(duplicate["source_id"])
                    payload_row = conn.execute(
                        "SELECT payload_json FROM local_sources_v14 WHERE source_id=?",
                        (duplicate_id,),
                    ).fetchone()
                    payload = json.loads(str(payload_row["payload_json"]))
                    payload.update(
                        {
                            "status": "removed",
                            "canonical_source_id": canonical_id,
                            "updated_at": utc_now(),
                        }
                    )
                    conn.execute(
                        "UPDATE local_sources_v14 SET status='removed', payload_json=?, "
                        "updated_at=? WHERE source_id=?",
                        (
                            json.dumps(payload, ensure_ascii=False, sort_keys=True),
                            payload["updated_at"],
                            duplicate_id,
                        ),
                    )
                    hidden += 1
        return {"hidden_empty_aliases": hidden}

    def list_sources(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT source_id FROM local_sources_v14 "
                "WHERE status!='removed' ORDER BY updated_at DESC, source_id"
            ).fetchall()
        return [item for row in rows if (item := self.source(str(row[0]))) is not None]

    def source_root(self, source_id: str) -> Path | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT absolute_root FROM local_sources_v14 WHERE source_id=?", (source_id,)
            ).fetchone()
        return Path(row[0]) if row else None

    def link_candidates_to_source_by_work(self, source_id: str) -> int:
        """Reconnect durable Principles to a folder using canonical Work identity.

        This makes a paper-free imported Principle library useful immediately
        after the user reconnects the corresponding raw source directory.
        """

        now = utc_now()
        with self.connect() as conn:
            before = conn.total_changes
            conn.execute(
                """
                INSERT OR IGNORE INTO candidate_source_memberships(
                    candidate_id, source_id, created_at
                )
                SELECT DISTINCT e.candidate_id, ?, ?
                FROM candidate_work_evidence e
                JOIN local_source_documents d ON d.work_id=e.work_id
                WHERE d.source_id=?
                """,
                (source_id, now, source_id),
            )
            linked = conn.total_changes - before
            conn.execute(
                """
                UPDATE local_source_documents
                SET principle_count=(
                    SELECT COUNT(DISTINCT e.candidate_id)
                    FROM candidate_work_evidence e
                    WHERE e.work_id=local_source_documents.work_id
                ), updated_at=?
                WHERE source_id=?
                """,
                (now, source_id),
            )
        return linked

    def source(self, source_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT source_id, portable_uri, display_name, status, source_kind,
                       revision, display_location, created_at, updated_at, payload_json
                FROM local_sources_v14 WHERE source_id=?
                """,
                (source_id,),
            ).fetchone()
            if row is None:
                return None
            counts = conn.execute(
                """
                SELECT COUNT(*) AS document_count,
                       COALESCE(SUM(extraction_eligible), 0) AS extractable_count,
                       COALESCE(SUM(principle_count), 0) AS principle_count,
                       COALESCE(SUM(CASE WHEN a.content_kind='full_text'
                                                  OR d.portable_relative_uri LIKE '%/paper.pdf'
                                                  OR d.portable_relative_uri LIKE '%/full-text.txt'
                                             THEN 1 ELSE 0 END), 0)
                           AS full_text_count,
                       COALESCE(SUM(CASE WHEN a.content_kind='abstract'
                                                  OR d.portable_relative_uri LIKE '%/abstract.txt'
                                             THEN 1 ELSE 0 END), 0)
                           AS abstract_only_count,
                       COALESCE(SUM(CASE WHEN a.mime_type='application/pdf'
                                                  OR d.portable_relative_uri LIKE '%.pdf'
                                             THEN 1 ELSE 0 END), 0)
                           AS pdf_count,
                       COALESCE(SUM(CASE WHEN (a.content_kind='full_text'
                                                   AND a.mime_type!='application/pdf')
                                                  OR d.portable_relative_uri LIKE '%/full-text.txt'
                                         THEN 1 ELSE 0 END), 0)
                           AS text_full_text_count
                FROM local_source_documents d
                LEFT JOIN scholarly_acquisitions a ON a.acquisition_id=d.acquisition_id
                WHERE d.source_id=?
                """,
                (source_id,),
            ).fetchone()
        source_payload = json.loads(str(row["payload_json"]))
        source_row = dict(row)
        source_row.pop("payload_json", None)
        return {
            **source_row,
            "canonical_source_id": str(source_payload.get("canonical_source_id") or ""),
            "document_count": int(counts["document_count"]),
            "full_text_count": int(counts["full_text_count"]),
            "abstract_only_count": int(counts["abstract_only_count"]),
            "pdf_count": int(counts["pdf_count"]),
            "text_full_text_count": int(counts["text_full_text_count"]),
            "extractable_count": int(counts["extractable_count"]),
            "principle_count": int(counts["principle_count"]),
        }

    def save_source_document(self, payload: dict[str, Any]) -> None:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO local_source_documents(
                    document_id, source_id, work_id, acquisition_id,
                    portable_relative_uri, content_sha256, parse_status,
                    extraction_eligible, principle_count, last_indexed_revision,
                    payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    acquisition_id=excluded.acquisition_id,
                    portable_relative_uri=excluded.portable_relative_uri,
                    content_sha256=excluded.content_sha256,
                    parse_status=excluded.parse_status,
                    extraction_eligible=excluded.extraction_eligible,
                    principle_count=excluded.principle_count,
                    last_indexed_revision=excluded.last_indexed_revision,
                    payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at
                """,
                (
                    payload["document_id"],
                    payload["source_id"],
                    payload["work_id"],
                    payload.get("acquisition_id") or None,
                    payload["portable_relative_uri"],
                    payload.get("content_sha256", ""),
                    payload.get("parse_status", "pending"),
                    1 if payload.get("extraction_eligible") else 0,
                    int(payload.get("principle_count") or 0),
                    int(payload.get("last_indexed_revision") or 1),
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    payload.get("created_at", now),
                    now,
                ),
            )

    def source_documents(
        self,
        source_id: str,
        *,
        limit: int = 50,
        cursor: str = "",
        query: str = "",
        extractable: bool | None = None,
    ) -> dict[str, Any]:
        resolved_limit = max(1, min(int(limit), 100))
        clauses = ["d.source_id=?"]
        values: list[Any] = [source_id]
        if extractable is not None:
            clauses.append("d.extraction_eligible=?")
            values.append(1 if extractable else 0)
        if query.strip():
            escaped = query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            clauses.append(
                "(json_extract(w.payload_json, '$.title') LIKE ? ESCAPE '\\' "
                "OR d.portable_relative_uri LIKE ? ESCAPE '\\')"
            )
            values.extend([f"%{escaped}%", f"%{escaped}%"])
        where = " AND ".join(clauses)
        with self.connect() as conn:
            total = int(
                conn.execute(
                    f"SELECT COUNT(*) FROM local_source_documents d JOIN works w ON w.id=d.work_id WHERE {where}",
                    values,
                ).fetchone()[0]
            )
            page_clauses = list(clauses)
            page_values = list(values)
            if cursor:
                updated, identifier = _decode_cursor(cursor)
                page_clauses.append("(d.updated_at < ? OR (d.updated_at=? AND d.document_id>?))")
                page_values.extend([updated, updated, identifier])
            rows = conn.execute(
                f"""
                SELECT d.document_id, d.source_id, d.work_id,
                       d.portable_relative_uri, d.content_sha256, d.parse_status,
                       d.extraction_eligible, d.principle_count,
                       d.last_indexed_revision, d.updated_at,
                       COALESCE(a.byte_size,
                                json_extract(d.payload_json, '$.content_byte_size'),
                                json_extract(d.payload_json, '$.byte_size'), 0)
                           AS content_byte_size,
                       (SELECT COUNT(*)
                        FROM v14_job_units xu
                        JOIN v14_jobs xj ON xj.job_id=xu.job_id
                        WHERE xj.kind='local_extraction'
                          AND json_extract(xu.checkpoint_json, '$.document_id')=d.document_id
                       ) AS extraction_attempt_count,
                       CASE
                         WHEN EXISTS(
                           SELECT 1 FROM v14_job_units xu
                           JOIN v14_jobs xj ON xj.job_id=xu.job_id
                           WHERE xj.kind='local_extraction' AND xu.state='succeeded'
                             AND json_extract(xu.checkpoint_json, '$.document_id')=d.document_id
                         ) THEN 'processed'
                         WHEN EXISTS(
                           SELECT 1 FROM v14_job_units xu
                           JOIN v14_jobs xj ON xj.job_id=xu.job_id
                           WHERE xj.kind='local_extraction' AND xu.state IN ('queued','running')
                             AND json_extract(xu.checkpoint_json, '$.document_id')=d.document_id
                         ) THEN 'processing'
                         WHEN EXISTS(
                           SELECT 1 FROM v14_job_units xu
                           JOIN v14_jobs xj ON xj.job_id=xu.job_id
                           WHERE xj.kind='local_extraction' AND xu.state='failed'
                             AND json_extract(xu.checkpoint_json, '$.document_id')=d.document_id
                         ) THEN 'failed'
                         ELSE 'not_started'
                       END AS extraction_status,
                       w.payload_json AS work_json
                FROM local_source_documents d JOIN works w ON w.id=d.work_id
                LEFT JOIN scholarly_acquisitions a ON a.acquisition_id=d.acquisition_id
                WHERE {" AND ".join(page_clauses)}
                ORDER BY d.updated_at DESC, d.document_id LIMIT ?
                """,
                (*page_values, resolved_limit + 1),
            ).fetchall()
        has_more = len(rows) > resolved_limit
        rows = rows[:resolved_limit]
        items = []
        for row in rows:
            work = json.loads(row["work_json"])
            relative_uri = str(row["portable_relative_uri"] or "")
            content_representation = (
                "pdf"
                if relative_uri.casefold().endswith(".pdf")
                else "full_text"
                if relative_uri.casefold().endswith("/full-text.txt")
                else "abstract"
                if relative_uri.casefold().endswith("/abstract.txt")
                else "other"
            )
            items.append(
                {
                    key: row[key]
                    for key in (
                        "document_id",
                        "source_id",
                        "work_id",
                        "portable_relative_uri",
                        "content_sha256",
                        "content_byte_size",
                        "parse_status",
                        "extraction_eligible",
                        "extraction_status",
                        "extraction_attempt_count",
                        "principle_count",
                        "last_indexed_revision",
                        "updated_at",
                    )
                }
                | {
                    "title": work.get("title") or row["work_id"],
                    "year": work.get("year"),
                    "authors": work.get("authors") or [],
                    "abstract_available": bool(str(work.get("abstract") or "").strip()),
                    "content_representation": content_representation,
                }
            )
        return {
            "items": items,
            "total": total,
            "next_cursor": (
                _encode_cursor(str(rows[-1]["updated_at"]), str(rows[-1]["document_id"]))
                if has_more and rows
                else None
            ),
        }

    def source_work_ids(self, source_id: str) -> set[str]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT work_id FROM local_source_documents WHERE source_id=?",
                (source_id,),
            ).fetchall()
        return {str(row["work_id"]) for row in rows}

    def extraction_documents(self, source_id: str, document_ids: list[str]) -> list[dict[str, Any]]:
        identities = list(dict.fromkeys(document_ids))
        if not identities:
            return []
        if len(identities) > 500:
            raise ValueError("an extraction may select at most 500 documents")
        output: list[dict[str, Any]] = []
        with self.connect() as conn:
            for start in range(0, len(identities), 300):
                chunk = identities[start : start + 300]
                placeholders = ",".join("?" for _ in chunk)
                rows = conn.execute(
                    f"""
                    SELECT d.*, w.payload_json AS work_json
                    FROM local_source_documents d JOIN works w ON w.id=d.work_id
                    WHERE d.source_id=? AND d.document_id IN ({placeholders})
                    """,
                    (source_id, *chunk),
                ).fetchall()
                for row in rows:
                    segments = conn.execute(
                        """
                        SELECT segment_id, segment_key, section, page_start, page_end,
                               text, text_sha256
                        FROM scholarly_segments WHERE acquisition_id=? ORDER BY ordinal
                        """,
                        (row["acquisition_id"],),
                    ).fetchall()
                    if not segments:
                        # A paper can be imported through more than one Local
                        # folder.  Strong bibliographic deduplication may map
                        # the new folder row to a canonical Work ID while the
                        # already parsed source asset keeps its original local
                        # Work ID.  The immutable byte digest bridges those
                        # identities and avoids presenting an indexed paper as
                        # inexplicably non-extractable.
                        legacy = conn.execute(
                            """
                            SELECT normalized_text, text_sha256 FROM source_assets
                            WHERE work_id=? OR byte_sha256=?
                            ORDER BY CASE WHEN work_id=? THEN 0 ELSE 1 END,
                                     updated_at DESC
                            LIMIT 1
                            """,
                            (row["work_id"], row["content_sha256"], row["work_id"]),
                        ).fetchone()
                        if legacy and str(legacy["normalized_text"] or "").strip():
                            segments = [
                                {
                                    "segment_id": f"local:{row['document_id']}",
                                    "segment_key": f"local:{row['document_id']}:0",
                                    "section": "local_document",
                                    "page_start": None,
                                    "page_end": None,
                                    "text": str(legacy["normalized_text"]),
                                    "text_sha256": str(legacy["text_sha256"]),
                                }
                            ]
                    output.append(
                        {
                            "document_id": row["document_id"],
                            "source_id": row["source_id"],
                            "work_id": row["work_id"],
                            "acquisition_id": row["acquisition_id"],
                            "extraction_eligible": bool(row["extraction_eligible"]),
                            "last_indexed_revision": row["last_indexed_revision"],
                            "work": json.loads(row["work_json"]),
                            "segments": [dict(item) for item in segments],
                        }
                    )
        by_id = {str(item["document_id"]): item for item in output}
        missing = [identifier for identifier in identities if identifier not in by_id]
        if missing:
            raise ValueError("selection contains documents outside the chosen Local source")
        return [by_id[identifier] for identifier in identities]

    def library_summary(self) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM local_research_goals WHERE status!='archived')
                        AS research_goal_count,
                    (SELECT COUNT(*) FROM local_sources_v14 WHERE status!='removed')
                        AS source_count,
                    (SELECT COUNT(*) FROM local_source_documents) AS document_count,
                    (SELECT COUNT(*) FROM local_candidates
                     WHERE eligibility_status='eligible' AND quality_state='eligible')
                        AS principle_count,
                    (SELECT COUNT(*) FROM local_candidates
                     WHERE quality_state='legacy_needs_revalidation')
                        AS needs_revalidation_count,
                    (SELECT COUNT(*) FROM local_candidates
                     WHERE quality_state IN ('quarantined', 'not_a_principle'))
                        AS quarantined_count,
                    (SELECT COUNT(*) FROM candidate_work_evidence e
                     JOIN local_candidates c ON c.candidate_id=e.candidate_id
                     WHERE c.quality_state='eligible') AS evidence_link_count
                """
            ).fetchone()
            area_count = int(
                conn.execute(
                    """
                    WITH effective_areas AS (
                        SELECT c.area
                        FROM local_candidates c
                        WHERE c.quality_state='eligible'
                          AND c.eligibility_status='eligible'
                          AND c.area NOT IN ('', 'uncategorized')
                        UNION
                        SELECT assignment.area
                        FROM candidate_area_assignments assignment
                        JOIN local_candidates c
                          ON c.candidate_id=assignment.candidate_id
                        WHERE c.quality_state='eligible'
                          AND c.eligibility_status='eligible'
                          AND assignment.state IN ('confirmed', 'suggested')
                          AND assignment.area NOT IN ('', 'uncategorized')
                          AND assignment.revision=(
                              SELECT MAX(latest.revision)
                              FROM candidate_area_assignments latest
                              WHERE latest.candidate_id=assignment.candidate_id
                                AND latest.area=assignment.area
                          )
                    )
                    SELECT COUNT(*) FROM effective_areas
                    """
                ).fetchone()[0]
            )
        return {
            **dict(row),
            "area_count": area_count,
            "label": "Local · Private Workspace",
            "principle_contract": "scientific-principle-v2",
        }

    def repair_candidate_goal_memberships(self) -> dict[str, int]:
        """Recover explicit extraction-Goal memberships without inventing one.

        Metadata searches are not Research Goals.  Early selection updates
        could nevertheless create a search-backed Goal before extraction then
        create a second, explicit extraction Goal with the same text.  Prefer
        the Candidate's persisted ``goal_id``, archive only that duplicate
        search projection, and retain every search/dataset record for audit.
        """

        now = utc_now()
        with self.connect() as conn:
            before = int(
                conn.execute(
                    "SELECT COUNT(*) FROM local_candidates c WHERE NOT EXISTS ("
                    "SELECT 1 FROM candidate_goal_memberships m "
                    "WHERE m.candidate_id=c.candidate_id)"
                ).fetchone()[0]
            )
            # An explicit focus persisted on the Candidate is authoritative.
            # Remove memberships inferred from metadata-search provenance.
            conn.execute(
                """
                DELETE FROM candidate_goal_memberships
                WHERE EXISTS (
                    SELECT 1 FROM local_candidates c
                    WHERE c.candidate_id=candidate_goal_memberships.candidate_id
                      AND (c.context_relevance='outside_focus'
                           OR (COALESCE(c.goal_id, '')!=''
                               AND c.goal_id!=candidate_goal_memberships.goal_id))
                )
                """
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO candidate_goal_memberships(
                    candidate_id, goal_id, created_at
                )
                SELECT c.candidate_id, c.goal_id, ?
                FROM local_candidates c
                JOIN local_research_goals goals ON goals.goal_id=c.goal_id
                WHERE COALESCE(c.goal_id, '')!='' AND goals.status!='archived'
                  AND c.context_relevance!='outside_focus'
                """,
                (now,),
            )
            # Hide obsolete duplicate Goal cards created by the old search
            # selection side effect.  The row and search_id remain auditable.
            conn.execute(
                """
                UPDATE local_research_goals AS search_goal
                SET status='archived',
                    payload_json=json_set(
                        search_goal.payload_json,
                        '$.status', 'archived',
                        '$.merged_into', (
                            SELECT manual_goal.goal_id
                            FROM local_research_goals manual_goal
                            WHERE manual_goal.search_id IS NULL
                              AND manual_goal.status!='archived'
                              AND manual_goal.source_id=search_goal.source_id
                              AND lower(trim(manual_goal.goal))=lower(trim(search_goal.goal))
                            ORDER BY manual_goal.created_at, manual_goal.goal_id LIMIT 1
                        )
                    ),
                    updated_at=?
                WHERE search_goal.search_id IS NOT NULL
                  AND search_goal.status!='archived'
                  AND EXISTS (
                      SELECT 1 FROM local_research_goals manual_goal
                      WHERE manual_goal.search_id IS NULL
                        AND manual_goal.status!='archived'
                        AND manual_goal.source_id=search_goal.source_id
                        AND lower(trim(manual_goal.goal))=lower(trim(search_goal.goal))
                  )
                """,
                (now,),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO candidate_goal_memberships(
                    candidate_id, goal_id, created_at
                )
                SELECT sm.candidate_id, goals.goal_id, ?
                FROM candidate_source_memberships sm
                JOIN (
                    SELECT source_id, MIN(goal_id) AS goal_id
                    FROM local_research_goals
                    WHERE status!='archived' AND source_id IS NOT NULL
                    GROUP BY source_id HAVING COUNT(*)=1
                ) goals ON goals.source_id=sm.source_id
                JOIN local_candidates c ON c.candidate_id=sm.candidate_id
                WHERE NOT EXISTS (SELECT 1 FROM candidate_goal_memberships existing
                                  WHERE existing.candidate_id=sm.candidate_id)
                  AND c.context_relevance!='outside_focus'
                """,
                (now,),
            )
            conn.execute(
                """
                UPDATE local_candidates
                SET goal_id=(
                    SELECT m.goal_id FROM candidate_goal_memberships m
                    WHERE m.candidate_id=local_candidates.candidate_id
                    ORDER BY m.goal_id LIMIT 1
                )
                WHERE COALESCE(goal_id, '')='' AND EXISTS (
                    SELECT 1 FROM candidate_goal_memberships m
                    WHERE m.candidate_id=local_candidates.candidate_id
                )
                """
            )
            after = int(
                conn.execute(
                    "SELECT COUNT(*) FROM local_candidates c WHERE NOT EXISTS ("
                    "SELECT 1 FROM candidate_goal_memberships m "
                    "WHERE m.candidate_id=c.candidate_id)"
                ).fetchone()[0]
            )
        return {"repaired": before - after, "unresolved": after}

    def library_collections(
        self, kind: str, *, include_archived: bool = False
    ) -> list[dict[str, Any]]:
        if kind not in {"research_goal", "area", "source"}:
            raise ValueError("collection kind must be research_goal, area, or source")
        with self.connect() as conn:
            if kind == "research_goal":
                rows = conn.execute(
                    """
                    SELECT g.goal_id AS collection_id, g.goal AS title, g.area,
                           COALESCE(g.source_id, '') AS source_id,
                           g.status, g.updated_at,
                           COALESCE(s.display_name, '') AS source_name,
                           (SELECT COUNT(*) FROM local_candidates c
                            WHERE EXISTS (SELECT 1 FROM candidate_goal_memberships gm
                                          WHERE gm.candidate_id=c.candidate_id
                                            AND gm.goal_id=g.goal_id)
                              AND c.quality_state='eligible'
                              AND c.eligibility_status='eligible') AS principle_count,
                           (SELECT COUNT(*) FROM local_candidates c
                            WHERE EXISTS (SELECT 1 FROM candidate_goal_memberships gm
                                          WHERE gm.candidate_id=c.candidate_id
                                            AND gm.goal_id=g.goal_id)
                              AND c.quality_state='legacy_needs_revalidation')
                              AS needs_revalidation_count,
                           (SELECT COUNT(*) FROM local_candidates c
                            WHERE EXISTS (SELECT 1 FROM candidate_goal_memberships gm
                                          WHERE gm.candidate_id=c.candidate_id
                                            AND gm.goal_id=g.goal_id)
                              AND c.quality_state IN ('quarantined','not_a_principle'))
                              AS quarantined_count,
                           (SELECT COUNT(*) FROM local_source_documents d
                            WHERE d.source_id=g.source_id) AS work_count,
                           (SELECT COUNT(*) FROM candidate_work_evidence e
                            JOIN local_candidates c ON c.candidate_id=e.candidate_id
                            WHERE EXISTS (SELECT 1 FROM candidate_goal_memberships gm
                                          WHERE gm.candidate_id=c.candidate_id
                                            AND gm.goal_id=g.goal_id)
                              AND c.quality_state='eligible')
                              AS evidence_count
                    FROM local_research_goals g
                    LEFT JOIN local_sources_v14 s ON s.source_id=g.source_id
                    WHERE (? OR g.status!='archived')
                    ORDER BY g.updated_at DESC, g.goal_id
                    """,
                    (1 if include_archived else 0,),
                ).fetchall()
            elif kind == "area":
                rows = conn.execute(
                    """
                    WITH effective_candidate_areas AS (
                        SELECT c.candidate_id, c.area
                        FROM local_candidates c
                        WHERE c.area NOT IN ('', 'uncategorized')
                          AND NOT EXISTS (
                              SELECT 1 FROM candidate_area_assignments active
                              WHERE active.candidate_id=c.candidate_id
                                AND active.state IN ('confirmed', 'suggested')
                                AND active.revision=(
                                    SELECT MAX(latest_active.revision)
                                    FROM candidate_area_assignments latest_active
                                    WHERE latest_active.candidate_id=active.candidate_id
                                      AND latest_active.area=active.area
                                )
                          )
                        UNION
                        SELECT assignment.candidate_id, assignment.area
                        FROM candidate_area_assignments assignment
                        WHERE assignment.state IN ('confirmed', 'suggested')
                          AND assignment.area NOT IN ('', 'uncategorized')
                          AND assignment.revision=(
                              SELECT MAX(latest.revision)
                              FROM candidate_area_assignments latest
                              WHERE latest.candidate_id=assignment.candidate_id
                                AND latest.area=assignment.area
                          )
                    ), areas AS (
                        SELECT DISTINCT area FROM effective_candidate_areas
                        UNION
                        SELECT DISTINCT area FROM local_research_goals
                        WHERE area NOT IN ('', 'uncategorized')
                          AND status!='removed'
                    )
                    SELECT 'area:' || a.area AS collection_id,
                           a.area AS title, a.area, '' AS source_id,
                           'active' AS status,
                           COALESCE((SELECT MAX(updated_at) FROM local_candidates c
                                     WHERE EXISTS (
                                         SELECT 1 FROM effective_candidate_areas eca
                                         WHERE eca.candidate_id=c.candidate_id
                                           AND eca.area=a.area
                                     )), '') AS updated_at,
                           '' AS source_name,
                           (SELECT COUNT(*) FROM local_candidates c
                            WHERE EXISTS (
                                      SELECT 1 FROM effective_candidate_areas eca
                                      WHERE eca.candidate_id=c.candidate_id
                                        AND eca.area=a.area
                                  ) AND c.quality_state='eligible'
                              AND c.eligibility_status='eligible') AS principle_count,
                           (SELECT COUNT(*) FROM local_candidates c
                            WHERE EXISTS (
                                      SELECT 1 FROM effective_candidate_areas eca
                                      WHERE eca.candidate_id=c.candidate_id
                                        AND eca.area=a.area
                                  )
                              AND c.quality_state='legacy_needs_revalidation')
                              AS needs_revalidation_count,
                           (SELECT COUNT(*) FROM local_candidates c
                            WHERE EXISTS (
                                      SELECT 1 FROM effective_candidate_areas eca
                                      WHERE eca.candidate_id=c.candidate_id
                                        AND eca.area=a.area
                                  )
                              AND c.quality_state IN ('quarantined','not_a_principle'))
                              AS quarantined_count,
                           (SELECT COUNT(DISTINCT e.work_id)
                            FROM candidate_work_evidence e
                            JOIN local_candidates c ON c.candidate_id=e.candidate_id
                            WHERE EXISTS (
                                SELECT 1 FROM effective_candidate_areas eca
                                WHERE eca.candidate_id=c.candidate_id
                                  AND eca.area=a.area
                            )) AS work_count,
                           (SELECT COUNT(*) FROM candidate_work_evidence e
                            JOIN local_candidates c ON c.candidate_id=e.candidate_id
                            WHERE EXISTS (
                                      SELECT 1 FROM effective_candidate_areas eca
                                      WHERE eca.candidate_id=c.candidate_id
                                        AND eca.area=a.area
                                  ) AND c.quality_state='eligible')
                              AS evidence_count
                    FROM areas a
                    ORDER BY a.area
                    """
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT s.source_id AS collection_id, s.display_name AS title,
                           COALESCE((SELECT area FROM local_research_goals g
                                     WHERE g.source_id=s.source_id LIMIT 1), '') AS area,
                           s.source_id, s.status, s.updated_at,
                           s.display_name AS source_name,
                           (SELECT COUNT(*) FROM local_candidates c
                            WHERE EXISTS (SELECT 1 FROM candidate_source_memberships sm
                                          WHERE sm.candidate_id=c.candidate_id
                                            AND sm.source_id=s.source_id)
                              AND c.quality_state='eligible'
                              AND c.eligibility_status='eligible') AS principle_count,
                           (SELECT COUNT(*) FROM local_candidates c
                            WHERE EXISTS (SELECT 1 FROM candidate_source_memberships sm
                                          WHERE sm.candidate_id=c.candidate_id
                                            AND sm.source_id=s.source_id)
                              AND c.quality_state='legacy_needs_revalidation')
                              AS needs_revalidation_count,
                           (SELECT COUNT(*) FROM local_candidates c
                            WHERE EXISTS (SELECT 1 FROM candidate_source_memberships sm
                                          WHERE sm.candidate_id=c.candidate_id
                                            AND sm.source_id=s.source_id)
                              AND c.quality_state IN ('quarantined','not_a_principle'))
                              AS quarantined_count,
                           (SELECT COUNT(*) FROM local_source_documents d
                            WHERE d.source_id=s.source_id) AS work_count,
                           (SELECT COUNT(*) FROM candidate_work_evidence e
                            JOIN local_candidates c ON c.candidate_id=e.candidate_id
                            WHERE EXISTS (SELECT 1 FROM candidate_source_memberships sm
                                          WHERE sm.candidate_id=c.candidate_id
                                            AND sm.source_id=s.source_id)
                              AND c.quality_state='eligible')
                              AS evidence_count,
                           s.display_location
                    FROM local_sources_v14 s WHERE (? OR s.status!='removed')
                    ORDER BY s.updated_at DESC, s.source_id
                    """,
                    (1 if include_archived else 0,),
                ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            item["kind"] = kind
            item["overlapping_view"] = True
            item.setdefault("display_location", "")
            output.append(item)
        return output

    @staticmethod
    def _append_mutation_event(
        conn: sqlite3.Connection,
        *,
        aggregate_type: str,
        aggregate_id: str,
        operation: str,
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> None:
        payload = {"before": before, "after": after}
        conn.execute(
            """
            INSERT INTO v14_events(
                event_id, aggregate_type, aggregate_id, operation,
                input_digest, output_digest, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"event:{uuid.uuid4().hex}",
                aggregate_type,
                aggregate_id,
                operation,
                canonical_sha256(before),
                canonical_sha256(after),
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                utc_now(),
            ),
        )

    def update_collection(self, kind: str, collection_id: str, title: str) -> dict[str, Any]:
        normalized = " ".join(title.split())
        if not normalized:
            raise ValueError("a collection title cannot be empty")
        now = utc_now()
        with self.connect() as conn:
            if kind == "research_goal":
                row = conn.execute(
                    "SELECT goal_id, goal, area, COALESCE(source_id, '') AS source_id, "
                    "status, payload_json FROM local_research_goals WHERE goal_id=?",
                    (collection_id,),
                ).fetchone()
                if row is None:
                    raise KeyError(f"unknown Research Goal: {collection_id}")
                before = dict(row)
                payload = json.loads(row["payload_json"])
                payload["goal"] = normalized
                conn.execute(
                    "UPDATE local_research_goals SET goal=?, payload_json=?, updated_at=? "
                    "WHERE goal_id=?",
                    (
                        normalized,
                        json.dumps(payload, ensure_ascii=False, sort_keys=True),
                        now,
                        collection_id,
                    ),
                )
                after = {**before, "goal": normalized, "payload_json": payload}
                self._append_mutation_event(
                    conn,
                    aggregate_type="research_goal",
                    aggregate_id=collection_id,
                    operation="rename",
                    before=before,
                    after=after,
                )
                return {"collection_id": collection_id, "kind": kind, "title": normalized}
            if kind == "source":
                row = conn.execute(
                    "SELECT source_id, display_name, status, payload_json "
                    "FROM local_sources_v14 WHERE source_id=?",
                    (collection_id,),
                ).fetchone()
                if row is None:
                    raise KeyError(f"unknown Local source: {collection_id}")
                before = dict(row)
                payload = json.loads(row["payload_json"])
                payload["display_name"] = normalized
                payload["updated_at"] = now
                conn.execute(
                    "UPDATE local_sources_v14 SET display_name=?, payload_json=?, updated_at=? "
                    "WHERE source_id=?",
                    (
                        normalized,
                        json.dumps(payload, ensure_ascii=False, sort_keys=True),
                        now,
                        collection_id,
                    ),
                )
                after = {**before, "display_name": normalized, "payload_json": payload}
                self._append_mutation_event(
                    conn,
                    aggregate_type="local_source",
                    aggregate_id=collection_id,
                    operation="rename",
                    before=before,
                    after=after,
                )
                return {"collection_id": collection_id, "kind": kind, "title": normalized}
            if kind != "area":
                raise ValueError("unknown collection kind")
            old_area = collection_id.removeprefix("area:")
            new_area = normalized.casefold().replace(" ", "-")
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", new_area):
                raise ValueError("Area labels use 2-63 lowercase letters, numbers, and hyphens")
            return self._relabel_area(conn, old_area=old_area, new_area=new_area, now=now)

    def _relabel_area(
        self, conn: sqlite3.Connection, *, old_area: str, new_area: str, now: str
    ) -> dict[str, Any]:
        candidate_rows = conn.execute(
            """
            SELECT DISTINCT c.candidate_id, c.payload_json
            FROM local_candidates c
            WHERE c.area=? OR EXISTS (
                SELECT 1 FROM candidate_area_assignments assignment
                WHERE assignment.candidate_id=c.candidate_id
                  AND assignment.area=?
                  AND assignment.state IN ('confirmed','suggested')
                  AND assignment.revision=(
                    SELECT MAX(latest.revision)
                    FROM candidate_area_assignments latest
                    WHERE latest.candidate_id=assignment.candidate_id
                      AND latest.area=assignment.area
                  )
            )
            """,
            (old_area, old_area),
        ).fetchall()
        goal_rows = conn.execute(
            "SELECT goal_id, payload_json FROM local_research_goals WHERE area=?",
            (old_area,),
        ).fetchall()
        if not candidate_rows and not goal_rows:
            raise KeyError(f"unknown Area collection: area:{old_area}")
        before = {
            "area": old_area,
            "candidate_ids": [str(row["candidate_id"]) for row in candidate_rows],
            "goal_ids": [str(row["goal_id"]) for row in goal_rows],
        }
        for row in candidate_rows:
            candidate_id = str(row["candidate_id"])
            payload = json.loads(row["payload_json"])
            # The scalar area is a legacy fallback.  Relabel it only when it is
            # the label being changed; multi-label Candidates retain their
            # other current assignments.
            if str(payload.get("area") or "") == old_area:
                payload["area"] = new_area
                payload["updated_at"] = now
                conn.execute(
                    "UPDATE local_candidates SET area=?, payload_json=?, content_digest=?, "
                    "updated_at=? WHERE candidate_id=?",
                    (
                        new_area,
                        json.dumps(payload, ensure_ascii=False, sort_keys=True),
                        canonical_sha256(payload),
                        now,
                        candidate_id,
                    ),
                )
            latest_old = int(
                conn.execute(
                    "SELECT COALESCE(MAX(revision), 0) FROM candidate_area_assignments "
                    "WHERE candidate_id=? AND area=?",
                    (candidate_id, old_area),
                ).fetchone()[0]
            )
            if latest_old:
                decision = {
                    "candidate_id": candidate_id,
                    "area": old_area,
                    "state": "rejected",
                    "provenance": "human_library_edit",
                    "rationale": f"Renamed to {new_area}",
                }
                conn.execute(
                    "INSERT INTO candidate_area_assignments(candidate_id, area, revision, "
                    "state, provenance, rationale, model_trace_json, payload_json, created_at) "
                    "VALUES (?, ?, ?, 'rejected', 'human_library_edit', ?, '{}', ?, ?)",
                    (
                        candidate_id,
                        old_area,
                        latest_old + 1,
                        decision["rationale"],
                        json.dumps(decision, ensure_ascii=False, sort_keys=True),
                        now,
                    ),
                )
            current_labels = [
                str(item[0])
                for item in conn.execute(
                    """
                    SELECT assignment.area
                    FROM candidate_area_assignments assignment
                    WHERE assignment.candidate_id=?
                      AND assignment.state IN ('confirmed','suggested')
                      AND assignment.revision=(
                        SELECT MAX(latest.revision)
                        FROM candidate_area_assignments latest
                        WHERE latest.candidate_id=assignment.candidate_id
                          AND latest.area=assignment.area
                      )
                    ORDER BY assignment.area
                    """,
                    (candidate_id,),
                ).fetchall()
            ]
            fallback_area = str(payload.get("area") or "")
            fts_area = " ".join(current_labels or ([fallback_area] if fallback_area else []))
            conn.execute(
                "UPDATE local_principle_fts SET area=? WHERE principle_id=? AND version=0",
                (fts_area, candidate_id),
            )
            if new_area != "uncategorized":
                latest_new = int(
                    conn.execute(
                        "SELECT COALESCE(MAX(revision), 0) FROM candidate_area_assignments "
                        "WHERE candidate_id=? AND area=?",
                        (candidate_id, new_area),
                    ).fetchone()[0]
                )
                decision = {
                    "candidate_id": candidate_id,
                    "area": new_area,
                    "state": "confirmed",
                    "provenance": "human_library_edit",
                    "rationale": f"Renamed from {old_area}",
                }
                conn.execute(
                    "INSERT INTO candidate_area_assignments(candidate_id, area, revision, "
                    "state, provenance, rationale, model_trace_json, payload_json, created_at) "
                    "VALUES (?, ?, ?, 'confirmed', 'human_library_edit', ?, '{}', ?, ?)",
                    (
                        candidate_id,
                        new_area,
                        latest_new + 1,
                        decision["rationale"],
                        json.dumps(decision, ensure_ascii=False, sort_keys=True),
                        now,
                    ),
                )
        for row in goal_rows:
            payload = json.loads(row["payload_json"])
            payload["area"] = "" if new_area == "uncategorized" else new_area
            conn.execute(
                "UPDATE local_research_goals SET area=?, payload_json=?, updated_at=? "
                "WHERE goal_id=?",
                (
                    payload["area"],
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    now,
                    row["goal_id"],
                ),
            )
        after = {
            "area": new_area,
            "candidate_ids": before["candidate_ids"],
            "goal_ids": before["goal_ids"],
        }
        self._append_mutation_event(
            conn,
            aggregate_type="area",
            aggregate_id=f"area:{old_area}",
            operation="remove_label" if new_area == "uncategorized" else "rename",
            before=before,
            after=after,
        )
        return {
            "collection_id": f"area:{new_area}",
            "kind": "area",
            "title": new_area,
            "updated_candidates": len(candidate_rows),
            "updated_goals": len(goal_rows),
        }

    def archive_collection(self, kind: str, collection_id: str) -> dict[str, Any]:
        if kind == "area":
            old_area = collection_id.removeprefix("area:")
            with self.connect() as conn:
                return self._relabel_area(
                    conn, old_area=old_area, new_area="uncategorized", now=utc_now()
                )
        if kind not in {"research_goal", "source"}:
            raise ValueError("unknown collection kind")
        table = "local_research_goals" if kind == "research_goal" else "local_sources_v14"
        id_column = "goal_id" if kind == "research_goal" else "source_id"
        removed_state = "archived" if kind == "research_goal" else "removed"
        with self.connect() as conn:
            row = conn.execute(
                f"SELECT {id_column}, status, payload_json FROM {table} WHERE {id_column}=?",
                (collection_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown {kind} collection: {collection_id}")
            before = dict(row)
            payload = json.loads(row["payload_json"])
            payload["status"] = removed_state
            payload["updated_at"] = utc_now()
            conn.execute(
                f"UPDATE {table} SET status=?, payload_json=?, updated_at=? WHERE {id_column}=?",
                (
                    removed_state,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    payload["updated_at"],
                    collection_id,
                ),
            )
            after = {**before, "status": removed_state, "payload_json": payload}
            self._append_mutation_event(
                conn,
                aggregate_type=kind,
                aggregate_id=collection_id,
                operation="archive" if kind == "research_goal" else "disconnect",
                before=before,
                after=after,
            )
        return {"collection_id": collection_id, "kind": kind, "status": removed_state}

    def restore_collection(self, kind: str, collection_id: str) -> dict[str, Any]:
        if kind not in {"research_goal", "source"}:
            raise ValueError("only Research Goals and private folders can be restored")
        table = "local_research_goals" if kind == "research_goal" else "local_sources_v14"
        id_column = "goal_id" if kind == "research_goal" else "source_id"
        with self.connect() as conn:
            row = conn.execute(
                f"SELECT {id_column}, status, payload_json FROM {table} WHERE {id_column}=?",
                (collection_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown {kind} collection: {collection_id}")
            before = dict(row)
            payload = json.loads(row["payload_json"])
            payload["status"] = "active" if kind == "research_goal" else "ready"
            payload["updated_at"] = utc_now()
            conn.execute(
                f"UPDATE {table} SET status=?, payload_json=?, updated_at=? WHERE {id_column}=?",
                (
                    payload["status"],
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    payload["updated_at"],
                    collection_id,
                ),
            )
            after = {**before, "status": payload["status"], "payload_json": payload}
            self._append_mutation_event(
                conn,
                aggregate_type=kind,
                aggregate_id=collection_id,
                operation="restore",
                before=before,
                after=after,
            )
        return {"collection_id": collection_id, "kind": kind, "status": payload["status"]}

    def principle(self, principle_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json FROM local_principles
                WHERE principle_id=? ORDER BY version DESC LIMIT 1
                """,
                (principle_id,),
            ).fetchone()
            if row is None:
                row = conn.execute(
                    "SELECT payload_json FROM local_candidates WHERE candidate_id=?",
                    (principle_id,),
                ).fetchone()
        return json.loads(row[0]) if row else None

    def candidate_detail(self, candidate_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json, eligibility_status, source_kind, discovery_job_id,
                       dataset_id, source_count, relation_count, quarantine_reason,
                       candidate_fingerprint, goal_id, source_id,
                       scientific_contract_version, quality_gate_version, quality_state,
                       extraction_mode, context_relevance
                FROM local_candidates WHERE candidate_id=?
                """,
                (candidate_id,),
            ).fetchone()
            if row is None:
                return None
            payload = json.loads(row["payload_json"])
            evidence_rows = conn.execute(
                """
                SELECT e.evidence_id, e.work_id, e.role, e.locator_json,
                       e.excerpt_sha256, e.visibility, e.segment_id,
                       s.section, s.page_start, s.page_end,
                       w.payload_json AS work_json
                FROM candidate_work_evidence e
                JOIN works w ON w.id=e.work_id
                LEFT JOIN scholarly_segments s ON s.segment_id=e.segment_id
                WHERE e.candidate_id=?
                ORDER BY e.work_id, e.evidence_id LIMIT 100
                """,
                (candidate_id,),
            ).fetchall()
            incoming = conn.execute(
                """
                SELECT source_candidate_id, relation_type, provenance, payload_json
                FROM local_candidate_relations WHERE target_principle_id=?
                ORDER BY source_candidate_id, relation_index LIMIT 100
                """,
                (candidate_id,),
            ).fetchall()
            argument_row = conn.execute(
                """
                SELECT revision, payload_json, content_digest
                FROM candidate_argument_revisions WHERE candidate_id=?
                ORDER BY revision DESC LIMIT 1
                """,
                (candidate_id,),
            ).fetchone()
            evaluations = conn.execute(
                """
                SELECT payload_json FROM candidate_quality_evaluations
                WHERE candidate_id=? ORDER BY created_at, evaluation_id LIMIT 100
                """,
                (candidate_id,),
            ).fetchall()
            goal_memberships = conn.execute(
                "SELECT goal_id FROM candidate_goal_memberships WHERE candidate_id=? ORDER BY goal_id",
                (candidate_id,),
            ).fetchall()
            source_memberships = conn.execute(
                "SELECT source_id FROM candidate_source_memberships WHERE candidate_id=? ORDER BY source_id",
                (candidate_id,),
            ).fetchall()
            area_assignments = conn.execute(
                """
                SELECT a.area, a.revision, a.state, a.provenance, a.rationale,
                       a.created_at
                FROM candidate_area_assignments a
                WHERE a.candidate_id=? AND a.revision=(
                    SELECT MAX(latest.revision) FROM candidate_area_assignments latest
                    WHERE latest.candidate_id=a.candidate_id AND latest.area=a.area
                )
                ORDER BY CASE a.state WHEN 'confirmed' THEN 0 WHEN 'suggested' THEN 1 ELSE 2 END,
                         a.area
                """,
                (candidate_id,),
            ).fetchall()
        evidence: list[dict[str, Any]] = []
        for item in evidence_rows:
            work = json.loads(item["work_json"])
            locator = json.loads(item["locator_json"])
            evidence.append(
                {
                    "evidence_id": item["evidence_id"],
                    "work_id": item["work_id"],
                    "work_title": work.get("title") or item["work_id"],
                    "source_url": _public_reference_url(work),
                    "role": item["role"],
                    "locator": {key: value for key, value in locator.items() if key != "quotation"},
                    "excerpt_sha256": item["excerpt_sha256"],
                    "visibility": item["visibility"],
                    "segment_id": item["segment_id"],
                    "section": item["section"],
                    "page_start": item["page_start"],
                    "page_end": item["page_end"],
                    "quotation": str(locator.get("quotation") or "")[:1_200],
                    "excerpt_available": bool(locator.get("quotation")),
                }
            )
        payload["local_metadata"] = {
            "eligibility_status": row["eligibility_status"],
            "source_kind": row["source_kind"],
            "discovery_id": row["discovery_job_id"],
            "dataset_id": row["dataset_id"],
            "source_count": row["source_count"],
            "relation_count": row["relation_count"],
            "quarantine_reason": row["quarantine_reason"],
            "candidate_fingerprint": row["candidate_fingerprint"],
            "goal_id": row["goal_id"],
            "source_id": row["source_id"],
            "scientific_contract_version": row["scientific_contract_version"],
            "quality_gate_version": row["quality_gate_version"],
            "quality_state": row["quality_state"],
            "extraction_mode": row["extraction_mode"],
            "context_relevance": row["context_relevance"],
            "goal_ids": [item["goal_id"] for item in goal_memberships],
            "source_ids": [item["source_id"] for item in source_memberships],
        }
        payload["scientific_argument"] = (
            json.loads(argument_row["payload_json"]) if argument_row is not None else None
        )
        payload["quality_evaluations"] = [json.loads(item["payload_json"]) for item in evaluations]
        payload["evidence"] = evidence
        payload["area_suggestions"] = [dict(item) for item in area_assignments]
        payload["incoming_relations"] = [
            {
                "source_candidate_id": item["source_candidate_id"],
                "relation_type": item["relation_type"],
                "provenance": item["provenance"],
                "relation": json.loads(item["payload_json"]),
            }
            for item in incoming
        ]
        return payload

    def update_candidate_display(self, candidate_id: str, title: str) -> dict[str, Any]:
        """Edit presentation metadata without weakening scientific evidence checks."""

        normalized = " ".join(title.split())
        if len(normalized) < 3 or len(normalized) > 240:
            raise ValueError("a Principle title must contain 3-240 characters")
        now = utc_now()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT payload_json, title, claim, area, quality_state, eligibility_status "
                "FROM local_candidates WHERE candidate_id=?",
                (candidate_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown Candidate: {candidate_id}")
            payload = json.loads(row["payload_json"])
            before = {
                "title": row["title"],
                "content_digest": canonical_sha256(payload),
            }
            payload["title"] = normalized
            payload["updated_at"] = now
            conn.execute(
                "UPDATE local_candidates SET title=?, payload_json=?, content_digest=?, "
                "updated_at=? WHERE candidate_id=?",
                (
                    normalized,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    canonical_sha256(payload),
                    now,
                    candidate_id,
                ),
            )
            conn.execute(
                "UPDATE local_principle_fts SET title=? WHERE principle_id=? AND version=0",
                (normalized, candidate_id),
            )
            after = {"title": normalized, "content_digest": canonical_sha256(payload)}
            self._append_mutation_event(
                conn,
                aggregate_type="candidate",
                aggregate_id=candidate_id,
                operation="edit_display_title",
                before=before,
                after=after,
            )
        return {"candidate_id": candidate_id, "title": normalized, "status": "updated"}

    def archive_candidate(self, candidate_id: str) -> dict[str, Any]:
        now = utc_now()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT quality_state, eligibility_status, quarantine_reason "
                "FROM local_candidates WHERE candidate_id=?",
                (candidate_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown Candidate: {candidate_id}")
            before = dict(row)
            after = {
                "quality_state": "archived",
                "eligibility_status": "archived",
                "quarantine_reason": row["quarantine_reason"],
            }
            conn.execute(
                "UPDATE local_candidates SET quality_state='archived', "
                "eligibility_status='archived', updated_at=? WHERE candidate_id=?",
                (now, candidate_id),
            )
            conn.execute(
                "DELETE FROM local_principle_fts WHERE principle_id=? AND version=0",
                (candidate_id,),
            )
            self._append_mutation_event(
                conn,
                aggregate_type="candidate",
                aggregate_id=candidate_id,
                operation="archive",
                before=before,
                after=after,
            )
        return {"candidate_id": candidate_id, "status": "archived"}

    def restore_candidate(self, candidate_id: str) -> dict[str, Any]:
        now = utc_now()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT title, claim, area, quality_state, eligibility_status, "
                "quarantine_reason FROM local_candidates WHERE candidate_id=?",
                (candidate_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown Candidate: {candidate_id}")
            if row["quality_state"] != "archived":
                raise ValueError("the Principle is not archived")
            event = conn.execute(
                "SELECT payload_json FROM v14_events WHERE aggregate_type='candidate' "
                "AND aggregate_id=? AND operation='archive' ORDER BY created_at DESC LIMIT 1",
                (candidate_id,),
            ).fetchone()
            if event is None:
                raise ValueError("the archived Principle has no restoration receipt")
            receipt = json.loads(event["payload_json"])
            prior = dict(receipt.get("before") or {})
            quality_state = str(prior.get("quality_state") or "legacy_needs_revalidation")
            eligibility_status = str(prior.get("eligibility_status") or "unassessed")
            quarantine_reason = str(prior.get("quarantine_reason") or "")
            conn.execute(
                "UPDATE local_candidates SET quality_state=?, eligibility_status=?, "
                "quarantine_reason=?, updated_at=? WHERE candidate_id=?",
                (quality_state, eligibility_status, quarantine_reason, now, candidate_id),
            )
            if quality_state == "eligible" and eligibility_status == "eligible":
                conn.execute(
                    "INSERT INTO local_principle_fts(principle_id, version, title, claim, area, tags) "
                    "VALUES (?, 0, ?, ?, ?, '')",
                    (candidate_id, row["title"], row["claim"], row["area"]),
                )
            before = {
                "quality_state": row["quality_state"],
                "eligibility_status": row["eligibility_status"],
            }
            after = {
                "quality_state": quality_state,
                "eligibility_status": eligibility_status,
                "quarantine_reason": quarantine_reason,
            }
            self._append_mutation_event(
                conn,
                aggregate_type="candidate",
                aggregate_id=candidate_id,
                operation="restore",
                before=before,
                after=after,
            )
        return {"candidate_id": candidate_id, "status": "restored"}

    def candidate_area_suggestions(self, candidate_id: str) -> list[dict[str, Any]]:
        detail = self.candidate_detail(candidate_id)
        if detail is None:
            raise KeyError(candidate_id)
        return list(detail["area_suggestions"])

    def set_candidate_area(
        self,
        candidate_id: str,
        area: str,
        *,
        state: str,
        provenance: str,
        rationale: str,
    ) -> dict[str, Any]:
        if state not in {"suggested", "confirmed", "rejected"}:
            raise ValueError("unknown Area suggestion state")
        normalized = area.strip().casefold()
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]+", normalized):
            raise ValueError("Area labels use lowercase letters, digits, and hyphens")
        now = utc_now()
        with self.connect() as conn:
            if (
                conn.execute(
                    "SELECT 1 FROM local_candidates WHERE candidate_id=?", (candidate_id,)
                ).fetchone()
                is None
            ):
                raise KeyError(candidate_id)
            revision = int(
                conn.execute(
                    "SELECT COALESCE(MAX(revision), 0) + 1 FROM candidate_area_assignments "
                    "WHERE candidate_id=? AND area=?",
                    (candidate_id, normalized),
                ).fetchone()[0]
            )
            payload = {
                "candidate_id": candidate_id,
                "area": normalized,
                "revision": revision,
                "state": state,
                "provenance": provenance,
                "rationale": rationale,
                "created_at": now,
            }
            conn.execute(
                """
                INSERT INTO candidate_area_assignments(
                    candidate_id, area, revision, state, provenance, rationale,
                    model_trace_json, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, '{}', ?, ?)
                """,
                (
                    candidate_id,
                    normalized,
                    revision,
                    state,
                    provenance,
                    rationale,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    now,
                ),
            )
        return payload

    def save_candidate_evidence(
        self,
        *,
        evidence_id: str,
        candidate_id: str,
        work_id: str,
        excerpt_sha256: str,
        role: str = "evidence",
        segment_id: str | None = None,
        acquisition_id: str | None = None,
        locator: dict[str, Any] | None = None,
        extraction_trace: dict[str, Any] | None = None,
        visibility: str = "private",
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO candidate_work_evidence(
                    evidence_id, candidate_id, work_id, acquisition_id, segment_id,
                    role, locator_json, excerpt_sha256, extraction_trace_json,
                    visibility, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence_id,
                    candidate_id,
                    work_id,
                    acquisition_id,
                    segment_id,
                    role,
                    json.dumps(locator or {}, ensure_ascii=False, sort_keys=True),
                    excerpt_sha256,
                    json.dumps(extraction_trace or {}, ensure_ascii=False, sort_keys=True),
                    visibility,
                    utc_now(),
                ),
            )
            count = conn.execute(
                "SELECT COUNT(DISTINCT work_id) FROM candidate_work_evidence WHERE candidate_id=?",
                (candidate_id,),
            ).fetchone()[0]
            conn.execute(
                "UPDATE local_candidates SET source_count=? WHERE candidate_id=?",
                (count, candidate_id),
            )

    def save_evidence_atom(
        self,
        atom: EvidenceClaimAtom,
        *,
        candidate_id: str = "",
        work_id: str,
        source_document_id: str = "",
    ) -> None:
        payload = atom.model_dump(mode="json")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO evidence_claim_atoms(
                    atom_id, candidate_id, work_id, source_document_id, source_key,
                    assertion_type, evidence_type, epistemic_status, faithful_claim,
                    payload_json, content_digest, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(atom_id) DO UPDATE SET
                    candidate_id=COALESCE(evidence_claim_atoms.candidate_id,
                                          excluded.candidate_id),
                    source_document_id=COALESCE(evidence_claim_atoms.source_document_id,
                                                excluded.source_document_id)
                """,
                (
                    atom.atom_id,
                    candidate_id or None,
                    work_id,
                    source_document_id or None,
                    atom.source_key,
                    atom.assertion_type,
                    atom.evidence_type,
                    atom.epistemic_status,
                    atom.faithful_claim,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    canonical_sha256(payload),
                    utc_now(),
                ),
            )
            if candidate_id:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO candidate_atom_links(candidate_id, atom_id, created_at)
                    VALUES (?, ?, ?)
                    """,
                    (candidate_id, atom.atom_id, utc_now()),
                )

    def evidence_atoms_for_document(self, source_document_id: str) -> list[EvidenceClaimAtom]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM evidence_claim_atoms
                WHERE source_document_id=? ORDER BY atom_id
                """,
                (source_document_id,),
            ).fetchall()
        return [
            EvidenceClaimAtom.model_validate(json.loads(str(row["payload_json"]))) for row in rows
        ]

    def deterministic_revalidation_inputs(self, *, limit: int = 100_000) -> list[dict[str, Any]]:
        """Load current eligible arguments with their exact source atoms.

        This is intentionally a bounded internal maintenance projection. It is
        used when deterministic safeguards become stricter; no provider call
        and no source re-download is required.
        """

        with self.connect() as conn:
            rows = conn.execute(
                """
                WITH latest AS (
                    SELECT candidate_id, MAX(revision) AS revision
                    FROM candidate_argument_revisions GROUP BY candidate_id
                )
                SELECT c.candidate_id, c.goal_id, latest.revision, a.payload_json,
                       COALESCE(goal.goal, '') AS research_focus
                FROM local_candidates c
                JOIN latest ON latest.candidate_id=c.candidate_id
                JOIN candidate_argument_revisions a
                  ON a.candidate_id=latest.candidate_id AND a.revision=latest.revision
                LEFT JOIN local_research_goals goal ON goal.goal_id=c.goal_id
                WHERE c.quality_state='eligible' AND c.eligibility_status='eligible'
                ORDER BY c.candidate_id LIMIT ?
                """,
                (max(1, min(int(limit), 100_000)),),
            ).fetchall()
            output: list[dict[str, Any]] = []
            for row in rows:
                atom_rows = conn.execute(
                    """
                    SELECT atom.payload_json, atom.work_id
                    FROM candidate_atom_links link
                    JOIN evidence_claim_atoms atom ON atom.atom_id=link.atom_id
                    WHERE link.candidate_id=? ORDER BY atom.atom_id
                    """,
                    (row["candidate_id"],),
                ).fetchall()
                output.append(
                    {
                        "candidate_id": str(row["candidate_id"]),
                        "goal_id": str(row["goal_id"] or ""),
                        "research_focus": str(row["research_focus"] or ""),
                        "revision": int(row["revision"]),
                        "argument": ScientificArgument.model_validate_json(row["payload_json"]),
                        "atoms": [
                            EvidenceClaimAtom.model_validate_json(item["payload_json"])
                            for item in atom_rows
                        ],
                        "work_ids": {str(item["work_id"]) for item in atom_rows},
                    }
                )
        return output

    def set_candidate_context_relevance(
        self, candidate_id: str, *, goal_id: str, relevance: str
    ) -> None:
        if relevance not in {"matches", "outside_focus", "uncertain", "not_evaluated"}:
            raise ValueError("invalid Candidate context relevance")
        with self.connect() as conn:
            conn.execute(
                "UPDATE local_candidates SET context_relevance=?, updated_at=? "
                "WHERE candidate_id=?",
                (relevance, utc_now(), candidate_id),
            )
            if not goal_id:
                return
            if relevance == "matches":
                conn.execute(
                    "INSERT OR IGNORE INTO candidate_goal_memberships("
                    "candidate_id, goal_id, created_at) VALUES (?, ?, ?)",
                    (candidate_id, goal_id, utc_now()),
                )
            else:
                conn.execute(
                    "DELETE FROM candidate_goal_memberships WHERE candidate_id=? AND goal_id=?",
                    (candidate_id, goal_id),
                )

    def save_scientific_argument(
        self,
        candidate_id: str,
        argument: ScientificArgument,
        *,
        atoms: list[EvidenceClaimAtom],
    ) -> int:
        payload = argument.model_dump(mode="json")
        now = utc_now()
        atoms_by_segment = {
            span.segment_key: atom.atom_id for atom in atoms for span in atom.support
        }
        with self.connect() as conn:
            revision = int(
                conn.execute(
                    "SELECT COALESCE(MAX(revision), 0) + 1 "
                    "FROM candidate_argument_revisions WHERE candidate_id=?",
                    (candidate_id,),
                ).fetchone()[0]
            )
            conn.execute(
                """
                INSERT INTO candidate_argument_revisions(
                    candidate_id, revision, scientific_contract_version,
                    generalization_level, claim_class, payload_json,
                    content_digest, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate_id,
                    revision,
                    argument.scientific_contract_version,
                    argument.generalization_level.value,
                    argument.claim_class.value,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    canonical_sha256(payload),
                    now,
                ),
            )
            for index, span in enumerate(argument.support):
                atom_id = atoms_by_segment.get(span.segment_key)
                if not atom_id:
                    raise ValueError(
                        f"argument support segment is not owned by an atom: {span.segment_key}"
                    )
                segment_row = conn.execute(
                    "SELECT segment_id FROM scholarly_segments WHERE segment_key=?",
                    (span.segment_key.split(":chunk:", 1)[0],),
                ).fetchone()
                conn.execute(
                    """
                    INSERT INTO candidate_clause_support(
                        candidate_id, argument_revision, support_index, atom_id,
                        segment_id, supported_fields_json, quotation_sha256,
                        payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        candidate_id,
                        revision,
                        index,
                        atom_id,
                        str(segment_row["segment_id"]) if segment_row else None,
                        json.dumps(span.supported_fields, sort_keys=True),
                        canonical_sha256({"quotation": span.quotation}),
                        span.model_dump_json(),
                    ),
                )
        return revision

    def save_quality_evaluation(self, evaluation: QualityEvaluation) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO candidate_quality_evaluations(
                    evaluation_id, candidate_id, argument_revision, verdict,
                    reason_codes_json, scientific_contract_version,
                    quality_gate_version, evidence_digest, assessor,
                    payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evaluation.evaluation_id,
                    evaluation.candidate_id,
                    evaluation.argument_revision,
                    evaluation.verdict.value,
                    json.dumps([item.value for item in evaluation.reason_codes]),
                    evaluation.scientific_contract_version,
                    evaluation.quality_gate_version,
                    evaluation.evidence_digest,
                    evaluation.assessor,
                    evaluation.model_dump_json(),
                    evaluation.created_at,
                ),
            )

    def set_candidate_quality_state(
        self,
        candidate_id: str,
        *,
        quality_state: str,
        eligibility_status: str,
        reason: str = "",
        scientific_contract_version: str = "scientific-principle-v2",
        quality_gate_version: str = "quality-v2",
    ) -> None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT title, claim, area FROM local_candidates WHERE candidate_id=?",
                (candidate_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown Candidate: {candidate_id}")
            conn.execute(
                """
                UPDATE local_candidates
                SET quality_state=?, eligibility_status=?, quarantine_reason=?,
                    scientific_contract_version=?, quality_gate_version=?, updated_at=?
                WHERE candidate_id=?
                """,
                (
                    quality_state,
                    eligibility_status,
                    reason,
                    scientific_contract_version,
                    quality_gate_version,
                    utc_now(),
                    candidate_id,
                ),
            )
            conn.execute(
                "DELETE FROM local_principle_fts WHERE principle_id=? AND version=0",
                (candidate_id,),
            )
            if quality_state == "eligible" and eligibility_status == "eligible":
                conn.execute(
                    """
                    INSERT INTO local_principle_fts(
                        principle_id, version, title, claim, area, tags
                    ) VALUES (?, 0, ?, ?, ?, '')
                    """,
                    (candidate_id, row["title"], row["claim"], row["area"]),
                )

    def candidate_by_fingerprint(self, fingerprint: str) -> CandidatePrinciple | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM local_candidates "
                "WHERE candidate_fingerprint=? AND eligibility_status='eligible' "
                "AND quality_state='eligible' "
                "ORDER BY created_at, candidate_id LIMIT 1",
                (fingerprint,),
            ).fetchone()
        return CandidatePrinciple.model_validate_json(row[0]) if row else None

    def candidate_claims(self, area: str, *, limit: int = 10_000) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT candidate_id, claim, payload_json, candidate_fingerprint
                FROM local_candidates
                WHERE area=? AND eligibility_status='eligible' AND quality_state='eligible'
                ORDER BY created_at, candidate_id LIMIT ?
                """,
                (area, max(1, min(int(limit), 100_000))),
            ).fetchall()
        return [dict(row) for row in rows]

    def scientific_candidate_arguments(self, area: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                WITH latest AS (
                    SELECT candidate_id, MAX(revision) AS revision
                    FROM candidate_argument_revisions GROUP BY candidate_id
                )
                SELECT c.payload_json AS candidate_json,
                       c.candidate_fingerprint,
                       a.payload_json AS argument_json,
                       COALESCE((
                           SELECT GROUP_CONCAT(DISTINCT e.work_id)
                           FROM candidate_work_evidence e
                           WHERE e.candidate_id=c.candidate_id
                       ), '') AS work_ids
                FROM local_candidates c
                JOIN latest l ON l.candidate_id=c.candidate_id
                JOIN candidate_argument_revisions a
                  ON a.candidate_id=l.candidate_id AND a.revision=l.revision
                WHERE c.area=? AND c.eligibility_status='eligible'
                  AND c.quality_state='eligible'
                  AND c.scientific_contract_version='scientific-principle-v2'
                ORDER BY c.created_at, c.candidate_id
                """,
                (area,),
            ).fetchall()
        return [dict(row) for row in rows]

    def merge_candidate_alias(
        self, *, alias_candidate_id: str, canonical_candidate_id: str
    ) -> None:
        """Hide an equivalent alias while unioning all auditable provenance."""

        if alias_candidate_id == canonical_candidate_id:
            raise ValueError("a Candidate cannot be merged into itself")
        now = utc_now()
        with self.connect() as conn:
            alias = conn.execute(
                "SELECT payload_json FROM local_candidates WHERE candidate_id=?",
                (alias_candidate_id,),
            ).fetchone()
            canonical = conn.execute(
                "SELECT payload_json FROM local_candidates WHERE candidate_id=?",
                (canonical_candidate_id,),
            ).fetchone()
            if alias is None or canonical is None:
                raise KeyError("both alias and canonical Candidates must exist")
            evidence_rows = conn.execute(
                "SELECT * FROM candidate_work_evidence WHERE candidate_id=? ORDER BY evidence_id",
                (alias_candidate_id,),
            ).fetchall()
            for evidence in evidence_rows:
                evidence_id = (
                    "evidence:"
                    + canonical_sha256(
                        {
                            "candidate_id": canonical_candidate_id,
                            "work_id": evidence["work_id"],
                            "segment_id": evidence["segment_id"],
                            "excerpt_sha256": evidence["excerpt_sha256"],
                        }
                    )[:26]
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO candidate_work_evidence(
                        evidence_id, candidate_id, work_id, acquisition_id,
                        segment_id, role, locator_json, excerpt_sha256,
                        extraction_trace_json, visibility, created_at,
                        source_document_id, atom_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        evidence_id,
                        canonical_candidate_id,
                        evidence["work_id"],
                        evidence["acquisition_id"],
                        evidence["segment_id"],
                        evidence["role"],
                        evidence["locator_json"],
                        evidence["excerpt_sha256"],
                        evidence["extraction_trace_json"],
                        evidence["visibility"],
                        evidence["created_at"],
                        evidence["source_document_id"],
                        evidence["atom_id"],
                    ),
                )
            for table, column in (
                ("candidate_atom_links", "atom_id"),
                ("candidate_goal_memberships", "goal_id"),
                ("candidate_source_memberships", "source_id"),
            ):
                conn.execute(
                    f"INSERT OR IGNORE INTO {table}(candidate_id, {column}, created_at) "
                    f"SELECT ?, {column}, created_at FROM {table} WHERE candidate_id=?",
                    (canonical_candidate_id, alias_candidate_id),
                )
            canonical_payload = json.loads(canonical["payload_json"])
            alias_payload = json.loads(alias["payload_json"])
            references = {
                str(item.get("work_id") or ""): item
                for item in canonical_payload.get("source_references") or []
            }
            for item in alias_payload.get("source_references") or []:
                references.setdefault(str(item.get("work_id") or ""), item)
            canonical_payload["source_references"] = [
                references[key] for key in sorted(references) if key
            ]
            source_count = int(
                conn.execute(
                    "SELECT COUNT(DISTINCT work_id) FROM candidate_work_evidence "
                    "WHERE candidate_id=?",
                    (canonical_candidate_id,),
                ).fetchone()[0]
            )
            conn.execute(
                "UPDATE local_candidates SET payload_json=?, content_digest=?, source_count=?, "
                "updated_at=? WHERE candidate_id=?",
                (
                    json.dumps(canonical_payload, ensure_ascii=False, sort_keys=True),
                    canonical_sha256(canonical_payload),
                    source_count,
                    now,
                    canonical_candidate_id,
                ),
            )
            conn.execute(
                "UPDATE local_candidates SET quality_state='merged_alias', "
                "eligibility_status='merged_alias', quarantine_reason=?, "
                "updated_at=? WHERE candidate_id=?",
                (
                    f"equivalent_to:{canonical_candidate_id}",
                    now,
                    alias_candidate_id,
                ),
            )
            conn.execute(
                "DELETE FROM local_principle_fts WHERE principle_id=?",
                (alias_candidate_id,),
            )

    def record_candidate_merge(
        self,
        *,
        alias_candidate_id: str,
        canonical_candidate_id: str,
        fingerprint: str,
        decision: dict[str, Any],
    ) -> None:
        now = utc_now()
        cluster_id = f"cluster:{fingerprint[:26]}"
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO candidate_clusters(
                    cluster_id, canonical_candidate_id, fingerprint, decision,
                    decision_json, created_at, updated_at
                ) VALUES (?, ?, ?, 'equivalent', ?, ?, ?)
                ON CONFLICT(fingerprint) DO UPDATE SET
                    decision_json=excluded.decision_json,
                    updated_at=excluded.updated_at
                """,
                (
                    cluster_id,
                    canonical_candidate_id,
                    fingerprint,
                    json.dumps(decision, ensure_ascii=False, sort_keys=True),
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO candidate_aliases(
                    alias_candidate_id, cluster_id, canonical_candidate_id,
                    payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    alias_candidate_id,
                    cluster_id,
                    canonical_candidate_id,
                    json.dumps(decision, ensure_ascii=False, sort_keys=True),
                    now,
                ),
            )

    def save_scholarly_location(self, payload: dict[str, Any]) -> str:
        location_id = str(
            payload.get("location_id")
            or f"loc:{canonical_sha256({'work_id': payload['work_id'], 'url': payload['url']})[:24]}"
        )
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO scholarly_locations(
                    location_id, work_id, provider, url, access_basis,
                    manuscript_version, license, is_open_access, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    location_id,
                    payload["work_id"],
                    payload.get("provider", ""),
                    payload["url"],
                    payload.get("access_basis", ""),
                    payload.get("manuscript_version", ""),
                    payload.get("license", ""),
                    1 if payload.get("is_open_access") else 0,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    utc_now(),
                ),
            )
        return location_id

    def save_acquisition(self, payload: dict[str, Any]) -> str:
        acquisition_id = str(payload["acquisition_id"])
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO scholarly_acquisitions(
                    acquisition_id, dataset_id, work_id, location_id, status,
                    content_kind, final_url, mime_type, byte_sha256, text_sha256,
                    byte_size, payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dataset_id, work_id) DO UPDATE SET
                    location_id=excluded.location_id, status=excluded.status,
                    content_kind=excluded.content_kind, final_url=excluded.final_url,
                    mime_type=excluded.mime_type, byte_sha256=excluded.byte_sha256,
                    text_sha256=excluded.text_sha256, byte_size=excluded.byte_size,
                    payload_json=excluded.payload_json, updated_at=excluded.updated_at
                """,
                (
                    acquisition_id,
                    payload["dataset_id"],
                    payload["work_id"],
                    payload.get("location_id"),
                    payload.get("status", "usable"),
                    payload.get("content_kind", "abstract"),
                    payload.get("final_url", ""),
                    payload.get("mime_type", "text/plain"),
                    payload.get("byte_sha256", ""),
                    payload.get("text_sha256", ""),
                    int(payload.get("byte_size") or 0),
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    payload.get("created_at", now),
                    now,
                ),
            )
        return acquisition_id

    def replace_segments(
        self, acquisition_id: str, work_id: str, segments: list[dict[str, Any]]
    ) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM scholarly_segments WHERE acquisition_id=?", (acquisition_id,))
            for ordinal, segment in enumerate(segments):
                conn.execute(
                    """
                    INSERT INTO scholarly_segments(
                        segment_id, acquisition_id, segment_key, work_id, ordinal,
                        section, page_start, page_end, text, text_sha256,
                        character_count, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        segment["segment_id"],
                        acquisition_id,
                        segment["segment_key"],
                        work_id,
                        ordinal,
                        segment.get("section", ""),
                        segment.get("page_start"),
                        segment.get("page_end"),
                        segment["text"],
                        segment["text_sha256"],
                        len(segment["text"]),
                        utc_now(),
                    ),
                )

    def save_job_unit(self, payload: dict[str, Any]) -> None:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO v14_job_units(
                    unit_id, job_id, work_id, ordinal, state, attempt_count,
                    checkpoint_json, result_json, error_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(unit_id) DO UPDATE SET state=excluded.state,
                    attempt_count=excluded.attempt_count,
                    checkpoint_json=excluded.checkpoint_json,
                    result_json=excluded.result_json, error_json=excluded.error_json,
                    updated_at=excluded.updated_at
                """,
                (
                    payload["unit_id"],
                    payload["job_id"],
                    payload["work_id"],
                    int(payload["ordinal"]),
                    payload.get("state", "queued"),
                    int(payload.get("attempt_count") or 0),
                    json.dumps(payload.get("checkpoint") or {}, ensure_ascii=False, sort_keys=True),
                    json.dumps(payload.get("result"), ensure_ascii=False, sort_keys=True)
                    if payload.get("result") is not None
                    else None,
                    json.dumps(payload.get("error"), ensure_ascii=False, sort_keys=True)
                    if payload.get("error") is not None
                    else None,
                    payload.get("created_at", now),
                    now,
                ),
            )

    def job_unit_count(self, job_id: str, *, state: str = "") -> int:
        where = " AND state=?" if state else ""
        values: tuple[Any, ...] = (job_id, state) if state else (job_id,)
        with self.connect() as conn:
            return int(
                conn.execute(
                    f"SELECT COUNT(*) FROM v14_job_units WHERE job_id=?{where}", values
                ).fetchone()[0]
            )

    def job_unit_work_ids(self, job_id: str, *, states: tuple[str, ...] = ()) -> list[str]:
        placeholders = ",".join("?" for _ in states)
        state_filter = f" AND state IN ({placeholders})" if states else ""
        values: tuple[Any, ...] = (job_id, *states)
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT work_id FROM v14_job_units
                WHERE job_id=?
                """
                + state_filter
                + " ORDER BY ordinal, unit_id",
                values,
            ).fetchall()
        return list(dict.fromkeys(str(row["work_id"]) for row in rows))

    def list_job_units(self, job_id: str) -> list[dict[str, Any]]:
        """Return redacted, durable per-document outcomes for human recovery."""

        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT u.unit_id, u.work_id, u.ordinal, u.state, u.attempt_count,
                       u.checkpoint_json, u.result_json, u.error_json,
                       u.created_at, u.updated_at,
                       COALESCE(json_extract(w.payload_json, '$.title'), '') AS work_title
                FROM v14_job_units u
                LEFT JOIN works w ON w.id=u.work_id
                WHERE u.job_id=? ORDER BY u.ordinal, u.unit_id
                """,
                (job_id,),
            ).fetchall()
        output: list[dict[str, Any]] = []
        for row in rows:
            checkpoint = json.loads(row["checkpoint_json"] or "{}")
            output.append(
                {
                    "unit_id": str(row["unit_id"]),
                    "work_id": str(row["work_id"]),
                    "work_title": str(row["work_title"] or "Untitled work"),
                    "document_id": str(checkpoint.get("document_id") or ""),
                    "ordinal": int(row["ordinal"]),
                    "state": str(row["state"]),
                    "attempt_count": int(row["attempt_count"]),
                    "stage": str(checkpoint.get("stage") or ""),
                    "result": json.loads(row["result_json"]) if row["result_json"] else None,
                    "error": _redact_diagnostic(json.loads(row["error_json"]))
                    if row["error_json"]
                    else None,
                    "created_at": str(row["created_at"]),
                    "updated_at": str(row["updated_at"]),
                }
            )
        return output

    def save_provider_usage(self, job_id: str, usage: dict[str, int]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO provider_usage(
                    job_id, http_attempts, input_tokens, output_tokens, pro_calls, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    http_attempts=excluded.http_attempts,
                    input_tokens=excluded.input_tokens,
                    output_tokens=excluded.output_tokens,
                    pro_calls=excluded.pro_calls,
                    updated_at=excluded.updated_at
                """,
                (
                    job_id,
                    int(usage.get("http_attempts", 0)),
                    int(usage.get("input_tokens", 0)),
                    int(usage.get("output_tokens", 0)),
                    int(usage.get("pro_calls", 0)),
                    utc_now(),
                ),
            )

    def save_provider_attempt(self, payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO provider_attempts(
                    attempt_id, job_id, unit_id, provider, model, prompt_template,
                    prompt_sha256, input_sha256, output_sha256, state, retry_index,
                    latency_ms, error_category, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["attempt_id"],
                    payload["job_id"],
                    payload.get("unit_id"),
                    payload.get("provider", ""),
                    payload.get("model", ""),
                    payload.get("prompt_template", ""),
                    payload.get("prompt_sha256", ""),
                    payload.get("input_sha256", ""),
                    payload.get("output_sha256", ""),
                    payload.get("state", "succeeded"),
                    int(payload.get("retry_index") or 0),
                    int(payload.get("latency_ms") or 0),
                    payload.get("error_category", ""),
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    utc_now(),
                ),
            )

    def save_literature_search(self, payload: dict[str, Any], *, create_goal: bool = True) -> None:
        now = utc_now()
        search_id = str(payload["search_id"])
        goal_id = "goal:" + hashlib.sha256(search_id.encode("utf-8")).hexdigest()[:26]
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO scholarly_retrieval_runs(
                    search_id, goal, area, target_count, state, payload_json,
                    created_at, updated_at, job_id, result_revision
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(search_id) DO UPDATE SET state=excluded.state,
                    payload_json=excluded.payload_json, updated_at=excluded.updated_at,
                    job_id=excluded.job_id, result_revision=excluded.result_revision
                """,
                (
                    search_id,
                    str(payload["goal"]),
                    str(payload["area"]),
                    int(payload.get("target_count") or 20),
                    str(payload.get("state") or "ready"),
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    str(payload.get("created_at") or now),
                    now,
                    str(payload.get("job_id") or ""),
                    int(payload.get("result_revision") or 0),
                ),
            )
            if not create_goal:
                return
            goal_payload = {
                "goal_id": goal_id,
                "search_id": search_id,
                "goal": str(payload["goal"]),
                "area": str(payload["area"]),
                "source_id": "",
                "status": "active",
            }
            conn.execute(
                """
                INSERT INTO local_research_goals(
                    goal_id, search_id, goal, area, source_id, status,
                    payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, NULL, 'active', ?, ?, ?)
                ON CONFLICT(search_id) DO UPDATE SET goal=excluded.goal,
                    area=excluded.area, status='active',
                    payload_json=excluded.payload_json, updated_at=excluded.updated_at
                """,
                (
                    goal_id,
                    search_id,
                    str(payload["goal"]),
                    str(payload["area"]),
                    json.dumps(goal_payload, ensure_ascii=False, sort_keys=True),
                    str(payload.get("created_at") or now),
                    now,
                ),
            )

    def save_literature_search_task(
        self,
        *,
        search_id: str,
        job_id: str,
        query: str,
        target_count: int,
        deadline_seconds: int,
        state: str,
        checkpoint: dict[str, Any] | None = None,
    ) -> None:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO literature_search_tasks(
                    search_id, job_id, query, target_count, deadline_seconds,
                    state, checkpoint_json, result_revision, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                ON CONFLICT(search_id) DO UPDATE SET
                    job_id=excluded.job_id, state=excluded.state,
                    checkpoint_json=excluded.checkpoint_json,
                    updated_at=excluded.updated_at
                """,
                (
                    search_id,
                    job_id,
                    query,
                    target_count,
                    deadline_seconds,
                    state,
                    json.dumps(checkpoint or {}, ensure_ascii=False, sort_keys=True),
                    now,
                    now,
                ),
            )

    def save_literature_search_revision(
        self, search_id: str, payload: dict[str, Any], *, state: str
    ) -> int:
        now = utc_now()
        logical = _redact_diagnostic(payload)
        digest = canonical_sha256(logical)
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            revision = int(
                conn.execute(
                    "SELECT COALESCE(MAX(revision), 0) + 1 "
                    "FROM literature_search_result_revisions WHERE search_id=?",
                    (search_id,),
                ).fetchone()[0]
            )
            conn.execute(
                """
                INSERT INTO literature_search_result_revisions(
                    search_id, revision, state, provisional_count, result_digest,
                    payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    search_id,
                    revision,
                    state,
                    len(logical.get("results") or []),
                    digest,
                    json.dumps(logical, ensure_ascii=False, sort_keys=True),
                    now,
                ),
            )
            conn.execute(
                "UPDATE literature_search_tasks SET state=?, result_revision=?, "
                "updated_at=? WHERE search_id=?",
                (state, revision, now, search_id),
            )
            conn.commit()
        return revision

    def save_literature_search_attempt(self, payload: dict[str, Any]) -> None:
        safe = _redact_diagnostic(payload)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO literature_search_attempts(
                    attempt_id, search_id, job_id, provider, query_key, status,
                    result_count, retry_after_seconds, latency_ms, error_category,
                    payload_json, started_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    safe["attempt_id"],
                    safe["search_id"],
                    safe.get("job_id") or None,
                    safe.get("provider", ""),
                    safe.get("query_key", ""),
                    safe.get("status", ""),
                    int(safe.get("result_count") or 0),
                    safe.get("retry_after_seconds"),
                    int(safe.get("latency_ms") or 0),
                    safe.get("error_category", ""),
                    json.dumps(safe, ensure_ascii=False, sort_keys=True),
                    safe.get("started_at") or utc_now(),
                    safe.get("completed_at") or utc_now(),
                ),
            )

    def literature_search(self, search_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT r.payload_json, g.goal_id, COALESCE(g.source_id, '') AS source_id
                FROM scholarly_retrieval_runs r
                LEFT JOIN local_research_goals g ON g.search_id=r.search_id
                WHERE r.search_id=?
                """,
                (search_id,),
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["payload_json"])
        payload["goal_id"] = str(row["goal_id"] or "")
        payload["source_id"] = str(row["source_id"] or "")
        return payload

    def list_literature_searches(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT r.payload_json, g.goal_id, COALESCE(g.source_id, '') AS source_id
                FROM scholarly_retrieval_runs r
                LEFT JOIN local_research_goals g ON g.search_id=r.search_id
                ORDER BY r.updated_at DESC, r.search_id LIMIT ?
                """,
                (max(1, min(int(limit), 100)),),
            ).fetchall()
        output: list[dict[str, Any]] = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            payload["goal_id"] = str(row["goal_id"] or "")
            payload["source_id"] = str(row["source_id"] or "")
            output.append(payload)
        return output

    def bind_research_goal_source(self, *, search_id: str, source_id: str) -> str:
        """Bind a metadata search to the folder selected for acquisition."""

        with self.connect() as conn:
            row = conn.execute(
                "SELECT goal_id, payload_json FROM local_research_goals WHERE search_id=?",
                (search_id,),
            ).fetchone()
            if row is None:
                search = conn.execute(
                    "SELECT goal, area, payload_json, created_at FROM scholarly_retrieval_runs "
                    "WHERE search_id=?",
                    (search_id,),
                ).fetchone()
                if search is None:
                    raise KeyError(f"unknown research goal for search: {search_id}")
                goal_id = "goal:" + hashlib.sha256(search_id.encode("utf-8")).hexdigest()[:26]
                payload = {
                    "goal_id": goal_id,
                    "search_id": search_id,
                    "goal": str(search["goal"]),
                    "area": str(search["area"] or ""),
                    "source_id": source_id,
                    "status": "active",
                }
                conn.execute(
                    """
                    INSERT INTO local_research_goals(
                        goal_id, search_id, goal, area, source_id, status,
                        payload_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)
                    """,
                    (
                        goal_id,
                        search_id,
                        str(search["goal"]),
                        str(search["area"] or ""),
                        source_id,
                        json.dumps(payload, ensure_ascii=False, sort_keys=True),
                        str(search["created_at"] or utc_now()),
                        utc_now(),
                    ),
                )
                return goal_id
            payload = json.loads(row["payload_json"])
            payload["source_id"] = source_id
            payload["status"] = "active"
            conn.execute(
                """
                UPDATE local_research_goals
                SET source_id=?, status='active', payload_json=?, updated_at=?
                WHERE search_id=?
                """,
                (
                    source_id,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    utc_now(),
                    search_id,
                ),
            )
        return str(row["goal_id"])

    def backfill_acquired_research_goals(self) -> dict[str, int]:
        """Recover Goal collections from acquired datasets and their exact Works.

        Metadata search alone remains collection-free. Once a user acquires a
        selection into a private folder, that question becomes a durable
        overlapping Library view. Candidate membership follows exact Work
        provenance, so adding another search to the same folder cannot blur the
        two collections.
        """

        with self.connect() as conn:
            datasets = conn.execute(
                """
                SELECT DISTINCT search_id, source_id FROM research_datasets
                WHERE COALESCE(search_id, '')!='' AND COALESCE(source_id, '')!=''
                  AND EXISTS (
                      SELECT 1 FROM dataset_works ready_work
                      WHERE ready_work.dataset_id=research_datasets.dataset_id
                        AND ready_work.selected=1
                        AND ready_work.acquisition_status='usable'
                  )
                ORDER BY search_id, source_id
                """
            ).fetchall()
        created = 0
        for dataset in datasets:
            search_id = str(dataset["search_id"])
            with self.connect() as conn:
                existed = conn.execute(
                    "SELECT 1 FROM local_research_goals WHERE search_id=?", (search_id,)
                ).fetchone()
            self.bind_research_goal_source(
                search_id=search_id, source_id=str(dataset["source_id"])
            )
            created += 0 if existed else 1
        with self.connect() as conn:
            before = int(conn.execute("SELECT COUNT(*) FROM candidate_goal_memberships").fetchone()[0])
            conn.execute(
                """
                INSERT OR IGNORE INTO candidate_goal_memberships(
                    candidate_id, goal_id, created_at
                )
                SELECT DISTINCT e.candidate_id, g.goal_id, ?
                FROM candidate_work_evidence e
                JOIN local_candidates c ON c.candidate_id=e.candidate_id
                JOIN dataset_works dw ON dw.work_id=e.work_id
                  AND dw.selected=1 AND dw.acquisition_status='usable'
                JOIN research_datasets ds ON ds.dataset_id=dw.dataset_id
                JOIN local_research_goals g ON g.search_id=ds.search_id
                  AND g.source_id=ds.source_id
                JOIN candidate_source_memberships sm ON sm.candidate_id=e.candidate_id
                  AND sm.source_id=ds.source_id
                WHERE g.status!='archived' AND c.context_relevance!='outside_focus'
                """,
                (utc_now(),),
            )
            after = int(conn.execute("SELECT COUNT(*) FROM candidate_goal_memberships").fetchone()[0])
        return {"goals_created": created, "memberships_created": after - before}

    def graph_relations_for_principles(self, principle_ids: list[str]) -> list[dict[str, Any]]:
        identifiers = sorted({item for item in principle_ids if item})[:200]
        if not identifiers:
            return []
        placeholders = ",".join("?" for _ in identifiers)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                WITH latest AS (
                    SELECT relation_id, MAX(revision) AS revision
                    FROM principle_relation_revisions GROUP BY relation_id
                )
                SELECT r.relation_id, r.source_principle_id AS source,
                       r.target_principle_id AS target, r.relation_type,
                       r.direction, r.rationale
                FROM principle_relation_revisions r
                JOIN latest USING(relation_id, revision)
                WHERE r.validation_state='validated'
                  AND r.source_principle_id IN ({placeholders})
                  AND r.target_principle_id IN ({placeholders})
                ORDER BY r.relation_type, r.source_principle_id,
                         r.target_principle_id, r.relation_id
                """,
                [*identifiers, *identifiers],
            ).fetchall()
        return [dict(row) for row in rows]

    def resolve_research_goal(
        self,
        *,
        source_id: str,
        goal: str,
        area: str,
        goal_id: str = "",
    ) -> str:
        """Resolve the durable Goal identity or create one for a manual folder.

        Explicit mismatches fail closed so an extraction cannot silently appear
        under the wrong Principles Library collection.
        """

        normalized_goal = " ".join(goal.split())
        now = utc_now()
        with self.connect() as conn:
            if goal_id:
                row = conn.execute(
                    "SELECT goal, area, COALESCE(source_id, '') AS source_id "
                    "FROM local_research_goals WHERE goal_id=? AND status!='archived'",
                    (goal_id,),
                ).fetchone()
                if row is None:
                    raise ValueError("the selected Research Goal no longer exists")
                if (
                    str(row["area"]) != area
                    or " ".join(str(row["goal"]).split()) != normalized_goal
                ):
                    raise ValueError(
                        "the extraction goal does not match the selected Research Goal"
                    )
                if row["source_id"] and str(row["source_id"]) != source_id:
                    raise ValueError("the selected Research Goal belongs to another private folder")
                if not row["source_id"]:
                    conn.execute(
                        "UPDATE local_research_goals SET source_id=?, updated_at=? WHERE goal_id=?",
                        (source_id, now, goal_id),
                    )
                return goal_id

            row = conn.execute(
                """
                SELECT goal_id FROM local_research_goals
                WHERE source_id=? AND goal=? AND status!='archived'
                ORDER BY updated_at DESC, goal_id LIMIT 1
                """,
                (source_id, normalized_goal),
            ).fetchone()
            if row is not None:
                return str(row["goal_id"])

            resolved = (
                "goal:"
                + hashlib.sha256(f"{source_id}\0{area}\0{normalized_goal}".encode()).hexdigest()[
                    :26
                ]
            )
            payload = {
                "goal_id": resolved,
                "search_id": "",
                "goal": normalized_goal,
                "area": area,
                "source_id": source_id,
                "status": "active",
            }
            conn.execute(
                """
                INSERT INTO local_research_goals(
                    goal_id, search_id, goal, area, source_id, status,
                    payload_json, created_at, updated_at
                ) VALUES (?, NULL, ?, ?, ?, 'active', ?, ?, ?)
                ON CONFLICT(goal_id) DO NOTHING
                """,
                (
                    resolved,
                    normalized_goal,
                    area,
                    source_id,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    now,
                    now,
                ),
            )
        return resolved

    def research_goal(self, goal_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT goal_id, goal, area, COALESCE(source_id, '') AS source_id,
                       status, created_at, updated_at
                FROM local_research_goals WHERE goal_id=?
                """,
                (goal_id,),
            ).fetchone()
        return dict(row) if row else None

    def save_dataset(self, payload: dict[str, Any], *, storage_root: str) -> None:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO research_datasets(
                    dataset_id, search_id, goal, area, state, storage_root,
                    payload_json, created_at, updated_at, source_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dataset_id) DO UPDATE SET state=excluded.state,
                    payload_json=excluded.payload_json, updated_at=excluded.updated_at,
                    source_id=excluded.source_id
                """,
                (
                    payload["dataset_id"],
                    payload["search_id"],
                    payload["goal"],
                    payload["area"],
                    payload.get("state", "created"),
                    storage_root,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    payload.get("created_at", now),
                    now,
                    payload.get("source_id", ""),
                ),
            )

    def replace_dataset_works(self, dataset_id: str, works: list[dict[str, Any]]) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM dataset_works WHERE dataset_id=?", (dataset_id,))
            for ordinal, work in enumerate(works):
                conn.execute(
                    """
                    INSERT INTO dataset_works(
                        dataset_id, ordinal, work_id, selected, acquisition_status, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        dataset_id,
                        ordinal,
                        work["work_id"],
                        1 if work.get("selected", True) else 0,
                        work.get("acquisition_status", "pending"),
                        json.dumps(work, ensure_ascii=False, sort_keys=True),
                    ),
                )

    def update_dataset_work_status(self, dataset_id: str, work_id: str, status: str) -> None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM dataset_works WHERE dataset_id=? AND work_id=?",
                (dataset_id, work_id),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown dataset work: {dataset_id}/{work_id}")
            payload = json.loads(row[0])
            payload["acquisition_status"] = status
            conn.execute(
                "UPDATE dataset_works SET acquisition_status=?, payload_json=? "
                "WHERE dataset_id=? AND work_id=?",
                (
                    status,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    dataset_id,
                    work_id,
                ),
            )

    def list_datasets(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM research_datasets "
                "ORDER BY updated_at DESC, dataset_id LIMIT ?",
                (max(1, min(int(limit), 100)),),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def dataset_works(self, dataset_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT dw.payload_json, w.payload_json AS work_json,
                       dw.acquisition_status, dw.ordinal
                FROM dataset_works dw JOIN works w ON w.id=dw.work_id
                WHERE dw.dataset_id=? ORDER BY dw.ordinal
                """,
                (dataset_id,),
            ).fetchall()
        return [
            {
                **json.loads(row["payload_json"]),
                "work": json.loads(row["work_json"]),
                "acquisition_status": row["acquisition_status"],
                "ordinal": row["ordinal"],
            }
            for row in rows
        ]

    def work_detail(self, work_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT payload_json FROM works WHERE id=?", (work_id,)).fetchone()
            if row is None:
                return None
            count = conn.execute(
                "SELECT COUNT(DISTINCT candidate_id) FROM candidate_work_evidence WHERE work_id=?",
                (work_id,),
            ).fetchone()[0]
        payload = json.loads(row[0])
        payload["candidate_count"] = int(count)
        return payload

    def work_candidates(self, work_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT c.candidate_id, c.area, c.title, c.claim,
                       c.eligibility_status, c.assessment_status, c.updated_at
                FROM candidate_work_evidence e
                JOIN local_candidates c ON c.candidate_id=e.candidate_id
                WHERE e.work_id=? ORDER BY c.updated_at DESC, c.candidate_id LIMIT ?
                """,
                (work_id, max(1, min(int(limit), 100))),
            ).fetchall()
        return [dict(row) for row in rows]

    def candidate_work_links(self, candidate_ids: list[str]) -> list[dict[str, str]]:
        """Return evidence memberships for a bounded Candidate set in bulk."""

        identities = sorted(set(candidate_ids))[:500]
        if not identities:
            return []
        output: list[dict[str, str]] = []
        with self.connect() as conn:
            # Stay below SQLite's conservative host-parameter limit on every
            # supported Python/platform combination.
            for start in range(0, len(identities), 400):
                chunk = identities[start : start + 400]
                placeholders = ",".join("?" for _ in chunk)
                rows = conn.execute(
                    f"""
                    SELECT DISTINCT candidate_id, work_id
                    FROM candidate_work_evidence
                    WHERE candidate_id IN ({placeholders})
                    ORDER BY work_id, candidate_id
                    """,
                    chunk,
                ).fetchall()
                output.extend(
                    {"candidate_id": str(row["candidate_id"]), "work_id": str(row["work_id"])}
                    for row in rows
                )
        return sorted(output, key=lambda item: (item["work_id"], item["candidate_id"]))

    def candidate_relation_links(self, candidate_ids: list[str]) -> list[dict[str, Any]]:
        identities = sorted(set(candidate_ids))[:500]
        if not identities:
            return []
        output: list[dict[str, Any]] = []
        with self.connect() as conn:
            for start in range(0, len(identities), 300):
                chunk = identities[start : start + 300]
                placeholders = ",".join("?" for _ in chunk)
                rows = conn.execute(
                    f"""
                    SELECT source_candidate_id, target_principle_id, relation_type,
                           provenance, payload_json
                    FROM local_candidate_relations
                    WHERE source_candidate_id IN ({placeholders})
                    ORDER BY source_candidate_id, relation_index
                    """,
                    chunk,
                ).fetchall()
                output.extend(
                    {
                        "source": str(row["source_candidate_id"]),
                        "target": str(row["target_principle_id"]),
                        "type": str(row["relation_type"]),
                        "provenance": str(row["provenance"]),
                        "relation": json.loads(row["payload_json"]),
                    }
                    for row in rows
                )
        return output

    def relation_inputs(self, *, limit: int = 25_000) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                WITH latest_argument AS (
                    SELECT candidate_id, MAX(revision) AS revision
                    FROM candidate_argument_revisions GROUP BY candidate_id
                )
                SELECT c.candidate_id, c.content_digest, c.updated_at,
                       a.payload_json AS argument_json,
                       COALESCE((
                           SELECT GROUP_CONCAT(DISTINCT e.work_id)
                           FROM candidate_work_evidence e
                           WHERE e.candidate_id=c.candidate_id
                       ), '') AS work_ids
                FROM local_candidates c
                JOIN latest_argument latest ON latest.candidate_id=c.candidate_id
                JOIN candidate_argument_revisions a
                  ON a.candidate_id=latest.candidate_id AND a.revision=latest.revision
                WHERE c.eligibility_status='eligible' AND c.quality_state='eligible'
                ORDER BY c.candidate_id LIMIT ?
                """,
                (max(1, min(int(limit), 100_000)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def replace_validated_relation_set(self, relations: list[dict[str, Any]]) -> dict[str, int]:
        now = utc_now()
        inserted = 0
        superseded = 0
        current_ids = {str(item["relation_id"]) for item in relations}
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            latest_rows = conn.execute(
                """
                SELECT r.* FROM principle_relation_revisions r
                JOIN (
                    SELECT relation_id, MAX(revision) AS revision
                    FROM principle_relation_revisions GROUP BY relation_id
                ) latest USING(relation_id, revision)
                """
            ).fetchall()
            latest = {str(row["relation_id"]): row for row in latest_rows}
            for relation in relations:
                relation_id = str(relation["relation_id"])
                previous = latest.get(relation_id)
                payload_json = json.dumps(relation, ensure_ascii=False, sort_keys=True)
                if (
                    previous is not None
                    and str(previous["validation_state"]) == "validated"
                    and str(previous["payload_json"]) == payload_json
                ):
                    continue
                revision = int(previous["revision"]) + 1 if previous is not None else 1
                self._insert_relation_revision(
                    conn, relation, revision=revision, payload_json=payload_json, now=now
                )
                inserted += 1
            for relation_id, previous in latest.items():
                if (
                    relation_id in current_ids
                    or str(previous["validation_state"]) != "validated"
                    or str(previous["provenance"]) != "deterministic_validated"
                ):
                    continue
                payload = json.loads(str(previous["payload_json"]))
                payload["validation_state"] = "superseded"
                payload["rationale"] = "The current corpus no longer satisfies this relation."
                self._insert_relation_revision(
                    conn,
                    payload,
                    revision=int(previous["revision"]) + 1,
                    payload_json=json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    now=now,
                )
                superseded += 1
            conn.commit()
        return {"inserted": inserted, "superseded": superseded}

    @staticmethod
    def _insert_relation_revision(
        conn: sqlite3.Connection,
        relation: dict[str, Any],
        *,
        revision: int,
        payload_json: str,
        now: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO principle_relation_revisions(
                relation_id, revision, source_principle_id, target_principle_id,
                relation_type, direction, provenance, validation_state, rationale,
                source_version, target_version, evidence_digest, model_trace_json,
                payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                relation["relation_id"],
                revision,
                relation["source_principle_id"],
                relation["target_principle_id"],
                relation["relation_type"],
                relation.get("direction", "directed"),
                relation.get("provenance", "deterministic_validated"),
                relation.get("validation_state", "validated"),
                relation.get("rationale", ""),
                int(relation.get("source_version") or 0),
                int(relation.get("target_version") or 0),
                relation.get("evidence_digest", ""),
                json.dumps(relation.get("model_trace") or {}, sort_keys=True),
                payload_json,
                now,
            ),
        )

    def current_validated_relations(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT r.* FROM principle_relation_revisions r
                JOIN (
                    SELECT relation_id, MAX(revision) AS revision
                    FROM principle_relation_revisions GROUP BY relation_id
                ) latest USING(relation_id, revision)
                WHERE r.validation_state='validated'
                ORDER BY r.source_principle_id, r.target_principle_id,
                         r.relation_type, r.relation_id
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def principle_relations(self, principle_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT r.* FROM principle_relation_revisions r
                JOIN (
                    SELECT relation_id, MAX(revision) AS revision
                    FROM principle_relation_revisions GROUP BY relation_id
                ) latest USING(relation_id, revision)
                WHERE r.validation_state='validated'
                  AND (r.source_principle_id=? OR r.target_principle_id=?)
                ORDER BY r.relation_type, r.source_principle_id,
                         r.target_principle_id, r.relation_id
                """,
                (principle_id, principle_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def principle_relation_previews(
        self, principle_ids: list[str]
    ) -> dict[str, list[dict[str, Any]]]:
        """Return bounded, readable validated-relation previews for Principle cards."""
        identifiers = sorted({item for item in principle_ids if item})
        if not identifiers:
            return {}
        placeholders = ",".join("?" for _ in identifiers)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                WITH latest AS (
                    SELECT relation_id, MAX(revision) AS revision
                    FROM principle_relation_revisions GROUP BY relation_id
                )
                SELECT r.relation_id, r.source_principle_id,
                       r.target_principle_id, r.relation_type,
                       source.title AS source_title, target.title AS target_title
                FROM principle_relation_revisions r
                JOIN latest USING(relation_id, revision)
                LEFT JOIN local_candidates source
                  ON source.candidate_id=r.source_principle_id
                LEFT JOIN local_candidates target
                  ON target.candidate_id=r.target_principle_id
                WHERE r.validation_state='validated'
                  AND (r.source_principle_id IN ({placeholders})
                       OR r.target_principle_id IN ({placeholders}))
                ORDER BY r.relation_type, r.source_principle_id,
                         r.target_principle_id, r.relation_id
                """,
                [*identifiers, *identifiers],
            ).fetchall()
        result: dict[str, list[dict[str, Any]]] = {item: [] for item in identifiers}
        for raw in rows:
            row = dict(raw)
            source_id = str(row["source_principle_id"])
            target_id = str(row["target_principle_id"])
            for principle_id, other_id, other_title, orientation in (
                (source_id, target_id, row.get("target_title"), "outgoing"),
                (target_id, source_id, row.get("source_title"), "incoming"),
            ):
                if principle_id not in result:
                    continue
                result[principle_id].append(
                    {
                        "principle_id": other_id,
                        "title": str(other_title or other_id),
                        "relation_type": str(row["relation_type"]),
                        "orientation": orientation,
                    }
                )
        return result

    def save_relation_metric_snapshot(
        self,
        *,
        corpus_digest: str,
        maximum_neighbor_count: int | None,
        metrics: list[dict[str, Any]],
        payload: dict[str, Any],
    ) -> int:
        now = utc_now()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT metric_revision FROM relation_metric_revisions "
                "WHERE corpus_digest=? AND state='complete'",
                (corpus_digest,),
            ).fetchone()
            if existing is not None:
                conn.rollback()
                return int(existing["metric_revision"])
            cursor = conn.execute(
                """
                INSERT INTO relation_metric_revisions(
                    corpus_digest, state, maximum_neighbor_count, payload_json, created_at
                ) VALUES (?, 'building', ?, ?, ?)
                """,
                (
                    corpus_digest,
                    maximum_neighbor_count,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    now,
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("could not allocate relation metric revision")
            revision = int(cursor.lastrowid)
            for item in metrics:
                conn.execute(
                    """
                    INSERT INTO principle_relation_metrics(
                        metric_revision, principle_id, influence_score,
                        reliability_score, distinct_neighbor_count,
                        incoming_support_count, incoming_contradict_count,
                        payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        revision,
                        item["principle_id"],
                        item.get("influence_score"),
                        item.get("reliability_score"),
                        int(item.get("distinct_neighbor_count") or 0),
                        int(item.get("incoming_support_count") or 0),
                        int(item.get("incoming_contradict_count") or 0),
                        json.dumps(item, ensure_ascii=False, sort_keys=True),
                    ),
                )
            conn.execute(
                "UPDATE relation_metric_revisions SET state='complete' WHERE metric_revision=?",
                (revision,),
            )
            conn.commit()
        return revision

    def relation_metric_status(self) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT metric_revision, corpus_digest, state, maximum_neighbor_count,
                       payload_json, created_at
                FROM relation_metric_revisions
                ORDER BY metric_revision DESC LIMIT 1
                """
            ).fetchone()
        if row is None:
            return {
                "state": "not_built",
                "metric_revision": None,
                "corpus_digest": "",
                "maximum_neighbor_count": None,
                "created_at": "",
            }
        return {
            **dict(row),
            "details": json.loads(row["payload_json"]),
        }

    def principle_card_rows(
        self,
        *,
        limit: int = 100_000,
        offset: int = 0,
        goal_id: str = "",
        source_id: str = "",
        area: str = "",
        quality_states: tuple[str, ...] = ("eligible", "quarantined", "archived"),
        sort: str = "updated",
    ) -> list[dict[str, Any]]:
        clauses = [
            "c.eligibility_status IN ('eligible', 'quarantined', 'archived')",
        ]
        values: list[Any] = []
        if quality_states:
            placeholders = ",".join("?" for _ in quality_states)
            clauses.append(f"c.quality_state IN ({placeholders})")
            values.extend(quality_states)
        if goal_id:
            clauses.append(
                "EXISTS (SELECT 1 FROM candidate_goal_memberships selected_goal "
                "WHERE selected_goal.candidate_id=c.candidate_id "
                "AND selected_goal.goal_id=?)"
            )
            values.append(goal_id)
        if source_id:
            clauses.append(
                "EXISTS (SELECT 1 FROM candidate_source_memberships selected_source "
                "WHERE selected_source.candidate_id=c.candidate_id "
                "AND selected_source.source_id=?)"
            )
            values.append(source_id)
        if area:
            clauses.append(
                "(EXISTS (SELECT 1 FROM candidate_area_assignments selected_area "
                "WHERE selected_area.candidate_id=c.candidate_id "
                "AND selected_area.area=? AND selected_area.state IN ('confirmed','suggested') "
                "AND selected_area.revision=(SELECT MAX(latest_selected_area.revision) "
                "FROM candidate_area_assignments latest_selected_area "
                "WHERE latest_selected_area.candidate_id=selected_area.candidate_id "
                "AND latest_selected_area.area=selected_area.area)) "
                "OR (c.area=? AND NOT EXISTS (SELECT 1 FROM candidate_area_assignments active_area "
                "WHERE active_area.candidate_id=c.candidate_id "
                "AND active_area.state IN ('confirmed','suggested') "
                "AND active_area.revision=(SELECT MAX(latest_active_area.revision) "
                "FROM candidate_area_assignments latest_active_area "
                "WHERE latest_active_area.candidate_id=active_area.candidate_id "
                "AND latest_active_area.area=active_area.area))))"
            )
            values.extend([area, area])
        order_sql = {
            "title": "c.title COLLATE NOCASE ASC, c.candidate_id ASC",
            "supporting_papers": "supporting_work_count DESC, c.candidate_id DESC",
        }.get(sort, "c.updated_at DESC, c.candidate_id DESC")
        where_sql = " AND ".join(clauses)
        values.extend(
            [
                max(1, min(int(limit), 100_000)),
                max(0, int(offset)),
            ]
        )
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                WITH latest_argument AS (
                    SELECT candidate_id, MAX(revision) AS revision
                    FROM candidate_argument_revisions GROUP BY candidate_id
                ), latest_metric AS (
                    SELECT MAX(metric_revision) AS metric_revision
                    FROM relation_metric_revisions WHERE state='complete'
                )
                SELECT c.candidate_id, c.title, c.claim, c.area, c.updated_at,
                       c.assessment_status, c.quality_state, c.source_count, c.source_kind,
                       c.context_relevance, c.extraction_mode,
                       a.claim_class, a.generalization_level,
                       a.payload_json AS argument_json,
                       m.influence_score, m.reliability_score,
                       m.distinct_neighbor_count, m.incoming_support_count,
                       m.incoming_contradict_count,
                       COALESCE((SELECT COUNT(DISTINCT e.work_id)
                                 FROM candidate_work_evidence e
                                 WHERE e.candidate_id=c.candidate_id), 0)
                                 AS supporting_work_count,
                       COALESCE((SELECT COUNT(*) FROM candidate_clause_support s
                                 WHERE s.candidate_id=c.candidate_id), 0)
                                 AS evidence_anchor_count,
                       COALESCE((SELECT GROUP_CONCAT(DISTINCT atom.evidence_type)
                                 FROM evidence_claim_atoms atom
                                 WHERE atom.candidate_id=c.candidate_id), '')
                                 AS evidence_types,
                       COALESCE((SELECT GROUP_CONCAT(gm.goal_id)
                                 FROM candidate_goal_memberships gm
                                 WHERE gm.candidate_id=c.candidate_id), '') AS goal_ids,
                       COALESCE((SELECT GROUP_CONCAT(sm.source_id)
                                 FROM candidate_source_memberships sm
                                 WHERE sm.candidate_id=c.candidate_id), '') AS source_ids,
                       COALESCE((SELECT GROUP_CONCAT(area.area)
                                 FROM candidate_area_assignments area
                                 WHERE area.candidate_id=c.candidate_id
                                   AND area.state IN ('confirmed', 'suggested')
                                   AND area.revision=(
                                       SELECT MAX(latest_area.revision)
                                       FROM candidate_area_assignments latest_area
                                       WHERE latest_area.candidate_id=area.candidate_id
                                         AND latest_area.area=area.area
                                   )), '') AS area_labels
                FROM local_candidates c
                LEFT JOIN latest_argument latest ON latest.candidate_id=c.candidate_id
                LEFT JOIN candidate_argument_revisions a
                  ON a.candidate_id=latest.candidate_id AND a.revision=latest.revision
                LEFT JOIN latest_metric lm ON 1=1
                LEFT JOIN principle_relation_metrics m
                  ON m.metric_revision=lm.metric_revision AND m.principle_id=c.candidate_id
                WHERE {where_sql}
                ORDER BY {order_sql} LIMIT ? OFFSET ?
                """,
                values,
            ).fetchall()
        return [dict(row) for row in rows]

    def count_principle_card_rows(
        self,
        *,
        goal_id: str = "",
        source_id: str = "",
        area: str = "",
        quality_states: tuple[str, ...] = ("eligible", "quarantined", "archived"),
    ) -> int:
        clauses = [
            "c.eligibility_status IN ('eligible', 'quarantined', 'archived')",
        ]
        values: list[Any] = []
        if quality_states:
            placeholders = ",".join("?" for _ in quality_states)
            clauses.append(f"c.quality_state IN ({placeholders})")
            values.extend(quality_states)
        if goal_id:
            clauses.append(
                "EXISTS (SELECT 1 FROM candidate_goal_memberships selected_goal "
                "WHERE selected_goal.candidate_id=c.candidate_id "
                "AND selected_goal.goal_id=?)"
            )
            values.append(goal_id)
        if source_id:
            clauses.append(
                "EXISTS (SELECT 1 FROM candidate_source_memberships selected_source "
                "WHERE selected_source.candidate_id=c.candidate_id "
                "AND selected_source.source_id=?)"
            )
            values.append(source_id)
        if area:
            clauses.append(
                "(EXISTS (SELECT 1 FROM candidate_area_assignments selected_area "
                "WHERE selected_area.candidate_id=c.candidate_id "
                "AND selected_area.area=? AND selected_area.state IN ('confirmed','suggested') "
                "AND selected_area.revision=(SELECT MAX(latest_selected_area.revision) "
                "FROM candidate_area_assignments latest_selected_area "
                "WHERE latest_selected_area.candidate_id=selected_area.candidate_id "
                "AND latest_selected_area.area=selected_area.area)) "
                "OR (c.area=? AND NOT EXISTS (SELECT 1 FROM candidate_area_assignments active_area "
                "WHERE active_area.candidate_id=c.candidate_id "
                "AND active_area.state IN ('confirmed','suggested') "
                "AND active_area.revision=(SELECT MAX(latest_active_area.revision) "
                "FROM candidate_area_assignments latest_active_area "
                "WHERE latest_active_area.candidate_id=active_area.candidate_id "
                "AND latest_active_area.area=active_area.area))))"
            )
            values.extend([area, area])
        with self.connect() as conn:
            row = conn.execute(
                f"SELECT COUNT(*) FROM local_candidates c WHERE {' AND '.join(clauses)}",
                values,
            ).fetchone()
        return int(row[0])

    def principle_card_facets(
        self,
        *,
        goal_id: str = "",
        source_id: str = "",
        area: str = "",
        quality_states: tuple[str, ...] = ("eligible", "quarantined", "archived"),
    ) -> dict[str, Any]:
        """Aggregate complete collection facets without materializing every card."""

        clauses = ["c.eligibility_status IN ('eligible', 'quarantined', 'archived')"]
        values: list[Any] = []
        if quality_states:
            placeholders = ",".join("?" for _ in quality_states)
            clauses.append(f"c.quality_state IN ({placeholders})")
            values.extend(quality_states)
        if goal_id:
            clauses.append(
                "EXISTS (SELECT 1 FROM candidate_goal_memberships selected_goal "
                "WHERE selected_goal.candidate_id=c.candidate_id "
                "AND selected_goal.goal_id=?)"
            )
            values.append(goal_id)
        if source_id:
            clauses.append(
                "EXISTS (SELECT 1 FROM candidate_source_memberships selected_source "
                "WHERE selected_source.candidate_id=c.candidate_id "
                "AND selected_source.source_id=?)"
            )
            values.append(source_id)
        if area:
            clauses.append(
                "(EXISTS (SELECT 1 FROM candidate_area_assignments selected_area "
                "WHERE selected_area.candidate_id=c.candidate_id "
                "AND selected_area.area=? AND selected_area.state IN ('confirmed','suggested') "
                "AND selected_area.revision=(SELECT MAX(latest_selected_area.revision) "
                "FROM candidate_area_assignments latest_selected_area "
                "WHERE latest_selected_area.candidate_id=selected_area.candidate_id "
                "AND latest_selected_area.area=selected_area.area)) "
                "OR (c.area=? AND NOT EXISTS (SELECT 1 FROM candidate_area_assignments active_area "
                "WHERE active_area.candidate_id=c.candidate_id "
                "AND active_area.state IN ('confirmed','suggested') "
                "AND active_area.revision=(SELECT MAX(latest_active_area.revision) "
                "FROM candidate_area_assignments latest_active_area "
                "WHERE latest_active_area.candidate_id=active_area.candidate_id "
                "AND latest_active_area.area=active_area.area))))"
            )
            values.extend([area, area])
        where_sql = " AND ".join(clauses)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                WITH base AS (
                    SELECT c.* FROM local_candidates c WHERE {where_sql}
                ), latest_argument AS (
                    SELECT candidate_id, MAX(revision) AS revision
                    FROM candidate_argument_revisions GROUP BY candidate_id
                ), latest_metric AS (
                    SELECT MAX(metric_revision) AS metric_revision
                    FROM relation_metric_revisions WHERE state='complete'
                ), current_areas AS (
                    SELECT assignment.candidate_id, assignment.area
                    FROM candidate_area_assignments assignment
                    JOIN base ON base.candidate_id=assignment.candidate_id
                    WHERE assignment.state IN ('confirmed','suggested')
                      AND assignment.revision=(
                        SELECT MAX(latest.revision)
                        FROM candidate_area_assignments latest
                        WHERE latest.candidate_id=assignment.candidate_id
                          AND latest.area=assignment.area
                      )
                    UNION
                    SELECT base.candidate_id, base.area FROM base
                    WHERE base.area NOT IN ('', 'uncategorized')
                      AND NOT EXISTS (
                        SELECT 1 FROM candidate_area_assignments assignment
                        WHERE assignment.candidate_id=base.candidate_id
                          AND assignment.state IN ('confirmed','suggested')
                          AND assignment.revision=(
                            SELECT MAX(latest.revision)
                            FROM candidate_area_assignments latest
                            WHERE latest.candidate_id=assignment.candidate_id
                              AND latest.area=assignment.area
                          )
                      )
                )
                SELECT 'area' AS facet, area AS value, COUNT(DISTINCT candidate_id) AS count
                FROM current_areas GROUP BY area
                UNION ALL
                SELECT 'claim_type', argument.claim_class, COUNT(*)
                FROM base JOIN latest_argument latest USING(candidate_id)
                JOIN candidate_argument_revisions argument
                  ON argument.candidate_id=latest.candidate_id
                 AND argument.revision=latest.revision
                GROUP BY argument.claim_class
                UNION ALL
                SELECT 'evidence_status',
                  CASE base.quality_state
                    WHEN 'eligible' THEN 'checks_passed'
                    WHEN 'quarantined' THEN 'held_back'
                    WHEN 'pending_challenge' THEN 'checking'
                    WHEN 'archived' THEN 'archived'
                    ELSE 'update_required'
                  END, COUNT(*)
                FROM base GROUP BY 2
                UNION ALL
                SELECT 'human_review',
                  CASE WHEN base.assessment_status='reviewed' THEN 'reviewed'
                       WHEN base.assessment_status='rejected' THEN 'rejected'
                       ELSE 'pending' END, COUNT(*)
                FROM base GROUP BY 2
                UNION ALL
                SELECT 'metric', 'reliability', COUNT(*)
                FROM base JOIN latest_metric ON 1=1
                JOIN principle_relation_metrics metric
                  ON metric.metric_revision=latest_metric.metric_revision
                 AND metric.principle_id=base.candidate_id
                WHERE metric.reliability_score IS NOT NULL
                UNION ALL
                SELECT 'metric', 'influence', COUNT(*)
                FROM base JOIN latest_metric ON 1=1
                JOIN principle_relation_metrics metric
                  ON metric.metric_revision=latest_metric.metric_revision
                 AND metric.principle_id=base.candidate_id
                WHERE metric.influence_score IS NOT NULL
                UNION ALL
                SELECT 'metric', 'contradiction', COUNT(*)
                FROM base JOIN latest_metric ON 1=1
                JOIN principle_relation_metrics metric
                  ON metric.metric_revision=latest_metric.metric_revision
                 AND metric.principle_id=base.candidate_id
                WHERE metric.incoming_contradict_count>0
                """,
                values,
            ).fetchall()
        grouped: dict[str, dict[str, int]] = {}
        for row in rows:
            grouped.setdefault(str(row["facet"]), {})[str(row["value"])] = int(row["count"])
        area_counts = grouped.get("area", {})
        claim_counts = grouped.get("claim_type", {})
        evidence_counts = grouped.get("evidence_status", {})
        review_counts = grouped.get("human_review", {})
        metric_counts = grouped.get("metric", {})
        return {
            "areas": sorted(area_counts),
            "area_counts": dict(sorted(area_counts.items())),
            "claim_types": sorted(claim_counts),
            "claim_type_counts": dict(sorted(claim_counts.items())),
            "evidence_statuses": sorted(evidence_counts),
            "evidence_status_counts": dict(sorted(evidence_counts.items())),
            "human_review_statuses": sorted(review_counts),
            "human_review_status_counts": dict(sorted(review_counts.items())),
            "reliability_available_count": metric_counts.get("reliability", 0),
            "influence_available_count": metric_counts.get("influence", 0),
            "known_contradiction_count": metric_counts.get("contradiction", 0),
        }

    def repair_generated_candidate_titles(self) -> int:
        """Replace claim-copy titles while preserving deliberate human edits."""

        repaired = 0
        with self.connect() as conn:
            rows = conn.execute(
                """
                WITH latest AS (
                    SELECT candidate_id, MAX(revision) AS revision
                    FROM candidate_argument_revisions GROUP BY candidate_id
                )
                SELECT c.candidate_id, c.title, c.claim, c.payload_json,
                       a.payload_json AS argument_json
                FROM local_candidates c
                JOIN latest l ON l.candidate_id=c.candidate_id
                JOIN candidate_argument_revisions a
                  ON a.candidate_id=l.candidate_id AND a.revision=l.revision
                WHERE NOT EXISTS (
                    SELECT 1 FROM v14_events e
                    WHERE e.aggregate_type='candidate'
                      AND e.aggregate_id=c.candidate_id
                      AND e.operation='edit_display_title'
                )
                ORDER BY c.candidate_id
                """
            ).fetchall()
            for row in rows:
                stored = " ".join(str(row["title"] or "").split())
                argument = json.loads(str(row["argument_json"]))
                # Portable/public showcase snapshots deliberately contain only a
                # bounded argument projection.  Never replace their curated
                # display titles with a generic title derived from missing
                # internal slots.
                if not all(
                    str(argument.get(key) or "").strip()
                    for key in ("subject_system", "driver_or_intervention", "outcome")
                ):
                    continue
                title = concise_principle_title(argument)
                if not title or title.casefold() == stored.casefold():
                    continue
                payload = json.loads(str(row["payload_json"]))
                before = {"title": stored, "content_digest": canonical_sha256(payload)}
                payload["title"] = title
                digest = canonical_sha256(payload)
                conn.execute(
                    "UPDATE local_candidates SET title=?, payload_json=?, content_digest=? "
                    "WHERE candidate_id=?",
                    (
                        title,
                        json.dumps(payload, ensure_ascii=False, sort_keys=True),
                        digest,
                        row["candidate_id"],
                    ),
                )
                conn.execute(
                    "UPDATE local_principle_fts SET title=? WHERE principle_id=? AND version=0",
                    (title, row["candidate_id"]),
                )
                self._append_mutation_event(
                    conn,
                    aggregate_type="candidate",
                    aggregate_id=str(row["candidate_id"]),
                    operation="normalize_generated_title",
                    before=before,
                    after={"title": title, "content_digest": digest},
                )
                repaired += 1
        return repaired

    def save_job(self, job: JobRecord) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO v14_jobs(
                    job_id, kind, state, stage, progress, provider, model,
                    payload_json, created_at, updated_at, completed_units,
                    total_units, elapsed_seconds, eta_seconds, last_activity_at,
                    status_message, retry_after_seconds
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET state=excluded.state,
                    stage=excluded.stage, progress=excluded.progress,
                    payload_json=excluded.payload_json, updated_at=excluded.updated_at,
                    completed_units=excluded.completed_units,
                    total_units=excluded.total_units,
                    elapsed_seconds=excluded.elapsed_seconds,
                    eta_seconds=excluded.eta_seconds,
                    last_activity_at=excluded.last_activity_at,
                    status_message=excluded.status_message,
                    retry_after_seconds=excluded.retry_after_seconds
                """,
                (
                    job.job_id,
                    job.kind,
                    job.state,
                    job.stage,
                    job.progress,
                    job.provider,
                    job.model,
                    job.model_dump_json(),
                    job.created_at,
                    job.updated_at,
                    job.completed_units,
                    job.total_units,
                    job.elapsed_seconds,
                    job.eta_seconds,
                    job.last_activity_at,
                    job.status_message,
                    job.retry_after_seconds,
                ),
            )

    def heartbeat_job(self, job_id: str, *, elapsed_seconds: float) -> None:
        """Advance time/activity without overwriting concurrent job progress."""

        now = utc_now()
        elapsed = max(0.0, round(float(elapsed_seconds), 1))
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE v14_jobs
                SET elapsed_seconds=?, last_activity_at=?, updated_at=?,
                    payload_json=json_set(
                        payload_json,
                        '$.elapsed_seconds', ?,
                        '$.last_activity_at', ?,
                        '$.updated_at', ?
                    )
                WHERE job_id=?
                  AND state NOT IN ('succeeded','failed','cancelled','interrupted')
                """,
                (elapsed, now, now, elapsed, now, now, job_id),
            )

    def get_job(self, job_id: str) -> JobRecord | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM v14_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
        return JobRecord.model_validate_json(row[0]) if row else None

    def list_jobs(self, *, kind: str = "", limit: int = 50) -> list[JobRecord]:
        where = " WHERE kind=?" if kind else ""
        values: tuple[Any, ...] = (kind,) if kind else ()
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT payload_json FROM v14_jobs{where} "
                "ORDER BY updated_at DESC, job_id LIMIT ?",
                (*values, max(1, min(int(limit), 100))),
            ).fetchall()
        return [JobRecord.model_validate_json(row[0]) for row in rows]

    def active_jobs(self) -> list[JobRecord]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM v14_jobs "
                "WHERE state NOT IN ('succeeded','failed','cancelled','interrupted') "
                "ORDER BY updated_at DESC, job_id"
            ).fetchall()
        return [JobRecord.model_validate_json(row[0]) for row in rows]

    def append_job_event(
        self, job_id: str, event_type: str, payload: dict[str, Any], *, event_id: str
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO v14_job_events(
                    event_id, job_id, event_type, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    job_id,
                    event_type,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    utc_now(),
                ),
            )

    def job_events(self, job_id: str, *, after: int = 0, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT sequence, event_id, event_type, payload_json, created_at
                FROM v14_job_events WHERE job_id=? AND sequence>?
                ORDER BY sequence LIMIT ?
                """,
                (job_id, max(0, int(after)), max(1, min(int(limit), 100))),
            ).fetchall()
        return [
            {
                "sequence": row["sequence"],
                "event_id": row["event_id"],
                "event_type": row["event_type"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def interrupt_orphaned_jobs(self) -> int:
        now = utc_now()
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT job_id, payload_json FROM v14_jobs "
                "WHERE state IN ('queued', 'running', 'cancelling')"
            ).fetchall()
            for row in rows:
                job = JobRecord.model_validate_json(row["payload_json"])
                job.state = "interrupted"
                job.stage = "interrupted"
                job.updated_at = now
                conn.execute(
                    "UPDATE v14_jobs SET state='interrupted', stage='interrupted', "
                    "payload_json=?, updated_at=? WHERE job_id=?",
                    (job.model_dump_json(), now, job.job_id),
                )
                if job.kind == "literature_search":
                    conn.execute(
                        "UPDATE literature_search_tasks SET state='interrupted', "
                        "updated_at=? WHERE job_id=?",
                        (now, job.job_id),
                    )
        return len(rows)

    def reconcile_misreported_extraction_jobs(self) -> int:
        """Correct legacy all-failed extraction runs that were labelled successful."""

        corrected = 0
        now = utc_now()
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT job_id, payload_json FROM v14_jobs "
                "WHERE kind='local_extraction' AND state='succeeded'"
            ).fetchall()
            for row in rows:
                job = JobRecord.model_validate_json(str(row["payload_json"]))
                result = job.result or {}
                failed = int(result.get("failed_documents") or 0)
                processed = int(result.get("processed_documents") or 0)
                if failed <= 0 or processed > 0:
                    continue
                job.state = "failed"
                job.stage = "Needs attention"
                job.status_message = f"No papers were processed; {failed} need attention"
                job.error = {
                    "code": "local_extraction_failed",
                    "category": "provider",
                    "message": (
                        "This run did not process any selected paper. Correct the provider "
                        "configuration, then retry the failed papers."
                    ),
                    "retryable": True,
                }
                job.updated_at = now
                job.last_activity_at = now
                conn.execute(
                    "UPDATE v14_jobs SET state=?, stage=?, status_message=?, payload_json=?, "
                    "updated_at=?, last_activity_at=? WHERE job_id=?",
                    (
                        job.state,
                        job.stage,
                        job.status_message,
                        job.model_dump_json(),
                        now,
                        now,
                        job.job_id,
                    ),
                )
                conn.execute(
                    "INSERT INTO v14_job_events(event_id, job_id, event_type, payload_json, created_at) "
                    "VALUES (?, ?, 'corrected', ?, ?)",
                    (
                        f"event:{uuid.uuid4().hex}",
                        job.job_id,
                        json.dumps(
                            {
                                "stage": job.stage,
                                "message": job.status_message,
                                "reason": "all document units failed",
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        now,
                    ),
                )
                corrected += 1
        return corrected

    def acquire_runtime_lease(self, workspace_key: str = "primary") -> str | None:
        """Acquire the single-runtime reconciliation lease.

        A live process that already owns the workspace prevents a second
        runtime from marking its jobs interrupted. A dead owner is replaced in
        one immediate transaction.
        """

        now_dt = datetime.now(timezone.utc)
        now = now_dt.replace(microsecond=0).isoformat()
        expires = (now_dt + timedelta(minutes=5)).replace(microsecond=0).isoformat()
        process_id = os.getpid()
        lease_id = f"lease:{uuid.uuid4().hex}"
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT lease_id, process_id FROM workspace_runtime_leases WHERE workspace_key=?",
                (workspace_key,),
            ).fetchone()
            if row is not None and self._process_is_alive(int(row["process_id"])):
                conn.rollback()
                return None
            conn.execute(
                """
                INSERT INTO workspace_runtime_leases(
                    workspace_key, lease_id, process_id, acquired_at,
                    heartbeat_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(workspace_key) DO UPDATE SET
                    lease_id=excluded.lease_id,
                    process_id=excluded.process_id,
                    acquired_at=excluded.acquired_at,
                    heartbeat_at=excluded.heartbeat_at,
                    expires_at=excluded.expires_at
                """,
                (workspace_key, lease_id, process_id, now, now, expires),
            )
            conn.commit()
        return lease_id

    def release_runtime_lease(self, lease_id: str, workspace_key: str = "primary") -> bool:
        """Release only the lease owned by this runtime instance."""

        with self.connect() as conn:
            cursor = conn.execute(
                "DELETE FROM workspace_runtime_leases "
                "WHERE workspace_key=? AND lease_id=? AND process_id=?",
                (workspace_key, lease_id, os.getpid()),
            )
        return cursor.rowcount == 1

    @staticmethod
    def _process_is_alive(process_id: int) -> bool:
        if process_id <= 0:
            return False
        try:
            os.kill(process_id, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False
        return True

    def create_scenario(self, scenario: ScenarioRecord) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO scenarios VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    scenario.scenario_id,
                    scenario.name,
                    scenario.base_content_digest,
                    scenario.parent_scenario_id,
                    scenario.status,
                    scenario.created_at,
                    scenario.updated_at,
                ),
            )

    def append_scenario_event(self, event: ScenarioEvent) -> None:
        with self.connect() as conn:
            expected = conn.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM scenario_events WHERE scenario_id=?",
                (event.scenario_id,),
            ).fetchone()[0]
            if event.sequence != expected:
                raise ValueError(f"scenario event sequence must be {expected}")
            conn.execute(
                "INSERT INTO scenario_events VALUES (?, ?, ?, ?, ?, ?)",
                (
                    event.event_id,
                    event.scenario_id,
                    event.sequence,
                    event.event_type,
                    json.dumps(event.payload, ensure_ascii=False, sort_keys=True),
                    event.created_at,
                ),
            )

    def scenario_events(self, scenario_id: str) -> list[ScenarioEvent]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM scenario_events WHERE scenario_id=? ORDER BY sequence",
                (scenario_id,),
            ).fetchall()
        return [
            ScenarioEvent(
                event_id=row["event_id"],
                scenario_id=row["scenario_id"],
                sequence=row["sequence"],
                event_type=row["event_type"],
                payload=json.loads(row["payload_json"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def list_scenarios(self) -> list[ScenarioRecord]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM scenarios ORDER BY updated_at DESC").fetchall()
        return [ScenarioRecord.model_validate(dict(row)) for row in rows]

    def scenario(self, scenario_id: str) -> ScenarioRecord | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM scenarios WHERE scenario_id=?", (scenario_id,)
            ).fetchone()
        return ScenarioRecord.model_validate(dict(row)) if row else None

    def discard_scenario(self, scenario_id: str) -> None:
        now = utc_now()
        with self.connect() as conn:
            changed = conn.execute(
                "UPDATE scenarios SET status='discarded', updated_at=? WHERE scenario_id=?",
                (now, scenario_id),
            ).rowcount
        if not changed:
            raise KeyError(f"unknown scenario: {scenario_id}")

    def enqueue_review(self, candidate: CandidatePrinciple) -> None:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO admin_review_queue(
                    candidate_id, status, payload_json, decision_json, created_at, updated_at
                ) VALUES (?, 'pending', ?, NULL, ?, ?)
                ON CONFLICT(candidate_id) DO UPDATE SET payload_json=excluded.payload_json,
                    status='pending', decision_json=NULL, updated_at=excluded.updated_at
                """,
                (candidate.candidate_id, candidate.model_dump_json(), now, now),
            )

    def review_queue(self, *, status: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM admin_review_queue"
        values: tuple[Any, ...] = ()
        if status:
            sql += " WHERE status=?"
            values = (status,)
        sql += " ORDER BY updated_at DESC, candidate_id"
        with self.connect() as conn:
            rows = conn.execute(sql, values).fetchall()
        return [
            {
                "candidate": json.loads(row["payload_json"]),
                "status": row["status"],
                "decision": json.loads(row["decision_json"]) if row["decision_json"] else None,
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def decide_review(self, candidate_id: str, status: str, decision: dict[str, Any]) -> None:
        now = utc_now()
        with self.connect() as conn:
            changed = conn.execute(
                """
                UPDATE admin_review_queue SET status=?, decision_json=?, updated_at=?
                WHERE candidate_id=?
                """,
                (
                    status,
                    json.dumps(decision, ensure_ascii=False, sort_keys=True),
                    now,
                    candidate_id,
                ),
            ).rowcount
        if not changed:
            raise KeyError(f"unknown review candidate: {candidate_id}")

    def save_changeset(self, changeset: PublicationChangeset, *, status: str = "draft") -> None:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO publication_changesets(
                    changeset_id, area, status, expected_content_digest,
                    payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(changeset_id) DO UPDATE SET status=excluded.status,
                    payload_json=excluded.payload_json, updated_at=excluded.updated_at
                """,
                (
                    changeset.changeset_id,
                    changeset.area,
                    status,
                    changeset.expected_content_digest,
                    changeset.model_dump_json(),
                    changeset.created_at,
                    now,
                ),
            )

    def changeset(self, changeset_id: str) -> PublicationChangeset | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM publication_changesets WHERE changeset_id=?",
                (changeset_id,),
            ).fetchone()
        return PublicationChangeset.model_validate_json(row[0]) if row else None

    def canonical_content_digest(self) -> str:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM local_principles ORDER BY principle_id, version"
            ).fetchall()
        return canonical_sha256([json.loads(row[0]) for row in rows])

    def v14_counts(self) -> dict[str, int]:
        names = {
            "local_candidates": "local_candidates",
            "eligible_candidates": "local_candidates WHERE eligibility_status='eligible'",
            "quarantined_candidates": "local_candidates WHERE eligibility_status='quarantined'",
            "local_principles": "local_principles",
            "literature_searches": "scholarly_retrieval_runs",
            "research_datasets": "research_datasets",
            "candidate_evidence_links": "candidate_work_evidence",
            "eligible_candidate_evidence_links": (
                "candidate_work_evidence e JOIN local_candidates c "
                "ON c.candidate_id=e.candidate_id WHERE c.eligibility_status='eligible'"
            ),
            "jobs": "v14_jobs",
        }
        with self.connect() as conn:
            return {
                label: int(conn.execute(f"SELECT COUNT(*) FROM {source}").fetchone()[0])
                for label, source in names.items()
            }
