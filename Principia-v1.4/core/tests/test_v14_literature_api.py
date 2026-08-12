from __future__ import annotations

import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient

from principia import Principia
from principia.api import app_for_testing
from principia.domain import CandidatePrinciple, PrincipleKind, PrincipleScope
from principia.local.literature import ScholarlySearchService
from principia.models import WorkItem, utc_now


def _product_client(tmp_path: Path) -> tuple[Principia, TestClient, str]:
    product = Principia.open(tmp_path / "workspace", cloud_root=tmp_path / "cloud")
    app = app_for_testing(product)
    return product, TestClient(app, raise_server_exceptions=False), app.state.session_token


def test_search_projection_prefers_publication_venue_over_repository_copy() -> None:
    conference = WorkItem(
        id="work:conference-copy",
        title="Verified inference-time search",
        abstract="Verification improves bounded inference-time search.",
        source="semantic_scholar",
        venue="International Conference on Machine Learning",
        arxiv_id="2601.12345",
        metadata={"type": "preprint", "is_preprint": True},
    )
    projected = ScholarlySearchService._work_projection(conference, rank=1)
    assert projected["publication_status"] == "published"
    assert projected["publication_venue"] == "International Conference on Machine Learning"

    repository = conference.model_copy(
        update={
            "id": "work:repository-only",
            "venue": "arXiv.org",
        }
    )
    projected_repository = ScholarlySearchService._work_projection(repository, rank=2)
    assert projected_repository["publication_status"] == "preprint"
    assert projected_repository["publication_venue"] == ""

    publisher = conference.model_copy(
        update={
            "id": "work:publisher-name",
            "source": "crossref",
            "venue": "Elsevier BV",
            "metadata": {"type": "posted-content"},
        }
    )
    projected_publisher = ScholarlySearchService._work_projection(publisher, rank=3)
    assert projected_publisher["publication_status"] == "preprint"
    assert projected_publisher["publication_venue"] == ""


