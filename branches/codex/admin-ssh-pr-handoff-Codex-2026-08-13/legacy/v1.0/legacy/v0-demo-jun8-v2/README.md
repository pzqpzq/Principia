# Principia Demo Jun 8 v0

Principia is a principle-first research ideation demo. It has two parts:

1. A pure Python script/API layer for mining reusable `PrincipleCard` objects and generating traceable `IdeaCard` objects.
2. A local web UI built on the same Python layer.

The demo is intentionally small but now uses a richer v0.3 local Field Observatory: local SQLite storage, optional SiliconFlow/OpenAI-compatible LLM calls, arXiv corpus lookup, deterministic offline fallback, PrincipleCards with reusable mechanism structure, WorkFacts, Benchmark/Baseline/Result records, GapCards, ResultEstimates, lineage graph JSON, assistant export bundles, feedback import, and Codex prompt plans.

## Quick Start

```bash
cd /Users/zhengqipei/Desktop/ChipFlow/Principia/demos/Principia-demo-jun8-v0
python3 principia.py serve --host 127.0.0.1 --port 8787
```

Open:

```text
http://127.0.0.1:8787
```

## Configure LLM Calls

The demo does not hardcode secrets. To use SiliconFlow, create `.env` from `.env.example`:

```bash
cp .env.example .env
```

Then edit `.env` and set:

```text
SILICONFLOW_API_KEY=your_key_here
```

The default base URL is:

```text
https://api.siliconflow.cn/v1
```

Model routing:

- `auto`: efficient model for simpler tasks, stronger model for complex tasks.
- `efficient`: always use `PRINCIPIA_EFFICIENT_MODEL`.
- `strong`: always use `PRINCIPIA_STRONG_MODEL`.

Cost guard:

```text
PRINCIPIA_COST_LIMIT_CNY=1000
```

The guard is conservative and estimates token cost before each LLM call. Offline mode disables LLM and arXiv calls.

If your local Python install has a broken certificate bundle, LLM calls may fail with `CERTIFICATE_VERIFY_FAILED`. The safest fix is to repair Python certificates. For a local-only demo you can set `PRINCIPIA_SSL_VERIFY=0` in `.env`, but that sends API requests without TLS verification.

## CLI Examples

Generate ideas in online mode, using up to 20 local/online works and saving the resulting works, principles, and ideas:

```bash
python3 principia.py generate "Generate a novel, testable idea for improving long-context reasoning efficiency in LLM agents." --source-mode online --paper-count 20 --ideas 4
```

Generate ideas from only the local principle pool:

```bash
python3 principia.py generate "Generate a novel, testable idea for improving long-context reasoning efficiency in LLM agents." --source-mode local --ideas 4
```

Run online-mode logic without saving newly mined works/principles:

```bash
python3 principia.py generate "Improve agent memory under strict API budget" --source-mode online --paper-count 20 --no-persist-sources
```

Run without any remote calls:

```bash
python3 principia.py generate "Improve agent memory under strict API budget" --offline --ideas 3
```

Search saved principles:

```bash
python3 principia.py principles "adaptive budget allocation under uncertainty"
```

Export a compact graph:

```bash
python3 principia.py graph --query "long-context agent reasoning"
```

Show local store counts:

```bash
python3 principia.py state
```

Reset local data:

```bash
python3 principia.py reset --yes
```

## Web UI Flow

1. Enter a research goal.
2. Choose `Online` to use local plus newly searched works, or `Local` to use only the internal principle pool.
3. In online mode, set the target work count and whether to save mined works/principles locally.
4. Click `Generate Ideas` to mine/select principles, create Idea Cards, estimate validation, and render the lineage graph.
5. Expand Principle and Idea Cards for details, open source works, or copy the Codex validation plan.
6. Open `Principia Library` to inspect the local Field Observatory dashboard, work facts, principle landscape, benchmark matrix, graph, gaps, ideas, and runs.
7. In Idea detail, copy the Codex prompt plan, export `PRINCIPIA_BUNDLE.json`, or import feedback JSON to update local principle confidence.

## Local Data

All active demo artifacts are stored in SQLite:

```text
data/principia.sqlite
```

The previous single-file JSON store is automatically migrated once, then renamed to:

```text
data/store.legacy.json
```

The SQLite store contains these logical buckets:

- `goals`
- `source_works`
- `principles`
- `principle_relations`
- `ideas`
- `estimates`
- `prompt_plans`
- `runs`
- `feedback`
- `field_profiles`
- `work_facts`
- `benchmark_records`
- `baseline_records`
- `result_records`
- `gap_cards`
- `frontier_snapshots`
- `assistant_exports`

Each v0.2 PrincipleCard stores more than a short summary: `principle_type`, `abstract_signature`, `scarce_resources`, assumptions, constraints, invariants, tradeoffs, failure modes, feedback loops, validation notes, domain tags, and relation hints. Re-mining a similar query upgrades older sparse records instead of leaving stale cards in place.

IdeaCards now include an explicit insight, mechanism design, why-it-might-work notes, validation protocol, baselines, metrics, failure modes, ranking scores, similar local ideas/works, and a cheapest falsification path through the linked ResultEstimate.

The Library page derives structured observatory records from legacy records:

- `SourceWork.work_principles`, `work_insights`, and `work_novelty` become `WorkFact` records.
- Abstracts and local facts are conservatively scanned for benchmark, baseline, and result evidence.
- Local gap cards flag missing baselines, missing benchmarks, weak assumptions, unresolved tradeoffs, contradictions, and stale principles.
- Assistant export bundles collect an idea, source principles, source works, local benchmark evidence, result estimate, prompt plan, and feedback schema.

The web UI includes a `Clean Pool` action. By default it keeps up to 500 works, 1000 principles, and 100 ideas, preserving highlighted and frequently used records first.

The web API intentionally returns a limited recent snapshot for the browser UI, while the CLI can still inspect the full local store with:

```bash
python3 principia.py state --full
```

## Tests

Run the local regression suite without spending API budget:

```bash
python3 -m unittest discover -s tests -v
```

The tests cover Chinese sparse-view reconstruction query expansion, arXiv query construction, SQLite principle-pool upgrades, online/local generation behavior, rich offline idea generation, least-used cleanup, and principle relation derivation.

## Good Demo Queries

```text
Generate a novel, testable idea for improving long-context reasoning efficiency in LLM agents.
```

```text
Find a cheap validation idea for reducing hallucination in retrieval-augmented scientific assistants.
```

```text
Design an evaluation protocol for AI coding agents that predicts post-execution idea survival.
```

```text
Generate a method idea for adaptive tool-use routing in multi-agent research systems.
```

```text
Please design a method for 稀疏数据三维重建（即在有限视角下进行三维重建）任务
```

## Scope Notes

This is not the full product from the proposal. It focuses on the two core demo loops:

- Query to related works to local principle pool.
- Local principles to idea generation, visualization, result estimation, and validation prompts.
