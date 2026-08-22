from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence

from ..domain import (
    EvidenceClaimAtom,
    GeneralizationLevel,
    QualityReason,
    ScientificArgument,
)

_DOCUMENT_SUBJECT = re.compile(
    r"^(?:this |the |our |a |an )?"
    r"(?:paper|article|study|work|authors?|dataset|benchmark|manuscript|report)"
    r"(?: itself)?$",
    re.IGNORECASE,
)
_DOCUMENT_PREDICATE = re.compile(
    r"\b(?:the|this|our) (?:paper|article|study|work|manuscript|report) "
    r"(?:presents?|reports?|introduces?|describes?|proposes?|demonstrates?|shows?)\b",
    re.IGNORECASE,
)
_AUTHOR_SELF = re.compile(
    r"\b(?:we|our (?:paper|work|method|model|approach|system)|the authors?) "
    r"(?:present|report|introduce|describe|propose|develop|claim|show|demonstrate)\b",
    re.IGNORECASE,
)
_PRIORITY = re.compile(
    r"\b(?:is|was|are|were|presents?|reports?|introduces?) (?:the )?first\b"
    r"|\bfirst (?:system|method|model|approach|framework|study|demonstration|report)\b"
    r"|\b(?:novel|state[- ]of[- ]the[- ]art|unprecedented) (?:method|model|approach|framework|system)\b",
    re.IGNORECASE,
)
_CAUSAL = re.compile(
    r"\b(?:causes?|caused|drives?|induces?|mediates?|leads? to|results? in|"
    r"prevents?|enables?|is responsible for|because of|due to)\b",
    re.IGNORECASE,
)
_COMPARATIVE = re.compile(
    r"\b(?:improves?|improved|reduces?|reduced|increases?|increased|decreases?|"
    r"decreased|outperforms?|better|worse|greater|higher|lower|more|less|"
    r"superior|inferior|stronger|weaker|most|least|best|worst)\b",
    re.IGNORECASE,
)
_NUMBER_OR_FORMULA = re.compile(r"(?<![A-Za-z])(?:\d+(?:\.\d+)?%?|[<>]=?|=|±)(?![A-Za-z])")
_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9+/-]*")
_NON_TESTABLE = re.compile(
    r"\b(?:further research|could be useful|may be important|has potential|"
    r"might help|better understanding|should be considered)\b",
    re.IGNORECASE,
)
_VAGUE_FUTURE = re.compile(
    r"\b(?:is|are|was|were)?\s*(?:expected|anticipated|predicted)\s+to\s+"
    r"(?:play|become|transform|revolutionize|shape)\b"
    r"|\b(?:promising|important|central|key)\s+(?:future\s+)?(?:role|direction|avenue)\b"
    r"|\bwill\s+(?:likely\s+)?(?:play|become|transform|revolutionize|shape)\b",
    re.IGNORECASE,
)
_UNHEDGED_RELATION = re.compile(
    r"\b(?:requires?|causes?|drives?|induces?|prevents?|ensures?|guarantees?)\b",
    re.IGNORECASE,
)
_HEDGED_RELATION = re.compile(
    r"\b(?:may|might|can|could)\s+"
    r"(?P<verb>require|cause|drive|induce|prevent|ensure|guarantee)s?\b",
    re.IGNORECASE,
)
_GOAL_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "do",
    "does",
    "for",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "which",
    "what",
    "when",
    "where",
    "under",
    "their",
    "these",
    "those",
    "with",
    "from",
    "mechanism",
    "mechanisms",
    "improve",
    "improvement",
    "reliably",
    "produce",
    "primary",
    "acquired",
    "approach",
    "approaches",
    "method",
    "methods",
    "model",
    "models",
    "system",
    "systems",
}

_GOAL_TERM_EQUIVALENTS = {
    "verification": "verify",
    "verifier": "verify",
    "verified": "verify",
    "verifying": "verify",
    "selection": "select",
    "selected": "select",
    "selecting": "select",
    "inference": "infer",
    "inferential": "infer",
    "reasoning": "reason",
    "discovery": "discover",
    "coordination": "coordinate",
    "optimization": "optimize",
    "training": "train",
}


