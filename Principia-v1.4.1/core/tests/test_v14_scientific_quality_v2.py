from __future__ import annotations

from principia.domain import (
    ClaimClass,
    EvidenceAtomProposal,
    EvidenceClaimAtom,
    GeneralizationLevel,
    QualityReason,
    ScientificArgument,
    SupportSpan,
    concise_principle_title,
    materialize_evidence_atoms,
)
from principia.local.areas import suggest_area_labels
from principia.local.quality import ScientificQualityGate, stable_atom_id

SUPPORTED_FIELDS = [
    "canonical_claim",
    "subject_system",
    "driver_or_intervention",
    "outcome",
    "direction_or_qualifier",
    "conditions",
    "boundary",
]


def _atom(*, work_id: str, claim: str, quotation: str) -> EvidenceClaimAtom:
    return EvidenceClaimAtom(
        atom_id=stable_atom_id(work_id=work_id, source_key="source:0", faithful_claim=claim),
        source_key="source:0",
        faithful_claim=claim,
        assertion_type="observed_result",
        evidence_type="experiment",
        epistemic_status="observed",
        support=[
            SupportSpan(
                segment_key="seg:0",
                quotation=quotation,
                supported_fields=SUPPORTED_FIELDS,  # type: ignore[arg-type]
            )
        ],
    )


def _argument(atom: EvidenceClaimAtom, **updates: object) -> ScientificArgument:
    payload: dict[str, object] = {
        "canonical_claim": (
            "Independent verification reduces reasoning errors when the verifier has "
            "access to evidence not used by the generator."
        ),
        "claim_class": ClaimClass.DESIGN_RULE,
        "subject_system": "reasoning systems with independent verifiers",
        "driver_or_intervention": "independent verification",
        "outcome": "reasoning errors",
        "direction_or_qualifier": "reduces",
        "conditions": ["the verifier uses independent evidence"],
        "boundary": ["not established for verifiers sharing only generator evidence"],
        "generalization_level": GeneralizationLevel.STUDY_BOUND,
        "testability": "Compare error rates with and without independent verifier evidence.",
        "testability_provenance": "generated_challenge",
        "atom_ids": [atom.atom_id],
        "support": atom.support,
    }
    payload.update(updates)
    return ScientificArgument.model_validate(payload)


def test_document_priority_example_is_never_eligible() -> None:
    quotation = (
        "Ours is the first one including all four features: individual learning, "
        "no communication, shared resources with conflicts, and individual goals."
    )
    atom = _atom(work_id="work:mas", claim=quotation, quotation=quotation)
    argument = _argument(
        atom,
        canonical_claim=(
            "The paper presents the first multi-agent system model that simultaneously "
            "includes all four specified features."
        ),
        subject_system="The paper",
        driver_or_intervention="presentation of a multi-agent model",
        outcome="coverage of four specified features",
        direction_or_qualifier="first",
    )
    reasons = ScientificQualityGate().validate_argument(
        argument, atoms=[atom], independent_work_ids={"work:mas"}
    )
    assert QualityReason.DOCUMENT_META_CLAIM in reasons
    assert QualityReason.PRIORITY_OR_NOVELTY_CLAIM in reasons


def test_contextual_first_order_and_paper_substrate_are_not_keyword_rejected() -> None:
    quotation = (
        "A first-order phase transition in the paper substrate increased interfacial "
        "resistance under high humidity."
    )
    atom = _atom(work_id="work:materials", claim=quotation, quotation=quotation)
    argument = _argument(
        atom,
        canonical_claim=quotation,
        claim_class=ClaimClass.EMPIRICAL_ASSOCIATION,
        subject_system="paper substrate interfaces",
        driver_or_intervention="a first-order phase transition",
        outcome="interfacial resistance",
        direction_or_qualifier="increased",
        conditions=["high humidity"],
        boundary=["paper substrate interfaces under the tested humidity range"],
        testability="Measure interfacial resistance across the phase transition.",
    )
    reasons = ScientificQualityGate().validate_argument(
        argument, atoms=[atom], independent_work_ids={"work:materials"}
    )
    assert QualityReason.DOCUMENT_META_CLAIM not in reasons
    assert QualityReason.PRIORITY_OR_NOVELTY_CLAIM not in reasons


def test_cross_study_claim_requires_two_independent_works() -> None:
    quotation = "Independent verification reduced reasoning errors in the tested setting."
    atom = _atom(work_id="work:one", claim=quotation, quotation=quotation)
    argument = _argument(
        atom,
        generalization_level=GeneralizationLevel.CROSS_STUDY,
        atom_ids=[atom.atom_id, "atom:second-compatible-source"],
    )
    reasons = ScientificQualityGate().validate_argument(
        argument, atoms=[atom], independent_work_ids={"work:one"}
    )
    assert QualityReason.UNSUPPORTED_GENERALIZATION in reasons


