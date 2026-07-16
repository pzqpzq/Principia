from __future__ import annotations

import inspect
import math
import re
from collections import Counter
from typing import Any

from .constants import RELATION_ORDER
from .embeddings import (
    SiliconFlowEmbeddingClient,
    embedding_cache_key,
    validate_embedding_vectors,
)
from .models import QueryPlan, control_check_cancelled, control_checkpoint
from .utils import (
    clamp_float,
    clean_text,
    normalize_text,
    stable_id,
    tokenize,
    truncate,
    weighted_tokens,
)


def deterministic_rank(
    goal_text: str, works: list[dict[str, Any]], plan: QueryPlan
) -> list[dict[str, Any]]:
    scored = []
    goal_tokens = weighted_tokens(goal_text)
    citation_scores = cohort_normalized_citations(works)
    entity_weights = entity_specificity_weights(works, plan)
    for index, work in enumerate(works):
        item = dict(work)
        body = work_text(item)
        relevance = semantic_lite_score(
            goal_text,
            body,
            plan,
            goal_tokens=goal_tokens,
            entity_weights=entity_weights,
        )
        metadata = metadata_score(item, citation_score=citation_scores[index])
        exact_score = exact_entity_score(item, plan, entity_weights)
        exact_bonus = exact_score * 0.18
        aspect_score = query_aspect_score(item, plan)
        facet_score = goal_facet_score(item, plan)
        assessability = abstract_assessability_score(item)
        final = max(
            0.0,
            relevance * 0.66
            + aspect_score * 0.18
            + facet_score * 0.06
            + metadata
            + exact_bonus
            - (1.0 - assessability) * 0.035,
        )
        relation = relation_from_score(final, exact_bonus, relevance)
        item["_retrieval_score"] = final
        item["_aspect_coverage_score"] = aspect_score
        item["_goal_facet_score"] = facet_score
        item["_abstract_assessability_score"] = assessability
        item["_exact_entity_score"] = exact_score
        item["relation_label"] = relation
        item["retrieval_rationale"] = deterministic_rationale(item, plan, relevance, exact_bonus)
        item["reject_reason"] = ""
        item.setdefault("community_signals", {})["retrieval_score"] = round(final, 4)
        item.setdefault("community_signals", {})["relation_label"] = relation
        item.setdefault("community_signals", {})["goal_facet_score"] = round(facet_score, 4)
        item.setdefault("community_signals", {})["abstract_assessability_score"] = round(
            assessability, 4
        )
        scored.append(item)
    scored.sort(
        key=lambda item: (
            -float(item.get("_retrieval_score", 0.0)),
            -relation_rank(item),
            -safe_year(item),
            stable_rank_identity(item),
        )
    )
    return scored


def bm25_rank(goal_text: str, works: list[dict[str, Any]], plan: QueryPlan) -> list[dict[str, Any]]:
    docs = [tokenize(work_text(work)) for work in works]
    if not works:
        return []
    query_tokens = bm25_query_tokens(goal_text, plan)
    if not query_tokens:
        return deterministic_rank(goal_text, works, plan)
    doc_freq: Counter[str] = Counter()
    total_len = 0
    for tokens in docs:
        total_len += len(tokens)
        doc_freq.update(set(tokens))
    avg_len = total_len / max(1, len(docs))
    raw_scores = bm25_scores(docs, query_tokens, doc_freq=doc_freq, avg_len=avg_len)
    max_bm25 = max(raw_scores) if raw_scores else 0.0
    goal_tokens = weighted_tokens(goal_text)
    citation_scores = cohort_normalized_citations(works)
    entity_weights = entity_specificity_weights(works, plan)
    scored = []
    for index, (work, raw_score) in enumerate(zip(works, raw_scores, strict=True)):
        item = dict(work)
        body = work_text(item)
        relevance = semantic_lite_score(
            goal_text,
            body,
            plan,
            goal_tokens=goal_tokens,
            entity_weights=entity_weights,
        )
        metadata = metadata_score(item, citation_score=citation_scores[index])
        exact_score = exact_entity_score(item, plan, entity_weights)
        exact_bonus = exact_score * 0.18
        bm25_norm = raw_score / max_bm25 if max_bm25 > 0 else 0.0
        source_prior = source_prior_score(item)
        aspect_score = query_aspect_score(item, plan)
        facet_score = goal_facet_score(item, plan)
        query_support = query_support_score(item, plan)
        assessability = abstract_assessability_score(item)
        final = max(
            0.0,
            bm25_norm * 0.47
            + relevance * 0.2
            + aspect_score * 0.12
            + facet_score * 0.05
            + source_prior * 0.03
            + query_support * 0.03
            # Metadata is a confidence signal, not a substitute for topical
            # relevance.  Scaling it prevents a cohort citation or venue
            # completeness advantage from overturning a materially stronger
            # lexical match.
            + metadata * 0.35
            + exact_bonus
            - (1.0 - assessability) * 0.035,
        )
        relation = relation_from_score(final, exact_bonus, max(relevance, bm25_norm * 0.35))
        item["_retrieval_score"] = final
        item["_bm25_score"] = raw_score
        item["_bm25_normalized_score"] = bm25_norm
        item["_source_prior_score"] = source_prior
        item["_aspect_coverage_score"] = aspect_score
        item["_goal_facet_score"] = facet_score
        item["_query_support_score"] = query_support
        item["_evidence_quality_score"] = evidence_quality_score(item)
        item["_abstract_assessability_score"] = assessability
        item["_exact_entity_score"] = exact_score
        item["relation_label"] = relation
        item["retrieval_rationale"] = bm25_rationale(
            item, plan, raw_score, relevance, source_prior, exact_bonus
        )
        item["reject_reason"] = ""
        signals = item.setdefault("community_signals", {})
        signals["bm25_score"] = round(raw_score, 4)
        signals["source_prior_score"] = round(source_prior, 4)
        signals["aspect_coverage_score"] = round(aspect_score, 4)
        signals["goal_facet_score"] = round(facet_score, 4)
        signals["query_support_score"] = round(query_support, 4)
        signals["evidence_quality_score"] = round(item["_evidence_quality_score"], 4)
        signals["abstract_assessability_score"] = round(assessability, 4)
        signals["retrieval_score"] = round(final, 4)
        signals["relation_label"] = relation
        scored.append(item)
    scored.sort(
        key=lambda item: (
            -float(item.get("_retrieval_score", 0.0)),
            -relation_rank(item),
            -safe_year(item),
            stable_rank_identity(item),
        )
    )
    return scored


