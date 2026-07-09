from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from .models import RetrievalConfig, RetrievalResult, WorkSource
from .planner import QueryPlanner
from .ranking import bm25_rank, embedding_rerank, final_select, has_exact_entity, llm_rerank
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
        embedding_client: Any | None = None,
        callback: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> RetrievalResult:
        target_count = max(1, min(int(target_count or 50), 200))
        config = self.config
        rerank_mode = resolve_rerank_mode(config, use_llm_rerank)
        source_registry = self.sources if sources is None else sources
        planner = QueryPlanner(llm, use_llm=config.use_llm_planner, model_mode="auto")
        query_budget = max(1, config.max_queries)
        plan = planner.plan(goal_text, max_queries=query_budget)
        source_names = config.source_names or list(source_registry)
        queries = ordered_unique(plan.search_queries or [goal_text])[:query_budget]
        if callback:
            callback("query_plan", {"queries": queries, "entities": plan.entities, "domain_hints": plan.domain_hints, "rerank_mode": rerank_mode})

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
        elif rerank_mode == "llm_rerank" and llm_available(llm):
            prefiltered = llm_rerank(goal_text, prefiltered[: llm_rerank_candidate_limit(target_count)], plan, llm, batch_size=config.llm_batch_size)
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


def llm_rerank_candidate_limit(target_count: int) -> int:
    return max(int(target_count or 0) * 2, 50)


def embedding_rerank_candidate_limit(target_count: int, configured_limit: int = 0) -> int:
    if int(configured_limit or 0) > 0:
        return max(int(target_count or 0), int(configured_limit or 0))
    return llm_rerank_candidate_limit(target_count)


def resolve_rerank_mode(config: RetrievalConfig, use_llm_rerank: bool | None = None) -> str:
    if use_llm_rerank is not None:
        return "llm_rerank" if bool(use_llm_rerank) else "bm25"
    mode = str(getattr(config, "rerank_mode", "") or "").strip().lower()
    if mode in {"llm", "llm-rerank", "llm_rerank"}:
        return "llm_rerank"
    if mode in {"embedding", "embedding-rerank", "embedding_rerank"}:
        return "embedding_rerank"
    if mode in {"bm25", "deterministic", "no_llm", "no-llm"}:
        return "bm25"
    return "llm_rerank" if bool(getattr(config, "use_llm_rerank", False)) else "bm25"
