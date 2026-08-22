from __future__ import annotations

import shutil
import sqlite3
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
from principia.cloud.snapshot import _fts_query, _readable_principle_payload
from principia.domain.hashing import file_sha256

ROOT = Path(__file__).resolve().parents[1]


def canonical_root() -> Path:
    configured = __import__("os").environ.get("PRINCIPIA_GLOBAL_CANONICAL_ROOT", "")
    candidates = [Path(configured).expanduser()] if configured else []
    candidates.extend(parent / "global-cloud" for parent in ROOT.parents)
    candidates.insert(0, ROOT / "global-cloud")
    return next(path.resolve() for path in candidates if (path / "CLOUD_VERSION").is_file())


def build_v1_fixture(root: Path, snapshot: Path, *, release_id: str = "v1-fixture") -> None:
    (root / "data" / "v1").mkdir(parents=True)
    repository = CanonicalCloudRepository(root)
    repository.write_records("works", [])
    repository.write_records(
        "principles",
        [
            {
                "principle_id": "prn:foundations:01ARZ3NDEKTSV4RRFFQ69G5FAV",
                "revision": 1,
                "area": "foundations",
                "title": "A literature Principle in a v1 snapshot",
                "claim": "A verified literature result remains a literature result.",
                "kind": "empirical",
                "maturity": "supported",
                "scope": {},
                "falsifier": "A controlled observation contradicts the result.",
                "quality": {},
                "tags": ["fixture"],
                "status": "active",
                "review_status": "reviewed",
            }
        ],
    )
    repository.write_records("principle-work", [])
    repository.write_records("relations", [])
    build_cloud_snapshot(root, snapshot, release_id=release_id)


def test_migrated_global_cloud_baseline_and_review_status() -> None:
    repository = CanonicalCloudRepository(canonical_root())
    validation = repository.validate()
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


def test_changed_delta_is_logically_equal_to_its_full_snapshot(tmp_path: Path) -> None:
    target_root = tmp_path / "canonical"
    shutil.copytree(canonical_root(), target_root)
    repository = CanonicalCloudRepository(target_root)
    works = repository.records("works")
    works[0] = {**works[0], "title": works[0]["title"] + " updated", "content_digest": ""}
    repository.write_records("works", works)
    base = tmp_path / "base.pcg"
    target = tmp_path / "target.pcg"
    delta = tmp_path / "changed.pcd"
    applied = tmp_path / "applied.pcg"
    build_cloud_snapshot(
        canonical_root(), base, release_id="base", created_at="2026-08-13T00:00:00Z"
    )
    target_manifest = build_cloud_snapshot(
        target_root, target, release_id="target", created_at="2026-08-14T00:00:00Z"
    )
    build_cloud_delta(base, target, delta)

    applied_manifest = apply_cloud_delta(base, delta, applied)

    assert applied_manifest.content_digest == target_manifest.content_digest
    assert applied_manifest.work_count == target_manifest.work_count


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
    assert repository.validate()["content_digest"] == store.status()["content_digest"]


def test_research_goal_run_opens_frozen_explorer_membership(tmp_path: Path) -> None:
    snapshot = tmp_path / "global.pcg"
    build_cloud_snapshot(
        canonical_root(), snapshot, release_id="fixture", created_at="2026-08-13T00:00:00Z"
    )
    # Never let a test fixture replace the application-level cache shared by
    # another running application process.
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


def test_install_can_pin_an_older_verified_release_as_rollback(tmp_path: Path) -> None:
    first = tmp_path / "first.pcg"
    second = tmp_path / "second.pcg"
    build_cloud_snapshot(
        canonical_root(), first, release_id="first", created_at="2026-08-12T00:00:00Z"
    )
    build_cloud_snapshot(
        canonical_root(), second, release_id="second", created_at="2026-08-13T00:00:00Z"
    )
    store = GlobalCloudSnapshotStore(tmp_path / "cache")
    store.install_snapshot(first)
    store.install_snapshot(second, rollback_release_id="first")

    assert store.active()["release_id"] == "second"
    assert store.rollback()["release_id"] == "first"


def test_all_entity_search_reports_and_pages_the_combined_result_set(tmp_path: Path) -> None:
    snapshot = tmp_path / "global.pcg"
    build_cloud_snapshot(
        canonical_root(), snapshot, release_id="fixture", created_at="2026-08-13T00:00:00Z"
    )
    store = GlobalCloudSnapshotStore(tmp_path / "cache")
    store.install_snapshot(snapshot)
    request = CloudSearchRequest(entity="all", query="multi agent", limit=5)
    first = store.search(request)
    assert first["total"] >= len(first["items"])
    assert first["total"] > 5
    assert first["next_cursor"]

    second = store.search(request.model_copy(update={"cursor": first["next_cursor"]}))
    assert not ({item["id"] for item in first["items"]} & {item["id"] for item in second["items"]})

    complete = store.search(request.model_copy(update={"limit": 200}))
    assert {item["entity"] for item in complete["items"]} == {"paper", "principle"}
    combined_items = list(complete["items"])
    while complete["next_cursor"]:
        complete = store.search(
            request.model_copy(update={"limit": 200, "cursor": complete["next_cursor"]})
        )
        combined_items.extend(complete["items"])
    assert len(combined_items) == complete["total"]
    assert len({item["id"] for item in combined_items}) == len(combined_items)


