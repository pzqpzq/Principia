from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, SecretStr, model_validator

from ..cloud import ResearchGoalRunRequest
from ..domain import (
    DomainModel,
    JobRecord,
    LiteratureRunLimits,
    VirtualPrincipleProposal,
)
from ..providers import ModelPolicy


class ErrorBody(DomainModel):
    code: str
    category: str
    message: str
    retryable: bool
    request_id: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(DomainModel):
    error: ErrorBody


class ProviderCredentialRequest(DomainModel):
    api_key: SecretStr = Field(min_length=8, max_length=8_192)


class WorkingDirectorySwitchRequest(DomainModel):
    path: str = Field(min_length=1, max_length=4_096)


class WorkingDirectoryResponse(DomainModel):
    working_directory: str
    workspace: str
    local_data: str
    principles: str
    package_library: str | None = None
    display_name: str
    switched: bool
    empty: bool


class ResearchProjectCreateRequest(DomainModel):
    title: str = Field(min_length=1, max_length=120)


class ResearchProjectUpdateRequest(DomainModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    archived: bool | None = None


class ResearchSessionCreateRequest(DomainModel):
    run: ResearchGoalRunRequest
    title: str = Field(default="", max_length=160)
    project_id: str | None = None


class ResearchSessionUpdateRequest(DomainModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    project_id: str | None = None
    archived: bool | None = None
    expected_revision: int | None = Field(default=None, ge=1)


class ResearchGraphMutationRequest(DomainModel):
    expected_revision: int = Field(ge=0)
    operations: list[dict[str, Any]] = Field(min_length=1, max_length=250)


class ResearchArtifactCreateRequest(DomainModel):
    kind: Literal["virtual_principle", "virtual_connection"]
    payload: dict[str, Any]


class LibrarySummaryResponse(DomainModel):
    research_goal_count: int
    source_count: int
    document_count: int
    principle_count: int
    needs_revalidation_count: int
    quarantined_count: int
    evidence_link_count: int
    area_count: int
    label: str
    principle_contract: str


class LibraryCollectionItem(DomainModel):
    collection_id: str
    kind: Literal["research_goal", "area", "source"]
    title: str
    area: str
    source_id: str
    status: str
    updated_at: str
    source_name: str
    principle_count: int
    needs_revalidation_count: int
    quarantined_count: int
    work_count: int
    evidence_count: int
    display_location: str = ""
    overlapping_view: bool


class LibraryCollectionsResponse(DomainModel):
    kind: Literal["research_goal", "area", "source"]
    items: list[LibraryCollectionItem]
    explanation: str


class CollectionEditRequest(DomainModel):
    title: str = Field(min_length=1, max_length=400)


class CandidateDisplayEditRequest(DomainModel):
    title: str = Field(min_length=3, max_length=240)


class LocalSourceResponse(DomainModel):
    source_id: str
    portable_uri: str
    display_name: str
    status: str
    source_kind: str
    revision: int
    display_location: str
    created_at: str
    updated_at: str
    document_count: int
    full_text_count: int = 0
    abstract_only_count: int = 0
    pdf_count: int = 0
    text_full_text_count: int = 0
    extractable_count: int
    principle_count: int
    canonical_source_id: str = ""


class LocalSourcesResponse(DomainModel):
    sources: list[LocalSourceResponse]


class JobListResponse(DomainModel):
    items: list[JobRecord]


class SourceDocumentSummary(DomainModel):
    document_id: str
    source_id: str
    work_id: str
    portable_relative_uri: str
    content_sha256: str
    content_byte_size: int = Field(ge=0)
    parse_status: str
    extraction_eligible: bool
    extraction_status: Literal["not_started", "processing", "processed", "failed"]
    extraction_attempt_count: int = Field(ge=0)
    principle_count: int
    last_indexed_revision: int
    updated_at: str
    title: str
    year: int | None = None
    authors: list[str] = Field(default_factory=list)
    abstract_available: bool
    content_representation: Literal["pdf", "full_text", "abstract", "other"]


class SourceDocumentPage(DomainModel):
    items: list[SourceDocumentSummary]
    total: int
    next_cursor: str | None = None


class GraphNodeResponse(DomainModel):
    id: str
    entity_type: Literal["principle"]
    node_type: Literal["local_candidate", "global_capsule", "ghost_principle", "scenario_principle"]
    title: str
    claim: str
    area: str
    source: Literal["local", "global", "ghost", "scenario"]
    assessment: str
    maturity: str
    version: int
    source_count: int
    quality_state: str = ""
    ghost: bool
    install_action: bool


class GraphEdgeResponse(DomainModel):
    id: str
    source: str
    target: str
    type: str
    edge_class: Literal["scientific", "derived", "scenario"]
    provenance: str
    label: str
    strength: float | None = None
    shared_work_count: int | None = None


class GraphResponse(DomainModel):
    node_semantics: Literal["principle"]
    selection_policy: Literal["overview-v2"]
    scope: Literal["local", "global", "combined"]
    collection_id: str
    shown_count: int
    total_count: int
    explanation: str
    graph_digest: str
    nodes: list[GraphNodeResponse]
    edges: list[GraphEdgeResponse]
    truncated: bool
    soft_limit_exceeded: bool
    include_shared_evidence: bool
    seed_id: str | None = None
    depth: int | None = None
    limit: int | None = None
    area: str = ""
    goal_id: str = ""
    source_id: str = ""
    total_candidates: int = 0
    total_global_principles: int = 0
    recent_goals: list[LibraryCollectionItem] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)


class RelatedPrinciplePreview(DomainModel):
    principle_id: str
    title: str
    relation_type: str
    orientation: Literal["incoming", "outgoing"]


class PrincipleCardResponse(DomainModel):
    id: str
    source: Literal["local", "global", "both"]
    title: str
    claim: str
    claim_type: str
    applicability: str
    area_labels: list[str]
    evidence_status: Literal[
        "checks_passed", "checking", "held_back", "update_required", "archived"
    ]
    human_review_status: Literal["pending", "reviewed", "rejected"]
    evidence_scope: Literal["one_work", "multiple_works"]
    supporting_work_count: int = Field(ge=0)
    evidence_anchor_count: int = Field(ge=0)
    supporting_citation_count: int = Field(default=0, ge=0)
    citation_data_available: bool = False
    evidence_types: list[str]
    boundary_basis: str
    test_basis: str
    context_relevance: str
    updated_at: str
    reliability_score: float | None = Field(default=None, ge=0, le=100)
    influence_score: float | None = Field(default=None, ge=0, le=100)
    distinct_neighbor_count: int = Field(ge=0)
    incoming_support_count: int = Field(ge=0)
    incoming_contradict_count: int = Field(ge=0)
    validated_relation_count: int = Field(default=0, ge=0)
    related_principles: list[RelatedPrinciplePreview] = Field(default_factory=list)
    metric_revision: int | None = None
    virtual: bool = False


class PrincipleCardPage(DomainModel):
    items: list[PrincipleCardResponse]
    next_cursor: str | None = None
    total: int = Field(ge=0)
    facets: dict[str, Any]
    sort_explanation: str
    metric_status: dict[str, Any]
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=24, ge=1, le=100)
    page_count: int = Field(default=0, ge=0)


