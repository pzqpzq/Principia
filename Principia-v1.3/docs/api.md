# Principia v1.3.3 API

Principia is a local-first framework for cross-domain literature retrieval,
structured extraction, evidence selection, research-idea generation, comparison,
and validation hand-off.

## Install and import

```bash
python -m pip install principia-ai==1.3.3
```

```python
import principia as pc

assert pc.__version__ == "1.3.3"
```

The distribution name is `principia-ai`; the import packages are `principia`
and `principia_retrieval`. The framework subtree and built distribution use the
MIT license. The separate repository-root license applies to the surrounding
repository and does not replace the framework package license.

## Concise background workflow

```python
import os
import principia as pc

ws = pc.Workspace.project(
    "principia_project",
    llm_config=pc.siliconflow_config(os.environ["SILICONFLOW_API_KEY"], max_calls=220),
    allow_remote_private_content=True,
)
job = ws.start(
    "Your research objective",
    documents="private_sources",
    pipeline_config=pc.PipelineConfig.research(),
)
result = job.result()
result.show()
```

The 50-work research preset requests strict online target completion, embedding
reranking, an exact five/five/five evidence packet with at most two records per
work, and strict `scidialect-evo`. Local documents are supplemental and do not
satisfy the online target.

## End-to-end staged workflow

The staged API keeps expensive operations inspectable and resumable. This
example retrieves exactly 50 unique works, extracts all 50, selects an exact
15-record evidence packet, runs the three-stage SciDialect-Evo process, compares
the resulting idea with extracted prior ideas, updates the shared workspace
pool, and exports the seven-file idea and validation bundle.

```python
import principia as pc

API_KEY = "YOUR_SILICONFLOW_API_KEY"
goal = (
    "Develop uncertainty-aware sparse-view dynamic 3D reconstruction by combining "
    "feed-forward 3D Gaussian splatting with geometric priors for uncalibrated images."
)

llm_config = pc.siliconflow_config(
    API_KEY,
    model="Qwen/Qwen3.5-397B-A17B",
    timeout=420,
    max_retries=2,
    max_calls=220,
)
ws = pc.Workspace.project("principia_project", llm_config=llm_config)

retrieval_config = pc.RetrievalConfig(
    rerank_mode="embedding_rerank",
    embedding_model="Qwen/Qwen3-Embedding-4B",
    max_raw_candidates=600,
    candidate_oversample=4.0,
    max_queries=8,
    max_retrieval_rounds=3,
    require_target=True,
)
works = ws.research.search(
    goal,
    target_count=50,
    retrieval_config=retrieval_config,
    require_target=True,
    callback=pc.notebook_progress("Literature retrieval"),
)

features = ws.research.extract(
    works,
    model="siliconflow:Qwen/Qwen3.6-35B-A3B",
    overwrite=False,
    continue_on_error=False,
    callback=pc.notebook_progress("Feature extraction"),
)

evidence = pc.select_evidence(
    features,
    kinds=["ideas", "principles", "takeaways"],
    global_kind_limits={"ideas": 5, "principles": 5, "takeaways": 5},
    max_per_work=2,
    require_exact=True,
    user_note=goal,
)

idea = ws.ideas.generate(
    evidence,
    user_note=goal,
    mode="scidialect-evo",
    model="siliconflow:Qwen/Qwen3.5-397B-A17B",
    scidialect_config=pc.SciDialectConfig(allow_degraded_fallback=False),
    callback=pc.notebook_progress("Idea generation"),
)
comparison = ws.ideas.compare(
    idea,
    features,
    model="siliconflow:Qwen/Qwen3.5-397B-A17B",
    callback=pc.notebook_progress("Prior-idea comparison"),
)
export_path = ws.export(
    goal=goal,
    works=works,
    features=features,
    idea=idea,
    comparison=comparison,
)
```

When `rerank_mode="embedding_rerank"` is requested without an explicit
`embedding_client`, the high-level API reuses the workspace's SiliconFlow key
and base URL for `Qwen/Qwen3-Embedding-4B`. The diagnostic record always says
whether embedding reranking was actually applied.

## Project layout and exports

```python
ws = pc.Workspace.project("principia_project", llm_config=llm_config)
```

This recommended interface stores one reusable works/features pool and writes
each idea to its own sibling output folder:

```text
principia_project/
  tutorial.ipynb
  workspace/
    README.md
    works.json
    features.json
    manifest.json
    .principia/
      principia.sqlite
      artifacts/
  outputs/
    README.md
    <idea_id>/
      idea.md
      idea.json
      evidence.json
      comparison.json
      result.json
      validation_plan.md
      validation_plan.json
```

