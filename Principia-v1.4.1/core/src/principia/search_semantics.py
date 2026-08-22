from __future__ import annotations

import re
from collections.abc import Iterable

SEARCH_SEMANTICS_VERSION = "principia-concept-search-v1"

_TOKEN = re.compile(r"[a-z0-9][a-z0-9_-]+")
_COMPOUND_TERMS = (
    ("multi agent", "multi-agent"),
    ("language model", "language-model"),
    ("foundation model", "foundation-model"),
    ("low rank", "low-rank"),
    ("fine tuning", "fine-tuning"),
    ("parameter efficient", "parameter-efficient"),
    ("scientific discovery", "scientific-discovery"),
)
_QUERY_SCAFFOLD = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "being",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "for",
        "from",
        "had",
        "has",
        "have",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "may",
        "might",
        "of",
        "on",
        "or",
        "our",
        "should",
        "that",
        "the",
        "their",
        "these",
        "this",
        "those",
        "to",
        "using",
        "via",
        "was",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "would",
    }
)

# These families are deliberately scientific and mechanism-oriented.  They are
# an offline fallback when a verified Cloud release has no vectors or the
# configured embedding provider is unavailable.  A family is activated by any
# member, so a goal can retrieve useful Principles even when the paper and the
# user use different terminology.
_CONCEPT_FAMILIES: tuple[frozenset[str], ...] = (
    frozenset(
        {
            "agent",
            "agents",
            "multi-agent",
            "multiagent",
            "team",
            "teams",
            "coordination",
            "collaboration",
            "cooperation",
            "swarm",
            "collective",
            "decentralized",
            "specialization",
        }
    ),
    frozenset(
        {
            "theorem",
            "proving",
            "prover",
            "proof",
            "proofs",
            "deduction",
            "formal",
            "verification",
            "lean",
            "coq",
            "isabelle",
        }
    ),
    frozenset(
        {
            "math",
            "mathematics",
            "mathematical",
            "equation",
            "equations",
            "symbolic",
            "algebraic",
            "geometry",
        }
    ),
    frozenset(
        {
            "science",
            "scientific",
            "scientific-discovery",
            "research",
            "discovery",
            "experiment",
            "experimentation",
            "hypothesis",
            "laboratory",
            "autonomous",
            "agentic",
            "automation",
        }
    ),
    frozenset(
        {
            "reasoning",
            "inference",
            "deliberation",
            "planning",
            "search",
            "reflection",
            "critic",
            "verification",
            "self-correction",
        }
    ),
    frozenset(
        {
            "llm",
            "language-model",
            "transformer",
            "foundation-model",
            "generative",
            "prompting",
            "instruction",
        }
    ),
    frozenset(
        {
            "lora",
            "low-rank",
            "adapter",
            "adapters",
            "finetuning",
            "fine-tuning",
            "parameter-efficient",
            "peft",
        }
    ),
    frozenset(
        {
            "robust",
            "robustness",
            "reliable",
            "reliability",
            "fault",
            "faults",
            "resilient",
            "resilience",
            "recovery",
            "stability",
        }
    ),
    frozenset(
        {
            "memory",
            "persistent",
            "persistence",
            "history",
            "context",
            "retrieval",
            "knowledge",
            "archive",
        }
    ),
    frozenset(
        {
            "hilbert",
            "boltzmann",
            "kinetic",
            "hydrodynamic",
            "fluid",
            "continuum",
            "hard-sphere",
        }
    ),
    frozenset(
        {
            "physics",
            "physical",
            "simulation",
            "simulator",
            "dynamics",
            "mechanistic",
            "modeling",
        }
    ),
    frozenset(
        {
            "improve",
            "improves",
            "improved",
            "improving",
            "enhance",
            "enhances",
            "increase",
            "increases",
            "enable",
            "enables",
            "optimize",
            "optimizes",
        }
    ),
)


def literal_query_terms(query: str, *, limit: int = 30) -> list[str]:
    normalized = " ".join(str(query or "").casefold().replace("_", " ").split())
    for phrase, compound in _COMPOUND_TERMS:
        normalized = normalized.replace(phrase, compound)
    raw = _TOKEN.findall(normalized)
    meaningful = [term for term in raw if len(term) > 1 and term not in _QUERY_SCAFFOLD]
    return list(dict.fromkeys(meaningful or raw))[: max(1, limit)]


def semantic_query_groups(query: str | Iterable[str]) -> list[frozenset[str]]:
    ordered_terms = (
        literal_query_terms(query, limit=80)
        if isinstance(query, str)
        else list(dict.fromkeys(str(term).casefold() for term in query if str(term).strip()))
    )
    positions = {term: index for index, term in enumerate(ordered_terms)}
    groups = [family for family in _CONCEPT_FAMILIES if family & positions.keys()]
    return sorted(
        groups,
        key=lambda family: min(positions[term] for term in family if term in positions),
    )


def expand_semantic_terms(terms: Iterable[str], *, limit: int = 96) -> list[str]:
    ordered = list(dict.fromkeys(str(term).casefold() for term in terms if str(term).strip()))
    output = list(ordered)
    for family in semantic_query_groups(ordered):
        for term in sorted(family):
            if term not in output:
                output.append(term)
            if len(output) >= limit:
                return output
    return output[:limit]


def semantic_query_terms(query: str, *, limit: int = 64) -> list[str]:
    return expand_semantic_terms(literal_query_terms(query, limit=30), limit=limit)
