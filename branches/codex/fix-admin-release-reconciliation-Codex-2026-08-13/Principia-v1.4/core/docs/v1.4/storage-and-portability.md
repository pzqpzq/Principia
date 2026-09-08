# Storage and portability

Principia keeps private source material separate from portable scientific knowledge.
Deleting or withholding the private paper tree does not empty an exported Principles
Library: every portable Principle retains its public DOI, arXiv, or HTTPS reference,
evidence locator hashes, applicability boundary, testability, and validated relations.

## Working-directory and private-data layout

Every new v1.4 session starts from a user-selected working directory. Principia
immediately creates two explicit product boundaries below it:

```text
<working-directory>/
  workspace/       # database, parse cache, traces, and durable Principles
  local_data/      # user-owned raw source material only
```

Legacy Idea-export commands may additionally create `outputs/`; it is not part of
the Local data or durable Principle boundary.

The Principles Library exposes a native working-directory picker and an explicit
absolute-path fallback. Switching directories changes the complete active product
context. The SQLite database, provider credentials, jobs, scenarios, Local data
registry, and portable private Principles live within the selected boundary. The
paper-free `principle-packages/` library is deliberately application-level and remains
available when working directories change. An empty directory therefore has no private
knowledge after Principia creates its two structural folders, while shared packages may
still be browsed explicitly as downloaded knowledge.

An existing private folder may remain anywhere on disk and can be connected by
path. When Principia creates a literature folder, it creates a human-named folder
directly under `local_data/`.

Each registered folder is user-visible. Search acquisition writes one directory per
document so a human can understand and move the corpus without reverse-engineering
an internal cache:

```text
local_data/<folder-name>/
  README.txt
  manifest.json
  papers/
    <year-title-hash>/
      paper.pdf          # permitted PDF full text, when available
      full-text.txt      # permitted plain-text full text, instead of paper.pdf
      abstract.txt       # permitted fallback, only when full text is unavailable
```

`paper.pdf`, `full-text.txt`, and `abstract.txt` are mutually descriptive content
representations, not three copies of one paper. The UI reports document, PDF,
plain-text-full-text, and abstract-only counts separately. Private directories use
owner-only permissions and atomic writes. They must remain ignored by Git.
Normalized text and extraction metadata live under `workspace/source_cache/`,
while the paper-free durable projection lives under `workspace/principles/`.
Removing `local_data/` therefore disables raw-file access without emptying the
Principles Library or Explorer.

## Portable Principles showcase

`principia showcase export` writes exactly four deterministic files:

```text
manifest.json
principles.jsonl
works.jsonl
relations.jsonl
```

The export deliberately excludes PDFs, abstracts, quotations, raw source text,
normalized text, private paths, provider credentials, and model prompts/responses.
The manifest authenticates every file and the logical content digest. Import rejects
unexpected files, duplicate JSON keys, invalid numbers, digest mismatches, and private
path fields. Re-import is idempotent.

This is the appropriate artifact to commit in a Test repository so a clean GitHub
checkout opens with substantive Principle cards while large or redistributable paper
content stays private. Source links remain usable even if the private paper tree is
removed.

```bash
principia showcase --working-directory ./private-project export ./fixtures/principles-showcase
principia showcase --working-directory ./fresh-project import ./fixtures/principles-showcase
principia open --working-directory ./fresh-project
```

The portable artifact contains unassessed Local Principles, not reviewed Global
Capsules. Human review and Global publication remain separate governed actions.

## Shared downloadable Principle packages

The same paper-free Candidate corpus may be distributed through Principia's verified
package channel. A downloaded package is local data at runtime: Principia stores the
immutable `.pcp` and its rebuildable verified index beneath the shared
`principle-packages/` directory and continues to work offline. “Global” describes the
distribution channel, not a remote database and not a scientific review decision.

Two content classes are explicit and machine-readable:

- `reviewed_capsules`: human-reviewed Global Principle Capsules;
- `unassessed_candidates`: evidence-checked public-literature Candidates awaiting
  human review.

Both package types contain only Principle records, public bibliographic metadata,
relations, hashes, and bounded provenance. Neither contains PDFs, abstracts,
quotations, normalized source text, credentials, private paths, or job traces. The UI
shows the review state independently of installation and integrity status.

Relative artifact paths in `catalog.json` resolve from the catalog's own directory,
so a cloned Git repository can be installed without rewriting developer-specific
absolute paths:

```bash
principia open --working-directory ./my-project \
  --package-library ./principle-packages
```
