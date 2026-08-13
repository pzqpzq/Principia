from __future__ import annotations

import json
from pathlib import Path

import pytest

from principia.features import normalize_feature_payload_aliases, select_evidence
from principia.ideas import (
    IdeaService,
    deterministic_idea_payload,
    idea_payload_issues,
    parse_stage_candidates,
)
from principia.llm import LLMClient, LLMConfig
from principia.models import (
    EvidencePacket,
    ExtractedFeatures,
    SciDialectConfig,
    WorkFeatures,
    WorkItem,
    WorkList,
)
from principia.storage import WorkspaceStorage
from principia_retrieval import SearchDiagnostics


def feature(work_index: int) -> WorkFeatures:
    return WorkFeatures(
        work_id=f"W{work_index}",
        title=f"Quantum sensing evidence {work_index}",
        model="test",
        ideas=[
            {
                "id": f"I{work_index}",
                "title": "Sensing idea",
                "core_idea": "Use resonator response.",
            }
        ],
        principles=[
            {
                "id": f"P{work_index}",
                "name": "Noise principle",
                "argument": "Match noise to bandwidth.",
            }
        ],
        takeaways=[
            {"id": f"T{work_index}", "title": "Sensing takeaway", "message": "Report uncertainty."}
        ],
    )


def complete_idea(title: str, evidence_id: str = "W0") -> dict:
    return {
        "title": title,
        "thesis": "Use quantum resonator sensing with matched noise controls to distinguish a broadband signal.",
        "novelty_claim": "The design jointly treats bandwidth and false-positive discrimination.",
        "mechanism_design": [
            "Couple a broadband resonator response to an uncertainty-aware signal discriminator."
        ],
        "methodological_details": {
            "summary": "Measure resonator response under signal and matched-control conditions.",
            "symbols": [],
            "equations": [],
            "workflow": [
                {"step": "Measure response", "detail": "Compare signal and control observations."}
            ],
            "reliability_checks": [
                {"check": "False positives", "detail": "Test injected artifacts."}
            ],
        },
        "method_variants": ["wide-band scan"],
        "why_it_might_work": ["The evidence supports resonator sensitivity."],
        "validation_protocol": ["Run blinded signal injections and matched-noise controls."],
        "baselines": ["unsqueezed resonator control"],
        "metrics": ["detection efficiency", "false-positive rate"],
        "risks": ["Noise drift can mimic a signal."],
        "assumptions": ["The resonator response is stable over a scan."],
        "derived_principles": ["Sensitivity claims require matched false-positive controls."],
        "source_evidence": [{"work_id": evidence_id, "id": f"I{evidence_id[1:]}", "kind": "ideas"}],
    }


def test_grounding_guard_normalizes_physics_hyphens_and_inflections() -> None:
    packet = EvidencePacket(
        features=[
            WorkFeatures(
                work_id="W0",
                title=(
                    "Axion-like dark-matter haloscopes with superconducting resonators "
                    "and squeezed states"
                ),
                model="test",
                ideas=[{"id": "I0", "core_idea": "Use a resonator haloscope scan."}],
                principles=[
                    {
                        "id": "P0",
                        "name": "Squeezed-state readout",
                        "argument": "Squeezing can increase the resonator scan rate.",
                    }
                ],
            )
        ]
    )
    payload = complete_idea("Dual-chain axion haloscope scan")
    payload["thesis"] = "Use resonator readout and squeezing to test an axion signal."

    assert "proposal has no clear lexical anchor to the selected evidence" not in (
        idea_payload_issues(payload, packet)
    )


