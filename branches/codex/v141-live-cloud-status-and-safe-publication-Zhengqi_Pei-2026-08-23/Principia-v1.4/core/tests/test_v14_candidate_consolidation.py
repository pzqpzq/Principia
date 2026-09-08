from __future__ import annotations

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
from principia.local.consolidation import CandidateConsolidationService
from principia.models import WorkItem

FIELDS = [
    "canonical_claim",
    "subject_system",
    "driver_or_intervention",
    "outcome",
    "direction_or_qualifier",
    "conditions",
    "boundary",
]


def _argument(claim: str, *, direction: str = "reduces") -> ScientificArgument:
    support = SupportSpan(
        segment_key="segment:fixture",
        quotation=(
            "Independent verifier signals reduce selection errors when verifier failures "
            "differ from generator failures."
        ),
        supported_fields=FIELDS,  # type: ignore[arg-type]
    )
    return ScientificArgument(
        canonical_claim=claim,
        claim_class=ClaimClass.EMPIRICAL_ASSOCIATION,
        subject_system="verifier-guided selection systems",
        driver_or_intervention="independent verifier signals",
        outcome="selection errors",
        direction_or_qualifier=direction,
        conditions=["verifier failures differ from generator failures"],
        boundary=["the tested verifier-guided selection setting"],
        generalization_level=GeneralizationLevel.STUDY_BOUND,
        testability="Compare selection errors under independent and shared verifier failures.",
        testability_provenance="generated_challenge",
        atom_ids=["atom:fixture"],
        support=[support],
    )


def test_high_precision_consolidation_matches_equivalent_but_not_opposite(
    tmp_path: Path,
) -> None:
    product = Principia.open(tmp_path)
    product.workspace.storage.save_work(
        WorkItem(
            id="work:fixture",
            title="Independent verifier fixture",
            abstract="A bounded deterministic fixture.",
            source="fixture",
        )
    )
    canonical = CandidatePrinciple(
        candidate_id="cand:canonical",
        area="machine-intelligence",
        title="Independent verification reduces selection errors",
        claim=(
            "Independent verifier signals reduce selection errors when verifier failures "
            "differ from generator failures."
        ),
        kind=PrincipleKind.EMPIRICAL,
        scope=PrincipleScope(statement="verifier failures differ from generator failures"),
        falsifier="Shared failures produce the same reduction.",
    )
    product.repository.save_candidate(
        canonical,
        eligibility_status="eligible",
        candidate_fingerprint="a" * 64,
        scientific_contract_version="scientific-principle-v2",
        quality_gate_version="quality-v2",
        quality_state="eligible",
    )
    atom = EvidenceClaimAtom(
        atom_id="atom:fixture",
        source_key="source:0",
        faithful_claim=canonical.claim,
        assertion_type="observed_result",
        evidence_type="experiment",
        epistemic_status="observed",
        support=_argument(canonical.claim).support,
    )
    product.repository.save_evidence_atom(
        atom,
        candidate_id=canonical.candidate_id,
        work_id="work:fixture",
    )
    product.repository.save_candidate_evidence(
        evidence_id="evidence:canonical",
        candidate_id=canonical.candidate_id,
        work_id="work:fixture",
        excerpt_sha256="a" * 64,
    )
    product.repository.save_scientific_argument(
        canonical.candidate_id,
        _argument(canonical.claim),
        atoms=[atom],
    )
    consolidation = CandidateConsolidationService(product.repository)
    equivalent = _argument(
        "When verifier failures differ from generator failures, independent verifier "
        "signals reduce selection errors."
    )
    match = consolidation.find_equivalent(equivalent, area="machine-intelligence")
    assert match is not None
    assert match.candidate.candidate_id == canonical.candidate_id
    consolidation.record_merge(
        alias_candidate_id="cand:alias",
        canonical_candidate_id=canonical.candidate_id,
        similarity=match.similarity,
    )
    with product.repository.connect() as conn:
        alias = conn.execute(
            "SELECT canonical_candidate_id FROM candidate_aliases "
            "WHERE alias_candidate_id='cand:alias'"
        ).fetchone()
    assert alias[0] == canonical.candidate_id

    opposite = _argument(
        "When verifier failures differ from generator failures, independent verifier "
        "signals increase selection errors.",
        direction="increases",
    )
    assert consolidation.find_equivalent(opposite, area="machine-intelligence") is None

    alias_argument = _argument(
        canonical.claim,
    ).model_copy(
        update={
            "conditions": ["verifier failures differ in the tested failure regime"],
            "boundary": ["the tested failure regime"],
        }
    )
    alias_candidate = canonical.model_copy(update={"candidate_id": "cand:same-work-alias"})
    product.repository.save_candidate(
        alias_candidate,
        eligibility_status="eligible",
        candidate_fingerprint="b" * 64,
        scientific_contract_version="scientific-principle-v2",
        quality_gate_version="quality-v2",
        quality_state="eligible",
    )
    product.repository.save_evidence_atom(
        atom,
        candidate_id=alias_candidate.candidate_id,
        work_id="work:fixture",
    )
    product.repository.save_candidate_evidence(
        evidence_id="evidence:alias",
        candidate_id=alias_candidate.candidate_id,
        work_id="work:fixture",
        excerpt_sha256="a" * 64,
    )
    product.repository.save_scientific_argument(
        alias_candidate.candidate_id,
        alias_argument,
        atoms=[atom],
    )
    decisions = consolidation.reconcile_existing(area="machine-intelligence")
    assert decisions == [
        {
            "alias_candidate_id": alias_candidate.candidate_id,
            "canonical_candidate_id": canonical.candidate_id,
            "similarity": decisions[0]["similarity"],
        }
    ]
    detail = product.repository.candidate_detail(alias_candidate.candidate_id)
    assert detail is not None
    assert detail["local_metadata"]["quality_state"] == "merged_alias"
    assert detail["local_metadata"]["quarantine_reason"] == (
        f"equivalent_to:{canonical.candidate_id}"
    )
