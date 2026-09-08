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
