"""Fail-closed KaTeX QA for release Markdown, JSON, and notebooks.

This checker finds dollar-delimited mathematics that will be visible in a
release artifact and compiles every expression with KaTeX ``strict="error"``.
Markdown code fences and inline code are intentionally excluded because they
are examples, not rendered mathematics.  Code-cell source is likewise not a
retained notebook output.

KaTeX must be installed outside the repository and supplied explicitly::

    python scripts/check_release_math.py README.md docs examples \
      --node /path/to/node \
      --katex-module $TMPDIR/principia-katex/node_modules/katex

The explicit module path keeps release QA independent from global Node state
and prevents ``node_modules`` from being vendored into the distribution.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from principia.math import MathValidationError, normalize_latex_formula

SCHEMA_VERSION = "principia.release_math_qa.v1"
SUPPORTED_SUFFIXES = frozenset({".ipynb", ".json", ".markdown", ".md"})
IGNORED_DIRECTORY_NAMES = frozenset(
    {".git", ".ipynb_checkpoints", ".mypy_cache", ".pytest_cache", ".ruff_cache"}
)


class ReleaseMathError(RuntimeError):
    """Raised when release mathematics cannot be proved valid."""


@dataclass(frozen=True)
class MathOccurrence:
    """One visible, dollar-delimited mathematical expression."""

    path: Path
    location: str
    line: int
    column: int
    expression: str
    display: bool

    @property
    def expression_sha256(self) -> str:
        return hashlib.sha256(self.expression.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MathCheckSummary:
    """Serializable summary of one complete release-math audit."""

    files_scanned: int
    spans_compiled: int
    markdown_files: int
    json_files: int
    notebook_files: int


_NODE_DRIVER = r"""
const fs = require("fs");

function fail(message) {
  process.stderr.write(message + "\n");
  process.exit(2);
}

const modulePath = process.env.PRINCIPIA_KATEX_MODULE;
if (!modulePath) fail("PRINCIPIA_KATEX_MODULE is required");

let katex;
try {
  katex = require(modulePath);
} catch (error) {
  fail(`Cannot load KaTeX from the explicit module path: ${error.message}`);
}

let payload;
try {
  payload = JSON.parse(fs.readFileSync(0, "utf8"));
} catch (error) {
  fail(`Cannot parse checker input: ${error.message}`);
}

const results = payload.map((item) => {
  try {
    katex.renderToString(item.expression, {
      displayMode: Boolean(item.display),
      throwOnError: true,
      strict: "error",
      trust: false,
      maxExpand: 1000,
      maxSize: 50,
      output: "htmlAndMathml",
    });
    return {ok: true};
  } catch (error) {
    return {ok: false, error: String(error && error.message ? error.message : error)};
  }
});

