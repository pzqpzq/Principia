from __future__ import annotations

import json
from typing import Any

from ..cloud import CloudSearchRequest, GlobalCloudSnapshotStore
from ..domain import CandidatePrinciple, FoundationGroundingDecision, ScientificArgument
from ..models import utc_now
from ..persistence import V14WorkspaceRepository
from ..providers import OpenAICompatibleProvider


class FoundationGroundingService:
    """Ground valid Principles without turning Meta similarity into a truth test."""

    def __init__(
        self,
        repository: V14WorkspaceRepository,
        global_cloud: GlobalCloudSnapshotStore | None,
    ) -> None:
        self.repository = repository
        self.global_cloud = global_cloud

    def assess(
        self,
        candidate: CandidatePrinciple,
        argument: ScientificArgument,
        *,
        provider: OpenAICompatibleProvider | None,
    ) -> dict[str, Any]:
        query = " ".join(
            [
                candidate.title,
                candidate.claim,
                argument.subject_system,
                argument.driver_or_intervention,
                argument.outcome,
                *argument.conditions,
                *argument.boundary,
            ]
        )
        meta_candidates: list[dict[str, Any]] = []
        if self.global_cloud is not None and self.global_cloud.active():
            meta_candidates = self.global_cloud.search(
                CloudSearchRequest(
                    entity="meta_principle",
                    query=query,
                    limit=24,
                )
            )["items"]
        if not meta_candidates or provider is None:
            rationale = (
                "No compatible Meta-Principle candidate was retrieved; the independently "
                "validated Principle remains eligible."
                if not meta_candidates
                else "Meta candidates are available, but no grounding provider was configured; human review remains pending."
            )
            return self._persist(
                candidate.candidate_id,
                FoundationGroundingDecision(
                    verdict="ungrounded_solid" if not meta_candidates else "ambiguous",
                    links=[],
                    rationale=rationale,
                ),
                candidate_ids=[str(item["id"]) for item in meta_candidates],
                trace={},
            )

        generation = provider.ground_scientific_principle(
            principle_record={
                "principle_id": candidate.candidate_id,
                "title": candidate.title,
                "claim": candidate.claim,
                "argument": argument.model_dump(mode="json"),
                "falsifier": candidate.falsifier,
            },
            meta_candidates=[
                {
                    "meta_principle_id": item["id"],
                    "title": item.get("title") or "",
                    "argument": item.get("argument") or item.get("claim") or "",
                    "conditions": item.get("conditions") or [],
                    "boundary": item.get("boundary") or [],
                    "applications": item.get("applications") or [],
                    "epistemic_type": item.get("epistemic_type") or "",
                    "maturity": item.get("maturity") or "",
                }
                for item in meta_candidates
            ],
        )
        decision = FoundationGroundingDecision.model_validate(generation.value)
        permitted = {str(item["id"]) for item in meta_candidates}
        valid_links = []
        ambiguous = decision.verdict == "ambiguous"
        for link in decision.links:
            compatibility = {
                link.condition_compatibility,
                link.variable_compatibility,
                link.scale_compatibility,
            }
            if link.meta_principle_id not in permitted or "incompatible" in compatibility:
                ambiguous = True
                continue
            if "unknown" in compatibility or link.confidence < 0.65:
                ambiguous = True
            valid_links.append(link)
        if valid_links and not ambiguous:
            verdict = "grounded"
        elif valid_links or decision.links:
            verdict = "ambiguous"
        else:
            verdict = "ungrounded_solid"
        normalized = FoundationGroundingDecision(
            verdict=verdict,
            links=valid_links,
            rationale=decision.rationale,
        )
        return self._persist(
            candidate.candidate_id,
            normalized,
            candidate_ids=sorted(permitted),
            trace=generation.trace.model_dump(mode="json"),
        )

    def _persist(
        self,
        candidate_id: str,
        decision: FoundationGroundingDecision,
        *,
        candidate_ids: list[str],
        trace: dict[str, Any],
    ) -> dict[str, Any]:
        now = utc_now()
        with self.repository.connect() as conn:
            revision = int(
                conn.execute(
                    "SELECT COALESCE(MAX(revision),0)+1 FROM candidate_foundation_assessments "
                    "WHERE candidate_id=?",
                    (candidate_id,),
                ).fetchone()[0]
            )
            assessment_id = f"foundation-assessment:{candidate_id}:{revision}"
            conn.execute(
                "INSERT INTO candidate_foundation_assessments VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    assessment_id,
                    candidate_id,
                    revision,
                    decision.verdict,
                    decision.rationale,
                    json.dumps(candidate_ids, sort_keys=True),
                    str(trace.get("provider") or ""),
                    str(trace.get("model") or ""),
                    json.dumps(trace, sort_keys=True),
                    now,
                ),
            )
            for index, link in enumerate(decision.links):
                conn.execute(
                    "INSERT INTO candidate_foundation_links VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        f"foundation-link:{candidate_id}:{revision}:{index}",
                        assessment_id,
                        candidate_id,
                        link.meta_principle_id,
                        link.relation_type,
                        link.direction,
                        link.rationale,
                        json.dumps(
                            {
                                "conditions": link.condition_compatibility,
                                "variables": link.variable_compatibility,
                                "scale": link.scale_compatibility,
                            },
                            sort_keys=True,
                        ),
                        link.confidence,
                        "proposed" if decision.verdict == "ambiguous" else "active",
                        now,
                    ),
                )
        return {
            "assessment_id": assessment_id,
            "candidate_id": candidate_id,
            "revision": revision,
            **decision.model_dump(mode="json"),
            "candidate_meta_ids": candidate_ids,
            "trace": trace,
        }
