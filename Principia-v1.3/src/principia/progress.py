from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING, Any

from .models import PipelineResult, RunStatus

if TYPE_CHECKING:
    from .pipeline import PipelineJob


class NotebookProgress:
    """Small text-first notebook renderer with optional interactive controls."""

    def __init__(self, title: str = "Running Principia pipeline") -> None:
        self.title = title
        self.events: list[dict[str, Any]] = []
        self._last_progress = 0.0
        self._job: PipelineJob | None = None
        self._widgets: dict[str, Any] = {}

    def __call__(self, status: RunStatus) -> None:
        self._last_progress = max(self._last_progress, status.progress)
        if status.progress < self._last_progress:
            status = status.model_copy(update={"progress": self._last_progress})
        self.events.append(status.model_dump())
        if self._widgets:
            self._update_widgets(status)
        else:
            self._display(self.render_status(status))

    def bind(self, job: PipelineJob) -> Any:
        """Bind Pause/Resume/Stop controls when ipywidgets is installed."""

        self._job = job
        try:
            import ipywidgets as widgets  # type: ignore[import-not-found, import-untyped]
            from IPython.display import display

            progress = widgets.IntProgress(value=0, min=0, max=100, description="Progress")
            detail = widgets.HTML()
            pause = widgets.Button(description="Pause", button_style="warning", icon="pause")
            resume = widgets.Button(
                description="Resume", button_style="success", icon="play", disabled=True
            )
            stop = widgets.Button(description="Stop", button_style="danger", icon="stop")
            pause.on_click(lambda _: job.pause())
            resume.on_click(lambda _: job.resume())
            stop.on_click(lambda _: job.stop())
            panel = widgets.VBox(
                [
                    widgets.HTML(f"<strong>{self.title}</strong>"),
                    progress,
                    detail,
                    widgets.HBox([pause, resume, stop]),
                ]
            )
            self._widgets = {
                "progress": progress,
                "detail": detail,
                "pause": pause,
                "resume": resume,
                "stop": stop,
                "panel": panel,
            }
            self._update_widgets(job.status())
            display(panel)
            self._start_monitor()
            return panel
        except (ImportError, ModuleNotFoundError):
            status = job.status()
            self(status)
            self._start_monitor()
            return self

    def done(self, result: PipelineResult) -> None:
        self._display(self.render_result(result))

    def render_status(self, status: RunStatus) -> str:
        pct = max(0, min(100, int(status.progress * 100)))
        filled = "#" * (pct // 5)
        empty = "." * (20 - pct // 5)
        counts = _compact_counts(status.counts)
        eta = (
            format_duration(status.eta_seconds) if status.eta_seconds is not None else "calculating"
        )
        return "\n".join(
            [
                f"### {self.title}",
                "",
                f"**Operation:** `{status.operation}`  ",
                f"**State:** `{status.status}`  ",
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

    def _start_monitor(self) -> None:
        if self._job is None:
            return

        def monitor() -> None:
            assert self._job is not None
            last_signature: tuple[Any, ...] | None = None
            while True:
                try:
                    status = self._job.status()
                except KeyError:
                    return
                signature = (
                    status.status,
                    status.stage,
                    status.progress,
                    status.message,
                    status.updated_at,
                )
                if signature != last_signature:
                    self(status)
                    last_signature = signature
                if status.status in {"complete", "cancelled", "error"}:
                    return
                time.sleep(0.25)

        threading.Thread(target=monitor, name="principia-notebook-progress", daemon=True).start()

    def _update_widgets(self, status: RunStatus) -> None:
        progress = self._widgets.get("progress")
        detail = self._widgets.get("detail")
        if progress is not None:
            progress.value = max(progress.value, int(status.progress * 100))
            progress.bar_style = (
                "success"
                if status.status == "complete"
                else "danger"
                if status.status in {"cancelled", "error"}
                else "warning"
                if status.status in {"pause_requested", "paused"}
                else "info"
            )
        if detail is not None:
            detail.value = (
                f"<code>{status.status}</code> · <code>{status.stage}</code> · "
                f"{status.message} · elapsed {format_duration(status.elapsed_seconds)}"
            )
        paused = status.status in {"pause_requested", "paused"}
        terminal = status.status in {"complete", "cancelled", "error"}
        self._widgets["pause"].disabled = paused or terminal
        self._widgets["resume"].disabled = not paused or terminal
        self._widgets["stop"].disabled = terminal

    def _display(self, markdown: str) -> None:
        try:
            from IPython.display import Markdown, clear_output, display

            clear_output(wait=True)
            display(Markdown(markdown))
        except (ImportError, ModuleNotFoundError):
            print(markdown)


def notebook_progress(title: str = "Running Principia pipeline") -> NotebookProgress:
    return NotebookProgress(title=title)


class TerminalProgress:
    """Live Rich progress for a background pipeline in a terminal."""

    def __init__(self, title: str = "Principia") -> None:
        self.title = title
        self._thread: threading.Thread | None = None

    def bind(self, job: PipelineJob) -> TerminalProgress:
        from rich.progress import (
            BarColumn,
            Progress,
            SpinnerColumn,
            TaskProgressColumn,
            TextColumn,
            TimeElapsedColumn,
            TimeRemainingColumn,
        )

        progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
        )
        task_id = progress.add_task(self.title, total=100)

        def monitor() -> None:
            with progress:
                while True:
                    status = job.status()
                    description = f"{status.stage}: {status.message}".strip()[:100]
                    progress.update(
                        task_id,
                        completed=max(0.0, min(100.0, status.progress * 100.0)),
                        description=description,
                    )
                    if status.status in {"complete", "cancelled", "error"}:
                        return
                    time.sleep(0.25)

        self._thread = threading.Thread(
            target=monitor,
            name="principia-terminal-progress",
            daemon=True,
        )
        self._thread.start()
        return self


def display_pipeline_job(job: PipelineJob, *, mode: str = "auto") -> Any:
    """Use notebook controls in Jupyter and live Rich progress in terminals."""

    normalized = str(mode or "auto").strip().lower()
    if normalized == "none":
        return None

    view = NotebookProgress()
    if _in_notebook() and normalized in {"auto", "notebook"}:
        return view.bind(job)
    if normalized in {"auto", "rich"}:
        return TerminalProgress().bind(job)
    print(view.render_status(job.status()))
    view._job = job
    view._start_monitor()
    return view


def _in_notebook() -> bool:
    try:
        from IPython import get_ipython

        shell = get_ipython()
        return shell is not None and shell.__class__.__name__ in {"ZMQInteractiveShell", "Shell"}
    except (ImportError, NameError):
        return False


def _compact_counts(counts: dict[str, Any]) -> str:
    items: list[str] = []
    for key, value in counts.items():
        if key in {"pipeline_config", "trace", "warnings"}:
            continue
        if isinstance(value, (str, int, float, bool)):
            rendered = str(value)
        elif isinstance(value, (list, tuple, set, dict)):
            rendered = str(len(value))
        else:
            continue
        items.append(f"{key}={rendered[:48]}")
        if len(items) >= 6:
            break
    return ", ".join(items)


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
