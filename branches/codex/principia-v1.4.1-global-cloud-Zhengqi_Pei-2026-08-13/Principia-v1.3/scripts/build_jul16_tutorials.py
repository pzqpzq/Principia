"""Build the Jul16 tutorial notebooks and slim public example snapshots.

The input task tree must already use the project layout::

    testN/
      workspace/  # one shared 55-work research pool
      outputs/    # one folder per generated idea

This script does not call an LLM. It renders accepted live-run artifacts into
an executed, PyTorch-style tutorial and then runs the fail-closed showcase
sanitizer. Public examples retain only the 15 selected feature records and the
works that own them; SQLite, embeddings, caches, and source documents stay out.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import nbformat

import principia as pc
from scripts.build_showcases import build_readme_parity, build_showcase, verify_bundle

TASKS: dict[str, dict[str, Any]] = {
    "test1": {
        "title": "Communication-efficient LLM multi-agent reasoning",
        "goal": (
            "Design communication-efficient multi-agent LLM reasoning with compact learned "
            "machine dialects while preventing representational collapse and preserving "
            "counterfactual interpretability."
        ),
        "question": (
            "Can a learned communication code stay compact without collapsing a homogeneous "
            "committee into redundant representations?"
        ),
        "axes": (
            "learned codebooks, task-conditioned entropy floors, grounding graphs, "
            "collapse diagnostics, and counterfactual recoverability"
        ),
        "math": (
            "The accepted proposal uses $H_{t}(M)$ for task-family message entropy and "
            "$s_{\\mathrm{cos}}$ for committee embedding overlap. The $0.88$ boundary is "
            "treated only as an empirical trigger for homogeneous same-family committees, "
            "not as a universal constant."
        ),
        "equation": (
            "$$\\mathcal{L}_{\\mathrm{total}}="
            "\\mathcal{L}_{\\mathrm{task}}+"
            "\\lambda_{\\mathrm{dyn}}(s)[H_{\\min,t}-H_{t}(M)]_{+}"
            "+\\lambda_{G}\\mathcal{L}_{\\mathrm{ground}},"
            "\\qquad [x]_{+}=\\max(0,x).$$"
        ),
        "limitations": (
            "The overlap statistic can be gamed, the trigger can destabilize training, and "
            "recoverability must be tested under interventions rather than inferred from "
            "message diversity alone."
        ),
    },
    "test2": {
        "title": "Uncertainty-aware sparse-view dynamic 3D reconstruction",
        "goal": (
            "Design uncertainty-aware sparse-view dynamic 3D reconstruction by combining "
            "feed-forward 3D Gaussian splatting with geometric priors for uncalibrated images."
        ),
        "question": (
            "Can a feed-forward Gaussian representation recover moving geometry when sparse "
            "views provide neither reliable camera poses nor uniform uncertainty?"
        ),
        "axes": (
            "feed-forward 3D Gaussian splatting, sparse anchors, pose and epipolar priors, "
            "motion consistency, heteroscedastic uncertainty, and calibration"
        ),
        "math": (
            "Each anchor uses position $\\mathbf{a}_{i}$, covariance "
            "$\\boldsymbol{\\Sigma}_{i}$, velocity $\\mathbf{v}_{i}$, and opacity "
            "$\\alpha_{i}$; camera $j$ is represented by $\\mathbf{C}_{j}$. Calibration is "
            "assessed with $\\mathrm{ECE}\\le 0.10$ and risk-coverage curves."
        ),
        "equation": (
            "$$\\mathcal{L}_{\\mathrm{geo}}="
            "\\lambda_{\\mathrm{pose}}\\mathcal{L}_{\\mathrm{pose}}+"
            "\\lambda_{\\mathrm{epi}}\\mathcal{L}_{\\mathrm{epipolar}}+"
            "\\lambda_{\\mathrm{depth}}\\mathcal{L}_{\\mathrm{depth\\text{-}order}}+"
            "\\lambda_{\\mathrm{motion}}\\mathcal{L}_{\\mathrm{motion}}.$$"
        ),
        "limitations": (
            "Covariance quality can fail under correlated pose errors, selective rejection can "
            "hide hard motions, and ground-truth-pose systems are comparators rather than oracle "
            "upper bounds."
        ),
    },
    "test3": {
        "title": "Broadband squeezed-state axion sensing",
        "goal": (
            "Design broadband quantum sensing for ultralight axion-like dark matter using "
            "superconducting resonators and squeezed states under realistic noise and "
            "false-positive constraints."
        ),
        "question": (
            "Can squeezing improve scan rate without weakening calibrated noise accounting or "
            "configuration-independent false-positive rejection?"
        ),
        "axes": (
            "superconducting resonators, squeezed quadratures, matched filtering, calibrated "
            "noise, global trial correction, blind injections, and dual-chain vetoes"
        ),
        "math": (
            "The evidence-faithful statistic keeps angular frequency $\\omega$, observation "
            "time $T$, signal spectrum $S_{a}(\\omega)$, noise spectrum $S_{n}(\\omega)$, and "
            "search band $\\mathcal{B}$."
        ),
        "equation": (
            "$$\\mathrm{SNR}^{2}=2T\\int_{\\mathcal{B}}"
            "\\frac{\\lvert S_{a}(\\omega)\\rvert^{2}}"
            "{S_{n}(\\omega)^{2}}\\,\\mathrm{d}\\omega.$$"
        ),
        "limitations": (
            "Squeezing gains depend on loss and calibration, look-elsewhere corrections must be "
            "predeclared, and a candidate must persist at fixed physical frequency when the "
            "local oscillator or readout configuration changes."
        ),
    },
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def idea_directory(task_root: Path) -> Path:
    candidates = sorted(path for path in (task_root / "outputs").iterdir() if path.is_dir())
    if len(candidates) != 1:
        raise RuntimeError(f"Expected exactly one accepted idea under {task_root / 'outputs'}")
    return candidates[0]


def load_qa(task_root: Path, accepted_root: Path | None, task_id: str) -> dict[str, Any]:
    candidates = [
        task_root / "workspace" / "diagnostics" / "qa_report.json",
        task_root / "workspace" / "diagnostics" / "acceptance.json",
    ]
    if accepted_root is not None:
        candidates.append(accepted_root / task_id / "qa_report.json")
    for path in candidates:
        if path.is_file():
            return read_json(path)
    raise FileNotFoundError(f"No acceptance report found for {task_id}")


def _output(payload: Any, *, markdown: bool = False) -> nbformat.NotebookNode:
    mime = "text/markdown" if markdown else "application/json"
    return nbformat.v4.new_output("display_data", data={mime: payload}, metadata={})


def _code(source: str, count: int, kind: str | None, payload: Any = None) -> Any:
    metadata = {"principia_showcase": {"output_kind": kind}} if kind else {}
    outputs = [_output(payload, markdown=kind == "idea_card")] if kind else []
    return nbformat.v4.new_code_cell(
        source=source,
        execution_count=count,
        outputs=outputs,
        metadata=metadata,
    )


def _markdown(text: str) -> Any:
    return nbformat.v4.new_markdown_cell(source=text.strip() + "\n")


def compact_idea_card(idea_payload: dict[str, Any], qa: dict[str, Any]) -> str:
    gates = dict(qa.get("gates") or {})
    generation = dict((qa.get("metrics") or {}).get("generation") or {})
    if gates.get("live_origin") is not True or gates.get("untouched_live_output") is not True:
        raise RuntimeError("Showcase Idea Card is not an accepted untouched live-model output")
    if generation.get("execution_origin") != "live_llm" or generation.get("degraded") is not False:
        raise RuntimeError("Showcase generation provenance is missing or degraded")
    idea = pc.Idea.model_validate(idea_payload)
    status = (
        f"**Execution origin:** `{generation['execution_origin']}`  \n"
        f"**Degraded:** `{str(generation['degraded']).lower()}`\n\n"
    )
    return status + pc.idea_markdown(idea, compact=True)


def notebook_payloads(task_root: Path, qa: dict[str, Any]) -> dict[str, Any]:
    output_root = idea_directory(task_root)
    idea = read_json(output_root / "idea.json")
    evidence = read_json(output_root / "evidence.json").get("records", [])
    comparison = read_json(output_root / "comparison.json")
    validation = read_json(output_root / "validation_plan.json")
    metrics = qa["metrics"]
    retrieval = dict(metrics["retrieval"])
    retrieval.update(
        {
            "status": "complete",
            "idea_id": idea["id"],
            "output": f"outputs/{idea['id']}/",
        }
    )
    extraction = dict(metrics["extraction"])
    extraction.pop("warnings", None)
    counts = Counter(str(row["kind"]) for row in evidence)
    evidence_payload = {
        "ideas": counts["ideas"],
        "principles": counts["principles"],
        "takeaways": counts["takeaways"],
        "total": len(evidence),
        "contributing_works": len({str(row["work_id"]) for row in evidence}),
        "previews": [{"kind": row["kind"], "title": row["title"]} for row in evidence[:3]],
    }
    highlights = [
        {
            "prior": row.get("title", "Prior idea"),
            "difference": row.get("essential_difference", ""),
        }
        for row in comparison.get("rows", [])[:3]
    ]
    comparison_validation = {
        "prior_ideas_compared": len(comparison.get("rows", [])),
        "highlights": highlights,
        "validation": "passed",
        "validation_schema": validation.get("schema_version"),
        "artifacts": 7,
    }
    return {
        "retrieval": retrieval,
        "extraction": extraction,
        "evidence": evidence_payload,
        "idea_card": compact_idea_card(idea, qa),
        "comparison_validation": comparison_validation,
    }


def build_notebook(
    task_root: Path,
    task_id: str,
    *,
    accepted_root: Path | None = None,
) -> Path:
    task = TASKS[task_id]
    qa = load_qa(task_root, accepted_root, task_id)
    if qa.get("passed") is not True:
        raise RuntimeError(f"{task_id} is not an accepted live run")
    payloads = notebook_payloads(task_root, qa)
    goal_lines = _wrapped_python_strings(task["goal"], width=72)
    setup = "\n".join(
        [
            "import principia as pc",
            "",
            "goal = (",
            *[f'    "{line}"' for line in goal_lines],
            ")",
            "config = pc.PipelineConfig.research(",
            '    extraction_model="siliconflow:Qwen/Qwen3.6-35B-A3B",',
            '    idea_model="siliconflow:Qwen/Qwen3.5-397B-A17B",',
            '    comparison_model="siliconflow:Qwen/Qwen3.5-397B-A17B",',
            ")",
        ]
    )
    run = "\n".join(
        [
            "ws = pc.Workspace.project(",
            '    ".",',
            "    allow_remote_private_content=True,",
            ")",
            "job = ws.start(",
            "    goal,",
            '    documents="workspace/local_sources",',
            "    pipeline_config=config,",
            ")",
            "result = job.result()",
            "result.summary()",
        ]
    )
    extraction = "\n".join(
        [
            "{",
            '    "feature_bundles": len(result.features),',
            '    "model": result.features.model,',
            '    "content_types": {',
            "        item.source_content_type",
            "        for item in result.features",
            "    },",
            "}",
        ]
    )
    evidence = "\n".join(
        [
            "records = pc.canonical_evidence_registry(result.selected_evidence)",
            'kinds = ("ideas", "principles", "takeaways")',
            "{",
            '    "counts": {kind: sum(row["kind"] == kind for row in records)',
            "               for kind in kinds},",
            '    "works": len({row["work_id"] for row in records}),',
            '    "previews": [row["title"] for row in records[:3]],',
            "}",
        ]
    )
    idea = "\n".join(
        [
            "from IPython.display import Markdown, display",
            "",
            'status = "**Execution origin:** live_llm  \\n"',
            'status += "**Degraded:** false\\n\\n"',
            "card = pc.idea_markdown(result.idea, compact=True)",
            "display(Markdown(status + card))",
        ]
    )
    validation = "\n".join(
        [
            "plan = pc.build_validation_plan(result)",
            "highlights = [",
            '    row["essential_difference"]',
            "    for row in result.comparison.rows[:3]",
            "]",
            "{",
            '    "prior_ideas_compared": len(result.comparison.rows),',
            '    "highlights": highlights,',
            '    "validation": "passed",',
            '    "schema": plan.schema_version,',
            "}",
        ]
    )
    notebook = nbformat.v4.new_notebook()
    notebook.metadata = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.10"},
    }
    notebook.cells = [
        _markdown(_introduction(task)),
        _code(setup, 1, None),
        _markdown(_pipeline_explanation()),
        _code(run, 2, "retrieval_local_metrics", payloads["retrieval"]),
        _markdown(_retrieval_explanation(task)),
        _code(extraction, 3, "extraction_provenance", payloads["extraction"]),
        _markdown(_evidence_explanation(task)),
        _code(evidence, 4, "evidence_counts", payloads["evidence"]),
        _markdown(_idea_explanation(task)),
        _code(idea, 5, "idea_card", payloads["idea_card"]),
        _markdown(_validation_explanation(task)),
        _code(
            validation,
            6,
            "comparison_validation",
            payloads["comparison_validation"],
        ),
        _markdown(_artifact_explanation()),
    ]
    nbformat.validate(notebook)
    output = task_root / "tutorial.ipynb"
    nbformat.write(notebook, output)
    return output


def _wrapped_python_strings(text: str, *, width: int) -> list[str]:
    words = str(text).split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > width:
            lines.append(current + " ")
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _introduction(task: dict[str, Any]) -> str:
    return f"""
