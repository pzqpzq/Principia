from __future__ import annotations

import email.utils
import inspect
import json
import math
import os
import re
import ssl
import threading
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, cast

import certifi
import httpx

from .constants import STOPWORDS, USER_AGENT
from .models import (
    SourceFetchError,
    SourceReport,
    WorkSource,
    control_check_cancelled,
    control_checkpoint,
    control_register_stop_callback,
    control_wait,
)
from .utils import (
    clean_doi,
    clean_text,
    extract_arxiv_id,
    normalize_scholarly_title,
    openalex_abstract,
    stable_id,
    strip_tags,
    truncate,
)
from .works import normalize_work

SOURCE_PROVIDER_TERMS = {
    "arxiv": "https://info.arxiv.org/help/api/tou.html",
    "openalex": "https://openalex.org/OpenAlex_termsofservice.pdf",
    "crossref": "https://www.crossref.org/documentation/retrieve-metadata/",
    "semantic_scholar": "https://www.semanticscholar.org/product/api#api-license",
    "europe_pmc": "https://europepmc.org/developers",
}

_SECRET_QUERY_PARAMETER_RE = re.compile(
    r"(?i)([?&](?:api_key|access_token|token)=)[^&\s]+"
)


def redact_source_error(value: object) -> str:
    """Remove provider credentials from errors before diagnostics persist them."""

    return _SECRET_QUERY_PARAMETER_RE.sub(r"\1<redacted>", str(value))


class _SourceRateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._next_allowed: dict[str, float] = {}

    def wait(self, source: str, interval: float, *, control_token: Any | None = None) -> None:
        interval = max(0.0, float(interval or 0.0))
        control_checkpoint(control_token)
        if interval <= 0:
            return
        now = time.monotonic()
        with self._lock:
            scheduled = max(now, self._next_allowed.get(source, now))
            self._next_allowed[source] = scheduled + interval
        delay = scheduled - now
        if delay > 0:
            control_wait(control_token, delay, checkpoint=True)


_RATE_LIMITER = _SourceRateLimiter()


def default_sources() -> dict[str, WorkSource]:
    return {
        "arxiv": search_arxiv,
        "openalex": search_openalex,
        "crossref": search_crossref,
        "semantic_scholar": search_semantic_scholar,
        "europe_pmc": search_europe_pmc,
    }


def fetch_source(
    name: str,
    source: WorkSource,
    query: str,
    limit: int,
    timeout: float,
    *,
    max_retries: int = 2,
    backoff_seconds: float = 0.5,
    max_backoff_seconds: float = 8.0,
    min_interval_seconds: float = 0.0,
    control_token: Any | None = None,
) -> list[dict[str, Any]]:
    """Fetch and normalize a source, surfacing exhausted failures.

    The five positional arguments are unchanged from v1.3.2.  Callers that
    need observability can use :func:`fetch_source_with_report`.
    """

    rows, report = fetch_source_with_report(
        name,
        source,
        query,
        limit,
        timeout,
        max_retries=max_retries,
        backoff_seconds=backoff_seconds,
        max_backoff_seconds=max_backoff_seconds,
        min_interval_seconds=min_interval_seconds,
        control_token=control_token,
    )
    if report.status == "failed":
        raise SourceFetchError(report)
    return rows


