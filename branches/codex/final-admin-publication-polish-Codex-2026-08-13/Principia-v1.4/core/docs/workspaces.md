# Projects, workspaces, and outputs

Principia separates reusable research evidence from idea-specific results. The
recommended entry point is:

```python
import principia as pc

ws = pc.Workspace.project(".")
```

`Workspace.project(root)` creates a visible project with two siblings:

```text
root/
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

## Shared research pool

`workspace/works.json` and `workspace/features.json` describe the common pool
used by every idea in the project. A later generation can select a different
evidence packet from the same pool without copying works into the new idea
folder. `workspace/manifest.json` records counts and portable relative links to
all exported ideas.

The hidden `workspace/.principia/` directory holds SQLite checkpoints, cached
normalized text, and resumability data. It is runtime state, not a release
artifact. Public examples omit this directory, embeddings, provider responses,
private sources, and other regenerable caches.

## Idea-specific outputs

Each `outputs/<idea_id>/` folder is self-contained except for its explicit
relative references to the shared pool:

- `idea.md` is the readable Idea Card.
- `idea.json` is its structured scientific content without internal traces.
- `evidence.json` is the exact canonical evidence packet.
- `comparison.json` contains prior-idea comparison results.
- `result.json` is a compact manifest that points to shared works and features.
- `validation_plan.md` is the human-readable validation hand-off.
- `validation_plan.json` is the schema-valid validation hand-off.

The Markdown and JSON validation plans are produced without another LLM call
and use the same canonical evidence references as the Idea Card.

## Portable paths

Shareable JSON and Markdown contain only project-relative paths and portable
identifiers such as `local://corpus/relative-file.md`. Absolute source paths
remain in hidden runtime state and are never placed in LLM metadata, exports,
or public notebooks.

## Backward compatibility

`Workspace(path)` remains supported and uses the v1.3.0-v1.3.2 compatible
layout under `path/principia_outputs/`. Use it when opening an existing legacy
workspace. New tutorials and projects should use `Workspace.project(root)` so
that multiple ideas share one works/features pool.

