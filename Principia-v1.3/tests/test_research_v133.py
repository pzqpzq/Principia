from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import principia as pc
import principia.research as research_module
from principia.llm import LLMConfig
from principia.research import SourceContent


class ExtractionLLM(pc.LLMClient):
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        super().__init__(LLMConfig.from_model("mock"))
        self.responses = list(responses)
        self.calls = 0
        self.prompts: list[tuple[str, str]] = []

    def available(self, model: str = "auto") -> bool:
        return True

    def resolve(self, model: str = "auto") -> LLMConfig:
        return LLMConfig(
            provider="custom",
            model="cross-domain-extractor",
            api_key="test",
            base_url="https://example.test/v1",
        )

    def chat_json(self, system: str, user: str, **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        self.prompts.append((system, user))
        return self.responses[min(self.calls - 1, len(self.responses) - 1)]


def valid_payload() -> dict[str, Any]:
    return {
        "ideas": [
            {"title": "Resonator scan", "core_idea": "Scan resonances under calibrated noise."}
        ],
        "principles": [
            {"name": "Blind calibration", "argument": "Calibrate without signal leakage."}
        ],
        "takeaways": [
            {"title": "Track drift", "message": "Track resonator drift during acquisition."}
        ],
        "comparators": [{"name": "Unsqueezed readout"}],
        "experimental_systems": [{"name": "Superconducting resonator array"}],
        "result_facts": [],
    }


def test_extraction_records_full_provenance_and_prompt_cache_identity(
    tmp_path: Path, monkeypatch: Any
) -> None:
    llm = ExtractionLLM([valid_payload(), valid_payload()])
    workspace = pc.Workspace(tmp_path, llm=llm)
    work = pc.WorkItem(id="AXION", title="Broadband axion sensing", abstract="Abstract fallback.")
    evidence = "A superconducting resonator scan uses squeezed readout and calibrated noise. " * 20
    monkeypatch.setattr(
        research_module,
        "fetch_source_content",
        lambda *args, **kwargs: SourceContent(
            text=evidence,
            content_type="pdf_text",
            source_url="https://example.test/paper.pdf",
            warnings=("OCR normalized one symbol.",),
        ),
    )

    first = workspace.research.extract([work], model="custom:cross-domain-extractor")
    monkeypatch.setattr(research_module, "EXTRACTOR_FINGERPRINT", "f" * 64)
    second = workspace.research.extract([work], model="custom:cross-domain-extractor")

    assert llm.calls == 2
    assert first.items[0].source_content_type == "pdf_text"
    assert first.items[0].source_url == "https://example.test/paper.pdf"
    assert first.items[0].source_excerpt_chars == len(evidence)
    assert len(first.items[0].source_content_hash) == 64
    assert len(first.items[0].extractor_fingerprint) == 64
    assert first.items[0].baselines[0]["record_type"] == "comparator"
    assert first.items[0].benchmarks[0]["record_type"] == "experimental_system"
    assert second.items[0].skipped is False
    assert workspace.counts()["extractions"] == 2


def test_real_extraction_repairs_missing_and_off_domain_fields_once(
    tmp_path: Path, monkeypatch: Any
) -> None:
    invalid = {
        "ideas": [{"title": "Leak", "core_idea": "Use an autonomous coding agent."}],
        "principles": [],
        "takeaways": [],
    }
    llm = ExtractionLLM([invalid, valid_payload()])
    workspace = pc.Workspace(tmp_path, llm=llm)
    work = pc.WorkItem(id="PHYSICS", title="Superconducting resonator quantum sensing")
    evidence = (
        "Squeezed microwave states improve resonator readout under a calibrated noise model. " * 10
    )
    monkeypatch.setattr(
        research_module,
        "fetch_source_content",
        lambda *args, **kwargs: SourceContent(text=evidence, content_type="html"),
    )

    extracted = workspace.research.extract([work], model="custom:cross-domain-extractor")

    assert llm.calls == 2
    assert extracted.items[0].principles
    assert extracted.items[0].takeaways
    assert any("repair call" in warning for warning in extracted.items[0].extraction_warnings)


def test_real_extraction_detects_domain_neutral_off_domain_records(
    tmp_path: Path, monkeypatch: Any
) -> None:
    invalid = {
        "ideas": [
            {"title": "Crop intervention", "core_idea": "Edit a drought-response wheat gene."}
        ],
        "principles": [
            {"name": "Soil ecology", "argument": "Optimize rhizosphere microbial diversity."}
        ],
        "takeaways": [
            {"title": "Field trial", "message": "Measure crop yield across irrigation regimes."}
        ],
    }
    llm = ExtractionLLM([invalid, valid_payload()])
    workspace = pc.Workspace(tmp_path, llm=llm)
    work = pc.WorkItem(id="QUANTUM", title="Superconducting resonator quantum sensing")
    evidence = (
        "Squeezed microwave states improve resonator readout under calibrated quantum noise. " * 10
    )
    monkeypatch.setattr(
        research_module,
        "fetch_source_content",
        lambda *args, **kwargs: SourceContent(text=evidence, content_type="html"),
    )

    extracted = workspace.research.extract([work], model="custom:cross-domain-extractor")

    assert llm.calls == 2
    assert extracted.items[0].principles
    assert any(
        "off-domain or ungrounded" in warning for warning in extracted.items[0].extraction_warnings
    )


def test_real_extraction_repairs_unsupported_formula_and_benchmark(
    tmp_path: Path, monkeypatch: Any
) -> None:
    invalid = valid_payload()
    invalid["ideas"][0]["latex"] = "crop_yield = rainfall / fertilizer"
    invalid["benchmarks"] = [{"name": "ImageNet visual classification leaderboard"}]
    llm = ExtractionLLM([invalid, valid_payload()])
    workspace = pc.Workspace(tmp_path, llm=llm)
    work = pc.WorkItem(id="RESONATOR", title="Calibrated superconducting resonator scan")
    evidence = "A superconducting resonator scan uses squeezed readout and calibrated noise. " * 10
    monkeypatch.setattr(
        research_module,
        "fetch_source_content",
        lambda *args, **kwargs: SourceContent(text=evidence, content_type="pdf_text"),
    )

    extracted = workspace.research.extract([work], model="custom:cross-domain-extractor")

    assert llm.calls == 2
    warnings = " ".join(extracted.items[0].extraction_warnings)
    assert "equation or formula" in warnings
    assert "ungrounded benchmarks" in warnings


def test_live_extraction_rejects_persistent_unsafe_math_without_persistence(
    tmp_path: Path, monkeypatch: Any
) -> None:
    invalid = valid_payload()
    invalid["ideas"][0]["core_idea"] = "Use $M = (I - \x0crac{r}{r}P)^{-1}$ for diagnosis."
    llm = ExtractionLLM([invalid, invalid])
    workspace = pc.Workspace(tmp_path, llm=llm)
    work = pc.WorkItem(id="MATH", title="Successor representation diagnostic")
    evidence = "The successor representation M diagnoses communication topology. " * 10
    monkeypatch.setattr(
        research_module,
        "fetch_source_content",
        lambda *args, **kwargs: SourceContent(text=evidence, content_type="pdf_text"),
    )

    with pytest.raises(ValueError, match="remained invalid after one evidence-grounded repair"):
        workspace.research.extract([work], model="custom:cross-domain-extractor")

    assert llm.calls == 2
    initial_prompt = llm.prompts[0][1]
    repair_prompt = llm.prompts[1][1]
    assert "<END_UNTRUSTED_SOURCE_EVIDENCE>" in initial_prompt
    assert repair_prompt.index("Mathematical validation failed") < repair_prompt.index(
        "<BEGIN_UNTRUSTED_SOURCE_EVIDENCE>"
    )
    repair_context = repair_prompt.split("<BEGIN_UNTRUSTED_SOURCE_EVIDENCE>", 1)[0]
    assert "\\f" not in repair_context
    assert '"core_idea": null' in repair_context
    assert "<END_UNTRUSTED_SOURCE_EVIDENCE>" in repair_prompt
    assert workspace.counts()["extractions"] == 0


def test_live_extraction_repairs_bare_mathematical_unicode(
    tmp_path: Path, monkeypatch: Any
) -> None:
    invalid = valid_payload()
    invalid["principles"][0]["evidence"] = "Noise scale σ controls calibration stability."
    repaired = valid_payload()
    repaired["principles"][0]["evidence"] = (
        "Noise scale controls calibration stability."
    )
    llm = ExtractionLLM([invalid, repaired])
    workspace = pc.Workspace(tmp_path, llm=llm)
    work = pc.WorkItem(id="UNICODE-MATH", title="Calibrated resonator noise scale")
    evidence = (
        "A superconducting resonator scan uses squeezed readout and calibrated noise. "
        "Calibrate without signal leakage and track resonator drift during acquisition. "
        "The resonator noise scale controls calibration stability. "
    ) * 10
    monkeypatch.setattr(
        research_module,
        "fetch_source_content",
        lambda *args, **kwargs: SourceContent(text=evidence, content_type="pdf_text"),
    )

    extracted = workspace.research.extract(
        [work], model="custom:cross-domain-extractor"
    )

    assert llm.calls == 2
    repair_prompt = llm.prompts[1][1]
    assert "Mathematical validation failed" in repair_prompt
    repair_context = repair_prompt.split("<BEGIN_UNTRUSTED_SOURCE_EVIDENCE>", 1)[0]
    assert '"evidence": null' in repair_context
    assert "σ" not in repair_context
    assert "Never copy Unicode mathematical symbols" in repair_context
    assert "rewrite U+03C3 as `sigma`" in repair_context
    assert extracted.items[0].principles[0]["evidence"] == (
        "Noise scale controls calibration stability."
    )


def test_extraction_allows_genuinely_empty_individual_category(
    tmp_path: Path, monkeypatch: Any
) -> None:
    payload = valid_payload()
    payload["principles"] = []
    llm = ExtractionLLM([payload])
    workspace = pc.Workspace(tmp_path, llm=llm)
    evidence = (
        "Scan resonances under calibrated noise. Calibrate without signal leakage. "
        "Track resonator drift during acquisition. Compare unsqueezed readout in a "
        "superconducting resonator array. "
    ) * 10
    work = pc.WorkItem(id="EMPTY-PRINCIPLE", title="Resonator scan")
    monkeypatch.setattr(
        research_module,
        "fetch_source_content",
        lambda *args, **kwargs: SourceContent(text=evidence, content_type="pdf_text"),
    )

    extracted = workspace.research.extract([work], model="custom:cross-domain-extractor")

    assert llm.calls == 1
    assert extracted.items[0].principles == []
    assert extracted.items[0].ideas
    assert extracted.items[0].takeaways


def test_abstract_fallback_reports_actual_characters(tmp_path: Path, monkeypatch: Any) -> None:
    abstract = "A domain-neutral abstract describing a controlled physical experiment."
    grounded = {
        "ideas": [{"title": "Controlled experiment", "core_idea": abstract}],
        "principles": [{"name": "Physical control", "argument": abstract}],
        "takeaways": [{"title": "Measure the experiment", "message": abstract}],
        "baselines": [],
        "benchmarks": [],
        "result_facts": [],
    }
    llm = ExtractionLLM([grounded])
    workspace = pc.Workspace(tmp_path, llm=llm)
    work = pc.WorkItem(id="ABSTRACT", title="A physical experiment", abstract=abstract)
    monkeypatch.setattr(
        research_module,
        "fetch_source_content",
        lambda *args, **kwargs: SourceContent(text="", content_type="unknown"),
    )

    extracted = workspace.research.extract([work], model="custom:cross-domain-extractor")

    assert extracted.items[0].source_content_type == "abstract"
    assert extracted.items[0].source_excerpt_chars == len(abstract)
    assert "metadata abstract" in " ".join(extracted.items[0].extraction_warnings)
