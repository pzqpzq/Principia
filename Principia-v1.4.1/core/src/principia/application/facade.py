from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .._version import __version__
from ..admin import AdminCampaignService, AdminService
from ..cloud import (
    CloudInstaller,
    CloudRegistry,
    GlobalCloudSnapshotStore,
    load_catalog,
    package_registry_root,
    global_cloud_cache_root,
    resolve_package_library,
)
from ..domain import CatalogEntry, canonical_sha256
from ..local import LocalDiscoveryService
from ..persistence import V14WorkspaceRepository
from ..scenario import ScenarioService
from ..workspace import Workspace
from .explorer import PrincipleExplorerService
from .goal_runs import ResearchGoalRunService
from .graph import PrincipleGraphService
from .relations import PrincipleRelationService
from .search import PrincipleSearchService


class CloudService:
    def __init__(
        self,
        registry: CloudRegistry,
        *,
        package_library: Path | None = None,
    ) -> None:
        self.registry = registry
        self.package_library = package_library
        self.installer = CloudInstaller(registry)
        self.catalog: dict[tuple[str, str], CatalogEntry] = {}
        self.activation_errors: dict[tuple[str, str], str] = {}
        if registry.cached_catalog_path.exists():
            entries = load_catalog(registry.cached_catalog_path)
            self.catalog = {(item.area, item.package_version): item for item in entries}
        if package_library is not None and (package_library / "catalog.json").is_file():
            local_catalog = package_library / "catalog.json"
            entries = load_catalog(local_catalog)
            self.catalog.update(
                {(item.area, item.package_version): item for item in entries}
            )
            self.registry.cache_catalog(list(self.catalog.values()), source=local_catalog)
            self.activate_downloaded_packages()

    def refresh_catalog(self, path: str | Path) -> list[CatalogEntry]:
        entries = load_catalog(path)
        incoming = {(item.area, item.package_version): item for item in entries}
        if self.package_library is None:
            self.catalog = incoming
        else:
            self.catalog.update(incoming)
        self.registry.cache_catalog(list(self.catalog.values()), source=path)
        return entries

    def _downloaded_library_artifact(self, entry: CatalogEntry) -> Path | None:
        if self.package_library is None:
            return None
        from urllib.parse import urlparse

        parsed = urlparse(entry.artifact_url)
        if parsed.scheme not in {"", "file"}:
            return None
        artifact = Path(parsed.path if parsed.scheme == "file" else entry.artifact_url).resolve()
        try:
            artifact.relative_to(self.package_library)
        except ValueError:
            return None
        return artifact if artifact.is_file() else None

    def activate_downloaded_packages(self) -> list[dict[str, Any]]:
        """Verify and activate already-downloaded local packages once.

        Catalog entries that still point to a remote channel remain available for an
        explicit download.  A damaged local package is isolated to its own card and
        never prevents the private workspace from opening.
        """

        activated: list[dict[str, Any]] = []
        installed = {
            (str(item["area"]), str(item["version"])): item
            for item in self.registry.installed()
        }
        for key, entry in sorted(self.catalog.items()):
            artifact = self._downloaded_library_artifact(entry)
            if artifact is None:
                continue
            current = installed.get(key)
            if (
                current
                and bool(current["active"])
                and str(current["artifact_sha256"]) == entry.artifact_sha256
                and Path(str(current["package_path"])).is_file()
            ):
                continue
            try:
                activated.append(self.install(entry.area, version=entry.package_version))
                self.activation_errors.pop(key, None)
            except Exception as exc:  # one corrupt package must not hide the others
                self.activation_errors[key] = type(exc).__name__
        return activated

    def areas(self) -> list[dict[str, Any]]:
        installed = self.registry.installed()
        installed_keys = {(item["area"], item["version"]): item for item in installed}
        rows: list[dict[str, Any]] = []
        for key, entry in sorted(self.catalog.items()):
            state = installed_keys.get(key)
            downloaded = self._downloaded_library_artifact(entry) is not None
            activation_error = self.activation_errors.get(key)
            rows.append(
                {
                    **entry.model_dump(mode="json"),
                    "installed": bool(state),
                    "active": bool(state and state["active"]),
                    "pinned": bool(state and state["pinned"]),
                    "downloaded": downloaded,
                    "integrity": (
                        "activation_failed"
                        if activation_error
                        else "verified"
                        if state
                        else "downloaded"
                        if downloaded
                        else "not_downloaded"
                    ),
                }
            )
        for key, state in sorted(installed_keys.items()):
            if key in self.catalog:
                continue
            manifest = state["manifest_json"]
            rows.append(
                {
                    **__import__("json").loads(manifest),
                    "artifact_sha256": state["artifact_sha256"],
                    "installed": True,
                    "active": bool(state["active"]),
                    "pinned": bool(state["pinned"]),
                    "integrity": "verified",
                }
            )
        return rows

    def entry(self, area: str, version: str | None = None) -> CatalogEntry:
        matches = [
            item
            for (candidate_area, _), item in self.catalog.items()
            if candidate_area == area and (version is None or item.package_version == version)
        ]
        if not matches:
            raise KeyError(f"catalog has no package for {area}")
        return sorted(matches, key=lambda item: item.package_version, reverse=True)[0]

    def install(self, area: str, *, version: str | None = None) -> dict[str, Any]:
        verified = self.installer.install(self.entry(area, version))
        return {
            "area": verified.manifest.area,
            "version": verified.manifest.package_version,
            "artifact_sha256": verified.artifact_sha256,
            "content_digest": verified.manifest.content_digest,
            "status": "installed",
        }


