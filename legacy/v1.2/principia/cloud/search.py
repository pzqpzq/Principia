from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ..utils import lexical_score
from .manifest import CloudManifestClient
from .resolver import CloudResolver


OTHER_FILTER_VALUE = "__other__"
DEFAULT_KNOWN_VENUES = [
    "ICLR",
    "NeurIPS",
    "ICML",
    "CVPR",
    "ACL",
    "ICCV",
    "ECCV",
    "EMNLP",
    "AAAI",
    "TPAMI",
    "JMLR",
    "Nature",
    "Science",
    "Nature Machine Intelligence",
    "Nature Computational Science",
]


class CloudSearch:
    def __init__(self, resolver: CloudResolver):
        self.resolver = resolver

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
        offset: int = 0,
        model_key: str = "",
        venue: str = "",
        venues: list[str] | None = None,
        venue_other: bool = False,
        known_venues: list[str] | None = None,
        year: int | None = None,
        years: list[int] | None = None,
        year_other: bool = False,
        known_years: list[int] | None = None,
        source_type: str = "",
        concept_type: str = "",
    ) -> dict[str, Any]:
        try:
            manifest = self.resolver.manifest_client.load_manifest()
        except Exception as exc:
            return {
                "items": [],
                "offset": offset,
                "limit": limit,
                "has_more": False,
                "snapshot_id": "",
                "query": query,
                "facets": {},
                "warning": f"Cloud manifest is unavailable: {exc}",
            }
        if not manifest.get("assets"):
            return {"items": [], "snapshot_id": manifest.get("snapshot_id", ""), "warning": "No cloud manifest assets configured."}
        items = self._search_index_assets(
            manifest,
            query,
            limit=limit,
            offset=offset,
            model_key=model_key,
            venue=venue,
            venues=venues or [],
            venue_other=venue_other,
            known_venues=known_venues or DEFAULT_KNOWN_VENUES,
            year=year,
            years=years or [],
            year_other=year_other,
            known_years=known_years or [],
            source_type=source_type,
            concept_type=concept_type,
        )
        if items:
            items = self._enrich_work_items(manifest, items[:limit])
            return {"items": items[:limit], "offset": offset, "limit": limit, "has_more": len(items) >= limit, "snapshot_id": manifest.get("snapshot_id", ""), "query": query, "facets": manifest.get("facets") or {}}
        if any([venue, venues, venue_other, year, years, year_other, source_type, concept_type]):
            return {"items": [], "offset": offset, "limit": limit, "has_more": False, "snapshot_id": manifest.get("snapshot_id", ""), "query": query, "facets": manifest.get("facets") or {}}
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
        items = self._enrich_work_items(manifest, items[:limit])
        return {"items": items[:limit], "offset": offset, "limit": limit, "has_more": len(items) >= limit, "snapshot_id": manifest.get("snapshot_id", ""), "query": query, "facets": manifest.get("facets") or {}}

    def _enrich_work_items(self, manifest: dict[str, Any], items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        enriched: list[dict[str, Any]] = []
        bundle_cache: dict[str, dict[str, Any] | None] = {}
        for item in items:
            row = dict(item)
            work_id = str(row.get("work_id") or "")
            if work_id and work_id not in bundle_cache:
                try:
                    bundle_cache[work_id] = self.resolver.fetch_work_bundle_by_id(work_id, manifest)
                except Exception:
                    bundle_cache[work_id] = None
            bundle = bundle_cache.get(work_id)
            if isinstance(bundle, dict):
                row = _merge_bundle_into_search_row(row, bundle)
            enriched.append(row)
        return enriched

    def _search_index_assets(
        self,
        manifest: dict[str, Any],
        query: str,
        *,
        limit: int,
        offset: int,
        model_key: str,
        venue: str,
        venues: list[str],
        venue_other: bool,
        known_venues: list[str],
        year: int | None,
        years: list[int],
        year_other: bool,
        known_years: list[int],
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
                        offset=offset,
                        model_key=model_key,
                        venue=venue,
                        venues=venues,
                        venue_other=venue_other,
                        known_venues=known_venues,
                        year=year,
                        years=years,
                        year_other=year_other,
                        known_years=known_years,
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
        offset: int,
        model_key: str,
        venue: str,
        venues: list[str],
        venue_other: bool,
        known_venues: list[str],
        year: int | None,
        years: list[int],
        year_other: bool,
        known_years: list[int],
        source_type: str,
        concept_type: str,
    ) -> list[dict[str, Any]]:
        query = str(query or "").strip()
        clauses = []
        params: list[Any] = []
        selected_venues = _unique([*(venues or []), venue])
        selected_venues = [item for item in selected_venues if item != OTHER_FILTER_VALUE]
        venue_clauses: list[str] = []
        if selected_venues:
            venue_clauses.append("LOWER(COALESCE(w.venue, '')) IN (%s)" % ",".join("?" for _ in selected_venues))
            params.extend([item.lower() for item in selected_venues])
        known_venue_values = [item.lower() for item in _unique(known_venues or DEFAULT_KNOWN_VENUES) if item != OTHER_FILTER_VALUE]
        if venue_other:
            if known_venue_values:
                venue_clauses.append(
                    "(w.venue IS NULL OR TRIM(w.venue) = '' OR LOWER(w.venue) NOT IN (%s))"
                    % ",".join("?" for _ in known_venue_values)
                )
                params.extend(known_venue_values)
            else:
                venue_clauses.append("(w.venue IS NULL OR TRIM(w.venue) = '')")
        if venue_clauses:
            clauses.append("(" + " OR ".join(venue_clauses) + ")")
        selected_years = _unique_int([*(years or []), year])
        year_clauses: list[str] = []
        if selected_years:
            year_clauses.append("w.year IN (%s)" % ",".join("?" for _ in selected_years))
            params.extend(selected_years)
        known_year_values = _unique_int(known_years or [])
        if year_other:
            if known_year_values:
                year_clauses.append("(w.year IS NULL OR w.year NOT IN (%s))" % ",".join("?" for _ in known_year_values))
                params.extend(known_year_values)
            else:
                year_clauses.append("w.year IS NULL")
        if year_clauses:
            clauses.append("(" + " OR ".join(year_clauses) + ")")
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
                    "ORDER BY _score DESC LIMIT ? OFFSET ?"
                )
                rows = conn.execute(sql, [*params, fts_query, int(limit), int(offset)]).fetchall()
            else:
                like_clauses = []
                if query:
                    for column in ("work_id", "title", "abstract", "authors_json", "venue", "doi", "arxiv_id", "openalex_id", "concept_labels_json"):
                        like_clauses.append(f"w.{column} LIKE ?")
                        params.append(f"%{query}%")
                full_where = list(clauses)
                if like_clauses:
                    full_where.append("(" + " OR ".join(like_clauses) + ")")
                sql = "SELECT w.*, 0.1 AS _score FROM cloud_search_work w"
                if full_where:
                    sql += " WHERE " + " AND ".join(full_where)
                sql += " ORDER BY year DESC, title ASC LIMIT ? OFFSET ?"
                rows = conn.execute(sql, [*params, int(limit), int(offset)]).fetchall()
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


