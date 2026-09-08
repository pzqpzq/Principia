from __future__ import annotations

import json
import os
import shutil
import sqlite3
import stat
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .._sqlite import connect_sqlite
from .._version import __version__
from ..domain import AreaManifest, CatalogEntry, PrincipleCapsule
from ..domain.hashing import canonical_sha256, digest_records, file_sha256, loads_strict

PCP_ENTRIES = {"manifest.json", "area.sqlite", "README.txt"}
MAX_ARTIFACT_BYTES = 256 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100


class PackageIntegrityError(ValueError):
    pass


@dataclass(frozen=True)
class PackageBuildReceipt:
    path: Path
    manifest: AreaManifest
    artifact_sha256: str
    artifact_bytes: int
    receipt_digest: str

    def catalog_entry(self, artifact_url: str) -> CatalogEntry:
        return CatalogEntry(
            area=self.manifest.area,
            display_name=self.manifest.display_name,
            package_version=self.manifest.package_version,
            artifact_url=artifact_url,
            artifact_sha256=self.artifact_sha256,
            artifact_bytes=self.artifact_bytes,
            content_digest=self.manifest.content_digest,
            principle_count=self.manifest.principle_count,
            relation_count=self.manifest.relation_count,
            released_at=self.manifest.created_at,
            content_class=self.manifest.content_class,
            source_text_included=self.manifest.source_text_included,
        )


@dataclass(frozen=True)
class VerifiedPackage:
    path: Path
    manifest: AreaManifest
    artifact_sha256: str
    artifact_bytes: int


def _capsule_payload(capsule: PrincipleCapsule) -> dict[str, Any]:
    payload = capsule.model_dump(mode="json")
    if not payload["content_digest"]:
        payload["content_digest"] = canonical_sha256(
            {key: value for key, value in payload.items() if key != "content_digest"}
        )
    return payload


def _create_area_db(path: Path, capsules: list[PrincipleCapsule]) -> None:
    with connect_sqlite(path) as conn:
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("PRAGMA foreign_keys=ON")
        _initialize_area_schema(conn)
        work_payloads: dict[str, dict[str, Any]] = {}
        for capsule in sorted(capsules, key=lambda item: (item.principle_id, item.version)):
            payload = _capsule_payload(capsule)
            conn.execute(
                "INSERT INTO principles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    capsule.principle_id,
                    capsule.version,
                    capsule.area,
                    capsule.title,
                    capsule.claim,
                    capsule.kind.value,
                    capsule.maturity.value,
                    capsule.status,
                    payload["content_digest"],
                    json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    capsule.created_at,
                    capsule.updated_at,
                ),
            )
            for work in capsule.source_references:
                work_payloads.setdefault(work.work_id, work.model_dump(mode="json"))
                conn.execute(
                    "INSERT INTO principle_work VALUES (?, ?, ?, ?)",
                    (capsule.principle_id, capsule.version, work.work_id, work.role),
                )
            for index, relation in enumerate(capsule.relations):
                conn.execute(
                    "INSERT INTO relations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        capsule.principle_id,
                        capsule.version,
                        index,
                        relation.target_principle_id,
                        relation.target_area,
                        relation.minimum_package_version,
                        relation.relation_type.value,
                        relation.strength,
                        relation.model_dump_json(),
                    ),
                )
            for index, trace in enumerate(capsule.generation_trace):
                conn.execute(
                    "INSERT INTO generation_trace VALUES (?, ?, ?, ?, ?)",
                    (
                        capsule.principle_id,
                        capsule.version,
                        index,
                        trace.event_id,
                        trace.model_dump_json(),
                    ),
                )
        for work_id, payload in sorted(work_payloads.items()):
            conn.execute(
                "INSERT INTO works VALUES (?, ?, ?, ?, ?)",
                (
                    work_id,
                    payload["title"],
                    payload["url"],
                    payload["doi"],
                    json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                ),
            )
        for capsule in sorted(capsules, key=lambda item: (item.principle_id, item.version)):
            conn.execute(
                "INSERT INTO principle_fts VALUES (?, ?, ?, ?, ?, ?)",
                (
                    capsule.principle_id,
                    capsule.version,
                    capsule.title,
                    capsule.claim,
                    capsule.area,
                    " ".join(sorted(capsule.tags)),
                ),
            )
        _finalize_area_db(conn, revision_count=len(capsules))