`workspace/works.json` and `workspace/features.json` are shared by every idea.
`outputs/<idea_id>/result.json` is a compact manifest containing relative
references to that pool; it does not duplicate works. Both validation-plan
files are created automatically beside every Idea Card.

Opening a project runs idempotent SQLite migrations. Workspaces created by
v1.3.0-v1.3.2 retain their records; v1.3.3 adds and backfills new identity and
metadata fields without merging records that carry conflicting strong IDs.

`Workspace(path)` and `Workspace.export(...)` remain backward compatible. The
former retains the legacy `principia_outputs/` layout for existing callers.
Every shareable field is checked for embedded machine-local paths; workspace
paths become portable relative references and external paths are scrubbed. See
[workspaces.md](workspaces.md) for the artifact contract.

## Private local documents

```python
local = ws.research.ingest_local(
    "private_sources",
    config=pc.LocalCorpusConfig(
        recursive=True,
        max_files=500,
        max_file_bytes=50 * 1024 * 1024,
    ),
)

print(local.local_count)
print(local.local_diagnostics.reports)
```

Core parsers cover PDF, HTML/XML, Markdown, RST, LaTeX, text/code,
JSON/JSONL, YAML, CSV/TSV, and safely decodable unknown text. Install
`principia-ai[local]` for DOCX, PPTX, and XLSX. `register_local_parser(...)`
provides an extension point for OCR, EPUB, transcription, and
organization-specific formats.

Local work URLs use `local://<corpus>/<relative-path>`. Only hidden SQLite state
retains the resolved path and cached normalized text. A remote extraction call
requires `allow_remote_private_content=True`; the provider receives content and
portable identifiers, not absolute paths. See [local-corpus.md](local-corpus.md)
for limits, diagnostics, chunking, and cleanup.

## Public types

- `RetrievalConfig`: retry, query, source, candidate-pool, strictness, and
  embedding-rerank configuration.
- `SearchDiagnostics`: completeness, query plan, source health, ranking trace,
  rerank state, counts, and warnings for one search.
- `SourceReport`: outcome, counts, latency, attempts, retry details, and error
  information for one source/query request.
- `WorkItem`: normalized scholarly work, including DOI, arXiv, OpenAlex,
  Semantic Scholar, PMID, PDF identifiers/URLs, and `content_sha256`.
- `WorkList`: ordered works plus public/local counts, retrieval diagnostics, and
  defaulted local-corpus diagnostics.
- `LocalCorpusConfig`, `LocalCorpusDiagnostics`, and `LocalSourceReport`:
  bounded local ingestion and portable per-file outcomes.
- `WorkFeatures` and `ExtractedFeatures`: per-work and batch feature records.
- `EvidencePacket`: the explicit evidence input to generation.
- `SciDialectConfig`: budgets, temperatures, and degraded-fallback policy for
  three-stage SciDialect-Evo.
- `Idea`, `IdeaComparison`, and `PipelineResult`: generated and pipeline output
  schemas; `PipelineResult.selected_evidence` retains the exact packet.
- `PipelineConfig` and `PipelineJob`: concise presets and persisted background
  execution with pause/resume/stop controls.
- `ValidationPlan`: standalone structured validation hand-off.
- `LLMConfig`, `LLMClient`, and `LLMUsage`: provider configuration, calls, and
  cumulative token/call accounting.
- `RunHandle`, `RunStatus`, `CancelToken`, `RunCancelledError`, and
  `NotebookProgress`: progress, cancellation, and persisted run state.
- `canonical_evidence_registry`, `validate_evidence_references`, and
  `hydrate_evidence_references`: exact record-level citation validation.

All names above are importable from `principia`.

## Retrieval

### Configuration and precedence

```python
config = pc.RetrievalConfig(
    use_llm_planner=True,
    rerank_mode="embedding_rerank",
    max_raw_candidates=600,
    min_relevance=0.08,
    source_names=None,
    max_queries=8,
    embedding_model="Qwen/Qwen3-Embedding-4B",
    embedding_dimensions=1024,
    embedding_batch_size=8,
    embedding_timeout=45,
    embedding_max_retries=2,
    source_max_retries=2,
    source_backoff_seconds=0.5,
    source_max_backoff_seconds=8.0,
    max_retrieval_rounds=3,
    candidate_oversample=4.0,
    require_target=True,
)

works = ws.research.search(
    goal,
    target_count=50,
    retrieval_config=config,
    rerank_mode="embedding_rerank",
    sources=None,
    require_target=True,
)
```