def fetch_source_with_report(
    name: str,
    source: WorkSource,
    query: str,
    limit: int,
    timeout: float,
    *,
    max_retries: int = 2,
    backoff_seconds: float = 0.5,
    max_backoff_seconds: float = 8.0,
    min_interval_seconds: float = 0.0,
    retrieval_round: int = 1,
    control_token: Any | None = None,
) -> tuple[list[dict[str, Any]], SourceReport]:
    normalized_query = normalize_source_query(name, query)
    requested = max(1, int(limit or 1))
    attempts = max(1, int(max_retries or 0) + 1)
    started = time.monotonic()
    last_error: BaseException | None = None
    last_status: int | None = None
    last_retry_after: float | None = None
    actual_attempt = 0
    retry_errors: list[str] = []

    for attempt in range(1, attempts + 1):
        actual_attempt = attempt
        _RATE_LIMITER.wait(name, min_interval_seconds, control_token=control_token)
        try:
            raw_rows = list(
                _invoke_source(
                    source,
                    normalized_query,
                    requested,
                    timeout,
                    control_token=control_token,
                )
                or []
            )
            control_checkpoint(control_token)
            output = normalize_source_rows(name, query, requested, raw_rows)
            report = SourceReport(
                source=name,
                query=query,
                normalized_query=normalized_query,
                requested_count=requested,
                returned_count=len(raw_rows),
                normalized_count=len(output),
                status="success" if output else "empty",
                latency_ms=round((time.monotonic() - started) * 1000.0, 2),
                attempts=attempt,
                retries=attempt - 1,
                retry_errors=retry_errors,
                http_status=last_status,
                retry_after_seconds=last_retry_after,
                retrieval_round=retrieval_round,
            )
            return output, report
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as exc:  # noqa: BLE001 - report arbitrary plugin source failures
            # Cooperative cancellation must not be converted into a normal
            # source-outage report or trigger another paid request.
            control_check_cancelled(control_token)
            last_error = exc
            last_status = exception_http_status(exc)
            last_retry_after = retry_after_seconds(exc)
            retry_errors.append(
                truncate(redact_source_error(f"{type(exc).__name__}: {exc}"), 500)
            )
            if attempt >= attempts or not is_retryable_source_error(exc):
                break
            delay = last_retry_after
            if delay is None:
                delay = min(max_backoff_seconds, backoff_seconds * (2 ** (attempt - 1)))
            if delay > 0:
                control_wait(
                    control_token,
                    min(max_backoff_seconds, delay),
                    checkpoint=True,
                )

    report = SourceReport(
        source=name,
        query=query,
        normalized_query=normalized_query,
        requested_count=requested,
        status="failed",
        latency_ms=round((time.monotonic() - started) * 1000.0, 2),
        attempts=max(1, actual_attempt),
        retries=max(0, actual_attempt - 1),
        error_type=type(last_error).__name__ if last_error else "RuntimeError",
        error=truncate(redact_source_error(last_error or "source request failed"), 500),
        retry_errors=retry_errors,
        http_status=last_status,
        retry_after_seconds=last_retry_after,
        retrieval_round=retrieval_round,
    )
    return [], report


def _invoke_source(
    source: WorkSource,
    query: str,
    limit: int,
    timeout: float,
    *,
    control_token: Any | None = None,
) -> Any:
    """Support both the public positional protocol and legacy keyword adapters."""

    try:
        signature = inspect.signature(source)
        supports_control = "control_token" in signature.parameters or any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )
    except (TypeError, ValueError):
        signature = None
        supports_control = False
    kwargs = {"control_token": control_token} if supports_control else {}
    try:
        if signature is None:
            raise ValueError
        signature.bind(query, limit, timeout, **kwargs)
    except (TypeError, ValueError):
        return source(query, max_results=limit, timeout=timeout, **kwargs)  # type: ignore[call-arg]
    return source(query, limit, timeout, **kwargs)


def normalize_source_rows(
    name: str, original_query: str, limit: int, rows: list[Any]
) -> list[dict[str, Any]]:
    output = []
    for index, row in enumerate(rows, start=1):
        item = normalize_work(row)
        if not item:
            continue
        signals = dict(item.get("community_signals") or item.get("metadata") or {})
        signals.setdefault("source", name)
        signals.setdefault("source_query", original_query)
        signals.setdefault("source_rank", index)
        signals.setdefault("source_limit", limit)
        existing_queries = signals.get("matched_queries") or []
        if isinstance(existing_queries, str):
            existing_queries = [existing_queries]
        signals["matched_queries"] = list(dict.fromkeys([*existing_queries, original_query]))
        query_ranks = dict(signals.get("source_query_ranks") or {})
        previous_rank = query_ranks.get(original_query)
        query_ranks[original_query] = min(int(previous_rank or index), index)
        signals["source_query_ranks"] = query_ranks
        if name in SOURCE_PROVIDER_TERMS:
            signals.setdefault("provider_terms_url", SOURCE_PROVIDER_TERMS[name])
        item["community_signals"] = signals
        item["metadata"] = signals
        if not item.get("source"):
            item["source"] = name
        output.append(item)
    return output


