from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Iterable

from ..work_versioning import work_content_signature
from .compression import compress_file, decompress_file
from .ids import best_identity_key, candidate_identity_keys, shard_for_key
from .pack import PackEntry


def route_key_for_work(record: dict[str, Any]) -> str:
    identity = dict(record.get("identity") or {})
    identity.setdefault("title", identity.get("canonical_title") or record.get("title") or record.get("canonical_title") or "")
    identity.setdefault("abstract", record.get("abstract") or "")
    return best_identity_key(candidate_identity_keys(identity))


def route_key_for_concept(record: dict[str, Any]) -> str:
    return f"{record.get('concept_type') or 'concept'}:{record.get('canonical_key') or record.get('concept_id') or ''}"


def build_work_route_indexes(out_dir: Path, work_records: Iterable[dict[str, Any]], entries: dict[str, PackEntry], *, shard_count: int = 256) -> list[dict[str, Any]]:
    return _build_sharded_indexes(out_dir, work_records, entries, shard_count=shard_count, route_type="work")


def build_concept_route_indexes(out_dir: Path, concept_records: Iterable[dict[str, Any]], entries: dict[str, PackEntry], *, shard_count: int = 64) -> list[dict[str, Any]]:
    return _build_sharded_indexes(out_dir, concept_records, entries, shard_count=shard_count, route_type="concept")


def _build_sharded_indexes(out_dir: Path, records: Iterable[dict[str, Any]], entries: dict[str, PackEntry], *, shard_count: int, route_type: str) -> list[dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    by_shard: dict[int, list[dict[str, Any]]] = {}
    for record in records:
        key = route_key_for_work(record) if route_type == "work" else route_key_for_concept(record)
        shard = shard_for_key(key, shard_count)
        by_shard.setdefault(shard, []).append(record)
    assets: list[dict[str, Any]] = []
    for shard, rows in sorted(by_shard.items()):
        asset = _write_route_shard(out_dir, rows, entries, shard=shard, shard_count=shard_count, route_type=route_type)
        assets.append(asset)
    return assets


def _write_route_shard(out_dir: Path, records: list[dict[str, Any]], entries: dict[str, PackEntry], *, shard: int, shard_count: int, route_type: str) -> dict[str, Any]:
    width = max(2, len(str(max(0, shard_count - 1))))
    asset_id = f"{route_type}-route-index-{shard:0{width}d}"
    with tempfile.TemporaryDirectory() as tmp:
        sqlite_path = Path(tmp) / f"{asset_id}.sqlite"
        with sqlite3.connect(sqlite_path) as conn:
            if route_type == "work":
                _ensure_work_route(conn)
                for record in records:
                    entry = entries[record["work_id"]]
                    identity = record.get("identity") or record
                    source_state = record.get("source_state") or {}
                    sig = work_content_signature({"title": identity.get("canonical_title") or record.get("title") or "", "abstract": record.get("abstract") or ""})
                    latest_by_model = record.get("latest_by_model") or {}
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO cloud_work_route(
                            work_id, title_hash, doi, arxiv_id, openalex_id, crossref_id,
                            semantic_scholar_id, openreview_forum_id, pack_id, offset, length,
                            block_id, checksum, source_modified_at, source_updated_at,
                            abstract_hash, content_hash, latest_by_model_json,
                            canonical_title, venue, year, source_type, model_keys_json
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            record["work_id"],
                            identity.get("title_hash") or source_state.get("title_hash") or sig["title_hash"],
                            identity.get("doi") or "",
                            identity.get("arxiv_id") or "",
                            identity.get("openalex_id") or "",
                            identity.get("crossref_id") or "",
                            identity.get("semantic_scholar_id") or "",
                            identity.get("openreview_forum_id") or "",
                            entry.pack_id,
                            entry.offset,
                            entry.length,
                            entry.block_id,
                            entry.checksum,
                            source_state.get("source_modified_at") or "",
                            source_state.get("source_updated_at") or "",
                            source_state.get("abstract_hash") or sig["abstract_hash"],
                            source_state.get("content_hash") or sig["content_hash"],
                            json.dumps(latest_by_model, ensure_ascii=False),
                            identity.get("canonical_title") or record.get("title") or "",
                            identity.get("venue_or_source") or record.get("venue_or_source") or "",
                            identity.get("year") or record.get("year") or None,
                            identity.get("source_type") or record.get("source_type") or "paper",
                            json.dumps(sorted(latest_by_model.keys()), ensure_ascii=False),
                        ),
                    )
            else:
                _ensure_concept_route(conn)
                for record in records:
                    entry = entries[record["concept_id"]]
                    support = record.get("support") or {}
                    versioning = record.get("versioning") or {}
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO cloud_concept_route(
                            concept_id, concept_type, canonical_key, canonical_label, alias_hashes_json,
                            pack_id, offset, length, block_id, checksum, active_version_id,
                            support_count, confidence_score
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            record["concept_id"],
                            record.get("concept_type") or "concept",
                            record.get("canonical_key") or "",
                            record.get("canonical_label") or "",
                            json.dumps(record.get("aliases") or [], ensure_ascii=False),
                            entry.pack_id,
                            entry.offset,
                            entry.length,
                            entry.block_id,
                            entry.checksum,
                            versioning.get("active_version_id") or "",
                            int(support.get("evidence_count") or len(support.get("supporting_work_ids") or []) or 0),
                            float(support.get("confidence_score") or 0.5),
                        ),
                    )
        packed = out_dir / f"{asset_id}.sqlite.gz"
        compress_file(sqlite_path, packed)
    return {"asset_id": asset_id, "kind": "route_index", "route_type": route_type, "shard": shard, "url": str(packed), "bytes": packed.stat().st_size}


