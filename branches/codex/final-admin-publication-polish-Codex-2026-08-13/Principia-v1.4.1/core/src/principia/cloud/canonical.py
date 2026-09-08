from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal

from .._sqlite import connect_sqlite
from ..domain.hashing import (
    canonical_json_bytes,
    canonical_sha256,
    digest_records,
    file_sha256,
    loads_strict,
)
from .models_v1 import (
    CloudDeltaManifest,
    CloudManifest,
    EmbeddingContract,
    PrincipleRevision,
    PrincipleWorkLink,
    RelationRevision,
    WorkRevision,
    reject_forbidden_cloud_fields,
)

RecordKind = Literal["works", "principles", "principle-work", "relations"]
KIND_MODELS = {
    "works": WorkRevision,
    "principles": PrincipleRevision,
    "principle-work": PrincipleWorkLink,
    "relations": RelationRevision,
}
PCG_ENTRIES = {
    "manifest.json",
    "cloud.sqlite",
    "work-vectors.f16",
    "principle-vectors.f16",
    "README.txt",
}
PCD_ENTRIES = {"manifest.json", "changes.jsonl", "work-vectors.f16", "principle-vectors.f16"}
MAX_SNAPSHOT_BYTES = 512 * 1024 * 1024


def record_identity(kind: RecordKind, payload: dict[str, Any]) -> str:
    if kind == "works":
        return str(payload["work_id"])
    if kind == "principles":
        return str(payload["principle_id"])
    if kind == "principle-work":
        return ":".join(
            [
                str(payload["principle_id"]),
                str(payload["principle_revision"]),
                str(payload["work_id"]),
                str(payload.get("role") or "evidence"),
                str(payload.get("page") or ""),
                str(payload.get("section") or ""),
                str(payload.get("evidence_digest") or ""),
            ]
        )
    return str(payload["relation_id"])


def shard_name(identifier: str) -> str:
    return f"{hashlib.sha256(identifier.encode('utf-8')).hexdigest()[:2]}.jsonl"


def normalize_record(kind: RecordKind, payload: dict[str, Any]) -> dict[str, Any]:
    reject_forbidden_cloud_fields(payload)
    model = KIND_MODELS[kind].model_validate(payload)
    normalized = model.model_dump(mode="json")
    if "content_digest" in normalized and not normalized["content_digest"]:
        normalized["content_digest"] = canonical_sha256(
            {key: value for key, value in normalized.items() if key != "content_digest"}
        )
    return normalized


def _sort_key(kind: RecordKind, payload: dict[str, Any]) -> tuple[Any, ...]:
    identifier = record_identity(kind, payload)
    revision = int(payload.get("revision") or payload.get("principle_revision") or 0)
    return identifier, revision, canonical_json_bytes(payload)


