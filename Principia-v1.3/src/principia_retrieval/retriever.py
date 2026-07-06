from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from .models import RetrievalConfig, RetrievalResult, WorkSource
from .planner import QueryPlanner
from .ranking import deterministic_rank, final_select, has_exact_entity, llm_rerank
from .sources import default_sources, fetch_source
from .utils import llm_available, ordered_unique, strip_internal
from .works import dedupe_works


class WorkRetriever:
    def __init__(self, *, sources: dict[str, WorkSource] | None = None, config: RetrievalConfig | None = None) -> None:
        self.sources = default_sources() if sources is None else sources
        self.config = config or RetrievalConfig()

    def search(
        self,
        goal_text: str,
        *,
        target_count: int = 50,
        llm: Any | None = None,
        sources: dict[str, WorkSource] | None = None,
        timeout: float = 12,
        use_llm_rerank: bool | None = None,
        callback: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> RetrievalResult:
        target_count = max(1, min(int(target_count or 50), 200))
        config = self.config
        source_registry = self.sources if sources is None else sources
        planner = QueryPlanner(llm, use_llm=config.use_llm_planner, model_mode="auto")
        plan = planner.plan(goal_text)
        source_names = config.source_names or list(source_registry)
        queries = ordered_unique(plan.search_queries or [goal_text])[: max(1, config.max_queries)]
        if callback:
            callback("query_plan", {"queries": queries, "entities": plan.entities, "domain_hints": plan.domain_hints})

        per_query = max(8, min(25, math.ceil(config.max_raw_candidates / max(1, len(source_names) * len(queries)))))
        raw: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=min(8, max(1, len(source_names) * min(len(queries), 3)))) as executor:
            futures = []
            for name in source_names:
                source = source_registry.get(name)
                if not source:
                    continue
                for query in queries:
                    futures.append(executor.submit(fetch_source, name, source, query, per_query, timeout))
            for future in as_completed(futures):
                raw.extend(future.result())
                if len(raw) >= config.max_raw_candidates * 2:
                    break
        candidates = dedupe_works(raw)
        scored = deterministic_rank(goal_text, candidates, plan)
        prefiltered = [item for item in scored if item["_retrieval_score"] >= config.min_relevance or has_exact_entity(item, plan)]
        if not prefiltered:
            prefiltered = scored[: max(target_count, 20)]
        rerank_enabled = config.use_llm_rerank if use_llm_rerank is None else use_llm_rerank
        if rerank_enabled and llm_available(llm):
            prefiltered = llm_rerank(goal_text, prefiltered[: max(target_count * 4, 60)], plan, llm, batch_size=config.llm_batch_size)
        selected = final_select(prefiltered, target_count, plan)
        trace = [
            {
                "work_id": item.get("work_id", ""),
                "title": item.get("title", ""),
                "score": round(float(item.get("_retrieval_score", 0.0)), 4),
                "relation_label": item.get("relation_label", ""),
                "rationale": item.get("retrieval_rationale", ""),
                "reject_reason": item.get("reject_reason", ""),
            }
            for item in selected
        ]
        public_selected = [strip_internal(item) for item in selected]
        public_candidates = [strip_internal(item) for item in candidates]
        return RetrievalResult(plan, public_candidates, public_selected, trace)
