"""Cooperative task cancellation across discovery, HTTP and child processes.

Cancellation is control flow, not an analysis failure eligible for retry/fallback.
The owning worker must join its children before publishing its terminal state.
"""
from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from threading import Event
from typing import Any

import httpx


class TaskCancelled(BaseException):
    """Unwind to the task owner without entering ordinary error fallbacks."""


_current: ContextVar[Event | None] = ContextVar("principia_cancellation", default=None)


@contextmanager
def cancellation_scope(event: Event) -> Iterator[None]:
    token = _current.set(event)
    try:
        yield
    finally:
        _current.reset(token)


def check_cancelled() -> None:
    event = _current.get()
    if event is not None and event.is_set():
        raise TaskCancelled()


def cancellable_wait(seconds: float) -> None:
    event = _current.get()
    (event if event is not None else Event()).wait(seconds)
    check_cancelled()


def http_request(client: httpx.Client, method: str, url: str, *, transport: httpx.BaseTransport | None = None, async_options: dict[str, Any] | None = None, **kwargs: Any) -> httpx.Response:
    """Close an in-flight network request when its discovery is stopped.

    Ordinary callers and custom synchronous transports retain the sync client.
    A scoped network request owns its async client and always cancels and joins
    the request before returning; there is no abandoned background HTTP thread.
    """
    check_cancelled()
    if _current.get() is None or (transport is not None and not isinstance(transport, httpx.AsyncBaseTransport)):
        response = client.request(method, url, **kwargs)
        check_cancelled()
        return response

    async def request() -> httpx.Response:
        async_transport = transport if isinstance(transport, httpx.AsyncBaseTransport) else None
        async with httpx.AsyncClient(timeout=client.timeout, transport=async_transport, follow_redirects=client.follow_redirects, headers=client.headers, **(async_options or {})) as active:
            task = asyncio.create_task(active.request(method, url, **kwargs))
            try:
                while not task.done():
                    check_cancelled()
                    await asyncio.wait({task}, timeout=0.1)
                check_cancelled()
                return task.result()
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await task

    return asyncio.run(request())


class DiscoveryControl:
    """Bridge scoped discovery cancellation into the shared metadata retriever."""

    join_on_cancel = True

    def __init__(self, event: Event) -> None:
        self.event = event

    def cancel(self) -> None:
        self.event.set()

    @property
    def cancelled(self) -> bool:
        return self.event.is_set()

    def check_cancelled(self) -> None:
        if self.cancelled:
            raise TaskCancelled()

    raise_if_cancelled = check_cancelled
    checkpoint = check_cancelled

    def wait(self, seconds: float, **kwargs: Any) -> None:
        self.event.wait(seconds)
        self.check_cancelled()

    def fetch_bytes(self, url: str, timeout: float, *, verify: Any, headers: dict[str, str]) -> bytes:
        # Source workers receive this explicit control, not a thread-local copy.
        with cancellation_scope(self.event), httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            response = http_request(client, "GET", url, async_options={"verify": verify})
            response.raise_for_status()
            return response.content


def current_control() -> DiscoveryControl | None:
    event = _current.get()
    return DiscoveryControl(event) if event is not None else None
