from __future__ import annotations

import re
from enum import Enum
from typing import Literal

from pydantic import Field, model_validator

from .models import DomainModel

SCIENTIFIC_CONTRACT_VERSION: Literal["scientific-principle-v2"] = "scientific-principle-v2"
QUALITY_GATE_VERSION: Literal["quality-v2"] = "quality-v2"


class ClaimClass(str, Enum):
    EMPIRICAL_ASSOCIATION = "empirical_association"
    CAUSAL_MECHANISM = "causal_mechanism"
    DESIGN_RULE = "design_rule_or_intervention"
    BOUNDARY_TRADEOFF = "boundary_or_tradeoff"
    FORMAL_PROPOSITION = "formal_proposition"


class GeneralizationLevel(str, Enum):
    STUDY_BOUND = "study_bound"
    CROSS_STUDY = "cross_study"


class QualityVerdict(str, Enum):
    ELIGIBLE = "eligible"
    QUARANTINED = "quarantined"
    NOT_A_PRINCIPLE = "not_a_principle"
    AMBIGUOUS = "ambiguous"


class QualityReason(str, Enum):
    DOCUMENT_META_CLAIM = "document_meta_claim"
    PRIORITY_OR_NOVELTY_CLAIM = "priority_or_novelty_claim"
    AUTHOR_SELF_CLAIM = "author_self_claim"
    DESCRIPTIVE_SUMMARY = "descriptive_summary_not_principle"
    METHOD_WITHOUT_RELATION = "method_description_without_relation"
    MISSING_ARGUMENT_SLOT = "missing_argument_slot"
    UNSUPPORTED_RELATIONSHIP = "unsupported_relationship"
    UNSUPPORTED_CAUSAL_LANGUAGE = "unsupported_causal_language"
    UNSUPPORTED_COMPARATIVE = "unsupported_comparative_or_superlative"
    UNSUPPORTED_MODAL_STRENGTH = "unsupported_modal_or_quantifier_strengthening"
    UNSUPPORTED_GENERALIZATION = "unsupported_generalization"
    UNSUPPORTED_SCOPE = "unsupported_scope"
    OFF_GOAL = "off_goal"
    NON_FALSIFIABLE = "non_falsifiable"
    SPECULATIVE_FUTURE_CLAIM = "speculative_future_claim"
    UNKNOWN_SOURCE_REFERENCE = "unknown_source_reference"
    EVIDENCE_ANCHOR_MISSING = "evidence_anchor_missing"
    UNSUPPORTED_NUMBER_OR_FORMULA = "unsupported_number_or_formula"
    UNSUPPORTED_ENTITY = "unsupported_entity"
    CHALLENGE_UNAVAILABLE = "challenge_unavailable"
    CHALLENGE_INCONCLUSIVE = "challenge_inconclusive"


class SupportSpan(DomainModel):
    segment_key: str = Field(min_length=1, max_length=160)
    quotation: str = Field(min_length=8, max_length=1_200)
    supported_fields: list[
        Literal[
            "canonical_claim",
            "subject_system",
            "driver_or_intervention",
            "outcome",
            "direction_or_qualifier",
            "conditions",
            "boundary",
            "testability",
        ]
    ] = Field(min_length=1, max_length=8)


class EvidenceClaimAtom(DomainModel):
    """A source-faithful assertion. It is evidence, not yet a Principle."""

    atom_id: str = Field(default="", max_length=160)
    source_key: str = Field(min_length=1, max_length=160)
    faithful_claim: str = Field(min_length=12, max_length=2_400)
    assertion_type: Literal[
        "observed_result",
        "formal_result",
        "author_hypothesis",
        "review_summary",
        "author_priority_claim",
        "method_description",
    ]
    evidence_type: Literal[
        "experiment",
        "observational",
        "simulation",
        "formal_proof",
        "review",
        "method_report",
    ]
    epistemic_status: Literal["observed", "derived", "hypothesized", "reported"]
    support: list[SupportSpan] = Field(min_length=1, max_length=12)


class EvidenceClaimAtomBatch(DomainModel):
    atoms: list[EvidenceClaimAtom] = Field(default_factory=list, max_length=16)


class EvidenceAtomProposal(DomainModel):
    """Provider-facing atom; the server owns the exact source text."""

    source_key: str = Field(min_length=1, max_length=160)
    assertion_type: Literal[
        "observed_result",
        "formal_result",
        "author_hypothesis",
        "review_summary",
        "author_priority_claim",
        "method_description",
    ]
    evidence_type: Literal[
        "experiment",
        "observational",
        "simulation",
        "formal_proof",
        "review",
        "method_report",
    ]
    epistemic_status: Literal["observed", "derived", "hypothesized", "reported"]
    support_segment_keys: list[str] = Field(min_length=1, max_length=4)


