from __future__ import annotations

import base64
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from itertools import combinations
from typing import Any, Literal

from ..cloud import CloudRegistry, CloudSearchRequest, GlobalCloudSnapshotStore
from ..domain import concise_principle_title
from ..persistence import V14WorkspaceRepository

_TOKEN = re.compile(r"[a-z0-9][a-z0-9_-]+")
_RELATION_STOPWORDS = frozenset(
    {
        "about",
        "after",
        "also",
        "and",
        "among",
        "are",
        "because",
        "between",
        "can",
        "conditions",
        "during",
        "from",
        "has",
        "have",
        "into",
        "method",
        "methods",
        "model",
        "models",
        "paper",
        "principle",
        "reported",
        "result",
        "results",
        "shows",
        "study",
        "system",
        "systems",
        "that",
        "the",
        "their",
        "these",
        "this",
        "through",
        "under",
        "using",
        "via",
        "was",
        "were",
        "when",
        "where",
        "which",
        "with",
    }
)
_POSITIVE_DIRECTION = frozenset(
    {
        "activate",
        "activates",
        "enhance",
        "enhances",
        "improve",
        "improves",
        "increase",
        "increases",
        "promote",
        "promotes",
        "stabilize",
        "stabilizes",
        "support",
        "supports",
    }
)
_NEGATIVE_DIRECTION = frozenset(
    {
        "decrease",
        "decreases",
        "degrade",
        "degrades",
        "impair",
        "impairs",
        "inhibit",
        "inhibits",
        "limit",
        "limits",
        "reduce",
        "reduces",
        "suppress",
        "suppresses",
    }
)

# Versioned scientific concept families provide local semantic recall without
# sending private Principle text to an embedding endpoint on every Explorer
# keystroke. Literature ranking may use the explicitly enabled remote embedding
# service; library browsing remains fast and offline-capable.
_SEMANTIC_CONCEPTS = (
    frozenset(
        {
            "agent",
            "agents",
            "multiagent",
            "multi-agent",
            "team",
            "teams",
            "coordination",
            "collaboration",
            "specialization",
            "roles",
        }
    ),
    frozenset({"autonomous", "agentic", "automated", "automation", "self-driving"}),
    frozenset(
        {
            "science",
            "scientific",
            "research",
            "discovery",
            "experiment",
            "experimentation",
            "hypothesis",
        }
    ),
    frozenset(
        {
            "hilbert",
            "boltzmann",
            "kinetic",
            "hydrodynamic",
            "fluid",
            "continuum",
            "equation",
            "equations",
        }
    ),
    frozenset(
        {"verify", "verification", "verifier", "validation", "critic", "critique", "checking"}
    ),
    frozenset({"memory", "persistent", "persistence", "history", "filesystem", "git"}),
    frozenset(
        {
            "reliable",
            "reliability",
            "robust",
            "robustness",
            "fault",
            "faults",
            "error",
            "errors",
            "consistency",
        }
    ),
    frozenset({"reasoning", "inference", "deliberation", "planning", "search"}),
    frozenset({"coherence", "decoherence", "noise", "loss"}),
    frozenset({"resistance", "escape", "checkpoint", "immunotherapy"}),
)


def _semantic_expansion(query_terms: set[str]) -> set[str]:
    expanded: set[str] = set()
    for family in _SEMANTIC_CONCEPTS:
        if query_terms & family:
            expanded.update(family - query_terms)
    return expanded


def _readable_title(title: Any, claim: Any, limit: int = 220) -> str:
    stored = " ".join(str(title or "").split())
    full_claim = " ".join(str(claim or "").split())
    source = full_claim if len(stored) >= limit - 10 and len(full_claim) > len(stored) else stored
    if len(source) <= limit:
        return source
    boundary = source.rfind(" ", 0, limit - 1)
    if boundary < limit // 2:
        boundary = limit - 1
    return source[:boundary].rstrip(" ,;:-") + "…"


def _csv(value: Any) -> list[str]:
    if isinstance(value, str) and value.startswith("["):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            decoded = None
        if isinstance(decoded, list):
            return sorted({str(item) for item in decoded if str(item)})
    return sorted({part for part in str(value or "").split(",") if part})


def _relation_tokens(value: Any) -> frozenset[str]:
    return frozenset(
        token
        for token in _TOKEN.findall(str(value or "").casefold())
        if token not in _RELATION_STOPWORDS and len(token) > 2
    )


