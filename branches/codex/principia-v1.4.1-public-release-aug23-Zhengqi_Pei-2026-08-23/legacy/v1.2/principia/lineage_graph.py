from __future__ import annotations

import re
from typing import Any

from .global_store import GlobalStore
from .utils import compact_text


class LineageGraphBuilder:
    def __init__(self, store: GlobalStore):
        self.store = store

    def derivation_graph(self, derivation_id: str) -> dict[str, Any]:
        with self.store._connect() as conn:
            run = conn.execute("SELECT * FROM derivation_run WHERE derivation_id = ?", (derivation_id,)).fetchone()
            if not run:
                return {"nodes": [], "edges": [], "derivation": None}
            nodes = [dict(row) for row in conn.execute("SELECT * FROM derivation_node WHERE derivation_id = ? ORDER BY speculation_depth, created_at", (derivation_id,)).fetchall()]
            edges = [dict(row) for row in conn.execute("SELECT * FROM derivation_edge WHERE derivation_id = ? ORDER BY created_at", (derivation_id,)).fetchall()]
        connected_node_ids = {
            node_id
            for edge in edges
            for node_id in (edge.get("source_node_id"), edge.get("target_node_id"))
            if node_id
        }
        visible_nodes = [
            node
            for node in nodes
            if node.get("node_id") in connected_node_ids or node.get("node_type") == "final_idea"
        ]
        visible_node_ids = {node.get("node_id") for node in visible_nodes}
        visible_edges = [
            edge
            for edge in edges
            if edge.get("source_node_id") in visible_node_ids and edge.get("target_node_id") in visible_node_ids
        ]
        visible_nodes = self._repair_duplicate_display_summaries(visible_nodes)
        return {
            "derivation": dict(run),
            "nodes": [
                {
                    "id": node["node_id"],
                    "label": node.get("symbol_code") or node.get("node_id"),
                    "type": node.get("node_type"),
                    "summary": node.get("natural_language_summary"),
                    "validation_status": node.get("validation_status"),
                    "verifier_status": node.get("verifier_status"),
                    "speculation_depth": node.get("speculation_depth", 0),
                    "concept_id": node.get("concept_id"),
                    "expression": node.get("expression"),
                }
                for node in visible_nodes
            ],
            "edges": [
                {
                    "id": edge["edge_id"],
                    "source": edge["source_node_id"],
                    "target": edge["target_node_id"],
                    "label": edge.get("relation_type"),
                    "rationale": edge.get("rationale"),
                }
                for edge in visible_edges
            ],
        }

    def idea_lineage(self, idea_id: str) -> dict[str, Any]:
        with self.store._connect() as conn:
            node = conn.execute(
                "SELECT derivation_id FROM derivation_node WHERE concept_id = ? ORDER BY created_at DESC LIMIT 1",
                (idea_id,),
            ).fetchone()
        if not node:
            return {"nodes": [], "edges": [], "derivation": None}
        return self.derivation_graph(node["derivation_id"])

    def _repair_duplicate_display_summaries(self, nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        summary_counts: dict[str, int] = {}
        for node in nodes:
            summary = self._summary_key(node.get("natural_language_summary", ""))
            if node.get("node_type") in {"derived_concept", "argument", "hypothesis", "deduction", "constraint", "failure_mode", "idea_seed"}:
                summary_counts[summary] = summary_counts.get(summary, 0) + 1
        by_symbol = {node.get("symbol_code"): node for node in nodes if node.get("symbol_code")}
        repaired: list[dict[str, Any]] = []
        for node in nodes:
            item = dict(node)
            summary = self._summary_key(item.get("natural_language_summary", ""))
            if summary_counts.get(summary, 0) > 1:
                expression = str(item.get("expression") or "").strip()
                operator = re.match(r"([A-Za-z_]+)\((.*)\)", expression)
                if operator:
                    args = [arg.strip().strip('"') for arg in operator.group(2).split(",") if arg.strip()]
                    glosses = [
                        compact_text(str(by_symbol.get(arg, {}).get("natural_language_summary") or arg), 82)
                        for arg in args[:3]
                    ]
                    operation = operator.group(1).replace("_", " ")
                    item["natural_language_summary"] = compact_text(
                        f"{item.get('symbol_code') or 'Derived node'} applies {operation} to {', '.join(args)}"
                        + (f": {'; '.join(glosses)}." if glosses else "."),
                        420,
                    )
            repaired.append(item)
        return repaired

    def _summary_key(self, value: Any) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", str(value or "").lower())[:32])