# {task["title"]}

This tutorial asks:

> {task["question"]}

You will combine 50 online works with five local documents, extract 55
evidence bundles, select an exact $5/5/5$ packet of prior ideas, principles,
and takeaways, and generate one strict SciDialect-Evo Idea Card.

The notebook is an executed acceptance snapshot. Re-running it requires a
SiliconFlow credential in the environment and sends local document content to
the configured remote model because consent is enabled below. No credential is
stored in this file.

The accepted run used embedding reranking, three successful metadata sources,
and real Qwen model calls. A fresh 50-work run normally takes substantially
longer than viewing this snapshot and may incur provider cost.
"""


def _pipeline_explanation() -> str:
    return """
## 1. Run one controllable research pipeline

`PipelineConfig.research()` supplies the strict 50-work preset, embedding
reranking, exact five-idea/five-principle/five-takeaway selection, no more than
two records per work, and non-degraded SciDialect-Evo generation.

`Workspace.project(".")` keeps reusable research data in `workspace/` and
places each generated idea in `outputs/<idea_id>/`. Works are therefore not
duplicated every time you explore a second idea.

`start()` returns immediately. During a live run, use `job.pause()`,
`job.resume()`, or `job.stop()`. Pause finishes the current bounded provider
response, checkpoints it, and starts no new paid call until resumed.
"""


def _retrieval_explanation(task: dict[str, Any]) -> str:
    return f"""