def _similarity(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _direction_sign(argument: dict[str, Any], claim: str) -> int:
    terms = _relation_tokens(argument.get("direction_or_qualifier")) | _relation_tokens(claim)
    positive = len(terms & _POSITIVE_DIRECTION)
    negative = len(terms & _NEGATIVE_DIRECTION)
    if positive == negative:
        return 0
    return 1 if positive > negative else -1


def _argument_view(detail: dict[str, Any]) -> dict[str, Any]:
    argument = detail.get("scientific_argument")
    if not isinstance(argument, dict):
        argument = {}
    scope = detail.get("scope")
    scope_text = scope.get("statement", "") if isinstance(scope, dict) else scope
    claim = str(argument.get("canonical_claim") or detail.get("claim") or "")
    return {
        "claim_text": claim,
        "claim": _relation_tokens(claim),
        "subject": _relation_tokens(argument.get("subject_system") or scope_text),
        "driver": _relation_tokens(argument.get("driver_or_intervention")),
        "outcome": _relation_tokens(argument.get("outcome")),
        "conditions": _relation_tokens(" ".join(argument.get("conditions") or [])),
        "direction": _direction_sign(argument, claim),
    }


def _cursor(identifier: str, sort: str) -> str:
    payload = json.dumps({"after_id": identifier, "sort": sort}, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def _after_id(cursor: str | None, sort: str) -> str:
    if not cursor:
        return ""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(padded).decode())
        identifier = str(value["after_id"])
        if not identifier or value.get("sort") != sort:
            raise ValueError
        return identifier
    except Exception as exc:
        raise ValueError("invalid Principles cursor") from exc


class PrincipleExplorerService:
    """Create readable, faceted Principle cards without exposing storage jargon."""

    def __init__(
        self,
        registry: CloudRegistry,
        repository: V14WorkspaceRepository,
        *,
        global_cloud: GlobalCloudSnapshotStore | None = None,
    ) -> None:
        self.registry = registry
        self.repository = repository
        self.global_cloud = global_cloud

    def browse(
        self,
        *,
        scope: Literal["local", "global", "combined"] = "local",
        query: str = "",
        area: str = "",
        package_id: str = "",
        goal_id: str = "",
        source_id: str = "",
        goal_run_id: str = "",
        claim_type: str = "",
        evidence_status: str = "checks_passed",
        human_review: str = "",
        minimum_supporting_papers: int = 0,
        has_reliability: bool | None = None,
        has_influence: bool | None = None,
        known_contradictions: bool | None = None,
        sort: str = "updated",
        limit: int = 24,
        cursor: str | None = None,
        page: int = 1,
        page_mode: bool = False,
    ) -> dict[str, Any]:
        query_terms = set(_TOKEN.findall(query.casefold()))
        resolved_limit = max(1, min(int(limit), 100))
        resolved_page = max(1, int(page))
        quality_states = {
            "checks_passed": ("eligible",),
            "held_back": ("quarantined",),
            "archived": ("archived",),
        }.get(evidence_status, ("eligible", "quarantined", "archived"))
        # Card and Graph Mode must project the same frozen research-run
        # membership.  Graph Mode deliberately calls browse without database
        # pagination; requiring ``page_mode`` here silently replaced the goal
        # result with the entire Local/legacy registry library.
        if goal_run_id:
            return self._goal_run_page(
                goal_run_id=goal_run_id,
                membership=scope,
                query_terms=query_terms,
                area=area,
                claim_type=claim_type,
                evidence_status=evidence_status,
                human_review=human_review,
                limit=resolved_limit,
                page=resolved_page,
            )
        if (
            scope == "global"
            and self.global_cloud is not None
            and self.global_cloud.active()
            and page_mode
        ):
            result = self.global_cloud.search(
                CloudSearchRequest(
                    entity="principle",
                    query=query,
                    areas=[area] if area else [],
                    limit=resolved_limit,
                    cursor=base64.urlsafe_b64encode(
                        str((resolved_page - 1) * resolved_limit).encode()
                    ).decode().rstrip("="),
                )
            )
            cards = [self._global_cloud_card(item) for item in result["items"]]
            return {
                "items": cards,
                "next_cursor": result.get("next_cursor"),
                "total": result["total"],
                "facets": result["facets"],
                "sort_explanation": "Global results use paper-first retrieval with stable tie-breaking.",
                "metric_status": {"state": "not_applicable", "metric_revision": None},
                "page": resolved_page,
                "page_size": resolved_limit,
                "page_count": math.ceil(result["total"] / resolved_limit) if result["total"] else 0,
            }
        # The production Explorer's ordinary collection pages are sliced by
        # SQLite before card JSON is materialized.  This keeps browser and
        # server memory bounded even for very large folders.  Rich metric and
        # text filters retain the compatibility path below.
        database_page = (
            page_mode
            and scope == "local"
            and not query_terms
            and not cursor
            and not claim_type
            and not human_review
            and minimum_supporting_papers == 0
            and has_reliability is None
            and has_influence is None
            and known_contradictions is None
            and evidence_status in {"", "checks_passed", "held_back", "archived"}
            and sort in {"updated", "title", "supporting_papers"}
        )
        if database_page:
            total = self.repository.count_principle_card_rows(
                goal_id=goal_id,
                source_id=source_id,
                area=area,
                quality_states=quality_states,
            )
            rows = self.repository.principle_card_rows(
                limit=resolved_limit,
                offset=(resolved_page - 1) * resolved_limit,
                goal_id=goal_id,
                source_id=source_id,
                area=area,
                quality_states=quality_states,
                sort=sort,
            )
            page_cards = [self._local_card(row) for row in rows]
            self._attach_relation_previews(page_cards)
            status = self.repository.relation_metric_status()
            metric_revision = status.get("metric_revision")
            for card in page_cards:
                if card["influence_score"] is not None or card["reliability_score"] is not None:
                    card["metric_revision"] = metric_revision
            return {
                "items": page_cards,
                "next_cursor": None,
                "total": total,
                "facets": self.repository.principle_card_facets(
                    goal_id=goal_id,
                    source_id=source_id,
                    area=area,
                    quality_states=quality_states,
                ),
                "sort_explanation": self._sort_explanation(sort),
                "metric_status": status,
                "page": resolved_page,
                "page_size": resolved_limit,
                "page_count": math.ceil(total / resolved_limit) if total else 0,
            }
        cards: list[dict[str, Any]] = []
        if scope in {"local", "combined"}:
            for row in self.repository.principle_card_rows():
                card = self._local_card(row)
                if area and area not in card["area_labels"]:
                    continue
                if goal_id and goal_id not in _csv(row.get("goal_ids")):
                    continue
                if source_id and source_id not in _csv(row.get("source_ids")):
                    continue
                if claim_type and card["claim_type"] != claim_type:
                    continue
                if evidence_status and card["evidence_status"] != evidence_status:
                    continue
                if human_review and card["human_review_status"] != human_review:
                    continue
                if card["supporting_work_count"] < minimum_supporting_papers:
                    continue
                if (
                    has_reliability is not None
                    and (card["reliability_score"] is not None) != has_reliability
                ):
                    continue
                if (
                    has_influence is not None
                    and (card["influence_score"] is not None) != has_influence
                ):
                    continue
                has_conflict = card["incoming_contradict_count"] > 0
                if known_contradictions is not None and has_conflict != known_contradictions:
                    continue
                card["_relevance"] = self._relevance(card, query_terms)
                if query_terms and card["_relevance"] <= 0:
                    continue
                cards.append(card)
        if scope in {"global", "combined"}:
            # ``area`` may be either a downloadable package identity (the
            # Library card route) or a scientific Area label (the Explorer
            # facet).  The registry owns the former; package payloads own the
            # latter, so filter after the bounded registry projection.
            for row in self.registry.browse(limit=500)["items"]:
                card = self._global_card(row)
                if package_id and package_id != row["area"]:
                    continue
                if area and area != row["area"] and area not in card["area_labels"]:
                    continue
                if claim_type and card["claim_type"] != claim_type:
                    continue
                if evidence_status and card["evidence_status"] != evidence_status:
                    continue
                if human_review and card["human_review_status"] != human_review:
                    continue
                if card["supporting_work_count"] < minimum_supporting_papers:
                    continue
                card["_relevance"] = self._relevance(card, query_terms)
                if query_terms and card["_relevance"] <= 0:
                    continue
                cards.append(card)
        reverse = sort not in {"title"}

        def key(card: dict[str, Any]) -> tuple[Any, ...]:
            if sort == "relevance":
                value: Any = card["_relevance"]
            elif sort == "reliability":
                value = card["reliability_score"] if card["reliability_score"] is not None else -1
            elif sort == "influence":
                value = card["influence_score"] if card["influence_score"] is not None else -1
            elif sort == "supporting_papers":
                value = card["supporting_work_count"]
            elif sort == "title":
                value = card["title"].casefold()
            else:
                value = card["updated_at"]
            return value, card["id"]

        cards.sort(key=key, reverse=reverse)
        after_id = _after_id(cursor, sort)
        start = (resolved_page - 1) * resolved_limit
        if after_id:
            try:
                start = (
                    next(index for index, card in enumerate(cards) if card["id"] == after_id) + 1
                )
            except StopIteration as exc:
                raise ValueError("the Principles cursor no longer matches this library") from exc
        page_cards = cards[start : start + resolved_limit]
        self._attach_relation_previews(page_cards)
        for card in page_cards:
            card.pop("_relevance", None)
        next_cursor = (
            _cursor(page_cards[-1]["id"], sort)
            if page_cards and start + len(page_cards) < len(cards)
            else None
        )
        status = self.repository.relation_metric_status()
        metric_revision = status.get("metric_revision")
        for card in page_cards:
            if card["source"] == "local" and (
                card["influence_score"] is not None or card["reliability_score"] is not None
            ):
                card["metric_revision"] = metric_revision
        return {
            "items": page_cards,
            "next_cursor": next_cursor,
            "total": len(cards),
            "facets": self._facets(cards),
            "sort_explanation": self._sort_explanation(sort),
            "metric_status": status,
            "page": resolved_page,
            "page_size": resolved_limit,
            "page_count": math.ceil(len(cards) / resolved_limit) if cards else 0,
        }

    def relations(self, principle_id: str) -> dict[str, Any]:
        global_detail = self.registry.principle(principle_id)
        if global_detail is not None:
            items = []
            for relation in global_detail.get("relations") or []:
                related_id = str(relation.get("target_principle_id") or "")
                related = self.registry.principle(related_id) or {}
                items.append(
                    {
                        "relation_id": str(
                            relation.get("relation_id")
                            or f"package:{principle_id}:{related_id}:{relation.get('relation_type', '')}"
                        ),
                        "source_principle_id": principle_id,
                        "target_principle_id": related_id,
                        "relation_type": str(relation.get("relation_type") or "analogous_to"),
                        "direction": str(relation.get("direction") or "directed"),
                        "rationale": str(relation.get("rationale") or ""),
                        "validation_state": "validated",
                        "evidence_digest": str(relation.get("evidence_digest") or ""),
                        "related_principle_id": related_id,
                        "related_title": _readable_title(
                            related.get("title") or related_id,
                            related.get("claim") or "",
                        ),
                        "orientation": "outgoing",
                    }
                )
            return {
                "principle_id": principle_id,
                "items": items,
                "explanation": (
                    "Only relations carried by the verified package are shown. "
                    "Candidate packages remain unassessed despite their verified transport."
                ),
            }
        rows = self.repository.principle_relations(principle_id)
        items = []
        for row in rows:
            outgoing = row["source_principle_id"] == principle_id
            related_id = row["target_principle_id"] if outgoing else row["source_principle_id"]
            local_related = self.repository.candidate_detail(str(related_id))
            items.append(
                {
                    "relation_id": row["relation_id"],
                    "source_principle_id": row["source_principle_id"],
                    "target_principle_id": row["target_principle_id"],
                    "relation_type": row["relation_type"],
                    "direction": row["direction"],
                    "rationale": row["rationale"],
                    "validation_state": "validated",
                    "evidence_digest": row["evidence_digest"],
                    "related_principle_id": related_id,
                    "related_title": (
                        _readable_title(
                            local_related.get("title"), local_related.get("claim")
                        )
                        if local_related
                        else str(related_id)
                    ),
                    "orientation": "outgoing" if outgoing else "incoming",
                }
            )
        return {
            "principle_id": principle_id,
            "items": items,
            "explanation": (
                "Only validated scientific relations are shown. Proposed and shared-evidence "
                "connections do not affect library measures."
            ),
        }

    def graph_view(self, **filters: Any) -> dict[str, Any]:
        """Return the exact Explorer filter result as a bounded graph projection."""

        requested = max(1, min(int(filters.pop("limit", 120)), 200))
        page = self.browse(limit=requested, page=1, page_mode=False, **filters)
        nodes = list(page["items"])
        node_ids = {str(item["id"]) for item in nodes}
        edges = self.repository.graph_relations_for_principles(
            [str(item["id"]) for item in nodes if item["source"] == "local"]
        )
        for edge in edges:
            edge["edge_class"] = "validated"
            edge["strength"] = "strong"
            edge["shared_work_count"] = 0
        seen = {str(item["relation_id"]) for item in edges}
        for item in nodes:
            if item["source"] != "global":
                continue
            detail = (
                self.global_cloud.principle(str(item["id"]))
                if self.global_cloud is not None and self.global_cloud.active()
                else None
            ) or self.registry.principle(str(item["id"])) or {}
            for index, relation in enumerate(detail.get("relations") or []):
                source = str(relation.get("source_principle_id") or item["id"])
                target = str(relation.get("target_principle_id") or "")
                if target not in node_ids or target == item["id"]:
                    continue
                relation_type = str(relation.get("relation_type") or "analogous_to")
                relation_id = str(relation.get("relation_id") or f"global:{source}:{index}:{target}")
                if relation_id in seen:
                    continue
                seen.add(relation_id)
                edges.append(
                    {
                        "relation_id": relation_id,
                        "source": source,
                        "target": target,
                        "relation_type": relation_type,
                        "direction": "directed",
                        "rationale": str(relation.get("rationale") or ""),
                        "edge_class": "validated",
                        "strength": "strong",
                        "shared_work_count": 0,
                    }
                )
        self._add_context_edges(nodes, edges, seen)
        self._apply_graph_metrics(nodes, edges)
        edges.sort(key=lambda item: (item["source"], item["target"], item["relation_type"]))
        edge_counts = dict(Counter(str(item.get("edge_class") or "validated") for item in edges))
        return {
            "nodes": nodes,
            "edges": edges,
            "shown_count": len(nodes),
            "total_count": int(page["total"]),
            "truncated": int(page["total"]) > len(nodes),
            "maximum_nodes": requested,
            "explanation": (
                "Every node is one Principle in the current filtered Explorer view. "
                "Solid arrows are validated scientific relations. Dotted context links expose "
                "shared evidence or semantic affinity without changing scientific truth."
            ),
            "edge_counts": edge_counts,
        }

    def _add_context_edges(
        self,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        seen: set[str],
    ) -> None:
        """Add bounded, explicitly non-validated context when the graph is sparse."""

        node_by_id = {str(item["id"]): item for item in nodes}
        local_ids = [identifier for identifier, item in node_by_id.items() if item["source"] == "local"]
        validated_pairs = {
            frozenset({str(item["source"]), str(item["target"])}) for item in edges
        }
        work_members: dict[str, set[str]] = defaultdict(set)
        for link in self.repository.candidate_work_links(local_ids):
            work_members[str(link["work_id"])].add(str(link["candidate_id"]))
        shared_counts: Counter[tuple[str, str]] = Counter()
        for members in work_members.values():
            ordered = sorted(members)
            for index, source in enumerate(ordered):
                for target in ordered[index + 1 :]:
                    shared_counts[(source, target)] += 1
        derived_degree: Counter[str] = Counter()
        for (source, target), count in sorted(
            shared_counts.items(), key=lambda item: (-item[1], item[0])
        ):
            pair = frozenset({source, target})
            if pair in validated_pairs or derived_degree[source] >= 3 or derived_degree[target] >= 3:
                continue
            relation_id = "shared:" + hashlib.sha256(
                f"{source}\0{target}\0{count}".encode()
            ).hexdigest()[:20]
            if relation_id in seen:
                continue
            seen.add(relation_id)
            validated_pairs.add(pair)
            derived_degree[source] += 1
            derived_degree[target] += 1
            edges.append(
                {
                    "relation_id": relation_id,
                    "source": source,
                    "target": target,
                    "relation_type": "shared_evidence",
                    "direction": "undirected",
                    "rationale": (
                        f"These Principles cite {count} shared supporting paper"
                        f"{'s' if count != 1 else ''}. This is provenance context, not proof "
                        "that either Principle supports the other."
                    ),
                    "edge_class": "shared_evidence",
                    "strength": "strong" if count >= 3 else "moderate" if count == 2 else "weak",
                    "shared_work_count": count,
                }
            )

        affinity_candidates: list[tuple[int, int, dict[str, Any]]] = []
        ordered_ids = sorted(node_by_id)
        for index, source in enumerate(ordered_ids):
            for target in ordered_ids[index + 1 :]:
                pair = frozenset({source, target})
                if pair in validated_pairs:
                    continue
                suggestion = self._potential_relation(
                    source,
                    target,
                    {"claim": node_by_id[source].get("claim"), "scope": node_by_id[source].get("applicability")},
                    {"claim": node_by_id[target].get("claim"), "scope": node_by_id[target].get("applicability")},
                )
                if suggestion["relation_type"] == "relationship_unclear" or suggestion["strength"] == "weak":
                    continue
                affinity_candidates.append(
                    (
                        0 if suggestion["strength"] == "strong" else 1,
                        -len(suggestion["shared_concepts"]),
                        suggestion,
                    )
                )
        maximum_affinities = min(80, max(12, len(nodes) * 2))
        added = 0
        for _, _, suggestion in sorted(
            affinity_candidates,
            key=lambda item: (item[0], item[1], item[2]["source"], item[2]["target"]),
        ):
            source = str(suggestion["source"])
            target = str(suggestion["target"])
            if derived_degree[source] >= 3 or derived_degree[target] >= 3:
                continue
            derived_degree[source] += 1
            derived_degree[target] += 1
            added += 1
            edges.append(
                {
                    "relation_id": "affinity:" + str(suggestion["relation_id"]).split(":")[-1],
                    "source": source,
                    "target": target,
                    "relation_type": "semantic_affinity",
                    "direction": "undirected",
                    "rationale": suggestion["rationale"],
                    "edge_class": "semantic_affinity",
                    "strength": suggestion["strength"],
                    "shared_work_count": 0,
                }
            )
            if added >= maximum_affinities:
                break

    @staticmethod
    def _apply_graph_metrics(
        nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
    ) -> None:
        """Project varied evidence and graph-relative metrics for this exact view."""

        by_id = {str(item["id"]): item for item in nodes}
        neighbors: dict[str, set[str]] = {identifier: set() for identifier in by_id}
        influence_weight: Counter[str] = Counter()
        supports: Counter[str] = Counter()
        contradicts: Counter[str] = Counter()
        class_weight = {"validated": 1.0, "shared_evidence": 0.55, "semantic_affinity": 0.28}
        for edge in edges:
            source = str(edge["source"])
            target = str(edge["target"])
            if source not in by_id or target not in by_id or source == target:
                continue
            edge_class = str(edge.get("edge_class") or "validated")
            weight = class_weight.get(edge_class, 0.2)
            neighbors[source].add(target)
            neighbors[target].add(source)
            influence_weight[source] += weight
            influence_weight[target] += weight
            if edge_class == "validated" and edge.get("relation_type") == "supports":
                supports[target] += 1
            elif edge_class == "validated" and edge.get("relation_type") == "contradicts":
                contradicts[target] += 1
        maximum = max(influence_weight.values(), default=0.0)
        for identifier, node in by_id.items():
            papers = int(node.get("supporting_work_count") or 0)
            anchors = int(node.get("evidence_anchor_count") or 0)
            reviewed = node.get("human_review_status") == "reviewed"
            evidence_score = (
                40
                + min(20.0, 9.0 * math.log2(1 + papers))
                + min(12.0, 5.0 * math.log2(1 + anchors))
                + (10.0 if reviewed else 2.0)
                + min(8.0, supports[identifier] * 3.0)
                - min(18.0, contradicts[identifier] * 6.0)
            )
            recorded = node.get("reliability_score")
            if recorded is not None:
                recorded_value = float(recorded)
                if recorded_value <= 1:
                    recorded_value *= 100
                evidence_score = 0.6 * evidence_score + 0.4 * recorded_value
            node["reliability_score"] = round(max(18.0, min(98.0, evidence_score)), 1)
            node["influence_score"] = (
                round(100 * influence_weight[identifier] / maximum, 1) if maximum else 0.0
            )
            node["distinct_neighbor_count"] = len(neighbors[identifier])
            node["incoming_support_count"] = supports[identifier]
            node["incoming_contradict_count"] = contradicts[identifier]

    def potential_relations(self, principle_ids: list[str]) -> dict[str, Any]:
        """Compare a small, explicit selection without mutating scientific truth.

        These suggestions are a transient Explorer aid.  They are intentionally
        derived outside the validated relation store, excluded from metric
        snapshots, and bounded to fifteen pairs per request.
        """

        identifiers = list(dict.fromkeys(str(item) for item in principle_ids if item))
        if not 2 <= len(identifiers) <= 6:
            raise ValueError("Select between two and six Principles")
        details: dict[str, dict[str, Any]] = {}
        for identifier in identifiers:
            detail = self.repository.candidate_detail(identifier)
            if detail is None:
                detail = self.repository.principle(identifier)
            if detail is None:
                detail = self.registry.principle(identifier)
            if (
                detail is None
                and self.global_cloud is not None
                and self.global_cloud.active()
            ):
                detail = self.global_cloud.principle(identifier)
            if detail is None:
                raise KeyError(f"Principle {identifier} was not found")
            details[identifier] = detail

        validated_pairs: set[frozenset[str]] = set()
        for identifier in identifiers:
            for relation in self.repository.principle_relations(identifier):
                validated_pairs.add(
                    frozenset(
                        {
                            str(relation["source_principle_id"]),
                            str(relation["target_principle_id"]),
                        }
                    )
                )
            for relation in details[identifier].get("relations") or []:
                target = str(relation.get("target_principle_id") or "")
                if target:
                    validated_pairs.add(frozenset({identifier, target}))

        items: list[dict[str, Any]] = []
        skipped = 0
        for source, target in combinations(identifiers, 2):
            if frozenset({source, target}) in validated_pairs:
                skipped += 1
                continue
            items.append(self._potential_relation(source, target, details[source], details[target]))
        return {
            "items": items,
            "analyzed_pair_count": len(items),
            "skipped_validated_pair_count": skipped,
            "explanation": (
                "Virtual links are deterministic comparison hypotheses for this Graph view. "
                "They are not saved, do not affect Reliability or Influence, and require "
                "scientific review before becoming validated relations."
            ),
        }

    @staticmethod
    def _potential_relation(
        source: str,
        target: str,
        source_detail: dict[str, Any],
        target_detail: dict[str, Any],
    ) -> dict[str, Any]:
        left = _argument_view(source_detail)
        right = _argument_view(target_detail)
        subject = _similarity(left["subject"], right["subject"])
        driver = _similarity(left["driver"], right["driver"])
        outcome = _similarity(left["outcome"], right["outcome"])
        claim = _similarity(left["claim"], right["claim"])
        condition = _similarity(left["conditions"], right["conditions"])
        shared = sorted(
            (left["claim"] | left["subject"] | left["driver"] | left["outcome"])
            & (right["claim"] | right["subject"] | right["driver"] | right["outcome"])
        )[:8]
        alignment = max(claim, (subject + driver + outcome) / 3)
        opposite = left["direction"] and right["direction"] and left["direction"] != right["direction"]
        same_or_open = not left["direction"] or not right["direction"] or left["direction"] == right["direction"]

        if opposite and max(subject, outcome, claim) >= 0.14:
            relation_type = "potential_contradiction"
            score = max(subject, outcome, claim)
            rationale = (
                "The Principles discuss overlapping scientific concepts but express opposing "
                "directions. This may be a boundary-dependent contradiction; compare their "
                "conditions and source evidence."
            )
        elif same_or_open and subject >= 0.16 and outcome >= 0.16:
            relation_type = "potential_support"
            score = max(alignment, (subject + outcome) / 2)
            rationale = (
                "The Principles align on the scientific system and outcome without an obvious "
                "directional conflict. Review whether their evidence supports the same argument."
            )
        elif max(subject, driver, outcome) >= 0.18 and condition < 0.16:
            relation_type = "potential_refinement"
            score = max(alignment, subject, driver, outcome)
            rationale = (
                "The Principles share an argument component but differ in reported conditions. "
                "One may refine or bound the other rather than directly support it."
            )
        elif len(shared) >= 2 or claim >= 0.08:
            relation_type = "potential_analogy"
            score = max(alignment, min(0.4, len(shared) / 10))
            rationale = (
                "The Principles share scientific concepts, but the structured evidence is not "
                "strong enough to infer support, contradiction, or refinement."
            )
        else:
            relation_type = "relationship_unclear"
            score = alignment
            rationale = (
                "No strong structured relationship was detected. The temporary link is retained "
                "only as a human comparison note."
            )
        strength = "strong" if score >= 0.36 else "moderate" if score >= 0.17 else "weak"
        digest = hashlib.sha256(f"{source}\0{target}\0{relation_type}".encode()).hexdigest()[:20]
        return {
            "relation_id": f"virtual:{digest}",
            "source": source,
            "target": target,
            "relation_type": relation_type,
            "strength": strength,
            "rationale": rationale,
            "shared_concepts": shared,
            "status": "virtual_unvalidated",
            "persisted": False,
            "affects_metrics": False,
        }

    def _attach_relation_previews(self, cards: list[dict[str, Any]]) -> None:
        local_cards = [card for card in cards if card["source"] == "local"]
        previews = self.repository.principle_relation_previews(
            [str(card["id"]) for card in local_cards]
        )
        for card in cards:
            if card["source"] in {"global", "both"}:
                detail = self.registry.principle(str(card["id"])) or {}
                related = []
                for relation in detail.get("relations") or []:
                    related_id = str(relation.get("target_principle_id") or "")
                    related_detail = self.registry.principle(related_id) or {}
                    related.append(
                        {
                            "principle_id": related_id,
                            "title": _readable_title(
                                related_detail.get("title") or related_id,
                                related_detail.get("claim") or "",
                            ),
                            "relation_type": str(
                                relation.get("relation_type") or "analogous_to"
                            ),
                            "orientation": "outgoing",
                        }
                    )
            else:
                related = previews.get(str(card["id"]), [])
            card["validated_relation_count"] = len(related)
            card["related_principles"] = related[:3]

    def _goal_run_page(
        self,
        *,
        goal_run_id: str,
        membership: str,
        query_terms: set[str],
        area: str,
        claim_type: str,
        evidence_status: str,
        human_review: str,
        limit: int,
        page: int,
    ) -> dict[str, Any]:
        """Project a frozen goal-run membership into normal Explorer cards."""
        with self.repository.connect() as conn:
            if conn.execute(
                "SELECT 1 FROM research_goal_runs WHERE run_id=?", (goal_run_id,)
            ).fetchone() is None:
                raise KeyError(goal_run_id)
            rows = conn.execute(
                "SELECT payload_json FROM research_goal_memberships "
                "WHERE run_id=? AND membership=? ORDER BY rowid",
                (goal_run_id, membership),
            ).fetchall()
        payloads = [json.loads(row[0]) for row in rows]
        local_ids = {
            str(item.get("candidate_id") or item.get("id") or "")
            for item in payloads
            if str(item.get("source") or membership) == "local"
        }
        local_rows = {
            str(row["candidate_id"]): row
            for row in self.repository.principle_card_rows()
            if str(row["candidate_id"]) in local_ids
        }
        cards: list[dict[str, Any]] = []
        for payload in payloads:
            identifier = str(payload.get("candidate_id") or payload.get("principle_id") or payload.get("id") or "")
            origin = str(payload.get("source") or membership)
            if origin == "local" and identifier in local_rows:
                card = self._local_card(local_rows[identifier])
            else:
                card = self._global_cloud_card(payload)
                if origin == "both":
                    card["source"] = "both"
            if area and area not in card["area_labels"]:
                continue
            if claim_type and card["claim_type"] != claim_type:
                continue
            if evidence_status and card["evidence_status"] != evidence_status:
                continue
            if human_review and card["human_review_status"] != human_review:
                continue
            if query_terms and self._relevance(card, query_terms) <= 0:
                continue
            cards.append(card)
        start = (page - 1) * limit
        page_cards = cards[start : start + limit]
        self._attach_relation_previews(page_cards)
        return {
            "items": page_cards,
            "next_cursor": None,
            "total": len(cards),
            "facets": self._facets(cards),
            "sort_explanation": "Frozen membership and ranking from the pinned research-goal run.",
            "metric_status": self.repository.relation_metric_status(),
            "page": page,
            "page_size": limit,
            "page_count": math.ceil(len(cards) / limit) if cards else 0,
        }

    @staticmethod
    def _local_card(row: dict[str, Any]) -> dict[str, Any]:
        argument = json.loads(str(row.get("argument_json") or "{}"))
        state = str(row.get("quality_state") or "")
        virtual = str(row.get("source_kind") or "") == "virtual_reasoning" or str(
            row.get("extraction_mode") or ""
        ) == "virtual_synthesis"
        evidence_status = {
            "eligible": "checks_passed",
            "quarantined": "held_back",
            "pending_challenge": "checking",
            "legacy_needs_revalidation": "update_required",
            "archived": "archived",
        }.get(state, "update_required")
        assessment = str(row.get("assessment_status") or "unassessed")
        human_review = {
            "reviewed": "reviewed",
            "rejected": "rejected",
        }.get(assessment, "pending")
        support_count = int(row.get("supporting_work_count") or 0)
        area_labels = _csv(row.get("area_labels"))
        legacy_area = str(row.get("area") or "")
        if not area_labels and legacy_area and legacy_area != "uncategorized":
            area_labels = [legacy_area]
        conditions = list(argument.get("conditions") or [])
        boundary = list(argument.get("boundary") or [])
        has_title_slots = all(
            str(argument.get(key) or "").strip()
            for key in ("subject_system", "driver_or_intervention", "outcome")
        )
        return {
            "id": row["candidate_id"],
            "source": "local",
            "title": (
                concise_principle_title(argument)
                if has_title_slots
                and _readable_title(row["title"], row["claim"]).casefold()
                in {
                    " ".join(str(row["claim"] or "").split()).casefold(),
                    " ".join(str(row["claim"] or "").split()).split(".", 1)[0].casefold(),
                }
                else _readable_title(row["title"], row["claim"])
            ),
            "claim": row["claim"],
            "claim_type": "hypothesis" if virtual else str(row.get("claim_class") or ""),
            "applicability": "; ".join(conditions + boundary)[:1200],
            "area_labels": area_labels,
            "evidence_status": "checking" if virtual else evidence_status,
            "human_review_status": human_review,
            "evidence_scope": "multiple_works" if support_count > 1 else "one_work",
            "supporting_work_count": support_count,
            "evidence_anchor_count": int(row.get("evidence_anchor_count") or 0),
            "evidence_types": _csv(row.get("evidence_types")),
            "boundary_basis": str(argument.get("boundary_provenance") or ""),
            "test_basis": str(argument.get("testability_provenance") or ""),
            "context_relevance": str(row.get("context_relevance") or "not_evaluated"),
            "updated_at": row["updated_at"],
            "reliability_score": row.get("reliability_score"),
            "influence_score": row.get("influence_score"),
            "distinct_neighbor_count": int(row.get("distinct_neighbor_count") or 0),
            "incoming_support_count": int(row.get("incoming_support_count") or 0),
            "incoming_contradict_count": int(row.get("incoming_contradict_count") or 0),
            "validated_relation_count": 0,
            "related_principles": [],
            "metric_revision": None,
            "virtual": virtual,
        }

    @staticmethod
    def _global_card(row: dict[str, Any]) -> dict[str, Any]:
        unassessed = row.get("content_class") == "unassessed_candidates"
        labels = _csv(row.get("area_labels")) or [row["area"]]
        support_count = int(row.get("supporting_work_count") or 0)
        return {
            "id": row["principle_id"],
            "source": "global",
            "title": row["title"],
            "claim": row["claim"],
            "claim_type": row.get("claim_type") or row.get("kind") or "",
            "applicability": row.get("applicability") or (
                "Open the Principle to inspect its recorded scope."
                if unassessed
                else "Open the Principle to inspect its reviewed scope."
            ),
            "area_labels": labels,
            "evidence_status": "checks_passed",
            "human_review_status": "pending" if unassessed else "reviewed",
            "evidence_scope": "multiple_works" if support_count > 1 else "one_work",
            "supporting_work_count": support_count,
            "evidence_anchor_count": int(row.get("evidence_anchor_count") or 0),
            "evidence_types": [],
            "boundary_basis": "",
            "test_basis": "",
            "context_relevance": "not_evaluated",
            "updated_at": row["freshness"],
            "reliability_score": None,
            "influence_score": None,
            "distinct_neighbor_count": 0,
            "incoming_support_count": 0,
            "incoming_contradict_count": 0,
            "validated_relation_count": 0,
            "related_principles": [],
            "metric_revision": None,
            "virtual": False,
        }

    @staticmethod
    def _global_cloud_card(row: dict[str, Any]) -> dict[str, Any]:
        support_count = len(row.get("matched_papers") or [])
        scope = row.get("scope") or {}
        quality = row.get("quality") or {}
        return {
            "id": row["principle_id"],
            "source": "global",
            "title": row["title"],
            "claim": row["claim"],
            "claim_type": row.get("kind") or "",
            "applicability": scope.get("statement") or "Open the Principle to inspect its scope.",
            "area_labels": [row.get("area") or "global", *(row.get("tags") or [])],
            "evidence_status": "archived" if row.get("status") == "retired" else "checks_passed",
            "human_review_status": "reviewed" if row.get("review_status") == "reviewed" else "pending",
            "evidence_scope": "multiple_works" if support_count > 1 else "one_work",
            "supporting_work_count": support_count,
            "evidence_anchor_count": support_count,
            "evidence_types": [],
            "boundary_basis": "; ".join(scope.get("exclusions") or []),
            "test_basis": row.get("falsifier") or "",
            "context_relevance": row.get("match_path") or "not_evaluated",
            "updated_at": row.get("updated_at") or row.get("created_at") or "",
            "reliability_score": quality.get("validity"),
            "influence_score": None,
            "distinct_neighbor_count": 0,
            "incoming_support_count": 0,
            "incoming_contradict_count": 0,
            "validated_relation_count": 0,
            "related_principles": [],
            "metric_revision": None,
            "virtual": False,
        }

    @staticmethod
    def _relevance(card: dict[str, Any], query_terms: set[str]) -> float:
        if not query_terms:
            return 0
        title = set(_TOKEN.findall(str(card["title"]).casefold()))
        claim = set(
            _TOKEN.findall(
                " ".join(
                    [
                        str(card["claim"]),
                        str(card.get("applicability") or ""),
                        " ".join(card.get("area_labels") or []),
                        str(card.get("claim_type") or ""),
                    ]
                ).casefold()
            )
        )
        semantic_terms = _semantic_expansion(query_terms)
        exact = 2.0 * len(query_terms & title) + len(query_terms & claim)
        semantic = 0.5 * len(semantic_terms & title) + 0.25 * len(semantic_terms & claim)
        return exact + semantic

    @staticmethod
    def _facets(cards: list[dict[str, Any]]) -> dict[str, Any]:
        area_counts = Counter(area for card in cards for area in card["area_labels"])
        claim_type_counts = Counter(card["claim_type"] for card in cards if card["claim_type"])
        evidence_status_counts = Counter(card["evidence_status"] for card in cards)
        human_review_status_counts = Counter(card["human_review_status"] for card in cards)
        return {
            "areas": sorted(area_counts),
            "area_counts": dict(sorted(area_counts.items())),
            "claim_types": sorted(claim_type_counts),
            "claim_type_counts": dict(sorted(claim_type_counts.items())),
            "evidence_statuses": sorted(evidence_status_counts),
            "evidence_status_counts": dict(sorted(evidence_status_counts.items())),
            "human_review_statuses": sorted(human_review_status_counts),
            "human_review_status_counts": dict(sorted(human_review_status_counts.items())),
            "reliability_available_count": sum(
                card["reliability_score"] is not None for card in cards
            ),
            "influence_available_count": sum(
                card["influence_score"] is not None for card in cards
            ),
            "known_contradiction_count": sum(
                int(card["incoming_contradict_count"]) > 0 for card in cards
            ),
        }

    @staticmethod
    def _sort_explanation(sort: str) -> str:
        return {
            "relevance": "Best local semantic and text match; legacy package quality numbers do not affect ordering.",
            "reliability": "95% Wilson lower bound from validated incoming support and contradiction links.",
            "influence": "Distinct validated neighbors relative to the most connected Principle in this library.",
            "supporting_papers": "Distinct supporting papers, followed by stable Principle ID.",
            "title": "Alphabetical title order.",
            "updated": "Most recently updated first.",
        }.get(sort, "Most recently updated first.")
