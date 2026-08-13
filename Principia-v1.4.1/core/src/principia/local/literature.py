from __future__ import annotations

import hashlib
import io
import ipaddress
import json
import math
import os
import re
import socket
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
from pypdf import PdfReader

from principia_retrieval import RetrievalConfig

from ..domain import canonical_sha256, monotonic_ulid
from ..models import WorkItem, utc_now
from ..persistence import V14WorkspaceRepository
from ..research import (
    ResearchService,
    coerce_work,
    is_peer_reviewed_work,
    is_preprint_work,
    peer_reviewed_venue,
)

MAX_PAPER_BYTES = 50 * 1024 * 1024
MAX_DATASET_BYTES = 1024 * 1024 * 1024
ALLOWED_FULL_TEXT_TYPES = {
    "application/pdf",
    "text/plain",
    "text/html",
    "application/xml",
    "text/xml",
}
_RELEVANCE_STOPWORDS = {
    "and",
    "are",
    "cause",
    "causes",
    "conditions",
    "do",
    "does",
    "for",
    "from",
    "how",
    "improve",
    "improves",
    "mechanism",
    "mechanisms",
    "produce",
    "reliably",
    "the",
    "their",
    "under",
    "what",
    "when",
    "which",
    "with",
}
_RELEVANCE_WORD = re.compile(r"[a-z0-9]+", flags=re.IGNORECASE)

_DOMAIN_RELEVANCE_PROFILES: list[tuple[re.Pattern[str], re.Pattern[str]]] = [
    (
        re.compile(
            r"\bhilbert(?:'s|s)?\s+sixth\s+problem\b|"
            r"\bsixth\s+problem\s+of\s+hilbert\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bhilbert(?:'s|s)?\s+sixth\s+problem\b|"
            r"\bsixth\s+(?:hilbert\s+)?problem\b|"
            r"\bsixth\s+problem\s+of\s+hilbert\b|"
            r"\bboltzmann(?:'s)?\s+(?:equation|kinetic theory)\b|"
            r"\bhydrodynamic limits?\b|"
            r"\bkinetic theory\b.{0,80}\bfluid equations?\b",
            re.IGNORECASE,
        ),
    ),
    (
        re.compile(
            r"\bautonomous scientific (?:agents?|discovery)\b|"
            r"\bscientific agents?\b|\bAI scientists?\b|\brobot scientists?\b|"
            r"\bself[- ]driving laborator",
            re.IGNORECASE,
        ),
        re.compile(
            r"\bautonomous scientific\b|\bscientific agents?\b|\bAI agents?\b|"
            r"\bautonomous agents?\b|\bagentic\b|\bmulti[- ]?agent\b|"
            r"\bLLMs?\b|\blarge language models?\b|\bself[- ]driving laborator|"
            r"\bscientific discovery\b|\bautonomous workflows?\b|\brobot scientists?\b",
            re.IGNORECASE,
        ),
    ),
    (
        re.compile(r"\bretrieval[- ]augmented generation\b|\bRAG\b", re.IGNORECASE),
        re.compile(
            r"\bretrieval[- ]augmented\b|\bRAG\b|\blarge language model\b|"
            r"\bLLM\b|\bquestion answering\b|\bgenerative (?:AI|model)\b",
            re.IGNORECASE,
        ),
    ),
    (
        re.compile(r"\bmulti[- ]agent\b", re.IGNORECASE),
        re.compile(r"\bmulti[- ]?agent\b|\bagent coordination\b|\bagentic\b", re.IGNORECASE),
    ),
    (
        re.compile(r"\bsuperconducting[- ]qubits?\b", re.IGNORECASE),
        re.compile(r"\bsuperconduct(?:ing|or)?\b|\btransmon\b|\bqubits?\b", re.IGNORECASE),
    ),
    (
        re.compile(r"\bPD[- ]?(?:1|L1)\b|checkpoint[- ]blockade", re.IGNORECASE),
        re.compile(
            r"\bPD[- ]?(?:1|L1)\b|\bimmune checkpoint\b|\bcheckpoint (?:blockade|inhibitor)\b|\bimmunotherap",
            re.IGNORECASE,
        ),
    ),
    (
        re.compile(r"\bLLM(?:s)?\b|\blarge language models?\b", re.IGNORECASE),
        re.compile(
            r"\bLLM(?:s)?\b|\blarge language models?\b|\blanguage model reasoning\b", re.IGNORECASE
        ),
    ),
]


