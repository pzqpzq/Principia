"""Compress an explicitly selected, stopped runtime tree and verify before removal.

Never accepts a corpus or evaluation directory. Credentials are refused before
reading any file. Symlinks are preserved as pointers and never followed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import tarfile
from contextlib import closing
from pathlib import Path


def digest(stream) -> str:
    value = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        value.update(chunk)
    return value.hexdigest()


def credential_name(path: Path) -> bool:
    return (path.name in {".secrets", "secrets", "credentials.json", "provider-secrets.json"}
            or path.name.startswith(".env") or path.suffix == ".env")


def inventory(source: Path, *, preserve_credentials: bool) -> list[Path]:
    paths = []
    for root, directories, names in os.walk(source, followlinks=False):
        if preserve_credentials:
            directories[:] = [name for name in directories if not credential_name(Path(name))]
            names = [name for name in names if not credential_name(Path(name))]
        paths.extend(Path(root) / name for name in directories + names)
    # Complete name-only preflight before reading any payload.
    for path in paths:
        rel = path.relative_to(source)
        if any(credential_name(Path(part)) for part in rel.parts):
            raise ValueError("Credential material must remain outside runtime archives.")
    return paths


def snapshot(source: Path, *, preserve_credentials: bool = False) -> dict:
    paths = inventory(source, preserve_credentials=preserve_credentials)
    for path in paths:
        if path.name != "principia.sqlite" or path.is_symlink() or not path.is_file():
            continue
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "workspace_runtime_leases" in tables:
                for (pid,) in conn.execute("SELECT process_id FROM workspace_runtime_leases"):
                    try:
                        if int(pid) <= 0:
                            raise ValueError("Invalid runtime lease.")
                        os.kill(int(pid), 0)
                    except ProcessLookupError:
                        continue
                    except PermissionError:
                        pass
                    raise ValueError("Stop the runtime before archiving its workspace.")
    # Read-only SQLite inspection can initialize WAL bookkeeping files. Enumerate
    # after closing those connections so the verified snapshot includes them.
    entries = {}
    for path in sorted(inventory(source, preserve_credentials=preserve_credentials)):
        rel = path.relative_to(source).as_posix()
        if path.is_symlink():
            entries[rel] = {"kind": "symlink", "target": os.readlink(path)}
        elif path.is_dir():
            entries[rel] = {"kind": "directory"}
        elif path.is_file():
            with path.open("rb") as stream:
                entries[rel] = {"kind": "file", "bytes": path.stat().st_size, "sha256": digest(stream)}
        else:
            raise ValueError("Special files cannot be archived safely.")
    return entries


def verify(archive: Path, entries: dict) -> None:
    found = {}
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle:
            if member.isdir():
                found[member.name] = {"kind": "directory"}
            elif member.issym():
                found[member.name] = {"kind": "symlink", "target": member.linkname}
            elif member.isfile():
                with bundle.extractfile(member) as stream:
                    found[member.name] = {"kind": "file", "bytes": member.size, "sha256": digest(stream)}
            else:
                raise ValueError("Unexpected archive member type.")
    if found != entries:
        raise ValueError("Archive verification failed; original files are retained.")


def archive_runtime(source: Path, archive: Path, *, remove_verified: bool = False,
                    preserve_credentials: bool = False) -> dict:
    if source.is_symlink():
        raise ValueError("The runtime root must not be a symlink.")
    source, archive = source.resolve(), archive.resolve()
    if "runtime" not in source.parts or source.name == "runtime" or "evaluation" in source.parts:
        raise ValueError("Only an explicit subdirectory of runtime/ may be archived.")
    if not source.is_dir() or source == archive or source in archive.parents:
        raise ValueError("The archive must be outside the selected runtime directory.")
    manifest = archive.with_suffix(archive.suffix + ".manifest.json")
    partial = archive.with_suffix(archive.suffix + ".partial")
    if any(path.exists() for path in (archive, manifest, partial)):
        raise ValueError("Archive output already exists; it is never overwritten.")
    entries = snapshot(source, preserve_credentials=preserve_credentials)
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(partial, "w:gz", compresslevel=6, dereference=False) as bundle:
        for relative in entries:
            bundle.add(source / relative, arcname=relative, recursive=False)
    verify(partial, entries)
    if snapshot(source, preserve_credentials=preserve_credentials) != entries:
        raise ValueError("Runtime changed during archival; originals are retained.")
    partial.rename(archive)
    receipt = {"schema_version": "principia.runtime-archive/v1", "source": str(source),
               "source_bytes": sum(entry.get("bytes", 0) for entry in entries.values()),
               "archive_bytes": archive.stat().st_size, "verified": True,
               "verified_payload_removed": remove_verified,
               "credentials_left_in_place": preserve_credentials, "entries": entries}
    manifest.write_text(json.dumps(receipt, indent=2) + "\n")
    if remove_verified:
        # Remove only verified entries. Credential subtrees are never visited or
        # removed; ancestors remain if they contain retained material.
        for relative in sorted(entries, key=lambda name: len(Path(name).parts), reverse=True):
            path = source / relative
            if entries[relative]["kind"] == "directory":
                try:
                    path.rmdir()
                except OSError:
                    pass
            else:
                path.unlink()
        try:
            source.rmdir()
        except OSError:
            pass
    return {key: value for key, value in receipt.items() if key != "entries"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--remove-verified", action="store_true")
    parser.add_argument("--preserve-credentials", action="store_true", help="Leave credential paths untouched and outside the archive.")
    args = parser.parse_args()
    print(json.dumps(archive_runtime(args.source, args.archive, remove_verified=args.remove_verified,
                                    preserve_credentials=args.preserve_credentials), indent=2))
