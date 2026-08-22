from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from principia import Principia
from principia.api import app_for_testing
from principia.domain import (
    CandidatePrinciple,
    JobRecord,
    PrincipleKind,
    PrincipleScope,
)
from principia.providers import ProviderRequestError


def _client(tmp_path: Path) -> tuple[TestClient, str]:
    product = Principia.open(tmp_path / "workspace", cloud_root=tmp_path / "cloud")
    app = app_for_testing(product)
    return TestClient(app, raise_server_exceptions=False), app.state.session_token


def test_provider_failures_retain_actionable_message_in_api(tmp_path: Path, monkeypatch) -> None:
    product = Principia.open(tmp_path / "workspace", cloud_root=tmp_path / "cloud")
    app = app_for_testing(product)
    client = TestClient(app, raise_server_exceptions=False)

    def rejected(**_kwargs: object) -> dict[str, object]:
        raise ProviderRequestError(
            "SiliconFlow rejected the saved credential; enter and verify the key again.",
            category="authentication",
            retryable=False,
            status_code=401,
        )

    monkeypatch.setattr(product.virtual_principles, "generate", rejected)
    response = client.post(
        "/api/v1/principles/virtual-principles/generate",
        headers={"X-Principia-Session": app.state.session_token},
        json={
            "principle_ids": ["prn:fixture:one", "prn:fixture:two"],
            "provider_profile_id": "siliconflow",
            "model": "fixture-model",
            "egress_confirmed": True,
            "requested_count": 2,
            "research_direction": "",
        },
    )

    assert response.status_code == 401
    assert response.json()["error"]["category"] == "authentication"
    assert "verify the key again" in response.json()["error"]["message"]


def test_runtime_is_secretless_and_mutations_require_session(tmp_path: Path) -> None:
    client, token = _client(tmp_path)
    runtime = client.get("/api/v1/runtime")
    assert runtime.status_code == 200
    assert "session" not in runtime.text.lower()
    denied = client.post("/api/v1/scenarios", json={"name": "Denied"})
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "invalid_session"
    created = client.post(
        "/api/v1/scenarios",
        headers={"X-Principia-Session": token},
        json={"name": "Accepted"},
    )
    assert created.status_code == 200
    assert created.json()["scenario_id"].startswith("scn:")
    assert created.headers["X-Principia-Request-ID"]


def test_library_and_principle_management_are_reversible(tmp_path: Path) -> None:
    product = Principia.open(tmp_path / "workspace", cloud_root=tmp_path / "cloud")
    source = product.local.create_managed_source(name="Original folder")
    source_id = source["source_id"]
    candidate = CandidatePrinciple(
        candidate_id="cand:managed",
        area="machine-intelligence",
        title="Original display title",
        claim="Distinct verification signals reduce correlated selection errors.",
        kind=PrincipleKind.EMPIRICAL,
        scope=PrincipleScope(statement="Distinct verifier failure modes."),
    )
    product.repository.save_candidate(
        candidate, eligibility_status="eligible", quality_state="eligible"
    )
    app = app_for_testing(product)
    client = TestClient(app, raise_server_exceptions=False)
    headers = {"X-Principia-Session": app.state.session_token}

    renamed = client.patch(
        f"/api/v1/library/collections/source/{source_id}",
        headers=headers,
        json={"title": "Renamed folder"},
    )
    assert renamed.status_code == 200
    assert product.repository.source(source_id)["display_name"] == "Renamed folder"
    disconnected = client.delete(f"/api/v1/library/collections/source/{source_id}", headers=headers)
    assert disconnected.status_code == 200
    assert product.repository.source(source_id)["status"] == "removed"
    restored = client.post(
        f"/api/v1/library/collections/source/{source_id}/restore", headers=headers
    )
    assert restored.status_code == 200
    assert product.repository.source(source_id)["status"] == "ready"

    edited = client.patch(
        "/api/v1/local/candidates/cand:managed",
        headers=headers,
        json={"title": "Readable managed Principle"},
    )
    assert edited.status_code == 200
    archived = client.delete("/api/v1/local/candidates/cand:managed", headers=headers)
    assert archived.status_code == 200
    assert (
        product.repository.candidate_detail("cand:managed")["local_metadata"]["quality_state"]
        == "archived"
    )
    restored_principle = client.post(
        "/api/v1/local/candidates/cand:managed/restore", headers=headers
    )
    assert restored_principle.status_code == 200
    detail = product.repository.candidate_detail("cand:managed")
    assert detail["title"] == "Readable managed Principle"
    assert detail["local_metadata"]["quality_state"] == "eligible"


def test_origin_body_limit_and_privileged_route_isolation(tmp_path: Path) -> None:
    client, token = _client(tmp_path)
    bad_origin = client.get("/api/v1/health", headers={"Origin": "https://attacker.invalid"})
    assert bad_origin.status_code == 403
    oversized = client.post(
        "/api/v1/local/sources",
        headers={"X-Principia-Session": token, "content-type": "application/json"},
        content=json.dumps({"path": "x" * (1024 * 1024 + 1)}),
    )
    assert oversized.status_code == 413
    privileged = client.get("/" + "ad" + "min")
    assert privileged.status_code == 404
    assert privileged.json()["error"]["code"] == "not_found"


