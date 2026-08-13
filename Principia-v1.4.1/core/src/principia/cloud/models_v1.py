from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from ..domain.models import PRINCIPLE_ID_PATTERN, SHA256_PATTERN, DomainModel
from ..models import utc_now


class AuthorAffiliation(DomainModel):
    author: str = Field(min_length=1, max_length=300)
    institutions: list[str] = Field(default_factory=list, max_length=30)


class WorkAvailability(DomainModel):
    status: Literal["available", "unavailable", "unknown", "probe_failed"] = "unknown"
    full_text_url: str = ""
    license: str = ""
    page_count: int | None = Field(default=None, ge=1, le=100_000)
    pdf_bytes: int | None = Field(default=None, ge=1, le=1024 * 1024 * 1024)
    checked_at: str = ""
    basis: str = ""


class WorkRevision(DomainModel):
    schema_version: Literal["global-work-v1"] = "global-work-v1"
    work_id: str = Field(min_length=3, max_length=200)
    revision: int = Field(default=1, ge=1)
    title: str = Field(min_length=1, max_length=1_000)
    abstract: str = Field(default="", max_length=100_000)
    authors: list[str] = Field(default_factory=list, max_length=200)
    affiliations: list[AuthorAffiliation] = Field(default_factory=list, max_length=200)
    institutions: list[str] = Field(default_factory=list, max_length=300)
    venue: str = Field(default="", max_length=500)
    publication_date: str = ""
    year: int | None = Field(default=None, ge=1000, le=3000)
    doi: str = ""
    arxiv_id: str = ""
    pmid: str = ""
    pmcid: str = ""
    openalex_id: str = ""
    semantic_scholar_id: str = ""
    landing_url: str = ""
    source_urls: list[str] = Field(default_factory=list, max_length=50)
    availability: WorkAvailability = Field(default_factory=WorkAvailability)
    citation_count: int | None = Field(default=None, ge=0)
    content_digest: str = ""
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)

    @field_validator("landing_url")
    @classmethod
    def public_landing_url(cls, value: str) -> str:
        if value and not value.startswith("https://"):
            raise ValueError("cloud links must use public HTTPS URLs")
        return value

    @field_validator("source_urls")
    @classmethod
    def public_source_urls(cls, values: list[str]) -> list[str]:
        if any(not value.startswith("https://") for value in values):
            raise ValueError("cloud source links must use public HTTPS URLs")
        return list(dict.fromkeys(values))

    @field_validator("content_digest")
    @classmethod
    def digest(cls, value: str) -> str:
        if value and not SHA256_PATTERN.fullmatch(value):
            raise ValueError("content_digest must be lowercase SHA-256")
        return value


class PrincipleRevision(DomainModel):
    schema_version: Literal["global-principle-v1"] = "global-principle-v1"
    principle_id: str
    revision: int = Field(ge=1)
    area: str = Field(min_length=2, max_length=63, pattern=r"^[a-z0-9][a-z0-9-]+$")
    title: str = Field(min_length=1, max_length=240)
    claim: str = Field(min_length=1, max_length=10_000)
    kind: Literal["theorem", "mechanistic", "empirical", "heuristic", "hypothesis"]
    maturity: Literal["unassessed", "supported", "replicated", "established", "contested", "retired"]
    scope: dict[str, Any]
    falsifier: str = Field(min_length=1, max_length=10_000)
    quality: dict[str, Any]
    tags: list[str] = Field(default_factory=list, max_length=100)
    status: Literal["active", "retired"] = "active"
    review_status: Literal["reviewed", "unassessed"] = "reviewed"
    generation_trace: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    review_actor: str = ""
    reviewed_at: str = ""
    legacy_ids: list[str] = Field(default_factory=list, max_length=20)
    migration_provenance: dict[str, Any] = Field(default_factory=dict)
    content_digest: str = ""
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)

    @field_validator("principle_id")
    @classmethod
    def valid_id(cls, value: str) -> str:
        if not PRINCIPLE_ID_PATTERN.fullmatch(value):
            raise ValueError("principle_id must use prn:<area>:<ULID>")
        return value

    @field_validator("content_digest")
    @classmethod
    def digest(cls, value: str) -> str:
        if value and not SHA256_PATTERN.fullmatch(value):
            raise ValueError("content_digest must be lowercase SHA-256")
        return value


class PrincipleWorkLink(DomainModel):
    schema_version: Literal["global-principle-work-v1"] = "global-principle-work-v1"
    principle_id: str
    principle_revision: int = Field(ge=1)
    work_id: str = Field(min_length=3, max_length=200)
    role: Literal["evidence", "proof", "falsifier", "context"] = "evidence"
    page: int | None = Field(default=None, ge=1, le=100_000)
    section: str = Field(default="", max_length=500)
    evidence_digest: str = ""

    @field_validator("evidence_digest")
    @classmethod
    def digest(cls, value: str) -> str:
        if value and not SHA256_PATTERN.fullmatch(value):
            raise ValueError("evidence_digest must be lowercase SHA-256")
        return value