def _ensure_work_route(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cloud_work_route (
            work_id TEXT PRIMARY KEY,
            title_hash TEXT,
            doi TEXT,
            arxiv_id TEXT,
            openalex_id TEXT,
            crossref_id TEXT,
            semantic_scholar_id TEXT,
            openreview_forum_id TEXT,
            pack_id TEXT NOT NULL,
            offset INTEGER NOT NULL,
            length INTEGER NOT NULL,
            block_id TEXT,
            checksum TEXT NOT NULL,
            source_modified_at TEXT,
            source_updated_at TEXT,
            abstract_hash TEXT,
            content_hash TEXT,
            latest_by_model_json TEXT NOT NULL,
            canonical_title TEXT,
            venue TEXT,
            year INTEGER,
            source_type TEXT,
            model_keys_json TEXT DEFAULT '[]'
        )
        """
    )
    for column in ("doi", "arxiv_id", "openalex_id", "crossref_id", "semantic_scholar_id", "openreview_forum_id", "title_hash"):
        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_cloud_work_route_{column} ON cloud_work_route({column})")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cloud_work_route_venue_year ON cloud_work_route(venue, year)")


def _ensure_concept_route(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cloud_concept_route (
            concept_id TEXT PRIMARY KEY,
            concept_type TEXT NOT NULL,
            canonical_key TEXT NOT NULL,
            canonical_label TEXT,
            alias_hashes_json TEXT,
            pack_id TEXT NOT NULL,
            offset INTEGER NOT NULL,
            length INTEGER NOT NULL,
            block_id TEXT,
            checksum TEXT NOT NULL,
            active_version_id TEXT,
            support_count INTEGER DEFAULT 0,
            confidence_score REAL DEFAULT 0.5
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cloud_concept_type_key ON cloud_concept_route(concept_type, canonical_key)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cloud_concept_label ON cloud_concept_route(canonical_label)")


def ensure_unpacked_sqlite(packed: Path, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists() or target.stat().st_mtime < packed.stat().st_mtime:
        decompress_file(packed, target)
    return target
