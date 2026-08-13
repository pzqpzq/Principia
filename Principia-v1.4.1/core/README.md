<h1 align="center">Principia</h1>

<p align="center"><strong>Principle-first scientific idea discovery</strong></p>
<p align="center"><em>Grounded in evidence. Structured for scrutiny. Exported for validation.</em></p>

<p align="center">
  <a href="https://pypi.org/project/principia-ai/"><img alt="PyPI" src="https://img.shields.io/pypi/v/principia-ai?style=flat-square&amp;logo=pypi&amp;logoColor=white&amp;label=PyPI"></a>
  <a href="https://pypi.org/project/principia-ai/"><img alt="Python versions" src="https://img.shields.io/pypi/pyversions/principia-ai?style=flat-square&amp;logo=python&amp;logoColor=white"></a>
  <a href="https://github.com/pzqpzq/Principia/blob/main/Principia-v1.4.1/core/CHANGELOG.md"><img alt="Release v1.4.1" src="https://img.shields.io/badge/release-v1.4.1-111827?style=flat-square"></a>
  <a href="https://github.com/pzqpzq/Principia/blob/main/Principia-v1.4/core/LICENSE"><img alt="MIT license" src="https://img.shields.io/badge/license-MIT-0F766E?style=flat-square"></a>
  <a href="https://icml.cc/virtual/2026/poster/61557"><img alt="ICML 2026" src="https://img.shields.io/badge/ICML-2026-7C3AED?style=flat-square"></a>
</p>

<p align="center">
  <a href="https://github.com/pzqpzq/Principia">GitHub</a> ·
  <a href="https://pypi.org/project/principia-ai/">PyPI</a> ·
  <a href="https://github.com/pzqpzq/Principia/tree/main/Principia-v1.4/core/docs">Documentation</a> ·
  <a href="https://github.com/pzqpzq/Principia/tree/main/Principia-v1.4/core/examples">Examples</a> ·
  <a href="https://github.com/pzqpzq/Principia/blob/main/Principia-v1.4/core/RELEASE_QA.md">Release QA</a>
</p>

> **Ideas from principles. Validated by evidence.**
>
> Principia is a local-first scientific discovery workspace that turns public literature and private research materials into **evidence-linked Principle maps**, **traceable Idea Cards**, and **validation-ready research packs**.

> **Release scope:** this README documents **Principia v1.4.1**, including the
> snapshot-backed Global Principles Cloud and compatibility with v1.4.0 `.pcp` packages.

## Open the v1.4 product

```bash
python -m pip install principia-ai==1.4.1
principia open --working-directory ./principia-project
```

The Python-only installed runtime serves a packaged React UI on loopback. It provides a Principles Library, card-based Principles Explorer, folder-first Local Discovery, reversible Scenario Mode, verified Principle packages, and a separately launched Admin review workspace. Private workspace content starts truthfully empty; an adjacent or explicitly configured shared `principle-packages/` library can make already-downloaded, paper-free packages available immediately.

### v1.4.1 Global Principles Cloud

Research-goal runs now search a pinned, verified Cloud snapshot in parallel with
any selected private folders. The paper-first hybrid index expands matched Works
through explicit Principle provenance; SQLite supplies complete totals, facets,
and cursor pagination. The shared Cloud cache is offline-capable and rolls back
atomically, while private content never leaves the selected working directory.

Admin mode adds Discover, Extract, Review & Compare, Publish, Dashboard, and
Cloud Browser workflows. Canonical reviewable records live under the repository-root
`global-cloud/`; checked PRs and GitHub Actions build immutable `.pcg` snapshots and
`.pcd` deltas. See [Global Cloud architecture](docs/v1.4.1/global-cloud.md),
[Admin ingestion](docs/v1.4.1/admin-ingestion.md), and the
[v1.4.1 release QA report](docs/v1.4.1/release-qa-report.md).

As soon as a working directory is selected, Principia creates the two visible product
boundaries: `workspace/` for durable application state and paper-free Principles, and
`local_data/` for raw PDFs/text/abstracts acquired on the user's behalf. Existing
private folders may be connected from anywhere without being copied. Removing
`local_data/` never removes already extracted Principles or their public paper links.
The Principles Library can switch the active working directory with a native folder
picker. Each selection is a fully isolated private project: databases, credentials,
jobs, Local sources, and private Principles are never inherited from another
working directory. Selecting an empty folder therefore opens no private collections;
downloaded packages in the shared library remain available in their separate section.

### Your first five minutes

1. In **Principles Library**, choose the working directory for this independent project.
2. Add existing papers, or use **Find public literature** to review and select a ranked metadata preview.
3. Give the search corpus a folder name. Principia creates it under `local_data/` and acquires permitted full text or abstract fallbacks there; this does not start extraction.
4. Select the exact documents, optionally add a research focus, and run evidence-grounded extraction.
5. Review ready and held-back findings, then browse them as stable cards in **Principles Explorer**.

A downloadable Principle catalog is optional. “Global” describes the distribution channel, not the runtime location: verified packages are downloaded into a shared local `principle-packages/` library and remain available offline from every working directory. Packages declare whether they contain human-reviewed Capsules or unassessed public-literature Candidates; neither class contains PDFs or source text. A paper-free portable showcase can also populate a clean checkout; see [storage and portability](docs/v1.4/storage-and-portability.md).

