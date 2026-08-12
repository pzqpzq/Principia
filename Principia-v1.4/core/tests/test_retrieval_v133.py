from __future__ import annotations

import urllib.parse
from typing import Any

import httpx
import pytest

from principia_retrieval import (
    AllSourcesFailedError,
    InsufficientResultsError,
    QueryPlan,
    RetrievalConfig,
    WorkRetriever,
    default_sources,
    deterministic_query_plan,
    fetch_source_with_report,
    normalize_source_query,
)
from principia_retrieval import sources as source_module
from principia_retrieval.ranking import (
    bm25_rank,
    embedding_rerank,
    final_select,
    has_exact_entity,
    stratified_embedding_candidates,
)
from principia_retrieval.retriever import embedding_rerank_candidate_limit, resolve_source_names
from principia_retrieval.utils import normalize_scholarly_title, tokenize
from principia_retrieval.works import dedupe_works, normalize_work


def work(index: int, *, query: str = "quantum sensing") -> dict[str, Any]:
    return {
        "title": f"{query.title()} Method {index}",
        "authors": [f"Researcher {index}"],
        "year": 2024,
        "abstract": f"A study of {query}, uncertainty, controls, and validation protocol {index}.",
        "doi": f"10.1234/example.{index}",
        "url": f"https://doi.org/10.1234/example.{index}",
    }


def config(**overrides: Any) -> RetrievalConfig:
    values: dict[str, Any] = {
        "use_llm_planner": False,
        "max_queries": 1,
        "max_raw_candidates": 20,
        "candidate_oversample": 1.0,
        "max_retrieval_rounds": 3,
        "source_max_retries": 0,
        "source_backoff_seconds": 0.0,
        "source_min_interval_seconds": {},
        "min_relevance": 0.0,
    }
    values.update(overrides)
    return RetrievalConfig(**values)


def test_openreview_search_preserves_accepted_venue_and_public_pdf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        source_module,
        "_fetch_json",
        lambda *args, **kwargs: {
            "notes": [
                {
                    "id": "paper-id",
                    "odate": 1738368000000,
                    "license": "CC BY 4.0",
                    "content": {
                        "title": {"value": "Multi-Agent Verification for Scientific Discovery"},
                        "abstract": {"value": "Specialized agents verify generated hypotheses."},
                        "authors": {"value": ["A. Scientist", "B. Researcher"]},
                        "venue": {"value": "Published as a conference paper at ICLR 2025"},
                        "venueid": {"value": "ICLR.cc/2025/Conference/Accepted_Submission"},
                        "pdf": {"value": "/pdf/example.pdf"},
                    },
                }
            ]
        },
    )

    rows = source_module.search_openreview("multi agent scientific discovery", limit=5)

    assert len(rows) == 1
    assert rows[0]["venue_or_source"] == "Published as a conference paper at ICLR 2025"
    assert rows[0]["pdf_url"] == "https://openreview.net/pdf/example.pdf"
    assert rows[0]["community_signals"]["is_peer_reviewed"] is True
    assert rows[0]["community_signals"]["peer_reviewed_venue"] == "ICLR 2025"


def test_published_edition_wins_venue_while_retaining_preprint_provenance() -> None:
    rows = dedupe_works(
        [
            normalize_work(
                {
                    "title": "Many Heads Are Better Than One",
                    "authors": ["A. Scientist"],
                    "venue_or_source": "OpenReview",
                    "source_type": "preprint",
                    "url_or_doi": "https://openreview.net/forum?id=example",
                    "pdf_url": "https://openreview.net/pdf?id=example",
                    "community_signals": {
                        "source": "openreview",
                        "is_preprint": True,
                        "publication_type": "preprint",
                    },
                }
            ),
            normalize_work(
                {
                    "title": "Many Heads Are Better Than One",
                    "authors": ["A. Scientist"],
                    "venue_or_source": "ACL 2025",
                    "source_type": "conference-paper",
                    "url_or_doi": "https://aclanthology.org/2025.example",
                    "community_signals": {
                        "source": "crossref",
                        "type": "proceedings-article",
                    },
                }
            ),
        ]
    )

    assert len(rows) == 1
    assert rows[0]["venue_or_source"] == "ACL 2025"
    assert rows[0]["community_signals"]["has_preprint"] is True
    assert rows[0]["community_signals"]["is_peer_reviewed"] is True
    assert rows[0]["community_signals"]["peer_reviewed_venue"] == "ACL 2025"


