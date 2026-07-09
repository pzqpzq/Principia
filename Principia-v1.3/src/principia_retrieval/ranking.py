from __future__ import annotations

import json
import math
from collections import Counter
from typing import Any

from .constants import RELATION_ORDER
from .embeddings import SiliconFlowEmbeddingClient, embedding_cache_key
from .models import QueryPlan
from .utils import call_llm_json, clamp_float, clean_text, normalize_text, stable_id, tokenize, truncate, weighted_tokens


def deterministic_rank(goal_text: str, works: list[dict[str, Any]], plan: QueryPlan) -> list[dict[str, Any]]:
    scored = []
    goal_tokens = weighted_tokens(goal_text)
    for work in works:
        item = dict(work)
        body = work_text(item)
        relevance = semantic_lite_score(goal_text, body, plan, goal_tokens=goal_tokens)
        metadata = metadata_score(item)
        exact_bonus = 0.35 if has_exact_entity(item, plan) else 0.0
        final = max(0.0, relevance + metadata + exact_bonus)
        relation = relation_from_score(final, exact_bonus, relevance)
        item["_retrieval_score"] = final
        item["relation_label"] = relation
        item["retrieval_rationale"] = deterministic_rationale(item, plan, relevance, exact_bonus)
        item["reject_reason"] = ""
        item.setdefault("community_signals", {})["retrieval_score"] = round(final, 4)
        item.setdefault("community_signals", {})["relation_label"] = relation
        scored.append(item)
    scored.sort(key=lambda item: (float(item.get("_retrieval_score", 0.0)), relation_rank(item), int(item.get("year") or 0)), reverse=True)
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
    scored = []
    for work, raw_score in zip(works, raw_scores):
        item = dict(work)
        body = work_text(item)
        relevance = semantic_lite_score(goal_text, body, plan, goal_tokens=goal_tokens)
        metadata = metadata_score(item)
        exact_bonus = 0.35 if has_exact_entity(item, plan) else 0.0
        bm25_norm = raw_score / max_bm25 if max_bm25 > 0 else 0.0
        source_prior = source_prior_score(item)
        final = max(0.0, bm25_norm * 0.62 + relevance * 0.28 + source_prior * 0.06 + metadata + exact_bonus)
        relation = relation_from_score(final, exact_bonus, max(relevance, bm25_norm * 0.35))
        item["_retrieval_score"] = final
        item["_bm25_score"] = raw_score
        item["_source_prior_score"] = source_prior
        item["relation_label"] = relation
        item["retrieval_rationale"] = bm25_rationale(item, plan, raw_score, relevance, source_prior, exact_bonus)
        item["reject_reason"] = ""
        signals = item.setdefault("community_signals", {})
        signals["bm25_score"] = round(raw_score, 4)
        signals["source_prior_score"] = round(source_prior, 4)
        signals["retrieval_score"] = round(final, 4)
        signals["relation_label"] = relation
        scored.append(item)
    scored.sort(key=lambda item: (float(item.get("_retrieval_score", 0.0)), relation_rank(item), int(item.get("year") or 0)), reverse=True)
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
        try:
            value = float(signals.get(key))
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
) -> list[dict[str, Any]]:
    by_id = {str(work.get("work_id") or stable_id("W", work.get("title", ""))): dict(work) for work in works}
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
    query_text = query_embedding_text(goal_text, plan)
    corpus_texts = [work_embedding_text(work) for work in rows]
    try:
        vectors = embed_texts_cached(
            [query_text, *corpus_texts],
            client,
            model=model,
            dimensions=dimensions,
            batch_size=batch_size,
            timeout=timeout,
            cache=cache,
        )
    except Exception as exc:  # noqa: BLE001
        return embedding_fallback(rows, exc, model=model, dimensions=dimensions)
    query_vector = vectors[0]
    work_vectors = vectors[1:]
    output = []
    for work, vector in zip(rows, work_vectors):
        item = dict(work)
        similarity = clamp_float(cosine_similarity(query_vector, vector), 0.0, 1.0)
        metadata = metadata_score(item)
        exact_bonus = 0.01 if has_exact_entity(item, plan) else 0.0
        final = similarity + metadata * 0.05 + exact_bonus
        relation = relation_from_embedding_similarity(similarity, exact_bonus > 0)
        item["_retrieval_score"] = final
        item["_embedding_similarity"] = similarity
        item["relation_label"] = relation
        item["retrieval_rationale"] = embedding_rationale(item, similarity)
        item["reject_reason"] = ""
        signals = item.setdefault("community_signals", {})
        signals["embedding_similarity"] = round(similarity, 4)
        signals["embedding_model"] = model
        signals["embedding_dimensions"] = int(dimensions or 0)
        signals["retrieval_score"] = round(final, 4)
        signals["relation_label"] = relation
        output.append(item)
    output.sort(key=lambda item: (float(item.get("_retrieval_score", 0.0)), relation_rank(item), int(item.get("year") or 0)), reverse=True)
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
) -> list[list[float]]:
    keys = [embedding_cache_key(model, dimensions, text) for text in texts]
    missing: list[tuple[str, str]] = []
    seen_missing = set()
    for key, text in zip(keys, texts):
        if key in cache or key in seen_missing:
            continue
        missing.append((key, text))
        seen_missing.add(key)
    for index in range(0, len(missing), max(1, int(batch_size or 1))):
        batch = missing[index : index + max(1, int(batch_size or 1))]
        batch_vectors = call_embedding_client(
            client,
            [text for _, text in batch],
            model=model,
            dimensions=dimensions,
            timeout=timeout,
        )
        if len(batch_vectors) != len(batch):
            raise RuntimeError(f"Embedding client returned {len(batch_vectors)} vector(s), expected {len(batch)}.")
        for (key, _), vector in zip(batch, batch_vectors):
            cache[key] = [float(value) for value in vector]
    return [cache[key] for key in keys]


