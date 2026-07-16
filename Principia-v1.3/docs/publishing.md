# Publishing Principia v1.3.3

This document is a maintainer checklist. It prepares and verifies release
artifacts; it does not authorize a GitHub push, GitHub release, or PyPI upload.

## Release provenance

The v1.3.3 framework release must be based on upstream `main` commit
`11a03027855de9e25951cc012fd03730cf4a4ab7`, which includes merged PR #8. The
integration path is:

```text
pzqpzq/Principia@11a0302
  -> repository subtree Principia-v1.3/
  -> local v1.3.3 framework release directory
  -> verified v1.3.3 source/wheel/sdist
  -> maintainer-reviewed Principia-v1.3/ update
  -> GitHub and PyPI (separate authorized actions)
```

Do not seed the release from a v1.0 checkout or from a pre-PR v1.3.2 desktop
copy. Keep the source commit and this integration path in the release QA report.

## Distribution and licenses

The PyPI distribution is `principia-ai`; it installs both import packages:

```python
import principia
import principia_retrieval
```

The name `principia` is occupied on PyPI, so do not document
`pip install principia` as an installation route.

License scope must remain explicit:

- the upstream repository-root license is Apache-2.0 and governs the material
  covered by that root license;
- the `Principia-v1.3` framework subtree has its own MIT `LICENSE`;
- the `principia-ai` package metadata and v1.3.3 framework distributions must
  continue to declare and include the MIT license.

Do not replace the framework `LICENSE` with the repository-root license. Verify
both the wheel metadata and sdist contents before publication.

## Source and provider responsibilities

Principia retrieves public metadata from arXiv, OpenAlex, Crossref, Semantic
Scholar, and, when routed for biomedical/life-science goals, Europe PMC. Before
release, review [retrieval.md](retrieval.md) and confirm that source attribution,
rate limits, API etiquette, and provider terms links are current. Principia
stores source attribution and identifiers; it does not transfer ownership of
source records or papers.

OpenAlex now uses free API keys instead of the retired `mailto` polite pool.
For an OpenAlex release smoke test, set `OPENALEX_API_KEY` only in the process
environment. Confirm that the key is absent from source diagnostics, source
JSON, logs, notebooks, and both distribution archives.

SiliconFlow and other LLM/embedding providers are optional user-configured
services. Never put a maintainer or test API key in a source release, wheel,
sdist, README, documentation, source JSON, or upload-ready notebook.

Private-corpus extraction sends normalized document content to the configured
remote provider only after explicit consent. Release QA must confirm that
absolute source paths stay in hidden SQLite state, original private files are
not copied, and no private excerpt or sentinel appears in a shareable artifact.

## Repository hygiene

Run from the framework release root:

```bash
find . -name .DS_Store -delete
find . \( -name __pycache__ -o -name .pytest_cache -o -name .mypy_cache -o -name .ruff_cache \) -prune -exec rm -rf {} +
find . -maxdepth 5 \( -name .principia -o -name principia_outputs -o -name .venv -o -name principia_project \) -print
```

The final command must not identify a runtime workspace inside release content.

Check for likely credentials and machine-specific paths. Investigate every hit;
placeholders and documentation examples are allowed, real credentials are not.

```bash
rg -n 'sk-[A-Za-z0-9_-]{16,}|/Users/|/home/|Authorization: Bearer' \
  --glob '!dist/**' --glob '!build/**' .
```

## Upload-ready notebook gate

The release contains exactly `examples/test1`, `examples/test2`, and
`examples/test3`. Each is a display-only projection of its corresponding Jul16
acceptance project and has this public shape:

```text
testN/
  tutorial.ipynb
  workspace/
    README.md
    works.json
    features.json
    manifest.json
  outputs/
    README.md
    <idea_id>/
      idea.md
      idea.json
      evidence.json
      comparison.json
      result.json
      validation_plan.md
      validation_plan.json
```

The projection may retain only the works and feature records needed to explain
the selected evidence. It must not contain SQLite state, embeddings, caches,
provider responses, private source files, credentials, raw prompts, internal
traces, or absolute paths. `result.json` must point relatively to the shared
workspace instead of embedding another copy of the works pool.