def _domain_relevance(goal: str, item: dict[str, Any]) -> bool | None:
    """Return domain-anchor relevance, or None for an unrecognized goal.

    This deliberately avoids a universal keyword threshold.  It activates only
    for explicit domain phrases where generic homonyms such as radiometric
    "retrieval" are known to produce unsafe default selections.
    """

    text = f"{item.get('title', '')} {item.get('abstract', '')}"
    for goal_pattern, item_pattern in _DOMAIN_RELEVANCE_PROFILES:
        if goal_pattern.search(goal):
            return bool(item_pattern.search(text))
    return None


def _relevance_terms(value: str) -> list[str]:
    terms: list[str] = []
    for raw in _RELEVANCE_WORD.findall(value.casefold()):
        if len(raw) < 3 or raw in _RELEVANCE_STOPWORDS:
            continue
        if len(raw) > 6 and raw.endswith("ing"):
            raw = raw[:-3]
        elif len(raw) > 5 and raw.endswith("ed"):
            raw = raw[:-2]
        elif len(raw) > 5 and raw.endswith("s"):
            raw = raw[:-1]
        terms.append(raw)
    return terms


def _metadata_is_usable(item: dict[str, Any]) -> bool:
    return bool(str(item.get("abstract") or "").strip() or item.get("oa_locations"))


def _stored_work_metadata_is_usable(item: dict[str, Any]) -> bool:
    raw_metadata = item.get("metadata")
    metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
    return bool(
        str(item.get("abstract") or "").strip()
        or str(item.get("arxiv_id") or "").strip()
        or str(metadata.get("pmcid") or metadata.get("pmc_id") or "").strip()
    )