class PrincipleRelationResponse(DomainModel):
    relation_id: str
    source_principle_id: str
    target_principle_id: str
    relation_type: str
    direction: str
    rationale: str
    validation_state: Literal["validated"]
    evidence_digest: str
    related_principle_id: str
    related_title: str
    orientation: Literal["incoming", "outgoing"]


class PrincipleRelationsResponse(DomainModel):
    principle_id: str
    items: list[PrincipleRelationResponse]
    explanation: str


class PrincipleGraphEdgeResponse(DomainModel):
    relation_id: str
    source: str
    target: str
    relation_type: str
    direction: str
    rationale: str
    edge_class: Literal["validated", "shared_evidence", "semantic_affinity"] = "validated"
    strength: Literal["strong", "moderate", "weak"] | None = None
    shared_work_count: int = Field(default=0, ge=0)


class PrincipleGraphViewResponse(DomainModel):
    nodes: list[PrincipleCardResponse]
    edges: list[PrincipleGraphEdgeResponse]
    shown_count: int = Field(ge=0)
    total_count: int = Field(ge=0)
    truncated: bool
    maximum_nodes: int = Field(ge=1, le=500)
    explanation: str
    edge_counts: dict[str, int] = Field(default_factory=dict)


class PotentialRelationsRequest(DomainModel):
    principle_ids: list[str] = Field(min_length=2, max_length=20)

    @model_validator(mode="after")
    def unique_principles(self) -> PotentialRelationsRequest:
        if len(set(self.principle_ids)) != len(self.principle_ids):
            raise ValueError("Select each Principle only once")
        return self


