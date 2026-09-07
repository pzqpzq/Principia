"""Bound provider context without changing the local scientific blueprint."""
from __future__ import annotations

import json
from typing import Any


def compact_scientific_context(context: dict[str, Any], *, max_bytes: int = 80_000) -> dict[str, Any]:
    if max_bytes < 4_096:
        raise ValueError("Scientific context needs a minimum 4096-byte budget")
    omitted: dict[str, int] = {}
    raw_sample_keys = {"first_row_sample", "sampled_rows", "sample_values", "raw_values"}

    def compact(value: Any, path: str, depth: int = 0) -> Any:
        if depth > 10:
            omitted[path] = 1
            return {"omitted": "nested profile; complete receipt remains local"}
        if isinstance(value, str):
            limit = 3_000 if path.endswith(("scenario_context", "user_brief")) else 768
            if len(value) > limit:
                omitted[path] = len(value) - limit
            return value[:limit]
        if isinstance(value, list):
            if len(value) > 24:
                omitted[path] = len(value) - 24
            return [compact(item, f"{path}[{i}]", depth + 1) for i, item in enumerate(value[:24])]
        if isinstance(value, dict):
            if len(value) > 64:
                omitted[path] = len(value) - 64
            return {str(key): compact(item, f"{path}.{key}", depth + 1) for key, item in list(value.items())[:64] if key not in raw_sample_keys}
        return value

    result = compact(context, "context")
    def encoded_size() -> int:
        return len(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode())
    while encoded_size() > max_bytes - 2_048:
        lists: list[tuple[int, str, list[Any]]] = []
        def collect(value: Any, path: str, found: list = lists):
            if isinstance(value, list) and len(value) > 1:
                protected = path.endswith(("target_bindings", "independent_units", "input_bindings", "sources"))
                found.append((len(json.dumps(value)) // (8 if protected else 1), path, value))
            if isinstance(value, dict):
                for key, item in value.items():
                    collect(item, f"{path}.{key}")
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    collect(item, f"{path}[{index}]")
        collect(result, "context")
        if not lists:
            raise ValueError("Scientific context cannot fit safely within the provider budget")
        _, path, largest = max(lists, key=lambda item: (item[0], item[1]))
        keep = max(1, len(largest) // 2)
        omitted[path] = omitted.get(path, 0) + len(largest) - keep
        del largest[keep:]
    result["context_budget"] = {
        "max_bytes": max_bytes,
        "compacted": bool(omitted),
        "omitted_field_count": len(omitted),
        "policy": "bounded profiles and scientific bindings; complete blueprint stays local",
        "local_execution_uses_full_blueprint": True,
    }
    return result
