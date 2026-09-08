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


def test_cli_doctor_creates_canonical_working_directory(tmp_path: Path) -> None:
    root = tmp_path / "principia-project"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "principia.cli",
            "doctor",
            "--working-directory",
            str(root),
            "--json",
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    assert payload["workspace"]["layout"] == "project"
    assert payload["workspace"]["directories"]["local_data"] == "local_data"
    assert (root / "workspace" / ".principia" / "principia.sqlite").is_file()
    assert (root / "workspace" / "principles" / "manifest.json").is_file()
    assert (root / "local_data").is_dir()


def test_v14_product_cli_requires_an_explicit_storage_root() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "principia.cli", "doctor", "--json"],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2
    assert "requires --working-directory" in result.stderr


def test_cli_accepts_shared_package_library(tmp_path: Path) -> None:
    root = tmp_path / "working-directory"
    library = tmp_path / "principle-packages"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "principia.cli",
            "doctor",
            "--working-directory",
            str(root),
            "--package-library",
            str(library),
            "--json",
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    assert payload["cloud"]["shared_package_library"] is True
    assert (library / ".principia" / "registry.sqlite").is_file()


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
