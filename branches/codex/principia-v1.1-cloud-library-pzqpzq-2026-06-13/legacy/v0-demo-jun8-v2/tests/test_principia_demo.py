from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader

import principia_demo.engine as engine_module
from principia_demo.arxiv import build_arxiv_queries, fallback_seed_work
from principia_demo.config import get_settings
from principia_demo.engine import PrincipiaEngine
from principia_demo.llm_client import LLMClient
from principia_demo.models import BaselineRecord, BenchmarkRecord, FieldProfile, ResultRecord, WorkFact, to_dict
from principia_demo.storage import Store
from principia_demo.utils import enrich_query, stable_id


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

    def chat_json(self, system: str, user: str, **kwargs):
        if "extract nontrivial research structures" in system:
            work_ids = re.findall(r'"work_id":\s*"([^"]+)"', user)
            return {
                "works": [
                    {
                        "work_id": work_id,
                        "existed_ideas": [
                            {
                                "title": "Benchmark-conditioned prompt routing",
                                "idea_text": "Use benchmark uncertainty to decide whether a reasoning exemplar should update the active logical pattern.",
                                "mechanism": "Condition pattern extraction on uncertainty and task family.",
                                "evidence": "LLM extraction fixture.",
                            }
                        ],
                        "principles": [
                            {
                                "name": "Uncertainty-gated pattern transfer",
                                "abstract_signature": "Transfer a logical pattern only when uncertainty identifies a compatible reasoning pressure.",
                                "mechanism": "Gate pattern reuse by task uncertainty and exemplar compatibility.",
                                "boundary_conditions": ["reasoning tasks with exemplar traces"],
                                "evidence": "LLM extraction fixture.",
                            }
                        ],
                        "takeaway_messages": [
                            {
                                "title": "Pattern reuse needs a compatibility test",
                                "message_text": "Logical patterns improve reasoning only when the exemplar family matches the target inference pressure.",
                                "condition": "test-time exemplar reuse",
                                "finding": "compatibility matters more than raw exemplar count",
                                "actionable_lesson": "Measure when extracted patterns transfer before spending more tokens.",
                                "evidence": "LLM extraction fixture.",
                            }
                        ],
                        "benchmarks": [],
                        "baselines": [],
                    }
                    for work_id in work_ids
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


class PrincipiaDemoTests(unittest.TestCase):
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
        self.assertIn("Qwen3.6-35B-A3B", client.choose_model(mode="qwen_35b"))
        self.assertIn("Qwen3.5-122B-A10B", client.choose_model(mode="qwen_122b"))
        self.assertIn("GLM-5.1", client.choose_model(mode="glm"))
        self.assertEqual(client.choose_model(mode="openai_gpt5_pro"), "gpt-5-pro")
        self.assertEqual(client.choose_model(mode="openai_gpt52_pro"), "gpt-5.2-pro")
        self.assertEqual(client.choose_model(mode="openai_gpt55"), "gpt-5.5")
        self.assertEqual(client.choose_model(mode="openai_gpt55_pro_20260423"), "gpt-5.5-pro-2026-04-23")
        self.assertEqual(client.choose_model(mode="model:custom/ExactModel"), "custom/ExactModel")

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
                "Tip-Adapter, and TPT. It reports top-1 accuracy 83.4% with GPU hours and latency accounting."
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
        self.assertTrue(proposed)
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
                "It reports accuracy 77.2% and latency 18ms."
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
            "abstract": "We evaluate on ImageNet and OxfordPets with CoOp and zero-shot CLIP baselines, reporting top-1 accuracy 81.2%.",
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
                    "Benchmark experiments evaluate ImageNet, Caltech101, and OxfordPets against CoOp, CoCoOp, and MaPLe with accuracy 75%."
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

    def test_v2_project_tabs_are_scoped_and_delete_removes_orphan_records(self) -> None:
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
        self.assertIsNone(store.get_item("existed_ideas", left_idea["canonical_id"]))
        self.assertIsNotNone(store.get_item("existed_ideas", right_idea["canonical_id"]))

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
                "It reports top-1 accuracy 83.4% with GPU hours and latency accounting."
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


if __name__ == "__main__":
    unittest.main()
