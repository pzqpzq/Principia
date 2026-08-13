from __future__ import annotations

import json
from pathlib import Path

from principia.application import Principia
from principia.domain import (
    CandidatePrinciple,
    ClaimClass,
    EvidenceClaimAtom,
    GeneralizationLevel,
    PrincipleKind,
    PrincipleScope,
    ScientificArgument,
    SupportSpan,
)
from principia.local import PortablePrincipleLibrary
from principia.local.literature import write_private_acquisition
from principia.models import WorkItem


def _seed_ready_principle(product: Principia) -> None:
    work = WorkItem(
        id="work:portable",
        title="Verifier diversity and inference selection",
        authors=["A. Researcher"],
        year=2026,
        venue="International Conference on Machine Learning",
        doi="10.0000/portable.fixture",
        abstract="Private source text that must not enter the showcase.",
        source="fixture",
    )
    product.workspace.storage.save_work(work)
    candidate = CandidatePrinciple(
        candidate_id="cand:portable",
        area="machine-intelligence",
        title="Diverse verifier failures reduce correlated selection errors",
        claim="Verifier diversity reduces correlated inference-selection errors under distinct failure modes.",
        kind=PrincipleKind.EMPIRICAL,
        scope=PrincipleScope(
            statement="Verifier failures are not perfectly correlated.",
            conditions=["distinct verifier failure modes"],
        ),
        falsifier="The error rate does not change when verifier failure diversity increases.",
    )
    product.repository.save_candidate(
        candidate,
        eligibility_status="eligible",
        quality_state="eligible",
        scientific_contract_version="scientific-principle-v2",
        quality_gate_version="quality-v2",
    )
    span = SupportSpan(
        segment_key="segment:portable",
        quotation="Verifier diversity reduces correlated inference-selection errors.",
        supported_fields=[
            "canonical_claim",
            "subject_system",
            "driver_or_intervention",
            "outcome",
            "direction_or_qualifier",
            "conditions",
            "boundary",
        ],
    )
    atom = EvidenceClaimAtom(
        atom_id="atom:portable",
        source_key="source:portable",
        faithful_claim=span.quotation,
        assertion_type="observed_result",
        evidence_type="experiment",
        epistemic_status="observed",
        support=[span],
    )
    product.repository.save_evidence_atom(atom, candidate_id=candidate.candidate_id, work_id=work.id)
    argument = ScientificArgument(
        canonical_claim=candidate.claim,
        claim_class=ClaimClass.EMPIRICAL_ASSOCIATION,
        subject_system="inference-selection systems",
        driver_or_intervention="verifier diversity",
        outcome="correlated selection errors",
        direction_or_qualifier="reduces",
        conditions=["distinct verifier failure modes"],
        boundary=["the evaluated inference tasks"],
        generalization_level=GeneralizationLevel.STUDY_BOUND,
        testability=candidate.falsifier,
        testability_provenance="generated_challenge",
        atom_ids=[atom.atom_id],
        support=[span],
    )
    product.repository.save_scientific_argument(candidate.candidate_id, argument, atoms=[atom])
    product.repository.save_candidate_evidence(
        evidence_id="evidence:portable",
        candidate_id=candidate.candidate_id,
        work_id=work.id,
        excerpt_sha256="a" * 64,
        locator={"section": "results", "page_start": 4},
    )
    product.repository.set_candidate_area(
        candidate.candidate_id,
        "machine-intelligence",
        state="confirmed",
        provenance="fixture",
        rationale="fixture area",
    )


def test_portable_export_is_paper_free_path_free_and_deterministic(tmp_path: Path) -> None:
    product = Principia.open(tmp_path / "private", cloud_root=tmp_path / "cloud")
    _seed_ready_principle(product)
    first = tmp_path / "showcase-a"
    second = tmp_path / "showcase-b"
    library = PortablePrincipleLibrary(product.workspace.storage, product.repository)
    first_manifest = library.export(first)
    second_manifest = library.export(second)
    assert first_manifest == second_manifest
    assert {path.name for path in first.iterdir()} == {
        "manifest.json",
        "principles.jsonl",
        "works.jsonl",
        "relations.jsonl",
    }
    assert first_manifest["principle_count"] == 1
    combined = b"".join(path.read_bytes() for path in sorted(first.iterdir()))
    assert b"Private source text" not in combined
    assert str(tmp_path).encode() not in combined
    assert b".pdf" not in combined
    assert b"https://doi.org/10.0000/portable.fixture" in combined
    assert (first / "principles.jsonl").read_bytes() == (second / "principles.jsonl").read_bytes()


