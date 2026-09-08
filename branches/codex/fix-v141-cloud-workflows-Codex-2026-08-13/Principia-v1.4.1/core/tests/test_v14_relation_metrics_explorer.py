from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from principia.api.app import create_app
from principia.application import Principia, PrincipleRelationService, wilson_lower_bound
from principia.application.explorer import PrincipleExplorerService, _readable_title
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
from principia.models import WorkItem

_FIELDS = [
    "canonical_claim",
    "subject_system",
    "driver_or_intervention",
    "outcome",
    "direction_or_qualifier",
    "conditions",
    "boundary",
]


def _save_argument(
    product: Principia,
    *,
    candidate_id: str,
    work_id: str,
    claim: str,
    direction: str,
) -> None:
    quotation = claim
    span = SupportSpan(
        segment_key=f"segment:{candidate_id}",
        quotation=quotation,
        supported_fields=_FIELDS,  # type: ignore[arg-type]
    )
    argument = ScientificArgument(
        canonical_claim=claim,
        claim_class=ClaimClass.EMPIRICAL_ASSOCIATION,
        subject_system="verifier-guided selection systems",
        driver_or_intervention="independent verifier signals",
        outcome="inference selection errors",
        direction_or_qualifier=direction,
        conditions=["verifier failures differ from generator failures"],
        boundary=["the tested inference setting"],
        generalization_level=GeneralizationLevel.STUDY_BOUND,
        testability="Compare selection errors under independent and shared verifier failures.",
        testability_provenance="generated_challenge",
        atom_ids=[f"atom:{candidate_id}"],
        support=[span],
    )
    candidate = CandidatePrinciple(
        candidate_id=candidate_id,
        area="machine-intelligence",
        title=claim[:80],
        claim=claim,
        kind=PrincipleKind.EMPIRICAL,
        scope=PrincipleScope(statement="verifier failures differ from generator failures"),
        falsifier="Shared failures yield the same selection error change.",
    )
    product.workspace.storage.save_work(
        WorkItem(id=work_id, title=work_id, abstract=quotation, source="fixture")
    )
    product.repository.save_candidate(
        candidate,
        eligibility_status="eligible",
        quality_state="eligible",
        scientific_contract_version="scientific-principle-v2",
        quality_gate_version="quality-v2",
    )
    atom = EvidenceClaimAtom(
        atom_id=f"atom:{candidate_id}",
        source_key=f"source:{candidate_id}",
        faithful_claim=quotation,
        assertion_type="observed_result",
        evidence_type="experiment",
        epistemic_status="observed",
        support=[span],
    )
    product.repository.save_evidence_atom(atom, candidate_id=candidate_id, work_id=work_id)
    product.repository.save_candidate_evidence(
        evidence_id=f"evidence:{candidate_id}",
        candidate_id=candidate_id,
        work_id=work_id,
        excerpt_sha256="a" * 64,
    )
    product.repository.save_scientific_argument(candidate_id, argument, atoms=[atom])


def test_strengthened_deterministic_checks_hold_back_previous_output(tmp_path: Path) -> None:
    product = Principia.open(tmp_path / "workspace", cloud_root=tmp_path / "cloud")
    _save_argument(
        product,
        candidate_id="cand:future",
        work_id="work:future",
        claim=(
            "Multi-agent hierarchies are expected to play a central role in maintaining "
            "high decision quality in future discovery systems."
        ),
        direction="expected",
    )

    receipt = product.local.extraction.revalidate_deterministic_quality()

    assert receipt == {"checked": 1, "held_back": 1}
    detail = product.repository.candidate_detail("cand:future")
    assert detail is not None
    assert detail["local_metadata"]["quality_state"] == "quarantined"
    assert "speculative_future_claim" in detail["local_metadata"]["quarantine_reason"]


