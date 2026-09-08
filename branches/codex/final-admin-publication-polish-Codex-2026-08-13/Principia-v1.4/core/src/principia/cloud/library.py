from __future__ import annotations

import os
from pathlib import Path

PACKAGE_LIBRARY_ENV = "PRINCIPIA_PACKAGE_LIBRARY"


def discover_package_library(start: str | Path | None = None) -> Path | None:
    """Find an adjacent, application-level Principle package library.

    The selected working directory is deliberately not searched: private workspace
    state and downloaded Principle packages have different lifecycles.  An explicit
    environment value wins, followed by a checkout-style sibling directory.
    """

    configured = os.getenv(PACKAGE_LIBRARY_ENV, "").strip()
    if configured:
        return Path(configured).expanduser().resolve()

    origin = Path(start).expanduser().resolve() if start is not None else Path.cwd().resolve()
    candidates = [origin / "principle-packages", origin.parent / "principle-packages"]
    for parent in Path(__file__).resolve().parents:
        candidates.append(parent / "principle-packages")

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if (resolved / "catalog.json").is_file():
            return resolved
    return None


def resolve_package_library(
    value: str | Path | None,
    *,
    discover: bool,
) -> Path | None:
    resolved = Path(value).expanduser().resolve() if value is not None else None
    if resolved is None and discover:
        resolved = discover_package_library()
    if resolved is not None:
        resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def package_registry_root(package_library: Path) -> Path:
    """Return rebuildable runtime state inside the shared package library."""

    return package_library / ".principia"
