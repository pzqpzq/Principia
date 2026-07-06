from __future__ import annotations

from typing import Any

from .utils import clean_doi, clean_text, extract_arxiv_id, max_int, ordered_unique, stable_id, title_key


def dedupe_works(works: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    key_to_index: dict[str, int] = {}
    for work in works:
        item = normalize_work(work)
        if not item:
            continue
        keys = identity_keys(item) or [f"title:{title_key(item.get('title', ''))}"]
        match = next((key_to_index[key] for key in keys if key in key_to_index), None)
        if match is None:
            index = len(output)
            output.append(item)
            for key in keys:
                key_to_index[key] = index
            continue
        output[match] = merge_work(output[match], item)
        for key in identity_keys(output[match]):
            key_to_index[key] = match
    return output


def normalize_work(row: dict[str, Any] | Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        row = {key: getattr(row, key, None) for key in dir(row) if not key.startswith("_") and not callable(getattr(row, key, None))}
    title = clean_text(row.get("title") or row.get("display_name") or "")
    if not title:
        return {}
    url = str(row.get("url_or_doi") or row.get("url") or row.get("paper_link") or "")
    doi = clean_doi(row.get("doi") or row.get("DOI") or "")
    arxiv_id = str(row.get("arxiv_id") or extract_arxiv_id(url) or "")
    metadata = dict(row.get("community_signals") or row.get("metadata") or {})
    return {
        "work_id": str(row.get("work_id") or row.get("id") or stable_id("W", title, doi or arxiv_id or url)),
        "id": str(row.get("id") or row.get("work_id") or stable_id("W", title, doi or arxiv_id or url)),
        "title": title,
        "authors": list(row.get("authors") or []),
        "year": row.get("year"),
        "venue_or_source": clean_text(row.get("venue_or_source") or row.get("venue") or row.get("source") or ""),
        "venue": clean_text(row.get("venue") or row.get("venue_or_source") or row.get("source") or ""),
        "source": str(row.get("source") or metadata.get("source") or ""),
        "source_type": str(row.get("source_type") or row.get("publication_type") or "paper"),
        "url_or_doi": url,
        "url": url,
        "doi": doi,
        "arxiv_id": arxiv_id,
        "openalex_id": str(row.get("openalex_id") or ""),
        "semantic_scholar_id": str(row.get("semantic_scholar_id") or ""),
        "abstract": clean_text(row.get("abstract") or ""),
        "citation_count": row.get("citation_count"),
        "source_urls": list(row.get("source_urls") or ([url] if url else [])),
        "community_signals": metadata,
        "metadata": metadata,
    }


def merge_work(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    preferred, secondary = (right, left) if source_quality(right) > source_quality(left) else (left, right)
    metadata = {**dict(secondary.get("community_signals") or {}), **dict(preferred.get("community_signals") or {})}
    metadata["merged_sources"] = ordered_unique([*(metadata.get("merged_sources") or []), source_name(left), source_name(right)])
    merged = dict(preferred)
    for key in ("authors", "year", "venue_or_source", "url_or_doi", "doi", "arxiv_id", "openalex_id", "semantic_scholar_id"):
        if not merged.get(key) and secondary.get(key):
            merged[key] = secondary[key]
    if len(str(secondary.get("abstract") or "")) > len(str(merged.get("abstract") or "")):
        merged["abstract"] = secondary.get("abstract", "")
    merged["citation_count"] = max_int(merged.get("citation_count"), secondary.get("citation_count"))
    merged["source_urls"] = ordered_unique([*(preferred.get("source_urls") or []), *(secondary.get("source_urls") or [])])
    merged["community_signals"] = metadata
    merged["metadata"] = metadata
    return merged


def identity_keys(work: dict[str, Any]) -> list[str]:
    keys = []
    for field, prefix in [("doi", "doi"), ("arxiv_id", "arxiv"), ("openalex_id", "openalex"), ("semantic_scholar_id", "s2")]:
        value = clean_text(work.get(field) or "")
        if value:
            keys.append(f"{prefix}:{value.lower()}")
    if work.get("title"):
        keys.append(f"title:{title_key(work['title'])}")
    return keys


def source_quality(work: dict[str, Any]) -> tuple[int, int, int]:
    source = source_name(work)
    venue = str(work.get("venue_or_source") or "").lower()
    peer = 0 if venue in {"", "arxiv", "openalex", "crossref", "semantic scholar"} else 1
    return (peer, {"crossref": 4, "openalex": 3, "semantic_scholar": 2, "arxiv": 1}.get(source, 0), int(work.get("citation_count") or 0))


def source_name(work: dict[str, Any]) -> str:
    return str((work.get("community_signals") or {}).get("source") or work.get("source") or "").lower()