def test_global_principle_details_project_public_paper_links(tmp_path: Path) -> None:
    snapshot = tmp_path / "global.pcg"
    build_cloud_snapshot(
        canonical_root(), snapshot, release_id="fixture", created_at="2026-08-13T00:00:00Z"
    )
    store = GlobalCloudSnapshotStore(tmp_path / "cache")
    store.install_snapshot(snapshot)
    result = store.search(
        CloudSearchRequest(entity="principle", query="multi agent", limit=20)
    )
    assert result["items"]
    for item in result["items"]:
        detail = store.principle(item["principle_id"])
        assert detail is not None
        assert detail["source_references"]
        work_ids = [reference["work_id"] for reference in detail["source_references"]]
        assert len(work_ids) == len(set(work_ids))
        assert all(
            reference["source_url"].startswith("https://")
            for reference in detail["source_references"]
        )


def test_offline_conceptual_search_recalls_solution_related_principles(tmp_path: Path) -> None:
    snapshot = tmp_path / "global.pcg"
    build_cloud_snapshot(
        canonical_root(), snapshot, release_id="fixture", created_at="2026-08-13T00:00:00Z"
    )
    store = GlobalCloudSnapshotStore(tmp_path / "cache")
    store.install_snapshot(snapshot)

    result = store.search(
        CloudSearchRequest(
            entity="principle",
            query="how does multi-agent system improve math theorem proving",
            limit=12,
        )
    )

    assert result["ranking_mode"] == "paper_first_conceptual_fts"
    assert result["items"]
    searchable = " ".join(
        f"{item.get('title', '')} {item.get('claim', '')} {item.get('area', '')}"
        for item in result["items"]
    ).casefold()
    assert any(term in searchable for term in ("agent", "collabor", "coordination"))


def test_offline_two_concept_search_does_not_degrade_to_broad_or_matching() -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE VIRTUAL TABLE papers USING fts5(title, abstract)")
    connection.executemany(
        "INSERT INTO papers(title, abstract) VALUES (?, ?)",
        [
            ("Generic LLM evaluation", "A language model benchmark."),
            ("Post-training optimization", "A generic post-training method."),
            ("LLM post-training", "A post-training method for language models."),
        ],
    )

    matches = {
        row[0]
        for row in connection.execute(
            "SELECT title FROM papers WHERE papers MATCH ?", (_fts_query("LLM post-training"),)
        )
    }

    assert matches == {"LLM post-training"}


def test_offline_single_concept_search_uses_scientific_synonyms() -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE VIRTUAL TABLE principles USING fts5(title, claim)")
    connection.executemany(
        "INSERT INTO principles(title, claim) VALUES (?, ?)",
        [
            ("Formal proof search", "Deduction under explicit rules."),
            ("Generic language model", "Text generation."),
        ],
    )
    matches = {
        row[0]
        for row in connection.execute(
            "SELECT title FROM principles WHERE principles MATCH ?",
            (_fts_query("theorem proving"),),
        )
    }
    assert matches == {"Formal proof search"}


def test_offline_multi_agent_scientific_discovery_is_a_two_concept_query() -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE VIRTUAL TABLE principles USING fts5(title, claim)")
    connection.executemany(
        "INSERT INTO principles(title, claim) VALUES (?, ?)",
        [
            (
                "Coordinated autonomous laboratory",
                "Agent collaboration closes the loop between hypothesis and experiment.",
            ),
            ("Generic agent benchmark", "Agent collaboration on a game task."),
        ],
    )
    matches = {
        row[0]
        for row in connection.execute(
            "SELECT title FROM principles WHERE principles MATCH ?",
            (_fts_query("multi-agent scientific discovery"),),
        )
    }
    assert matches == {"Coordinated autonomous laboratory"}


def test_study_bound_marker_projects_as_a_specific_human_interpretation() -> None:
    projected = _readable_principle_payload(
        {
            "interpretation": "study_bound",
            "conditions": ["coordination failures are not perfectly correlated"],
            "boundary": ["Transfer to single-agent systems is unestablished."],
        }
    )
    assert projected["interpretation"].startswith("Apply this result only when")
    assert "coordination failures" in projected["interpretation"]
    assert "single-agent" in projected["interpretation"]


