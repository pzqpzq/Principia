from __future__ import annotations

import json
import re
from typing import Any

from ._llm_progress import call_with_progress
from .features import FEATURE_KINDS, feature_record_text, source_evidence_rows
from .ids import readable_id
from .llm import LLMClient, redact_secrets
from .models import (
    CancelToken,
    EvidencePacket,
    ExtractedFeatures,
    Idea,
    IdeaComparison,
    WorkFeatures,
    WorkItem,
    WorkList,
)
from .research import lexical_score
from .run import ProgressCallback, RunHandle
from .storage import WorkspaceStorage

MODE_ALIASES = {
    "standard": "standard",
    "calculus": "calculus",
    "principia_calculus": "calculus",
    "scidialect": "scidialect_evo",
    "sci-dialect": "scidialect_evo",
    "scidialect_evo": "scidialect_evo",
    "scidialect-evo": "scidialect_evo",
}
SCIDIALECT_PATTERN = re.compile(r"\b(?:sci[-_\s]?dialect(?:[-_\s]?evo)?|scidialect(?:[_-]evo)?)\b", re.I)
DIALECT_PATTERN = re.compile(r"\bdialect(?:ic|ical|s)?\b", re.I)


class IdeaService:
    def __init__(self, storage: WorkspaceStorage, llm: LLMClient) -> None:
        self.storage = storage
        self.llm = llm

    def generate(
        self,
        evidences: ExtractedFeatures | EvidencePacket | list[WorkFeatures],
        *,
        user_note: str = "",
        mode: str = "calculus",
        model: str = "auto",
        offline: bool = False,
        overwrite: bool = False,
        show_progress: bool = False,
        callback: ProgressCallback | None = None,
        cancel_token: CancelToken | None = None,
    ) -> Idea:
        normalized_mode = MODE_ALIASES.get(str(mode or "").lower().replace(" ", "_"), "")
        if normalized_mode not in {"standard", "calculus", "scidialect_evo"}:
            raise ValueError("mode must be standard, calculus, or scidialect_evo")
        packet = self._packet(evidences, user_note=user_note)
        model_label = self.llm.resolve(model).label
        with RunHandle(self.storage, f"ideas.generate.{normalized_mode}", callback=callback, token=cancel_token, show_progress=show_progress) as run:
            run.update("evidence_pack", "Packing selected evidence.", progress=0.1, evidence_items=len(packet.features))
            if self.llm.resolve(model).provider == "mock":
                payload = self.llm.chat_json("generate idea", self._prompt_packet(packet), model=model)
            elif offline:
                payload = deterministic_idea_payload(packet, normalized_mode)
            else:
                if not self.llm.available(model):
                    raise RuntimeError(
                        "No callable LLM is configured. Pass a valid API key through "
                        "pc.siliconflow_config(...), pc.LLMConfig(...), or provider environment variables."
                    )
                payload = call_with_progress(
                    run,
                    stage="llm_generation",
                    message=f"Calling {model_label} for evidence-grounded idea generation.",
                    progress_start=0.35,
                    progress_end=0.7,
                    estimated_seconds=150,
                    call=lambda: self.llm.chat_json(
                        "You generate one rigorous, evidence-grounded research Idea Card. Return strict JSON only.",
                        self._idea_prompt(packet, normalized_mode),
                        model=model,
                        max_tokens=4200,
                        temperature=0.22,
                    ),
                )
            run.update("quality_review", "Checking generated idea schema and grounding.", progress=0.72)
            idea = self._idea_from_payload(payload, packet, normalized_mode, model_label, run.status.run_id)
            _ = overwrite
            self.storage.save_idea(idea)
            run.update("complete", f"Saved idea {idea.id}.", progress=0.98, idea_id=idea.id)
            return idea
        raise RuntimeError("idea generation run ended without producing a result")

    def compare(
        self,
        idea: Idea,
        works: WorkList | list[WorkItem] | ExtractedFeatures | list[WorkFeatures],
        *,
        model: str = "auto",
        limit: int = 12,
        show_progress: bool = False,
        callback: ProgressCallback | None = None,
        cancel_token: CancelToken | None = None,
    ) -> IdeaComparison:
        model_label = self.llm.resolve(model).label
        with RunHandle(self.storage, "ideas.compare", callback=callback, token=cancel_token, show_progress=show_progress) as run:
            run.update("candidate_shortlist", "Shortlisting prior ideas from extracted works.", progress=0.1)
            candidates = self._comparison_candidates(works, idea, limit=limit)
            if not candidates:
                comparison = IdeaComparison(idea_id=idea.id, rows=[], model=model_label, run_id=run.status.run_id)
                self.storage.save_comparison(comparison)
                return comparison
            if self.llm.resolve(model).provider == "mock":
                rows: list[dict[str, Any]] = mock_comparison_rows(idea, candidates)
            else:
                if not self.llm.available(model):
                    raise RuntimeError(
                        "Idea comparison requires a callable LLM. Pass a valid API key through "
                        "pc.siliconflow_config(...), pc.LLMConfig(...), or provider environment variables."
                    )
                payload = call_with_progress(
                    run,
                    stage="llm_comparison",
                    message=f"Comparing against {len(candidates)} prior idea(s) with {model_label}.",
                    progress_start=0.45,
                    progress_end=0.86,
                    estimated_seconds=120,
                    call=lambda: self.llm.chat_json(
                        "You compare a generated research idea against prior ideas. Return strict JSON only.",
                        (
                            "Return {\"rows\":[{\"work_id\":\"...\",\"title\":\"...\","
                            "\"mechanistic_similarity\":\"...\",\"essential_difference\":\"...\","
                            "\"potential_advantage\":\"...\",\"potential_weakness\":\"...\"}]}.\n"
                            "Each row must name concrete mechanisms from both sides. Do not use boilerplate.\n\n"
                            f"Generated idea: {json.dumps(idea.model_dump(), ensure_ascii=False)}\n"
                            f"Prior ideas: {json.dumps(candidates, ensure_ascii=False)}"
                        ),
                        model=model,
                        max_tokens=3000,
                        temperature=0.15,
                    ),
                )
                rows = list(payload.get("rows") or [])
            clean_rows = [row for row in rows if self._valid_comparison_row(row)]
            comparison = IdeaComparison(
                idea_id=idea.id,
                rows=clean_rows,
                model=model_label,
                run_id=run.status.run_id,
            )
            self.storage.save_comparison(comparison)
            run.update("complete", f"Saved {len(clean_rows)} comparison row(s).", progress=0.98, rows=len(clean_rows))
            return comparison
        raise RuntimeError("idea comparison run ended without producing a result")

    def _packet(self, evidences: ExtractedFeatures | EvidencePacket | list[WorkFeatures], *, user_note: str) -> EvidencePacket:
        if isinstance(evidences, EvidencePacket):
            return EvidencePacket(query=evidences.query, features=evidences.features, user_note=redact_secrets(user_note or evidences.user_note))
        if isinstance(evidences, ExtractedFeatures):
            return EvidencePacket(features=evidences.items, user_note=redact_secrets(user_note))
        return EvidencePacket(features=list(evidences), user_note=redact_secrets(user_note))

    def _prompt_packet(self, packet: EvidencePacket) -> str:
        return json.dumps(
            {
                "query": packet.query,
                "user_note": packet.user_note,
                "features": [item.model_dump() for item in packet.features[:16]],
            },
            ensure_ascii=False,
        )

    def _idea_prompt(self, packet: EvidencePacket, mode: str) -> str:
        strategy = generation_strategy_label(mode)
        return (
            "Generate exactly one Idea Card with keys: title, thesis, novelty_claim, mechanism_design, "
            "methodological_details, method_variants, why_it_might_work, validation_protocol, baselines, metrics, "
            "risks, assumptions, derived_principles, source_evidence. "
            "methodological_details must include summary, symbols, equations, workflow, reliability_checks. "
            "Each equation should include name, latex, and explanation. Wrap inline formulas as $...$ and display formulas as $$...$$. "
            "Workflow step labels must be short semantic labels without numbering; do not write labels like 'Step 2' or details prefixed by '2.'. "
            "Use the internal generation strategy only as reasoning procedure metadata, never as source evidence or as the topic of the idea. "
            "Use only selected evidence supplied in the packet. Do not invent performance numbers or citations. "
            "The idea title, thesis, source_evidence, and methodological details must be about the research problem and selected papers, not about this generator or its internal strategy.\n\n"
            f"Internal generation strategy: {strategy}\nEvidence packet:\n{self._prompt_packet(packet)}"
        )

    def _idea_from_payload(
        self,
        payload: dict[str, Any],
        packet: EvidencePacket,
        mode: str,
        model_label: str,
        run_id: str,
    ) -> Idea:
        payload = sanitize_tool_leakage_payload(payload, packet)
        title = str(payload.get("title") or "Principia Idea").strip()
        thesis = str(payload.get("thesis") or payload.get("one_sentence_thesis") or "").strip()
        if not thesis:
            raise RuntimeError("Generated idea is missing a thesis.")
        evidence_ids = [feature.work_id for feature in packet.features]
        lineage: dict[str, Any] = {}
        trace: dict[str, Any] = {}
        if mode == "calculus":
            lineage_value = payload.get("lineage")
            lineage = lineage_value if isinstance(lineage_value, dict) else calculus_lineage(packet)
        if mode == "scidialect_evo":
            trace_value = payload.get("trace")
            trace = trace_value if isinstance(trace_value, dict) else scidialect_trace(packet)
        return Idea(
            id=readable_id(title),
            title=title,
            thesis=thesis,
            mode=mode,  # type: ignore[arg-type]
            novelty_claim=str(payload.get("novelty_claim") or ""),
            mechanism_design=listify(payload.get("mechanism_design") or payload.get("mechanistic_design")),
            methodological_details=normalize_methodological_details(payload.get("methodological_details"), packet),
            method_variants=listify(payload.get("method_variants")),
            why_it_might_work=listify(payload.get("why_it_might_work")),
            validation_protocol=listify(payload.get("validation_protocol")),
            baselines=listify(payload.get("baselines") or payload.get("relevant_baselines")),
            metrics=listify(payload.get("metrics")),
            risks=listify(payload.get("risks") or payload.get("failure_modes")),
            assumptions=listify(payload.get("assumptions")),
            derived_principles=listify(payload.get("derived_principles")),
            evidence_work_ids=evidence_ids,
            source_evidence=normalize_source_evidence(payload.get("source_evidence"), packet),
            lineage=lineage,
            trace=trace,
            generation_metadata={
                "mode": mode,
                "model": model_label,
                "evidence_counts": packet.counts(),
                "selected_work_ids": evidence_ids,
            },
            model=model_label,
            run_id=run_id,
        )

    def _comparison_candidates(
        self,
        works: WorkList | list[WorkItem] | ExtractedFeatures | list[WorkFeatures],
        idea: Idea,
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        features: list[WorkFeatures] = []
        if isinstance(works, ExtractedFeatures):
            features = works.items
        elif isinstance(works, WorkList):
            features = [item for item in (self.storage.latest_extraction_for_work(work.id) for work in works.items) if item]
        elif works and isinstance(works[0], WorkFeatures):  # type: ignore[index]
            features = list(works)  # type: ignore[arg-type]
        else:
            features = [item for item in (self.storage.latest_extraction_for_work(work.id) for work in works) if item]  # type: ignore[union-attr]
        idea_text = " ".join([idea.title, idea.thesis, idea.novelty_claim, " ".join(idea.mechanism_design)])
        candidates: list[dict[str, Any]] = []
        for feature in features:
            for prior in feature.ideas:
                text = feature_record_text(prior, "ideas")
                candidates.append(
                    {
                        "work_id": feature.work_id,
                        "title": prior.get("title") or feature.title,
                        "prior_idea": prior,
                        "similarity_score": lexical_score(idea_text, text),
                    }
                )
        candidates.sort(key=lambda row: float(row["similarity_score"]), reverse=True)
        return candidates[: max(1, min(int(limit), 24))]

    def _valid_comparison_row(self, row: dict[str, Any]) -> bool:
        required = ["mechanistic_similarity", "essential_difference", "potential_advantage", "potential_weakness"]
        return all(len(str(row.get(key) or "").split()) >= 6 for key in required)


def deterministic_idea_payload(packet: EvidencePacket, mode: str) -> dict[str, Any]:
    anchors = evidence_anchor_terms(packet)
    title_seed = " ".join(anchors[:5]) or "Evidence-Gated Research Mechanism"
    return {
        "title": f"Evidence-Gated {title_seed.title()}",
        "thesis": "Use selected literature features as explicit gates for when a new research mechanism should activate, adapt, or defer to a baseline.",
        "novelty_claim": "The idea turns source evidence into a reusable control layer rather than treating prior work as generic prompt context.",
        "mechanism_design": [
            "Build an evidence ledger from extracted ideas, principles, baselines, and takeaways.",
            "Score each candidate mechanism by anchor coverage, baseline contrast, and validation cost.",
            "Activate the mechanism only when the score clears a threshold; otherwise defer to the nearest baseline.",
        ],
        "methodological_details": fallback_methodological_details(packet),
        "method_variants": ["strict threshold", "cost-first threshold", "baseline-gap threshold"],
        "why_it_might_work": ["It prevents unsupported transfer.", "It creates direct ablation handles."],
        "validation_protocol": ["Run gated vs ungated variants on the smallest fair benchmark slice."],
        "baselines": ["ungated mechanism transfer", "nearest source-work baseline"],
        "metrics": ["quality", "cost", "time to first validation signal"],
        "risks": ["A weak evidence gate may suppress useful rare mechanisms."],
        "assumptions": ["Selected evidence contains enough baseline contrast to justify a gate."],
        "derived_principles": ["Evidence gates should precede expensive mechanism activation."],
        "source_evidence": source_evidence_rows(packet, limit=12),
        "lineage": calculus_lineage(packet) if mode == "calculus" else {},
        "trace": scidialect_trace(packet) if mode == "scidialect_evo" else {},
    }


def calculus_lineage(packet: EvidencePacket) -> dict[str, Any]:
    nodes = [{"id": feature.work_id, "type": "work", "label": feature.title} for feature in packet.features[:8]]
    nodes.append({"id": "D_EvidenceGate", "type": "derived_concept", "label": "Evidence-gated mechanism"})
    edges = [{"source": feature.work_id, "target": "D_EvidenceGate", "relation": "supports"} for feature in packet.features[:8]]
    return {"nodes": nodes, "edges": edges}


def scidialect_trace(packet: EvidencePacket) -> dict[str, Any]:
    return {
        "rounds": 3,
        "variants": ["candidate_evolution_full", "feature_gate", "anomaly_review"],
        "evidence_items": len(packet.features),
        "top_variant": "candidate_evolution_full",
    }


def normalize_methodological_details(value: Any, packet: EvidencePacket) -> dict[str, Any]:
    details = value if isinstance(value, dict) else {}
    normalized = {
        "summary": str(details.get("summary") or "").strip(),
        "symbols": normalize_method_rows(details.get("symbols"), default_key="definition"),
        "equations": normalize_method_rows(details.get("equations"), default_key="latex"),
        "workflow": normalize_method_rows(details.get("workflow"), default_key="detail"),
        "reliability_checks": normalize_method_rows(details.get("reliability_checks"), default_key="detail"),
    }
    if not normalized["summary"] or not normalized["symbols"] or not normalized["equations"] or not normalized["workflow"]:
        fallback = fallback_methodological_details(packet)
        for key, fallback_value in fallback.items():
            if not normalized.get(key):
                normalized[key] = fallback_value
    return normalized


def normalize_method_rows(value: Any, *, default_key: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    rows = value if isinstance(value, list) else [value]
    output: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            clean = {str(key): item for key, item in row.items() if item not in (None, "")}
            if "step" in clean:
                clean["step"] = clean_method_label(str(clean["step"]))
            if "title" in clean:
                clean["title"] = clean_method_label(str(clean["title"]))
            if "detail" in clean:
                clean["detail"] = clean_method_detail(str(clean["detail"]))
            if "description" in clean:
                clean["description"] = clean_method_detail(str(clean["description"]))
            if "check" in clean:
                clean["check"] = clean_method_label(str(clean["check"]))
            if "latex" in clean:
                clean["latex"] = normalize_latex(str(clean["latex"]))
            if "formula" in clean:
                clean["formula"] = normalize_latex(str(clean["formula"]))
            if "equation" in clean:
                clean["equation"] = normalize_latex(str(clean["equation"]))
            if "symbol" in clean:
                clean["symbol"] = normalize_inline_latex(str(clean["symbol"]))
            if clean:
                output.append(clean)
        elif str(row).strip():
            value_text = str(row).strip()
            if default_key == "latex":
                value_text = normalize_latex(value_text)
            elif default_key == "detail":
                value_text = clean_method_detail(value_text)
            output.append({default_key: value_text})
    return output


def clean_method_label(value: str) -> str:
    text = " ".join(str(value or "").split())
    for _ in range(4):
        previous = text
        text = re.sub(r"^\s*(?:step\s*)?\d+[\).:\-]\s*", "", text, flags=re.I)
        text = re.sub(r"^\s*step\s+\d+\s*[:\-]\s*", "", text, flags=re.I)
        if text == previous:
            break
    text = re.sub(r"^\s*step\s+\d+\s*$", "Step", text, flags=re.I)
    return text.strip() or "Step"


def clean_method_detail(value: str) -> str:
    text = " ".join(str(value or "").split())
    for _ in range(4):
        previous = text
        text = re.sub(r"^\s*(?:step\s*)?\d+[\).:\-]\s*", "", text, flags=re.I)
        text = re.sub(r"^\s*step\s+\d+\s*[:\-]\s*", "", text, flags=re.I)
        if text == previous:
            break
    return normalize_inline_math_text(text.strip())


def normalize_latex(value: str) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return ""
    if "$" in text:
        return text
    if any(marker in text for marker in ("\\", "^", "_", "=", "\\sum", "\\arg", "\\mid", "\\le", "\\ge")):
        return f"${text}$"
    return text


def normalize_inline_latex(value: str) -> str:
    text = " ".join(str(value or "").split())
    if not text or "$" in text:
        return text
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:\\([^)]*\\))?", text) or "_" in text or "\\" in text:
        return f"${text}$"
    return text