def test_source_title_normalization_removes_namespaced_mathml_without_damaging_latex() -> None:
    raw_title = (
        'Axion haloscope array with <mml:math xmlns:mml="http://www.w3.org/1998/Math/MathML">'
        "<mml:msub><mml:mi>N</mml:mi><mml:mi>a</mml:mi></mml:msub>"
        "<mml:mo>×</mml:mo><mml:mi>B</mml:mi></mml:math> detectors"
    )
    expected = "Axion haloscope array with Na×B detectors"

    assert normalize_scholarly_title(raw_title) == expected
    assert normalize_work({"title": raw_title, "doi": "10.1000/example"})["title"] == expected

    latex_title = r"Bounds on $m_a < 5\,\mathrm{eV}$ from $g_{a\gamma}$"
    assert normalize_scholarly_title(latex_title) == latex_title


def test_default_candidate_pool_uses_stability_oversampling() -> None:
    assert RetrievalConfig().candidate_oversample == 3.0


@pytest.mark.parametrize("api_key", ["", "openalex_unit_test_key"])
def test_openalex_uses_optional_api_key_without_legacy_mailto(
    monkeypatch: pytest.MonkeyPatch, api_key: str
) -> None:
    captured: dict[str, str] = {}

    def fake_fetch_json(
        url: str, timeout: float, *, control_token: Any | None = None
    ) -> dict[str, Any]:
        captured["url"] = url
        return {"results": []}

    if api_key:
        monkeypatch.setenv("OPENALEX_API_KEY", api_key)
    else:
        monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    monkeypatch.setattr(source_module, "_fetch_json", fake_fetch_json)

    assert source_module.search_openalex("quantum sensing", limit=3) == []
    params = urllib.parse.parse_qs(urllib.parse.urlsplit(captured["url"]).query)
    assert "mailto" not in params
    assert params.get("api_key", []) == ([api_key] if api_key else [])


def test_source_report_redacts_api_key_from_persisted_errors() -> None:
    sensitive = "openalex_unit_test_sensitive_value"

    def failing(query: str, limit: int, timeout: float) -> list[dict[str, Any]]:
        request = httpx.Request(
            "GET", f"https://api.openalex.org/works?api_key={sensitive}&search=test"
        )
        response = httpx.Response(403, request=request)
        response.raise_for_status()
        return []

    rows, report = fetch_source_with_report(
        "openalex",
        failing,
        "quantum sensing",
        3,
        1,
        max_retries=0,
        backoff_seconds=0.0,
    )

    serialized = str(report.to_dict())
    assert rows == []
    assert report.status == "failed"
    assert sensitive not in serialized
    assert "api_key=<redacted>" in serialized


def test_source_fetch_retries_and_reports_retry_after() -> None:
    calls = 0

    def flaky(query: str, limit: int, timeout: float) -> list[dict[str, Any]]:
        nonlocal calls
        calls += 1
        if calls == 1:
            request = httpx.Request("GET", "https://example.test")
            response = httpx.Response(429, headers={"Retry-After": "0"}, request=request)
            raise httpx.HTTPStatusError("rate limited", request=request, response=response)
        return [work(1)]

    rows, report = fetch_source_with_report(
        "mock",
        flaky,
        "quantum sensing",
        5,
        1,
        max_retries=2,
        backoff_seconds=0,
    )

    assert len(rows) == 1
    assert report.status == "success"
    assert report.attempts == 2
    assert report.retries == 1
    assert report.http_status == 429
    assert report.retry_errors and "rate limited" in report.retry_errors[0]
    assert calls == 2


def test_partial_source_failure_is_explicit_but_returns_results() -> None:
    def good(query: str, limit: int, timeout: float) -> list[dict[str, Any]]:
        return [work(1)]

    def broken(query: str, limit: int, timeout: float) -> list[dict[str, Any]]:
        raise RuntimeError("provider unavailable")

    result = WorkRetriever(sources={"good": good, "broken": broken}, config=config()).search(
        "quantum sensing", target_count=1
    )

    assert result.diagnostics.complete is True
    assert result.diagnostics.degraded is True
    assert result.diagnostics.successful_sources == ["good"]
    assert any(
        report.status == "failed" and report.source == "broken"
        for report in result.diagnostics.source_reports
    )
    assert "Partial metadata-source failure" in result.diagnostics.warnings[0]


