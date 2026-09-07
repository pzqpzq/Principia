from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from ..models import utc_now
from .models import SHA256_PATTERN, DomainModel

DataModality = Literal["table", "array", "signal", "image", "volume", "graph", "context"]
AssetStatus = Literal["analyzable", "metadata_only", "failed", "blocked"]
FindingStatus = Literal["supported_candidate", "inconclusive", "refuted", "held_back"]
NoveltyStatus = Literal[
    "not_assessed", "prior_art_found", "no_close_prior_art_found", "possibly_novel"
]


class DataAsset(DomainModel):
    asset_id: str
    study_id: str
    source_id: str
    portable_uri: str
    byte_sha256: str
    byte_size: int = Field(ge=0)
    format: str
    role: Literal["raw", "context", "metadata", "user_context"] = "raw"
    modality: DataModality
    mime_type: str = "application/octet-stream"
    adapter: str
    adapter_version: str = "1"
    status: AssetStatus
    warnings: list[str] = Field(default_factory=list, max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)

    @field_validator("byte_sha256")
    @classmethod
    def valid_digest(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not SHA256_PATTERN.fullmatch(normalized):
            raise ValueError("byte_sha256 must be a lowercase SHA-256 digest")
        return normalized


class DataView(DomainModel):
    view_id: str
    study_id: str
    asset_ids: list[str] = Field(min_length=1, max_length=10_000)
    kind: DataModality
    name: str
    dimensions: dict[str, int] = Field(default_factory=dict)
    variables: list[str] = Field(default_factory=list, max_length=5_000)
    units: dict[str, str] = Field(default_factory=dict)
    keys: list[str] = Field(default_factory=list, max_length=100)
    masks: list[str] = Field(default_factory=list, max_length=100)
    locator: dict[str, Any] = Field(default_factory=dict)
    profile: dict[str, Any] = Field(default_factory=dict)
    content_digest: str
    created_at: str = Field(default_factory=utc_now)

    @field_validator("content_digest")
    @classmethod
    def valid_digest(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not SHA256_PATTERN.fullmatch(normalized):
            raise ValueError("content_digest must be a lowercase SHA-256 digest")
        return normalized


class DatasetAlignment(DomainModel):
    alignment_id: str
    study_id: str
    source_view_id: str
    target_view_id: str
    relation: Literal[
        "shared_identifier", "series_member", "coordinate_alignment", "codebook", "context_for"
    ]
    source_keys: list[str] = Field(default_factory=list)
    target_keys: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    rationale: str


class DatasetGraph(DomainModel):
    study_id: str
    view_ids: list[str] = Field(default_factory=list)
    alignments: list[DatasetAlignment] = Field(default_factory=list)
    independent_unit: str = "unknown"
    split_strategy: Literal["group", "chronological", "spatial_block", "contiguous_epoch", "none"] = (
        "none"
    )
    semantics: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class StudyBlueprint(DomainModel):
    """Versioned, evidence-neutral interpretation compiled before analysis.

    A blueprint binds scientific meaning to concrete DataViews.  It may use
    bounded context documents to interpret a schema, but none of that context
    is promoted to computed evidence.  Low-confidence blueprints remain
    editable and force conservative/exploratory validation downstream.
    """

    study_id: str
    schema_version: Literal[
        "principia.study-blueprint/v1", "principia.study-blueprint/v2"
    ] = "principia.study-blueprint/v2"
    domain_candidates: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    scientific_objects: list[dict[str, Any]] = Field(default_factory=list, max_length=200)
    object_hierarchy: list[dict[str, Any]] = Field(default_factory=list, max_length=500)
    variable_bindings: list[dict[str, Any]] = Field(default_factory=list, max_length=5_000)
    target_bindings: list[dict[str, Any]] = Field(default_factory=list, max_length=1_000)
    input_bindings: list[dict[str, Any]] = Field(default_factory=list, max_length=5_000)
    nuisance_bindings: list[dict[str, Any]] = Field(default_factory=list, max_length=2_000)
    coordinate_bindings: list[dict[str, Any]] = Field(default_factory=list, max_length=1_000)
    mask_bindings: list[dict[str, Any]] = Field(default_factory=list, max_length=1_000)
    independent_units: list[dict[str, Any]] = Field(default_factory=list, max_length=200)
    joins: list[dict[str, Any]] = Field(default_factory=list, max_length=500)
    unit_bindings: list[dict[str, Any]] = Field(default_factory=list, max_length=2_000)
    missing_value_codes: list[dict[str, Any]] = Field(default_factory=list, max_length=500)
    split_candidates: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    prohibited_leakage_variables: list[dict[str, Any]] = Field(
        default_factory=list, max_length=2_000
    )
    semantic_resolution: dict[str, Any] = Field(default_factory=dict)
    edit_revision: int = Field(default=0, ge=0)
    context_excerpts: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    interpretation_summary: str = Field(default="", max_length=4_000)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    needs_user_confirmation: bool = True
    warnings: list[str] = Field(default_factory=list, max_length=100)
    blueprint_digest: str
    created_at: str = Field(default_factory=utc_now)

    @field_validator("blueprint_digest")
    @classmethod
    def valid_blueprint_digest(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not SHA256_PATTERN.fullmatch(normalized):
            raise ValueError("blueprint_digest must be a lowercase SHA-256 digest")
        return normalized


class StudyBlueprintV2(StudyBlueprint):
    """Role-complete scientific interpretation used by executable programs."""

    schema_version: Literal["principia.study-blueprint/v2"] = (
        "principia.study-blueprint/v2"
    )


class ExecutableHypothesis(DomainModel):
    """A model proposal compiled against immutable typed-view bindings.

    Prose alone is never executable.  The dispatcher accepts only hypotheses
    whose target, inputs, independent units, split strategy, and falsifier are
    bound to real blueprint records.
    """

    executable_hypothesis_id: str
    study_id: str
    hypothesis_id: str
    track: Literal["mechanism", "predictive_closure"]
    target_binding_ids: list[str] = Field(default_factory=list, max_length=1_000)
    input_binding_ids: list[str] = Field(default_factory=list, max_length=5_000)
    nuisance_binding_ids: list[str] = Field(default_factory=list, max_length=2_000)
    independent_unit_binding_ids: list[str] = Field(
        default_factory=list, max_length=1_000
    )
    split_strategy: Literal[
        "group", "chronological", "spatial_block", "contiguous_signal", "stratified_group"
    ]
    admissible_family_kinds: list[str] = Field(default_factory=list, max_length=100)
    falsifying_control: dict[str, Any]
    state: Literal["bound", "repaired", "rejected"]
    rejection_reasons: list[str] = Field(default_factory=list, max_length=100)
    binding_digest: str

    @field_validator("binding_digest")
    @classmethod
    def valid_binding_digest(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not SHA256_PATTERN.fullmatch(normalized):
            raise ValueError("binding_digest must be a lowercase SHA-256 digest")
        return normalized


class GateReceipt(DomainModel):
    """Evidence-bearing, reproducible decision for one scientific-law gate."""

    gate_id: str
    gate_contract_version: str = "principia.rule-gates/v2"
    metric: str
    comparison: Literal[
        "greater_than", "greater_or_equal", "less_than", "less_or_equal", "equal", "boolean"
    ]
    threshold: float | bool | str
    observed: float | bool | str
    passed: bool
    execution_state: Literal["passed", "failed", "unfinished", "legacy_unverified"] = "legacy_unverified"
    method: str
    split: str = "test"
    input_digest: str
    code_digest: str
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now)

    @field_validator("input_digest", "code_digest")
    @classmethod
    def valid_gate_digest(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not SHA256_PATTERN.fullmatch(normalized):
            raise ValueError("gate receipt digests must be lowercase SHA-256 values")
        return normalized


class EquationNode(DomainModel):
    """Canonical executable node for a scientific-law expression.

    Display LaTeX, source code, and fitted calibrations are projections of this
    tree.  They are never accepted as the executable identity of a law.
    """

    op: Literal[
        "variable",
        "parameter",
        "constant",
        "add",
        "multiply",
        "power",
        "negative",
        "exp",
        "log",
        "log1p",
        "sigmoid",
        "absolute",
        "minimum",
        "maximum",
        "kernel",
        "basis",
    ]
    symbol: str = Field(default="", max_length=160)
    value: float | None = None
    children: list[EquationNode] = Field(default_factory=list, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_arity(self) -> EquationNode:
        leaf = self.op in {"variable", "parameter", "constant", "kernel", "basis"}
        if leaf and self.children:
            raise ValueError(f"{self.op} equation nodes cannot have children")
        if self.op in {"variable", "parameter", "kernel", "basis"} and not self.symbol:
            raise ValueError(f"{self.op} equation nodes require a symbol")
        if self.op == "constant" and self.value is None:
            raise ValueError("constant equation nodes require a value")
        if self.op in {"negative", "exp", "log", "log1p", "sigmoid", "absolute"} and len(self.children) != 1:
            raise ValueError(f"{self.op} equation nodes require one child")
        if self.op == "power" and len(self.children) != 2:
            raise ValueError("power equation nodes require base and exponent")
        if self.op in {"add", "multiply", "minimum", "maximum"} and len(self.children) < 2:
            raise ValueError(f"{self.op} equation nodes require at least two children")
        return self


class SplitManifest(DomainModel):
    split_manifest_id: str
    study_id: str
    independent_unit_kind: str
    strategy: Literal[
        "group", "chronological", "spatial_block", "contiguous_signal", "stratified_group"
    ]
    seed_digest: str
    assignments: list[dict[str, Any]] = Field(default_factory=list, max_length=100_000)
    development_unit_count: int = Field(ge=0)
    validation_unit_count: int = Field(ge=0)
    test_unit_count: int = Field(ge=0)
    frozen: bool = True
    target_blind_digest: str
    created_at: str = Field(default_factory=utc_now)


class TransformGraph(DomainModel):
    transform_graph_id: str
    study_id: str
    nodes: list[dict[str, Any]] = Field(default_factory=list, max_length=10_000)
    edges: list[dict[str, Any]] = Field(default_factory=list, max_length=20_000)
    fold_local_nodes: list[str] = Field(default_factory=list, max_length=10_000)
    source_view_ids: list[str] = Field(default_factory=list, max_length=10_000)
    graph_digest: str
    created_at: str = Field(default_factory=utc_now)


class ScientificProgram(DomainModel):
    program_id: str
    study_id: str
    track: Literal["mechanism", "predictive_closure"]
    title: str = Field(min_length=3, max_length=240)
    scientific_intent: str = Field(min_length=12, max_length=2_400)
    target_bindings: list[dict[str, Any]] = Field(default_factory=list, max_length=1_000)
    input_bindings: list[dict[str, Any]] = Field(default_factory=list, max_length=5_000)
    nuisance_bindings: list[dict[str, Any]] = Field(default_factory=list, max_length=2_000)
    coordinate_bindings: list[dict[str, Any]] = Field(default_factory=list, max_length=1_000)
    independent_unit_bindings: list[dict[str, Any]] = Field(default_factory=list, max_length=1_000)
    principle_ids: list[str] = Field(default_factory=list, max_length=500)
    hypothesis_ids: list[str] = Field(default_factory=list, max_length=1_000)
    law_search_hints: list[dict[str, Any]] = Field(default_factory=list, max_length=32)
    split_manifest_id: str = ""
    transform_graph_id: str = ""
    engine_version: str = "principia-cross-domain-rule-engine/2"
    executor_id: str = "unresolved"
    executor_version: str = ""
    signature_identity: str = ""
    executable_hypotheses: list[ExecutableHypothesis] = Field(
        default_factory=list, max_length=1_000
    )
    state: Literal[
        "compiled", "running", "completed", "partial", "invalid", "data_insufficient"
    ] = "compiled"
    decisions: list[str] = Field(default_factory=list, max_length=500)
    limitations: list[str] = Field(default_factory=list, max_length=500)
    program_digest: str
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)


class ScientificLawFamily(DomainModel):
    law_id: str
    study_id: str
    program_id: str
    name: str = Field(min_length=3, max_length=240)
    family_kind: Literal[
        "scaling",
        "saturation",
        "activation",
        "competing_kinetics",
        "regime_transition",
        "spatial_field",
        "response_kernel",
        "conservation",
        "reaction_transport",
        "hierarchical",
        "spectral",
        "state_space",
        "recurrence",
        "network_scaling",
        "sparse_symbolic_closure",
    ]
    rule_kind: Literal["empirical_predictive", "mechanistic_invariant"] = (
        "empirical_predictive"
    )
    engine_version: str = "principia-cross-domain-rule-engine/2"
    executor_id: str = "unresolved"
    executor_version: str = ""
    signature_identity: str = ""
    gate_contract_version: str = "principia.rule-gates/v2"
    equation_ast: EquationNode
    canonical_ast_digest: str
    expression_latex: str = Field(min_length=3, max_length=8_000)
    scientific_meaning: str = Field(min_length=12, max_length=4_000)
    target: str
    scope: str
    dimensional_signature: dict[str, dict[str, float]] = Field(default_factory=dict)
    constraints: list[dict[str, Any]] = Field(default_factory=list, max_length=500)
    symmetries: list[str] = Field(default_factory=list, max_length=100)
    parameter_roles: list[dict[str, Any]] = Field(default_factory=list, max_length=500)
    evidence_tier: Literal[
        "candidate",
        "internal_locked_validation",
        "stress_stable",
        "prospectively_sealed",
        "externally_replicated",
    ] = "candidate"
    gate_summary: dict[str, Any] = Field(default_factory=dict)
    gate_receipts: list[GateReceipt] = Field(default_factory=list, max_length=500)
    variable_bindings: list[dict[str, Any]] = Field(default_factory=list, max_length=5_000)
    object_bindings: list[dict[str, Any]] = Field(default_factory=list, max_length=1_000)
    independent_unit_bindings: list[dict[str, Any]] = Field(
        default_factory=list, max_length=1_000
    )
    scientific_or_industrial_use: str = Field(default="", max_length=2_000)
    limitations: list[str] = Field(default_factory=list, max_length=500)
    calibration_ids: list[str] = Field(default_factory=list, max_length=10_000)
    evaluation_ids: list[str] = Field(default_factory=list, max_length=10_000)
    test_ids: list[str] = Field(default_factory=list, max_length=10_000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=10_000)
    family_digest: str
    created_at: str = Field(default_factory=utc_now)

    @field_validator("canonical_ast_digest")
    @classmethod
    def valid_ast_identity(cls, value: str) -> str:
        # The canonical digest is checked again by the executor.  Requiring a
        # SHA-256 shape here prevents display strings from substituting for an
        # executable identity at persistence boundaries.
        normalized = value.strip().lower()
        if not SHA256_PATTERN.fullmatch(normalized):
            raise ValueError("canonical_ast_digest must be a lowercase SHA-256 digest")
        return normalized


class ScientificLawCalibration(DomainModel):
    calibration_id: str
    study_id: str
    law_id: str
    split_manifest_id: str
    regime: str = "pooled"
    fitted_parameters: dict[str, Any] = Field(default_factory=dict)
    parameter_uncertainty: dict[str, Any] = Field(default_factory=dict)
    development_metrics: dict[str, Any] = Field(default_factory=dict)
    validation_metrics: dict[str, Any] = Field(default_factory=dict)
    test_metrics: dict[str, Any] = Field(default_factory=dict)
    worst_unit_metrics: dict[str, Any] = Field(default_factory=dict)
    residual_diagnostics: dict[str, Any] = Field(default_factory=dict)
    sensitivity: dict[str, Any] = Field(default_factory=dict)
    support: dict[str, Any] = Field(default_factory=dict)
    counterexamples: list[dict[str, Any]] = Field(default_factory=list, max_length=1_000)
    prediction_artifact_id: str = ""
    residual_artifact_id: str = ""
    calibration_digest: str
    created_at: str = Field(default_factory=utc_now)


class LawCandidate(DomainModel):
    candidate_id: str
    study_id: str
    program_id: str
    law_id: str
    equation_ast: EquationNode
    complexity: int = Field(ge=1)
    development_score: float | None = None
    validation_score: float | None = None
    baseline_contrast: dict[str, Any] = Field(default_factory=dict)
    rejection_reasons: list[str] = Field(default_factory=list, max_length=200)
    state: Literal["enumerated", "fitted", "rejected", "champion"]
    candidate_digest: str
    created_at: str = Field(default_factory=utc_now)


class LawEvaluation(DomainModel):
    evaluation_id: str
    study_id: str
    law_id: str
    calibration_id: str
    split: Literal["development", "validation", "test", "stress", "external"]
    unit_metrics: list[dict[str, Any]] = Field(default_factory=list, max_length=100_000)
    aggregate_metrics: dict[str, Any] = Field(default_factory=dict)
    baseline_metrics: dict[str, Any] = Field(default_factory=dict)
    gate_results: dict[str, Any] = Field(default_factory=dict)
    gate_receipts: list[GateReceipt] = Field(default_factory=list, max_length=500)
    selection_affected: bool = False
    evaluation_digest: str
    created_at: str = Field(default_factory=utc_now)


class ScientificDecision(DomainModel):
    decision_id: str
    study_id: str
    program_id: str
    subject_id: str
    decision_type: Literal[
        "binding", "split_freeze", "candidate_selection", "gate", "promotion", "abstention"
    ]
    outcome: Literal["accepted", "rejected", "held", "not_applicable"]
    reasons: list[str] = Field(min_length=1, max_length=200)
    input_digests: list[str] = Field(default_factory=list, max_length=10_000)
    decision_digest: str
    created_at: str = Field(default_factory=utc_now)


class DataHypothesis(DomainModel):
    hypothesis_id: str
    study_id: str
    claim: str = Field(min_length=12, max_length=2_400)
    origin: Literal["data_driven", "principle_guided", "cross_modal"]
    expected_relationship: str
    input_view_ids: list[str] = Field(min_length=1)
    principle_ids: list[str] = Field(default_factory=list)
    confounders: list[str] = Field(default_factory=list)
    boundary: list[str] = Field(default_factory=list)
    falsifier: str
    state: Literal["proposed", "planned", "tested", "rejected"] = "proposed"
    created_at: str = Field(default_factory=utc_now)


class AnalysisPlan(DomainModel):
    plan_id: str
    study_id: str
    hypothesis_id: str
    executor: Literal["operator", "python"]
    operator: str = ""
    input_view_ids: list[str] = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    expected_outputs: list[str] = Field(default_factory=list)
    validation_checks: list[str] = Field(default_factory=list)
    code: str = ""
    code_digest: str = ""
    plan_digest: str

    @model_validator(mode="after")
    def complete_executor(self) -> AnalysisPlan:
        if self.executor == "operator" and not self.operator:
            raise ValueError("operator plans require an operator")
        if self.executor == "python" and not self.code:
            raise ValueError("python plans require code")
        return self


class TestResult(DomainModel):
    test_id: str
    study_id: str
    hypothesis_id: str
    plan_id: str
    plan_digest: str
    state: Literal["succeeded", "failed", "invalid", "timed_out"]
    sample_definition: str
    independent_unit_count: int = Field(default=0, ge=0)
    estimate: dict[str, Any] = Field(default_factory=dict)
    uncertainty: dict[str, Any] = Field(default_factory=dict)
    corrected_significance: dict[str, Any] = Field(default_factory=dict)
    diagnostics: list[str] = Field(default_factory=list)
    sensitivities: list[dict[str, Any]] = Field(default_factory=list)
    negative_evidence: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    # Formula-bearing results are a stricter projection than findings.  The
    # expression must be emitted by executed deterministic/generated code and
    # its split receipt must describe how model selection and evaluation were
    # separated.  A reasoning model is never allowed to invent these fields.
    expression_latex: str = Field(default="", max_length=4_000)
    equation_variables: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    split_validation: dict[str, Any] = Field(default_factory=dict)
    result_digest: str
    created_at: str = Field(default_factory=utc_now)


class ComputedEvidenceAnchor(DomainModel):
    evidence_id: str
    study_id: str
    finding_id: str = ""
    test_id: str
    asset_id: str
    view_id: str
    locator: dict[str, Any]
    units: dict[str, str] = Field(default_factory=dict)
    plan_digest: str
    code_digest: str = ""
    executor_version: str
    result_digest: str


class DataFinding(DomainModel):
    finding_id: str
    study_id: str
    title: str = Field(min_length=3, max_length=240)
    claim: str = Field(min_length=12, max_length=2_400)
    interpretation: str
    mechanism: str
    significance: str = ""
    # Insight depth describes the scientific role of a result, not its certainty.
    # Validation and novelty remain orthogonal, independently audited fields.
    insight_level: Literal[
        "observational", "structural", "mechanistic", "principle_level"
    ] = "observational"
    nontriviality_basis: str = ""
    surprising_result: str = ""
    practical_value: str = ""
    principle_statement: str = ""
    transfer_scope: str = ""
    principle_chain: list[str] = Field(default_factory=list)
    status: FindingStatus
    validation_level: Literal[
        "exploratory", "internal_holdout", "cross_modal_replication", "externally_replicated"
    ] = "exploratory"
    novelty_status: NoveltyStatus = "not_assessed"
    hypothesis_ids: list[str] = Field(default_factory=list)
    test_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    principle_ids: list[str] = Field(default_factory=list)
    robustness: list[str] = Field(default_factory=list)
    confounders: list[str] = Field(default_factory=list)
    falsifiers: list[str] = Field(default_factory=list)
    negative_evidence: list[str] = Field(default_factory=list)
    prior_art: list[dict[str, Any]] = Field(default_factory=list)
    limits: list[str] = Field(default_factory=list)
    next_validation: str = ""
    # Promotion is deliberately a separate, deterministic gate.  A fluent
    # synthesis, a high insight label, or a user-visible finding card must not
    # imply that the record is ready to become a Data-derived Principle.
    promotion_eligible: bool = False
    promotion_blockers: list[str] = Field(default_factory=list, max_length=50)
    record_kind: Literal["discovery_finding"] = "discovery_finding"
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)


class DataRule(DomainModel):
    """A compact equation-level projection backed by an executed split receipt."""

    rule_id: str
    study_id: str
    finding_id: str
    title: str = Field(min_length=3, max_length=240)
    rule_family: str = Field(min_length=3, max_length=160)
    expression_latex: str = Field(min_length=3, max_length=4_000)
    interpretation: str = Field(min_length=3, max_length=1_200)
    equation_variables: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    # The headline is deliberately symbolic. Executed coefficient values and
    # physical scales live here so a reusable law is never confused with one
    # dataset's calibration.
    parameter_estimates: dict[str, Any] = Field(default_factory=dict)
    sample_definition: str
    split_strategy: str
    development: dict[str, Any] = Field(default_factory=dict)
    test: dict[str, Any] = Field(default_factory=dict)
    uncertainty: dict[str, Any] = Field(default_factory=dict)
    diagnostics: list[str] = Field(default_factory=list, max_length=100)
    test_ids: list[str] = Field(min_length=1, max_length=100)
    evidence_ids: list[str] = Field(default_factory=list, max_length=100)
    validation_status: Literal[
        "validated", "internally_stable", "exploratory_expression"
    ]
    record_kind: Literal["data_rule"] = "data_rule"
    created_at: str = Field(default_factory=utc_now)


class DataExtraPrinciple(DomainModel):
    extra_principle_id: str
    study_id: str
    title: str = Field(min_length=8, max_length=240)
    claim: str = Field(min_length=20, max_length=2_400)
    explanatory_gap: str = Field(min_length=20, max_length=2_000)
    mechanism: str = Field(min_length=20, max_length=4_000)
    boundary_conditions: list[str] = Field(default_factory=list)
    falsifiers: list[str] = Field(default_factory=list)
    supporting_sources: list[dict[str, Any]] = Field(default_factory=list)
    related_finding_ids: list[str] = Field(default_factory=list)
    status: Literal["provisional_research_synthesis"] = "provisional_research_synthesis"
    record_kind: Literal["extra_principle"] = "extra_principle"
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)


class DataDiscoveryReport(DomainModel):
    study_id: str
    state: Literal["queued", "running", "partial", "succeeded", "failed", "cancelled"]
    source_digest: str
    coverage: dict[str, Any] = Field(default_factory=dict)
    findings: list[DataFinding] = Field(default_factory=list)
    negative_results: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    generated_at: str = Field(default_factory=utc_now)


class DataDerivedPrincipleDraft(DomainModel):
    draft_id: str
    finding_id: str
    study_id: str
    title: str
    claim: str
    scope: str
    falsifier: str
    principle_links: list[str] = Field(default_factory=list)
    state: Literal["pending", "approved", "rejected"] = "pending"
    record_kind: Literal["data_derived_principle"] = "data_derived_principle"
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)
