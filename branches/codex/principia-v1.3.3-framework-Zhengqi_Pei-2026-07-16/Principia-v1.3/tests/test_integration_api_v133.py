from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import principia as pc
import principia.cli as cli_module
import principia.research as research_module
from principia.llm import LLMConfig
from principia.research import SourceContent
from principia_retrieval import InsufficientResultsError


def source_row(title: str, doi: str) -> dict[str, Any]:
    return {
        "title": title,
        "authors": ["Ada Example"],
        "abstract": f"{title} reports a controlled research result.",
        "year": 2026,
        "source": "fixture",
        "doi": doi,
    }


def test_search_method_arguments_override_retrieval_config_and_serialize_diagnostics(
    tmp_path: Path,
) -> None:
    def configured(query: str, limit: int, timeout: float) -> list[dict[str, Any]]:
        return [source_row("Configured source", "10.1/configured")]

    def explicit(query: str, limit: int, timeout: float) -> list[dict[str, Any]]:
        return [source_row("Explicit source", "10.1/explicit")]

    workspace = pc.Workspace(
        tmp_path,
        llm=pc.MockLLMClient(),
        search_sources={"configured": configured, "explicit": explicit},
    )
    config = pc.RetrievalConfig(
        source_names=["configured"],
        rerank_mode="embedding_rerank",
        require_target=False,
        use_llm_planner=False,
        max_retrieval_rounds=1,
    )

    works = workspace.research.search(
        "controlled research result",
        target_count=1,
        retrieval_config=config,
        sources=["explicit"],
        rerank_mode="bm25",
        require_target=True,
    )

    assert [work.title for work in works] == ["Explicit source"]
    assert works.sources == ["explicit"]
    assert works.diagnostics.rerank_mode_requested == "bm25"
    assert works.diagnostics.complete is True
    # The caller's reusable dataclass is not mutated by explicit method args.
    assert config.source_names == ["configured"]
    assert config.rerank_mode == "embedding_rerank"
    assert config.require_target is False
    artifact = workspace.artifacts_dir / "source_json" / f"{works.run_id}.json"
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["diagnostics"]["source_reports"]
    assert payload["diagnostics"]["ranking_trace"]
    assert payload["diagnostics"]["successful_sources"] == ["explicit"]
    assert payload["diagnostics"]["failed_sources"] == []
    assert payload["diagnostics"]["complete"] is True
    assert payload["diagnostics"]["completeness"] == 1.0
    assert payload["diagnostics"]["rerank_mode_requested"] == "bm25"
    assert payload["diagnostics"]["rerank_mode_applied"] == "bm25"


def test_source_json_uses_complete_diagnostics_to_dict_for_partial_outage(
    tmp_path: Path,
) -> None:
    def good(query: str, limit: int, timeout: float) -> list[dict[str, Any]]:
        return [source_row("Available source", "10.1/available")]

    def broken(query: str, limit: int, timeout: float) -> list[dict[str, Any]]:
        raise RuntimeError("fixture outage")

    workspace = pc.Workspace(
        tmp_path,
        llm=pc.MockLLMClient(),
        search_sources={"good": good, "broken": broken},
    )
    config = pc.RetrievalConfig(
        source_names=["good", "broken"],
        use_llm_planner=False,
        max_queries=1,
        max_retrieval_rounds=1,
        source_max_retries=0,
        source_backoff_seconds=0,
    )

    works = workspace.research.search(
        "available controlled result",
        target_count=1,
        retrieval_config=config,
        require_target=True,
    )

    artifact = workspace.artifacts_dir / "source_json" / f"{works.run_id}.json"
    persisted = json.loads(artifact.read_text(encoding="utf-8"))["diagnostics"]
    assert persisted == works.diagnostics.to_dict()
    assert persisted["successful_sources"] == ["good"]
    assert persisted["failed_sources"] == ["broken"]
    assert persisted["degraded"] is True
    assert persisted["complete"] is True
    assert persisted["completeness"] == 1.0
    assert persisted["ranking_trace"]
    assert persisted["rerank_mode_applied"] == "bm25"

    restored = pc.WorkList.model_validate_json(artifact.read_text(encoding="utf-8"))
    assert restored.diagnostics.successful_sources == ["good"]
    assert restored.diagnostics.failed_sources == ["broken"]
    assert restored.diagnostics.to_dict() == persisted


