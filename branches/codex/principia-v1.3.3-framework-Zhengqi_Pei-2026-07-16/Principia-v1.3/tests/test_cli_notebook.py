from __future__ import annotations

import ast
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
    assert (ROOT / "src" / "principia_retrieval" / "py.typed").exists()


def test_official_tutorials_are_release_clean_and_parseable() -> None:
    paths = [
        ROOT / "examples" / task / "tutorial.ipynb"
        for task in ("test1", "test2", "test3")
    ]
    notebook_sources: list[str] = []
    for path in paths:
        notebook = json.loads(path.read_text(encoding="utf-8"))
        all_source = "\n".join("".join(cell.get("source", [])) for cell in notebook["cells"])
        notebook_sources.append(all_source)
        code_cells = [
            "".join(cell.get("source", []))
            for cell in notebook["cells"]
            if cell.get("cell_type") == "code"
        ]

        assert notebook["nbformat"] == 4
        assert not re.search(r"sk-[A-Za-z0-9_-]{16,}", all_source)
        assert "/Users/" not in all_source
        assert "/home/" not in all_source
        assert "file://" not in all_source
        assert 4 <= sum(len(cell.get("outputs", [])) for cell in notebook["cells"]) <= 7
        assert len(notebook["cells"]) <= 13
        assert sum(len(source.splitlines()) for source in code_cells) <= 60
        for source in code_cells:
            ast.parse(source, filename=path.name)

    for source in notebook_sources:
        assert "PipelineConfig.research" in source
        assert "Qwen/Qwen3.6-35B-A3B" in source
        assert "Qwen/Qwen3.5-397B-A17B" in source
        assert "Workspace.project" in source
        assert "job.result()" in source
        assert "selected_evidence" in source
