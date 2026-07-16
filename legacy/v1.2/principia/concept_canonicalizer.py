from __future__ import annotations

import json
import re
from typing import Any

from .utils import stable_id
from .work_versioning import text_hash


CONCEPT_PREFIX = {
    "existed_idea": "XI",
    "principle": "P",
    "takeaway_message": "TM",
    "benchmark": "B",
    "baseline": "BL",
    "result_fact": "RF",
    "generated_idea": "I",
    "derived_concept": "D",
    "argument": "ARG",
    "hypothesis": "H",
    "deduction": "D",
    "failure_mode": "F",
    "assumption": "A",
    "user_note": "N",
}


def canonical_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def summarize_payload(payload: dict[str, Any]) -> str:
    fields = [
        "title",
        "name",
        "canonical_label",
        "idea_text",
        "message_text",
        "one_sentence_thesis",
        "abstract_signature",
        "mechanism",
        "summary",
        "benchmark_name",
        "baseline_name",
        "dataset",
    ]
    parts: list[str] = []
    for field in fields:
        value = payload.get(field)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    for field in ("mechanism_design", "why_it_might_work", "validation_protocol", "failure_modes", "domain_tags"):
        value = payload.get(field)
        if isinstance(value, list):
            parts.extend(str(item) for item in value[:4] if item)
    return " ".join(parts).strip()


def canonical_label(concept_type: str, payload: dict[str, Any], key_text: str = "") -> str:
    for key in ("title", "name", "benchmark_name", "baseline_name", "dataset", "canonical_label"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value[:180]
    if concept_type == "takeaway_message":
        return str(payload.get("message_text") or key_text or "Takeaway message")[:180]
    if concept_type == "existed_idea":
        return str(payload.get("idea_text") or key_text or "Existed idea")[:180]
    return str(key_text or summarize_payload(payload) or concept_type.replace("_", " ").title())[:180]


class ConceptCanonicalizer:
    def canonical_key(self, concept_type: str, payload: dict[str, Any], key_text: str = "") -> str:
        label = canonical_label(concept_type, payload, key_text)
        body = summarize_payload(payload)
        source_hint = ",".join(str(item) for item in payload.get("source_work_ids") or payload.get("source_works") or [])
        return canonical_text(f"{label} {body[:260]} {source_hint}")[:300]

    def concept_id(self, concept_type: str, canonical_key: str, public_scope: str = "project_private") -> str:
        prefix = CONCEPT_PREFIX.get(concept_type, "C")
        return stable_id(prefix, concept_type, canonical_key, public_scope)

    def version_id(
        self,
        concept_id: str,
        payload: dict[str, Any],
        *,
        extraction_run_id: str = "",
        model_mode: str = "auto",
        llm_model: str = "",
        is_manual_edit: bool = False,
    ) -> str:
        return stable_id(
            "CV",
            concept_id,
            extraction_run_id,
            "manual" if is_manual_edit else model_mode,
            "manual" if is_manual_edit else llm_model,
            text_hash(json.dumps(payload, sort_keys=True, ensure_ascii=False)),
        )

    def quality_score(self, payload: dict[str, Any], *, evidence_count: int = 0, is_manual_edit: bool = False) -> float:
        body = summarize_payload(payload)
        specificity = min(len(body) / 900, 1.0)
        list_fields = sum(1 for key, value in payload.items() if isinstance(value, list) and value)
        evidence_support = min(evidence_count / 2, 1.0)
        score = 0.3 * evidence_support + 0.2 * specificity + 0.2 * min(list_fields / 5, 1.0) + 0.2
        if is_manual_edit:
            score += 0.1
        return round(max(0.05, min(score, 1.0)), 4)
