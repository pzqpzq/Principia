from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_production_frontend_graph_is_an_optional_bounded_explorer_view() -> None:
    package = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    dependencies = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
    assert "@xyflow/react" in dependencies
    assert "d3-force" not in dependencies
    assert "@types/d3-force" not in dependencies
    assert not (ROOT / "frontend" / "src" / "workers" / "graphLayout.worker.ts").exists()
    graph = (ROOT / "frontend" / "src" / "components" / "PrincipleGraph.tsx").read_text(
        encoding="utf-8"
    )
    explorer = (ROOT / "frontend" / "src" / "pages" / "MapPage.tsx").read_text(
        encoding="utf-8"
    )
    assert "ReactFlow" in graph
    assert "nodesDraggable" in graph
    assert "panOnDrag" in graph
    assert "panOnScroll" in graph
    assert "PanOnScrollMode.Free" in graph
    assert "zoomOnScroll={false}" in graph
    assert "zoomOnPinch" in graph
    assert 'type: "bezier"' in graph
    assert "connectedComponents" in graph
    assert "isolates" in graph
    assert "Derive Virtual Connection" in graph
    assert "Select 2–20 Principles" in graph
    assert "Selected Principles tray" in graph
    assert 'value="macaron"' in graph
    assert ">Daylight</option>" in graph
    assert 'value="midnight"' in graph
    assert "Present</button>" not in graph
    assert ">Palette</span>" not in graph
    assert "Selected Principle details" in graph
    assert "Virtual work tray" in graph
    assert "Temporary connection batches" in graph
    assert "Generated hypothesis batches" in graph
    assert "Synthesis in progress" in graph
    assert "Close Virtual Principle studio" in graph
    assert "onOpenSavedVirtualLibrary" in graph
    assert "Open saved hypothesis" in graph
    assert "virtual-principle-edge" in graph
    assert "onAnalyzePotentialRelations" in graph
    assert "MiniMap" not in graph
    assert 'params.get("view") === "graph"' in explorer
    assert 'params.get("virtual") === "true"' in explorer
    assert "Saved Virtual Principles" in explorer
    assert "lazy(() => import" in explorer


def test_local_ui_exposes_paths_optional_focus_credentials_and_readable_copy() -> None:
    source = (ROOT / "frontend" / "src" / "pages" / "LocalPage.tsx").read_text(encoding="utf-8")
    for required in (
        "absolute_path",
        "Copy Path",
        "Open Folder",
        "Research focus <em>optional</em>",
        "New API key",
        "Test connection",
        "Boolean(result.ok)",
        "Add papers to this folder",
        "Find papers for this folder",
        "Home searches never write into folders you connected earlier",
        "!homeOnlineSearch && destinationMode === \"existing\"",
        "Ready to review",
        "Held back",
        "setSelectedDocumentIds([])",
    ):
        assert required in source
    assert "second-pass evidence check" in source.casefold()
    assert "<span>Area</span><select" not in source
    assert "Independent Challenge" not in source
    assert "Scientific Principle Contract" not in source


def test_explorer_uses_cards_and_keeps_technical_terms_collapsed() -> None:
    source = (ROOT / "frontend" / "src" / "pages" / "MapPage.tsx").read_text(encoding="utf-8")
    assert "title={collectionTitle}" in source
    assert "Filter Principles" in source
    assert "principle-pagination" in source
    assert "principle-card-grid" in source
    assert "Technical record" in source
    assert "truth probability or real-world importance" in source
    assert "Research question</span>" not in source
    assert "Load 24 more" not in source
    assert "Graph Mode" in source
    assert "explorerAreaOptions" in source
    assert "ready to review in Principles Library" in source
    assert "match current filters" in source
    assert "same Areas shown in Principles Library" in source
    assert "contextualAreaRows" not in source


def test_downloaded_candidate_packages_never_claim_human_review() -> None:
    library = (ROOT / "frontend" / "src" / "pages" / "LibraryPage.tsx").read_text(
        encoding="utf-8"
    )
    explorer = (ROOT / "frontend" / "src" / "pages" / "MapPage.tsx").read_text(
        encoding="utf-8"
    )
    assert "Shared Principle Package Library" in library
    assert "Human review pending" in library
    assert "Paper files not included" in library
    assert "Downloaded Principle · Human review pending" in explorer
    assert "Open source paper" in explorer