def call_embedding_client(
    client: Any,
    texts: list[str],
    *,
    model: str,
    dimensions: int,
    timeout: float,
) -> list[list[float]]:
    embed = getattr(client, "embed", None)
    if callable(embed):
        try:
            return embed(texts, model=model, dimensions=dimensions, timeout=timeout)
        except TypeError:
            return embed(texts)
    if callable(client):
        try:
            return client(texts, model=model, dimensions=dimensions, timeout=timeout)
        except TypeError:
            return client(texts)
    raise RuntimeError("Embedding rerank requires an embedding client with an embed method.")


def embedding_fallback(rows: list[dict[str, Any]], error: Exception, *, model: str, dimensions: int) -> list[dict[str, Any]]:
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
    rows = [
        ("research_goal", goal_text),
        ("search_queries", "; ".join(clean_text(value) for value in plan.search_queries[:8] if clean_text(value))),
        ("entities", "; ".join(clean_text(value) for value in plan.entities[:16] if clean_text(value))),
        ("key_phrases", "; ".join(clean_text(value) for value in plan.key_phrases[:20] if clean_text(value))),
        ("domain_hints", "; ".join(clean_text(value) for value in plan.domain_hints[:8] if clean_text(value))),
    ]
    return "\n".join(f"{label}: {text}" for label, text in rows if text)


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
    if exact_entity or similarity >= 0.78:
        return "direct"
    if similarity >= 0.62:
        return "background"
    if similarity >= 0.46:
        return "methodological"
    return "out_of_scope"


def embedding_rationale(work: dict[str, Any], similarity: float) -> str:
    bits = [f"embedding cosine similarity {similarity:.2f}"]
    if float(work.get("_bm25_score", 0.0) or 0.0) > 0:
        bits.append("BM25 prefilter match")
    return "; ".join(bits)


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
                    "Return {\"items\":[...]} with one item per candidate. Each item must include: "
                    "work_id, relevance_score, relation_label, rationale, reject_reason.\n"
                    "Score 0-1 by usefulness for the research goal: 0.90-1.00 central match, "
                    "0.65-0.89 strong supporting evidence, 0.35-0.64 related method/background, "
                    "0.10-0.34 weak connection, below 0.10 irrelevant.\n"
                    "relation_label must be one of: direct, background, methodological, out_of_scope. "
                    "direct = studies the goal's target object/task/mechanism; background = useful context "
                    "or evidence; methodological = transferable method/evaluation/resource; out_of_scope = "
                    "not useful for this goal.\n"
                    "Use only title, abstract, venue, and year. Keep rationale under 20 words. "
                    "Set reject_reason only for out_of_scope items, otherwise use an empty string.\n\n"
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
    seen = set()
    for work in works:
        label = normalize_relation(work.get("relation_label"))
        if label == "out_of_scope" and clean_text(work.get("reject_reason") or ""):
            continue
        if label == "out_of_scope" and not has_exact_entity(work, plan) and float(work.get("_retrieval_score", 0.0)) < 0.18:
            continue
        selected.append(work)
        seen.add(selection_key(work))
        if len(selected) >= target_count:
            break
    if len(selected) < target_count:
        for work in works:
            if normalize_relation(work.get("relation_label")) == "out_of_scope" and clean_text(work.get("reject_reason") or ""):
                continue
            key = selection_key(work)
            if key in seen:
                continue
            selected.append(work)
            seen.add(key)
            if len(selected) >= target_count:
                break
    return selected[:target_count]


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


def has_exact_entity(work: dict[str, Any], plan: QueryPlan) -> bool:
    text = normalize_text(work_text(work))
    return any(normalize_text(entity) and normalize_text(entity) in text for entity in plan.entities)


def deterministic_rationale(work: dict[str, Any], plan: QueryPlan, relevance: float, exact_bonus: float) -> str:
    bits = []
    if exact_bonus:
        bits.append("matches target entity")
    matched = [phrase for phrase in plan.key_phrases if normalize_text(phrase) and normalize_text(phrase) in normalize_text(work_text(work))]
    if matched:
        bits.append("matches " + ", ".join(matched[:3]))
    if not bits:
        bits.append(f"lexical-semantic overlap {relevance:.2f}")
    return "; ".join(bits)


def bm25_rationale(work: dict[str, Any], plan: QueryPlan, raw_bm25: float, relevance: float, source_prior: float, exact_bonus: float) -> str:
    bits = []
    if exact_bonus:
        bits.append("matches target entity")
    matched = [phrase for phrase in plan.key_phrases if normalize_text(phrase) and normalize_text(phrase) in normalize_text(work_text(work))]
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
    if not value or value in {"arxiv", "openalex", "crossref", "semantic scholar"}:
        return 0.0
    if any(term in value for term in ["nature", "science", "neurips", "icml", "iclr", "cvpr", "acl", "emnlp", "astrophysical journal", "astronomy", "monthly notices"]):
        return 1.0
    return 0.55


def work_text(work: dict[str, Any]) -> str:
    return " ".join(str(work.get(key) or "") for key in ["title", "abstract", "venue_or_source"])


def selection_key(work: dict[str, Any]) -> str:
    return str(work.get("work_id") or stable_id("W", work.get("title", ""), work.get("url_or_doi", "")))
