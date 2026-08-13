from __future__ import annotations

from types import SimpleNamespace

import principia.admin.github as github_module
from principia.admin.github import GitHubPublicationAdapter


class _Response:
    status_code = 200

    def __init__(self, payload: dict[str, object]):
        self._payload = payload

    def json(self) -> dict[str, object]:
        return self._payload


def test_followup_release_commit_completes_reviewed_publication(monkeypatch) -> None:
    adapter = GitHubPublicationAdapter()
    merge_sha = "a" * 40
    release_sha = "b" * 40
    release_id = "20260813-followup"

    def status(path: str) -> dict[str, object]:
        if path.endswith("/pulls/14"):
            return {"merged": True, "merge_commit_sha": merge_sha}
        assert path.endswith(f"/releases/tags/global-{release_id}")
        return {
            "assets": [
                {"name": f"principia-global-{release_id}.pcg"},
                {"name": "manifest.json"},
                {"name": "SHA256SUMS"},
            ]
        }

    monkeypatch.setattr(GitHubPublicationAdapter, "_status_request", lambda _self, path: status(path))
    monkeypatch.setattr(
        GitHubPublicationAdapter,
        "compare_commits",
        lambda _self, **_: {"status": "ahead"},
    )
    monkeypatch.setattr(
        github_module,
        "httpx",
        SimpleNamespace(
            get=lambda *_args, **_kwargs: _Response(
                {
                    "verified": True,
                    "commit_sha": release_sha,
                    "release_id": release_id,
                }
            )
        ),
    )

    outcome = adapter.publication_status(pr_number=14)

    assert outcome["state"] == "published"
    assert outcome["release_id"] == release_id


def test_unrelated_verified_release_does_not_complete_publication(monkeypatch) -> None:
    adapter = GitHubPublicationAdapter()
    monkeypatch.setattr(
        GitHubPublicationAdapter,
        "_status_request",
        lambda _self, _path: {"merged": True, "merge_commit_sha": "a" * 40},
    )
    monkeypatch.setattr(
        GitHubPublicationAdapter,
        "compare_commits",
        lambda _self, **_: {"status": "diverged"},
    )
    monkeypatch.setattr(
        github_module,
        "httpx",
        SimpleNamespace(
            get=lambda *_args, **_kwargs: _Response(
                {
                    "verified": True,
                    "commit_sha": "b" * 40,
                    "release_id": "unrelated",
                }
            )
        ),
    )

    assert adapter.publication_status(pr_number=14)["state"] == "release_building"
