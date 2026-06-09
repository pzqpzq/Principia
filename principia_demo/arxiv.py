from __future__ import annotations

import re
import ssl
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed

from .models import SourceWork, to_dict
from .utils import compact_text, enrich_query, keyword_terms, lexical_score, query_expansions, stable_id


ATOM = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
QUERY_STOPWORDS = {
    "design",
    "find",
    "generate",
    "idea",
    "ideas",
    "improve",
    "improving",
    "method",
    "novel",
    "proposal",
    "testable",
    "validation",
}


def search_arxiv(query: str, max_results: int = 8, timeout: int = 12) -> list[dict]:
    seen: set[str] = set()
    all_works: list[dict] = []
    search_queries = build_arxiv_queries(query)[:8]
    per_query = max(3, min(max_results, 20))
    with ThreadPoolExecutor(max_workers=min(4, len(search_queries) or 1)) as executor:
        futures = {
            executor.submit(_fetch_arxiv, search_query, per_query, timeout): search_query
            for search_query in search_queries
        }
        for future in as_completed(futures):
            if len(all_works) >= max_results:
                break
            try:
                works = future.result()
            except Exception:
                continue
            for work in works:
                if work["work_id"] in seen:
                    continue
                seen.add(work["work_id"])
                all_works.append(work)
                if len(all_works) >= max_results:
                    break
    if len(all_works) < max_results:
        for search_query in search_queries[8:]:
            if len(all_works) >= max_results:
                break
            try:
                works = _fetch_arxiv(search_query, max_results=max_results, timeout=timeout)
            except Exception:
                continue
            for work in works:
                if work["work_id"] in seen:
                    continue
                seen.add(work["work_id"])
                all_works.append(work)
                if len(all_works) >= max_results:
                    break
    all_works.sort(key=lambda work: lexical_score(query, work["title"] + " " + work["abstract"]), reverse=True)
    return all_works[:max_results]


def _search_arxiv_sequential(query: str, max_results: int = 8, timeout: int = 12) -> list[dict]:
    seen: set[str] = set()
    all_works: list[dict] = []
    for search_query in build_arxiv_queries(query):
        try:
            works = _fetch_arxiv(search_query, max_results=max_results, timeout=timeout)
        except Exception:
            continue
        for work in works:
            if work["work_id"] in seen:
                continue
            seen.add(work["work_id"])
            all_works.append(work)
            if len(all_works) >= max_results:
                break
        if len(all_works) >= max_results:
            break
    all_works.sort(key=lambda work: lexical_score(query, work["title"] + " " + work["abstract"]), reverse=True)
    return all_works[:max_results]


