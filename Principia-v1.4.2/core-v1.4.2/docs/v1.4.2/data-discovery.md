# Dataset-native Autonomous Scientific Discovery

Principia v1.4.2 treats scientific datasets as datasets, not as papers. A run creates
versioned `DataAsset`, `DataView`, `DataHypothesis`, `AnalysisPlan`, `TestResult`,
`ComputedEvidenceAnchor`, and `DataFinding` records. `USER_BRIEF.txt` can guide
interpretation but is never scientific evidence.

## Workflow

1. **Inventory** streams hashes and inspects magic bytes, structures, roles, and limitations.
2. **Understand** infers candidate series, joins, coordinates, modalities, and independent units.
3. **Analyze** executes deterministic operators and, only behind verified isolation, audited Python.
4. **Challenge** preserves nulls and contradictions while checking specifications, missingness,
   confounders, falsifiers, and Benjamini-Hochberg test families.
5. **Synthesize** connects surviving patterns to established Principles and prepares—not
   automatically approves—data-derived Principle drafts. The strongest surviving findings and
   only the established Principles used to explain them are seeded into an existing research
   session graph with permanently distinct record kinds.

Fast, Balanced, and Deep budgets cap wall time, hypotheses, analysis units, challenge rounds,
visual calls, and prior-art review. A large row count is not a valid holdout: without a
defensible group, chronological, spatial, or contiguous-signal split, validation remains
`exploratory`.

## Source integrity and derived state

Source files are opened read-only. Archives are inspected virtually or unpacked only in workspace
scratch space. Paths, raw tables, bulk files, unrestricted DICOM metadata, credentials, and
environment variables are excluded from provider requests and exports.

```text
.principia/artifacts/data-discovery/<study_id>/
outputs/<study_id>/
  report.md
  report.json
  findings.json
  tests.json
  provenance.json
  code/
  figures/
```

Every computed anchor records a portable source locator and plan/result digest. The report never
contains raw data. Generated Python records its source, AST audit, environment, logs, inputs and
outputs by digest, and isolation receipt. If verified isolation is unavailable, Principia uses the
deterministic operator engine and reports reduced flexibility.

The generated-code receipt includes wall time, output bytes, peak resident memory, and the 4 GiB
memory guard. macOS framework Python reserves a virtual address range that makes a reduced
`RLIMIT_AS` unusable, so the local Mac runtime enforces the 4 GiB boundary with parent-side
resident-memory monitoring; platforms with a usable address-space rlimit retain `RLIMIT_AS`.

## Privacy and scientific labels

Every remote run requires initially unselected, one-run consent showing the provider, resolved
reasoning and vision models, modalities, and allowed egress. Image requests contain at most two
bounded previews and record each transmitted preview hash. Missing vision support never blocks
quantitative analysis.

For the strongest locally surviving findings, Principia performs current public-literature
metadata searches after egress consent. A related result produces `prior art found`; an empty or
failed metadata search remains `not assessed` because metadata retrieval alone cannot establish
novelty. Exact model IDs, literature-search receipts, and preview hashes are frozen into coverage
receipts.

`Principle`, `Discovery Finding`, and `Data-derived Principle` are permanent, distinct record
kinds. Approval of a data-derived draft preserves its originating study, tests, and evidence badge.
Novelty statuses are limited to `not assessed`, `prior art found`, `no close prior art found`, and
`possibly novel`; the application never emits an unconditional `novel` label.

## Expression search and Rule qualification (September 5 development revision)

The typed table search implements development fitting followed by validation selection and a
sealed test evaluation. The LLM can propose admissible expression families grounded in a
specific asset and target. It does not choose coefficients or declare a fitted expression valid.
The local engine binds each target to one materializable view, its admissible inputs, and an
explicit independent-unit key. It rejects ambiguous joins, unavailable targets, leakage inputs,
and insufficient independent support. Original string unit identifiers are preserved by table
loaders. A row count or a file count alone is not evidence of independence.

