from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_cli_status(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "principia.cli",
            "--workspace",
            str(tmp_path),
            "--mock-llm",
            "status",
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        text=True,
        capture_output=True,
        check=True,
    )
    assert '"works": 0' in result.stdout


def test_release_files_exist() -> None:
    assert (ROOT / "LICENSE").exists()
    assert (ROOT / ".gitignore").exists()
    assert (ROOT / "examples" / "README.md").exists()
    assert (ROOT / "src" / "principia" / "py.typed").exists()


def test_official_tutorial_is_release_clean() -> None:
    path = ROOT / "examples" / "principia_v13_tutorial.ipynb"
    notebook = json.loads(path.read_text())
    all_source = "\n".join("".join(cell.get("source", [])) for cell in notebook["cells"])
    code_source = "\n".join(
        "".join(cell.get("source", [])) for cell in notebook["cells"] if cell.get("cell_type") == "code"
    )

    assert "YOUR_SILICONFLOW_API_KEY" in all_source
    assert not re.search(r"sk-[A-Za-z0-9_-]{16,}", all_source)
    assert "/Users/" not in all_source
    assert "test-project-1" not in all_source
    assert "REPO_ROOT" not in all_source
    assert "ws.run(" not in all_source
    assert "target_count=50" in all_source
    assert "EXTRACT_COUNT = 20" in all_source
    assert 'mode="calculus"' in all_source
    assert 'mode="scidialect-evo"' not in all_source
    assert "feature_ids=[" not in code_source
    assert sum(len(cell.get("outputs", [])) for cell in notebook["cells"]) == 0
    assert all(cell.get("execution_count") is None for cell in notebook["cells"] if cell["cell_type"] == "code")