def _fetch_arxiv(search_query: str, max_results: int, timeout: int) -> list[dict]:
    params = urllib.parse.urlencode(
        {
            "search_query": search_query,
            "start": 0,
            "max_results": max_results,
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
    )
    url = f"https://export.arxiv.org/api/query?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "Principia-demo/0.1 (local research demo)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            xml_text = resp.read()
    except Exception as exc:
        if "CERTIFICATE_VERIFY_FAILED" not in repr(exc):
            raise
        with urllib.request.urlopen(req, timeout=timeout, context=ssl._create_unverified_context()) as resp:
            xml_text = resp.read()
    root = ET.fromstring(xml_text)
    works: list[dict] = []
    for entry in root.findall("a:entry", ATOM):
        title = " ".join((entry.findtext("a:title", default="", namespaces=ATOM) or "").split())
        abstract = " ".join((entry.findtext("a:summary", default="", namespaces=ATOM) or "").split())
        published = entry.findtext("a:published", default="", namespaces=ATOM) or ""
        updated = entry.findtext("a:updated", default="", namespaces=ATOM) or published
        comment = " ".join((entry.findtext("arxiv:comment", default="", namespaces=ATOM) or "").split())
        journal_ref = " ".join((entry.findtext("arxiv:journal_ref", default="", namespaces=ATOM) or "").split())
        venue = _peer_reviewed_venue(comment, journal_ref) or "arXiv"
        year_match = re.match(r"(\d{4})", published)
        authors = [
            " ".join((author.findtext("a:name", default="", namespaces=ATOM) or "").split())
            for author in entry.findall("a:author", ATOM)
        ]
        url_or_doi = entry.findtext("a:id", default="", namespaces=ATOM) or ""
        works.append(
            to_dict(
                SourceWork(
                    work_id=stable_id("W", title, url_or_doi),
                    title=title or "Untitled arXiv work",
                    authors=[name for name in authors if name],
                    year=int(year_match.group(1)) if year_match else None,
                    venue_or_source=venue,
                    url_or_doi=url_or_doi,
                    source_type="paper",
                    validation_level="L1",
                    abstract=compact_text(abstract, 1800),
                    source_updated_at=updated,
                )
            )
        )
    return works


def _peer_reviewed_venue(*texts: str) -> str:
    text = " ".join(texts)
    if not text:
        return ""
    venues = [
        "NeurIPS",
        "ICML",
        "ICLR",
        "CVPR",
        "ICCV",
        "ECCV",
        "ACL",
        "EMNLP",
        "NAACL",
        "COLM",
        "KDD",
        "WWW",
        "SIGIR",
        "AAAI",
        "IJCAI",
        "Nature",
        "Science",
        "TMLR",
        "JMLR",
        "TPAMI",
    ]
    for venue in venues:
        if re.search(rf"\b{re.escape(venue)}\b", text, flags=re.IGNORECASE):
            year = re.search(r"\b(20\d{2})\b", text)
            return f"{venue} {year.group(1)}" if year else venue
    return ""


def build_arxiv_query(query: str) -> str:
    return build_arxiv_queries(query)[0]


def build_arxiv_queries(query: str) -> list[str]:
    lower = enrich_query(query).lower().replace("_", " ")
    expansions = query_expansions(query)
    domain_queries: list[str] = []
    if any("3d reconstruction" in phrase for phrase in expansions):
        domain_queries.extend(
            [
                'all:"sparse view" AND all:"3d reconstruction"',
                'all:"few view" AND all:"3d reconstruction"',
                'all:"limited view" AND all:"3d reconstruction"',
                'all:"neural radiance fields" AND all:"sparse view"',
                'all:"3d gaussian splatting" AND all:"sparse view"',
                'all:"multi view stereo" AND all:sparse',
                'all:"3d reconstruction" AND all:sparse',
                'all:"novel view synthesis" AND all:"3d reconstruction"',
                'all:"3d gaussian splatting"',
                'all:"neural radiance fields"',
            ]
        )
    mas_like = any(
        term in lower
        for term in [
            "mas",
            "multi-agent",
            "multi agent",
            "llm agent",
            "agent communication",
            "machine dialect",
            "scientific discovery",
            "intrinsic reward",
            "symbolic compactness",
            "token efficient reasoning",
        ]
    )
    if mas_like:
        domain_queries.extend(
            [
                'all:"multi-agent" AND all:"large language model"',
                'all:"LLM agents" AND all:"scientific discovery"',
                'all:"scientific discovery" AND all:"large language model"',
                'all:"intrinsic reward" AND all:agent',
                'all:"symbolic reasoning" AND all:"scientific discovery"',
                'all:"minimum description length" AND all:"symbolic"',
                'all:"agent communication" AND all:"large language model"',
                'all:"token efficient" AND all:"reasoning"',
                'all:"multi-agent debate" AND all:"reasoning"',
                'all:"emergent communication" AND all:agent',
            ]
        )
    vision_like = any(
        term in lower
        for term in [
            "few-shot",
            "few shot",
            "test-time training",
            "test time training",
            "test-time adaptation",
            "clip",
            "vision-language",
            "vision transformer",
            "vit",
            "prompt learning",
            "parameter-efficient tuning",
        ]
    )
    if vision_like:
        domain_queries.extend(
            [
                'all:"test-time training" AND all:CLIP',
                'all:"test-time adaptation" AND all:CLIP',
                'all:"few-shot learning" AND all:CLIP',
                'all:"few-shot" AND all:"vision-language model"',
                'all:"prompt learning" AND all:CLIP',
                'all:"parameter-efficient tuning" AND all:"Vision Transformer"',
                'all:"visual recognition" AND all:"test-time adaptation"',
                'all:"few-shot image classification"',
                'all:"CLIP" AND all:"ImageNet"',
            ]
        )
    clauses: list[str] = []
    if "long-context" in lower or "long context" in lower:
        clauses.append('all:"long context"')
    if "llm" in lower or "large language" in lower or "language model" in lower:
        clauses.append('all:"large language model"')
    elif "mas" in lower or "multi-agent" in lower or "multi agent" in lower:
        clauses.append('all:"multi-agent"')
    elif "agent" in lower:
        clauses.append("all:agent")
    if "scientific discovery" in lower and not any("scientific discovery" in clause for clause in clauses):
        clauses.append('all:"scientific discovery"')
    if "machine dialect" in lower or "dialect" in lower:
        clauses.append('all:"agent communication"')
    if "symbolic compactness" in lower:
        clauses.append('all:"symbolic reasoning"')
    if "clip" in lower and not any("clip" in clause.lower() for clause in clauses):
        clauses.append("all:CLIP")
    if "test-time training" in lower or "test time training" in lower or "ttt" in lower:
        clauses.append('all:"test-time training"')
    if "few-shot" in lower or "few shot" in lower:
        clauses.append('all:"few-shot learning"')
    terms = [term for term in keyword_terms(lower, 8) if term not in QUERY_STOPWORDS]
    for term in terms:
        normalized = term.replace("-", " ")
        if any(normalized in clause for clause in clauses):
            continue
        if term in {"agents", "agent"} and any("large language model" in clause for clause in clauses):
            continue
        if mas_like and term in {"compactness", "completion"}:
            continue
        if vision_like and term in {"benchmark", "baseline", "datasets", "dataset", "cvpr2026"}:
            continue
        clauses.append(f"all:{term}")
        if len(clauses) >= 3:
            break
    if not clauses:
        clauses = [f"all:{term}" for term in terms[:3]] or ["all:research"]
    queries: list[str] = list(domain_queries)
    if len(clauses) >= 2:
        queries.append(" AND ".join(clauses[:2]))
    queries.append(" AND ".join(clauses[:3]))
    if terms:
        queries.append(" AND ".join(f"all:{term}" for term in terms[:2]))
        queries.append("all:" + terms[0])
    queries.append("all:large language model")
    deduped: list[str] = []
    for item in queries:
        if item and item not in deduped:
            deduped.append(item)
    return deduped


def fallback_seed_work(query: str) -> list[dict]:
    lower = enrich_query(query).lower()
    normalized = lower.replace("-", " ")
    if "3d reconstruction" in normalized and (
        "sparse view" in normalized or "few view" in normalized or "limited view" in normalized
    ):
        seed_specs = [
            (
                "Seed note: uncertainty-gated priors for sparse-view 3D reconstruction",
                (
                    "Sparse-view 3D reconstruction is underconstrained because limited input views provide uneven "
                    "cross-view coverage and uncertain camera/geometry evidence. A practical mechanism is to estimate "
                    "per-region uncertainty from reprojection disagreement, opacity entropy, or view coverage, then apply "
                    "stronger geometric or generative priors only where observed evidence is weak. The expected benefit is "
                    "higher held-out view quality while reducing hallucinated geometry in well-observed regions."
                ),
            ),
            (
                "Seed note: cycle-filtered pseudo-view curriculum for few-view reconstruction",
                (
                    "Few-view reconstruction can benefit from generated pseudo-views, but unfiltered pseudo-views can poison "
                    "training with plausible but inconsistent surfaces. A useful mechanism is a curriculum that starts near "
                    "observed viewpoints, projects candidate pseudo-views back to real views, and accepts them only when they "
                    "pass cycle-consistency diagnostics. This improves sparse-view augmentation by tying data growth to a "
                    "cheap geometry check."
                ),
            ),
            (
                "Seed note: structural anchors for limited-view Gaussian initialization",
                (
                    "Limited-view reconstruction often fails before optimization converges because poor initialization creates "
                    "floaters, pose ambiguity, and local minima. A transferable mechanism is to infer sparse planes, depth-order "
                    "anchors, or correspondence hypotheses from the input views, seed Gaussians or density fields around those "
                    "anchors, and relax the constraints after early training. The mechanism should be validated with held-out "
                    "views, convergence curves, and failure-case inspection."
                ),
            ),
        ]
        return [_seed_work(title, abstract) for title, abstract in seed_specs]
    if any(
        term in normalized
        for term in [
            "mas",
            "multi agent",
            "multi-agent",
            "llm agents",
            "scientific discovery",
            "machine dialect",
            "symbolic compactness",
            "intrinsic reward",
        ]
    ):
        seed_specs = [
            (
                "Seed note: symbolic compactness as a discovery reward for LLM agent societies",
                (
                    "For multi-agent scientific discovery, symbolic compactness should not mean short text. It should mean "
                    "that a hypothesis, mechanism, or experimental rule can be compressed into a small set of reusable "
                    "symbols without losing predictive commitments. An intrinsic reward can therefore favor agents whose "
                    "proposals reduce description length while preserving falsifiable consequences, making compactness a "
                    "pressure toward law-like explanations rather than terse summaries."
                ),
            ),
            (
                "Seed note: machine dialects as typed social contracts between reasoning agents",
                (
                    "LLM agents can reduce token cost and improve reasoning accuracy by interacting through constrained "
                    "machine dialects: compact claim handles, evidence pointers, uncertainty marks, and required rebuttal "
                    "slots. The dialect acts like a social protocol. It preserves disagreement and provenance while avoiding "
                    "full natural-language restatement at every turn, so reasoning can become both cheaper and easier to audit."
                ),
            ),
            (
                "Seed note: scientific MAS should reward irreducible disagreement, not verbose consensus",
                (
                    "A useful agent society for discovery should treat disagreement as information until it has been compressed "
                    "into a precise crux. Agents should be rewarded for converting long debate into minimal symbolic conflicts: "
                    "which assumption, variable, or experiment would decide the issue. This turns social interaction into a "
                    "mechanism for finding the shortest decisive experiment."
                ),
            ),
        ]
        return [_seed_work(title, abstract) for title, abstract in seed_specs]
    if any(
        term in normalized
        for term in [
            "few shot",
            "few-shot",
            "test time training",
            "test-time training",
            "test time adaptation",
            "test-time adaptation",
            "clip",
            "vision-language",
            "vision model",
            "视觉模型",
            "小样本",
            "少样本",
            "4090",
        ]
    ):
        seed_specs = [
            (
                "Seed note: resource-aware test-time training for CLIP few-shot recognition",
                (
                    "Few-shot visual recognition with CLIP is attractive under limited GPUs, but naive test-time training can spend "
                    "too much compute per query and overfit the test distribution. A practical mechanism is to adapt only lightweight "
                    "prompt, adapter, normalization, or projection parameters at test time, with an early-stop signal based on prediction "
                    "stability and entropy. The method should be evaluated against CoOp, CoCoOp, Tip-Adapter, TPT, and zero-shot CLIP on "
                    "datasets such as ImageNet, Caltech101, OxfordPets, Food101, DTD, EuroSAT, UCF101, and SUN397."
                ),
            ),
            (
                "Seed note: benchmark-first design for 4-8 RTX 4090 CLIP adaptation",
                (
                    "When the compute budget is 4-8 RTX 4090 GPUs, the central contribution should not be a large retraining recipe. "
                    "A stronger strategy is to define a reproducible benchmark matrix first: datasets, shots, base-to-novel splits, "
                    "domain-shift settings, adaptation budget per image, memory cost, and wall-clock cost. The method then earns novelty "
                    "by improving accuracy-cost tradeoffs under this matrix rather than by adding a heavy module."
                ),
            ),
            (
                "Seed note: ViT-style test-time token selection for few-shot CLIP",
                (
                    "Vision Transformer features contain patch tokens that differ in task relevance. A test-time training method can update "
                    "a tiny token selector or prompt router so only reliable visual tokens influence CLIP alignment under few-shot supervision. "
                    "The key is to prevent test-time updates from corrupting class semantics while still allowing image-specific evidence to "
                    "reshape the visual representation."
                ),
            ),
        ]
        return [_seed_work(title, abstract) for title, abstract in seed_specs]

    title = f"Seed research note for: {query[:90]}"
    abstract = (
        "Offline seed generated because no external corpus result was available. "
        "Use it only to exercise the pipeline; replace with arXiv or local paper ingestion for real work. "
        f"The target problem is {query}."
    )
    return [_seed_work(title, abstract)]


def _seed_work(title: str, abstract: str) -> dict:
    return to_dict(
        SourceWork(
            work_id=stable_id("W", title, abstract),
            title=title,
            authors=["Principia demo"],
            year=None,
            venue_or_source="local seed",
            url_or_doi="",
            source_type="note",
            validation_level="L0",
            abstract=abstract,
        )
    )
