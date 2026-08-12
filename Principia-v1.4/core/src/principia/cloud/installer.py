from __future__ import annotations

import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import httpx

from ..domain import CatalogEntry
from .package import VerifiedPackage, verify_pcp
from .registry import CloudRegistry


class CloudInstaller:
    def __init__(self, registry: CloudRegistry, *, timeout: float = 60) -> None:
        self.registry = registry
        self.timeout = timeout

    def _download(self, entry: CatalogEntry, partial: Path) -> None:
        parsed = urlparse(entry.artifact_url)
        if parsed.scheme in {"", "file"}:
            source = Path(parsed.path if parsed.scheme == "file" else entry.artifact_url)
            with source.open("rb") as read, partial.open("wb") as write:
                shutil.copyfileobj(read, write, 1024 * 1024)
            return
        if parsed.scheme != "https":
            raise ValueError("Cloud artifacts require HTTPS or an explicit local fixture path")
        with httpx.stream("GET", entry.artifact_url, timeout=self.timeout, follow_redirects=True) as response:
            response.raise_for_status()
            with partial.open("wb") as handle:
                for chunk in response.iter_bytes(1024 * 1024):
                    handle.write(chunk)
                    if handle.tell() > entry.artifact_bytes:
                        raise ValueError("download exceeded catalog artifact size")

    def install(self, entry: CatalogEntry) -> VerifiedPackage:
        active_version = self.registry.active_version(entry.area)
        if active_version:
            installed = [
                item
                for item in self.registry.installed()
                if item["area"] == entry.area and item["version"] == active_version
            ]
            if installed and installed[0]["pinned"] and active_version != entry.package_version:
                raise ValueError(f"{entry.area} is pinned at {active_version}")
        partial = self.registry.downloads_dir / f"{entry.area}-{entry.package_version}.pcp.partial"
        try:
            self._download(entry, partial)
            verified = verify_pcp(
                partial,
                expected_artifact_sha256=entry.artifact_sha256,
                expected_artifact_bytes=entry.artifact_bytes,
            )
            if verified.manifest.area != entry.area:
                raise ValueError("package area does not match catalog")
            if verified.manifest.package_version != entry.package_version:
                raise ValueError("package version does not match catalog")
            final_dir = self.registry.version_dir(entry.area, entry.package_version)
            if not final_dir.exists():
                final_dir.parent.mkdir(parents=True, exist_ok=True)
                staging = Path(
                    tempfile.mkdtemp(prefix=f".{entry.package_version}-", dir=final_dir.parent)
                )
                try:
                    package_archive = staging / "package.pcp"
                    os.replace(partial, package_archive)
                    with zipfile.ZipFile(package_archive) as archive:
                        archive.extractall(staging)
                    os.replace(staging, final_dir)
                finally:
                    if staging.exists():
                        shutil.rmtree(staging)
            else:
                partial.unlink(missing_ok=True)
            database_path = final_dir / "area.sqlite"
            self.registry.register(database_path, verified.manifest, verified.artifact_sha256)
            self.registry.activate(entry.area, entry.package_version, verified.manifest)
            return VerifiedPackage(
                final_dir / "package.pcp",
                verified.manifest,
                verified.artifact_sha256,
                verified.artifact_bytes,
            )
        finally:
            partial.unlink(missing_ok=True)

    def verify_installed(self, area: str, version: str | None = None) -> VerifiedPackage:
        resolved = version or self.registry.active_version(area)
        if not resolved:
            raise KeyError(f"area is not installed: {area}")
        return verify_pcp(self.registry.version_dir(area, resolved) / "package.pcp")

    def rollback(self, area: str) -> str:
        active = self.registry.active_version(area)
        versions = [
            item
            for item in self.registry.installed()
            if item["area"] == area and item["version"] != active
        ]
        if not versions:
            raise ValueError(f"no previous version retained for {area}")
        target = versions[0]
        manifest = verify_pcp(Path(target["package_path"]).parent / "package.pcp").manifest
        self.registry.register(Path(target["package_path"]), manifest, target["artifact_sha256"])
        self.registry.activate(area, target["version"], manifest)
        return str(target["version"])


def load_catalog(path: str | Path) -> list[CatalogEntry]:
    catalog_path = Path(path).expanduser().resolve()
    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    entries = data.get("areas", data) if isinstance(data, dict) else data
    if not isinstance(entries, list):
        raise ValueError("catalog must contain an areas list")
    resolved: list[CatalogEntry] = []
    for raw in entries:
        entry = CatalogEntry.model_validate(raw)
        parsed = urlparse(entry.artifact_url)
        if parsed.scheme == "" and not Path(entry.artifact_url).is_absolute():
            entry = entry.model_copy(
                update={"artifact_url": str((catalog_path.parent / entry.artifact_url).resolve())}
            )
        resolved.append(entry)
    return resolved
