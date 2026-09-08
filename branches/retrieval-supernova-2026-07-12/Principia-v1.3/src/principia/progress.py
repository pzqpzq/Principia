from __future__ import annotations

from typing import Any

from .models import PipelineResult, RunStatus


class NotebookProgress:
    def __init__(self, title: str = "Running Principia pipeline") -> None:
        self.title = title
        self.events: list[dict[str, Any]] = []

    def __call__(self, status: RunStatus) -> None:
        self.events.append(status.model_dump())
        self._display(self.render_status(status))

    def done(self, result: PipelineResult) -> None:
        self._display(self.render_result(result))

    def render_status(self, status: RunStatus) -> str:
        pct = max(0, min(100, int(status.progress * 100)))
        filled = "#" * (pct // 5)
        empty = "." * (20 - pct // 5)
        counts = ", ".join(f"{key}={value}" for key, value in status.counts.items())
        eta = format_duration(status.eta_seconds) if status.eta_seconds is not None else "calculating"
        return "\n".join(
            [
                f"### {self.title}",
                "",
                f"**Operation:** `{status.operation}`  ",
                f"**Stage:** `{status.stage}`  ",
                f"**Progress:** `{filled}{empty}` {pct}%  ",
                f"**Elapsed:** {format_duration(status.elapsed_seconds)}  ",
                f"**ETA:** {eta}  ",
                f"**Message:** {status.message}  ",
                f"**Counts:** {counts or '-'}",
            ]
        )

    def render_result(self, result: PipelineResult) -> str:
        return "\n".join(
            [
                "### Pipeline complete",
                "",
                f"- Retrieved works: **{len(result.works)}**",
                f"- Extracted feature sets: **{len(result.features)}**",
                f"- Comparison rows: **{len(result.comparison.rows)}**",
                f"- Idea: **{result.idea.title}**",
                f"- Export path: `{result.export_path}`",
            ]
        )

    def _display(self, markdown: str) -> None:
        try:
            from IPython.display import Markdown, clear_output, display

            clear_output(wait=True)
            display(Markdown(markdown))
        except Exception:
            print(markdown)


def notebook_progress(title: str = "Running Principia pipeline") -> NotebookProgress:
    return NotebookProgress(title=title)


def format_duration(seconds: float | int | None) -> str:
    if seconds is None:
        return "-"
    remaining = max(0, int(round(float(seconds))))
    minutes, sec = divmod(remaining, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {sec:02d}s"
    if minutes:
        return f"{minutes}m {sec:02d}s"
    return f"{sec}s"
