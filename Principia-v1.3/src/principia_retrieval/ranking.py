from __future__ import annotations

import json
from typing import Any

from .constants import RELATION_ORDER
from .models import QueryPlan
from .utils import call_llm_json, clamp_float, clean_text, contains_query_trigger, normalize_text, stable_id, truncate, weighted_tokens


def deterministic_rank(goal_text: str, works: list[dict[str, Any]], plan: QueryPlan) -> list[dict[str, Any]]:
    scored = []
    goal_tokens = weighted_tokens(goal_text)
    for work in works:
        item = dict(work)
        body = work_text(item)
        relevance = semantic_lite_score(goal_text, body, plan, goal_tokens=goal_tokens)
        metadata = metadata_score(item)
        ai_penalty = 0.22 if is_ai_work(item) and not plan.ai_intent else 0.0
        exact_bonus = 0.35 if has_exact_entity(item, plan) else 0.0
        final = max(0.0, relevance + metadata + exact_bonus - ai_penalty)
        relation = relation_from_score(final, exact_bonus, relevance)
        item["_retrieval_score"] = final
        item["relation_label"] = relation
        item["retrieval_rationale"] = deterministic_rationale(item, plan, relevance, exact_bonus, ai_penalty)
        item["reject_reason"] = "AI-focused work for non-AI goal" if ai_penalty and relation == "out_of_scope" else ""
        item.setdefault("community_signals", {})["retrieval_score"] = round(final, 4)
        item.setdefault("community_signals", {})["relation_label"] = relation
        scored.append(item)
    scored.sort(key=lambda item: (float(item.get("_retrieval_score", 0.0)), relation_rank(item), int(item.get("year") or 0)), reverse=True)
    return scored


def llm_rerank(goal_text: str, works: list[dict[str, Any]], plan: QueryPlan, llm: Any, *, batch_size: int) -> list[dict[str, Any]]:
    by_id = {str(work.get("work_id") or stable_id("W", work.get("title", ""))): dict(work) for work in works}
    updates: dict[str, dict[str, Any]] = {}
    rows = list(by_id.values())
    for index in range(0, len(rows), max(1, batch_size)):
        batch = rows[index : index + batch_size]
        payload = [
            {
                "work_id": work.get("work_id"),
                "title": work.get("title"),
                "abstract": truncate(work.get("abstract", ""), 900),
                "venue": work.get("venue_or_source"),
                "year": work.get("year"),
            }
            for work in batch
        ]
        try:
            result = call_llm_json(
                llm,
                "You semantically rank candidate research works for a research goal. Return strict JSON only.",
                (
                    "Return JSON with key items. Each item must include work_id, relevance_score between 0 and 1, "
                    "relation_label as one of direct/background/methodological/out_of_scope, rationale, reject_reason. "
                    "Direct means the work directly studies the target object, method, mechanism, or phenomenon. "
                    "Do not reward AI/LLM papers for non-AI goals just because they mention scientific discovery.\n\n"
                    f"Research goal:\n{goal_text}\n\nCandidate works:\n{json.dumps(payload, ensure_ascii=False)}"
                ),
                mode="auto",
                max_tokens=2600,
                temperature=0,
            )
        except Exception:
            continue
        for row in result.get("items", []) if isinstance(result, dict) else []:
            if isinstance(row, dict) and row.get("work_id"):
                updates[str(row["work_id"])] = row
    output = []
    for work in rows:
        item = dict(work)
        row = updates.get(str(item.get("work_id") or ""))
        if row:
            label = normalize_relation(row.get("relation_label"))
            llm_score = clamp_float(row.get("relevance_score"), 0.0, 1.0)
            metadata = metadata_score(item)
            if is_ai_work(item) and not plan.ai_intent and label not in {"direct", "background"}:
                llm_score *= 0.25
            item["_retrieval_score"] = llm_score * 1.25 + metadata
            item["relation_label"] = label
            item["retrieval_rationale"] = clean_text(row.get("rationale") or item.get("retrieval_rationale") or "")
            item["reject_reason"] = clean_text(row.get("reject_reason") or "")
            item.setdefault("community_signals", {})["llm_relevance_score"] = round(llm_score, 4)
            item.setdefault("community_signals", {})["relation_label"] = label
        output.append(item)
    output.sort(key=lambda item: (float(item.get("_retrieval_score", 0.0)), relation_rank(item), int(item.get("year") or 0)), reverse=True)
    return output


