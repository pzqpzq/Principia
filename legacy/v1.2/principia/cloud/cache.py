from __future__ import annotations

import json
import shutil
import sqlite3
import threading
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from ..models import utc_now
from .compression import decompress_file
from .ids import sha256_hex


_ASSET_LOCKS: dict[str, threading.Lock] = {}
_ASSET_LOCKS_GUARD = threading.Lock()


class CloudCache:
    def __init__(self, db_path: Path, artifact_root: Path):
        self.db_path = db_path
        self.artifact_root = artifact_root
        self.artifact_root.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def cache_asset(self, asset: dict[str, Any], *, snapshot_id: str = "") -> Path:
        asset_id = str(asset.get("asset_id") or "")
        if not asset_id:
            raise ValueError("Cloud asset is missing asset_id")
        url = str(asset.get("url") or "")
        suffix = Path(url).suffix or ".asset"
        local = self.artifact_root / "assets" / f"{asset_id}{suffix}"
        local.parent.mkdir(parents=True, exist_ok=True)
        lock = _asset_lock(str(local))
        with lock:
            if not local.exists() or not self._checksum_ok(local, asset.get("sha256")):
                raw = self._fetch(url)
                if asset.get("sha256") and sha256_hex(raw) != asset.get("sha256"):
                    raise ValueError(f"Checksum mismatch for {asset_id}")
                tmp = local.with_suffix(local.suffix + ".tmp")
                tmp.write_bytes(raw)
                tmp.replace(local)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO cloud_asset_cache(
                    asset_id, snapshot_id, kind, record_type, url, local_path,
                    sha256, bytes, fetched_at, cache_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ready')
                """,
                (
                    asset_id,
                    snapshot_id,
                    asset.get("kind") or "",
                    asset.get("record_type") or asset.get("route_type") or "",
                    url,
                    str(local),
                    asset.get("sha256") or sha256_hex(local.read_bytes()),
                    local.stat().st_size,
                    utc_now(),
                ),
            )
        return local

    def unpack_sqlite_asset(self, asset: dict[str, Any], *, snapshot_id: str = "") -> Path:
        packed = self.cache_asset(asset, snapshot_id=snapshot_id)
        unpacked = self.artifact_root / "indexes" / packed.name.removesuffix(".gz")
        lock = _asset_lock(str(unpacked))
        with lock:
            if not unpacked.exists() or unpacked.stat().st_mtime < packed.stat().st_mtime:
                tmp = unpacked.with_suffix(unpacked.suffix + ".tmp")
                decompress_file(packed, tmp)
                tmp.replace(unpacked)
        return unpacked

    def cache_payload(self, *, record_id: str, snapshot_id: str, record_type: str, payload: dict[str, Any], payload_sha256: str = "") -> None:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO cloud_payload_cache(
                    record_id, snapshot_id, record_type, payload_json,
                    payload_sha256, fetched_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (record_id, snapshot_id, record_type, body, payload_sha256 or sha256_hex(body), utc_now()),
            )

    def log_resolution(self, *, cache_key: str, snapshot_id: str, work_id: str, resolution: dict[str, Any], model_key: str, source_state_hash: str, decision: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO cloud_resolution_cache(
                    cache_key, snapshot_id, work_id, resolution_json, model_key,
                    source_state_hash, decision, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (cache_key, snapshot_id, work_id, json.dumps(resolution, ensure_ascii=False), model_key, source_state_hash, decision, utc_now()),
            )

    def stats(self) -> dict[str, Any]:
        with self._connect() as conn:
            assets = conn.execute("SELECT COUNT(*), COALESCE(SUM(bytes), 0) FROM cloud_asset_cache WHERE cache_status = 'ready'").fetchone()
            payloads = conn.execute("SELECT COUNT(*) FROM cloud_payload_cache").fetchone()
            resolutions = conn.execute("SELECT decision, COUNT(*) FROM cloud_resolution_cache GROUP BY decision").fetchall()
        return {
            "asset_count": int(assets[0] or 0),
            "asset_bytes": int(assets[1] or 0),
            "payload_count": int(payloads[0] or 0),
            "resolution_decisions": {str(row[0] or ""): int(row[1] or 0) for row in resolutions},
        }

    def _fetch(self, url: str) -> bytes:
        if not url:
            raise ValueError("Cloud asset has no URL")
        if url.startswith("http://") or url.startswith("https://"):
            req = Request(url, headers={"User-Agent": "PrincipiaCloud/1.1"})
            with urlopen(req, timeout=30) as resp:
                return resp.read()
        if url.startswith("file://"):
            return Path(url.removeprefix("file://")).read_bytes()
        path = Path(url)
        if not path.is_absolute():
            path = Path.cwd() / path
        return path.read_bytes()

    def _checksum_ok(self, path: Path, expected: Any) -> bool:
        if not expected:
            return True
        return sha256_hex(path.read_bytes()) == str(expected)


def _asset_lock(key: str) -> threading.Lock:
    with _ASSET_LOCKS_GUARD:
        lock = _ASSET_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _ASSET_LOCKS[key] = lock
        return lock