Key guides: [getting started](docs/v1.4/getting-started.md), [Local Literature Discovery](docs/v1.4/local-literature-discovery.md), [storage and portability](docs/v1.4/storage-and-portability.md), [privacy and model egress](docs/v1.4/privacy-and-security.md), [Global packages](docs/v1.4/global-packages.md), [Scenario Mode](docs/v1.4/scenarios.md), [Admin dry runs](docs/v1.4/admin.md), [migration and recovery](docs/v1.4/migration-and-recovery.md), and [release verification](docs/v1.4/release-verification.md).

[Why Principia](#the-thesis) · [Workflow](#from-a-research-goal-to-a-validation-pack) · [Installation](#installation) · [Examples](#live-v140-examples) · [Trustworthiness](#trustworthiness-is-an-architecture-not-a-disclaimer) · [Research foundations](#core-research-foundations) · [Architecture](#technical-architecture) · [Contact](#contact)

---

## The thesis

Most LLM research assistants optimize for a convincing answer. Principia optimizes for an **inspectable scientific object**.

A serious research idea should make five things visible:

1. **Origin** — which works and evidence records informed it;
2. **Principles** — which mechanisms, constraints, and transferable abstractions it builds on;
3. **Construction** — how those ingredients became the proposed method;
4. **Risk** — which assumptions, failure modes, and prior-art overlaps may invalidate it;
5. **Testability** — what experiment, baseline, metric, and falsification path should come next.

Principia therefore treats an idea as a typed research contract rather than a paragraph:

```text
Idea Card
  = selected evidence
  + reusable principles
  + explicit mechanism
  + novelty contrast
  + assumptions and risks
  + validation contract
```

The goal is not to generate more ideas. The goal is to generate ideas whose **provenance, scientific logic, uncertainty, and next experiment are visible**.

### Why this changes the workflow

| Conventional workflow | Principia v1.4.0 |
| --- | --- |
| Ask an LLM to brainstorm from a prompt | Build an exact evidence packet before generation |
| Retrieve whole documents or opaque chunks | Extract typed ideas, principles, takeaways, comparators, evaluation contexts, and result facts |
| Accept a fluent one-shot proposal | Run a strict candidate–critique–evolution–selection process |
| Trust citations emitted by the model | Resolve every citation to a canonical `(work_id, kind, record_id)` |
| Hide provider failures behind generic output | Surface failures, allow one grounded repair, then fail closed |
| Leave the result in chat history | Export a portable, versioned research pack |
| Treat validation as future work | Make baselines, metrics, risks, and falsification part of the output |

---

## From a research goal to a validation pack

```text
Research goal
    │
    ├── Public literature
    │     arXiv · OpenAlex · Crossref · Semantic Scholar · Europe PMC
    │
    └── Private corpus (optional)
          PDF · Office · Markdown · LaTeX · code · structured text
                │
                ▼
      Cross-domain retrieval and identity reconciliation
                │
                ▼
      Structured scientific feature extraction
      ideas · principles · takeaways · baselines · benchmarks · result facts
                │
                ▼
      Canonical evidence packet
                │
                ▼
      SciDialect-Evo: 3 candidates → 2 evolved candidates → 1 final Idea Card
                │
                ▼
      Prior-idea comparison
                │
                ▼
      Deterministic validation plan + portable seven-file research pack
```

Principia is deliberately staged. Retrieval, extraction, evidence selection, generation, comparison, and export remain separately inspectable and resumable.

---

## What ships in v1.4.0

| Layer | Capability | Why it matters |
| --- | --- | --- |
| **Product UI** | Packaged Library, Map, Local Discovery, Scenario, and isolated Admin routes served by the Python wheel | Installed users need no Node runtime and never fall back to mock content |
| **Local Literature Discovery** | Folder-first indexing and exact document selection, with optional multi-source metadata search, open-access acquisition, evidence-grounded extraction, held-back drafts, and cross-paper deduplication | Search helps build a real private folder but never hides ownership or starts model extraction automatically |
| **Downloadable Principle packages** | Immutable, verified `.pcp` packages with install/update/verify/pin/rollback, registry rebuild, explicit content/review class, and offline use | Reviewed Capsules and clearly unassessed Candidate collections remain reproducible without conflating distribution with scientific review |
| **Principles Explorer** | Deterministic Global/Local/Combined search, faceted card browsing, evidence drawers, relation measures, pagination, and editable Local display metadata | Hundreds of Principles remain readable and stable without a jumping or overcrowded graph canvas |
| **Scenario Mode** | Append-only copy-on-write overlays, replay, impact/diff, branch, compare, and discard | Counterfactual exploration cannot silently mutate canonical scientific truth |
| **Governed publication** | Candidate/Capsule separation, human review, immutable changesets, validation, and dry-run export | Publication readiness is a review decision rather than a model assertion |
| **Cross-domain retrieval** | Query planning, arXiv/OpenAlex/Crossref/Semantic Scholar access, automatic Europe PMC routing for biomedical topics, bounded retries, identity reconciliation, BM25 or embedding reranking | A research idea should not be limited to one source, one naming convention, or one surface vocabulary |
| **Private research context** | Recursive local ingestion with portable `local://` identities; core support for PDF, HTML/XML, Markdown, RST, LaTeX, text/code, JSON, YAML, CSV/TSV; optional DOCX/PPTX/XLSX support | Public literature can be combined with private notes, unpublished drafts, internal reports, and project-specific evidence |
| **Structured extraction** | Typed prior ideas, principles, takeaways, comparators, evaluation contexts, and grounded result facts with provenance and content fingerprints | Principia reasons over scientific objects, not only document chunks |
| **Canonical evidence** | Exact record-level citations, source-text hydration, mixed public/private evidence checks, configurable global evidence budgets | The generator cannot silently invent the evidence it claims to use |
| **Strict SciDialect-Evo** | Three distinct proposals, explicit scoring, evolution of the strongest two, final selection, one evidence-grounded repair, fail-closed persistence | Idea generation becomes a controlled search process rather than a single completion |
| **Prior-art comparison** | Content-level shortlisting plus model-assisted comparison of mechanistic similarity, essential difference, potential advantage, and weakness | Novelty is treated as a contrastive claim, not a self-awarded label |
| **Validation hand-off** | Human-readable and JSON validation plans generated from the final Idea Card and canonical evidence without another LLM call | The research hypothesis and the experiment contract stay synchronized |
| **Controllable jobs** | Weighted progress, checkpoints, pause/resume/stop controls, notebook widgets, terminal display, event history | Long research runs remain observable and controllable while the worker process is active |
| **Portable state** | Shared project workspace, per-idea output folders, SQLite migrations, path-safe exports | Research memory can compound without duplicating the evidence pool |

---

## Installation

Principia supports **Python 3.10–3.13**. The distribution name is `principia-ai`; the import package is `principia`.

```bash
python -m pip install principia-ai==1.4.0
```

Add Office-document and notebook support when needed:

```bash
python -m pip install "principia-ai[local,notebook]==1.4.0"
```

The examples below use SiliconFlow through an OpenAI-compatible API. Principia can also be configured with `pc.LLMConfig(...)` for other OpenAI-compatible endpoints.

```bash
export SILICONFLOW_API_KEY="your-key"

# Required to use OpenAlex under its current authentication policy.
export OPENALEX_API_KEY="your-openalex-key"
```

Never commit credentials to source files, notebooks, `.env` files, or exported artifacts.

---

## Quick start

### One-call research workflow

```python
import os
import principia as pc

GOAL = (
    "Develop an evidence-grounded method for improving long-horizon "
    "reasoning efficiency in LLM agents under a fixed token budget."
)

ws = pc.Workspace.project(
    "principia_project",
    llm_config=pc.siliconflow_config(
        os.environ["SILICONFLOW_API_KEY"],
        max_calls=220,
    ),
)

job = ws.start(
    GOAL,
    pipeline_config=pc.PipelineConfig.research(),
)

result = job.result()
result.show()
```

`PipelineConfig.research()` is the opinionated v1.4.0 research preset:

- exactly **50 public works** requested;
- embedding reranking requested and reported explicitly;
- strict failure if the public target cannot be completed;
- an exact **15-record evidence packet**: 5 ideas, 5 principles, and 5 takeaways;
- no more than 2 selected records from one work;
- strict `scidialect-evo` generation.

The preset is intentionally demanding. Every field can be overridden through `PipelineConfig`, `RetrievalConfig`, or the staged API.

### Add a private corpus

```python
import os
import principia as pc

ws = pc.Workspace.project(
    "principia_project",
    llm_config=pc.siliconflow_config(
        os.environ["SILICONFLOW_API_KEY"],
        max_calls=220,
    ),
    allow_remote_private_content=True,
)

job = ws.start(
    "Your research objective",
    documents="private_sources",
    pipeline_config=pc.PipelineConfig.research(),
)

result = job.result()
result.show()
```

Private documents are **supplemental**: they never silently replace the requested public-literature target. Original files are not copied into the project. Absolute paths remain in hidden local state and are excluded from prompts and shareable exports.

Sending private text to a remote model requires explicit `allow_remote_private_content=True`. The provider receives document content and portable identifiers, not local absolute paths.

See [Private corpus ingestion](https://github.com/pzqpzq/Principia/blob/main/Principia-v1.4/core/docs/local-corpus.md) for parser limits, chunking, diagnostics, deduplication, custom parser registration, and cache cleanup.

---

## Inspect every stage

The high-level workflow is concise, but the research process remains fully programmable:

```python
works = ws.research.search(
    GOAL,
    target_count=50,
    rerank_mode="embedding_rerank",
    require_target=True,
    show_progress=True,
)

features = ws.research.extract(
    works,
    model="auto",
    show_progress=True,
)

evidence = pc.select_evidence(
    features,
    global_kind_limits={
        "ideas": 5,
        "principles": 5,
        "takeaways": 5,
    },
    max_per_work=2,
    require_exact=True,
    user_note=GOAL,
)

idea = ws.ideas.generate(
    evidence,
    user_note=GOAL,
    mode="scidialect-evo",
    model="auto",
    show_progress=True,
)

comparison = ws.ideas.compare(
    idea,
    features,
    model="auto",
    show_progress=True,
)
```

This staged interface is useful when you need to inspect retrieval diagnostics, curate an evidence packet, replace a model, modify a generation budget, or stop before an expensive stage.

---

## Control long-running jobs

```python
status = job.status()
print(status.status, status.stage, status.progress)

job.pause()   # pause at the next safe provider boundary
job.resume()
job.stop()    # schedule no further work

for event in job.events():
    print(event)
```

The same controls are available from the workspace or CLI while the original
worker process remains active. Keep the persisted run ID so another notebook
cell or terminal can address that worker:

```python
run_id = job.run_id
ws.status(run_id)
ws.pause(run_id)
ws.resume(run_id)
ws.stop(run_id)
```

Pause and stop are cooperative. An in-flight bounded provider request may finish and checkpoint, but no subsequent paid call begins after the relevant control boundary.

Run status, events, and completed stage checkpoints persist in SQLite. A Python
`PipelineJob` itself is thread-backed, however: reopening a workspace after its
worker process has exited does not recreate that thread or restart the remaining
pipeline automatically.

---

## What Principia returns

`Workspace.project(...)` separates reusable research state from idea-specific outputs:

```text
principia_project/
  workspace/
    works.json
    features.json
    manifest.json
    .principia/
  outputs/
    <idea_id>/
      idea.md
      idea.json
      evidence.json
      comparison.json
      result.json
      validation_plan.md
      validation_plan.json
```

### The Idea Card

A generated `Idea` can include:

- title and one-sentence thesis;
- novelty claim and closest conceptual contrasts;
- mechanism design and methodological details;
- formulas and symbols when supported by evidence;
- method variants;
- validation protocol;
- baselines, metrics, risks, and assumptions;
- derived principles;
- exact source-evidence references;
- candidate, critique, evolution, selection, and repair metadata.

### The validation pack

The validation plan is derived deterministically from the final Idea Card and selected evidence. It does not trigger another model call. Its Markdown and JSON forms preserve:

- the research goal and thesis;
- the proposed protocol;
- comparators and baselines;
- success and failure metrics;
- risks and assumptions;
- canonical evidence references;
- model, mode, schema version, and timestamps.

The result is designed to move cleanly into experiment repositories, coding agents, review workflows, or reproducibility bundles.

---

## Live v1.4.0 examples

The release contains three compact, output-bearing acceptance showcases across AI, computer vision, and physics.

Each originating run used **50 public works + 5 local documents**, produced **55 feature bundles**, selected an exact **15-record evidence packet**, ran live non-degraded `scidialect-evo`, compared the final idea with extracted prior ideas, and exported seven portable artifacts.

> These examples demonstrate the framework's retrieval, grounding, generation, comparison, mathematics, privacy, and export contracts. Their Idea Cards are **generated research hypotheses**, not experimentally confirmed discoveries.

The excerpts below are rendered from the accepted live Idea Cards. Only
Markdown wrapping and deterministic LaTeX notation normalization are applied;
no scientific claim is rewritten.

The following acceptance metrics are generated directly from the verified
showcase manifests:

<!-- PRINCIPIA_SHOWCASE_TABLE_START -->
| Task | Online | Local | Features | Evidence | Mode | Validation |
| --- | --- | --- | --- | --- | --- | --- |
| [Communication-efficient LLM multi-agent reasoning](https://github.com/pzqpzq/Principia/blob/main/Principia-v1.4/core/examples/test1/tutorial.ipynb) | 50 | 5 | 55 | 15 | scidialect-evo | passed |
| [Uncertainty-aware sparse-view dynamic 3D reconstruction](https://github.com/pzqpzq/Principia/blob/main/Principia-v1.4/core/examples/test2/tutorial.ipynb) | 50 | 5 | 55 | 15 | scidialect-evo | passed |
| [Broadband squeezed-state axion sensing](https://github.com/pzqpzq/Principia/blob/main/Principia-v1.4/core/examples/test3/tutorial.ipynb) | 50 | 5 | 55 | 15 | scidialect-evo | passed |
<!-- PRINCIPIA_SHOWCASE_TABLE_END -->

| Research task | Generated Idea Card | Review |
| --- | --- | --- |
| Communication-efficient LLM multi-agent reasoning | **Entropy-Constrained Discrete Codebook with Counterfactual Decoding and Diversity-Aware Calibration** | [Notebook](https://github.com/pzqpzq/Principia/blob/main/Principia-v1.4/core/examples/test1/tutorial.ipynb) · [Showcase](https://github.com/pzqpzq/Principia/blob/main/Principia-v1.4/core/examples/test1/showcase.md) |
| Uncertainty-aware sparse-view dynamic 3D reconstruction | **AnchorSplat-Dynamic: Sparse Anchor-Based Uncertainty for Uncalibrated Motion** | [Notebook](https://github.com/pzqpzq/Principia/blob/main/Principia-v1.4/core/examples/test2/tutorial.ipynb) · [Showcase](https://github.com/pzqpzq/Principia/blob/main/Principia-v1.4/core/examples/test2/showcase.md) |
| Broadband squeezed-state axion sensing | **Dynamic Heuristic Optimization of Squeezed-State Haloscopes with Continuum Noise Modeling** | [Notebook](https://github.com/pzqpzq/Principia/blob/main/Principia-v1.4/core/examples/test3/tutorial.ipynb) · [Showcase](https://github.com/pzqpzq/Principia/blob/main/Principia-v1.4/core/examples/test3/showcase.md) |

<details>
<summary><strong>Example 1 — Communication-efficient LLM multi-agent reasoning</strong></summary>

**Generated thesis**

> Imposing a per-task entropy floor on learned discrete messages prevents representational collapse while achieving token efficiency, provided that a counterfactual decoding protocol verifies causal interpretability and the entropy target is calibrated using real-time embedding diversity metrics.

**Mechanism**

Agents map internal states to indices in a shared codebook. The loss function includes a term penalizing codebook usage below a calculated entropy threshold ($H_{\mathrm{target}}$). $H_{\mathrm{target}}$ is adjusted if pre-training diagnostics show agent embedding cosine similarity exceeds 0.88, signaling potential collapse. A separate decoder module must reconstruct the original observation from the code index; if reconstruction fails under minimal input perturbations (counterfactuals), the dialect is rejected.

$$L_{\mathrm{total}} = L_{\mathrm{task}} + \lambda L_{\mathrm{tokens}} - \beta \max(0, H_{\mathrm{target}} - H(C))$$

**Validation contract**

Compare against standard CoT, uncompressed multi-agent baselines, and static codebook variants. Measure token reduction, accuracy, codebook entropy, success rate on counterfactual decoding tests, and embedding overlap. Specifically test scenarios where $S_{\mathrm{cos}}$ approaches 0.88 to verify the dynamic calibration of $H_{\mathrm{target}}$ prevents performance degradation.

The exported card used canonical evidence from five works and was compared against three extracted prior ideas.

</details>

<details>
<summary><strong>Example 2 — Sparse-view dynamic 3D reconstruction</strong></summary>

**Generated thesis**

> By decoupling Gaussian primitives from the 2D pixel grid and anchoring them to a sparse set of 3D geometric proxies, we jointly optimize pose, motion, and heteroscedastic uncertainty for uncalibrated dynamic scenes, reducing redundancy in static regions while focusing capacity on moving objects.

**Mechanism**

A feed-forward encoder predicts sparse 3D anchors and associated Gaussian parameters (appearance, opacity, motion vectors, covariance). A differentiable renderer projects these into input views. A geometric prior module enforces epipolar and motion consistency constraints. An uncertainty head predicts per-Gaussian variance, gating gradient flow during test-time refinement to prevent overfitting to noise in uncalibrated views.

$$\mathcal{L}_{\mathrm{total}} = \sum_{i \in \mathcal{A}} (1 - \sigma_{u,i}) \cdot \mathcal{L}_{\mathrm{render}}(i) + \lambda \mathcal{L}_{\mathrm{geo}}(i)$$

**Validation contract**

Train on synthetic dynamic scenes (6–12 views). Evaluate on real-world uncalibrated sequences. Metrics: PSNR/SSIM, ECE, Risk-Coverage curves. Baselines: Dense pixel-aligned GS, Pose-dependent LRMs. Pass/Fail: $\mathrm{ECE} \le 0.10$; masking top 20% uncertain Gaussians must reduce median error.

The exported card used five canonical records across four works and was compared against five extracted prior ideas.

</details>

<details>
<summary><strong>Example 3 — Broadband squeezed-state axion sensing</strong></summary>

**Generated thesis**

> Integrating real-time heuristic search algorithms with Josephson Parametric Amplifiers allows for dynamic stabilization of squeezed states against environmental drift, while modeling noise propagation as a continuum through lossy transmission lines maximizes broadband scan speed and maintains false-positive controls via configuration-independent rejection.

**Mechanism**

A feedback loop where a heuristic search algorithm continuously adjusts JPA pump frequency and power based on real-time noise spectral density measurements derived from a continuum noise model. The system employs a dual-readout chain to enforce configuration-independent signal rejection, ensuring candidates are physical resonator responses rather than readout artifacts.

$$\text{SNR}^{2} = T_{\mathrm{int}} \int \frac{S_{\mathrm{ax}}^{2}(f)}{S_{\mathrm{noise}}(f)} df$$

**Validation contract**

Validate squeezing advantage using reported metrics; verify candidate signals appear in both readout chains with predicted coherence width; test rejection of signals correlating with configuration changes; compare continuum noise model predictions against measured noise spectra.

The exported card used five canonical records across five works and was compared against three extracted prior ideas.

</details>

---

## Trustworthiness is an architecture, not a disclaimer

Principia does not treat provenance and privacy as presentation features. They are enforced at the data-model and persistence layers.

| Invariant | v1.4.0 behavior |
| --- | --- |
| **Record-level evidence** | Every citation must resolve to one canonical `(work_id, kind, record_id)` tuple. Quoted content is hydrated from the selected record rather than trusted from model output. |
| **Evidence before generation** | The generator receives an explicit `EvidencePacket`; configuration, traces, warnings, and usage metadata cannot become scientific evidence. |
| **Fail-closed generation** | Live output receives at most one evidence-grounded repair. If canonical references, grounding, required fields, or mathematical constraints remain invalid, the idea is not persisted. |
| **No invisible live fallback** | A failed live model call is surfaced. Deterministic mock output exists only as an explicitly labelled `mock_fixture` for tests and cannot satisfy release showcase gates. |
| **Private by explicit consent** | Local originals are not copied; absolute paths remain hidden; exported identifiers are portable; remote processing of private text requires explicit authorization. |
| **Prompt-injection boundary** | Retrieved and local documents are delimited as untrusted research data; embedded instructions are not treated as executable directives. |
| **Observable retrieval** | Diagnostics expose query plans, source health, retry outcomes, result counts, degraded-source warnings, ranking traces, and the rerank mode actually applied. |
| **Strict mathematics** | Retained formulas are normalized to canonical LaTeX, structurally validated, and included in strict KaTeX release checks. |
| **Deterministic hand-off** | `ValidationPlan` is generated from the accepted Idea Card and evidence registry without another probabilistic model call. |

Principia's grounding checks are **recoverability** checks, not a truth certificate. They ask whether canonical evidence references and the task-critical anchors needed to audit a proposal remain recoverable. Scientific validity still requires external evaluation.

---

## Release confidence

The v1.4.0 release tree records a fail-closed acceptance process. Highlights include:

- the complete regression suite is rerun on Python 3.10, 3.12, and 3.13 against the final source and showcase artifacts before publication, with exact results recorded in the release QA report;
- CI coverage configured for Python 3.10–3.13;
- Ruff and mypy checks passed;
- wheel and source distribution build and `twine check` passed;
- clean-environment core and `[local]` installation smokes passed;
- strict source, export, notebook, LaTeX, and KaTeX audits passed;
- archive scans checked credentials, authorization headers, private paths, private sentinels, and stale artifacts;
- all three live research showcases passed their retrieval, evidence, generation, comparison, privacy, mathematics, and export gates.

See the complete [Principia 1.3.3 Release QA report](https://github.com/pzqpzq/Principia/blob/main/Principia-v1.3/RELEASE_QA.md) for exact commands, thresholds, warnings, and artifact checksums.

---

## Core research foundations

Principia is not merely a retrieval wrapper. It is a downstream research system built around a deeper question:

> **What representations should AI agents create, exchange, preserve, and evolve when the objective is scientific discovery rather than fluent conversation?**

Two related research lines shape the framework.

### 1. Machine Dialectology

[Machine Dialectology](https://github.com/pzqpzq/LSF_MDia) studies how heterogeneous LLM agents can create, inherit, exchange, and route compact machine-oriented languages.

Its concrete ICML 2026 precursor is **Communicative Language Symbolism Routing (CLSR)**:

- [ICML 2026 official page](https://icml.cc/virtual/2026/poster/61557)
- [OpenReview](https://openreview.net/forum?id=ovpL0ujD6j)
- [arXiv:2606.29354](https://arxiv.org/abs/2606.29354)
- [Code and Machine Dialectology repository](https://github.com/pzqpzq/LSF_MDia)

CLSR treats a **Language Symbolism Framework (LSF)** as a reusable protocol rather than a shorter prose prompt. An LSF contains compact symbols, usage rules, validity constraints, and a message-passing contract. The system:

1. samples seed exemplars;
2. lets LLM agents invent candidate LSFs;
3. generates LSF-conditioned responses;
4. selects correct and token-efficient traces;
5. evolves the protocol pool through propose → evaluate → select → mutate cycles;
6. routes, ensembles, or composes LSFs at inference time.

The ICML paper reports a **3–6× reduction in latency-oriented generated-token completion** relative to standard Chain-of-Thought while maintaining accuracy across the studied benchmarks.

The broader Machine Dialectology agenda generalizes this idea from one model family to heterogeneous machine societies. Its central insight is that machine-to-machine reasoning does not have to inherit the full rhetorical overhead of human prose. Agents can develop task-conditioned protocols whose intermediate states are denser, reusable, and routable.

**Principia's connection:** scientific ideation also has an intermediate-language problem. Mechanisms, trade-offs, assumptions, analogies, and falsification rules must be represented before they can be composed. Machine Dialectology provides the conceptual substrate for compact symbolic handles and reusable operators that help an agent move from literature evidence to structured, testable hypotheses.

### 2. SciDialect

**SciDialect: Symbolic Compression as an Intrinsic Reward for Scientific Discovery Agents** *(Zhengqi Pei, Qingming Huang, and Shuhui Wang; technical manuscript, 2026)* studies a complementary problem: compact symbolic representations are useful only when their scientific meaning survives compression.

Scientific agents often receive sparse external rewards. A hypothesis may not be rewarded until an experiment finishes; a coding approach may not be rewarded until hidden tests run; a research trajectory may not be rewarded until review. SciDialect introduces a denser representation-level signal: **grounded symbolic compression**.

A symbolic state earns credit only when it becomes shorter while preserving the task-critical anchors needed for independent reconstruction and audit.

An evidence anchor has the conceptual form:

```text
anchor = (type, normalized value, source or location, role in the task)
```

Anchors may include variables, units, regimes, time windows, effect directions, equations, function signatures, dataset paths, output contracts, visible tests, prior-work links, or experimental controls.

A scientific dialect primitive is not an arbitrary abbreviation. It carries:

```text
symbol
+ natural-language definition
+ argument schema
+ evidence slots
+ validity conditions
+ anti-definition of nearby invalid meanings
+ decoder template
```

Independent decoders must reconstruct the proposed meaning without access to the original verbose proposition. A skeptical reviewer checks missing anchors, added assumptions, semantic drift, invalid arguments, unsupported evidence, and dictionary bloat.

The intrinsic objective can be summarized as:

$$R_{\mathrm{SD}}=w_{\mathrm{c}}G_{\mathrm{comp}}+w_{\mathrm{r}}S_{\mathrm{rec}}+w_{\mathrm{g}}S_{\mathrm{ground}}+w_{\mathrm{a}}S_{\mathrm{agree}}+w_{\mathrm{u}}U_{\mathrm{task}}-w_{\mathrm{b}}B_{\mathrm{dict}}.$$

The terms reward compression, reconstruction fidelity, evidence grounding, decoder agreement, and optional development utility while charging dictionary growth. Reconstruction, grounding, agreement, dictionary-cost, leakage, and task-validity checks act as hard feasibility gates: a highly compressed but ungrounded state is never allowed to guide the solver.

This creates three important principles:

- **No-free compression:** a short private identifier has no scientific value when its definition cost and lost meaning are ignored;
- **Amortized abstraction:** a primitive is valuable only when reuse savings exceed definition, redundancy, and checking costs;
- **Anchor-gated auditability:** accepted states retain an explicit lower bound on recoverable task-critical anchors under the chosen grounding rule.

SciDialect does **not** certify that a claim is true. It certifies a stricter and more useful intermediate property: the compressed representation remains public enough to reconstruct, grounded enough to audit, and reusable enough to justify its symbolic cost.

#### How v1.4.0 operationalizes this line

Principia v1.4.0 implements a strict idea-evolution protocol inspired by this research:

```text
3 mechanistically distinct candidate ideas
        ↓
score novelty · grounding · feasibility · discriminability
        ↓
evolve the strongest 2 with explicit critiques and recorded changes
        ↓
select 1 final evolved candidate with a rationale
        ↓
validate canonical evidence and scientific fields
        ↓
one grounded repair or fail closed
```

The broader SciDialect manuscript studies reward-conditioned symbolic scientific memory across several task adapters. Principia v1.4.0 implements the evidence-grounded idea-generation protocol relevant to this framework; it does not claim to reproduce every adapter or experiment in the broader manuscript.

### How the two ideas fit together

| Research question | Research line | Principia consequence |
| --- | --- | --- |
| What machine-oriented representations can agents invent, evolve, and route? | **Machine Dialectology / CLSR** | Use reusable symbolic protocols and task-conditioned operators rather than relying only on verbose prose |
| When should a compressed scientific representation be trusted? | **SciDialect** | Motivate Principia's canonical-evidence and audit checks; decoder-agreement and dictionary-cost objectives remain outside v1.4.0 |
| How can those representations become useful research outputs? | **Principia** | Convert an evidence packet into a traceable Idea Card, contrast it with prior ideas, and export a falsifiable validation contract |

Together, they move scientific-agent design from **“generate a plausible proposal”** toward **“evolve an auditable representation that can survive comparison and experimentation.”**

---

## Technical architecture

Principia v1.4.0 uses typed objects and explicit boundaries rather than a monolithic agent loop.

| Component | Responsibility |
| --- | --- |
| `principia_retrieval` | Source-aware query planning, provider clients, identity reconciliation, ranking, embeddings, retries, and diagnostics |
| `principia.research` | Public search, private ingestion, source acquisition, structured extraction, and checkpoint reuse |
| `principia.features` | Scientific feature schemas, evidence selection, canonical registries, validation, and source-text hydration |
| `principia.ideas` | Standard, calculus-compatible, and strict SciDialect-Evo generation; prior-idea comparison; fail-closed grounding checks |
| `principia.validation` | Deterministic validation-plan construction and Markdown/JSON rendering |
| `principia.pipeline` | Persisted end-to-end orchestration, weighted progress, pause/resume/stop, and result assembly |
| `principia.storage` | SQLite state, migrations, manifests, content fingerprints, portable artifacts, and private-cache controls |
| `principia.math` | LaTeX normalization, structural validation, and release-quality mathematical checks |
| `principia.cli` | Search, extraction, generation, run inspection, and run control from the terminal |

Public models, retrieval dataclasses, and job handles are importable directly from `principia`, including `WorkItem`, `WorkFeatures`, `EvidencePacket`, `Idea`, `IdeaComparison`, `PipelineResult`, `ValidationPlan`, `RetrievalConfig`, `SciDialectConfig`, `SearchDiagnostics`, and `PipelineJob`.

---

## CLI

The package installs a `principia` command.

```bash
# Initialize and inspect a workspace
principia --workspace ./principia_project/workspace init
principia --workspace ./principia_project/workspace status

# Search public research metadata
principia --workspace ./principia_project/workspace \
  search "evidence-efficient scientific agents" \
  --target-count 20 \
  --rerank-mode embedding_rerank \
  --require-target

# Search, extract, and generate one strict SciDialect-Evo idea
principia --workspace ./principia_project/workspace \
  generate "evidence-efficient scientific agents" \
  --target-count 20 \
  --rerank-mode embedding_rerank \
  --require-target

# Inspect and control persisted runs
principia --workspace ./principia_project/workspace runs
principia --workspace ./principia_project/workspace status RUN_ID
principia --workspace ./principia_project/workspace pause RUN_ID
principia --workspace ./principia_project/workspace resume RUN_ID
principia --workspace ./principia_project/workspace stop RUN_ID
```

Use `--mock-llm` only for deterministic smoke tests. Mock output is explicitly labelled and is not scientific evidence.

---

## Documentation

- [API reference](https://github.com/pzqpzq/Principia/blob/main/Principia-v1.4/core/docs/api.md)
- [Projects, workspaces, and outputs](https://github.com/pzqpzq/Principia/blob/main/Principia-v1.4/core/docs/workspaces.md)
- [Private corpus ingestion](https://github.com/pzqpzq/Principia/blob/main/Principia-v1.4/core/docs/local-corpus.md)
- [Background jobs and run control](https://github.com/pzqpzq/Principia/blob/main/Principia-v1.4/core/docs/jobs.md)
- [Trustworthy generation and mathematics](https://github.com/pzqpzq/Principia/blob/main/Principia-v1.4/core/docs/trustworthiness.md)
- [Retrieval, diagnostics, and provider terms](https://github.com/pzqpzq/Principia/blob/main/Principia-v1.4/core/docs/retrieval.md)
- [Publishing and release checks](https://github.com/pzqpzq/Principia/blob/main/Principia-v1.4/core/docs/publishing.md)
- [Examples](https://github.com/pzqpzq/Principia/tree/main/Principia-v1.4/core/examples)
- [Changelog](https://github.com/pzqpzq/Principia/blob/main/Principia-v1.4/core/CHANGELOG.md)
- [Release QA](https://github.com/pzqpzq/Principia/blob/main/Principia-v1.4/core/RELEASE_QA.md)
- [Upstream integration and license scope](https://github.com/pzqpzq/Principia/blob/main/Principia-v1.4/core/UPSTREAM.md)

---

## Development

```bash
git clone https://github.com/pzqpzq/Principia.git
cd Principia/Principia-v1.3

python -m pip install -e ".[dev,local,notebook]"

python -m ruff check src tests scripts
python -m mypy src
python -m pytest -q
python -m build --no-isolation
python -m twine check dist/*
```

Contributions are especially valuable in retrieval adapters, scientific schemas, evidence validation, domain-specific evaluation, private-document parsers, reproducibility tooling, and expert review of generated Idea Cards.

---

## Responsible interpretation

Principia is a research framework, not an oracle.

- Generated Idea Cards are hypotheses, not established results.
- Canonical evidence improves provenance; it does not guarantee that a source is correct.
- Prior-art comparison reduces obvious duplication risk; it does not replace a complete scholarly review or legal patent search.
- Validation plans structure the next experiment; they do not predict its outcome.
- Private documents should be sent to a remote model only under an appropriate data-governance policy.
- Scientific claims should be accepted only after independent empirical, theoretical, or expert validation.

The intended standard is simple: **every persuasive claim should be paired with an inspectable source, an explicit assumption, or a test that could prove it wrong.**

---

## Citation

To cite Principia as software:

```bibtex
@software{principia2026,
  title   = {Principia: Principle-First Scientific Idea Discovery},
  author  = {{Principia Contributors}},
  year    = {2026},
  version = {1.3.3},
  url     = {https://github.com/pzqpzq/Principia}
}
```

To cite the CLSR / Machine Dialectology research foundation:

```bibtex
@inproceedings{pei2026lsf,
  title     = {When LLMs Develop Languages: Symbolic Communication for Efficient Multi-Agent Reasoning},
  author    = {Pei, Zhengqi and Huang, Qingming and Wang, Shuhui},
  booktitle = {Proceedings of the 43rd International Conference on Machine Learning},
  year      = {2026}
}
```

---

## Contact

**Academic collaboration**  
In collaboration with the [Institute of Computing Technology, Chinese Academy of Sciences](https://english.ict.cas.cn/).  
Contact: `peizhengqi22@mails.ucas.ac.cn`

**Business collaboration**  
In collaboration with Beijing Chipflow Technology Co., Ltd.  
Contact: `peizhengqi@chipflow.net`

---

## License

The `principia-ai` v1.4.0 framework is released under the [MIT License](https://github.com/pzqpzq/Principia/blob/main/Principia-v1.4/core/LICENSE).

The upstream multi-project repository contains separately scoped material. See [UPSTREAM.md](https://github.com/pzqpzq/Principia/blob/main/Principia-v1.4/core/UPSTREAM.md) for the exact integration and license boundary.

---

<p align="center"><strong>Build ideas whose evidence, mechanism, and falsification path can be inspected.</strong></p>

<p align="center">If Principia is useful to your research, consider <a href="https://github.com/pzqpzq/Principia">starring the repository</a> and following the next releases in Principia, Machine Dialectology, and SciDialect.</p>
