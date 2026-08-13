from __future__ import annotations

import base64
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Any

import httpx

_REPOSITORY = "pzqpzq/Principia"
_KEYCHAIN_SERVICE = "Principia Global Cloud GitHub"
_TOKEN_PATTERN = re.compile(r"^(?:github_pat_|ghp_)[A-Za-z0-9_]{20,}$")


class GitHubPublicationError(RuntimeError):
    pass


@dataclass(frozen=True)
class GitHubPublicationAdapter:
    """Fine-grained, Keychain-backed adapter restricted to pzqpzq/Principia."""

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
            return False

    def _request(
        self, method: str, path: str, *, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        token = self._token()
        try:
            response = httpx.request(
                method,
                "https://api.github.com" + path,
                json=payload,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {token}",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": "Principia/1.4.1 Global Cloud Publisher",
                },
                timeout=30,
                follow_redirects=False,
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

        pull = self._request("GET", f"/repos/{self.repository}/pulls/{pr_number}")
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
            checks = self._request("GET", f"/repos/{self.repository}/commits/{head_sha}/check-runs")
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
        latest_url = "https://pzqpzq.github.io/Principia/cloud/v1/latest.json"
        response = httpx.get(latest_url, timeout=20, follow_redirects=False)
        if response.status_code != 200:
            return {"state": "release_building", "merge_commit_sha": merge_sha, "error": {}}
        try:
            latest = response.json()
        except ValueError:
            return {"state": "release_building", "merge_commit_sha": merge_sha, "error": {}}
        if not isinstance(latest, dict) or not bool(latest.get("verified")):
            return {"state": "release_building", "merge_commit_sha": merge_sha, "error": {}}
        if str(latest.get("commit_sha") or "") != merge_sha:
            return {"state": "release_building", "merge_commit_sha": merge_sha, "error": {}}
        release_id = str(latest.get("release_id") or "")
        release = self._request(
            "GET", f"/repos/{self.repository}/releases/tags/global-{release_id}"
        )
        asset_names = {str(item.get("name") or "") for item in release.get("assets") or []}
        snapshot_name = f"principia-global-{release_id}.pcg"
        if not {snapshot_name, "manifest.json", "SHA256SUMS"}.issubset(asset_names):
            return {"state": "release_building", "merge_commit_sha": merge_sha, "error": {}}
        return {
            "state": "published",
            "release_id": release_id,
            "merge_commit_sha": merge_sha,
            "error": {},
        }


def keychain_install_command() -> str:
    """Safe help text: the token is read by `security` from an interactive prompt."""

    return f"security add-generic-password -U -s '{_KEYCHAIN_SERVICE}' -a '{_REPOSITORY}' -w"