def exception_http_status(exc: BaseException) -> int | None:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code
    code = getattr(exc, "code", None)
    return int(code) if isinstance(code, int) else None


def retry_after_seconds(exc: BaseException) -> float | None:
    value = ""
    if isinstance(exc, httpx.HTTPStatusError):
        value = exc.response.headers.get("Retry-After", "")
    elif hasattr(exc, "headers"):
        value = str(cast(Any, exc).headers.get("Retry-After", ""))
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            parsed = email.utils.parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return max(0.0, (parsed - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


def is_retryable_source_error(exc: BaseException) -> bool:
    status = exception_http_status(exc)
    if status is not None:
        return status in {408, 425, 429} or status >= 500
    return isinstance(
        exc,
        (
            httpx.TimeoutException,
            httpx.NetworkError,
            TimeoutError,
            ConnectionError,
            OSError,
            RuntimeError,
        ),
    )


def normalize_source_query(name: str, query: str) -> str:
    value = clean_text(query)
    if name == "arxiv":
        return arxiv_query(value)
    # Semantic Scholar rejects Boolean syntax and is unusually sensitive to
    # Unicode dashes.  The bibliographic APIs also perform better with focused
    # noun phrases than with prose goals.
    value = re.sub(r"[‐‑‒–—−_-]+", " ", value)
    value = re.sub(r"\b(?:AND|OR|NOT)\b", " ", value, flags=re.I)
    value = clean_text(re.sub(r"[(){}\[\]\"']+", " ", value))
    if name in {"openalex", "crossref", "semantic_scholar", "europe_pmc"}:
        return focused_bibliographic_query(value)
    return value


def focused_bibliographic_query(query: str, *, max_terms: int = 14) -> str:
    tokens = re.findall(
        r"\d+[A-Za-z][A-Za-z0-9.+/]*|[A-Za-z][A-Za-z0-9.+/]*|\d+(?:\.\d+)?", clean_text(query)
    )
    focused = [token for token in tokens if token.lower() not in STOPWORDS]
    return " ".join(focused[: max(3, max_terms)]) or clean_text(query)


def _fetch_bytes(url: str, timeout: float, *, control_token: Any | None = None) -> bytes:
    """Fetch one source response with certifi TLS and active-stop support."""

    control_checkpoint(control_token)
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    client = httpx.Client(
        verify=ssl_context,
        follow_redirects=True,
        timeout=max(0.1, float(timeout or 12.0)),
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json,application/atom+xml,*/*",
        },
    )
    close_transport = getattr(client, "close", None)
    stop_callback = close_transport if callable(close_transport) else lambda: None
    unregister = control_register_stop_callback(control_token, stop_callback)
    try:
        response = client.get(url)
        response.raise_for_status()
        content = response.content
    except BaseException:
        control_check_cancelled(control_token)
        raise
    finally:
        unregister()
        if callable(close_transport):
            close_transport()
    # Pausing here retains the completed response while preventing the next
    # source request from starting.
    control_checkpoint(control_token)
    return content


def _fetch_json(url: str, timeout: float, *, control_token: Any | None = None) -> dict[str, Any]:
    return json.loads(
        _fetch_bytes(url, timeout, control_token=control_token).decode("utf-8", errors="replace")
    )


def search_arxiv(
    query: str,
    limit: int = 20,
    timeout: float = 12,
    *,
    control_token: Any | None = None,
) -> list[dict[str, Any]]:
    search_query = arxiv_query(query)
    params = urllib.parse.urlencode(
        {
            "search_query": search_query,
            "start": 0,
            "max_results": max(1, min(limit, 100)),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
    )
    root = ET.fromstring(
        _fetch_bytes(
            f"https://export.arxiv.org/api/query?{params}",
            timeout,
            control_token=control_token,
        )
    )
    ns = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    works = []
    for entry in root.findall("a:entry", ns):
        title = normalize_scholarly_title(entry.findtext("a:title", default="", namespaces=ns))
        if not title:
            continue
        abstract = clean_text(entry.findtext("a:summary", default="", namespaces=ns))
        url = entry.findtext("a:id", default="", namespaces=ns) or ""
        published = entry.findtext("a:published", default="", namespaces=ns) or ""
        year_match = re.match(r"(\d{4})", published)
        authors = [
            clean_text(author.findtext("a:name", default="", namespaces=ns))
            for author in entry.findall("a:author", ns)
        ]
        pdf_url = ""
        for link in entry.findall("a:link", ns):
            if link.get("title") == "pdf" or link.get("type") == "application/pdf":
                pdf_url = link.get("href") or ""
                break
        works.append(
            {
                "work_id": stable_id("W", title, url),
                "title": title,
                "authors": [name for name in authors if name],
                "year": int(year_match.group(1)) if year_match else None,
                "venue_or_source": "arXiv",
                "url_or_doi": url,
                "paper_link": url,
                "pdf_url": pdf_url,
                "abstract": abstract,
                "arxiv_id": extract_arxiv_id(url),
                "source_urls": [value for value in [url, pdf_url] if value],
                "community_signals": {"source": "arxiv", "is_preprint": True, "type": "preprint"},
            }
        )
    return works


def search_openalex(
    query: str,
    limit: int = 20,
    timeout: float = 12,
    *,
    control_token: Any | None = None,
) -> list[dict[str, Any]]:
    focused = normalize_source_query("openalex", query)
    query_params: dict[str, str | int] = {
        "search": focused,
        "per-page": max(1, min(limit, 100)),
        "sort": "relevance_score:desc",
    }
    api_key = os.getenv("OPENALEX_API_KEY", "").strip()
    if api_key:
        query_params["api_key"] = api_key
    params = urllib.parse.urlencode(query_params)
    data = _fetch_json(
        f"https://api.openalex.org/works?{params}",
        timeout,
        control_token=control_token,
    )
    works = []
    for item in data.get("results", []) if isinstance(data, dict) else []:
        title = normalize_scholarly_title(item.get("title") or item.get("display_name") or "")
        if not title:
            continue
        primary = item.get("primary_location") or {}
        source = (primary.get("source") or {}) if isinstance(primary, dict) else {}
        best_oa = item.get("best_oa_location") or {}
        landing = primary.get("landing_page_url") or item.get("doi") or item.get("id") or ""
        pdf_url = (
            primary.get("pdf_url")
            or (best_oa.get("pdf_url") if isinstance(best_oa, dict) else "")
            or ""
        )
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
                "pdf_url": pdf_url,
                "doi": clean_doi(item.get("doi") or ""),
                "openalex_id": item.get("id") or "",
                "abstract": openalex_abstract(item.get("abstract_inverted_index") or {}),
                "citation_count": item.get("cited_by_count"),
                "source_urls": [
                    url for url in [landing, pdf_url, item.get("doi"), item.get("id")] if url
                ],
                "community_signals": {
                    "source": "openalex",
                    "type": item.get("type", ""),
                    "is_oa": bool(primary.get("is_oa")) if isinstance(primary, dict) else False,
                    "source_score": item.get("relevance_score"),
                },
            }
        )
    return works


def search_crossref(
    query: str,
    limit: int = 20,
    timeout: float = 12,
    *,
    control_token: Any | None = None,
) -> list[dict[str, Any]]:
    focused = normalize_source_query("crossref", query)
    params = urllib.parse.urlencode(
        {
            "query.bibliographic": focused,
            "rows": max(1, min(limit, 100)),
            "sort": "relevance",
            "mailto": "principia-ai@users.noreply.github.com",
        }
    )
    data = _fetch_json(
        f"https://api.crossref.org/works?{params}",
        timeout,
        control_token=control_token,
    )
    items = (
        (((data or {}).get("message") or {}).get("items") or []) if isinstance(data, dict) else []
    )
    works = []
    for item in items:
        title = normalize_scholarly_title(" ".join(item.get("title") or []))
        if not title:
            continue
        year_parts = (
            (
                item.get("published-print")
                or item.get("published-online")
                or item.get("issued")
                or {}
            ).get("date-parts")
            or [[]]
        )[0]
        year = year_parts[0] if year_parts and isinstance(year_parts[0], int) else None
        doi = item.get("DOI") or ""
        url = item.get("URL") or (f"https://doi.org/{doi}" if doi else "")
        links = item.get("link") or []
        pdf_url = next(
            (
                str(link.get("URL") or "")
                for link in links
                if isinstance(link, dict) and "pdf" in str(link.get("content-type") or "").lower()
            ),
            "",
        )
        authors = []
        for author in item.get("author", [])[:12]:
            name = " ".join(
                part for part in [author.get("given", ""), author.get("family", "")] if part
            ).strip()
            if name:
                authors.append(name)
        works.append(
            {
                "work_id": stable_id("W", title),
                "title": title,
                "authors": authors,
                "year": year,
                "venue_or_source": clean_text(
                    " ".join(item.get("container-title") or [])
                    or item.get("publisher")
                    or "Crossref"
                ),
                "url_or_doi": url,
                "pdf_url": pdf_url,
                "doi": clean_doi(doi),
                "abstract": strip_tags(item.get("abstract") or ""),
                "citation_count": item.get("is-referenced-by-count"),
                "source_urls": [value for value in [url, pdf_url] if value],
                "community_signals": {"source": "crossref", "type": item.get("type", "")},
            }
        )
    return works


def search_semantic_scholar(
    query: str,
    limit: int = 20,
    timeout: float = 12,
    *,
    control_token: Any | None = None,
) -> list[dict[str, Any]]:
    focused = normalize_source_query("semantic_scholar", query)
    fields = "title,authors,year,venue,url,abstract,citationCount,externalIds,openAccessPdf"
    params = urllib.parse.urlencode(
        {"query": focused, "limit": max(1, min(limit, 100)), "fields": fields}
    )
    data = _fetch_json(
        f"https://api.semanticscholar.org/graph/v1/paper/search?{params}",
        timeout,
        control_token=control_token,
    )
    works = []
    for item in data.get("data", []) if isinstance(data, dict) else []:
        title = normalize_scholarly_title(item.get("title") or "")
        if not title:
            continue
        external = item.get("externalIds") or {}
        open_pdf = item.get("openAccessPdf") or {}
        pdf_url = str(open_pdf.get("url") or "") if isinstance(open_pdf, dict) else ""
        authors = [
            clean_text(author.get("name") or "")
            for author in item.get("authors", [])[:12]
            if isinstance(author, dict)
        ]
        url = item.get("url") or (
            f"https://doi.org/{external.get('DOI')}" if external.get("DOI") else ""
        )
        works.append(
            {
                "work_id": stable_id("W", title),
                "title": title,
                "authors": [name for name in authors if name],
                "year": item.get("year"),
                "venue_or_source": clean_text(item.get("venue") or "Semantic Scholar"),
                "url_or_doi": url,
                "pdf_url": pdf_url,
                "doi": clean_doi(external.get("DOI") or ""),
                "arxiv_id": str(external.get("ArXiv") or ""),
                "semantic_scholar_id": str(item.get("paperId") or ""),
                "pmid": str(external.get("PubMed") or ""),
                "abstract": clean_text(item.get("abstract") or ""),
                "citation_count": item.get("citationCount"),
                "source_urls": [value for value in [url, pdf_url] if value],
                "community_signals": {"source": "semantic_scholar"},
            }
        )
    return works


def search_europe_pmc(
    query: str,
    limit: int = 20,
    timeout: float = 12,
    *,
    control_token: Any | None = None,
) -> list[dict[str, Any]]:
    focused = normalize_source_query("europe_pmc", query)
    params = urllib.parse.urlencode(
        {
            "query": focused,
            "format": "json",
            "resultType": "core",
            "pageSize": max(1, min(limit, 100)),
        }
    )
    data = _fetch_json(
        f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?{params}",
        timeout,
        control_token=control_token,
    )
    result_list = data.get("resultList") if isinstance(data, dict) else {}
    items = result_list.get("result", []) if isinstance(result_list, dict) else []
    works = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = normalize_scholarly_title(item.get("title") or "")
        if not title:
            continue
        doi = clean_doi(item.get("doi") or "")
        pmid = clean_text(item.get("pmid") or "")
        pmcid = clean_text(item.get("pmcid") or "")
        url = (
            f"https://europepmc.org/article/MED/{pmid}"
            if pmid
            else (
                f"https://europepmc.org/article/PMC/{pmcid}"
                if pmcid
                else (f"https://doi.org/{doi}" if doi else "")
            )
        )
        pdf_url = f"https://europepmc.org/articles/{pmcid}/bin" if pmcid else ""
        authors = [
            clean_text(name)
            for name in re.split(r",|;", item.get("authorString") or "")
            if clean_text(name)
        ]
        year_match = re.search(
            r"\b(19|20)\d{2}\b", str(item.get("pubYear") or item.get("firstPublicationDate") or "")
        )
        works.append(
            {
                "work_id": stable_id("W", title, doi or pmid or pmcid),
                "title": title,
                "authors": authors[:12],
                "year": int(year_match.group(0)) if year_match else None,
                "venue_or_source": clean_text(item.get("journalTitle") or "Europe PMC"),
                "url_or_doi": url,
                "pdf_url": pdf_url,
                "doi": doi,
                "pmid": pmid,
                "abstract": strip_tags(item.get("abstractText") or ""),
                "citation_count": item.get("citedByCount"),
                "source_urls": [
                    value
                    for value in [url, pdf_url, f"https://doi.org/{doi}" if doi else ""]
                    if value
                ],
                "community_signals": {
                    "source": "europe_pmc",
                    "type": item.get("pubType", ""),
                    "pmcid": pmcid,
                    "is_open_access": str(item.get("isOpenAccess") or "").upper() == "Y",
                },
            }
        )
    return works


def arxiv_query(query: str) -> str:
    value = clean_text(query)
    lower = value.lower()
    if "all:" in lower or "cat:" in lower or "ti:" in lower or "abs:" in lower:
        return value
    tokens = [
        token
        for token in re.findall(
            r"\d+[A-Za-z][A-Za-z0-9.+-]*|[A-Za-z][A-Za-z0-9.+-]*|\d+(?:\.\d+)?", value
        )
        if token.lower() not in STOPWORDS
    ][:9]
    if not tokens:
        return "all:" + urllib.parse.quote(value)
    terms = list(dict.fromkeys(tokens))
    if len(terms) <= 3:
        return " OR ".join(f'all:"{term}"' for term in terms)
    # Require evidence from two parts of the focused query while permitting
    # synonyms or wording variation inside each part. This avoids both the old
    # all-term AND recall collapse and the later all-chunk OR precision drift.
    pivot = math.ceil(len(terms) * 0.55)
    left = " OR ".join(f'all:"{term}"' for term in terms[:pivot])
    right = " OR ".join(f'all:"{term}"' for term in terms[pivot:])
    return f"({left}) AND ({right})"
