from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .utils import compact_text, stable_id


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(title or "").lower()).strip()


def text_hash(value: str, *, length: int = 16) -> str:
    normalized = " ".join(str(value or "").split()).lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:length]


def metadata_hash(payload: dict[str, Any], *, length: int = 16) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:length]


def work_content_signature(work: dict[str, Any]) -> dict[str, str]:
    title = compact_text(str(work.get("title") or work.get("canonical_title") or "Untitled work"), 320)
    abstract = compact_text(str(work.get("abstract") or ""), 6000)
    return {
        "title_hash": text_hash(title),
        "abstract_hash": text_hash(abstract),
        "content_hash": metadata_hash(
            {
                "title": title,
                "abstract": abstract,
                "source_updated_at": work.get("source_updated_at") or work.get("source_modified_at") or "",
            }
        ),
    }


def work_version_id(work_id: str, work: dict[str, Any]) -> str:
    sig = work_content_signature(work)
    return stable_id("WV", work_id, sig["title_hash"], sig["abstract_hash"], sig["content_hash"])


def version_decision(remote_work: dict[str, Any], latest_version: dict[str, Any] | None) -> str:
    if not latest_version:
        return "new_version"
    sig = work_content_signature(remote_work)
    if sig["title_hash"] != latest_version.get("title_hash") or sig["abstract_hash"] != latest_version.get("abstract_hash"):
        return "new_version"
    new_modified = str(remote_work.get("source_updated_at") or remote_work.get("source_modified_at") or "")
    old_modified = str(latest_version.get("source_updated_at") or latest_version.get("source_modified_at") or "")
    if new_modified and old_modified and new_modified != old_modified:
        return "metadata_update"
    return "unchanged"


def model_key(
    llm_provider: str,
    llm_model: str,
    model_mode: str,
    prompt_version: str,
    schema_version: str,
    extraction_task_type: str,
) -> str:
    return ":".join(
        [
            str(llm_provider or "unknown"),
            str(llm_model or "unknown"),
            str(model_mode or "auto"),
            str(prompt_version or "principia-work-extract-v1"),
            str(schema_version or "principia-cloud-1.1"),
            str(extraction_task_type or "work_concepts"),
        ]
    )


def cloud_freshness_decision(candidate: dict[str, Any], cloud_work: dict[str, Any] | None, current_model_key: str) -> dict[str, Any]:
    if not cloud_work:
        return {"should_extract": True, "reason": "not_in_cloud"}
    latest_by_model = cloud_work.get("latest_by_model") or {}
    if current_model_key and current_model_key not in latest_by_model:
        return {"should_extract": True, "reason": "model_version_missing"}
    source_state = cloud_work.get("source_state") or {}
    candidate_modified = str(candidate.get("source_modified_at") or candidate.get("source_updated_at") or "")
    cloud_modified = str(source_state.get("source_modified_at") or source_state.get("source_updated_at") or "")
    if candidate_modified and cloud_modified:
        if candidate_modified > cloud_modified:
            return {"should_extract": True, "reason": "source_newer_than_cloud"}
        return {"should_extract": False, "reason": "cloud_cache_hit"}
    sig = work_content_signature(candidate)
    if sig.get("abstract_hash") and source_state.get("abstract_hash") and sig["abstract_hash"] != source_state.get("abstract_hash"):
        return {"should_extract": True, "reason": "abstract_hash_changed"}
    if sig.get("content_hash") and source_state.get("content_hash") and sig["content_hash"] != source_state.get("content_hash"):
        return {"should_extract": True, "reason": "content_hash_changed"}
    return {"should_extract": False, "reason": "cloud_cache_hit"}