def test_total_source_failure_raises_with_diagnostics() -> None:
    def broken(query: str, limit: int, timeout: float) -> list[dict[str, Any]]:
        raise RuntimeError("network down")

    with pytest.raises(AllSourcesFailedError) as caught:
        WorkRetriever(sources={"broken": broken}, config=config()).search(
            "quantum sensing", target_count=3
        )

    assert caught.value.diagnostics.degraded is True
    assert caught.value.diagnostics.source_reports[0].error == "network down"


def test_adaptive_round_top_up_meets_strict_unique_target() -> None:
    def overlapping_pages(query: str, limit: int, timeout: float) -> list[dict[str, Any]]:
        shared = [work(index, query="quantum sensing") for index in range(3)]
        suffix = abs(sum(ord(char) for char in query)) % 1000
        extras = [work(suffix + index, query="quantum sensing") for index in range(3, limit)]
        return [*shared, *extras][:limit]

    result = WorkRetriever(
        sources={"paged": overlapping_pages},
        config=config(max_queries=2, max_raw_candidates=6),
    ).search("quantum sensing uncertainty controls", target_count=6, require_target=True)

    assert len(result.selected_works) == 6
    assert result.diagnostics.complete is True
    assert result.diagnostics.completeness == 1.0
    assert result.diagnostics.retrieval_rounds >= 2


def test_adaptive_rounds_accumulate_shifted_provider_pages() -> None:
    calls = 0

    def shifting_pages(query: str, limit: int, timeout: float) -> list[dict[str, Any]]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return [work(1), work(2)]
        return [work(1), work(3), work(4)]

    result = WorkRetriever(
        sources={"shifting": shifting_pages},
        config=config(
            max_queries=1,
            max_raw_candidates=2,
            candidate_oversample=2.0,
            max_retrieval_rounds=2,
        ),
    ).search("quantum sensing", target_count=3, require_target=True)

    candidate_dois = {item["doi"] for item in result.candidates}
    assert "10.1234/example.2" in candidate_dois
    assert len(result.candidates) == 4
    assert result.diagnostics.retrieval_rounds == 2


def test_strict_target_underfill_raises_with_partial_result() -> None:
    def tiny(query: str, limit: int, timeout: float) -> list[dict[str, Any]]:
        return [work(1), work(2)]

    with pytest.raises(InsufficientResultsError) as caught:
        WorkRetriever(sources={"tiny": tiny}, config=config()).search(
            "quantum sensing", target_count=5, require_target=True
        )

    assert len(caught.value.result.selected_works) == 2
    assert caught.value.diagnostics.completeness == 0.4
    assert caught.value.diagnostics.complete is False


class WorkingEmbeddingClient:
    def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        return [[1.0, float(index + 1)] for index, _ in enumerate(texts)]


class BrokenEmbeddingClient:
    def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        raise RuntimeError("embedding endpoint unavailable")


def many(query: str, limit: int, timeout: float) -> list[dict[str, Any]]:
    return [work(index) for index in range(min(limit, 8))]


def test_embedding_rerank_reports_applied_state() -> None:
    result = WorkRetriever(
        sources={"many": many},
        config=config(rerank_mode="embedding", embedding_dimensions=2),
    ).search("quantum sensing", target_count=3, embedding_client=WorkingEmbeddingClient())

    assert result.diagnostics.rerank_mode_requested == "embedding_rerank"
    assert result.diagnostics.rerank_mode_applied == "embedding_rerank"
    assert result.diagnostics.rerank_fallback_reason == ""
    assert all(row["embedding_similarity"] is not None for row in result.ranking_trace)


def test_embedding_rerank_reports_fallback_state() -> None:
    result = WorkRetriever(
        sources={"many": many},
        config=config(rerank_mode="embedding", embedding_dimensions=2),
    ).search("quantum sensing", target_count=3, embedding_client=BrokenEmbeddingClient())

    assert result.diagnostics.rerank_mode_requested == "embedding_rerank"
    assert result.diagnostics.rerank_mode_applied == "bm25"
    assert "embedding endpoint unavailable" in result.diagnostics.rerank_fallback_reason
    assert result.diagnostics.degraded is True


