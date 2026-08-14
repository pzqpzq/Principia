from __future__ import annotations

import time
from pathlib import Path

from principia.application import Principia
from principia.cloud import (
    CanonicalCloudRepository,
    CloudSearchRequest,
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
    # The original package migration is a permanent lower bound; reviewed
    # Admin publications legitimately grow the canonical Cloud afterward.
    assert validation["counts"]["works"] >= 18
    assert validation["counts"]["principles"] >= 62
    assert validation["counts"]["principle-work"] >= 191
    assert validation["counts"]["relations"] >= 36
    principles = repository.records("principles")
    migrated = [item for item in principles if item["review_status"] == "unassessed"]
    assert len(migrated) == 62
    assert {item["maturity"] for item in migrated} == {"unassessed"}


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
    assert verify_cloud_snapshot(applied).principle_count == len(
        CanonicalCloudRepository(canonical_root()).records("principles")
    )


def test_verified_snapshot_exposes_complete_canonical_publication_baseline(
    tmp_path: Path,
) -> None:
    snapshot = tmp_path / "canonical.pcg"
    repository = CanonicalCloudRepository(canonical_root())
    build_cloud_snapshot(
        canonical_root(), snapshot, release_id="canonical", created_at="2026-08-13T00:00:00Z"
    )
    store = GlobalCloudSnapshotStore(tmp_path / "cache")
    store.install_snapshot(snapshot)

    records = store.canonical_records()

    assert {kind: len(rows) for kind, rows in records.items()} == {
        kind: len(repository.records(kind))
        for kind in ("works", "principles", "principle-work", "relations")
    }
    assert CanonicalCloudRepository(canonical_root()).validate()["content_digest"] == store.status()[
        "content_digest"
    ]


def test_research_goal_run_opens_frozen_explorer_membership(tmp_path: Path) -> None:
    snapshot = tmp_path / "global.pcg"
    build_cloud_snapshot(
        canonical_root(), snapshot, release_id="fixture", created_at="2026-08-13T00:00:00Z"
    )
    app = Principia.open(
        working_directory=tmp_path / "working",
        cloud_root=tmp_path / "isolated-cloud-cache",
    )
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
        graph = app.explorer.graph_view(
            scope="global",
            goal_run_id=run["run_id"],
            limit=100,
            evidence_status="",
        )
        assert graph["total_count"] == page["total"]
        assert {item["id"] for item in graph["nodes"]} == {
            item["id"] for item in page["items"]
        }
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


def test_all_entity_search_pages_one_combined_result_set(tmp_path: Path) -> None:
    snapshot = tmp_path / "global.pcg"
    build_cloud_snapshot(
        canonical_root(), snapshot, release_id="fixture", created_at="2026-08-13T00:00:00Z"
    )
    store = GlobalCloudSnapshotStore(tmp_path / "cache")
    store.install_snapshot(snapshot)
    request = CloudSearchRequest(entity="all", query="multi agent", limit=5)
    first = store.search(request)
    second = store.search(request.model_copy(update={"cursor": first["next_cursor"]}))

    assert first["total"] > 5
    assert first["next_cursor"]
    assert not ({item["id"] for item in first["items"]} & {item["id"] for item in second["items"]})


def test_global_principle_details_project_public_paper_links(tmp_path: Path) -> None:
    snapshot = tmp_path / "global.pcg"
    build_cloud_snapshot(
        canonical_root(), snapshot, release_id="fixture", created_at="2026-08-13T00:00:00Z"
    )
    store = GlobalCloudSnapshotStore(tmp_path / "cache")
    store.install_snapshot(snapshot)

    result = store.search(CloudSearchRequest(entity="principle", query="multi agent", limit=20))

    assert result["items"]
    for item in result["items"]:
        detail = store.principle(item["principle_id"])
        assert detail is not None
        assert detail["source_references"]
        assert all(
            reference["source_url"].startswith("https://")
            for reference in detail["source_references"]
        )
