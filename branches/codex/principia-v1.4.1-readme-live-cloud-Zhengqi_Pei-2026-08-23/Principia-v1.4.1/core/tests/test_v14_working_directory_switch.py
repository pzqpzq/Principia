from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from principia import Principia
from principia.api import app_for_testing
from principia.domain import JobRecord


def test_library_switches_between_fully_isolated_working_directories(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # Keep this isolation test independent of an adjacent release package library.
    # The upload-ready layout intentionally places principle-packages/ beside core/,
    # and production auto-discovery of that shared library is covered separately.
    monkeypatch.setattr(
        "principia.application.facade.resolve_package_library",
        lambda value, *, discover: None,
    )
    shared_cloud = tmp_path / "application-cloud-cache"
    monkeypatch.setenv("PRINCIPIA_GLOBAL_CLOUD_CACHE", str(shared_cloud))
    first = tmp_path / "first-project"
    second = tmp_path / "empty-project"
    second.mkdir()
    product = Principia.open(working_directory=first)
    product.local.create_managed_source(name="first-only-papers")
    product.local.save_provider_credential("siliconflow", "first-workspace-secret")
    app = app_for_testing(product)
    client = TestClient(app, raise_server_exceptions=False)
    headers = {"X-Principia-Session": app.state.session_token}

    disclosed = client.post(
        "/api/v1/runtime/working-directory/disclosure", headers=headers
    )
    assert disclosed.status_code == 200, disclosed.text
    assert disclosed.headers["cache-control"] == "no-store"
    assert disclosed.json()["working_directory"] == str(first)
    assert disclosed.json()["empty"] is False
    assert client.get("/api/v1/library/summary").json()["source_count"] == 1
    assert client.get("/api/v1/providers").json()["profiles"][0]["configured"] is True

    switched = client.post(
        "/api/v1/runtime/working-directory/switch",
        headers=headers,
        json={"path": str(second)},
    )
    assert switched.status_code == 200, switched.text
    assert switched.json()["switched"] is True
    assert switched.json()["empty"] is True
    assert switched.json()["working_directory"] == str(second)
    assert (second / "local_data").is_dir()
    assert (second / "workspace" / "principles").is_dir()
    assert client.get("/api/v1/library/summary").json()["source_count"] == 0
    assert client.get("/api/v1/providers").json()["profiles"][0]["configured"] is False
    # Public Global snapshots are application-level cache data. Switching a
    # private working directory must preserve the same verified Cloud cache.
    assert app.state.principia.cloud.registry.root == shared_cloud
    assert app.state.principia.global_cloud.root == shared_cloud / "global-v1"

    returned = client.post(
        "/api/v1/runtime/working-directory/switch",
        headers=headers,
        json={"path": str(first)},
    )
    assert returned.status_code == 200, returned.text
    assert returned.json()["empty"] is False
    assert client.get("/api/v1/library/summary").json()["source_count"] == 1
    assert client.get("/api/v1/providers").json()["profiles"][0]["configured"] is True


def test_working_directory_switch_preserves_shared_package_library(tmp_path: Path) -> None:
    current = tmp_path / "current"
    target = tmp_path / "target"
    target.mkdir()
    package_library = tmp_path / "principle-packages"
    package_library.mkdir()
    product = Principia.open(
        working_directory=current,
        package_library=package_library,
    )
    app = app_for_testing(product)
    client = TestClient(app, raise_server_exceptions=False)
    headers = {"X-Principia-Session": app.state.session_token}

    disclosed = client.post(
        "/api/v1/runtime/working-directory/disclosure", headers=headers
    )
    assert disclosed.status_code == 200
    assert disclosed.json()["package_library"] == str(package_library)

    switched = client.post(
        "/api/v1/runtime/working-directory/switch",
        headers=headers,
        json={"path": str(target)},
    )
    assert switched.status_code == 200, switched.text
    assert switched.json()["package_library"] == str(package_library)
    assert app.state.principia.package_library_root == package_library
    assert app.state.principia.cloud.registry.root == package_library / ".principia"
    assert switched.json()["empty"] is True


def test_working_directory_switch_refuses_active_jobs(tmp_path: Path) -> None:
    current = tmp_path / "current"
    target = tmp_path / "target"
    target.mkdir()
    product = Principia.open(working_directory=current)
    product.repository.save_job(
        JobRecord(
            job_id="job:active-switch-guard",
            kind="literature_search",
            state="running",
            stage="Searching sources",
            progress=0.25,
        )
    )
    app = app_for_testing(product)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        "/api/v1/runtime/working-directory/switch",
        headers={"X-Principia-Session": app.state.session_token},
        json={"path": str(target)},
    )
    assert response.status_code == 409, response.text
    assert "active operations" in response.json()["error"]["message"]
    assert app.state.principia.workspace.working_directory_root == current
    assert not (target / "workspace").exists()
