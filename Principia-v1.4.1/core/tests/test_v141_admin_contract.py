from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from principia.admin.ingestion import _admin_discovery_queries
from principia.api import app_for_testing
from principia.application import AdminWorkspace
from principia.cloud import AdminExtractRequest, AdminStagedItem, BulkStagingDecisionRequest
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


def test_admin_selection_rejects_metadata_only_papers(tmp_path: Path) -> None:
    app = AdminWorkspace.open(working_directory=tmp_path / "admin")
    try:
        service = app.admin_campaigns
        assert service is not None
        now = "2026-08-14T00:00:00Z"
        with app.repository.connect() as conn:
            conn.execute(
                "INSERT INTO admin_campaigns VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("campaign:metadata-only", None, None, "discovery_ready", "AI for Physics", 1,
                 "", "", "", "{}", '{"research_goal":"AI for Physics"}', now, now),
            )
            conn.execute(
                "INSERT INTO admin_campaign_works VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("campaign:metadata-only", "work:metadata-only", 0, 0, "discovered",
                 "unknown", "", None, "", "new",
                 '{"title":"Abstract-only AI policy paper"}', "{}", None, ""),
            )
        with pytest.raises(ValueError, match="full-text-only"):
            service.select("campaign:metadata-only", ["work:metadata-only"])
    finally:
        app.close()


def test_ai_for_physics_admin_discovery_uses_focused_subfield_queries() -> None:
    queries = _admin_discovery_queries("AI for Physics", 50)
    assert len(queries) >= 8
    assert "physics-informed machine learning" in queries
    assert "machine learning quantum physics" in queries
    assert "machine learning particle physics" in queries


def test_admin_selection_rejects_available_but_off_goal_legacy_paper(tmp_path: Path) -> None:
    app = AdminWorkspace.open(working_directory=tmp_path / "admin")
    try:
        service = app.admin_campaigns
        assert service is not None
        now = "2026-08-15T00:00:00Z"
        with app.repository.connect() as conn:
            conn.execute(
                "INSERT INTO admin_campaigns VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "campaign:off-goal", None, None, "discovery_ready", "AI for Physics", 1,
                    "", "", "", "{}", '{"research_goal":"AI for Physics"}', now, now,
                ),
            )
            conn.execute(
                "INSERT INTO admin_campaign_works VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "campaign:off-goal", "work:education", 0, 0, "discovered", "available",
                    "", None, "", "new",
                    '{"title":"AI tutoring in education","abstract":"Completion rates improved.",'
                    '"oa_locations":[{"url":"https://example.org/paper.pdf"}]}',
                    "{}", None, "",
                ),
            )
        paper = service.papers("campaign:off-goal")["items"][0]
        assert paper["goal_relevant"] is False
        with pytest.raises(ValueError, match="both sides"):
            service.select("campaign:off-goal", ["work:education"])
    finally:
        app.close()


def test_admin_work_staging_is_idempotent_for_retry(tmp_path: Path) -> None:
    app = AdminWorkspace.open(working_directory=tmp_path / "admin")
    try:
        service = app.admin_campaigns
        assert service is not None
        now = "2026-08-14T00:00:00Z"
        with app.repository.connect() as conn:
            conn.execute(
                "INSERT INTO admin_campaigns VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("campaign:retry", None, None, "review_ready", "AI for Physics", 1,
                 "", "", "", "{}", '{"research_goal":"AI for Physics"}', now, now),
            )
        first = service._stage(
            "campaign:retry", "W-RETRY", "work",
            {"work_id": "W-RETRY", "revision": 1, "title": "AI for Physics"},
        )
        second = service._stage(
            "campaign:retry", "W-RETRY", "work",
            {"work_id": "W-RETRY", "revision": 1, "title": "AI for Physics updated"},
        )
        assert second.stage_id == first.stage_id
        with app.repository.connect() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM admin_staged_items WHERE campaign_id=? AND work_id=?",
                ("campaign:retry", "W-RETRY"),
            ).fetchone()[0]
        assert count == 1
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


def test_dashboard_counts_only_in_flight_or_conflicted_syncs_as_pending(tmp_path: Path) -> None:
    product = AdminWorkspace.open(working_directory=tmp_path / "admin")
    try:
        now = "2026-08-13T00:00:00Z"
        with product.repository.connect() as conn:
            for index, state in enumerate(
                ("reviewed", "failed", "published", "checks_running", "needs_resolution")
            ):
                conn.execute(
                    "INSERT INTO admin_campaigns VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        f"campaign:{index}", None, None, "draft", "dashboard test", 1,
                        "", "", "", "{}", '{"research_goal":"dashboard test"}', now, now,
                    ),
                )
                conn.execute(
                    "INSERT INTO admin_cloud_syncs VALUES (?,?,?,?,?,?)",
                    (
                        f"sync:{index}", f"campaign:{index}", state,
                        '{"schema_version":"cloud-sync-v1","sync_id":"sync:test",'
                        '"campaign_id":"campaign:test"}', now, now,
                    ),
                )
        response = TestClient(app_for_testing(product, admin_mode=True)).get(
            "/api/v1/admin/dashboard"
        )
        assert response.status_code == 200, response.text
        assert response.json()["pending_syncs"] == 2
    finally:
        product.close()


