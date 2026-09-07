from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from principia import Principia
from principia.api import create_app
from principia.data_discovery.rule_presentation import present_rules, response_title
from principia.data_discovery.service import DataDiscoveryService
from principia.domain import DataFinding, JobRecord


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    app = Principia.open(working_directory=tmp_path / "working", cloud_root=tmp_path / "cloud")
    source = tmp_path / "source"
    source.mkdir()
    app.repository.register_source("src:test", source, "fixture://test", "Measurements")
    home = app.research_sessions.create_data_discovery_home(source_ids=["src:test"], title="Measurements", provider_profile_id="", model="")
    sid = home["session_id"]
    for name in ("one", "two"):
        app.repository.save_job(JobRecord(job_id=f"job:{name}", kind="data_discovery", state="succeeded", stage="synthesize", progress=1))
        app.repository.create_data_study({"study_id": f"study:{name}", "job_id": f"job:{name}", "session_id": sid, "source_ids": ["src:test"], "state": "succeeded"})
    def projection(study_id):
        name = study_id.split(":")[-1]
        return {"study_id": study_id, "records": [{"record_id": f"finding:{name}", "record_kind": "discovery_finding", "category": "observations", "origin": "data_discovery", "payload": {"title": f"Measured {name}"}}], "edges": [], "counts": {"observations": 1}}
    monkeypatch.setattr(app.data_discovery, "workspace_records", projection)
    asgi = create_app(app, test_mode=True)
    client = TestClient(asgi, headers={"X-Principia-Session": asgi.state.session_token})
    try:
        yield app, client, sid
    finally:
        app.close()


def test_manual_context_layout_and_visibility_survive_canonical_reads(workspace):
    app, client, sid = workspace
    endpoint = f"/api/v1/research-sessions/{sid}/workspace?run_id=study:one"
    original = client.get(endpoint).json()
    def patch(operations):
        revision = client.get(endpoint).json()["graph"]["revision"]
        result = client.patch(f"/api/v1/research-sessions/{sid}/graph", json={"expected_revision": revision, "operations": operations})
        assert result.status_code == 200, result.text
    patch([{"action": "add", "principle_id": "principle:user", "payload": {"id": "principle:user", "title": "User context"}, "x": 10, "y": 20}, {"action": "move", "principle_id": "finding:one", "x": 111, "y": -42}, {"action": "viewport", "viewport": {"x": .2, "y": .8, "ratio": 2.4}}, {"action": "theme", "theme": "deep-space"}])
    with app.repository.connect() as conn:
        before = list(conn.iterdump())
    result = client.get(endpoint)
    body = result.json()
    assert {item["principle_id"] for item in body["graph"]["items"]} == {"finding:one", "principle:user"}
    assert body["records"][0] == original["records"][0]
    added = next(item for item in body["records"] if item["record_id"] == "principle:user")
    assert added["origin"] == "user_added"
    assert body["counts"] == {"observations": 1, "global_principles": 1}
    assert body["graph"]["viewport"]["ratio"] == 2.4
    assert body["graph"]["theme"] == "deep-space"
    assert client.get(f"/api/v1/research-sessions/{sid}/graph?run_id=study:one").json() == body["graph"]
    moved = next(item for item in body["graph"]["items"] if item["principle_id"] == "finding:one")
    assert (moved["x"], moved["y"]) == (111, -42)
    assert client.get(endpoint, headers={"If-None-Match": result.headers["etag"]}).status_code == 304
    with app.repository.connect() as conn:
        assert list(conn.iterdump()) == before
    patch([{"action": "remove", "principle_id": "finding:one"}, {"action": "remove", "principle_id": "principle:user"}])
    hidden = client.get(endpoint).json()
    assert hidden["graph"]["items"] == []
    assert hidden["records"] == original["records"]  # Evidence stays in Results.
    patch([{"action": "add", "principle_id": "principle:user", "payload": {"id": "principle:user", "title": "Restored context"}, "x": 30, "y": 40}])
    restored = client.get(endpoint).json()
    assert restored["records"][-1]["payload"]["title"] == "Restored context"
    other = client.get(endpoint.replace("study:one", "study:two")).json()
    assert {item["principle_id"] for item in other["graph"]["items"]} == {"finding:two", "principle:user"}
    assert "finding:one" not in str(other["records"])


def test_graph_revision_is_atomic_and_bad_batches_roll_back(workspace):
    app, client, sid = workspace
    def save(_):
        try:
            app.research_sessions.mutate_graph(sid, [{"action": "theme", "theme": "deep-space"}], expected_revision=0)
            return "saved"
        except ValueError:
            return "conflict"
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(save, range(2))) == ["conflict", "saved"]
    response = client.patch(f"/api/v1/research-sessions/{sid}/graph", json={"expected_revision": 1, "operations": [{"action": "add", "principle_id": "user:rollback", "payload": {"title": "Rollback"}}, {"action": "theme", "theme": "invalid"}]})
    assert response.status_code == 409
    assert app.research_sessions.graph(sid)["revision"] == 1
    assert "user:rollback" not in str(app.research_sessions.graph(sid))


