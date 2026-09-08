from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from .models import DomainModel, PrincipleKind


class EvidenceAnchorDraft(DomainModel):
    """A model-proposed quotation tied to a server-issued evidence segment key."""

    segment_key: str = Field(min_length=1, max_length=160)
    quotation: str = Field(min_length=8, max_length=1_200)
    role: Literal["evidence", "falsifier", "context"] = "evidence"


class CandidateDraft(DomainModel):
    """Untrusted provider output before IDs and canonical references are assigned."""

    title: str = Field(min_length=3, max_length=240)
    claim: str = Field(min_length=12, max_length=2_400)
    kind: PrincipleKind
    scope: str = Field(min_length=3, max_length=1_200)
    falsifier: str = Field(default="", max_length=1_200)
    source_keys: list[str] = Field(min_length=1, max_length=8)
    evidence: list[EvidenceAnchorDraft] = Field(min_length=1, max_length=12)

    @field_validator("source_keys")
    @classmethod
    def unique_source_keys(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("source keys cannot be empty")
        if len(set(normalized)) != len(normalized):
            raise ValueError("source keys must be unique")
        return normalized


class CandidateDraftBatch(DomainModel):
    """Zero-to-eight atomic drafts for one extraction unit.

    An empty batch is explicitly valid: the model must not invent a Principle when
    the supplied paper does not support one.
    """

    drafts: list[CandidateDraft] = Field(default_factory=list, max_length=8)


class LiteratureRunLimits(DomainModel):
    max_http_attempts: int = Field(default=140, ge=1, le=1_000)
    max_input_tokens: int = Field(default=1_500_000, ge=1, le=20_000_000)
    max_output_tokens: int = Field(default=300_000, ge=1, le=5_000_000)
    max_pro_calls: int = Field(default=20, ge=0, le=100)
    max_wall_seconds: int = Field(default=10_800, ge=60, le=86_400)
    max_repairs_per_unit: Literal[0, 1] = 1
    concurrency: int = Field(default=3, ge=1, le=8)
    reasoning_tokens_per_request: int = Field(default=1_024, ge=128, le=32_768)
