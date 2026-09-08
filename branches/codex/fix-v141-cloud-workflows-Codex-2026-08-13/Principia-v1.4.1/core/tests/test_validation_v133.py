from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from principia import MockLLMClient, Workspace
from principia.models import (
    ExtractedFeatures,
    Idea,
    IdeaComparison,
    PipelineResult,
    WorkFeatures,
    WorkItem,
    WorkList,
)
from principia.storage import WorkspaceStorage
from principia.validation import (
    ValidationPlan,
    build_validation_plan,
    render_validation_plan_markdown,
    validation_plan_json,
)


def sample_idea() -> Idea:
    return Idea(
        id="Uncertainty_Aware_Quantum_Sensor",
        title="Uncertainty-Aware Quantum Sensor",
        thesis="Use uncertainty-calibrated readout to reject transient false positives.",
        mode="scidialect_evo",
        validation_protocol=[
            "Inject synthetic signals.",
            "Measure blind recovery under realistic noise.",
        ],
        baselines=["Matched filtering", "Unsqueezed resonator readout"],
        metrics=["Detection efficiency", "False-positive rate"],
        risks=["Calibration may drift across operating temperatures."],
        assumptions=["Noise-only control data are representative."],
        evidence_work_ids=["W1"],
        source_evidence=[
            {
                "work_id": "W1",
                "work_title": "Quantum sensing under realistic noise",
                "kind": "principles",
                "id": "P1",
                "title": "Calibrated rejection",
                "text": "False-positive controls must be measured independently.",
            }
        ],
        model="siliconflow:Qwen/Qwen3.5-397B-A17B",
        run_id="RUN_TEST",
        created_at="2026-07-14T12:00:00+00:00",
    )


def sample_result(root: Path) -> PipelineResult:
    works = WorkList(
        query="broadband quantum sensing",
        target_count=1,
        sources=["openalex"],
        items=[
            WorkItem(
                id="W1",
                title="Quantum sensing under realistic noise",
                abstract="A source paper.",
                pmid="123456",
                metadata={
                    "local_pdf_path": str(root / ".principia" / "artifacts" / "pdfs" / "W1.pdf")
                },
            )
        ],
    )
    features = ExtractedFeatures(
        model="mock:extractor",
        items=[
            WorkFeatures(
                work_id="W1",
                title="Quantum sensing under realistic noise",
                model="mock:extractor",
                retained_pdf_path=str(root / ".principia" / "artifacts" / "pdfs" / "W1.pdf"),
                principles=[{"id": "P1", "argument": "Calibrate false-positive rejection."}],
            )
        ],
    )
    idea = sample_idea()
    comparison = IdeaComparison(
        idea_id=idea.id,
        rows=[
            {"title": "Prior sensor", "essential_difference": "Explicit uncertainty calibration."}
        ],
        model="mock:compare",
    )
    return PipelineResult(
        goal="Detect ultralight dark matter under realistic noise.",
        works=works,
        features=features,
        idea=idea,
        comparison=comparison,
        workspace_path=str(root),
        export_path=str(root / "old-export"),
    )


def test_validation_plan_build_and_render_without_llm() -> None:
    idea = sample_idea()

    plan = build_validation_plan(
        idea,
        goal="Detect ultralight dark matter under realistic noise.",
        created_at="2026-07-14T13:00:00+00:00",
    )

    assert isinstance(plan, ValidationPlan)
    assert plan.schema_version == "1.0"
    assert plan.idea_id == idea.id
    assert plan.baselines == idea.baselines
    assert plan.comparators == idea.baselines
    assert [reference.work_id for reference in plan.evidence_references] == ["W1"]
    assert json.loads(validation_plan_json(plan))["validation_protocol"] == idea.validation_protocol
    markdown = render_validation_plan_markdown(plan)
    assert "## Validation Protocol" in markdown
    assert "## Baselines and Comparators" in markdown
    assert "False-positive rate" in markdown
    assert "`W1`" in markdown


def test_build_validation_plan_from_idea_requires_goal() -> None:
    with pytest.raises(ValueError, match="goal is required"):
        build_validation_plan(sample_idea())


