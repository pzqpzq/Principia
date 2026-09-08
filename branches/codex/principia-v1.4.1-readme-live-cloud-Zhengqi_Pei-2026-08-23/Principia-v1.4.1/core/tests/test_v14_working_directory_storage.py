from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from fastapi.testclient import TestClient

from principia.api import app_for_testing
from principia.application import Principia
from principia.domain import CandidatePrinciple, PrincipleKind, PrincipleScope
from principia.local import PortablePrincipleLibrary
from principia.models import WorkItem, utc_now


def test_working_directory_separates_raw_data_and_durable_principles(tmp_path: Path) -> None:
    working_directory = tmp_path / "research-project"
    product = Principia.open(working_directory=working_directory)

    assert product.workspace.path == working_directory / "workspace"
    assert product.workspace.local_data_root == working_directory / "local_data"
    assert (working_directory / ".principia-working-directory.json").is_file()
    layout = json.loads(
        (working_directory / ".principia-working-directory.json").read_text(encoding="utf-8")
    )
    assert layout["principles"] == "workspace/principles"

    source = product.local.create_managed_source(name="test-ASD")
    source_root = Path(source["created_location"])
    assert source_root == working_directory / "local_data" / "test-ASD"
    assert source["display_location"] == "local_data/test-ASD"
    raw_text = "Private source text that must remain outside the Principles snapshot."
    (source_root / "paper.txt").write_text(raw_text, encoding="utf-8")

    work = WorkItem(
        id="work:durable",
        title="Public evidence record",
        doi="10.0000/durable.fixture",
        source="fixture",
    )
    product.workspace.storage.save_work(work)
    candidate = CandidatePrinciple(
        candidate_id="cand:durable",
        area="uncategorized",
        title="Evidence persistence principle",
        claim="Derived Principles remain available independently of private raw files.",
        kind=PrincipleKind.EMPIRICAL,
        scope=PrincipleScope(statement="After a completed extraction"),
        falsifier="Removing a raw folder removes the persisted Principle.",
    )
    product.repository.save_candidate(
        candidate,
        source_id=source["source_id"],
        eligibility_status="eligible",
        quality_state="eligible",
        scientific_contract_version="scientific-principle-v2",
        quality_gate_version="quality-v2",
    )
    product.repository.save_candidate_evidence(
        evidence_id="evidence:durable",
        candidate_id=candidate.candidate_id,
        work_id=work.id,
        excerpt_sha256="a" * 64,
        locator={"quotation": raw_text, "section": "results"},
    )
    snapshot = PortablePrincipleLibrary(
        product.workspace.storage, product.repository
    ).export(product.workspace.principles_dir)
    assert snapshot["principle_count"] == 1
    assert raw_text not in (product.workspace.principles_dir / "principles.jsonl").read_text(
        encoding="utf-8"
    )

    shutil.rmtree(product.workspace.local_data_root)
    reopened = Principia.open(working_directory=working_directory)
    page = reopened.explorer.browse(scope="local", limit=24)
    assert page["total"] == 1
    assert page["items"][0]["id"] == candidate.candidate_id
    detail = reopened.repository.candidate_detail(candidate.candidate_id)
    assert detail is not None
    assert detail["evidence"][0]["source_url"] == (
        "https://doi.org/10.0000/durable.fixture"
    )
    disclosure = reopened.local.source_location_disclosures([source["source_id"]])[0]
    assert disclosure["available"] is False
    assert reopened.workspace.local_data_root.is_dir()