Explicit method arguments override `retrieval_config`. An explicit `sources`
list also overrides automatic routing. With no explicit list, Principia queries
arXiv, OpenAlex, Crossref, and Semantic Scholar, and automatically adds Europe
PMC for biomedical/life-science plans.

Set `OPENALEX_API_KEY` to authenticate OpenAlex requests under the provider's
current key-based access policy. It is read from the environment, excluded from
query plans and results, and redacted if a transport error includes the request
URL.

The query planner preserves domain hints, entities, acronyms, scientific
notation, synonyms, and complementary intents. Source-specific normalization
keeps arXiv queries broad enough to return useful cohorts and converts the plan
to focused, supported query syntax for Semantic Scholar, Crossref, OpenAlex,
and Europe PMC.

### Reliability behavior

Source requests use bounded retries and backoff, respect numeric
`Retry-After`, apply per-source minimum intervals, and use certifi-backed TLS.
Adaptive rounds increase the per-query result budget until the target candidate
pool is available or the configured round limit is reached.

- If every configured source fails, search raises `AllSourcesFailedError`.
- If some sources fail, results are returned only with
  `diagnostics.degraded=True` and an explicit warning.
- If `require_target=True` and the requested number of unique works cannot be
  produced, search raises `InsufficientResultsError` (or a high-level strict
  identity-reconciliation error) instead of silently underfilling.
- If embedding reranking fails, BM25 results may remain available, but
  `rerank_mode_applied`, `rerank_fallback_reason`, and warnings expose the
  fallback. Acceptance workflows should assert that embedding was applied.

```python
diagnostics = works.diagnostics

assert isinstance(diagnostics, pc.SearchDiagnostics)
assert diagnostics.complete
assert diagnostics.selected_count == 50
assert diagnostics.rerank_mode_requested == "embedding_rerank"
assert diagnostics.rerank_mode_applied == "embedding_rerank"

for report in diagnostics.source_reports:
    assert isinstance(report, pc.SourceReport)
    print(report.source, report.status, report.returned_count, report.latency_ms, report.retries)
```

`SearchDiagnostics` fields include `complete`, `completeness`, `degraded`,
`target_count`, `selected_count`, `raw_count`, `candidate_count`,
`bm25_scored_count`, `bm25_prefiltered_count`, `embedding_input_count`,
`retrieval_rounds`, `query_plan`, `source_reports`, `ranking_trace`,
`rerank_mode_requested`, `rerank_mode_applied`, `rerank_fallback_reason`,
`stability_anchor_applied`, `stability_anchor_window`,
`stability_anchor_retained`, `stability_anchor_restored`, `warnings`, and
`counts_by_source`. `successful_sources` and `failed_sources` provide convenient
derived lists. `to_dict()` returns a JSON-ready snapshot. Repeated equivalent
searches make fresh source and embedding calls; the default process-local
stability anchor is explicit in these fields and can be disabled with
`RetrievalConfig(stabilize_repeated_searches=False)` when raw provider
volatility is the quantity under test.

Ranking is domain-neutral: lexical/BM25 relevance, metadata completeness,
cohort-normalized citation evidence, optional embeddings, and diversity are
used without AI- or astronomy-specific venue whitelists. Strong identifiers are
authoritative during deduplication; cautious title/author/year matching connects
likely preprint/publication versions while preserving known-distinct works.
Repeated searches update matched records rather than manufacturing new work IDs.

See [retrieval.md](retrieval.md) for source details and provider terms.

## Extraction

```python
features = ws.research.extract(
    works,
    model="siliconflow:Qwen/Qwen3.6-35B-A3B",
    overwrite=False,
    continue_on_error=False,
    retain_pdfs=False,
    max_chars=24_000,
)
```

Extraction attempts PDF text or HTML, then falls back to abstract or title only.
Local documents use cached normalized text and report `local_text`.
Each `WorkFeatures` record exposes:

- `source_content_type`: `pdf_text`, `html`, `local_text`, `abstract`,
  `title_only`, or `unknown`;
- `source_url` and the actual `source_excerpt_chars` used;
- `source_content_hash` for the complete supplied evidence text;
- `extractor_fingerprint`, derived from the extractor prompt and schema;
- `extraction_warnings` and optional portable `retained_pdf_path`.

The cache identity includes the content hash and extractor fingerprint, so a
prompt/schema change cannot reuse stale v1.3.2 extractions. Completed matching
records are resumed when `overwrite=False`. `continue_on_error=False` is the
recommended acceptance setting; set it to `True` only when an explicitly
partial extraction batch is acceptable.

