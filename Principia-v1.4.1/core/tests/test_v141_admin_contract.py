from __future__ import annotations

from pathlib import Path

import pytest

from principia.application import AdminWorkspace
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
