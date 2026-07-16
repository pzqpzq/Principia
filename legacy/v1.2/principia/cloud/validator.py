from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import CONTRIBUTION_SCHEMA_VERSION, SCHEMA_VERSION


FORBIDDEN_FULL_TEXT_KEYS = {
    "full_text",
    "pdf_text",
    "paper_text",
    "raw_pdf",
    "full_text_excerpt",
}


def validate_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append("manifest.schema_version must be principia-cloud-1.1")
    if not manifest.get("snapshot_id"):
        errors.append("manifest.snapshot_id is required")
    if not isinstance(manifest.get("assets", []), list):
        errors.append("manifest.assets must be a list")
    seen = set()
    for asset in manifest.get("assets") or []:
        asset_id = asset.get("asset_id")
        if not asset_id:
            errors.append("asset.asset_id is required")
        elif asset_id in seen:
            errors.append(f"duplicate asset_id: {asset_id}")
        seen.add(asset_id)
        if int(asset.get("bytes") or 0) >= 2 * 1024 * 1024 * 1024:
            errors.append(f"asset exceeds GitHub release limit: {asset_id}")
    return {"ok": not errors, "errors": errors}


def validate_contribution(data: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if data.get("schema_version") != CONTRIBUTION_SCHEMA_VERSION:
        errors.append("contribution.schema_version must be principia-cloud-contribution-1.1")
    if not data.get("contribution_id"):
        errors.append("contribution_id is required")
    if not data.get("model_key"):
        warnings.append("model_key is empty; contribution can be metadata-only but will not satisfy model coverage")
    for section in ("work_records", "work_version_records", "extraction_records", "concept_records", "relation_records", "evidence_records"):
        if not isinstance(data.get(section, []), list):
            errors.append(f"{section} must be a list")
    for section in ("work_records", "work_version_records", "extraction_records", "concept_records", "relation_records", "evidence_records"):
        for idx, record in enumerate(data.get(section) or []):
            _validate_public_scope(record, f"{section}[{idx}]", errors, warnings)
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def validate_contribution_file(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "errors": [f"Cannot read contribution JSON: {exc}"], "warnings": []}
    return validate_contribution(data)


def _validate_public_scope(record: Any, prefix: str, errors: list[str], warnings: list[str]) -> None:
    if not isinstance(record, dict):
        errors.append(f"{prefix} must be an object")
        return
    for key, value in record.items():
        if key in FORBIDDEN_FULL_TEXT_KEYS:
            errors.append(f"{prefix}.{key} is forbidden in public cloud packs")
        if isinstance(value, str) and len(value) > 12000:
            warnings.append(f"{prefix}.{key} is unusually long; check that it is not full paper text")
        if isinstance(value, dict):
            _validate_public_scope(value, f"{prefix}.{key}", errors, warnings)
        elif isinstance(value, list):
            for idx, item in enumerate(value):
                if isinstance(item, dict):
                    _validate_public_scope(item, f"{prefix}.{key}[{idx}]", errors, warnings)
