from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from ..work_versioning import normalize_title, work_content_signature


def canonical_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_hex(data: str | bytes) -> str:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    return hashlib.sha256(raw).hexdigest()


def cloud_id(prefix: str, *parts: Any, length: int = 24) -> str:
    body = canonical_json([part for part in parts if part is not None])
    return f"{prefix}_{sha256_hex(body)[:length]}"


def normalize_external_id(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().lower())


def best_identity_key(keys: dict[str, str]) -> str:
    for name in ("doi", "arxiv_id", "openreview_forum_id", "openalex_id", "semantic_scholar_id", "crossref_id", "title_hash"):
        value = str(keys.get(name) or "").strip()
        if value:
            return f"{name}:{value}"
    return f"title_norm:{normalize_title(keys.get('canonical_title') or '')}"


def candidate_identity_keys(work: dict[str, Any]) -> dict[str, str]:
    sig = work_content_signature(work)
    keys = {
        "canonical_title": str(work.get("canonical_title") or work.get("title") or "").strip(),
        "title_hash": str(work.get("title_hash") or sig.get("title_hash") or "").strip(),
        "abstract_hash": str(work.get("abstract_hash") or sig.get("abstract_hash") or "").strip(),
        "content_hash": str(work.get("content_hash") or sig.get("content_hash") or "").strip(),
        "doi": normalize_external_id(work.get("doi") or work.get("DOI") or ""),
        "arxiv_id": normalize_external_id(work.get("arxiv_id") or ""),
        "openalex_id": normalize_external_id(work.get("openalex_id") or ""),
        "crossref_id": normalize_external_id(work.get("crossref_id") or ""),
        "semantic_scholar_id": normalize_external_id(work.get("semantic_scholar_id") or ""),
        "openreview_forum_id": normalize_external_id(work.get("openreview_forum_id") or ""),
    }
    return {key: value for key, value in keys.items() if value}


def shard_for_key(key: str, shard_count: int) -> int:
    if shard_count <= 1:
        return 0
    return int(sha256_hex(key)[:8], 16) % shard_count


def shard_id(prefix: str, key: str, shard_count: int) -> str:
    width = max(2, len(str(max(0, shard_count - 1))))
    return f"{prefix}-{shard_for_key(key, shard_count):0{width}d}"


def candidate_route_shards(work: dict[str, Any], shard_count: int) -> set[int]:
    keys = candidate_identity_keys(work)
    route_keys = {best_identity_key(keys)}
    for name in ("doi", "arxiv_id", "openreview_forum_id", "openalex_id", "semantic_scholar_id", "crossref_id", "title_hash"):
        value = keys.get(name)
        if value:
            route_keys.add(f"{name}:{value}")
    return {shard_for_key(key, shard_count) for key in route_keys if key}
