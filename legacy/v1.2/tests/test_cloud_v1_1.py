from __future__ import annotations

import hashlib
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
import principia.research_sources as research_sources
from principia.cloud.auth import (
    ADMIN_KEY_ENV,
    ADMIN_KEY_HASH_ENV,
    ADMIN_SESSION_SECRET_ENV,
    UPLOAD_KEY_ENV,
    admin_session_status,
    check_admin_session,
    create_admin_session_cookie,
)
from principia.cloud.compactor import _dedupe_concepts_with_aliases, compact_contributions, export_snapshot
from principia.cloud.crawler import plan_crawl
from principia.cloud.github_client import maintainer_direct_push, publish_cloud_contribution
from principia.cloud.hydrate import CloudHydrator
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

    def test_hashed_admin_key_creates_http_only_session_cookie(self) -> None:
        key = "pa_test_admin_key_that_is_not_stored_in_source"
        old_env = {
            ADMIN_KEY_ENV: os.environ.get(ADMIN_KEY_ENV),
            UPLOAD_KEY_ENV: os.environ.get(UPLOAD_KEY_ENV),
            ADMIN_KEY_HASH_ENV: os.environ.get(ADMIN_KEY_HASH_ENV),
            ADMIN_SESSION_SECRET_ENV: os.environ.get(ADMIN_SESSION_SECRET_ENV),
        }
        try:
            os.environ.pop(ADMIN_KEY_ENV, None)
            os.environ.pop(UPLOAD_KEY_ENV, None)
            os.environ.pop(ADMIN_SESSION_SECRET_ENV, None)
            os.environ[ADMIN_KEY_HASH_ENV] = hashlib.sha256(key.encode("utf-8")).hexdigest()

            fixed_cookie = create_admin_session_cookie(now=1000)
            self.assertIn("HttpOnly", fixed_cookie)
            self.assertIn("SameSite=Lax", fixed_cookie)
            self.assertTrue(check_admin_session(fixed_cookie, now=1001))
            self.assertFalse(check_admin_session(fixed_cookie.replace("a", "b", 1), now=1001))
            self.assertFalse(check_admin_session(fixed_cookie, now=1000 + 13 * 60 * 60))

            live_cookie = create_admin_session_cookie()
            status = admin_session_status(live_cookie)
            self.assertTrue(status["configured"])
            self.assertTrue(status["authenticated"])
        finally:
            for name, value in old_env.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

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

    def test_cloud_hydration_is_idempotent_for_existing_concepts(self) -> None:
        tmpdir, store = self.make_store()
        self.addCleanup(tmpdir.cleanup)
        hydrator = CloudHydrator(GlobalStore(store.path), store)
        record = {
            "concept_id": "B-CLOUD-IDEMPOTENT",
            "concept_type": "benchmark",
            "canonical_key": "idempotent-benchmark",
            "canonical_label": "Idempotent Benchmark",
            "model_keys": ["fake:model:auto:prompt:schema:work_concepts"],
            "payload": {
                "concept_id": "B-CLOUD-IDEMPOTENT",
                "benchmark_name": "Idempotent Benchmark",
                "task": "duplicate hydration",
                "metrics": ["accuracy"],
            },
            "support": {"confidence_score": 0.8},
        }
        first = hydrator.hydrate_concept(record, snapshot_id="SNAP-test", model_key="", project_id="cloud-crawl")
        second = hydrator.hydrate_concept(record, snapshot_id="SNAP-test", model_key="", project_id="cloud-crawl")
        with sqlite3.connect(store.path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM concept_card WHERE concept_id = ?", ("B-CLOUD-IDEMPOTENT",)).fetchone()[0]
            membership_count = conn.execute(
                """
                SELECT COUNT(*) FROM records
                WHERE bucket = 'project_memberships'
                AND json_extract(payload, '$.field_id') = 'cloud-crawl'
                AND json_extract(payload, '$.bucket') = 'benchmark_records'
                AND json_extract(payload, '$.record_id') = 'B-CLOUD-IDEMPOTENT'
                """
            ).fetchone()[0]
        legacy = store.get_item("benchmark_records", "B-CLOUD-IDEMPOTENT") or {}
        self.assertEqual(first["concept_id"], "B-CLOUD-IDEMPOTENT")
        self.assertEqual(second["concept_id"], "B-CLOUD-IDEMPOTENT")
        self.assertEqual(count, 1)
        self.assertEqual(membership_count, 1)
        self.assertEqual((legacy.get("cloud_origin") or {}).get("cloud_model_key"), "fake:model:auto:prompt:schema:work_concepts")

    def test_cloud_hydrator_rebinds_extraction_to_local_work_version(self) -> None:
        tmpdir, store = self.make_store()
        self.addCleanup(tmpdir.cleanup)
        hydrator = CloudHydrator(GlobalStore(store.path), store)
        bundle = {
            "record_type": "work_bundle",
            "work_id": "W-CLOUD-FK",
            "work": {
                "record_type": "work",
                "work_id": "W-CLOUD-FK",
                "identity": {
                    "canonical_title": "Hydrator FK Paper",
                    "title_norm": "hydrator fk paper",
                    "title_hash": "hydrator-fk",
                    "source_urls": ["https://arxiv.org/abs/2601.00001v1"],
                    "year": 2026,
                    "venue_or_source": "ICML",
                    "source_type": "paper",
                },
                "abstract": "A paper whose release extraction run references a remote work version.",
                "work_versions": [
                    {
                        "work_version_id": "WV-REMOTE-ONLY",
                        "work_id": "W-CLOUD-FK",
                        "title": "Hydrator FK Paper",
                        "abstract": "A paper whose release extraction run references a remote work version.",
                        "source_provider": "test",
                        "source_record_id": "remote",
                    }
                ],
                "extraction_runs": [
                    {
                        "extraction_run_id": "ER-REMOTE",
                        "work_id": "W-CLOUD-FK",
                        "work_version_id": "WV-REMOTE-ONLY",
                        "llm_provider": "siliconflow",
                        "llm_model": "Qwen/Qwen3.5-397B-A17B",
                        "model_mode": "qwen_397b",
                        "prompt_version": "principia-work-extract-v1",
                        "schema_version": "principia-cloud-1.1",
                        "extraction_task_type": "work_concepts",
                        "extraction_status": "complete",
                    }
                ],
            },
            "concepts": [
                {
                    "concept_id": "P-CLOUD-FK",
                    "concept_type": "principle",
                    "canonical_label": "Hydrated FK Principle",
                    "payload": {
                        "concept_id": "P-CLOUD-FK",
                        "principle_id": "P-CLOUD-FK",
                        "name": "Hydrated FK Principle",
                        "argument": "Imported concepts should hydrate even when release work-version IDs are remote.",
                        "source_work_ids": ["W-CLOUD-FK"],
                        "source_work_title": "Hydrator FK Paper",
                    },
                    "support": {"supporting_work_ids": ["W-CLOUD-FK"], "confidence_score": 0.8},
                }
            ],
        }
        result = hydrator.hydrate_work_bundle(
            bundle,
            snapshot_id="SNAP-fk",
            model_key="siliconflow:Qwen/Qwen3.5-397B-A17B:qwen_397b:principia-work-extract-v1:principia-cloud-1.1:work_concepts",
            project_id="cloud-crawl",
        )
        self.assertEqual(len(result["concepts"]), 1)
        self.assertIsNotNone(store.get_item("principles", "P-CLOUD-FK"))
        with sqlite3.connect(store.path) as conn:
            run = conn.execute(
                "SELECT work_version_id FROM extraction_run WHERE llm_model = 'Qwen/Qwen3.5-397B-A17B' AND model_mode = 'qwen_397b'"
            ).fetchone()
            self.assertIsNotNone(run)
            self.assertNotEqual(run[0], "WV-REMOTE-ONLY")

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

    def test_search_index_supports_other_venue_and_year_filters(self) -> None:
        tmpdir, store = self.make_store()
        self.addCleanup(tmpdir.cleanup)
        self._seed_store(store)
        self._seed_store_with_work(
            store,
            title="Residual cloud cache paper",
            abstract="A paper from a residual venue facet.",
            venue="Workshop on AI Systems",
            year=2019,
            doi="10.5555/residual-cloud-cache",
        )
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
            selected = search.search("Cloud cache", venues=["ICLR"], years=[2026], limit=10)
            residual = search.search(
                "Cloud cache",
                venue_other=True,
                known_venues=["ICLR", "NeurIPS"],
                year_other=True,
                known_years=[2026, 2025],
                limit=10,
            )
        self.assertEqual([item["title"] for item in selected["items"]], ["Cloud cache paper"])
        self.assertEqual([item["title"] for item in residual["items"]], ["Residual cloud cache paper"])

    def test_search_enriches_released_concept_payloads(self) -> None:
        tmpdir, store = self.make_store()
        self.addCleanup(tmpdir.cleanup)
        current_model_key = self._seed_store(store)
        global_store = GlobalStore(store.path)
        with sqlite3.connect(store.path) as conn:
            conn.row_factory = sqlite3.Row
            work = dict(conn.execute("SELECT * FROM global_work LIMIT 1").fetchone())
            version = dict(conn.execute("SELECT * FROM work_version WHERE work_id = ? LIMIT 1", (work["work_id"],)).fetchone())
            run = dict(conn.execute("SELECT * FROM extraction_run WHERE work_id = ? LIMIT 1", (work["work_id"],)).fetchone())
        global_store.upsert_concept(
            "benchmark",
            {
                "benchmark_name": "MATH",
                "dataset": "MATH",
                "task": "competition mathematics reasoning",
                "data_form": "public problem set",
                "metrics": ["accuracy"],
                "description": "Mathematical reasoning benchmark.",
                "source_works": [work["work_id"]],
            },
            key_text="MATH",
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
                    "work_version_id": version["work_version_id"],
                    "evidence_span": "The evaluation uses the MATH benchmark.",
                    "evidence_type": "abstract",
                    "confidence": 0.9,
                }
            ],
        )
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
            result = search.search("Cloud cache", model_key=current_model_key, limit=10)
        self.assertEqual(len(result["items"]), 1)
        benchmark = next(item for item in result["items"][0]["concept_records"] if item["concept_type"] == "benchmark")
        self.assertEqual(benchmark["benchmark_name"], "MATH")
        self.assertEqual(benchmark["task"], "competition mathematics reasoning")
        self.assertEqual(benchmark["metrics"], ["accuracy"])

    def test_local_manifest_checksum_mismatch_repairs_pointer(self) -> None:
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
                        "latest_snapshot_id": "STALE",
                        "latest_manifest_url": snapshot["manifest_path"],
                        "latest_manifest_sha256": "bad-sha",
                        "updated_at": utc_now(),
                    }
                ),
                encoding="utf-8",
            )
            manifest = CloudManifestClient(pointer).load_manifest()
            repaired = json.loads(pointer.read_text(encoding="utf-8"))
            expected_sha = sha256_hex(Path(repaired["latest_manifest_url"]).read_bytes())
        self.assertEqual(manifest["snapshot_id"], snapshot["manifest"]["snapshot_id"])
        self.assertEqual(repaired["latest_snapshot_id"], snapshot["manifest"]["snapshot_id"])
        self.assertEqual(repaired["latest_manifest_sha256"], expected_sha)

    def test_manifest_url_env_can_point_to_released_pointer(self) -> None:
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
            old = os.environ.get("PRINCIPIA_CLOUD_MANIFEST_URL")
            os.environ["PRINCIPIA_CLOUD_MANIFEST_URL"] = str(pointer)
            try:
                manifest = CloudManifestClient(Path(cloud_tmp) / "unused-local-pointer.json").load_manifest()
            finally:
                if old is None:
                    os.environ.pop("PRINCIPIA_CLOUD_MANIFEST_URL", None)
                else:
                    os.environ["PRINCIPIA_CLOUD_MANIFEST_URL"] = old
        self.assertEqual(manifest["snapshot_id"], snapshot["manifest"]["snapshot_id"])

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
        self.assertTrue(result["ok"], result["upload_decisions"])
        self.assertEqual(result["allowed_work_ids"], [work["work_id"]])
        self.assertEqual(result["upload_decisions"][0]["missing_required_extractions"], [])

    def test_prepare_contribution_allows_missing_takeaway_when_either_core_record_exists(self) -> None:
        tmpdir, store = self.make_store()
        self.addCleanup(tmpdir.cleanup)
        global_store = GlobalStore(store.path)
        work = global_store.upsert_work(
            {
                "title": "Core extraction paper",
                "abstract": "This paper has a high quality existed idea and principle but no takeaway.",
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
        global_store.complete_extraction_run(run["extraction_run_id"], result={"existed_idea_count": 1, "principle_count": 1})
        global_store.upsert_concept(
            "existed_idea",
            {
                "title": "Core idea",
                "idea_text": "A concrete source-grounded mechanism extracted from the paper.",
                "source_works": [work["work_id"]],
                "confidence_score": 0.72,
            },
            key_text="Core idea",
            public_scope="public_cloud",
            extraction_run_id=run["extraction_run_id"],
            llm_provider="fake",
            llm_model="fake-model",
            model_mode="auto",
            prompt_version="principia-work-extract-v1",
            schema_version="principia-cloud-1.1",
            evidence=[{"work_id": work["work_id"], "work_version_id": work["work_version_id"], "evidence_span": "A concrete source-grounded mechanism."}],
        )
        global_store.upsert_concept(
            "principle",
            {
                "name": "Core principle",
                "argument": "A reusable principle with enough source-grounded substance.",
                "source_works": [work["work_id"]],
                "confidence_score": 0.72,
            },
            key_text="Core principle",
            public_scope="public_cloud",
            extraction_run_id=run["extraction_run_id"],
            llm_provider="fake",
            llm_model="fake-model",
            model_mode="auto",
            prompt_version="principia-work-extract-v1",
            schema_version="principia-cloud-1.1",
            evidence=[{"work_id": work["work_id"], "work_version_id": work["work_version_id"], "evidence_span": "A reusable principle."}],
        )

        result = prepare_contribution(store.path, Path(tmpdir.name) / "contributions", model_key=current_model_key, work_ids=[work["work_id"]])
        self.assertTrue(result["ok"], result["upload_decisions"])
        self.assertEqual(result["allowed_work_ids"], [work["work_id"]])
        self.assertEqual(result["upload_decisions"][0]["missing_required_extractions"], [])

    def test_prepare_contribution_rejects_when_no_core_extraction_exists(self) -> None:
        tmpdir, store = self.make_store()
        self.addCleanup(tmpdir.cleanup)
        global_store = GlobalStore(store.path)
        work = global_store.upsert_work(
            {
                "title": "No core extraction paper",
                "abstract": "This paper has only a takeaway, which is not enough for cloud upload.",
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
        global_store.complete_extraction_run(run["extraction_run_id"], result={"takeaway_message_count": 1})
        global_store.upsert_concept(
            "takeaway_message",
            {
                "title": "Only takeaway",
                "message_text": "A takeaway alone should not pass the upload gate.",
                "source_works": [work["work_id"]],
                "confidence_score": 0.9,
            },
            key_text="Only takeaway",
            public_scope="public_cloud",
            extraction_run_id=run["extraction_run_id"],
            llm_provider="fake",
            llm_model="fake-model",
            model_mode="auto",
            prompt_version="principia-work-extract-v1",
            schema_version="principia-cloud-1.1",
            evidence=[{"work_id": work["work_id"], "work_version_id": work["work_version_id"], "evidence_span": "A takeaway."}],
        )

        result = prepare_contribution(store.path, Path(tmpdir.name) / "contributions", model_key=current_model_key, work_ids=[work["work_id"]])
        self.assertFalse(result["ok"])
        self.assertEqual(result["upload_decisions"][0]["cloud_decision"], "missing_required_extractions")
        self.assertEqual(result["upload_decisions"][0]["missing_required_extractions"], ["principle_or_existed_idea"])

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

    def test_compactor_merges_concepts_by_canonical_key_and_returns_aliases(self) -> None:
        concepts, aliases = _dedupe_concepts_with_aliases(
            [
                {
                    "concept_id": "C_ONE",
                    "concept_type": "benchmark",
                    "canonical_key": "imagenet-c",
                    "canonical_label": "ImageNet-C",
                    "payload": {"benchmark_name": "ImageNet-C"},
                    "support": {"supporting_work_ids": ["W1"], "evidence_count": 1, "confidence_score": 0.7},
                },
                {
                    "concept_id": "C_TWO",
                    "concept_type": "benchmark",
                    "canonical_key": "imagenet-c",
                    "canonical_label": "ImageNet-C corruption benchmark",
                    "payload": {"benchmark_name": "ImageNet-C", "metrics": ["accuracy"]},
                    "support": {"supporting_work_ids": ["W2"], "evidence_count": 2, "confidence_score": 0.8},
                },
            ]
        )
        self.assertEqual(len(concepts), 1)
        self.assertEqual(aliases["C_TWO"], "C_ONE")
        self.assertEqual(concepts[0]["support"]["supporting_work_ids"], ["W1", "W2"])
        self.assertEqual(concepts[0]["support"]["evidence_count"], 2)

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
                    "work_id": "W_BOOK",
                    "title": "12 Machine Learning Patterns from ICLR and NeurIPS",
                    "abstract": "A handbook chapter mentioning ICLR, NeurIPS, ICML, CVPR, and ACL, but not published there.",
                    "year": 2025,
                    "venue_or_source": "The Handbook of Data Science and AI",
                    "source_type": "book_chapter",
                },
                {
                    "work_id": "W_ON",
                    "title": "On venue agent paper",
                    "abstract": "A public metadata result from the selected venue about agent planning.",
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
        self.assertNotIn("W_BOOK", [item["work_id"] for item in plan["candidates"]])

    def test_crawler_live_mode_other_venue_is_explicit_residual_filter(self) -> None:
        original = crawler_module.search_hybrid_sources
        original_openreview = crawler_module._openreview_candidates

        def fake_search(query: str, max_results: int = 100, timeout: int = 12) -> list[dict[str, object]]:
            _ = (query, max_results, timeout)
            return [
                {
                    "work_id": "W_ICLR",
                    "title": "Known venue paper",
                    "abstract": "An agent systems paper from a known venue.",
                    "year": 2025,
                    "venue_or_source": "ICLR",
                    "source_type": "paper",
                },
                {
                    "work_id": "W_OTHER",
                    "title": "Residual venue paper",
                    "abstract": "An agent systems paper from a residual venue.",
                    "year": 2024,
                    "venue_or_source": "Workshop on AI Systems",
                    "source_type": "paper",
                },
            ]

        crawler_module.search_hybrid_sources = fake_search
        crawler_module._openreview_candidates = lambda *args, **kwargs: []
        try:
            plan = crawler_module.plan_crawl(
                venues=[],
                venue_other=True,
                known_venues=["ICLR", "NeurIPS"],
                years=[],
                year_other=True,
                known_years=[2025],
                topics=["agent systems"],
                max_papers=5,
                model_key="fake:model:auto:prompt:schema:work_concepts",
                live=True,
                timeout=3,
            )
        finally:
            crawler_module.search_hybrid_sources = original
            crawler_module._openreview_candidates = original_openreview

        self.assertEqual([item["work_id"] for item in plan["candidates"]], ["W_OTHER"])
        self.assertEqual(plan["candidates"][0]["venue_or_source"], "Workshop on AI Systems")

    def test_crawler_live_mode_enforces_topic_relevance_for_test_time_scaling(self) -> None:
        original = crawler_module.search_hybrid_sources
        original_openreview = crawler_module._openreview_candidates

        def fake_search(query: str, max_results: int = 100, timeout: int = 12) -> list[dict[str, object]]:
            _ = (query, max_results, timeout)
            return [
                {
                    "work_id": "W_IRRELEVANT",
                    "title": "General Machine Learning Survey",
                    "abstract": "A broad survey of supervised learning systems.",
                    "year": 2025,
                    "venue_or_source": "ICLR",
                    "source_type": "paper",
                },
                {
                    "work_id": "W_TTS",
                    "title": "Inference-Time Scaling for Language Model Reasoning",
                    "abstract": "The method allocates additional test-time compute to improve reasoning accuracy.",
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
                topics=["test-time scaling"],
                max_papers=5,
                model_key="fake:model:auto:prompt:schema:work_concepts",
                live=True,
                timeout=3,
            )
        finally:
            crawler_module.search_hybrid_sources = original
            crawler_module._openreview_candidates = original_openreview

        self.assertEqual([item["work_id"] for item in plan["candidates"]], ["W_TTS"])
        self.assertGreater(plan["candidates"][0]["topic_score"], 0)

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
        store.upsert("source_works", {"work_id": "W_PRINCIPLE_ONLY", "title": "Principle Only Paper", "cloud_sync_status": "unsynced"}, "work_id")
        store.upsert("source_works", {"work_id": "W_TAKEAWAY_ONLY", "title": "Takeaway Only Paper", "cloud_sync_status": "unsynced"}, "work_id")
        records = [
            ("existed_ideas", "Ready idea", {"title": "Ready idea", "idea_text": "A reusable idea.", "source_works": ["W_READY"]}),
            ("principles", "Ready principle", {"name": "Ready principle", "argument": "A reusable principle.", "source_works": ["W_READY"]}),
            ("takeaway_messages", "Ready takeaway", {"title": "Ready takeaway", "message_text": "A reusable takeaway.", "source_works": ["W_READY"]}),
            ("principles", "Principle-only record", {"name": "Principle-only record", "argument": "A usable principle.", "source_works": ["W_PRINCIPLE_ONLY"]}),
            ("takeaway_messages", "Takeaway-only record", {"title": "Takeaway-only record", "message_text": "A useful takeaway without core extraction.", "source_works": ["W_TAKEAWAY_ONLY"]}),
        ]
        id_keys = {"existed_ideas": "canonical_id", "principles": "principle_id", "takeaway_messages": "canonical_id"}
        for bucket, key_text, payload in records:
            item = engine._v2_upsert_canonical(bucket, key_text, payload, model_mode="auto")
            record_id = item[id_keys[bucket]]
            source_work_id = (payload.get("source_works") or [""])[0]
            store.upsert(
                "evidence_links",
                engine._v2_evidence_link("cloud-crawl", bucket, record_id, source_work_id, "evidence"),
                "link_id",
            )
            engine.add_project_memberships("cloud-crawl", bucket, [record_id], source="test")
        engine.add_project_memberships("cloud-crawl", "source_works", ["W_READY", "W_PRINCIPLE_ONLY", "W_TAKEAWAY_ONLY"], source="test")
        engine._set_cloud_work_research_state("W_READY", "ready", model_mode="auto", message="Ready.")
        engine._set_cloud_work_research_state("W_PRINCIPLE_ONLY", "needs_review", model_mode="auto", message="Missing optional records.")
        engine._set_cloud_work_research_state("W_TAKEAWAY_ONLY", "needs_review", model_mode="auto", message="Missing principle or existed idea.")

        status = engine.cloud_work_research_status("W_READY", field_id="cloud-crawl")
        self.assertTrue(status["ready_to_sync"])
        self.assertTrue(engine.cloud_work_research_status("W_PRINCIPLE_ONLY", field_id="cloud-crawl")["ready_to_sync"])
        self.assertFalse(engine.cloud_work_research_status("W_TAKEAWAY_ONLY", field_id="cloud-crawl")["ready_to_sync"])
        ready = engine.build_cloud_local_tab("cloud-crawl", "ready_works", sync_state="unsynced")
        self.assertEqual({item["work_id"] for item in ready["items"]}, {"W_READY", "W_PRINCIPLE_ONLY"})
        principles = engine.build_cloud_local_tab("cloud-crawl", "principles", sync_state="unsynced")
        self.assertEqual({item["name"] for item in principles["items"]}, {"Ready principle", "Principle-only record"})

    def test_cloud_queue_ready_and_sync_are_target_llm_scoped(self) -> None:
        tmpdir, store = self.make_store()
        self.addCleanup(tmpdir.cleanup)
        engine = PrincipiaEngine(store=store)
        engine.create_project(name="Cloud Crawl", field_id="cloud-crawl", query="cloud")
        queued = engine.queue_cloud_candidates(
            [
                {
                    "title": "LLM scoped paper",
                    "abstract": "A paper that should be tracked independently per target model.",
                    "year": 2026,
                    "venue_or_source": "ICLR",
                }
            ],
            field_id="cloud-crawl",
            model_mode="qwen_27b",
        )
        work_id = queued["work_ids"][0]
        self.assertEqual(len(engine.build_cloud_local_tab("cloud-crawl", "queued_works", model_mode="qwen_27b")["items"]), 1)
        self.assertEqual(len(engine.build_cloud_local_tab("cloud-crawl", "queued_works", model_mode="qwen_35b")["items"]), 1)

        records = [
            ("existed_ideas", "Scoped idea", {"title": "Scoped idea", "idea_text": "A scoped idea.", "source_works": [work_id]}),
            ("principles", "Scoped principle", {"name": "Scoped principle", "argument": "A scoped principle.", "source_works": [work_id]}),
            ("takeaway_messages", "Scoped takeaway", {"title": "Scoped takeaway", "message_text": "A scoped takeaway.", "source_works": [work_id]}),
        ]
        id_keys = {"existed_ideas": "canonical_id", "principles": "principle_id", "takeaway_messages": "canonical_id"}
        for bucket, key_text, payload in records:
            item = engine._v2_upsert_canonical(bucket, key_text, payload, model_mode="qwen_27b")
            record_id = item[id_keys[bucket]]
            store.upsert(
                "evidence_links",
                engine._v2_evidence_link("cloud-crawl", bucket, record_id, work_id, "evidence"),
                "link_id",
            )
            engine.add_project_memberships("cloud-crawl", bucket, [record_id], source="test")

        self.assertTrue(engine.cloud_work_research_status(work_id, field_id="cloud-crawl", model_mode="qwen_27b")["ready_to_sync"])
        self.assertFalse(engine.cloud_work_research_status(work_id, field_id="cloud-crawl", model_mode="qwen_35b")["ready_to_sync"])
        self.assertEqual(len(engine.build_cloud_local_tab("cloud-crawl", "ready_works", model_mode="qwen_27b")["items"]), 1)
        self.assertEqual(engine.build_cloud_local_tab("cloud-crawl", "ready_works", model_mode="qwen_35b")["items"], [])
        self.assertEqual(len(engine.build_cloud_local_tab("cloud-crawl", "existed_ideas", model_mode="qwen_27b")["items"]), 1)
        self.assertEqual(len(engine.build_cloud_local_tab("cloud-crawl", "principles", model_mode="qwen_27b")["items"]), 1)
        self.assertEqual(len(engine.build_cloud_local_tab("cloud-crawl", "takeaway_messages", model_mode="qwen_27b")["items"]), 1)
        self.assertEqual(engine.build_cloud_local_tab("cloud-crawl", "principles", model_mode="qwen_35b")["items"], [])

        engine.mark_cloud_synced([work_id], field_id="cloud-crawl", model_mode="qwen_27b")
        self.assertTrue(engine.cloud_work_research_status(work_id, field_id="cloud-crawl", model_mode="qwen_27b")["synced"])
        self.assertFalse(engine.cloud_work_research_status(work_id, field_id="cloud-crawl", model_mode="qwen_35b")["synced"])
        self.assertEqual(engine.build_cloud_local_tab("cloud-crawl", "principles", model_mode="qwen_27b")["items"], [])
        self.assertEqual(len(engine.build_cloud_local_tab("cloud-crawl", "queued_works", model_mode="qwen_35b")["items"]), 1)

        engine.queue_cloud_candidates([store.get_item("source_works", work_id)], field_id="cloud-crawl", model_mode="qwen_35b")
        self.assertEqual(len(engine.build_cloud_local_tab("cloud-crawl", "queued_works", model_mode="qwen_35b")["items"]), 1)

    def test_cloud_queue_counts_match_tab_filters_after_add_all(self) -> None:
        tmpdir, store = self.make_store()
        self.addCleanup(tmpdir.cleanup)
        engine = PrincipiaEngine(store=store)
        engine.create_project(name="Cloud Crawl", field_id="cloud-crawl", query="cloud")
        queued = engine.queue_cloud_candidates(
            [
                {"title": "Queue Paper One", "abstract": "First queued paper.", "venue_or_source": "ICLR", "year": 2026},
                {"title": "Queue Paper Two", "abstract": "Second queued paper.", "venue_or_source": "ICML", "year": 2026},
            ],
            field_id="cloud-crawl",
            model_mode="all",
        )
        self.assertEqual(len(queued["work_ids"]), 2)

        added = engine.add_all_cloud_research_tasks(field_id="cloud-crawl", model_mode="qwen_397b")
        self.assertEqual(len(added["added_work_ids"]), 2)
        counts = engine.cloud_local_counts("cloud-crawl", model_mode="qwen_397b")
        tasks = engine.build_cloud_local_tab("cloud-crawl", "research_tasks", model_mode="qwen_397b", include_counts=False)
        queued_tab = engine.build_cloud_local_tab("cloud-crawl", "queued_works", model_mode="qwen_397b", include_counts=False)
        self.assertEqual(counts["research_tasks"]["unsynced"], tasks["total"])
        self.assertEqual(counts["queued_works"]["unsynced"], queued_tab["total"])

    def test_cloud_ready_all_infers_model_from_extracted_records_and_ignores_stale_sync(self) -> None:
        tmpdir, store = self.make_store()
        self.addCleanup(tmpdir.cleanup)
        engine = PrincipiaEngine(store=store)
        engine.create_project(name="Cloud Crawl", field_id="cloud-crawl", query="cloud")
        store.upsert("source_works", {"work_id": "W_STALE_SYNC", "title": "Stale Sync Paper", "cloud_sync_status": "unsynced"}, "work_id")
        engine.add_project_memberships("cloud-crawl", "source_works", ["W_STALE_SYNC"], source="test")
        principle = engine._v2_upsert_canonical(
            "principles",
            "Stale sync principle",
            {"name": "Stale sync principle", "argument": "A newer extraction should be uploadable.", "source_works": ["W_STALE_SYNC"]},
            model_mode="qwen_397b",
        )
        store.upsert(
            "evidence_links",
            engine._v2_evidence_link("cloud-crawl", "principles", principle["principle_id"], "W_STALE_SYNC", "evidence"),
            "link_id",
        )
        engine.add_project_memberships("cloud-crawl", "principles", [principle["principle_id"]], source="test")
        model_key = engine._cloud_model_key("qwen_397b")
        work = store.get_item("source_works", "W_STALE_SYNC")
        work["cloud_sync_by_model"] = {
            model_key: {
                "status": "synced",
                "model_mode": "qwen_397b",
                "model_key": model_key,
                "synced_at": "2026-01-01T00:00:00+00:00",
            }
        }
        work["cloud_research_by_model"] = {
            model_key: {
                "state": "ready",
                "model_mode": "qwen_397b",
                "model_key": model_key,
                "updated_at": "2026-01-02T00:00:00+00:00",
            }
        }
        store.upsert("source_works", work, "work_id")

        self.assertFalse(engine._cloud_work_synced_for_mode(store.get_item("source_works", "W_STALE_SYNC"), "qwen_397b"))
        ready_all = engine.build_cloud_local_tab("cloud-crawl", "ready_works", model_mode="all", include_counts=False)
        counts_all = engine.cloud_local_counts("cloud-crawl", model_mode="all")
        self.assertEqual(ready_all["total"], 1)
        self.assertEqual(ready_all["items"][0]["ready_model_mode"], "qwen_397b")
        self.assertEqual(counts_all["ready_works"]["unsynced"], ready_all["total"])
        self.assertEqual(counts_all["principles"]["unsynced"], 1)

    def test_equivalent_work_aliases_share_current_llm_extractions(self) -> None:
        tmpdir, store = self.make_store()
        self.addCleanup(tmpdir.cleanup)
        engine = PrincipiaEngine(store=store)
        store.upsert("source_works", {"work_id": "W_CLOUD", "title": "Shared Paper", "arxiv_id": "2412.11427"}, "work_id")
        store.upsert("source_works", {"work_id": "W_LOCAL", "title": "Shared Paper", "url_or_doi": "https://arxiv.org/abs/2412.11427v2"}, "work_id")
        principle = engine._v2_upsert_canonical(
            "principles",
            "Alias principle",
            {"name": "Alias principle", "argument": "A shared paper should expose the same reusable principle through every local alias.", "source_works": ["W_LOCAL"]},
            model_mode="qwen_397b",
        )
        benchmark = engine._v2_upsert_canonical(
            "benchmark_records",
            "AliasBench",
            {"benchmark_name": "AliasBench", "task": "Alias consistency", "source_work_ids": ["W_CLOUD"]},
            model_mode="qwen_397b",
        )
        store.upsert("evidence_links", engine._v2_evidence_link("project-a", "principles", principle["principle_id"], "W_LOCAL", "evidence"), "link_id")
        store.upsert("evidence_links", engine._v2_evidence_link("project-b", "benchmark_records", benchmark["benchmark_id"], "W_CLOUD", "evidence"), "link_id")

        for work_id in ("W_CLOUD", "W_LOCAL"):
            counts = engine.v2_work_extraction_counts(work_id, model_mode="qwen_397b")
            self.assertEqual(counts["principles"], 1)
            self.assertEqual(counts["benchmark_records"], 1)
            groups = engine._v2_work_extraction_groups(work_id, model_mode="qwen_397b")
            self.assertEqual(groups["total"], 2)

    def test_explicit_work_id_is_preserved_for_selected_cloud_research_tasks(self) -> None:
        tmpdir, store = self.make_store()
        self.addCleanup(tmpdir.cleanup)
        engine = PrincipiaEngine(store=store)
        first = engine._v2_upsert_work(
            {
                "work_id": "W_FIRST_ALIAS",
                "title": "Stable Queue Identity",
                "abstract": "The first queued alias.",
            },
            model_mode="metadata",
        )
        second = engine._v2_upsert_work(
            {
                "work_id": "W_SELECTED_TASK",
                "title": "Stable Queue Identity",
                "abstract": "The selected research task must keep its own local ID.",
                "preserve_work_id": True,
            },
            model_mode="metadata",
        )

        self.assertEqual(first["work_id"], "W_FIRST_ALIAS")
        self.assertEqual(second["work_id"], "W_SELECTED_TASK")
        self.assertIsNotNone(store.get_item("source_works", "W_FIRST_ALIAS"))
        self.assertIsNotNone(store.get_item("source_works", "W_SELECTED_TASK"))

    def test_pdf_hyphenation_is_repaired_before_extraction_text_use(self) -> None:
        tmpdir, store = self.make_store()
        self.addCleanup(tmpdir.cleanup)
        self.assertEqual(research_sources._clean_text("scien- tific tools support multi-agent work"), "scientific tools support multi-agent work")
        engine = PrincipiaEngine(store=store)
        self.assertEqual(engine._normalize_pdf_text("scien- tific tools"), "scientific tools")

    def test_missing_abstract_recovery_uses_landing_page_metadata(self) -> None:
        original = research_sources._fetch_landing_page_abstract

        def fake_fetch(url: str, *, timeout: int, max_chars: int) -> str:
            _ = (timeout, max_chars)
            self.assertIn("10.1007/example", url)
            return "Modern AI systems achieve remarkable performance through stochastic learning processes. " * 3

        research_sources._fetch_landing_page_abstract = fake_fetch
        try:
            recovered = research_sources.recover_missing_abstract(
                {
                    "title": "The stochastic nature of machine learning and its implications for high-consequence AI",
                    "abstract": "",
                    "url_or_doi": "https://doi.org/10.1007/example",
                    "source_urls": [],
                    "community_signals": {"source": "crossref"},
                }
            )
        finally:
            research_sources._fetch_landing_page_abstract = original

        self.assertIn("stochastic learning processes", recovered["abstract"])
        self.assertEqual(recovered["community_signals"]["abstract_recovered_from"], "https://doi.org/10.1007/example")

    def test_cloud_sync_recovers_missing_work_abstract_before_global_write(self) -> None:
        tmpdir, store = self.make_store()
        self.addCleanup(tmpdir.cleanup)
        engine = PrincipiaEngine(store=store)
        engine.create_project(name="Cloud Crawl", field_id="cloud-crawl", query="cloud")
        store.upsert(
            "source_works",
            {
                "work_id": "W_MISSING_ABSTRACT",
                "title": "Missing abstract cloud sync paper",
                "abstract": "",
                "year": 2026,
                "venue_or_source": "Nature",
                "url_or_doi": "https://doi.org/10.1007/example",
                "source_urls": ["https://doi.org/10.1007/example"],
                "cloud_sync_status": "unsynced",
            },
            "work_id",
        )
        engine.add_project_memberships("cloud-crawl", "source_works", ["W_MISSING_ABSTRACT"], source="test")
        original = research_sources._fetch_landing_page_abstract

        def fake_fetch(url: str, *, timeout: int, max_chars: int) -> str:
            _ = (timeout, max_chars)
            self.assertIn("10.1007/example", url)
            return "Recovered abstract metadata that should be written to cloud work versions."

        research_sources._fetch_landing_page_abstract = fake_fetch
        try:
            result = engine.sync_cloud_legacy_records_for_upload(
                ["W_MISSING_ABSTRACT"],
                field_id="cloud-crawl",
                model_mode="qwen_397b",
            )
        finally:
            research_sources._fetch_landing_page_abstract = original

        self.assertEqual(len(result["work_ids"]), 1)
        with sqlite3.connect(store.path) as conn:
            abstract = conn.execute(
                "SELECT abstract FROM work_version WHERE work_id = ? ORDER BY created_at DESC LIMIT 1",
                (result["work_ids"][0],),
            ).fetchone()[0]
        self.assertIn("Recovered abstract metadata", abstract)

    def test_published_contribution_is_searchable_from_cloud_manifest(self) -> None:
        tmpdir, store = self.make_store()
        self.addCleanup(tmpdir.cleanup)
        current_model_key = self._seed_store(store)
        contribution_dir = Path(tmpdir.name) / "contributions"
        prepared = prepare_contribution(store.path, contribution_dir, model_key=current_model_key, upload_mode="normal")
        self.assertTrue(prepared["ok"], prepared)

        publish = publish_cloud_contribution(
            prepared["path"],
            Path(tmpdir.name),
            direct_push={"ok": True, "pushed": True, "branch": "main"},
            branch="main",
            trigger_workflow=False,
            local_snapshot=True,
        )
        self.assertTrue(publish["ok"], publish)
        self.assertTrue(publish["available_for_search"], publish)
        pointer = Path(publish["local_snapshot"]["pointer_path"])
        fresh_tmp, fresh_store = self.make_store()
        self.addCleanup(fresh_tmp.cleanup)
        search = CloudSearch(CloudResolver(fresh_store, manifest_client=CloudManifestClient(pointer)))
        result = search.search("Cloud cache paper", model_key=current_model_key, limit=10)
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["title"], "Cloud cache paper")

    def test_local_snapshot_publish_keeps_existing_local_contributions(self) -> None:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        repo_root = Path(tmpdir.name) / "repo"
        artifact_dir = repo_root / "data" / "artifacts" / "cloud" / "contributions"
        artifact_dir.mkdir(parents=True)

        first_store = Store(Path(tmpdir.name) / "first.sqlite")
        first_model_key = self._seed_store(first_store)
        first = prepare_contribution(first_store.path, artifact_dir, model_key=first_model_key, upload_mode="normal")
        self.assertTrue(first["ok"], first)

        second_store = Store(Path(tmpdir.name) / "second.sqlite")
        second_model_key = self._seed_store_with_work(
            second_store,
            title="Second cumulative cloud paper",
            abstract="A second reusable extraction target.",
        )
        second_dir = Path(tmpdir.name) / "new-contribution"
        second = prepare_contribution(second_store.path, second_dir, model_key=second_model_key, upload_mode="normal")
        self.assertTrue(second["ok"], second)

        publish = publish_cloud_contribution(
            second["path"],
            repo_root,
            direct_push={"ok": True, "pushed": True, "branch": "codex/cloud-contribution-test"},
            branch="codex/cloud-contribution-test",
            trigger_workflow=False,
            local_snapshot=True,
        )
        self.assertTrue(publish["ok"], publish)
        self.assertEqual(publish["local_snapshot"]["counts"]["works"], 2)
        pointer = Path(publish["local_snapshot"]["pointer_path"])
        fresh_tmp, fresh_store = self.make_store()
        self.addCleanup(fresh_tmp.cleanup)
        search = CloudSearch(CloudResolver(fresh_store, manifest_client=CloudManifestClient(pointer)))
        self.assertEqual(search.search("Cloud cache paper", model_key=first_model_key, limit=10)["items"][0]["title"], "Cloud cache paper")
        self.assertEqual(search.search("Second cumulative cloud paper", model_key=second_model_key, limit=10)["items"][0]["title"], "Second cumulative cloud paper")

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
        return self._seed_store_with_work(store, title="Cloud cache paper", abstract="A reusable extraction target.")

    def _seed_store_with_work(
        self,
        store: Store,
        *,
        title: str,
        abstract: str,
        venue: str = "ICLR",
        year: int = 2026,
        doi: str = "",
    ) -> str:
        global_store = GlobalStore(store.path)
        work = global_store.upsert_work(
            {
                "title": title,
                "abstract": abstract,
                "authors": ["A. Researcher"],
                "doi": doi,
                "year": year,
                "venue_or_source": venue,
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
                    "evidence_span": abstract,
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
                    "evidence_span": abstract,
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
                    "evidence_span": abstract,
                    "evidence_type": "abstract",
                    "confidence": 0.9,
                }
            ],
        )
        store.upsert("source_works", {"work_id": work["work_id"], "title": title, "abstract": abstract}, "work_id")
        store.upsert("existed_ideas", {"canonical_id": idea["concept_id"], "title": "Cache reuse idea", "idea_text": "Cloud cache reuse avoids repeated extraction when paper identity and model coverage are unchanged.", "source_works": [work["work_id"]]}, "canonical_id")
        store.upsert("principles", {"principle_id": concept["concept_id"], "name": "Cache reuse principle", "source_works": [work["work_id"]]}, "principle_id")
        store.upsert("takeaway_messages", {"canonical_id": takeaway["concept_id"], "title": "Reuse cached extraction", "message_text": "If source identity and model coverage are unchanged, reuse cached paper extraction before calling the LLM again.", "source_works": [work["work_id"]]}, "canonical_id")
        return current_model_key


if __name__ == "__main__":
    unittest.main()