def test_grounding_guard_rejects_off_domain_proposal_and_ignores_generic_like() -> None:
    packet = EvidencePacket(
        features=[
            WorkFeatures(
                work_id="W0",
                title="Axion-like dark-matter haloscopes with superconducting resonators",
                model="test",
                ideas=[{"id": "I0", "core_idea": "Use a resonator haloscope scan."}],
                principles=[
                    {
                        "id": "P0",
                        "name": "Squeezed-state receiver",
                        "argument": "Squeezing increases scan rate under quantum noise.",
                    }
                ],
            )
        ]
    )
    payload = complete_idea("Coordinate software agents like cooperative peers")
    payload["thesis"] = "Compress messages while retaining interpretable team decisions."
    payload["mechanism_design"] = ["Route messages through a learned communication graph."]
    payload["methodological_details"] = {
        "summary": "Train communicating agents and measure held-out task accuracy.",
        "symbols": [],
        "equations": [],
        "workflow": [{"step": "Train", "detail": "Optimize a coordination policy."}],
        "reliability_checks": [],
    }

    assert "proposal has no clear lexical anchor to the selected evidence" in (
        idea_payload_issues(payload, packet)
    )


def test_grounding_guard_remains_compatible_with_ai_domain_vocabulary() -> None:
    packet = EvidencePacket(
        features=[
            WorkFeatures(
                work_id="W0",
                title="Learned machine dialects for multi-agent communication",
                model="test",
                ideas=[{"id": "I0", "core_idea": "Learn compact agent messages."}],
                principles=[
                    {
                        "id": "P0",
                        "name": "Protocol collapse control",
                        "argument": "Monitor message entropy and semantic recovery.",
                    }
                ],
            )
        ]
    )
    payload = complete_idea("Entropy-regularized learned machine dialect")
    payload["thesis"] = "Prevent protocol collapse while preserving agent communication."

    assert "proposal has no clear lexical anchor to the selected evidence" not in (
        idea_payload_issues(payload, packet)
    )


class ThreeStageLLM(LLMClient):
    def __init__(self) -> None:
        super().__init__(
            LLMConfig(
                provider="custom",
                model="three-stage",
                api_key="test",
                base_url="https://example.test",
            )
        )

    def available(self, model: str = "auto") -> bool:
        return True

    def resolve(self, model: str = "auto") -> LLMConfig:
        return self.config

    def chat_json(self, system: str, user: str, **kwargs):
        self._begin_call(self.config)
        self._finish_call(success=True, usage={"prompt_tokens": 10, "completion_tokens": 5})
        if system.startswith("Generate three distinct"):
            return {
                "candidates": [
                    {
                        "candidate_id": f"C{index}",
                        "idea": complete_idea(f"Quantum Resonator Design {index}"),
                        "scores": {
                            "novelty": 0.5 + index / 10,
                            "grounding": 0.8,
                            "feasibility": 0.7,
                            "discriminability": 0.75,
                        },
                        "selection_rationale": "Grounded candidate with a distinct bandwidth-control tradeoff.",
                    }
                    for index in range(1, 4)
                ]
            }
        if system.startswith("Critique and evolve"):
            return {
                "evolutions": [
                    {
                        "candidate_id": candidate_id,
                        "idea": complete_idea(f"Evolved Quantum Resonator {candidate_id}"),
                        "scores": {
                            "novelty": 0.9,
                            "grounding": 0.9,
                            "feasibility": 0.8,
                            "discriminability": 0.9,
                        },
                        "critique": "The original needed a more explicit false-positive control.",
                        "changes": "Added blinded injections and matched-noise controls.",
                        "selection_rationale": "The evolved design has a falsifiable distinguishing observation.",
                    }
                    for candidate_id in ("C3", "C2")
                ]
            }
        if system.startswith("Select and finalize"):
            return {
                **complete_idea("Broadband Quantum Resonator Validation"),
                "selected_candidate_id": "C3",
                "selection_rationale": "C3 best balances grounding, feasibility, and false-positive discrimination.",
            }
        raise AssertionError(f"Unexpected stage: {system}")


class WrappedFinalLLM(ThreeStageLLM):
    def chat_json(self, system: str, user: str, **kwargs):
        if system.startswith("Select and finalize"):
            self._begin_call(self.config)
            self._finish_call(success=True, usage={"prompt_tokens": 10, "completion_tokens": 5})
            return {
                "idea": complete_idea("Wrapped Broadband Quantum Resonator"),
                "selected_candidate_id": "C3",
                "selection_rationale": "The wrapped final candidate is fully grounded.",
            }
        return super().chat_json(system, user, **kwargs)


