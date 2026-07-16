# Principia 1.3.3 Release QA

Date: 2026-07-16  
Status: **PASS — PyPI published; GitHub PR awaiting final receipt CI and merge**

This report records the checks performed against the final framework source,
the three Jul16 live acceptance runs, and the exact wheel and source archive
selected for publication. Credentials and machine-local paths are deliberately
excluded.

## Provenance and license boundary

- Upstream repository: `pzqpzq/Principia`.
- Seed commit: `11a03027855de9e25951cc012fd03730cf4a4ab7`.
- The seed contains merged pull request #8 and is the source of the broadened
  retrieval implementation hardened in this release.
- Active framework path: `Principia-v1.3/`.
- Distribution/import names: `principia-ai==1.3.3` / `principia`.
- Framework license: MIT (`Principia-v1.3/LICENSE` and package metadata).
- Repository-root license: Apache-2.0 for its separately scoped material; it
  does not replace the framework's MIT license.
- The former v1.2 visual workbench, its README, and its two historical
  tutorials are retained under `legacy/v1.2/`. Generated SQLite state and a
  machine-local manifest pointer are intentionally omitted and documented.
- The unrelated dirty maintainer checkout was not used or modified.

Exact integration path:

```text
pzqpzq/Principia@11a03027855de9e25951cc012fd03730cf4a4ab7
  -> Principia-v1.3/ framework seed
  -> local v1.3.3 retrieval/private-corpus/trustworthiness/UX revision
  -> three Jul16 cross-domain live acceptance runs
  -> verified 1.3.3 wheel and sdist
  -> codex/principia-v1.3.3-framework
  -> reviewed merge to pzqpzq/Principia main
  -> principia-ai 1.3.3 on PyPI
```

## Implemented release contract

- Reliable multi-source retrieval with bounded retry/backoff, source reports,
  adaptive target top-up, query planning, Europe PMC routing, domain-neutral
  ranking, duplicate reconciliation, and visible embedding-rerank state.
- Private-folder ingestion with portable `local://` identities, core parsers,
  optional DOCX/PPTX/XLSX parsers, parser registration, structured per-file
  diagnostics, chunked LLM extraction, and selective cache invalidation.
- Explicit consent before remote processing of private document text; local
  filesystem paths are not sent to models or written into portable exports.
- Canonical record-level evidence references, no generator configuration as
  evidence, no silent production templates, bounded live repair, and no save
  after an unresolved generation defect.
- Strict SciDialect-Evo: three explicit candidates, two critiques/evolutions,
  one selected evolved result, concise trace metadata, and no hidden reasoning.
- Shared math normalization and validation with braced scripts such as
  `$R_{cf}$`, structural checks, `pylatexenc`, and strict KaTeX compilation.
- Persisted pipeline progress and safe-boundary pause/resume/stop controls in
  Python, notebooks, and the CLI.
- Portable Idea Card, evidence, comparison, result, and Markdown/JSON
  validation artifacts; validation plans require no additional model call.
- Three concise output-bearing, credential-free public showcase notebooks
  generated from checksum-verified live acceptance artifacts.

## Final deterministic commands

All commands below were run from the final framework tree. The two KaTeX
environment variables pointed to an isolated Node 22 / KaTeX 0.16.22 runtime.

| Command | Final result |
| --- | --- |
| Python 3.10.4: `python -m pytest -q -p no:cacheprovider` | PASS — 212 passed, 0 skipped/warnings, 112.30 s |
| Python 3.12.7: `python -m pytest -q -p no:cacheprovider` | PASS — 212 passed, 0 skipped/warnings, 107.30 s |
| Python 3.13.0: `python -m pytest -q -p no:cacheprovider` | PASS — 212 passed, 0 skipped/warnings, 109.32 s |
| `python -m ruff check src tests scripts` | PASS — all checks passed |
| `python -m mypy src` | PASS — no issues in 27 source files |
| `python scripts/check_release_math.py . ...` | PASS — 115 spans across 59 retained release artifacts |
| `python scripts/check_release_math.py <Jul16 acceptance tree> ...` | PASS — 551 spans across 69 retained acceptance artifacts |
| `python scripts/build_showcases.py verify examples/test1` | PASS — 6 code cells, 56 lines, 5 outputs, 16,022 bytes |
| `python scripts/build_showcases.py verify examples/test2` | PASS — 6 code cells, 56 lines, 5 outputs, 15,625 bytes |
| `python scripts/build_showcases.py verify examples/test3` | PASS — 6 code cells, 56 lines, 5 outputs, 15,635 bytes |
| `python scripts/build_showcases.py readme examples --readme README.md --check` | PASS — generated table in sync |
| `shasum -a 256 -c examples/test*/checksums.sha256` | PASS — all 9 public showcase files match |
| `python -m build --no-isolation` | PASS — exactly one 1.3.3 wheel and one 1.3.3 sdist |
| `python -m twine check dist/*` | PASS — both archives |
| `python scripts/check_release_archive.py dist/*` | PASS — 153 text members and 2,015,372 uncompressed bytes scanned |
| clean installed-wheel core smoke | PASS — imports, 14 public interfaces, typing markers, CLI, dependency integrity |
| clean installed-wheel `[local]` smoke | PASS — DOCX/PPTX/XLSX parsers, 3/3 ingestion, portable URIs, no path leakage |

