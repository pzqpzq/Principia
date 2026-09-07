from __future__ import annotations

import json
import math
import os
import re
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from contextvars import copy_context
from dataclasses import dataclass, replace
from importlib import metadata as package_metadata
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, Field

from ..application.search import PrincipleSearchService
from ..cancellation import TaskCancelled as _Cancelled
from ..cancellation import cancellation_scope, check_cancelled
from ..domain import (
    ComputedEvidenceAnchor,
    DataAsset,
    DataDerivedPrincipleDraft,
    DataDiscoveryReport,
    DataExtraPrinciple,
    DataFinding,
    DataHypothesis,
    DataRule,
    DatasetAlignment,
    DatasetGraph,
    JobRecord,
    StudyBlueprint,
    StudyBlueprintV2,
    canonical_sha256,
    event_id,
    file_sha256,
    monotonic_ulid,
)
from ..models import utc_now
from ..persistence import V14WorkspaceRepository
from ..providers import ModelPolicy, OpenAICompatibleProvider, ProviderCredentialStore
from ..storage import WorkspaceStorage
from .adapters import AssetInventory, InventoryResult
from .artifact_io import copy_artifact
from .collection_operators import analyze_collection
from .context_budget import compact_scientific_context
from .interpretation import explain_finding
from .operators import OperatorOutcome, analyze_asset, benjamini_hochberg, load_numeric
from .previews import build_preview
from .rule_engine import RULE_ENGINE_VERSION, execute_cross_domain_program, outcomes_to_law_bundle
from .rule_presentation import present_rules
from .sandbox import AnalysisSandbox
from .scientific_programs import (
    ScientificProgramBundle,
    compile_scientific_programs,
)
from .semantics import classify_variable, compile_dataset_semantics, compile_study_blueprint

BudgetName = Literal["fast", "balanced", "deep"]


@dataclass(frozen=True)
class DiscoveryBudget:
    wall_seconds: int
    hypotheses: int
    analysis_units: int
    challenge_rounds: int
    visual_calls: int
    prior_art_results: int


BUDGETS: dict[BudgetName, DiscoveryBudget] = {
    "fast": DiscoveryBudget(600, 8, 16, 1, 2, 1),
    "balanced": DiscoveryBudget(2_400, 16, 48, 2, 6, 3),
    "deep": DiscoveryBudget(7_200, 32, 120, 2, 12, 5),
}

# A budget permits more calls when a future scientific selector can justify
# them, but the default path sends only a compact, diverse preview set. This
# keeps image egress proportionate while still exercising multimodal analysis.
MAX_DEFAULT_REMOTE_PREVIEW_IMAGES = 4


def _casefold_unique(values: list[str], *, limit: int = 100) -> list[str]:
    """Preserve order while removing cosmetic duplicates from model output."""

    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = " ".join(str(value).split())
        key = normalized.casefold().rstrip(".")
        if not normalized or key in seen:
            continue
        seen.add(key)
        output.append(normalized)
        if len(output) >= limit:
            break
    return output


def _distinct_scientific_text(value: str, *shown: str) -> str:
    """Do not manufacture a new semantic section by relabelling the same text."""

    candidate = " ".join(value.split()).strip()
    if not candidate:
        return ""
    key = re.sub(r"[^\w]+", "", candidate.casefold())
    if key and any(
        key == re.sub(r"[^\w]+", "", " ".join(item.split()).casefold())
        for item in shown
        if item.strip()
    ):
        return ""
    return candidate


def _scientific_text_similarity(first: str, second: str) -> float:
    """Compare scientific claims while ignoring cosmetic values and punctuation."""

    def shingles(value: str) -> set[tuple[str, str, str]]:
        normalized = value.casefold()
        normalized = re.sub(r"\b(?:tic\s*)?\d+(?:\.\d+)?(?:e[-+]?\d+)?\b", " value ", normalized)
        words = re.findall(r"[a-z\u4e00-\u9fff]+", normalized)
        return set(zip(words, words[1:], words[2:], strict=False))

    left = shingles(first)
    right = shingles(second)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _scientific_text_duplicate(first: str, second: str) -> bool:
    """Detect paraphrased duplicate claims without conflating related mechanisms."""

    def terms(value: str) -> set[str]:
        normalized = value.casefold()
        normalized = re.sub(r"\b(?:tic\s*)?\d+(?:\.\d+)?(?:e[-+]?\d+)?\b", " value ", normalized)
        return set(re.findall(r"[a-z\u4e00-\u9fff]+", normalized))

    left = terms(first)
    right = terms(second)
    containment = len(left & right) / max(1, min(len(left), len(right)))
    jaccard = len(left & right) / max(1, len(left | right))
    return (
        _scientific_text_similarity(first, second) >= 0.72
        or (containment >= 0.88 and jaccard >= 0.72)
    )


def _extra_principle_duplicates_finding(claim: str, finding: Any) -> bool:
    """Keep an Extra Principle distinct from every user-facing finding claim."""

    return any(
        text and _scientific_text_duplicate(claim, str(text))
        for text in (
            getattr(finding, "claim", ""),
            getattr(finding, "principle_statement", ""),
            getattr(finding, "mechanism", ""),
        )
    )


INSIGHT_LEVELS = (
    "observational",
    "structural",
    "mechanistic",
    "principle_level",
)


def _scientific_specificity(value: str) -> int:
    """Reward quantities and scientific structure, not length or rhetoric."""

    lowered = value.casefold()
    quantities = len(re.findall(r"(?<![a-z])[-+]?\d+(?:\.\d+)?", lowered))
    structures = sum(
        marker in lowered
        for marker in (
            "boundary",
            "coherence",
            "decoupl",
            "gradient",
            "holdout",
            "interaction",
            "invariant",
            "lag",
            "negative control",
            "nonlinear",
            "partial",
            "phase",
            "regime",
            "residual",
            "reversal",
            "threshold",
            "tradeoff",
        )
    )
    return quantities * 3 + structures * 2


_PRIOR_ART_STOPWORDS = {
    "across", "adjusted", "analysis", "associated", "between", "both",
    "candidate", "component", "control", "data", "design", "effect",
    "finding", "higher", "lower", "mechanism", "model", "pattern",
    "principle", "relationship", "reproducible", "response", "result",
    "results", "significant", "specific", "spatial", "study", "supports",
    "system", "using", "variation", "with", "within",
}
_DOMAIN_TOKEN_GROUPS = (
    {"tess", "stellar", "star", "photometric", "asteroseismology", "periodogram", "exoplanet", "lightcurve"},
    {"wafer", "deposition", "precursor", "plasma", "semiconductor", "sputter", "pecvd", "ald", "film", "conductance", "thickness", "substrate", "chamber", "recipe", "shd"},
    {"vulnerability", "cve", "cvss", "exploit", "malware", "cybersecurity", "cryptographic", "cryptography"},
    {"clinical", "patient", "disease", "medical", "diagnosis", "treatment", "hospital"},
    {"neural", "neuron", "neuroscience", "sensorimotor", "eeg", "brain", "cortical", "synaptic", "axon"},
    {"inflation", "employment", "income", "economic", "survey", "household", "price", "worker", "workplace", "wage", "productivity", "financial", "savings", "liquid", "funds", "wealth", "credit", "shed"},
    {"climate", "storm", "ocean", "coral", "ssta"},
    {"earthquake", "seismic", "aftershock", "tectonic", "magnitude", "comcat"},
    {"genomic", "gene", "protein", "cell", "microbial", "rna", "biological"},
    {"cure", "curing", "encapsulant", "thermoset", "polymer", "rheology", "dsc", "ftir", "raman", "vitrification"},
    {"reasoning", "language", "llm", "logical", "ranking", "retrieval", "answer", "benchmark", "weights", "activation-patching", "transformer", "attention", "faithfulness"},
    {"mlperf", "accelerator", "latency", "throughput", "topology"},
    {"gravitational", "gwosc", "strain", "detector", "interferometer", "narrowband", "spectrum"},
    {"rydberg", "electrometry", "radiofrequency", "rubidium", "cesium", "eit", "atomic", "atom"},
    {"atlas", "collider", "lepton", "four-lepton", "particle", "root", "cern"},
    {"vehicle", "automotive", "recall", "complaint", "nhtsa", "manufacturer", "crash"},
    {"sequence", "recurrence", "integer", "oeis", "generating", "combinatorial"},
    {"borophene", "adatom", "electrode", "battery", "crystal", "alloy", "intercalation"},
    {"electron", "phonon", "resistivity", "quasiparticle", "dmft", "superconducting", "fermi"},
)

_SCIENTIFIC_CONCEPT_GROUPS = (
    {"transport", "conductance", "flow", "residence", "diffusion", "delivery", "depletion", "aperture", "permeability"},
    {"reaction", "kinetic", "kinetics", "chemistry", "surface", "etching", "growth", "conversion", "cure", "activation"},
    {"regime", "boundary", "limited", "limitation", "competition", "balance", "optimum", "nonlinear", "reversal", "threshold"},
    {"spatial", "radial", "azimuthal", "uniformity", "gradient", "wafer", "shape", "map", "profile"},
    {"thermal", "temperature", "heating", "activation", "vitrification", "arrhenius", "energy"},
    {"temporal", "time", "contiguous", "coherence", "persistent", "periodic", "oscillation", "frequency", "window"},
    {"robust", "replication", "holdout", "cross", "stable", "invariant", "sensitivity", "validation"},
    {"saving", "savings", "liquid", "liquidity", "buffer", "shock", "volatility", "smoothing", "resilience", "obligation", "financial", "income", "stability"},
    {"labor", "employment", "worker", "wage", "productivity", "skill", "task", "adoption", "automation"},
    {"price", "inflation", "housing", "cost", "monetary", "lag", "lead", "reallocation"},
    {"severity", "disclosure", "enrichment", "exploit", "vulnerability", "warning", "recall", "complaint"},
    {"behavior", "behaviour", "state", "pupil", "locomotion", "neuromodulation", "acetylcholine"},
    {"cluster", "clustering", "aftershock", "adjacency", "coherence", "front", "boundary", "mask"},
)

_DOMAIN_QUERY_EXPANSIONS = (
    (
        {"wafer", "deposition", "pecvd", "conductance", "aperture", "shd", "thickness"},
        "PECVD plasma deposition precursor transport surface reaction wafer film conductance uniformity",
    ),
    (
        {"cure", "encapsulant", "conversion", "activation", "thermoset", "rheology"},
        "thermoset cure kinetics activation energy conversion vitrification diffusion rheology polymer",
    ),
    (
        {"tess", "stellar", "photometric", "lightcurve", "periodogram"},
        "stellar photometry light curve periodicity coherence instrumental alias",
    ),
    (
        {"saving", "savings", "liquid", "household", "income", "volatility"},
        "household liquid savings income volatility consumption smoothing financial resilience",
    ),
    (
        {"inflation", "employment", "housing", "price", "monetary"},
        "housing inflation employment lag monetary policy labor reallocation",
    ),
    (
        {"worker", "workplace", "productivity", "task", "adoption", "automation"},
        "worker task breadth productivity time savings skill adoption automation",
    ),
    (
        {"eeg", "neural", "cortical", "axon", "pupil", "locomotion", "acetylcholine"},
        "neural modulation acetylcholine pupil locomotion behavioral state cortical signal",
    ),
    (
        {"earthquake", "seismic", "aftershock", "tectonic", "magnitude"},
        "earthquake aftershock space time clustering magnitude catalog completeness",
    ),
    (
        {"climate", "ocean", "coral", "ssta", "anomaly"},
        "sea surface temperature anomaly spatial coherence ocean advection climate front",
    ),
    (
        {"vulnerability", "cve", "cvss", "exploit", "cybersecurity"},
        "vulnerability disclosure enrichment delay CVSS CWE exploit software products",
    ),
    (
        {"mlperf", "accelerator", "inference", "latency", "throughput"},
        "MLPerf inference accelerator latency throughput power scaling frontier",
    ),
    (
        {"gravitational", "gwosc", "strain", "detector", "narrowband"},
        "gravitational wave detector strain narrowband spectral line frequency drift instrumental noise",
    ),
    (
        {"vehicle", "recall", "complaint", "nhtsa", "manufacturer"},
        "vehicle complaint recall investigation manufacturer communication early warning",
    ),
    (
        {"sequence", "recurrence", "integer", "oeis"},
        "integer sequence recurrence generating function structural invariance",
    ),
)

_FOUNDATION_TRIGGER_RULES: tuple[tuple[set[str], tuple[str, ...]], ...] = (
    (
        {"gravitational", "gwosc", "strain", "detector", "interferometer", "narrowband"},
        (
            "meta:information-control-complexity:shannon-nyquist-sampling",
            "meta:foundations:measurement-validity",
            "meta:foundations:parsimony-mdl",
        ),
    ),
    (
        {"rydberg", "electrometry", "radiofrequency", "rubidium", "cesium", "eit"},
        (
            "meta:physics:quantum-superposition",
            "meta:foundations:measurement-validity",
            "meta:engineering-optimization:dimensional-analysis",
        ),
    ),
    (
        {"atlas", "collider", "lepton", "four-lepton", "cern"},
        (
            "meta:physics:gauge-principle",
            "meta:physics:noether",
            "meta:foundations:measurement-validity",
        ),
    ),
    (
        {"dicom", "imaging", "mammography", "radiology", "modality"},
        (
            "meta:foundations:measurement-validity",
            "meta:medicine-epidemiology:measurement-and-case-definition",
            "meta:statistics-causality:missing-data-mechanisms",
        ),
    ),
    (
        {"htops", "workplace", "worker", "adoption", "automation", "survey"},
        (
            "meta:socio-technical-systems:diffusion-of-innovations",
            "meta:socio-technical-systems:socio-technical-joint-optimization",
            "meta:statistics-causality:exchangeability",
        ),
    ),
    (
        {"vehicle", "recall", "complaint", "nhtsa", "manufacturer"},
        (
            "meta:socio-technical-systems:high-reliability-organizations",
            "meta:socio-technical-systems:swiss-cheese-defense-in-depth",
            "meta:foundations:open-world-coverage-gap",
        ),
    ),
    (
        {"cure", "curing", "encapsulant", "thermoset", "vitrification"},
        (
            "meta:chemistry-materials:arrhenius-rate",
            "meta:chemistry-materials:thermodynamics-kinetics",
            "meta:chemistry-materials:transition-state-theory",
        ),
    ),
    (
        {"pecvd", "deposition", "wafer", "conductance", "aperture", "shd"},
        (
            "meta:chemistry-materials:processing-structure-properties",
            "meta:chemistry-materials:thermodynamics-kinetics",
            "meta:engineering-optimization:robust-design-under-uncertainty",
        ),
    ),
    (
        {"tess", "stellar", "photometric", "lightcurve", "periodogram"},
        (
            "meta:information-control-complexity:shannon-nyquist-sampling",
            "meta:foundations:measurement-validity",
        ),
    ),
    (
        {"eeg", "edf", "neural", "cortical", "brain", "neuron", "axon"},
        (
            "meta:information-control-complexity:shannon-nyquist-sampling",
            "meta:foundations:measurement-validity",
        ),
    ),
    (
        {"vulnerability", "cve", "cvss", "exploit", "cybersecurity"},
        (
            "meta:computer-science:computational-security",
            "meta:foundations:open-world-coverage-gap",
        ),
    ),
    (
        {"mlperf", "accelerator", "latency", "throughput", "inference"},
        (
            "meta:computing-industry:roofline-model",
            "meta:computing-industry:data-movement-energy",
            "meta:engineering-optimization:pareto-frontier",
        ),
    ),
    (
        {"gene", "genomic", "rna", "protein", "cell", "microbial"},
        (
            "meta:biology-evolution:central-dogma",
            "meta:biology-evolution:homeostasis",
        ),
    ),
    (
        {"earthquake", "seismic", "quake", "tectonic"},
        (
            "meta:earth-climate:plate-tectonics",
            "meta:earth-climate:chaos-predictability",
        ),
    ),
    (
        {"climate", "storm", "coral", "ocean", "anomaly", "ssta"},
        (
            "meta:earth-climate:forcing-internal-variability",
            "meta:earth-climate:state-dependent-resilience",
            "meta:earth-climate:mass-energy-budgets",
        ),
    ),
    (
        {"inflation", "employment", "income", "economic", "household"},
        (
            "meta:economics-game-theory:lucas-critique",
            "meta:economics-game-theory:path-dependence-increasing-returns",
        ),
    ),
    (
        {"sequence", "recurrence", "integer", "oeis"},
        (
            "meta:foundations:parsimony-mdl",
            "meta:mathematics-logic:invariance",
        ),
    ),
)


def _foundation_ids_for_text(value: str, *, limit: int = 3) -> list[str]:
    """Return curated foundations for an explicitly detected scientific domain.

    This is intentionally a domain gate rather than a search-rank fallback.  A
    lexical Cloud hit that happens to share a generic word such as ``power`` or
    ``conversion`` must not displace a relevant, curated foundation during ASD
    planning.
    """

    tokens = _literature_tokens(value)
    output: list[str] = []
    for triggers, identifiers in _FOUNDATION_TRIGGER_RULES:
        if not tokens & triggers:
            continue
        for identifier in identifiers:
            if identifier not in output:
                output.append(identifier)
                if len(output) >= limit:
                    return output
    return output


def _foundation_ids_for_finding(finding: DataFinding, *, limit: int = 3) -> list[str]:
    return _foundation_ids_for_text(
        " ".join(
            (
                finding.title,
                finding.claim,
                finding.interpretation,
                finding.mechanism,
                finding.transfer_scope,
            )
        ),
        limit=limit,
    )


def _literature_tokens(value: str) -> set[str]:
    normalized = (
        value.casefold().replace("light curve", "lightcurve").replace("-", " ")
    )
    aliases = {
        "films": "film",
        "households": "household",
        "lightcurves": "lightcurve",
        "patients": "patient",
        "regimes": "regime",
        "shocks": "shock",
        "stars": "star",
        "wafers": "wafer",
    }
    return {
        aliases.get(token, token)
        for token in re.findall(r"[a-z][a-z0-9-]{3,}", normalized)
        if token not in _PRIOR_ART_STOPWORDS
    }


def _source_title_relevant_to_context(
    context_value: str, source: dict[str, Any]
) -> bool:
    context = _literature_tokens(context_value)
    title = _literature_tokens(str(source.get("title") or ""))
    shared = context & title
    if len(shared) < 2:
        return False
    detected_groups = [group for group in _DOMAIN_TOKEN_GROUPS if len(context & group) >= 2]
    if detected_groups:
        return any(len(context & title & group) >= 2 for group in detected_groups)
    return len(shared) >= 3


def _planning_principle_relevant(
    context_value: str, principle: dict[str, Any]
) -> bool:
    """Keep Cloud planning knowledge only when domain and mechanism agree.

    Search can truthfully degrade to lexical plus evidence-graph retrieval when
    vectors are unavailable.  In that mode a long query may produce a bridge
    through one generic token.  Those records remain auditable retrieval
    candidates, but they cannot become executable-program grounding or visible
    graph knowledge unless this independent relevance gate passes.
    """

    context_tokens = _literature_tokens(context_value)
    principle_tokens = _literature_tokens(
        " ".join(
            str(principle.get(key) or "")
            for key in (
                "id",
                "principle_id",
                "title",
                "claim",
                "argument",
                "interpretation",
                "applications",
                "tags",
            )
        )
    )
    if not context_tokens or not principle_tokens:
        return False
    context_domains = {
        index
        for index, group in enumerate(_DOMAIN_TOKEN_GROUPS)
        if context_tokens & group
    }
    principle_domains = {
        index
        for index, group in enumerate(_DOMAIN_TOKEN_GROUPS)
        if principle_tokens & group
    }
    if context_domains and principle_domains and not context_domains & principle_domains:
        return False
    exact = len(context_tokens & principle_tokens)
    shared_concepts = sum(
        bool(context_tokens & group) and bool(principle_tokens & group)
        for group in _SCIENTIFIC_CONCEPT_GROUPS
    )
    if context_domains & principle_domains:
        return exact >= 2 and shared_concepts >= 1
    if context_domains and not principle_domains:
        return exact >= 3 and shared_concepts >= 1
    return exact >= 3 and shared_concepts >= 2


def _prior_art_title_relevant(finding: DataFinding, source: dict[str, Any]) -> bool:
    """Conservative title-level gate; lexical coincidence is not prior art."""

    finding_title = " ".join(finding.title.casefold().split())
    source_title = " ".join(str(source.get("title") or "").casefold().split())
    if len(finding_title) >= 16 and finding_title in source_title:
        # Exact claim-title reuse (for example "Independent replication of …")
        # is stronger evidence than a token heuristic and must survive generic
        # scientific stopword changes.
        return True
    return _source_title_relevant_to_context(
        " ".join(
            (
                finding.title,
                finding.claim,
                finding.interpretation,
                finding.mechanism,
                finding.significance,
            )
        ),
        source,
    )


def _principle_relevant_to_finding(
    finding: DataFinding, principle: dict[str, Any]
) -> bool:
    """Require shared domain and mechanism, with aliases handled explicitly.

    The former three-token intersection silently rejected strong Principles
    whose vocabulary differed from the computed result (for example
    conductance versus residence/transport). This gate remains conservative
    while recognizing scientific concepts instead of identical prose.
    """

    principle_id = str(principle.get("id") or principle.get("principle_id") or "")
    if principle_id in _foundation_ids_for_finding(finding):
        return True
    finding_tokens = _literature_tokens(
        " ".join(
            (finding.title, finding.claim, finding.interpretation, finding.mechanism)
        )
    )
    principle_tokens = _literature_tokens(
        " ".join(
            str(principle.get(key) or "")
            for key in (
                "id",
                "principle_id",
                "title",
                "claim",
                "argument",
                "interpretation",
            )
        )
    )
    exact = len(finding_tokens & principle_tokens)
    shared_concepts = sum(
        bool(finding_tokens & group) and bool(principle_tokens & group)
        for group in _SCIENTIFIC_CONCEPT_GROUPS
    )
    finding_domains = {
        index for index, group in enumerate(_DOMAIN_TOKEN_GROUPS)
        if finding_tokens & group
    }
    principle_domains = {
        index for index, group in enumerate(_DOMAIN_TOKEN_GROUPS)
        if principle_tokens & group
    }
    same_domain = bool(finding_domains & principle_domains)
    if finding_domains and principle_domains and not same_domain:
        return False
    if same_domain:
        return (exact >= 2 and shared_concepts >= 1) or (
            exact >= 1 and shared_concepts >= 2
        )
    if finding_domains and not principle_domains:
        # A genuinely general method can explain a domain result, but only when
        # its language matches multiple structural concepts.  This admits, for
        # example, contiguous-window replication while rejecting a materials
        # record that merely shares the words "thermal" and "energy".
        return exact >= 3 and shared_concepts >= 1
    # Domain-free cross-field Principles need unusually strong agreement.
    return exact >= 3 and shared_concepts >= 1


def _principle_search_queries(finding: DataFinding) -> list[str]:
    """Return short mechanism queries; long finding prose degrades FTS ranking."""

    base = f"{finding.title}. {finding.mechanism}"
    tokens = _literature_tokens(base)
    expansions = [
        expansion
        for triggers, expansion in _DOMAIN_QUERY_EXPANSIONS
        if tokens & triggers
    ]
    # The title is retained as a second, claim-specific route.  Each query is
    # deliberately independent so generic words in a long mechanism paragraph
    # cannot crowd the domain terms out of lexical ranking.
    candidates = [*expansions, finding.title[:500]]
    return list(dict.fromkeys(" ".join(item.split()) for item in candidates if item.strip()))[:3]


def _principle_search_query(finding: DataFinding) -> str:
    """Compatibility wrapper returning the first focused retrieval query."""

    queries = _principle_search_queries(finding)
    return queries[0] if queries else finding.title[:500]


class FindingInterpretation(BaseModel):
    finding_id: str
    title: str = Field(default="", max_length=240)
    claim: str = Field(default="", max_length=2_400)
    interpretation: str
    mechanism: str
    significance: str = Field(default="", max_length=2_000)
    insight_level: Literal[
        "observational", "structural", "mechanistic", "principle_level"
    ] | None = None
    nontriviality_basis: str = Field(default="", max_length=2_000)
    surprising_result: str = Field(default="", max_length=2_000)
    practical_value: str = Field(default="", max_length=2_000)
    principle_statement: str = Field(default="", max_length=2_000)
    transfer_scope: str = Field(default="", max_length=2_000)
    principle_chain: list[str] = Field(default_factory=list, max_length=12)
    principle_ids: list[str] = Field(default_factory=list)
    additional_confounders: list[str] = Field(default_factory=list)
    additional_limits: list[str] = Field(default_factory=list)
    next_validation: str = ""
    recommended_disposition: Literal["retain", "hold_back"] = "retain"
    hold_back_reason: str = Field(default="", max_length=2_000)


class ExtraPrincipleProposal(BaseModel):
    title: str = Field(min_length=8, max_length=240)
    claim: str = Field(min_length=20, max_length=2_400)
    explanatory_gap: str = Field(min_length=20, max_length=2_000)
    mechanism: str = Field(min_length=20, max_length=4_000)
    boundary_conditions: list[str] = Field(default_factory=list, max_length=20)
    falsifiers: list[str] = Field(default_factory=list, max_length=20)
    supporting_source_keys: list[str] = Field(default_factory=list, max_length=20)
    related_finding_ids: list[str] = Field(default_factory=list, max_length=20)


class DiscoverySynthesis(BaseModel):
    interpretations: list[FindingInterpretation] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    principle_gap_detected: bool = False
    principle_gap_reason: str = Field(default="", max_length=2_000)
    extra_principles: list[ExtraPrincipleProposal] = Field(
        default_factory=list, max_length=6
    )


class ScientificHypothesisProposal(BaseModel):
    title: str = Field(min_length=8, max_length=240)
    claim: str = Field(min_length=20, max_length=1_500)
    scientific_rationale: str = Field(min_length=20, max_length=2_000)
    analysis_family: Literal[
        "time_series",
        "signal",
        "spatial",
        "relational",
        "group_comparison",
        "mechanistic_curve",
        "matrix_structure",
        "cross_modal",
        "cross_asset_replication",
        "anomaly_or_regime",
    ]
    asset_ids: list[str] = Field(min_length=1, max_length=20)
    variables_or_features: list[str] = Field(default_factory=list, max_length=30)
    admissible_law_families: list[Literal["scaling", "saturation", "activation", "regime_transition", "response_kernel"]] = Field(default_factory=list, max_length=5)
    expected_relationship: str = Field(min_length=10, max_length=1_500)
    mechanism: str = Field(min_length=20, max_length=2_000)
    confounders: list[str] = Field(default_factory=list, max_length=30)
    falsifier: str = Field(min_length=12, max_length=1_500)
    why_it_matters: str = Field(min_length=20, max_length=2_000)
    priority: float = Field(ge=0, le=1)


class ScientificHypothesisPortfolio(BaseModel):
    domain: str = Field(min_length=3, max_length=200)
    dataset_interpretation: str = Field(min_length=20, max_length=3_000)
    hypotheses: list[ScientificHypothesisProposal] = Field(default_factory=list, max_length=32)
    key_design_risks: list[str] = Field(default_factory=list, max_length=30)


class GeneratedAnalysisProposal(BaseModel):
    scientific_intent: str = Field(min_length=12, max_length=1_000)
    target_finding_ids: list[str] = Field(min_length=1, max_length=4)
    target_test_ids: list[str] = Field(min_length=1, max_length=12)
    required_table_ids: list[str] = Field(default_factory=list, max_length=4)
    stability_check: str = Field(min_length=12, max_length=1_000)
    code: str = Field(min_length=20, max_length=100_000)
    expected_output: str = Field(min_length=3, max_length=1_000)


class VisualObservation(BaseModel):
    asset_id: str
    observation: str = Field(min_length=3, max_length=2_000)
    scientific_relevance: str = Field(default="", max_length=2_000)
    limitations: list[str] = Field(default_factory=list, max_length=20)


class VisualObservationBatch(BaseModel):
    observations: list[VisualObservation] = Field(default_factory=list, max_length=2)