def test_atom_anchor_must_be_exact_and_source_key_known() -> None:
    atom = _atom(
        work_id="work:one",
        claim="Verification reduced errors in the tested setting.",
        quotation="Verification reduced errors in the tested setting.",
    )
    failures = ScientificQualityGate().validate_atoms(
        [atom],
        segment_text={"seg:0": "A different source sentence."},
        permitted_source_keys={"source:1"},
    )
    assert failures[atom.atom_id] == [
        QualityReason.UNKNOWN_SOURCE_REFERENCE,
        QualityReason.EVIDENCE_ANCHOR_MISSING,
    ]


def test_modal_strengthening_from_may_require_to_requires_is_quarantined() -> None:
    quotation = "Hard instances may require several verification attempts."
    atom = _atom(work_id="work:one", claim=quotation, quotation=quotation)
    argument = _argument(
        atom,
        canonical_claim="Hard instances require several verification attempts.",
        subject_system="hard inference-time search instances",
        driver_or_intervention="instance difficulty",
        outcome="several verification attempts",
        direction_or_qualifier="requires",
        conditions=["hard instances"],
    )
    reasons = ScientificQualityGate().validate_argument(
        argument, atoms=[atom], independent_work_ids={"work:one"}
    )
    assert QualityReason.UNSUPPORTED_MODAL_STRENGTH in reasons


def test_vague_future_importance_is_not_a_reusable_principle() -> None:
    quotation = (
        "Multi-agent hierarchies are expected to play a central role in larger "
        "and more heterogeneous spaces."
    )
    atom = _atom(work_id="work:future", claim=quotation, quotation=quotation)
    argument = _argument(
        atom,
        canonical_claim=quotation,
        subject_system="multi-agent hierarchies",
        driver_or_intervention="larger and more heterogeneous search spaces",
        outcome="a central role in early decisions",
        direction_or_qualifier="expected",
        conditions=["larger heterogeneous spaces"],
    )
    reasons = ScientificQualityGate().validate_argument(
        argument, atoms=[atom], independent_work_ids={"work:future"}
    )
    assert QualityReason.SPECULATIVE_FUTURE_CLAIM in reasons


def test_concrete_prospective_hypothesis_is_not_rejected_as_future_rhetoric() -> None:
    quotation = (
        "Under heterogeneous verifier failures, routing each claim to three independent "
        "critics is predicted to reduce undetected reasoning errors."
    )
    atom = _atom(work_id="work:hypothesis", claim=quotation, quotation=quotation)
    argument = _argument(
        atom,
        canonical_claim=quotation,
        subject_system="multi-agent verification systems",
        driver_or_intervention="routing each claim to three independent critics",
        outcome="undetected reasoning errors",
        direction_or_qualifier="is predicted to reduce",
        conditions=["heterogeneous verifier failures"],
    )
    reasons = ScientificQualityGate().validate_argument(
        argument, atoms=[atom], independent_work_ids={"work:hypothesis"}
    )
    assert QualityReason.SPECULATIVE_FUTURE_CLAIM not in reasons


def test_principle_titles_are_short_relational_labels() -> None:
    quotation = "Experiment strategy evolution increases code execution success rates."
    atom = _atom(work_id="work:title", claim=quotation, quotation=quotation)
    argument = _argument(
        atom,
        canonical_claim=quotation,
        claim_class=ClaimClass.EMPIRICAL_ASSOCIATION,
        driver_or_intervention="experiment strategy evolution",
        outcome="increased code execution success rates",
    )
    title = concise_principle_title(argument)
    assert title == "Experiment strategy evolution–code execution success rates principle"
    assert title != argument.canonical_claim
    assert len(title.split()) <= 9


def test_hilbert_focus_semantically_matches_kinetic_fluid_arguments() -> None:
    quotation = (
        "The Boltzmann-Grad limit links hard-sphere kinetic dynamics to continuum "
        "fluid equations under molecular chaos."
    )
    atom = _atom(work_id="work:hilbert", claim=quotation, quotation=quotation)
    argument = _argument(
        atom,
        canonical_claim=quotation,
        subject_system="hard-sphere kinetic systems",
        driver_or_intervention="the Boltzmann-Grad limit",
        outcome="continuum fluid equations",
        direction_or_qualifier="links",
        conditions=["molecular chaos"],
    )
    reasons = ScientificQualityGate().validate_argument(
        argument,
        atoms=[atom],
        independent_work_ids={"work:hilbert"},
        goal="Hilbert's sixth problem and its solution",
    )
    assert QualityReason.OFF_GOAL not in reasons


