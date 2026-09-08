from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from ..domain.models import PRINCIPLE_ID_PATTERN, SHA256_PATTERN, DomainModel
from ..models import utc_now
from .models_v1 import WorkRevision

META_PRINCIPLE_ID_PATTERN = re.compile(r"^meta:[a-z0-9][a-z0-9-]{1,62}:[a-z0-9][a-z0-9-]{1,159}$")
GLOBAL_PRINCIPLE_ID_PATTERN = re.compile(
    rf"(?:{PRINCIPLE_ID_PATTERN.pattern[1:-1]})|(?:{META_PRINCIPLE_ID_PATTERN.pattern[1:-1]})"
)

PrincipleClass = Literal["literature", "meta"]
FoundationVerdict = Literal["grounded", "ungrounded_solid", "ambiguous", "invalid"]
ReviewStatus = Literal["reviewed", "unassessed"]


class WorkRevisionV2(WorkRevision):
    schema_version: Literal["global-work-v2"] = "global-work-v2"
    status: Literal["active", "retired"] = "active"
    legacy_ids: list[str] = Field(default_factory=list, max_length=100)
    identifier_observations: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    migration_provenance: dict[str, Any] = Field(default_factory=dict)


class ReviewAttestation(DomainModel):
    actor: str = Field(min_length=1, max_length=300)
    reviewed_at: str = Field(min_length=1, max_length=100)
    basis: str = Field(min_length=1, max_length=1_000)
    source_review_status: str = Field(default="", max_length=100)
    trace_id: str = Field(default="", max_length=500)


class PrincipleRevisionV2(DomainModel):
    """Shared scientific record for literature Principles and Meta-Principles."""

    schema_version: Literal["global-principle-v2"] = "global-principle-v2"
    principle_id: str
    principle_class: PrincipleClass
    revision: int = Field(ge=1)
    area: str = Field(min_length=2, max_length=63, pattern=r"^[a-z0-9][a-z0-9-]+$")
    area_display: str = Field(default="", max_length=200)
    title: str = Field(min_length=1, max_length=500)
    claim: str = Field(min_length=1, max_length=20_000)
    argument: str = Field(min_length=1, max_length=50_000)
    interpretation: str = Field(default="", max_length=50_000)
    conditions: list[str] = Field(default_factory=list, max_length=100)
    boundary: list[str] = Field(default_factory=list, max_length=100)
    applications: list[str] = Field(default_factory=list, max_length=100)
    falsifier: str = Field(default="", max_length=20_000)
    kind: Literal["theorem", "mechanistic", "empirical", "heuristic", "hypothesis"]
    epistemic_type: str = Field(default="", max_length=500)
    maturity: Literal[
        "unassessed", "supported", "replicated", "established", "contested", "retired"
    ]
    stability: Literal["unknown", "low", "medium", "high"] = "unknown"
    validity_period: str = Field(default="", max_length=500)
    significance: dict[str, Any] = Field(default_factory=dict)
    recognition: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    scope: dict[str, Any] = Field(default_factory=dict)
    quality: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list, max_length=200)
    status: Literal["active", "retired"] = "active"
    review_status: ReviewStatus = "unassessed"
    review_attestation: ReviewAttestation | None = None
    generation_trace: list[dict[str, Any]] = Field(default_factory=list, max_length=200)
    legacy_ids: list[str] = Field(default_factory=list, max_length=100)
    migration_provenance: dict[str, Any] = Field(default_factory=dict)
    content_digest: str = ""
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)

    @field_validator("principle_id")
    @classmethod
    def valid_id(cls, value: str) -> str:
        if not GLOBAL_PRINCIPLE_ID_PATTERN.fullmatch(value):
            raise ValueError("principle_id must use prn:<area>:<ULID> or meta:<area>:<slug>")
        return value

    @field_validator("content_digest")
    @classmethod
    def digest(cls, value: str) -> str:
        if value and not SHA256_PATTERN.fullmatch(value):
            raise ValueError("content_digest must be lowercase SHA-256")
        return value

    @model_validator(mode="after")
    def class_matches_identifier(self) -> PrincipleRevisionV2:
        if self.principle_class == "meta" and not META_PRINCIPLE_ID_PATTERN.fullmatch(
            self.principle_id
        ):
            raise ValueError("Meta-Principles must preserve their meta:<area>:<slug> identity")
        if self.principle_class == "literature" and not PRINCIPLE_ID_PATTERN.fullmatch(
            self.principle_id
        ):
            raise ValueError("literature Principles must preserve their prn:<area>:<ULID> identity")
        if self.principle_class == "literature" and not self.falsifier.strip():
            raise ValueError("literature Principles require a falsifier or disproof criterion")
        if self.review_status == "reviewed" and self.review_attestation is None:
            raise ValueError("reviewed v2 Principles require an explicit review attestation")
        if self.maturity == "retired" and self.status != "retired":
            raise ValueError("retired maturity requires retired status")
        return self


