from __future__ import annotations

import json
import sqlite3
from typing import Any

from .global_store import GlobalStore
from .utils import enrich_query, lexical_score, validation_number


class HybridRetriever:
    def __init__(self, store: GlobalStore):
        self.store = store

    def retrieve(
        self,
        query: str,
        *,
        concept_types: list[str] | None = None,
        project_id: str = "",
        limit_per_type: int = 12,
    ) -> dict[str, Any]:
        query = query or ""
        types = concept_types or ["existed_idea", "principle", "takeaway_message", "benchmark", "baseline"]
        results: dict[str, list[dict[str, Any]]] = {}
        for concept_type in types:
            candidates = self._candidate_concepts(query, concept_type, project_id=project_id, limit=max(limit_per_type * 8, 40))
            ranked = self._rank(query, candidates, project_id=project_id)
            results[concept_type] = ranked[:limit_per_type]
        return {"query": query, "results": results}

    def _candidate_concepts(self, query: str, concept_type: str, *, project_id: str, limit: int) -> list[dict[str, Any]]:
        candidates = self.store.concepts(concept_type, project_id=project_id, limit=limit)
        fts_ids = self._fts_ids(query, concept_type, limit=limit)
        if fts_ids:
            existing_ids = {item["concept_id"] for item in candidates}
            with self.store._connect() as conn:
                for concept_id in fts_ids:
                    if concept_id in existing_ids:
                        continue
                    concept = self.store.get_concept(concept_id, conn=conn)
                    if concept:
                        candidates.append(concept)
        return candidates

    def _fts_ids(self, query: str, concept_type: str, *, limit: int) -> list[str]:
        if not query:
            return []
        with self.store._connect() as conn:
            try:
                rows = conn.execute(
                    """
                    SELECT concept_id
                    FROM concept_fts
                    WHERE concept_fts MATCH ? AND concept_type = ?
                    LIMIT ?
                    """,
                    (self._fts_query(query), concept_type, limit),
                ).fetchall()
            except sqlite3.OperationalError:
                return []
        return [row["concept_id"] for row in rows]

    def _rank(self, query: str, concepts: list[dict[str, Any]], *, project_id: str) -> list[dict[str, Any]]:
        scored: list[tuple[float, dict[str, Any]]] = []
        enriched_query = enrich_query(query)
        for concept in concepts:
            payload = concept.get("payload") or {}
            body = " ".join(
                [
                    str(concept.get("canonical_label") or ""),
                    str(concept.get("concept_type") or ""),
                    json.dumps(payload, ensure_ascii=False),
                    " ".join(str(link.get("evidence_span", "")) for link in concept.get("evidence_links", [])),
                ]
            )
            lexical = lexical_score(enriched_query, body) if query else 0.0
            validation = validation_number(str(concept.get("validation_level") or "L0"))
            evidence_count = len(concept.get("evidence_links") or [])
            score = lexical * 4.0 + validation * 0.08 + min(evidence_count, 4) * 0.08 + float(concept.get("confidence_score", 0) or 0) * 0.2
            if project_id:
                score += 0.08
            item = dict(concept)
            item["_score"] = round(score, 4)
            item["_score_components"] = {
                "lexical": round(lexical, 4),
                "validation_prior": validation,
                "evidence_count": evidence_count,
                "confidence": concept.get("confidence_score", 0),
            }
            item["why_retrieved"] = self._why_retrieved(query, item, lexical=lexical, evidence_count=evidence_count)
            scored.append((score, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in scored]

    def _why_retrieved(self, query: str, concept: dict[str, Any], *, lexical: float, evidence_count: int) -> list[str]:
        reasons = []
        if query and lexical > 0:
            reasons.append("matched lexical/semantic query terms")
        if concept.get("symbol"):
            reasons.append(f"symbol {concept['symbol'].get('short_code')} is available")
        if evidence_count:
            reasons.append(f"{evidence_count} evidence link(s)")
        if concept.get("validation_level"):
            reasons.append(f"validation: {concept.get('validation_level')}")
        return reasons or ["recent reusable concept card"]

    def _fts_query(self, query: str) -> str:
        terms = [term.replace('"', "") for term in enrich_query(query).split()[:8] if len(term) > 2]
        return " OR ".join(terms) if terms else query
