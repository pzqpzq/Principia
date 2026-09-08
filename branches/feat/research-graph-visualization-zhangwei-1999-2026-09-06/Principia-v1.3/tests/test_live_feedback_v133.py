from __future__ import annotations

from typing import Any

from principia_retrieval.embeddings import SiliconFlowEmbeddingClient
from principia_retrieval.planner import deterministic_query_plan
from principia_retrieval.works import dedupe_works


def test_arxiv_version_suffixes_share_one_strong_identity() -> None:
    rows = dedupe_works(
        [
            {
                "title": "When Models Develop Languages",
                "authors": ["Ada Example"],
                "year": 2026,
                "source": "semantic_scholar",
                "arxiv_id": "2606.29354",
                "semantic_scholar_id": "S2-A",
            },
            {
                "title": "When Models Develop Languages",
                "authors": ["Ada Example"],
                "year": 2026,
                "source": "arxiv",
                "arxiv_id": "2606.29354v1",
            },
        ]
    )

    assert len(rows) == 1
    assert rows[0]["arxiv_id"] == "2606.29354"


def test_doi_resolver_and_prefix_forms_share_one_strong_identity() -> None:
    rows = dedupe_works(
        [
            {
                "title": "Preprint title",
                "doi": "HTTPS://WWW.DOI.ORG/doi%3A10.1000/ABC",
                "source": "openalex",
            },
            {
                "title": "Retitled journal publication",
                "doi": "doi:10.1000/abc",
                "source": "crossref",
            },
        ]
    )

    assert len(rows) == 1
    assert rows[0]["doi"] == "10.1000/abc"


def test_generic_acronym_is_not_a_standalone_search_query() -> None:
    plan = deterministic_query_plan(
        "Communication-efficient multi-agent LLM reasoning with learned machine dialects"
    )

    assert "LLM" not in plan.search_queries
    assert any("LLM" in query and len(query.split()) > 1 for query in plan.search_queries)


def test_embedding_client_reuses_vectors_across_fresh_searches(monkeypatch: Any) -> None:
    calls: list[list[str]] = []

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            texts = calls[-1]
            return {
                "data": [
                    {"index": index, "embedding": [float(index + 1), 1.0]}
                    for index, _ in enumerate(texts)
                ]
            }

    class Client:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def __enter__(self) -> Client:
            return self

        def __exit__(self, *args: Any) -> None:
            return None

        def post(self, url: str, *, json: dict[str, Any]) -> Response:
            calls.append(list(json["input"]))
            return Response()

    monkeypatch.setattr("principia_retrieval.embeddings.httpx.Client", Client)
    client = SiliconFlowEmbeddingClient(api_key="test", dimensions=2, max_retries=0)

    assert client.embed(["alpha", "beta"]) == client.embed(["alpha", "beta"])
    assert calls == [["alpha", "beta"]]
