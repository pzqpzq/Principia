from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .._sqlite import connect_sqlite
from ..domain.hashing import canonical_sha256, file_sha256

LEGACY_IMPORT_MIGRATION = "1.4.0-001"
ADMIN_MIGRATION_VERSION = "1.4.0-002"
LITERATURE_MIGRATION_VERSION = "1.4.0-003"
HUMAN_CENTERED_MIGRATION_VERSION = "1.4.0-004"
MIGRATION_VERSION = "1.4.0-005"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS local_candidates (
    candidate_id TEXT PRIMARY KEY,
    area TEXT NOT NULL,
    title TEXT NOT NULL,
    claim TEXT NOT NULL,
    assessment_status TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    content_digest TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS local_principles (
    principle_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    area TEXT NOT NULL,
    status TEXT NOT NULL,
    title TEXT NOT NULL,
    claim TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    content_digest TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(principle_id, version)
);
CREATE INDEX IF NOT EXISTS idx_local_principles_area ON local_principles(area, status);
CREATE TABLE IF NOT EXISTS local_relations (
    source_principle_id TEXT NOT NULL,
    source_version INTEGER NOT NULL,
    relation_index INTEGER NOT NULL,
    target_principle_id TEXT NOT NULL,
    target_area TEXT,
    minimum_package_version TEXT,
    relation_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY(source_principle_id, source_version, relation_index),
    FOREIGN KEY(source_principle_id, source_version)
        REFERENCES local_principles(principle_id, version)
);
CREATE TABLE IF NOT EXISTS local_generation_trace (
    principle_id TEXT NOT NULL,
    principle_version INTEGER NOT NULL,
    trace_index INTEGER NOT NULL,
    event_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY(principle_id, principle_version, trace_index),
    FOREIGN KEY(principle_id, principle_version)
        REFERENCES local_principles(principle_id, version)
);
CREATE TABLE IF NOT EXISTS v14_events (
    event_id TEXT PRIMARY KEY,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    input_digest TEXT NOT NULL,
    output_digest TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS v14_jobs (
    job_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    state TEXT NOT NULL,
    stage TEXT NOT NULL,
    progress REAL NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_v14_jobs_state ON v14_jobs(state, updated_at);
CREATE TABLE IF NOT EXISTS scenarios (
    scenario_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    base_content_digest TEXT NOT NULL,
    parent_scenario_id TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(parent_scenario_id) REFERENCES scenarios(scenario_id)
);
CREATE TABLE IF NOT EXISTS scenario_events (
    event_id TEXT PRIMARY KEY,
    scenario_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(scenario_id, sequence),
    FOREIGN KEY(scenario_id) REFERENCES scenarios(scenario_id)
);
CREATE TABLE IF NOT EXISTS local_sources_v14 (
    source_id TEXT PRIMARY KEY,
    portable_uri TEXT NOT NULL UNIQUE,
    absolute_root TEXT NOT NULL,
    display_name TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS local_principle_fts USING fts5(
    principle_id UNINDEXED,
    version UNINDEXED,
    title,
    claim,
    area,
    tags,
    tokenize='unicode61 remove_diacritics 2'
);
"""

_ADMIN_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS admin_review_queue (
    candidate_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    decision_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_admin_review_status ON admin_review_queue(status, updated_at);
CREATE TABLE IF NOT EXISTS publication_changesets (
    changeset_id TEXT PRIMARY KEY,
    area TEXT NOT NULL,
    status TEXT NOT NULL,
    expected_content_digest TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

_LITERATURE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS scholarly_retrieval_runs (
    search_id TEXT PRIMARY KEY,
    goal TEXT NOT NULL,
    area TEXT NOT NULL,
    target_count INTEGER NOT NULL,
    state TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scholarly_runs_updated
    ON scholarly_retrieval_runs(updated_at DESC, search_id);
CREATE TABLE IF NOT EXISTS scholarly_provider_observations (
    observation_id TEXT PRIMARY KEY,
    search_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    status TEXT NOT NULL,
    result_count INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(search_id) REFERENCES scholarly_retrieval_runs(search_id)
);
CREATE INDEX IF NOT EXISTS idx_scholarly_observations_search
    ON scholarly_provider_observations(search_id, created_at, observation_id);
CREATE TABLE IF NOT EXISTS research_datasets (
    dataset_id TEXT PRIMARY KEY,
    search_id TEXT NOT NULL,
    goal TEXT NOT NULL,
    area TEXT NOT NULL,
    state TEXT NOT NULL,
    storage_root TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(search_id) REFERENCES scholarly_retrieval_runs(search_id)
);
CREATE INDEX IF NOT EXISTS idx_research_datasets_updated
    ON research_datasets(updated_at DESC, dataset_id);
CREATE TABLE IF NOT EXISTS dataset_works (
    dataset_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    work_id TEXT NOT NULL,
    selected INTEGER NOT NULL,
    acquisition_status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY(dataset_id, work_id),
    UNIQUE(dataset_id, ordinal),
    FOREIGN KEY(dataset_id) REFERENCES research_datasets(dataset_id),
    FOREIGN KEY(work_id) REFERENCES works(id)
);
CREATE INDEX IF NOT EXISTS idx_dataset_works_status
    ON dataset_works(dataset_id, acquisition_status, ordinal);
CREATE TABLE IF NOT EXISTS scholarly_locations (
    location_id TEXT PRIMARY KEY,
    work_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    url TEXT NOT NULL,
    access_basis TEXT NOT NULL,
    manuscript_version TEXT NOT NULL,
    license TEXT NOT NULL,
    is_open_access INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(work_id) REFERENCES works(id)
);
CREATE INDEX IF NOT EXISTS idx_scholarly_locations_work
    ON scholarly_locations(work_id, is_open_access DESC, location_id);
CREATE TABLE IF NOT EXISTS scholarly_acquisitions (
    acquisition_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL,
    work_id TEXT NOT NULL,
    location_id TEXT,
    status TEXT NOT NULL,
    content_kind TEXT NOT NULL,
    final_url TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    byte_sha256 TEXT NOT NULL,
    text_sha256 TEXT NOT NULL,
    byte_size INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(dataset_id, work_id),
    FOREIGN KEY(dataset_id) REFERENCES research_datasets(dataset_id),
    FOREIGN KEY(work_id) REFERENCES works(id),
    FOREIGN KEY(location_id) REFERENCES scholarly_locations(location_id)
);
CREATE TABLE IF NOT EXISTS scholarly_segments (
    segment_id TEXT PRIMARY KEY,
    acquisition_id TEXT NOT NULL,
    segment_key TEXT NOT NULL UNIQUE,
    work_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    section TEXT NOT NULL,
    page_start INTEGER,
    page_end INTEGER,
    text TEXT NOT NULL,
    text_sha256 TEXT NOT NULL,
    character_count INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(acquisition_id) REFERENCES scholarly_acquisitions(acquisition_id),
    FOREIGN KEY(work_id) REFERENCES works(id)
);
CREATE INDEX IF NOT EXISTS idx_scholarly_segments_work
    ON scholarly_segments(work_id, ordinal);
CREATE TABLE IF NOT EXISTS v14_job_units (
    unit_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    work_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    state TEXT NOT NULL,
    attempt_count INTEGER NOT NULL,
    checkpoint_json TEXT NOT NULL,
    result_json TEXT,
    error_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(job_id, work_id),
    UNIQUE(job_id, ordinal),
    FOREIGN KEY(job_id) REFERENCES v14_jobs(job_id),
    FOREIGN KEY(work_id) REFERENCES works(id)
);
CREATE INDEX IF NOT EXISTS idx_v14_job_units_state
    ON v14_job_units(job_id, state, ordinal);
CREATE TABLE IF NOT EXISTS v14_job_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    job_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES v14_jobs(job_id)
);
CREATE INDEX IF NOT EXISTS idx_v14_job_events_job
    ON v14_job_events(job_id, sequence);
CREATE TABLE IF NOT EXISTS provider_attempts (
    attempt_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    unit_id TEXT,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_template TEXT NOT NULL,
    prompt_sha256 TEXT NOT NULL,
    input_sha256 TEXT NOT NULL,
    output_sha256 TEXT NOT NULL,
    state TEXT NOT NULL,
    retry_index INTEGER NOT NULL,
    latency_ms INTEGER NOT NULL,
    error_category TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES v14_jobs(job_id),
    FOREIGN KEY(unit_id) REFERENCES v14_job_units(unit_id)
);
CREATE INDEX IF NOT EXISTS idx_provider_attempts_job
    ON provider_attempts(job_id, created_at, attempt_id);
CREATE TABLE IF NOT EXISTS provider_usage (
    job_id TEXT PRIMARY KEY,
    http_attempts INTEGER NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    pro_calls INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES v14_jobs(job_id)
);
CREATE TABLE IF NOT EXISTS candidate_work_evidence (
    evidence_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    work_id TEXT NOT NULL,
    acquisition_id TEXT,
    segment_id TEXT,
    role TEXT NOT NULL,
    locator_json TEXT NOT NULL,
    excerpt_sha256 TEXT NOT NULL,
    extraction_trace_json TEXT NOT NULL,
    visibility TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(candidate_id, work_id, segment_id, excerpt_sha256),
    FOREIGN KEY(candidate_id) REFERENCES local_candidates(candidate_id),
    FOREIGN KEY(work_id) REFERENCES works(id),
    FOREIGN KEY(acquisition_id) REFERENCES scholarly_acquisitions(acquisition_id),
    FOREIGN KEY(segment_id) REFERENCES scholarly_segments(segment_id)
);
CREATE INDEX IF NOT EXISTS idx_candidate_evidence_candidate
    ON candidate_work_evidence(candidate_id, work_id, evidence_id);
CREATE INDEX IF NOT EXISTS idx_candidate_evidence_work
    ON candidate_work_evidence(work_id, candidate_id, evidence_id);
CREATE TABLE IF NOT EXISTS candidate_clusters (
    cluster_id TEXT PRIMARY KEY,
    canonical_candidate_id TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    decision TEXT NOT NULL,
    decision_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(canonical_candidate_id) REFERENCES local_candidates(candidate_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_candidate_clusters_fingerprint
    ON candidate_clusters(fingerprint);
CREATE TABLE IF NOT EXISTS candidate_aliases (
    alias_candidate_id TEXT PRIMARY KEY,
    cluster_id TEXT NOT NULL,
    canonical_candidate_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(cluster_id) REFERENCES candidate_clusters(cluster_id),
    FOREIGN KEY(canonical_candidate_id) REFERENCES local_candidates(candidate_id)
);
CREATE TABLE IF NOT EXISTS local_candidate_relations (
    source_candidate_id TEXT NOT NULL,
    relation_index INTEGER NOT NULL,
    target_principle_id TEXT NOT NULL,
    target_area TEXT,
    minimum_package_version TEXT,
    relation_type TEXT NOT NULL,
    provenance TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY(source_candidate_id, relation_index),
    FOREIGN KEY(source_candidate_id) REFERENCES local_candidates(candidate_id)
);
CREATE INDEX IF NOT EXISTS idx_candidate_relations_target
    ON local_candidate_relations(target_principle_id, source_candidate_id);
"""

_HUMAN_CENTERED_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS local_research_goals (
    goal_id TEXT PRIMARY KEY,
    search_id TEXT UNIQUE,
    goal TEXT NOT NULL,
    area TEXT NOT NULL,
    source_id TEXT,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(search_id) REFERENCES scholarly_retrieval_runs(search_id),
    FOREIGN KEY(source_id) REFERENCES local_sources_v14(source_id)
);
CREATE INDEX IF NOT EXISTS idx_local_research_goals_area
    ON local_research_goals(area, updated_at DESC, goal_id);
CREATE TABLE IF NOT EXISTS local_source_documents (
    document_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    work_id TEXT NOT NULL,
    acquisition_id TEXT,
    portable_relative_uri TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    parse_status TEXT NOT NULL,
    extraction_eligible INTEGER NOT NULL,
    principle_count INTEGER NOT NULL DEFAULT 0,
    last_indexed_revision INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(source_id, work_id),
    UNIQUE(source_id, portable_relative_uri),
    FOREIGN KEY(source_id) REFERENCES local_sources_v14(source_id),
    FOREIGN KEY(work_id) REFERENCES works(id),
    FOREIGN KEY(acquisition_id) REFERENCES scholarly_acquisitions(acquisition_id)
);
CREATE INDEX IF NOT EXISTS idx_local_source_documents_browse
    ON local_source_documents(source_id, extraction_eligible DESC,
                              updated_at DESC, document_id);
CREATE TABLE IF NOT EXISTS local_extraction_selections (
    selection_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL UNIQUE,
    source_id TEXT NOT NULL,
    source_revision INTEGER NOT NULL,
    selection_mode TEXT NOT NULL,
    document_ids_json TEXT NOT NULL,
    selection_digest TEXT NOT NULL,
    goal_id TEXT,
    goal TEXT NOT NULL,
    area TEXT NOT NULL,
    quality_policy TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES v14_jobs(job_id),
    FOREIGN KEY(source_id) REFERENCES local_sources_v14(source_id),
    FOREIGN KEY(goal_id) REFERENCES local_research_goals(goal_id)
);
CREATE INDEX IF NOT EXISTS idx_local_extraction_selections_source
    ON local_extraction_selections(source_id, created_at DESC, selection_id);
CREATE TABLE IF NOT EXISTS evidence_claim_atoms (
    atom_id TEXT PRIMARY KEY,
    candidate_id TEXT,
    work_id TEXT NOT NULL,
    source_document_id TEXT,
    source_key TEXT NOT NULL,
    assertion_type TEXT NOT NULL,
    evidence_type TEXT NOT NULL,
    epistemic_status TEXT NOT NULL,
    faithful_claim TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    content_digest TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(candidate_id) REFERENCES local_candidates(candidate_id),
    FOREIGN KEY(work_id) REFERENCES works(id),
    FOREIGN KEY(source_document_id) REFERENCES local_source_documents(document_id)
);
CREATE INDEX IF NOT EXISTS idx_evidence_claim_atoms_candidate
    ON evidence_claim_atoms(candidate_id, atom_id);
CREATE INDEX IF NOT EXISTS idx_evidence_claim_atoms_work
    ON evidence_claim_atoms(work_id, atom_id);
CREATE TABLE IF NOT EXISTS candidate_atom_links (
    candidate_id TEXT NOT NULL,
    atom_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(candidate_id, atom_id),
    FOREIGN KEY(candidate_id) REFERENCES local_candidates(candidate_id),
    FOREIGN KEY(atom_id) REFERENCES evidence_claim_atoms(atom_id)
);
CREATE TABLE IF NOT EXISTS candidate_argument_revisions (
    candidate_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    scientific_contract_version TEXT NOT NULL,
    generalization_level TEXT NOT NULL,
    claim_class TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    content_digest TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(candidate_id, revision),
    FOREIGN KEY(candidate_id) REFERENCES local_candidates(candidate_id)
);
CREATE TABLE IF NOT EXISTS candidate_clause_support (
    candidate_id TEXT NOT NULL,
    argument_revision INTEGER NOT NULL,
    support_index INTEGER NOT NULL,
    atom_id TEXT NOT NULL,
    segment_id TEXT,
    supported_fields_json TEXT NOT NULL,
    quotation_sha256 TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY(candidate_id, argument_revision, support_index),
    FOREIGN KEY(candidate_id, argument_revision)
        REFERENCES candidate_argument_revisions(candidate_id, revision),
    FOREIGN KEY(atom_id) REFERENCES evidence_claim_atoms(atom_id),
    FOREIGN KEY(segment_id) REFERENCES scholarly_segments(segment_id)
);
CREATE TABLE IF NOT EXISTS candidate_quality_evaluations (
    evaluation_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    argument_revision INTEGER NOT NULL,
    verdict TEXT NOT NULL,
    reason_codes_json TEXT NOT NULL,
    scientific_contract_version TEXT NOT NULL,
    quality_gate_version TEXT NOT NULL,
    evidence_digest TEXT NOT NULL,
    assessor TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(candidate_id, argument_revision)
        REFERENCES candidate_argument_revisions(candidate_id, revision)
);
CREATE INDEX IF NOT EXISTS idx_candidate_quality_latest
    ON candidate_quality_evaluations(candidate_id, created_at DESC, evaluation_id);
CREATE TABLE IF NOT EXISTS candidate_lineage (
    child_candidate_id TEXT NOT NULL,
    parent_candidate_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(child_candidate_id, parent_candidate_id, relation_type),
    FOREIGN KEY(child_candidate_id) REFERENCES local_candidates(candidate_id),
    FOREIGN KEY(parent_candidate_id) REFERENCES local_candidates(candidate_id)
);
CREATE TABLE IF NOT EXISTS candidate_goal_memberships (
    candidate_id TEXT NOT NULL,
    goal_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(candidate_id, goal_id),
    FOREIGN KEY(candidate_id) REFERENCES local_candidates(candidate_id),
    FOREIGN KEY(goal_id) REFERENCES local_research_goals(goal_id)
);
CREATE INDEX IF NOT EXISTS idx_candidate_goal_memberships_goal
    ON candidate_goal_memberships(goal_id, candidate_id);
CREATE TABLE IF NOT EXISTS candidate_source_memberships (
    candidate_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(candidate_id, source_id),
    FOREIGN KEY(candidate_id) REFERENCES local_candidates(candidate_id),
    FOREIGN KEY(source_id) REFERENCES local_sources_v14(source_id)
);
CREATE INDEX IF NOT EXISTS idx_candidate_source_memberships_source
    ON candidate_source_memberships(source_id, candidate_id);
"""

_USABILITY_RECOVERY_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS literature_search_tasks (
    search_id TEXT PRIMARY KEY,
    job_id TEXT UNIQUE,
    query TEXT NOT NULL,
    target_count INTEGER NOT NULL,
    deadline_seconds INTEGER NOT NULL,
    state TEXT NOT NULL,
    checkpoint_json TEXT NOT NULL,
    result_revision INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(search_id) REFERENCES scholarly_retrieval_runs(search_id),
    FOREIGN KEY(job_id) REFERENCES v14_jobs(job_id)
);
CREATE INDEX IF NOT EXISTS idx_literature_search_tasks_state
    ON literature_search_tasks(state, updated_at DESC, search_id);
CREATE TABLE IF NOT EXISTS literature_search_attempts (
    attempt_id TEXT PRIMARY KEY,
    search_id TEXT NOT NULL,
    job_id TEXT,
    provider TEXT NOT NULL,
    query_key TEXT NOT NULL,
    status TEXT NOT NULL,
    result_count INTEGER NOT NULL,
    retry_after_seconds REAL,
    latency_ms INTEGER NOT NULL,
    error_category TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    FOREIGN KEY(search_id) REFERENCES scholarly_retrieval_runs(search_id),
    FOREIGN KEY(job_id) REFERENCES v14_jobs(job_id)
);
CREATE INDEX IF NOT EXISTS idx_literature_search_attempts_search
    ON literature_search_attempts(search_id, started_at, attempt_id);
CREATE TABLE IF NOT EXISTS literature_search_result_revisions (
    search_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    state TEXT NOT NULL,
    provisional_count INTEGER NOT NULL,
    result_digest TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(search_id, revision),
    FOREIGN KEY(search_id) REFERENCES scholarly_retrieval_runs(search_id)
);
CREATE TABLE IF NOT EXISTS workspace_runtime_leases (
    workspace_key TEXT PRIMARY KEY,
    lease_id TEXT NOT NULL,
    process_id INTEGER NOT NULL,
    acquired_at TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS candidate_area_assignments (
    candidate_id TEXT NOT NULL,
    area TEXT NOT NULL,
    revision INTEGER NOT NULL,
    state TEXT NOT NULL,
    provenance TEXT NOT NULL,
    rationale TEXT NOT NULL,
    model_trace_json TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(candidate_id, area, revision),
    FOREIGN KEY(candidate_id) REFERENCES local_candidates(candidate_id)
);
CREATE INDEX IF NOT EXISTS idx_candidate_area_assignments_current
    ON candidate_area_assignments(area, state, candidate_id, revision DESC);
CREATE TABLE IF NOT EXISTS principle_relation_revisions (
    relation_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    source_principle_id TEXT NOT NULL,
    target_principle_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    direction TEXT NOT NULL,
    provenance TEXT NOT NULL,
    validation_state TEXT NOT NULL,
    rationale TEXT NOT NULL,
    source_version INTEGER NOT NULL,
    target_version INTEGER NOT NULL,
    evidence_digest TEXT NOT NULL,
    model_trace_json TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(relation_id, revision)
);
CREATE INDEX IF NOT EXISTS idx_principle_relation_revisions_source
    ON principle_relation_revisions(source_principle_id, validation_state,
                                    relation_type, revision DESC, relation_id);
CREATE INDEX IF NOT EXISTS idx_principle_relation_revisions_target
    ON principle_relation_revisions(target_principle_id, validation_state,
                                    relation_type, revision DESC, relation_id);
CREATE TABLE IF NOT EXISTS relation_metric_revisions (
    metric_revision INTEGER PRIMARY KEY AUTOINCREMENT,
    corpus_digest TEXT NOT NULL,
    state TEXT NOT NULL,
    maximum_neighbor_count INTEGER,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_relation_metric_revisions_digest
    ON relation_metric_revisions(corpus_digest, state);
CREATE TABLE IF NOT EXISTS principle_relation_metrics (
    metric_revision INTEGER NOT NULL,
    principle_id TEXT NOT NULL,
    influence_score REAL,
    reliability_score REAL,
    distinct_neighbor_count INTEGER NOT NULL,
    incoming_support_count INTEGER NOT NULL,
    incoming_contradict_count INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY(metric_revision, principle_id),
    FOREIGN KEY(metric_revision) REFERENCES relation_metric_revisions(metric_revision)
);
CREATE INDEX IF NOT EXISTS idx_principle_relation_metrics_influence
    ON principle_relation_metrics(metric_revision, influence_score DESC, principle_id);
CREATE INDEX IF NOT EXISTS idx_principle_relation_metrics_reliability
    ON principle_relation_metrics(metric_revision, reliability_score DESC, principle_id);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@contextmanager
def migration_lock(db_path: Path) -> Iterator[None]:
    lock_path = db_path.with_suffix(f"{db_path.suffix}.v14-migration.lock")
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RuntimeError(f"workspace migration is already active: {lock_path.name}") from exc
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode())
        os.close(descriptor)
        yield
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def _migration_applied(db_path: Path, version: str = MIGRATION_VERSION) -> bool:
    if not db_path.exists():
        return False
    with connect_sqlite(db_path) as conn:
        present = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        ).fetchone()
        if not present:
            return False
        return (
            conn.execute("SELECT 1 FROM schema_migrations WHERE version=?", (version,)).fetchone()
            is not None
        )


def _backup_database(db_path: Path) -> tuple[Path, str]:
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = backup_dir / f"principia-pre-v1.4.0-{timestamp}.sqlite"
    with connect_sqlite(db_path) as source, connect_sqlite(backup_path) as target:
        source.execute("PRAGMA wal_checkpoint(FULL)")
        source.backup(target)
    with connect_sqlite(f"file:{backup_path}?mode=ro", uri=True) as check:
        result = check.execute("PRAGMA quick_check").fetchone()
        if result is None or result[0] != "ok":
            raise RuntimeError("v1.4 migration backup failed SQLite quick_check")
    os.chmod(backup_path, 0o600)
    return backup_path, file_sha256(backup_path)


def _legacy_candidate_payload(
    row_id: str, raw_payload: str, now: str
) -> tuple[dict[str, Any], str]:
    try:
        legacy = json.loads(raw_payload)
    except (TypeError, json.JSONDecodeError):
        legacy = {"unparsed_payload": raw_payload}
    if not isinstance(legacy, dict):
        legacy = {"payload": legacy}
    candidate_id = f"cand:legacy:{row_id}"
    title = str(legacy.get("title") or f"Imported legacy Idea {row_id}")
    claim = str(legacy.get("thesis") or legacy.get("novelty_claim") or title)
    payload: dict[str, Any] = {
        "candidate_id": candidate_id,
        "area": "legacy-ideas",
        "title": title,
        "claim": claim,
        "kind": "hypothesis",
        "scope": {
            "statement": "Imported from a Principia v1.3.3 Idea; scope requires human review.",
            "conditions": [],
            "exclusions": [],
            "populations": [],
        },
        "falsifier": "",
        "source_references": [],
        "relations": [],
        "generation_trace": [],
        "assessment_status": "unassessed",
        "raw_legacy_payload": legacy,
        "created_at": str(legacy.get("created_at") or now),
        "updated_at": now,
    }
    return payload, canonical_sha256(payload)


def _import_legacy_ideas(conn: sqlite3.Connection, now: str) -> int:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ideas'"
    ).fetchone()
    if not exists:
        return 0
    imported = 0
    for row_id, raw_payload in conn.execute(
        "SELECT id, payload_json FROM ideas ORDER BY id"
    ).fetchall():
        payload, output_digest = _legacy_candidate_payload(str(row_id), str(raw_payload), now)
        candidate_id = str(payload["candidate_id"])
        inserted = conn.execute(
            """
            INSERT OR IGNORE INTO local_candidates(
                candidate_id, area, title, claim, assessment_status, source_kind,
                payload_json, content_digest, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'unassessed', 'legacy_idea', ?, ?, ?, ?)
            """,
            (
                candidate_id,
                payload["area"],
                payload["title"],
                payload["claim"],
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                output_digest,
                payload["created_at"],
                now,
            ),
        ).rowcount
        if not inserted:
            continue
        input_digest = hashlib.sha256(str(raw_payload).encode()).hexdigest()
        event_payload = {
            "legacy_table": "ideas",
            "legacy_id": str(row_id),
            "candidate_id": candidate_id,
            "quality_assessment_created": False,
            "promotion_created": False,
        }
        conn.execute(
            """
            INSERT INTO v14_events(
                event_id, aggregate_type, aggregate_id, operation, input_digest,
                output_digest, payload_json, created_at
            ) VALUES (?, 'candidate', ?, 'legacy_import', ?, ?, ?, ?)
            """,
            (
                f"evt:legacy-import:{row_id}",
                candidate_id,
                input_digest,
                output_digest,
                json.dumps(event_payload, ensure_ascii=False, sort_keys=True),
                now,
            ),
        )
        conn.execute(
            "INSERT INTO local_principle_fts(principle_id, version, title, claim, area, tags) "
            "VALUES (?, 0, ?, ?, ?, '')",
            (candidate_id, payload["title"], payload["claim"], payload["area"]),
        )
        imported += 1
    return imported


def _ensure_local_candidate_columns(conn: sqlite3.Connection) -> None:
    columns = {
        str(row[1]) for row in conn.execute("PRAGMA table_info(local_candidates)").fetchall()
    }
    additions = {
        "discovery_job_id": "TEXT NOT NULL DEFAULT ''",
        "dataset_id": "TEXT NOT NULL DEFAULT ''",
        "eligibility_status": "TEXT NOT NULL DEFAULT 'unassessed'",
        "candidate_fingerprint": "TEXT NOT NULL DEFAULT ''",
        "source_count": "INTEGER NOT NULL DEFAULT 0",
        "relation_count": "INTEGER NOT NULL DEFAULT 0",
        "quarantine_reason": "TEXT NOT NULL DEFAULT ''",
    }
    for name, declaration in additions.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE local_candidates ADD COLUMN {name} {declaration}")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_local_candidates_browse "
        "ON local_candidates(updated_at DESC, candidate_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_local_candidates_discovery "
        "ON local_candidates(discovery_job_id, eligibility_status, updated_at DESC, candidate_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_local_candidates_dataset "
        "ON local_candidates(dataset_id, area, updated_at DESC, candidate_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_local_candidates_fingerprint "
        "ON local_candidates(candidate_fingerprint) WHERE candidate_fingerprint != ''"
    )


def _ensure_human_centered_columns(conn: sqlite3.Connection) -> None:
    table_additions: dict[str, dict[str, str]] = {
        "local_candidates": {
            "goal_id": "TEXT NOT NULL DEFAULT ''",
            "source_id": "TEXT NOT NULL DEFAULT ''",
            "scientific_contract_version": "TEXT NOT NULL DEFAULT ''",
            "quality_gate_version": "TEXT NOT NULL DEFAULT ''",
            "quality_state": "TEXT NOT NULL DEFAULT 'legacy_needs_revalidation'",
        },
        "local_sources_v14": {
            "source_kind": "TEXT NOT NULL DEFAULT 'connected'",
            "revision": "INTEGER NOT NULL DEFAULT 1",
            "display_location": "TEXT NOT NULL DEFAULT ''",
        },
        "research_datasets": {
            "source_id": "TEXT NOT NULL DEFAULT ''",
        },
        "candidate_work_evidence": {
            "source_document_id": "TEXT NOT NULL DEFAULT ''",
            "atom_id": "TEXT NOT NULL DEFAULT ''",
        },
    }
    for table, additions in table_additions.items():
        columns = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for name, declaration in additions.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_local_candidates_collection "
        "ON local_candidates(goal_id, source_id, area, quality_state, "
        "updated_at DESC, candidate_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_research_datasets_source "
        "ON research_datasets(source_id, updated_at DESC, dataset_id)"
    )


def _ensure_usability_recovery_columns(conn: sqlite3.Connection) -> None:
    table_additions: dict[str, dict[str, str]] = {
        "v14_jobs": {
            "completed_units": "INTEGER NOT NULL DEFAULT 0",
            "total_units": "INTEGER NOT NULL DEFAULT 0",
            "elapsed_seconds": "REAL NOT NULL DEFAULT 0",
            "eta_seconds": "REAL",
            "last_activity_at": "TEXT NOT NULL DEFAULT ''",
            "status_message": "TEXT NOT NULL DEFAULT ''",
            "retry_after_seconds": "REAL",
        },
        "scholarly_retrieval_runs": {
            "job_id": "TEXT NOT NULL DEFAULT ''",
            "result_revision": "INTEGER NOT NULL DEFAULT 0",
        },
        "local_extraction_selections": {
            "research_focus": "TEXT NOT NULL DEFAULT ''",
            "extraction_mode": "TEXT NOT NULL DEFAULT 'focus_guided'",
            "context_json": "TEXT NOT NULL DEFAULT '{}'",
        },
        "local_candidates": {
            "extraction_mode": "TEXT NOT NULL DEFAULT 'focus_guided'",
            "context_relevance": "TEXT NOT NULL DEFAULT 'not_evaluated'",
        },
    }
    for table, additions in table_additions.items():
        columns = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for name, declaration in additions.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_scholarly_runs_job "
        "ON scholarly_retrieval_runs(job_id) WHERE job_id != ''"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_local_candidates_context "
        "ON local_candidates(extraction_mode, context_relevance, updated_at DESC, candidate_id)"
    )


def _backfill_usability_recovery(conn: sqlite3.Connection, *, now: str) -> dict[str, int]:
    areas_backfilled = 0
    tasks_backfilled = 0
    results_backfilled = 0
    for candidate_id, area, created_at in conn.execute(
        "SELECT candidate_id, area, created_at FROM local_candidates ORDER BY candidate_id"
    ).fetchall():
        normalized_area = str(area or "").strip()
        if not normalized_area:
            continue
        areas_backfilled += int(
            conn.execute(
                """
                INSERT OR IGNORE INTO candidate_area_assignments(
                    candidate_id, area, revision, state, provenance, rationale,
                    model_trace_json, payload_json, created_at
                ) VALUES (?, ?, 1, 'confirmed', 'legacy_area',
                          'Preserved from the pre-v1.4.0-005 Candidate area field.',
                          '{}', ?, ?)
                """,
                (
                    str(candidate_id),
                    normalized_area,
                    json.dumps(
                        {"historical": True, "area": normalized_area},
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    str(created_at or now),
                ),
            ).rowcount
        )
    rows = conn.execute(
        """
        SELECT search_id, goal, target_count, state, payload_json, created_at, updated_at
        FROM scholarly_retrieval_runs ORDER BY created_at, search_id
        """
    ).fetchall()
    for search_id, query, target_count, state, payload_json, created_at, updated_at in rows:
        tasks_backfilled += int(
            conn.execute(
                """
                INSERT OR IGNORE INTO literature_search_tasks(
                    search_id, job_id, query, target_count, deadline_seconds, state,
                    checkpoint_json, result_revision, created_at, updated_at
                ) VALUES (?, NULL, ?, ?, 120, ?, '{}', 1, ?, ?)
                """,
                (
                    str(search_id),
                    str(query),
                    int(target_count),
                    str(state),
                    str(created_at or now),
                    str(updated_at or now),
                ),
            ).rowcount
        )
        raw_payload = str(payload_json)
        try:
            logical_payload = json.loads(raw_payload)
        except (TypeError, json.JSONDecodeError):
            logical_payload = {"unparsed_payload": raw_payload}
        result_digest = canonical_sha256(logical_payload)
        provisional_count = len(logical_payload.get("results") or []) if isinstance(
            logical_payload, dict
        ) else 0
        results_backfilled += int(
            conn.execute(
                """
                INSERT OR IGNORE INTO literature_search_result_revisions(
                    search_id, revision, state, provisional_count, result_digest,
                    payload_json, created_at
                ) VALUES (?, 1, ?, ?, ?, ?, ?)
                """,
                (
                    str(search_id),
                    str(state),
                    provisional_count,
                    result_digest,
                    raw_payload,
                    str(updated_at or created_at or now),
                ),
            ).rowcount
        )
    return {
        "candidate_areas_backfilled": areas_backfilled,
        "literature_tasks_backfilled": tasks_backfilled,
        "literature_result_revisions_backfilled": results_backfilled,
    }


def _slug(value: str, *, fallback: str = "research-goal") -> str:
    output = []
    previous_dash = False
    for character in value.casefold():
        if character.isascii() and character.isalnum():
            output.append(character)
            previous_dash = False
        elif output and not previous_dash:
            output.append("-")
            previous_dash = True
    slug = "".join(output).strip("-")[:56]
    return slug or fallback


def _backfill_human_centered_aggregates(
    conn: sqlite3.Connection, *, db_path: Path, now: str
) -> dict[str, int]:
    workspace_root = db_path.parent.parent
    goal_count = 0
    source_count = 0
    document_count = 0
    searches = conn.execute(
        "SELECT search_id, goal, area, created_at, updated_at "
        "FROM scholarly_retrieval_runs ORDER BY created_at, search_id"
    ).fetchall()
    for search_id, goal, area, created_at, updated_at in searches:
        stable = hashlib.sha256(str(search_id).encode()).hexdigest()
        goal_id = f"goal:{stable[:26]}"
        source_id = f"source:managed:{stable[:20]}"
        directory_name = f"{_slug(str(goal))}-{stable[:8]}"
        display_location = f"Principia Local Data/{directory_name}"
        source_root = workspace_root / "Principia Local Data" / directory_name
        source_payload = {
            "source_id": source_id,
            "source_kind": "managed_literature",
            "display_name": str(goal)[:120],
            "display_location": display_location,
            "status": "pending_materialization",
            "revision": 1,
            "search_id": str(search_id),
            "goal_id": goal_id,
        }
        inserted_source = conn.execute(
            """
            INSERT OR IGNORE INTO local_sources_v14(
                source_id, portable_uri, absolute_root, display_name, status,
                payload_json, created_at, updated_at, source_kind, revision,
                display_location
            ) VALUES (?, ?, ?, ?, 'pending_materialization', ?, ?, ?,
                      'managed_literature', 1, ?)
            """,
            (
                source_id,
                f"principia-managed://{stable[:20]}",
                str(source_root),
                str(goal)[:120],
                json.dumps(source_payload, ensure_ascii=False, sort_keys=True),
                str(created_at or now),
                str(updated_at or now),
                display_location,
            ),
        ).rowcount
        source_count += int(inserted_source)
        goal_payload = {
            "goal_id": goal_id,
            "search_id": str(search_id),
            "goal": str(goal),
            "area": str(area),
            "source_id": source_id,
            "status": "active",
        }
        inserted_goal = conn.execute(
            """
            INSERT OR IGNORE INTO local_research_goals(
                goal_id, search_id, goal, area, source_id, status, payload_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)
            """,
            (
                goal_id,
                str(search_id),
                str(goal),
                str(area),
                source_id,
                json.dumps(goal_payload, ensure_ascii=False, sort_keys=True),
                str(created_at or now),
                str(updated_at or now),
            ),
        ).rowcount
        goal_count += int(inserted_goal)
        conn.execute(
            "UPDATE research_datasets SET source_id=? WHERE search_id=? AND source_id=''",
            (source_id, str(search_id)),
        )
        conn.execute(
            """
            UPDATE local_candidates SET goal_id=?, source_id=?
            WHERE dataset_id IN (
                SELECT dataset_id FROM research_datasets WHERE search_id=?
            ) AND (goal_id='' OR source_id='')
            """,
            (goal_id, source_id, str(search_id)),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO candidate_goal_memberships(candidate_id, goal_id, created_at)
            SELECT candidate_id, ?, ? FROM local_candidates WHERE goal_id=?
            """,
            (goal_id, now, goal_id),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO candidate_source_memberships(candidate_id, source_id, created_at)
            SELECT candidate_id, ?, ? FROM local_candidates WHERE source_id=?
            """,
            (source_id, now, source_id),
        )
        acquisitions = conn.execute(
            """
            SELECT dw.work_id, a.acquisition_id, a.content_kind,
                   a.byte_sha256, a.text_sha256, a.status, a.updated_at
            FROM dataset_works dw
            JOIN research_datasets d ON d.dataset_id=dw.dataset_id
            LEFT JOIN scholarly_acquisitions a
                ON a.dataset_id=dw.dataset_id AND a.work_id=dw.work_id
            WHERE d.search_id=?
            ORDER BY d.updated_at DESC, dw.ordinal, dw.work_id
            """,
            (str(search_id),),
        ).fetchall()
        seen_works: set[str] = set()
        for acquisition in acquisitions:
            work_id = str(acquisition[0])
            if work_id in seen_works:
                continue
            seen_works.add(work_id)
            acquisition_id = str(acquisition[1] or "")
            content_kind = str(acquisition[2] or "metadata")
            content_sha256 = str(acquisition[4] or acquisition[3] or "")
            short = hashlib.sha256(work_id.encode()).hexdigest()[:16]
            if content_kind == "pdf":
                relative_uri = f"papers/work-{short}.pdf"
            elif content_kind == "abstract":
                relative_uri = f"abstracts/work-{short}.txt"
            else:
                relative_uri = f"metadata/work-{short}.json"
            document_id = (
                f"doc:{hashlib.sha256(f'{source_id}:{work_id}'.encode()).hexdigest()[:26]}"
            )
            payload = {
                "document_id": document_id,
                "source_id": source_id,
                "work_id": work_id,
                "portable_relative_uri": relative_uri,
                "parse_status": "indexed" if content_sha256 else "metadata_only",
                "extraction_eligible": bool(content_sha256),
                "materialization_state": "pending_copy",
            }
            inserted_document = conn.execute(
                """
                INSERT OR IGNORE INTO local_source_documents(
                    document_id, source_id, work_id, acquisition_id,
                    portable_relative_uri, content_sha256, parse_status,
                    extraction_eligible, principle_count, last_indexed_revision,
                    payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 1, ?, ?, ?)
                """,
                (
                    document_id,
                    source_id,
                    work_id,
                    acquisition_id or None,
                    relative_uri,
                    content_sha256,
                    payload["parse_status"],
                    1 if payload["extraction_eligible"] else 0,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    str(acquisition[6] or now),
                    str(acquisition[6] or now),
                ),
            ).rowcount
            document_count += int(inserted_document)
    # Fail closed: legacy v1 output is preserved but is not part of active search
    # or map projections until it earns a versioned v2 quality decision.
    conn.execute(
        """
        UPDATE local_candidates
        SET quality_state='legacy_needs_revalidation',
            scientific_contract_version='', quality_gate_version=''
        WHERE quality_state='' OR quality_state='legacy_needs_revalidation'
        """
    )
    conn.execute("DELETE FROM local_principle_fts WHERE version=0")
    return {
        "research_goals_backfilled": goal_count,
        "managed_sources_backfilled": source_count,
        "source_documents_backfilled": document_count,
    }


def _legacy_extraction_candidate_payload(
    *,
    extraction_id: str,
    work_id: str,
    work_title: str,
    principle: Any,
    index: int,
    now: str,
) -> tuple[dict[str, Any], str, str]:
    raw = principle if isinstance(principle, dict) else {"claim": str(principle)}
    claim = str(
        raw.get("claim")
        or raw.get("statement")
        or raw.get("principle")
        or raw.get("description")
        or raw.get("name")
        or ""
    ).strip()
    if not claim:
        claim = f"Legacy extraction record {index + 1} from {work_title}"
    title = str(raw.get("title") or raw.get("name") or claim).strip()[:240]
    raw_kind = str(raw.get("kind") or raw.get("type") or "hypothesis").strip().lower()
    kind = (
        raw_kind
        if raw_kind in {"theorem", "mechanistic", "empirical", "heuristic", "hypothesis"}
        else "hypothesis"
    )
    raw_scope = raw.get("scope")
    if isinstance(raw_scope, dict) and str(raw_scope.get("statement") or "").strip():
        scope = {
            "statement": str(raw_scope["statement"]).strip(),
            "conditions": list(raw_scope.get("conditions") or [])[:20],
            "exclusions": list(raw_scope.get("exclusions") or [])[:20],
            "populations": list(raw_scope.get("populations") or [])[:20],
        }
    else:
        scope = {
            "statement": str(raw_scope or "Imported v1.3 extraction; scope requires review."),
            "conditions": [],
            "exclusions": [],
            "populations": [],
        }
    stable = hashlib.sha256(f"{extraction_id}:{index}".encode()).hexdigest()[:24]
    candidate_id = f"cand:legacy-extraction:{stable}"
    payload: dict[str, Any] = {
        "candidate_id": candidate_id,
        "area": "legacy-extractions",
        "title": title,
        "claim": claim,
        "kind": kind,
        "scope": scope,
        "falsifier": str(raw.get("falsifier") or ""),
        "source_references": [
            {
                "work_id": work_id,
                "title": work_title,
                "url": "",
                "doi": "",
                "role": "evidence",
                "public": True,
            }
        ],
        "relations": [],
        "generation_trace": [],
        "assessment_status": "unassessed",
        "raw_legacy_payload": {
            "legacy_table": "extractions",
            "legacy_extraction_id": extraction_id,
            "legacy_principle_index": index,
            "principle": raw,
        },
        "created_at": now,
        "updated_at": now,
    }
    fingerprint = canonical_sha256(
        {"claim": " ".join(claim.casefold().split()), "kind": kind, "scope": scope["statement"]}
    )
    return payload, canonical_sha256(payload), fingerprint


def _import_legacy_extracted_principles(conn: sqlite3.Connection, now: str) -> int:
    tables = {
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if not {"extractions", "works"}.issubset(tables):
        return 0
    imported = 0
    rows = conn.execute(
        """
        SELECT e.id, e.work_id, e.payload_json, w.payload_json
        FROM extractions e JOIN works w ON w.id=e.work_id
        ORDER BY e.id
        """
    ).fetchall()
    for extraction_id, work_id, extraction_json, work_json in rows:
        try:
            extraction = json.loads(str(extraction_json))
        except (TypeError, json.JSONDecodeError):
            continue
        principles = extraction.get("principles") if isinstance(extraction, dict) else None
        if not isinstance(principles, list):
            continue
        try:
            work = json.loads(str(work_json))
        except (TypeError, json.JSONDecodeError):
            work = {}
        work_title = str(work.get("title") or f"Legacy work {work_id}")
        for index, principle in enumerate(principles):
            payload, output_digest, fingerprint = _legacy_extraction_candidate_payload(
                extraction_id=str(extraction_id),
                work_id=str(work_id),
                work_title=work_title,
                principle=principle,
                index=index,
                now=now,
            )
            candidate_id = str(payload["candidate_id"])
            inserted = conn.execute(
                """
                INSERT OR IGNORE INTO local_candidates(
                    candidate_id, area, title, claim, assessment_status, source_kind,
                    payload_json, content_digest, created_at, updated_at,
                    eligibility_status, candidate_fingerprint, source_count
                ) VALUES (?, ?, ?, ?, 'unassessed', 'legacy_extraction', ?, ?, ?, ?,
                          'legacy_unverified', ?, 1)
                """,
                (
                    candidate_id,
                    payload["area"],
                    payload["title"],
                    payload["claim"],
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    output_digest,
                    now,
                    now,
                    fingerprint,
                ),
            ).rowcount
            if not inserted:
                continue
            raw_principle = json.dumps(principle, ensure_ascii=False, sort_keys=True)
            input_digest = hashlib.sha256(raw_principle.encode()).hexdigest()
            event_suffix = candidate_id.rsplit(":", 1)[-1]
            conn.execute(
                """
                INSERT INTO v14_events(
                    event_id, aggregate_type, aggregate_id, operation, input_digest,
                    output_digest, payload_json, created_at
                ) VALUES (?, 'candidate', ?, 'legacy_extraction_import', ?, ?, ?, ?)
                """,
                (
                    f"evt:legacy-extraction:{event_suffix}",
                    candidate_id,
                    input_digest,
                    output_digest,
                    json.dumps(
                        {
                            "legacy_table": "extractions",
                            "legacy_extraction_id": str(extraction_id),
                            "legacy_work_id": str(work_id),
                            "eligible": False,
                            "reviewed": False,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    now,
                ),
            )
            excerpt_digest = hashlib.sha256(str(payload["claim"]).encode()).hexdigest()
            conn.execute(
                """
                INSERT INTO candidate_work_evidence(
                    evidence_id, candidate_id, work_id, acquisition_id, segment_id,
                    role, locator_json, excerpt_sha256, extraction_trace_json,
                    visibility, created_at
                ) VALUES (?, ?, ?, NULL, NULL, 'evidence', ?, ?, ?, 'private', ?)
                """,
                (
                    f"ev:legacy:{event_suffix}",
                    candidate_id,
                    str(work_id),
                    json.dumps({"legacy_extraction_id": str(extraction_id)}, sort_keys=True),
                    excerpt_digest,
                    json.dumps({"source": "v1.3-extraction", "verified_anchor": False}),
                    now,
                ),
            )
            conn.execute(
                "INSERT INTO local_principle_fts(principle_id, version, title, claim, area, tags) "
                "VALUES (?, 0, ?, ?, ?, '')",
                (candidate_id, payload["title"], payload["claim"], payload["area"]),
            )
            imported += 1
    return imported


def migrate_workspace(db_path: Path, *, legacy_database_existed: bool) -> dict[str, Any]:
    db_path = Path(db_path)
    if _migration_applied(db_path):
        return {"version": MIGRATION_VERSION, "applied": False, "already_current": True}
    with migration_lock(db_path):
        if _migration_applied(db_path):
            return {"version": MIGRATION_VERSION, "applied": False, "already_current": True}
        backup_path: Path | None = None
        backup_sha256 = ""
        if legacy_database_existed and db_path.exists() and db_path.stat().st_size:
            backup_path, backup_sha256 = _backup_database(db_path)
        now = _utc_now()
        legacy_checksum = hashlib.sha256(_SCHEMA_SQL.encode()).hexdigest()
        admin_checksum = hashlib.sha256((_SCHEMA_SQL + _ADMIN_SCHEMA_SQL).encode()).hexdigest()
        literature_checksum = hashlib.sha256(
            (_SCHEMA_SQL + _ADMIN_SCHEMA_SQL + _LITERATURE_SCHEMA_SQL).encode()
        ).hexdigest()
        human_centered_checksum = hashlib.sha256(
            (
                _SCHEMA_SQL
                + _ADMIN_SCHEMA_SQL
                + _LITERATURE_SCHEMA_SQL
                + _HUMAN_CENTERED_SCHEMA_SQL
            ).encode()
        ).hexdigest()
        checksum = hashlib.sha256(
            (
                _SCHEMA_SQL
                + _ADMIN_SCHEMA_SQL
                + _LITERATURE_SCHEMA_SQL
                + _HUMAN_CENTERED_SCHEMA_SQL
                + _USABILITY_RECOVERY_SCHEMA_SQL
            ).encode()
        ).hexdigest()
        conn = connect_sqlite(db_path, timeout=30)
        try:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("BEGIN IMMEDIATE")
            imported = 0
            imported_extracted = 0
            aggregate_counts = {
                "research_goals_backfilled": 0,
                "managed_sources_backfilled": 0,
                "source_documents_backfilled": 0,
            }
            recovery_counts = {
                "candidate_areas_backfilled": 0,
                "literature_tasks_backfilled": 0,
                "literature_result_revisions_backfilled": 0,
            }
            legacy_applied = (
                conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
                ).fetchone()
                and conn.execute(
                    "SELECT 1 FROM schema_migrations WHERE version=?", (LEGACY_IMPORT_MIGRATION,)
                ).fetchone()
            )
            if not legacy_applied:
                for statement in _SCHEMA_SQL.split(";"):
                    if statement.strip():
                        conn.execute(statement)
                imported = _import_legacy_ideas(conn, now)
                conn.execute(
                    "INSERT INTO schema_migrations(version, checksum, applied_at) VALUES (?, ?, ?)",
                    (LEGACY_IMPORT_MIGRATION, legacy_checksum, now),
                )
            admin_applied = conn.execute(
                "SELECT 1 FROM schema_migrations WHERE version=?", (ADMIN_MIGRATION_VERSION,)
            ).fetchone()
            if not admin_applied:
                for statement in _ADMIN_SCHEMA_SQL.split(";"):
                    if statement.strip():
                        conn.execute(statement)
                conn.execute(
                    "INSERT INTO schema_migrations(version, checksum, applied_at) VALUES (?, ?, ?)",
                    (ADMIN_MIGRATION_VERSION, admin_checksum, now),
                )
            literature_applied = conn.execute(
                "SELECT 1 FROM schema_migrations WHERE version=?",
                (LITERATURE_MIGRATION_VERSION,),
            ).fetchone()
            if not literature_applied:
                for statement in _LITERATURE_SCHEMA_SQL.split(";"):
                    if statement.strip():
                        conn.execute(statement)
                _ensure_local_candidate_columns(conn)
                imported_extracted = _import_legacy_extracted_principles(conn, now)
                conn.execute(
                    "INSERT INTO schema_migrations(version, checksum, applied_at) VALUES (?, ?, ?)",
                    (LITERATURE_MIGRATION_VERSION, literature_checksum, now),
                )
            human_centered_applied = conn.execute(
                "SELECT 1 FROM schema_migrations WHERE version=?",
                (HUMAN_CENTERED_MIGRATION_VERSION,),
            ).fetchone()
            if not human_centered_applied:
                for statement in _HUMAN_CENTERED_SCHEMA_SQL.split(";"):
                    if statement.strip():
                        conn.execute(statement)
                _ensure_human_centered_columns(conn)
                aggregate_counts = _backfill_human_centered_aggregates(
                    conn, db_path=db_path, now=now
                )
                conn.execute(
                    "INSERT INTO schema_migrations(version, checksum, applied_at) VALUES (?, ?, ?)",
                    (HUMAN_CENTERED_MIGRATION_VERSION, human_centered_checksum, now),
                )
            for statement in _USABILITY_RECOVERY_SCHEMA_SQL.split(";"):
                if statement.strip():
                    conn.execute(statement)
            _ensure_usability_recovery_columns(conn)
            recovery_counts = _backfill_usability_recovery(conn, now=now)
            conn.execute(
                "INSERT INTO schema_migrations(version, checksum, applied_at) VALUES (?, ?, ?)",
                (MIGRATION_VERSION, checksum, now),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        receipt = {
            "version": MIGRATION_VERSION,
            "applied": True,
            "schema_checksum": checksum,
            "backup_path": str(backup_path) if backup_path else "",
            "backup_sha256": backup_sha256,
            "legacy_ideas_imported": imported,
            "legacy_extracted_principles_imported": imported_extracted,
            **aggregate_counts,
            **recovery_counts,
            "applied_at": now,
        }
        receipt_dir = db_path.parent / "migration_receipts"
        receipt_dir.mkdir(parents=True, exist_ok=True)
        receipt_path = receipt_dir / f"{MIGRATION_VERSION}.json"
        if not receipt_path.exists():
            receipt_path.write_text(
                json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            os.chmod(receipt_path, 0o600)
        return receipt
