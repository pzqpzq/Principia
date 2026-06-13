from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from principia.cloud.compactor import export_snapshot
from principia.cloud.crawler import plan_crawl
from principia.cloud.manifest import CloudManifestClient
from principia.cloud.pack import read_record, write_pack
from principia.cloud.resolver import CloudResolver
from principia.cloud.search import CloudSearch
from principia.cloud.contribution import prepare_contribution
from principia.cloud.validator import validate_contribution
from principia.global_store import GlobalStore
from principia.models import utc_now
from principia.storage import Store
from principia.work_versioning import model_key


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

    def test_crawler_plan_is_dry_run_and_normalizes_venues(self) -> None:
        plan = plan_crawl(venues=["nmi", "ICLR"], years=[2025], topics=["agents"], max_papers=5, model_key="fake:model:auto:prompt:schema:work_concepts")
        self.assertEqual(plan["venues"][0], "Nature Machine Intelligence")
        self.assertEqual(len(plan["candidates"]), 5)
        self.assertTrue(plan["dry_run"])

    def test_100k_synthetic_snapshot_scale_is_opt_in(self) -> None:
        if os.getenv("PRINCIPIA_RUN_SCALE_TESTS") != "1":
            self.skipTest("Set PRINCIPIA_RUN_SCALE_TESTS=1 to run the 100k synthetic snapshot check.")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pack-work-100k.pcz"
            records = (
                {
                    "record_type": "work",
                    "work_id": f"W_SCALE_{idx:06d}",
                    "title": f"Synthetic work {idx}",
                    "abstract": "Synthetic capacity fixture.",
                }
                for idx in range(100_000)
            )
            entries = write_pack(path, records, pack_id="pack-work-100k", record_type="work", records_per_block=512)
            self.assertEqual(len(entries), 100_000)
            self.assertLess(path.stat().st_size, 2 * 1024 * 1024 * 1024)

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
        global_store.complete_extraction_run(run["extraction_run_id"], result={"principle_count": 1})
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
        store.upsert("source_works", {"work_id": work["work_id"], "title": "Cloud cache paper", "abstract": "A reusable extraction target."}, "work_id")
        store.upsert("principles", {"principle_id": concept["concept_id"], "name": "Cache reuse principle", "source_works": [work["work_id"]]}, "principle_id")
        return current_model_key


if __name__ == "__main__":
    unittest.main()
