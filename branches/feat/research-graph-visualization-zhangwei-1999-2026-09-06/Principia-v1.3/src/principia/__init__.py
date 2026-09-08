"""Principia v1.3.3 framework API."""

from principia_retrieval import RetrievalConfig, SearchDiagnostics, SourceReport

from .features import (
    canonical_evidence_registry,
    feature_record_text,
    feature_record_title,
    feature_summary_markdown,
    feature_summary_rows,
    hydrate_evidence_references,
    idea_markdown,
    markdown_table,
    schema_markdown,
    select_evidence,
    source_evidence_rows,
    validate_evidence_references,
    work_review_status,
)
from .ids import readable_id
from .llm import LLMClient, LLMConfig, LLMUsage, MockLLMClient, redact_secrets, siliconflow_config
from .local_sources import LocalCorpusIngestor, LocalParserRegistry, register_local_parser
from .models import (
    CancelToken,
    EvidencePacket,
    ExtractedFeatures,
    Idea,
    IdeaComparison,
    LocalCorpusConfig,
    LocalCorpusDiagnostics,
    LocalSourceReport,
    PipelineResult,
    RunStatus,
    SciDialectConfig,
    WorkFeatures,
    WorkItem,
    WorkList,
)
from .pipeline import PipelineConfig, PipelineJob
from .progress import NotebookProgress, notebook_progress
from .run import RunCancelledError, RunHandle
from .validation import (
    ValidationPlan,
    build_validation_plan,
    render_validation_plan_markdown,
    validation_plan_json,
    validation_plan_markdown,
    write_validation_plan,
)
from .workspace import Workspace

__all__ = [
    "CancelToken",
    "EvidencePacket",
    "ExtractedFeatures",
    "Idea",
    "IdeaComparison",
    "LocalCorpusConfig",
    "LocalCorpusDiagnostics",
    "LocalCorpusIngestor",
    "LocalParserRegistry",
    "LocalSourceReport",
    "PipelineResult",
    "PipelineConfig",
    "PipelineJob",
    "LLMClient",
    "LLMConfig",
    "LLMUsage",
    "MockLLMClient",
    "NotebookProgress",
    "RunHandle",
    "RunCancelledError",
    "RunStatus",
    "RetrievalConfig",
    "SciDialectConfig",
    "SearchDiagnostics",
    "SourceReport",
    "ValidationPlan",
    "WorkFeatures",
    "WorkItem",
    "WorkList",
    "Workspace",
    "canonical_evidence_registry",
    "feature_record_text",
    "feature_record_title",
    "feature_summary_markdown",
    "feature_summary_rows",
    "hydrate_evidence_references",
    "idea_markdown",
    "build_validation_plan",
    "markdown_table",
    "readable_id",
    "notebook_progress",
    "redact_secrets",
    "render_validation_plan_markdown",
    "schema_markdown",
    "select_evidence",
    "siliconflow_config",
    "source_evidence_rows",
    "validate_evidence_references",
    "validation_plan_json",
    "validation_plan_markdown",
    "work_review_status",
    "write_validation_plan",
    "register_local_parser",
]

__version__ = "1.3.3"
