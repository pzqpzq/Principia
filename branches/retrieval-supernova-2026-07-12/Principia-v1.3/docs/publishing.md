# Publishing Principia V1.3

## Package Names

The Python import package is:

```python
import principia
```

The initial PyPI distribution is:

```bash
pip install principia-ai
```

The `principia` distribution name is currently occupied on PyPI. Treat `pip install principia` as unavailable until ownership is transferred or another formal decision is made. If the distribution name changes later, only package metadata changes; the import path remains `principia`.

## Repository Hygiene

Before pushing to GitHub:

```bash
find . -name .DS_Store -delete
find . \( -name __pycache__ -o -name .pytest_cache -o -name .mypy_cache -o -name .ruff_cache \) -prune -exec rm -rf {} +
```

Confirm the source tree has no local runtime artifacts:

```bash
find . -maxdepth 4 \( -name ".principia" -o -name "principia_outputs" -o -name ".venv" -o -name "principia_project" \) -print
```

The official notebook in `examples/` must remain release-clean:

```bash
python - <<'PY'
import json, re
from pathlib import Path

path = Path("examples/principia_v13_tutorial.ipynb")
nb = json.loads(path.read_text())
source = "\n".join("".join(cell.get("source", [])) for cell in nb["cells"])
assert "YOUR_SILICONFLOW_API_KEY" in source
assert not re.search(r"sk-[A-Za-z0-9_-]{16,}", source)
assert "/Users/" not in source
assert "test-project-1" not in source
assert sum(len(cell.get("outputs", [])) for cell in nb["cells"]) == 0
assert all(cell.get("execution_count") is None for cell in nb["cells"] if cell["cell_type"] == "code")
PY
```

## QA

Run the full local gate:

```bash
python -m pip install -e ".[dev]"
python -m ruff check src tests
python -m mypy src/principia
python -m pytest -q
```

The standard test suite is deterministic and uses mocked LLM calls. For a manual release smoke, open `examples/principia_v13_tutorial.ipynb`, insert a real API key in your local copy, run the staged cells, and inspect `principia_project/principia_outputs/latest/`.

## Build

```bash
rm -rf dist build src/principia_ai.egg-info
python -m build --no-isolation
python -m twine check dist/*
```

Expected artifacts:

```text
dist/principia_ai-1.3.2-py3-none-any.whl
dist/principia_ai-1.3.2.tar.gz
```

## Clean Install Smoke

```bash
python -m venv /tmp/principia-v13-smoke
/tmp/principia-v13-smoke/bin/python -m pip install --upgrade pip
/tmp/principia-v13-smoke/bin/python -m pip install dist/principia_ai-1.3.2-py3-none-any.whl
/tmp/principia-v13-smoke/bin/python -c "import principia as pc; print(pc.__version__)"
/tmp/principia-v13-smoke/bin/principia --workspace /tmp/principia-v13-ws status
```

If the local Python installation has certificate issues, add trusted hosts for the smoke install only:

```bash
/tmp/principia-v13-smoke/bin/python -m pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org dist/principia_ai-1.3.2-py3-none-any.whl
```

## Upload To PyPI

Use TestPyPI first when validating credentials:

```bash
python -m twine upload --repository testpypi dist/*
```

Then publish to PyPI:

```bash
python -m twine upload dist/*
```

After upload:

```bash
python -m venv /tmp/principia-v13-pypi
/tmp/principia-v13-pypi/bin/python -m pip install principia-ai
/tmp/principia-v13-pypi/bin/python -c "import principia as pc; print(pc.__version__)"
```