def normalize_inline_math_text(value: str) -> str:
    text = " ".join(str(value or "").split())
    if not text or "$" in text:
        return text
    text = re.sub(r"(?<![\w$])([A-Za-z]+_[A-Za-z0-9]+)(?![\w$])", r"$\1$", text)
    text = re.sub(r"(?<![\w$])([A-Z])(?=(?:[,.;:)]|\s+(?:and|or|from|to|with|under|for|as)\b))", r"$\1$", text)
    return text


def fallback_methodological_details(packet: EvidencePacket) -> dict[str, Any]:
    anchors = evidence_anchor_terms(packet)
    return {
        "summary": "Represent selected evidence as a quality-control state, estimate calibrated intervention risk, and route the coding agent to the least invasive corrective action that satisfies the project policy.",
        "symbols": [
            {"symbol": "$q_t$", "definition": "Observed process-quality state of the autonomous coding agent at step $t$."},
            {"symbol": "$r_t$", "definition": "Calibrated probability that the current trajectory will produce an unacceptable repository change."},
            {"symbol": "$a_t$", "definition": "Action selected by the controller, such as continue, request tests, inspect diff, or stop."},
            {"symbol": "$\\tau$", "definition": "User-defined action threshold for acceptable calibrated risk."},
        ],
        "equations": [
            {
                "name": "Calibrated risk",
                "latex": "$r_t = P(y_t=1 \\mid q_t, h_t, E)$",
                "explanation": "Estimate the probability of a process-quality failure from state, trajectory history, and selected evidence.",
            },
            {
                "name": "Action rule",
                "latex": "$a_t = \\arg\\min_a C(a) \\;\\text{s.t.}\\; r_t(a) \\le \\tau$",
                "explanation": "Choose the lowest-cost intervention that keeps risk below the configured threshold.",
            },
        ],
        "workflow": [
            {"step": "Encode evidence", "detail": f"Convert selected ideas, principles, and takeaways into monitoring features: {', '.join(anchors[:5])}."},
            {"step": "Estimate risk", "detail": "Map live coding-agent traces to calibrated risk estimates and confidence intervals."},
            {"step": "Route action", "detail": "Translate risk into concrete next actions: continue, test, inspect, rollback, or ask the user."},
            {"step": "Audit outcome", "detail": "Store the intervention, evidence state, and observed result for later calibration."},
        ],
        "reliability_checks": [
            {"check": "Calibration", "detail": "Track expected calibration error across risk buckets."},
            {"check": "Actionability", "detail": "Every warning must map to a concrete operation the agent or user can perform."},
            {"check": "Repository scale", "detail": "Validate latency and storage behavior on large repositories, not only toy tasks."},
        ],
    }