class RelationRevision(DomainModel):
    schema_version: Literal["global-relation-v1"] = "global-relation-v1"
    relation_id: str = Field(min_length=3, max_length=300)
    revision: int = Field(default=1, ge=1)
    source_principle_id: str
    target_principle_id: str
    relation_type: str = Field(min_length=1, max_length=100)
    rationale: str = Field(default="", max_length=10_000)
    strength: float = Field(default=1.0, ge=0, le=1)
    status: Literal["active", "retired"] = "active"
    unresolved_target: bool = False
    migration_provenance: dict[str, Any] = Field(default_factory=dict)
    content_digest: str = ""
    created_at: str = Field(default_factory=utc_now)


class EmbeddingContract(DomainModel):
    schema_version: Literal["global-embedding-contract-v1"] = "global-embedding-contract-v1"
    contract_id: Literal["qwen3-embedding-4b-1024-v1"] = "qwen3-embedding-4b-1024-v1"
    model: str = "Qwen/Qwen3-Embedding-4B"
    dimensions: Literal[1024] = 1024
    dtype: Literal["float16"] = "float16"
    normalized: Literal[True] = True
    work_template: str = "title: {title}\nabstract: {abstract}\nvenue: {venue}"
    principle_template: str = "title: {title}\nclaim: {claim}\nscope: {scope}\ntags: {tags}"


class CloudManifest(DomainModel):
    schema_version: Literal["principia-global-manifest-v1"] = "principia-global-manifest-v1"
    release_id: str = Field(min_length=1, max_length=200)
    commit_sha: str = ""
    content_digest: str
    snapshot_sha256: str = ""
    snapshot_bytes: int = Field(default=0, ge=0)
    work_count: int = Field(ge=0)
    principle_count: int = Field(ge=0)
    principle_revision_count: int = Field(ge=0)
    principle_work_count: int = Field(ge=0)
    relation_count: int = Field(ge=0)
    embedding_contract: str = "qwen3-embedding-4b-1024-v1"
    vector_dimensions: int = Field(default=1024, ge=1)
    vectors_complete: bool = False
    created_at: str = Field(default_factory=utc_now)

    @field_validator("content_digest", "snapshot_sha256")
    @classmethod
    def optional_digest(cls, value: str) -> str:
        if value and not SHA256_PATTERN.fullmatch(value):
            raise ValueError("manifest digest must be lowercase SHA-256")
        return value


class CloudDeltaManifest(DomainModel):
    schema_version: Literal["principia-global-delta-v1"] = "principia-global-delta-v1"
    base_release_id: str
    target_release_id: str
    base_content_digest: str
    target_content_digest: str
    target_commit_sha: str = ""
    target_created_at: str
    target_snapshot_sha256: str = ""
    work_count: int = Field(ge=0)
    principle_count: int = Field(ge=0)
    principle_revision_count: int = Field(ge=0)
    principle_work_count: int = Field(ge=0)
    relation_count: int = Field(ge=0)
    embedding_contract: str = "qwen3-embedding-4b-1024-v1"
    vector_dimensions: int = 1024
    vectors_complete: bool = False
    change_count: int = Field(ge=0)
    created_at: str = Field(default_factory=utc_now)

    @field_validator("base_content_digest", "target_content_digest", "target_snapshot_sha256")
    @classmethod
    def delta_digest(cls, value: str) -> str:
        if value and not SHA256_PATTERN.fullmatch(value):
            raise ValueError("delta digest must be lowercase SHA-256")
        return value


class CloudSearchRequest(DomainModel):
    entity: Literal["paper", "principle", "all"] = "principle"
    query: str = Field(default="", max_length=4_000)
    year_from: int | None = Field(default=None, ge=1000, le=3000)
    year_to: int | None = Field(default=None, ge=1000, le=3000)
    venues: list[str] = Field(default_factory=list, max_length=100)
    institutions: list[str] = Field(default_factory=list, max_length=100)
    areas: list[str] = Field(default_factory=list, max_length=100)
    full_text_status: Literal["", "available", "unavailable", "unknown", "probe_failed"] = ""
    page_min: int | None = Field(default=None, ge=1)
    page_max: int | None = Field(default=None, ge=1)
    pdf_bytes_min: int | None = Field(default=None, ge=1)
    pdf_bytes_max: int | None = Field(default=None, ge=1)
    cursor: str = ""
    limit: int = Field(default=50, ge=1, le=200)
    paper_cohort: int = Field(default=100, ge=1, le=500)

    @model_validator(mode="after")
    def ranges(self) -> CloudSearchRequest:
        for low, high, label in (
            (self.year_from, self.year_to, "year"),
            (self.page_min, self.page_max, "page"),
            (self.pdf_bytes_min, self.pdf_bytes_max, "PDF byte"),
        ):
            if low is not None and high is not None and low > high:
                raise ValueError(f"{label} minimum cannot exceed maximum")
        return self


