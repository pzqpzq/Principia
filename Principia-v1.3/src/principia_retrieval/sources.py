from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any

from .models import WorkSource
from .utils import (
    clean_doi,
    clean_text,
    contains_query_trigger,
    extract_arxiv_id,
    fetch_bytes,
    fetch_json,
    openalex_abstract,
    stable_id,
    strip_tags,
)
from .works import normalize_work


def default_sources() -> dict[str, WorkSource]:
    return {
        "arxiv": search_arxiv,
        "openalex": search_openalex,
        "crossref": search_crossref,
        "semantic_scholar": search_semantic_scholar,
    }


def fetch_source(name: str, source: WorkSource, query: str, limit: int, timeout: float) -> list[dict[str, Any]]:
    try:
        rows = source(query, limit, timeout)
    except TypeError:
        try:
            rows = source(query, max_results=limit, timeout=timeout)  # type: ignore[misc]
        except Exception:
            return []
    except Exception:
        return []
    output = []
    for row in rows or []:
        item = normalize_work(row)
        if item:
            signals = dict(item.get("community_signals") or item.get("metadata") or {})
            signals.setdefault("source", name)
            item["community_signals"] = signals
            item["metadata"] = signals
            if not item.get("source"):
                item["source"] = name
            output.append(item)
    return output


def search_arxiv(query: str, limit: int = 20, timeout: float = 12) -> list[dict[str, Any]]:
    search_query = arxiv_query(query)
    params = urllib.parse.urlencode(
        {"search_query": search_query, "start": 0, "max_results": max(1, min(limit, 100)), "sortBy": "relevance", "sortOrder": "descending"}
    )
    root = ET.fromstring(fetch_bytes(f"https://export.arxiv.org/api/query?{params}", timeout))
    ns = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    works = []
    for entry in root.findall("a:entry", ns):
        title = clean_text(entry.findtext("a:title", default="", namespaces=ns))
        if not title:
            continue
        abstract = clean_text(entry.findtext("a:summary", default="", namespaces=ns))
        url = entry.findtext("a:id", default="", namespaces=ns) or ""
        published = entry.findtext("a:published", default="", namespaces=ns) or ""
        year_match = re.match(r"(\d{4})", published)
        authors = [clean_text(author.findtext("a:name", default="", namespaces=ns)) for author in entry.findall("a:author", ns)]
        works.append(
            {
                "work_id": stable_id("W", title, url),
                "title": title,
                "authors": [name for name in authors if name],
                "year": int(year_match.group(1)) if year_match else None,
                "venue_or_source": "arXiv",
                "url_or_doi": url,
                "paper_link": url,
                "abstract": abstract,
                "arxiv_id": extract_arxiv_id(url),
                "source_urls": [url],
                "community_signals": {"source": "arxiv", "is_preprint": True, "type": "preprint"},
            }
        )
    return works


def search_openalex(query: str, limit: int = 20, timeout: float = 12) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({"search": query, "per-page": max(1, min(limit, 100)), "sort": "relevance_score:desc"})
    data = fetch_json(f"https://api.openalex.org/works?{params}", timeout)
    works = []
    for item in data.get("results", []) if isinstance(data, dict) else []:
        title = clean_text(item.get("title") or item.get("display_name") or "")
        if not title:
            continue
        primary = item.get("primary_location") or {}
        source = (primary.get("source") or {}) if isinstance(primary, dict) else {}
        landing = primary.get("landing_page_url") or item.get("doi") or item.get("id") or ""
        authors = [
            clean_text((authorship.get("author") or {}).get("display_name") or "")
            for authorship in item.get("authorships", [])[:12]
            if isinstance(authorship, dict)
        ]
        works.append(
            {
                "work_id": stable_id("W", title),
                "title": title,
                "authors": [name for name in authors if name],
                "year": item.get("publication_year"),
                "venue_or_source": clean_text(source.get("display_name") or "OpenAlex"),
                "url_or_doi": landing,
                "doi": clean_doi(item.get("doi") or ""),
                "openalex_id": item.get("id") or "",
                "abstract": openalex_abstract(item.get("abstract_inverted_index") or {}),
                "citation_count": item.get("cited_by_count"),
                "source_urls": [url for url in [landing, item.get("doi"), item.get("id")] if url],
                "community_signals": {"source": "openalex", "type": item.get("type", ""), "is_oa": bool(primary.get("is_oa")) if isinstance(primary, dict) else False},
            }
        )
    return works


def search_crossref(query: str, limit: int = 20, timeout: float = 12) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({"query": query, "rows": max(1, min(limit, 100)), "sort": "relevance"})
    data = fetch_json(f"https://api.crossref.org/works?{params}", timeout)
    items = (((data or {}).get("message") or {}).get("items") or []) if isinstance(data, dict) else []
    works = []
    for item in items:
        title = clean_text(" ".join(item.get("title") or []))
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
        works.append(
            {
                "work_id": stable_id("W", title),
                "title": title,
                "authors": authors,
                "year": year,
                "venue_or_source": clean_text(" ".join(item.get("container-title") or []) or item.get("publisher") or "Crossref"),
                "url_or_doi": url,
                "doi": clean_doi(doi),
                "abstract": strip_tags(item.get("abstract") or ""),
                "citation_count": item.get("is-referenced-by-count"),
                "source_urls": [url],
                "community_signals": {"source": "crossref", "type": item.get("type", "")},
            }
        )
    return works


def search_semantic_scholar(query: str, limit: int = 20, timeout: float = 12) -> list[dict[str, Any]]:
    fields = "title,authors,year,venue,url,abstract,citationCount,externalIds"
    params = urllib.parse.urlencode({"query": query, "limit": max(1, min(limit, 100)), "fields": fields})
    data = fetch_json(f"https://api.semanticscholar.org/graph/v1/paper/search?{params}", timeout)
    works = []
    for item in data.get("data", []) if isinstance(data, dict) else []:
        title = clean_text(item.get("title") or "")
        if not title:
            continue
        external = item.get("externalIds") or {}
        authors = [clean_text(author.get("name") or "") for author in item.get("authors", [])[:12] if isinstance(author, dict)]
        works.append(
            {
                "work_id": stable_id("W", title),
                "title": title,
                "authors": [name for name in authors if name],
                "year": item.get("year"),
                "venue_or_source": clean_text(item.get("venue") or "Semantic Scholar"),
                "url_or_doi": item.get("url") or (f"https://doi.org/{external.get('DOI')}" if external.get("DOI") else ""),
                "doi": clean_doi(external.get("DOI") or ""),
                "arxiv_id": str(external.get("ArXiv") or ""),
                "semantic_scholar_id": str(item.get("paperId") or ""),
                "abstract": clean_text(item.get("abstract") or ""),
                "citation_count": item.get("citationCount"),
                "source_urls": [url for url in [item.get("url"), f"https://doi.org/{external.get('DOI')}" if external.get("DOI") else ""] if url],
                "community_signals": {"source": "semantic_scholar"},
            }
        )
    return works


def arxiv_query(query: str) -> str:
    lower = query.lower()
    if "astro-ph" in lower or "all:" in lower or "cat:" in lower:
        return query
    return " AND ".join(f'all:"{part}"' if " " in part else f"all:{part}" for part in query.split()[:6])
