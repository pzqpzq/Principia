<h1 align="center">Principia</h1>

<p align="center"><strong>Autonomous Scientific Discovery, grounded in Principles and tested against data.</strong></p>
<p align="center">Explore scientific knowledge. Discover interpretable Rules. Inspect the evidence.</p>

<p align="center">
  <a href="./Principia-v1.4.2/"><img alt="Principia v1.4.2 source release" src="https://img.shields.io/badge/Principia-v1.4.2-111827?style=flat-square&amp;logo=github"></a>
  <a href="#five-demo-projects"><img alt="Five included demo projects" src="https://img.shields.io/badge/demo_projects-5-0F766E?style=flat-square"></a>
  <a href="./ASD-benchmarks/"><img alt="Principia ASD Benchmark: 100 scientific scenarios" src="https://img.shields.io/badge/ASD_benchmark-100_scenarios-2563EB?style=flat-square"></a>
  <a href="./Principia-v1.4.2/core-v1.4.2/LICENSE"><img alt="MIT licensed application" src="https://img.shields.io/badge/code-MIT-0F766E?style=flat-square"></a>
  <a href="https://arxiv.org/abs/2606.29354"><img alt="ICML 2026 research" src="https://img.shields.io/badge/ICML-2026-6D4AFF?style=flat-square"></a>
</p>

<p align="center">
  <a href="#start-v142-locally">Quick start</a> ·
  <a href="#five-demo-projects">Included projects</a> ·
  <a href="#from-local-data-to-an-inspectable-rule">Discovery workflow</a> ·
  <a href="#principia-100-scientific-discovery-benchmark">ASD benchmark</a> ·
  <a href="#principia-v141">v1.4.1</a> ·
  <a href="#research-foundations">Research</a>
</p>

---

# Principia v1.4.2

**Bring a research goal and a local dataset. Principia connects scientific context with executable analysis to look for compact, interpretable relationships—and keeps the evidence behind each result available for inspection.**

Version 1.4.2 brings dataset-native **Autonomous Scientific Discovery (ASD)** into the Principles workspace. Literature Principles provide scientific context; observations describe computed evidence; extracted Rules carry equations, calibration results, validation decisions, and a stated scope. A study map connects these objects so you can move from a promising relationship to the records that support it.

The release includes **five demo public-data projects**, analyzed with **DeepSeek-V4-Pro**. Their saved maps, results, equations, and packaged evidence open locally without the original datasets or an API key. Connect your own data and models when you are ready to begin a new discovery.

<p align="center">
  <a href="./assets/screenshots-v1.4.2-sep7/main-page.png"><img src="./assets/screenshots-v1.4.2-sep7/main-page.png" alt="Principia v1.4.2 home: research goal input, scientific area filters, Principles map, and five projects in the sidebar" width="100%"></a>
  <br><sub>A shared scientific workspace: explore Principles by area, enter a research goal, or return to a saved project.</sub>
</p>

## From local data to an inspectable Rule

| Stage | What Principia does | What you can inspect |
| :--- | :--- | :--- |
| **Inventory & understand** | Reads supported files, profiles measurements, and connects variables with the research goal and scientific context. | Source inventory, formats, units, coverage, and interpretation. |
| **Generate & evaluate** | Proposes candidate expressions, fits them on development data, and uses validation evidence to compare alternatives. | Executable expressions, fitted parameters, baselines, and candidate tests. |
| **Challenge** | Applies recorded held-out checks and evidence gates before promoting an executable relationship. | Split definitions, errors, controls, failure reasons, and limits of applicability. |
| **Synthesize & explore** | Presents supported Rules alongside observations and relevant Principles in a saved study map. | Typeset equations, plain-language interpretation, linked evidence, and the underlying numerical records. |

**The result is a scientific object you can examine.** A strong fit alone does not establish a mechanism. Known identities, empirical relationships, and tentative interpretations retain their own evidential scope; unsuccessful candidates remain part of the study record. A dataset may produce observations without a Rule that passes the available checks.

<p align="center">
  <a href="./assets/screenshots-v1.4.2-sep7/project-page.png"><img src="./assets/screenshots-v1.4.2-sep7/project-page.png" alt="Rydberg electric-field calibration project with its saved study map, connected Principles, observations, and extracted Rule" width="100%"></a>
  <br><sub>The Rydberg project: move between the study map, discovery results, and individual evidence records.</sub>
</p>

The workspace also supports **Discover again** with a new project by default, configurable reasoning and vision models, visible task activity and stop controls, resizable information panels, and project deletion. Data and workspace state remain separate, so repeated discovery does not require copying the source dataset into each project.

## Five demo projects

These examples span atomic sensing, seismology, particle physics, thin-film metrology, and human movement. Three were selected from the initial twenty-scenario discovery campaign; two were added during subsequent user testing. They illustrate different kinds of useful scientific output, rather than a claim that every recovered relationship is a new law of nature.