class InvalidFinalLLM(ThreeStageLLM):
    def chat_json(self, system: str, user: str, **kwargs):
        if system.startswith("Select and finalize"):
            self._begin_call(self.config)
            self._finish_call(success=True, usage={"prompt_tokens": 10, "completion_tokens": 5})
            return {"selection_rationale": "Missing the required final Idea Card."}
        return super().chat_json(system, user, **kwargs)


class NestedAliasLLM(ThreeStageLLM):
    def chat_json(self, system: str, user: str, **kwargs):
        if system.startswith("Critique and evolve"):
            self._begin_call(self.config)
            self._finish_call(success=True, usage={"prompt_tokens": 10, "completion_tokens": 5})
            return {
                "response": {
                    "data": {
                        "revised_candidates": [
                            {
                                "candidate_id": candidate_id,
                                "revised_idea": complete_idea(
                                    f"Revised Quantum Resonator {candidate_id}"
                                ),
                                "scores": {
                                    "novelty": 0.9,
                                    "grounding": 0.9,
                                    "feasibility": 0.8,
                                    "discriminability": 0.9,
                                },
                                "critique": "The original needed a more explicit false-positive control.",
                                "changes": "Added blinded injections and matched-noise controls.",
                                "selection_rationale": "The revision is grounded and falsifiable.",
                            }
                            for candidate_id in ("C3", "C2")
                        ]
                    }
                }
            }
        if system.startswith("Select and finalize"):
            self._begin_call(self.config)
            self._finish_call(success=True, usage={"prompt_tokens": 10, "completion_tokens": 5})
            return {
                "response": {
                    "result": {
                        "idea_card": complete_idea("Nested Broadband Quantum Resonator"),
                        "selected_candidate_id": "C2",
                        "selection_rationale": "C2 has the strongest falsification protocol.",
                    }
                }
            }
        return super().chat_json(system, user, **kwargs)


class InvalidEvolutionLLM(ThreeStageLLM):
    def chat_json(self, system: str, user: str, **kwargs):
        if system.startswith("Critique and evolve"):
            self._begin_call(self.config)
            self._finish_call(success=True, usage={"prompt_tokens": 10, "completion_tokens": 5})
            return {
                "output": {
                    "critiqued_candidates": [
                        {
                            "candidate_id": "C3",
                            "evolved_idea": complete_idea("Valid Evolved Candidate"),
                        },
                        {
                            "candidate_id": "C2",
                            "evolved_idea": {"title": "Missing thesis"},
                        },
                    ]
                }
            }
        return super().chat_json(system, user, **kwargs)


def test_work_models_add_identifiers_diagnostics_and_provenance() -> None:
    work = WorkItem(
        id="W1",
        title="Cross-domain work",
        semantic_scholar_id="S2-1",
        pmid="12345",
        pdf_url="https://example.test/paper.pdf",
    )
    works = WorkList(query="cross-domain", items=[work])
    extracted = WorkFeatures(
        work_id="W1",
        title=work.title,
        model="test",
        source_content_type="html",
        source_url="https://example.test/paper",
        source_excerpt_chars=4312,
        source_content_hash="sha256:abc",
        extractor_fingerprint="extractor-v133",
        extraction_warnings=["PDF unavailable; used HTML."],
    )

    assert isinstance(works.diagnostics, SearchDiagnostics)
    assert works.diagnostics.complete is False
    assert extracted.source_content_type == "html"
    assert extracted.source_excerpt_chars == 4312
    assert extracted.extraction_warnings
    assert WorkItem.model_validate(work.model_dump()).pmid == "12345"


def test_persisted_work_and_feature_titles_reload_without_html_markup() -> None:
    raw_title = "Calibration of <i>in situ</i> H<sub>2</sub>O &amp; CO<sub>2</sub> sensing"
    expected = "Calibration of in situ H2O & CO2 sensing"
    work_payload = json.dumps({"id": "W-HTML", "title": raw_title})
    feature_payload = json.dumps(
        {"work_id": "W-HTML", "title": raw_title, "model": "siliconflow:test"}
    )

    assert WorkItem.model_validate_json(work_payload).title == expected
    assert WorkFeatures.model_validate_json(feature_payload).title == expected