process.stdout.write(JSON.stringify(results));
"""


def _is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return bool(backslashes % 2)


def _mask_range(mask: list[bool], start: int, end: int) -> None:
    for index in range(start, end):
        mask[index] = True


def _markdown_code_mask(text: str) -> list[bool]:
    """Return positions belonging to Markdown code or HTML comments."""

    mask = [False] * len(text)
    offset = 0
    fence_character = ""
    fence_length = 0
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        leading = len(body) - len(body.lstrip(" "))
        candidate = body[leading:] if leading <= 3 else ""
        match = re.match(r"(`{3,}|~{3,})(.*)$", candidate)
        if fence_character:
            _mask_range(mask, offset, offset + len(line))
            if match and match.group(1)[0] == fence_character:
                marker = match.group(1)
                trailer = match.group(2)
                if len(marker) >= fence_length and not trailer.strip():
                    fence_character = ""
                    fence_length = 0
        elif match:
            marker = match.group(1)
            fence_character = marker[0]
            fence_length = len(marker)
            _mask_range(mask, offset, offset + len(line))
        offset += len(line)

    comment_start = 0
    while True:
        start = text.find("<!--", comment_start)
        if start < 0:
            break
        end = text.find("-->", start + 4)
        if end < 0:
            _mask_range(mask, start, len(text))
            break
        _mask_range(mask, start, end + 3)
        comment_start = end + 3

    index = 0
    while index < len(text):
        if mask[index] or text[index] != "`" or _is_escaped(text, index):
            index += 1
            continue
        run_length = 1
        while index + run_length < len(text) and text[index + run_length] == "`":
            run_length += 1
        marker = "`" * run_length
        end = text.find(marker, index + run_length)
        if end < 0:
            index += run_length
            continue
        _mask_range(mask, index, end + run_length)
        index = end + run_length
    return mask


def _line_and_column(text: str, index: int) -> tuple[int, int]:
    line = text.count("\n", 0, index) + 1
    previous_newline = text.rfind("\n", 0, index)
    return line, index - previous_newline


def extract_math_spans(
    text: str,
    *,
    path: Path,
    location: str,
    markdown: bool,
) -> list[MathOccurrence]:
    """Extract strict ``$...$`` and ``$$...$$`` spans from visible text."""

    mask = _markdown_code_mask(text) if markdown else [False] * len(text)
    visible = "".join(
        " " if hidden and char != "\n" else char for char, hidden in zip(text, mask, strict=True)
    )
    unsupported = re.search(r"(?<!\\)\\[([]", visible)
    if unsupported:
        line, column = _line_and_column(text, unsupported.start())
        raise ReleaseMathError(
            f"{path}:{line}:{column} [{location}]: use $...$ or $$...$$, "
            "not \\( ... \\) or \\[ ... \\]."
        )

    occurrences: list[MathOccurrence] = []
    index = 0
    while index < len(text):
        if mask[index] or text[index] != "$" or _is_escaped(text, index):
            index += 1
            continue
        display = index + 1 < len(text) and not mask[index + 1] and text[index + 1] == "$"
        delimiter_length = 2 if display else 1
        content_start = index + delimiter_length
        cursor = content_start
        closing = -1
        while cursor < len(text):
            if mask[cursor] or text[cursor] != "$" or _is_escaped(text, cursor):
                cursor += 1
                continue
            run_length = 1
            while cursor + run_length < len(text) and text[cursor + run_length] == "$":
                run_length += 1
            if run_length == delimiter_length:
                closing = cursor
                break
            line, column = _line_and_column(text, cursor)
            raise ReleaseMathError(
                f"{path}:{line}:{column} [{location}]: nested or mismatched dollar delimiter."
            )
        if closing < 0:
            line, column = _line_and_column(text, index)
            raise ReleaseMathError(
                f"{path}:{line}:{column} [{location}]: unbalanced dollar delimiter."
            )
        expression = text[content_start:closing].strip()
        line, column = _line_and_column(text, index)
        if not expression:
            raise ReleaseMathError(f"{path}:{line}:{column} [{location}]: empty mathematical span.")
        if "==" in expression:
            raise ReleaseMathError(
                f"{path}:{line}:{column} [{location}]: use = for equality, not ==."
            )
        compact_expression = " ".join(expression.split())
        try:
            canonical_span = normalize_latex_formula(compact_expression, display=display)
        except MathValidationError as exc:
            raise ReleaseMathError(
                f"{path}:{line}:{column} [{location}]: {exc}."
            ) from exc
        delimiter = "$$" if display else "$"
        canonical_expression = canonical_span[len(delimiter) : -len(delimiter)]
        if canonical_expression != compact_expression:
            raise ReleaseMathError(
                f"{path}:{line}:{column} [{location}]: non-canonical LaTeX; "
                f"use {canonical_expression!r}."
            )
        unsafe_controls = [char for char in expression if ord(char) < 32 and char not in "\t\r\n"]
        if unsafe_controls or "\x7f" in expression:
            raise ReleaseMathError(
                f"{path}:{line}:{column} [{location}]: mathematical span contains a control character."
            )
        occurrences.append(
            MathOccurrence(
                path=path,
                location=location,
                line=line,
                column=column,
                expression=compact_expression,
                display=display,
            )
        )
        index = closing + delimiter_length
    return occurrences


def _scan_json_value(value: Any, *, path: Path, location: str) -> list[MathOccurrence]:
    occurrences: list[MathOccurrence] = []
    if isinstance(value, str):
        occurrences.extend(extract_math_spans(value, path=path, location=location, markdown=False))
    elif isinstance(value, Mapping):
        for key, child in value.items():
            occurrences.extend(_scan_json_value(child, path=path, location=f"{location}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            occurrences.extend(_scan_json_value(child, path=path, location=f"{location}[{index}]"))
    return occurrences


def extract_from_markdown(path: Path) -> list[MathOccurrence]:
    return extract_math_spans(
        path.read_text(encoding="utf-8"), path=path, location="markdown", markdown=True
    )


def extract_from_json(path: Path) -> list[MathOccurrence]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseMathError(f"Cannot parse JSON release artifact {path}: {exc}") from exc
    return _scan_json_value(payload, path=path, location="$")


def _as_text(value: Any) -> str:
    if isinstance(value, list):
        return "".join(str(part) for part in value)
    return str(value)


def extract_from_notebook(path: Path) -> list[MathOccurrence]:
    try:
        notebook = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseMathError(f"Cannot parse notebook {path}: {exc}") from exc
    cells = notebook.get("cells")
    if not isinstance(cells, list):
        raise ReleaseMathError(f"Notebook {path} has no valid cells array.")

    occurrences: list[MathOccurrence] = []
    for cell_index, cell in enumerate(cells):
        if not isinstance(cell, Mapping):
            raise ReleaseMathError(f"Notebook {path} cell {cell_index} is not an object.")
        cell_type = cell.get("cell_type")
        if cell_type in {"markdown", "raw"}:
            occurrences.extend(
                extract_math_spans(
                    _as_text(cell.get("source", "")),
                    path=path,
                    location=f"cells[{cell_index}].source",
                    markdown=cell_type == "markdown",
                )
            )
        outputs = cell.get("outputs", [])
        if not isinstance(outputs, list):
            raise ReleaseMathError(f"Notebook {path} cell {cell_index} has invalid outputs.")
        for output_index, output in enumerate(outputs):
            if not isinstance(output, Mapping):
                raise ReleaseMathError(
                    f"Notebook {path} cell {cell_index} output {output_index} is not an object."
                )
            base = f"cells[{cell_index}].outputs[{output_index}]"
            if output.get("output_type") == "stream":
                occurrences.extend(
                    extract_math_spans(
                        _as_text(output.get("text", "")),
                        path=path,
                        location=f"{base}.text",
                        markdown=False,
                    )
                )
            data = output.get("data", {})
            if not isinstance(data, Mapping):
                continue
            for mime, value in data.items():
                mime_text = str(mime)
                location = f"{base}.data[{mime_text}]"
                if mime_text == "application/json" or mime_text.endswith("+json"):
                    occurrences.extend(_scan_json_value(value, path=path, location=location))
                elif mime_text.startswith("text/"):
                    occurrences.extend(
                        extract_math_spans(
                            _as_text(value),
                            path=path,
                            location=location,
                            markdown=mime_text == "text/markdown",
                        )
                    )
    return occurrences


def collect_release_files(inputs: Sequence[Path]) -> list[Path]:
    """Resolve supported artifact inputs deterministically."""

    files: set[Path] = set()
    for source in inputs:
        if not source.exists():
            raise ReleaseMathError(f"Release-math input does not exist: {source}")
        candidates: Iterable[Path]
        if source.is_dir():
            candidates = source.rglob("*")
        else:
            candidates = (source,)
        for candidate in candidates:
            if not candidate.is_file() or candidate.suffix.casefold() not in SUPPORTED_SUFFIXES:
                continue
            if any(
                part.startswith(".") or part in IGNORED_DIRECTORY_NAMES for part in candidate.parts
            ):
                continue
            files.add(candidate.resolve())
    return sorted(files, key=lambda item: item.as_posix())


def extract_release_math(files: Sequence[Path]) -> list[MathOccurrence]:
    occurrences: list[MathOccurrence] = []
    for path in files:
        suffix = path.suffix.casefold()
        if suffix in {".md", ".markdown"}:
            occurrences.extend(extract_from_markdown(path))
        elif suffix == ".json":
            occurrences.extend(extract_from_json(path))
        elif suffix == ".ipynb":
            occurrences.extend(extract_from_notebook(path))
        else:  # pragma: no cover - collect_release_files enforces this invariant
            raise ReleaseMathError(f"Unsupported release-math artifact: {path}")
    return occurrences


def compile_with_katex(
    occurrences: Sequence[MathOccurrence],
    *,
    node_executable: Path,
    katex_module: Path,
) -> None:
    """Compile every occurrence with one bounded KaTeX subprocess."""

    if not node_executable.is_file():
        raise ReleaseMathError(f"Node executable does not exist: {node_executable}")
    if not katex_module.is_dir() or not (katex_module / "package.json").is_file():
        raise ReleaseMathError(
            f"KaTeX module path must be an installed package directory: {katex_module}"
        )
    payload = [
        {"expression": occurrence.expression, "display": occurrence.display}
        for occurrence in occurrences
    ]
    environment = os.environ.copy()
    environment["PRINCIPIA_KATEX_MODULE"] = str(katex_module.resolve())
    try:
        process = subprocess.run(
            [str(node_executable), "-e", _NODE_DRIVER],
            input=json.dumps(payload),
            capture_output=True,
            check=False,
            text=True,
            timeout=120,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ReleaseMathError(f"KaTeX compiler could not run: {exc}") from exc
    if process.returncode:
        detail = process.stderr.strip() or process.stdout.strip() or "unknown Node failure"
        raise ReleaseMathError(f"KaTeX compiler failed before completing the batch: {detail}")
    try:
        results = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise ReleaseMathError("KaTeX compiler returned malformed JSON.") from exc
    if not isinstance(results, list) or len(results) != len(occurrences):
        raise ReleaseMathError("KaTeX compiler returned an incomplete result set.")

    failures: list[str] = []
    for occurrence, result in zip(occurrences, results, strict=True):
        if not isinstance(result, Mapping) or result.get("ok") is not True:
            error = (
                result.get("error", "unknown KaTeX error")
                if isinstance(result, Mapping)
                else result
            )
            failures.append(
                f"{occurrence.path}:{occurrence.line}:{occurrence.column} "
                f"[{occurrence.location}] ({occurrence.expression_sha256[:12]}): {error}"
            )
    if failures:
        raise ReleaseMathError(
            f"Strict KaTeX rejected {len(failures)} mathematical span(s):\n- "
            + "\n- ".join(failures)
        )


def _summary(files: Sequence[Path], occurrences: Sequence[MathOccurrence]) -> MathCheckSummary:
    return MathCheckSummary(
        files_scanned=len(files),
        spans_compiled=len(occurrences),
        markdown_files=sum(path.suffix.casefold() in {".md", ".markdown"} for path in files),
        json_files=sum(path.suffix.casefold() == ".json" for path in files),
        notebook_files=sum(path.suffix.casefold() == ".ipynb" for path in files),
    )


def check_release_math(
    inputs: Sequence[Path],
    *,
    node_executable: Path,
    katex_module: Path,
) -> tuple[MathCheckSummary, list[MathOccurrence]]:
    files = collect_release_files(inputs)
    if not files:
        raise ReleaseMathError("No supported Markdown, JSON, or notebook artifacts were found.")
    occurrences = extract_release_math(files)
    compile_with_katex(
        occurrences,
        node_executable=node_executable,
        katex_module=katex_module,
    )
    return _summary(files, occurrences), occurrences


def _write_report(
    path: Path, summary: MathCheckSummary, occurrences: Sequence[MathOccurrence]
) -> None:
    working_directory = Path.cwd().resolve()

    def portable_path(artifact: Path) -> str:
        try:
            return artifact.resolve().relative_to(working_directory).as_posix()
        except ValueError:
            return artifact.name

    payload = {
        "schema_version": SCHEMA_VERSION,
        "engine": "KaTeX",
        "strict": "error",
        "status": "passed",
        "summary": asdict(summary),
        "spans": [
            {
                "path": portable_path(occurrence.path),
                "location": occurrence.location,
                "line": occurrence.line,
                "column": occurrence.column,
                "display": occurrence.display,
                "expression_sha256": occurrence.expression_sha256,
            }
            for occurrence in occurrences
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument(
        "--node",
        type=Path,
        default=os.environ.get("PRINCIPIA_NODE"),
        required="PRINCIPIA_NODE" not in os.environ,
        help="Node.js executable (or set PRINCIPIA_NODE).",
    )
    parser.add_argument(
        "--katex-module",
        type=Path,
        default=os.environ.get("PRINCIPIA_KATEX_MODULE"),
        required="PRINCIPIA_KATEX_MODULE" not in os.environ,
        help="Temporary node_modules/katex directory (or set PRINCIPIA_KATEX_MODULE).",
    )
    parser.add_argument("--report-json", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        summary, occurrences = check_release_math(
            arguments.inputs,
            node_executable=arguments.node,
            katex_module=arguments.katex_module,
        )
        if arguments.report_json:
            _write_report(arguments.report_json, summary, occurrences)
    except ReleaseMathError as exc:
        print(f"release math QA: FAILED\n{exc}", file=sys.stderr)
        return 1
    print(
        "release math QA: PASSED "
        f"({summary.spans_compiled} spans across {summary.files_scanned} artifacts)"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
