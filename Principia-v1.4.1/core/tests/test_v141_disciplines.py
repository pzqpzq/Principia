from __future__ import annotations

from pathlib import Path

from principia.cloud import CloudSearchRequest, GlobalCloudSnapshotStore, build_cloud_snapshot
from principia.cloud.disciplines import classify_scientific_discipline

ROOT = Path(__file__).resolve().parents[1]


def canonical_root() -> Path:
    configured = __import__("os").environ.get("PRINCIPIA_GLOBAL_CANONICAL_ROOT", "")
    candidates = [Path(configured).expanduser()] if configured else []
    candidates.extend(parent / "global-cloud" for parent in (ROOT, *ROOT.parents))
    return next(path.resolve() for path in candidates if (path / "CLOUD_VERSION").is_file())


def test_discipline_classifier_uses_concrete_scholarly_fields() -> None:
    assert classify_scientific_discipline(
        {"area": "general", "title": "Liquidity buffers", "claim": "Cash-flow visibility reduces financial distress."},
        [{"title": "Working capital and firm resilience", "abstract": "Liquidity and financing constraints."}],
    ) == "economics-game-theory"
    assert classify_scientific_discipline(
        {"area": "hilbert", "title": "Kinetic limits", "claim": "A theorem establishes convergence."}
    ) == "mathematics-logic"
    assert classify_scientific_discipline(
        {"area": "general", "title": "Quantum phases", "claim": "A phase transition occurs."}
    ) == "physics"


def test_snapshot_projects_legacy_areas_without_mutating_canonical_records(
    tmp_path: Path,
) -> None:
    snapshot = tmp_path / "disciplines.pcg"
    build_cloud_snapshot(
        canonical_root(),
        snapshot,
        release_id="disciplines",
        created_at="2026-08-20T00:00:00Z",
    )
    store = GlobalCloudSnapshotStore(tmp_path / "cache")
    store.install_snapshot(snapshot)
    request = CloudSearchRequest(entity="principle", query="", limit=100)
    result = store.search(request)
    items = list(result["items"])
    while result["next_cursor"]:
        result = store.search(request.model_copy(update={"cursor": result["next_cursor"]}))
        items.extend(result["items"])
    areas = {item["area"] for item in items}
    assert len(items) == 676
    assert "general" not in areas
    assert "hilbert" not in areas
    assert {"mathematics-logic", "ai-ml", "neuroscience-cognition"} <= areas

    canonical_areas = {row["area"] for row in store.canonical_records()["principles"]}
    assert "general" in canonical_areas
    assert canonical_areas != areas
