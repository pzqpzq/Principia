# Principia v1.4.1 Global Cloud

`global-cloud/data/v2/` is the reviewable source of truth. Literature Principles
and Meta-Principles are separately sharded but implement one versioned scientific
record contract and share the derived search/graph indexes. Every stable identity
is assigned to the first-byte SHA-256 shard; each JSONL row is canonical JSON and
rows are ordered by identity and revision. Git stores metadata, Principle content,
provenance links, foundation assessments/gaps, relations, schemas, and audit
receipts—never PDFs or extracted source text.

The local migration starts from verified release `20260821-06ae855fe489` rather
than the old package seed. It preserves all 676 literature Principle revisions,
233 live Works, 1,295 provenance links, and 36 relations, then accounts for the
supplied 406 Meta-Principles, 736 source Work identities, 807 evidence links, 432
relation seeds, and 30 relation gaps. Strong-identifier normalization yields 958
current unique Works. All 406 Meta revisions remain traceable; 405 are active and
the historically retired Dennard-scaling record remains as a reviewed retired
revision.

Meta records preserve their `meta:<area>:<slug>` identities. Literature records
preserve `prn:*`. `FoundationAssessment` explicitly distinguishes grounded,
ungrounded-solid, ambiguous, and invalid outcomes. A sound literature Principle
may have no compatible Meta root, and no Meta match can rescue an unsupported
claim. The 676 literature records are in the local owner-curation queue; no
retirement or foundation link becomes canonical until its individual review and
final changeset confirmation.

GitHub Releases publish derived `.pcg` SQLite/vector snapshots and `.pcd` deltas.
Pages publishes only `latest.json`, per-release controls, and `stats.json` after
the release assets have been downloaded and verified. Runtime sync uses ETags,
prefers a delta below 40 percent of the full asset, verifies all hashes/counts and
dimensions on a copy, then atomically changes the active pointer. The prior
verified generation remains available for rollback and offline use.

Background synchronization is monotonic by schema generation: a published v1
pointer may be observed while v2 is staged locally, but it cannot replace a
verified v2 snapshot. An explicit human rollback remains available.

Global retrieval is paper-first: Work FTS and vector rankings are fused, filtered,
expanded through `principle_work`, then ranked 60 percent by paper relevance and
40 percent by direct Principle relevance. Direct Principle hits fill only an
underfull linked cohort and are labeled `fallback_direct`. Missing query embeddings
or vector assets cause a visible FTS-only result, not an invented semantic score.

Use `python scripts/validate_global_cloud.py global-cloud` before review,
`scripts/migrate_global_cloud_v2.py` for the count/digest-gated migration, and
`scripts/build_global_cloud_release.py` for deterministic local release builds.
The v1 canonical shards and v1.4.0 `.pcp` catalog remain frozen and readable.