def test_saved_search_refreshes_venue_labels_without_rewriting_results(tmp_path: Path) -> None:
    product, _, _ = _product_client(tmp_path)
    work = WorkItem(
        id="work:saved-venue",
        title="Reusable verification",
        abstract="Verification reduces unsupported outputs under reported conditions.",
        source="semantic_scholar",
        venue="International Conference on Machine Learning",
        metadata={"type": "preprint", "is_preprint": True},
    )
    product.workspace.storage.save_work(work)
    original = {
        "search_id": "search:saved-venue",
        "goal": "Which verification mechanisms reduce unsupported outputs?",
        "area": "",
        "target_count": 20,
        "state": "ready",
        "results": [
            {
                "work_id": work.id,
                "rank": 1,
                "title": work.title,
                "publication_status": "repository_record",
                "publication_venue": "",
            }
        ],
        "selected_work_ids": [work.id],
        "alternate_work_ids": [],
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    product.repository.save_literature_search(original, create_goal=False)

    refreshed = product.local.literature_search("search:saved-venue")
    assert refreshed is not None
    assert refreshed["results"][0]["publication_status"] == "published"
    assert refreshed["results"][0]["publication_venue"] == (
        "International Conference on Machine Learning"
    )
    assert product.repository.literature_search("search:saved-venue") == {
        **original,
        "goal_id": "",
        "source_id": "",
    }


def test_editing_literature_selection_does_not_create_research_goal(tmp_path: Path) -> None:
    product, _, _ = _product_client(tmp_path)
    work = WorkItem(
        id="work:metadata-only-selection",
        title="Metadata selection remains separate from extraction focus",
        abstract="A complete abstract makes this paper selectable without creating a Goal.",
        source="fixture",
    )
    product.workspace.storage.save_work(work)
    now = utc_now()
    product.repository.save_literature_search(
        {
            "search_id": "search:metadata-only-selection",
            "goal": "Which metadata selections remain independent from extraction focus?",
            "area": "",
            "target_count": 1,
            "state": "ready",
            "results": [{"work_id": work.id, "title": work.title, "abstract": work.abstract}],
            "selected_work_ids": [work.id],
            "alternate_work_ids": [],
            "created_at": now,
            "updated_at": now,
        },
        create_goal=False,
    )

    updated = product.local.update_literature_selection("search:metadata-only-selection", [work.id])

    assert updated["selected_work_ids"] == [work.id]
    with product.repository.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM local_research_goals").fetchone()[0] == 0


def test_candidate_browse_overview_and_diagnostics_are_populated(tmp_path: Path) -> None:
    product, client, token = _product_client(tmp_path)
    for index in range(125):
        product.repository.save_candidate(
            CandidatePrinciple(
                candidate_id=f"cand:api:{index:03d}",
                area="machine-intelligence",
                title=f"API candidate {index}",
                claim=f"A grounded local API candidate claim with distinct mechanism alpha {index}.",
                kind=PrincipleKind.EMPIRICAL,
                scope=PrincipleScope(statement="API literature fixture"),
            ),
            discovery_job_id="job:api",
            scientific_contract_version="scientific-principle-v2",
            quality_gate_version="quality-v2",
            quality_state="eligible",
        )
    first = client.get("/api/v1/local/candidates?limit=100")
    assert first.status_code == 200, first.text
    assert len(first.json()["items"]) == 100
    second = client.get(
        "/api/v1/local/candidates",
        params={"limit": 100, "cursor": first.json()["next_cursor"]},
    )
    assert len(second.json()["items"]) == 25
    overview = client.get("/api/v1/graph/overview?scope=local&limit=60")
    assert overview.status_code == 200
    assert len(overview.json()["nodes"]) == 60
    assert overview.json()["total_candidates"] == 125
    diagnostics = client.get("/api/v1/diagnostics").json()
    assert diagnostics["workspace"]["counts"]["local_candidates"] == 125

    candidate_id = "cand:api:000"
    suggested = client.post(
        f"/api/v1/local/candidates/{candidate_id}/area-suggestions",
        headers={"X-Principia-Session": token},
        json={"area": "machine-intelligence", "rationale": "User organization"},
    )
    assert suggested.status_code == 200, suggested.text
    accepted = client.post(
        f"/api/v1/local/candidates/{candidate_id}/area-suggestions/machine-intelligence/accept",
        headers={"X-Principia-Session": token},
    )
    assert accepted.json()["state"] == "confirmed"
    edited = client.patch(
        f"/api/v1/local/candidates/{candidate_id}/area-suggestions/machine-intelligence",
        headers={"X-Principia-Session": token},
        json={"new_area": "ai-systems", "rationale": "Narrower organization"},
    )
    assert edited.json()["area"] == "ai-systems"
    detail = client.get(f"/api/v1/local/candidates/{candidate_id}").json()
    states = {(item["area"], item["state"]) for item in detail["area_suggestions"]}
    assert states == {("machine-intelligence", "rejected"), ("ai-systems", "suggested")}


def test_literature_selection_no_llm_discovery_and_job_events(tmp_path: Path) -> None:
    product, client, token = _product_client(tmp_path)
    work = WorkItem(
        id="work:api-literature",
        title="Public abstract fixture",
        abstract="A permitted public abstract describes a bounded scientific mechanism.",
    )
    product.workspace.storage.save_work(work)
    now = utc_now()
    product.repository.save_literature_search(
        {
            "search_id": "search:api-literature",
            "goal": "Which bounded mechanisms are supported by this public abstract?",
            "area": "machine-intelligence",
            "target_count": 1,
            "state": "ready",
            "sources": ["fixture"],
            "unavailable_sources": [],
            "results": [{"work_id": work.id, "title": work.title}],
            "selected_work_ids": [work.id],
            "alternate_work_ids": [],
            "pool_count": 1,
            "diagnostics": {},
            "created_at": now,
            "updated_at": now,
        }
    )
    selection = client.patch(
        "/api/v1/local/literature-searches/search:api-literature/selection",
        headers={"X-Principia-Session": token},
        json={"work_ids": [work.id]},
    )
    assert selection.status_code == 200, selection.text
    started = client.post(
        "/api/v1/local/literature-searches/search:api-literature/discoveries",
        headers={"X-Principia-Session": token},
        json={"policy": "no_llm", "provider_profile_id": "siliconflow"},
    )
    assert started.status_code == 200, started.text
    job_id = started.json()["job_id"]
    deadline = time.monotonic() + 10
    record = started.json()
    while record["state"] not in {"succeeded", "failed"} and time.monotonic() < deadline:
        time.sleep(0.02)
        record = client.get(f"/api/v1/jobs/{job_id}").json()
    assert record["state"] == "succeeded", record
    assert record["result"]["candidate_count"] == 0
    assert record["result"]["abstract_fallback_papers"] == 1
    events = client.get(f"/api/v1/jobs/{job_id}/events").json()["items"]
    assert {item["event_type"] for item in events} >= {"queued", "completed"}


def test_literature_search_returns_202_with_provisional_progress_and_no_goal(
    tmp_path: Path, monkeypatch
) -> None:
    product, client, token = _product_client(tmp_path)
    release = threading.Event()
    work = WorkItem(
        id="work:async-search",
        title="Verification for autonomous scientific discovery",
        abstract="Independent verification reduces unsupported hypotheses under bounded conditions.",
        source="fixture",
        year=2026,
    )

    def fake_search(query: str, **kwargs: object) -> dict[str, object]:
        callback = kwargs["progress_callback"]
        search_id = str(kwargs["search_id"])
        callback(
            "query_planning",
            {"message": "Preparing", "progress": 0.05},
        )
        callback(
            "source_search",
            {
                "message": "Received fixture",
                "progress": 0.45,
                "query_count": 1,
                "sources": ["fixture"],
                "source_report": {
                    "source": "fixture",
                    "query": query,
                    "status": "success",
                    "returned_count": 1,
                    "latency_ms": 12,
                    "retries": 0,
                    "retry_after_seconds": None,
                },
                "provisional_results": [work.model_dump(mode="json")],
            },
        )
        assert release.wait(5)
        callback("dedupe", {"message": "Deduplicating", "progress": 0.72})
        callback("ranking", {"message": "Ranking", "progress": 0.84})
        callback("saving", {"message": "Saving", "progress": 0.96})
        projection = product.local.literature.search_service._work_projection(work, rank=1)
        return {
            "search_id": search_id,
            "goal": query,
            "area": "",
            "target_count": 20,
            "state": "ready",
            "sources": ["fixture"],
            "unavailable_sources": [],
            "results": [projection],
            "selected_work_ids": [work.id],
            "alternate_work_ids": [],
            "pool_count": 1,
            "diagnostics": {},
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }

    monkeypatch.setattr(product.local.literature.search_service, "search", fake_search)
    # Measure the steady-state interactive endpoint rather than TestClient's
    # one-time ASGI transport initialization.
    assert client.get("/api/v1/health").status_code == 200
    started_at = time.perf_counter()
    response = client.post(
        "/api/v1/local/literature-searches",
        headers={"X-Principia-Session": token},
        json={
            "query": "Which verification mechanisms improve autonomous discovery?",
            "target_count": 20,
        },
    )
    creation_seconds = time.perf_counter() - started_at
    assert response.status_code == 202, response.text
    assert creation_seconds < 0.3
    job_id = response.json()["job_id"]
    search_id = response.json()["result"]["search_id"]

    deadline = time.monotonic() + 3
    detail: dict[str, object] = {}
    while time.monotonic() < deadline:
        detail = client.get(f"/api/v1/local/literature-searches/{search_id}").json()
        if detail.get("results"):
            break
        time.sleep(0.02)
    assert detail["selection_finalized"] is False
    assert detail["results"][0]["work_id"] == work.id
    progress = client.get(f"/api/v1/jobs/{job_id}").json()
    assert progress["stage"] == "Searching sources"
    assert progress["eta_seconds"] is None

    release.set()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        progress = client.get(f"/api/v1/jobs/{job_id}").json()
        if progress["state"] == "succeeded":
            break
        time.sleep(0.02)
    assert progress["state"] == "succeeded", progress
    final = client.get(f"/api/v1/local/literature-searches/{search_id}").json()
    assert final["selection_finalized"] is True
    assert final["selected_work_ids"] == [work.id]
    with product.repository.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM local_research_goals").fetchone()[0] == 0
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM literature_search_attempts WHERE search_id=?",
                (search_id,),
            ).fetchone()[0]
            == 1
        )
    with client.stream("GET", f"/api/v1/jobs/{job_id}/stream") as stream:
        body = "\n".join(stream.iter_lines())
    assert "event: progress" in body
    assert "event: completed" in body
    with client.stream(
        "GET",
        f"/api/v1/jobs/{job_id}/stream",
        headers={"Last-Event-ID": "999999"},
    ) as stream:
        terminal_body = "\n".join(stream.iter_lines())
    assert "retry: 15000" in terminal_body
    assert "event: succeeded" in terminal_body


