from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

# This is a display/retrieval taxonomy, not a replacement for the immutable
# canonical Principle area.  Profiles are deliberately concrete scholarly
# disciplines; transient names, people and problem names (for example
# ``hilbert``) must never become top-level map areas.
_DISCIPLINE_PROFILES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "mathematics-logic",
        (
            r"\btheorem\b",
            r"\bproofs?\b",
            r"\bhilbert\b",
            r"\balgebra(?:ic)?\b",
            r"\bgeometry|geometric\b",
            r"\btopolog(?:y|ical)\b",
            r"\bcombinatori",
            r"\bnumber theory\b",
            r"\bprobability\b",
            r"\bstochastic process",
            r"\bdifferential equations?\b",
            r"\bmathematical\b",
            r"\bformal proposition\b",
        ),
    ),
    (
        "quantum-information",
        (
            r"\bquantum information\b",
            r"\bquantum comput",
            r"\bqubits?\b",
            r"\bquantum channel",
            r"\bquantum error",
        ),
    ),
    (
        "physics",
        (
            r"\bphysics?\b",
            r"\bquantum\b",
            r"\bparticle\b",
            r"\brelativit",
            r"\bthermodynamic",
            r"\bstatistical mechanics\b",
            r"\bkinetic theory\b",
            r"\bboltzmann\b",
            r"\bhydrodynamic",
            r"\bfluid dynamics\b",
            r"\bplasma\b",
            r"\bcondensed matter\b",
            r"\bsuperconduct",
            r"\bcosmolog",
            r"\bastrophys",
        ),
    ),
    (
        "economics-game-theory",
        (
            r"\beconom(?:y|ics|etric)\b",
            r"\bfinanc(?:e|ial|ing)\b",
            r"\bcash[- ]?flow\b",
            r"\bliquidity\b",
            r"\bcapital market",
            r"\bcredit\b",
            r"\bbankrupt",
            r"\bmonetary\b",
            r"\bfiscal\b",
            r"\bfirm-level\b",
            r"\bhousehold income\b",
            r"\bworking capital\b",
            r"\bsolvency\b",
            r"\basset pricing\b",
        ),
    ),
    (
        "ai-ml",
        (
            r"\bartificial intelligence\b",
            r"\bmachine learning\b",
            r"\bdeep learning\b",
            r"\blarge language models?\b",
            r"\bllms?\b",
            r"\bmulti[- ]?agent",
            r"\breinforcement learning\b",
            r"\bneural networks?\b",
            r"\balgorithms?\b",
            r"\bsoftware\b",
            r"\bcomputer science\b",
            r"\btheorem proving\b",
            r"\bpost[- ]?training\b",
            r"\bfoundation models?\b",
            r"\bagentic\b",
        ),
    ),
    (
        "neuroscience-cognition",
        (
            r"\bneuroscience\b",
            r"\bbrain\b",
            r"\bcortical\b",
            r"\bcognition\b",
            r"\bcognitive\b",
            r"\bperception\b",
            r"\bmemory\b",
            r"\battention\b",
            r"\bneural activity\b",
            r"\bdecision making\b",
        ),
    ),
    (
        "medicine-epidemiology",
        (
            r"\bclinical\b",
            r"\bpatients?\b",
            r"\bdisease\b",
            r"\btherap",
            r"\bepidemiolog",
            r"\bpublic health\b",
        ),
    ),
    (
        "biology-evolution",
        (
            r"\bbiolog",
            r"\bgenom",
            r"\bprotein",
            r"\bcellular\b",
            r"\bclinical\b",
            r"\bpatient",
            r"\bdisease\b",
            r"\btherap",
            r"\bimmun",
            r"\bcancer\b",
            r"\becolog",
            r"\bevolution",
        ),
    ),
    (
        "chemistry-materials",
        (
            r"\bchemist",
            r"\bchemical\b",
            r"\bmolecule",
            r"\bcataly",
            r"\bpolymer",
            r"\belectrochem",
            r"\bmaterials science\b",
            r"\bnanomaterial",
        ),
    ),
    (
        "engineering-optimization",
        (
            r"\bengineering\b",
            r"\brobot",
            r"\bcontrol systems?\b",
            r"\bpower systems?\b",
            r"\bmanufactur",
            r"\bmechanical\b",
            r"\belectrical\b",
            r"\bcivil infrastructure\b",
        ),
    ),
    (
        "earth-climate",
        (
            r"\bclimate\b",
            r"\benvironment",
            r"\bgeolog",
            r"\bocean",
            r"\batmospher",
            r"\bearth science\b",
            r"\bsustainab",
            r"\becosystem",
        ),
    ),
    (
        "statistics-causality",
        (
            r"\bstatistics?\b",
            r"\bcausal(?:ity| inference)?\b",
            r"\bregression\b",
            r"\bestimator",
            r"\bidentifiability\b",
        ),
    ),
    (
        "information-control-complexity",
        (
            r"\binformation theory\b",
            r"\bentropy\b",
            r"\bcontrol theory\b",
            r"\bfeedback control\b",
            r"\bcomplex systems?\b",
        ),
    ),
    (
        "computing-industry",
        (
            r"\bsemiconductor",
            r"\bmoore['’]?s law\b",
            r"\bcomputing industry\b",
            r"\bhardware scaling\b",
        ),
    ),
    (
        "scientific-discovery",
        (
            r"\bscientific discovery\b",
            r"\bscientific method\b",
            r"\bexperiment design\b",
            r"\bhypothesis generation\b",
        ),
    ),
    (
        "socio-technical-systems",
        (
            r"\bsocial\b",
            r"\bbehavior",
            r"\bpsycholog",
            r"\bsociolog",
            r"\bpolitic",
            r"\borganization",
            r"\bleadership\b",
            r"\bpublic opinion\b",
        ),
    ),
    (
        "socio-technical-systems",
        (r"\beducation\b", r"\blearning sciences?\b", r"\bstudents?\b", r"\bpedagog"),
    ),
    (
        "socio-technical-systems",
        (r"\blegal\b", r"\blaw\b", r"\bpolicy\b", r"\bregulat", r"\bgovernance\b"),
    ),
)

