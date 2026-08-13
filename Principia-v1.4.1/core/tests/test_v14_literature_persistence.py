from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from principia.domain import CandidatePrinciple, JobRecord, PrincipleKind, PrincipleScope
from principia.models import WorkFeatures, WorkItem
from principia.persistence import V14WorkspaceRepository
from principia.persistence.migrations import LITERATURE_MIGRATION_VERSION, MIGRATION_VERSION
from principia.storage import WorkspaceStorage


def _candidate(index: int) -> CandidatePrinciple:
    return CandidatePrinciple(
        candidate_id=f"cand:page:{index:04d}",
        area="machine-intelligence",
        title=f"Grounded candidate {index}",
        claim=f"A bounded mechanism claim supported by fixture evidence number {index}.",
        kind=PrincipleKind.MECHANISTIC,
        scope=PrincipleScope(statement="Synthetic literature persistence fixture"),
        created_at=f"2026-08-09T00:{index // 60:02d}:{index % 60:02d}+00:00",
        updated_at=f"2026-08-09T00:{index // 60:02d}:{index % 60:02d}+00:00",
    )


def test_candidate_keyset_pagination_has_no_gaps_or_duplicates(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path)
    repository = V14WorkspaceRepository(storage.db_path)
    expected = {_candidate(index).candidate_id for index in range(205)}
    for index in range(205):
        repository.save_candidate(_candidate(index), discovery_job_id="job:fixture")

    seen: list[str] = []
    cursor = ""
    while True:
        page = repository.browse_candidates(limit=37, cursor=cursor, discovery_id="job:fixture")
        seen.extend(item["candidate_id"] for item in page["items"])
        cursor = page["next_cursor"] or ""
        if not cursor:
            break
    assert len(seen) == 205
    assert len(set(seen)) == 205
    assert set(seen) == expected


def test_v14_counts_separate_visible_from_quarantined_evidence(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path)
    repository = V14WorkspaceRepository(storage.db_path)
    work = WorkItem(id="work:count", title="Evidence count fixture")
    storage.save_work(work)
    for index, eligibility in enumerate(("eligible", "quarantined")):
        candidate = _candidate(index)
        repository.save_candidate(candidate, eligibility_status=eligibility)
        repository.save_candidate_evidence(
            evidence_id=f"evidence:count:{index}",
            candidate_id=candidate.candidate_id,
            work_id=work.id,
            excerpt_sha256=f"{'0' if index == 0 else '1'}" * 64,
        )

    counts = repository.v14_counts()
    assert counts["candidate_evidence_links"] == 2
    assert counts["eligible_candidate_evidence_links"] == 1


def test_003_imports_v13_extracted_principles_with_work_provenance(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path)
    work = WorkItem(id="work:legacy", title="A legacy paper", abstract="Legacy evidence")
    storage.save_work(work)
    extraction = WorkFeatures(
        work_id=work.id,
        title=work.title,
        model="fixture-model",
        principles=[
            {
                "title": "Boundary-conditioned improvement",
                "claim": "Verification improves decisions only when the verifier has independent signal.",
                "kind": "empirical",
                "scope": "Synthetic legacy extraction",
            }
        ],
        extraction_id="ext:legacy",
    )
    storage.save_extraction(extraction, "legacy-content")
    with sqlite3.connect(storage.db_path) as conn:
        conn.execute(
            "DELETE FROM schema_migrations WHERE version IN (?, ?)",
            (LITERATURE_MIGRATION_VERSION, MIGRATION_VERSION),
        )
        conn.execute("DELETE FROM local_candidates")
        conn.execute("DELETE FROM local_principle_fts")
    receipt = tmp_path / ".principia" / "migration_receipts" / f"{MIGRATION_VERSION}.json"
    receipt.unlink(missing_ok=True)

    reopened = WorkspaceStorage(tmp_path)
    assert reopened.v14_migration["legacy_extracted_principles_imported"] == 1
    repository = V14WorkspaceRepository(reopened.db_path)
    candidate = repository.list_candidates(limit=10)[0]
    assert candidate.assessment_status == "unassessed"
    assert candidate.source_references[0].work_id == work.id
    detail = repository.candidate_detail(candidate.candidate_id)
    assert detail is not None
    assert detail["local_metadata"]["eligibility_status"] == "legacy_unverified"
    assert detail["evidence"][0]["work_id"] == work.id

    counts_before = repository.v14_counts()
    second = WorkspaceStorage(tmp_path)
    assert second.v14_migration["already_current"] is True
    assert repository.v14_counts() == counts_before


def test_literature_tables_are_private_and_additive(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path)
    with sqlite3.connect(storage.db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        candidate_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(local_candidates)").fetchall()
        }
    assert {
        "scholarly_retrieval_runs",
        "research_datasets",
        "scholarly_acquisitions",
        "candidate_work_evidence",
        "v14_job_units",
        "provider_attempts",
    }.issubset(tables)
    assert {"eligibility_status", "candidate_fingerprint", "source_count"}.issubset(
        candidate_columns
    )
    receipt = json.loads(
        (tmp_path / ".principia" / "migration_receipts" / f"{MIGRATION_VERSION}.json").read_text()
    )
    assert receipt["version"] == "1.4.0-005"


