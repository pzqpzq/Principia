from __future__ import annotations

import re
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..models import utc_now

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
PRINCIPLE_ID_PATTERN = re.compile(r"^prn:[a-z0-9][a-z0-9-]{1,62}:[0-9A-HJKMNP-TV-Z]{26}$")


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class PrincipleKind(str, Enum):
    THEOREM = "theorem"
    MECHANISTIC = "mechanistic"
    EMPIRICAL = "empirical"
    HEURISTIC = "heuristic"
    HYPOTHESIS = "hypothesis"


class PrincipleMaturity(str, Enum):
    SUPPORTED = "supported"
    REPLICATED = "replicated"
    ESTABLISHED = "established"
    CONTESTED = "contested"
    RETIRED = "retired"


class RelationType(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    REFINES = "refines"
    GENERALIZES = "generalizes"
    SPECIALIZES = "specializes"
    DEPENDS_ON = "depends_on"
    ANALOGOUS_TO = "analogous_to"
    MOTIVATES = "motivates"


class TraceOperation(str, Enum):
    IMPORT = "import"
    EXTRACT = "extract"
    CHALLENGE = "challenge"
    MAP = "map"
    REVIEW = "review"
    EDIT = "edit"
    MERGE = "merge"
    PROMOTE = "promote"
    RETIRE = "retire"


class QualityAssessment(DomainModel):
    grade: Literal["A", "B", "C", "D"]
    validity: float = Field(ge=0, le=1)
    reproducibility: float = Field(ge=0, le=1)
    evidence_strength: float = Field(ge=0, le=1)
    generality: float = Field(ge=0, le=1)
    usefulness: float = Field(ge=0, le=1)
    assessed_by: str = Field(min_length=1)
    assessed_at: str = Field(default_factory=utc_now)


class PrincipleScope(DomainModel):
    statement: str = Field(min_length=1)
    conditions: list[str] = Field(default_factory=list, max_length=20)
    exclusions: list[str] = Field(default_factory=list, max_length=20)
    populations: list[str] = Field(default_factory=list, max_length=20)


class WorkReference(DomainModel):
    work_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    url: str = ""
    doi: str = ""
    role: Literal["evidence", "proof", "falsifier", "context"] = "evidence"
    public: bool = True


class PrincipleRelation(DomainModel):
    relation_type: RelationType
    target_principle_id: str = Field(min_length=1)
    target_area: str | None = None
    minimum_package_version: str | None = None
    rationale: str = ""
    strength: float = Field(default=1.0, ge=0, le=1)


class GenerationTrace(DomainModel):
    event_id: str = Field(min_length=1)
    operation: TraceOperation
    actor: str = Field(min_length=1)
    provider: str = ""
    model: str = ""
    prompt_template: str = ""
    prompt_sha256: str = ""
    input_sha256: str = ""
    output_sha256: str = ""
    run_id: str = ""
    latency_ms: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    retries: int = Field(default=0, ge=0, le=2)
    created_at: str = Field(default_factory=utc_now)

    @field_validator("prompt_sha256", "input_sha256", "output_sha256")
    @classmethod
    def valid_optional_digest(cls, value: str) -> str:
        value = value.strip().lower()
        if value and not SHA256_PATTERN.fullmatch(value):
            raise ValueError("digest must be a lowercase SHA-256 value")
        return value


class CandidatePrinciple(DomainModel):
    candidate_id: str = Field(min_length=1)
    area: str = Field(min_length=2, max_length=63, pattern=r"^[a-z0-9][a-z0-9-]+$")
    title: str = Field(min_length=1, max_length=240)
    claim: str = Field(min_length=1)
    kind: PrincipleKind
    scope: PrincipleScope
    falsifier: str = ""
    source_references: list[WorkReference] = Field(default_factory=list)
    relations: list[PrincipleRelation] = Field(default_factory=list)
    generation_trace: list[GenerationTrace] = Field(default_factory=list)
    assessment_status: Literal["unassessed", "reviewed", "rejected"] = "unassessed"
    raw_legacy_payload: dict[str, Any] | None = None
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)


class PrincipleCapsule(DomainModel):
    principle_id: str
    area: str = Field(min_length=2, max_length=63, pattern=r"^[a-z0-9][a-z0-9-]+$")
    version: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=240)
    claim: str = Field(min_length=1)
    kind: PrincipleKind
    maturity: PrincipleMaturity
    scope: PrincipleScope
    quality: QualityAssessment
    falsifier: str = Field(min_length=1)
    source_references: list[WorkReference] = Field(min_length=1, max_length=12)
    relations: list[PrincipleRelation] = Field(default_factory=list, max_length=32)
    generation_trace: list[GenerationTrace] = Field(min_length=1, max_length=32)
    tags: list[str] = Field(default_factory=list, max_length=20)
    source_count: int = Field(ge=1)
    relation_count: int = Field(ge=0)
    trace_count: int = Field(ge=1)
    status: Literal["active", "retired"] = "active"
    content_digest: str = ""
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)

    @field_validator("principle_id")
    @classmethod
    def valid_principle_id(cls, value: str) -> str:
        if not PRINCIPLE_ID_PATTERN.fullmatch(value):
            raise ValueError("principle_id must use prn:<area>:<ULID>")
        return value

    @field_validator("content_digest")
    @classmethod
    def valid_content_digest(cls, value: str) -> str:
        value = value.strip().lower()
        if value and not SHA256_PATTERN.fullmatch(value):
            raise ValueError("content_digest must be a lowercase SHA-256 value")
        return value

    @model_validator(mode="after")
    def complete_projection_counts(self) -> PrincipleCapsule:
        if self.source_count < len(self.source_references):
            raise ValueError("source_count cannot be smaller than its projection")
        if self.relation_count < len(self.relations):
            raise ValueError("relation_count cannot be smaller than its projection")
        if self.trace_count < len(self.generation_trace):
            raise ValueError("trace_count cannot be smaller than its projection")
        if self.maturity is PrincipleMaturity.RETIRED and self.status != "retired":
            raise ValueError("retired maturity requires retired status")
        return self


