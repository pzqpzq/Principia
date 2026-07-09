from __future__ import annotations

import re
from typing import Any

from .constants import STOPWORDS
from .models import QueryPlan
from .utils import call_llm_json, clean_text, llm_available, normalize_text, ordered_unique, string_list, tokenize


class QueryPlanner:
    def __init__(self, llm: Any | None = None, *, use_llm: bool = True, model_mode: str = "auto") -> None:
        self.llm = llm
        self.use_llm = use_llm
        self.model_mode = model_mode

    def plan(self, goal_text: str, *, max_queries: int | None = None) -> QueryPlan:
        deterministic = deterministic_query_plan(goal_text)
        if not self.use_llm or not llm_available(self.llm):
            return deterministic
        try:
            payload = call_llm_json(
                self.llm,
                "You build academic literature search plans. Return strict JSON only.",
                (
                    "Given a research goal, produce a generic academic metadata search plan. "
                    "Return exactly one JSON object with keys: search_queries, entities, key_phrases.\n\n"
                    "Field definitions:\n"
                    "- search_queries: 5-8 concise plain-text academic search strings suitable for arXiv, "
                    "OpenAlex, Crossref, and Semantic Scholar. Each query should be a focused combination "
                    "of the goal's core task, object, method, constraint, metric, or mechanism. Preserve "
                    "important acronyms, exact names, model names, datasets, benchmarks, materials, organisms, "
                    "phenomena, and technical phrases from the goal. The queries must be complementary and "
                    "cover different retrieval dimensions; do not generate near-duplicate paraphrases of "
                    "the same query. Include useful alternative formulations "
                    "only when they are directly implied by the goal. Do not use source-specific syntax, "
                    "Boolean operators, negative filters, or broad generic filler terms.\n"
                    "- entities: explicit named entities mentioned in or directly required by the goal, such as "
                    "methods, systems, model names, datasets, benchmarks, instruments, organisms, materials, "
                    "phenomena, tasks, or acronyms. Do not include vague broad fields unless the goal names "
                    "them as targets.\n"
                    "- key_phrases: short noun phrases capturing the core concepts, mechanisms, constraints, "
                    "evaluation metrics, tasks, resources, or desired outcomes in the goal. Prefer 2-6 word "
                    "phrases that can help rank retrieved works.\n\n"
                    "Use the same generic strategy for every research goal. Do not classify the goal into a "
                    "domain, do not add exclusion terms, and do not return keys other than search_queries, "
                    "entities, and key_phrases.\n\n"
                    f"Research goal:\n{goal_text}"
                ),
                mode=self.model_mode,
                max_tokens=1200,
                temperature=0,
            )
        except Exception:
            return deterministic
        llm_queries = string_list(payload.get("search_queries"))
        entities = ordered_unique([*deterministic.entities, *string_list(payload.get("entities"))])
        phrases = ordered_unique([*deterministic.key_phrases, *string_list(payload.get("key_phrases"))])
        queries = mix_search_queries(deterministic.search_queries, llm_queries, goal_text, max_queries=max_queries)
        return QueryPlan(
            goal_text=goal_text,
            search_queries=queries,
            entities=entities,
            key_phrases=phrases,
            domain_hints=[],
            exclude_terms=[],
            ai_intent=False,
            trace={
                **deterministic.trace,
                "llm_planner": bool(llm_queries),
                "query_mixing": query_mixing_trace(deterministic.search_queries, llm_queries, goal_text, max_queries=max_queries),
            },
        )


