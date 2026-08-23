<h1 align="center">Principia</h1>

<p align="center"><strong>The living Principles Cloud for Autonomous Scientific Discovery</strong></p>
<p align="center"><em>From scientific works to reusable structure. From structure to testable derivations.</em></p>

<p align="center">
  <a href="https://github.com/pzqpzq/Principia/actions/workflows/principia-v141-ci.yml"><img alt="v1.4.1 CI" src="https://github.com/pzqpzq/Principia/actions/workflows/principia-v141-ci.yml/badge.svg"></a>
  <a href="https://github.com/pzqpzq/Principia/tree/main/Principia-v1.4.1/core"><img alt="Principia v1.4.1" src="https://img.shields.io/badge/Principia-v1.4.1-111827?style=flat-square&amp;logo=github"></a>
  <a href="https://pypi.org/project/principia-ai/"><img alt="PyPI stable" src="https://img.shields.io/pypi/v/principia-ai?style=flat-square&amp;logo=pypi&amp;logoColor=white&amp;label=PyPI%20stable"></a>
  <a href="https://github.com/pzqpzq/Principia/blob/main/Principia-v1.4.1/core/LICENSE"><img alt="MIT license" src="https://img.shields.io/badge/v1.4.1%20core-MIT-0F766E?style=flat-square"></a>
  <a href="https://arxiv.org/abs/2606.29354"><img alt="ICML 2026" src="https://img.shields.io/badge/ICML-2026-6D4AFF?style=flat-square"></a>
</p>

<p align="center">
  <a href="#principia-v141">v1.4.1</a> ·
  <a href="#scientific-object-model">Object model</a> ·
  <a href="#from-retrieval-to-derivation">Workflow</a> ·
  <a href="#global-principles-cloud">Cloud</a> ·
  <a href="#install-and-open-v141">Quick start</a> ·
  <a href="#principia-v133--evidence-grounded-idea-discovery">v1.3.3</a> ·
  <a href="#research-foundations">Research</a>
</p>

---

# Principia v1.4.1

Principia v1.4.1 is a local-first research workbench that turns scientific literature into an **inspectable reasoning substrate**. Instead of treating papers as the terminal unit of knowledge, it represents reusable mechanisms, constraints, regularities, trade-offs, boundary conditions, and falsifiers as revisioned **Principles**.

> **Core thesis:** autonomous scientific discovery needs an intermediate scientific language between papers and hypotheses—one that preserves provenance, scope, uncertainty, and falsifiability.

The result is neither a paper database nor a generic chat interface. It is a living map where evidence-linked Principles can be connected to higher-order Meta-Principles, combined into candidate relations, and developed into locally controlled derived Principles.

<p align="center">
  <a href="./assets/screenshots-v1.4.1-aug23/home.png">
    <img src="./assets/screenshots-v1.4.1-aug23/home.png" alt="Principia v1.4.1 New Research workspace and living Principles map" width="100%">
  </a>
</p>

## Scientific object model

Principia represents scientific knowledge as a small set of typed, composable objects:

```text
scientific Works
      │  provenance
      ▼
literature Principles  ───── typed relations ─────  literature Principles
      │
      │  foundation assessment
      ▼
Meta-Principles
      │
      │  explicitly selected reasoning context
      ▼
virtual connections and derived Principles
      │
      ▼
validation, revision, or rejection
```

| Object | Scientific contract | Why it matters |
| --- | --- | --- |
| **Work** | A public source identity and bibliographic record. | Keeps every reusable claim connected to where it came from. |
| **Literature Principle** | An evidence-linked claim that retains its argument, scope, conditions, boundaries, falsifier, provenance, relations, and revision history. | Converts papers into scientific units that can be compared, transferred, challenged, and reused. |
| **Meta-Principle** | A higher-order law, constraint, invariant, scaling relation, impossibility result, causal regularity, or design trade-off that can organize claims across domains. | Supplies deeper foundations without erasing domain-specific assumptions. |
| **Derived / virtual artifact** | A candidate connection or Principle produced from an explicitly selected set of literature and Meta-Principles. | Turns retrieval into controlled hypothesis construction rather than unconstrained brainstorming. |