Long local documents use overlapping 24,000-character chunks with 2,000
characters of overlap by default. Every chunk uses the configured LLM; multiple
chunks are consolidated by another grounded LLM call. Completed chunks remain
checkpointed for pause, cancellation, and resumption.

Feature names are cross-domain while retaining the v1.3 storage schema:

| Canonical field | Domain-neutral meaning | Accepted aliases |
| --- | --- | --- |
| `baselines` | Comparators, controls, standard methods, or reference theories | `comparators`, `controls`, `standard_methods`, `reference_theories` |
| `benchmarks` | Evaluation contexts, datasets, experimental systems, instruments, observables, or standard tasks | `evaluation_contexts`, `experimental_systems`, `instruments`, `observables`, `standard_tasks` |

Aliases are normalized into the canonical fields and retain their more specific
meaning in each record's `record_type`. A real LLM extraction that is incomplete
or contains records with no lexical anchor to the supplied evidence receives at
most one evidence-grounded repair call. The same validation rejects equations,
formulas, comparator language, or evaluation contexts absent from the evidence;
no discipline-specific fallback content is injected.

## Evidence selection

Per-work limiting remains backward compatible:

```python
packet = pc.select_evidence(
    features,
    kinds=["ideas", "principles", "takeaways"],
    limit_per_kind=2,
)
```

Use global limits for an exact packet spanning the whole batch:

```python
packet = pc.select_evidence(
    features,
    kinds=["ideas", "principles", "takeaways"],
    global_kind_limits={"ideas": 5, "principles": 5, "takeaways": 5},
    max_per_work=2,
    require_exact=True,
)

assert packet.counts()["ideas"] == 5
assert packet.counts()["principles"] == 5
assert packet.counts()["takeaways"] == 5
```

`require_exact=True` raises when the requested global contract is infeasible.
`work_ids` and `feature_ids` can further restrict the eligible evidence.

The generator sees a minimal canonical registry. Every final citation must
resolve exactly to `(work_id, kind, record_id)`, and quoted text is rehydrated
from the selected record. Model configuration, mode, trace, warnings, and usage
metadata never enter this registry. When a packet mixes local `L-...` works
with public works, the final Idea must cite at least one canonical record from
each class. A missing class receives the same single evidence-grounded LLM
repair used for other generation defects; unresolved output is not saved.

## Idea generation and comparison

Supported modes are `standard`, `calculus` (alias
`principia_calculus`), and `scidialect_evo` (alias `scidialect-evo`).
Direct `IdeaService.generate(...)` calls and the `principia generate` CLI now
default to strict `scidialect-evo`. Existing workflows can retain the legacy
calculus path by passing `mode="calculus"` (or `--mode calculus`) explicitly.

SciDialect-Evo is a real three-stage protocol:

1. generate exactly three evidence-grounded candidates;
2. score, critique, and evolve the strongest two;
3. select and finalize one Idea Card.

```python
idea = ws.ideas.generate(
    packet,
    user_note=goal,
    mode="scidialect-evo",
    model="siliconflow:Qwen/Qwen3.5-397B-A17B",
    scidialect_config=pc.SciDialectConfig(
        candidate_count=3,
        evolved_candidate_count=2,
        allow_degraded_fallback=False,
    ),
    overwrite=False,
)

assert idea.mode == "scidialect_evo"
assert idea.trace["degraded"] is False
assert [stage["name"] for stage in idea.trace["stages"]] == [
    "candidate_generation",
    "critique_evolution",
    "final_selection",
]
```

The trace stores concise scores, critiques, stage status, selection rationale,
and degraded-state metadata, not hidden chain-of-thought. One evidence-grounded
repair call validates missing/off-domain Idea Card fields. With
`allow_degraded_fallback=False`, stage failure is surfaced rather than hidden.
Live stages never insert a canned Idea Card or substitute formula. They perform
at most one evidence-grounded repair and fail without persistence when required
defects remain. Explicit mock execution is marked `mock_fixture` and is not a
live acceptance origin.

`overwrite=False` preserves same-title idea history by allocating another
stable ID. `overwrite=True` intentionally replaces the matched record.

```python
comparison = ws.ideas.compare(
    idea,
    features,
    model="siliconflow:Qwen/Qwen3.5-397B-A17B",
    limit=12,
)
```

Comparison shortlists extracted prior ideas, then produces mechanistic
similarities, essential differences, potential advantages, and weaknesses.

## Standalone validation plans

