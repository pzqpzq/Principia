from __future__ import annotations

import json
import re
from typing import Any

from .derivation_verifier import DerivationVerifier
from .global_store import GlobalStore
from .hybrid_retriever import HybridRetriever
from .lineage_graph import LineageGraphBuilder
from .models import utc_now
from .symbol_registry import SymbolRegistry
from .utils import compact_text, stable_id


class SymbolicIdeator:
    def __init__(self, store: GlobalStore, llm: Any | None = None):
        self.store = store
        self.llm = llm
        self.symbols = SymbolRegistry(store)
        self.verifier = DerivationVerifier()

    def generate(
        self,
        query: str,
        *,
        project_id: str = "default",
        selected_concepts: list[dict[str, Any]] | None = None,
        user_note: str = "",
        model_mode: str = "auto",
        offline: bool = False,
    ) -> dict[str, Any]:
        if not offline and (not self.llm or not self.llm.available()):
            raise RuntimeError("No callable LLM is configured. Principia Calculus will not use template fallback content; add an API key or run with offline=True.")
        concepts = selected_concepts or self._default_concepts(query, project_id)
        if not concepts and user_note:
            concepts = [
                self.store.upsert_concept(
                    "user_note",
                    {"title": "User research note", "summary": user_note, "source": "user"},
                    key_text=user_note,
                    source_origin="user_note",
                    validation_level="user_validated",
                    verification_status="user_validated",
                    public_scope="project_private",
                )
            ]
        if not concepts:
            raise RuntimeError("No concepts are available for symbolic generation. Run research or select evidence first.")

        symbol_rows = self.symbols.ensure_symbols(concepts, namespace=project_id or "global")
        symbol_table = self._symbol_table(concepts, symbol_rows)
        derivation_id = stable_id("DR", project_id, query, model_mode, utc_now())
        self._create_derivation(derivation_id, project_id, query, model_mode)
        try:
            patch = self._offline_patch(query, symbol_table, user_note) if offline else self._llm_patch(query, symbol_table, user_note, model_mode)
            if not offline:
                self._require_substantive_online_candidate(patch)
            patch = self._normalize_patch(patch, symbol_table, query=query, user_note=user_note)
            verified = self.verifier.verify_patch(patch, symbol_table)
            if not verified["ok"]:
                raise RuntimeError("Derivation patch failed verification: " + "; ".join(verified["errors"]))
            stored = self._store_verified_patch(derivation_id, verified["patch"], symbol_table, project_id=project_id, model_mode=model_mode)
            self._complete_derivation(derivation_id, "complete", warnings=verified["warnings"])
            graph = LineageGraphBuilder(self.store).derivation_graph(derivation_id)
            return {
                "ok": True,
                "generation_mode": "principia_calculus",
                "derivation_id": derivation_id,
                "symbol_table": list(symbol_table.values()),
                "idea": stored["idea"],
                "derived_nodes": stored["derived_nodes"],
                "graph": graph,
                "warnings": verified["warnings"],
            }
        except Exception as exc:
            self._complete_derivation(derivation_id, "error", warnings=[str(exc)])
            raise

    def _default_concepts(self, query: str, project_id: str) -> list[dict[str, Any]]:
        retrieval = HybridRetriever(self.store).retrieve(
            query,
            concept_types=["principle", "existed_idea", "takeaway_message", "benchmark", "baseline"],
            project_id=project_id,
            limit_per_type=4,
        )
        concepts: list[dict[str, Any]] = []
        for items in retrieval["results"].values():
            concepts.extend(items[:3])
        return concepts[:12]

    def _symbol_table(self, concepts: list[dict[str, Any]], symbol_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        by_concept = {row["concept_id"]: row for row in symbol_rows}
        table = {}
        for concept in concepts:
            symbol = by_concept.get(concept["concept_id"])
            if not symbol:
                continue
            table[symbol["short_code"]] = {
                "symbol": symbol["short_code"],
                "concept_id": concept["concept_id"],
                "concept_type": concept.get("concept_type"),
                "short_label": symbol.get("label"),
                "gloss": symbol.get("gloss"),
                "validation_level": concept.get("validation_level"),
                "source_origin": concept.get("source_origin"),
                "evidence_links": [link.get("evidence_id") for link in concept.get("evidence_links", [])],
            }
        return table

    def _llm_patch(self, query: str, symbol_table: dict[str, dict[str, Any]], user_note: str, model_mode: str) -> dict[str, Any]:
        compact_symbols = list(symbol_table.values())[:16]
        try:
            return self.llm.chat_json(
                "You are Principia Calculus. Return only compact verified JSON derivation patches.",
                (
                    "Create a symbolic derivation patch with keys reasoning_plan, new_nodes, new_edges, candidate_ideas. "
                    "Each new_nodes item must use node_type, not type. Use supplied symbols as primary support, and later derived nodes may cite earlier derived nodes as support for higher-order reasoning. New speculative nodes must be L0 and "
                    "validation_status speculative_unverified. Expressions must use compose, stress_test, "
                    "contrast, specialize, branch, critique, prune, revise, merge, select, or feedback_loop. Each candidate idea must include derived_from referencing at least one new node symbol. "
                    "Use adaptive-order calculus, not a fixed L1->L2->L3->L4->L5 ladder. First write reasoning_plan.target_depth and reasoning_plan.depth_rationale from the goal, evidence diversity, conflicts, and uncertainty; allowed depth is 1-10, but finish at L1-L3 when that is enough. Use L4-L10 only when a surviving branch genuinely needs additional abstraction, critique, or synthesis. "
                    "Explore 2-4 competing reasoning branches when evidence supports multiple plausible paths. New nodes should include branch_id and branch_status kept|revised|pruned|merged|final_support. Prune weak branches explicitly through critique or pruning_decision nodes instead of forcing every branch into the final idea. "
                    "Add speculation_depth to each node where source evidence is L0, first derived nodes are usually L1, and nodes depending on prior derived nodes may have higher depth. Do not create every integer depth just to look systematic; skip depths or stop early when justified. No node may exceed depth 10. "
                    "Use self_feedback and critique fields on derived nodes to explain why a branch is kept, revised, or rejected. It is acceptable to change direction mid-derivation when a critique exposes weak novelty, weak grounding, or poor validation feasibility. "
                    "If there are 3 or more derived nodes, include at least one explicit critique/self_feedback/pruning node or a candidate_ideas.reasoning_trace explaining why branching was unnecessary. "
                    "The final candidate idea should cite only the strongest surviving derived node(s), not every intermediate step. "
                    "Do not create multiple derived nodes with the same summary, expression, or support set. Each derived node must represent a distinct reasoning operation. "
                    "Each derived node summary must be 2-3 concrete sentences explaining what is inferred, how the support symbols combine or conflict, and why this step matters. "
                    "Every selected source symbol that actually contributes must appear in at least one edge; omit unused symbols instead of pretending they contributed. "
                    "Each candidate idea must be presentation-ready, not a placeholder: include title, one_sentence_thesis, novelty_claim, "
                    "mechanistic_design(list), method_variants(list), why_it_might_work(list), validation_protocol(list), relevant_baselines(list), "
                    "metrics(list), risks(list), derived_principles(list), and cheapest_falsification. "
                    "mechanistic_design must read like a concise methodology section: include variables/data structures, an algorithmic loop, a scoring or update rule only when it is technically necessary, and variable definitions; write formulas in paper-ready LaTeX using $...$ or $$...$$. Do not describe derivation graph nodes, do not start items with 'this node', and do not use lineage-node summaries as the method. "
                    "Selected symbols are inspiration and constraints, not prose to copy. The final candidate must introduce at least one new mechanism, representation, objective, or inference-time control loop that is not already present in the supplied symbols. Remove copied method names except as explicit prior-work citations. Replace decorative or undefined formulas with precise algorithmic prose. method_variants must include 2-4 concrete alternatives or ablations. "
                    "Each candidate idea must include reasoning_trace as 3-6 concise bullets covering branch exploration, critique/pruning, self-feedback, and why the final branch survived. "
                    "derived_principles and relevant_baselines must include symbol plus full argument/method text, not bare symbols. "
                    "Do not invent performance numbers, percentages, or ranges unless they appear verbatim in the supplied symbols. "
                    "Keep the derivation as compact as the evidence permits, but make the final idea card concrete, evidence-specific, and non-template.\n\n"
                    f"Query: {query}\nUser note: {user_note}\nSymbols: {json.dumps(compact_symbols, ensure_ascii=False)}"
                ),
                complexity=0.84,
                mode=model_mode,
                max_tokens=3800,
                temperature=0.25,
            )
        except Exception as exc:
            raise RuntimeError(f"Principia Calculus LLM call failed; no fallback idea was generated. {exc}") from exc

    def _require_substantive_online_candidate(self, patch: dict[str, Any]) -> None:
        raw_ideas = patch.get("candidate_ideas") if isinstance(patch, dict) else None
        if not isinstance(raw_ideas, list) or not raw_ideas:
            raise RuntimeError("Principia Calculus LLM returned no candidate idea; no template fallback was generated.")
        first = raw_ideas[0] if isinstance(raw_ideas[0], dict) else {}
        text_fields = [
            str(first.get("title") or ""),
            str(first.get("one_sentence_thesis") or first.get("thesis") or ""),
            str(first.get("novelty_claim") or ""),
            " ".join(str(item) for item in first.get("mechanistic_design", []) or []),
        ]
        if len(" ".join(text_fields).strip()) < 80:
            raise RuntimeError("Principia Calculus LLM returned an underspecified candidate idea; no template fallback was generated.")

    def _offline_patch(self, query: str, symbol_table: dict[str, dict[str, Any]], user_note: str) -> dict[str, Any]:
        symbols = list(symbol_table)
        support = symbols[:2] if len(symbols) >= 2 else symbols
        risk = symbols[2:3]
        d_symbol = "D.OFF"
        i_symbol = "I.OFF"
        title_seed = compact_text(user_note or query, 70) or "Principia Calculus Idea"
        return {
            "new_nodes": [
                {
                    "symbol": d_symbol,
                    "node_type": "derived_concept",
                    "expression": f"compose({', '.join(support)})" if support else "compose()",
                    "summary": "Offline symbolic derivation created from explicitly selected evidence; this is marked as speculative.",
                    "support_symbols": support,
                    "risk_symbols": risk,
                    "validation_status": "speculative_unverified",
                    "confidence": 0.35,
                    "cheapest_falsification": "Compare the candidate against the strongest selected baseline on the smallest fair validation slice.",
                }
            ],
            "new_edges": [
                {
                    "source": symbol,
                    "target": d_symbol,
                    "relation": "composes",
                    "rationale": "The selected concept contributes a reusable mechanism or constraint.",
                }
                for symbol in support
            ],
            "candidate_ideas": [
                {
                    "symbol": i_symbol,
                    "title": f"Symbolic Lineage Variant for {title_seed}",
                    "derived_from": [d_symbol],
                    "one_sentence_thesis": "Use the selected principle lineage as a compact controller for a falsifiable research variant.",
                }
            ],
        }

    def _normalize_patch(self, patch: dict[str, Any], symbol_table: dict[str, dict[str, Any]], *, query: str, user_note: str) -> dict[str, Any]:
        patch = dict(patch or {})
        known_symbols = set(symbol_table)
        allowed_node_types = {
            "derived_concept",
            "argument",
            "hypothesis",
            "deduction",
            "constraint",
            "failure_mode",
            "idea_seed",
            "branch",
            "critique",
            "pruning_decision",
            "self_feedback",
            "synthesis",
            "final_idea",
        }
        allowed_operators = {
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
        }
        raw_nodes = patch.get("new_nodes") if isinstance(patch.get("new_nodes"), list) else []
        support_default = list(symbol_table)[:2]
        normalized_nodes: list[dict[str, Any]] = []
        used_symbols: set[str] = set()
        used_node_signatures: set[str] = set()
        for index, raw in enumerate(raw_nodes, start=1):
            if not isinstance(raw, dict):
                continue
            prior_derived_symbols = set(used_symbols)
            symbol = str(raw.get("symbol") or raw.get("id") or raw.get("code") or f"D{index}").strip()
            symbol = re.sub(r"\s+", "_", symbol)[:32] or f"D{index}"
            if symbol in known_symbols or symbol in used_symbols:
                symbol = f"D{index}"
            node_type = str(raw.get("node_type") or raw.get("type") or raw.get("kind") or "derived_concept").strip()
            if node_type not in allowed_node_types:
                node_type = "derived_concept"
            supports = self._normalize_symbol_list(raw.get("support_symbols") or raw.get("support") or raw.get("sources"), known_symbols | prior_derived_symbols)
            if not supports:
                supports = support_default[:2]
            risks = self._normalize_symbol_list(raw.get("risk_symbols") or raw.get("risks"), known_symbols)
            expression = str(raw.get("expression") or "").strip()
            operator = re.findall(r"([A-Za-z_]+)\(", expression)
            if not expression or any(item not in allowed_operators for item in operator):
                expression = f"compose({', '.join(supports)})" if supports else "compose()"
            summary = compact_text(
                str(raw.get("summary") or raw.get("text") or raw.get("description") or raw.get("rationale") or user_note or query),
                520,
            )
            summary = self._enrich_node_summary(summary, expression, supports, symbol_table)
            summary = self._append_reasoning_annotations(summary, raw)
            signature = self._node_signature(summary, expression, supports)
            if signature in used_node_signatures:
                support_gloss = "; ".join(
                    compact_text(str(symbol_table.get(item, {}).get("gloss") or symbol_table.get(item, {}).get("short_label") or item), 120)
                    for item in supports[:3]
                )
                summary = self._enrich_node_summary(f"{expression}: {support_gloss or summary}", expression, supports, symbol_table)
                signature = self._node_signature(summary, expression, supports)
                if signature in used_node_signatures:
                    continue
            used_node_signatures.add(signature)
            used_symbols.add(symbol)
            normalized_nodes.append(
                {
                    **raw,
                    "symbol": symbol,
                    "node_type": node_type,
                    "expression": expression,
                    "summary": summary,
                    "support_symbols": supports,
                    "risk_symbols": risks,
                    "branch_id": compact_text(str(raw.get("branch_id") or raw.get("branch") or ""), 80),
                    "branch_status": compact_text(str(raw.get("branch_status") or raw.get("status") or ""), 80),
                    "critique": compact_text(str(raw.get("critique") or ""), 520),
                    "self_feedback": compact_text(str(raw.get("self_feedback") or raw.get("feedback") or ""), 520),
                    "pruning_rationale": compact_text(str(raw.get("pruning_rationale") or raw.get("prune_reason") or ""), 520),
                    "validation_status": "speculative_unverified",
                    "speculation_depth": self._normalize_depth(raw.get("speculation_depth") or 0),
                    "confidence": float(raw.get("confidence", 0.42) or 0.42),
                    "cheapest_falsification": raw.get("cheapest_falsification") or raw.get("falsification_path") or "",
                }
            )
        if not normalized_nodes:
            d_symbol = "D1"
            supports = support_default[:2]
            normalized_nodes.append(
                {
                    "symbol": d_symbol,
                    "node_type": "derived_concept",
                    "expression": f"compose({', '.join(supports)})" if supports else "compose()",
                    "summary": self._enrich_node_summary(compact_text(user_note or query, 520) or "Speculative symbolic composition from selected evidence.", f"compose({', '.join(supports)})" if supports else "compose()", supports, symbol_table),
                    "support_symbols": supports,
                    "risk_symbols": [],
                    "branch_id": "fallback",
                    "branch_status": "kept",
                    "critique": "",
                    "self_feedback": "Fallback derivation used the selected evidence directly because the LLM did not return a valid branch structure.",
                    "pruning_rationale": "",
                    "validation_status": "speculative_unverified",
                    "confidence": 0.38,
                    "cheapest_falsification": "",
                }
            )
        new_symbols = {node["symbol"] for node in normalized_nodes}
        raw_edges = patch.get("new_edges") if isinstance(patch.get("new_edges"), list) else []
        normalized_edges: list[dict[str, Any]] = []
        all_symbols = known_symbols | new_symbols
        seen_edges: set[tuple[str, str]] = set()
        for raw in raw_edges:
            if not isinstance(raw, dict):
                continue
            source = str(raw.get("source") or raw.get("from") or "").strip()
            target = str(raw.get("target") or raw.get("to") or "").strip()
            if source not in all_symbols or target not in all_symbols or source == target:
                continue
            if (source, target) in seen_edges:
                continue
            seen_edges.add((source, target))
            normalized_edges.append(
                {
                    "source": source,
                    "target": target,
                    "relation": raw.get("relation") or raw.get("type") or "supports",
                    "rationale": compact_text(raw.get("rationale") or raw.get("summary") or "Symbolic support relation.", 260),
                }
            )
        for node in normalized_nodes:
            for support in node.get("support_symbols") or []:
                if support in all_symbols and (support, node["symbol"]) not in seen_edges:
                    seen_edges.add((support, node["symbol"]))
                    normalized_edges.append(
                        {
                            "source": support,
                            "target": node["symbol"],
                            "relation": "composes",
                            "rationale": "Selected evidence contributes a specific mechanism or constraint to this derived node.",
                        }
                    )
        raw_ideas = patch.get("candidate_ideas") if isinstance(patch.get("candidate_ideas"), list) else []
        normalized_ideas: list[dict[str, Any]] = []
        fallback_parent = normalized_nodes[-1]["symbol"]
        for index, raw in enumerate(raw_ideas or [{}], start=1):
            if not isinstance(raw, dict):
                raw = {}
            symbol = str(raw.get("symbol") or raw.get("id") or f"I{index}").strip() or f"I{index}"
            symbol = re.sub(r"\s+", "_", symbol)[:32]
            derived_from = self._normalize_symbol_list(raw.get("derived_from") or raw.get("parents") or raw.get("support_symbols"), new_symbols)
            if not derived_from:
                derived_from = [fallback_parent]
            thesis = compact_text(
                str(raw.get("one_sentence_thesis") or raw.get("thesis") or raw.get("summary") or raw.get("description") or user_note or query),
                520,
            )
            title = compact_text(str(raw.get("title") or raw.get("candidate_title") or thesis or "Principia Calculus Idea"), 120)
            normalized_ideas.append(
                {
                    **raw,
                    "symbol": symbol,
                    "title": title,
                    "derived_from": derived_from,
                    "one_sentence_thesis": thesis,
                    "novelty_claim": compact_text(str(raw.get("novelty_claim") or raw.get("novelty") or ""), 900),
                    "mechanistic_design": self._normalize_text_list(raw.get("mechanistic_design") or raw.get("design") or raw.get("method_steps")),
                    "method_variants": self._normalize_text_list(raw.get("method_variants") or raw.get("variants") or raw.get("ablation_variants")),
                    "why_it_might_work": self._normalize_text_list(raw.get("why_it_might_work") or raw.get("rationale") or raw.get("expected_mechanism")),
                    "validation_protocol": self._normalize_text_list(raw.get("validation_protocol") or raw.get("validation") or raw.get("falsification_path") or raw.get("cheapest_falsification")),
                    "relevant_baselines": self._expand_symbol_list_items(self._normalize_text_list(raw.get("relevant_baselines") or raw.get("baselines")), symbol_table),
                    "reasoning_trace": self._normalize_text_list(raw.get("reasoning_trace") or raw.get("branching_summary") or raw.get("self_feedback") or raw.get("critique_summary"), limit=700),
                    "selected_branch_ids": self._normalize_text_list(raw.get("selected_branch_ids") or raw.get("surviving_branches") or raw.get("selected_branches"), limit=120),
                    "metrics": self._normalize_text_list(raw.get("metrics") or raw.get("success_metrics")),
                    "risks": self._normalize_text_list(raw.get("risks") or raw.get("failure_modes")),
                    "derived_principles": self._expand_symbol_list_items(self._normalize_text_list(raw.get("derived_principles") or raw.get("principles")), symbol_table),
                    "cheapest_falsification": compact_text(str(raw.get("cheapest_falsification") or raw.get("falsification_path") or ""), 520),
                }
            )
        return {**patch, "new_nodes": normalized_nodes, "new_edges": normalized_edges, "candidate_ideas": normalized_ideas}

    def _append_reasoning_annotations(self, summary: str, raw: dict[str, Any]) -> str:
        annotations: list[str] = []
        branch_id = compact_text(str(raw.get("branch_id") or raw.get("branch") or ""), 80)
        branch_status = compact_text(str(raw.get("branch_status") or raw.get("status") or ""), 80)
        critique = compact_text(str(raw.get("critique") or ""), 360)
        feedback = compact_text(str(raw.get("self_feedback") or raw.get("feedback") or ""), 360)
        pruning = compact_text(str(raw.get("pruning_rationale") or raw.get("prune_reason") or ""), 360)
        if branch_id or branch_status:
            annotations.append(f"Branch: {branch_id or 'unnamed'}" + (f" ({branch_status})." if branch_status else "."))
        if critique:
            annotations.append(f"Critique: {critique}")
        if feedback:
            annotations.append(f"Self-feedback: {feedback}")
        if pruning:
            annotations.append(f"Pruning rationale: {pruning}")
        if not annotations:
            return summary
        return compact_text(f"{summary.rstrip()} {' '.join(annotations)}", 1100)

    def _normalize_depth(self, value: Any) -> int:
        try:
            return max(0, min(int(value or 0), 10))
        except Exception:
            return 0

    def _enrich_node_summary(self, summary: str, expression: str, supports: list[str], symbol_table: dict[str, dict[str, Any]]) -> str:
        text = compact_text(str(summary or "").strip(), 520)
        sentence_count = len([part for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()])
        if sentence_count >= 2:
            return text
        support_glosses = [
            compact_text(str(symbol_table.get(symbol, {}).get("gloss") or symbol_table.get(symbol, {}).get("short_label") or symbol), 120)
            for symbol in supports[:3]
        ]
        support_text = "; ".join(item for item in support_glosses if item)
        extra = (
            f"It is derived by applying {expression or 'a composition operation'} to {', '.join(supports) or 'the selected evidence'}. "
            f"The supporting evidence says: {support_text}."
            if support_text
            else f"It is derived by applying {expression or 'a composition operation'} to the selected evidence and should be treated as an L0 hypothesis until falsified."
        )
        return compact_text(f"{text.rstrip('.')}. {extra}", 900)

    def _expand_symbol_list_items(self, items: list[str], symbol_table: dict[str, dict[str, Any]]) -> list[str]:
        output: list[str] = []
        for item in items:
            text = str(item or "").strip()
            match = re.match(r"^([A-Z][A-Z0-9_.-]{1,31})(?:\s*[:：-]\s*)?(.*)$", text)
            if match and match.group(1) in symbol_table and len(match.group(2).strip()) < 32:
                symbol = match.group(1)
                entry = symbol_table[symbol]
                gloss = entry.get("gloss") or entry.get("short_label") or symbol
                text = f"{symbol}: {gloss}"
            if text and text not in output:
                output.append(compact_text(text, 900))
        return output

    def _node_signature(self, summary: str, expression: str, supports: list[str]) -> str:
        _ = expression, supports
        words = re.findall(r"[a-z0-9]+", str(summary or "").lower())
        return " ".join(words[:28])

    def _normalize_text_list(self, value: Any, *, limit: int = 520) -> list[str]:
        if isinstance(value, list):
            raw_items = value
        elif isinstance(value, str) and value.strip():
            raw_items = re.split(r"\n+|(?<=[.;])\s+(?=[A-Z0-9])", value)
        else:
            raw_items = []
        output: list[str] = []
        for item in raw_items:
            text = compact_text(str(item or "").strip(), limit).rstrip()
            if text and text not in output:
                output.append(text)
        return output

    def _normalize_symbol_list(self, value: Any, allowed: set[str]) -> list[str]:
        if isinstance(value, str):
            raw_items = re.split(r"[,;\s]+", value)
        elif isinstance(value, list):
            raw_items = value
        else:
            raw_items = []
        output: list[str] = []
        for item in raw_items:
            symbol = item.get("symbol") if isinstance(item, dict) else item
            symbol = str(symbol or "").strip()
            if symbol in allowed and symbol not in output:
                output.append(symbol)
        return output

    def _create_derivation(self, derivation_id: str, project_id: str, query: str, model_mode: str) -> None:
        with self.store._connect() as conn:
            conn.execute(
                """
                INSERT INTO derivation_run(
                    derivation_id, project_id, query, generation_mode, llm_provider,
                    llm_model, prompt_version, status, created_at
                )
                VALUES (?, ?, ?, 'principia_calculus', ?, ?, 'v1-symbolic-patch', 'running', ?)
                """,
                (derivation_id, project_id, query, "offline" if not self.llm else getattr(self.llm, "model_label", lambda **_: "unknown")(mode=model_mode), model_mode, utc_now()),
            )

    def _complete_derivation(self, derivation_id: str, status: str, *, warnings: list[str]) -> None:
        with self.store._connect() as conn:
            conn.execute(
                "UPDATE derivation_run SET status = ?, warnings_json = ?, completed_at = ? WHERE derivation_id = ?",
                (status, json.dumps(warnings, ensure_ascii=False), utc_now(), derivation_id),
            )

    def _store_verified_patch(
        self,
        derivation_id: str,
        patch: dict[str, Any],
        symbol_table: dict[str, dict[str, Any]],
        *,
        project_id: str,
        model_mode: str,
    ) -> dict[str, Any]:
        symbol_to_node: dict[str, str] = {}
        with self.store._connect() as conn:
            for symbol, entry in symbol_table.items():
                node_id = stable_id("DN", derivation_id, symbol)
                symbol_to_node[symbol] = node_id
                conn.execute(
                    """
                    INSERT OR IGNORE INTO derivation_node(
                        node_id, derivation_id, concept_id, node_type, symbol_code,
                        expression, natural_language_summary, validation_status,
                        speculation_depth, confidence, verifier_status, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 1.0, 'evidence_backed', ?)
                    """,
                    (
                        node_id,
                        derivation_id,
                        entry.get("concept_id"),
                        entry.get("concept_type") or "evidence_card",
                        symbol,
                        symbol,
                        entry.get("gloss") or entry.get("short_label") or "",
                        entry.get("validation_level") or "extracted_unverified",
                        utc_now(),
                    ),
                )

        derived_nodes: list[dict[str, Any]] = []
        depth_by_symbol: dict[str, int] = {symbol: 0 for symbol in symbol_table}
        for raw_node in patch.get("new_nodes", []) or []:
            support_symbols = raw_node.get("support_symbols") or []
            raw_depth = self._normalize_depth(raw_node.get("speculation_depth") or 0)
            computed_depth = 1 + max([depth_by_symbol.get(str(symbol), 0) for symbol in support_symbols] or [0])
            speculation_depth = max(1, min(max(raw_depth, computed_depth), 10))
            payload = {
                "title": raw_node.get("symbol"),
                "summary": raw_node.get("summary") or "",
                "expression": raw_node.get("expression") or "",
                "support_symbols": support_symbols,
                "risk_symbols": raw_node.get("risk_symbols") or [],
                "branch_id": raw_node.get("branch_id") or "",
                "branch_status": raw_node.get("branch_status") or "",
                "critique": raw_node.get("critique") or "",
                "self_feedback": raw_node.get("self_feedback") or "",
                "pruning_rationale": raw_node.get("pruning_rationale") or "",
                "cheapest_falsification": raw_node.get("cheapest_falsification") or "",
                "confidence_score": raw_node.get("confidence", 0.4),
                "speculation_depth": speculation_depth,
            }
            concept = self.store.upsert_concept(
                raw_node.get("node_type") or "derived_concept",
                payload,
                key_text=f"{raw_node.get('symbol')} {payload['summary']}",
                source_origin="llm_derived",
                validation_level="L0",
                verification_status="speculative_unverified",
                public_scope="symbolic_scratch",
                model_mode=model_mode,
            )
            derived_nodes.append(concept)
            with self.store._connect() as conn:
                node_id = stable_id("DN", derivation_id, raw_node.get("symbol"))
                symbol_to_node[raw_node.get("symbol")] = node_id
                conn.execute(
                    """
                    INSERT OR REPLACE INTO derivation_node(
                        node_id, derivation_id, concept_id, node_type, symbol_code,
                        expression, natural_language_summary, validation_status,
                        speculation_depth, confidence, verifier_status, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'speculative_unverified', ?, ?, 'verified', ?)
                    """,
                    (
                        node_id,
                        derivation_id,
                        concept["concept_id"],
                        raw_node.get("node_type") or "derived_concept",
                        raw_node.get("symbol"),
                        raw_node.get("expression") or "",
                        raw_node.get("summary") or "",
                        speculation_depth,
                        float(raw_node.get("confidence", 0.4) or 0.4),
                        utc_now(),
                    ),
                )
            depth_by_symbol[str(raw_node.get("symbol") or "")] = speculation_depth
        idea = self._store_final_idea(derivation_id, patch, symbol_to_node, project_id=project_id, model_mode=model_mode)
        with self.store._connect() as conn:
            for edge in patch.get("new_edges", []) or []:
                source = symbol_to_node.get(edge.get("source"))
                target = symbol_to_node.get(edge.get("target"))
                if not source or not target:
                    continue
                edge_id = stable_id("DE", derivation_id, source, target, edge.get("relation", "supports"))
                conn.execute(
                    """
                    INSERT OR IGNORE INTO derivation_edge(edge_id, derivation_id, source_node_id, target_node_id, relation_type, rationale, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (edge_id, derivation_id, source, target, edge.get("relation") or "supports", edge.get("rationale") or "", utc_now()),
                )
        return {"idea": idea, "derived_nodes": derived_nodes}

    def _store_final_idea(self, derivation_id: str, patch: dict[str, Any], symbol_to_node: dict[str, str], *, project_id: str, model_mode: str) -> dict[str, Any]:
        raw = (patch.get("candidate_ideas") or [{}])[0]
        title = raw.get("title") or "Principia Calculus Idea"
        payload = {
            **raw,
            "title": title,
            "symbol": raw.get("symbol") or "I.FINAL",
            "one_sentence_thesis": raw.get("one_sentence_thesis") or "",
            "novelty_claim": raw.get("novelty_claim") or "",
            "mechanistic_design": raw.get("mechanistic_design") or [],
            "method_variants": raw.get("method_variants") or [],
            "why_it_might_work": raw.get("why_it_might_work") or [],
            "validation_protocol": raw.get("validation_protocol") or [],
            "relevant_baselines": raw.get("relevant_baselines") or [],
            "reasoning_trace": raw.get("reasoning_trace") or [],
            "selected_branch_ids": raw.get("selected_branch_ids") or [],
            "metrics": raw.get("metrics") or [],
            "risks": raw.get("risks") or [],
            "derived_principles": raw.get("derived_principles") or [],
            "cheapest_falsification": raw.get("cheapest_falsification") or "",
            "derived_from": raw.get("derived_from") or [],
            "generation_mode": "principia_calculus",
            "derivation_id": derivation_id,
            "validation_status": "speculative_unverified",
            "source_origin": "llm_derived",
        }
        idea = self.store.upsert_concept(
            "generated_idea",
            payload,
            key_text=f"{title} {derivation_id}",
            source_origin="llm_derived",
            validation_level="L0",
            verification_status="speculative_unverified",
            public_scope="project_private",
            model_mode=model_mode,
        )
        self.store.add_project_membership(project_id, "generated_idea", idea["concept_id"], source="principia_calculus", display_order=0)
        with self.store._connect() as conn:
            node_id = stable_id("DN", derivation_id, raw.get("symbol") or idea["concept_id"])
            symbol_to_node[raw.get("symbol") or idea["concept_id"]] = node_id
            final_depth = 1 + max([self._node_depth(conn, derivation_id, symbol_to_node.get(parent_symbol, "")) for parent_symbol in raw.get("derived_from") or []] or [1])
            conn.execute(
                """
                INSERT OR REPLACE INTO derivation_node(
                    node_id, derivation_id, concept_id, node_type, symbol_code, expression,
                    natural_language_summary, validation_status, speculation_depth, confidence,
                    verifier_status, created_at
                )
                VALUES (?, ?, ?, 'final_idea', ?, ?, ?, 'speculative_unverified', ?, 0.5, 'verified', ?)
                """,
                (
                    node_id,
                    derivation_id,
                    idea["concept_id"],
                    payload["symbol"],
                    "specialize(derived_concept)",
                    payload["one_sentence_thesis"],
                    final_depth,
                    utc_now(),
                ),
            )
            for parent_symbol in raw.get("derived_from") or []:
                source = symbol_to_node.get(parent_symbol)
                if not source:
                    continue
                edge_id = stable_id("DE", derivation_id, source, node_id, "leads_to")
                conn.execute(
                    "INSERT OR IGNORE INTO derivation_edge(edge_id, derivation_id, source_node_id, target_node_id, relation_type, rationale, created_at) VALUES (?, ?, ?, ?, 'leads_to', ?, ?)",
                    (edge_id, derivation_id, source, node_id, "Verified speculative derivation leads to final Idea Card.", utc_now()),
                )
        return idea

    def _node_depth(self, conn: Any, derivation_id: str, node_id: str) -> int:
        if not node_id:
            return 0
        row = conn.execute(
            "SELECT speculation_depth FROM derivation_node WHERE derivation_id = ? AND node_id = ?",
            (derivation_id, node_id),
        ).fetchone()
        return int(row["speculation_depth"] or 0) if row else 0