class CanonicalCloudRepository:
    """Reviewable, deterministically sharded source of truth for Global Cloud."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.data_root = self.root / "data" / "v1"

    def records(self, kind: RecordKind) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        directory = self.data_root / kind
        if not directory.exists():
            return rows
        for path in sorted(directory.glob("*.jsonl")):
            shard_rows: list[dict[str, Any]] = []
            for line_number, raw in enumerate(path.read_bytes().splitlines(), start=1):
                if not raw.strip():
                    continue
                value = loads_strict(raw)
                if not isinstance(value, dict):
                    raise ValueError(f"{path.name}:{line_number} is not a JSON object")
                normalized = normalize_record(kind, value)
                expected = shard_name(record_identity(kind, normalized))
                if path.name != expected:
                    raise ValueError(
                        f"{path.name}:{line_number} belongs in shard {expected}"
                    )
                shard_rows.append(normalized)
            if shard_rows != sorted(shard_rows, key=lambda row: _sort_key(kind, row)):
                raise ValueError(f"{kind} shard {path.name} is not in canonical order")
            rows.extend(shard_rows)
        return rows

    def all_records(self) -> dict[RecordKind, list[dict[str, Any]]]:
        return {kind: self.records(kind) for kind in KIND_MODELS}

    def validate(self) -> dict[str, Any]:
        records = self.all_records()
        works = {row["work_id"] for row in records["works"]}
        principles = {
            (row["principle_id"], int(row["revision"])) for row in records["principles"]
        }
        current_ids = {row["principle_id"] for row in records["principles"]}
        if len({(row["work_id"], int(row["revision"])) for row in records["works"]}) != len(
            records["works"]
        ):
            raise ValueError("duplicate Work revision")
        if len(principles) != len(records["principles"]):
            raise ValueError("duplicate Principle revision")
        if len({record_identity("principle-work", row) for row in records["principle-work"]}) != len(
            records["principle-work"]
        ):
            raise ValueError("duplicate Principle–Work provenance link")
        strong_identifiers: dict[tuple[str, str], str] = {}
        for row in records["works"]:
            for field in ("doi", "arxiv_id", "pmid", "pmcid", "openalex_id", "semantic_scholar_id"):
                value = str(row.get(field) or "").strip().casefold()
                if not value:
                    continue
                previous = strong_identifiers.setdefault((field, value), str(row["work_id"]))
                if previous != row["work_id"]:
                    raise ValueError(f"duplicate strong Work identifier: {field}:{value}")
        for row in records["principle-work"]:
            if row["work_id"] not in works:
                raise ValueError(f"Principle link references unknown Work: {row['work_id']}")
            key = (row["principle_id"], int(row["principle_revision"]))
            if key not in principles:
                raise ValueError(f"Principle link references unknown revision: {key}")
        for row in records["relations"]:
            if row["source_principle_id"] not in current_ids:
                raise ValueError("relation source is unknown")
            if row["target_principle_id"] not in current_ids and not (
                row.get("unresolved_target") and row.get("status") == "retired"
            ):
                raise ValueError("relation target is unknown")
        logical_records = [
            {"kind": kind, "payload": row}
            for kind, rows in records.items()
            for row in rows
        ]
        return {
            "schema_version": "principia-global-validation-v1",
            "valid": True,
            "content_digest": digest_records(logical_records),
            "counts": {kind: len(rows) for kind, rows in records.items()},
        }

    def write_records(self, kind: RecordKind, records: Iterable[dict[str, Any]]) -> None:
        normalized = [normalize_record(kind, record) for record in records]
        grouped: dict[str, list[dict[str, Any]]] = {}
        for record in normalized:
            grouped.setdefault(shard_name(record_identity(kind, record)), []).append(record)
        directory = self.data_root / kind
        directory.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=f".{kind}.", dir=directory.parent))
        try:
            for name in (f"{value:02x}.jsonl" for value in range(256)):
                rows = grouped.get(name, [])
                body = b"".join(
                    canonical_json_bytes(row) + b"\n"
                    for row in sorted(rows, key=lambda row: _sort_key(kind, row))
                )
                (temporary / name).write_bytes(body)
            backup = directory.with_name(f".{directory.name}.previous")
            if backup.exists():
                shutil.rmtree(backup)
            if directory.exists():
                os.replace(directory, backup)
            os.replace(temporary, directory)
            if backup.exists():
                shutil.rmtree(backup)
        except BaseException:
            shutil.rmtree(temporary, ignore_errors=True)
            raise


def _initialize_snapshot_database(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA journal_mode=DELETE;
        PRAGMA foreign_keys=ON;
        CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
        CREATE TABLE works(
            work_id TEXT NOT NULL, revision INTEGER NOT NULL, title TEXT NOT NULL,
            abstract TEXT NOT NULL, authors_json TEXT NOT NULL, institutions_json TEXT NOT NULL,
            venue TEXT NOT NULL, year INTEGER, doi TEXT NOT NULL, arxiv_id TEXT NOT NULL,
            pmid TEXT NOT NULL, pmcid TEXT NOT NULL, openalex_id TEXT NOT NULL,
            semantic_scholar_id TEXT NOT NULL, landing_url TEXT NOT NULL,
            full_text_status TEXT NOT NULL, page_count INTEGER, pdf_bytes INTEGER,
            content_digest TEXT NOT NULL, payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            PRIMARY KEY(work_id, revision)
        ) WITHOUT ROWID;
        CREATE TABLE current_works AS SELECT * FROM works WHERE 0;
        CREATE TABLE principles(
            principle_id TEXT NOT NULL, revision INTEGER NOT NULL, area TEXT NOT NULL,
            title TEXT NOT NULL, claim TEXT NOT NULL, kind TEXT NOT NULL,
            maturity TEXT NOT NULL, status TEXT NOT NULL, review_status TEXT NOT NULL,
            tags_json TEXT NOT NULL, content_digest TEXT NOT NULL, payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            PRIMARY KEY(principle_id, revision)
        ) WITHOUT ROWID;
        CREATE TABLE current_principles AS SELECT * FROM principles WHERE 0;
        CREATE TABLE principle_work(
            link_id TEXT PRIMARY KEY, principle_id TEXT NOT NULL, principle_revision INTEGER NOT NULL,
            work_id TEXT NOT NULL, role TEXT NOT NULL, page INTEGER, section TEXT NOT NULL,
            evidence_digest TEXT NOT NULL, payload_json TEXT NOT NULL,
            FOREIGN KEY(principle_id, principle_revision) REFERENCES principles(principle_id, revision)
        ) WITHOUT ROWID;
        CREATE TABLE relations(
            relation_id TEXT NOT NULL, revision INTEGER NOT NULL,
            source_principle_id TEXT NOT NULL, target_principle_id TEXT NOT NULL,
            relation_type TEXT NOT NULL, rationale TEXT NOT NULL, strength REAL NOT NULL,
            status TEXT NOT NULL, unresolved_target INTEGER NOT NULL, payload_json TEXT NOT NULL,
            PRIMARY KEY(relation_id, revision)
        ) WITHOUT ROWID;
        CREATE TABLE work_vector_ordinals(work_id TEXT PRIMARY KEY, ordinal INTEGER NOT NULL) WITHOUT ROWID;
        CREATE TABLE principle_vector_ordinals(principle_id TEXT PRIMARY KEY, ordinal INTEGER NOT NULL) WITHOUT ROWID;
        CREATE VIRTUAL TABLE work_fts USING fts5(
            work_id UNINDEXED, title, abstract, authors, institutions, venue,
            tokenize='unicode61 remove_diacritics 2'
        );
        CREATE VIRTUAL TABLE principle_fts USING fts5(
            principle_id UNINDEXED, title, claim, area, tags,
            tokenize='unicode61 remove_diacritics 2'
        );
        CREATE INDEX idx_works_year ON works(year, venue);
        CREATE UNIQUE INDEX idx_current_works_id ON current_works(work_id);
        CREATE INDEX idx_current_works_updated ON current_works(updated_at DESC, work_id);
        CREATE INDEX idx_current_works_filters ON current_works(year, venue, full_text_status, work_id);
        CREATE UNIQUE INDEX idx_current_principles_id ON current_principles(principle_id);
        CREATE INDEX idx_current_principles_updated ON current_principles(updated_at DESC, principle_id);
        CREATE INDEX idx_current_principles_area ON current_principles(area, status, principle_id);
        CREATE INDEX idx_principle_work_work ON principle_work(work_id, principle_id);
        CREATE INDEX idx_relations_source ON relations(source_principle_id, status);
        """
    )