class EvidenceAtomProposalBatch(DomainModel):
    atoms: list[EvidenceAtomProposal] = Field(max_length=16)


def materialize_evidence_atoms(
    proposals: list[EvidenceAtomProposal],
    evidence_lines: dict[str, tuple[str, str]],
) -> list[EvidenceClaimAtom]:
    """Resolve provider span keys to exact text under the canonical segment key."""

    supported_fields = [
        "canonical_claim",
        "subject_system",
        "driver_or_intervention",
        "outcome",
        "direction_or_qualifier",
        "conditions",
        "boundary",
    ]
    output: list[EvidenceClaimAtom] = []
    for proposal in proposals:
        keys = list(dict.fromkeys(proposal.support_segment_keys))
        if any(key not in evidence_lines for key in keys):
            continue
        resolved = [evidence_lines[key] for key in keys]
        quotations = [quotation for _, quotation in resolved]
        faithful_claim = " ".join(quotations).strip()
        output.append(
            EvidenceClaimAtom(
                source_key=proposal.source_key,
                faithful_claim=faithful_claim[:2_400],
                assertion_type=proposal.assertion_type,
                evidence_type=proposal.evidence_type,
                epistemic_status=proposal.epistemic_status,
                support=[
                    SupportSpan(
                        segment_key=canonical_segment_key,
                        quotation=quotation,
                        supported_fields=supported_fields,  # type: ignore[arg-type]
                    )
                    for canonical_segment_key, quotation in resolved
                ],
            )
        )
    return output


class ScientificArgument(DomainModel):
    """The normalized, transferable argument required for a v2 Candidate."""

    scientific_contract_version: Literal["scientific-principle-v2"] = SCIENTIFIC_CONTRACT_VERSION
    canonical_claim: str = Field(min_length=12, max_length=2_400)
    claim_class: ClaimClass
    subject_system: str = Field(min_length=2, max_length=400)
    driver_or_intervention: str = Field(min_length=1, max_length=800)
    outcome: str = Field(min_length=1, max_length=800)
    direction_or_qualifier: str = Field(min_length=1, max_length=400)
    conditions: list[str] = Field(min_length=1, max_length=12)
    boundary: list[str] = Field(min_length=1, max_length=12)
    boundary_provenance: Literal["source_grounded", "conservative_study_limit"] = "source_grounded"
    generalization_level: GeneralizationLevel
    testability: str = Field(min_length=12, max_length=1_200)
    testability_provenance: Literal["source_grounded", "generated_challenge"]
    atom_ids: list[str] = Field(min_length=1, max_length=32)
    support: list[SupportSpan] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def complete_argument_contract(self) -> ScientificArgument:
        supported = {field for span in self.support for field in span.supported_fields}
        required = {
            "canonical_claim",
            "subject_system",
            "driver_or_intervention",
            "outcome",
            "direction_or_qualifier",
            "conditions",
        }
        if self.boundary_provenance == "source_grounded":
            required.add("boundary")
        missing = sorted(required - supported)
        if missing:
            raise ValueError(f"support mapping is missing fields: {', '.join(missing)}")
        if len(set(self.atom_ids)) != len(self.atom_ids):
            raise ValueError("atom_ids must be unique")
        if self.generalization_level is GeneralizationLevel.CROSS_STUDY and len(self.atom_ids) < 2:
            raise ValueError("cross-study arguments require at least two evidence atoms")
        if (
            self.boundary_provenance == "conservative_study_limit"
            and self.generalization_level is not GeneralizationLevel.STUDY_BOUND
        ):
            raise ValueError("a conservative study boundary requires study_bound generalization")
        return self


