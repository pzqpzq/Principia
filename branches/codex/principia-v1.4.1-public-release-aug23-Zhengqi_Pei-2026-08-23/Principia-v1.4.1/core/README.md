<h1 align="center">Principia v1.4.1</h1>

<p align="center"><strong>The living Principles Cloud for Autonomous Scientific Discovery</strong></p>
<p align="center"><em>From scientific works to reusable Principles. From Principles to solutions.</em></p>

<p align="center">
  <a href="https://github.com/pzqpzq/Principia/actions/workflows/principia-v141-ci.yml"><img alt="v1.4.1 CI" src="https://github.com/pzqpzq/Principia/actions/workflows/principia-v141-ci.yml/badge.svg"></a>
  <a href="https://github.com/pzqpzq/Principia/tree/main/Principia-v1.4.1/core"><img alt="Release v1.4.1" src="https://img.shields.io/badge/release-v1.4.1-111827?style=flat-square"></a>
  <a href="https://github.com/pzqpzq/Principia/blob/main/Principia-v1.4.1/core/LICENSE"><img alt="MIT license" src="https://img.shields.io/badge/license-MIT-0F766E?style=flat-square"></a>
  <a href="https://img.shields.io/badge/Python-3.10%E2%80%933.13-3776AB?style=flat-square"><img alt="Python 3.10–3.13" src="https://img.shields.io/badge/Python-3.10%E2%80%933.13-3776AB?style=flat-square&amp;logo=python&amp;logoColor=white"></a>
</p>

Principia v1.4.1 is the regular-user application for exploring the Global Principles Cloud and extracting reusable scientific Principles from explicitly selected local literature. It combines paper-first retrieval, Meta-Principle foundations, a scalable WebGL knowledge map, and durable research sessions in one local-first browser workspace.

For the product narrative and full-size screenshots, see the [repository README](../../README.md).

## What is new

- **One New Research workspace.** Search, Local extraction, results, inspection, graph editing, and model settings remain in one continuous interface.
- **A unified Principles graph.** Literature Principles and Meta-Principles are visually distinct, semantically searchable, and connected through validated relations.
- **Paper-first Global retrieval.** Relevant Works are retrieved first and expanded through explicit Work–Principle provenance before direct Principle fallback.
- **Meta-aware scientific structure.** Literature claims may be grounded in zero to four compatible Meta-Principles without using a Meta match to rescue unsupported evidence.
- **Durable projects and sessions.** Graph membership, layout, viewport, results, and virtual artifacts save automatically.
- **Optional Local work.** Connected folders are unselected by default; only explicitly selected sources enter model-assisted extraction.
- **Local hypothesis tools.** Users can derive virtual connections and virtual Principles from up to 20 selected records while keeping those artifacts visibly distinct from canonical Cloud records.
- **Verified offline Cloud.** Canonical records are distributed as hashed snapshots, activated atomically, and retained for rollback.

## Install from source

The stable PyPI release remains v1.3.3. Install v1.4.1 from this repository until its distribution is released separately:

```bash
git clone https://github.com/pzqpzq/Principia.git
cd Principia

python -m venv .venv
source .venv/bin/activate
python -m pip install -e "./Principia-v1.4.1/core[local]"
```

Open the application with an isolated working directory:

```bash
principia open --working-directory ./principia-workspace
```

Principia creates `workspace/` for durable application state and `local_data/` for user-controlled source material acquired within the application. Existing literature folders can be connected from any location without being copied.

## The regular-user workflow

1. Open **New Research** and select a working directory.
2. Enter a research goal and search the Global Cloud.
3. Optionally open the secondary Local controls and select folders or find papers online.
4. Global retrieval and selected Local extraction proceed independently and concurrently.
5. The five highest-ranked literature Principles and their valid Meta foundations enter the graph first.
6. All Global, Local, and Meta results continue into the hideable result tray.
7. Inspect sources and relations, adjust graph membership, or derive local virtual artifacts.

A failed Local provider call does not erase successful Global results. A failed Global sync does not erase verified offline data. No local document is uploaded during Cloud search.

## Scientific object model

The schema-v2 Cloud treats literature and Meta records as two classes of a shared revisioned Principle contract. Records can carry:

- argument and interpretation;
- scope, conditions, boundaries, and falsifier;
- applications, maturity, stability, and significance;
- public Work provenance and revision history;
- typed Principle relations;
- foundation assessments and zero or more defensible Meta links.

A valid literature Principle may have no compatible Meta root. Such a record remains available as `ungrounded_solid`; being ungrounded is not classified automatically as either disruptive or invalid.

## Cloud architecture

```text
canonical JSON revisions in Git
            ↓
deterministic snapshot builder
            ↓
verified SQLite/vector release snapshot
            ↓
shared local cache with atomic activation
            ↓
paper-first search and viewport graph access
```

Git stores reviewable canonical metadata and audit receipts. Derived `.pcg` snapshots and `.pcd` deltas are Release assets rather than ordinary Git blobs. Clients verify hashes, schemas, logical counts, and vector contracts before activation and keep the previous verified snapshot for rollback.

The Cloud forbids PDFs, extracted source text, credentials, absolute local paths, and private URLs. Public bibliographic metadata and source links are retained.

## Privacy boundaries

| Boundary | Purpose |
| --- | --- |
| Shared Cloud cache | Public, paper-free records and search indexes reusable across working directories |
| Working directory | Sessions, jobs, settings, local Principles, layouts, and virtual artifacts |
| `local_data/` and connected folders | User-controlled source files |
| Operating-system credential store | Provider secrets, excluded from databases, logs, events, and frontend state |

The public package contains the regular-user product and neutral read-only Cloud infrastructure only. Privileged Cloud-maintenance software and credentials are not shipped in this source tree, frontend bundle, wheel, or source distribution.

## Development

```bash
python -m pip install -e ".[dev,local]"
python -m pytest -q
python -m ruff check src tests scripts
```

Frontend development uses pnpm:

```bash
cd frontend
corepack pnpm install --frozen-lockfile
corepack pnpm test -- --run
corepack pnpm build
```

The generated frontend under `src/principia/ui_dist/` is included in Python distributions so installed users do not need Node.js.

## Documentation

- [Global Cloud v2](docs/v1.4.1/global-cloud.md)
- [Privacy and security](docs/v1.4.1/privacy-security.md)
- [Recovery and deployment](docs/v1.4.1/recovery-deployment.md)
- [Getting started](docs/v1.4/getting-started.md)
- [Local literature discovery](docs/v1.4/local-literature-discovery.md)
- [Storage and portability](docs/v1.4/storage-and-portability.md)
- [API reference](docs/api.md)
- [OpenAPI contract](src/principia/openapi-v1.json)
- [Changelog](CHANGELOG.md)

## Responsible interpretation

Principia is a research framework, not an oracle. A fluent claim is not automatically a Principle; a foundation link is not proof of truth; and a virtual Principle is a hypothesis rather than a confirmed contribution. Every persuasive claim should remain paired with an inspectable source, an explicit scope or assumption, and a test that could prove it wrong.

## License

The v1.4.1 regular-user core is released under the [MIT License](LICENSE). The repository root uses Apache License 2.0.