def _initialize_area_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
            CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
            CREATE TABLE principles(
                principle_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                area TEXT NOT NULL,
                title TEXT NOT NULL,
                claim TEXT NOT NULL,
                kind TEXT NOT NULL,
                maturity TEXT NOT NULL,
                status TEXT NOT NULL,
                content_digest TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(principle_id, version)
            ) WITHOUT ROWID;
            CREATE TABLE works(
                work_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                doi TEXT NOT NULL,
                payload_json TEXT NOT NULL
            ) WITHOUT ROWID;
            CREATE TABLE principle_work(
                principle_id TEXT NOT NULL,
                principle_version INTEGER NOT NULL,
                work_id TEXT NOT NULL,
                role TEXT NOT NULL,
                PRIMARY KEY(principle_id, principle_version, work_id, role),
                FOREIGN KEY(principle_id, principle_version)
                    REFERENCES principles(principle_id, version) DEFERRABLE INITIALLY DEFERRED,
                FOREIGN KEY(work_id) REFERENCES works(work_id) DEFERRABLE INITIALLY DEFERRED
            ) WITHOUT ROWID;
            CREATE TABLE relations(
                source_principle_id TEXT NOT NULL,
                source_version INTEGER NOT NULL,
                relation_index INTEGER NOT NULL,
                target_principle_id TEXT NOT NULL,
                target_area TEXT,
                minimum_package_version TEXT,
                relation_type TEXT NOT NULL,
                strength REAL NOT NULL,
                payload_json TEXT NOT NULL,
                PRIMARY KEY(source_principle_id, source_version, relation_index),
                FOREIGN KEY(source_principle_id, source_version)
                    REFERENCES principles(principle_id, version)
            ) WITHOUT ROWID;
            CREATE TABLE generation_trace(
                principle_id TEXT NOT NULL,
                principle_version INTEGER NOT NULL,
                trace_index INTEGER NOT NULL,
                event_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                PRIMARY KEY(principle_id, principle_version, trace_index),
                FOREIGN KEY(principle_id, principle_version)
                    REFERENCES principles(principle_id, version)
            ) WITHOUT ROWID;
            CREATE VIRTUAL TABLE principle_fts USING fts5(
                principle_id UNINDEXED,
                version UNINDEXED,
                title,
                claim,
                area,
                tags,
                tokenize='unicode61 remove_diacritics 2'
            );
            CREATE VIEW current_principles AS
                SELECT p.* FROM principles p
                JOIN (
                    SELECT principle_id, MAX(version) AS version
                    FROM principles GROUP BY principle_id
                ) latest USING(principle_id, version);
        """
    )


def _finalize_area_db(conn: sqlite3.Connection, *, revision_count: int) -> None:
    principle_count = int(
        conn.execute("SELECT COUNT(DISTINCT principle_id) FROM principles").fetchone()[0]
    )
    conn.executemany(
        "INSERT INTO meta VALUES (?, ?)",
        [
            ("format", "principia-area-v1"),
            ("framework_version", __version__),
            ("principle_count", str(principle_count)),
            ("revision_count", str(revision_count)),
        ],
    )
    problems = conn.execute("PRAGMA foreign_key_check").fetchall()
    if problems:
        raise PackageIntegrityError(f"area database contains foreign-key errors: {problems}")
    conn.commit()
    conn.execute("VACUUM")


def _zip_entry(path: Path, arcname: str) -> tuple[zipfile.ZipInfo, bytes]:
    info = zipfile.ZipInfo(arcname, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (0o100644 & 0xFFFF) << 16
    return info, path.read_bytes()


def build_pcp(
    output: str | Path,
    *,
    area: str,
    display_name: str,
    package_version: str,
    capsules: list[PrincipleCapsule],
    readme: str,
) -> PackageBuildReceipt:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not capsules:
        raise ValueError("a Principle package must contain at least one revision")
    if any(item.area != area for item in capsules):
        raise ValueError("every Principle must match the package area")
    keys = [(item.principle_id, item.version) for item in capsules]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate Principle revision")
    with tempfile.TemporaryDirectory(prefix="principia-pcp-build-") as temp:
        root = Path(temp)
        database_path = root / "area.sqlite"
        _create_area_db(database_path, capsules)
        logical_records = [_capsule_payload(item) for item in capsules]
        manifest = AreaManifest(
            area=area,
            display_name=display_name,
            package_version=package_version,
            principle_count=len({item.principle_id for item in capsules}),
            revision_count=len(capsules),
            relation_count=sum(len(item.relations) for item in capsules),
            work_count=len(
                {work.work_id for capsule in capsules for work in capsule.source_references}
            ),
            content_digest=digest_records(logical_records),
            area_sqlite_sha256=file_sha256(database_path),
            builder_version=__version__,
            python_version=sys.version.split()[0],
            sqlite_version=sqlite3.sqlite_version,
        )
        manifest_path = root / "manifest.json"
        manifest_path.write_text(
            json.dumps(
                manifest.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        readme_path = root / "README.txt"
        readme_path.write_text(readme.rstrip() + "\n", encoding="utf-8")
        partial = output_path.with_suffix(output_path.suffix + ".partial")
        with zipfile.ZipFile(partial, "w", compresslevel=9) as archive:
            for filename in sorted(PCP_ENTRIES):
                info, data = _zip_entry(root / filename, filename)
                archive.writestr(info, data)
        os.replace(partial, output_path)
    artifact_sha256 = file_sha256(output_path)
    receipt_payload = {
        "artifact_sha256": artifact_sha256,
        "artifact_bytes": output_path.stat().st_size,
        "manifest": manifest.model_dump(mode="json"),
    }
    return PackageBuildReceipt(
        path=output_path,
        manifest=manifest,
        artifact_sha256=artifact_sha256,
        artifact_bytes=output_path.stat().st_size,
        receipt_digest=canonical_sha256(receipt_payload),
    )


def build_candidate_pcp(
    output: str | Path,
    *,
    package_id: str,
    display_name: str,
    package_version: str,
    principles: list[dict[str, Any]],
    works: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    readme: str,
) -> PackageBuildReceipt:
    """Build a verified paper-free package of unassessed Candidate Principles.

    Candidate packages use the same immutable download, verification, registry,
    pin, and rollback machinery as reviewed Capsule packages.  Their manifest
    content class prevents the distribution channel from being mistaken for a
    human scientific review decision.
    """

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not principles:
        raise ValueError("a Candidate Principle package must contain at least one Principle")
    principle_ids = {str(item.get("principle_id") or "") for item in principles}
    if "" in principle_ids or len(principle_ids) != len(principles):
        raise ValueError("Candidate Principle IDs must be present and unique")
    work_by_id = {str(item.get("work_id") or ""): item for item in works}
    if "" in work_by_id or len(work_by_id) != len(works):
        raise ValueError("Candidate package Work IDs must be present and unique")
    relation_rows = [
        item
        for item in relations
        if str(item.get("source_principle_id") or "") in principle_ids
        and str(item.get("target_principle_id") or "")
    ]
    logical_records = sorted(principles, key=lambda item: str(item["principle_id"]))
    with tempfile.TemporaryDirectory(prefix="principia-candidate-pcp-build-") as temp:
        root = Path(temp)
        database_path = root / "area.sqlite"
        with connect_sqlite(database_path) as conn:
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.execute("PRAGMA foreign_keys=ON")
            _initialize_area_schema(conn)
            for principle in logical_records:
                references = list(principle.get("references") or [])
                referenced_ids = {str(item.get("work_id") or "") for item in references}
                missing = referenced_ids - set(work_by_id)
                if missing:
                    raise ValueError(f"Candidate package references unknown Works: {sorted(missing)}")
                payload = {
                    **principle,
                    "package_content_class": "unassessed_candidates",
                    "assessment_status": "unassessed",
                    "source_text_included": False,
                }
                content_digest = canonical_sha256(payload)
                kind = str(principle.get("kind") or "empirical")
                conn.execute(
                    "INSERT INTO principles VALUES (?, 1, ?, ?, ?, ?, 'supported', "
                    "'active', ?, ?, ?, ?)",
                    (
                        principle["principle_id"],
                        package_id,
                        principle["title"],
                        principle["claim"],
                        kind,
                        content_digest,
                        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                        principle.get("created_at") or "1970-01-01T00:00:00Z",
                        principle.get("updated_at") or "1970-01-01T00:00:00Z",
                    ),
                )
                reference_roles = sorted(
                    {
                        (str(item["work_id"]), str(item.get("role") or "evidence"))
                        for item in references
                    }
                )
                for work_id, role in reference_roles:
                    conn.execute(
                        "INSERT INTO principle_work VALUES (?, 1, ?, ?)",
                        (
                            principle["principle_id"],
                            work_id,
                            role,
                        ),
                    )
                conn.execute(
                    "INSERT INTO generation_trace VALUES (?, 1, 0, ?, ?)",
                    (
                        principle["principle_id"],
                        f"package-import:{principle['principle_id']}",
                        json.dumps(
                            {
                                "operation": "import",
                                "actor": "principia-candidate-package-v1",
                                "evidence_digest": dict(principle.get("verification") or {}).get(
                                    "evidence_digest", ""
                                ),
                                "source_text_included": False,
                            },
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    ),
                )
                conn.execute(
                    "INSERT INTO principle_fts VALUES (?, 1, ?, ?, ?, ?)",
                    (
                        principle["principle_id"],
                        principle["title"],
                        principle["claim"],
                        package_id,
                        " ".join(sorted(set(principle.get("area_labels") or []))),
                    ),
                )
            for work_id, work in sorted(work_by_id.items()):
                conn.execute(
                    "INSERT INTO works VALUES (?, ?, ?, ?, ?)",
                    (
                        work_id,
                        work.get("title") or work_id,
                        work.get("url") or "",
                        work.get("doi") or "",
                        json.dumps(work, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    ),
                )
            for index, relation in enumerate(
                sorted(relation_rows, key=lambda item: str(item.get("relation_id") or ""))
            ):
                conn.execute(
                    "INSERT INTO relations VALUES (?, 1, ?, ?, ?, ?, ?, 1.0, ?)",
                    (
                        relation["source_principle_id"],
                        index,
                        relation["target_principle_id"],
                        relation.get("target_area") or package_id,
                        relation.get("minimum_package_version") or package_version,
                        relation.get("relation_type") or "analogous_to",
                        json.dumps(relation, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    ),
                )
            _finalize_area_db(conn, revision_count=len(principles))
        with connect_sqlite(f"file:{database_path}?mode=ro", uri=True) as package_db:
            package_records = [
                loads_strict(row[0])
                for row in package_db.execute(
                    "SELECT payload_json FROM principles ORDER BY principle_id, version"
                ).fetchall()
            ]
        manifest = AreaManifest(
            area=package_id,
            display_name=display_name,
            package_version=package_version,
            principle_count=len(principles),
            revision_count=len(principles),
            relation_count=len(relation_rows),
            work_count=len(works),
            content_digest=digest_records(package_records),
            area_sqlite_sha256=file_sha256(database_path),
            builder_version=__version__,
            python_version=sys.version.split()[0],
            sqlite_version=sqlite3.sqlite_version,
            content_class="unassessed_candidates",
            created_at=max(
                (str(item.get("updated_at") or "") for item in principles),
                default="",
            )
            or "1970-01-01T00:00:00Z",
        )
        (root / "manifest.json").write_text(
            json.dumps(manifest.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
            + "\n",
            encoding="utf-8",
        )
        (root / "README.txt").write_text(readme.rstrip() + "\n", encoding="utf-8")
        partial = output_path.with_suffix(output_path.suffix + ".partial")
        with zipfile.ZipFile(partial, "w", compresslevel=9) as archive:
            for filename in sorted(PCP_ENTRIES):
                info, data = _zip_entry(root / filename, filename)
                archive.writestr(info, data)
        os.replace(partial, output_path)
    artifact_sha256 = file_sha256(output_path)
    receipt_payload = {
        "artifact_sha256": artifact_sha256,
        "artifact_bytes": output_path.stat().st_size,
        "manifest": manifest.model_dump(mode="json"),
    }
    return PackageBuildReceipt(
        path=output_path,
        manifest=manifest,
        artifact_sha256=artifact_sha256,
        artifact_bytes=output_path.stat().st_size,
        receipt_digest=canonical_sha256(receipt_payload),
    )


def _validate_zip(archive: zipfile.ZipFile) -> None:
    infos = archive.infolist()
    names = {item.filename for item in infos}
    if len(infos) != 3 or names != PCP_ENTRIES:
        raise PackageIntegrityError(".pcp must contain exactly manifest.json, area.sqlite, README.txt")
    total = 0
    for info in infos:
        path = Path(info.filename)
        if path.is_absolute() or ".." in path.parts or len(path.parts) != 1:
            raise PackageIntegrityError("unsafe path in .pcp")
        mode = info.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise PackageIntegrityError("symlinks are forbidden in .pcp")
        total += info.file_size
        if info.file_size and info.compress_size == 0:
            raise PackageIntegrityError("invalid compressed entry")
        if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
            raise PackageIntegrityError(".pcp compression ratio exceeds safety limit")
    if total > MAX_UNCOMPRESSED_BYTES:
        raise PackageIntegrityError(".pcp uncompressed size exceeds safety limit")


def verify_pcp(
    path: str | Path,
    *,
    expected_artifact_sha256: str = "",
    expected_artifact_bytes: int | None = None,
) -> VerifiedPackage:
    package_path = Path(path)
    size = package_path.stat().st_size
    if size > MAX_ARTIFACT_BYTES:
        raise PackageIntegrityError(".pcp exceeds artifact size limit")
    if expected_artifact_bytes is not None and size != expected_artifact_bytes:
        raise PackageIntegrityError(".pcp size does not match catalog")
    artifact_digest = file_sha256(package_path)
    if expected_artifact_sha256 and artifact_digest != expected_artifact_sha256:
        raise PackageIntegrityError(".pcp artifact SHA-256 does not match catalog")
    with zipfile.ZipFile(package_path) as archive:
        _validate_zip(archive)
        manifest_raw = archive.read("manifest.json")
        manifest = AreaManifest.model_validate(loads_strict(manifest_raw))
        with tempfile.TemporaryDirectory(prefix="principia-pcp-verify-") as temp:
            database_path = Path(temp) / "area.sqlite"
            with archive.open("area.sqlite") as source, database_path.open("wb") as target:
                shutil.copyfileobj(source, target, 1024 * 1024)
            if file_sha256(database_path) != manifest.area_sqlite_sha256:
                raise PackageIntegrityError("area.sqlite SHA-256 does not match manifest")
            with connect_sqlite(f"file:{database_path}?mode=ro", uri=True) as conn:
                quick = conn.execute("PRAGMA quick_check").fetchone()
                if quick is None or quick[0] != "ok":
                    raise PackageIntegrityError("area.sqlite failed quick_check")
                if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
                    raise PackageIntegrityError("area.sqlite failed foreign_key_check")
                rows = conn.execute(
                    "SELECT payload_json FROM principles ORDER BY principle_id, version"
                ).fetchall()
                logical_records = [loads_strict(row[0]) for row in rows]
                if digest_records(logical_records) != manifest.content_digest:
                    raise PackageIntegrityError("logical content digest does not match manifest")
                counts = conn.execute(
                    "SELECT COUNT(DISTINCT principle_id), COUNT(*) FROM principles"
                ).fetchone()
                if counts != (manifest.principle_count, manifest.revision_count):
                    raise PackageIntegrityError("Principle counts do not match manifest")
    return VerifiedPackage(package_path, manifest, artifact_digest, size)
