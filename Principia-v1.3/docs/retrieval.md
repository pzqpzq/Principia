# Principia Retrieval: Flow and Current Behavior

This document describes the implementation in `principia_retrieval` as it exists today. It covers public metadata retrieval, query planning, deduplication, ranking, optional reranking, failure behavior, and known implementation issues.

## Scope and Entry Points

The shared retrieval package is exposed through `principia_retrieval.WorkRetriever`. Its primary API is:

```python
result = WorkRetriever(config=config).search(
    goal_text,
    target_count=50,
    llm=llm,
    embedding_client=embedding_client,
)
```

`RetrievalResult` contains:

- `query_plan`: the generated `QueryPlan`.
- `candidates`: normalized and deduplicated works before scoring. Internal score fields beginning with `_` are removed.
- `selected_works`: final works after ranking and final filtering. Internal score fields are removed.
- `ranking_trace`: the final works with public score, relation label, rationale, and rejection reason.

The V1.3 application calls this package through `principia.research.ResearchService.search`. It accepts `rerank_mode` and the CLI exposes `--rerank-mode bm25|embedding_rerank` for search, extract, and generate commands.

## End-to-End Flow

```text
research goal
  -> deterministic query plan
  -> optional LLM query-plan augmentation
  -> bounded query list
  -> concurrent source queries
  -> normalize works
  -> deduplicate works
  -> BM25 + deterministic signals
  -> relevance prefilter
  -> optional embedding reranker, or keep BM25 order
  -> final out-of-scope filtering and top-up
  -> selected works and ranking trace
```

### 1. Input Bounds and Reranker Selection

`target_count` is clamped to `[1, 200]`. `RetrievalConfig.rerank_mode` accepts the following aliases:

| Requested value | Resolved mode |
| --- | --- |
| `embedding`, `embedding-rerank`, `embedding_rerank` | `embedding_rerank` |
| `bm25`, `deterministic`, `no_llm`, `no-llm` | `bm25` |

Any mode other than an embedding alias resolves to deterministic BM25 ranking.

Relevant defaults in `RetrievalConfig` are:

| Setting | Default | Meaning |
| --- | ---: | --- |
| `max_raw_candidates` | 240 | Requested raw-candidate budget before deduplication; see the budget caveat below. |
| `max_queries` | 6 | Maximum search strings sent to each source. |
| `min_relevance` | 0.08 | BM25-combined score threshold for the reranking pool. |
| `embedding_model` | `Qwen/Qwen3-Embedding-4B` | SiliconFlow embedding model. |
| `embedding_dimensions` | 1024 | Requested embedding vector dimension. |
| `embedding_batch_size` | 32 | Texts per embedding API call. |
| `embedding_rerank_candidate_limit` | 0 | If zero, uses `max(2 * target_count, 50)`; otherwise uses at least `target_count`. |

### 2. Query Planning

The planner always starts with a deterministic plan.

1. It cleans the goal text.
2. It extracts entity-like identifiers using regular expressions, including long uppercase identifiers, mixed acronym-number forms, arXiv identifiers, and astronomy transient identifiers.
3. It tokenizes English alphanumeric terms, removes a fixed stopword list, and produces 3-token phrases, 2-token phrases, then individual tokens.
4. It forms queries from entities and phrases, adds an entity-plus-phrase combination, and finally adds the full goal text.

When `use_llm_planner=True` and the supplied LLM reports availability, the planner asks the LLM for `search_queries`, `entities`, and `key_phrases`. The deterministic entities and phrases are retained and combined with the LLM output. With a query budget, the mixed list keeps deterministic anchor queries, LLM queries, and the full goal where possible. Any planner exception falls back to the deterministic plan.

`QueryPlan.domain_hints` and `exclude_terms` exist in the data model but are not populated by the current planner and do not affect source retrieval or scoring.

### 3. Source Retrieval

The default source registry contains four adapters:

| Source | Endpoint behavior |
| --- | --- |
| arXiv | Atom API, sorted by relevance. |
| OpenAlex | `/works?search=...`, sorted by `relevance_score`. |
| Crossref | `/works?query=...`, sorted by relevance. |
| Semantic Scholar | Graph paper search with title, authors, year, venue, URL, abstract, citations, and external IDs. |

For every selected source and query pair, `WorkRetriever` starts `fetch_source` in a thread pool. The pool has at most eight workers. `fetch_source` absorbs source-call failures and returns an empty list for a failed adapter call. Successful rows are normalized and tagged with `source`, `source_query`, `source_rank`, and `source_limit` in `community_signals`.

The raw-candidate budget is divided across all active source/query pairs:

```text
base, remainder = divmod(max_raw_candidates, active_source_query_pairs)
limit[i] = min(25, base + 1) for the first remainder pairs
limit[i] = min(25, base) otherwise
```

Pairs are ordered by query and then source. Only pairs with a positive allocation are queried. Returned rows are capped again to the allocated limit, so a custom source that ignores its requested limit cannot exceed the raw budget. Requests are still concurrent, but results are concatenated in source/query task order rather than completion order.

### 4. Normalization and Deduplication

Each source row is normalized to a common schema. Key fields include `work_id`, title, authors, year, venue, URL/DOI, DOI, arXiv/OpenAlex/Semantic Scholar identifiers, abstract, citation count, source URLs, and community signals.

Deduplication uses these identity keys, in order:

1. DOI
2. arXiv identifier
3. OpenAlex identifier
4. Semantic Scholar identifier
5. normalized title

On a match, the system selects the higher-quality source record. Source quality prefers a non-aggregator venue, then Crossref, OpenAlex, Semantic Scholar, arXiv, and then citation count. It merges URLs, keeps the longer abstract, keeps the maximum citation count, and records `merged_sources`.