def build_cloud_snapshot(
    canonical_root: str | Path,
    output: str | Path,
    *,
    release_id: str,
    commit_sha: str = "",
    work_vectors: bytes = b"",
    principle_vectors: bytes = b"",
    created_at: str | None = None,
) -> CloudManifest:
    source = CanonicalCloudRepository(canonical_root)
    validation = source.validate()
    records = source.all_records()
    output_path = Path(output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    build_root = Path(tempfile.mkdtemp(prefix="principia-global-build."))
    try:
        database = build_root / "cloud.sqlite"
        with connect_sqlite(database) as conn:
            conn.row_factory = sqlite3.Row
            _initialize_snapshot_database(conn)
            for row in records["works"]:
                a = row["availability"]
                conn.execute(
                    "INSERT INTO works VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        row["work_id"], row["revision"], row["title"], row["abstract"],
                        json.dumps(row["authors"], ensure_ascii=False, separators=(",", ":")),
                        json.dumps(row["institutions"], ensure_ascii=False, separators=(",", ":")),
                        row["venue"], row["year"], row["doi"], row["arxiv_id"], row["pmid"],
                        row["pmcid"], row["openalex_id"], row["semantic_scholar_id"],
                        row["landing_url"], a["status"], a["page_count"], a["pdf_bytes"],
                        row["content_digest"], json.dumps(row, ensure_ascii=False, sort_keys=True),
                        row["created_at"], row["updated_at"],
                    ),
                )
            for row in records["principles"]:
                conn.execute(
                    "INSERT INTO principles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        row["principle_id"], row["revision"], row["area"], row["title"],
                        row["claim"], row["kind"], row["maturity"], row["status"],
                        row["review_status"], json.dumps(row["tags"], ensure_ascii=False),
                        row["content_digest"], json.dumps(row, ensure_ascii=False, sort_keys=True),
                        row["created_at"], row["updated_at"],
                    ),
                )
            for row in records["principle-work"]:
                conn.execute(
                    "INSERT INTO principle_work VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        canonical_sha256(row), row["principle_id"], row["principle_revision"], row["work_id"],
                        row["role"], row["page"], row["section"], row["evidence_digest"],
                        json.dumps(row, ensure_ascii=False, sort_keys=True),
                    ),
                )
            for row in records["relations"]:
                conn.execute(
                    "INSERT INTO relations VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        row["relation_id"], row["revision"], row["source_principle_id"],
                        row["target_principle_id"], row["relation_type"], row["rationale"],
                        row["strength"], row["status"], int(row["unresolved_target"]),
                        json.dumps(row, ensure_ascii=False, sort_keys=True),
                    ),
                )
            conn.execute(
                "INSERT INTO current_works SELECT w.* FROM works w JOIN ("
                "SELECT work_id, MAX(revision) revision FROM works GROUP BY work_id"
                ") latest USING(work_id, revision)"
            )
            conn.execute(
                "INSERT INTO current_principles SELECT p.* FROM principles p JOIN ("
                "SELECT principle_id, MAX(revision) revision FROM principles GROUP BY principle_id"
                ") latest USING(principle_id, revision)"
            )
            current_works = conn.execute("SELECT * FROM current_works ORDER BY work_id").fetchall()
            current_principles = conn.execute(
                "SELECT * FROM current_principles ORDER BY principle_id"
            ).fetchall()
            for ordinal, row in enumerate(current_works):
                conn.execute("INSERT INTO work_vector_ordinals VALUES (?,?)", (row["work_id"], ordinal))
                conn.execute(
                    "INSERT INTO work_fts VALUES (?,?,?,?,?,?)",
                    (
                        row["work_id"], row["title"], row["abstract"],
                        " ".join(json.loads(row["authors_json"])),
                        " ".join(json.loads(row["institutions_json"])), row["venue"],
                    ),
                )
            for ordinal, row in enumerate(current_principles):
                conn.execute(
                    "INSERT INTO principle_vector_ordinals VALUES (?,?)",
                    (row["principle_id"], ordinal),
                )
                conn.execute(
                    "INSERT INTO principle_fts VALUES (?,?,?,?,?)",
                    (
                        row["principle_id"], row["title"], row["claim"], row["area"],
                        " ".join(json.loads(row["tags_json"])),
                    ),
                )
            meta = {
                "format": "principia-global-snapshot-v1",
                "release_id": release_id,
                "content_digest": validation["content_digest"],
                "embedding_contract": EmbeddingContract().contract_id,
            }
            conn.executemany("INSERT INTO meta VALUES (?,?)", sorted(meta.items()))
            if conn.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("snapshot contains foreign-key errors")
            conn.commit()
            conn.execute("VACUUM")
        work_path = build_root / "work-vectors.f16"
        principle_path = build_root / "principle-vectors.f16"
        work_path.write_bytes(work_vectors)
        principle_path.write_bytes(principle_vectors)
        dimensions = 1024
        vectors_complete = (
            len(work_vectors) == len({row["work_id"] for row in records["works"]}) * dimensions * 2
            and len(principle_vectors)
            == len({row["principle_id"] for row in records["principles"]}) * dimensions * 2
        )
        manifest = CloudManifest(
            release_id=release_id,
            commit_sha=commit_sha,
            content_digest=validation["content_digest"],
            work_count=len({row["work_id"] for row in records["works"]}),
            principle_count=len({row["principle_id"] for row in records["principles"]}),
            principle_revision_count=len(records["principles"]),
            principle_work_count=len(records["principle-work"]),
            relation_count=len(records["relations"]),
            vectors_complete=vectors_complete,
            **({"created_at": created_at} if created_at else {}),
        )
        (build_root / "manifest.json").write_text(
            json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        (build_root / "README.txt").write_text(
            "Principia Global Cloud v1 snapshot. Contains metadata and Principles; no papers.\n",
            encoding="utf-8",
        )
        temporary = output_path.with_suffix(output_path.suffix + ".partial")
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name in sorted(PCG_ENTRIES):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (0o100644 & 0xFFFF) << 16
                archive.writestr(info, (build_root / name).read_bytes())
        # The archive digest belongs in the external release control document. An
        # archive cannot contain its own digest without changing that digest.
        manifest = manifest.model_copy(
            update={"snapshot_sha256": file_sha256(temporary), "snapshot_bytes": temporary.stat().st_size}
        )
        os.replace(temporary, output_path)
        return manifest
    finally:
        shutil.rmtree(build_root, ignore_errors=True)


def verify_cloud_snapshot(path: str | Path, *, expected_sha256: str = "") -> CloudManifest:
    snapshot = Path(path).expanduser().resolve()
    if not snapshot.is_file() or snapshot.stat().st_size > MAX_SNAPSHOT_BYTES:
        raise ValueError("Global Cloud snapshot is missing or exceeds its size limit")
    if expected_sha256 and file_sha256(snapshot) != expected_sha256:
        raise ValueError("Global Cloud snapshot digest does not match the control manifest")
    with zipfile.ZipFile(snapshot) as archive:
        names = set(archive.namelist())
        if names != PCG_ENTRIES:
            raise ValueError("Global Cloud snapshot contains unexpected entries")
        for info in archive.infolist():
            if info.is_dir() or info.filename.startswith(("/", "../")) or ".." in Path(info.filename).parts:
                raise ValueError("unsafe Global Cloud snapshot entry")
        manifest = CloudManifest.model_validate_json(archive.read("manifest.json"))
        work_vector_bytes = len(archive.read("work-vectors.f16"))
        principle_vector_bytes = len(archive.read("principle-vectors.f16"))
        if manifest.vectors_complete:
            expected_work_bytes = manifest.work_count * manifest.vector_dimensions * 2
            expected_principle_bytes = manifest.principle_count * manifest.vector_dimensions * 2
            if work_vector_bytes != expected_work_bytes:
                raise ValueError("Global Cloud Work vector dimensions do not match its manifest")
            if principle_vector_bytes != expected_principle_bytes:
                raise ValueError("Global Cloud Principle vector dimensions do not match its manifest")
        elif work_vector_bytes or principle_vector_bytes:
            raise ValueError("partial Global Cloud vector files are forbidden")
        temporary = Path(tempfile.mkdtemp(prefix="principia-global-verify."))
        try:
            archive.extract("cloud.sqlite", temporary)
            with connect_sqlite(f"file:{temporary / 'cloud.sqlite'}?mode=ro", uri=True) as conn:
                if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise ValueError("Global Cloud SQLite integrity check failed")
                if conn.execute("PRAGMA foreign_key_check").fetchall():
                    raise ValueError("Global Cloud SQLite foreign-key check failed")
                counts = {
                    "work_count": conn.execute("SELECT COUNT(*) FROM current_works").fetchone()[0],
                    "principle_count": conn.execute("SELECT COUNT(*) FROM current_principles").fetchone()[0],
                    "principle_revision_count": conn.execute("SELECT COUNT(*) FROM principles").fetchone()[0],
                    "principle_work_count": conn.execute("SELECT COUNT(*) FROM principle_work").fetchone()[0],
                    "relation_count": conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0],
                }
                for key, value in counts.items():
                    if int(getattr(manifest, key)) != int(value):
                        raise ValueError(f"Global Cloud count mismatch: {key}")
        finally:
            shutil.rmtree(temporary, ignore_errors=True)
    return manifest


