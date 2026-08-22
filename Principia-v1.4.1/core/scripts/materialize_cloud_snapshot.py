#!/usr/bin/env python3
"""Materialize canonical JSONL shards from a verified Global Cloud snapshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from principia.cloud.canonical import CanonicalCloudRepository, _snapshot_records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    manifest, records = _snapshot_records(arguments.snapshot.resolve())
    output = arguments.output.resolve()
    if manifest.schema_version == "principia-global-manifest-v2":
        (output / "data" / "v2").mkdir(parents=True, exist_ok=True)
    repository = CanonicalCloudRepository(output)
    for kind in repository.kind_models:
        repository.write_records(kind, records.get(kind, []))
    validation = repository.validate()
    if validation["content_digest"] != manifest.content_digest:
        raise SystemExit("materialized canonical digest does not match snapshot")
    print(
        json.dumps(
            {
                "release_id": manifest.release_id,
                "commit_sha": manifest.commit_sha,
                "content_digest": manifest.content_digest,
                "counts": validation["counts"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
