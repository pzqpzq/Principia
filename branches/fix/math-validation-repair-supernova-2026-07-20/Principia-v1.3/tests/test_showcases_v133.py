from __future__ import annotations

import hashlib
import json
from pathlib import Path

import nbformat
import pytest

from scripts.build_showcases import (
    README_SHOWCASE_END,
    README_SHOWCASE_START,
    ShowcaseError,
    build_readme_parity,
    build_showcase,
    sanitize_notebook,
    sync_root_readme_showcases,
    verify_bundle,
    verify_notebook,
    verify_root_readme_showcases,
)
from scripts.build_showcases import (
    main as showcase_main,
)

SYNTHETIC_SECRET = "".join(("s", "k", "-", "synthetic-showcase-credential-123456"))


def _json_output(payload: object) -> nbformat.NotebookNode:
    return nbformat.v4.new_output(
        "display_data",
        data={"application/json": payload, "text/plain": repr(payload)},
        metadata={},
    )


def _markdown_output(payload: str) -> nbformat.NotebookNode:
    return nbformat.v4.new_output(
        "display_data",
        data={"text/markdown": payload, "text/plain": payload},
        metadata={},
    )


def _showcase_cell(
    kind: str,
    payload: object,
    *,
    execution_count: int,
    source: str = "display(summary)",
) -> nbformat.NotebookNode:
    return nbformat.v4.new_code_cell(
        source=source,
        execution_count=execution_count,
        outputs=[_json_output(payload)],
        metadata={"principia_showcase": {"output_kind": kind}},
    )


def _executed_notebook(local_root: Path) -> nbformat.NotebookNode:
    notebook = nbformat.v4.new_notebook()
    notebook.metadata["widgets"] = {
        "application/vnd.jupyter.widget-state+json": {"state": {"secret": SYNTHETIC_SECRET}}
    }
    notebook.cells = [
        nbformat.v4.new_markdown_cell(
            f"# Local acceptance run\n\nSource: {local_root}/local_sources\nKey: {SYNTHETIC_SECRET}"
        ),
        _showcase_cell(
            "retrieval_local_metrics",
            {
                "online_works": 50,
                "local_documents": 5,
                "embedding_rerank": "applied",
                "workspace": str(local_root / "workspace"),
            },
            execution_count=1,
            source=(
                "import json, os\n"
                f'API_KEY = "{SYNTHETIC_SECRET}"\n'
                f'workspace = "{local_root}/workspace"\n'
                "display(summary)"
            ),
        ),
        _showcase_cell(
            "extraction_provenance",
            {"feature_bundles": 55, "model": "Qwen/Qwen3.6-35B-A3B"},
            execution_count=2,
        ),
        _showcase_cell(
            "evidence_counts",
            {"ideas": 5, "principles": 5, "takeaways": 5, "total": 15},
            execution_count=3,
        ),
        _showcase_cell(
            "idea_card",
            {
                "title": "Adaptive communication with collapse monitors",
                "thesis": r"Gate compact messages with $\alpha + \beta$ stability.",
                "mode": "scidialect-evo",
                "execution_origin": "live_llm",
                "degraded": False,
            },
            execution_count=4,
        ),
        _showcase_cell(
            "comparison_highlights",
            {
                "prior_ideas_compared": 1,
                "highlights": [
                    "Connects bandwidth control to intervention-based interpretability."
                ],
            },
            execution_count=5,
        ),
        _showcase_cell(
            "validation_result",
            {"status": "passed", "artifacts": 5},
            execution_count=6,
        ),
        nbformat.v4.new_code_cell(
            source="result = run.result()",
            execution_count=7,
            outputs=[
                nbformat.v4.new_output(
                    "stream",
                    name="stdout",
                    text=f"raw private frame at {local_root}\n",
                )
            ],
        ),
    ]
    return notebook


def _write_source(path: Path, notebook: nbformat.NotebookNode) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    nbformat.write(notebook, path)


