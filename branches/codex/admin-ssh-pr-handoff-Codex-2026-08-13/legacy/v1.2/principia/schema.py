from __future__ import annotations

import sqlite3
from pathlib import Path


V1_SCHEMA_VERSION = "principia-v1.0"
V11_CLOUD_SCHEMA_VERSION = "principia-cloud-1.1"


def ensure_artifact_dirs(root: Path) -> None:
    for name in (
        "sources",
        "pdfs",
        "prompt_packs",
        "run_logs",
        "exports",
        "cache/embeddings",
        "cache/source_json",
        "cloud/manifests",
        "cloud/indexes",
        "cloud/packs",
        "cloud/contributions",
        "cloud/releases",
        "cloud/tmp",
        "cloud/assets",
    ):
        (root / "data" / "artifacts" / name).mkdir(parents=True, exist_ok=True)


def ensure_v1_schema(conn: sqlite3.Connection) -> None:
    """Create the normalized local-first Principia v1 tables.

    The legacy `records` table remains the compatibility API. These tables are
    the durable global memory layer used by v1 services.
    """

    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS global_work (
            work_id TEXT PRIMARY KEY,
            canonical_title TEXT NOT NULL,
            title_norm TEXT NOT NULL,
            title_hash TEXT NOT NULL,
            doi TEXT,
            arxiv_id TEXT,
            openalex_id TEXT,
            crossref_id TEXT,
            semantic_scholar_id TEXT,
            year INTEGER,
            venue_or_source TEXT,
            source_type TEXT,
            source_urls_json TEXT,
            identity_confidence REAL DEFAULT 1.0,
            identity_status TEXT DEFAULT 'resolved',
            metadata_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_v1_work_doi ON global_work(doi) WHERE doi IS NOT NULL AND doi != ''")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_v1_work_arxiv ON global_work(arxiv_id) WHERE arxiv_id IS NOT NULL AND arxiv_id != ''")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_v1_work_title_hash ON global_work(title_hash)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS work_version (
            work_version_id TEXT PRIMARY KEY,
            work_id TEXT NOT NULL,
            source_provider TEXT,
            source_record_id TEXT,
            title TEXT,
            abstract TEXT,
            title_hash TEXT,
            abstract_hash TEXT,
            content_hash TEXT,
            source_modified_at TEXT,
            source_updated_at TEXT,
            metadata_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY(work_id) REFERENCES global_work(work_id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_v1_work_version_work ON work_version(work_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_v1_work_version_hash ON work_version(work_id, title_hash, abstract_hash, content_hash)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS extraction_run (
            extraction_run_id TEXT PRIMARY KEY,
            work_id TEXT NOT NULL,
            work_version_id TEXT NOT NULL,
            llm_provider TEXT,
            llm_model TEXT,
            model_mode TEXT,
            prompt_version TEXT,
            schema_version TEXT,
            extraction_task_type TEXT,
            extraction_status TEXT,
            input_token_estimate INTEGER DEFAULT 0,
            output_token_estimate INTEGER DEFAULT 0,
            cost_estimate REAL DEFAULT 0,
            error_message TEXT DEFAULT '',
            result_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            completed_at TEXT,
            FOREIGN KEY(work_id) REFERENCES global_work(work_id),
            FOREIGN KEY(work_version_id) REFERENCES work_version(work_version_id)
        )
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_v1_extraction_cache
        ON extraction_run(work_version_id, llm_provider, llm_model, prompt_version, schema_version, extraction_task_type)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS concept_card (
            concept_id TEXT PRIMARY KEY,
            concept_type TEXT NOT NULL,
            canonical_key TEXT NOT NULL,
            canonical_label TEXT,
            source_origin TEXT NOT NULL,
            validation_level TEXT,
            verification_status TEXT,
            confidence_score REAL DEFAULT 0.5,
            public_scope TEXT DEFAULT 'project_private',
            active_version_id TEXT DEFAULT '',
            created_by_user_id TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(concept_type, canonical_key, public_scope)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_v1_concept_type ON concept_card(concept_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_v1_concept_validation ON concept_card(validation_level)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_v1_concept_scope ON concept_card(public_scope)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS concept_version (
            concept_version_id TEXT PRIMARY KEY,
            concept_id TEXT NOT NULL,
            extraction_run_id TEXT,
            llm_provider TEXT,
            llm_model TEXT,
            model_mode TEXT,
            prompt_version TEXT,
            schema_version TEXT,
            payload_json TEXT NOT NULL,
            summary_text TEXT,
            text_hash TEXT,
            quality_score REAL DEFAULT 0.5,
            is_active INTEGER DEFAULT 1,
            is_manual_edit INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY(concept_id) REFERENCES concept_card(concept_id),
            FOREIGN KEY(extraction_run_id) REFERENCES extraction_run(extraction_run_id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_v1_concept_version_concept ON concept_version(concept_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_v1_concept_version_active ON concept_version(concept_id, is_active)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS evidence_link (
            evidence_id TEXT PRIMARY KEY,
            concept_id TEXT NOT NULL,
            concept_version_id TEXT,
            work_id TEXT,
            work_version_id TEXT,
            evidence_type TEXT,
            evidence_span TEXT,
            source_url TEXT,
            confidence REAL DEFAULT 0.5,
            created_at TEXT NOT NULL,
            FOREIGN KEY(concept_id) REFERENCES concept_card(concept_id),
            FOREIGN KEY(concept_version_id) REFERENCES concept_version(concept_version_id),
            FOREIGN KEY(work_id) REFERENCES global_work(work_id),
            FOREIGN KEY(work_version_id) REFERENCES work_version(work_version_id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_v1_evidence_concept ON evidence_link(concept_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_v1_evidence_work ON evidence_link(work_id)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS symbol_registry (
            symbol_id TEXT PRIMARY KEY,
            concept_id TEXT NOT NULL,
            namespace TEXT NOT NULL,
            short_code TEXT NOT NULL,
            label TEXT NOT NULL,
            gloss TEXT,
            symbol_source TEXT,
            llm_provider TEXT,
            llm_model TEXT,
            status TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(namespace, short_code),
            FOREIGN KEY(concept_id) REFERENCES concept_card(concept_id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_v1_symbol_concept ON symbol_registry(concept_id)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS derivation_run (
            derivation_id TEXT PRIMARY KEY,
            project_id TEXT,
            query TEXT,
            generation_mode TEXT,
            llm_provider TEXT,
            llm_model TEXT,
            prompt_version TEXT,
            status TEXT,
            warnings_json TEXT DEFAULT '[]',
            created_at TEXT NOT NULL,
            completed_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS derivation_node (
            node_id TEXT PRIMARY KEY,
            derivation_id TEXT NOT NULL,
            concept_id TEXT,
            node_type TEXT,
            symbol_code TEXT,
            expression TEXT,
            natural_language_summary TEXT,
            validation_status TEXT,
            speculation_depth INTEGER DEFAULT 0,
            confidence REAL DEFAULT 0.5,
            verifier_status TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(derivation_id) REFERENCES derivation_run(derivation_id),
            FOREIGN KEY(concept_id) REFERENCES concept_card(concept_id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_v1_derivation_node_run ON derivation_node(derivation_id)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS derivation_edge (
            edge_id TEXT PRIMARY KEY,
            derivation_id TEXT NOT NULL,
            source_node_id TEXT NOT NULL,
            target_node_id TEXT NOT NULL,
            relation_type TEXT,
            rationale TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(derivation_id) REFERENCES derivation_run(derivation_id),
            FOREIGN KEY(source_node_id) REFERENCES derivation_node(node_id),
            FOREIGN KEY(target_node_id) REFERENCES derivation_node(node_id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_v1_derivation_edge_run ON derivation_edge(derivation_id)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS project_record_membership (
            membership_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            record_type TEXT NOT NULL,
            record_id TEXT NOT NULL,
            source TEXT,
            display_order INTEGER DEFAULT 0,
            hidden INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(project_id, record_type, record_id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_v1_project_membership_project ON project_record_membership(project_id, record_type, display_order)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS run_event (
            event_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            message TEXT,
            payload_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_v1_run_event_run ON run_event(run_id, created_at)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS embedding_index (
            embedding_id TEXT PRIMARY KEY,
            owner_type TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            view_name TEXT NOT NULL,
            embedding_model TEXT NOT NULL,
            dims INTEGER DEFAULT 0,
            vector_json TEXT DEFAULT '[]',
            created_at TEXT NOT NULL,
            UNIQUE(owner_type, owner_id, view_name, embedding_model)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS migration_status (
            migration_id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            status TEXT NOT NULL,
            detail_json TEXT DEFAULT '{}',
            started_at TEXT NOT NULL,
            completed_at TEXT
        )
        """
    )
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('v1_schema_version', ?)", (V1_SCHEMA_VERSION,))
    ensure_cloud_schema(conn)
    _ensure_fts(conn)


def ensure_cloud_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cloud_manifest_cache (
            snapshot_id TEXT PRIMARY KEY,
            manifest_json TEXT NOT NULL,
            manifest_url TEXT,
            manifest_sha256 TEXT,
            fetched_at TEXT NOT NULL,
            active INTEGER DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cloud_asset_cache (
            asset_id TEXT PRIMARY KEY,
            snapshot_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            record_type TEXT,
            url TEXT NOT NULL,
            local_path TEXT,
            sha256 TEXT,
            bytes INTEGER,
            fetched_at TEXT,
            cache_status TEXT DEFAULT 'missing'
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cloud_asset_snapshot ON cloud_asset_cache(snapshot_id, kind, record_type)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cloud_route_shard_cache (
            shard_id TEXT PRIMARY KEY,
            snapshot_id TEXT NOT NULL,
            route_type TEXT NOT NULL,
            local_path TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            fetched_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cloud_route_snapshot ON cloud_route_shard_cache(snapshot_id, route_type)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cloud_resolution_cache (
            cache_key TEXT PRIMARY KEY,
            snapshot_id TEXT NOT NULL,
            work_id TEXT,
            resolution_json TEXT NOT NULL,
            model_key TEXT,
            source_state_hash TEXT,
            decision TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cloud_resolution_work ON cloud_resolution_cache(work_id, model_key, snapshot_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cloud_resolution_decision ON cloud_resolution_cache(decision, created_at)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cloud_payload_cache (
            record_id TEXT PRIMARY KEY,
            snapshot_id TEXT NOT NULL,
            record_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            payload_sha256 TEXT NOT NULL,
            fetched_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cloud_payload_snapshot ON cloud_payload_cache(snapshot_id, record_type)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cloud_upload_log (
            upload_id TEXT PRIMARY KEY,
            work_id TEXT,
            model_key TEXT,
            contribution_path TEXT,
            github_pr_url TEXT,
            upload_mode TEXT,
            status TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cloud_upload_status ON cloud_upload_log(status, created_at)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cloud_relation (
            relation_id TEXT PRIMARY KEY,
            subject_id TEXT NOT NULL,
            predicate TEXT NOT NULL,
            object_id TEXT NOT NULL,
            evidence_ids_json TEXT DEFAULT '[]',
            confidence REAL DEFAULT 0.5,
            source TEXT,
            model_key TEXT,
            snapshot_id TEXT,
            payload_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cloud_relation_subject ON cloud_relation(subject_id, predicate)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cloud_relation_object ON cloud_relation(object_id, predicate)")
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('cloud_schema_version', ?)", (V11_CLOUD_SCHEMA_VERSION,))


def _ensure_fts(conn: sqlite3.Connection) -> None:
    try:
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS work_fts
            USING fts5(work_id UNINDEXED, title, abstract, metadata)
            """
        )
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS concept_fts
            USING fts5(concept_id UNINDEXED, concept_type UNINDEXED, label, summary, payload)
            """
        )
        conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('v1_fts_enabled', '1')")
    except sqlite3.OperationalError:
        conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('v1_fts_enabled', '0')")