def test_remove_canonical_node_without_prior_layout_persists(workspace):
    app, client, sid = workspace
    app.research_sessions.mutate_graph(sid, [{"action": "remove", "principle_id": "finding:one"}], expected_revision=0)
    result = client.get(f"/api/v1/research-sessions/{sid}/workspace?run_id=study:one").json()
    assert result["graph"]["items"] == []
    assert len(result["records"]) == 1


def test_map_excludes_screened_candidates_but_results_preserves_them(workspace, monkeypatch):
    app, client, sid = workspace
    statuses = ["supported_candidate", "held_back", "inconclusive", "refuted"]
    records = [{"record_id": f"finding:{status}", "record_kind": "discovery_finding",
                "category": "observations", "origin": "data_discovery",
                "payload": {"title": status, "status": status}} for status in statuses]
    monkeypatch.setattr(app.data_discovery, "workspace_records", lambda _: {
        "records": records, "edges": [], "counts": {"observations": 4}})
    with app.repository.connect() as conn:
        before = list(conn.iterdump())
    result = client.get(f"/api/v1/research-sessions/{sid}/workspace?run_id=study:one").json()
    assert result["records"] == records
    assert result["counts"]["observations"] == 4
    assert [item["principle_id"] for item in result["graph"]["items"]] == ["finding:supported_candidate"]
    with app.repository.connect() as conn:
        assert list(conn.iterdump()) == before


def test_rule_titles_describe_ast_not_normalization_and_preserve_recordings():
    x = {"op": "variable", "symbol": "x_0"}
    scale = {"op": "power", "children": [{"op": "parameter", "symbol": "s_0"}, {"op": "constant", "value": -1}]}
    normalized = {"op": "multiply", "children": [x, scale]}
    base = {"title": "Short-horizon fluorescence response", "equation_ast": normalized}
    assert response_title(base) == "Fluorescence: linear response"
    linear_history = {"op": "multiply", "children": [scale, {"op": "add", "children": [x, {"op": "variable", "symbol": "x_1"}]}]}
    assert response_title({**base, "equation_ast": linear_history}) == "Fluorescence: linear response with one-step history"
    cubic = {**base, "equation_ast": {"op": "power", "children": [normalized, {"op": "constant", "value": 3}]}}
    rules = [{**cubic, "rule_id": str(index), "test_ids": [str(index)]} for index in range(2)]
    original = copy.deepcopy(rules)
    output = present_rules(rules, [{"test_id": str(index), "locator": {"relative_path": f"raw/sub-A_ses-day{index}_recording.nwb"}} for index in range(2)])
    assert rules == original
    assert len({rule["title"] for rule in output}) == 2
    assert all("cubic response" in rule["title"].lower() for rule in output)
    assert [rule["equation_ast"] for rule in output] == [rule["equation_ast"] for rule in original]
    assert all(rule["recorded_title"] == base["title"] for rule in output)
    stellar = present_rules(rules, [{"test_id": str(index), "locator": {"relative_path": f"hlsp_tars_tess_ffi_s0096-000000000000000{index + 1}_tess_v01_lc.fits"}} for index in range(2)])
    assert stellar[0]["source_context"] == "TESS target 1, sector 96"
    assert "hlsp_" not in stellar[0]["title"]
    assert stellar[0]["source_paths"][0].endswith(".fits")


def test_blank_data_home_can_add_context_before_first_discovery(tmp_path):
    app = Principia.open(working_directory=tmp_path / "working", cloud_root=tmp_path / "cloud")
    try:
        source = tmp_path / "source"
        source.mkdir()
        app.repository.register_source("src:blank", source, "fixture://blank", "Blank source")
        home = app.research_sessions.create_data_discovery_home(source_ids=["src:blank"], title="Blank source", provider_profile_id="", model="")
        sid = home["session_id"]
        asgi = create_app(app, test_mode=True)
        client = TestClient(asgi, headers={"X-Principia-Session": asgi.state.session_token})
        endpoint = f"/api/v1/research-sessions/{sid}/workspace"
        assert client.get(endpoint).json()["records"] == []
        response = client.patch(f"/api/v1/research-sessions/{sid}/graph", json={"expected_revision": 0, "operations": [{"action": "add", "principle_id": "virtual:context", "origin": "virtual_principle", "payload": {"id": "virtual:context", "title": "Testable hypothesis", "virtual": True}}]})
        assert response.status_code == 200
        result = client.get(endpoint).json()
        assert result["selected_run"] is None
        assert result["records"][0]["origin"] == "user_added"
        assert result["graph"]["items"][0]["origin"] == "virtual_principle"
    finally:
        app.close()


def test_read_only_finding_presentation_retains_persisted_timestamp(monkeypatch):
    finding = DataFinding(finding_id="finding:stable", study_id="study:stable", title="Stable finding", claim="A measured relationship remains stable.", interpretation="Measured response", mechanism="Unknown", status="held_back", updated_at="2026-09-05T00:00:00Z")
    original = finding.model_dump()
    monkeypatch.setattr("principia.data_discovery.service.utc_now", lambda: "2026-09-06T00:00:00Z")
    first = DataDiscoveryService._sanitize_public_finding(finding)
    monkeypatch.setattr("principia.data_discovery.service.utc_now", lambda: "2026-09-07T00:00:00Z")
    second = DataDiscoveryService._sanitize_public_finding(finding)
    assert first == second
    assert first.updated_at == finding.updated_at
    assert finding.model_dump() == original