def test_managed_folder_preserves_safe_underscores_and_excludes_container_metadata(
    tmp_path: Path,
) -> None:
    product = Principia.open(working_directory=tmp_path / "project")
    source = product.local.create_managed_source(name="test_hilbert")

    root = Path(source["created_location"])
    assert root.name == "test_hilbert"
    assert (root / "README.txt").is_file()
    assert (root / "manifest.json").is_file()

    indexed = product.local.index_source(source["source_id"])
    assert indexed.state == "succeeded", indexed.error
    assert indexed.result is not None
    assert indexed.result["document_count"] == 0
    inventory = product.local.source_documents(source["source_id"], limit=100)
    assert inventory == {"items": [], "total": 0, "next_cursor": None}
    detail = product.local.source_detail(source["source_id"])
    assert detail["document_count"] == 0
    assert detail["extractable_count"] == 0


def test_working_directory_disclosure_and_search_acquisition_use_visible_siblings(
    tmp_path: Path,
) -> None:
    root = tmp_path / "user-selected-directory"
    product = Principia.open(working_directory=root)
    app = app_for_testing(product)
    client = TestClient(app, raise_server_exceptions=False)
    headers = {"X-Principia-Session": app.state.session_token}

    assert (root / "local_data").is_dir()
    assert (root / "workspace" / "principles").is_dir()
    disclosure = client.post(
        "/api/v1/local/storage-layout/disclosure", headers=headers
    )
    assert disclosure.status_code == 200, disclosure.text
    assert disclosure.headers["cache-control"] == "no-store"
    assert disclosure.json() == {
        "layout": "working_directory",
        "working_directory": str(root),
        "workspace": str(root / "workspace"),
        "local_data": str(root / "local_data"),
        "principles": str(root / "workspace" / "principles"),
        "raw_data_removable": True,
    }
    try:
        product.local.start_literature_acquisition(
            search_id="search:missing",
            folder_name="must-not-be-created",
            work_ids=["work:missing"],
        )
    except KeyError:
        pass
    else:
        raise AssertionError("an unknown search must fail before folder creation")
    assert not (root / "local_data" / "must-not-be-created").exists()

    work = WorkItem(
        id="work:managed-search-folder",
        title="Managed literature input",
        abstract="A permitted abstract supplies a bounded scientific input.",
        source="fixture",
    )
    product.workspace.storage.save_work(work)
    now = utc_now()
    product.repository.save_literature_search(
        {
            "search_id": "search:managed-folder",
            "query": "Which bounded scientific inputs are supported?",
            "goal": "Which bounded scientific inputs are supported?",
            "area": "",
            "target_count": 1,
            "state": "ready",
            "sources": ["fixture"],
            "unavailable_sources": [],
            "results": [{"work_id": work.id, "title": work.title}],
            "selected_work_ids": [work.id],
            "alternate_work_ids": [],
            "pool_count": 1,
            "selection_finalized": True,
            "created_at": now,
            "updated_at": now,
        },
        create_goal=False,
    )
    response = client.post(
        "/api/v1/local/literature-searches/search:managed-folder/acquisitions",
        headers=headers,
        json={"folder_name": "bounded-inputs", "work_ids": [work.id]},
    )
    assert response.status_code == 200, response.text
    job = response.json()
    source_id = job["checkpoint"]["source_id"]
    deadline = time.monotonic() + 10
    while job["state"] not in {"succeeded", "failed"} and time.monotonic() < deadline:
        time.sleep(0.02)
        job = client.get(f"/api/v1/jobs/{job['job_id']}").json()
    assert job["state"] == "succeeded", job
    source_root = product.repository.source_root(source_id)
    assert source_root == root / "local_data" / "bounded-inputs"
    assert list(source_root.glob("papers/*/abstract.txt"))
    assert job["result"]["candidate_count"] == 0


def test_working_directory_rejects_mixed_workspace_arguments(tmp_path: Path) -> None:
    try:
        Principia.open(tmp_path / "workspace", working_directory=tmp_path / "project")
    except ValueError as exc:
        assert "either workspace or working_directory" in str(exc)
    else:
        raise AssertionError("mixed storage roots must fail closed")