Each notebook should use short, readable code cells and thorough Markdown
explanations. Retain a small set of curated outputs covering retrieval and
ingestion counts, extraction provenance, exact evidence counts, the compact
Idea Card, comparison highlights, and validation status. Remove full QA
dictionaries, warning streams, transient progress frames, private excerpts,
and widget state.

Scan the complete notebook JSON—not source cells alone:

```bash
python - <<'PY'
import json
import re
from pathlib import Path

secret = re.compile(r"(?:sk-|Bearer\s+)[A-Za-z0-9._-]{16,}", re.I)
local_path = re.compile(r"(?:/Users/[^/\s]+|/home/[^/\s]+|file://)", re.I)

for path in sorted(Path("examples").rglob("*.ipynb")):
    notebook = json.loads(path.read_text(encoding="utf-8"))
    payload = json.dumps(notebook, ensure_ascii=False)
    assert not secret.search(payload), path
    assert not local_path.search(payload), path
    assert "Authorization" not in payload, path
    assert "LOCAL_ONLY_DO_NOT_UPLOAD" not in payload, path

    if re.search(r"examples/test[123]/tutorial\.ipynb$", path.as_posix()):
        code = [cell for cell in notebook["cells"] if cell.get("cell_type") == "code"]
        assert all(";" not in "".join(cell.get("source", [])) for cell in code), path
PY
```

For each task, verify that workspace counts agree with the retained records,
every evidence reference resolves to exactly one feature record, every
`result.json` link resolves within the example, and the Markdown/JSON validation
plans describe the same idea. Compile all retained formulas with strict KaTeX;
subscripts and superscripts must use explicit braces. The full executed Jul16
test projects remain outside the source distribution.

## Static and regression QA

Install the development dependencies and run the deterministic gate:

```bash
python -m pip install -e ".[dev,local,notebook]"
python -m ruff check src tests scripts
python -m mypy src/principia src/principia_retrieval
python -m pytest -q
```

The regression suite must cover source retries/partial outages, strict target
top-up, source diagnostics, cross-domain query planning, deterministic ranking,
visible embedding fallback, repeated-search idempotency, duplicate identity,
cross-domain extraction, extractor-cache invalidation, local parser/MIME and
corruption handling, symlink/size limits, private-content consent, chunk resume,
prompt injection, no-path leakage, live-origin/no-template behavior, canonical
evidence hydration, generator contamination, idea history, exact evidence
selection, safe pause/resume/stop, strict math, curated example authenticity,
portable exports, and JSON/Markdown validation-plan parity.

Verify Python 3.10, 3.12, and 3.13 locally when those interpreters are
available:

```bash
qa_root="$(mktemp -d)"
for py in python3.10 python3.12 python3.13; do
  env_dir="${qa_root}/principia-v133-${py}"
  "$py" -m venv "$env_dir"
  "$env_dir/bin/python" -m pip install -e ".[dev,local,notebook]"
  "$env_dir/bin/python" -m pytest -q
done
```

CI must run the same suite on Python 3.10, 3.11, 3.12, and 3.13. A local machine
without one interpreter does not replace the missing CI matrix job.

## Live acceptance evidence

Before publication, record the three same-day live acceptance runs in the
release QA report. Each run must document:

- exactly 50 unique public works plus five accepted local documents and 55
  completed extraction bundles;
- applied `Qwen/Qwen3-Embedding-4B` reranking with no fallback;
- at least three successful metadata sources and no duplicate identities;
- top-20 relevance at least 85%, top-50 relevance at least 75%, no more than
  five out-of-scope works, and fresh-run Jaccard@20 at least 0.70;
- an exact evidence packet of five ideas, five principles, and five takeaways,
  from 8-15 works with at most two records per work, including at least three
  records from at least two local documents;
- `Qwen/Qwen3.6-35B-A3B` extraction and
  `Qwen/Qwen3.5-397B-A17B` non-degraded `scidialect-evo` generation;
- canonical local and public citations, nonempty prior-idea comparison, the
  shared workspace manifest, all seven per-idea artifacts, and strict
  LaTeX/KaTeX validity;