def deterministic_query_plan(goal_text: str) -> QueryPlan:
    text = clean_text(goal_text)
    entities = extract_entities(text)
    phrases = extract_key_phrases(text)
    queries: list[str] = []
    for entity in entities[:4]:
        queries.append(entity)
        for phrase in phrases[:3]:
            queries.append(f"{entity} {phrase}")
    queries.extend(phrases[:6])
    query_from_terms = " ".join([*entities[:2], *phrases[:5]]).strip()
    if query_from_terms:
        queries.append(query_from_terms)
    queries.append(text)
    return QueryPlan(
        goal_text=text,
        search_queries=ordered_unique([q for q in queries if clean_text(q)]),
        entities=entities,
        key_phrases=phrases,
        domain_hints=[],
        exclude_terms=[],
        ai_intent=False,
        trace={"deterministic": True},
    )


def mix_search_queries(
    deterministic_queries: list[str],
    llm_queries: list[str],
    goal_text: str,
    *,
    max_queries: int | None = None,
) -> list[str]:
    deterministic = unique_queries(deterministic_queries)
    llm = unique_queries(llm_queries)
    goal = clean_text(goal_text)
    if not llm:
        return deterministic
    if max_queries is None:
        return unique_queries([*deterministic[:2], *llm, goal, *deterministic[2:]])

    budget = max(1, int(max_queries or 1))
    if budget == 1:
        return unique_queries([goal, *llm, *deterministic])[:1]

    goal_key = query_key(goal)
    deterministic_pool = [query for query in deterministic if query_key(query) != goal_key]
    llm_pool = [query for query in llm if query_key(query) != goal_key]

    fallback_budget = 1 if goal else 0
    if budget <= 2:
        anchor_budget = min(1, len(deterministic_pool), budget)
        llm_budget = max(0, budget - anchor_budget - fallback_budget)
    else:
        anchor_budget = min(2, max(1, budget // 4), len(deterministic_pool), max(0, budget - fallback_budget))
        llm_budget = max(0, budget - anchor_budget - fallback_budget)

    mixed = [
        *deterministic_pool[:anchor_budget],
        *llm_pool[:llm_budget],
        goal,
        *llm_pool[llm_budget:],
        *deterministic_pool[anchor_budget:],
    ]
    return unique_queries(mixed)[:budget]


def query_mixing_trace(
    deterministic_queries: list[str],
    llm_queries: list[str],
    goal_text: str,
    *,
    max_queries: int | None = None,
) -> dict[str, Any]:
    mixed = mix_search_queries(deterministic_queries, llm_queries, goal_text, max_queries=max_queries)
    return {
        "max_queries": max_queries,
        "deterministic_query_count": len(unique_queries(deterministic_queries)),
        "llm_query_count": len(unique_queries(llm_queries)),
        "mixed_query_count": len(mixed),
        "goal_fallback_included": query_key(goal_text) in {query_key(query) for query in mixed},
    }


def unique_queries(values: list[Any]) -> list[str]:
    output = []
    seen = set()
    for value in values:
        text = clean_text(value)
        key = query_key(text)
        if text and key and key not in seen:
            output.append(text)
            seen.add(key)
    return output


def query_key(value: Any) -> str:
    return normalize_text(clean_text(value))


def extract_entities(text: str) -> list[str]:
    entities = []
    patterns = [
        r"\b[A-Z]\d{5,}[A-Za-z0-9]*\b",
        r"\b[A-Z]{2,}[A-Za-z]*\d+[A-Za-z0-9\-]*\b",
        r"\barXiv:\d{4}\.\d{4,5}(?:v\d+)?\b",
        r"\b(?:GW|GRB|AT|SN|FRB|ZTF|S)\d{4,}[A-Za-z0-9]*\b",
    ]
    for pattern in patterns:
        entities.extend(re.findall(pattern, text))
    return ordered_unique(entities)


def extract_key_phrases(text: str) -> list[str]:
    lower = clean_text(text).lower()
    tokens = [token for token in tokenize(lower) if token not in STOPWORDS]
    candidates = []
    for size in (3, 2):
        for index in range(0, max(0, len(tokens) - size + 1)):
            candidates.append(" ".join(tokens[index : index + size]))
    candidates.extend(tokens[:12])
    return ordered_unique(candidates)