def bm25_scores(
    docs: list[list[str]],
    query_tokens: list[str],
    *,
    doc_freq: Counter[str],
    avg_len: float,
) -> list[float]:
    total_docs = max(1, len(docs))
    query_counts = Counter(query_tokens)
    k1 = 1.35
    b = 0.75
    output = []
    for tokens in docs:
        counts = Counter(tokens)
        doc_len = len(tokens) or 1
        score = 0.0
        for token, query_freq in query_counts.items():
            freq = counts.get(token, 0)
            if not freq:
                continue
            df = max(1, doc_freq.get(token, 0))
            idf = math.log(1.0 + (total_docs - df + 0.5) / (df + 0.5))
            denom = freq + k1 * (1.0 - b + b * doc_len / max(avg_len, 1.0))
            query_weight = 1.0 + min(1.5, math.log1p(query_freq))
            score += idf * ((freq * (k1 + 1.0)) / denom) * query_weight
        output.append(score)
    return output


def bm25_query_tokens(goal_text: str, plan: QueryPlan) -> list[str]:
    pieces = [
        goal_text,
        *plan.search_queries[:8],
        *plan.entities,
        *plan.key_phrases[:12],
    ]
    tokens: list[str] = []
    for piece in pieces:
        tokens.extend(tokenize(piece))
    return tokens


def source_prior_score(work: dict[str, Any]) -> float:
    signals = work.get("community_signals") or work.get("metadata") or {}
    if not isinstance(signals, dict):
        signals = {}
    score_candidates = []
    for key in ["benchmark_bm25_score", "source_score", "relevance_score", "score"]:
        raw_value = signals.get(key)
        if raw_value is None:
            continue
        try:
            value = float(raw_value)
        except Exception:
            continue
        if value > 0:
            score_candidates.append(min(1.0, math.log1p(value) / 8.0))
    try:
        rank = int(signals.get("source_rank") or 0)
    except Exception:
        rank = 0
    rank_score = 1.0 / math.sqrt(rank) if rank > 0 else 0.0
    return max([0.0, rank_score, *score_candidates])


def query_aspect_score(work: dict[str, Any], plan: QueryPlan) -> float:
    queries = distinct_aspect_queries(plan)
    if not queries:
        return 0.0
    query_sets = [set(tokenize(query)) for query in queries]
    document_tokens = set(tokenize(work_text(work)))
    document_frequency: Counter[str] = Counter(token for tokens in query_sets for token in tokens)
    total_queries = len(query_sets)
    scores: list[float] = []
    for tokens in query_sets:
        weights = {
            token: math.log(1.0 + (total_queries + 1.0) / (document_frequency[token] + 0.5))
            for token in tokens
        }
        matched = tokens & document_tokens
        coverage = sum(weights[token] for token in matched) / max(1e-9, sum(weights.values()))
        # A single ambiguous word (for example "compression") is not enough
        # evidence that a work addresses a complete research aspect.
        coverage *= min(1.0, len(matched) / 2.0)
        scores.append(coverage)
    scores.sort(reverse=True)
    breadth = sum(scores[:3]) / min(3, len(scores))
    return clamp_float(scores[0] * 0.55 + breadth * 0.45, 0.0, 1.0)