def test_relation_metrics_use_only_validated_relations_and_wilson_bound(tmp_path: Path) -> None:
    product = Principia.open(tmp_path / "workspace", cloud_root=tmp_path / "cloud")
    _save_argument(
        product,
        candidate_id="cand:a",
        work_id="work:a",
        claim=(
            "Independent verifier signals reduce inference selection errors when verifier "
            "failures differ from generator failures."
        ),
        direction="reduce",
    )
    _save_argument(
        product,
        candidate_id="cand:b",
        work_id="work:b",
        claim=(
            "Verifier signals reduce selection errors when their failures differ from "
            "generator failures in inference systems."
        ),
        direction="reduce",
    )
    result = product.relations.rebuild()
    assert result["relation_count"] == 1
    relation = product.repository.current_validated_relations()[0]
    assert relation["relation_type"] == "supports"
    assert relation["provenance"] == "deterministic_validated"
    cards = {item["id"]: item for item in product.explorer.browse(limit=100)["items"]}
    relation_facets = product.explorer.browse(limit=100)["facets"]
    assert relation_facets["influence_available_count"] == 2
    assert relation_facets["reliability_available_count"] == 1
    assert cards["cand:a"]["influence_score"] == 100
    assert cards["cand:a"]["reliability_score"] is None
    assert cards["cand:a"]["validated_relation_count"] == 1
    preview = cards["cand:a"]["related_principles"][0]
    assert preview["principle_id"] == "cand:b"
    assert preview["title"].startswith("Verifier signals reduce selection errors")
    assert preview["relation_type"] == "supports"
    assert preview["orientation"] == "outgoing"
    assert cards["cand:b"]["incoming_support_count"] == 1
    assert cards["cand:b"]["reliability_score"] == round(100 * (wilson_lower_bound(1, 0) or 0), 2)
    relation_response = product.explorer.relations("cand:a")["items"][0]
    assert relation_response["related_principle_id"] == "cand:b"
    assert relation_response["related_title"].startswith("Verifier signals reduce")
    assert relation_response["orientation"] == "outgoing"


def test_formula_allows_high_influence_with_low_relational_reliability() -> None:
    inputs = [{"candidate_id": f"cand:{name}"} for name in "abcd"]
    relations = [
        {
            "source_principle_id": "cand:b",
            "target_principle_id": "cand:a",
            "relation_type": "supports",
        },
        {
            "source_principle_id": "cand:c",
            "target_principle_id": "cand:a",
            "relation_type": "contradicts",
        },
        {
            "source_principle_id": "cand:d",
            "target_principle_id": "cand:a",
            "relation_type": "contradicts",
        },
    ]
    metrics, maximum = PrincipleRelationService._metrics(inputs, relations)
    target = next(item for item in metrics if item["principle_id"] == "cand:a")
    assert maximum == 3
    assert target["influence_score"] == 100
    assert target["reliability_score"] is not None
    assert target["reliability_score"] < 10


def test_principle_card_api_is_readable_and_exposes_null_absent_scores(tmp_path: Path) -> None:
    product = Principia.open(tmp_path / "workspace", cloud_root=tmp_path / "cloud")
    _save_argument(
        product,
        candidate_id="cand:single",
        work_id="work:single",
        claim="Independent verifier signals reduce selection errors under distinct failure modes.",
        direction="reduce",
    )
    client = TestClient(create_app(product, test_mode=True))
    response = client.get("/api/v1/principles", params={"scope": "local"})
    assert response.status_code == 200
    card = response.json()["items"][0]
    assert card["evidence_status"] == "checks_passed"
    assert card["human_review_status"] == "pending"
    assert card["evidence_scope"] == "one_work"
    assert card["reliability_score"] is None
    assert card["influence_score"] is None
    assert response.json()["facets"]["evidence_status_counts"] == {"checks_passed": 1}
    assert response.json()["facets"]["influence_available_count"] == 0
    serialized = response.text
    assert "quality-v2" not in serialized
    assert "scientific-principle-v2" not in serialized


