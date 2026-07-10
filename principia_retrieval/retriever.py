from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from .models import RetrievalConfig, RetrievalResult, WorkSource
from .planner import QueryPlanner
from .ranking import bm25_rank, embedding_rerank, final_select, has_exact_entity
from .sources import default_sources, fetch_source
from .utils import ordered_unique, strip_internal
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
        embedding_client: Any | None = None,
        callback: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> RetrievalResult:
        target_count = max(1, min(int(target_count or 50), 200))
        config = self.config
        rerank_mode = resolve_rerank_mode(config)
        source_registry = self.sources if sources is None else sources
        planner = QueryPlanner(llm, use_llm=config.use_llm_planner, model_mode="auto")
        query_budget = max(1, config.max_queries)
        plan = planner.plan(goal_text, max_queries=query_budget)
        source_names = config.source_names or list(source_registry)
        queries = ordered_unique(plan.search_queries or [goal_text])[:query_budget]
        if callback:
            callback("query_plan", {"queries": queries, "entities": plan.entities, "domain_hints": plan.domain_hints, "rerank_mode": rerank_mode})

        tasks = [(name, source_registry[name], query) for query in queries for name in source_names if name in source_registry]
        raw_budget = max(1, int(config.max_raw_candidates or 1))
        task_limits = source_task_limits(len(tasks), raw_budget)
        raw_by_task: list[list[dict[str, Any]]] = [[] for _ in tasks]
        with ThreadPoolExecutor(max_workers=min(8, max(1, len(tasks)))) as executor:
            futures = {
                executor.submit(fetch_source, name, source, query, limit, timeout): (index, limit)
                for index, ((name, source, query), limit) in enumerate(zip(tasks, task_limits))
                if limit > 0
            }
            for future in as_completed(futures):
                index, limit = futures[future]
                raw_by_task[index] = future.result()[:limit]
        raw = [item for rows in raw_by_task for item in rows]
        candidates = dedupe_works(raw)
        scored = bm25_rank(goal_text, candidates, plan)
        prefiltered = [item for item in scored if item["_retrieval_score"] >= config.min_relevance or has_exact_entity(item, plan)]
        if not prefiltered:
            prefiltered = scored[: max(target_count, 20)]
        if rerank_mode == "embedding_rerank":
            prefiltered = embedding_rerank(
                goal_text,
                prefiltered[: embedding_rerank_candidate_limit(target_count, config.embedding_rerank_candidate_limit)],
                plan,
                model=config.embedding_model,
                dimensions=config.embedding_dimensions,
                batch_size=config.embedding_batch_size,
                timeout=config.embedding_timeout,
                max_retries=config.embedding_max_retries,
                embedding_client=embedding_client,
            )
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


def embedding_rerank_candidate_limit(target_count: int, configured_limit: int = 0) -> int:
    if int(configured_limit or 0) > 0:
        return max(int(target_count or 0), int(configured_limit or 0))
    return max(int(target_count or 0) * 2, 50)


def source_task_limits(task_count: int, raw_budget: int) -> list[int]:
    if task_count <= 0:
        return []
    base, remainder = divmod(max(0, raw_budget), task_count)
    return [min(25, base + (1 if index < remainder else 0)) for index in range(task_count)]


def resolve_rerank_mode(config: RetrievalConfig) -> str:
    mode = str(getattr(config, "rerank_mode", "") or "").strip().lower()
    if mode in {"embedding", "embedding-rerank", "embedding_rerank"}:
        return "embedding_rerank"
    return "bm25"
