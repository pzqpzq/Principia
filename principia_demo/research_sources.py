from __future__ import annotations

import json
import re
import ssl
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from .arxiv import search_arxiv
from .utils import compact_text, lexical_score, stable_id


USER_AGENT = "Principia-v2/0.2 (local research workspace; mailto:research@example.local)"


def search_hybrid_sources(query: str, max_results: int = 100, timeout: int = 12) -> list[dict[str, Any]]:
    """Search free public metadata sources and return SourceWork-shaped dicts.

    The function intentionally avoids paid/search-engine APIs. It combines arXiv,
    OpenAlex, and Crossref metadata, then ranks and deduplicates by title.
    """

    query = " ".join(str(query or "").split())
    if not query:
        return []
    per_source = max(20, min(max_results, 100))
    sources = [
        ("arxiv", lambda: search_arxiv(query, max_results=per_source, timeout=timeout)),
        ("openalex", lambda: search_openalex(query, max_results=per_source, timeout=timeout)),
        ("crossref", lambda: search_crossref(query, max_results=per_source, timeout=timeout)),
    ]
    works: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(fetcher) for _, fetcher in sources]
        for future in as_completed(futures):
            try:
                works.extend(future.result())
            except Exception:
                continue
    ranked = _dedupe_works(works)
    ranked.sort(
        key=lambda work: (
            lexical_score(query, f"{work.get('title', '')} {work.get('abstract', '')}"),
            int(work.get("year") or 0),
            bool(work.get("url_or_doi")),
        ),
        reverse=True,
    )
    return ranked[:max_results]


def search_openalex(query: str, max_results: int = 50, timeout: int = 12) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode(
        {
            "search": query,
            "per-page": max(1, min(max_results, 100)),
            "sort": "relevance_score:desc",
        }
    )
    data = _fetch_json(f"https://api.openalex.org/works?{params}", timeout)
    works: list[dict[str, Any]] = []
    for item in data.get("results", []) if isinstance(data, dict) else []:
        title = _clean_text(item.get("title") or item.get("display_name") or "")
        if not title:
            continue
        abstract = _openalex_abstract(item.get("abstract_inverted_index") or {})
        year = item.get("publication_year")
        primary = item.get("primary_location") or {}
        source = primary.get("source") or {}
        landing = primary.get("landing_page_url") or item.get("doi") or item.get("id") or ""
        authors = [
            _clean_text(((authorship.get("author") or {}).get("display_name") or ""))
            for authorship in item.get("authorships", [])[:12]
            if isinstance(authorship, dict)
        ]
        venue = _clean_text(source.get("display_name") or item.get("host_venue", {}).get("display_name") or "OpenAlex")
        works.append(
            {
                "work_id": stable_id("W", _title_key(title)),
                "title": title,
                "authors": [name for name in authors if name],
                "year": int(year) if isinstance(year, int) else None,
                "venue_or_source": venue or "OpenAlex",
                "url_or_doi": landing,
                "source_type": "paper",
                "validation_level": "L1",
                "abstract": compact_text(abstract, 1800),
                "citation_count": item.get("cited_by_count"),
                "community_signals": {
                    "source": "openalex",
                    "is_oa": bool((primary.get("is_oa") if isinstance(primary, dict) else False)),
                    "type": item.get("type", ""),
                },
                "source_urls": [url for url in [landing, item.get("id", "")] if url],
                "source_updated_at": item.get("updated_date", ""),
            }
        )
    return works


