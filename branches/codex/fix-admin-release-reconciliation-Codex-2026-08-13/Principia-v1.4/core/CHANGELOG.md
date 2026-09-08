# Changelog

## 1.3.3 - 2026-07-16

- Consolidated project UX around one reusable `workspace/` evidence pool and
  per-idea `outputs/<idea_id>/` research packs, with concise output-bearing
  tutorials for the LLM-MAS, dynamic 3D reconstruction, and physics examples.
- Hardened mathematical normalization so subscript and superscript operands are
  explicitly braced (for example, `$R_{cf}$`), repeated scripts are rejected,
  and every retained release formula is structurally checked and compiled with
  strict KaTeX during QA.

- Added observable, retrying, cross-domain retrieval with strict target
  completion, source diagnostics, biomedical routing, explicit embedding-rerank
  state, and a transparent process-local repeated-search stability anchor.
- Normalized scholarly-title markup before identity matching and display, and
  made per-provider query execution order deterministic so repeated retrievals
  remain stable without weakening source-specific query plans.
- Updated OpenAlex access for its key-based API using optional
  `OPENALEX_API_KEY`, removed the retired `mailto` mechanism, and redacted
  provider credentials from persisted source errors.
- Added domain-neutral feature semantics and provenance-aware extraction cache identities.
- Added recursive private-folder ingestion with portable `local://` identities,
  bounded parsing, per-file diagnostics, selective cache invalidation, optional
  Office parsers, and an extension registry for OCR/transcription/organization
  formats.
- Added explicit consent before private document content is sent to a remote
  model. Original files are never copied, and shareable artifacts never expose
  absolute source paths.
- Added chunk-level extraction and real-LLM consolidation for long local
  documents, with resumable checkpoints and parser/content fingerprints.
- Added bounded real-LLM recovery for token-truncated JSON and unsafe decoded
  control escapes; repairs remain source-grounded and unresolved output still
  fails without being persisted.
- Strengthened live proposal grounding with robust scientific anchor tokens,
  structured methodology fields, and the complete research goal in generation
  prompts. Failed-call usage is now persisted even when validation fails, while
  invalid ideas remain fail-closed and unsaved.
- Added strict canonical evidence references. Generation and validation plans
  now resolve every citation by `(work_id, kind, record_id)` and hydrate source
  text from the selected record. Mixed local/public packets require at least one
  canonical citation from each source class, with one live grounded repair and
  fail-closed persistence when the mix remains incomplete.
- Removed live template fallbacks and generator-as-evidence leakage. Explicit
  mock execution remains a labeled synthetic fixture and cannot satisfy release
  showcase gates.
- Added strict three-stage SciDialect-Evo generation as the direct API and CLI
  default, while preserving explicit `calculus` compatibility. Also added
  global evidence-packet constraints, comparison-input isolation, and LLM
  call/token accounting.
- Added shared LaTeX tokenization, normalization, structural validation, and
  release-time strict KaTeX verification.
- Canonicalized retained mathematical fields and supported Unicode notation to
  safe LaTeX delimiters and commands before structural and KaTeX validation.
- Added persisted background pipelines with weighted progress, safe-boundary
  pause/resume, best-effort stop, notebook controls, terminal fallbacks, and CLI
  run-control commands.
- Added portable Markdown and JSON validation plans to every idea export.
- Added idempotent workspace migrations, collision-resistant concurrent run
  identifiers, byte-stable no-op workspace reopening, and stronger
  cross-provider identity handling.
- Canonicalized DOI/arXiv/OpenAlex transport forms and rechecked strict targets after SQLite reconciliation.
- Added curated, output-bearing showcase gates that scan complete notebook JSON
  for credentials, private paths, private excerpts, and transient UI state.
- Added Python 3.10-3.13 CI, core and `[local]` smoke checks, and wheel-content
  verification for both public packages and typing markers.

## 1.3.2

- Published the initial `principia-ai` V1.3 framework package.