| Included project | Relationship to explore | Recorded evidence and scope |
| :--- | :--- | :--- |
| **Rydberg electric-field calibration** | Field amplitude follows a square-root RF-power form: $E_r(P)=b_r+\kappa_r\sqrt{P}$. | Optical and ion readouts have held-out RMSE of **0.0825 and 0.0923 V/m**, over **92% below** their development-mean baselines. Only two held-out power settings per readout; both share the same RF chain. |
| **Earthquake magnitude scaling** | A one-parameter exponential describes conditional magnitude-exceedance fractions: $S(M)=\exp[-\beta(M-2.5)]$. | **18 development, 6 validation, and 7 test days**; test normalized RMSE **0.1267**, versus **0.6584** for the frozen linear baseline. Restricted to the retained `ml` catalog subset; it does not predict event times or locations. |
| **ATLAS transverse momentum** | A parameter-free vector identity: $p_T=\sqrt{p_x^2+p_y^2}$, with a corresponding direction check. | **78,227 events** in two held-out period files; 99th-percentile relative magnitude error about **1.17 × 10⁻⁷**. This checks representation consistency and recovers known geometry. |
| **Hafnia wafer measurements** | A spatial relationship connects measured thin-film thickness with position on a wafer. | Held-out normalized RMSE **0.7471**, **41.1% below** a constant baseline. A fit for the measured specimen; transfer to another wafer remains untested. |
| **Walking dynamics** | Contact moment is reconstructed from normal load and pressure-center displacement. | An executable force-plate consistency relationship under the recorded coordinate convention; it is not evidence of a new biological mechanism. |

Open **Dataset & evidence** for each project's provenance and selection rationale. Open a Rule to inspect its equation, calibration, comparisons, and limitations. Rounded display values are backed by full-precision records. The [demo guide](./Principia-v1.4.2/core-v1.4.2/docs/v1.4.2/demo-projects.md) explains portability, reruns, and deletion.

<table>
  <tr>
    <td width="50%" valign="top">
      <a href="./assets/screenshots-v1.4.2-sep7/principle-page.png"><img src="./assets/screenshots-v1.4.2-sep7/principle-page.png" alt="Principle inspector showing thermodynamic favorability, reaction-rate distinctions, scientific scope, and supporting context" width="100%"></a>
      <p><strong>Inspect a Principle.</strong><br>Read the scientific statement, its scope, and supporting context without leaving the project.</p>
    </td>
    <td width="50%" valign="top">
      <a href="./assets/screenshots-v1.4.2-sep7/rule-page.png"><img src="./assets/screenshots-v1.4.2-sep7/rule-page.png" alt="Earthquake magnitude Rule inspector with a typeset exponential equation, validation metrics, interpretation, and evidence" width="100%"></a>
      <p><strong>Interrogate a Rule.</strong><br>Follow a typeset equation through interpretation, quantitative checks, and evidence. Click either image for full resolution.</p>
    </td>
  </tr>
</table>

## Start v1.4.2 locally

Use **Python 3.11 or 3.12** in a virtual environment. This is the GitHub source release; the commands below do not depend on a matching version being published to PyPI.

**Download the application without the separate public test corpus.**

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/pzqpzq/Principia.git
cd Principia
git sparse-checkout set Principia-v1.4.2
```

**For Linux or macOS**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install "./Principia-v1.4.2/core-v1.4.2[asd,local]"
principia open --working-directory ./principia-workspace --port 8142
```

**For Windows**

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install "./Principia-v1.4.2/core-v1.4.2[asd,local]"
principia open --working-directory ./principia-workspace --port 8142

# for Windows users after frontend changes
# If the frontend code has been modified, rebuild the frontend and reinstall the local package using the following commands:
cd "Principia\Principia-v1.4.2\core-v1.4.2\frontend"
pnpm build