_COMPILED = tuple(
    (name, tuple(re.compile(pattern, re.IGNORECASE) for pattern in patterns))
    for name, patterns in _DISCIPLINE_PROFILES
)

_LEGACY_AREAS = {
    "hilbert": "mathematics-logic",
    "mas-asd": "ai-ml",
    "cognitive": "neuroscience-cognition",
}


def _text(parts: Iterable[Any]) -> str:
    return " ".join(str(part or "") for part in parts)


def classify_scientific_discipline(
    principle: Mapping[str, Any],
    works: Iterable[Mapping[str, Any]] = (),
) -> str:
    """Return one stable, human-readable discipline for map grouping.

    Linked Work title/abstract/venue provide the strongest context.  Ties use
    the profile order above and the immutable Principle area only as an
    explicit legacy mapping.  The fallback is scientific discovery rather
    than the unhelpfully dominant ``general`` bucket.
    """

    canonical_area = str(principle.get("area") or "").strip().casefold()
    if canonical_area in _LEGACY_AREAS:
        return _LEGACY_AREAS[canonical_area]
    if canonical_area and canonical_area not in {"general", "global", "uncategorized"}:
        # Accept canonical values only when they already identify a known
        # discipline. Person/problem labels cannot leak through this branch.
        known = {name for name, _ in _COMPILED}
        normalized = re.sub(r"[^a-z0-9]+", "-", canonical_area).strip("-")
        if normalized in known:
            return normalized

    work_text = _text(
        field
        for work in works
        for field in (work.get("title"), work.get("abstract"), work.get("venue"))
    )
    principle_text = _text(
        (
            principle.get("title"),
            principle.get("claim"),
            " ".join(str(item) for item in principle.get("tags") or []),
            principle.get("kind"),
        )
    )
    scores: list[tuple[int, int, str]] = []
    for order, (name, patterns) in enumerate(_COMPILED):
        # A linked paper match carries twice the weight of a Principle-text
        # match because generic words such as "network" are cross-disciplinary.
        score = 2 * sum(bool(pattern.search(work_text)) for pattern in patterns)
        score += sum(bool(pattern.search(principle_text)) for pattern in patterns)
        scores.append((score, -order, name))
    best = max(scores, default=(0, 0, "scientific-discovery"))
    return best[2] if best[0] > 0 else "scientific-discovery"


def discipline_label(value: str) -> str:
    return {
        "ai-ml": "AI & Machine Learning",
        "economics-game-theory": "Economics, Finance & Game Theory",
        "neuroscience-cognition": "Neuroscience & Cognition",
        "biology-evolution": "Biology & Evolution",
        "chemistry-materials": "Chemistry & Materials",
        "engineering-optimization": "Engineering, Robotics & Optimization",
        "earth-climate": "Earth & Climate",
        "socio-technical-systems": "Socio-Technical Systems",
        "scientific-discovery": "Scientific Discovery",
    }.get(value, value.replace("-", " ").title())
