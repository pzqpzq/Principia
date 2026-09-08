from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class PrincipiaModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class WorkItem(PrincipiaModel):
    id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    abstract: str = ""
    published_at: str = ""
    year: int | None = None
    venue: str = ""
    source: str = ""
    source_type: str = "paper"
    url: str = ""
    doi: str = ""
    arxiv_id: str = ""
    openalex_id: str = ""
    source_urls: list[str] = Field(default_factory=list)
    citation_count: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)

    @field_validator("title")
    @classmethod
    def title_required(cls, value: str) -> str:
        value = " ".join(str(value or "").split())
        if not value:
            raise ValueError("Work title is required")
        return value


class WorkList(PrincipiaModel):
    query: str
    items: list[WorkItem] = Field(default_factory=list)
    target_count: int = 0
    mode: str = "hybrid"
    sources: list[str] = Field(default_factory=list)
    run_id: str = ""
    created_at: str = Field(default_factory=utc_now)

    def __iter__(self):
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def counts(self) -> dict[str, int]:
        return {"works": len(self.items)}

    def __getitem__(self, item):
        return self.items[item]


class WorkFeatures(PrincipiaModel):
    work_id: str
    title: str
    model: str
    ideas: list[dict[str, Any]] = Field(default_factory=list)
    principles: list[dict[str, Any]] = Field(default_factory=list)
    baselines: list[dict[str, Any]] = Field(default_factory=list)
    benchmarks: list[dict[str, Any]] = Field(default_factory=list)
    takeaways: list[dict[str, Any]] = Field(default_factory=list)
    result_facts: list[dict[str, Any]] = Field(default_factory=list)
    source_excerpt_chars: int = 0
    retained_pdf_path: str = ""
    skipped: bool = False
    extraction_id: str = ""
    created_at: str = Field(default_factory=utc_now)


class ExtractedFeatures(PrincipiaModel):
    items: list[WorkFeatures] = Field(default_factory=list)
    model: str
    run_id: str = ""
    created_at: str = Field(default_factory=utc_now)

    def __iter__(self):
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def counts(self) -> dict[str, int]:
        return feature_counts(self.items)


class EvidencePacket(PrincipiaModel):
    query: str = ""
    features: list[WorkFeatures] = Field(default_factory=list)
    user_note: str = ""
    created_at: str = Field(default_factory=utc_now)

    def __len__(self) -> int:
        return len(self.features)

    def counts(self) -> dict[str, int]:
        return feature_counts(self.features)


class Idea(PrincipiaModel):
    id: str
    title: str
    thesis: str
    mode: Literal["standard", "calculus", "scidialect_evo"]
    novelty_claim: str = ""
    mechanism_design: list[str] = Field(default_factory=list)
    methodological_details: dict[str, Any] = Field(default_factory=dict)
    method_variants: list[str] = Field(default_factory=list)
    why_it_might_work: list[str] = Field(default_factory=list)
    validation_protocol: list[str] = Field(default_factory=list)
    baselines: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    derived_principles: list[str] = Field(default_factory=list)
    evidence_work_ids: list[str] = Field(default_factory=list)
    source_evidence: list[dict[str, Any]] = Field(default_factory=list)
    lineage: dict[str, Any] = Field(default_factory=dict)
    trace: dict[str, Any] = Field(default_factory=dict)
    generation_metadata: dict[str, Any] = Field(default_factory=dict)
    model: str = ""
    run_id: str = ""
    created_at: str = Field(default_factory=utc_now)


class IdeaComparison(PrincipiaModel):
    idea_id: str
    rows: list[dict[str, Any]] = Field(default_factory=list)
    model: str = ""
    run_id: str = ""
    created_at: str = Field(default_factory=utc_now)


class PipelineResult(PrincipiaModel):
    goal: str
    works: WorkList
    features: ExtractedFeatures
    idea: Idea
    comparison: IdeaComparison
    workspace_path: str
    export_path: str = ""
    created_at: str = Field(default_factory=utc_now)


class RunStatus(PrincipiaModel):
    run_id: str
    operation: str
    status: Literal["queued", "running", "complete", "cancelled", "error"] = "queued"
    stage: str = "queued"
    message: str = ""
    progress: float = 0.0
    counts: dict[str, Any] = Field(default_factory=dict)
    elapsed_seconds: float = 0.0
    eta_seconds: float | None = None
    error: str = ""
    started_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)
    completed_at: str = ""


class CancelToken:
    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def raise_if_cancelled(self) -> None:
        if self._cancelled:
            raise KeyboardInterrupt("Principia run was cancelled")


def as_path(value: str | Path) -> Path:
    return value if isinstance(value, Path) else Path(value)


def feature_counts(features: list[WorkFeatures]) -> dict[str, int]:
    return {
        "works": len(features),
        "ideas": sum(len(item.ideas) for item in features),
        "principles": sum(len(item.principles) for item in features),
        "takeaways": sum(len(item.takeaways) for item in features),
        "baselines": sum(len(item.baselines) for item in features),
        "benchmarks": sum(len(item.benchmarks) for item in features),
        "result_facts": sum(len(item.result_facts) for item in features),
    }