- no template origin, canned fallback phrase, generator-as-evidence reference,
  blank canonical evidence field, duplicate identity, private path, or secret;
- call/token usage, warnings, artifact checksums, and any selectively rerun
  invalidated stage.

Do not describe a failed gate as passing. Refine the affected code/query/prompt
and rerun only the invalidated stage.

## Build

Remove stale v1.3.2 distributions and build only v1.3.3:

```bash
rm -rf dist build src/principia_ai.egg-info
python -m build --no-isolation
python -m twine check dist/*
find dist -maxdepth 1 -type f -print | sort
```

The only distribution files should be:

```text
dist/principia_ai-1.3.3-py3-none-any.whl
dist/principia_ai-1.3.3.tar.gz
```

Inspect wheel/sdist contents and metadata:

```bash
unzip -l dist/principia_ai-1.3.3-py3-none-any.whl
tar -tzf dist/principia_ai-1.3.3.tar.gz
unzip -p dist/principia_ai-1.3.3-py3-none-any.whl \
  principia_ai-1.3.3.dist-info/METADATA | sed -n '1,80p'
```

Confirm that the wheel contains:

```text
principia/
principia/py.typed
principia_retrieval/
principia_retrieval/py.typed
principia_ai-1.3.3.dist-info/licenses/LICENSE
```

Record SHA-256 hashes in the release QA report:

```bash
shasum -a 256 dist/principia_ai-1.3.3-py3-none-any.whl \
  dist/principia_ai-1.3.3.tar.gz
```

## Installed-wheel smoke

Test the artifact, not the editable source tree:

```bash
wheel_root="$(mktemp -d)"
python3.12 -m venv "$wheel_root/venv"
wheel_python="$wheel_root/venv/bin/python"
"$wheel_python" -m pip install --upgrade pip
"$wheel_python" -m pip install \
  dist/principia_ai-1.3.3-py3-none-any.whl
"$wheel_python" - <<'PY'
import importlib.resources
import principia
import principia_retrieval

assert principia.__version__ == "1.3.3"
assert importlib.resources.files("principia").joinpath("py.typed").is_file()
assert importlib.resources.files("principia_retrieval").joinpath("py.typed").is_file()
print(principia.__version__)
PY
"$wheel_root/venv/bin/principia" \
  --workspace "$wheel_root/workspace" status
```

Create a second clean environment for the optional local-document parsers:

```bash
python3.12 -m venv "$wheel_root/local-venv"
"$wheel_root/local-venv/bin/python" -m pip install \
  "principia-ai[local] @ file://${PWD}/dist/principia_ai-1.3.3-py3-none-any.whl"
"$wheel_root/local-venv/bin/python" - <<'PY'
import docx
import openpyxl
import pptx
import principia

assert principia.__version__ == "1.3.3"
assert principia.LocalCorpusConfig().max_files == 500
PY
```

Repeat both core and `[local]` smoke checks on Python 3.10 and 3.13. Ensure the
working directory is outside the release source tree so imports cannot
accidentally resolve to `src/`.

## Maintainer publication steps

Only after review and explicit authorization:

1. integrate the verified release files into the upstream `Principia-v1.3/`
   subtree;
2. rerun static, wheel, and clean-install gates from the integration commit;
3. push/open the intended GitHub change and wait for the Python 3.10-3.13 CI
   matrix;
4. upload to TestPyPI and verify installation;
5. publish the same checksummed artifacts to PyPI;
6. create the GitHub release/tag and attach the release QA report.

Suggested TestPyPI verification commands:

```bash
python -m twine upload --repository testpypi dist/*
testpypi_root="$(mktemp -d)"
python -m venv "$testpypi_root/venv"
"$testpypi_root/venv/bin/python" -m pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ principia-ai==1.3.3
"$testpypi_root/venv/bin/python" -c \
  "import principia, principia_retrieval; print(principia.__version__)"
```

Production upload remains a separate action:

```bash
python -m twine upload dist/*
```

Never rebuild between TestPyPI and production upload; publish the exact
previously verified, checksummed artifacts.