class PrincipleWorkLinkV2(DomainModel):
    schema_version: Literal["global-principle-work-v2"] = "global-principle-work-v2"
    principle_id: str
    principle_revision: int = Field(ge=1)
    work_id: str = Field(min_length=3, max_length=200)
    role: Literal["evidence", "proof", "falsifier", "context"] = "evidence"
    role_detail: str = Field(default="", max_length=500)
    source_observations: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    page: int | None = Field(default=None, ge=1, le=100_000)
    section: str = Field(default="", max_length=500)
    evidence_digest: str = ""

    @field_validator("principle_id")
    @classmethod
    def valid_principle_id(cls, value: str) -> str:
        if not GLOBAL_PRINCIPLE_ID_PATTERN.fullmatch(value):
            raise ValueError("unknown v2 Principle identity")
        return value

    @field_validator("evidence_digest")
    @classmethod
    def digest(cls, value: str) -> str:
        if value and not SHA256_PATTERN.fullmatch(value):
            raise ValueError("evidence_digest must be lowercase SHA-256")
        return value


class FoundationLinkRevision(DomainModel):
    schema_version: Literal["global-foundation-link-v1"] = "global-foundation-link-v1"
    link_id: str = Field(min_length=3, max_length=300)
    revision: int = Field(default=1, ge=1)
    principle_id: str
    principle_revision: int = Field(ge=1)
    meta_principle_id: str
    meta_principle_revision: int = Field(ge=1)
    direction: Literal["meta_to_principle", "principle_to_meta"] = "meta_to_principle"
    relation_type: Literal[
        "specializes",
        "depends_on",
        "refines",
        "motivates",
        "generalizes",
        "analogous_to",
        "supports",
        "contradicts",
        "bounded_by",
        "contrasts_with",
        "approximates",
        "equivalent_to",
        "consistent_with",
    ]
    rationale: str = Field(min_length=1, max_length=20_000)
    condition_compatibility: str = Field(default="", max_length=10_000)
    variable_compatibility: str = Field(default="", max_length=10_000)
    scale_compatibility: str = Field(default="", max_length=10_000)
    confidence: float = Field(ge=0, le=1)
    status: Literal["active", "retired", "proposed"] = "proposed"
    review_status: ReviewStatus = "unassessed"
    review_attestation: ReviewAttestation | None = None
    generation_trace: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    content_digest: str = ""
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_endpoints(self) -> FoundationLinkRevision:
        if not PRINCIPLE_ID_PATTERN.fullmatch(self.principle_id):
            raise ValueError("foundation source must be a literature Principle")
        if not META_PRINCIPLE_ID_PATTERN.fullmatch(self.meta_principle_id):
            raise ValueError("foundation target must be a Meta-Principle")
        if self.review_status == "reviewed" and self.review_attestation is None:
            raise ValueError("reviewed foundation links require an attestation")
        return self


class FoundationAssessmentRevision(DomainModel):
    schema_version: Literal["global-foundation-assessment-v1"] = "global-foundation-assessment-v1"
    assessment_id: str = Field(min_length=3, max_length=300)
    revision: int = Field(default=1, ge=1)
    principle_id: str
    principle_revision: int = Field(ge=1)
    verdict: FoundationVerdict
    rationale: str = Field(min_length=1, max_length=20_000)
    foundation_link_ids: list[str] = Field(default_factory=list, max_length=4)
    frontier_candidate: bool = False
    review_status: ReviewStatus = "unassessed"
    review_attestation: ReviewAttestation | None = None
    generation_trace: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    content_digest: str = ""
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)

    @field_validator("principle_id")
    @classmethod
    def literature_only(cls, value: str) -> str:
        if not PRINCIPLE_ID_PATTERN.fullmatch(value):
            raise ValueError("only literature Principles receive foundation assessments")
        return value


class FoundationGapRevision(DomainModel):
    schema_version: Literal["global-foundation-gap-v1"] = "global-foundation-gap-v1"
    gap_id: str = Field(min_length=3, max_length=300)
    revision: int = Field(default=1, ge=1)
    principle_id: str = ""
    requested_target_id: str = ""
    area: str = Field(min_length=2, max_length=63, pattern=r"^[a-z0-9][a-z0-9-]+$")
    description: str = Field(min_length=1, max_length=20_000)
    rationale: str = Field(default="", max_length=20_000)
    status: Literal["open", "resolved", "retired"] = "open"
    source_trace: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)


class RelationRevisionV2(DomainModel):
    schema_version: Literal["global-relation-v2"] = "global-relation-v2"
    relation_id: str = Field(min_length=3, max_length=300)
    revision: int = Field(default=1, ge=1)
    source_principle_id: str
    target_principle_id: str
    relation_type: Literal[
        "specializes",
        "depends_on",
        "refines",
        "motivates",
        "generalizes",
        "analogous_to",
        "supports",
        "contradicts",
        "bounded_by",
        "contrasts_with",
        "approximates",
        "equivalent_to",
        "consistent_with",
    ]
    relation_role: Literal["foundation", "peer"] = "peer"
    rationale: str = Field(default="", max_length=20_000)
    strength: float | None = Field(default=None, ge=0, le=1)
    status: Literal["active", "retired", "proposed"] = "proposed"
    review_status: ReviewStatus = "unassessed"
    review_attestation: ReviewAttestation | None = None
    unresolved_target: bool = False
    migration_provenance: dict[str, Any] = Field(default_factory=dict)
    content_digest: str = ""
    created_at: str = Field(default_factory=utc_now)

    @field_validator("source_principle_id", "target_principle_id")
    @classmethod
    def valid_endpoint(cls, value: str) -> str:
        if not GLOBAL_PRINCIPLE_ID_PATTERN.fullmatch(value):
            raise ValueError("relation endpoints must reference a Global Principle")
        return value
