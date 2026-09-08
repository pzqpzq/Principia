"""Fail-closed hygiene scan for Principia wheel and source archives.

The scanner reports categories and member names without printing matched
credential text. It rejects runtime caches/workspaces, concrete machine-local
paths, private sentinels outside their sanitizer documentation, and credential
or authorization-token patterns.

Run after the final build::

    python scripts/check_release_archive.py dist/*
"""

from __future__ import annotations

import argparse
import json
import re
import tarfile
import zipfile
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

SCHEMA_VERSION = "principia.release_archive_qa.v1"
EXPECTED_ARCHIVES = frozenset(
    {
        "principia_ai-1.3.3-py3-none-any.whl",
        "principia_ai-1.3.3.tar.gz",
    }
)

_SECRET_RE = re.compile(rb"\bsk-[A-Za-z0-9_-]{16,}\b")
_AUTHORIZATION_RE = re.compile(
    rb"(?i)\bauthorization\s*[:=]\s*[\"']?(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}"
)
_ABSOLUTE_PATH_RE = re.compile(
    r"(?:/(?:Users|home|root|tmp|private|Volumes|mnt)/[^\s'\"<>`|()\[\]{}]+)"
    r"|(?:[A-Za-z]:\\Users\\[^\s'\"<>`|()\[\]{}]+)"
)
_CONCRETE_FILE_URI_RE = re.compile(
    r"(?i)\bfile:///(?:Users|home|root|tmp|private|Volumes|mnt)/"
    r"[^\s'\"<>`|()\[\]{}]+"
)
_PRIVATE_SENTINELS = (
    "LOCAL_ONLY_DO_NOT_UPLOAD",
    "PRIVATE_SENTINEL",
    "BEGIN_PRIVATE_CONTENT",
)
_SENTINEL_REFERENCE_FILES = frozenset(
    {
        "docs/publishing.md",
        "scripts/build_showcases.py",
        "scripts/check_release_archive.py",
    }
)
_ALLOWED_SYNTHETIC_PATH_PREFIXES = (
    "/Users/alice",
    "/Users/example",
    r"C:\Users\alice",
    r"C:\Users\example",
    "file:///Users/alice",
    "file:///Users/example",
    "/private/cache.bin",
    "/private/risk.txt",
)
_SYNTHETIC_PATH_FIXTURE_FILES = frozenset(
    {
        "scripts/check_release_archive.py",
        "tests/test_validation_v133.py",
    }
)
_FORBIDDEN_MEMBER_PARTS = frozenset(
    {
        ".git",
        ".ipynb_checkpoints",
        ".mypy_cache",
        ".principia",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "build",
        "principia_outputs",
    }
)


class ReleaseArchiveError(RuntimeError):
    """Raised when release archives are incomplete or contain unsafe material."""


@dataclass(frozen=True)
class ArchiveScanSummary:
    schema_version: str
    archives: tuple[str, ...]
    members_scanned: int
    text_members_scanned: int
    bytes_scanned: int


@dataclass(frozen=True)
class _Member:
    name: str
    data: bytes


def _logical_path(member_name: str) -> str:
    parts = PurePosixPath(member_name).parts
    if parts and re.fullmatch(r"principia_ai-1\.3\.3", parts[0]):
        parts = parts[1:]
    return "/".join(parts)


def _members(path: Path) -> Iterator[_Member]:
    if path.suffix == ".whl":
        try:
            with zipfile.ZipFile(path) as archive:
                for zip_info in archive.infolist():
                    if not zip_info.is_dir():
                        yield _Member(zip_info.filename, archive.read(zip_info))
        except (OSError, zipfile.BadZipFile) as exc:
            raise ReleaseArchiveError(f"Cannot read wheel {path.name}: {exc}") from exc
        return
    if path.name.endswith(".tar.gz"):
        try:
            with tarfile.open(path, "r:gz") as archive:
                for tar_info in archive.getmembers():
                    if tar_info.issym() or tar_info.islnk():
                        raise ReleaseArchiveError(
                            f"Archive {path.name} contains a link member: {tar_info.name}"
                        )
                    if not tar_info.isfile():
                        continue
                    stream = archive.extractfile(tar_info)
                    if stream is not None:
                        yield _Member(tar_info.name, stream.read())
        except (OSError, tarfile.TarError) as exc:
            raise ReleaseArchiveError(f"Cannot read sdist {path.name}: {exc}") from exc
        return
    raise ReleaseArchiveError(f"Unsupported release archive: {path.name}")


