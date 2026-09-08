from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from ..models import utc_now
from ..utils import stable_id
from . import DEFAULT_CONCEPT_SHARDS, DEFAULT_WORK_SHARDS, SCHEMA_VERSION
from .ids import sha256_hex
from .pack import PackEntry, write_pack
from .route_index import build_concept_route_indexes, build_work_route_indexes
from .search_index import build_work_search_index
from .validator import validate_contribution, validate_manifest


def export_snapshot(
    db_path: Path,
    out_dir: Path,
    *,
    snapshot_id: str = "",
    work_shards: int = DEFAULT_WORK_SHARDS,
    concept_shards: int = DEFAULT_CONCEPT_SHARDS,
    limit: int | None = None,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    packs_dir = out_dir / "packs"
    indexes_dir = out_dir / "indexes"
    work_bundles, concept_records = _read_records(db_path, limit=limit)
    concept_records = _dedupe_concepts(concept_records)
    snapshot_id = snapshot_id or stable_id("SNAP", utc_now(), len(work_bundles), len(concept_records))
    work_pack = packs_dir / "pack-work-0000.pcz"
    concept_pack = packs_dir / "pack-concept-0000.pcz"
    concept_entries = write_pack(concept_pack, concept_records, pack_id="pack-concept-0000", record_type="concept")
    concept_entry_by_id: dict[str, PackEntry] = {entry.record_id: entry for entry in concept_entries}
    work_bundles = [_reference_concepts(bundle, concept_entry_by_id) for bundle in work_bundles]
    work_entries = write_pack(work_pack, work_bundles, pack_id="pack-work-0000", record_type="work_bundle")
    entry_by_id: dict[str, PackEntry] = {entry.record_id: entry for entry in [*work_entries, *concept_entries]}
    work_route_assets = build_work_route_indexes(indexes_dir, [bundle["work"] for bundle in work_bundles], entry_by_id, shard_count=work_shards)
    concept_route_assets = build_concept_route_indexes(indexes_dir, concept_records, entry_by_id, shard_count=concept_shards) if concept_records else []
    search_asset, facets = build_work_search_index(indexes_dir, work_bundles, concept_records)
    assets = [
        _asset("pack-work-0000", "pack", "work", work_pack),
        _asset("pack-concept-0000", "pack", "concept", concept_pack),
        *[_indexed_asset(asset, indexes_dir / f"{asset['asset_id']}.sqlite.gz") for asset in work_route_assets],
        *[_indexed_asset(asset, indexes_dir / f"{asset['asset_id']}.sqlite.gz") for asset in concept_route_assets],
        _indexed_asset(search_asset, indexes_dir / f"{search_asset['asset_id']}.sqlite.gz"),
    ]
    assets = [asset for asset in assets if Path(asset["url"]).exists()]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "snapshot_id": snapshot_id,
        "created_at": utc_now(),
        "generated_by": {"tool": "principia.cloud.compactor", "tool_version": "1.1.0", "git_commit": ""},
        "counts": {
            "works": len(work_bundles),
            "work_versions": sum(len(bundle.get("work_versions") or []) for bundle in work_bundles),
            "active_extraction_versions": sum(len(bundle.get("extraction_runs") or []) for bundle in work_bundles),
            "concepts": len(concept_records),
            "relations": 0,
            "evidence_links": sum(len(bundle.get("evidence") or []) for bundle in work_bundles),
        },
        "facets": facets,
        "supported_model_keys": _model_keys(work_bundles),
        "retention_policy": {"max_versions_per_work_model_key": 3},
        "route_indexes": {
            "work": {"shard_count": work_shards, "shard_key": "sha256_identity_prefix"},
            "concept": {"shard_count": concept_shards, "shard_key": "sha256_concept_id_prefix"},
        },
        "assets": assets,
        "deltas": [],
        "tombstones": [],
        "license_notice": "metadata and extracted research-memory records; no full paper text",
        "source_attribution_policy": "records must preserve DOI/arXiv/OpenAlex/OpenReview/Semantic Scholar/Crossref/source URLs when available",
    }
    validation = validate_manifest(manifest)
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (out_dir / "stats.json").write_text(json.dumps(manifest["counts"], ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    checksums = "\n".join(f"{asset['sha256']}  {Path(asset['url']).name}" for asset in assets)
    (out_dir / "checksums.sha256").write_text(checksums + "\n", encoding="utf-8")
    return {"ok": validation["ok"], "manifest": manifest, "manifest_path": str(manifest_path), "validation": validation}


def compact_contributions(input_dir: Path, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    accepted = []
    rejected = []
    work_records: dict[str, dict[str, Any]] = {}
    versions_by_work: dict[str, list[dict[str, Any]]] = {}
    extractions_by_work: dict[str, list[dict[str, Any]]] = {}
    evidence_by_work: dict[str, list[dict[str, Any]]] = {}
    concepts_by_id: dict[str, dict[str, Any]] = {}
    admin_operations: list[dict[str, Any]] = []
    for path in sorted(input_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            rejected.append({"path": str(path), "error": str(exc)})
            continue
        if data.get("operation_id") and data.get("operation_type"):
            admin_operations.append(data)
            accepted.append({"path": str(path), "operation_id": data.get("operation_id"), "admin_operations": 1})
            continue
        validation = validate_contribution(data)
        if not validation["ok"]:
            rejected.append({"path": str(path), "error": "; ".join(validation["errors"]), "warnings": validation.get("warnings", [])})
            continue
        if not data.get("work_records") and not data.get("admin_operations"):
            rejected.append({"path": str(path), "error": "no work records"})
            continue
        for record in data.get("work_records") or []:
            work_id = str(record.get("work_id") or "")
            if work_id:
                work_records[work_id] = _merge_public_work(work_records.get(work_id), record)
        for record in data.get("work_version_records") or []:
            versions_by_work.setdefault(str(record.get("work_id") or ""), []).append(record)
        for record in data.get("extraction_records") or []:
            extractions_by_work.setdefault(str(record.get("work_id") or ""), []).append(record)
        for record in data.get("evidence_records") or []:
            evidence_by_work.setdefault(str(record.get("work_id") or ""), []).append(record)
        for record in data.get("concept_records") or []:
            concept_id = str(record.get("concept_id") or "")
            if concept_id:
                concepts_by_id[concept_id] = _merge_public_concept(concepts_by_id.get(concept_id), record)
        admin_operations.extend(list(data.get("admin_operations") or []))
        accepted.append(
            {
                "path": str(path),
                "contribution_id": data.get("contribution_id"),
                "works": len(data.get("work_records") or []),
                "admin_operations": len(data.get("admin_operations") or []),
                "warnings": validation.get("warnings", []),
            }
        )
    _apply_admin_operations(work_records, concepts_by_id, versions_by_work, extractions_by_work, evidence_by_work, admin_operations)
    concept_records, concept_id_map = _dedupe_concepts_with_aliases(list(concepts_by_id.values()))
    if concept_id_map:
        for rows in evidence_by_work.values():
            for row in rows:
                concept_id = str(row.get("concept_id") or "")
                if concept_id in concept_id_map:
                    row["concept_id"] = concept_id_map[concept_id]
    concept_by_id = {str(record.get("concept_id") or ""): record for record in concept_records}
    work_bundles = []
    for work_id, record in sorted(work_records.items()):
        versions = _latest_three_versions(versions_by_work.get(work_id, []))
        extractions = _retained_extractions(extractions_by_work.get(work_id, []))
        evidence = evidence_by_work.get(work_id, [])
        related = []
        for item in evidence:
            concept = concept_by_id.get(str(item.get("concept_id") or ""))
            if concept and concept not in related:
                related.append(concept)
        work = _public_work_bundle_record(record, versions, extractions, evidence, related)
        work_bundles.append(
            {
                "record_type": "work_bundle",
                "work_id": work_id,
                "work": work,
                "work_versions": versions,
                "extraction_runs": extractions,
                "concepts": related,
                "evidence": evidence,
            }
        )
    if work_bundles:
        snapshot = _write_snapshot_from_records(work_bundles, concept_records, out_dir)
        report = {
            "ok": snapshot["ok"] and not rejected,
            "accepted": accepted,
            "rejected": rejected,
            "created_at": utc_now(),
            "snapshot_id": snapshot["manifest"].get("snapshot_id"),
            "manifest_path": snapshot["manifest_path"],
            "validation": snapshot["validation"],
            "counts": snapshot["manifest"].get("counts", {}),
        }
    else:
        report = {"ok": False, "accepted": accepted, "rejected": rejected, "created_at": utc_now(), "error": "no compactable work records"}
    (out_dir / "compaction-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def _write_snapshot_from_records(work_bundles: list[dict[str, Any]], concept_records: list[dict[str, Any]], out_dir: Path) -> dict[str, Any]:
    packs_dir = out_dir / "packs"
    indexes_dir = out_dir / "indexes"
    snapshot_id = stable_id("SNAP", utc_now(), len(work_bundles), len(concept_records))
    work_pack = packs_dir / "pack-work-0000.pcz"
    concept_pack = packs_dir / "pack-concept-0000.pcz"
    concept_entries = write_pack(concept_pack, concept_records, pack_id="pack-concept-0000", record_type="concept")
    concept_entry_by_id: dict[str, PackEntry] = {entry.record_id: entry for entry in concept_entries}
    work_bundles = [_reference_concepts(bundle, concept_entry_by_id) for bundle in work_bundles]
    work_entries = write_pack(work_pack, work_bundles, pack_id="pack-work-0000", record_type="work_bundle")
    entry_by_id: dict[str, PackEntry] = {entry.record_id: entry for entry in [*work_entries, *concept_entries]}
    work_route_assets = build_work_route_indexes(indexes_dir, [bundle["work"] for bundle in work_bundles], entry_by_id, shard_count=DEFAULT_WORK_SHARDS)
    concept_route_assets = build_concept_route_indexes(indexes_dir, concept_records, entry_by_id, shard_count=DEFAULT_CONCEPT_SHARDS) if concept_records else []
    search_asset, facets = build_work_search_index(indexes_dir, work_bundles, concept_records)
    assets = [
        _asset("pack-work-0000", "pack", "work", work_pack),
        _asset("pack-concept-0000", "pack", "concept", concept_pack),
        *[_indexed_asset(asset, indexes_dir / f"{asset['asset_id']}.sqlite.gz") for asset in work_route_assets],
        *[_indexed_asset(asset, indexes_dir / f"{asset['asset_id']}.sqlite.gz") for asset in concept_route_assets],
        _indexed_asset(search_asset, indexes_dir / f"{search_asset['asset_id']}.sqlite.gz"),
    ]
    assets = [asset for asset in assets if Path(asset["url"]).exists()]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "snapshot_id": snapshot_id,
        "created_at": utc_now(),
        "generated_by": {"tool": "principia.cloud.compactor", "tool_version": "1.1.0", "source": "contributions"},
        "counts": {
            "works": len(work_bundles),
            "work_versions": sum(len(bundle.get("work_versions") or []) for bundle in work_bundles),
            "active_extraction_versions": sum(len(bundle.get("extraction_runs") or []) for bundle in work_bundles),
            "concepts": len(concept_records),
            "relations": 0,
            "evidence_links": sum(len(bundle.get("evidence") or []) for bundle in work_bundles),
        },
        "facets": facets,
        "supported_model_keys": _model_keys(work_bundles),
        "retention_policy": {"max_versions_per_work_model_key": 3},
        "route_indexes": {
            "work": {"shard_count": DEFAULT_WORK_SHARDS, "shard_key": "sha256_identity_prefix"},
            "concept": {"shard_count": DEFAULT_CONCEPT_SHARDS, "shard_key": "sha256_concept_id_prefix"},
        },
        "assets": assets,
        "deltas": [],
        "tombstones": [],
        "license_notice": "metadata and extracted research-memory records; no full paper text",
        "source_attribution_policy": "records must preserve DOI/arXiv/OpenAlex/OpenReview/Semantic Scholar/Crossref/source URLs when available",
    }
    validation = validate_manifest(manifest)
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (out_dir / "stats.json").write_text(json.dumps(manifest["counts"], ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    checksums = "\n".join(f"{asset['sha256']}  {Path(asset['url']).name}" for asset in assets)
    (out_dir / "checksums.sha256").write_text(checksums + "\n", encoding="utf-8")
    return {"ok": validation["ok"], "manifest": manifest, "manifest_path": str(manifest_path), "validation": validation}


def _merge_public_work(existing: dict[str, Any] | None, incoming: dict[str, Any]) -> dict[str, Any]:
    if not existing:
        return dict(incoming)
    old_ts = str((existing.get("timestamps") or {}).get("updated_at") or "")
    new_ts = str((incoming.get("timestamps") or {}).get("updated_at") or "")
    return dict(incoming if new_ts >= old_ts else existing)


def _merge_public_concept(existing: dict[str, Any] | None, incoming: dict[str, Any]) -> dict[str, Any]:
    if not existing:
        return dict(incoming)
    merged = dict(existing)
    incoming_ts = str((incoming.get("timestamps") or {}).get("updated_at") or incoming.get("updated_at") or "")
    existing_ts = str((merged.get("timestamps") or {}).get("updated_at") or merged.get("updated_at") or "")
    incoming_support = incoming.get("support") or {}
    existing_support = merged.get("support") or {}
    incoming_conf = float(incoming_support.get("confidence_score") or incoming.get("confidence_score") or 0.0)
    existing_conf = float(existing_support.get("confidence_score") or merged.get("confidence_score") or 0.0)
    if incoming_ts > existing_ts or incoming_conf > existing_conf:
        for key in ("canonical_label", "payload", "versioning", "timestamps", "aliases"):
            if incoming.get(key):
                merged[key] = incoming.get(key)
    support = dict(merged.get("support") or {})
    support["supporting_work_ids"] = sorted(
        {
            *[str(item) for item in support.get("supporting_work_ids") or []],
            *[str(item) for item in incoming_support.get("supporting_work_ids") or []],
        }
    )
    support["evidence_count"] = max(int(support.get("evidence_count") or 0), int(incoming_support.get("evidence_count") or 0))
    support["confidence_score"] = max(float(support.get("confidence_score") or 0.5), float(incoming_support.get("confidence_score") or 0.5))
    merged["support"] = support
    return merged


def _apply_admin_operations(
    works: dict[str, dict[str, Any]],
    concepts: dict[str, dict[str, Any]],
    versions: dict[str, list[dict[str, Any]]],
    extractions: dict[str, list[dict[str, Any]]],
    evidence: dict[str, list[dict[str, Any]]],
    operations: list[dict[str, Any]],
) -> None:
    for operation in operations:
        op_type = str(operation.get("operation_type") or "")
        payload = operation.get("payload") or {}
        target_id = str(payload.get("work_id") or payload.get("concept_id") or payload.get("target_id") or "")
        if op_type == "delete" and target_id:
            works.pop(target_id, None)
            concepts.pop(target_id, None)
            versions.pop(target_id, None)
            extractions.pop(target_id, None)
            evidence.pop(target_id, None)
        elif op_type == "edit" and target_id and target_id in works:
            works[target_id] = _merge_public_work(works[target_id], dict(payload.get("record") or payload))
        elif op_type == "edit" and target_id and target_id in concepts:
            concepts[target_id] = _merge_public_concept(concepts[target_id], dict(payload.get("record") or payload))


def _latest_three_versions(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(records, key=lambda item: item.get("created_at") or "")
    return ordered[-3:]


def _public_work_bundle_record(
    record: dict[str, Any],
    versions: list[dict[str, Any]],
    extractions: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
) -> dict[str, Any]:
    work = dict(record)
    latest_by_model: dict[str, dict[str, Any]] = {}
    by_model: dict[str, list[dict[str, Any]]] = {}
    for extraction in sorted(extractions, key=lambda item: item.get("completed_at") or item.get("created_at") or ""):
        model = str(extraction.get("model_key") or "")
        if model:
            by_model.setdefault(model, []).append(extraction)
    for model, retained in by_model.items():
        active = retained[-1]
        latest_by_model[model] = {
            "active_extraction_run_id": active.get("extraction_run_id") or "",
            "active_work_version_id": active.get("work_version_id") or "",
            "last_three_extraction_run_ids": [item.get("extraction_run_id") for item in retained[-3:] if item.get("extraction_run_id")],
            "last_three_record_pack_refs": ["pack-work-0000"],
        }
    work["latest_by_model"] = latest_by_model
    if versions:
        latest = versions[-1]
        work["abstract"] = latest.get("abstract") or work.get("abstract") or ""
        source_state = dict(work.get("source_state") or {})
        for key in ("source_provider", "source_record_id", "source_modified_at", "source_updated_at", "title_hash", "abstract_hash", "content_hash"):
            if latest.get(key):
                source_state[key] = latest.get(key)
        work["source_state"] = source_state
    work["relations"] = {"principles": [item.get("concept_id") for item in concepts if item.get("concept_type") == "principle"]}
    work["work_versions"] = versions
    work["extraction_runs"] = extractions
    work["concepts"] = concepts
    work["evidence"] = evidence
    return work


def _dedupe_concepts(concepts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _dedupe_concepts_with_aliases(concepts)[0]


def _dedupe_concepts_with_aliases(concepts: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    by_key: dict[str, dict[str, Any]] = {}
    id_map: dict[str, str] = {}
    for concept in concepts:
        key = f"{concept.get('concept_type') or ''}:{concept.get('canonical_key') or concept.get('concept_id') or ''}"
        if key not in by_key:
            by_key[key] = concept
            concept_id = str(concept.get("concept_id") or "")
            if concept_id:
                id_map[concept_id] = concept_id
            continue
        existing = by_key[key]
        by_key[key] = _merge_public_concept(existing, concept)
        kept_id = str(by_key[key].get("concept_id") or existing.get("concept_id") or "")
        duplicate_id = str(concept.get("concept_id") or "")
        if duplicate_id and kept_id:
            id_map[duplicate_id] = kept_id
    return list(by_key.values()), id_map


def _reference_concepts(bundle: dict[str, Any], concept_entries: dict[str, PackEntry]) -> dict[str, Any]:
    output = dict(bundle)
    work = dict(output.get("work") or {})
    refs = []
    for concept in output.get("concepts") or work.get("concepts") or []:
        concept_id = str(concept.get("concept_id") or "")
        entry = concept_entries.get(concept_id)
        if not concept_id or not entry:
            continue
        refs.append(
            {
                "concept_id": concept_id,
                "concept_type": concept.get("concept_type") or "",
                "canonical_key": concept.get("canonical_key") or "",
                "canonical_label": concept.get("canonical_label") or "",
                "pack_id": entry.pack_id,
                "offset": entry.offset,
                "length": entry.length,
                "checksum": entry.checksum,
            }
        )
    work["concept_refs"] = refs
    work.pop("concepts", None)
    output["work"] = work
    output["concept_refs"] = refs
    output.pop("concepts", None)
    return output


def _read_records(db_path: Path, *, limit: int | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        work_rows = [dict(row) for row in conn.execute("SELECT * FROM global_work ORDER BY updated_at DESC" + (f" LIMIT {int(limit)}" if limit else "")).fetchall()]
        versions = _group(conn, "work_version", "work_id")
        extractions = _group(conn, "extraction_run", "work_id")
        evidence = _group(conn, "evidence_link", "work_id")
        concept_rows = [dict(row) for row in conn.execute("SELECT * FROM concept_card ORDER BY updated_at DESC").fetchall()]
        concept_versions = _latest_concept_payloads(conn)
    concepts = [_concept_record(row, concept_versions.get(row["concept_id"], {})) for row in concept_rows]
    concept_by_id = {concept["concept_id"]: concept for concept in concepts}
    bundles = []
    for row in work_rows:
        work_id = row["work_id"]
        related_concepts = []
        for ev in evidence.get(work_id, []):
            concept = concept_by_id.get(ev.get("concept_id"))
            if concept and concept not in related_concepts:
                related_concepts.append(concept)
        work = _work_record(row, versions.get(work_id, []), extractions.get(work_id, []), evidence.get(work_id, []), related_concepts)
        bundles.append({"record_type": "work_bundle", "work_id": work_id, "work": work, "work_versions": work.get("work_versions", []), "extraction_runs": work.get("extraction_runs", []), "concepts": related_concepts, "evidence": evidence.get(work_id, [])})
    return bundles, concepts


def _group(conn: sqlite3.Connection, table: str, key: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in conn.execute(f"SELECT * FROM {table}").fetchall():
        item = dict(row)
        grouped.setdefault(str(item.get(key) or ""), []).append(item)
    return grouped


def _latest_concept_payloads(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    output = {}
    for row in conn.execute("SELECT * FROM concept_version WHERE is_active = 1").fetchall():
        item = dict(row)
        try:
            output[item["concept_id"]] = json.loads(item.get("payload_json") or "{}")
        except Exception:
            output[item["concept_id"]] = {}
    return output


def _loads(text: str) -> Any:
    try:
        return json.loads(text or "{}")
    except Exception:
        return {}


def _work_record(row: dict[str, Any], versions: list[dict[str, Any]], extractions: list[dict[str, Any]], evidence: list[dict[str, Any]], concepts: list[dict[str, Any]]) -> dict[str, Any]:
    metadata = _loads(row.get("metadata_json", "{}"))
    version_records = [_work_version_record(item) for item in versions]
    extraction_records = _retained_extractions([_extraction_record(item) for item in extractions])
    model_map: dict[str, dict[str, Any]] = {}
    by_model: dict[str, list[dict[str, Any]]] = {}
    for extraction in sorted(extraction_records, key=lambda item: item.get("completed_at") or item.get("created_at") or ""):
        by_model.setdefault(extraction["model_key"], []).append(extraction)
    for model_key, retained in by_model.items():
        active = retained[-1]
        model_map[model_key] = {
            "active_extraction_run_id": active["extraction_run_id"],
            "active_work_version_id": active["work_version_id"],
            "last_three_extraction_run_ids": [item["extraction_run_id"] for item in retained[-3:]],
            "last_three_record_pack_refs": ["pack-work-0000"],
        }
    return {
        "record_type": "work",
        "work_id": row["work_id"],
        "identity": {
            "canonical_title": row.get("canonical_title"),
            "title_norm": row.get("title_norm"),
            "title_hash": row.get("title_hash"),
            "doi": row.get("doi") or "",
            "arxiv_id": row.get("arxiv_id") or "",
            "openalex_id": row.get("openalex_id") or "",
            "crossref_id": row.get("crossref_id") or "",
            "semantic_scholar_id": row.get("semantic_scholar_id") or "",
            "authors": metadata.get("authors") or [],
            "year": row.get("year"),
            "venue_or_source": row.get("venue_or_source") or "",
            "source_type": row.get("source_type") or "paper",
            "source_urls": _loads(row.get("source_urls_json", "[]")),
        },
        "abstract": version_records[0].get("abstract", "") if version_records else "",
        "source_state": {
            "source_provider": version_records[0].get("source_provider", "") if version_records else "",
            "source_record_id": version_records[0].get("source_record_id", "") if version_records else "",
            "source_modified_at": version_records[0].get("source_modified_at", "") if version_records else "",
            "source_updated_at": version_records[0].get("source_updated_at", "") if version_records else metadata.get("source_updated_at", ""),
            "title_hash": row.get("title_hash"),
            "abstract_hash": version_records[0].get("abstract_hash", "") if version_records else "",
            "content_hash": version_records[0].get("content_hash", "") if version_records else "",
        },
        "latest_by_model": model_map,
        "relations": {"principles": [c["concept_id"] for c in concepts if c.get("concept_type") == "principle"]},
        "quality": {"validation_level": "L1", "identity_confidence": row.get("identity_confidence") or 1.0, "verification_status": "llm_extracted", "public_scope": "public_cloud"},
        "work_versions": version_records,
        "extraction_runs": extraction_records,
        "concepts": concepts,
        "evidence": [_evidence_record(item) for item in evidence],
        "timestamps": {"created_at": row.get("created_at"), "updated_at": row.get("updated_at")},
    }


def _work_version_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_type": "work_version",
        "work_version_id": row["work_version_id"],
        "work_id": row["work_id"],
        "title": row.get("title") or "",
        "abstract": row.get("abstract") or "",
        "title_hash": row.get("title_hash") or "",
        "abstract_hash": row.get("abstract_hash") or "",
        "content_hash": row.get("content_hash") or "",
        "source_provider": row.get("source_provider") or "",
        "source_record_id": row.get("source_record_id") or "",
        "source_modified_at": row.get("source_modified_at") or "",
        "source_updated_at": row.get("source_updated_at") or "",
        "metadata": _loads(row.get("metadata_json", "{}")),
        "created_at": row.get("created_at"),
    }


def _extraction_record(row: dict[str, Any]) -> dict[str, Any]:
    model_key = ":".join([row.get("llm_provider") or "", row.get("llm_model") or "", row.get("model_mode") or "auto", row.get("prompt_version") or "", row.get("schema_version") or "", row.get("extraction_task_type") or "work_concepts"])
    return {
        "record_type": "extraction_run",
        "extraction_run_id": row["extraction_run_id"],
        "work_id": row["work_id"],
        "work_version_id": row["work_version_id"],
        "model_key": model_key,
        "llm_provider": row.get("llm_provider") or "",
        "llm_model": row.get("llm_model") or "",
        "model_mode": row.get("model_mode") or "auto",
        "prompt_version": row.get("prompt_version") or "",
        "schema_version": row.get("schema_version") or "",
        "extraction_task_type": row.get("extraction_task_type") or "work_concepts",
        "extraction_status": row.get("extraction_status") or "",
        "result_summary": _loads(row.get("result_json", "{}")),
        "created_at": row.get("created_at"),
        "completed_at": row.get("completed_at"),
    }


def _retained_extractions(extractions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_model: dict[str, list[dict[str, Any]]] = {}
    for extraction in extractions:
        by_model.setdefault(str(extraction.get("model_key") or ""), []).append(extraction)
    retained: list[dict[str, Any]] = []
    for items in by_model.values():
        ordered = sorted(items, key=lambda item: item.get("completed_at") or item.get("created_at") or "")
        retained.extend(ordered[-3:])
    return sorted(retained, key=lambda item: item.get("completed_at") or item.get("created_at") or "")


def _concept_record(row: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_type": "concept",
        "concept_id": row["concept_id"],
        "concept_type": row.get("concept_type") or "",
        "canonical_key": row.get("canonical_key") or "",
        "canonical_label": row.get("canonical_label") or "",
        "aliases": [],
        "payload": payload,
        "support": {"supporting_work_ids": payload.get("source_works") or payload.get("source_work_ids") or [], "evidence_count": 0, "confidence_score": row.get("confidence_score") or 0.5, "validation_level": row.get("validation_level") or "L1", "verification_status": row.get("verification_status") or "llm_extracted"},
        "versioning": {"active_version_id": row.get("active_version_id") or "", "last_three_version_ids_by_model": {}},
        "timestamps": {"created_at": row.get("created_at"), "updated_at": row.get("updated_at")},
    }


def _evidence_record(row: dict[str, Any]) -> dict[str, Any]:
    snippet = str(row.get("evidence_span") or "")[:1200]
    return {
        "record_type": "evidence",
        "evidence_id": row["evidence_id"],
        "concept_id": row.get("concept_id") or "",
        "work_id": row.get("work_id") or "",
        "work_version_id": row.get("work_version_id") or "",
        "evidence_type": row.get("evidence_type") or "metadata",
        "locator": {"source_url": row.get("source_url") or ""},
        "snippet": snippet,
        "claim_text": snippet,
        "confidence": row.get("confidence") or 0.5,
        "created_at": row.get("created_at"),
    }


def _asset(asset_id: str, kind: str, record_type: str, path: Path) -> dict[str, Any]:
    return {"asset_id": asset_id, "kind": kind, "record_type": record_type, "url": str(path), "bytes": path.stat().st_size, "sha256": sha256_hex(path.read_bytes()), "compression": "gzip", "format": "pcz"}


def _indexed_asset(asset: dict[str, Any], path: Path) -> dict[str, Any]:
    return {**asset, "url": str(path), "bytes": path.stat().st_size, "sha256": sha256_hex(path.read_bytes()), "compression": "gzip", "format": "sqlite.gz"}


def _model_keys(bundles: list[dict[str, Any]]) -> list[str]:
    keys = {extraction.get("model_key") for bundle in bundles for extraction in bundle.get("extraction_runs") or [] if extraction.get("model_key")}
    return sorted(keys)
