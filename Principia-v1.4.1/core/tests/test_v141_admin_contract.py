from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from principia.application import AdminWorkspace
from principia.api import app_for_testing
from principia.cloud import AdminExtractRequest
from principia.domain import JobRecord


def test_admin_extract_requires_four_for_new_run(tmp_path: Path) -> None:
    app = AdminWorkspace.open(working_directory=tmp_path / "admin")
    try:
        service = app.admin_campaigns
        assert service is not None
        with app.repository.connect() as conn:
            now = "2026-08-13T00:00:00Z"
            conn.execute(
                "INSERT INTO admin_campaigns VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "campaign:test", None, None, "discovery_ready", "test bounded goal", 3,
                    "", "", "", "{}",
                    '{"research_goal":"test bounded goal","provider_profile_id":"siliconflow","model":"x","concurrency":4,"extraction":{}}',
                    now, now,
                ),
            )
            for index in range(3):
                conn.execute(
                    "INSERT INTO admin_campaign_works VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        "campaign:test", f"work:{index}", index, 1, "discovered", "unknown",
                        "", None, "", "new", '{"title":"paper"}', "{}", None, "",
                    ),
                )
        with pytest.raises(ValueError, match="at least four"):
            service.extract(
                "campaign:test", AdminExtractRequest(retry=False, egress_confirmed=True)
            )
    finally:
        app.close()


def test_admin_extract_preflights_provider_before_creating_job(tmp_path: Path, monkeypatch) -> None:
    app = AdminWorkspace.open(working_directory=tmp_path / "admin")
    try:
        service = app.admin_campaigns
        assert service is not None
        now = "2026-08-13T00:00:00Z"
        with app.repository.connect() as conn:
            conn.execute(
                "INSERT INTO admin_campaigns VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "campaign:preflight", None, None, "discovery_ready", "test provider preflight", 4,
                    "", "", "", "{}",
                    '{"research_goal":"test provider preflight","provider_profile_id":"siliconflow",'
                    '"model":"fixture","concurrency":4,"extraction":{}}',
                    now, now,
                ),
            )
            for index in range(4):
                conn.execute(
                    "INSERT INTO admin_campaign_works VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        "campaign:preflight", f"work:preflight:{index}", index, 1,
                        "discovered", "available", "", None, "", "new",
                        '{"title":"paper"}', "{}", None, "",
                    ),
                )
        monkeypatch.setattr(
            service.local,
            "test_provider_connection",
            lambda _provider_id: {"ok": False, "category": "authentication"},
        )
        with pytest.raises(ValueError, match="saved API key was rejected"):
            service.extract(
                "campaign:preflight", AdminExtractRequest(retry=False, egress_confirmed=True)
            )
        assert app.repository.list_jobs(kind="admin_extraction") == []
    finally:
        app.close()


def test_admin_papers_expose_redacted_failure_detail(tmp_path: Path) -> None:
    app = AdminWorkspace.open(working_directory=tmp_path / "admin")
    try:
        service = app.admin_campaigns
        assert service is not None
        now = "2026-08-13T00:00:00Z"
        with app.repository.connect() as conn:
            conn.execute(
                "INSERT INTO admin_campaigns VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "campaign:error-detail", None, None, "failed", "test error detail", 1,
                    "", "", "", "{}",
                    '{"research_goal":"test error detail","provider_profile_id":"siliconflow",'
                    '"model":"fixture","concurrency":4,"extraction":{}}',
                    now, now,
                ),
            )
            conn.execute(
                "INSERT INTO admin_campaign_works VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "campaign:error-detail", "work:error-detail", 0, 1, "provider_failed",
                    "available", "", None, "", "new", '{"title":"paper"}', "{}",
                    '{"category":"rate_limited","message":"Provider is temporarily rate limited.",'
                    '"retryable":true}', "",
                ),
            )
        paper = service.papers("campaign:error-detail")["items"][0]
        assert paper["error"] == {
            "category": "rate_limited",
            "message": "Provider is temporarily rate limited.",
            "retryable": True,
        }
    finally:
        app.close()


