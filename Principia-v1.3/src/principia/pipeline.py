from __future__ import annotations

import json
import secrets
import threading
import time
from collections.abc import Callable, Mapping
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .ids import stable_prefixed_id
from .models import PipelineResult, RunStatus, utc_now
from .run import (
    ProgressCallback,
    RunCancelledError,
    RunControlToken,
    StopCallback,
    WeightedProgress,
)

DEFAULT_STAGE_WEIGHTS: dict[str, float] = {
    "retrieval": 0.14,
    "ingestion": 0.08,
    "extraction": 0.43,
    "evidence": 0.08,
    "generation": 0.15,
    "comparison": 0.07,
    "export": 0.05,
}

_TERMINAL_STATES = {"complete", "cancelled", "error"}
_PAUSE_STATES = {"pause_requested", "paused"}


class PipelineStorage(Protocol):
    """Narrow persistence surface required by :class:`PipelineJob`."""

    def create_run(self, status: RunStatus) -> RunStatus: ...

    def update_run(self, status: RunStatus) -> RunStatus: ...

    def get_run(self, run_id: str) -> RunStatus | None: ...

    def log_event(
        self,
        run_id: str,
        stage: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None: ...

    def list_run_events(self, run_id: str) -> list[dict[str, Any]]: ...


class PipelineConfig(BaseModel):
    """High-level pipeline defaults; explicit ``Workspace`` arguments win."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    target_count: int = Field(default=20, ge=1)
    rerank_mode: Literal["bm25", "embedding_rerank"] = "bm25"
    require_target: bool = False
    extraction_model: str = "auto"
    idea_model: str = "auto"
    comparison_model: str = "auto"
    mode: str = "scidialect-evo"
    global_kind_limits: dict[str, int] | None = None
    max_per_work: int | None = Field(default=None, ge=1)
    require_exact_evidence: bool = False
    progress: Literal["auto", "rich", "notebook", "text", "none"] = "auto"
    stage_weights: dict[str, float] = Field(default_factory=lambda: dict(DEFAULT_STAGE_WEIGHTS))

    @field_validator("stage_weights")
    @classmethod
    def valid_stage_weights(cls, value: dict[str, float]) -> dict[str, float]:
        if not value or sum(max(0.0, float(weight)) for weight in value.values()) <= 0:
            raise ValueError("stage_weights must contain at least one positive weight")
        return {str(name): max(0.0, float(weight)) for name, weight in value.items()}

    @classmethod
    def research(cls, **overrides: Any) -> PipelineConfig:
        """Return the concise 50-work, exact 5/5/5 research preset."""

        values: dict[str, Any] = {
            "target_count": 50,
            "rerank_mode": "embedding_rerank",
            "require_target": True,
            "global_kind_limits": {"ideas": 5, "principles": 5, "takeaways": 5},
            "max_per_work": 2,
            "require_exact_evidence": True,
            "mode": "scidialect-evo",
        }
        values.update(overrides)
        return cls(**values)


class PipelineController:
    """Control and progress bridge passed to a background pipeline runner."""

    def __init__(
        self,
        storage: PipelineStorage,
        run_id: str,
        *,
        stage_weights: Mapping[str, float] | None = None,
        callback: ProgressCallback | None = None,
        poll_seconds: float = 0.1,
        state_lock: Any | None = None,
    ) -> None:
        self.storage = storage
        self.run_id = run_id
        self.callback = callback
        self.progress = WeightedProgress(stage_weights or DEFAULT_STAGE_WEIGHTS)
        self._started_monotonic = time.monotonic()
        self._lock = state_lock or threading.RLock()
        self.token = RunControlToken(
            state_loader=self._load_state,
            on_paused=self._mark_paused,
            poll_seconds=poll_seconds,
        )

    @property
    def elapsed_seconds(self) -> float:
        return round(time.monotonic() - self._started_monotonic, 1)

    def checkpoint(self) -> None:
        self.token.checkpoint()

    def wait(self, seconds: float, *, checkpoint: bool = True) -> None:
        self.token.wait(seconds, checkpoint=checkpoint)

    def register_stop_callback(self, callback: StopCallback) -> Callable[[], None]:
        return self.token.register_stop_callback(callback)

    def update(
        self,
        stage: str,
        fraction: float,
        message: str,
        *,
        eta_seconds: float | None = None,
        safe_boundary: bool = True,
        **counts: Any,
    ) -> RunStatus:
        """Persist one monotonic parent update.

        Child heartbeats set ``safe_boundary=False`` so an in-flight provider
        response can finish. The child :class:`RunHandle` performs the boundary
        checkpoint immediately after that response.
        """

        if safe_boundary:
            self.checkpoint()
        else:
            self.token.check_cancelled()
        parent_progress = self.progress.update(stage, fraction)
        with self._lock:
            status = self._require_status()
            if safe_boundary and status.status in _PAUSE_STATES:
                # A cross-process pause can race the first checkpoint. Observe it
                # before writing progress so the request is never overwritten.
                self.token.request_pause()
                self.checkpoint()
                status = self._require_status()
            if status.status not in _PAUSE_STATES:
                status.status = "running"
            status.stage = stage
            status.message = message
            status.progress = max(status.progress, parent_progress)
            status.elapsed_seconds = self.elapsed_seconds
            if eta_seconds is not None:
                status.eta_seconds = max(0.0, float(eta_seconds))
            status.counts = {
                **status.counts,
                **{key: value for key, value in counts.items() if value is not None},
            }
            self.storage.update_run(status)
            self.storage.log_event(self.run_id, stage, message, status.counts)
            self._emit(status)
            return status

    def child_callback(self, stage: str) -> ProgressCallback:
        """Map one child ``RunStatus`` onto a weighted parent stage."""

        def report(child: RunStatus) -> None:
            reserved = {
                "safe_boundary",
                "eta_seconds",
                "child_run_id",
                "child_stage",
                "child_status",
            }
            child_counts = {
                key: value for key, value in child.counts.items() if key not in reserved
            }
            self.update(
                stage,
                child.progress,
                child.message,
                eta_seconds=child.eta_seconds,
                safe_boundary=False,
                child_run_id=child.run_id,
                child_stage=child.stage,
                child_status=child.status,
                **child_counts,
            )

        return report

    def complete_stage(self, stage: str, message: str, **counts: Any) -> RunStatus:
        return self.update(stage, 1.0, message, **counts)

    def event(self, stage: str, message: str, **payload: Any) -> None:
        self.storage.log_event(self.run_id, stage, message, payload)

    def _load_state(self) -> str | None:
        status = self.storage.get_run(self.run_id)
        return status.status if status else None

    def _mark_paused(self) -> None:
        with self._lock:
            status = self._require_status()
            if status.status not in _PAUSE_STATES:
                return
            status.status = "paused"
            status.message = "Paused at a safe boundary."
            status.eta_seconds = None
            status.elapsed_seconds = self.elapsed_seconds
            self.storage.update_run(status)
            self.storage.log_event(self.run_id, "control", status.message)
            self._emit(status)

    def _require_status(self) -> RunStatus:
        status = self.storage.get_run(self.run_id)
        if status is None:
            raise KeyError(f"Unknown pipeline run: {self.run_id}")
        return status

    def _emit(self, status: RunStatus) -> None:
        if self.callback is not None:
            self.callback(status)


PipelineRunner = Callable[[PipelineController], PipelineResult]
ResultLoader = Callable[[str], PipelineResult | None]


class PipelineJob:
    """Persisted, cooperatively controllable background pipeline handle.

    ``Workspace.start`` should construct jobs with :meth:`start`. Its runner
    receives a :class:`PipelineController`, passes ``controller.token`` to all
    existing staged APIs, and uses ``controller.child_callback(stage)`` for
    progress forwarding.
    """

    def __init__(
        self,
        storage: PipelineStorage,
        run_id: str,
        *,
        thread: threading.Thread | None = None,
        controller: PipelineController | None = None,
        result_loader: ResultLoader | None = None,
        state_lock: Any | None = None,
    ) -> None:
        self.storage = storage
        self.run_id = run_id
        self._thread = thread
        self._controller = controller
        self._result_loader = result_loader
        self._state_lock = state_lock or threading.RLock()
        self._result: PipelineResult | None = None
        self._exception: BaseException | None = None
        self._done = threading.Event()

    @classmethod
    def start(
        cls,
        storage: PipelineStorage,
        runner: PipelineRunner,
        *,
        operation: str = "workspace.pipeline",
        config: PipelineConfig | None = None,
        callback: ProgressCallback | None = None,
        result_loader: ResultLoader | None = None,
        daemon: bool = True,
        poll_seconds: float = 0.1,
    ) -> PipelineJob:
        selected = config or PipelineConfig()
        run_id = stable_prefixed_id(
            "RUN", operation, utc_now(), time.time_ns(), secrets.token_hex(8)
        )
        status = RunStatus(
            run_id=run_id,
            operation=operation,
            status="queued",
            stage="queued",
            message="Pipeline queued.",
            counts={"pipeline_config": selected.model_dump(mode="json")},
        )
        storage.create_run(status)
        storage.log_event(run_id, "queued", status.message, status.counts)
        state_lock = threading.RLock()
        controller = PipelineController(
            storage,
            run_id,
            stage_weights=selected.stage_weights,
            callback=callback,
            poll_seconds=poll_seconds,
            state_lock=state_lock,
        )
        job = cls(
            storage,
            run_id,
            controller=controller,
            result_loader=result_loader,
            state_lock=state_lock,
        )
        thread = threading.Thread(
            target=job._run,
            args=(runner,),
            name=f"principia-{run_id}",
            daemon=daemon,
        )
        job._thread = thread
        thread.start()
        return job

    @classmethod
    def attach(
        cls,
        storage: PipelineStorage,
        run_id: str,
        *,
        result_loader: ResultLoader | None = None,
    ) -> PipelineJob:
        if storage.get_run(run_id) is None:
            raise KeyError(f"Unknown pipeline run: {run_id}")
        return cls(storage, run_id, result_loader=result_loader)

    def status(self) -> RunStatus:
        status = self.storage.get_run(self.run_id)
        if status is None:
            raise KeyError(f"Unknown pipeline run: {self.run_id}")
        return status

    def events(self) -> list[dict[str, Any]]:
        return self.storage.list_run_events(self.run_id)

    def pause(self) -> RunStatus:
        with self._state_lock:
            status = self.status()
            if status.status in _TERMINAL_STATES or status.status in _PAUSE_STATES:
                return status
            status.status = "pause_requested"
            status.message = "Pause requested; finishing the current safe unit."
            status.eta_seconds = None
            self.storage.update_run(status)
            self.storage.log_event(self.run_id, "control", status.message)
            if self._controller is not None:
                self._controller.token.request_pause()
            return status

    def resume(self) -> RunStatus:
        with self._state_lock:
            status = self.status()
            if status.status not in _PAUSE_STATES:
                return status
            status.status = "running"
            status.message = "Pipeline resumed."
            self.storage.update_run(status)
            self.storage.log_event(self.run_id, "control", status.message)
            if self._controller is not None:
                self._controller.token.resume()
            return status

    def stop(self) -> RunStatus:
        with self._state_lock:
            status = self.status()
            if status.status in _TERMINAL_STATES:
                return status
            status.status = "cancel_requested"
            status.message = "Stop requested; no new work will be scheduled."
            status.eta_seconds = None
            self.storage.update_run(status)
            self.storage.log_event(self.run_id, "control", status.message)
            if self._controller is not None:
                self._controller.token.cancel()
            return status

    def result(self, timeout: float | None = None) -> PipelineResult:
        deadline = None if timeout is None else time.monotonic() + max(0.0, timeout)
        while True:
            status = self.status()
            if status.status in _TERMINAL_STATES:
                break
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                raise TimeoutError(f"Pipeline {self.run_id} did not finish before timeout")
            self._done.wait(timeout=min(0.1, remaining) if remaining is not None else 0.1)

        if status.status == "cancelled":
            raise RunCancelledError(status.message or f"Pipeline {self.run_id} was cancelled")
        if status.status == "error":
            if self._exception is not None:
                raise RuntimeError(status.error or status.message) from self._exception
            raise RuntimeError(status.error or status.message or f"Pipeline {self.run_id} failed")
        if self._result is not None:
            return self._result
        if self._result_loader is not None:
            loaded = self._result_loader(self.run_id)
            if loaded is not None:
                return loaded
        raise RuntimeError(
            f"Pipeline {self.run_id} completed, but its result is unavailable in this process. "
            "Load the exported result from the workspace instead."
        )

    def display(self, *, mode: str = "auto") -> Any:
        """Display live notebook controls when available, otherwise text status."""

        from .progress import display_pipeline_job

        return display_pipeline_job(self, mode=mode)

    def _run(self, runner: PipelineRunner) -> None:
        assert self._controller is not None
        try:
            with self._state_lock:
                status = self.status()
                if status.status == "cancel_requested":
                    raise RunCancelledError("Pipeline stopped before it started")
                if status.status not in _PAUSE_STATES:
                    status.status = "running"
                    status.stage = "starting"
                    status.message = "Pipeline started."
                    self.storage.update_run(status)
                    self.storage.log_event(self.run_id, status.stage, status.message)
            self._controller.checkpoint()
            result = runner(self._controller)
            self._controller.checkpoint()
            self._result = result
            with self._state_lock:
                status = self.status()
                status.status = "complete"
                status.stage = "complete"
                status.message = "Pipeline complete."
                status.progress = 1.0
                status.elapsed_seconds = self._controller.elapsed_seconds
                status.eta_seconds = 0
                status.completed_at = utc_now()
                self.storage.update_run(status)
                self.storage.log_event(self.run_id, status.stage, status.message)
        except (RunCancelledError, KeyboardInterrupt) as exc:
            self._exception = exc
            with self._state_lock:
                status = self.status()
                status.status = "cancelled"
                status.stage = "cancelled"
                status.message = "Pipeline cancelled; completed checkpoints were preserved."
                status.elapsed_seconds = self._controller.elapsed_seconds
                status.eta_seconds = 0
                status.completed_at = utc_now()
                self.storage.update_run(status)
                self.storage.log_event(self.run_id, status.stage, status.message)
        except BaseException as exc:  # noqa: BLE001
            self._exception = exc
            with self._state_lock:
                status = self.status()
                status.status = "error"
                status.stage = "error"
                status.message = str(exc) or exc.__class__.__name__
                status.error = status.message
                status.elapsed_seconds = self._controller.elapsed_seconds
                status.eta_seconds = None
                status.completed_at = utc_now()
                self.storage.update_run(status)
                self.storage.log_event(self.run_id, status.stage, status.message)
        finally:
            self._done.set()


def list_pipeline_runs(storage: Any, *, limit: int = 50) -> list[RunStatus]:
    """List recent persisted runs without requiring a storage-schema extension."""

    with storage.connect() as conn:
        rows = conn.execute(
            "SELECT payload_json FROM runs ORDER BY updated_at DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
    output: list[RunStatus] = []
    for row in rows:
        raw = row["payload_json"] if hasattr(row, "keys") else row[0]
        try:
            output.append(RunStatus.model_validate(json.loads(str(raw))))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    return output
