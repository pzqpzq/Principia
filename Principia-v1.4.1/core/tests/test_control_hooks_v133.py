from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

import httpx
import pytest

import principia.llm as llm_module
from principia.llm import LLMClient, LLMConfig
from principia.run import RunCancelledError, RunControlToken
from principia_retrieval.models import QueryPlan, RetrievalConfig
from principia_retrieval.ranking import embed_texts_cached
from principia_retrieval.retriever import WorkRetriever
from principia_retrieval.sources import fetch_source_with_report


class BoundaryStop(RuntimeError):
    pass


class StopOnWaitToken:
    def __init__(self) -> None:
        self.waits: list[tuple[float, bool]] = []

    def checkpoint(self) -> None:
        return None

    def check_cancelled(self) -> None:
        return None

    def wait(self, seconds: float, *, checkpoint: bool = True) -> None:
        self.waits.append((seconds, checkpoint))
        raise BoundaryStop("stopped during retry wait")

    def register_stop_callback(self, callback: Callable[[], None]) -> Callable[[], None]:
        return lambda: None


def test_source_retry_backoff_is_interruptible_and_does_not_start_another_call() -> None:
    calls = 0
    token = StopOnWaitToken()

    def failing_source(query: str, limit: int, timeout: float) -> list[dict[str, Any]]:
        nonlocal calls
        calls += 1
        raise TimeoutError("temporary source timeout")

    with pytest.raises(BoundaryStop, match="retry wait"):
        fetch_source_with_report(
            "fixture",
            failing_source,
            "quantum sensing",
            5,
            10,
            max_retries=5,
            backoff_seconds=30,
            control_token=token,
        )

    assert calls == 1
    assert token.waits == [(8.0, True)]


def test_embedding_batch_pause_boundary_freezes_new_provider_calls() -> None:
    class PauseAfterResponse:
        paused = False

        def checkpoint(self) -> None:
            if self.paused:
                raise BoundaryStop("paused after completed embedding batch")

        def check_cancelled(self) -> None:
            return None

    token = PauseAfterResponse()

    class Embeddings:
        calls = 0

        def embed(
            self,
            texts: list[str],
            *,
            control_token: Any | None = None,
            **_: Any,
        ) -> list[list[float]]:
            self.calls += 1
            assert control_token is token
            token.paused = True
            return [[1.0, float(index + 1)] for index, _ in enumerate(texts)]

    client = Embeddings()
    with pytest.raises(BoundaryStop, match="paused"):
        embed_texts_cached(
            ["one", "two", "three", "four"],
            client,
            model="fixture",
            dimensions=2,
            batch_size=2,
            timeout=10,
            cache={},
            control_token=token,
        )

    assert client.calls == 1


def test_llm_retry_wait_is_interruptible(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    class FailingClient:
        def __init__(self, **_: Any) -> None:
            pass

        def post(self, *_: Any, **__: Any) -> Any:
            nonlocal calls
            calls += 1
            raise httpx.TimeoutException("provider timed out")

        def close(self) -> None:
            return None

    monkeypatch.setattr(llm_module.httpx, "Client", FailingClient)
    token = StopOnWaitToken()
    client = LLMClient(
        LLMConfig(
            provider="custom",
            model="fixture",
            api_key="local-test-key",
            base_url="https://provider.invalid/v1",
            max_retries=4,
        )
    )

    with pytest.raises(BoundaryStop, match="retry wait"):
        client.chat_text("system", "user", control_token=token)

    assert calls == 1
    assert len(token.waits) == 1


def test_llm_stop_closes_active_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    request_started = threading.Event()
    transport_closed = threading.Event()

    class BlockingClient:
        def __init__(self, **_: Any) -> None:
            pass

        def post(self, *_: Any, **__: Any) -> Any:
            request_started.set()
            if not transport_closed.wait(timeout=5):
                raise AssertionError("active transport was not closed")
            raise httpx.ReadError("transport closed by stop")

        def close(self) -> None:
            transport_closed.set()

    monkeypatch.setattr(llm_module.httpx, "Client", BlockingClient)
    token = RunControlToken(poll_seconds=0.01)
    client = LLMClient(
        LLMConfig(
            provider="custom",
            model="fixture",
            api_key="local-test-key",
            base_url="https://provider.invalid/v1",
            max_retries=3,
        )
    )
    failures: list[BaseException] = []

    def invoke() -> None:
        try:
            client.chat_text("system", "user", control_token=token)
        except BaseException as exc:  # noqa: BLE001 - asserted below
            failures.append(exc)

    worker = threading.Thread(target=invoke, daemon=True)
    worker.start()
    assert request_started.wait(timeout=1)
    started = time.monotonic()
    token.cancel()
    worker.join(timeout=1)

    assert not worker.is_alive()
    assert time.monotonic() - started < 1
    assert transport_closed.is_set()
    assert len(failures) == 1
    assert isinstance(failures[0], RunCancelledError)
    assert client.usage_totals()["calls"] == 1


def test_retriever_stop_interrupts_as_completed_wait_and_active_sources() -> None:
    started = threading.Event()
    active_count = 0
    active_lock = threading.Lock()

    def blocking_source(
        query: str,
        limit: int,
        timeout: float,
        *,
        control_token: Any | None = None,
    ) -> list[dict[str, Any]]:
        nonlocal active_count
        released = threading.Event()
        unregister = control_token.register_stop_callback(released.set)
        with active_lock:
            active_count += 1
            if active_count == 2:
                started.set()
        try:
            released.wait(timeout=5)
            control_token.check_cancelled()
            return []
        finally:
            unregister()

    token = RunControlToken(poll_seconds=0.01)
    retriever = WorkRetriever(
        sources={"one": blocking_source, "two": blocking_source},
        config=RetrievalConfig(
            use_llm_planner=False,
            max_queries=1,
            source_max_retries=0,
            source_min_interval_seconds={},
            max_retrieval_rounds=1,
        ),
    )
    failures: list[BaseException] = []

    def search() -> None:
        try:
            retriever.search(
                "uncertainty-aware sensing",
                target_count=2,
                control_token=token,
            )
        except BaseException as exc:  # noqa: BLE001 - asserted below
            failures.append(exc)

    worker = threading.Thread(target=search, daemon=True)
    worker.start()
    assert started.wait(timeout=1)
    started_at = time.monotonic()
    token.cancel()
    worker.join(timeout=1)

    assert not worker.is_alive()
    assert time.monotonic() - started_at < 1
    assert len(failures) == 1
    assert isinstance(failures[0], RunCancelledError)


def test_control_hook_additions_preserve_legacy_embedding_adapter() -> None:
    class LegacyEmbedding:
        def embed(self, texts: list[str]) -> list[list[float]]:
            return [[1.0, float(index)] for index, _ in enumerate(texts)]

    vectors = embed_texts_cached(
        ["query", "document"],
        LegacyEmbedding(),
        model="legacy",
        dimensions=2,
        batch_size=8,
        timeout=10,
        cache={},
    )
    assert vectors == [[1.0, 0.0], [1.0, 1.0]]
    assert QueryPlan(goal_text="goal", search_queries=["goal"]).goal_text == "goal"