def rank_literature_for_goal(goal: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply a deterministic goal-specific lexical rerank to provider results.

    Provider-native scores are useful for recall but can over-rank papers that
    match one generic word (for example, "material" outside quantum systems).
    Query-term inverse document frequency and a stronger title weight retain
    source ranking as a stable tie-break while suppressing those false friends.
    """

    goal_terms = set(_relevance_terms(goal))
    if not goal_terms or not items:
        return items
    document_terms = [
        set(_relevance_terms(f"{item.get('title', '')} {item.get('abstract', '')}"))
        for item in items
    ]
    document_frequency = {
        term: sum(1 for terms in document_terms if term in terms) for term in goal_terms
    }
    total = len(items)

    hilbert_sixth_goal = bool(_DOMAIN_RELEVANCE_PROFILES[0][0].search(goal))

    def score(item: dict[str, Any]) -> float:
        title_terms = set(_relevance_terms(str(item.get("title") or "")))
        abstract_terms = set(_relevance_terms(str(item.get("abstract") or "")))
        value = 0.0
        for term in goal_terms:
            weight = math.log((total + 1) / (document_frequency[term] + 1)) + 1.0
            if term in title_terms:
                value += 4.0 * weight
            elif term in abstract_terms:
                value += weight
        if hilbert_sixth_goal:
            title = " ".join(_relevance_terms(str(item.get("title") or "")))
            if re.search(r"\bhilbert sixth problem\b|\bsixth hilbert problem\b", title):
                value += 24.0
            elif "sixth problem of hilbert" in title:
                value += 24.0
            if "derivation of fluid equations" in title and "boltzmann" in title:
                value += 12.0
        return value

    def publication_priority(item: dict[str, Any]) -> int:
        status = str(item.get("publication_status") or "")
        return {"published": 2, "preprint": 1}.get(status, 0)

    lexical_scores = {str(item.get("work_id") or id(item)): score(item) for item in items}
    max_lexical = max(lexical_scores.values(), default=0.0)
    max_retrieval_rank = max(
        (int(item.get("retrieval_rank") or item.get("rank") or 1) for item in items),
        default=1,
    )

    def combined_score(item: dict[str, Any]) -> float:
        domain_decision = _domain_relevance(goal, item)
        if domain_decision is False:
            return -1.0
        retrieval_rank = int(item.get("retrieval_rank") or item.get("rank") or 1)
        retrieval = 1.0 - ((retrieval_rank - 1) / max(1, max_retrieval_rank - 1))
        lexical = lexical_scores[str(item.get("work_id") or id(item))] / max(max_lexical, 1e-9)
        # The shared retriever has already applied BM25 or embedding ranking.
        # Preserve that semantic order and use lexical evidence only as a
        # bounded refinement. Exact Hilbert-title recovery is the deliberate
        # exception because namesake Hilbert-space results are common.
        if hilbert_sixth_goal:
            return lexical * 0.72 + retrieval * 0.28
        return retrieval * 0.85 + lexical * 0.15

    ranked = sorted(
        items,
        key=lambda item: (
            -combined_score(item),
            -publication_priority(item),
            int(item.get("retrieval_rank") or item.get("rank") or 0),
            str(item.get("work_id") or ""),
        ),
    )
    for rank, item in enumerate(ranked, start=1):
        item["rank"] = rank
        item["relevance_score"] = round(score(item), 6)
        item["combined_relevance_score"] = round(combined_score(item), 6)
    return ranked


def collapse_literature_editions(
    items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Collapse exact-title publication versions for one search preview.

    DOI-version records and repository revisions can be scientifically the
    same paper while carrying distinct provider identifiers.  They remain
    separate canonical Work observations in storage, but must occupy only one
    selectable slot in a human-facing literature search.
    """

    def normalized(value: object) -> str:
        return " ".join(_RELEVANCE_WORD.findall(str(value or "").casefold()))

    def key(item: dict[str, Any]) -> tuple[str, str]:
        title = normalized(item.get("title"))
        # Exact normalized titles identify display editions even when a
        # double-blind OpenReview record omits authors while an arXiv version
        # names them. Canonical Work observations remain distinct in storage.
        return title, ""

    def preference(item: dict[str, Any]) -> tuple[int, int, int, int, str]:
        publication = {"published": 2, "preprint": 1}.get(
            str(item.get("publication_status") or ""), 0
        )
        return (
            1 if item.get("oa_locations") else 0,
            publication,
            1 if str(item.get("abstract") or "").strip() else 0,
            -int(item.get("retrieval_rank") or item.get("rank") or 0),
            str(item.get("work_id") or ""),
        )

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    order: list[tuple[str, str]] = []
    for item in items:
        identity = key(item)
        if not identity[0]:
            identity = (f"work:{item.get('work_id')}", "")
        if identity not in grouped:
            grouped[identity] = []
            order.append(identity)
        grouped[identity].append(item)

    output: list[dict[str, Any]] = []
    collapsed = 0
    for identity in order:
        variants: list[dict[str, Any]] = grouped[identity]
        ordered_by_preference = sorted(variants, key=preference, reverse=True)
        representative = dict(ordered_by_preference[0])
        collapsed += len(variants) - 1
        representative["retrieval_rank"] = min(
            int(item.get("retrieval_rank") or item.get("rank") or 0) for item in variants
        )
        published = [item for item in variants if item.get("publication_status") == "published"]
        if published:
            best_publication = min(
                published,
                key=lambda item: (
                    int(item.get("retrieval_rank") or item.get("rank") or 0),
                    str(item.get("work_id") or ""),
                ),
            )
            representative["publication_status"] = "published"
            representative["publication_venue"] = best_publication.get(
                "publication_venue"
            ) or best_publication.get("venue")
            representative["venue"] = representative["publication_venue"]
        locations: dict[tuple[str, str], dict[str, Any]] = {}
        for item in variants:
            for location in item.get("oa_locations") or []:
                location_key = (
                    str(location.get("provider") or ""),
                    str(location.get("url") or ""),
                )
                locations[location_key] = dict(location)
        representative["oa_locations"] = [locations[item] for item in sorted(locations)]
        representative["edition_work_ids"] = [
            str(item.get("work_id") or "")
            for item in sorted(
                variants,
                key=lambda item: (
                    int(item.get("retrieval_rank") or item.get("rank") or 0),
                    str(item.get("work_id") or ""),
                ),
            )
        ]
        output.append(representative)
    return output, collapsed


def _default_source_names(goal: str) -> list[str]:
    """Route biomedical-only indexing without polluting other domains.

    Europe PMC is valuable for life-science questions, but its full-text index
    can dominate unrelated physics and computer-science searches with review
    mentions and duplicate repository editions. The general scholarly trio is
    always searched; Europe PMC is added when the question is biomedical.
    """

    names = ["arxiv", "crossref", "semantic_scholar"]
    biomedical_terms = {
        "biomedical",
        "biology",
        "cancer",
        "cell",
        "clinical",
        "disease",
        "drug",
        "gene",
        "genomic",
        "immune",
        "medicine",
        "patient",
        "protein",
        "tumor",
    }
    if set(_relevance_terms(goal)) & biomedical_terms:
        names.append("europe_pmc")
    if re.search(
        r"\b(?:AI|LLM|agentic|multi[- ]agent|machine learning|neural)\b",
        goal,
        flags=re.I,
    ):
        names.append("openreview")
    if os.getenv("OPENALEX_API_KEY"):
        names.append("openalex")
    return names


class ScholarlySearchService:
    """The v1.4 literature contract over the shared v1.3 retrieval engine."""

    def __init__(self, research: ResearchService, repository: V14WorkspaceRepository) -> None:
        self.research = research
        self.repository = repository

    def refresh_publication_metadata(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Refresh display-only venue facts without rerunning or rewriting a search.

        Saved searches outlive ranking and projection improvements.  Recompute
        only their publication labels from the canonical Work records so older
        results immediately benefit while selection, ranks, and diagnostics
        remain byte-for-byte represented by the original search receipt.
        """

        refreshed = dict(payload)
        results: list[dict[str, Any]] = []
        for original in payload.get("results") or []:
            item = dict(original)
            stored = self.repository.work_detail(str(item.get("work_id") or ""))
            if stored is not None:
                projection = self._work_projection(
                    coerce_work(stored), rank=int(item.get("rank") or 0)
                )
                for key in ("venue", "publication_venue", "publication_status"):
                    item[key] = projection[key]
            results.append(item)
        refreshed["results"] = results
        return refreshed

    def search(
        self,
        goal: str,
        *,
        area: str,
        target_count: int = 20,
        timeout: float = 120.0,
        search_id: str = "",
        progress_callback: Callable[[str, dict[str, Any]], None] | None = None,
        cancel_token: Any | None = None,
        embedding_client: Any | None = None,
        excluded_work_ids: set[str] | None = None,
    ) -> dict[str, Any]:
        target = max(1, min(int(target_count or 20), 50))
        pool_target = min(60, max(30, target * 3))
        source_names = _default_source_names(goal)

        def research_progress(status: Any) -> None:
            if progress_callback is None:
                return
            progress_callback(
                str(status.stage),
                {
                    "message": str(status.message),
                    "progress": float(status.progress),
                    "elapsed_seconds": float(status.elapsed_seconds),
                    "eta_seconds": status.eta_seconds,
                    **dict(status.counts),
                },
            )

        works = self.research.search(
            goal,
            target_count=pool_target,
            sources=source_names,
            retrieval_config=RetrievalConfig(
                use_llm_planner=False,
                rerank_mode="embedding_rerank" if embedding_client is not None else "bm25",
                max_raw_candidates=240,
                max_queries=4,
                source_max_retries=1,
                source_backoff_seconds=0.5,
                source_max_backoff_seconds=8.0,
                max_retrieval_rounds=1,
                candidate_oversample=1.0,
                max_results_per_source_query=60,
                require_target=False,
            ),
            require_target=False,
            persist=True,
            timeout=min(20.0, max(5.0, timeout / 6.0)),
            callback=research_progress,
            cancel_token=cancel_token,
            embedding_client=embedding_client,
        )
        if progress_callback is not None:
            progress_callback(
                "ranking",
                {
                    "message": "Ranking the most relevant papers.",
                    "progress": 0.84,
                    "candidate_count": len(works),
                },
            )
        excluded = excluded_work_ids or set()
        items = [
            self._work_projection(work, rank=index + 1)
            for index, work in enumerate(works)
            if work.id not in excluded
        ]
        items, collapsed_editions = collapse_literature_editions(items)
        items = rank_literature_for_goal(goal, items)
        domain_decisions = [_domain_relevance(goal, item) for item in items]
        domain_filter_active = any(decision is not None for decision in domain_decisions)
        excluded_domain_false_friends = 0
        if domain_filter_active:
            retained = [
                item for item, decision in zip(items, domain_decisions, strict=True) if decision
            ]
            excluded_domain_false_friends = len(items) - len(retained)
            items = retained
        usable_items = [item for item in items if _metadata_is_usable(item)]
        metadata_only_items = [item for item in items if not _metadata_is_usable(item)]
        items = [*usable_items, *metadata_only_items]
        for rank, item in enumerate(items, start=1):
            item["rank"] = rank
            item["extractable_metadata"] = _metadata_is_usable(item)
        selected_ids = [item["work_id"] for item in usable_items[:target]]
        alternate_ids = [item["work_id"] for item in usable_items[target : target + 10]]
        diagnostics = works.diagnostics.to_dict()
        diagnostics["principia_domain_relevance"] = {
            "active": domain_filter_active,
            "excluded_false_friends": excluded_domain_false_friends,
            "retained": len(items),
            "target": target,
        }
        diagnostics["usable_metadata_count"] = len(usable_items)
        diagnostics["metadata_only_count"] = len(metadata_only_items)
        diagnostics["collapsed_edition_count"] = collapsed_editions
        diagnostics["excluded_existing_count"] = len(excluded)
        diagnostics["semantic_ranking"] = {
            "requested": embedding_client is not None,
            "applied": diagnostics.get("rerank_mode_applied") == "embedding_rerank",
            "fallback_reason": diagnostics.get("rerank_fallback_reason") or "",
        }
        search_id = search_id or f"search:{monotonic_ulid()}"
        now = utc_now()
        payload: dict[str, Any] = {
            "search_id": search_id,
            "goal": goal,
            "area": area,
            "target_count": target,
            "state": "ready" if selected_ids else "empty",
            "sources": source_names,
            "unavailable_sources": []
            if os.getenv("OPENALEX_API_KEY")
            else [
                {
                    "provider": "openalex",
                    "reason": "OPENALEX_API_KEY is not configured",
                }
            ],
            "results": items[: target + 10],
            "selected_work_ids": selected_ids,
            "alternate_work_ids": alternate_ids,
            "pool_count": len(items),
            "diagnostics": diagnostics,
            "created_at": now,
            "updated_at": now,
        }
        if progress_callback is not None:
            progress_callback(
                "saving",
                {
                    "message": "Saving the ranked paper preview.",
                    "progress": 0.96,
                    "selected_count": len(selected_ids),
                },
            )
        self.repository.save_literature_search(payload, create_goal=False)
        return payload

    def update_selection(self, search_id: str, work_ids: list[str]) -> dict[str, Any]:
        payload = self.repository.literature_search(search_id)
        if payload is None:
            raise KeyError(f"unknown literature search: {search_id}")
        allowed: set[str] = set()
        for item in payload.get("results") or []:
            work_id = str(item["work_id"])
            if _metadata_is_usable(item):
                allowed.add(work_id)
                continue
            # Searches created before result projections carried abstracts and
            # access locations may contain only an ID and title. Consult the
            # canonical Work record so those saved selections remain usable,
            # while genuinely title-only records still fail closed.
            stored_work = self.repository.work_detail(work_id)
            if stored_work is not None and _stored_work_metadata_is_usable(stored_work):
                allowed.add(work_id)
        selected = list(dict.fromkeys(str(item) for item in work_ids))
        if not selected or len(selected) > 50:
            raise ValueError("select between 1 and 50 papers")
        unknown = [item for item in selected if item not in allowed]
        if unknown:
            raise ValueError("selection contains a paper without usable evidence metadata")
        payload["selected_work_ids"] = selected
        payload["updated_at"] = utc_now()
        # Editing a metadata-search selection must remain metadata-only.  A
        # Research Goal is created only when the user explicitly supplies a
        # focus to Principle extraction.
        self.repository.save_literature_search(payload, create_goal=False)
        return payload

    @staticmethod
    def _work_projection(work: WorkItem, *, rank: int) -> dict[str, Any]:
        published_venue = peer_reviewed_venue(work)
        publication_status = (
            "published"
            if is_peer_reviewed_work(work) and published_venue
            else "preprint"
            if is_preprint_work(work)
            else "repository_record"
        )
        return {
            "work_id": work.id,
            "rank": rank,
            "retrieval_rank": rank,
            "title": work.title,
            "authors": work.authors[:12],
            "abstract": work.abstract,
            "published_at": work.published_at,
            "year": work.year,
            "venue": work.venue,
            "publication_venue": published_venue,
            "publication_status": publication_status,
            "source": work.source,
            "url": work.url,
            "doi": work.doi,
            "arxiv_id": work.arxiv_id,
            "pmid": work.pmid,
            "pdf_url": work.pdf_url,
            "citation_count": work.citation_count,
            "oa_locations": open_access_locations(work),
        }


def open_access_locations(work: WorkItem) -> list[dict[str, Any]]:
    """Return only locations with a source-specific public access basis."""

    output: list[dict[str, Any]] = []
    arxiv_id = str(work.arxiv_id or "").strip()
    if arxiv_id:
        output.append(
            {
                "provider": "arxiv",
                "url": f"https://arxiv.org/pdf/{arxiv_id}.pdf",
                "access_basis": "arxiv_public_full_text",
                "manuscript_version": "author_preprint",
                "license": str(work.metadata.get("license") or "arxiv-distribution"),
                "is_open_access": True,
            }
        )
    pmcid = str(work.metadata.get("pmcid") or work.metadata.get("pmc_id") or "").strip()
    if pmcid:
        output.append(
            {
                "provider": "europe_pmc",
                "url": f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML",
                "access_basis": "europe_pmc_open_access",
                "manuscript_version": str(
                    work.metadata.get("manuscript_version") or "repository_copy"
                ),
                "license": str(work.metadata.get("license") or "repository-recorded"),
                "is_open_access": True,
            }
        )
    if str(work.source or "").casefold() == "openreview" and str(work.pdf_url or "").strip():
        output.append(
            {
                "provider": "openreview",
                "url": str(work.pdf_url),
                "access_basis": "openreview_public_submission",
                "manuscript_version": (
                    "version_of_record"
                    if bool(work.metadata.get("is_peer_reviewed"))
                    else "public_submission"
                ),
                "license": str(work.metadata.get("license") or "repository-recorded"),
                "is_open_access": True,
            }
        )
    # Crossref and Semantic Scholar URLs deliberately remain metadata hints.
    return output


class SafeLiteratureAcquirer:
    """Fail-closed OA downloader with redirect and network-boundary validation."""

    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        resolver: Callable[[str], list[str]] | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.client = httpx.Client(
            transport=transport,
            timeout=httpx.Timeout(timeout, connect=10.0),
            follow_redirects=False,
            headers={"User-Agent": "Principia/1.4 literature-acquirer"},
        )
        self.resolver = resolver or self._resolve

    @staticmethod
    def _resolve(host: str) -> list[str]:
        return list(
            dict.fromkeys(
                str(item[4][0]) for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            )
        )

    def _validate_url(self, url: str) -> None:
        parsed = urlsplit(url)
        if parsed.scheme.lower() != "https":
            raise ValueError("literature acquisition requires HTTPS")
        if parsed.username or parsed.password:
            raise ValueError("credential-bearing literature URLs are forbidden")
        if not parsed.hostname:
            raise ValueError("literature URL has no host")
        host = parsed.hostname.rstrip(".").casefold()
        if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
            raise ValueError("loopback literature destinations are forbidden")
        try:
            addresses = self.resolver(host)
        except OSError as exc:
            raise ValueError("literature destination could not be resolved") from exc
        if not addresses:
            raise ValueError("literature destination resolved to no address")
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if not ip.is_global:
                raise ValueError(
                    "private, loopback, or link-local literature destinations are forbidden"
                )

    def download(self, location: dict[str, Any], *, dataset_bytes: int = 0) -> dict[str, Any]:
        if not location.get("is_open_access") or not location.get("access_basis"):
            raise PermissionError("full text requires a recorded open-access basis")
        url = str(location.get("url") or "")
        body = bytearray()
        response: httpx.Response | None = None
        for _ in range(6):
            self._validate_url(url)
            with self.client.stream("GET", url) as current:
                if current.status_code in {301, 302, 303, 307, 308}:
                    redirect = current.headers.get("location")
                    if not redirect:
                        raise ValueError("literature redirect omitted Location")
                    url = urljoin(url, redirect)
                    continue
                current.raise_for_status()
                media_type = (
                    current.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                )
                if media_type not in ALLOWED_FULL_TEXT_TYPES:
                    raise ValueError(f"unsupported literature MIME type: {media_type or 'missing'}")
                declared = int(current.headers.get("content-length") or 0)
                if declared > MAX_PAPER_BYTES or dataset_bytes + declared > MAX_DATASET_BYTES:
                    raise ValueError("literature download exceeds the configured byte limit")
                for chunk in current.iter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_PAPER_BYTES or dataset_bytes + len(body) > MAX_DATASET_BYTES:
                        raise ValueError("literature download exceeds the configured byte limit")
                response = current
                break
        else:
            raise ValueError("literature redirect limit exceeded")
        if response is None:
            raise ValueError("literature acquisition did not produce a response")
        media_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        text, pages = normalize_acquired_content(bytes(body), media_type)
        return {
            "final_url": url,
            "mime_type": media_type,
            "bytes": bytes(body),
            "text": text,
            "pages": pages,
            "byte_size": len(body),
            "byte_sha256": hashlib.sha256(body).hexdigest(),
            "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "access_basis": location["access_basis"],
            "manuscript_version": location.get("manuscript_version", ""),
            "license": location.get("license", ""),
        }


def normalize_acquired_content(body: bytes, media_type: str) -> tuple[str, list[dict[str, Any]]]:
    if media_type == "application/pdf":
        reader = PdfReader(io.BytesIO(body))
        if reader.is_encrypted:
            raise ValueError("encrypted PDFs are not accepted")
        pages: list[dict[str, Any]] = []
        for index, page in enumerate(reader.pages, start=1):
            text = "\n".join(
                line.rstrip() for line in (page.extract_text() or "").splitlines()
            ).strip()
            if text:
                pages.append({"page": index, "section": "page", "text": text})
        normalized = "\n\n".join(item["text"] for item in pages)
    else:
        decoded = body.decode("utf-8", errors="strict")
        if media_type in {"text/html", "application/xml", "text/xml"}:
            decoded = re.sub(r"<script\b[^>]*>.*?</script>", " ", decoded, flags=re.I | re.S)
            decoded = re.sub(r"<style\b[^>]*>.*?</style>", " ", decoded, flags=re.I | re.S)
            decoded = re.sub(r"<[^>]+>", " ", decoded)
        normalized = re.sub(r"[ \t]+", " ", decoded)
        normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
        pages = [{"page": None, "section": "full_text", "text": normalized}] if normalized else []
    if not normalized.strip():
        raise ValueError("acquired literature contained no extractable text")
    return normalized, pages


def write_private_acquisition(
    root: Path,
    *,
    work_id: str,
    acquired: dict[str, Any],
    relative_stem: str = "",
    metadata: dict[str, Any] | None = None,
    derived_root: Path | None = None,
) -> dict[str, str]:
    """Materialize raw source bytes separately from rebuildable workspace data.

    ``root`` is the user-owned Local data folder and receives only the acquired
    representation. Parsed/normalized text and Principia metadata are written
    below ``derived_root`` when supplied.
    """

    safe_id = hashlib.sha256(work_id.encode()).hexdigest()[:24]
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    stem = re.sub(r"[^a-z0-9-]+", "-", relative_stem.casefold()).strip("-")[:96]
    stem = stem or f"work-{safe_id}"
    # Layout v2 keeps every representation of one scholarly Work together.
    # Users no longer have to reconcile parallel papers/abstracts/text/metadata
    # directories to understand what was actually acquired.
    document_root = root / "papers" / f"{stem}-{safe_id[:8]}"
    if acquired["mime_type"] == "application/pdf":
        raw_path = document_root / "paper.pdf"
    elif acquired.get("content_kind") == "full_text":
        raw_path = document_root / "full-text.txt"
    else:
        raw_path = document_root / "abstract.txt"
    derived_document_root = (
        Path(derived_root).expanduser().resolve() / f"{stem}-{safe_id[:8]}"
        if derived_root is not None
        else document_root
    )
    if derived_root is not None:
        Path(derived_root).expanduser().resolve().mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(Path(derived_root).expanduser().resolve(), 0o700)
    text_path = derived_document_root / "normalized.txt"
    metadata_path = derived_document_root / "metadata.json"
    for parent in {raw_path.parent, text_path.parent, metadata_path.parent}:
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(parent, 0o700)

    def atomic_write(path: Path, body: bytes) -> None:
        if path.exists():
            if hashlib.sha256(path.read_bytes()).hexdigest() == hashlib.sha256(body).hexdigest():
                return
            raise FileExistsError(
                f"private source file already exists with different bytes: {path.name}"
            )
        partial = path.with_name(f".{path.name}.{safe_id}.partial")
        descriptor = os.open(partial, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(body)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(partial, path)
            os.chmod(path, 0o600)
        finally:
            partial.unlink(missing_ok=True)

    atomic_write(raw_path, acquired["bytes"])
    atomic_write(text_path, acquired["text"].encode())
    metadata_payload = {
        **(metadata or {}),
        "work_id": work_id,
        "content_kind": acquired.get("content_kind", "full_text"),
        "byte_sha256": acquired["byte_sha256"],
        "text_sha256": acquired["text_sha256"],
        "access_basis": acquired.get("access_basis", ""),
        "manuscript_version": acquired.get("manuscript_version", ""),
        "license": acquired.get("license", ""),
    }
    atomic_write(
        metadata_path,
        (
            json.dumps(metadata_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode(),
    )
    return {
        "raw_path": str(raw_path),
        "text_path": str(text_path),
        "metadata_path": str(metadata_path),
        "document_path": str(document_root),
        "derived_document_path": str(derived_document_root),
        "raw_relative_path": raw_path.relative_to(root).as_posix(),
        "text_relative_path": (
            text_path.relative_to(Path(derived_root).expanduser().resolve()).as_posix()
            if derived_root is not None
            else text_path.relative_to(root).as_posix()
        ),
        "document_relative_path": document_root.relative_to(root).as_posix(),
        "logical_digest": canonical_sha256(
            {
                "work_id": work_id,
                "byte_sha256": acquired["byte_sha256"],
                "text_sha256": acquired["text_sha256"],
            }
        ),
    }
