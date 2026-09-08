from __future__ import annotations

import time
from pathlib import Path

import httpx
import pytest

from principia.application import Principia
from principia.local import SafeLiteratureAcquirer, ScholarlySearchService
from principia.local.literature import collapse_literature_editions, rank_literature_for_goal
from principia.models import WorkItem, WorkList
from principia.persistence import V14WorkspaceRepository
from principia.storage import WorkspaceStorage


class _ResearchFixture:
    def __init__(self, items: list[WorkItem]) -> None:
        self.items = items
        self.calls: list[dict[str, object]] = []

    def search(self, goal: str, **kwargs: object) -> WorkList:
        self.calls.append({"goal": goal, **kwargs})
        return WorkList(
            query=goal,
            items=self.items,
            target_count=int(kwargs["target_count"]),
            sources=list(kwargs["sources"]),
        )


def test_goal_rerank_suppresses_generic_keyword_false_friends() -> None:
    ranked = rank_literature_for_goal(
        "How do material and interface mechanisms cause superconducting qubit coherence loss?",
        [
            {
                "work_id": "work:generic",
                "rank": 1,
                "retrieval_rank": 1,
                "title": "Material efficiency improvements in transport policy",
                "abstract": "An economic index decomposition study.",
            },
            {
                "work_id": "work:qubit",
                "rank": 2,
                "retrieval_rank": 2,
                "title": "Interface dielectric loss in superconducting qubits",
                "abstract": "Surface participation limits transmon coherence.",
            },
        ],
    )
    assert ranked[0]["work_id"] == "work:qubit"
    assert ranked[0]["relevance_score"] > ranked[1]["relevance_score"]


def test_semantic_retrieval_order_is_not_overridden_by_exact_title_stuffing() -> None:
    ranked = rank_literature_for_goal(
        "how does multi-agent systems improve autonomous scientific discovery",
        [
            {
                "work_id": "work:semantic",
                "rank": 1,
                "retrieval_rank": 1,
                "title": (
                    "Many Heads Are Better Than One: Improved Scientific Idea "
                    "Generation by a Multi-Agent System"
                ),
                "abstract": (
                    "Specialized language-model agents collaborate, critique ideas, and "
                    "improve scientific hypothesis generation."
                ),
            },
            {
                "work_id": "work:stuffed",
                "rank": 5,
                "retrieval_rank": 5,
                "title": (
                    "Multi-Agent Systems for Autonomous Scientific Discovery in "
                    "High-Dimensional Research Landscapes"
                ),
                "abstract": "A short generic description without evaluated mechanisms.",
                "publication_status": "published",
            },
        ],
    )

    assert ranked[0]["work_id"] == "work:semantic"


def test_exact_hilbert_sixth_problem_paper_outranks_keyword_false_friends() -> None:
    ranked = rank_literature_for_goal(
        "Hilbert's sixth problem and its solution by Yu Deng",
        [
            {
                "work_id": "work:hilbert-space",
                "rank": 1,
                "retrieval_rank": 1,
                "title": "Six open problems for learning in Hilbert spaces",
                "abstract": "Kernel methods are studied in reproducing Hilbert spaces.",
            },
            {
                "work_id": "work:exact",
                "rank": 8,
                "retrieval_rank": 8,
                "title": (
                    "Hilbert's sixth problem: derivation of fluid equations via "
                    "Boltzmann's kinetic theory"
                ),
                "abstract": (
                    "Yu Deng, Zaher Hani, and Xiao Ma derive fluid equations from "
                    "Boltzmann kinetic theory."
                ),
            },
            {
                "work_id": "work:sixth-order",
                "rank": 2,
                "retrieval_rank": 2,
                "title": "A sixth-order discretization for fluid equations",
                "abstract": "A numerical method for continuum mechanics.",
            },
        ],
    )
    assert ranked[0]["work_id"] == "work:exact"
    assert ranked[0]["relevance_score"] > ranked[1]["relevance_score"]


