from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from ..domain import JobRecord, canonical_sha256, event_id, monotonic_ulid
from ..local_sources import LocalCorpusIngestor
from ..models import LocalCorpusConfig, utc_now
from ..persistence import V14WorkspaceRepository
from ..storage import WorkspaceStorage
from .literature import write_private_acquisition


def _safe_slug(value: str) -> str:
    output: list[str] = []
    previous_dash = False
    for character in value.casefold():
        if character.isascii() and character.isalnum():
            output.append(character)
            previous_dash = False
        elif output and not previous_dash:
            output.append("-")
            previous_dash = True
    return "".join(output).strip("-")[:64] or "private-literature"


def _safe_directory_name(value: str) -> str:
    """Preserve a readable user folder name without permitting path syntax."""

    output: list[str] = []
    previous_separator = False
    for character in value.strip():
        if character.isascii() and character.isalnum():
            output.append(character)
            previous_separator = False
        elif character in {"-", "_"}:
            if output and not previous_separator:
                output.append(character)
                previous_separator = True
        elif character.isspace() and output and not previous_separator:
            output.append("-")
            previous_separator = True
    return "".join(output).strip("-_")[:64] or "private-literature"


def _atomic_private_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    partial = path.with_name(f".{path.name}.{monotonic_ulid()}.partial")
    descriptor = os.open(partial, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(partial, path)
        os.chmod(path, 0o600)
    finally:
        partial.unlink(missing_ok=True)


class LocalSourceService:
    def __init__(
        self,
        storage: WorkspaceStorage,
        repository: V14WorkspaceRepository,
        *,
        local_data_root: str | Path | None = None,
    ) -> None:
        self.storage = storage
        self.repository = repository
        self.local_data_root = (
            Path(local_data_root).expanduser().resolve()
            if local_data_root is not None
            else (storage.root / "Principia Local Data").resolve()
        )
        self.local_data_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.local_data_root, 0o700)
        source_cache = self.storage.root / "source_cache"
        source_cache.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(source_cache, 0o700)

    def reconcile_working_directory_roots(self) -> dict[str, int]:
        """Rebase managed Local paths after a working directory is moved.

        Only sources carrying a portable ``local_data/...`` location and a
        matching source manifest are eligible. External folders are never
        moved or rebound implicitly.
        """

        rebased_sources = 0
        rebased_acquisitions = 0
        for source in self.repository.list_sources():
            display = Path(str(source.get("display_location") or ""))
            if not display.parts or display.parts[0] != "local_data":
                continue
            relative = Path(*display.parts[1:])
            if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
                continue
            expected = (self.local_data_root / relative).resolve()
            previous = self.repository.source_root(str(source["source_id"]))
            if previous is None or previous == expected or not expected.is_dir():
                continue
            manifest_path = expected / "manifest.json"
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if str(manifest.get("source_id") or "") != str(source["source_id"]):
                continue
            old_working_root = previous
            for _part in display.parts:
                old_working_root = old_working_root.parent
            old_workspace = old_working_root / "workspace"
            with self.repository.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "UPDATE local_sources_v14 SET absolute_root=?, updated_at=? WHERE source_id=?",
                    (str(expected), utc_now(), source["source_id"]),
                )
                conn.execute(
                    "UPDATE research_datasets SET storage_root=?, updated_at=? "
                    "WHERE source_id=? AND storage_root=?",
                    (str(expected), utc_now(), source["source_id"], str(previous)),
                )
                rows = conn.execute(
                    """
                    SELECT a.acquisition_id, a.payload_json
                    FROM scholarly_acquisitions a
                    JOIN local_source_documents d
                      ON d.acquisition_id=a.acquisition_id
                    WHERE d.source_id=?
                    """,
                    (source["source_id"],),
                ).fetchall()
                for row in rows:
                    payload = json.loads(str(row["payload_json"]))
                    paths = dict(payload.get("private_paths") or {})
                    changed = False
                    for key, raw in list(paths.items()):
                        candidate = Path(str(raw))
                        replacement: Path | None = None
                        if candidate.is_relative_to(previous):
                            replacement = expected / candidate.relative_to(previous)
                        elif candidate.is_relative_to(old_workspace):
                            replacement = self.storage.root / candidate.relative_to(old_workspace)
                        if replacement is not None:
                            paths[key] = str(replacement)
                            changed = True
                    if changed:
                        payload["private_paths"] = paths
                        conn.execute(
                            "UPDATE scholarly_acquisitions SET payload_json=?, updated_at=? "
                            "WHERE acquisition_id=?",
                            (
                                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                                utc_now(),
                                row["acquisition_id"],
                            ),
                        )
                        rebased_acquisitions += 1
                conn.commit()
            rebased_sources += 1
        return {
            "rebased_sources": rebased_sources,
            "rebased_acquisitions": rebased_acquisitions,
        }

    def isolate_derived_sidecars(self) -> dict[str, int]:
        """Move Principia-generated parse sidecars out of Local raw-data folders.

        Older layouts colocated ``normalized.txt`` and ``metadata.json`` with
        each acquired paper.  The raw representation remains untouched; each
        sidecar is copied atomically into the workspace cache, hash-verified,
        and only then removed from the user-owned Local data folder.
        """

        moved = 0
        sources = self.repository.list_sources()
        for source in sources:
            source_id = str(source["source_id"])
            root = self.repository.source_root(source_id)
            if root is None or not root.is_dir():
                continue
            cache_root = (
                self.storage.root
                / "source_cache"
                / hashlib.sha256(source_id.encode()).hexdigest()[:24]
            )
            replacements: dict[str, str] = {}
            for name in ("normalized.txt", "metadata.json"):
                for old in sorted(root.glob(f"papers/*/{name}")):
                    if old.is_symlink() or not old.is_file():
                        continue
                    relative_parent = old.parent.relative_to(root / "papers")
                    destination = cache_root / relative_parent / name
                    body = old.read_bytes()
                    digest = hashlib.sha256(body).hexdigest()
                    if destination.exists():
                        if hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
                            raise ValueError(
                                "workspace source cache conflicts with retained Local data"
                            )
                    else:
                        _atomic_private_write(destination, body)
                    if hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
                        raise ValueError("workspace source cache verification failed")
                    replacements[str(old)] = str(destination)
                    old.unlink()
                    moved += 1
            if not replacements:
                continue
            with self.repository.connect() as conn:
                rows = conn.execute(
                    "SELECT acquisition_id, payload_json FROM scholarly_acquisitions"
                ).fetchall()
                for row in rows:
                    payload = json.loads(str(row["payload_json"]))
                    paths = dict(payload.get("private_paths") or {})
                    changed = False
                    for key in ("text_path", "metadata_path"):
                        if str(paths.get(key) or "") in replacements:
                            paths[key] = replacements[str(paths[key])]
                            changed = True
                    if changed:
                        payload["private_paths"] = paths
                        conn.execute(
                            "UPDATE scholarly_acquisitions SET payload_json=?, updated_at=? "
                            "WHERE acquisition_id=?",
                            (
                                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                                utc_now(),
                                row["acquisition_id"],
                            ),
                        )
        return {"moved_sidecars": moved}

    def materialize_pending(self) -> dict[str, int]:
        """Copy retained legacy acquisitions into visible managed folders.

        Original acquisition assets remain untouched until every copied byte and
        normalized-text hash has been verified.
        """

        copied_sources = 0
        copied_documents = 0
        with self.repository.connect() as conn:
            pending = conn.execute(
                """
                SELECT source_id, absolute_root, display_name, display_location
                FROM local_sources_v14 WHERE status='pending_materialization'
                ORDER BY source_id
                """
            ).fetchall()
        for source in pending:
            source_id = str(source["source_id"])
            root = Path(str(source["absolute_root"]))
            root.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(root, 0o700)
            _atomic_private_write(
                root / "README.txt",
                (
                    b"Principia private literature source\n\n"
                    b"This folder contains only user-owned source material. Principia "
                    b"stores parsed text, evidence records, and reusable Principles "
                    b"separately in the working directory's workspace folder.\n"
                ),
            )
            with self.repository.connect() as conn:
                documents = conn.execute(
                    """
                    SELECT d.document_id, d.work_id, d.acquisition_id,
                           a.mime_type, a.byte_sha256, a.text_sha256,
                           a.content_kind, a.payload_json, w.payload_json AS work_json
                    FROM local_source_documents d
                    LEFT JOIN scholarly_acquisitions a
                        ON a.acquisition_id=d.acquisition_id
                    JOIN works w ON w.id=d.work_id
                    WHERE d.source_id=? ORDER BY d.document_id
                    """,
                    (source_id,),
                ).fetchall()
            manifest_documents: list[dict[str, Any]] = []
            for document in documents:
                if not document["acquisition_id"] or not document["payload_json"]:
                    continue
                acquisition = json.loads(document["payload_json"])
                paths = acquisition.get("private_paths") or {}
                raw_path = Path(str(paths.get("raw_path") or ""))
                text_path = Path(str(paths.get("text_path") or ""))
                if not raw_path.is_file() or not text_path.is_file():
                    continue
                raw = raw_path.read_bytes()
                normalized = text_path.read_text(encoding="utf-8")
                if hashlib.sha256(raw).hexdigest() != str(document["byte_sha256"]):
                    raise ValueError("retained acquisition byte hash changed during migration")
                if hashlib.sha256(normalized.encode()).hexdigest() != str(document["text_sha256"]):
                    raise ValueError("retained acquisition text hash changed during migration")
                work = json.loads(document["work_json"])
                acquired = {
                    "mime_type": str(document["mime_type"]),
                    "bytes": raw,
                    "text": normalized,
                    "byte_sha256": str(document["byte_sha256"]),
                    "text_sha256": str(document["text_sha256"]),
                    "content_kind": str(document["content_kind"]),
                    "access_basis": acquisition.get("access_basis", ""),
                    "manuscript_version": acquisition.get("manuscript_version", ""),
                    "license": acquisition.get("license", ""),
                }
                visible = write_private_acquisition(
                    root,
                    work_id=str(document["work_id"]),
                    acquired=acquired,
                    relative_stem=f"{work.get('year') or 'undated'}-{work.get('title') or 'work'}",
                    metadata={
                        "title": work.get("title") or document["work_id"],
                        "year": work.get("year"),
                        "doi": work.get("doi", ""),
                    },
                    derived_root=(
                        self.storage.root
                        / "source_cache"
                        / hashlib.sha256(source_id.encode()).hexdigest()[:24]
                    ),
                )
                with self.repository.connect() as conn:
                    conn.execute(
                        """
                        UPDATE local_source_documents
                        SET portable_relative_uri=?, parse_status='indexed',
                            extraction_eligible=1, updated_at=?
                        WHERE document_id=?
                        """,
                        (
                            visible["raw_relative_path"],
                            utc_now(),
                            document["document_id"],
                        ),
                    )
                manifest_documents.append(
                    {
                        "document_id": document["document_id"],
                        "work_id": document["work_id"],
                        "relative_path": visible["raw_relative_path"],
                        "byte_sha256": document["byte_sha256"],
                        "text_sha256": document["text_sha256"],
                    }
                )
                copied_documents += 1
            manifest = {
                "schema_version": "principia-local-source-v1",
                "source_id": source_id,
                "display_name": source["display_name"],
                "display_location": source["display_location"],
                "materialized_at": utc_now(),
                "documents": manifest_documents,
            }
            _atomic_private_write(
                root / "manifest.json",
                (
                    json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
                ).encode(),
            )
            with self.repository.connect() as conn:
                conn.execute(
                    """
                    UPDATE local_sources_v14 SET status='ready', updated_at=?,
                        payload_json=json_set(payload_json, '$.status', 'ready')
                    WHERE source_id=?
                    """,
                    (utc_now(), source_id),
                )
            copied_sources += 1
        return {"sources": copied_sources, "documents": copied_documents}

    def consolidate_legacy_layouts(self) -> dict[str, int]:
        """Move verified acquisition representations into one folder per Work.

        The database is updated only after every replacement file has been
        written and hash-verified. Legacy duplicates are removed only after the
        authoritative paths commit successfully.
        """

        migrated_sources = 0
        migrated_documents = 0
        for source in self.repository.list_sources():
            source_id = str(source["source_id"])
            root = self.repository.source_root(source_id)
            if root is None or not root.is_dir():
                continue
            with self.repository.connect() as conn:
                rows = conn.execute(
                    """
                    SELECT d.document_id, d.work_id, d.acquisition_id,
                           d.portable_relative_uri, a.mime_type, a.byte_sha256,
                           a.text_sha256, a.content_kind, a.payload_json,
                           w.payload_json AS work_json
                    FROM local_source_documents d
                    JOIN scholarly_acquisitions a ON a.acquisition_id=d.acquisition_id
                    JOIN works w ON w.id=d.work_id
                    WHERE d.source_id=? ORDER BY d.document_id
                    """,
                    (source_id,),
                ).fetchall()
            updates: list[tuple[dict[str, str], sqlite3.Row, dict[str, Any]]] = []
            # sqlite3 is imported lazily to keep this service's public surface small.
            for row in rows:
                acquisition = json.loads(row["payload_json"])
                paths = dict(acquisition.get("private_paths") or {})
                raw_path = Path(str(paths.get("raw_path") or ""))
                text_path = Path(str(paths.get("text_path") or ""))
                metadata_path = Path(str(paths.get("metadata_path") or ""))
                if not raw_path.is_file() or not text_path.is_file():
                    continue
                relative_raw = (
                    raw_path.relative_to(root).as_posix() if raw_path.is_relative_to(root) else ""
                )
                expected_name = (
                    "paper.pdf"
                    if str(row["mime_type"]) == "application/pdf"
                    else "full-text.txt"
                    if str(row["content_kind"]) == "full_text"
                    else "abstract.txt"
                )
                raw_layout_is_current = (
                    re.match(
                        r"^papers/[^/]+/(?:paper\.pdf|full-text\.txt|abstract\.txt)$",
                        relative_raw,
                    )
                    and raw_path.name == expected_name
                )
                derived_is_isolated = not text_path.is_relative_to(root) and (
                    not metadata_path.exists() or not metadata_path.is_relative_to(root)
                )
                if raw_layout_is_current and derived_is_isolated:
                    continue
                raw = raw_path.read_bytes()
                normalized = text_path.read_text(encoding="utf-8")
                if hashlib.sha256(raw).hexdigest() != str(row["byte_sha256"]):
                    raise ValueError("legacy acquisition bytes changed before layout migration")
                if hashlib.sha256(normalized.encode()).hexdigest() != str(row["text_sha256"]):
                    raise ValueError("legacy normalized text changed before layout migration")
                work = json.loads(row["work_json"])
                acquired = {
                    "mime_type": str(row["mime_type"]),
                    "bytes": raw,
                    "text": normalized,
                    "byte_sha256": str(row["byte_sha256"]),
                    "text_sha256": str(row["text_sha256"]),
                    "content_kind": str(row["content_kind"]),
                    "access_basis": acquisition.get("access_basis", ""),
                    "manuscript_version": acquisition.get("manuscript_version", ""),
                    "license": acquisition.get("license", ""),
                }
                visible = write_private_acquisition(
                    root,
                    work_id=str(row["work_id"]),
                    acquired=acquired,
                    relative_stem=f"{work.get('year') or 'undated'}-{work.get('title') or 'work'}",
                    metadata={
                        "title": work.get("title") or row["work_id"],
                        "year": work.get("year"),
                        "doi": work.get("doi", ""),
                        "venue": work.get("venue", ""),
                        "source": work.get("source", ""),
                    },
                    derived_root=(
                        self.storage.root
                        / "source_cache"
                        / hashlib.sha256(source_id.encode()).hexdigest()[:24]
                    ),
                )
                updates.append((visible, row, {**paths, "metadata_path": str(metadata_path)}))
            if not updates:
                continue
            with self.repository.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                for visible, row, _old_paths in updates:
                    acquisition = json.loads(row["payload_json"])
                    acquisition["private_paths"] = visible
                    conn.execute(
                        "UPDATE scholarly_acquisitions SET payload_json=?, updated_at=? "
                        "WHERE acquisition_id=?",
                        (
                            json.dumps(acquisition, ensure_ascii=False, sort_keys=True),
                            utc_now(),
                            row["acquisition_id"],
                        ),
                    )
                    conn.execute(
                        "UPDATE local_source_documents SET portable_relative_uri=?, "
                        "updated_at=? WHERE document_id=?",
                        (visible["raw_relative_path"], utc_now(), row["document_id"]),
                    )
                conn.commit()
            removed: list[str] = []
            for visible, _row, old_paths in updates:
                protected = {
                    Path(visible["raw_path"]),
                    Path(visible["text_path"]),
                    Path(visible["metadata_path"]),
                }
                for key in ("raw_path", "text_path", "metadata_path"):
                    old = Path(str(old_paths.get(key) or ""))
                    if old.is_file() and old not in protected and old.is_relative_to(root):
                        old.unlink()
                        removed.append(old.relative_to(root).as_posix())
            for legacy in (root / "abstracts", root / "text", root / "metadata"):
                if legacy.is_dir() and not any(legacy.iterdir()):
                    legacy.rmdir()
            receipt = {
                "schema_version": "principia-local-layout-v2",
                "source_id": source_id,
                "migrated_documents": len(updates),
                "removed_verified_duplicates": sorted(removed),
                "completed_at": utc_now(),
            }
            _atomic_private_write(
                root / ".principia-layout-v2-receipt.json",
                (json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(),
            )
            manifest = {
                "schema_version": "principia-local-source-v2",
                "source_id": source_id,
                "display_name": source["display_name"],
                "display_location": source["display_location"],
                "updated_at": utc_now(),
                "documents": self.repository.source_documents(source_id, limit=100)["items"],
            }
            _atomic_private_write(
                root / "manifest.json",
                (
                    json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
                ).encode(),
            )
            migrated_sources += 1
            migrated_documents += len(updates)
        return {"sources": migrated_sources, "documents": migrated_documents}

    def create_managed(
        self,
        *,
        name: str,
        goal: str = "",
        area: str = "",
        parent: str | Path | None = None,
    ) -> dict[str, Any]:
        base = Path(parent).expanduser().resolve(strict=True) if parent else self.local_data_root
        if not base.is_dir():
            raise NotADirectoryError("managed-source parent is not a directory")
        source_id = f"src:{monotonic_ulid()}"
        base_name = _safe_directory_name(name or goal)
        directory_name = base_name
        suffix = 2
        while (base / directory_name).exists():
            directory_name = f"{base_name}-{suffix}"
            suffix += 1
        managed_root = base / directory_name
        managed_root.mkdir(parents=True, exist_ok=False, mode=0o700)
        os.chmod(managed_root, 0o700)
        for child in ("papers",):
            (managed_root / child).mkdir(mode=0o700)
        manifest = {
            "schema_version": "principia-local-source-v1",
            "source_id": source_id,
            "display_name": name or goal or "Private literature",
            "goal": goal,
            "area": area,
            "created_at": utc_now(),
            "documents": [],
        }
        _atomic_private_write(
            managed_root / "README.txt",
            (
                b"Principia private literature source\n\n"
                b"This folder contains Local source material only: acquired PDFs, permitted "
                b"plain-text full text, and abstracts. Parsed text, evidence records, and "
                b"extracted Principles are stored separately in the Principia workspace.\n"
            ),
        )
        _atomic_private_write(
            managed_root / "manifest.json",
            (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(),
        )
        if managed_root.is_relative_to(self.local_data_root):
            prefix = (
                "local_data"
                if self.local_data_root.name == "local_data"
                else self.local_data_root.name
            )
            display_location = (
                Path(prefix) / managed_root.relative_to(self.local_data_root)
            ).as_posix()
        elif managed_root.is_relative_to(self.storage.root):
            display_location = managed_root.relative_to(self.storage.root).as_posix()
        else:
            display_location = f"External/{managed_root.name}"
        now = utc_now()
        payload = {
            "source_id": source_id,
            "portable_uri": f"principia-managed://{source_id.removeprefix('src:')}",
            "display_name": name or goal or managed_root.name,
            "display_location": display_location,
            "source_kind": "managed",
            "status": "ready",
            "revision": 1,
            "created_at": now,
            "updated_at": now,
        }
        with self.repository.connect() as conn:
            conn.execute(
                """
                INSERT INTO local_sources_v14(
                    source_id, portable_uri, absolute_root, display_name, status,
                    payload_json, created_at, updated_at, source_kind, revision,
                    display_location
                ) VALUES (?, ?, ?, ?, 'ready', ?, ?, ?, 'managed', 1, ?)
                """,
                (
                    source_id,
                    payload["portable_uri"],
                    str(managed_root),
                    payload["display_name"],
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    now,
                    now,
                    display_location,
                ),
            )
        # The absolute location is intentionally returned only by this creation
        # response. All subsequent reads expose the opaque ID and display path.
        return {**payload, "created_location": str(managed_root)}

    def rename(self, source_id: str, display_name: str) -> dict[str, Any]:
        root = self.repository.source_root(source_id)
        source = self.repository.source(source_id)
        if root is None or source is None:
            raise KeyError(f"unknown Local source: {source_id}")
        result = self.repository.update_collection("source", source_id, display_name)
        manifest_path = root / "manifest.json"
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["display_name"] = result["title"]
            manifest["updated_at"] = utc_now()
            _atomic_private_write(
                manifest_path,
                (
                    json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
                ).encode(),
            )
        return result

    def disconnect(self, source_id: str) -> dict[str, Any]:
        """Remove a folder from active views without deleting any local file."""

        return self.repository.archive_collection("source", source_id)

    def restore(self, source_id: str) -> dict[str, Any]:
        root = self.repository.source_root(source_id)
        if root is None:
            raise KeyError(f"unknown Local source: {source_id}")
        if not root.is_dir():
            raise FileNotFoundError("the disconnected folder is no longer available")
        return self.repository.restore_collection("source", source_id)

    def index(self, source_id: str, *, defer: bool = False) -> JobRecord:
        root = self.repository.source_root(source_id)
        source = self.repository.source(source_id)
        if root is None or source is None:
            raise KeyError(f"unknown Local source: {source_id}")
        job = JobRecord(
            job_id=f"job:{monotonic_ulid()}",
            kind="local_source_index",
            state="queued",
            stage="Waiting to index",
            progress=0,
            checkpoint={"source_id": source_id, "source_revision": source["revision"]},
            last_activity_at=utc_now(),
            status_message="Waiting to inspect the selected folder",
        )
        self.repository.save_job(job)
        with self.repository.connect() as conn:
            conn.execute(
                "UPDATE local_sources_v14 SET status='indexing', updated_at=? WHERE source_id=?",
                (utc_now(), source_id),
            )
        self.repository.append_job_event(
            job.job_id,
            "queued",
            {"stage": job.stage, "message": job.status_message},
            event_id=event_id(),
        )
        if defer:
            return job
        return self.run_index(job.job_id)

    def run_index(self, job_id: str) -> JobRecord:
        job = self.repository.get_job(job_id)
        if job is None or job.kind != "local_source_index":
            raise KeyError(f"unknown Local indexing job: {job_id}")
        checkpoint = job.checkpoint or {}
        source_id = str(checkpoint.get("source_id") or "")
        root = self.repository.source_root(source_id)
        source = self.repository.source(source_id)
        if root is None or source is None:
            raise KeyError(f"unknown Local source: {source_id}")
        job.state = "running"
        job.stage = "Indexing folder"
        job.progress = 0.1
        job.status_message = "Reading supported files and updating the paper inventory"
        job.last_activity_at = utc_now()
        job.updated_at = job.last_activity_at
        self.repository.save_job(job)
        self.repository.append_job_event(
            job.job_id,
            "progress",
            {"stage": job.stage, "message": job.status_message, "progress": job.progress},
            event_id=event_id(),
        )
        try:
            started = time.monotonic()

            def on_progress(completed: int, total: int, report: Any | None) -> bool:
                latest = self.repository.get_job(job.job_id)
                if latest is not None and latest.state == "cancelling":
                    return False
                job.completed_units = completed
                job.total_units = total
                job.progress = 0.1 + 0.8 * completed / max(1, total)
                job.elapsed_seconds = round(time.monotonic() - started, 1)
                job.eta_seconds = (
                    round(job.elapsed_seconds / completed * (total - completed), 1)
                    if completed >= 3 and total > completed
                    else None
                )
                job.status_message = (
                    f"Inspected {completed} of {total} files"
                    if report is not None
                    else f"Found {total} filesystem entries to inspect"
                )
                job.last_activity_at = utc_now()
                job.updated_at = job.last_activity_at
                self.repository.save_job(job)
                if completed == 0 or completed == total or completed % 5 == 0:
                    self.repository.append_job_event(
                        job.job_id,
                        "progress",
                        {
                            "stage": job.stage,
                            "message": job.status_message,
                            "progress": job.progress,
                            "completed_units": completed,
                            "total_units": total,
                            "elapsed_seconds": job.elapsed_seconds,
                            "eta_seconds": job.eta_seconds,
                        },
                        event_id=event_id(),
                    )
                return True

            result = LocalCorpusIngestor(self.storage).ingest(
                root,
                config=LocalCorpusConfig(max_files=500, follow_symlinks=False),
                progress_callback=on_progress,
            )
            latest = self.repository.get_job(job.job_id)
            if latest is not None and latest.state == "cancelling":
                job.state = "cancelled"
                job.stage = "Cancelled"
                job.status_message = "Folder indexing was cancelled before inventory update"
                job.progress = latest.progress
                job.updated_at = utc_now()
                job.last_activity_at = job.updated_at
                self.repository.save_job(job)
                self.repository.append_job_event(
                    job.job_id,
                    "cancelled",
                    {"stage": job.stage, "message": job.status_message},
                    event_id=event_id(),
                )
                return job
            reports_by_uri = {report.uri: report for report in result.local_diagnostics.reports}
            managed_metadata_paths = {
                "README.txt",
                "manifest.json",
                ".principia-layout-v2-receipt.json",
            }
            if str(source.get("source_kind") or "") == "managed":
                # These files describe Principia's source container; they are
                # never scientific documents.  Remove rows created by older
                # indexers so a clean managed folder truthfully contains zero
                # extractable papers.
                with self.repository.connect() as conn:
                    placeholders = ",".join("?" for _ in managed_metadata_paths)
                    conn.execute(
                        f"DELETE FROM local_source_documents WHERE source_id=? "
                        f"AND portable_relative_uri IN ({placeholders})",
                        (source_id, *sorted(managed_metadata_paths)),
                    )
            manifest_documents: dict[str, dict[str, Any]] = {}
            manifest_path = root / "manifest.json"
            if manifest_path.is_file():
                try:
                    source_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    if source_manifest.get("schema_version") == "principia-local-source-v1":
                        manifest_documents = {
                            str(
                                item.get("portable_relative_uri") or item.get("relative_path")
                            ): item
                            for item in source_manifest.get("documents") or []
                            if item.get("portable_relative_uri") or item.get("relative_path")
                        }
                except (OSError, ValueError, TypeError):
                    manifest_documents = {}
            next_revision = int(source["revision"]) + 1
            saved = 0
            for work in result.items:
                report = reports_by_uri.get(work.url)
                if report is None:
                    continue
                relative_path = str(report.relative_path)
                if (
                    str(source.get("source_kind") or "") == "managed"
                    and relative_path in managed_metadata_paths
                ):
                    continue
                manifest_document = manifest_documents.get(relative_path)
                if manifest_documents and manifest_document is None:
                    # A managed source manifest identifies the authoritative raw
                    # representation. Ignore normalized/metadata sidecars as
                    # separate papers.
                    continue
                work_id = work.id
                if manifest_document is not None:
                    canonical_work_id = str(manifest_document.get("work_id") or "")
                    if canonical_work_id and self.storage.get_work(canonical_work_id) is not None:
                        work_id = canonical_work_id
                        with self.repository.connect() as conn:
                            conn.execute(
                                "UPDATE source_assets SET work_id=? "
                                "WHERE work_id=? AND portable_uri=?",
                                (canonical_work_id, work.id, report.uri),
                            )
                document_id = (
                    "doc:" + hashlib.sha256(f"{source_id}:{work_id}".encode()).hexdigest()[:26]
                )
                self.repository.save_source_document(
                    {
                        "document_id": document_id,
                        "source_id": source_id,
                        "work_id": work_id,
                        "portable_relative_uri": relative_path,
                        "content_sha256": report.byte_sha256,
                        "content_byte_size": report.byte_size,
                        "parse_status": report.status,
                        "extraction_eligible": report.status in {"accepted", "cached"},
                        "principle_count": 0,
                        "last_indexed_revision": next_revision,
                    }
                )
                saved += 1
            linked_principles = self.repository.link_candidates_to_source_by_work(source_id)
            with self.repository.connect() as conn:
                conn.execute(
                    """
                    UPDATE local_sources_v14 SET revision=?, updated_at=?, status='ready'
                    WHERE source_id=?
                    """,
                    (next_revision, utc_now(), source_id),
                )
            diagnostics = result.local_diagnostics.model_dump(mode="json")
            sidecar_receipt = self.isolate_derived_sidecars()
            job.state = "succeeded"
            job.stage = "Indexed"
            job.progress = 1.0
            job.completed_units = saved
            job.total_units = int(diagnostics["discovered_count"])
            job.status_message = f"Indexed {saved} usable papers"
            job.result = {
                "source_id": source_id,
                "source_revision": next_revision,
                "document_count": saved,
                "discovered_count": diagnostics["discovered_count"],
                "accepted_count": diagnostics["accepted_count"],
                "cached_count": diagnostics["cached_count"],
                "skipped_count": diagnostics["skipped_count"],
                "failed_count": diagnostics["failed_count"],
                "linked_principle_count": linked_principles,
                "isolated_sidecar_count": sidecar_receipt["moved_sidecars"],
            }
        except Exception as exc:
            job.state = "failed"
            job.stage = "failed"
            job.status_message = "The folder could not be indexed"
            job.error = {
                "code": "local_source_index_failed",
                "category": "local_source",
                "message": str(exc),
                "retryable": True,
            }
            with self.repository.connect() as conn:
                conn.execute(
                    "UPDATE local_sources_v14 SET status='index_failed', updated_at=? WHERE source_id=?",
                    (utc_now(), source_id),
                )
        job.updated_at = utc_now()
        job.last_activity_at = job.updated_at
        self.repository.save_job(job)
        self.repository.append_job_event(
            job.job_id,
            "completed" if job.state == "succeeded" else "failed",
            {
                "stage": job.stage,
                "message": job.status_message,
                "progress": job.progress,
            },
            event_id=event_id(),
        )
        return job

    def reveal(self, source_id: str) -> dict[str, Any]:
        root = self.repository.source_root(source_id)
        source = self.repository.source(source_id)
        if root is None or source is None:
            raise KeyError(f"unknown Local source: {source_id}")
        if not root.is_dir():
            raise FileNotFoundError("the registered Local source is currently unavailable")
        if sys.platform == "darwin":
            command = ["open", str(root)]
        elif sys.platform == "win32":
            command = ["explorer", str(root)]
        elif shutil.which("xdg-open"):
            command = ["xdg-open", str(root)]
        else:
            raise RuntimeError("Reveal is unavailable on this system")
        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {
            "source_id": source_id,
            "display_location": source["display_location"],
            "revealed": True,
        }

    def import_paths(self, source_id: str, paths: list[str]) -> dict[str, Any]:
        root = self.repository.source_root(source_id)
        source = self.repository.source(source_id)
        if root is None or source is None:
            raise KeyError(f"unknown Local source: {source_id}")
        destination = root / "papers"
        destination.mkdir(parents=True, exist_ok=True, mode=0o700)
        total = 0
        imported: list[str] = []
        for raw in paths:
            path = Path(raw).expanduser()
            if path.is_symlink():
                raise PermissionError("symbolic-link imports are not allowed")
            try:
                path = path.resolve(strict=True)
            except OSError as exc:
                raise FileNotFoundError("an imported file is unavailable") from exc
            if not path.is_file():
                raise ValueError("imports must be regular files")
            size = path.stat().st_size
            if size > 50 * 1024 * 1024 or total + size > 1024 * 1024 * 1024:
                raise ValueError("the import exceeds Local source size limits")
            body = path.read_bytes()
            total += len(body)
            suffix = path.suffix.casefold()[:12]
            safe_name = _safe_slug(path.stem)[:80]
            digest = hashlib.sha256(body).hexdigest()
            target = destination / f"{safe_name}-{digest[:8]}{suffix}"
            _atomic_private_write(target, body)
            imported.append(target.relative_to(root).as_posix())
        index_job = self.index(source_id)
        return {
            "source_id": source_id,
            "imported_count": len(imported),
            "imported_documents": imported,
            "index_job": index_job.model_dump(mode="json"),
        }

    def selection_digest(
        self, *, source_id: str, source_revision: int, document_ids: list[str]
    ) -> str:
        return canonical_sha256(
            {
                "source_id": source_id,
                "source_revision": source_revision,
                "document_ids": document_ids,
            }
        )
