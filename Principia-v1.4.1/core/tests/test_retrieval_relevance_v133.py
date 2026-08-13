from __future__ import annotations

from itertools import permutations
from time import perf_counter
from typing import Any

from principia_retrieval import QueryPlan
from principia_retrieval.ranking import (
    abstract_assessability_score,
    bm25_rank,
    embedding_rerank,
    final_select,
    goal_facet_score,
    stratified_embedding_candidates,
)

GOAL = (
    "Design communication-efficient LLM multi-agent reasoning with compact learned machine "
    "dialects while preventing representational collapse and preserving causal interpretability."
)


def _plan() -> QueryPlan:
    return QueryPlan(
        goal_text=GOAL,
        search_queries=[
            "communication efficient LLM multi agent reasoning",
            "representational collapse multi-agent LLM communication",
            "causal interpretability multi-agent systems",
        ],
        synonyms={
            "machine dialects": [
                "emergent communication protocols",
                "compact agent representations",
            ]
        },
    )


def _work(work_id: str, title: str, abstract: str) -> dict[str, Any]:
    return {
        "work_id": work_id,
        "title": title,
        "abstract": abstract,
        "authors": ["A. Researcher"],
        "year": 2025,
        "doi": f"10.1234/{work_id.lower()}",
        "url_or_doi": f"https://doi.org/10.1234/{work_id.lower()}",
    }


def test_goal_facet_score_rewards_substantive_target_support() -> None:
    plan = _plan()
    collapse_measurement = _work(
        "collapse",
        "Measuring representational collapse in multi-agent LLM committees",
        "A controlled measurement of representational collapse under inter-agent communication.",
    )
    learned_protocol = _work(
        "protocol",
        "Emergent communication protocols for agent coordination",
        "A compact learned machine dialect reduces communication cost in collaborative reasoning.",
    )
    generic_application = _work(
        "generic",
        "LLM agents for clinical scheduling",
        "An application of language-model agents to hospital appointment scheduling.",
    )

    assert goal_facet_score(collapse_measurement, plan) > goal_facet_score(
        generic_application, plan
    )
    assert goal_facet_score(learned_protocol, plan) > goal_facet_score(generic_application, plan)


class _EqualEmbeddingClient:
    def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


def test_embedding_rerank_prefers_assessable_evidence_when_semantics_tie() -> None:
    plan = _plan()
    sparse = _work("sparse", "Communication-efficient multi-agent reasoning", "")
    rich = _work(
        "rich",
        "Communication-efficient multi-agent reasoning",
        "We evaluate a compact communication protocol with bandwidth controls, collapse metrics, "
        "and causal interventions across multi-agent reasoning tasks. " * 4,
    )

    ranked = embedding_rerank(
        GOAL,
        [sparse, rich],
        plan,
        model="fixture",
        dimensions=2,
        batch_size=16,
        embedding_client=_EqualEmbeddingClient(),
    )

    assert ranked[0]["work_id"] == "rich"
    assert abstract_assessability_score(rich) == 1.0
    assert abstract_assessability_score(sparse) == 0.0


def test_all_ranking_stages_use_stable_identity_tie_breakers() -> None:
    plan = QueryPlan(
        goal_text="quantum sensor calibration",
        search_queries=["quantum sensor calibration"],
    )
    rows = [
        _work(work_id, "Quantum sensor calibration", "Calibration under realistic noise.")
        for work_id in ["c", "a", "b"]
    ]
    expected: list[str] | None = None

    for permuted in permutations(rows):
        ranked = bm25_rank(plan.goal_text, list(permuted), plan)
        embedding_ranked = embedding_rerank(
            plan.goal_text,
            ranked,
            plan,
            model="fixture",
            dimensions=2,
            batch_size=16,
            embedding_client=_EqualEmbeddingClient(),
        )
        pooled = stratified_embedding_candidates(embedding_ranked, 3, plan)
        selected = final_select(pooled, 3, plan)
        identities = [str(row["work_id"]) for row in selected]
        expected = expected or identities
        assert identities == expected


def test_final_selection_keeps_interactive_latency_for_320_papers() -> None:
    plan = QueryPlan(
        goal_text="autonomous scientific discovery",
        search_queries=["autonomous scientific discovery"],
    )
    rows = []
    for index in range(320):
        rows.append(
            {
                "work_id": f"work-{index:03d}",
                "title": f"Autonomous scientific discovery mechanism {index}",
                "abstract": (
                    "agent hypothesis experiment evidence verification discovery "
                    f"facet-{index % 17} "
                )
                * 40,
                "venue_or_source": f"venue-{index % 11}",
                "year": 2020 + index % 6,
                "relation_label": "analogous_to",
                "_retrieval_score": 1.0 - index / 10_000,
            }
        )

    started = perf_counter()
    selected = final_select(rows, 40, plan)
    elapsed = perf_counter() - started

    assert len(selected) == 40
    assert elapsed < 0.75, f"320-paper final selection took {elapsed:.3f}s"
