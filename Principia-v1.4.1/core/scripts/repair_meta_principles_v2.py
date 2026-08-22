#!/usr/bin/env python3
"""Repair the six escaped TeX control sequences in the supplied Meta corpus.

The operation is deterministic and atomic. It updates only JSONL files that
contain the known corrupt sequences, recomputes record content digests where
present, and refreshes SHA256SUMS for every tracked file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from principia.domain.hashing import canonical_json_bytes, canonical_sha256

REPAIRS = {
    "\x07pprox": r"\approx",
    "\x07lpha": r"\alpha",
    "\x0barepsilon": r"\varepsilon",
}


def _repair_value(value: Any) -> Any:
    if isinstance(value, str):
        for broken, repaired in REPAIRS.items():
            value = value.replace(broken, repaired)
        return value
    if isinstance(value, list):
        return [_repair_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _repair_value(item) for key, item in value.items()}
    return value


def _atomic_write(path: Path, body: bytes) -> None:
    descriptor, raw_temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(raw_temporary)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def repair_jsonl(path: Path) -> int:
    repaired_rows: list[dict[str, Any]] = []
    changed = 0
    for raw in path.read_bytes().splitlines():
        if not raw.strip():
            continue
        source = json.loads(raw)
        repaired = _repair_value(source)
        if repaired != source:
            changed += 1
            if "content_digest" in repaired:
                repaired["content_digest"] = canonical_sha256(
                    {key: value for key, value in repaired.items() if key != "content_digest"}
                )
        repaired_rows.append(repaired)
    if changed:
        _atomic_write(path, b"".join(canonical_json_bytes(row) + b"\n" for row in repaired_rows))
    return changed


def refresh_checksums(root: Path) -> None:
    checksum_path = root / "SHA256SUMS"
    tracked = []
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        _, relative = line.split("  ", 1)
        tracked.append(relative)
    lines = []
    for relative in tracked:
        digest = hashlib.sha256((root / relative).read_bytes()).hexdigest()
        lines.append(f"{digest}  {relative}\n")
    _atomic_write(checksum_path, "".join(lines).encode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    root = arguments.root.expanduser().resolve()
    affected = sorted((root / "data").glob("*.jsonl"))
    corrupt = []
    for path in affected:
        text = path.read_text(encoding="utf-8")
        if "\\u0007" in text or "\\u000b" in text:
            corrupt.append(path)
    if arguments.check:
        if corrupt:
            raise SystemExit("corrupt TeX escapes remain: " + ", ".join(path.name for path in corrupt))
        return 0
    changed = sum(repair_jsonl(path) for path in corrupt)
    refresh_checksums(root)
    remaining = []
    for path in affected:
        decoded = path.read_text(encoding="utf-8")
        if "\\u0007" in decoded or "\\u000b" in decoded:
            remaining.append(path.name)
    if remaining:
        raise SystemExit("repair incomplete: " + ", ".join(remaining))
    print(json.dumps({"changed_records": changed, "changed_files": len(corrupt)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
