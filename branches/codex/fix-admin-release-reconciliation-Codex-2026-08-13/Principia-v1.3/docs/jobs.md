# Background jobs and run control

`Workspace.start(...)` runs the same research pipeline as `Workspace.run(...)`
in a persisted background job. The synchronous staged APIs remain available;
background execution is useful when retrieval, extraction, or generation may
take several minutes.

## Start and wait

```python
import os
import principia as pc

ws = pc.Workspace.project(
    "project",
    llm_config=pc.siliconflow_config(os.environ["SILICONFLOW_API_KEY"], max_calls=220),
    allow_remote_private_content=True,
)
job = ws.start(
    "Your research objective",
    documents="private_sources",
    pipeline_config=pc.PipelineConfig.research(),
)
print(job.run_id)
result = job.result()
result.show()
```

`PipelineConfig.research()` is the 50-public-work preset. It requests embedding
reranking, strict target completion, an exact evidence packet of five ideas,
five principles, and five takeaways, no more than two records per work, and
strict `scidialect-evo` generation. Models can be set without expanding the
workflow:

```python
config = pc.PipelineConfig.research(
    extraction_model="siliconflow:Qwen/Qwen3.6-35B-A3B",
    idea_model="siliconflow:Qwen/Qwen3.5-397B-A17B",
    comparison_model="siliconflow:Qwen/Qwen3.5-397B-A17B",
)
```

Explicit arguments to `Workspace.start(...)` and `Workspace.run(...)` override
the corresponding configuration fields.

## States and progress

A parent pipeline moves through these persisted states:

```text
queued -> running -> complete
                  -> pause_requested -> paused -> running
                  -> cancel_requested -> cancelled
                  -> error
```

Progress is weighted and monotonic across retrieval, local ingestion,
extraction, evidence selection, generation, comparison, and export. The parent
record retains stage, message, elapsed time, optional ETA, counts, errors, and
an event log.

```python
status = job.status()
print(status.status, status.stage, status.progress)
events = job.events()
```

Recent persisted runs are available through `ws.runs()` and the CLI:

```bash
principia --workspace project/workspace runs
principia --workspace project/workspace status RUN_ID
```

## Pause, resume, and stop

```python
job.pause()
job.resume()
job.stop()
```

or, when only a persisted run ID is available to the same live worker process:

```python
ws.pause(run_id)
ws.resume(run_id)
ws.stop(run_id)
```

Pause is cooperative and occurs at a safe boundary. An in-flight provider
response is allowed to finish and checkpoint; no subsequent paid call starts
until resume. Completed retrieval pages, embedding batches, source text, and
extraction chunks remain available for resumption.

Stop requests cancellation and schedules no further unit of work. If the
active HTTP transport supports closing the request, Principia asks it to close;
otherwise the bounded current request may finish before the run becomes
`cancelled`. A stopped job raises `RunCancelledError` from `result()`.

```bash
principia --workspace project/workspace pause RUN_ID
principia --workspace project/workspace resume RUN_ID
principia --workspace project/workspace stop RUN_ID
```

Provider retries, retry backoff, retrieval waits, embedding batches,
full-text requests, chunk extraction, and LLM calls share the same cooperative
control boundary. `cancel_token=` remains available on staged APIs for backward
compatibility.

## Notebook and terminal display

`PipelineConfig.progress` accepts `auto`, `notebook`, `rich`, `text`, or
`none`. `auto` uses an `ipywidgets` panel with Pause, Resume, and Stop buttons
when notebook extras are installed:

```bash
python -m pip install "principia-ai[notebook]==1.3.3"
```

Without widget support, Principia falls back to text. Terminal sessions retain
Rich or text progress and can use CLI controls from a second terminal.

The display is a view of persisted state; closing a notebook output does not
erase the run while its Python worker remains alive. Keep the printed `run_id`
so the workspace or CLI can inspect and control it from that process.

## Call ceiling and resumability

Use `LLMConfig.max_calls` or `siliconflow_config(..., max_calls=N)` as an
explicit provider-call ceiling. The legacy currency-limit setting is deprecated
because provider pricing cannot be inferred reliably.

Safe pause and stop do not roll back completed work. Reopening the workspace
applies idempotent migrations and preserves SQLite checkpoints and run history.
The v1.3.3 background runner is thread-backed, however: ending the Python
process ends that runner, and `resume(run_id)` does not recreate it in a new
process. Resume within the original live worker, or restart the affected staged
API from its persisted retrieval/extraction checkpoints. A completed portable
result remains in `outputs/<idea_id>/result.json`. Legacy `Workspace(path)`
projects continue to expose `principia_outputs/latest/`.
