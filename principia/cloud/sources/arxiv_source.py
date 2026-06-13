from __future__ import annotations

from typing import Any

from ...arxiv import search_arxiv


def search(query: str, *, limit: int = 20) -> list[dict[str, Any]]:
    return search_arxiv(query, max_results=limit)
