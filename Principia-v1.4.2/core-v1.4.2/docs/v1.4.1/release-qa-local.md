# Principia v1.4.1 local acceptance report

Date: 2026-08-22

Status: local implementation complete; GitHub publication intentionally blocked
pending owner acceptance.

## Verified local Cloud

- Active QA release: `local-v2-meta-20260822-qa2`
- Works: 958
- Literature Principles: 676
- Active Meta-Principles: 405 (406 revisions retained)
- Current searchable Principles: 1,081
- Principle–Work provenance links: 2,101
- Relations: 468
- Foundation assessments: 676
- Foundation gaps: 30
- Vector contract: Qwen3-Embedding-4B, 1,024 dimensions, normalized float16
- Work and Principle vector files: complete and memory-mapped

The v2 snapshot was reactivated with the verified live v1 release retained for
rollback. A real forced background sync observed published v1 release
`20260821-06ae855fe489` and returned `schema_downgrade_blocked`; the active v2
pointer remained unchanged.

## Automated verification

- Backend plus private Admin: 430 passed, 2 skipped.
- Public frontend: 5 passed.
- Public and private TypeScript checks: passed.
- Public and private production frontend builds: passed.
- Real 1.4.1 wheel and sdist: built successfully.
- Archive hygiene: 3,481 members and more than 14.3 million bytes scanned; no unsafe
  content and zero Admin-named members in either public artifact.
- All five requested test working directories contain genuine Principia markers
  and isolated workspace state.

## Scale evidence

The local scale fixture contains 20,000 Works, 10,000 current Principles, 20,000
provenance links, and 50,000 graph edges.

- Complete pagination: 20,000 items across 100 pages.
- Compressed snapshot: 17.988 MiB (limit: 250 MiB).
- Warm hybrid search p95: 0.0806 seconds; maximum: 0.0806 seconds.
- Bounded graph tile: 2,500 nodes and 2,000 overview edges; close views retain
  at least 500 edges while rich-card rendering remains capped at 160 nodes.
- Graph viewport p95: 0.0774 seconds; maximum: 0.1074 seconds.
- Vector files remained memory-mapped and complete.
- After activating the optimized real v2 snapshot, the live loopback API returned
  all 1,081 current nodes and 463 visible validated edges in 0.0643 seconds.

## Human-facing browser QA

The loopback regular and private Admin applications were exercised through the
in-app browser, not only through API tests.

- New Research created and reopened a durable Global-only session.
- A post-restart browser reload settled at 1,081 Cloud Principles; the private
  Admin dashboard settled at 958 Works, 676 literature Principles, 405 active
  Meta-Principles, and two preserved legacy publications needing attention.
- Semantic search returned relevant multi-agent/autonomous-discovery Principles.
- Foundation results were verified as real `meta:*` records after the v1 fallback
  labeling and schema-downgrade defects were fixed.
- The shared inspector displayed rich Meta structure, differentiated metrics,
  and working public paper links.
- Add Global returned literature and Meta records; an added Meta-Principle was
  still present after reload.
- The virtual-Principle cart accepted two selections and displayed `2/20` without
  making a paid provider call.
- `/library` redirected to `/research/new`; `/local` redirected to the in-place
  local settings disclosure.
- Admin Dashboard, 676-item paged curation queue, semantic Meta catalog/editor,
  persisted extraction progress, Review & Compare, and publication status were
  opened and inspected.
- A persisted 100-paper Admin campaign showed 41 staged papers, two provider
  failures, eight acquisition failures, and 49 scientific quarantines with
  explicit per-paper explanations—confirming that failures are no longer
  collapsed into an unusable all-failed state.
- Two legacy publication records were safely reconciled from indefinite
  `syncing` into explicit attention items; the active Cloud was unchanged and
  their local staging remains preserved.

## Owner gates still intentionally open

The generated curation queue accounts for all 676 live literature Principles:
23 duplicate-review suggestions, 72 scientific-review suggestions, and 581
grounding-review suggestions. No suggested retirement or Meta foundation link
has been applied without owner confirmation.

No GitHub branch, PR, commit, release, or Pages pointer was created during this
implementation. Publication requires the owner's explicit acceptance and will
use one consolidated public changeset; future private Admin changesets remain
data-only and path-allowlisted to `global-cloud/**`.
