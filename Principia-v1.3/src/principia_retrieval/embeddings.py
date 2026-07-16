from __future__ import annotations

import hashlib
import os
import ssl
import threading
from collections.abc import Sequence
from typing import Any

import certifi
import httpx

from .constants import USER_AGENT
from .models import (
    control_check_cancelled,
    control_checkpoint,
    control_register_stop_callback,
    control_wait,
)

DEFAULT_EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-4B"
DEFAULT_EMBEDDING_DIMENSIONS = 1024


class SiliconFlowEmbeddingClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = DEFAULT_EMBEDDING_MODEL,
        dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS,
        timeout: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        self.api_key = (
            api_key or os.getenv("SILICONFLOW_API_KEY") or os.getenv("PRINCIPIA_API_KEY") or ""
        )
        self.base_url = (
            base_url or os.getenv("PRINCIPIA_LLM_BASE_URL") or "https://api.siliconflow.cn/v1"
        ).rstrip("/")
        self.model = model
        self.dimensions = int(dimensions or 0)
        self.timeout = float(timeout or 30.0)
        self.max_retries = max(0, int(max_retries or 0))
        self._cache: dict[str, list[float]] = {}
        self._cache_lock = threading.Lock()
        self._max_cache_entries = 4096

    def available(self) -> bool:
        return bool(self.api_key and self.base_url)

    def embed(
        self,
        texts: Sequence[str],
        *,
        model: str | None = None,
        dimensions: int | None = None,
        timeout: float | None = None,
        control_token: Any | None = None,
    ) -> list[list[float]]:
        control_checkpoint(control_token)
        inputs = [str(text or "") for text in texts]
        if not inputs:
            return []
        if not self.available():
            raise RuntimeError("No SiliconFlow API key configured for embedding rerank.")
        resolved_model = model or self.model
        resolved_dimensions = int(dimensions if dimensions is not None else self.dimensions)
        keys = [embedding_cache_key(resolved_model, resolved_dimensions, text) for text in inputs]
        missing_keys: list[str] = []
        missing_inputs: list[str] = []
        with self._cache_lock:
            for key, text in zip(keys, inputs, strict=True):
                if key not in self._cache and key not in missing_keys:
                    missing_keys.append(key)
                    missing_inputs.append(text)
            if not missing_keys:
                return [list(self._cache[key]) for key in keys]
        payload: dict[str, Any] = {"model": resolved_model, "input": missing_inputs}
        if resolved_dimensions > 0:
            payload["dimensions"] = resolved_dimensions
        request_timeout = float(timeout or self.timeout)
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            control_checkpoint(control_token)
            try:
                ssl_context = ssl.create_default_context(cafile=certifi.where())
                client = httpx.Client(
                    verify=ssl_context,
                    timeout=request_timeout,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "User-Agent": USER_AGENT,
                    },
                )
                close_transport = getattr(client, "close", None)
                stop_callback = close_transport if callable(close_transport) else lambda: None
                unregister = control_register_stop_callback(control_token, stop_callback)
                try:
                    response = client.post(self.base_url + "/embeddings", json=payload)
                    response.raise_for_status()
                    body = response.json()
                finally:
                    unregister()
                    if callable(close_transport):
                        close_transport()
                vectors = parse_embedding_response(
                    body,
                    expected_count=len(missing_inputs),
                    expected_dimensions=resolved_dimensions,
                )
                with self._cache_lock:
                    for key, vector in zip(missing_keys, vectors, strict=True):
                        self._cache[key] = vector
                    while len(self._cache) > self._max_cache_entries:
                        self._cache.pop(next(iter(self._cache)))
                    output = [list(self._cache[key]) for key in keys]
                control_checkpoint(control_token)
                return output
            except httpx.HTTPStatusError as exc:
                control_check_cancelled(control_token)
                detail = exc.response.text
                last_error = RuntimeError(
                    f"Embedding HTTP {exc.response.status_code}: {detail[:500]}"
                )
                if (
                    exc.response.status_code not in {408, 425, 429, 500, 502, 503, 504}
                    or attempt >= self.max_retries
                ):
                    break
                retry_after = exc.response.headers.get("Retry-After", "")
                try:
                    delay = max(0.0, float(retry_after))
                except ValueError:
                    delay = min(8.0, 0.8 * (2**attempt))
                control_wait(control_token, min(8.0, delay), checkpoint=True)
                continue
            except httpx.TimeoutException:
                control_check_cancelled(control_token)
                last_error = RuntimeError(f"Embedding request timed out after {request_timeout}s.")
                if attempt >= self.max_retries:
                    break
            except httpx.NetworkError as exc:
                control_check_cancelled(control_token)
                last_error = RuntimeError(f"Embedding request failed: {exc}")
                if attempt >= self.max_retries:
                    break
            except Exception as exc:  # noqa: BLE001
                control_check_cancelled(control_token)
                last_error = exc
                break
            control_wait(control_token, min(8.0, 0.8 * (2**attempt)), checkpoint=True)
        raise RuntimeError(str(last_error or "Embedding request failed."))


def parse_embedding_response(
    body: dict[str, Any], *, expected_count: int, expected_dimensions: int = 0
) -> list[list[float]]:
    rows = body.get("data") if isinstance(body, dict) else None
    if not isinstance(rows, list):
        raise RuntimeError("Embedding response did not include a data list.")
    indexed: list[tuple[int, list[float]]] = []
    for fallback_index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        embedding = row.get("embedding")
        if not isinstance(embedding, list):
            continue
        try:
            vector = [float(value) for value in embedding]
        except Exception as exc:
            raise RuntimeError("Embedding response contained a non-numeric vector.") from exc
        index = row.get("index")
        indexed.append((int(index) if isinstance(index, int) else fallback_index, vector))
    indexed.sort(key=lambda item: item[0])
    vectors = [vector for _, vector in indexed]
    if len(vectors) != expected_count:
        raise RuntimeError(
            f"Embedding response returned {len(vectors)} vector(s), expected {expected_count}."
        )
    validate_embedding_vectors(vectors, expected_dimensions=expected_dimensions)
    return vectors


def validate_embedding_vectors(
    vectors: Sequence[Sequence[float]], *, expected_dimensions: int = 0
) -> None:
    lengths = {len(vector) for vector in vectors}
    if not lengths or 0 in lengths:
        raise RuntimeError("Embedding response contained an empty vector.")
    if len(lengths) != 1:
        raise RuntimeError("Embedding response contained vectors with inconsistent dimensions.")
    if expected_dimensions > 0 and lengths.pop() != expected_dimensions:
        raise RuntimeError(
            f"Embedding response dimension did not match requested dimension {expected_dimensions}."
        )


def embedding_cache_key(model: str, dimensions: int, text: str) -> str:
    digest = hashlib.sha1(str(text or "").encode("utf-8")).hexdigest()
    return f"{model}:{int(dimensions or 0)}:{digest}"
