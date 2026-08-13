# v1.4.1 release QA report

Status: **local release gates passed on 2026-08-13**. GitHub publication checks
remain the authoritative gate for the repository branch and first Cloud release.

| Gate | Evidence |
|---|---|
| Migration | Count-locked v1.4.0 import: 18 Works, 62 Principles, 191 links, 36 relations; review status remains unassessed |
| Determinism | Canonical shard validation; byte-identical repeated `.pcg`; delta application compared with full target |
| Runtime | Verified atomic cache activation/rollback; SQLite FTS pagination/facets; memory-mapped float16 vectors |
| Privacy | Forbidden-field/secret/path scan; no PDF or normalized source in staged/canonical/release data |
| Admin | Four-wide dispatch, terminal-tail/retry exception, durable pause/cancel/resume, redacted provider accounting |
| UI/API | Generated OpenAPI TypeScript client; six-tab Admin; Library research-goal coordinator; Explorer memberships |
| Deployment | Checked PR, auto-merge request, post-merge release, independent redownload verification, delayed Pages pointer |

## Local evidence

- Backend: **368 passed, 2 skipped** in 135.28 seconds. The skips are existing
  optional-environment cases; there were no failures.
- Frontend: TypeScript/OpenAPI checks passed, Vitest **1 passed**, and the
  production Vite bundle built successfully.
- Python lint and bytecode compilation passed; wheel and source distribution
  built as `principia_ai-1.4.1`.
- Canonical migration validation passed with digest
  `82d1ab51ed5bceea18909f4823dbbb79c5a1d1a7a3bc2b66ec5caa723aabd35b`.
- Browser QA covered Library and all six Admin tabs at desktop and 390 px mobile;
  no error/warning logs or horizontal overflow remained after the responsive fix.
- Each of the five requested test folders is an initialized, isolated Principia
  working directory with marker, `workspace/`, `local_data/`, private secret
  directory, migration receipt, and jobs database.

The 20,000-Work/10,000-Principle performance evidence is recorded in
`qa-v1.4.1.json`: 100 complete pages, 11.935 MiB snapshot, memory-mapped vectors,
and 0.2853-second warm hybrid-search p95 on the development Mac.