def test_global_graph_pages_are_disjoint_and_report_complete_total(tmp_path: Path) -> None:
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
        first = app.explorer.graph_view(
            scope="global", evidence_status="checks_passed", limit=30, page=1
        )
        second = app.explorer.graph_view(
            scope="global", evidence_status="checks_passed", limit=30, page=2
        )
        assert first["total_count"] == app.global_cloud.status()["principle_count"]
        assert second["total_count"] == first["total_count"]
        assert not (
            {item["id"] for item in first["nodes"]}
            & {item["id"] for item in second["nodes"]}
        )
    finally:
        app.close()


def test_sync_refetches_control_when_active_pointer_and_etag_state_disagree(
    tmp_path: Path, monkeypatch,
) -> None:
    valid = tmp_path / "valid.pcg"
    stale = tmp_path / "stale.pcg"
    build_cloud_snapshot(
        canonical_root(), valid, release_id="verified", created_at="2026-08-13T00:00:00Z"
    )
    build_cloud_snapshot(
        canonical_root(), stale, release_id="fixture", created_at="2026-08-12T00:00:00Z"
    )
    store = GlobalCloudSnapshotStore(tmp_path / "cache")
    store.install_snapshot(valid)
    store._atomic_json(
        store.state_path,
        {
            "schema_version": "principia-global-sync-state-v1",
            "release_id": "verified",
            "etag": '"verified-etag"',
            "last_checked_epoch": time.time(),
            "last_error": "",
        },
    )
    store.install_snapshot(stale)

    class _Response:
        status_code = 200
        headers = {"etag": '"new-etag"'}

        def json(self) -> dict[str, object]:
            return {
                "release_id": "verified",
                "snapshot_url": "https://example.test/verified.pcg",
                "snapshot_sha256": file_sha256(valid),
                "snapshot_bytes": valid.stat().st_size,
            }

        def raise_for_status(self) -> None:
            return None

    class _Download:
        def __enter__(self) -> _Download:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def raise_for_status(self) -> None:
            return None

        def iter_bytes(self):  # type: ignore[no-untyped-def]
            yield valid.read_bytes()

    class _Client:
        observed_headers: dict[str, str] = {}

        def __init__(self, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> _Client:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def get(self, _url: str, *, headers: dict[str, str]) -> _Response:
            self.observed_headers = headers
            assert "If-None-Match" not in headers
            return _Response()

        def stream(self, _method: str, _url: str) -> _Download:
            return _Download()

    monkeypatch.setattr("principia.cloud.snapshot.httpx.Client", _Client)
    assert store.sync()["release_id"] == "verified"
    assert store.status()["work_count"] == len(
        {row["work_id"] for row in CanonicalCloudRepository(canonical_root()).records("works")}
    )


def test_v1_snapshot_never_labels_literature_as_meta(tmp_path: Path) -> None:
    snapshot = tmp_path / "v1.pcg"
    build_v1_fixture(tmp_path / "v1-cloud", snapshot)
    store = GlobalCloudSnapshotStore(tmp_path / "cache")
    store.install_snapshot(snapshot)

    browse = store.search(CloudSearchRequest(entity="meta_principle", query="", limit=20))
    search = store.search(
        CloudSearchRequest(entity="meta_principle", query="literature result", limit=20)
    )

    assert browse["items"] == []
    assert browse["total"] == 0
    assert search["items"] == []
    assert search["total"] == 0


def test_background_sync_cannot_downgrade_a_verified_v2_snapshot(
    tmp_path: Path, monkeypatch
) -> None:
    v2 = tmp_path / "v2.pcg"
    build_cloud_snapshot(canonical_root(), v2, release_id="verified-v2")
    v1 = tmp_path / "v1.pcg"
    build_v1_fixture(tmp_path / "v1-cloud", v1, release_id="published-v1")
    store = GlobalCloudSnapshotStore(tmp_path / "cache")
    store.install_snapshot(v2)

    class _Response:
        status_code = 200
        headers = {"etag": '"published-v1"'}

        def json(self) -> dict[str, object]:
            return {
                "release_id": "published-v1",
                "snapshot_url": "https://example.test/published-v1.pcg",
                "snapshot_sha256": file_sha256(v1),
                "snapshot_bytes": v1.stat().st_size,
            }

        def raise_for_status(self) -> None:
            return None

    class _Download:
        def __enter__(self) -> _Download:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def raise_for_status(self) -> None:
            return None

        def iter_bytes(self):  # type: ignore[no-untyped-def]
            yield v1.read_bytes()

    class _Client:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> _Client:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def get(self, _url: str, *, headers: dict[str, str]) -> _Response:
            return _Response()

        def stream(self, _method: str, _url: str) -> _Download:
            return _Download()

    monkeypatch.setattr("principia.cloud.snapshot.httpx.Client", _Client)

    result = store.sync(force=True)

    assert result["outcome"] == "schema_downgrade_blocked"
    assert result["release_id"] == "verified-v2"
    assert result["remote_release_id"] == "published-v1"
    assert store.active()["release_id"] == "verified-v2"
    assert store.status()["meta_principle_count"] > 0
    assert not (store.downloads_dir / "published-v1.pcg.partial").exists()
