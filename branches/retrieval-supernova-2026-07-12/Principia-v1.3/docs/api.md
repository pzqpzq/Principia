# Principia V1.3 API

## Install And Import

```bash
pip install principia-ai
```

```python
import principia as pc
```

The installed distribution is `principia-ai` for the initial release. The import package is `principia`.

## Workspace

```python
ws = pc.Workspace("./my_project")
```

The workspace creates this local layout:

```text
README.md
principia_outputs/
  README.md
  latest/
    idea.md
    result.json
    works.json
  exports/
    <idea_id>/
      idea.md
      result.json
      works.json
.principia/
  principia.sqlite
  artifacts/
    pdfs/
    source_json/
    runs/
    exports/
    cache/
```

Visible user-facing exports are written to `principia_outputs/`. Internal SQLite state, run logs, and caches remain in hidden `.principia/`. Private notes, prompts, full text, generated ideas, and API keys remain local unless user code explicitly exports them.

## Staged Quickstart

The primary notebook and script API is staged. This keeps each long operation visible, cancellable, and resumable:

```python
import principia as pc

API_key = "sk-your-key-here"
goal = "your research goal"

ws = pc.Workspace("./my_project", llm_config=pc.siliconflow_config(API_key))
progress = pc.notebook_progress

works = ws.research.search(goal, target_count=50, callback=progress("Research search"))
features = ws.research.extract(
    works[:20],
    model="siliconflow:deepseek-ai/DeepSeek-V4-Pro",
    callback=progress("Information extraction"),
)
selected_evidence = pc.select_evidence(
    features,
    kinds=["ideas", "principles", "takeaways", "baselines", "benchmarks", "result_facts"],
)
idea = ws.ideas.generate(
    selected_evidence,
    user_note=goal,
    mode="calculus",
    model="siliconflow:Qwen/Qwen3.5-397B-A17B",
    callback=progress("Idea generation"),
)
comparison = ws.ideas.compare(
    idea,
    features,
    model="siliconflow:Qwen/Qwen3.5-397B-A17B",
    callback=progress("Idea comparison"),
)
export_path = ws.export(goal=goal, works=works, features=features, idea=idea, comparison=comparison)
```

`target_count` controls real public work retrieval. In the official tutorial, retrieving 50 works but extracting the top 20 keeps runtime bounded while preserving the full research list. Completed extraction records are skipped on rerun unless `overwrite=True`.

`Workspace.run(...)` remains available as a convenience wrapper for production scripts that want the whole workflow in one call.

Notebook progress is packaged and passed as a callback to each long operation. It reports elapsed time, ETA, run stage, progress, and per-stage counts. Long LLM calls emit heartbeat updates while waiting for the provider response:

```python
features = ws.research.extract(
    works[:20],
    model="siliconflow:deepseek-ai/DeepSeek-V4-Pro",
    callback=pc.notebook_progress("Information extraction"),
)
```

## Resume From Existing Research

Use the same workspace folder to continue from data already stored in SQLite. This is the recommended workflow when opening a new notebook after search and extraction have already finished:

```python
import principia as pc

API_key = "sk-your-key-here"
goal = "your research goal"

ws = pc.Workspace("./my_project", llm_config=pc.siliconflow_config(API_key))

works = ws.load_works()
features = ws.load_features()
selected_evidence = pc.select_evidence(features)

idea = ws.ideas.generate(
    selected_evidence,
    user_note=goal,
    mode="calculus",
    model="siliconflow:Qwen/Qwen3.5-397B-A17B",
    callback=pc.notebook_progress("Idea generation"),
)
```

No public search or LLM extraction is run by `load_works()` or `load_features()`.

Filtering options:

```python
features = ws.load_features(limit=50)
features = ws.load_features(model="siliconflow:deepseek-ai/DeepSeek-V4-Pro")
features = ws.load_features(work_ids=["Some_Work_ID"])
features = ws.load_features(latest_only=False)
```

Equivalent service-level methods are available as `ws.research.load_works(...)` and `ws.research.load_features(...)`.

## Storage Inspection And Compaction

