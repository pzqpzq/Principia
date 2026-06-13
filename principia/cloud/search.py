from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ..utils import lexical_score
from .manifest import CloudManifestClient
from .resolver import CloudResolver


class CloudSearch:
    def __init__(self, resolver: CloudResolver):
        self.resolver = resolver

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
        model_key: str = "",
        venue: str = "",
        year: int | None = None,
        source_type: str = "",
        concept_type: str = "",
    ) -> dict[str, Any]:
        manifest = self.resolver.manifest_client.load_manifest()
        if not manifest.get("assets"):
            return {"items": [], "snapshot_id": manifest.get("snapshot_id", ""), "warning": "No cloud manifest assets configured."}
        items = self._search_index_assets(
            manifest,
            query,
            limit=limit,
            model_key=model_key,
            venue=venue,
            year=year,
            source_type=source_type,
            concept_type=concept_type,
        )
        if items:
            return {"items": items[:limit], "snapshot_id": manifest.get("snapshot_id", ""), "query": query, "facets": manifest.get("facets") or {}}
        if any([venue, year, source_type, concept_type]):
            return {"items": [], "snapshot_id": manifest.get("snapshot_id", ""), "query": query, "facets": manifest.get("facets") or {}}
        items = []
        for asset in manifest.get("assets") or []:
            if asset.get("kind") != "route_index" or asset.get("route_type") != "work":
                continue
            try:
                path = self.resolver.cache.unpack_sqlite_asset(asset, snapshot_id=str(manifest.get("snapshot_id") or ""))
                items.extend(self._search_route(path, query, limit=limit, model_key=model_key))
            except Exception:
                continue
            if len(items) >= limit:
                break
        items.sort(key=lambda row: row.get("_score", 0), reverse=True)
        return {"items": items[:limit], "snapshot_id": manifest.get("snapshot_id", ""), "query": query, "facets": manifest.get("facets") or {}}

    def _search_index_assets(
        self,
        manifest: dict[str, Any],
        query: str,
        *,
        limit: int,
        model_key: str,
        venue: str,
        year: int | None,
        source_type: str,
        concept_type: str,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for asset in manifest.get("assets") or []:
            if asset.get("kind") != "search_index" or asset.get("record_type") != "work":
                continue
            try:
                path = self.resolver.cache.unpack_sqlite_asset(asset, snapshot_id=str(manifest.get("snapshot_id") or ""))
                items.extend(
                    self._search_index(
                        path,
                        query,
                        limit=limit,
                        model_key=model_key,
                        venue=venue,
                        year=year,
                        source_type=source_type,
                        concept_type=concept_type,
                    )
                )
            except Exception:
                continue
            if len(items) >= limit:
                break
        items.sort(key=lambda row: row.get("_score", 0), reverse=True)
        return items[:limit]

    def _search_index(
        self,
        path: Path,
        query: str,
        *,
        limit: int,
        model_key: str,
        venue: str,
        year: int | None,
        source_type: str,
        concept_type: str,
    ) -> list[dict[str, Any]]:
        query = str(query or "").strip()
        clauses = []
        params: list[Any] = []
        if venue:
            clauses.append("w.venue = ?")
            params.append(venue)
        if year:
            clauses.append("w.year = ?")
            params.append(int(year))
        if source_type:
            clauses.append("w.source_type = ?")
            params.append(source_type)
        if model_key:
            clauses.append("w.model_keys_json LIKE ?")
            params.append(f"%{model_key}%")
        if concept_type:
            clauses.append("w.concept_types_json LIKE ?")
            params.append(f"%{concept_type}%")
        with sqlite3.connect(path) as conn:
            conn.row_factory = sqlite3.Row
            has_fts = _table_exists(conn, "cloud_search_work_fts")
            where_sql = (" WHERE " + " AND ".join(clauses)) if clauses else ""
            if query and has_fts and not any(token in query for token in ("*", ":", '"')):
                fts_query = " ".join(token for token in query.replace("-", " ").split() if token)
                sql = (
                    "SELECT w.*, bm25(cloud_search_work_fts) * -1.0 AS _score "
                    "FROM cloud_search_work_fts JOIN cloud_search_work w ON w.rowid = cloud_search_work_fts.rowid "
                    f"{where_sql + (' AND ' if where_sql else ' WHERE ')} cloud_search_work_fts MATCH ? "
                    "ORDER BY _score DESC LIMIT ?"
                )
                rows = conn.execute(sql, [*params, fts_query, int(limit)]).fetchall()
            else:
                clauses = [clause.removeprefix("w.") for clause in clauses]
                like_clauses = []
                if query:
                    for column in ("work_id", "title", "abstract", "authors_json", "venue", "doi", "arxiv_id", "openalex_id", "concept_labels_json"):
                        like_clauses.append(f"{column} LIKE ?")
                        params.append(f"%{query}%")
                full_where = list(clauses)
                if like_clauses:
                    full_where.append("(" + " OR ".join(like_clauses) + ")")
                sql = "SELECT *, 0.1 AS _score FROM cloud_search_work"
                if full_where:
                    sql += " WHERE " + " AND ".join(full_where)
                sql += " ORDER BY year DESC, title ASC LIMIT ?"
                rows = conn.execute(sql, [*params, int(limit)]).fetchall()
        return [_normalize_work_row(dict(row), query) for row in rows]

    def _search_route(self, path: Path, query: str, *, limit: int, model_key: str = "") -> list[dict[str, Any]]:
        rows = []
        with sqlite3.connect(path) as conn:
            conn.row_factory = sqlite3.Row
            for row in conn.execute("SELECT * FROM cloud_work_route LIMIT 5000").fetchall():
                item = dict(row)
                latest = _loads(item.get("latest_by_model_json", "{}"))
                if model_key and model_key not in latest:
                    continue
                text = " ".join(str(item.get(key) or "") for key in ("work_id", "doi", "arxiv_id", "openalex_id", "title_hash", "canonical_title", "venue", "year"))
                score = lexical_score(query, text) if query else 0.1
                if score > 0 or not query:
                    item["_score"] = score
                    item["latest_by_model"] = latest
                    item["model_keys"] = _loads(item.pop("model_keys_json", "[]"))
                    rows.append(item)
        rows.sort(key=lambda row: row.get("_score", 0), reverse=True)
        return rows[:limit]


def _loads(text: str) -> Any:
    try:
        return json.loads(text or "{}")
    except Exception:
        return {}


def _normalize_work_row(row: dict[str, Any], query: str) -> dict[str, Any]:
    for key in ("authors_json", "source_urls_json", "model_keys_json", "concept_ids_json", "concept_labels_json", "concept_types_json"):
        value = row.pop(key, "[]")
        row[key.removesuffix("_json")] = _loads(value)
    text = " ".join(str(row.get(key) or "") for key in ("work_id", "title", "abstract", "venue", "doi", "arxiv_id", "openalex_id"))
    row["_score"] = float(row.get("_score") or lexical_score(query, text) or 0.1)
    return row


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?", (table,)).fetchone()
    return bool(row)
