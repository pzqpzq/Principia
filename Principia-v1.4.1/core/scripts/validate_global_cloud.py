#!/usr/bin/env python3
"""Fail-closed validation for canonical Global Cloud pull requests."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from principia.cloud.canonical import CanonicalCloudRepository, normalize_record
from principia.domain.hashing import canonical_sha256

SECRET = re.compile(r"(?i)(ghp_|github_pat_|sk-[A-Za-z0-9_-]{20,}|api[_-]?key\s*[:=])")
ABSOLUTE_PATH = re.compile(r"(?:^|[\s\"'])/(?:Users|home|var|tmp|private)/")


def validate(root: Path) -> dict[str, object]:
    repository = CanonicalCloudRepository(root)
    for kind in repository.kind_models:
        directory = repository.data_root / kind
        names = {path.name for path in directory.glob("*.jsonl")}
        expected = {f"{value:02x}.jsonl" for value in range(256)}
        if names != expected:
            raise ValueError(f"{kind} must contain exactly 256 canonical shards")
    result = repository.validate()
    records = repository.all_records()
    for kind, rows in records.items():
        for row in rows:
            normalized = normalize_record(
                kind, row, schema_generation=repository.schema_generation
            )
            digest = normalized.get("content_digest")
            if digest and digest != canonical_sha256(
                {key: value for key, value in normalized.items() if key != "content_digest"}
            ):
                raise ValueError(f"stale content digest in {kind}")
            serialized = json.dumps(normalized, ensure_ascii=False, sort_keys=True)
            if SECRET.search(serialized):
                raise ValueError(f"credential-like value is forbidden in {kind}")
            if ABSOLUTE_PATH.search(serialized):
                raise ValueError(f"absolute local path is forbidden in {kind}")
            if kind in {"principles", "meta-principles"} and row["review_status"] == "reviewed":
                if repository.schema_generation >= 2:
                    if not row.get("review_attestation"):
                        raise ValueError("reviewed v2 Principle lacks owner attestation")
                elif not row.get("review_actor") or not row.get("reviewed_at"):
                    raise ValueError("reviewed Principle lacks owner attestation")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = validate(args.root.resolve())
    body = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.write_text(body, encoding="utf-8")
    print(body, end="")


if __name__ == "__main__":
    main()