def test_cross_domain_aliases_normalize_with_record_types() -> None:
    item = WorkFeatures(
        work_id="W1",
        title="Quantum experiment",
        model="test",
        comparators=[{"name": "standard quantum limit"}],
        controls=["unsqueezed control"],
        evaluation_contexts=[{"name": "broadband scan"}],
        experimental_systems=[{"name": "superconducting resonator"}],
    )
    payload = normalize_feature_payload_aliases(
        {
            "comparators": [{"name": "reference theory"}],
            "controls": ["null injection"],
            "experimental_systems": ["cryogenic resonator"],
        }
    )

    assert [record["record_type"] for record in item.baselines] == ["comparator", "control"]
    assert [record["record_type"] for record in item.benchmarks] == [
        "evaluation_context",
        "experimental_system",
    ]
    assert [record["record_type"] for record in payload["baselines"]] == ["comparator", "control"]
    assert payload["benchmarks"][0]["record_type"] == "experimental_system"


def test_evidence_selection_enforces_exact_global_counts_and_work_capacity() -> None:
    features = ExtractedFeatures(items=[feature(index) for index in range(10)], model="test")
    selected = select_evidence(
        features,
        kinds=["ideas", "principles", "takeaways"],
        global_kind_limits={"ideas": 5, "principles": 5, "takeaways": 5},
        max_per_work=2,
        require_exact=True,
    )

    assert selected.counts() == {
        "works": 10,
        "ideas": 5,
        "principles": 5,
        "takeaways": 5,
        "baselines": 0,
        "benchmarks": 0,
        "result_facts": 0,
    }
    assert all(
        sum(len(getattr(item, kind)) for kind in ("ideas", "principles", "takeaways")) <= 2
        for item in selected.features
    )

    legacy = select_evidence(features, kinds=["ideas", "principles"], limit_per_kind=1)
    assert legacy.counts()["ideas"] == 10
    assert legacy.counts()["principles"] == 10


def test_evidence_selection_reports_infeasible_exact_packet() -> None:
    features = ExtractedFeatures(items=[feature(0)], model="test")
    with pytest.raises(ValueError, match="Unable to satisfy exact global evidence counts"):
        select_evidence(
            features,
            kinds=["ideas", "principles", "takeaways"],
            global_kind_limits={"ideas": 2, "principles": 2, "takeaways": 2},
            max_per_work=2,
            require_exact=True,
        )


def test_scidialect_runs_three_stages_and_preserves_same_title_history(tmp_path: Path) -> None:
    llm = ThreeStageLLM()
    storage = WorkspaceStorage(tmp_path)
    service = IdeaService(storage, llm)
    evidence = ExtractedFeatures(items=[feature(0)], model="test")

    first = service.generate(
        evidence,
        user_note="quantum sensing with broadband resonators",
        model="custom:three-stage",
        scidialect_config=SciDialectConfig(),
    )
    second = service.generate(
        evidence,
        user_note="quantum sensing with broadband resonators",
        mode="scidialect-evo",
        model="custom:three-stage",
    )

    assert first.mode == "scidialect_evo"
    assert first.trace["degraded"] is False
    assert [stage["name"] for stage in first.trace["stages"]] == [
        "candidate_generation",
        "critique_evolution",
        "final_selection",
    ]
    assert first.trace["selected_candidate_id"] == "C3"
    assert first.generation_metadata["llm_usage"]["calls"] == 3
    first_run = storage.get_run(first.run_id)
    assert first_run is not None
    assert first_run.counts["llm_usage"]["calls"] == 3
    assert first.id != second.id
    assert storage.counts()["ideas"] == 2

    overwritten = service.generate(
        evidence,
        user_note="quantum sensing with broadband resonators",
        mode="scidialect-evo",
        model="custom:three-stage",
        overwrite=True,
    )
    assert overwritten.id == first.id
    assert overwritten.generation_metadata["replaced_idea_id"] == first.id
    assert storage.counts()["ideas"] == 2


