from __future__ import annotations

import json
from concurrent.futures import Future

import pytest
from fastapi.testclient import TestClient

from principia import Principia
from principia.api import create_app
from principia.cloud import ResearchGoalRunRequest
from principia.domain import JobRecord


class DeferredExecutor:
    def submit(self, *_args, **_kwargs):
        return Future()


def test_fast_worker_cannot_publish_a_terminal_session_before_its_map(tmp_path, monkeypatch):
    app = Principia.open(working_directory=tmp_path / "working", cloud_root=tmp_path / "cloud")
    executor = app.goal_runs._executor
    app.goal_runs._executor = DeferredExecutor()
    original_start = app.goal_runs.start
    observed = []

    def completed_start(request, **kwargs):
        run = original_start(request, **kwargs)
        with app.repository.connect() as conn:
            conn.execute("UPDATE research_goal_runs SET state='succeeded' WHERE run_id=?", (run["run_id"],))
        return app.goal_runs.detail(run["run_id"])

    def held_projection(run_id):
        with app.repository.connect() as conn:
            observed.append(conn.execute("SELECT state FROM research_sessions WHERE active_run_id=?", (run_id,)).fetchone()[0])

    monkeypatch.setattr(app.goal_runs, "start", completed_start)
    monkeypatch.setattr(app.research_sessions, "finalize_goal_run", held_projection)
    try:
        session = app.research_sessions.create(ResearchGoalRunRequest(goal="Find principles about diffusion", include_global=True))
        assert observed == ["running"]
        assert session["state"] == "running"
        assert session["active_run"]["state"] == "succeeded"
        assert app.research_sessions.graph(session["session_id"])["items"] == []
        assert observed == ["running"]  # Reading never repairs a projection.
        with pytest.raises(ValueError, match="still active"):
            app.research_sessions.start_run(session["session_id"], ResearchGoalRunRequest(goal="Search again for diffusion"))
    finally:
        app.goal_runs._executor = executor
        app.close()


def test_lightweight_status_exposes_heartbeat_without_decoding_report_or_checkpoint(tmp_path):
    app = Principia.open(working_directory=tmp_path / "working", cloud_root=tmp_path / "cloud")
    try:
        job = JobRecord(job_id="job:status", kind="data_discovery", state="running", stage="Synthesize",
                        status_message="Waiting for a model response", last_activity_at="2026-09-06T04:10:00Z")
        app.repository.save_job(job)
        app.repository.create_data_study({"study_id": "study:status", "job_id": job.job_id, "state": "running", "phase": "synthesize"})
        with app.repository.connect() as conn:
            conn.execute("UPDATE data_studies SET coverage_json='not JSON',report_json='not JSON'")
            conn.execute("UPDATE v14_jobs SET payload_json='not JSON' WHERE job_id=?", (job.job_id,))
            before = list(conn.iterdump())
        with TestClient(create_app(app, test_mode=True)) as client:
            response = client.get("/api/v1/data-discoveries/study:status/status")
            assert response.status_code == 200
            status = response.json()
            assert status["job"]["status_message"] == "Waiting for a model response"
            assert status["job"]["last_activity_at"] == "2026-09-06T04:10:00Z"
            assert status["counts"] == {"tests": 0, "findings": 0, "supported_findings": 0}
            assert len(json.dumps(status)) < 2000
            assert "checkpoint" not in status["job"]
        with app.repository.connect() as conn:
            assert list(conn.iterdump()) == before
    finally:
        app.close()


def test_provider_heartbeat_cannot_undo_a_cancel_request(tmp_path):
    app = Principia.open(working_directory=tmp_path / "working", cloud_root=tmp_path / "cloud")
    try:
        job = JobRecord(job_id="job:cancelling", kind="data_discovery", state="cancelling")
        app.repository.save_job(job)
        app.data_discovery._update_job(job.job_id, progress=0.5, status="Stopping after the current response")
        assert app.repository.get_job(job.job_id).state == "cancelling"
    finally:
        app.close()
