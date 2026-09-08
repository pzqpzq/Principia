from __future__ import annotations

import time
from pathlib import Path

from principia.application import Principia
from principia.cloud import ResearchGoalRunRequest, build_cloud_snapshot

ROOT = Path(__file__).resolve().parents[1]


def canonical_root() -> Path:
    configured = __import__("os").environ.get("PRINCIPIA_GLOBAL_CANONICAL_ROOT", "")
    candidates = [Path(configured).expanduser()] if configured else []
    candidates.extend(parent / "global-cloud" for parent in (ROOT, *ROOT.parents))
    return next(path.resolve() for path in candidates if (path / "CLOUD_VERSION").is_file())


def test_global_only_session_is_durable_and_graph_autosaves(tmp_path: Path) -> None:
    snapshot = tmp_path / "global.pcg"
    build_cloud_snapshot(
        canonical_root(),
        snapshot,
        release_id="session-fixture",
        created_at="2026-08-21T00:00:00Z",
    )
    app = Principia.open(
        working_directory=tmp_path / "working",
        cloud_root=tmp_path / "cloud-cache",
    )
    try:
        app.global_cloud.install_snapshot(snapshot)
        project = app.research_sessions.create_project("Agent research")
        session = app.research_sessions.create(
            ResearchGoalRunRequest(
                goal="how multi-agent systems improve autonomous scientific discovery",
                source_ids=[],
                include_global=True,
                global_limit=12,
            ),
            project_id=project["project_id"],
        )
        deadline = time.time() + 8
        while time.time() < deadline:
            session = app.research_sessions.detail(session["session_id"]) or {}
            if session.get("state") in {"succeeded", "partial", "failed"}:
                break
            time.sleep(0.03)
        assert session["state"] == "succeeded"
        global_page = app.research_sessions.results(session["session_id"], "global", limit=20)
        assert global_page["total"] >= 5
        graph = app.research_sessions.graph(session["session_id"])
        ordinary = [item for item in graph["items"] if item["record_kind"] == "ordinary"]
        meta = [item for item in graph["items"] if item["record_kind"] == "meta_principle"]
        assert len(ordinary) == 5
        assert len(meta) >= 1

        first = ordinary[0]
        receipt = app.research_sessions.mutate_graph(
            session["session_id"],
            [
                {
                    "action": "move",
                    "principle_id": first["principle_id"],
                    "x": 321.5,
                    "y": -42.0,
                },
                {"action": "viewport", "viewport": {"x": 10, "y": 20, "ratio": 0.8}},
            ],
            expected_revision=graph["revision"],
        )
        reopened = app.research_sessions.graph(session["session_id"])
        moved = next(
            item for item in reopened["items"] if item["principle_id"] == first["principle_id"]
        )
        assert (moved["x"], moved["y"]) == (321.5, -42.0)
        assert reopened["revision"] == receipt["revision"]
        assert reopened["viewport"]["ratio"] == 0.8

        artifact = app.research_sessions.save_artifact(
            session["session_id"], "virtual_principle", {"title": "Testable hypothesis"}
        )
        assert artifact["payload"]["title"] == "Testable hypothesis"
        assert app.research_sessions.delete_artifact(
            session["session_id"], artifact["artifact_id"]
        )["deleted"]

        generated = app.research_sessions.save_artifact(
            session["session_id"],
            "virtual_principle",
            {
                "items": [
                    {"virtual_id": "virtual:keep", "proposal": {"title": "Keep"}},
                    {"virtual_id": "virtual:delete", "proposal": {"title": "Delete"}},
                ]
            },
        )
        deletion = app.research_sessions.delete_virtual_principle(
            session["session_id"], "virtual:delete"
        )
        assert deletion["deleted"] is True
        assert deletion["removed_items"] == 1
        remaining = next(
            value
            for value in app.research_sessions.artifacts(session["session_id"])
            if value["artifact_id"] == generated["artifact_id"]
        )
        assert [item["virtual_id"] for item in remaining["payload"]["items"]] == ["virtual:keep"]

        run_id = session["active_run_id"]
        job_id = str((session.get("active_run") or {}).get("job_id") or "")
        deletion = app.research_sessions.delete_session(
            session["session_id"], expected_revision=int(session["revision"])
        )
        assert deletion["deleted"] is True
        assert app.research_sessions.detail(session["session_id"]) is None
        assert app.research_sessions.goal_runs.detail(run_id) is None
        assert app.repository.get_job(job_id) is None
        assert app.research_sessions.delete_project(project["project_id"])["deleted"] is True
    finally:
        app.close()


def test_active_research_cannot_be_deleted(tmp_path: Path) -> None:
    app = Principia.open(working_directory=tmp_path / "working")
    try:
        session = app.research_sessions.create(
            ResearchGoalRunRequest(
                goal="a sufficiently detailed research question",
                source_ids=[],
                include_global=True,
            )
        )
        # The session begins non-terminal even if the coordinator will finish
        # quickly; force the invariant under test without relying on timing.
        with app.repository.connect() as conn:
            conn.execute(
                "UPDATE research_sessions SET state='running' WHERE session_id=?",
                (session["session_id"],),
            )
        try:
            app.research_sessions.delete_session(session["session_id"])
        except ValueError as exc:
            assert "finish or cancel" in str(exc)
        else:
            raise AssertionError("active research deletion should fail closed")
    finally:
        app.close()
