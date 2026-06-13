from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import principia.cloud.crawler as crawler_module
from principia.cloud.compactor import compact_contributions, export_snapshot
from principia.cloud.crawler import plan_crawl
from principia.cloud.github_client import maintainer_direct_push
from principia.cloud.ids import sha256_hex
from principia.cloud.manifest import CloudManifestClient
from principia.cloud.pack import read_record, write_pack
from principia.cloud.route_index import build_work_route_indexes
from principia.cloud.resolver import CloudResolver
from principia.cloud.search import CloudSearch
from principia.cloud.search_index import build_work_search_index
from principia.cloud.contribution import prepare_contribution
from principia.cloud.validator import validate_contribution
from principia.engine import PrincipiaEngine
from principia.global_store import GlobalStore
from principia.models import utc_now
from principia.storage import Store
from principia.work_versioning import model_key, work_content_signature


class CloudV11Tests(unittest.TestCase):
    def make_store(self) -> tuple[tempfile.TemporaryDirectory, Store]:
        tmpdir = tempfile.TemporaryDirectory()
        store = Store(Path(tmpdir.name) / "principia-test.sqlite")
        return tmpdir, store

    def test_cloud_schema_tables_are_created_with_v1_store(self) -> None:
        tmpdir, store = self.make_store()
        self.addCleanup(tmpdir.cleanup)
        with sqlite3.connect(store.path) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'cloud_%'"
                ).fetchall()
            }
        self.assertIn("cloud_manifest_cache", tables)
        self.assertIn("cloud_payload_cache", tables)
        self.assertIn("cloud_relation", tables)

    def test_pack_roundtrip_reads_record_by_block_location(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pack-work-0000.pcz"
            records = [
                {"record_type": "work", "work_id": "W_one", "title": "One"},
                {"record_type": "work", "work_id": "W_two", "title": "Two"},
            ]
            entries = write_pack(path, records, pack_id="pack-work-0000", record_type="work", records_per_block=2)
            entry = next(item for item in entries if item.record_id == "W_two")
            loaded = read_record(path, record_id="W_two", offset=entry.offset, length=entry.length, checksum=entry.checksum)
        self.assertEqual(loaded["title"], "Two")

    def test_resolver_hydrates_cloud_hit_and_skips_llm(self) -> None:
        tmpdir, store = self.make_store()
        self.addCleanup(tmpdir.cleanup)
        current_model_key = self._seed_store(store)
        with tempfile.TemporaryDirectory() as cloud_tmp:
            snapshot = export_snapshot(store.path, Path(cloud_tmp), work_shards=8, concept_shards=4)
            pointer = Path(cloud_tmp) / "latest.json"
            pointer.write_text(
                json.dumps(
                    {
                        "schema_version": "principia-cloud-pointer-1.1",
                        "latest_snapshot_id": snapshot["manifest"]["snapshot_id"],
                        "latest_manifest_url": snapshot["manifest_path"],
                        "latest_manifest_sha256": "",
                        "updated_at": utc_now(),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            fresh_tmp, fresh_store = self.make_store()
            self.addCleanup(fresh_tmp.cleanup)
            resolver = CloudResolver(fresh_store, manifest_client=CloudManifestClient(pointer))
            decision = resolver.resolve_batch(
                [
                    {
                        "work_id": "LOCAL-CANDIDATE",
                        "title": "Cloud cache paper",
                        "abstract": "A reusable extraction target.",
                    }
                ],
                current_model_key,
                project_id="default",
            )[0]
            counts = fresh_store.get_item("source_works", decision["work_id"])
        self.assertFalse(decision["should_extract"])
        self.assertEqual(decision["decision"], "cloud_cache_hit")
        self.assertTrue(decision["hydrated"])
        self.assertIsNotNone(counts)

    def test_resolver_is_safe_under_parallel_cached_reads(self) -> None:
        tmpdir, store = self.make_store()
        self.addCleanup(tmpdir.cleanup)
        current_model_key = self._seed_store(store)
        with tempfile.TemporaryDirectory() as cloud_tmp:
            snapshot = export_snapshot(store.path, Path(cloud_tmp), work_shards=8, concept_shards=4)
            pointer = Path(cloud_tmp) / "latest.json"
            pointer.write_text(
                json.dumps(
                    {
                        "schema_version": "principia-cloud-pointer-1.1",
                        "latest_snapshot_id": snapshot["manifest"]["snapshot_id"],
                        "latest_manifest_url": snapshot["manifest_path"],
                        "latest_manifest_sha256": "",
                        "updated_at": utc_now(),
                    }
                ),
                encoding="utf-8",
            )
            fresh_tmp, fresh_store = self.make_store()
            self.addCleanup(fresh_tmp.cleanup)

            def resolve_once() -> str:
                resolver = CloudResolver(fresh_store, manifest_client=CloudManifestClient(pointer))
                decision = resolver.resolve_batch(
                    [{"work_id": "LOCAL-CANDIDATE", "title": "Cloud cache paper", "abstract": "A reusable extraction target."}],
                    current_model_key,
                )[0]
                return decision["decision"]

            with ThreadPoolExecutor(max_workers=10) as pool:
                decisions = list(pool.map(lambda _: resolve_once(), range(10)))
        self.assertEqual(decisions.count("cloud_cache_hit"), 10)

    def test_search_index_supports_title_venue_year_filters(self) -> None:
        tmpdir, store = self.make_store()
        self.addCleanup(tmpdir.cleanup)
        self._seed_store(store)
        with tempfile.TemporaryDirectory() as cloud_tmp:
            snapshot = export_snapshot(store.path, Path(cloud_tmp), work_shards=8, concept_shards=4)
            pointer = Path(cloud_tmp) / "latest.json"
            pointer.write_text(
                json.dumps(
                    {
                        "schema_version": "principia-cloud-pointer-1.1",
                        "latest_snapshot_id": snapshot["manifest"]["snapshot_id"],
                        "latest_manifest_url": snapshot["manifest_path"],
                        "latest_manifest_sha256": "",
                        "updated_at": utc_now(),
                    }
                ),
                encoding="utf-8",
            )
            fresh_tmp, fresh_store = self.make_store()
            self.addCleanup(fresh_tmp.cleanup)
            search = CloudSearch(CloudResolver(fresh_store, manifest_client=CloudManifestClient(pointer)))
            result = search.search("Cloud cache", venue="ICLR", year=2026, limit=10)
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["title"], "Cloud cache paper")
        self.assertIn("venue", result.get("facets") or {})

    def test_prepare_contribution_records_upload_decisions(self) -> None:
        tmpdir, store = self.make_store()
        self.addCleanup(tmpdir.cleanup)
        current_model_key = self._seed_store(store)
        out_dir = Path(tmpdir.name) / "contributions"
        result = prepare_contribution(store.path, out_dir, model_key=current_model_key, upload_mode="normal")
        self.assertTrue(result["ok"])
        self.assertIn(result["upload_decisions"][0]["cloud_decision"], {"cloud_empty", "not_in_cloud"})
        self.assertTrue(Path(result["path"]).exists())
        data = json.loads(Path(result["path"]).read_text(encoding="utf-8"))
        self.assertEqual(data["upload_decisions"][0]["work_id"], result["allowed_work_ids"][0])

    def test_prepare_contribution_rejects_missing_required_extractions(self) -> None:
        tmpdir, store = self.make_store()
        self.addCleanup(tmpdir.cleanup)
        global_store = GlobalStore(store.path)
        work = global_store.upsert_work(
            {
                "title": "Partial extraction paper",
                "abstract": "Only one extraction category exists.",
                "year": 2026,
                "venue_or_source": "ICLR",
                "source_type": "paper",
            }
        )
        current_model_key = model_key("fake", "fake-model", "auto", "principia-work-extract-v1", "principia-cloud-1.1", "work_concepts")
        run = global_store.ensure_extraction_run(
            work["work_id"],
            work["work_version_id"],
            llm_provider="fake",
            llm_model="fake-model",
            model_mode="auto",
            prompt_version="principia-work-extract-v1",
            schema_version="principia-cloud-1.1",
            extraction_task_type="work_concepts",
        )
        global_store.complete_extraction_run(run["extraction_run_id"], result={"principle_count": 1})
        global_store.upsert_concept(
            "principle",
            {"name": "Partial principle", "argument": "A partial principle.", "source_works": [work["work_id"]]},
            key_text="Partial principle",
            public_scope="public_cloud",
            extraction_run_id=run["extraction_run_id"],
            llm_provider="fake",
            llm_model="fake-model",
            model_mode="auto",
            prompt_version="principia-work-extract-v1",
            schema_version="principia-cloud-1.1",
            evidence=[{"work_id": work["work_id"], "work_version_id": work["work_version_id"], "evidence_span": "Only one extraction category exists."}],
        )

        result = prepare_contribution(store.path, Path(tmpdir.name) / "contributions", model_key=current_model_key, work_ids=[work["work_id"]])
        self.assertFalse(result["ok"])
        self.assertEqual(result["upload_decisions"][0]["cloud_decision"], "missing_required_extractions")
        self.assertIn("existed_idea", result["upload_decisions"][0]["missing_required_extractions"])
        self.assertIn("takeaway_message", result["upload_decisions"][0]["missing_required_extractions"])

    def test_contribution_validation_rejects_full_text(self) -> None:
        result = validate_contribution(
            {
                "schema_version": "principia-cloud-contribution-1.1",
                "contribution_id": "CONTRIB_bad",
                "created_at": utc_now(),
                "upload_mode": "normal",
                "model_key": "fake:model:auto:prompt:schema:work_concepts",
                "work_records": [{"work_id": "W_bad", "full_text": "not allowed"}],
                "work_version_records": [],
                "extraction_records": [],
                "concept_records": [],
                "relation_records": [],
                "evidence_records": [],
            }
        )
        self.assertFalse(result["ok"])
        self.assertTrue(any("full_text" in error for error in result["errors"]))

    def test_compact_contributions_exports_release_ready_snapshot(self) -> None:
        tmpdir, store = self.make_store()
        self.addCleanup(tmpdir.cleanup)
        current_model_key = self._seed_store(store)
        contribution_dir = Path(tmpdir.name) / "contributions"
        prepared = prepare_contribution(store.path, contribution_dir, model_key=current_model_key, upload_mode="normal")
        out_dir = Path(tmpdir.name) / "compact"
        report = compact_contributions(contribution_dir, out_dir)
        self.assertTrue(report["ok"], report)
        self.assertTrue((out_dir / "manifest.json").exists())
        self.assertTrue((out_dir / "packs" / "pack-work-0000.pcz").exists())
        self.assertTrue((out_dir / "indexes" / "work-search-index-0000.sqlite.gz").exists())
        self.assertEqual(report["counts"]["works"], len(prepared["allowed_work_ids"]))

    def test_direct_push_helper_commits_in_isolated_worktree_without_push(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Principia Test"], cwd=repo, check=True)
            (repo / "README.md").write_text("# fixture\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            contribution = repo / "data" / "artifacts" / "cloud" / "contributions" / "CONTRIB_test.json"
            contribution.parent.mkdir(parents=True)
            contribution.write_text('{"schema_version":"principia-cloud-contribution-1.1"}\n', encoding="utf-8")
            result = maintainer_direct_push(str(contribution), repo, branch="codex/test-cloud-contribution", push=False)
            self.assertTrue(result["ok"], result)
            self.assertFalse(result["pushed"])
            self.assertEqual(result["target_path"], "cloud/contributions/CONTRIB_test.json")

    def test_crawler_plan_is_dry_run_and_normalizes_venues(self) -> None:
        plan = plan_crawl(venues=["nmi", "ICLR"], years=[2025], topics=["agents"], max_papers=5, model_key="fake:model:auto:prompt:schema:work_concepts")
        self.assertEqual(plan["venues"][0], "Nature Machine Intelligence")
        self.assertEqual(len(plan["candidates"]), 5)
        self.assertTrue(plan["dry_run"])

    def test_crawler_live_mode_uses_metadata_candidates(self) -> None:
        original = crawler_module.search_hybrid_sources
        original_openreview = crawler_module._openreview_candidates
        calls: list[str] = []

        def fake_search(query: str, max_results: int = 100, timeout: int = 12) -> list[dict[str, object]]:
            calls.append(query)
            return [
                {
                    "work_id": "W_REAL",
                    "title": "Real Metadata Paper",
                    "abstract": "Agent benchmark paper from public metadata.",
                    "year": 2025,
                    "venue_or_source": "ICLR",
                    "source_type": "paper",
                    "source_provider": "fake_public_metadata",
                    "citation_count": 42,
                }
            ]

        crawler_module.search_hybrid_sources = fake_search
        crawler_module._openreview_candidates = lambda *args, **kwargs: []
        try:
            plan = crawler_module.plan_crawl(
                venues=["ICLR"],
                years=[2025],
                topics=["agents"],
                max_papers=3,
                model_key="fake:model:auto:prompt:schema:work_concepts",
                live=True,
                timeout=3,
            )
        finally:
            crawler_module.search_hybrid_sources = original
            crawler_module._openreview_candidates = original_openreview

        self.assertTrue(calls)
        self.assertTrue(plan["live_metadata"])
        self.assertEqual(plan["candidates"][0]["title"], "Real Metadata Paper")
        self.assertEqual(plan["candidates"][0]["crawl_status"], "metadata_candidate")

    def test_crawler_live_mode_enforces_selected_venue_and_year(self) -> None:
        original = crawler_module.search_hybrid_sources
        original_openreview = crawler_module._openreview_candidates

        def fake_search(query: str, max_results: int = 100, timeout: int = 12) -> list[dict[str, object]]:
            _ = (query, max_results, timeout)
            return [
                {
                    "work_id": "W_OFF",
                    "title": "Off venue paper",
                    "abstract": "A public metadata result from the wrong venue.",
                    "year": 2025,
                    "venue_or_source": "AAAI",
                    "source_type": "paper",
                },
                {
                    "work_id": "W_ON",
                    "title": "On venue paper",
                    "abstract": "A public metadata result from the selected venue.",
                    "year": 2025,
                    "venue_or_source": "ICLR",
                    "source_type": "paper",
                },
            ]

        crawler_module.search_hybrid_sources = fake_search
        crawler_module._openreview_candidates = lambda *args, **kwargs: []
        try:
            plan = crawler_module.plan_crawl(
                venues=["ICLR"],
                years=[2025],
                topics=["agents"],
                max_papers=5,
                model_key="fake:model:auto:prompt:schema:work_concepts",
                live=True,
                timeout=3,
            )
        finally:
            crawler_module.search_hybrid_sources = original
            crawler_module._openreview_candidates = original_openreview

        self.assertEqual([item["work_id"] for item in plan["candidates"]], ["W_ON"])
        self.assertTrue(all(item["venue_or_source"] == "ICLR" for item in plan["candidates"]))

    def test_openreview_candidates_parse_real_venue_records_without_templates(self) -> None:
        original_fetch = crawler_module._fetch_openreview_json

        def fake_fetch(url: str, timeout: int) -> dict[str, object]:
            self.assertIn("ICLR.cc%2F2025%2FConference", url)
            return {
                "notes": [
                    {
                        "id": "OR123",
                        "forum": "OR123",
                        "content": {
                            "title": {"value": "Agent Memory via Retrieval Planning"},
                            "authors": {"value": ["A. Author"]},
                            "keywords": {"value": ["agents", "memory"]},
                            "abstract": {"value": "We study retrieval planning for agent memory."},
                        },
                    }
                ]
            }

        crawler_module._fetch_openreview_json = fake_fetch
        try:
            items = crawler_module._openreview_candidates(
                "ICLR",
                2025,
                ["agents"],
                ["venue", "topic"],
                max_papers=3,
                timeout=3,
                warnings=[],
            )
        finally:
            crawler_module._fetch_openreview_json = original_fetch

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["venue_or_source"], "ICLR")
        self.assertEqual(items[0]["source_provider"], "openreview")
        self.assertNotIn("candidate", items[0]["title"].lower())

    def test_cloud_local_tabs_mark_sync_and_cleanup_preserves_project_works(self) -> None:
        tmpdir, store = self.make_store()
        self.addCleanup(tmpdir.cleanup)
        engine = PrincipiaEngine(store=store)
        engine.create_project(name="Cloud Crawl", field_id="cloud-crawl", query="cloud")
        engine.create_project(name="Saved Project", field_id="saved-project", query="saved")
        store.upsert("source_works", {"work_id": "W_SYNCED", "title": "Synced Paper", "cloud_sync_status": "synced"}, "work_id")
        store.upsert("source_works", {"work_id": "W_NEW", "title": "New Paper", "cloud_sync_status": "unsynced"}, "work_id")
        store.upsert("principles", {"principle_id": "P_SYNCED", "name": "Synced principle", "source_works": ["W_SYNCED"], "cloud_sync_status": "synced"}, "principle_id")
        store.upsert("principles", {"principle_id": "P_NEW", "name": "New principle", "source_works": ["W_NEW"], "cloud_sync_status": "unsynced"}, "principle_id")
        engine.add_project_memberships("cloud-crawl", "source_works", ["W_SYNCED", "W_NEW"], source="test")
        engine.add_project_memberships("cloud-crawl", "principles", ["P_SYNCED", "P_NEW"], source="test")
        engine.add_project_memberships("saved-project", "source_works", ["W_SYNCED"], source="test")

        unsynced = engine.build_cloud_local_tab("cloud-crawl", "works", sync_state="unsynced")
        self.assertEqual([item["work_id"] for item in unsynced["items"]], ["W_NEW"])

        marked = engine.mark_cloud_synced(["W_NEW"], field_id="cloud-crawl", contribution_path="/tmp/contrib.json", upload_id="UPLOAD_1")
        self.assertEqual(marked["updated"]["source_works"], 1)
        self.assertEqual(store.get_item("source_works", "W_NEW")["cloud_sync_status"], "synced")

        cleanup = engine.clear_cloud_synced_cache("cloud-crawl")
        self.assertTrue(cleanup["ok"])
        self.assertIsNotNone(store.get_item("source_works", "W_SYNCED"))
        self.assertIsNone(store.get_item("source_works", "W_NEW"))
        self.assertIsNone(store.get_item("principles", "P_NEW"))

    def test_cloud_ready_tab_requires_core_extractions(self) -> None:
        tmpdir, store = self.make_store()
        self.addCleanup(tmpdir.cleanup)
        engine = PrincipiaEngine(store=store)
        engine.create_project(name="Cloud Crawl", field_id="cloud-crawl", query="cloud")
        store.upsert("source_works", {"work_id": "W_READY", "title": "Ready Paper", "cloud_sync_status": "unsynced"}, "work_id")
        store.upsert("source_works", {"work_id": "W_PARTIAL", "title": "Partial Paper", "cloud_sync_status": "unsynced"}, "work_id")
        records = [
            ("existed_ideas", "XI_READY", {"canonical_id": "XI_READY", "title": "Ready idea", "idea_text": "A reusable idea.", "source_works": ["W_READY"]}),
            ("principles", "P_READY", {"principle_id": "P_READY", "name": "Ready principle", "source_works": ["W_READY"]}),
            ("takeaway_messages", "TM_READY", {"canonical_id": "TM_READY", "title": "Ready takeaway", "message_text": "A reusable takeaway.", "source_works": ["W_READY"]}),
            ("principles", "P_PARTIAL", {"principle_id": "P_PARTIAL", "name": "Partial principle", "source_works": ["W_PARTIAL"]}),
        ]
        id_keys = {"existed_ideas": "canonical_id", "principles": "principle_id", "takeaway_messages": "canonical_id"}
        for bucket, record_id, payload in records:
            store.upsert(bucket, payload, id_keys[bucket])
            source_work_id = (payload.get("source_works") or [""])[0]
            store.upsert(
                "evidence_links",
                engine._v2_evidence_link("cloud-crawl", bucket, record_id, source_work_id, "evidence"),
                "link_id",
            )
            engine.add_project_memberships("cloud-crawl", bucket, [record_id], source="test")
        engine.add_project_memberships("cloud-crawl", "source_works", ["W_READY", "W_PARTIAL"], source="test")

        status = engine.cloud_work_research_status("W_READY", field_id="cloud-crawl")
        self.assertTrue(status["ready_to_sync"])
        self.assertFalse(engine.cloud_work_research_status("W_PARTIAL", field_id="cloud-crawl")["ready_to_sync"])
        ready = engine.build_cloud_local_tab("cloud-crawl", "ready_works", sync_state="unsynced")
        self.assertEqual([item["work_id"] for item in ready["items"]], ["W_READY"])

    def test_100k_synthetic_snapshot_scale_is_opt_in(self) -> None:
        if os.getenv("PRINCIPIA_RUN_SCALE_TESTS") != "1":
            self.skipTest("Set PRINCIPIA_RUN_SCALE_TESTS=1 to run the 100k synthetic warm-cache snapshot check.")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "cloud"
            packs = out / "packs"
            indexes = out / "indexes"
            current_model_key = model_key("fake", "fake-model", "auto", "principia-work-extract-v1", "principia-cloud-1.1", "work_concepts")
            bundles = []
            for idx in range(100_000):
                title = f"Synthetic cloud work {idx:06d}"
                abstract = f"Synthetic capacity fixture for cloud lookup {idx:06d}."
                sig = work_content_signature({"title": title, "abstract": abstract})
                work_id = f"W_SCALE_{idx:06d}"
                work = {
                    "record_type": "work",
                    "work_id": work_id,
                    "identity": {
                        "canonical_title": title,
                        "title_hash": sig["title_hash"],
                        "doi": f"10.5555/principia.{idx:06d}",
                        "year": 2026,
                        "venue_or_source": "ICLR",
                        "source_type": "paper",
                    },
                    "abstract": abstract,
                    "source_state": sig,
                    "latest_by_model": {
                        current_model_key: {
                            "active_extraction_run_id": f"XR_SCALE_{idx:06d}",
                            "active_work_version_id": f"WV_SCALE_{idx:06d}",
                            "last_three_extraction_run_ids": [f"XR_SCALE_{idx:06d}"],
                            "last_three_record_pack_refs": ["pack-work-100k"],
                        }
                    },
                    "quality": {"verification_status": "synthetic_scale_fixture", "public_scope": "public_cloud"},
                    "timestamps": {"created_at": utc_now(), "updated_at": utc_now()},
                }
                bundles.append({"record_type": "work_bundle", "work_id": work_id, "work": work, "work_versions": [], "extraction_runs": [], "concepts": [], "evidence": []})
            pack_path = packs / "pack-work-100k.pcz"
            entries = write_pack(pack_path, bundles, pack_id="pack-work-100k", record_type="work_bundle", records_per_block=512)
            entry_by_id = {entry.record_id: entry for entry in entries}
            route_assets = build_work_route_indexes(indexes, [bundle["work"] for bundle in bundles], entry_by_id, shard_count=256)
            search_asset, facets = build_work_search_index(indexes, bundles, [])
            assets = [
                {
                    "asset_id": "pack-work-100k",
                    "kind": "pack",
                    "record_type": "work",
                    "url": str(pack_path),
                    "bytes": pack_path.stat().st_size,
                    "sha256": sha256_hex(pack_path.read_bytes()),
                    "compression": "gzip",
                    "format": "pcz",
                }
            ]
            for asset in [*route_assets, search_asset]:
                path = indexes / f"{asset['asset_id']}.sqlite.gz"
                assets.append(
                    {
                        **asset,
                        "url": str(path),
                        "bytes": path.stat().st_size,
                        "sha256": sha256_hex(path.read_bytes()),
                        "compression": "gzip",
                        "format": "sqlite.gz",
                    }
                )
            manifest = {
                "schema_version": "principia-cloud-1.1",
                "snapshot_id": "SNAP_SCALE_100K",
                "created_at": utc_now(),
                "counts": {"works": 100_000, "concepts": 0},
                "facets": facets,
                "supported_model_keys": [current_model_key],
                "retention_policy": {"max_versions_per_work_model_key": 3},
                "route_indexes": {"work": {"shard_count": 256, "shard_key": "sha256_identity_prefix"}},
                "assets": assets,
                "deltas": [],
                "tombstones": [],
            }
            manifest_path = out / "manifest.json"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            pointer = out / "latest.json"
            pointer.write_text(
                json.dumps(
                    {
                        "schema_version": "principia-cloud-pointer-1.1",
                        "latest_snapshot_id": manifest["snapshot_id"],
                        "latest_manifest_url": str(manifest_path),
                        "latest_manifest_sha256": "",
                        "updated_at": utc_now(),
                    }
                ),
                encoding="utf-8",
            )
            tmpdir, store = self.make_store()
            self.addCleanup(tmpdir.cleanup)
            resolver = CloudResolver(store, manifest_client=CloudManifestClient(pointer))
            candidates = [
                {
                    "work_id": f"LOCAL_SCALE_{idx:02d}",
                    "title": f"Synthetic cloud work {99980 + idx:06d}",
                    "abstract": f"Synthetic capacity fixture for cloud lookup {99980 + idx:06d}.",
                    "doi": f"10.5555/principia.{99980 + idx:06d}",
                }
                for idx in range(20)
            ]
            warmup = resolver.resolve_batch(candidates, current_model_key, hydrate=False)
            self.assertEqual(sum(1 for item in warmup if item["decision"] == "cloud_cache_hit"), 20)
            search = CloudSearch(resolver)
            self.assertTrue(search.search("Synthetic cloud work 099999", limit=5)["items"])

            def read_once(idx: int) -> str:
                local_resolver = CloudResolver(store, manifest_client=CloudManifestClient(pointer))
                decision = local_resolver.resolve_batch([candidates[idx % len(candidates)]], current_model_key, hydrate=False)[0]
                results = CloudSearch(local_resolver).search(f"Synthetic cloud work {99980 + idx % len(candidates):06d}", limit=5)
                return f"{decision['decision']}:{len(results['items'])}"

            started = time.perf_counter()
            with ThreadPoolExecutor(max_workers=20) as pool:
                outputs = list(pool.map(read_once, range(20)))
            elapsed = time.perf_counter() - started
            self.assertEqual(outputs.count("cloud_cache_hit:1"), 20)
            self.assertLessEqual(elapsed, float(os.getenv("PRINCIPIA_SCALE_SECONDS", "2.0")))

    def _seed_store(self, store: Store) -> str:
        global_store = GlobalStore(store.path)
        work = global_store.upsert_work(
            {
                "title": "Cloud cache paper",
                "abstract": "A reusable extraction target.",
                "authors": ["A. Researcher"],
                "year": 2026,
                "venue_or_source": "ICLR",
                "source_type": "paper",
            }
        )
        current_model_key = model_key("fake", "fake-model", "auto", "principia-work-extract-v1", "principia-cloud-1.1", "work_concepts")
        run = global_store.ensure_extraction_run(
            work["work_id"],
            work["work_version_id"],
            llm_provider="fake",
            llm_model="fake-model",
            model_mode="auto",
            prompt_version="principia-work-extract-v1",
            schema_version="principia-cloud-1.1",
            extraction_task_type="work_concepts",
        )
        global_store.complete_extraction_run(run["extraction_run_id"], result={"existed_idea_count": 1, "principle_count": 1, "takeaway_message_count": 1})
        idea = global_store.upsert_concept(
            "existed_idea",
            {
                "title": "Cache reuse idea",
                "idea_text": "Cloud cache reuse avoids repeated extraction when paper identity and model coverage are unchanged.",
                "source_works": [work["work_id"]],
            },
            key_text="Cache reuse idea",
            public_scope="public_cloud",
            extraction_run_id=run["extraction_run_id"],
            llm_provider="fake",
            llm_model="fake-model",
            model_mode="auto",
            prompt_version="principia-work-extract-v1",
            schema_version="principia-cloud-1.1",
            evidence=[
                {
                    "work_id": work["work_id"],
                    "work_version_id": work["work_version_id"],
                    "evidence_span": "A reusable extraction target.",
                    "evidence_type": "abstract",
                    "confidence": 0.9,
                }
            ],
        )
        concept = global_store.upsert_concept(
            "principle",
            {
                "title": "Cache reuse principle",
                "name": "Cache reuse principle",
                "argument": "Reuse source-grounded extraction when identity and model coverage are unchanged.",
                "source_works": [work["work_id"]],
            },
            key_text="Cache reuse principle",
            public_scope="public_cloud",
            extraction_run_id=run["extraction_run_id"],
            llm_provider="fake",
            llm_model="fake-model",
            model_mode="auto",
            prompt_version="principia-work-extract-v1",
            schema_version="principia-cloud-1.1",
            evidence=[
                {
                    "work_id": work["work_id"],
                    "work_version_id": work["work_version_id"],
                    "evidence_span": "A reusable extraction target.",
                    "evidence_type": "abstract",
                    "confidence": 0.9,
                }
            ],
        )
        takeaway = global_store.upsert_concept(
            "takeaway_message",
            {
                "title": "Reuse cached extraction",
                "message_text": "If source identity and model coverage are unchanged, reuse cached paper extraction before calling the LLM again.",
                "source_works": [work["work_id"]],
            },
            key_text="Reuse cached extraction",
            public_scope="public_cloud",
            extraction_run_id=run["extraction_run_id"],
            llm_provider="fake",
            llm_model="fake-model",
            model_mode="auto",
            prompt_version="principia-work-extract-v1",
            schema_version="principia-cloud-1.1",
            evidence=[
                {
                    "work_id": work["work_id"],
                    "work_version_id": work["work_version_id"],
                    "evidence_span": "A reusable extraction target.",
                    "evidence_type": "abstract",
                    "confidence": 0.9,
                }
            ],
        )
        store.upsert("source_works", {"work_id": work["work_id"], "title": "Cloud cache paper", "abstract": "A reusable extraction target."}, "work_id")
        store.upsert("existed_ideas", {"canonical_id": idea["concept_id"], "title": "Cache reuse idea", "idea_text": "Cloud cache reuse avoids repeated extraction when paper identity and model coverage are unchanged.", "source_works": [work["work_id"]]}, "canonical_id")
        store.upsert("principles", {"principle_id": concept["concept_id"], "name": "Cache reuse principle", "source_works": [work["work_id"]]}, "principle_id")
        store.upsert("takeaway_messages", {"canonical_id": takeaway["concept_id"], "title": "Reuse cached extraction", "message_text": "If source identity and model coverage are unchanged, reuse cached paper extraction before calling the LLM again.", "source_works": [work["work_id"]]}, "canonical_id")
        return current_model_key


if __name__ == "__main__":
    unittest.main()
