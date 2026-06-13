from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from ..config import ROOT_DIR
from ..models import utc_now
from . import POINTER_SCHEMA_VERSION, SCHEMA_VERSION
from .ids import sha256_hex


DEFAULT_POINTER = ROOT_DIR / "cloud" / "manifests" / "latest.json"
LOCAL_SEED_MANIFEST = ROOT_DIR / "dist" / "cloud-seed" / "manifest.json"


def _read_url_or_path(ref: str, *, timeout: int = 20) -> bytes:
    if ref.startswith("http://") or ref.startswith("https://"):
        req = Request(ref, headers={"User-Agent": "PrincipiaCloud/1.1"})
        with urlopen(req, timeout=timeout) as resp:
            return resp.read()
    if ref.startswith("file://"):
        return Path(ref.removeprefix("file://")).read_bytes()
    return Path(ref).read_bytes()


class CloudManifestClient:
    def __init__(self, pointer_path: Path | None = None):
        self.pointer_path = pointer_path or DEFAULT_POINTER

    def load_pointer(self) -> dict[str, Any]:
        if not self.pointer_path.exists():
            return empty_pointer()
        try:
            return json.loads(self.pointer_path.read_text(encoding="utf-8"))
        except Exception:
            return empty_pointer()

    def load_manifest(self, *, refresh: bool = False) -> dict[str, Any]:
        pointer = self.load_pointer()
        inline = pointer.get("inline_manifest")
        if isinstance(inline, dict):
            return inline
        url = str(pointer.get("latest_manifest_url") or "").strip()
        if not url:
            if LOCAL_SEED_MANIFEST.exists():
                return json.loads(LOCAL_SEED_MANIFEST.read_text(encoding="utf-8"))
            return empty_manifest()
        raw = _read_url_or_path(url)
        expected = str(pointer.get("latest_manifest_sha256") or "").strip()
        actual = sha256_hex(raw)
        if expected and expected != actual:
            raise ValueError("Cloud manifest checksum mismatch")
        return json.loads(raw.decode("utf-8"))

    def stats(self) -> dict[str, Any]:
        manifest = self.load_manifest()
        return {
            "schema_version": manifest.get("schema_version", SCHEMA_VERSION),
            "snapshot_id": manifest.get("snapshot_id", ""),
            "created_at": manifest.get("created_at", ""),
            "counts": manifest.get("counts", {}),
            "supported_model_keys": manifest.get("supported_model_keys", []),
            "facets": manifest.get("facets", {}),
            "assets": len(manifest.get("assets") or []),
            "deltas": len(manifest.get("deltas") or []),
            "tombstones": len(manifest.get("tombstones") or []),
        }


def empty_pointer() -> dict[str, Any]:
    return {
        "schema_version": POINTER_SCHEMA_VERSION,
        "latest_snapshot_id": "",
        "latest_manifest_url": "",
        "latest_manifest_sha256": "",
        "updated_at": utc_now(),
    }


def empty_manifest() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "snapshot_id": "",
        "created_at": "",
        "counts": {},
        "supported_model_keys": [],
        "retention_policy": {"max_versions_per_work_model_key": 3},
        "route_indexes": {},
        "assets": [],
        "deltas": [],
        "tombstones": [],
        "license_notice": "metadata and extracted research-memory records; no full paper text",
    }


def asset_by_id(manifest: dict[str, Any], asset_id: str) -> dict[str, Any] | None:
    for asset in manifest.get("assets") or []:
        if asset.get("asset_id") == asset_id:
            return asset
    return None


def write_pointer(path: Path, manifest_path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    raw = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    pointer = {
        "schema_version": POINTER_SCHEMA_VERSION,
        "latest_snapshot_id": manifest.get("snapshot_id", ""),
        "latest_manifest_url": str(manifest_path),
        "latest_manifest_sha256": sha256_hex(raw),
        "updated_at": utc_now(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pointer, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return pointer