For a bound target, the engine freezes disjoint unit assignments before fitting, scales inputs
using development data, and enumerates combinations of permitted transformations. These
include powers, products, ratios, and bounded nonlinear response terms. Fast, Balanced, and
Deep allow at most 1,000, 10,000, and 50,000 candidates per search program, divided across its
targets. Candidate evaluation uses cached development moments and three development group
folds. Unit weighting prevents a densely sampled unit from dominating the fit or error metric.
Only two expression searches enter CPU evaluation concurrently.

The development frontier retains candidates by complexity and coefficient-direction stability.
Validation selects at most three Pareto finalists. Their identities are sealed before locked
test targets are evaluated; they are never replaced using test feedback. A finalist must improve
both validation and test normalized RMSE by at least 2% over the development-fitted linear
baseline, satisfy the stability check, and survive a unit-level residual sign control. The control
uses 99 replicates and a threshold of 0.05 divided by the number of finalists for that target.
This controls the finalist family for one target, not multiplicity across every target in a study.
Complete-case filtering, few held-out units, and this limited multiplicity scope remain explicit
limitations. The reported held-out unit error range is not a parameter confidence interval.

Checkpoints persist the split manifest, specification and source identities, development
normalization, append-only candidate batches, validation selection, fitted parameters, and final
evidence. Completed searches return their recorded result. An interruption after the locked test
has been reserved cannot silently reopen it. Candidate batches are bounded to avoid repeatedly
serializing the entire search frontier. They are local execution artifacts and contain no raw table.

`ScientificLawFamily` remains the only source of Rules. Gate receipts now distinguish `passed`,
`failed`, `unfinished`, and `legacy_unverified`. Missing baseline execution, independent split
assignments, dimensional annotations, falsifying controls, or AST replay cannot be converted to a
pass by a legacy boolean flag. A missing control is unfinished work. An executed failing control
is negative evidence. The stored equation keeps parameter symbols separate from fitted values;
replaying the raw-input AST must reproduce its normalized representation. Unit checks for this
grammar require supplied input and target units; fitted scale parameters carry input units.

This revision does not certify the historical domain-specific executors under the stronger
execution checks. Some still use name-dependent legacy bindings or lack frozen predictions and
AST replay receipts. Their current candidates and all negative evidence are retained. Historical
promoted Rules remain visible under their original evaluation contract; browsing never rewrites
the accepted snapshot. Neither old promotion counts nor synthetic recovery tests establish fresh
21-case scientific acceptance. Consult the new campaign receipt and qualification-loss audit.

## Independent projects and result presentation

A canonical source set resolves to one flat project; reruns belong to its run history. Project
creation resolves source aliases and serializes its lookup and insert to avoid concurrent
duplicates. Retrieval for a data study is explicitly scoped to that study's source IDs, including
planning, synthesis, and repair requests. The 21 internal cases are separate studies and projects.

The project sidebar supports search, Recent/Active/All/Archived filters, complete pagination,
readable titles, and focus-managed organization dialogs. Completed studies open results first,
with run diagnostics in a collapsed section. The canonical workspace projection supplies the
graph, Map contents, and the four result categories: Principles, Observations, Rules, and Extra.
Provisional, refuted, inconclusive, and negative observations remain available. Rule cards show
metrics actually present in the stored evaluation instead of a universal hardcoded fit metric.
Established background Principles are labeled separately from data-derived discoveries.

## Runtime, storage, and remote request budgets

The workspace API returns compact records instead of embedding the full study report repeatedly.
It supports ETags, and a lightweight study status endpoint supplies frequent progress polling;
the full report refreshes less frequently and when a run terminates. Project summaries and event
reads avoid loading complete reports. Read-only endpoints do not create exports or repair state.
Interrupted work is reconciled during startup, and a pause remains `pausing` until an execution
checkpoint acknowledges it. Cancellation is cooperative: an in-flight provider request or legacy
operator can still delay shutdown; this revision does not promise a fixed shutdown deadline.

