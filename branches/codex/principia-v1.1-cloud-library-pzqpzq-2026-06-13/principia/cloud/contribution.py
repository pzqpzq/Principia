from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ..models import utc_now
from ..utils import stable_id
from .auth import check_admin_key
from . import CONTRIBUTION_SCHEMA_VERSION
from .resolver import CloudResolver
from .validator import validate_contribution


def prepare_contribution(
    db_path: Path,
    out_dir: Path,
    *,
    model_key: str = "",
    work_ids: list[str] | None = None,
    created_by: dict[str, Any] | None = None,
    upload_mode: str = "normal",
    admin_key: str = "",
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    auth = check_admin_key(admin_key, purpose="cloud_upload")
    upload_mode = upload_mode if upload_mode in {"normal", "force"} else "normal"
    requested_work_ids = work_ids or []
    decisions = evaluate_upload_candidates(db_path, requested_work_ids, model_key=model_key, upload_mode=upload_mode)
    allowed_work_ids = [item["work_id"] for item in decisions if item.get("upload_allowed")]
    export_work_ids = allowed_work_ids if allowed_work_ids else ["__principia_no_allowed_work__"]
    contribution = export_contribution(
        db_path,
        model_key=model_key,
        work_ids=export_work_ids,
        created_by=created_by,
        upload_mode=upload_mode,
        upload_decisions=decisions,
        upload_authorization=auth,
    )
    validation = validate_contribution(contribution)
    path = out_dir / f"{contribution['contribution_id']}.json"
    path.write_text(json.dumps(contribution, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return {
        "ok": validation["ok"] and bool(allowed_work_ids),
        "path": str(path),
        "contribution_id": contribution["contribution_id"],
        "validation": validation,
        "authorization": auth,
        "upload_mode": upload_mode,
        "upload_decisions": decisions,
        "allowed_work_ids": allowed_work_ids,
        "rejected_work_ids": [item["work_id"] for item in decisions if not item.get("upload_allowed")],
        "instructions": [
            "Review the generated contribution JSON.",
            "Open a branch or PR that adds it under cloud/contributions/ or hand it to the maintainer workflow.",
            "GitHub Actions will validate and compact it into release assets.",
        ],
    }


def export_contribution(
    db_path: Path,
    *,
    model_key: str = "",
    work_ids: list[str] | None = None,
    created_by: dict[str, Any] | None = None,
    upload_mode: str = "normal",
    upload_decisions: list[dict[str, Any]] | None = None,
    upload_authorization: dict[str, Any] | None = None,
) -> dict[str, Any]:
    work_ids = work_ids or []
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        works = _rows(conn, "SELECT * FROM global_work" + _where_work_ids(work_ids), work_ids)
        versions = _rows(conn, "SELECT * FROM work_version" + _where_work_ids(work_ids), work_ids)
        extractions = _rows(conn, "SELECT * FROM extraction_run" + _where_work_ids(work_ids), work_ids)
        evidence = _rows(conn, "SELECT * FROM evidence_link" + _where_work_ids(work_ids), work_ids)
        concept_ids = sorted({str(row.get("concept_id") or "") for row in evidence if row.get("concept_id")})
        concepts = _rows(conn, "SELECT * FROM concept_card" + _where_concept_ids(concept_ids), concept_ids)
        concept_versions = _rows(conn, "SELECT * FROM concept_version" + _where_concept_ids(concept_ids), concept_ids)
    concept_payloads = {row["concept_version_id"]: _loads(row.get("payload_json", "{}")) for row in concept_versions}
    contribution_id = stable_id("CONTRIB", utc_now(), model_key, ",".join(work_ids))
    return {
        "schema_version": CONTRIBUTION_SCHEMA_VERSION,
        "contribution_id": contribution_id,
        "created_at": utc_now(),
        "created_by": created_by or {},
        "upload_mode": upload_mode if upload_mode in {"normal", "force"} else "normal",
        "model_key": model_key,
        "upload_decisions": upload_decisions or [],
        "upload_authorization": _public_auth(upload_authorization or {}),
        "work_records": [_public_work(row) for row in works],
        "work_version_records": [_public_work_version(row) for row in versions],
        "extraction_records": [_public_extraction(row, model_key=model_key) for row in extractions],
        "concept_records": [_public_concept(row, concept_payloads) for row in concepts],
        "relation_records": [],
        "evidence_records": [_public_evidence(row) for row in evidence],
        "admin_operations": [],
        "provenance": {"principia_version": "1.1.0", "prompt_version": "principia-work-extract-v1"},
    }


def evaluate_upload_candidates(db_path: Path, work_ids: list[str] | None, *, model_key: str = "", upload_mode: str = "normal") -> list[dict[str, Any]]:
    work_ids = work_ids or []
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        works = _rows(conn, "SELECT * FROM global_work" + _where_work_ids(work_ids), work_ids)
        versions = _latest_versions(conn, [row["work_id"] for row in works])
    candidates = [_candidate_for_upload(row, versions.get(row["work_id"])) for row in works]
    if not candidates:
        return []
    decisions = CloudResolver(_StoreRef(db_path)).resolve_batch(candidates, model_key, hydrate=False)
    by_candidate = {str(item.get("candidate_work_id") or ""): item for item in decisions}
    output = []
    for candidate in candidates:
        decision = by_candidate.get(str(candidate.get("work_id") or ""), {})
        reason = str(decision.get("decision") or "not_in_cloud")
        allowed = upload_mode == "force" or reason in {
            "not_in_cloud",
            "cloud_empty",
            "model_version_missing",
            "source_newer_than_cloud",
            "abstract_hash_changed",
            "content_hash_changed",
        }
        output.append(
            {
                "work_id": candidate.get("work_id") or "",
                "title": candidate.get("title") or "",
                "cloud_work_id": decision.get("work_id") or "",
                "cloud_decision": "force_upload" if upload_mode == "force" else reason,
                "upload_allowed": bool(allowed),
                "upload_mode": upload_mode,
            }
        )
    return output


def log_upload_status(db_path: Path, *, contribution_path: str, status: str, github_pr_url: str = "", upload_mode: str = "normal") -> dict[str, Any]:
    upload_id = stable_id("UPLOAD", contribution_path, utc_now())
    with sqlite3.connect(db_path, timeout=30) as conn:
        conn.execute(
            """
            INSERT INTO cloud_upload_log(
                upload_id, contribution_path, github_pr_url, upload_mode,
                status, created_at, completed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (upload_id, contribution_path, github_pr_url, upload_mode, status, utc_now(), utc_now() if status in {"prepared", "submitted"} else None),
        )
    return {"upload_id": upload_id, "status": status, "contribution_path": contribution_path, "github_pr_url": github_pr_url}


def upload_status(db_path: Path, upload_id: str = "") -> dict[str, Any]:
    with sqlite3.connect(db_path, timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        if upload_id:
            row = conn.execute("SELECT * FROM cloud_upload_log WHERE upload_id = ?", (upload_id,)).fetchone()
            return {"item": dict(row) if row else None}
        return {"items": [dict(row) for row in conn.execute("SELECT * FROM cloud_upload_log ORDER BY created_at DESC LIMIT 100").fetchall()]}


def _where_work_ids(work_ids: list[str]) -> str:
    return " WHERE work_id IN (%s)" % ",".join("?" for _ in work_ids) if work_ids else ""


def _where_concept_ids(concept_ids: list[str]) -> str:
    return " WHERE concept_id IN (%s)" % ",".join("?" for _ in concept_ids) if concept_ids else " WHERE 1 = 0"


def _rows(conn: sqlite3.Connection, sql: str, params: list[str] | None = None) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, params or []).fetchall()]


def _latest_versions(conn: sqlite3.Connection, work_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not work_ids:
        return {}
    rows = _rows(
        conn,
        "SELECT * FROM work_version WHERE work_id IN (%s) ORDER BY created_at DESC" % ",".join("?" for _ in work_ids),
        work_ids,
    )
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        latest.setdefault(str(row.get("work_id") or ""), row)
    return latest


def _candidate_for_upload(work: dict[str, Any], version: dict[str, Any] | None) -> dict[str, Any]:
    metadata = _loads(work.get("metadata_json", "{}"))
    source_urls = _loads(work.get("source_urls_json", "[]"))
    version = version or {}
    return {
        "work_id": work.get("work_id") or "",
        "title": version.get("title") or work.get("canonical_title") or "",
        "canonical_title": work.get("canonical_title") or version.get("title") or "",
        "abstract": version.get("abstract") or "",
        "doi": work.get("doi") or "",
        "arxiv_id": work.get("arxiv_id") or "",
        "openalex_id": work.get("openalex_id") or "",
        "crossref_id": work.get("crossref_id") or "",
        "semantic_scholar_id": work.get("semantic_scholar_id") or "",
        "year": work.get("year"),
        "venue_or_source": work.get("venue_or_source") or "",
        "source_type": work.get("source_type") or "paper",
        "source_urls": source_urls,
        "authors": metadata.get("authors") or [],
        "source_modified_at": version.get("source_modified_at") or "",
        "source_updated_at": version.get("source_updated_at") or metadata.get("source_updated_at") or "",
    }


def _public_auth(auth: dict[str, Any]) -> dict[str, Any]:
    return {
        "authorized": bool(auth.get("authorized")),
        "mode": auth.get("mode") or "",
        "warning": auth.get("warning") or "",
        "secret_exposed_to_browser": False,
    }


class _StoreRef:
    def __init__(self, path: Path):
        self.path = path


def _loads(text: str) -> Any:
    try:
        return json.loads(text or "{}")
    except Exception:
        return {}


def _public_work(row: dict[str, Any]) -> dict[str, Any]:
    metadata = _loads(row.get("metadata_json", "{}"))
    return {
        "record_type": "work",
        "work_id": row["work_id"],
        "identity": {
            "canonical_title": row.get("canonical_title"),
            "title_norm": row.get("title_norm"),
            "title_hash": row.get("title_hash"),
            "doi": row.get("doi") or "",
            "arxiv_id": row.get("arxiv_id") or "",
            "openalex_id": row.get("openalex_id") or "",
            "crossref_id": row.get("crossref_id") or "",
            "semantic_scholar_id": row.get("semantic_scholar_id") or "",
            "authors": metadata.get("authors") or [],
            "year": row.get("year"),
            "venue_or_source": row.get("venue_or_source") or "",
            "source_type": row.get("source_type") or "paper",
            "source_urls": _loads(row.get("source_urls_json", "[]")),
        },
        "source_state": {
            "source_provider": "",
            "source_record_id": "",
            "source_updated_at": metadata.get("source_updated_at") or "",
            "title_hash": row.get("title_hash"),
        },
        "latest_by_model": {},
        "relations": {},
        "quality": {"validation_level": "L1", "identity_confidence": row.get("identity_confidence") or 1.0, "verification_status": "llm_extracted", "public_scope": "public_cloud"},
        "timestamps": {"created_at": row.get("created_at"), "updated_at": row.get("updated_at")},
    }


def _public_work_version(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_type": "work_version",
        "work_version_id": row["work_version_id"],
        "work_id": row["work_id"],
        "title": row.get("title") or "",
        "abstract": row.get("abstract") or "",
        "title_hash": row.get("title_hash") or "",
        "abstract_hash": row.get("abstract_hash") or "",
        "content_hash": row.get("content_hash") or "",
        "source_provider": row.get("source_provider") or "",
        "source_record_id": row.get("source_record_id") or "",
        "source_modified_at": row.get("source_modified_at") or "",
        "source_updated_at": row.get("source_updated_at") or "",
        "metadata": _loads(row.get("metadata_json", "{}")),
        "created_at": row.get("created_at"),
    }


def _public_extraction(row: dict[str, Any], *, model_key: str) -> dict[str, Any]:
    return {
        "record_type": "extraction_run",
        "extraction_run_id": row["extraction_run_id"],
        "work_id": row["work_id"],
        "work_version_id": row["work_version_id"],
        "model_key": model_key,
        "llm_provider": row.get("llm_provider") or "",
        "llm_model": row.get("llm_model") or "",
        "model_mode": row.get("model_mode") or "auto",
        "prompt_version": row.get("prompt_version") or "",
        "schema_version": row.get("schema_version") or "",
        "extraction_task_type": row.get("extraction_task_type") or "work_concepts",
        "extraction_status": row.get("extraction_status") or "",
        "token_estimates": {"input": row.get("input_token_estimate") or 0, "output": row.get("output_token_estimate") or 0},
        "cost_estimate": row.get("cost_estimate") or 0,
        "result_summary": _loads(row.get("result_json", "{}")),
        "created_at": row.get("created_at"),
        "completed_at": row.get("completed_at"),
    }


def _public_concept(row: dict[str, Any], payloads: dict[str, Any]) -> dict[str, Any]:
    payload = payloads.get(row.get("active_version_id") or "") or {}
    return {
        "record_type": "concept",
        "concept_id": row["concept_id"],
        "concept_type": row.get("concept_type") or "",
        "canonical_key": row.get("canonical_key") or "",
        "canonical_label": row.get("canonical_label") or "",
        "aliases": [],
        "payload": payload,
        "support": {
            "supporting_work_ids": payload.get("source_works") or payload.get("source_work_ids") or [],
            "evidence_count": 0,
            "confidence_score": row.get("confidence_score") or 0.5,
            "validation_level": row.get("validation_level") or "L1",
            "verification_status": row.get("verification_status") or "llm_extracted",
        },
        "versioning": {"active_version_id": row.get("active_version_id") or "", "last_three_version_ids_by_model": {}},
        "timestamps": {"created_at": row.get("created_at"), "updated_at": row.get("updated_at")},
    }


def _public_evidence(row: dict[str, Any]) -> dict[str, Any]:
    snippet = str(row.get("evidence_span") or "")[:1200]
    return {
        "record_type": "evidence",
        "evidence_id": row["evidence_id"],
        "concept_id": row.get("concept_id") or "",
        "work_id": row.get("work_id") or "",
        "work_version_id": row.get("work_version_id") or "",
        "evidence_type": row.get("evidence_type") or "metadata",
        "locator": {"source_url": row.get("source_url") or ""},
        "snippet": snippet,
        "claim_text": snippet,
        "confidence": row.get("confidence") or 0.5,
        "created_at": row.get("created_at"),
    }