def test_literature_search_for_existing_folder_excludes_saved_works(
    tmp_path: Path, monkeypatch
) -> None:
    product, client, token = _product_client(tmp_path)
    source = product.local.create_managed_source(name="Existing literature")
    existing = WorkItem(
        id="work:already-saved",
        title="An already acquired kinetic limit",
        abstract="A kinetic description converges to a continuum fluid limit.",
        source="fixture",
        year=2025,
    )
    novel = WorkItem(
        id="work:new-result",
        title="A new hydrodynamic limit",
        abstract="A distinct scaling derives fluid equations from kinetic dynamics.",
        source="fixture",
        year=2026,
    )
    for work in (existing, novel):
        product.workspace.storage.save_work(work)
    product.repository.save_source_document(
        {
            "document_id": "doc:already-saved",
            "source_id": source["source_id"],
            "work_id": existing.id,
            "portable_relative_uri": "papers/already-saved/paper.pdf",
            "content_sha256": "a" * 64,
            "parse_status": "ready",
            "extraction_eligible": True,
        }
    )

    def fake_search(query: str, **kwargs: object) -> dict[str, object]:
        search_id = str(kwargs["search_id"])
        projections = [
            product.local.literature.search_service._work_projection(work, rank=rank)
            for rank, work in enumerate((existing, novel), start=1)
        ]
        return {
            "search_id": search_id,
            "goal": query,
            "area": "",
            "target_count": 1,
            "state": "ready",
            "sources": ["fixture"],
            "unavailable_sources": [],
            "results": projections,
            "selected_work_ids": [existing.id],
            "alternate_work_ids": [novel.id],
            "pool_count": 2,
            "diagnostics": {},
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }

    monkeypatch.setattr(product.local.literature.search_service, "search", fake_search)
    response = client.post(
        "/api/v1/local/literature-searches",
        headers={"X-Principia-Session": token},
        json={
            "query": "How do kinetic limits produce fluid equations?",
            "target_count": 1,
            "source_id": source["source_id"],
        },
    )
    assert response.status_code == 202, response.text
    search_id = response.json()["result"]["search_id"]
    deadline = time.monotonic() + 5
    detail: dict[str, object] = {}
    while time.monotonic() < deadline:
        detail = client.get(f"/api/v1/local/literature-searches/{search_id}").json()
        if detail.get("selection_finalized"):
            break
        time.sleep(0.02)

    assert detail["selected_work_ids"] == [novel.id]
    assert [item["work_id"] for item in detail["results"]] == [novel.id]
    assert detail["excluded_existing_count"] == 1