def normalize_source_evidence(value: Any, packet: EvidencePacket) -> list[dict[str, Any]]:
    if isinstance(value, list) and value:
        work_ids = {feature.work_id for feature in packet.features}
        feature_ids = selected_feature_ids(packet)
        rows = [
            sanitize_tool_leakage_value(row, packet)
            for row in value
            if isinstance(row, dict)
            and (
                str(row.get("work_id") or "") in work_ids
                or str(row.get("id") or "") in feature_ids
            )
        ]
        if rows:
            return rows[:24]
    return sanitize_tool_leakage_value(source_evidence_rows(packet, limit=24), packet)


def generation_strategy_label(mode: str) -> str:
    return {
        "standard": "direct_evidence_synthesis",
        "calculus": "symbolic_evidence_composition",
        "scidialect_evo": "candidate_evolution_scoring",
    }.get(mode, "direct_evidence_synthesis")


def selected_feature_ids(packet: EvidencePacket) -> set[str]:
    ids: set[str] = set()
    for feature in packet.features:
        for kind in FEATURE_KINDS:
            for record in getattr(feature, kind):
                record_id = str(record.get("id") or "").strip()
                if record_id:
                    ids.add(record_id)
    return ids


def sanitize_tool_leakage_payload(payload: dict[str, Any], packet: EvidencePacket) -> dict[str, Any]:
    clean = sanitize_tool_leakage_value(payload, packet)
    return clean if isinstance(clean, dict) else payload


