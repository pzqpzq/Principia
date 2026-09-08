"""Principia V1.3 framework API."""

from .features import (
    feature_record_text,
    feature_record_title,
    feature_summary_markdown,
    feature_summary_rows,
    idea_markdown,
    markdown_table,
    schema_markdown,
    select_evidence,
    source_evidence_rows,
    work_review_status,
)
from .ids import readable_id
from .llm import LLMClient, LLMConfig, MockLLMClient, redact_secrets, siliconflow_config
from .models import (
    CancelToken,
    EvidencePacket,
    ExtractedFeatures,
    Idea,
    IdeaComparison,
    PipelineResult,
    RunStatus,
    WorkFeatures,
    WorkItem,
    WorkList,
)
from .progress import NotebookProgress, notebook_progress
from .run import RunHandle
from .workspace import Workspace

__all__ = [
    "CancelToken",
    "EvidencePacket",
    "ExtractedFeatures",
    "Idea",
    "IdeaComparison",
    "PipelineResult",
    "LLMClient",
    "LLMConfig",
    "MockLLMClient",
    "NotebookProgress",
    "RunHandle",
    "RunStatus",
    "WorkFeatures",
    "WorkItem",
    "WorkList",
    "Workspace",
    "feature_record_text",
    "feature_record_title",
    "feature_summary_markdown",
    "feature_summary_rows",
    "idea_markdown",
    "markdown_table",
    "readable_id",
    "notebook_progress",
    "redact_secrets",
    "schema_markdown",
    "select_evidence",
    "siliconflow_config",
    "source_evidence_rows",
    "work_review_status",
]

__version__ = "1.3.2"
