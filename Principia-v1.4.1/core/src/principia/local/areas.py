from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from ..persistence import V14WorkspaceRepository

_AREA_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "kinetic-theory",
        (
            "boltzmann",
            "kinetic theory",
            "molecular chaos",
            "mean free path",
            "hard sphere",
            "collision frequency",
            "gas molecule",
        ),
    ),
    (
        "fluid-dynamics",
        (
            "fluid equation",
            "fluid dynamics",
            "hydrodynamic",
            "continuum law",
            "navier-stokes",
            "euler equation",
            "capillarity",
            "van der waals",
        ),
    ),
    (
        "mathematical-physics",
        (
            "hilbert's sixth",
            "hilbert sixth",
            "formal proposition",
            "formal proof",
            "thermodynamic limit",
            "dynamical system",
            "spectral stability",
            "atomistic",
        ),
    ),
    (
        "probability-statistics",
        (
            "probability",
            "stochastic",
            "random measure",
            "bayes",
            "ergodic",
            "statistical measure",
            "entropy decay",
        ),
    ),
    (
        "multi-agent-systems",
        (
            "multi-agent",
            "multiagent",
            "agent coordination",
            "agent collaboration",
            "agent team",
            "role specialization",
            "specialized agents",
        ),
    ),
    (
        "autonomous-scientific-discovery",
        (
            "scientific discovery",
            "autonomous science",
            "research agent",
            "hypothesis generation",
            "experiment planning",
            "scientific workflow",
            "laboratory automation",
        ),
    ),
    (
        "machine-intelligence",
        (
            "language model",
            "llm",
            "transformer",
            "machine learning",
            "artificial intelligence",
            "reasoning model",
            "self-correction",
            "retrieval-augmented",
        ),
    ),
)


def suggest_area_labels(
    *,
    argument: Mapping[str, Any] | None,
    claim: str,
    work_titles: list[str],
    research_focus: str = "",
    limit: int = 3,
) -> list[str]:
    """Return deterministic organization suggestions after evidence checks.

    Area labels never participate in scientific validity.  The compact,
    versioned vocabulary gives users useful Explorer facets while every label
    remains editable or rejectable.
    """

    fields = dict(argument or {})
    text = " ".join(
        [
            claim,
            research_focus,
            *work_titles,
            *(str(fields.get(key) or "") for key in (
                "canonical_claim",
                "subject_system",
                "driver_or_intervention",
                "outcome",
                "direction_or_qualifier",
            )),
        ]
    ).casefold()
    folded = re.sub(r"[^a-z0-9]+", " ", text).strip()
    scores: list[tuple[int, int, str]] = []
    for order, (area, phrases) in enumerate(_AREA_RULES):
        score = 0
        for phrase in phrases:
            normalized_phrase = re.sub(r"[^a-z0-9]+", " ", phrase.casefold()).strip()
            if normalized_phrase in folded:
                score += 2 if " " in normalized_phrase else 1
        if score:
            scores.append((score, -order, area))
    scores.sort(reverse=True)
    return [area for _, _, area in scores[: max(0, min(limit, 3))]]


class CandidateAreaSuggestionService:
    def __init__(self, repository: V14WorkspaceRepository) -> None:
        self.repository = repository

    def suggest_for_candidate(
        self,
        candidate_id: str,
        *,
        argument: Mapping[str, Any],
        claim: str,
        work_titles: list[str],
        research_focus: str = "",
    ) -> list[str]:
        labels = suggest_area_labels(
            argument=argument,
            claim=claim,
            work_titles=work_titles,
            research_focus=research_focus,
        )
        current = {
            str(item.get("area"))
            for item in self.repository.candidate_area_suggestions(candidate_id)
            if item.get("state") in {"suggested", "confirmed"}
        }
        for label in labels:
            if label in current:
                continue
            self.repository.set_candidate_area(
                candidate_id,
                label,
                state="suggested",
                provenance="deterministic-area-v1",
                rationale="Suggested from the validated claim and supporting paper metadata.",
            )
        return labels

    def backfill(self) -> dict[str, int]:
        with self.repository.connect() as conn:
            rows = conn.execute(
                """
                SELECT c.candidate_id
                FROM local_candidates c
                WHERE c.quality_state='eligible' AND c.eligibility_status='eligible'
                  AND NOT EXISTS (
                      SELECT 1 FROM candidate_area_assignments a
                      WHERE a.candidate_id=c.candidate_id
                        AND a.state IN ('suggested', 'confirmed')
                        AND a.revision=(
                            SELECT MAX(latest.revision)
                            FROM candidate_area_assignments latest
                            WHERE latest.candidate_id=a.candidate_id
                              AND latest.area=a.area
                        )
                  )
                ORDER BY c.candidate_id
                """
            ).fetchall()
        updated = 0
        for row in rows:
            candidate_id = str(row["candidate_id"])
            detail = self.repository.candidate_detail(candidate_id)
            if detail is None:
                continue
            metadata = dict(detail.get("local_metadata") or {})
            goal = self.repository.research_goal(str(metadata.get("goal_id") or ""))
            labels = self.suggest_for_candidate(
                candidate_id,
                argument=dict(detail.get("scientific_argument") or {}),
                claim=str(detail.get("claim") or ""),
                work_titles=[
                    str(item.get("work_title") or "")
                    for item in detail.get("evidence") or []
                ],
                research_focus=str((goal or {}).get("goal") or ""),
            )
            updated += bool(labels)
        return {"examined": len(rows), "updated": updated}
