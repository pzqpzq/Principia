from __future__ import annotations

import secrets
import threading
import time
from collections.abc import Callable, Mapping
from contextlib import suppress
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
StopCallback = Callable[[], None]

_TERMINAL_STATES = {"cancelled", "complete", "error"}
_PAUSE_STATES = {"pause_requested", "paused"}
_CANCEL_STATES = {"cancel_requested", "cancelled"}


class RunCancelledError(RuntimeError):
    """Raised when a cooperative Principia run is stopped.

    This deliberately differs from :class:`KeyboardInterrupt`: applications can
    catch a cancelled background job without also swallowing a user's process-
    level interrupt.
    """


class RunControlToken(CancelToken):
    """Thread-safe pause/stop token shared by a parent pipeline and child runs.

    ``state_loader`` makes the token process-cooperative as well as thread-
    cooperative: a CLI command can update the persisted parent run and the
    worker observes that request at its next control check.
    """

    def __init__(
        self,
        *,
        state_loader: Callable[[], str | None] | None = None,
        on_paused: Callable[[], None] | None = None,
        poll_seconds: float = 0.1,
    ) -> None:
        super().__init__()
        self._condition = threading.Condition(threading.RLock())
        self._pause_requested = False
        self._stop_requested = False
        self._paused_notified = False
        self._state_loader = state_loader
        self._on_paused = on_paused
        self._poll_seconds = max(0.01, float(poll_seconds))
        self._stop_callbacks: list[StopCallback] = []
        self._callbacks_invoked = False

    @property
    def cancelled(self) -> bool:
        with self._condition:
            return self._stop_requested or super().cancelled

    @property
    def pause_requested(self) -> bool:
        with self._condition:
            return self._pause_requested

    def request_pause(self) -> None:
        with self._condition:
            if not self._stop_requested:
                self._pause_requested = True
                self._condition.notify_all()

    def resume(self) -> None:
        with self._condition:
            self._pause_requested = False
            self._paused_notified = False
            self._condition.notify_all()

    def cancel(self) -> None:
        callbacks: list[StopCallback]
        with self._condition:
            if self._stop_requested:
                return
            self._stop_requested = True
            self._pause_requested = False
            super().cancel()
            callbacks = self._take_stop_callbacks_locked()
            self._condition.notify_all()
        _invoke_stop_callbacks(callbacks)

    def register_stop_callback(self, callback: StopCallback) -> Callable[[], None]:
        """Register best-effort active-I/O cancellation and return an unregister hook."""

        invoke_now = False
        with self._condition:
            if self._stop_requested:
                invoke_now = True
            elif callback not in self._stop_callbacks:
                self._stop_callbacks.append(callback)
        if invoke_now:
            _invoke_stop_callbacks([callback])

        def unregister() -> None:
            with self._condition:
                with suppress(ValueError):
                    self._stop_callbacks.remove(callback)

        return unregister

    def check_cancelled(self) -> None:
        """Observe a stop request without blocking for pause.

        Provider heartbeats use this method so a pause lets the in-flight paid
        request finish. The next :meth:`checkpoint` performs the actual pause.
        """

        self._sync_persisted_state(allow_resume=False)
        if self.cancelled:
            raise RunCancelledError("Principia run was cancelled")

    def raise_if_cancelled(self) -> None:
        self.check_cancelled()

    def checkpoint(self) -> None:
        """Block at a safe boundary while paused, or raise when stopped."""

        while True:
            self._sync_persisted_state(allow_resume=True)
            notify_paused = False
            with self._condition:
                if self._stop_requested or super().cancelled:
                    raise RunCancelledError("Principia run was cancelled")
                if not self._pause_requested:
                    return
                if not self._paused_notified:
                    self._paused_notified = True
                    notify_paused = True
            if notify_paused and self._on_paused is not None:
                self._on_paused()
            with self._condition:
                self._condition.wait(timeout=self._poll_seconds)

    def wait(self, seconds: float, *, checkpoint: bool = True) -> None:
        """Wait without making cancellation wait for a long sleep/backoff."""

        deadline = time.monotonic() + max(0.0, float(seconds))
        while True:
            if checkpoint:
                self.checkpoint()
            else:
                self.check_cancelled()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            with self._condition:
                self._condition.wait(timeout=min(self._poll_seconds, remaining))

    def _sync_persisted_state(self, *, allow_resume: bool) -> None:
        if self._state_loader is None:
            return
        state = self._state_loader()
        if state in _CANCEL_STATES:
            self.cancel()
        elif state in _PAUSE_STATES:
            self.request_pause()
        elif allow_resume and state == "running" and self.pause_requested:
            self.resume()

    def _take_stop_callbacks_locked(self) -> list[StopCallback]:
        if self._callbacks_invoked:
            return []
        self._callbacks_invoked = True
        callbacks = list(reversed(self._stop_callbacks))
        self._stop_callbacks.clear()
        return callbacks


