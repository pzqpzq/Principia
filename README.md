# Principia

<p align="center">
  <strong>A local-first research intelligence workspace for turning a rough research goal into structured field knowledge and new idea drafts.</strong>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> ·
  <a href="#workflow">Workflow</a> ·
  <a href="#architecture">Architecture</a> ·
  <a href="#configuration">Configuration</a> ·
  <a href="#quality-and-safety">Quality and Safety</a>
</p>

---

## Overview

Principia is a project-first research workspace for researchers, builders, and product teams who need a clearer view of a technical field before proposing a new idea.

Given a research goal or idea draft, Principia helps collect relevant works, structure their essential ideas, identify reusable principles and takeaway messages, extract benchmarks and baselines, and synthesize a new idea grounded in the selected evidence.

The app is intentionally local-first:

- User projects live in a local SQLite database.
- API keys stay on the user's machine in `.env`.
- The frontend is static HTML/CSS/JS served by a small Python standard-library backend.
- No project data is bundled in this repository.

## Core Capabilities

| Area | What Principia Provides |
| --- | --- |
| Project workspace | Create local projects and scope all research records to the active project. |
| Research pipeline | Search related papers and technical sources, then structure them into reusable field knowledge. |
| Existed Ideas | Concise statements of the essential innovations found in prior works. |
| Principles | Fundamental, reusable mechanisms or conclusions supported by the field evidence. |
| Takeaway Messages | Nontrivial empirical lessons and reusable findings, filtered to avoid generic claims. |
| Benchmarks | Public datasets or benchmark suites used by the retrieved works, with official links where available. |
| Baselines | Comparable methods suitable for experiment tables, with source papers, code links, and performance evidence where available. |
| Idea generation | Generate new ideas from selected existed ideas, principles, takeaway messages, and the user's own idea note. |
| Idea detail page | Review novelty, mechanism, validation plan, risks, related existed-idea comparisons, and a principle map. |

## Quick Start

Clone or download this repository, then run:

```bash
python3 principia.py serve
```

Open:

```text
http://127.0.0.1:8790/
```

On first launch, Principia creates a local database:

```text
data/principia.sqlite
```

## Workflow

1. Create a project.
2. Enter a research goal or idea draft.
3. Choose an LLM and target work count.
4. Click `Research` to collect and structure related field knowledge.
5. Inspect `Existed Ideas`, `Benchmarks`, `Baselines`, `Principles`, and `Takeaway Messages`.
6. Click `Generate Idea`.
7. Select evidence, add your own idea note, choose a target LLM, and generate.
8. Open the generated idea detail page from `My Ideas`.

## Architecture

```text
Principia
├── principia.py              # CLI entry point
├── principia_demo/
│   ├── server.py             # Local HTTP API and static file server
│   ├── engine.py             # Research, extraction, merge, and idea-generation logic
│   ├── llm_client.py         # SiliconFlow/OpenAI-compatible LLM calls
│   ├── research_sources.py   # Hybrid paper/source discovery
│   ├── storage.py            # SQLite-backed local object store
│   └── models.py             # Core record models
├── static/
│   ├── index.html            # Main app
│   ├── app.js                # Project workspace frontend
│   ├── idea.html / idea.js   # Generated idea detail page
│   └── item.html / item.js   # Record detail page
├── tests/                    # Offline regression tests
└── data/                     # Blank local data directory
```

## Configuration

Principia ships without secrets. Configure API keys in the app via `API Keys`, or create `.env` manually:

```bash
cp .env.example .env
```

Then edit:

```text
SILICONFLOW_API_KEY=your_siliconflow_key_here
OPENAI_API_KEY=your_openai_key_here
```

The app can use SiliconFlow-compatible chat completions and OpenAI-compatible responses/chat endpoints. At least one callable provider is required for LLM extraction and idea generation.

Useful `.env` options:

```text
PRINCIPIA_REQUEST_TIMEOUT=180
PRINCIPIA_COST_LIMIT_CNY=1000
PRINCIPIA_SSL_VERIFY=1
```

If a port is already in use:

```bash
python3 principia.py serve --port 8791
```

## Quality And Safety

Principia is designed to avoid misleading demo behavior:

- It does not ship with private data or API keys.
- It stores user data only in the local `data/principia.sqlite` database.
- LLM-dependent workflows should warn the user when a provider cannot be called.
- Quality-sensitive idea comparisons reject repetitive or template-like content instead of silently falling back to deterministic filler.
- Tests use fake/no-op LLM clients and do not spend API credits.

## Running Tests

Install the optional test dependency:

```bash
python3 -m pip install -r requirements.txt
```

Run:

```bash
python3 -m unittest discover -s tests -p 'test*.py'
```

## Reset Local Data

```bash
python3 principia.py reset --yes
```

This removes the local SQLite records and returns the app to a blank state.

## Distribution Notes

Do not commit or share:

- `.env`
- `data/*.sqlite`
- `data/*.sqlite-*`
- `__pycache__/`
- `*.pyc`
- `.DS_Store`

The included `.gitignore` excludes these files.

## Status

Principia is an actively evolving research demo. It is intended for local experimentation, product validation, and high-fidelity research workflow prototyping rather than production multi-user deployment.