class DataDiscoveryService:
    """Dataset-native, byte-preserving autonomous discovery orchestration."""

    phase_ids = ("inventory", "understand", "analyze", "challenge", "synthesize")
    worker_capacity = 4

    def __init__(
        self,
        storage: WorkspaceStorage,
        repository: V14WorkspaceRepository,
        search: PrincipleSearchService,
        *,
        outputs_root: Path,
        literature_searcher: Callable[..., dict[str, Any]] | None = None,
    ) -> None:
        self.storage = storage
        self.repository = repository
        self.search = search
        self.outputs_root = outputs_root
        self.literature_searcher = literature_searcher
        self.inventory_adapter = AssetInventory()
        self.credentials = ProviderCredentialStore(storage.root)
        self._executor = ThreadPoolExecutor(
            max_workers=self.worker_capacity,
            thread_name_prefix="principia-data-discovery",
        )
        self._futures: dict[str, Future[Any]] = {}
        self._cancel: dict[str, threading.Event] = {}
        self._pause: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    def close(self) -> None:
        # Wake paused workers before joining. Every scientific batch observes
        # the same cancellation token; completed evidence remains durable.
        with self._lock:
            for cancellation in self._cancel.values():
                cancellation.set()
            for pause in self._pause.values():
                pause.clear()
        self._executor.shutdown(wait=True, cancel_futures=False)

    def _provider_receipt(
        self,
        *,
        study_id: str,
        phase: str,
        provider: str,
        model: str,
        endpoint_class: str,
        state: str,
        started: float,
        prompt_template: str = "",
        input_payload: Any = None,
        generation: Any = None,
        error: Exception | None = None,
        retry_index: int = 0,
        preview_hashes: list[str] | None = None,
    ) -> dict[str, Any]:
        """Persist a path-free, secret-free receipt for every remote phase attempt."""

        study = self.repository.data_study(study_id) or {}
        job_id = str(study.get("job_id") or "")
        trace_payload: dict[str, Any] = {}
        trace = getattr(generation, "trace", None)
        if trace is not None:
            try:
                trace_payload = trace.model_dump(mode="json")
            except Exception:
                trace_payload = {}
        value = getattr(generation, "value", None)
        value_payload = (
            value.model_dump(mode="json") if isinstance(value, BaseModel) else value
        )
        provider_error_category = str(getattr(error, "category", "") or "")
        error_category = (
            provider_error_category
            or (type(error).__name__ if error is not None else "")
        )
        error_message = {
            "authentication": "The provider rejected the configured credential.",
            "configuration": "The requested provider is not configured.",
            "network": "The provider endpoint could not be reached.",
            "provider_unavailable": "The provider could not complete this request.",
            "rate_limited": "The provider rate-limited this request.",
            "timeout": "The provider response did not reach Principia before the phase timeout.",
            "ProviderOutputError": "The provider response remained schema-invalid after one bounded repair.",
        }.get(error_category, "A provider phase failed; raw error text was not retained.")
        # ProviderTrace exposes token counters directly. Older provider traces
        # may wrap them in ``usage``; accept both without losing accounting.
        usage = dict(trace_payload.get("usage") or trace_payload)
        receipt = {
            "schema_version": "principia.provider-attempt-receipt/v1",
            "attempt_id": f"provider-attempt:{monotonic_ulid()}",
            "job_id": job_id,
            "study_id": study_id,
            "phase": phase,
            "provider": provider,
            "model": model,
            "endpoint_class": endpoint_class,
            "prompt_template": prompt_template,
            "prompt_sha256": canonical_sha256(
                {"template": prompt_template, "endpoint_class": endpoint_class}
            ),
            "input_sha256": canonical_sha256(input_payload)
            if input_payload is not None
            else "",
            "output_sha256": (
                canonical_sha256(value_payload) if value_payload is not None else ""
            ),
            "state": state,
            "retry_index": retry_index,
            "latency_ms": max(0, int((time.monotonic() - started) * 1_000)),
            "error_category": error_category,
            "error_message": error_message if error is not None else "",
            "status_code": getattr(error, "status_code", None) if error is not None else None,
            "retryable": bool(getattr(error, "retryable", False)) if error is not None else False,
            "token_usage": {
                key: int(value)
                for key, value in usage.items()
                if key in {"input_tokens", "output_tokens", "total_tokens"}
                and isinstance(value, (int, float))
            },
            "preview_sha256": list(preview_hashes or [])[:2],
            "created_at": utc_now(),
        }
        if job_id:
            self.repository.save_provider_attempt(receipt)
        return receipt

    def create(
        self,
        *,
        source_ids: list[str],
        objective: str = "",
        provider: str = "siliconflow",
        reasoning_model: str = "auto",
        vision_model: str = "auto",
        knowledge_scope: str = "combined",
        prior_art: str = "survivors",
        budget: BudgetName = "balanced",
        session_id: str = "",
        project_mode: str = "reuse",
        source_set_digest: str = "",
        expected_session_revision: int | None = None,
        egress_confirmed: bool = False,
        defer: bool = True,
    ) -> dict[str, Any]:
        normalized_sources = list(dict.fromkeys(item.strip() for item in source_ids if item.strip()))
        if not normalized_sources:
            raise ValueError("select at least one Local data source")
        if budget not in BUDGETS:
            raise ValueError("budget must be fast, balanced, or deep")
        for source_id in normalized_sources:
            root = self.repository.source_root(source_id)
            if root is None or not root.is_dir():
                raise KeyError(f"unknown or unavailable Local source: {source_id}")
        if provider and not egress_confirmed:
            # A deterministic local run remains available, but no provider request may occur.
            resolved_provider = ""
            reasoning_model = ""
            vision_model = ""
        else:
            resolved_provider = provider.strip()

        study_id = f"study:{monotonic_ulid()}"
        job_id = f"job:{monotonic_ulid()}"
        request = {
            "objective": objective.strip()[:4_000],
            "provider": resolved_provider,
            "reasoning_model": reasoning_model.strip()[:200],
            "vision_model": vision_model.strip()[:200],
            "knowledge_scope": knowledge_scope,
            "prior_art": prior_art,
            "budget": budget,
            "egress_confirmed": bool(egress_confirmed),
            "schema_version": "principia.data-discovery-request/v2",
            "engine_version": RULE_ENGINE_VERSION,
            "source_ids": normalized_sources,
            "project_mode": project_mode,
        }
        job = JobRecord(
            job_id=job_id,
            kind="data_discovery",
            state="queued",
            stage="Inventory",
            progress=0,
            provider=resolved_provider,
            model=reasoning_model if reasoning_model != "auto" else "",
            checkpoint={
                "study_id": study_id,
                "phase": "inventory",
                "session_id": session_id,
            },
            total_units=len(normalized_sources),
            last_activity_at=utc_now(),
            status_message="Waiting to inventory selected data",
        )
        with self.repository.atomic():
            if session_id:
                with self.repository.connect() as conn:
                    active = conn.execute("SELECT 1 FROM data_studies WHERE session_id=? AND state IN ('queued','running','pausing','paused','resuming','cancelling') LIMIT 1", (session_id,)).fetchone()
                    if active:
                        raise ValueError("this project already has an active discovery; finish or cancel it first")
                    current = conn.execute("SELECT revision FROM research_sessions WHERE session_id=?", (session_id,)).fetchone()
                    if expected_session_revision is not None and (current is None or current[0] != expected_session_revision):
                        raise ValueError("the project changed; reload it before starting discovery")
                    conn.execute("UPDATE research_sessions SET source_ids_json=?, source_set_digest=CASE WHEN ?='' THEN source_set_digest ELSE ? END, provider_profile_id=?, model=?, state='queued', revision=revision+1, updated_at=? WHERE session_id=?", (json.dumps(normalized_sources), source_set_digest, source_set_digest, resolved_provider, reasoning_model, utc_now(), session_id))
            self.repository.save_job(job)
            self.repository.create_data_study(
            {
                "study_id": study_id,
                "job_id": job_id,
                "session_id": session_id,
                "source_ids": normalized_sources,
                "request": request,
            }
            )
        self._event(job_id, "queued", "Inventory", "Discovery queued", study_id=study_id)
        cancellation = threading.Event()
        with self._lock:
            self._cancel[study_id] = cancellation
            self._pause[study_id] = threading.Event()
        if defer:
            future = self._executor.submit(self._run, study_id, cancellation)
            with self._lock:
                self._futures[study_id] = future
        else:
            self._run(study_id, cancellation)
        return self.get(study_id)

    def get(self, study_id: str) -> dict[str, Any]:
        study = self.repository.data_study(study_id)
        if study is None:
            raise KeyError(f"unknown data study: {study_id}")
        job = self.repository.get_job(str(study["job_id"]))
        live_counts = self.repository.data_study_counts(study_id)
        coverage = dict(study.get("coverage") or {})
        coverage["live_counts"] = {
            "executed_tests": live_counts["tests"],
            "supported_findings": live_counts["supported_findings"],
            "completed_analysis_units": int(job.completed_units if job else 0),
            "total_analysis_units": int(job.total_units if job else 0),
        }
        provider_attempts = self.repository.provider_attempts(str(study["job_id"]))
        failed_attempts = [
            item for item in provider_attempts if str(item.get("state")) != "succeeded"
        ]
        resolved_models = list(
            dict.fromkeys(
                str(item.get("model") or "")
                for item in provider_attempts
                if item.get("model") and str(item.get("state")) == "succeeded"
            )
        )
        requested_provider = str(dict(study.get("request") or {}).get("provider") or "")
        study_engine_version = str(
            dict(study.get("request") or {}).get("engine_version") or ""
        )
        historical_rule_evaluation = study_engine_version != RULE_ENGINE_VERSION
        coverage["provider_capability"] = {
            "state": (
                "local_only"
                if not requested_provider
                else "reduced_capability"
                if failed_attempts
                else "verified"
                if provider_attempts
                else "pending"
            ),
            "provider": requested_provider,
            "resolved_models": resolved_models,
            "attempt_count": len(provider_attempts),
            "failed_attempt_count": len(failed_attempts),
            "latest_error_category": str(failed_attempts[-1].get("error_category") or "")
            if failed_attempts
            else "",
        }
        with self._lock:
            active_workers = sum(
                future.running() and not future.done()
                for future in self._futures.values()
            )
            queued = [
                identifier
                for identifier, future in self._futures.items()
                if not future.running() and not future.done()
            ]
        queue_position = queued.index(study_id) + 1 if study_id in queued else 0
        return {
            **study,
            "coverage": coverage,
            "job": job.model_dump(mode="json") if job else None,
            "finding_count": live_counts["findings"],
            "engine_version": study_engine_version or "legacy-pre-rule-engine-v2",
            "historical_rule_evaluation": historical_rule_evaluation,
            "historical_label": (
                "Historical run — predates current Rule evaluation"
                if historical_rule_evaluation
                else ""
            ),
            "run_with_current_engine": {
                "source_ids": list(study.get("source_ids") or []),
                "session_id": str(study.get("session_id") or ""),
                "budget": str(dict(study.get("request") or {}).get("budget") or "balanced"),
            },
            "execution": {
                "worker_capacity": self.worker_capacity,
                "active_workers": active_workers,
                "queue_position": queue_position,
                "state": "queued" if queue_position else "active_or_terminal",
            },
        }

    def events(self, study_id: str, *, after: int = 0) -> list[dict[str, Any]]:
        study = self.repository.data_study_status(study_id)
        if study is None:
            raise KeyError(f"unknown data study: {study_id}")
        return self.repository.job_events(str(study["job_id"]), after=after)

    def findings(self, study_id: str) -> list[dict[str, Any]]:
        if self.repository.data_study(study_id) is None:
            raise KeyError(f"unknown data study: {study_id}")
        return [
            self._sanitize_finding_principle_links(item).model_dump(mode="json")
            for item in self.repository.data_findings(study_id)
        ]

    def blueprint(self, study_id: str) -> dict[str, Any]:
        if self.repository.data_study(study_id) is None:
            raise KeyError(f"unknown data study: {study_id}")
        payload = self.repository.study_blueprint(study_id)
        if payload is None:
            return {
                "study_id": study_id,
                "schema_version": "principia.study-blueprint/v2",
                "state": "pending_inventory",
                "edit_revision": 0,
            }
        return StudyBlueprint.model_validate(payload).model_dump(mode="json")

    def patch_blueprint(self, study_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        """Apply one explicit, role-only interpretation correction.

        Source files are never changed, and an executed study cannot be
        reinterpreted in place.  The corrected binding is used only while the
        run is still between inventory and analysis; completed runs must be
        rerun so their receipts remain immutable.
        """

        study = self.repository.data_study(study_id)
        if study is None:
            raise KeyError(f"unknown data study: {study_id}")
        if self.repository.data_tests(study_id) or self.repository.scientific_law_families(study_id):
            raise ValueError(
                "an executed discovery is immutable; start a new run with the corrected interpretation"
            )
        current_payload = self.repository.study_blueprint(study_id)
        if current_payload is None:
            raise ValueError("the blueprint is not available until inventory and understanding finish")
        current = StudyBlueprint.model_validate(current_payload)
        expected_revision = int(patch.get("expected_edit_revision") or 0)
        if expected_revision != current.edit_revision:
            raise ValueError("the interpretation changed; reload it before applying this edit")
        by_id = {
            str(item.get("binding_id") or ""): dict(item)
            for item in current.variable_bindings
            if str(item.get("binding_id") or "")
        }

        def resolve(name: str) -> list[dict[str, Any]]:
            requested = [str(item) for item in list(patch.get(name) or [])]
            missing = [item for item in requested if item not in by_id]
            if missing:
                raise ValueError(f"unknown blueprint binding: {missing[0]}")
            return [by_id[item] for item in requested]

        targets = resolve("target_binding_ids")
        inputs = resolve("input_binding_ids")
        nuisances = resolve("nuisance_binding_ids")
        independent = resolve("independent_unit_binding_ids")
        target_ids = {str(item["binding_id"]) for item in targets}
        input_ids = {str(item["binding_id"]) for item in inputs}
        overlap = target_ids & input_ids
        if overlap:
            raise ValueError("a measurement cannot be both target and input")
        forbidden = {
            str(item.get("binding_id") or "")
            for item in current.prohibited_leakage_variables
        }
        if input_ids & forbidden:
            raise ValueError("identifier and row-order fields cannot be scientific inputs")
        payload = current.model_dump(mode="json", exclude={"blueprint_digest"})
        payload.update(
            schema_version="principia.study-blueprint/v2",
            target_bindings=[{**item, "scientific_role": "target"} for item in targets],
            input_bindings=[{**item, "scientific_role": "controlled_or_design_input"} for item in inputs],
            nuisance_bindings=[{**item, "scientific_role": "nuisance_or_design_only"} for item in nuisances],
            independent_units=[
                {
                    "binding_id": item["binding_id"],
                    "view_id": item.get("view_id"),
                    "variable": item.get("name") or item.get("variable"),
                    "confidence": 1.0,
                    "source": "explicit_user_interpretation",
                }
                for item in independent
            ],
            interpretation_summary=(
                str(patch.get("interpretation_summary") or "").strip()
                or current.interpretation_summary
            ),
            semantic_resolution={
                **current.semantic_resolution,
                "explicit_user_correction": True,
                "deterministic_role_binding_complete": True,
            },
            edit_revision=current.edit_revision + 1,
            needs_user_confirmation=False,
        )
        updated = StudyBlueprintV2(
            **payload, blueprint_digest=canonical_sha256(payload)
        )
        self.repository.save_study_blueprint(updated.model_dump(mode="json"))
        return updated.model_dump(mode="json")

    def workspace_records(self, study_id: str) -> dict[str, Any]:
        """Return the single normalized record projection used by map and graph."""

        study = self.repository.data_study(study_id)
        if study is None:
            raise KeyError(f"unknown data study: {study_id}")
        findings = self.findings(study_id)
        rules = self.rules(study_id)
        extras = self.extra_principles(study_id)
        linked = self.linked_principles(study_id)
        records: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        seen: set[str] = set()

        def append_record(
            identifier: str,
            *,
            record_kind: str,
            category: str,
            origin: str,
            payload: dict[str, Any],
        ) -> None:
            if not identifier or identifier in seen:
                return
            seen.add(identifier)
            records.append(
                {
                    "record_id": identifier,
                    "record_kind": record_kind,
                    "category": category,
                    "origin": origin,
                    "payload": payload,
                }
            )

        for item in findings:
            identifier = str(item.get("finding_id") or "")
            append_record(
                identifier,
                record_kind="discovery_finding",
                category="principles" if item.get("status") == "supported_candidate" and item.get("insight_level") == "principle_level" else "observations",
                origin="data_discovery",
                payload=item,
            )
            for principle_id in list(item.get("principle_ids") or []):
                edges.append(
                    {
                        "edge_id": canonical_sha256(
                            [study_id, identifier, principle_id, "explained_by"]
                        )[:32],
                        "source_id": identifier,
                        "target_id": str(principle_id),
                        "edge_class": "explanation",
                        "relation_type": "explained by",
                    }
                )
        for item in rules:
            append_record(
                str(item.get("rule_id") or ""),
                record_kind="data_rule",
                category="rules",
                origin="executed_law",
                payload=item,
            )
            finding_id = str(item.get("finding_id") or "")
            if finding_id:
                edges.append(
                    {
                        "edge_id": canonical_sha256(
                            [study_id, finding_id, item.get("rule_id"), "rule_projection"]
                        )[:32],
                        "source_id": finding_id,
                        "target_id": str(item.get("rule_id") or ""),
                        "edge_class": "computed_rule",
                        "relation_type": "expressed as",
                    }
                )
        for item in list(linked.get("principles") or []):
            identifier = str(item.get("id") or item.get("principle_id") or "")
            append_record(
                identifier,
                record_kind="principle",
                category="global_principles",
                origin="cloud_grounding",
                payload=dict(item),
            )
        for item in list(linked.get("foundations") or []):
            identifier = str(item.get("id") or item.get("principle_id") or "")
            append_record(
                identifier,
                record_kind="meta_principle",
                category="principles",
                origin="cloud_foundation",
                payload=dict(item),
            )
            edges.extend(
                dict(relation)
                for relation in list(item.get("relations") or [])
                if isinstance(relation, dict)
            )
        for item in extras:
            identifier = str(item.get("extra_principle_id") or "")
            append_record(
                identifier,
                record_kind="extra_principle",
                category="extra_knowledge",
                origin="research_gap_synthesis",
                payload=item,
            )
            for finding_id in list(item.get("related_finding_ids") or []):
                edges.append(
                    {
                        "edge_id": canonical_sha256(
                            [study_id, finding_id, identifier, "extra_principle"]
                        )[:32],
                        "source_id": str(finding_id),
                        "target_id": identifier,
                        "edge_class": "provisional_explanation",
                        "relation_type": "motivates extra knowledge",
                    }
                )
        normalized_edges: list[dict[str, Any]] = []
        edge_digests: dict[str, str] = {}
        for edge in edges:
            source_id = str(edge.get("source_id") or edge.get("source") or "")
            target_id = str(edge.get("target_id") or edge.get("target") or "")
            if not source_id or not target_id:
                continue
            edge_class = str(edge.get("edge_class") or "relationship")
            relation_type = str(edge.get("relation_type") or "related to")
            edge_id = str(edge.get("edge_id") or "") or canonical_sha256(
                [study_id, source_id, target_id, edge_class, relation_type]
            )[:32]
            normalized = {
                **edge,
                "edge_id": edge_id,
                "source_id": source_id,
                "target_id": target_id,
                "edge_class": edge_class,
                "relation_type": relation_type,
            }
            normalized.pop("source", None)
            normalized.pop("target", None)
            digest = canonical_sha256(normalized)
            previous = edge_digests.get(edge_id)
            if previous is not None:
                if previous != digest:
                    raise ValueError(
                        f"conflicting workspace edge identity: {edge_id}"
                    )
                continue
            edge_digests[edge_id] = digest
            normalized_edges.append(normalized)
        counts: dict[str, int] = {}
        for record in records:
            category = str(record["category"])
            counts[category] = counts.get(category, 0) + 1
        return {
            "schema_version": "principia.workspace-records/v1",
            "study_id": study_id,
            "records": records,
            "edges": normalized_edges,
            "counts": counts,
        }

    def _retrieve_relevant_principles(
        self, finding: DataFinding, *, scope: str = "combined"
    ) -> DataFinding:
        """Repair saved links with focused, conservative Global Cloud retrieval.

        This is deterministic and local: it searches the installed Cloud index,
        never calls a model, and never pads the graph to a target count.
        """

        sanitized = self._sanitize_finding_principle_links(finding)
        ordinary = [
            identifier
            for identifier in sanitized.principle_ids
            if not identifier.startswith("meta:")
        ]
        resolved_scope = "global" if scope in {"global", "combined"} else "local"
        for query in _principle_search_queries(sanitized):
            try:
                records = list(
                    self._scoped_search(
                        query,
                        scope=resolved_scope,
                        source_ids=list((self.repository.data_study(finding.study_id) or {}).get("source_ids") or []),
                        limit=12,
                    ).get("items")
                    or []
                )
            except Exception:
                records = []
            for record in records:
                identifier = str(record.get("id") or record.get("principle_id") or "")
                if (
                    not identifier
                    or identifier.startswith("meta:")
                    or identifier in ordinary
                    or not _principle_relevant_to_finding(sanitized, record)
                ):
                    continue
                ordinary.append(identifier)
                if len(ordinary) >= 3:
                    break
            if len(ordinary) >= 3:
                break
        return self._sanitize_finding_principle_links(
            sanitized.model_copy(update={"principle_ids": ordinary[:3]})
        )

    def _sanitize_finding_principle_links(
        self, finding: DataFinding
    ) -> DataFinding:
        sanitized = self._sanitize_public_finding(finding)
        principle_ids: list[str] = []
        requested_ids = [
            *sanitized.principle_ids,
            *_foundation_ids_for_finding(sanitized),
        ]
        for identifier in dict.fromkeys(requested_ids):
            detail = self.search.principle(identifier)
            if detail is not None and _principle_relevant_to_finding(
                sanitized, detail
            ):
                principle_ids.append(identifier)
        return sanitized.model_copy(update={"principle_ids": principle_ids})

    @staticmethod
    def _latex_text(value: Any) -> str:
        normalized = " ".join(str(value).replace("\\", " ").split())[:80]
        return (
            normalized.replace("{", "(")
            .replace("}", ")")
            .replace("_", r"\_")
            .replace("%", r"\%")
            .replace("&", r"\&")
            .replace("#", r"\#")
        )

    @classmethod
    def _compact_rule_parameters(cls, value: Any, *, depth: int = 0) -> Any:
        """Bound fitted-value receipts without hiding scientific meaning."""

        if depth >= 4:
            return "…"
        if isinstance(value, dict):
            return {
                str(key)[:120]: cls._compact_rule_parameters(item, depth=depth + 1)
                for key, item in list(value.items())[:30]
            }
        if isinstance(value, (list, tuple)):
            retained = [
                cls._compact_rule_parameters(item, depth=depth + 1)
                for item in list(value)[:16]
            ]
            if len(value) > 16:
                retained.append(f"… {len(value) - 16} more")
            return retained
        if isinstance(value, str):
            return value[:500]
        return value

    @classmethod
    def _rule_from_test(
        cls, finding: DataFinding, test: dict[str, Any]
    ) -> DataRule | None:
        """Project only executed formula results with a real split receipt.

        This is intentionally deterministic.  Text synthesis cannot create a
        Rule, change an equation coefficient, or turn a failed holdout into a
        passing one.
        """

        if finding.status != "supported_candidate" or str(test.get("state")) != "succeeded":
            return None
        linked_finding_id = str(test.get("finding_id") or "")
        if linked_finding_id and linked_finding_id != finding.finding_id:
            return None
        estimate = dict(test.get("estimate") or {})
        analysis_plan = dict(test.get("analysis_plan") or {})
        operator = str(analysis_plan.get("operator") or "")
        if operator == "mechanistic_response_curve":
            # This broad screening operator deliberately fits simple numeric
            # pairs. Its output is useful evidence, but never a domain law.
            return None
        rule_title = finding.title
        rule_interpretation = (
            finding.practical_value.strip()
            or finding.interpretation.strip()
            or finding.claim.strip()
        )
        expression = str(test.get("expression_latex") or "").strip()
        variables = [
            dict(item)
            for item in list(test.get("equation_variables") or [])
            if isinstance(item, dict)
        ]
        split = dict(test.get("split_validation") or {})

        # Backward-compatible projection for saved v1.4.2 light-curve receipts.
        # The amplitude/period values came from executed code; phi is explicitly
        # a fitted nuisance phase rather than an invented number.
        if not expression and operator == "light_curve_periodicity":
            # An ensemble finding may cite all constituent tests, but no
            # single-target equation is evidence for that aggregate claim.
            if len(finding.test_ids) != 1:
                return None
            period = estimate.get("period_days")
            amplitude = estimate.get("fractional_semi_amplitude")
            sensitivities = [
                dict(item)
                for item in list(test.get("sensitivities") or [])
                if isinstance(item, dict)
            ]
            if not isinstance(period, (int, float)) or not isinstance(
                amplitude, (int, float)
            ):
                return None
            if len(sensitivities) < 2 or not bool(
                estimate.get("contiguous_half_harmonic_stable")
            ):
                return None
            expression = (
                r"\Delta F(t)=A\sin\!\left(\frac{2\pi t}{P}+\phi\right)+\varepsilon(t)"
            )
            target = dict(estimate.get("target") or {})
            target_id = str(target.get("tic_id") or "unlabelled target")
            rule_title = (
                f"TIC {target_id}: {float(period):.3f}-day modulation at "
                f"{float(amplitude):.3g} fractional semi-amplitude"
            )
            rule_interpretation = (
                f"For TIC {target_id}, the {float(period):.3f}-day harmonic was recovered "
                "in both chronological halves. This supports time-local stability of the "
                "periodic form, not an independently replicated stellar mechanism."
            )
            variables = [
                {"symbol": "t", "meaning": "time", "unit": "day"},
                {
                    "symbol": r"\Delta F",
                    "meaning": "detrended fractional flux",
                    "unit": "relative flux",
                },
                {
                    "symbol": r"\phi",
                    "meaning": "fitted nuisance phase",
                    "unit": "radian",
                },
            ]
            split = {
                "strategy": "contiguous_half_period_replication",
                "selection_lock": (
                    "the period family was recomputed independently in both chronological halves"
                ),
                "development": sensitivities[0],
                "test": {**sensitivities[1], "passed": True},
            }

        # A generic two-column line is an executed observation, not a reusable
        # scientific Rule. Domain operators may still use linearized physical
        # laws when the equation family, units, boundary, and falsifier exist.
        if not expression and operator == "shd_aperture_thickness_fixed_effect_coupling":
            coefficient = estimate.get("partial_correlation")
            uncertainty = dict(test.get("uncertainty") or {})
            leave_one_out = [
                float(value)
                for value in list(
                    uncertainty.get("leave_one_hardware_out_correlations") or []
                )
                if isinstance(value, (int, float))
            ]
            p_value = uncertainty.get("exact_two_sided_sign_flip_p")
            passed = (
                isinstance(coefficient, (int, float))
                and isinstance(p_value, (int, float))
                and float(p_value) <= 0.05
                and len(leave_one_out) >= 5
                and all(value * float(coefficient) > 0 for value in leave_one_out)
            )
            if passed:
                expression = (
                    r"\rho\!\left(A^{\perp}_{h,p},T^{\perp}_{h,p}\mid r,h\right)"
                    r"=\rho_{*}>0,\quad \operatorname{sign}(\rho_{-h})="
                    r"\operatorname{sign}(\rho_{*})"
                )
                rule_title = "Aperture-thickness residual coupling survives hardware exclusion"
                rule_interpretation = (
                    f"After removing cubic radius and hardware baselines, the residual "
                    f"coupling was {float(coefficient):.3f}; every leave-one-hardware-out "
                    "estimate retained its direction. Aperture is therefore a reproducible "
                    "secondary term, not a standalone thickness law."
                )
                variables = [
                    {
                        "symbol": r"A_{\mathrm{res}}",
                        "meaning": "aperture residual after radial and hardware baselines",
                    },
                    {
                        "symbol": r"T_{\mathrm{res}}",
                        "meaning": "thickness residual after radial and hardware baselines",
                    },
                ]
                split = {
                    "strategy": "leave_one_hardware_out",
                    "selection_lock": (
                        "cubic radius and hardware baselines were fixed before each hardware exclusion"
                    ),
                    "development": {
                        "hardware_count": estimate.get("varying_hardware_maps"),
                        "partial_correlation": coefficient,
                    },
                    "test": {
                        "passed": True,
                        "leave_one_hardware_out_min": min(leave_one_out),
                        "leave_one_hardware_out_max": max(leave_one_out),
                        "exact_p_value": p_value,
                    },
                }

        if not expression and operator == "shd_conductance_deposition_regime_reversal":
            medians = dict(estimate.get("family_median_correlations") or {})
            counts = dict(estimate.get("map_counts") or {})
            positives = dict(estimate.get("positive_map_counts") or {})
            uncertainty = dict(test.get("uncertainty") or {})
            p_value = uncertainty.get("two_sided_fisher_exact_p")
            named = [
                (str(name), float(value))
                for name, value in sorted(medians.items())
                if isinstance(value, (int, float))
            ]
            passed = (
                len(named) >= 2
                and isinstance(p_value, (int, float))
                and float(p_value) <= 0.05
                and min(int(value) for value in counts.values()) >= 5
            )
            if passed:
                expression = (
                    r"\widetilde{\rho}_{C,T\mid g}=\rho_g,\qquad "
                    r"\rho_{g_1}\rho_{g_2}<0"
                )
                rule_title = "Process family switches the sign of conductance-thickness coupling"
                rule_interpretation = (
                    "Hardware-level maps separate into opposite conductance-thickness "
                    "coupling regimes. A conductance correction must therefore be conditioned "
                    "on deposition process family rather than transferred globally."
                )
                variables = [
                    {"symbol": "C", "meaning": "within-wafer conductance"},
                    {"symbol": "T", "meaning": "within-wafer thickness"},
                ]
                split = {
                    "strategy": "cross_hardware_process_strata",
                    "selection_lock": (
                        "correlation sign was evaluated per hardware map before the process-family comparison"
                    ),
                    "development": {
                        "family_medians": medians,
                        "hardware_map_counts": counts,
                    },
                    "test": {
                        "passed": True,
                        "positive_map_counts": positives,
                        "exact_fisher_p_value": p_value,
                    },
                }

        test_receipt = dict(split.get("test") or {})
        if not expression or not split or not bool(test_receipt.get("passed")):
            return None
        rule_gate = dict(split.get("rule_gate") or {})
        required_gate_fields = {
            "interpretable_law_family",
            "held_out_baseline_improvement",
            "parameter_stability",
            "unit_plausibility",
            "negative_control",
            "transfer_boundary_declared",
        }
        if not required_gate_fields <= set(rule_gate) or not all(
            bool(rule_gate.get(field)) for field in required_gate_fields
        ):
            # An equation remains visible in its executed Test receipt, but it
            # is not promoted into the permanent Rules taxonomy until every
            # scientific-law gate is explicit and passing.
            return None
        test_receipt["negative_control"] = dict(
            split.get("negative_control") or {}
        )
        test_receipt["rule_gate"] = rule_gate
        independent_units = int(test.get("independent_unit_count") or 0)
        validation_status: Literal[
            "validated", "internally_stable", "exploratory_expression"
        ] = "internally_stable"
        if finding.validation_level != "exploratory" and independent_units >= 50:
            validation_status = "validated"
        elif finding.validation_level == "exploratory" or independent_units < 50:
            validation_status = "exploratory_expression"
        rule_id = "rule:" + canonical_sha256(
            {
                "study": finding.study_id,
                "finding": finding.finding_id,
                "test": test.get("test_id"),
                "expression": expression,
                "split": split,
            }
        )[:24]
        return DataRule(
            rule_id=rule_id,
            study_id=finding.study_id,
            finding_id=finding.finding_id,
            title=rule_title,
            rule_family=operator,
            expression_latex=expression,
            interpretation=rule_interpretation[:1_200],
            equation_variables=variables,
            parameter_estimates=cls._compact_rule_parameters(
                {
                    "executed_fit": estimate,
                    "uncertainty": dict(test.get("uncertainty") or {}),
                }
            ),
            sample_definition=str(test.get("sample_definition") or ""),
            split_strategy=str(split.get("strategy") or "executed split"),
            development=dict(split.get("development") or {}),
            test=test_receipt,
            uncertainty=dict(test.get("uncertainty") or {}),
            diagnostics=[str(item) for item in list(test.get("diagnostics") or [])],
            test_ids=[str(test.get("test_id"))],
            evidence_ids=(list(finding.evidence_ids) if len(finding.test_ids) == 1 else []),
            validation_status=validation_status,
            created_at=finding.created_at,
        )

    @staticmethod
    def _headline_metrics(metrics: dict[str, Any], evidence_ids: list[str]) -> list[dict[str, Any]]:
        labels = {"mean_map_mape_percent": "Mean field MAPE", "worst_map_mape_percent": "Worst field MAPE", "mean_absolute_residual_neighbor_correlation": "Residual correlation"}
        preferred = ("normalized_rmse", "mean_map_mape_percent", "worst_map_mape_percent", "r_squared", "correlation", "coefficient", "accuracy", "auc", "p_value")
        values: list[dict[str, Any]] = []
        def visit(payload: dict[str, Any], prefix: str = "") -> None:
            for key in sorted(payload, key=lambda name: (preferred.index(name) if name in preferred else len(preferred), name)):
                value = payload[key]
                locator = f"{prefix}.{key}" if prefix else key
                if isinstance(value, dict) and not prefix:
                    visit(value, locator)
                elif isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(float(value)):
                    values.append({"label": labels.get(key, key.replace("_", " ")), "value": value, "unit": "%" if key.endswith("percent") else "", "metric_path": locator, "evidence_ids": evidence_ids})
        visit(metrics)
        return values[:3]

    def rules(self, study_id: str) -> list[dict[str, Any]]:
        if self.repository.data_study(study_id) is None:
            raise KeyError(f"unknown data study: {study_id}")
        tests = {
            str(item.get("test_id")): item
            for item in self.repository.data_tests(study_id)
        }
        scientific_laws = self.repository.scientific_law_families(study_id)
        finding_ids = {item.finding_id for item in self.repository.data_findings(study_id)}
        scientific_rules: list[dict[str, Any]] = []
        for law in scientific_laws:
            if law.evidence_tier == "candidate":
                continue
            calibrations = self.repository.scientific_law_calibrations(law.law_id)
            calibration = calibrations[0] if calibrations else None
            linked_test = next(
                (tests[test_id] for test_id in law.test_ids if test_id in tests),
                {},
            )
            split = (
                self.repository.scientific_split_manifest(calibration.split_manifest_id)
                if calibration is not None
                else None
            )
            independent_units = (
                split.development_unit_count
                + split.validation_unit_count
                + split.test_unit_count
                if split is not None
                else 0
            )
            scientific_rules.append(
                {
                    "rule_id": law.law_id,
                    "law_id": law.law_id,
                    "study_id": law.study_id,
                    "finding_id": str(linked_test.get("finding_id") or "") if linked_test.get("finding_id") in finding_ids else "",
                    "finding_pending": bool(linked_test.get("finding_id") and linked_test.get("finding_id") not in finding_ids),
                    "title": law.name,
                    "rule_family": law.family_kind,
                    "rule_kind": law.rule_kind,
                    "engine_version": law.engine_version,
                    "executor_id": law.executor_id,
                    "executor_version": law.executor_version,
                    "signature_identity": law.signature_identity,
                    "expression_latex": law.expression_latex,
                    # The canonical AST remains the executable identity.  The
                    # bound test expression restores the scientifically named
                    # left-hand side for human display without changing that
                    # identity or embedding fitted coefficients in the family.
                    "display_expression_latex": str(
                        linked_test.get("expression_latex") or law.expression_latex
                    ),
                    "equation_ast": law.equation_ast.model_dump(mode="json"),
                    "canonical_ast_digest": law.canonical_ast_digest,
                    "interpretation": law.scientific_meaning,
                    "equation_variables": law.parameter_roles,
                    "variable_bindings": law.variable_bindings,
                    "target": law.target,
                    "baseline_comparison": dict(linked_test.get("split_validation") or {}).get("baseline_comparison", {}),
                    "parameter_estimates": (
                        calibration.fitted_parameters if calibration is not None else {}
                    ),
                    "sample_definition": law.scope,
                    "headline_metrics": self._headline_metrics(calibration.test_metrics if calibration else {}, law.evidence_ids),
                    "split_strategy": split.strategy if split is not None else "",
                    "development": (
                        calibration.development_metrics if calibration is not None else {}
                    ),
                    "test": (
                        {
                            "passed": bool(law.gate_summary.get("passed")),
                            **calibration.test_metrics,
                            "transfer_boundary": law.scope,
                        }
                        if calibration is not None
                        else {"passed": False}
                    ),
                    "uncertainty": (
                        calibration.parameter_uncertainty if calibration is not None else {}
                    ),
                    "diagnostics": [
                        f"Evidence tier: {law.evidence_tier.replace('_', ' ')}.",
                        "The equation AST, not LaTeX, is the executable identity.",
                        "Internal evidence remains selection-affected until prospectively sealed.",
                    ],
                    "test_ids": law.test_ids,
                    "evidence_ids": law.evidence_ids,
                    "validation_status": (
                        "internally_stable"
                        if independent_units >= 50
                        else "exploratory_expression"
                    ),
                    "record_kind": "data_rule",
                    "scientific_law": True,
                    "evidence_tier": law.evidence_tier,
                    "gate_summary": law.gate_summary,
                    "gate_receipts": [
                        item.model_dump(mode="json") for item in law.gate_receipts
                    ],
                    "calibration_count": len(calibrations),
                    "created_at": law.created_at,
                }
            )
        # ScientificLawFamily is the sole Rule source.  Historical expression
        # tests remain available through the report and legacy-equation count,
        # but can never be promoted by a GET-time text projection.
        with self.repository.connect() as conn:
            evidence = [json.loads(row[0]) for row in conn.execute(
                "SELECT payload_json FROM data_evidence_links WHERE study_id=? ORDER BY evidence_id",
                (study_id,),
            )]
        return present_rules(scientific_rules, evidence)

    def rule_candidates(self, study_id: str) -> list[dict[str, Any]]:
        """Return executed equations that did not satisfy every Rule gate.

        Candidates are deliberately kept outside ``rules()``.  This gives a
        scientist a complete account of the law search without making a failed
        holdout, an under-replicated equation, or a merely plausible formula
        look like an accepted Rule.
        """

        if self.repository.data_study(study_id) is None:
            raise KeyError(f"unknown data study: {study_id}")
        required_gate_fields = (
            "interpretable_law_family",
            "held_out_baseline_improvement",
            "parameter_stability",
            "unit_plausibility",
            "negative_control",
            "transfer_boundary_declared",
        )
        promoted_test_ids = {
            str(test_id)
            for rule in self.rules(study_id)
            for test_id in list(rule.get("test_ids") or [])
        }
        findings = {
            item.finding_id: self._sanitize_public_finding(item)
            for item in self.repository.data_findings(study_id)
        }
        output: list[dict[str, Any]] = []
        typed_test_ids: set[str] = set()
        for law in self.repository.scientific_law_families(study_id):
            typed_test_ids.update(str(item) for item in law.test_ids)
            if law.evidence_tier != "candidate":
                continue
            calibrations = self.repository.scientific_law_calibrations(law.law_id)
            calibration = calibrations[0] if calibrations else None
            output.append(
                {
                    "candidate_id": law.law_id,
                    "rule_id": law.law_id,
                    "law_id": law.law_id,
                    "record_kind": "law_candidate",
                    "study_id": law.study_id,
                    "title": law.name,
                    "rule_family": law.family_kind,
                    "rule_kind": law.rule_kind,
                    "expression_latex": law.expression_latex,
                    "equation_ast": law.equation_ast.model_dump(mode="json"),
                    "canonical_ast_digest": law.canonical_ast_digest,
                    "equation_variables": law.variable_bindings,
                    "parameter_estimates": (
                        calibration.fitted_parameters if calibration is not None else {}
                    ),
                    "sample_definition": law.scope,
                    "headline_metrics": self._headline_metrics(calibration.test_metrics if calibration else {}, law.evidence_ids),
                    "split_strategy": (
                        self.repository.scientific_split_manifest(
                            calibration.split_manifest_id
                        ).strategy
                        if calibration is not None
                        and self.repository.scientific_split_manifest(
                            calibration.split_manifest_id
                        ) is not None
                        else ""
                    ),
                    "test": (
                        calibration.test_metrics if calibration is not None else {}
                    ),
                    "uncertainty": (
                        calibration.parameter_uncertainty if calibration is not None else {}
                    ),
                    "diagnostics": (
                        list(calibration.residual_diagnostics.get("diagnostics") or [])
                        if calibration is not None
                        else []
                    ),
                    "test_ids": law.test_ids,
                    "evidence_ids": law.evidence_ids,
                    "validation_status": "held_back_candidate",
                    "evidence_tier": law.evidence_tier,
                    "engine_version": law.engine_version,
                    "executor_id": law.executor_id,
                    "executor_version": law.executor_version,
                    "signature_identity": law.signature_identity,
                    "gate_receipts": [
                        item.model_dump(mode="json") for item in law.gate_receipts
                    ],
                    "failed_gates": list(law.gate_summary.get("failed_gates") or []),
                    "held_back_reason": (
                        "The equation was executed but did not pass every evidence-bearing Rule gate."
                    ),
                    "interpretation": law.scientific_meaning,
                    "created_at": law.created_at,
                }
            )
        for test in self.repository.data_tests(study_id):
            test_id = str(test.get("test_id") or "")
            expression = str(test.get("expression_latex") or "").strip()
            if not expression or test_id in promoted_test_ids or test_id in typed_test_ids:
                continue
            split = dict(test.get("split_validation") or {})
            gate = dict(split.get("rule_gate") or {})
            # Historical runs stored many fitted expressions before the
            # formula-first gate contract existed. They remain auditable in the
            # report, but presenting a coefficient-bearing regression as a new
            # law candidate repeats the exact UX/scientific failure this API is
            # designed to prevent.
            if not gate:
                continue
            failed_gates = [
                field for field in required_gate_fields if not bool(gate.get(field))
            ]
            test_receipt = dict(split.get("test") or {})
            finding = findings.get(str(test.get("finding_id") or ""))
            reasons: list[str] = []
            if finding is None or finding.status != "supported_candidate":
                reasons.append("the scientific finding did not survive its evidence gate")
            if not split:
                reasons.append("no separated validation split was executed")
            elif not bool(test_receipt.get("passed")):
                reasons.append("the separated validation split did not pass")
            if failed_gates:
                reasons.append(
                    "required Rule gates remain open: "
                    + ", ".join(field.replace("_", " ") for field in failed_gates)
                )
            analysis_plan = dict(test.get("analysis_plan") or {})
            output.append(
                {
                    "candidate_id": "rule-candidate:"
                    + canonical_sha256(
                        {"study": study_id, "test": test_id, "expression": expression}
                    )[:24],
                    "rule_id": "rule-candidate:"
                    + canonical_sha256(
                        {"study": study_id, "test": test_id, "expression": expression}
                    )[:24],
                    "record_kind": "law_candidate",
                    "study_id": study_id,
                    "finding_id": str(test.get("finding_id") or ""),
                    "title": finding.title if finding is not None else "Tested law candidate",
                    "rule_family": str(analysis_plan.get("operator") or "scientific_law"),
                    "expression_latex": expression,
                    "equation_variables": [
                        dict(item)
                        for item in list(test.get("equation_variables") or [])
                        if isinstance(item, dict)
                    ],
                    "parameter_estimates": self._compact_rule_parameters(
                        {
                            "executed_fit": dict(test.get("estimate") or {}),
                            "uncertainty": dict(test.get("uncertainty") or {}),
                        }
                    ),
                    "sample_definition": str(test.get("sample_definition") or ""),
                    "split_strategy": str(split.get("strategy") or "not available"),
                    "development": dict(split.get("development") or {}),
                    "test": test_receipt,
                    "uncertainty": dict(test.get("uncertainty") or {}),
                    "diagnostics": [
                        str(item) for item in list(test.get("diagnostics") or [])
                    ],
                    "test_ids": [test_id] if test_id else [],
                    "validation_status": "held_back_candidate",
                    "evidence_tier": "candidate",
                    "failed_gates": failed_gates,
                    "held_back_reason": "; ".join(reasons)
                    or "the equation remains a candidate pending independent confirmation",
                    "interpretation": (
                        finding.interpretation if finding is not None else ""
                    ),
                    "created_at": str(test.get("created_at") or ""),
                }
            )
        output.sort(key=lambda item: (str(item["title"]), str(item["candidate_id"])))
        return output

    def legacy_equation_count(self, study_id: str) -> int:
        """Count pre-gate expressions retained only in the historical report."""

        if self.repository.data_study(study_id) is None:
            raise KeyError(f"unknown data study: {study_id}")
        promoted_test_ids = {
            str(test_id)
            for rule in self.rules(study_id)
            for test_id in list(rule.get("test_ids") or [])
        }
        return sum(
            1
            for test in self.repository.data_tests(study_id)
            if str(test.get("expression_latex") or "").strip()
            and str(test.get("test_id") or "") not in promoted_test_ids
            and not dict(test.get("split_validation") or {}).get("rule_gate")
        )

    def programs(self, study_id: str) -> list[dict[str, Any]]:
        if self.repository.data_study(study_id) is None:
            raise KeyError(f"unknown data study: {study_id}")
        return [
            item.model_dump(mode="json")
            for item in self.repository.scientific_programs(study_id)
        ]

    def program(self, study_id: str, program_id: str) -> dict[str, Any]:
        program = self.repository.scientific_program(study_id, program_id)
        if program is None:
            raise KeyError(f"unknown scientific program: {program_id}")
        split = (
            self.repository.scientific_split_manifest(program.split_manifest_id)
            if program.split_manifest_id
            else None
        )
        transform = (
            self.repository.scientific_transform_graph(program.transform_graph_id)
            if program.transform_graph_id
            else None
        )
        split_manifests = (
            self.repository.scientific_split_manifests(study_id)
            if program.track == "predictive_closure"
            else []
        )
        transform_graphs = (
            self.repository.scientific_transform_graphs(study_id)
            if program.track == "predictive_closure"
            else []
        )
        return {
            **program.model_dump(mode="json"),
            "split_manifest": split.model_dump(mode="json") if split else None,
            "transform_graph": transform.model_dump(mode="json") if transform else None,
            "split_manifests": [
                item.model_dump(mode="json") for item in split_manifests
            ],
            "transform_graphs": [
                item.model_dump(mode="json") for item in transform_graphs
            ],
            "decisions": [
                item.model_dump(mode="json")
                for item in self.repository.scientific_decisions(program_id)
            ],
            "candidate_frontier": [
                item.model_dump(mode="json")
                for item in self.repository.scientific_law_candidates(program_id)
            ],
        }

    def laws(self, study_id: str) -> list[dict[str, Any]]:
        if self.repository.data_study(study_id) is None:
            raise KeyError(f"unknown data study: {study_id}")
        tests = {
            str(item.get("test_id") or ""): item
            for item in self.repository.data_tests(study_id)
        }
        output: list[dict[str, Any]] = []
        for law in self.repository.scientific_law_families(study_id):
            calibrations = self.repository.scientific_law_calibrations(law.law_id)
            headline = calibrations[0] if calibrations else None
            linked_test = next(
                (tests[test_id] for test_id in law.test_ids if test_id in tests),
                {},
            )
            output.append(
                {
                    **law.model_dump(mode="json"),
                    "display_expression_latex": str(
                        linked_test.get("expression_latex") or law.expression_latex
                    ),
                    "promoted": law.evidence_tier != "candidate",
                    "calibration_count": len(calibrations),
                    "headline_metrics": (
                        {
                            "development": headline.development_metrics,
                            "validation": headline.validation_metrics,
                            "test": headline.test_metrics,
                            "worst_unit": headline.worst_unit_metrics,
                        }
                        if headline
                        else {}
                    ),
                }
            )
        return output

    def law(self, study_id: str, law_id: str) -> dict[str, Any]:
        law = self.repository.scientific_law_family(study_id, law_id)
        if law is None:
            raise KeyError(f"unknown scientific law: {law_id}")
        calibrations = self.repository.scientific_law_calibrations(law_id)
        evaluations = self.repository.scientific_law_evaluations(law_id)
        program = self.repository.scientific_program(study_id, law.program_id)
        tests = {
            str(item.get("test_id") or ""): item
            for item in self.repository.data_tests(study_id)
        }
        linked_test = next(
            (tests[test_id] for test_id in law.test_ids if test_id in tests),
            {},
        )
        return {
            **law.model_dump(mode="json"),
            "display_expression_latex": str(
                linked_test.get("expression_latex") or law.expression_latex
            ),
            "promoted": law.evidence_tier != "candidate",
            "program": program.model_dump(mode="json") if program else None,
            "calibrations": [item.model_dump(mode="json") for item in calibrations],
            "tests": [tests[identifier] for identifier in law.test_ids if identifier in tests],
            "evaluations": [item.model_dump(mode="json") for item in evaluations],
            "candidate_frontier": self.repository.scientific_law_candidate_summaries(law.program_id, law_id),
            "candidate_artifacts_program_id": law.program_id,
        }

    def law_calibration(
        self, study_id: str, law_id: str, calibration_id: str
    ) -> dict[str, Any]:
        calibration = self.repository.scientific_law_calibration(
            study_id, law_id, calibration_id
        )
        if calibration is None:
            raise KeyError(f"unknown scientific-law calibration: {calibration_id}")
        return calibration.model_dump(mode="json")

    def artifacts(self, study_id: str) -> list[dict[str, Any]]:
        if self.repository.data_study(study_id) is None:
            raise KeyError(f"unknown data study: {study_id}")
        if not study_id.startswith("study:"):
            raise ValueError("invalid study identifier")
        root = self.storage.artifacts_dir / "data-discovery" / study_id
        if not root.is_dir():
            return []
        output: list[dict[str, Any]] = []
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            relative = path.relative_to(root).as_posix()
            output.append(
                {
                    "artifact_id": "artifact:" + canonical_sha256(
                        {"study": study_id, "relative": relative}
                    )[:24],
                    "name": path.name,
                    "kind": path.suffix.casefold().lstrip(".") or "file",
                    "byte_size": path.stat().st_size,
                    "sha256": file_sha256(path),
                    "derived": True,
                }
            )
        return output

    @classmethod
    def _sanitize_public_finding(cls, finding: DataFinding) -> DataFinding:
        relevant = [
            source
            for source in finding.prior_art
            if _prior_art_title_relevant(finding, source)
        ]
        sanitized = finding.model_copy(
            update={
                "prior_art": relevant,
                "novelty_status": (
                    finding.novelty_status if relevant else "not_assessed"
                ),
            }
        )
        # Presentation is read-only: finalization also serves write workflows,
        # but a GET must retain the persisted time and a stable response body.
        return cls._finalize_insight_contract(sanitized).model_copy(
            update={"updated_at": finding.updated_at}
        )

    @staticmethod
    def _sanitize_extra_principle(
        principle: DataExtraPrinciple,
        findings: list[DataFinding] | None = None,
    ) -> DataExtraPrinciple | None:
        context = " ".join(
            (
                principle.title,
                principle.claim,
                principle.explanatory_gap,
                principle.mechanism,
            )
        )
        sources = [
            source
            for source in principle.supporting_sources
            if _source_title_relevant_to_context(context, source)
        ]
        if not sources:
            return None
        finding_by_id = {
            item.finding_id: item for item in (findings or [])
        }
        if any(
            identifier in finding_by_id
            and _extra_principle_duplicates_finding(
                principle.claim,
                finding_by_id[identifier],
            )
            for identifier in principle.related_finding_ids
        ):
            return None
        return principle.model_copy(update={"supporting_sources": sources})

    def extra_principles(self, study_id: str) -> list[dict[str, Any]]:
        if self.repository.data_study(study_id) is None:
            raise KeyError(f"unknown data study: {study_id}")
        findings = self.repository.data_findings(study_id)
        return [
            sanitized.model_dump(mode="json")
            for item in self.repository.data_extra_principles(study_id)
            if (sanitized := self._sanitize_extra_principle(item, findings)) is not None
        ]

    def linked_principles(self, study_id: str) -> dict[str, Any]:
        findings = [
            self._sanitize_finding_principle_links(item)
            for item in self.repository.data_findings(study_id)
        ]
        if self.repository.data_study(study_id) is None:
            raise KeyError(f"unknown data study: {study_id}")
        finding_principle_ids = list(
            dict.fromkeys(
                principle_id
                for finding in findings
                for principle_id in finding.principle_ids
                if principle_id
            )
        )
        # A Principle that materially framed an executable hypothesis or
        # ScientificProgram remains part of the study's knowledge lineage even
        # when the corresponding candidate is refuted or held back.  Merely
        # retrieved candidates are not persisted on either record and remain
        # outside the graph.
        scientific_programs = self.repository.scientific_programs(study_id)
        planning_principle_ids = list(
            dict.fromkeys(
                [
                    *[
                        principle_id
                        for hypothesis in self.repository.data_hypotheses(study_id)
                        for principle_id in hypothesis.principle_ids
                        if principle_id
                    ],
                    *[
                        principle_id
                        for program in scientific_programs
                        for principle_id in program.principle_ids
                        if principle_id
                    ],
                ]
            )
        )
        planning_principle_ids = [
            principle_id
            for principle_id in planning_principle_ids
            if principle_id not in finding_principle_ids
        ][:12]
        used_principle_ids = [*finding_principle_ids, *planning_principle_ids]
        principles: list[dict[str, Any]] = []
        foundations: list[dict[str, Any]] = []
        seen_principles: set[str] = set()
        seen_foundations: set[str] = set()
        for identifier in used_principle_ids:
            detail = self.search.principle(identifier)
            if detail is None:
                continue
            principle_id = str(
                detail.get("id") or detail.get("principle_id") or identifier
            )
            if principle_id not in seen_principles:
                seen_principles.add(principle_id)
                principles.append(
                    {
                        **detail,
                        "knowledge_usage": (
                            "finding_interpretation"
                            if identifier in finding_principle_ids
                            else "hypothesis_planning"
                        ),
                    }
                )
            for item in list(detail.get("foundations") or []):
                foundation = dict(item) if isinstance(item, dict) else {}
                meta = dict(foundation.get("meta_principle") or {})
                meta_id = str(
                    meta.get("id")
                    or meta.get("principle_id")
                    or foundation.get("meta_principle_id")
                    or ""
                )
                if meta_id and meta_id not in seen_foundations:
                    seen_foundations.add(meta_id)
                    foundations.append(
                        {
                            **meta,
                            "id": meta_id,
                            "principle_id": meta_id,
                            "principle_class": "meta",
                            "link": dict(foundation.get("link") or {}),
                            "relations": [
                                {
                                    "source": principle_id,
                                    "target": meta_id,
                                    "edge_class": "foundation",
                                    "relation_type": str(
                                        foundation.get("relation_type")
                                        or dict(foundation.get("link") or {}).get(
                                            "relation_type"
                                        )
                                        or "grounded in"
                                    ),
                                    "rationale": str(
                                        foundation.get("rationale")
                                        or dict(foundation.get("link") or {}).get(
                                            "rationale"
                                        )
                                        or "Established foundation link."
                                    ),
                                }
                            ],
                        }
                    )
        return {
            "principles": principles,
            "foundations": foundations,
            "used_principle_ids": [
                str(item.get("id") or item.get("principle_id") or "")
                for item in principles
                if item.get("id") or item.get("principle_id")
            ],
        }

    def finding(self, study_id: str, finding_id: str) -> dict[str, Any]:
        result = self.repository.data_finding(study_id, finding_id)
        if result is None:
            raise KeyError(f"unknown data finding: {finding_id}")
        finding = self._sanitize_finding_principle_links(
            DataFinding.model_validate(
                {
                    key: value
                    for key, value in result.items()
                    if key in DataFinding.model_fields
                }
            )
        )
        return {
            **result,
            **finding.model_dump(mode="json"),
            "plain_language_interpretation": explain_finding(finding.model_dump(mode="json")),
        }

    def cancel(self, study_id: str) -> dict[str, Any]:
        # This lock also guards final publication. A stop arriving after commit
        # is an idempotent read; a stop accepted first prevents success commit.
        with self._lock:
            study = self.repository.data_study(study_id)
            if study is None:
                raise KeyError(f"unknown data study: {study_id}")
            if study["state"] in {"succeeded", "partial", "failed", "cancelled", "interrupted", "data_insufficient", "cancelling"}:
                return {**(self.repository.data_study_status(study_id) or study), "counts": self.repository.data_study_counts(study_id)}
            token = self._cancel.get(study_id)
            future = self._futures.get(study_id)
            queued = future is not None and future.cancel()
            # A restored run with no owning worker can stop immediately too.
            stopped = queued or token is None
            state = "cancelled" if stopped else "cancelling"
            self.repository.update_data_study(study_id, state=state)
            self.repository.update_data_session_state(str(study.get("session_id") or ""), state)
            job = self.repository.get_job(str(study["job_id"]))
            if job:
                self.repository.save_job(job.model_copy(update={
                    "state": state, "last_activity_at": utc_now(), "updated_at": utc_now(),
                    "status_message": "Discovery cancelled before inventory; no analysis started" if queued else "Discovery stopped; completed evidence was preserved" if stopped else "Stopping active work and preserving completed evidence",
                }))
            if token is not None:
                token.set()
            if queued:
                self._futures.pop(study_id, None)
                self._cancel.pop(study_id, None)
                self._pause.pop(study_id, None)
            self._event(str(study["job_id"]), state, "Stopped" if stopped else "Stopping", "Stop requested; completed evidence is preserved", study_id=study_id)
        return {**(self.repository.data_study_status(study_id) or study), "counts": self.repository.data_study_counts(study_id), "execution": {"queue_position": 0, "worker_capacity": self.worker_capacity}}

    def pause(self, study_id: str) -> dict[str, Any]:
        study = self.repository.data_study(study_id)
        if study is None:
            raise KeyError(f"unknown data study: {study_id}")
        with self._lock:
            token = self._pause.get(study_id)
        if token is None:
            raise ValueError("only an active data discovery can be paused")
        token.set()
        self.repository.update_data_study(study_id, state="pausing")
        job = self.repository.get_job(str(study["job_id"]))
        if job:
            self.repository.update_data_session_state(
                str(study.get("session_id") or ""), "pausing"
            )
            self.repository.save_job(
                job.model_copy(
                    update={
                        "state": "pausing",
                        "status_message": "Pausing at the next safe analysis boundary",
                        "last_activity_at": utc_now(),
                        "updated_at": utc_now(),
                    }
                )
            )
        return self.get(study_id)

    def resume(self, study_id: str) -> dict[str, Any]:
        study = self.repository.data_study(study_id)
        if study is None:
            raise KeyError(f"unknown data study: {study_id}")
        with self._lock:
            token = self._pause.get(study_id)
        if token is None:
            raise ValueError("only an active data discovery can be resumed")
        token.clear()
        self.repository.update_data_study(study_id, state="running")
        job = self.repository.get_job(str(study["job_id"]))
        if job:
            self.repository.update_data_session_state(
                str(study.get("session_id") or ""), "running"
            )
            self.repository.save_job(
                job.model_copy(
                    update={
                        "state": "running",
                        "status_message": "Discovery resumed",
                        "last_activity_at": utc_now(),
                        "updated_at": utc_now(),
                    }
                )
            )
        return self.get(study_id)

    def prepare_principle_draft(self, study_id: str, finding_id: str) -> dict[str, Any]:
        payload = self.repository.data_finding(study_id, finding_id)
        if payload is None:
            raise KeyError(f"unknown data finding: {finding_id}")
        finding = self._sanitize_public_finding(
            DataFinding.model_validate(
                {key: value for key, value in payload.items() if key in DataFinding.model_fields}
            )
        )
        if not finding.promotion_eligible:
            raise ValueError(
                "Principle drafting is blocked: " + "; ".join(finding.promotion_blockers)
            )
        draft = DataDerivedPrincipleDraft(
            draft_id="data-draft:"
            + canonical_sha256({"study": study_id, "finding": finding_id})[:24],
            finding_id=finding_id,
            study_id=study_id,
            title=finding.title,
            claim=finding.claim,
            scope="Candidate pattern in the exact source study and computed evidence anchors.",
            falsifier=finding.falsifiers[0],
            principle_links=list(finding.principle_ids),
        )
        self.repository.save_data_derived_draft(draft)
        return draft.model_dump(mode="json")

    def decide_draft(self, draft_id: str, state: Literal["approved", "rejected"]) -> dict[str, Any]:
        return self.repository.decide_data_derived_draft(draft_id, state).model_dump(mode="json")

    def artifact(self, study_id: str, artifact_id: str) -> tuple[Path, str]:
        if not artifact_id or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-_:." for character in artifact_id.casefold()):
            raise ValueError("invalid artifact identifier")
        root = (self.storage.artifacts_dir / "data-discovery" / study_id).resolve()
        if not root.is_dir():
            raise KeyError(f"unknown data discovery artifact: {artifact_id}")
        if artifact_id.startswith("artifact:"):
            path = next(
                (
                    candidate.resolve()
                    for candidate in root.rglob("*")
                    if candidate.is_file()
                    and "artifact:"
                    + canonical_sha256(
                        {
                            "study": study_id,
                            "relative": candidate.relative_to(root).as_posix(),
                        }
                    )[:24]
                    == artifact_id
                ),
                root / "missing",
            )
        else:
            path = (root / artifact_id).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise KeyError(f"unknown data discovery artifact: {artifact_id}")
        mime = {
            ".json": "application/json",
            ".md": "text/markdown",
            ".png": "image/png",
            ".svg": "image/svg+xml",
            ".py": "text/x-python",
        }.get(path.suffix.casefold(), "application/octet-stream")
        return path, mime

    def _refresh_extra_principle_exports(self, study_id: str) -> None:
        items = [
            DataExtraPrinciple.model_validate(item)
            for item in self.extra_principles(study_id)
        ]
        payload = {
            "schema_version": "principia.data-extra-principles/v1",
            "study_id": study_id,
            "record_kind": "extra_principle",
            "status": "provisional_research_synthesis",
            "items": [item.model_dump(mode="json") for item in items],
        }
        markdown = [
            "# Principia Extra Principles",
            "",
            f"Study: `{study_id}`",
            "",
            "These records passed a same-domain literature relevance gate. They remain provisional research syntheses, not established Global Cloud Principles.",
            "",
        ]
        for principle in items:
            markdown.extend(
                [
                    f"## {principle.title}",
                    "",
                    f"Record ID: `{principle.extra_principle_id}`",
                    "",
                    principle.claim,
                    "",
                    f"Explanatory gap: {principle.explanatory_gap}",
                    "",
                    f"Mechanism: {principle.mechanism}",
                    "",
                    "### Boundary conditions",
                    "",
                    *[f"- {item}" for item in principle.boundary_conditions],
                    "",
                    "### Falsifiers",
                    "",
                    *[f"- {item}" for item in principle.falsifiers],
                    "",
                    "### Supporting literature",
                    "",
                    *[
                        f"- {source.get('title') or source.get('source_key')}"
                        + (f" — {source.get('url')}" if source.get("url") else "")
                        for source in principle.supporting_sources
                    ],
                    "",
                ]
            )
        encoded_json = (
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode()
        encoded_md = ("\n".join(markdown).rstrip() + "\n").encode()
        for root in (self._artifact_root(study_id), self.outputs_root / study_id):
            root.mkdir(parents=True, exist_ok=True, mode=0o700)
            self._atomic_write(root / "extra-principles.json", encoded_json)
            self._atomic_write(root / "extra-principles.md", encoded_md)

    def source_assets(
        self, source_id: str, *, limit: int = 100, offset: int = 0
    ) -> dict[str, Any]:
        if self.repository.source_root(source_id) is None:
            raise KeyError(f"unknown Local source: {source_id}")
        return self.repository.data_assets(
            source_id=source_id, limit=limit, offset=offset
        )

    def preview(self, source_id: str, asset_id: str) -> dict[str, Any]:
        asset = self.repository.data_asset(asset_id)
        if asset is None or asset.source_id != source_id:
            raise KeyError(f"unknown data asset: {asset_id}")
        root = self.repository.source_root(source_id)
        if root is None:
            raise KeyError(f"unknown Local source: {source_id}")
        return build_preview(asset, root)

    def _run(self, study_id: str, cancellation: threading.Event) -> None:
        with cancellation_scope(cancellation):
            self._run_scoped(study_id, cancellation)

    def _run_scoped(self, study_id: str, cancellation: threading.Event) -> None:
        started = time.monotonic()
        study = self.repository.data_study(study_id)
        if study is None:
            return
        job_id = str(study["job_id"])
        request = dict(study["request"])
        budget = BUDGETS[str(request.get("budget") or "balanced")]  # type: ignore[index]
        try:
            self._check_control(study_id, cancellation)
            self.repository.update_data_session_state(
                str(study.get("session_id") or ""), "running"
            )
            self._set_phase(study_id, "inventory", 0.02, "Inventorying files")
            inventories = self._inventory_sources(study_id, list(study["source_ids"]), cancellation)
            source_digest = canonical_sha256(
                [{"source_id": key, "digest": value.source_digest} for key, value in inventories]
            )
            coverage = self._combined_coverage(inventories)
            self._event(
                job_id,
                "activity",
                "Inventory",
                f"Mapped {coverage['asset_count']} files into {coverage['view_count']} analyzable views across {len(coverage['modality_counts'])} modalities",
                study_id=study_id,
                counts={
                    "assets": coverage["asset_count"],
                    "views": coverage["view_count"],
                    "modalities": coverage["modality_counts"],
                },
            )
            self.repository.update_data_study(
                study_id, source_digest=source_digest, coverage=coverage
            )
            self._check_control(study_id, cancellation)

            self._set_phase(study_id, "understand", 0.22, "Inferring dataset relationships")
            graph = self._understand(study_id)
            coverage["dataset_graph"] = graph.model_dump(mode="json")
            # Hypothesis formulation must see the semantic compiler receipt.
            # Previously this was persisted only after the remote call, so the
            # model could not use inferred roles, units, split candidates, or
            # prohibited identifiers when framing the portfolio.
            self.repository.update_data_study(study_id, coverage=coverage)
            semantic_roles = dict(graph.semantics.get("role_counts") or {})
            self._event(
                job_id,
                "activity",
                "Understand",
                f"Bound {sum(int(value) for value in semantic_roles.values())} variables across "
                f"{len(graph.view_ids)} typed views and proposed {len(graph.alignments)} auditable "
                "cross-file relationships; unvalidated joins remain ineligible for evidence",
                study_id=study_id,
            )
            hypothesis_portfolio, portfolio_warning = self._propose_hypothesis_portfolio(
                study_id=study_id,
                request=request,
                budget=budget,
                cancellation=cancellation,
            )
            coverage["hypothesis_portfolio"] = hypothesis_portfolio
            self._event(
                job_id,
                "activity",
                "Understand",
                f"Grounded planning in {len(list(hypothesis_portfolio.get('considered_principle_ids') or []))} "
                f"Cloud records; framed {int(hypothesis_portfolio.get('count') or 0)} domain hypotheses "
                "and recorded their falsifiers",
                study_id=study_id,
            )
            if portfolio_warning:
                coverage["hypothesis_portfolio_warning"] = portfolio_warning
            blueprint_payload = self.repository.study_blueprint(study_id)
            if blueprint_payload is None:
                raise RuntimeError("scientific program compilation requires a persisted blueprint")
            blueprint = StudyBlueprint.model_validate(blueprint_payload)
            planned_hypotheses = self.repository.data_hypotheses(study_id)
            planning_principle_ids = list(
                dict.fromkeys(
                    [
                        *[
                            principle_id
                            for hypothesis in planned_hypotheses
                            for principle_id in hypothesis.principle_ids
                            if principle_id
                        ],
                        *[
                            str(principle_id)
                            for principle_id in list(
                                hypothesis_portfolio.get("considered_principle_ids") or []
                            )
                            if principle_id
                        ],
                    ]
                )
            )[:12]
            mechanism_program, predictive_program = compile_scientific_programs(
                study_id=study_id,
                blueprint=blueprint,
                # The first six domain-ranked records are the bounded knowledge
                # actually used to choose mechanism/law grammars.  The larger
                # retrieved set remains a considered-knowledge receipt only.
                principle_ids=planning_principle_ids[:6],
                hypothesis_ids=[item.hypothesis_id for item in planned_hypotheses],
                law_search_hints=list(hypothesis_portfolio.get("hypotheses") or []),
            )
            self.repository.save_scientific_program(mechanism_program)
            self.repository.save_scientific_program(predictive_program)
            coverage["scientific_programs"] = [
                {
                    "program_id": item.program_id,
                    "track": item.track,
                    "state": item.state,
                    "hypothesis_count": len(item.hypothesis_ids),
                    "principle_count": len(item.principle_ids),
                }
                for item in (mechanism_program, predictive_program)
            ]
            self._event(
                job_id,
                "program_compiled",
                "Understand",
                "Compiled separate mechanism and predictive-closure programs against the frozen blueprint.",
                study_id=study_id,
                program_ids=[mechanism_program.program_id, predictive_program.program_id],
            )
            self.repository.update_data_study(study_id, coverage=coverage)
            self._check_control(study_id, cancellation)

            self._set_phase(study_id, "analyze", 0.34, "Executing scientific programs")
            assets_and_roots = [
                (asset, root)
                for source_id, inventory in inventories
                if (root := self.repository.source_root(source_id)) is not None
                for asset in inventory.assets
            ]
            scientific_bundle = execute_cross_domain_program(
                study_id=study_id,
                program=predictive_program,
                blueprint=blueprint,
                assets_and_roots=assets_and_roots,
                views=[view for _, inventory in inventories for view in inventory.views],
                artifact_root=self._artifact_root(study_id),
                budget=str(request.get("budget") or "balanced"),
                check_control=lambda: self._check_deadline(study_id, cancellation, started + budget.wall_seconds),
                emit=lambda event_type, message, payload: self._event(
                    job_id,
                    event_type,
                    "Analyze",
                    message,
                    study_id=study_id,
                    **payload,
                ),
            )
            self._persist_scientific_program_bundle(scientific_bundle)
            coverage["expression_search"] = list(scientific_bundle.search_receipts)
            scientific_outcomes = list(scientific_bundle.outcomes)
            primary_generated_warning = ""
            primary_generated_receipt: dict[str, Any] = {"state": "not_applicable"}
            provider_id = str(request.get("provider") or "")
            if scientific_outcomes and provider_id and bool(request.get("egress_confirmed")):
                api_key = self.credentials.api_key(provider_id)
                if api_key:
                    from ..providers import ProviderProfile

                    profile = ProviderProfile.siliconflow()
                    exact_model = str(request.get("reasoning_model") or "auto")
                    if exact_model == "auto":
                        exact_model = profile.default_model
                    base_url = self.credentials.base_url(provider_id) or profile.base_url
                    primary_provider = OpenAICompatibleProvider(
                        ModelPolicy(
                            mode="remote",
                            provider=provider_id,
                            model=exact_model,
                            base_url=base_url,
                            remote_egress_confirmed=True,
                        ),
                        api_key=api_key,
                        timeout=min(720, max(120, budget.wall_seconds // 4)),
                        thinking_budget=8_192,
                    )
                    try:
                        generated_findings, primary_generated_receipt, primary_generated_warning = (
                            self._run_generated_challenge(
                                study_id=study_id,
                                provider=primary_provider,
                                findings=[item.finding for item in scientific_outcomes],
                                outcomes=scientific_outcomes,
                                phase_id="analyze",
                            )
                        )
                        generated_by_id = {
                            item.finding_id: item for item in generated_findings
                        }
                        scientific_outcomes = [
                            replace(
                                item,
                                finding=generated_by_id.get(
                                    item.finding.finding_id, item.finding
                                ),
                            )
                            for item in scientific_outcomes
                        ]
                    finally:
                        primary_provider.close()
                else:
                    primary_generated_receipt = {
                        "state": "credential_unavailable",
                        "model": str(request.get("reasoning_model") or "auto"),
                    }
                    primary_generated_warning = (
                        "Primary generated scientific programming was unavailable because the provider credential could not be loaded."
                    )
            elif scientific_outcomes:
                primary_generated_receipt = {"state": "egress_not_authorized"}
            coverage["generated_python_primary"] = primary_generated_receipt
            if primary_generated_warning:
                coverage.setdefault("analysis_limitations", []).append(
                    primary_generated_warning
                )
            coverage["scientific_program_execution"] = {
                "program_count": len(scientific_bundle.programs),
                "engine_version": RULE_ENGINE_VERSION,
                "law_family_count": len(scientific_bundle.laws),
                "calibration_count": len(scientific_bundle.calibrations),
                "candidate_count": len(scientific_bundle.candidates),
                "evaluation_count": len(scientific_bundle.evaluations),
                "promoted_rule_count": sum(
                    item.evidence_tier != "candidate" for item in scientific_bundle.laws
                ),
            }
            self._set_phase(study_id, "analyze", 0.42, "Executing complementary analyses")
            deterministic_outcomes, limitations = self._analyze(
                study_id,
                job_id,
                inventories,
                budget,
                cancellation,
                started,
                hypothesis_portfolio,
                skip_collection=True,
            )
            supplemental_law_bundle = outcomes_to_law_bundle(
                study_id=study_id,
                program=(
                    scientific_bundle.programs[0]
                    if scientific_bundle.programs
                    else predictive_program
                ),
                outcomes=deterministic_outcomes,
                emit=lambda event_type, message, payload: self._event(
                    job_id,
                    event_type,
                    "Analyze",
                    message,
                    study_id=study_id,
                    **payload,
                ),
            )
            self._persist_scientific_program_bundle(supplemental_law_bundle)
            execution_receipt = dict(coverage["scientific_program_execution"])
            execution_receipt["law_family_count"] += len(supplemental_law_bundle.laws)
            execution_receipt["calibration_count"] += len(supplemental_law_bundle.calibrations)
            execution_receipt["candidate_count"] += len(supplemental_law_bundle.candidates)
            execution_receipt["evaluation_count"] += len(supplemental_law_bundle.evaluations)
            execution_receipt["promoted_rule_count"] += sum(
                item.evidence_tier != "candidate"
                for item in supplemental_law_bundle.laws
            )
            coverage["scientific_program_execution"] = execution_receipt
            outcomes = [*scientific_outcomes, *deterministic_outcomes]
            limitations = [*scientific_bundle.limitations, *limitations]
            if primary_generated_warning:
                limitations.append(primary_generated_warning)
            mechanism_program = mechanism_program.model_copy(
                update={
                    "state": "completed" if deterministic_outcomes else "partial",
                    "decisions": [
                        *mechanism_program.decisions,
                        (
                            f"Executed {len(deterministic_outcomes)} complementary mechanism/structure tests."
                            if deterministic_outcomes
                            else "No mechanism test could be bound without weakening the scientific contract."
                        ),
                    ],
                    "updated_at": utc_now(),
                }
            )
            self.repository.save_scientific_program(mechanism_program)
            self._check_control(study_id, cancellation)
            self._event(
                job_id,
                "activity",
                "Analyze",
                f"Completed {len(outcomes)} executable scientific tests; {len(limitations)} limitations remain explicit",
                study_id=study_id,
            )

            self._set_phase(study_id, "challenge", 0.72, "Challenging candidate patterns")
            findings, screened_findings = self._challenge(outcomes)
            self._event(
                job_id,
                "activity",
                "Challenge",
                f"Stress-tested {len(outcomes)} results; {len(findings)} distinct candidates survived correction, stability, and duplication gates",
                study_id=study_id,
            )
            self._check_control(study_id, cancellation)

            self._set_phase(study_id, "synthesize", 0.86, "Connecting findings to Principles")
            pre_synthesis_findings = list(findings)
            findings, synthesis_warnings, resolved_models = self._run_with_heartbeat(
                study_id=study_id,
                cancellation=cancellation,
                base_progress=0.86,
                stage="Synthesize",
                message="Connecting findings to Principles with the reasoning model",
                call=lambda: self._synthesize(
                    study_id=study_id,
                    request=request,
                    findings=findings,
                    outcomes=outcomes,
                    coverage=coverage,
                    cancellation=cancellation,
                ),
            )
            # A remote request cannot always be interrupted mid-response. Honor
            # a cancellation received during that request before committing its
            # synthesis, while retaining already persisted tests and evidence.
            self._check_control(study_id, cancellation)
            limitations.extend(synthesis_warnings)
            retained_ids = {item.finding_id for item in findings}
            reasoning_holdback_reasons = {
                str(item.get("finding_id") or ""): str(item.get("reason") or "")
                for item in list(coverage.get("reasoning_holdbacks") or [])
                if isinstance(item, dict)
            }
            for candidate in pre_synthesis_findings:
                if candidate.finding_id in retained_ids:
                    continue
                reason = reasoning_holdback_reasons.get(candidate.finding_id) or (
                    "The reasoning review did not retain this candidate after scientific-validity "
                    "and distinctness checks."
                )
                screened_findings.append(
                    self._finalize_insight_contract(
                        candidate.model_copy(
                            update={
                                "status": "held_back",
                                "negative_evidence": _casefold_unique(
                                    [*candidate.negative_evidence, reason], limit=20
                                ),
                                "updated_at": utc_now(),
                            }
                        )
                    )
                )
            self._event(
                job_id,
                "activity",
                "Synthesize",
                f"Completed mechanism and Principle review for {len(findings)} surviving findings",
                study_id=study_id,
            )
            all_findings = [*findings, *screened_findings]
            for finding in all_findings:
                self.repository.save_data_finding(finding)
            # Only supported candidates may seed explanatory links or the graph.
            # Screened records remain inspectable evidence, never graph claims.
            self.repository.replace_data_principle_links(study_id, findings)
            linked_records = self.linked_principles(study_id)
            graph_principles = [
                *list(linked_records.get("principles") or []),
                *list(linked_records.get("foundations") or []),
            ]
            extra_principles = self.repository.data_extra_principles(study_id)
            coverage["graph_seed"] = self.repository.seed_data_discovery_graph(
                str(study.get("session_id") or ""),
                findings,
                graph_principles,
                extra_principles,
                used_principle_ids=list(
                    linked_records.get("used_principle_ids") or []
                ),
            )
            workspace_projection = self.workspace_records(study_id)
            self.repository.replace_workspace_projection(
                session_id=str(study.get("session_id") or ""),
                run_id=study_id,
                records=list(workspace_projection.get("records") or []),
                edges=list(workspace_projection.get("edges") or []),
            )
            coverage["workspace_record_counts"] = dict(
                workspace_projection.get("counts") or {}
            )
            generated_record = dict(coverage.get("generated_python") or {})
            generated_count = (
                len(list(generated_record.get("target_finding_ids") or []))
                if generated_record.get("state") == "scientifically_valid"
                else 0
            )
            coverage["executed_test_count"] = len(outcomes) + generated_count
            coverage["deterministic_test_count"] = len(outcomes)
            coverage["generated_test_count"] = generated_count
            represented_test_ids = {
                test_id for item in findings for test_id in item.test_ids
            }
            coverage["screened_test_count"] = sum(
                outcome.result.test_id not in represented_test_ids for outcome in outcomes
            )
            coverage["screened_finding_count"] = len(screened_findings)
            coverage["total_finding_count"] = len(all_findings)
            coverage["surviving_finding_count"] = len(findings)
            coverage["insight_distribution"] = {
                level: sum(item.insight_level == level for item in findings)
                for level in INSIGHT_LEVELS
            }
            rule_records = self.rules(study_id)
            tested_rule_candidates = self.rule_candidates(study_id)
            coverage["rule_count"] = len(rule_records)
            coverage["heldout_rule_count"] = sum(
                str(item.get("evidence_tier") or "")
                in {
                    "internal_locked_validation",
                    "stress_stable",
                    "prospectively_sealed",
                    "externally_replicated",
                }
                for item in rule_records
            )
            coverage["validated_rule_count"] = sum(
                item.get("validation_status") == "validated" for item in rule_records
            )
            scientific_program_execution = dict(
                coverage.get("scientific_program_execution") or {}
            )
            executed_equation_count = len(rule_records) + len(
                tested_rule_candidates
            )
            scientific_program_execution["executed_equation_candidate_count"] = (
                executed_equation_count
            )
            scientific_program_execution["candidate_count"] = max(
                int(scientific_program_execution.get("candidate_count") or 0),
                executed_equation_count,
            )
            coverage["scientific_program_execution"] = scientific_program_execution
            coverage["finding_quality_gate"] = {
                "requires_supported_candidate": True,
                "generic_image_record_order_findings_allowed": False,
                "insight_depth_is_separate_from_validation": True,
                "principle_level_requires_structure_and_replication_or_holdout": True,
                "synthesis_cannot_remove_deterministic_quantitative_specificity": True,
                "null_and_held_back_results_retained_in_findings_and_tests": True,
                "finding_quota_enforced": False,
            }
            coverage["resolved_models"] = resolved_models
            coverage["analysis_limitations"] = limitations
            degraded: list[dict[str, str]] = []
            portfolio_state = str(
                dict(coverage.get("hypothesis_portfolio") or {}).get("state") or ""
            )
            if portfolio_state and portfolio_state != "ready":
                degraded.append(
                    {
                        "capability": "domain hypothesis framing",
                        "state": portfolio_state,
                        "impact": "Deterministic analyses continued, but model-guided prioritization was reduced.",
                    }
                )
            generated_state = str(dict(coverage.get("generated_python") or {}).get("state") or "")
            if generated_state and generated_state not in {"scientifically_valid", "not_needed"}:
                degraded.append(
                    {
                        "capability": "generated-code challenge",
                        "state": generated_state,
                        "impact": "No generated computation strengthened a finding.",
                    }
                )
            if resolved_models.get("vision_model") in {None, ""}:
                degraded.append(
                    {
                        "capability": "visual interpretation",
                        "state": "unavailable",
                        "impact": "Quantitative analysis continued without remote visual interpretation.",
                    }
                )
            coverage["degraded_capabilities"] = degraded
            state: Literal["succeeded", "partial"] = "succeeded"
            if not outcomes or limitations:
                state = "partial"
            report = DataDiscoveryReport(
                study_id=study_id,
                state=state,
                source_digest=source_digest,
                coverage=coverage,
                findings=all_findings,
                negative_results=[
                    item
                    for outcome in outcomes
                    for item in outcome.result.negative_evidence
                ],
                unresolved_questions=[
                    "Independent experimental units and source-specific design remain to be confirmed."
                ],
                provenance={
                    "schema_version": "principia.data-discovery-report/v1",
                    "source_ids": list(study["source_ids"]),
                    "source_digest": source_digest,
                    "derived_only": True,
                    "raw_data_exported": False,
                },
            )
            self._check_control(study_id, cancellation)
            with self._lock:
                check_cancelled()
                self._write_report(study_id, report, outcomes)
                self.repository.update_data_study(
                    study_id,
                    state=state,
                    phase="synthesize",
                    coverage=coverage,
                    report=report.model_dump(mode="json"),
                )
                self.repository.update_data_session_state(
                    str(study.get("session_id") or ""), state
                )
                job = self.repository.get_job(job_id)
                if job:
                    self.repository.save_job(
                        job.model_copy(
                            update={
                                "state": "succeeded",
                                "stage": "Synthesize",
                                "progress": 1.0,
                                "completed_units": len(outcomes),
                                "elapsed_seconds": round(time.monotonic() - started, 2),
                                "result": {
                                    "study_id": study_id,
                                    "finding_count": len(findings),
                                    "report_artifact": "report.json",
                                },
                                "last_activity_at": utc_now(),
                                "status_message": (
                                    "Discovery completed with explicit limitations"
                                    if state == "partial"
                                    else "Discovery completed"
                                ),
                                "updated_at": utc_now(),
                            }
                        )
                    )
                self._event(job_id, "completed", "Synthesize", "Discovery completed", study_id=study_id)
        except _Cancelled:
            self.repository.update_data_study(study_id, state="cancelled")
            self.repository.update_data_session_state(
                str(study.get("session_id") or ""), "cancelled"
            )
            job = self.repository.get_job(job_id)
            if job:
                self.repository.save_job(
                    job.model_copy(
                        update={
                            "state": "cancelled",
                            "elapsed_seconds": round(time.monotonic() - started, 2),
                            "last_activity_at": utc_now(),
                            "status_message": "Discovery cancelled; completed evidence was preserved",
                            "updated_at": utc_now(),
                        }
                    )
                )
            self._event(job_id, "cancelled", "Stopped", "Discovery cancelled", study_id=study_id)
        except Exception as exc:
            self.repository.update_data_study(
                study_id,
                state="failed",
                report={"error": type(exc).__name__, "message": "Scientific execution stopped safely; completed evidence is preserved."},
            )
            self.repository.update_data_session_state(
                str(study.get("session_id") or ""), "failed"
            )
            job = self.repository.get_job(job_id)
            if job:
                self.repository.save_job(
                    job.model_copy(
                        update={
                            "state": "failed",
                            "error": {"type": type(exc).__name__, "message": "Scientific execution stopped safely; completed evidence is preserved."},
                            "elapsed_seconds": round(time.monotonic() - started, 2),
                            "last_activity_at": utc_now(),
                            "status_message": "Discovery stopped safely",
                            "updated_at": utc_now(),
                        }
                    )
                )
            self._event(job_id, "failed", "Stopped", "Discovery stopped safely", study_id=study_id)
        finally:
            with self._lock:
                self._futures.pop(study_id, None)
                self._cancel.pop(study_id, None)
                self._pause.pop(study_id, None)

    def _inventory_sources(
        self, study_id: str, source_ids: list[str], cancellation: threading.Event
    ) -> list[tuple[str, InventoryResult]]:
        results: list[tuple[str, InventoryResult]] = []
        for index, source_id in enumerate(source_ids):
            self._check_control(study_id, cancellation)
            root = self.repository.source_root(source_id)
            if root is None:
                raise KeyError(f"unknown Local source: {source_id}")
            inventory = self.inventory_adapter.inventory(
                root=root, source_id=source_id, study_id=study_id
            )
            for asset in inventory.assets:
                self.repository.save_data_asset(asset)
            for view in inventory.views:
                self.repository.save_data_view(view)
            results.append((source_id, inventory))
            self.repository.update_data_study(study_id, coverage=self._combined_coverage(results))
            study = self.repository.data_study(study_id)
            if study:
                self._update_job(
                    str(study["job_id"]),
                    progress=0.04 + 0.14 * ((index + 1) / len(source_ids)),
                    status=f"Inventoried {index + 1} of {len(source_ids)} sources",
                )
                self._event(
                    str(study["job_id"]),
                    "activity",
                    "Inventory",
                    f"Source {index + 1}/{len(source_ids)}: {len(inventory.assets)} files, {len(inventory.views)} typed views, {inventory.coverage.get('total_bytes', 0):,} bytes hashed read-only",
                    study_id=study_id,
                    source_id=source_id,
                )
        return results

    def _understand(self, study_id: str) -> DatasetGraph:
        views = self.repository.data_views(study_id)
        semantics = compile_dataset_semantics(views)
        alignments: list[DatasetAlignment] = []
        aligned_pairs: set[tuple[str, str]] = set()
        # Prefer explicit shared schema keys over filename resemblance.  The
        # relationship remains unvalidated until value-level cardinality and
        # orphan checks run in a collection operator.
        for index, source in enumerate(views):
            source_variables = {
                name.casefold(): name for name in [*source.keys, *source.variables]
            }
            for target in views[index + 1 :]:
                if len(alignments) >= 100:
                    break
                target_variables = {
                    name.casefold(): name for name in [*target.keys, *target.variables]
                }
                common = sorted(set(source_variables) & set(target_variables))
                shared_keys = [
                    source_variables[name]
                    for name in common
                    if classify_variable(source_variables[name])["role"]
                    in {"identifier", "independent_unit_identifier", "time_coordinate"}
                ][:8]
                if not shared_keys:
                    continue
                pair = tuple(sorted((source.view_id, target.view_id)))
                alignment = DatasetAlignment(
                    alignment_id="align:"
                    + canonical_sha256(
                        {
                            "study": study_id,
                            "source": source.view_id,
                            "target": target.view_id,
                            "keys": shared_keys,
                        }
                    )[:24],
                    study_id=study_id,
                    source_view_id=source.view_id,
                    target_view_id=target.view_id,
                    relation="shared_identifier",
                    source_keys=shared_keys,
                    target_keys=[target_variables[name.casefold()] for name in shared_keys],
                    confidence=0.68,
                    rationale=(
                        "Exact shared schema key; candidate join only. Cardinality, orphan rate, "
                        "value agreement, and unit compatibility must pass before scientific use."
                    ),
                )
                self.repository.save_data_alignment(alignment)
                alignments.append(alignment)
                aligned_pairs.add(pair)
        by_stem: dict[str, list[Any]] = {}
        for view in views:
            stem = Path(view.name).stem.casefold()
            for suffix in ("_matrix", "_barcodes", "_features", "_metadata", "-matrix"):
                stem = stem.replace(suffix, "")
            by_stem.setdefault(stem[:120], []).append(view)
        for stem, related in sorted(by_stem.items()):
            if not stem or len(related) < 2:
                continue
            anchor = related[0]
            for target in related[1:10]:
                pair = tuple(sorted((anchor.view_id, target.view_id)))
                if pair in aligned_pairs:
                    continue
                alignment = DatasetAlignment(
                    alignment_id="align:"
                    + canonical_sha256(
                        {"study": study_id, "source": anchor.view_id, "target": target.view_id}
                    )[:24],
                    study_id=study_id,
                    source_view_id=anchor.view_id,
                    target_view_id=target.view_id,
                    relation="series_member",
                    confidence=0.55,
                    rationale="Deterministic normalized filename-family match; value-level join not assumed.",
                )
                self.repository.save_data_alignment(alignment)
                alignments.append(alignment)
                aligned_pairs.add(pair)
        independent_candidates = list(semantics.get("independent_unit_candidates") or [])
        split_strategy = str(semantics.get("recommended_split_strategy") or "none")
        if split_strategy not in {
            "group", "chronological", "spatial_block", "contiguous_epoch", "none"
        }:
            split_strategy = "none"
        asset_page = self.repository.data_assets(study_id=study_id, limit=500)
        asset_profiles: list[dict[str, Any]] = []
        for payload in list(asset_page.get("items") or []):
            metadata_payload = dict(payload.get("metadata") or {})
            profile = metadata_payload.get("profile")
            asset_profiles.append(
                {
                    "asset_id": str(payload.get("asset_id") or ""),
                    "profile": profile if isinstance(profile, dict) else {},
                }
            )
        blueprint = compile_study_blueprint(
            study_id=study_id,
            views=views,
            alignments=alignments,
            asset_profiles=asset_profiles,
        )
        self.repository.save_study_blueprint(blueprint.model_dump(mode="json"))
        semantics["study_blueprint"] = blueprint.model_dump(mode="json")
        return DatasetGraph(
            study_id=study_id,
            view_ids=[item.view_id for item in views],
            alignments=alignments,
            independent_unit=(
                str(independent_candidates[0].get("variable") or "")
                if independent_candidates
                else "unknown until source-specific design validation"
            ),
            split_strategy=split_strategy,  # type: ignore[arg-type]
            semantics=semantics,
            warnings=[
                "Schema and filename relationships are candidate alignments and never evidence by themselves.",
                "Every cross-file analysis must validate join cardinality, orphan rate, and unit compatibility.",
                *blueprint.warnings,
            ],
        )

    def _persist_scientific_program_bundle(
        self, bundle: ScientificProgramBundle
    ) -> None:
        """Persist one immutable program frontier in referential order."""

        with self.repository.atomic():
            self._write_scientific_program_bundle(bundle)

    def _write_scientific_program_bundle(self, bundle: ScientificProgramBundle) -> None:

        for program in bundle.programs:
            self.repository.save_scientific_program(program)
        for manifest in bundle.split_manifests:
            self.repository.save_split_manifest(manifest)
        for graph in bundle.transform_graphs:
            self.repository.save_transform_graph(graph)
        for law in bundle.laws:
            self.repository.save_scientific_law_family(law)
        for calibration in bundle.calibrations:
            self.repository.save_scientific_law_calibration(calibration)
        for candidate in bundle.candidates:
            self.repository.save_scientific_law_candidate(candidate)
        for evaluation in bundle.evaluations:
            self.repository.save_scientific_law_evaluation(evaluation)
        for decision in bundle.decisions:
            self.repository.save_scientific_decision(decision)
        for outcome in bundle.outcomes:
            self.repository.save_data_hypothesis(outcome.hypothesis)
            test_payload = outcome.result.model_dump(mode="json")
            test_payload["finding_id"] = outcome.finding.finding_id
            test_payload["analysis_plan"] = outcome.plan.model_dump(mode="json")
            self.repository.save_data_test(test_payload)
            self.repository.save_computed_evidence(outcome.evidence)
            for evidence in outcome.additional_evidence:
                self.repository.save_computed_evidence(evidence)

    def _analyze(
        self,
        study_id: str,
        job_id: str,
        inventories: list[tuple[str, InventoryResult]],
        budget: DiscoveryBudget,
        cancellation: threading.Event,
        started: float,
        hypothesis_portfolio: dict[str, Any],
        *,
        skip_collection: bool = False,
    ) -> tuple[list[OperatorOutcome], list[str]]:
        prioritized: list[tuple[str, Any]] = []
        preferred_formats = {
            "csv", "tsv", "delimited", "delimited_text", "delimited_gzip",
            "matrix_market_gzip", "fits", "hdf5", "nwb", "root", "edf",
            "dicom", "netcdf", "xlsx", "ras", "zip", "json", "geojson",
        }
        proposed_asset_order: dict[str, int] = {}
        for proposal in list(hypothesis_portfolio.get("hypotheses") or []):
            for asset_id in list(proposal.get("asset_ids") or []):
                proposed_asset_order.setdefault(str(asset_id), len(proposed_asset_order))
        # Round one gives every selected source a fair opportunity to execute a test.
        remaining: list[tuple[str, Any]] = []
        for source_id, inventory in inventories:
            eligible = [
                item
                for item in inventory.assets
                if item.status == "analyzable"
                and item.role == "raw"
                and bool(item.metadata.get("evidence_eligible", True))
                and item.format in preferred_formats
            ]
            eligible = self._balanced_asset_order(eligible, proposed_asset_order)
            if eligible:
                prioritized.append((source_id, eligible[0]))
            remaining.extend((source_id, item) for item in eligible[1:])
        prioritized.extend(remaining)
        outcomes: list[OperatorOutcome] = []
        limitations: list[str] = []
        ordinal = 0
        # Collection-level operators run before isolated file screens. They are
        # the only deterministic layer allowed to claim relationships spanning
        # matched files or modalities; filename alignment alone is never used as
        # evidence.
        for source_id, inventory in ([] if skip_collection else inventories):
            self._check_control(study_id, cancellation)
            if time.monotonic() - started > budget.wall_seconds:
                limitations.append(
                    "Wall-time budget reached before all collection-level analyses could run."
                )
                break
            root = self.repository.source_root(source_id)
            collection, collection_limits = analyze_collection(
                study_id=study_id,
                assets=[
                    item
                    for item in inventory.assets
                    if item.status == "analyzable"
                    and item.role == "raw"
                    and bool(item.metadata.get("evidence_eligible", True))
                ],
                root=root or Path("."),
                blueprint=self.repository.study_blueprint(study_id),
            )
            limitations.extend(collection_limits)
            for outcome in collection:
                if len(outcomes) >= budget.analysis_units:
                    break
                unit = {
                    "unit_id": "data-unit:"
                    + canonical_sha256(
                        {
                            "study": study_id,
                            "operator": outcome.plan.operator,
                            "plan": outcome.plan.plan_digest,
                        }
                    )[:24],
                    "study_id": study_id,
                    "job_id": job_id,
                    "unit_kind": "collection_analysis",
                    "ordinal": ordinal,
                    "state": "succeeded",
                    "attempt_count": 1,
                    "input_digest": canonical_sha256(
                        sorted(item.byte_sha256 for item in inventory.assets)
                    ),
                    "asset_id": outcome.evidence.asset_id,
                    "result": {
                        "test_id": outcome.result.test_id,
                        "finding_id": outcome.finding.finding_id,
                        "result_digest": outcome.result.result_digest,
                    },
                }
                ordinal += 1
                self.repository.save_data_hypothesis(outcome.hypothesis)
                test_payload = outcome.result.model_dump(mode="json")
                test_payload["finding_id"] = outcome.finding.finding_id
                test_payload["analysis_plan"] = outcome.plan.model_dump(mode="json")
                self.repository.save_data_test(test_payload)
                self.repository.save_computed_evidence(outcome.evidence)
                for evidence in outcome.additional_evidence:
                    self.repository.save_computed_evidence(evidence)
                self.repository.save_data_job_unit(unit)
                outcomes.append(outcome)
                self._event(
                    job_id,
                    "analysis_result",
                    "Analyze",
                    f"Executed cross-file test: {outcome.plan.operator}",
                    study_id=study_id,
                    test_id=outcome.result.test_id,
                    disposition=outcome.finding.status,
                )

        remaining_budget = max(0, budget.analysis_units - len(outcomes))
        for source_id, asset in prioritized[:remaining_budget]:
            self._check_control(study_id, cancellation)
            if time.monotonic() - started > budget.wall_seconds:
                limitations.append("Wall-time budget reached; remaining assets retain inventory-only coverage.")
                break
            unit = {
                "unit_id": "data-unit:"
                + canonical_sha256({"study": study_id, "asset": asset.asset_id})[:24],
                "study_id": study_id,
                "job_id": job_id,
                "unit_kind": "analysis",
                "ordinal": ordinal,
                "state": "running",
                "attempt_count": 1,
                "input_digest": asset.byte_sha256,
                "asset_id": asset.asset_id,
            }
            # Ordinals identify attempts, not only successful scientific tests.
            # Advance before execution so metadata-only/failed projections cannot
            # collide with the following durable unit.
            ordinal += 1
            self.repository.save_data_job_unit(unit)
            root = self.repository.source_root(source_id)
            try:
                outcome = analyze_asset(study_id=study_id, asset=asset, root=root or Path("."))
            except Exception as exc:
                unit.update(
                    state="failed",
                    error={"type": type(exc).__name__, "message": str(exc)[:300]},
                )
                limitations.append(
                    f"{asset.portable_uri}: analysis limitation ({type(exc).__name__})."
                )
                self.repository.save_data_job_unit(unit)
                continue
            if outcome is None:
                unit.update(state="succeeded", result={"status": "no_valid_numeric_projection"})
                self.repository.save_data_job_unit(unit)
                limitations.append(f"{asset.portable_uri}: no valid bounded numeric projection.")
                continue
            self.repository.save_data_hypothesis(outcome.hypothesis)
            test_payload = outcome.result.model_dump(mode="json")
            test_payload["finding_id"] = outcome.finding.finding_id
            test_payload["analysis_plan"] = outcome.plan.model_dump(mode="json")
            self.repository.save_data_test(test_payload)
            self.repository.save_computed_evidence(outcome.evidence)
            for evidence in outcome.additional_evidence:
                self.repository.save_computed_evidence(evidence)
            outcomes.append(outcome)
            unit.update(
                state="succeeded",
                result={
                    "test_id": outcome.result.test_id,
                    "finding_id": outcome.finding.finding_id,
                    "result_digest": outcome.result.result_digest,
                },
            )
            self.repository.save_data_job_unit(unit)
            self._event(
                job_id,
                "analysis_result",
                "Analyze",
                f"Executed bounded test {ordinal}: {outcome.plan.operator}",
                study_id=study_id,
                test_id=outcome.result.test_id,
                disposition=outcome.finding.status,
            )
            self._update_job(
                job_id,
                progress=min(0.70, 0.36 + 0.34 * (ordinal / max(1, len(prioritized)))),
                status=f"Attempted {ordinal} bounded analyses",
                completed=len(outcomes),
                total=min(len(prioritized) + len(outcomes), budget.analysis_units),
            )
        return outcomes, limitations

    @staticmethod
    def _balanced_asset_order(
        assets: list[Any], proposed_asset_order: dict[str, int]
    ) -> list[Any]:
        """Keep model guidance from becoming unrecorded outcome selection.

        Three deterministic, size-bounded assets are scheduled for every one asset
        prioritized by the hypothesis portfolio. This preserves a reproducible
        coverage backbone while still giving domain hypotheses bounded influence.
        """

        baseline = sorted(assets, key=lambda item: (item.byte_size, item.asset_id))
        proposed = sorted(
            (item for item in assets if item.asset_id in proposed_asset_order),
            key=lambda item: (
                proposed_asset_order[item.asset_id],
                item.byte_size,
                item.asset_id,
            ),
        )
        ordered: list[Any] = []
        seen: set[str] = set()
        baseline_index = 0
        proposed_index = 0
        while len(ordered) < len(baseline):
            admitted = 0
            while baseline_index < len(baseline) and admitted < 3:
                item = baseline[baseline_index]
                baseline_index += 1
                if item.asset_id in seen:
                    continue
                ordered.append(item)
                seen.add(item.asset_id)
                admitted += 1
            while proposed_index < len(proposed):
                item = proposed[proposed_index]
                proposed_index += 1
                if item.asset_id in seen:
                    continue
                ordered.append(item)
                seen.add(item.asset_id)
                break
            if admitted == 0 and proposed_index >= len(proposed):
                break
        return ordered

    @staticmethod
    def _planning_principle_queries(
        *, context: dict[str, Any], objective: str
    ) -> list[str]:
        """Compile short, domain-bearing Cloud queries from the frozen blueprint.

        Retrieval is local and deterministic.  It deliberately happens before
        provider availability is checked so a missing remote model cannot make
        scientific planning knowledge-blind.  Context excerpts contribute only
        vocabulary; they never become evidence for a finding.
        """

        blueprint = dict(context.get("study_blueprint") or {})
        domain_terms: list[str] = []
        for candidate in list(blueprint.get("domain_candidates") or [])[:4]:
            if not isinstance(candidate, dict):
                continue
            domain_terms.extend(str(item) for item in list(candidate.get("signals") or []))
            domain = str(candidate.get("domain") or "").replace("_", " ").replace("-", " ")
            if domain:
                domain_terms.append(domain)
        context_text = " ".join(
            str(item.get("text") or "")
            for item in list(blueprint.get("context_excerpts") or [])[:8]
            if isinstance(item, dict)
        )[:8_000]
        seed = " ".join(
            (
                objective[:1_000],
                str(context.get("scientific_focus") or "")[:1_000],
                str(blueprint.get("interpretation_summary") or "")[:1_000],
                " ".join(domain_terms),
                context_text,
            )
        )
        tokens = _literature_tokens(seed)
        expansions = [
            expansion
            for triggers, expansion in _DOMAIN_QUERY_EXPANSIONS
            if tokens & triggers
        ]
        concise_domain = " ".join(
            _casefold_unique(
                [
                    item
                    for item in domain_terms
                    if item and item.casefold() not in _PRIOR_ART_STOPWORDS
                ],
                limit=10,
            )
        )
        candidates = [*expansions]
        if concise_domain:
            candidates.append(concise_domain)
        if objective.strip():
            candidates.append(objective[:500])
        if not candidates:
            candidates.append("scientific mechanism validation")
        return list(
            dict.fromkeys(" ".join(item.split()) for item in candidates if item.strip())
        )[:3]

    def _scoped_search(self, query: str, *, scope: str, source_ids: list[str], limit: int) -> dict[str, Any]:
        lanes: list[dict[str, Any]] = []
        if scope in {"global", "combined"}:
            lanes.append(self.search.search_with_plan(query, scope="global", limit=limit, intent="auto"))
        if scope in {"local", "combined"}:
            for source_id in sorted(set(source_ids)):
                lanes.append(self.search.search_with_plan(query, scope="local", source_id=source_id, limit=limit, intent="auto"))
        merged: dict[str, dict[str, dict[str, Any]]] = {"items": {}}
        for lane in lanes:
            for section, records in {"items": lane.get("items", []), **dict(lane.get("sections") or {})}.items():
                target = merged.setdefault(section, {})
                for record in records:
                    if isinstance(record, dict) and record.get("id"):
                        target[str(record["id"])] = record
        return {"items": list(merged.pop("items").values())[:limit], "sections": {key: list(value.values())[:limit] for key, value in merged.items()}}

    def _retrieve_planning_principles(
        self,
        *,
        context: dict[str, Any],
        request: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Retrieve a compact, typed knowledge portfolio before planning.

        Direct/domain Principles lead; method Principles and Meta-Principles
        remain visibly typed.  A result is considered knowledge at this stage,
        not evidence.  Only the bounded subset attached to an executable
        ScientificProgram becomes graph-visible study knowledge.
        """

        scope = str(request.get("knowledge_scope") or "combined")
        if scope not in {"global", "local", "combined"}:
            scope = "combined"
        queries = self._planning_principle_queries(
            context=context,
            objective=str(request.get("objective") or ""),
        )
        blueprint = dict(context.get("study_blueprint") or {})
        planning_context = " ".join(
            [
                str(request.get("objective") or ""),
                str(context.get("scientific_focus") or ""),
                str(blueprint.get("interpretation_summary") or ""),
                *queries,
                *[
                    str(item.get("text") or "")
                    for item in list(blueprint.get("context_excerpts") or [])[:8]
                    if isinstance(item, dict)
                ],
            ]
        )[:16_000]
        ordered_sections = (
            "direct_bridge",
            "domain_principles",
            "method_principles",
            "meta_foundations",
        )
        retained: list[dict[str, Any]] = []
        seen: set[str] = set()
        receipts: list[dict[str, Any]] = []
        for identifier in _foundation_ids_for_text(planning_context, limit=4):
            detail = self.search.principle(identifier)
            if detail is None:
                continue
            retained.append(
                {
                    **detail,
                    "match_section": "meta_foundations",
                    "match_path": "curated_domain_foundation",
                }
            )
            seen.add(identifier)
        for query in queries:
            try:
                payload = self._scoped_search(query, scope=scope, source_ids=list(request.get("source_ids") or []), limit=16)
            except Exception as exc:
                receipts.append(
                    {
                        "query": query,
                        "state": "failed",
                        "error": type(exc).__name__,
                    }
                )
                continue
            sections = dict(payload.get("sections") or {})
            candidates: list[dict[str, Any]] = []
            section_caps = {
                "direct_bridge": 4,
                "domain_principles": 3,
                "method_principles": 2,
                "meta_foundations": 2,
            }
            for section in ordered_sections:
                for raw in list(sections.get(section) or [])[: section_caps[section]]:
                    if isinstance(raw, dict):
                        candidates.append({**raw, "match_section": section})
            if not candidates:
                candidates = [
                    dict(item)
                    for item in list(payload.get("items") or [])
                    if isinstance(item, dict)
                ]
            rejected_irrelevant = 0
            for item in candidates:
                identifier = str(item.get("id") or item.get("principle_id") or "")
                if not identifier or identifier in seen:
                    continue
                entity = str(item.get("entity") or "principle")
                if entity not in {"principle", "meta_principle"}:
                    continue
                if not _planning_principle_relevant(planning_context, item):
                    rejected_irrelevant += 1
                    continue
                seen.add(identifier)
                retained.append(item)
            capabilities = dict(payload.get("capabilities") or {})
            receipts.append(
                {
                    "query": query,
                    "state": "ready",
                    "intent": dict(payload.get("query_plan") or {}).get("intent"),
                    "ranking_mode": capabilities.get("ranking_mode"),
                    "degraded": bool(capabilities.get("degraded")),
                    "section_counts": dict(payload.get("section_counts") or {}),
                    "rejected_by_relevance_gate": rejected_irrelevant,
                }
            )
        return retained[:12], {
            "schema_version": "principia.planning-knowledge/v1",
            "state": "ready" if retained else "empty",
            "queries": receipts,
            "considered_count": len(retained[:12]),
            "evidence_eligible": False,
        }

    def _propose_hypothesis_portfolio(
        self,
        *,
        study_id: str,
        request: dict[str, Any],
        budget: DiscoveryBudget,
        cancellation: threading.Event,
    ) -> tuple[dict[str, Any], str]:
        """Use the reasoning model before execution to frame falsifiable scientific work.

        These records are plans, never findings. Invalid asset references are discarded and
        every retained proposal is persisted with a proposed state until a real operator tests it.
        """

        context = self._bounded_study_context(study_id)
        principle_records, principle_receipt = self._retrieve_planning_principles(
            context=context,
            request=request,
        )
        principle_ids = [
            str(item.get("id") or item.get("principle_id") or "")
            for item in principle_records
            if item.get("id") or item.get("principle_id")
        ][:12]
        knowledge_payload = {
            "considered_principle_ids": principle_ids,
            "considered_principles": [
                {
                    "id": item.get("id") or item.get("principle_id"),
                    "title": item.get("title"),
                    "claim": item.get("claim"),
                    "principle_class": item.get("principle_class"),
                    "match_section": item.get("match_section"),
                    "match_path": item.get("match_path"),
                }
                for item in principle_records[:12]
            ],
            "knowledge_retrieval": principle_receipt,
        }
        provider_id = str(request.get("provider") or "")
        if not provider_id:
            return {
                "state": "not_authorized",
                "hypotheses": [],
                **knowledge_payload,
            }, ""
        api_key = self.credentials.api_key(provider_id)
        if not api_key:
            return {
                "state": "credential_unavailable",
                "hypotheses": [],
                **knowledge_payload,
            }, (
                "Hypothesis framing could not use the configured provider credential."
            )
        from ..providers import ProviderProfile

        profile = ProviderProfile.siliconflow()
        requested = str(request.get("reasoning_model") or "auto")
        reasoning_model = self._resolve_model(
            requested,
            profile.reasoning_models or profile.models,
            set(profile.reasoning_models or profile.models),
        )
        if not reasoning_model:
            return {
                "state": "model_unavailable",
                "hypotheses": [],
                **knowledge_payload,
            }, (
                "No compatible reasoning model was available for hypothesis framing."
            )
        asset_page = self.repository.data_assets(study_id=study_id, limit=500)
        allowed_assets = {
            str(item.get("asset_id"))
            for item in list(asset_page.get("items") or [])
            if item.get("asset_id") and item.get("role") == "raw"
        }
        if not allowed_assets:
            return {
                "state": "no_raw_assets",
                "hypotheses": [],
                **knowledge_payload,
            }, ""
        self._check_control(study_id, cancellation)
        generation = None
        last_error: Exception | None = None
        from ..providers.models import SILICONFLOW_AUTHORIZED_BASE_URLS

        remembered = self.credentials.base_url(provider_id)
        origins = list(
            dict.fromkeys(
                [
                    item
                    for item in (remembered, profile.base_url, *SILICONFLOW_AUTHORIZED_BASE_URLS)
                    if item
                ]
            )
        )
        # Resolve the credential region before submitting an expensive reasoning
        # request.  Some SiliconFlow credentials are valid on only one official
        # regional origin.  Replaying a timed-out generation against another
        # origin can both hide the real error and duplicate paid work.
        resolved_origin = ""
        for origin in origins:
            probe_policy = ModelPolicy(
                mode="remote",
                provider=provider_id,
                model=reasoning_model,
                base_url=origin,
                remote_egress_confirmed=True,
            )
            probe = OpenAICompatibleProvider(probe_policy, api_key=api_key, timeout=30)
            probe_started = time.monotonic()
            try:
                available = {str(item["id"]) for item in probe.available_models()}
                self._provider_receipt(
                    study_id=study_id,
                    phase="understand",
                    provider=provider_id,
                    model=reasoning_model,
                    endpoint_class="models_canary",
                    state="succeeded" if reasoning_model in available else "model_unavailable",
                    started=probe_started,
                    prompt_template="model-availability-canary-v1",
                    input_payload={"requested_model": reasoning_model},
                )
                if reasoning_model in available:
                    resolved_origin = origin
                    self.credentials.remember_base_url(provider_id, origin)
                    break
            except Exception as exc:
                self._provider_receipt(
                    study_id=study_id,
                    phase="understand",
                    provider=provider_id,
                    model=reasoning_model,
                    endpoint_class="models_canary",
                    state="failed",
                    started=probe_started,
                    prompt_template="model-availability-canary-v1",
                    input_payload={"requested_model": reasoning_model},
                    error=exc,
                )
                continue
            finally:
                probe.close()
        if not resolved_origin:
            return {
                "state": "provider_failed",
                "model": reasoning_model,
                "hypotheses": [],
                "error": "ModelEndpointUnavailable",
                "error_category": "provider_unavailable",
                "status_code": None,
                **knowledge_payload,
            }, "Domain hypothesis framing could not verify a compatible provider endpoint."
        budget_name = str(request.get("budget") or "balanced")
        reasoning_timeout = {"fast": 300, "balanced": 480, "deep": 720}[budget_name]
        with self._lock:
            check_cancelled()
            current_study = self.repository.data_study(study_id) or {}
            current_job = self.repository.get_job(str(current_study.get("job_id") or ""))
            if current_job:
                self.repository.save_job(current_job.model_copy(update={"model": reasoning_model, "updated_at": utc_now()}))
        hypothesis_input = {
            "objective": str(request.get("objective") or "")[:2_000],
            "budget_hypothesis_cap": budget.hypotheses,
            "study_context": context,
            "principles": [
                {"id": item.get("id"), "title": item.get("title"), "claim": item.get("claim")}
                for item in principle_records[:12]
            ],
        }
        for origin in [resolved_origin]:
            policy = ModelPolicy(
                mode="remote",
                provider=provider_id,
                model=reasoning_model,
                base_url=origin,
                remote_egress_confirmed=True,
            )
            provider = OpenAICompatibleProvider(
                policy,
                api_key=api_key,
                timeout=reasoning_timeout,
                thinking_budget=8_192,
            )
            generation_started = time.monotonic()
            try:
                generation = self._run_with_heartbeat(
                    study_id=study_id,
                    cancellation=cancellation,
                    base_progress=0.22,
                    stage="Understand",
                    message="Framing falsifiable domain hypotheses with the reasoning model",
                    call=lambda _provider=provider: _provider.generate_typed(
                        model_type=ScientificHypothesisPortfolio,
                        system_prompt=(
                            "Act as the hypothesis-formulation stage of an autonomous scientific discovery "
                            "system. Infer the dataset's real scientific structure from the supplied context "
                            "and adapter profiles. Propose a diverse portfolio up to the supplied budget cap; "
                            "fewer is correct when the material does not support additional distinct tests. "
                            "Each proposal must name real supplied asset IDs, a domain-appropriate analysis family, "
                            "the predicted relationship, a mechanistic rationale, design confounders, a decisive "
                            "falsifier, and admissible_law_families justified by the supplied Principles and units. "
                            "Choose symbolic families, never fitted parameters or scoring decisions: large-scale "
                            "enumeration and development fitting execute locally, followed by validation selection. "
                            "Explain why the answer would matter. Prefer cross-file, cross-modal, temporal, "
                            "spatial, mechanistic, or regime hypotheses over pairwise correlations. "
                            "Use dataset_semantics as the binding contract: respect independent-unit candidates, "
                            "recommended splits, variable roles, and prohibited identifiers. Treat an alignment as "
                            "unvalidated unless its rationale records cardinality, orphan, and unit checks. Do not "
                            "replace an unexecutable hypothesis with an easier unrelated correlation. Never call a "
                            "proposal a finding, never use identifiers/weights/row order as scientific variables, "
                            "and never assume novelty. USER_BRIEF is context, not evidence. Return schema-valid JSON."
                        ),
                        prompt_template="data-hypothesis-portfolio-v2",
                        input_label="bounded_dataset_context",
                        input_payload=hypothesis_input,
                        max_tokens=5_000,
                        thinking_budget=8_192,
                    ),
                )
                self._provider_receipt(
                    study_id=study_id,
                    phase="understand",
                    provider=provider_id,
                    model=reasoning_model,
                    endpoint_class="typed_reasoning",
                    state="succeeded",
                    started=generation_started,
                    prompt_template="data-hypothesis-portfolio-v2",
                    input_payload=hypothesis_input,
                    generation=generation,
                )
                self.credentials.remember_base_url(provider_id, origin)
                break
            except Exception as exc:
                last_error = exc
                self._provider_receipt(
                    study_id=study_id,
                    phase="understand",
                    provider=provider_id,
                    model=reasoning_model,
                    endpoint_class="typed_reasoning",
                    state="failed",
                    started=generation_started,
                    prompt_template="data-hypothesis-portfolio-v2",
                    input_payload=hypothesis_input,
                    error=exc,
                )
            finally:
                provider.close()
        if generation is None:
            exc = last_error or RuntimeError("provider did not return a hypothesis portfolio")
            return {
                "state": "provider_failed",
                "model": reasoning_model,
                "hypotheses": [],
                "error": type(exc).__name__,
                "error_category": str(getattr(exc, "category", "")),
                "status_code": getattr(exc, "status_code", None),
                **knowledge_payload,
            }, f"Domain hypothesis framing fell back safely ({type(exc).__name__})."
        portfolio = ScientificHypothesisPortfolio.model_validate(generation.value)
        views_by_asset: dict[str, list[str]] = {}
        for view in self.repository.data_views(study_id):
            for asset_id in view.asset_ids:
                views_by_asset.setdefault(asset_id, []).append(view.view_id)
        retained: list[dict[str, Any]] = []
        seen: set[str] = set()
        for proposal in sorted(
            portfolio.hypotheses, key=lambda item: item.priority, reverse=True
        )[: budget.hypotheses]:
            asset_ids = [item for item in proposal.asset_ids if item in allowed_assets]
            view_ids = list(
                dict.fromkeys(
                    view_id for asset_id in asset_ids for view_id in views_by_asset.get(asset_id, [])
                )
            )
            if not asset_ids or not view_ids:
                continue
            digest = canonical_sha256(
                {
                    "study": study_id,
                    "claim": proposal.claim,
                    "assets": asset_ids,
                    "analysis_family": proposal.analysis_family,
                }
            )
            if digest in seen:
                continue
            seen.add(digest)
            hypothesis = {
                **proposal.model_dump(mode="json"),
                "asset_ids": asset_ids,
                "hypothesis_id": f"hyp:{digest[:24]}",
            }
            retained.append(hypothesis)
            self.repository.save_data_hypothesis(
                DataHypothesis(
                    hypothesis_id=hypothesis["hypothesis_id"],
                    study_id=study_id,
                    claim=proposal.claim,
                    origin=(
                        "cross_modal"
                        if proposal.analysis_family == "cross_modal"
                        else "principle_guided"
                    ),
                    expected_relationship=proposal.expected_relationship,
                    input_view_ids=view_ids,
                    principle_ids=[
                        str(item.get("id"))
                        for item in principle_records[:5]
                        if item.get("id")
                    ],
                    confounders=proposal.confounders,
                    boundary=[portfolio.dataset_interpretation[:1_000]],
                    falsifier=proposal.falsifier,
                    state="proposed",
                )
            )
        return {
            "state": "ready",
            "model": reasoning_model,
            "domain": portfolio.domain,
            "dataset_interpretation": portfolio.dataset_interpretation,
            "key_design_risks": portfolio.key_design_risks,
            "hypotheses": retained,
            "count": len(retained),
            "trace": generation.trace.model_dump(mode="json"),
            **knowledge_payload,
        }, ""

    def _challenge(
        self, outcomes: list[OperatorOutcome]
    ) -> tuple[list[DataFinding], list[DataFinding]]:
        adjusted_by_test: dict[str, float | None] = {}
        family_by_test: dict[str, str] = {}
        grouped: dict[str, list[OperatorOutcome]] = {}
        for outcome in outcomes:
            grouped.setdefault(outcome.plan.operator, []).append(outcome)
        for family, members in grouped.items():
            raw_p = [
                item.result.uncertainty.get("p_value_uncorrected") for item in members
            ]
            adjusted = benjamini_hochberg(
                [float(value) if isinstance(value, (int, float)) else None for value in raw_p]
            )
            for outcome, corrected in zip(members, adjusted, strict=True):
                adjusted_by_test[outcome.result.test_id] = corrected
                family_by_test[outcome.result.test_id] = family
        survivors: list[DataFinding] = []
        screened: dict[str, DataFinding] = {}
        for outcome in outcomes:
            corrected = adjusted_by_test.get(outcome.result.test_id)
            result = outcome.result.model_copy(
                update={
                    "corrected_significance": {
                        "method": "benjamini-hochberg",
                        "family": family_by_test.get(
                            outcome.result.test_id, outcome.plan.operator
                        ),
                        "adjusted_p_value": corrected,
                    }
                }
            )
            payload = result.model_dump(mode="json")
            payload["finding_id"] = outcome.finding.finding_id
            payload["analysis_plan"] = outcome.plan.model_dump(mode="json")
            self.repository.save_data_test(payload)
            finding = outcome.finding
            if corrected is not None and corrected > 0.05 and finding.status == "supported_candidate":
                finding = finding.model_copy(
                    update={
                        "status": "held_back",
                        "negative_evidence": [
                            *finding.negative_evidence,
                            "Candidate did not survive within-family Benjamini-Hochberg correction at 0.05.",
                        ],
                        "updated_at": utc_now(),
                    }
                )
            if finding.status == "supported_candidate" and not result.uncertainty:
                finding = finding.model_copy(
                    update={
                        "status": "held_back",
                        "negative_evidence": _casefold_unique(
                            [
                                *finding.negative_evidence,
                                "Candidate has no executed uncertainty receipt; descriptive estimates remain inspectable but cannot be marked supported.",
                            ]
                        ),
                        "promotion_eligible": False,
                        "updated_at": utc_now(),
                    }
                )
            if finding.status == "supported_candidate":
                survivors.append(finding)
            else:
                screened[finding.finding_id] = self._finalize_insight_contract(finding)
        consolidated = self._consolidate_supported_findings(outcomes, survivors)
        consolidated = self._consolidate_light_curve_findings(outcomes, consolidated)
        consolidated = self._deduplicate_supported_findings(outcomes, consolidated)
        represented_test_ids = {
            test_id for finding in consolidated for test_id in finding.test_ids
        }
        for outcome in outcomes:
            if outcome.result.test_id in represented_test_ids:
                continue
            if outcome.finding.finding_id in screened:
                continue
            screened[outcome.finding.finding_id] = self._finalize_insight_contract(
                outcome.finding.model_copy(
                    update={
                        "status": "held_back",
                        "negative_evidence": _casefold_unique(
                            [
                                *outcome.finding.negative_evidence,
                                "Candidate did not survive correction, stability, distinctness, or collection-level consolidation gates.",
                            ],
                            limit=20,
                        ),
                        "updated_at": utc_now(),
                    }
                )
            )
        return consolidated, list(screened.values())

    def _consolidate_light_curve_findings(
        self,
        outcomes: list[OperatorOutcome],
        survivors: list[DataFinding],
    ) -> list[DataFinding]:
        """Promote an ensemble validation result, never repeated target templates."""

        light_curves = [
            item for item in outcomes if item.plan.operator == "light_curve_periodicity"
        ]
        if len(light_curves) < 6:
            return survivors
        individual_ids = {item.finding.finding_id for item in light_curves}
        retained = [item for item in survivors if item.finding_id not in individual_ids]
        fap_pass = [
            item
            for item in light_curves
            if isinstance(item.result.uncertainty.get("false_alarm_probability"), (int, float))
            and float(item.result.uncertainty["false_alarm_probability"]) <= 1e-4
        ]
        stable = [
            item
            for item in light_curves
            if bool(item.result.estimate.get("contiguous_half_harmonic_stable"))
        ]
        stable_ids = {
            str(item.result.estimate.get("target", {}).get("tic_id") or "unknown")
            for item in stable
        }
        unstable_despite_fap = [
            item
            for item in fap_pass
            if not bool(item.result.estimate.get("contiguous_half_harmonic_stable"))
        ]
        if len(stable) < 2 or len(unstable_despite_fap) < 2:
            return retained
        study_id = light_curves[0].finding.study_id
        digest = canonical_sha256(
            {
                "study": study_id,
                "operator": "tess_period_coherence_screen",
                "tests": sorted(item.result.test_id for item in light_curves),
                "stable": sorted(stable_ids),
            }
        )
        finding_id = f"finding:{digest[:24]}"
        evidence_ids: list[str] = []
        for outcome in light_curves:
            evidence_id = "evidence:" + canonical_sha256(
                {"aggregate": finding_id, "source_evidence": outcome.evidence.evidence_id}
            )[:24]
            evidence_ids.append(evidence_id)
            self.repository.save_computed_evidence(
                outcome.evidence.model_copy(
                    update={"evidence_id": evidence_id, "finding_id": finding_id}
                )
            )
        now = utc_now()
        retained.append(
            DataFinding(
                finding_id=finding_id,
                study_id=study_id,
                title="Contiguous-time coherence rejects most nominally significant TESS periods",
                claim=(
                    f"Only {len(stable)}/{len(light_curves)} sector light curves retained a harmonically "
                    f"consistent period in both contiguous halves, while {len(unstable_despite_fap)} "
                    f"of {len(fap_pass)} candidates passing the 10⁻⁴ periodogram false-alarm threshold "
                    "failed that coherence test. The stable subset was "
                    + ", ".join(f"TIC {value}" for value in sorted(stable_ids))
                    + "."
                ),
                interpretation=(
                    "In this outcome-blind sector sample, formal peak significance and catalog-period agreement "
                    "are not sufficient evidence for a persistent stellar clock. Time-local reproducibility is the "
                    "dominant discriminator between publishable periodic candidates and alias/evolution-prone observations."
                ),
                mechanism=(
                    "A full-sector Lomb–Scargle peak integrates repeated structure even when its frequency drifts or "
                    "appears in only part of the baseline. Window aliases, evolving starspots, contamination, and residual "
                    "instrumental systematics can therefore yield extreme false-alarm probabilities without contiguous coherence."
                ),
                significance=(
                    "The result defines a concrete reliability principle for short-baseline survey mining: candidate ranking "
                    "must be gated by time-local coherence, not peak significance alone, before astrophysical interpretation."
                ),
                principle_chain=[
                    "Periodogram significance quantifies a peak under a noise model.",
                    "A persistent physical oscillator must reproduce across contiguous observation windows.",
                    "Failure of window-level coherence falsifies persistence even when the global peak is extreme.",
                ],
                status="supported_candidate",
                validation_level="exploratory",
                hypothesis_ids=sorted(
                    {item.hypothesis.hypothesis_id for item in light_curves}
                ),
                test_ids=sorted({item.result.test_id for item in light_curves}),
                evidence_ids=evidence_ids,
                robustness=[
                    "outcome-blind TIC sampling",
                    "uniform Lomb–Scargle search contract",
                    "factor-of-two harmonic tolerance",
                    "two contiguous time-window checks per target",
                    "all retained targets reported, including failures",
                ],
                confounders=[
                    "single-sector observation window",
                    "target-dependent magnitude and crowding",
                    "linear detrending choice",
                    "spot evolution versus stable rotation",
                    "instrumental aliases",
                ],
                falsifiers=[
                    "The rejected targets recover the same coherent period under predeclared alternate detrending and in independent TESS sectors."
                ],
                negative_evidence=[
                    f"{len(light_curves) - len(stable)} of {len(light_curves)} targets failed contiguous-half coherence."
                ],
                limits=[
                    "Eight targets are sufficient to expose the validation failure mode but not to estimate its population prevalence.",
                    "Coherence does not by itself prove stellar rotation rather than another stable source of variability.",
                ],
                next_validation=(
                    "Repeat the predeclared screen in independent sectors, compare detrending families, and test whether "
                    "coherence predicts follow-up recovery better than false-alarm probability alone."
                ),
                created_at=now,
                updated_at=now,
            )
        )
        return retained

    @staticmethod
    def _deduplicate_supported_findings(
        outcomes: list[OperatorOutcome], findings: list[DataFinding]
    ) -> list[DataFinding]:
        """Keep the strongest representative when file-level titles are identical."""

        outcome_by_finding = {item.finding.finding_id: item for item in outcomes}

        def score(finding: DataFinding) -> tuple[float, float, str]:
            outcome = outcome_by_finding.get(finding.finding_id)
            if outcome is None:
                return (math.inf, math.inf, finding.finding_id)
            estimate = outcome.result.estimate
            primary = float(
                estimate.get("r_squared")
                or estimate.get("variance_explained")
                or estimate.get("spectral_concentration")
                or estimate.get("adjacency_correlation")
                or 0.0
            )
            secondary = abs(float(estimate.get("correlation") or 0.0))
            return (primary, secondary, finding.finding_id)

        grouped: dict[str, list[DataFinding]] = {}
        order: list[str] = []
        for finding in findings:
            key = " ".join(finding.title.casefold().split())
            if key not in grouped:
                grouped[key] = []
                order.append(key)
            grouped[key].append(finding)
        return [max(grouped[key], key=score) for key in order]

    def _consolidate_supported_findings(
        self,
        outcomes: list[OperatorOutcome],
        survivors: list[DataFinding],
    ) -> list[DataFinding]:
        """Replace repetitive file-level signatures with cross-asset evidence.

        A resolved peak in one scan is useful executed evidence, but it is not a
        dataset-level discovery. Multiple diffraction scans are surfaced only when
        they support stable, separated regimes across deterministic file splits.
        """

        diffraction = [
            item
            for item in outcomes
            if item.plan.operator == "diffraction_peak_profile"
            and item.finding.status == "supported_candidate"
        ]
        if not diffraction:
            return survivors
        retained = [
            item
            for item in survivors
            if item.finding_id not in {outcome.finding.finding_id for outcome in diffraction}
        ]
        if len(diffraction) < 6:
            return retained

        def fit_two(values: list[float]) -> tuple[list[float], list[int]] | None:
            centers = [min(values), max(values)]
            labels: list[int] = []
            for _ in range(20):
                labels = [
                    0 if abs(value - centers[0]) <= abs(value - centers[1]) else 1
                    for value in values
                ]
                if min(labels.count(0), labels.count(1)) < 2:
                    return None
                updated = [
                    sum(value for value, label in zip(values, labels, strict=True) if label == index)
                    / labels.count(index)
                    for index in (0, 1)
                ]
                if max(abs(updated[index] - centers[index]) for index in (0, 1)) < 1e-9:
                    centers = updated
                    break
                centers = updated
            order = sorted(range(2), key=centers.__getitem__)
            remap = {old: new for new, old in enumerate(order)}
            return [centers[index] for index in order], [remap[label] for label in labels]

        angles = [float(item.result.estimate["peak_angle"]) for item in diffraction]
        fitted = fit_two(angles)
        if fitted is None:
            return retained
        centers, labels = fitted
        cluster_sizes = [labels.count(0), labels.count(1)]
        if min(cluster_sizes) < 3:
            return retained
        absolute_deviations = [
            abs(value - centers[label])
            for value, label in zip(angles, labels, strict=True)
        ]
        sorted_deviations = sorted(absolute_deviations)
        within_median = sorted_deviations[len(sorted_deviations) // 2]
        separation = centers[1] - centers[0]
        separation_ratio = separation / max(0.004, within_median)
        if separation < 0.03 or separation_ratio < 4.0:
            return retained
        split_centers: list[list[float]] = []
        for start in (0, 1):
            split_fit = fit_two(angles[start::2])
            if split_fit is None:
                return retained
            split_centers.append(split_fit[0])
        stable = all(
            abs(split[index] - centers[index]) <= 0.06
            for split in split_centers
            for index in (0, 1)
        )
        if not stable:
            return retained

        study_id = diffraction[0].finding.study_id
        aggregate_digest = canonical_sha256(
            {
                "study": study_id,
                "operator": "cross_asset_diffraction_regimes",
                "tests": sorted(item.result.test_id for item in diffraction),
                "centers": centers,
                "sizes": cluster_sizes,
            }
        )
        finding_id = f"finding:{aggregate_digest[:24]}"
        aggregate_evidence_ids: list[str] = []
        for outcome in diffraction:
            evidence_id = "evidence:" + canonical_sha256(
                {"aggregate": finding_id, "source_evidence": outcome.evidence.evidence_id}
            )[:24]
            aggregate_evidence_ids.append(evidence_id)
            self.repository.save_computed_evidence(
                outcome.evidence.model_copy(
                    update={"evidence_id": evidence_id, "finding_id": finding_id}
                )
            )
        now = utc_now()
        retained.append(
            DataFinding(
                finding_id=finding_id,
                study_id=study_id,
                title="Two reproducible X-ray reflectivity peak-angle regimes across wafer scans",
                claim=(
                    f"Across {len(angles)} resolved scans, peak angles separated into regimes centered "
                    f"at {centers[0]:.4f}° (n={cluster_sizes[0]}) and {centers[1]:.4f}° "
                    f"(n={cluster_sizes[1]}); both centers reproduced within 0.06° in alternating-file splits."
                ),
                interpretation=(
                    "The collection contains cross-scan structural regimes rather than a list of unrelated single-scan peaks."
                ),
                mechanism=(
                    "Under X-ray reflectivity physics, systematic changes in critical-angle or fringe structure can arise from "
                    "distinct electron-density, thickness, roughness, or process states. The present peak-only analysis does not identify which state changed."
                ),
                status="supported_candidate",
                validation_level="exploratory",
                hypothesis_ids=sorted({item.hypothesis.hypothesis_id for item in diffraction}),
                test_ids=sorted({item.result.test_id for item in diffraction}),
                evidence_ids=aggregate_evidence_ids,
                robustness=[
                    "resolved-peak threshold in every retained scan",
                    "two-regime one-dimensional clustering",
                    "minimum three scans per regime",
                    "alternating-file center stability",
                ],
                confounders=[
                    "scan geometry and instrument calibration",
                    "background and footprint effects",
                    "wafer-position and process-condition imbalance",
                    "file-order structure in the deterministic split",
                ],
                falsifiers=[
                    "The two regimes collapse after full reflectivity-model fitting, calibration correction, or process-balanced replication."
                ],
                negative_evidence=[],
                limits=[
                    "Peak angle alone cannot distinguish thickness, density, roughness, phase, and instrumental mechanisms.",
                    "Fewer than 50 defensibly independent units forces an exploratory validation label.",
                ],
                next_validation=(
                    "Fit the full reflectivity curves with a shared instrument model, map fitted parameters to wafer coordinates and process metadata, "
                    "and reproduce the regimes in an independently deposited wafer."
                ),
                created_at=now,
                updated_at=now,
            )
        )
        return retained

    def _synthesize(
        self,
        *,
        study_id: str,
        request: dict[str, Any],
        findings: list[DataFinding],
        outcomes: list[OperatorOutcome],
        coverage: dict[str, Any],
        cancellation: threading.Event,
    ) -> tuple[list[DataFinding], list[str], dict[str, str]]:
        objective = str(request.get("objective") or "")
        scope = str(request.get("knowledge_scope") or "combined")
        if scope not in {"global", "local", "combined"}:
            scope = "combined"
        study_context = self._bounded_study_context(study_id)
        principle_records: list[dict[str, Any]] = []
        principle_candidates: dict[str, list[str]] = {}
        query = objective or str(study_context.get("scientific_focus") or "")
        if not query:
            query = findings[0].title if findings else "scientific data mechanism"
        seen_principles: set[str] = set()
        finding_by_id = {item.finding_id: item for item in findings}
        search_requests = [("study", query[:500])]
        search_requests.extend(
            (item.finding_id, focused_query)
            for item in findings[:8]
            for focused_query in _principle_search_queries(item)
        )
        for owner, search_query in search_requests:
            try:
                records = list(
                    self._scoped_search(search_query, scope=scope, source_ids=list(request.get("source_ids") or []), limit=10).get("items")
                    or []
                )
            except Exception:
                records = []
            owned: list[str] = []
            for record in records:
                principle_id = str(record.get("id") or "")
                if not principle_id:
                    continue
                if owner == "study":
                    relevant = any(
                        _principle_relevant_to_finding(item, record)
                        for item in findings
                    )
                else:
                    relevant = owner in finding_by_id and _principle_relevant_to_finding(
                        finding_by_id[owner], record
                    )
                if not relevant:
                    continue
                owned.append(principle_id)
                if principle_id not in seen_principles:
                    seen_principles.add(principle_id)
                    principle_records.append(record)
            if owner != "study":
                principle_candidates[owner] = list(
                    dict.fromkeys([*principle_candidates.get(owner, []), *owned])
                )[:4]
            if len(principle_records) >= 18:
                break
        # Full-text search is strongest for Literature Principles. Supplement
        # it with a small, audited set of canonical domain foundations already
        # present in the Global Cloud; never create or infer new records here.
        for finding in findings[:8]:
            owned = list(principle_candidates.get(finding.finding_id, []))
            anchored: list[str] = []
            for principle_id in _foundation_ids_for_finding(finding):
                detail = self.search.principle(principle_id)
                if detail is None or not _principle_relevant_to_finding(
                    finding, detail
                ):
                    continue
                anchored.append(principle_id)
                if principle_id not in seen_principles:
                    seen_principles.add(principle_id)
                    principle_records.append({**detail, "id": principle_id})
            principle_candidates[finding.finding_id] = [
                *anchored,
                *(identifier for identifier in owned if identifier not in anchored),
            ][:4]
        principle_ids = [str(item.get("id") or "") for item in principle_records if item.get("id")]
        linked = [
            self._finalize_insight_contract(
                item.model_copy(
                    update={
                        "principle_ids": principle_candidates.get(item.finding_id, [])[:3],
                        "updated_at": utc_now(),
                    }
                )
            )
            for item in findings
        ]
        provider_id = str(request.get("provider") or "")
        if not provider_id:
            return linked, ["Remote synthesis was not authorized; deterministic synthesis used."], {}
        api_key = self.credentials.api_key(provider_id)
        if not api_key:
            return linked, ["Configured provider credential was unavailable; deterministic synthesis used."], {}
        budget = BUDGETS[str(request.get("budget") or "balanced")]  # type: ignore[index]
        linked, prior_art_receipts, prior_art_warning = self._review_prior_art(
            findings=linked,
            objective=objective,
            maximum=budget.prior_art_results,
        )
        coverage["prior_art_receipts"] = prior_art_receipts
        self._check_control(study_id, cancellation)
        requested_reasoning = str(request.get("reasoning_model") or "auto")
        requested_vision = str(request.get("vision_model") or "auto")
        from ..providers import ProviderProfile
        from ..providers.models import SILICONFLOW_AUTHORIZED_BASE_URLS

        profile = ProviderProfile.siliconflow()
        origins = [profile.base_url]
        if profile.base_url in SILICONFLOW_AUTHORIZED_BASE_URLS:
            origins.extend(
                item for item in SILICONFLOW_AUTHORIZED_BASE_URLS if item != profile.base_url
            )
        available: set[str] = set()
        resolved_base_url = profile.base_url
        for origin in origins:
            probe_policy = ModelPolicy(
                mode="remote",
                provider=provider_id,
                model=profile.default_model,
                base_url=origin,
                remote_egress_confirmed=True,
            )
            probe = OpenAICompatibleProvider(probe_policy, api_key=api_key, timeout=30)
            try:
                available = {str(item["id"]) for item in probe.available_models()}
                resolved_base_url = origin
                self.credentials.remember_base_url(provider_id, origin)
                break
            except Exception:
                continue
            finally:
                probe.close()
        if not available:
            available = set(profile.models + profile.vision_models)
        discovery_policy = ModelPolicy(
            mode="remote",
            provider=provider_id,
            model=profile.default_model,
            base_url=resolved_base_url,
            remote_egress_confirmed=True,
        )
        reasoning = self._resolve_model(
            requested_reasoning, profile.reasoning_models or profile.models, available
        )
        vision_preferences = list(dict.fromkeys([profile.default_vision_model, *profile.vision_models]))
        vision = self._resolve_model(requested_vision, vision_preferences, available, optional=True)
        coverage["resolved_models"] = {"reasoning_model": reasoning, "vision_model": vision}
        self.repository.update_data_study(study_id, coverage=coverage)
        if not reasoning:
            return linked, ["No compatible reasoning model was available; deterministic synthesis used."], {"vision_model": vision}
        policy = discovery_policy.model_copy(update={"model": reasoning})
        budget_name = str(request.get("budget") or "balanced")
        reasoning_timeout = {"fast": 300, "balanced": 480, "deep": 720}[budget_name]
        provider = OpenAICompatibleProvider(
            policy,
            api_key=api_key,
            timeout=reasoning_timeout,
            thinking_budget=8_192,
        )
        synthesis_warnings: list[str] = []
        if requested_vision not in {"", "auto"} and not vision:
            synthesis_warnings.append(
                f"The selected vision model {requested_vision} was not available from this provider; "
                "visual interpretation was skipped. Select another vision model in Sources & model."
            )
        if prior_art_warning:
            synthesis_warnings.append(prior_art_warning)
        try:
            visual_observations, visual_receipts, visual_warning = self._run_visual_interpretation(
                study_id=study_id,
                provider_id=provider_id,
                base_url=resolved_base_url,
                api_key=api_key,
                vision_model=vision,
                budget=budget,
            )
            coverage["vision_receipts"] = visual_receipts
            if visual_warning:
                synthesis_warnings.append(visual_warning)
            primary_receipt = dict(coverage.get("generated_python_primary") or {})
            if primary_receipt.get("state") not in {
                "",
                "not_applicable",
                "egress_not_authorized",
                "credential_unavailable",
            }:
                generated_receipt = primary_receipt
                generated_warning = ""
            else:
                linked, generated_receipt, generated_warning = self._run_generated_challenge(
                    study_id=study_id,
                    provider=provider,
                    findings=linked,
                    outcomes=outcomes,
                )
            coverage["generated_python"] = generated_receipt
            if generated_warning:
                synthesis_warnings.append(generated_warning)
            outcome_by_finding = {
                item.finding.finding_id: item for item in outcomes
            }
            compact_findings: list[dict[str, Any]] = []
            for item in linked[:10]:
                outcome = outcome_by_finding.get(item.finding_id)
                estimate = dict(outcome.result.estimate) if outcome is not None else {}
                estimate.pop("summaries", None)
                compact_findings.append(
                    {
                        "finding_id": item.finding_id,
                        "title": item.title,
                        "claim": item.claim,
                        "current_interpretation": item.interpretation,
                        "current_mechanism": item.mechanism,
                        "current_significance": item.significance,
                        "current_insight_level": item.insight_level,
                        "current_nontriviality_basis": item.nontriviality_basis,
                        "current_surprising_result": item.surprising_result,
                        "current_practical_value": item.practical_value,
                        "current_principle_statement": item.principle_statement,
                        "current_transfer_scope": item.transfer_scope,
                        "current_principle_chain": item.principle_chain,
                        "status": item.status,
                        "validation_level": item.validation_level,
                        "operator": outcome.plan.operator if outcome is not None else "",
                        "sample_definition": (
                            outcome.result.sample_definition if outcome is not None else ""
                        ),
                        "estimate": estimate,
                        "uncertainty": (
                            outcome.result.uncertainty if outcome is not None else {}
                        ),
                        "sensitivities": (
                            outcome.result.sensitivities[:6] if outcome is not None else []
                        ),
                        "robustness": item.robustness,
                        "confounders": item.confounders,
                        "falsifiers": item.falsifiers,
                        "negative_evidence": item.negative_evidence,
                        "limits": item.limits,
                    }
                )
            compact_principles = [
                {
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "claim": item.get("claim"),
                    "assessment": item.get("assessment"),
                }
                for item in principle_records[:12]
            ]
            literature_sources: dict[str, dict[str, Any]] = {}
            for finding in linked:
                for source in finding.prior_art:
                    key = str(
                        source.get("work_id")
                        or source.get("doi")
                        or source.get("url")
                        or ""
                    )
                    if key and key not in literature_sources:
                        literature_sources[key] = {
                            "source_key": key,
                            "title": str(source.get("title") or "")[:500],
                            "year": source.get("year"),
                            "doi": str(source.get("doi") or ""),
                            "url": str(source.get("url") or ""),
                            "publication_status": str(
                                source.get("publication_status") or ""
                            ),
                        }
            synthesis_input = {
                "objective": objective[:2_000],
                "study_context": study_context,
                "coverage": {
                    "asset_count": coverage.get("asset_count"),
                    "modality_counts": coverage.get("modality_counts"),
                },
                "findings": compact_findings,
                "principles": compact_principles,
                "literature_sources": list(literature_sources.values())[:40],
                "visual_observations": visual_observations,
            }
            synthesis_started = time.monotonic()
            generation = provider.generate_typed(
                model_type=DiscoverySynthesis,
                system_prompt=(
                    "Act as a rigorous scientific co-investigator, not a copy editor or template engine. Interpret only "
                    "the supplied supported candidates and their executed results. For every returned "
                    "item, write an evidence-specific title and claim, then explain the domain-level implication, "
                    "a concrete multi-step principle chain, "
                    "and an accessible interpretation in 90-150 words: explain what the measured pattern "
                    "means in this dataset, why the tested contrast supports that reading, what remains "
                    "ambiguous, and what observation would separate the main competing explanations. "
                    "Use familiar quantity names and unpack specialist terms. Do not repeat the claim or "
                    "recite coefficients; keep only the few numbers needed for the inference. Explain "
                    "mechanisms as hypotheses unless the executed design discriminates them. Never turn "
                    "internal consistency into proof of measurement accuracy, absence of artifacts, "
                    "clinical validity, or safe intervention. Practical implications must be conditional "
                    "on the recorded scope and confounders; do not assert untested improvements. "
                    "why the result could matter, the strongest alternative explanation, and the decisive "
                    "next falsification test. A generic restatement of a correlation or a claim that "
                    "'relevant principles may exist' is invalid. Reusing sentence frames, swapping only an "
                    "identifier/number, generic phrases such as 'the data suggest a relationship', and parallel "
                    "fill-in-the-blank titles are invalid. Every retained item must articulate a distinct scientific "
                    "principle, boundary condition, regime change, mechanism, or falsification result; a per-file "
                    "observation is not sufficient. Preserve all numerical qualifiers and exploratory labels. "
                    "Classify each item by scientific role, independently of validation certainty: observational "
                    "means an unexpected, calibrated pattern that is already decision-relevant; structural means "
                    "a regime, boundary, interaction, invariance, decoupling, or cross-modal organization; "
                    "mechanistic means the evidence discriminates a concrete causal architecture while remaining "
                    "explicitly non-causal when the design is observational; principle_level means a transferable "
                    "rule with a stated scope, boundary conditions, and falsifier, supported by multiple executed "
                    "tests or an internal holdout. Never inflate depth to satisfy a quota. For every retained item, "
                    "supply a compact nontriviality_basis, surprising_result, practical_value, transfer_scope, and "
                    "a principle_statement when principle_level. Each must name the actual variables, conditions, "
                    "effect direction, or validation contrast; generic benefits and rhetorical surprise are invalid. "
                    "Keep each of those fields to one information-dense sentence (45 words maximum), and keep the "
                    "principle statement to 50 words. Do not repeat the claim in those fields. "
                    "You may recommend hold_back only when the "
                    "supplied diagnostics, sensitivities, visual evidence, or a concrete scientific validity "
                    "failure contradicts the candidate; give the exact reason. This is a one-way safety gate: "
                    "you can demote a candidate but can never promote one. Never invent measurements, "
                    "treat identifiers or row order as science, claim causality, or label anything novel. "
                    "Link only supplied Principle IDs and distinguish source-derived metadata from independent "
                    "replication. If and only if the supplied established Principles leave a concrete explanatory "
                    "gap, set principle_gap_detected and propose a small number of Extra Principles. An Extra "
                    "Principle is provisional research synthesis, not an established or data-derived Principle; it "
                    "must cite one or more supplied literature source_keys, state boundary conditions and falsifiers, "
                    "and identify the related finding IDs. Do not create one merely to fill a quota. "
                    "A cited source must address the same scientific domain and mechanism; a shared word such as "
                    "uniformity, thickness, aperture, regime, or coherence is not evidence of relevance. If no supplied "
                    "source actually supports the proposed explanatory principle, do not propose it. Return concise "
                    "JSON matching the schema, including a distinct significance and principle_chain for every "
                    "retained finding."
                ),
                prompt_template="data-discovery-synthesis-v5-grounded-interpretation",
                input_label="computed_findings_and_principles",
                input_payload=synthesis_input,
                max_tokens=7_000,
                thinking_budget=8_192,
            )
            self._provider_receipt(
                study_id=study_id,
                phase="synthesize",
                provider=provider_id,
                model=reasoning,
                endpoint_class="typed_reasoning",
                state="succeeded",
                started=synthesis_started,
                prompt_template="data-discovery-synthesis-v5-grounded-interpretation",
                input_payload=synthesis_input,
                generation=generation,
            )
        except Exception as exc:
            self._provider_receipt(
                study_id=study_id,
                phase="synthesize",
                provider=provider_id,
                model=reasoning,
                endpoint_class="typed_reasoning",
                state="failed",
                started=locals().get("synthesis_started", time.monotonic()),
                prompt_template="data-discovery-synthesis-v5-grounded-interpretation",
                input_payload=locals().get("synthesis_input", {}),
                error=exc,
            )
            return linked, [*synthesis_warnings, f"Reasoning synthesis fell back safely ({type(exc).__name__})."], {"reasoning_model": reasoning, "vision_model": vision}
        finally:
            provider.close()
        synthesis = DiscoverySynthesis.model_validate(generation.value)
        interpretations = {
            item.finding_id: item for item in synthesis.interpretations
        }
        output, reasoning_holdbacks = self._apply_reasoning_interpretations(
            findings=linked,
            interpretations=interpretations,
            allowed_principles=set(principle_ids),
        )
        coverage["reasoning_holdbacks"] = reasoning_holdbacks
        extra_principles = self._materialize_extra_principles(
            study_id=study_id,
            synthesis=synthesis,
            literature_sources=literature_sources,
            findings=output,
        )
        coverage["principle_gap"] = {
            "detected": bool(synthesis.principle_gap_detected),
            "reason": synthesis.principle_gap_reason[:2_000],
        }
        coverage["extra_principles"] = [
            item.model_dump(mode="json") for item in extra_principles
        ]
        for principle in extra_principles:
            self.repository.save_data_extra_principle(principle)
        return output, synthesis_warnings, {"reasoning_model": reasoning, "vision_model": vision}

    @staticmethod
    def _materialize_extra_principles(
        *,
        study_id: str,
        synthesis: DiscoverySynthesis,
        literature_sources: dict[str, dict[str, Any]],
        findings: list[DataFinding],
    ) -> list[DataExtraPrinciple]:
        if not synthesis.principle_gap_detected:
            return []
        findings_by_id = {item.finding_id: item for item in findings}
        output: list[DataExtraPrinciple] = []
        seen: set[str] = set()
        for proposal in synthesis.extra_principles:
            proposal_context = " ".join(
                (
                    proposal.title,
                    proposal.claim,
                    proposal.explanatory_gap,
                    proposal.mechanism,
                )
            )
            keys = [
                key
                for key in _casefold_unique(proposal.supporting_source_keys, limit=20)
                if key in literature_sources
                and _source_title_relevant_to_context(
                    proposal_context, literature_sources[key]
                )
            ]
            related = [
                identifier
                for identifier in _casefold_unique(proposal.related_finding_ids, limit=20)
                if identifier in findings_by_id
            ]
            # Literature-grounded and finding-linked are hard requirements;
            # unsupported model synthesis is not retained as a scientific record.
            if not keys or not related:
                continue
            if any(
                _extra_principle_duplicates_finding(
                    proposal.claim,
                    findings_by_id[identifier],
                )
                for identifier in related
            ):
                # Extra Principles must close an explanatory gap, not duplicate
                # a result that already has a permanent Discovery Finding kind.
                continue
            digest = canonical_sha256(
                {
                    "study": study_id,
                    "claim": " ".join(proposal.claim.casefold().split()),
                    "sources": sorted(keys),
                    "findings": sorted(related),
                }
            )
            if digest in seen:
                continue
            seen.add(digest)
            output.append(
                DataExtraPrinciple(
                    extra_principle_id=f"extra-principle:{digest[:24]}",
                    study_id=study_id,
                    title=proposal.title,
                    claim=proposal.claim,
                    explanatory_gap=proposal.explanatory_gap,
                    mechanism=proposal.mechanism,
                    boundary_conditions=_casefold_unique(
                        proposal.boundary_conditions, limit=20
                    ),
                    falsifiers=_casefold_unique(proposal.falsifiers, limit=20),
                    supporting_sources=[literature_sources[key] for key in keys],
                    related_finding_ids=related,
                )
            )
        return output[:6]

    @staticmethod
    def _insight_depth_cap(finding: DataFinding) -> str:
        """Return the deepest scientific role justified by the audited record.

        This is deliberately independent of novelty and confidence.  It prevents a
        fluent synthesis model from turning a single observation into a Principle.
        """

        if finding.status != "supported_candidate":
            return "observational"
        combined = " ".join(
            (
                finding.title,
                finding.claim,
                finding.interpretation,
                finding.mechanism,
                finding.significance,
                finding.principle_statement,
            )
        ).casefold()
        structural = any(
            marker in combined
            for marker in (
                "boundary",
                "coherence",
                "decoupl",
                "gradient",
                "interaction",
                "invariant",
                "negative control",
                "nonlinear",
                "regime",
                "residual",
                "reversal",
                "threshold",
                "tradeoff",
            )
        )
        mechanism_is_concrete = (
            len(finding.mechanism.split()) >= 22
            and "no mechanism" not in combined
            and "relevant existing principles" not in combined
            and bool(finding.falsifiers)
        )
        replicated_or_held_out = (
            len(finding.test_ids) >= 2
            or finding.validation_level != "exploratory"
        )
        principle_ready = (
            structural
            and replicated_or_held_out
            and len(finding.robustness) >= 3
            and bool(finding.falsifiers)
            and (len(finding.principle_chain) >= 3 or bool(finding.significance))
        )
        if principle_ready:
            return "principle_level"
        if mechanism_is_concrete and len(finding.principle_chain) >= 2:
            return "mechanistic"
        if structural or len(finding.robustness) >= 3:
            return "structural"
        return "observational"

    @staticmethod
    def _promotion_gate(finding: DataFinding) -> tuple[bool, list[str]]:
        """Return auditable blockers for Data-derived Principle drafting."""

        blockers: list[str] = []
        if finding.status != "supported_candidate":
            blockers.append("the result is not a supported candidate")
        if finding.insight_level not in {"mechanistic", "principle_level"}:
            blockers.append("the scientific role has not reached mechanistic depth")
        if finding.validation_level == "exploratory":
            blockers.append("an independent holdout or cross-modal replication is required")
        if not finding.evidence_ids:
            blockers.append("no computed evidence anchor is linked")
        if len(finding.robustness) < 3:
            blockers.append("fewer than three robustness checks are recorded")
        if not finding.falsifiers:
            blockers.append("no explicit falsifier is recorded")
        if not finding.transfer_scope.strip():
            blockers.append("the transfer scope is not defined")
        if finding.novelty_status == "not_assessed":
            blockers.append("current prior art has not been assessed")
        high_risk_text = " ".join(
            [*finding.confounders, *finding.limits]
        ).casefold()
        high_risk_terms = {
            "confounded": "a declared design confounder remains unresolved",
            "pseudoreplication": "pseudoreplication remains unresolved",
            "unit conflict": "a unit conflict remains unresolved",
            "unit inconsistency": "a unit inconsistency remains unresolved",
            "single patient": "only one patient is available",
            "one patient": "only one patient is available",
            "single participant": "only one participant is available",
            "one participant": "only one participant is available",
            "no independent": "independent validation remains unavailable",
        }
        for term, message in high_risk_terms.items():
            if term in high_risk_text:
                blockers.append(message)
        return not blockers, blockers

    @staticmethod
    def _finalize_insight_contract(
        finding: DataFinding, *, requested_level: str | None = None
    ) -> DataFinding:
        cap = DataDiscoveryService._insight_depth_cap(finding)
        has_explicit_contract = any(
            (
                finding.nontriviality_basis.strip(),
                finding.surprising_result.strip(),
                finding.practical_value.strip(),
                finding.principle_statement.strip(),
                finding.transfer_scope.strip(),
            )
        )
        requested = (
            requested_level
            if requested_level in INSIGHT_LEVELS
            else finding.insight_level
            if has_explicit_contract
            else cap
        )
        level = INSIGHT_LEVELS[
            min(INSIGHT_LEVELS.index(requested), INSIGHT_LEVELS.index(cap))
        ]
        nontriviality = finding.nontriviality_basis.strip() or finding.significance.strip()
        if not nontriviality:
            checks = ", ".join(finding.robustness[:3])
            nontriviality = (
                f"The candidate remains visible only after {checks}."
                if checks
                else finding.interpretation
            )
        surprising = _distinct_scientific_text(
            finding.surprising_result, finding.claim
        )
        practical = _distinct_scientific_text(
            finding.practical_value.strip() or finding.significance.strip(),
            finding.claim,
            finding.interpretation,
            surprising,
            finding.next_validation,
        )
        principle_statement = finding.principle_statement.strip()
        if level == "principle_level" and not principle_statement:
            principle_statement = finding.significance.strip() or finding.interpretation.strip()
        transfer_scope = finding.transfer_scope.strip()
        if not transfer_scope:
            transfer_scope = (
                "Restricted to the supplied sample, acquisition design, and stated boundary conditions."
            )
        provisional = finding.model_copy(
            update={
                "insight_level": level,
                "nontriviality_basis": nontriviality[:2_000],
                "surprising_result": surprising[:2_000],
                "practical_value": practical[:2_000],
                "principle_statement": principle_statement[:2_000],
                "transfer_scope": transfer_scope[:2_000],
                "updated_at": utc_now(),
            }
        )
        eligible, blockers = DataDiscoveryService._promotion_gate(provisional)
        return provisional.model_copy(
            update={
                "promotion_eligible": eligible,
                "promotion_blockers": blockers,
            }
        )

    @staticmethod
    def _apply_reasoning_interpretations(
        *,
        findings: list[DataFinding],
        interpretations: dict[str, FindingInterpretation],
        allowed_principles: set[str],
    ) -> tuple[list[DataFinding], list[dict[str, str]]]:
        """Apply model interpretation as a one-way safety gate.

        Only deterministically supported candidates enter this method. Model output can
        enrich or demote them, but it has no path that can promote a screened test.
        """

        output: list[DataFinding] = []
        reasoning_holdbacks: list[dict[str, str]] = []
        for finding in findings:
            interpretation = interpretations.get(finding.finding_id)
            if interpretation is None:
                output.append(DataDiscoveryService._finalize_insight_contract(finding))
                continue
            # A reasoning pass may clarify a deterministic result, but it may not
            # erase the quantities or scientific contrasts that made it auditable.
            interpreted_claim = interpretation.claim[:2_400] or finding.claim
            if (
                _scientific_specificity(finding.claim) >= 3
                and _scientific_specificity(interpreted_claim)
                < max(1, _scientific_specificity(finding.claim) // 2)
            ):
                interpreted_claim = finding.claim
            updated = finding.model_copy(
                update={
                    "title": interpretation.title[:240] or finding.title,
                    "claim": interpreted_claim,
                    "interpretation": interpretation.interpretation[:4_000],
                    "mechanism": interpretation.mechanism[:4_000],
                    "significance": interpretation.significance[:2_000]
                    or finding.significance,
                    "nontriviality_basis": interpretation.nontriviality_basis[:2_000],
                    "surprising_result": interpretation.surprising_result[:2_000],
                    "practical_value": interpretation.practical_value[:2_000],
                    "principle_statement": interpretation.principle_statement[:2_000],
                    "transfer_scope": interpretation.transfer_scope[:2_000],
                    "principle_chain": _casefold_unique(
                        interpretation.principle_chain, limit=12
                    ),
                    "principle_ids": [
                        item for item in interpretation.principle_ids if item in allowed_principles
                    ],
                    "confounders": _casefold_unique(
                        [*finding.confounders, *interpretation.additional_confounders]
                    ),
                    "limits": _casefold_unique(
                        [*finding.limits, *interpretation.additional_limits]
                    ),
                    "next_validation": interpretation.next_validation[:2_000]
                    or finding.next_validation,
                    "updated_at": utc_now(),
                }
            )
            if interpretation.recommended_disposition == "hold_back":
                reason = interpretation.hold_back_reason.strip() or (
                    "Reasoning review identified a concrete scientific validity concern."
                )
                reasoning_holdbacks.append(
                    {"finding_id": finding.finding_id, "reason": reason[:2_000]}
                )
                continue
            output.append(
                DataDiscoveryService._finalize_insight_contract(
                    updated,
                    requested_level=(
                        "principle_level"
                        if finding.insight_level == "principle_level"
                        else interpretation.insight_level
                    ),
                )
            )
        accepted: list[DataFinding] = []
        for candidate in output:
            duplicate_index = next(
                (
                    index
                    for index, existing in enumerate(accepted)
                    if DataDiscoveryService._template_similarity(existing, candidate) >= 0.72
                ),
                None,
            )
            if duplicate_index is None:
                accepted.append(candidate)
                continue
            existing = accepted[duplicate_index]
            existing_score = len(set((existing.title + " " + existing.claim).casefold().split()))
            candidate_score = len(set((candidate.title + " " + candidate.claim).casefold().split()))
            held_back, retained = (
                (existing, candidate)
                if candidate_score > existing_score
                else (candidate, existing)
            )
            accepted[duplicate_index] = retained
            reasoning_holdbacks.append(
                {
                    "finding_id": held_back.finding_id,
                    "reason": "Held back because its synthesized title and claim were structurally near-duplicate of a stronger retained finding.",
                }
            )
        return accepted, reasoning_holdbacks

    @staticmethod
    def _template_similarity(first: DataFinding, second: DataFinding) -> float:
        return _scientific_text_similarity(
            f"{first.title} {first.claim}", f"{second.title} {second.claim}"
        )

    def _bounded_study_context(self, study_id: str) -> dict[str, Any]:
        """Build a path-free, bounded scientific context card for remote reasoning.

        Context can guide interpretation but never becomes computed evidence. Raw payload values
        are deliberately absent; only adapter profiles and explicitly contextual documents appear.
        """

        study = self.repository.data_study(study_id) or {}
        source_cards: list[dict[str, Any]] = []
        scientific_focus = ""
        for source_id in list(study.get("source_ids") or [])[:8]:
            root = self.repository.source_root(str(source_id))
            source = self.repository.source(str(source_id)) or {}
            card: dict[str, Any] = {
                "source_id": str(source_id),
                "label": str(
                    source.get("display_name")
                    or source.get("name")
                    or source.get("title")
                    or "local dataset"
                )[:300],
                "scenario_context": "",
                "user_brief": "",
                "provenance": {},
            }
            if root is not None:
                for filename, key, limit in (
                    ("SCENARIO.md", "scenario_context", 6_000),
                    ("USER_BRIEF.txt", "user_brief", 3_000),
                ):
                    path = root / filename
                    if not path.is_file() or path.stat().st_size > 256 * 1024:
                        continue
                    try:
                        value = path.read_text(encoding="utf-8", errors="replace")[:limit]
                    except OSError:
                        continue
                    card[key] = value.replace(str(root), "[local-source]")
                    if key == "scenario_context" and not scientific_focus:
                        scientific_focus = " ".join(value.split())[:500]
                provenance_path = root / "PROVENANCE.json"
                if provenance_path.is_file() and provenance_path.stat().st_size <= 2 * 1024 * 1024:
                    try:
                        provenance = json.loads(
                            provenance_path.read_text(encoding="utf-8", errors="replace")
                        )
                    except (OSError, json.JSONDecodeError):
                        provenance = {}
                    if isinstance(provenance, dict):
                        card["provenance"] = {
                            key: provenance.get(key)
                            for key in (
                                "publisher",
                                "doi",
                                "accession",
                                "release",
                                "version",
                                "license",
                            )
                            if provenance.get(key) not in (None, "", [], {})
                        }
            source_cards.append(card)
        asset_page = self.repository.data_assets(study_id=study_id, limit=500)
        assets: list[dict[str, Any]] = []
        for item in list(asset_page.get("items") or [])[:40]:
            metadata = dict(item.get("metadata") or {})
            profile = metadata.get("profile")
            assets.append(
                {
                    "asset_id": item.get("asset_id"),
                    "format": item.get("format"),
                    "modality": item.get("modality"),
                    "role": item.get("role"),
                    "status": item.get("status"),
                    "profile": profile if isinstance(profile, dict) else {},
                    "warnings": list(item.get("warnings") or [])[:5],
                }
            )
        dataset_graph = dict(dict(study.get("coverage") or {}).get("dataset_graph") or {})
        semantics = dict(dataset_graph.get("semantics") or {})
        blueprint = self.repository.study_blueprint(study_id) or {}
        semantic_views = []
        for card in list(semantics.get("views") or [])[:40]:
            if not isinstance(card, dict):
                continue
            semantic_views.append(
                {
                    "view_id": card.get("view_id"),
                    "name": card.get("name"),
                    "kind": card.get("kind"),
                    "dimensions": card.get("dimensions"),
                    "unit_coverage": card.get("unit_coverage"),
                    "variable_bindings": list(card.get("variable_bindings") or [])[:60],
                }
            )
        return compact_scientific_context({
            "scientific_focus": scientific_focus,
            "sources": source_cards,
            "asset_profiles": assets,
            "dataset_semantics": {
                "schema_version": semantics.get("schema_version"),
                "independent_unit_candidates": list(
                    semantics.get("independent_unit_candidates") or []
                )[:40],
                "recommended_split_strategy": semantics.get(
                    "recommended_split_strategy"
                ),
                "prohibited_scientific_variables": list(
                    semantics.get("prohibited_scientific_variables") or []
                )[:80],
                "views": semantic_views,
                "alignments": list(dataset_graph.get("alignments") or [])[:60],
            },
            "study_blueprint": {
                "schema_version": blueprint.get("schema_version"),
                "domain_candidates": list(blueprint.get("domain_candidates") or [])[:10],
                "scientific_objects": list(blueprint.get("scientific_objects") or [])[:40],
                "variable_bindings": list(blueprint.get("variable_bindings") or [])[:200],
                "target_bindings": list(blueprint.get("target_bindings") or [])[:100],
                "input_bindings": list(blueprint.get("input_bindings") or [])[:100],
                "independent_units": list(blueprint.get("independent_units") or [])[:40],
                "joins": list(blueprint.get("joins") or [])[:60],
                "unit_bindings": list(blueprint.get("unit_bindings") or [])[:100],
                "missing_value_codes": list(blueprint.get("missing_value_codes") or [])[:60],
                "split_candidates": list(blueprint.get("split_candidates") or [])[:20],
                "context_excerpts": list(blueprint.get("context_excerpts") or [])[:30],
                "interpretation_summary": blueprint.get("interpretation_summary"),
                "confidence": blueprint.get("confidence"),
                "needs_user_confirmation": blueprint.get("needs_user_confirmation"),
                "warnings": list(blueprint.get("warnings") or [])[:20],
            },
            "evidence_rule": (
                "Scenario text and user briefs guide interpretation but are not evidence; "
                "only executed tests and computed anchors support findings."
            ),
        })

    def _review_prior_art(
        self,
        *,
        findings: list[DataFinding],
        objective: str,
        maximum: int,
    ) -> tuple[list[DataFinding], list[dict[str, Any]], str]:
        """Run current metadata searches for the strongest surviving results.

        Metadata retrieval can establish that related prior work exists, but
        it cannot establish novelty. Empty or failed searches therefore remain
        ``not_assessed`` instead of being promoted to a novelty claim.
        """

        if self.literature_searcher is None:
            return findings, [], "Current-literature review was unavailable in this runtime."
        ranked = sorted(
            (
                item
                for item in findings
                if item.status in {"supported_candidate", "inconclusive"}
            ),
            key=lambda item: (
                item.status != "supported_candidate",
                item.validation_level == "exploratory",
                item.finding_id,
            ),
        )[: max(0, maximum)]
        updates: dict[str, DataFinding] = {}
        receipts: list[dict[str, Any]] = []
        for finding in ranked:
            check_cancelled()
            query = " ".join(
                part
                for part in (
                    objective.strip(),
                    finding.title,
                    finding.claim,
                    finding.mechanism,
                    finding.significance,
                )
                if part
            )[:1_500]
            try:
                search = self.literature_searcher(
                    query,
                    area="",
                    target_count=5,
                    timeout=30.0,
                )
            except Exception as exc:
                receipts.append(
                    {
                        "finding_id": finding.finding_id,
                        "state": "failed",
                        "error": type(exc).__name__,
                    }
                )
                continue
            results = [dict(item) for item in list(search.get("results") or [])[:10]]
            retrieved_records = [
                {
                    "work_id": str(item.get("work_id") or ""),
                    "title": str(item.get("title") or "")[:500],
                    "year": item.get("year"),
                    "doi": str(item.get("doi") or ""),
                    "url": str(item.get("url") or ""),
                    "publication_status": str(item.get("publication_status") or ""),
                }
                for item in results
            ]
            public_records = [
                item
                for item in retrieved_records
                if _prior_art_title_relevant(finding, item)
            ]
            receipts.append(
                {
                    "finding_id": finding.finding_id,
                    "state": str(search.get("state") or "unknown"),
                    "search_id": str(search.get("search_id") or ""),
                    "retrieved_result_count": len(retrieved_records),
                    "relevant_result_count": len(public_records),
                    "result_count": len(public_records),
                    "relevance_gate": "same-domain title evidence; lexical coincidence rejected",
                    "sources": list(search.get("sources") or []),
                    "unavailable_sources": list(search.get("unavailable_sources") or []),
                }
            )
            if public_records:
                updates[finding.finding_id] = finding.model_copy(
                    update={
                        "novelty_status": "prior_art_found",
                        "prior_art": public_records,
                        "updated_at": utc_now(),
                    }
                )
        return [updates.get(item.finding_id, item) for item in findings], receipts, ""

    def _run_visual_interpretation(
        self,
        *,
        study_id: str,
        provider_id: str,
        base_url: str,
        api_key: str,
        vision_model: str,
        budget: DiscoveryBudget,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
        if not vision_model:
            return [], [], "No compatible vision model was available; quantitative analysis continued."
        page = self.repository.data_assets(study_id=study_id, limit=500)
        candidates = [
            DataAsset.model_validate(item)
            for item in page["items"]
            if str(item.get("modality")) in {"image", "volume"}
            and str(item.get("status")) == "analyzable"
            and bool(dict(item.get("metadata") or {}).get("evidence_eligible", True))
        ]
        candidates.sort(key=lambda item: (item.role != "raw", item.byte_size, item.asset_id))
        if not candidates:
            return [], [], "No bounded scientific image preview was available for vision analysis."
        observations: list[dict[str, Any]] = []
        receipts: list[dict[str, Any]] = []
        policy = ModelPolicy(
            mode="remote",
            provider=provider_id,
            model=vision_model,
            base_url=base_url,
            remote_egress_confirmed=True,
        )
        vision_provider = OpenAICompatibleProvider(policy, api_key=api_key, timeout=180)
        try:
            maximum_images = min(
                len(candidates),
                budget.visual_calls * 2,
                MAX_DEFAULT_REMOTE_PREVIEW_IMAGES,
            )
            for start in range(0, maximum_images, 2):
                batch = candidates[start : start + 2]
                preview_records: list[dict[str, Any]] = []
                parts: list[dict[str, Any]] = []
                for asset in batch:
                    root = self.repository.source_root(asset.source_id)
                    if root is None:
                        continue
                    preview = build_preview(asset, root)
                    if preview.get("kind") != "image" or not preview.get("data_url"):
                        continue
                    preview_records.append(
                        {
                            "asset_id": asset.asset_id,
                            "format": asset.format,
                            "derived": bool(preview.get("derived")),
                            "preview_sha256": preview["preview_sha256"],
                        }
                    )
                    parts.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": preview["data_url"]},
                        }
                    )
                if not parts:
                    continue
                vision_input = {"previews": preview_records}
                vision_started = time.monotonic()
                try:
                    generation = vision_provider.generate_typed(
                        model_type=VisualObservationBatch,
                        system_prompt=(
                            "Interpret the supplied bounded scientific previews conservatively. "
                            "Return at most one observation per supplied asset ID. Treat visual "
                            "patterns as context, never as proof, and state acquisition or rendering "
                            "limitations. Do not infer patient identity or hidden metadata."
                        ),
                        prompt_template="data-vision-observation-v1",
                        input_label="bounded_preview_manifest",
                        input_payload=vision_input,
                        content_parts=parts,
                        max_tokens=2_400,
                    )
                    batch_value = VisualObservationBatch.model_validate(generation.value)
                except Exception as exc:
                    self._provider_receipt(
                        study_id=study_id,
                        phase="understand",
                        provider=provider_id,
                        model=vision_model,
                        endpoint_class="vision_reasoning",
                        state="failed",
                        started=vision_started,
                        prompt_template="data-vision-observation-v1",
                        input_payload=vision_input,
                        error=exc,
                        preview_hashes=[
                            str(item.get("preview_sha256") or "") for item in preview_records
                        ],
                    )
                    receipts.append(
                        {
                            "model": vision_model,
                            "previews": preview_records,
                            "state": "failed",
                            "error": type(exc).__name__,
                        }
                    )
                    continue
                allowed = {item["asset_id"] for item in preview_records}
                accepted = [
                    item.model_dump(mode="json")
                    for item in batch_value.observations
                    if item.asset_id in allowed
                ]
                observations.extend(accepted)
                provider_receipt = self._provider_receipt(
                    study_id=study_id,
                    phase="understand",
                    provider=provider_id,
                    model=vision_model,
                    endpoint_class="vision_reasoning",
                    state="succeeded",
                    started=vision_started,
                    prompt_template="data-vision-observation-v1",
                    input_payload=vision_input,
                    generation=generation,
                    preview_hashes=[
                        str(item.get("preview_sha256") or "") for item in preview_records
                    ],
                )
                receipts.append(
                    {
                        "model": vision_model,
                        "previews": preview_records,
                        "state": "succeeded",
                        "trace": generation.trace.model_dump(mode="json"),
                        "attempt_id": provider_receipt["attempt_id"],
                    }
                )
        finally:
            vision_provider.close()
        if not observations:
            return observations, receipts, "Vision interpretation was unavailable; quantitative analysis continued."
        return observations, receipts, ""

    def _run_generated_challenge(
        self,
        *,
        study_id: str,
        provider: OpenAICompatibleProvider,
        findings: list[DataFinding],
        outcomes: list[OperatorOutcome],
        phase_id: Literal["analyze", "challenge"] = "challenge",
    ) -> tuple[list[DataFinding], dict[str, Any], str]:
        phase_label = "Analyze" if phase_id == "analyze" else "Challenge"
        endpoint_prefix = "generated_code_primary" if phase_id == "analyze" else "generated_code"
        compact_tests = []
        for outcome in outcomes[:12]:
            association = dict(
                outcome.result.estimate.get("strongest_association") or {}
            )
            eligible_findings = [
                finding.finding_id
                for finding in findings
                if outcome.result.test_id in finding.test_ids
                or outcome.finding.finding_id == finding.finding_id
            ]
            if not eligible_findings:
                continue
            compact_tests.append(
                {
                    "test_id": outcome.result.test_id,
                    "eligible_finding_ids": eligible_findings,
                    "operator": outcome.plan.operator,
                    "correlation": association.get("coefficient"),
                    "n": association.get("n"),
                    "estimate": {
                        key: value
                        for key, value in outcome.result.estimate.items()
                        if key not in {"summaries", "session_effects", "hardware_level_correlations"}
                    },
                    "uncertainty": outcome.result.uncertainty,
                    "sensitivities": outcome.result.sensitivities,
                }
            )
        table_contracts: list[dict[str, Any]] = []
        local_tables: list[dict[str, Any]] = []
        views_by_asset: dict[str, str] = {}
        for view in self.repository.data_views(study_id):
            for asset_id in view.asset_ids:
                views_by_asset.setdefault(asset_id, view.view_id)
        assets_page = self.repository.data_assets(study_id=study_id, limit=500)
        for payload in list(assets_page.get("items") or []):
            if len(local_tables) >= 4:
                break
            asset = DataAsset.model_validate(payload)
            if (
                asset.role != "raw"
                or asset.status != "analyzable"
                or asset.modality != "table"
                or not bool(asset.metadata.get("evidence_eligible", True))
            ):
                continue
            source_root = self.repository.source_root(asset.source_id)
            if source_root is None:
                continue
            try:
                loaded = load_numeric(asset, source_root)
            except Exception:
                loaded = None
            if loaded is None or loaded.values.shape[0] < 10:
                continue
            row_count = min(2_000, loaded.values.shape[0])
            column_count = min(20, loaded.values.shape[1])
            indices = np.linspace(
                0, loaded.values.shape[0] - 1, row_count, dtype=int
            )
            values = np.asarray(
                loaded.values[indices, :column_count], dtype=float
            )
            summaries: list[dict[str, Any]] = []
            for index, variable in enumerate(loaded.variables[:column_count]):
                finite = values[np.isfinite(values[:, index]), index]
                summaries.append(
                    {
                        "variable": variable,
                        "finite_count": int(finite.size),
                        "minimum": float(np.min(finite)) if finite.size else None,
                        "median": float(np.median(finite)) if finite.size else None,
                        "maximum": float(np.max(finite)) if finite.size else None,
                        "mean": float(np.mean(finite)) if finite.size else None,
                        "standard_deviation": (
                            float(np.std(finite, ddof=1)) if finite.size > 1 else None
                        ),
                    }
                )
            table_id = f"table:{asset.asset_id.split(':')[-1]}"
            table_contracts.append(
                {
                    "table_id": table_id,
                    "asset_id": asset.asset_id,
                    "view_id": views_by_asset.get(asset.asset_id, ""),
                    "variables": loaded.variables[:column_count],
                    "sampled_rows": row_count,
                    "source_rows": int(loaded.values.shape[0]),
                    "summaries": summaries,
                    "locator_kind": sorted(loaded.locator),
                }
            )
            local_tables.append(
                {
                    "table_id": table_id,
                    "asset_id": asset.asset_id,
                    "view_id": views_by_asset.get(asset.asset_id, ""),
                    "locator": loaded.locator,
                    "variables": loaded.variables[:column_count],
                    "values": [
                        [float(value) if math.isfinite(value) else None for value in row]
                        for row in values
                    ],
                }
            )
        if not compact_tests and not local_tables:
            return findings, {"state": "not_needed"}, ""
        study = self.repository.data_study(study_id) or {}
        job_id = str(study.get("job_id") or "")
        if job_id:
            self._event(
                job_id,
                "activity",
                phase_label,
                f"Planning an isolated generated scientific program over {len(compact_tests)} executed-test receipts and {len(local_tables)} bounded local tables",
                study_id=study_id,
            )
        generated_plan_input = {
            "schema_version": "principia.generated-analysis-input/v1",
            "tests": compact_tests,
            "table_contracts": table_contracts,
        }
        provider_policy = getattr(provider, "policy", None)
        receipt_provider = str(getattr(provider_policy, "provider", "test-provider"))
        receipt_model = str(getattr(provider_policy, "model", "test-model"))
        generated_plan_started = time.monotonic()
        try:
            generation = provider.generate_typed(
                model_type=GeneratedAnalysisProposal,
                system_prompt=(
                    "Write one compact deterministic Python scientific sensitivity analysis over JSON INPUT. "
                    "INPUT has the exact schema principia.generated-analysis-input/v1 with keys schema_version, "
                    "tests, and tables. Each test has test_id and eligible_finding_ids. Each execution table has "
                    "table_id, asset_id, view_id, locator, variables, and values; the planning payload provides the "
                    "same table IDs with schemas and summaries but omits values. Select explicit target_finding_ids, "
                    "target_test_ids, required_table_ids, and a predeclared stability_check in the proposal. The code "
                    "must assign a JSON object to RESULT using schema principia.generated-analysis-result/v1 with "
                    "those exact target IDs, stability_check_passed (boolean), diagnostics (list), and finding. "
                    "finding must be null when the check fails; otherwise it must contain claim, effect_size, "
                    "independent_unit_count, uncertainty, sensitivities, and falsifier. Test a scientifically "
                    "motivated robustness, confounding, interaction, regime, or "
                    "cross-table replication question not already resolved by the supplied operators. Report "
                    "effect sizes, independent-unit caveats, null/contradictory evidence, and falsifiers. It may import only "
                    "math, statistics, or numpy; must not read files, use networking, processes, "
                    "dynamic imports, serialization, eval, or exec; and must preserve null and "
                    "contradictory results. Never use row order or identifiers as scientific variables, never "
                    "claim novelty, and do not emit a finding unless a predeclared stability check passes."
                ),
                prompt_template="generated-data-challenge-v2",
                input_label="bounded_executed_test_summaries",
                input_payload=generated_plan_input,
                max_tokens=4_500,
                thinking_budget=4_096,
            )
            proposal = GeneratedAnalysisProposal.model_validate(generation.value)
            self._provider_receipt(
                study_id=study_id,
                phase=phase_id,
                provider=receipt_provider,
                model=receipt_model,
                endpoint_class=f"{endpoint_prefix}_planning",
                state="succeeded",
                started=generated_plan_started,
                prompt_template="generated-data-challenge-v2",
                input_payload=generated_plan_input,
                generation=generation,
            )
        except Exception as exc:
            self._provider_receipt(
                study_id=study_id,
                phase=phase_id,
                provider=receipt_provider,
                model=receipt_model,
                endpoint_class=f"{endpoint_prefix}_planning",
                state="failed",
                started=generated_plan_started,
                prompt_template="generated-data-challenge-v2",
                input_payload=generated_plan_input,
                error=exc,
            )
            return (
                findings,
                {"state": "provider_plan_failed", "error": type(exc).__name__},
                "Generated-Python planning failed; deterministic challenge checks remain authoritative.",
            )
        known_findings = {item.finding_id for item in findings}
        known_tests = {str(item["test_id"]) for item in compact_tests}
        known_tables = {str(item["table_id"]) for item in table_contracts}
        def lineage_errors(candidate: GeneratedAnalysisProposal) -> list[str]:
            errors: list[str] = []
            if not set(candidate.target_finding_ids) <= known_findings:
                errors.append("unknown target finding")
            if not set(candidate.target_test_ids) <= known_tests:
                errors.append("unknown target test")
            if not set(candidate.required_table_ids) <= known_tables:
                errors.append("unknown required table")
            for finding_id in candidate.target_finding_ids:
                if not any(
                    finding_id in list(test.get("eligible_finding_ids") or [])
                    for test in compact_tests
                    if test.get("test_id") in candidate.target_test_ids
                ):
                    errors.append(f"no selected test is linked to {finding_id}")
            return sorted(set(errors))

        proposal_errors = lineage_errors(proposal)
        lineage_repair: dict[str, Any] = {"attempted": False}
        if proposal_errors:
            lineage_repair = {
                "attempted": True,
                "initial_errors": proposal_errors,
            }
            if job_id:
                self._event(
                    job_id,
                    "activity",
                    phase_label,
                    "Repairing generated-code lineage against the exact finding, test, and table IDs",
                    study_id=study_id,
                )
            repair_input = {
                "rejected_proposal": proposal.model_dump(mode="json"),
                "rejection_errors": proposal_errors,
                "allowed_tests": compact_tests,
                "allowed_table_contracts": table_contracts,
                "allowed_finding_ids": sorted(known_findings),
            }
            repair_started = time.monotonic()
            try:
                repaired_generation = provider.generate_typed(
                    model_type=GeneratedAnalysisProposal,
                    system_prompt=(
                        "Repair the rejected generated-analysis proposal. Return the complete proposal schema, "
                        "but use only the exact allowed IDs supplied below. Preserve the scientific intent when "
                        "it is compatible with those records; otherwise choose one valid linked test/finding pair. "
                        "Update every ID embedded in the Python RESULT object as well as the proposal fields. "
                        "Do not weaken the stability check, invent a record, read files, use networking, or claim novelty."
                    ),
                    prompt_template="generated-data-challenge-lineage-repair-v1",
                    input_label="rejected_proposal_and_exact_lineage",
                    input_payload=repair_input,
                    max_tokens=4_500,
                    thinking_budget=4_096,
                )
                proposal = GeneratedAnalysisProposal.model_validate(
                    repaired_generation.value
                )
                proposal_errors = lineage_errors(proposal)
                lineage_repair.update(
                    {
                        "final_errors": proposal_errors,
                        "trace": repaired_generation.trace.model_dump(mode="json"),
                    }
                )
                generation = repaired_generation
                self._provider_receipt(
                    study_id=study_id,
                    phase=phase_id,
                    provider=receipt_provider,
                    model=receipt_model,
                    endpoint_class=f"{endpoint_prefix}_lineage_repair",
                    state="succeeded",
                    started=repair_started,
                    prompt_template="generated-data-challenge-lineage-repair-v1",
                    input_payload=repair_input,
                    generation=repaired_generation,
                    retry_index=1,
                )
            except Exception as exc:
                self._provider_receipt(
                    study_id=study_id,
                    phase=phase_id,
                    provider=receipt_provider,
                    model=receipt_model,
                    endpoint_class=f"{endpoint_prefix}_lineage_repair",
                    state="failed",
                    started=repair_started,
                    prompt_template="generated-data-challenge-lineage-repair-v1",
                    input_payload=repair_input,
                    error=exc,
                    retry_index=1,
                )
                proposal_errors = [
                    *proposal_errors,
                    f"lineage repair failed ({type(exc).__name__})",
                ]
                lineage_repair["final_errors"] = proposal_errors
        if proposal_errors:
            return (
                findings,
                {
                    "state": "plan_lineage_rejected",
                    "errors": sorted(set(proposal_errors)),
                    "lineage_repair": lineage_repair,
                },
                "Generated-Python planning was rejected because its finding/test/table lineage was invalid.",
            )
        artifact_name = "generated-primary-1" if phase_id == "analyze" else "generated-challenge-1"
        root = self._artifact_root(study_id) / "code" / artifact_name
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        sandbox = AnalysisSandbox(python_executable=Path(sys.executable), wall_timeout_seconds=120)
        result, audit = sandbox.run(
            code=proposal.code,
            inputs={
                "schema_version": "principia.generated-analysis-input/v1",
                "tests": compact_tests,
                "tables": local_tables,
            },
            artifact_root=root,
            read_roots=[],
            seed=int(canonical_sha256(compact_tests)[:8], 16),
        )
        environment = {
            "python": sys.version.split()[0],
            "platform": sys.platform,
            "packages": {},
        }
        for name in ("numpy", "pandas", "scipy", "statsmodels", "scikit-learn"):
            try:
                environment["packages"][name] = package_metadata.version(name)  # type: ignore[index]
            except package_metadata.PackageNotFoundError:
                continue
        self._atomic_write(
            root / "environment.json",
            (json.dumps(environment, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(),
        )
        result_payload = dict(result) if isinstance(result, dict) else {}
        returned_finding = result_payload.get("finding")
        lineage_valid = (
            result_payload.get("schema_version") == "principia.generated-analysis-result/v1"
            and set(result_payload.get("target_finding_ids") or [])
            == set(proposal.target_finding_ids)
            and set(result_payload.get("target_test_ids") or [])
            == set(proposal.target_test_ids)
        )
        scientific_valid = (
            lineage_valid
            and result_payload.get("stability_check_passed") is True
            and isinstance(returned_finding, dict)
            and bool(str(returned_finding.get("claim") or "").strip())
            and returned_finding.get("effect_size") is not None
            and int(returned_finding.get("independent_unit_count") or 0) >= 2
            and bool(str(returned_finding.get("falsifier") or "").strip())
            and isinstance(returned_finding.get("uncertainty") or {}, dict)
            and isinstance(returned_finding.get("sensitivities") or [], list)
            and isinstance(returned_finding.get("negative_evidence") or [], list)
            and isinstance(result_payload.get("diagnostics") or [], list)
        )
        receipt_state = "fallback"
        if result is not None and not lineage_valid:
            receipt_state = "lineage_invalid"
        elif result is not None and not scientific_valid:
            receipt_state = "scientific_null"
        elif scientific_valid:
            receipt_state = "scientifically_valid"
        receipt = {
            "state": receipt_state,
            "scientific_intent": proposal.scientific_intent,
            "target_finding_ids": proposal.target_finding_ids,
            "target_test_ids": proposal.target_test_ids,
            "required_table_ids": proposal.required_table_ids,
            "stability_check": proposal.stability_check,
            "expected_output": proposal.expected_output,
            "code_digest": audit.code_digest,
            "ast_digest": audit.ast_digest,
            "isolated": audit.isolated,
            "violations": list(audit.violations),
            "resource_usage": {
                "elapsed_seconds": audit.elapsed_seconds,
                "max_resident_bytes": audit.max_resident_bytes,
                "memory_limit_bytes": audit.memory_limit_bytes,
                "memory_limit_kind": audit.memory_limit_kind,
                "output_bytes": audit.output_bytes,
            },
            "result_digest": canonical_sha256(result) if result is not None else "",
            "input_digest": canonical_sha256(
                {
                    "schema_version": "principia.generated-analysis-input/v1",
                    "tests": compact_tests,
                    "tables": local_tables,
                }
            ),
            "table_contracts": table_contracts,
            "trace": generation.trace.model_dump(mode="json"),
            "lineage_repair": lineage_repair,
        }
        self._atomic_write(
            root / "receipt.json",
            (json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(),
        )
        if result is None:
            return (
                findings,
                receipt,
                "Generated Python did not pass verified isolation; deterministic operators were retained.",
            )
        if not lineage_valid:
            return (
                findings,
                receipt,
                "Generated Python returned invalid finding/test lineage; it did not strengthen any finding.",
            )
        if not scientific_valid:
            return (
                findings,
                receipt,
                "Generated Python returned a null or stability-failing result; it was preserved without strengthening any finding.",
            )
        if job_id:
            self._event(
                job_id,
                "activity",
                phase_label,
                f"Isolated generated-code challenge completed in {audit.elapsed_seconds:.1f}s; receipt {audit.code_digest[:12]}",
                study_id=study_id,
            )
        target_tables = {
            str(item["table_id"]): item
            for item in local_tables
            if item["table_id"] in proposal.required_table_ids
        }
        updated: list[DataFinding] = []
        for finding in findings:
            if finding.finding_id not in proposal.target_finding_ids:
                updated.append(finding)
                continue
            plan_digest = canonical_sha256(
                {
                    "proposal": proposal.model_dump(mode="json"),
                    "input_digest": receipt["input_digest"],
                    "code_digest": audit.code_digest,
                }
            )
            generated_test_id = "test:" + canonical_sha256(
                {"finding": finding.finding_id, "plan": plan_digest, "result": result_payload}
            )[:24]
            generated_test = {
                "test_id": generated_test_id,
                "study_id": study_id,
                "finding_id": finding.finding_id,
                "hypothesis_id": finding.hypothesis_ids[0] if finding.hypothesis_ids else "",
                "plan_id": "plan:" + plan_digest[:24],
                "plan_digest": plan_digest,
                "state": "succeeded",
                "sample_definition": str(returned_finding.get("sample_definition") or "bounded generated-code challenge"),
                "independent_unit_count": int(returned_finding["independent_unit_count"]),
                "estimate": {"generated_challenge": returned_finding.get("effect_size")},
                "uncertainty": dict(returned_finding.get("uncertainty") or {}),
                "corrected_significance": {},
                "diagnostics": [str(item) for item in list(result_payload.get("diagnostics") or [])],
                "sensitivities": [dict(item) for item in list(returned_finding.get("sensitivities") or []) if isinstance(item, dict)],
                "negative_evidence": [str(item) for item in list(returned_finding.get("negative_evidence") or [])],
                "artifacts": [f"code/{artifact_name}/receipt.json"],
                "expression_latex": "",
                "equation_variables": [],
                "split_validation": {},
                "result_digest": canonical_sha256(result_payload),
                "analysis_plan": {
                    "plan_id": "plan:" + plan_digest[:24],
                    "executor": "python",
                    "operator": (
                        "generated_scientific_program"
                        if phase_id == "analyze"
                        else "generated_scientific_challenge"
                    ),
                    "code_digest": audit.code_digest,
                    "target_test_ids": proposal.target_test_ids,
                    "required_table_ids": proposal.required_table_ids,
                    "stability_check": proposal.stability_check,
                },
                "created_at": utc_now(),
            }
            self.repository.save_data_test(generated_test)
            evidence_ids: list[str] = []
            for table_id, table in target_tables.items():
                if not table.get("view_id"):
                    continue
                evidence_id = "evidence:" + canonical_sha256(
                    {"finding": finding.finding_id, "test": generated_test_id, "table": table_id}
                )[:24]
                self.repository.save_computed_evidence(
                    ComputedEvidenceAnchor(
                        evidence_id=evidence_id,
                        study_id=study_id,
                        finding_id=finding.finding_id,
                        test_id=generated_test_id,
                        asset_id=str(table["asset_id"]),
                        view_id=str(table["view_id"]),
                        locator={
                            "table_id": table_id,
                            "sample": table.get("locator") or {},
                            "source_values_transmitted": False,
                        },
                        plan_digest=plan_digest,
                        code_digest=audit.code_digest,
                        executor_version="principia-generated-python/v1",
                        result_digest=canonical_sha256(result_payload),
                    )
                )
                evidence_ids.append(evidence_id)
            updated.append(
                finding.model_copy(
                    update={
                        "test_ids": [*finding.test_ids, generated_test_id],
                        "evidence_ids": [*finding.evidence_ids, *evidence_ids],
                        "robustness": [
                            *finding.robustness,
                            f"targeted isolated generated-Python stability check {audit.code_digest[:12]}",
                        ],
                        "updated_at": utc_now(),
                    }
                )
            )
        return updated, receipt, ""

    @staticmethod
    def _resolve_model(
        requested: str,
        preferences: list[str],
        available: set[str],
        *,
        optional: bool = False,
    ) -> str:
        if requested and requested != "auto":
            return requested if requested in available else ""
        for model in preferences:
            if model in available:
                return model
        return "" if optional or not available else sorted(available)[0]

    @staticmethod
    def _combined_coverage(inventories: list[tuple[str, InventoryResult]]) -> dict[str, Any]:
        coverage: dict[str, Any] = {
            "source_count": len(inventories),
            "asset_count": 0,
            "view_count": 0,
            "total_bytes": 0,
            "status_counts": {},
            "modality_counts": {},
            "format_counts": {},
            "read_only": True,
            "sources": [{"source_id": source_id, **inventory.coverage} for source_id, inventory in inventories],
        }
        for _, inventory in inventories:
            for scalar in ("asset_count", "view_count", "total_bytes"):
                coverage[scalar] += int(inventory.coverage.get(scalar) or 0)
            for group in ("status_counts", "modality_counts", "format_counts"):
                for key, value in dict(inventory.coverage.get(group) or {}).items():
                    coverage[group][key] = int(coverage[group].get(key) or 0) + int(value)
        return coverage

    def _set_phase(self, study_id: str, phase: str, progress: float, message: str) -> None:
        with self._lock:
            check_cancelled()
            study = self.repository.update_data_study(
                study_id, state="running", phase=phase
            )
            job_id = str(study["job_id"])
            self._update_job(job_id, progress=progress, status=message, stage=phase.title())
            self._event(job_id, "phase", phase.title(), message, phase_id=phase, study_id=study_id)

    def _run_with_heartbeat(
        self,
        *,
        study_id: str,
        cancellation: threading.Event,
        base_progress: float,
        stage: str,
        message: str,
        call: Callable[[], Any],
    ) -> Any:
        """Keep long provider-bound phases visibly alive without faking progress.

        The bounded increment is explicitly a heartbeat, never a percentage of
        model completion. Cancellation propagates to the request context; its socket is closed
        and its worker joined before the task can become cancelled.
        """

        study = self.repository.data_study(study_id)
        if study is None:
            return call()
        job_id = str(study["job_id"])
        started = time.monotonic()
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="principia-provider")
        future = executor.submit(copy_context().run, call)
        try:
            while True:
                try:
                    return future.result(timeout=5.0)
                except FutureTimeoutError:
                    elapsed = int(time.monotonic() - started)
                    stopping = cancellation.is_set()
                    status = (
                        "Stopping the active request and preserving completed evidence"
                        if stopping
                        else (
                            f"{message} · provider request active · {elapsed}s elapsed · "
                            "the next analysis milestone will appear here"
                        )
                    )
                    # Reserve the next phase boundary: elapsed time is not
                    # presented as fractional model completion.
                    heartbeat_progress = min(base_progress + 0.03, 0.89)
                    self._update_job(
                        job_id,
                        progress=heartbeat_progress,
                        status=status,
                    )
                    self._event(
                        job_id,
                        "heartbeat",
                        stage,
                        status,
                        study_id=study_id,
                        elapsed_seconds=elapsed,
                        activity_kind="provider_request",
                        cancellation_available=True,
                        progress_semantics="phase_checkpoint_not_model_percentage",
                    )
        finally:
            executor.shutdown(wait=True, cancel_futures=False)

    def _update_job(
        self,
        job_id: str,
        *,
        progress: float,
        status: str,
        stage: str | None = None,
        completed: int | None = None,
        total: int | None = None,
    ) -> None:
        job = self.repository.get_job(job_id)
        if job is None:
            return
        update: dict[str, Any] = {
            "state": job.state if job.state in {"cancelling", "pausing", "paused"} else "running",
            "progress": max(job.progress, min(1.0, progress)),
            "status_message": status,
            "last_activity_at": utc_now(),
            "updated_at": utc_now(),
        }
        if stage:
            update["stage"] = stage
        if completed is not None:
            update["completed_units"] = completed
        if total is not None:
            update["total_units"] = total
        self.repository.save_job(job.model_copy(update=update))

    def _event(self, job_id: str, event_type: str, stage: str, message: str, **payload: Any) -> None:
        self.repository.append_job_event(
            job_id,
            event_type,
            {"stage": stage, "message": message, **payload},
            event_id=event_id("data-event"),
        )

    def _check_deadline(self, study_id: str, cancellation: threading.Event, deadline: float) -> None:
        self._check_control(study_id, cancellation)
        if time.monotonic() >= deadline:
            raise TimeoutError("Scientific execution exhausted its frozen wall-time budget.")

    def _check_control(self, study_id: str, cancellation: threading.Event) -> None:
        while True:
            if cancellation.is_set():
                raise _Cancelled
            with self._lock:
                pause = self._pause.get(study_id)
            if pause is None or not pause.is_set():
                return
            status = self.repository.data_study_status(study_id)
            if status and status["state"] != "paused":
                self.repository.update_data_study(study_id, state="paused")
                self.repository.update_data_session_state(str(status.get("session_id") or ""), "paused")
                job = self.repository.get_job(str(status["job_id"]))
                if job:
                    self.repository.save_job(job.model_copy(update={"state": "paused", "status_message": "Paused at a safe analysis boundary", "updated_at": utc_now()}))
            cancellation.wait(0.2)

    def _artifact_root(self, study_id: str) -> Path:
        if not study_id.startswith("study:"):
            raise ValueError("invalid study identifier")
        root = self.storage.artifacts_dir / "data-discovery" / study_id
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        return root

    def _write_report(
        self, study_id: str, report: DataDiscoveryReport, outcomes: list[OperatorOutcome]
    ) -> None:
        artifact_root = self._artifact_root(study_id)
        export_root = self.outputs_root / study_id
        export_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        findings = [item.model_dump(mode="json") for item in report.findings]
        tests = [
            {
                **item.result.model_dump(mode="json"),
                "analysis_plan": item.plan.model_dump(mode="json"),
            }
            for item in outcomes
        ]
        payloads = {
            "report.json": report.model_dump(mode="json"),
            "findings.json": {"schema_version": "principia.data-findings/v1", "items": findings},
            "tests.json": {"schema_version": "principia.data-tests/v1", "items": tests},
            "rules.json": {
                "schema_version": "principia.data-rules/v1",
                "items": self.rules(study_id),
            },
            "programs.json": {
                "schema_version": "principia.scientific-program-collection/v1",
                "items": self.programs(study_id),
            },
            "laws.json": {
                "schema_version": "principia.scientific-law-collection/v1",
                "items": self.laws(study_id),
            },
            "provenance.json": report.provenance,
        }
        extra_principles = [
            sanitized
            for item in self.repository.data_extra_principles(study_id)
            if (sanitized := self._sanitize_extra_principle(item, report.findings)) is not None
        ]
        payloads["extra-principles.json"] = {
            "schema_version": "principia.data-extra-principles/v1",
            "study_id": study_id,
            "record_kind": "extra_principle",
            "status": "provisional_research_synthesis",
            "items": [item.model_dump(mode="json") for item in extra_principles],
        }
        extra_markdown = [
            "# Principia Extra Principles",
            "",
            f"Study: `{study_id}`",
            "",
            "These records are provisional literature-grounded research syntheses. They are not established Global Cloud Principles.",
            "",
        ]
        for principle in extra_principles:
            extra_markdown.extend(
                [
                    f"## {principle.title}",
                    "",
                    f"Record ID: `{principle.extra_principle_id}`",
                    "",
                    principle.claim,
                    "",
                    f"Explanatory gap: {principle.explanatory_gap}",
                    "",
                    f"Mechanism: {principle.mechanism}",
                    "",
                    "### Boundary conditions",
                    "",
                    *[f"- {item}" for item in principle.boundary_conditions],
                    "",
                    "### Falsifiers",
                    "",
                    *[f"- {item}" for item in principle.falsifiers],
                    "",
                    "### Supporting literature",
                    "",
                    *[
                        f"- {source.get('title') or source.get('source_key')}"
                        + (f" — {source.get('url')}" if source.get("url") else "")
                        for source in principle.supporting_sources
                    ],
                    "",
                ]
            )
        extra_md = "\n".join(extra_markdown).rstrip() + "\n"
        markdown = [
            "# Principia data discovery report",
            "",
            f"Study: `{study_id}`",
            "",
            "All findings are candidate hypotheses. No raw data is included in this export.",
            "",
            "## Findings",
            "",
        ]
        for finding in report.findings:
            markdown.extend(
                [
                    f"### {finding.title}",
                    "",
                    f"Status: {finding.status}; validation: {finding.validation_level}; novelty: {finding.novelty_status}.",
                    "",
                    finding.claim,
                    "",
                    finding.interpretation,
                    "",
                ]
            )
        report_md = "\n".join(markdown).rstrip() + "\n"
        for name, payload in payloads.items():
            self._atomic_write(artifact_root / name, (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode())
        self._atomic_write(artifact_root / "report.md", report_md.encode())
        self._atomic_write(artifact_root / "extra-principles.md", extra_md.encode())
        for name in (*payloads, "report.md", "extra-principles.md"):
            copy_artifact(artifact_root / name, export_root / name)
        for root in (artifact_root, export_root):
            for child in ("code", "figures"):
                (root / child).mkdir(exist_ok=True, mode=0o700)
        generated_code = artifact_root / "code"
        export_code = export_root / "code"
        for source in generated_code.rglob("*"):
            if not source.is_file():
                continue
            destination = export_code / source.relative_to(generated_code)
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            copy_artifact(source, destination)

    @staticmethod
    def _atomic_write(path: Path, body: bytes) -> None:
        descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".partial", dir=path.parent)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(body)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)