Use `storage_report()` to inspect workspace sizes:

```python
ws.storage_report()
```

Returned keys include `workspace`, `internal`, `database`, `database_wal`, `artifacts`, `source_json`, `exports`, `pdfs`, `cache`, and `visible_outputs`, measured in bytes.

Use `compact()` to checkpoint and vacuum SQLite:

```python
ws.compact()
```

The default is non-destructive. It keeps works, extractions, generated ideas, exports, PDFs, and source JSON. Optional cleanup removes only regenerable artifacts:

```python
ws.compact(keep_source_json=1, remove_cache=True)
ws.compact(remove_pdfs=True)  # only when retained PDFs are no longer needed
```

## Public Types

- `Workspace`: top-level local framework object.
- `WorkItem`: one source work with title, authors, abstract, venue, links, DOI/arXiv/OpenAlex IDs, and metadata.
- `WorkList`: ordered search result list.
- `WorkFeatures`: extracted ideas, principles, baselines, benchmarks, takeaways, and result facts for one work.
- `ExtractedFeatures`: batch extraction result.
- `EvidencePacket`: explicit generation input packet.
- `Idea`: generated idea card.
- `IdeaComparison`: comparison rows against prior ideas.
- `PipelineResult`: output from `Workspace.run(...)`.
- `RunHandle`, `RunStatus`, `CancelToken`: progress, cancellation, and persisted run state.
- `LLMConfig`, `LLMClient`: OpenAI-compatible model configuration.

## Core Schemas

`WorkFeatures` contains the extracted feature buckets for one work:

| Field | Meaning |
| --- | --- |
| `work_id`, `title`, `model` | Source work identity and extraction model. |
| `ideas` | Prior or existed ideas, typically with `id`, `title`, `core_idea`, `mechanism`, `discussion`, `evidence`. |
| `principles` | Reusable principles, typically with `id`, `name`, `argument`, `boundary_conditions`, `discussion`, `evidence`. |
| `takeaways` | Actionable lessons, typically with `id`, `title`, `message`, `condition`, `actionable_lesson`, `evidence`. |
| `baselines`, `benchmarks`, `result_facts` | Comparison methods, evaluation settings, and grounded result facts. |

`EvidencePacket` is the generation input. Create it with:

```python
selected_evidence = pc.select_evidence(
    features,
    kinds=["ideas", "principles", "takeaways"],
    feature_ids=["Some_Feature_ID"],
)
```

If `kinds`, `work_ids`, and `feature_ids` are omitted, all extracted features are selected.

`Idea` contains the generated idea card:

| Field | Meaning |
| --- | --- |
| `id`, `title`, `thesis`, `mode`, `model` | Stable identity, headline, one-sentence thesis, generation mode, and model. |
| `novelty_claim`, `mechanism_design` | Claimed difference and mechanistic design. |
| `methodological_details` | V1.2-style method block with `summary`, `symbols`, `equations`, `workflow`, and `reliability_checks`. Equations can contain LaTeX. |
| `method_variants`, `why_it_might_work`, `validation_protocol` | Variants, rationale, and validation plan. |
| `baselines`, `metrics`, `risks`, `assumptions`, `derived_principles` | Evaluation and risk structure. |
| `source_evidence`, `evidence_work_ids` | Selected extracted features used as evidence. |
| `lineage`, `trace`, `generation_metadata` | Calculus/SciDialect metadata and selected-evidence counts. |

Useful display helpers:

```python
display(Markdown(pc.feature_summary_markdown(features)))
display(Markdown(pc.idea_markdown(idea)))
display(Markdown(pc.schema_markdown(pc.Idea)))
```

## Search

```python
works = ws.research.search(
    "machine dialects for multi-agent scientific discovery",
    target_count=20,
    sources=["arxiv", "openalex", "crossref"],
)
```

Search uses public metadata sources and deduplicates by DOI, arXiv ID, OpenAlex ID, and normalized title. By default, OpenAlex and Crossref are queried before arXiv, ranking includes a peer-reviewed metadata bonus, and duplicate records are merged so a peer-reviewed venue is preferred over an arXiv-only venue while retaining arXiv IDs and links. Results are persisted to SQLite by default and exported to `.principia/artifacts/source_json/`.

