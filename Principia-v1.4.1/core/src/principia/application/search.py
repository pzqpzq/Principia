from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Literal

from ..cloud import CloudRegistry, CloudSearchRequest, GlobalCloudSnapshotStore
from ..persistence import V14WorkspaceRepository

SearchScope = Literal["global", "local", "combined"]


class PrincipleSearchService:
    policy_version = "search-v1"

    def __init__(
        self,
        cloud: CloudRegistry,
        workspace: V14WorkspaceRepository,
        *,
        global_cloud: GlobalCloudSnapshotStore | None = None,
    ) -> None:
        self.cloud = cloud
        self.workspace = workspace
        self.global_cloud = global_cloud

    def _global_search(self, query: str, *, limit: int) -> list[dict[str, Any]]:
        if self.global_cloud is not None and self.global_cloud.active():
            result = self.global_cloud.search(
                CloudSearchRequest(entity="principle", query=query, limit=limit)
            )
            return list(result["items"])
        return self.cloud.search(query, limit=limit)

    def search(
        self,
        query: str,
        *,
        scope: SearchScope = "combined",
        limit: int = 50,
        area: str = "",
        goal_id: str = "",
        source_id: str = "",
    ) -> list[dict[str, Any]]:
        resolved_limit = max(1, min(int(limit), 100))
        results: list[dict[str, Any]] = []
        global_rows: list[dict[str, Any]] = []
        local_rows: list[dict[str, Any]] = []
        if scope == "combined":
            # Global packages and the private workspace are independent SQLite stores.
            # Querying them concurrently keeps combined search within the same latency
            # envelope as either source without changing deterministic merge ordering.
            with ThreadPoolExecutor(max_workers=2, thread_name_prefix="principia-search") as pool:
                global_future = pool.submit(self._global_search, query, limit=resolved_limit)
                local_future = pool.submit(
                    self.workspace.search_local,
                    query,
                    limit=resolved_limit,
                    area=area,
                    goal_id=goal_id,
                    source_id=source_id,
                )
                global_rows = global_future.result()
                local_rows = local_future.result()
        elif scope == "global":
            global_rows = self._global_search(query, limit=resolved_limit)
        else:
            local_rows = self.workspace.search_local(
                query,
                limit=resolved_limit,
                area=area,
                goal_id=goal_id,
                source_id=source_id,
            )
        if area:
            global_rows = [item for item in global_rows if str(item.get("area") or "") == area]
        for item in global_rows:
            if item.get("entity") == "principle":
                results.append(
                    {
                        **item,
                        "assessment": item.get("review_status") or "unassessed",
                        "search_policy": "paper-first-v1",
                        "sort_score": float(item.get("score") or 0),
                    }
                )
                continue
            rank = abs(float(item.pop("lexical_rank", 0)))
            item.update(
                {
                    "id": item.pop("principle_id"),
                    "source": "global",
                    "assessment": (
                        "unassessed"
                        if item.get("content_class") == "unassessed_candidates"
                        else "reviewed"
                    ),
                    "search_policy": self.policy_version,
                    "sort_score": rank + float(item.get("quality", 0)) * 0.2,
                }
            )
            results.append(item)
        for item in local_rows:
            rank = abs(float(item.pop("rank", 0)))
            version = int(item.get("version") or 0)
            item.update(
                {
                    "id": item.pop("principle_id"),
                    "source": "local",
                    "assessment": "reviewed" if version else "unassessed",
                    "search_policy": self.policy_version,
                    "sort_score": rank,
                }
            )
            results.append(item)
        results.sort(key=lambda item: (-float(item["sort_score"]), str(item["id"])))
        for item in results:
            item.pop("sort_score", None)
        return results[:resolved_limit]

    def principle(self, principle_id: str) -> dict[str, Any] | None:
        local = (
            self.workspace.candidate_detail(principle_id)
            if principle_id.startswith("cand:")
            else self.workspace.principle(principle_id)
        )
        if local is not None:
            return {**local, "source": "local"}
        if self.global_cloud is not None and self.global_cloud.active():
            current = self.global_cloud.principle(principle_id)
            if current is not None:
                return current
        global_principle = self.cloud.principle(principle_id)
        if global_principle is not None:
            content_class = str(
                global_principle.get("package_content_class") or "reviewed_capsules"
            )
            references = list(global_principle.get("references") or [])
            if content_class == "unassessed_candidates":
                source_references = list(global_principle.get("source_references") or [])
                public_by_id = {str(item.get("work_id") or ""): item for item in source_references}
                roles_by_id: dict[str, str] = {}
                for item in references:
                    work_id = str(item.get("work_id") or "")
                    if work_id:
                        roles_by_id.setdefault(work_id, str(item.get("role") or "evidence"))
                global_principle["source_references"] = [
                    {
                        "work_id": work_id,
                        "title": str(
                            public_by_id.get(work_id, {}).get("title")
                            or work_id
                            or "Supporting paper"
                        ),
                        "url": str(public_by_id.get(work_id, {}).get("url") or ""),
                        "doi": str(public_by_id.get(work_id, {}).get("doi") or ""),
                        "role": roles_by_id[work_id],
                    }
                    for work_id in sorted(roles_by_id)
                ]
                global_principle["quality"] = None
                global_principle["assessment_status"] = "unassessed"
            return {
                **global_principle,
                "source": "global",
                "package_content_class": content_class,
            }
        return None
