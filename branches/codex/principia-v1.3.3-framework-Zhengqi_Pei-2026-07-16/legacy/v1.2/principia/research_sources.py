from __future__ import annotations

import json
import html as html_lib
import re
import shutil
import ssl
import subprocess
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from principia_retrieval import RetrievalConfig, WorkRetriever

from .utils import compact_text, stable_id


USER_AGENT = "Principia-v2/0.2 (local research workspace; mailto:research@example.local)"


def search_hybrid_sources(
    query: str,
    max_results: int = 100,
    timeout: int = 12,
    *,
    llm: Any | None = None,
    original_goal: str | None = None,
    sources: dict[str, Any] | None = None,
    retrieval_rerank_mode: str | None = None,
) -> list[dict[str, Any]]:
    """Search free public metadata sources and return SourceWork-shaped dicts.

    The function intentionally avoids paid/search-engine APIs. It combines arXiv,
    OpenAlex, Crossref, and Semantic Scholar metadata through the shared semantic
    retriever. Queries can use the LLM planner when available. Paper reranking
    defaults to BM25; callers can opt into embedding reranking for the BM25
    head set.
    """

    query = " ".join(str(query or "").split())
    if not query:
        return []
    rerank_mode = _retrieval_rerank_mode(retrieval_rerank_mode)
    config = RetrievalConfig(
        use_llm_planner=llm is not None,
        rerank_mode=rerank_mode,
        max_raw_candidates=max(100, int(max_results or 100) * 4),
        max_queries=8,
    )
    result = WorkRetriever(sources=sources, config=config).search(
        original_goal or query,
        target_count=max_results,
        llm=llm,
        timeout=timeout,
    )
    return result.selected_works


def _retrieval_rerank_mode(value: str | None) -> str:
    mode = str(value or "bm25").strip().lower()
    if mode in {"embedding", "embedding-rerank", "embedding_rerank"}:
        return "embedding_rerank"
    return "bm25"


def fetch_transient_full_text(work: dict[str, Any], *, timeout: int = 14, max_chars: int = 24_000) -> str:
    """Fetch paper text for extraction without persisting the full text locally."""

    for url in _candidate_full_text_urls(work)[:3]:
        try:
            text = _fetch_url_text(url, timeout=timeout, max_chars=max_chars)
        except Exception:
            continue
        if len(text) >= 500:
            return compact_text(_clean_text(text), max_chars)
    return ""


def recover_missing_abstract(work: dict[str, Any], *, timeout: int = 6, max_chars: int = 1800) -> dict[str, Any]:
    """Fill an empty metadata abstract from DOI/landing-page metadata.

    This keeps crawler records useful without storing full text. It only reads
    short HTML metadata fields such as citation_abstract/description.
    """

    if compact_text(work.get("abstract") or "", max_chars):
        return work
    for url in _candidate_full_text_urls(work)[:4]:
        try:
            abstract = _fetch_landing_page_abstract(url, timeout=timeout, max_chars=max_chars)
        except Exception:
            continue
        if abstract:
            updated = dict(work)
            updated["abstract"] = abstract
            urls = _ordered_unique([*(updated.get("source_urls") or []), url])
            updated["source_urls"] = urls
            metadata = dict(updated.get("community_signals") or {})
            metadata["abstract_recovered_from"] = url
            updated["community_signals"] = metadata
            return updated
    return work


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


def _candidate_full_text_urls(work: dict[str, Any]) -> list[str]:
    urls = _ordered_unique(
        [
            work.get("url_or_doi") or "",
            work.get("paper_link") or "",
            *(work.get("source_urls") or []),
        ]
    )
    output: list[str] = []
    for raw_url in urls:
        url = str(raw_url or "").strip()
        if not url:
            continue
        arxiv_id = _extract_arxiv_id(url)
        if arxiv_id:
            output.append(f"https://arxiv.org/pdf/{arxiv_id}")
        output.append(url)
    return _ordered_unique(output)


def _extract_arxiv_id(url: str) -> str:
    match = re.search(r"arxiv\.org/(?:abs|pdf)/([^?#/\s]+)", url, flags=re.IGNORECASE)
    if not match:
        match = re.search(r"\barxiv:([0-9]{4}\.[0-9]{4,5}(?:v\d+)?)", url, flags=re.IGNORECASE)
    return match.group(1).removesuffix(".pdf") if match else ""