cd ..
pip install -e .
```

The application opens at **http://127.0.0.1:8142/**. Its frontend is already built; Node.js is needed only for frontend development. Dependency installation requires internet access. Once installed, the five demos and their packaged evidence can be browsed offline; external publisher links and remote model calls require a connection.

Demos initialize **once in an empty workspace**. Existing projects are preserved, and deleted demos do not reappear on restart. To try the included projects separately from existing work, choose a new working directory.

### Discover from your own data

1. Choose **New research**, use **Add data** to connect a local folder, and describe your research goal.
2. Open **Sources & model** to configure your provider credentials and select reasoning and vision models. The included examples used **DeepSeek-V4-Pro via SiliconFlow**; new runs use your own configuration.
3. Start discovery and review the provider permission request. **View activity** shows task progress, models, source information, and stop controls.
4. Inspect observations and Rules, follow the evidence, or use **Discover again** to change the goal, data, or models. Keep a new attempt as a separate project or explicitly overwrite the current project.

Raw files remain in the selected folders. Remote analysis can send bounded profiles, excerpts, or previews after per-run permission; it is not a promise of zero network egress. No author credentials or original demo datasets are packaged with the application. A new computation on a demo requires reconnecting the relevant public data. See [ASD](./Principia-v1.4.2/core-v1.4.2/docs/v1.4.2/data-discovery.md), [privacy](./Principia-v1.4.2/core-v1.4.2/docs/v1.4/privacy-and-security.md), and [storage](./Principia-v1.4.2/core-v1.4.2/docs/v1.4.2/storage-policy.md).


# Principia-100 scientific discovery benchmark

**[Principia-100](./ASD-benchmarks/) brings 100 source-verifiable scientific scenarios to autonomous discovery: native data, practical research questions, and a protocol for testing the resulting equations.** It is a core part of Principia's research ecosystem and is also usable with other discovery systems.

<p align="center">
  <a href="./ASD-benchmarks/"><img src="./ASD-benchmarks/assets/principia-100.svg" alt="Principia-100: 100 scientific scenarios connecting native data, equations, and evidence" width="100%"></a>
</p>

The collection spans **semiconductor devices, materials, physics, biology, medicine, environmental science, society, computing and mathematics**. It retains heterogeneous source formats: spreadsheets, instrument logs, scientific arrays, images, audio, video, spatial records and computational trajectories. Every case includes source attribution, reuse terms, checksums, a neutral brief and a scientific task card with validation units and limitations.

| What is included | Why it matters |
| :--- | :--- |
| **100 scenarios · 1,685 frozen scientific assets** | Study realistic research folders with source-native organization and documented processing. |
| **85 measured/observed cases**, plus clearly labeled mixed, computational and reference cases | Examine a broad range of evidence without confusing simulation with observation. |
| **100 task cards and an evaluation protocol** | Test executable relationships with uncertainty, baselines, falsifying controls and appropriate held-out groups. |
| **A catalog, source/license registers and replay tools** | Choose cases, trace evidence and reconstruct the exact released inputs. |

Start with [membrane permeation](./ASD-benchmarks/task_cards/061.md), [industrial screw driving](./ASD-benchmarks/task_cards/053.md), [CHO bioreactor cultivations](./ASD-benchmarks/task_cards/071.md), or [Arctic ocean profiles](./ASD-benchmarks/task_cards/094.md). Download a selected case, connect it through **New research → Add data**, and use its `USER_BRIEF.txt` as a starting research goal. For a formal benchmark study, follow the input allowlist and freeze the case-specific validation design first.

**[Explore all 100 →](./ASD-benchmarks/CATALOG.md)** · **[Download selected cases](./ASD-benchmarks/DOWNLOAD.md)** · **[Read the protocol](./ASD-benchmarks/EVALUATION_PROTOCOL.md)**

The full benchmark is about **4.80 GB** and uses **Git LFS** for large assets; it is optional and separate from the application installation above. This is an **open, source-aware corpus**: published analyses are disclosed, the original 20 scenarios were used during Principia development, and native-reader support is distinguished from application ingestion. Reproduction, validated extension, novelty candidate and justified abstention are separate outcomes. The release supplies research inputs and evaluation standards, without claiming 100 unknown laws or an aggregate discovery score.

Dataset reuse follows the [source-specific terms](./ASD-benchmarks/LICENSES.md). The earlier [`scenario/`](./scenario/) directory remains a historical collection; use the versioned `ASD-benchmarks/` corpus for new benchmark studies.

## Built for inspection and continued work

The release separates source data, runtime state, and portable demonstration results. Its demo bundle is compressed and checksummed; it carries saved study records, executable Rules, calibrations, and selected derived artifacts without shipping an old runtime database. A clean-release size gate excludes environments, caches, private folders, and credentials. Backend and frontend checks, schema validation, archive hygiene, and a fresh-workspace demo check are included in [v1.4.2 CI](./.github/workflows/principia-v142-ci.yml).

Explore the [source](./Principia-v1.4.2/), read the [demo guide](./Principia-v1.4.2/core-v1.4.2/docs/v1.4.2/demo-projects.md), or browse the [recorded release checks](./Principia-v1.4.2/core-v1.4.2/qa-v1.4.2.json). Computational reproduction requires the original inputs and the recorded analysis conditions; a packaged result remains evidence to assess, not independent replication.

**Help improve Principia.** Share a reproducible issue, a difficult public dataset, or a scientifically meaningful failure case in [GitHub Issues](https://github.com/pzqpzq/Principia/issues). Star or watch the repository to follow development of the Principles Cloud and data-driven scientific discovery.

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
