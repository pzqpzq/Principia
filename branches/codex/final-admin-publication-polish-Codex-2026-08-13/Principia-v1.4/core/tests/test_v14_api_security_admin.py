from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from principia import AdminWorkspace, Principia
from principia.api import app_for_testing
from principia.domain import (
    CandidatePrinciple,
    GenerationTrace,
    JobRecord,
    PrincipleCapsule,
    PrincipleKind,
    PrincipleMaturity,
    PrincipleScope,
    QualityAssessment,
    TraceOperation,
    WorkReference,
)


def _client(tmp_path: Path, *, admin: bool = False) -> tuple[TestClient, str]:
    product = (
        AdminWorkspace.open(tmp_path / "workspace", cloud_root=tmp_path / "cloud")
        if admin
        else Principia.open(tmp_path / "workspace", cloud_root=tmp_path / "cloud")
    )
    app = app_for_testing(product, admin_mode=admin)
    return TestClient(app, raise_server_exceptions=False), app.state.session_token


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
    disconnected = client.delete(
        f"/api/v1/library/collections/source/{source_id}", headers=headers
    )
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
    archived = client.delete(
        "/api/v1/local/candidates/cand:managed", headers=headers
    )
    assert archived.status_code == 200
    assert product.repository.candidate_detail("cand:managed")["local_metadata"]["quality_state"] == "archived"
    restored_principle = client.post(
        "/api/v1/local/candidates/cand:managed/restore", headers=headers
    )
    assert restored_principle.status_code == 200
    detail = product.repository.candidate_detail("cand:managed")
    assert detail["title"] == "Readable managed Principle"
    assert detail["local_metadata"]["quality_state"] == "eligible"


def test_origin_body_limit_and_admin_isolation(tmp_path: Path) -> None:
    client, token = _client(tmp_path)
    bad_origin = client.get(
        "/api/v1/health", headers={"Origin": "https://attacker.invalid"}
    )
    assert bad_origin.status_code == 403
    oversized = client.post(
        "/api/v1/local/sources",
        headers={"X-Principia-Session": token, "content-type": "application/json"},
        content=json.dumps({"path": "x" * (1024 * 1024 + 1)}),
    )
    assert oversized.status_code == 413
    admin = client.get("/admin")
    assert admin.status_code == 404
    assert admin.json()["error"]["code"] == "not_found"


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


def test_admin_harvest_queue_exists_only_in_admin_runtime(tmp_path: Path) -> None:
    ordinary, ordinary_token = _client(tmp_path / "ordinary")
    denied = ordinary.post(
        "/api/v1/admin/harvest",
        headers={"X-Principia-Session": ordinary_token},
        json={},
    )
    assert denied.status_code == 404

    admin, token = _client(tmp_path / "admin", admin=True)
    candidate = CandidatePrinciple(
        candidate_id="cand:admin-fixture",
        area="demo-admin",
        title="Admin fixture candidate",
        claim="A bounded admin fixture claim.",
        kind=PrincipleKind.HYPOTHESIS,
        scope=PrincipleScope(statement="Synthetic public fixture"),
    )
    harvested = admin.post(
        "/api/v1/admin/harvest",
        headers={"X-Principia-Session": token},
        json={"candidate": candidate.model_dump(mode="json")},
    )
    assert harvested.status_code == 200, harvested.text
    queue = admin.get("/api/v1/admin/review")
    assert queue.status_code == 200
    assert queue.json()["items"][0]["candidate"]["candidate_id"] == candidate.candidate_id
    runtime = admin.get("/api/v1/admin/runtime").json()
    assert runtime["publication_default"] == "dry_run"
    assert runtime["github_write_enabled"] is False


def test_openapi_contains_bounded_graph_and_no_admin_when_ordinary(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    schema = client.get("/api/v1/openapi.json").json()
    assert "/api/v1/graph/neighborhood" in schema["paths"]
    assert not any(path.startswith("/api/v1/admin") for path in schema["paths"])


def test_admin_typed_capsule_changeset_and_dry_run(tmp_path: Path) -> None:
    admin, token = _client(tmp_path, admin=True)
    capsule = PrincipleCapsule(
        principle_id="prn:demo-admin:00000000000000000000000001",
        area="demo-admin",
        version=1,
        title="Reviewed fixture",
        claim="A reviewed synthetic fixture preserves a bounded checksum.",
        kind=PrincipleKind.EMPIRICAL,
        maturity=PrincipleMaturity.SUPPORTED,
        scope=PrincipleScope(statement="Synthetic acceptance only"),
        quality=QualityAssessment(
            grade="B",
            validity=0.8,
            reproducibility=0.8,
            evidence_strength=0.8,
            generality=0.8,
            usefulness=0.8,
            assessed_by="test-reviewer",
        ),
        falsifier="The fixed input produces a different checksum.",
        source_references=[WorkReference(work_id="fixture:1", title="Public fixture")],
        generation_trace=[
            GenerationTrace(
                event_id="evt:review:1",
                operation=TraceOperation.PROMOTE,
                actor="test-reviewer",
                input_sha256="0" * 64,
                output_sha256="1" * 64,
            )
        ],
        source_count=1,
        relation_count=0,
        trace_count=1,
    )
    built = admin.post(
        "/api/v1/admin/changesets",
        headers={"X-Principia-Session": token},
        json={
            "area": "demo-admin",
            "base_package_version": "0.0.0",
            "proposed_package_version": "1.0.0",
            "expected_content_digest": "0" * 64,
            "goal": "Typed API regression",
            "capsules": [capsule.model_dump(mode="json")],
        },
    )
    assert built.status_code == 200, built.text
    changeset_id = built.json()["changeset_id"]
    dry_run = admin.post(
        f"/api/v1/admin/changesets/{changeset_id}/publish",
        headers={"X-Principia-Session": token},
        json={"mode": "dry_run", "output": None, "confirmation": ""},
    )
    assert dry_run.status_code == 200, dry_run.text
    assert dry_run.json()["external_write_performed"] is False
