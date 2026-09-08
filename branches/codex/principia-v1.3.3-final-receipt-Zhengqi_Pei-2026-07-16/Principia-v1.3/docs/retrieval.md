# Principia Retrieval (v1.3.3)

`principia_retrieval` is Principia's public, domain-neutral academic metadata
retriever. It plans complementary queries, searches multiple providers, merges
publication identities, ranks a candidate pool, and returns both works and
machine-readable diagnostics.

Private folders use the separate `ResearchService.ingest_local(...)` adapter
documented in [local-corpus.md](local-corpus.md). In a high-level pipeline,
`target_count` always means the public online-literature target; every accepted
local document is supplemental and cannot hide an underfilled online search.

## Public entry point

```python
from principia_retrieval import RetrievalConfig, WorkRetriever

config = RetrievalConfig(
    rerank_mode="embedding_rerank",
    max_raw_candidates=300,
    max_queries=8,
    require_target=True,
)
result = WorkRetriever(config=config).search(
    research_goal,
    target_count=50,
    embedding_client=embedding_client,
)
```

`RetrievalResult` contains the `QueryPlan`, normalized `candidates`, final
`selected_works`, a public `ranking_trace`, and `SearchDiagnostics`. The
diagnostics include completeness, all source/query reports, query routing,
candidate counts, warnings, and whether embedding reranking was actually
applied or fell back to BM25.

When `require_target=True`, an underfilled search raises
`InsufficientResultsError`. Its `.result` attribute contains the partial result
and complete diagnostics. If every source request fails, the retriever raises
`AllSourcesFailedError` instead of returning a misleading empty search.

## Query planning and routing

The deterministic planner retains exact acronyms, identifiers, scientific
notation, technical phrases, directly supported synonyms, and complementary
method/evaluation/control intents. It decomposes prose goals into a core
research problem plus method, constraint, evaluation, and failure-mode facets;
each bibliographic query keeps the core anchor while varying one facet. This
avoids both full-goal overconstraint and same-word/different-problem drift
without relying on discipline-specific query templates. An available LLM may
augment this plan, but planner failure falls back deterministically.
`QueryPlan.trace` records the routed providers.

The standard providers are:

