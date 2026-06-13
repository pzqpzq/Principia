from __future__ import annotations

import json
import sqlite3
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from .compression import compress_file


def build_work_search_index(out_dir: Path, work_bundles: list[dict[str, Any]], concept_records: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    asset_id = "work-search-index-0000"
    concept_by_id = {str(item.get("concept_id") or ""): item for item in concept_records}
    facets: dict[str, Counter[str]] = {"venue": Counter(), "year": Counter(), "source_type": Counter(), "model_key": Counter(), "concept_type": Counter()}
    with tempfile.TemporaryDirectory() as tmp:
        sqlite_path = Path(tmp) / f"{asset_id}.sqlite"
        with sqlite3.connect(sqlite_path) as conn:
            _ensure_search_schema(conn)
            for bundle in work_bundles:
                work = bundle.get("work") or bundle
                row = _work_search_row(work, concept_by_id)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO cloud_search_work(
                        work_id, title, abstract, authors_json, venue, year, source_type,
                        doi, arxiv_id, openalex_id, semantic_scholar_id, source_urls_json,
                        source_modified_at, source_updated_at, model_keys_json,
                        concept_ids_json, concept_labels_json, concept_types_json, status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["work_id"],
                        row["title"],
                        row["abstract"],
                        json.dumps(row["authors"], ensure_ascii=False),
                        row["venue"],
                        row["year"],
                        row["source_type"],
                        row["doi"],
                        row["arxiv_id"],
                        row["openalex_id"],
                        row["semantic_scholar_id"],
                        json.dumps(row["source_urls"], ensure_ascii=False),
                        row["source_modified_at"],
                        row["source_updated_at"],
                        json.dumps(row["model_keys"], ensure_ascii=False),
                        json.dumps(row["concept_ids"], ensure_ascii=False),
                        json.dumps(row["concept_labels"], ensure_ascii=False),
                        json.dumps(row["concept_types"], ensure_ascii=False),
                        row["status"],
                    ),
                )
                if _table_exists(conn, "cloud_search_work_fts"):
                    conn.execute(
                        """
                        INSERT INTO cloud_search_work_fts(rowid, work_id, title, abstract, authors, venue, concepts)
                        VALUES (
                            (SELECT rowid FROM cloud_search_work WHERE work_id = ?),
                            ?, ?, ?, ?, ?, ?
                        )
                        """,
                        (
                            row["work_id"],
                            row["work_id"],
                            row["title"],
                            row["abstract"],
                            " ".join(map(str, row["authors"])),
                            row["venue"],
                            " ".join(row["concept_labels"]),
                        ),
                    )
                _add_facets(facets, row)
            _write_facets(conn, facets)
        packed = out_dir / f"{asset_id}.sqlite.gz"
        compress_file(sqlite_path, packed)
    asset = {"asset_id": asset_id, "kind": "search_index", "record_type": "work", "url": str(packed), "bytes": packed.stat().st_size}
    return asset, {key: dict(counter.most_common(100)) for key, counter in facets.items()}


