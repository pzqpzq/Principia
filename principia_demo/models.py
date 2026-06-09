from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class ResearchGoal:
    goal_id: str
    raw_query: str
    target_domain: str
    contribution_type: list[str]
    success_metrics: list[str]
    constraints: dict[str, str]
    search_terms: list[str]
    complexity: float
    query_kind: str = "task"
    idea_draft: str = ""
    created_at: str = field(default_factory=utc_now)


@dataclass
class SourceWork:
    work_id: str
    title: str
    authors: list[str]
    year: int | None
    venue_or_source: str
    url_or_doi: str
    source_type: str
    validation_level: str
    abstract: str
    citation_count: int | None = None
    community_signals: dict[str, Any] = field(default_factory=dict)
    extracted_claims: list[dict[str, str]] = field(default_factory=list)
    work_principles: list[str] = field(default_factory=list)
    work_insights: list[str] = field(default_factory=list)
    work_novelty: list[str] = field(default_factory=list)
    source_updated_at: str = ""
    created_at: str = field(default_factory=utc_now)


@dataclass
class FieldProfile:
    field_id: str
    name: str
    description: str = ""
    query: str = ""
    domain_tags: list[str] = field(default_factory=list)
    display_order: int = 0
    archived: bool = False
    goal_text: str = ""
    settings: dict[str, Any] = field(default_factory=dict)
    last_refresh_at: str = ""
    refresh_status: str = "idle"
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


@dataclass
class ProjectMembership:
    membership_id: str
    field_id: str
    bucket: str
    record_id: str
    display_order: int = 0
    source: str = "manual"
    hidden: bool = False
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


@dataclass
class WorkFact:
    fact_id: str
    work_id: str
    field_id: str
    fact_type: str
    text: str
    normalized_name: str = ""
    evidence_span: dict[str, str] = field(default_factory=dict)
    confidence_score: float = 0.5
    extraction_mode: str = "heuristic"
    validated_by_user: bool = False
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


@dataclass
class PrincipleCard:
    principle_id: str
    name: str
    principle_type: str
    abstraction_level: str
    abstract_signature: str
    mechanism: str
    problem_pressure: str
    objective: str
    scarce_resources: list[str]
    assumptions: list[str]
    constraints: list[str]
    invariants: list[str]
    tradeoffs: list[str]
    failure_modes: list[str]
    feedback_loop: list[str]
    transfer_hooks: list[str]
    source_works: list[str]
    validation_level: str
    confidence_score: float
    empirical_claims: list[str] = field(default_factory=list)
    evidence_spans: list[dict[str, str]] = field(default_factory=list)
    validation_notes: list[str] = field(default_factory=list)
    domain_tags: list[str] = field(default_factory=list)
    relation_hints: list[str] = field(default_factory=list)
    compatible_principles: list[str] = field(default_factory=list)
    contradiction_links: list[str] = field(default_factory=list)
    model_mode: str = "auto"
    model_name: str = "offline"
    query_kind: str = "task"
    language_variants: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


@dataclass
class PrincipleRelation:
    relation_id: str
    source_principle_id: str
    target_principle_id: str
    relation_type: str
    weight: float
    rationale: str
    evidence_fact_ids: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)


@dataclass
class BenchmarkRecord:
    benchmark_id: str
    field_id: str
    work_id: str
    task: str
    dataset: str
    split: str
    metric: str
    metric_direction: str
    evidence_span: dict[str, str] = field(default_factory=dict)
    confidence_score: float = 0.5
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


@dataclass
class BaselineRecord:
    baseline_id: str
    field_id: str
    work_id: str
    benchmark_id: str
    baseline_name: str
    baseline_type: str
    evidence_span: dict[str, str] = field(default_factory=dict)
    confidence_score: float = 0.5
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


@dataclass
class ResultRecord:
    result_id: str
    field_id: str
    work_id: str
    benchmark_id: str
    method_name: str
    baseline_id: str = ""
    metric: str = ""
    value: float | None = None
    value_text: str = ""
    unit: str = ""
    compute_budget: str = ""
    code_url: str = ""
    result_quality: dict[str, bool] = field(default_factory=dict)
    evidence_span: dict[str, str] = field(default_factory=dict)
    confidence_score: float = 0.5
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


@dataclass
class ResultEstimate:
    estimate_id: str
    idea_id: str
    primary_metric: str
    mean: float
    lower_90: float
    upper_90: float
    probability_useful_signal: float
    probability_negative_result: float
    probability_implementation_failure: float
    compute_cost_estimate: str
    time_to_first_signal: str
    key_risks: list[str]
    cheapest_falsification: str
    evidence_basis: list[str]
    calibration_basis: dict[str, list[str] | str]
    estimator_version: str = "demo-v0.2"
    created_at: str = field(default_factory=utc_now)


@dataclass
class PromptStep:
    step_id: str
    objective: str
    prompt_text: str
    expected_outputs: list[str]
    acceptance_checks: list[str]


@dataclass
class PromptPlan:
    prompt_plan_id: str
    idea_id: str
    target_agent: str
    repo_assumptions: list[str]
    prompts: list[PromptStep]
    feedback_export_schema: str
    created_at: str = field(default_factory=utc_now)


@dataclass
class IdeaCard:
    idea_id: str
    title: str
    one_sentence_thesis: str
    research_goal_id: str
    source_principles: list[str]
    operator_trace: list[dict[str, str]]
    novelty_claim: str
    prior_art_overlap: list[str]
    expected_contribution: str
    insight: str
    mechanism_design: list[str]
    why_it_might_work: list[str]
    minimal_experiment: str
    validation_protocol: list[str]
    baselines: list[str]
    metrics: list[str]
    failure_modes: list[str]
    ranking_scores: dict[str, float]
    result_estimate_id: str
    codex_prompt_plan_id: str
    feedback_status: str
    model_mode: str = "auto"
    model_name: str = "offline"
    query_kind: str = "task"
    language_variants: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)


@dataclass
class GapCard:
    gap_id: str
    field_id: str
    gap_type: str
    title: str
    summary: str
    evidence_fact_ids: list[str] = field(default_factory=list)
    related_work_ids: list[str] = field(default_factory=list)
    related_principle_ids: list[str] = field(default_factory=list)
    related_benchmark_ids: list[str] = field(default_factory=list)
    suggested_idea_seeds: list[str] = field(default_factory=list)
    severity: float = 0.5
    novelty_potential: float = 0.5
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


@dataclass
class FrontierSnapshot:
    snapshot_id: str
    field_id: str
    summary: str
    counts: dict[str, int]
    coverage: dict[str, float]
    top_principle_ids: list[str] = field(default_factory=list)
    gap_ids: list[str] = field(default_factory=list)
    evidence: list[dict[str, str]] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)


@dataclass
class AssistantExport:
    export_id: str
    field_id: str
    idea_id: str
    target_agent: str
    bundle_version: str
    bundle: dict[str, Any]
    created_at: str = field(default_factory=utc_now)


@dataclass
class FeedbackEvent:
    feedback_id: str
    field_id: str
    idea_id: str
    run_id: str = ""
    outcome_label: str = "inconclusive"
    metric_delta_observed: str = ""
    runtime_cost: str = ""
    strengthened_principles: list[str] = field(default_factory=list)
    weakened_principles: list[str] = field(default_factory=list)
    new_failure_modes: list[str] = field(default_factory=list)
    notes: str = ""
    source: str = "user"
    created_at: str = field(default_factory=utc_now)


def to_dict(value: Any) -> dict[str, Any]:
    return asdict(value)