def _fetch_url_text(url: str, *, timeout: int, max_chars: int) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/pdf,text/html,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            body = resp.read(12_000_000)
    except Exception as exc:
        if "CERTIFICATE_VERIFY_FAILED" not in repr(exc):
            raise
        with urllib.request.urlopen(req, timeout=timeout, context=ssl._create_unverified_context()) as resp:
            content_type = resp.headers.get("Content-Type", "")
            body = resp.read(12_000_000)
    if "pdf" in content_type.lower() or url.lower().endswith(".pdf") or body[:4] == b"%PDF":
        return _pdf_bytes_to_text(body, max_chars=max_chars)
    html = body.decode("utf-8", errors="replace")
    html = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", html)
    text = _strip_tags(html)
    return compact_text(text, max_chars)


def _fetch_landing_page_abstract(url: str, *, timeout: int, max_chars: int) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            body = resp.read(1_500_000)
    except Exception as exc:
        if "CERTIFICATE_VERIFY_FAILED" not in repr(exc):
            raise
        with urllib.request.urlopen(req, timeout=timeout, context=ssl._create_unverified_context()) as resp:
            content_type = resp.headers.get("Content-Type", "")
            body = resp.read(1_500_000)
    if "html" not in content_type.lower() and not body.lstrip().lower().startswith(b"<!doctype") and b"<html" not in body[:500].lower():
        return ""
    html = body.decode("utf-8", errors="replace")
    for name in ("citation_abstract", "dc.description", "description", "og:description", "twitter:description"):
        value = _html_meta_content(html, name)
        if value and _looks_like_abstract(value):
            return compact_text(value, max_chars)
    json_ld = re.findall(r"(?is)<script[^>]+type=[\"']application/ld\\+json[\"'][^>]*>(.*?)</script>", html)
    for block in json_ld:
        try:
            parsed = json.loads(html_lib.unescape(block.strip()))
        except Exception:
            continue
        candidates = parsed if isinstance(parsed, list) else [parsed]
        for item in candidates:
            if isinstance(item, dict):
                value = str(item.get("description") or item.get("abstract") or "").strip()
                if value and _looks_like_abstract(value):
                    return compact_text(_strip_tags(value), max_chars)
    text = _strip_tags(re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", html))
    match = re.search(r"(?is)\bAbstract\b\s*(.{220,4000}?)(?:\bKeywords\b|\bIntroduction\b|\bReferences\b|$)", text)
    if match:
        value = " ".join(match.group(1).split())
        if _looks_like_abstract(value):
            return compact_text(value, max_chars)
    return ""


def _html_meta_content(html: str, name: str) -> str:
    escaped = re.escape(name)
    patterns = [
        rf"(?is)<meta[^>]+(?:name|property)=[\"']{escaped}[\"'][^>]+content=[\"'](.*?)[\"']",
        rf"(?is)<meta[^>]+content=[\"'](.*?)[\"'][^>]+(?:name|property)=[\"']{escaped}[\"']",
    ]
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            return _strip_tags(html_lib.unescape(match.group(1))).strip()
    return ""


def _looks_like_abstract(value: str) -> bool:
    text = " ".join(str(value or "").split())
    if len(text) < 120:
        return False
    lowered = text.lower()
    if any(term in lowered for term in ("cookie", "javascript", "enable your browser", "access this article")):
        return False
    return True


def _pdf_bytes_to_text(body: bytes, *, max_chars: int) -> str:
    if not body:
        return ""
    if shutil.which("pdftotext"):
        with tempfile.TemporaryDirectory(prefix="principia-fulltext-") as tmpdir:
            pdf_path = Path(tmpdir) / "paper.pdf"
            pdf_path.write_bytes(body)
            result = subprocess.run(
                ["pdftotext", "-layout", str(pdf_path), "-"],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=20,
            )
            if result.returncode == 0 and result.stdout:
                return compact_text(result.stdout.decode("utf-8", errors="replace"), max_chars)
    try:
        from pypdf import PdfReader  # type: ignore

        with tempfile.TemporaryDirectory(prefix="principia-fulltext-") as tmpdir:
            pdf_path = Path(tmpdir) / "paper.pdf"
            pdf_path.write_bytes(body)
            reader = PdfReader(str(pdf_path))
            pages = []
            for page in reader.pages[:24]:
                pages.append(page.extract_text() or "")
                if sum(len(item) for item in pages) >= max_chars:
                    break
            return compact_text(" ".join(pages), max_chars)
    except Exception:
        return ""


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
    text = str(value or "")
    # Repair PDF line-wrap artifacts such as "scien- tific" before collapsing
    # whitespace. Do not touch ordinary in-word hyphens like "test-time".
    text = re.sub(r"(?<=[A-Za-z])-\s+(?=[a-z])", "", text)
    return " ".join(text.split())


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