class VirtualPrincipleGenerateRequest(DomainModel):
    principle_ids: list[str] = Field(min_length=2, max_length=20)
    provider_profile_id: str = Field(default="siliconflow", min_length=2, max_length=80)
    model: str = Field(min_length=2, max_length=200)
    egress_confirmed: bool = False
    requested_count: int = Field(default=3, ge=1, le=5)
    research_direction: str = Field(default="", max_length=1_000)

    @model_validator(mode="after")
    def unique_principles(self) -> VirtualPrincipleGenerateRequest:
        if len(set(self.principle_ids)) != len(self.principle_ids):
            raise ValueError("Select each Principle only once")
        if not self.egress_confirmed:
            raise ValueError("Confirm remote analysis of the selected Principle text")
        return self


class GeneratedVirtualPrinciple(DomainModel):
    virtual_id: str
    proposal: VirtualPrincipleProposal


class VirtualPrincipleGenerationResponse(DomainModel):
    items: list[GeneratedVirtualPrinciple]
    cross_principle_map: list[str]
    provider: str
    model: str
    trace: dict[str, Any]
    disclosure: str


class VirtualPrincipleSaveRequest(DomainModel):
    proposal: VirtualPrincipleProposal
    provider: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=200)
    trace: dict[str, Any] = Field(default_factory=dict)


class PotentialRelationResponse(DomainModel):
    relation_id: str
    source: str
    target: str
    relation_type: Literal[
        "potential_support",
        "potential_contradiction",
        "potential_refinement",
        "potential_analogy",
        "relationship_unclear",
    ]
    strength: Literal["strong", "moderate", "weak"]
    rationale: str
    shared_concepts: list[str]
    status: Literal["virtual_unvalidated"] = "virtual_unvalidated"
    persisted: Literal[False] = False
    affects_metrics: Literal[False] = False


class PotentialRelationsResponse(DomainModel):
    items: list[PotentialRelationResponse]
    analyzed_pair_count: int = Field(ge=0, le=190)
    skipped_validated_pair_count: int = Field(ge=0, le=190)
    explanation: str


class CatalogRefreshRequest(DomainModel):
    path: str


class AreaVersionRequest(DomainModel):
    version: str | None = None


class PinRequest(DomainModel):
    version: str
    pinned: bool = True


class SourceRegistrationRequest(DomainModel):
    path: str


class ManagedSourceRequest(DomainModel):
    name: str = Field(min_length=1, max_length=160)
    goal: str = Field(default="", max_length=4000)
    area: str = Field(default="", pattern=r"^(?:|[a-z0-9][a-z0-9-]+)$")
    parent: str | None = None


class SourceImportRequest(DomainModel):
    paths: list[str] = Field(min_length=1, max_length=100)


class SourceLocationDisclosureRequest(DomainModel):
    source_ids: list[str] = Field(min_length=1, max_length=100)


class SourceLocationDisclosure(DomainModel):
    source_id: str
    absolute_path: str
    available: bool
    readable: bool
    writable: bool


class DiscoveryRequest(DomainModel):
    source_id: str
    goal: str = Field(min_length=1, max_length=4000)
    area: str = Field(pattern=r"^[a-z0-9][a-z0-9-]+$")
    policy: ModelPolicy


