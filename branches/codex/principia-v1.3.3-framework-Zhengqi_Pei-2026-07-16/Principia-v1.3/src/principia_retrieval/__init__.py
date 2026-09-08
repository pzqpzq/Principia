"""Shared semantic work retrieval utilities for Principia."""

from .models import (
    AllSourcesFailedError,
    InsufficientResultsError,
    QueryPlan,
    RetrievalConfig,
    RetrievalError,
    RetrievalResult,
    SearchDiagnostics,
    SourceFetchError,
    SourceReport,
    WorkSource,
)
from .planner import QueryPlanner, deterministic_query_plan
from .ranking import bm25_rank, deterministic_rank, embedding_rerank, final_select
from .retriever import WorkRetriever
from .sources import (
    default_sources,
    fetch_source,
    fetch_source_with_report,
    normalize_source_query,
    search_arxiv,
    search_crossref,
    search_europe_pmc,
    search_openalex,
    search_semantic_scholar,
)
from .utils import contains_query_trigger, normalize_scholarly_title
from .works import dedupe_works, normalize_work

__all__ = [
    "AllSourcesFailedError",
    "InsufficientResultsError",
    "QueryPlan",
    "QueryPlanner",
    "RetrievalConfig",
    "RetrievalError",
    "RetrievalResult",
    "SearchDiagnostics",
    "SourceFetchError",
    "SourceReport",
    "WorkSource",
    "WorkRetriever",
    "bm25_rank",
    "contains_query_trigger",
    "dedupe_works",
    "default_sources",
    "deterministic_query_plan",
    "deterministic_rank",
    "embedding_rerank",
    "fetch_source",
    "fetch_source_with_report",
    "final_select",
    "normalize_work",
    "normalize_scholarly_title",
    "normalize_source_query",
    "search_arxiv",
    "search_crossref",
    "search_europe_pmc",
    "search_openalex",
    "search_semantic_scholar",
]
