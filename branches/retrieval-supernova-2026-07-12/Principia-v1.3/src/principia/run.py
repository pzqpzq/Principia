from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, Literal

from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from .ids import stable_prefixed_id
from .models import CancelToken, RunStatus, utc_now
from .storage import WorkspaceStorage

ProgressCallback = Callable[[RunStatus], None]


class RunHandle:
    def __init__(
        self,
        storage: WorkspaceStorage,
        operation: str,
        *,
        callback: ProgressCallback | None = None,
        token: CancelToken | None = None,
        show_progress: bool = False,
    ) -> None:
        self.storage = storage
        self.token = token or CancelToken()
        self.callback = callback
        self.show_progress = show_progress
        self.status = RunStatus(
            run_id=stable_prefixed_id("RUN", operation, utc_now()),
            operation=operation,
            status="running",
            stage="starting",
            message="Starting.",
        )
        self._started_monotonic = time.monotonic()
        self.storage.create_run(self.status)
        self._progress: Progress | None = None
        self._task_id: Any = None

    def __enter__(self) -> RunHandle:
        if self.show_progress:
            self._progress = Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                TextColumn("{task.percentage:>3.0f}%"),
                TimeElapsedColumn(),
                TimeRemainingColumn(),
                transient=False,
            )
            self._progress.start()
            self._task_id = self._progress.add_task(self.status.message, total=100)
        return self

    def __exit__(self, exc_type, exc, tb) -> Literal[False]:
        try:
            if exc_type is KeyboardInterrupt:
                self.cancel("Run cancelled by user.")
                return False
            if exc_type:
                self.error(str(exc))
                return False
            if self.status.status == "running":
                self.complete()
            return False
        finally:
            if self._progress:
                self._progress.stop()

    def cancel(self, message: str = "Cancelled.") -> None:
        self.token.cancel()
        self.status.status = "cancelled"
        self.status.stage = "cancelled"
        self.status.message = message
        self.status.elapsed_seconds = round(time.monotonic() - self._started_monotonic, 1)
        self.status.eta_seconds = 0
        self.status.completed_at = utc_now()
        self.storage.update_run(self.status)
        self.storage.log_event(self.status.run_id, self.status.stage, message)
        self._emit()

    def complete(self, message: str = "Complete.") -> None:
        self.status.status = "complete"
        self.status.stage = "complete"
        self.status.message = message
        self.status.progress = 1.0
        self.status.elapsed_seconds = round(time.monotonic() - self._started_monotonic, 1)
        self.status.eta_seconds = 0
        self.status.completed_at = utc_now()
        self.storage.update_run(self.status)
        self.storage.log_event(self.status.run_id, self.status.stage, message)
        self._emit()

    def error(self, message: str) -> None:
        self.status.status = "error"
        self.status.stage = "error"
        self.status.message = message
        self.status.error = message
        self.status.elapsed_seconds = round(time.monotonic() - self._started_monotonic, 1)
        self.status.eta_seconds = None
        self.status.completed_at = utc_now()
        self.storage.update_run(self.status)
        self.storage.log_event(self.status.run_id, self.status.stage, message)
        self._emit()

    def update(
        self,
        stage: str,
        message: str,
        *,
        progress: float | None = None,
        eta_seconds: float | None = None,
        **counts: Any,
    ) -> None:
        self.check_cancelled()
        self.status.status = "running"
        self.status.stage = stage
        self.status.message = message
        if progress is not None:
            self.status.progress = max(0.0, min(1.0, float(progress)))
        self.status.elapsed_seconds = round(time.monotonic() - self._started_monotonic, 1)
        self.status.eta_seconds = self._eta_seconds(eta_seconds)
        self.status.counts = {**self.status.counts, **{key: value for key, value in counts.items() if value is not None}}
        self.storage.update_run(self.status)
        self.storage.log_event(self.status.run_id, stage, message, self.status.counts)
        self._emit()

    def check_cancelled(self) -> None:
        self.token.raise_if_cancelled()
        persisted = self.storage.get_run(self.status.run_id)
        if persisted and persisted.status == "cancelled":
            self.token.cancel()
            self.token.raise_if_cancelled()

    def _emit(self) -> None:
        if self.callback:
            self.callback(self.status)
        if self._progress and self._task_id is not None:
            self._progress.update(
                self._task_id,
                description=f"{self.status.stage}: {self.status.message}",
                completed=int(self.status.progress * 100),
            )

    def _eta_seconds(self, explicit_eta: float | None) -> float | None:
        if explicit_eta is not None:
            return max(0.0, round(float(explicit_eta), 1))
        progress = self.status.progress
        if progress <= 0.01 or progress >= 1:
            return None
        elapsed = time.monotonic() - self._started_monotonic
        estimate = elapsed * (1 - progress) / progress
        return max(0.0, round(estimate, 1))