def _unsafe_member_reason(name: str) -> str:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        return "unsafe archive path"
    if any(part in _FORBIDDEN_MEMBER_PARTS for part in path.parts):
        return "runtime/cache member"
    if path.name == ".DS_Store" or path.suffix in {".pyc", ".pyo"}:
        return "runtime/cache member"
    if path.name == "LOCAL_ONLY_DO_NOT_UPLOAD.md":
        return "local-only marker"
    return ""


def _allowed_synthetic_path(value: str, *, logical_path: str) -> bool:
    return logical_path in _SYNTHETIC_PATH_FIXTURE_FILES and value.startswith(
        _ALLOWED_SYNTHETIC_PATH_PREFIXES
    )


def _content_findings(member: _Member) -> list[str]:
    findings: list[str] = []
    if _SECRET_RE.search(member.data):
        findings.append("credential")
    if _AUTHORIZATION_RE.search(member.data):
        findings.append("authorization token")
    try:
        text = member.data.decode("utf-8")
    except UnicodeDecodeError:
        return findings
    logical_path = _logical_path(member.name)
    for pattern in (_ABSOLUTE_PATH_RE, _CONCRETE_FILE_URI_RE):
        if any(
            not _allowed_synthetic_path(match.group(0), logical_path=logical_path)
            for match in pattern.finditer(text)
        ):
            findings.append("machine-local path")
            break
    if logical_path not in _SENTINEL_REFERENCE_FILES and any(
        sentinel in text for sentinel in _PRIVATE_SENTINELS
    ):
        findings.append("private sentinel")
    return findings


def verify_release_archives(paths: Iterable[Path]) -> ArchiveScanSummary:
    """Verify the exact v1.3.3 wheel/sdist pair and return scan counts."""

    archives = tuple(sorted((Path(path).resolve() for path in paths), key=lambda item: item.name))
    names = {path.name for path in archives}
    if names != EXPECTED_ARCHIVES or len(archives) != 2:
        missing = sorted(EXPECTED_ARCHIVES - names)
        unexpected = sorted(names - EXPECTED_ARCHIVES)
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if unexpected:
            details.append("unexpected " + ", ".join(unexpected))
        raise ReleaseArchiveError("Release archive pair is invalid: " + "; ".join(details))
    if any(not path.is_file() for path in archives):
        raise ReleaseArchiveError("A required release archive does not exist.")

    member_count = 0
    text_count = 0
    byte_count = 0
    findings: list[str] = []
    for archive in archives:
        for member in _members(archive):
            member_count += 1
            byte_count += len(member.data)
            try:
                member.data.decode("utf-8")
            except UnicodeDecodeError:
                pass
            else:
                text_count += 1
            member_reason = _unsafe_member_reason(member.name)
            if member_reason:
                findings.append(f"{archive.name}:{member.name}: {member_reason}")
            for reason in _content_findings(member):
                findings.append(f"{archive.name}:{member.name}: {reason}")
    if findings:
        raise ReleaseArchiveError(
            "Release archive hygiene scan failed:\n" + "\n".join(sorted(set(findings)))
        )
    return ArchiveScanSummary(
        schema_version=SCHEMA_VERSION,
        archives=tuple(path.name for path in archives),
        members_scanned=member_count,
        text_members_scanned=text_count,
        bytes_scanned=byte_count,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", nargs="+", type=Path)
    parser.add_argument("--report-json", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    summary = verify_release_archives(args.archives)
    payload = asdict(summary)
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
