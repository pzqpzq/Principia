from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

import principia.cli as cli_module
from principia._llm_progress import call_with_progress
from principia.cli import build_parser, main
from principia.models import (
    ExtractedFeatures,
    Idea,
    IdeaComparison,
    PipelineResult,
    RunStatus,
    WorkList,
)
from principia.pipeline import PipelineConfig, PipelineJob
from principia.run import RunCancelledError, RunControlToken, RunHandle, WeightedProgress
from principia.storage import WorkspaceStorage


def _result(tmp_path: Path) -> PipelineResult:
    idea = Idea(id="IDEA_TEST", title="Test idea", thesis="A testable thesis.", mode="standard")
    return PipelineResult(
        goal="Test goal",
        works=WorkList(query="test"),
        features=ExtractedFeatures(model="test"),
        idea=idea,
        comparison=IdeaComparison(idea_id=idea.id),
        workspace_path=str(tmp_path),
    )


def _wait_for(predicate, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition did not become true before timeout")


def test_pipeline_research_preset_and_weighted_progress_are_deterministic() -> None:
    config = PipelineConfig.research()
    progress = WeightedProgress({"a": 1, "b": 3})

    assert config.target_count == 50
    assert config.rerank_mode == "embedding_rerank"
    assert config.global_kind_limits == {"ideas": 5, "principles": 5, "takeaways": 5}
    assert config.max_per_work == 2
    assert config.require_exact_evidence is True
    assert progress.update("a", 0.8) == pytest.approx(0.2)
    assert progress.update("a", 0.2) == pytest.approx(0.2)
    assert progress.update("b", 0.5) == pytest.approx(0.575)
    with pytest.raises(KeyError):
        progress.update("missing", 1)


def test_run_ids_remain_unique_when_clock_values_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = WorkspaceStorage(tmp_path)
    monkeypatch.setattr("principia.run.utc_now", lambda: "2026-07-15T00:00:00+00:00")
    monkeypatch.setattr("principia.run.time.time_ns", lambda: 1)

    with RunHandle(storage, "research.extract") as first:
        first_id = first.status.run_id
    with RunHandle(storage, "research.extract") as second:
        second_id = second.status.run_id

    assert first_id != second_id


def test_pipeline_pause_freezes_at_safe_boundary_and_resume_completes(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path)
    first_unit_complete = threading.Event()
    enter_next_boundary = threading.Event()
    scheduled: list[str] = []

    def runner(control):
        scheduled.append("unit-1")
        control.update("retrieval", 0.4, "First unit complete.")
        first_unit_complete.set()
        assert enter_next_boundary.wait(timeout=2)
        control.checkpoint()
        scheduled.append("unit-2")
        control.complete_stage("retrieval", "Second unit complete.")
        return _result(tmp_path)

    job = PipelineJob.start(storage, runner, poll_seconds=0.01)
    assert first_unit_complete.wait(timeout=2)
    requested = job.pause()
    assert requested.status == "pause_requested"
    enter_next_boundary.set()
    _wait_for(lambda: job.status().status == "paused")
    assert scheduled == ["unit-1"]

    resumed = job.resume()
    assert resumed.status == "running"
    result = job.result(timeout=3)

    assert result.idea.id == "IDEA_TEST"
    assert scheduled == ["unit-1", "unit-2"]
    assert job.status().status == "complete"
    assert job.status().progress == 1.0
    assert [event["stage"] for event in job.events()].count("retrieval") == 2


def test_pipeline_stop_is_prompt_and_invokes_transport_callback(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path)
    active_call = threading.Event()
    transport_closed = threading.Event()

    def runner(control):
        control.register_stop_callback(transport_closed.set)
        active_call.set()
        control.wait(30, checkpoint=False)
        raise AssertionError("stop should interrupt the active wait")

    job = PipelineJob.start(storage, runner, poll_seconds=0.01)
    assert active_call.wait(timeout=2)
    started = time.monotonic()
    requested = job.stop()
    assert requested.status == "cancel_requested"
    _wait_for(lambda: job.status().status == "cancelled")

    assert transport_closed.is_set()
    assert time.monotonic() - started < 1
    with pytest.raises(RunCancelledError):
        job.result(timeout=1)
    assert "checkpoints were preserved" in job.status().message


def test_provider_pause_checkpoints_response_before_next_call(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path)
    token = RunControlToken(poll_seconds=0.01)
    provider_started = threading.Event()
    provider_release = threading.Event()
    provider_finished = threading.Event()
    consumer_finished = threading.Event()
    output: list[str] = []

    def provider() -> str:
        provider_started.set()
        assert provider_release.wait(timeout=2)
        provider_finished.set()
        return "paid response"

    def consume() -> None:
        with RunHandle(storage, "test.provider", token=token) as run:
            output.append(
                call_with_progress(
                    run,
                    stage="provider",
                    message="Calling provider.",
                    progress_start=0.1,
                    progress_end=0.9,
                    estimated_seconds=1,
                    heartbeat_seconds=0.01,
                    call=provider,
                )
            )
        consumer_finished.set()

    thread = threading.Thread(target=consume)
    thread.start()
    assert provider_started.wait(timeout=2)
    token.request_pause()
    provider_release.set()
    assert provider_finished.wait(timeout=2)
    time.sleep(0.05)
    assert not consumer_finished.is_set()
    assert output == []

    token.resume()
    assert consumer_finished.wait(timeout=2)
    thread.join(timeout=1)
    assert output == ["paid response"]


def test_parent_child_heartbeat_does_not_block_inflight_provider_completion(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path)
    provider_started = threading.Event()
    provider_release = threading.Event()
    provider_finished = threading.Event()

    def provider() -> str:
        provider_started.set()
        assert provider_release.wait(timeout=2)
        provider_finished.set()
        return "checkpoint me"

    def runner(control):
        with RunHandle(
            storage,
            "ideas.generate",
            token=control.token,
            callback=control.child_callback("generation"),
        ) as run:
            response = call_with_progress(
                run,
                stage="provider",
                message="Generating.",
                progress_start=0.1,
                progress_end=0.9,
                estimated_seconds=1,
                heartbeat_seconds=0.01,
                call=provider,
            )
        assert response == "checkpoint me"
        control.complete_stage("generation", "Generation complete.")
        return _result(tmp_path)

    job = PipelineJob.start(storage, runner, poll_seconds=0.01)
    assert provider_started.wait(timeout=2)
    job.pause()
    provider_release.set()
    assert provider_finished.wait(timeout=2)
    _wait_for(lambda: job.status().status == "paused")

    job.resume()
    assert job.result(timeout=3).idea.id == "IDEA_TEST"
    assert job.status().status == "complete"


def test_stop_callback_is_best_effort_and_runs_once() -> None:
    token = RunControlToken()
    calls: list[str] = []
    token.register_stop_callback(lambda: calls.append("first"))

    def broken_close() -> None:
        calls.append("broken")
        raise RuntimeError("transport already closed")

    token.register_stop_callback(broken_close)
    token.cancel()
    token.cancel()

    assert calls == ["broken", "first"]
    with pytest.raises(RunCancelledError):
        token.wait(10)


def test_cli_control_commands_and_auto_model_defaults(tmp_path: Path, capsys) -> None:
    parser = build_parser()
    assert parser.parse_args(["extract", "query"]).model == "auto"
    assert parser.parse_args(["generate", "query"]).model == "auto"
    assert parser.parse_args(["generate", "query"]).mode == "scidialect-evo"

    storage = WorkspaceStorage(tmp_path)
    status = RunStatus(run_id="RUN_CLI", operation="workspace.pipeline", status="running")
    storage.create_run(status)

    assert main(["--workspace", str(tmp_path), "pause", status.run_id]) == 0
    assert '"status": "pause_requested"' in capsys.readouterr().out
    assert main(["--workspace", str(tmp_path), "resume", status.run_id]) == 0
    assert '"status": "running"' in capsys.readouterr().out
    assert main(["--workspace", str(tmp_path), "stop", status.run_id]) == 0
    assert '"status": "cancel_requested"' in capsys.readouterr().out
    assert main(["--workspace", str(tmp_path), "runs", "--limit", "1"]) == 0
    assert "RUN_CLI" in capsys.readouterr().out


def test_attached_job_reports_missing_result_without_hanging(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path)
    status = RunStatus(
        run_id="RUN_COMPLETE",
        operation="workspace.pipeline",
        status="complete",
        progress=1,
    )
    storage.create_run(status)
    attached = PipelineJob.attach(storage, status.run_id)

    with pytest.raises(RuntimeError, match="unavailable in this process"):
        attached.result(timeout=0.1)


def test_cli_keyboard_interrupt_reports_checkpoint_run_id(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    class InterruptingResearch:
        def search(self, *args, **kwargs):
            raise KeyboardInterrupt

    class InterruptingWorkspace:
        def __init__(self, path: Path, *, llm=None) -> None:
            self.storage = WorkspaceStorage(path)
            self.storage.create_run(
                RunStatus(run_id="RUN_RESUMABLE", operation="research.search", status="running")
            )
            self.research = InterruptingResearch()

    monkeypatch.setattr(cli_module, "Workspace", InterruptingWorkspace)
    exit_code = cli_module.main(["--workspace", str(tmp_path), "search", "interrupt me"])

    assert exit_code == 130
    assert '"run_id": "RUN_RESUMABLE"' in capsys.readouterr().err