| Provider | Coverage | Terms |
| --- | --- | --- |
| arXiv | Preprints across physics, mathematics, computing, and related fields | [API terms](https://info.arxiv.org/help/api/tou.html) |
| OpenAlex | Cross-domain scholarly graph | [Terms](https://openalex.org/OpenAlex_termsofservice.pdf) |
| Crossref | DOI and publisher metadata | [Metadata and licensing guidance](https://www.crossref.org/documentation/retrieve-metadata/) |
| Semantic Scholar | Cross-domain paper graph | [API license](https://www.semanticscholar.org/product/api#api-license) |
| Europe PMC | Biomedical and life-science literature | [Developer and content-access guidance](https://europepmc.org/developers) |

OpenAlex requires a free API key under its current
[authentication policy](https://developers.openalex.org/api-reference/authentication).
Set `OPENALEX_API_KEY` in the process environment. The retired `mailto` polite
pool is not used, and provider credentials are redacted from persisted source
errors and retry diagnostics.

Europe PMC is added automatically for biomedical/life-science plans. Explicit
`source_names` always override automatic routing. Provider adapters apply
source-appropriate query syntax: arXiv requires a match from each of two
concept groups while allowing OR alternatives within a group, avoiding both an
all-term AND recall collapse and an all-concept OR precision collapse.
Semantic Scholar strips unsupported Boolean syntax and Unicode hyphens;
OpenAlex, Crossref, and Europe PMC receive focused bibliographic terms.

Principia preserves source attribution and provider identifiers but does not
grant rights to publisher full text or provider metadata. Users must follow the
linked provider terms, rate-limit guidance, attribution requirements, and any
separate full-text license. Private content sent to an LLM is governed by that
provider's terms and requires Principia's explicit privacy consent; it is not
submitted to these bibliographic metadata sources.

## Reliability and diagnostics

Every source/query call has bounded retries, exponential backoff, `Retry-After`
support, per-provider pacing, and a certifi-backed TLS context. A `SourceReport`
records the original and normalized query, requested/returned/normalized
counts, latency, attempts, retry errors, HTTP status, and final state:
`success`, `empty`, or `failed`.

Source calls run concurrently, while pacing is coordinated per provider.
Partial outages return available results with `diagnostics.degraded=True` and
an explicit warning. Empty successful responses remain distinguishable from
network/provider failures.

Retrieval is adaptive. The first round divides a candidate-pool budget across
all query/provider pairs. If deduplication leaves too few unique candidates,
later rounds request deeper result pages (up to the configured per-task and
round bounds). Strict target mode either returns exactly the requested number
or raises with the partial result.

Key reliability controls in `RetrievalConfig` are:

| Setting | Default |
| --- | ---: |
| `source_max_retries` | 2 |
| `source_backoff_seconds` | 0.5 |
| `source_max_backoff_seconds` | 8.0 |
| `max_retrieval_rounds` | 3 |
| `candidate_oversample` | 3.0 |
| `max_results_per_source_query` | 100 |
| `stabilize_repeated_searches` | `True` |
| `stability_window` | 20 |
| `stability_min_jaccard` | 0.70 |

Repeated equivalent searches in the same Python process still make fresh
provider and embedding requests. By default, Principia then applies a bounded,
transparent top-20 stability anchor: it retains only the mathematically needed
portion of the preceding top cohort to meet the configured Jaccard floor while
leaving room for newly retrieved works. If a retained work is absent from a
transient provider response, its previously normalized metadata may be restored
for that process-local comparison. Diagnostics expose whether this happened in
`stability_anchor_applied`, `stability_anchor_window`,
`stability_anchor_retained`, and `stability_anchor_restored`; the ranking trace
marks retained rows with `stability_anchor=true`. Set
`stabilize_repeated_searches=False` when measuring raw provider volatility.

## Identity reconciliation

DOI, arXiv, OpenAlex, Semantic Scholar, and PMID identifiers are authoritative
within their namespaces. Exact identifiers merge directly. A matching title
can connect a preprint to a publication when identifiers do not conflict and
author/year evidence is compatible. Near-identical title matching has stricter
author/year checks. Distinct values in the same identifier namespace never
merge.

DOIs are canonicalized across bare, `doi:`, percent-encoded, and resolver-URL
forms. arXiv resolver URLs and version suffixes map to the underlying work, and
OpenAlex URLs map to their stable `W...` identifier. SQLite repeats the same
normalization during idempotent migration, reconciles compatible legacy rows,
and preserves rows with conflicting strong identities. Strict searches recheck
the requested unique count after persistence reconciliation.

Merged records retain provider URLs, the longest abstract, the maximum citation
count, publication/preprint provenance, PMID and PDF links, and all known strong
identifiers. They also retain every matched query and its best provider rank;
this query provenance contributes a small support signal during ranking.

## Ranking and reranking

BM25 lexical relevance, rare-term-weighted query-facet coverage, provider/query
support, metadata completeness, and a small citation signal determine the
initial order. Generic acronyms that occur throughout a candidate cohort do not
receive an exact-entity bonus; distinctive identifiers still do. Citation
counts are log-scaled within three-year publication cohorts so old or
high-citation disciplines do not dominate. A specific venue is only a metadata
completeness signal; there are no AI, astronomy, or named-venue whitelists.

The embedding pool retains the strongest overall BM25 candidates and reserves
capacity for every query facet and provider. This prevents an essential but
specialized method from being excluded by one aggregate prefilter.

With `rerank_mode="embedding_rerank"`, the BM25 pool is reranked using
`Qwen/Qwen3-Embedding-4B` by default. Principia accepts an injected embedding
client or uses SiliconFlow credentials (`SILICONFLOW_API_KEY` or
`PRINCIPIA_API_KEY`) and `PRINCIPIA_LLM_BASE_URL`. The reranker embeds an
instruction-prefixed goal and each complementary research facet separately,
then combines goal similarity, strongest facet similarity, facet breadth,
normalized BM25, lexical facet coverage, assessable-content quality, and query
support. Title-only records remain eligible but rank below equally relevant
records with enough abstract evidence to assess. Embedding calls validate
vector counts and dimensions and use bounded transient-error retries.

Final selection applies novelty only as a two-percent tie-breaker inside the
relevance-qualified pool. Diversity therefore broadens closely scored evidence
without promoting a topical tangent over a materially stronger match.

An embedding failure preserves deterministic BM25 order and records the reason
in both work metadata and `SearchDiagnostics.rerank_fallback_reason`. Callers
must check `rerank_mode_applied`; a requested embedding mode is not silently
reported as successful.

## Verification

`tests/test_retrieval_v133.py` covers retry and `Retry-After` behavior, partial
and total outages, adaptive strict-target top-up, strict underfill errors,
embedding applied/fallback diagnostics, provider query normalization,
biomedical routing, diagnostics serialization, generic-entity calibration,
multi-aspect embedding, metadata-quality weighting, query-provenance merging,
facet-stratified pooling, and relevance-first diversity. The broader research
tests cover persistence integration, preprint/publication merging,
deterministic ranking, and non-AI domain retrieval.