def sanitize_tool_leakage_value(value: Any, packet: EvidencePacket) -> Any:
    if isinstance(value, str):
        return sanitize_tool_leakage_text(value, packet)
    if isinstance(value, list):
        return [sanitize_tool_leakage_value(item, packet) for item in value]
    if isinstance(value, dict):
        return {key: sanitize_tool_leakage_value(item, packet) for key, item in value.items()}
    return value


def sanitize_tool_leakage_text(value: str, packet: EvidencePacket) -> str:
    text = str(value)
    corpus = evidence_corpus(packet)
    if not SCIDIALECT_PATTERN.search(corpus):
        text = re.sub(r"\bSci[-_\s]?Dialect[-_\s]?Evo\b", "candidate-evolution", text, flags=re.I)
        text = re.sub(r"\bSci[-_\s]?Dialect\b", "candidate-evolution", text, flags=re.I)
        text = re.sub(r"\bscidialect[_-]evo\b", "candidate_evolution", text, flags=re.I)
        text = re.sub(r"\bscidialect\b", "candidate_evolution", text, flags=re.I)
    if not DIALECT_PATTERN.search(corpus):
        text = re.sub(r"\bdialectical\b", "iterative", text, flags=re.I)
        text = re.sub(r"\bdialectic\b", "iteration", text, flags=re.I)
        text = re.sub(r"\bdialects\b", "iterations", text, flags=re.I)
        text = re.sub(r"\bdialect\b", "iteration", text, flags=re.I)
    return text


