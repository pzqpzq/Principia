# Principia Global Principles Cloud

This directory is the reviewable source of truth for Principia's Global Cloud. It stores
bibliographic metadata, immutable literature and Meta-Principle revisions,
Work–Principle provenance, foundation assessments and typed relations. It must never
contain PDFs, extracted full text, quotations,
credentials, private URLs or absolute local paths.

Records use RFC 8785 canonical JSON, one object per line. The first byte of
`sha256(stable_id)` selects one of 256 shards. GitHub Actions validates changes and builds
immutable `.pcg` snapshots and `.pcd` deltas for GitHub Releases; clients never query GitHub
as a live database.

The v1.4.0 `.pcp` catalog is frozen for compatibility. New publication uses only this
directory and appends revisions instead of overwriting history.

## Version 2 collections

`data/v2/principles/` stores literature-derived Principles and
`data/v2/meta-principles/` stores reviewed foundation records while preserving their
`meta:<area>:<slug>` identities. Both implement the same v2 Principle contract and share
the runtime FTS/vector index. `foundation-links/`, `foundation-assessments/`, and
`foundation-gaps/` make grounding explicit without forcing every solid new Principle to
inherit from an existing foundation.

The v1 canonical shards remain frozen and readable. The v1-to-v2 release transition is a
full verified snapshot so clients can retain and roll back to their previous v1 release.