def test_literature_preview_collapses_repository_versions_without_losing_venue() -> None:
    collapsed, count = collapse_literature_editions(
        [
            {
                "work_id": "work:preprint-v1",
                "retrieval_rank": 2,
                "title": "A Shared Scientific Result",
                "authors": ["Ada Researcher"],
                "year": 2025,
                "publication_status": "preprint",
                "venue": "arXiv",
                "oa_locations": [{"provider": "arxiv", "url": "https://arxiv.org/pdf/1"}],
            },
            {
                "work_id": "work:published",
                "retrieval_rank": 1,
                "title": "A Shared Scientific Result",
                "authors": ["Ada Researcher"],
                "year": 2025,
                "publication_status": "published",
                "publication_venue": "Journal of Reproducible Results",
                "venue": "Journal of Reproducible Results",
                "oa_locations": [],
            },
        ]
    )

    assert count == 1
    assert len(collapsed) == 1
    assert collapsed[0]["work_id"] == "work:preprint-v1"
    assert collapsed[0]["publication_status"] == "published"
    assert collapsed[0]["publication_venue"] == "Journal of Reproducible Results"
    assert collapsed[0]["edition_work_ids"] == ["work:published", "work:preprint-v1"]


def test_hilbert_sixth_profile_rejects_hilbert_space_and_sixth_order_homonyms() -> None:
    goal = "Hilbert's sixth problem and its solution"
    exact = {
        "title": "Hilbert's sixth problem: derivation of fluid equations via Boltzmann's kinetic theory",
        "abstract": "A derivation from kinetic theory.",
    }
    false_friends = [
        {
            "title": "Global solutions of approximation problems in Hilbert spaces",
            "abstract": "Approximation in a Hilbert space.",
        },
        {
            "title": "A finite element method for a sixth order elliptic problem",
            "abstract": "A numerical boundary-value method.",
        },
    ]

    from principia.local.literature import _domain_relevance

    assert _domain_relevance(goal, exact) is True
    assert all(_domain_relevance(goal, item) is False for item in false_friends)


def test_rag_search_excludes_generic_retrieval_false_friends(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path)
    repository = V14WorkspaceRepository(storage.db_path)
    works = [
        WorkItem(
            id="work:rag",
            title="Uncertainty-aware retrieval-augmented generation",
            abstract="A RAG system detects contradictory evidence for question answering.",
            source="arxiv",
        ),
        WorkItem(
            id="work:radiometry",
            title="Ozone column retrieval with uncertainty estimation",
            abstract="Radiometric calibration for atmospheric measurements.",
            source="crossref",
        ),
    ]
    for work in works:
        storage.save_work(work)
    result = ScholarlySearchService(_ResearchFixture(works), repository).search(
        "Which uncertainty mechanisms make retrieval-augmented generation robust?",
        area="machine-intelligence",
        target_count=20,
    )
    assert result["selected_work_ids"] == ["work:rag"]
    assert result["diagnostics"]["principia_domain_relevance"] == {
        "active": True,
        "excluded_false_friends": 1,
        "retained": 1,
        "target": 20,
    }


def test_autonomous_scientific_agent_search_excludes_generic_recovery(
    tmp_path: Path,
) -> None:
    storage = WorkspaceStorage(tmp_path)
    repository = V14WorkspaceRepository(storage.db_path)
    works = [
        WorkItem(
            id="work:agent",
            title="Self-healing autonomous agents for scientific discovery",
            abstract="An AI agent detects evidence errors and recovers its scientific workflow.",
            source="arxiv",
        ),
        WorkItem(
            id="work:flood",
            title="How firms recover after floods",
            abstract="Economic mechanisms explain business recovery from flooding.",
            source="crossref",
        ),
    ]
    for work in works:
        storage.save_work(work)
    result = ScholarlySearchService(_ResearchFixture(works), repository).search(
        "Which mechanisms allow autonomous scientific agents to recover from evidence errors?",
        area="",
        target_count=5,
    )
    assert result["selected_work_ids"] == ["work:agent"]
    assert result["diagnostics"]["principia_domain_relevance"]["active"] is True
    assert result["diagnostics"]["principia_domain_relevance"]["excluded_false_friends"] == 1


