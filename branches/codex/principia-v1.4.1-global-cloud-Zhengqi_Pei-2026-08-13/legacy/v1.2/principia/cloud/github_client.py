from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from typing import Any
from pathlib import Path

from .compactor import compact_contributions
from .ids import sha256_hex
from .manifest import write_pointer


def pr_export_instructions(contribution_path: str) -> dict[str, Any]:
    return {
        "mode": "pr_export",
        "contribution_path": contribution_path,
        "safe_default": True,
        "instructions": [
            "Create a branch in the GitHub repository.",
            "Add the contribution file under cloud/contributions/ or attach it to the maintainer workflow.",
            "Open a pull request against main.",
            "Wait for principia-cloud-validate to pass before merge.",
        ],
    }


def maintainer_direct_push(
    contribution_path: str,
    repo_root: Path,
    *,
    branch: str = "",
    remote: str = "origin",
    base_branch: str = "main",
    push: bool = True,
) -> dict[str, Any]:
    source = _resolve_contribution_path(contribution_path, repo_root)
    if not source.exists():
        return {"ok": False, "mode": "maintainer_direct_push", "error": f"Contribution file not found: {source}"}
    if source.suffix.lower() != ".json":
        return {"ok": False, "mode": "maintainer_direct_push", "error": "Contribution file must be a JSON file."}

    branch = branch.strip() or f"codex/cloud-contribution-{_safe_branch_part(source.stem)}"
    worktree_root = Path(tempfile.mkdtemp(prefix="principia-cloud-push-"))
    worktree_path = worktree_root / _safe_branch_part(branch)
    target_rel = Path("cloud") / "contributions" / source.name
    commands: list[dict[str, Any]] = []

    def git(cwd: Path, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        commands.append(
            {
                "cwd": str(cwd),
                "args": ["git", *args],
                "returncode": completed.returncode,
                "stdout": completed.stdout[-2000:],
                "stderr": completed.stderr[-2000:],
            }
        )
        if check and completed.returncode != 0:
            raise RuntimeError((completed.stderr or completed.stdout or "git command failed").strip())
        return completed

    try:
        git(repo_root, ["fetch", remote, base_branch], check=False)
        if worktree_path.exists():
            shutil.rmtree(worktree_path)
        base_ref = f"{remote}/{base_branch}"
        add = git(repo_root, ["worktree", "add", "--detach", str(worktree_path), base_ref], check=False)
        if add.returncode != 0:
            git(repo_root, ["worktree", "add", "--detach", str(worktree_path), base_branch])
        git(worktree_path, ["checkout", "-B", branch])
        target = worktree_path / target_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        git(worktree_path, ["add", str(target_rel)])
        status = git(worktree_path, ["status", "--porcelain", "--", str(target_rel)]).stdout.strip()
        if not status:
            return {
                "ok": True,
                "mode": "maintainer_direct_push",
                "branch": branch,
                "pushed": False,
                "message": "Contribution already exists with identical content.",
                "commands": commands,
            }
        git(worktree_path, ["commit", "-m", f"Add Principia cloud contribution {source.stem}"])
        commit = git(worktree_path, ["rev-parse", "HEAD"]).stdout.strip()
        if push:
            git(worktree_path, ["push", "-u", remote, f"HEAD:{branch}"])
        return {
            "ok": True,
            "mode": "maintainer_direct_push",
            "branch": branch,
            "remote": remote,
            "base_branch": base_branch,
            "pushed": bool(push),
            "commit": commit,
            "target_path": str(target_rel),
            "commands": commands,
        }
    except Exception as exc:
        return {
            "ok": False,
            "mode": "maintainer_direct_push",
            "branch": branch,
            "remote": remote,
            "base_branch": base_branch,
            "pushed": False,
            "error": str(exc),
            "commands": commands,
        }
    finally:
        if worktree_path.exists():
            git(repo_root, ["worktree", "remove", "--force", str(worktree_path)], check=False)
        if worktree_root.exists():
            shutil.rmtree(worktree_root, ignore_errors=True)


def publish_cloud_contribution(
    contribution_path: str,
    repo_root: Path,
    *,
    direct_push: dict[str, Any] | None = None,
    branch: str = "",
    remote: str = "origin",
    base_branch: str = "main",
    trigger_workflow: bool = True,
    local_snapshot: bool = True,
) -> dict[str, Any]:
    """Make a submitted contribution readable through the cloud manifest path.

    The GitHub-native path is a release workflow. The local snapshot path uses
    the same immutable pack/index format so the UI does not fall back to local
    source-table search while the remote release is still publishing.
    """
    source = _resolve_contribution_path(contribution_path, repo_root)
    if not source.exists():
        return {"ok": False, "mode": "cloud_publish", "error": f"Contribution file not found: {source}"}
    branch = branch.strip() or str((direct_push or {}).get("branch") or base_branch or "main")
    commit = str((direct_push or {}).get("commit") or "").strip()
    push_trigger_branch = branch in {"main", "master"} or branch.startswith("codex/cloud-contribution-")
    release_tag = f"principia-cloud-{commit[:12]}" if push_trigger_branch and commit else f"principia-cloud-{int(time.time())}-{_safe_branch_part(source.stem)[:32]}"
    result: dict[str, Any] = {
        "ok": False,
        "mode": "cloud_publish",
        "contribution_path": str(source),
        "branch": branch,
        "remote": remote,
        "release_tag": release_tag,
        "available_for_search": False,
    }
    if local_snapshot:
        result["local_snapshot"] = _publish_local_snapshot(source, repo_root)
        result["available_for_search"] = bool(result["local_snapshot"].get("ok"))
    if trigger_workflow:
        result["github_release"] = trigger_cloud_release_workflow(
            repo_root,
            branch=branch,
            tag=release_tag,
            remote=remote,
            source="contributions",
            input_dir="cloud/contributions",
        )
    else:
        result["github_release"] = {"ok": False, "skipped": True, "reason": "workflow trigger disabled"}
    direct_ok = not direct_push or bool(direct_push.get("ok"))
    workflow_ok = bool((result.get("github_release") or {}).get("ok")) or bool((result.get("github_release") or {}).get("will_run_on_push"))
    result["ok"] = bool(direct_ok and (result["available_for_search"] or workflow_ok))
    if result["available_for_search"]:
        result["message"] = "Contribution was compacted into the cloud manifest/index format and is searchable now."
    elif workflow_ok:
        result["message"] = "Contribution was pushed; GitHub Actions is expected to publish the cloud release."
    else:
        result["message"] = "Contribution was pushed, but no searchable cloud snapshot was published."
    return result


def trigger_cloud_release_workflow(
    repo_root: Path,
    *,
    branch: str,
    tag: str,
    remote: str = "origin",
    source: str = "contributions",
    input_dir: str = "cloud/contributions",
) -> dict[str, Any]:
    workflow = "principia-cloud-release.yml"
    repo_slug = _remote_repo_slug(repo_root, remote=remote)
    will_run_on_push = branch in {"main", "master"} or branch.startswith("codex/cloud-contribution-")
    release_url = f"https://github.com/{repo_slug}/releases/tag/{tag}" if repo_slug else ""
    if will_run_on_push:
        return {
            "ok": False,
            "mode": "push_trigger",
            "workflow": workflow,
            "branch": branch,
            "tag": tag,
            "repo": repo_slug,
            "release_url": release_url,
            "will_run_on_push": True,
            "reason": "Release workflow is configured to run from this contribution push.",
        }
    gh = shutil.which("gh")
    if gh:
        args = [
            gh,
            "workflow",
            "run",
            workflow,
            "--ref",
            branch,
            "-f",
            f"tag={tag}",
            "-f",
            f"source={source}",
            "-f",
            f"input_dir={input_dir}",
        ]
        completed = subprocess.run(args, cwd=str(repo_root), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        return {
            "ok": completed.returncode == 0,
            "mode": "gh_workflow_dispatch",
            "workflow": workflow,
            "branch": branch,
            "tag": tag,
            "repo": repo_slug,
            "stdout": completed.stdout[-2000:],
            "stderr": completed.stderr[-2000:],
            "returncode": completed.returncode,
        }
    return {
        "ok": False,
        "mode": "not_triggered",
        "workflow": workflow,
        "branch": branch,
        "tag": tag,
        "repo": repo_slug,
        "release_url": release_url,
        "will_run_on_push": False,
        "reason": "gh CLI is not installed and this branch is not configured for push-triggered release.",
    }


def _resolve_contribution_path(value: str, repo_root: Path) -> Path:
    path = Path(str(value or "")).expanduser()
    return path if path.is_absolute() else repo_root / path


def _publish_local_snapshot(source: Path, repo_root: Path) -> dict[str, Any]:
    out_dir = repo_root / "dist" / "cloud-live"
    pointer_path = repo_root / "cloud" / "manifests" / "latest.json"
    with tempfile.TemporaryDirectory(prefix="principia-cloud-compact-") as tmp:
        input_dir = Path(tmp) / "contributions"
        input_dir.mkdir(parents=True, exist_ok=True)
        for existing_dir in (
            repo_root / "cloud" / "contributions",
            repo_root / "data" / "artifacts" / "cloud" / "contributions",
        ):
            if not existing_dir.exists():
                continue
            for path in sorted(existing_dir.glob("CONTRIB-*.json")):
                if not _contribution_has_work_records(path):
                    continue
                shutil.copyfile(path, input_dir / path.name)
        if not _contribution_has_work_records(source):
            return {"ok": False, "out_dir": str(out_dir), "error": "Contribution has no work records.", "contribution_path": str(source)}
        shutil.copyfile(source, input_dir / source.name)
        report = compact_contributions(input_dir, out_dir)
    if not report.get("ok"):
        return {"ok": False, "out_dir": str(out_dir), "report": report}
    manifest_path = out_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    pointer = write_pointer(pointer_path, manifest_path, manifest)
    return {
        "ok": True,
        "out_dir": str(out_dir),
        "manifest_path": str(manifest_path),
        "pointer_path": str(pointer_path),
        "snapshot_id": manifest.get("snapshot_id", ""),
        "counts": manifest.get("counts", {}),
        "pointer_sha256": sha256_hex(json.dumps(pointer, sort_keys=True).encode("utf-8")),
        "report": report,
    }


def _remote_repo_slug(repo_root: Path, *, remote: str = "origin") -> str:
    completed = subprocess.run(
        ["git", "config", "--get", f"remote.{remote}.url"],
        cwd=str(repo_root),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    raw = completed.stdout.strip()
    if not raw:
        return os.getenv("GITHUB_REPOSITORY", "").strip()
    if raw.startswith("git@github.com:"):
        raw = raw.removeprefix("git@github.com:")
    elif raw.startswith("https://github.com/"):
        raw = raw.removeprefix("https://github.com/")
    raw = raw.removesuffix(".git").strip("/")
    return raw if "/" in raw else ""


def _contribution_has_work_records(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    records = data.get("work_records")
    return isinstance(records, list) and bool(records)


def _safe_branch_part(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in str(value or "").strip())
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return (cleaned or "contribution")[:80]
