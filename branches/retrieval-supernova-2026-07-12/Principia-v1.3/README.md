# Principia V1.3

Principia V1.3 is a local-first Python framework for research search, paper feature extraction, evidence-grounded idea generation, and prior-idea comparison.

The import package is `principia`. The initial PyPI distribution name is `principia-ai` because the `principia` distribution name is currently occupied on PyPI. If that ownership issue is resolved later, the import API remains unchanged.

## Install

```bash
pip install principia-ai
```

For notebooks:

```bash
pip install principia-ai ipykernel
python -m ipykernel install --user --name principia-v13-python --display-name "Python 3.12 (Principia V1.3)"
```

## Quickstart

```python
import principia as pc

API_key = "sk-your-key-here"
goal = "provide real-time, calibrated, actionable process quality control for autonomous coding agents operating on large-scale repositories"

ws = pc.Workspace(
    "./principia_project",
    llm_config=pc.siliconflow_config(API_key, timeout=420, max_retries=2),
)

works = ws.research.search(goal, target_count=50)
features = ws.research.extract(
    works[:20],
    model="siliconflow:deepseek-ai/DeepSeek-V4-Pro",
    overwrite=False,
)
selected_evidence = pc.select_evidence(features)
idea = ws.ideas.generate(
    selected_evidence,
    user_note=goal,
    mode="calculus",
    model="siliconflow:Qwen/Qwen3.5-397B-A17B",
)
comparison = ws.ideas.compare(idea, features, model="siliconflow:Qwen/Qwen3.5-397B-A17B")

export_path = ws.export(
    goal=goal,
    works=works,
    features=features,
    idea=idea,
    comparison=comparison,
)
```

## Continue From Existing Features

If research and extraction already finished in an earlier notebook, reopen the same workspace and load persisted features:

```python
import principia as pc

API_key = "sk-your-key-here"
goal = "your research goal"

ws = pc.Workspace("./principia_project", llm_config=pc.siliconflow_config(API_key))
features = ws.load_features()
selected_evidence = pc.select_evidence(features)

idea = ws.ideas.generate(
    selected_evidence,
    user_note=goal,
    mode="calculus",
    model="siliconflow:Qwen/Qwen3.5-397B-A17B",
)
```

This does not rerun public search or LLM extraction.

## What Principia Provides

- Hybrid research search over OpenAlex, Crossref, and arXiv.
- DOI/arXiv/OpenAlex/title deduplication with peer-reviewed venue promotion.
- Structured extraction of ideas, principles, baselines, benchmarks, takeaways, and result facts.
- Evidence selection through `pc.select_evidence(...)`.
- Idea generation modes: `standard`, `calculus`, and `scidialect_evo`.
- Generation modes are internal strategies, not evidence; generated `source_evidence` is grounded to selected work/feature IDs.
- Prior-idea comparison using lexical shortlisting plus the configured LLM.
- Notebook and terminal progress with ETA, heartbeat updates during long LLM calls, cancellation, and resume-by-cache behavior.
- Local SQLite storage with visible user-facing exports.

## Workspace Layout

Principia creates visible files under the workspace root:

```text
principia_project/
  README.md
  principia_outputs/
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
      source_json/
      exports/
      pdfs/
      cache/
```

The `.principia/` folder stores internal SQLite state, cache data, and canonical artifacts. The visible `principia_outputs/` folder mirrors the latest readable outputs for inspection.

Inspect and compact storage:

```python
ws.storage_report()
ws.compact()
```

`ws.compact()` checkpoints and vacuums SQLite without deleting works, features, ideas, or exports. Optional cleanup knobs such as `keep_source_json=1` and `remove_cache=True` only remove regenerable artifacts.

## Tutorial And Docs

- Official tutorial notebook: [examples/principia_v13_tutorial.ipynb](examples/principia_v13_tutorial.ipynb)
- Example setup notes: [examples/README.md](examples/README.md)
- API reference: [docs/api.md](docs/api.md)
- Publishing checklist: [docs/publishing.md](docs/publishing.md)

The official tutorial contains no real API key and no executed outputs. Replace `YOUR_SILICONFLOW_API_KEY` at runtime in your own local copy.