Use `pc.work_review_status(work)` to display whether a result is currently marked `peer-reviewed`, `preprint`, or `unknown`.

## Extraction

```python
features = ws.research.extract(
    works,
    model="openai:gpt-4.1",
    overwrite=False,
    retain_pdfs=False,
)
```

Extraction fetches transient full text when available. PDFs are not retained unless `retain_pdfs=True` or `pdf_dir=...` is supplied. Completed extractions are cached by work, model, and content hash. Restarted runs skip completed work unless `overwrite=True`.

Tests can inject a custom `LLMClient`, but production tutorials should pass an explicit provider model and a real API key.

## Idea Generation

```python
selected_evidence = pc.select_evidence(
    features,
    kinds=["ideas", "principles", "takeaways", "baselines", "benchmarks", "result_facts"],
)
idea = ws.ideas.generate(
    selected_evidence,
    user_note="focus on token efficiency",
    mode="calculus",
    model="openai:gpt-4.1",
)
```

Supported modes:

- `standard`: direct evidence synthesis.
- `calculus` or `principia_calculus`: symbolic lineage-backed synthesis.
- `scidialect_evo` or `scidialect-evo`: internal candidate evolution with trace metadata.

Generation modes are tools, not evidence. Principia sends mode labels to the LLM as internal strategy metadata, filters ungrounded tool/mode names out of generated idea content, and only accepts `source_evidence` rows that can be grounded to selected feature IDs or work IDs.

Online generation raises when no callable LLM is configured. Pass a valid API key through `pc.siliconflow_config(...)`, `pc.LLMConfig(...)`, or provider environment variables.

## Idea Comparison

```python
comparison = ws.ideas.compare(idea, works, model="openai:gpt-4.1")
```

Comparison first builds a lexical shortlist from extracted prior ideas, then asks the configured LLM for row-level mechanistic comparisons. It does not silently fall back to template comparison when the requested LLM is unavailable.

## Progress And Cancellation

Every long operation persists a run record and run events:

```python
events = ws.run_events(features.run_id)
```

Use callbacks for notebook or app integrations:

```python
def on_progress(status: pc.RunStatus):
    print(status.stage, status.progress)

works = ws.research.search("topic", callback=on_progress)
```

Use `show_progress=True` for Rich terminal progress bars. `KeyboardInterrupt` marks the current run cancelled and preserves completed records.

## LLM Configuration

Environment variables:

- `OPENAI_API_KEY`
- `PRINCIPIA_OPENAI_BASE_URL`
- `SILICONFLOW_API_KEY`
- `PRINCIPIA_LLM_BASE_URL`
- `PRINCIPIA_MODEL`

SiliconFlow model strings use the same provider-prefix syntax as OpenAI:

```python
features = ws.research.extract(works, model="siliconflow:deepseek-ai/DeepSeek-V4-Pro")
idea = ws.ideas.generate(features, mode="calculus", model="siliconflow:Qwen/Qwen3.5-397B-A17B")
```

Explicit configuration:

```python
config = pc.LLMConfig.from_model(
    "custom:my-model",
    api_key="...",
    base_url="https://example.com/v1",
)
ws = pc.Workspace("./my_project", llm_config=config)
```

Secrets are redacted before being persisted in prompts, notes, or logs.

## Official Tutorial

The official notebook is [examples/principia_v13_tutorial.ipynb](../examples/principia_v13_tutorial.ipynb). It demonstrates a staged real-LLM workflow with:

- 50-work public search.
- Top-20 information extraction.
- Evidence selection through `pc.select_evidence(...)`.
- Idea generation with `calculus` mode.
- Prior-idea comparison.
- Visible export inspection under `principia_project/principia_outputs/latest/`.

The checked-in notebook intentionally contains `API_key = "YOUR_SILICONFLOW_API_KEY"` and no executed outputs. Users should replace the key only in their own local runtime copy.
