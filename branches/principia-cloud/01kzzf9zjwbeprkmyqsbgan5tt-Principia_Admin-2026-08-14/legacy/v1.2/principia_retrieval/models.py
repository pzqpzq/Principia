from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

WorkSource = Callable[[str, int, float], Sequence[dict[str, Any] | Any]]


@dataclass
class RetrievalConfig:
    use_llm_planner: bool = True
    rerank_mode: str = ""
    max_raw_candidates: int = 240
    min_relevance: float = 0.08
    source_names: list[str] | None = None
    max_queries: int = 6
    embedding_model: str = "Qwen/Qwen3-Embedding-4B"
    embedding_dimensions: int = 1024
    embedding_batch_size: int = 32
    embedding_timeout: float = 30.0
    embedding_max_retries: int = 2
    embedding_rerank_candidate_limit: int = 0


@dataclass
class QueryPlan:
    goal_text: str
    search_queries: list[str]
    entities: list[str] = field(default_factory=list)
    key_phrases: list[str] = field(default_factory=list)
    domain_hints: list[str] = field(default_factory=list)
    exclude_terms: list[str] = field(default_factory=list)
    ai_intent: bool = False
    trace: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalResult:
    query_plan: QueryPlan
    candidates: list[dict[str, Any]]
    selected_works: list[dict[str, Any]]
    ranking_trace: list[dict[str, Any]]
