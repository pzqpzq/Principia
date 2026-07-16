from __future__ import annotations

import json
import re
import unicodedata
from typing import Any, cast

from ._llm_progress import call_with_progress
from .features import (
    FEATURE_KINDS,
    MAX_SOURCE_EVIDENCE_REFERENCES,
    canonical_evidence_registry,
    feature_record_text,
    hydrate_evidence_references,
    requires_mixed_source_citations,
    source_evidence_rows,
    validate_evidence_references,
)
from .ids import readable_id
from .llm import LLMClient, redact_secrets, untrusted_data_block
from .math import (
    MathValidationError,
    generated_math_issues,
    normalize_latex_formula,
    normalize_latex_symbol,
    normalize_math_text,
    tokenize_math_spans,
)
from .models import (
    CancelToken,
    EvidencePacket,
    ExtractedFeatures,
    Idea,
    IdeaComparison,
    SciDialectConfig,
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
GENERATOR_IDENTIFIER_PATTERN = re.compile(
    r"\b(?:sci[-_\s]?dialect(?:[-_\s]?evo)?|scidialect(?:[_-]evo)?|"
    r"candidate[-_\s]evolution(?:[-_\s]scoring)?|direct[-_\s]evidence[-_\s]synthesis|"
    r"symbolic[-_\s]evidence[-_\s]composition)\b",
    re.I,
)
GENERATOR_EVIDENCE_PATTERN = re.compile(
    r"\b(?:idea generator|generation (?:mode|strategy)|internal strategy|tool trace)\b.{0,100}"
    r"\b(?:evidence|source|mechanism|justification)\b|"
    r"\b(?:evidence|source|mechanism|justification)\b.{0,100}"
    r"\b(?:idea generator|generation (?:mode|strategy)|internal strategy|tool trace)\b",
    re.I,
)
COMPARISON_BOILERPLATE_PATTERN = re.compile(
    r"\b(?:no (?:essential )?(?:difference|advantage|weakness|similarity) (?:was |is )?"
    r"(?:specified|provided|available)|not (?:specified|provided|available)|"
    r"cannot be determined|insufficient (?:data|information)|n/?a)\b",
    re.I,
)

METHODOLOGICAL_SCHEMA_CONTRACT = (
    'methodological_details must use exactly this nested shape: {"summary":"...",'
    '"symbols":[{"symbol":"...","definition":"..."}],'
    '"equations":[{"name":"...","latex":"$$...$$","explanation":"..."}],'
    '"workflow":[{"step":"short semantic label","detail":"..."}],'
    '"reliability_checks":[{"check":"short semantic label","detail":"..."}]}. '
    "symbols and equations may be empty only when the evidence does not support a grounded "
    "formalization; workflow and reliability_checks must remain structured objects. "
)
GOAL_COVERAGE_CONTRACT = (
    "Address every explicit requirement, boundary condition, preservation clause, risk, and "
    "control in the authorized research goal. Do not discard a goal constraint during candidate "
    "selection. Operationalize evidence-supported uncertainty, calibration, robustness, "
    "interpretability, noise, safety, and false-positive controls in the mechanism or validation "
    "protocol whenever the goal calls for them. "
)


class IdeaService:
    def __init__(self, storage: WorkspaceStorage, llm: LLMClient) -> None:
        self.storage = storage
        self.llm = llm

    def generate(
        self,
        evidences: ExtractedFeatures | EvidencePacket | list[WorkFeatures],
        *,
        user_note: str = "",
        mode: str = "scidialect-evo",
        model: str = "auto",
        offline: bool = False,
        overwrite: bool = False,
        scidialect_config: SciDialectConfig | None = None,
        show_progress: bool = False,
        callback: ProgressCallback | None = None,
        cancel_token: CancelToken | None = None,
    ) -> Idea:
        normalized_mode = MODE_ALIASES.get(str(mode or "").lower().replace(" ", "_"), "")
        if normalized_mode not in {"standard", "calculus", "scidialect_evo"}:
            raise ValueError("mode must be standard, calculus, or scidialect_evo")
        packet = self._packet(evidences, user_note=user_note)
        resolved_model = self.llm.resolve(model)
        model_label = resolved_model.label
        usage_before = llm_usage_snapshot(self.llm)
        # Live SciDialect is strict by default. Degraded behavior remains an
        # explicit opt-in through ``SciDialectConfig`` and never fabricates a
        # template Idea Card.
        dialect_config = scidialect_config or SciDialectConfig(allow_degraded_fallback=False)
        with RunHandle(
            self.storage,
            f"ideas.generate.{normalized_mode}",
            callback=callback,
            token=cancel_token,
            show_progress=show_progress,
        ) as run:
            run.update(
                "evidence_pack",
                "Packing selected evidence.",
                progress=0.1,
                evidence_items=len(packet.features),
            )
            trace_override: dict[str, Any] | None = None
            repair_metadata: dict[str, Any] = {"attempted": False, "issues": []}
            fixture_run = offline or resolved_model.provider == "mock"
            if fixture_run:
                payload = deterministic_idea_payload(packet, normalized_mode)
            elif not self.llm.available(model):
                raise RuntimeError(
                    "No callable LLM is configured. Pass a valid API key through "
                    "pc.siliconflow_config(...), pc.LLMConfig(...), or provider environment variables."
                )
            elif normalized_mode == "scidialect_evo":
                payload, trace_override = self._scidialect_payload(
                    packet,
                    model=model,
                    model_label=model_label,
                    config=dialect_config,
                    run=run,
                )
            else:
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
                        control_token=run.token,
                    ),
                )
            if not fixture_run:
                payload, repair_metadata = self._repair_payload_if_needed(
                    payload,
                    packet,
                    model=model,
                    model_label=model_label,
                    run=run,
                )
                if trace_override is not None:
                    trace_override["repair"] = repair_metadata
                remaining = list(repair_metadata.get("remaining_issues") or [])
                if remaining:
                    # A failed repair is still a paid, observable live run.
                    # Persist the usage delta before RunHandle records the
                    # terminal validation error, without saving an invalid idea.
                    failed_usage = llm_usage_delta(
                        usage_before, llm_usage_snapshot(self.llm)
                    )
                    run.update(
                        "quality_review",
                        "Generated Idea Card remains invalid after repair.",
                        progress=0.84,
                        checkpoint=False,
                        llm_usage=failed_usage,
                    )
                    raise RuntimeError(
                        "Generated Idea Card failed validation after one evidence-grounded repair: "
                        + "; ".join(remaining)
                    )
            run.update(
                "quality_review", "Checking generated idea schema and grounding.", progress=0.84
            )
            idea = self._idea_from_payload(
                payload,
                packet,
                normalized_mode,
                model_label,
                run.status.run_id,
                trace_override=trace_override,
                allow_methodological_fallback=fixture_run,
                generation_metadata={
                    "repair": repair_metadata,
                    "scidialect_config": dialect_config.model_dump()
                    if normalized_mode == "scidialect_evo"
                    else {},
                    "execution_origin": "mock_fixture" if fixture_run else "live_llm",
                },
            )
            idea_id, replaced_id = self._resolve_idea_id(idea.title, overwrite=overwrite)
            usage_delta = llm_usage_delta(usage_before, llm_usage_snapshot(self.llm))
            generation_metadata = dict(idea.generation_metadata)
            generation_metadata["llm_usage"] = usage_delta
            generation_metadata["overwrite"] = bool(overwrite)
            if replaced_id:
                generation_metadata["replaced_idea_id"] = replaced_id
            idea = idea.model_copy(
                update={"id": idea_id, "generation_metadata": generation_metadata}
            )
            self.storage.save_idea(idea)
            run.update(
                "complete",
                f"Saved idea {idea.id}.",
                progress=0.98,
                idea_id=idea.id,
                llm_usage=usage_delta,
            )
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
        usage_before = llm_usage_snapshot(self.llm)
        with RunHandle(
            self.storage,
            "ideas.compare",
            callback=callback,
            token=cancel_token,
            show_progress=show_progress,
        ) as run:
            run.update(
                "candidate_shortlist",
                "Shortlisting prior ideas from extracted works.",
                progress=0.1,
            )
            candidates = self._comparison_candidates(works, idea, limit=limit)
            if not candidates:
                comparison = IdeaComparison(
                    idea_id=idea.id, rows=[], model=model_label, run_id=run.status.run_id
                )
                self.storage.save_comparison(comparison)
                usage_delta = llm_usage_delta(usage_before, llm_usage_snapshot(self.llm))
                self._record_comparison_usage(idea, usage_delta, run.status.run_id)
                run.update(
                    "complete",
                    "Saved 0 comparison rows.",
                    progress=0.98,
                    rows=0,
                    llm_usage=usage_delta,
                )
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
                            'Return {"rows":[{"work_id":"...","title":"...",'
                            '"mechanistic_similarity":"...","essential_difference":"...",'
                            '"potential_advantage":"...","potential_weakness":"..."}]}.\n'
                            "Each row must name concrete mechanisms from both sides. Do not use boilerplate.\n\n"
                            f"Generated idea content: {json.dumps(idea_content_projection(idea), ensure_ascii=False)}\n"
                            f"{untrusted_data_block('prior_idea_records', candidates)}"
                        ),
                        model=model,
                        max_tokens=3000,
                        temperature=0.15,
                        control_token=run.token,
                    ),
                )
                rows = canonicalize_explicit_math(list(payload.get("rows") or []))
                comparison_issues = generated_math_issues(rows, path="comparison.rows")
                if comparison_issues:
                    repair_payload = call_with_progress(
                        run,
                        stage="llm_comparison_repair",
                        message="Repairing comparison notation without changing scientific claims.",
                        progress_start=0.82,
                        progress_end=0.9,
                        estimated_seconds=60,
                        call=lambda: self.llm.chat_json(
                            "Repair comparison rows using only the supplied idea and prior records. Return strict JSON only.",
                            (
                                'Return {"rows":[...]} with the same comparison claims and row identities. '
                                "Repair every listed mathematical-format issue. Use canonical $...$ or $$...$$ LaTeX, "
                                "brace every subscript and superscript, and never introduce a coefficient, power, "
                                "threshold, denominator, or scientific claim.\n\n"
                                f"Issues: {json.dumps(comparison_issues, ensure_ascii=False)}\n\n"
                                f"Rows: {json.dumps(rows, ensure_ascii=False)}\n\n"
                                f"Generated idea content: {json.dumps(idea_content_projection(idea), ensure_ascii=False)}\n"
                                f"{untrusted_data_block('prior_idea_records', candidates)}"
                            ),
                            model=model,
                            max_tokens=3200,
                            temperature=0,
                            control_token=run.token,
                        ),
                    )
                    rows = canonicalize_explicit_math(list(repair_payload.get("rows") or []))
                    remaining_comparison_issues = generated_math_issues(
                        rows, path="comparison.rows"
                    )
                    if remaining_comparison_issues:
                        raise RuntimeError(
                            "Idea comparison failed mathematical validation after one repair: "
                            + "; ".join(remaining_comparison_issues)
                        )
            clean_rows = [row for row in rows if self._valid_comparison_row(row)]
            comparison = IdeaComparison(
                idea_id=idea.id,
                rows=clean_rows,
                model=model_label,
                run_id=run.status.run_id,
            )
            self.storage.save_comparison(comparison)
            usage_delta = llm_usage_delta(usage_before, llm_usage_snapshot(self.llm))
            self._record_comparison_usage(idea, usage_delta, run.status.run_id)
            run.update(
                "complete",
                f"Saved {len(clean_rows)} comparison row(s).",
                progress=0.98,
                rows=len(clean_rows),
                llm_usage=usage_delta,
            )
            return comparison
        raise RuntimeError("idea comparison run ended without producing a result")

    def _packet(
        self, evidences: ExtractedFeatures | EvidencePacket | list[WorkFeatures], *, user_note: str
    ) -> EvidencePacket:
        if isinstance(evidences, EvidencePacket):
            return EvidencePacket(
                query=evidences.query,
                features=evidences.features,
                user_note=redact_secrets(user_note or evidences.user_note),
            )
        if isinstance(evidences, ExtractedFeatures):
            return EvidencePacket(features=evidences.items, user_note=redact_secrets(user_note))
        return EvidencePacket(features=list(evidences), user_note=redact_secrets(user_note))

    def _prompt_packet(self, packet: EvidencePacket) -> str:
        request = json.dumps(
            {"research_goal": packet.query, "user_guidance": packet.user_note},
            ensure_ascii=False,
        )
        source_mix = citation_source_mix_instruction(packet)
        return (
            f"Authorized research request: {request}\n"
            f"{source_mix}"
            f"{untrusted_data_block('canonical_evidence_registry', canonical_evidence_registry(packet))}"
        )

    def _idea_prompt(self, packet: EvidencePacket, mode: str) -> str:
        strategy = generation_strategy_label(mode)
        return (
            "Generate exactly one Idea Card with keys: title, thesis, novelty_claim, mechanism_design, "
            "methodological_details, method_variants, why_it_might_work, validation_protocol, baselines, metrics, "
            "risks, assumptions, derived_principles, source_evidence. "
            f"{METHODOLOGICAL_SCHEMA_CONTRACT}"
            "Use empty symbol/equation lists when the selected discipline does not support a grounded formalization; never add generic equations. "
            "When equations are supported, include name, latex, and explanation and wrap formulas in $...$ or $$...$$. "
            "Workflow step labels must be short semantic labels without numbering; do not write labels like 'Step 2' or details prefixed by '2.'. "
            "Treat baselines as comparators, controls, standard methods, or reference theories as appropriate to the discipline. "
            "Use the internal generation strategy only as reasoning procedure metadata, never as source evidence or as the topic of the idea. "
            "source_evidence must contain references only, each with exact work_id, kind, and record_id copied from "
            "the canonical registry; do not author quotations because Principia hydrates canonical text after validation. "
            "Use only selected evidence supplied in the packet. Do not invent performance numbers or citations. "
            f"{GOAL_COVERAGE_CONTRACT}"
            "The idea title, thesis, source_evidence, and methodological details must be about the research problem and selected papers, not about this generator or its internal strategy.\n\n"
            f"Internal generation strategy: {strategy}\nEvidence packet:\n{self._prompt_packet(packet)}"
        )

    def _scidialect_payload(
        self,
        packet: EvidencePacket,
        *,
        model: str,
        model_label: str,
        config: SciDialectConfig,
        run: RunHandle,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        trace = scidialect_trace(packet, degraded=False)
        trace["model"] = model_label
        trace["stages"] = []
        candidates: list[dict[str, Any]] = []
        evolved: list[dict[str, Any]] = []

        try:
            stage_one = call_with_progress(
                run,
                stage="candidate_generation",
                message=f"Generating three evidence-grounded candidates with {model_label}.",
                progress_start=0.2,
                progress_end=0.38,
                estimated_seconds=150,
                call=lambda: self.llm.chat_json(
                    "Generate three distinct evidence-grounded research candidates. Return strict JSON only.",
                    candidate_generation_prompt(packet),
                    model=model,
                    max_tokens=config.candidate_max_tokens,
                    temperature=config.candidate_temperature,
                    control_token=run.token,
                ),
            )
            candidates = parse_stage_candidates(stage_one, key="candidates")
            if len(candidates) != config.candidate_count:
                if is_idea_card_payload(stage_one):
                    if not config.allow_degraded_fallback:
                        raise RuntimeError(
                            "candidate generation returned a direct Idea Card instead of exactly three candidates"
                        )
                    return degraded_scidialect_result(
                        stage_one,
                        trace,
                        "Candidate stage returned a direct Idea Card; later stages were skipped.",
                        stage="candidate_generation",
                    )
                if not candidates:
                    raise RuntimeError("candidate generation returned no usable candidates")
                if not config.allow_degraded_fallback:
                    raise RuntimeError(
                        f"candidate generation returned {len(candidates)} usable candidate(s), expected 3"
                    )
                fallback = strongest_candidates(candidates, count=1)[0]["idea"]
                return degraded_scidialect_result(
                    fallback,
                    trace,
                    f"Candidate stage returned {len(candidates)} usable candidate(s), expected 3.",
                    stage="candidate_generation",
                )
            candidate_contract = stage_candidate_contract_issues(candidates, evolution=False)
            if candidate_contract:
                if not config.allow_degraded_fallback:
                    raise RuntimeError(
                        "candidate generation contract invalid: " + "; ".join(candidate_contract)
                    )
                fallback = strongest_candidates(candidates, count=1)[0]["idea"]
                return degraded_scidialect_result(
                    fallback,
                    trace,
                    "Candidate stage did not provide explicit IDs, four scores, and rationale: "
                    + "; ".join(candidate_contract),
                    stage="candidate_generation",
                )
            trace["stages"].append(
                {
                    "name": "candidate_generation",
                    "status": "complete",
                    "candidate_count": len(candidates),
                    "candidates": [candidate_trace_summary(item) for item in candidates],
                }
            )

            strongest = strongest_candidates(candidates, count=config.evolved_candidate_count)
            stage_two = call_with_progress(
                run,
                stage="critique_evolution",
                message=f"Critiquing and evolving the strongest two candidates with {model_label}.",
                progress_start=0.4,
                progress_end=0.58,
                estimated_seconds=150,
                call=lambda: self.llm.chat_json(
                    "Critique and evolve two research candidates. Return concise audit fields and strict JSON only.",
                    critique_evolution_prompt(packet, strongest),
                    model=model,
                    max_tokens=config.evolution_max_tokens,
                    temperature=config.evolution_temperature,
                    control_token=run.token,
                ),
            )
            evolved = parse_stage_candidates(stage_two, key="evolutions")
            if len(evolved) != config.evolved_candidate_count:
                if not config.allow_degraded_fallback:
                    raise RuntimeError(
                        f"evolution stage returned {len(evolved)} usable evolution(s), expected 2"
                    )
                fallback_pool = evolved or strongest
                fallback = strongest_candidates(fallback_pool, count=1)[0]["idea"]
                return degraded_scidialect_result(
                    fallback,
                    trace,
                    f"Evolution stage returned {len(evolved)} usable evolution(s), expected 2.",
                    stage="critique_evolution",
                )
            evolution_contract = stage_candidate_contract_issues(evolved, evolution=True)
            if evolution_contract:
                if not config.allow_degraded_fallback:
                    raise RuntimeError(
                        "evolution stage contract invalid: " + "; ".join(evolution_contract)
                    )
                fallback = strongest_candidates(evolved, count=1)[0]["idea"]
                return degraded_scidialect_result(
                    fallback,
                    trace,
                    "Evolution stage did not provide complete scores and audit fields: "
                    + "; ".join(evolution_contract),
                    stage="critique_evolution",
                )
            trace["stages"].append(
                {
                    "name": "critique_evolution",
                    "status": "complete",
                    "candidate_count": len(evolved),
                    "candidates": [
                        candidate_trace_summary(item, include_critique=True) for item in evolved
                    ],
                }
            )

            stage_three = call_with_progress(
                run,
                stage="final_selection",
                message=f"Selecting and finalizing one Idea Card with {model_label}.",
                progress_start=0.6,
                progress_end=0.74,
                estimated_seconds=150,
                call=lambda: self.llm.chat_json(
                    "Select and finalize one evidence-grounded research Idea Card. Return strict JSON only.",
                    final_selection_prompt(packet, evolved),
                    model=model,
                    max_tokens=config.final_max_tokens,
                    temperature=config.final_temperature,
                    control_token=run.token,
                ),
            )
            final_payload = unwrap_idea_card(stage_three)
            if final_payload is None:
                if not config.allow_degraded_fallback:
                    raise RuntimeError("final selection did not return a usable Idea Card")
                fallback = strongest_candidates(evolved, count=1)[0]["idea"]
                return degraded_scidialect_result(
                    fallback,
                    trace,
                    "Final selection did not return a usable Idea Card.",
                    stage="final_selection",
                )
            selected_id = str(
                wrapped_response_value(stage_three, "selected_candidate_id") or ""
            ).strip()
            selection_rationale = concise_text(
                wrapped_response_value(stage_three, "selection_rationale"), 320
            )
            evolved_ids = {str(item.get("candidate_id") or "") for item in evolved}
            final_contract: list[str] = []
            if not selected_id:
                final_contract.append("missing selected_candidate_id")
            elif selected_id not in evolved_ids:
                final_contract.append(
                    "selected_candidate_id does not identify an evolved candidate"
                )
            if not selection_rationale:
                final_contract.append("missing selection_rationale")
            if final_contract:
                if not config.allow_degraded_fallback:
                    raise RuntimeError(
                        "final selection contract invalid: " + "; ".join(final_contract)
                    )
                fallback = strongest_candidates(evolved, count=1)[0]["idea"]
                return degraded_scidialect_result(
                    fallback,
                    trace,
                    "Final selection omitted required audit fields: " + "; ".join(final_contract),
                    stage="final_selection",
                )
            trace["selected_candidate_id"] = selected_id
            trace["selection_rationale"] = selection_rationale
            trace["stages"].append(
                {
                    "name": "final_selection",
                    "status": "complete",
                    "selected_candidate_id": selected_id,
                    "selection_rationale": trace["selection_rationale"],
                }
            )
            return dict(final_payload), trace
        except Exception as exc:  # noqa: BLE001
            if not config.allow_degraded_fallback:
                raise
            fallback_pool = evolved or candidates
            if fallback_pool:
                fallback = strongest_candidates(fallback_pool, count=1)[0]["idea"]
                return degraded_scidialect_result(
                    fallback,
                    trace,
                    f"SciDialect-Evo stage failed: {concise_text(redact_secrets(str(exc)), 300)}",
                    stage="stage_error",
                )
            try:
                direct = call_with_progress(
                    run,
                    stage="direct_degraded_fallback",
                    message=f"Attempting one direct evidence-grounded fallback with {model_label}.",
                    progress_start=0.6,
                    progress_end=0.74,
                    estimated_seconds=120,
                    call=lambda: self.llm.chat_json(
                        "Generate one evidence-grounded research Idea Card as a degraded fallback. Return strict JSON only.",
                        self._idea_prompt(packet, "scidialect_evo"),
                        model=model,
                        max_tokens=config.final_max_tokens,
                        temperature=config.final_temperature,
                        control_token=run.token,
                    ),
                )
                if is_idea_card_payload(direct):
                    assert isinstance(direct, dict)
                    return degraded_scidialect_result(
                        direct,
                        trace,
                        f"Three-stage generation failed before a candidate was available: {concise_text(redact_secrets(str(exc)), 260)}",
                        stage="direct_degraded_fallback",
                    )
            except Exception as fallback_exc:  # noqa: BLE001
                raise RuntimeError(
                    "SciDialect-Evo and its direct fallback failed: "
                    f"{redact_secrets(str(fallback_exc))}"
                ) from fallback_exc
            raise RuntimeError(
                f"SciDialect-Evo failed before producing a candidate: {redact_secrets(str(exc))}"
            ) from exc

    def _repair_payload_if_needed(
        self,
        payload: dict[str, Any],
        packet: EvidencePacket,
        *,
        model: str,
        model_label: str,
        run: RunHandle,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        # Canonical formatting changes such as ``$R_cf$`` -> ``$R_{cf}$`` are
        # deterministic and do not alter a scientific claim. Apply them before
        # deciding whether a paid evidence-grounded repair is necessary.
        payload = canonicalize_explicit_math(payload)
        issues = idea_payload_issues(payload, packet)
        metadata: dict[str, Any] = {
            "attempted": False,
            "issues": issues,
            "remaining_issues": issues,
        }
        if not issues:
            return payload, metadata
        metadata["attempted"] = True
        try:
            repaired_value = call_with_progress(
                run,
                stage="idea_repair",
                message=f"Repairing incomplete or weakly grounded Idea Card with {model_label}.",
                progress_start=0.75,
                progress_end=0.82,
                estimated_seconds=100,
                call=lambda: self.llm.chat_json(
                    "Repair one research Idea Card using only supplied evidence. Return strict JSON only.",
                    repair_idea_prompt(payload, packet, issues),
                    model=model,
                    max_tokens=4400,
                    temperature=0.08,
                    control_token=run.token,
                ),
            )
            repaired: dict[str, Any] = repaired_value if isinstance(repaired_value, dict) else {}
            repaired_payload = canonicalize_explicit_math(unwrap_idea_card(repaired) or repaired)
            merged = canonicalize_explicit_math(
                merge_nonempty_payload(payload, repaired_payload)
            )
            remaining = idea_payload_issues(merged, packet)
            metadata["remaining_issues"] = remaining
            metadata["succeeded"] = not remaining
            return merged, metadata
        except Exception as exc:  # noqa: BLE001
            metadata["succeeded"] = False
            metadata["error"] = concise_text(redact_secrets(str(exc)), 300)
            return payload, metadata

    def _resolve_idea_id(self, title: str, *, overwrite: bool) -> tuple[str, str]:
        with self.storage.connect() as conn:
            rows = conn.execute(
                "SELECT id, payload_json, created_at FROM ideas ORDER BY created_at"
            ).fetchall()
        existing_ids = {str(row["id"]) for row in rows}
        normalized_title = " ".join(title.lower().split())
        same_title_ids: list[str] = []
        for row in rows:
            try:
                stored = json.loads(row["payload_json"])
            except (TypeError, json.JSONDecodeError):
                continue
            if " ".join(str(stored.get("title") or "").lower().split()) == normalized_title:
                same_title_ids.append(str(row["id"]))
        base_id = readable_id(title)
        if overwrite:
            target = (
                base_id
                if base_id in existing_ids
                else (same_title_ids[0] if same_title_ids else base_id)
            )
            return target, target if target in existing_ids else ""
        return readable_id(title, existing=existing_ids), ""

    def _record_comparison_usage(self, idea: Idea, usage: dict[str, Any], run_id: str) -> None:
        metadata = dict(idea.generation_metadata)
        history = list(metadata.get("comparison_usage") or [])
        history.append({"run_id": run_id, "llm_usage": usage})
        metadata["comparison_usage"] = history[-20:]
        idea.generation_metadata = metadata
        self.storage.save_idea(idea)

    def _idea_from_payload(
        self,
        payload: dict[str, Any],
        packet: EvidencePacket,
        mode: str,
        model_label: str,
        run_id: str,
        *,
        trace_override: dict[str, Any] | None = None,
        allow_methodological_fallback: bool = False,
        generation_metadata: dict[str, Any] | None = None,
    ) -> Idea:
        title = str(payload.get("title") or "").strip()
        if not title:
            raise RuntimeError("Generated idea is missing a title.")
        thesis = str(payload.get("thesis") or payload.get("one_sentence_thesis") or "").strip()
        if not thesis:
            raise RuntimeError("Generated idea is missing a thesis.")
        source_evidence = normalize_source_evidence(payload.get("source_evidence"), packet)
        evidence_ids = list(dict.fromkeys(str(row["work_id"]) for row in source_evidence))
        selected_ids = [feature.work_id for feature in packet.features]
        lineage: dict[str, Any] = {}
        trace: dict[str, Any] = {}
        if mode == "calculus":
            lineage_value = payload.get("lineage")
            lineage = lineage_value if isinstance(lineage_value, dict) else {}
        if mode == "scidialect_evo":
            trace_value = payload.get("trace")
            trace = trace_value if isinstance(trace_value, dict) else scidialect_trace(packet)
            if trace_override is not None:
                trace = dict(trace_override)
        metadata = {
            "mode": mode,
            "model": model_label,
            "evidence_counts": packet.counts(),
            "selected_work_ids": selected_ids,
            "cited_work_ids": evidence_ids,
        }
        metadata.update(generation_metadata or {})
        return Idea(
            id=readable_id(title),
            title=title,
            thesis=thesis,
            mode=mode,  # type: ignore[arg-type]
            novelty_claim=str(payload.get("novelty_claim") or ""),
            mechanism_design=listify(
                payload.get("mechanism_design") or payload.get("mechanistic_design")
            ),
            methodological_details=normalize_methodological_details(
                payload.get("methodological_details"),
                packet,
                allow_fallback=allow_methodological_fallback,
            ),
            method_variants=listify(payload.get("method_variants")),
            why_it_might_work=listify(payload.get("why_it_might_work")),
            validation_protocol=listify(payload.get("validation_protocol")),
            baselines=listify(
                payload.get("baselines")
                or payload.get("relevant_baselines")
                or payload.get("comparators")
                or payload.get("controls")
            ),
            metrics=listify(payload.get("metrics")),
            risks=listify(payload.get("risks") or payload.get("failure_modes")),
            assumptions=listify(payload.get("assumptions")),
            derived_principles=listify(payload.get("derived_principles")),
            evidence_work_ids=evidence_ids,
            source_evidence=source_evidence,
            lineage=lineage,
            trace=trace,
            generation_metadata=metadata,
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
            features = [
                item
                for item in (
                    self.storage.latest_extraction_for_work(work.id) for work in works.items
                )
                if item
            ]
        elif works and isinstance(works[0], WorkFeatures):  # type: ignore[index]
            features = list(works)  # type: ignore[arg-type]
        else:
            work_items = cast(list[WorkItem], works)
            features = [
                item
                for item in (
                    self.storage.latest_extraction_for_work(work.id) for work in work_items
                )
                if item
            ]
        idea_text = " ".join(
            [idea.title, idea.thesis, idea.novelty_claim, " ".join(idea.mechanism_design)]
        )
        candidates: list[dict[str, Any]] = []
        for feature in features:
            for prior in feature.ideas:
                text = feature_record_text(prior, "ideas")
                candidates.append(
                    {
                        "work_id": feature.work_id,
                        "work_title": feature.title,
                        "record_id": str(prior.get("record_id") or prior.get("id") or ""),
                        "title": str(prior.get("title") or feature.title),
                        "text": text,
                        "similarity_score": lexical_score(idea_text, text),
                    }
                )
        candidates.sort(key=lambda row: float(row["similarity_score"]), reverse=True)
        return candidates[: max(1, min(int(limit), 24))]

    def _valid_comparison_row(self, row: dict[str, Any]) -> bool:
        required = [
            "mechanistic_similarity",
            "essential_difference",
            "potential_advantage",
            "potential_weakness",
        ]
        values = [str(row.get(key) or "").strip() for key in required]
        return all(len(value.split()) >= 6 for value in values) and not any(
            COMPARISON_BOILERPLATE_PATTERN.search(value) for value in values
        )


def candidate_generation_prompt(packet: EvidencePacket) -> str:
    return (
        'Return {"candidates":[...]} with exactly three candidates. Each candidate must contain '
        "candidate_id, an idea object, scores, and selection_rationale. The idea object must contain title, "
        "thesis, novelty_claim, mechanism_design, methodological_details, method_variants, why_it_might_work, "
        "validation_protocol, baselines, metrics, risks, assumptions, derived_principles, and source_evidence. "
        "Scores must contain novelty, grounding, feasibility, and discriminability on [0,1], and the rationale "
        "must justify those four audit scores. source_evidence rows must contain only exact work_id, kind, and "
        "record_id values copied from the canonical evidence registry. "
        "selection_rationale is a concise audit sentence, not hidden reasoning. Make the candidates mechanistically distinct. "
        f"{METHODOLOGICAL_SCHEMA_CONTRACT}"
        f"{GOAL_COVERAGE_CONTRACT}"
        "Use only the evidence packet; do not invent citations or numerical results.\n\n"
        f"Evidence packet:\n{evidence_prompt(packet)}"
    )


def idea_content_projection(idea: Idea) -> dict[str, Any]:
    """Return scientific proposal content without operational metadata."""

    return {
        "title": idea.title,
        "thesis": idea.thesis,
        "novelty_claim": idea.novelty_claim,
        "mechanism_design": idea.mechanism_design,
        "methodological_details": idea.methodological_details,
        "method_variants": idea.method_variants,
        "why_it_might_work": idea.why_it_might_work,
        "validation_protocol": idea.validation_protocol,
        "baselines": idea.baselines,
        "metrics": idea.metrics,
        "risks": idea.risks,
        "assumptions": idea.assumptions,
        "derived_principles": idea.derived_principles,
    }


def critique_evolution_prompt(packet: EvidencePacket, candidates: list[dict[str, Any]]) -> str:
    return (
        'Return {"evolutions":[...]} with exactly two evolved candidates. Each item must contain candidate_id, '
        "idea, scores, critique, changes, and selection_rationale. critique and changes must be concise, externally "
        "auditable summaries; do not provide private chain-of-thought. Repair grounding gaps, specify a falsifiable "
        "validation protocol, and keep comparators appropriate to the evidence discipline. Each evolution must retain "
        "four audit scores and a concise rationale. source_evidence may contain only exact canonical record references. "
        f"{METHODOLOGICAL_SCHEMA_CONTRACT}"
        f"{GOAL_COVERAGE_CONTRACT}"
        "Use no unsupported equations.\n\n"
        f"Evidence packet: {evidence_prompt(packet)}\n"
        f"Candidates: {json.dumps(candidates, ensure_ascii=False)}"
    )


def final_selection_prompt(packet: EvidencePacket, candidates: list[dict[str, Any]]) -> str:
    return (
        'Return exactly {"selected_candidate_id":"...","selection_rationale":"...",'
        '"final_idea":{...}}. final_idea must contain title, thesis, novelty_claim, mechanism_design, '
        "methodological_details, method_variants, why_it_might_work, validation_protocol, baselines, metrics, risks, "
        "assumptions, derived_principles, and source_evidence. "
        f"{METHODOLOGICAL_SCHEMA_CONTRACT}"
        "Every source_evidence row "
        "must contain an exact work_id, kind, and record_id tuple copied from the canonical registry. Select on evidence grounding, "
        "mechanistic novelty, feasibility, and ability to distinguish "
        "the proposal from relevant comparators. If the selected evolved candidate lacks an explicit goal constraint, "
        "integrate a grounded control from the other evolved candidate while retaining the selected candidate ID. "
        f"{GOAL_COVERAGE_CONTRACT}"
        "Do not expose chain-of-thought. Use only supplied evidence and do not "
        "invent citations, measurements, benchmarks, or equations.\n\n"
        f"Evidence packet: {evidence_prompt(packet)}\n"
        f"Evolved candidates: {json.dumps(candidates, ensure_ascii=False)}"
    )


def repair_idea_prompt(payload: dict[str, Any], packet: EvidencePacket, issues: list[str]) -> str:
    return (
        "Return a complete repaired Idea Card as one JSON object with title, thesis, novelty_claim, mechanism_design, "
        "methodological_details, method_variants, why_it_might_work, validation_protocol, baselines, metrics, risks, "
        "assumptions, derived_principles, and source_evidence. "
        f"{METHODOLOGICAL_SCHEMA_CONTRACT}"
        "Every source_evidence row must contain an exact work_id, kind, and record_id tuple copied "
        "from the canonical registry. Never use generator mode, strategy, trace, or configuration as scientific evidence. "
        "Correct only the listed defects. Ground every mechanism, comparator, "
        "validation step, and evidence reference in the packet. Symbols or equations may be empty when the discipline "
        "does not support a source-grounded formalization. "
        f"{GOAL_COVERAGE_CONTRACT}"
        "Do not add generic software, benchmark, or agent language.\n\n"
        f"Defects: {json.dumps(issues, ensure_ascii=False)}\n"
        f"Draft: {json.dumps(payload, ensure_ascii=False)}\n"
        f"Evidence packet: {evidence_prompt(packet)}"
    )


def evidence_prompt(packet: EvidencePacket) -> str:
    request = json.dumps(
        {"research_goal": packet.query, "user_guidance": packet.user_note},
        ensure_ascii=False,
    )
    source_mix = citation_source_mix_instruction(packet)
    return (
        f"Authorized research request: {request}\n"
        f"{source_mix}"
        f"{untrusted_data_block('canonical_evidence_registry', canonical_evidence_registry(packet))}"
    )


def citation_source_mix_instruction(packet: EvidencePacket) -> str:
    if not requires_mixed_source_citations(packet):
        return ""
    return (
        "The selected packet mixes local and public evidence. source_evidence must cite at least "
        "one exact canonical record whose work_id starts with 'L-' and at least one exact canonical "
        "record whose work_id does not start with 'L-'. Both must appear within the first 24 rows "
        "retained in the saved Idea.\n"
    )


RESPONSE_WRAPPER_KEYS = ("result", "response", "data", "output", "payload")
EVOLUTION_LIST_KEYS = (
    "evolutions",
    "evolved_candidates",
    "revised_candidates",
    "critiqued_candidates",
)
CANDIDATE_IDEA_KEYS = ("idea", "evolved_idea", "revised_idea", "candidate", "idea_card")
IDEA_CARD_WRAPPER_KEYS = ("final_idea", "idea", "idea_card", "selected_idea", "selected_candidate")


def parse_stage_candidates(payload: dict[str, Any], *, key: str) -> list[dict[str, Any]]:
    raw_items = stage_candidate_items(payload, key=key)
    output: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_items, start=1):
        if not isinstance(raw, dict):
            continue
        idea: dict[str, Any] | None = None
        for idea_key in CANDIDATE_IDEA_KEYS:
            idea = unwrap_idea_card(raw.get(idea_key))
            if idea is not None:
                break
        if idea is None and is_idea_card_payload(raw):
            idea = dict(raw)
        if idea is None:
            continue
        raw_scores_value = raw.get("scores")
        raw_scores: dict[str, Any] = raw_scores_value if isinstance(raw_scores_value, dict) else {}
        scores: dict[str, float] = {}
        for name in ("novelty", "grounding", "feasibility", "discriminability", "overall"):
            raw_score = raw_scores.get(name)
            if not isinstance(raw_score, (int, float, str)):
                continue
            try:
                score = float(raw_score)
            except (TypeError, ValueError):
                continue
            scores[name] = max(0.0, min(1.0, score))
        output.append(
            {
                "candidate_id": str(
                    raw.get("candidate_id") or raw.get("id") or f"candidate_{index}"
                ),
                "explicit_candidate_id": bool(
                    str(raw.get("candidate_id") or raw.get("id") or "").strip()
                ),
                "idea": idea,
                "scores": scores,
                "selection_rationale": concise_text(
                    raw.get("selection_rationale") or raw.get("rationale"), 320
                ),
                "critique": concise_text(raw.get("critique"), 320),
                "changes": concise_text(raw.get("changes") or raw.get("evolution_summary"), 320),
            }
        )
    return output


def stage_candidate_contract_issues(
    candidates: list[dict[str, Any]],
    *,
    evolution: bool,
) -> list[str]:
    """Check the public, auditable SciDialect stage contract."""

    issues: list[str] = []
    required_scores = {"novelty", "grounding", "feasibility", "discriminability"}
    identifiers: list[str] = []
    for index, candidate in enumerate(candidates):
        prefix = f"candidate[{index}]"
        candidate_id = str(candidate.get("candidate_id") or "").strip()
        identifiers.append(candidate_id)
        if not candidate.get("explicit_candidate_id") or not candidate_id:
            issues.append(f"{prefix} lacks an explicit candidate_id")
        scores_value = candidate.get("scores")
        scores: dict[str, Any] = scores_value if isinstance(scores_value, dict) else {}
        missing_scores = sorted(required_scores - set(scores))
        if missing_scores:
            issues.append(f"{prefix} lacks scores: {', '.join(missing_scores)}")
        if not str(candidate.get("selection_rationale") or "").strip():
            issues.append(f"{prefix} lacks a score/selection rationale")
        idea_value = candidate.get("idea")
        if not is_idea_card_payload(idea_value):
            issues.append(f"{prefix} lacks an Idea Card title or thesis")
        if evolution:
            if not str(candidate.get("critique") or "").strip():
                issues.append(f"{prefix} lacks critique")
            if not str(candidate.get("changes") or "").strip():
                issues.append(f"{prefix} lacks changes")
    nonempty_ids = [item for item in identifiers if item]
    if len(nonempty_ids) != len(set(nonempty_ids)):
        issues.append("candidate_id values must be unique")
    return issues


def is_idea_card_payload(payload: Any) -> bool:
    return (
        isinstance(payload, dict)
        and bool(str(payload.get("title") or "").strip())
        and bool(str(payload.get("thesis") or payload.get("one_sentence_thesis") or "").strip())
    )


def unwrap_idea_card(payload: Any) -> dict[str, Any] | None:
    """Accept common provider wrappers while requiring an actual Idea Card."""

    for layer in response_layers(payload):
        if is_idea_card_payload(layer):
            return dict(layer)
        for key in IDEA_CARD_WRAPPER_KEYS:
            candidate = layer.get(key)
            if is_idea_card_payload(candidate):
                assert isinstance(candidate, dict)
                return dict(candidate)
    return None


def stage_candidate_items(payload: Any, *, key: str) -> list[Any]:
    """Find one explicitly named candidate list inside common response wrappers."""

    candidate_keys = EVOLUTION_LIST_KEYS if key == "evolutions" else (key,)
    for layer in response_layers(payload):
        for candidate_key in candidate_keys:
            value = layer.get(candidate_key)
            if isinstance(value, list):
                return value
    return []


def response_layers(payload: Any) -> list[dict[str, Any]]:
    """Traverse only known provider wrapper objects, never arbitrary model content."""

    if not isinstance(payload, dict):
        return []
    output: list[dict[str, Any]] = []
    queue: list[dict[str, Any]] = [payload]
    seen: set[int] = set()
    while queue:
        layer = queue.pop(0)
        identity = id(layer)
        if identity in seen:
            continue
        seen.add(identity)
        output.append(layer)
        for wrapper_key in RESPONSE_WRAPPER_KEYS:
            nested = layer.get(wrapper_key)
            if isinstance(nested, dict):
                queue.append(nested)
    return output


def wrapped_response_value(payload: Any, key: str) -> Any:
    """Read final-selection audit metadata from the same accepted wrappers."""

    for layer in response_layers(payload):
        value = layer.get(key)
        if value not in (None, ""):
            return value
    return None


def strongest_candidates(candidates: list[dict[str, Any]], *, count: int) -> list[dict[str, Any]]:
    def score(candidate: dict[str, Any]) -> float:
        values = [
            float(value)
            for value in (candidate.get("scores") or {}).values()
            if isinstance(value, (int, float))
        ]
        return sum(values) / len(values) if values else 0.0

    ranked = sorted(enumerate(candidates), key=lambda item: (-score(item[1]), item[0]))
    return [candidate for _, candidate in ranked[: max(1, int(count))]]


def candidate_trace_summary(
    candidate: dict[str, Any], *, include_critique: bool = False
) -> dict[str, Any]:
    idea_value = candidate.get("idea")
    idea: dict[str, Any] = idea_value if isinstance(idea_value, dict) else {}
    summary: dict[str, Any] = {
        "candidate_id": candidate.get("candidate_id", ""),
        "title": concise_text(idea.get("title"), 180),
        "scores": candidate.get("scores") or {},
        "selection_rationale": concise_text(candidate.get("selection_rationale"), 320),
    }
    if include_critique:
        summary["critique"] = concise_text(candidate.get("critique"), 320)
        summary["changes"] = concise_text(candidate.get("changes"), 320)
    return summary


def degraded_scidialect_result(
    payload: dict[str, Any],
    trace: dict[str, Any],
    warning: str,
    *,
    stage: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    trace["degraded"] = True
    trace.setdefault("warnings", []).append(concise_text(warning, 360))
    trace.setdefault("stages", []).append({"name": stage, "status": "degraded"})
    return dict(payload), trace


def idea_payload_issues(payload: dict[str, Any], packet: EvidencePacket) -> list[str]:
    issues: list[str] = []
    if not str(payload.get("title") or "").strip():
        issues.append("missing title")
    if not str(payload.get("thesis") or payload.get("one_sentence_thesis") or "").strip():
        issues.append("missing thesis")
    if not listify(payload.get("mechanism_design") or payload.get("mechanistic_design")):
        issues.append("missing mechanism design")
    if not listify(payload.get("validation_protocol")):
        issues.append("missing falsifiable validation protocol")
    if not listify(payload.get("metrics")):
        issues.append("missing evaluation metrics or observables")
    details_value = payload.get("methodological_details")
    details: dict[str, Any] = details_value if isinstance(details_value, dict) else {}
    issues.extend(methodological_structure_issues(details))
    references_value = payload.get("source_evidence")
    issues.extend(validate_evidence_references(references_value, packet))
    issues.extend(methodological_math_issues(details))
    issues.extend(generated_math_issues(proposal_content_projection(payload), path="idea"))
    if generator_contamination_present(payload):
        issues.append(
            "proposal content contains an internal generator identifier; generator mode and strategy are metadata, not evidence"
        )
    anchors = {
        term for term in evidence_anchor_terms(packet) if term not in DOMAIN_NEUTRAL_STOPWORDS
    }
    visible = " ".join(
        [
            str(payload.get("title") or ""),
            str(payload.get("thesis") or ""),
            json.dumps(payload.get("mechanism_design") or [], ensure_ascii=False),
            json.dumps(details, ensure_ascii=False),
        ]
    )
    visible_terms = set(lexical_terms(visible))
    if anchors and anchors.isdisjoint(visible_terms):
        issues.append("proposal has no clear lexical anchor to the selected evidence")
    return issues


def canonicalize_explicit_math(value: Any) -> Any:
    """Canonicalize valid explicit math while preserving malformed text for repair.

    The validator can safely add braces or normalize supported Unicode without
    another model call. Truly malformed spans remain unchanged so
    :func:`generated_math_issues` can report them to the single live repair
    stage instead of hiding the defect.
    """

    if isinstance(value, str):
        try:
            return normalize_math_text(value)
        except MathValidationError:
            return value
    if isinstance(value, dict):
        return {key: canonicalize_explicit_math(item) for key, item in value.items()}
    if isinstance(value, list):
        return [canonicalize_explicit_math(item) for item in value]
    if isinstance(value, tuple):
        return tuple(canonicalize_explicit_math(item) for item in value)
    return value


def methodological_structure_issues(details: dict[str, Any]) -> list[str]:
    """Validate the auditable nested methodology contract before persistence."""

    issues: list[str] = []
    if not str(details.get("summary") or "").strip():
        issues.append("missing methodological summary")

    symbols = details.get("symbols")
    if not isinstance(symbols, list):
        issues.append("methodological_details.symbols must be a list")
    else:
        for index, row in enumerate(symbols):
            if not isinstance(row, dict):
                issues.append(
                    f"methodological_details.symbols[{index}] must contain symbol and definition"
                )
                continue
            if not str(row.get("symbol") or "").strip():
                issues.append(f"methodological_details.symbols[{index}] is missing symbol")
            if not str(row.get("definition") or "").strip():
                issues.append(f"methodological_details.symbols[{index}] is missing definition")

    equations = details.get("equations")
    if not isinstance(equations, list):
        issues.append("methodological_details.equations must be a list")
    else:
        for index, row in enumerate(equations):
            if not isinstance(row, dict):
                issues.append(
                    f"methodological_details.equations[{index}] must contain name, latex, and explanation"
                )
                continue
            if not str(row.get("name") or row.get("title") or "").strip():
                issues.append(f"methodological_details.equations[{index}] is missing name")
            if not str(
                row.get("latex") or row.get("formula") or row.get("equation") or ""
            ).strip():
                issues.append(f"methodological_details.equations[{index}] is missing latex")
            if not str(
                row.get("explanation") or row.get("meaning") or row.get("description") or ""
            ).strip():
                issues.append(f"methodological_details.equations[{index}] is missing explanation")

    workflow = details.get("workflow")
    if not isinstance(workflow, list) or not workflow:
        issues.append("missing methodological workflow")
    else:
        for index, row in enumerate(workflow):
            if not isinstance(row, dict):
                issues.append(
                    f"methodological_details.workflow[{index}] must contain step and detail"
                )
                continue
            if not str(row.get("step") or row.get("title") or "").strip():
                issues.append(f"methodological_details.workflow[{index}] is missing step")
            if not str(
                row.get("detail") or row.get("description") or row.get("text") or ""
            ).strip():
                issues.append(f"methodological_details.workflow[{index}] is missing detail")

    checks = details.get("reliability_checks")
    if not isinstance(checks, list):
        issues.append("methodological_details.reliability_checks must be a list")
    else:
        for index, row in enumerate(checks):
            if not isinstance(row, dict):
                issues.append(
                    f"methodological_details.reliability_checks[{index}] must contain check and detail"
                )
                continue
            if not str(row.get("check") or row.get("title") or row.get("name") or "").strip():
                issues.append(
                    f"methodological_details.reliability_checks[{index}] is missing check"
                )
            if not str(
                row.get("detail") or row.get("description") or row.get("text") or ""
            ).strip():
                issues.append(
                    f"methodological_details.reliability_checks[{index}] is missing detail"
                )
    return issues


def methodological_math_issues(details: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    symbols_value = details.get("symbols")
    symbols: list[Any] = symbols_value if isinstance(symbols_value, list) else []
    for index, row in enumerate(symbols):
        raw = row.get("symbol") if isinstance(row, dict) else row
        if not str(raw or "").strip():
            continue
        try:
            spans = tokenize_math_spans(str(raw))
            if (
                len(spans) != 1
                or spans[0].display
                or spans[0].start != 0
                or spans[0].end != len(str(raw).strip())
            ):
                issues.append(
                    f"methodological_details.symbols[{index}] must be one canonical inline $...$ span"
                )
                continue
            normalize_latex_symbol(str(raw))
        except MathValidationError as exc:
            issues.append(f"methodological_details.symbols[{index}]: {exc}")
    equations_value = details.get("equations")
    equations: list[Any] = equations_value if isinstance(equations_value, list) else []
    for index, row in enumerate(equations):
        raw = (
            row.get("latex") or row.get("formula") or row.get("equation")
            if isinstance(row, dict)
            else row
        )
        if not str(raw or "").strip():
            continue
        try:
            spans = tokenize_math_spans(str(raw))
            if (
                len(spans) != 1
                or not spans[0].display
                or spans[0].start != 0
                or spans[0].end != len(str(raw).strip())
            ):
                issues.append(
                    f"methodological_details.equations[{index}] must be one canonical display $$...$$ span"
                )
                continue
            normalize_latex_formula(str(raw), display=True)
        except MathValidationError as exc:
            issues.append(f"methodological_details.equations[{index}]: {exc}")
    return issues


def proposal_content_projection(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove operational metadata before quality and contamination checks."""

    excluded = {
        "trace",
        "lineage",
        "generation_metadata",
        "model",
        "mode",
        "strategy",
        "source_evidence",
    }
    return {key: value for key, value in payload.items() if key not in excluded}


def generator_contamination_present(payload: dict[str, Any]) -> bool:
    visible = json.dumps(proposal_content_projection(payload), ensure_ascii=False)
    return bool(
        GENERATOR_IDENTIFIER_PATTERN.search(visible) or GENERATOR_EVIDENCE_PATTERN.search(visible)
    )


DOMAIN_NEUTRAL_STOPWORDS = {
    "about",
    "based",
    "evidence",
    "like",
    "method",
    "paper",
    "research",
    "selected",
    "study",
    "using",
    "with",
    "analysis",
    "approach",
    "design",
    "model",
    "novel",
    "result",
    "system",
}


def merge_nonempty_payload(original: dict[str, Any], repaired: dict[str, Any]) -> dict[str, Any]:
    output = dict(original)
    for key, value in repaired.items():
        if value not in (None, "", [], {}):
            output[key] = value
    return output


def concise_text(value: Any, limit: int = 320) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: max(0, limit - 3)].rstrip() + "..."


def llm_usage_snapshot(llm: LLMClient) -> dict[str, Any]:
    getter = getattr(llm, "usage_totals", None)
    if not callable(getter):
        return {}
    try:
        value = getter()
    except Exception:  # noqa: BLE001
        return {}
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    return dict(value) if isinstance(value, dict) else {}


def llm_usage_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    if not after:
        return {}
    delta: dict[str, Any] = {}
    for key, value in after.items():
        previous = before.get(key, 0)
        if isinstance(value, (int, float)) and isinstance(previous, (int, float)):
            delta[key] = value - previous
        else:
            delta[key] = value
    return delta


def deterministic_idea_payload(packet: EvidencePacket, mode: str) -> dict[str, Any]:
    """Create an explicit synthetic fixture for offline tests and demos.

    This function is never a live-provider fallback and its output is marked by
    ``Idea.generation_metadata.execution_origin == 'mock_fixture'``.
    """

    anchors = evidence_anchor_terms(packet)
    title_seed = " ".join(anchors[:5]) or "Evidence-Grounded Research Design"
    return {
        "title": f"Evidence-Grounded {title_seed.title()}",
        "thesis": "Combine the selected mechanisms and boundary conditions into a falsifiable research design that is tested against the closest evidence-backed comparator.",
        "novelty_claim": "The proposal makes its evidence-to-mechanism mapping and distinguishing validation outcome explicit.",
        "mechanism_design": [
            "Map extracted ideas, principles, comparators, contexts, and takeaways to explicit design constraints.",
            "Combine only mechanisms whose stated boundary conditions are mutually compatible.",
            "Define an observation that distinguishes the proposal from the nearest comparator.",
        ],
        "methodological_details": fallback_methodological_details(packet),
        "method_variants": [
            "minimal mechanism combination",
            "boundary-condition stress test",
            "comparator-first design",
        ],
        "why_it_might_work": [
            "It preserves source boundary conditions.",
            "It defines a direct distinguishing observation.",
        ],
        "validation_protocol": [
            "Measure the proposal and closest comparator under the same evidence-supported context and report uncertainty."
        ],
        "baselines": ["closest comparator or control identified in the selected evidence"],
        "metrics": ["primary distinguishing observable", "uncertainty", "resource requirement"],
        "risks": [
            "The selected evidence may not cover a boundary condition that dominates the target setting."
        ],
        "assumptions": [
            "The evidence packet contains at least one credible comparator and evaluation context."
        ],
        "derived_principles": [
            "A new mechanism should be paired with an observation that can distinguish it from prior explanations."
        ],
        "source_evidence": source_evidence_rows(packet, limit=12),
        "lineage": calculus_lineage(packet) if mode == "calculus" else {},
        "trace": scidialect_trace(packet, degraded=True) if mode == "scidialect_evo" else {},
    }


def calculus_lineage(packet: EvidencePacket) -> dict[str, Any]:
    nodes = [
        {"id": feature.work_id, "type": "work", "label": feature.title}
        for feature in packet.features[:8]
    ]
    nodes.append(
        {
            "id": "mock_fixture_result",
            "type": "synthetic_fixture",
            "label": "Synthetic offline result",
        }
    )
    edges = [
        {"source": feature.work_id, "target": "mock_fixture_result", "relation": "fixture_input"}
        for feature in packet.features[:8]
    ]
    return {"nodes": nodes, "edges": edges}


def scidialect_trace(packet: EvidencePacket, *, degraded: bool = True) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "strategy": "candidate_evolution",
        "rounds": 3,
        "evidence_items": len(packet.features),
        "top_variant": "candidate_evolution_full",
        "degraded": degraded,
        "warnings": ["No live three-stage trace was available."] if degraded else [],
    }


def normalize_methodological_details(
    value: Any,
    packet: EvidencePacket,
    *,
    allow_fallback: bool = True,
) -> dict[str, Any]:
    details = value if isinstance(value, dict) else {}
    normalized = {
        "summary": str(details.get("summary") or "").strip(),
        "symbols": normalize_method_rows(details.get("symbols"), default_key="definition"),
        "equations": normalize_method_rows(details.get("equations"), default_key="latex"),
        "workflow": normalize_method_rows(details.get("workflow"), default_key="detail"),
        "reliability_checks": normalize_method_rows(
            details.get("reliability_checks"), default_key="detail"
        ),
    }
    if allow_fallback and (not normalized["summary"] or not normalized["workflow"]):
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
    return normalize_math_text(text.strip())


def normalize_latex(value: str) -> str:
    """Backward-compatible equation normalizer using strict display LaTeX."""

    return normalize_latex_formula(value, display=True)


def normalize_inline_latex(value: str) -> str:
    return normalize_latex_symbol(value)


def normalize_inline_math_text(value: str) -> str:
    return normalize_math_text(value)


def fallback_methodological_details(packet: EvidencePacket) -> dict[str, Any]:
    anchors = evidence_anchor_terms(packet)
    anchor_text = ", ".join(anchors[:5]) or "the selected mechanisms and boundary conditions"
    return {
        "summary": "Translate selected evidence into explicit mechanism, context, comparator, and observation constraints, then test the smallest design that can distinguish the proposal from prior explanations.",
        "symbols": [
            {
                "symbol": "$E$",
                "definition": "The selected set of evidence records and their stated boundary conditions.",
            },
            {"symbol": "$M$", "definition": "The proposed mechanism or explanatory model."},
            {
                "symbol": "$C$",
                "definition": "The closest comparator, control, or reference theory.",
            },
            {
                "symbol": "$O$",
                "definition": "A measurable observation that can distinguish $M$ from $C$.",
            },
        ],
        "equations": [
            {
                "name": "Distinguishing contrast",
                "latex": "$$\\Delta_O = O(M, E) - O(C, E)$$",
                "explanation": "Express the discipline-specific observable as a contrast between the proposal and comparator under matched evidence-supported conditions.",
            },
        ],
        "workflow": [
            {
                "step": "Map evidence",
                "detail": f"Record mechanisms, contexts, and boundary conditions associated with {anchor_text}.",
            },
            {
                "step": "Formulate contrast",
                "detail": "State how the proposed mechanism differs from the closest comparator or reference explanation.",
            },
            {
                "step": "Match conditions",
                "detail": "Evaluate both alternatives in the same experimental, observational, computational, or theoretical context.",
            },
            {
                "step": "Assess outcome",
                "detail": "Report the distinguishing observation, uncertainty, failure criteria, and resource requirements.",
            },
        ],
        "reliability_checks": [
            {
                "check": "Evidence provenance",
                "detail": "Every design choice must map to a selected work or be labeled as an assumption.",
            },
            {
                "check": "Matched comparison",
                "detail": "Apply the same conditions and measurement process to the proposal and comparator.",
            },
            {
                "check": "Uncertainty",
                "detail": "Report uncertainty and a result that would falsify or weaken the proposed mechanism.",
            },
        ],
    }


def normalize_source_evidence(value: Any, packet: EvidencePacket) -> list[dict[str, Any]]:
    return hydrate_evidence_references(value, packet)[:MAX_SOURCE_EVIDENCE_REFERENCES]


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


def sanitize_tool_leakage_payload(
    payload: dict[str, Any], packet: EvidencePacket
) -> dict[str, Any]:
    """Deprecated compatibility shim; validation now rejects contamination.

    Principia never rewrites scientific language after generation because doing
    so can corrupt legitimate terms such as "learned machine dialects".
    """

    _ = packet
    return dict(payload)


def sanitize_tool_leakage_value(value: Any, packet: EvidencePacket) -> Any:
    _ = packet
    return value


def sanitize_tool_leakage_text(value: str, packet: EvidencePacket) -> str:
    _ = packet
    return str(value)


def evidence_corpus(packet: EvidencePacket) -> str:
    return " ".join(
        [
            packet.query,
            packet.user_note,
            json.dumps([feature.model_dump() for feature in packet.features], ensure_ascii=False),
        ]
    )


def evidence_anchor_terms(packet: EvidencePacket) -> list[str]:
    # Evidence-derived vocabulary comes first so a long user note cannot crowd
    # out domain-specific terms (for example ``resonator`` or ``haloscope``).
    # The shared tokenizer splits hyphenated compounds and retains their joined
    # form, while conservative stemming connects simple surface inflections.
    text_parts = [
        *[feature.title for feature in packet.features],
        *[
            str(item.get("name") or item.get("title") or item.get("argument") or "")
            for feature in packet.features
            for item in feature.principles[:2]
        ],
        packet.user_note,
    ]
    tokens: list[str] = []
    for text_part in text_parts:
        for token in lexical_terms(text_part):
            if token not in tokens:
                tokens.append(token)
    return tokens


def lexical_terms(value: Any) -> list[str]:
    """Return comparable domain terms without language- or field-specific lists.

    Hyphenated forms contribute both components and the joined form, so
    ``axion-like`` can ground ``axion`` while still preserving ``axionlike``.
    Only conservative English surface inflections are normalized; canonical
    evidence-reference checks remain separate and authoritative.
    """

    text = unicodedata.normalize("NFKC", str(value or "")).lower().replace("_", "-")
    raw_terms = re.findall(r"[^\W_]+(?:[-\u2010-\u2015][^\W_]+)*", text, flags=re.UNICODE)
    output: list[str] = []
    for raw in raw_terms:
        parts = [part for part in re.split(r"[-\u2010-\u2015]+", raw) if part]
        candidates = [*parts]
        if len(parts) > 1:
            candidates.append("".join(parts))
        for candidate in candidates:
            for term in _lexical_variants(candidate):
                if len(term) >= 4 and term not in output:
                    output.append(term)
    return output


def _lexical_variants(token: str) -> list[str]:
    variants = [token]
    stem = token
    if len(token) > 5 and token.endswith("ies"):
        stem = token[:-3] + "y"
    elif len(token) > 4 and token.endswith("s") and not token.endswith(
        ("ss", "us", "is", "ics")
    ):
        stem = token[:-1]
    elif len(token) > 6 and token.endswith("ing"):
        base = token[:-3]
        stem = base + "e" if base.endswith(("v", "z")) else base
    elif len(token) > 5 and token.endswith("ed"):
        base = token[:-2]
        stem = base + "e" if base.endswith(("v", "z")) else base
    if stem != token:
        variants.append(stem)
    return variants


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
