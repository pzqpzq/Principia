from __future__ import annotations

from pathlib import Path
from typing import Any

import principia as pc
from principia.ids import normalize_key, readable_id
from principia.models import WorkItem


def test_readable_id_is_human_readable_and_collision_safe() -> None:
    first = readable_id("Cooperation Without Governance Risks Manipulative Equilibria")
    second = readable_id("Cooperation Without Governance Risks Manipulative Equilibria", existing={first})

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


def test_save_work_recovers_arxiv_unique_conflict_after_stale_lookup(tmp_path: Path, monkeypatch: Any) -> None:
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
