from __future__ import annotations

import importlib.util
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest


def script(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[1] / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_clean_release_excludes_history_dependencies_credentials_and_symlinks(tmp_path):
    source = tmp_path / "old"
    keep = "core-v1.4.2/src/principia/ui_dist/index.html"
    for name in (keep, "core-v1.4.2/frontend/node_modules/heavy.js", "runtime/history.sqlite",
                 "evaluation/private.json", "core-v1.4.2/.venv/bin/python",
                 "core-v1.4.2/src/nested/llm-api.env", "core-v1.4.2/src/nested/.secrets/key",
                 "core-v1.4.2/src/nested/__pycache__/bad.pyc"):
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture")
    (source / "core-v1.4.2/src/external").symlink_to(tmp_path, target_is_directory=True)
    destination = tmp_path / "new"
    result = script("build_clean_release").build_clean_release(source, destination)
    assert result["source_bytes"] == len("fixture")
    assert (destination / keep).read_text() == "fixture"
    assert not (destination / "runtime").exists()
    assert not (destination / "core-v1.4.2/src/nested").exists()
    assert not (destination / "core-v1.4.2/src/external").exists()
    assert result["initial_projects"] == 0
    with pytest.raises(ValueError, match="empty"):
        script("build_clean_release").build_clean_release(source, destination)


def test_clean_release_omits_expanded_public_cloud_cache(tmp_path):
    tool = script("build_clean_release")
    assert not tool.allowed(Path("core-v1.4.2/global-cloud/global-v1/releases/id/cloud.sqlite"))
    assert not tool.allowed(Path("core-v1.4.2/global-cloud/registry.sqlite"))
    assert tool.allowed(Path("core-v1.4.2/global-cloud/data/v2/principles/ab.jsonl"))
    assert tool.allowed(Path("core-v1.4.2/src/principia/demo_projects/knowledge.pcg"))


def test_release_size_gate_leaves_destination_empty(tmp_path):
    source = tmp_path / "old"
    file = source / "core-v1.4.2/src/principia/ui_dist/index.html"
    file.parent.mkdir(parents=True)
    file.write_bytes(b"x" * 1024)
    with pytest.raises(ValueError, match="size budget"):
        script("build_clean_release").build_clean_release(source, tmp_path / "new", maximum_bytes=512)
    assert not (tmp_path / "new").exists()


def test_verified_archive_preserves_evidence_and_does_not_follow_symlinks(tmp_path):
    source = tmp_path / "runtime/test-workspace"
    source.mkdir(parents=True)
    (source / "negative-evidence.json").write_bytes(b"negative evidence" * 10000)
    external = tmp_path / "raw.csv"
    external.write_text("raw input")
    (source / "raw-link").symlink_to(external)
    tool = script("archive_runtime")
    entries = tool.snapshot(source)
    archive = tmp_path / "runtime/archives/test.tar.gz"
    result = tool.archive_runtime(source, archive, remove_verified=True)
    tool.verify(archive, entries)
    assert result["archive_bytes"] < result["source_bytes"] / 10
    assert not source.exists()
    assert external.read_text() == "raw input"


def test_failed_verification_retains_originals(tmp_path, monkeypatch):
    source = tmp_path / "runtime/test-workspace"
    source.mkdir(parents=True)
    evidence = source / "result.json"
    evidence.write_text("evidence")
    tool = script("archive_runtime")
    def fail(*args):
        raise ValueError("verification failed")
    monkeypatch.setattr(tool, "verify", fail)
    with pytest.raises(ValueError, match="verification failed"):
        tool.archive_runtime(source, tmp_path / "history.tar.gz", remove_verified=True)
    assert evidence.read_text() == "evidence"


def test_archive_refuses_credentials_and_nonruntime_roots(tmp_path):
    tool = script("archive_runtime")
    source = tmp_path / "runtime/test-workspace"
    source.mkdir(parents=True)
    (source / "llm-api.env").write_text("fixture")
    with pytest.raises(ValueError, match="Credential"):
        tool.archive_runtime(source, tmp_path / "history.tar.gz", remove_verified=True)
    assert source.exists()
    with pytest.raises(ValueError, match="runtime"):
        tool.archive_runtime(tmp_path / "evaluation", tmp_path / "history.tar.gz")


def test_archive_can_preserve_credentials_in_place_without_archiving_them(tmp_path):
    source = tmp_path / "runtime/test-workspace"
    secret = source / "workspace/.principia/secrets/fixture"
    secret.parent.mkdir(parents=True)
    secret.write_text("credential fixture")
    evidence = source / "evidence.json"
    evidence.write_text("scientific result")
    tool = script("archive_runtime")
    archive = tmp_path / "history.tar.gz"
    result = tool.archive_runtime(source, archive, remove_verified=True, preserve_credentials=True)
    assert result["credentials_left_in_place"]
    assert secret.read_text() == "credential fixture"
    assert not evidence.exists()
    import json
    manifest = json.loads(archive.with_suffix(".gz.manifest.json").read_text())
    assert not any("secrets" in name for name in manifest["entries"])


def test_archive_handles_sqlite_wal_bookkeeping_and_restorable_records(tmp_path):
    source = tmp_path / "runtime/old-test"
    source.mkdir(parents=True)
    with closing(sqlite3.connect(source / "principia.sqlite")) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE evidence(value TEXT)")
        conn.execute("INSERT INTO evidence VALUES('preserved')")
        conn.commit()
    tool = script("archive_runtime")
    archive = tmp_path / "old.tar.gz"
    tool.archive_runtime(source, archive, remove_verified=True)
    import tarfile
    restored = tmp_path / "restored"
    restored.mkdir()
    with tarfile.open(archive) as bundle:
        bundle.extractall(restored, filter="data")
    with closing(sqlite3.connect(restored / "principia.sqlite")) as conn:
        assert conn.execute("SELECT value FROM evidence").fetchall() == [("preserved",)]
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
