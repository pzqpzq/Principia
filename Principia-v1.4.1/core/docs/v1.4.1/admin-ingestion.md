# Admin ingestion and review

Admin is available only in the loopback Admin runtime. A campaign pins the active
Cloud release, commit, and logical digest before discovery. Search is paginated in
bounded provider rounds up to 20,000 results and preserves degraded-source state.
Filters distinguish `unknown` and `probe_failed` availability from `unavailable`.

A new extraction requires four selected papers and dispatches four to eight paper
workers. Every worker uses a job- and unit-specific directory under
`.principia/admin/tmp`, downloads mandatory open full text, parses, extracts,
challenges, validates, stages only metadata/Principles, then deletes PDF and
normalized text in `finally`. Cleanup failure prevents success. Pause stops new
dispatch and waits for active cleanup; cancel cancels queued work and does the
same. Restart removes orphaned temporary bytes. Resume skips committed staged
units and redownloads unfinished units from durable checkpoints.

Review presents the pinned Cloud value beside the proposal with a field-level
diff. Decisions are `add`, `update`, `retire`, or `skip`; an update appends a new
revision. Ambiguous semantic near-duplicates cannot be bulk accepted. Typed
`SUBMIT <campaign>` is the review attestation. Typed publication then creates a
`global-cloud/**`-only PR and requests auto-merge. `published` is not reported
until required checks, merge, Release construction, and control-pointer integrity
have all succeeded. Staging remains after every failure or conflict and can be
purged only after publication or explicit abandonment.