def _snapshot_records(snapshot: Path) -> tuple[CloudManifest, dict[RecordKind, list[dict[str, Any]]]]:
    manifest = verify_cloud_snapshot(snapshot)
    temporary = Path(tempfile.mkdtemp(prefix="principia-global-records."))
    try:
        with zipfile.ZipFile(snapshot) as archive:
            archive.extract("cloud.sqlite", temporary)
        with connect_sqlite(f"file:{temporary / 'cloud.sqlite'}?mode=ro", uri=True) as conn:
            output: dict[RecordKind, list[dict[str, Any]]] = {}
            for kind, table in (
                ("works", "works"),
                ("principles", "principles"),
                ("principle-work", "principle_work"),
                ("relations", "relations"),
            ):
                output[kind] = [json.loads(row[0]) for row in conn.execute(
                    f"SELECT payload_json FROM {table} ORDER BY payload_json"
                )]
        return manifest, output
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def build_cloud_delta(previous: str | Path, target: str | Path, output: str | Path) -> CloudDeltaManifest:
    previous_path = Path(previous).expanduser().resolve()
    target_path = Path(target).expanduser().resolve()
    base_manifest, base_records = _snapshot_records(previous_path)
    target_manifest, target_records = _snapshot_records(target_path)
    changes: list[dict[str, Any]] = []
    for kind in KIND_MODELS:
        before = {record_identity(kind, row): row for row in base_records[kind]}
        after = {record_identity(kind, row): row for row in target_records[kind]}
        for identifier in sorted(before.keys() - after.keys()):
            changes.append({"kind": kind, "op": "delete", "id": identifier})
        for identifier in sorted(after):
            if identifier not in before or canonical_json_bytes(before[identifier]) != canonical_json_bytes(after[identifier]):
                changes.append({"kind": kind, "op": "upsert", "id": identifier, "payload": after[identifier]})
    delta = CloudDeltaManifest(
        base_release_id=base_manifest.release_id,
        target_release_id=target_manifest.release_id,
        base_content_digest=base_manifest.content_digest,
        target_content_digest=target_manifest.content_digest,
        target_commit_sha=target_manifest.commit_sha,
        target_created_at=target_manifest.created_at,
        target_snapshot_sha256=file_sha256(target_path),
        work_count=target_manifest.work_count,
        principle_count=target_manifest.principle_count,
        principle_revision_count=target_manifest.principle_revision_count,
        principle_work_count=target_manifest.principle_work_count,
        relation_count=target_manifest.relation_count,
        vectors_complete=target_manifest.vectors_complete,
        change_count=len(changes),
    )
    with zipfile.ZipFile(target_path) as target_archive:
        entries = {
            "manifest.json": json.dumps(delta.model_dump(mode="json"), sort_keys=True, indent=2).encode() + b"\n",
            "changes.jsonl": b"".join(canonical_json_bytes(row) + b"\n" for row in changes),
            "work-vectors.f16": target_archive.read("work-vectors.f16"),
            "principle-vectors.f16": target_archive.read("principle-vectors.f16"),
        }
    output_path = Path(output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".partial")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100644 & 0xFFFF) << 16
            archive.writestr(info, entries[name])
    os.replace(temporary, output_path)
    return delta


