from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Literal

from ..cloud import CloudRegistry, CloudSearchRequest, GlobalCloudSnapshotStore
from ..persistence import V14WorkspaceRepository
from ..search_semantics import (
    SEARCH_SEMANTICS_VERSION,
    literal_query_terms,
    semantic_query_groups,
)

SearchScope = Literal["global", "local", "combined"]


class PrincipleSearchService:
    policy_version = "search-v2"

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

    @staticmethod
    def _identifier(item: dict[str, Any]) -> str:
        return str(item.get("id") or item.get("principle_id") or "")

    @classmethod
    def _result_card(cls, item: dict[str, Any]) -> dict[str, Any]:
        """Return the bounded, path-free record used by interactive search."""

        identifier = cls._identifier(item)
        allowed = (
            "entity",
            "principle_class",
            "source",
            "area",
            "area_display",
            "title",
            "claim",
            "kind",
            "maturity",
            "stability",
            "assessment",
            "review_status",
            "status",
            "match_path",
            "match_section",
            "match_explanation",
            "bridge_provenance",
            "search_policy",
        )
        card = {name: item[name] for name in allowed if name in item}
        card.update(
            {
                "id": identifier,
                "principle_id": identifier,
                "entity": str(item.get("entity") or "principle"),
                "principle_class": str(item.get("principle_class") or "literature"),
            }
        )
        return card

    @staticmethod
    def _concept_groups(query: str) -> list[list[str]]:
        literal = literal_query_terms(query, limit=12)
        families = semantic_query_groups(literal)
        output: list[list[str]] = []
        consumed: set[str] = set()
        for family in families:
            if not family.intersection(literal):
                continue
            output.append(sorted(family))
            consumed.update(family)
        output.extend([[term] for term in literal if term not in consumed])
        return output

    def search_with_plan(
        self,
        query: str,
        *,
        scope: SearchScope = "combined",
        limit: int = 50,
        area: str = "",
        goal_id: str = "",
        source_id: str = "",
        intent: str = "auto",
        session_id: str = "",
    ) -> dict[str, Any]:
        """Execute explicit intersection, bridge, and side-support lanes."""

        if intent not in {"auto", "intersection", "bridge", "either"}:
            raise ValueError("intent must be auto, intersection, bridge, or either")
        clean_query = " ".join(str(query).split())
        groups = self._concept_groups(clean_query)
        resolved_intent = intent
        if intent == "auto":
            resolved_intent = (
                "bridge"
                if len(groups) >= 2 and " and " in f" {clean_query.casefold()} "
                else "intersection"
            )
        direct = self.search(
            clean_query,
            scope=scope,
            limit=limit,
            area=area,
            goal_id=goal_id,
            source_id=source_id,
        )
        bridge: dict[str, Any] = {"works": [], "principles": []}
        if (
            resolved_intent in {"bridge", "either"}
            and len(groups) >= 2
            and self.global_cloud is not None
            and self.global_cloud.active()
            and scope in {"global", "combined"}
        ):
            bridge = self.global_cloud.bridge_principles(groups[:2], limit=min(limit, 40))

        literal = literal_query_terms(clean_query, limit=12)
        side_sections: list[list[dict[str, Any]]] = []
        for group in groups[:2]:
            representative = next((term for term in literal if term in group), group[0])
            side_sections.append(
                self.search(
                    representative,
                    scope=scope,
                    limit=min(limit, 24),
                    area=area,
                    goal_id=goal_id,
                    source_id=source_id,
                )
            )
        while len(side_sections) < 2:
            side_sections.append([])

        bridge_items = list(bridge.get("principles") or [])
        bridge_ids = {self._identifier(item) for item in bridge_items}
        domain = [item for item in side_sections[0] if self._identifier(item) not in bridge_ids]
        domain_ids = {self._identifier(item) for item in domain}
        method = [
            item
            for item in side_sections[1]
            if self._identifier(item) not in bridge_ids | domain_ids
        ]
        foundations: list[dict[str, Any]] = []
        foundation_ids: set[str] = set()
        for item in [*bridge_items, *direct, *domain, *method]:
            identifier = self._identifier(item)
            detail = self.principle(identifier) if identifier else None
            for link in list((detail or {}).get("foundations") or []):
                meta = dict(link.get("meta_principle") or {}) if isinstance(link, dict) else {}
                meta_id = self._identifier(meta) or str(
                    (link or {}).get("meta_principle_id") if isinstance(link, dict) else ""
                )
                if not meta_id or meta_id in foundation_ids:
                    continue
                foundation_ids.add(meta_id)
                foundations.append(
                    {
                        **meta,
                        "id": meta_id,
                        "principle_id": meta_id,
                        "entity": "meta_principle",
                        "principle_class": "meta",
                        "match_path": "foundation_of_retrieved_principle",
                    }
                )
                if len(foundations) >= 12:
                    break
            if len(foundations) >= 12:
                break

        flattened: list[dict[str, Any]] = []
        seen: set[str] = set()
        primary = bridge_items if resolved_intent == "bridge" and bridge_items else direct
        explanations = {
            "direct_bridge": "Connected through a Cloud work that contains both concepts.",
            "domain_principles": "Supports the first scientific concept.",
            "method_principles": "Supports the second scientific or methodological concept.",
            "meta_foundations": "Established foundation of a retrieved Principle.",
        }
        for section_name, values in (
            ("direct_bridge", primary),
            ("domain_principles", domain),
            ("method_principles", method),
            ("meta_foundations", foundations),
        ):
            for item in values:
                identifier = self._identifier(item)
                if not identifier or identifier in seen:
                    continue
                seen.add(identifier)
                flattened.append(
                    {
                        **item,
                        "match_section": section_name,
                        "match_explanation": explanations[section_name],
                    }
                )
                if len(flattened) >= max(1, min(limit, 100)):
                    break
            if len(flattened) >= max(1, min(limit, 100)):
                break

        direct_section = bridge_items if bridge_items else direct
        section_cards = {
            "direct_bridge": [self._result_card(item) for item in direct_section],
            "domain_principles": [self._result_card(item) for item in domain],
            "method_principles": [self._result_card(item) for item in method],
            "meta_foundations": [self._result_card(item) for item in foundations],
        }
        flattened_cards = [self._result_card(item) for item in flattened]
        supporting_works = [
            {
                "work_id": str(item.get("work_id") or ""),
                "title": str(item.get("title") or ""),
                "abstract": str(item.get("abstract") or "")[:600],
                "matched_concepts": list(item.get("matched_concepts") or []),
            }
            for item in list(bridge.get("works") or [])
        ]
        cloud_status = self.global_cloud.status() if self.global_cloud is not None else {}
        vectors_complete = bool(cloud_status.get("vectors_complete"))
        return {
            "schema_version": "principia.principle-search/v2",
            "items": flattened_cards,
            "total": len(flattened_cards),
            "sections": section_cards,
            "section_counts": {
                "direct_bridge": len(direct_section),
                "domain_principles": len(domain),
                "method_principles": len(method),
                "meta_foundations": len(foundations),
            },
            "supporting_works": supporting_works,
            "query_plan": {
                "raw_query": clean_query,
                "intent": resolved_intent,
                "concept_groups": groups,
                "semantics_version": SEARCH_SEMANTICS_VERSION,
                "session_id": session_id,
            },
            "capabilities": {
                "vectors_complete": vectors_complete,
                "lexical": True,
                "evidence_graph": bool(self.global_cloud and self.global_cloud.active()),
                "ranking_mode": (
                    "hybrid + evidence graph"
                    if vectors_complete
                    else "lexical + evidence-graph fallback"
                ),
                "degraded": not vectors_complete,
                "degradation_reason": (
                    "The installed Cloud has no complete vector index; deterministic lexical and evidence-graph retrieval remains active."
                    if not vectors_complete
                    else ""
                ),
            },
            "next_cursor": None,
        }

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
