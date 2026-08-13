from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from .utils import (
    clean_doi,
    clean_text,
    extract_arxiv_id,
    max_int,
    normalize_scholarly_title,
    ordered_unique,
    stable_id,
    title_key,
)


def dedupe_works(works: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    key_to_index: dict[str, int] = {}
    for work in works:
        item = normalize_work(work)
        if not item:
            continue
        keys = identity_keys(item) or [f"title:{title_key(item.get('title', ''))}"]
        match = find_duplicate_index(item, keys, output, key_to_index)
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


def find_duplicate_index(
    item: dict[str, Any],
    keys: list[str],
    works: list[dict[str, Any]],
    key_to_index: dict[str, int],
) -> int | None:
    """Prefer stable identifiers; use title only when at least one record lacks one."""
    strong_keys = set(strong_identity_keys(item))
    for key in strong_keys:
        if key in key_to_index:
            return key_to_index[key]

    title = f"title:{title_key(item.get('title', ''))}"
    match = key_to_index.get(title)
    if match is not None:
        existing_strong_keys = set(strong_identity_keys(works[match]))
        if not conflicting_identifiers(
            strong_keys, existing_strong_keys
        ) and compatible_bibliography(item, works[match]):
            return match
    # Publication titles often gain or lose a subtitle between preprint and
    # venue metadata.  A very high title match plus compatible author/year
    # evidence is safe enough to connect those versions without collapsing
    # unrelated works that merely share a generic title.
    for index, existing in enumerate(works):
        if cautious_title_match(item, existing) and not conflicting_identifiers(
            strong_keys, set(strong_identity_keys(existing))
        ):
            return index
    return None


def normalize_work(row: dict[str, Any] | Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        row = {
            key: getattr(row, key, None)
            for key in dir(row)
            if not key.startswith("_") and not callable(getattr(row, key, None))
        }
    title = normalize_scholarly_title(row.get("title") or row.get("display_name") or "")
    if not title:
        return {}
    url = str(row.get("url_or_doi") or row.get("url") or row.get("paper_link") or "")
    doi = clean_doi(row.get("doi") or row.get("DOI") or "")
    arxiv_id = normalize_arxiv_id(row.get("arxiv_id") or extract_arxiv_id(url) or "")
    metadata = dict(row.get("community_signals") or row.get("metadata") or {})
    return {
        "work_id": str(
            row.get("work_id") or row.get("id") or stable_id("W", title, doi or arxiv_id or url)
        ),
        "id": str(
            row.get("id") or row.get("work_id") or stable_id("W", title, doi or arxiv_id or url)
        ),
        "title": title,
        "authors": list(row.get("authors") or []),
        "year": row.get("year"),
        "venue_or_source": clean_text(
            row.get("venue_or_source") or row.get("venue") or row.get("source") or ""
        ),
        "venue": clean_text(
            row.get("venue") or row.get("venue_or_source") or row.get("source") or ""
        ),
        "source": str(row.get("source") or metadata.get("source") or ""),
        "source_type": str(row.get("source_type") or row.get("publication_type") or "paper"),
        "url_or_doi": url,
        "url": url,
        "doi": doi,
        "arxiv_id": arxiv_id,
        "openalex_id": str(row.get("openalex_id") or ""),
        "semantic_scholar_id": str(row.get("semantic_scholar_id") or ""),
        "pmid": str(row.get("pmid") or ""),
        "pdf_url": str(row.get("pdf_url") or ""),
        "abstract": clean_text(row.get("abstract") or ""),
        "citation_count": row.get("citation_count"),
        "source_urls": list(row.get("source_urls") or ([url] if url else [])),
        "community_signals": metadata,
        "metadata": metadata,
    }


def merge_work(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    preferred, secondary = (
        (right, left) if source_quality(right) > source_quality(left) else (left, right)
    )
    left_metadata = dict(left.get("community_signals") or {})
    right_metadata = dict(right.get("community_signals") or {})
    metadata = {
        **dict(secondary.get("community_signals") or {}),
        **dict(preferred.get("community_signals") or {}),
    }
    metadata["merged_sources"] = ordered_unique(
        [*(metadata.get("merged_sources") or []), source_name(left), source_name(right)]
    )
    metadata["matched_queries"] = ordered_unique(
        [
            *metadata_list(left_metadata.get("matched_queries")),
            *metadata_list(right_metadata.get("matched_queries")),
            left_metadata.get("source_query") or "",
            right_metadata.get("source_query") or "",
        ]
    )
    query_ranks: dict[str, int] = {}
    for source_metadata in (left_metadata, right_metadata):
        for query, rank in dict(source_metadata.get("source_query_ranks") or {}).items():
            try:
                normalized_rank = int(rank)
            except (TypeError, ValueError):
                continue
            query_ranks[str(query)] = min(
                query_ranks.get(str(query), normalized_rank), normalized_rank
            )
    metadata["source_query_ranks"] = query_ranks
    metadata["has_preprint"] = any(
        [
            source_name(left) == "arxiv",
            source_name(right) == "arxiv",
            bool(left_metadata.get("is_preprint") or left_metadata.get("has_preprint")),
            bool(right_metadata.get("is_preprint") or right_metadata.get("has_preprint")),
        ]
    )
    peer_versions = [item for item in (left, right) if work_has_peer_reviewed_metadata(item)]
    metadata["has_peer_reviewed"] = bool(peer_versions)
    if peer_versions:
        peer_version = max(peer_versions, key=source_quality)
        peer_metadata = dict(peer_version.get("community_signals") or {})
        metadata["is_peer_reviewed"] = True
        metadata["peer_reviewed_venue"] = clean_text(
            peer_metadata.get("peer_reviewed_venue")
            or peer_version.get("venue_or_source")
            or peer_version.get("venue")
            or ""
        )
        metadata["publication_type"] = str(
            peer_metadata.get("publication_type")
            or peer_metadata.get("type")
            or peer_version.get("source_type")
            or "conference-paper"
        )
    merged = dict(preferred)
    for key in (
        "authors",
        "year",
        "venue_or_source",
        "url_or_doi",
        "doi",
        "arxiv_id",
        "openalex_id",
        "semantic_scholar_id",
        "pmid",
        "pdf_url",
    ):
        if not merged.get(key) and secondary.get(key):
            merged[key] = secondary[key]
    if len(str(secondary.get("abstract") or "")) > len(str(merged.get("abstract") or "")):
        merged["abstract"] = secondary.get("abstract", "")
    merged["citation_count"] = max_int(
        merged.get("citation_count"), secondary.get("citation_count")
    )
    merged["source_urls"] = ordered_unique(
        [*(preferred.get("source_urls") or []), *(secondary.get("source_urls") or [])]
    )
    merged["community_signals"] = metadata
    merged["metadata"] = metadata
    return merged


def work_has_peer_reviewed_metadata(work: dict[str, Any]) -> bool:
    metadata = dict(work.get("community_signals") or {})
    if bool(metadata.get("is_peer_reviewed") or metadata.get("has_peer_reviewed")):
        return True
    publication_type = str(
        metadata.get("publication_type")
        or metadata.get("type")
        or work.get("source_type")
        or ""
    ).casefold()
    if publication_type not in {
        "conference paper",
        "conference-paper",
        "journal article",
        "journal-article",
        "proceedings article",
        "proceedings-article",
    }:
        return False
    if bool(metadata.get("is_preprint")):
        return False
    venue = str(work.get("venue_or_source") or work.get("venue") or "").casefold()
    return bool(venue and venue not in {"arxiv", "crossref", "openreview", "semantic scholar"})


def identity_keys(work: dict[str, Any]) -> list[str]:
    keys = strong_identity_keys(work)
    if work.get("title"):
        keys.append(f"title:{title_key(work['title'])}")
    return keys


def strong_identity_keys(work: dict[str, Any]) -> list[str]:
    keys = []
    for field, prefix in [
        ("doi", "doi"),
        ("arxiv_id", "arxiv"),
        ("openalex_id", "openalex"),
        ("semantic_scholar_id", "s2"),
        ("pmid", "pmid"),
    ]:
        value = clean_text(work.get(field) or "")
        if value:
            keys.append(f"{prefix}:{value.lower()}")
    return keys


def normalize_arxiv_id(value: Any) -> str:
    """Treat arXiv version suffixes as versions of the same strong identity."""
    return re.sub(r"v\d+$", "", clean_text(value), flags=re.I)


def source_quality(work: dict[str, Any]) -> tuple[int, int, int]:
    source = source_name(work)
    peer = 1 if work_has_peer_reviewed_metadata(work) else 0
    return (
        peer,
        {"crossref": 6, "openreview": 5, "europe_pmc": 4, "openalex": 3, "semantic_scholar": 2, "arxiv": 1}.get(
            source, 0
        ),
        int(work.get("citation_count") or 0),
    )


def source_name(work: dict[str, Any]) -> str:
    return str(
        (work.get("community_signals") or {}).get("source") or work.get("source") or ""
    ).lower()


def conflicting_identifiers(left: set[str], right: set[str]) -> bool:
    left_by_prefix = {value.split(":", 1)[0]: value for value in left}
    right_by_prefix = {value.split(":", 1)[0]: value for value in right}
    return any(
        left_by_prefix[prefix] != right_by_prefix[prefix]
        for prefix in left_by_prefix.keys() & right_by_prefix.keys()
    )


def compatible_bibliography(left: dict[str, Any], right: dict[str, Any]) -> bool:
    try:
        left_year = int(left.get("year") or 0)
        right_year = int(right.get("year") or 0)
    except (TypeError, ValueError):
        left_year = right_year = 0
    if left_year and right_year and abs(left_year - right_year) > 2:
        return False
    left_authors = author_keys(left)
    right_authors = author_keys(right)
    return not left_authors or not right_authors or bool(left_authors & right_authors)


def cautious_title_match(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_title = title_key(left.get("title", ""))
    right_title = title_key(right.get("title", ""))
    if not left_title or not right_title or not compatible_bibliography(left, right):
        return False
    ratio = SequenceMatcher(None, left_title, right_title).ratio()
    left_tokens = set(left_title.split())
    right_tokens = set(right_title.split())
    overlap = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))
    return ratio >= 0.96 or (overlap >= 0.9 and min(len(left_tokens), len(right_tokens)) >= 5)


def author_keys(work: dict[str, Any]) -> set[str]:
    output = set()
    for author in work.get("authors") or []:
        parts = title_key(str(author)).split()
        if parts:
            output.add(parts[-1])
    return output


def metadata_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return [value] if value else []
