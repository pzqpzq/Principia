from __future__ import annotations

import json
import re
import sqlite3
import tempfile
import threading
import urllib.request
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from pypdf import PdfReader

import principia.engine as engine_module
from principia.arxiv import build_arxiv_queries, fallback_seed_work
from principia.config import Settings, get_settings
from principia.engine import PrincipiaEngine
from principia.llm_client import LLMClient
from principia.models import BaselineRecord, BenchmarkRecord, FieldProfile, ResultRecord, WorkFact, to_dict
from principia.server import make_handler
from principia.storage import Store
from principia.utils import enrich_query, safe_json_loads, stable_id


SPARSE_VIEW_QUERY = "Please design a method for 稀疏数据三维重建（即在有限视角下进行三维重建）任务"
TIMESFM_RUL_QUERY = (
    "把TimesFM作为时序特征抽取器，然后融合多个时序特征，"
    "接一个transformer做跨传感器特征融合，最后接一个回归头做剩余使用寿命预测"
)
SYMBOLIC_COMPACTNESS_MAS_QUERY = (
    "I would like use symbolic compactness as an intrinsic rewards for an MAS in scientific discovery"
)
MACHINE_DIALECT_MAS_QUERY = (
    "Please design an MAS framework where LLMs are interacting machine dialects like social interaction "
    "to improve the reasoning accuracy and reducing the tokens completion and cost"
)
VISION_CLIP_TTT_QUERY = (
    "实验资源受限情况下（4-8块4090），视觉模型和clip在few shot learning任务上的新策略。"
    "重点考虑test time training，可以参考cvpr2026的vit^3这篇文章。"
    "要求明确测评benchmark，对比的baseline，使用的数据集，预计的实验代价和创新点（或者贡献）"
)


class NoLLM:
    costs = type("Costs", (), {"calls": []})()

    def available(self) -> bool:
        return False

    def model_label(self, mode: str = "auto", complexity: float = 0.4) -> str:
        return f"offline:{mode}"


class FakeV2LLM:
    costs = type("Costs", (), {"calls": []})()
    settings = type("Settings", (), {"api_key": "fake", "openai_api_key": "fake"})()

    def available(self) -> bool:
        return True

    def model_label(self, mode: str = "auto", complexity: float = 0.4) -> str:
        return f"fake:{mode}"

    def resolve_model(self, complexity: float = 0.4, mode: str = "auto") -> dict[str, str]:
        return {"provider": "fake", "model": mode or "fake-model", "base_url": "", "api_key": "fake"}

    def objective_source(self, work: dict) -> str:
        text = work.get("abstract") or work.get("full_text_excerpt") or "a method, benchmark conditions, routing signals, adaptation behavior, and evaluation results"
        return (
            text.replace("We introduce", "The source work introduces")
            .replace("We show that", "The reported results indicate that")
            .replace("we introduce", "the source work introduces")
            .replace("we show that", "the reported results indicate that")
        )

    def chat_json(self, system: str, user: str, **kwargs):
        if "extract nontrivial research structures" in system:
            match = re.search(r"Works:\s*(\[.*\])", user, flags=re.S)
            works = json.loads(match.group(1)) if match else [{"work_id": work_id, "title": work_id, "abstract": ""} for work_id in re.findall(r'"work_id":\s*"([^"]+)"', user)]
            return {
                "works": [
                    {
                        "work_id": work.get("work_id"),
                        "existed_ideas": [
                            {
                                "title": "Source-conditioned mechanism routing",
                                "core_idea": f"{work.get('title') or 'The source work'} uses source-described routing or adaptation signals to decide when the active mechanism should change under the evaluated task conditions.",
                                "idea_text": f"{work.get('title') or 'The source work'} uses source-described routing or adaptation signals to decide when the active mechanism should change under the evaluated task conditions.",
                                "mechanism": f"The method context in {work.get('title') or 'the source work'} connects the source-described mechanism to the task and benchmark conditions reported in the work. The extracted mechanism treats routing or adaptation as a conditional operation that should be activated only when the work's own evidence indicates that a uniform default method is insufficient.",
                                "discussion": "The value of this idea is that mechanism use becomes a controlled decision rather than an unconditional architectural addition. It is most useful when source evidence contains both a proposed mechanism and an evaluation setting where the cost or reliability of activating that mechanism can be measured.",
                                "evidence": f"The source metadata for {work.get('title') or 'the work'} discusses {self.objective_source(work)}.",
                            }
                        ],
                        "principles": [
                            {
                                "name": "Evidence-gated mechanism transfer",
                                "argument": "When a method is evaluated under distribution shift or benchmark-specific pressure, adaptation should be gated by the source-described diagnostic signal rather than applied uniformly.",
                                "abstract_signature": "When a method is evaluated under distribution shift or benchmark-specific pressure, adaptation should be gated by the source-described diagnostic signal rather than applied uniformly.",
                                "boundary_conditions": ["tasks with explicit source evidence for routing or adaptation"],
                                "evidence": f"The source work {work.get('title') or ''} discusses {self.objective_source(work)}, which supports a gated transfer rule.",
                                "discussion": "This principle helps separate useful adaptation from unnecessary intervention. It can guide systems that must decide when to spend extra computation or alter a representation, but it requires a diagnostic signal that is actually supported by the source work.",
                            }
                        ],
                        "takeaway_messages": [
                            {
                                "title": "Mechanism use needs source-supported conditions",
                                "main_results": "Under the evaluated benchmark setting, conditional routing or adaptation is most defensible when the source work identifies the condition that makes a uniform method unreliable.",
                                "message_text": "Under the evaluated benchmark setting, conditional routing or adaptation is most defensible when the source work identifies the condition that makes a uniform method unreliable.",
                                "condition": "The result applies when the source work reports a method, task condition, and benchmark or evaluation setting that exposes the relevant failure pressure. It is most relevant when the system can observe a diagnostic signal before activating the mechanism.",
                                "finding": "source-supported conditions matter more than unconditional mechanism use",
                                "actionable_lesson": "Measure whether the diagnostic condition exists before spending extra compute or changing the active method.",
                                "discussion": "The takeaway is useful because it turns mechanism activation into an empirical control problem. It should not be generalized to settings where the source work provides no condition, benchmark signal, or diagnostic evidence.",
                                "evidence": f"The source work {work.get('title') or ''} provides evidence through its discussion of {self.objective_source(work)}.",
                            }
                        ],
                        "benchmarks": [],
                        "baselines": [],
                    }
                    for work in works
                ]
            }
        if "generate one rigorous research idea" in system:
            return {
                "title": "Trace-Conditioned Logical Pattern Router",
                "one_sentence_thesis": "Extract reusable logical patterns from exemplars only after a compatibility probe predicts accuracy gain per token.",
                "novelty_claim": "The idea treats exemplar-derived logic as a routed, measurable inference-time resource rather than a fixed prompt decoration.",
                "mechanistic_design": ["Probe exemplar-target compatibility.", "Extract a compact logical pattern.", "Route pattern use by expected accuracy-per-token gain."],
                "why_it_might_work": ["It avoids spending tokens on incompatible exemplars.", "It creates a direct ablation for pattern transfer."],
                "validation_protocol": ["Compare direct CoT, self-consistency, and pattern-routed inference on GSM8K, MATH, and FOLIO."],
                "relevant_baselines": ["Chain-of-Thought", "self-consistency", "least-to-most prompting"],
                "metrics": ["accuracy", "tokens per correct answer", "accuracy-token frontier"],
                "risks": ["The compatibility probe may cost more tokens than it saves."],
                "derived_principles": ["Inference-time pattern transfer should be gated by expected accuracy per token."],
                "related_existed_ideas": [
                    {
                        "id": "XI-PRIOR",
                        "mechanistic_similarity": "Uncertainty is the shared control signal: each method delays adaptation until a diagnostic says the default path is unreliable.",
                        "essential_difference": "Logical-pattern transfer changes the object being routed from visual prompt parameters to reusable reasoning structure extracted from exemplars.",
                        "potential_advantage": "Accuracy per token becomes measurable at the decision point, so the method can refuse expensive exemplar logic when the compatibility probe predicts poor transfer.",
                        "potential_weakness": "A bad compatibility probe can suppress the only exemplar that contains the latent rule, whereas visual prompt routing usually keeps the representation space fixed.",
                    }
                ],
            }
        if "compare a generated research idea" in system:
            ids = re.findall(r'"id":\s*"([^"]+)"', user)
            return {
                "rows": [
                    {
                        "id": item_id,
                        "mechanistic_similarity": "Routing is the common causal handle: both ideas avoid applying every available mechanism uniformly and instead condition intervention on a diagnostic state.",
                        "essential_difference": "Compatibility scoring moves the decision boundary to exemplar-derived logical rules, while the prior evidence routes adaptation modules around prediction uncertainty.",
                        "potential_advantage": "Token expenditure becomes an explicit optimization target because pattern extraction is invoked only when the prior evidence suggests the rule can transfer.",
                        "potential_weakness": "Adversarial or mixed-rule exemplars can fool the compatibility scorer before reasoning begins, leaving no later module to recover the missing logical step.",
                    }
                    for item_id in ids
                ]
            }
        return {}