The local Python installer initially required a certifi CA bundle for fresh
environment downloads. This was a machine certificate-chain issue before
package installation, not a Principia archive or runtime failure.

## Jul16 live acceptance

Every task used 50 unique online works plus five local documents and produced
55 feature bundles. Public retrieval used embedding reranking; extraction used
`siliconflow:Qwen/Qwen3.6-35B-A3B`; generation used
`siliconflow:Qwen/Qwen3.5-397B-A17B` in non-degraded `scidialect-evo` mode.

| Gate | LLM multi-agent reasoning | Dynamic 3D reconstruction | Axion sensing |
| --- | ---: | ---: | ---: |
| online / local works | 50 / 5 | 50 / 5 | 50 / 5 |
| completed feature bundles | 55 | 55 | 55 |
| top-20 relevance | 100% | 100% | 100% |
| top-50 relevance | 98% | 100% | 100% |
| out-of-scope online works | 1 | 0 | 0 |
| successful metadata sources | 3 | 3 | 3 |
| embedding rerank | applied | applied | applied |
| same-day Jaccard@20 | 0.8182 | 0.7391 | 0.7391 |
| selected idea/principle/takeaway records | 5 / 5 / 5 | 5 / 5 / 5 | 5 / 5 / 5 |
| selected works / max records per work | 10 / 2 | 9 / 2 | 9 / 2 |
| selected local records / local works | 8 / 5 | 7 / 4 | 8 / 5 |
| strict trace candidates / evolutions | 3 / 2 | 3 / 2 | 3 / 2 |
| comparison rows | 3 | 5 | 3 |
| exported files | 7 | 7 | 7 |
| all 23 recorded QA gates | PASS | PASS | PASS |

Accepted ideas:

1. **Entropy-Constrained Discrete Codebook with Counterfactual Decoding and
   Diversity-Aware Calibration**
2. **AnchorSplat-Dynamic: Sparse Anchor-Based Uncertainty for Uncalibrated
   Motion**
3. **Dynamic Heuristic Optimization of Squeezed-State Haloscopes with
   Continuum Noise Modeling**

Each accepted idea has live-model origin, no manual postprocessing, canonical
local and public citations, valid mathematical notation, a nonempty prior-idea
comparison, and these seven files:

```text
idea.md
idea.json
evidence.json
comparison.json
result.json
validation_plan.md
validation_plan.json
```

### Authentic live rerun usage

Only generation, comparison, and export were rerun after the authenticity
audit; the accepted works, 55 feature bundles, and 15-record evidence packets
were reused by checksum.

| Task | Generation calls / tokens | Comparison calls / tokens | Final idea SHA-256 | Final comparison SHA-256 |
| --- | ---: | ---: | --- | --- |
| test1 | 4 / 23,883 | 2 / 8,504 | `1a13af2e8f2c83f7339567532d7a0c633136b58c6903b2a86aa7a27d1a6ed15a` | `4f95cd718b7a4bd2921f0404030f9e81045ff93077484e7be2d20d1692ff4fd8` |
| test2 | 4 / 22,479 | 1 / 3,878 | `4b07a097cde0a9107b21e10bf00845ec7b653431b23f2654c695297cb16b7762` | `7caeb87fca8b37c8472da51c7631736d7b34dc147ce679b391b79809816e263c` |
| test3 | 4 / 22,772 | 1 / 3,114 | `6471a3eb3350eaac303e46877a1d7f48fc58765c08f1ba35cb371a01f54b7625` | `58c8790549fc9b2fc5b086fb380c577dd57e43494298997b592eb5976a62680f` |

