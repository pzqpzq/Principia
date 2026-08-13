#!/usr/bin/env python3
"""Build deterministic .pcg/.pcd release assets and small Pages controls."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from principia.cloud.canonical import build_cloud_delta, build_cloud_snapshot, verify_cloud_snapshot
from principia.domain.hashing import file_sha256


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("canonical_root", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--commit-sha", default="")
    parser.add_argument("--created-at", required=True)
    parser.add_argument("--work-vectors", type=Path)
    parser.add_argument("--principle-vectors", type=Path)
    parser.add_argument("--previous-snapshot", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    work_vectors = args.work_vectors.read_bytes() if args.work_vectors else b""
    principle_vectors = args.principle_vectors.read_bytes() if args.principle_vectors else b""
    snapshot = output / f"principia-global-{args.release_id}.pcg"
    manifest = build_cloud_snapshot(
        args.canonical_root.resolve(),
        snapshot,
        release_id=args.release_id,
        commit_sha=args.commit_sha,
        created_at=args.created_at,
        work_vectors=work_vectors,
        principle_vectors=principle_vectors,
    )
    verify_cloud_snapshot(snapshot, expected_sha256=manifest.snapshot_sha256)
    delta = None
    if args.previous_snapshot:
        previous = verify_cloud_snapshot(args.previous_snapshot)
        delta_path = output / f"principia-global-{previous.release_id}--{args.release_id}.pcd"
        delta = build_cloud_delta(args.previous_snapshot, snapshot, delta_path)
    release = {
        **manifest.model_dump(mode="json"),
        "snapshot_url": f"https://github.com/pzqpzq/Principia/releases/download/global-{args.release_id}/{snapshot.name}",
        "delta": (
            {
                **delta.model_dump(mode="json"),
                "url": f"https://github.com/pzqpzq/Principia/releases/download/global-{args.release_id}/principia-global-{delta.base_release_id}--{args.release_id}.pcd",
                "bytes": (
                    output / f"principia-global-{delta.base_release_id}--{args.release_id}.pcd"
                )
                .stat()
                .st_size,
                "sha256": file_sha256(
                    output / f"principia-global-{delta.base_release_id}--{args.release_id}.pcd"
                ),
            }
            if delta
            else None
        ),
    }
    (output / "manifest.json").write_text(json.dumps(release, indent=2, sort_keys=True) + "\n")
    assets = [snapshot, *(output.glob("*.pcd"))]
    (output / "SHA256SUMS").write_text(
        "".join(f"{file_sha256(path)}  {path.name}\n" for path in sorted(assets)), encoding="utf-8"
    )
    controls = output / "cloud" / "v1"
    controls.mkdir(parents=True, exist_ok=True)
    releases = controls / "releases"
    releases.mkdir(exist_ok=True)
    control = {**release, "verified": True}
    (releases / f"{args.release_id}.json").write_text(
        json.dumps(control, indent=2, sort_keys=True) + "\n"
    )
    (controls / "latest.json").write_text(json.dumps(control, indent=2, sort_keys=True) + "\n")
    stats = {
        key: release[key]
        for key in (
            "release_id",
            "commit_sha",
            "content_digest",
            "created_at",
            "snapshot_bytes",
            "work_count",
            "principle_count",
            "principle_revision_count",
            "principle_work_count",
            "relation_count",
            "embedding_contract",
            "vector_dimensions",
            "vectors_complete",
        )
    }
    (controls / "stats.json").write_text(json.dumps(stats, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