def apply_cloud_delta(base: str | Path, delta: str | Path, output: str | Path) -> CloudManifest:
    base_path = Path(base).expanduser().resolve()
    delta_path = Path(delta).expanduser().resolve()
    base_manifest, records = _snapshot_records(base_path)
    with zipfile.ZipFile(delta_path) as archive:
        if set(archive.namelist()) != PCD_ENTRIES:
            raise ValueError("Global Cloud delta contains unexpected entries")
        manifest = CloudDeltaManifest.model_validate_json(archive.read("manifest.json"))
        if manifest.base_release_id != base_manifest.release_id or manifest.base_content_digest != base_manifest.content_digest:
            raise ValueError("Global Cloud delta does not apply to the active release")
        changes = [loads_strict(line) for line in archive.read("changes.jsonl").splitlines() if line.strip()]
        work_vectors = archive.read("work-vectors.f16")
        principle_vectors = archive.read("principle-vectors.f16")
    if len(changes) != manifest.change_count:
        raise ValueError("Global Cloud delta change count mismatch")
    by_kind = {
        kind: {record_identity(kind, row): row for row in values}
        for kind, values in records.items()
    }
    for change in changes:
        kind = str(change.get("kind") or "")
        if kind not in KIND_MODELS or change.get("op") not in {"upsert", "delete"}:
            raise ValueError("invalid Global Cloud delta operation")
        identifier = str(change.get("id") or "")
        if change["op"] == "delete":
            by_kind[kind].pop(identifier, None)
        else:
            payload = normalize_record(kind, change.get("payload") or {})
            if record_identity(kind, payload) != identifier:
                raise ValueError("Global Cloud delta identity mismatch")
            by_kind[kind][identifier] = payload
    temporary_root = Path(tempfile.mkdtemp(prefix="principia-global-apply."))
    try:
        canonical = temporary_root / "canonical"
        repository = CanonicalCloudRepository(canonical)
        for kind in KIND_MODELS:
            repository.write_records(kind, by_kind[kind].values())
        result = build_cloud_snapshot(
            canonical,
            output,
            release_id=manifest.target_release_id,
            commit_sha=manifest.target_commit_sha,
            work_vectors=work_vectors,
            principle_vectors=principle_vectors,
            created_at=manifest.target_created_at,
        )
        if result.content_digest != manifest.target_content_digest:
            raise ValueError("Global Cloud delta produced the wrong logical digest")
        if manifest.target_snapshot_sha256 and file_sha256(output) != manifest.target_snapshot_sha256:
            raise ValueError("Global Cloud delta output differs from the published full snapshot")
        return result
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)