def _build_three_showcases(tmp_path: Path) -> Path:
    local_root = tmp_path / "local"
    source = local_root / "tutorial.ipynb"
    _write_source(source, _executed_notebook(local_root))
    output_root = tmp_path / "release" / "examples" / "showcases"
    for task_id, title in (
        ("test1", "Multi-agent reasoning"),
        ("test2", "Dynamic 3D reconstruction"),
        ("test3", "Broadband axion sensing"),
    ):
        build_showcase(
            source,
            output_root=output_root,
            task_id=task_id,
            title=title,
        )
    return output_root


def test_build_showcase_is_output_bearing_concise_and_secret_free(tmp_path: Path) -> None:
    local_root = tmp_path / "test1"
    source = local_root / "tutorial.ipynb"
    _write_source(source, _executed_notebook(local_root))

    bundle = build_showcase(
        source,
        output_root=tmp_path / "release" / "examples" / "showcases",
        task_id="test1",
        title="Communication-efficient multi-agent reasoning",
    )

    public_text = bundle.notebook.read_text(encoding="utf-8")
    assert SYNTHETIC_SECRET not in public_text
    assert str(local_root) not in public_text
    assert 'os.environ[\\"SILICONFLOW_API_KEY\\"]' in public_text
    assert "raw private frame" not in public_text
    assert "widget-state" not in public_text
    assert bundle.audit.code_cells == 7
    assert bundle.audit.retained_outputs == 6
    assert bundle.audit.code_lines <= 60
    assert bundle.audit.size_bytes <= 250 * 1024

    manifest = json.loads(bundle.manifest.read_text(encoding="utf-8"))
    row = manifest["readme_row"]
    assert row["online_works"] == 50
    assert row["local_documents"] == 5
    assert row["feature_bundles"] == 55
    assert row["evidence_records"] == 15
    assert row["mode"] == "scidialect-evo"
    assert row["validation"] == "passed"
    assert verify_bundle(bundle.directory) == bundle.audit

    parity_json, parity_markdown = build_readme_parity(bundle.directory.parent)
    parity = json.loads(parity_json.read_text(encoding="utf-8"))
    assert parity["rows"] == [row]
    assert "| 50 | 5 | 55 | 15 | scidialect-evo | passed |" in parity_markdown.read_text(
        encoding="utf-8"
    )


def test_sanitizer_fails_closed_on_authorization_header(tmp_path: Path) -> None:
    source = tmp_path / "tutorial.ipynb"
    notebook = _executed_notebook(tmp_path)
    synthetic_header = "".join(("Authorization: ", "synthetic-token-value", "\n"))
    notebook.cells[2].outputs = [
        nbformat.v4.new_output(
            "stream",
            name="stdout",
            text=synthetic_header,
        )
    ]
    _write_source(source, notebook)

    with pytest.raises(ShowcaseError, match="authorization header"):
        sanitize_notebook(source, task_id="test1", title="Unsafe run")


def test_sanitizer_rejects_mock_or_degraded_origin(tmp_path: Path) -> None:
    source = tmp_path / "tutorial.ipynb"
    notebook = _executed_notebook(tmp_path)
    notebook.cells[2].outputs = [
        _json_output({"feature_bundles": 55, "execution_origin": "mock_fixture"})
    ]
    _write_source(source, notebook)
    with pytest.raises(ShowcaseError, match="Mock or template"):
        sanitize_notebook(source, task_id="test1", title="Mock run")

    notebook.cells[2].outputs = [_json_output({"feature_bundles": 55, "degraded": True})]
    _write_source(source, notebook)
    with pytest.raises(ShowcaseError, match="degraded"):
        sanitize_notebook(source, task_id="test1", title="Degraded run")


def test_verify_rejects_incomplete_story_and_oversized_code_cell(tmp_path: Path) -> None:
    source = tmp_path / "tutorial.ipynb"
    notebook = _executed_notebook(tmp_path)
    _write_source(source, notebook)
    public = sanitize_notebook(source, task_id="test1", title="Valid run")
    public.cells[2].metadata = {}
    public.cells[2].outputs = []
    with pytest.raises(ShowcaseError, match="missing signals: extraction"):
        verify_notebook(public)

    public = sanitize_notebook(source, task_id="test1", title="Valid run")
    public.cells[1].source = "\n".join(f"value_{index} = {index}" for index in range(13))
    with pytest.raises(ShowcaseError, match="maximum is 12"):
        verify_notebook(public)