def final_select(works: list[dict[str, Any]], target_count: int, plan: QueryPlan) -> list[dict[str, Any]]:
    selected = []
    for work in works:
        label = normalize_relation(work.get("relation_label"))
        if label == "out_of_scope" and not has_exact_entity(work, plan) and float(work.get("_retrieval_score", 0.0)) < 0.18:
            continue
        if is_ai_work(work) and not plan.ai_intent and label not in {"direct", "background"}:
            continue
        selected.append(work)
        if len(selected) >= target_count:
            break
    return selected or works[:target_count]


def semantic_lite_score(goal_text: str, text: str, plan: QueryPlan, *, goal_tokens: dict[str, float] | None = None) -> float:
    body = normalize_text(text)
    if not body:
        return 0.0
    goal_tokens = goal_tokens or weighted_tokens(goal_text)
    text_tokens = weighted_tokens(text)
    overlap = sum(weight for token, weight in goal_tokens.items() if token in text_tokens)
    coverage = overlap / max(1.0, sum(goal_tokens.values()))
    phrase_bonus = 0.0
    for phrase in plan.key_phrases[:12]:
        if normalize_text(phrase) and normalize_text(phrase) in body:
            phrase_bonus += 0.055
    entity_bonus = 0.0
    for entity in plan.entities:
        if normalize_text(entity) and normalize_text(entity) in body:
            entity_bonus += 0.18
    return min(1.0, coverage + min(0.35, phrase_bonus) + min(0.5, entity_bonus))


def metadata_score(work: dict[str, Any]) -> float:
    year = int(work.get("year") or 0) if str(work.get("year") or "").isdigit() else 0
    recency = min(max(year - 2016, 0), 12) / 12 if year else 0.0
    citation = min(int(work.get("citation_count") or 0), 500) / 500 if str(work.get("citation_count") or "0").isdigit() else 0.0
    venue = venue_quality(str(work.get("venue_or_source") or ""))
    abstract = 1.0 if work.get("abstract") else 0.0
    link = 1.0 if work.get("url_or_doi") or work.get("source_urls") else 0.0
    return recency * 0.05 + citation * 0.03 + venue * 0.03 + abstract * 0.025 + link * 0.01


def is_ai_work(work: dict[str, Any]) -> bool:
    text = normalize_text(work_text(work))
    return any(contains_query_trigger(text, term) for term in ["large language model", "llm", "multi-agent", "ai agent", "machine learning", "deep learning", "reinforcement learning"])


def has_exact_entity(work: dict[str, Any], plan: QueryPlan) -> bool:
    text = normalize_text(work_text(work))
    return any(normalize_text(entity) and normalize_text(entity) in text for entity in plan.entities)


def deterministic_rationale(work: dict[str, Any], plan: QueryPlan, relevance: float, exact_bonus: float, ai_penalty: float) -> str:
    bits = []
    if exact_bonus:
        bits.append("matches target entity")
    matched = [phrase for phrase in plan.key_phrases if normalize_text(phrase) and normalize_text(phrase) in normalize_text(work_text(work))]
    if matched:
        bits.append("matches " + ", ".join(matched[:3]))
    if ai_penalty:
        bits.append("AI-topic penalty for non-AI goal")
    if not bits:
        bits.append(f"lexical-semantic overlap {relevance:.2f}")
    return "; ".join(bits)


def relation_from_score(final: float, exact_bonus: float, relevance: float) -> str:
    if exact_bonus or final >= 0.48:
        return "direct"
    if final >= 0.28:
        return "background"
    if relevance >= 0.12:
        return "methodological"
    return "out_of_scope"


def relation_rank(work: dict[str, Any]) -> int:
    return RELATION_ORDER.get(normalize_relation(work.get("relation_label")), 0)


def normalize_relation(value: Any) -> str:
    label = str(value or "").strip().lower()
    return label if label in RELATION_ORDER else "out_of_scope"


def venue_quality(venue: str) -> float:
    value = venue.lower()
    if not value or value in {"arxiv", "openalex", "crossref", "semantic scholar"}:
        return 0.0
    if any(term in value for term in ["nature", "science", "neurips", "icml", "iclr", "cvpr", "acl", "emnlp", "astrophysical journal", "astronomy", "monthly notices"]):
        return 1.0
    return 0.55


def work_text(work: dict[str, Any]) -> str:
    return " ".join(str(work.get(key) or "") for key in ["title", "abstract", "venue_or_source"])
