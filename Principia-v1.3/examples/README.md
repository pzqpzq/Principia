# Principia v1.3.3 examples

These three compact projects demonstrate the same evidence-grounded workflow
across AI, computer vision, and physics:

- `test1`: communication-efficient LLM multi-agent reasoning with learned
  machine dialects;
- `test2`: uncertainty-aware sparse-view dynamic 3D reconstruction;
- `test3`: superconducting-resonator and squeezed-state axion sensing.

They are display bundles for GitHub and PyPI, not archived runtime workspaces.
Each notebook keeps concise explanatory code and a small set of meaningful
outputs. Large or sensitive runtime state is deliberately excluded.

## Project structure

Every task uses exactly one shared evidence pool and one folder per idea:

```text
testN/
  tutorial.ipynb
  workspace/
    README.md
    works.json
    features.json
    manifest.json
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

`workspace/works.json` and `workspace/features.json` contain only the compact
records needed to understand the example. All ideas in one task reference this
same pool. An output folder therefore contains no duplicate `works.json` or
`features.json`. `workspace/manifest.json` distinguishes originating acceptance
metrics from the number of records retained in the display bundle.

The release examples omit:

- credentials and authorization headers;
- absolute paths and `file://` URIs;
- SQLite databases, embeddings, provider caches, and retry histories;
- source originals and normalized private-document text;
- raw prompts, internal traces, progress frames, and widget state.

## Tutorial style

The notebooks follow a concept-first structure: a short explanation introduces
each stage, followed by a small code cell that exposes only the essential API.
The retained outputs show the research contract rather than implementation
noise:

1. public/local work and extraction counts;
2. exact evidence-kind counts and canonical record identities;
3. a compact Idea Card with source-grounded mathematics;
4. prior-idea comparison highlights;
5. standalone validation status and artifact links.

Release notebooks use environment lookup in every credential-bearing example:

```python
import os
import principia as pc

ws = pc.Workspace.project(
    ".",
    llm_config=pc.siliconflow_config(os.environ["SILICONFLOW_API_KEY"]),
    allow_remote_private_content=True,
)
job = ws.start(
    goal,
    documents="local_sources",
    pipeline_config=pc.PipelineConfig.research(),
)
result = job.result()
```

The compact display bundles may not include enough runtime state to repeat the
accepted live run in place. To run the workflow, copy the tutorial into a fresh
project, provide authorized source documents if desired, and install:

```bash
python -m pip install "principia-ai[local,notebook]==1.3.3"
export SILICONFLOW_API_KEY="your-key"
```

## Shared outputs and validation

`Workspace.project(".")` writes reusable works and features to `workspace/`.
Each generated idea is exported to `outputs/<idea_id>/`. Its `result.json`
contains relative pointers back to the shared pool, and both validation-plan
files are generated without another LLM call.

Every cited evidence item resolves exactly to
`(work_id, kind, record_id)`. Generator mode, model settings, traces, warnings,
and usage metadata cannot become scientific evidence.

Mathematical output uses `$...$` inline and `$$...$$` for display equations.
Subscripts and superscripts are semantically braced, for example $R_{cf}$,
$\boldsymbol{\Sigma}_{i}$, and $\mathrm{SNR}^{2}$. All retained expressions
must pass the shared validator and strict KaTeX compilation.

## Long-run control

The full workflow remains controllable even though transient progress output is
not retained in the public notebooks:

```python
job.status()
job.pause()
job.resume()
job.stop()
```

Pause checkpoints the current safe provider unit and starts no further paid
call until resume. Stop schedules no new work and best-effort closes a
supported active transport. The persisted `run_id` can be inspected after a
notebook or terminal is closed.

## Release verification

Before publishing, scan the complete notebook JSON and all visible artifacts,
not only code-cell source. The gate must reject credentials, local paths,
private excerpts, malformed canonical evidence, unbraced scripts, invalid
LaTeX, and stale output links. Display metrics must agree with the compact
workspace and idea manifests.