### Selective reruns and retained warnings

- The original showcase assembly had rewritten live content outside the model
  call. It was rejected. Generation, comparison, and export were rerun from
  canonical checkpointed evidence, and only untouched live outputs were kept.
- A test2 generation attempt returned safe but unbraced scripts after its one
  repair. It was not persisted. The shared math layer now canonicalizes safe
  notation-only changes before deciding whether a paid repair is needed; the
  fresh affected-stage rerun passed strict KaTeX.
- A test1 comparison attempt contained canned “difference unspecified” text.
  It was rejected. Comparison validation now rejects this boilerplate, and the
  comparison-only rerun produced three substantive rows.
- Metadata-provider partial-outage warnings remain explicit: test1 and test2
  report OpenAlex and Semantic Scholar failures; test3 reports arXiv, OpenAlex,
  and Semantic Scholar failures. Each task nevertheless completed exactly 50
  unique online works from three successful sources, with applied embedding
  reranking and passing relevance/stability thresholds.
- Extraction reports retain 58, 50, and 61 evidence-quality warnings for
  test1, test2, and test3 respectively. These identify abstract/title-only or
  short-content fallbacks, fetch failures, and successful grounded repairs;
  provenance remains complete for all 165 feature bundles.
- No unresolved template, mock-origin, canonical-reference, privacy, math,
  duplicate, rerank, or generator-contamination defect remains.

## Public showcase integrity

| Task | Notebook SHA-256 | Showcase manifest SHA-256 |
| --- | --- | --- |
| test1 | `0df8d655e02de32233d54e0764f48c670cbf66c922c8ca4bb7a3d28c6e4da212` | `6956d1aecef450f945e6cd89503056029110ec1915c226f74e66303974231a1d` |
| test2 | `496ec52724a28ff121777b1356b0dacb410c812b9d386727494d813104ead59a` | `1f12bc210d0d237a841155eaf01d41f86673d2934523ae7c735c689c96cecf56` |
| test3 | `a80ab39623e709fbea6108d4bf845eb6d1de045a518404d8c68a8a5981cccf6c` | `bc0407568d0f76592d5687c60a8f95fb537f891cdc987abf08461b9aee4a0265` |

The public notebooks retain only five meaningful outputs, use environment
credential lookup and relative runtime paths, and contain no widget state,
raw traces, private excerpts, authorization headers, credentials, local file
URIs, or machine paths. The README showcase table is generated from these
verified manifests and uses absolute GitHub links so it renders correctly on
both GitHub and PyPI.

## Exact publication archives

`dist/` contains only these two artifacts:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `principia_ai-1.3.3-py3-none-any.whl` | 170,917 | `5414073952a4a26f5f5e8689f9b8268b05405b56505599750ac3e81359007cb7` |
| `principia_ai-1.3.3.tar.gz` | 317,781 | `78aa4c7173bcb6bf87a7b8fadc2868ed64a6ee25f4c258d2ecbcdc8e105680fb` |

Archive inspection confirmed package metadata version 1.3.3, Python 3.10+
compatibility, MIT license metadata, `principia` and `principia_retrieval`, both
`py.typed` markers, the CLI entry point, valid wheel RECORD hashes, a single
sdist root, and README identity across source, wheel metadata, and sdist. The
archive scanner found no credential, authorization header, real machine path,
cache, runtime workspace, duplicate member, or nested distribution.

## Publication receipt

The maintainer explicitly authorized GitHub and PyPI publication in this task.
No credential is written to this report.

- GitHub branch: `codex/principia-v1.3.3-framework`.
- Pre-receipt head: `1ad7fb6618b0ba199ae0bbc906dc4bd009069f34`.
- Pull request: <https://github.com/pzqpzq/Principia/pull/9>.
- Corrected pre-publication CI: run `29497057756`, with all nine jobs green
  across core/local Python 3.10-3.13 and package/archive verification.
- PyPI release: <https://pypi.org/project/principia-ai/1.3.3/>.
- PyPI verification: 2026-07-16 22:21 CST. The JSON API returned exactly the
  two non-yanked files, byte sizes, and SHA-256 digests recorded in the archive
  table above, with `requires_python` set to `>=3.10`.

This receipt commit must pass the same GitHub CI before PR #9 is merged. GitHub
assigns the final merge commit after that gate; it is therefore verified as a
post-merge public-endpoint check rather than predicted in this source report.