Reports are serialized once to a canonical artifact and atomically copied to exports. APFS
copy-on-write clones are used where available, with a normal copy fallback. Exports have distinct
file identities, so editing an export cannot alter canonical evidence. Actual physical space savings
depend on the filesystem and are not inferred from logical file sizes.

Remote scientific context is compacted to 80,000 UTF-8 bytes, retaining scientific role bindings
where possible and recording omissions. Raw sample fields are removed. Full local blueprints
remain intact. A process-safe SQLite token ledger reserves a conservative allowance before every
remote attempt, including retries and embeddings, and settles reported usage afterward. Unknown
usage remains charged. Set `PRINCIPIA_TOKEN_BUDGET_FILE` and
`PRINCIPIA_TOKEN_BUDGET_LIMIT` for a shared budget. A ledger's limit cannot be silently changed.
Evaluation uses one cumulative 3,000,000-token cap across canaries and the final campaign.

The acceptance runner accepts `--credential-env` only for an explicitly authorized local dotenv
file. Its loader reads allowlisted provider variables without executing the file, printing values,
or copying it. `--token-ledger` shares the cumulative budget across executions. The primary
evaluation model is exactly `deepseek-ai/DeepSeek-V4-Flash`. Offline execution audits never count
as remote scientific acceptance.

The final inspection also corrected numeric punctuation parsing in operator version 5. Column
evidence distinguishes decimal commas and comma grouping; mixed or unresolved punctuation is
kept missing with a locator receipt instead of being silently rescaled. Both CSV and workbook
materializers use this parser. The September 5 remote campaign is preserved at its original source
revision; the subsequent parser and mobile-title corrections have separate regression and data
projection checks. They do not turn that failed scientific acceptance receipt into an accepted run.


## September 5 feedback revision

The expression search version is `principia-expression-search/2`. Provider hints
extend a common numeric library, including power, reciprocal, saturation and
response-decay terms. Every structure is screened at three development-only
regularization settings; regularization settings are not separate mechanisms.
Linear expressions test a frozen no-input constant reference. Nonlinear
expressions retain the frozen linear reference. Reference choice depends on
structure and is recorded before held-out scoring. Validation, locked-test,
stability and falsifying-control thresholds are unchanged.

When roles or independent units remain unresolved, a separate descriptive search
can persist provisional expressions with in-sample errors and explicit missing
validation work. It uses at most 24 distinct raw asset digests, two projections
per asset, two responses per projection and 2,048 input-ordered complete rows per
fit. It never creates independent units, supplies a validated selector, or
promotes a Rule. Missing observations, deduplication and selection-affected
scores remain visible in receipts. Search coverage is available in Results.

Empirical equations can be dimensionally checked in native source quantities:
input scales carry their corresponding input dimensions, coefficients carry the
target dimension, and the AST checker must prove cancellation. This is not SI
calibration, a unit conversion, or a microscopic-mechanism claim. The receipt
separately records whether physical unit annotations are complete. Mechanistic
interpretation still requires the relevant physical semantics.

The spatial executor now retains exact coefficient/scaler ASTs over a versioned
input-only feature map, including its actual exponential clipping and a native
target reference. Each equation is replayed against frozen predictions to a
relative tolerance of 1e-10. Matching specimen keys stay together across regimes
in outer partitions and development folds; fits weight physical groups equally.
The recurrence executor selects the coefficient family on development accession
groups, validates on separate accession groups and retains all locked suffix
failures. It forecasts recursively from observed prefixes and rejects unsafe
floating-point integer replay ranges.

Projects expose direct permanent deletion with revision checks. Deletion rejects
active work and removes ASD study dependencies, workspace projections, jobs and
generated study directories. It preserves registered source files and shared
Principles. Archived projects are available through the project-list options.
