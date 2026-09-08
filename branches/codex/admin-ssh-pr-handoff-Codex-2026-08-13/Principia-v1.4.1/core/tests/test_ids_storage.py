from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

import principia as pc
from principia.ids import normalize_key, readable_id
from principia.models import WorkItem

IDENTITY_INDEXES = (
    "idx_works_doi",
    "idx_works_arxiv",
    "idx_works_openalex",
    "idx_works_semantic_scholar",
    "idx_works_pmid",
)


def insert_legacy_work(
    conn: sqlite3.Connection,
    work: WorkItem,
    identities: dict[str, str],
) -> None:
    payload = work.model_dump()
    payload.update(identities)
    conn.execute(
        """
        INSERT INTO works(
            id, title_norm, title_hash, doi, arxiv_id, openalex_id,
            semantic_scholar_id, pmid, abstract_hash, payload_json, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            work.id,
            normalize_key(work.title),
            f"TITLE-{work.id}",
            identities.get("doi", ""),
            identities.get("arxiv_id", ""),
            identities.get("openalex_id", ""),
            identities.get("semantic_scholar_id", ""),
            identities.get("pmid", ""),
            f"ABSTRACT-{work.id}",
            json.dumps(payload),
            work.created_at,
            work.updated_at,
        ),
    )


def test_readable_id_is_human_readable_and_collision_safe() -> None:
    first = readable_id("Cooperation Without Governance Risks Manipulative Equilibria")
    second = readable_id(
        "Cooperation Without Governance Risks Manipulative Equilibria", existing={first}
    )

    assert first == "Cooperation_Without_Governance_Risks_Manipulative_Equilibria"
    assert second.startswith(first[:50])
    assert second != first
    assert len(second) <= 96


def test_workspace_layout_and_sqlite_counts(tmp_path: Path) -> None:
    ws = pc.Workspace(tmp_path, llm=pc.MockLLMClient())

    assert ws.db_path.exists()
    assert (tmp_path / ".principia" / "artifacts" / "pdfs").is_dir()
    assert ws.counts()["works"] == 0

    ws.storage.save_work(
        WorkItem(
            id=readable_id("A source work"),
            title="A source work",
            abstract="A compact abstract about routing and validation.",
        )
    )

    assert ws.counts()["works"] == 1
    assert normalize_key("A Source Work") == "a source work"


def test_noop_workspace_reopen_preserves_checkpointed_database_bytes_and_rows(
    tmp_path: Path,
) -> None:
    workspace = pc.Workspace(tmp_path, llm=pc.MockLLMClient())
    workspace.storage.save_work(
        WorkItem(
            id="STABLE_WORK",
            title="A physically stable stored work",
            authors=["Ada Example"],
            abstract="This row is already canonical and must not be rewritten.",
            doi="10.5555/principia.stable",
            arxiv_id="2601.12345",
        )
    )
    db_path = workspace.db_path

    def checkpointed_snapshot() -> tuple[str, dict[str, list[tuple[Any, ...]]]]:
        with sqlite3.connect(db_path) as conn:
            assert conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone() == (0, 0, 0)
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            logical_rows = {
                table: conn.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
                for table in (
                    "works",
                    "works_fts",
                    "source_assets",
                    "source_asset_chunks",
                    "extractions",
                    "ideas",
                    "comparisons",
                    "runs",
                    "run_events",
                )
            }
        return hashlib.sha256(db_path.read_bytes()).hexdigest(), logical_rows

    before_hash, before_rows = checkpointed_snapshot()
    pc.Workspace(tmp_path, llm=pc.MockLLMClient())
    after_hash, after_rows = checkpointed_snapshot()

    assert after_rows == before_rows
    assert after_hash == before_hash


def test_explicit_model_resolution_preserves_workspace_llm_options() -> None:
    config = pc.LLMConfig.from_model(
        "siliconflow:Qwen/Qwen3.5-397B-A17B",
        api_key="test-key",
        base_url="https://example.test/v1",
        timeout=420,
        max_retries=1,
    )
    client = pc.LLMClient(config)

    resolved = client.resolve("siliconflow:deepseek-ai/DeepSeek-V4-Pro")

    assert resolved.model == "deepseek-ai/DeepSeek-V4-Pro"
    assert resolved.api_key == "test-key"
    assert resolved.base_url == "https://example.test/v1"
    assert resolved.timeout == 420
    assert resolved.max_retries == 1


def test_public_siliconflow_config_and_notebook_progress_helpers() -> None:
    config = pc.siliconflow_config("test-key", timeout=420)
    progress = pc.notebook_progress()
    status = pc.RunStatus(
        run_id="RUN_TEST",
        operation="research.search",
        stage="source_search",
        progress=0.25,
        message="Searching sources.",
        counts={"target_count": 50},
        elapsed_seconds=5,
        eta_seconds=15,
    )

    assert config.provider == "siliconflow"
    assert config.api_key == "test-key"
    assert config.timeout == 420
    rendered = progress.render_status(status)
    assert "research.search" in rendered
    assert "ETA" in rendered
    assert "15s" in rendered


def test_siliconflow_config_rejects_placeholder_key() -> None:
    try:
        pc.siliconflow_config("YOUR_SILICONFLOW_API_KEY")
    except ValueError as exc:
        assert "Set API_key" in str(exc)
    else:
        raise AssertionError("placeholder API key should be rejected")


def test_save_work_merges_duplicate_source_identity(tmp_path: Path) -> None:
    ws = pc.Workspace(tmp_path, llm=pc.MockLLMClient())
    first = WorkItem(
        id="First_Id",
        title="Repository coding agent benchmark",
        arxiv_id="2601.12345",
    )
    duplicate = WorkItem(
        id="Second_Id",
        title="Repository coding agent benchmark revised",
        arxiv_id="2601.12345",
    )

    saved_first = ws.storage.save_work(first)
    saved_duplicate = ws.storage.save_work(duplicate)

    assert saved_duplicate.id == saved_first.id
    assert ws.counts()["works"] == 1


def test_work_item_and_storage_canonicalize_doi_and_arxiv_forms(tmp_path: Path) -> None:
    ws = pc.Workspace(tmp_path, llm=pc.MockLLMClient())
    first = WorkItem(
        id="CANONICAL",
        title="Canonical provider identities",
        doi="HTTPS://DX.DOI.ORG/10.5555/Principia.Identity",
        arxiv_id="https://arxiv.org/pdf/2601.12345v3.pdf?download=1",
        openalex_id="https://openalex.org/W123456789",
    )

    assert first.doi == "10.5555/principia.identity"
    assert first.arxiv_id == "2601.12345"
    assert first.openalex_id == "W123456789"
    saved = ws.storage.save_work(first)
    repeated = ws.storage.save_work(
        WorkItem(
            id="REPEATED",
            title="Canonical provider identities revised",
            doi="doi: 10.5555/PRINCIPIA.IDENTITY",
            arxiv_id="arXiv:2601.12345v9",
        )
    )

    assert repeated.id == saved.id
    assert repeated.doi == "10.5555/principia.identity"
    assert repeated.arxiv_id == "2601.12345"
    assert ws.counts()["works"] == 1


def test_identity_migration_reconciles_formats_and_moves_extraction_payload(tmp_path: Path) -> None:
    ws = pc.Workspace(tmp_path, llm=pc.MockLLMClient())
    peer = WorkItem(
        id="PEER",
        title="A migrated publication",
        abstract="The complete peer-reviewed abstract.",
        source="crossref",
        venue="Journal of Migration Safety",
        metadata={"is_peer_reviewed": True},
    )
    preprint = WorkItem(
        id="PREPRINT",
        title="A migrated publication preprint",
        source="arxiv",
        venue="arXiv",
    )
    with ws.storage.connect() as conn:
        for index_name in IDENTITY_INDEXES:
            conn.execute(f"DROP INDEX IF EXISTS {index_name}")
        insert_legacy_work(
            conn,
            peer,
            {
                "doi": "HTTPS://DOI.ORG/10.5555/Migration.Identity",
                "arxiv_id": "https://arxiv.org/abs/2601.54321v2",
                "openalex_id": "https://openalex.org/W987654321",
                "semantic_scholar_id": "S2-MIGRATED",
                "pmid": "445566",
            },
        )
        insert_legacy_work(
            conn,
            preprint,
            {
                "doi": "doi:10.5555/migration.identity",
                "arxiv_id": "arXiv:2601.54321v5",
                "openalex_id": "w987654321",
                "semantic_scholar_id": "S2-MIGRATED",
                "pmid": "445566",
            },
        )
        features = pc.WorkFeatures(
            work_id=preprint.id,
            title=preprint.title,
            model="mock",
            ideas=[{"title": "Migrated extraction"}],
            extraction_id="EXT-MIGRATED",
        )
        conn.execute(
            """
            INSERT INTO extractions(
                id, work_id, model, content_hash, payload_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                features.extraction_id,
                features.work_id,
                features.model,
                "legacy-content",
                features.model_dump_json(),
                features.created_at,
                features.created_at,
            ),
        )

    migrated = pc.Workspace(tmp_path, llm=pc.MockLLMClient()).storage
    # A second open verifies the migration and all index creation are idempotent.
    pc.Workspace(tmp_path, llm=pc.MockLLMClient())
    loaded = migrated.get_work(peer.id)
    assert loaded is not None
    assert loaded.doi == "10.5555/migration.identity"
    assert loaded.arxiv_id == "2601.54321"
    assert loaded.openalex_id == "W987654321"
    assert loaded.semantic_scholar_id == "S2-MIGRATED"
    assert loaded.pmid == "445566"
    assert migrated.counts()["works"] == 1
    extraction = migrated.latest_extraction_for_work(peer.id)
    assert extraction is not None
    assert extraction.work_id == peer.id
    with migrated.connect() as conn:
        indexes = {row["name"] for row in conn.execute("PRAGMA index_list(works)")}
    assert set(IDENTITY_INDEXES) <= indexes