Meta-grounding is deliberately non-authoritative. A Meta-Principle may explain or organize a literature claim, but it cannot rescue unsupported evidence. Conversely, a scientifically sound frontier Principle may remain ungrounded when no compatible foundation is known.

## From retrieval to derivation

| **01 · Discover** | **02 · Inspect** | **03 · Derive** |
| --- | --- | --- |
| Paper-first Global retrieval finds relevant Works, expands them through explicit Work–Principle provenance, and ranks the resulting Principles. Optional Local extraction runs only on folders the user selects. | A scalable WebGL map distinguishes literature Principles, Meta-Principles, and virtual hypotheses. The shared inspector exposes argument, conditions, boundaries, applications, reliability, influence, revisions, relations, and public sources. | **Derive connection** creates removable candidate edges. **Derive Principles** performs multi-level reasoning over up to 20 selected records, balancing novelty with scientific defensibility. |

Global retrieval and selected Local extraction run independently and concurrently. Top-ranked literature Principles and their valid Meta foundations enter the graph first, while the complete Global, Local, and Meta result sets continue to stream into the workspace. Projects preserve graph membership, layout, viewport, results, and virtual artifacts across sessions.

<p align="center">
  <a href="./assets/screenshots-v1.4.1-aug23/project-page.png">
    <img src="./assets/screenshots-v1.4.1-aug23/project-page.png" alt="Principia v1.4.1 project workspace with literature Principles, Meta-Principles, virtual hypotheses, and the scientific record inspector" width="100%">
  </a>
</p>

Search results are therefore not the endpoint. They become a bounded and inspectable reasoning context from which researchers can construct, compare, revise, and eventually test new hypotheses. Derived objects remain local, visibly distinct from canonical Cloud records, removable, and under the user's control.

## Why this architecture matters

| Academic research | Industrial R&D |
| --- | --- |
| Principia introduces an explicit intermediate representation between literature retrieval and hypothesis generation. Provenance, cross-domain transfer, foundation alignment, contradiction, revision, and falsification become first-class operations rather than hidden behavior inside a prompt. | The same representation can convert papers, technical reports, and selected private materials into reusable mechanisms, engineering constraints, failure boundaries, and candidate solutions. Local-first storage supports durable R&D memory across projects without treating generated text as institutional truth. |

**The architectural novelty is the combination:** evidence-linked abstraction, Meta-Principle grounding, graph-native exploration, and local hypothesis derivation operate inside one revisioned scientific system. The distinction from conventional document-centric RAG is structural: Principia retrieves and composes scientific objects and relations, not only passages.

## Global Principles Cloud

The Global Principles Cloud is maintained as reviewable canonical JSON under [`global-cloud/`](./global-cloud/). Literature Principles and Meta-Principles are separately sharded but implement one versioned scientific contract and share the derived search and graph indexes.

<p align="center"><strong>v1.4.1 launch snapshot</strong></p>

<table>
  <tr>
    <td align="center"><strong>958</strong><br>Works</td>
    <td align="center"><strong>676</strong><br>Literature Principles</td>
    <td align="center"><strong>405</strong><br>Active Meta-Principles</td>
    <td align="center"><strong>1,081</strong><br>Active Principles</td>
  </tr>
  <tr>
    <td align="center"><strong>2,101</strong><br>Provenance links</td>
    <td align="center"><strong>468</strong><br>Principle relations</td>
    <td align="center"><strong>84</strong><br>Foundation links</td>
    <td align="center"><strong>676</strong><br>Foundation assessments</td>
  </tr>
</table>

