from __future__ import annotations

from types import SimpleNamespace

import principia.admin.github as github_module
from principia.admin.github import GitHubPublicationAdapter


class _Response:
    status_code = 200

    def __init__(self, payload: dict[str, object], *, text: str = ""):
        self._payload = payload
        self.text = text

    def json(self) -> dict[str, object]:
        return self._payload


def test_followup_release_commit_completes_reviewed_publication(monkeypatch) -> None:
    adapter = GitHubPublicationAdapter()
    merge_sha = "a" * 40
    release_sha = "b" * 40
    release_id = "20260813-followup"

    snapshot_sha = "c" * 64
    latest = {
        "verified": True,
        "commit_sha": release_sha,
        "content_digest": "d" * 64,
        "snapshot_sha256": snapshot_sha,
        "release_id": release_id,
    }
    monkeypatch.setattr(
        GitHubPublicationAdapter,
        "_status_request",
        lambda _self, path: {"merged": True, "merge_commit_sha": merge_sha},
    )
    monkeypatch.setattr(
        GitHubPublicationAdapter,
        "compare_commits",
        lambda _self, **_: {"status": "ahead"},
    )
    monkeypatch.setattr(
        github_module,
        "httpx",
        SimpleNamespace(
            HTTPError=RuntimeError,
            get=lambda url, *_args, **_kwargs: (
                _Response(latest, text=f"{snapshot_sha}  principia-global-{release_id}.pcg\n")
                if str(url).endswith("latest.json") or str(url).endswith("SHA256SUMS")
                else _Response(latest)
            ),
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
            HTTPError=RuntimeError,
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


def test_exact_release_status_does_not_require_github_api(monkeypatch) -> None:
    adapter = GitHubPublicationAdapter()
    commit_sha = "e" * 40
    release_id = "20260815-direct-controls"
    snapshot_sha = "f" * 64
    latest = {
        "verified": True,
        "commit_sha": commit_sha,
        "content_digest": "a" * 64,
        "snapshot_sha256": snapshot_sha,
        "release_id": release_id,
    }

    def get(url: str, *_args, **_kwargs) -> _Response:
        if url.endswith("SHA256SUMS"):
            return _Response({}, text=f"{snapshot_sha}  principia-global-{release_id}.pcg\n")
        return _Response(latest)

    monkeypatch.setattr(
        GitHubPublicationAdapter,
        "_status_request",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("REST API used")),
    )
    monkeypatch.setattr(
        github_module,
        "httpx",
        SimpleNamespace(HTTPError=RuntimeError, get=get),
    )

    assert adapter._verified_release_status(commit_sha) == {
        "state": "published",
        "release_id": release_id,
        "error": {},
    }


def test_reviewed_branch_reports_one_failed_publication_run(monkeypatch) -> None:
    adapter = GitHubPublicationAdapter()
    monkeypatch.setattr(
        GitHubPublicationAdapter,
        "_verified_release_status",
        lambda _self, _sha: {"state": "release_building", "error": {}},
    )
    monkeypatch.setattr(
        GitHubPublicationAdapter,
        "_public_request",
        lambda _self, path: {
            "workflow_runs": [
                {
                    "name": "Publish reviewed Global Cloud batch",
                    "status": "completed",
                    "conclusion": "failure",
                    "html_url": "https://github.test/actions/1",
                }
            ]
        }
        if "/actions/runs?" in path
        else [],
    )

    outcome = adapter.review_branch_status(branch="principia-cloud/test", commit_sha="c" * 40)

    assert outcome["state"] == "needs_resolution"
    assert outcome["error"]["category"] == "publication_workflow_failed"


def test_reviewed_branch_completes_from_verified_release_without_a_pr(monkeypatch) -> None:
    adapter = GitHubPublicationAdapter()
    monkeypatch.setattr(
        GitHubPublicationAdapter,
        "_verified_release_status",
        lambda _self, _sha: {
            "state": "published",
            "release_id": "20260814-zero-touch",
            "error": {},
        },
    )

    outcome = adapter.review_branch_status(branch="principia-cloud/test", commit_sha="d" * 40)

    assert outcome == {
        "state": "published",
        "release_id": "20260814-zero-touch",
        "error": {},
    }
