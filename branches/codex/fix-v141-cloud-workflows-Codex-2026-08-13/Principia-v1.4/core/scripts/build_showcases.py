"""Build fail-closed, output-bearing Principia showcase notebooks.

The local acceptance notebooks are deliberately credential-bearing and may
contain private paths, verbose diagnostics, progress frames, and raw model
traces.  This module converts one such notebook into a small public bundle.  It
retains outputs only from cells carrying an explicit ``principia_showcase``
marker and rejects the result unless all structural and privacy gates pass.

Example cell metadata::

    {
      "principia_showcase": {"output_kind": "retrieval_local_metrics"}
    }

Use the command line with an explicit root for every absolute path that may
legitimately be rewritten::

    python scripts/build_showcases.py build local/tutorial.ipynb \
      --output-root examples/showcases --task-id test1 \
      --title "Learned machine dialects" --path-root local

No source credential is accepted as a command-line argument.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import nbformat
from nbformat import NotebookNode

SCHEMA_VERSION = "principia.showcase.v1"
PUBLIC_NOTEBOOK_NAME = "tutorial.ipynb"
README_SHOWCASE_START = "<!-- PRINCIPIA_SHOWCASE_TABLE_START -->"
README_SHOWCASE_END = "<!-- PRINCIPIA_SHOWCASE_TABLE_END -->"
DEFAULT_README_TASK_IDS = ("test1", "test2", "test3")
PUBLIC_REPOSITORY_EXAMPLES_URL = (
    "https://github.com/pzqpzq/Principia/blob/main/Principia-v1.3/examples"
)

ALLOWED_OUTPUT_KINDS = frozenset(
    {
        "retrieval_metrics",
        "local_ingestion_metrics",
        "retrieval_local_metrics",
        "extraction_provenance",
        "evidence_counts",
        "extraction_evidence",
        "idea_card",
        "comparison_highlights",
        "validation_result",
        "comparison_validation",
    }
)

_SIGNALS_BY_KIND: dict[str, frozenset[str]] = {
    "retrieval_metrics": frozenset({"retrieval"}),
    "local_ingestion_metrics": frozenset({"ingestion"}),
    "retrieval_local_metrics": frozenset({"retrieval", "ingestion"}),
    "extraction_provenance": frozenset({"extraction"}),
    "evidence_counts": frozenset({"evidence"}),
    "extraction_evidence": frozenset({"extraction", "evidence"}),
    "idea_card": frozenset({"idea"}),
    "comparison_highlights": frozenset({"comparison"}),
    "validation_result": frozenset({"validation"}),
    "comparison_validation": frozenset({"comparison", "validation"}),
}
_REQUIRED_SIGNALS = frozenset(
    {"retrieval", "ingestion", "extraction", "evidence", "idea", "comparison", "validation"}
)

_SECRET_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")
_QUOTED_CREDENTIAL_RE = re.compile(
    r"(?P<quote>['\"])(?:YOUR_SILICONFLOW_API_KEY|sk-[A-Za-z0-9_-]{16,})(?P=quote)"
)
_AUTH_HEADER_RE = re.compile(r"(?i)\bauthorization\s*[:=]")
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}")
_FILE_URI_RE = re.compile(r"(?i)\b(?:file|local)://")
_ABSOLUTE_PATH_RE = re.compile(
    r"(?:/(?:Users|home|root|tmp|private|Volumes|mnt|var|opt|etc|usr|srv|data|workspace|"
    r"Applications|Library|System)/[^\s'\"<>]*)"
    r"|(?:[A-Za-z]:\\(?:Users|Documents and Settings|Temp)\\[^\s'\"<>]*)"
)
_UNC_PATH_RE = re.compile(r"\\\\[A-Za-z0-9_.-]+\\[^\s'\"<>]*")
_PROGRESS_LINE_RE = re.compile(
    r"(?i)(?:\d{1,3}%\s*[|\[]|\bit/s\b|\bETA\b|\belapsed\b|\bprogress\b.*\d+\s*/\s*\d+)"
)
_WARNING_LINE_RE = re.compile(
    r"(?i)^\s*(?:warning|userwarning|runtimewarning|futurewarning)\s*[:\[]"
)
_MOCK_ORIGIN_RE = re.compile(
    r"(?i)(?:execution_origin|origin)[\"']?\s*[:=]\s*[\"'](?:mock_fixture|template_fixture)"
)
_DEGRADED_TRUE_RE = re.compile(r"(?i)[\"']degraded[\"']\s*:\s*true")

_SENSITIVE_OUTPUT_KEYS = frozenset(
    {
        "absolute_path",
        "api_key",
        "authorization",
        "document_text",
        "local_path",
        "messages",
        "normalized_text",
        "private_excerpt",
        "prompt",
        "qa_report",
        "raw_text",
        "raw_trace",
        "source_excerpt",
        "token",
        "trace",
        "warning",
        "warnings",
        "widget_state",
    }
)

DEFAULT_PRIVATE_SENTINELS = (
    "LOCAL_ONLY_DO_NOT_UPLOAD",
    "PRIVATE_SENTINEL",
    "BEGIN_PRIVATE_CONTENT",
)


class ShowcaseError(RuntimeError):
    """Raised when a notebook cannot safely become a public showcase."""


@dataclass(frozen=True)
class ShowcaseAudit:
    """Structural and privacy facts verified for a showcase notebook."""

    code_cells: int
    code_lines: int
    retained_outputs: int
    output_kinds: tuple[str, ...]
    size_bytes: int
    privacy_scan: str = "passed"
    authenticity_scan: str = "passed"


@dataclass(frozen=True)
class ShowcaseBundle:
    """Paths and audit data returned by :func:`build_showcase`."""

    directory: Path
    notebook: Path
    markdown: Path
    manifest: Path
    checksums: Path
    audit: ShowcaseAudit


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _as_text(value: Any) -> str:
    if isinstance(value, list):
        return "".join(str(part) for part in value)
    return str(value)


def _rewrite_allowed_paths(text: str, roots: Sequence[Path]) -> str:
    rewritten = text
    ordered = sorted(
        (root.expanduser().resolve() for root in roots), key=lambda item: -len(str(item))
    )
    for root in ordered:
        variants = {str(root), root.as_posix()}
        for value in sorted(variants, key=len, reverse=True):
            prefix = value.rstrip("/\\")
            rewritten = rewritten.replace(f"{prefix}/", "")
            rewritten = rewritten.replace(f"{prefix}\\", "")
            rewritten = rewritten.replace(prefix, ".")
    return rewritten


def _assert_safe_text(text: str, *, private_sentinels: Sequence[str]) -> None:
    findings: list[str] = []
    if _SECRET_RE.search(text):
        findings.append("credential")
    if _AUTH_HEADER_RE.search(text) or _BEARER_RE.search(text):
        findings.append("authorization header")
    if _FILE_URI_RE.search(text):
        findings.append("file URI")
    if _ABSOLUTE_PATH_RE.search(text) or _UNC_PATH_RE.search(text):
        findings.append("absolute local path")
    folded = text.casefold()
    if any(sentinel.casefold() in folded for sentinel in private_sentinels if sentinel):
        findings.append("private sentinel")
    if findings:
        unique = ", ".join(dict.fromkeys(findings))
        raise ShowcaseError(f"Public showcase privacy scan failed: {unique}.")


def _assert_safe_value(value: Any, *, private_sentinels: Sequence[str]) -> None:
    """Scan decoded structured content without mistaking JSON-escaped LaTeX for UNC paths."""

    if isinstance(value, Mapping):
        for key, child in value.items():
            _assert_safe_text(str(key), private_sentinels=private_sentinels)
            _assert_safe_value(child, private_sentinels=private_sentinels)
        return
    if isinstance(value, list):
        for child in value:
            _assert_safe_value(child, private_sentinels=private_sentinels)
        return
    if isinstance(value, str):
        _assert_safe_text(value, private_sentinels=private_sentinels)


def _sanitize_non_code_text(
    text: str,
    *,
    path_roots: Sequence[Path],
    private_sentinels: Sequence[str],
) -> str:
    sanitized = _rewrite_allowed_paths(text, path_roots)
    sanitized = _SECRET_RE.sub("${SILICONFLOW_API_KEY}", sanitized)
    _assert_safe_text(sanitized, private_sentinels=private_sentinels)
    return sanitized


def _sanitize_code(
    source: str,
    *,
    path_roots: Sequence[Path],
    private_sentinels: Sequence[str],
) -> str:
    sanitized = _rewrite_allowed_paths(source, path_roots)
    uses_environment = bool(_QUOTED_CREDENTIAL_RE.search(sanitized))
    sanitized = _QUOTED_CREDENTIAL_RE.sub('os.environ["SILICONFLOW_API_KEY"]', sanitized)
    if uses_environment and not re.search(
        r"(?m)^\s*(?:import\s+[^#\n]*\bos\b|from\s+os\s+import\s+\w+)", sanitized
    ):
        sanitized = f"import os\n{sanitized}"
    _assert_safe_text(sanitized, private_sentinels=private_sentinels)
    try:
        ast.parse(sanitized)
    except SyntaxError as exc:
        raise ShowcaseError(
            f"Sanitized code is not valid Python: {exc.msg} (line {exc.lineno})."
        ) from exc
    return sanitized.rstrip() + "\n"


def _clean_json_value(
    value: Any,
    *,
    path_roots: Sequence[Path],
    private_sentinels: Sequence[str],
) -> Any:
    if isinstance(value, Mapping):
        cleaned: dict[str, Any] = {}
        for key, child in value.items():
            key_text = str(key)
            if key_text.casefold() in _SENSITIVE_OUTPUT_KEYS:
                continue
            cleaned[key_text] = _clean_json_value(
                child,
                path_roots=path_roots,
                private_sentinels=private_sentinels,
            )
        return cleaned
    if isinstance(value, list):
        return [
            _clean_json_value(item, path_roots=path_roots, private_sentinels=private_sentinels)
            for item in value
        ]
    if isinstance(value, str):
        return _sanitize_non_code_text(
            value,
            path_roots=path_roots,
            private_sentinels=private_sentinels,
        )
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _sanitize_non_code_text(
        str(value),
        path_roots=path_roots,
        private_sentinels=private_sentinels,
    )


def _filter_stream_lines(text: str) -> str:
    lines = text.replace("\r", "\n").splitlines()
    kept = [
        line
        for line in lines
        if line.strip() and not _PROGRESS_LINE_RE.search(line) and not _WARNING_LINE_RE.search(line)
    ]
    return "\n".join(kept)


def _sanitize_output(
    output: NotebookNode,
    *,
    path_roots: Sequence[Path],
    private_sentinels: Sequence[str],
) -> NotebookNode | None:
    output_type = str(output.get("output_type", ""))
    if output_type == "error":
        return None
    if output_type == "stream":
        if output.get("name", "stdout") != "stdout":
            return None
        text = _filter_stream_lines(_as_text(output.get("text", "")))
        if not text:
            return None
        text = _sanitize_non_code_text(
            text,
            path_roots=path_roots,
            private_sentinels=private_sentinels,
        )
        return nbformat.v4.new_output("stream", name="stdout", text=f"{text}\n")

    if output_type not in {"display_data", "execute_result"}:
        return None
    data = output.get("data", {})
    selected_mime: str | None = None
    selected_value: Any = None
    for mime in ("application/json", "text/markdown", "text/plain"):
        if mime in data:
            selected_mime = mime
            selected_value = data[mime]
            break
    if selected_mime is None:
        return None
    if selected_mime == "application/json":
        selected_value = _clean_json_value(
            selected_value,
            path_roots=path_roots,
            private_sentinels=private_sentinels,
        )
    else:
        text = _filter_stream_lines(_as_text(selected_value))
        if not text:
            return None
        structured: Any | None = None
        if selected_mime == "text/plain":
            for loader in (json.loads, ast.literal_eval):
                try:
                    candidate = loader(text)
                except (ValueError, SyntaxError, json.JSONDecodeError):
                    continue
                if isinstance(candidate, (Mapping, list)):
                    structured = candidate
                    break
        if structured is not None:
            selected_mime = "application/json"
            selected_value = _clean_json_value(
                structured,
                path_roots=path_roots,
                private_sentinels=private_sentinels,
            )
        else:
            selected_value = _sanitize_non_code_text(
                text,
                path_roots=path_roots,
                private_sentinels=private_sentinels,
            )
    kwargs: dict[str, Any] = {"data": {selected_mime: selected_value}, "metadata": {}}
    if output_type == "execute_result":
        kwargs["execution_count"] = output.get("execution_count")
    return nbformat.v4.new_output(output_type, **kwargs)


def _output_kind(cell: NotebookNode) -> str | None:
    metadata = cell.get("metadata", {})
    marker = metadata.get("principia_showcase")
    kind: str | None = None
    if isinstance(marker, str):
        kind = marker
    elif isinstance(marker, Mapping):
        candidate = marker.get("output_kind")
        if isinstance(candidate, str):
            kind = candidate
    for tag in metadata.get("tags", []):
        if isinstance(tag, str) and tag.startswith("showcase-output:"):
            tagged = tag.split(":", 1)[1]
            if kind is not None and tagged != kind:
                raise ShowcaseError("A showcase cell declares conflicting output kinds.")
            kind = tagged
    if kind is not None and kind not in ALLOWED_OUTPUT_KINDS:
        allowed = ", ".join(sorted(ALLOWED_OUTPUT_KINDS))
        raise ShowcaseError(f"Unknown showcase output kind {kind!r}; expected one of: {allowed}.")
    return kind


def _safe_notebook_metadata(notebook: NotebookNode, *, task_id: str, title: str) -> NotebookNode:
    source = notebook.get("metadata", {})
    metadata: dict[str, Any] = {
        "principia_showcase": {
            "schema_version": SCHEMA_VERSION,
            "task_id": task_id,
            "title": title,
        }
    }
    for key in ("kernelspec", "language_info"):
        if key in source and isinstance(source[key], Mapping):
            metadata[key] = dict(source[key])
    return NotebookNode(metadata)


def sanitize_notebook(
    source_notebook: Path,
    *,
    task_id: str,
    title: str,
    path_roots: Sequence[Path] = (),
    private_sentinels: Sequence[str] = DEFAULT_PRIVATE_SENTINELS,
) -> NotebookNode:
    """Return a public notebook or raise before any output is written.

    Outputs are retained only from explicitly marked cells.  A marked cell must
    have been executed and must reduce to exactly one safe textual/JSON output.
    """

    source_notebook = source_notebook.expanduser().resolve()
    notebook = nbformat.read(source_notebook, as_version=4)
    raw_json = nbformat.writes(notebook)
    if _MOCK_ORIGIN_RE.search(raw_json):
        raise ShowcaseError("Mock or template execution origin cannot pass showcase QA.")
    if _DEGRADED_TRUE_RE.search(raw_json):
        raise ShowcaseError("A degraded live run cannot pass showcase QA.")

    roots = tuple(dict.fromkeys((source_notebook.parent.resolve(), *path_roots)))
    public = nbformat.v4.new_notebook()
    public.metadata = _safe_notebook_metadata(notebook, task_id=task_id, title=title)
    output_kinds: list[str] = []

    for original in notebook.cells:
        if original.cell_type == "markdown":
            source = _sanitize_non_code_text(
                _as_text(original.get("source", "")),
                path_roots=roots,
                private_sentinels=private_sentinels,
            )
            cell = nbformat.v4.new_markdown_cell(source=source)
            public.cells.append(cell)
            continue
        if original.cell_type != "code":
            continue

        source = _sanitize_code(
            _as_text(original.get("source", "")),
            path_roots=roots,
            private_sentinels=private_sentinels,
        )
        kind = _output_kind(original)
        outputs: list[NotebookNode] = []
        if kind is not None:
            if original.get("execution_count") is None:
                raise ShowcaseError(f"Showcase output cell {kind!r} was not executed.")
            for raw_output in original.get("outputs", []):
                cleaned = _sanitize_output(
                    raw_output,
                    path_roots=roots,
                    private_sentinels=private_sentinels,
                )
                if cleaned is not None:
                    outputs.append(cleaned)
            if len(outputs) != 1:
                raise ShowcaseError(
                    f"Showcase output cell {kind!r} must reduce to exactly one meaningful output; "
                    f"found {len(outputs)}."
                )
            if kind in output_kinds:
                raise ShowcaseError(f"Showcase output kind {kind!r} is declared more than once.")
            output_kinds.append(kind)
        cell = nbformat.v4.new_code_cell(
            source=source,
            execution_count=original.get("execution_count"),
            outputs=outputs,
            metadata=({"principia_showcase": {"output_kind": kind}} if kind is not None else {}),
        )
        public.cells.append(cell)

    nbformat.validate(public)
    verify_notebook(public, private_sentinels=private_sentinels)
    return public


def _code_line_count(source: str) -> int:
    return len(source.rstrip().splitlines()) if source.rstrip() else 0


def verify_notebook(
    notebook: NotebookNode,
    *,
    private_sentinels: Sequence[str] = DEFAULT_PRIVATE_SENTINELS,
    max_code_cells: int = 8,
    max_code_lines: int = 60,
    max_lines_per_cell: int = 12,
    min_outputs: int = 4,
    max_outputs: int = 7,
    max_size_bytes: int = 250 * 1024,
) -> ShowcaseAudit:
    """Validate privacy, authenticity, story coverage, and concision."""

    nbformat.validate(notebook)
    code_cells = [cell for cell in notebook.cells if cell.cell_type == "code"]
    line_counts = [_code_line_count(_as_text(cell.get("source", ""))) for cell in code_cells]
    if len(code_cells) > max_code_cells:
        raise ShowcaseError(
            f"Showcase has {len(code_cells)} code cells; maximum is {max_code_cells}."
        )
    if sum(line_counts) > max_code_lines:
        raise ShowcaseError(
            f"Showcase has {sum(line_counts)} code lines; maximum is {max_code_lines}."
        )
    if any(count > max_lines_per_cell for count in line_counts):
        largest = max(line_counts, default=0)
        raise ShowcaseError(
            f"A showcase code cell has {largest} lines; maximum is {max_lines_per_cell}."
        )

    output_kinds: list[str] = []
    retained_outputs = 0
    for cell in code_cells:
        kind = _output_kind(cell)
        outputs = cell.get("outputs", [])
        if outputs and kind is None:
            raise ShowcaseError("An unmarked code cell retains output.")
        if kind is not None:
            if cell.get("execution_count") is None:
                raise ShowcaseError(f"Showcase output cell {kind!r} has no execution count.")
            if len(outputs) != 1:
                raise ShowcaseError(
                    f"Showcase output cell {kind!r} must contain exactly one output."
                )
            output_kinds.append(kind)
            retained_outputs += 1

    if not min_outputs <= retained_outputs <= max_outputs:
        raise ShowcaseError(
            f"Showcase retains {retained_outputs} outputs; expected {min_outputs}–{max_outputs}."
        )
    if len(set(output_kinds)) != len(output_kinds):
        raise ShowcaseError("Showcase output kinds must be unique.")
    covered = frozenset().union(*(_SIGNALS_BY_KIND[kind] for kind in output_kinds))
    missing = sorted(_REQUIRED_SIGNALS - covered)
    if missing:
        raise ShowcaseError(f"Showcase story is incomplete; missing signals: {', '.join(missing)}.")

    serialized = nbformat.writes(notebook)
    payload = serialized.encode("utf-8")
    if len(payload) > max_size_bytes:
        raise ShowcaseError(f"Showcase is {len(payload)} bytes; maximum is {max_size_bytes} bytes.")
    _assert_safe_value(notebook, private_sentinels=private_sentinels)
    if _MOCK_ORIGIN_RE.search(serialized) or _DEGRADED_TRUE_RE.search(serialized):
        raise ShowcaseError("Showcase authenticity scan failed.")
    if '"application/vnd.jupyter.widget' in serialized or '"widgets"' in serialized:
        raise ShowcaseError("Widget state or widget MIME is not allowed in a public showcase.")
    _assert_authentic_story(notebook)

    return ShowcaseAudit(
        code_cells=len(code_cells),
        code_lines=sum(line_counts),
        retained_outputs=retained_outputs,
        output_kinds=tuple(output_kinds),
        size_bytes=len(payload),
    )


def _payload_from_output(output: NotebookNode) -> Any:
    if output.output_type == "stream":
        return _as_text(output.get("text", "")).strip()
    data = output.get("data", {})
    if "application/json" in data:
        return data["application/json"]
    value = data.get("text/markdown", data.get("text/plain", ""))
    text = _as_text(value).strip()
    for loader in (json.loads, ast.literal_eval):
        try:
            parsed = loader(text)
        except (ValueError, SyntaxError, json.JSONDecodeError):
            continue
        if isinstance(parsed, (dict, list, str, int, float, bool)) or parsed is None:
            return parsed
    return text


def _output_summaries(notebook: NotebookNode) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        kind = _output_kind(cell)
        if kind is None:
            continue
        payload = _payload_from_output(cell.outputs[0])
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        summaries.append(
            {
                "kind": kind,
                "payload": payload,
                "payload_sha256": _sha256_bytes(canonical.encode("utf-8")),
            }
        )
    return summaries


def _recursive_find(value: Any, names: Sequence[str]) -> Any | None:
    folded_names = {name.casefold() for name in names}
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).casefold() in folded_names and isinstance(child, (str, int, float, bool)):
                return child
        for child in value.values():
            found = _recursive_find(child, names)
            if found is not None:
                return found
    if isinstance(value, list):
        for child in value:
            found = _recursive_find(child, names)
            if found is not None:
                return found
    if isinstance(value, str):
        if "title" in folded_names:
            heading = re.search(r"(?m)^#\s+(.+?)\s*$", value)
            if heading:
                return heading.group(1).strip()
        for name in folded_names:
            label = name.replace("_", r"[ _-]")
            match = re.search(
                rf"(?im)^\s*(?:[-*]\s*)?(?:\*\*)?{label}\s*"
                rf"(?::\*\*|\*\*:|:)\s*(.+?)\s*$",
                value,
            )
            if match:
                return _markdown_scalar(match.group(1))
    return None


def _markdown_scalar(value: str) -> Any:
    """Decode one labelled Markdown value used by a curated output card."""

    text = str(value).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"`", "'", '"'}:
        text = text[1:-1].strip()
    folded = text.casefold()
    if folded == "true":
        return True
    if folded == "false":
        return False
    if re.fullmatch(r"-?[0-9]+", text):
        return int(text)
    if re.fullmatch(r"-?(?:[0-9]+\.[0-9]*|[0-9]*\.[0-9]+)", text):
        return float(text)
    return text


def _assert_authentic_story(notebook: NotebookNode) -> None:
    """Require a live, complete acceptance story in the curated outputs."""

    payloads = {item["kind"]: item["payload"] for item in _output_summaries(notebook)}

    def first(*kinds: str) -> Any:
        return next((payloads[kind] for kind in kinds if kind in payloads), {})

    retrieval = first("retrieval_metrics", "retrieval_local_metrics")
    ingestion = first("local_ingestion_metrics", "retrieval_local_metrics")
    extraction = first("extraction_provenance", "extraction_evidence")
    evidence = first("evidence_counts", "extraction_evidence")
    idea = first("idea_card")
    comparison = first("comparison_highlights", "comparison_validation")
    validation = first("validation_result", "comparison_validation")

    expected = {
        "online works": (_recursive_find(retrieval, ("online_works", "online_count")), 50),
        "local documents": (_recursive_find(ingestion, ("local_documents", "local_count")), 5),
        "feature bundles": (
            _recursive_find(extraction, ("feature_bundles", "completed_features", "extracted")),
            55,
        ),
        "idea evidence": (_recursive_find(evidence, ("ideas",)), 5),
        "principle evidence": (_recursive_find(evidence, ("principles",)), 5),
        "takeaway evidence": (_recursive_find(evidence, ("takeaways",)), 5),
        "total evidence": (
            _recursive_find(evidence, ("evidence_records", "selected_records", "total")),
            15,
        ),
    }
    wrong = [name for name, (actual, required) in expected.items() if actual != required]
    if wrong:
        raise ShowcaseError(
            "Showcase acceptance metrics are incomplete or inconsistent: " + ", ".join(wrong) + "."
        )

    rerank = _recursive_find(retrieval, ("embedding_rerank", "rerank_mode_applied"))
    if rerank not in {True, "applied", "embedding_rerank"}:
        raise ShowcaseError("Showcase does not prove successful embedding reranking.")

    origin = _recursive_find(idea, ("execution_origin", "origin"))
    degraded = _recursive_find(idea, ("degraded",))
    mode = _recursive_find(idea, ("mode", "generation_mode"))
    title = _recursive_find(idea, ("title",))
    thesis = _recursive_find(idea, ("thesis",))
    if origin != "live_llm":
        raise ShowcaseError("Showcase Idea Card must declare execution_origin='live_llm'.")
    if degraded is not False:
        raise ShowcaseError("Showcase Idea Card must explicitly be non-degraded.")
    if mode != "scidialect-evo" or not str(title or "").strip() or not str(thesis or "").strip():
        raise ShowcaseError("Showcase Idea Card is missing its strict live generation contract.")

    compared = _recursive_find(comparison, ("prior_ideas_compared", "comparison_rows"))
    highlights = comparison.get("highlights") if isinstance(comparison, Mapping) else None
    if not isinstance(compared, (int, float)) or isinstance(compared, bool) or compared < 1:
        raise ShowcaseError("Showcase comparison must include at least one prior idea.")
    if not isinstance(highlights, list) or not highlights:
        raise ShowcaseError("Showcase comparison highlights must be nonempty.")

    status = _recursive_find(validation, ("validation", "status", "passed"))
    passed = status is True or (isinstance(status, str) and status.casefold() == "passed")
    if not passed:
        raise ShowcaseError("Showcase validation result must be passed.")


def _summary_payload(summaries: Sequence[Mapping[str, Any]], kinds: Iterable[str]) -> Any:
    choices = set(kinds)
    for item in summaries:
        if item["kind"] in choices:
            return item["payload"]
    return {}


def _readme_row(task_id: str, title: str, summaries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    retrieval = _summary_payload(summaries, {"retrieval_metrics", "retrieval_local_metrics"})
    ingestion = _summary_payload(summaries, {"local_ingestion_metrics", "retrieval_local_metrics"})
    extraction = _summary_payload(summaries, {"extraction_provenance", "extraction_evidence"})
    evidence = _summary_payload(summaries, {"evidence_counts", "extraction_evidence"})
    idea = _summary_payload(summaries, {"idea_card"})
    validation = _summary_payload(summaries, {"validation_result", "comparison_validation"})
    return {
        "task_id": task_id,
        "title": title,
        "online_works": _recursive_find(retrieval, ("online_works", "online_count")),
        "local_documents": _recursive_find(ingestion, ("local_documents", "local_count")),
        "feature_bundles": _recursive_find(
            extraction, ("feature_bundles", "completed_features", "extracted")
        ),
        "evidence_records": _recursive_find(
            evidence, ("evidence_records", "selected_records", "total")
        ),
        "mode": _recursive_find(idea, ("mode", "generation_mode")),
        "validation": _recursive_find(validation, ("validation", "status", "passed")),
    }


def _render_markdown(title: str, summaries: Sequence[Mapping[str, Any]]) -> str:
    lines = [
        f"# {title}",
        "",
        "Verified Principia v1.3.3 showcase generated from a live acceptance notebook.",
        "",
    ]
    for item in summaries:
        heading = str(item["kind"]).replace("_", " ").title()
        payload = item["payload"]
        lines.extend((f"## {heading}", ""))
        if isinstance(payload, str):
            lines.extend((payload, ""))
        else:
            lines.extend(("```json", json.dumps(payload, indent=2, ensure_ascii=False), "```", ""))
    return "\n".join(lines).rstrip() + "\n"


def _write_checksums(directory: Path, names: Sequence[str]) -> Path:
    output = directory / "checksums.sha256"
    lines = [f"{_sha256_file(directory / name)}  {name}" for name in names]
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


def build_showcase(
    source_notebook: Path,
    *,
    output_root: Path,
    task_id: str,
    title: str,
    path_roots: Sequence[Path] = (),
    private_sentinels: Sequence[str] = DEFAULT_PRIVATE_SENTINELS,
) -> ShowcaseBundle:
    """Build one verified public bundle from an executed local notebook."""

    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", task_id):
        raise ShowcaseError("task_id must contain only lowercase letters, digits, '_' or '-'.")
    public = sanitize_notebook(
        source_notebook,
        task_id=task_id,
        title=title,
        path_roots=path_roots,
        private_sentinels=private_sentinels,
    )
    audit = verify_notebook(public, private_sentinels=private_sentinels)
    notebook_bytes = nbformat.writes(public).encode("utf-8")
    summaries = _output_summaries(public)

    directory = output_root.expanduser().resolve() / task_id
    directory.mkdir(parents=True, exist_ok=True)
    notebook_path = directory / PUBLIC_NOTEBOOK_NAME
    notebook_path.write_bytes(notebook_bytes)
    markdown_path = directory / "showcase.md"
    markdown_path.write_text(_render_markdown(title, summaries), encoding="utf-8")
    manifest_path = directory / "showcase.json"
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "task_id": task_id,
        "title": title,
        "source_notebook_sha256": _sha256_file(source_notebook),
        "notebook": PUBLIC_NOTEBOOK_NAME,
        "notebook_sha256": _sha256_file(notebook_path),
        "audit": asdict(audit),
        "outputs": summaries,
        "readme_row": _readme_row(task_id, title, summaries),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    checksums_path = _write_checksums(
        directory, (PUBLIC_NOTEBOOK_NAME, "showcase.md", "showcase.json")
    )
    bundle = ShowcaseBundle(
        directory=directory,
        notebook=notebook_path,
        markdown=markdown_path,
        manifest=manifest_path,
        checksums=checksums_path,
        audit=audit,
    )
    verify_bundle(directory, private_sentinels=private_sentinels)
    return bundle


def verify_bundle(
    directory: Path,
    *,
    private_sentinels: Sequence[str] = DEFAULT_PRIVATE_SENTINELS,
) -> ShowcaseAudit:
    """Verify a generated bundle, including every declared checksum."""

    directory = directory.expanduser().resolve()
    notebook_path = directory / PUBLIC_NOTEBOOK_NAME
    manifest_path = directory / "showcase.json"
    checksum_path = directory / "checksums.sha256"
    for path in (notebook_path, manifest_path, directory / "showcase.md", checksum_path):
        if not path.is_file():
            raise ShowcaseError(f"Missing showcase artifact: {path.name}.")
    notebook = nbformat.read(notebook_path, as_version=4)
    audit = verify_notebook(notebook, private_sentinels=private_sentinels)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ShowcaseError("Unsupported showcase manifest schema.")
    if manifest.get("notebook_sha256") != _sha256_file(notebook_path):
        raise ShowcaseError("Notebook checksum does not match showcase.json.")
    showcase_metadata = notebook.metadata.get("principia_showcase", {})
    task_id = showcase_metadata.get("task_id")
    title = showcase_metadata.get("title")
    summaries = _output_summaries(notebook)
    expected_audit = json.loads(json.dumps(asdict(audit)))
    if manifest.get("task_id") != task_id or manifest.get("title") != title:
        raise ShowcaseError("Showcase manifest identity does not match the notebook metadata.")
    if manifest.get("audit") != expected_audit:
        raise ShowcaseError("Showcase manifest audit does not match the verified notebook.")
    if manifest.get("outputs") != summaries:
        raise ShowcaseError("Showcase manifest outputs do not match the verified notebook.")
    if manifest.get("readme_row") != _readme_row(str(task_id), str(title), summaries):
        raise ShowcaseError("Showcase README row does not match the verified notebook outputs.")
    expected: dict[str, str] = {}
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        digest, separator, name = line.partition("  ")
        if not separator or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ShowcaseError("Malformed checksums.sha256 entry.")
        expected[name] = digest
    for name in (PUBLIC_NOTEBOOK_NAME, "showcase.md", "showcase.json"):
        if expected.get(name) != _sha256_file(directory / name):
            raise ShowcaseError(f"Checksum mismatch for {name}.")
    _assert_safe_value(manifest, private_sentinels=private_sentinels)
    for path in (directory / "showcase.md", checksum_path):
        _assert_safe_text(path.read_text(encoding="utf-8"), private_sentinels=private_sentinels)
    return audit


def _display_value(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "passed" if value else "failed"
    return str(value).replace("|", "\\|")


def _verified_readme_data(
    output_root: Path,
    *,
    private_sentinels: Sequence[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    output_root = output_root.expanduser().resolve()
    rows: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in sorted(output_root.glob("*/showcase.json")):
        verify_bundle(path.parent, private_sentinels=private_sentinels)
        manifest = json.loads(path.read_text(encoding="utf-8"))
        task_id = str(manifest["task_id"])
        if path.parent.name != task_id:
            raise ShowcaseError(
                f"Showcase directory {path.parent.name!r} does not match task_id {task_id!r}."
            )
        if task_id in seen:
            raise ShowcaseError(f"Duplicate showcase task_id in README inputs: {task_id!r}.")
        seen.add(task_id)
        rows.append(manifest["readme_row"])
        sources.append(
            {
                "task_id": task_id,
                "showcase_json_sha256": _sha256_file(path),
                "notebook_sha256": manifest["notebook_sha256"],
            }
        )
    if not rows:
        raise ShowcaseError("No verified showcase bundles were found.")
    return rows, sources


def _render_readme_table(
    rows: Sequence[Mapping[str, Any]],
    *,
    link_prefix: str = "",
) -> str:
    headers = ("Task", "Online", "Local", "Features", "Evidence", "Mode", "Validation")
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    prefix = link_prefix.strip("/")
    for row in rows:
        relative = f"{row['task_id']}/tutorial.ipynb"
        link = f"{prefix}/{relative}" if prefix else relative
        values = (
            f"[{row['title']}]({link})",
            row.get("online_works"),
            row.get("local_documents"),
            row.get("feature_bundles"),
            row.get("evidence_records"),
            row.get("mode"),
            row.get("validation"),
        )
        lines.append("| " + " | ".join(_display_value(value) for value in values) + " |")
    return "\n".join(lines) + "\n"


def _required_readme_rows(
    rows: Sequence[dict[str, Any]],
    expected_task_ids: Sequence[str],
) -> list[dict[str, Any]]:
    expected = tuple(str(task_id) for task_id in expected_task_ids)
    if not expected or len(set(expected)) != len(expected):
        raise ShowcaseError("Expected README task IDs must be nonempty and unique.")
    by_id = {str(row.get("task_id")): row for row in rows}
    missing = [task_id for task_id in expected if task_id not in by_id]
    unexpected = sorted(set(by_id) - set(expected))
    if missing or unexpected:
        details: list[str] = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if unexpected:
            details.append("unexpected " + ", ".join(unexpected))
        raise ShowcaseError("README showcase task set is incomplete: " + "; ".join(details) + ".")
    return [by_id[task_id] for task_id in expected]


def _readme_table_bounds(text: str) -> tuple[int, int]:
    start_matches = list(re.finditer(rf"(?m)^{re.escape(README_SHOWCASE_START)}$", text))
    end_matches = list(re.finditer(rf"(?m)^{re.escape(README_SHOWCASE_END)}$", text))
    if len(start_matches) != 1 or len(end_matches) != 1:
        raise ShowcaseError(
            "README must contain exactly one showcase start marker and one showcase end marker."
        )
    start = start_matches[0].start()
    end = end_matches[0].end()
    if end_matches[0].start() <= start_matches[0].end():
        raise ShowcaseError("README showcase markers are out of order.")
    return start, end


def _canonical_root_readme_block(rows: Sequence[Mapping[str, Any]]) -> str:
    # The same README is rendered at the repository root and on PyPI.  Absolute
    # links keep the verified showcase notebooks reachable from both surfaces.
    table = _render_readme_table(
        rows,
        link_prefix=PUBLIC_REPOSITORY_EXAMPLES_URL,
    ).rstrip("\n")
    return f"{README_SHOWCASE_START}\n{table}\n{README_SHOWCASE_END}"


def sync_root_readme_showcases(
    readme_path: Path,
    output_root: Path,
    *,
    expected_task_ids: Sequence[str] = DEFAULT_README_TASK_IDS,
    private_sentinels: Sequence[str] = DEFAULT_PRIVATE_SENTINELS,
) -> bool:
    """Update only the marked root-README table from verified showcase manifests."""

    rows, _ = _verified_readme_data(output_root, private_sentinels=private_sentinels)
    ordered = _required_readme_rows(rows, expected_task_ids)
    readme_path = readme_path.expanduser().resolve()
    if not readme_path.is_file():
        raise ShowcaseError(f"Root README does not exist: {readme_path}")
    original = readme_path.read_text(encoding="utf-8")
    start, end = _readme_table_bounds(original)
    block = _canonical_root_readme_block(ordered)
    _assert_safe_text(block, private_sentinels=private_sentinels)
    updated = original[:start] + block + original[end:]
    if updated == original:
        return False
    readme_path.write_text(updated, encoding="utf-8")
    return True


def verify_root_readme_showcases(
    readme_path: Path,
    output_root: Path,
    *,
    expected_task_ids: Sequence[str] = DEFAULT_README_TASK_IDS,
    private_sentinels: Sequence[str] = DEFAULT_PRIVATE_SENTINELS,
) -> None:
    """Fail if the marked root-README table drifts from verified manifests."""

    rows, _ = _verified_readme_data(output_root, private_sentinels=private_sentinels)
    ordered = _required_readme_rows(rows, expected_task_ids)
    readme_path = readme_path.expanduser().resolve()
    if not readme_path.is_file():
        raise ShowcaseError(f"Root README does not exist: {readme_path}")
    text = readme_path.read_text(encoding="utf-8")
    start, end = _readme_table_bounds(text)
    expected = _canonical_root_readme_block(ordered)
    if text[start:end] != expected:
        raise ShowcaseError(
            "Root README showcase table is stale; run the README parity update command."
        )
    _assert_safe_text(expected, private_sentinels=private_sentinels)


def build_readme_parity(
    output_root: Path,
    *,
    private_sentinels: Sequence[str] = DEFAULT_PRIVATE_SENTINELS,
) -> tuple[Path, Path]:
    """Build README-ready parity data only from checksum-verified bundles."""

    output_root = output_root.expanduser().resolve()
    rows, manifests = _verified_readme_data(
        output_root,
        private_sentinels=private_sentinels,
    )
    json_path = output_root / "README_PARITY.json"
    json_path.write_text(
        json.dumps(
            {"schema_version": SCHEMA_VERSION, "rows": rows, "sources": manifests},
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    markdown_path = output_root / "README_TABLE.md"
    markdown_path.write_text(_render_readme_table(rows), encoding="utf-8")
    _assert_safe_value(
        json.loads(json_path.read_text(encoding="utf-8")),
        private_sentinels=private_sentinels,
    )
    _assert_safe_text(
        markdown_path.read_text(encoding="utf-8"), private_sentinels=private_sentinels
    )
    return json_path, markdown_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="sanitize one executed notebook")
    build.add_argument("source", type=Path)
    build.add_argument("--output-root", type=Path, required=True)
    build.add_argument("--task-id", required=True)
    build.add_argument("--title", required=True)
    build.add_argument("--path-root", action="append", default=[], type=Path)
    build.add_argument("--private-sentinel", action="append", default=[])
    verify = subparsers.add_parser("verify", help="verify one generated bundle")
    verify.add_argument("directory", type=Path)
    verify.add_argument("--private-sentinel", action="append", default=[])
    parity = subparsers.add_parser("parity", help="build README parity artifacts")
    parity.add_argument("output_root", type=Path)
    parity.add_argument("--private-sentinel", action="append", default=[])
    readme = subparsers.add_parser(
        "readme",
        help="update or verify the marked root-README showcase table",
    )
    readme.add_argument("output_root", type=Path)
    readme.add_argument("--readme", type=Path, required=True)
    readme.add_argument("--check", action="store_true", help="verify without writing")
    readme.add_argument(
        "--task-id",
        action="append",
        default=[],
        help="required showcase task ID; defaults to test1, test2, and test3",
    )
    readme.add_argument("--private-sentinel", action="append", default=[])
    return parser


def _sentinels(extra: Sequence[str]) -> tuple[str, ...]:
    return (*DEFAULT_PRIVATE_SENTINELS, *extra)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "build":
        bundle = build_showcase(
            args.source,
            output_root=args.output_root,
            task_id=args.task_id,
            title=args.title,
            path_roots=args.path_root,
            private_sentinels=_sentinels(args.private_sentinel),
        )
        print(json.dumps({"bundle": str(bundle.directory), "audit": asdict(bundle.audit)}))
        return 0
    if args.command == "verify":
        audit = verify_bundle(
            args.directory,
            private_sentinels=_sentinels(args.private_sentinel),
        )
        print(json.dumps(asdict(audit)))
        return 0
    if args.command == "parity":
        json_path, markdown_path = build_readme_parity(
            args.output_root,
            private_sentinels=_sentinels(args.private_sentinel),
        )
        print(json.dumps({"json": str(json_path), "markdown": str(markdown_path)}))
        return 0
    expected = tuple(args.task_id) or DEFAULT_README_TASK_IDS
    if args.check:
        verify_root_readme_showcases(
            args.readme,
            args.output_root,
            expected_task_ids=expected,
            private_sentinels=_sentinels(args.private_sentinel),
        )
        print(json.dumps({"readme": str(args.readme), "status": "in_sync"}))
        return 0
    changed = sync_root_readme_showcases(
        args.readme,
        args.output_root,
        expected_task_ids=expected,
        private_sentinels=_sentinels(args.private_sentinel),
    )
    print(json.dumps({"readme": str(args.readme), "changed": changed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
