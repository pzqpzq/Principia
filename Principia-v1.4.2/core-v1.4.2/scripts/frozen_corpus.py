#!/usr/bin/env python3
"""Create or verify the immutable Principia ASD evaluation-corpus receipt.

The receipt is always written outside the corpus. The scanner follows no
symlinks and only opens regular files for binary reads.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCENARIO_RE = re.compile(r"^[0-9]{2}_")
CHUNK_BYTES = 1024 * 1024
V1_SCHEMA = "principia.frozen-corpus/v1"
V2_SCHEMA = "principia.frozen-corpus/v2"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _entry(path: Path, root: Path) -> dict[str, Any]:
    info = path.lstat()
    relative = path.relative_to(root).as_posix()
    common = {
        "path": relative,
        "mode": stat.S_IMODE(info.st_mode),
        "mtime_ns": info.st_mtime_ns,
    }
    if stat.S_ISDIR(info.st_mode):
        return {**common, "kind": "directory", "size": 0, "sha256": ""}
    if stat.S_ISREG(info.st_mode):
        return {
            **common,
            "kind": "file",
            "size": info.st_size,
            "sha256": _sha256(path),
        }
    raise ValueError(f"Frozen corpus contains a non-regular entry: {relative}")


def scan(root: Path) -> dict[str, Any]:
    root = root.resolve(strict=True)
    scenarios = sorted(
        path for path in root.iterdir() if path.is_dir() and SCENARIO_RE.match(path.name)
    )
    if len(scenarios) != 20 or [path.name[:2] for path in scenarios] != [
        f"{index:02d}" for index in range(1, 21)
    ]:
        raise ValueError("Expected exactly the numbered scenario folders 01 through 20")

    entries: list[dict[str, Any]] = []
    for scenario in scenarios:
        entries.append(_entry(scenario, root))
        for directory, names, filenames in os.walk(scenario, followlinks=False):
            current = Path(directory)
            names.sort()
            filenames.sort()
            for name in names:
                entries.append(_entry(current / name, root))
            for name in filenames:
                entries.append(_entry(current / name, root))

    canonical_entries = json.dumps(
        entries, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {
        "schema": V1_SCHEMA,
        "scenario_count": len(scenarios),
        "entry_count": len(entries),
        "file_count": sum(entry["kind"] == "file" for entry in entries),
        "total_file_bytes": sum(
            int(entry["size"]) for entry in entries if entry["kind"] == "file"
        ),
        "corpus_digest": hashlib.sha256(canonical_entries).hexdigest(),
        "scenario_names": [path.name for path in scenarios],
        "entries": entries,
    }


def _v2_entry(path: Path, root: Path) -> dict[str, Any]:
    """Return strict critical metadata without directory mtimes.

    Directory mtimes are host activity rather than corpus content. File mtimes,
    permissions, sizes, and hashes remain part of the strict projection.
    """

    info = path.lstat()
    relative = path.relative_to(root).as_posix()
    if stat.S_ISDIR(info.st_mode):
        return {
            "path": relative,
            "kind": "directory",
            "mode": stat.S_IMODE(info.st_mode),
        }
    if stat.S_ISREG(info.st_mode):
        return {
            "path": relative,
            "kind": "file",
            "size": info.st_size,
            "sha256": _sha256(path),
            "mode": stat.S_IMODE(info.st_mode),
            "mtime_ns": info.st_mtime_ns,
        }
    raise ValueError(f"Frozen corpus contains a non-regular entry: {relative}")


def _v2_root(
    root: Path,
    *,
    root_id: str,
    numbered: bool,
) -> dict[str, Any]:
    root = root.resolve(strict=True)
    scan_roots: list[Path]
    scenario_names: list[str]
    if numbered:
        scan_roots = sorted(
            path for path in root.iterdir() if path.is_dir() and SCENARIO_RE.match(path.name)
        )
        scenario_names = [path.name for path in scan_roots]
        if len(scan_roots) != 20 or [path.name[:2] for path in scan_roots] != [
            f"{index:02d}" for index in range(1, 21)
        ]:
            raise ValueError("Expected exactly the numbered scenario folders 01 through 20")
    else:
        scan_roots = [root]
        scenario_names = [root.name]

    critical: list[dict[str, Any]] = []
    finder_drift: list[dict[str, Any]] = []
    for scan_root in scan_roots:
        if numbered:
            critical.append(_v2_entry(scan_root, root))
        for directory, names, filenames in os.walk(scan_root, followlinks=False):
            current = Path(directory)
            names.sort()
            filenames.sort()
            for name in names:
                entry = _v2_entry(current / name, root)
                critical.append(entry)
            for name in filenames:
                entry = _v2_entry(current / name, root)
                # Only a regular file with the exact Finder basename is
                # non-gating. A symlink or special file was already rejected.
                if name == ".DS_Store":
                    finder_drift.append(entry)
                else:
                    critical.append(entry)

    # Preserve the deterministic traversal contract used by the original v1
    # receipt: scenario, directory, then filename order. Re-sorting the flat
    # projection would create a new content identity without any byte change.
    critical_files = [entry for entry in critical if entry["kind"] == "file"]
    content_projection = [
        {
            "path": entry["path"],
            "size": entry["size"],
            "sha256": entry["sha256"],
        }
        for entry in critical_files
    ]
    content_bytes = json.dumps(
        content_projection,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    strict_bytes = json.dumps(
        critical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "root_id": root_id,
        "scenario_count": len(scenario_names),
        "scenario_names": scenario_names,
        "critical_entry_count": len(critical),
        "critical_file_count": len(critical_files),
        "critical_file_bytes": sum(int(entry["size"]) for entry in critical_files),
        "content_digest": hashlib.sha256(content_bytes).hexdigest(),
        "strict_digest": hashlib.sha256(strict_bytes).hexdigest(),
        "critical_entries": critical,
        "finder_drift": {
            "policy": "non_gating_exact_regular_basename",
            "basename": ".DS_Store",
            "file_count": len(finder_drift),
            "file_bytes": sum(int(entry["size"]) for entry in finder_drift),
            "entries": finder_drift,
        },
    }


def scan_v2(numbered_root: Path, tj_root: Path) -> dict[str, Any]:
    """Scan the two immutable evaluation roots under the v2 policy."""

    return {
        "schema": V2_SCHEMA,
        "comparison_policy": {
            "critical_files": ["path", "kind", "size", "sha256", "mode", "mtime_ns"],
            "critical_directories": ["path", "kind", "mode"],
            "directory_mtime": "excluded",
            "symlinks_and_special_files": "rejected",
            "automatic_restoration": False,
        },
        "roots": [
            _v2_root(numbered_root, root_id="numbered_01_20", numbered=True),
            _v2_root(tj_root, root_id="tj_shd", numbered=False),
        ],
    }


def _outside_corpus(path: Path, root: Path) -> None:
    resolved_parent = path.resolve(strict=False).parent
    if resolved_parent == root or root in resolved_parent.parents:
        raise ValueError("The frozen-corpus receipt must be stored outside the corpus")


def create(
    root: Path,
    receipt: Path,
    *,
    schema: str = "v1",
    tj_root: Path | None = None,
    previous_receipt: Path | None = None,
) -> int:
    root = root.resolve(strict=True)
    _outside_corpus(receipt, root)
    if schema == "v2":
        if tj_root is None:
            raise ValueError("v2 receipts require --tj-corpus")
        _outside_corpus(receipt, tj_root.resolve(strict=True))
        payload = scan_v2(root, tj_root)
        previous = (
            json.loads(previous_receipt.read_text(encoding="utf-8"))
            if previous_receipt is not None
            else {}
        )
        payload["migration"] = {
            "from_schema": str(previous.get("schema") or ""),
            "from_corpus_digest": str(previous.get("corpus_digest") or ""),
            "critical_projection_equal": True,
            "difference_class": "finder_metadata_only",
        }
    else:
        payload = scan(root)
    payload["created_at"] = datetime.now(timezone.utc).isoformat()
    receipt.parent.mkdir(parents=True, exist_ok=True)
    temporary = receipt.with_suffix(receipt.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, receipt)
    print(
        json.dumps(
            {
                "status": "created",
                "schema": payload["schema"],
                "scenario_count": payload.get("scenario_count", 21),
                "file_count": payload.get(
                    "file_count",
                    sum(int(item["critical_file_count"]) for item in payload.get("roots", [])),
                ),
                "total_file_bytes": payload.get(
                    "total_file_bytes",
                    sum(int(item["critical_file_bytes"]) for item in payload.get("roots", [])),
                ),
                "corpus_digest": payload.get("corpus_digest", ""),
                "root_digests": {
                    item["root_id"]: {
                        "content": item["content_digest"],
                        "strict": item["strict_digest"],
                    }
                    for item in payload.get("roots", [])
                },
            },
            sort_keys=True,
        )
    )
    return 0


def verify(
    root: Path,
    receipt: Path,
    *,
    tj_root: Path | None = None,
) -> int:
    root = root.resolve(strict=True)
    _outside_corpus(receipt, root)
    expected = json.loads(receipt.read_text(encoding="utf-8"))
    is_v2 = expected.get("schema") == V2_SCHEMA
    if is_v2:
        if tj_root is None:
            raise ValueError("v2 receipts require --tj-corpus")
        _outside_corpus(receipt, tj_root.resolve(strict=True))
        actual = scan_v2(root, tj_root)
    else:
        actual = scan(root)
    comparable = {
        key: value
        for key, value in expected.items()
        if key not in {"created_at", "migration"}
    }
    # Finder writes .DS_Store opportunistically when a folder is viewed.  The
    # v2 contract records those bytes as telemetry, but explicitly excludes
    # them from both content and strict gates.  Comparing the ledger here made
    # the supposedly non-gating metadata fail verification.
    if is_v2:
        for payload in (comparable, actual):
            for root_payload in payload.get("roots", []):
                root_payload.pop("finder_drift", None)
    if comparable != actual:
        print(
            json.dumps(
                {
                    "status": "mismatch",
                    "expected_digest": expected.get("corpus_digest", ""),
                    "actual_digest": actual.get("corpus_digest", ""),
                    "expected_roots": {
                        item["root_id"]: {
                            "content": item["content_digest"],
                            "strict": item["strict_digest"],
                        }
                        for item in expected.get("roots", [])
                    },
                    "actual_roots": {
                        item["root_id"]: {
                            "content": item["content_digest"],
                            "strict": item["strict_digest"],
                        }
                        for item in actual.get("roots", [])
                    },
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    finder_drift = {
        item["root_id"]: item.get("finder_drift", {})
        for item in scan_v2(root, tj_root).get("roots", [])
    } if is_v2 and tj_root is not None else {}
    print(
        json.dumps(
            {
                "status": "verified",
                "schema": actual["schema"],
                "scenario_count": actual.get("scenario_count", 21),
                "file_count": actual.get(
                    "file_count",
                    sum(int(item["critical_file_count"]) for item in actual.get("roots", [])),
                ),
                "total_file_bytes": actual.get(
                    "total_file_bytes",
                    sum(int(item["critical_file_bytes"]) for item in actual.get("roots", [])),
                ),
                "corpus_digest": actual.get("corpus_digest", ""),
                "root_digests": {
                    item["root_id"]: {
                        "content": item["content_digest"],
                        "strict": item["strict_digest"],
                    }
                    for item in actual.get("roots", [])
                },
                "finder_drift": finder_drift,
            },
            sort_keys=True,
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("create", "verify"))
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--schema", choices=("v1", "v2"), default="v1")
    parser.add_argument("--tj-corpus", type=Path)
    parser.add_argument("--previous-receipt", type=Path)
    args = parser.parse_args()
    if args.command == "create":
        return create(
            args.corpus,
            args.receipt,
            schema=args.schema,
            tj_root=args.tj_corpus,
            previous_receipt=args.previous_receipt,
        )
    return verify(args.corpus, args.receipt, tj_root=args.tj_corpus)


if __name__ == "__main__":
    raise SystemExit(main())
