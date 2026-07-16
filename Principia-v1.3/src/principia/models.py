from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from principia_retrieval import SearchDiagnostics, normalize_scholarly_title

from .math import generated_math_issues, normalize_math_value


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_doi_identifier(value: Any) -> str:
    """Return the canonical, case-insensitive DOI identity.

    Providers interchange bare DOI values with ``doi:`` and resolver-URL forms.
    Normalizing them at the public model boundary keeps retrieval, persistence,
    and repeated searches on the same identity without changing display URLs.
    """

    text = unquote(str(value or "")).strip()
    prefix = re.compile(
        r"^(?:(?:https?://)?(?:(?:dx|www)\.)?doi\.org/|doi\s*:\s*)",
        flags=re.IGNORECASE,
    )
    previous = None
    while text and text != previous:
        previous = text
        text = prefix.sub("", text, count=1).strip()
    return text.lower()


def normalize_arxiv_identifier(value: Any) -> str:
    """Return an arXiv identity without resolver syntax or version suffixes."""

    text = unquote(str(value or "")).strip()
    text = re.sub(
        r"^https?://(?:(?:www|export)\.)?arxiv\.org/(?:abs|pdf)/",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"^arxiv\s*:\s*", "", text, flags=re.IGNORECASE)
    text = re.split(r"[?#]", text, maxsplit=1)[0].strip()
    text = re.sub(r"\.pdf$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"v\d+$", "", text, flags=re.IGNORECASE)
    return text.lower()


def normalize_openalex_identifier(value: Any) -> str:
    """Return the stable ``W...`` component of an OpenAlex work identity."""

    text = unquote(str(value or "")).strip()
    text = re.sub(
        r"^https?://(?:api\.)?openalex\.org/(?:works/)?",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.split(r"[?#/]", text, maxsplit=1)[0].strip()
    return text.upper() if re.fullmatch(r"w\d+", text, flags=re.IGNORECASE) else text


class PrincipiaModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


def _typed_feature_records(value: Any, record_type: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    records = value if isinstance(value, list) else [value]
    output: list[dict[str, Any]] = []
    for record in records:
        if isinstance(record, dict):
            normalized = dict(record)
        elif str(record).strip():
            normalized = {"name": str(record).strip()}
        else:
            continue
        normalized.setdefault("record_type", record_type)
        output.append(normalized)
    return output


def _merge_feature_aliases(
    data: dict[str, Any],
    *,
    canonical: str,
    aliases: dict[str, str],
    canonical_type: str,
) -> list[dict[str, Any]]:
    output = _typed_feature_records(data.get(canonical), canonical_type)
    for alias, record_type in aliases.items():
        output.extend(_typed_feature_records(data.pop(alias, None), record_type))
    return output


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
    semantic_scholar_id: str = ""
    pmid: str = ""
    pdf_url: str = ""
    source_urls: list[str] = Field(default_factory=list)
    citation_count: int | None = None
    content_sha256: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)

    @field_validator("title", mode="before")
    @classmethod
    def title_required(cls, value: Any) -> str:
        value = normalize_scholarly_title(value)
        if not value:
            raise ValueError("Work title is required")
        return value

    @field_validator("doi", mode="before")
    @classmethod
    def canonical_doi(cls, value: Any) -> str:
        return normalize_doi_identifier(value)

    @field_validator("arxiv_id", mode="before")
    @classmethod
    def canonical_arxiv_id(cls, value: Any) -> str:
        return normalize_arxiv_identifier(value)

    @field_validator("openalex_id", mode="before")
    @classmethod
    def canonical_openalex_id(cls, value: Any) -> str:
        return normalize_openalex_identifier(value)

    @field_validator("semantic_scholar_id", "pmid", mode="before")
    @classmethod
    def trim_provider_identity(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("content_sha256", mode="before")
    @classmethod
    def canonical_content_hash(cls, value: Any) -> str:
        text = str(value or "").strip().lower()
        if text and not re.fullmatch(r"[0-9a-f]{64}", text):
            raise ValueError("content_sha256 must be a 64-character hexadecimal SHA-256 digest")
        return text


class LocalCorpusConfig(PrincipiaModel):
    """Bounded, privacy-conscious local document ingestion settings."""

    recursive: bool = True
    max_files: int = Field(default=500, ge=1, le=100_000)
    max_file_bytes: int = Field(default=50 * 1024 * 1024, ge=1)
    include_hidden: bool = False
    follow_symlinks: bool = False
    chunk_chars: int = Field(default=24_000, ge=1_000)
    chunk_overlap: int = Field(default=2_000, ge=0)
    corpus_name: str = ""

    @model_validator(mode="after")
    def validate_chunk_overlap(self) -> LocalCorpusConfig:
        if self.chunk_overlap >= self.chunk_chars:
            raise ValueError("chunk_overlap must be smaller than chunk_chars")
        return self


class LocalSourceReport(PrincipiaModel):
    """Portable per-file ingestion report; absolute source paths are forbidden."""

    uri: str = ""
    relative_path: str = ""
    status: Literal["accepted", "cached", "duplicate", "skipped", "error"] = "skipped"
    work_id: str = ""
    mime_type: str = ""
    parser: str = ""
    parser_fingerprint: str = ""
    byte_sha256: str = ""
    text_sha256: str = ""
    byte_size: int = 0
    character_count: int = 0
    chunk_count: int = 0
    duplicate_of: str = ""
    warnings: list[str] = Field(default_factory=list)
    error: str = ""


class LocalCorpusDiagnostics(PrincipiaModel):
    """Aggregate local-corpus health and completeness information."""

    corpus_name: str = ""
    discovered_count: int = 0
    accepted_count: int = 0
    cached_count: int = 0
    duplicate_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    total_bytes: int = 0
    total_characters: int = 0
    reports: list[LocalSourceReport] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class WorkList(PrincipiaModel):
    query: str
    items: list[WorkItem] = Field(default_factory=list)
    target_count: int = 0
    mode: str = "hybrid"
    sources: list[str] = Field(default_factory=list)
    diagnostics: SearchDiagnostics = Field(default_factory=SearchDiagnostics)
    local_diagnostics: LocalCorpusDiagnostics = Field(default_factory=LocalCorpusDiagnostics)
    public_count: int = 0
    local_count: int = 0
    run_id: str = ""
    created_at: str = Field(default_factory=utc_now)

    @model_validator(mode="before")
    @classmethod
    def normalize_persisted_diagnostics(cls, value: Any) -> Any:
        """Accept source snapshots containing derived diagnostic summaries.

        ``SearchDiagnostics.to_dict()`` intentionally persists the convenient
        ``successful_sources`` and ``failed_sources`` summaries. The dataclass
        derives both values from ``source_reports``, so they are not constructor
        fields and must not be forwarded during public model validation.
        """

        if not isinstance(value, dict):
            return value
        diagnostics = value.get("diagnostics")
        if not isinstance(diagnostics, dict):
            return value
        normalized_diagnostics = dict(diagnostics)
        normalized_diagnostics.pop("successful_sources", None)
        normalized_diagnostics.pop("failed_sources", None)
        normalized = dict(value)
        normalized["diagnostics"] = normalized_diagnostics
        return normalized

    @model_validator(mode="after")
    def populate_source_counts(self) -> WorkList:
        local_count = sum(1 for item in self.items if item.source == "local")
        object.__setattr__(self, "local_count", local_count)
        object.__setattr__(self, "public_count", len(self.items) - local_count)
        return self

    def __iter__(self):
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def counts(self) -> dict[str, int]:
        return {
            "works": len(self.items),
            "public_works": self.public_count,
            "local_works": self.local_count,
        }

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
    source_content_type: Literal[
        "pdf_text",
        "html",
        "local_text",
        "abstract",
        "title_only",
        "unknown",
    ] = "unknown"
    source_url: str = ""
    source_content_hash: str = ""
    extractor_fingerprint: str = ""
    extraction_warnings: list[str] = Field(default_factory=list)
    retained_pdf_path: str = ""
    skipped: bool = False
    extraction_id: str = ""
    created_at: str = Field(default_factory=utc_now)

    @field_validator("title", mode="before")
    @classmethod
    def normalize_cached_title(cls, value: Any) -> str:
        """Clean legacy cached feature titles when they are loaded."""

        return normalize_scholarly_title(value)

    @field_validator(
        "ideas",
        "principles",
        "baselines",
        "benchmarks",
        "takeaways",
        "result_facts",
        mode="before",
    )
    @classmethod
    def canonicalize_feature_math(cls, value: Any) -> Any:
        """Canonicalize explicit mathematics before feature persistence or reuse."""

        return normalize_math_value(value)

    @model_validator(mode="before")
    @classmethod
    def normalize_cross_domain_aliases(cls, value: Any) -> Any:
        """Accept domain-neutral names while retaining the v1.3 storage schema.

        ``baselines`` and ``benchmarks`` remain the canonical persisted fields for
        compatibility.  A ``record_type`` tag preserves the more precise meaning
        supplied by callers (for example, a control or an experimental system).
        """

        if not isinstance(value, dict):
            return value
        data = dict(value)
        data["baselines"] = _merge_feature_aliases(
            data,
            canonical="baselines",
            aliases={
                "comparators": "comparator",
                "controls": "control",
                "standard_methods": "standard_method",
                "reference_theories": "reference_theory",
            },
            canonical_type="comparator",
        )
        data["benchmarks"] = _merge_feature_aliases(
            data,
            canonical="benchmarks",
            aliases={
                "evaluation_contexts": "evaluation_context",
                "experimental_systems": "experimental_system",
                "instruments": "instrument",
                "observables": "observable",
                "standard_tasks": "standard_task",
            },
            canonical_type="evaluation_context",
        )
        return data

    @field_validator("extraction_warnings", mode="before")
    @classmethod
    def normalize_legacy_math_diagnostics(cls, value: Any) -> Any:
        """Keep legacy warning text from masquerading as rendered math.

        Early v1.3.3 checkpoints quoted unsupported LaTeX delimiters literally
        inside a diagnostic.  Those strings are audit metadata, not formulas,
        and would themselves fail the release math scanner when a cached
        feature was exported.  Normalize only that known diagnostic wording
        when old workspaces are reloaded.
        """

        if not isinstance(value, list):
            return value
        legacy = r"Use $...$ or $$...$$, not \( ... \) or \[ ... \]"
        replacement = (
            "Use dollar-delimited inline or display math; "
            "parenthesis/bracket LaTeX delimiters are unsupported"
        )
        return [str(item).replace(legacy, replacement) for item in value]

    @property
    def comparators(self) -> list[dict[str, Any]]:
        return list(self.baselines)

    @property
    def evaluation_contexts(self) -> list[dict[str, Any]]:
        return list(self.benchmarks)


class SciDialectConfig(PrincipiaModel):
    """Configuration for the three-stage SciDialect-Evo generation protocol."""

    candidate_count: Literal[3] = 3
    evolved_candidate_count: Literal[2] = 2
    candidate_temperature: float = Field(default=0.45, ge=0.0, le=2.0)
    evolution_temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    final_temperature: float = Field(default=0.18, ge=0.0, le=2.0)
    candidate_max_tokens: int = Field(default=4800, ge=512, le=16000)
    evolution_max_tokens: int = Field(default=5200, ge=512, le=16000)
    final_max_tokens: int = Field(default=4400, ge=512, le=16000)
    allow_degraded_fallback: bool = False


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

    @model_validator(mode="before")
    @classmethod
    def canonicalize_generated_math(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        for field in (
            "thesis",
            "novelty_claim",
            "mechanism_design",
            "methodological_details",
            "method_variants",
            "why_it_might_work",
            "validation_protocol",
            "baselines",
            "metrics",
            "risks",
            "assumptions",
            "derived_principles",
            "source_evidence",
            "lineage",
            "trace",
        ):
            if field in data:
                data[field] = normalize_math_value(data[field])
        return data

    @model_validator(mode="after")
    def reject_uncanonical_generated_math(self) -> Idea:
        content = {
            "thesis": self.thesis,
            "novelty_claim": self.novelty_claim,
            "mechanism_design": self.mechanism_design,
            "methodological_details": self.methodological_details,
            "method_variants": self.method_variants,
            "why_it_might_work": self.why_it_might_work,
            "validation_protocol": self.validation_protocol,
            "baselines": self.baselines,
            "metrics": self.metrics,
            "risks": self.risks,
            "assumptions": self.assumptions,
            "derived_principles": self.derived_principles,
            "source_evidence": self.source_evidence,
            "lineage": self.lineage,
            "trace": self.trace,
        }
        issues = generated_math_issues(content, path="idea")
        if issues:
            raise ValueError("Idea contains non-canonical mathematics: " + "; ".join(issues))
        return self


class IdeaComparison(PrincipiaModel):
    idea_id: str
    rows: list[dict[str, Any]] = Field(default_factory=list)
    model: str = ""
    run_id: str = ""
    created_at: str = Field(default_factory=utc_now)

    @field_validator("rows", mode="before")
    @classmethod
    def canonicalize_comparison_math(cls, value: Any) -> Any:
        return normalize_math_value(value)

    @model_validator(mode="after")
    def reject_uncanonical_comparison_math(self) -> IdeaComparison:
        issues = generated_math_issues(self.rows, path="comparison.rows")
        if issues:
            raise ValueError(
                "Idea comparison contains non-canonical mathematics: " + "; ".join(issues)
            )
        return self


class PipelineResult(PrincipiaModel):
    goal: str
    works: WorkList
    features: ExtractedFeatures
    idea: Idea
    comparison: IdeaComparison
    workspace_path: str
    selected_evidence: EvidencePacket = Field(default_factory=EvidencePacket)
    export_path: str = ""
    created_at: str = Field(default_factory=utc_now)

    @field_validator("goal", mode="before")
    @classmethod
    def canonicalize_goal_math(cls, value: Any) -> Any:
        return normalize_math_value(value)

    def summary(self) -> dict[str, Any]:
        """Return the compact, stable result summary used by terminals and notebooks."""

        evidence_counts = self.selected_evidence.counts()
        successful_sources = self.works.diagnostics.successful_sources
        return {
            "idea_id": self.idea.id,
            "idea_title": self.idea.title,
            "status": "complete",
            "public_works": self.works.public_count,
            "local_works": self.works.local_count,
            "online_works": self.works.public_count,
            "local_documents": self.works.local_count,
            "feature_bundles": len(self.features),
            "evidence_records": sum(
                evidence_counts.get(kind, 0)
                for kind in (
                    "ideas",
                    "principles",
                    "takeaways",
                    "baselines",
                    "benchmarks",
                    "result_facts",
                )
            ),
            "evidence_counts": {
                kind: evidence_counts.get(kind, 0)
                for kind in ("ideas", "principles", "takeaways")
            },
            "embedding_rerank": self.works.diagnostics.rerank_mode_applied,
            "successful_sources": len(successful_sources),
            "source_names": successful_sources,
            "extraction_model": self.features.model,
            "idea_model": self.idea.model,
            "mode": self.idea.mode.replace("_", "-"),
            "execution_origin": self.idea.generation_metadata.get("execution_origin", ""),
            "degraded": bool(self.idea.trace.get("degraded", False)),
            "comparison_rows": len(self.comparison.rows),
            "export_path": self.export_path,
        }

    def show(self) -> PipelineResult:
        """Display a concise result card and return ``self`` for notebook chaining."""

        from rich.console import Console
        from rich.table import Table

        summary = self.summary()
        table = Table(title=self.idea.title, show_header=False, box=None, pad_edge=False)
        table.add_column("field", style="bold cyan", no_wrap=True)
        table.add_column("value")
        for label, key in (
            ("Idea", "idea_id"),
            ("Works", "public_works"),
            ("Local", "local_works"),
            ("Features", "feature_bundles"),
            ("Evidence", "evidence_records"),
            ("Comparisons", "comparison_rows"),
            ("Export", "export_path"),
        ):
            table.add_row(label, str(summary[key]))
        Console().print(table)
        return self


class RunStatus(PrincipiaModel):
    run_id: str
    operation: str
    status: Literal[
        "queued",
        "running",
        "pause_requested",
        "paused",
        "cancel_requested",
        "cancelled",
        "complete",
        "error",
    ] = "queued"
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
