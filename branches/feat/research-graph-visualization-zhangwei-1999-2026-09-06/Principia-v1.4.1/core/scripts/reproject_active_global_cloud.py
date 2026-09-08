#!/usr/bin/env python3
"""Rebuild the active derived snapshot without changing canonical Cloud data.

This is the local migration used when a v1 snapshot projection changes (for
example the map's scientific-discipline taxonomy).  It deliberately reads the
active verified release rather than the smaller fixture bundled with a source
checkout, preserves vectors and release identity, and leaves a recoverable
pre-migration archive in the shared cache downloads directory.
"""

from __future__ import annotations

import argparse
import json
import tempfile
import zipfile
from pathlib import Path

from principia.cloud import global_cloud_cache_root
from principia.cloud.canonical import (
    PCG_ENTRIES,
    V1_KIND_MODELS,
    V2_KIND_MODELS,
    CanonicalCloudRepository,
    build_cloud_snapshot,
)
from principia.cloud.snapshot import GlobalCloudSnapshotStore
from principia.domain.hashing import file_sha256


def _archive_active(release_root: Path, target: Path) -> None:
    temporary = target.with_suffix(target.suffix + ".partial")
    with zipfile.ZipFile(
        temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for name in sorted(PCG_ENTRIES):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100600 & 0xFFFF) << 16
            archive.writestr(info, (release_root / name).read_bytes())
    temporary.replace(target)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-root", type=Path, default=global_cloud_cache_root())
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    store = GlobalCloudSnapshotStore(args.cache_root)
    active = store.active()
    if not active:
        raise SystemExit("No verified active Global Cloud snapshot is installed.")
    manifest = active["manifest"]
    schema_generation = 2 if manifest.schema_version == "principia-global-manifest-v2" else 1
    records = store.canonical_records(include_extended=schema_generation >= 2)
    # A snapshot produced by this projection stores the immutable canonical
    # area separately.  Strip the derived field when this migration is rerun.
    for row in records["principles"]:
        if row.get("canonical_area"):
            row["area"] = row.pop("canonical_area")

    with tempfile.TemporaryDirectory(prefix="principia-global-reproject.") as raw:
        temporary_root = Path(raw)
        canonical_root = temporary_root / "canonical"
        (canonical_root / "data" / f"v{schema_generation}").mkdir(parents=True)
        repository = CanonicalCloudRepository(canonical_root)
        kind_models = V2_KIND_MODELS if schema_generation >= 2 else V1_KIND_MODELS
        for kind in kind_models:
            repository.write_records(kind, records.get(kind, []))
        output = temporary_root / f"principia-global-{manifest.release_id}.pcg"
        build_cloud_snapshot(
            canonical_root,
            output,
            release_id=manifest.release_id,
            commit_sha=manifest.commit_sha,
            created_at=manifest.created_at,
            work_vectors=(active["release_root"] / "work-vectors.f16").read_bytes(),
            principle_vectors=(
                active["release_root"] / "principle-vectors.f16"
            ).read_bytes(),
        )
        if args.dry_run:
            print(json.dumps({"verified": True, "release_id": manifest.release_id}))
            return

        previous_pointer = store._json(store.active_path)
        backup = store.downloads_dir / f"{manifest.release_id}.before-reprojection.pcg"
        _archive_active(active["release_root"], backup)
        status = store.install_snapshot(output, expected_sha256=file_sha256(output))
        store._atomic_json(
            store.active_path,
            {
                "schema_version": "principia-global-active-v1",
                "release_id": manifest.release_id,
                "previous_release_id": previous_pointer.get("previous_release_id") or "",
                "activated_at": status["activated_at"],
            },
        )
        print(json.dumps(store.status(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
