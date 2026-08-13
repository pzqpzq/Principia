#!/usr/bin/env python3
"""Reuse unchanged vectors and embed only changed canonical records."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import httpx
import numpy as np

from principia.cloud.canonical import CanonicalCloudRepository
from principia.cloud.models_v1 import EmbeddingContract


def _previous(path: Path | None, entity: str) -> dict[str, np.ndarray[Any, Any]]:
    if not path:
        return {}
    contract = EmbeddingContract()
    table = "current_works" if entity == "work" else "current_principles"
    identifier = "work_id" if entity == "work" else "principle_id"
    entry = f"{entity}-vectors.f16"
    with tempfile.TemporaryDirectory(prefix="principia-vector-reuse.") as temporary:
        root = Path(temporary)
        with zipfile.ZipFile(path) as archive:
            archive.extract("cloud.sqlite", root)
            vectors = np.frombuffer(archive.read(entry), dtype="<f2")
        with sqlite3.connect(root / "cloud.sqlite") as conn:
            rows = conn.execute(
                f"SELECT {identifier}, content_digest FROM {table} ORDER BY {identifier}"
            ).fetchall()
        if vectors.size != len(rows) * contract.dimensions:
            return {}
        matrix = vectors.reshape((len(rows), contract.dimensions))
        return {str(digest): matrix[index].copy() for index, (_, digest) in enumerate(rows)}


def _texts(records: list[dict[str, Any]], entity: str) -> list[str]:
    contract = EmbeddingContract()
    if entity == "work":
        return [contract.work_template.format(**row) for row in records]
    return [contract.principle_template.format(
        title=row["title"], claim=row["claim"],
        scope=json.dumps(row["scope"], ensure_ascii=False, sort_keys=True),
        tags=" ".join(row["tags"]),
    ) for row in records]


def _embed(client: httpx.Client, url: str, token: str, texts: list[str]) -> np.ndarray[Any, Any]:
    contract = EmbeddingContract()
    response = client.post(
        url.rstrip("/") + "/embeddings",
        headers={"Authorization": f"Bearer {token}"},
        json={"model": contract.model, "input": texts, "dimensions": contract.dimensions},
    )
    response.raise_for_status()
    rows = sorted(response.json()["data"], key=lambda item: int(item["index"]))
    matrix = np.asarray([item["embedding"] for item in rows], dtype=np.float32)
    if matrix.shape != (len(texts), contract.dimensions):
        raise ValueError(f"embedding API returned shape {matrix.shape}")
    norm = np.linalg.norm(matrix, axis=1, keepdims=True)
    if np.any(norm == 0):
        raise ValueError("embedding API returned a zero vector")
    return matrix / norm


def build(root: Path, output: Path, *, previous: Path | None, url: str, token: str) -> None:
    repository = CanonicalCloudRepository(root)
    records = repository.all_records()
    output.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=120) as client:
        for entity, kind, identifier in (
            ("work", "works", "work_id"), ("principle", "principles", "principle_id")
        ):
            latest: dict[str, dict[str, Any]] = {}
            for row in records[kind]:
                current = latest.get(str(row[identifier]))
                if current is None or int(row["revision"]) > int(current["revision"]):
                    latest[str(row[identifier])] = row
            ordered = [latest[key] for key in sorted(latest)]
            old = _previous(previous, entity)
            matrix = np.empty((len(ordered), EmbeddingContract().dimensions), dtype=np.float32)
            missing: list[int] = []
            for index, row in enumerate(ordered):
                reused = old.get(str(row["content_digest"]))
                if reused is None:
                    missing.append(index)
                else:
                    matrix[index] = reused.astype(np.float32)
            texts = _texts(ordered, entity)
            for start in range(0, len(missing), 32):
                indexes = missing[start:start + 32]
                embedded = _embed(client, url, token, [texts[index] for index in indexes])
                for offset, index in enumerate(indexes):
                    matrix[index] = embedded[offset]
            Path(output / f"{entity}-vectors.f16").write_bytes(matrix.astype("<f2").tobytes())
            print(json.dumps({"entity": entity, "total": len(ordered), "reused": len(ordered) - len(missing), "embedded": len(missing)}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("canonical_root", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--previous-snapshot", type=Path)
    parser.add_argument("--api-url", default=os.getenv("PRINCIPIA_EMBEDDING_API_URL", "https://api.siliconflow.cn/v1"))
    args = parser.parse_args()
    token = os.getenv("PRINCIPIA_EMBEDDING_API_KEY", "")
    if not token:
        raise ValueError("PRINCIPIA_EMBEDDING_API_KEY is required to build changed vectors")
    build(args.canonical_root.resolve(), args.output.resolve(), previous=args.previous_snapshot, url=args.api_url, token=token)


if __name__ == "__main__":
    main()