def test_openalex_migration_preserves_rows_with_conflicting_strong_ids(tmp_path: Path) -> None:
    ws = pc.Workspace(tmp_path, llm=pc.MockLLMClient())
    first = WorkItem(
        id="DISTINCT_A",
        title="Known distinct publication A",
        source="crossref",
        metadata={"is_peer_reviewed": True},
    )
    second = WorkItem(id="DISTINCT_B", title="Known distinct publication B", source="openalex")
    with ws.storage.connect() as conn:
        for index_name in IDENTITY_INDEXES:
            conn.execute(f"DROP INDEX IF EXISTS {index_name}")
        insert_legacy_work(
            conn,
            first,
            {"doi": "10.5555/distinct-a", "openalex_id": "https://openalex.org/W111"},
        )
        insert_legacy_work(
            conn,
            second,
            {"doi": "10.5555/distinct-b", "openalex_id": "w111"},
        )

    migrated = pc.Workspace(tmp_path, llm=pc.MockLLMClient()).storage
    reopened = pc.Workspace(tmp_path, llm=pc.MockLLMClient()).storage
    works = {work.id: work for work in reopened.list_works()}

    assert migrated.counts()["works"] == 2
    assert set(works) == {first.id, second.id}
    assert works[first.id].openalex_id == "W111"
    assert works[second.id].openalex_id == ""
    assert works[first.id].doi == "10.5555/distinct-a"
    assert works[second.id].doi == "10.5555/distinct-b"
    assert works[second.id].metadata["identity_migration_warnings"]
    with reopened.connect() as conn:
        indexes = {row["name"] for row in conn.execute("PRAGMA index_list(works)")}
    assert "idx_works_openalex" in indexes