def test_folder_indexing_returns_202_and_persists_progress(tmp_path: Path) -> None:
    _, client, token = _product_client(tmp_path)
    folder = tmp_path / "index-asynchronous"
    folder.mkdir()
    (folder / "paper.txt").write_text(
        "A reusable mechanism links verification diversity to lower selection error.",
        encoding="utf-8",
    )
    registered = client.post(
        "/api/v1/local/sources",
        headers={"X-Principia-Session": token},
        json={"path": str(folder)},
    ).json()

    started_at = time.perf_counter()
    response = client.post(
        f"/api/v1/local/sources/{registered['source_id']}/indexes",
        headers={"X-Principia-Session": token},
    )
    creation_seconds = time.perf_counter() - started_at

    assert response.status_code == 202, response.text
    assert creation_seconds < 0.3
    job_id = response.json()["job_id"]
    deadline = time.monotonic() + 5
    record = response.json()
    while (
        record["state"] not in {"succeeded", "failed", "cancelled"} and time.monotonic() < deadline
    ):
        time.sleep(0.02)
        record = client.get(f"/api/v1/jobs/{job_id}").json()
    assert record["state"] == "succeeded", record
    assert record["result"]["document_count"] == 1
    events = client.get(f"/api/v1/jobs/{job_id}/events").json()["items"]
    assert {item["event_type"] for item in events} >= {"queued", "progress", "completed"}


