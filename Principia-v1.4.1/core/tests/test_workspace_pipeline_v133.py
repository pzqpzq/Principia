from __future__ import annotations

import json
import time
from pathlib import Path
from types import MethodType
from typing import Any

import pytest

import principia as pc
from principia.llm import LLMConfig
from principia_retrieval import InsufficientResultsError

GOAL = "calibrated supplemental research workflow"


def _public_rows(count: int) -> list[dict[str, Any]]:
    return [
        {
            "work_id": f"PUBLIC_{index}",
            "title": f"Calibrated supplemental research workflow study {index}",
            "authors": [f"Fixture Author {index}"],
            "abstract": (
                "A calibrated supplemental research workflow combines a distinct public "
                f"mechanism, comparison, and validation observation for cohort {index}."
            ),
            "year": 2026,
            "source": "fixture",
        }
        for index in range(1, count + 1)
    ]


def _source_with_rows(count: int):
    rows = _public_rows(count)

    def source(query: str, limit: int, timeout: float) -> list[dict[str, Any]]:
        del query, timeout
        return rows[:limit]

    return source


def _retrieval_config() -> pc.RetrievalConfig:
    return pc.RetrievalConfig(
        source_names=["fixture"],
        use_llm_planner=False,
        min_relevance=0,
        max_queries=1,
        max_retrieval_rounds=1,
        source_max_retries=0,
        source_backoff_seconds=0,
        source_min_interval_seconds={},
    )


def _write_local_documents(root: Path, count: int = 3) -> Path:
    corpus = root / "local_sources"
    corpus.mkdir(parents=True)
    for index in range(1, count + 1):
        (corpus / f"note_{index}.md").write_text(
            "\n".join(
                [
                    f"# Supplemental calibration note {index}",
                    "",
                    "This local document records a distinct control, principle, and takeaway ",
                    f"for calibrated workflow cohort {index}.",
                ]
            ),
            encoding="utf-8",
        )
    return corpus


def _mock_pipeline_config(**updates: Any) -> pc.PipelineConfig:
    values: dict[str, Any] = {
        "target_count": 5,
        "require_target": True,
        "extraction_model": "mock",
        "idea_model": "mock",
        "comparison_model": "mock",
        "mode": "standard",
        "progress": "none",
    }
    values.update(updates)
    return pc.PipelineConfig(**values)


def test_workspace_run_appends_local_documents_and_extract_count_keeps_them(
    tmp_path: Path,
) -> None:
    corpus = _write_local_documents(tmp_path)
    workspace = pc.Workspace(
        tmp_path / "workspace",
        llm=pc.MockLLMClient(),
        search_sources={"fixture": _source_with_rows(5)},
    )

    result = workspace.run(
        GOAL,
        documents=corpus,
        pipeline_config=_mock_pipeline_config(),
        retrieval_config=_retrieval_config(),
        sources=["fixture"],
        extract_count=2,
    )

    assert result.works.target_count == 5
    assert result.works.public_count == 5
    assert result.works.local_count == 3
    assert len(result.works) == 8
    assert len(result.features) == 5
    extracted_ids = {item.work_id for item in result.features}
    local_ids = {work.id for work in result.works if work.source == "local"}
    public_ids = {work.id for work in result.works if work.source != "local"}
    assert local_ids <= extracted_ids
    assert len(extracted_ids & public_ids) == 2
    assert result.works.local_diagnostics.accepted_count == 3


def test_local_documents_never_satisfy_the_public_retrieval_target(tmp_path: Path) -> None:
    corpus = _write_local_documents(tmp_path, count=5)
    workspace = pc.Workspace(
        tmp_path / "workspace",
        llm=pc.MockLLMClient(),
        search_sources={"fixture": _source_with_rows(2)},
    )

    with pytest.raises(InsufficientResultsError):
        workspace.run(
            GOAL,
            documents=corpus,
            pipeline_config=_mock_pipeline_config(target_count=3),
            retrieval_config=_retrieval_config(),
            sources=["fixture"],
        )

    assert workspace.counts()["works"] == 0
    assert workspace.counts()["source_assets"] == 0