def test_title_only_metadata_is_visible_but_never_selected(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path)
    repository = V14WorkspaceRepository(storage.db_path)
    works = [
        WorkItem(
            id="work:title-only",
            title="Verification mechanisms for autonomous scientific agents",
            abstract="",
            source="crossref",
        ),
        WorkItem(
            id="work:abstract",
            title="Evidence recovery in autonomous scientific agents",
            abstract="A controlled study evaluates detection and recovery from evidence errors.",
            source="arxiv",
        ),
    ]
    for work in works:
        storage.save_work(work)
    result = ScholarlySearchService(_ResearchFixture(works), repository).search(
        "Which verification mechanisms help autonomous scientific agents recover?",
        area="",
        target_count=1,
    )
    assert result["selected_work_ids"] == ["work:abstract"]
    by_id = {item["work_id"]: item for item in result["results"]}
    assert by_id["work:title-only"]["extractable_metadata"] is False
    assert result["diagnostics"]["metadata_only_count"] == 1
    with pytest.raises(ValueError, match="without usable evidence metadata"):
        ScholarlySearchService(_ResearchFixture(works), repository).update_selection(
            result["search_id"], ["work:title-only"]
        )


def test_existing_folder_works_are_removed_before_preview_is_truncated(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path)
    repository = V14WorkspaceRepository(storage.db_path)
    works = [
        WorkItem(
            id=f"work:{index:02d}",
            title=f"Kinetic-to-fluid limit result {index:02d}",
            abstract="A hydrodynamic limit connects the Boltzmann equation to fluid dynamics.",
            source="arxiv",
            arxiv_id=f"2608.{index:05d}",
        )
        for index in range(40)
    ]
    for work in works:
        storage.save_work(work)
    existing = {work.id for work in works[:10]}

    result = ScholarlySearchService(_ResearchFixture(works), repository).search(
        "Hilbert's sixth problem and its relation to physics",
        area="",
        target_count=20,
        excluded_work_ids=existing,
    )

    assert len(result["selected_work_ids"]) == 20
    assert len(result["alternate_work_ids"]) == 10
    assert not existing.intersection(result["selected_work_ids"])
    assert not existing.intersection(item["work_id"] for item in result["results"])
    assert result["diagnostics"]["excluded_existing_count"] == 10


def test_search_defaults_to_twenty_with_visible_alternates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    storage = WorkspaceStorage(tmp_path)
    repository = V14WorkspaceRepository(storage.db_path)
    items = [
        WorkItem(
            id=f"work:{index:02d}",
            title=f"Evidence paper {index}",
            abstract="A grounded abstract.",
            source="arxiv",
            arxiv_id=f"2608.{index:05d}",
        )
        for index in range(35)
    ]
    for item in items:
        storage.save_work(item)
    research = _ResearchFixture(items)
    result = ScholarlySearchService(research, repository).search(
        "Which mechanisms improve verification?", area="machine-intelligence"
    )
    assert len(result["selected_work_ids"]) == 20
    assert len(result["alternate_work_ids"]) == 10
    assert len(result["results"]) == 30
    assert "openalex" not in result["sources"]
    assert result["unavailable_sources"][0]["provider"] == "openalex"
    assert repository.literature_search(result["search_id"])["goal"] == result["goal"]


def test_safe_acquirer_revalidates_hostile_redirects() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://127.0.0.1/private"})

    acquirer = SafeLiteratureAcquirer(
        transport=httpx.MockTransport(handler),
        resolver=lambda host: ["93.184.216.34"] if host == "example.org" else [host],
    )
    with pytest.raises(ValueError, match="private, loopback"):
        acquirer.download(
            {
                "url": "https://example.org/paper",
                "is_open_access": True,
                "access_basis": "fixture_open_access",
            }
        )