def test_search_collapses_sqlite_canonical_ids_and_corrects_diagnostics(
    tmp_path: Path,
) -> None:
    def bridged_rows(query: str, limit: int, timeout: float) -> list[dict[str, Any]]:
        return [
            {
                "work_id": "DOI_PROVIDER_ROW",
                "title": "Quantum sensing DOI edition",
                "abstract": "Quantum sensing under calibrated noise.",
                "doi": "10.1000/bridge",
                "source": "fixture",
            },
            {
                "work_id": "ARXIV_PROVIDER_ROW",
                "title": "Quantum sensing preprint edition",
                "abstract": "Quantum sensing under calibrated noise.",
                "arxiv_id": "2601.12345",
                "source": "fixture",
            },
        ]

    workspace = pc.Workspace(
        tmp_path,
        llm=pc.MockLLMClient(),
        search_sources={"fixture": bridged_rows},
    )
    workspace.storage.save_work(
        pc.WorkItem(
            id="CANONICAL",
            title="Canonical quantum sensing paper",
            doi="10.1000/bridge",
            arxiv_id="2601.12345",
        )
    )
    config = pc.RetrievalConfig(
        source_names=["fixture"],
        use_llm_planner=False,
        min_relevance=0,
        max_queries=1,
        max_retrieval_rounds=1,
        source_min_interval_seconds={},
    )

    works = workspace.research.search(
        "quantum sensing",
        target_count=2,
        retrieval_config=config,
        require_target=False,
    )

    assert [work.id for work in works] == ["CANONICAL"]
    assert works.diagnostics.selected_count == 1
    assert works.diagnostics.complete is False
    assert works.diagnostics.completeness == 0.5
    assert works.diagnostics.degraded is True
    assert [row["work_id"] for row in works.diagnostics.ranking_trace] == ["CANONICAL"]
    assert any(
        "SQLite identity reconciliation" in warning for warning in works.diagnostics.warnings
    )
    artifact = workspace.artifacts_dir / "source_json" / f"{works.run_id}.json"
    persisted = json.loads(artifact.read_text(encoding="utf-8"))
    assert len(persisted["items"]) == 1
    assert persisted["diagnostics"]["selected_count"] == 1
    assert persisted["diagnostics"]["complete"] is False


def test_strict_search_rechecks_target_after_sqlite_identity_reconciliation(
    tmp_path: Path,
) -> None:
    def bridged_rows(query: str, limit: int, timeout: float) -> list[dict[str, Any]]:
        return [
            source_row("Quantum sensing DOI edition", "10.1000/bridge"),
            {
                **source_row("Quantum sensing preprint edition", ""),
                "arxiv_id": "2601.12345",
            },
        ]

    workspace = pc.Workspace(
        tmp_path,
        llm=pc.MockLLMClient(),
        search_sources={"fixture": bridged_rows},
    )
    workspace.storage.save_work(
        pc.WorkItem(
            id="CANONICAL",
            title="Canonical quantum sensing paper",
            doi="10.1000/bridge",
            arxiv_id="2601.12345",
        )
    )

    with pytest.raises(InsufficientResultsError) as caught:
        workspace.research.search(
            "quantum sensing",
            target_count=2,
            retrieval_config=pc.RetrievalConfig(
                source_names=["fixture"],
                use_llm_planner=False,
                min_relevance=0,
                max_queries=1,
                max_retrieval_rounds=1,
                source_min_interval_seconds={},
            ),
            require_target=True,
        )

    assert caught.value.diagnostics.selected_count == 1
    assert caught.value.diagnostics.complete is False
    assert caught.value.diagnostics.completeness == 0.5
    assert caught.value.diagnostics.degraded is True
    assert [row["work_id"] for row in caught.value.diagnostics.ranking_trace] == ["CANONICAL"]


def test_strict_search_tops_up_after_sqlite_identity_reconciliation(
    tmp_path: Path,
) -> None:
    def bridged_rows(query: str, limit: int, timeout: float) -> list[dict[str, Any]]:
        return [
            source_row("Quantum sensing DOI edition", "10.1000/bridge"),
            {
                **source_row("Quantum sensing preprint edition", ""),
                "arxiv_id": "2601.12345",
            },
            {
                **source_row("Instrument calibration appendix", "10.1000/top-up"),
                "abstract": "A calibration control for quantum sensors under realistic noise.",
            },
        ][:limit]

    workspace = pc.Workspace(
        tmp_path,
        llm=pc.MockLLMClient(),
        search_sources={"fixture": bridged_rows},
    )
    workspace.storage.save_work(
        pc.WorkItem(
            id="CANONICAL",
            title="Canonical quantum sensing paper",
            doi="10.1000/bridge",
            arxiv_id="2601.12345",
        )
    )

    works = workspace.research.search(
        "quantum sensing",
        target_count=2,
        retrieval_config=pc.RetrievalConfig(
            source_names=["fixture"],
            use_llm_planner=False,
            min_relevance=0,
            max_queries=1,
            max_retrieval_rounds=1,
            candidate_oversample=2,
            source_min_interval_seconds={},
        ),
        require_target=True,
    )

    assert len(works) == 2
    assert works.diagnostics.complete is True
    assert works.diagnostics.completeness == 1.0
    assert {work.doi for work in works} == {"10.1000/bridge", "10.1000/top-up"}
    assert [row["work_id"] for row in works.diagnostics.ranking_trace] == [
        work.id for work in works
    ]
    assert any("ranked candidate top-up" in warning for warning in works.diagnostics.warnings)