def test_save_work_recovers_arxiv_unique_conflict_after_stale_lookup(
    tmp_path: Path, monkeypatch: Any
) -> None:
    ws = pc.Workspace(tmp_path, llm=pc.MockLLMClient())
    first = ws.storage.save_work(
        WorkItem(
            id="First_Id",
            title="Repository coding agent benchmark",
            arxiv_id="2601.12345",
        )
    )
    original_lookup = ws.storage._existing_work_ids_for_identity
    stale_misses = 2

    def flaky_lookup(conn: Any, work: WorkItem) -> list[str]:
        nonlocal stale_misses
        if work.id == "Second_Id" and stale_misses > 0:
            stale_misses -= 1
            return []
        return original_lookup(conn, work)

    monkeypatch.setattr(ws.storage, "_existing_work_ids_for_identity", flaky_lookup)

    duplicate = ws.storage.save_work(
        WorkItem(
            id="Second_Id",
            title="Repository coding agent benchmark revised",
            arxiv_id="2601.12345",
        )
    )

    assert duplicate.id == first.id
    assert ws.counts()["works"] == 1


def test_save_work_merges_existing_doi_and_arxiv_rows_without_unique_error(tmp_path: Path) -> None:
    ws = pc.Workspace(tmp_path, llm=pc.MockLLMClient())
    peer = ws.storage.save_work(
        WorkItem(
            id="Peer_Row",
            title="Repository Aware Quality Control for Coding Agents",
            venue="International Conference on Software Engineering",
            source="crossref",
            doi="10.1145/principia.peer",
            metadata={"is_peer_reviewed": True},
        )
    )
    arxiv = ws.storage.save_work(
        WorkItem(
            id="Arxiv_Row",
            title="Repository Aware Quality Control for Coding Agents preprint",
            venue="arXiv",
            source="arxiv",
            arxiv_id="2601.12345",
            metadata={"is_preprint": True},
        )
    )
    ws.storage.save_extraction(
        pc.WorkFeatures(
            work_id=arxiv.id,
            title=arxiv.title,
            model="mock",
            ideas=[{"title": "Prior idea", "core_idea": "Use quality gates."}],
            extraction_id="EXT_ARXIV",
        ),
        "content-hash",
    )

    saved = ws.storage.save_work(
        WorkItem(
            id="Merged_Row",
            title="Repository Aware Quality Control for Coding Agents",
            venue="International Conference on Software Engineering",
            source="crossref",
            doi="10.1145/principia.peer",
            arxiv_id="2601.12345",
            metadata={"is_peer_reviewed": True, "has_preprint": True},
        )
    )

    assert saved.id == peer.id
    assert saved.doi == "10.1145/principia.peer"
    assert saved.arxiv_id == "2601.12345"
    assert ws.counts()["works"] == 1
    moved = ws.storage.latest_extraction_for_work(saved.id)
    assert moved is not None
    assert moved.ideas[0]["core_idea"] == "Use quality gates."