def search_crossref(query: str, max_results: int = 50, timeout: int = 12) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({"query": query, "rows": max(1, min(max_results, 100)), "sort": "relevance"})
    data = _fetch_json(f"https://api.crossref.org/works?{params}", timeout)
    items = (((data or {}).get("message") or {}).get("items") or []) if isinstance(data, dict) else []
    works: list[dict[str, Any]] = []
    for item in items:
        title = _clean_text(" ".join(item.get("title") or []))
        if not title:
            continue
        year_parts = (((item.get("published-print") or item.get("published-online") or item.get("issued") or {}).get("date-parts") or [[]])[0])
        year = year_parts[0] if year_parts and isinstance(year_parts[0], int) else None
        doi = item.get("DOI") or ""
        url = item.get("URL") or (f"https://doi.org/{doi}" if doi else "")
        authors = []
        for author in item.get("author", [])[:12]:
            name = " ".join(part for part in [author.get("given", ""), author.get("family", "")] if part).strip()
            if name:
                authors.append(name)
        venue = _clean_text(" ".join(item.get("container-title") or []) or item.get("publisher") or "Crossref")
        abstract = _strip_tags(item.get("abstract") or "")
        works.append(
            {
                "work_id": stable_id("W", _title_key(title)),
                "title": title,
                "authors": authors,
                "year": year,
                "venue_or_source": venue or "Crossref",
                "url_or_doi": url,
                "source_type": "paper",
                "validation_level": "L1",
                "abstract": compact_text(abstract, 1800),
                "citation_count": item.get("is-referenced-by-count"),
                "community_signals": {"source": "crossref", "type": item.get("type", "")},
                "source_urls": [url for url in [url, item.get("resource", {}).get("primary", {}).get("URL", "")] if url],
                "source_updated_at": item.get("indexed", {}).get("date-time", ""),
            }
        )
    return works


def _fetch_json(url: str, timeout: int) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        if "CERTIFICATE_VERIFY_FAILED" not in repr(exc):
            raise
        with urllib.request.urlopen(req, timeout=timeout, context=ssl._create_unverified_context()) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))


def _openalex_abstract(index: dict[str, list[int]]) -> str:
    if not isinstance(index, dict) or not index:
        return ""
    pairs: list[tuple[int, str]] = []
    for word, positions in index.items():
        for pos in positions or []:
            if isinstance(pos, int):
                pairs.append((pos, word))
    pairs.sort(key=lambda item: item[0])
    return " ".join(word for _, word in pairs)


def _dedupe_works(works: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for work in works:
        title = _clean_text(work.get("title", ""))
        if not title:
            continue
        key = _title_key(title)
        current = merged.get(key)
        if not current:
            item = dict(work)
            item["work_id"] = stable_id("W", key)
            merged[key] = item
            continue
        current["source_urls"] = _ordered_unique([*(current.get("source_urls") or []), *(work.get("source_urls") or []), work.get("url_or_doi", "")])
        if not current.get("abstract") and work.get("abstract"):
            current["abstract"] = work["abstract"]
        if not current.get("url_or_doi") and work.get("url_or_doi"):
            current["url_or_doi"] = work["url_or_doi"]
        if _venue_rank(work.get("venue_or_source", "")) > _venue_rank(current.get("venue_or_source", "")):
            current["venue_or_source"] = work.get("venue_or_source") or current.get("venue_or_source")
        if not current.get("year") and work.get("year"):
            current["year"] = work["year"]
        current["citation_count"] = max(int(current.get("citation_count") or 0), int(work.get("citation_count") or 0)) or current.get("citation_count")
    return list(merged.values())


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output = []
    for value in values:
        clean = str(value or "").strip()
        if clean and clean not in seen:
            seen.add(clean)
            output.append(clean)
    return output


def _title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _clean_text(title).lower()).strip()


def _clean_text(value: str) -> str:
    return " ".join(str(value or "").split())


def _strip_tags(value: str) -> str:
    return _clean_text(re.sub(r"<[^>]+>", " ", value or ""))


def _venue_rank(venue: str) -> int:
    value = _clean_text(venue).lower()
    if not value:
        return 0
    top = [
        "neurips",
        "icml",
        "iclr",
        "cvpr",
        "iccv",
        "eccv",
        "acl",
        "emnlp",
        "naacl",
        "colm",
        "kdd",
        "www",
        "sigir",
        "aaai",
        "ijcai",
        "jmlr",
        "tmlr",
        "tpami",
        "nature",
        "science",
    ]
    if any(term in value for term in top):
        return 4
    if value not in {"arxiv", "openalex", "crossref"}:
        return 3
    if value in {"arxiv", "openalex", "crossref"}:
        return 1
    return 2
