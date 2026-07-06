from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

WorkSource = Callable[[str, int, float], Sequence[dict[str, Any] | Any]]


@dataclass
class RetrievalConfig:
    use_llm_planner: bool = True
    use_llm_rerank: bool = True
    max_raw_candidates: int = 240
    min_relevance: float = 0.08
    source_names: list[str] | None = None
    max_queries: int = 6
    llm_batch_size: int = 24


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