The Cloud grows through reviewed, data-only releases; the [latest verified Cloud release](https://github.com/pzqpzq/Principia/releases/latest) provides the live manifest and counts. Canonical updates append revisions rather than erasing history. Public bibliographic metadata and source links remain inspectable, while PDFs, extracted full text, credentials, private URLs, and absolute local paths are forbidden from the Cloud.

GitHub is the distribution layer, not a live database. Deterministic builders publish verified SQLite/vector `.pcg` snapshots and optional `.pcd` deltas through GitHub Releases. Clients validate hashes, schemas, counts, and vector contracts before atomic activation, retain the preceding verified generation for rollback, and degrade visibly to SQLite FTS when semantic vectors are unavailable.

## Local-first by construction

| Boundary | Stored content |
| --- | --- |
| **Shared Cloud cache** | Public, paper-free metadata, Principles, relations, indexes, and verified manifests |
| **Working directory** | Sessions, jobs, provider settings, local Principles, layouts, and virtual artifacts |
| **`local_data/` and connected folders** | User-controlled PDFs, text, notes, and acquired literature |

Connected folders are unselected by default, and private documents are processed only after explicit selection. No local content is uploaded during Global search. Provider credentials are kept through the operating-system credential mechanism and are excluded from frontend state, logs, events, databases, changesets, and artifacts.

## Install and open v1.4.1

v1.4.1 is currently published from source. The stable PyPI release remains v1.3.3 until the v1.4.1 distribution is released separately.

```bash
git clone https://github.com/pzqpzq/Principia.git
cd Principia

python -m venv .venv
source .venv/bin/activate
python -m pip install -e "./Principia-v1.4.1/core[local]"

principia open --working-directory ./principia-workspace
```

Principia opens on a loopback address in the browser. The packaged React application is included in the Python source; Node.js is required only for frontend development.

<details>
<summary><strong>Development and verification</strong></summary>

```bash
cd Principia-v1.4.1/core

python -m pip install -e ".[dev,local]"
python -m pytest -q
python -m ruff check src tests scripts

cd frontend
corepack pnpm install --frozen-lockfile
corepack pnpm test -- --run
corepack pnpm build
```

</details>

### v1.4.1 resources

- [Public v1.4.1 source](./Principia-v1.4.1/core/)
- [Core README](./Principia-v1.4.1/core/README.md)
- [Global Cloud architecture](./Principia-v1.4.1/core/docs/v1.4.1/global-cloud.md)
- [Privacy and security](./Principia-v1.4.1/core/docs/v1.4.1/privacy-security.md)
- [Recovery and deployment](./Principia-v1.4.1/core/docs/v1.4.1/recovery-deployment.md)
- [Canonical Cloud data](./global-cloud/)
- [OpenAPI contract](./Principia-v1.4.1/core/src/principia/openapi-v1.json)
- [Changelog](./Principia-v1.4.1/core/CHANGELOG.md)

---

# Principia v1.3.3 — Evidence-Grounded Idea Discovery

<p align="center"><strong>Ideas from principles. Validated by evidence.</strong></p>

v1.3.3 remains the stable PyPI workflow for turning public literature and optional private research materials into traceable **Idea Cards**, prior-art comparisons, and validation-ready research packs.

```text
research goal
    ↓
public literature + optional private corpus
    ↓
typed scientific feature extraction
    ↓
canonical evidence packet
    ↓
SciDialect-Evo idea generation
    ↓
prior-art comparison
    ↓
deterministic validation plan
```

## What v1.3.3 provides

| Capability | Purpose |
| --- | --- |
| Cross-domain retrieval | Search arXiv, OpenAlex, Crossref, Semantic Scholar, and Europe PMC with identity reconciliation and diagnostics |
| Private research context | Add PDFs, Office files, Markdown, LaTeX, code, and structured text under explicit privacy controls |
| Structured extraction | Convert works into typed ideas, Principles, takeaways, comparators, evaluation contexts, and result facts |
| Canonical evidence | Require every selected citation to resolve to an exact evidence record |
| Strict SciDialect-Evo | Generate three candidates, evolve the strongest two, select one, allow one grounded repair, and fail closed |
| Prior-art comparison | Compare mechanistic similarity, essential differences, potential advantages, and weaknesses |
| Validation hand-off | Derive human-readable and JSON validation plans without another LLM call |
| Controllable jobs | Persist progress, events, checkpoints, pause/resume/stop state, and outputs |

## Install v1.3.3

```bash
python -m pip install principia-ai==1.3.3
```

Optional Office and notebook support:

```bash
python -m pip install "principia-ai[local,notebook]==1.3.3"
```

## One-call workflow

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

`PipelineConfig.research()` requests 50 public works, constructs an exact 15-record evidence packet, limits per-work concentration, reports retrieval/reranking diagnostics, and runs strict SciDialect-Evo generation.

The result is exported as a seven-file research pack:

```text
idea.md
idea.json
evidence.json
comparison.json
result.json
validation_plan.md
validation_plan.json
```

Generated Idea Cards are hypotheses, not experimentally confirmed discoveries. Canonical evidence improves provenance and recoverability; it does not guarantee that the source or resulting idea is correct.

### v1.3.3 resources

- [Complete v1.3.3 README](./Principia-v1.3/README.md)
- [Examples](./Principia-v1.3/examples/)
- [API reference](./Principia-v1.3/docs/api.md)
- [Private corpus ingestion](./Principia-v1.3/docs/local-corpus.md)
- [Trustworthiness](./Principia-v1.3/docs/trustworthiness.md)
- [Release QA](./Principia-v1.3/RELEASE_QA.md)
- [PyPI release](https://pypi.org/project/principia-ai/1.3.3/)

---

# Research foundations

Principia is shaped by a broader question:

> **What representations should AI agents create, exchange, preserve, and evolve when the objective is scientific discovery rather than fluent conversation?**

## Machine Dialectology and CLSR

[Machine Dialectology](https://github.com/pzqpzq/LSF_MDia) studies how heterogeneous LLM agents can invent, exchange, route, and evolve compact machine-oriented languages. Its ICML 2026 precursor, **When LLMs Develop Languages: Symbolic Communication for Efficient Multi-Agent Reasoning**, introduces Communicative Language Symbolism Routing (CLSR).

- [ICML 2026](https://icml.cc/virtual/2026/poster/61557)
- [OpenReview](https://openreview.net/forum?id=ovpL0ujD6j)
- [arXiv:2606.29354](https://arxiv.org/abs/2606.29354)
- [Code](https://github.com/pzqpzq/LSF_MDia)

Its connection to Principia is representational: mechanisms, constraints, analogies, trade-offs, and falsification rules must become reusable intermediate objects before they can be composed efficiently.

## SciDialect

SciDialect studies **grounded symbolic compression** as an intrinsic reward for scientific discovery agents. Compact states are useful only when task-critical meaning, evidence anchors, and reconstruction remain recoverable.

Principia operationalizes this philosophy through typed scientific objects, explicit evidence references, bounded generation trace, strict validation, and fail-closed persistence.

---

# Repository map

```text
Principia/
  README.md                       # v1.4.1 project overview
  assets/                         # product screenshots
  global-cloud/                   # canonical, paper-free Cloud data and schemas
  Principia-v1.4.1/
    core/                         # regular-user package, API, UI, tests, and docs
  Principia-v1.3/                 # maintained v1.3.3 framework and examples
  legacy/                         # historical releases
```

# Responsible interpretation

Principia is a research framework, not an oracle.

- A fluent claim is not automatically a Principle.
- A reviewed record is not automatically universal outside its stated scope.
- A foundation link is not proof of truth.
- A relation score is not a probability of correctness.
- A virtual Principle is a hypothesis, not a confirmed contribution.
- A generated connection suggests a reasoning path; it does not replace empirical validation.

The intended standard is simple:

> **Every persuasive claim should be paired with an inspectable source, an explicit scope or assumption, and a test that could prove it wrong.**

# Citation

```bibtex
@inproceedings{
pei2026when,
title={When {LLM}s Develop Languages: Symbolic Communication for Efficient Multi-Agent Reasoning},
author={Zhengqi Pei and Qingming Huang and Shuhui Wang},
booktitle={Forty-third International Conference on Machine Learning},
year={2026},
url={https://openreview.net/forum?id=ovpL0ujD6j}
}
```

# License and contact

The repository root is distributed under the [Apache License 2.0](./LICENSE). The v1.4.1 regular-user core is separately released under the [MIT License](./Principia-v1.4.1/core/LICENSE).

**Academic collaboration**  
Institute of Computing Technology, Chinese Academy of Sciences  
`peizhengqi22@mails.ucas.ac.cn`

**Business collaboration**  
Beijing Chipflow Technology Co., Ltd.  
`peizhengqi@chipflow.net`

---

<p align="center"><strong>Let scientific knowledge compound: from works, to Principles, to solutions.</strong></p>

<p align="center">If Principia is useful to your research, consider <a href="https://github.com/pzqpzq/Principia">starring the repository</a> and following the evolution of the Principles Cloud.</p>
