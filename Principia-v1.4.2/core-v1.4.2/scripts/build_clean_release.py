"""Build a source release from an explicit allowlist, with a size gate."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path

EXCLUDED = {".git", ".venv", "node_modules", "runtime", "evaluation", ".principia",
            ".secrets", "secrets", "__pycache__", ".pytest_cache", ".ruff_cache",
            ".mypy_cache", "build", "dist", "local_data", "principia_outputs"}
PRODUCT_PARTS = {"src", "frontend", "docs", "tests", "scripts", "global-cloud", "examples",
                 "pyproject.toml", "README.md", "CHANGELOG.md", "LICENSE", "UPSTREAM.md",
                 "openapi-admin-v1.json",
                 "qa-v1.4.1.json", "qa-v1.4.2.json", ".gitignore"}


def allowed(path: Path) -> bool:
    if "global-cloud" in path.parts and ("global-v1" in path.parts or path.name.startswith("registry.sqlite")):
        return False
    return not (any(part in EXCLUDED for part in path.parts)
                or path.name.startswith(("._", ".env"))
                or path.name == ".DS_Store"
                or path.name in {"credentials.json", "provider-secrets.json"}
                or path.suffix in {".env", ".pyc", ".pyo", ".log", ".tsbuildinfo"})


def product_files(item: Path, source: Path):
    if item.is_symlink() or not allowed(item.relative_to(source)):
        return
    if item.is_file():
        yield item
        return
    for root, directories, names in os.walk(item, followlinks=False):
        base = Path(root)
        directories[:] = [name for name in directories
                          if not (base / name).is_symlink() and allowed((base / name).relative_to(source))]
        for name in names:
            path = base / name
            if path.is_file() and not path.is_symlink() and allowed(path.relative_to(source)):
                yield path


def build_clean_release(source: Path, destination: Path, *, maximum_bytes: int = 192 * 1024**2,
                        products: tuple[str, ...] = ("core-v1.4.2",)) -> dict:
    source, destination = source.resolve(), destination.resolve()
    if source == destination or source in destination.parents:
        raise ValueError("The clean release must be outside the source folder.")
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Destination must be empty; existing user work is never replaced.")
    candidates = []
    for product in products:
        if Path(product).name != product or product in {".", ".."}:
            raise ValueError("Product names must be direct child directories.")
        for name in sorted(PRODUCT_PARTS):
            item = source / product / name
            if item.exists():
                candidates.extend(product_files(item, source))
    meta = source / "meta-principles"
    if meta.exists():
        candidates.extend(product_files(meta, source))
    for name in ("start_local.py", "build_clean_release.py"):
        launcher = source / "scripts" / name
        if launcher.is_file():
            candidates.append(launcher)
    files = [p for p in candidates if p.is_file() and not p.is_symlink()
             and allowed(p.relative_to(source))
             and not any(parent.is_symlink() for parent in p.parents if parent != source)]
    total = sum(p.stat().st_size for p in files)
    if total > maximum_bytes:
        raise ValueError(f"Clean release exceeds its size budget: {total} > {maximum_bytes} bytes")
    if not any(p.relative_to(source).as_posix() == "core-v1.4.2/src/principia/ui_dist/index.html" for p in files):
        raise ValueError("Build the frontend before preparing a runnable clean release.")
    demo_manifest_path = source / "core-v1.4.2/src/principia/demo_projects/manifest.json"
    demos = json.loads(demo_manifest_path.read_text()) if demo_manifest_path.is_file() else {}
    if demos:
        bundle = demo_manifest_path.with_name("public-v142.json.gz")
        if demos.get("raw_data_included") is not False or hashlib.sha256(bundle.read_bytes()).hexdigest() != demos.get("sha256"):
            raise ValueError("Bundled demo integrity or raw-data boundary failed")
    destination.mkdir(parents=True, exist_ok=True)
    manifest = []
    for file in sorted(files):
        relative = file.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, target)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        manifest.append({"path": relative.as_posix(), "bytes": target.stat().st_size, "sha256": digest})
    receipt = {"schema_version": "principia.clean-release/v1", "version": "1.4.2",
               "initial_projects": int(demos.get("project_count", 0)),
               "initial_sources": int(demos.get("source_count", 0)),
               "initial_runs": int(demos.get("project_count", 0)),
               "demo_bundle_sha256": demos.get("sha256", ""),
               "source_bytes": total, "maximum_source_bytes": maximum_bytes,
               "excluded": sorted(EXCLUDED), "files": manifest}
    (destination / "CLEAN_RELEASE.json").write_text(json.dumps(receipt, indent=2) + "\n")
    (destination / ".gitignore").write_text("runtime/\n**/.venv/\n**/node_modules/\n**/__pycache__/\n**/.secrets/\n**/.env\n**/*.log\n")
    (destination / "AGENTS.md").write_text("Respond in English. Read instruction.md before development.\n")
    (destination / "instruction.md").write_text(
        "# Clean v1.4.2 development workspace\n\n"
        "Work in core-v1.4.2. This release includes only curated public demo projects, if bundled. "
        "Keep source datasets read-only and separate from runtime/. Never copy an old runtime, "
        "virtual environment, node_modules, or credentials into a new release. Use "
        "scripts/build_clean_release.py in the release root; its size and exclusion gates are mandatory. "
        "Inspect and archive disposable test workspaces after verification. Preserve scientific "
        "receipts and negative evidence. GET requests must not repair or migrate data. "
        "Rules require persisted executable laws and unchanged scientific evidence gates. "
        "Run relevant tests, then the full backend suite, frontend tests/build, Ruff, and schema check. "
        "No commit, push, publication, or upload without explicit user authorization.\n")
    (destination / "README.md").write_text(
        "# Principia v1.4.2\n\n"
        "This folder contains the product source and bundled public scientific knowledge. "
        + (f"It includes {demos['project_count']} curated public demo projects with equations, study maps, "
           "and recorded evidence. Original datasets are not required to browse them. " if demos else "")
        + "It contains no private source data or API credentials.\n\n"
        "## Start locally\n\n"
        "With Python 3.11 or newer, install once:\n\n"
        "```sh\ncd core-v1.4.2\npython3 -m venv .venv\n"
        ".venv/bin/python -m pip install '.[asd,local]'\ncd ..\n"
        "python3 scripts/start_local.py --port 8142 --browser\n```\n\n"
        "Start with `python3 scripts/start_local.py --port 8142`. The launcher uses a local "
        "core-v1.4.2/.venv or the shared dependency runtime on this computer. If unavailable, "
        "create the local virtual environment and install `.[asd,local]` from core-v1.4.2. "
        "The bundled frontend needs no node_modules to run.\n\n"
        "User state lives in runtime/user-workspace/. Demos are installed once in an empty "
        "workspace; existing projects and demo deletions are respected. To explore your own "
        "data, configure API & models in the interface, add a local folder, and start discovery. "
        "No author credentials are provided or needed for offline demo viewing. To rerun a "
        "demo, obtain its public source data and connect the folder. Dependency libraries are "
        "installed separately and counted separately from this "
        "source folder. See core-v1.4.2/docs/v1.4.2/storage-policy.md for storage maintenance.\n")
    return {key: value for key, value in receipt.items() if key != "files"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--maximum-mib", type=int, default=192)
    args = parser.parse_args()
    print(json.dumps(build_clean_release(args.source, args.destination, maximum_bytes=args.maximum_mib * 1024**2), indent=2))