def _merge_bundle_into_search_row(row: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    work = bundle.get("work") if bundle.get("record_type") == "work_bundle" else bundle
    if not isinstance(work, dict):
        return row
    identity = work.get("identity") if isinstance(work.get("identity"), dict) else {}
    source_state = work.get("source_state") if isinstance(work.get("source_state"), dict) else {}
    row.setdefault("title", identity.get("canonical_title") or work.get("title") or "")
    row.setdefault("abstract", work.get("abstract") or "")
    row.setdefault("authors", identity.get("authors") or work.get("authors") or [])
    row.setdefault("venue", identity.get("venue_or_source") or work.get("venue_or_source") or "")
    row.setdefault("year", identity.get("year") or work.get("year"))
    row.setdefault("source_type", identity.get("source_type") or work.get("source_type") or "paper")
    row.setdefault("source_urls", identity.get("source_urls") or work.get("source_urls") or [])
    row["source_updated_at"] = row.get("source_updated_at") or source_state.get("source_updated_at") or ""
    row["source_modified_at"] = row.get("source_modified_at") or source_state.get("source_modified_at") or ""
    concepts = bundle.get("concepts") or work.get("concepts") or []
    evidence = bundle.get("evidence") or work.get("evidence") or []
    source_work = {
        "work_id": row.get("work_id") or work.get("work_id") or "",
        "title": row.get("title") or identity.get("canonical_title") or "",
        "venue_or_source": row.get("venue") or identity.get("venue_or_source") or "",
        "year": row.get("year") or identity.get("year") or "",
        "url_or_doi": row.get("url_or_doi") or (row.get("source_urls") or [""])[0],
    }
    concept_records = [_flatten_concept_record(concept, source_work, evidence, row) for concept in concepts if isinstance(concept, dict)]
    concept_records = [record for record in concept_records if record]
    if concept_records:
        row["concept_records"] = concept_records
        row["concept_ids"] = [record.get("concept_id") for record in concept_records if record.get("concept_id")]
        row["concept_types"] = [record.get("concept_type") for record in concept_records if record.get("concept_type")]
        row["concept_labels"] = [_concept_label(record) for record in concept_records if _concept_label(record)]
    row["cloud_bundle_loaded"] = bool(concept_records)
    return row


def _flatten_concept_record(
    concept: dict[str, Any],
    source_work: dict[str, Any],
    evidence_rows: list[dict[str, Any]],
    work_row: dict[str, Any],
) -> dict[str, Any]:
    payload = dict(concept.get("payload") or {})
    concept_id = str(concept.get("concept_id") or "")
    concept_type = str(concept.get("concept_type") or payload.get("concept_type") or "")
    id_key = {
        "existed_idea": "canonical_id",
        "principle": "principle_id",
        "takeaway_message": "canonical_id",
        "benchmark": "benchmark_id",
        "baseline": "baseline_id",
    }.get(concept_type, "canonical_id")
    if concept_id:
        payload.setdefault(id_key, concept_id)
        payload["concept_id"] = concept_id
    payload["concept_type"] = concept_type
    payload.setdefault("canonical_label", concept.get("canonical_label") or "")
    payload.setdefault("canonical_key", concept.get("canonical_key") or "")
    payload.setdefault("source_works", [source_work["work_id"]] if source_work.get("work_id") else [])
    payload.setdefault("source_work_ids", [source_work["work_id"]] if source_work.get("work_id") else [])
    payload["source_work_details"] = [source_work] if source_work.get("work_id") else []
    payload["source_work_title"] = source_work.get("title") or ""
    payload["venue_or_source"] = source_work.get("venue_or_source") or ""
    payload["year"] = source_work.get("year") or ""
    payload["model_keys"] = work_row.get("model_keys") or []
    support = concept.get("support") if isinstance(concept.get("support"), dict) else {}
    payload.setdefault("confidence_score", support.get("confidence_score"))
    payload.setdefault("validation_level", support.get("validation_level") or "")
    payload.setdefault("verification_status", support.get("verification_status") or "")
    evidence = _evidence_for_concept(concept_id, evidence_rows)
    if evidence and not payload.get("evidence"):
        payload["evidence"] = evidence
    if concept_type == "benchmark":
        payload.setdefault("benchmark_name", payload.get("dataset") or payload.get("canonical_label") or concept.get("canonical_label") or "")
        payload.setdefault("dataset", payload.get("benchmark_name") or "")
    elif concept_type == "baseline":
        payload.setdefault("baseline_name", payload.get("method_name") or payload.get("canonical_label") or concept.get("canonical_label") or "")
    elif concept_type == "principle":
        payload.setdefault("name", payload.get("title") or payload.get("canonical_label") or concept.get("canonical_label") or "")
    else:
        payload.setdefault("title", payload.get("canonical_label") or concept.get("canonical_label") or "")
    return payload


def _evidence_for_concept(concept_id: str, evidence_rows: list[dict[str, Any]]) -> str:
    for row in evidence_rows:
        if str(row.get("concept_id") or "") != concept_id:
            continue
        return str(row.get("snippet") or row.get("claim_text") or row.get("evidence_span") or "")
    return ""


def _concept_label(record: dict[str, Any]) -> str:
    return str(
        record.get("title")
        or record.get("name")
        or record.get("benchmark_name")
        or record.get("baseline_name")
        or record.get("canonical_label")
        or record.get("core_idea")
        or record.get("message_text")
        or record.get("argument")
        or ""
    )


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?", (table,)).fetchone()
    return bool(row)


def _unique(values: list[Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def _unique_int(values: list[Any]) -> list[int]:
    output: list[int] = []
    seen: set[int] = set()
    for value in values:
        try:
            number = int(value)
        except Exception:
            continue
        if number in seen:
            continue
        seen.add(number)
        output.append(number)
    return output