def test_scidialect_accepts_common_final_idea_wrapper(tmp_path: Path) -> None:
    service = IdeaService(WorkspaceStorage(tmp_path), WrappedFinalLLM())

    idea = service.generate(
        ExtractedFeatures(items=[feature(0)], model="test"),
        mode="scidialect-evo",
        model="custom:three-stage",
        scidialect_config=SciDialectConfig(allow_degraded_fallback=False),
    )

    assert idea.title == "Wrapped Broadband Quantum Resonator"
    assert idea.trace["degraded"] is False
    assert idea.trace["stages"][-1]["status"] == "complete"


@pytest.mark.parametrize(
    "list_key",
    ["evolutions", "evolved_candidates", "revised_candidates", "critiqued_candidates"],
)
@pytest.mark.parametrize(
    "idea_key",
    ["idea", "evolved_idea", "revised_idea", "candidate", "idea_card"],
)
def test_evolution_parser_accepts_documented_aliases_and_nested_wrappers(
    list_key: str,
    idea_key: str,
) -> None:
    payload = {
        "response": {
            "data": {
                list_key: [
                    {
                        "candidate_id": candidate_id,
                        idea_key: complete_idea(f"Aliased Candidate {candidate_id}"),
                        "scores": {"grounding": 0.9},
                        "selection_rationale": "The candidate is grounded.",
                    }
                    for candidate_id in ("C3", "C2")
                ]
            }
        }
    }

    parsed = parse_stage_candidates(payload, key="evolutions")

    assert [item["candidate_id"] for item in parsed] == ["C3", "C2"]
    assert [item["idea"]["title"] for item in parsed] == [
        "Aliased Candidate C3",
        "Aliased Candidate C2",
    ]


def test_scidialect_preserves_final_audit_fields_through_nested_wrappers(tmp_path: Path) -> None:
    service = IdeaService(WorkspaceStorage(tmp_path), NestedAliasLLM())

    idea = service.generate(
        ExtractedFeatures(items=[feature(0)], model="test"),
        mode="scidialect-evo",
        model="custom:three-stage",
        scidialect_config=SciDialectConfig(allow_degraded_fallback=False),
    )

    assert idea.title == "Nested Broadband Quantum Resonator"
    assert idea.trace["degraded"] is False
    assert idea.trace["selected_candidate_id"] == "C2"
    assert idea.trace["selection_rationale"] == "C2 has the strongest falsification protocol."


def test_scidialect_strict_mode_rejects_incomplete_evolution_alias(tmp_path: Path) -> None:
    service = IdeaService(WorkspaceStorage(tmp_path), InvalidEvolutionLLM())

    with pytest.raises(
        RuntimeError, match=r"evolution stage returned 1 usable evolution\(s\), expected 2"
    ):
        service.generate(
            ExtractedFeatures(items=[feature(0)], model="test"),
            mode="scidialect-evo",
            model="custom:three-stage",
            scidialect_config=SciDialectConfig(allow_degraded_fallback=False),
        )


def test_scidialect_strict_mode_rejects_invalid_final_stage(tmp_path: Path) -> None:
    service = IdeaService(WorkspaceStorage(tmp_path), InvalidFinalLLM())

    with pytest.raises(RuntimeError, match="final selection did not return a usable Idea Card"):
        service.generate(
            ExtractedFeatures(items=[feature(0)], model="test"),
            mode="scidialect-evo",
            model="custom:three-stage",
            scidialect_config=SciDialectConfig(allow_degraded_fallback=False),
        )


def test_offline_fallback_is_domain_neutral() -> None:
    payload = deterministic_idea_payload(
        select_evidence([feature(0)], kinds=["ideas", "principles", "takeaways"]),
        "scidialect_evo",
    )
    visible = str(payload).lower()
    assert "coding agent" not in visible
    assert "repository" not in visible
    assert payload["trace"]["degraded"] is True