class LiteratureSearchRequest(DomainModel):
    query: str = Field(default="", max_length=4000)
    # Deprecated request aliases retained for v1.4.0-rc compatibility.  The
    # production client sends only `query` and never constrains search by area.
    goal: str = Field(default="", max_length=4000)
    area: str = Field(default="", max_length=80)
    target_count: int = Field(default=20, ge=1, le=50)
    semantic_ranking: bool = True
    source_id: str = Field(default="", max_length=160)

    @model_validator(mode="after")
    def require_query(self) -> LiteratureSearchRequest:
        resolved = " ".join((self.query or self.goal).split())
        if len(resolved) < 8:
            raise ValueError("literature search requires a specific research question")
        object.__setattr__(self, "query", resolved)
        return self


class LiteratureSelectionRequest(DomainModel):
    work_ids: list[str] = Field(min_length=1, max_length=50)


class LiteratureDiscoveryRequest(DomainModel):
    provider_profile_id: str = "siliconflow"
    policy: Literal["remote", "no_llm"] = "remote"
    model: str = Field(
        default="deepseek-ai/DeepSeek-V4-Flash",
        min_length=2,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/+\-]{1,199}$",
    )
    egress_confirmed: bool = False
    limits: LiteratureRunLimits = Field(default_factory=LiteratureRunLimits)


class LiteratureAcquisitionRequest(DomainModel):
    source_id: str | None = Field(default=None, min_length=1, max_length=160)
    folder_name: str | None = Field(default=None, min_length=1, max_length=120)
    work_ids: list[str] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def choose_destination(self) -> LiteratureAcquisitionRequest:
        if bool(self.source_id) == bool(self.folder_name):
            raise ValueError("provide exactly one of source_id or folder_name")
        return self


class StorageLayoutDisclosureResponse(DomainModel):
    layout: Literal["working_directory", "legacy_workspace"]
    working_directory: str
    workspace: str
    local_data: str
    principles: str
    raw_data_removable: bool


class StorageLayoutRevealRequest(DomainModel):
    target: Literal["working_directory", "workspace", "local_data", "principles"]


class LocalExtractionContext(DomainModel):
    research_goal_id: str | None = Field(default=None, max_length=160)
    research_focus: str | None = Field(default=None, max_length=4000)


class AreaSuggestionCreateRequest(DomainModel):
    area: str = Field(pattern=r"^[a-z0-9][a-z0-9-]+$")
    rationale: str = Field(default="User suggestion", max_length=500)


class AreaSuggestionEditRequest(DomainModel):
    new_area: str = Field(pattern=r"^[a-z0-9][a-z0-9-]+$")
    rationale: str = Field(default="User edit", max_length=500)


class LocalExtractionRequest(DomainModel):
    source_id: str = Field(min_length=1, max_length=160)
    document_ids: list[str] = Field(default_factory=list, max_length=500)
    selection_mode: Literal["exact", "all"] = "exact"
    source_revision: int = Field(ge=1)
    context: LocalExtractionContext = Field(default_factory=LocalExtractionContext)
    # Deprecated flat fields are accepted for existing CLI/Python clients.
    goal_id: str = Field(default="", max_length=160)
    goal: str = Field(default="", max_length=4000)
    area: str = Field(default="", pattern=r"^(?:|[a-z0-9][a-z0-9-]+)$")
    provider_profile_id: str = "siliconflow"
    model: str = Field(
        default="deepseek-ai/DeepSeek-V4-Flash",
        min_length=2,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/+\-]{1,199}$",
    )
    policy: Literal["remote", "no_llm"] = "remote"
    egress_confirmed: bool = False
    limits: LiteratureRunLimits = Field(default_factory=LiteratureRunLimits)
    quality_policy: Literal["scientific-principle-v2"] = "scientific-principle-v2"


class ScenarioCreateRequest(DomainModel):
    name: str = Field(min_length=1, max_length=200)
    parent_scenario_id: str | None = None


class ScenarioEventRequest(DomainModel):
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