class AreaManifest(DomainModel):
    schema_version: Literal["area-manifest-v1"] = "area-manifest-v1"
    area: str = Field(min_length=2, max_length=63, pattern=r"^[a-z0-9][a-z0-9-]+$")
    display_name: str = Field(min_length=1)
    package_version: str = Field(pattern=r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
    framework_min_version: str = "1.4.0"
    framework_max_version: str = "1.x"
    principle_count: int = Field(ge=0)
    revision_count: int = Field(ge=0)
    relation_count: int = Field(ge=0)
    work_count: int = Field(ge=0)
    content_digest: str
    area_sqlite_sha256: str
    builder_version: str
    python_version: str
    sqlite_version: str
    content_class: Literal["reviewed_capsules", "unassessed_candidates"] = "reviewed_capsules"
    source_text_included: Literal[False] = False
    immutable: Literal[True] = True
    created_at: str = Field(default_factory=utc_now)

    @field_validator("content_digest", "area_sqlite_sha256")
    @classmethod
    def valid_digest(cls, value: str) -> str:
        value = value.strip().lower()
        if not SHA256_PATTERN.fullmatch(value):
            raise ValueError("digest must be a lowercase SHA-256 value")
        return value


class CatalogEntry(DomainModel):
    schema_version: Literal["catalog-entry-v1"] = "catalog-entry-v1"
    area: str
    display_name: str
    package_version: str
    artifact_url: str
    artifact_sha256: str
    artifact_bytes: int = Field(gt=0)
    content_digest: str
    principle_count: int = Field(ge=0)
    relation_count: int = Field(ge=0)
    released_at: str
    content_class: Literal["reviewed_capsules", "unassessed_candidates"] = "reviewed_capsules"
    source_text_included: Literal[False] = False

    @field_validator("artifact_sha256", "content_digest")
    @classmethod
    def valid_catalog_digest(cls, value: str) -> str:
        value = value.strip().lower()
        if not SHA256_PATTERN.fullmatch(value):
            raise ValueError("digest must be a lowercase SHA-256 value")
        return value


class ChangesetOperation(DomainModel):
    operation: Literal["add", "update", "retire"]
    principle_id: str
    expected_version: int | None = Field(default=None, ge=1)
    proposed: PrincipleCapsule


class PublicationChangeset(DomainModel):
    schema_version: Literal["publication-changeset-v1"] = "publication-changeset-v1"
    changeset_id: str
    area: str
    base_package_version: str
    proposed_package_version: str
    expected_content_digest: str
    goal: str
    operations: list[ChangesetOperation] = Field(min_length=1)
    required_approvals: int = Field(default=1, ge=1)
    approvals: list[str] = Field(default_factory=list)
    generator_trace: list[GenerationTrace] = Field(default_factory=list)
    validation_results: dict[str, bool] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now)

    @field_validator("expected_content_digest")
    @classmethod
    def valid_expected_digest(cls, value: str) -> str:
        value = value.strip().lower()
        if not SHA256_PATTERN.fullmatch(value):
            raise ValueError("expected_content_digest must be SHA-256")
        return value


class JobRecord(DomainModel):
    job_id: str
    kind: str
    state: Literal[
        "queued",
        "running",
        "pausing",
        "paused",
        "resuming",
        "recovering",
        "cancelling",
        "cancelled",
        "succeeded",
        "failed",
        "interrupted",
    ] = "queued"
    stage: str = "queued"
    progress: float = Field(default=0, ge=0, le=1)
    provider: str = ""
    model: str = ""
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    checkpoint: dict[str, Any] | None = None
    completed_units: int = Field(default=0, ge=0)
    total_units: int = Field(default=0, ge=0)
    elapsed_seconds: float = Field(default=0, ge=0)
    eta_seconds: float | None = Field(default=None, ge=0)
    last_activity_at: str = ""
    status_message: str = ""
    retry_after_seconds: float | None = Field(default=None, ge=0)
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)


class ScenarioEvent(DomainModel):
    event_id: str
    scenario_id: str
    sequence: int = Field(ge=1)
    event_type: Literal[
        "set_maturity",
        "set_support_pressure",
        "pin_version",
        "add_virtual_principle",
        "set_scope",
        "add_relation",
        "disable_relation",
    ]
    payload: dict[str, Any]
    created_at: str = Field(default_factory=utc_now)


class ScenarioRecord(DomainModel):
    scenario_id: str
    name: str = Field(min_length=1)
    base_content_digest: str
    parent_scenario_id: str | None = None
    status: Literal["active", "discarded"] = "active"
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)