class WeightedProgress:
    """Combine child-stage progress into one monotonic parent value."""

    def __init__(self, weights: Mapping[str, float]) -> None:
        positive = {str(name): max(0.0, float(weight)) for name, weight in weights.items()}
        total = sum(positive.values())
        if not positive or total <= 0:
            raise ValueError("At least one positive progress-stage weight is required")
        self.weights = {name: weight / total for name, weight in positive.items()}
        self._fractions = {name: 0.0 for name in self.weights}
        self._progress = 0.0
        self._lock = threading.Lock()

    @property
    def value(self) -> float:
        with self._lock:
            return self._progress

    def update(self, stage: str, fraction: float) -> float:
        if stage not in self.weights:
            raise KeyError(f"Unknown progress stage: {stage}")
        bounded = max(0.0, min(1.0, float(fraction)))
        with self._lock:
            self._fractions[stage] = max(self._fractions[stage], bounded)
            combined = sum(self.weights[name] * value for name, value in self._fractions.items())
            self._progress = max(self._progress, min(1.0, combined))
            return self._progress


class RunHandle:
    def __init__(
        self,
        storage: WorkspaceStorage,
        operation: str,
        *,
        callback: ProgressCallback | None = None,
        token: CancelToken | None = None,
        show_progress: bool = False,
        run_id: str | None = None,
        parent_run_id: str = "",
        control_poll_seconds: float = 0.1,
    ) -> None:
        self.storage = storage
        self.token = token or RunControlToken(poll_seconds=control_poll_seconds)
        self.callback = callback
        self.show_progress = show_progress
        self.status = RunStatus(
            run_id=run_id
            or stable_prefixed_id(
                "RUN", operation, utc_now(), time.time_ns(), secrets.token_hex(8)
            ),
            operation=operation,
            status="running",
            stage="starting",
            message="Starting.",
            counts={"parent_run_id": parent_run_id} if parent_run_id else {},
        )
        self._started_monotonic = time.monotonic()
        self._control_poll_seconds = max(0.01, float(control_poll_seconds))
        self._stop_callbacks: list[StopCallback] = []
        self._stop_callbacks_invoked = False
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
            if exc_type and issubclass(exc_type, (KeyboardInterrupt, RunCancelledError)):
                self.cancel("Run cancelled by user.")
                return False
            if exc_type:
                self.error(str(exc))
                return False
            if self.status.status not in _TERMINAL_STATES:
                self.complete()
            return False
        finally:
            if self._progress:
                self._progress.stop()

    def register_stop_callback(self, callback: StopCallback) -> Callable[[], None]:
        if isinstance(self.token, RunControlToken):
            return self.token.register_stop_callback(callback)
        self._stop_callbacks.append(callback)

        def unregister() -> None:
            with suppress(ValueError):
                self._stop_callbacks.remove(callback)

        return unregister

    def request_pause(
        self, message: str = "Pause requested; finishing the current safe unit."
    ) -> None:
        if self.status.status in _TERMINAL_STATES:
            return
        self.status.status = "pause_requested"
        self.status.message = message
        self._persist_event("control", message)
        if isinstance(self.token, RunControlToken):
            self.token.request_pause()
        self._emit()

    def resume(self, message: str = "Run resumed.") -> None:
        if self.status.status not in _PAUSE_STATES:
            return
        if isinstance(self.token, RunControlToken):
            self.token.resume()
        self.status.status = "running"
        self.status.message = message
        self._persist_event("control", message)
        self._emit()

    def request_stop(self, message: str = "Stop requested.") -> None:
        if self.status.status in _TERMINAL_STATES:
            return
        self.status.status = "cancel_requested"
        self.status.message = message
        self._persist_event("control", message)
        self.token.cancel()
        self._invoke_stop_callbacks()
        self._emit()

    def cancel(self, message: str = "Cancelled.") -> None:
        self.token.cancel()
        self._invoke_stop_callbacks()
        self.status.status = "cancelled"
        self.status.stage = "cancelled"
        self.status.message = message
        self.status.elapsed_seconds = round(time.monotonic() - self._started_monotonic, 1)
        self.status.eta_seconds = 0
        self.status.completed_at = utc_now()
        self._persist_event(self.status.stage, message)
        self._emit()

    def complete(self, message: str = "Complete.") -> None:
        self.status.status = "complete"
        self.status.stage = "complete"
        self.status.message = message
        self.status.progress = 1.0
        self.status.elapsed_seconds = round(time.monotonic() - self._started_monotonic, 1)
        self.status.eta_seconds = 0
        self.status.completed_at = utc_now()
        self._persist_event(self.status.stage, message)
        self._emit()

    def error(self, message: str) -> None:
        self.status.status = "error"
        self.status.stage = "error"
        self.status.message = message
        self.status.error = message
        self.status.elapsed_seconds = round(time.monotonic() - self._started_monotonic, 1)
        self.status.eta_seconds = None
        self.status.completed_at = utc_now()
        self._persist_event(self.status.stage, message)
        self._emit()

    def update(
        self,
        stage: str,
        message: str,
        *,
        progress: float | None = None,
        eta_seconds: float | None = None,
        checkpoint: bool = True,
        **counts: Any,
    ) -> None:
        if checkpoint:
            self.checkpoint()
        else:
            self.check_cancelled()
        self.status.status = "running"
        self.status.stage = stage
        self.status.message = message
        if progress is not None:
            bounded = max(0.0, min(1.0, float(progress)))
            self.status.progress = max(self.status.progress, bounded)
        self.status.elapsed_seconds = round(time.monotonic() - self._started_monotonic, 1)
        self.status.eta_seconds = self._eta_seconds(eta_seconds)
        self.status.counts = {
            **self.status.counts,
            **{key: value for key, value in counts.items() if value is not None},
        }
        self._persist_event(stage, message, self.status.counts)
        self._emit()

    def check_cancelled(self) -> None:
        persisted = self.storage.get_run(self.status.run_id)
        if persisted and persisted.status in _CANCEL_STATES:
            self.token.cancel()
            self._invoke_stop_callbacks()
        try:
            if isinstance(self.token, RunControlToken):
                self.token.check_cancelled()
            else:
                self.token.raise_if_cancelled()
        except KeyboardInterrupt as exc:
            raise RunCancelledError("Principia run was cancelled") from exc

    def checkpoint(self) -> None:
        """Enter a safe pause boundary before scheduling the next work unit."""

        while True:
            self.check_cancelled()
            persisted = self.storage.get_run(self.status.run_id)
            persisted_state = persisted.status if persisted else self.status.status
            if isinstance(self.token, RunControlToken):
                self.token.checkpoint()
                return
            if persisted_state not in _PAUSE_STATES:
                return
            if persisted_state == "pause_requested":
                self.status.status = "paused"
                self.status.message = "Paused at a safe boundary."
                self._persist_event("control", self.status.message)
                self._emit()
            time.sleep(self._control_poll_seconds)

    def interruptible_wait(self, seconds: float, *, checkpoint: bool = True) -> None:
        if isinstance(self.token, RunControlToken):
            self.token.wait(seconds, checkpoint=checkpoint)
            return
        deadline = time.monotonic() + max(0.0, float(seconds))
        while True:
            if checkpoint:
                self.checkpoint()
            else:
                self.check_cancelled()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(self._control_poll_seconds, remaining))

    def _invoke_stop_callbacks(self) -> None:
        if self._stop_callbacks_invoked:
            return
        self._stop_callbacks_invoked = True
        callbacks = list(reversed(self._stop_callbacks))
        self._stop_callbacks.clear()
        _invoke_stop_callbacks(callbacks)

    def _persist_event(
        self,
        stage: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.storage.update_run(self.status)
        self.storage.log_event(self.status.run_id, stage, message, payload)

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


def _invoke_stop_callbacks(callbacks: list[StopCallback]) -> None:
    for callback in callbacks:
        with suppress(Exception):
            callback()