def _ensure_search_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cloud_search_work (
            work_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            abstract TEXT,
            authors_json TEXT DEFAULT '[]',
            venue TEXT,
            year INTEGER,
            source_type TEXT,
            doi TEXT,
            arxiv_id TEXT,
            openalex_id TEXT,
            semantic_scholar_id TEXT,
            source_urls_json TEXT DEFAULT '[]',
            source_modified_at TEXT,
            source_updated_at TEXT,
            model_keys_json TEXT DEFAULT '[]',
            concept_ids_json TEXT DEFAULT '[]',
            concept_labels_json TEXT DEFAULT '[]',
            concept_types_json TEXT DEFAULT '[]',
            status TEXT DEFAULT 'active'
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cloud_search_work_venue_year ON cloud_search_work(venue, year)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cloud_search_work_year ON cloud_search_work(year)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cloud_search_work_source_type ON cloud_search_work(source_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cloud_search_work_doi ON cloud_search_work(doi)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cloud_search_work_arxiv ON cloud_search_work(arxiv_id)")
    try:
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS cloud_search_work_fts
            USING fts5(work_id, title, abstract, authors, venue, concepts)
            """
        )
    except sqlite3.OperationalError:
        pass
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cloud_search_facet (
            facet_type TEXT NOT NULL,
            facet_value TEXT NOT NULL,
            count INTEGER NOT NULL,
            PRIMARY KEY(facet_type, facet_value)
        )
        """
    )


def _work_search_row(work: dict[str, Any], concept_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    identity = work.get("identity") or work
    refs = work.get("concept_refs") or []
    if not refs and work.get("concepts"):
        refs = [
            {
                "concept_id": concept.get("concept_id"),
                "concept_type": concept.get("concept_type"),
                "canonical_label": concept.get("canonical_label"),
            }
            for concept in work.get("concepts") or []
        ]
    concept_ids = [str(ref.get("concept_id") or "") for ref in refs if ref.get("concept_id")]
    concepts = [concept_by_id.get(concept_id, {}) for concept_id in concept_ids]
    concept_labels = [
        str((concept.get("payload") or {}).get("title") or concept.get("canonical_label") or ref.get("canonical_label") or "")
        for concept, ref in zip(concepts, refs)
    ]
    concept_types = [str(concept.get("concept_type") or ref.get("concept_type") or "") for concept, ref in zip(concepts, refs)]
    latest_by_model = work.get("latest_by_model") or {}
    source_state = work.get("source_state") or {}
    return {
        "work_id": str(work.get("work_id") or ""),
        "title": str(identity.get("canonical_title") or work.get("title") or "Untitled work"),
        "abstract": str(work.get("abstract") or ""),
        "authors": list(identity.get("authors") or work.get("authors") or []),
        "venue": str(identity.get("venue_or_source") or work.get("venue_or_source") or ""),
        "year": int(identity.get("year") or work.get("year") or 0) or None,
        "source_type": str(identity.get("source_type") or work.get("source_type") or "paper"),
        "doi": str(identity.get("doi") or ""),
        "arxiv_id": str(identity.get("arxiv_id") or ""),
        "openalex_id": str(identity.get("openalex_id") or ""),
        "semantic_scholar_id": str(identity.get("semantic_scholar_id") or ""),
        "source_urls": list(identity.get("source_urls") or work.get("source_urls") or []),
        "source_modified_at": str(source_state.get("source_modified_at") or ""),
        "source_updated_at": str(source_state.get("source_updated_at") or ""),
        "model_keys": sorted(str(key) for key in latest_by_model.keys()),
        "concept_ids": concept_ids,
        "concept_labels": [label for label in concept_labels if label],
        "concept_types": [kind for kind in concept_types if kind],
        "status": str((work.get("quality") or {}).get("verification_status") or "active"),
    }


def _add_facets(facets: dict[str, Counter[str]], row: dict[str, Any]) -> None:
    for key, value in (("venue", row.get("venue")), ("year", row.get("year")), ("source_type", row.get("source_type"))):
        if value:
            facets[key][str(value)] += 1
    for model_key in row.get("model_keys") or []:
        if model_key:
            facets["model_key"][str(model_key)] += 1
    for concept_type in row.get("concept_types") or []:
        if concept_type:
            facets["concept_type"][str(concept_type)] += 1


def _write_facets(conn: sqlite3.Connection, facets: dict[str, Counter[str]]) -> None:
    for facet_type, counter in facets.items():
        for value, count in counter.items():
            conn.execute(
                "INSERT OR REPLACE INTO cloud_search_facet(facet_type, facet_value, count) VALUES (?, ?, ?)",
                (facet_type, value, int(count)),
            )


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?", (table,)).fetchone()
    return bool(row)
