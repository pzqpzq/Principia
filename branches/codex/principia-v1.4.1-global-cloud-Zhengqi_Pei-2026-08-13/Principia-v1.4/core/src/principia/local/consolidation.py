from __future__ import annotations

import re
from dataclasses import dataclass

from ..domain import CandidatePrinciple, ScientificArgument, canonical_sha256
from ..persistence import V14WorkspaceRepository

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "is",
    "of",
    "on",
    "the",
    "to",
    "under",
    "when",
    "with",
}
_POSITIVE = {"increase", "increases", "enhance", "enhances", "improve", "improves"}
_NEGATIVE = {"decrease", "decreases", "reduce", "reduces", "impair", "impairs"}
_NEGATION = {"no", "not", "never", "without"}


def _tokens(value: str) -> set[str]:
    return {item for item in _TOKEN.findall(value.casefold()) if item not in _STOP}


def _jaccard(left: str, right: str) -> float:
    a, b = _tokens(left), _tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _polarity(value: str) -> tuple[bool, bool, bool]:
    tokens = _tokens(value)
    return bool(tokens & _POSITIVE), bool(tokens & _NEGATIVE), bool(tokens & _NEGATION)


@dataclass(frozen=True)
class ConsolidationMatch:
    candidate: CandidatePrinciple
    fingerprint: str
    similarity: dict[str, float]


class CandidateConsolidationService:
    """High-precision deterministic equivalence blocking; ambiguity stays separate."""

    def __init__(self, repository: V14WorkspaceRepository) -> None:
        self.repository = repository

    @staticmethod
    def _similarity(
        existing: ScientificArgument, argument: ScientificArgument
    ) -> dict[str, float]:
        return {
            "claim": _jaccard(existing.canonical_claim, argument.canonical_claim),
            "subject": _jaccard(existing.subject_system, argument.subject_system),
            "driver": _jaccard(
                existing.driver_or_intervention, argument.driver_or_intervention
            ),
            "outcome": _jaccard(existing.outcome, argument.outcome),
            "conditions": _jaccard(
                " ".join(existing.conditions), " ".join(argument.conditions)
            ),
        }

    @staticmethod
    def _is_equivalent(
        existing: ScientificArgument,
        argument: ScientificArgument,
        similarity: dict[str, float],
        *,
        shared_work: bool,
    ) -> bool:
        if existing.claim_class is not argument.claim_class:
            return False
        if _polarity(existing.canonical_claim) != _polarity(argument.canonical_claim):
            return False
        strict = similarity["claim"] >= 0.86 and all(
            similarity[field] >= threshold
            for field, threshold in (
                ("subject", 0.65),
                ("driver", 0.65),
                ("outcome", 0.65),
                ("conditions", 0.45),
            )
        )
        # Repeated normalization of the same evidence occasionally varies the
        # subject label (for example, "host tumors" versus "tumor systems")
        # while preserving the exact relationship.  For a shared Work, strong
        # claim/driver/outcome/condition agreement is therefore more reliable
        # than the provider-authored subject slot alone.
        same_evidence = (
            shared_work
            and similarity["claim"] >= 0.86
            and similarity["driver"] >= 0.75
            and similarity["outcome"] >= 0.75
            and similarity["conditions"] >= 0.40
        )
        return strict or same_evidence

    def find_equivalent(
        self, argument: ScientificArgument, *, area: str, work_id: str = ""
    ) -> ConsolidationMatch | None:
        for item in self.repository.scientific_candidate_arguments(area):
            existing = ScientificArgument.model_validate_json(item["argument_json"])
            similarity = self._similarity(existing, argument)
            shared_work = bool(
                work_id
                and work_id
                in {value for value in str(item.get("work_ids") or "").split(",") if value}
            )
            if self._is_equivalent(
                existing, argument, similarity, shared_work=shared_work
            ):
                return ConsolidationMatch(
                    candidate=CandidatePrinciple.model_validate_json(item["candidate_json"]),
                    fingerprint=str(item["candidate_fingerprint"]),
                    similarity=similarity,
                )
        return None

    def reconcile_existing(self, *, area: str) -> list[dict[str, object]]:
        """Merge high-confidence historical aliases without deleting any row."""

        rows = self.repository.scientific_candidate_arguments(area)
        canonical_rows: list[dict[str, object]] = []
        decisions: list[dict[str, object]] = []
        for row in rows:
            candidate = CandidatePrinciple.model_validate_json(str(row["candidate_json"]))
            argument = ScientificArgument.model_validate_json(str(row["argument_json"]))
            work_ids = {
                value for value in str(row.get("work_ids") or "").split(",") if value
            }
            match: tuple[dict[str, object], dict[str, float]] | None = None
            for existing_row in canonical_rows:
                existing = ScientificArgument.model_validate_json(
                    str(existing_row["argument_json"])
                )
                existing_work_ids = {
                    value
                    for value in str(existing_row.get("work_ids") or "").split(",")
                    if value
                }
                similarity = self._similarity(existing, argument)
                if self._is_equivalent(
                    existing,
                    argument,
                    similarity,
                    shared_work=bool(work_ids & existing_work_ids),
                ):
                    match = existing_row, similarity
                    break
            if match is None:
                canonical_rows.append(dict(row))
                continue
            existing_row, similarity = match
            canonical = CandidatePrinciple.model_validate_json(
                str(existing_row["candidate_json"])
            )
            self.record_merge(
                alias_candidate_id=candidate.candidate_id,
                canonical_candidate_id=canonical.candidate_id,
                similarity=similarity,
            )
            self.repository.merge_candidate_alias(
                alias_candidate_id=candidate.candidate_id,
                canonical_candidate_id=canonical.candidate_id,
            )
            decisions.append(
                {
                    "alias_candidate_id": candidate.candidate_id,
                    "canonical_candidate_id": canonical.candidate_id,
                    "similarity": similarity,
                }
            )
        return decisions

    def record_merge(
        self,
        *,
        alias_candidate_id: str,
        canonical_candidate_id: str,
        similarity: dict[str, float],
    ) -> None:
        fingerprint = canonical_sha256(
            {
                "alias": alias_candidate_id,
                "canonical": canonical_candidate_id,
                "similarity": similarity,
            }
        )
        self.repository.record_candidate_merge(
            alias_candidate_id=alias_candidate_id,
            canonical_candidate_id=canonical_candidate_id,
            fingerprint=fingerprint,
            decision={
                "decision": "equivalent_scope_compatible",
                "method": "scientific-argument-slots-v1",
                "similarity": similarity,
            },
        )