def test_argument_without_distinctive_goal_terms_is_quarantined() -> None:
    quotation = "Resource disturbances cause disproportionate hospital service loss."
    atom = _atom(work_id="work:hospital", claim=quotation, quotation=quotation)
    argument = _argument(
        atom,
        canonical_claim=quotation,
        subject_system="hospital service systems",
        driver_or_intervention="resource disturbances",
        outcome="service loss",
        direction_or_qualifier="disproportionate",
        conditions=["combined resource disturbances"],
    )
    reasons = ScientificQualityGate().validate_argument(
        argument,
        atoms=[atom],
        independent_work_ids={"work:hospital"},
        goal="Which coordination and memory mechanisms improve multi-agent scientific discovery?",
    )
    assert QualityReason.OFF_GOAL in reasons


def test_human_team_analogy_does_not_answer_multi_agent_discovery_goal() -> None:
    quotation = (
        "Specialization and coordination predict innovation performance in undergraduate teams."
    )
    atom = _atom(work_id="work:teams", claim=quotation, quotation=quotation)
    argument = _argument(
        atom,
        canonical_claim=quotation,
        subject_system="undergraduate innovation teams",
        driver_or_intervention="specialization and coordination",
        outcome="innovation performance",
        direction_or_qualifier="positively predicts",
        conditions=["undergraduate teams"],
    )
    reasons = ScientificQualityGate().validate_argument(
        argument,
        atoms=[atom],
        independent_work_ids={"work:teams"},
        goal=(
            "Which coordination, specialization, memory, and error-control mechanisms "
            "improve multi-agent autonomous scientific discovery?"
        ),
    )
    assert QualityReason.OFF_GOAL in reasons


def test_direct_multi_agent_mechanism_remains_goal_relevant() -> None:
    quotation = (
        "Dynamic agent routing reduces latency in multi-agent collaboration while "
        "preserving task success."
    )
    atom = _atom(work_id="work:agents", claim=quotation, quotation=quotation)
    argument = _argument(
        atom,
        canonical_claim=quotation,
        subject_system="multi-agent collaboration systems",
        driver_or_intervention="dynamic agent routing",
        outcome="latency and task success",
        direction_or_qualifier="reduces latency while preserving success",
        conditions=["multi-agent tasks"],
    )
    reasons = ScientificQualityGate().validate_argument(
        argument,
        atoms=[atom],
        independent_work_ids={"work:agents"},
        goal=(
            "Which coordination, specialization, memory, and error-control mechanisms "
            "improve multi-agent autonomous scientific discovery?"
        ),
    )
    assert QualityReason.OFF_GOAL not in reasons


def test_unknown_provider_span_is_rejected_without_losing_the_batch() -> None:
    proposals = [
        EvidenceAtomProposal(
            source_key="source:0",
            assertion_type="observed_result",
            evidence_type="experiment",
            epistemic_status="observed",
            support_segment_keys=["unknown:span"],
        ),
        EvidenceAtomProposal(
            source_key="source:0",
            assertion_type="observed_result",
            evidence_type="experiment",
            epistemic_status="observed",
            support_segment_keys=["known:span"],
        ),
    ]
    atoms = materialize_evidence_atoms(
        proposals,
        {
            "known:span": (
                "known:segment",
                "Independent verification reduced errors in the tested setting.",
            )
        },
    )
    assert len(atoms) == 1
    assert atoms[0].support[0].segment_key == "known:segment"


def test_area_suggestions_are_post_extraction_multilabel_organization() -> None:
    hilbert = suggest_area_labels(
        argument={
            "subject_system": "hard-sphere gas in the Boltzmann-Grad limit",
            "driver_or_intervention": "molecular chaos",
            "outcome": "hydrodynamic fluid equations",
        },
        claim="A kinetic limit links atomistic hard-sphere motion to continuum laws.",
        work_titles=[
            "Hilbert's sixth problem: derivation of fluid equations via Boltzmann's kinetic theory"
        ],
        research_focus="Hilbert's sixth problem and its solution",
    )
    assert hilbert == ["kinetic-theory", "fluid-dynamics", "mathematical-physics"]

    agents = suggest_area_labels(
        argument={
            "subject_system": "multi-agent scientific discovery systems",
            "driver_or_intervention": "role specialization and agent coordination",
            "outcome": "more reliable hypothesis generation",
        },
        claim="Specialized language-model agents coordinate scientific workflows.",
        work_titles=["Multi-agent systems for autonomous scientific discovery"],
    )
    assert agents == [
        "multi-agent-systems",
        "autonomous-scientific-discovery",
        "machine-intelligence",
    ]
