from __future__ import annotations

import hashlib
import json
import os
import socket
import time
import urllib.error
import urllib.request
from typing import Any, Sequence

from .constants import USER_AGENT


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
        self.api_key = api_key or os.getenv("SILICONFLOW_API_KEY") or os.getenv("PRINCIPIA_API_KEY") or ""
        self.base_url = (base_url or os.getenv("PRINCIPIA_LLM_BASE_URL", "https://api.siliconflow.cn/v1")).rstrip("/")
        self.model = model
        self.dimensions = int(dimensions or 0)
        self.timeout = float(timeout or 30.0)
        self.max_retries = max(0, int(max_retries or 0))

    def available(self) -> bool:
        return bool(self.api_key and self.base_url)

    def embed(
        self,
        texts: Sequence[str],
        *,
        model: str | None = None,
        dimensions: int | None = None,
        timeout: float | None = None,
    ) -> list[list[float]]:
        inputs = [str(text or "") for text in texts]
        if not inputs:
            return []
        if not self.available():
            raise RuntimeError("No SiliconFlow API key configured for embedding rerank.")
        resolved_model = model or self.model
        resolved_dimensions = int(dimensions if dimensions is not None else self.dimensions)
        payload: dict[str, Any] = {"model": resolved_model, "input": inputs}
        if resolved_dimensions > 0:
            payload["dimensions"] = resolved_dimensions
        data = json.dumps(payload).encode("utf-8")
        request_timeout = float(timeout or self.timeout)
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                req = urllib.request.Request(
                    self.base_url + "/embeddings",
                    data=data,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "User-Agent": USER_AGENT,
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=request_timeout) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                return parse_embedding_response(body, expected_count=len(inputs), expected_dimensions=resolved_dimensions)
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                last_error = RuntimeError(f"Embedding HTTP {exc.code}: {detail[:500]}")
                if exc.code not in {429, 500, 502, 503, 504} or attempt >= self.max_retries:
                    break
            except (TimeoutError, socket.timeout) as exc:
                last_error = RuntimeError(f"Embedding request timed out after {request_timeout}s.")
                if attempt >= self.max_retries:
                    break
            except urllib.error.URLError as exc:
                last_error = RuntimeError(f"Embedding request failed: {exc}")
                if attempt >= self.max_retries:
                    break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                break
            time.sleep(min(8.0, 0.8 * (2**attempt)))
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
        raise RuntimeError(f"Embedding response returned {len(vectors)} vector(s), expected {expected_count}.")
    validate_embedding_vectors(vectors, expected_dimensions=expected_dimensions)
    return vectors


def validate_embedding_vectors(vectors: Sequence[Sequence[float]], *, expected_dimensions: int = 0) -> None:
    lengths = {len(vector) for vector in vectors}
    if not lengths or 0 in lengths:
        raise RuntimeError("Embedding response contained an empty vector.")
    if len(lengths) != 1:
        raise RuntimeError("Embedding response contained vectors with inconsistent dimensions.")
    if expected_dimensions > 0 and lengths.pop() != expected_dimensions:
        raise RuntimeError(f"Embedding response dimension did not match requested dimension {expected_dimensions}.")


def embedding_cache_key(model: str, dimensions: int, text: str) -> str:
    digest = hashlib.sha1(str(text or "").encode("utf-8")).hexdigest()
    return f"{model}:{int(dimensions or 0)}:{digest}"
