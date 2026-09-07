from __future__ import annotations

import base64
import gzip
import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest

from scripts.check_release_archive import ReleaseArchiveError, verify_release_archives


def test_release_scans_compressed_demo_records_and_embedded_artifacts(tmp_path):
    hidden = ("/" + "Users" + "/real-machine/private.txt").encode()
    payload = gzip.compress(json.dumps({"artifacts": [
        {"path": "receipt.json", "content": base64.b64encode(hidden).decode()}
    ]}).encode())
    wheel, sdist = _write_pair(tmp_path, wheel_files={"principia/demo_projects/public-v142.json.gz": payload})
    with pytest.raises(ReleaseArchiveError, match="machine-local path"):
        verify_release_archives([wheel, sdist])


@pytest.mark.parametrize("member", ["frontend/node_modules/heavy.js", "runtime/data.sqlite", ".secrets/key", "nested/llm-api.env"])
def test_release_archive_refuses_dependency_runtime_and_credential_members(tmp_path, member):
    wheel, sdist = _write_pair(tmp_path, sdist_files={f"principia_ai-1.3.3/{member}": b"fixture"})
    with pytest.raises(ReleaseArchiveError):
        verify_release_archives([wheel, sdist])


def _write_pair(
    root: Path,
    *,
    wheel_files: dict[str, bytes] | None = None,
    sdist_files: dict[str, bytes] | None = None,
) -> tuple[Path, Path]:
    wheel = root / "principia_ai-1.3.3-py3-none-any.whl"
    sdist = root / "principia_ai-1.3.3.tar.gz"
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, payload in (wheel_files or {"principia/__init__.py": b"safe = True\n"}).items():
            archive.writestr(name, payload)
    with tarfile.open(sdist, "w:gz") as archive:
        files = sdist_files or {"principia_ai-1.3.3/README.md": b"# Safe release\n"}
        for name, payload in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    return wheel, sdist


def test_release_archive_scan_accepts_clean_pair_and_synthetic_path_fixture(
    tmp_path: Path,
) -> None:
    synthetic_path = "/" + "Users" + "/alice/negative-fixture.txt"
    wheel, sdist = _write_pair(
        tmp_path,
        sdist_files={
            "principia_ai-1.3.3/README.md": b"# Safe release\n",
            "principia_ai-1.3.3/tests/test_validation_v133.py": synthetic_path.encode(),
        },
    )

    summary = verify_release_archives([sdist, wheel])

    assert summary.archives == (
        "principia_ai-1.3.3-py3-none-any.whl",
        "principia_ai-1.3.3.tar.gz",
    )
    assert summary.members_scanned == 3


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ("".join(("s", "k", "-", "archivecredentialfixture123456")), "credential"),
        ("/" + "Users" + "/real-machine/private.txt", "machine-local path"),
        ("/" + "Users" + "/alice/not-a-test-fixture.txt", "machine-local path"),
        ("LOCAL_ONLY_" + "DO_NOT_UPLOAD", "private sentinel"),
    ],
)
def test_release_archive_scan_rejects_sensitive_content(
    tmp_path: Path, payload: str, message: str
) -> None:
    wheel, sdist = _write_pair(
        tmp_path,
        sdist_files={"principia_ai-1.3.3/README.md": payload.encode()},
    )

    with pytest.raises(ReleaseArchiveError, match=message):
        verify_release_archives([wheel, sdist])


def test_release_archive_scan_rejects_cache_members_and_incomplete_pair(tmp_path: Path) -> None:
    wheel, sdist = _write_pair(
        tmp_path,
        wheel_files={"principia/__pycache__/module.pyc": b"compiled"},
    )
    with pytest.raises(ReleaseArchiveError, match="runtime/cache member"):
        verify_release_archives([wheel, sdist])
    with pytest.raises(ReleaseArchiveError, match="missing principia_ai-1.3.3.tar.gz"):
        verify_release_archives([wheel])


def test_release_archive_scan_accepts_current_version_pair(tmp_path: Path) -> None:
    wheel, sdist = _write_pair(tmp_path)
    current_wheel = wheel.with_name("principia_ai-1.4.0-py3-none-any.whl")
    current_sdist = sdist.with_name("principia_ai-1.4.0.tar.gz")
    wheel.rename(current_wheel)
    sdist.rename(current_sdist)

    summary = verify_release_archives([current_sdist, current_wheel])

    assert summary.archives == (
        "principia_ai-1.4.0-py3-none-any.whl",
        "principia_ai-1.4.0.tar.gz",
    )


def test_release_archive_scan_accepts_admin_package_pair(tmp_path: Path) -> None:
    wheel, sdist = _write_pair(tmp_path)
    admin_wheel = wheel.with_name("principia_admin_local-1.4.2-py3-none-any.whl")
    admin_sdist = sdist.with_name("principia_admin_local-1.4.2.tar.gz")
    wheel.rename(admin_wheel)
    sdist.rename(admin_sdist)

    summary = verify_release_archives([admin_sdist, admin_wheel])

    assert summary.archives == (
        "principia_admin_local-1.4.2-py3-none-any.whl",
        "principia_admin_local-1.4.2.tar.gz",
    )