def concise_principle_title(argument: ScientificArgument | dict[str, object]) -> str:
    """Build a short, non-duplicative title from validated argument slots.

    The scientific claim remains the description. Titles are a deterministic
    presentation projection and never introduce facts that were absent from the
    structured argument.
    """

    payload = (
        argument.model_dump(mode="json") if isinstance(argument, ScientificArgument) else argument
    )

    def phrase(key: str, words: int) -> str:
        value = re.sub(r"\s+", " ", str(payload.get(key) or "")).strip(" .,:;–—-")
        value = re.sub(r"\s*\([^)]*\)\s*", " ", value).strip()
        if key == "driver_or_intervention":
            value = re.sub(
                r"^(?:the\s+)?(?:integration|combination|use|application|deployment)\s+of\s+",
                "",
                value,
                flags=re.IGNORECASE,
            )
        if key in {"driver_or_intervention", "outcome"}:
            value = re.sub(r"^(?:the|a|an)\s+", "", value, flags=re.IGNORECASE)
        if key == "outcome":
            # Direction already has a dedicated argument slot. Removing a
            # duplicated nominal prefix prevents headings such as "drives
            # Increased..." without changing the scientific claim.
            value = re.sub(
                r"^(?:(?:increased|improved|enhanced|higher|greater|reduced|"
                r"decreased|lower)\s+|(?:maintenance|achievement|generation and "
                r"validation|detection|reduction)\s+of\s+)",
                "",
                value,
                flags=re.IGNORECASE,
            )
        parts = value.split()
        if len(parts) > words:
            value = " ".join(parts[:words]).rstrip(" .,:;–—-")
        value = re.sub(
            r"\s+(?:a|an|and|for|from|in|of|or|the|to|under|with)$",
            "",
            value,
            flags=re.IGNORECASE,
        )
        return value

    claim_class = str(payload.get("claim_class") or "")
    driver = phrase("driver_or_intervention", 4)
    outcome = phrase("outcome", 4)
    subject = phrase("subject_system", 4)
    if claim_class == ClaimClass.CAUSAL_MECHANISM.value:
        title = f"{driver}–{outcome} mechanism"
    elif claim_class == ClaimClass.DESIGN_RULE.value:
        title = f"{driver} for {outcome}"
    elif claim_class == ClaimClass.BOUNDARY_TRADEOFF.value:
        title = f"{driver}–{outcome} boundary"
    elif claim_class == ClaimClass.FORMAL_PROPOSITION.value:
        title = f"{subject}–{outcome} theorem"
    else:
        title = f"{driver}–{outcome} principle"
    title = re.sub(r"\s+", " ", title).strip(" .,:;–—-")
    if not title or len(title.split()) < 2:
        title = subject or phrase("canonical_claim", 10) or "Scientific principle"
    if len(title) > 72:
        boundary = title.rfind(" ", 0, 69)
        title = title[: boundary if boundary >= 40 else 69].rstrip(" .,:;–—-") + "…"
    return title[:1].upper() + title[1:]


class ScientificArgumentBatch(DomainModel):
    arguments: list[ScientificArgument] = Field(default_factory=list, max_length=8)


_ARGUMENT_SUPPORT_FIELDS = Literal[
    "canonical_claim",
    "subject_system",
    "driver_or_intervention",
    "outcome",
    "direction_or_qualifier",
    "conditions",
    "boundary",
]


class ArgumentSupportAssignment(DomainModel):
    """Compact provider output; exact quotations are resolved by the server."""

    field: _ARGUMENT_SUPPORT_FIELDS
    atom_ids: list[str] = Field(min_length=1, max_length=16)


class ScientificArgumentProposal(DomainModel):
    """Provider-facing argument without repeated, error-prone quote payloads."""

    scientific_contract_version: Literal["scientific-principle-v2"] = SCIENTIFIC_CONTRACT_VERSION
    canonical_claim: str = Field(min_length=12, max_length=2_400)
    claim_class: ClaimClass
    subject_system: str = Field(min_length=2, max_length=400)
    driver_or_intervention: str = Field(min_length=1, max_length=800)
    outcome: str = Field(min_length=1, max_length=800)
    direction_or_qualifier: str = Field(min_length=1, max_length=400)
    conditions: list[str] = Field(min_length=1, max_length=12)
    boundary: list[str] = Field(min_length=1, max_length=12)
    boundary_provenance: Literal["source_grounded", "conservative_study_limit"] = "source_grounded"
    generalization_level: GeneralizationLevel
    testability: str = Field(min_length=12, max_length=1_200)
    testability_provenance: Literal["source_grounded", "generated_challenge"]
    atom_ids: list[str] = Field(min_length=1, max_length=32)
    field_support: list[ArgumentSupportAssignment] = Field(min_length=6, max_length=20)

    @model_validator(mode="after")
    def complete_support_assignments(self) -> ScientificArgumentProposal:
        assigned = {item.field for item in self.field_support}
        required = {
            "canonical_claim",
            "subject_system",
            "driver_or_intervention",
            "outcome",
            "direction_or_qualifier",
            "conditions",
        }
        if self.boundary_provenance == "source_grounded":
            required.add("boundary")
        missing = sorted(required - assigned)
        if missing:
            raise ValueError(f"field_support is missing fields: {', '.join(missing)}")
        known = set(self.atom_ids)
        referenced = {atom_id for item in self.field_support for atom_id in item.atom_ids}
        if not referenced.issubset(known):
            raise ValueError("field_support references an atom outside atom_ids")
        if (
            self.boundary_provenance == "conservative_study_limit"
            and self.generalization_level is not GeneralizationLevel.STUDY_BOUND
        ):
            raise ValueError("a conservative study boundary requires study_bound generalization")
        return self