def test_library_and_explorer_share_effective_multilabel_area_projection(tmp_path: Path) -> None:
    product = Principia.open(tmp_path / "workspace", cloud_root=tmp_path / "cloud")
    _save_argument(
        product,
        candidate_id="cand:area-projection",
        work_id="work:area-projection",
        claim="Independent verifier signals reduce selection errors under distinct failures.",
        direction="reduce",
    )
    product.repository.set_candidate_area(
        "cand:area-projection",
        "quantum-systems",
        state="suggested",
        provenance="fixture",
        rationale="Current post-extraction organization",
    )

    library_areas = {
        item["area"]: item["principle_count"]
        for item in product.repository.library_collections("area")
    }
    explorer = product.explorer.browse(limit=100)

    assert library_areas == {"quantum-systems": 1}
    assert explorer["facets"]["area_counts"] == library_areas
    assert product.explorer.browse(area="quantum-systems", limit=100)["total"] == 1
    assert product.explorer.browse(area="machine-intelligence", limit=100)["total"] == 0
    database_page = product.explorer.browse(
        area="quantum-systems",
        evidence_status="checks_passed",
        sort="updated",
        limit=24,
        page=1,
        page_mode=True,
    )
    assert database_page["total"] == 1
    assert database_page["facets"]["area_counts"] == {"quantum-systems": 1}

    product.repository.update_collection("area", "area:quantum-systems", "materials science")
    renamed_areas = {
        item["area"]: item["principle_count"]
        for item in product.repository.library_collections("area")
    }
    assert renamed_areas == {"materials-science": 1}
    assert product.explorer.browse(area="materials-science", limit=100)["total"] == 1
    assert product.explorer.browse(area="quantum-systems", limit=100)["total"] == 0