def _goal_terms(value: str) -> set[str]:
    normalized = value.casefold()
    normalized = re.sub(r"\bcoginitive\b", "cognitive", normalized)
    normalized = re.sub(r"\b(?:cognitive|cognition)\b", " cognition ", normalized)
    normalized = re.sub(
        r"\b(?:neuroscience|neuroscientific|neural(?!\s+networks?))\b",
        " neuroscience ",
        normalized,
    )
    # Preserve short scientific acronyms before the generic length filter.
    # Without this expansion, a goal such as "AI for Physics" contains only
    # one usable term ("physics") and the old two-term overlap rule becomes
    # mathematically impossible to satisfy.
    normalized = re.sub(
        r"\b(?:ai|artificial intelligence|machine learning|deep learning|neural networks?)\b",
        " machineintelligence ",
        normalized,
    )
    normalized = re.sub(r"\bml\b", " machineintelligence ", normalized)
    normalized = re.sub(r"α\s*(?=pd[- ]?(?:1|l1))", "", normalized)
    normalized = re.sub(r"\bpd[- ]?l1\b", " pdl1 ", normalized)
    normalized = re.sub(r"\bpd[- ]?1\b", " pd1 ", normalized)
    normalized = re.sub(r"\bmulti[- ]agent\b", " multiagent ", normalized)
    terms: set[str] = set()
    for token in re.findall(r"[a-z0-9]+", normalized):
        if len(token) < 3 or token in _GOAL_STOPWORDS:
            continue
        if len(token) > 5 and token.endswith("ies"):
            token = token[:-3] + "y"
        elif len(token) > 5 and token.endswith("s") and not token.endswith("ss"):
            token = token[:-1]
        token = _GOAL_TERM_EQUIVALENTS.get(token, token)
        terms.add(token)
    return terms


def _goal_compound_anchors(value: str) -> set[str]:
    """Return vocabulary-neutral explicit topic anchors from a human goal."""

    anchors = {
        re.sub(r"[^a-z0-9]", "", match.casefold())
        for match in re.findall(r"\b[a-zA-Z0-9]+[- ][a-zA-Z0-9]+\b", value)
        if "-" in match
    }
    if re.search(r"\bmulti[- ]agent\b", value, re.IGNORECASE):
        anchors.add("multiagent")
    return {item for item in anchors if len(item) >= 5}


def _symbols(value: str) -> set[str]:
    output: set[str] = set()
    for token in _TOKEN.findall(value):
        capitals = sum(1 for character in token if character.isupper())
        if capitals >= 2 or any(character.isdigit() for character in token):
            normalized = re.sub(r"[^a-z0-9]", "", token.casefold())
            if len(normalized) >= 2:
                output.add(normalized)
    return output


def _evidence_text(atoms: Sequence[EvidenceClaimAtom]) -> str:
    lines: list[str] = []
    for atom in atoms:
        lines.append(atom.faithful_claim)
        lines.extend(span.quotation for span in atom.support)
    return "\n".join(lines)


