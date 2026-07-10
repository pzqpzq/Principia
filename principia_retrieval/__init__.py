"""Shared semantic work retrieval utilities for Principia."""

from .models import QueryPlan, RetrievalConfig, RetrievalResult, WorkSource
from .planner import QueryPlanner, deterministic_query_plan
from .ranking import bm25_rank, deterministic_rank, embedding_rerank, final_select
from .retriever import WorkRetriever
from .sources import (
    default_sources,
    fetch_source,
    search_arxiv,
    search_crossref,
    search_openalex,
    search_semantic_scholar,
)
from .utils import contains_query_trigger
from .works import dedupe_works, normalize_work

__all__ = [
    "QueryPlan",
    "QueryPlanner",
    "RetrievalConfig",
    "RetrievalResult",
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
    "final_select",
    "normalize_work",
    "search_arxiv",
    "search_crossref",
    "search_openalex",
    "search_semantic_scholar",
]