def test_safe_acquirer_streams_permitted_text_and_rejects_oversize() -> None:
    responses = iter(
        [
            httpx.Response(
                200,
                headers={"content-type": "text/plain"},
                content=b"A specific scientific mechanism with bounded evidence.",
            ),
            httpx.Response(
                200,
                headers={"content-type": "text/plain", "content-length": str(51 * 1024 * 1024)},
                content=b"not downloaded",
            ),
        ]
    )
    acquirer = SafeLiteratureAcquirer(
        transport=httpx.MockTransport(lambda request: next(responses)),
        resolver=lambda host: ["93.184.216.34"],
    )
    location = {
        "url": "https://example.org/paper",
        "is_open_access": True,
        "access_basis": "fixture_open_access",
        "license": "CC-BY",
    }
    acquired = acquirer.download(location)
    assert acquired["text"].startswith("A specific")
    assert len(acquired["byte_sha256"]) == 64
    with pytest.raises(ValueError, match="byte limit"):
        acquirer.download(location)


def test_full_text_without_oa_basis_fails_closed() -> None:
    acquirer = SafeLiteratureAcquirer(
        transport=httpx.MockTransport(lambda request: httpx.Response(200)),
        resolver=lambda host: ["93.184.216.34"],
    )
    with pytest.raises(PermissionError, match="open-access basis"):
        acquirer.download({"url": "https://example.org/paper", "is_open_access": False})


def test_acquisition_receipt_counts_the_materialized_pdf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    product = Principia.open(tmp_path / "workspace", cloud_root=tmp_path / "cloud")
    work = WorkItem(
        id="work:pdf",
        title="A bounded PDF finding",
        abstract="A bounded PDF finding with extractable evidence.",
        source="arxiv",
        arxiv_id="2608.00001",
    )
    product.workspace.storage.save_work(work)
    product.repository.save_literature_search(
        {
            "search_id": "search:pdf",
            "goal": "Which bounded relation is supported?",
            "area": "",
            "target_count": 1,
            "state": "ready",
            "selected_work_ids": [work.id],
            "alternate_work_ids": [],
            "results": [{"work_id": work.id}],
        },
        create_goal=False,
    )
    source = product.local.create_managed_source(name="PDF receipt fixture")
    acquired = {
        "content_kind": "full_text",
        "mime_type": "application/pdf",
        "bytes": b"fixture-pdf-bytes",
        "text": "A bounded PDF finding with extractable evidence.",
        "pages": [
            {
                "page": 1,
                "section": "results",
                "text": "A bounded PDF finding with extractable evidence.",
            }
        ],
        "byte_size": len(b"fixture-pdf-bytes"),
        "byte_sha256": "1" * 64,
        "text_sha256": "2" * 64,
        "access_basis": "fixture_open_access",
        "manuscript_version": "author_preprint",
        "license": "CC-BY",
        "final_url": "https://example.org/paper.pdf",
    }
    monkeypatch.setattr(
        product.local.acquisition,
        "_acquire",
        lambda *args, **kwargs: (dict(acquired), None),
    )
    job = product.local.start_literature_acquisition(
        search_id="search:pdf", source_id=source["source_id"], work_ids=[work.id]
    )
    deadline = time.monotonic() + 10
    current = job
    while current.state not in {"succeeded", "failed", "cancelled"} and time.monotonic() < deadline:
        time.sleep(0.02)
        current = product.local.get(job.job_id) or current
    assert current.state == "succeeded", current.error
    assert current.result is not None
    assert current.result["full_text_count"] == 1
    assert current.result["pdf_count"] == 1
    assert current.result["text_full_text_count"] == 0
    assert current.result["items"][0]["representation"] == "pdf"
    source_root = Path(source["created_location"])
    assert len(list(source_root.glob("papers/*/paper.pdf"))) == 1
    assert not list(source_root.glob("papers/*/normalized.txt"))
    assert not list(source_root.glob("papers/*/metadata.json"))
    assert len(list((product.workspace.path / "source_cache").rglob("normalized.txt"))) == 1
    assert len(list((product.workspace.path / "source_cache").rglob("metadata.json"))) == 1
    with pytest.raises(ValueError, match="already in this private folder"):
        product.local.start_literature_acquisition(
            search_id="search:pdf", source_id=source["source_id"], work_ids=[work.id]
        )