def test_same_reviewed_batch_reuses_one_publication_sync(tmp_path: Path) -> None:
    product = AdminWorkspace.open(working_directory=tmp_path / "admin")
    try:
        service = product.admin_campaigns
        assert service is not None
        now = "2026-08-14T00:00:00Z"
        campaign_id = "campaign:idempotent"
        item = AdminStagedItem(
            stage_id="stage:idempotent",
            campaign_id=campaign_id,
            entity="work",
            proposed={"work_id": "work:idempotent", "title": "One reviewed paper"},
            match_kind="new",
            decision="add",
        )
        with product.repository.connect() as conn:
            conn.execute(
                "INSERT INTO admin_campaigns VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    campaign_id, None, None, "review_ready", "idempotent publication", 1,
                    "release:test", "a" * 40, "digest:test", "{}",
                    '{"research_goal":"idempotent publication"}', now, now,
                ),
            )
            conn.execute(
                "INSERT INTO admin_staged_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    item.stage_id, campaign_id, "work:idempotent", item.entity,
                    item.match_kind, item.similarity, item.decision, 0, None, "",
                    "content:test", item.model_dump_json(), now, now,
                ),
            )

        first = service.create_sync(campaign_id, confirmation=f"SUBMIT {campaign_id}")
        second = service.create_sync(campaign_id, confirmation=f"SUBMIT {campaign_id}")

        assert first["sync_id"] == second["sync_id"]
        with product.repository.connect() as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM admin_cloud_syncs WHERE campaign_id=?", (campaign_id,)
            ).fetchone()[0] == 1
    finally:
        product.close()


def test_add_all_clear_excludes_ambiguous_and_allows_publication(tmp_path: Path) -> None:
    product = AdminWorkspace.open(working_directory=tmp_path / "admin")
    try:
        service = product.admin_campaigns
        assert service is not None
        now = "2026-08-14T00:00:00Z"
        campaign_id = "campaign:clear-with-ambiguous"
        clear = AdminStagedItem(
            stage_id="stage:clear",
            campaign_id=campaign_id,
            entity="work",
            match_kind="new",
            proposed={"work_id": "W-CLEAR", "title": "A clear paper"},
        )
        ambiguous = AdminStagedItem(
            stage_id="stage:ambiguous",
            campaign_id=campaign_id,
            entity="work",
            match_kind="ambiguous",
            proposed={"work_id": "W-PROPOSED", "title": "A possible duplicate"},
            current={"work_id": "W-CURRENT", "revision": 1, "title": "A possible duplicate"},
        )
        with product.repository.connect() as conn:
            conn.execute(
                "INSERT INTO admin_campaigns VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    campaign_id, None, None, "review_ready", "clear review", 2,
                    "release:base", "commit:base", "digest:base", "{}",
                    '{"research_goal":"clear review"}', now, now,
                ),
            )
            for item in (clear, ambiguous):
                conn.execute(
                    "INSERT INTO admin_staged_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        item.stage_id, campaign_id, str(item.proposed["work_id"]), item.entity,
                        item.match_kind, item.similarity, item.decision, 0, None, "",
                        "content-digest", item.model_dump_json(), item.created_at,
                        item.updated_at,
                    ),
                )

        result = service.bulk_decide(
            BulkStagingDecisionRequest(
                stage_ids=[clear.stage_id, ambiguous.stage_id], decision="add"
            )
        )
        assert result == {
            "updated": [clear.stage_id],
            "excluded_ambiguous": 1,
            "skipped_ambiguous": [ambiguous.stage_id],
        }
        decisions = {item["stage_id"]: item for item in service.staging(campaign_id)}
        assert decisions[clear.stage_id]["decision"] == "add"
        assert decisions[ambiguous.stage_id]["decision"] == "skip"
        assert decisions[ambiguous.stage_id]["ambiguous_confirmed"] is False

        sync = service.create_sync(campaign_id, confirmation=f"SUBMIT {campaign_id}")
        assert sync["state"] == "reviewed"
    finally:
        product.close()


def test_publication_auto_excludes_undecided_ambiguous_from_old_ui(tmp_path: Path) -> None:
    product = AdminWorkspace.open(working_directory=tmp_path / "admin")
    try:
        service = product.admin_campaigns
        assert service is not None
        now = "2026-08-14T00:00:00Z"
        campaign_id = "campaign:old-ui"
        clear = AdminStagedItem(
            stage_id="stage:accepted",
            campaign_id=campaign_id,
            entity="work",
            match_kind="new",
            proposed={"work_id": "W-ACCEPTED", "title": "Accepted paper"},
            decision="add",
        )
        ambiguous = AdminStagedItem(
            stage_id="stage:left-behind",
            campaign_id=campaign_id,
            entity="work",
            match_kind="ambiguous",
            proposed={"work_id": "W-LEFT-BEHIND", "title": "Possible duplicate"},
        )
        with product.repository.connect() as conn:
            conn.execute(
                "INSERT INTO admin_campaigns VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    campaign_id, None, None, "review_ready", "old browser", 2,
                    "release:base", "commit:base", "digest:base", "{}",
                    '{"research_goal":"old browser"}', now, now,
                ),
            )
            for item in (clear, ambiguous):
                conn.execute(
                    "INSERT INTO admin_staged_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        item.stage_id, campaign_id, str(item.proposed["work_id"]), item.entity,
                        item.match_kind, item.similarity, item.decision, 0, None, "",
                        "content-digest", item.model_dump_json(), item.created_at,
                        item.updated_at,
                    ),
                )

        sync = service.create_sync(campaign_id, confirmation=f"SUBMIT {campaign_id}")
        assert sync["state"] == "reviewed"
        rows = {item["stage_id"]: item for item in service.staging(campaign_id)}
        assert rows[ambiguous.stage_id]["decision"] == "skip"
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