### 5. Deterministic BM25 Ranking

All deduplicated works are ranked before any optional reranker. The document text is the concatenation of title, abstract, and venue. The BM25 query is formed from:

- full research goal;
- at most eight planned search queries;
- all entities;
- at most twelve key phrases.

The tokenizer indexes English alphanumeric tokens of length at least three (with `_` and `-` allowed), applying small plural normalization. For contiguous CJK text it emits overlapping two-character tokens, so Chinese goals and metadata participate in BM25 and lexical-overlap scoring without requiring an external tokenizer.

For a candidate, the combined BM25-stage score is:

```text
score = max(0,
    0.62 * normalized_BM25
  + 0.28 * semantic_lite_overlap
  + 0.06 * source_prior
  + metadata_score
  + exact_entity_bonus)
```

`semantic_lite_overlap` is a weighted lexical coverage score over the goal, with bonuses for planned phrases and entities in the document. The source prior is the maximum of a transformed source-provided relevance score and `1 / sqrt(source_rank)`. `metadata_score` is at most `0.115`, composed of recency, citation count, venue heuristic, abstract presence, and link presence. An exact entity match adds `0.35`.

The BM25 relation labels are assigned as follows:

| Condition | Label |
| --- | --- |
| exact entity, or combined score >= 0.48 | `direct` |
| combined score >= 0.28 | `background` |
| lexical overlap >= 0.12 | `methodological` |
| otherwise | `out_of_scope` |

Candidates with a combined score below `min_relevance` are removed before reranking unless they contain an exact planned entity. If this leaves no candidates, the top `max(target_count, 20)` BM25 candidates are restored.

### 6. Single-Vector Embedding Reranking

Embedding reranking is selected only by `rerank_mode="embedding_rerank"` (or an alias) and runs after the BM25 prefilter. It reranks at most the configured candidate limit; the default is `max(2 * target_count, 50)`.

The default provider is SiliconFlow's OpenAI-compatible embeddings endpoint. It requires `SILICONFLOW_API_KEY` or `PRINCIPIA_API_KEY`. Its base URL defaults to `https://api.siliconflow.cn/v1`, but can be overridden with `PRINCIPIA_LLM_BASE_URL`. The request body contains the model, an input-text array, and the requested dimensions. Transient HTTP status codes 429, 500, 502, 503, and 504, timeout errors, and URL errors are retried up to `embedding_max_retries` with exponential waits.

This is a single-vector method:

1. The goal and query-plan fields are serialized into one query text:

   ```text
   research_goal: <goal>
   search_queries: <up to 8 queries>
   entities: <up to 16 entities>
   key_phrases: <up to 20 phrases>
   domain_hints: <up to 8 hints>
   ```

2. Each work is serialized into one document text:

   ```text
   title: <title>
   abstract: <abstract truncated to 5,000 characters>
   venue: <venue>
   year: <year>
   authors: <up to 10 authors>
   doi: <DOI or URL>
   source: <source>
   ```

3. The query and all candidate texts are embedded, batching uncached texts. The in-memory cache key is model, dimensions, and SHA-1 of the serialized text. The cache is local to one `embedding_rerank` call unless the caller passes a cache object.
4. A candidate's main score is cosine similarity between the one query vector and its one work vector. The cosine value is clamped to `[0, 1]`.
5. The final embedding score is:

   ```text
   embedding_score = cosine_similarity + 0.05 * metadata_score + 0.01 * exact_entity_match
   ```

6. Embedding relation labels use similarity thresholds: `direct` for an exact entity or similarity >= 0.78; `background` for >= 0.62; `methodological` for >= 0.46; otherwise `out_of_scope`.

If the embedding request, response parsing, or client invocation fails, the candidate order remains BM25 order. Each candidate receives `embedding_rerank_error`, `embedding_model`, and `embedding_dimensions` in `community_signals`.

### 7. Final Selection

The list is sorted by retrieval score, relation-label priority (`direct`, `background`, `methodological`, `out_of_scope`), and descending year.

The first pass excludes:

- an `out_of_scope` work with a non-empty rejection reason; and
- an `out_of_scope` work without an exact entity match whose score is below `0.18`.

If too few works remain, a second pass fills the result from the ranked list, still excluding works that have an explicit rejection reason. Deduplication for this final top-up uses `work_id`, or a stable title-and-URL hash when no ID is present.

## Integrity Rules and Remaining Limitations

### Deduplication identity rule

DOI, arXiv, OpenAlex, and Semantic Scholar identifiers are strong identifiers. A matching strong identifier merges records. A normalized-title match merges records only when at least one record has no strong identifier; two records with distinct strong identifiers remain distinct even when their titles are identical.

This avoids merging known-distinct publications, but title-only records remain an inherently weaker identity case. A future enhancement can use authors and publication year to make title-only merging more conservative.

### Embedding response validation

The SiliconFlow response parser validates vector count, non-empty vectors, consistent dimensions, and the requested dimension when a positive dimension was sent in the API request. Generic injected embedding clients are also checked for non-empty and mutually consistent vector lengths. A violation triggers the existing BM25 fallback.

### Scoring calibration

BM25 and embedding scores are calibrated independently. Their absolute values should not be compared across modes. Changes to source mix, CJK tokenization, model version, or metadata quality should be evaluated with the retrieval benchmark before changing relation-label thresholds.

## Verification Coverage

The focused shared-retriever tests cover BM25 ordering, optional LLM query planning, embedding reranking, embedding fallback, reranking pool limits, mode aliases, within-call embedding-text caching, distinct DOI records with a shared title, strict candidate-budget behavior, and CJK BM25 ranking. Application and CLI integration should additionally be covered by end-to-end tests when their command surface changes.