class ScientificArgumentProposalBatch(DomainModel):
    arguments: list[ScientificArgumentProposal] = Field(max_length=8)


def materialize_scientific_argument(
    proposal: ScientificArgumentProposal,
    atoms: list[EvidenceClaimAtom],
) -> ScientificArgument:
    """Resolve provider atom assignments to exact, server-owned quote spans."""

    atoms_by_id = {atom.atom_id: atom for atom in atoms}
    unknown = set(proposal.atom_ids) - set(atoms_by_id)
    if unknown:
        raise ValueError("argument proposal references an unknown evidence atom")
    mapped: dict[tuple[str, str], set[str]] = {}
    for assignment in proposal.field_support:
        for atom_id in assignment.atom_ids:
            atom = atoms_by_id.get(atom_id)
            if atom is None:
                raise ValueError("field support references an unknown evidence atom")
            for span in atom.support:
                mapped.setdefault((span.segment_key, span.quotation), set()).add(assignment.field)
    support = [
        SupportSpan(
            segment_key=segment_key,
            quotation=quotation,
            supported_fields=sorted(fields),  # type: ignore[arg-type]
        )
        for (segment_key, quotation), fields in sorted(mapped.items())
    ]
    payload = proposal.model_dump(mode="json", exclude={"field_support"})
    payload["support"] = [item.model_dump(mode="json") for item in support]
    return ScientificArgument.model_validate(payload)


class ChallengeDecision(DomainModel):
    argument_index: int = Field(ge=0, le=7)
    verdict: Literal["supported", "reject", "ambiguous"]
    reason_codes: list[QualityReason] = Field(default_factory=list, max_length=12)
    note: str = Field(default="", max_length=1_200)

    @model_validator(mode="after")
    def reasons_match_verdict(self) -> ChallengeDecision:
        if self.verdict == "supported" and self.reason_codes:
            raise ValueError("supported Challenge decisions cannot contain rejection reasons")
        if self.verdict != "supported" and not self.reason_codes:
            raise ValueError("non-supported Challenge decisions require reason codes")
        return self


class ChallengeDecisionBatch(DomainModel):
    decisions: list[ChallengeDecision] = Field(max_length=8)

    @model_validator(mode="after")
    def unique_argument_indices(self) -> ChallengeDecisionBatch:
        indices = [item.argument_index for item in self.decisions]
        if len(indices) != len(set(indices)):
            raise ValueError("Challenge decisions must use unique argument indices")
        return self


class QualityEvaluation(DomainModel):
    evaluation_id: str = Field(min_length=1, max_length=160)
    candidate_id: str = Field(min_length=1, max_length=160)
    argument_revision: int = Field(ge=1)
    verdict: QualityVerdict
    reason_codes: list[QualityReason] = Field(default_factory=list, max_length=32)
    scientific_contract_version: Literal["scientific-principle-v2"] = SCIENTIFIC_CONTRACT_VERSION
    quality_gate_version: Literal["quality-v2"] = QUALITY_GATE_VERSION
    evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    assessor: Literal["deterministic", "challenge", "human"]
    provider: str = Field(default="", max_length=160)
    model: str = Field(default="", max_length=240)
    prompt_sha256: str = Field(default="", pattern=r"^(?:|[0-9a-f]{64})$")
    output_sha256: str = Field(default="", pattern=r"^(?:|[0-9a-f]{64})$")
    note: str = Field(default="", max_length=2_400)
    created_at: str = Field(min_length=1)

    @model_validator(mode="after")
    def fail_closed_verdict(self) -> QualityEvaluation:
        if self.verdict is QualityVerdict.ELIGIBLE and self.reason_codes:
            raise ValueError("eligible evaluations cannot contain rejection reasons")
        if self.verdict is not QualityVerdict.ELIGIBLE and not self.reason_codes:
            raise ValueError("non-eligible evaluations require at least one reason code")
        return self