class ResearchGoalRunRequest(DomainModel):
    goal: str = Field(min_length=8, max_length=4_000)
    source_ids: list[str] = Field(default_factory=list, max_length=100)
    include_global: bool = True
    include_online: bool = False
    provider_profile_id: str = "siliconflow"
    model: str = "deepseek-ai/DeepSeek-V4-Flash"
    local_limit: int = Field(default=20, ge=1, le=500)
    global_limit: int = Field(default=50, ge=1, le=200)


class ResearchGoalRun(DomainModel):
    schema_version: Literal["research-goal-run-v1"] = "research-goal-run-v1"
    run_id: str
    goal: str
    state: Literal[
        "queued", "running", "succeeded", "partial", "failed", "cancelled"
    ] = "queued"
    cloud_release_id: str = ""
    branches: dict[str, Any] = Field(default_factory=dict)
    result_counts: dict[str, int] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)


class AdminCampaignRequest(DomainModel):
    research_goal: str = Field(min_length=8, max_length=4_000)
    target_count: int = Field(default=50, ge=1, le=20_000)
    provider_profile_id: str = "siliconflow"
    model: str = "deepseek-ai/DeepSeek-V4-Flash"
    concurrency: int = Field(default=4, ge=4, le=8)


class AdminSelectionRequest(DomainModel):
    work_ids: list[str] = Field(min_length=1, max_length=20_000)


class AdminExtractRequest(DomainModel):
    retry: bool = False
    egress_confirmed: bool = False


class StagingDecisionRequest(DomainModel):
    decision: Literal["add", "update", "retire", "skip"]
    confirmed_ambiguous: bool = False


class BulkStagingDecisionRequest(DomainModel):
    stage_ids: list[str] = Field(min_length=1, max_length=20_000)
    decision: Literal["add", "update", "retire", "skip"]


class AdminSyncRequest(DomainModel):
    confirmation: str = Field(min_length=1, max_length=500)
    mode: Literal["dry_run", "github_pr"] = "dry_run"


class AdminStagedItem(DomainModel):
    schema_version: Literal["admin-staged-item-v1"] = "admin-staged-item-v1"
    stage_id: str
    campaign_id: str
    entity: Literal["work", "principle", "principle_work", "relation"]
    proposed: dict[str, Any]
    current: dict[str, Any] = Field(default_factory=dict)
    diff: dict[str, Any] = Field(default_factory=dict)
    match_kind: Literal["new", "exact", "strong_id", "semantic", "ambiguous"] = "new"
    match_reason: str = ""
    similarity: float = Field(default=0, ge=0, le=1)
    decision: Literal["", "add", "update", "retire", "skip"] = ""
    ambiguous_confirmed: bool = False
    expected_revision: int | None = Field(default=None, ge=1)
    expected_digest: str = ""
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)


class CloudSync(DomainModel):
    schema_version: Literal["cloud-sync-v1"] = "cloud-sync-v1"
    sync_id: str
    campaign_id: str
    state: Literal[
        "draft", "reviewed", "pr_creating", "checks_running", "auto_merge_queued",
        "merged", "release_building", "published", "needs_resolution", "failed", "cancelled"
    ] = "draft"
    base_release_id: str = ""
    base_commit_sha: str = ""
    base_manifest_digest: str = ""
    changeset_digest: str = ""
    pr_number: int | None = None
    pr_url: str = ""
    release_id: str = ""
    error: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)


_FORBIDDEN_KEYS = re.compile(
    r"(?:pdf|full[_-]?text|raw[_-]?text|quotation|excerpt|api[_-]?key|token|secret|password|local[_-]?path)$",
    re.IGNORECASE,
)


def reject_forbidden_cloud_fields(payload: Any, path: str = "$") -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if _FORBIDDEN_KEYS.search(str(key)) and value not in (None, "", [], {}):
                raise ValueError(f"forbidden cloud field at {path}.{key}")
            reject_forbidden_cloud_fields(value, f"{path}.{key}")
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            reject_forbidden_cloud_fields(value, f"{path}[{index}]")
    elif isinstance(payload, str):
        if payload.startswith(("file://", "/Users/", "/home/", "/private/", "/tmp/")):
            raise ValueError(f"private path is forbidden at {path}")
