from __future__ import annotations

import time
from pathlib import Path

from principia.application import Principia
from principia.cloud import (
    CanonicalCloudRepository,
    GlobalCloudSnapshotStore,
    apply_cloud_delta,
    build_cloud_delta,
    build_cloud_snapshot,
    verify_cloud_snapshot,
)
from principia.domain.hashing import file_sha256

ROOT = Path(__file__).resolve().parents[1]


def canonical_root() -> Path:
    configured = __import__("os").environ.get("PRINCIPIA_GLOBAL_CANONICAL_ROOT", "")
    candidates = [Path(configured).expanduser()] if configured else []
    candidates.extend(parent / "global-cloud" for parent in ROOT.parents)
    candidates.insert(0, ROOT / "global-cloud")
    return next(path.resolve() for path in candidates if (path / "CLOUD_VERSION").is_file())


def test_migrated_global_cloud_baseline_and_review_status() -> None:
    repository = CanonicalCloudRepository(canonical_root())
    validation = repository.validate()
    assert validation["counts"] == {
        "works": 18,
        "principles": 62,
        "principle-work": 191,
        "relations": 36,
    }
    principles = repository.records("principles")
    assert {item["review_status"] for item in principles} == {"unassessed"}
    assert {item["maturity"] for item in principles} == {"unassessed"}


def test_full_snapshot_and_identity_delta_are_deterministic(tmp_path: Path) -> None:
    stamp = "2026-08-13T00:00:00Z"
    first = tmp_path / "first.pcg"
    second = tmp_path / "second.pcg"
    kwargs = {"release_id": "fixture", "commit_sha": "abc", "created_at": stamp}
    build_cloud_snapshot(canonical_root(), first, **kwargs)
    build_cloud_snapshot(canonical_root(), second, **kwargs)
    assert first.read_bytes() == second.read_bytes()
    delta = tmp_path / "identity.pcd"
    build_cloud_delta(first, second, delta)
    applied = tmp_path / "applied.pcg"
    apply_cloud_delta(first, delta, applied)
    assert applied.read_bytes() == second.read_bytes()
    assert verify_cloud_snapshot(applied).principle_count == 62


def test_research_goal_run_opens_frozen_explorer_membership(tmp_path: Path) -> None:
    snapshot = tmp_path / "global.pcg"
    build_cloud_snapshot(
        canonical_root(), snapshot, release_id="fixture", created_at="2026-08-13T00:00:00Z"
    )
    app = Principia.open(working_directory=tmp_path / "working")
    try:
        app.global_cloud.install_snapshot(snapshot)
        run = app.goal_runs.start(
            __import__(
                "principia.cloud", fromlist=["ResearchGoalRunRequest"]
            ).ResearchGoalRunRequest(
                goal="bounded physical mechanisms in engineered systems",
                include_global=True,
                source_ids=[],
                global_limit=10,
            )
        )
        deadline = time.time() + 5
        while time.time() < deadline:
            detail = app.goal_runs.detail(run["run_id"])
            if detail and detail["state"] in {"succeeded", "partial", "failed"}:
                break
            time.sleep(0.02)
        page = app.explorer.browse(
            scope="global",
            goal_run_id=run["run_id"],
            limit=10,
            page=1,
            page_mode=True,
            evidence_status="",
        )
        assert page["total"] >= len(page["items"])
        assert all(item["source"] == "global" for item in page["items"])
    finally:
        app.close()


def test_corrupt_snapshot_cannot_replace_active_generation(tmp_path: Path) -> None:
    source = tmp_path / "valid.pcg"
    build_cloud_snapshot(
        canonical_root(), source, release_id="valid", created_at="2026-08-13T00:00:00Z"
    )
    store = GlobalCloudSnapshotStore(tmp_path / "cache")
    store.install_snapshot(source)
    active = store.active()
    assert active
    corrupt = tmp_path / "corrupt.pcg"
    corrupt.write_bytes(source.read_bytes()[:100])
    try:
        store.install_snapshot(corrupt)
    except Exception:
        pass
    assert store.active()["release_id"] == active["release_id"]
    assert file_sha256(active["release_root"] / "manifest.json")
