# Principia Global Principles Cloud

This directory is the reviewable source of truth for Principia's Global Cloud. It stores
bibliographic metadata, immutable Principle revisions, Work–Principle provenance and
Principle relations. It must never contain PDFs, extracted full text, quotations,
credentials, private URLs or absolute local paths.

Records use RFC 8785 canonical JSON, one object per line. The first byte of
`sha256(stable_id)` selects one of 256 shards. GitHub Actions validates changes and builds
immutable `.pcg` snapshots and `.pcd` deltas for GitHub Releases; clients never query GitHub
as a live database.

The v1.4.0 `.pcp` catalog is frozen for compatibility. New publication uses only this
directory and appends revisions instead of overwriting history.