class ScientificQualityGate:
    """Deterministic, fail-closed checks applied before independent Challenge."""

    version = "quality-v2"

    def validate_atoms(
        self,
        atoms: Sequence[EvidenceClaimAtom],
        *,
        segment_text: Mapping[str, str],
        permitted_source_keys: set[str],
    ) -> dict[str, list[QualityReason]]:
        failures: dict[str, list[QualityReason]] = {}
        for index, atom in enumerate(atoms):
            key = atom.atom_id or f"atom-index:{index}"
            reasons: list[QualityReason] = []
            if atom.source_key not in permitted_source_keys:
                reasons.append(QualityReason.UNKNOWN_SOURCE_REFERENCE)
            for span in atom.support:
                source = segment_text.get(span.segment_key)
                if source is None or span.quotation not in source:
                    reasons.append(QualityReason.EVIDENCE_ANCHOR_MISSING)
            if reasons:
                failures[key] = list(dict.fromkeys(reasons))
        return failures

    def validate_argument(
        self,
        argument: ScientificArgument,
        *,
        atoms: Sequence[EvidenceClaimAtom],
        independent_work_ids: set[str],
        goal: str = "",
    ) -> list[QualityReason]:
        reasons: list[QualityReason] = []
        claim = argument.canonical_claim.strip()
        subject = argument.subject_system.strip()
        combined = f"{subject}. {claim}"
        atom_ids = {atom.atom_id for atom in atoms}
        if not set(argument.atom_ids).issubset(atom_ids):
            reasons.append(QualityReason.UNKNOWN_SOURCE_REFERENCE)

        argument_text = " ".join(
            [
                argument.canonical_claim,
                argument.subject_system,
                argument.driver_or_intervention,
                argument.outcome,
                *argument.conditions,
            ]
        )
        goal_terms = _goal_terms(goal)
        argument_terms = _goal_terms(argument_text)
        # Goal fit is a prioritization signal, not a scientific-validity test.
        # Keep this vocabulary-neutral: named discipline profiles previously
        # rejected sound economics, robotics and neuroscience results merely
        # because those domains used different terminology. One substantive
        # lexical anchor is enough to flag obvious drift; the independent
        # evidence/challenge gates below decide whether the Principle is valid.
        overlap = goal_terms.intersection(argument_terms)
        compound_anchors = _goal_compound_anchors(goal)
        named_problem = bool(
            re.search(r"\b(?:problem|conjecture|paradox)\b", goal, re.IGNORECASE)
            and re.search(r"\b[A-Z][A-Za-z]+(?:['’]s)?\b", goal)
        )
        required_overlap = (
            len(goal_terms) if len(goal_terms) <= 2 else 2 if len(goal_terms) <= 6 else 3
        )
        if goal_terms and (
            not named_problem
            and not (compound_anchors & argument_terms)
            and len(overlap) < required_overlap
        ):
            reasons.append(QualityReason.OFF_GOAL)

        evidence = _evidence_text(atoms)
        evidence_normalized = re.sub(r"[^a-z0-9]", "", evidence.casefold())
        if _DOCUMENT_SUBJECT.search(subject) or _DOCUMENT_PREDICATE.search(combined):
            reasons.append(QualityReason.DOCUMENT_META_CLAIM)
        if _AUTHOR_SELF.search(combined):
            reasons.append(QualityReason.AUTHOR_SELF_CLAIM)
        # Grammatical priority claims are rejected, while contextual compounds
        # such as "first-order" and scientific materials such as "paper
        # substrate" do not match these patterns.
        if _PRIORITY.search(combined):
            reasons.append(QualityReason.PRIORITY_OR_NOVELTY_CLAIM)
        if _DOCUMENT_PREDICATE.search(combined):
            reasons.append(QualityReason.DESCRIPTIVE_SUMMARY)
        if argument.claim_class.value == "design_rule_or_intervention" and (
            argument.driver_or_intervention.casefold() in {"method", "model", "system"}
            or argument.outcome.casefold() in {"performance", "results", "capability"}
        ):
            reasons.append(QualityReason.METHOD_WITHOUT_RELATION)
        if (
            any(
                not value.strip()
                for value in (
                    argument.subject_system,
                    argument.driver_or_intervention,
                    argument.outcome,
                    argument.direction_or_qualifier,
                )
            )
            or not argument.conditions
            or not argument.boundary
        ):
            reasons.append(QualityReason.MISSING_ARGUMENT_SLOT)

        if _CAUSAL.search(claim) and not _CAUSAL.search(evidence):
            reasons.append(QualityReason.UNSUPPORTED_CAUSAL_LANGUAGE)
        if _COMPARATIVE.search(claim) and not _COMPARATIVE.search(evidence):
            reasons.append(QualityReason.UNSUPPORTED_COMPARATIVE)
        hedged_verbs = {
            match.group("verb").casefold() for match in _HEDGED_RELATION.finditer(evidence)
        }
        claim_verbs = {
            match.group(0).casefold().removesuffix("s")
            for match in _UNHEDGED_RELATION.finditer(claim)
            if not re.search(
                rf"\b(?:may|might|can|could)\s+{re.escape(match.group(0))}\b",
                claim,
                re.IGNORECASE,
            )
        }
        if claim_verbs & hedged_verbs:
            reasons.append(QualityReason.UNSUPPORTED_MODAL_STRENGTH)
        if (
            argument.generalization_level is GeneralizationLevel.CROSS_STUDY
            and len(independent_work_ids) < 2
        ):
            reasons.append(QualityReason.UNSUPPORTED_GENERALIZATION)
        if (
            argument.generalization_level is GeneralizationLevel.STUDY_BOUND
            and len(independent_work_ids) != 1
        ):
            reasons.append(QualityReason.UNSUPPORTED_SCOPE)
        if _NON_TESTABLE.search(argument.testability) or len(argument.testability.split()) < 5:
            reasons.append(QualityReason.NON_FALSIFIABLE)
        if _VAGUE_FUTURE.search(claim):
            reasons.append(QualityReason.SPECULATIVE_FUTURE_CLAIM)

        unsupported_numbers = [
            token for token in _NUMBER_OR_FORMULA.findall(claim) if token not in evidence
        ]
        if unsupported_numbers:
            reasons.append(QualityReason.UNSUPPORTED_NUMBER_OR_FORMULA)
        unsupported_symbols = [
            symbol for symbol in _symbols(claim) if symbol not in evidence_normalized
        ]
        if unsupported_symbols:
            reasons.append(QualityReason.UNSUPPORTED_ENTITY)
        return list(dict.fromkeys(reasons))


def stable_atom_id(*, work_id: str, source_key: str, faithful_claim: str) -> str:
    digest = hashlib.sha256(
        f"{work_id}\0{source_key}\0{' '.join(faithful_claim.split())}".encode()
    ).hexdigest()
    return f"atom:{digest[:26]}"
