from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from principia.domain import (
    CandidatePrinciple,
    CanonicalizationError,
    GenerationTrace,
    PrincipleCapsule,
    PrincipleKind,
    PrincipleMaturity,
    PrincipleScope,
    QualityAssessment,
    TraceOperation,
    WorkReference,
    canonical_sha256,
    loads_strict,
    principle_id,
)
from principia.persistence import V14WorkspaceRepository
from principia.storage import WorkspaceStorage


def test_new_principle_ids_are_scoped_monotonic_ulids() -> None:
    first = principle_id("complex-systems")
    second = principle_id("complex-systems")
    assert first.startswith("prn:complex-systems:")
    assert len(first.rsplit(":", 1)[1]) == 26
    assert first < second


def test_canonical_json_is_order_independent_and_strict() -> None:
    assert canonical_sha256({"b": 2, "a": 1}) == canonical_sha256({"a": 1, "b": 2})
    with pytest.raises(CanonicalizationError, match="duplicate JSON key"):
        loads_strict('{"a": 1, "a": 2}')
    with pytest.raises(CanonicalizationError, match="non-finite"):
        canonical_sha256({"value": float("nan")})


def test_candidate_is_unassessed_and_rejects_fabricated_quality() -> None:
    candidate = CandidatePrinciple(
        candidate_id="cand:test",
        area="complex-systems",
        title="Local candidate",
        claim="A bounded claim",
        kind=PrincipleKind.HYPOTHESIS,
        scope=PrincipleScope(statement="Synthetic acceptance scope"),
    )
    assert candidate.assessment_status == "unassessed"
    with pytest.raises(ValidationError):
        CandidatePrinciple.model_validate({**candidate.model_dump(), "quality": {"grade": "A"}})


def _capsule() -> PrincipleCapsule:
    trace = GenerationTrace(
        event_id="evt:test",
        operation=TraceOperation.REVIEW,
        actor="reviewer",
        input_sha256="1" * 64,
        output_sha256="2" * 64,
    )
    return PrincipleCapsule(
        principle_id=principle_id("complex-systems"),
        area="complex-systems",
        version=1,
        title="A reviewed principle",
        claim="The reviewed synthetic claim",
        kind=PrincipleKind.EMPIRICAL,
        maturity=PrincipleMaturity.SUPPORTED,
        scope=PrincipleScope(statement="Synthetic systems"),
        quality=QualityAssessment(
            grade="B",
            validity=0.8,
            reproducibility=0.7,
            evidence_strength=0.7,
            generality=0.6,
            usefulness=0.9,
            assessed_by="reviewer",
        ),
        falsifier="A held-out synthetic observation disagrees.",
        source_references=[WorkReference(work_id="work:1", title="Synthetic evidence")],
        generation_trace=[trace],
        source_count=1,
        relation_count=0,
        trace_count=1,
    )


def test_workspace_revisions_are_immutable(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path)
    repository = V14WorkspaceRepository(storage.db_path)
    capsule = _capsule()
    repository.save_capsule(capsule)
    with pytest.raises(ValueError, match="immutable"):
        repository.save_capsule(capsule)


def test_legacy_idea_migration_creates_backup_and_unassessed_candidate(tmp_path: Path) -> None:
    meta = tmp_path / ".principia"
    meta.mkdir()
    db_path = meta / "principia.sqlite"
    legacy = {
        "id": "idea-1",
        "title": "Legacy idea",
        "thesis": "Legacy claim",
        "mode": "standard",
        "lineage": {"seed": "legacy"},
        "trace": {"provider": "fixture"},
        "generation_metadata": {"model": "fixture-model"},
    }
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE ideas(id TEXT PRIMARY KEY, mode TEXT, model TEXT, payload_json TEXT, "
            "created_at TEXT, updated_at TEXT)"
        )
        conn.execute(
            "INSERT INTO ideas VALUES ('idea-1', 'standard', 'fixture-model', ?, '', '')",
            (json.dumps(legacy),),
        )

    first = WorkspaceStorage(tmp_path)
    assert first.v14_migration["legacy_ideas_imported"] == 1
    backup = Path(first.v14_migration["backup_path"])
    assert backup.exists()
    assert len(first.v14_migration["backup_sha256"]) == 64
    repository = V14WorkspaceRepository(first.db_path)
    candidates = repository.list_candidates()
    assert len(candidates) == 1
    assert candidates[0].assessment_status == "unassessed"
    assert candidates[0].raw_legacy_payload == legacy

    second = WorkspaceStorage(tmp_path)
    assert second.v14_migration["already_current"] is True
    assert len(repository.list_candidates()) == 1
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM v14_events").fetchone()[0] == 1


def test_generated_schemas_are_in_sync() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "scripts/generate_v14_schemas.py", "--check"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