def evidence_corpus(packet: EvidencePacket) -> str:
    return " ".join(
        [
            packet.query,
            packet.user_note,
            json.dumps([feature.model_dump() for feature in packet.features], ensure_ascii=False),
        ]
    )


def evidence_anchor_terms(packet: EvidencePacket) -> list[str]:
    text = " ".join(
        [
            packet.user_note,
            *[feature.title for feature in packet.features],
            *[str(item.get("name") or item.get("title") or item.get("argument") or "") for feature in packet.features for item in feature.principles[:2]],
        ]
    )
    tokens = []
    for raw in text.replace("_", " ").split():
        token = "".join(ch for ch in raw.lower() if ch.isalnum())
        if len(token) >= 4 and token not in tokens:
            tokens.append(token)
        if len(tokens) >= 10:
            break
    return tokens


def mock_comparison_rows(idea: Idea, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for candidate in candidates[:12]:
        prior_title = str(candidate.get("title") or "Prior idea")
        rows.append(
            {
                "work_id": candidate.get("work_id", ""),
                "title": prior_title,
                "similarity": round(float(candidate.get("similarity_score") or 0.0), 3),
                "mechanistic_similarity": f"Both {idea.title} and {prior_title} condition the method on a diagnostic signal rather than applying every mechanism uniformly.",
                "essential_difference": f"{idea.title} makes evidence gating the explicit reusable control layer, while {prior_title} remains tied to its source-specific mechanism.",
                "potential_advantage": "The new idea can expose cost, evidence coverage, and baseline contrast at the decision point before spending implementation effort.",
                "potential_weakness": "The gate can become too conservative when sparse evidence hides a mechanism that would transfer after deeper experimentation.",
            }
        )
    return rows


def listify(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)] if str(value).strip() else []