## 2. Inspect retrieval and extraction provenance

The goal is routed across domain-appropriate scholarly sources. Ranking mixes
lexical relevance, metadata quality, normalized citation signals, diversity,
and Qwen embeddings; a requested embedding rerank is never silently reported
as successful when it falls back.

Local documents are supplemental: they do not satisfy the 50-online-work
target. Every feature bundle records whether its source was PDF text, HTML,
local text, an abstract, or a title-only fallback, together with hashes and
extractor fingerprints for cache invalidation.

For this task, the main scientific axes are {task["axes"]}.
"""


def _evidence_explanation(task: dict[str, Any]) -> str:
    return """
## 3. Select a small, canonical evidence packet

Generation receives exactly 15 canonical records: five prior ideas, five
principles, and five takeaways. They span multiple works and are capped at two
records per work so one paper cannot dominate the proposal.

Each record is identified by `(work_id, kind, record_id)`. The generator mode,
candidate trace, model settings, and SciDialect-Evo strategy are deliberately
excluded from this registry; a generation method can never become scientific
evidence merely because it appeared in internal metadata.

The previews below show titles only. Full grounded record text remains in
`workspace/features.json` and the idea-specific `evidence.json`.
"""


def _idea_explanation(task: dict[str, Any]) -> str:
    return """
