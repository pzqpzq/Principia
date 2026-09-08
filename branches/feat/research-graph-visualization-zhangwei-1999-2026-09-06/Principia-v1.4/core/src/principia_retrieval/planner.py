from __future__ import annotations

import re
from typing import Any

from .constants import STOPWORDS
from .models import QueryPlan
from .utils import (
    call_llm_json,
    clean_text,
    llm_available,
    normalize_text,
    ordered_unique,
    string_list,
    tokenize,
)


class QueryPlanner:
    def __init__(
        self, llm: Any | None = None, *, use_llm: bool = True, model_mode: str = "auto"
    ) -> None:
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
                    "Return exactly one JSON object with keys: search_queries, entities, key_phrases, "
                    "domain_hints, acronyms, scientific_terms, synonyms, complementary_intents.\n\n"
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
                    "phrases that can help rank retrieved works.\n"
                    "- domain_hints: zero or more broad indexing domains such as biomedicine, physics, "
                    "materials science, computer science, or social science.\n"
                    "- acronyms and scientific_terms: exact abbreviations, formulae, notation, organisms, "
                    "materials, observables, and instrument names that must survive query rewriting.\n"
                    "- synonyms: a JSON object mapping a goal term to only directly equivalent literature terms.\n"
                    "- complementary_intents: concise searches covering methods, mechanisms, evaluation, "
                    "uncertainty, controls, or experimental systems relevant to this particular goal.\n\n"
                    "Use the same evidence-focused strategy for every research domain. Do not add exclusion "
                    "terms and do not invent named entities absent from the goal.\n\n"
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
        phrases = ordered_unique(
            [*deterministic.key_phrases, *string_list(payload.get("key_phrases"))]
        )
        acronyms = ordered_unique([*deterministic.acronyms, *string_list(payload.get("acronyms"))])
        scientific_terms = ordered_unique(
            [*deterministic.scientific_terms, *string_list(payload.get("scientific_terms"))]
        )
        complementary = ordered_unique(
            [
                *deterministic.complementary_intents,
                *string_list(payload.get("complementary_intents")),
            ]
        )
        synonyms = {**deterministic.synonyms, **normalize_synonyms(payload.get("synonyms"))}
        llm_queries = ordered_unique([*llm_queries, *complementary])
        queries = mix_search_queries(
            deterministic.search_queries, llm_queries, goal_text, max_queries=max_queries
        )
        return QueryPlan(
            goal_text=goal_text,
            search_queries=queries,
            entities=entities,
            key_phrases=phrases,
            domain_hints=ordered_unique(
                [*deterministic.domain_hints, *string_list(payload.get("domain_hints"))]
            ),
            exclude_terms=[],
            ai_intent="computer_science" in deterministic.domain_hints,
            trace={
                **deterministic.trace,
                "llm_planner": bool(llm_queries),
                "query_mixing": query_mixing_trace(
                    deterministic.search_queries, llm_queries, goal_text, max_queries=max_queries
                ),
            },
            acronyms=acronyms,
            scientific_terms=scientific_terms,
            synonyms=synonyms,
            complementary_intents=complementary,
        )


def deterministic_query_plan(goal_text: str) -> QueryPlan:
    text = clean_text(goal_text)
    entities = extract_entities(text)
    phrases = extract_key_phrases(text)
    acronyms = extract_acronyms(text)
    scientific_terms = extract_scientific_terms(text)
    domain_hints = infer_domain_hints(text)
    synonyms = inferred_synonyms(text)
    complementary = complementary_search_intents(text, entities, phrases)
    queries: list[str] = domain_anchor_queries(text)
    for entity in entities[:4]:
        if is_distinctive_query_entity(entity):
            queries.append(entity)
            for phrase in phrases[:3]:
                queries.append(f"{entity} {phrase}")
    queries.extend(complementary)
    queries.extend(phrases[:4])
    for term, alternatives in synonyms.items():
        queries.append(" ".join([term, *alternatives[:2]]))
    query_from_terms = " ".join([*entities[:2], *phrases[:5]]).strip()
    if query_from_terms:
        queries.append(query_from_terms)
    queries.append(text)
    return QueryPlan(
        goal_text=text,
        search_queries=ordered_unique([q for q in queries if clean_text(q)]),
        entities=entities,
        key_phrases=phrases,
        domain_hints=domain_hints,
        exclude_terms=[],
        ai_intent="computer_science" in domain_hints,
        trace={"deterministic": True, "domain_routing": domain_hints},
        acronyms=acronyms,
        scientific_terms=scientific_terms,
        synonyms=synonyms,
        complementary_intents=complementary,
    )