def test_moving_working_directory_rebases_only_managed_local_data(tmp_path: Path) -> None:
    original = tmp_path / "original"
    product = Principia.open(working_directory=original)
    managed = product.local.create_managed_source(name="portable-source")
    source_id = managed["source_id"]
    external = tmp_path / "external-source"
    external.mkdir()
    connected = product.local.register_source(external)

    moved = tmp_path / "moved"
    shutil.move(original, moved)
    reopened = Principia.open(working_directory=moved)

    assert reopened.repository.source_root(source_id) == (
        moved / "local_data" / "portable-source"
    )
    assert reopened.repository.source_root(connected["source_id"]) == external
    assert reopened.local.root_reconciliation_receipt == {
        "rebased_sources": 1,
        "rebased_acquisitions": 0,
    }


def test_reconnecting_the_same_folder_reuses_its_authoritative_source(tmp_path: Path) -> None:
    product = Principia.open(working_directory=tmp_path / "project")
    managed = product.local.create_managed_source(name="existing-literature")
    connected = product.local.register_source(Path(managed["created_location"]))

    assert connected["source_id"] == managed["source_id"]
    assert len(product.local.list_sources()) == 1


def test_reconnecting_managed_raw_data_restores_work_membership_without_sidecar_papers(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    product = Principia.open(working_directory=root)
    work = WorkItem(id="work:canonical", title="Canonical paper", source="fixture")
    product.workspace.storage.save_work(work)
    candidate = CandidatePrinciple(
        candidate_id="cand:canonical",
        area="uncategorized",
        title="Canonical evidence principle",
        claim="Canonical Work identity reconnects derived evidence to raw source material.",
        kind=PrincipleKind.EMPIRICAL,
        scope=PrincipleScope(statement="A managed source manifest is present"),
        falsifier="The raw document reconnects as an unrelated Work.",
    )
    product.repository.save_candidate(
        candidate,
        eligibility_status="eligible",
        quality_state="eligible",
        scientific_contract_version="scientific-principle-v2",
        quality_gate_version="quality-v2",
    )
    product.repository.save_candidate_evidence(
        evidence_id="evidence:canonical",
        candidate_id=candidate.candidate_id,
        work_id=work.id,
        excerpt_sha256="b" * 64,
    )
    folder = root / "local_data" / "reconnected"
    document = folder / "papers" / "canonical"
    document.mkdir(parents=True)
    raw = document / "full-text.txt"
    raw.write_text(
        "Canonical Work identity reconnects evidence to raw source material.",
        encoding="utf-8",
    )
    (document / "normalized.txt").write_text(raw.read_text(encoding="utf-8"), encoding="utf-8")
    (document / "metadata.json").write_text("{}\n", encoding="utf-8")
    (folder / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "principia-local-source-v1",
                "documents": [
                    {
                        "work_id": work.id,
                        "portable_relative_uri": "papers/canonical/full-text.txt",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    source = product.local.register_source(folder)
    indexed = product.local.index_source(source["source_id"])
    assert indexed.state == "succeeded", indexed.error
    documents = product.local.source_documents(source["source_id"], limit=100)
    assert documents["total"] == 1
    assert documents["items"][0]["work_id"] == work.id
    assert indexed.result is not None
    assert indexed.result["linked_principle_count"] == 1
    assert indexed.result["isolated_sidecar_count"] == 2
    assert not (document / "normalized.txt").exists()
    assert not (document / "metadata.json").exists()
    cache_files = sorted((root / "workspace" / "source_cache").rglob("*.*"))
    assert {item.name for item in cache_files if item.is_file()} == {
        "metadata.json",
        "normalized.txt",
    }
    source_detail = product.local.source_detail(source["source_id"])
    assert source_detail["full_text_count"] == 1
    assert source_detail["text_full_text_count"] == 1
    assert source_detail["pdf_count"] == 0
    assert source_detail["abstract_only_count"] == 0
    detail = product.repository.candidate_detail(candidate.candidate_id)
    assert detail is not None
    assert detail["local_metadata"]["source_ids"] == [source["source_id"]]