def test_auto_embedding_client_reuses_siliconflow_workspace_credentials(
    tmp_path: Path, monkeypatch: Any
) -> None:
    captured: dict[str, Any] = {}

    class CapturingEmbeddingClient:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

        def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
            dimensions = int(kwargs["dimensions"])
            return [[float(index + 1)] * dimensions for index, _ in enumerate(texts)]

    monkeypatch.setattr(research_module, "SiliconFlowEmbeddingClient", CapturingEmbeddingClient)
    llm = pc.LLMClient(
        LLMConfig.from_model(
            "siliconflow:Qwen/Qwen3.6-35B-A3B",
            api_key="local-test-key",
            base_url="https://siliconflow.example/v1",
        )
    )
    workspace = pc.Workspace(
        tmp_path,
        llm=llm,
        search_sources={
            "fixture": lambda query, limit, timeout: [source_row("Embedded", "10.1/embed")]
        },
    )

    works = workspace.research.search(
        "embedded controlled result",
        target_count=1,
        rerank_mode="embedding_rerank",
        sources=["fixture"],
        require_target=True,
    )

    assert captured["api_key"] == "local-test-key"
    assert captured["base_url"] == "https://siliconflow.example/v1"
    assert captured["model"] == "Qwen/Qwen3-Embedding-4B"
    assert works.diagnostics.rerank_mode_applied == "embedding_rerank"
    assert works.diagnostics.rerank_fallback_reason == ""


def test_extraction_uses_canonical_persisted_work_id(tmp_path: Path, monkeypatch: Any) -> None:
    workspace = pc.Workspace(tmp_path, llm=pc.MockLLMClient())
    existing = pc.WorkItem(id="canonical", title="Canonical paper", doi="10.1/same")
    workspace.storage.save_work(existing)
    incoming = pc.WorkItem(id="provider-specific", title="Canonical paper", doi="10.1/same")
    monkeypatch.setattr(
        research_module,
        "fetch_source_content",
        lambda *args, **kwargs: SourceContent(
            text="Source-grounded evidence.", content_type="html"
        ),
    )

    features = workspace.research.extract([incoming], model="mock")

    assert features.items[0].work_id == "canonical"
    assert workspace.counts()["works"] == 1
    assert workspace.counts()["extractions"] == 1


def test_extraction_provenance_counts_exact_prompt_content(
    tmp_path: Path, monkeypatch: Any
) -> None:
    class CapturingExtractionLLM(pc.LLMClient):
        def __init__(self) -> None:
            super().__init__(LLMConfig.from_model("mock"))
            self.user_prompt = ""

        def available(self, model: str = "auto") -> bool:
            return True

        def resolve(self, model: str = "auto") -> LLMConfig:
            return LLMConfig(
                provider="custom",
                model="capture",
                api_key="test",
                base_url="https://example.test/v1",
            )

        def chat_json(self, system: str, user: str, **kwargs: Any) -> dict[str, Any]:
            self.user_prompt = user
            return {
                "ideas": [{"title": "Idea", "core_idea": "abcdefghijk"}],
                "principles": [{"name": "Principle", "argument": "abcdefghijk"}],
                "takeaways": [{"title": "Takeaway", "message": "abcdefghijk"}],
            }

    llm = CapturingExtractionLLM()
    workspace = pc.Workspace(tmp_path, llm=llm)
    monkeypatch.setattr(
        research_module,
        "fetch_source_content",
        lambda *args, **kwargs: SourceContent(
            text="abcdefghijklmnopqrstuvwxyz", content_type="html"
        ),
    )

    features = workspace.research.extract(
        [pc.WorkItem(id="limited", title="Limited evidence")],
        model="custom:capture",
        max_chars=11,
    )

    assert '"text":"abcdefghijk"' in llm.user_prompt
    assert llm.user_prompt.endswith("<END_UNTRUSTED_SOURCE_EVIDENCE>")
    assert "abcdefghijkl" not in llm.user_prompt
    assert features.items[0].source_excerpt_chars == 11
    assert features.items[0].source_content_hash == (
        "ca2f2069ea0c6e4658222e06f8dd639659cbb5e67cbbba6734bc334a3799bc68"
    )


