from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from typing import TypeVar

from .run import RunHandle

T = TypeVar("T")


def call_with_progress(
    run: RunHandle,
    *,
    stage: str,
    message: str,
    progress_start: float,
    progress_end: float,
    estimated_seconds: float,
    call: Callable[[], T],
    heartbeat_seconds: float = 2.0,
) -> T:
    results: queue.Queue[tuple[bool, T | BaseException]] = queue.Queue(maxsize=1)

    def worker() -> None:
        try:
            results.put((True, call()))
        except BaseException as exc:  # noqa: BLE001
            results.put((False, exc))

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    started = time.monotonic()
    last_progress = progress_start
    run.update(stage, message, progress=progress_start, eta_seconds=estimated_seconds)
    while True:
        try:
            ok, value = results.get(timeout=heartbeat_seconds)
        except queue.Empty:
            run.check_cancelled()
            elapsed = time.monotonic() - started
            stage_progress = _bounded_stage_progress(elapsed, estimated_seconds)
            next_progress = progress_start + (progress_end - progress_start) * stage_progress
            last_progress = max(last_progress, min(progress_end - 0.01, next_progress))
            eta = max(0.0, estimated_seconds - elapsed)
            run.update(
                stage,
                f"{message} Waiting for provider response ({int(elapsed)}s elapsed).",
                progress=last_progress,
                eta_seconds=eta,
                llm_wait_seconds=int(elapsed),
            )
            continue
        if ok:
            run.update(stage, "Provider response received; parsing output.", progress=progress_end, eta_seconds=0)
            return value  # type: ignore[return-value]
        if isinstance(value, BaseException):
            raise value
        raise RuntimeError(str(value))


def _bounded_stage_progress(elapsed: float, estimated_seconds: float) -> float:
    if estimated_seconds <= 0:
        return 0.5
    linear = elapsed / estimated_seconds
    if linear <= 0.85:
        return min(0.85, linear)
    return min(0.96, 0.85 + (linear - 0.85) * 0.12)
