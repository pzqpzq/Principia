from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

from platformdirs import user_data_path

from .._sqlite import connect_sqlite
from ..domain import AreaManifest, CatalogEntry
from ..models import utc_now
from .package import verify_pcp


class CloudRegistry:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root else user_data_path("Principia", appauthor=False) / "cloud"
        self.packages_dir = self.root / "packages"
        self.active_dir = self.root / "active"
        self.downloads_dir = self.root / "downloads"
        self.catalog_dir = self.root / "catalog"
        self.db_path = self.root / "registry.sqlite"
        for path in (self.packages_dir, self.active_dir, self.downloads_dir, self.catalog_dir):
            path.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def connect(self) -> sqlite3.Connection:
        conn = connect_sqlite(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS installed_areas(
                    area TEXT NOT NULL,
                    version TEXT NOT NULL,
                    package_path TEXT NOT NULL,
                    artifact_sha256 TEXT NOT NULL,
                    content_digest TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 0,
                    pinned INTEGER NOT NULL DEFAULT 0,
                    installed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(area, version)
                );
                CREATE TABLE IF NOT EXISTS principle_index(
                    principle_id TEXT PRIMARY KEY,
                    version INTEGER NOT NULL,
                    area TEXT NOT NULL,
                    package_version TEXT NOT NULL,
                    title TEXT NOT NULL,
                    claim TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    maturity TEXT NOT NULL,
                    quality REAL NOT NULL,
                    freshness TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    content_class TEXT NOT NULL DEFAULT 'reviewed_capsules',
                    supporting_work_count INTEGER NOT NULL DEFAULT 0,
                    evidence_anchor_count INTEGER NOT NULL DEFAULT 0,
                    area_labels TEXT NOT NULL DEFAULT '',
                    claim_type TEXT NOT NULL DEFAULT '',
                    applicability TEXT NOT NULL DEFAULT ''
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS principle_fts USING fts5(
                    principle_id UNINDEXED,
                    title,
                    claim,
                    area,
                    tags,
                    tokenize='unicode61 remove_diacritics 2'
                );
                """
            )
            columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(principle_index)")}
            additions = {
                "content_class": "TEXT NOT NULL DEFAULT 'reviewed_capsules'",
                "supporting_work_count": "INTEGER NOT NULL DEFAULT 0",
                "evidence_anchor_count": "INTEGER NOT NULL DEFAULT 0",
                "area_labels": "TEXT NOT NULL DEFAULT ''",
                "claim_type": "TEXT NOT NULL DEFAULT ''",
                "applicability": "TEXT NOT NULL DEFAULT ''",
            }
            for column, definition in additions.items():
                if column not in columns:
                    conn.execute(f"ALTER TABLE principle_index ADD COLUMN {column} {definition}")

    def version_dir(self, area: str, version: str) -> Path:
        return self.packages_dir / area / version

    def active_pointer(self, area: str) -> Path:
        return self.active_dir / f"{area}.json"

    @property
    def cached_catalog_path(self) -> Path:
        return self.catalog_dir / "catalog.json"

    def cache_catalog(self, entries: list[CatalogEntry], *, source: str | Path) -> None:
        payload = {
            "schema_version": "principia-catalog-v1",
            "areas": [item.model_dump(mode="json") for item in entries],
        }
        temporary = self.cached_catalog_path.with_suffix(".json.partial")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.cached_catalog_path)
        source_digest = hashlib.sha256(str(source).encode("utf-8")).hexdigest()
        state = self.catalog_dir / "state.json"
        state_tmp = state.with_suffix(".json.partial")
        state_tmp.write_text(
            json.dumps(
                {
                    "schema_version": "principia-catalog-cache-v1",
                    "source_sha256": source_digest,
                    "etag": None,
                    "refreshed_at": utc_now(),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        os.replace(state_tmp, state)

    def active_version(self, area: str) -> str | None:
        path = self.active_pointer(area)
        if not path.exists():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return str(value.get("version") or "") or None

    def installed(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM installed_areas ORDER BY area, version DESC"
                ).fetchall()
            ]

    def register(self, package_path: Path, manifest: AreaManifest, artifact_sha256: str) -> None:
        with connect_sqlite(f"file:{package_path}?mode=ro", uri=True) as package:
            package.row_factory = sqlite3.Row
            rows = package.execute(
                """
                SELECT p.* FROM principles p JOIN (
                    SELECT principle_id, MAX(version) AS version
                    FROM principles GROUP BY principle_id
                ) current USING(principle_id, version)
                ORDER BY p.principle_id
                """
            ).fetchall()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE installed_areas SET active=0 WHERE area=?", (manifest.area,))
            conn.execute(
                """
                INSERT INTO installed_areas(
                    area, version, package_path, artifact_sha256, content_digest,
                    manifest_json, active, pinned
                ) VALUES (?, ?, ?, ?, ?, ?, 1,
                    COALESCE((SELECT pinned FROM installed_areas WHERE area=? AND version=?), 0))
                ON CONFLICT(area, version) DO UPDATE SET package_path=excluded.package_path,
                    artifact_sha256=excluded.artifact_sha256,
                    content_digest=excluded.content_digest,
                    manifest_json=excluded.manifest_json, active=1
                """,
                (
                    manifest.area,
                    manifest.package_version,
                    str(package_path),
                    artifact_sha256,
                    manifest.content_digest,
                    manifest.model_dump_json(),
                    manifest.area,
                    manifest.package_version,
                ),
            )
            conn.execute("DELETE FROM principle_fts WHERE area=?", (manifest.area,))
            conn.execute("DELETE FROM principle_index WHERE area=?", (manifest.area,))
            for row in rows:
                payload = json.loads(row["payload_json"])
                quality = payload.get("quality") or {}
                numeric_quality = (
                    sum(
                        float(quality.get(name, 0))
                        for name in (
                            "validity",
                            "reproducibility",
                            "evidence_strength",
                            "generality",
                            "usefulness",
                        )
                    )
                    / 5
                )
                tags = " ".join(payload.get("tags") or [])
                content_class = manifest.content_class
                area_labels = json.dumps(
                    sorted(set(payload.get("area_labels") or [])), separators=(",", ":")
                )
                supporting_work_count = len(
                    {str(item.get("work_id") or "") for item in payload.get("references") or []}
                    - {""}
                )
                evidence_anchor_count = len(
                    {
                        (str(item.get("work_id") or ""), str(item.get("excerpt_sha256") or ""))
                        for item in payload.get("references") or []
                    }
                )
                claim_type = str(payload.get("claim_class") or row["kind"])
                applicability = "; ".join(
                    [
                        *[str(item) for item in payload.get("conditions") or []],
                        *[str(item) for item in payload.get("boundary") or []],
                    ]
                )[:1200]
                conn.execute(
                    "INSERT INTO principle_index(principle_id, version, area, package_version, "
                    "title, claim, kind, maturity, quality, freshness, tags, content_class, "
                    "supporting_work_count, evidence_anchor_count, area_labels, claim_type, "
                    "applicability) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        row["principle_id"],
                        row["version"],
                        row["area"],
                        manifest.package_version,
                        row["title"],
                        row["claim"],
                        row["kind"],
                        row["maturity"],
                        numeric_quality,
                        row["updated_at"],
                        tags,
                        content_class,
                        supporting_work_count,
                        evidence_anchor_count,
                        area_labels,
                        claim_type,
                        applicability,
                    ),
                )
                conn.execute(
                    "INSERT INTO principle_fts VALUES (?, ?, ?, ?, ?)",
                    (row["principle_id"], row["title"], row["claim"], row["area"], tags),
                )

    def activate(self, area: str, version: str, manifest: AreaManifest) -> None:
        pointer = self.active_pointer(area)
        temporary = pointer.with_suffix(".json.partial")
        temporary.write_text(
            json.dumps(
                {
                    "area": area,
                    "version": version,
                    "content_digest": manifest.content_digest,
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, pointer)

    def pin(self, area: str, version: str, *, pinned: bool = True) -> None:
        with self.connect() as conn:
            changed = conn.execute(
                "UPDATE installed_areas SET pinned=? WHERE area=? AND version=?",
                (int(pinned), area, version),
            ).rowcount
        if not changed:
            raise KeyError(f"area version is not installed: {area}@{version}")

    def search(self, query: str, *, limit: int = 50) -> list[dict[str, Any]]:
        terms = re.findall(r"[\w-]+", query, flags=re.UNICODE)
        if not terms:
            return []
        fts_query = " AND ".join(f'"{term.replace(chr(34), "")}"' for term in terms[:20])
        resolved_limit = max(1, min(int(limit), 100))
        # Broad terms can match the entire registry. Ranking every match before
        # LIMIT makes latency proportional to catalog size, so search-v1 first
        # takes a deterministic rowid-ordered recall window and ranks within it.
        # Package indexing is itself deterministic, making the bounded window
        # reproducible while keeping the worst case responsive and memory-bounded.
        scan_limit = max(2_000, resolved_limit * 50)
        candidate_limit = max(200, resolved_limit * 8)
        with self.connect() as conn:
            rows = conn.execute(
                """
                WITH bounded_matches AS MATERIALIZED (
                    SELECT principle_id, rank AS lexical_rank
                    FROM principle_fts
                    WHERE principle_fts MATCH ?
                    ORDER BY rowid
                    LIMIT ?
                ),
                lexical_candidates AS (
                    SELECT principle_id, lexical_rank
                    FROM bounded_matches
                    ORDER BY lexical_rank, principle_id
                    LIMIT ?
                )
                SELECT i.*, c.lexical_rank
                FROM lexical_candidates c
                JOIN principle_index i USING(principle_id)
                ORDER BY c.lexical_rank, i.quality DESC, i.freshness DESC, i.principle_id
                LIMIT ?
                """,
                (fts_query, scan_limit, candidate_limit, resolved_limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def browse(self, *, area: str = "", limit: int = 60) -> dict[str, Any]:
        """Browse the active verified Global projection without requiring a query."""

        resolved_limit = max(1, min(int(limit), 500))
        where = "WHERE area=?" if area else ""
        values: tuple[Any, ...] = (area,) if area else ()
        with self.connect() as conn:
            total = int(
                conn.execute(f"SELECT COUNT(*) FROM principle_index {where}", values).fetchone()[0]
            )
            rows = conn.execute(
                f"""
                SELECT principle_id, version, area, package_version, title, claim,
                       kind, maturity, quality, freshness, content_class,
                       supporting_work_count, evidence_anchor_count, area_labels,
                       claim_type, applicability
                FROM principle_index {where}
                ORDER BY quality DESC, freshness DESC, principle_id
                LIMIT ?
                """,
                (*values, resolved_limit),
            ).fetchall()
        return {"items": [dict(row) for row in rows], "total": total}

    def rebuild(self) -> int:
        pointers = sorted(self.active_dir.glob("*.json"))
        with self.connect() as conn:
            conn.execute("DELETE FROM principle_fts")
            conn.execute("DELETE FROM principle_index")
            conn.execute("UPDATE installed_areas SET active=0")
        rebuilt = 0
        for pointer in pointers:
            data = json.loads(pointer.read_text(encoding="utf-8"))
            package_archive = self.version_dir(data["area"], data["version"]) / "package.pcp"
            verified = verify_pcp(package_archive)
            database = self.version_dir(data["area"], data["version"]) / "area.sqlite"
            self.register(database, verified.manifest, verified.artifact_sha256)
            rebuilt += 1
        return rebuilt

    def principle(self, principle_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM principle_index WHERE principle_id=?", (principle_id,)
            ).fetchone()
        if not row:
            return None
        route = dict(row)
        package = self.version_dir(route["area"], route["package_version"]) / "area.sqlite"
        with connect_sqlite(f"file:{package}?mode=ro", uri=True) as conn:
            detail = conn.execute(
                "SELECT payload_json FROM principles WHERE principle_id=? AND version=?",
                (principle_id, route["version"]),
            ).fetchone()
            if detail is None:
                return None
            references = conn.execute(
                """
                SELECT w.payload_json, pw.role
                FROM principle_work pw JOIN works w USING(work_id)
                WHERE pw.principle_id=? AND pw.principle_version=?
                ORDER BY w.work_id, pw.role
                """,
                (principle_id, route["version"]),
            ).fetchall()
            relations = conn.execute(
                """
                SELECT payload_json FROM relations
                WHERE source_principle_id=? AND source_version=?
                ORDER BY relation_index
                """,
                (principle_id, route["version"]),
            ).fetchall()
        payload = json.loads(detail[0])
        payload["source_references"] = [
            {**json.loads(row[0]), "role": str(row[1])} for row in references
        ]
        payload["relations"] = [json.loads(row[0]) for row in relations]
        return payload