def test_admin_temp_sweeper_is_allowlisted(tmp_path: Path) -> None:
    root = tmp_path / "admin"
    app = AdminWorkspace.open(working_directory=root)
    try:
        service = app.admin_campaigns
        assert service is not None
        orphan = service.temp_root / "job-fixture" / "unit-fixture"
        orphan.mkdir(parents=True)
        (orphan / "source.bin").write_bytes(b"pdf")
        outside = root / "do-not-delete.txt"
        outside.write_text("safe")
        receipt = service.sweep_orphaned_temp()
        assert receipt["removed_job_directories"] == 1
        assert outside.read_text() == "safe"
        assert not orphan.exists()
    finally:
        app.close()


def test_interrupted_admin_cancel_is_durable_without_runtime_control(tmp_path: Path) -> None:
    app = AdminWorkspace.open(working_directory=tmp_path / "admin")
    try:
        service = app.admin_campaigns
        assert service is not None
        job = JobRecord(
            job_id="job:admin-interrupted", kind="admin_extraction", state="interrupted",
            stage="interrupted", total_units=1, checkpoint={"campaign_id": "campaign:missing"},
        )
        app.repository.save_job(job)
        cancelled = service.cancel(job.job_id)
        assert cancelled["state"] == "cancelled"
    finally:
        app.close()


def test_admin_nested_campaign_routes_do_not_get_swallowed_by_detail_route(
    tmp_path: Path,
) -> None:
    """The browser must receive paper rows, not a lookup for ``<id>/papers``."""

    product = AdminWorkspace.open(working_directory=tmp_path / "admin")
    try:
        service = product.admin_campaigns
        assert service is not None
        now = "2026-08-13T00:00:00Z"
        with product.repository.connect() as conn:
            conn.execute(
                "INSERT INTO admin_campaigns VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "campaign:route-test", None, None, "discovery_ready",
                    "multi-agent systems", 1, "", "", "", "{}",
                    '{"research_goal":"multi-agent systems","provider_profile_id":"siliconflow",'
                    '"model":"fixture","concurrency":4,"extraction":{},"discovery":{}}',
                    now, now,
                ),
            )
            conn.execute(
                "INSERT INTO admin_campaign_works VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "campaign:route-test", "work:route-test", 1, 0, "discovered",
                    "available", "", None, "", "new",
                    '{"work_id":"work:route-test","title":"A multi-agent systems paper"}',
                    "{}", None, "",
                ),
            )
        api = app_for_testing(product, admin_mode=True)
        client = TestClient(api, raise_server_exceptions=False)

        papers = client.get("/api/v1/admin/campaigns/campaign:route-test/papers")
        assert papers.status_code == 200, papers.text
        assert papers.json()["total"] == 1
        assert papers.json()["items"][0]["title"] == "A multi-agent systems paper"
        detail = client.get("/api/v1/admin/campaigns/campaign:route-test")
        assert detail.status_code == 200, detail.text
        assert detail.json()["campaign_id"] == "campaign:route-test"
    finally:
        product.close()


def test_research_goal_nested_routes_accept_colon_ids(tmp_path: Path) -> None:
    """Goal progress/results must not be captured by the detail route."""

    product = AdminWorkspace.open(working_directory=tmp_path / "regular")
    try:
        now = "2026-08-13T00:00:00Z"
        product.repository.save_job(
            JobRecord(
                job_id="job:route-test", kind="research_goal_run", state="succeeded",
                stage="Complete", progress=1,
            )
        )
        with product.repository.connect() as conn:
            conn.execute(
                "INSERT INTO research_goal_runs VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    "goalrun:route-test", "job:route-test", "succeeded", "test research goal",
                    "release:test", '{"goal":"test research goal"}', "{}", "{}", now, now,
                ),
            )
        client = TestClient(app_for_testing(product), raise_server_exceptions=False)
        detail = client.get("/api/v1/research-goal-runs/goalrun:route-test")
        results = client.get(
            "/api/v1/research-goal-runs/goalrun:route-test/results?membership=combined"
        )
        assert detail.status_code == 200, detail.text
        assert results.status_code == 200, results.text
        assert results.json() == {"items": [], "total": 0}
    finally:
        product.close()