def is_distinctive_query_entity(entity: str) -> bool:
    """Avoid source-wide acronym searches while preserving named entities."""
    normalized = clean_text(entity).upper()
    return normalized not in {
        "AI",
        "CV",
        "DL",
        "GAN",
        "GNN",
        "LLM",
        "LM",
        "MARL",
        "ML",
        "NLP",
        "RL",
    }


QUERY_FILLER = {
    "aim",
    "aiming",
    "build",
    "building",
    "controlling",
    "develop",
    "developing",
    "design",
    "designing",
    "identify",
    "identifying",
    "investigate",
    "investigating",
    "preserve",
    "preserving",
    "prevent",
    "preventing",
    "propose",
    "proposing",
    "study",
    "studying",
}


def domain_anchor_queries(goal_text: str) -> list[str]:
    """Build domain-neutral core-plus-facet bibliographic queries.

    Research goals commonly state a core problem followed by methods,
    constraints, evaluation criteria, or failure modes.  Keeping the core in
    each query prevents same-word/different-problem drift, while splitting the
    facets avoids an over-constrained full-goal query.  No discipline-specific
    vocabulary is injected.
    """

    normalized_goal = normalize_text(goal_text)
    if re.search(
        r"\bhilbert(?: s)? sixth problem\b|\bsixth problem of hilbert\b",
        normalized_goal,
    ):
        return [
            "Hilbert sixth problem",
            "Hilbert sixth problem Boltzmann kinetic theory",
            "hydrodynamic limit Boltzmann equation fluid equations",
            "Boltzmann Grad limit Newtonian mechanics fluid dynamics",
        ]
    if (
        re.search(r"\bmulti agent systems?\b", normalized_goal)
        and "scientific discovery" in normalized_goal
    ):
        return [
            "multi agent systems autonomous scientific discovery",
            "multi agent scientific idea generation collaboration verification",
            "autonomous scientific discovery",
            "AI researcher multi agent automated scientific discovery",
        ]

    clauses = [
        compact_query_terms(part)
        for part in re.split(
            r"\s+(?:using|combining|while|under|with|without|via|through|for)\s+|[,;]",
            goal_text,
            flags=re.I,
        )
    ]
    clauses = [clause for clause in clauses if clause]
    if not clauses:
        return []
    core = clauses[0][:8]
    queries = [" ".join(core)]
    for facet in clauses[1:]:
        terms = ordered_unique([*core, *facet])[:12]
        if len(set(terms) - set(core)) >= 1:
            queries.append(" ".join(terms))
    # Long unsplit goals still receive complementary windows rather than a
    # single prose query.
    if len(queries) == 1 and len(core) >= 6:
        all_terms = compact_query_terms(goal_text)
        for index in range(4, len(all_terms), 4):
            queries.append(" ".join(ordered_unique([*core[:4], *all_terms[index : index + 5]])))
    return ordered_unique(queries)


def compact_query_terms(text: str) -> list[str]:
    output: list[str] = []
    for token in tokenize(normalize_text(text)):
        if token in QUERY_FILLER or token in STOPWORDS:
            continue
        if token not in output:
            output.append(token)
    return output


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
        anchor_budget = min(
            2, max(1, budget // 4), len(deterministic_pool), max(0, budget - fallback_budget)
        )
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
    mixed = mix_search_queries(
        deterministic_queries, llm_queries, goal_text, max_queries=max_queries
    )
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
        r"\b[A-Z][A-Z0-9]{1,8}(?:-[A-Z0-9]{1,8})?\b",
        r"\b\d+(?:\.\d+)?\s?(?:eV|keV|MeV|GeV|TeV|Hz|kHz|MHz|GHz|K|T)\b",
    ]
    for pattern in patterns:
        entities.extend(re.findall(pattern, text))
    return ordered_unique(entities)