Validation plans are built deterministically from an existing `Idea` or
`PipelineResult`; no additional LLM call is made.

```python
plan = pc.build_validation_plan(idea, goal=goal)
assert isinstance(plan, pc.ValidationPlan)

markdown_text = pc.validation_plan_markdown(plan)
json_text = pc.validation_plan_json(plan)
markdown_path, json_path = pc.write_validation_plan(plan, "validation_handoff")
```

The schema includes `schema_version`, idea ID/title, goal, thesis, validation
protocol, baselines/comparators, metrics, risks, assumptions, portable evidence
references, model/mode, run identity, and timestamps.

In the recommended project layout, export writes the Markdown and JSON forms to
`outputs/<idea_id>/` automatically. They cite the same canonical records as
`evidence.json` and require no additional provider call.

## LLM call ceilings and usage

```python
config = pc.siliconflow_config(
    API_KEY,
    model="Qwen/Qwen3.5-397B-A17B",
    max_calls=220,
)
ws = pc.Workspace.project("principia_project", llm_config=config)

print(ws.llm.usage_totals())
# calls, successful_calls, failed_calls, prompt_tokens,
# completion_tokens, total_tokens
```

Every provider attempt, including a retry or JSON repair request, consumes one
call from `max_calls`. Provider token usage is accumulated when returned by the
API and copied into generation/run metadata. `cost_limit_usd` is retained only
for source compatibility, emits a deprecation warning, and is not a currency
budget; provider prices cannot be inferred reliably by the client.

## Convenience pipeline

`Workspace.run(...)` forwards local documents, retrieval/rerank settings,
strictness, extraction resume/error behavior, exact evidence selection, and
SciDialect configuration:

```python
result = ws.run(
    goal,
    documents="private_sources",
    allow_remote_private_content=True,
    target_count=50,
    model="siliconflow:Qwen/Qwen3.6-35B-A3B",
    idea_model="siliconflow:Qwen/Qwen3.5-397B-A17B",
    compare_model="siliconflow:Qwen/Qwen3.5-397B-A17B",
    mode="scidialect-evo",
    retrieval_config=retrieval_config,
    require_target=True,
    extract_count=50,
    resume_extraction=True,
    continue_on_error=False,
    scidialect_config=pc.SciDialectConfig(allow_degraded_fallback=False),
)
```

Use the staged API when individual acceptance gates or selective reruns are
required.

For a controllable background run:

```python
config = pc.PipelineConfig.research(
    extraction_model="siliconflow:Qwen/Qwen3.6-35B-A3B",
    idea_model="siliconflow:Qwen/Qwen3.5-397B-A17B",
    comparison_model="siliconflow:Qwen/Qwen3.5-397B-A17B",
)
job = ws.start(goal, documents="private_sources", pipeline_config=config)

job.pause()
job.resume()
job.stop()
```

`PipelineJob` exposes `run_id`, `status()`, `events()`, `pause()`, `resume()`,
`stop()`, `result()`, and `display()`. Equivalent workspace methods accept a
persisted run ID. Pause occurs after the current safe provider response and
starts no further paid call until resume. Stop schedules no subsequent call and
best-effort closes a supported active transport. See [jobs.md](jobs.md).

## Resume, inspection, and compaction

```python
works = ws.load_works(limit=50)
features = ws.load_features(limit=50)
features = ws.load_features(
    model="siliconflow:Qwen/Qwen3.6-35B-A3B",
    work_ids=["Some_Work_ID"],
    latest_only=True,
)

print(ws.counts())
print(ws.storage_report())
print(ws.run_events(features.run_id))
ws.compact()
```

`load_works()` and `load_features()` do not make public-source or LLM calls.
`compact()` is non-destructive by default. Optional `keep_source_json`,
`remove_cache`, `remove_pdfs`, and `remove_private_text_cache` settings remove
only explicitly selected, regenerable artifacts. The last option removes cached
normalized local text without deleting source files.

## Display helpers

```python
from IPython.display import Markdown, display

display(Markdown(pc.feature_summary_markdown(features)))
display(Markdown(pc.idea_markdown(idea)))
display(Markdown(pc.schema_markdown(pc.ValidationPlan)))
```

The compact public notebooks live under [examples](../examples/). Each task
uses the same `tutorial.ipynb`, shared `workspace/`, and sibling `outputs/`
shape as a real project. The display bundles omit credentials, SQLite state,
embeddings, source originals, caches, raw traces, and widget state. Their
complete notebook JSON—including MIME output and metadata—is scanned for
credentials and machine-local paths.
