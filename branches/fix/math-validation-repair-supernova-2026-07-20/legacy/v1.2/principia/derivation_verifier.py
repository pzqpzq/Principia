from __future__ import annotations

import re
from typing import Any


ALLOWED_NODE_TYPES = {
    "evidence_card",
    "existed_idea",
    "principle",
    "takeaway_message",
    "benchmark",
    "baseline",
    "derived_concept",
    "argument",
    "hypothesis",
    "deduction",
    "constraint",
    "failure_mode",
    "idea_seed",
    "final_idea",
    "branch",
    "critique",
    "pruning_decision",
    "self_feedback",
    "synthesis",
}

ALLOWED_EDGE_TYPES = {
    "supports",
    "composes",
    "transfers_to",
    "abstracts",
    "specializes",
    "contradicts",
    "warns_against",
    "resolves_tradeoff",
    "assumes",
    "falsifies",
    "validates",
    "leads_to",
    "derived_from",
    "branches_to",
    "critiques",
    "prunes",
    "revises",
    "merges",
    "selects",
    "feedback",
}

ALLOWED_OPERATORS = {
    "compose",
    "stress_test",
    "contrast",
    "specialize",
    "principle_transfer",
    "assumption_inversion",
    "contradiction_resolution",
    "mechanism_composition",
    "failure_mode_transplant",
    "evaluator_binding",
    "branch",
    "critique",
    "prune",
    "revise",
    "merge",
    "select",
    "feedback_loop",
    "synthesis",
}


class DerivationVerifier:
    def verify_patch(self, patch: dict[str, Any], symbol_table: dict[str, dict[str, Any]]) -> dict[str, Any]:
        errors: list[str] = []
        warnings: list[str] = []
        known_symbols = set(symbol_table)
        new_symbols: set[str] = set()

        for node in patch.get("new_nodes", []) or []:
            symbol = str(node.get("symbol") or "").strip()
            if not symbol:
                errors.append("node missing symbol")
                continue
            if symbol in known_symbols or symbol in new_symbols:
                errors.append(f"duplicate symbol: {symbol}")
            new_symbols.add(symbol)
            if node.get("node_type") not in ALLOWED_NODE_TYPES:
                errors.append(f"unsupported node type for {symbol}: {node.get('node_type')}")
            for support in node.get("support_symbols", []) or []:
                if support not in known_symbols and support not in new_symbols:
                    errors.append(f"{symbol} references unknown support symbol {support}")
            for risk in node.get("risk_symbols", []) or []:
                if risk not in known_symbols and risk not in new_symbols:
                    warnings.append(f"{symbol} references unknown risk symbol {risk}")
            expression = str(node.get("expression") or "")
            for operator in re.findall(r"([A-Za-z_]+)\(", expression):
                if operator not in ALLOWED_OPERATORS:
                    errors.append(f"{symbol} uses unsupported operator {operator}")
            if node.get("node_type") in {"derived_concept", "argument", "hypothesis", "deduction", "idea_seed", "final_idea"}:
                node["validation_status"] = "speculative_unverified"
                node["source_origin"] = "llm_derived"

        all_symbols = known_symbols | new_symbols
        for edge in patch.get("new_edges", []) or []:
            source = str(edge.get("source") or "")
            target = str(edge.get("target") or "")
            if source not in all_symbols:
                errors.append(f"edge references unknown source {source}")
            if target not in all_symbols:
                errors.append(f"edge references unknown target {target}")
            if edge.get("relation") not in ALLOWED_EDGE_TYPES:
                warnings.append(f"edge relation {edge.get('relation')} will be stored but needs review")

        for idea in patch.get("candidate_ideas", []) or []:
            derived_from = idea.get("derived_from") or []
            if not derived_from:
                errors.append(f"candidate idea {idea.get('symbol') or idea.get('title')} lacks derived_from")
            for symbol in derived_from:
                if symbol not in all_symbols:
                    errors.append(f"candidate idea references unknown symbol {symbol}")

        return {
            "ok": not errors,
            "errors": errors,
            "warnings": warnings,
            "patch": patch,
        }
