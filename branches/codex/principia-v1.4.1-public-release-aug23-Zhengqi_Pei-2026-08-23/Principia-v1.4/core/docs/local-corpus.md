# Private corpus ingestion

Principia v1.3.3 can use a user-supplied folder as supplemental research
evidence. The online `target_count` and the local corpus are independent: a
50-work search with five accepted local documents produces 55 works for
extraction, not 50.

## Install and ingest

The core package supports PDF, HTML/XML, Markdown, RST, LaTeX, plain text and
code, JSON/JSONL, YAML, CSV/TSV, and safely decodable unknown text.

```bash
python -m pip install principia-ai==1.3.3
```

DOCX, PPTX, and XLSX require the optional parsers:

```bash
python -m pip install "principia-ai[local]==1.3.3"
```

Use the staged API when ingestion itself is the desired operation:

```python
import principia as pc

ws = pc.Workspace.project("project")
works = ws.research.ingest_local(
    "private_sources",
    config=pc.LocalCorpusConfig(corpus_name="lab-notes"),
)

print(works.local_count)
print(works.local_diagnostics.model_dump(mode="json"))
```

Use `documents=` in a complete synchronous or background pipeline:

```python
result = ws.run(goal, documents="private_sources", allow_remote_private_content=True)

job = ws.start(
    goal,
    documents=["private_sources", "internal_results"],
    allow_remote_private_content=True,
)
```

Explicit `Workspace.run(...)` and `Workspace.start(...)` keyword arguments take
precedence over `PipelineConfig` defaults.

## Privacy boundary

Every accepted file becomes a `WorkItem` with a portable URI:

```text
local://<corpus>/<relative-path>
```

The absolute source path is retained only in hidden SQLite state so that the
same workspace can resume extraction. It is not placed in LLM metadata, source
JSON, exports, generated README files, or release notebooks. Principia does not
copy the original file. It caches normalized text in hidden workspace state.

Local text is private by default. Before a non-mock remote provider receives
that text, the caller must set either:

```python
ws = pc.Workspace.project("project", allow_remote_private_content=True)
```

or the per-run override:

```python
ws.run(goal, documents="private_sources", allow_remote_private_content=True)
```

The provider receives normalized document content and portable identifiers,
not absolute filesystem paths. Consent should be enabled only after checking
the provider's data-handling terms and obtaining any required authorization.

To remove cached normalized private text after an export:

```python
ws.compact(remove_private_text_cache=True)
```

This does not delete the user's originals. Other workspace records and exports
remain intact.

In the project layout, local and public work metadata is consolidated in
`workspace/works.json`, and extracted records are consolidated in
`workspace/features.json`. Generating another idea writes only a new
`outputs/<idea_id>/` folder; it does not copy the corpus or feature pool.

## Default limits and skip policy

`LocalCorpusConfig` defaults to:

| Setting | Default |
| --- | ---: |
| recursive scan | yes |
| maximum files | 500 |
| maximum bytes per file | 50 MiB |
| hidden files | excluded |
| symbolic links | not followed |
| chunk size | 24,000 characters |
| chunk overlap | 2,000 characters |

Archives, symlinks, device files, encrypted or corrupt documents, legacy
Office files (`.doc`, `.ppt`, `.xls`), and opaque image/audio/video files are
skipped with a `LocalSourceReport`. Core v1.3.3 does not bundle OCR,
audio/video transcription, or legacy Office conversion. A parser failure is
reported per file and does not erase successfully parsed neighbors.

`LocalCorpusDiagnostics` reports discovered, accepted, cached, duplicate,
skipped, and failed counts plus byte/character totals, warnings, and one
portable report per file. Accepted files and partial failures are therefore
distinguishable.

## Identity, deduplication, and cache invalidation

Principia records both the full-byte SHA-256 and the normalized-text SHA-256,
along with MIME type, parser fingerprint, chunk count, status, and warnings.

- Exact byte duplicates are deduplicated.
- Distinct local files with the same title remain distinct.
- A local document and a public work merge only when they share a strong
  scholarly identifier.
- A file-content or parser-fingerprint change invalidates only that source's
  extraction cache.
- `WorkItem.content_sha256` contains the normalized content identity.

The `source_assets` migration is idempotent when an older v1.3 workspace is
opened.

## Long documents

Long normalized text is divided into overlapping chunks. Every chunk is sent
through the configured extraction LLM. When a document has more than one
chunk, Principia performs an additional LLM consolidation pass that deduplicates
only grounded records. It does not synthesize a deterministic feature bundle.

Completed chunk extractions are checkpointed. A paused, cancelled, or failed
run can therefore resume without repeating completed provider calls when the
content, parser, extractor prompt, schema, and model identity are unchanged.

## Parser registration

An extension parser receives the local `Path` and file bytes and returns
normalized text. For example:

```python
import principia as pc

def read_epub(path, data):
    return your_epub_reader(data)

pc.register_local_parser(
    "organization-epub",
    read_epub,
    extensions=[".epub"],
    mime_types=["application/epub+zip"],
    version="1",
)
```

Increase `version` whenever parser behavior changes. The resulting fingerprint
then invalidates only affected cached sources. Registered parsers must return
document text, not filesystem paths, credentials, or unrelated metadata.

## Prompt-injection boundary

Local and public source content is delimited as untrusted quoted data in every
LLM stage. Embedded instructions, role changes, tool requests, and output-format
requests are research content to analyze—not commands to follow. This boundary
does not replace ordinary data governance: users should still review a corpus
before authorizing remote processing.
