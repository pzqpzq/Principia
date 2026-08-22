from __future__ import annotations

from pathlib import Path

from principia.domain import (
    CandidatePrinciple,
    ClaimClass,
    FoundationGroundingDecision,
    FoundationLinkProposal,
    GeneralizationLevel,
    PrincipleKind,
    PrincipleScope,
    ScientificArgument,
    SupportSpan,
)
from principia.local.foundation_grounding import FoundationGroundingService
from principia.persistence import V14WorkspaceRepository
from principia.providers import ProviderTrace
from principia.providers.openai_compatible import ScientificGeneration
from principia.storage import WorkspaceStorage


class _Cloud:
    def __init__(self, items: list[dict[str, object]]) -> None:
        self.items = items

    def active(self) -> dict[str, str]:
        return {"release_id": "fixture-v2"}

    def search(self, _request: object) -> dict[str, object]:
        return {"items": self.items}


class _Provider:
    def ground_scientific_principle(self, **_kwargs: object) -> ScientificGeneration:
        return ScientificGeneration(
            value=FoundationGroundingDecision(
                verdict="grounded",
                links=[
                    FoundationLinkProposal(
                        meta_principle_id="meta:physics:conservation-law",
                        relation_type="depends_on",
                        direction="meta_to_principle",
                        rationale=(
                            "The proposed mechanism preserves the conserved quantity under "
                            "the same closed-system assumptions."
                        ),
                        condition_compatibility="compatible",
                        variable_compatibility="compatible",
                        scale_compatibility="compatible",
                        confidence=0.91,
                    )
                ],
                rationale="A condition-compatible foundational relation is directly supported.",
            ),
            trace=ProviderTrace(
                provider="fixture",
                model="grounder",
                prompt_template="meta-grounding-v1",
                prompt_sha256="a" * 64,
                input_sha256="b" * 64,
                output_sha256="c" * 64,
                latency_ms=4,
                input_tokens=100,
                output_tokens=40,
                attempts=1,
                transport_attempts=1,
                schema_valid=True,
            ),
        )


def _candidate() -> CandidatePrinciple:
    return CandidatePrinciple(
        candidate_id="candidate:foundation-test",
        area="physics",
        title="Conservation-constrained dynamics",
        claim="Conservation constraints reduce physically invalid trajectories.",
        kind=PrincipleKind.MECHANISTIC,
        scope=PrincipleScope(
            statement="Closed dynamical systems",
            conditions=["the conserved quantity is correctly specified"],
        ),
        falsifier="No reduction in invalid trajectories under matched evaluation.",
    )


def _argument() -> ScientificArgument:
    return ScientificArgument(
        canonical_claim="Conservation constraints reduce physically invalid trajectories.",
        claim_class=ClaimClass.CAUSAL_MECHANISM,
        subject_system="closed dynamical systems",
        driver_or_intervention="conservation constraints",
        outcome="physically invalid trajectories",
        direction_or_qualifier="reduce",
        conditions=["the conserved quantity is correctly specified"],
        boundary=["open systems with unmodelled exchange"],
        generalization_level=GeneralizationLevel.STUDY_BOUND,
        testability="Compare invalid trajectory rates under matched closed-system tests.",
        testability_provenance="generated_challenge",
        atom_ids=["atom:fixture"],
        support=[
            SupportSpan(
                segment_key="segment:fixture",
                quotation="Conservation constraints reduced invalid trajectories in the test.",
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
        ],
    )


def _repository(tmp_path: Path) -> V14WorkspaceRepository:
    storage = WorkspaceStorage(tmp_path / "working")
    repository = V14WorkspaceRepository(storage.db_path)
    repository.save_candidate(_candidate())
    return repository


def test_sound_principle_without_a_meta_match_is_preserved(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    result = FoundationGroundingService(repository, _Cloud([])).assess(
        _candidate(),
        _argument(),
        provider=_Provider(),  # type: ignore[arg-type]
    )
    assert result["verdict"] == "ungrounded_solid"
    assert (
        repository.candidate_detail(_candidate().candidate_id)["foundation_assessment"]["verdict"]
        == "ungrounded_solid"
    )


def test_compatible_meta_link_is_persisted_as_grounded(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    cloud = _Cloud(
        [
            {
                "id": "meta:physics:conservation-law",
                "title": "Conservation law",
                "claim": "Closed systems preserve conserved quantities.",
                "conditions": ["closed system"],
                "boundary": ["open systems"],
            }
        ]
    )
    result = FoundationGroundingService(repository, cloud).assess(
        _candidate(),
        _argument(),
        provider=_Provider(),  # type: ignore[arg-type]
    )
    assert result["verdict"] == "grounded"
    detail = repository.candidate_detail(_candidate().candidate_id)
    assert detail is not None
    assert detail["foundation_assessment"]["links"][0]["meta_principle_id"] == (
        "meta:physics:conservation-law"
    )


def test_provider_absence_never_turns_meta_similarity_into_rejection(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    cloud = _Cloud([{"id": "meta:physics:conservation-law", "title": "Conservation"}])
    result = FoundationGroundingService(repository, cloud).assess(
        _candidate(), _argument(), provider=None
    )
    assert result["verdict"] == "ambiguous"
    assert result["links"] == []