def test_workspace_run_selects_exact_composite_evidence_with_per_work_cap(
    tmp_path: Path,
) -> None:
    corpus = _write_local_documents(tmp_path)
    workspace = pc.Workspace(
        tmp_path / "workspace",
        llm=pc.MockLLMClient(),
        search_sources={"fixture": _source_with_rows(5)},
    )
    config = _mock_pipeline_config(
        global_kind_limits={"ideas": 5, "principles": 5, "takeaways": 5},
        max_per_work=2,
        require_exact_evidence=True,
    )

    result = workspace.run(
        GOAL,
        documents=corpus,
        pipeline_config=config,
        retrieval_config=_retrieval_config(),
        sources=["fixture"],
    )

    packet = result.selected_evidence
    counts = packet.counts()
    assert {kind: counts[kind] for kind in ("ideas", "principles", "takeaways")} == {
        "ideas": 5,
        "principles": 5,
        "takeaways": 5,
    }
    assert len(packet.features) == 8
    for feature in packet.features:
        selected_for_work = sum(
            len(getattr(feature, kind)) for kind in ("ideas", "principles", "takeaways")
        )
        assert 1 <= selected_for_work <= 2


class _RemoteFixtureLLM(pc.LLMClient):
    def __init__(self) -> None:
        super().__init__(
            LLMConfig(
                provider="custom",
                model="remote-fixture",
                api_key="unused-fixture-value",
                base_url="https://unused.invalid/v1",
            )
        )

    def chat_json(self, system: str, user: str, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("privacy gating must occur before any remote fixture call")


class _ReachedExtraction(RuntimeError):
    pass


def _consent_workspace(root: Path, corpus: Path, *, default: bool) -> pc.Workspace:
    return pc.Workspace(
        root,
        llm=_RemoteFixtureLLM(),
        search_sources={"fixture": _source_with_rows(1)},
        allow_remote_private_content=default,
    )


def _run_until_extraction(
    workspace: pc.Workspace,
    corpus: Path,
    monkeypatch: pytest.MonkeyPatch,
    **run_options: Any,
) -> bool:
    captured: dict[str, Any] = {}

    def fake_extract(*args: Any, **kwargs: Any) -> pc.ExtractedFeatures:
        del args
        captured.update(kwargs)
        raise _ReachedExtraction

    monkeypatch.setattr(workspace.research, "extract", fake_extract)
    with pytest.raises(_ReachedExtraction):
        workspace.run(
            GOAL,
            documents=corpus,
            target_count=1,
            retrieval_config=_retrieval_config(),
            sources=["fixture"],
            require_target=True,
            **run_options,
        )
    return bool(captured["allow_remote_private_content"])


def test_workspace_constructor_and_run_privacy_consent_precedence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corpus = _write_local_documents(tmp_path, count=1)
    default_denied = _consent_workspace(tmp_path / "denied", corpus, default=False)

    with pytest.raises(PermissionError, match="allow_remote_private_content=True"):
        default_denied.run(
            GOAL,
            documents=corpus,
            target_count=1,
            retrieval_config=_retrieval_config(),
            sources=["fixture"],
            require_target=True,
        )
    assert _run_until_extraction(
        default_denied,
        corpus,
        monkeypatch,
        allow_remote_private_content=True,
    )

    default_allowed = _consent_workspace(tmp_path / "allowed", corpus, default=True)
    assert _run_until_extraction(default_allowed, corpus, monkeypatch)
    with pytest.raises(PermissionError, match="allow_remote_private_content=True"):
        default_allowed.run(
            GOAL,
            documents=corpus,
            target_count=1,
            retrieval_config=_retrieval_config(),
            sources=["fixture"],
            require_target=True,
            allow_remote_private_content=False,
        )


def _sample_result(root: Path, *, include_local_path: bool = False) -> pc.PipelineResult:
    path_text = str((root / "private" / "source.md").resolve())
    work = pc.WorkItem(
        id="PUBLIC_SAMPLE",
        title="Calibrated workflow sample",
        abstract="A public fixture for persisted pipeline controls.",
        source="fixture",
        metadata={"diagnostic": path_text if include_local_path else "portable"},
    )
    feature = pc.WorkFeatures(
        work_id=work.id,
        title=work.title,
        model="mock:mock",
        ideas=[
            {
                "id": "idea_1",
                "title": "Calibrated workflow mechanism",
                "core_idea": "Calibrate the control boundary before intervention.",
            }
        ],
        principles=[
            {
                "id": "principle_1",
                "name": "Calibration principle",
                "argument": "A measured boundary should govern intervention.",
            }
        ],
        takeaways=[
            {
                "id": "takeaway_1",
                "title": "Report calibration",
                "message": "Report calibration alongside the intervention outcome.",
            }
        ],
    )
    evidence_text = (
        f"Calibration evidence originated at {path_text}."
        if include_local_path
        else "Calibration evidence supports the intervention boundary."
    )
    idea = pc.Idea(
        id="IDEA_SAMPLE",
        title="Calibrated Workflow Proposal",
        thesis="Use an observed calibration boundary to govern a falsifiable intervention.",
        mode="standard",
        novelty_claim="The control boundary is measured before intervention.",
        mechanism_design=["Measure the boundary and condition the intervention on it."],
        methodological_details={
            "summary": "A calibration-controlled workflow.",
            "symbols": [],
            "equations": [],
            "workflow": [{"step": "Calibrate", "detail": "Measure the control boundary."}],
            "reliability_checks": [],
        },
        validation_protocol=["Compare controlled and uncontrolled interventions."],
        baselines=["Uncontrolled intervention"],
        metrics=["Calibration error"],
        risks=[path_text if include_local_path else "Calibration drift"],
        assumptions=["The boundary can be measured before intervention."],
        evidence_work_ids=[work.id],
        source_evidence=[
            {
                "work_id": work.id,
                "kind": "ideas",
                "record_id": "idea_1",
                "title": "Calibrated workflow mechanism",
                "text": evidence_text,
            }
        ],
        model="mock:mock",
    )
    packet = pc.EvidencePacket(
        query=GOAL,
        features=[feature.model_copy(update={"principles": [], "takeaways": []})],
    )
    return pc.PipelineResult(
        goal=GOAL,
        works=pc.WorkList(query=GOAL, items=[work], target_count=1, sources=["fixture"]),
        features=pc.ExtractedFeatures(items=[feature], model="mock:mock"),
        idea=idea,
        comparison=pc.IdeaComparison(
            idea_id=idea.id,
            rows=[
                {
                    "title": "Prior workflow",
                    "essential_difference": "The proposal measures the boundary before intervention.",
                }
            ],
            model="mock:mock",
        ),
        selected_evidence=packet,
        workspace_path=str(root.resolve()),
    )


def _wait_for_status(
    workspace: pc.Workspace,
    run_id: str,
    expected: set[str],
    *,
    timeout: float = 3.0,
) -> pc.RunStatus:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = workspace.status(run_id)
        if status.status in expected:
            return status
        time.sleep(0.01)
    raise AssertionError(
        f"run {run_id} did not reach {sorted(expected)}; last status={workspace.status(run_id).status}"
    )


def test_workspace_start_persists_progress_and_delegates_pause_resume_stop(
    tmp_path: Path,
) -> None:
    workspace = pc.Workspace(tmp_path / "workspace", llm=pc.MockLLMClient())
    release_first = False
    first_started = False

    def controlled_run(
        self: pc.Workspace,
        goal: str,
        *,
        _pipeline_control: Any,
        **kwargs: Any,
    ) -> pc.PipelineResult:
        del self, goal, kwargs
        nonlocal release_first, first_started
        _pipeline_control.update("retrieval", 0.5, "Half of retrieval persisted.")
        first_started = True
        while not release_first:
            _pipeline_control.wait(0.01)
        _pipeline_control.complete_stage("retrieval", "Retrieval complete.")
        return _sample_result(tmp_path)

    workspace.run = MethodType(controlled_run, workspace)
    job = workspace.start(GOAL, pipeline_config=_mock_pipeline_config(), progress="none")
    deadline = time.monotonic() + 3
    while not first_started and time.monotonic() < deadline:
        time.sleep(0.01)
    assert first_started
    persisted = workspace.status(job.run_id)
    assert persisted.stage == "retrieval"
    assert persisted.progress > 0
    assert any(item.run_id == job.run_id for item in workspace.runs())

    requested = workspace.pause(job.run_id)
    assert requested.status == "pause_requested"
    assert _wait_for_status(workspace, job.run_id, {"paused"}).status == "paused"
    resumed = workspace.resume(job.run_id)
    assert resumed.status == "running"
    release_first = True
    result = job.result(timeout=3)
    assert result.idea.id == "IDEA_SAMPLE"
    assert workspace.status(job.run_id).status == "complete"
    assert workspace.status(job.run_id).progress == 1.0
    assert workspace.run_events(job.run_id)

    release_second = False
    second_started = False

    def cancellable_run(
        self: pc.Workspace,
        goal: str,
        *,
        _pipeline_control: Any,
        **kwargs: Any,
    ) -> pc.PipelineResult:
        del self, goal, kwargs
        nonlocal release_second, second_started
        _pipeline_control.update("retrieval", 0.25, "Cancellation checkpoint persisted.")
        second_started = True
        while not release_second:
            _pipeline_control.wait(0.01)
        return _sample_result(tmp_path)

    workspace.run = MethodType(cancellable_run, workspace)
    cancelled_job = workspace.start(GOAL, pipeline_config=_mock_pipeline_config(), progress="none")
    deadline = time.monotonic() + 3
    while not second_started and time.monotonic() < deadline:
        time.sleep(0.01)
    assert second_started
    assert workspace.stop(cancelled_job.run_id).status == "cancel_requested"
    with pytest.raises(pc.RunCancelledError):
        cancelled_job.result(timeout=3)
    assert _wait_for_status(workspace, cancelled_job.run_id, {"cancelled"}).status == "cancelled"


def test_new_workspace_pipeline_symbols_are_publicly_exported() -> None:
    expected = {
        "LocalCorpusConfig",
        "LocalCorpusDiagnostics",
        "LocalSourceReport",
        "PipelineConfig",
        "PipelineJob",
        "RunCancelledError",
        "canonical_evidence_registry",
        "hydrate_evidence_references",
        "validate_evidence_references",
        "register_local_parser",
    }
    assert expected <= set(pc.__all__)
    assert all(getattr(pc, name, None) is not None for name in expected)


def test_pipeline_result_show_is_concise_and_returns_self(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = _sample_result(tmp_path)

    returned = result.show()

    output = capsys.readouterr().out
    compact_output = " ".join(output.split())
    assert returned is result
    assert "Calibrated Workflow Proposal" in compact_output
    assert "IDEA_SAMPLE" in compact_output
    assert len(output.splitlines()) <= 20


def test_workspace_exports_scrub_absolute_paths_and_file_uris(tmp_path: Path) -> None:
    workspace = pc.Workspace(tmp_path / "workspace", llm=pc.MockLLMClient())
    result = _sample_result(tmp_path, include_local_path=True)
    absolute_private_path = str((tmp_path / "private" / "source.md").resolve())
    result.idea.risks.append(f"file://{absolute_private_path}")

    hidden_export = workspace.export_result(result)
    visible_export = workspace.outputs_dir / "exports" / result.idea.id
    latest_export = workspace.outputs_dir / "latest"

    for directory in (hidden_export, visible_export, latest_export):
        assert {
            "idea.md",
            "result.json",
            "works.json",
            "validation_plan.md",
            "validation_plan.json",
        } <= {path.name for path in directory.iterdir()}
        for path in directory.iterdir():
            if path.suffix not in {".json", ".md"}:
                continue
            text = path.read_text(encoding="utf-8")
            assert absolute_private_path not in text
            assert str(tmp_path.resolve()) not in text
            assert "file://" not in text
            if path.suffix == ".json":
                json.loads(text)


def test_project_layout_shares_works_and_features_without_output_duplication(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "research_project"
    workspace = pc.Workspace.project(project_root, llm=pc.MockLLMClient())
    result = _sample_result(project_root)

    export_dir = workspace.export_result(result)

    assert workspace.path == project_root / "workspace"
    assert workspace.outputs_dir == project_root / "outputs"
    assert export_dir == project_root / "outputs" / result.idea.id
    assert {"manifest.json", "works.json", "features.json"} <= {
        path.name for path in workspace.path.iterdir()
    }
    assert {
        "idea.md",
        "idea.json",
        "evidence.json",
        "comparison.json",
        "result.json",
        "validation_plan.md",
        "validation_plan.json",
    } <= {path.name for path in export_dir.iterdir()}
    assert not (export_dir / "works.json").exists()
    assert not (export_dir / "features.json").exists()

    manifest = json.loads((workspace.path / "manifest.json").read_text(encoding="utf-8"))
    result_manifest = json.loads((export_dir / "result.json").read_text(encoding="utf-8"))
    assert manifest["shared_artifacts"] == {
        "works": "works.json",
        "features": "features.json",
    }
    assert result_manifest["workspace"]["works"] == "../../workspace/works.json"
    assert "works" not in json.loads((export_dir / "idea.json").read_text(encoding="utf-8"))
    assert "trace" not in json.loads((export_dir / "idea.json").read_text(encoding="utf-8"))

    compact_card = pc.idea_markdown(result.idea, compact=True)
    assert compact_card.startswith(f"# {result.idea.title}\n")
    assert "## Mechanism" in compact_card
    assert "**Evidence:** 1 canonical record across 1 work." in compact_card

    summary = result.summary()
    assert summary["status"] == "complete"
    assert summary["online_works"] == 1
    assert summary["local_documents"] == 0
    assert summary["evidence_counts"] == {"ideas": 1, "principles": 0, "takeaways": 0}
    assert summary["mode"] == "standard"