def test_verify_scans_metadata_and_bundle_checksums(tmp_path: Path) -> None:
    local_root = tmp_path / "test1"
    source = local_root / "tutorial.ipynb"
    _write_source(source, _executed_notebook(local_root))
    bundle = build_showcase(
        source,
        output_root=tmp_path / "release",
        task_id="test1",
        title="Checksum test",
    )

    notebook = nbformat.read(bundle.notebook, as_version=4)
    notebook.metadata["hidden"] = {"path": "/var/folders/private-file.txt"}
    with pytest.raises(ShowcaseError, match="absolute local path"):
        verify_notebook(notebook)

    bundle.markdown.write_text(
        bundle.markdown.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8"
    )
    with pytest.raises(ShowcaseError, match="Checksum mismatch"):
        verify_bundle(bundle.directory)


def test_verify_bundle_recomputes_manifest_outputs_and_readme_row(tmp_path: Path) -> None:
    local_root = tmp_path / "test1"
    source = local_root / "tutorial.ipynb"
    _write_source(source, _executed_notebook(local_root))
    bundle = build_showcase(
        source,
        output_root=tmp_path / "release",
        task_id="test1",
        title="Manifest parity test",
    )

    manifest = json.loads(bundle.manifest.read_text(encoding="utf-8"))
    manifest["readme_row"]["online_works"] = 49
    bundle.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    digest = hashlib.sha256(bundle.manifest.read_bytes()).hexdigest()
    checksum_lines = bundle.checksums.read_text(encoding="utf-8").splitlines()
    bundle.checksums.write_text(
        "\n".join(
            f"{digest}  showcase.json" if line.endswith("  showcase.json") else line
            for line in checksum_lines
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ShowcaseError, match="README row"):
        verify_bundle(bundle.directory)


def test_verify_requires_live_origin_and_passed_validation(tmp_path: Path) -> None:
    source = tmp_path / "tutorial.ipynb"
    notebook = _executed_notebook(tmp_path)
    notebook.cells[4].outputs = [
        _json_output(
            {
                "title": "Candidate",
                "thesis": "A grounded thesis.",
                "mode": "scidialect-evo",
                "degraded": False,
            }
        )
    ]
    _write_source(source, notebook)
    with pytest.raises(ShowcaseError, match="execution_origin"):
        sanitize_notebook(source, task_id="test1", title="Missing live origin")

    notebook = _executed_notebook(tmp_path)
    notebook.cells[6].outputs = [_json_output({"status": "failed", "artifacts": 5})]
    _write_source(source, notebook)
    with pytest.raises(ShowcaseError, match="must be passed"):
        sanitize_notebook(source, task_id="test1", title="Failed validation")


def test_plain_dict_output_is_cleaned_as_structured_json(tmp_path: Path) -> None:
    source = tmp_path / "tutorial.ipynb"
    notebook = _executed_notebook(tmp_path)
    payload = {
        "title": "Live candidate",
        "thesis": "A grounded thesis.",
        "mode": "scidialect-evo",
        "execution_origin": "live_llm",
        "degraded": False,
        "trace": {"private": "must be removed"},
        "warnings": ["must be removed"],
        "prompt": "must be removed",
    }
    notebook.cells[4].outputs = [
        nbformat.v4.new_output(
            "display_data",
            data={"text/plain": repr(payload)},
            metadata={},
        )
    ]
    _write_source(source, notebook)

    public = sanitize_notebook(source, task_id="test1", title="Structured output")
    output = public.cells[4].outputs[0]
    assert list(output.data) == ["application/json"]
    assert output.data["application/json"]["execution_origin"] == "live_llm"
    assert "trace" not in output.data["application/json"]
    assert "warnings" not in output.data["application/json"]
    assert "prompt" not in output.data["application/json"]


def test_markdown_idea_card_is_rendered_and_still_machine_verified(tmp_path: Path) -> None:
    source = tmp_path / "tutorial.ipynb"
    notebook = _executed_notebook(tmp_path)
    notebook.cells[4].outputs = [
        _markdown_output(
            "# Adaptive communication with collapse monitors\n\n"
            "**Thesis:** Gate messages with $R_{\\mathrm{cf}}$.  \n"
            "**Mode:** `scidialect-evo`  \n"
            "**Execution origin:** `live_llm`  \n"
            "**Degraded:** `false`\n"
        )
    ]
    _write_source(source, notebook)

    public = sanitize_notebook(source, task_id="test1", title="Rendered Idea Card")

    output = public.cells[4].outputs[0]
    assert list(output.data) == ["text/markdown"]
    assert "$R_{\\mathrm{cf}}$" in output.data["text/markdown"]
    assert verify_notebook(public).retained_outputs == 6


def test_root_readme_table_sync_is_verified_idempotent_and_relative(tmp_path: Path) -> None:
    output_root = _build_three_showcases(tmp_path)
    readme = tmp_path / "release" / "README.md"
    readme.write_text(
        "# Release\n\n## Live showcases\n\n"
        f"{README_SHOWCASE_START}\nstale table\n{README_SHOWCASE_END}\n\n"
        "## Install\n",
        encoding="utf-8",
    )

    assert sync_root_readme_showcases(readme, output_root) is True
    verify_root_readme_showcases(readme, output_root)
    assert sync_root_readme_showcases(readme, output_root) is False
    text = readme.read_text(encoding="utf-8")
    assert "# Release\n\n## Live showcases" in text
    assert "## Install\n" in text
    assert (
        "https://github.com/pzqpzq/Principia/blob/main/Principia-v1.3/"
        "examples/test1/tutorial.ipynb"
    ) in text
    assert "examples/test2/tutorial.ipynb" in text
    assert "examples/test3/tutorial.ipynb" in text
    assert text.count("| 50 | 5 | 55 | 15 | scidialect-evo | passed |") == 3

    readme.write_text(text.replace("| 50 | 5 |", "| 49 | 5 |", 1), encoding="utf-8")
    with pytest.raises(ShowcaseError, match="table is stale"):
        verify_root_readme_showcases(readme, output_root)


def test_root_readme_sync_fails_closed_before_writing(tmp_path: Path) -> None:
    local_root = tmp_path / "local"
    source = local_root / "tutorial.ipynb"
    _write_source(source, _executed_notebook(local_root))
    output_root = tmp_path / "showcases"
    build_showcase(
        source,
        output_root=output_root,
        task_id="test1",
        title="Only one completed showcase",
    )
    readme = tmp_path / "README.md"
    original = f"# Release\n\n{README_SHOWCASE_START}\nold\n{README_SHOWCASE_END}\n"
    readme.write_text(original, encoding="utf-8")

    with pytest.raises(ShowcaseError, match="missing test2, test3"):
        sync_root_readme_showcases(readme, output_root)
    assert readme.read_text(encoding="utf-8") == original

    complete_root = _build_three_showcases(tmp_path / "complete")
    readme.write_text("# Release\n", encoding="utf-8")
    with pytest.raises(ShowcaseError, match="exactly one showcase start marker"):
        sync_root_readme_showcases(readme, complete_root)
    assert readme.read_text(encoding="utf-8") == "# Release\n"


def test_root_readme_cli_update_and_check(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output_root = _build_three_showcases(tmp_path)
    readme = tmp_path / "release" / "README.md"
    readme.write_text(
        f"# Release\n\n{README_SHOWCASE_START}\nold\n{README_SHOWCASE_END}\n",
        encoding="utf-8",
    )

    assert (
        showcase_main(
            ["readme", str(output_root), "--readme", str(readme)]
        )
        == 0
    )
    updated = json.loads(capsys.readouterr().out)
    assert updated["changed"] is True
    assert (
        showcase_main(
            ["readme", str(output_root), "--readme", str(readme), "--check"]
        )
        == 0
    )
    checked = json.loads(capsys.readouterr().out)
    assert checked["status"] == "in_sync"