def test_005_adds_durable_search_relation_metric_and_optional_context_contracts(
    tmp_path: Path,
) -> None:
    storage = WorkspaceStorage(tmp_path)
    with sqlite3.connect(storage.db_path) as conn:
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        job_columns = {row[1] for row in conn.execute("PRAGMA table_info(v14_jobs)").fetchall()}
        selection_columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(local_extraction_selections)").fetchall()
        }
        candidate_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(local_candidates)").fetchall()
        }
    assert {
        "literature_search_tasks",
        "literature_search_attempts",
        "literature_search_result_revisions",
        "workspace_runtime_leases",
        "candidate_area_assignments",
        "principle_relation_revisions",
        "relation_metric_revisions",
        "principle_relation_metrics",
    }.issubset(tables)
    assert {
        "completed_units",
        "total_units",
        "elapsed_seconds",
        "eta_seconds",
        "last_activity_at",
        "status_message",
        "retry_after_seconds",
    }.issubset(job_columns)
    assert {"research_focus", "extraction_mode", "context_json"}.issubset(selection_columns)
    assert {"extraction_mode", "context_relevance"}.issubset(candidate_columns)


def test_single_workspace_runtime_lease_prevents_competing_reconciliation(
    tmp_path: Path,
) -> None:
    storage = WorkspaceStorage(tmp_path)
    first = V14WorkspaceRepository(storage.db_path)
    second = V14WorkspaceRepository(storage.db_path)

    lease_id = first.acquire_runtime_lease()

    assert lease_id is not None
    assert second.acquire_runtime_lease() is None


def test_unambiguous_source_membership_repairs_missing_goal_link(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path)
    repository = V14WorkspaceRepository(storage.db_path)
    source_id = "src:repair-membership"
    search_id = "search:repair-membership"
    repository.register_source(source_id, tmp_path, "local-source://repair", "Repair")
    repository.save_literature_search(
        {
            "search_id": search_id,
            "goal": "Which verification mechanisms improve LLM reasoning?",
            "area": "machine-intelligence",
            "target_count": 1,
            "state": "ready",
            "selected_work_ids": ["work:repair"],
        }
    )
    goal_id = repository.bind_research_goal_source(search_id=search_id, source_id=source_id)
    candidate = _candidate(999)
    repository.save_candidate(candidate, source_id=source_id, goal_id="")

    detail = repository.candidate_detail(candidate.candidate_id)
    assert detail is not None
    assert detail["local_metadata"]["goal_ids"] == []
    assert repository.repair_candidate_goal_memberships() == {
        "repaired": 1,
        "unresolved": 0,
    }
    detail = repository.candidate_detail(candidate.candidate_id)
    assert detail is not None
    assert detail["local_metadata"]["goal_ids"] == [goal_id]
    assert repository.repair_candidate_goal_memberships()["repaired"] == 0


def test_outside_focus_candidate_is_not_added_to_goal_collection(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path)
    repository = V14WorkspaceRepository(storage.db_path)
    source_id = "src:outside-focus"
    search_id = "search:outside-focus"
    repository.register_source(source_id, tmp_path, "local-source://outside", "Outside")
    repository.save_literature_search(
        {
            "search_id": search_id,
            "goal": "How do multi-agent systems improve scientific discovery?",
            "area": "",
            "target_count": 1,
            "state": "ready",
            "selected_work_ids": ["work:outside"],
        }
    )
    goal_id = repository.bind_research_goal_source(search_id=search_id, source_id=source_id)
    candidate = _candidate(1000)
    repository.save_candidate(
        candidate,
        source_id=source_id,
        goal_id=goal_id,
        context_relevance="outside_focus",
    )

    detail = repository.candidate_detail(candidate.candidate_id)
    assert detail is not None
    assert detail["local_metadata"]["goal_id"] == goal_id
    assert detail["local_metadata"]["goal_ids"] == []
    repository.repair_candidate_goal_memberships()
    detail = repository.candidate_detail(candidate.candidate_id)
    assert detail is not None
    assert detail["local_metadata"]["goal_ids"] == []


def test_job_unit_projection_redacts_private_paths_and_secrets(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path)
    repository = V14WorkspaceRepository(storage.db_path)
    storage.save_work(WorkItem(id="work:redaction", title="Redaction fixture"))
    repository.save_job(
        JobRecord(
            job_id="job:redaction",
            kind="local_extraction",
            state="failed",
            stage="failed",
            progress=1,
        )
    )
    repository.save_job_unit(
        {
            "unit_id": "unit:redaction",
            "job_id": "job:redaction",
            "work_id": "work:redaction",
            "ordinal": 0,
            "state": "failed",
            "error": {
                "code": "fixture_failed",
                "message": (
                    "Could not parse /"
                    + "Users/researcher/"
                    + "private/paper.pdf; api_key=do-not-project"
                ),
                "retryable": True,
            },
        }
    )
    projected = repository.list_job_units("job:redaction")[0]
    message = projected["error"]["message"]
    assert "/" + "Users/researcher" not in message
    assert "do-not-project" not in message
    assert "[PRIVATE_PATH]" in message
    assert "[REDACTED]" in message