def test_legacy_discovery_never_uses_a_client_selected_provider_origin(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("PRINCIPIA_LLM_API_KEY", "server-secret-fixture")
    monkeypatch.setenv("PRINCIPIA_LLM_BASE_URL", "https://api.siliconflow.com/v1")
    product = Principia.open(tmp_path / "workspace", cloud_root=tmp_path / "cloud")
    app = app_for_testing(product)
    client = TestClient(app, raise_server_exceptions=False)
    captured: dict[str, object] = {}

    def fake_start(**kwargs: object) -> JobRecord:
        captured.update(kwargs)
        return JobRecord(job_id="job:server-owned-origin", kind="local_extraction")

    monkeypatch.setattr(product.local, "start", fake_start)
    response = client.post(
        "/api/v1/local/discoveries",
        headers={"X-Principia-Session": app.state.session_token},
        json={
            "source_id": "src:fixture",
            "goal": "Test the server-owned provider origin boundary",
            "area": "machine-intelligence",
            "policy": {
                "mode": "remote",
                "provider": "siliconflow",
                "model": "deepseek-ai/DeepSeek-V4-Flash",
                "base_url": "https://attacker.invalid/v1",
                "remote_egress_confirmed": True,
            },
        },
    )

    assert response.status_code == 200, response.text
    assert captured["policy"].base_url == "https://api.siliconflow.com/v1"
    assert "attacker.invalid" not in response.text
    assert "server-secret-fixture" not in response.text


def test_workspace_provider_credential_is_private_persistent_and_never_in_sqlite(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("PRINCIPIA_LLM_API_KEY", raising=False)
    monkeypatch.delenv("SILICONFLOW_API_KEY", raising=False)
    workspace = tmp_path / "workspace"
    product = Principia.open(workspace, cloud_root=tmp_path / "cloud")
    app = app_for_testing(product)
    client = TestClient(app, raise_server_exceptions=False)
    # Assemble the credential-shaped fixture at runtime so a fail-closed source
    # archive scan never has to exempt a literal key-like string.
    secret = "".join(("s", "k", "-", "private-workspace-fixture-value"))

    saved = client.put(
        "/api/v1/provider-profiles/siliconflow/credential",
        headers={"X-Principia-Session": app.state.session_token},
        json={"api_key": secret},
    )
    assert saved.status_code == 200, saved.text
    assert secret not in saved.text
    assert saved.json()["credential_source"] == "workspace"
    path = workspace / ".principia" / "secrets" / "provider_credentials.json"
    assert path.is_file()
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600
        assert path.parent.stat().st_mode & 0o777 == 0o700

    reopened = Principia.open(workspace, cloud_root=tmp_path / "cloud")
    assert reopened.local.provider_profile().credential_source == "workspace"
    assert reopened.local.credentials.api_key("siliconflow") == secret
    with sqlite3.connect(workspace / ".principia" / "principia.sqlite") as conn:
        dump = "\n".join(conn.iterdump())
    assert secret not in dump

    monkeypatch.setenv("PRINCIPIA_LLM_API_KEY", "environment-fallback-fixture")
    deleted = client.delete(
        "/api/v1/provider-profiles/siliconflow/credential",
        headers={"X-Principia-Session": app.state.session_token},
    )
    assert deleted.status_code == 200
    assert deleted.json()["credential_source"] == "environment"
    assert secret not in deleted.text


def test_validation_errors_do_not_echo_provider_credentials(tmp_path: Path) -> None:
    client, token = _client(tmp_path)
    secret = "short-secret-that-must-not-echo"
    response = client.put(
        "/api/v1/provider-profiles/siliconflow/credential",
        headers={"X-Principia-Session": token},
        json={"api_key": secret * 500},
    )
    assert response.status_code == 422
    assert secret not in response.text
    assert "input" not in response.json()["error"]["details"]["errors"][0]


def test_local_source_response_and_diagnostics_do_not_expose_absolute_paths(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "private-documents"
    folder.mkdir()
    client, token = _client(tmp_path)
    response = client.post(
        "/api/v1/local/sources",
        headers={"X-Principia-Session": token},
        json={"path": str(folder)},
    )
    assert response.status_code == 200
    assert str(folder) not in response.text
    diagnostics = client.get("/api/v1/diagnostics")
    assert diagnostics.status_code == 200
    assert str(tmp_path) not in diagnostics.text

    disclosed = client.post(
        "/api/v1/local/sources/location-disclosures",
        headers={"X-Principia-Session": token},
        json={"source_ids": [response.json()["source_id"]]},
    )
    assert disclosed.status_code == 200, disclosed.text
    assert disclosed.headers["Cache-Control"] == "no-store"
    assert disclosed.json()["items"] == [
        {
            "source_id": response.json()["source_id"],
            "absolute_path": str(folder),
            "available": True,
            "readable": True,
            "writable": True,
        }
    ]


def test_openapi_contains_bounded_graph_and_no_privileged_routes(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    schema = client.get("/api/v1/openapi.json").json()
    assert "/api/v1/graph/neighborhood" in schema["paths"]
    privileged_prefix = "/api/v1/" + "ad" + "min"
    assert not any(path.startswith(privileged_prefix) for path in schema["paths"])
