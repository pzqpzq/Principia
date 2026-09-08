from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .models import DomainModel


class VirtualPrincipleProposal(DomainModel):
    """A deliberately hypothetical synthesis derived from installed Principles."""

    title: str = Field(min_length=8, max_length=180)
    claim: str = Field(min_length=20, max_length=2_400)
    area: str = Field(min_length=2, max_length=63, pattern=r"^[a-z0-9][a-z0-9-]+$")
    derivation_level: Literal[
        "direct_composition",
        "cross_context_generalization",
        "boundary_hypothesis",
        "mechanistic_bridge",
    ]
    scope_statement: str = Field(min_length=12, max_length=1_200)
    conditions: list[str] = Field(default_factory=list, max_length=12)
    exclusions: list[str] = Field(default_factory=list, max_length=12)
    falsifier: str = Field(min_length=12, max_length=1_200)
    assumptions: list[str] = Field(default_factory=list, max_length=12)
    contributing_principle_ids: list[str] = Field(min_length=2, max_length=20)
    synthesis_summary: str = Field(min_length=20, max_length=1_600)
    reliability_rationale: str = Field(min_length=20, max_length=1_200)
    novelty_rationale: str = Field(min_length=20, max_length=1_200)
    reliability_score: float = Field(ge=0, le=100)
    novelty_score: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def unique_contributors(self) -> VirtualPrincipleProposal:
        if len(set(self.contributing_principle_ids)) != len(self.contributing_principle_ids):
            raise ValueError("contributing Principles must be unique")
        return self


class VirtualPrincipleBatch(DomainModel):
    cross_principle_map: list[str] = Field(default_factory=list, max_length=12)
    proposals: list[VirtualPrincipleProposal] = Field(min_length=1, max_length=5)