def test_provider_profile_is_server_owned_and_unconfigured_remote_is_actionable(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("PRINCIPIA_LLM_API_KEY", raising=False)
    monkeypatch.delenv("SILICONFLOW_API_KEY", raising=False)
    product, client, token = _product_client(tmp_path)
    profile = client.get("/api/v1/providers").json()["profiles"][0]
    assert profile["configured"] is False
    assert "deepseek-ai/DeepSeek-V4-Flash" in profile["models"]
    now = utc_now()
    product.repository.save_literature_search(
        {
            "search_id": "search:unconfigured",
            "goal": "A sufficiently specific provider configuration fixture",
            "area": "machine-intelligence",
            "target_count": 1,
            "state": "ready",
            "sources": [],
            "unavailable_sources": [],
            "results": [{"work_id": "work:missing"}],
            "selected_work_ids": ["work:missing"],
            "alternate_work_ids": [],
            "pool_count": 1,
            "diagnostics": {},
            "created_at": now,
            "updated_at": now,
        }
    )
    response = client.post(
        "/api/v1/local/literature-searches/search:unconfigured/discoveries",
        headers={"X-Principia-Session": token},
        json={"policy": "remote", "egress_confirmed": True},
    )
    assert response.status_code == 409
    assert "not configured" in response.json()["error"]["message"]


def test_folder_first_acquisition_and_extraction_are_separate(tmp_path: Path) -> None:
    product, client, token = _product_client(tmp_path)
    headers = {"X-Principia-Session": token}
    created = client.post(
        "/api/v1/local/sources/managed",
        headers=headers,
        json={
            "name": "Verifier literature",
            "goal": "When does independent verification improve reasoning?",
            "area": "machine-intelligence",
        },
    )
    assert created.status_code == 200, created.text
    source_id = created.json()["source_id"]
    created_location = created.json()["created_location"]
    source = client.get(f"/api/v1/local/sources/{source_id}")
    assert source.status_code == 200
    assert created_location not in source.text
    assert source.json()["display_location"].startswith("Principia Local Data/")

    work = WorkItem(
        id="work:separate-acquisition",
        title="Independent verifier evidence",
        abstract=(
            "Independent verifier signals reduced selection errors when verifier "
            "failures differed from generator failures."
        ),
    )
    product.workspace.storage.save_work(work)
    now = utc_now()
    product.repository.save_literature_search(
        {
            "search_id": "search:separate-acquisition",
            "goal": "When does independent verification improve reasoning?",
            "area": "machine-intelligence",
            "target_count": 1,
            "state": "ready",
            "sources": ["fixture"],
            "unavailable_sources": [],
            "results": [{"work_id": work.id, "title": work.title}],
            "selected_work_ids": [work.id],
            "alternate_work_ids": [],
            "pool_count": 1,
            "diagnostics": {},
            "created_at": now,
            "updated_at": now,
        }
    )
    acquired = client.post(
        "/api/v1/local/literature-searches/search:separate-acquisition/acquisitions",
        headers=headers,
        json={"source_id": source_id, "work_ids": [work.id]},
    )
    assert acquired.status_code == 200, acquired.text
    acquisition_job = acquired.json()
    deadline = time.monotonic() + 10
    while acquisition_job["state"] not in {"succeeded", "failed"} and time.monotonic() < deadline:
        time.sleep(0.02)
        acquisition_job = client.get(f"/api/v1/jobs/{acquisition_job['job_id']}").json()
    assert acquisition_job["state"] == "succeeded", acquisition_job
    assert acquisition_job["result"]["candidate_count"] == 0
    assert acquisition_job["result"]["extraction_started"] is False
    assert product.repository.browse_candidates(limit=10)["total"] == 0

    source = client.get(f"/api/v1/local/sources/{source_id}").json()
    documents = client.get(f"/api/v1/local/sources/{source_id}/documents?extractable=true").json()
    assert documents["total"] == 1
    extracted = client.post(
        "/api/v1/local/extractions",
        headers=headers,
        json={
            "source_id": source_id,
            "source_revision": source["revision"],
            "document_ids": [documents["items"][0]["document_id"]],
            "selection_mode": "exact",
            "goal": "When does independent verification improve reasoning?",
            "area": "machine-intelligence",
            "policy": "no_llm",
            "quality_policy": "scientific-principle-v2",
        },
    )
    assert extracted.status_code == 200, extracted.text
    extraction_job = extracted.json()
    deadline = time.monotonic() + 10
    while extraction_job["state"] not in {"succeeded", "failed"} and time.monotonic() < deadline:
        time.sleep(0.02)
        extraction_job = client.get(f"/api/v1/jobs/{extraction_job['job_id']}").json()
    assert extraction_job["state"] == "succeeded", extraction_job
    assert extraction_job["result"]["candidate_count"] == 0


def test_library_exposes_overlapping_goal_area_and_folder_collections(tmp_path: Path) -> None:
    product, client, _ = _product_client(tmp_path)
    now = utc_now()
    for index, area in enumerate(("machine-intelligence", "quantum-systems")):
        search_id = f"search:collection:{index}"
        product.repository.save_literature_search(
            {
                "search_id": search_id,
                "goal": f"Collection goal {index} with enough scientific detail",
                "area": area,
                "target_count": 20,
                "state": "ready",
                "sources": ["fixture"],
                "unavailable_sources": [],
                "results": [],
                "selected_work_ids": [],
                "alternate_work_ids": [],
                "pool_count": 0,
                "diagnostics": {},
                "created_at": now,
                "updated_at": now,
            }
        )
        folder = tmp_path / f"private-source-{index}"
        folder.mkdir()
        source_id = f"src:collection:{index}"
        product.repository.register_source(
            source_id,
            folder,
            f"local-source://collection-{index}",
            f"Collection {index}",
        )
        product.repository.bind_research_goal_source(search_id=search_id, source_id=source_id)
    goals = client.get("/api/v1/library/collections?kind=research_goal").json()
    areas = client.get("/api/v1/library/collections?kind=area").json()
    sources = client.get("/api/v1/library/collections?kind=source").json()
    assert len(goals["items"]) == 2
    assert {item["area"] for item in areas["items"]} == {
        "machine-intelligence",
        "quantum-systems",
    }
    assert len(sources["items"]) == 2
    assert "overlapping views" in goals["explanation"]


def test_acquired_search_backfills_goal_collection_from_exact_work_provenance(
    tmp_path: Path,
) -> None:
    product, client, _ = _product_client(tmp_path)
    now = utc_now()
    search_id = "search:acquired-goal"
    work = WorkItem(
        id="work:acquired-goal",
        title="A transferable scientific result",
        abstract="Independent verification reduces selection errors under distinct failures.",
        source="fixture",
    )
    product.workspace.storage.save_work(work)
    product.repository.save_literature_search(
        {
            "search_id": search_id,
            "goal": "When does verification improve scientific inference?",
            "area": "",
            "target_count": 1,
            "state": "ready",
            "sources": ["fixture"],
            "unavailable_sources": [],
            "results": [work.model_dump(mode="json")],
            "selected_work_ids": [work.id],
            "alternate_work_ids": [],
            "pool_count": 1,
            "diagnostics": {},
            "created_at": now,
            "updated_at": now,
        },
        create_goal=False,
    )
    folder = tmp_path / "acquired-source"
    folder.mkdir()
    source_id = "src:acquired-goal"
    product.repository.register_source(
        source_id, folder, "local-source://acquired-goal", "Acquired source"
    )
    dataset_id = "dataset:acquired-goal"
    product.repository.save_dataset(
        {
            "dataset_id": dataset_id,
            "search_id": search_id,
            "source_id": source_id,
            "goal": "When does verification improve scientific inference?",
            "area": "",
            "state": "ready",
        },
        storage_root=str(folder),
    )
    product.repository.replace_dataset_works(
        dataset_id,
        [{"work_id": work.id, "selected": True, "acquisition_status": "usable"}],
    )
    candidate = CandidatePrinciple(
        candidate_id="cand:acquired-goal",
        area="machine-intelligence",
        title="Independent verification and selection errors",
        claim="Independent verification reduces selection errors under distinct failures.",
        kind=PrincipleKind.EMPIRICAL,
        scope=PrincipleScope(statement="distinct verifier failures"),
        falsifier="Selection errors do not decrease.",
    )
    product.repository.save_candidate(
        candidate,
        eligibility_status="eligible",
        quality_state="eligible",
        source_id=source_id,
    )
    product.repository.save_candidate_evidence(
        evidence_id="evidence:acquired-goal",
        candidate_id=candidate.candidate_id,
        work_id=work.id,
        excerpt_sha256="b" * 64,
    )

    receipt = product.repository.backfill_acquired_research_goals()
    goals = client.get("/api/v1/library/collections?kind=research_goal").json()["items"]

    assert receipt == {"goals_created": 1, "memberships_created": 1}
    assert len(goals) == 1
    assert goals[0]["title"] == "When does verification improve scientific inference?"
    assert goals[0]["principle_count"] == 1
