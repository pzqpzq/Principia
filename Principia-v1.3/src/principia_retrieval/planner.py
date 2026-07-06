from __future__ import annotations

import re
from typing import Any

from .constants import STOPWORDS
from .models import QueryPlan
from .utils import call_llm_json, clean_text, contains_query_trigger, llm_available, ordered_unique, string_list, tokenize


class QueryPlanner:
    def __init__(self, llm: Any | None = None, *, use_llm: bool = True, model_mode: str = "auto") -> None:
        self.llm = llm
        self.use_llm = use_llm
        self.model_mode = model_mode

    def plan(self, goal_text: str) -> QueryPlan:
        deterministic = deterministic_query_plan(goal_text)
        if not self.use_llm or not llm_available(self.llm):
            return deterministic
        try:
            payload = call_llm_json(
                self.llm,
                "You build academic literature search plans. Return strict JSON only.",
                (
                    "Given a research goal, return JSON with keys: search_queries, entities, key_phrases, "
                    "domain_hints, exclude_terms. Search queries must be concise academic search strings. "
                    "Do not inject AI/LLM terms unless the goal explicitly asks for AI, LLMs, agents, or machine learning.\n\n"
                    f"Research goal:\n{goal_text}"
                ),
                mode=self.model_mode,
                max_tokens=1200,
                temperature=0,
            )
        except Exception:
            return deterministic
        raw_llm_queries = string_list(payload.get("search_queries"))
        llm_queries = [query for query in raw_llm_queries if deterministic.ai_intent or not is_ai_goal(query)]
        entities = ordered_unique([*deterministic.entities, *string_list(payload.get("entities"))])
        phrases = ordered_unique([*deterministic.key_phrases, *string_list(payload.get("key_phrases"))])
        hints = ordered_unique([*deterministic.domain_hints, *string_list(payload.get("domain_hints"))])
        excludes = ordered_unique([*deterministic.exclude_terms, *string_list(payload.get("exclude_terms"))])
        queries = ordered_unique([*deterministic.search_queries, *llm_queries])
        return QueryPlan(
            goal_text=goal_text,
            search_queries=queries,
            entities=entities,
            key_phrases=phrases,
            domain_hints=hints,
            exclude_terms=excludes,
            ai_intent=deterministic.ai_intent,
            trace={**deterministic.trace, "llm_planner": bool(llm_queries), "llm_queries_filtered": len(raw_llm_queries) - len(llm_queries)},
        )


def deterministic_query_plan(goal_text: str) -> QueryPlan:
    text = clean_text(goal_text)
    entities = extract_entities(text)
    phrases = extract_key_phrases(text)
    ai_intent = is_ai_goal(text)
    hints = domain_hints(text)
    queries: list[str] = []
    for entity in entities[:4]:
        queries.append(entity)
        for phrase in phrases[:3]:
            queries.append(f"{entity} {phrase}")
    if "astronomy_transient" in hints:
        queries.extend(
            [
                " ".join([*entities[:1], "kilonova electromagnetic counterpart compact object merger"]).strip(),
                "kilonova compact object merger electromagnetic counterpart",
                "optical transient gravitational wave counterpart kilonova",
                "AGN disk merger flare optical transient",
                "supernova contaminant kilonova gravitational wave follow-up",
            ]
        )
    if "vision" in hints:
        queries.extend(
            [
                "test-time adaptation CLIP few-shot learning",
                "few-shot vision-language model CLIP",
                "prompt learning CLIP parameter-efficient tuning",
            ]
        )
    if "3d_reconstruction" in hints:
        queries.extend(
            [
                "sparse view 3d reconstruction",
                "few view 3d reconstruction neural radiance fields",
                "3d gaussian splatting sparse view",
            ]
        )
    if ai_intent:
        queries.extend(
            [
                "large language model multi-agent systems",
                "LLM agents scientific discovery",
                "agent communication large language model",
                "multi-agent debate reasoning",
            ]
        )
    query_from_terms = " ".join([*entities[:2], *phrases[:5]]).strip()
    if query_from_terms:
        queries.append(query_from_terms)
    queries.append(text)
    return QueryPlan(
        goal_text=text,
        search_queries=ordered_unique([q for q in queries if clean_text(q)]),
        entities=entities,
        key_phrases=phrases,
        domain_hints=hints,
        exclude_terms=exclude_terms_for_goal(text, ai_intent),
        ai_intent=ai_intent,
        trace={"deterministic": True},
    )


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
    candidates = []
    known = [
        "sub-solar-mass",
        "compact-object merger",
        "compact object merger",
        "electromagnetic emission",
        "electromagnetic counterpart",
        "optical transient",
        "follow-up",
        "kilonova",
        "kilonovae",
        "agn-disk",
        "agn disk",
        "supernova contaminants",
        "large language model",
        "multi-agent",
        "machine dialect",
        "test-time training",
        "few-shot learning",
        "3d reconstruction",
        "sparse view",
    ]
    for phrase in known:
        if contains_query_trigger(lower, phrase):
            candidates.append(phrase)
    tokens = [token for token in tokenize(lower) if token not in STOPWORDS]
    candidates.extend(tokens[:10])
    return ordered_unique(candidates)


def domain_hints(text: str) -> list[str]:
    lower = text.lower()
    hints = []
    if any(
        contains_query_trigger(lower, term)
        for term in [
            "kilonova",
            "optical transient",
            "gravitational wave",
            "compact object merger",
            "sub-solar-mass",
            "agn disk",
            "agn-disk",
            "supernova contaminant",
        ]
    ):
        hints.append("astronomy_transient")
    if any(contains_query_trigger(lower, term) for term in ["3d reconstruction", "sparse view", "few view", "neural radiance fields", "gaussian splatting"]):
        hints.append("3d_reconstruction")
    if any(contains_query_trigger(lower, term) for term in ["clip", "few-shot", "test-time training", "vision-language"]):
        hints.append("vision")
    if is_ai_goal(lower):
        hints.append("ai")
    return hints


def exclude_terms_for_goal(text: str, ai_intent: bool) -> list[str]:
    excludes = []
    if not ai_intent:
        excludes.extend(["large language model", "llm", "multi-agent llm", "ai agent"])
    if "astronomy_transient" in domain_hints(text):
        excludes.extend(["grounded source transient electromagnetic", "geophysical", "mineral exploration"])
    return excludes


def is_ai_goal(text: str) -> bool:
    lower = text.lower()
    triggers = [
        "llm",
        "ai",
        "artificial intelligence",
        "large language model",
        "language model",
        "ai agent",
        "agentic ai",
        "multi-agent",
        "multi agent",
        "agent communication",
        "machine dialect",
        "prompt learning",
        "neural network",
        "deep learning",
        "reinforcement learning",
        "machine learning",
    ]
    return any(contains_query_trigger(lower, trigger) for trigger in triggers) or contains_query_trigger(lower, "MAS")
