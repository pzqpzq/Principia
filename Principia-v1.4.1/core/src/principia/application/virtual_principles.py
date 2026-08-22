from __future__ import annotations

import re
from typing import Any

from ..domain import (
    CandidatePrinciple,
    GenerationTrace,
    PrincipleKind,
    PrincipleRelation,
    PrincipleScope,
    RelationType,
    TraceOperation,
    VirtualPrincipleProposal,
    candidate_id,
    canonical_sha256,
    event_id,
)
from ..local import LocalDiscoveryService
from ..persistence import V14WorkspaceRepository
from ..providers import OpenAICompatibleProvider
from .explorer import PrincipleExplorerService


class VirtualPrincipleService:
    """Generate and optionally persist bounded, unreviewed synthesis hypotheses."""

    def __init__(
        self,
        repository: V14WorkspaceRepository,
        local: LocalDiscoveryService,
        explorer: PrincipleExplorerService,
    ) -> None:
        self.repository = repository
        self.local = local
        self.explorer = explorer

    def _detail(self, identifier: str) -> dict[str, Any]:
        detail = self.repository.candidate_detail(identifier)
        if detail is None:
            detail = self.repository.principle(identifier)
        if detail is None:
            detail = self.explorer.registry.principle(identifier)
        if (
            detail is None
            and self.explorer.global_cloud is not None
            and self.explorer.global_cloud.active()
        ):
            detail = self.explorer.global_cloud.principle(identifier)
        if detail is None:
            raise KeyError(f"Principle {identifier} was not found")
        return detail

    @staticmethod
    def _provider_record(identifier: str, detail: dict[str, Any]) -> dict[str, Any]:
        argument = detail.get("scientific_argument")
        scope = detail.get("scope")
        return {
            "principle_id": identifier,
            "title": str(detail.get("title") or identifier)[:240],
            "claim": str(detail.get("claim") or "")[:2_800],
            "kind": str(detail.get("kind") or detail.get("claim_type") or "hypothesis"),
            "area": str(detail.get("area") or "general")[:63],
            "scope": scope if isinstance(scope, dict) else {"statement": str(scope or "")},
            "scientific_argument": argument if isinstance(argument, dict) else {},
            "falsifier": str(detail.get("falsifier") or "")[:1_200],
            "maturity": str(detail.get("maturity") or "unassessed"),
            "review_status": str(
                detail.get("review_status") or detail.get("assessment_status") or "unassessed"
            ),
        }

    def generate(
        self,
        *,
        principle_ids: list[str],
        provider_profile_id: str,
        model: str,
        egress_confirmed: bool,
        requested_count: int,
        research_direction: str,
    ) -> dict[str, Any]:
        identifiers = list(dict.fromkeys(principle_ids))
        if not 2 <= len(identifiers) <= 20:
            raise ValueError("Select between two and twenty Principles")
        records = [
            self._provider_record(identifier, self._detail(identifier))
            for identifier in identifiers
        ]
        _, policy, api_key = self.local.provider_configuration(
            provider_profile_id,
            model,
            egress_confirmed=egress_confirmed,
        )
        provider = OpenAICompatibleProvider(policy, api_key=api_key, timeout=240)
        try:
            generation = provider.derive_virtual_principles(
                principle_records=records,
                research_direction=research_direction,
                requested_count=requested_count,
            )
        finally:
            provider.close()
        batch = generation.value
        selected = set(identifiers)
        items: list[dict[str, Any]] = []
        for proposal in batch.proposals[:requested_count]:  # type: ignore[attr-defined]
            contributors = list(dict.fromkeys(proposal.contributing_principle_ids))
            if len(contributors) < 2 or not set(contributors).issubset(selected):
                contributors = identifiers
                proposal = proposal.model_copy(update={"contributing_principle_ids": contributors})
            virtual_id = (
                "virtual:"
                + canonical_sha256(
                    {"proposal": proposal.model_dump(mode="json"), "parents": contributors}
                )[:24]
            )
            items.append({"virtual_id": virtual_id, "proposal": proposal})
        trace = generation.trace.model_dump(mode="json")
        return {
            "items": items,
            "cross_principle_map": list(batch.cross_principle_map),  # type: ignore[attr-defined]
            "provider": generation.trace.provider,
            "model": generation.trace.model,
            "trace": trace,
            "disclosure": (
                "These are LLM-derived hypotheses from selected Principle text, not extracted "
                "paper findings. They remain temporary until you save them locally."
            ),
        }

    def save(
        self,
        proposal: VirtualPrincipleProposal,
        *,
        provider: str,
        model: str,
        trace: dict[str, Any],
    ) -> dict[str, Any]:
        parents = list(dict.fromkeys(proposal.contributing_principle_ids))
        if not 2 <= len(parents) <= 20:
            raise ValueError("A Virtual Principle must retain two to twenty parent Principles")
        for identifier in parents:
            self._detail(identifier)
        area = re.sub(r"[^a-z0-9-]+", "-", proposal.area.casefold()).strip("-") or "general"
        identifier = candidate_id()
        provider_trace = {
            key: trace.get(key)
            for key in (
                "prompt_template",
                "prompt_sha256",
                "input_sha256",
                "output_sha256",
                "latency_ms",
                "input_tokens",
                "output_tokens",
                "attempts",
            )
        }
        candidate = CandidatePrinciple(
            candidate_id=identifier,
            area=area,
            title=proposal.title,
            claim=proposal.claim,
            kind=PrincipleKind.HYPOTHESIS,
            scope=PrincipleScope(
                statement=proposal.scope_statement,
                conditions=proposal.conditions,
                exclusions=proposal.exclusions,
            ),
            falsifier=proposal.falsifier,
            relations=[
                PrincipleRelation(
                    relation_type=RelationType.DEPENDS_ON,
                    target_principle_id=parent,
                    rationale=(
                        "This unreviewed hypothesis was synthesized from the selected parent "
                        "Principle; the relationship is model-proposed, not validated."
                    ),
                    strength=max(0.0, min(1.0, proposal.reliability_score / 100)),
                )
                for parent in parents
            ],
            generation_trace=[
                GenerationTrace(
                    event_id=event_id("virtual"),
                    operation=TraceOperation.MAP,
                    actor="virtual-principle-synthesis",
                    provider=provider,
                    model=model,
                    prompt_template=str(provider_trace.get("prompt_template") or ""),
                    prompt_sha256=str(provider_trace.get("prompt_sha256") or ""),
                    input_sha256=str(provider_trace.get("input_sha256") or ""),
                    output_sha256=str(provider_trace.get("output_sha256") or ""),
                    latency_ms=int(provider_trace.get("latency_ms") or 0),
                    input_tokens=int(provider_trace.get("input_tokens") or 0),
                    output_tokens=int(provider_trace.get("output_tokens") or 0),
                    retries=max(0, min(2, int(provider_trace.get("attempts") or 1) - 1)),
                )
            ],
            raw_legacy_payload={
                "virtual_principle": True,
                "derivation_level": proposal.derivation_level,
                "assumptions": proposal.assumptions,
                "synthesis_summary": proposal.synthesis_summary,
                "reliability_score": proposal.reliability_score,
                "novelty_score": proposal.novelty_score,
                "reliability_rationale": proposal.reliability_rationale,
                "novelty_rationale": proposal.novelty_rationale,
                "parent_principle_ids": parents,
            },
        )
        self.repository.save_candidate(
            candidate,
            source_kind="virtual_reasoning",
            eligibility_status="eligible",
            quality_state="eligible",
            extraction_mode="virtual_synthesis",
            context_relevance="hypothetical",
            scientific_contract_version="virtual-principle-v1",
            quality_gate_version="unreviewed-hypothesis",
        )
        return self.repository.candidate_detail(identifier) or candidate.model_dump(mode="json")
