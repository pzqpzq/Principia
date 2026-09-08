from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping
from typing import Any

import rfc8785


class CanonicalizationError(ValueError):
    pass


def _reject_nonfinite(value: Any, path: str = "$") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise CanonicalizationError(f"non-finite number at {path}")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalizationError(f"non-string key at {path}")
            _reject_nonfinite(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_nonfinite(item, f"{path}[{index}]")


def canonical_json_bytes(value: Any) -> bytes:
    _reject_nonfinite(value)
    try:
        return rfc8785.dumps(value)
    except (TypeError, ValueError) as exc:
        raise CanonicalizationError(str(exc)) from exc


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def digest_records(records: Iterable[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    ordered = sorted(records, key=canonical_json_bytes)
    for record in ordered:
        payload = canonical_json_bytes(record)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def loads_strict(payload: str | bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in items:
            if key in output:
                raise CanonicalizationError(f"duplicate JSON key: {key}")
            output[key] = value
        return output

    try:
        value = json.loads(
            payload,
            object_pairs_hook=pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                CanonicalizationError(f"non-finite JSON number: {value}")
            ),
        )
    except UnicodeDecodeError as exc:
        raise CanonicalizationError("JSON must be valid UTF-8") from exc
    _reject_nonfinite(value)
    return value


def file_sha256(path: str | Any) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