class PrincipiaTests(unittest.TestCase):
    def make_store(self) -> Store:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        return Store(Path(tmpdir.name) / "principia-test.sqlite")

    def test_chinese_sparse_view_query_expands_to_reconstruction_terms(self) -> None:
        expanded = enrich_query(SPARSE_VIEW_QUERY).lower()
        self.assertIn("sparse-view 3d reconstruction", expanded)
        self.assertIn("few-view 3d reconstruction", expanded)
        self.assertIn("multi view stereo", expanded)

        queries = build_arxiv_queries(SPARSE_VIEW_QUERY)
        self.assertEqual(queries[0], 'all:"sparse view" AND all:"3d reconstruction"')
        self.assertIn('all:"3d gaussian splatting" AND all:"sparse view"', queries)

        hyphenated_seeds = fallback_seed_work("sparse-view 3D reconstruction")
        self.assertGreaterEqual(len(hyphenated_seeds), 3)

    def test_chinese_timesfm_query_expands_to_rul_sensor_terms(self) -> None:
        expanded = enrich_query(TIMESFM_RUL_QUERY).lower()

        self.assertIn("time series foundation model", expanded)
        self.assertIn("multisensor fusion", expanded)
        self.assertIn("remaining useful life prediction", expanded)

    def test_vision_clip_ttt_query_expands_to_relevant_terms(self) -> None:
        expanded = enrich_query(VISION_CLIP_TTT_QUERY).lower()
        queries = build_arxiv_queries(VISION_CLIP_TTT_QUERY)

        self.assertIn("few-shot learning", expanded)
        self.assertIn("test-time training", expanded)
        self.assertIn("vision-language model", expanded)
        self.assertIn('all:"test-time training" AND all:CLIP', queries)
        self.assertIn('all:"few-shot learning" AND all:CLIP', queries)

    def test_mas_queries_expand_to_agent_symbolic_and_dialect_terms(self) -> None:
        symbolic = enrich_query(SYMBOLIC_COMPACTNESS_MAS_QUERY).lower()
        dialect = enrich_query(MACHINE_DIALECT_MAS_QUERY).lower()

        self.assertIn("multi-agent systems", symbolic)
        self.assertIn("automated scientific discovery", symbolic)
        self.assertIn("minimum description length", symbolic)
        self.assertIn("agent communication protocol", dialect)
        self.assertIn("token efficient reasoning", dialect)

        queries = build_arxiv_queries(SYMBOLIC_COMPACTNESS_MAS_QUERY)
        self.assertIn('all:"multi-agent" AND all:"large language model"', queries)
        self.assertIn('all:"symbolic reasoning" AND all:"scientific discovery"', queries)
        self.assertNotIn("all:compactness", queries[:6])

    def test_principle_merge_upgrades_legacy_sparse_record(self) -> None:
        store = self.make_store()
        legacy = {
            "principle_id": "P-LEGACY",
            "name": "Sparse View Prior principle",
            "mechanism": "Use priors to stabilize sparse-view 3D reconstruction.",
            "source_works": ["W-OLD"],
            "validation_level": "L0",
            "confidence_score": 0.2,
        }
        store.upsert("principles", legacy, "principle_id")

        rich = {
            **legacy,
            "source_works": ["W-NEW"],
            "principle_type": "geometry_prior_under_sparse_observation",
            "abstraction_level": "mechanism",
            "abstract_signature": "recover latent 3D structure from scarce, ambiguous views",
            "problem_pressure": "Finite-view settings underconstrain geometry.",
            "objective": "Improve held-out novel-view quality without hallucinating geometry.",
            "scarce_resources": ["input views", "cross-view overlap"],
            "assumptions": ["Geometry priors can compensate for missing views."],
            "constraints": ["No dense-view supervision."],
            "invariants": ["Held-out views must remain cross-view consistent."],
            "tradeoffs": ["prior strength vs hallucination risk"],
            "failure_modes": ["Priors hallucinate unseen surfaces."],
            "feedback_loop": ["train on sparse views", "render held-out diagnostics"],
            "transfer_hooks": ["gate priors by region uncertainty"],
            "validation_notes": ["Run 3/6/9-view splits."],
            "domain_tags": ["sparse-view", "3d-reconstruction"],
            "relation_hints": ["shares_sparse_observation_pressure"],
            "confidence_score": 0.55,
        }

        [saved] = store.merge_principles([rich])
        self.assertEqual(saved["principle_id"], "P-LEGACY")
        self.assertEqual(saved["abstract_signature"], rich["abstract_signature"])
        self.assertEqual(saved["source_works"], ["W-OLD", "W-NEW"])
        self.assertIn("3d-reconstruction", saved["domain_tags"])
        self.assertEqual(saved["confidence_score"], 0.55)

        hits = store.search_principles(SPARSE_VIEW_QUERY, top_k=3)
        self.assertEqual(hits[0]["principle_id"], "P-LEGACY")
        self.assertIn("feedback_loop", hits[0])

    def test_offline_sparse_view_generation_returns_rich_principles_and_ideas(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)

        result = engine.generate_ideas(SPARSE_VIEW_QUERY, offline=True, max_works=3, max_ideas=3)

        self.assertEqual(len(result["source_works"]), 3)
        self.assertGreater(len(result["principles"]), len(result["source_works"]))
        self.assertGreaterEqual(len(result["principle_relations"]), 1)
        self.assertEqual(len(result["ideas"]), 3)
        principle = result["principles"][0]
        self.assertEqual(principle["principle_type"], "geometry_prior_under_sparse_observation")
        self.assertIn("3d-reconstruction", principle["domain_tags"])
        self.assertTrue(principle["abstract_signature"])
        self.assertGreaterEqual(len(principle["scarce_resources"]), 3)
        self.assertGreaterEqual(len(principle["feedback_loop"]), 3)

        titles = [idea["title"] for idea in result["ideas"]]
        self.assertIn("Uncertainty-Gated Prior Injection for Sparse-View 3D Reconstruction", titles)
        for idea in result["ideas"]:
            self.assertTrue(idea["insight"])
            self.assertGreaterEqual(len(idea["mechanism_design"]), 3)
            self.assertGreaterEqual(len(idea["validation_protocol"]), 3)
            self.assertIn("testability", idea["ranking_scores"])
            estimate = result["estimates"][0]
            self.assertIn("cheapest_falsification", estimate)
            self.assertEqual(estimate["estimator_version"], "demo-v0.2")

        counts = store.counts()
        self.assertGreaterEqual(counts["principle_relations"], 1)

    def test_local_mode_uses_existing_pool_without_new_work_mining(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)

        with self.assertRaisesRegex(RuntimeError, "Local mode"):
            engine.generate_ideas(SPARSE_VIEW_QUERY, source_mode="local", offline=True, max_ideas=1)

        online = engine.generate_ideas(SPARSE_VIEW_QUERY, source_mode="online", offline=True, paper_count=3, max_ideas=2)
        counts_after_online = store.counts()
        local = engine.generate_ideas(SPARSE_VIEW_QUERY, source_mode="local", offline=True, max_ideas=2)
        counts_after_local = store.counts()

        self.assertTrue(local["from_cache"])
        self.assertEqual(counts_after_online["source_works"], counts_after_local["source_works"])
        self.assertEqual(counts_after_online["principles"], counts_after_local["principles"])
        self.assertGreaterEqual(len(local["principles"]), len(online["source_works"]))

    def test_cleanup_keeps_highlighted_and_high_usage_records(self) -> None:
        store = self.make_store()
        for idx in range(4):
            store.upsert(
                "source_works",
                {
                    "work_id": f"W-{idx}",
                    "title": f"Work {idx}",
                    "authors": [],
                    "year": None,
                    "venue_or_source": "local",
                    "url_or_doi": "",
                    "source_type": "note",
                    "validation_level": "L0",
                    "abstract": f"sparse view reconstruction note {idx}",
                    "usage_count": idx,
                    "highlighted": idx == 0,
                },
                "work_id",
            )

        result = store.prune_least_used(max_works=2, max_principles=1000, max_ideas=100)
        remaining = {item["work_id"] for item in store.list_items("source_works", limit=10)}

        self.assertEqual(result["deleted"]["source_works"], 2)
        self.assertIn("W-0", remaining)
        self.assertIn("W-3", remaining)

    def test_model_router_exposes_extended_siliconflow_aliases(self) -> None:
        client = LLMClient(settings=get_settings())

        self.assertIn("Kimi-K2.6", client.choose_model(mode="kimi"))
        self.assertIn("DeepSeek-V4-Pro", client.choose_model(mode="deepseek_pro"))
        self.assertIn("DeepSeek-R1", client.choose_model(mode="deepseek_r1"))
        self.assertIn("Qwen3.6-27B", client.choose_model(mode="qwen_27b"))
        self.assertIn("Qwen3.6-35B-A3B", client.choose_model(mode="qwen_35b"))
        self.assertIn("Qwen3.5-122B-A10B", client.choose_model(mode="qwen_122b"))
        self.assertIn("Qwen3.5-397B-A17B", client.choose_model(mode="qwen_397b"))
        self.assertIn("GLM-5.1", client.choose_model(mode="glm"))
        self.assertEqual(client.choose_model(mode="openai_gpt5_pro"), "gpt-5-pro")
        self.assertEqual(client.choose_model(mode="openai_gpt52_pro"), "gpt-5.2-pro")
        self.assertEqual(client.choose_model(mode="openai_gpt55"), "gpt-5.5")
        self.assertEqual(client.choose_model(mode="openai_gpt55_pro_20260423"), "gpt-5.5-pro-2026-04-23")
        self.assertEqual(client.choose_model(mode="model:custom/ExactModel"), "custom/ExactModel")

    def test_llm_json_repair_preserves_provider_content_without_template_fallback(self) -> None:
        class RepairingClient(LLMClient):
            def __init__(self):
                self.calls = []

            def resolve_model(self, complexity: float = 0.4, mode: str = "auto") -> dict[str, str]:
                return {"provider": "siliconflow", "model": "fake-model", "base_url": "", "api_key": "fake"}

            def chat_text(self, system: str, user: str, **kwargs):
                self.calls.append({"system": system, "user": user, **kwargs})
                if len(self.calls) == 1:
                    return "{'ok': True, 'items': ['alpha']}"
                return '{"ok": true, "items": ["alpha"]}'

        client = RepairingClient()
        result = client.chat_json("Return JSON.", "Return an object with ok and items.", mode="efficient")

        self.assertEqual(result, {"ok": True, "items": ["alpha"]})
        self.assertEqual(len(client.calls), 2)
        self.assertIn("Malformed provider response", client.calls[1]["user"])
        self.assertIn("Do not add scientific content", client.calls[1]["system"])

    def test_safe_json_loads_repairs_unquoted_keys_without_llm_templates(self) -> None:
        payload = safe_json_loads(
            """
            Here is the JSON:
            {
              title: "Logical Pattern Controller",
              novelty_claim: "Gate pattern extraction by expected value.",
              method_variants: ["classifier gate", "two-signal gate",],
            }
            """
        )

        self.assertEqual(payload["title"], "Logical Pattern Controller")
        self.assertEqual(payload["method_variants"], ["classifier gate", "two-signal gate"])

    def test_qwen_122b_uses_slow_timeout_floor_for_large_generation(self) -> None:
        settings = Settings(
            api_key="fake",
            base_url="https://api.siliconflow.cn/v1",
            openai_api_key="",
            openai_base_url="https://api.openai.com/v1",
            efficient_model="Qwen/Qwen3.6-27B",
            strong_model="deepseek-ai/DeepSeek-V3",
            model_aliases={"qwen_122b": "Qwen/Qwen3.5-122B-A10B", "efficient": "Qwen/Qwen3.6-27B"},
            cost_limit_cny=1000,
            request_timeout=45,
            slow_request_timeout=420,
            ssl_verify=True,
        )
        client = LLMClient(settings=settings)

        self.assertEqual(client._request_timeout(client.resolve_model(mode="qwen_122b"), 3200), 420)
        self.assertEqual(client._request_timeout(client.resolve_model(mode="efficient"), 64), 45)

    def test_timeout_message_is_not_extraction_specific_for_generation(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store, llm=NoLLM())

        message = engine._friendly_llm_error(RuntimeError("LLM request timed out after 420s waiting for siliconflow:Qwen/Qwen3.5-122B-A10B."))

        self.assertIn("did not finish after 420 seconds", message)
        self.assertIn("did not generate a template fallback", message)
        self.assertNotIn("extraction latency", message)

    def test_model_specific_views_do_not_fall_back_to_other_models(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)

        glm = engine.generate_ideas(
            SPARSE_VIEW_QUERY,
            source_mode="online",
            offline=True,
            paper_count=2,
            max_ideas=1,
            model_mode="glm",
        )
        deepseek = engine.generate_ideas(
            SPARSE_VIEW_QUERY,
            source_mode="online",
            offline=True,
            paper_count=2,
            max_ideas=1,
            model_mode="deepseek_pro",
        )

        self.assertEqual({item["model_mode"] for item in glm["principles"]}, {"glm"})
        self.assertEqual({item["model_mode"] for item in deepseek["principles"]}, {"deepseek_pro"})
        self.assertNotEqual(glm["ideas"][0]["idea_id"], deepseek["ideas"][0]["idea_id"])
        self.assertNotEqual(glm["ideas"][0]["insight"], deepseek["ideas"][0]["insight"])
        self.assertEqual(engine._filter_model_version(glm["principles"], "deepseek_pro"), [])

    def test_timesfm_gpt55_ideas_have_clean_unique_titles_and_fact_lineage(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)

        result = engine.generate_ideas(
            TIMESFM_RUL_QUERY,
            source_mode="online",
            offline=True,
            paper_count=5,
            max_ideas=8,
            model_mode="openai_gpt55",
        )
        titles = [idea["title"] for idea in result["ideas"]]

        self.assertEqual(len(titles), 8)
        self.assertEqual(len(set(titles)), 8)
        self.assertFalse(any(title.startswith("GPT-5.5:") for title in titles))
        self.assertTrue(any("TimesFM" in title or "RUL" in title for title in titles))
        self.assertEqual(result["curation"]["brief"]["curator"], "heuristic")
        self.assertIn("bottleneck", result["curation"]["brief"]["core_tension"])
        self.assertTrue(result["curation"]["insights"])
        self.assertTrue(result["curation"]["novelty"])
        for idea in result["ideas"]:
            self.assertTrue(idea["source_insights"])
            self.assertTrue(idea["source_novelty"])
            self.assertIn("composition_trace", idea)
            self.assertTrue(idea["conceptual_takeaway"])
            self.assertTrue(idea["sharp_reframing"])
        self.assertTrue(any(edge["label"] == "inspires" for edge in result["graph"]["edges"]))

    def test_timesfm_chinese_variants_do_not_wrap_english_substance(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)

        result = engine.generate_ideas(
            TIMESFM_RUL_QUERY,
            source_mode="online",
            offline=True,
            language="zh",
            paper_count=5,
            max_ideas=3,
            model_mode="openai_gpt55",
        )
        zh_payload = json.dumps(
            {
                "works": [work["language_variants"]["zh"] for work in result["source_works"]],
                "principles": [principle["language_variants"]["zh"] for principle in result["principles"]],
                "ideas": [idea["language_variants"]["zh"] for idea in result["ideas"]],
            },
            ensure_ascii=False,
        ).lower()

        forbidden = [
            "allocate scarce resources",
            "push toward frontier-level",
            "cheap falsification path",
            "this work uses",
            "this principle",
            "this idea",
        ]
        self.assertFalse(any(phrase in zh_payload for phrase in forbidden))
        self.assertIn("跨传感器", zh_payload)
        self.assertIn("退化", zh_payload)
        self.assertIn("rul", zh_payload)

    def test_stale_mixed_chinese_principle_variant_is_repaired(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)
        stale = {
            "principle_id": "P-STALE-ZH",
            "name": "RUL resource allocation principle",
            "principle_type": "resource_allocation",
            "abstraction_level": "mechanism",
            "abstract_signature": "allocate scarce resources under uncertainty and validate with a cheap falsification path",
            "mechanism": "Use TimesFM features with cross-sensor fusion for RUL.",
            "problem_pressure": "RUL sensor data are noisy.",
            "objective": "Improve remaining useful life prediction.",
            "scarce_resources": ["labeled RUL data"],
            "assumptions": [],
            "constraints": ["limited labels"],
            "invariants": ["stable degradation trend"],
            "tradeoffs": ["adaptation vs overfitting"],
            "failure_modes": ["sensor drift"],
            "feedback_loop": [],
            "transfer_hooks": ["compare frozen TimesFM and fused variants"],
            "source_works": [],
            "validation_level": "L1",
            "confidence_score": 0.4,
            "empirical_claims": [],
            "evidence_spans": [],
            "validation_notes": ["run RUL MAE"],
            "domain_tags": ["time-series", "rul"],
            "relation_hints": [],
            "language_variants": {
                "zh": {
                    "abstract_signature": "这个 principle 可以概括为：allocate scarce resources under uncertainty and validate with a cheap falsification path。它不是对单篇论文的复述。",
                    "mechanism": "这个 principle 的机制是：Use TimesFM features with cross-sensor fusion.",
                }
            },
        }

        repaired = engine.repair_language_variants(stale)
        zh_text = json.dumps(repaired["language_variants"]["zh"], ensure_ascii=False).lower()

        self.assertNotIn("allocate scarce resources", zh_text)
        self.assertNotIn("cheap falsification path", zh_text)
        self.assertIn("跨传感器", zh_text)

    def test_vision_clip_ttt_generation_uses_domain_specific_diverse_core(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)

        result = engine.generate_ideas(
            VISION_CLIP_TTT_QUERY,
            source_mode="online",
            offline=True,
            language="zh",
            paper_count=8,
            max_ideas=8,
            model_mode="openai_gpt55",
        )
        titles = [idea["title"] for idea in result["ideas"]]
        joined = json.dumps(result["ideas"], ensure_ascii=False).lower()
        zh_payload = json.dumps([idea["language_variants"]["zh"] for idea in result["ideas"]], ensure_ascii=False).lower()
        generic_terms = ["falsification-gated", "evaluator-first", "staged mechanism"]

        self.assertEqual(len(titles), 8)
        self.assertEqual(len(set(titles)), 8)
        self.assertFalse(any(title.lower().startswith(("gpt-5.5:", "gpt5.5:", "openai gpt")) for title in titles))
        self.assertFalse(any(term in joined for term in generic_terms))
        self.assertTrue(any("CLIP" in title or "TTT" in title or "Few-Shot" in title for title in titles))
        self.assertIn("imagenet", joined)
        self.assertIn("tip-adapter", joined)
        self.assertIn("4090", joined)
        self.assertIn("少样本", zh_payload)
        self.assertIn("测试时", zh_payload)
        self.assertFalse(any(term in zh_payload for term in generic_terms))

    def test_clean_idea_title_removes_model_prefixes(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)

        self.assertEqual(
            engine._clean_idea_title("GPT-5.5: Falsifiable But Clean Title", 0),
            "Falsifiable But Clean Title",
        )
        self.assertEqual(
            engine._clean_idea_title("OpenAI GPT5.5 - Cost-Aware CLIP Adapter", 0),
            "Cost-Aware CLIP Adapter",
        )

    def test_symbolic_mas_generation_rejects_timesfm_and_math_compactness_leakage(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)
        goal = engine.formalize_goal(SYMBOLIC_COMPACTNESS_MAS_QUERY, offline=True)

        self.assertFalse(
            engine._is_domain_compatible(
                goal,
                {
                    "title": "Reliability-Gated TimesFM Sensor Fusion for RUL",
                    "abstract": "TimesFM features for remaining useful life prediction with cross-sensor degradation modeling.",
                },
            )
        )
        self.assertFalse(
            engine._is_domain_compatible(
                goal,
                {
                    "title": "Obstructions for Compactness of Hankel Operators",
                    "abstract": "Compactness multipliers on Hilbert spaces and semigroup operator spectra.",
                },
            )
        )

        result = engine.generate_ideas(
            SYMBOLIC_COMPACTNESS_MAS_QUERY,
            source_mode="online",
            offline=True,
            paper_count=8,
            max_ideas=8,
            model_mode="openai_gpt55",
        )
        text = "\n".join(
            [
                *(work.get("title", "") for work in result["source_works"]),
                *(principle.get("name", "") for principle in result["principles"]),
                *(idea.get("title", "") for idea in result["ideas"]),
            ]
        ).lower()
        titles = [idea["title"] for idea in result["ideas"]]

        self.assertNotIn("timesfm", text)
        self.assertNotIn("hankel", text)
        self.assertEqual(len(titles), 8)
        self.assertEqual(len(set(titles)), 8)
        self.assertEqual(titles[0], "Symbolic Compactness Reward Market")

    def test_machine_dialect_mas_fallback_uses_distinct_dialect_concepts(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)

        result = engine.generate_ideas(
            MACHINE_DIALECT_MAS_QUERY,
            source_mode="online",
            offline=True,
            paper_count=8,
            max_ideas=8,
            model_mode="openai_gpt55",
        )
        titles = [idea["title"] for idea in result["ideas"]]
        generic_terms = ["falsification-gated", "evaluator-first", "staged mechanism"]

        self.assertEqual(len(titles), 8)
        self.assertEqual(len(set(titles)), 8)
        self.assertEqual(titles[0], "Dialect Contract Swarm")
        self.assertTrue(any("Dialect" in title for title in titles))
        self.assertFalse(any(term in title.lower() for title in titles for term in generic_terms))

    def test_cached_work_pool_is_remined_for_new_model_alias(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)
        engine.generate_ideas(
            SPARSE_VIEW_QUERY,
            source_mode="online",
            offline=True,
            paper_count=3,
            max_ideas=1,
            model_mode="deepseek_pro",
        )

        glm = engine.generate_ideas(
            SPARSE_VIEW_QUERY,
            source_mode="online",
            offline=True,
            paper_count=3,
            max_ideas=1,
            model_mode="glm",
        )

        self.assertTrue(glm["principles"])
        self.assertEqual({item["model_mode"] for item in glm["principles"]}, {"glm"})
        self.assertTrue(glm["ideas"][0]["source_principles"])

    def test_force_refresh_remines_current_model_even_when_work_is_current(self) -> None:
        store = self.make_store()
        work = {
            "work_id": "W-CURRENT",
            "title": "Current sparse-view work",
            "authors": [],
            "year": 2026,
            "venue_or_source": "local",
            "url_or_doi": "",
            "source_type": "note",
            "validation_level": "L1",
            "abstract": "sparse-view 3D reconstruction with uncertainty-gated priors",
            "source_updated_at": "2026-01-01T00:00:00Z",
        }
        store.upsert("source_works", work, "work_id")
        store.merge_principles(
            [
                {
                    "principle_id": "P-CURRENT-GLM",
                    "name": "Current sparse-view principle",
                    "principle_type": "geometry_prior_under_sparse_observation",
                    "abstraction_level": "mechanism",
                    "abstract_signature": "recover latent 3D structure from scarce views",
                    "mechanism": "Use uncertainty-gated priors for sparse-view 3D reconstruction.",
                    "problem_pressure": "Sparse views underconstrain geometry.",
                    "objective": "Improve held-out view quality.",
                    "scarce_resources": ["views", "overlap", "pose certainty"],
                    "assumptions": ["Priors help sparse views."],
                    "constraints": ["few-view split"],
                    "invariants": ["cross-view consistency"],
                    "tradeoffs": ["prior strength vs hallucination risk"],
                    "failure_modes": ["hallucinated geometry"],
                    "feedback_loop": ["train", "render", "measure"],
                    "transfer_hooks": ["gate prior by uncertainty"],
                    "source_works": ["W-CURRENT"],
                    "validation_level": "L1",
                    "confidence_score": 0.5,
                    "validation_notes": ["Run held-out views."],
                    "domain_tags": ["sparse-view", "3d-reconstruction"],
                    "relation_hints": ["shares_sparse_observation_pressure"],
                    "model_mode": "glm",
                    "model_name": "offline:glm",
                }
            ]
        )
        calls = []

        class RefreshEngine(PrincipiaEngine):
            def _collect_works(self, goal, max_works, offline, **kwargs):  # type: ignore[override]
                return [work]

            def _mine_principles(self, goal, works, *, offline, model_mode):  # type: ignore[override]
                calls.append(model_mode)
                return super()._mine_principles(goal, works, offline=offline, model_mode=model_mode)

        refresh_engine = RefreshEngine(store=store)
        second = refresh_engine.ingest_principles(
            SPARSE_VIEW_QUERY,
            max_works=1,
            offline=True,
            model_mode="glm",
            refresh_existing=True,
            force_refresh=True,
        )

        self.assertTrue(second["principles"])
        self.assertEqual(calls, ["glm"])

    def test_idea_draft_queries_are_formalized_as_drafts(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)
        draft = (
            "My idea draft: use uncertainty-gated diffusion priors to generate pseudo-views, "
            "then validate sparse-view 3D reconstruction with pose-stratified held-out views."
        )

        goal = engine.formalize_goal(draft, offline=True)

        self.assertEqual(goal["query_kind"], "idea_draft")
        self.assertIn("uncertainty-gated", goal["idea_draft"])

    def test_work_enrichment_adds_principle_insight_and_novelty_fields(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)
        result = engine.ingest_principles(SPARSE_VIEW_QUERY, offline=True, max_works=1, bypass_cache=True)
        work = result["source_works"][0]

        self.assertTrue(work["work_principles"])
        self.assertTrue(work["work_insights"])
        self.assertTrue(work["work_novelty"])
        self.assertTrue(result["principles"][0]["language_variants"]["zh"]["mechanism"])
        self.assertIn("offline:auto", result["principles"][0]["model_name"])

    def test_chinese_translation_pass_populates_real_language_variants(self) -> None:
        store = self.make_store()

        class FakeTranslator:
            costs = type("Costs", (), {"calls": []})()
            settings = type("Settings", (), {"api_key": "fake-siliconflow", "openai_api_key": ""})()

            def __init__(self) -> None:
                self.calls: list[dict] = []

            def available(self) -> bool:
                return True

            def model_label(self, mode: str = "auto", complexity: float = 0.4) -> str:
                return f"fake:{mode}"

            def chat_json(self, system: str, user: str, **kwargs):
                self.calls.append({"system": system, "user": user, **kwargs})
                return {
                    "works": [
                        {
                            "work_id": "W-T",
                            "zh": {
                                "title": "TimesFM Sensor Paper",
                                "abstract": "这篇工作讨论如何把 TimesFM 用作时序特征抽取器。",
                                "work_principles": ["把通用时序表征与任务约束分离。"],
                                "work_insights": ["真正的误差常来自跨传感器漂移，而不是单变量预测。"],
                                "work_novelty": ["创新点在于把基础时序模型接入 RUL 融合流程。"],
                            },
                        }
                    ],
                    "principles": [
                        {
                            "principle_id": "P-T",
                            "zh": {
                                "name": "表征与校正分离",
                                "abstract_signature": "先获得稳定表征，再学习任务残差。",
                                "mechanism": "把 TimesFM 作为冻结表征层，把跨传感器校正留给轻量模块。",
                                "problem_pressure": "端到端堆叠会掩盖误差来源。",
                                "objective": "让方法贡献更容易被消融验证。",
                                "transfer_hooks": ["先测基础表征，再测融合层增益。"],
                                "validation_notes": ["比较冻结表征、融合层和完整模型。"],
                                "scarce_resources": ["标注寿命数据"],
                                "constraints": ["避免额外大规模训练"],
                                "invariants": ["校正层不能破坏基础趋势"],
                                "tradeoffs": ["泛化性与任务适配之间的权衡"],
                                "failure_modes": ["冻结表征可能缺少退化信号"],
                            },
                        }
                    ],
                    "ideas": [
                        {
                            "idea_id": "I-T",
                            "zh": {
                                "title": "残差校正型 TimesFM RUL 模型",
                                "one_sentence_thesis": "先让 TimesFM 给出基础寿命估计，再让融合模块只学习残差。",
                                "conceptual_takeaway": "不要把所有能力都塞进一个 Transformer；先区分基础趋势和跨传感器误差。",
                                "sharp_reframing": "RUL 预测可以被重写为基础预测加残差解释。",
                                "insight": "残差比最终标签更能暴露融合层的真实价值。",
                                "mechanism_design": ["冻结 TimesFM。", "训练跨传感器残差模块。"],
                                "why_it_might_work": ["它让贡献来源更清楚。"],
                                "validation_protocol": ["比较直接回归与残差校正。"],
                                "source_insights": ["TimesFM Sensor Paper：误差来自跨传感器漂移。"],
                                "source_novelty": ["TimesFM Sensor Paper：基础模型接入 RUL 融合流程。"],
                                "metrics": ["RUL MAE"],
                                "failure_modes": ["残差信号可能过弱。"],
                                "baselines": ["TimesFM + MLP"],
                            },
                        }
                    ],
                }

        fake = FakeTranslator()
        engine = PrincipiaEngine(store=store, llm=fake)
        goal = engine.formalize_goal(TIMESFM_RUL_QUERY, offline=True)
        work = {
            "work_id": "W-T",
            "title": "TimesFM Sensor Paper",
            "authors": [],
            "year": 2026,
            "venue_or_source": "local",
            "url_or_doi": "",
            "source_type": "note",
            "validation_level": "L1",
            "abstract": "This work uses TimesFM as a temporal feature extractor.",
            "work_principles": ["Separate generic temporal representation from task correction."],
            "work_insights": ["Errors often arise from cross-sensor drift."],
            "work_novelty": ["Connect a time-series foundation model to RUL fusion."],
        }
        principle = {
            "principle_id": "P-T",
            "name": "Representation-correction separation",
            "principle_type": "mechanism",
            "abstraction_level": "mechanism",
            "abstract_signature": "separate base representation from residual correction",
            "mechanism": "Freeze TimesFM and learn correction.",
            "problem_pressure": "End-to-end stacks hide error sources.",
            "objective": "Make contribution attribution cleaner.",
            "scarce_resources": ["labeled RUL data"],
            "assumptions": [],
            "constraints": ["avoid large retraining"],
            "invariants": ["base trend remains stable"],
            "tradeoffs": ["generalization vs adaptation"],
            "failure_modes": ["frozen features may miss degradation"],
            "feedback_loop": [],
            "transfer_hooks": ["measure base representation first"],
            "source_works": ["W-T"],
            "validation_level": "L1",
            "confidence_score": 0.5,
            "empirical_claims": [],
            "evidence_spans": [],
            "validation_notes": ["compare frozen and fused variants"],
            "domain_tags": ["time-series"],
            "relation_hints": [],
        }
        idea = {
            "idea_id": "I-T",
            "title": "Residual TimesFM RUL Corrector",
            "one_sentence_thesis": "Predict residual RUL after a base TimesFM estimate.",
            "research_goal_id": goal["goal_id"],
            "source_principles": ["P-T"],
            "operator_trace": [],
            "novelty_claim": "Separate base prediction from residual correction.",
            "prior_art_overlap": [],
            "expected_contribution": "Cleaner attribution.",
            "insight": "Residuals expose fusion value.",
            "mechanism_design": ["Freeze TimesFM.", "Train residual module."],
            "why_it_might_work": ["It clarifies contribution."],
            "minimal_experiment": "Compare direct and residual heads.",
            "validation_protocol": ["Run a direct-head baseline."],
            "baselines": ["TimesFM + MLP"],
            "metrics": ["RUL MAE"],
            "failure_modes": ["Residual signal may be weak."],
            "ranking_scores": {},
            "result_estimate_id": "E-T",
            "codex_prompt_plan_id": "PP-T",
            "feedback_status": "unvalidated",
            "conceptual_takeaway": "Separate trend and correction.",
            "sharp_reframing": "RUL as base plus residual.",
            "source_insights": [{"work_id": "W-T", "work_title": "TimesFM Sensor Paper", "text": "Errors arise from drift."}],
            "source_novelty": [{"work_id": "W-T", "work_title": "TimesFM Sensor Paper", "text": "Foundation model in RUL."}],
        }

        works, principles, ideas = engine._ensure_chinese_language_variants(
            goal,
            [work],
            [principle],
            [idea],
            offline=False,
            model_mode="openai_gpt55",
        )

        self.assertEqual(fake.calls[0]["mode"], "qwen_122b")
        self.assertIn("standard, idiomatic academic Chinese", fake.calls[0]["user"])
        self.assertIn("这篇工作讨论", works[0]["language_variants"]["zh"]["abstract"])
        self.assertEqual(principles[0]["language_variants"]["zh"]["name"], "表征与校正分离")
        self.assertIn("不要把所有能力", ideas[0]["language_variants"]["zh"]["conceptual_takeaway"])
        self.assertEqual(ideas[0]["language_variants"]["zh"]["metrics"], ["RUL MAE"])

    def test_lineage_graph_exposes_clickable_work_fact_nodes(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)
        result = engine.generate_ideas(SPARSE_VIEW_QUERY, source_mode="online", offline=True, paper_count=2, max_ideas=1)

        graph = result["graph"]
        fact_nodes = [node for node in graph["nodes"] if node["type"] in {"novelty", "insight"}]

        self.assertTrue(fact_nodes)
        self.assertTrue(all(node.get("work_id") for node in fact_nodes))
        self.assertTrue(all(node.get("label") for node in fact_nodes))

    def test_online_target_bypasses_principle_cache_when_more_works_are_needed(self) -> None:
        store = self.make_store()
        for idx in range(3):
            store.upsert(
                "source_works",
                {
                    "work_id": f"W-OLD-{idx}",
                    "title": f"Sparse view old work {idx}",
                    "authors": [],
                    "year": None,
                    "venue_or_source": "local",
                    "url_or_doi": "",
                    "source_type": "note",
                    "validation_level": "L0",
                    "abstract": "sparse view 3d reconstruction finite view geometry prior",
                },
                "work_id",
            )
        for idx in range(4):
            store.merge_principles(
                [
                    {
                        "principle_id": f"P-CACHED-{idx}",
                        "name": f"Cached sparse reconstruction principle {idx}",
                        "principle_type": "geometry_prior_under_sparse_observation",
                        "abstraction_level": "mechanism",
                        "abstract_signature": "recover latent 3D structure from scarce, ambiguous views",
                        "mechanism": "Use sparse-view geometry priors for 3D reconstruction.",
                        "problem_pressure": "Sparse view 3D reconstruction is underconstrained.",
                        "objective": "Improve held-out view quality.",
                        "scarce_resources": ["input views", "overlap", "pose certainty"],
                        "assumptions": ["Priors help scarce views."],
                        "constraints": ["few-view split"],
                        "invariants": ["cross-view consistency"],
                        "tradeoffs": ["prior strength vs hallucination risk"],
                        "failure_modes": ["hallucinated geometry"],
                        "feedback_loop": ["train", "render", "measure"],
                        "transfer_hooks": ["gate prior by uncertainty"],
                        "source_works": [f"W-OLD-{idx % 3}"],
                        "validation_level": "L0",
                        "confidence_score": 0.5,
                        "validation_notes": ["Run held-out views."],
                        "domain_tags": ["sparse-view", "3d-reconstruction"],
                        "relation_hints": ["shares_sparse_observation_pressure"],
                    }
                ]
            )

        calls: list[tuple[int, set[str]]] = []

        class CountingEngine(PrincipiaEngine):
            def _collect_works(self, goal, max_works, offline, **kwargs):  # type: ignore[override]
                calls.append((max_works, set(kwargs.get("exclude_work_ids") or set())))
                return [
                    {
                        "work_id": f"W-NEW-{idx}",
                        "title": f"New sparse reconstruction work {idx}",
                        "authors": [],
                        "year": None,
                        "venue_or_source": "local",
                        "url_or_doi": "",
                        "source_type": "note",
                        "validation_level": "L0",
                        "abstract": "sparse view 3d reconstruction prior consistency validation",
                    }
                    for idx in range(max_works)
                ]

        engine = CountingEngine(store=store)
        result = engine.generate_ideas(
            SPARSE_VIEW_QUERY,
            source_mode="online",
            offline=True,
            paper_count=5,
            max_ideas=2,
        )

        self.assertTrue(calls)
        self.assertEqual(calls[0][0], 2)
        self.assertEqual(len(calls[0][1]), 3)
        self.assertEqual(len(result["source_works"]), 5)
        self.assertEqual(store.counts()["source_works"], 5)

    def test_real_online_mode_searches_even_when_local_pool_is_ready(self) -> None:
        store = self.make_store()

        def rich_principle(pid: str, wid: str) -> dict:
            return {
                "principle_id": pid,
                "name": f"Ready sparse reconstruction principle {pid}",
                "principle_type": "geometry_prior_under_sparse_observation",
                "abstraction_level": "mechanism",
                "abstract_signature": "recover latent 3D structure from scarce views",
                "mechanism": "Use sparse-view geometry priors for 3D reconstruction.",
                "problem_pressure": "Sparse view 3D reconstruction is underconstrained.",
                "objective": "Improve held-out view quality.",
                "scarce_resources": ["input views", "overlap", "pose certainty"],
                "assumptions": ["Priors help scarce views."],
                "constraints": ["few-view split"],
                "invariants": ["cross-view consistency"],
                "tradeoffs": ["prior strength vs hallucination risk"],
                "failure_modes": ["hallucinated geometry"],
                "feedback_loop": ["train", "render", "measure"],
                "transfer_hooks": ["gate prior by uncertainty"],
                "source_works": [wid],
                "validation_level": "L1",
                "confidence_score": 0.5,
                "validation_notes": ["Run held-out views."],
                "domain_tags": ["sparse-view", "3d-reconstruction"],
                "relation_hints": ["shares_sparse_observation_pressure"],
            }

        for idx in range(3):
            store.upsert(
                "source_works",
                {
                    "work_id": f"W-LOCAL-{idx}",
                    "title": f"Local sparse reconstruction work {idx}",
                    "authors": [],
                    "year": 2025,
                    "venue_or_source": "local",
                    "url_or_doi": "",
                    "source_type": "note",
                    "validation_level": "L1",
                    "abstract": "sparse view 3d reconstruction finite view geometry prior",
                    "source_updated_at": "2025-01-01T00:00:00Z",
                },
                "work_id",
            )
        store.merge_principles([rich_principle(f"P-READY-{idx}", f"W-LOCAL-{idx % 3}") for idx in range(4)])
        calls: list[int] = []

        class NoLLM:
            costs = type("Costs", (), {"calls": []})()

            def available(self) -> bool:
                return False

        class OnlineSearchEngine(PrincipiaEngine):
            def _collect_works(self, goal, max_works, offline, **kwargs):  # type: ignore[override]
                calls.append(max_works)
                return [
                    {
                        "work_id": f"W-REMOTE-{idx}",
                        "title": f"Remote sparse reconstruction work {idx}",
                        "authors": [],
                        "year": 2026,
                        "venue_or_source": "arXiv",
                        "url_or_doi": f"https://arxiv.org/abs/2601.0000{idx}",
                        "source_type": "paper",
                        "validation_level": "L1",
                        "abstract": "online sparse-view reconstruction work with updated principles",
                        "source_updated_at": f"2026-01-0{idx + 1}T00:00:00Z",
                    }
                    for idx in range(max_works)
                ]

            def _mine_principles(self, goal, works, *, offline, model_mode):  # type: ignore[override]
                return [rich_principle(f"P-REMOTE-{idx}", work["work_id"]) for idx, work in enumerate(works)]

        engine = OnlineSearchEngine(store=store, llm=NoLLM())  # type: ignore[arg-type]
        result = engine.generate_ideas(
            SPARSE_VIEW_QUERY,
            source_mode="online",
            offline=False,
            paper_count=3,
            max_ideas=1,
        )

        self.assertEqual(calls, [3])
        self.assertTrue(all(work["work_id"].startswith("W-REMOTE") for work in result["source_works"]))
        self.assertFalse(result["from_cache"])

    def test_stale_remote_work_refreshes_work_and_replaces_old_principles(self) -> None:
        store = self.make_store()
        old_work = {
            "work_id": "W-SAME",
            "title": "Sparse View Dynamic Prior",
            "authors": [],
            "year": 2025,
            "venue_or_source": "arXiv",
            "url_or_doi": "https://arxiv.org/abs/2501.00001",
            "source_type": "paper",
            "validation_level": "L1",
            "abstract": "Old abstract about sparse view reconstruction.",
            "source_updated_at": "2025-01-01T00:00:00Z",
        }
        store.upsert("source_works", old_work, "work_id")
        store.merge_principles(
            [
                {
                    "principle_id": "P-OLD",
                    "name": "Old sparse-view prior principle",
                    "principle_type": "geometry_prior_under_sparse_observation",
                    "abstraction_level": "mechanism",
                    "abstract_signature": "old sparse-view signature",
                    "mechanism": "Use an old prior to stabilize sparse reconstruction.",
                    "problem_pressure": "Sparse views underconstrain geometry.",
                    "objective": "Improve held-out view quality.",
                    "scarce_resources": ["views", "overlap", "pose certainty"],
                    "assumptions": ["old prior transfers"],
                    "constraints": ["few-view split"],
                    "invariants": ["cross-view consistency"],
                    "tradeoffs": ["prior strength vs hallucination"],
                    "failure_modes": ["hallucinated surfaces"],
                    "feedback_loop": ["train", "render", "measure"],
                    "transfer_hooks": ["gate old prior by uncertainty"],
                    "source_works": ["W-SAME"],
                    "validation_level": "L1",
                    "confidence_score": 0.42,
                    "validation_notes": ["old validation"],
                    "domain_tags": ["sparse-view", "3d-reconstruction"],
                    "relation_hints": ["shares_sparse_observation_pressure"],
                }
            ]
        )
        remote_work = {
            **old_work,
            "abstract": "Updated abstract with new uncertainty-gated pseudo-view validation.",
            "source_updated_at": "2026-02-03T00:00:00Z",
        }
        mined_ids: list[str] = []

        class RefreshEngine(PrincipiaEngine):
            def _collect_works(self, goal, max_works, offline, **kwargs):  # type: ignore[override]
                return [remote_work]

            def _mine_principles(self, goal, works, *, offline, model_mode):  # type: ignore[override]
                mined_ids.extend([work["work_id"] for work in works])
                return [
                    {
                        "principle_id": "P-NEW",
                        "name": "Updated pseudo-view uncertainty principle",
                        "principle_type": "geometry_prior_under_sparse_observation",
                        "abstraction_level": "mechanism",
                        "abstract_signature": "updated sparse-view signature",
                        "mechanism": "Refresh pseudo-view priors when remote evidence updates.",
                        "problem_pressure": "Limited views make pseudo-view priors risky.",
                        "objective": "Improve sparse-view reconstruction without stale hallucination.",
                        "scarce_resources": ["views", "overlap", "pose certainty"],
                        "assumptions": ["updated evidence transfers"],
                        "constraints": ["few-view split"],
                        "invariants": ["cross-view consistency"],
                        "tradeoffs": ["refresh cost vs stale principle risk"],
                        "failure_modes": ["stale prior remains in the pool"],
                        "feedback_loop": ["search", "refresh", "validate"],
                        "transfer_hooks": ["refresh stale work before generation"],
                        "source_works": ["W-SAME"],
                        "validation_level": "L1",
                        "confidence_score": 0.58,
                        "validation_notes": ["new validation"],
                        "domain_tags": ["sparse-view", "3d-reconstruction"],
                        "relation_hints": ["shares_sparse_observation_pressure"],
                    }
                ]

        engine = RefreshEngine(store=store)
        result = engine.ingest_principles(
            SPARSE_VIEW_QUERY,
            max_works=1,
            offline=True,
            bypass_cache=True,
            refresh_existing=True,
        )

        self.assertEqual(mined_ids, ["W-SAME"])
        self.assertEqual(result["source_works"][0]["source_updated_at"], "2026-02-03T00:00:00Z")
        principles = store.list_items("principles", limit=10)
        self.assertEqual({item["base_principle_id"] for item in principles}, {"P-NEW"})
        self.assertEqual({item["model_mode"] for item in principles}, {"auto"})
        self.assertEqual(store.get_item("source_works", "W-SAME")["source_updated_at"], "2026-02-03T00:00:00Z")

    def test_progress_callback_reports_work_counts(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)
        updates: list[dict] = []

        engine.generate_ideas(
            SPARSE_VIEW_QUERY,
            source_mode="online",
            offline=True,
            paper_count=3,
            max_ideas=1,
            progress_callback=updates.append,
        )

        stages = {update["stage"] for update in updates}
        self.assertIn("local_pool", stages)
        self.assertIn("offline_seed", stages)
        self.assertTrue(any(update["target"] == 3 for update in updates))
        self.assertTrue(any(update["found"] == 3 for update in updates))

    def test_export_report_returns_markdown_and_pdf_bytes(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)
        engine.generate_ideas(SPARSE_VIEW_QUERY, source_mode="online", offline=True, paper_count=2, max_ideas=1)

        md_name, md_bytes, md_type = engine.export_report(SPARSE_VIEW_QUERY, language="zh", fmt="markdown")
        pdf_name, pdf_bytes, pdf_type = engine.export_report(SPARSE_VIEW_QUERY, language="zh", fmt="pdf")

        self.assertTrue(md_name.endswith(".md"))
        md_text = md_bytes.decode("utf-8")
        self.assertIn("Principia", md_text)
        self.assertLess(md_text.index("## Generated Ideas"), md_text.index("## Principle Atlas"))
        self.assertLess(md_text.index("## Principle Atlas"), md_text.index("## 相关工作"))
        self.assertIn("text/markdown", md_type)
        self.assertTrue(pdf_name.endswith(".pdf"))
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertEqual(pdf_type, "application/pdf")
        pdf_path = Path(tempfile.gettempdir()) / "principia-test-zh.pdf"
        pdf_path.write_bytes(pdf_bytes)
        extracted = "\n".join(page.extract_text() or "" for page in PdfReader(str(pdf_path)).pages)
        self.assertIn("principia", extracted.lower())
        self.assertIn("当前", extracted)

    def test_export_report_includes_richer_idea_work_and_evidence_fields(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)
        query = "field observatory baseline evidence"
        work = {
            "work_id": "W-EXPORT",
            "title": "Benchmark Evidence for Local Field Observatories",
            "authors": ["Ada Example"],
            "year": 2026,
            "venue_or_source": "local",
            "url_or_doi": "https://example.com/field-observatory",
            "source_type": "paper",
            "validation_level": "L1",
            "abstract": "Field observatory systems track ideas, principles, baselines, and benchmark evidence.",
            "work_principles": ["Treat benchmark and baseline evidence as first-class field state."],
            "work_insights": ["Local evidence makes research monitoring auditable."],
            "work_novelty": ["The novelty is project-scoped evidence extraction."],
        }
        principle = {
            "principle_id": "P-EXPORT",
            "name": "Project-scoped evidence memory",
            "principle_type": "research_memory",
            "abstraction_level": "mechanism",
            "abstract_signature": "project-scoped field observatory evidence",
            "mechanism": "Persist linked ideas, works, principles, baselines, and benchmark evidence.",
            "problem_pressure": "Research chats lose field context across sessions.",
            "objective": "Keep benchmark evidence auditable inside each project.",
            "scarce_resources": ["attention", "curated evidence"],
            "assumptions": ["The user revisits a research field."],
            "constraints": ["Evidence must stay local and editable."],
            "invariants": ["Linked works should remain visible in exports."],
            "tradeoffs": ["structure vs speed"],
            "failure_modes": ["weak source grounding"],
            "feedback_loop": ["extract", "curate", "export"],
            "transfer_hooks": ["apply to baseline tracking"],
            "source_works": ["W-EXPORT"],
            "validation_level": "L1",
            "confidence_score": 0.6,
            "domain_tags": ["field", "observatory", "baseline", "evidence"],
        }
        idea = {
            "idea_id": "I-EXPORT",
            "title": "Project Evidence Observatory",
            "one_sentence_thesis": "Create project-scoped monitoring for works, principles, baselines, benchmarks, and ideas.",
            "research_goal_id": "G-EXPORT",
            "source_principles": ["P-EXPORT"],
            "source_principle_names": ["Project-scoped evidence memory"],
            "operator_trace": [],
            "novelty_claim": "Turns benchmark and baseline evidence into editable project memory.",
            "prior_art_overlap": ["Local field observatory dashboards"],
            "expected_contribution": "A faster and more auditable Library export.",
            "insight": "Research value comes from retaining evidence structure.",
            "mechanism_design": ["Project list", "Grouped benchmark units", "Baseline evidence cards"],
            "why_it_might_work": ["Users can inspect related works when exporting ideas."],
            "minimal_experiment": "Export one project and inspect its linked evidence.",
            "validation_protocol": ["Check Markdown for linked works", "Check benchmark evidence"],
            "baselines": ["manual literature spreadsheet"],
            "metrics": ["coverage", "time to inspect"],
            "failure_modes": ["stale links"],
            "ranking_scores": {"novelty": 0.7},
            "result_estimate_id": "",
            "codex_prompt_plan_id": "",
            "feedback_status": "unvalidated",
        }
        benchmark = to_dict(
            BenchmarkRecord(
                benchmark_id="B-EXPORT",
                field_id="default",
                work_id="W-EXPORT",
                task="research evidence monitoring",
                dataset="ImageNet",
                split="base-to-novel",
                metric="coverage",
                metric_direction="higher_is_better",
            )
        )
        baseline = to_dict(
            BaselineRecord(
                baseline_id="BL-EXPORT",
                field_id="default",
                work_id="W-EXPORT",
                benchmark_id="B-EXPORT",
                baseline_name="CoOp",
                baseline_type="published",
            )
        )
        store.upsert("goals", {"goal_id": "G-EXPORT", "raw_query": query}, "goal_id")
        store.upsert("source_works", work, "work_id")
        store.upsert("principles", principle, "principle_id")
        store.upsert("ideas", idea, "idea_id")
        store.upsert("benchmark_records", benchmark, "benchmark_id")
        store.upsert("baseline_records", baseline, "baseline_id")

        _, md_bytes, _ = engine.export_report(query, fmt="markdown")
        md_text = md_bytes.decode("utf-8")

        self.assertIn("Similar or inspiring works: Benchmark Evidence for Local Field Observatories", md_text)
        self.assertIn("Expected contribution: A faster and more auditable Library export.", md_text)
        self.assertIn("Benchmark And Baseline Evidence", md_text)
        self.assertIn("Baselines: CoOp", md_text)

    def test_generate_ideas_can_auto_create_project_with_imported_records(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)

        result = engine.generate_ideas(
            VISION_CLIP_TTT_QUERY,
            source_mode="online",
            offline=True,
            paper_count=3,
            max_ideas=1,
            create_project=True,
            project_name="CLIP TTT Project",
        )
        project = result["project"]
        projects = {item["field_id"]: item for item in engine.list_projects()}
        dashboard = engine.build_library_dashboard(field_id=project["field_id"])

        self.assertEqual(project["name"], "CLIP TTT Project")
        self.assertIn(project["field_id"], projects)
        self.assertEqual(len(project["work_ids"]), len(result["source_works"]))
        self.assertEqual(len(project["idea_ids"]), len(result["ideas"]))
        self.assertGreaterEqual(dashboard["counts"]["work_facts"], 1)
        self.assertGreaterEqual(dashboard["counts"]["benchmarks"], 1)
        self.assertEqual(store.counts()["frontier_snapshots"], 0)

    def test_v1_project_tab_pagination_and_counts_are_membership_scoped(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)
        project = engine.create_project(name="Project Pagination", query="few-shot CLIP", goal_text="few-shot CLIP")
        work_ids = []
        for idx in range(25):
            work_id = f"W-PAGE-{idx:02d}"
            work_ids.append(work_id)
            store.upsert(
                "source_works",
                {
                    "work_id": work_id,
                    "title": f"Project work {idx:02d}",
                    "authors": [],
                    "year": 2026,
                    "venue_or_source": "local",
                    "url_or_doi": "",
                    "source_type": "paper",
                    "validation_level": "L1",
                    "abstract": "few-shot CLIP adaptation benchmark evidence",
                },
                "work_id",
            )
        engine.add_project_memberships(project["field_id"], "source_works", work_ids, source="test")

        first = engine.build_project_tab(project["field_id"], "works", offset=0, limit=10)
        second = engine.build_project_tab(project["field_id"], "works", offset=10, limit=10)
        summary = engine.project_summary(project["field_id"])

        self.assertEqual(first["total"], 25)
        self.assertEqual(len(first["items"]), 10)
        self.assertEqual(len(second["items"]), 10)
        self.assertEqual(first["items"][0]["work_id"], "W-PAGE-00")
        self.assertEqual(second["items"][0]["work_id"], "W-PAGE-10")
        self.assertTrue(second["has_more"])
        self.assertEqual(summary["counts"]["works"], 25)

    def test_v1_import_from_v0_copies_records_without_mutating_source(self) -> None:
        source_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(source_tmp.cleanup)
        source_path = Path(source_tmp.name) / "v0.sqlite"
        source = Store(source_path)
        source.upsert(
            "field_profiles",
            {
                **to_dict(FieldProfile(field_id="PRJ-V0", name="Imported v0 project", query="clip")),
                "work_ids": ["W-V0"],
                "principle_ids": ["P-V0"],
                "idea_ids": ["I-V0"],
            },
            "field_id",
        )
        source.upsert(
            "source_works",
            {
                "work_id": "W-V0",
                "title": "v0 CLIP work",
                "authors": [],
                "year": 2025,
                "venue_or_source": "local",
                "url_or_doi": "",
                "source_type": "paper",
                "validation_level": "L1",
                "abstract": "legacy v0 work",
            },
            "work_id",
        )
        source.upsert("principles", {"principle_id": "P-V0", "name": "v0 principle", "source_works": ["W-V0"]}, "principle_id")
        source.upsert("ideas", {"idea_id": "I-V0", "title": "v0 idea", "source_principles": ["P-V0"]}, "idea_id")
        before = source.counts()

        target = self.make_store()
        result = PrincipiaEngine(store=target).import_v0_store(source_path)
        after = source.counts()

        self.assertTrue(result["ok"])
        self.assertEqual(before, after)
        self.assertEqual(target.get_item("source_works", "W-V0")["title"], "v0 CLIP work")
        project_tab = PrincipiaEngine(store=target).build_project_tab("PRJ-V0", "works", offset=0, limit=10)
        self.assertEqual(project_tab["total"], 1)
        self.assertEqual(project_tab["items"][0]["work_id"], "W-V0")

    def test_benchmark_extraction_keeps_full_dataset_suite_and_baseline_methods(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)
        goal = engine._observatory_goal("few-shot CLIP adaptation")
        work = {
            "work_id": "W-SUITE",
            "title": "Cost-aware CLIP Adaptation Across Suite",
            "authors": [],
            "year": 2026,
            "venue_or_source": "local",
            "url_or_doi": "https://github.com/example/cost-aware-clip",
            "source_type": "paper",
            "validation_level": "L2",
            "abstract": (
                "We evaluate on ImageNet, Caltech101, OxfordPets, Food101, DTD, EuroSAT, UCF101, and SUN397 "
                "under a base-to-novel split. The method compares against zero-shot CLIP, CoOp, CoCoOp, "
                "Tip-Adapter, and TPT. zero-shot CLIP reports top-1 accuracy 68.1%. CoOp reports top-1 accuracy 74.2%. "
                "CoCoOp reports top-1 accuracy 75.0%. Tip-Adapter reports top-1 accuracy 76.4%. TPT reports top-1 accuracy 77.1%. "
                "The evaluated method reports top-1 accuracy 83.4% with GPU hours and latency accounting."
            ),
        }

        extracted = engine.extract_benchmark_records(goal, work)
        datasets = {item["dataset"] for item in extracted["benchmark_records"]}
        baseline_names = {item["baseline_name"] for item in extracted["baseline_records"]}
        proposed = [item for item in extracted["baseline_records"] if item["baseline_type"] == "proposed_method"]
        coop_links = {
            item["benchmark_id"]
            for item in extracted["baseline_records"]
            if item["baseline_name"] == "CoOp"
        }

        self.assertTrue({"ImageNet", "Caltech101", "OxfordPets", "Food101", "DTD", "EuroSAT", "UCF101", "SUN397"} <= datasets)
        self.assertNotIn("COCO", datasets)
        self.assertTrue({"zero-shot CLIP", "CoOp", "CoCoOp", "Tip-Adapter", "TPT"} <= baseline_names)
        self.assertFalse(proposed)
        self.assertGreaterEqual(len(coop_links), 8)
        self.assertTrue(any(item["source_hash"] for item in extracted["benchmark_records"]))

    def test_benchmark_extraction_parses_named_suites_and_compared_methods(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)
        goal = engine._observatory_goal("few-shot CLIP prompt learning")
        work = {
            "work_id": "W-PARSE",
            "title": "RouterPrompt for Cost-aware CLIP",
            "authors": [],
            "year": 2026,
            "venue_or_source": "local",
            "url_or_doi": "https://github.com/example/routerprompt",
            "source_type": "paper",
            "validation_level": "L2",
            "abstract": (
                "We evaluate on FGVCAircraft, StanfordCars, Flowers102, ImageNet, and EuroSAT. "
                "We compare against MaPLe, ProGrad, PromptSRC, KgCoOp, and CLIP-Adapter. "
                "MaPLe reports accuracy 73.0%. ProGrad reports accuracy 73.4%. PromptSRC reports accuracy 74.1%. "
                "KgCoOp reports accuracy 74.5%. CLIP-Adapter reports accuracy 72.8%. The evaluated method reports accuracy 77.2% and latency 18ms."
            ),
        }

        extracted = engine.extract_benchmark_records(goal, work)
        datasets = {item["dataset"] for item in extracted["benchmark_records"]}
        baselines = {item["baseline_name"] for item in extracted["baseline_records"]}
        view = engine.build_baseline_view()
        promptsrc = next(item for item in view["items"] if item["baseline_name"] == "PromptSRC")

        self.assertTrue({"FGVCAircraft", "StanfordCars", "Flowers102", "ImageNet", "EuroSAT"} <= datasets)
        self.assertTrue({"MaPLe", "ProGrad", "PromptSRC", "KgCoOp", "CLIP-Adapter"} <= baselines)
        self.assertEqual(promptsrc["official_code_url"], "https://github.com/muzairkhattak/PromptSRC")

    def test_benchmark_extraction_uses_transient_full_text_but_does_not_store_it(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)
        goal = engine._observatory_goal("logical pattern extraction during inference")
        work = {
            "work_id": "W-FULLTEXT",
            "title": "Inference-Time Logical Pattern Extraction",
            "authors": [],
            "year": 2026,
            "venue_or_source": "local",
            "url_or_doi": "https://example.org/fulltext",
            "abstract": "We study logical pattern extraction for language-model reasoning.",
            "transient_full_text": (
                "Experiments evaluate GSM8K and FOLIO with accuracy and exact match. "
                "The compared baselines are Chain-of-Thought, self-consistency, and ReAct. "
                "Chain-of-Thought reports exact match 62.0%. self-consistency reports exact match 67.3%. ReAct reports exact match 65.4%."
            ),
        }

        extracted = engine.extract_benchmark_records(goal, work)
        datasets = {item["dataset"] for item in extracted["benchmark_records"]}
        baselines = {item["baseline_name"] for item in extracted["baseline_records"]}
        stored = store.list_items("benchmark_records", limit=20)

        self.assertTrue({"GSM8K", "FOLIO"} <= datasets)
        self.assertTrue({"Chain-of-Thought", "self-consistency", "ReAct"} <= baselines)
        self.assertTrue(all(item["evidence_span"]["source"] == "transient_full_text" for item in stored))
        self.assertTrue(all("transient_full_text" not in item for item in stored))

    def test_reasoning_benchmark_extraction_does_not_invent_low_confidence_candidates(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)
        goal = engine._observatory_goal("logical pattern extraction during inference")
        work = {
            "work_id": "W-NO-DATASET",
            "title": "Inference-Time Logical Pattern Extraction",
            "authors": [],
            "year": 2026,
            "venue_or_source": "local",
            "abstract": (
                "We discuss logical pattern extraction and reasoning-domain evaluation, "
                "but this text does not explicitly name a dataset or benchmark suite."
            ),
            "transient_full_text": (
                "The method analyses exemplars during inference and describes qualitative reasoning behavior. "
                "No explicit dataset name or compared method is reported here."
            ),
        }

        extracted = engine.extract_benchmark_records(goal, work)

        self.assertEqual(extracted["benchmark_records"], [])
        self.assertEqual(extracted["baseline_records"], [])

    def test_baseline_extraction_rejects_generic_ablation_and_comparison_titles(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)
        goal = engine._observatory_goal("logical reasoning benchmark comparison")
        work = {
            "work_id": "W-BAD-BASELINE",
            "title": "A Comparison of LLMs and External Solvers for Logical Reasoning",
            "abstract": (
                "Experiments evaluate GSM8K with accuracy. "
                "The ablation section reports accuracy 71.2%, but no named compared method is used as a baseline."
            ),
        }

        extracted = engine.extract_benchmark_records(goal, work)
        names = {item["baseline_name"] for item in extracted["baseline_records"]}
        unknown = engine._v2_baseline_payload({"baseline_name": "A Comparison of LLMs and External Solvers"}, work, [])

        self.assertNotIn("ablation", {name.lower() for name in names})
        self.assertFalse(any(name.startswith("Comparison of LLMs") for name in names))
        self.assertEqual(unknown["description"], "")

    def test_benchmark_and_baseline_extraction_canonicalizes_noisy_fragments(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)
        goal = engine._observatory_goal("few-shot CLIP adaptation")
        work = {
            "work_id": "W-NOISY-ENTITIES",
            "title": "Noisy Prompt Tuning Evaluation",
            "abstract": (
                "Experiments are on ImageNet [3], ImageNet-R, and ImageNet-Sketch. "
                "The evaluation also mentions domain generalization using models trained on ImageNet. "
                "Baselines include aligning with experiments from TPT, state-of-the-art test-time prompt tuning method TPT, and CoOp. "
                "TPT reports top-1 accuracy 74.1%. CoOp reports top-1 accuracy 70.2%."
            ),
        }

        extracted = engine.extract_benchmark_records(goal, work)
        datasets = {item["dataset"] for item in extracted["benchmark_records"]}
        baselines = {item["baseline_name"] for item in extracted["baseline_records"]}
        noisy_datasets = [
            item["dataset"]
            for item in extracted["benchmark_records"]
            if item["dataset"].lower().startswith("on ")
            or "trained on" in item["dataset"].lower()
            or "domain generalization" in item["dataset"].lower()
        ]
        noisy_baselines = [
            item["baseline_name"]
            for item in extracted["baseline_records"]
            if "state-of-the-art" in item["baseline_name"].lower()
            or "experiments from" in item["baseline_name"].lower()
            or "aligning with" in item["baseline_name"].lower()
        ]

        self.assertTrue({"ImageNet", "ImageNet-R", "ImageNet-Sketch"} <= datasets)
        self.assertTrue({"TPT", "CoOp"} <= baselines)
        self.assertEqual(noisy_datasets, [])
        self.assertEqual(noisy_baselines, [])

    def test_payload_enrichment_repairs_noisy_official_entities(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)
        work = {"work_id": "W-CANON", "title": "Prompt Tuning", "url_or_doi": "https://example.org/paper"}

        benchmark = engine._v2_benchmark_payload({"dataset": "on ImageNet [3", "metric": "top-1 accuracy"}, work)
        baseline = engine._v2_baseline_payload({"baseline_name": "state-of-the-art test-time prompt tuning method TPT"}, work, [])

        self.assertEqual(benchmark["dataset"], "ImageNet")
        self.assertEqual(benchmark["benchmark_name"], "ImageNet")
        self.assertEqual(baseline["baseline_name"], "TPT")

    def test_work_fact_extraction_prefers_takeaway_insights_and_concrete_novelty(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)
        goal = engine._observatory_goal("few-shot CLIP adaptation")
        work = {
            "work_id": "W-FACT-RICH",
            "title": "Evidence-gated CLIP adapters",
            "authors": [],
            "year": 2026,
            "venue_or_source": "local",
            "url_or_doi": "",
            "source_type": "paper",
            "validation_level": "L2",
            "abstract": (
                "We propose an evidence-gated adapter that updates only when prompt uncertainty is high. "
                "Ablation shows that updating all layers hurts novel-class accuracy when shots are scarce. "
                "The main novelty lies in a benchmark-conditioned router that switches between cache retrieval and prompt tuning."
            ),
        }

        facts = engine.extract_work_facts(goal, work)
        insights = [fact["text"] for fact in facts if fact["fact_type"] == "insight"]
        novelty = [fact["text"] for fact in facts if fact["fact_type"] == "novelty"]

        self.assertTrue(any("hurts novel-class accuracy" in text for text in insights))
        self.assertTrue(any("benchmark-conditioned router" in text for text in novelty))

    def test_v1_refresh_skips_unchanged_works_after_cached_extraction(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)
        project = engine.create_project(name="Refresh Project", query="clip refresh", goal_text="clip refresh")
        work = {
            "work_id": "W-REFRESH",
            "title": "Refresh-aware CLIP adaptation",
            "authors": [],
            "year": 2026,
            "venue_or_source": "local",
            "url_or_doi": "https://github.com/example/refresh",
            "source_type": "paper",
            "validation_level": "L2",
            "abstract": "We evaluate on ImageNet and OxfordPets with CoOp and zero-shot CLIP baselines. CoOp reports top-1 accuracy 70.0%. zero-shot CLIP reports top-1 accuracy 66.8%. The evaluated method reports top-1 accuracy 81.2%.",
            "source_updated_at": "2026-01-01T00:00:00Z",
        }
        store.upsert("source_works", work, "work_id")
        engine.add_project_memberships(project["field_id"], "source_works", ["W-REFRESH"], source="test")

        first = engine.refresh_project(project["field_id"], source_mode="local")
        second = engine.refresh_project(project["field_id"], source_mode="local")

        self.assertGreaterEqual(first["run"]["output_counts"]["benchmark_records"], 1)
        self.assertGreaterEqual(second["run"]["output_counts"]["skipped_unchanged_works"], 1)
        self.assertGreaterEqual(second["summary"]["counts"]["benchmarks"], 1)
        self.assertGreaterEqual(second["summary"]["counts"]["baselines"], 1)

    def test_v1_idea_assembler_persists_traceable_idea_at_top(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store, llm=NoLLM())  # type: ignore[arg-type]
        project = engine.create_project(
            name="Assembler Project",
            description="Project-scoped evidence synthesis",
            query="assemble CLIP idea",
            goal_text="assemble CLIP idea",
        )
        work = {
            "work_id": "W-ASM",
            "title": "Assembler evidence work",
            "authors": [],
            "year": 2026,
            "venue_or_source": "local",
            "url_or_doi": "",
            "source_type": "paper",
            "validation_level": "L1",
            "abstract": "few-shot CLIP adaptation needs selected evidence synthesis.",
        }
        fact = to_dict(
            WorkFact(
                fact_id="WF-ASM",
                field_id=project["field_id"],
                work_id="W-ASM",
                fact_type="insight",
                text="Selected evidence should constrain the assembled idea.",
            )
        )
        principle = {
            "principle_id": "P-ASM",
            "name": "Evidence-constrained assembly",
            "principle_type": "research_memory",
            "abstraction_level": "mechanism",
            "abstract_signature": "selected evidence constrains idea generation",
            "mechanism": "Combine selected project facts into one falsifiable mechanism.",
            "problem_pressure": "Unscoped generation loses source grounding.",
            "objective": "Keep new ideas traceable to selected evidence.",
            "scarce_resources": ["attention"],
            "assumptions": ["selected evidence is relevant"],
            "constraints": ["project-scoped synthesis"],
            "invariants": ["source evidence remains visible"],
            "tradeoffs": ["specificity vs breadth"],
            "failure_modes": ["overfitting to one source"],
            "feedback_loop": ["select", "assemble", "validate"],
            "transfer_hooks": ["reuse evidence tray"],
            "source_works": ["W-ASM"],
            "validation_level": "L1",
            "confidence_score": 0.56,
            "domain_tags": ["assembly"],
        }
        store.upsert("source_works", work, "work_id")
        store.upsert("work_facts", fact, "fact_id")
        store.merge_principles([principle])
        engine.add_project_memberships(project["field_id"], "source_works", ["W-ASM"], source="test")
        engine.add_project_memberships(project["field_id"], "work_facts", ["WF-ASM"], source="test")
        engine.add_project_memberships(project["field_id"], "principles", ["P-ASM"], source="test")

        result = engine.assemble_idea(
            field_id=project["field_id"],
            goal_text="assemble CLIP idea",
            project_name="Assembler Project",
            project_description="Project-scoped evidence synthesis",
            selected_refs=[{"bucket": "works", "id": "W-ASM"}, {"bucket": "insights", "id": "WF-ASM"}],
            model_mode="auto",
        )
        ideas = engine.build_project_tab(project["field_id"], "ideas", offset=0, limit=10)["items"]

        self.assertTrue(result["ok"])
        self.assertEqual(ideas[0]["idea_id"], result["idea"]["idea_id"])
        self.assertIn("W-ASM", result["idea"]["source_works"])
        self.assertIn("WF-ASM", result["idea"]["source_facts"])
        self.assertEqual(result["idea"]["assembly_trace"]["selected_refs"][0]["id"], "W-ASM")

    def test_v1_idea_assembler_accepts_user_note_as_first_class_evidence(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store, llm=NoLLM())  # type: ignore[arg-type]
        project = engine.create_project(
            name="Note Assembly Project",
            description="User hunches should steer assembly.",
            query="",
            goal_text="",
        )
        note = "Try a two-stage CLIP adapter where benchmark uncertainty decides whether to use prompt tuning or cache retrieval."

        result = engine.assemble_idea(
            field_id=project["field_id"],
            goal_text="few-shot CLIP adaptation",
            project_name=project["name"],
            project_description=project["description"],
            selected_refs=[],
            user_note=note,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["idea"]["assembly_trace"]["user_note"], note)
        self.assertIn("user_note", result["idea"])
        self.assertTrue(any(fact_id.startswith("UN-") for fact_id in result["idea"]["source_facts"]))

    def test_v2_canonical_work_keeps_model_versions_and_manual_active(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store, llm=NoLLM())  # type: ignore[arg-type]
        work_a = {
            "work_id": "W-A",
            "title": "Adaptive Prompt Routing for Few-Shot Vision Models",
            "authors": ["A. Researcher"],
            "year": 2026,
            "venue_or_source": "ICLR",
            "url_or_doi": "https://example.org/a",
            "abstract": "We introduce adaptive prompt routing for few-shot CLIP adaptation.",
        }
        work_b = {**work_a, "work_id": "W-B", "url_or_doi": "https://example.org/b", "abstract": "We introduce a revised abstract."}

        first = engine._v2_upsert_work(work_a, model_mode="efficient")
        second = engine._v2_upsert_work(work_b, model_mode="strong")
        self.assertEqual(first["work_id"], second["work_id"])
        self.assertEqual(len(store.list_items("source_works", limit=10)), 1)
        self.assertEqual(len(second["variants"]), 2)

        edited = engine.v2_item_update(
            {
                "bucket": "source_works",
                "id": second["work_id"],
                "payload": {"title": "Manual title", "abstract": "Manual abstract"},
            }
        )["item"]
        refreshed = engine._v2_upsert_work({**work_b, "abstract": "Another model update."}, model_mode="strong")
        presented = engine._v2_present_item(refreshed)

        self.assertEqual(edited["title"], "Manual title")
        self.assertEqual(presented["title"], "Manual title")
        self.assertTrue(presented["active_variant"]["is_user_edit"])

    def test_v2_research_extracts_and_merges_project_evidence(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store, llm=FakeV2LLM())  # type: ignore[arg-type]
        project = engine.create_project(name="Vision Adaptation", goal_text="few-shot CLIP adaptation")
        works = [
            {
                "work_id": "W-R1",
                "title": "Adaptive Prompt Routing for Few-Shot Vision Models",
                "authors": ["A. Researcher"],
                "year": 2026,
                "venue_or_source": "CVPR",
                "url_or_doi": "https://example.org/r1",
                "abstract": (
                    "We introduce Adaptive Prompt Routing, a method that routes CLIP prompts under distribution shift. "
                    "We show that under base-to-novel transfer, routing improves calibration for rare classes. "
                    "Benchmark experiments evaluate ImageNet, Caltech101, and OxfordPets against CoOp, CoCoOp, and MaPLe. "
                    "CoOp reports accuracy 70.0%. CoCoOp reports accuracy 71.4%. MaPLe reports accuracy 73.0%. The evaluated method reports accuracy 75.0%."
                ),
            },
            {
                "work_id": "W-R2",
                "title": "Adaptive Prompt Routing for Few-Shot Vision Models",
                "authors": ["B. Researcher"],
                "year": 2026,
                "venue_or_source": "arXiv",
                "url_or_doi": "https://example.org/r2",
                "abstract": "We introduce Adaptive Prompt Routing with updated benchmark details.",
            },
        ]
        original = engine_module.search_hybrid_sources
        engine_module.search_hybrid_sources = lambda *args, **kwargs: works
        try:
            result = engine.v2_research_project(project["field_id"], goal_text=project["goal_text"], model_mode="efficient", target_works=2)
        finally:
            engine_module.search_hybrid_sources = original

        counts = result["summary"]["counts"]
        self.assertEqual(counts["works"], 1)
        self.assertGreaterEqual(counts["existed_ideas"], 1)
        self.assertGreaterEqual(counts["principles"], 1)
        self.assertGreaterEqual(counts["takeaway_messages"], 1)
        self.assertGreaterEqual(counts["benchmarks"], 3)
        self.assertTrue(any(item["dataset"] == "ImageNet" for item in store.list_items("benchmark_records", limit=20)))
        self.assertTrue(any(item["baseline_name"] == "CoOp" for item in store.list_items("baseline_records", limit=20)))

    def test_v2_research_persists_full_text_records_before_llm_availability(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store, llm=NoLLM())  # type: ignore[arg-type]
        project = engine.create_project(name="Clip-FS", goal_text=VISION_CLIP_TTT_QUERY)
        works = [
            {
                "work_id": "W-CLIP-FULL",
                "title": "Budgeted Test-Time CLIP Adaptation",
                "authors": ["A. Researcher"],
                "year": 2026,
                "venue_or_source": "CVPR",
                "url_or_doi": "https://example.org/clip-full",
                "abstract": "Few-shot CLIP adaptation with limited GPUs.",
            }
        ]
        full_text = (
            "Experiments evaluate ImageNet, Caltech101, and OxfordPets under a base-to-novel split with top-1 accuracy. "
            "The method compares against zero-shot CLIP, CoOp, CoCoOp, and MaPLe. "
            "zero-shot CLIP reports top-1 accuracy 67.2%. CoOp reports top-1 accuracy 70.0%. CoCoOp reports top-1 accuracy 71.4%. MaPLe reports top-1 accuracy 73.0%. "
            "We show that test-time prompt routing improves novel-class calibration when compute is limited to 4-8 GPUs."
        )
        original_search = engine_module.search_hybrid_sources
        original_fetch = engine_module.fetch_transient_full_text
        engine_module.search_hybrid_sources = lambda *args, **kwargs: works
        engine_module.fetch_transient_full_text = lambda *args, **kwargs: full_text
        try:
            result = engine.v2_research_project(project["field_id"], goal_text=project["goal_text"], model_mode="deepseek_pro", target_works=1)
        finally:
            engine_module.search_hybrid_sources = original_search
            engine_module.fetch_transient_full_text = original_fetch

        counts = result["summary"]["counts"]
        self.assertGreaterEqual(counts["works"], 1)
        self.assertGreaterEqual(counts["benchmarks"], 3)
        self.assertGreaterEqual(counts["baselines"], 3)
        self.assertTrue(any(item["dataset"] == "ImageNet" for item in store.list_items("benchmark_records", limit=20)))
        self.assertTrue(any(item["baseline_name"] == "CoOp" for item in store.list_items("baseline_records", limit=20)))

    def test_v2_research_limits_structured_extraction_to_selected_works(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store, llm=NoLLM())  # type: ignore[arg-type]
        project = engine.create_project(name="Clip-FS", goal_text=VISION_CLIP_TTT_QUERY)
        works = [
            {
                "work_id": f"W-CLIP-{index:02d}",
                "title": f"Few-shot CLIP adaptation study {index}",
                "authors": ["A. Researcher"],
                "year": 2026,
                "venue_or_source": "arXiv",
                "url_or_doi": f"https://example.org/clip-{index}",
                "abstract": "Few-shot CLIP test-time training with ImageNet and adaptation baselines.",
            }
            for index in range(40)
        ]
        structured_calls: list[str] = []
        original_search = engine_module.search_hybrid_sources
        original_fetch = engine_module.fetch_transient_full_text
        original_extract = engine.extract_benchmark_records

        def fake_extract(goal, work, *, field_id="default", persist=True, force=False):
            structured_calls.append(str(work.get("work_id") or ""))
            return {"benchmark_records": [], "baseline_records": [], "result_records": []}

        engine_module.search_hybrid_sources = lambda *args, **kwargs: works
        engine_module.fetch_transient_full_text = lambda *args, **kwargs: ""
        engine.extract_benchmark_records = fake_extract  # type: ignore[method-assign]
        try:
            result = engine.v2_research_project(project["field_id"], goal_text=project["goal_text"], model_mode="deepseek_pro", target_works=40)
        finally:
            engine_module.search_hybrid_sources = original_search
            engine_module.fetch_transient_full_text = original_fetch
            engine.extract_benchmark_records = original_extract  # type: ignore[method-assign]

        self.assertEqual(result["summary"]["counts"]["works"], 40)
        self.assertLess(len(structured_calls), 40)
        self.assertLessEqual(len(structured_calls), engine._v2_llm_extraction_limit("deepseek_pro"))

    def test_project_navigation_paths_do_not_require_full_snapshot(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store, llm=NoLLM())  # type: ignore[arg-type]
        project = engine.create_project(name="Fast Project", goal_text=VISION_CLIP_TTT_QUERY)
        work = engine._v2_upsert_work(
            {
                "work_id": "W-FAST",
                "title": "Fast CLIP Work",
                "abstract": "Few-shot CLIP adaptation.",
                "year": 2026,
                "url_or_doi": "https://example.org/fast",
            },
            model_mode="metadata",
        )
        idea = engine._v2_upsert_canonical(
            "existed_ideas",
            "Gate test-time adaptation by uncertainty.",
            {
                "title": "Uncertainty-gated adaptation",
                "idea_text": "Gate test-time adaptation by uncertainty.",
                "source_work_ids": [work["work_id"]],
            },
            model_mode="fake",
        )
        engine.add_project_memberships(project["field_id"], "source_works", [work["work_id"]])
        engine.add_project_memberships(project["field_id"], "existed_ideas", [idea["canonical_id"]])

        def fail_snapshot(*args, **kwargs):
            raise AssertionError("full snapshot should not be required")

        store.snapshot = fail_snapshot  # type: ignore[method-assign]
        self.assertEqual(engine.v2_project_summary(project["field_id"])["counts"]["works"], 1)
        self.assertEqual(engine.list_projects()[0]["field_id"], project["field_id"])
        tab = engine.build_v2_project_tab(project["field_id"], "existed_ideas", limit=10)
        self.assertEqual(tab["total"], 1)
        deleted = engine.delete_project(project["field_id"])
        self.assertTrue(deleted["ok"])

    def test_project_tab_uses_compact_payload_for_heavy_records(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store, llm=NoLLM())  # type: ignore[arg-type]
        project = engine.create_project(name="Heavy Records", goal_text=VISION_CLIP_TTT_QUERY)
        performance = [{"benchmark_name": "ImageNet", "metric": "accuracy", "value_text": str(index)} for index in range(180)]
        baseline = engine._v2_upsert_canonical(
            "baseline_records",
            "Heavy baseline on ImageNet",
            {
                "baseline_name": "Heavy Baseline",
                "description": "A compacted baseline fixture.",
                "source_work_ids": ["W-H"],
                "benchmarks": ["ImageNet"] * 180,
                "performance": performance,
            },
            model_mode="fake",
        )
        engine.add_project_memberships(project["field_id"], "baseline_records", [baseline["baseline_id"]])

        tab = engine.build_v2_project_tab(project["field_id"], "baselines", limit=10)
        item = tab["items"][0]

        self.assertNotIn("variants", item)
        self.assertLessEqual(len(item["performance"]), 6)
        self.assertGreaterEqual(item["performance_total"], 120)
        self.assertNotIn("payload", item["active_variant"])

    def test_stale_running_research_becomes_partial_error_with_kept_records(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store, llm=NoLLM())  # type: ignore[arg-type]
        project = engine.create_project(name="Stale Research", goal_text="few-shot CLIP")
        run = {
            "run_id": "VRUN-STALE",
            "field_id": project["field_id"],
            "type": "v2_research",
            "status": "running",
            "stage": "llm_extraction",
            "message": "Waiting for LLM extraction.",
            "counts": {"stored_works": 12, "benchmarks": 2},
            "started_at": "2000-01-01T00:00:00+00:00",
            "updated_at": "2000-01-01T00:00:00+00:00",
        }
        store.upsert("research_runs", run, "run_id")
        profile = store.get_item("field_profiles", project["field_id"])
        profile["refresh_status"] = "researching"
        store.upsert("field_profiles", profile, "field_id")

        recovered = engine.recover_stale_research_run("VRUN-STALE", stale_seconds=-1)
        refreshed_profile = store.get_item("field_profiles", project["field_id"])

        self.assertEqual(recovered["status"], "partial_error")
        self.assertIn("Completed records were kept", recovered["message"])
        self.assertEqual(refreshed_profile["refresh_status"], "partial_error")

    def test_v1_status_route_recovers_stale_research_run(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store, llm=NoLLM())  # type: ignore[arg-type]
        project = engine.create_project(name="Stale Route Research", goal_text="few-shot CLIP")
        stale_at = "2000-01-01T00:00:00+00:00"
        run = {
            "run_id": "VRUN-STALE-ROUTE",
            "field_id": project["field_id"],
            "type": "v2_research",
            "status": "running",
            "stage": "llm_extraction",
            "message": "Waiting for LLM extraction.",
            "counts": {"stored_works": 8, "principles": 1},
            "started_at": stale_at,
            "updated_at": stale_at,
        }
        store.upsert("research_runs", run, "run_id")
        stale_payload = {**run, "updated_at": stale_at}
        with store._connect() as conn:
            conn.execute(
                "UPDATE records SET payload = ?, updated_at = ? WHERE bucket = ? AND id = ?",
                (json.dumps(stale_payload), stale_at, "research_runs", run["run_id"]),
            )

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(store, engine))
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)

        url = f"http://127.0.0.1:{httpd.server_port}/api/v1/research/status?run_id={run['run_id']}"
        with urllib.request.urlopen(url, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))

        self.assertEqual(payload["run"]["status"], "partial_error")
        self.assertIn("Completed records were kept", payload["run"]["message"])

    def test_v2_research_allows_200_target_works(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store, llm=NoLLM())  # type: ignore[arg-type]
        project = engine.create_project(name="Reasoning Patterns", goal_text=SYMBOLIC_COMPACTNESS_MAS_QUERY)
        calls = []
        works = [
            {
                "work_id": "W-RP1",
                "title": "Neural-Symbolic Reasoning with Exemplar Pattern Induction",
                "authors": ["A. Researcher"],
                "year": 2026,
                "venue_or_source": "arXiv",
                "url_or_doi": "https://example.org/rp1",
                "abstract": "We study how exemplar patterns support logical reasoning on GSM8K, MATH, BBH, and FOLIO benchmarks.",
            }
        ]
        original = engine_module.search_hybrid_sources

        def fake_search(query, max_results=100, timeout=12):
            calls.append({"query": query, "max_results": max_results, "timeout": timeout})
            return works

        engine_module.search_hybrid_sources = fake_search
        try:
            result = engine.v2_research_project(
                project["field_id"],
                goal_text="Explore the intrinsic logical patterns inside the exemplars in various reasoning domains and benchmarks",
                model_mode="qwen_122b",
                target_works=200,
            )
        finally:
            engine_module.search_hybrid_sources = original

        self.assertEqual(calls[0]["max_results"], 200)
        self.assertEqual(result["run"]["target_works"], 200)
        self.assertEqual(result["summary"]["project"]["settings"]["target_works"], 200)

    def test_v2_source_sentence_extraction_rejects_incomplete_template_filler(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store, llm=NoLLM())  # type: ignore[arg-type]
        work = {
            "work_id": "W-NSR",
            "title": "Neural-Symbolic Reasoning: Towards the Integration of Logical Reasoning with Large Language Models",
            "abstract": (
                "We introduce a neural-symbolic verifier that extracts logical forms from exemplars and evaluates the verifier on GSM8K and FOLIO. "
                "The principle is that exemplar-derived logical forms should transfer only when verifier constraints match the target task mechanism."
            ),
            "venue_or_source": "IEEE",
            "year": 2025,
        }

        extracted = engine._v2_extract_concepts_from_work(
            "Explore the intrinsic logical patterns inside the exemplars in various reasoning domains and benchmarks",
            work,
            {},
        )

        self.assertEqual(extracted["existed_ideas"], [])
        self.assertEqual(extracted["principles"], [])
        self.assertEqual(extracted["takeaway_messages"], [])

    def test_v2_content_gate_rejects_boilerplate_objectives_and_repairs_author_voice(self) -> None:
        engine = PrincipiaEngine(store=self.make_store(), llm=NoLLM())  # type: ignore[arg-type]

        self.assertFalse(
            engine._v2_is_high_quality_concept(
                "Materials prior to 2016 here are licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 3.0 International License.",
                kind="principle",
            )
        )
        self.assertFalse(
            engine._v2_is_high_quality_concept(
                "(iii) To examine how different LLMs varying in architecture and training data influence creativity dimensions when prompted with analogies.",
                kind="principle",
            )
        )
        repaired = engine._v2_repair_objective_concept_item(
            {"title": "Probe claim", "text": "We do not claim that a successfully trained LTN probe is always proof that an LLM shows the modelled reasoning."},
            kind="message",
            work={},
        )

        self.assertIn("is not always proof", repaired["text"])
        self.assertNotIn("We do not claim", repaired["text"])

    def test_v2_extraction_contract_rejects_duplicate_principle_fields_and_dangling_citations(self) -> None:
        engine = PrincipiaEngine(store=self.make_store(), llm=NoLLM())  # type: ignore[arg-type]
        work = {
            "work_id": "W-RLHF",
            "title": "Preference Alignment Under Shifting Stakeholder Goals",
            "abstract": "The work evaluates RLHF preference optimization under shifting stakeholder goals and analyzes mis-generalization in deployed alignment systems.",
        }
        duplicate = {
            "title": "RLHF shifts",
            "text": "When stakeholder goals shift, preference optimization can mis-generalize because fixed reward models preserve outdated tradeoffs.",
            "argument": "When stakeholder goals shift, preference optimization can mis-generalize because fixed reward models preserve outdated tradeoffs.",
            "mechanism": "When stakeholder goals shift, preference optimization can mis-generalize because fixed reward models preserve outdated tradeoffs.",
            "evidence": "The source work evaluates RLHF preference optimization under shifting stakeholder goals and analyzes mis-generalization in deployed alignment systems.",
            "discussion": "The principle is useful because alignment behavior depends on whether the preference model remains valid after deployment conditions change. It should be applied when reward models encode stakeholder goals that may drift over time.",
        }
        dangling = {
            "title": "RLHF shifts",
            "text": "While effective, RLHF and its variants optimize against fixed training preferences and can mis-generalize under shifting stakeholder goals (Son et al.",
            "argument": "While effective, RLHF and its variants optimize against fixed training preferences and can mis-generalize under shifting stakeholder goals (Son et al.",
            "evidence": duplicate["evidence"],
            "discussion": duplicate["discussion"],
        }

        repaired_duplicate = engine._v2_enforce_concept_contract(duplicate, kind="principle", work=work)
        self.assertIsNotNone(repaired_duplicate)
        self.assertNotEqual(repaired_duplicate["argument"], repaired_duplicate.get("mechanism", ""))
        self.assertEqual(repaired_duplicate.get("mechanism", ""), "")
        self.assertIsNone(engine._v2_enforce_concept_contract(dangling, kind="principle", work=work))

    def test_v2_extraction_contract_rejects_irrelevant_logic_artifacts(self) -> None:
        engine = PrincipiaEngine(store=self.make_store(), llm=NoLLM())  # type: ignore[arg-type]
        work = {
            "work_id": "W-ALIGN",
            "title": "Preference Alignment Under Shifting Stakeholder Goals",
            "abstract": "The work evaluates RLHF preference optimization under shifting stakeholder goals and analyzes mis-generalization in deployed alignment systems.",
            "year": 2025,
        }
        extracted = engine._v2_extract_concepts_from_work(
            "logical pattern extraction during inference",
            work,
            {
                "principles": [
                    {
                        "name": "Free-floating disjunction",
                        "argument": "(A ∨ B)→ B: If A or B, C.; C, except when neither A nor B.",
                        "evidence": "The source work evaluates RLHF preference optimization under shifting stakeholder goals and analyzes mis-generalization in deployed alignment systems.",
                        "discussion": "The record is intentionally unrelated to the current work and should be rejected by the work-grounding quality gate.",
                    }
                ]
            },
        )

        self.assertEqual(extracted["principles"], [])

    def test_v2_extraction_contract_accepts_grounded_type_specific_records(self) -> None:
        engine = PrincipiaEngine(store=self.make_store(), llm=NoLLM())  # type: ignore[arg-type]
        work = {
            "work_id": "W-PATTERN",
            "title": "Benchmark-Conditioned Logical Pattern Routing",
            "abstract": (
                "The work studies reasoning exemplars, logical pattern routing, benchmark-conditioned compatibility tests, "
                "and token-efficient inference under GSM8K and FOLIO evaluation."
            ),
            "year": 2025,
        }
        extracted = engine._v2_extract_concepts_from_work(
            "logical pattern extraction during inference",
            work,
            {
                "existed_ideas": [
                    {
                        "title": "Benchmark-conditioned logical pattern routing",
                        "core_idea": "Benchmark-conditioned logical pattern routing uses compatibility tests to decide when exemplar-derived reasoning structure should influence token-efficient inference.",
                        "mechanism": "The method represents each reasoning exemplar as a candidate logical pattern and scores it against the target benchmark family before inference. Patterns are routed into the prompt only when compatibility evidence suggests that the pattern can improve accuracy per token.",
                        "discussion": "This idea is valuable because it turns exemplar reuse into a measurable control decision rather than an automatic context expansion. It is limited by the quality of the compatibility test and should be validated on reasoning benchmarks where transfer failures are observable.",
                        "evidence": "The source work studies reasoning exemplars, logical pattern routing, benchmark-conditioned compatibility tests, and token-efficient inference under GSM8K and FOLIO evaluation.",
                    }
                ],
                "principles": [
                    {
                        "name": "Compatibility-gated pattern transfer",
                        "argument": "When exemplar-derived reasoning patterns are reused during inference, transfer should be gated by benchmark compatibility rather than by exemplar availability alone.",
                        "evidence": "The source work links reasoning exemplars, logical pattern routing, benchmark-conditioned compatibility tests, and token-efficient inference under GSM8K and FOLIO evaluation.",
                        "discussion": "The principle is useful because it makes the control signal for pattern reuse explicit and testable. It applies when a system can estimate benchmark compatibility before spending additional reasoning tokens.",
                    }
                ],
                "takeaway_messages": [
                    {
                        "title": "Compatibility matters more than raw exemplar count",
                        "main_results": "Logical pattern routing is most useful when benchmark compatibility identifies which exemplar structure can transfer to the target inference case.",
                        "condition": "The result applies to reasoning benchmarks such as GSM8K and FOLIO where exemplar-derived structure is visible before inference. It assumes token cost and answer accuracy are evaluated under the same benchmark protocol.",
                        "discussion": "The takeaway discourages adding more exemplars merely because context length permits it. It supports measuring whether each pattern earns its token budget before entering the inference trace.",
                        "evidence": "The source work studies benchmark-conditioned compatibility tests for logical pattern routing under token-efficient reasoning evaluation.",
                    }
                ],
            },
        )

        self.assertEqual(len(extracted["existed_ideas"]), 1)
        self.assertEqual(len(extracted["principles"]), 1)
        self.assertEqual(len(extracted["takeaway_messages"]), 1)
        self.assertNotEqual(extracted["principles"][0]["argument"], extracted["principles"][0].get("mechanism", ""))

    def test_v2_generation_sanitizes_unsupported_quantitative_claims(self) -> None:
        engine = PrincipiaEngine(store=self.make_store(), llm=NoLLM())  # type: ignore[arg-type]

        sanitized = engine._sanitize_unsupported_quantitative_claims(
            {
                "novelty_claim": "The router reduces token usage by 55-87% while preserving accuracy.",
                "mechanistic_design": ["Ablation improves accuracy 12% on the target benchmark."],
            },
            evidence_text="The evidence mentions token cost and accuracy but no numeric reduction.",
        )

        self.assertNotIn("55-87", sanitized["novelty_claim"])
        self.assertNotIn("12%", sanitized["mechanistic_design"][0])
        self.assertIn("measured validation protocol", sanitized["novelty_claim"])

    def test_v2_reasoning_pattern_query_expands_to_benchmarks_and_exemplars(self) -> None:
        engine = PrincipiaEngine(store=self.make_store(), llm=NoLLM())  # type: ignore[arg-type]

        query = engine._v2_research_query("Explore the intrinsic logical patterns inside the exemplars in various reasoning domains and benchmarks")

        self.assertIn("chain-of-thought reasoning", query)
        self.assertIn("BBH GSM8K MATH FOLIO ProofWriter ARC StrategyQA", query)

    def test_v2_generate_my_idea_detail_includes_related_ideas_and_principle_map(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store, llm=FakeV2LLM())  # type: ignore[arg-type]
        project = engine.create_project(name="Idea Project", goal_text="adaptive prompt routing")
        existed = engine._v2_upsert_canonical(
            "existed_ideas",
            "adaptive prompt routing",
            {"title": "Adaptive Prompt Routing", "idea_text": "Use uncertainty to route prompts for CLIP adaptation.", "source_work_ids": []},
            model_mode="efficient",
        )
        principle = engine._v2_upsert_canonical(
            "principles",
            "uncertainty routes adaptation",
            {"name": "Uncertainty Routes Adaptation", "abstract_signature": "Uncertainty can select between adaptation mechanisms.", "source_work_ids": []},
            model_mode="efficient",
        )
        message = engine._v2_upsert_canonical(
            "takeaway_messages",
            "routing helps rare classes",
            {"title": "Routing helps rare classes", "message_text": "Under rare-class shift, routing prompts improves calibration.", "source_work_ids": []},
            model_mode="efficient",
        )
        engine.add_project_memberships(project["field_id"], "existed_ideas", [existed["canonical_id"]])
        engine.add_project_memberships(project["field_id"], "principles", [principle["principle_id"]])
        engine.add_project_memberships(project["field_id"], "takeaway_messages", [message["canonical_id"]])

        generated = engine.v2_generate_my_idea(
            field_id=project["field_id"],
            goal_text=project["goal_text"],
            selected_refs=[
                {"bucket": "existed_ideas", "id": existed["canonical_id"]},
                {"bucket": "principles", "id": principle["principle_id"]},
                {"bucket": "takeaway_messages", "id": message["canonical_id"]},
            ],
            user_note="Prioritize my own idea: let benchmark uncertainty decide between prompt tuning and retrieval.",
            model_mode="efficient",
        )
        detail = engine.v2_my_idea_detail(project["field_id"], generated["idea"]["idea_id"])

        self.assertTrue(generated["ok"])
        self.assertIn("benchmark uncertainty", generated["idea"]["user_note"])
        self.assertGreaterEqual(len(detail["related_existed_ideas"]), 1)
        self.assertGreaterEqual(len(detail["principle_map"]["nodes"]), 1)
        self.assertEqual(len(detail["source_evidence"]), 3)
        self.assertEqual(generated["idea"]["generation_mode"], "llm")

    def test_v2_generate_my_idea_requires_available_llm(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store, llm=NoLLM())  # type: ignore[arg-type]
        project = engine.create_project(name="Idea Project", goal_text="adaptive prompt routing")

        with self.assertRaisesRegex(RuntimeError, "no API key|not available"):
            engine.v2_generate_my_idea(
                field_id=project["field_id"],
                goal_text=project["goal_text"],
                selected_refs=[],
                user_note="Generate only if the selected LLM is callable.",
                model_mode="efficient",
            )

    def test_v2_related_idea_comparison_requires_llm_not_heuristic_fallback(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store, llm=NoLLM())  # type: ignore[arg-type]
        idea = {
            "idea_id": "MI-COMPARE",
            "title": "Benchmark-Uncertainty Prompt Router",
            "novelty_claim": "Route between prompt tuning and cache retrieval using benchmark-level uncertainty.",
            "mechanistic_design": ["Estimate uncertainty", "route between prompt tuning and retrieval", "report base-to-novel cost-normalized accuracy"],
            "user_note": "Focus on benchmark uncertainty and cost-normalized novel-class accuracy.",
        }
        existed = [
            {
                "canonical_id": "XI-PRIOR",
                "title": "Uncertainty-Gated Prompt Routing",
                "idea_text": "Use prediction uncertainty to route each sample between frozen CLIP prompts, learned prompt tuning, and retrieval-style cache evidence.",
                "mechanism": "Conditional routing preserves CLIP semantics unless uncertainty asks for adaptation.",
            }
        ]

        rows = engine._v2_related_existed_ideas(idea, existed, allow_heuristic=True)

        self.assertEqual(rows, [])

    def test_v2_related_comparison_accepts_qwen_style_comparison_phrasing(self) -> None:
        class QwenStyleComparisonLLM(FakeV2LLM):
            def chat_json(self, system: str, user: str, **kwargs):
                if "compare a generated research idea" in system:
                    return {
                        "rows": [
                            {
                                "id": "XI-PRIOR",
                                "mechanistic_similarity": "Both ideas use a diagnostic state to decide whether exemplar-derived reasoning structure should affect inference.",
                                "essential_difference": "Compared with uncertainty-gated routing, the new design extracts explicit logical patterns before spending long-chain reasoning tokens.",
                                "potential_advantage": "Compared with the prior router, the pattern extractor can improve accuracy per token when exemplars share a transferable proof skeleton.",
                                "potential_weakness": "Compared with the prior router, it can fail when the selected exemplar hides an incompatible rule behind similar surface wording.",
                            }
                        ]
                    }
                return super().chat_json(system, user, **kwargs)

        store = self.make_store()
        engine = PrincipiaEngine(store=store, llm=QwenStyleComparisonLLM())  # type: ignore[arg-type]
        idea = {
            "idea_id": "MI-QWEN",
            "title": "Logical Pattern Extraction Router",
            "one_sentence_thesis": "Extract exemplar-derived logical patterns only when a compatibility diagnostic predicts accuracy gain per token.",
            "novelty_claim": "Treat logical patterns as routed inference-time resources rather than fixed prompt decorations.",
            "mechanistic_design": ["score exemplar compatibility", "extract a compact logical pattern", "route pattern use by expected accuracy per token"],
        }
        existed = [
            {
                "canonical_id": "XI-PRIOR",
                "title": "Uncertainty-Gated Prompt Routing",
                "idea_text": "Use prediction uncertainty to route each sample between frozen prompts, learned prompt tuning, and retrieval-style evidence.",
                "mechanism": "Conditional routing preserves default reasoning unless uncertainty asks for intervention.",
            }
        ]

        rows = engine._v2_related_existed_ideas(idea, existed, model_mode="qwen_122b", limit=1)

        self.assertEqual(len(rows), 1)
        self.assertIn("Compared with", rows[0]["differences"])

    def test_v2_benchmark_and_baseline_payloads_use_public_dataset_and_method_links(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store, llm=NoLLM())  # type: ignore[arg-type]
        work = {"work_id": "W-LINKS", "title": "CLIP Work", "url_or_doi": "https://example.org/work", "venue_or_source": "local"}

        benchmark = engine._v2_benchmark_payload({"dataset": "ImageNet", "metric": "top-1 accuracy"}, work)
        baseline = engine._v2_baseline_payload({"baseline_name": "CoOp", "baseline_type": "published", "benchmark_id": "ImageNet"}, work, [])

        self.assertEqual(benchmark["official_url"], "https://www.image-net.org/")
        self.assertTrue(benchmark["public_dataset"])
        self.assertEqual(baseline["source_paper_link"], "https://arxiv.org/abs/2109.01134")
        self.assertEqual(baseline["official_code_url"], "https://github.com/KaiyangZhou/CoOp")

    def test_v2_project_tabs_are_scoped_and_delete_keeps_local_records_by_default(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store, llm=NoLLM())  # type: ignore[arg-type]
        left = engine.create_project(name="Left Project", goal_text="left")
        right = engine.create_project(name="Right Project", goal_text="right")
        left_idea = engine._v2_upsert_canonical(
            "existed_ideas",
            "left mechanism",
            {"title": "Left Mechanism", "idea_text": "Use left-specific routing to improve reasoning.", "source_work_ids": []},
            model_mode="efficient",
        )
        right_idea = engine._v2_upsert_canonical(
            "existed_ideas",
            "right mechanism",
            {"title": "Right Mechanism", "idea_text": "Use right-specific verification to improve reasoning.", "source_work_ids": []},
            model_mode="efficient",
        )
        engine.add_project_memberships(left["field_id"], "existed_ideas", [left_idea["canonical_id"]])
        engine.add_project_memberships(right["field_id"], "existed_ideas", [right_idea["canonical_id"]])

        left_tab = engine.build_v2_project_tab(left["field_id"], "existed_ideas")
        right_tab = engine.build_v2_project_tab(right["field_id"], "existed_ideas")

        self.assertEqual([item["title"] for item in left_tab["items"]], ["Left Mechanism"])
        self.assertEqual([item["title"] for item in right_tab["items"]], ["Right Mechanism"])

        deleted = engine.delete_project(left["field_id"])

        self.assertTrue(deleted["ok"])
        self.assertIsNone(store.get_item("field_profiles", left["field_id"]))
        self.assertEqual(engine.build_v2_project_tab(left["field_id"], "existed_ideas")["total"], 0)
        self.assertTrue(engine.v2_project_summary_or_deleted(left["field_id"])["project_deleted"])
        self.assertIsNotNone(store.get_item("existed_ideas", left_idea["canonical_id"]))
        self.assertIsNotNone(store.get_item("existed_ideas", right_idea["canonical_id"]))

        cleanup = engine.delete_project(right["field_id"], delete_orphan_records=True)

        self.assertTrue(cleanup["ok"])
        self.assertIsNone(store.get_item("existed_ideas", right_idea["canonical_id"]))

    def test_v2_list_projects_hides_default_and_clear_local_records_keeps_shells(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store, llm=NoLLM())  # type: ignore[arg-type]
        project = engine.create_project(name="Visible Project", goal_text="reasoning")
        work = engine._v2_upsert_work({"work_id": "W-CLEAR", "title": "Clearable Work", "abstract": "Evidence.", "year": 2025}, model_mode="metadata")
        idea = engine._v2_upsert_canonical("existed_ideas", "clearable idea", {"title": "Clearable Idea", "idea_text": "Use clearable evidence to test reasoning under a diagnostic.", "source_work_ids": [work["work_id"]]}, model_mode="efficient")
        engine.add_project_memberships(project["field_id"], "source_works", [work["work_id"]])
        engine.add_project_memberships(project["field_id"], "existed_ideas", [idea["canonical_id"]])

        projects = engine.list_projects()
        counts = projects[0]["counts"]
        cleared = engine.clear_local_records()

        self.assertEqual([item["field_id"] for item in projects], [project["field_id"]])
        self.assertEqual(counts["existed_ideas"], 1)
        self.assertEqual(counts["works"], 1)
        self.assertIsNotNone(store.get_item("field_profiles", project["field_id"]))
        self.assertEqual(store.counts()["source_works"], 0)
        self.assertEqual(store.counts()["existed_ideas"], 0)
        self.assertGreaterEqual(cleared["deleted"].get("project_memberships", 0), 1)

    def test_v2_works_tab_supports_show_more_and_sort_modes(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store, llm=NoLLM())  # type: ignore[arg-type]
        project = engine.create_project(name="Works Project", goal_text="logical exemplar reasoning")
        works = [
            {
                "work_id": "W-OLD-RELEVANT",
                "title": "Logical Exemplar Reasoning Patterns",
                "abstract": "A directly relevant work about logical exemplars and reasoning patterns.",
                "venue_or_source": "arXiv",
                "year": 2022,
                "updated_at": "2024-01-01T00:00:00Z",
            },
            {
                "work_id": "W-NEW",
                "title": "Fresh General Reasoning Survey",
                "abstract": "A broad reasoning survey.",
                "venue_or_source": "arXiv",
                "year": 2026,
                "updated_at": "2026-01-01T00:00:00Z",
            },
            {
                "work_id": "W-VENUE",
                "title": "Benchmark Transfer Notes",
                "abstract": "Evidence about reasoning transfer.",
                "venue_or_source": "NeurIPS",
                "year": 2023,
                "updated_at": "2025-01-01T00:00:00Z",
            },
        ]
        desired_updated_at = {item["work_id"]: item["updated_at"] for item in works}
        store.upsert_many("source_works", works, "work_id")
        with sqlite3.connect(store.path) as conn:
            for work in works:
                row = conn.execute("SELECT payload FROM records WHERE bucket = 'source_works' AND id = ?", (work["work_id"],)).fetchone()
                payload = json.loads(row[0])
                payload["updated_at"] = desired_updated_at[work["work_id"]]
                conn.execute(
                    "UPDATE records SET payload = ?, updated_at = ? WHERE bucket = 'source_works' AND id = ?",
                    (json.dumps(payload), desired_updated_at[work["work_id"]], work["work_id"]),
                )
        engine.add_project_memberships(project["field_id"], "source_works", [item["work_id"] for item in works])

        page = engine.build_v2_project_tab(project["field_id"], "works", limit=2, sort_mode="modified")
        relevant = engine.build_v2_project_tab(project["field_id"], "works", limit=3, sort_mode="relevance")
        composite = engine.build_v2_project_tab(project["field_id"], "works", limit=3, sort_mode="composite")

        self.assertEqual(page["total"], 3)
        self.assertTrue(page["has_more"])
        self.assertEqual(page["items"][0]["work_id"], "W-NEW")
        self.assertEqual(relevant["items"][0]["work_id"], "W-OLD-RELEVANT")
        self.assertEqual(composite["items"][0]["work_id"], "W-VENUE")

    def test_v2_existed_idea_title_is_mechanism_not_work_title(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store, llm=NoLLM())  # type: ignore[arg-type]
        work = engine._v2_upsert_work(
            {
                "work_id": "W-GEOMETRY",
                "title": "The Geometry of Reasoning: Flowing Logics in Representation Space",
                "abstract": "We introduce flow-constrained logic routing that separates rule selection from answer decoding during inference.",
                "venue_or_source": "arXiv",
                "year": 2026,
            },
            model_mode="metadata",
        )
        extracted = engine._v2_extract_concepts_from_work(
            "logical patterns in reasoning benchmarks",
            {**work, "transient_full_text": "We introduce flow-constrained logic routing that separates rule selection from answer decoding during inference."},
            {
                "existed_ideas": [
                    {
                        "title": work["title"],
                        "core_idea": "Flow-constrained logic routing separates rule selection from answer decoding so reasoning systems can control logical structure before producing final answers.",
                        "mechanism": "The mechanism routes candidate logic flows through a constrained representation space before answer decoding begins. Rule selection is treated as a separate control operation, which lets the system regulate reasoning structure independently from the final language generation step.",
                        "discussion": "This idea is useful because it isolates the reasoning-control step from answer surface form. It is most relevant for benchmarked reasoning systems where failures can come from choosing the wrong logical route rather than from decoding the final answer.",
                        "evidence": "The source work introduces flow-constrained logic routing and states that it separates rule selection from answer decoding during inference.",
                    }
                ]
            },
        )

        self.assertTrue(extracted["existed_ideas"])
        title = extracted["existed_ideas"][0]["title"]
        self.assertNotEqual(engine._v2_canonical_key(title), engine._v2_canonical_key(work["title"]))
        self.assertNotIn("uses source-backed evidence", extracted["existed_ideas"][0]["idea_text"].lower())

    def test_v2_baseline_aliases_merge_logic_lm_proposed_names(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store, llm=NoLLM())  # type: ignore[arg-type]
        work = engine._v2_upsert_work(
            {
                "work_id": "W-LOGIC-LM",
                "title": "Logic-LM: Empowering Large Language Models with Symbolic Solvers for Faithful Logical Reasoning",
                "abstract": "Logic-LM is evaluated on logical reasoning datasets.",
                "url_or_doi": "https://arxiv.org/abs/2305.12295",
                "venue_or_source": "ACL",
                "year": 2023,
            },
            model_mode="metadata",
        )
        first = engine._v2_upsert_canonical(
            "baseline_records",
            "Logic-LM: Empowering Large Language Models with Symbolic Solvers for Faithful Logical Reasoning",
            {"baseline_name": "Logic-LM: Empowering Large Language Models with Symbolic Solvers for Faithful Logical Reasoning", "source_work_ids": [work["work_id"]]},
            model_mode="efficient",
        )
        second = engine._v2_upsert_canonical(
            "baseline_records",
            "Logic-LM (Proposed)",
            {"baseline_name": "Logic-LM (Proposed)", "source_work_ids": [work["work_id"]]},
            model_mode="efficient",
        )

        self.assertEqual(first["baseline_id"], second["baseline_id"])
        self.assertEqual(store.counts()["baseline_records"], 1)

    def test_v2_publication_time_sort_uses_linked_work_year(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store, llm=NoLLM())  # type: ignore[arg-type]
        project = engine.create_project(name="Publication Sort", goal_text="reasoning")
        old_work = engine._v2_upsert_work({"work_id": "W-OLD", "title": "Old Reasoning Work", "abstract": "Old evidence.", "year": 2021}, model_mode="metadata")
        new_work = engine._v2_upsert_work({"work_id": "W-NEW", "title": "New Reasoning Work", "abstract": "New evidence.", "year": 2026}, model_mode="metadata")
        old_idea = engine._v2_upsert_canonical("existed_ideas", "old routing", {"title": "Old Routing", "idea_text": "Use old routing to improve reasoning under a diagnostic.", "source_work_ids": [old_work["work_id"]]}, model_mode="efficient")
        new_idea = engine._v2_upsert_canonical("existed_ideas", "new routing", {"title": "New Routing", "idea_text": "Use new routing to improve reasoning under a diagnostic.", "source_work_ids": [new_work["work_id"]]}, model_mode="efficient")
        engine.add_project_memberships(project["field_id"], "existed_ideas", [old_idea["canonical_id"], new_idea["canonical_id"]])

        page = engine.build_v2_project_tab(project["field_id"], "existed_ideas", sort_mode="work_year")

        self.assertEqual(page["items"][0]["canonical_id"], new_idea["canonical_id"])

    def test_v2_benchmark_tab_hides_non_official_benchmarks(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store, llm=NoLLM())  # type: ignore[arg-type]
        project = engine.create_project(name="Benchmark Project", goal_text="benchmark")
        official = engine._v2_upsert_canonical(
            "benchmark_records",
            "ImageNet",
            {"benchmark_name": "ImageNet", "dataset": "ImageNet", "metric": "accuracy"},
            model_mode="efficient",
        )
        vague = engine._v2_upsert_canonical(
            "benchmark_records",
            "internal reasoning benchmark",
            {"benchmark_name": "internal reasoning benchmark", "dataset": "internal reasoning benchmark", "metric": "score"},
            model_mode="efficient",
        )
        engine.add_project_memberships(project["field_id"], "benchmark_records", [official["benchmark_id"], vague["benchmark_id"]])

        tab = engine.build_v2_project_tab(project["field_id"], "benchmarks")

        self.assertEqual(tab["total"], 1)
        self.assertEqual(tab["items"][0]["benchmark_name"], "ImageNet")
        self.assertEqual(tab["items"][0]["official_url"], "https://www.image-net.org/")

    def test_reasoning_benchmark_catalog_keeps_public_downloadable_datasets(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store, llm=NoLLM())  # type: ignore[arg-type]
        project = engine.create_project(name="Reasoning Benchmarks", goal_text="logical pattern extraction during inference")
        for name in ["GSM8K", "MATH", "MMLU", "GPQA", "FOLIO", "ProofWriter", "LogiQA", "ReClor", "PrOntoQA", "ARC-Challenge", "BBH"]:
            item = engine._v2_upsert_canonical(
                "benchmark_records",
                name,
                {"benchmark_name": name, "dataset": name, "metric": "accuracy"},
                model_mode="efficient",
            )
            engine.add_project_memberships(project["field_id"], "benchmark_records", [item["benchmark_id"]])

        tab = engine.build_v2_project_tab(project["field_id"], "benchmarks", limit=20)
        names = {item["benchmark_name"] for item in tab["items"]}

        self.assertGreaterEqual(tab["total"], 10)
        self.assertIn("MATH", names)
        self.assertIn("FOLIO", names)
        self.assertIn("ProofWriter", names)
        self.assertTrue(all(item["official_url"] for item in tab["items"]))

    def test_v2_takeaway_repair_removes_template_titles(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store, llm=NoLLM())  # type: ignore[arg-type]
        item = engine._v2_upsert_canonical(
            "takeaway_messages",
            "bad template",
            {
                "title": "Use the source result as a reusable lesson for few-shot vision-language adaptation un",
                "message_text": "Use the source result as a reusable lesson for few-shot vision-language adaptation under distribution and resource constraints.",
                "evidence": "We show that base-to-novel transfer reveals prompt overfitting even when base-class accuracy improves.",
            },
            model_mode="efficient",
        )

        presented = engine._v2_present_item(item)

        self.assertNotIn("Use the source result", presented["title"])
        self.assertIn("base-to-novel", presented["message_text"].lower())

    def test_v2_concept_extraction_rejects_incomplete_paper_summary_frames(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store, llm=NoLLM())  # type: ignore[arg-type]
        work = {
            "work_id": "W-LOGIC-FRAME",
            "title": "Logic-LM",
            "abstract": "Logic-LM integrates language models with symbolic solvers.",
            "year": 2023,
        }
        extracted = engine._v2_extract_concepts_from_work(
            "logical pattern extraction during inference",
            work,
            {
                "existed_ideas": [
                    {
                        "title": "Logic-LM",
                        "idea_text": "This paper introduces a novel framework, Logic-LM, which integrates LLMs with symbolic solvers to improve logical problem-solving.",
                    }
                ],
                "principles": [
                    "This paper introduces a novel framework, Logic-LM, which integrates LLMs with symbolic solvers to improve logical problem-solving."
                ],
                "takeaway_messages": [
                    "This paper introduces a novel framework, Logic-LM, which integrates LLMs with symbolic solvers to improve logical problem-solving."
                ],
            },
        )
        self.assertEqual(extracted["existed_ideas"], [])
        self.assertEqual(extracted["principles"], [])
        self.assertEqual(extracted["takeaway_messages"], [])

    def test_v2_item_update_saves_manual_variant_for_baseline(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store, llm=NoLLM())  # type: ignore[arg-type]
        baseline = engine._v2_upsert_canonical(
            "baseline_records",
            "CoOp",
            {"baseline_name": "CoOp", "description": "Old summary", "principle": "Old principle"},
            model_mode="efficient",
        )

        updated = engine.v2_item_update(
            {
                "bucket": "baseline_records",
                "id": baseline["baseline_id"],
                "payload": {"description": "New user-edited summary", "principle": "New user-edited principle"},
            }
        )["item"]

        self.assertEqual(updated["description"], "New user-edited summary")
        self.assertEqual(updated["principle"], "New user-edited principle")
        self.assertTrue(updated["active_variant"]["is_user_edit"])

    def test_principle_relation_derivation_links_shared_structure(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)
        left_id = stable_id("P", "left")
        right_id = stable_id("P", "right")

        relations = engine._derive_principle_relations(
            [
                {
                    "principle_id": left_id,
                    "domain_tags": ["sparse-view", "3d-reconstruction"],
                    "relation_hints": ["shares_sparse_observation_pressure"],
                    "tradeoffs": ["prior strength vs hallucination risk"],
                },
                {
                    "principle_id": right_id,
                    "domain_tags": ["sparse-view", "3d-reconstruction"],
                    "relation_hints": ["shares_sparse_observation_pressure"],
                    "tradeoffs": ["prior strength vs hallucination risk"],
                },
            ]
        )

        self.assertEqual(len(relations), 1)
        self.assertEqual(relations[0]["relation_type"], "shares_sparse_observation_pressure")
        self.assertEqual(relations[0]["source_principle_id"], left_id)
        self.assertEqual(relations[0]["target_principle_id"], right_id)

    def test_observatory_buckets_store_structured_records(self) -> None:
        store = self.make_store()
        fact = to_dict(
            WorkFact(
                fact_id="WF-1",
                work_id="W-1",
                field_id="default",
                fact_type="insight",
                text="Nearest baselines are the decisive evidence surface.",
            )
        )
        benchmark = to_dict(
            BenchmarkRecord(
                benchmark_id="B-1",
                field_id="default",
                work_id="W-1",
                task="few-shot adaptation",
                dataset="ImageNet",
                split="base-to-novel",
                metric="accuracy",
                metric_direction="higher_is_better",
            )
        )
        baseline = to_dict(
            BaselineRecord(
                baseline_id="BL-1",
                field_id="default",
                work_id="W-1",
                benchmark_id="B-1",
                baseline_name="CoOp",
                baseline_type="published",
            )
        )
        result = to_dict(
            ResultRecord(
                result_id="RR-1",
                field_id="default",
                work_id="W-1",
                benchmark_id="B-1",
                method_name="candidate",
                metric="accuracy",
                value=83.4,
                value_text="accuracy 83.4%",
            )
        )

        store.upsert("work_facts", fact, "fact_id")
        store.upsert("benchmark_records", benchmark, "benchmark_id")
        store.upsert("baseline_records", baseline, "baseline_id")
        store.upsert("result_records", result, "result_id")

        self.assertEqual(store.get_item("work_facts", "WF-1")["fact_type"], "insight")
        self.assertEqual(store.get_item("benchmark_records", "B-1")["dataset"], "ImageNet")
        self.assertEqual(store.get_item("baseline_records", "BL-1")["baseline_name"], "CoOp")
        self.assertEqual(store.get_item("result_records", "RR-1")["value"], 83.4)

    def test_extract_work_facts_normalizes_legacy_work_fields(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)
        work = {
            "work_id": "W-FACT",
            "title": "Sparse-view uncertainty gating",
            "authors": [],
            "year": 2026,
            "venue_or_source": "local",
            "url_or_doi": "",
            "source_type": "note",
            "validation_level": "L1",
            "abstract": "Sparse-view reconstruction is underconstrained and often fails when priors hallucinate surfaces.",
            "work_principles": ["Gate priors by uncertainty before injecting them into sparse-view reconstruction."],
            "work_insights": ["Uncertainty should decide where a prior is allowed to act."],
            "work_novelty": ["The novelty is local prior gating rather than global regularization."],
        }

        facts = engine.extract_work_facts(engine._observatory_goal("sparse view"), work)
        second = engine.extract_work_facts(engine._observatory_goal("sparse view"), work)
        types = {fact["fact_type"] for fact in facts}

        self.assertIn("core_idea", types)
        self.assertIn("principle", types)
        self.assertIn("insight", types)
        self.assertIn("novelty", types)
        self.assertIn("failure_mode", types)
        self.assertEqual(len(facts), len(second))

    def test_benchmark_extraction_creates_matrix_records_from_abstract(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)
        goal = engine._observatory_goal("few-shot CLIP adaptation")
        work = {
            "work_id": "W-BENCH",
            "title": "Cost-aware CLIP adaptation",
            "authors": [],
            "year": 2026,
            "venue_or_source": "local",
            "url_or_doi": "https://github.com/example/clip-adapt",
            "source_type": "paper",
            "validation_level": "L2",
            "abstract": (
                "We evaluate on ImageNet and OxfordPets under a base-to-novel split. "
                "The method compares against zero-shot CLIP, CoOp, and Tip-Adapter. "
                "zero-shot CLIP reports top-1 accuracy 67.0%. CoOp reports top-1 accuracy 74.2%. Tip-Adapter reports top-1 accuracy 75.6%. "
                "The evaluated method reports top-1 accuracy 83.4% with GPU hours and latency accounting."
            ),
        }

        extracted = engine.extract_benchmark_records(goal, work)

        self.assertTrue(extracted["benchmark_records"])
        self.assertTrue(any(item["dataset"] == "ImageNet" for item in extracted["benchmark_records"]))
        self.assertTrue(any(item["baseline_name"] == "CoOp" for item in extracted["baseline_records"]))
        self.assertTrue(extracted["result_records"])
        self.assertTrue(any(item["result_quality"]["has_code"] for item in extracted["result_records"]))

    def test_library_benchmark_and_baseline_views_group_local_evidence(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)
        for idx in range(2):
            store.upsert(
                "source_works",
                {
                    "work_id": f"W-BM-{idx}",
                    "title": f"CLIP adaptation work {idx}",
                    "authors": [],
                    "year": 2026,
                    "venue_or_source": "local",
                    "url_or_doi": "",
                    "source_type": "paper",
                    "validation_level": "L1",
                    "abstract": "ImageNet base-to-novel accuracy with CoOp and zero-shot CLIP baselines.",
                },
                "work_id",
            )
            benchmark = to_dict(
                BenchmarkRecord(
                    benchmark_id=f"B-BM-{idx}",
                    field_id="default",
                    work_id=f"W-BM-{idx}",
                    task="few-shot CLIP adaptation",
                    dataset="ImageNet",
                    split="base-to-novel",
                    metric="accuracy",
                    metric_direction="higher_is_better",
                )
            )
            baseline = to_dict(
                BaselineRecord(
                    baseline_id=f"BL-BM-{idx}",
                    field_id="default",
                    work_id=f"W-BM-{idx}",
                    benchmark_id=f"B-BM-{idx}",
                    baseline_name="CoOp",
                    baseline_type="published",
                )
            )
            result = to_dict(
                ResultRecord(
                    result_id=f"RR-BM-{idx}",
                    field_id="default",
                    work_id=f"W-BM-{idx}",
                    benchmark_id=f"B-BM-{idx}",
                    method_name="CoOp",
                    baseline_id=f"BL-BM-{idx}",
                    metric="accuracy",
                    value=82.0 + idx,
                    value_text=f"{82.0 + idx:.1f}% top-1 accuracy",
                    unit="%",
                    code_url="https://github.com/KaiyangZhou/CoOp",
                )
            )
            store.upsert("benchmark_records", benchmark, "benchmark_id")
            store.upsert("baseline_records", baseline, "baseline_id")
            store.upsert("result_records", result, "result_id")

        benchmarks = engine.build_benchmark_view()
        baselines = engine.build_baseline_view()

        self.assertEqual(len(benchmarks["items"]), 1)
        grouped = benchmarks["items"][0]
        self.assertEqual(grouped["dataset"], "ImageNet")
        self.assertEqual(len(grouped["record_ids"]), 2)
        self.assertIn("1.2M training images", grouped["scale"])
        self.assertEqual(grouped["official_url"], "https://www.image-net.org/")
        self.assertEqual(grouped["baseline_count"], 1)
        self.assertTrue(any(item["method_name"] == "CoOp" for item in grouped["baseline_performance"]))

        self.assertEqual(len(baselines["items"]), 1)
        baseline = baselines["items"][0]
        self.assertEqual(baseline["baseline_name"], "CoOp")
        self.assertIn("continuous prompt vectors", baseline["description"])
        self.assertEqual(baseline["official_code_url"], "https://github.com/KaiyangZhou/CoOp")
        self.assertIn("ImageNet · accuracy", baseline["benchmarks"])

    def test_library_dashboard_gap_and_assistant_export_are_local(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)
        store.upsert(
            "source_works",
            {
                "work_id": "W-OBS",
                "title": "Principle observatory work",
                "authors": [],
                "year": 2026,
                "venue_or_source": "local",
                "url_or_doi": "",
                "source_type": "note",
                "validation_level": "L1",
                "abstract": "A method idea is evaluated qualitatively with no structured experimental evidence.",
                "work_principles": ["Turn local literature into reusable principle cards."],
                "work_insights": ["Local memory is the durable product layer."],
                "work_novelty": ["The novelty is feedback into the principle pool."],
            },
            "work_id",
        )
        store.upsert(
            "principles",
            {
                "principle_id": "P-OBS",
                "name": "Local principle memory",
                "mechanism": "Persist facts, principles, ideas, and feedback locally.",
                "abstract_signature": "local memory compounds research context",
                "problem_pressure": "Generic chats do not preserve field state.",
                "objective": "Make field progress auditable.",
                "assumptions": ["Users revisit the same field.", "Feedback can recalibrate principles."],
                "tradeoffs": ["structure vs extraction cost"],
                "failure_modes": ["weak source grounding"],
                "transfer_hooks": ["export a validation bundle"],
                "source_works": ["W-OBS"],
                "validation_level": "L1",
                "confidence_score": 0.51,
                "domain_tags": ["research-memory"],
            },
            "principle_id",
        )
        store.upsert(
            "ideas",
            {
                "idea_id": "I-OBS",
                "title": "Benchmark-aware field observatory",
                "one_sentence_thesis": "Expose missing benchmark and baseline evidence as first-class local gaps.",
                "research_goal_id": "G-OBS",
                "source_principles": ["P-OBS"],
                "baselines": [],
                "metrics": ["extraction coverage"],
                "feedback_status": "unvalidated",
            },
            "idea_id",
        )

        dashboard = engine.build_library_dashboard()
        gaps = engine.mine_gap_cards()
        bundle = engine.build_assistant_export_bundle("I-OBS")

        self.assertEqual(dashboard["counts"]["works"], 1)
        self.assertGreaterEqual(dashboard["coverage"]["core_idea"], 1.0)
        self.assertTrue(any(gap["gap_type"] in {"missing_benchmark", "missing_baseline"} for gap in gaps))
        self.assertEqual(bundle["idea"]["idea_id"], "I-OBS")
        self.assertEqual(bundle["principles"][0]["principle_id"], "P-OBS")
        self.assertIn("feedback_schema", bundle)

    def test_feedback_assimilation_updates_idea_and_principle_state(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)
        principle = {
            "principle_id": "P-FB",
            "name": "Feedback-calibrated principle",
            "mechanism": "Update confidence from local validation outcomes.",
            "abstract_signature": "feedback changes confidence",
            "problem_pressure": "Unvalidated ideas are overconfident.",
            "objective": "Keep the principle pool honest.",
            "assumptions": ["feedback is reliable"],
            "tradeoffs": ["confidence vs conservatism"],
            "failure_modes": [],
            "transfer_hooks": ["import feedback JSON"],
            "source_works": [],
            "validation_level": "L1",
            "confidence_score": 0.4,
            "domain_tags": ["feedback"],
        }
        idea = {
            "idea_id": "I-FB",
            "title": "Feedback import",
            "one_sentence_thesis": "Import coding-agent results into the local principle graph.",
            "research_goal_id": "G-FB",
            "source_principles": ["P-FB"],
            "feedback_status": "unvalidated",
        }
        store.upsert("principles", principle, "principle_id")
        store.upsert("ideas", idea, "idea_id")

        supported = engine.assimilate_feedback({"idea_id": "I-FB", "outcome_label": "supported", "metric_delta_observed": "+1.2 accuracy"})
        after_supported = store.get_item("principles", "P-FB")
        contradicted = engine.assimilate_feedback(
            {
                "idea_id": "I-FB",
                "outcome_label": "contradicted",
                "notes": "Nearest baseline already contains the mechanism.",
                "failure_modes": ["baseline stronger than expected"],
            }
        )
        implementation_failed = engine.assimilate_feedback(
            {
                "idea_id": "I-FB",
                "outcome_label": "implementation_failed",
                "notes": "The minimal implementation did not run.",
            }
        )
        after_all = store.get_item("principles", "P-FB")

        self.assertTrue(supported["ok"])
        self.assertTrue(contradicted["ok"])
        self.assertTrue(implementation_failed["ok"])
        self.assertEqual(store.get_item("ideas", "I-FB")["feedback_status"], "implementation_failed")
        self.assertEqual(after_supported["validation_level"], "L4")
        self.assertGreater(after_supported["confidence_score"], 0.4)
        self.assertLess(after_all["confidence_score"], after_supported["confidence_score"])
        self.assertIn("baseline stronger than expected", after_all["failure_modes"])

    def test_v1_schema_is_created_with_normalized_tables(self) -> None:
        store = self.make_store()
        expected = {
            "global_work",
            "work_version",
            "extraction_run",
            "concept_card",
            "concept_version",
            "evidence_link",
            "symbol_registry",
            "derivation_run",
            "derivation_node",
            "derivation_edge",
            "project_record_membership",
            "run_event",
            "embedding_index",
            "migration_status",
        }
        with sqlite3.connect(store.path) as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'virtual table')")}
        self.assertTrue(expected.issubset(tables))

    def test_v1_migration_maps_legacy_buckets_to_global_memory(self) -> None:
        store = self.make_store()
        store.upsert(
            "source_works",
            {
                "work_id": "W-LEG",
                "title": "Evidence-value routing for research agents",
                "abstract": "A paper about routing research actions by expected evidence value.",
                "year": 2026,
                "source_type": "paper",
                "validation_level": "L1",
            },
            "work_id",
        )
        store.upsert(
            "principles",
            {
                "principle_id": "P-LEG",
                "name": "Evidence-value routing",
                "mechanism": "Route scarce research budget toward actions with the highest expected evidence value.",
                "source_works": ["W-LEG"],
                "validation_level": "L1",
                "confidence_score": 0.7,
            },
            "principle_id",
        )
        engine = PrincipiaEngine(store=store)
        result = engine.migrate_to_v1_memory(project_id="PRJ-LEG")
        counts = engine.global_store.counts()

        self.assertTrue(result["ok"])
        self.assertGreaterEqual(counts["global_work"], 1)
        self.assertGreaterEqual(counts["work_version"], 1)
        self.assertGreaterEqual(counts["concept_card"], 1)
        self.assertGreaterEqual(counts["evidence_link"], 1)

    def test_v1_migration_keeps_missing_work_evidence_fk_safe(self) -> None:
        store = self.make_store()
        store.upsert(
            "existed_ideas",
            {
                "canonical_id": "XI-MISSING-WORK",
                "title": "Evidence-safe generated idea",
                "idea_text": "Use available concepts even when the referenced work is still being ingested.",
                "source_work_ids": ["W-MISSING"],
                "confidence_score": 0.5,
            },
            "canonical_id",
        )
        engine = PrincipiaEngine(store=store)

        result = engine.migrate_to_v1_memory(project_id="PRJ-FK")

        self.assertTrue(result["ok"])
        with sqlite3.connect(store.path) as conn:
            rows = conn.execute("SELECT work_id, evidence_span FROM evidence_link").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0][0])
        self.assertIn("referenced work", rows[0][1])

    def test_v1_work_identity_versioning_and_extraction_cache(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)
        first = engine.global_store.upsert_work(
            {
                "title": "Adaptive Routing for LLM Agents",
                "abstract": "Route compute by uncertainty.",
                "doi": "10.1234/example",
                "year": 2026,
            }
        )
        same = engine.global_store.upsert_work(
            {
                "title": "Adaptive Routing for LLM Agents",
                "abstract": "Route compute by uncertainty.",
                "doi": "10.1234/example",
                "year": 2026,
            }
        )
        changed = engine.global_store.upsert_work(
            {
                "title": "Adaptive Routing for LLM Agents",
                "abstract": "Route compute by uncertainty and expected evidence value.",
                "doi": "10.1234/example",
                "year": 2026,
            }
        )
        extraction_a = engine.global_store.ensure_extraction_run(
            first["work_id"],
            first["work_version_id"],
            llm_provider="fake",
            llm_model="model-a",
            model_mode="efficient",
            prompt_version="p1",
            schema_version="s1",
        )
        extraction_b = engine.global_store.ensure_extraction_run(
            first["work_id"],
            first["work_version_id"],
            llm_provider="fake",
            llm_model="model-a",
            model_mode="efficient",
            prompt_version="p1",
            schema_version="s1",
        )

        self.assertEqual(first["work_id"], same["work_id"])
        self.assertEqual(first["work_version_id"], same["work_version_id"])
        self.assertEqual(first["work_id"], changed["work_id"])
        self.assertNotEqual(first["work_version_id"], changed["work_version_id"])
        self.assertEqual(extraction_a["extraction_run_id"], extraction_b["extraction_run_id"])

    def test_v1_concept_retrieval_symbols_and_collision_handling(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)
        first = engine.global_store.upsert_concept(
            "principle",
            {
                "name": "Adaptive Token Routing",
                "mechanism": "Allocate token budget by uncertainty and marginal value.",
                "confidence_score": 0.8,
            },
            key_text="adaptive token routing",
            validation_level="evidence_supported",
            evidence=[{"evidence_span": "routing evidence"}],
        )
        second = engine.global_store.upsert_concept(
            "principle",
            {
                "name": "Adaptive Token Routing",
                "mechanism": "A different but nearby routing principle.",
                "confidence_score": 0.6,
            },
            key_text="adaptive token routing collision variant",
            validation_level="evidence_supported",
        )
        retrieval = engine.v1_retrieve_concepts("token routing uncertainty", concept_types=["principle"], limit_per_type=5)
        symbols = engine.v1_symbols_table(namespace="default")["items"]
        codes = [item["short_code"] for item in symbols]

        self.assertGreaterEqual(len(retrieval["results"]["principle"]), 1)
        self.assertGreaterEqual(len(symbols), 2)
        self.assertEqual(len(codes), len(set(codes)))
        self.assertTrue(first["concept_id"])
        self.assertTrue(second["concept_id"])

    def test_v1_derivation_verifier_and_offline_symbolic_generation(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store, llm=NoLLM())
        concept = engine.global_store.upsert_concept(
            "principle",
            {
                "name": "Evaluator-first binding",
                "mechanism": "Bind generation to the cheapest falsification signal.",
            },
            key_text="evaluator first binding",
            validation_level="evidence_supported",
        )
        result = engine.v1_symbolic_generate(
            field_id="default",
            goal_text="reduce API cost for research agents",
            selected_refs=[{"concept_id": concept["concept_id"]}],
            user_note="route retrieval only when evidence value is high",
            model_mode="efficient",
            offline=True,
        )
        lineage = engine.v1_idea_lineage(result["idea"]["idea_id"])

        self.assertTrue(result["ok"])
        self.assertEqual(result["generation_mode"], "principia_calculus")
        self.assertTrue(result["derived_nodes"])
        self.assertEqual(result["derived_nodes"][0]["verification_status"], "speculative_unverified")
        self.assertGreaterEqual(len(lineage["nodes"]), 2)

    def test_v1_online_symbolic_generation_requires_llm_and_does_not_template_fallback(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store, llm=NoLLM())
        with self.assertRaises(RuntimeError):
            engine.v1_symbolic_generate(
                field_id="default",
                goal_text="generate a symbolic idea without an LLM",
                selected_refs=[],
                user_note="",
                model_mode="efficient",
                offline=False,
            )
        self.assertEqual(store.counts()["my_ideas"], 0)

    def test_v1_standard_generation_saves_idea_when_related_comparison_fails(self) -> None:
        class ComparisonFailLLM(FakeV2LLM):
            def chat_json(self, system: str, user: str, **kwargs):
                if "compare a generated research idea" in system:
                    raise TimeoutError("timed out after 70s")
                return super().chat_json(system, user, **kwargs)

        store = self.make_store()
        engine = PrincipiaEngine(store=store, llm=ComparisonFailLLM())  # type: ignore[arg-type]
        project = engine.create_project(name="Generation Project", goal_text="logical pattern routing")
        idea = engine._v2_upsert_canonical(
            "existed_ideas",
            "compatibility probes",
            {"title": "Compatibility Probes", "idea_text": "Use compatibility probes to route reasoning patterns only when they transfer.", "source_work_ids": []},
            model_mode="efficient",
        )
        engine.add_project_memberships(project["field_id"], "existed_ideas", [idea["canonical_id"]])

        result = engine.v1_standard_generate(
            field_id=project["field_id"],
            goal_text=project["goal_text"],
            selected_refs=[{"bucket": "existed_ideas", "id": idea["canonical_id"]}],
            user_note="prioritize accuracy-token frontier",
            model_mode="efficient",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(store.counts()["my_ideas"], 1)
        self.assertIn("Trace-Conditioned", result["idea"]["title"])

    def test_v1_symbolic_generation_normalizes_llm_patch_schema_variants(self) -> None:
        class SymbolicSchemaVariantLLM(FakeV2LLM):
            def chat_json(self, system: str, user: str, **kwargs):
                if "Principia Calculus" in system:
                    return {
                        "new_nodes": [
                            {
                                "id": "N1",
                                "type": "hypothesis",
                                "summary": "Gate logical-pattern extraction by a verifier that predicts transfer before spending long-chain tokens.",
                            }
                        ],
                        "new_edges": [],
                        "candidate_ideas": [
                            {
                                "title": "Verifier-Gated Pattern Extraction",
                                "one_sentence_thesis": "Use a verifier to decide when exemplar-derived logical patterns deserve inference-time token budget.",
                                "novelty_claim": "The verifier turns logical-pattern extraction into a conditional inference-time operator rather than a fixed prompt expansion.",
                                "mechanistic_design": ["Build a compatibility verifier over selected exemplar-pattern evidence.", "Spend pattern-extraction tokens only when the verifier predicts transfer."],
                                "why_it_might_work": ["The gate prevents incompatible exemplar logic from consuming budget."],
                                "validation_protocol": ["Compare verifier-gated extraction against direct chain-of-thought at equal token budgets."],
                                "relevant_baselines": ["chain-of-thought", "self-consistency"],
                                "metrics": ["accuracy per token", "tokens per correct answer"],
                                "risks": ["The verifier may reject rare but useful exemplar structures."],
                                "derived_principles": ["Inference-time logical pattern extraction should be gated by predicted transfer value."],
                            }
                        ],
                    }
                return super().chat_json(system, user, **kwargs)

        store = self.make_store()
        engine = PrincipiaEngine(store=store, llm=SymbolicSchemaVariantLLM())  # type: ignore[arg-type]
        concept = engine.global_store.upsert_concept(
            "principle",
            {"name": "Pattern transfer gating", "mechanism": "Gate pattern reuse by compatibility evidence."},
            key_text="pattern transfer gating",
            validation_level="evidence_supported",
        )

        result = engine.v1_symbolic_generate(
            field_id="default",
            goal_text="improve reasoning accuracy-token frontier",
            selected_refs=[{"concept_id": concept["concept_id"]}],
            user_note="avoid spending tokens on incompatible exemplar logic",
            model_mode="efficient",
            offline=False,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["generation_mode"], "principia_calculus")
        self.assertEqual(result["derived_nodes"][0]["concept_type"], "hypothesis")
        self.assertTrue(result["concept_idea"]["payload"]["derived_from"])
        self.assertEqual(len(result["idea"]["selected_refs"]), 1)
        self.assertEqual(len(result["idea"]["derived_principles"]), 1)
        self.assertNotEqual(result["idea"]["novelty_claim"], "Generated through Principia Calculus over selected evidence symbols.")

    def test_v1_symbolic_lineage_repairs_duplicate_nodes_and_hides_unused_sources(self) -> None:
        class DuplicateNodeLLM(FakeV2LLM):
            def chat_json(self, system: str, user: str, **kwargs):
                if "Principia Calculus" in system:
                    symbols = re.findall(r'"symbol":\s*"([^"]+)"', user)
                    first = symbols[0]
                    second = symbols[1]
                    return {
                        "new_nodes": [
                            {
                                "symbol": "N1",
                                "node_type": "derived_concept",
                                "summary": "Transfer exemplar logic only after a diagnostic predicts reusable structure.",
                                "support_symbols": [first],
                            },
                            {
                                "symbol": "N2",
                                "node_type": "derived_concept",
                                "summary": "Transfer exemplar logic only after a diagnostic predicts reusable structure.",
                                "support_symbols": [second],
                            },
                        ],
                        "new_edges": [],
                        "candidate_ideas": [
                            {
                                "symbol": "I1",
                                "title": "Diagnostic-Gated Logical Pattern Transfer",
                                "derived_from": ["N1", "N2"],
                                "one_sentence_thesis": "Gate logical-pattern transfer with diagnostics that separate reusable exemplar structure from misleading surface overlap.",
                                "novelty_claim": "The idea links exemplar selection and token budget through verified symbolic lineage instead of applying every exemplar trace.",
                                "mechanistic_design": ["score exemplar compatibility", "derive compact pattern rules", "spend reasoning tokens only on supported rules"],
                                "why_it_might_work": ["The derivation isolates when source patterns should influence the target problem."],
                                "validation_protocol": ["Compare against chain-of-thought and self-consistency at equal token budgets."],
                                "relevant_baselines": ["Chain-of-Thought", "self-consistency"],
                                "metrics": ["accuracy per token", "tokens per correct answer"],
                                "risks": ["The diagnostic can miss rare transferable structures."],
                                "derived_principles": ["Pattern transfer should be conditional on diagnostic support."],
                                "cheapest_falsification": "Run a two-benchmark ablation with and without the compatibility diagnostic.",
                            }
                        ],
                    }
                return super().chat_json(system, user, **kwargs)

        store = self.make_store()
        engine = PrincipiaEngine(store=store, llm=DuplicateNodeLLM())  # type: ignore[arg-type]
        first = engine.global_store.upsert_concept("principle", {"name": "Compatibility gate", "mechanism": "Gate exemplar reuse by transfer evidence."}, key_text="compatibility gate")
        second = engine.global_store.upsert_concept("existed_idea", {"title": "Token budget routing", "summary": "Route long reasoning only when it can repay the token cost."}, key_text="token budget routing")
        unused = engine.global_store.upsert_concept("principle", {"name": "Unused audit rule", "mechanism": "This source is selected but not used by the patch."}, key_text="unused audit rule")

        result = engine.v1_symbolic_generate(
            field_id="default",
            goal_text="improve reasoning accuracy-token frontier",
            selected_refs=[
                {"concept_id": first["concept_id"]},
                {"concept_id": second["concept_id"]},
                {"concept_id": unused["concept_id"]},
            ],
            user_note="diagnostic-gated pattern transfer",
            model_mode="efficient",
            offline=False,
        )
        lineage = engine.v1_idea_lineage(result["idea"]["idea_id"])
        derived_summaries = [node["summary"] for node in lineage["nodes"] if node["type"] == "derived_concept"]
        visible_concepts = {node.get("concept_id") for node in lineage["nodes"]}

        self.assertEqual(len(derived_summaries), len(set(derived_summaries)))
        self.assertNotIn(unused["concept_id"], visible_concepts)
        self.assertTrue(all(edge["source"] and edge["target"] for edge in lineage["edges"]))

    def test_v1_related_comparison_can_be_generated_without_regenerating_idea(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store, llm=FakeV2LLM())  # type: ignore[arg-type]
        project = engine.create_project(name="Comparison Project", goal_text="logical pattern routing")
        prior = engine._v2_upsert_canonical(
            "existed_ideas",
            "diagnostic routing",
            {
                "title": "Diagnostic Routing",
                "idea_text": "Use a diagnostic state to decide whether to spend adaptation compute.",
                "mechanism": "Route intervention by uncertainty.",
            },
            model_mode="efficient",
        )
        engine.add_project_memberships(project["field_id"], "existed_ideas", [prior["canonical_id"]])
        idea_payload = {
            "field_id": project["field_id"],
            "title": "Pattern Router",
            "one_sentence_thesis": "Route logical-pattern extraction by a compatibility probe.",
            "novelty_claim": "Logical patterns become a measured inference-time resource.",
            "mechanistic_design": ["Probe compatibility.", "Route extraction by expected accuracy per token."],
            "selected_refs": [],
            "derived_principles": ["Only extract exemplar logic when transfer is predicted."],
        }
        stored = engine._v2_store_my_idea_version({}, idea_payload, model_mode="efficient")
        store.upsert("my_ideas", stored, "idea_id")
        engine.add_project_memberships(project["field_id"], "my_ideas", [stored["idea_id"]])

        result = engine.v2_generate_related_comparison(
            field_id=project["field_id"],
            idea_id=stored["idea_id"],
            model_mode="efficient",
        )
        refreshed = store.get_item("my_ideas", stored["idea_id"])

        self.assertTrue(result["ok"])
        self.assertEqual(result["idea"]["title"], "Pattern Router")
        self.assertGreaterEqual(len(result["related_existed_ideas"]), 1)
        self.assertGreaterEqual(len(refreshed.get("related_existed_ideas", [])), 1)

    def test_v1_related_comparison_reports_provider_timeout_reason(self) -> None:
        class TimeoutComparisonLLM(FakeV2LLM):
            def chat_json(self, system: str, user: str, **kwargs):
                if "compare a generated research idea" in system:
                    raise TimeoutError("timed out after 140s")
                return super().chat_json(system, user, **kwargs)

        store = self.make_store()
        engine = PrincipiaEngine(store=store, llm=TimeoutComparisonLLM())  # type: ignore[arg-type]
        project = engine.create_project(name="Timeout Comparison", goal_text="logical pattern routing")
        prior = engine._v2_upsert_canonical(
            "existed_ideas",
            "diagnostic routing",
            {"title": "Diagnostic Routing", "idea_text": "Use a diagnostic state to decide whether to spend adaptation compute."},
            model_mode="efficient",
        )
        engine.add_project_memberships(project["field_id"], "existed_ideas", [prior["canonical_id"]])
        stored = engine._v2_store_my_idea_version(
            {},
            {
                "field_id": project["field_id"],
                "title": "Pattern Router",
                "one_sentence_thesis": "Route logical-pattern extraction by a compatibility probe.",
                "novelty_claim": "Logical patterns become a measured inference-time resource.",
                "mechanistic_design": ["Probe compatibility.", "Route extraction by expected accuracy per token."],
            },
            model_mode="efficient",
        )
        store.upsert("my_ideas", stored, "idea_id")
        engine.add_project_memberships(project["field_id"], "my_ideas", [stored["idea_id"]])

        with self.assertRaisesRegex(RuntimeError, "could not generate.*provider did not finish"):
            engine.v2_generate_related_comparison(
                field_id=project["field_id"],
                idea_id=stored["idea_id"],
                model_mode="qwen_122b",
            )

    def test_principle_map_hides_existing_principles_without_edges(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store, llm=FakeV2LLM())  # type: ignore[arg-type]
        idea = {
            "idea_id": "MI-MAP",
            "title": "Alpha Gate",
            "one_sentence_thesis": "Alpha beta controller.",
            "novelty_claim": "Alpha beta controller.",
            "mechanistic_design": ["Alpha beta control."],
            "derived_principles": ["Alpha beta transfer gate."],
        }
        unrelated = [
            {
                "principle_id": "P-UNRELATED",
                "name": "Geometric sparse reconstruction",
                "abstract_signature": "Camera pose recovery with multi-view depth priors.",
                "mechanism": "Fuse epipolar constraints and Gaussian splats.",
            }
        ]
        graph = engine._v2_principle_map(idea, unrelated, related=[])

        self.assertEqual([node["type"] for node in graph["nodes"]], ["new_principle"])
        self.assertEqual(graph["edges"], [])

    def test_v1_run_cancellation_marks_run_and_blocks_late_save(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)
        store.upsert(
            "research_runs",
            {
                "run_id": "RUN-CANCEL",
                "field_id": "default",
                "status": "running",
                "stage": "llm_generation",
                "message": "Running",
            },
            "run_id",
        )
        result = engine.cancel_run("RUN-CANCEL")

        self.assertTrue(result["ok"])
        self.assertTrue(engine._is_run_cancelled("RUN-CANCEL"))
        self.assertEqual(store.get_item("research_runs", "RUN-CANCEL")["status"], "cancelled")

    def test_v2_quality_gate_rejects_quote_fragments_and_pdf_artifacts(self) -> None:
        engine = PrincipiaEngine(store=self.make_store())

        self.assertFalse(
            engine._v2_is_high_quality_concept(
                "Thus, alignment becomes a system-level objective that must hold under delegation and communication.",
                kind="principle",
            )
        )
        self.assertFalse(
            engine._v2_is_high_quality_concept(
                "Figure 1 summarizes this pipeline: filter for efficiency-revealing questions and compare token cost.",
                kind="principle",
            )
        )
        self.assertFalse(
            engine._v2_is_high_quality_concept(
                "open, hardware-agnostic benchmark that jointly measures accuracy and token efficiency",
                kind="idea",
            )
        )
        self.assertEqual(engine._normalize_pdf_text("multi-step reason- ing ob- jective"), "multi-step reasoning objective")

    def test_v2_missing_existed_idea_triggers_targeted_recovery(self) -> None:
        class MissingIdeaThenRecoverLLM(FakeV2LLM):
            def chat_json(self, system: str, user: str, **kwargs):
                if "extract nontrivial research structures" in system:
                    work_id = re.search(r'"work_id":\s*"([^"]+)"', user).group(1)
                    return {
                        "works": [
                            {
                                "work_id": work_id,
                                "existed_ideas": [],
                                "principles": [
                                    {
                                        "name": "Compatibility-gated rule transfer",
                                        "argument": "When exemplar-derived rules are evaluated under heterogeneous reasoning tasks, transfer should be gated by a compatibility signal before changing the inference path.",
                                        "abstract_signature": "When exemplar-derived rules are evaluated under heterogeneous reasoning tasks, transfer should be gated by a compatibility signal before changing the inference path.",
                                        "evidence": "PatternGate routes exemplar logic through a compatibility signal before applying it to heterogeneous reasoning tasks.",
                                        "discussion": "This principle is grounded in the source mechanism because the work separates rule extraction from the decision to use the extracted rule. It applies when exemplar rules are useful only for a subset of task instances and token budget makes unconditional transfer expensive.",
                                    }
                                ],
                                "takeaway_messages": [
                                    {
                                        "title": "Compatibility gating improves transfer control",
                                        "main_results": "Under heterogeneous reasoning benchmarks, rule transfer is more reliable when a compatibility signal filters exemplar patterns before inference uses them.",
                                        "message_text": "Under heterogeneous reasoning benchmarks, rule transfer is more reliable when a compatibility signal filters exemplar patterns before inference uses them.",
                                        "condition": "The result applies to reasoning tasks where exemplars contain reusable logical rules but not every rule transfers to every instance. It assumes the system can compute a compatibility signal before spending long reasoning tokens.",
                                        "discussion": "The lesson is useful because it turns exemplar reuse into a controlled selection problem. It should be applied with matched token budgets so gains cannot be explained only by longer prompts.",
                                        "evidence": "PatternGate evaluates exemplar-rule routing on heterogeneous reasoning benchmarks with a compatibility signal.",
                                    }
                                ],
                                "benchmarks": [],
                                "baselines": [],
                            }
                        ]
                    }
                if "recover missing high-quality Principia extraction records" in system:
                    work_id = re.search(r'"work_id":\s*"([^"]+)"', user).group(1)
                    return {
                        "works": [
                            {
                                "work_id": work_id,
                                "existed_ideas": [
                                    {
                                        "title": "Compatibility-gated exemplar rule transfer",
                                        "core_idea": "PatternGate uses a compatibility signal to decide whether an exemplar-derived logical rule should modify the active inference path for a target reasoning instance.",
                                        "idea_text": "PatternGate uses a compatibility signal to decide whether an exemplar-derived logical rule should modify the active inference path for a target reasoning instance.",
                                        "mechanism": "The method first extracts a compact logical rule from an exemplar and represents it separately from the target problem. A compatibility scorer then compares the rule with the target instance and permits the inference system to use the rule only when the score indicates likely transfer under the benchmark condition.",
                                        "discussion": "The idea is valuable because it makes exemplar reuse conditional rather than automatic, which directly addresses cases where irrelevant exemplars consume tokens or introduce wrong reasoning structure. It is most useful for heterogeneous reasoning suites where different tasks require different latent rules and the system must protect the accuracy-token frontier.",
                                        "evidence": "PatternGate routes exemplar logic through a compatibility signal before applying it to heterogeneous reasoning tasks.",
                                    }
                                ],
                                "principles": [],
                                "takeaway_messages": [],
                                "benchmarks": [],
                                "baselines": [],
                            }
                        ]
                    }
                return super().chat_json(system, user, **kwargs)

        engine = PrincipiaEngine(store=self.make_store(), llm=MissingIdeaThenRecoverLLM())  # type: ignore[arg-type]
        result = engine._v2_llm_extract_batch(
            "improve logical reasoning accuracy-token frontier",
            [
                {
                    "work_id": "W-PG",
                    "title": "PatternGate: Compatibility-Gated Exemplar Rule Transfer",
                    "abstract": "PatternGate routes exemplar logic through a compatibility signal before applying it to heterogeneous reasoning tasks.",
                    "transient_full_text": "PatternGate routes exemplar logic through a compatibility signal before applying it to heterogeneous reasoning tasks. The method extracts compact logical rules from exemplars, scores compatibility with target instances, and applies the rule only when benchmark evidence supports transfer.",
                }
            ],
            model_mode="efficient",
        )

        self.assertEqual(len(result["W-PG"]["existed_ideas"]), 1)
        self.assertIn("compatibility signal", result["W-PG"]["existed_ideas"][0]["core_idea"].lower())

    def test_v2_baseline_contract_requires_official_method_performance_and_discussion(self) -> None:
        engine = PrincipiaEngine(store=self.make_store())
        work = {
            "work_id": "W-BL",
            "title": "PatternGate for Reasoning Benchmarks",
            "abstract": "PatternGate compares against Chain-of-Thought on GSM8K and reports exact-match accuracy.",
        }

        bad_payload = engine._v2_baseline_payload(
            {
                "baseline_name": "ablation",
                "description": "ablation was extracted from local source evidence",
                "benchmarks": ["GSM8K"],
                "performance": [{"benchmark_name": "GSM8K", "metric": "accuracy", "value_text": "accuracy 72.1%"}],
            },
            work,
            [],
        )
        self.assertFalse(engine._is_supported_baseline_record(bad_payload, work, bad_payload.get("performance")))

        proposed_payload = engine._v2_baseline_payload(
            {
                "baseline_name": "PatternGate",
                "baseline_type": "proposed_method",
                "core_idea": "PatternGate routes exemplar-derived logical rules through a compatibility scorer before inference uses them.",
                "methodology": "The method extracts compact logical rules from exemplars and applies a compatibility scorer before modifying the inference path. It then runs the selected rule under the same benchmark split and metric as the compared methods.",
                "discussion": "The proposed method should be represented as the evaluated method rather than as a baseline. Keeping it out of baseline records prevents comparisons from double-counting the source work as its own competing method.",
                "benchmarks": ["GSM8K"],
                "performance": [{"benchmark_name": "GSM8K", "metric": "exact match", "value_text": "Exact-match accuracy is 78.4% on GSM8K."}],
            },
            work,
            [],
        )
        self.assertFalse(engine._is_supported_baseline_record(proposed_payload, work, proposed_payload.get("performance")))

        good_payload = engine._v2_baseline_payload(
            {
                "baseline_name": "Chain-of-Thought",
                "baseline_type": "compared_method",
                "core_idea": "Chain-of-Thought prompting elicits intermediate reasoning steps before the answer so the model can expose a serial solution path.",
                "methodology": "The baseline prompts the model to write intermediate reasoning before producing the final answer. It is evaluated on the same GSM8K split and exact-match metric as PatternGate so the comparison isolates whether compatibility-gated rule transfer improves over a standard explicit-trace prompt.",
                "discussion": "This baseline is meaningful because it tests whether explicit reasoning traces alone explain the reported gains. The comparison is only valid when token budgets, model choice, benchmark split, and scoring protocol are held fixed across the baseline and the evaluated method.",
                "benchmarks": ["GSM8K"],
                "performance": [{"benchmark_name": "GSM8K", "metric": "exact match", "value_text": "Exact-match accuracy is 72.1% on GSM8K."}],
                "evidence": "The experiment compares PatternGate against Chain-of-Thought on GSM8K using exact-match accuracy.",
            },
            work,
            [],
        )
        self.assertTrue(engine._is_supported_baseline_record(good_payload, work, good_payload.get("performance")))

    def test_v2_cleanup_merges_argument_duplicates_with_pdf_noise(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)
        store.upsert(
            "source_works",
            {
                "work_id": "W1",
                "title": "ARCANE Tool-Use Reasoning",
                "abstract": "ARCANE routes multi-step reasoning through explicit tool-use checkpoints when tasks require compositional evidence gathering.",
            },
            "work_id",
        )
        store.upsert(
            "source_works",
            {
                "work_id": "W2",
                "title": "ARCANE Tool-Use Reasoning Update",
                "abstract": "ARCANE routes multi-step reasoning through explicit tool-use checkpoints when tasks require compositional evidence gathering.",
            },
            "work_id",
        )
        first = {
            "canonical_id": "XI-DUP-A",
            "canonical_key": "old-a",
            "title": "ARCANE Tool-Use Reasoning",
            "core_idea": "ARCANE routes multi-step reasoning through explicit tool-use checkpoints when tasks require compositional evidence gathering.",
            "idea_text": "ARCANE routes multi-step reasoning through explicit tool-use checkpoints when tasks require compositional evidence gathering.",
            "mechanism": "The method inserts explicit tool-use checkpoints into a multi-step reasoning trajectory before accepting gathered evidence as sufficient. Each checkpoint forces the system to decide whether the next tool call is needed for compositional evidence gathering.",
            "discussion": "This idea is useful because tool use becomes a controlled reasoning step rather than an unconstrained action stream. It is most relevant when multi-step tasks require external evidence that must be gathered and verified across several operations.",
            "evidence": "ARCANE routes multi-step reasoning through explicit tool-use checkpoints when tasks require compositional evidence gathering.",
            "confidence_score": 0.7,
            "source_work_ids": ["W1"],
        }
        second = {
            "canonical_id": "XI-DUP-B",
            "canonical_key": "old-b",
            "title": "Arcane Challenging Tool Use",
            "core_idea": "ARCANE routes multi-step reason- ing through explicit tool-use checkpoints when tasks require compositional evidence gathering.",
            "idea_text": "ARCANE routes multi-step reason- ing through explicit tool-use checkpoints when tasks require compositional evidence gathering.",
            "mechanism": "The method inserts explicit tool-use checkpoints into a multi-step reasoning trajectory before accepting gathered evidence as sufficient. Each checkpoint forces the system to decide whether the next tool call is needed for compositional evidence gathering.",
            "discussion": "This idea is useful because tool use becomes a controlled reasoning step rather than an unconstrained action stream. It is most relevant when multi-step tasks require external evidence that must be gathered and verified across several operations.",
            "evidence": "ARCANE routes multi-step reasoning through explicit tool-use checkpoints when tasks require compositional evidence gathering.",
            "confidence_score": 0.6,
            "source_work_ids": ["W2"],
        }
        store.upsert("existed_ideas", first, "canonical_id")
        store.upsert("existed_ideas", second, "canonical_id")

        result = engine.cleanup_local_records()
        rows = store.list_items("existed_ideas", limit=20)

        self.assertEqual(len(rows), 1)
        self.assertGreaterEqual(result["repaired"]["merged_duplicates"], 1)
        self.assertEqual(sorted(rows[0]["source_work_ids"]), ["W1", "W2"])

    def test_v1_symbolic_generation_accepts_higher_order_derived_supports(self) -> None:
        class HigherOrderSymbolicLLM(FakeV2LLM):
            def chat_json(self, system: str, user: str, **kwargs):
                if "Principia Calculus" in system:
                    symbols = re.findall(r'"symbol":\s*"([^"]+)"', user)
                    first, second = symbols[0], symbols[1]
                    return {
                        "new_nodes": [
                            {
                                "symbol": "D1",
                                "node_type": "derived_concept",
                                "expression": f"compose({first})",
                                "summary": "Extract a compact compatibility signal from source evidence before spending long-form reasoning tokens.",
                                "support_symbols": [first],
                                "speculation_depth": 1,
                            },
                            {
                                "symbol": "D2",
                                "node_type": "hypothesis",
                                "expression": f"compose(D1, {second})",
                                "summary": "Bind the compatibility signal to benchmark pressure so the controller can reject misleading exemplar patterns.",
                                "support_symbols": ["D1", second],
                                "speculation_depth": 2,
                            },
                            {
                                "symbol": "D3",
                                "node_type": "idea_seed",
                                "expression": "specialize(D2)",
                                "summary": "Turn the benchmark-bound signal into an inference-time policy that updates logical patterns only when expected accuracy per token improves.",
                                "support_symbols": ["D2"],
                                "speculation_depth": 3,
                            },
                        ],
                        "new_edges": [],
                        "candidate_ideas": [
                            {
                                "symbol": "I1",
                                "title": "Benchmark-Bound Logical Pattern Controller",
                                "derived_from": ["D3"],
                                "one_sentence_thesis": "Use a benchmark-bound compatibility controller to decide when exemplar-derived logical patterns should modify inference-time reasoning.",
                                "novelty_claim": "The controller treats logical-pattern extraction as a measured policy update rather than an unconditional prompt expansion.",
                                "mechanistic_design": [
                                    "Represent each exemplar as p=(s,m,e), where s is a symbolic pattern, m is a mechanism tag, and e is source evidence.",
                                    "Compute value V(p,x)=Pr(correct|p,x)-lambda*tokens(p) for target query x; lambda is the token-cost penalty.",
                                    "Update the active pattern set only when max_p V(p,x) exceeds a calibrated no-update threshold.",
                                ],
                                "method_variants": [
                                    "Use a learned compatibility classifier instead of the value equation when calibration data is available.",
                                    "Use a conservative threshold variant that updates only after two independent evidence symbols agree.",
                                ],
                                "why_it_might_work": ["The derivation separates pattern discovery from the decision to spend tokens on it."],
                                "validation_protocol": ["Compare against chain-of-thought and self-consistency at equal token budgets."],
                                "relevant_baselines": ["Chain-of-Thought", "self-consistency"],
                                "metrics": ["accuracy per token", "tokens per correct answer"],
                                "risks": ["The compatibility signal may under-select rare transferable patterns."],
                                "derived_principles": ["Logical-pattern transfer should be gated by expected accuracy gain per token."],
                                "cheapest_falsification": "Run a small equal-budget ablation with and without the compatibility controller.",
                            }
                        ],
                    }
                return super().chat_json(system, user, **kwargs)

        store = self.make_store()
        engine = PrincipiaEngine(store=store, llm=HigherOrderSymbolicLLM())  # type: ignore[arg-type]
        c1 = engine.global_store.upsert_concept("principle", {"name": "Compatibility gating", "mechanism": "Gate transfer by compatibility."}, key_text="compatibility gating")
        c2 = engine.global_store.upsert_concept("principle", {"name": "Benchmark pressure", "mechanism": "Bind generation to benchmark pressure."}, key_text="benchmark pressure")

        result = engine.v1_symbolic_generate(
            field_id="default",
            goal_text="improve reasoning accuracy-token frontier",
            selected_refs=[{"concept_id": c1["concept_id"]}, {"concept_id": c2["concept_id"]}],
            user_note="prefer multi-step symbolic derivation",
            model_mode="efficient",
        )
        lineage = engine.v1_idea_lineage(result["idea"]["idea_id"])
        depths = {node["label"]: int(node.get("speculation_depth") or 0) for node in lineage["nodes"]}

        self.assertTrue(result["ok"])
        self.assertIn("method_variants", result["idea"])
        self.assertGreaterEqual(max(depths.values()), 4)
        self.assertTrue(any(edge["source"].endswith("D1") or "D1" in edge["source"] for edge in lineage["edges"]) or any(node["label"] == "D2" for node in lineage["nodes"]))

    def test_my_idea_markdown_export_includes_variants_and_lineage(self) -> None:
        store = self.make_store()
        engine = PrincipiaEngine(store=store)
        project = engine.create_project(name="Export Project", goal_text="logical pattern transfer")
        stored = engine._v2_store_my_idea_version(
            {},
            {
                "field_id": project["field_id"],
                "title": "Pattern Controller",
                "one_sentence_thesis": "Route logical-pattern extraction by expected value.",
                "novelty_claim": "Pattern extraction becomes a budgeted policy update.",
                "mechanistic_design": ["Compute V(p,x)=gain(p,x)-lambda*tokens(p)."],
                "method_variants": ["Classifier-gated variant.", "Two-signal conservative variant."],
                "validation_protocol": ["Equal-token ablation."],
            },
            model_mode="efficient",
        )
        store.upsert("my_ideas", stored, "idea_id")
        engine.add_project_memberships(project["field_id"], "my_ideas", [stored["idea_id"]])

        filename, body, content_type = engine.export_my_idea_markdown(project["field_id"], stored["idea_id"], model_mode="efficient")
        text = body.decode("utf-8")

        self.assertTrue(filename.endswith(".md"))
        self.assertIn("text/markdown", content_type)
        self.assertIn("## Method Variants", text)
        self.assertIn("Classifier-gated variant", text)


if __name__ == "__main__":
    unittest.main()