def test_cross_domain_query_normalization_and_biomedical_routing() -> None:
    semantic = normalize_source_query(
        "semantic_scholar", 'uncertainty-aware AND "sparse-view" 3D reconstruction'
    )
    arxiv = normalize_source_query(
        "arxiv", "uncertainty-aware sparse-view dynamic 3D reconstruction Gaussian splatting"
    )
    biomedical = deterministic_query_plan(
        "Clinical protein biomarkers for cancer patients and drug therapy"
    )
    routed = resolve_source_names(
        RetrievalConfig(), default_sources(), biomedical.domain_hints, False
    )

    assert "AND" not in semantic
    assert "-" not in semantic
    assert "3D" in semantic
    assert " OR " in arxiv
    assert "europe_pmc" in routed


def test_diagnostics_are_serializable_and_include_plan_and_trace() -> None:
    result = WorkRetriever(sources={"many": many}, config=config()).search(
        "quantum sensing", target_count=2
    )
    payload = result.diagnostics.to_dict()

    assert payload["query_plan"]["goal_text"] == "quantum sensing"
    assert len(payload["ranking_trace"]) == 2
    assert payload["source_reports"][0]["status"] == "success"
    assert payload["complete"] is True


def test_generic_entity_does_not_force_exact_match_or_direct_relation() -> None:
    generic_plan = QueryPlan(
        goal_text="efficient multi agent LLM communication",
        search_queries=["multi agent LLM communication protocol"],
        entities=["LLM"],
        key_phrases=["communication protocol"],
    )
    rows = bm25_rank(
        generic_plan.goal_text,
        [
            work(1, query="multi agent LLM communication"),
            work(2, query="generic LLM application"),
        ],
        generic_plan,
    )

    assert all(row["_exact_entity_score"] == 0 for row in rows)
    assert all(has_exact_entity(row, generic_plan) is False for row in rows)

    rare_plan = QueryPlan(
        goal_text="follow-up of S251112cm",
        search_queries=["S251112cm optical transient"],
        entities=["S251112cm"],
    )
    rare = bm25_rank(
        rare_plan.goal_text,
        [{"title": "Optical follow-up of S251112cm", "abstract": "Transient analysis."}],
        rare_plan,
    )[0]
    assert rare["_exact_entity_score"] > 0.5
    assert has_exact_entity(rare, rare_plan) is True


class AspectEmbeddingClient:
    def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        vectors = []
        for text in texts:
            lower = text.lower()
            if lower.startswith("instruct:") and "research aspect" in lower:
                vectors.append([0.0, 1.0])
            elif lower.startswith("instruct:"):
                vectors.append([1.0, 0.0])
            elif "learned protocol mechanism" in lower:
                vectors.append([0.7, 0.7])
            else:
                vectors.append([1.0, 0.0])
        return vectors


def test_multi_aspect_embedding_rerank_rewards_material_facet_match() -> None:
    plan = QueryPlan(
        goal_text="collaborative reasoning with efficient communication",
        search_queries=[
            "collaborative reasoning efficient communication",
            "learned protocol mechanism",
            "failure analysis coordination",
        ],
    )
    rows = embedding_rerank(
        plan.goal_text,
        [
            {
                "work_id": "generic",
                "title": "Collaborative reasoning systems",
                "abstract": "A broad overview of reasoning applications.",
            },
            {
                "work_id": "facet",
                "title": "Learned protocol mechanism for collaboration",
                "abstract": "An evaluated learned protocol mechanism for efficient communication.",
            },
        ],
        plan,
        model="fixture",
        dimensions=2,
        batch_size=16,
        embedding_client=AspectEmbeddingClient(),
    )

    assert rows[0]["work_id"] == "facet"
    assert rows[0]["_embedding_aspect_similarity"] > rows[1]["_embedding_aspect_similarity"]
    assert "best research-aspect match" in rows[0]["retrieval_rationale"]


def test_assessable_abstract_materially_improves_otherwise_equal_rank() -> None:
    plan = QueryPlan(
        goal_text="catalyst degradation controls",
        search_queries=["catalyst degradation controls"],
    )
    rich = work(1, query="catalyst degradation controls")
    sparse = work(2, query="catalyst degradation controls")
    rich["title"] = sparse["title"] = "Catalyst degradation controls"
    rich["abstract"] = (
        "Catalyst degradation controls under realistic temperature and uncertainty. " * 20
    )
    sparse["abstract"] = ""

    ranked = bm25_rank(plan.goal_text, [sparse, rich], plan)

    assert ranked[0]["doi"] == rich["doi"]
    assert ranked[0]["_evidence_quality_score"] - ranked[1]["_evidence_quality_score"] > 0.5