def test_export_writes_validation_artifacts_to_all_locations_and_removes_absolute_paths(
    tmp_path: Path,
) -> None:
    workspace = Workspace(tmp_path, llm=MockLLMClient())
    result = sample_result(tmp_path)
    result.works.items[0].metadata["arbitrary_note"] = (
        f"Loaded from {tmp_path}/private/cache.bin and /Users/alice/notes.txt"
    )
    result.features.items[0].extraction_warnings.append(
        f"Parser cache was read from {tmp_path}/.principia/cache/parser.json and /opt/cache/parser.bin"
    )
    result.idea.risks.append(f"A local artifact at {tmp_path}/private/risk.txt may be stale.")
    result.idea.assumptions.append(r"A Windows cache at C:\Users\alice\risk.txt is current.")
    result.idea.source_evidence[0]["text"] = (
        "Evidence copied from file:///Users/alice/private/evidence.txt."
    )
    result.comparison.rows[0]["potential_weakness"] = (
        f"Comparison log lives under {tmp_path}/logs/compare.txt."
    )

    hidden = workspace.export_result(result)
    locations = [
        hidden,
        tmp_path / "principia_outputs" / "exports" / result.idea.id,
        tmp_path / "principia_outputs" / "latest",
    ]
    primary_artifacts = {
        "idea.md",
        "result.json",
        "works.json",
        "validation_plan.md",
        "validation_plan.json",
    }
    for location in locations:
        assert primary_artifacts <= {path.name for path in location.iterdir()}

    validation_payloads = [
        json.loads((location / "validation_plan.json").read_text()) for location in locations
    ]
    assert validation_payloads[0] == validation_payloads[1] == validation_payloads[2]
    assert ValidationPlan.model_validate(validation_payloads[0]).idea_id == result.idea.id

    forbidden_paths = (str(tmp_path), "/Users/alice", "/opt/cache", r"C:\Users\alice")
    for location in locations:
        for filename in primary_artifacts:
            text = (location / filename).read_text()
            assert not any(path in text for path in forbidden_paths), (location, filename)
    visible_readme = (locations[1] / "README.md").read_text()
    assert not any(path in visible_readme for path in forbidden_paths)
    assert ".principia/artifacts/exports/" in visible_readme

    result_payload = json.loads((hidden / "result.json").read_text())
    assert result_payload["workspace_path"] == "."
    assert result_payload["export_path"] == f"principia_outputs/exports/{result.idea.id}"
    assert (
        result_payload["features"]["items"][0]["retained_pdf_path"]
        == ".principia/artifacts/pdfs/W1.pdf"
    )
    works_payload = json.loads((hidden / "works.json").read_text())
    assert (
        works_payload["items"][0]["metadata"]["local_pdf_path"]
        == ".principia/artifacts/pdfs/W1.pdf"
    )
    assert "[local path]" in works_payload["items"][0]["metadata"]["arbitrary_note"]


def test_sqlite_migration_adds_and_backfills_v133_identity_columns(tmp_path: Path) -> None:
    meta_dir = tmp_path / ".principia"
    meta_dir.mkdir(parents=True)
    db_path = meta_dir / "principia.sqlite"
    legacy_payload = WorkItem(id="LEGACY", title="A legacy biomedical work").model_dump()
    legacy_payload.pop("semantic_scholar_id")
    legacy_payload.pop("pmid")
    legacy_payload.pop("pdf_url")
    legacy_payload["metadata"] = {"s2_id": "S2-LEGACY", "pmid": "998877"}
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE works (
                id TEXT PRIMARY KEY,
                title_norm TEXT NOT NULL,
                title_hash TEXT NOT NULL,
                doi TEXT DEFAULT '',
                arxiv_id TEXT DEFAULT '',
                openalex_id TEXT DEFAULT '',
                abstract_hash TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO works VALUES (?, ?, ?, '', '', '', ?, ?, ?, ?)",
            (
                "LEGACY",
                "a legacy biomedical work",
                "TITLEHASH",
                "ABSTRACTHASH",
                json.dumps(legacy_payload),
                legacy_payload["created_at"],
                legacy_payload["updated_at"],
            ),
        )

    storage = WorkspaceStorage(tmp_path)
    # Re-opening exercises migration idempotency.
    WorkspaceStorage(tmp_path)
    with storage.connect() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(works)").fetchall()}
        row = conn.execute(
            "SELECT semantic_scholar_id, pmid FROM works WHERE id = 'LEGACY'"
        ).fetchone()
        indexes = {row["name"] for row in conn.execute("PRAGMA index_list(works)").fetchall()}

    assert {"semantic_scholar_id", "pmid"} <= columns
    assert dict(row) == {"semantic_scholar_id": "S2-LEGACY", "pmid": "998877"}
    assert {"idx_works_openalex", "idx_works_semantic_scholar", "idx_works_pmid"} <= indexes
    loaded = storage.get_work("LEGACY")
    assert loaded is not None
    assert loaded.semantic_scholar_id == "S2-LEGACY"
    assert loaded.pmid == "998877"


