# Principia v1.4.1 Global Cloud

`global-cloud/data/v1/` is the reviewable source of truth. Each stable identity is
assigned to the first-byte SHA-256 shard, each JSONL row is canonical JSON, and
rows are ordered by identity and revision. Git stores metadata, Principle content,
provenance links, relations, schemas, and audit receipts—never PDFs or extracted
source text.

GitHub Releases publish derived `.pcg` SQLite/vector snapshots and `.pcd` deltas.
Pages publishes only `latest.json`, per-release controls, and `stats.json` after
the release assets have been downloaded and verified. Runtime sync uses ETags,
prefers a delta below 40 percent of the full asset, verifies all hashes/counts and
dimensions on a copy, then atomically changes the active pointer. The prior
verified generation remains available for rollback and offline use.

Global retrieval is paper-first: Work FTS and vector rankings are fused, filtered,
expanded through `principle_work`, then ranked 60 percent by paper relevance and
40 percent by direct Principle relevance. Direct Principle hits fill only an
underfull linked cohort and are labeled `fallback_direct`. Missing query embeddings
or vector assets cause a visible FTS-only result, not an invented semantic score.

Use `python scripts/validate_global_cloud.py global-cloud` before review and
`scripts/build_global_cloud_release.py` for deterministic local release builds.
The migration command in `scripts/migrate_v140_global_cloud.py` is count- and
digest-gated against the three frozen v1.4.0 packages.