def query_support_score(work: dict[str, Any], plan: QueryPlan) -> float:
    signals = work.get("community_signals") or work.get("metadata") or {}
    if not isinstance(signals, dict):
        return 0.0
    matched_queries = signals.get("matched_queries") or []
    if isinstance(matched_queries, str):
        matched_queries = [matched_queries]
    planned = {normalize_text(query) for query in distinct_aspect_queries(plan)}
    matched = {normalize_text(query) for query in matched_queries if normalize_text(query)}
    count = len(planned & matched) if planned else len(matched)
    count_score = min(1.0, count / min(4, max(1, len(planned))))
    ranks = []
    for rank in dict(signals.get("source_query_ranks") or {}).values():
        try:
            ranks.append(max(1, int(rank)))
        except (TypeError, ValueError):
            continue
    rank_score = max((1.0 / math.sqrt(rank) for rank in ranks), default=0.0)
    return count_score * 0.7 + rank_score * 0.3


def distinct_aspect_queries(plan: QueryPlan) -> list[str]:
    goal_key = normalize_text(plan.goal_text)
    output: list[str] = []
    seen = {goal_key}
    for query in [*plan.search_queries, *plan.complementary_intents]:
        text = clean_text(query)
        key = normalize_text(text)
        if text and key and key not in seen:
            output.append(text)
            seen.add(key)
        if len(output) >= 8:
            break
    return output


def entity_specificity_weights(works: list[dict[str, Any]], plan: QueryPlan) -> dict[str, float]:
    output: dict[str, float] = {}
    bodies = [normalize_text(work_text(work)) for work in works]
    for entity in plan.entities:
        normalized = normalize_text(entity)
        if not normalized:
            continue
        prevalence = sum(normalized in body for body in bodies) / max(1, len(bodies))
        compact = recompact(normalized)
        identifier_like = any(character.isdigit() for character in compact) and len(compact) >= 5
        intrinsic = 1.0 if identifier_like or " " in normalized or len(compact) >= 5 else 0.2
        prevalence_weight = clamp_float((0.55 - prevalence) / 0.45, 0.0, 1.0)
        output[normalized] = 1.0 if identifier_like else intrinsic * prevalence_weight
    return output


def exact_entity_score(
    work: dict[str, Any], plan: QueryPlan, entity_weights: dict[str, float] | None = None
) -> float:
    text = normalize_text(work_text(work))
    weights = entity_weights or entity_specificity_weights([work], plan)
    return max(
        [weight for entity, weight in weights.items() if entity and entity in text],
        default=0.0,
    )


def recompact(value: str) -> str:
    return "".join(character for character in value if character.isalnum())


def evidence_quality_score(work: dict[str, Any]) -> float:
    abstract = min(1.0, len(clean_text(work.get("abstract") or "")) / 800.0)
    title = min(1.0, len(clean_text(work.get("title") or "")) / 40.0)
    authors = 1.0 if work.get("authors") else 0.0
    year = 1.0 if work.get("year") else 0.0
    identifier = (
        1.0
        if any(
            work.get(key)
            for key in ["doi", "arxiv_id", "openalex_id", "semantic_scholar_id", "pmid"]
        )
        else 0.0
    )
    venue = venue_quality(str(work.get("venue_or_source") or ""))
    link = 1.0 if work.get("url_or_doi") or work.get("source_urls") else 0.0
    return (
        abstract * 0.62
        + title * 0.05
        + authors * 0.08
        + year * 0.06
        + identifier * 0.08
        + venue * 0.06
        + link * 0.05
    )


_GOAL_FACET_SPLIT = re.compile(
    r"\s+(?:and|combining|for|through|under|using|via|while|with|without)\s+|[,;]",
    flags=re.I,
)
_GOAL_INTENT_TOKENS = {
    "aim",
    "build",
    "create",
    "design",
    "develop",
    "identify",
    "investigate",
    "preserve",
    "preserving",
    "prevent",
    "preventing",
    "propose",
    "study",
}