def test_portable_import_populates_explorer_without_paper_files(tmp_path: Path) -> None:
    source_product = Principia.open(tmp_path / "source", cloud_root=tmp_path / "cloud-a")
    _seed_ready_principle(source_product)
    showcase = tmp_path / "showcase"
    PortablePrincipleLibrary(
        source_product.workspace.storage, source_product.repository
    ).export(showcase)

    destination = Principia.open(tmp_path / "destination", cloud_root=tmp_path / "cloud-b")
    receipt = PortablePrincipleLibrary(
        destination.workspace.storage, destination.repository
    ).import_showcase(showcase)
    with destination.repository.connect() as connection:
        before_assignments = connection.execute(
            "SELECT COUNT(*) FROM candidate_area_assignments"
        ).fetchone()[0]
        before_digest = connection.execute(
            "SELECT content_digest FROM local_candidates WHERE candidate_id='cand:portable'"
        ).fetchone()[0]
    PortablePrincipleLibrary(
        destination.workspace.storage, destination.repository
    ).import_showcase(showcase)
    with destination.repository.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM candidate_area_assignments"
        ).fetchone()[0] == before_assignments
        assert connection.execute(
            "SELECT content_digest FROM local_candidates WHERE candidate_id='cand:portable'"
        ).fetchone()[0] == before_digest
    page = destination.explorer.browse(scope="local", limit=24)
    assert receipt["imported_principles"] == 1
    assert page["total"] == 1
    assert page["items"][0]["id"] == "cand:portable"
    assert not list((tmp_path / "destination").rglob("*.pdf"))
    work = destination.repository.work_detail("work:portable")
    assert work is not None
    assert work["abstract"] == ""
    assert work["url"] == "https://doi.org/10.0000/portable.fixture"
    detail = destination.repository.candidate_detail("cand:portable")
    assert detail is not None
    assert detail["evidence"][0]["source_url"] == (
        "https://doi.org/10.0000/portable.fixture"
    )
    assert detail["evidence"][0]["quotation"] == ""


def test_portable_export_can_preserve_one_private_folder_boundary(tmp_path: Path) -> None:
    product = Principia.open(tmp_path / "private", cloud_root=tmp_path / "cloud")
    _seed_ready_principle(product)
    folder = tmp_path / "folder"
    folder.mkdir()
    product.repository.register_source(
        "src:portable",
        folder,
        "local-source://portable",
        "Portable folder",
    )
    with product.repository.connect() as connection:
        connection.execute(
            "INSERT INTO candidate_source_memberships(candidate_id, source_id, created_at) "
            "VALUES ('cand:portable', 'src:portable', '2026-01-01T00:00:00Z')"
        )
    output = tmp_path / "folder-showcase"
    manifest = PortablePrincipleLibrary(
        product.workspace.storage, product.repository
    ).export(output, source_id="src:portable", label="Portable folder")
    assert manifest["collection_kind"] == "private_folder"
    assert manifest["principle_count"] == 1


def test_private_acquisition_co_locates_every_document_representation(tmp_path: Path) -> None:
    paths = write_private_acquisition(
        tmp_path,
        work_id="work:one",
        acquired={
            "content_kind": "abstract",
            "mime_type": "text/plain",
            "bytes": b"permitted abstract",
            "text": "permitted abstract",
            "byte_sha256": "1" * 64,
            "text_sha256": "2" * 64,
        },
        relative_stem="2026-A useful finding",
        metadata={"title": "A useful finding", "venue": "Nature"},
    )
    document_root = Path(paths["document_path"])
    assert document_root.parent == tmp_path / "papers"
    assert {path.name for path in document_root.iterdir()} == {
        "abstract.txt",
        "normalized.txt",
        "metadata.json",
    }
    metadata = json.loads((document_root / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["venue"] == "Nature"