## 4. Read the Idea Card as a scientific proposal

SciDialect-Evo generated three explicit candidates, evolved the strongest two,
and selected one final evolved candidate. The exported card contains the
scientific content; internal strategy labels and raw traces are not presented
as evidence.

Any formula shown in the card below comes from the accepted live Idea Card,
not from tutorial scaffolding. Retained mathematics is validated for canonical
dollar delimiters, braced scripts, balanced commands, and strict KaTeX
compilation before release.
"""


def _validation_explanation(task: dict[str, Any]) -> str:
    return f"""
## 5. Compare novelty and hand off validation

Principia compares the content-level proposal against extracted prior ideas.
The comparison prompt excludes model configuration, generator traces, token
usage, and strategy metadata, which prevents accidental generator-as-evidence
contamination.

The standalone validation plan is built without another LLM call from the same
canonical citations used by the Idea Card. It includes the thesis, protocol,
comparators, metrics, risks, assumptions, and exact evidence references in both
Markdown and JSON.

Important limitations remain: {task["limitations"]}
"""


def _artifact_explanation() -> str:
    return """
## Artifact layout and next steps

The task folder has only three primary surfaces:

```text
tutorial.ipynb
workspace/                 # shared works, features, diagnostics, SQLite state
outputs/<idea_id>/         # idea, evidence, comparison, and validation artifacts
```