def goal_facet_score(work: dict[str, Any], plan: QueryPlan) -> float:
    """Measure lexical support for the core objective and its distinct facets.

    Embeddings remain the primary semantic signal.  This small, domain-neutral
    feature prevents a generic application that mentions only the broad field
    from outranking a work that materially covers a named method, constraint,
    failure mode, control, or observable. No discipline-specific vocabulary is
    added, and semantic paraphrases remain the embedding model's responsibility.
    """

    groups = goal_facet_groups(plan.goal_text)
    if not groups:
        return 0.0
    document_tokens = set(tokenize(work_text(work)))
    coverages = [weighted_group_coverage(group, document_tokens) for group in groups]
    if len(coverages) == 1:
        return coverages[0]
    primary = coverages[0]
    supporting = max(coverages[1:], default=0.0)
    strongest = sorted(coverages, reverse=True)[:2]
    breadth = sum(strongest) / len(strongest)
    return clamp_float(primary * 0.42 + supporting * 0.38 + breadth * 0.20, 0.0, 1.0)


def goal_facet_groups(goal_text: str) -> list[dict[str, float]]:
    groups: list[dict[str, float]] = []
    for chunk in _GOAL_FACET_SPLIT.split(clean_text(goal_text)):
        weights = {
            token: weight
            for token, weight in weighted_tokens(chunk).items()
            if token not in _GOAL_INTENT_TOKENS
        }
        if weights:
            groups.append(weights)
    return groups


def weighted_group_coverage(group: dict[str, float], document_tokens: set[str]) -> float:
    matched = {token for token in group if token in document_tokens}
    if not matched:
        return 0.0
    weighted = sum(group[token] for token in matched) / max(1e-9, sum(group.values()))
    # One ambiguous token from a multi-token facet is weak evidence.  A
    # genuinely atomic facet may still be fully supported by its single term.
    minimum_matches = min(2, len(group))
    return clamp_float(weighted * min(1.0, len(matched) / minimum_matches), 0.0, 1.0)


def abstract_assessability_score(work: dict[str, Any]) -> float:
    """Confidence that relevance can be assessed beyond a title-only hit."""

    return clamp_float(len(clean_text(work.get("abstract") or "")) / 400.0, 0.0, 1.0)