def test_legacy_workspace_migration_creates_and_reuses_local_source_tables(
    tmp_path: Path,
) -> None:
    meta_dir = tmp_path / ".principia"
    meta_dir.mkdir(parents=True)
    db_path = meta_dir / "principia.sqlite"
    work = WorkItem(id="LEGACY_LOCAL", title="Legacy private source")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE works (
                id TEXT PRIMARY KEY,
                title_norm TEXT NOT NULL,
                title_hash TEXT NOT NULL,
                doi TEXT DEFAULT '',
                arxiv_id TEXT DEFAULT '',
                openalex_id TEXT DEFAULT '',
                abstract_hash TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO works VALUES (?, ?, ?, '', '', '', ?, ?, ?, ?)",
            (
                work.id,
                "legacy private source",
                "TITLEHASH",
                "ABSTRACTHASH",
                work.model_dump_json(),
                work.created_at,
                work.updated_at,
            ),
        )

    storage = WorkspaceStorage(tmp_path)
    asset = {
        "id": "ASSET_LEGACY_LOCAL",
        "work_id": work.id,
        "corpus_name": "legacy-corpus",
        "portable_uri": "local://legacy-corpus/source.txt",
        "relative_path": "source.txt",
        "absolute_path": str(tmp_path / "source.txt"),
        "mime_type": "text/plain",
        "parser_name": "text",
        "parser_fingerprint": "text-parser-v1",
        "byte_sha256": "a" * 64,
        "text_sha256": "b" * 64,
        "byte_size": 14,
        "character_count": 14,
        "chunk_count": 1,
        "normalized_text": "private source",
        "status": "accepted",
        "warnings": [],
    }
    chunk = WorkFeatures(
        work_id=work.id,
        title=work.title,
        model="mock:legacy-chunk",
        principles=[{"id": "P1", "argument": "A migrated chunk remains reusable."}],
    )

    storage.save_source_asset(asset)
    storage.save_source_chunk_extraction(
        asset["id"], 0, chunk.model, "c" * 64, "extractor-v1", chunk
    )
    reopened = WorkspaceStorage(tmp_path)
    reopened.save_source_asset(asset)
    reopened.save_source_chunk_extraction(
        asset["id"], 0, chunk.model, "c" * 64, "extractor-v1", chunk
    )

    with reopened.connect() as conn:
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert {"source_assets", "source_asset_chunks"} <= tables
        assert conn.execute("SELECT COUNT(*) FROM source_assets").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM source_asset_chunks").fetchone()[0] == 1
    loaded_asset = reopened.get_source_asset(asset["id"])
    loaded_chunk = reopened.get_source_chunk_extraction(
        asset["id"], 0, chunk.model, "c" * 64, "extractor-v1"
    )
    assert loaded_asset is not None
    assert loaded_asset["normalized_text"] == "private source"
    assert loaded_chunk is not None
    assert loaded_chunk.principles == chunk.principles


def test_repeated_search_identity_updates_title_only_and_semantic_scholar_records(
    tmp_path: Path,
) -> None:
    storage = WorkspaceStorage(tmp_path)
    title = "Uncertainty Aware Sparse View Dynamic Reconstruction"
    original = storage.save_work(
        WorkItem(
            id="TITLE_ONLY",
            title=title,
            authors=["A. Researcher"],
            year=2025,
            abstract="Short abstract.",
        )
    )
    enriched = storage.save_work(
        WorkItem(
            id="S2_NEW",
            title=title,
            authors=["A. Researcher"],
            year=2026,
            abstract="A much longer abstract with geometric priors and uncertainty calibration.",
            semantic_scholar_id="S2:123",
            pdf_url="https://example.test/paper.pdf",
            source="semantic_scholar",
        )
    )
    repeated = storage.save_work(
        WorkItem(
            id="S2_REPEAT",
            title="Updated title from the provider",
            semantic_scholar_id="S2:123",
            pmid="556677",
            source="semantic_scholar",
        )
    )

    assert enriched.id == original.id
    assert repeated.id == original.id
    assert repeated.semantic_scholar_id == "S2:123"
    assert repeated.pmid == "556677"
    assert repeated.pdf_url == "https://example.test/paper.pdf"
    assert storage.counts()["works"] == 1

    distinct = storage.save_work(
        WorkItem(
            id="DISTINCT",
            title="Updated title from the provider",
            semantic_scholar_id="S2:DIFFERENT",
            pmid="DIFFERENT",
        )
    )
    assert distinct.id == "DISTINCT"
    assert storage.counts()["works"] == 2


def test_extraction_cache_hash_uses_full_content_and_fingerprint(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path)
    work = WorkItem(id="W", title="Cache identity")
    prefix = "x" * 3_000

    first = storage.content_hash(work, prefix + "first tail", "schema-v1")
    changed_tail = storage.content_hash(work, prefix + "second tail", "schema-v1")
    changed_schema = storage.content_hash(work, prefix + "first tail", "schema-v2")

    assert len(first) == 40
    assert len({first, changed_tail, changed_schema}) == 3


def test_title_matching_does_not_merge_ambiguous_strong_identities(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path)
    title = "A deliberately identical but bibliographically ambiguous publication title"
    storage.save_work(WorkItem(id="DOI_A", title=title, doi="10.1000/a", year=2025))
    storage.save_work(WorkItem(id="DOI_B", title=title, doi="10.1000/b", year=2025))
    storage.save_work(WorkItem(id="TITLE_ONLY", title=title, year=2025))

    assert storage.counts()["works"] == 3