def test_filtered_graph_view_contains_cards_and_only_internal_validated_edges(
    tmp_path: Path,
) -> None:
    product = Principia.open(tmp_path / "workspace", cloud_root=tmp_path / "cloud")
    _save_argument(
        product,
        candidate_id="cand:graph-a",
        work_id="work:graph-a",
        claim="Independent verifier signals reduce inference selection errors under distinct failures.",
        direction="reduce",
    )
    _save_argument(
        product,
        candidate_id="cand:graph-b",
        work_id="work:graph-b",
        claim="Verifier signals reduce selection errors when failures differ from generator failures.",
        direction="reduce",
    )
    product.relations.rebuild()
    client = TestClient(create_app(product, test_mode=True))

    response = client.get(
        "/api/v1/principles/graph",
        params={"scope": "local", "q": "verifier errors", "limit": 120},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert {node["id"] for node in payload["nodes"]} == {"cand:graph-a", "cand:graph-b"}
    assert len(payload["edges"]) == 1
    assert {payload["edges"][0]["source"], payload["edges"][0]["target"]} == {
        "cand:graph-a",
        "cand:graph-b",
    }
    assert payload["edges"][0]["relation_type"] in {
        "supports",
        "analogous_to",
        "refines",
        "generalizes",
        "specializes",
        "depends_on",
        "contradicts",
    }
    assert payload["truncated"] is False


def test_virtual_relation_analysis_is_bounded_temporary_and_metric_neutral(tmp_path: Path) -> None:
    product = Principia.open(tmp_path / "workspace", cloud_root=tmp_path / "cloud")
    _save_argument(
        product,
        candidate_id="cand:virtual-a",
        work_id="work:virtual-a",
        claim="Independent verifier signals reduce selection errors under distinct failures.",
        direction="reduce",
    )
    _save_argument(
        product,
        candidate_id="cand:virtual-b",
        work_id="work:virtual-b",
        claim="Shared verifier signals increase selection errors under correlated failures.",
        direction="increase",
    )
    app = create_app(product, test_mode=True)
    client = TestClient(app)
    before = product.repository.current_validated_relations()

    response = client.post(
        "/api/v1/principles/potential-relations",
        json={"principle_ids": ["cand:virtual-a", "cand:virtual-b"]},
        headers={"X-Principia-Session": app.state.session_token},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["analyzed_pair_count"] == 1
    assert payload["skipped_validated_pair_count"] == 0
    suggestion = payload["items"][0]
    assert suggestion["relation_id"].startswith("virtual:")
    assert suggestion["status"] == "virtual_unvalidated"
    assert suggestion["persisted"] is False
    assert suggestion["affects_metrics"] is False
    assert suggestion["relation_type"] in {
        "potential_support",
        "potential_contradiction",
        "potential_refinement",
        "potential_analogy",
        "relationship_unclear",
    }
    assert product.repository.current_validated_relations() == before


def test_virtual_relation_analysis_skips_existing_validated_pairs(tmp_path: Path) -> None:
    product = Principia.open(tmp_path / "workspace", cloud_root=tmp_path / "cloud")
    _save_argument(
        product,
        candidate_id="cand:linked-a",
        work_id="work:linked-a",
        claim="Independent verifier signals reduce inference selection errors.",
        direction="reduce",
    )
    _save_argument(
        product,
        candidate_id="cand:linked-b",
        work_id="work:linked-b",
        claim="Verifier signals reduce inference selection errors under distinct failures.",
        direction="reduce",
    )
    product.relations.rebuild()
    result = product.explorer.potential_relations(["cand:linked-a", "cand:linked-b"])
    assert result["items"] == []
    assert result["analyzed_pair_count"] == 0
    assert result["skipped_validated_pair_count"] == 1


def test_long_principle_titles_end_at_a_word_boundary() -> None:
    claim = (
        "The steady-state quasiparticle density and tunneling rate in superconducting qubits "
        "scale with the electrical power emitted by a nearby radiator, with the scaling "
        "exponent depending on the dominant quasiparticle-loss mechanism under controlled "
        "cryogenic conditions."
    )
    stored_truncation = claim[:220]
    display = _readable_title(stored_truncation, claim)
    assert len(display) <= 220
    assert display.endswith("…")
    assert not display.endswith("mec…")


def test_explorer_semantic_recall_connects_hilbert_to_kinetic_fluid_claims() -> None:
    card = {
        "title": "Boltzmann–hydrodynamic limit boundary",
        "claim": "A kinetic limit links hard-sphere dynamics to continuum fluid equations.",
        "applicability": "dilute gases under molecular chaos",
        "area_labels": ["mathematical-physics"],
        "claim_type": "boundary_or_tradeoff",
    }
    assert PrincipleExplorerService._relevance(card, {"hilbert", "sixth", "problem"}) > 0


def test_principle_card_cursor_pages_have_no_gaps_or_duplicates(tmp_path: Path) -> None:
    product = Principia.open(tmp_path / "workspace", cloud_root=tmp_path / "cloud")
    for index in range(25):
        _save_argument(
            product,
            candidate_id=f"cand:{index:02d}",
            work_id=f"work:{index:02d}",
            claim=(
                f"Independent verifier configuration {index} reduces selection errors "
                "under distinct verifier and generator failure modes."
            ),
            direction="reduce",
        )
    identifiers: list[str] = []
    cursor: str | None = None
    while True:
        page = product.explorer.browse(limit=7, cursor=cursor, sort="title")
        identifiers.extend(item["id"] for item in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert len(identifiers) == 25
    assert len(set(identifiers)) == 25

    second_page = product.explorer.browse(limit=7, page=2, sort="title")
    assert second_page["page"] == 2
    assert second_page["page_size"] == 7
    assert second_page["page_count"] == 4
    assert [item["id"] for item in second_page["items"]] == identifiers[7:14]

    client = TestClient(create_app(product, test_mode=True))
    api_page = client.get(
        "/api/v1/principles",
        params={"scope": "local", "sort": "title", "limit": 7, "page": 2},
    )
    assert api_page.status_code == 200
    assert [item["id"] for item in api_page.json()["items"]] == identifiers[7:14]
    assert api_page.json()["facets"]["area_counts"] == {"machine-intelligence": 25}
    assert api_page.json()["facets"]["claim_type_counts"] == {"empirical_association": 25}
    assert api_page.json()["facets"]["evidence_status_counts"] == {"checks_passed": 25}