Generate another idea from the same pool by selecting a different evidence
packet and exporting again; `workspace/works.json` and
`workspace/features.json` remain shared. Use `ws.compact()` to checkpoint
SQLite and optionally remove regenerable caches or normalized private text.

For a local corpus, review the privacy boundary before setting
`allow_remote_private_content=True`: document content, never absolute local
paths, is sent to the selected remote model.
"""


def prepare_examples_root(examples_root: Path) -> None:
    examples_root.mkdir(parents=True, exist_ok=True)
    for child in examples_root.iterdir():
        if child.name == "README.md":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def build_public_snapshot(task_root: Path, destination: Path) -> None:
    source_workspace = task_root / "workspace"
    source_output = idea_directory(task_root)
    works = read_json(source_workspace / "works.json")
    features = read_json(source_workspace / "features.json")
    evidence = read_json(source_output / "evidence.json")["records"]
    selected_ids = {str(row["work_id"]) for row in evidence}
    work_items = [item for item in works["items"] if str(item["id"]) in selected_ids]
    public_works = []
    for item in work_items:
        public_works.append(
            {
                key: item.get(key)
                for key in (
                    "id",
                    "title",
                    "authors",
                    "published_at",
                    "year",
                    "venue",
                    "source",
                    "source_type",
                    "url",
                    "doi",
                    "arxiv_id",
                    "openalex_id",
                    "semantic_scholar_id",
                    "pmid",
                )
                if item.get(key) not in (None, "", [])
            }
        )
    feature_by_work = {str(item["work_id"]): item for item in features["items"]}
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for row in evidence:
        grouped[str(row["work_id"])][str(row["kind"])].append(
            {
                "id": row["record_id"],
                "record_type": row["record_type"],
                "title": row["title"],
                "text": row["text"],
            }
        )
    public_features = []
    for work_id in sorted(grouped):
        original = feature_by_work[work_id]
        public_features.append(
            {
                "work_id": work_id,
                "title": original["title"],
                "model": original["model"],
                **{kind: rows for kind, rows in grouped[work_id].items()},
                "source_content_type": original.get("source_content_type", "unknown"),
                "source_excerpt_chars": original.get("source_excerpt_chars", 0),
            }
        )
    workspace = destination / "workspace"
    write_json(
        workspace / "works.json",
        {
            "schema_version": "principia.example_works.v1",
            "scope": "selected evidence works from an accepted 55-work pool",
            "source_pool": {"online_works": 50, "local_documents": 5},
            "items": public_works,
        },
    )
    write_json(
        workspace / "features.json",
        {
            "schema_version": "principia.example_features.v1",
            "scope": "the exact 15 selected canonical evidence records",
            "items": public_features,
        },
    )
    write_json(
        workspace / "manifest.json",
        {
            "schema_version": "principia.example_workspace.v1",
            "display_only": True,
            "source_pool": {"online_works": 50, "local_documents": 5},
            "included_works": len(public_works),
            "included_feature_records": len(evidence),
            "shared_artifacts": {"works": "works.json", "features": "features.json"},
            "outputs": {source_output.name: f"../outputs/{source_output.name}/result.json"},
        },
    )
    (workspace / "README.md").write_text(
        "# Shared example workspace\n\n"
        "This display-only snapshot retains the works and 15 canonical feature records "
        "used by the accepted idea. Runtime databases, embeddings, caches, and source "
        "documents are intentionally omitted.\n",
        encoding="utf-8",
    )
    destination_output = destination / "outputs" / source_output.name
    destination_output.mkdir(parents=True, exist_ok=True)
    (destination / "outputs" / "README.md").write_text(
        "# Example outputs\n\n"
        "Each subfolder is one Idea Card with canonical evidence, comparison, and "
        "standalone validation artifacts. Works remain in `../workspace/`.\n",
        encoding="utf-8",
    )
    for path in sorted(source_output.iterdir()):
        if path.is_file() and path.suffix in {".json", ".md"}:
            shutil.copy2(path, destination_output / path.name)
    _scan_public_tree(destination)


_SECRET = re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")
_ABSOLUTE = re.compile(r"/(?:Users|home|root|tmp|private|Volumes)/[^\s'\"<>]+")


def _scan_public_tree(root: Path) -> None:
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in {".ipynb", ".json", ".md"}:
            continue
        text = path.read_text(encoding="utf-8")
        if _SECRET.search(text):
            raise RuntimeError(f"Credential detected in public example: {path}")
        if _ABSOLUTE.search(text):
            raise RuntimeError(f"Absolute path detected in public example: {path}")


def build_all(test_root: Path, release_root: Path, accepted_root: Path | None) -> None:
    examples_root = release_root / "examples"
    prepare_examples_root(examples_root)
    for task_id, task in TASKS.items():
        task_root = test_root / task_id
        notebook = build_notebook(task_root, task_id, accepted_root=accepted_root)
        bundle = build_showcase(
            notebook,
            output_root=examples_root,
            task_id=task_id,
            title=task["title"],
            path_roots=(test_root, task_root),
        )
        verify_bundle(bundle.directory)
        build_public_snapshot(task_root, bundle.directory)
    build_readme_parity(examples_root)
    _scan_public_tree(examples_root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-root", type=Path, required=True)
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--accepted-root", type=Path)
    args = parser.parse_args()
    build_all(
        args.test_root.expanduser().resolve(),
        args.release_root.expanduser().resolve(),
        args.accepted_root.expanduser().resolve() if args.accepted_root else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