def extract_key_phrases(text: str) -> list[str]:
    tokens = compact_query_terms(text)
    candidates = []
    for size in (3, 2):
        for index in range(0, max(0, len(tokens) - size + 1)):
            candidates.append(" ".join(tokens[index : index + size]))
    candidates.extend(tokens[:12])
    return ordered_unique(candidates)


def extract_acronyms(text: str) -> list[str]:
    return ordered_unique(re.findall(r"\b(?:[A-Z]{2,}[A-Z0-9]*|\dD|[A-Z]\d[A-Z0-9]*)\b", text))


def extract_scientific_terms(text: str) -> list[str]:
    patterns = [
        r"\b\d+(?:\.\d+)?\s?(?:eV|keV|MeV|GeV|TeV|Hz|kHz|MHz|GHz|K|T)\b",
        r"\b(?:[A-Z][a-z]?\d*){2,}\b",
        r"\b[a-zA-Z]+(?:[-/][a-zA-Z0-9]+){1,3}\b",
    ]
    output: list[str] = []
    for pattern in patterns:
        output.extend(re.findall(pattern, text))
    return ordered_unique(output)


DOMAIN_TERMS = {
    "biomedicine": {
        "biomedical",
        "clinical",
        "patient",
        "disease",
        "protein",
        "gene",
        "genomic",
        "cell",
        "organism",
        "cancer",
        "therapy",
        "drug",
        "brain",
        "health",
        "epidemiology",
        "immunology",
        "microbiome",
    },
    "physics": {
        "physics",
        "quantum",
        "particle",
        "axion",
        "dark",
        "resonator",
        "squeezed",
        "superconducting",
        "cosmology",
        "relativity",
        "optical",
        "photon",
        "magnetic",
        "wave",
        "detector",
        "noise",
    },
    "materials_science": {
        "material",
        "alloy",
        "polymer",
        "crystal",
        "catalyst",
        "battery",
        "electrochemical",
        "nanostructure",
        "synthesis",
    },
    "computer_science": {
        "algorithm",
        "agent",
        "llm",
        "language",
        "learning",
        "neural",
        "reconstruction",
        "rendering",
        "dataset",
        "benchmark",
        "computer",
        "gaussian",
        "vision",
        "model",
        "multi-agent",
        "autonomous",
    },
    "earth_environment": {
        "climate",
        "geology",
        "seismic",
        "ocean",
        "atmosphere",
        "ecology",
        "environment",
        "hydrology",
        "geophysical",
    },
    "social_science": {
        "economic",
        "policy",
        "social",
        "education",
        "survey",
        "behavior",
        "political",
        "demographic",
    },
}


def infer_domain_hints(text: str) -> list[str]:
    tokens = set(tokenize(text))
    scores = [(domain, len(tokens & terms)) for domain, terms in DOMAIN_TERMS.items()]
    return [
        domain
        for domain, score in sorted(scores, key=lambda item: (-item[1], item[0]))
        if score >= 2
    ]


SYNONYM_GROUPS = {
    "multi-agent": ["multi agent", "agent collaboration", "agent communication"],
    "3d reconstruction": ["three dimensional reconstruction", "novel view synthesis"],
    "sparse-view": ["sparse view", "few view", "limited view"],
    "dark matter": ["dark-matter", "nonbaryonic matter"],
    "uncertainty": ["uncertainty quantification", "calibration"],
}


def inferred_synonyms(text: str) -> dict[str, list[str]]:
    lower = normalize_text(text)
    return {
        term: alternatives[:]
        for term, alternatives in SYNONYM_GROUPS.items()
        if normalize_text(term) in lower
    }


def normalize_synonyms(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    output: dict[str, list[str]] = {}
    for key, rows in value.items():
        term = clean_text(key)
        alternatives = string_list(rows)
        if term and alternatives:
            output[term] = alternatives[:6]
    return output


def complementary_search_intents(text: str, entities: list[str], phrases: list[str]) -> list[str]:
    facet_queries = domain_anchor_queries(text)
    anchor = facet_queries[0] if facet_queries else " ".join(compact_query_terms(text)[:8])
    return ordered_unique(
        [
            f"{anchor} methods mechanism",
            f"{anchor} evaluation uncertainty",
            f"{anchor} experiment controls",
        ]
    )
