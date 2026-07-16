from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from ..global_store import GlobalStore
from ..storage import Store
from ..work_versioning import cloud_freshness_decision, work_content_signature
from .cache import CloudCache
from .hydrate import CloudHydrator
from .ids import candidate_identity_keys, candidate_route_shards, sha256_hex
from .manifest import CloudManifestClient, asset_by_id
from .pack import read_record


class CloudResolver:
    def __init__(self, store: Store, manifest_client: CloudManifestClient | None = None):
        self.store = store
        self.global_store = GlobalStore(store.path)
        self.manifest_client = manifest_client or CloudManifestClient()
        self.cache = CloudCache(store.path, store.path.parent / "artifacts" / "cloud")
        self.hydrator = CloudHydrator(self.global_store, store)

    def stats(self) -> dict[str, Any]:
        try:
            stats = self.manifest_client.stats()
        except Exception as exc:
            return {"snapshot_id": "", "counts": {}, "warning": str(exc)}
        return {**stats, "cache": self.cache.stats()}

    def resolve_batch(
        self,
        candidates: list[dict[str, Any]],
        model_key: str,
        *,
        hydrate: bool = True,
        project_id: str = "default",
    ) -> list[dict[str, Any]]:
        try:
            manifest = self.manifest_client.load_manifest()
        except Exception as exc:
            return [self._miss(candidate, "cloud_unavailable", error=str(exc)) for candidate in candidates]
        snapshot_id = str(manifest.get("snapshot_id") or "")
        if not manifest.get("assets") or not snapshot_id:
            return [self._miss(candidate, "cloud_empty") for candidate in candidates]
        work_route = (manifest.get("route_indexes") or {}).get("work") or {}
        shard_count = int(work_route.get("shard_count") or 1)
        shard_assets = {
            int(asset.get("shard")): asset
            for asset in manifest.get("assets") or []
            if asset.get("kind") == "route_index" and asset.get("route_type") == "work"
        }
        needed = sorted({shard for candidate in candidates for shard in candidate_route_shards(candidate, shard_count)})
        route_paths: dict[int, Path] = {}
        with ThreadPoolExecutor(max_workers=min(8, max(1, len(needed)))) as pool:
            futures = {
                pool.submit(self.cache.unpack_sqlite_asset, shard_assets[shard], snapshot_id=snapshot_id): shard
                for shard in needed
                if shard in shard_assets
            }
            for future, shard in list(futures.items()):
                try:
                    route_paths[shard] = future.result()
                except Exception:
                    pass
        results = []
        for candidate in candidates:
            result = self._resolve_one(candidate, model_key, manifest, route_paths, shard_count, hydrate=hydrate, project_id=project_id)
            results.append(result)
        return results

    def fetch_work_bundle_by_id(self, work_id: str, manifest: dict[str, Any] | None = None) -> dict[str, Any] | None:
        work_id = str(work_id or "").strip()
        if not work_id:
            return None
        manifest = manifest or self.manifest_client.load_manifest()
        snapshot_id = str(manifest.get("snapshot_id") or "")
        if not snapshot_id:
            return None
        for asset in manifest.get("assets") or []:
            if asset.get("kind") != "route_index" or asset.get("route_type") != "work":
                continue
            try:
                path = self.cache.unpack_sqlite_asset(asset, snapshot_id=snapshot_id)
                row = self._lookup_route_by_work_id(path, work_id)
            except Exception:
                row = None
            if not row:
                continue
            route = dict(row)
            route["latest_by_model"] = self._loads(route.pop("latest_by_model_json", "{}"))
            return self._fetch_payload(manifest, route, record_id=work_id)
        return None

    def _resolve_one(
        self,
        candidate: dict[str, Any],
        model_key: str,
        manifest: dict[str, Any],
        route_paths: dict[int, Path],
        shard_count: int,
        *,
        hydrate: bool,
        project_id: str,
    ) -> dict[str, Any]:
        keys = candidate_identity_keys(candidate)
        for shard in candidate_route_shards(candidate, shard_count):
            path = route_paths.get(shard)
            if not path:
                continue
            row = self._lookup_route(path, keys)
            if not row:
                continue
            route = dict(row)
            route["latest_by_model"] = self._loads(route.pop("latest_by_model_json", "{}"))
            effective_model_key = self._effective_model_key(model_key, route.get("latest_by_model") or {})
            decision = cloud_freshness_decision(candidate, {"source_state": route, "latest_by_model": route.get("latest_by_model")}, effective_model_key)
            should_extract = bool(decision.get("should_extract"))
            payload = None
            if not should_extract:
                payload = self._fetch_payload(manifest, route, record_id=route["work_id"])
                if hydrate and payload:
                    self.hydrator.hydrate_work_bundle(payload, snapshot_id=manifest.get("snapshot_id", ""), model_key=effective_model_key, project_id=project_id)
            result = {
                "candidate_work_id": candidate.get("work_id") or "",
                "work_id": route["work_id"],
                "decision": decision.get("reason") or "cloud_cache_hit",
                "should_extract": should_extract,
                "cloud_record": payload if payload and not should_extract else None,
                "route": route,
                "hydrated": bool(payload and hydrate and not should_extract),
                "requested_model_key": model_key,
                "model_key": effective_model_key,
            }
            self.cache.log_resolution(
                cache_key=sha256_hex(str(keys) + effective_model_key),
                snapshot_id=str(manifest.get("snapshot_id") or ""),
                work_id=route["work_id"],
                resolution=result,
                model_key=effective_model_key,
                source_state_hash=work_content_signature(candidate).get("content_hash", ""),
                decision=result["decision"],
            )
            return result
        return self._miss(candidate, "not_in_cloud")

    def _lookup_route(self, sqlite_path: Path, keys: dict[str, str]) -> sqlite3.Row | None:
        clauses = []
        params = []
        for column in ("doi", "arxiv_id", "openalex_id", "crossref_id", "semantic_scholar_id", "openreview_forum_id", "title_hash"):
            value = keys.get(column)
            if value:
                clauses.append(f"{column} = ?")
                params.append(value)
        if not clauses:
            return None
        with sqlite3.connect(sqlite_path) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute(f"SELECT * FROM cloud_work_route WHERE {' OR '.join(clauses)} LIMIT 1", params).fetchone()

    def _lookup_route_by_work_id(self, sqlite_path: Path, work_id: str) -> sqlite3.Row | None:
        with sqlite3.connect(sqlite_path) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute("SELECT * FROM cloud_work_route WHERE work_id = ? LIMIT 1", (work_id,)).fetchone()

    def _effective_model_key(self, requested_model_key: str, latest_by_model: dict[str, Any]) -> str:
        requested_model_key = str(requested_model_key or "")
        if requested_model_key and ":auto:" not in requested_model_key:
            return requested_model_key
        keys = [str(key) for key in (latest_by_model or {}).keys() if key]
        if not keys:
            return requested_model_key
        return sorted(keys, key=self._model_strength_rank, reverse=True)[0]

    def _model_strength_rank(self, model_key: str) -> int:
        mode = str(model_key or "").split(":")[2] if len(str(model_key or "").split(":")) > 2 else ""
        order = [
            "openai_gpt55_pro_20260423",
            "openai_gpt55",
            "openai_gpt52_pro",
            "openai_gpt5_pro",
            "qwen_397b",
            "glm",
            "deepseek_pro",
            "deepseek_r1",
            "kimi",
            "qwen_122b",
            "strong",
            "qwen_35b",
            "qwen_27b",
            "auto",
        ]
        try:
            return len(order) - order.index(mode)
        except ValueError:
            return 0

    def _fetch_payload(self, manifest: dict[str, Any], route: dict[str, Any], *, record_id: str) -> dict[str, Any] | None:
        asset = asset_by_id(manifest, route.get("pack_id") or "")
        if not asset:
            return None
        path = self.cache.cache_asset(asset, snapshot_id=str(manifest.get("snapshot_id") or ""))
        payload = read_record(path, record_id=record_id, offset=int(route["offset"]), length=int(route["length"]), checksum=route.get("checksum") or "")
        if payload:
            payload = self._expand_work_refs(manifest, payload)
            self.cache.cache_payload(
                record_id=record_id,
                snapshot_id=str(manifest.get("snapshot_id") or ""),
                record_type=str(payload.get("record_type") or "work"),
                payload=payload,
            )
        return payload

    def _expand_work_refs(self, manifest: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return payload
        work = payload.get("work") if payload.get("record_type") == "work_bundle" else payload
        if not isinstance(work, dict):
            return payload
        refs = work.get("concept_refs") or payload.get("concept_refs") or []
        if not refs or work.get("concepts"):
            return payload
        concepts = []
        for ref in refs[:250]:
            asset = asset_by_id(manifest, str(ref.get("pack_id") or ""))
            if not asset:
                continue
            try:
                path = self.cache.cache_asset(asset, snapshot_id=str(manifest.get("snapshot_id") or ""))
                concept = read_record(
                    path,
                    record_id=str(ref.get("concept_id") or ""),
                    offset=int(ref.get("offset") or 0),
                    length=int(ref.get("length") or 0),
                    checksum=str(ref.get("checksum") or ""),
                )
            except Exception:
                concept = None
            if concept:
                concepts.append(concept)
                self.cache.cache_payload(
                    record_id=str(concept.get("concept_id") or ""),
                    snapshot_id=str(manifest.get("snapshot_id") or ""),
                    record_type="concept",
                    payload=concept,
                )
        if concepts:
            work["concepts"] = concepts
            if payload.get("record_type") == "work_bundle":
                payload["work"] = work
                payload["concepts"] = concepts
            else:
                payload = work
        return payload

    def _miss(self, candidate: dict[str, Any], reason: str, *, error: str = "") -> dict[str, Any]:
        result = {
            "candidate_work_id": candidate.get("work_id") or "",
            "work_id": "",
            "decision": reason,
            "should_extract": True,
            "cloud_record": None,
            "hydrated": False,
        }
        if error:
            result["error"] = error
        return result

    def _loads(self, text: str) -> Any:
        try:
            import json

            return json.loads(text or "{}")
        except Exception:
            return {}