def test_diversity_is_tie_breaker_not_tangent_reward() -> None:
    plan = QueryPlan(
        goal_text="quantum sensor calibration", search_queries=["quantum sensor calibration"]
    )
    rows = [
        {**work(1), "work_id": "best", "_retrieval_score": 0.8, "relation_label": "direct"},
        {
            **work(2),
            "work_id": "close",
            "title": "Quantum sensing calibration protocol",
            "abstract": "Quantum sensor calibration protocol under realistic noise.",
            "_retrieval_score": 0.79,
            "relation_label": "direct",
        },
        {
            **work(3),
            "work_id": "tangent",
            "title": "Unrelated ecological population survey",
            "abstract": "Ecological field observations and population statistics.",
            "_retrieval_score": 0.75,
            "relation_label": "background",
        },
    ]

    selected = final_select(rows, 2, plan)

    assert [row["work_id"] for row in selected] == ["best", "close"]


def test_query_provenance_is_merged_and_embedding_pool_covers_facets() -> None:
    duplicate_rows = [
        {
            **work(1),
            "community_signals": {
                "source": "a",
                "source_query": "core method",
                "matched_queries": ["core method"],
                "source_query_ranks": {"core method": 2},
            },
        },
        {
            **work(1),
            "community_signals": {
                "source": "b",
                "source_query": "failure analysis",
                "matched_queries": ["failure analysis"],
                "source_query_ranks": {"failure analysis": 4},
            },
        },
    ]
    merged = dedupe_works(duplicate_rows)[0]
    assert set(merged["community_signals"]["matched_queries"]) == {
        "core method",
        "failure analysis",
    }

    plan = QueryPlan(
        goal_text="core method under failure analysis",
        search_queries=["core method", "rare failure analysis"],
    )
    candidates = [
        {
            **work(index, query="core method"),
            "work_id": f"core-{index}",
            "_retrieval_score": 1.0 - index / 100,
        }
        for index in range(6)
    ]
    candidates.append(
        {
            **work(99, query="rare failure analysis"),
            "work_id": "facet-specialist",
            "_retrieval_score": 0.2,
        }
    )
    pool = stratified_embedding_candidates(candidates, 4, plan)
    assert "facet-specialist" in {row["work_id"] for row in pool}


def test_domain_neutral_facet_queries_and_compound_tokens() -> None:
    goal = (
        "Identify robust catalytic pathways for low-temperature ammonia synthesis using earth-abundant "
        "materials while controlling catalyst degradation and energy consumption."
    )
    plan = deterministic_query_plan(goal)

    assert "materials_science" in plan.domain_hints
    assert any("ammonia synthesis" in query for query in plan.search_queries[:4])
    assert any("catalyst degradation" in query for query in plan.search_queries[:4])
    assert "synthesis" in tokenize("ammonia synthesis")
    assert {"sparse-view", "sparse", "view"} <= set(tokenize("sparse-view"))
    arxiv = normalize_source_query("arxiv", "ammonia synthesis catalyst degradation")
    assert ") AND (" in arxiv and " OR " in arxiv


def test_high_ambiguity_research_goals_receive_disambiguating_recall_queries() -> None:
    hilbert = deterministic_query_plan("Hilbert's sixth problem and its solution")
    assert "Hilbert sixth problem Boltzmann kinetic theory" in hilbert.search_queries
    assert "hydrodynamic limit Boltzmann equation fluid equations" in hilbert.search_queries

    mas = deterministic_query_plan(
        "how does multi-agent systems improve autonomous scientific discovery"
    )
    assert "multi agent systems autonomous scientific discovery" in mas.search_queries
    assert "autonomous scientific discovery" in mas.search_queries
    assert "AI researcher multi agent automated scientific discovery" in mas.search_queries
    assert "computer_science" in mas.domain_hints


def test_default_embedding_pool_is_large_enough_for_strict_top_up() -> None:
    assert embedding_rerank_candidate_limit(50) == 200
    assert embedding_rerank_candidate_limit(50, configured_limit=250) == 250