class Principia:
    def __init__(
        self,
        workspace: Workspace,
        *,
        cloud_root: str | Path | None = None,
        package_library: str | Path | None = None,
        admin_mode: bool = False,
    ) -> None:
        if cloud_root is not None and package_library is not None:
            raise ValueError("choose either cloud_root or package_library, not both")
        self.workspace = workspace
        self.repository = V14WorkspaceRepository(workspace.db_path)
        self.package_library_root = (
            Path(package_library).expanduser().resolve() if package_library is not None else None
        )
        registry_root = (
            package_registry_root(self.package_library_root)
            if self.package_library_root is not None
            else cloud_root
        )
        self.cloud = CloudService(
            CloudRegistry(registry_root), package_library=self.package_library_root
        )
        self.global_cloud = GlobalCloudSnapshotStore(self.cloud.registry.root)
        self.search = PrincipleSearchService(
            self.cloud.registry, self.repository, global_cloud=self.global_cloud
        )
        self.graph = PrincipleGraphService(self.search)
        self.explorer = PrincipleExplorerService(
            self.cloud.registry, self.repository, global_cloud=self.global_cloud
        )
        relation_snapshot_export = None
        if workspace.layout == "project":
            def relation_snapshot_export() -> dict[str, Any]:
                from ..local.portable import PortablePrincipleLibrary

                return PortablePrincipleLibrary(
                    workspace.storage, self.repository
                ).export(workspace.principles_dir)

        self.relations = PrincipleRelationService(
            self.repository,
            snapshot_export=relation_snapshot_export,
        )
        self.local = LocalDiscoveryService(
            workspace.storage,
            self.repository,
            self.search,
            workspace.research,
            local_data_root=workspace.local_data_root,
            principles_export_root=(
                workspace.principles_dir if workspace.layout == "project" else None
            ),
            working_directory_root=workspace.working_directory_root,
            relation_rebuild=self.relations.start_rebuild,
        )
        self.goal_runs = ResearchGoalRunService(
            self.repository, self.local, self.global_cloud
        )
        base_digest = self.content_digest()
        self.scenarios = ScenarioService(self.repository, base_digest)
        self.admin_mode = admin_mode
        self.admin = AdminService(self.repository) if admin_mode else None
        self.admin_campaigns = (
            AdminCampaignService(
                self.repository,
                self.local,
                self.global_cloud,
                workspace.working_directory_root,
            )
            if admin_mode
            else None
        )
        if not admin_mode:
            self.global_cloud.start_background_sync()

    @classmethod
    def open(
        cls,
        workspace: str | Path | None = None,
        *,
        working_directory: str | Path | None = None,
        cloud_root: str | Path | None = None,
        package_library: str | Path | None = None,
    ) -> Principia:
        if workspace is not None and working_directory is not None:
            raise ValueError("choose either workspace or working_directory, not both")
        resolved = (
            Workspace.working_directory(working_directory)
            if working_directory is not None
            else Workspace(workspace or ".")
        )
        if cloud_root is not None and package_library is not None:
            raise ValueError("choose either cloud_root or package_library, not both")
        shared_library = resolve_package_library(
            package_library, discover=cloud_root is None
        )
        isolated_cloud = cloud_root
        if shared_library is None and isolated_cloud is None:
            isolated_cloud = global_cloud_cache_root()
        return cls(
            resolved,
            cloud_root=isolated_cloud,
            package_library=shared_library,
            admin_mode=False,
        )

    def close(self) -> None:
        if self.admin_campaigns is not None:
            self.admin_campaigns.close()
        self.goal_runs.close()
        self.local.close()

    def content_digest(self) -> str:
        active = [
            {
                "area": item["area"],
                "version": item["version"],
                "content_digest": item["content_digest"],
            }
            for item in self.cloud.registry.installed()
            if item["active"]
        ]
        return canonical_sha256(
            {
                "global": sorted(active, key=lambda item: item["area"]),
                "local": self.repository.canonical_content_digest(),
            }
        )

    def open_ui(
        self,
        *,
        port: int = 0,
        browser: bool = True,
    ) -> str:
        from ..api.server import run_server

        return run_server(self, port=port, browser=browser, admin_mode=self.admin_mode)

    def diagnostics(self) -> dict[str, Any]:
        migration = dict(self.workspace.storage.v14_migration)
        if migration.get("backup_path"):
            migration["backup_path"] = Path(str(migration["backup_path"])).name
        return {
            "version": __version__,
            "workspace": {
                "database": self.workspace.db_path.name,
                "layout": self.workspace.layout,
                "directories": (
                    {
                        "workspace": "workspace",
                        "local_data": "local_data",
                        "principles": "workspace/principles",
                    }
                    if self.workspace.layout == "project"
                    else {"workspace": "."}
                ),
                "migration": migration,
                "counts": {**self.workspace.counts(), **self.repository.v14_counts()},
            },
            "cloud": {
                "installed_area_count": len(
                    {item["area"] for item in self.cloud.registry.installed() if item["active"]}
                ),
                "catalog_configured": bool(self.cloud.catalog),
                "shared_package_library": self.package_library_root is not None,
                "global": self.global_cloud.status(),
            },
            "admin_mode": self.admin_mode,
            "demo_mode": os.getenv("PRINCIPIA_DEMO_MODE") == "1",
        }


class AdminWorkspace(Principia):
    @classmethod
    def open(
        cls,
        workspace: str | Path | None = None,
        *,
        working_directory: str | Path | None = None,
        cloud_root: str | Path | None = None,
        package_library: str | Path | None = None,
    ) -> AdminWorkspace:
        if workspace is not None and working_directory is not None:
            raise ValueError("choose either workspace or working_directory, not both")
        resolved = (
            Workspace.working_directory(working_directory)
            if working_directory is not None
            else Workspace(workspace or ".")
        )
        if cloud_root is not None and package_library is not None:
            raise ValueError("choose either cloud_root or package_library, not both")
        shared_library = resolve_package_library(
            package_library, discover=cloud_root is None
        )
        isolated_cloud = cloud_root
        if shared_library is None and isolated_cloud is None:
            isolated_cloud = global_cloud_cache_root()
        return cls(
            resolved,
            cloud_root=isolated_cloud,
            package_library=shared_library,
            admin_mode=True,
        )


PrinciplesCloud = Principia
