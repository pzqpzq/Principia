from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from ..domain import canonical_sha256
from .search import PrincipleSearchService, SearchScope


class PrincipleGraphService:
    selection_policy = "overview-v2"

    def __init__(self, search: PrincipleSearchService) -> None:
        self.search = search

    @staticmethod
    def _principle_node(principle_id: str, detail: dict[str, Any] | None) -> dict[str, Any]:
        if detail is None:
            return {
                "id": principle_id,
                "entity_type": "principle",
                "node_type": "ghost_principle",
                "title": "Uninstalled Principle",
                "claim": "",
                "area": "",
                "source": "ghost",
                "assessment": "unavailable",
                "maturity": "ghost",
                "version": 0,
                "source_count": 0,
                "ghost": True,
                "install_action": True,
            }
        source = str(detail.get("source") or "local")
        metadata = detail.get("local_metadata") or {}
        is_local_candidate = principle_id.startswith("cand:")
        return {
            "id": principle_id,
            "entity_type": "principle",
            "node_type": ("local_candidate" if is_local_candidate else "global_capsule"),
            "title": detail.get("title", principle_id),
            "claim": detail.get("claim", ""),
            "area": detail.get("area", ""),
            "source": source,
            "assessment": "unassessed" if is_local_candidate else "reviewed",
            "maturity": (
                (detail.get("scientific_argument") or {}).get("generalization_level", "study_bound")
                if is_local_candidate
                else detail.get("maturity", "supported")
            ),
            "version": detail.get("version", 0),
            "source_count": int(metadata.get("source_count") or detail.get("source_count") or 0),
            "quality_state": metadata.get("quality_state", "reviewed"),
            "ghost": False,
            "install_action": False,
        }

    def _shared_evidence_edges(
        self, candidate_ids: list[str], *, limit: int = 200
    ) -> list[dict[str, Any]]:
        members: dict[str, set[str]] = defaultdict(set)
        for link in self.search.workspace.candidate_work_links(candidate_ids):
            members[link["work_id"]].add(link["candidate_id"])
        pair_counts: dict[tuple[str, str], int] = defaultdict(int)
        for identities in members.values():
            ordered = sorted(identities)
            for first_index, first in enumerate(ordered):
                for second in ordered[first_index + 1 :]:
                    pair_counts[(first, second)] += 1
        output = []
        for (first, second), count in sorted(
            pair_counts.items(), key=lambda item: (-item[1], item[0])
        )[:limit]:
            output.append(
                {
                    "id": f"{first}|{second}|shared_evidence",
                    "source": first,
                    "target": second,
                    "type": "shared_evidence",
                    "edge_class": "derived",
                    "provenance": "derived_shared_evidence",
                    "shared_work_count": count,
                    "label": f"{count} shared evidence work{'s' if count != 1 else ''}",
                }
            )
        return output

    @staticmethod
    def _descriptor(
        *,
        scope: str,
        collection_id: str,
        shown: int,
        total: int,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        explanation: str,
    ) -> dict[str, Any]:
        return {
            "node_semantics": "principle",
            "selection_policy": "overview-v2",
            "scope": scope,
            "collection_id": collection_id,
            "shown_count": shown,
            "total_count": total,
            "explanation": explanation,
            "graph_digest": canonical_sha256(
                {
                    "nodes": [item["id"] for item in nodes],
                    "edges": [item["id"] for item in edges],
                    "scope": scope,
                    "collection_id": collection_id,
                }
            ),
        }

    def neighborhood(
        self,
        seed_id: str,
        *,
        scope: SearchScope = "combined",
        depth: int = 1,
        limit: int = 60,
        include_shared_evidence: bool = False,
    ) -> dict[str, Any]:
        resolved_depth = max(1, min(int(depth), 2))
        resolved_limit = max(1, min(int(limit), 500))
        queue: deque[tuple[str, int]] = deque([(seed_id, 0)])
        visited: set[str] = set()
        nodes: dict[str, dict[str, Any]] = {}
        edges: dict[tuple[str, str, str], dict[str, Any]] = {}
        truncated = False
        while queue:
            principle_id, current_depth = queue.popleft()
            if principle_id in visited:
                continue
            if len(nodes) >= resolved_limit:
                truncated = True
                break
            visited.add(principle_id)
            detail = self.search.principle(principle_id)
            if detail is not None:
                source = str(detail.get("source") or "local")
                if scope != "combined" and source != scope:
                    continue
            nodes[principle_id] = self._principle_node(principle_id, detail)
            if detail is None or current_depth >= resolved_depth:
                continue
            for relation in detail.get("relations") or []:
                target = str(relation.get("target_principle_id") or "")
                if not target:
                    continue
                relation_type = str(relation.get("relation_type") or "related")
                key = (principle_id, target, relation_type)
                edges[key] = {
                    "id": "|".join(key),
                    "source": principle_id,
                    "target": target,
                    "type": relation_type,
                    "edge_class": "scientific",
                    "provenance": "asserted_relation",
                    "strength": relation.get("strength", 1),
                    "label": relation_type.replace("_", " "),
                }
                if target not in visited:
                    queue.append((target, current_depth + 1))
            for relation in detail.get("incoming_relations") or []:
                source_id = str(relation.get("source_candidate_id") or "")
                if not source_id:
                    continue
                relation_type = str(relation.get("relation_type") or "related")
                key = (source_id, principle_id, relation_type)
                edges[key] = {
                    "id": "|".join(key),
                    "source": source_id,
                    "target": principle_id,
                    "type": relation_type,
                    "edge_class": "scientific",
                    "provenance": relation.get("provenance", "model_proposed"),
                    "strength": 1,
                    "label": relation_type.replace("_", " "),
                }
                if source_id not in visited:
                    queue.append((source_id, current_depth + 1))
        ordered_nodes = [nodes[key] for key in sorted(nodes)]
        ordered_edges = [edges[key] for key in sorted(edges)]
        if include_shared_evidence:
            local_ids = [
                item["id"] for item in ordered_nodes if item["node_type"] == "local_candidate"
            ]
            ordered_edges.extend(self._shared_evidence_edges(local_ids))
        ordered_edges = sorted(ordered_edges, key=lambda item: item["id"])
        descriptor = self._descriptor(
            scope=scope,
            collection_id="",
            shown=len(ordered_nodes),
            total=len(ordered_nodes),
            nodes=ordered_nodes,
            edges=ordered_edges,
            explanation=(
                "Every node is one Principle. This view expands asserted scientific "
                "relations around the selected Principle. Papers remain evidence only."
            ),
        )
        return {
            **descriptor,
            "seed_id": seed_id,
            "depth": resolved_depth,
            "limit": resolved_limit,
            "nodes": ordered_nodes,
            "edges": ordered_edges,
            "truncated": truncated or (len(ordered_nodes) >= resolved_limit and bool(queue)),
            "soft_limit_exceeded": len(ordered_nodes) > 150,
            "include_shared_evidence": include_shared_evidence,
            # Focused neighborhoods do not have a collection-wide denominator.
            # Report the entities actually present so the Map never claims that a
            # visible Local or Global Principle belongs to an empty source.
            "total_candidates": sum(
                item["node_type"] == "local_candidate" for item in ordered_nodes
            ),
            "total_global_principles": sum(
                item["node_type"] == "global_capsule" for item in ordered_nodes
            ),
        }

    @staticmethod
    def _diverse_local_selection(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        strata: dict[tuple[str, str, str], deque[dict[str, Any]]] = defaultdict(deque)
        for item in items:
            goal_id = str(item.get("goal_ids") or "").split(",", 1)[0]
            key = (
                str(item.get("area") or ""),
                goal_id,
                str(item.get("claim_class") or "unclassified"),
            )
            strata[key].append(item)
        for key, values in list(strata.items()):
            strata[key] = deque(
                sorted(
                    values,
                    key=lambda item: (
                        -int(item.get("relation_count") or 0),
                        -int(item.get("source_count") or 0),
                        str(item.get("candidate_id")),
                    ),
                )
            )
        selected: list[dict[str, Any]] = []
        ordered_keys = sorted(strata)
        while len(selected) < limit and ordered_keys:
            next_keys = []
            for key in ordered_keys:
                if strata[key] and len(selected) < limit:
                    selected.append(strata[key].popleft())
                if strata[key]:
                    next_keys.append(key)
            ordered_keys = next_keys
        return selected

    def overview(
        self,
        *,
        scope: SearchScope = "local",
        limit: int = 60,
        area: str = "",
        goal_id: str = "",
        source_id: str = "",
        collection_id: str = "",
        include_shared_evidence: bool = False,
    ) -> dict[str, Any]:
        if collection_id.startswith("area:") and not area:
            area = collection_id.removeprefix("area:")
        elif collection_id.startswith("goal:") and not goal_id:
            goal_id = collection_id
        elif (
            collection_id.startswith("src:") or collection_id.startswith("source:")
        ) and not source_id:
            source_id = collection_id
        resolved_limit = max(1, min(int(limit), 500))
        local_budget = resolved_limit if scope == "local" else (resolved_limit + 1) // 2
        global_budget = resolved_limit if scope == "global" else resolved_limit // 2
        local_page: dict[str, Any] = {"items": [], "total": 0, "next_cursor": None}
        global_page: dict[str, Any] = {"items": [], "total": 0}
        if scope in {"local", "combined"}:
            local_page = self.search.workspace.browse_candidates(
                limit=100,
                area=area,
                goal_id=goal_id,
                source_id=source_id,
                eligibility="eligible",
                quality_state="eligible",
            )
            pool = list(local_page["items"])
            cursor = local_page["next_cursor"]
            while cursor and len(pool) < 500:
                page = self.search.workspace.browse_candidates(
                    limit=100,
                    cursor=cursor,
                    area=area,
                    goal_id=goal_id,
                    source_id=source_id,
                    eligibility="eligible",
                    quality_state="eligible",
                )
                pool.extend(page["items"])
                cursor = page["next_cursor"]
            local_page["items"] = self._diverse_local_selection(pool, local_budget)
        if scope in {"global", "combined"} and global_budget:
            global_page = self.search.cloud.browse(area=area, limit=global_budget)
        local_nodes = [
            {
                "id": item["candidate_id"],
                "entity_type": "principle",
                "node_type": "local_candidate",
                "title": item["title"],
                "claim": item["claim"],
                "area": item["area"],
                "source": "local",
                "assessment": "unassessed",
                "maturity": item.get("generalization_level") or "study_bound",
                "version": 0,
                "source_count": int(item.get("source_count") or 0),
                "quality_state": item.get("quality_state") or "eligible",
                "ghost": False,
                "install_action": False,
            }
            for item in local_page["items"]
        ]
        global_nodes = [
            {
                "id": item["principle_id"],
                "entity_type": "principle",
                "node_type": "global_capsule",
                "title": item["title"],
                "claim": item["claim"],
                "area": item["area"],
                "source": "global",
                "assessment": "reviewed",
                "maturity": item["maturity"],
                "version": item["version"],
                "source_count": int(item.get("source_count") or 0),
                "quality_state": "reviewed",
                "ghost": False,
                "install_action": False,
            }
            for item in global_page["items"]
        ]
        nodes = sorted([*local_nodes, *global_nodes], key=lambda item: item["id"])
        node_ids = {item["id"] for item in nodes}
        edges = []
        for relation in self.search.workspace.candidate_relation_links(
            [item["id"] for item in local_nodes]
        ):
            if relation["target"] not in node_ids:
                continue
            edges.append(
                {
                    "id": f"{relation['source']}|{relation['target']}|{relation['type']}",
                    "source": relation["source"],
                    "target": relation["target"],
                    "type": relation["type"],
                    "edge_class": "scientific",
                    "provenance": relation["provenance"],
                    "label": relation["type"].replace("_", " "),
                }
            )
        if include_shared_evidence:
            edges.extend(self._shared_evidence_edges([item["id"] for item in local_nodes]))
        edges = sorted({item["id"]: item for item in edges}.values(), key=lambda item: item["id"])
        total = int(local_page["total"]) + int(global_page["total"])
        descriptor = self._descriptor(
            scope=scope,
            collection_id=collection_id,
            shown=len(nodes),
            total=total,
            nodes=nodes,
            edges=edges,
            explanation=(
                "Every node is one generalizable Principle argument. Papers and topics "
                "are never nodes; papers appear only as evidence in the inspector. "
                "overview-v2 balances areas, research goals, and claim classes."
            ),
        )
        return {
            **descriptor,
            "area": area,
            "goal_id": goal_id,
            "source_id": source_id,
            "nodes": nodes,
            "edges": edges,
            "truncated": total > len(nodes),
            "soft_limit_exceeded": len(nodes) > 150,
            "include_shared_evidence": include_shared_evidence,
            "total_candidates": local_page["total"],
            "total_global_principles": global_page["total"],
            "recent_goals": self.search.workspace.library_collections("research_goal")[:8],
            "counts": {
                **self.search.workspace.v14_counts(),
                "global_principles": int(global_page["total"]),
                "installed_areas": len(
                    {item["area"] for item in self.search.cloud.installed() if item["active"]}
                ),
            },
        }
