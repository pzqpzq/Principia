from __future__ import annotations

from dataclasses import replace
from typing import Any

from principia_retrieval import QueryPlan, RetrievalConfig, WorkRetriever
from principia_retrieval.ranking import bm25_rank
from principia_retrieval.retriever import _clear_query_plan_cache


class AlternatingPlanner:
    def __init__(self) -> None:
        self.calls = 0

    def available(self, *args: Any, **kwargs: Any) -> bool:
        return True

    def chat_json(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        variant = self.calls
        return {
            "search_queries": [f"planner variant {variant} calibrated sensing"],
            "entities": [f"PlannerVariant{variant}"],
            "key_phrases": ["calibrated sensing"],
            "domain_hints": ["physics"],
            "acronyms": [],
            "scientific_terms": [],
            "synonyms": {},
            "complementary_intents": [],
        }


def retrieval_config() -> RetrievalConfig:
    return RetrievalConfig(
        use_llm_planner=True,
        rerank_mode="bm25",
        max_raw_candidates=1,
        min_relevance=0.0,
        max_queries=3,
        source_max_retries=0,
        source_backoff_seconds=0.0,
        source_min_interval_seconds={},
        max_retrieval_rounds=1,
        candidate_oversample=1.0,
        max_results_per_source_query=1,
    )


def test_identical_search_reuses_canonical_plan_but_refetches_sources() -> None:
    _clear_query_plan_cache()
    planner = AlternatingPlanner()
    source_queries: list[str] = []

    def source(query: str, limit: int, timeout: float) -> list[dict[str, Any]]:
        source_queries.append(query)
        return [
            {
                "work_id": "W-STABLE",
                "title": "Calibrated quantum sensing",
                "abstract": "A calibrated sensing protocol with realistic noise controls.",
                "doi": "10.1234/stable",
                "year": 2025,
            }
        ]

    retriever = WorkRetriever(sources={"fixture": source}, config=retrieval_config())
    first = retriever.search("Broadband calibrated quantum sensing", target_count=1, llm=planner)
    first_queries = list(first.query_plan.search_queries)
    first_network_calls = len(source_queries)
    first.query_plan.search_queries[0] = "caller mutation must not poison cache"

    repeat = retriever.search("Broadband calibrated quantum sensing", target_count=1, llm=planner)

    assert planner.calls == 1
    assert repeat.query_plan.search_queries == first_queries
    assert source_queries[first_network_calls:] == source_queries[:first_network_calls]
    assert len(source_queries) == first_network_calls * 2
    assert first.diagnostics.query_plan["trace"]["planner_cache"]["hit"] is False
    assert repeat.diagnostics.query_plan["trace"]["planner_cache"]["hit"] is True
    assert "goal_facet_score" in repeat.diagnostics.ranking_trace[0]
    assert "abstract_assessability_score" in repeat.diagnostics.ranking_trace[0]


def test_goal_or_retrieval_config_change_invalidates_plan_cache() -> None:
    _clear_query_plan_cache()
    planner = AlternatingPlanner()

    def source(query: str, limit: int, timeout: float) -> list[dict[str, Any]]:
        return [
            {
                "work_id": "W-CACHE-INVALIDATION",
                "title": "Calibrated sensing controls",
                "abstract": "Calibrated sensing controls under uncertainty.",
                "doi": "10.1234/cache-invalidation",
            }
        ]

    base = retrieval_config()
    WorkRetriever(sources={"fixture": source}, config=base).search(
        "Calibrated quantum sensing", target_count=1, llm=planner
    )
    config_changed = WorkRetriever(
        sources={"fixture": source},
        config=replace(base, min_relevance=0.01),
    ).search("Calibrated quantum sensing", target_count=1, llm=planner)
    goal_changed = WorkRetriever(sources={"fixture": source}, config=base).search(
        "Calibrated optical sensing", target_count=1, llm=planner
    )

    assert planner.calls == 3
    assert config_changed.query_plan.trace["planner_cache"]["hit"] is False
    assert goal_changed.query_plan.trace["planner_cache"]["hit"] is False


def test_bm25_ties_are_stable_when_provider_order_changes() -> None:
    plan = QueryPlan(
        goal_text="calibrated sensing",
        search_queries=["calibrated sensing"],
    )
    rows = [
        {
            "work_id": work_id,
            "title": "Calibrated sensing",
            "abstract": "Calibrated sensing under realistic noise.",
            "authors": ["Example Author"],
            "year": 2025,
            "doi": f"10.1234/{work_id.lower()}",
        }
        for work_id in ("W-A", "W-B", "W-C")
    ]

    forward = [row["work_id"] for row in bm25_rank(plan.goal_text, rows, plan)]
    reversed_input = [row["work_id"] for row in bm25_rank(plan.goal_text, rows[::-1], plan)]

    assert forward == reversed_input


def test_repeated_fresh_searches_apply_transparent_top20_stability_anchor() -> None:
    _clear_query_plan_cache()
    calls = 0

    def volatile_source(query: str, limit: int, timeout: float) -> list[dict[str, Any]]:
        nonlocal calls
        calls += 1
        start = 0 if calls == 1 else 20
        return [
            {
                "work_id": f"W-{index}",
                "title": f"Calibrated sensing method {index}",
                "abstract": "Calibrated sensing under realistic noise and controls.",
                "doi": f"10.1234/stability.{index}",
            }
            for index in range(start, start + 20)
        ]

    config = RetrievalConfig(
        use_llm_planner=False,
        min_relevance=0.0,
        max_queries=1,
        max_raw_candidates=20,
        max_retrieval_rounds=1,
        candidate_oversample=1.0,
        source_max_retries=0,
        source_min_interval_seconds={},
    )
    retriever = WorkRetriever(sources={"volatile": volatile_source}, config=config)
    first = retriever.search("calibrated sensing", target_count=20, require_target=True)
    second = retriever.search("calibrated sensing", target_count=20, require_target=True)
    first_ids = {item["doi"] for item in first.selected_works}
    second_ids = {item["doi"] for item in second.selected_works}

    assert calls == 2
    assert len(first_ids & second_ids) / len(first_ids | second_ids) >= 0.70
    assert second.diagnostics.stability_anchor_applied is True
    assert second.diagnostics.stability_anchor_retained == 17
    assert second.diagnostics.stability_anchor_restored == 17
    assert sum(bool(row["stability_anchor"]) for row in second.ranking_trace[:20]) == 17
