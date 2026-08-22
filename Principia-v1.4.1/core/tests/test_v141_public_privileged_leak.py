from __future__ import annotations

from pathlib import Path


def test_public_tree_contains_no_privileged_maintenance_implementation() -> None:
    root = Path(__file__).resolve().parents[1]
    forbidden = (
        "principia." + "ad" + "min",
        "Ad" + "minWorkspace",
        "Ad" + "minPage",
        "/api/v1/" + "ad" + "min",
        "principia-" + "ad" + "min-local",
    )
    checked = [
        root / "src",
        root / "frontend" / "src",
        root / "scripts",
        root / "docs",
        root / "README.md",
        root / "CHANGELOG.md",
        root / "pyproject.toml",
    ]
    leaks: list[str] = []
    for candidate in checked:
        paths = [candidate] if candidate.is_file() else list(candidate.rglob("*"))
        for path in paths:
            if not path.is_file() or path.suffix in {".pyc", ".png", ".jpg", ".pcg", ".f16"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(token in text for token in forbidden):
                leaks.append(str(path.relative_to(root)))
    assert leaks == []


def test_public_source_has_no_privileged_named_paths() -> None:
    root = Path(__file__).resolve().parents[1]
    marker = "ad" + "min"
    paths = [
        path
        for base in (root / "src", root / "frontend" / "src", root / "docs")
        for path in base.rglob("*")
        if marker in path.name.casefold()
    ]
    assert paths == []
