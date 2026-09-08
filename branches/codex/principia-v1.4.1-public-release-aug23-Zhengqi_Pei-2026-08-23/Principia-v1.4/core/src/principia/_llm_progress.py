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
    stop_callback: Callable[[], None] | None = None,
) -> T:
    # A pause is honored *before* starting a paid request. During a request we
    # only observe stop, allowing pause to checkpoint the completed response and
    # block the following call instead of discarding paid work.
    run.checkpoint()
    run.update(
        stage,
        message,
        progress=progress_start,
        eta_seconds=estimated_seconds,
        checkpoint=False,
    )
    results: queue.Queue[tuple[bool, T | BaseException]] = queue.Queue(maxsize=1)

    def worker() -> None:
        try:
            results.put((True, call()))
        except BaseException as exc:  # noqa: BLE001
            results.put((False, exc))

    unregister = (
        run.register_stop_callback(stop_callback) if stop_callback is not None else lambda: None
    )
    thread = threading.Thread(target=worker, daemon=True, name=f"principia-provider-{stage}")
    started = time.monotonic()
    last_progress = progress_start
    thread.start()
    try:
        while True:
            try:
                ok, value = results.get(timeout=max(0.01, heartbeat_seconds))
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
                    checkpoint=False,
                    llm_wait_seconds=int(elapsed),
                )
                continue
            if ok:
                run.update(
                    stage,
                    "Provider response received; parsing output.",
                    progress=progress_end,
                    eta_seconds=0,
                    checkpoint=False,
                )
                run.checkpoint()
                return value  # type: ignore[return-value]
            if isinstance(value, BaseException):
                raise value
            raise RuntimeError(str(value))
    finally:
        unregister()


def _bounded_stage_progress(elapsed: float, estimated_seconds: float) -> float:
    if estimated_seconds <= 0:
        return 0.5
    linear = elapsed / estimated_seconds
    if linear <= 0.85:
        return min(0.85, linear)
    return min(0.96, 0.85 + (linear - 0.85) * 0.12)