def stratified_embedding_candidates(
    works: list[dict[str, Any]], limit: int, plan: QueryPlan
) -> list[dict[str, Any]]:
    """Keep high-relevance works while reserving room for every query facet.

    A single aggregate BM25 list can omit a specialized but essential method.
    This pool starts with the strongest overall half, then round-robins through
    complementary query facets and providers before filling by overall score.
    """

    limit = min(len(works), max(0, int(limit)))
    if limit <= 0:
        return []
    ordered_works = sorted(
        works,
        key=lambda work: (
            -float(work.get("_retrieval_score", 0.0)),
            -relation_rank(work),
            -safe_year(work),
            stable_rank_identity(work),
        ),
    )
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(work: dict[str, Any]) -> None:
        key = selection_key(work)
        if key not in seen and len(selected) < limit:
            selected.append(work)
            seen.add(key)

    for work in ordered_works[: max(1, limit // 2)]:
        add(work)

    aspect_queries = distinct_aspect_queries(plan)
    per_aspect = max(2, limit // max(1, len(aspect_queries) * 3))
    for query in aspect_queries:
        ranked = sorted(
            ordered_works,
            key=lambda work: (
                -single_query_coverage(work, query),
                -float(work.get("_retrieval_score", 0.0)),
                stable_rank_identity(work),
            ),
        )
        for work in ranked[:per_aspect]:
            add(work)

    sources = sorted(
        {
            clean_text(work.get("source") or "")
            for work in ordered_works
            if clean_text(work.get("source") or "")
        }
    )
    per_source = max(1, limit // max(1, len(sources) * 10))
    for source in sources:
        for work in [
            item for item in ordered_works if clean_text(item.get("source") or "") == source
        ][:per_source]:
            add(work)

    for work in ordered_works:
        add(work)
    return selected


def single_query_coverage(work: dict[str, Any], query: str) -> float:
    query_tokens = set(tokenize(query))
    if not query_tokens:
        return 0.0
    matched = query_tokens & set(tokenize(work_text(work)))
    return len(matched) / len(query_tokens) * min(1.0, len(matched) / 2.0)


def embedding_rerank(
    goal_text: str,
    works: list[dict[str, Any]],
    plan: QueryPlan,
    *,
    model: str,
    dimensions: int,
    batch_size: int,
    timeout: float = 30.0,
    max_retries: int = 2,
    embedding_client: Any | None = None,
    cache: dict[str, list[float]] | None = None,
    control_token: Any | None = None,
) -> list[dict[str, Any]]:
    by_id = {
        str(work.get("work_id") or stable_id("W", work.get("title", ""))): dict(work)
        for work in works
    }
    rows = list(by_id.values())
    if not rows:
        return []
    client = embedding_client or SiliconFlowEmbeddingClient(
        model=model,
        dimensions=dimensions,
        timeout=timeout,
        max_retries=max_retries,
    )
    cache = {} if cache is None else cache
    query_texts = [
        query_embedding_text(goal_text, plan),
        *aspect_query_embedding_texts(goal_text, plan),
    ]
    corpus_texts = [work_embedding_text(work) for work in rows]
    try:
        vectors = embed_texts_cached(
            [*query_texts, *corpus_texts],
            client,
            model=model,
            dimensions=dimensions,
            batch_size=batch_size,
            timeout=timeout,
            cache=cache,
            control_token=control_token,
        )
    except Exception as exc:  # noqa: BLE001
        control_check_cancelled(control_token)
        return embedding_fallback(rows, exc, model=model, dimensions=dimensions)
    query_vectors = vectors[: len(query_texts)]
    work_vectors = vectors[len(query_texts) :]
    output = []
    citation_scores = cohort_normalized_citations(rows)
    for index, (work, vector) in enumerate(zip(rows, work_vectors, strict=True)):
        item = dict(work)
        goal_similarity = clamp_float(cosine_similarity(query_vectors[0], vector), 0.0, 1.0)
        aspect_similarities = sorted(
            [
                clamp_float(cosine_similarity(query_vector, vector), 0.0, 1.0)
                for query_vector in query_vectors[1:]
            ],
            reverse=True,
        )
        if aspect_similarities:
            aspect_similarity = aspect_similarities[0]
            aspect_breadth = sum(aspect_similarities[:3]) / min(3, len(aspect_similarities))
            similarity = goal_similarity * 0.5 + aspect_similarity * 0.35 + aspect_breadth * 0.15
        else:
            aspect_similarity = goal_similarity
            aspect_breadth = goal_similarity
            similarity = goal_similarity
        bm25_norm = clamp_float(item.get("_bm25_normalized_score", 0.0), 0.0, 1.0)
        lexical_aspect = clamp_float(
            item.get("_aspect_coverage_score", query_aspect_score(item, plan)), 0.0, 1.0
        )
        facet_score = clamp_float(
            item.get("_goal_facet_score", goal_facet_score(item, plan)), 0.0, 1.0
        )
        quality = evidence_quality_score(item)
        assessability = abstract_assessability_score(item)
        support = clamp_float(
            item.get("_query_support_score", query_support_score(item, plan)), 0.0, 1.0
        )
        exact_score = clamp_float(item.get("_exact_entity_score", 0.0), 0.0, 1.0)
        metadata = metadata_score(item, citation_score=citation_scores[index])
        final = max(
            0.0,
            similarity * 0.63
            + bm25_norm * 0.14
            + lexical_aspect * 0.08
            + facet_score * 0.04
            + quality * 0.07
            + support * 0.025
            + min(0.015, metadata * 0.12)
            + exact_score * 0.025
            - (1.0 - assessability) * 0.035,
        )
        relation = relation_from_embedding_similarity(similarity, exact_score > 0.5)
        item["_retrieval_score"] = final
        item["_embedding_similarity"] = similarity
        item["_embedding_goal_similarity"] = goal_similarity
        item["_embedding_aspect_similarity"] = aspect_similarity
        item["_embedding_aspect_breadth"] = aspect_breadth
        item["_evidence_quality_score"] = quality
        item["_goal_facet_score"] = facet_score
        item["_abstract_assessability_score"] = assessability
        item["relation_label"] = relation
        item["retrieval_rationale"] = embedding_rationale(
            item,
            similarity,
            aspect_similarity=aspect_similarity,
            quality=quality,
        )
        item["reject_reason"] = ""
        signals = item.setdefault("community_signals", {})
        signals["embedding_similarity"] = round(similarity, 4)
        signals["embedding_goal_similarity"] = round(goal_similarity, 4)
        signals["embedding_aspect_similarity"] = round(aspect_similarity, 4)
        signals["embedding_aspect_breadth"] = round(aspect_breadth, 4)
        signals["goal_facet_score"] = round(facet_score, 4)
        signals["abstract_assessability_score"] = round(assessability, 4)
        signals["embedding_model"] = model
        signals["embedding_dimensions"] = int(dimensions or 0)
        signals["retrieval_score"] = round(final, 4)
        signals["relation_label"] = relation
        output.append(item)
    output.sort(
        key=lambda item: (
            -float(item.get("_retrieval_score", 0.0)),
            -relation_rank(item),
            -safe_year(item),
            stable_rank_identity(item),
        )
    )
    return output


def embed_texts_cached(
    texts: list[str],
    client: Any,
    *,
    model: str,
    dimensions: int,
    batch_size: int,
    timeout: float,
    cache: dict[str, list[float]],
    control_token: Any | None = None,
) -> list[list[float]]:
    control_checkpoint(control_token)
    keys = [embedding_cache_key(model, dimensions, text) for text in texts]
    missing: list[tuple[str, str]] = []
    seen_missing = set()
    for key, text in zip(keys, texts, strict=True):
        if key in cache or key in seen_missing:
            continue
        missing.append((key, text))
        seen_missing.add(key)
    for index in range(0, len(missing), max(1, int(batch_size or 1))):
        control_checkpoint(control_token)
        batch = missing[index : index + max(1, int(batch_size or 1))]
        batch_vectors = call_embedding_client(
            client,
            [text for _, text in batch],
            model=model,
            dimensions=dimensions,
            timeout=timeout,
            control_token=control_token,
        )
        if len(batch_vectors) != len(batch):
            raise RuntimeError(
                f"Embedding client returned {len(batch_vectors)} vector(s), expected {len(batch)}."
            )
        validate_embedding_vectors(batch_vectors)
        for (key, _), vector in zip(batch, batch_vectors, strict=True):
            cache[key] = [float(value) for value in vector]
        control_checkpoint(control_token)
    return [cache[key] for key in keys]


def call_embedding_client(
    client: Any,
    texts: list[str],
    *,
    model: str,
    dimensions: int,
    timeout: float,
    control_token: Any | None = None,
) -> list[list[float]]:
    embed = getattr(client, "embed", None)
    if callable(embed):
        kwargs: dict[str, Any] = {
            "model": model,
            "dimensions": dimensions,
            "timeout": timeout,
            "control_token": control_token,
        }
        supported = _supported_kwargs(embed, kwargs)
        try:
            return embed(texts, **supported)
        except TypeError:
            # Preserve the v1.3.2 minimal ``embed(texts)`` adapter protocol.
            if supported:
                raise
            return embed(texts)
    if callable(client):
        kwargs = {
            "model": model,
            "dimensions": dimensions,
            "timeout": timeout,
            "control_token": control_token,
        }
        supported = _supported_kwargs(client, kwargs)
        try:
            return client(texts, **supported)
        except TypeError:
            if supported:
                raise
            return client(texts)
    raise RuntimeError("Embedding rerank requires an embedding client with an embed method.")


def _supported_kwargs(callable_object: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    try:
        parameters = inspect.signature(callable_object).parameters
    except (TypeError, ValueError):
        return kwargs
    if any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()):
        return kwargs
    return {name: value for name, value in kwargs.items() if name in parameters}


def embedding_fallback(
    rows: list[dict[str, Any]], error: Exception, *, model: str, dimensions: int
) -> list[dict[str, Any]]:
    message = truncate(str(error), 220)
    output = []
    for work in rows:
        item = dict(work)
        signals = item.setdefault("community_signals", {})
        signals["embedding_model"] = model
        signals["embedding_dimensions"] = int(dimensions or 0)
        signals["embedding_rerank_error"] = message
        if not clean_text(item.get("retrieval_rationale") or ""):
            item["retrieval_rationale"] = "BM25 fallback; embedding rerank unavailable"
        output.append(item)
    return output


def query_embedding_text(goal_text: str, plan: QueryPlan) -> str:
    goal = clean_text(goal_text or plan.goal_text)
    return (
        "Instruct: Retrieve scholarly work that directly addresses this research objective or provides an "
        "essential method, principle, evaluation, control, or failure analysis.\n"
        f"Query: {goal}"
    )


def aspect_query_embedding_texts(goal_text: str, plan: QueryPlan) -> list[str]:
    goal_key = normalize_text(goal_text)
    output: list[str] = []
    seen = {goal_key}
    for query in [*plan.search_queries, *plan.complementary_intents]:
        text = clean_text(query)
        key = normalize_text(text)
        if not text or not key or key in seen:
            continue
        output.append(
            "Instruct: Retrieve scholarly work that directly addresses or materially enables this research aspect.\n"
            f"Query: {text}"
        )
        seen.add(key)
        if len(output) >= 8:
            break
    return output


def work_embedding_text(work: dict[str, Any]) -> str:
    authors = work.get("authors") or []
    if not isinstance(authors, list):
        authors = []
    rows = [
        ("title", clean_text(work.get("title") or "")),
        ("abstract", truncate(work.get("abstract") or "", 5000)),
        ("venue", clean_text(work.get("venue_or_source") or work.get("venue") or "")),
        ("year", clean_text(work.get("year") or "")),
        ("authors", "; ".join(clean_text(value) for value in authors[:10] if clean_text(value))),
        ("doi", clean_text(work.get("doi") or work.get("url_or_doi") or "")),
        ("source", clean_text(work.get("source") or "")),
    ]
    return "\n".join(f"{label}: {text}" for label, text in rows if text)


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    length = min(len(left), len(right))
    dot = sum(left[index] * right[index] for index in range(length))
    left_norm = math.sqrt(sum(value * value for value in left[:length]))
    right_norm = math.sqrt(sum(value * value for value in right[:length]))
    if left_norm <= 0 or right_norm <= 0:
        return 0.0
    return dot / (left_norm * right_norm)


def relation_from_embedding_similarity(similarity: float, exact_entity: bool) -> str:
    if exact_entity or similarity >= 0.66:
        return "direct"
    if similarity >= 0.58:
        return "background"
    if similarity >= 0.5:
        return "methodological"
    return "out_of_scope"


def embedding_rationale(
    work: dict[str, Any],
    similarity: float,
    *,
    aspect_similarity: float | None = None,
    quality: float | None = None,
) -> str:
    bits = [f"multi-aspect embedding relevance {similarity:.2f}"]
    if aspect_similarity is not None:
        bits.append(f"best research-aspect match {aspect_similarity:.2f}")
    if float(work.get("_bm25_score", 0.0) or 0.0) > 0:
        bits.append("BM25 prefilter match")
    if quality is not None and quality < 0.45:
        bits.append("limited assessable metadata")
    return "; ".join(bits[:3])


def final_select(
    works: list[dict[str, Any]], target_count: int, plan: QueryPlan
) -> list[dict[str, Any]]:
    eligible = []
    for work in works:
        label = normalize_relation(work.get("relation_label"))
        if label == "out_of_scope" and clean_text(work.get("reject_reason") or ""):
            continue
        if (
            label == "out_of_scope"
            and not has_exact_entity(work, plan)
            and float(work.get("_retrieval_score", 0.0)) < 0.18
        ):
            continue
        eligible.append(work)
    if len(eligible) < target_count:
        for work in works:
            if normalize_relation(work.get("relation_label")) == "out_of_scope" and clean_text(
                work.get("reject_reason") or ""
            ):
                continue
            if selection_key(work) in {selection_key(item) for item in eligible}:
                continue
            eligible.append(work)
            if len(eligible) >= target_count:
                break
    selected: list[dict[str, Any]] = []
    remaining = list(eligible)
    while remaining and len(selected) < target_count:
        ranked = []
        for work in remaining:
            novelty = diversity_novelty(work, selected)
            # Diversity is a tie-breaker inside a relevance-qualified pool; it
            # must not promote a topical tangent over a materially stronger hit.
            adjusted = float(work.get("_retrieval_score", 0.0)) * 0.98 + novelty * 0.02
            ranked.append(
                (
                    adjusted,
                    relation_rank(work),
                    safe_year(work),
                    normalize_text(work.get("title") or ""),
                    stable_rank_identity(work),
                    work,
                    novelty,
                )
            )
        _, _, _, _, _, chosen, novelty = min(
            ranked,
            key=lambda row: (
                -row[0],
                -row[1],
                -row[2],
                row[3],
                row[4],
            ),
        )
        signals = chosen.setdefault("community_signals", {})
        signals["diversity_score"] = round(novelty, 4)
        selected.append(chosen)
        remaining.remove(chosen)
    return selected[:target_count]


def semantic_lite_score(
    goal_text: str,
    text: str,
    plan: QueryPlan,
    *,
    goal_tokens: dict[str, float] | None = None,
    entity_weights: dict[str, float] | None = None,
) -> float:
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
    weights = entity_weights or entity_specificity_weights([], plan)
    for entity in plan.entities:
        normalized = normalize_text(entity)
        if normalized and normalized in body:
            entity_bonus += 0.12 * weights.get(normalized, 0.0)
    return min(1.0, coverage + min(0.3, phrase_bonus) + min(0.24, entity_bonus))


def metadata_score(work: dict[str, Any], *, citation_score: float = 0.0) -> float:
    year = int(work.get("year") or 0) if str(work.get("year") or "").isdigit() else 0
    recency = min(max(year - 2010, 0), 16) / 16 if year else 0.0
    venue = venue_quality(str(work.get("venue_or_source") or ""))
    abstract = min(1.0, len(clean_text(work.get("abstract") or "")) / 500.0)
    link = 1.0 if work.get("url_or_doi") or work.get("source_urls") else 0.0
    authors = 1.0 if work.get("authors") else 0.0
    identifier = (
        1.0
        if any(
            work.get(key)
            for key in ["doi", "arxiv_id", "openalex_id", "semantic_scholar_id", "pmid"]
        )
        else 0.0
    )
    return (
        recency * 0.01
        + citation_score * 0.02
        + venue * 0.01
        + abstract * 0.05
        + link * 0.005
        + authors * 0.01
        + identifier * 0.01
    )


def has_exact_entity(work: dict[str, Any], plan: QueryPlan) -> bool:
    if "_exact_entity_score" in work:
        return float(work.get("_exact_entity_score", 0.0) or 0.0) > 0.5
    text = normalize_text(work_text(work))
    return any(
        normalize_text(entity)
        and normalize_text(entity) in text
        and (
            any(character.isdigit() for character in recompact(normalize_text(entity)))
            or " " in normalize_text(entity)
            or len(recompact(normalize_text(entity))) >= 5
        )
        for entity in plan.entities
    )


def deterministic_rationale(
    work: dict[str, Any], plan: QueryPlan, relevance: float, exact_bonus: float
) -> str:
    bits = []
    if exact_bonus:
        bits.append("matches target entity")
    matched = [
        phrase
        for phrase in plan.key_phrases
        if normalize_text(phrase) and normalize_text(phrase) in normalize_text(work_text(work))
    ]
    if matched:
        bits.append("matches " + ", ".join(matched[:3]))
    if not bits:
        bits.append(f"lexical-semantic overlap {relevance:.2f}")
    return "; ".join(bits)


def bm25_rationale(
    work: dict[str, Any],
    plan: QueryPlan,
    raw_bm25: float,
    relevance: float,
    source_prior: float,
    exact_bonus: float,
) -> str:
    bits = []
    if exact_bonus:
        bits.append("matches target entity")
    matched = [
        phrase
        for phrase in plan.key_phrases
        if normalize_text(phrase) and normalize_text(phrase) in normalize_text(work_text(work))
    ]
    if matched:
        bits.append("matches " + ", ".join(matched[:3]))
    if raw_bm25 > 0:
        bits.append(f"BM25 lexical match {raw_bm25:.2f}")
    elif relevance > 0:
        bits.append(f"lexical-semantic overlap {relevance:.2f}")
    if source_prior >= 0.5:
        bits.append("ranked highly by source")
    if not bits:
        bits.append("low textual match")
    return "; ".join(bits[:3])


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
    if not value or value in {"arxiv", "openalex", "crossref", "semantic scholar", "europe pmc"}:
        return 0.0
    # Presence of a specific publication venue is a metadata-completeness
    # signal; no discipline or named venue receives a whitelist bonus.
    return min(1.0, 0.45 + len(value.split()) * 0.08)


def work_text(work: dict[str, Any]) -> str:
    return " ".join(str(work.get(key) or "") for key in ["title", "abstract", "venue_or_source"])


def selection_key(work: dict[str, Any]) -> str:
    return str(
        work.get("work_id") or stable_id("W", work.get("title", ""), work.get("url_or_doi", ""))
    )


def stable_rank_identity(work: dict[str, Any]) -> str:
    """Return a total-order identity for deterministic score tie-breaking."""

    strong = next(
        (
            f"{field}:{clean_text(work.get(field) or '').lower()}"
            for field in ["doi", "arxiv_id", "openalex_id", "semantic_scholar_id", "pmid"]
            if clean_text(work.get(field) or "")
        ),
        "",
    )
    return strong or normalize_text(selection_key(work))


def safe_year(work: dict[str, Any]) -> int:
    try:
        return int(work.get("year") or 0)
    except (TypeError, ValueError):
        return 0


def cohort_normalized_citations(works: list[dict[str, Any]]) -> list[float]:
    """Normalize citations within three-year publication cohorts.

    This prevents older/high-volume fields from dominating ranking while still
    retaining a small, comparable community signal across disciplines.
    """

    cohorts: dict[int, list[float]] = {}
    values: list[tuple[int, float]] = []
    for work in works:
        try:
            year = int(work.get("year") or 0)
        except (TypeError, ValueError):
            year = 0
        try:
            citations = max(0.0, float(work.get("citation_count") or 0.0))
        except (TypeError, ValueError):
            citations = 0.0
        cohort = (year // 3) * 3 if year else 0
        transformed = math.log1p(citations)
        cohorts.setdefault(cohort, []).append(transformed)
        values.append((cohort, transformed))
    maxima = {cohort: max(rows, default=0.0) for cohort, rows in cohorts.items()}
    return [value / maxima[cohort] if maxima[cohort] > 0 else 0.0 for cohort, value in values]


def diversity_novelty(work: dict[str, Any], selected: list[dict[str, Any]]) -> float:
    if not selected:
        return 1.0
    tokens = set(tokenize(work_text(work)))
    venue = normalize_text(work.get("venue_or_source") or "")
    similarities = []
    for existing in selected:
        other = set(tokenize(work_text(existing)))
        lexical = len(tokens & other) / max(1, len(tokens | other))
        venue_overlap = (
            0.1 if venue and venue == normalize_text(existing.get("venue_or_source") or "") else 0.0
        )
        similarities.append(min(1.0, lexical + venue_overlap))
    return 1.0 - max(similarities, default=0.0)
