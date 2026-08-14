from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

_REPOSITORY = "pzqpzq/Principia"
_KEYCHAIN_SERVICE = "Principia Global Cloud GitHub"
_TOKEN_PATTERN = re.compile(r"^(?:github_pat_|ghp_)[A-Za-z0-9_]{20,}$")
_SSH_KEY_CANDIDATES = (
    Path.home() / ".ssh" / "id_ed25519_principia_github",
    Path.home() / ".ssh" / "principia_github_v1_release_ed25519",
)


class GitHubPublicationError(RuntimeError):
    pass


@dataclass(frozen=True)
class GitHubPublicationAdapter:
    """Repository-restricted publisher using Keychain PAT or the Principia SSH key."""

    repository: str = _REPOSITORY

    def _token(self) -> str:
        if os.name != "posix" or not __import__("sys").platform.startswith("darwin"):
            raise GitHubPublicationError("GitHub publication requires the macOS Keychain")
        result = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-s",
                _KEYCHAIN_SERVICE,
                "-a",
                self.repository,
                "-w",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        token = result.stdout.strip()
        if result.returncode != 0 or not _TOKEN_PATTERN.fullmatch(token):
            raise GitHubPublicationError("a valid fine-grained GitHub credential is not configured")
        return token

    def configured(self) -> bool:
        try:
            self._token()
            return True
        except GitHubPublicationError:
            return self._ssh_key() is not None

    def credential_mode(self) -> str:
        try:
            self._token()
            return "keychain"
        except GitHubPublicationError:
            return "ssh" if self._ssh_key() is not None else ""

    def _ssh_key(self) -> Path | None:
        configured = os.getenv("PRINCIPIA_GITHUB_SSH_KEY", "").strip()
        candidates = ([Path(configured).expanduser()] if configured else []) + list(
            _SSH_KEY_CANDIDATES
        )
        for candidate in candidates:
            try:
                if candidate.is_file() and candidate.stat().st_mode & 0o077 == 0:
                    return candidate.resolve()
            except OSError:
                continue
        return None

    def _public_request(self, path: str) -> Any:
        # Public status polling bypasses ambient HTTP proxies. Shared proxy
        # egress can exhaust GitHub's anonymous rate limit for unrelated users,
        # while direct requests retain the machine's own allowance.
        with httpx.Client(trust_env=False, timeout=30, follow_redirects=False) as client:
            response = client.get(
                "https://api.github.com" + path,
                headers={
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": "Principia/1.4.1 Global Cloud Publisher",
                },
            )
        if response.status_code >= 400:
            raise GitHubPublicationError(
                f"GitHub API rejected the status request ({response.status_code})"
            )
        return response.json()

    def _ssh_command(self, key: Path) -> str:
        return f"ssh -i {key} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"

    def create_review_branch_ssh(
        self,
        *,
        branch: str,
        base: str,
        files: dict[str, bytes],
        message: str,
    ) -> dict[str, Any]:
        """Commit reviewed canonical records and push a protected publication branch.

        The private key path is never written into the clone, logs, durable
        state, or command arguments visible to the UI.  The clone is deleted
        immediately after the push.
        """

        if not branch.startswith("principia-cloud/"):
            raise GitHubPublicationError("publication branches must use principia-cloud/*")
        if not files or any(
            not path.startswith("global-cloud/") or ".." in path.split("/") for path in files
        ):
            raise GitHubPublicationError("publication commits must affect only global-cloud/**")
        key = self._ssh_key()
        if key is None:
            raise GitHubPublicationError("the Principia GitHub SSH key is not configured")
        git = shutil.which("git")
        if git is None:
            raise GitHubPublicationError("git is unavailable")
        env = {
            **os.environ,
            "GIT_SSH_COMMAND": self._ssh_command(key),
            "GIT_TERMINAL_PROMPT": "0",
        }
        with tempfile.TemporaryDirectory(prefix="principia-cloud-publish.") as temporary:
            root = Path(temporary) / "repository"

            def run(*arguments: str) -> subprocess.CompletedProcess[str]:
                result = subprocess.run(
                    [git, *arguments],
                    cwd=root if root.exists() else None,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=False,
                )
                if result.returncode != 0:
                    raise GitHubPublicationError("the checked GitHub branch could not be prepared")
                return result

            run(
                "clone", "--depth", "1", "--branch", base,
                f"git@github.com:{self.repository}.git", str(root),
            )
            parent_sha = run("rev-parse", "HEAD").stdout.strip()
            run("checkout", "-b", branch)
            for relative, body in sorted(files.items()):
                target = (root / relative).resolve()
                try:
                    target.relative_to((root / "global-cloud").resolve())
                except ValueError as exc:
                    raise GitHubPublicationError("publication path escaped global-cloud") from exc
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(body)
            run("add", "--", "global-cloud")
            changed = run("diff", "--cached", "--name-only").stdout.splitlines()
            if not changed or any(not path.startswith("global-cloud/") for path in changed):
                raise GitHubPublicationError("the reviewed publication contains no safe change")
            run("-c", "user.name=Principia Admin", "-c", "user.email=admin@principia.local",
                "commit", "-m", message)
            commit_sha = run("rev-parse", "HEAD").stdout.strip()
            run("push", "--set-upstream", "origin", branch)
        return {"branch": branch, "commit_sha": commit_sha, "base_commit_sha": parent_sha}

    def review_branch_status(self, *, branch: str, commit_sha: str = "") -> dict[str, Any]:
        """Reconcile the zero-touch reviewed-branch publication workflow."""

        if commit_sha:
            release = self._verified_release_status(commit_sha)
            if release["state"] == "published":
                return release
            runs = self._public_request(
                f"/repos/{self.repository}/actions/runs?head_sha={commit_sha}&per_page=20"
            )
            publication_runs = [
                item
                for item in (runs.get("workflow_runs") if isinstance(runs, dict) else []) or []
                if str(item.get("name") or "")
                in {
                    "Publish reviewed Global Cloud batch",
                    "Submit reviewed Global Cloud branch",
                }
            ]
            if publication_runs:
                latest = publication_runs[0]
                conclusion = str(latest.get("conclusion") or "")
                if conclusion in {"failure", "cancelled", "timed_out", "action_required"}:
                    return {
                        "state": "needs_resolution",
                        "pr_number": None,
                        "pr_url": str(latest.get("html_url") or ""),
                        "error": {
                            "category": "publication_workflow_failed",
                            "workflow_url": str(latest.get("html_url") or ""),
                        },
                    }
                if str(latest.get("status") or "") == "completed":
                    return {**release, "state": "release_building"}
                return {
                    "state": "checks_running",
                    "pr_number": None,
                    "pr_url": str(latest.get("html_url") or ""),
                    "error": {},
                }

        # Compatibility for batches submitted by builds that still created a
        # PR before the zero-touch workflow was installed.
        pulls = self._public_request(
            f"/repos/{self.repository}/pulls?state=all&head=pzqpzq:{branch}&per_page=10"
        )
        if isinstance(pulls, list) and pulls:
            pull = pulls[0]
            return {
                "state": "checks_running",
                "pr_number": int(pull["number"]),
                "pr_url": str(pull.get("html_url") or ""),
                "error": {},
            }
        return {"state": "checks_running", "pr_number": None, "pr_url": "", "error": {}}

    def compare_commits(self, *, base: str, head: str) -> dict[str, Any]:
        value = self._public_request(f"/repos/{self.repository}/compare/{base}...{head}")
        if not isinstance(value, dict):
            raise GitHubPublicationError("GitHub returned an unexpected comparison response")
        return value

    def _verified_release_status(self, expected_commit: str) -> dict[str, Any]:
        latest_url = (
            "https://github.com/pzqpzq/Principia/releases/latest/download/latest.json"
        )
        response = httpx.get(latest_url, timeout=20, follow_redirects=True)
        if response.status_code != 200:
            return {"state": "release_building", "error": {}}
        try:
            latest = response.json()
        except ValueError:
            return {"state": "release_building", "error": {}}
        if not isinstance(latest, dict) or not bool(latest.get("verified")):
            return {"state": "release_building", "error": {}}
        latest_commit = str(latest.get("commit_sha") or "")
        if latest_commit != expected_commit:
            compare = self.compare_commits(base=expected_commit, head=latest_commit)
            if str(compare.get("status") or "") not in {"ahead", "identical"}:
                return {"state": "release_building", "error": {}}
        release_id = str(latest.get("release_id") or "")
        release = self._status_request(
            f"/repos/{self.repository}/releases/tags/global-{release_id}"
        )
        asset_names = {str(item.get("name") or "") for item in release.get("assets") or []}
        snapshot_name = f"principia-global-{release_id}.pcg"
        if not {snapshot_name, "manifest.json", "SHA256SUMS"}.issubset(asset_names):
            return {"state": "release_building", "error": {}}
        return {"state": "published", "release_id": release_id, "error": {}}

    def _request(
        self, method: str, path: str, *, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        token = self._token()
        try:
            with httpx.Client(
                trust_env=False, timeout=30, follow_redirects=False
            ) as client:
                response = client.request(
                    method,
                    "https://api.github.com" + path,
                    json=payload,
                    headers={
                        "Accept": "application/vnd.github+json",
                        "Authorization": f"Bearer {token}",
                        "X-GitHub-Api-Version": "2022-11-28",
                        "User-Agent": "Principia/1.4.1 Global Cloud Publisher",
                    },
                )
        finally:
            token = ""  # keep the credential out of durable state and exception payloads
        if response.status_code >= 400:
            raise GitHubPublicationError(
                f"GitHub API rejected the operation ({response.status_code})"
            )
        value = response.json()
        if not isinstance(value, dict):
            raise GitHubPublicationError("GitHub API returned an unexpected response")
        return value

    def _graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        value = self._request(
            "POST",
            "/graphql",
            payload={"query": query, "variables": variables},
        )
        if value.get("errors"):
            raise GitHubPublicationError("GitHub could not enable checked auto-merge")
        return value

    def _status_request(self, path: str) -> dict[str, Any]:
        try:
            return self._request("GET", path)
        except GitHubPublicationError as exc:
            value = self._public_request(path)
            if not isinstance(value, dict):
                raise GitHubPublicationError(
                    "GitHub returned an unexpected status response"
                ) from exc
            return value

    def repository_capabilities(self) -> dict[str, Any]:
        value = self._request("GET", f"/repos/{self.repository}")
        permissions = value.get("permissions") or {}
        return {
            "repository": value.get("full_name") or "",
            "default_branch": value.get("default_branch") or "main",
            "contents_write": bool(permissions.get("push")),
            "pull_requests_write": bool(permissions.get("push")),
        }

    def create_review_branch(
        self,
        *,
        branch: str,
        base: str,
        files: dict[str, bytes],
        message: str,
    ) -> dict[str, Any]:
        if not branch.startswith("principia-cloud/"):
            raise GitHubPublicationError("publication branches must use principia-cloud/*")
        if not files or any(
            not path.startswith("global-cloud/") or ".." in path.split("/") for path in files
        ):
            raise GitHubPublicationError("publication commits must affect only global-cloud/**")
        reference = self._request("GET", f"/repos/{self.repository}/git/ref/heads/{base}")
        parent_sha = str((reference.get("object") or {}).get("sha") or "")
        if not parent_sha:
            raise GitHubPublicationError("the repository base ref has no commit")
        parent = self._request("GET", f"/repos/{self.repository}/git/commits/{parent_sha}")
        base_tree = str((parent.get("tree") or {}).get("sha") or "")
        tree_items: list[dict[str, Any]] = []
        for path, body in sorted(files.items()):
            blob = self._request(
                "POST",
                f"/repos/{self.repository}/git/blobs",
                payload={"content": base64.b64encode(body).decode(), "encoding": "base64"},
            )
            tree_items.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        tree = self._request(
            "POST",
            f"/repos/{self.repository}/git/trees",
            payload={"base_tree": base_tree, "tree": tree_items},
        )
        commit = self._request(
            "POST",
            f"/repos/{self.repository}/git/commits",
            payload={"message": message, "tree": tree["sha"], "parents": [parent_sha]},
        )
        self._request(
            "POST",
            f"/repos/{self.repository}/git/refs",
            payload={"ref": f"refs/heads/{branch}", "sha": commit["sha"]},
        )
        return {"branch": branch, "commit_sha": commit["sha"], "base_commit_sha": parent_sha}

    def submit_reviewed_changeset(
        self,
        *,
        branch: str,
        base: str,
        title: str,
        body: str,
    ) -> dict[str, Any]:
        if not branch.startswith("principia-cloud/"):
            raise GitHubPublicationError("publication branches must use principia-cloud/*")
        pull = self._request(
            "POST",
            f"/repos/{self.repository}/pulls",
            payload={"title": title, "head": branch, "base": base, "body": body, "draft": False},
        )
        number = int(pull["number"])
        # Auto-merge remains subject to all repository branch protections and checks;
        # this mutation does not merge immediately.
        try:
            self._graphql(
                """
                mutation EnableAutoMerge($pullRequestId: ID!) {
                  enablePullRequestAutoMerge(input: {
                    pullRequestId: $pullRequestId,
                    mergeMethod: SQUASH
                  }) { pullRequest { autoMergeRequest { enabledAt } } }
                }
                """,
                {"pullRequestId": str(pull["node_id"])},
            )
            auto_merge_state = "auto_merge_queued"
        except GitHubPublicationError:
            auto_merge_state = "checks_or_branch_protection_pending"
        return {
            "pr_number": number,
            "pr_url": str(pull.get("html_url") or ""),
            "state": auto_merge_state,
        }

    def publication_status(self, *, pr_number: int) -> dict[str, Any]:
        """Reconcile a durable sync with GitHub and the verified Pages pointer.

        GitHub is deliberately polled rather than treated as the application's
        database.  A merged PR is only published once the release workflow has
        advanced the independently verified control document to that merge.
        """

        pull = self._status_request(f"/repos/{self.repository}/pulls/{pr_number}")
        if not bool(pull.get("merged")):
            if str(pull.get("state") or "") == "closed":
                return {"state": "failed", "error": {"category": "pr_closed_unmerged"}}
            mergeable_state = str(pull.get("mergeable_state") or "")
            if mergeable_state in {"dirty", "blocked"} and not pull.get("auto_merge"):
                return {
                    "state": "needs_resolution",
                    "error": {"category": "checks_or_merge_conflict", "detail": mergeable_state},
                }
            head_sha = str((pull.get("head") or {}).get("sha") or "")
            checks = self._status_request(
                f"/repos/{self.repository}/commits/{head_sha}/check-runs"
            )
            conclusions = {
                str(item.get("conclusion") or "")
                for item in checks.get("check_runs") or []
                if str(item.get("status") or "") == "completed"
            }
            if conclusions & {"failure", "cancelled", "timed_out", "action_required"}:
                return {
                    "state": "needs_resolution",
                    "error": {"category": "required_check_failed"},
                }
            return {
                "state": "auto_merge_queued" if pull.get("auto_merge") else "checks_running",
                "error": {},
            }

        merge_sha = str(pull.get("merge_commit_sha") or "")
        return {**self._verified_release_status(merge_sha), "merge_commit_sha": merge_sha}


def keychain_install_command() -> str:
    """Safe help text: the token is read by `security` from an interactive prompt."""

    return f"security add-generic-password -U -s '{_KEYCHAIN_SERVICE}' -a '{_REPOSITORY}' -w"