def test_extraction_run_metadata_reports_usage_delta(tmp_path: Path, monkeypatch: Any) -> None:
    llm = pc.LLMClient(LLMConfig.from_model("mock"))
    workspace = pc.Workspace(tmp_path, llm=llm)
    work = pc.WorkItem(id="usage", title="Usage accounting")
    monkeypatch.setattr(
        research_module,
        "fetch_source_content",
        lambda *args, **kwargs: SourceContent(
            text="Evidence for usage accounting.", content_type="html"
        ),
    )

    first = workspace.research.extract([work], model="mock", overwrite=True)
    second = workspace.research.extract([work], model="mock", overwrite=True)
    first_status = workspace.storage.get_run(first.run_id)
    second_status = workspace.storage.get_run(second.run_id)

    assert first_status is not None
    assert second_status is not None
    assert first_status.counts["llm_usage"]["calls"] == 1
    assert second_status.counts["llm_usage"]["calls"] == 1
    assert llm.usage_totals()["calls"] == 2


def test_comparison_run_metadata_reports_usage_delta(tmp_path: Path) -> None:
    class ComparisonLLM(pc.LLMClient):
        def __init__(self) -> None:
            super().__init__(
                LLMConfig(
                    provider="custom",
                    model="comparison-usage",
                    api_key="test",
                    base_url="https://example.test/v1",
                )
            )

        def available(self, model: str = "auto") -> bool:
            return True

        def resolve(self, model: str = "auto") -> LLMConfig:
            return self.config

        def chat_json(self, system: str, user: str, **kwargs: Any) -> dict[str, Any]:
            self._begin_call(self.config)
            self._finish_call(success=True, usage={"prompt_tokens": 20, "completion_tokens": 10})
            return {
                "rows": [
                    {
                        "work_id": "W1",
                        "title": "Prior uncertainty-aware sensing method",
                        "mechanistic_similarity": "Both methods explicitly propagate calibrated uncertainty through their decision stages.",
                        "essential_difference": "The new method introduces a distinct evidence-gated control mechanism.",
                        "potential_advantage": "The explicit gate may reduce false positives under distribution shift.",
                        "potential_weakness": "Gate calibration may fail when the reference evidence is sparse.",
                    }
                ]
            }

    workspace = pc.Workspace(tmp_path, llm=ComparisonLLM())
    idea = pc.Idea(
        id="I1",
        title="Evidence-gated uncertainty controller",
        thesis="Use calibrated evidence gates to control uncertain observations.",
        mode="standard",
    )
    feature = pc.WorkFeatures(
        work_id="W1",
        title="Prior uncertainty-aware sensing method",
        model="fixture",
        ideas=[
            {
                "title": "Prior calibrated controller",
                "core_idea": "Propagate calibrated uncertainty through a reference control stage.",
            }
        ],
    )

    comparison = workspace.ideas.compare(idea, [feature], model="custom:comparison-usage")
    status = workspace.storage.get_run(comparison.run_id)

    assert comparison.rows
    assert status is not None
    assert status.counts["llm_usage"]["calls"] == 1
    assert status.counts["llm_usage"]["total_tokens"] == 30


def test_explicit_unavailable_extraction_model_does_not_silently_fallback(
    tmp_path: Path, monkeypatch: Any
) -> None:
    llm = pc.LLMClient(
        LLMConfig(
            provider="custom", model="extractor", api_key="", base_url="https://example.test/v1"
        )
    )
    workspace = pc.Workspace(tmp_path, llm=llm)
    monkeypatch.setattr(
        research_module,
        "fetch_source_content",
        lambda *args, **kwargs: SourceContent(text="Evidence.", content_type="html"),
    )

    try:
        workspace.research.extract(
            [pc.WorkItem(id="unavailable", title="Unavailable explicit model")],
            model="custom:extractor",
        )
    except RuntimeError as exc:
        assert "explicitly requested extraction model" in str(exc)
    else:
        raise AssertionError(
            "Explicit unavailable model unexpectedly used a deterministic fallback"
        )


def test_cli_defaults_to_live_auto_and_requires_explicit_mock(
    tmp_path: Path, monkeypatch: Any
) -> None:
    captured: dict[str, Any] = {}

    class FakeResearch:
        def search(self, *args: Any, **kwargs: Any) -> list[Any]:
            return []

        def extract(self, *args: Any, **kwargs: Any) -> pc.ExtractedFeatures:
            return pc.ExtractedFeatures(model="mock")

    class FakeWorkspace:
        def __init__(self, path: Path, *, llm: Any = None) -> None:
            captured["llm"] = llm
            self.research = FakeResearch()

    monkeypatch.setattr(cli_module, "Workspace", FakeWorkspace)

    assert cli_module.main(["--workspace", str(tmp_path), "extract", "live default"]) == 0
    assert captured["llm"] is None
    assert (
        cli_module.main(["--workspace", str(tmp_path), "--mock-llm", "extract", "offline fixture"])
        == 0
    )
    assert isinstance(captured["llm"], pc.MockLLMClient)
