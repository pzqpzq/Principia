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


def normalize_arxiv_id(value: Any) -> str:
    value = normalize_external_id(value)
    value = re.sub(r"\.(?:pdf|html)$", "", value)
    return re.sub(r"v\d+$", "", value)


def _iter_identity_values(work: dict[str, Any]) -> list[str]:
    values: list[Any] = [
        work.get("doi"),
        work.get("DOI"),
        work.get("url_or_doi"),
        work.get("paper_link"),
        work.get("source_paper_link"),
        work.get("official_url"),
    ]
    for key in ("source_urls", "source_paper_links", "links"):
        raw = work.get(key)
        if isinstance(raw, list):
            values.extend(raw)
        elif raw:
            values.append(raw)
    return [str(value).strip() for value in values if str(value or "").strip()]


def _extract_arxiv_id(value: str) -> str:
    text = str(value or "").strip()
    patterns = [
        r"arxiv\.org/(?:abs|pdf|html)/([^?#/\s]+)",
        r"(?:^|\b)arxiv\s*:\s*([a-z-]+/\d{7}|[0-9]{4}\.[0-9]{4,5}(?:v\d+)?)",
    ]
    if "arxiv" in text.lower():
        patterns.append(r"\b([a-z-]+/\d{7}|[0-9]{4}\.[0-9]{4,5}(?:v\d+)?)\b")
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return normalize_arxiv_id(match.group(1))
    return ""


def _extract_doi(value: str) -> str:
    text = str(value or "").strip()
    match = re.search(r"(?:doi\.org/|doi\s*:\s*)?(10\.\d{4,9}/[^\s?#<>\"']+)", text, flags=re.IGNORECASE)
    if not match:
        return ""
    return normalize_external_id(match.group(1).rstrip(".,);]"))


def _extract_openreview_forum_id(value: str) -> str:
    text = str(value or "").strip()
    match = re.search(r"openreview\.net/(?:forum|pdf)\?id=([^&#\s]+)", text, flags=re.IGNORECASE)
    if match:
        return normalize_external_id(match.group(1))
    return ""


def _first_extracted(values: list[str], extractor) -> str:
    for value in values:
        extracted = extractor(value)
        if extracted:
            return extracted
    return ""


def best_identity_key(keys: dict[str, str]) -> str:
    for name in ("doi", "arxiv_id", "openreview_forum_id", "openalex_id", "semantic_scholar_id", "crossref_id", "title_hash"):
        value = str(keys.get(name) or "").strip()
        if value:
            return f"{name}:{value}"
    return f"title_norm:{normalize_title(keys.get('canonical_title') or '')}"


def candidate_identity_keys(work: dict[str, Any]) -> dict[str, str]:
    sig = work_content_signature(work)
    identity_values = _iter_identity_values(work)
    keys = {
        "canonical_title": str(work.get("canonical_title") or work.get("title") or "").strip(),
        "title_hash": str(work.get("title_hash") or sig.get("title_hash") or "").strip(),
        "abstract_hash": str(work.get("abstract_hash") or sig.get("abstract_hash") or "").strip(),
        "content_hash": str(work.get("content_hash") or sig.get("content_hash") or "").strip(),
        "doi": normalize_external_id(work.get("doi") or work.get("DOI") or _first_extracted(identity_values, _extract_doi)),
        "arxiv_id": normalize_arxiv_id(work.get("arxiv_id") or _first_extracted(identity_values, _extract_arxiv_id)),
        "openalex_id": normalize_external_id(work.get("openalex_id") or ""),
        "crossref_id": normalize_external_id(work.get("crossref_id") or ""),
        "semantic_scholar_id": normalize_external_id(work.get("semantic_scholar_id") or ""),
        "openreview_forum_id": normalize_external_id(work.get("openreview_forum_id") or _first_extracted(identity_values, _extract_openreview_forum_id)),
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
