from __future__ import annotations

import random
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import textwrap
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from .arxiv import fallback_seed_work, search_arxiv
from .llm_client import LLMClient
from .research_sources import search_hybrid_sources
from .models import (
    AssistantExport,
    BaselineRecord,
    BenchmarkRecord,
    FeedbackEvent,
    FieldProfile,
    GapCard,
    IdeaCard,
    PrincipleCard,
    PromptPlan,
    PromptStep,
    ProjectMembership,
    ResearchGoal,
    ResultEstimate,
    ResultRecord,
    WorkFact,
    to_dict,
    utc_now,
)
from .storage import BUCKETS, Store
from .utils import (
    clamp,
    compact_text,
    enrich_query,
    keyword_terms,
    lexical_score,
    query_expansions,
    sentence_split,
    slugify,
    stable_id,
    validation_number,
)


OPERATORS = [
    "principle_transfer",
    "assumption_inversion",
    "contradiction_resolution",
    "mechanism_composition",
    "failure_mode_transplant",
    "evaluator_binding",
]

RICH_PRINCIPLE_FIELDS = {
    "principle_type",
    "abstract_signature",
    "objective",
    "scarce_resources",
    "feedback_loop",
    "validation_notes",
    "domain_tags",
    "relation_hints",
}


class CancelledRun(RuntimeError):
    """Raised when a user cancels a long-running LLM workflow."""


class PrincipiaEngine:
    def __init__(self, store: Store | None = None, llm: LLMClient | None = None):
        self.store = store or Store()
        self.llm = llm or LLMClient()
        self._cancelled_runs: set[str] = set()

    def cancel_run(self, run_id: str) -> dict[str, Any]:
        run_id = str(run_id or "").strip()
        if not run_id:
            raise ValueError("Missing run_id")
        self._cancelled_runs.add(run_id)
        run = self.store.get_item("research_runs", run_id) or {"run_id": run_id}
        if run.get("status") not in {"complete", "error", "cancelled"}:
            run = {
                **run,
                "status": "cancelled",
                "stage": "cancelled",
                "message": "Cancelled by user. Any late LLM response will be ignored.",
                "completed_at": utc_now(),
                "updated_at": utc_now(),
            }
            self.store.upsert("research_runs", run, "run_id")
        return {"ok": True, "run": run}

    def _is_run_cancelled(self, run_id: str) -> bool:
        if not run_id:
            return False
        run = self.store.get_item("research_runs", run_id)
        return run_id in self._cancelled_runs or bool(run and run.get("status") == "cancelled")

    def _raise_if_cancelled(self, run_id: str) -> None:
        if self._is_run_cancelled(run_id):
            raise CancelledRun("Cancelled by user.")

    def _mark_run_cancelled(self, run: dict[str, Any]) -> dict[str, Any]:
        run["status"] = "cancelled"
        run["stage"] = "cancelled"
        run["message"] = "Cancelled by user. No further LLM results were saved."
        run["completed_at"] = utc_now()
        run["updated_at"] = utc_now()
        self.store.upsert("research_runs", run, "run_id")
        self._cancelled_runs.add(str(run.get("run_id") or ""))
        return run


    def formalize_goal(
        self,
        query: str,
        constraints: dict[str, str] | None = None,
        *,
        offline: bool = False,
        model_mode: str = "auto",
    ) -> dict[str, Any]:
        constraints = constraints or {}
        complexity = self._complexity(query, constraints)
        query_kind = self._detect_query_kind(query)
        if self.llm.available() and not offline:
            try:
                data = self.llm.chat_json(
                    "You convert rough research requests into typed Principia ResearchGoal JSON.",
                    (
                        "Return strict JSON with keys: target_domain, contribution_type, "
                        "success_metrics, search_terms, complexity, query_kind, idea_draft. query_kind is "
                        "\"task\" or \"idea_draft\". contribution_type and "
                        "success_metrics and search_terms must be arrays. complexity is 0.0-1.0. "
                        "If the user gives a concrete method/hypothesis/algorithm draft, preserve it in idea_draft "
                        "and extract search terms for related work and stress tests. "
                        f"User query: {query}\nConstraints: {constraints}"
                    ),
                    complexity=complexity,
                    mode=model_mode,
                    max_tokens=900,
                    temperature=0.1,
                )
                goal = ResearchGoal(
                    goal_id=stable_id("G", query, str(constraints), str(data.get("query_kind") or query_kind)),
                    raw_query=query,
                    target_domain=str(data.get("target_domain") or "AI research"),
                    contribution_type=list(data.get("contribution_type") or ["method", "evaluation"]),
                    success_metrics=list(
                        data.get("success_metrics")
                        or ["task success at fixed budget", "time to first validation signal"]
                    ),
                    constraints={
                        "compute_budget": constraints.get("compute_budget", "unrestricted demo default"),
                        "timeline": constraints.get("timeline", "open"),
                        "privacy_mode": constraints.get("privacy_mode", "local only"),
                        "target_venue": constraints.get("target_venue", "workshop or open-source demo"),
                    },
                    search_terms=list(data.get("search_terms") or keyword_terms(query, 6)),
                    complexity=clamp(float(data.get("complexity", complexity)), 0.0, 1.0),
                    query_kind=str(data.get("query_kind") or query_kind),
                    idea_draft=str(data.get("idea_draft") or (query if query_kind == "idea_draft" else "")),
                )
                self.store.upsert("goals", to_dict(goal), "goal_id")
                return to_dict(goal)
            except Exception:
                pass
        goal = self._fallback_goal(query, constraints, complexity)
        self.store.upsert("goals", to_dict(goal), "goal_id")
        return to_dict(goal)

    def ingest_principles(
        self,
        query: str,
        *,
        max_works: int = 6,
        constraints: dict[str, str] | None = None,
        offline: bool = False,
        model_mode: str = "auto",
        persist: bool = True,
        bypass_cache: bool = False,
        exclude_work_ids: set[str] | None = None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
        progress_found_offset: int = 0,
        progress_target: int | None = None,
        refresh_existing: bool = False,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        goal = self.formalize_goal(query, constraints, offline=offline, model_mode=model_mode)
        cached = self.store.search_principles(
            query,
            top_k=self._principle_search_k(max(3, max_works), model_mode),
            min_validation="L0",
        )
        cached = self._filter_model_version(cached, model_mode)
        cached = self._filter_domain_compatible_principles(goal, cached)
        strong_cached = [
            item
            for item in cached
            if item.get("_lexical_score", 0) >= 0.25 and self._is_rich_principle(item)
        ]
        if not bypass_cache and len(strong_cached) >= max(3, min(max_works, 4)):
            relations = self._derive_principle_relations(strong_cached)
            if relations:
                self.store.upsert_many("principle_relations", relations, "relation_id")
            return {
                "goal": goal,
                "source_works": [],
                "principles": strong_cached,
                "principle_relations": relations,
                "from_cache": True,
                "costs": self.llm.costs.calls,
            }

        works = self._collect_works(
            goal,
            max_works=max_works,
            offline=offline,
            exclude_work_ids=exclude_work_ids,
            progress_callback=progress_callback,
            progress_found_offset=progress_found_offset,
            progress_target=progress_target or max_works,
        )
        works = self._filter_domain_compatible_works(
            goal,
            [self._enrich_work_record(goal, work) for work in works],
        )
        works_to_mine = works
        refreshing_work_ids: set[str] = set()
        if refresh_existing:
            rich_work_ids = self._rich_principle_work_ids(model_mode=model_mode)
            works_to_mine = []
            for work in works:
                wid = work.get("work_id", "")
                local = self.store.get_item("source_works", wid) if wid else None
                is_stale = self._work_needs_refresh(work, local)
                if local and is_stale:
                    refreshing_work_ids.add(wid)
                if force_refresh or is_stale or wid not in rich_work_ids:
                    works_to_mine.append(work)
        mining_message = (
            f"Mining principles from {len(works_to_mine)} updated or unseen works."
            if works_to_mine
            else "Online search finished; selected works are already current locally."
        )
        self._emit_progress(
            progress_callback,
            "mining_principles",
            progress_found_offset + len(works),
            progress_target or max_works,
            mining_message,
        )
        if persist:
            self.store.upsert_many("source_works", works, "work_id")
            self.store.delete_principle_links_for_works(refreshing_work_ids)
        principles = self._mine_principles(goal, works_to_mine, offline=offline, model_mode=model_mode) if works_to_mine else []
        principles = [self._attach_principle_metadata(principle, goal, model_mode, offline) for principle in principles]
        principles = self._filter_domain_compatible_principles(goal, principles)
        saved = self.store.merge_principles(principles) if persist and principles else principles
        if refresh_existing and persist:
            relevant = [
                principle
                for principle in self.store.search_principles(
                    query,
                    top_k=self._principle_search_k(max(6, max_works * 3), model_mode),
                    min_validation="L0",
                )
                if self._is_rich_principle(principle)
            ]
            relevant = self._filter_model_version(relevant, model_mode)
            relevant = self._filter_domain_compatible_principles(goal, relevant)
            saved = self._dedupe_principles([*saved, *relevant])
        relations = self._derive_principle_relations(saved)
        if persist and relations:
            self.store.upsert_many("principle_relations", relations, "relation_id")
        if persist:
            run_id = stable_id("R", goal["goal_id"], "ingest", utc_now())
            self.store.upsert(
                "runs",
                {
                    "run_id": run_id,
                    "type": "ingest",
                    "goal_id": goal["goal_id"],
                    "query": query,
                    "work_ids": [work["work_id"] for work in works],
                    "principle_ids": [principle["principle_id"] for principle in saved],
                    "relation_ids": [relation["relation_id"] for relation in relations],
                    "created_at": utc_now(),
                },
                "run_id",
            )
        return {
            "goal": goal,
            "source_works": works,
            "principles": saved,
            "principle_relations": relations,
            "from_cache": False,
            "persisted": persist,
            "costs": self.llm.costs.calls,
        }

    def generate_ideas(
        self,
        query: str,
        *,
        max_ideas: int = 4,
        max_works: int = 6,
        min_validation: str = "L0",
        constraints: dict[str, str] | None = None,
        offline: bool = False,
        model_mode: str = "auto",
        source_mode: str = "online",
        paper_count: int | None = None,
        persist_sources: bool = True,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
        force_refresh: bool = False,
        language: str = "en",
        create_project: bool = False,
        project_name: str = "",
    ) -> dict[str, Any]:
        goal = self.formalize_goal(query, constraints, offline=offline, model_mode=model_mode)
        source_mode = source_mode if source_mode in {"online", "local"} else "online"
        work_target = max(1, int(paper_count or max_works or 6))
        principle_top_k = max(8, max_ideas * 3)
        principles = [
            principle
            for principle in self.store.search_principles(
                query,
                top_k=self._principle_search_k(principle_top_k, model_mode),
                min_validation=min_validation,
            )
            if self._is_rich_principle(principle)
        ]
        principles = self._filter_model_version(principles, model_mode)
        principles = self._filter_domain_compatible_principles(goal, principles)
        source_works: list[dict[str, Any]] = self._works_for_principles(principles)
        from_cache = False
        if source_mode == "local":
            if not principles:
                raise RuntimeError("Local mode found no matching local principles. Switch to online mode to mine papers first.")
            from_cache = True
        else:
            local_works = self._filter_domain_compatible_works(
                goal,
                self.store.search_works(query, top_k=max(work_target * 3, work_target)),
            )[:work_target]
            self._emit_progress(
                progress_callback,
                "local_pool",
                len(local_works),
                work_target,
                f"Found {len(local_works)} matching local works for this query.",
            )
            if not offline:
                ingest = self.ingest_principles(
                    query,
                    max_works=work_target,
                    constraints=constraints,
                    offline=False,
                    model_mode=model_mode,
                    persist=persist_sources,
                    bypass_cache=True,
                    progress_callback=progress_callback,
                    progress_target=work_target,
                    refresh_existing=True,
                    force_refresh=force_refresh,
                )
                source_works = self._filter_domain_compatible_works(
                    goal,
                    self._dedupe_works([*ingest.get("source_works", []), *local_works]),
                )[:work_target]
                if persist_sources:
                    principles = [
                        principle
                        for principle in self.store.search_principles(
                            query,
                            top_k=self._principle_search_k(principle_top_k, model_mode),
                            min_validation=min_validation,
                        )
                        if self._is_rich_principle(principle)
                    ]
                    principles = self._filter_model_version(principles, model_mode)
                    principles = self._filter_domain_compatible_principles(goal, principles)
                else:
                    principles = self._dedupe_principles([*ingest.get("principles", []), *principles])
                    principles = self._filter_domain_compatible_principles(goal, principles)
                if not principles:
                    principles = ingest["principles"]
            else:
                local_ready = len(local_works) >= work_target and len(principles) >= max(2, min(max_ideas, 4))
                if local_ready:
                    source_works = local_works[:work_target]
                    from_cache = True
                else:
                    if local_works and len(principles) < max(2, min(max_ideas, 4)):
                        source_works = local_works[:work_target]
                        self._emit_progress(
                            progress_callback,
                            "mining_principles",
                            len(source_works),
                            work_target,
                            f"Mining {model_mode} principles from {len(source_works)} relevant local works.",
                        )
                        mined = self._mine_principles(goal, source_works, offline=True, model_mode=model_mode)
                        mined = [self._attach_principle_metadata(principle, goal, model_mode, True) for principle in mined]
                        if persist_sources and mined:
                            self.store.merge_principles(mined)
                            principles = [
                                principle
                                for principle in self.store.search_principles(
                                    query,
                                    top_k=self._principle_search_k(principle_top_k, model_mode),
                                    min_validation=min_validation,
                                )
                                if self._is_rich_principle(principle)
                            ]
                            principles = self._filter_model_version(principles, model_mode)
                            principles = self._filter_domain_compatible_principles(goal, principles)
                        else:
                            principles = self._dedupe_principles([*mined, *principles])
                            principles = self._filter_domain_compatible_principles(goal, principles)
                    remaining = max(1, work_target - len(local_works))
                    ingest = self.ingest_principles(
                        query,
                        max_works=remaining,
                        constraints=constraints,
                        offline=True,
                        model_mode=model_mode,
                        persist=persist_sources,
                        bypass_cache=True,
                        exclude_work_ids={work["work_id"] for work in local_works},
                        progress_callback=progress_callback,
                        progress_found_offset=len(local_works),
                        progress_target=work_target,
                    )
                    source_works = self._filter_domain_compatible_works(
                        goal,
                        self._dedupe_works([*source_works, *local_works, *ingest.get("source_works", [])]),
                    )[:work_target]
                    if persist_sources:
                        principles = [
                            principle
                            for principle in self.store.search_principles(
                                query,
                                top_k=self._principle_search_k(principle_top_k, model_mode),
                                min_validation=min_validation,
                            )
                            if self._is_rich_principle(principle)
                        ]
                        principles = self._filter_model_version(principles, model_mode)
                        principles = self._filter_domain_compatible_principles(goal, principles)
                    else:
                        principles = self._dedupe_principles([*ingest.get("principles", []), *principles])
                        principles = self._filter_domain_compatible_principles(goal, principles)
                    if not principles:
                        principles = ingest["principles"]
        if len(principles) < 2 and source_mode != "local":
            ingest = self.ingest_principles(
                query,
                max_works=work_target,
                constraints=constraints,
                offline=offline,
                model_mode=model_mode,
                persist=persist_sources,
                bypass_cache=True,
                exclude_work_ids={work["work_id"] for work in source_works},
                progress_callback=progress_callback,
                progress_found_offset=len(source_works),
                progress_target=work_target,
                refresh_existing=not offline,
                force_refresh=force_refresh,
            )
            principles = [
                principle
                for principle in self.store.search_principles(
                    query,
                    top_k=self._principle_search_k(principle_top_k, model_mode),
                    min_validation=min_validation,
                )
                if self._is_rich_principle(principle)
            ]
            principles = self._filter_model_version(principles, model_mode)
            principles = self._filter_domain_compatible_principles(goal, principles)
            if not principles:
                principles = ingest["principles"]
                principles = self._filter_domain_compatible_principles(goal, principles)
            source_works = self._filter_domain_compatible_works(
                goal,
                self._dedupe_works([*source_works, *ingest.get("source_works", [])]),
            )[:work_target]

        curation = self._curate_materials(
            goal,
            source_works,
            principles,
            max_ideas=max_ideas,
            offline=offline,
            model_mode=model_mode,
        )
        curated_principles = curation["principles"]
        curated_works = curation["source_works"]
        self._emit_progress(
            progress_callback,
            "curating_materials",
            len(curated_works),
            max(len(source_works), 1),
            f"Curated {len(curated_works)} works, {len(curated_principles)} principles, "
            f"{len(curation['insights'])} insights, and {len(curation['novelty'])} novelty facts.",
        )

        ideas, estimates, plans = self._synthesize_ideas(
            goal,
            curated_principles,
            max_ideas=max_ideas,
            offline=offline,
            model_mode=model_mode,
            curation=curation,
        )
        ideas = [self._attach_idea_metadata(idea, goal, model_mode, offline) for idea in ideas]
        if str(language).lower().startswith("zh"):
            self._emit_progress(
                progress_callback,
                "translating_results",
                len(curated_works),
                work_target,
                "Translating English records into polished Chinese display variants.",
            )
            curated_works, curated_principles, ideas = self._ensure_chinese_language_variants(
                goal,
                curated_works,
                curated_principles,
                ideas,
                offline=offline,
                model_mode=model_mode,
            )
        self._emit_progress(
            progress_callback,
            "generating_ideas",
            len(curated_works),
            work_target,
            f"Generating {max_ideas} ideas from a curated insight brief.",
        )
        self._attach_similar_idea_ids(ideas)
        relations = self._derive_principle_relations(curated_principles)
        if persist_sources and relations:
            self.store.upsert_many("principle_relations", relations, "relation_id")
        persist_outputs = persist_sources or source_mode == "local"
        if persist_outputs:
            self.store.upsert_many("source_works", curated_works, "work_id")
            self.store.upsert_many("principles", curated_principles, "principle_id")
            self.store.upsert_many("estimates", estimates, "estimate_id")
            self.store.upsert_many("prompt_plans", plans, "prompt_plan_id")
            self.store.upsert_many("ideas", ideas, "idea_id")
            self.store.touch_usage(
                {
                    "source_works": [work["work_id"] for work in curated_works],
                    "principles": [principle["principle_id"] for principle in curated_principles],
                    "ideas": [idea["idea_id"] for idea in ideas],
                }
            )
        run_id = stable_id("R", goal["goal_id"], "generate", utc_now())
        project = None
        if persist_outputs:
            self.store.upsert(
                "runs",
                {
                    "run_id": run_id,
                    "type": "generate",
                    "mode": source_mode,
                    "goal_id": goal["goal_id"],
                    "query": query,
                    "work_ids": [work["work_id"] for work in curated_works],
                    "principle_ids": [principle["principle_id"] for principle in curated_principles],
                    "relation_ids": [relation["relation_id"] for relation in relations],
                    "idea_ids": [idea["idea_id"] for idea in ideas],
                    "curation": curation.get("brief", {}),
                    "created_at": utc_now(),
                },
                "run_id",
            )
            if create_project:
                project = self.create_project_from_result(
                    goal,
                    curated_works,
                    curated_principles,
                    ideas,
                    query=query,
                    name=project_name,
                )
        return {
            "goal": goal,
            "source_mode": source_mode,
            "source_works": curated_works,
            "principles": curated_principles,
            "curation": curation,
            "principle_relations": relations,
            "ideas": ideas,
            "estimates": estimates,
            "prompt_plans": plans,
            "graph": (
                self.build_graph(query=query, idea_ids=[idea["idea_id"] for idea in ideas])
                if persist_outputs
                else self._build_transient_graph(curated_works, curated_principles, ideas, relations)
            ),
            "from_cache": from_cache,
            "persisted": persist_outputs,
            "project": project,
            "costs": self.llm.costs.calls,
        }

    def export_report(
        self,
        query: str,
        *,
        language: str = "en",
        model_mode: str = "auto",
        fmt: str = "markdown",
        top_k: int = 12,
    ) -> tuple[str, bytes, str]:
        data = self.store.snapshot(limit_per_bucket=None)
        principles = self._filter_model_version(
            [
                principle
                for principle in self.store.search_principles(
                    query,
                    top_k=self._principle_search_k(top_k, model_mode),
                    min_validation="L0",
                )
                if self._is_rich_principle(principle)
            ],
            model_mode,
        )
        goal = to_dict(self._fallback_goal(query, {}, self._complexity(query, {})))
        principles = self._filter_domain_compatible_principles(goal, principles)
        goal_ids = {
            goal_id
            for goal_id, item in data.get("goals", {}).items()
            if item.get("raw_query") == query
        }
        ideas = [
            idea
            for idea in data.get("ideas", {}).values()
            if (model_mode == "auto" or idea.get("model_mode") == model_mode)
            and self._is_domain_compatible(goal, idea)
            and (
                idea.get("research_goal_id") in goal_ids
                or lexical_score(query, self._material_text(idea)) >= 0.18
            )
        ][-top_k:]
        works = self._filter_domain_compatible_works(goal, self._works_for_principles(principles))
        idea_work_ids = {
            wid
            for idea in ideas
            for wid in self._idea_source_work_ids(
                idea,
                [principle for principle in principles if principle.get("principle_id") in set(idea.get("source_principles", []))],
            )
        }
        works = self._dedupe_works([*works, *[data.get("source_works", {}).get(wid) for wid in idea_work_ids if data.get("source_works", {}).get(wid)]])
        principles = self.repair_language_variants_many(principles)
        ideas = self.repair_language_variants_many(ideas)
        works = self.repair_language_variants_many(works)
        library = {
            "work_facts": list(data.get("work_facts", {}).values()),
            "benchmark_records": list(data.get("benchmark_records", {}).values()),
            "baseline_records": list(data.get("baseline_records", {}).values()),
            "result_records": list(data.get("result_records", {}).values()),
            "estimates": data.get("estimates", {}),
            "prompt_plans": data.get("prompt_plans", {}),
            "source_works": data.get("source_works", {}),
            "principles": data.get("principles", {}),
        }
        md = self._render_report_markdown(query, principles, ideas, works, library=library, language=language, model_mode=model_mode)
        stem = slugify(query)[:64] or "principia-report"
        if fmt == "pdf":
            return f"{stem}.pdf", self._markdown_to_simple_pdf(md), "application/pdf"
        return f"{stem}.md", md.encode("utf-8"), "text/markdown; charset=utf-8"

    def list_projects(self) -> list[dict[str, Any]]:
        data = self.store.snapshot(limit_per_bucket=None)
        profiles = list(data.get("field_profiles", {}).values())
        if not any(item.get("field_id") == "default" for item in profiles):
            profiles.insert(
                0,
                to_dict(
                    FieldProfile(
                        field_id="default",
                        name="All Local Records",
                        description="Global local pool across all projects.",
                        display_order=-1,
                    )
                ),
            )
        rows = []
        for profile in profiles:
            if profile.get("archived"):
                continue
            field_id = profile.get("field_id", "default")
            row = dict(profile)
            row.setdefault("goal_text", row.get("query", ""))
            row.setdefault("settings", {})
            row.setdefault("display_order", 0)
            row.setdefault("refresh_status", "idle")
            row["counts"] = self.project_counts(data, field_id)
            rows.append(row)
        rows.sort(
            key=lambda item: (
                item.get("field_id") == "default",
                int(item.get("display_order", 0) or 0),
                item.get("created_at", ""),
            )
        )
        return rows

    def create_project(
        self,
        *,
        name: str,
        query: str = "",
        description: str = "",
        field_id: str = "",
        goal_text: str = "",
        settings: dict[str, Any] | None = None,
        display_order: int | None = None,
    ) -> dict[str, Any]:
        field_id = field_id or stable_id("PRJ", name, query or utc_now())
        if display_order is None:
            existing_orders = [
                int(item.get("display_order", 0) or 0)
                for item in self.store.list_items("field_profiles", limit=10000)
                if item.get("field_id") != "default"
            ]
            display_order = (max(existing_orders) + 1) if existing_orders else 0
        profile = FieldProfile(
            field_id=field_id,
            name=name or "Untitled Project",
            description=description,
            query=query,
            goal_text=goal_text or query,
            settings=settings or {},
            display_order=display_order,
            domain_tags=keyword_terms(query or name, 8),
        )
        payload = to_dict(profile)
        payload.setdefault("work_ids", [])
        payload.setdefault("principle_ids", [])
        payload.setdefault("idea_ids", [])
        self.store.upsert("field_profiles", payload, "field_id")
        return payload

    def update_project(self, field_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        if field_id == "default":
            raise ValueError("The default project cannot be edited.")
        profile = self.store.get_item("field_profiles", field_id)
        if not profile:
            raise KeyError(f"field_profiles:{field_id} not found")
        for key in ("name", "description", "query", "goal_text", "refresh_status", "last_refresh_at"):
            if key in updates:
                profile[key] = str(updates.get(key) or "")
        if "display_order" in updates:
            profile["display_order"] = int(updates.get("display_order") or 0)
        if "archived" in updates:
            profile["archived"] = bool(updates.get("archived"))
        if "settings" in updates and isinstance(updates["settings"], dict):
            profile["settings"] = dict(updates["settings"])
        for key in ("work_ids", "principle_ids", "idea_ids"):
            if key in updates and isinstance(updates[key], list):
                profile[key] = self._ordered_unique([str(item) for item in updates[key] if item])
        profile["updated_at"] = utc_now()
        self.store.upsert("field_profiles", profile, "field_id")
        return profile

    def delete_project(self, field_id: str, *, delete_orphan_records: bool = True) -> dict[str, Any]:
        if field_id == "default":
            raise ValueError("The default project cannot be deleted.")
        data = self.store.snapshot(limit_per_bucket=None)
        project_memberships = [
            membership
            for membership in data.get("project_memberships", {}).values()
            if membership.get("field_id") == field_id
        ]
        candidate_records: dict[str, set[str]] = {}
        for membership in project_memberships:
            candidate_records.setdefault(str(membership.get("bucket") or ""), set()).add(str(membership.get("record_id") or ""))
        for membership in data.get("project_memberships", {}).values():
            if membership.get("field_id") == field_id:
                self.store.delete_item("project_memberships", membership["membership_id"])
        deleted_records: dict[str, int] = {}
        if delete_orphan_records:
            remaining_memberships = [
                membership
                for membership in data.get("project_memberships", {}).values()
                if membership.get("field_id") != field_id
            ]
            still_referenced = {
                (str(membership.get("bucket") or ""), str(membership.get("record_id") or ""))
                for membership in remaining_memberships
                if membership.get("bucket") and membership.get("record_id")
            }
            for bucket, record_ids in candidate_records.items():
                id_key = self._record_id_key(bucket)
                for record_id in record_ids:
                    if not record_id or (bucket, record_id) in still_referenced:
                        continue
                    record = data.get(bucket, {}).get(record_id)
                    if not record:
                        continue
                    # Keep global/default records that were not created through a concrete project.
                    if record.get("field_id") == "default" and bucket not in {"existed_ideas", "principles", "takeaway_messages", "benchmark_records", "baseline_records", "source_works", "my_ideas"}:
                        continue
                    self.store.delete_item(bucket, record_id)
                    deleted_records[bucket] = deleted_records.get(bucket, 0) + 1
                    if bucket == "source_works":
                        work_id = record.get("work_id", record_id)
                        for linked_bucket in ("work_facts", "benchmark_records", "baseline_records", "result_records"):
                            linked_id_key = self._record_id_key(linked_bucket)
                            for linked in data.get(linked_bucket, {}).values():
                                if linked.get("work_id") == work_id and (linked_bucket, linked.get(linked_id_key, "")) not in still_referenced:
                                    self.store.delete_item(linked_bucket, linked[linked_id_key])
                                    deleted_records[linked_bucket] = deleted_records.get(linked_bucket, 0) + 1
            for link in data.get("evidence_links", {}).values():
                if link.get("field_id") == field_id or (link.get("target_bucket"), link.get("target_id")) in {
                    (bucket, record_id) for bucket, ids in candidate_records.items() for record_id in ids
                }:
                    self.store.delete_item("evidence_links", link["link_id"])
                    deleted_records["evidence_links"] = deleted_records.get("evidence_links", 0) + 1
            for run in data.get("research_runs", {}).values():
                if run.get("field_id") == field_id:
                    self.store.delete_item("research_runs", run["run_id"])
                    deleted_records["research_runs"] = deleted_records.get("research_runs", 0) + 1
        self.store.delete_item("field_profiles", field_id)
        return {"ok": True, "deleted": field_id, "deleted_records": deleted_records}

    def reorder_projects(self, field_ids: list[str]) -> list[dict[str, Any]]:
        for index, field_id in enumerate([fid for fid in field_ids if fid and fid != "default"]):
            profile = self.store.get_item("field_profiles", field_id)
            if not profile:
                continue
            profile["display_order"] = index
            profile["updated_at"] = utc_now()
            self.store.upsert("field_profiles", profile, "field_id")
        return self.list_projects()

    def create_project_from_result(
        self,
        goal: dict[str, Any],
        works: list[dict[str, Any]],
        principles: list[dict[str, Any]],
        ideas: list[dict[str, Any]],
        *,
        query: str,
        name: str = "",
    ) -> dict[str, Any]:
        field_id = stable_id("PRJ", goal.get("goal_id", ""), query)
        existing = self.store.get_item("field_profiles", field_id) or {}
        profile = {
            **to_dict(
                FieldProfile(
                    field_id=field_id,
                    name=name or compact_text(query, 70) or "Generated Project",
                    description="Auto-created from a Principia workbench query.",
                    query=query,
                    domain_tags=keyword_terms(query, 8),
                )
            ),
            **existing,
        }
        profile["name"] = existing.get("name") or name or compact_text(query, 70) or "Generated Project"
        profile["description"] = existing.get("description") or "Auto-created from a Principia workbench query."
        profile["query"] = existing.get("query") or query
        profile["goal_text"] = existing.get("goal_text") or query
        profile.setdefault("settings", {})
        profile.setdefault("display_order", 0)
        profile["work_ids"] = self._ordered_unique([*(existing.get("work_ids") or []), *[work["work_id"] for work in works if work.get("work_id")]])
        profile["principle_ids"] = self._ordered_unique(
            [*(existing.get("principle_ids") or []), *[principle["principle_id"] for principle in principles if principle.get("principle_id")]]
        )
        profile["idea_ids"] = self._ordered_unique([*(existing.get("idea_ids") or []), *[idea["idea_id"] for idea in ideas if idea.get("idea_id")]])
        profile["updated_at"] = utc_now()
        self.store.upsert("field_profiles", profile, "field_id")
        self.add_project_memberships(field_id, "source_works", [work["work_id"] for work in works if work.get("work_id")], source="generate")
        self.add_project_memberships(field_id, "principles", [principle["principle_id"] for principle in principles if principle.get("principle_id")], source="generate")
        self.add_project_memberships(field_id, "ideas", [idea["idea_id"] for idea in ideas if idea.get("idea_id")], source="generate")
        project_goal = self._observatory_goal(query)
        fact_ids: list[str] = []
        benchmark_ids: list[str] = []
        baseline_ids: list[str] = []
        result_ids: list[str] = []
        for work in works:
            facts = self.extract_work_facts(project_goal, work, field_id=field_id, persist=True)
            extracted = self.extract_benchmark_records(project_goal, work, field_id=field_id, persist=True)
            fact_ids.extend([item["fact_id"] for item in facts if item.get("fact_id")])
            benchmark_ids.extend([item["benchmark_id"] for item in extracted["benchmark_records"] if item.get("benchmark_id")])
            baseline_ids.extend([item["baseline_id"] for item in extracted["baseline_records"] if item.get("baseline_id")])
            result_ids.extend([item["result_id"] for item in extracted["result_records"] if item.get("result_id")])
        self.add_project_memberships(field_id, "work_facts", fact_ids, source="extract")
        self.add_project_memberships(field_id, "benchmark_records", benchmark_ids, source="extract")
        self.add_project_memberships(field_id, "baseline_records", baseline_ids, source="extract")
        self.add_project_memberships(field_id, "result_records", result_ids, source="extract")
        self.mine_gap_cards(field_id=field_id, query=query, persist=True, ensure=False)
        return profile

    def attach_generation_to_project(
        self,
        field_id: str,
        result: dict[str, Any],
        *,
        query: str,
        settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        profile = self._ensure_field_profile(field_id, query)
        profile["goal_text"] = query or profile.get("goal_text", "")
        profile["query"] = query or profile.get("query", "")
        if settings:
            profile["settings"] = dict(settings)
        works = list(result.get("source_works") or [])
        principles = list(result.get("principles") or [])
        ideas = list(result.get("ideas") or [])
        profile["work_ids"] = self._ordered_unique([*(profile.get("work_ids") or []), *[work["work_id"] for work in works if work.get("work_id")]])
        profile["principle_ids"] = self._ordered_unique([*(profile.get("principle_ids") or []), *[item["principle_id"] for item in principles if item.get("principle_id")]])
        profile["idea_ids"] = self._ordered_unique([*(profile.get("idea_ids") or []), *[item["idea_id"] for item in ideas if item.get("idea_id")]])
        self.store.upsert("field_profiles", profile, "field_id")
        self.add_project_memberships(field_id, "source_works", [work["work_id"] for work in works if work.get("work_id")], source="generate", prepend=True)
        self.add_project_memberships(field_id, "principles", [item["principle_id"] for item in principles if item.get("principle_id")], source="generate")
        self.add_project_memberships(field_id, "ideas", [item["idea_id"] for item in ideas if item.get("idea_id")], source="generate", prepend=True)
        goal = self._observatory_goal(query)
        fact_ids: list[str] = []
        benchmark_ids: list[str] = []
        baseline_ids: list[str] = []
        result_ids: list[str] = []
        for work in works:
            facts = self.extract_work_facts(goal, work, field_id=field_id, persist=True)
            extracted = self.extract_benchmark_records(goal, work, field_id=field_id, persist=True)
            fact_ids.extend([item["fact_id"] for item in facts if item.get("fact_id")])
            benchmark_ids.extend([item["benchmark_id"] for item in extracted["benchmark_records"] if item.get("benchmark_id")])
            baseline_ids.extend([item["baseline_id"] for item in extracted["baseline_records"] if item.get("baseline_id")])
            result_ids.extend([item["result_id"] for item in extracted["result_records"] if item.get("result_id")])
        self.add_project_memberships(field_id, "work_facts", fact_ids, source="generate")
        self.add_project_memberships(field_id, "benchmark_records", benchmark_ids, source="generate")
        self.add_project_memberships(field_id, "baseline_records", baseline_ids, source="generate")
        self.add_project_memberships(field_id, "result_records", result_ids, source="generate")
        return self.project_summary(field_id)

    def sync_library_observatory(self, field_id: str = "default", query: str = "", *, record_run: bool = False) -> dict[str, Any]:
        """Derive v0.3 observatory records from the existing local store."""

        self._ensure_field_profile(field_id, query)
        data = self.store.snapshot(limit_per_bucket=None)
        goal = self._observatory_goal(query)
        project_work_ids = self._project_id_set(data, field_id, "work_ids")
        work_count = 0
        fact_count = 0
        benchmark_count = 0
        baseline_count = 0
        result_count = 0
        for work in data.get("source_works", {}).values():
            if project_work_ids and work.get("work_id") not in project_work_ids:
                continue
            if query and lexical_score(query, self._material_text(work)) <= 0:
                continue
            work_count += 1
            facts = self.extract_work_facts(goal, work, field_id=field_id, persist=True)
            extracted = self.extract_benchmark_records(goal, work, field_id=field_id, persist=True)
            self.add_project_memberships(field_id, "work_facts", [item["fact_id"] for item in facts if item.get("fact_id")], source="sync")
            self.add_project_memberships(
                field_id,
                "benchmark_records",
                [item["benchmark_id"] for item in extracted["benchmark_records"] if item.get("benchmark_id")],
                source="sync",
            )
            self.add_project_memberships(
                field_id,
                "baseline_records",
                [item["baseline_id"] for item in extracted["baseline_records"] if item.get("baseline_id")],
                source="sync",
            )
            self.add_project_memberships(
                field_id,
                "result_records",
                [item["result_id"] for item in extracted["result_records"] if item.get("result_id")],
                source="sync",
            )
            fact_count += len(facts)
            benchmark_count += len(extracted["benchmark_records"])
            baseline_count += len(extracted["baseline_records"])
            result_count += len(extracted["result_records"])
        gaps = self.mine_gap_cards(field_id=field_id, query=query, persist=True, ensure=False)
        run_id = ""
        if record_run:
            run_id = stable_id("R", field_id, "sync_field", utc_now())
            self.store.upsert(
                "runs",
                {
                    "run_id": run_id,
                    "type": "sync_field",
                    "field_id": field_id,
                    "query": query,
                    "input_counts": {"works": work_count},
                    "output_counts": {
                        "work_facts": fact_count,
                        "benchmark_records": benchmark_count,
                        "baseline_records": baseline_count,
                        "result_records": result_count,
                        "gap_cards": len(gaps),
                    },
                    "created_at": utc_now(),
                },
                "run_id",
            )
        return {
            "ok": True,
            "field_id": field_id,
            "run_id": run_id,
            "processed_works": work_count,
            "created_or_refreshed": {
                "work_facts": fact_count,
                "benchmark_records": benchmark_count,
                "baseline_records": baseline_count,
                "result_records": result_count,
                "gap_cards": len(gaps),
            },
        }

    def refresh_project(
        self,
        field_id: str,
        *,
        query: str = "",
        source_mode: str = "online",
        paper_count: int = 10,
        model_mode: str = "auto",
        force: bool = False,
    ) -> dict[str, Any]:
        profile = self._ensure_field_profile(field_id, query)
        query = query or profile.get("goal_text") or profile.get("query") or profile.get("name", "")
        goal = self._observatory_goal(query)
        profile["refresh_status"] = "running"
        profile["updated_at"] = utc_now()
        self.store.upsert("field_profiles", profile, "field_id")
        data_before = self.store.snapshot(limit_per_bucket=None)
        existing_work_ids = self._project_id_set(data_before, field_id, "work_ids")
        if not existing_work_ids and field_id == "default":
            existing_work_ids = set(data_before.get("source_works", {}).keys())
        new_works: list[dict[str, Any]] = []
        if source_mode == "online" and query:
            try:
                for work in search_arxiv(query, max_results=max(1, int(paper_count or 10)), timeout=8):
                    local = data_before.get("source_works", {}).get(work["work_id"])
                    if local and not force and not self._work_needs_refresh(work, local):
                        continue
                    self.store.upsert("source_works", work, "work_id")
                    new_works.append(work)
            except Exception:
                if not existing_work_ids:
                    new_works = fallback_seed_work(query)[: max(1, int(paper_count or 10))]
                    self.store.upsert_many("source_works", new_works, "work_id")
        if new_works:
            self.add_project_memberships(field_id, "source_works", [work["work_id"] for work in new_works], source="refresh", prepend=True)
        data = self.store.snapshot(limit_per_bucket=None)
        work_ids = self._project_id_set(data, field_id, "work_ids")
        if not work_ids and field_id == "default":
            work_ids = set(data.get("source_works", {}).keys())
        works = [data.get("source_works", {}).get(wid) for wid in work_ids if data.get("source_works", {}).get(wid)]
        processed = skipped = fact_count = benchmark_count = baseline_count = result_count = 0
        for work in works:
            current_benchmarks = [
                item
                for item in data.get("benchmark_records", {}).values()
                if item.get("field_id", "default") == field_id and item.get("work_id") == work.get("work_id")
            ]
            source_hash = self._work_source_hash(work)
            if current_benchmarks and not force and all(item.get("source_hash") == source_hash for item in current_benchmarks):
                skipped += 1
            processed += 1
            facts = self.extract_work_facts(goal, work, field_id=field_id, persist=True)
            extracted = self.extract_benchmark_records(goal, work, field_id=field_id, persist=True, force=force)
            self.add_project_memberships(field_id, "work_facts", [item["fact_id"] for item in facts if item.get("fact_id")], source="refresh")
            self.add_project_memberships(field_id, "benchmark_records", [item["benchmark_id"] for item in extracted["benchmark_records"] if item.get("benchmark_id")], source="refresh")
            self.add_project_memberships(field_id, "baseline_records", [item["baseline_id"] for item in extracted["baseline_records"] if item.get("baseline_id")], source="refresh")
            self.add_project_memberships(field_id, "result_records", [item["result_id"] for item in extracted["result_records"] if item.get("result_id")], source="refresh")
            fact_count += len(facts)
            benchmark_count += len(extracted["benchmark_records"])
            baseline_count += len(extracted["baseline_records"])
            result_count += len(extracted["result_records"])
        profile = self.store.get_item("field_profiles", field_id) or profile
        profile["last_refresh_at"] = utc_now()
        profile["refresh_status"] = "idle"
        profile["goal_text"] = profile.get("goal_text") or query
        profile["updated_at"] = utc_now()
        self.store.upsert("field_profiles", profile, "field_id")
        run_id = stable_id("R", field_id, "refresh_project", utc_now())
        run = {
            "run_id": run_id,
            "type": "refresh_project",
            "field_id": field_id,
            "query": query,
            "model_mode": model_mode,
            "source_mode": source_mode,
            "input_counts": {"existing_project_works": len(existing_work_ids), "new_works": len(new_works)},
            "output_counts": {
                "processed_works": processed,
                "skipped_unchanged_works": skipped,
                "work_facts": fact_count,
                "benchmark_records": benchmark_count,
                "baseline_records": baseline_count,
                "result_records": result_count,
            },
            "costs": list(self.llm.costs.calls),
            "created_at": utc_now(),
        }
        self.store.upsert("runs", run, "run_id")
        return {"ok": True, "run": run, "project": profile, "new_works": new_works, "summary": self.project_summary(field_id)}

    def import_v0_store(self, source_db_path: str | Path) -> dict[str, Any]:
        source_path = Path(source_db_path).expanduser()
        if not source_path.exists():
            raise FileNotFoundError(str(source_path))
        source = Store(source_path)
        data = source.snapshot(limit_per_bucket=None)
        imported: dict[str, int] = {}
        for bucket, records in data.items():
            if bucket == "meta" or bucket not in BUCKETS:
                continue
            if not isinstance(records, dict) or not records:
                imported[bucket] = 0
                continue
            id_key = self.store._id_key(bucket)
            self.store.upsert_many(bucket, list(records.values()), id_key)
            imported[bucket] = len(records)
        current = self.store.snapshot(limit_per_bucket=None)
        for profile in current.get("field_profiles", {}).values():
            field_id = profile.get("field_id", "")
            if not field_id or field_id == "default":
                continue
            self.add_project_memberships(field_id, "source_works", list(profile.get("work_ids") or []), source="v0_import")
            self.add_project_memberships(field_id, "principles", list(profile.get("principle_ids") or []), source="v0_import")
            self.add_project_memberships(field_id, "ideas", list(profile.get("idea_ids") or []), source="v0_import")
            for bucket in ("work_facts", "benchmark_records", "baseline_records", "result_records", "gap_cards"):
                id_key = self._record_id_key(bucket)
                ids = [
                    item.get(id_key)
                    for item in current.get(bucket, {}).values()
                    if item.get("field_id", "default") == field_id and item.get(id_key)
                ]
                self.add_project_memberships(field_id, bucket, ids, source="v0_import")
        return {"ok": True, "source": str(source_path), "imported": imported, "projects": self.list_projects()}

    # ------------------------------------------------------------------
    # v2 research workspace

    def v2_project_counts(self, data: dict[str, Any], field_id: str, query: str = "") -> dict[str, int]:
        return {
            "existed_ideas": len(self._v2_project_records(data, field_id, "existed_ideas", query=query)),
            "benchmarks": len(self._v2_project_records(data, field_id, "benchmark_records", query=query)),
            "baselines": len(self._v2_project_records(data, field_id, "baseline_records", query=query)),
            "my_ideas": len(self._v2_project_records(data, field_id, "my_ideas", query=query)),
            "principles": len(self._v2_project_records(data, field_id, "principles", query=query)),
            "takeaway_messages": len(self._v2_project_records(data, field_id, "takeaway_messages", query=query)),
            "works": len(self._v2_project_records(data, field_id, "source_works", query=query)),
        }

    def v2_project_summary(self, field_id: str = "default", query: str = "") -> dict[str, Any]:
        data = self.store.snapshot(limit_per_bucket=None)
        return {
            "project": data.get("field_profiles", {}).get(field_id) or self._ensure_field_profile(field_id, query),
            "counts": self.v2_project_counts(data, field_id, query=query),
            "last_research_run": self._v2_last_research_run(data, field_id),
        }

    def v2_research_project(
        self,
        field_id: str,
        *,
        goal_text: str,
        model_mode: str = "auto",
        target_works: int = 50,
        run_id: str = "",
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        target_works = max(1, min(int(target_works or 50), 100))
        profile = self._ensure_field_profile(field_id, goal_text)
        goal_text = goal_text or profile.get("goal_text") or profile.get("query") or profile.get("name", "")
        model = self._v2_model_meta(model_mode)
        run_id = run_id or stable_id("VRUN", field_id, goal_text, model["model_name"], utc_now())
        run = {
            "run_id": run_id,
            "field_id": field_id,
            "type": "v2_research",
            "status": "running",
            "stage": "starting",
            "message": "Starting research.",
            "goal_text": goal_text,
            "model_mode": model_mode,
            "model_name": model["model_name"],
            "provider": model["provider"],
            "target_works": target_works,
            "counts": {},
            "errors": [],
            "warnings": [],
            "started_at": utc_now(),
            "updated_at": utc_now(),
        }
        self._cancelled_runs.discard(run_id)
        self.store.upsert("research_runs", run, "run_id")

        def update(stage: str, message: str, **counts: Any) -> None:
            self._raise_if_cancelled(run_id)
            run["stage"] = stage
            run["message"] = message
            run["counts"] = {**run.get("counts", {}), **counts}
            run["updated_at"] = utc_now()
            self.store.upsert("research_runs", run, "run_id")
            if progress_callback:
                progress_callback(dict(run))

        try:
            self._raise_if_cancelled(run_id)
            profile["goal_text"] = goal_text
            profile["query"] = goal_text
            profile["settings"] = {**dict(profile.get("settings") or {}), "model_mode": model_mode, "language": "en", "source_mode": "online+local", "paper_count": target_works}
            profile["refresh_status"] = "researching"
            profile["updated_at"] = utc_now()
            self.store.upsert("field_profiles", profile, "field_id")

            update("query_planning", "Planning hybrid academic/web queries.")
            query = self._v2_research_query(goal_text)
            update("source_search", "Searching arXiv, OpenAlex, Crossref, and public metadata.", planned_query=query)
            works = search_hybrid_sources(query, max_results=target_works, timeout=12)
            self._raise_if_cancelled(run_id)
            if len(works) < min(8, target_works):
                works = self._dedupe_works([*works, *fallback_seed_work(goal_text)])[:target_works]
            works = works[:target_works]
            work_ids: list[str] = []
            existed_ids: list[str] = []
            principle_ids: list[str] = []
            message_ids: list[str] = []
            benchmark_ids: list[str] = []
            baseline_ids: list[str] = []
            result_ids: list[str] = []
            evidence_links: list[dict[str, Any]] = []
            work_lookup = {str(work.get("work_id") or ""): work for work in works}

            def persist_llm_concepts(batch_extras: dict[str, dict[str, Any]]) -> None:
                batch_links: list[dict[str, Any]] = []
                batch_work_ids: list[str] = []
                batch_existed: list[str] = []
                batch_principles: list[str] = []
                batch_messages: list[str] = []
                for raw_work_id, extras in batch_extras.items():
                    raw_work = work_lookup.get(str(raw_work_id))
                    if not raw_work or not extras:
                        continue
                    work = self._v2_upsert_work(raw_work, model_mode=model_mode)
                    batch_work_ids.append(work["work_id"])
                    if work["work_id"] not in work_ids:
                        work_ids.append(work["work_id"])
                    extracted = self._v2_extract_concepts_from_work(goal_text, work, extras)
                    for payload in extracted["existed_ideas"]:
                        item = self._v2_upsert_canonical("existed_ideas", payload["idea_text"], payload, model_mode=model_mode)
                        existed_ids.append(item["canonical_id"])
                        batch_existed.append(item["canonical_id"])
                        batch_links.append(self._v2_evidence_link(field_id, "existed_ideas", item["canonical_id"], work["work_id"], payload.get("evidence", "")))
                    for payload in extracted["principles"]:
                        item = self._v2_upsert_canonical("principles", payload["name"], payload, model_mode=model_mode)
                        principle_ids.append(item["principle_id"])
                        batch_principles.append(item["principle_id"])
                        batch_links.append(self._v2_evidence_link(field_id, "principles", item["principle_id"], work["work_id"], payload.get("evidence", "")))
                    for payload in extracted["takeaway_messages"]:
                        item = self._v2_upsert_canonical("takeaway_messages", payload["message_text"], payload, model_mode=model_mode)
                        message_ids.append(item["canonical_id"])
                        batch_messages.append(item["canonical_id"])
                        batch_links.append(self._v2_evidence_link(field_id, "takeaway_messages", item["canonical_id"], work["work_id"], payload.get("evidence", "")))
                if batch_links:
                    evidence_links.extend(batch_links)
                    self.store.upsert_many("evidence_links", batch_links, "link_id")
                self.add_project_memberships(field_id, "source_works", self._ordered_unique(batch_work_ids), source="v2_research", prepend=True)
                self.add_project_memberships(field_id, "existed_ideas", self._ordered_unique(batch_existed), source="v2_research", prepend=True)
                self.add_project_memberships(field_id, "principles", self._ordered_unique(batch_principles), source="v2_research")
                self.add_project_memberships(field_id, "takeaway_messages", self._ordered_unique(batch_messages), source="v2_research")
                if batch_existed or batch_principles or batch_messages:
                    update(
                        "llm_extraction_persist",
                        "Stored the latest extracted ideas, principles, and takeaway messages.",
                        found_works=len(works),
                        llm_extracted_works=len(set(work_ids)),
                        existed_ideas=len(set(existed_ids)),
                        principles=len(set(principle_ids)),
                        takeaway_messages=len(set(message_ids)),
                    )

            llm_limit = min(len(works), self._v2_llm_extraction_limit(model_mode))
            llm_candidates = [work for work in works[:llm_limit] if self._v2_needs_llm_extraction(work, model_mode)]
            skipped_unchanged = max(0, llm_limit - len(llm_candidates))
            if skipped_unchanged:
                update(
                    "llm_extraction_cache",
                    f"Skipped {skipped_unchanged} unchanged works for the same LLM.",
                    found_works=len(works),
                    skipped_unchanged_llm=skipped_unchanged,
                )
            llm_extras = self._v2_llm_extract_batch(
                goal_text,
                llm_candidates,
                model_mode=model_mode,
                progress_callback=update,
                batch_result_callback=persist_llm_concepts,
                cancel_check=lambda: self._is_run_cancelled(run_id),
            )
            self._raise_if_cancelled(run_id)
            llm_extract_error = str(getattr(self, "_last_v2_llm_extract_error", "") or "")
            if llm_extract_error:
                run["warnings"] = self._ordered_unique([*run.get("warnings", []), llm_extract_error])
                update("llm_extraction_warning", llm_extract_error)
            update(
                "work_upsert",
                f"Storing {len(works)} candidate works.",
                found_works=len(works),
                llm_extracted_works=len(llm_extras),
                skipped_unchanged_llm=skipped_unchanged,
            )
            goal = self._observatory_goal(goal_text)
            for index, raw_work in enumerate(works, start=1):
                self._raise_if_cancelled(run_id)
                work = self._v2_upsert_work(raw_work, model_mode=model_mode)
                work_ids.append(work["work_id"])
                extras = llm_extras.get(raw_work.get("work_id", "")) or llm_extras.get(work.get("work_id", "")) or {}
                extracted = (
                    self._v2_extract_concepts_from_work(goal_text, work, extras)
                    if extras
                    else {"existed_ideas": [], "principles": [], "takeaway_messages": []}
                )
                for payload in extracted["existed_ideas"]:
                    item = self._v2_upsert_canonical("existed_ideas", payload["idea_text"], payload, model_mode=model_mode)
                    existed_ids.append(item["canonical_id"])
                    evidence_links.append(self._v2_evidence_link(field_id, "existed_ideas", item["canonical_id"], work["work_id"], payload.get("evidence", "")))
                for payload in extracted["principles"]:
                    item = self._v2_upsert_canonical("principles", payload["name"], payload, model_mode=model_mode)
                    principle_ids.append(item["principle_id"])
                    evidence_links.append(self._v2_evidence_link(field_id, "principles", item["principle_id"], work["work_id"], payload.get("evidence", "")))
                for payload in extracted["takeaway_messages"]:
                    item = self._v2_upsert_canonical("takeaway_messages", payload["message_text"], payload, model_mode=model_mode)
                    message_ids.append(item["canonical_id"])
                    evidence_links.append(self._v2_evidence_link(field_id, "takeaway_messages", item["canonical_id"], work["work_id"], payload.get("evidence", "")))
                matrix = self.extract_benchmark_records(goal, work, field_id=field_id, persist=False)
                for benchmark in matrix.get("benchmark_records", []):
                    payload = self._v2_benchmark_payload(benchmark, work)
                    item = self._v2_upsert_canonical("benchmark_records", payload["benchmark_name"], payload, model_mode=model_mode)
                    benchmark_ids.append(item["benchmark_id"])
                    evidence_links.append(self._v2_evidence_link(field_id, "benchmark_records", item["benchmark_id"], work["work_id"], payload.get("evidence", "")))
                for benchmark in extras.get("benchmarks", []) or []:
                    if not isinstance(benchmark, dict):
                        continue
                    payload = self._v2_benchmark_payload(benchmark, work)
                    if not payload.get("benchmark_name") or payload.get("benchmark_name") == "Unspecified benchmark":
                        continue
                    item = self._v2_upsert_canonical("benchmark_records", payload["benchmark_name"], payload, model_mode=model_mode)
                    benchmark_ids.append(item["benchmark_id"])
                    evidence_links.append(self._v2_evidence_link(field_id, "benchmark_records", item["benchmark_id"], work["work_id"], payload.get("evidence", "")))
                for baseline in matrix.get("baseline_records", []):
                    related_results = [result for result in matrix.get("result_records", []) if result.get("baseline_id") == baseline.get("baseline_id") or result.get("benchmark_id") == baseline.get("benchmark_id")]
                    payload = self._v2_baseline_payload(baseline, work, related_results)
                    item = self._v2_upsert_canonical("baseline_records", payload["baseline_name"], payload, model_mode=model_mode)
                    baseline_ids.append(item["baseline_id"])
                    evidence_links.append(self._v2_evidence_link(field_id, "baseline_records", item["baseline_id"], work["work_id"], payload.get("evidence", "")))
                for baseline in extras.get("baselines", []) or []:
                    if not isinstance(baseline, dict):
                        continue
                    payload = self._v2_baseline_payload(baseline, work, list(baseline.get("performance") or []))
                    if not payload.get("baseline_name") or payload.get("baseline_name") == "Baseline":
                        continue
                    item = self._v2_upsert_canonical("baseline_records", payload["baseline_name"], payload, model_mode=model_mode)
                    baseline_ids.append(item["baseline_id"])
                    evidence_links.append(self._v2_evidence_link(field_id, "baseline_records", item["baseline_id"], work["work_id"], payload.get("evidence", "")))
                for result in matrix.get("result_records", []):
                    result = dict(result)
                    result.setdefault("source_work_id", work["work_id"])
                    result_ids.append(result["result_id"])
                    self.store.upsert("result_records", result, "result_id")
                if index % 10 == 0 or index == len(works):
                    update(
                        "structured_extraction",
                        f"Extracted structured evidence from {index}/{len(works)} works.",
                        processed_works=index,
                        existed_ideas=len(set(existed_ids)),
                        principles=len(set(principle_ids)),
                        takeaway_messages=len(set(message_ids)),
                        benchmarks=len(set(benchmark_ids)),
                        baselines=len(set(baseline_ids)),
                    )
            if evidence_links:
                self.store.upsert_many("evidence_links", evidence_links, "link_id")
            self.add_project_memberships(field_id, "source_works", work_ids, source="v2_research", prepend=True)
            self.add_project_memberships(field_id, "existed_ideas", self._ordered_unique(existed_ids), source="v2_research", prepend=True)
            self.add_project_memberships(field_id, "principles", self._ordered_unique(principle_ids), source="v2_research")
            self.add_project_memberships(field_id, "takeaway_messages", self._ordered_unique(message_ids), source="v2_research")
            self.add_project_memberships(field_id, "benchmark_records", self._ordered_unique(benchmark_ids), source="v2_research")
            self.add_project_memberships(field_id, "baseline_records", self._ordered_unique(baseline_ids), source="v2_research")
            self.add_project_memberships(field_id, "result_records", self._ordered_unique(result_ids), source="v2_research")
            profile = self.store.get_item("field_profiles", field_id) or profile
            profile["refresh_status"] = "idle"
            profile["last_refresh_at"] = utc_now()
            profile["updated_at"] = utc_now()
            self.store.upsert("field_profiles", profile, "field_id")
            run["status"] = "complete"
            run["stage"] = "complete"
            run["message"] = "Research complete."
            run["completed_at"] = utc_now()
            run["updated_at"] = utc_now()
            run["counts"] = {
                "works": len(set(work_ids)),
                "existed_ideas": len(set(existed_ids)),
                "principles": len(set(principle_ids)),
                "takeaway_messages": len(set(message_ids)),
                "benchmarks": len(set(benchmark_ids)),
                "baselines": len(set(baseline_ids)),
                "result_records": len(set(result_ids)),
            }
            self.store.upsert("research_runs", run, "run_id")
            return {"ok": True, "run": run, "summary": self.v2_project_summary(field_id)}
        except CancelledRun:
            self._mark_run_cancelled(run)
            profile = self.store.get_item("field_profiles", field_id) or profile
            profile["refresh_status"] = "cancelled"
            profile["updated_at"] = utc_now()
            self.store.upsert("field_profiles", profile, "field_id")
            return {"ok": False, "cancelled": True, "run": run, "summary": self.v2_project_summary(field_id)}
        except Exception as exc:
            run["status"] = "error"
            run["stage"] = "error"
            run["message"] = str(exc)
            run["errors"] = [*run.get("errors", []), str(exc)]
            run["updated_at"] = utc_now()
            self.store.upsert("research_runs", run, "run_id")
            profile = self.store.get_item("field_profiles", field_id) or profile
            profile["refresh_status"] = "error"
            profile["updated_at"] = utc_now()
            self.store.upsert("field_profiles", profile, "field_id")
            raise

    def build_v2_project_tab(
        self,
        field_id: str,
        tab: str,
        *,
        offset: int = 0,
        limit: int = 10,
        query: str = "",
        model_mode: str = "auto",
    ) -> dict[str, Any]:
        bucket = {
            "existed_ideas": "existed_ideas",
            "benchmarks": "benchmark_records",
            "baselines": "baseline_records",
            "principles": "principles",
            "takeaway_messages": "takeaway_messages",
            "my_ideas": "my_ideas",
        }.get(tab, tab)
        data = self.store.snapshot(limit_per_bucket=None)
        items = [self._v2_present_item(item, model_mode=model_mode) for item in self._v2_project_records(data, field_id, bucket, query=query)]
        profile = data.get("field_profiles", {}).get(field_id) or {}
        sort_query = query or profile.get("goal_text") or profile.get("query") or profile.get("name", "")
        if bucket == "my_ideas":
            items.sort(
                key=lambda item: (
                    str(item.get("created_at") or item.get("entered_at") or item.get("updated_at") or ""),
                    str(item.get("updated_at") or ""),
                ),
                reverse=True,
            )
        else:
            items.sort(key=lambda item: self._v2_sort_score(item, sort_query), reverse=True)
        total = len(items)
        return {
            "items": items[offset : offset + limit],
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": offset + limit < total,
            "counts": self.v2_project_counts(data, field_id, query=query),
        }

    def v2_item_detail(self, bucket: str, record_id: str, *, version: str = "", model_mode: str = "auto") -> dict[str, Any]:
        bucket = self._v2_bucket(bucket)
        item = self.store.get_item(bucket, record_id)
        if not item:
            raise KeyError(f"{bucket}:{record_id} not found")
        detail = self._v2_present_item(item, model_mode=model_mode, version_id=version)
        data = self.store.snapshot(limit_per_bucket=None)
        source_ids = detail.get("source_work_ids") or detail.get("source_works") or []
        works = [data.get("source_works", {}).get(wid) for wid in source_ids if data.get("source_works", {}).get(wid)]
        detail["source_work_details"] = [self._v2_present_item(work, model_mode=model_mode) for work in works]
        detail["evidence_links"] = [
            link
            for link in data.get("evidence_links", {}).values()
            if link.get("target_bucket") == bucket and link.get("target_id") == record_id
        ]
        return {"item": detail}

    def v2_item_update(self, payload: dict[str, Any]) -> dict[str, Any]:
        bucket = self._v2_bucket(str(payload.get("bucket") or ""))
        record_id = str(payload.get("id") or payload.get("record_id") or "")
        item = self.store.get_item(bucket, record_id)
        if not item:
            raise KeyError(f"{bucket}:{record_id} not found")
        update_payload = dict(payload.get("payload") or payload.get("fields") or {})
        merged_payload = {**self._v2_active_payload(item), **update_payload}
        updated = self._v2_upsert_canonical(bucket, item.get("canonical_key") or record_id, merged_payload, model_mode="manual", is_user_edit=True, existing_id=record_id)
        return {"ok": True, "item": self._v2_present_item(updated, version_id=updated.get("active_version_id", ""))}

    def v2_item_refresh(self, payload: dict[str, Any], *, run_id: str = "") -> dict[str, Any]:
        bucket = self._v2_bucket(str(payload.get("bucket") or ""))
        record_id = str(payload.get("id") or payload.get("record_id") or "")
        model_mode = str(payload.get("model_mode") or "auto")
        item = self.store.get_item(bucket, record_id)
        if not item:
            raise KeyError(f"{bucket}:{record_id} not found")
        self._raise_if_cancelled(run_id)
        current = self._v2_active_payload(item)
        refreshed = self._v2_refresh_payload_with_llm(bucket, current, model_mode=model_mode)
        self._raise_if_cancelled(run_id)
        updated = self._v2_upsert_canonical(bucket, item.get("canonical_key") or record_id, refreshed, model_mode=model_mode, existing_id=record_id)
        return {"ok": True, "item": self._v2_present_item(updated, model_mode=model_mode)}

    def v2_item_delete(self, payload: dict[str, Any]) -> dict[str, Any]:
        bucket = self._v2_bucket(str(payload.get("bucket") or ""))
        record_id = str(payload.get("id") or payload.get("record_id") or "")
        if not bucket or not record_id:
            raise ValueError("Missing bucket or id")
        item = self.store.get_item(bucket, record_id)
        if not item:
            raise KeyError(f"{bucket}:{record_id} not found")
        data = self.store.snapshot(limit_per_bucket=None)
        deleted = {bucket: 1, "project_memberships": 0, "evidence_links": 0}
        self.store.delete_item(bucket, record_id)
        for membership in data.get("project_memberships", {}).values():
            if membership.get("bucket") == bucket and membership.get("record_id") == record_id:
                self.store.delete_item("project_memberships", membership["membership_id"])
                deleted["project_memberships"] += 1
        for link in data.get("evidence_links", {}).values():
            if link.get("target_bucket") == bucket and link.get("target_id") == record_id:
                self.store.delete_item("evidence_links", link["link_id"])
                deleted["evidence_links"] += 1
        return {"ok": True, "deleted": {"bucket": bucket, "id": record_id, "counts": deleted}}

    def v2_assembler_sources(
        self,
        field_id: str,
        source: str,
        *,
        query: str = "",
        offset: int = 0,
        limit: int = 20,
        model_mode: str = "auto",
    ) -> dict[str, Any]:
        bucket = {
            "existed_ideas": "existed_ideas",
            "principles": "principles",
            "takeaway_messages": "takeaway_messages",
        }.get(source, "existed_ideas")
        data = self.store.snapshot(limit_per_bucket=None)
        items = [self._v2_present_item(item, model_mode=model_mode) for item in self._v2_project_records(data, field_id, bucket, query=query)]
        profile = data.get("field_profiles", {}).get(field_id) or {}
        sort_query = query or profile.get("goal_text") or profile.get("query") or profile.get("name", "")
        items.sort(key=lambda item: self._v2_sort_score(item, sort_query), reverse=True)
        return {"items": items[offset : offset + limit], "total": len(items), "has_more": offset + limit < len(items)}

    def v2_generate_my_idea(
        self,
        *,
        field_id: str,
        goal_text: str,
        selected_refs: list[dict[str, str]],
        user_note: str = "",
        model_mode: str = "auto",
        run_id: str = "",
    ) -> dict[str, Any]:
        self._raise_if_cancelled(run_id)
        profile = self._ensure_field_profile(field_id, goal_text)
        data = self.store.snapshot(limit_per_bucket=None)
        selected: list[dict[str, Any]] = []
        for ref in selected_refs or []:
            bucket = self._v2_bucket(str(ref.get("bucket") or ""))
            record_id = str(ref.get("id") or ref.get("record_id") or "")
            item = data.get(bucket, {}).get(record_id)
            if item:
                selected.append({"bucket": bucket, "id": record_id, "item": self._v2_present_item(item, model_mode=model_mode)})
        idea = self._v2_synthesize_my_idea(profile, goal_text, selected, user_note, model_mode=model_mode, run_id=run_id)
        self._raise_if_cancelled(run_id)
        existed = [self._v2_present_item(item, model_mode=model_mode) for item in self._v2_project_records(data, field_id, "existed_ideas")]
        related_rows = self._v2_related_existed_ideas(idea, existed, model_mode=model_mode) or idea.get("related_existed_ideas") or []
        if related_rows and not self._v2_rows_are_repetitive(related_rows):
            idea["related_existed_ideas"] = related_rows
        stored = self._v2_store_my_idea_version({}, idea, model_mode=model_mode)
        self.store.upsert("my_ideas", stored, "idea_id")
        self.add_project_memberships(field_id, "my_ideas", [stored["idea_id"]], source="v2_generate", prepend=True)
        return {"ok": True, "idea": self._v2_present_item(stored, model_mode=model_mode), "generation_mode": stored.get("generation_mode", "fallback"), "version_action": "created"}

    def v2_regenerate_my_idea(
        self,
        *,
        field_id: str,
        idea_id: str,
        model_mode: str = "auto",
        version: str = "",
        run_id: str = "",
    ) -> dict[str, Any]:
        self._raise_if_cancelled(run_id)
        existing = self.store.get_item("my_ideas", idea_id)
        if not existing:
            raise KeyError(f"my_ideas:{idea_id} not found")
        existing = self._v2_materialize_my_idea_versions(existing)
        current = self._v2_present_item(existing, model_mode=model_mode, version_id=version)
        profile = self._ensure_field_profile(field_id, current.get("novelty_claim") or "")
        goal_text = profile.get("goal_text") or profile.get("query") or current.get("novelty_claim") or ""
        data = self.store.snapshot(limit_per_bucket=None)
        selected: list[dict[str, Any]] = []
        for ref in current.get("selected_refs") or []:
            bucket = self._v2_bucket(str(ref.get("bucket") or ""))
            record_id = str(ref.get("id") or ref.get("record_id") or "")
            item = data.get(bucket, {}).get(record_id)
            if item:
                selected.append({"bucket": bucket, "id": record_id, "item": self._v2_present_item(item, model_mode=model_mode)})
        target_model = self._v2_model_meta(model_mode)
        active_variant = current.get("active_variant") or {}
        same_model = (
            str(active_variant.get("provider") or "") == target_model["provider"]
            and str(active_variant.get("model_name") or "") == target_model["model_name"]
        )
        idea = self._v2_synthesize_my_idea(
            profile,
            goal_text,
            selected,
            str(current.get("user_note") or ""),
            model_mode=model_mode,
            run_id=run_id,
            prior_idea=current,
            existing_idea_id=idea_id,
        )
        self._raise_if_cancelled(run_id)
        existed = [self._v2_present_item(item, model_mode=model_mode) for item in self._v2_project_records(data, field_id, "existed_ideas")]
        related_rows = self._v2_related_existed_ideas(idea, existed, model_mode=model_mode) or idea.get("related_existed_ideas") or []
        if related_rows and not self._v2_rows_are_repetitive(related_rows):
            idea["related_existed_ideas"] = related_rows
        stored = self._v2_store_my_idea_version(existing, idea, model_mode=model_mode, idea_id=idea_id)
        self.store.upsert("my_ideas", stored, "idea_id")
        self.add_project_memberships(field_id, "my_ideas", [idea_id], source="v2_regenerate", prepend=True)
        return {
            "ok": True,
            "idea": self._v2_present_item(stored, model_mode=model_mode),
            "version_action": "updated" if same_model else "created",
        }

    def v2_my_idea_detail(self, field_id: str, idea_id: str, *, model_mode: str = "auto", version: str = "") -> dict[str, Any]:
        idea = self.store.get_item("my_ideas", idea_id)
        if not idea:
            raise KeyError(f"my_ideas:{idea_id} not found")
        materialized = self._v2_materialize_my_idea_versions(idea)
        if materialized != idea:
            self.store.upsert("my_ideas", materialized, "idea_id")
        presented_idea = self._v2_present_item(materialized, model_mode=model_mode, version_id=version)
        data = self.store.snapshot(limit_per_bucket=None)
        existed = [self._v2_present_item(item, model_mode=model_mode) for item in self._v2_project_records(data, field_id, "existed_ideas")]
        cached_related = [
            row
            for row in (presented_idea.get("related_existed_ideas") or [])
            if isinstance(row, dict) and not self._v2_related_row_is_template(row)
        ]
        related = [] if self._v2_rows_are_repetitive(cached_related) else cached_related
        principles = [self._v2_present_item(item, model_mode=model_mode) for item in self._v2_project_records(data, field_id, "principles")]
        active_variant = presented_idea.get("active_variant") or {}
        return {
            "project": data.get("field_profiles", {}).get(field_id) or {},
            "idea": self._v2_repair_my_idea_payload(presented_idea),
            "related_existed_ideas": related,
            "principle_map": self._v2_principle_map(presented_idea, principles, related),
            "source_evidence": self._v2_my_idea_sources(presented_idea, data, model_mode=model_mode),
            "reference_labels": self._v2_reference_labels(data, model_mode=model_mode),
            "comparison_warning": "" if related else (
                "No high-quality LLM comparison is available for this idea version. "
                "Regenerate the idea with a callable LLM to create non-templated related-idea comparisons."
            ),
            "generation_meta": {
                "model_mode": active_variant.get("model_mode", presented_idea.get("model_mode", "")),
                "model_name": active_variant.get("model_name", presented_idea.get("model_name", "")),
                "provider": active_variant.get("provider", presented_idea.get("provider", "")),
                "generation_mode": presented_idea.get("generation_mode", ""),
                "llm_error": presented_idea.get("llm_error", ""),
                "created_at": active_variant.get("extracted_at", presented_idea.get("created_at", "")),
                "selected_refs": presented_idea.get("selected_refs", []),
                "version_id": active_variant.get("version_id", ""),
                "versions": presented_idea.get("versions", []),
            },
        }

    def _v2_model_meta(self, model_mode: str) -> dict[str, str]:
        try:
            resolved = self.llm.resolve_model(mode=model_mode)
        except Exception:
            resolved = {"provider": "offline", "model": model_mode or "auto"}
        return {"model_mode": model_mode or "auto", "provider": resolved.get("provider", "offline"), "model_name": resolved.get("model", model_mode or "auto")}

    def _v2_research_query(self, goal_text: str) -> str:
        terms = keyword_terms(goal_text, 10)
        if not terms:
            return goal_text
        return " ".join(self._ordered_unique([goal_text, *terms]))

    def _v2_upsert_work(self, work: dict[str, Any], *, model_mode: str) -> dict[str, Any]:
        title = compact_text(work.get("title") or "Untitled work", 240)
        payload = {
            "title": title,
            "authors": work.get("authors") or [],
            "year": work.get("year"),
            "venue_or_source": work.get("venue_or_source") or work.get("source_type") or "online",
            "url_or_doi": work.get("url_or_doi") or "",
            "paper_link": work.get("url_or_doi") or "",
            "abstract": compact_text(work.get("abstract") or "", 2400),
            "source_type": work.get("source_type") or "paper",
            "validation_level": work.get("validation_level") or "L1",
            "citation_count": work.get("citation_count"),
            "community_signals": work.get("community_signals") or {},
            "source_urls": self._ordered_unique([*(work.get("source_urls") or []), work.get("url_or_doi") or ""]),
            "source_updated_at": work.get("source_updated_at") or "",
            "work_principles": work.get("work_principles") or [],
            "work_insights": work.get("work_insights") or [],
            "work_novelty": work.get("work_novelty") or [],
        }
        return self._v2_upsert_canonical("source_works", title, payload, model_mode=model_mode, existing_id=work.get("work_id") or "")

    def _v2_needs_llm_extraction(self, work: dict[str, Any], model_mode: str) -> bool:
        title = compact_text(work.get("title") or "Untitled work", 240)
        canonical_key = self._v2_canonical_key(title)
        existing = self._v2_find_by_key("source_works", canonical_key)
        if not existing:
            return True
        variants = list((existing.get("variants") or {}).values())
        exact = [variant for variant in variants if variant.get("model_mode") == model_mode and not variant.get("is_user_edit")]
        if not exact:
            return True
        latest = sorted(exact, key=lambda variant: variant.get("extracted_at", ""), reverse=True)[0]
        payload = dict(latest.get("payload") or {})
        old_abstract = compact_text(payload.get("abstract") or "", 2400)
        new_abstract = compact_text(work.get("abstract") or "", 2400)
        old_modified = str(payload.get("source_updated_at") or "")
        new_modified = str(work.get("source_updated_at") or "")
        if self._v2_canonical_key(payload.get("title") or "") != canonical_key:
            return True
        if old_abstract != new_abstract:
            return True
        if new_modified and old_modified != new_modified:
            return True
        return False

    def _v2_sort_score(self, item: dict[str, Any], query: str = "") -> tuple[float, int, float, float, str]:
        body = json.dumps(item, ensure_ascii=False)
        relevance = lexical_score(query, body) if query else 0.0
        venue = str(item.get("venue_or_source") or item.get("source") or "")
        peer_score = float(self._venue_quality_rank(venue))
        year = int(item.get("year") or 0) if str(item.get("year") or "").isdigit() else 0
        confidence = float(item.get("confidence_score", 0) or 0)
        recency_bonus = min(max(year - 2015, 0), 15) / 15 if year else 0.0
        updated = str(item.get("updated_at") or item.get("created_at") or "")
        return (relevance * 4.0 + peer_score + recency_bonus + confidence, year, relevance, confidence, updated)

    def _venue_quality_rank(self, venue: str) -> int:
        value = str(venue or "").lower()
        if not value:
            return 0
        top = [
            "neurips",
            "icml",
            "iclr",
            "cvpr",
            "iccv",
            "eccv",
            "acl",
            "emnlp",
            "naacl",
            "colm",
            "kdd",
            "www",
            "sigir",
            "aaai",
            "ijcai",
            "jmlr",
            "tmlr",
            "tpami",
            "nature",
            "science",
        ]
        if any(term in value for term in top):
            return 4
        if "arxiv" in value:
            return 1
        if value not in {"openalex", "crossref", "local extraction", "online"}:
            return 3
        return 2

    def _v2_upsert_canonical(
        self,
        bucket: str,
        key_text: str,
        payload: dict[str, Any],
        *,
        model_mode: str,
        is_user_edit: bool = False,
        existing_id: str = "",
    ) -> dict[str, Any]:
        bucket = self._v2_bucket(bucket)
        id_key = self._record_id_key(bucket)
        prefix = {
            "source_works": "W",
            "existed_ideas": "XI",
            "principles": "P",
            "takeaway_messages": "TM",
            "benchmark_records": "B",
            "baseline_records": "BL",
            "my_ideas": "MI",
        }.get(bucket, "C")
        canonical_key = self._v2_canonical_key(key_text)
        record_id = existing_id or stable_id(prefix, canonical_key)
        item = self.store.get_item(bucket, record_id) or {}
        if not item and bucket == "source_works":
            by_key = self._v2_find_by_key(bucket, canonical_key)
            if by_key:
                item = by_key
                record_id = by_key.get(id_key, record_id)
        model = self._v2_model_meta(model_mode)
        variant_id = stable_id("VER", record_id, "manual" if is_user_edit else model["provider"], "manual" if is_user_edit else model["model_name"])
        variants = dict(item.get("variants") or {})
        prior_payload = dict((variants.get(variant_id) or {}).get("payload") or {})
        merged_payload = self._v2_merge_payloads(prior_payload, payload)
        variants[variant_id] = {
            "version_id": variant_id,
            "model_mode": "manual" if is_user_edit else model["model_mode"],
            "model_name": "manual" if is_user_edit else model["model_name"],
            "provider": "user" if is_user_edit else model["provider"],
            "entered_at": (variants.get(variant_id) or {}).get("entered_at") or utc_now(),
            "extracted_at": utc_now(),
            "payload": merged_payload,
            "source_urls": self._ordered_unique([*(payload.get("source_urls") or []), *(payload.get("source_paper_links") or []), payload.get("paper_link", ""), payload.get("official_url", "")]),
            "confidence_score": float(payload.get("confidence_score", 0.62) or 0.62),
            "needs_review": bool(payload.get("needs_review", False)),
            "is_user_edit": bool(is_user_edit),
        }
        active_id = item.get("active_version_id") or variant_id
        active_variant = variants.get(active_id) or {}
        if is_user_edit or not active_variant.get("is_user_edit"):
            active_id = variant_id
        active_payload = dict(variants.get(active_id, {}).get("payload") or merged_payload)
        base = {
            **item,
            **active_payload,
            id_key: record_id,
            "canonical_id": item.get("canonical_id") or record_id,
            "canonical_key": item.get("canonical_key") or canonical_key,
            "active_version_id": active_id,
            "variants": variants,
            "model_mode": variants[active_id]["model_mode"],
            "model_name": variants[active_id]["model_name"],
            "provider": variants[active_id]["provider"],
            "entered_at": variants[active_id]["entered_at"],
            "extracted_at": variants[active_id]["extracted_at"],
            "confidence_score": variants[active_id]["confidence_score"],
            "created_at": item.get("created_at") or utc_now(),
            "updated_at": utc_now(),
        }
        if bucket == "principles":
            base.setdefault("principle_id", record_id)
            base.setdefault("name", active_payload.get("name") or active_payload.get("title") or key_text)
            base.setdefault("principle_type", "empirical_principle")
            base.setdefault("abstraction_level", "L2")
            base.setdefault("source_works", active_payload.get("source_work_ids") or active_payload.get("source_works") or [])
            base.setdefault("validation_level", "L1")
        self.store.upsert(bucket, base, id_key)
        return base

    def _v2_extract_concepts_from_work(self, goal_text: str, work: dict[str, Any], llm_extra: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        text = " ".join([work.get("title", ""), work.get("abstract", ""), " ".join(work.get("work_principles", [])), " ".join(work.get("work_insights", [])), " ".join(work.get("work_novelty", []))])
        source = self._v2_source_payload(work)
        if llm_extra:
            novelty_raw = llm_extra.get("existed_ideas", []) or self._extract_novelty_points(text) or work.get("work_novelty", [])
            principle_raw = llm_extra.get("principles", []) or work.get("work_principles", []) or self._extract_principle_sentences(text)
            message_raw = llm_extra.get("takeaway_messages", []) or self._extract_insight_messages(text) or work.get("work_insights", [])
        else:
            novelty_raw = self._extract_novelty_points(text) or work.get("work_novelty", [])
            principle_raw = work.get("work_principles", []) or self._extract_principle_sentences(text)
            message_raw = self._extract_insight_messages(text) or work.get("work_insights", [])
        novelty = self._v2_normalize_concepts(novelty_raw, kind="idea", work=work, text=text, goal_text=goal_text, allow_fallback=True)
        principles = self._v2_normalize_concepts(principle_raw, kind="principle", work=work, text=text, goal_text=goal_text, allow_fallback=True)
        messages = self._v2_normalize_concepts(message_raw, kind="message", work=work, text=text, goal_text=goal_text, allow_fallback=True)
        return {
            "existed_ideas": [
                {
                    **source,
                    "title": item["title"],
                    "idea_text": item["text"],
                    "mechanism": item.get("mechanism", ""),
                    "summary": compact_text(item["text"], 240),
                    "source_work_ids": [work["work_id"]],
                    "evidence": item.get("evidence") or compact_text(text, 360),
                    "confidence_score": 0.72 if llm_extra else 0.58,
                }
                for item in novelty[:5]
            ],
            "principles": [
                {
                    **source,
                    "name": item["title"],
                    "abstract_signature": item["text"],
                    "mechanism": item.get("mechanism") or item["text"],
                    "boundary_conditions": item.get("boundary_conditions", []),
                    "problem_pressure": compact_text(goal_text, 240),
                    "objective": item.get("objective") or "Capture a reusable mechanism evidenced by the source work.",
                    "source_work_ids": [work["work_id"]],
                    "source_works": [work["work_id"]],
                    "evidence": item.get("evidence") or compact_text(text, 360),
                    "confidence_score": 0.68 if llm_extra else 0.52,
                }
                for item in principles[:5]
            ],
            "takeaway_messages": [
                {
                    **source,
                    "title": item["title"],
                    "message_text": item["text"],
                    "condition": item.get("condition", ""),
                    "finding": item.get("finding", ""),
                    "actionable_lesson": item.get("actionable_lesson", ""),
                    "source_work_ids": [work["work_id"]],
                    "evidence": item.get("evidence") or compact_text(text, 360),
                    "confidence_score": 0.7 if llm_extra else 0.54,
                }
                for item in messages[:6]
            ],
        }

    def _v2_normalize_concepts(
        self,
        raw_items: Any,
        *,
        kind: str,
        work: dict[str, Any],
        text: str,
        goal_text: str,
        allow_fallback: bool = True,
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        items = raw_items if isinstance(raw_items, list) else [raw_items]
        for raw in items:
            if isinstance(raw, dict):
                source_text = (
                    raw.get("idea_text")
                    or raw.get("message_text")
                    or raw.get("abstract_signature")
                    or raw.get("text")
                    or raw.get("summary")
                    or raw.get("title")
                    or raw.get("name")
                    or ""
                )
                if not source_text:
                    continue
                title = raw.get("title") or raw.get("name") or source_text
                item = {
                    "title": compact_text(str(title), 92),
                    "text": compact_text(str(source_text), 520),
                    "mechanism": compact_text(raw.get("mechanism", ""), 420),
                    "condition": compact_text(raw.get("condition", ""), 180),
                    "finding": compact_text(raw.get("finding", ""), 260),
                    "actionable_lesson": compact_text(raw.get("actionable_lesson", ""), 260),
                    "objective": compact_text(raw.get("objective", ""), 220),
                    "boundary_conditions": self._listify(raw.get("boundary_conditions")),
                    "evidence": compact_text(raw.get("evidence", ""), 360),
                }
            else:
                source_text = str(raw or "").strip()
                if not source_text:
                    continue
                item = self._v2_rewrite_concept(source_text, kind=kind, work=work, text=text, goal_text=goal_text)
            if not self._v2_is_high_quality_concept(item["text"], kind=kind):
                continue
            normalized.append(item)
        if allow_fallback and not normalized:
            fallback = self._v2_rewrite_concept(text, kind=kind, work=work, text=text, goal_text=goal_text)
            if self._v2_is_high_quality_concept(fallback["text"], kind=kind):
                normalized.append(fallback)
        seen: set[str] = set()
        output = []
        for item in normalized:
            key = self._v2_canonical_key(item["text"])
            if key in seen:
                continue
            seen.add(key)
            output.append(item)
        return output

    def _v2_rewrite_concept(self, source_text: str, *, kind: str, work: dict[str, Any], text: str, goal_text: str) -> dict[str, Any]:
        title = compact_text(work.get("title") or "Source work", 90)
        cleaned = self._strip_fact_prefix(compact_text(source_text, 520))
        method = self._v2_method_phrase(work, cleaned)
        pressure = self._v2_pressure_phrase(goal_text, text)
        evidence = self._first_matching_sentence(text, ["propose", "introduce", "evaluate", "show", "under", "when", "compare", "benchmark"])
        if kind == "idea":
            body = compact_text(f"{method} turns {pressure} into a concrete mechanism rather than treating it as a generic performance claim.", 420)
            label = compact_text(method, 88)
            mechanism = compact_text(cleaned, 360)
        elif kind == "principle":
            rule = self._v2_principle_rule(cleaned, pressure)
            body = compact_text(rule, 420)
            label = compact_text(rule, 88)
            mechanism = body
        else:
            message = self._v2_takeaway_message(cleaned, pressure)
            body = compact_text(message, 460)
            label = compact_text(message, 88)
            mechanism = ""
        return {
            "title": label or title,
            "text": body,
            "mechanism": mechanism,
            "condition": pressure if kind == "message" else "",
            "finding": body if kind == "message" else "",
            "actionable_lesson": compact_text(f"Use this as a design or evaluation constraint for {pressure}.", 240) if kind == "message" else "",
            "objective": compact_text(f"Reuse the mechanism for {pressure}.", 220) if kind == "principle" else "",
            "boundary_conditions": [pressure] if kind == "principle" and pressure else [],
            "evidence": evidence,
        }

    def _v2_is_high_quality_concept(self, text: str, *, kind: str) -> bool:
        value = compact_text(text, 600)
        lower = value.lower()
        if len(value) < 42:
            return False
        blocked = [
            "achieves state of the art",
            "achieves state-of-the-art",
            "experiments demonstrate the effectiveness",
            "extensive experiments demonstrate",
            "the paper proposes a method",
            "this work proposes a method",
        ]
        if any(term in lower for term in blocked):
            return False
        if kind == "idea":
            return bool(re.search(r"\b(turns?|uses?|routes?|separates?|aligns?|adapts?|regularizes?|conditions?|grounds?|constrains?|allocates?|couples?)\b", lower))
        if kind == "principle":
            return bool(re.search(r"\b(when|under|if|because|only when|rather than|trade[- ]off|invariant|constraint|mechanism)\b", lower))
        return bool(re.search(r"\b(when|under|improves?|fails?|reduces?|helps?|hurts?|more|less|only|not|instead|trade[- ]off)\b", lower))

    def _v2_method_phrase(self, work: dict[str, Any], source_text: str) -> str:
        source = source_text.strip()
        patterns = [
            r"(?:propose|introduce|present|develop|design)s?\s+([^.;]{12,160})",
            r"(?:novelty|contribution|innovation)\s+(?:is|lies in|comes from)\s+([^.;]{12,160})",
        ]
        for pattern in patterns:
            match = re.search(pattern, source, flags=re.IGNORECASE)
            if match:
                return compact_text(self._clean_extracted_entity(match.group(1)), 140)
        return compact_text(work.get("title") or source, 140)

    def _v2_pressure_phrase(self, goal_text: str, text: str) -> str:
        lower = f"{goal_text} {text}".lower()
        if "few-shot" in lower or "few shot" in lower or "clip" in lower:
            return "few-shot vision-language adaptation under distribution and resource constraints"
        if "sparse" in lower and ("3d" in lower or "reconstruction" in lower):
            return "geometry recovery from too few reliable views"
        if "rul" in lower or "remaining useful life" in lower:
            return "remaining-life prediction under noisy cross-sensor degradation"
        if "multi-agent" in lower or "mas" in lower or "reasoning" in lower:
            return "multi-agent reasoning where communication budget and correctness compete"
        terms = keyword_terms(goal_text or text, 7)
        return " ".join(terms[:5]) or "the target research pressure"

    def _v2_principle_rule(self, source_text: str, pressure: str) -> str:
        lower = source_text.lower()
        if "uncertain" in lower or "confidence" in lower or "entropy" in lower:
            return f"When evidence quality is uneven, adaptation should be gated by uncertainty before changing the main representation for {pressure}."
        if "prompt" in lower and ("clip" in lower or "vision" in lower):
            return f"In prompt-based transfer, preserving the pretrained semantic prior matters as much as fitting the few-shot samples for {pressure}."
        if "baseline" in lower or "compare" in lower:
            return f"A method claim is reusable only when the nearest competing method is held fixed on the same benchmark protocol for {pressure}."
        if "route" in lower or "select" in lower:
            return f"Routing is valuable when different samples expose different bottlenecks; the selector must be evaluated as part of the mechanism for {pressure}."
        return f"Under {pressure}, the reusable principle is to isolate the bottleneck mechanism before adding model capacity."

    def _v2_takeaway_message(self, source_text: str, pressure: str) -> str:
        lower = source_text.lower()
        if "not" in lower or "fail" in lower or "hurt" in lower:
            return f"Negative evidence matters: under {pressure}, a stronger-looking adaptation can fail when its assumption does not match the evaluation split."
        if "calibration" in lower:
            return f"Calibration can be a first-class success signal under {pressure}, especially when accuracy alone hides rare-class or shift failures."
        if "latency" in lower or "gpu" in lower or "compute" in lower:
            return f"Compute cost should be reported with the main metric under {pressure}; otherwise complex methods can beat baselines only by spending more budget."
        if "base-to-novel" in lower or "few-shot" in lower:
            return f"Base-to-novel transfer is the diagnostic slice for {pressure}; gains on base classes alone are not enough evidence."
        return f"Use the source result as a reusable lesson for {pressure}: identify the condition where the method helps, not just whether it improves an average score."

    def _v2_benchmark_payload(self, benchmark: dict[str, Any], work: dict[str, Any]) -> dict[str, Any]:
        dataset = benchmark.get("dataset") or benchmark.get("benchmark_name") or benchmark.get("name") or ""
        info = self._benchmark_catalog_info(dataset)
        official_url = benchmark.get("official_url") or benchmark.get("dataset_url") or benchmark.get("download_url") or info.get("official_url", "")
        metrics = benchmark.get("metrics") if isinstance(benchmark.get("metrics"), list) else []
        metrics = self._ordered_unique([benchmark.get("metric", ""), *metrics, *(info.get("metrics") or [])])
        public_dataset = bool(official_url) and dataset.lower() != "unspecified local benchmark"
        return {
            **self._v2_source_payload(work),
            "benchmark_name": dataset or "Unspecified benchmark",
            "dataset": dataset or "Unspecified benchmark",
            "task": benchmark.get("task", ""),
            "official_url": official_url,
            "candidate_dataset_pages": [] if official_url else [f"https://huggingface.co/datasets?search={dataset.replace(' ', '%20')}"] if dataset else [],
            "data_form": benchmark.get("data_form") or info.get("data_form") or benchmark.get("split", ""),
            "scale": benchmark.get("scale") or info.get("scale", ""),
            "metrics": metrics,
            "metric": benchmark.get("metric") or (metrics[0] if metrics else ""),
            "source": info.get("source") or work.get("venue_or_source", ""),
            "description": benchmark.get("description") or info.get("description") or benchmark.get("task", ""),
            "public_dataset": public_dataset,
            "source_work_ids": [work["work_id"]],
            "evidence": compact_text(benchmark.get("evidence") or benchmark.get("evidence_text") or json.dumps(benchmark, ensure_ascii=False), 360),
            "confidence_score": benchmark.get("confidence_score", 0.58),
            "needs_review": not public_dataset,
        }

    def _v2_baseline_payload(self, baseline: dict[str, Any], work: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
        info = self._baseline_catalog_info(baseline.get("baseline_name", ""))
        benchmark_names = [
            item.get("benchmark_name") or item.get("dataset") or item.get("benchmark_id", "")
            for item in baseline.get("benchmarks", []) or []
            if isinstance(item, dict)
        ]
        if not benchmark_names:
            benchmark_names = [str(item) for item in baseline.get("benchmarks", []) or [] if str(item).strip()]
        if not benchmark_names:
            benchmark_names = [baseline.get("benchmark_id", "")]
        return {
            **self._v2_source_payload(work),
            "baseline_name": baseline.get("baseline_name") or "Baseline",
            "baseline_type": baseline.get("baseline_type") or baseline.get("type") or "published",
            "description": info.get("description") or f"{baseline.get('baseline_name', 'Baseline')} is a compared or proposed method tracked from source work evidence.",
            "principle": info.get("principle") or "Method principle should be verified from the linked source paper.",
            "source_paper_link": baseline.get("source_paper_link") or info.get("source_paper_link") or (work.get("url_or_doi", "") if baseline.get("baseline_type") == "proposed_method" else ""),
            "official_code_url": baseline.get("official_code_url") or baseline.get("code_url") or info.get("official_code_url") or next((result.get("code_url") for result in results if isinstance(result, dict) and result.get("code_url")), ""),
            "benchmarks": self._ordered_unique(benchmark_names),
            "performance": results,
            "source_work_ids": [work["work_id"]],
            "evidence": compact_text(baseline.get("evidence") or baseline.get("evidence_text") or json.dumps(baseline, ensure_ascii=False), 360),
            "confidence_score": baseline.get("confidence_score", 0.55),
            "needs_review": not bool(baseline.get("source_paper_link") or info.get("source_paper_link") or info.get("official_code_url")),
        }

    def _v2_synthesize_my_idea(
        self,
        profile: dict[str, Any],
        goal_text: str,
        selected: list[dict[str, Any]],
        user_note: str,
        *,
        model_mode: str,
        run_id: str = "",
        prior_idea: dict[str, Any] | None = None,
        existing_idea_id: str = "",
    ) -> dict[str, Any]:
        field_id = profile.get("field_id", "default")
        context = [
            {
                "bucket": ref["bucket"],
                "id": ref["id"],
                "title": ref["item"].get("title") or ref["item"].get("name") or ref["item"].get("benchmark_name") or ref["item"].get("baseline_name"),
                "text": ref["item"].get("idea_text") or ref["item"].get("message_text") or ref["item"].get("abstract_signature") or ref["item"].get("summary") or ref["item"].get("description"),
            }
            for ref in selected
        ]
        if not self.llm.available():
            raise RuntimeError("The selected LLM is not available because no API key is configured. Open API Keys and configure the provider before generating an idea.")
        try:
            self._raise_if_cancelled(run_id)
            prior_context = ""
            if prior_idea:
                prior_context = (
                    "\nPrior version to regenerate, improve, and keep comparable: "
                    f"{json.dumps({key: prior_idea.get(key) for key in ['title', 'one_sentence_thesis', 'novelty_claim', 'mechanistic_design', 'why_it_might_work', 'validation_protocol', 'derived_principles']}, ensure_ascii=False)}"
                )
            payload = self.llm.chat_json(
                "You generate one rigorous research idea for Principia. Return strict JSON only.",
                (
                    "Use the user's own note as first-priority evidence, then use selected existed ideas/principles/messages. "
                    "Return keys: title, novelty_claim, mechanistic_design(list), why_it_might_work(list), validation_protocol(list), "
                    "relevant_baselines(list), metrics(list), risks(list), derived_principles(list), one_sentence_thesis. "
                    "Also return related_existed_ideas(list) if prior idea evidence is provided, where each row has: "
                    "id, similarity, differences, potential_advantage, potential_weakness. These comparison rows must be substantive, "
                    "mechanism-level, non-repetitive, and must not all begin with the same phrase.\n\n"
                    f"Project: {profile.get('name')}\nGoal: {goal_text}\nUser note: {user_note}\nSelected evidence: {json.dumps(context, ensure_ascii=False)}{prior_context}"
                ),
                complexity=0.75,
                mode=model_mode,
                max_tokens=3200,
                temperature=0.25,
            )
            self._raise_if_cancelled(run_id)
        except Exception as exc:
            if isinstance(exc, CancelledRun):
                raise
            raise RuntimeError(f"The selected LLM could not be called, so no idea was generated. {self._friendly_llm_error(exc)}") from exc
        if not payload:
            raise RuntimeError("The selected LLM returned an empty response, so no idea was generated.")
        model = self._v2_model_meta(model_mode)
        idea_id = existing_idea_id or stable_id("MI", field_id, payload.get("title", ""), user_note, utc_now())
        idea = {
            "idea_id": idea_id,
            "field_id": field_id,
            "title": payload.get("title") or "Generated Idea",
            "one_sentence_thesis": payload.get("one_sentence_thesis") or payload.get("novelty_claim") or "",
            "novelty_claim": payload.get("novelty_claim", ""),
            "mechanistic_design": self._listify(payload.get("mechanistic_design")),
            "why_it_might_work": self._listify(payload.get("why_it_might_work")),
            "validation_protocol": self._listify(payload.get("validation_protocol")),
            "relevant_baselines": self._listify(payload.get("relevant_baselines")),
            "metrics": self._listify(payload.get("metrics")),
            "risks": self._listify(payload.get("risks")),
            "derived_principles": self._listify(payload.get("derived_principles")),
            "selected_refs": [{"bucket": ref["bucket"], "id": ref["id"]} for ref in selected],
            "user_note": user_note,
            "model_mode": model["model_mode"],
            "model_name": model["model_name"],
            "provider": model["provider"],
            "generation_mode": "llm",
            "llm_error": "",
            "related_existed_ideas": [
                row for row in (payload.get("related_existed_ideas") or []) if isinstance(row, dict)
            ],
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }
        return self._v2_repair_my_idea_payload(idea)

    def _v2_materialize_my_idea_versions(self, idea: dict[str, Any]) -> dict[str, Any]:
        if not idea:
            return idea
        variants = dict(idea.get("variants") or {})
        if variants:
            return idea
        idea_id = str(idea.get("idea_id") or stable_id("MI", idea.get("field_id", ""), idea.get("title", ""), utc_now()))
        provider = str(idea.get("provider") or "unknown")
        model_name = str(idea.get("model_name") or idea.get("model_mode") or "unknown")
        model_mode = str(idea.get("model_mode") or "auto")
        version_id = stable_id("MIV", idea_id, provider, model_name)
        payload = {key: value for key, value in idea.items() if key not in {"variants", "active_version_id", "active_variant"}}
        payload["idea_id"] = idea_id
        variant = {
            "version_id": version_id,
            "model_mode": model_mode,
            "model_name": model_name,
            "provider": provider,
            "entered_at": idea.get("created_at") or idea.get("updated_at") or utc_now(),
            "extracted_at": idea.get("updated_at") or idea.get("created_at") or utc_now(),
            "payload": payload,
            "source_urls": idea.get("source_urls", []),
            "confidence_score": idea.get("confidence_score", 0.72),
            "needs_review": bool(idea.get("needs_review", False)),
            "is_user_edit": bool(idea.get("is_user_edit", False)),
        }
        return {**idea, "idea_id": idea_id, "variants": {version_id: variant}, "active_version_id": version_id}

    def _v2_store_my_idea_version(
        self,
        existing: dict[str, Any],
        payload: dict[str, Any],
        *,
        model_mode: str,
        idea_id: str = "",
    ) -> dict[str, Any]:
        model = self._v2_model_meta(model_mode)
        base = self._v2_materialize_my_idea_versions(existing) if existing else {}
        idea_id = idea_id or str(payload.get("idea_id") or base.get("idea_id") or stable_id("MI", payload.get("field_id", ""), payload.get("title", ""), utc_now()))
        payload = self._v2_repair_my_idea_payload({**payload, "idea_id": idea_id})
        payload["model_mode"] = model["model_mode"]
        payload["model_name"] = model["model_name"]
        payload["provider"] = model["provider"]
        payload["updated_at"] = utc_now()
        payload.setdefault("created_at", base.get("created_at") or utc_now())
        version_id = stable_id("MIV", idea_id, model["provider"], model["model_name"])
        variants = dict(base.get("variants") or {})
        variants[version_id] = {
            "version_id": version_id,
            "model_mode": model["model_mode"],
            "model_name": model["model_name"],
            "provider": model["provider"],
            "entered_at": variants.get(version_id, {}).get("entered_at") or utc_now(),
            "extracted_at": utc_now(),
            "payload": payload,
            "source_urls": payload.get("source_urls", []),
            "confidence_score": payload.get("confidence_score", 0.78),
            "needs_review": bool(payload.get("needs_review", False)),
            "is_user_edit": bool(payload.get("is_user_edit", False)),
        }
        return {
            **base,
            **payload,
            "idea_id": idea_id,
            "variants": variants,
            "active_version_id": version_id,
            "updated_at": payload["updated_at"],
            "created_at": base.get("created_at") or payload.get("created_at") or utc_now(),
        }

    def _v2_present_item(self, item: dict[str, Any], *, model_mode: str = "auto", version_id: str = "") -> dict[str, Any]:
        active = self._v2_active_variant(item, model_mode=model_mode, version_id=version_id)
        payload = dict(active.get("payload") or {})
        if item.get("benchmark_id") or payload.get("benchmark_name") or payload.get("dataset"):
            payload = self._v2_enrich_benchmark_payload(payload)
        if item.get("baseline_id") or payload.get("baseline_name"):
            payload = self._v2_enrich_baseline_payload(payload)
        if item.get("idea_id") and ("novelty_claim" in payload or "mechanistic_design" in payload or "one_sentence_thesis" in payload):
            payload = self._v2_repair_my_idea_payload(payload)
        if (item.get("canonical_id") or payload.get("message_text")) and (payload.get("message_text") or payload.get("actionable_lesson")):
            payload = self._v2_repair_takeaway_payload(payload)
        versions = [
            {
                "version_id": vid,
                "model_mode": variant.get("model_mode", ""),
                "model_name": variant.get("model_name", ""),
                "provider": variant.get("provider", ""),
                "is_user_edit": bool(variant.get("is_user_edit")),
                "confidence_score": variant.get("confidence_score", 0),
                "extracted_at": variant.get("extracted_at", ""),
            }
            for vid, variant in (item.get("variants") or {}).items()
        ]
        return {**item, **payload, "active_variant": active, "versions": versions}

    def _v2_enrich_benchmark_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        enriched = dict(payload)
        dataset = enriched.get("dataset") or enriched.get("benchmark_name") or ""
        info = self._benchmark_catalog_info(dataset)
        for key in ("description", "data_form", "scale", "source"):
            if not enriched.get(key) and info.get(key):
                enriched[key] = info[key]
        if not enriched.get("official_url") and info.get("official_url"):
            enriched["official_url"] = info["official_url"]
        metrics = enriched.get("metrics") if isinstance(enriched.get("metrics"), list) else []
        enriched["metrics"] = self._ordered_unique([*(metrics or []), enriched.get("metric", ""), *(info.get("metrics") or [])])
        enriched["public_dataset"] = self._v2_is_official_benchmark_record(enriched)
        if not enriched.get("candidate_dataset_pages") and dataset and not enriched.get("official_url"):
            enriched["candidate_dataset_pages"] = []
        return enriched

    def _v2_enrich_baseline_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        enriched = dict(payload)
        info = self._baseline_catalog_info(enriched.get("baseline_name", ""))
        for key in ("description", "principle", "source"):
            if not enriched.get(key) and info.get(key):
                enriched[key] = info[key]
        if not enriched.get("source_paper_link") and info.get("source_paper_link"):
            enriched["source_paper_link"] = info["source_paper_link"]
        if not enriched.get("official_code_url") and info.get("official_code_url"):
            enriched["official_code_url"] = info["official_code_url"]
        return enriched

    def _v2_is_official_benchmark_record(self, item: dict[str, Any]) -> bool:
        dataset = str(item.get("dataset") or item.get("benchmark_name") or "").strip()
        if not dataset or "unspecified" in dataset.lower() or dataset.lower() in {"benchmark", "dataset"}:
            return False
        info = self._benchmark_catalog_info(dataset)
        official_url = str(item.get("official_url") or info.get("official_url") or "").strip()
        if not official_url:
            return False
        if official_url.startswith("https://huggingface.co/datasets?search="):
            return False
        return True

    def _v2_repair_takeaway_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        repaired = dict(payload)
        text = str(repaired.get("message_text") or repaired.get("summary") or "").strip()
        title = str(repaired.get("title") or "").strip()
        if not text and not title:
            return repaired
        bad_prefixes = (
            "use the source result as a reusable lesson",
            "negative evidence matters:",
            "under few-shot vision-language adaptation",
            "under multi-agent reasoning where communication",
        )
        lower = f"{title} {text}".lower()
        if not any(prefix in lower for prefix in bad_prefixes):
            return repaired
        evidence = " ".join(
            str(repaired.get(key) or "")
            for key in ("evidence", "source_work_title", "source_paper_title", "finding", "condition", "actionable_lesson")
        )
        specific = self._v2_specific_takeaway(evidence or text or title)
        if specific:
            repaired["message_text"] = specific
            repaired["title"] = compact_text(specific, 96).rstrip(".")
            if not repaired.get("finding"):
                repaired["finding"] = specific
            if not repaired.get("actionable_lesson"):
                repaired["actionable_lesson"] = self._v2_actionable_lesson_from_takeaway(specific)
        return repaired

    def _v2_specific_takeaway(self, text: str) -> str:
        candidates = []
        for sentence in sentence_split(text):
            clean = self._strip_fact_prefix(sentence)
            lower = clean.lower()
            if len(clean) < 36:
                continue
            if any(term in lower for term in ["show", "find", "observe", "improve", "reduce", "fail", "not ", "under", "when", "ablation", "latency", "accuracy", "token", "cost", "benchmark"]):
                clean = re.sub(r"^(we|this work|the paper)\s+(show|shows|find|finds|observe|observes|demonstrate|demonstrates)\s+(that\s+)?", "", clean, flags=re.IGNORECASE).strip()
                candidates.append(compact_text(clean, 420))
        if candidates:
            return candidates[0]
        terms = keyword_terms(text, 8)
        if len(terms) >= 3:
            return compact_text(f"{terms[0].title()} depends on {terms[1]} and should be evaluated against {terms[2]} rather than summarized as an average gain.", 360)
        return ""

    def _v2_actionable_lesson_from_takeaway(self, text: str) -> str:
        lower = text.lower()
        if "token" in lower or "cost" in lower or "latency" in lower:
            return "Report quality and cost together; do not let a larger inference budget masquerade as a better method."
        if "benchmark" in lower or "accuracy" in lower:
            return "Pin the benchmark split and metric before comparing methods."
        if "fail" in lower or "not " in lower:
            return "Use the negative case as an ablation target before adding complexity."
        return "Turn the finding into one validation constraint for the next generated idea."

    def _v2_repair_my_idea_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        repaired = dict(payload)
        title = str(repaired.get("title") or "").strip()
        thesis = str(repaired.get("one_sentence_thesis") or "").strip()
        if not title or "..." in title or (thesis and title.lower() == thesis.lower()):
            repaired["title"] = self._v2_title_from_idea(repaired)
        if not thesis or thesis.lower() == str(repaired.get("title", "")).lower():
            mechanisms = self._listify(repaired.get("mechanistic_design"))
            first = mechanisms[0] if mechanisms else repaired.get("novelty_claim", "")
            repaired["one_sentence_thesis"] = compact_text(
                first or "A project-specific idea that links selected evidence to a falsifiable validation path.",
                520,
            )
        return repaired

    def _v2_title_from_idea(self, idea: dict[str, Any]) -> str:
        text = " ".join(
            [
                idea.get("user_note", ""),
                idea.get("novelty_claim", ""),
                " ".join(self._listify(idea.get("mechanistic_design"))[:3]),
            ]
        )
        terms = self._v2_mechanism_terms(text)
        if "benchmark" in terms and "uncertainty" in terms and ("prompt" in terms or "routing" in terms):
            return "Benchmark-Uncertainty Prompt Router"
        if "logical" in text.lower() or "logic" in text.lower():
            return "Inference-Time Logical Pattern Transfer"
        if "token" in terms and ("communication" in terms or "reasoning" in terms):
            return "Token-Budgeted Reasoning Pattern Extractor"
        strong = [term for term in terms if len(term) > 4][:4]
        return compact_text(" ".join(term.title() for term in strong) or "Evidence-Guided Research Idea", 110).rstrip(".")

    def _v2_active_variant(self, item: dict[str, Any], *, model_mode: str = "auto", version_id: str = "") -> dict[str, Any]:
        variants = dict(item.get("variants") or {})
        if not variants:
            return {"version_id": "", "payload": dict(item)}
        if version_id and version_id in variants:
            return variants[version_id]
        manual = [variant for variant in variants.values() if variant.get("is_user_edit")]
        if manual:
            return sorted(manual, key=lambda variant: variant.get("extracted_at", ""), reverse=True)[0]
        if model_mode and model_mode != "auto":
            exact = [variant for variant in variants.values() if variant.get("model_mode") == model_mode]
            if exact:
                return sorted(exact, key=lambda variant: variant.get("extracted_at", ""), reverse=True)[0]
        active = item.get("active_version_id", "")
        if active in variants:
            return variants[active]
        return sorted(variants.values(), key=lambda variant: (float(variant.get("confidence_score", 0) or 0), variant.get("extracted_at", "")), reverse=True)[0]

    def _v2_active_payload(self, item: dict[str, Any]) -> dict[str, Any]:
        return dict(self._v2_active_variant(item).get("payload") or item)

    def _v2_project_records(self, data: dict[str, Any], field_id: str, bucket: str, query: str = "") -> list[dict[str, Any]]:
        bucket = self._v2_bucket(bucket)
        records = data.get(bucket, {})
        if field_id == "default":
            items = list(records.values())
        else:
            ids = [
                member.get("record_id", "")
                for member in data.get("project_memberships", {}).values()
                if member.get("field_id") == field_id and member.get("bucket") == bucket and not member.get("hidden")
            ]
            if not ids and bucket in {"source_works", "principles"}:
                legacy_key = "work_ids" if bucket == "source_works" else "principle_ids"
                ids = list((data.get("field_profiles", {}).get(field_id) or {}).get(legacy_key) or [])
            items = [records[item_id] for item_id in ids if item_id in records]
        if query:
            items = self._query_items(items, query)
        if bucket == "benchmark_records":
            items = [item for item in items if self._v2_is_official_benchmark_record(item)]
        return items

    def _v2_bucket(self, bucket: str) -> str:
        return {
            "works": "source_works",
            "work": "source_works",
            "existedIdeas": "existed_ideas",
            "existed_idea": "existed_ideas",
            "existed_ideas": "existed_ideas",
            "principle": "principles",
            "principles": "principles",
            "messages": "takeaway_messages",
            "takeaway": "takeaway_messages",
            "takeaway_messages": "takeaway_messages",
            "benchmark": "benchmark_records",
            "benchmarks": "benchmark_records",
            "benchmark_records": "benchmark_records",
            "baseline": "baseline_records",
            "baselines": "baseline_records",
            "baseline_records": "baseline_records",
            "myIdeas": "my_ideas",
            "my_idea": "my_ideas",
            "my_ideas": "my_ideas",
        }.get(bucket, bucket)

    def _v2_canonical_key(self, text: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()[:180]

    def _v2_find_by_key(self, bucket: str, canonical_key: str) -> dict[str, Any] | None:
        for item in self.store.list_items(bucket, limit=100000):
            if item.get("canonical_key") == canonical_key:
                return item
        return None

    def _v2_merge_payloads(self, current: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        merged = {**current, **{key: value for key, value in incoming.items() if value not in (None, "", [])}}
        for key in ("source_work_ids", "source_works", "source_urls", "source_paper_links", "metrics", "benchmarks", "performance", "evidence_items"):
            merged[key] = self._ordered_unique([*(current.get(key) or []), *(incoming.get(key) or [])])
        return merged

    def _v2_source_payload(self, work: dict[str, Any]) -> dict[str, Any]:
        return {
            "source_work_ids": [work.get("work_id", "")],
            "source_work_title": work.get("title", ""),
            "source_paper_title": work.get("title", ""),
            "source_paper_link": work.get("url_or_doi", ""),
            "source_paper_links": [work.get("url_or_doi", "")] if work.get("url_or_doi") else [],
            "venue_or_source": work.get("venue_or_source", ""),
            "year": work.get("year"),
        }

    def _v2_evidence_link(self, field_id: str, target_bucket: str, target_id: str, work_id: str, evidence: str = "") -> dict[str, Any]:
        return {
            "link_id": stable_id("EL", field_id, target_bucket, target_id, work_id),
            "field_id": field_id,
            "target_bucket": target_bucket,
            "target_id": target_id,
            "source_bucket": "source_works",
            "source_id": work_id,
            "evidence": compact_text(evidence, 500),
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }

    def _v2_filter_generic(self, items: list[str], *, kind: str) -> list[str]:
        output = []
        blocked = [
            "state of the art",
            "state-of-the-art",
            "experiments demonstrate",
            "experiments show",
            "our approach achieves",
            "extensive experiments",
            "benchmark results demonstrate",
        ]
        for item in items:
            text = compact_text(item, 520)
            lower = text.lower()
            if len(text) < 24:
                continue
            if any(term in lower for term in blocked) and not re.search(r"\b(on|under|when|by|because|using|reduces?|improves?|fails?|outperforms?)\b", lower):
                continue
            if kind in {"idea", "principle"} and not re.search(r"\b(propos|introduc|use|learn|adapt|constrain|separat|align|route|factor|regulariz|optimiz|infer|reason)\w*", lower):
                continue
            output.append(text)
        return self._ordered_unique(output)

    def _extract_principle_sentences(self, text: str) -> list[str]:
        signals = ["principle", "because", "under", "when", "requires", "shows that", "demonstrates that", "implies", "trade-off", "invariant"]
        return [sentence for sentence in sentence_split(text) if any(signal in sentence.lower() for signal in signals)][:8]

    def _v2_llm_extraction_limit(self, model_mode: str) -> int:
        if model_mode.startswith("openai_"):
            return 24
        if model_mode in {"qwen_122b", "deepseek_pro", "kimi", "glm"}:
            return 32
        return 24

    def _v2_llm_batch_size(self, model_mode: str) -> int:
        if model_mode.startswith("openai_"):
            return 2
        if model_mode in {"qwen_122b", "deepseek_pro", "kimi", "glm"}:
            return 3
        return 4

    def _v2_llm_parallelism(self, model_mode: str) -> int:
        if model_mode.startswith("openai_"):
            return 1
        if model_mode in {"qwen_122b", "deepseek_pro", "kimi", "glm"}:
            return 2
        return 2

    def _v2_llm_extract_batch(
        self,
        goal_text: str,
        works: list[dict[str, Any]],
        *,
        model_mode: str,
        progress_callback: Callable[..., None] | None = None,
        batch_result_callback: Callable[[dict[str, dict[str, Any]]], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> dict[str, dict[str, Any]]:
        self._last_v2_llm_extract_error = ""
        if cancel_check and cancel_check():
            raise CancelledRun("Cancelled by user.")
        if not works:
            return {}
        if not self.llm.available():
            self._last_v2_llm_extract_error = "LLM extraction was skipped because no API key is configured for the selected provider."
            return {}
        payload = [
            {
                "work_id": work.get("work_id"),
                "title": work.get("title"),
                "abstract": compact_text(work.get("abstract", ""), 900),
                "venue_or_source": work.get("venue_or_source"),
                "year": work.get("year"),
            }
            for work in works
            if work.get("abstract") or work.get("title")
        ]
        if not payload:
            return {}
        batch_size = self._v2_llm_batch_size(model_mode)
        batches = [payload[idx : idx + batch_size] for idx in range(0, len(payload), batch_size)]
        extracted: dict[str, dict[str, Any]] = {}
        failures: list[str] = []
        parallelism = min(self._v2_llm_parallelism(model_mode), len(batches))

        def call_batch(batch_index: int, batch: list[dict[str, Any]]) -> tuple[int, dict[str, Any], int]:
            attempts = 0
            while True:
                if cancel_check and cancel_check():
                    raise CancelledRun("Cancelled by user.")
                attempts += 1
                try:
                    result = self.llm.chat_json(
                "You extract nontrivial research structures. Return strict JSON only.",
                (
                    "For each work, extract typed research records. Do not quote the abstract; rewrite into compact, reusable research language. "
                    "Existed ideas are the work's essential innovation mechanisms. Principles are fundamental reusable mechanisms or constraints validated by the work. "
                    "Takeaway messages are useful nontrivial findings or empirical lessons with a condition and a finding; reject generic SOTA claims. "
                    "Benchmarks must be public datasets/benchmarks actually used for experiments, with official_url/download page when known, data_form, scale, and metrics. "
                    "Baselines must be competing methods suitable for experiment tables, including the proposed method and compared methods, with source_paper_link/code link when known. "
                    "Return {\"works\":[{\"work_id\":\"...\","
                    "\"existed_ideas\":[{\"title\":\"...\",\"idea_text\":\"...\",\"mechanism\":\"...\",\"evidence\":\"...\"}],"
                    "\"principles\":[{\"name\":\"...\",\"abstract_signature\":\"...\",\"mechanism\":\"...\",\"boundary_conditions\":[\"...\"],\"evidence\":\"...\"}],"
                    "\"takeaway_messages\":[{\"title\":\"...\",\"message_text\":\"...\",\"condition\":\"...\",\"finding\":\"...\",\"actionable_lesson\":\"...\",\"evidence\":\"...\"}],"
                    "\"benchmarks\":[{\"benchmark_name\":\"...\",\"task\":\"...\",\"official_url\":\"...\",\"data_form\":\"...\",\"scale\":\"...\",\"metrics\":[\"...\"],\"evidence\":\"...\"}],"
                    "\"baselines\":[{\"baseline_name\":\"...\",\"baseline_type\":\"proposed_method|compared_method|published\",\"description\":\"...\",\"principle\":\"...\",\"source_paper_link\":\"...\",\"official_code_url\":\"...\",\"benchmarks\":[\"...\"],\"performance\":[{\"benchmark_name\":\"...\",\"metric\":\"...\",\"value_text\":\"...\"}],\"evidence\":\"...\"}]}]}.\n\n"
                    f"Research goal: {goal_text}\nWorks: {json.dumps(batch, ensure_ascii=False)}"
                ),
                complexity=0.72,
                mode=model_mode,
                max_tokens=2600 + 850 * len(batch),
                temperature=0.05,
            )
                    return batch_index, result, attempts
                except Exception as exc:
                    if isinstance(exc, CancelledRun):
                        raise
                    if attempts >= 2 or not self._v2_retryable_llm_error(exc):
                        raise
                    time.sleep(1.5 * attempts)
                    if cancel_check and cancel_check():
                        raise CancelledRun("Cancelled by user.")

        if progress_callback:
            progress_callback(
                "llm_extraction",
                f"Calling {len(batches)} LLM extractor batches with {parallelism} worker(s).",
                llm_batches_done=0,
                llm_batches_total=len(batches),
                llm_extracted_works=0,
            )
        completed = 0
        executor = ThreadPoolExecutor(max_workers=max(1, parallelism))
        futures = {
            executor.submit(call_batch, batch_index, batch): (batch_index, batch)
            for batch_index, batch in enumerate(batches, start=1)
        }
        try:
            for future in as_completed(futures):
                if cancel_check and cancel_check():
                    for pending in futures:
                        pending.cancel()
                    raise CancelledRun("Cancelled by user.")
                batch_index, _batch = futures[future]
                completed += 1
                try:
                    _, result, attempts = future.result()
                    if cancel_check and cancel_check():
                        raise CancelledRun("Cancelled by user.")
                    batch_extracted: dict[str, dict[str, Any]] = {}
                    for item in result.get("works", []):
                        if item.get("work_id"):
                            batch_extracted[str(item.get("work_id"))] = item
                    extracted.update(batch_extracted)
                    if batch_result_callback and batch_extracted:
                        batch_result_callback(batch_extracted)
                    if progress_callback:
                        retry_note = f" after {attempts} attempts" if attempts > 1 else ""
                        progress_callback(
                            "llm_extraction",
                            f"LLM extractor batch {batch_index}/{len(batches)} complete{retry_note}.",
                            llm_batches_done=completed,
                            llm_batches_total=len(batches),
                            llm_extracted_works=len(extracted),
                        )
                except Exception as exc:
                    if isinstance(exc, CancelledRun):
                        for pending in futures:
                            pending.cancel()
                        raise
                    failures.append(f"batch {batch_index}/{len(batches)}: {self._friendly_llm_error(exc)}")
                    if progress_callback:
                        progress_callback(
                            "llm_extraction",
                            f"LLM extractor batch {batch_index}/{len(batches)} failed; continuing with remaining batches.",
                            llm_batches_done=completed,
                            llm_batches_total=len(batches),
                            llm_extracted_works=len(extracted),
                            llm_failed_batches=len(failures),
                        )
        finally:
            executor.shutdown(wait=not (cancel_check and cancel_check()), cancel_futures=bool(cancel_check and cancel_check()))
        if failures:
            if extracted:
                self._last_v2_llm_extract_error = (
                    f"LLM extraction partially failed; {len(extracted)} works were extracted and "
                    f"{len(failures)} batches failed. First failure: {failures[0]}"
                )
            else:
                self._last_v2_llm_extract_error = (
                    f"LLM extraction failed for every batch, so only deterministic metadata was stored. "
                    f"First failure: {failures[0]}"
                )
        return extracted

    def _v2_retryable_llm_error(self, exc: Exception) -> bool:
        text = str(exc).lower()
        if any(term in text for term in ["insufficient_quota", "invalid_api_key", "no api key", "cost guard", "model_not_found"]):
            return False
        return any(term in text for term in ["timed out", "timeout", "temporarily", "connection reset", "remote end closed", "http 502", "http 503", "http 504", "rate limit"])

    def _friendly_llm_error(self, exc: Exception) -> str:
        text = str(exc)
        lower = text.lower()
        if "timed out" in lower or "read operation timed out" in lower:
            return (
                "Reason: the LLM API request reached the network but the provider did not finish before the timeout. "
                "Search had already completed; this is an LLM extraction latency issue."
            )
        if "insufficient_quota" in lower or "exceeded your current quota" in lower:
            return (
                "Reason: the LLM provider rejected the request for insufficient quota or billing. "
                "Search may still work, but LLM extraction/generation cannot run on this model until quota is restored."
            )
        if "no api key" in lower:
            return "Reason: no API key is configured for the selected provider."
        if "empty json text" in lower or "no text output" in lower:
            return (
                "Reason: the model request completed but did not include final JSON text. Principia now requests JSON-formatted output and minimal reasoning for OpenAI GPT-5-family calls; retry with a larger output budget if this repeats."
            )
        if "http 429" in lower:
            return "Reason: the LLM provider rate-limited or quota-limited the request."
        return f"Reason: {text}"

    def _v2_refresh_payload_with_llm(self, bucket: str, current: dict[str, Any], *, model_mode: str) -> dict[str, Any]:
        if self.llm.available():
            try:
                data = self.llm.chat_json(
                    "You refresh one Principia research record. Return strict JSON only.",
                    (
                        "Rewrite and complete the record without inventing unverifiable links. Preserve specific paper/official links already present. "
                        "Return a JSON object with the same conceptual fields plus confidence_score and needs_review.\n\n"
                        f"Bucket: {bucket}\nRecord: {json.dumps(current, ensure_ascii=False)}"
                    ),
                    complexity=0.65,
                    mode=model_mode,
                    max_tokens=2200,
                    temperature=0.08,
                )
                return {**current, **data, "refreshed_at": utc_now()}
            except Exception:
                pass
        return {**current, "refreshed_at": utc_now(), "needs_review": current.get("needs_review", False)}

    def _v2_last_research_run(self, data: dict[str, Any], field_id: str) -> dict[str, Any] | None:
        runs = [run for run in data.get("research_runs", {}).values() if run.get("field_id") == field_id]
        if not runs:
            return None
        return sorted(runs, key=lambda run: run.get("updated_at") or run.get("started_at") or "", reverse=True)[0]

    def _v2_related_existed_ideas(
        self,
        idea: dict[str, Any],
        existed: list[dict[str, Any]],
        *,
        model_mode: str = "auto",
        allow_heuristic: bool = False,
        use_llm: bool = True,
    ) -> list[dict[str, Any]]:
        # `allow_heuristic` is retained for older call sites only. Related-idea
        # comparison prose is quality-sensitive and must come from a callable
        # LLM; deterministic fallback text makes the product look falsely
        # confident and quickly becomes templated.
        _ = allow_heuristic
        body = " ".join([idea.get("title", ""), idea.get("one_sentence_thesis", ""), idea.get("novelty_claim", ""), " ".join(idea.get("mechanistic_design", []))])
        scored = []
        for item in existed:
            text = " ".join([item.get("title", ""), item.get("idea_text", ""), item.get("summary", "")])
            score = lexical_score(body, text)
            if score <= 0:
                continue
            scored.append((score, item, text))
        scored.sort(key=lambda row: row[0], reverse=True)
        seen_ids = {item.get("canonical_id", "") for _, item, _ in scored}
        if len(scored) < 24:
            for item in existed:
                item_id = item.get("canonical_id", "")
                if item_id in seen_ids:
                    continue
                text = " ".join([item.get("title", ""), item.get("idea_text", ""), item.get("summary", "")])
                scored.append((0.01, item, text))
                seen_ids.add(item_id)
                if len(scored) >= 24:
                    break
        candidates = scored[:24]
        if use_llm and candidates and self.llm.available():
            prompt_rows = [
                {
                    "id": item.get("canonical_id", ""),
                    "title": item.get("title") or compact_text(item.get("idea_text", ""), 120),
                    "idea_text": item.get("idea_text", ""),
                    "mechanism": item.get("mechanism", ""),
                    "summary": item.get("summary", ""),
                    "source_paper_title": item.get("source_paper_title", ""),
                    "venue_or_source": item.get("venue_or_source", ""),
                    "year": item.get("year"),
                }
                for _, item, _ in candidates
            ]
            prior_attempt_note = ""
            for attempt in range(2):
                try:
                    result = self.llm.chat_json(
                        "You compare a generated research idea against prior ideas. Return strict JSON only.",
                        (
                            "Write one row per prior idea. Every row must be independently reasoned from that prior idea's actual mechanism. "
                            "Do not use fixed sentence frames, repeated openings, or boilerplate transitions. "
                            "Forbidden openings include: 'Compared with', 'The mechanistic pivot', 'It may', 'The new idea', and 'The prior'. "
                            "Mechanistic Similarity must name the shared causal handle or experimental pressure. "
                            "Essential Difference must name the changed assumption, mechanism, objective, representation, or validation setting. "
                            "Potential Advantage must be a concrete advantage over that exact prior idea, not a reusable generic benefit. "
                            "Potential Weakness must be a concrete failure mode against that exact prior idea, not a reusable generic caveat. "
                            "Prefer specific nouns from the generated idea and the prior idea over abstract placeholders. "
                            "Return {\"rows\":[{\"id\":\"...\",\"mechanistic_similarity\":\"...\",\"essential_difference\":\"...\","
                            "\"potential_advantage\":\"...\",\"potential_weakness\":\"...\"}]}.\n"
                            f"{prior_attempt_note}\n\nGenerated idea: {json.dumps(idea, ensure_ascii=False)}\n"
                            f"Prior ideas: {json.dumps(prompt_rows, ensure_ascii=False)}"
                        ),
                        complexity=0.72,
                        mode=model_mode,
                        max_tokens=4800,
                        temperature=0.14 + attempt * 0.12,
                    )
                    by_id = {str(row.get("id")): row for row in result.get("rows", []) if row.get("id")}
                    if not by_id:
                        continue
                    output = []
                    for score, item, _ in candidates:
                        row = self._v2_related_row(idea, item, score, llm_row=by_id.get(str(item.get("canonical_id", ""))) or {})
                        if row:
                            output.append(row)
                    if output and not self._v2_rows_are_repetitive(output):
                        return output
                    prior_attempt_note = (
                        "The previous answer was rejected because it used repeated phrasing or insufficiently specific row-level reasoning. "
                        "Rewrite from scratch with visibly different sentence structure per row."
                    )
                except Exception:
                    break
        return []

    def _v2_related_row(self, idea: dict[str, Any], item: dict[str, Any], score: float, llm_row: dict[str, Any] | None = None) -> dict[str, Any] | None:
        llm_row = llm_row or {}
        similarity = str(llm_row.get("mechanistic_similarity") or llm_row.get("similarity_points") or llm_row.get("similarity") or "").strip()
        differences = str(llm_row.get("essential_difference") or llm_row.get("differences") or "").strip()
        advantage = str(llm_row.get("potential_advantage") or "").strip()
        weakness = str(llm_row.get("potential_weakness") or "").strip()
        candidate = {
            "similarity_points": similarity,
            "differences": differences,
            "potential_advantage": advantage,
            "potential_weakness": weakness,
        }
        if any(not self._v2_related_text_is_substantive(value) for value in candidate.values()):
            return None
        if self._v2_related_row_is_template(candidate):
            return None
        title = self._v2_display_label(item, fallback=item.get("canonical_id", ""))
        return (
                {
                    "id": item.get("canonical_id", ""),
                    "title": title,
                    "similarity": round(min(1.0, score), 2),
                    "similarity_points": compact_text(similarity, 900),
                    "differences": compact_text(differences, 900),
                    "potential_advantage": compact_text(advantage, 900),
                    "potential_weakness": compact_text(weakness, 900),
                    "source_paper_title": item.get("source_paper_title", ""),
                    "venue_or_source": item.get("venue_or_source", ""),
                    "year": item.get("year"),
                    "source_paper_link": item.get("source_paper_link", ""),
                }
            )

    def _v2_rows_are_repetitive(self, rows: list[dict[str, Any]]) -> bool:
        if len(rows) < 3:
            return any(self._v2_related_row_is_template(row) for row in rows)
        for key in ("differences", "potential_advantage", "potential_weakness"):
            values = [str(row.get(key, "")).strip().lower() for row in rows if row.get(key)]
            if values and len(set(values)) <= max(1, len(values) // 3):
                return True
            prefixes = [" ".join(re.findall(r"[a-z0-9-]+", value)[:4]) for value in values if value]
            if prefixes:
                most_common = max(prefixes.count(prefix) for prefix in set(prefixes))
                if most_common >= max(3, int(len(prefixes) * 0.45)):
                    return True
        return any(self._v2_related_row_is_template(row) for row in rows)

    def _v2_related_text_is_substantive(self, value: Any) -> bool:
        text = re.sub(r"\s+", " ", str(value or "").strip())
        if len(text) < 45:
            return False
        tokens = re.findall(r"[A-Za-z][A-Za-z0-9-]+", text.lower())
        if len(set(tokens)) < 10:
            return False
        return True

    def _v2_related_row_is_template(self, row: dict[str, Any]) -> bool:
        blocked_fragments = [
            "user-note driven and should be validated",
            "the mechanistic pivot is different",
            "the new proposal adds",
            "as explicit design variables",
            "it may allocate adaptation effort",
            "it can make evaluation part of the mechanism",
            "it may create an extra control lever",
            "its advantage must come from",
            "it may underperform if the omitted prior factor",
            "the added variable",
            "the risk is duplication",
            "closest available principle in the current project evidence pool",
        ]
        blocked_openings = [
            "compared with",
            "the mechanistic pivot",
            "the new idea",
            "the prior",
            "it may",
            "this idea",
            "the generated idea",
        ]
        for key in ("similarity_points", "differences", "potential_advantage", "potential_weakness"):
            text = re.sub(r"\s+", " ", str(row.get(key, "") or "").strip().lower())
            if not text:
                return True
            if any(fragment in text for fragment in blocked_fragments):
                return True
            if key in {"differences", "potential_advantage", "potential_weakness"} and any(text.startswith(opening) for opening in blocked_openings):
                return True
        return False

    def _v2_mechanism_terms(self, text: str) -> list[str]:
        candidates = []
        lower = text.lower()
        catalog = [
            "uncertainty", "confidence", "entropy", "routing", "prompt", "retrieval", "adapter", "cache",
            "regularization", "calibration", "base-to-novel", "test-time", "few-shot", "compute", "latency",
            "benchmark", "baseline", "ablation", "cross-sensor", "fusion", "sparse-view", "geometry",
            "communication", "token", "memory", "verification", "self-consistency",
        ]
        for term in catalog:
            if term in lower:
                candidates.append(term)
        phrase_matches = re.findall(r"\b[a-zA-Z][a-zA-Z0-9-]*(?:\s+[a-zA-Z][a-zA-Z0-9-]*){1,3}\b", text)
        for phrase in phrase_matches[:20]:
            cleaned = phrase.lower().strip()
            if not any(stop in cleaned.split() for stop in ["the", "and", "with", "from", "that", "this", "into"]):
                candidates.append(cleaned)
        candidates.extend(keyword_terms(text, 12))
        return self._ordered_unique([term.lower() for term in candidates if len(term) > 2])[:12]

    def _v2_principle_map(self, idea: dict[str, Any], principles: list[dict[str, Any]], related: list[dict[str, Any]]) -> dict[str, Any]:
        derived = self._listify(idea.get("derived_principles"))
        if not derived:
            derived = self._listify(idea.get("mechanistic_design"))[:3] or [idea.get("novelty_claim", "")]
        pressure = self._v2_pressure_phrase(idea.get("one_sentence_thesis", ""), " ".join(self._listify(idea.get("mechanistic_design"))))
        new_nodes = []
        for index, item in enumerate(derived[:6]):
            text = compact_text(str(item or ""), 360)
            if not text:
                continue
            label = compact_text(text, 92).rstrip(".")
            new_nodes.append(
                {
                    "id": stable_id("NP", idea.get("idea_id", ""), text),
                    "type": "new_principle",
                    "label": label,
                    "full_label": text.rstrip("."),
                    "summary": self._v2_principle_rule(text, pressure),
                    "layer": "Generated Idea Principles",
                    "ref_bucket": "my_ideas",
                    "ref_id": idea.get("idea_id", ""),
                    "x": 660,
                    "y": 110 + index * 190,
                }
            )
        related_text = " ".join(
            f"{row.get('title', '')} {row.get('similarity_points', '')} {row.get('differences', '')}"
            for row in related
        )

        idea_text = " ".join([idea.get("title", ""), idea.get("novelty_claim", ""), " ".join(self._listify(idea.get("mechanistic_design"))), related_text])
        principle_scores = []
        for item in principles:
            text = " ".join([item.get("name", ""), item.get("abstract_signature", ""), item.get("mechanism", "")])
            principle_scores.append((lexical_score(idea_text, text), item))
        principle_scores.sort(key=lambda row: (row[0], int(row[1].get("year") or 0)), reverse=True)
        existing_nodes = []
        for index, (_, item) in enumerate(principle_scores[:12]):
            label = item.get("name", "") or item.get("abstract_signature", "") or "Existing principle"
            full_label = compact_text(str(label), 220).rstrip(".")
            existing_nodes.append(
                {
                    "id": item.get("principle_id", ""),
                    "type": "existing_principle",
                    "label": compact_text(label, 92).rstrip("."),
                    "full_label": full_label,
                    "summary": item.get("abstract_signature", "") or item.get("mechanism", ""),
                    "layer": "Similar-Idea Principles",
                    "ref_bucket": "principles",
                    "ref_id": item.get("principle_id", ""),
                    "source_paper_title": item.get("source_paper_title", ""),
                    "source_paper_link": item.get("source_paper_link", ""),
                    "x": 70,
                    "y": 80 + index * 190,
                }
            )
        edges = []
        for new_node in new_nodes:
            linked = 0
            for existing in existing_nodes:
                relation = self._v2_principle_relation(new_node, existing)
                if not relation:
                    continue
                edges.append({"source": existing["id"], "target": new_node["id"], **relation})
                linked += 1
                if linked >= 4:
                    break
        if not edges and new_nodes and existing_nodes:
            edges.append({"source": existing_nodes[0]["id"], "target": new_nodes[0]["id"], "relation": "nearest_neighbor", "rationale": "Closest available principle in the current project evidence pool."})
        return {
            "groups": [
                {"name": "Similar-Idea Principles", "type": "existing_principle"},
                {"name": "Generated Idea Principles", "type": "new_principle"},
            ],
            "nodes": [*existing_nodes, *new_nodes],
            "edges": edges,
            "related_idea_count": len(related),
        }

    def _v2_display_label(self, item: dict[str, Any], *, fallback: str = "") -> str:
        candidates = [
            item.get("title"),
            item.get("name"),
            item.get("benchmark_name"),
            item.get("baseline_name"),
            item.get("idea_text"),
            item.get("message_text"),
            item.get("abstract_signature"),
            item.get("source_paper_title"),
            fallback,
        ]
        for candidate in candidates:
            text = compact_text(str(candidate or "").strip(), 110).rstrip(".")
            if not text:
                continue
            if re.fullmatch(r"(?:MI|XI|P|TM|B|BL|W)-[A-Z0-9]+", text):
                continue
            return text
        return fallback or "Record"

    def _v2_principle_relation(self, new_node: dict[str, Any], existing_node: dict[str, Any]) -> dict[str, str] | None:
        new_text = f"{new_node.get('label', '')} {new_node.get('summary', '')}"
        existing_text = f"{existing_node.get('label', '')} {existing_node.get('summary', '')}"
        score = lexical_score(new_text, existing_text)
        if score <= 0:
            return None
        combined = f"{new_text} {existing_text}".lower()
        if any(term in combined for term in ["not ", "fail", "negative", "contradict"]):
            return {"relation": "tension", "rationale": "The generated principle should be tested against a prior boundary or negative finding."}
        if score > 0.42:
            return {"relation": "equivalent_or_refinement", "rationale": "The generated principle appears to refine a closely overlapping existing mechanism."}
        if any(term in combined for term in ["cost", "token", "latency", "budget", "efficiency"]):
            return {"relation": "complementary_budget", "rationale": "The existing principle can constrain the generated idea's accuracy-cost tradeoff."}
        return {"relation": "complementary_mechanism", "rationale": "The existing principle shares a mechanism handle but leaves room for the generated idea's new control variable."}

    def _v2_my_idea_sources(self, idea: dict[str, Any], data: dict[str, Any], *, model_mode: str) -> list[dict[str, Any]]:
        output = []
        for ref in idea.get("selected_refs", []):
            bucket = self._v2_bucket(ref.get("bucket", ""))
            item = data.get(bucket, {}).get(ref.get("id", ""))
            if item:
                output.append({"bucket": bucket, "id": ref.get("id", ""), "item": self._v2_present_item(item, model_mode=model_mode)})
        return output

    def _v2_reference_labels(self, data: dict[str, Any], *, model_mode: str) -> dict[str, dict[str, str]]:
        labels: dict[str, dict[str, str]] = {}
        buckets = [
            "existed_ideas",
            "principles",
            "takeaway_messages",
            "benchmark_records",
            "baseline_records",
            "source_works",
            "my_ideas",
        ]
        for bucket in buckets:
            id_key = self._record_id_key(bucket)
            for raw in data.get(bucket, {}).values():
                item = self._v2_present_item(raw, model_mode=model_mode)
                record_id = str(item.get(id_key) or item.get("canonical_id") or "")
                if not record_id:
                    continue
                label = self._v2_display_label(item, fallback=record_id)
                labels[record_id] = {
                    "bucket": bucket,
                    "id": record_id,
                    "label": compact_text(str(label), 90).rstrip("."),
                }
        return labels

    def _listify(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [compact_text(str(item), 420) for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [compact_text(value, 420)]
        return []

    def assemble_idea(
        self,
        *,
        field_id: str,
        goal_text: str,
        project_name: str = "",
        project_description: str = "",
        selected_refs: list[dict[str, str]] | None = None,
        user_note: str = "",
        language: str = "en",
        model_mode: str = "auto",
    ) -> dict[str, Any]:
        data = self.store.snapshot(limit_per_bucket=None)
        profile = data.get("field_profiles", {}).get(field_id) or self._ensure_field_profile(field_id, goal_text)
        user_note = compact_text(user_note, 1200)
        goal_text = goal_text or profile.get("goal_text") or profile.get("query") or profile.get("name", "")
        goal_for_synthesis = "\n".join([part for part in [goal_text, f"User idea note: {user_note}" if user_note else ""] if part])
        goal = self.formalize_goal(goal_for_synthesis or goal_text, {}, offline=True, model_mode=model_mode)
        goal["raw_query"] = goal_for_synthesis or goal_text
        goal["target_domain"] = compact_text(" ".join([project_name or profile.get("name", ""), project_description or profile.get("description", ""), goal.get("target_domain", "")]), 180)
        bucket_aliases = {
            "works": "source_works",
            "principles": "principles",
            "insights": "work_facts",
            "novelty": "work_facts",
            "benchmarks": "benchmark_records",
            "baselines": "baseline_records",
            "ideas": "ideas",
        }
        selected: dict[str, list[dict[str, Any]]] = {
            "source_works": [],
            "principles": [],
            "work_facts": [],
            "benchmark_records": [],
            "baseline_records": [],
            "ideas": [],
        }
        for ref in selected_refs or []:
            bucket = bucket_aliases.get(str(ref.get("bucket") or ""), str(ref.get("bucket") or ""))
            record_id = str(ref.get("id") or ref.get("record_id") or "")
            item = data.get(bucket, {}).get(record_id)
            if item and bucket in selected:
                selected[bucket].append(item)
        project_principles = self._project_records(data, field_id, "principles")[:8]
        principles = self._dedupe_principles([*selected["principles"], *project_principles])[:8]
        if not principles:
            synthetic = self._normalize_principle(
                {
                    "name": f"{project_name or profile.get('name', 'Project')} assembly principle",
                    "mechanism": "Combine selected project evidence into one falsifiable research mechanism.",
                    "problem_pressure": goal_for_synthesis or goal_text,
                    "objective": "Generate a new idea grounded in selected local evidence.",
                    "domain_tags": keyword_terms(goal_for_synthesis or goal_text, 4),
                },
                [item.get("work_id", "") for item in selected["source_works"] if item.get("work_id")],
            )
            principles = [synthetic]
            self.store.merge_principles([synthetic])
        insight_facts = [item for item in selected["work_facts"] if item.get("fact_type") == "insight"]
        novelty_facts = [item for item in selected["work_facts"] if item.get("fact_type") == "novelty"]
        if user_note:
            insight_facts.insert(
                0,
                {
                    "fact_id": stable_id("UN", field_id, user_note),
                    "type": "user_note",
                    "fact_type": "user_note",
                    "work_id": "",
                    "work_title": "User idea note",
                    "text": user_note,
                    "confidence_score": 1.0,
                },
            )
        curation = {
            "insights": insight_facts,
            "novelty": novelty_facts,
            "brief": {
                "curator": "assembler",
                "synthesis_brief": "Assemble one idea from user-selected project evidence and the user's own idea note.",
                "core_tension": compact_text(goal_for_synthesis or goal_text, 320),
                "user_need": project_description or profile.get("description", ""),
                "user_idea_note": user_note,
                "rejection_notes": [],
            },
        }
        ideas, estimates, plans = self._synthesize_ideas(
            goal,
            principles,
            max_ideas=1,
            offline=not self.llm.available(),
            model_mode=model_mode,
            curation=curation,
        )
        idea = ideas[0]
        idea["assembly_trace"] = {
            "selected_refs": selected_refs or [],
            "project_name": project_name or profile.get("name", ""),
            "project_description": project_description or profile.get("description", ""),
            "user_note": user_note,
        }
        idea["source_works"] = self._ordered_unique(
            [
                *[item.get("work_id") for item in selected["source_works"] if item.get("work_id")],
                *[item.get("work_id") for item in selected["work_facts"] if item.get("work_id")],
            ]
        )
        idea["source_facts"] = self._ordered_unique([item.get("fact_id") for item in selected["work_facts"] if item.get("fact_id")])
        if user_note:
            idea["source_facts"] = self._ordered_unique([stable_id("UN", field_id, user_note), *idea["source_facts"]])
            idea["user_note"] = user_note
        idea["source_benchmarks"] = self._ordered_unique([item.get("benchmark_id") for item in selected["benchmark_records"] if item.get("benchmark_id")])
        idea["source_baselines"] = self._ordered_unique([item.get("baseline_id") for item in selected["baseline_records"] if item.get("baseline_id")])
        self.store.upsert("goals", goal, "goal_id")
        self.store.upsert("ideas", idea, "idea_id")
        self.store.upsert("estimates", estimates[0], "estimate_id")
        self.store.upsert("prompt_plans", plans[0], "prompt_plan_id")
        self.add_project_memberships(field_id, "ideas", [idea["idea_id"]], source="assembler", prepend=True)
        self.add_project_memberships(field_id, "principles", [item["principle_id"] for item in principles if item.get("principle_id")], source="assembler")
        if language == "zh":
            idea = self.repair_language_variants(idea)
        run_id = stable_id("R", field_id, "assemble_idea", idea["idea_id"], utc_now())
        self.store.upsert(
            "runs",
            {
                "run_id": run_id,
                "type": "assemble_idea",
                "field_id": field_id,
                "idea_id": idea["idea_id"],
                "selected_refs": selected_refs or [],
                "created_at": utc_now(),
            },
            "run_id",
        )
        return {"ok": True, "idea": idea, "estimate": estimates[0], "prompt_plan": plans[0], "run_id": run_id}

    def build_library_dashboard(self, field_id: str = "default", query: str = "") -> dict[str, Any]:
        data = self.store.snapshot(limit_per_bucket=None)
        works = self._project_records(data, field_id, "source_works", query=query)
        principles = self._project_records(data, field_id, "principles", query=query)
        ideas = self._project_records(data, field_id, "ideas", query=query)
        facts = self._project_records(data, field_id, "work_facts", query=query)
        benchmarks = self._project_records(data, field_id, "benchmark_records", query=query)
        baselines = self._project_records(data, field_id, "baseline_records", query=query)
        results = self._project_records(data, field_id, "result_records", query=query)
        gaps = self._project_records(data, field_id, "gap_cards", query=query)
        runs = self._query_items(data.get("runs", {}).values(), query)
        estimates = data.get("estimates", {})
        prompt_plans = data.get("prompt_plans", {})
        counts = {
            "works": len(works),
            "principles": len(principles),
            "work_facts": len(facts),
            "benchmarks": len(benchmarks),
            "baselines": len(baselines),
            "results": len(results),
            "ideas": len(ideas),
            "validated_ideas": sum(1 for idea in ideas if idea.get("validated") or idea.get("feedback_status") == "validated"),
            "estimates": len(estimates),
            "prompt_plans": len(prompt_plans),
            "runs": len(runs),
            "gaps": len(gaps),
        }
        coverage = self._coverage_payload(works, facts, benchmarks, baselines, results, principles)
        top_principles = self._top_principles_payload(principles, ideas, data.get("source_works", {}))[:8]
        recent_works = self._recent_items(works, "work_id")[:8]
        recent_ideas = self._recent_items(ideas, "idea_id")[:8]
        warnings = [
            {
                "title": gap.get("title", "Field gap"),
                "summary": gap.get("summary", ""),
                "severity": gap.get("severity", 0.5),
                "gap_type": gap.get("gap_type", "gap"),
                "gap_id": gap.get("gap_id", ""),
            }
            for gap in sorted(gaps, key=lambda item: float(item.get("severity", 0.0)), reverse=True)[:6]
        ]
        brief = self._frontier_brief(counts, coverage, top_principles, warnings)
        families = self._principle_families(principles, ideas)
        timeline = self._frontier_timeline(works, principles, gaps)
        return {
            "field": self.store.get_item("field_profiles", field_id) or to_dict(FieldProfile(field_id=field_id, name="Default Local Field")),
            "counts": counts,
            "coverage": coverage,
            "top_principles": top_principles,
            "recent_works": recent_works,
            "recent_ideas": recent_ideas,
            "warnings": warnings,
            "frontier_brief": brief,
            "principle_families": families,
            "timeline": timeline,
            "last_sync": data.get("meta", {}).get("updated_at"),
        }

    def build_fact_view(self, fact_type: str, field_id: str = "default", query: str = "") -> dict[str, Any]:
        data = self.store.snapshot(limit_per_bucket=None)
        project_work_ids = self._project_id_set(data, field_id, "work_ids")
        facts = [
            fact
            for fact in self._project_records(data, field_id, "work_facts", query=query)
            if fact.get("fact_type") == fact_type
            and (not project_work_ids or fact.get("work_id") in project_work_ids)
        ]
        works = data.get("source_works", {})
        rows = []
        for fact in facts:
            work = works.get(fact.get("work_id", ""), {})
            rows.append(
                {
                    **fact,
                    "work_title": work.get("title", fact.get("work_id", "")),
                    "work_year": work.get("year"),
                    "source": work.get("venue_or_source", "local"),
                    "url_or_doi": work.get("url_or_doi", ""),
                }
            )
        rows.sort(key=lambda item: (float(item.get("confidence_score", 0)), item.get("updated_at") or item.get("created_at") or ""), reverse=True)
        return {"items": rows}

    def build_benchmark_view(self, field_id: str = "default", query: str = "") -> dict[str, Any]:
        data = self.store.snapshot(limit_per_bucket=None)
        project_work_ids = self._project_id_set(data, field_id, "work_ids")
        records = [
            item
            for item in self._project_records(data, field_id, "benchmark_records", query=query)
            if not project_work_ids or item.get("work_id") in project_work_ids
        ]
        benchmark_ids = {item.get("benchmark_id") for item in records if item.get("benchmark_id")}
        record_work_ids = {item.get("work_id") for item in records if item.get("work_id")}
        baselines = [
            item
            for item in self._project_records(data, field_id, "baseline_records")
            if (
                (not benchmark_ids or item.get("benchmark_id") in benchmark_ids)
                and (not record_work_ids or item.get("work_id") in record_work_ids)
            )
        ]
        results = [
            item
            for item in self._project_records(data, field_id, "result_records")
            if (
                (not benchmark_ids or item.get("benchmark_id") in benchmark_ids)
                and (not record_work_ids or item.get("work_id") in record_work_ids)
            )
        ]
        works = data.get("source_works", {})
        groups: dict[str, dict[str, Any]] = {}
        for record in records:
            key = self._benchmark_group_key(record)
            group = groups.setdefault(
                key,
                {
                    "benchmark_id": key,
                    "task": record.get("task", ""),
                    "dataset": record.get("dataset", ""),
                    "split": record.get("split", ""),
                    "metric": record.get("metric", ""),
                    "metric_direction": record.get("metric_direction", "unknown"),
                    "record_ids": [],
                    "source_work_ids": [],
                    "sources": [],
                    "tasks": [],
                    "splits": [],
                    "metrics": [],
                    "baselines": [],
                    "results": [],
                    **self._benchmark_catalog_info(record.get("dataset", "")),
                },
            )
            group["record_ids"].append(record.get("benchmark_id", ""))
            for key, value in (("tasks", record.get("task", "")), ("splits", record.get("split", "")), ("metrics", record.get("metric", ""))):
                if value and value not in group[key]:
                    group[key].append(value)
            if record.get("work_id") not in group["source_work_ids"]:
                group["source_work_ids"].append(record.get("work_id", ""))
            work = works.get(record.get("work_id", ""), {})
            if work and work.get("title") not in group["sources"]:
                group["sources"].append(work.get("title"))
        record_to_group = {record_id: group_id for group_id, group in groups.items() for record_id in group["record_ids"]}
        for baseline in baselines:
            group_id = record_to_group.get(baseline.get("benchmark_id", ""))
            if group_id:
                groups[group_id]["baselines"].append(baseline)
        for result in results:
            group_id = record_to_group.get(result.get("benchmark_id", ""))
            if group_id:
                groups[group_id]["results"].append(result)
        rows = list(groups.values())
        for row in rows:
            row["task"] = ", ".join(row["tasks"][:4]) or row.get("task", "")
            row["split"] = ", ".join(row["splits"][:4]) or row.get("split", "")
            row["metric"] = ", ".join(row["metrics"][:6]) or row.get("metric", "")
            row["baseline_performance"] = self._baseline_performance_summary(row["baselines"], row["results"])
            row["baseline_count"] = len({baseline.get("baseline_name") for baseline in row["baselines"]})
            row["source_count"] = len(row["source_work_ids"])
        rows.sort(key=lambda item: (item["source_count"], item["baseline_count"], item.get("dataset", "")), reverse=True)
        return {
            "items": rows,
            "benchmark_records": records,
            "baseline_records": baselines,
            "result_records": results,
            "works": works,
        }

    def build_baseline_view(self, field_id: str = "default", query: str = "") -> dict[str, Any]:
        data = self.store.snapshot(limit_per_bucket=None)
        project_work_ids = self._project_id_set(data, field_id, "work_ids")
        baselines = [
            item
            for item in self._project_records(data, field_id, "baseline_records", query=query)
            if (not project_work_ids or item.get("work_id") in project_work_ids)
        ]
        benchmark_records = {
            item.get("benchmark_id"): item
            for item in self._project_records(data, field_id, "benchmark_records")
            if not project_work_ids or item.get("work_id") in project_work_ids
        }
        results = [
            item
            for item in self._project_records(data, field_id, "result_records")
            if not project_work_ids or item.get("work_id") in project_work_ids
        ]
        results_by_baseline: dict[str, list[dict[str, Any]]] = {}
        results_by_benchmark: dict[str, list[dict[str, Any]]] = {}
        for result in results:
            if result.get("baseline_id"):
                results_by_baseline.setdefault(result.get("baseline_id", ""), []).append(result)
            if result.get("benchmark_id"):
                results_by_benchmark.setdefault(result.get("benchmark_id", ""), []).append(result)
        works = data.get("source_works", {})
        groups: dict[str, dict[str, Any]] = {}
        group_result_ids: dict[str, set[str]] = {}
        for baseline in baselines:
            key = self._normalize_name(baseline.get("baseline_name", "")) or baseline.get("baseline_id", "")
            info = self._baseline_catalog_info(baseline.get("baseline_name", ""))
            group = groups.setdefault(
                key,
                {
                    "baseline_id": key,
                    "baseline_name": baseline.get("baseline_name", ""),
                    "baseline_type": baseline.get("baseline_type", "published"),
                    "source_work_ids": [],
                    "benchmarks": [],
                    "results": [],
                    "records": [],
                    **info,
                },
            )
            group["records"].append(baseline)
            if baseline.get("work_id") not in group["source_work_ids"]:
                group["source_work_ids"].append(baseline.get("work_id", ""))
            benchmark = benchmark_records.get(baseline.get("benchmark_id", ""))
            if benchmark:
                label = f"{benchmark.get('dataset', 'benchmark')} · {benchmark.get('metric', 'metric')}"
                if label not in group["benchmarks"]:
                    group["benchmarks"].append(label)
            linked_results = results_by_baseline.get(baseline.get("baseline_id", ""))
            if not linked_results:
                linked_results = results_by_benchmark.get(baseline.get("benchmark_id", ""), [])
            seen_results = group_result_ids.setdefault(key, set())
            for result in linked_results:
                result_id = result.get("result_id", "")
                if result_id and result_id not in seen_results and len(group["results"]) < 120:
                    seen_results.add(result_id)
                    group["results"].append(result)
        rows = list(groups.values())
        for row in rows:
            row["source_titles"] = [works.get(wid, {}).get("title", wid) for wid in row["source_work_ids"][:5]]
            row["performance"] = self._baseline_performance_summary(row["records"], row["results"])
            if not row.get("official_code_url"):
                row["official_code_url"] = next((result.get("code_url") for result in row["results"] if result.get("code_url")), "")
        rows.sort(key=lambda item: (len(item["benchmarks"]), len(item["source_work_ids"]), item.get("baseline_name", "")), reverse=True)
        return {
            "items": rows,
            "baseline_records": baselines,
            "result_records": results[:500],
            "benchmark_records": list(benchmark_records.values()),
            "works": works,
        }

    def extract_work_facts(
        self,
        goal: dict[str, Any],
        work: dict[str, Any],
        *,
        field_id: str = "default",
        persist: bool = True,
    ) -> list[dict[str, Any]]:
        work_id = work.get("work_id", "")
        if not work_id:
            return []
        data = self.store.snapshot(limit_per_bucket=None)
        existing = [
            fact
            for fact in data.get("work_facts", {}).values()
            if fact.get("work_id") == work_id and fact.get("field_id", "default") == field_id
        ]
        existing_keys = {(fact.get("fact_type"), self._normalize_name(fact.get("text", ""))) for fact in existing}
        text = " ".join(
            [
                work.get("title", ""),
                work.get("abstract", ""),
                " ".join(work.get("work_principles", [])),
                " ".join(work.get("work_insights", [])),
                " ".join(work.get("work_novelty", [])),
            ]
        )
        candidates: list[tuple[str, str, float, str]] = []
        principles = [self._strip_fact_prefix(item) for item in work.get("work_principles", []) if item]
        insights = self._ordered_unique(
            [
                *[self._strip_fact_prefix(item) for item in work.get("work_insights", []) if item],
                *self._extract_insight_messages(text),
            ]
        )
        novelty = self._ordered_unique(
            [
                *[self._strip_fact_prefix(item) for item in work.get("work_novelty", []) if item],
                *self._extract_novelty_points(text),
            ]
        )
        if principles:
            candidates.append(("core_idea", principles[0], 0.68, "legacy_work_principles"))
            for item in principles:
                candidates.append(("principle", item, 0.66, "legacy_work_principles"))
        elif work.get("title"):
            candidates.append(("core_idea", f"Investigate {work['title']}", 0.35, "title"))
        motivation = self._first_matching_sentence(
            work.get("abstract", ""),
            ["challenge", "problem", "limited", "scarce", "cost", "difficult", "underconstrained", "bottleneck", "motivation"],
        )
        if motivation:
            candidates.append(("motivation", motivation, 0.48, "abstract_sentence"))
        for item in insights:
            candidates.append(("insight", item, 0.64, "legacy_work_insights"))
        for item in novelty:
            candidates.append(("novelty", item, 0.62, "legacy_work_novelty"))
        for sentence in sentence_split(text):
            lower = sentence.lower()
            if any(term in lower for term in ["assume", "assumption", "requires", "under the condition"]):
                candidates.append(("assumption", sentence, 0.42, "abstract_sentence"))
            if any(term in lower for term in ["failure", "limitation", "breaks", "fails", "hallucinat", "overfit"]):
                candidates.append(("failure_mode", sentence, 0.42, "abstract_sentence"))
        records: list[dict[str, Any]] = []
        for fact_type, fact_text, confidence, source in candidates:
            clean = compact_text(str(fact_text), 420)
            if not clean:
                continue
            key = (fact_type, self._normalize_name(clean))
            if key in existing_keys:
                continue
            existing_keys.add(key)
            fact = WorkFact(
                fact_id=stable_id("WF", field_id, work_id, fact_type, clean),
                work_id=work_id,
                field_id=field_id,
                fact_type=fact_type,
                text=clean,
                normalized_name=self._normalize_name(clean),
                evidence_span={"source": source, "work_id": work_id},
                confidence_score=confidence,
                extraction_mode="heuristic",
            )
            records.append(to_dict(fact))
        if persist and records:
            self.store.upsert_many("work_facts", records, "fact_id")
        return [*existing, *records]

    def extract_benchmark_records(
        self,
        goal: dict[str, Any],
        work: dict[str, Any],
        *,
        field_id: str = "default",
        persist: bool = True,
        force: bool = False,
    ) -> dict[str, list[dict[str, Any]]]:
        work_id = work.get("work_id", "")
        if not work_id:
            return {"benchmark_records": [], "baseline_records": [], "result_records": []}
        data = self.store.snapshot(limit_per_bucket=None)
        current = {
            bucket: [
                item
                for item in data.get(bucket, {}).values()
                if item.get("work_id") == work_id and item.get("field_id", "default") == field_id
            ]
            for bucket in ("benchmark_records", "baseline_records", "result_records")
        }
        source_hash = self._work_source_hash(work)
        extraction_version = "benchmark-baseline-v1.3"
        refreshable_current = {
            bucket: [
                item
                for item in items
                if item.get("extractor") == "deterministic" or item.get("source_hash") or item.get("extraction_version")
            ]
            for bucket, items in current.items()
        }
        has_stale_extraction = any(
            item.get("extraction_version") != extraction_version
            for items in refreshable_current.values()
            for item in items
        )
        if force or has_stale_extraction:
            for bucket, items in refreshable_current.items():
                id_key = self._record_id_key(bucket)
                for item in items:
                    if item.get(id_key):
                        self.store.delete_item(bucket, item[id_key])
                removed = {item.get(id_key) for item in items}
                current[bucket] = [item for item in current[bucket] if item.get(id_key) not in removed]
        if (
            not force
            and current["benchmark_records"]
            and all(item.get("source_hash") == source_hash and item.get("extraction_version") == extraction_version for item in current["benchmark_records"])
        ):
            return current
        facts = [
            fact
            for fact in data.get("work_facts", {}).values()
            if fact.get("work_id") == work_id and fact.get("field_id", "default") == field_id
        ]
        text = " ".join(
            [
                work.get("title", ""),
                work.get("abstract", ""),
                " ".join(work.get("work_principles", [])),
                " ".join(work.get("work_insights", [])),
                " ".join(work.get("work_novelty", [])),
                " ".join(fact.get("text", "") for fact in facts),
            ]
        )
        if not self._contains_any(text, self._benchmark_signal_terms()):
            return current
        datasets = self._ordered_unique([*self._matched_terms(text, self._dataset_terms()), *self._extract_dataset_suite_terms(text)])
        metrics = self._matched_terms(text, self._metric_terms())
        baselines = self._ordered_unique([*self._matched_terms(text, self._baseline_terms()), *self._extract_compared_methods(text)])
        proposed_method = self._proposed_method_name(work)
        if not metrics and self._contains_any(text, ["benchmark", "evaluation", "result", "score"]):
            metrics = ["primary reported metric"]
        baselines = self._ordered_unique([proposed_method, *[name for name in baselines if self._is_plausible_method_name(name)]])
        benchmarks: list[dict[str, Any]] = []
        existing_bench_ids = {item.get("benchmark_id") for item in current["benchmark_records"]}
        for dataset in datasets:
            for metric in (metrics or ["primary reported metric"]):
                benchmark_id = stable_id("B", field_id, work_id, dataset, metric)
                if benchmark_id in existing_bench_ids:
                    continue
                confidence = 0.7 if dataset != "unspecified local benchmark" and metric != "primary reported metric" else 0.32
                record = BenchmarkRecord(
                    benchmark_id=benchmark_id,
                    field_id=field_id,
                    work_id=work_id,
                    task=self._infer_task_label(goal, work, text),
                    dataset=dataset,
                    split=self._infer_split(text),
                    metric=metric,
                    metric_direction=self._metric_direction(metric),
                    evidence_span={"source": "metadata_or_abstract", "text": compact_text(text, 260)},
                    confidence_score=confidence,
                )
                payload = to_dict(record)
                payload.update(
                    {
                        "source_hash": source_hash,
                        "extraction_version": extraction_version,
                        "extracted_at": utc_now(),
                        "extractor": "deterministic",
                        "needs_llm_review": confidence < 0.5,
                    }
                )
                benchmarks.append(payload)
        all_benchmarks = [*current["benchmark_records"], *benchmarks]
        baselines_out: list[dict[str, Any]] = []
        existing_baseline_ids = {item.get("baseline_id") for item in current["baseline_records"]}
        for benchmark in all_benchmarks:
            for name in baselines:
                baseline_id = stable_id("BL", field_id, work_id, benchmark["benchmark_id"], name)
                if baseline_id in existing_baseline_ids:
                    continue
                baseline_type = "proposed_method" if name == proposed_method else self._baseline_type(name)
                record = BaselineRecord(
                    baseline_id=baseline_id,
                    field_id=field_id,
                    work_id=work_id,
                    benchmark_id=benchmark["benchmark_id"],
                    baseline_name=name,
                    baseline_type=baseline_type,
                    evidence_span={"source": "metadata_or_abstract", "text": name},
                    confidence_score=0.7 if baseline_type == "proposed_method" else 0.58,
                )
                payload = to_dict(record)
                payload.update(
                    {
                        "source_hash": source_hash,
                        "extraction_version": extraction_version,
                        "extracted_at": utc_now(),
                        "extractor": "deterministic",
                        "needs_llm_review": False,
                    }
                )
                baselines_out.append(payload)
        results_out: list[dict[str, Any]] = []
        existing_result_ids = {item.get("result_id") for item in current["result_records"]}
        proposed_baselines = [item for item in [*current["baseline_records"], *baselines_out] if item.get("baseline_type") == "proposed_method"]
        code_url = self._extract_code_url(work, text)
        for benchmark in all_benchmarks:
            for value, value_text, unit in self._extract_numeric_results(text)[:8]:
                metric = self._metric_near_result(value_text, metrics)
                benchmark_id = benchmark["benchmark_id"]
                baseline_id = next((item["baseline_id"] for item in proposed_baselines if item.get("benchmark_id") == benchmark_id), "")
                result_id = stable_id("RR", field_id, work_id, benchmark_id, metric, value_text)
                if result_id in existing_result_ids:
                    continue
                record = ResultRecord(
                    result_id=result_id,
                    field_id=field_id,
                    work_id=work_id,
                    benchmark_id=benchmark_id,
                    method_name=proposed_method,
                    baseline_id=baseline_id,
                    metric=metric,
                    value=value,
                    value_text=value_text,
                    unit=unit,
                    code_url=code_url,
                    result_quality={
                        "has_code": bool(code_url),
                        "has_ablation": self._contains_any(text, ["ablation", "ablate"]),
                        "has_compute_accounting": self._contains_any(text, ["gpu hour", "flops", "latency", "memory", "compute"]),
                        "needs_verification": value is None,
                    },
                    evidence_span={"source": "metadata_or_abstract", "text": value_text},
                    confidence_score=0.46 if value is not None else 0.28,
                )
                payload = to_dict(record)
                payload.update(
                    {
                        "source_hash": source_hash,
                        "extraction_version": extraction_version,
                        "extracted_at": utc_now(),
                        "extractor": "deterministic",
                        "needs_llm_review": value is None,
                    }
                )
                results_out.append(payload)
        if persist:
            if benchmarks:
                self.store.upsert_many("benchmark_records", benchmarks, "benchmark_id")
            if baselines_out:
                self.store.upsert_many("baseline_records", baselines_out, "baseline_id")
            if results_out:
                self.store.upsert_many("result_records", results_out, "result_id")
        return {
            "benchmark_records": [*current["benchmark_records"], *benchmarks],
            "baseline_records": [*current["baseline_records"], *baselines_out],
            "result_records": [*current["result_records"], *results_out],
        }

    def build_library_graph(self, field_id: str = "default", mode: str = "principle_lineage", query: str = "") -> dict[str, Any]:
        data = self.store.snapshot(limit_per_bucket=None)
        base = self.build_graph(query=query, top_k=10)
        nodes = [{"id": field_id, "type": "field", "label": "Default Local Field"}, *base.get("nodes", [])]
        edges = list(base.get("edges", []))
        node_ids = {node["id"] for node in nodes}
        for work in self._query_items(data.get("source_works", {}).values(), query)[:12]:
            wid = work.get("work_id")
            if not wid:
                continue
            if wid not in node_ids:
                nodes.append({"id": wid, "type": "work", "label": work.get("title", wid)})
                node_ids.add(wid)
            edges.append({"source": field_id, "target": wid, "label": "contains"})
        if mode in {"benchmark_map", "principle_lineage", "work_evidence"}:
            for benchmark in self._field_items(data.get("benchmark_records", {}).values(), field_id)[:18]:
                bid = benchmark["benchmark_id"]
                nodes.append(
                    {
                        "id": bid,
                        "type": "benchmark",
                        "label": f"{benchmark.get('dataset')} · {benchmark.get('metric')}",
                    }
                )
                edges.append({"source": benchmark.get("work_id", field_id), "target": bid, "label": "evaluates_on"})
        if mode in {"gap_map", "principle_lineage"}:
            for gap in self._field_items(data.get("gap_cards", {}).values(), field_id)[:10]:
                gid = gap["gap_id"]
                nodes.append({"id": gid, "type": "gap", "label": gap.get("title", gid), "severity": gap.get("severity", 0.5)})
                edges.append({"source": field_id, "target": gid, "label": "exposes"})
                for pid in gap.get("related_principle_ids", [])[:3]:
                    edges.append({"source": pid, "target": gid, "label": "exposes"})
        unique_nodes = {node["id"]: node for node in nodes}
        unique_edges = []
        seen_edges: set[tuple[str, str, str]] = set()
        for edge in edges:
            key = (str(edge.get("source")), str(edge.get("target")), str(edge.get("label")))
            if key in seen_edges:
                continue
            seen_edges.add(key)
            unique_edges.append(edge)
        return {"field_id": field_id, "mode": mode, "nodes": list(unique_nodes.values()), "edges": unique_edges}

    def mine_gap_cards(
        self,
        field_id: str = "default",
        query: str = "",
        *,
        persist: bool = True,
        ensure: bool = True,
    ) -> list[dict[str, Any]]:
        if ensure:
            self.sync_library_observatory(field_id=field_id, query=query)
        data = self.store.snapshot(limit_per_bucket=None)
        works = self._query_items(data.get("source_works", {}).values(), query)
        principles = self._query_items(data.get("principles", {}).values(), query)
        ideas = self._query_items(data.get("ideas", {}).values(), query)
        facts = self._field_items(data.get("work_facts", {}).values(), field_id)
        benchmarks = self._field_items(data.get("benchmark_records", {}).values(), field_id)
        baselines = self._field_items(data.get("baseline_records", {}).values(), field_id)
        results = self._field_items(data.get("result_records", {}).values(), field_id)
        gaps: list[dict[str, Any]] = []
        if works and (len(baselines) < max(1, len(benchmarks))):
            gaps.append(
                self._gap(
                    field_id,
                    "missing_baseline",
                    "Missing nearest-baseline accounting",
                    f"{len(works)} local works are present, but only {len(baselines)} baseline records are structured.",
                    related_work_ids=[work.get("work_id", "") for work in works[:8]],
                    related_benchmark_ids=[benchmark.get("benchmark_id", "") for benchmark in benchmarks[:8]],
                    severity=0.72 if benchmarks else 0.56,
                    novelty_potential=0.7,
                    suggested=["Build a nearest-baseline comparison matrix", "Generate ideas that make the baseline argue against the mechanism"],
                )
            )
        if ideas and not benchmarks:
            gaps.append(
                self._gap(
                    field_id,
                    "missing_benchmark",
                    "Generated ideas need benchmark anchors",
                    f"{len(ideas)} ideas exist, but the field has no structured benchmark records yet.",
                    related_work_ids=[work.get("work_id", "") for work in works[:6]],
                    severity=0.68,
                    novelty_potential=0.62,
                    suggested=["Define the smallest benchmark slice for the top idea", "Extract datasets and metrics from highlighted works"],
                )
            )
        weak = [
            principle
            for principle in principles
            if len(principle.get("assumptions", [])) >= 2 and validation_number(principle.get("validation_level", "L0")) < 3
        ]
        if weak:
            gaps.append(
                self._gap(
                    field_id,
                    "weak_assumption",
                    "Assumption-heavy principles lack result evidence",
                    f"{len(weak)} principles have multiple assumptions but are below L3 validation.",
                    related_principle_ids=[principle.get("principle_id", "") for principle in weak[:10]],
                    severity=0.6,
                    novelty_potential=0.66,
                    suggested=["Create a falsification experiment for the strongest assumption", "Promote only evidence-backed assumptions into reusable principles"],
                )
            )
        tradeoff_counts: dict[str, list[str]] = {}
        for principle in principles:
            for tradeoff in principle.get("tradeoffs", []):
                key = self._normalize_name(tradeoff)
                if key:
                    tradeoff_counts.setdefault(key, []).append(principle.get("principle_id", ""))
        repeated = [(key, ids) for key, ids in tradeoff_counts.items() if len(ids) >= 2]
        if repeated:
            key, ids = sorted(repeated, key=lambda pair: len(pair[1]), reverse=True)[0]
            gaps.append(
                self._gap(
                    field_id,
                    "unresolved_tradeoff",
                    "Repeated tradeoff without a resolving benchmark",
                    f"The tradeoff '{key}' appears in {len(ids)} principles, but linked result evidence is still sparse.",
                    related_principle_ids=ids[:10],
                    related_benchmark_ids=[benchmark.get("benchmark_id", "") for benchmark in benchmarks[:6]],
                    severity=0.58,
                    novelty_potential=0.72,
                    suggested=[f"Design an idea that measures the {key} tradeoff directly"],
                )
            )
        contradictions = [principle for principle in principles if principle.get("contradiction_links")]
        if contradictions:
            gaps.append(
                self._gap(
                    field_id,
                    "contradiction",
                    "Contradiction links need adjudication",
                    f"{len(contradictions)} principles contain contradiction links.",
                    related_principle_ids=[principle.get("principle_id", "") for principle in contradictions[:10]],
                    severity=0.64,
                    novelty_potential=0.68,
                    suggested=["Create a stress test that decides between the conflicting mechanisms"],
                )
            )
        stale = [
            principle
            for principle in principles
            if validation_number(principle.get("validation_level", "L0")) == 0 and not principle.get("source_works")
        ]
        if stale:
            gaps.append(
                self._gap(
                    field_id,
                    "stale_principle",
                    "Speculative principles need source grounding",
                    f"{len(stale)} principles are L0 and have no linked source works.",
                    related_principle_ids=[principle.get("principle_id", "") for principle in stale[:10]],
                    severity=0.42,
                    novelty_potential=0.45,
                    suggested=["Link each speculative principle to at least one source work or retire it"],
                )
            )
        if works and not facts:
            gaps.append(
                self._gap(
                    field_id,
                    "needs_extraction",
                    "Works need fact extraction",
                    "The local field has works, but no structured work facts are available.",
                    related_work_ids=[work.get("work_id", "") for work in works[:8]],
                    severity=0.5,
                    novelty_potential=0.5,
                    suggested=["Run field sync to extract core ideas, insights, novelty, and evaluation signals"],
                )
            )
        if works and benchmarks and not results:
            gaps.append(
                self._gap(
                    field_id,
                    "missing_result",
                    "Benchmark rows need reported result evidence",
                    f"{len(benchmarks)} benchmark records exist, but no structured result values were extracted.",
                    related_benchmark_ids=[benchmark.get("benchmark_id", "") for benchmark in benchmarks[:10]],
                    severity=0.55,
                    novelty_potential=0.52,
                    suggested=["Inspect abstracts or PDFs for reported scores and compute accounting"],
                )
            )
        if persist and gaps:
            self.store.upsert_many("gap_cards", gaps, "gap_id")
        return gaps

    def calibrate_result_estimate(
        self,
        idea: dict[str, Any],
        field_id: str = "default",
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = data or self.store.snapshot(limit_per_bucket=None)
        estimate_id = idea.get("result_estimate_id", "")
        estimate = dict(data.get("estimates", {}).get(estimate_id, {}))
        if not estimate:
            estimate = self._normalize_estimate(idea.get("idea_id", stable_id("I", idea.get("title", ""))), {}, idea.get("source_principles", []))
        idea_text = self._material_text(idea)
        benchmarks = [
            item
            for item in self._field_items(data.get("benchmark_records", {}).values(), field_id)
            if lexical_score(idea_text, json.dumps(item, ensure_ascii=False)) > 0
        ][:8]
        results = [
            item
            for item in self._field_items(data.get("result_records", {}).values(), field_id)
            if item.get("benchmark_id") in {benchmark.get("benchmark_id") for benchmark in benchmarks}
        ][:8]
        similar_ideas = [
            other.get("idea_id")
            for other in data.get("ideas", {}).values()
            if other.get("idea_id") != idea.get("idea_id") and lexical_score(idea_text, self._material_text(other)) >= 0.18
        ][:6]
        feedback_events = [
            event.get("feedback_id")
            for event in data.get("feedback", {}).values()
            if event.get("idea_id") == idea.get("idea_id") or event.get("idea_id") in similar_ideas
        ][:8]
        calibration = dict(estimate.get("calibration_basis") or {})
        calibration.update(
            {
                "similar_ideas": similar_ideas,
                "similar_principles": idea.get("source_principles", []),
                "matched_benchmarks": [benchmark.get("benchmark_id") for benchmark in benchmarks],
                "matched_results": [result.get("result_id") for result in results],
                "feedback_events": feedback_events,
                "confidence_reason": self._estimate_confidence_reason(benchmarks, results, feedback_events),
            }
        )
        estimate["calibration_basis"] = calibration
        estimate["estimate_confidence"] = "medium" if results else ("low" if benchmarks else "very_low")
        estimate["baseline_threat_level"] = "high" if idea.get("baselines") else "unknown"
        estimate["benchmark_risk"] = "low" if benchmarks else "high"
        return estimate

    def assimilate_feedback(self, feedback: dict[str, Any], field_id: str = "default") -> dict[str, Any]:
        idea_id = str(feedback.get("idea_id") or "")
        if not idea_id:
            raise ValueError("feedback.idea_id is required")
        idea = self.store.get_item("ideas", idea_id)
        if not idea:
            raise KeyError(f"ideas:{idea_id} not found")
        outcome = str(feedback.get("outcome_label") or "inconclusive")
        strengthened = list(feedback.get("strengthened_principles") or [])
        weakened = list(feedback.get("weakened_principles") or [])
        if outcome == "supported" and not strengthened:
            strengthened = list(idea.get("source_principles", []))
        if outcome in {"contradicted", "implementation_failed"} and not weakened:
            weakened = list(idea.get("source_principles", []))
        event = FeedbackEvent(
            feedback_id=str(feedback.get("feedback_id") or stable_id("F", field_id, idea_id, outcome, utc_now())),
            field_id=field_id,
            idea_id=idea_id,
            run_id=str(feedback.get("run_id") or ""),
            outcome_label=outcome,
            metric_delta_observed=str(feedback.get("metric_delta_observed") or ""),
            runtime_cost=str(feedback.get("runtime_cost") or ""),
            strengthened_principles=strengthened,
            weakened_principles=weakened,
            new_failure_modes=list(feedback.get("new_failure_modes") or feedback.get("failure_modes") or []),
            notes=str(feedback.get("notes") or ""),
            source=str(feedback.get("source") or "user"),
        )
        event_dict = to_dict(event)
        self.store.upsert("feedback", event_dict, "feedback_id")
        idea["feedback_status"] = self._status_from_outcome(outcome)
        idea["validated"] = outcome == "supported"
        idea["updated_at"] = utc_now()
        self.store.upsert("ideas", idea, "idea_id")
        touched: list[str] = []
        for pid in strengthened:
            principle = self.store.get_item("principles", pid)
            if not principle:
                continue
            principle["confidence_score"] = round(clamp(float(principle.get("confidence_score", 0.45)) + 0.08, 0.0, 0.98), 3)
            principle["validation_level"] = self._max_validation_level(principle.get("validation_level", "L0"), "L4")
            notes = list(principle.get("validation_notes", []))
            notes.append(compact_text(f"Supported by feedback on {idea.get('title', idea_id)}: {event.metric_delta_observed or event.notes}", 260))
            principle["validation_notes"] = notes[-12:]
            principle["updated_at"] = utc_now()
            self.store.upsert("principles", principle, "principle_id")
            touched.append(pid)
        for pid in weakened:
            principle = self.store.get_item("principles", pid)
            if not principle:
                continue
            principle["confidence_score"] = round(clamp(float(principle.get("confidence_score", 0.45)) - 0.06, 0.0, 0.98), 3)
            failures = list(principle.get("failure_modes", []))
            failures.extend(event.new_failure_modes or [event.notes or f"Feedback outcome: {outcome}"])
            principle["failure_modes"] = [item for item in failures if item][-12:]
            notes = list(principle.get("validation_notes", []))
            notes.append(compact_text(f"Weakened by feedback on {idea.get('title', idea_id)}: {event.notes or outcome}", 260))
            principle["validation_notes"] = notes[-12:]
            principle["updated_at"] = utc_now()
            self.store.upsert("principles", principle, "principle_id")
            touched.append(pid)
        run_id = stable_id("R", field_id, "import_feedback", event.feedback_id)
        self.store.upsert(
            "runs",
            {
                "run_id": run_id,
                "type": "import_feedback",
                "field_id": field_id,
                "idea_id": idea_id,
                "feedback_id": event.feedback_id,
                "outcome_label": outcome,
                "principle_ids": touched,
                "created_at": utc_now(),
            },
            "run_id",
        )
        self.mine_gap_cards(field_id=field_id, persist=True, ensure=False)
        return {"ok": True, "feedback": event_dict, "idea": idea, "updated_principle_ids": touched, "run_id": run_id}

    def build_assistant_export_bundle(self, idea_id: str, target_agent: str = "codex", field_id: str = "default") -> dict[str, Any]:
        data = self.store.snapshot(limit_per_bucket=None)
        idea = data.get("ideas", {}).get(idea_id)
        if not idea:
            raise KeyError(f"ideas:{idea_id} not found")
        principle_ids = set(idea.get("source_principles", []))
        principles = [data.get("principles", {}).get(pid) for pid in principle_ids if data.get("principles", {}).get(pid)]
        work_ids = self._idea_source_work_ids(idea, principles)
        works = [data.get("source_works", {}).get(wid) for wid in work_ids if data.get("source_works", {}).get(wid)]
        benchmark_ids = {
            benchmark.get("benchmark_id")
            for benchmark in data.get("benchmark_records", {}).values()
            if benchmark.get("field_id", "default") == field_id and benchmark.get("work_id") in work_ids
        }
        benchmarks = [data["benchmark_records"][bid] for bid in benchmark_ids if bid in data.get("benchmark_records", {})]
        baselines = [
            baseline
            for baseline in data.get("baseline_records", {}).values()
            if baseline.get("field_id", "default") == field_id and baseline.get("benchmark_id") in benchmark_ids
        ]
        results = [
            result
            for result in data.get("result_records", {}).values()
            if result.get("field_id", "default") == field_id and result.get("benchmark_id") in benchmark_ids
        ]
        estimate = self.calibrate_result_estimate(idea, field_id=field_id)
        prompt_plan = data.get("prompt_plans", {}).get(idea.get("codex_prompt_plan_id", ""))
        bundle = {
            "bundle_version": "principia-v0.3",
            "target_agent": target_agent,
            "idea": idea,
            "principles": principles,
            "source_works": works,
            "benchmarks": benchmarks,
            "baselines": baselines,
            "results": results,
            "result_estimate": estimate,
            "prompt_plan": prompt_plan,
            "feedback_schema": self._assistant_feedback_schema(),
        }
        export = AssistantExport(
            export_id=stable_id("AX", field_id, idea_id, target_agent, data.get("meta", {}).get("updated_at", "")),
            field_id=field_id,
            idea_id=idea_id,
            target_agent=target_agent,
            bundle_version="principia-v0.3",
            bundle=bundle,
        )
        self.store.upsert("assistant_exports", to_dict(export), "export_id")
        return bundle

    def _ensure_field_profile(self, field_id: str, query: str = "") -> dict[str, Any]:
        existing = self.store.get_item("field_profiles", field_id)
        if existing:
            return existing
        profile = FieldProfile(
            field_id=field_id,
            name="All Local Records" if field_id == "default" else "Untitled Project",
            description="Research workspace for papers, ideas, benchmarks, baselines, and validation evidence.",
            query=query,
            domain_tags=keyword_terms(query, 6) if query else [],
            display_order=-1 if field_id == "default" else 0,
        )
        payload = to_dict(profile)
        self.store.upsert("field_profiles", payload, "field_id")
        return payload

    def _observatory_goal(self, query: str) -> dict[str, Any]:
        if query:
            return to_dict(self._fallback_goal(query, {}, self._complexity(query, {})))
        return {
            "goal_id": "G-FIELD-DEFAULT",
            "raw_query": "",
            "target_domain": "local research field",
            "search_terms": [],
            "constraints": {},
            "complexity": 0.4,
            "query_kind": "task",
        }

    def _field_items(self, items: Any, field_id: str) -> list[dict[str, Any]]:
        return [dict(item) for item in items if dict(item).get("field_id", "default") == field_id]

    def _membership_id(self, field_id: str, bucket: str, record_id: str) -> str:
        return stable_id("PM", field_id, bucket, record_id)

    def _record_id_key(self, bucket: str) -> str:
        return {
            "source_works": "work_id",
            "principles": "principle_id",
            "ideas": "idea_id",
            "work_facts": "fact_id",
            "benchmark_records": "benchmark_id",
            "baseline_records": "baseline_id",
            "result_records": "result_id",
            "gap_cards": "gap_id",
            "existed_ideas": "canonical_id",
            "takeaway_messages": "canonical_id",
            "my_ideas": "idea_id",
            "evidence_links": "link_id",
            "research_runs": "run_id",
        }.get(bucket, "id")

    def add_project_memberships(
        self,
        field_id: str,
        bucket: str,
        record_ids: list[str],
        *,
        source: str = "manual",
        prepend: bool = False,
    ) -> list[dict[str, Any]]:
        if field_id == "default":
            return []
        current = [
            item
            for item in self.store.list_items("project_memberships", limit=100000)
            if item.get("field_id") == field_id and item.get("bucket") == bucket
        ]
        existing = {item.get("record_id"): item for item in current}
        orders = [int(item.get("display_order", 0) or 0) for item in current]
        next_order = (min(orders) - len(record_ids)) if (prepend and orders) else ((max(orders) + 1) if orders else 0)
        rows = []
        for record_id in self._ordered_unique([str(item) for item in record_ids if item]):
            row = existing.get(record_id)
            if row:
                if row.get("hidden"):
                    row["hidden"] = False
                    row["updated_at"] = utc_now()
                    rows.append(row)
                continue
            rows.append(
                to_dict(
                    ProjectMembership(
                        membership_id=self._membership_id(field_id, bucket, record_id),
                        field_id=field_id,
                        bucket=bucket,
                        record_id=record_id,
                        display_order=next_order,
                        source=source,
                    )
                )
            )
            next_order += 1
        if rows:
            self.store.upsert_many("project_memberships", rows, "membership_id")
        return rows

    def _membership_ids(self, data: dict[str, Any], field_id: str, bucket: str) -> list[str]:
        if field_id == "default":
            return []
        rows = [
            dict(item)
            for item in data.get("project_memberships", {}).values()
            if item.get("field_id") == field_id and item.get("bucket") == bucket and not item.get("hidden")
        ]
        rows.sort(key=lambda item: (int(item.get("display_order", 0) or 0), item.get("created_at", "")))
        return [str(item.get("record_id")) for item in rows if item.get("record_id")]

    def _project_id_set(self, data: dict[str, Any], field_id: str, key: str) -> set[str]:
        if field_id == "default":
            return set()
        bucket = {
            "work_ids": "source_works",
            "principle_ids": "principles",
            "idea_ids": "ideas",
        }.get(key)
        if bucket:
            member_ids = self._membership_ids(data, field_id, bucket)
            if member_ids:
                return set(member_ids)
        profile = data.get("field_profiles", {}).get(field_id) or {}
        return {str(item) for item in profile.get(key, []) if item}

    def _project_records(
        self,
        data: dict[str, Any],
        field_id: str,
        bucket: str,
        *,
        query: str = "",
    ) -> list[dict[str, Any]]:
        records = list(data.get(bucket, {}).values())
        project_key = {
            "source_works": ("work_ids", "work_id"),
            "principles": ("principle_ids", "principle_id"),
            "ideas": ("idea_ids", "idea_id"),
        }.get(bucket)
        if field_id != "default":
            member_ids = self._membership_ids(data, field_id, bucket)
            id_key = self._record_id_key(bucket)
            if member_ids:
                order = {record_id: index for index, record_id in enumerate(member_ids)}
                records = [item for item in records if item.get(id_key) in order]
                records.sort(key=lambda item: order.get(item.get(id_key), 10**9))
            elif project_key:
                ids = self._project_id_set(data, field_id, project_key[0])
                records = [item for item in records if item.get(project_key[1]) in ids]
            elif bucket in {"work_facts", "benchmark_records", "baseline_records", "result_records", "gap_cards"}:
                records = self._field_items(records, field_id)
        return self._query_items(records, query)

    def project_counts(self, data: dict[str, Any], field_id: str) -> dict[str, int]:
        works = self._project_records(data, field_id, "source_works")
        principles = self._project_records(data, field_id, "principles")
        facts = self._project_records(data, field_id, "work_facts")
        benchmarks = self._project_records(data, field_id, "benchmark_records")
        baselines = self._project_records(data, field_id, "baseline_records")
        ideas = self._project_records(data, field_id, "ideas")
        benchmark_group_count = len({self._benchmark_group_key(item) for item in benchmarks})
        baseline_group_count = len({self._normalize_name(item.get("baseline_name", "")) or item.get("baseline_id", "") for item in baselines})
        return {
            "works": len(works),
            "principles": len(principles),
            "insights": len([item for item in facts if item.get("fact_type") == "insight"]),
            "novelty": len([item for item in facts if item.get("fact_type") == "novelty"]),
            "benchmarks": benchmark_group_count,
            "baselines": baseline_group_count,
            "ideas": len(ideas),
        }

    def project_summary(self, field_id: str = "default", query: str = "") -> dict[str, Any]:
        data = self.store.snapshot(limit_per_bucket=None)
        profile = data.get("field_profiles", {}).get(field_id)
        if not profile and field_id == "default":
            profile = to_dict(FieldProfile(field_id="default", name="All Local Records", display_order=-1))
        if not profile:
            raise KeyError(f"field_profiles:{field_id} not found")
        return {
            "project": profile,
            "counts": self.project_counts(data, field_id),
            "last_sync": data.get("meta", {}).get("updated_at"),
            "refresh_status": profile.get("refresh_status", "idle"),
            "last_refresh_at": profile.get("last_refresh_at", ""),
        }

    def build_project_tab(
        self,
        field_id: str,
        tab: str,
        *,
        offset: int = 0,
        limit: int = 10,
        query: str = "",
    ) -> dict[str, Any]:
        data = self.store.snapshot(limit_per_bucket=None)
        tab = tab if tab in {"works", "principles", "insights", "novelty", "benchmarks", "baselines", "ideas"} else "works"
        collections: dict[str, Any] = {}
        if tab == "works":
            items = self.repair_language_variants_many(self._project_records(data, field_id, "source_works", query=query))
        elif tab == "principles":
            items = self.repair_language_variants_many(self._project_records(data, field_id, "principles", query=query))
            works = data.get("source_works", {})
            for item in items:
                item["source_work_links"] = [
                    {
                        "work_id": work_id,
                        "title": works.get(work_id, {}).get("title", work_id),
                        "url": works.get(work_id, {}).get("url_or_doi", ""),
                    }
                    for work_id in item.get("source_works", [])
                    if work_id
                ]
        elif tab == "insights":
            view = self.build_fact_view("insight", field_id=field_id, query=query)
            items = view.get("items", [])
            collections = view
        elif tab == "novelty":
            view = self.build_fact_view("novelty", field_id=field_id, query=query)
            items = view.get("items", [])
            collections = view
        elif tab == "benchmarks":
            view = self.build_benchmark_view(field_id=field_id, query=query)
            items = view.get("items", [])
            collections = view
        elif tab == "baselines":
            view = self.build_baseline_view(field_id=field_id, query=query)
            items = view.get("items", [])
            collections = view
        else:
            items = self.repair_language_variants_many(self._project_records(data, field_id, "ideas", query=query))
            for item in items:
                estimate = dict(data.get("estimates", {}).get(item.get("result_estimate_id", ""), {}))
                if estimate:
                    estimate.setdefault("estimate_confidence", "stored")
                item["_calibrated_estimate"] = estimate
                item["_prompt_plan"] = data.get("prompt_plans", {}).get(item.get("codex_prompt_plan_id", ""))
        total = len(items)
        offset = max(0, int(offset or 0))
        limit = max(1, min(int(limit or 10), 50))
        page = items[offset : offset + limit]
        return {
            "field_id": field_id,
            "tab": tab,
            "items": page,
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": offset + limit < total,
            "counts": self.project_counts(data, field_id),
            "collections": {key: value for key, value in collections.items() if key != "items"},
        }

    def _query_items(self, items: Any, query: str) -> list[dict[str, Any]]:
        output = [dict(item) for item in items]
        if not query:
            return output
        return [item for item in output if lexical_score(query, self._material_text(item)) > 0]

    def _ordered_unique(self, items: list[Any]) -> list[Any]:
        output = []
        seen: set[str] = set()
        for item in items:
            key = str(item)
            if not key or key in seen:
                continue
            seen.add(key)
            output.append(item)
        return output

    def _coverage_payload(
        self,
        works: list[dict[str, Any]],
        facts: list[dict[str, Any]],
        benchmarks: list[dict[str, Any]],
        baselines: list[dict[str, Any]],
        results: list[dict[str, Any]],
        principles: list[dict[str, Any]],
    ) -> dict[str, float]:
        work_ids = {work.get("work_id") for work in works}
        facts_by_type: dict[str, set[str]] = {}
        for fact in facts:
            facts_by_type.setdefault(fact.get("fact_type", ""), set()).add(fact.get("work_id", ""))
        principle_work_ids = {
            wid
            for principle in principles
            for wid in principle.get("source_works", [])
            if wid in work_ids
        }
        total = max(len(work_ids), 1)

        def ratio(count: int) -> float:
            return round(count / total, 3)

        return {
            "core_idea": ratio(len(facts_by_type.get("core_idea", set()) | {work.get("work_id") for work in works if work.get("work_principles")})),
            "motivation": ratio(len(facts_by_type.get("motivation", set()))),
            "insight": ratio(len(facts_by_type.get("insight", set()) | {work.get("work_id") for work in works if work.get("work_insights")})),
            "novelty": ratio(len(facts_by_type.get("novelty", set()) | {work.get("work_id") for work in works if work.get("work_novelty")})),
            "principle": ratio(len(facts_by_type.get("principle", set()) | principle_work_ids)),
            "benchmark": ratio(len({item.get("work_id") for item in benchmarks})),
            "baseline": ratio(len({item.get("work_id") for item in baselines})),
            "result": ratio(len({item.get("work_id") for item in results})),
            "evidence_span": ratio(
                len(
                    {
                        fact.get("work_id")
                        for fact in facts
                        if fact.get("evidence_span")
                    }
                )
            ),
        }

    def _top_principles_payload(
        self,
        principles: list[dict[str, Any]],
        ideas: list[dict[str, Any]],
        works: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        idea_counts: dict[str, int] = {}
        for idea in ideas:
            for pid in idea.get("source_principles", []):
                idea_counts[pid] = idea_counts.get(pid, 0) + 1
        rows = []
        for principle in principles:
            pid = principle.get("principle_id", "")
            rows.append(
                {
                    "principle_id": pid,
                    "name": principle.get("name", pid),
                    "abstract_signature": principle.get("abstract_signature", ""),
                    "mechanism": principle.get("mechanism", ""),
                    "validation_level": principle.get("validation_level", "L0"),
                    "confidence_score": principle.get("confidence_score", 0),
                    "source_work_count": len(principle.get("source_works", [])),
                    "idea_count": idea_counts.get(pid, 0),
                    "domain_tags": principle.get("domain_tags", [])[:4],
                    "source_titles": [
                        works.get(wid, {}).get("title", wid)
                        for wid in principle.get("source_works", [])[:3]
                    ],
                }
            )
        rows.sort(
            key=lambda item: (
                validation_number(item.get("validation_level", "L0")),
                float(item.get("confidence_score", 0)),
                int(item.get("source_work_count", 0)),
                int(item.get("idea_count", 0)),
            ),
            reverse=True,
        )
        return rows

    def _recent_items(self, items: list[dict[str, Any]], id_key: str) -> list[dict[str, Any]]:
        rows = []
        for item in items:
            row = dict(item)
            row["_id"] = row.get(id_key, "")
            row["_title"] = row.get("title") or row.get("name") or row.get(id_key, "")
            rows.append(row)
        rows.sort(key=lambda item: item.get("updated_at") or item.get("created_at") or "", reverse=True)
        return rows

    def _frontier_brief(
        self,
        counts: dict[str, int],
        coverage: dict[str, float],
        top_principles: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not counts.get("works"):
            return {
                "summary": "No local field records yet. Generate or ingest papers to build the first principle and benchmark map.",
                "evidence": [],
            }
        top = top_principles[0] if top_principles else {}
        weak_eval = coverage.get("baseline", 0) < 0.35 or coverage.get("result", 0) < 0.25
        work_label = self._plural(counts.get("works", 0), "work", "works")
        principle_label = self._plural(counts.get("principles", 0), "principle", "principles")
        idea_label = self._plural(counts.get("ideas", 0), "generated idea", "generated ideas")
        sentence = (
            f"The local field currently tracks {counts.get('works', 0)} {work_label}, "
            f"{counts.get('principles', 0)} {principle_label}, and {counts.get('ideas', 0)} {idea_label}."
        )
        if top:
            sentence += f" The strongest reusable mechanism is '{top.get('name')}', supported by {top.get('source_work_count', 0)} source works."
        if weak_eval:
            sentence += " Evaluation coverage is still thin, so benchmark and nearest-baseline extraction should be treated as the next frontier task."
        elif warnings:
            sentence += f" The main open warning is {warnings[0].get('title', 'a field gap').lower()}."
        else:
            sentence += " Benchmark, baseline, and result records are present enough to support first-pass local calibration."
        evidence = []
        if top:
            evidence.append({"type": "principle", "id": top.get("principle_id", ""), "label": top.get("name", "")})
        for warning in warnings[:2]:
            evidence.append({"type": "gap", "id": warning.get("gap_id", ""), "label": warning.get("title", "")})
        return {"summary": sentence, "evidence": evidence}

    def _plural(self, count: int, singular: str, plural: str) -> str:
        return singular if int(count or 0) == 1 else plural

    def _principle_families(self, principles: list[dict[str, Any]], ideas: list[dict[str, Any]]) -> list[dict[str, Any]]:
        idea_counts: dict[str, int] = {}
        for idea in ideas:
            for pid in idea.get("source_principles", []):
                idea_counts[pid] = idea_counts.get(pid, 0) + 1
        families: dict[str, dict[str, Any]] = {}
        for principle in principles:
            family = (
                (principle.get("domain_tags") or [None])[0]
                or principle.get("principle_type")
                or "general mechanisms"
            )
            row = families.setdefault(
                family,
                {"family": family, "principles": 0, "works": set(), "ideas": 0, "confidence": 0.0},
            )
            row["principles"] += 1
            row["works"].update(principle.get("source_works", []))
            row["ideas"] += idea_counts.get(principle.get("principle_id", ""), 0)
            row["confidence"] += float(principle.get("confidence_score", 0))
        output = []
        for row in families.values():
            count = max(row["principles"], 1)
            output.append(
                {
                    "family": row["family"],
                    "principles": row["principles"],
                    "works": len(row["works"]),
                    "ideas": row["ideas"],
                    "mean_confidence": round(row["confidence"] / count, 2),
                }
            )
        output.sort(key=lambda item: (item["principles"], item["works"], item["ideas"]), reverse=True)
        return output[:8]

    def _frontier_timeline(
        self,
        works: list[dict[str, Any]],
        principles: list[dict[str, Any]],
        gaps: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for work in works:
            year = work.get("year")
            if year:
                rows.append({"time": str(year), "type": "work", "label": compact_text(work.get("title", "Work"), 110), "id": work.get("work_id", "")})
        for principle in principles[:12]:
            created = str(principle.get("created_at") or "")[:10] or "local"
            rows.append({"time": created, "type": "principle", "label": compact_text(principle.get("name", "Principle"), 110), "id": principle.get("principle_id", "")})
        for gap in gaps[:8]:
            created = str(gap.get("created_at") or "")[:10] or "local"
            rows.append({"time": created, "type": "gap", "label": compact_text(gap.get("title", "Gap"), 110), "id": gap.get("gap_id", "")})
        rows.sort(key=lambda item: item["time"], reverse=True)
        return rows[:16]

    def _gap(
        self,
        field_id: str,
        gap_type: str,
        title: str,
        summary: str,
        *,
        evidence_fact_ids: list[str] | None = None,
        related_work_ids: list[str] | None = None,
        related_principle_ids: list[str] | None = None,
        related_benchmark_ids: list[str] | None = None,
        severity: float = 0.5,
        novelty_potential: float = 0.5,
        suggested: list[str] | None = None,
    ) -> dict[str, Any]:
        card = GapCard(
            gap_id=stable_id("GAP", field_id, gap_type, title),
            field_id=field_id,
            gap_type=gap_type,
            title=title,
            summary=summary,
            evidence_fact_ids=[item for item in (evidence_fact_ids or []) if item],
            related_work_ids=[item for item in (related_work_ids or []) if item],
            related_principle_ids=[item for item in (related_principle_ids or []) if item],
            related_benchmark_ids=[item for item in (related_benchmark_ids or []) if item],
            suggested_idea_seeds=suggested or [],
            severity=round(clamp(severity, 0.0, 1.0), 2),
            novelty_potential=round(clamp(novelty_potential, 0.0, 1.0), 2),
        )
        return to_dict(card)

    def _normalize_name(self, text: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()[:160]

    def _contains_any(self, text: str, terms: list[str]) -> bool:
        lower = str(text or "").lower()
        return any(term.lower() in lower for term in terms)

    def _work_source_hash(self, work: dict[str, Any]) -> str:
        payload = json.dumps(
            {
                "title": work.get("title", ""),
                "abstract": work.get("abstract", ""),
                "url_or_doi": work.get("url_or_doi", ""),
                "source_updated_at": work.get("source_updated_at", ""),
                "work_principles": work.get("work_principles", []),
                "work_insights": work.get("work_insights", []),
                "work_novelty": work.get("work_novelty", []),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def _proposed_method_name(self, work: dict[str, Any]) -> str:
        title = compact_text(str(work.get("title") or "Proposed method"), 80)
        for prefix in ("A ", "An ", "The "):
            if title.startswith(prefix) and len(title) > len(prefix) + 8:
                title = title[len(prefix) :]
        return title or "Proposed method"

    def _matched_terms(self, text: str, terms: list[str]) -> list[str]:
        source = str(text or "")
        matches = []
        for term in terms:
            pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", re.IGNORECASE)
            if pattern.search(source) and term not in matches:
                matches.append(term)
        return matches

    def _extract_dataset_suite_terms(self, text: str) -> list[str]:
        output: list[str] = []
        patterns = [
            r"(?:evaluate|evaluated|experiments?\s+(?:are\s+)?(?:on|use)|benchmarks?\s+(?:include|cover|on)|datasets?\s+(?:include|are|:)|evaluation\s+uses)\s+([^.;]{0,320})",
            r"(?:on|across)\s+((?:[A-Z][A-Za-z0-9+\-_/]*(?:,\s*|\s+and\s+)){2,}[A-Z][A-Za-z0-9+\-_/]*)",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text or "", flags=re.IGNORECASE):
                for item in self._split_entity_list(match.group(1)):
                    name = self._clean_extracted_entity(item)
                    if self._is_plausible_benchmark_name(name):
                        output.append(name)
        return self._ordered_unique(output)[:40]

    def _extract_compared_methods(self, text: str) -> list[str]:
        output: list[str] = []
        patterns = [
            r"(?:compare(?:s|d)?\s+(?:against|with|to)|comparison\s+(?:against|with)|baselines?\s+(?:include|are|:)|against)\s+([^.;]{0,260})",
            r"(?:compared\s+methods?\s+(?:include|are|:))\s+([^.;]{0,260})",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text or "", flags=re.IGNORECASE):
                fragment = re.split(r"\b(?:on|under|using|report(?:s|ed|ing)?|achiev(?:e|es|ed|ing)?)\b", match.group(1), maxsplit=1, flags=re.IGNORECASE)[0]
                for item in self._split_entity_list(fragment):
                    name = self._clean_extracted_entity(item)
                    if self._is_plausible_method_name(name):
                        output.append(name)
        return self._ordered_unique(output)[:40]

    def _split_entity_list(self, text: str) -> list[str]:
        value = re.sub(r"\([^)]{0,80}\)", "", str(text or ""))
        value = re.sub(r"\bet\s+al\.?", "", value, flags=re.IGNORECASE)
        value = value.replace("/", ",")
        parts = re.split(r",|;|\s+\+\s+|\s+and\s+|\s+or\s+", value)
        return [part.strip() for part in parts if part.strip()]

    def _clean_extracted_entity(self, text: str) -> str:
        value = re.sub(r"^(?:the|a|an|our|their|its|method|model|baseline|baselines|dataset|datasets)\s+", "", str(text or "").strip(), flags=re.IGNORECASE)
        value = re.sub(r"\s+(?:baseline|baselines|dataset|datasets|benchmark|benchmarks)$", "", value, flags=re.IGNORECASE)
        value = value.strip(" .,:;()[]{}")
        return compact_text(value, 90)

    def _is_plausible_benchmark_name(self, name: str) -> bool:
        if not name or len(name) < 2 or len(name) > 90:
            return False
        lower = name.lower()
        if lower in {"we", "this work", "the method", "accuracy", "latency", "gpu hours", "base-to-novel split"}:
            return False
        if any(term.lower() == lower for term in self._baseline_terms()):
            return False
        return bool(re.search(r"[A-Za-z]", name)) and (bool(re.search(r"[A-Z0-9]", name)) or "-" in name)

    def _is_plausible_method_name(self, name: str) -> bool:
        if not name or len(name) < 2 or len(name) > 90:
            return False
        lower = name.lower()
        blocked = {
            "the method",
            "our method",
            "we",
            "accuracy",
            "top-1 accuracy",
            "latency",
            "gpu hours",
            "base-to-novel split",
            "few-shot split",
        }
        if lower in blocked:
            return False
        if any(term.lower() == lower for term in self._dataset_terms()):
            return False
        return bool(re.search(r"[A-Za-z]", name)) and not lower.startswith(("under ", "with ", "using "))

    def _benchmark_group_key(self, record: dict[str, Any]) -> str:
        dataset = self._normalize_name(record.get("dataset", ""))
        task = self._normalize_name(record.get("task", ""))
        return stable_id("BMK", dataset or task or "unspecified benchmark")

    def _benchmark_catalog_info(self, dataset: str) -> dict[str, Any]:
        key = self._normalize_name(dataset)
        catalog = {
            "imagenet": {
                "description": "Large-scale image classification benchmark commonly used to evaluate visual representation transfer and adaptation.",
                "data_form": "Labeled natural images organized by object category; standard classification labels and train/validation splits.",
                "scale": "Approximately 1.2M training images and 50K validation images in the ILSVRC classification setup.",
                "official_url": "https://www.image-net.org/",
                "source": "ImageNet / ILSVRC",
            },
            "caltech101": {
                "description": "Object-category image classification benchmark used in few-shot and transfer-learning evaluations.",
                "data_form": "Images across 101 object categories plus background, usually sampled into few-shot train/test splits.",
                "scale": "Roughly 9K images across 101 categories.",
                "official_url": "https://data.caltech.edu/records/mzrjq-6wc02",
                "source": "Caltech",
            },
            "oxfordpets": {
                "description": "Fine-grained pet breed classification benchmark with cat and dog categories.",
                "data_form": "Pet images with breed labels and segmentation trimaps.",
                "scale": "Around 7.3K images across 37 pet breeds.",
                "official_url": "https://www.robots.ox.ac.uk/~vgg/data/pets/",
                "source": "University of Oxford VGG",
            },
            "food101": {
                "description": "Fine-grained food image classification benchmark.",
                "data_form": "Food images grouped into 101 dish categories.",
                "scale": "101K images, 1K per class.",
                "official_url": "https://data.vision.ee.ethz.ch/cvl/datasets_extra/food-101/",
                "source": "ETH Zurich",
            },
            "dtd": {
                "description": "Texture recognition benchmark for describable visual texture categories.",
                "data_form": "Texture images annotated with describable texture classes.",
                "scale": "5,640 images across 47 texture categories.",
                "official_url": "https://www.robots.ox.ac.uk/~vgg/data/dtd/",
                "source": "University of Oxford VGG",
            },
            "eurosat": {
                "description": "Remote-sensing land-use and land-cover classification benchmark.",
                "data_form": "Sentinel-2 satellite image patches with land-use labels.",
                "scale": "27K images across 10 land-use classes.",
                "official_url": "https://github.com/phelber/eurosat",
                "source": "EuroSAT",
            },
            "ucf101": {
                "description": "Human action recognition benchmark built from realistic action videos.",
                "data_form": "Video clips labeled with action classes.",
                "scale": "13K videos across 101 action categories.",
                "official_url": "https://www.crcv.ucf.edu/data/UCF101.php",
                "source": "University of Central Florida",
            },
            "sun397": {
                "description": "Scene recognition benchmark covering a broad range of scene categories.",
                "data_form": "Scene images labeled by scene category.",
                "scale": "108K images across 397 scene categories.",
                "official_url": "https://vision.princeton.edu/projects/2010/SUN/",
                "source": "SUN Database",
            },
            "c maps": {
                "description": "Turbofan engine degradation benchmark for remaining useful life prediction.",
                "data_form": "Multivariate time-series sensor readings with simulated operating conditions and degradation trajectories.",
                "scale": "Multiple train/test subsets of engine trajectories.",
                "official_url": "https://data.nasa.gov/dataset/C-MAPSS-Aircraft-Engine-Simulator-Data/xaut-bemq",
                "source": "NASA Prognostics Center of Excellence",
            },
            "dtu": {
                "description": "Multi-view stereo reconstruction benchmark used for 3D reconstruction quality evaluation.",
                "data_form": "Multi-view images with calibrated cameras and ground-truth scans.",
                "scale": "Dozens of scenes captured under controlled lighting.",
                "official_url": "https://roboimagedata.compute.dtu.dk/?page_id=36",
                "source": "Technical University of Denmark",
            },
            "swe bench": {
                "description": "Software engineering benchmark where systems repair real GitHub issues.",
                "data_form": "Repository snapshots, issue descriptions, tests, and patch targets.",
                "scale": "Thousands of issue-task instances across Python repositories.",
                "official_url": "https://www.swebench.com/",
                "source": "SWE-bench",
            },
            "cifar 10": {
                "description": "Small natural-image classification benchmark used for algorithmic and robustness comparisons.",
                "data_form": "32x32 color images with single-label object categories.",
                "scale": "60K images across 10 classes.",
                "official_url": "https://www.cs.toronto.edu/~kriz/cifar.html",
                "source": "University of Toronto",
            },
            "cifar 100": {
                "description": "Small natural-image classification benchmark with fine-grained category labels.",
                "data_form": "32x32 color images with 100 fine classes and 20 coarse classes.",
                "scale": "60K images across 100 classes.",
                "official_url": "https://www.cs.toronto.edu/~kriz/cifar.html",
                "source": "University of Toronto",
            },
            "mnist": {
                "description": "Handwritten digit classification benchmark.",
                "data_form": "Grayscale handwritten digit images with digit labels.",
                "scale": "70K images across 10 digit classes.",
                "official_url": "http://yann.lecun.com/exdb/mnist/",
                "source": "Yann LeCun / NYU",
            },
            "fashion mnist": {
                "description": "Fashion product image classification benchmark designed as a harder MNIST-style replacement.",
                "data_form": "Grayscale clothing images with category labels.",
                "scale": "70K images across 10 fashion classes.",
                "official_url": "https://github.com/zalandoresearch/fashion-mnist",
                "source": "Zalando Research",
            },
            "svhn": {
                "description": "Street View House Numbers benchmark for digit recognition in natural images.",
                "data_form": "Cropped house-number digit images with labels.",
                "scale": "More than 600K digit images including extra training data.",
                "official_url": "http://ufldl.stanford.edu/housenumbers/",
                "source": "Stanford",
            },
            "fgvcaircraft": {
                "description": "Fine-grained aircraft classification benchmark.",
                "data_form": "Aircraft images annotated with variant, family, and manufacturer labels.",
                "scale": "10K images across 100 aircraft variants.",
                "official_url": "https://www.robots.ox.ac.uk/~vgg/data/fgvc-aircraft/",
                "source": "University of Oxford VGG",
            },
            "stanfordcars": {
                "description": "Fine-grained car classification benchmark.",
                "data_form": "Car images with make, model, and year labels.",
                "scale": "16K images across 196 car classes.",
                "official_url": "https://ai.stanford.edu/~jkrause/cars/car_dataset.html",
                "source": "Stanford AI Lab",
            },
            "flowers102": {
                "description": "Fine-grained flower classification benchmark.",
                "data_form": "Flower images with species labels.",
                "scale": "8K images across 102 flower categories.",
                "official_url": "https://www.robots.ox.ac.uk/~vgg/data/flowers/102/",
                "source": "University of Oxford VGG",
            },
            "coco": {
                "description": "Large-scale image benchmark for detection, segmentation, captioning, and keypoints.",
                "data_form": "Images with object annotations, segmentations, captions, and task-specific labels.",
                "scale": "Hundreds of thousands of labeled images depending on split/task.",
                "official_url": "https://cocodataset.org/#download",
                "source": "COCO Consortium",
            },
            "pascal voc": {
                "description": "Classic visual object recognition benchmark for classification, detection, and segmentation.",
                "data_form": "Natural images with object class and localization annotations.",
                "scale": "Multiple annual challenge splits.",
                "official_url": "http://host.robots.ox.ac.uk/pascal/VOC/",
                "source": "PASCAL VOC",
            },
            "ade20k": {
                "description": "Scene parsing benchmark with dense semantic segmentation annotations.",
                "data_form": "Scene images with pixel-level object and stuff labels.",
                "scale": "More than 20K annotated scene images.",
                "official_url": "https://groups.csail.mit.edu/vision/datasets/ADE20K/",
                "source": "MIT CSAIL",
            },
            "cityscapes": {
                "description": "Urban street-scene benchmark for semantic understanding.",
                "data_form": "Street-view images with fine and coarse pixel-level annotations.",
                "scale": "Thousands of annotated urban driving images.",
                "official_url": "https://www.cityscapes-dataset.com/",
                "source": "Cityscapes",
            },
            "kitti": {
                "description": "Autonomous-driving benchmark suite for vision, depth, odometry, and detection.",
                "data_form": "Synchronized camera, LiDAR, GPS/IMU, and annotation data.",
                "scale": "Multiple task-specific datasets and sequences.",
                "official_url": "https://www.cvlibs.net/datasets/kitti/",
                "source": "KITTI Vision Benchmark",
            },
            "gsm8k": {
                "description": "Grade-school math reasoning benchmark.",
                "data_form": "Natural-language math word problems with worked answers.",
                "scale": "8.5K multi-step arithmetic problems.",
                "official_url": "https://huggingface.co/datasets/openai/gsm8k",
                "source": "OpenAI / Hugging Face",
            },
            "math": {
                "description": "Competition-style mathematical reasoning benchmark covering algebra, geometry, counting, probability, number theory, and precalculus.",
                "data_form": "Natural-language math problems with final answers and solutions.",
                "scale": "12.5K problems across multiple difficulty levels and subject areas.",
                "official_url": "https://github.com/hendrycks/math",
                "source": "Hendrycks et al.",
            },
            "aqua": {
                "description": "Algebraic word-problem benchmark for multi-step quantitative reasoning.",
                "data_form": "Multiple-choice math word problems with rationales.",
                "scale": "Roughly 100K algebraic word problems.",
                "official_url": "https://huggingface.co/datasets/deepmind/aqua_rat",
                "source": "DeepMind / Hugging Face",
            },
            "aqua rat": {
                "description": "Algebraic word-problem benchmark for multi-step quantitative reasoning.",
                "data_form": "Multiple-choice math word problems with rationales.",
                "scale": "Roughly 100K algebraic word problems.",
                "official_url": "https://huggingface.co/datasets/deepmind/aqua_rat",
                "source": "DeepMind / Hugging Face",
            },
            "svamp": {
                "description": "Arithmetic word-problem benchmark designed to test robustness to variations in wording and structure.",
                "data_form": "Short natural-language math questions with numeric answers.",
                "scale": "1K word problems.",
                "official_url": "https://huggingface.co/datasets/ChilleD/SVAMP",
                "source": "SVAMP / Hugging Face",
            },
            "multiarith": {
                "description": "Multi-step arithmetic word-problem benchmark.",
                "data_form": "Natural-language arithmetic questions with numeric answers.",
                "scale": "600 math word problems.",
                "official_url": "https://huggingface.co/datasets/ChilleD/MultiArith",
                "source": "MultiArith / Hugging Face",
            },
            "humaneval": {
                "description": "Python code-generation benchmark for function synthesis.",
                "data_form": "Programming prompts with unit tests.",
                "scale": "164 programming problems.",
                "official_url": "https://github.com/openai/human-eval",
                "source": "OpenAI",
            },
            "mmlu": {
                "description": "Massive Multitask Language Understanding benchmark for broad academic and professional knowledge.",
                "data_form": "Multiple-choice questions spanning many subject areas.",
                "scale": "Roughly 14K questions across 57 tasks.",
                "official_url": "https://huggingface.co/datasets/cais/mmlu",
                "source": "CAIS / Hugging Face",
            },
            "gpqa": {
                "description": "Graduate-Level Google-Proof Q&A benchmark for difficult expert-written science questions.",
                "data_form": "Multiple-choice science questions designed to resist simple web lookup.",
                "scale": "448 challenging questions in the main diamond split.",
                "official_url": "https://huggingface.co/datasets/Idavidrein/gpqa",
                "source": "GPQA / Hugging Face",
            },
            "aime": {
                "description": "Mathematical problem-solving benchmark based on American Invitational Mathematics Examination problems.",
                "data_form": "Competition math questions with integer answers.",
                "scale": "Annual problem sets; commonly evaluated as curated benchmark splits.",
                "official_url": "https://huggingface.co/datasets/Maxwell-Jia/AIME_2024",
                "source": "AIME / Hugging Face",
            },
            "mbpp": {
                "description": "Mostly Basic Python Problems benchmark for code generation.",
                "data_form": "Natural-language programming tasks with Python tests.",
                "scale": "Around 1K crowd-sourced Python programming tasks.",
                "official_url": "https://huggingface.co/datasets/google-research-datasets/mbpp",
                "source": "Google Research / Hugging Face",
            },
            "logicbench": {
                "description": "Logical-reasoning benchmark suite designed for systematic evaluation of LLM reasoning patterns.",
                "data_form": "Reasoning questions spanning propositional, first-order, and non-monotonic logic patterns.",
                "scale": "Multiple logical reasoning task families and difficulty patterns.",
                "official_url": "https://github.com/teacherpeterpan/LogicBench",
                "source": "LogicBench",
            },
            "logiqa": {
                "description": "Logical reasoning reading-comprehension benchmark derived from expert-written exam questions.",
                "data_form": "Multiple-choice passages and logical reasoning questions.",
                "scale": "Thousands of logical reasoning examples.",
                "official_url": "https://huggingface.co/datasets/lucasmccabe/logiqa",
                "source": "LogiQA / Hugging Face",
            },
            "logiqa2 0": {
                "description": "Expanded logical reasoning benchmark for natural-language inference and exam-style reasoning.",
                "data_form": "Multiple-choice logical reasoning questions.",
                "scale": "Thousands of examples across train/dev/test splits.",
                "official_url": "https://github.com/csitfun/LogiQA2.0",
                "source": "LogiQA2.0",
            },
            "reclor": {
                "description": "Reading comprehension benchmark for logical reasoning.",
                "data_form": "Multiple-choice logic questions with passages and answer options.",
                "scale": "More than 6K questions.",
                "official_url": "https://whyu.me/reclor/",
                "source": "ReClor",
            },
            "folio": {
                "description": "Natural-language reasoning benchmark grounded in first-order logic.",
                "data_form": "Premises and conclusions labeled for logical entailment.",
                "scale": "More than 1K expert-written examples.",
                "official_url": "https://huggingface.co/datasets/yale-nlp/FOLIO",
                "source": "Yale NLP / Hugging Face",
            },
            "proofwriter": {
                "description": "Rule-based logical reasoning benchmark requiring multi-hop proof construction.",
                "data_form": "Facts, rules, questions, and proof labels.",
                "scale": "Synthetic datasets across proof depths.",
                "official_url": "https://huggingface.co/datasets/tasksource/proofwriter",
                "source": "ProofWriter / Hugging Face",
            },
            "prontoqa": {
                "description": "Synthetic logical reasoning benchmark for testing chain-of-thought and formal reasoning behavior.",
                "data_form": "Natural-language logical rules and queries.",
                "scale": "Synthetic reasoning instances with controlled proof structure.",
                "official_url": "https://github.com/asaparov/prontoqa",
                "source": "PrOntoQA",
            },
            "logical deduction": {
                "description": "BIG-Bench Hard logical-deduction task family for constrained natural-language reasoning.",
                "data_form": "Multiple-choice logical deduction prompts.",
                "scale": "Three difficulty levels inside BIG-Bench Hard.",
                "official_url": "https://github.com/suzgunmirac/BIG-Bench-Hard",
                "source": "BIG-Bench Hard",
            },
            "strategyqa": {
                "description": "Question-answering benchmark requiring implicit multi-step reasoning strategies.",
                "data_form": "Yes/no questions with supporting facts.",
                "scale": "2.7K strategy questions.",
                "official_url": "https://huggingface.co/datasets/ChilleD/StrategyQA",
                "source": "StrategyQA / Hugging Face",
            },
            "commonsenseqa": {
                "description": "Multiple-choice commonsense reasoning benchmark.",
                "data_form": "Commonsense questions with answer options.",
                "scale": "12K questions.",
                "official_url": "https://huggingface.co/datasets/tau/commonsense_qa",
                "source": "CommonsenseQA / Hugging Face",
            },
            "drop": {
                "description": "Reading comprehension benchmark requiring discrete reasoning over paragraphs.",
                "data_form": "Paragraph-question-answer examples with numerical, counting, and span reasoning.",
                "scale": "96K question-answer pairs.",
                "official_url": "https://huggingface.co/datasets/ucinlp/drop",
                "source": "DROP / Hugging Face",
            },
            "musr": {
                "description": "Multistep soft reasoning benchmark for long-context reasoning.",
                "data_form": "Multiple-choice reasoning problems with narratives and constraints.",
                "scale": "Task-specific MuSR splits.",
                "official_url": "https://huggingface.co/datasets/TAUR-Lab/MuSR",
                "source": "MuSR / Hugging Face",
            },
            "mus r": {
                "description": "Multistep soft reasoning benchmark for long-context reasoning.",
                "data_form": "Multiple-choice reasoning problems with narratives and constraints.",
                "scale": "Task-specific MuSR splits.",
                "official_url": "https://huggingface.co/datasets/TAUR-Lab/MuSR",
                "source": "MuSR / Hugging Face",
            },
            "mu sr": {
                "description": "Multistep soft reasoning benchmark for long-context reasoning.",
                "data_form": "Multiple-choice reasoning problems with narratives and constraints.",
                "scale": "Task-specific MuSR splits.",
                "official_url": "https://huggingface.co/datasets/TAUR-Lab/MuSR",
                "source": "MuSR / Hugging Face",
            },
            "a 3 bench": {
                "description": "Memory-driven scientific reasoning benchmark for evaluating how models use evidence over reasoning steps.",
                "data_form": "Scientific reasoning tasks with memory/evidence structure.",
                "scale": "Benchmark suite introduced with A^3-Bench.",
                "official_url": "https://github.com/PerceptionComputingLab/A3-Bench",
                "source": "A^3-Bench",
            },
            "halluscore": {
                "description": "Hallucination question-answering benchmark for measuring hallucination behavior across reasoning difficulty levels.",
                "data_form": "Question-answering examples grouped by hallucination and reasoning categories.",
                "scale": "Benchmark suite for hallucination evaluation.",
                "official_url": "https://github.com/tianyi-lab/HalluScore",
                "source": "HalluScore",
            },
            "arc": {
                "description": "AI2 science-question benchmark for grade-school science reasoning.",
                "data_form": "Multiple-choice science exam questions.",
                "scale": "ARC Easy and ARC Challenge splits.",
                "official_url": "https://huggingface.co/datasets/allenai/ai2_arc",
                "source": "AI2 / Hugging Face",
            },
            "arc challenge": {
                "description": "Hard split of the AI2 science-question benchmark.",
                "data_form": "Multiple-choice science exam questions.",
                "scale": "ARC Challenge split.",
                "official_url": "https://huggingface.co/datasets/allenai/ai2_arc",
                "source": "AI2 / Hugging Face",
            },
            "bbh": {
                "description": "BIG-Bench Hard suite of challenging reasoning tasks.",
                "data_form": "Task-specific prompts and labels for hard BIG-Bench tasks.",
                "scale": "23 challenging task families.",
                "official_url": "https://github.com/suzgunmirac/BIG-Bench-Hard",
                "source": "BIG-Bench Hard",
            },
            "big bench": {
                "description": "Collaborative benchmark suite for probing broad language-model capabilities.",
                "data_form": "Many task-specific prompt/answer datasets.",
                "scale": "Hundreds of benchmark tasks.",
                "official_url": "https://github.com/google/BIG-bench",
                "source": "BIG-Bench",
            },
            "big bench hard": {
                "description": "Subset of BIG-Bench tasks selected for difficulty under prior language models.",
                "data_form": "Task-specific prompts and labels for hard reasoning tasks.",
                "scale": "23 challenging task families.",
                "official_url": "https://github.com/suzgunmirac/BIG-Bench-Hard",
                "source": "BIG-Bench Hard",
            },
            "hellaswag": {
                "description": "Commonsense natural-language inference benchmark for grounded situation completion.",
                "data_form": "Multiple-choice context continuation examples.",
                "scale": "Around 70K examples.",
                "official_url": "https://huggingface.co/datasets/Rowan/hellaswag",
                "source": "HellaSwag / Hugging Face",
            },
            "winogrande": {
                "description": "Adversarial pronoun-resolution benchmark for commonsense reasoning.",
                "data_form": "Fill-in-the-blank sentence pairs with pronoun/coreference choices.",
                "scale": "44K examples.",
                "official_url": "https://huggingface.co/datasets/allenai/winogrande",
                "source": "AI2 / Hugging Face",
            },
            "truthfulqa": {
                "description": "Benchmark for whether language models avoid imitative falsehoods.",
                "data_form": "Questions with truthful and false reference answers.",
                "scale": "817 questions.",
                "official_url": "https://huggingface.co/datasets/truthfulqa/truthful_qa",
                "source": "TruthfulQA / Hugging Face",
            },
        }
        for name, info in sorted(catalog.items(), key=lambda pair: len(pair[0]), reverse=True):
            if key == name or name in key:
                return info
        return {
            "description": f"{dataset or 'Benchmark'} appears in local source evidence. Add official metadata when you curate this project.",
            "data_form": "Unknown from local metadata; inspect the source work or benchmark page.",
            "scale": "Unknown from local metadata.",
            "official_url": "",
            "source": "local extraction",
        }

    def _baseline_catalog_info(self, baseline_name: str) -> dict[str, Any]:
        key = self._normalize_name(baseline_name)
        catalog = {
            "zero shot clip": {
                "description": "Use CLIP directly with text prompts and no task-specific training.",
                "principle": "Measures how far prompt-only pretrained vision-language alignment can go before adaptation.",
                "official_code_url": "https://github.com/openai/CLIP",
                "source_paper_link": "https://arxiv.org/abs/2103.00020",
                "source": "OpenAI CLIP",
            },
            "clip": {
                "description": "Contrastive Language-Image Pre-training model used as the base representation or zero-shot baseline.",
                "principle": "Align image and text embeddings so class names or prompts can act as classifiers.",
                "official_code_url": "https://github.com/openai/CLIP",
                "source_paper_link": "https://arxiv.org/abs/2103.00020",
                "source": "OpenAI CLIP",
            },
            "coop": {
                "description": "Context Optimization baseline for learning continuous prompt vectors for CLIP.",
                "principle": "Keep CLIP frozen and optimize learnable context tokens for few-shot adaptation.",
                "official_code_url": "https://github.com/KaiyangZhou/CoOp",
                "source_paper_link": "https://arxiv.org/abs/2109.01134",
                "source": "CoOp / CoCoOp codebase",
            },
            "cocoop": {
                "description": "Conditional Context Optimization baseline for instance-conditioned prompt adaptation.",
                "principle": "Generate prompt context conditioned on each image to improve transfer to novel classes.",
                "official_code_url": "https://github.com/KaiyangZhou/CoOp",
                "source_paper_link": "https://arxiv.org/abs/2203.05557",
                "source": "CoOp / CoCoOp codebase",
            },
            "tip adapter": {
                "description": "Training-free or lightweight adapter baseline for few-shot CLIP classification.",
                "principle": "Build a cache from few-shot features and blend cache retrieval with CLIP logits.",
                "official_code_url": "https://github.com/gaopengcuhk/Tip-Adapter",
                "source_paper_link": "https://arxiv.org/abs/2111.03930",
                "source": "Tip-Adapter",
            },
            "tpt": {
                "description": "Test-time Prompt Tuning baseline for adapting prompts during inference.",
                "principle": "Update prompt parameters at test time using augmentation consistency or entropy-style objectives.",
                "official_code_url": "https://github.com/azshue/TPT",
                "source_paper_link": "https://arxiv.org/abs/2209.07511",
                "source": "TPT",
            },
            "maple": {
                "description": "Multi-modal Prompt Learning baseline for adapting both vision and language branches of CLIP.",
                "principle": "Learn coupled prompts in multiple modalities so visual and textual adaptations remain aligned.",
                "official_code_url": "https://github.com/muzairkhattak/multimodal-prompt-learning",
                "source_paper_link": "https://arxiv.org/abs/2210.03117",
                "source": "MaPLe",
            },
            "prograd": {
                "description": "Prompt learning baseline that constrains updates with gradient alignment to preserve generalization.",
                "principle": "Avoid prompt updates that conflict with the zero-shot CLIP prior.",
                "official_code_url": "https://github.com/BeierZhu/Prompt-align",
                "source_paper_link": "https://arxiv.org/abs/2205.14865",
                "source": "ProGrad",
            },
            "promptsrc": {
                "description": "Prompt learning baseline with self-regularization for source-free CLIP adaptation.",
                "principle": "Use regularization to preserve useful CLIP priors while adapting prompts.",
                "official_code_url": "https://github.com/muzairkhattak/PromptSRC",
                "source_paper_link": "https://arxiv.org/abs/2307.06948",
                "source": "PromptSRC",
            },
            "kgcoop": {
                "description": "Prompt learning baseline that regularizes learned prompts with knowledge-guided constraints.",
                "principle": "Keep learned context close to meaningful textual knowledge to improve transfer.",
                "official_code_url": "https://github.com/htyao89/KgCoOp",
                "source_paper_link": "https://arxiv.org/abs/2211.15099",
                "source": "KgCoOp",
            },
            "clip adapter": {
                "description": "Adapter baseline that adds lightweight trainable layers on top of frozen CLIP features.",
                "principle": "Preserve the pretrained CLIP encoder and adapt with a small residual module.",
                "official_code_url": "https://github.com/gaopengcuhk/CLIP-Adapter",
                "source_paper_link": "https://arxiv.org/abs/2110.04544",
                "source": "CLIP-Adapter",
            },
            "timesfm mlp": {
                "description": "A simple regression head over TimesFM features.",
                "principle": "Test whether frozen foundation-model time-series features are sufficient before adding fusion complexity.",
                "official_code_url": "https://github.com/google-research/timesfm",
                "source_paper_link": "https://arxiv.org/abs/2310.10688",
                "source": "TimesFM",
            },
            "timesfm transformer": {
                "description": "Transformer fusion or regression stack over TimesFM-derived time-series features.",
                "principle": "Let a lightweight model learn cross-sensor or cross-channel interactions after foundation feature extraction.",
                "official_code_url": "https://github.com/google-research/timesfm",
                "source_paper_link": "https://arxiv.org/abs/2310.10688",
                "source": "TimesFM",
            },
            "nerf": {
                "description": "Neural Radiance Fields baseline for novel-view synthesis and 3D reconstruction.",
                "principle": "Represent scenes as continuous radiance fields optimized from posed images.",
                "official_code_url": "https://github.com/bmild/nerf",
                "source_paper_link": "https://arxiv.org/abs/2003.08934",
                "source": "NeRF",
            },
            "3dgs": {
                "description": "3D Gaussian Splatting baseline for radiance-field style scene reconstruction.",
                "principle": "Represent scenes with optimized 3D Gaussians for efficient rendering.",
                "official_code_url": "https://github.com/graphdeco-inria/gaussian-splatting",
                "source_paper_link": "https://repo-sam.inria.fr/fungraph/3d-gaussian-splatting/",
                "source": "3D Gaussian Splatting",
            },
        }
        for name, info in sorted(catalog.items(), key=lambda pair: len(pair[0]), reverse=True):
            if key == name or name in key:
                return info
        return {
            "description": f"{baseline_name or 'Baseline'} was extracted from local source evidence.",
            "principle": "Use this as a nearest comparison point; curate its exact mechanism and official implementation when available.",
            "official_code_url": "",
            "source": "local extraction",
        }

    def _baseline_performance_summary(self, baselines: list[dict[str, Any]], results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = []
        for result in results[:12]:
            rows.append(
                {
                    "method_name": result.get("method_name", ""),
                    "metric": result.get("metric", ""),
                    "value": result.get("value"),
                    "value_text": result.get("value_text", ""),
                    "unit": result.get("unit", ""),
                    "code_url": result.get("code_url", ""),
                }
            )
        if not rows:
            for baseline in baselines[:8]:
                rows.append(
                    {
                        "method_name": baseline.get("baseline_name", ""),
                        "metric": "not extracted",
                        "value": None,
                        "value_text": "No local result value extracted yet.",
                        "unit": "",
                        "code_url": self._baseline_catalog_info(baseline.get("baseline_name", "")).get("official_code_url", ""),
                    }
                )
        return rows

    def _extract_insight_messages(self, text: str) -> list[str]:
        messages: list[str] = []
        keywords = [
            "show",
            "demonstrate",
            "find",
            "observe",
            "suggest",
            "indicate",
            "improve",
            "outperform",
            "reduce",
            "not effective",
            "fails",
            "under",
            "when",
            "in low",
            "in limited",
            "ablation",
        ]
        for sentence in sentence_split(text):
            lower = sentence.lower()
            if not any(keyword in lower for keyword in keywords):
                continue
            if not any(signal in lower for signal in ["improv", "outperform", "reduce", "fail", "not ", "when ", "under ", "show", "demonstrat", "ablation"]):
                continue
            cleaned = self._strip_fact_prefix(sentence)
            if 45 <= len(cleaned) <= 420:
                messages.append(compact_text(cleaned, 320))
        return self._ordered_unique(messages)[:6]

    def _extract_novelty_points(self, text: str) -> list[str]:
        points: list[str] = []
        patterns = [
            r"(?:we|this work|the paper)\s+(?:propose|introduce|present|develop|design)s?\s+([^.;]{25,260})",
            r"(?:our|the)\s+(?:main\s+)?(?:novelty|contribution|innovation)\s+(?:is|lies in|comes from)\s+([^.;]{25,260})",
            r"(?:novel|new)\s+([^.;]{25,220})",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text or "", flags=re.IGNORECASE):
                phrase = compact_text(match.group(1), 260)
                phrase = re.sub(r"^(a|an|the)\s+", "", phrase, flags=re.IGNORECASE).strip()
                if phrase:
                    points.append(phrase)
        if not points:
            for sentence in sentence_split(text):
                lower = sentence.lower()
                if any(term in lower for term in ["propose", "introduce", "present", "framework", "architecture", "adapter", "module", "mechanism"]):
                    cleaned = self._strip_fact_prefix(sentence)
                    if 45 <= len(cleaned) <= 420:
                        points.append(compact_text(cleaned, 300))
        return self._ordered_unique(points)[:6]

    def _first_matching_sentence(self, text: str, keywords: list[str]) -> str:
        for sentence in sentence_split(text):
            lower = sentence.lower()
            if any(keyword in lower for keyword in keywords):
                return compact_text(sentence, 360)
        sentences = sentence_split(text)
        return compact_text(sentences[0], 360) if sentences else ""

    def _benchmark_signal_terms(self) -> list[str]:
        return [
            "benchmark",
            "dataset",
            "evaluation",
            "evaluate",
            "evaluated",
            "experiment",
            "experiments",
            "baseline",
            "accuracy",
            "acc",
            "rmse",
            "mae",
            "f1",
            "auc",
            "bleu",
            "rouge",
            "pass@",
            "psnr",
            "ssim",
            "map",
            "gpu",
            "latency",
            "flops",
            "imagenet",
            "clip",
            "cmaps",
            "swe-bench",
            "logicbench",
            "logiqa",
            "reclor",
            "folio",
            "proofwriter",
            "prontoqa",
            "aime",
            "math",
            "mmlu",
            "gpqa",
        ]

    def _dataset_terms(self) -> list[str]:
        return [
            "ImageNet",
            "Caltech101",
            "OxfordPets",
            "Food101",
            "DTD",
            "EuroSAT",
            "UCF101",
            "SUN397",
            "CIFAR-10",
            "CIFAR-100",
            "MNIST",
            "Fashion-MNIST",
            "SVHN",
            "STL-10",
            "Tiny ImageNet",
            "FGVCAircraft",
            "StanfordCars",
            "Flowers102",
            "COCO",
            "Pascal VOC",
            "ADE20K",
            "Cityscapes",
            "KITTI",
            "ScanNet",
            "DTU",
            "Tanks and Temples",
            "Mip-NeRF 360",
            "LLFF",
            "ShapeNet",
            "ScanObjectNN",
            "ModelNet40",
            "C-MAPSS",
            "NASA C-MAPSS",
            "PHM08",
            "MIMIC",
            "GSM8K",
            "MATH",
            "AQuA",
            "AQuA-RAT",
            "SVAMP",
            "MultiArith",
            "HumanEval",
            "MBPP",
            "SWE-bench",
            "MMLU",
            "GPQA",
            "AIME",
            "LogicBench",
            "LogiQA",
            "LogiQA2.0",
            "ReClor",
            "FOLIO",
            "ProofWriter",
            "PrOntoQA",
            "ProntoQA",
            "Logical Deduction",
            "StrategyQA",
            "CommonsenseQA",
            "DROP",
            "MuSR",
            "A^3-Bench",
            "HalluScore",
            "ARC",
            "ARC-Challenge",
            "AI2 ARC",
            "HellaSwag",
            "Winogrande",
            "TruthfulQA",
            "SQuAD",
            "GLUE",
            "SuperGLUE",
            "BIG-Bench",
            "BBH",
            "LibriSpeech",
            "WMT",
            "VQA",
            "TextVQA",
            "HotpotQA",
            "Natural Questions",
        ]

    def _metric_terms(self) -> list[str]:
        return [
            "accuracy",
            "top-1 accuracy",
            "base-to-novel gap",
            "RMSE",
            "MAE",
            "F1",
            "AUC",
            "BLEU",
            "ROUGE",
            "pass@1",
            "exact match",
            "EM",
            "multiple-choice accuracy",
            "token cost",
            "accuracy-token frontier",
            "mAP",
            "PSNR",
            "SSIM",
            "LPIPS",
            "Chamfer distance",
            "latency",
            "GPU hours",
            "memory",
        ]

    def _baseline_terms(self) -> list[str]:
        return [
            "zero-shot CLIP",
            "CLIP",
            "CoOp",
            "CoCoOp",
            "Tip-Adapter",
            "TPT",
            "MaPLe",
            "ProGrad",
            "PromptSRC",
            "KgCoOp",
            "CLIP-Adapter",
            "linear probe",
            "ViT^3",
            "TimesFM + MLP",
            "TimesFM + Transformer",
            "LSTM",
            "TCN",
            "Transformer",
            "NeRF",
            "3DGS",
            "RegNeRF",
            "SparseNeRF",
            "pixelNeRF",
            "single-agent",
            "majority vote",
            "self-consistency",
            "chain-of-thought",
            "Chain-of-Thought",
            "CoT",
            "Tree-of-Thought",
            "ToT",
            "Least-to-Most",
            "Program-of-Thought",
            "PoT",
            "ReAct",
            "Reflexion",
            "self-refine",
            "debate",
            "multi-agent debate",
            "RAG",
            "retrieval-augmented generation",
            "nearest published baseline",
            "ablation",
        ]

    def _infer_task_label(self, goal: dict[str, Any], work: dict[str, Any], text: str) -> str:
        if goal.get("target_domain"):
            return compact_text(str(goal["target_domain"]), 80)
        lower = text.lower()
        if "reconstruction" in lower:
            return "3D reconstruction"
        if "rul" in lower or "remaining useful life" in lower:
            return "remaining useful life prediction"
        if "few-shot" in lower or "clip" in lower:
            return "few-shot vision-language adaptation"
        if "reasoning" in lower:
            return "reasoning evaluation"
        return compact_text(work.get("title", "local evaluation"), 80)

    def _infer_split(self, text: str) -> str:
        lower = text.lower()
        if "test split" in lower:
            return "test split"
        if "base-to-novel" in lower:
            return "base-to-novel"
        if "few-shot" in lower:
            return "few-shot split"
        if "held-out" in lower:
            return "held-out"
        return "unspecified"

    def _metric_direction(self, metric: str) -> str:
        lower = metric.lower()
        if any(term in lower for term in ["rmse", "mae", "distance", "latency", "gpu", "memory", "gap", "lpips"]):
            return "lower_is_better"
        if any(term in lower for term in ["accuracy", "f1", "auc", "bleu", "rouge", "pass@", "map", "psnr", "ssim"]):
            return "higher_is_better"
        return "unknown"

    def _baseline_type(self, name: str) -> str:
        lower = name.lower()
        if "ablation" in lower or "without" in lower or "no " in lower:
            return "ablation"
        if "oracle" in lower:
            return "oracle"
        if "nearest" in lower:
            return "nearest_prior"
        return "published"

    def _extract_numeric_results(self, text: str) -> list[tuple[float | None, str, str]]:
        pattern = re.compile(
            r"(?P<label>(?:accuracy|acc|rmse|mae|f1|auc|bleu|rouge|psnr|ssim|map|pass@1|latency|memory|gpu hours?)"
            r"[^.;,\n]{0,40}?)?(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>%|percent|ms|s|hours?|gpu hours?|gb|fps|dB)?",
            re.IGNORECASE,
        )
        results: list[tuple[float | None, str, str]] = []
        for match in pattern.finditer(text or ""):
            start = max(0, match.start() - 80)
            end = min(len(text), match.end() + 80)
            context = compact_text(text[start:end], 220)
            unit = match.group("unit") or ""
            try:
                value: float | None = float(match.group("value"))
            except Exception:
                value = None
            if value is not None and value > 10000:
                continue
            if not self._contains_any(context, self._metric_terms() + ["result", "score", "improve", "outperform"]):
                continue
            results.append((value, context, unit))
        return results

    def _metric_near_result(self, value_text: str, metrics: list[str]) -> str:
        for metric in metrics:
            if metric.lower() in value_text.lower():
                return metric
        for metric in self._metric_terms():
            if metric.lower() in value_text.lower():
                return metric
        return metrics[0] if metrics else "reported metric"

    def _extract_code_url(self, work: dict[str, Any], text: str) -> str:
        url = str(work.get("url_or_doi") or "")
        if "github.com" in url.lower():
            return url
        match = re.search(r"https?://(?:www\.)?github\.com/[^\s)>\]]+", text or "", flags=re.IGNORECASE)
        return match.group(0) if match else ""

    def _estimate_confidence_reason(
        self,
        benchmarks: list[dict[str, Any]],
        results: list[dict[str, Any]],
        feedback_events: list[str],
    ) -> str:
        if results and feedback_events:
            return f"Based on {len(results)} matched result records and {len(feedback_events)} local feedback events."
        if results:
            return f"Based on {len(results)} matched result records, but local feedback is still sparse."
        if benchmarks:
            return f"Based on {len(benchmarks)} matched benchmark records with no structured result history yet."
        return "Evidence is weak because this idea has no matched local benchmark or result records."

    def _status_from_outcome(self, outcome: str) -> str:
        return {
            "supported": "validated",
            "contradicted": "failed",
            "implementation_failed": "implementation_failed",
            "duplicate": "duplicate",
            "inconclusive": "inconclusive",
        }.get(outcome, outcome or "inconclusive")

    def _max_validation_level(self, left: str, right: str) -> str:
        return left if validation_number(left) >= validation_number(right) else right

    def _idea_source_work_ids(self, idea: dict[str, Any], principles: list[dict[str, Any]]) -> list[str]:
        ids: list[str] = []
        for principle in principles:
            ids.extend(principle.get("source_works", []))
        for field in ("source_insights", "source_novelty"):
            for fact in idea.get(field, []):
                if isinstance(fact, dict) and fact.get("work_id"):
                    ids.append(fact["work_id"])
        seen: set[str] = set()
        output = []
        for wid in ids:
            if wid and wid not in seen:
                seen.add(wid)
                output.append(wid)
        return output

    def _assistant_feedback_schema(self) -> dict[str, Any]:
        return {
            "idea_id": "string",
            "outcome_label": "supported|contradicted|inconclusive|duplicate|implementation_failed",
            "metric_delta_observed": "string",
            "runtime_cost": "string",
            "failure_modes": ["string"],
            "strengthened_principles": ["principle_id"],
            "weakened_principles": ["principle_id"],
            "commands_used": ["string"],
            "notes": "string",
        }

    def _render_report_markdown(
        self,
        query: str,
        principles: list[dict[str, Any]],
        ideas: list[dict[str, Any]],
        works: list[dict[str, Any]],
        *,
        library: dict[str, Any],
        language: str,
        model_mode: str,
    ) -> str:
        zh = language == "zh"
        works_by_id = library.get("source_works", {})
        principles_by_id = library.get("principles", {})
        facts = library.get("work_facts", [])
        benchmarks = library.get("benchmark_records", [])
        baselines = library.get("baseline_records", [])
        results = library.get("result_records", [])
        estimates = library.get("estimates", {})
        prompt_plans = library.get("prompt_plans", {})
        lines = [
            "# Principia Report" if not zh else "# Principia 报告",
            "",
            ("**Query**: " if not zh else "**当前 Query**：") + query,
            ("**Model view**: " if not zh else "**模型版本**：") + model_mode,
            "",
            "## Generated Ideas" if not zh else "## Generated Ideas / 生成想法",
        ]
        for idea in ideas:
            view = self._localized(idea, language)
            linked_principles = [principles_by_id.get(pid, {}) for pid in idea.get("source_principles", [])]
            inspiring_work_ids = self._idea_source_work_ids(idea, linked_principles)
            inspiring_works = [works_by_id.get(wid, {}) for wid in inspiring_work_ids if works_by_id.get(wid)]
            estimate = estimates.get(idea.get("result_estimate_id", ""), {})
            plan = prompt_plans.get(idea.get("codex_prompt_plan_id", ""), {})
            insight_sources = [
                f"{fact.get('work_title') or fact.get('work_id')}: {fact.get('text')}"
                for fact in idea.get("source_insights", [])
            ]
            novelty_sources = [
                f"{fact.get('work_title') or fact.get('work_id')}: {fact.get('text')}"
                for fact in idea.get("source_novelty", [])
            ]
            insight_sources = view.get("source_insights") or insight_sources
            novelty_sources = view.get("source_novelty") or novelty_sources
            lines.extend(
                [
                    f"### {view.get('title') or idea.get('title', 'Idea')}",
                    f"- Model: {idea.get('model_name', 'legacy')}",
                    f"- Inspired principles: {', '.join(idea.get('source_principle_names', idea.get('source_principles', [])))}",
                    f"- Independent insights: {'; '.join(insight_sources)}",
                    f"- Independent novelty: {'; '.join(novelty_sources)}",
                    f"- Thesis: {view.get('one_sentence_thesis') or idea.get('one_sentence_thesis', '')}",
                    f"- Expected contribution: {view.get('expected_contribution') or idea.get('expected_contribution', '')}",
                    f"- Novelty claim: {view.get('novelty_claim') or idea.get('novelty_claim', '')}",
                    f"- Prior-art overlap: {'; '.join(view.get('prior_art_overlap') or idea.get('prior_art_overlap', []))}",
                    f"- Why it may work: {'; '.join(view.get('why_it_might_work') or idea.get('why_it_might_work', []))}",
                    f"- Mechanism design: {'; '.join(view.get('mechanism_design') or idea.get('mechanism_design', []))}",
                    f"- Minimal experiment: {idea.get('minimal_experiment', '')}",
                    f"- Validation protocol: {'; '.join(view.get('validation_protocol') or idea.get('validation_protocol', []))}",
                    f"- Similar or inspiring works: {'; '.join(work.get('title', work.get('work_id', '')) for work in inspiring_works) or 'Not linked'}",
                    f"- Baselines: {'; '.join(view.get('baselines') or idea.get('baselines', []))}",
                    f"- Metrics: {'; '.join(view.get('metrics') or idea.get('metrics', []))}",
                    f"- Failure modes: {'; '.join(view.get('failure_modes') or idea.get('failure_modes', []))}",
                    f"- Result estimate: {estimate.get('primary_metric', 'unknown metric')} mean={estimate.get('mean', 'n/a')} range=[{estimate.get('lower_90', 'n/a')}, {estimate.get('upper_90', 'n/a')}], useful-signal={estimate.get('probability_useful_signal', 'n/a')}",
                    f"- Cheapest falsification: {estimate.get('cheapest_falsification', '')}",
                    f"- Prompt plan: {'; '.join(step.get('objective', '') for step in plan.get('prompts', [])[:5])}",
                    "",
                ]
            )
        lines.append("## Principle Atlas" if not zh else "## Principle Atlas / 原理图谱")
        for principle in principles:
            view = self._localized(principle, language)
            lines.extend(
                [
                    f"### {view.get('name') or principle.get('name', 'Principle')}",
                    f"- Model: {principle.get('model_name', 'legacy')}",
                    f"- Source works: {', '.join(principle.get('source_works', []))}",
                    f"- Abstract signature: {view.get('abstract_signature') or principle.get('abstract_signature', '')}",
                    f"- Mechanism: {view.get('mechanism') or principle.get('mechanism', '')}",
                    f"- Problem pressure: {view.get('problem_pressure') or principle.get('problem_pressure', '')}",
                    f"- Insight: {view.get('objective') or principle.get('objective', '')}",
                    f"- Scarce resources: {'; '.join(view.get('scarce_resources') or principle.get('scarce_resources', []))}",
                    f"- Assumptions: {'; '.join(view.get('assumptions') or principle.get('assumptions', []))}",
                    f"- Constraints: {'; '.join(view.get('constraints') or principle.get('constraints', []))}",
                    f"- Invariants: {'; '.join(view.get('invariants') or principle.get('invariants', []))}",
                    f"- Tradeoffs: {'; '.join(view.get('tradeoffs') or principle.get('tradeoffs', []))}",
                    f"- Application: {'; '.join(view.get('transfer_hooks') or principle.get('transfer_hooks', []))}",
                    f"- Feedback loop: {'; '.join(view.get('feedback_loop') or principle.get('feedback_loop', []))}",
                    f"- Requirements: {'; '.join((view.get('scarce_resources') or principle.get('scarce_resources', []))[:3] + (view.get('constraints') or principle.get('constraints', []))[:3])}",
                    f"- Failure modes: {'; '.join(view.get('failure_modes') or principle.get('failure_modes', []))}",
                    f"- Validation notes: {'; '.join(view.get('validation_notes') or principle.get('validation_notes', []))}",
                    "",
                ]
            )
        lines.append("## Source Works" if not zh else "## 相关工作")
        for work in works:
            view = self._localized(work, language)
            work_id = work.get("work_id", "")
            work_facts = [fact for fact in facts if fact.get("work_id") == work_id]
            work_benchmarks = [item for item in benchmarks if item.get("work_id") == work_id]
            work_baselines = [item for item in baselines if item.get("work_id") == work_id]
            work_results = [item for item in results if item.get("work_id") == work_id]
            lines.extend(
                [
                    f"### {work.get('title', work.get('work_id', 'Work'))}",
                    f"- Authors: {', '.join(work.get('authors', []))}",
                    f"- Year/source: {work.get('year', '')} · {work.get('venue_or_source', '')}",
                    f"- URL: {work.get('url_or_doi', '') or 'local'}",
                    f"- Abstract: {view.get('abstract') or work.get('abstract', '')}",
                    f"- Core idea: {'; '.join(fact.get('text', '') for fact in work_facts if fact.get('fact_type') == 'core_idea') or '; '.join((view.get('work_principles') or work.get('work_principles', []))[:2])}",
                    f"- Motivation: {'; '.join(fact.get('text', '') for fact in work_facts if fact.get('fact_type') == 'motivation')}",
                    f"- Insight: {'; '.join((view.get('work_insights') or work.get('work_insights', []))[:3])}",
                    f"- Novelty: {'; '.join((view.get('work_novelty') or work.get('work_novelty', []))[:3])}",
                    f"- Principles: {'; '.join((view.get('work_principles') or work.get('work_principles', []))[:3])}",
                    f"- Benchmarks: {'; '.join('{} / {}'.format(item.get('dataset'), item.get('metric')) for item in work_benchmarks)}",
                    f"- Baselines: {'; '.join(item.get('baseline_name', '') for item in work_baselines)}",
                    f"- Reported results: {'; '.join(item.get('value_text') or str(item.get('value', '')) for item in work_results)}",
                    "",
                ]
            )
        if benchmarks:
            lines.append("## Benchmark And Baseline Evidence" if not zh else "## Benchmark 与 baseline 证据")
            for item in benchmarks[:24]:
                linked_baselines = [baseline for baseline in baselines if baseline.get("benchmark_id") == item.get("benchmark_id")]
                linked_results = [result for result in results if result.get("benchmark_id") == item.get("benchmark_id")]
                lines.extend(
                    [
                        f"### {item.get('dataset', 'Benchmark')} · {item.get('metric', 'metric')}",
                        f"- Task/split: {item.get('task', '')} · {item.get('split', '')}",
                        f"- Metric direction: {item.get('metric_direction', 'unknown')}",
                        f"- Source work: {works_by_id.get(item.get('work_id', ''), {}).get('title', item.get('work_id', ''))}",
                        f"- Baselines: {'; '.join(baseline.get('baseline_name', '') for baseline in linked_baselines)}",
                        f"- Results: {'; '.join(result.get('value_text') or str(result.get('value', '')) for result in linked_results)}",
                        "",
                    ]
                )
        return "\n".join(lines)

    def _localized(self, item: dict[str, Any], language: str) -> dict[str, Any]:
        item = self.repair_language_variants(item)
        variants = item.get("language_variants") or {}
        return variants.get(language) or variants.get("en") or {}

    def _markdown_to_plain_text(self, markdown: str) -> str:
        lines: list[str] = []
        for raw in markdown.splitlines():
            text = raw.replace("**", "").strip()
            if text.startswith("#"):
                level = len(text) - len(text.lstrip("#"))
                text = text[level:].strip()
                if lines and lines[-1]:
                    lines.append("")
                lines.append(text.upper() if level <= 1 else text)
                lines.append("")
            else:
                lines.append(text)
        return "\n".join(lines).strip() + "\n"

    def _markdown_to_system_pdf(self, markdown: str) -> bytes | None:
        cupsfilter = shutil.which("cupsfilter")
        if not cupsfilter:
            return None
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "principia-report.txt"
            source.write_text(self._markdown_to_plain_text(markdown), encoding="utf-8")
            try:
                result = subprocess.run(
                    [cupsfilter, "-m", "application/pdf", str(source)],
                    capture_output=True,
                    timeout=30,
                    check=False,
                )
            except Exception:
                return None
        if result.returncode == 0 and result.stdout.startswith(b"%PDF"):
            return result.stdout
        return None

    def _markdown_to_simple_pdf(self, markdown: str) -> bytes:
        system_pdf = self._markdown_to_system_pdf(markdown)
        if system_pdf:
            return system_pdf
        lines: list[str] = []
        for raw in markdown.splitlines():
            text = raw.replace("#", "").replace("*", "").strip()
            if not text:
                lines.append("")
            else:
                lines.extend(textwrap.wrap(text, width=92) or [""])
        page_height = 792
        margin = 48
        line_height = 13
        pages = [lines[i : i + 52] for i in range(0, len(lines), 52)] or [[]]
        objects: list[bytes] = []
        objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
        kids = " ".join(f"{3 + idx * 2} 0 R" for idx in range(len(pages)))
        objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode("latin-1"))
        for idx, page_lines in enumerate(pages):
            page_obj = 3 + idx * 2
            content_obj = page_obj + 1
            objects.append(
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> /Contents {content_obj} 0 R >>".encode(
                    "latin-1"
                )
            )
            commands = ["BT", "/F1 10 Tf", f"{margin} {page_height - margin} Td"]
            for line_no, line in enumerate(page_lines):
                escaped = line.encode("latin-1", errors="replace").decode("latin-1").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
                if line_no:
                    commands.append(f"0 -{line_height} Td")
                commands.append(f"({escaped}) Tj")
            commands.append("ET")
            stream = "\n".join(commands).encode("latin-1")
            objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1") + stream + b"\nendstream")
        out = bytearray(b"%PDF-1.4\n")
        offsets = [0]
        for idx, obj in enumerate(objects, start=1):
            offsets.append(len(out))
            out.extend(f"{idx} 0 obj\n".encode("latin-1"))
            out.extend(obj)
            out.extend(b"\nendobj\n")
        xref = len(out)
        out.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode("latin-1"))
        for offset in offsets[1:]:
            out.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
        out.extend(f"trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("latin-1"))
        return bytes(out)

    def _emit_progress(
        self,
        progress_callback: Callable[[dict[str, Any]], None] | None,
        stage: str,
        found: int,
        target: int,
        message: str,
    ) -> None:
        if progress_callback:
            progress_callback({"stage": stage, "found": found, "target": target, "message": message})

    def _is_rich_principle(self, principle: dict[str, Any]) -> bool:
        return all(bool(principle.get(field)) for field in RICH_PRINCIPLE_FIELDS)

    def _model_label(self, model_mode: str, offline: bool = False, complexity: float = 0.4) -> str:
        if offline or not self.llm.available():
            return f"offline:{model_mode}"
        try:
            return self.llm.model_label(mode=model_mode, complexity=complexity)
        except Exception:
            return f"unknown:{model_mode}"

    def _attach_principle_metadata(
        self,
        principle: dict[str, Any],
        goal: dict[str, Any],
        model_mode: str,
        offline: bool,
    ) -> dict[str, Any]:
        item = dict(principle)
        model_name = self._model_label(model_mode, offline, goal.get("complexity", 0.4))
        item["base_principle_id"] = item.get("base_principle_id") or item.get("principle_id")
        item["principle_id"] = stable_id(
            "P",
            item.get("base_principle_id", ""),
            goal.get("goal_id", ""),
            model_mode,
            model_name,
        )
        item["model_mode"] = model_mode
        item["model_name"] = model_name
        item["query_kind"] = goal.get("query_kind", "task")
        item["language_variants"] = self._principle_language_variants(item)
        return item

    def _attach_idea_metadata(
        self,
        idea: dict[str, Any],
        goal: dict[str, Any],
        model_mode: str,
        offline: bool,
    ) -> dict[str, Any]:
        item = dict(idea)
        item["model_mode"] = model_mode
        item["model_name"] = self._model_label(model_mode, offline, goal.get("complexity", 0.4))
        item["query_kind"] = goal.get("query_kind", "task")
        item["language_variants"] = self._idea_language_variants(item)
        return item

    def _zh_profile_from_text(self, text: str) -> dict[str, Any]:
        raw_lower = str(text or "").lower().replace("_", " ")
        lower = enrich_query(text).lower().replace("_", " ")
        vision_like = self._has_any(
            lower,
            [
                "few-shot",
                "few shot",
                "test-time training",
                "test time training",
                "test-time adaptation",
                "clip",
                "vision transformer",
                "vision-language",
                "vit",
                "4090",
            ],
        )
        time_series_like = self._has_any(
            lower,
            ["timesfm", "time series", "sensor", "remaining useful life", "degradation", "prognostic"],
        ) or self._has_rul_token(raw_lower) or self._has_rul_token(lower)
        if not vision_like and time_series_like:
            return {
                "work_abstract": "这条记录围绕 TimesFM、跨传感器特征融合与 RUL 预测展开，重点是区分通用时序表征、传感器交互和寿命回归头各自承担的作用。",
                "work_principles": ["先获得稳定的时序表征，再显式建模跨传感器关系，最后用可校准的 RUL 目标约束输出。"],
                "work_insights": ["RUL 误差往往来自传感器漂移、缺失、工况变化和退化阶段差异，而不只是单变量时序预测能力不足。"],
                "work_novelty": ["创新空间在于让 TimesFM 的通用表征与任务特定的融合、校正、可靠性估计机制清晰分工。"],
                "principle_signature": "把通用时序表征、跨传感器交互和寿命回归拆成可单独验证的三个层次。",
                "principle_mechanism": "将 TimesFM 作为冻结或轻量适配的特征抽取器，再用传感器可靠性、退化阶段或残差校正模块控制信息融合。",
                "principle_pressure": "多传感器 RUL 场景中，直接堆叠 Transformer 和回归头容易掩盖误差来源，也容易把工况偏差误当成退化规律。",
                "principle_objective": "让方法贡献能通过消融实验定位：哪些收益来自 TimesFM 表征，哪些来自跨传感器融合，哪些来自回归头或校准机制。",
                "transfer_hooks": [
                    "先建立 TimesFM + 线性/MLP 回归的低成本基线。",
                    "再加入跨传感器融合层，并按传感器、工况、退化阶段分层报告收益。",
                    "用缺失传感器、跨设备和早晚期 RUL 切片测试鲁棒性。",
                ],
                "validation_notes": [
                    "对比 frozen TimesFM、TimesFM + Transformer、残差校正和可靠性门控版本。",
                    "报告 RMSE/MAE、早晚期误差、校准误差、传感器缺失下的性能曲线。",
                    "控制训练预算，避免把额外算力误判为方法创新。",
                ],
                "idea_thesis": "围绕 TimesFM 表征、跨传感器融合和 RUL 回归头的分工，构造一个可消融、可校准、能暴露误差来源的方法变体。",
                "idea_takeaway": "不要把 TimesFM、Transformer 和回归头简单串起来；更有价值的是证明每一层到底解决了哪一种退化预测误差。",
                "idea_reframing": "RUL 预测可以被重写为“通用时序趋势 + 跨传感器残差 + 退化阶段校准”的组合问题。",
                "idea_mechanism": [
                    "冻结或轻量适配 TimesFM，提取每个传感器窗口的时序特征。",
                    "加入跨传感器融合模块，但保留可关闭的可靠性、阶段或残差分支。",
                    "让回归头同时输出 RUL 和不确定性，便于识别高风险预测。",
                ],
                "idea_why": [
                    "这种拆分能把通用表征能力和任务特定误差校正分开观察。",
                    "分层消融能判断新增模块是否真的改善了退化建模，而不是只增加参数量。",
                ],
                "idea_validation": [
                    "使用同一数据划分比较 TimesFM + MLP、TimesFM + Transformer、可靠性门控、残差校正等版本。",
                    "按设备、工况、退化阶段和传感器缺失比例报告指标。",
                    "记录训练时间、显存占用和推理成本。",
                ],
                "metrics": ["RUL RMSE/MAE", "早期与晚期退化阶段误差", "不确定性校准误差", "传感器缺失鲁棒性"],
                "failure_modes": ["TimesFM 表征与工业传感器分布不匹配。", "融合层学习到工况伪相关。", "回归头在早期寿命阶段过度自信。"],
                "baselines": ["TimesFM + MLP", "TimesFM + Transformer", "原始传感器 Transformer", "不带校准或门控的直接回归头"],
            }
        if vision_like:
            return {
                "work_abstract": "这条记录面向资源受限的视觉少样本学习，重点关注 CLIP/ViT 在测试时训练或测试时适应下的准确率、成本和泛化权衡。",
                "work_principles": ["在少样本视觉任务中，只更新最小必要的提示、适配器、归一化或 token 选择模块，并严格记录测试时计算成本。"],
                "work_insights": ["少样本收益如果依赖大量测试时更新，就必须用准确率-成本曲线而不是单点精度来评价。"],
                "work_novelty": ["创新点应落在测试时更新对象、停止准则、token/提示选择机制和可复现实验矩阵上。"],
                "principle_signature": "在 4-8 块 RTX 4090 的预算下，把少样本精度提升改写为准确率、适应成本和语义稳定性的联合优化。",
                "principle_mechanism": "保留 CLIP/ViT 的语义先验，只在测试时轻量更新 prompt、adapter、normalization 或 token selector，并用稳定性信号控制更新步数。",
                "principle_pressure": "少样本视觉方法容易通过额外测试时计算获得表面提升，但在 base-to-novel、跨域数据集或成本受限条件下失效。",
                "principle_objective": "提出的新策略必须明确测评基准、对比基线、数据集、实验代价和贡献边界，而不是只报告一个平均精度。",
                "transfer_hooks": [
                    "固定 ImageNet、Caltech101、OxfordPets、Food101、DTD、EuroSAT、UCF101、SUN397 等数据集矩阵。",
                    "对比 zero-shot CLIP、CoOp、CoCoOp、Tip-Adapter、TPT、linear probe 和最近的测试时适应方法。",
                    "报告每个测试样本或每个 batch 的更新时间、显存和 GPU 小时。",
                ],
                "validation_notes": [
                    "使用 1/2/4/8/16-shot 设置，并尽量包含 base-to-novel 和跨域切片。",
                    "给出 4-8 块 4090 下的预计 wall-clock、显存峰值和可复现实验脚本。",
                    "分别消融更新参数、停止准则、token 选择和数据增强策略。",
                ],
                "idea_thesis": "围绕 CLIP/ViT 的测试时训练，设计一个只更新轻量组件、显式控制成本、并在标准少样本测评基准上验证的新策略。",
                "idea_takeaway": "核心不是再堆一个模块，而是证明测试时更新在哪些样本、哪些 token、哪些参数上值得花算力。",
                "idea_reframing": "少样本测试时训练应被看作准确率、成本和语义稳定性的 Pareto 问题。",
                "idea_mechanism": [
                    "冻结 CLIP/ViT 主干，只更新 prompt、adapter、normalization 或 token selector。",
                    "用预测熵、增强一致性或原型稳定性决定是否继续测试时更新。",
                    "为每个数据集记录更新步数、显存、时间和精度增益。",
                ],
                "idea_why": [
                    "轻量更新降低了 4-8 块 4090 预算下的实验风险。",
                    "稳定性停止准则可以避免测试时训练过拟合少量样本。",
                    "标准测评矩阵能让贡献和已有 CLIP 少样本基线清晰区分。",
                ],
                "idea_validation": [
                    "在 ImageNet、Caltech101、OxfordPets、Food101、DTD、EuroSAT、UCF101、SUN397 上跑 1/2/4/8/16-shot。",
                    "对比 zero-shot CLIP、CoOp、CoCoOp、Tip-Adapter、TPT、linear probe 和 ViT^3 相关设置。",
                    "报告准确率、base-to-novel gap、测试时 FLOPs/GPU hours、显存峰值和失败案例。",
                ],
                "metrics": ["平均准确率", "base-to-novel gap", "每样本测试时更新时间", "GPU 小时", "显存峰值", "校准误差"],
                "failure_modes": ["测试时更新过拟合支持集。", "额外计算掩盖方法本身贡献。", "CLIP 文本语义在更新后漂移。", "只在少数简单数据集上有效。"],
                "baselines": ["zero-shot CLIP", "CoOp", "CoCoOp", "Tip-Adapter", "TPT", "linear probe", "ViT^3-style test-time training"],
            }
        if self._has_any(lower, ["mas", "multi-agent", "agent", "dialect", "scientific discovery", "symbolic", "llm"]):
            return {
                "work_abstract": "这条记录面向 LLM 多智能体推理，关注通信协议、符号压缩、分歧定位和 token 成本之间的关系。",
                "work_principles": ["把 agent 交互从自由对话改造成有协议、有状态、有验收标准的压缩推理过程。"],
                "work_insights": ["多智能体系统的价值不在于说得更多，而在于更快定位能改变结论的关键分歧。"],
                "work_novelty": ["创新点在于把交互语言、角色调度和证据责任变成可度量的机制。"],
                "principle_signature": "用结构化通信和可审计状态压缩降低多智能体推理成本。",
                "principle_mechanism": "让 agent 交换 claim、evidence、crux、confidence 等结构化对象，而不是反复复述自然语言长文本。",
                "principle_pressure": "自由讨论容易产生重复 token、表面共识和不可追踪的推理跳跃。",
                "principle_objective": "提高单位 token 的推理收益，同时保留分歧、证据来源和可验证结论。",
                "transfer_hooks": ["定义机器方言或结构化消息格式。", "记录每轮消息是否改变共享信念状态。", "用固定 token budget 比较准确率。"],
                "validation_notes": ["对比 single-agent、free-form debate 和结构化协议。", "报告准确率、总 token、延迟和错误类型。"],
                "idea_thesis": "构造一个以结构化通信、分歧压缩和 token 收益为核心的 MAS 推理协议。",
                "idea_takeaway": "agent 之间真正该传递的是可验证的推理状态变化，而不是更长的解释。",
                "idea_reframing": "多智能体推理应按每千 token 解决了多少关键分歧来评价。",
                "idea_mechanism": ["定义结构化消息协议。", "让 agent 只在能减少不确定性时发言。", "用审计器检查结论是否可复原。"],
                "idea_why": ["它减少重复上下文。", "它把推理错误定位到具体交互步骤。"],
                "idea_validation": ["在推理 benchmark 上比较 free-form debate 与协议化 MAS。", "记录准确率、token、延迟和分歧解决率。"],
                "metrics": ["固定 token 预算下的准确率", "总 completion tokens", "分歧解决率", "每轮状态变化"],
                "failure_modes": ["协议过于刚性。", "agent 学会不可解释的私有简写。"],
                "baselines": ["single-agent", "free-form debate", "majority vote", "self-consistency"],
            }
        return {
            "work_abstract": "这条记录围绕当前研究问题抽取可复用机制、关键假设、验证约束和潜在失败模式。",
            "work_principles": ["把来源工作的机制转化为可观察、可消融、可失败的方法约束。"],
            "work_insights": ["有价值的 insight 应当改变方法设计或实验设计，而不只是复述论文贡献。"],
            "work_novelty": ["创新点需要通过最接近的 baseline 和公平成本核算来确认。"],
            "principle_signature": "从相关工作中抽取可迁移的机制约束，并绑定到明确的验证路径。",
            "principle_mechanism": "把核心假设、稀缺资源、方法模块和评价切片显式对应起来。",
            "principle_pressure": "新想法容易在 novelty、可实现性和验证成本之间失衡。",
            "principle_objective": "让候选方法先证明关键机制成立，再扩大实验规模。",
            "transfer_hooks": ["把 principle 写成一个可关闭的模块。", "为该模块设计公平 baseline 和消融。", "记录失败案例并更新 principle 置信度。"],
            "validation_notes": ["先做小规模 smoke test。", "再做分层对照和消融。", "避免把额外算力误判为方法收益。"],
            "idea_thesis": "构造一个围绕关键机制的小型方法变体，并用最小实验检验它是否真的改变了目标问题。",
            "idea_takeaway": "好的 demo idea 应该让关键机制、预期收益和失败条件都能被快速观察。",
            "idea_reframing": "先验证机制是否值得继续投入，而不是先追求完整复杂系统。",
            "idea_mechanism": ["把核心 principle 转成可替换模块。", "设计最小公平 baseline。", "记录正向、负向和失败样例。"],
            "idea_why": ["它把抽象 principle 变成可运行实验。", "它能在低成本下给出是否继续投入的信号。"],
            "idea_validation": ["运行 smoke test。", "做小规模分层对照。", "输出失败模式和下一步更新建议。"],
            "metrics": ["主任务指标", "运行成本", "消融增益", "失败案例比例"],
            "failure_modes": ["baseline 已经包含类似机制。", "小规模数据无法暴露真实瓶颈。"],
            "baselines": ["最接近的公开 baseline", "不含新增模块的直接版本"],
        }

    def _work_language_variants(self, work: dict[str, Any]) -> dict[str, Any]:
        title = work.get("title", "Work")
        abstract = work.get("abstract", "")
        principles = work.get("work_principles", [])
        insights = work.get("work_insights", [])
        novelty = work.get("work_novelty", [])
        zh = self._zh_profile_from_text(self._material_text(work))
        return {
            "en": {
                "title": title,
                "abstract": abstract,
                "work_principles": principles,
                "work_insights": insights,
                "work_novelty": novelty,
            },
            "zh": {
                "title": title,
                "abstract": zh["work_abstract"],
                "work_principles": zh["work_principles"],
                "work_insights": zh["work_insights"],
                "work_novelty": zh["work_novelty"],
            },
        }

    def _principle_language_variants(self, principle: dict[str, Any]) -> dict[str, Any]:
        name = principle.get("name", "Principle")
        mechanism = principle.get("mechanism", "")
        pressure = principle.get("problem_pressure", "")
        objective = principle.get("objective", "")
        zh = self._zh_profile_from_text(self._material_text(principle))
        return {
            "en": {
                "name": name,
                "abstract_signature": principle.get("abstract_signature", ""),
                "mechanism": mechanism,
                "problem_pressure": pressure,
                "objective": objective,
                "transfer_hooks": principle.get("transfer_hooks", []),
                "validation_notes": principle.get("validation_notes", []),
                "scarce_resources": principle.get("scarce_resources", []),
                "constraints": principle.get("constraints", []),
                "invariants": principle.get("invariants", []),
                "tradeoffs": principle.get("tradeoffs", []),
                "failure_modes": principle.get("failure_modes", []),
            },
            "zh": {
                "name": f"{name}",
                "abstract_signature": zh["principle_signature"],
                "mechanism": zh["principle_mechanism"],
                "problem_pressure": zh["principle_pressure"],
                "objective": zh["principle_objective"],
                "transfer_hooks": zh["transfer_hooks"],
                "validation_notes": zh["validation_notes"],
                "scarce_resources": zh["work_principles"] + zh["metrics"][:1],
                "constraints": zh["validation_notes"][:2],
                "invariants": zh["transfer_hooks"][:2],
                "tradeoffs": zh["metrics"][:3],
                "failure_modes": zh["failure_modes"],
            },
        }

    def _idea_language_variants(self, idea: dict[str, Any]) -> dict[str, Any]:
        title = idea.get("title", "Idea")
        thesis = idea.get("one_sentence_thesis", "")
        insight = idea.get("insight", "")
        zh = self._zh_profile_from_text(self._material_text(idea))
        return {
            "en": {
                "title": title,
                "one_sentence_thesis": thesis,
                "insight": insight,
                "mechanism_design": idea.get("mechanism_design", []),
                "why_it_might_work": idea.get("why_it_might_work", []),
                "validation_protocol": idea.get("validation_protocol", []),
                "conceptual_takeaway": idea.get("conceptual_takeaway", ""),
                "sharp_reframing": idea.get("sharp_reframing", ""),
                "source_insights": [
                    f"{fact.get('work_title') or fact.get('work_id')}: {fact.get('text', '')}"
                    for fact in idea.get("source_insights", [])
                ],
                "source_novelty": [
                    f"{fact.get('work_title') or fact.get('work_id')}: {fact.get('text', '')}"
                    for fact in idea.get("source_novelty", [])
                ],
                "metrics": idea.get("metrics", []),
                "failure_modes": idea.get("failure_modes", []),
                "baselines": idea.get("baselines", []),
            },
            "zh": {
                "title": title,
                "one_sentence_thesis": zh["idea_thesis"],
                "insight": zh["idea_takeaway"],
                "conceptual_takeaway": zh["idea_takeaway"],
                "sharp_reframing": zh["idea_reframing"],
                "mechanism_design": zh["idea_mechanism"],
                "why_it_might_work": zh["idea_why"],
                "validation_protocol": zh["idea_validation"],
                "source_insights": zh["work_insights"],
                "source_novelty": zh["work_novelty"],
                "metrics": zh["metrics"],
                "failure_modes": zh["failure_modes"],
                "baselines": zh["baselines"],
            },
        }

    def _translation_model_mode(self, model_mode: str) -> str:
        settings = getattr(self.llm, "settings", None)
        if settings and getattr(settings, "api_key", ""):
            return "qwen_122b"
        if settings and getattr(settings, "openai_api_key", ""):
            return model_mode if str(model_mode).startswith("openai_") else "openai_gpt55"
        return model_mode

    def _ensure_chinese_language_variants(
        self,
        goal: dict[str, Any],
        works: list[dict[str, Any]],
        principles: list[dict[str, Any]],
        ideas: list[dict[str, Any]],
        *,
        offline: bool,
        model_mode: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        works = [self._with_default_work_variants(work) for work in works]
        principles = [self._with_default_principle_variants(principle) for principle in principles]
        ideas = [self._with_default_idea_variants(idea) for idea in ideas]
        if offline or not self.llm.available():
            return works, principles, ideas
        try:
            payload = {
                "goal": {
                    "raw_query": goal.get("raw_query", ""),
                    "target_domain": goal.get("target_domain", ""),
                },
                "works": [
                    {
                        "work_id": work["work_id"],
                        "title": work.get("title", ""),
                        "abstract": compact_text(work.get("abstract", ""), 420),
                        "work_principles": [compact_text(item, 220) for item in work.get("work_principles", [])[:3]],
                        "work_insights": [compact_text(item, 220) for item in work.get("work_insights", [])[:3]],
                        "work_novelty": [compact_text(item, 220) for item in work.get("work_novelty", [])[:3]],
                    }
                    for work in works[:12]
                ],
                "principles": [
                    {
                        "principle_id": principle["principle_id"],
                        "name": principle.get("name", ""),
                        "abstract_signature": compact_text(principle.get("abstract_signature", ""), 220),
                        "mechanism": compact_text(principle.get("mechanism", ""), 320),
                        "problem_pressure": compact_text(principle.get("problem_pressure", ""), 240),
                        "objective": compact_text(principle.get("objective", ""), 240),
                        "transfer_hooks": [compact_text(item, 180) for item in principle.get("transfer_hooks", [])[:4]],
                        "validation_notes": [compact_text(item, 180) for item in principle.get("validation_notes", [])[:4]],
                        "scarce_resources": [compact_text(item, 140) for item in principle.get("scarce_resources", [])[:4]],
                        "constraints": [compact_text(item, 140) for item in principle.get("constraints", [])[:4]],
                        "invariants": [compact_text(item, 140) for item in principle.get("invariants", [])[:4]],
                        "tradeoffs": [compact_text(item, 160) for item in principle.get("tradeoffs", [])[:4]],
                        "failure_modes": [compact_text(item, 160) for item in principle.get("failure_modes", [])[:4]],
                    }
                    for principle in principles[:24]
                ],
                "ideas": [
                    {
                        "idea_id": idea["idea_id"],
                        "title": idea.get("title", ""),
                        "one_sentence_thesis": compact_text(idea.get("one_sentence_thesis", ""), 360),
                        "conceptual_takeaway": compact_text(idea.get("conceptual_takeaway", ""), 280),
                        "sharp_reframing": compact_text(idea.get("sharp_reframing", ""), 280),
                        "insight": compact_text(idea.get("insight", ""), 320),
                        "novelty_claim": compact_text(idea.get("novelty_claim", ""), 280),
                        "expected_contribution": compact_text(idea.get("expected_contribution", ""), 280),
                        "mechanism_design": [compact_text(item, 220) for item in idea.get("mechanism_design", [])[:5]],
                        "why_it_might_work": [compact_text(item, 220) for item in idea.get("why_it_might_work", [])[:4]],
                        "validation_protocol": [compact_text(item, 220) for item in idea.get("validation_protocol", [])[:4]],
                        "source_insights": [
                            compact_text(f"{fact.get('work_title') or fact.get('work_id')}: {fact.get('text', '')}", 260)
                            for fact in idea.get("source_insights", [])[:4]
                        ],
                        "source_novelty": [
                            compact_text(f"{fact.get('work_title') or fact.get('work_id')}: {fact.get('text', '')}", 260)
                            for fact in idea.get("source_novelty", [])[:4]
                        ],
                        "metrics": [compact_text(item, 140) for item in idea.get("metrics", [])[:5]],
                        "failure_modes": [compact_text(item, 180) for item in idea.get("failure_modes", [])[:5]],
                        "baselines": [compact_text(item, 160) for item in idea.get("baselines", [])[:4]],
                    }
                    for idea in ideas[:16]
                ],
            }
            data = self.llm.chat_json(
                "You are Principia's bilingual research editor. Translate English research records into polished Chinese.",
                (
                    "Translate the user-facing content into standard, idiomatic academic Chinese. Return strict JSON with keys "
                    "works, principles, ideas. Preserve all IDs exactly. Keep paper titles, method names, model names, acronyms, "
                    "and specialist terms in their original English when that is the normal academic usage, for example TimesFM, "
                    "RUL, LLM, MAS, Transformer, NeRF, 3D Gaussian Splatting, MDL. Do not translate URLs or IDs. Do not add new "
                    "scientific claims. Do not wrap English sentences with Chinese labels; actually translate the substance. "
                    "Avoid repeated labels such as 'Novelty: 创新点'. Use concise, natural Chinese.\n\n"
                    "Expected output shape:\n"
                    "{\"works\":[{\"work_id\":\"...\",\"zh\":{\"title\":\"same title unless a Chinese title already exists\","
                    "\"abstract\":\"...\",\"work_principles\":[\"...\"],\"work_insights\":[\"...\"],\"work_novelty\":[\"...\"]}}],"
                    "\"principles\":[{\"principle_id\":\"...\",\"zh\":{\"name\":\"...\",\"abstract_signature\":\"...\","
                    "\"mechanism\":\"...\",\"problem_pressure\":\"...\",\"objective\":\"...\",\"transfer_hooks\":[\"...\"],"
                    "\"validation_notes\":[\"...\"],\"scarce_resources\":[\"...\"],\"constraints\":[\"...\"],"
                    "\"invariants\":[\"...\"],\"tradeoffs\":[\"...\"],\"failure_modes\":[\"...\"]}}],"
                    "\"ideas\":[{\"idea_id\":\"...\",\"zh\":{\"title\":\"same title unless a Chinese title is natural\","
                    "\"one_sentence_thesis\":\"...\",\"conceptual_takeaway\":\"...\",\"sharp_reframing\":\"...\",\"insight\":\"...\","
                    "\"mechanism_design\":[\"...\"],\"why_it_might_work\":[\"...\"],\"validation_protocol\":[\"...\"],"
                    "\"source_insights\":[\"...\"],\"source_novelty\":[\"...\"],\"metrics\":[\"...\"],"
                    "\"failure_modes\":[\"...\"],\"baselines\":[\"...\"]}}]}\n\n"
                    f"Records to translate: {payload}"
                ),
                complexity=max(float(goal.get("complexity", 0.5)), 0.55),
                mode=self._translation_model_mode(model_mode),
                max_tokens=7600,
                temperature=0.05,
            )
            self._apply_chinese_translations(works, principles, ideas, data)
        except Exception:
            return works, principles, ideas
        return works, principles, ideas

    def _with_default_work_variants(self, work: dict[str, Any]) -> dict[str, Any]:
        item = dict(work)
        variants = dict(item.get("language_variants") or {})
        defaults = self._work_language_variants(item)
        variants.setdefault("en", defaults["en"])
        if not self._is_usable_chinese_variant(variants.get("zh", {})):
            variants["zh"] = defaults["zh"]
        item["language_variants"] = variants
        return item

    def _with_default_principle_variants(self, principle: dict[str, Any]) -> dict[str, Any]:
        item = dict(principle)
        variants = dict(item.get("language_variants") or {})
        defaults = self._principle_language_variants(item)
        variants.setdefault("en", defaults["en"])
        if not self._is_usable_chinese_variant(variants.get("zh", {})):
            variants["zh"] = defaults["zh"]
        item["language_variants"] = variants
        return item

    def _with_default_idea_variants(self, idea: dict[str, Any]) -> dict[str, Any]:
        item = dict(idea)
        variants = dict(item.get("language_variants") or {})
        defaults = self._idea_language_variants(item)
        variants.setdefault("en", defaults["en"])
        if not self._is_usable_chinese_variant(variants.get("zh", {})):
            variants["zh"] = defaults["zh"]
        item["language_variants"] = variants
        return item

    def repair_language_variants(self, item: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(item, dict):
            return item
        if item.get("principle_id"):
            return self._with_default_principle_variants(item)
        if item.get("idea_id"):
            return self._with_default_idea_variants(item)
        if item.get("work_id"):
            return self._with_default_work_variants(item)
        return item

    def repair_language_variants_many(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [self.repair_language_variants(item) for item in items]

    def _apply_chinese_translations(
        self,
        works: list[dict[str, Any]],
        principles: list[dict[str, Any]],
        ideas: list[dict[str, Any]],
        data: dict[str, Any],
    ) -> None:
        work_map = {item["work_id"]: item for item in works}
        principle_map = {item["principle_id"]: item for item in principles}
        idea_map = {item["idea_id"]: item for item in ideas}
        for raw in data.get("works", []) or []:
            if not isinstance(raw, dict):
                continue
            item = work_map.get(str(raw.get("work_id", "")))
            zh = raw.get("zh") if isinstance(raw.get("zh"), dict) else {}
            if item and zh:
                cleaned = self._clean_translation_variant(zh)
                if self._is_usable_chinese_variant(cleaned):
                    item.setdefault("language_variants", {}).setdefault("en", self._work_language_variants(item)["en"])
                    item["language_variants"]["zh"] = cleaned
        for raw in data.get("principles", []) or []:
            if not isinstance(raw, dict):
                continue
            item = principle_map.get(str(raw.get("principle_id", "")))
            zh = raw.get("zh") if isinstance(raw.get("zh"), dict) else {}
            if item and zh:
                cleaned = self._clean_translation_variant(zh)
                if self._is_usable_chinese_variant(cleaned):
                    item.setdefault("language_variants", {}).setdefault("en", self._principle_language_variants(item)["en"])
                    item["language_variants"]["zh"] = cleaned
        for raw in data.get("ideas", []) or []:
            if not isinstance(raw, dict):
                continue
            item = idea_map.get(str(raw.get("idea_id", "")))
            zh = raw.get("zh") if isinstance(raw.get("zh"), dict) else {}
            if item and zh:
                cleaned = self._clean_translation_variant(zh)
                if self._is_usable_chinese_variant(cleaned):
                    item.setdefault("language_variants", {}).setdefault("en", self._idea_language_variants(item)["en"])
                    item["language_variants"]["zh"] = cleaned

    def _clean_translation_variant(self, variant: dict[str, Any]) -> dict[str, Any]:
        cleaned: dict[str, Any] = {}
        for key, value in variant.items():
            if isinstance(value, list):
                cleaned[key] = [compact_text(str(item), 600) for item in value if str(item).strip()]
            elif value is not None:
                cleaned[key] = compact_text(str(value), 1000)
        return cleaned

    def _flatten_variant_text(self, value: Any) -> str:
        if isinstance(value, dict):
            return " ".join(self._flatten_variant_text(item) for item in value.values())
        if isinstance(value, list):
            return " ".join(self._flatten_variant_text(item) for item in value)
        return str(value or "")

    def _is_usable_chinese_variant(self, variant: dict[str, Any]) -> bool:
        text = self._flatten_variant_text(variant)
        if not text.strip():
            return False
        lowered = text.lower()
        forbidden = [
            "this work",
            "this principle",
            "this idea",
            "allocate scarce resources",
            "push toward frontier-level",
            "cheap falsification path",
            "falsification-gated",
            "evaluator-first",
            "staged mechanism",
        ]
        if any(phrase in lowered for phrase in forbidden):
            return False
        cjk_count = len(re.findall(r"[\u4e00-\u9fff]", text))
        latin_words = re.findall(r"[A-Za-z][A-Za-z0-9\-\^\.]{2,}", text)
        allowed_terms = {
            "timesfm",
            "rul",
            "llm",
            "mas",
            "clip",
            "vit",
            "ttt",
            "mdL".lower(),
            "nerf",
            "gaussian",
            "transformer",
            "imagenet",
            "caltech101",
            "oxfordpets",
            "food101",
            "dtd",
            "eurosat",
            "ucf101",
            "sun397",
            "coop",
            "cocoop",
            "tip-adapter",
            "tpt",
            "zero-shot",
            "few-shot",
            "base-to-novel",
            "test-time",
            "linear",
            "probe",
            "rtx",
            "gpu",
        }
        suspicious_chars = 0
        for word in latin_words:
            normalized = word.lower().strip(".,;:()[]{}")
            if normalized in allowed_terms:
                continue
            if normalized.isupper() or any(ch.isdigit() for ch in normalized):
                continue
            suspicious_chars += len(word)
        return cjk_count >= 12 and suspicious_chars <= max(90, int(cjk_count * 0.9))

    def _enrich_work_record(self, goal: dict[str, Any], work: dict[str, Any]) -> dict[str, Any]:
        item = dict(work)
        if item.get("work_insights") and item.get("work_novelty") and item.get("work_principles"):
            item = self._with_default_work_variants(item)
            return item
        sentences = sentence_split(item.get("abstract", ""))
        title = item.get("title", "this work")
        mechanism = self._pick_sentence(
            sentences,
            ["propose", "introduce", "present", "framework", "method", "learn", "optimize", "regularization"],
            sentences[0] if sentences else f"{title} proposes a method relevant to {goal.get('target_domain', 'the target domain')}.",
        )
        result = self._pick_sentence(
            sentences,
            ["show", "demonstrate", "achieve", "outperform", "improve", "robust", "reduce"],
            sentences[1] if len(sentences) > 1 else mechanism,
        )
        pressure = self._pick_sentence(
            sentences,
            ["challenge", "limited", "sparse", "uncertain", "insufficient", "efficient", "cost"],
            sentences[0] if sentences else mechanism,
        )
        item["work_principles"] = item.get("work_principles") or [
            compact_text(f"General principle: turn the work's pressure ({pressure}) into an explicit mechanism constraint.", 260),
            compact_text(f"Reusable mechanism: {mechanism}", 260),
        ]
        item["work_insights"] = item.get("work_insights") or [
            *(self._extract_insight_messages(" ".join([item.get("title", ""), item.get("abstract", "")]))[:2]),
            compact_text(f"Takeaway: {result}", 260),
        ]
        item["work_novelty"] = item.get("work_novelty") or [
            *(self._extract_novelty_points(" ".join([item.get("title", ""), item.get("abstract", "")]))[:2]),
            compact_text(f"Concrete innovation: {mechanism}", 260),
        ]
        item = self._with_default_work_variants(item)
        return item

    def _work_needs_refresh(self, remote_work: dict[str, Any], local_work: dict[str, Any] | None = None) -> bool:
        wid = remote_work.get("work_id", "")
        local = local_work if local_work is not None else (self.store.get_item("source_works", wid) if wid else None)
        if not local:
            return True
        remote_stamp = str(remote_work.get("source_updated_at") or remote_work.get("updated_at") or "")
        if not remote_stamp:
            return False
        if not local.get("source_updated_at"):
            return True
        local_stamp = str(local.get("source_updated_at") or local.get("updated_at") or local.get("created_at") or "")
        return remote_stamp > local_stamp

    def _work_has_rich_principles(self, work_id: str, *, model_mode: str = "auto") -> bool:
        if not work_id:
            return False
        return work_id in self._rich_principle_work_ids(model_mode=model_mode)

    def _rich_principle_work_ids(self, *, model_mode: str = "auto") -> set[str]:
        data = self.store.snapshot(limit_per_bucket=None)
        work_ids: set[str] = set()
        for principle in data.get("principles", {}).values():
            if model_mode != "auto" and principle.get("model_mode") != model_mode:
                continue
            if self._is_rich_principle(principle):
                work_ids.update(principle.get("source_works") or [])
        return work_ids

    def _dedupe_works(self, works: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        for work in works:
            wid = work.get("work_id")
            if wid and wid not in seen:
                seen.add(wid)
                result.append(work)
        return result

    def _dedupe_principles(self, principles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        for principle in principles:
            pid = principle.get("principle_id")
            if pid and pid not in seen:
                seen.add(pid)
                result.append(principle)
        return result

    def _filter_model_version(self, items: list[dict[str, Any]], model_mode: str) -> list[dict[str, Any]]:
        if model_mode == "auto":
            return items
        return [item for item in items if item.get("model_mode") == model_mode]

    def _principle_search_k(self, top_k: int, model_mode: str) -> int:
        if model_mode == "auto":
            return top_k
        return max(top_k * 12, 100)

    def _model_perspective(self, model_mode: str) -> dict[str, str]:
        profiles = {
            "efficient": {
                "prefix": "Efficient",
                "angle": "Prioritize the smallest mechanism that can be validated quickly.",
            },
            "qwen_35b": {
                "prefix": "MoE-Efficient",
                "angle": "Favor modular decomposition and low-cost ablation paths.",
            },
            "strong": {
                "prefix": "DeepSeek-Strong",
                "angle": "Stress-test assumptions aggressively before adding method complexity.",
            },
            "deepseek_pro": {
                "prefix": "DeepSeek-Pro",
                "angle": "Search for a sharper mechanism and an adversarial validation split.",
            },
            "kimi": {
                "prefix": "Long-Context",
                "angle": "Use broader literature lineage to preserve useful constraints across sources.",
            },
            "qwen_122b": {
                "prefix": "High-Capacity",
                "angle": "Combine multiple mechanisms while keeping each contribution separately falsifiable.",
            },
            "glm": {
                "prefix": "GLM-Agentic",
                "angle": "Make the idea operational by turning insight into explicit research actions.",
            },
            "openai_gpt5_pro": {
                "prefix": "GPT-5-Pro",
                "angle": "Optimize for research-grade mechanism clarity and a tight validation contract.",
            },
            "openai_gpt52_pro": {
                "prefix": "GPT-5.2-Pro",
                "angle": "Prefer high-signal ideas with clear causal mechanisms and honest uncertainty.",
            },
            "openai_gpt55": {
                "prefix": "GPT-5.5",
                "angle": "Prefer a precise mechanism with explicit benchmarks, cost accounting, and a decisive first experiment.",
            },
        }
        return profiles.get(model_mode, {"prefix": "", "angle": ""})

    def _works_for_principles(self, principles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        data = self.store.snapshot(limit_per_bucket=None)
        works = data.get("source_works", {})
        result: list[dict[str, Any]] = []
        for principle in principles:
            for wid in principle.get("source_works", []):
                work = works.get(wid)
                if work:
                    result.append(work)
        return self._dedupe_works(result)

    def _attach_similar_idea_ids(self, ideas: list[dict[str, Any]]) -> None:
        existing = self.store.snapshot(limit_per_bucket=None).get("ideas", {})
        for idea in ideas:
            source = set(idea.get("source_principles", []))
            if not source:
                idea["similar_idea_ids"] = []
                continue
            scored: list[tuple[int, str]] = []
            for other_id, other in existing.items():
                if other_id == idea.get("idea_id"):
                    continue
                overlap = len(source & set(other.get("source_principles", [])))
                if overlap:
                    scored.append((overlap, other_id))
            scored.sort(reverse=True)
            idea["similar_idea_ids"] = [idea_id for _, idea_id in scored[:5]]

    def _work_fact_nodes(self, work: dict[str, Any]) -> list[dict[str, Any]]:
        facts: list[dict[str, Any]] = []
        for fact_type, field in [("novelty", "work_novelty"), ("insight", "work_insights")]:
            values = [item for item in work.get(field, []) if item]
            if values:
                facts.append(
                    {
                        "id": stable_id(fact_type.upper()[0], work.get("work_id", ""), fact_type),
                        "type": fact_type,
                        "label": values[0],
                        "work_id": work.get("work_id", ""),
                    }
                )
        return facts

    def _append_idea_fact_lineage(
        self,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, str]],
        idea: dict[str, Any],
        works: dict[str, dict[str, Any]],
    ) -> None:
        for field in ["source_insights", "source_novelty"]:
            for fact in idea.get(field, []) or []:
                fact_id = fact.get("fact_id") or stable_id("F", idea.get("idea_id", ""), fact.get("text", ""))
                fact_type = fact.get("type") or ("insight" if field == "source_insights" else "novelty")
                work_id = fact.get("work_id", "")
                work = works.get(work_id)
                if work:
                    nodes.append(
                        {
                            "id": work_id,
                            "type": "work",
                            "label": work.get("title", fact.get("work_title", work_id)),
                            "validation": work.get("validation_level", "L0"),
                        }
                    )
                    edges.append({"source": work_id, "target": fact_id, "label": fact_type})
                nodes.append(
                    {
                        "id": fact_id,
                        "type": fact_type,
                        "label": fact.get("text", fact_id),
                        "work_id": work_id,
                    }
                )
                edges.append({"source": fact_id, "target": idea["idea_id"], "label": "inspires"})

    def build_graph(
        self,
        *,
        query: str = "",
        idea_ids: list[str] | None = None,
        top_k: int = 10,
        model_mode: str = "auto",
    ) -> dict[str, Any]:
        data = self.store.read()
        ideas = data.get("ideas", {})
        principles = data.get("principles", {})
        relations = data.get("principle_relations", {})
        works = data.get("source_works", {})
        if idea_ids:
            selected_ideas = [ideas[iid] for iid in idea_ids or [] if iid in ideas]
        else:
            idea_pool = list(ideas.values())
            if model_mode != "auto":
                idea_pool = [idea for idea in idea_pool if idea.get("model_mode") == model_mode]
            selected_ideas = idea_pool[-top_k:]
        selected_principles = {pid for idea in selected_ideas for pid in idea.get("source_principles", [])}
        if query and not idea_ids:
            for principle in self.store.search_principles(
                query,
                top_k=self._principle_search_k(top_k, model_mode),
                min_validation="L0",
            ):
                if model_mode != "auto" and principle.get("model_mode") != model_mode:
                    continue
                selected_principles.add(principle["principle_id"])
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, str]] = []
        for pid in selected_principles:
            principle = principles.get(pid)
            if not principle:
                continue
            nodes.append(
                {
                    "id": pid,
                    "type": "principle",
                    "label": principle.get("name", pid),
                    "confidence": principle.get("confidence_score", 0),
                    "validation": principle.get("validation_level", "L0"),
                }
            )
            for wid in principle.get("source_works", [])[:2]:
                work = works.get(wid)
                if work:
                    work = self._enrich_work_record({"target_domain": query or "current query"}, work)
                    nodes.append(
                        {
                            "id": wid,
                            "type": "work",
                            "label": work.get("title", wid),
                            "validation": work.get("validation_level", "L0"),
                        }
                    )
                    for fact in self._work_fact_nodes(work):
                        nodes.append(fact)
                        edges.append({"source": wid, "target": fact["id"], "label": fact["type"]})
                        edges.append({"source": fact["id"], "target": pid, "label": "informs"})
                    edges.append({"source": wid, "target": pid, "label": "supports"})
        for idea in selected_ideas:
            nodes.append({"id": idea["idea_id"], "type": "idea", "label": idea.get("title", "Idea")})
            self._append_idea_fact_lineage(nodes, edges, idea, works)
            for pid in idea.get("source_principles", []):
                if pid in selected_principles:
                    edges.append({"source": pid, "target": idea["idea_id"], "label": "derived_from"})
        for relation in relations.values():
            source = relation.get("source_principle_id")
            target = relation.get("target_principle_id")
            if source in selected_principles and target in selected_principles:
                edges.append(
                    {
                        "source": source,
                        "target": target,
                        "label": relation.get("relation_type", "related_to"),
                    }
                )
        unique_nodes = {node["id"]: node for node in nodes}
        return {"nodes": list(unique_nodes.values()), "edges": edges}

    def _build_transient_graph(
        self,
        works: list[dict[str, Any]],
        principles: list[dict[str, Any]],
        ideas: list[dict[str, Any]],
        relations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, str]] = []
        work_map = {work["work_id"]: work for work in works}
        principle_ids = {principle["principle_id"] for principle in principles}
        for principle in principles:
            nodes.append(
                {
                    "id": principle["principle_id"],
                    "type": "principle",
                    "label": principle.get("name", principle["principle_id"]),
                    "confidence": principle.get("confidence_score", 0),
                    "validation": principle.get("validation_level", "L0"),
                }
            )
            for wid in principle.get("source_works", [])[:2]:
                work = work_map.get(wid)
                if not work:
                    continue
                nodes.append({"id": wid, "type": "work", "label": work.get("title", wid)})
                for fact in self._work_fact_nodes(work):
                    nodes.append(fact)
                    edges.append({"source": wid, "target": fact["id"], "label": fact["type"]})
                    edges.append({"source": fact["id"], "target": principle["principle_id"], "label": "informs"})
                edges.append({"source": wid, "target": principle["principle_id"], "label": "supports"})
        for idea in ideas:
            nodes.append({"id": idea["idea_id"], "type": "idea", "label": idea.get("title", "Idea")})
            self._append_idea_fact_lineage(nodes, edges, idea, work_map)
            for pid in idea.get("source_principles", []):
                if pid in principle_ids:
                    edges.append({"source": pid, "target": idea["idea_id"], "label": "derived_from"})
        for relation in relations:
            source = relation.get("source_principle_id")
            target = relation.get("target_principle_id")
            if source in principle_ids and target in principle_ids:
                edges.append({"source": source, "target": target, "label": relation.get("relation_type", "related_to")})
        unique_nodes = {node["id"]: node for node in nodes}
        return {"nodes": list(unique_nodes.values()), "edges": edges}

    def _collect_works(
        self,
        goal: dict[str, Any],
        max_works: int,
        offline: bool,
        *,
        exclude_work_ids: set[str] | None = None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
        progress_found_offset: int = 0,
        progress_target: int | None = None,
    ) -> list[dict[str, Any]]:
        exclude_work_ids = exclude_work_ids or set()
        target = progress_target or max_works
        if offline:
            works = self._filter_domain_compatible_works(
                goal,
                [work for work in fallback_seed_work(goal["raw_query"]) if work["work_id"] not in exclude_work_ids],
            )[:max_works]
            self._emit_progress(
                progress_callback,
                "offline_seed",
                progress_found_offset + len(works),
                target,
                f"Loaded {len(works)} offline seed works.",
            )
            return works
        searches = []
        for search in [goal["raw_query"], " ".join(goal.get("search_terms", [])[:6])]:
            normalized = " ".join((search or "").split())
            if normalized and normalized not in searches:
                searches.append(normalized)
        seen: set[str] = set(exclude_work_ids)
        works: list[dict[str, Any]] = []
        for search in searches:
            if len(works) >= max_works:
                break
            self._emit_progress(
                progress_callback,
                "online_search",
                progress_found_offset + len(works),
                target,
                f"Searching online papers for: {search[:90]}",
            )
            try:
                request_size = min(50, max(max_works + len(exclude_work_ids), max_works))
                for work in search_arxiv(search, max_results=request_size, timeout=8):
                    if work["work_id"] not in seen:
                        if not self._is_domain_compatible(goal, work):
                            continue
                        seen.add(work["work_id"])
                        works.append(work)
                        self._emit_progress(
                            progress_callback,
                            "online_search",
                            progress_found_offset + len(works),
                            target,
                            f"Found {progress_found_offset + len(works)} of {target} requested works.",
                        )
                    if len(works) >= max_works:
                        break
            except Exception:
                continue
        if not works:
            works = self._filter_domain_compatible_works(
                goal,
                [work for work in fallback_seed_work(goal["raw_query"]) if work["work_id"] not in exclude_work_ids],
            )[:max_works]
        self._emit_progress(
            progress_callback,
            "work_search_done",
            progress_found_offset + len(works),
            target,
            f"Work search finished with {progress_found_offset + len(works)} of {target} requested works.",
        )
        return works[:max_works]

    def _derive_principle_relations(self, principles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        relations: list[dict[str, Any]] = []
        for i, left in enumerate(principles):
            for right in principles[i + 1 :]:
                left_tags = set(left.get("domain_tags", []))
                right_tags = set(right.get("domain_tags", []))
                left_hints = set(left.get("relation_hints", []))
                right_hints = set(right.get("relation_hints", []))
                shared_tags = sorted(left_tags & right_tags)
                shared_hints = sorted(left_hints & right_hints)
                shared_tradeoffs = sorted(set(left.get("tradeoffs", [])) & set(right.get("tradeoffs", [])))
                if shared_hints:
                    relation_type = shared_hints[0]
                    weight = 0.78
                elif shared_tags:
                    relation_type = "shares_domain_structure"
                    weight = 0.66
                elif shared_tradeoffs:
                    relation_type = "resolves_similar_tradeoff"
                    weight = 0.58
                else:
                    continue
                relation_id = stable_id(
                    "REL",
                    left["principle_id"],
                    right["principle_id"],
                    relation_type,
                )
                relations.append(
                    {
                        "relation_id": relation_id,
                        "source_principle_id": left["principle_id"],
                        "target_principle_id": right["principle_id"],
                        "relation_type": relation_type,
                        "weight": weight,
                        "rationale": compact_text(
                            "; ".join(shared_hints + shared_tags + shared_tradeoffs)
                            or "Principles share a reusable structural pattern.",
                            240,
                        ),
                        "created_at": utc_now(),
                    }
                )
        return relations

    def _mine_principles(
        self,
        goal: dict[str, Any],
        works: list[dict[str, Any]],
        *,
        offline: bool,
        model_mode: str,
    ) -> list[dict[str, Any]]:
        if self.llm.available() and not offline:
            try:
                compact_works = [
                    {
                        "work_id": work["work_id"],
                        "title": work["title"],
                        "year": work.get("year"),
                        "validation_level": work.get("validation_level", "L1"),
                        "abstract": compact_text(work.get("abstract", ""), 900),
                        "work_principles": work.get("work_principles", []),
                        "work_insights": work.get("work_insights", []),
                        "work_novelty": work.get("work_novelty", []),
                    }
                    for work in works
                ]
                data = self.llm.chat_json(
                    "You are Principia's Principle Miner. Extract sharp conceptual levers, not paper summaries.",
                    (
                        "Return strict JSON: {\"principles\": [ ... ]}. For each source work, create "
                        "one to three rich PrincipleCard objects when the work offers multiple mechanisms, "
                        "evaluation constraints, or transfer hooks for the current query. Each object must include keys: "
                        "name, principle_type, abstraction_level, "
                        "abstract_signature, mechanism, problem_pressure, objective, scarce_resources, "
                        "assumptions, constraints, invariants, tradeoffs, failure_modes, feedback_loop, "
                        "transfer_hooks, source_works, validation_level, confidence_score, empirical_claims, "
                        "evidence_spans, validation_notes, domain_tags, relation_hints. source_works must use work_id values. "
                        "Do not invent support beyond the abstract. Use L1 unless stronger evidence is explicit. "
                        "A good principle should feel like an insight a scientist can reuse: concise, non-obvious, "
                        "and capable of changing method design. Avoid bland technical descriptions and module lists. "
                        "Write the canonical record in English, even if the user query is Chinese; Chinese display text "
                        "will be produced by a later translation pass.\n\n"
                        "If query_kind is idea_draft, extract principles that can strengthen, revise, or falsify "
                        "the draft rather than merely supporting it.\n\n"
                        f"Research goal: {goal}\nSource works: {compact_works}"
                    ),
                    complexity=goal.get("complexity", 0.5),
                    mode=model_mode,
                    max_tokens=3600,
                    temperature=0.15,
                )
                principles = []
                for raw in data.get("principles", []):
                    source_ids = [wid for wid in raw.get("source_works", []) if wid in {w["work_id"] for w in works}]
                    if not source_ids:
                        continue
                    principles.append(self._normalize_principle(raw, source_ids))
                if principles:
                    return principles
            except Exception:
                pass
        principles: list[dict[str, Any]] = []
        for work in works:
            principles.extend(self._fallback_principles_for_work(goal, work))
        return principles

    def _curator_model_mode(self, model_mode: str) -> str:
        if model_mode.startswith("openai_"):
            return model_mode
        if model_mode in {"deepseek_pro", "kimi", "qwen_122b", "glm"}:
            return model_mode
        return "deepseek_pro"

    def _material_text(self, item: dict[str, Any]) -> str:
        values: list[str] = []
        for key in [
            "title",
            "abstract",
            "name",
            "one_sentence_thesis",
            "novelty_claim",
            "expected_contribution",
            "insight",
            "conceptual_takeaway",
            "sharp_reframing",
            "abstract_signature",
            "mechanism",
            "problem_pressure",
            "objective",
            "principle_type",
        ]:
            if item.get(key):
                values.append(str(item.get(key)))
        for key in [
            "work_principles",
            "work_insights",
            "work_novelty",
            "domain_tags",
            "transfer_hooks",
            "validation_notes",
            "tradeoffs",
            "failure_modes",
            "mechanism_design",
            "why_it_might_work",
            "validation_protocol",
            "baselines",
            "metrics",
        ]:
            values.extend(str(value) for value in item.get(key, []) if value)
        return " ".join(values)

    def _goal_text(self, goal: dict[str, Any]) -> str:
        return enrich_query(
            " ".join(
                [
                    str(goal.get("raw_query", "")),
                    str(goal.get("target_domain", "")),
                    " ".join(str(term) for term in goal.get("search_terms", []) if term),
                ]
            )
        ).lower()

    def _has_any(self, text: str, terms: list[str]) -> bool:
        return any(term in text for term in terms)

    def _has_rul_token(self, text: str) -> bool:
        return bool(re.search(r"(?<![a-z0-9])rul(?![a-z0-9])", text.lower()))

    def _goal_flags(self, goal: dict[str, Any]) -> dict[str, bool]:
        text = self._goal_text(goal)
        time_series = self._has_any(
            text,
            [
                "timesfm",
                "time series",
                "sensor",
                "remaining useful life",
                "forecast",
                "degradation",
                "prognostic",
            ],
        ) or self._has_rul_token(text)
        return {
            "time_series": time_series,
            "reconstruction": self._has_any(
                text,
                [
                    "3d reconstruction",
                    "sparse view",
                    "few view",
                    "limited view",
                    "nerf",
                    "gaussian splatting",
                    "multi view stereo",
                ],
            ),
            "mas": self._has_any(
                text,
                [
                    "mas",
                    "multi-agent",
                    "multi agent",
                    "llm agent",
                    "agent communication",
                    "agent collaboration",
                    "agent society",
                    "multi-agent systems",
                    "scientific discovery",
                ],
            ),
            "symbolic": self._has_any(
                text,
                [
                    "symbolic compactness",
                    "symbolic reasoning",
                    "intrinsic reward",
                    "intrinsic rewards",
                    "minimum description length",
                    "representation compression",
                ],
            ),
            "dialect": self._has_any(
                text,
                [
                    "machine dialect",
                    "dialect",
                    "social interaction",
                    "agent communication protocol",
                    "token efficient",
                    "token cost",
                    "completion cost",
                ],
            ),
            "vision_ttt": self._has_any(
                text,
                [
                    "few-shot",
                    "few shot",
                    "few-shot learning",
                    "test-time training",
                    "test time training",
                    "test-time adaptation",
                    "test time adaptation",
                    "clip",
                    "vision-language",
                    "vision transformer",
                    "vit",
                    "4090",
                    "prompt learning",
                    "parameter-efficient tuning",
                ],
            ),
        }

    def _is_domain_compatible(self, goal: dict[str, Any], item: dict[str, Any]) -> bool:
        body = self._material_text(item).lower()
        if not body:
            return True
        flags = self._goal_flags(goal)
        time_terms = [
            "timesfm",
            "remaining useful life",
            "rul prediction",
            "prognostic",
            "degradation modeling",
            "cross-sensor",
            "cross sensor",
            "sensor transformer",
            "industrial sensor",
        ]
        reconstruction_terms = [
            "sparse-view",
            "sparse view",
            "few-view",
            "few view",
            "limited-view",
            "limited view",
            "3d reconstruction",
            "neural radiance",
            "gaussian splatting",
            "novel view synthesis",
        ]
        if not flags["time_series"] and self._has_any(body, time_terms):
            return False
        if not flags["reconstruction"] and self._has_any(body, reconstruction_terms):
            return False
        if flags["mas"] or flags["symbolic"] or flags["dialect"]:
            mas_anchor_terms = [
                "llm",
                "large language model",
                "language model",
                "agent",
                "multi-agent",
                "multi agent",
                "scientific discovery",
                "hypothesis",
                "reasoning",
                "symbolic",
                "intrinsic reward",
                "minimum description length",
                "compression",
                "communication",
                "dialect",
                "debate",
                "social",
                "token",
                "cost",
                "emergent",
            ]
            math_compactness_terms = [
                "hankel",
                "zariski",
                "semigroup",
                "schrödinger",
                "schrodinger",
                "manifold",
                "cardinal",
                "topological",
                "topology",
                "spectrum",
                "operator",
                "hilbert",
                "banach",
                "fuzzy numbers",
            ]
            has_mas_anchor = self._has_any(body, mas_anchor_terms)
            if "compactness" in body and not has_mas_anchor:
                return False
            if self._has_any(body, math_compactness_terms) and not has_mas_anchor:
                return False
            if not has_mas_anchor and lexical_score(goal.get("raw_query", ""), body) < 0.28:
                return False
        return True

    def _filter_domain_compatible_works(
        self,
        goal: dict[str, Any],
        works: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [work for work in works if self._is_domain_compatible(goal, work)]

    def _filter_domain_compatible_principles(
        self,
        goal: dict[str, Any],
        principles: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [principle for principle in principles if self._is_domain_compatible(goal, principle)]

    def _curate_materials(
        self,
        goal: dict[str, Any],
        source_works: list[dict[str, Any]],
        principles: list[dict[str, Any]],
        *,
        max_ideas: int,
        offline: bool,
        model_mode: str,
    ) -> dict[str, Any]:
        source_works = self._filter_domain_compatible_works(goal, source_works)
        principles = self._filter_domain_compatible_principles(goal, principles)
        fallback = self._fallback_curate_materials(goal, source_works, principles, max_ideas=max_ideas)
        if offline or not self.llm.available() or not source_works or not principles:
            return fallback
        try:
            compact_works = [
                {
                    "work_id": work["work_id"],
                    "title": work.get("title", ""),
                    "abstract": compact_text(work.get("abstract", ""), 500),
                    "insights": [self._strip_fact_prefix(item) for item in work.get("work_insights", [])[:2]],
                    "novelty": [self._strip_fact_prefix(item) for item in work.get("work_novelty", [])[:2]],
                    "score_hint": round(lexical_score(goal["raw_query"], self._material_text(work)), 4),
                }
                for work in source_works[:40]
            ]
            compact_principles = [
                {
                    "principle_id": principle["principle_id"],
                    "name": principle.get("name", ""),
                    "mechanism": compact_text(principle.get("mechanism", ""), 360),
                    "problem_pressure": compact_text(principle.get("problem_pressure", ""), 240),
                    "objective": compact_text(principle.get("objective", ""), 240),
                    "source_works": principle.get("source_works", []),
                    "score_hint": round(lexical_score(goal["raw_query"], self._material_text(principle)), 4),
                }
                for principle in principles[:80]
            ]
            evidence_pool = self._idea_evidence_pool(goal, principles)
            fact_pool = {
                "insights": evidence_pool["insights"][:50],
                "novelty": evidence_pool["novelty"][:50],
            }
            data = self.llm.chat_json(
                "You are Principia's Evidence Curator. Be severe, selective, and insight-first.",
                (
                    "Select the materials that should be shown to the idea generator. Return strict JSON with keys: "
                    "selected_work_ids, selected_principle_ids, selected_insight_ids, selected_novelty_ids, "
                    "synthesis_brief, core_tension, user_need, rejection_notes. "
                    "Rules: choose only materials with direct leverage on the user's query; reject broad topical matches; "
                    "reject domain collisions even when they look locally plausible, e.g. TimesFM/RUL papers must not be "
                    "used for a symbolic/MAS query, and pure mathematical compactness papers must not be used when the "
                    "user means compact symbolic scientific reasoning; "
                    "prefer principles that reveal a bottleneck, tradeoff, or conceptual reframing; prefer insights that "
                    "would change how a scientist thinks about the problem; prefer novelty facts only when they supply a "
                    "non-obvious move. Do not reward technical complexity. The brief should be pithy, creative, and "
                    "non-incremental.\n\n"
                    f"User goal: {goal}\nCandidate works: {compact_works}\nCandidate principles: {compact_principles}\n"
                    f"Candidate work facts: {fact_pool}\n"
                    f"Select about {min(len(compact_works), max(4, max_ideas))} works, "
                    f"{min(len(compact_principles), max(6, max_ideas * 2))} principles, "
                    f"and {min(12, max_ideas * 2)} insights/novelty facts."
                ),
                complexity=max(float(goal.get("complexity", 0.5)), 0.72),
                mode=self._curator_model_mode(model_mode),
                max_tokens=2600,
                temperature=0.1,
            )
            curated = self._apply_curation_selection(goal, source_works, principles, data, max_ideas=max_ideas)
            if curated["principles"] and curated["source_works"]:
                return curated
        except Exception:
            pass
        return fallback

    def _apply_curation_selection(
        self,
        goal: dict[str, Any],
        source_works: list[dict[str, Any]],
        principles: list[dict[str, Any]],
        data: dict[str, Any],
        *,
        max_ideas: int,
    ) -> dict[str, Any]:
        work_map = {work["work_id"]: work for work in source_works}
        principle_map = {principle["principle_id"]: principle for principle in principles}
        evidence_pool = self._idea_evidence_pool(goal, principles)
        insight_map = {item["fact_id"]: item for item in evidence_pool["insights"]}
        novelty_map = {item["fact_id"]: item for item in evidence_pool["novelty"]}
        selected_works = [work_map[wid] for wid in data.get("selected_work_ids", []) if wid in work_map]
        selected_principles = [principle_map[pid] for pid in data.get("selected_principle_ids", []) if pid in principle_map]
        selected_insights = [insight_map[fid] for fid in data.get("selected_insight_ids", []) if fid in insight_map]
        selected_novelty = [novelty_map[fid] for fid in data.get("selected_novelty_ids", []) if fid in novelty_map]
        fallback = self._fallback_curate_materials(goal, source_works, principles, max_ideas=max_ideas)
        if not selected_principles:
            selected_principles = fallback["principles"]
        if not selected_works:
            selected_works = fallback["source_works"]
        if not selected_insights:
            selected_insights = fallback["insights"]
        if not selected_novelty:
            selected_novelty = fallback["novelty"]
        selected_works = self._dedupe_works(selected_works)[: max(5, max_ideas)]
        selected_principles = self._dedupe_principles(selected_principles)[: max(6, max_ideas * 2)]
        return {
            "source_works": selected_works,
            "principles": selected_principles,
            "insights": selected_insights[: max(6, max_ideas * 2)],
            "novelty": selected_novelty[: max(6, max_ideas * 2)],
            "brief": {
                "curator": "llm",
                "synthesis_brief": str(data.get("synthesis_brief") or fallback["brief"]["synthesis_brief"]),
                "core_tension": str(data.get("core_tension") or fallback["brief"]["core_tension"]),
                "user_need": str(data.get("user_need") or fallback["brief"]["user_need"]),
                "rejection_notes": self._list(data.get("rejection_notes"), fallback["brief"]["rejection_notes"]),
            },
        }

    def _fallback_curate_materials(
        self,
        goal: dict[str, Any],
        source_works: list[dict[str, Any]],
        principles: list[dict[str, Any]],
        *,
        max_ideas: int,
    ) -> dict[str, Any]:
        query = goal.get("raw_query", "")
        scored_principles = sorted(
            principles,
            key=lambda p: (
                lexical_score(query, self._material_text(p)),
                float(p.get("confidence_score", 0.0)),
                validation_number(p.get("validation_level", "L0")),
            ),
            reverse=True,
        )
        selected_principles = scored_principles[: max(6, max_ideas * 2)] or principles[: max(2, max_ideas)]
        principle_work_ids = {wid for principle in selected_principles for wid in principle.get("source_works", [])}
        work_candidates = [work for work in source_works if work.get("work_id") in principle_work_ids] or source_works
        selected_works = sorted(
            work_candidates,
            key=lambda work: lexical_score(query, self._material_text(work)),
            reverse=True,
        )[: max(5, max_ideas)]
        evidence_pool = self._idea_evidence_pool(goal, selected_principles)
        insights = sorted(
            evidence_pool["insights"],
            key=lambda item: lexical_score(query, item.get("text", "")),
            reverse=True,
        )[: max(6, max_ideas * 2)]
        novelty = sorted(
            evidence_pool["novelty"],
            key=lambda item: lexical_score(query, item.get("text", "")),
            reverse=True,
        )[: max(6, max_ideas * 2)]
        topic_terms = ", ".join(keyword_terms(enrich_query(query), 5))
        return {
            "source_works": self._dedupe_works(selected_works),
            "principles": self._dedupe_principles(selected_principles),
            "insights": insights,
            "novelty": novelty,
            "brief": {
                "curator": "heuristic",
                "synthesis_brief": (
                    f"Focus on the hidden leverage in {goal.get('target_domain', 'the task')}: "
                    "what must be separated, delayed, gated, or measured before adding model complexity."
                ),
                "core_tension": (
                    "The best idea should expose a sharp bottleneck, not merely append another module."
                ),
                "user_need": f"Give the user a reframing around {topic_terms or 'the query'} that feels obvious in hindsight.",
                "rejection_notes": [
                    "Dropped materials that only matched broad keywords.",
                    "Prioritized facts that imply a design choice or falsification axis.",
                ],
            },
        }

    def _synthesize_ideas(
        self,
        goal: dict[str, Any],
        principles: list[dict[str, Any]],
        *,
        max_ideas: int,
        offline: bool,
        model_mode: str,
        curation: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        evidence_pool = {
            "insights": list((curation or {}).get("insights") or []),
            "novelty": list((curation or {}).get("novelty") or []),
        }
        if not evidence_pool["insights"] and not evidence_pool["novelty"]:
            evidence_pool = self._idea_evidence_pool(goal, principles)
        brief = (curation or {}).get("brief", {})
        if self.llm.available() and not offline and principles:
            try:
                compact_principles = [
                    {
                        "principle_id": p["principle_id"],
                        "name": p["name"],
                        "mechanism": p["mechanism"],
                        "problem_pressure": p["problem_pressure"],
                        "tradeoffs": p.get("tradeoffs", []),
                        "failure_modes": p.get("failure_modes", []),
                        "transfer_hooks": p.get("transfer_hooks", []),
                        "validation_level": p.get("validation_level", "L0"),
                        "confidence_score": p.get("confidence_score", 0.4),
                    }
                    for p in principles
                ]
                compact_facts = {
                    "insights": evidence_pool["insights"][: min(18, max_ideas * 3)],
                    "novelty": evidence_pool["novelty"][: min(18, max_ideas * 3)],
                }
                data = self.llm.chat_json(
                    "You are Principia's Idea Algebra Engine. Be brilliant, concise, and non-incremental.",
                    (
                        "Generate principle-derived research IdeaCards. Return strict JSON with key "
                        "\"ideas\". Each idea must include: title, one_sentence_thesis, "
                        "conceptual_takeaway, sharp_reframing, "
                        "source_principles, source_insights, source_novelty, operator_trace, novelty_claim, prior_art_overlap, "
                        "expected_contribution, insight, mechanism_design, why_it_might_work, "
                        "minimal_experiment, validation_protocol, baselines, metrics, failure_modes, "
                        "ranking_scores, estimate. "
                        "source_principles must contain principle_id values. source_insights and source_novelty must contain "
                        "fact_id values from the supplied work facts, and they may come from different works than the principles. "
                        "Do not put model names such as GPT, DeepSeek, GLM, Kimi, or Qwen in idea titles. "
                        "Every title must be unique and method-specific. Avoid template duplicates. "
                        "Avoid overusing generic motifs such as 'falsification-gated', 'evaluator-first', or "
                        "'staged mechanism' unless the user's query explicitly asks for validation architecture. "
                        "For MAS or symbolic-scientific-discovery queries, favor conceptual moves such as symbolic "
                        "compression, dialect contracts, crux formation, social proof pressure, and token-value exchange. "
                        "Do not produce engineering stack-ups or incremental module soup. Each idea should read like a sharp research "
                        "thesis: name the bottleneck, the reframing, the mechanism, and the cheapest way to falsify it. "
                        "Keep technical details only where they reveal the conceptual move. Write the canonical IdeaCards in "
                        "English, even if the user query is Chinese; Chinese display text will be produced by a later translation pass. "
                        "estimate keys: primary_metric, mean, lower_90, upper_90, "
                        "probability_useful_signal, probability_negative_result, "
                        "probability_implementation_failure, compute_cost_estimate, "
                        "time_to_first_signal, key_risks, cheapest_falsification, evidence_basis. "
                        "Use explicit operators from this list: "
                        f"{OPERATORS}. Generate {max_ideas} ideas. Keep validation cheap enough for "
                        "a one-day local demo. If the goal contains an idea_draft, generate improved variants, "
                        "stress-test alternatives, and concrete validation paths rather than restating the draft.\n\n"
                        f"Goal: {goal}\nCurated synthesis brief: {brief}\n"
                        f"Curated principles: {compact_principles}\nCurated independent work facts: {compact_facts}"
                    ),
                    complexity=goal.get("complexity", 0.5),
                    mode=model_mode,
                    max_tokens=6800,
                    temperature=0.55,
                )
                raw_ideas = list(data.get("ideas", []) or [])
                raw_ideas.extend(
                    self._fallback_idea(goal, principles, idx, model_mode=model_mode)
                    for idx in range(max_ideas * 2)
                )
                return self._normalize_ideas(
                    goal,
                    principles,
                    raw_ideas,
                    model_mode=model_mode,
                    max_ideas=max_ideas,
                    evidence_pool=evidence_pool,
                )
            except Exception:
                pass
        raw = [self._fallback_idea(goal, principles, idx, model_mode=model_mode) for idx in range(max_ideas)]
        return self._normalize_ideas(
            goal,
            principles,
            raw,
            model_mode=model_mode,
            max_ideas=max_ideas,
            evidence_pool=evidence_pool,
        )

    def _normalize_principle(self, raw: dict[str, Any], source_ids: list[str]) -> dict[str, Any]:
        name = str(raw.get("name") or "Reusable research mechanism").strip()
        mechanism = str(raw.get("mechanism") or raw.get("core_mechanism") or "").strip()
        if not mechanism:
            mechanism = "Translate source evidence into an explicit mechanism and test its assumptions."
        principle = PrincipleCard(
            principle_id=stable_id("P", name, mechanism, ",".join(source_ids)),
            name=name[:140],
            principle_type=str(raw.get("principle_type") or "mechanism"),
            abstraction_level=str(raw.get("abstraction_level") or "mechanism"),
            abstract_signature=str(raw.get("abstract_signature") or "transfer a supported mechanism into a cheap validation path"),
            mechanism=mechanism,
            problem_pressure=str(raw.get("problem_pressure") or "A research system must turn prior work into reusable design constraints."),
            objective=str(raw.get("objective") or "Improve the target metric under the stated constraints."),
            scarce_resources=self._list(raw.get("scarce_resources"), ["data", "compute", "validation time"]),
            assumptions=self._list(raw.get("assumptions"), ["The source claim transfers to the target domain."]),
            constraints=self._list(raw.get("constraints"), ["Keep validation cheap and falsifiable."]),
            invariants=self._list(raw.get("invariants"), ["Mechanism must be observable in a small experiment."]),
            tradeoffs=self._list(raw.get("tradeoffs"), ["novelty vs feasibility"]),
            failure_modes=self._list(raw.get("failure_modes"), ["Transferred principle may not match the target benchmark."]),
            feedback_loop=self._list(raw.get("feedback_loop"), ["measure", "compare against baseline", "update principle confidence"]),
            transfer_hooks=self._list(raw.get("transfer_hooks"), ["map abstract pressure to target research system"]),
            source_works=source_ids,
            validation_level=str(raw.get("validation_level") or "L1"),
            confidence_score=clamp(float(raw.get("confidence_score", 0.45)), 0.0, 1.0),
            empirical_claims=self._list(raw.get("empirical_claims"), []),
            evidence_spans=list(raw.get("evidence_spans") or []),
            validation_notes=self._list(raw.get("validation_notes"), ["Verify with a small, explicit baseline comparison."]),
            domain_tags=self._list(raw.get("domain_tags"), keyword_terms(name + " " + mechanism, 4)),
            relation_hints=self._list(raw.get("relation_hints"), []),
        )
        return to_dict(principle)

    def _pick_sentence(self, sentences: list[str], keywords: list[str], default: str) -> str:
        for keyword in keywords:
            for sentence in sentences:
                if keyword.lower() in sentence.lower():
                    return sentence
        return default

    def _domain_profile(self, goal: dict[str, Any], work: dict[str, Any]) -> dict[str, Any]:
        text = enrich_query(
            " ".join(
                [
                    goal.get("target_domain", ""),
                    goal.get("raw_query", ""),
                    work.get("title", ""),
                    work.get("abstract", ""),
                ]
            )
        ).lower()
        if "3d reconstruction" in text or "sparse-view" in text or "few view" in text:
            return {
                "principle_type": "geometry_prior_under_sparse_observation",
                "abstract_signature": "recover latent 3D structure from scarce, ambiguous, partially overlapping observations",
                "scarce_resources": ["input views", "cross-view overlap", "camera/pose certainty", "training time"],
                "assumptions": [
                    "Geometric or physical constraints can compensate for missing views.",
                    "Generated or regularized views improve consistency more than they introduce hallucinated geometry.",
                    "The evaluation set contains enough pose and scene diversity to expose overfitting.",
                ],
                "constraints": [
                    "Use few-view benchmarks or a downsampled view split.",
                    "Avoid relying on full dense-view supervision during validation.",
                ],
                "invariants": [
                    "Novel-view predictions must remain cross-view consistent.",
                    "Geometry quality and perceptual quality must be measured separately.",
                    "Any prior or augmentation must be checked for hallucinated structure.",
                ],
                "tradeoffs": [
                    "geometry fidelity vs perceptual plausibility",
                    "prior strength vs hallucination risk",
                    "parameter efficiency vs scene-specific detail",
                    "view synthesis quality vs reconstruction consistency",
                ],
                "failure_modes": [
                    "Pose ambiguity creates plausible but wrong geometry.",
                    "Diffusion or foundation-model priors hallucinate unobserved surfaces.",
                    "Floaters or opacity artifacts improve PSNR while hurting 3D structure.",
                    "A method overfits to object-centric scenes and fails on open scenes.",
                ],
                "feedback_loop": [
                    "train on k sparse views",
                    "render held-out views and geometry diagnostics",
                    "measure PSNR/SSIM/LPIPS plus depth or consistency proxies",
                    "penalize principles that improve appearance while degrading geometry",
                ],
                "transfer_hooks": [
                    "turn sparse-view uncertainty into explicit view/region confidence",
                    "use priors only where cross-view evidence is weak",
                    "validate with view-count stratification and pose perturbation",
                ],
                "validation_notes": [
                    "Run 3/6/9-view splits rather than one aggregate score.",
                    "Compare against a plain 3DGS or NeRF baseline plus a regularized baseline.",
                    "Inspect failure cases visually because scalar metrics can reward hallucination.",
                ],
                "domain_tags": ["sparse-view", "3d-reconstruction", "geometry-prior", "view-consistency"],
                "relation_hints": ["shares_sparse_observation_pressure", "resolves_geometry_prior_tradeoff"],
            }
        if any(
            term in text
            for term in [
                "few-shot",
                "few shot",
                "test-time training",
                "test time training",
                "test-time adaptation",
                "clip",
                "vision-language",
                "vision transformer",
                "vit",
                "4090",
            ]
        ):
            return {
                "principle_type": "resource_aware_visual_adaptation",
                "abstract_signature": "adapt CLIP or ViT-style visual representations under few-shot supervision and strict test-time compute limits",
                "scarce_resources": ["labeled shots", "test-time compute", "GPU memory", "adaptation latency", "benchmark budget"],
                "assumptions": [
                    "CLIP already contains useful class semantics that should not be overwritten.",
                    "Few-shot gains should come from lightweight adaptation rather than full model retraining.",
                    "A method is only useful if its accuracy gain survives base-to-novel and domain-shift splits.",
                ],
                "constraints": [
                    "Fit experiments within 4-8 RTX 4090 GPUs.",
                    "Report per-dataset adaptation time and memory, not only accuracy.",
                    "Compare against zero-shot CLIP and common prompt/adaptation baselines.",
                ],
                "invariants": [
                    "Class semantics from CLIP must remain stable after test-time updates.",
                    "Test-time updates must have a bounded step count or early-stop rule.",
                    "The same benchmark matrix must be used for all baselines.",
                ],
                "tradeoffs": [
                    "accuracy gain vs per-sample adaptation cost",
                    "test-time plasticity vs semantic drift",
                    "prompt tuning simplicity vs token-level flexibility",
                    "few-shot specialization vs base-to-novel generalization",
                ],
                "failure_modes": [
                    "Test-time training overfits the support set or the first test batch.",
                    "Extra adaptation compute hides a weak method contribution.",
                    "A method improves easy datasets but fails on domain-shift datasets.",
                    "CLIP text semantics drift after visual-side updates.",
                ],
                "feedback_loop": [
                    "fix datasets, shots, and base-to-novel splits",
                    "run zero-shot and adaptation baselines under equal compute accounting",
                    "measure accuracy, adaptation time, GPU memory, and calibration",
                    "ablate the updated parameter subset and early-stop criterion",
                ],
                "transfer_hooks": [
                    "adapt only prompts, adapters, token selectors, or normalization statistics",
                    "use prediction stability or entropy to stop test-time updates",
                    "report ImageNet, Caltech101, OxfordPets, Food101, DTD, EuroSAT, UCF101, and SUN397",
                    "include CoOp, CoCoOp, Tip-Adapter, TPT, zero-shot CLIP, and linear-probe baselines",
                ],
                "validation_notes": [
                    "Use 1/2/4/8/16-shot settings with base-to-novel splits where available.",
                    "Report accuracy-cost Pareto curves and wall-clock estimates on 4-8 RTX 4090 GPUs.",
                    "Separate contribution into representation update, adaptation criterion, and benchmark protocol.",
                ],
                "domain_tags": ["few-shot-vision", "clip", "test-time-training", "resource-aware", "vision-transformer"],
                "relation_hints": ["shares_adaptation_budget_pressure", "resolves_accuracy_cost_tradeoff"],
            }
        return {
            "principle_type": "transferable_mechanism",
            "abstract_signature": "connect a scarce research resource to an observable mechanism and a decisive first experiment",
            "scarce_resources": ["data", "compute", "latency", "validation time"],
            "assumptions": [
                "The source abstraction preserves the important constraint in the target task.",
                "The first validation slice captures the key tradeoff.",
            ],
            "constraints": ["Avoid full-scale training in the demo."],
            "invariants": [
                "The mechanism must connect a scarce resource to an observable outcome.",
                "The idea must include a falsification path.",
            ],
            "tradeoffs": ["novelty vs implementation difficulty", "quality vs compute cost"],
            "failure_modes": [
                "Baseline may already contain the transferred mechanism.",
                "A small benchmark may understate variance or overhead.",
            ],
            "feedback_loop": ["measure", "compare against baseline", "update principle confidence"],
            "transfer_hooks": ["map the abstract pressure to a target-domain observable"],
            "validation_notes": ["Start with the smallest fair baseline comparison."],
            "domain_tags": keyword_terms(enrich_query(goal.get("raw_query", "")), 4),
            "relation_hints": ["shares_resource_tradeoff"],
        }

    def _fallback_principles_for_work(self, goal: dict[str, Any], work: dict[str, Any]) -> list[dict[str, Any]]:
        primary = self._fallback_principle(goal, work, variant=0)
        validation = self._fallback_principle(goal, work, variant=1)
        return [primary, validation]

    def _fallback_principle(self, goal: dict[str, Any], work: dict[str, Any], variant: int = 0) -> dict[str, Any]:
        sentences = sentence_split(work.get("abstract", ""))
        profile = self._domain_profile(goal, work)
        pressure = self._pick_sentence(
            sentences,
            ["challenge", "fail", "sparse", "limited", "insufficient", "cost", "resource", "pressure"],
            sentences[0] if sentences else f"Research goal needs prior work related to {goal['target_domain']}.",
        )
        mechanism = self._pick_sentence(
            sentences,
            ["propose", "employ", "framework", "uses", "leverage", "regularization", "constraint", "alignment", "augment"],
            sentences[1] if len(sentences) > 1 else (
            "Use the work's central mechanism as a transferable constraint, then validate it with a cheap controlled experiment."
            ),
        )
        objective = self._pick_sentence(
            sentences,
            ["achieve", "outperform", "improve", "demonstrate", "reduce", "robust", "generalization", "quality"],
            "Improve the target metric while preserving a fair, low-cost validation path.",
        )
        terms = keyword_terms(enrich_query(work.get("title", "") + " " + work.get("abstract", "")), 6)
        name = " ".join(term.capitalize() for term in terms[:4]) or "Transferable Mechanism"
        principle_kind = "evidence discipline" if variant else "mechanism"
        if variant:
            name = f"{name} validation"
            mechanism = (
                "Convert the work's central mechanism into a query-specific validation discipline: isolate the "
                "resource bottleneck, stratify the evaluation by failure mode, and reject variants that improve "
                "surface metrics while violating the principle invariants."
            )
            objective = (
                "Expose whether the principle genuinely helps the current scientific question before scaling the method."
            )
            profile = {
                **profile,
                "principle_type": f"{profile['principle_type']}_validation",
                "abstract_signature": profile["abstract_signature"] + " with explicit failure-stratified validation",
                "transfer_hooks": [
                    "turn the principle into an ablation axis",
                    "separate metric gains from mechanism-specific failure reduction",
                    *profile["transfer_hooks"],
                ],
                "relation_hints": [*profile["relation_hints"], "shares_validation_protocol"],
            }
        confidence = 0.28 + 0.08 * validation_number(work.get("validation_level", "L0"))
        return to_dict(
            PrincipleCard(
                principle_id=stable_id("P", name, mechanism, work["work_id"], str(variant)),
                name=f"{name} principle",
                principle_type=profile["principle_type"],
                abstraction_level=principle_kind,
                abstract_signature=profile["abstract_signature"],
                mechanism=compact_text(mechanism, 420),
                problem_pressure=compact_text(pressure, 320),
                objective=compact_text(objective, 280),
                scarce_resources=profile["scarce_resources"],
                assumptions=profile["assumptions"],
                constraints=[
                    goal.get("constraints", {}).get("compute_budget", "API-only or one-day validation"),
                    *profile["constraints"],
                ],
                invariants=profile["invariants"],
                tradeoffs=profile["tradeoffs"],
                failure_modes=profile["failure_modes"],
                feedback_loop=profile["feedback_loop"],
                transfer_hooks=[
                    f"Apply {terms[0] if terms else 'source'} mechanism to {goal.get('target_domain', 'target domain')}.",
                    *profile["transfer_hooks"],
                    "Bind the transfer to an estimator and minimal experiment.",
                ],
                source_works=[work["work_id"]],
                validation_level=work.get("validation_level", "L0"),
                confidence_score=clamp(confidence, 0.12, 0.75),
                empirical_claims=[compact_text(objective, 240)] if objective else [],
                evidence_spans=[{"section": "abstract", "claim": compact_text(pressure, 260)}],
                validation_notes=profile["validation_notes"],
                domain_tags=profile["domain_tags"],
                relation_hints=profile["relation_hints"],
            )
        )

    def _strip_fact_prefix(self, text: str) -> str:
        value = " ".join(str(text or "").split())
        prefixes = [
            "general principle",
            "reusable mechanism",
            "principle",
            "insight",
            "novelty",
            "核心机制",
            "创新点",
            "结论洞察",
        ]
        for _ in range(3):
            lower = value.lower()
            changed = False
            for prefix in prefixes:
                if lower.startswith(prefix.lower() + ":") or lower.startswith(prefix.lower() + "："):
                    value = value[len(prefix) + 1 :].strip()
                    changed = True
                    break
            if not changed:
                break
        return value

    def _clean_idea_title(self, title: str, idx: int) -> str:
        value = " ".join(str(title or f"Principia Idea {idx + 1}").split()).strip()
        value = re.sub(
            r"^\s*(?:openai\s*)?(?:gpt[-\s]?5(?:\.\d+)?(?:[-\s]?pro)?|deepseek(?:[-\s]?(?:pro|strong|v4))?|glm(?:[-\s]?agentic)?|kimi|qwen(?:\d+(?:\.\d+)?)?|moe[-\s]?efficient|high[-\s]?capacity|long[-\s]?context|efficient)\s*[:：\-]\s*",
            "",
            value,
            flags=re.IGNORECASE,
        ).strip()
        model_prefixes = [
            "GPT-5.5",
            "GPT5.5",
            "GPT-5.2-Pro",
            "GPT5.2-Pro",
            "GPT-5-Pro",
            "GPT5-Pro",
            "OpenAI",
            "DeepSeek-Pro",
            "DeepSeek-Strong",
            "DeepSeek-V4-Pro",
            "DeepSeek",
            "GLM-Agentic",
            "GLM",
            "GLM-5.1",
            "Kimi",
            "Kimi-2.6",
            "Qwen",
            "MoE-Efficient",
            "High-Capacity",
            "Efficient",
            "Long-Context",
        ]
        for _ in range(3):
            lower = value.lower()
            changed = False
            for prefix in model_prefixes:
                if lower.startswith(prefix.lower() + ":"):
                    value = value[len(prefix) + 1 :].strip()
                    changed = True
                    break
                if lower.startswith(prefix.lower() + " - "):
                    value = value[len(prefix) + 3 :].strip()
                    changed = True
                    break
            if not changed:
                break
        return compact_text(value or f"Principia Idea {idx + 1}", 140)

    def _idea_title_key(self, title: str) -> str:
        return "".join(ch.lower() for ch in title if ch.isalnum())

    def _idea_evidence_pool(self, goal: dict[str, Any], principles: list[dict[str, Any]]) -> dict[str, list[dict[str, str]]]:
        insights: list[dict[str, str]] = []
        novelty: list[dict[str, str]] = []
        for work in self._works_for_principles(principles):
            enriched = self._enrich_work_record(goal, work)
            for idx, text in enumerate(enriched.get("work_insights", [])[:2]):
                cleaned = self._strip_fact_prefix(text)
                if cleaned:
                    insights.append(
                        {
                            "fact_id": stable_id("FI", enriched.get("work_id", ""), str(idx), cleaned),
                            "type": "insight",
                            "work_id": enriched.get("work_id", ""),
                            "work_title": enriched.get("title", ""),
                            "text": compact_text(cleaned, 300),
                        }
                    )
            for idx, text in enumerate(enriched.get("work_novelty", [])[:2]):
                cleaned = self._strip_fact_prefix(text)
                if cleaned:
                    novelty.append(
                        {
                            "fact_id": stable_id("FN", enriched.get("work_id", ""), str(idx), cleaned),
                            "type": "novelty",
                            "work_id": enriched.get("work_id", ""),
                            "work_title": enriched.get("title", ""),
                            "text": compact_text(cleaned, 300),
                        }
                    )
        return {"insights": insights, "novelty": novelty}

    def _select_fact_sources(
        self,
        raw: dict[str, Any],
        field: str,
        pool: list[dict[str, str]],
        idx: int,
        *,
        count: int = 2,
    ) -> list[dict[str, str]]:
        if not pool:
            return []
        by_id = {item["fact_id"]: item for item in pool}
        selected: list[dict[str, str]] = []
        for raw_item in raw.get(field, []) or []:
            fact_id = raw_item.get("fact_id") if isinstance(raw_item, dict) else str(raw_item)
            item = by_id.get(str(fact_id))
            if item and item["fact_id"] not in {picked["fact_id"] for picked in selected}:
                selected.append(item)
        cursor = idx * count + (1 if field == "source_novelty" else 0)
        while len(selected) < count and len(selected) < len(pool):
            candidate = pool[cursor % len(pool)]
            cursor += 1
            if candidate["fact_id"] not in {picked["fact_id"] for picked in selected}:
                selected.append(candidate)
        return selected[:count]

    def _normalize_ideas(
        self,
        goal: dict[str, Any],
        principles: list[dict[str, Any]],
        raw_ideas: list[dict[str, Any]],
        *,
        model_mode: str = "auto",
        max_ideas: int | None = None,
        evidence_pool: dict[str, list[dict[str, str]]] | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        principle_ids = {p["principle_id"] for p in principles}
        evidence_pool = evidence_pool or self._idea_evidence_pool(goal, principles)
        seen_titles: set[str] = set()
        ideas: list[dict[str, Any]] = []
        estimates: list[dict[str, Any]] = []
        plans: list[dict[str, Any]] = []
        for idx, raw in enumerate(raw_ideas):
            title = self._clean_idea_title(str(raw.get("title") or f"Principia Idea {idx + 1}"), idx)
            title_key = self._idea_title_key(title)
            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)
            source_ids = [pid for pid in raw.get("source_principles", []) if pid in principle_ids]
            if not source_ids:
                source_ids = [p["principle_id"] for p in principles[idx : idx + 2]] or [
                    p["principle_id"] for p in principles[:2]
                ]
            insight_sources = self._select_fact_sources(raw, "source_insights", evidence_pool["insights"], idx)
            novelty_sources = self._select_fact_sources(raw, "source_novelty", evidence_pool["novelty"], idx)
            idea_id = stable_id("I", goal["goal_id"], title, ",".join(source_ids), model_mode)
            estimate = self._normalize_estimate(idea_id, raw.get("estimate") or {}, source_ids)
            plan = self._build_prompt_plan(idea_id, title, raw, goal, principles, estimate)
            idea = IdeaCard(
                idea_id=idea_id,
                title=title,
                one_sentence_thesis=str(
                    raw.get("one_sentence_thesis")
                    or raw.get("thesis")
                    or "Use explicit principle lineage to produce a testable research variant."
                ),
                research_goal_id=goal["goal_id"],
                source_principles=source_ids,
                operator_trace=list(
                    raw.get("operator_trace")
                    or [{"operator": OPERATORS[idx % len(OPERATORS)], "explanation": "Demo fallback trace."}]
                ),
                novelty_claim=str(
                    raw.get("novelty_claim")
                    or "The novelty is in binding the mechanism transfer to an explicit first validation slice."
                ),
                prior_art_overlap=list(raw.get("prior_art_overlap") or []),
                expected_contribution=str(raw.get("expected_contribution") or "A small, falsifiable method or evaluation contribution."),
                insight=str(
                    raw.get("insight")
                    or "The useful part of the idea is the explicit link between principle lineage and a measurable first signal."
                ),
                mechanism_design=self._list(
                    raw.get("mechanism_design"),
                    [
                        "Identify the weakest assumption in the source principles.",
                        "Turn that assumption into a measurable module or evaluation split.",
                        "Compare against the simplest fair baseline before adding complexity.",
                    ],
                ),
                why_it_might_work=self._list(
                    raw.get("why_it_might_work"),
                    [
                        "The selected principles address the same abstract pressure as the user goal.",
                        "The validation path checks the principle before requiring a large build.",
                    ],
                ),
                minimal_experiment=str(
                    raw.get("minimal_experiment")
                    or "Compare baseline vs candidate on a synthetic or small public task and save metrics to JSONL."
                ),
                validation_protocol=self._list(
                    raw.get("validation_protocol"),
                    [
                        "Run a smoke test on a tiny split.",
                        "Run a stratified comparison against at least one fair baseline.",
                        "Export metrics, qualitative failures, and a Principia feedback object.",
                    ],
                ),
                baselines=self._list(raw.get("baselines"), ["direct baseline", "retrieval or prompting baseline"]),
                metrics=self._list(
                    raw.get("metrics"),
                    goal.get("success_metrics") or ["task success at fixed budget", "runtime cost"],
                ),
                failure_modes=self._list(
                    raw.get("failure_modes"),
                    [
                        "The apparent gain comes from an unfair baseline.",
                        "The small validation split misses the real failure mode.",
                    ],
                ),
                ranking_scores=dict(
                    raw.get("ranking_scores")
                    or self._ranking_scores(source_ids, principles, estimate)
                ),
                result_estimate_id=estimate["estimate_id"],
                codex_prompt_plan_id=plan["prompt_plan_id"],
                feedback_status="unvalidated",
            )
            idea_dict = to_dict(idea)
            idea_dict["conceptual_takeaway"] = compact_text(
                str(
                    raw.get("conceptual_takeaway")
                    or raw.get("sharp_reframing")
                    or raw.get("insight")
                    or idea_dict["insight"]
                ),
                360,
            )
            idea_dict["sharp_reframing"] = compact_text(
                str(
                    raw.get("sharp_reframing")
                    or raw.get("conceptual_takeaway")
                    or idea_dict["one_sentence_thesis"]
                ),
                360,
            )
            similar_work_ids: list[str] = []
            for principle in principles:
                if principle.get("principle_id") not in source_ids:
                    continue
                for wid in principle.get("source_works", []):
                    if wid not in similar_work_ids:
                        similar_work_ids.append(wid)
            for fact in [*insight_sources, *novelty_sources]:
                wid = fact.get("work_id", "")
                if wid and wid not in similar_work_ids:
                    similar_work_ids.append(wid)
            idea_dict["similar_work_ids"] = similar_work_ids[:6]
            idea_dict["source_insights"] = insight_sources
            idea_dict["source_novelty"] = novelty_sources
            idea_dict["composition_trace"] = {
                "principles": source_ids,
                "insights": [item["fact_id"] for item in insight_sources],
                "novelty": [item["fact_id"] for item in novelty_sources],
                "rationale": (
                    "Idea synthesis treats reusable principles, empirical insights, and concrete novelty claims "
                    "as independent evidence streams that may originate from different works."
                ),
            }
            idea_dict["source_principle_names"] = [
                principle.get("name", principle["principle_id"])
                for principle in principles
                if principle.get("principle_id") in source_ids
            ]
            ideas.append(idea_dict)
            estimates.append(estimate)
            plans.append(plan)
            if max_ideas and len(ideas) >= max_ideas:
                break
        return ideas, estimates, plans

    def _normalize_estimate(
        self,
        idea_id: str,
        raw: dict[str, Any],
        source_principles: list[str],
    ) -> dict[str, Any]:
        mean = float(raw.get("mean", raw.get("expected_change", 2.0)))
        useful = clamp(float(raw.get("probability_useful_signal", 0.58)), 0.05, 0.95)
        negative = clamp(float(raw.get("probability_negative_result", 0.24)), 0.02, 0.9)
        failure = clamp(float(raw.get("probability_implementation_failure", 0.18)), 0.02, 0.8)
        estimate = ResultEstimate(
            estimate_id=stable_id("E", idea_id),
            idea_id=idea_id,
            primary_metric=str(raw.get("primary_metric") or "task success at fixed budget"),
            mean=round(mean, 2),
            lower_90=round(float(raw.get("lower_90", mean - 3.2)), 2),
            upper_90=round(float(raw.get("upper_90", mean + 4.1)), 2),
            probability_useful_signal=round(useful, 2),
            probability_negative_result=round(negative, 2),
            probability_implementation_failure=round(failure, 2),
            compute_cost_estimate=str(raw.get("compute_cost_estimate") or "API-only smoke test, then optional 2-6 GPU-hour small run"),
            time_to_first_signal=str(raw.get("time_to_first_signal") or "2-4 hours"),
            key_risks=self._list(
                raw.get("key_risks"),
                [
                    "Baseline may be stronger than assumed.",
                    "Small benchmark may not expose the target pressure.",
                    "Implementation overhead may erase gains.",
                ],
            ),
            cheapest_falsification=str(
                raw.get("cheapest_falsification")
                or "Run the smallest stratified baseline-vs-candidate comparison and inspect qualitative failures."
            ),
            evidence_basis=self._list(
                raw.get("evidence_basis"),
                [
                    "source principle confidence",
                    "validation level of related works",
                    "implementation complexity estimate",
                ],
            ),
            calibration_basis={
                "similar_ideas": [],
                "similar_principles": source_principles,
                "historical_runs": [],
            },
        )
        return to_dict(estimate)

    def _build_prompt_plan(
        self,
        idea_id: str,
        title: str,
        raw: dict[str, Any],
        goal: dict[str, Any],
        principles: list[dict[str, Any]],
        estimate: dict[str, Any],
    ) -> dict[str, Any]:
        slug = slugify(title)
        thesis = str(raw.get("one_sentence_thesis") or raw.get("thesis") or title)
        mechanism_design = self._list(raw.get("mechanism_design"), [])
        validation_protocol = self._list(raw.get("validation_protocol"), [])
        metric = estimate["primary_metric"]
        budget = goal.get("constraints", {}).get("compute_budget", "API-only or one day local")
        horizon = goal.get("constraints", {}).get("timeline", "1 day")
        source_ids = set(raw.get("source_principles") or [])
        trace = "\n".join(
            f"- {p['name']}: {p['mechanism']}" for p in principles if p["principle_id"] in source_ids
        ) or "- Principle lineage available in PRINCIPLE_TRACE.json"
        prompts = [
            PromptStep(
                step_id="P0",
                objective="Repository orientation",
                prompt_text=(
                    "You are validating a research idea exported from Principia.\n"
                    "Read the repository and produce a concise orientation report. Do not edit files yet.\n\n"
                    f"Idea title: {title}\nCore hypothesis: {thesis}\nTarget metric: {metric}\n"
                    f"Compute budget: {budget}\nValidation horizon: {horizon}\n\n"
                    "Tasks:\n1. Identify project structure.\n2. Identify where experiments and tests should live.\n"
                    "3. Identify the closest baseline.\n4. List the smallest runnable validation path.\n"
                    "5. List risks, missing dependencies, and assumptions."
                ),
                expected_outputs=["repo map", "minimal validation plan", "commands to run"],
                acceptance_checks=["No files edited", "Validation path fits the stated budget"],
            ),
            PromptStep(
                step_id="P1",
                objective="Create experiment contract",
                prompt_text=(
                    f"Create experiments/{slug}/EXPERIMENT_CONTRACT.md for this Principia idea.\n\n"
                    f"Idea: {title}\nThesis: {thesis}\nPrinciple lineage:\n{trace}\n\n"
                    f"Mechanism design:\n{self._bullet_text(mechanism_design)}\n\n"
                    f"Validation protocol:\n{self._bullet_text(validation_protocol)}\n\n"
                    "The contract must include hypothesis, baselines, candidate method, dataset or synthetic task, "
                    "metrics, compute budget, success criteria, failure criteria, ablations, and commands."
                ),
                expected_outputs=["EXPERIMENT_CONTRACT.md"],
                acceptance_checks=["Baseline is fair", "Success and failure criteria are measurable"],
            ),
            PromptStep(
                step_id="P2",
                objective="Implement minimal baseline",
                prompt_text=(
                    "Implement the minimal baseline from the experiment contract. Keep it small. "
                    "Add a smoke test, configurable seed, and metrics saved to JSONL or CSV. "
                    "Run the smoke test and report command, runtime, metric output, and failures."
                ),
                expected_outputs=["baseline code", "config", "smoke test", "metric file"],
                acceptance_checks=["Smoke test runs quickly", "Metrics are persisted"],
            ),
            PromptStep(
                step_id="P3",
                objective="Implement candidate method",
                prompt_text=(
                    f"Implement the candidate method for {title}.\n\nPrinciple lineage:\n{trace}\n\n"
                    "Change the smallest number of files necessary. Preserve the baseline path. "
                    "Add a config flag to switch baseline vs candidate. Avoid hidden changes that make the baseline unfair."
                ),
                expected_outputs=["candidate implementation", "config switch", "updated smoke test"],
                acceptance_checks=["Baseline and candidate both run", "Only intended files changed"],
            ),
            PromptStep(
                step_id="P4",
                objective="Analyze and export feedback",
                prompt_text=(
                    "Run the smallest fair comparison, analyze results, and write PRINCIPIA_FEEDBACK.json with: "
                    "idea_id, outcome_label, metric_delta_observed, runtime_cost, failure_modes, strengthened_principles, "
                    "weakened_principles, notes, and commands_used."
                ),
                expected_outputs=["result summary", "PRINCIPIA_FEEDBACK.json"],
                acceptance_checks=["Reports negative results honestly", "Feedback schema is valid JSON"],
            ),
        ]
        plan = PromptPlan(
            prompt_plan_id=stable_id("PP", idea_id),
            idea_id=idea_id,
            target_agent="codex",
            repo_assumptions=[
                "The target repository can run Python or shell-based smoke tests.",
                "A small synthetic or public benchmark can be added without large downloads.",
            ],
            prompts=prompts,
            feedback_export_schema=(
                "{\"idea_id\":\"string\",\"outcome_label\":\"supported|contradicted|inconclusive\","
                "\"metric_delta_observed\":\"string\",\"runtime_cost\":\"string\",\"notes\":\"string\"}"
            ),
        )
        return to_dict(plan)

    def _bullet_text(self, items: list[str]) -> str:
        return "\n".join(f"- {item}" for item in items) if items else "- Fill from the Idea Card."

    def _ranking_scores(
        self,
        source_ids: list[str],
        principles: list[dict[str, Any]],
        estimate: dict[str, Any],
    ) -> dict[str, float]:
        selected = [p for p in principles if p.get("principle_id") in set(source_ids)]
        principle_confidence = (
            sum(float(p.get("confidence_score", 0.4)) for p in selected) / max(len(selected), 1)
        )
        useful = float(estimate.get("probability_useful_signal", 0.5))
        failure = float(estimate.get("probability_implementation_failure", 0.25))
        return {
            "goal_relevance": round(0.74 + 0.08 * min(len(selected), 3), 2),
            "novelty": 0.68,
            "principle_confidence": round(principle_confidence, 2),
            "testability": 0.82,
            "feasibility": round(0.86 - failure * 0.35, 2),
            "expected_signal": round(useful, 2),
        }

    def _is_time_series_goal(self, goal: dict[str, Any], principle: dict[str, Any]) -> bool:
        return self._goal_flags(goal)["time_series"]

    def _is_mas_goal(self, goal: dict[str, Any]) -> bool:
        flags = self._goal_flags(goal)
        return flags["mas"] or flags["symbolic"] or flags["dialect"]

    def _is_vision_ttt_goal(self, goal: dict[str, Any]) -> bool:
        return self._goal_flags(goal)["vision_ttt"]

    def _time_series_idea_templates(
        self,
        domain: str,
        first: dict[str, Any],
        second: dict[str, Any],
    ) -> list[dict[str, Any]]:
        metrics = [
            "RMSE / MAE on remaining useful life",
            "early-life vs late-life error stratification",
            "calibration error for uncertainty intervals",
            "missing-sensor robustness and inference latency",
        ]
        baselines = [
            "TimesFM frozen features plus MLP regression head",
            "raw sensor Transformer without TimesFM features",
            "LSTM/TCN RUL baseline under the same train/test split",
            "cross-sensor Transformer without the proposed gate or adapter",
        ]
        return [
            {
                "title": "Reliability-Gated TimesFM Sensor Fusion for RUL",
                "thesis": (
                    "Use TimesFM as a frozen temporal feature bank, but route each sensor token through a reliability gate before "
                    "cross-sensor attention so noisy or weakly aligned sensors cannot dominate RUL prediction."
                ),
                "operator_explanation": (
                    f"Use '{first['name']}' as the reusable gating principle and '{second['name']}' as the fusion constraint."
                ),
                "novelty_claim": (
                    "The novelty is the reliability gate between foundation-model time features and cross-sensor fusion, rather than simply stacking a Transformer after TimesFM."
                ),
                "expected_contribution": "A modular RUL architecture that separates temporal representation quality from sensor-level trust.",
                "insight": (
                    "TimesFM can provide strong generic temporal embeddings, but RUL errors often come from sensor-specific drift, missingness, and operating-regime mismatch."
                ),
                "mechanism_design": [
                    "Encode each sensor window with TimesFM and project it into a shared sensor-token space.",
                    "Estimate a reliability score from missingness, local variance, reconstruction residual, and sensor agreement.",
                    "Multiply attention keys/values by reliability scores before the cross-sensor Transformer.",
                    "Attach a regression head that predicts both RUL mean and uncertainty.",
                ],
                "why_it_might_work": [
                    "It prevents a high-capacity fusion Transformer from over-trusting corrupted sensor channels.",
                    "The gate gives a direct diagnostic object for failure analysis.",
                    "It can be ablated cleanly without changing the TimesFM feature extractor.",
                ],
                "minimal_experiment": (
                    "Run frozen TimesFM+MLP, TimesFM+Transformer, and reliability-gated TimesFM+Transformer on one public RUL split."
                ),
                "validation_protocol": [
                    "Evaluate normal, missing-sensor, and noisy-sensor test subsets.",
                    "Plot reliability scores against sensor corruption and degradation stage.",
                    "Ablate each reliability feature.",
                    "Check whether uncertainty intervals widen on unreliable sensors.",
                ],
                "baselines": baselines,
                "metrics": metrics,
                "failure_modes": [
                    "Reliability scores may suppress weak but early-warning sensors.",
                    "TimesFM features may not align with industrial sensor sampling rates.",
                    "The gate can become a shortcut for operating condition labels.",
                ],
                "ranking_scores": {
                    "goal_relevance": 0.93,
                    "novelty": 0.76,
                    "principle_confidence": 0.45,
                    "testability": 0.88,
                    "feasibility": 0.82,
                    "expected_signal": 0.64,
                },
            },
            {
                "title": "Degradation-Stage Tokens for Cross-Sensor RUL Attention",
                "thesis": (
                    "Introduce learned degradation-stage tokens that attend to TimesFM sensor features and force the fusion Transformer "
                    "to organize evidence by health phase rather than by raw time index alone."
                ),
                "operator_explanation": (
                    "Invert the usual sensor-first fusion pipeline: first infer degradation phase, then let phase tokens query sensor evidence."
                ),
                "novelty_claim": "The method makes degradation stage an explicit intermediate representation with its own ablations and diagnostics.",
                "expected_contribution": "A stage-aware RUL predictor that can explain which phase-specific evidence drives the prediction.",
                "insight": "RUL prediction is not only forecasting; it is phase recognition plus residual lifetime regression under changing sensor relevance.",
                "mechanism_design": [
                    "Extract TimesFM embeddings for each sensor and temporal window.",
                    "Add K degradation-stage query tokens initialized by simple health-index prototypes.",
                    "Let stage tokens cross-attend to sensor tokens, then pool stage tokens into a RUL head.",
                    "Regularize stage-token ordering with a monotonic or ordinal loss when labels permit.",
                ],
                "why_it_might_work": [
                    "It gives the Transformer a bottleneck aligned with the physical degradation process.",
                    "It can reduce overfitting to absolute time or operating condition.",
                    "It produces interpretable phase-level attention maps.",
                ],
                "minimal_experiment": "Compare no-stage-token, learned-stage-token, and monotonic-stage-token variants on the same RUL split.",
                "validation_protocol": [
                    "Report error by early/mid/late degradation phase.",
                    "Visualize stage-token trajectories over time.",
                    "Run an oracle phase-label sanity check if phase annotations or heuristics exist.",
                    "Test whether stage tokens remain stable under sensor dropout.",
                ],
                "baselines": baselines,
                "metrics": metrics,
                "failure_modes": [
                    "Stage tokens may collapse to redundant attention heads.",
                    "Monotonic constraints may be wrong under maintenance resets.",
                    "Phase heuristics may leak label information.",
                ],
                "ranking_scores": {
                    "goal_relevance": 0.9,
                    "novelty": 0.78,
                    "principle_confidence": 0.44,
                    "testability": 0.84,
                    "feasibility": 0.78,
                    "expected_signal": 0.61,
                },
            },
            {
                "title": "Residual RUL Corrector on Top of Frozen TimesFM Features",
                "thesis": (
                    "Treat TimesFM as a generic temporal prior and train the fusion Transformer only to predict the residual error "
                    "left by a simple per-sensor RUL head."
                ),
                "operator_explanation": "Compose a strong generic feature extractor with a residual-learning principle to keep the trainable module small.",
                "novelty_claim": "The idea separates base temporal competence from cross-sensor correction, making the contribution easier to attribute.",
                "expected_contribution": "A low-risk RUL method that improves interpretability and reduces overfitting on small prognostics datasets.",
                "insight": "If TimesFM already captures common trends, the useful learnable signal may be the residual caused by sensor interactions and operating regimes.",
                "mechanism_design": [
                    "Train a simple per-sensor TimesFM+linear RUL predictor.",
                    "Compute residual targets and feed TimesFM embeddings plus baseline predictions to a cross-sensor Transformer.",
                    "Predict a bounded residual correction and add it to the base RUL estimate.",
                    "Constrain correction magnitude with a calibration-aware penalty.",
                ],
                "why_it_might_work": [
                    "The fusion model focuses on interactions instead of relearning temporal features.",
                    "Residual magnitude provides a built-in overfitting warning.",
                    "It supports a very clear baseline comparison.",
                ],
                "minimal_experiment": "Measure base TimesFM error, residual-corrected error, and an unconstrained direct Transformer on the same split.",
                "validation_protocol": [
                    "Plot residual correction vs true baseline error.",
                    "Check whether corrections are larger near failure onset.",
                    "Ablate correction clipping and calibration penalty.",
                    "Evaluate across operating conditions.",
                ],
                "baselines": baselines,
                "metrics": metrics,
                "failure_modes": [
                    "Base TimesFM predictor may be too weak, leaving residuals too hard.",
                    "Residual head may learn label leakage from split artifacts.",
                    "Correction clipping may underfit late-stage degradation.",
                ],
                "ranking_scores": {
                    "goal_relevance": 0.88,
                    "novelty": 0.72,
                    "principle_confidence": 0.43,
                    "testability": 0.9,
                    "feasibility": 0.86,
                    "expected_signal": 0.6,
                },
            },
            {
                "title": "Sensor-Agreement Contrastive Adapter for TimesFM",
                "thesis": (
                    "Add a lightweight adapter after TimesFM and train it with contrastive objectives that pull together sensors "
                    "that agree on degradation state while pushing apart misleading correlations."
                ),
                "operator_explanation": "Use representation-alignment as the bridge between generic time-series features and prognostic sensor fusion.",
                "novelty_claim": "The adapter learns cross-sensor agreement before the RUL head, instead of relying on the final regression loss to discover it.",
                "expected_contribution": "A pre-fusion adaptation objective for small-data RUL settings.",
                "insight": "Cross-sensor fusion fails when sensors are merely correlated by operating condition rather than degradation mechanism.",
                "mechanism_design": [
                    "Freeze TimesFM and train small LoRA/MLP adapters per sensor or sensor group.",
                    "Build positive pairs from nearby windows with consistent health indicators and negative pairs from mismatched degradation stages.",
                    "Feed adapted embeddings into a cross-sensor Transformer.",
                    "Jointly optimize contrastive alignment and RUL regression after a warmup phase.",
                ],
                "why_it_might_work": [
                    "It shapes the embedding space before supervised labels become scarce.",
                    "It can reduce spurious operating-condition correlations.",
                    "Adapter parameters keep compute and memory manageable.",
                ],
                "minimal_experiment": "Compare frozen TimesFM, supervised adapter, and contrastive adapter before the same fusion Transformer.",
                "validation_protocol": [
                    "Evaluate nearest-neighbor degradation consistency in embedding space.",
                    "Run operating-condition holdout tests.",
                    "Ablate positive-pair construction.",
                    "Report adapter parameter count and latency.",
                ],
                "baselines": baselines,
                "metrics": metrics,
                "failure_modes": [
                    "Positive/negative pair heuristics may be noisy.",
                    "Contrastive loss may remove useful operating-condition information.",
                    "Adapters may overfit if sensor groups are too fine-grained.",
                ],
                "ranking_scores": {
                    "goal_relevance": 0.87,
                    "novelty": 0.8,
                    "principle_confidence": 0.42,
                    "testability": 0.82,
                    "feasibility": 0.76,
                    "expected_signal": 0.59,
                },
            },
            {
                "title": "Missing-Sensor Consistency Distillation for RUL Fusion",
                "thesis": (
                    "Train the full-sensor TimesFM fusion model as a teacher and distill consistent RUL predictions into students "
                    "that observe randomly dropped sensor subsets."
                ),
                "operator_explanation": "Transplant robustness validation into training by making missing-sensor behavior a first-class objective.",
                "novelty_claim": "The idea treats sensor dropout as a structured distillation problem rather than only as augmentation.",
                "expected_contribution": "A deployment-oriented RUL model that remains stable under sensor loss or communication gaps.",
                "insight": "Industrial RUL systems often fail in deployment because the model assumes all sensors are reliable and present.",
                "mechanism_design": [
                    "Train a teacher with all TimesFM sensor features and the fusion Transformer.",
                    "Sample sensor subsets and train a shared student to match teacher RUL distribution plus ground truth.",
                    "Add consistency loss between overlapping subset predictions.",
                    "Use uncertainty inflation when critical sensors are absent.",
                ],
                "why_it_might_work": [
                    "It exposes the model to realistic sensor availability patterns.",
                    "Teacher distribution carries richer information than point labels.",
                    "It gives a direct robustness metric for deployment.",
                ],
                "minimal_experiment": "Evaluate full-sensor, random-dropout training, and consistency-distilled models under synthetic sensor dropout.",
                "validation_protocol": [
                    "Report RUL error for 0%, 20%, 40%, and targeted sensor dropout.",
                    "Check whether uncertainty increases as sensors disappear.",
                    "Ablate teacher soft targets vs subset consistency.",
                    "Measure inference overhead.",
                ],
                "baselines": baselines,
                "metrics": metrics,
                "failure_modes": [
                    "Teacher mistakes can be amplified.",
                    "Random dropout may not match real sensor failures.",
                    "Student may underperform full model when all sensors are present.",
                ],
                "ranking_scores": {
                    "goal_relevance": 0.86,
                    "novelty": 0.74,
                    "principle_confidence": 0.42,
                    "testability": 0.86,
                    "feasibility": 0.8,
                    "expected_signal": 0.58,
                },
            },
            {
                "title": "Monotonic Health-Index Bottleneck before RUL Regression",
                "thesis": (
                    "Force the cross-sensor Transformer to output a low-dimensional monotonic health index before the final RUL head, "
                    "making remaining-life prediction depend on an interpretable degradation bottleneck."
                ),
                "operator_explanation": "Bind mechanism composition to an invariant: health should generally degrade before predicted RUL declines.",
                "novelty_claim": "The bottleneck turns an opaque TimesFM+Transformer stack into a constrained two-step prognostics model.",
                "expected_contribution": "An interpretable RUL architecture with explicit health-index diagnostics.",
                "insight": "A direct regression head may fit dataset-specific time patterns; a health-index bottleneck can test whether the model learned degradation.",
                "mechanism_design": [
                    "Fuse TimesFM sensor embeddings with a Transformer.",
                    "Project the fused state into 2-4 health-index dimensions.",
                    "Apply monotonic or smoothness regularization over each unit trajectory.",
                    "Predict RUL from the health index plus calibrated uncertainty.",
                ],
                "why_it_might_work": [
                    "It adds a physically meaningful inductive bias without replacing TimesFM.",
                    "The bottleneck can be visualized and sanity-checked.",
                    "It reduces the regression head's chance to memorize unit identity.",
                ],
                "minimal_experiment": "Compare direct RUL head, health-index bottleneck, and bottleneck without monotonic regularization.",
                "validation_protocol": [
                    "Plot health-index curves for representative engines or devices.",
                    "Report monotonicity violations and RUL metrics.",
                    "Test cross-unit generalization.",
                    "Ablate bottleneck dimension.",
                ],
                "baselines": baselines,
                "metrics": metrics,
                "failure_modes": [
                    "True degradation can be non-monotonic after maintenance or transient recovery.",
                    "Too strict a bottleneck can erase useful sensor details.",
                    "Health-index labels may be unavailable, forcing weak regularization.",
                ],
                "ranking_scores": {
                    "goal_relevance": 0.89,
                    "novelty": 0.77,
                    "principle_confidence": 0.43,
                    "testability": 0.87,
                    "feasibility": 0.79,
                    "expected_signal": 0.6,
                },
            },
            {
                "title": "Multi-Horizon RUL Head with Degradation-Rate Calibration",
                "thesis": (
                    "Replace the single regression head with a multi-horizon head that predicts near-term degradation rate, medium-term health trend, "
                    "and final RUL, then calibrates consistency among them."
                ),
                "operator_explanation": "Use evaluator binding to make the output head test several mechanistic predictions, not only final RUL.",
                "novelty_claim": "The output layer becomes a structured prognostic contract with internal consistency checks.",
                "expected_contribution": "A richer RUL head that can reveal when TimesFM+fusion features know short-term trends but fail long-term life estimation.",
                "insight": "RUL labels are sparse and noisy; auxiliary degradation-rate targets can create denser learning signals.",
                "mechanism_design": [
                    "Use fused TimesFM sensor embeddings as shared state.",
                    "Predict short-horizon degradation deltas, medium-horizon health trend, and final RUL.",
                    "Add consistency constraints between predicted deltas and RUL decrease.",
                    "Use uncertainty weighting to balance auxiliary losses.",
                ],
                "why_it_might_work": [
                    "Auxiliary horizons regularize the final RUL predictor.",
                    "Consistency errors expose when the model is making implausible forecasts.",
                    "The head can be tested independently of the feature extractor.",
                ],
                "minimal_experiment": "Compare single-head RUL, auxiliary multi-task head, and consistency-calibrated multi-horizon head.",
                "validation_protocol": [
                    "Report final RUL metrics and auxiliary horizon errors.",
                    "Check consistency between predicted degradation rate and RUL trajectory.",
                    "Ablate each auxiliary horizon.",
                    "Evaluate early-warning performance near failure onset.",
                ],
                "baselines": baselines,
                "metrics": metrics,
                "failure_modes": [
                    "Auxiliary labels may be noisy derivatives of RUL.",
                    "Multi-task loss can distract from final prediction.",
                    "Consistency constraints may be violated by nonstationary operating regimes.",
                ],
                "ranking_scores": {
                    "goal_relevance": 0.86,
                    "novelty": 0.73,
                    "principle_confidence": 0.42,
                    "testability": 0.88,
                    "feasibility": 0.83,
                    "expected_signal": 0.57,
                },
            },
            {
                "title": "Failure-Mode Evaluator for TimesFM RUL Fusion",
                "thesis": (
                    "Before changing the architecture, build a failure-mode evaluator that clusters errors by degradation phase, sensor missingness, "
                    "operating condition, and horizon length, then uses those clusters to choose the next fusion intervention."
                ),
                "operator_explanation": "Make the validation principle independent from the method principle, so the evaluator can select among competing designs.",
                "novelty_claim": "The evaluator becomes a method-selection layer for TimesFM-based RUL design rather than a passive report after training.",
                "expected_contribution": "A diagnostic harness plus a selected architecture variant grounded in observed failure structure.",
                "insight": "The best next module depends on which failure family dominates; otherwise model complexity is added blindly.",
                "mechanism_design": [
                    "Run the baseline TimesFM+Transformer+regression pipeline.",
                    "Tag errors by phase, operating condition, sensor dropout, and RUL horizon.",
                    "Map each failure cluster to candidate interventions such as reliability gating, stage tokens, or residual correction.",
                    "Implement the highest-yield intervention and re-run the frozen evaluator.",
                ],
                "why_it_might_work": [
                    "It prevents premature architecture tuning.",
                    "It produces actionable evidence even if the first method variant fails.",
                    "It aligns method design with measurable failure modes.",
                ],
                "minimal_experiment": "Build the evaluator on one train/test split, choose one intervention, and report per-cluster deltas.",
                "validation_protocol": [
                    "Freeze cluster definitions before implementing the intervention.",
                    "Report aggregate and per-cluster metrics.",
                    "Check if the intervention helps its target cluster without hurting others.",
                    "Export failure examples for future principle updates.",
                ],
                "baselines": baselines,
                "metrics": metrics,
                "failure_modes": [
                    "Failure clusters may be too coarse to guide design.",
                    "The selected intervention may overfit the evaluator split.",
                    "Diagnostic overhead may delay method implementation.",
                ],
                "ranking_scores": {
                    "goal_relevance": 0.84,
                    "novelty": 0.71,
                    "principle_confidence": 0.44,
                    "testability": 0.92,
                    "feasibility": 0.88,
                    "expected_signal": 0.59,
                },
            },
        ]

    def _reconstruction_idea_templates(
        self,
        domain: str,
        first: dict[str, Any],
        second: dict[str, Any],
    ) -> list[dict[str, Any]]:
        metrics = [
            "PSNR / SSIM / LPIPS on held-out views",
            "depth or geometry consistency proxy",
            "view-count robustness curve",
            "training time and memory",
        ]
        baselines = [
            "plain 3D Gaussian Splatting or NeRF on the same sparse views",
            "regularized sparse-view baseline such as RegNeRF-style consistency",
            "source-work baseline if code is available",
        ]
        return [
            {
                "title": "Uncertainty-Gated Prior Injection for Sparse-View 3D Reconstruction",
                "thesis": (
                    "Inject generative or geometry priors only in rays and regions where sparse-view evidence is uncertain, "
                    "so priors fill missing structure without dominating observed geometry."
                ),
                "operator_explanation": (
                    f"Compose '{first['name']}' with '{second['name']}' by using principle confidence as a gate for where priors may act."
                ),
                "novelty_claim": (
                    "Many sparse-view methods apply priors globally; this idea makes prior strength conditional on cross-view uncertainty."
                ),
                "expected_contribution": "A lightweight uncertainty-gated regularizer for sparse-view reconstruction.",
                "insight": (
                    "Sparse-view failure is uneven across a scene. Treating all regions as equally underconstrained wastes prior capacity "
                    "and increases hallucination risk."
                ),
                "mechanism_design": [
                    "Estimate per-ray or per-Gaussian uncertainty from reprojection disagreement, opacity entropy, or view coverage.",
                    "Apply stronger generative/geometry prior only to high-uncertainty regions.",
                    "Freeze or weakly regularize high-confidence observed regions to preserve measured geometry.",
                    "Anneal the prior weight as new pseudo-views become self-consistent.",
                ],
                "why_it_might_work": [
                    "It directly targets the sparse observation pressure captured by the source principles.",
                    "It reduces hallucination by separating observed geometry from uncertain missing regions.",
                    "It can be tested by adding a small confidence-weighted loss to an existing baseline.",
                ],
                "minimal_experiment": (
                    "Run 3/6/9-view splits on one small scene set; compare global-prior, no-prior, and uncertainty-gated-prior variants."
                ),
                "validation_protocol": [
                    "Use identical sparse-view splits for all baselines.",
                    "Report PSNR/SSIM/LPIPS and a consistency or depth proxy.",
                    "Visualize high-uncertainty regions before and after prior injection.",
                    "Inspect whether gains come from real geometry or hallucinated texture.",
                ],
                "baselines": baselines,
                "metrics": metrics,
                "failure_modes": [
                    "Uncertainty estimate is miscalibrated and suppresses useful priors.",
                    "Prior still hallucinates plausible but wrong backsides.",
                    "View coverage proxy overfits to object-centric scenes.",
                ],
                "ranking_scores": {
                    "goal_relevance": 0.92,
                    "novelty": 0.78,
                    "principle_confidence": 0.42,
                    "testability": 0.86,
                    "feasibility": 0.82,
                    "expected_signal": 0.62,
                },
            },
            {
                "title": "Cycle-Consistent Pseudo-View Curriculum for Sparse-View Reconstruction",
                "thesis": (
                    "Generate pseudo-views gradually, but accept them only when they pass cycle consistency back to observed sparse views."
                ),
                "operator_explanation": (
                    "Use principle transfer from self-augmentation and cross-view alignment: generated views become training data only after a consistency check."
                ),
                "novelty_claim": (
                    "The idea turns pseudo-view augmentation into a curriculum with explicit reject/accept tests, rather than a one-shot augmentation step."
                ),
                "expected_contribution": "A practical augmentation curriculum that is less likely to poison sparse-view training.",
                "insight": (
                    "Pseudo-views are useful only when they reduce ambiguity faster than they inject errors; acceptance should be earned by geometry checks."
                ),
                "mechanism_design": [
                    "Train an initial reconstruction from sparse real views.",
                    "Render candidate pseudo-views and enhance or complete them with a prior model.",
                    "Project pseudo-view evidence back to observed views and score cycle consistency.",
                    "Add only the accepted pseudo-views, starting with near-observed views before harder extrapolations.",
                ],
                "why_it_might_work": [
                    "It keeps the benefit of self-augmentation while adding a principled filter.",
                    "The curriculum makes early training stable before pushing to severely unseen regions.",
                ],
                "minimal_experiment": (
                    "Compare no pseudo-views, all pseudo-views, and cycle-filtered pseudo-views on a small sparse-view benchmark."
                ),
                "validation_protocol": [
                    "Use the same pseudo-view generator across variants.",
                    "Track accepted pseudo-view ratio over training.",
                    "Report held-out view quality and qualitative geometry failures.",
                    "Ablate the cycle-consistency threshold.",
                ],
                "baselines": baselines,
                "metrics": metrics,
                "failure_modes": [
                    "Cycle score rewards texture consistency but misses geometry errors.",
                    "Too strict a threshold prevents useful augmentation.",
                    "Pseudo-view generator has domain bias.",
                ],
                "ranking_scores": {
                    "goal_relevance": 0.9,
                    "novelty": 0.74,
                    "principle_confidence": 0.42,
                    "testability": 0.84,
                    "feasibility": 0.8,
                    "expected_signal": 0.6,
                },
            },
            {
                "title": "Plane-and-Depth Anchored Gaussian Initialization for Few-View Scenes",
                "thesis": (
                    "Initialize 3D Gaussians from sparse planes and relative depth anchors before appearance optimization, reducing pose ambiguity and floaters."
                ),
                "operator_explanation": (
                    "Resolve the correspondence scarcity contradiction by importing the one-plane pose-hypothesis principle into Gaussian initialization."
                ),
                "novelty_claim": (
                    "Instead of treating sparse-view reconstruction as only a rendering optimization problem, the idea makes structural anchors the first-class initialization object."
                ),
                "expected_contribution": "A stronger initialization recipe for sparse-view 3DGS or NeRF-style reconstruction.",
                "insight": (
                    "Many sparse-view failures begin before training converges: bad initial geometry creates local minima that later priors cannot fully repair."
                ),
                "mechanism_design": [
                    "Detect sparse planes or depth-order anchors from input views.",
                    "Generate a small set of pose/plane hypotheses and score them by reprojection consistency.",
                    "Seed Gaussians or density fields around the best structural anchors.",
                    "Regularize early training to preserve anchor geometry, then relax constraints.",
                ],
                "why_it_might_work": [
                    "It attacks pose and correspondence ambiguity before appearance losses dominate.",
                    "It can be evaluated as an initialization change without redesigning the full renderer.",
                ],
                "minimal_experiment": (
                    "Run baseline initialization vs anchor initialization on two-view or three-view scenes with severe viewpoint changes."
                ),
                "validation_protocol": [
                    "Use fixed optimizer settings for baseline and candidate.",
                    "Evaluate early-iteration convergence and final held-out quality.",
                    "Report cases where anchors hurt due to wrong plane detection.",
                ],
                "baselines": baselines,
                "metrics": metrics,
                "failure_modes": [
                    "Plane detector fails on non-planar scenes.",
                    "Wrong anchors bias optimization toward incorrect geometry.",
                    "Benefits disappear when camera poses are already accurate.",
                ],
                "ranking_scores": {
                    "goal_relevance": 0.88,
                    "novelty": 0.72,
                    "principle_confidence": 0.42,
                    "testability": 0.88,
                    "feasibility": 0.78,
                    "expected_signal": 0.58,
                },
            },
        ]

    def _mas_idea_templates(
        self,
        domain: str,
        first: dict[str, Any],
        second: dict[str, Any],
    ) -> list[dict[str, Any]]:
        metrics = [
            "answer accuracy at fixed token budget",
            "irreducible-crux rate",
            "symbolic description length of accepted hypotheses",
            "cost per resolved disagreement",
        ]
        templates = [
            {
                "title": "Symbolic Compactness Reward Market",
                "thesis": (
                    f"Turn {domain} into a market where agents are rewarded for compressing a hypothesis into fewer symbols "
                    "only when the compressed form preserves testable consequences."
                ),
                "operator_explanation": (
                    f"Use '{first['name']}' as the compression pressure and '{second['name']}' as the guardrail against empty terseness."
                ),
                "novelty_claim": (
                    "The reward is not brevity; it is consequence-preserving compression, so symbolic compactness becomes a proxy for law-like structure."
                ),
                "expected_contribution": (
                    "A MAS reward design that makes agents prefer concise, reusable scientific explanations over verbose plausible narratives."
                ),
                "insight": (
                    "In scientific discovery, the deepest ideas often become short because they have found the right abstraction, not because they omitted detail."
                ),
                "conceptual_takeaway": (
                    "Reward agents for making theories smaller only when the theory keeps its obligations to prediction and experiment."
                ),
                "sharp_reframing": (
                    "Compactness should be treated as conserved meaning under compression, not as shorter text."
                ),
                "mechanism_design": [
                    "Represent each candidate hypothesis as a symbolic claim graph with variables, relations, and predicted observables.",
                    "Score an agent by the reduction in graph description length after another agent successfully reconstructs the predictions.",
                    "Penalize compression that removes falsifiable commitments or hides unresolved assumptions.",
                    "Let a critic agent search for the shortest counterexample that breaks the compressed claim graph.",
                ],
                "why_it_might_work": [
                    "It aligns MAS incentives with the structure of scientific explanation: simpler when possible, explicit when necessary.",
                    "The reconstruction check prevents agents from winning by producing cryptic slogans.",
                    "The critic turns compactness into a living pressure rather than a static regularizer.",
                ],
                "minimal_experiment": (
                    "Run agents on 20 toy discovery tasks with known hidden rules; compare natural-language debate, brevity reward, and consequence-preserving compactness reward."
                ),
                "validation_protocol": [
                    "Measure whether accepted hypotheses stay predictive after symbolic compression.",
                    "Track token cost, reconstruction success, and number of unresolved assumptions.",
                    "Inspect failures where the shortest hypothesis is elegant but wrong.",
                ],
                "baselines": ["plain multi-agent debate", "brevity-only reward", "single-agent chain-of-thought"],
                "metrics": metrics,
                "failure_modes": [
                    "Agents may learn private codes that are compact but not externally interpretable.",
                    "The claim graph schema may bias the kind of discoveries agents can express.",
                    "Critic agents may over-penalize speculative but fertile hypotheses.",
                ],
                "ranking_scores": {
                    "goal_relevance": 0.9,
                    "novelty": 0.82,
                    "principle_confidence": 0.48,
                    "testability": 0.84,
                    "feasibility": 0.78,
                    "expected_signal": 0.66,
                },
            },
            {
                "title": "Dialect Contract Swarm",
                "thesis": (
                    f"Make LLM agents in {domain} communicate through compact machine dialects whose tokens have declared semantics, "
                    "audit hooks, and lossless expansion tests."
                ),
                "operator_explanation": (
                    f"Transfer '{first['name']}' into a communication contract, then use '{second['name']}' to test whether the contract preserves reasoning state."
                ),
                "novelty_claim": (
                    "The dialect is a social interface, not a prompt style: it defines what agents owe each other when they compress a reasoning move."
                ),
                "expected_contribution": (
                    "A token-efficient MAS protocol where agents exchange typed claims, cruxes, evidence handles, and uncertainty marks instead of full prose."
                ),
                "insight": (
                    "Reasoning cost falls when agents stop re-saying context and start trading accountable state changes."
                ),
                "conceptual_takeaway": (
                    "Treat inter-agent language as a protocol for obligations, not as shorter natural language."
                ),
                "sharp_reframing": (
                    "The unit of communication becomes a verifiable reasoning move, not a sentence."
                ),
                "mechanism_design": [
                    "Define a small dialect with tokens for claim, evidence, assumption, objection, crux, confidence, and requested experiment.",
                    "Require every compressed message to pass a re-expansion test by a separate translator agent.",
                    "Route natural language only when the dialect cannot express the next useful move.",
                    "Log dialect moves as a ledger so later agents can audit where accuracy was gained or lost.",
                ],
                "why_it_might_work": [
                    "It reduces repeated context while preserving the structure needed for critique.",
                    "Translator checks discourage private shorthand that other agents cannot use.",
                    "A ledger makes reasoning failures localizable to specific social moves.",
                ],
                "minimal_experiment": (
                    "Compare free-form MAS debate versus dialect-contract MAS on reasoning benchmarks with equal model calls and a hard token budget."
                ),
                "validation_protocol": [
                    "Measure accuracy, total completion tokens, and failed re-expansion events.",
                    "Ablate each dialect token family to see which social obligation matters.",
                    "Inspect whether dialect use increases decisive disagreements rather than superficial consensus.",
                ],
                "baselines": ["free-form multi-agent debate", "single-agent self-consistency", "summarize-and-pass protocol"],
                "metrics": metrics,
                "failure_modes": [
                    "The dialect may be too rigid for creative leaps.",
                    "Agents may spend tokens translating rather than reasoning.",
                    "Accuracy may improve only on tasks whose structure matches the dialect schema.",
                ],
                "ranking_scores": {
                    "goal_relevance": 0.91,
                    "novelty": 0.8,
                    "principle_confidence": 0.48,
                    "testability": 0.86,
                    "feasibility": 0.82,
                    "expected_signal": 0.68,
                },
            },
            {
                "title": "Crux Compression Society",
                "thesis": (
                    f"Organize {domain} agents so each dialogue round must compress disagreement into the smallest decisive crux: "
                    "the assumption or experiment that would change an agent's mind."
                ),
                "operator_explanation": (
                    f"Use '{first['name']}' to find what should be preserved under compression and '{second['name']}' to turn disagreement into action."
                ),
                "novelty_claim": (
                    "The MAS is optimized for discovering decisive cruxes, not for producing more arguments."
                ),
                "expected_contribution": (
                    "A social reasoning framework where agents improve accuracy by shrinking disputes into inspectable, testable pivots."
                ),
                "insight": (
                    "The value of agent interaction is not diversity by itself; it is the pressure to locate what would actually settle the disagreement."
                ),
                "conceptual_takeaway": (
                    "Good scientific dialogue compresses many words into one decisive question."
                ),
                "sharp_reframing": (
                    "Multi-agent reasoning should be measured by crux discovery per token, not debate length."
                ),
                "mechanism_design": [
                    "Give each agent a private hypothesis and force it to publish only its current crux, not its full rationale.",
                    "Let other agents attack the crux with minimal counter-evidence or propose a cheaper deciding experiment.",
                    "Reward agents when a crux eliminates multiple hypotheses or reduces future communication.",
                    "Escalate to full natural-language explanation only when crux compression stalls.",
                ],
                "why_it_might_work": [
                    "It prevents debate from becoming parallel monologues.",
                    "It turns social interaction into a search over decision boundaries.",
                    "It naturally reduces token cost by keeping only disagreement-bearing content.",
                ],
                "minimal_experiment": (
                    "Use scientific QA or synthetic hypothesis-discovery tasks; compare final accuracy and crux count under fixed token budgets."
                ),
                "validation_protocol": [
                    "Annotate whether each published crux would genuinely change a hypothesis ranking.",
                    "Measure how many hypotheses are eliminated per 1k tokens.",
                    "Check cases where agents converge too early because the crux was badly chosen.",
                ],
                "baselines": ["standard debate", "majority vote", "tree-of-thought with no crux constraint"],
                "metrics": metrics,
                "failure_modes": [
                    "Agents may choose easy cruxes that look decisive but avoid the true uncertainty.",
                    "The framework may underperform when broad exploration is needed before compression.",
                    "Crux annotations may require a reliable judge.",
                ],
                "ranking_scores": {
                    "goal_relevance": 0.88,
                    "novelty": 0.79,
                    "principle_confidence": 0.46,
                    "testability": 0.86,
                    "feasibility": 0.8,
                    "expected_signal": 0.65,
                },
            },
            {
                "title": "Token-Value Speaker Router",
                "thesis": (
                    f"In {domain}, choose the next speaking agent by expected reasoning value per token rather than by fixed debate order."
                ),
                "operator_explanation": (
                    f"Use '{first['name']}' to estimate which agent can most compress uncertainty, and '{second['name']}' to audit whether the turn was worth its cost."
                ),
                "novelty_claim": (
                    "The router treats social interaction as an economic allocation problem: each utterance must buy uncertainty reduction."
                ),
                "expected_contribution": (
                    "A MAS controller that reduces completion cost by letting agents speak only when they can change the shared belief state."
                ),
                "insight": (
                    "Many multi-agent systems waste tokens because turn-taking is polite rather than epistemically priced."
                ),
                "conceptual_takeaway": (
                    "The next agent should speak only if it can buy more insight than silence."
                ),
                "sharp_reframing": (
                    "Agent scheduling is a scientific instrument: it decides which uncertainty is worth paying to reduce."
                ),
                "mechanism_design": [
                    "Maintain a shared belief ledger containing claims, confidence, unresolved cruxes, and estimated token price.",
                    "Before each turn, ask agents for a cheap bid: what uncertainty they can reduce and at what token budget.",
                    "Allocate the turn to the highest expected value-per-token bid.",
                    "After the turn, score whether the shared ledger actually changed.",
                ],
                "why_it_might_work": [
                    "It makes token cost visible before the dialogue expands.",
                    "It rewards agents for targeted contributions rather than verbosity.",
                    "The bid ledger can reveal which roles are consistently valuable.",
                ],
                "minimal_experiment": (
                    "Compare round-robin MAS, moderator-selected MAS, and token-value routing on reasoning tasks at several token caps."
                ),
                "validation_protocol": [
                    "Track accuracy, total tokens, skipped turns, and belief-ledger delta per turn.",
                    "Ablate the bidding step and the after-turn value audit separately.",
                    "Inspect whether the router suppresses minority agents that would have found rare errors.",
                ],
                "baselines": ["round-robin debate", "fixed role pipeline", "single moderator"],
                "metrics": metrics,
                "failure_modes": [
                    "Agents may game bids by promising high value.",
                    "Low-cost turns may dominate even when expensive deep reasoning is needed.",
                    "The ledger delta may miss subtle qualitative improvements.",
                ],
                "ranking_scores": {
                    "goal_relevance": 0.86,
                    "novelty": 0.76,
                    "principle_confidence": 0.45,
                    "testability": 0.88,
                    "feasibility": 0.84,
                    "expected_signal": 0.64,
                },
            },
            {
                "title": "Public-Proof Private-Dialect MAS",
                "thesis": (
                    f"Let agents in {domain} use private compact dialects internally, but require every accepted conclusion "
                    "to be converted into a public proof object that outside agents can audit."
                ),
                "operator_explanation": (
                    f"Use '{first['name']}' to allow efficient private compression and '{second['name']}' to force public accountability."
                ),
                "novelty_claim": (
                    "The system separates the speed of private dialects from the trust requirement of public scientific explanation."
                ),
                "expected_contribution": (
                    "A MAS architecture that permits emergent shorthand without letting it become unauditable private language."
                ),
                "insight": (
                    "Private compression is useful only if the final artifact can still survive public reconstruction."
                ),
                "conceptual_takeaway": (
                    "Let agents think in shorthand, but make them publish in proof-bearing objects."
                ),
                "sharp_reframing": (
                    "The safety boundary is not whether agents use dialects; it is whether dialect outputs can be publicly re-derived."
                ),
                "mechanism_design": [
                    "Allow each agent pair to develop compact internal symbols during exploration.",
                    "Before a claim enters shared memory, require a public proof object: assumptions, evidence handles, and predicted consequences.",
                    "Use a verifier agent that has not seen the private dialogue to reconstruct the claim.",
                    "Down-rank dialects whose public reconstruction repeatedly fails.",
                ],
                "why_it_might_work": [
                    "It captures the token savings of shorthand while preserving scientific auditability.",
                    "A blind verifier detects when the dialect has become too private.",
                    "It gives an interpretable failure signal for communication protocols.",
                ],
                "minimal_experiment": (
                    "Let agent pairs solve rule-discovery tasks with private shorthand, then test whether fresh agents can verify the published proof objects."
                ),
                "validation_protocol": [
                    "Measure private-token savings, public reconstruction success, and final answer accuracy.",
                    "Compare no-private-dialect, unrestricted-private-dialect, and public-proof-gated dialect variants.",
                    "Inspect cases where private symbols become efficient but scientifically meaningless.",
                ],
                "baselines": ["fully public debate", "unrestricted private messages", "summary-only handoff"],
                "metrics": metrics,
                "failure_modes": [
                    "The public proof step may erase the token savings.",
                    "Verifier agents may be too weak to reconstruct valid compressed ideas.",
                    "Private dialects may converge to brittle task-specific codes.",
                ],
                "ranking_scores": {
                    "goal_relevance": 0.85,
                    "novelty": 0.78,
                    "principle_confidence": 0.45,
                    "testability": 0.84,
                    "feasibility": 0.8,
                    "expected_signal": 0.63,
                },
            },
            {
                "title": "Semantic Exchange-Rate Controller",
                "thesis": (
                    f"Give {domain} agents a controller that learns the exchange rate between natural language, dialect tokens, "
                    "symbols, and experiments, then chooses the cheapest representation that preserves the needed meaning."
                ),
                "operator_explanation": (
                    f"Use '{first['name']}' to price representational compactness and '{second['name']}' to test meaning preservation."
                ),
                "novelty_claim": (
                    "The controller treats representation choice as a scientific decision, not a formatting decision."
                ),
                "expected_contribution": (
                    "A dynamic communication policy that switches between prose, symbolic claims, and experiment handles by expected semantic value."
                ),
                "insight": (
                    "The same reasoning state should not always be carried in the same language; some moments need prose, others need symbols."
                ),
                "conceptual_takeaway": (
                    "Pay for the representation that preserves the next useful distinction, no more."
                ),
                "sharp_reframing": (
                    "Token efficiency is a semantic exchange-rate problem."
                ),
                "mechanism_design": [
                    "Maintain multiple encodings of the shared state: prose summary, symbolic claim graph, dialect ledger, and experiment queue.",
                    "Before each message, estimate which encoding changes the receiver's belief at lowest token cost.",
                    "Force periodic cross-encoding consistency checks.",
                    "Learn routing rules from which encoding historically resolved each type of uncertainty.",
                ],
                "why_it_might_work": [
                    "It avoids forcing every reasoning move through one brittle communication format.",
                    "It can discover when compact symbols are helpful and when they hide too much context.",
                    "It links token cost directly to belief-state change.",
                ],
                "minimal_experiment": (
                    "Run mixed-format MAS on reasoning tasks and compare fixed-prose, fixed-dialect, and adaptive representation routing."
                ),
                "validation_protocol": [
                    "Track representation chosen per turn and belief change per token.",
                    "Ablate cross-encoding consistency checks.",
                    "Inspect whether the controller overuses the cheapest format even when accuracy drops.",
                ],
                "baselines": ["all-prose MAS", "all-dialect MAS", "static summarize-then-reason protocol"],
                "metrics": metrics,
                "failure_modes": [
                    "The exchange-rate estimator may be noisy on small tasks.",
                    "Switching formats may introduce translation errors.",
                    "Agents may overfit to the learned routing policy.",
                ],
                "ranking_scores": {
                    "goal_relevance": 0.84,
                    "novelty": 0.77,
                    "principle_confidence": 0.44,
                    "testability": 0.82,
                    "feasibility": 0.78,
                    "expected_signal": 0.62,
                },
            },
            {
                "title": "Disagreement Distillation Ladder",
                "thesis": (
                    f"Make {domain} agents move every disagreement down a ladder: narrative dispute, symbolic crux, minimal experiment, "
                    "then reusable discovery rule."
                ),
                "operator_explanation": (
                    f"Use '{first['name']}' to compress disagreement and '{second['name']}' to preserve the experiment that made the compression legitimate."
                ),
                "novelty_claim": (
                    "The framework turns social interaction into a distillation process that produces reusable scientific rules, not just final answers."
                ),
                "expected_contribution": (
                    "A MAS loop that converts debate traces into compact rules for future discovery tasks."
                ),
                "insight": (
                    "A resolved disagreement is wasted if it does not leave behind a shorter rule for the next problem."
                ),
                "conceptual_takeaway": (
                    "The output of agent debate should be a reusable crux rule, not merely a consensus."
                ),
                "sharp_reframing": (
                    "Reasoning accuracy improves when disagreement is distilled into memory, not when it is simply settled."
                ),
                "mechanism_design": [
                    "Detect when two agents disagree on an assumption, variable, or experiment.",
                    "Force them to rewrite the disagreement as a symbolic crux.",
                    "Select the minimal test or evidence lookup that resolves the crux.",
                    "Store the resolved crux as a reusable rule with scope conditions.",
                ],
                "why_it_might_work": [
                    "It converts transient social reasoning into future cost reduction.",
                    "It creates a compact memory of why a conclusion was reached.",
                    "It helps agents avoid repeating the same debate on nearby problems.",
                ],
                "minimal_experiment": (
                    "Run sequential related reasoning tasks and measure whether crux-rule memory reduces token cost while preserving accuracy."
                ),
                "validation_protocol": [
                    "Compare MAS with no memory, summary memory, and crux-rule memory.",
                    "Track whether stored crux rules transfer or mislead on shifted tasks.",
                    "Measure repeated-disagreement reduction across task sequences.",
                ],
                "baselines": ["no memory", "conversation summary memory", "retrieval of full debate traces"],
                "metrics": metrics,
                "failure_modes": [
                    "Rules may overgeneralize from one disagreement.",
                    "Agents may prematurely force rich disputes into oversimplified cruxes.",
                    "Memory retrieval may dominate the cost savings.",
                ],
                "ranking_scores": {
                    "goal_relevance": 0.83,
                    "novelty": 0.75,
                    "principle_confidence": 0.44,
                    "testability": 0.84,
                    "feasibility": 0.8,
                    "expected_signal": 0.61,
                },
            },
            {
                "title": "Cost-Aware Translation Tribunal",
                "thesis": (
                    f"Use a small tribunal in {domain} where translator agents convert one agent's dialect into another's, and judges reward "
                    "translations that preserve reasoning value at the lowest token cost."
                ),
                "operator_explanation": (
                    f"Use '{first['name']}' as the source of compact dialect pressure and '{second['name']}' as the cross-agent alignment test."
                ),
                "novelty_claim": (
                    "The tribunal evaluates the communication layer itself, making dialect quality an optimizable object."
                ),
                "expected_contribution": (
                    "A way to train or select machine dialects by how well they survive translation among heterogeneous LLM agents."
                ),
                "insight": (
                    "If a dialect cannot be translated without losing the crux, it is not a social reasoning language."
                ),
                "conceptual_takeaway": (
                    "The best dialect is the one that travels between agents with the least loss per token."
                ),
                "sharp_reframing": (
                    "Machine dialects should be judged like scientific notation: compact, shared, and hard to misuse."
                ),
                "mechanism_design": [
                    "Assign agents different dialect preferences or compression budgets.",
                    "Ask translator agents to convert messages between dialects under token caps.",
                    "Use judge agents to compare translated reasoning state against the original crux and evidence.",
                    "Promote dialect rules that survive translation and demote those that lose decisive distinctions.",
                ],
                "why_it_might_work": [
                    "It directly tests whether dialects support social interaction rather than private shorthand.",
                    "It creates a measurable objective for communication quality.",
                    "It can reveal which symbols carry genuine reasoning load.",
                ],
                "minimal_experiment": (
                    "Create paired-agent reasoning tasks with hidden cruxes; compare unrestricted prose, single dialect, and tribunal-selected dialect rules."
                ),
                "validation_protocol": [
                    "Measure translation loss, final accuracy, token cost, and judge agreement.",
                    "Stress-test with agents from different model families.",
                    "Inspect high-loss symbols to refine the dialect inventory.",
                ],
                "baselines": ["direct prose handoff", "single fixed dialect", "natural-language summary translator"],
                "metrics": metrics,
                "failure_modes": [
                    "Judges may reward surface similarity rather than reasoning preservation.",
                    "Translation overhead may exceed savings on short tasks.",
                    "Dialect rules may become model-family-specific.",
                ],
                "ranking_scores": {
                    "goal_relevance": 0.82,
                    "novelty": 0.76,
                    "principle_confidence": 0.43,
                    "testability": 0.82,
                    "feasibility": 0.77,
                    "expected_signal": 0.6,
                },
            },
        ]
        lower_domain = domain.lower()
        if "dialect" in lower_domain or "token-efficient" in lower_domain or "token efficient" in lower_domain:
            order = [1, 3, 5, 7, 2, 4, 6, 0]
            return [templates[idx] for idx in order if idx < len(templates)]
        if "symbolic" in lower_domain or "compactness" in lower_domain or "scientific discovery" in lower_domain:
            order = [0, 2, 6, 1, 4, 5, 3, 7]
            return [templates[idx] for idx in order if idx < len(templates)]
        return templates

    def _vision_ttt_idea_templates(
        self,
        domain: str,
        first: dict[str, Any],
        second: dict[str, Any],
    ) -> list[dict[str, Any]]:
        metrics = [
            "mean accuracy across 1/2/4/8/16-shot settings",
            "base-to-novel gap",
            "test-time adaptation seconds per image or batch",
            "GPU hours on 4-8 RTX 4090",
            "peak memory",
            "expected calibration error",
        ]
        baselines = [
            "zero-shot CLIP",
            "linear probe",
            "CoOp",
            "CoCoOp",
            "Tip-Adapter",
            "TPT",
            "ViT^3-style test-time training setting if reproducible",
        ]
        datasets = "ImageNet, Caltech101, OxfordPets, Food101, DTD, EuroSAT, UCF101, SUN397"
        return [
            {
                "title": "Entropy-Stopped Prompt Tuning for Few-Shot CLIP",
                "thesis": (
                    f"For {domain}, update only a tiny set of visual/text prompts at test time and stop when prediction entropy "
                    "or augmentation consistency no longer improves, keeping adaptation useful under 4-8 RTX 4090 GPUs."
                ),
                "operator_explanation": f"Use '{first['name']}' as the adaptation pressure and '{second['name']}' as the cost-control guardrail.",
                "novelty_claim": "The contribution is a bounded test-time prompt update rule that reports accuracy-cost Pareto curves, not an unbounded adaptation recipe.",
                "expected_contribution": "A reproducible CLIP few-shot strategy with explicit stopping, cost accounting, and dataset coverage.",
                "insight": "Test-time training is only valuable if each update buys accuracy faster than it spends GPU time.",
                "conceptual_takeaway": "Make test-time adaptation earn every gradient step.",
                "sharp_reframing": "Few-shot CLIP adaptation becomes a stopping-rule problem, not just a prompt-learning problem.",
                "mechanism_design": [
                    "Freeze CLIP image/text encoders and update only prompt vectors or a tiny prompt adapter.",
                    "For each test batch, run weak/strong augmentations and compute entropy plus prediction stability.",
                    "Stop updates when entropy improvement falls below a threshold or class prototypes start drifting.",
                    f"Evaluate on {datasets} with identical shot splits and fixed wall-clock budgets.",
                ],
                "why_it_might_work": [
                    "It prevents TTT from overfitting hard examples after the useful signal has saturated.",
                    "Prompt-only updates keep memory and implementation cost low.",
                    "Entropy and consistency are available without extra labels at test time.",
                ],
                "minimal_experiment": (
                    "Run 1/2/4/8/16-shot splits on four datasets first, then scale to the full eight-dataset matrix; log per-batch adaptation steps and time."
                ),
                "validation_protocol": [
                    f"Compare against {', '.join(baselines)}.",
                    "Report accuracy, base-to-novel gap, adaptation time, GPU hours, and peak memory.",
                    "Ablate stop threshold, update parameter count, augmentation strength, and per-image vs per-batch adaptation.",
                ],
                "baselines": baselines,
                "metrics": metrics,
                "failure_modes": [
                    "Entropy can be overconfident on shifted samples.",
                    "Prompt updates may help easy datasets but hurt base-to-novel generalization.",
                    "Per-image adaptation may be too slow unless batched.",
                ],
                "ranking_scores": {
                    "goal_relevance": 0.92,
                    "novelty": 0.76,
                    "principle_confidence": 0.48,
                    "testability": 0.9,
                    "feasibility": 0.84,
                    "expected_signal": 0.66,
                },
            },
            {
                "title": "Prototype-Stability Test-Time Adapter for CLIP",
                "thesis": (
                    "Attach a tiny adapter after CLIP visual features and update it only when class prototypes remain stable across augmentations and support subsets."
                ),
                "operator_explanation": "Transfer the scarce-shot principle into a stability gate that decides whether adaptation is safe.",
                "novelty_claim": "The method treats prototype stability as the permission signal for test-time learning.",
                "expected_contribution": "A safer TTT adapter that reduces semantic drift in few-shot CLIP.",
                "insight": "Few-shot adaptation fails when the support prototype is unstable; the model should first ask whether there is enough agreement to learn.",
                "conceptual_takeaway": "Adapt only when the few-shot prototype is trustworthy.",
                "sharp_reframing": "The test-time question is not what to update, but when the support signal deserves an update.",
                "mechanism_design": [
                    "Compute CLIP class prototypes from support images and augmented views.",
                    "Measure prototype variance and text-image alignment margin.",
                    "Update a small residual adapter only for classes whose prototypes pass the stability check.",
                    "Keep unstable classes at zero-shot or Tip-Adapter-style retrieval behavior.",
                ],
                "why_it_might_work": [
                    "It avoids corrupting CLIP semantics for classes with noisy support examples.",
                    "It can be implemented without full encoder fine-tuning.",
                    "Prototype variance gives an interpretable failure signal.",
                ],
                "minimal_experiment": "Run ImageNet, OxfordPets, EuroSAT, and DTD first; then complete the eight-dataset benchmark.",
                "validation_protocol": [
                    "Compare all methods under equal support shots and equal adaptation budgets.",
                    "Report gains by high-stability vs low-stability classes.",
                    "Ablate variance gate, adapter size, and text-image margin threshold.",
                ],
                "baselines": baselines,
                "metrics": metrics,
                "failure_modes": [
                    "Prototype variance may reject hard but learnable classes.",
                    "Adapter capacity may be too small for large domain shifts.",
                    "Support augmentation choices may dominate the stability estimate.",
                ],
                "ranking_scores": {
                    "goal_relevance": 0.9,
                    "novelty": 0.74,
                    "principle_confidence": 0.47,
                    "testability": 0.88,
                    "feasibility": 0.86,
                    "expected_signal": 0.64,
                },
            },
            {
                "title": "ViT Token Router for Test-Time CLIP Adaptation",
                "thesis": (
                    "Learn a lightweight test-time router that selects which ViT patch tokens should influence CLIP alignment for each few-shot task."
                ),
                "operator_explanation": "Use mechanism composition to connect token relevance with few-shot adaptation cost.",
                "novelty_claim": "Instead of updating the full visual representation, the method changes which tokens are trusted at test time.",
                "expected_contribution": "A token-selection TTT strategy inspired by ViT-style evidence routing, with explicit compute accounting.",
                "insight": "Many few-shot failures come from irrelevant background or spurious patch evidence, not from missing global semantics.",
                "conceptual_takeaway": "Spend test-time compute on choosing evidence, not rewriting the whole model.",
                "sharp_reframing": "TTT can be a token routing problem rather than a parameter updating problem.",
                "mechanism_design": [
                    "Freeze CLIP and add a tiny router over ViT patch tokens.",
                    "Use support examples to identify class-relevant token patterns.",
                    "At test time, update only router logits with entropy/consistency objectives.",
                    "Report routing sparsity, accuracy, and adaptation cost.",
                ],
                "why_it_might_work": [
                    "Token routing is cheaper than updating the encoder.",
                    "It can suppress background patches that hurt few-shot transfer.",
                    "Router sparsity creates a visible explanation of what changed.",
                ],
                "minimal_experiment": "Prototype on Caltech101, DTD, EuroSAT, and ImageNet 16-shot before running all datasets.",
                "validation_protocol": [
                    "Compare with prompt-only TTT and adapter-only TTT.",
                    "Ablate router sparsity, token budget, and whether text tokens are also routed.",
                    "Visualize selected patch tokens for success and failure cases.",
                ],
                "baselines": baselines,
                "metrics": [*metrics, "token sparsity", "selected-token stability"],
                "failure_modes": [
                    "Router may learn dataset shortcuts.",
                    "Patch-token visualization may look plausible without improving accuracy.",
                    "Routing overhead may erase savings on small batches.",
                ],
                "ranking_scores": {
                    "goal_relevance": 0.88,
                    "novelty": 0.82,
                    "principle_confidence": 0.46,
                    "testability": 0.84,
                    "feasibility": 0.78,
                    "expected_signal": 0.62,
                },
            },
            {
                "title": "Accuracy-Cost Benchmark Matrix for CLIP TTT",
                "thesis": (
                    "Make the benchmark protocol itself part of the contribution: every method is ranked by accuracy, adaptation time, memory, and GPU hours."
                ),
                "operator_explanation": "Convert the resource constraint into the benchmark axis that decides which adaptation methods are actually useful.",
                "novelty_claim": "The contribution is a reproducible evaluation matrix for resource-limited CLIP TTT, plus one method optimized for that matrix.",
                "expected_contribution": "A stronger experimental standard for 4-8 RTX 4090 few-shot vision work.",
                "insight": "A method that wins by spending unreported test-time compute is not a useful low-resource strategy.",
                "conceptual_takeaway": "For this query, the benchmark is not bookkeeping; it is the scientific instrument.",
                "sharp_reframing": "Few-shot CLIP TTT should be judged by Pareto dominance, not best average accuracy alone.",
                "mechanism_design": [
                    f"Define datasets: {datasets}.",
                    "Use 1/2/4/8/16-shot settings and base-to-novel splits where possible.",
                    "Log GPU type, number of GPUs, wall-clock, memory, update steps, and test-time FLOPs.",
                    "Publish an accuracy-cost table and use it to choose the final adaptation variant.",
                ],
                "why_it_might_work": [
                    "It prevents hidden compute from masquerading as algorithmic novelty.",
                    "It gives reviewers a clear way to compare TTT methods under realistic lab resources.",
                    "It can reveal simple baselines that dominate complex methods at fixed cost.",
                ],
                "minimal_experiment": "Run the full matrix for zero-shot CLIP, Tip-Adapter, TPT, and one proposed lightweight method.",
                "validation_protocol": [
                    "Freeze all data splits and cost accounting before method tuning.",
                    "Report Pareto frontiers rather than only mean accuracy.",
                    "Include confidence intervals over seeds for low-shot settings.",
                ],
                "baselines": baselines,
                "metrics": metrics,
                "failure_modes": [
                    "Benchmark work may be undervalued unless paired with a clear method variant.",
                    "Different implementations of baselines may have unfair cost accounting.",
                    "Full matrix can still be expensive if every ablation is run on every dataset.",
                ],
                "ranking_scores": {
                    "goal_relevance": 0.87,
                    "novelty": 0.72,
                    "principle_confidence": 0.48,
                    "testability": 0.94,
                    "feasibility": 0.9,
                    "expected_signal": 0.66,
                },
            },
            {
                "title": "Support-Set Memory Bank with Test-Time Drift Guard",
                "thesis": (
                    "Build a support-set memory bank for CLIP features, but allow test-time updates only when the memory prediction and CLIP text prior agree."
                ),
                "operator_explanation": "Resolve the tension between retrieval-based few-shot adaptation and semantic drift.",
                "novelty_claim": "The drift guard turns memory retrieval into a safe adaptation controller rather than a passive nearest-neighbor add-on.",
                "expected_contribution": "A practical hybrid of Tip-Adapter-style memory and bounded TTT.",
                "insight": "Support-set memory is useful, but it should not be allowed to drag CLIP away from its text prior without evidence.",
                "conceptual_takeaway": "Use memory to propose updates, and CLIP semantics to veto unsafe ones.",
                "sharp_reframing": "Few-shot adaptation becomes a negotiation between support evidence and pretrained text semantics.",
                "mechanism_design": [
                    "Build a feature cache from support examples.",
                    "Score each test sample with both cache retrieval and CLIP text logits.",
                    "Run TTT only when cache/text disagreement is moderate and correctable.",
                    "Skip adaptation when disagreement is extreme or confidence is already high.",
                ],
                "why_it_might_work": [
                    "It avoids wasting updates on easy examples.",
                    "It protects CLIP semantics on ambiguous or shifted examples.",
                    "It directly extends strong few-shot baselines rather than replacing them.",
                ],
                "minimal_experiment": "Compare Tip-Adapter, TPT, and memory-plus-drift-guard on 4/8/16-shot splits.",
                "validation_protocol": [
                    "Stratify results by cache/text agreement level.",
                    "Ablate guard thresholds and memory size.",
                    "Report cost per adapted sample and skipped-sample ratio.",
                ],
                "baselines": baselines,
                "metrics": [*metrics, "adapted-sample ratio"],
                "failure_modes": [
                    "Agreement thresholds may need dataset-specific tuning.",
                    "Cache retrieval can amplify mislabeled support examples.",
                    "Skipping too many samples may leave accuracy unchanged.",
                ],
                "ranking_scores": {
                    "goal_relevance": 0.86,
                    "novelty": 0.75,
                    "principle_confidence": 0.46,
                    "testability": 0.86,
                    "feasibility": 0.86,
                    "expected_signal": 0.62,
                },
            },
            {
                "title": "Class-Conditional Normalization TTT for CLIP",
                "thesis": (
                    "Adapt only lightweight normalization statistics conditioned on predicted classes, preserving CLIP semantics while correcting dataset shift."
                ),
                "operator_explanation": "Use the low-resource constraint to choose the smallest plausible update target.",
                "novelty_claim": "The method targets distribution shift through class-conditional normalization rather than prompt or full-adapter updates.",
                "expected_contribution": "A minimal TTT mechanism with very low memory and clear ablations.",
                "insight": "Some few-shot shifts are feature-distribution shifts; updating prompts may be less direct than stabilizing normalized features.",
                "conceptual_takeaway": "If the model already knows the class semantics, adapt the feature statistics before adapting the meaning.",
                "sharp_reframing": "TTT can correct visual distribution shift without touching the semantic prompt.",
                "mechanism_design": [
                    "Insert tiny class-conditional normalization or affine calibration layers after visual features.",
                    "Initialize from support-set feature statistics.",
                    "Update calibration parameters at test time with entropy and consistency losses.",
                    "Regularize calibration to stay close to support statistics.",
                ],
                "why_it_might_work": [
                    "It is cheaper than prompt or adapter updates.",
                    "It directly addresses feature shift under domain change.",
                    "It is easy to ablate and reproduce.",
                ],
                "minimal_experiment": "Run on EuroSAT, DTD, SUN397, and ImageNet variants where feature distribution shift is visible.",
                "validation_protocol": [
                    "Compare against prompt TTT, adapter TTT, and no TTT.",
                    "Report calibration parameter count and memory overhead.",
                    "Ablate class-conditional vs global normalization.",
                ],
                "baselines": baselines,
                "metrics": metrics,
                "failure_modes": [
                    "Predicted class conditioning can reinforce wrong pseudo-labels.",
                    "Normalization may not help semantic or fine-grained errors.",
                    "Regularization strength may be dataset-sensitive.",
                ],
                "ranking_scores": {
                    "goal_relevance": 0.84,
                    "novelty": 0.7,
                    "principle_confidence": 0.44,
                    "testability": 0.88,
                    "feasibility": 0.9,
                    "expected_signal": 0.6,
                },
            },
            {
                "title": "Two-Budget TTT: Fast Path and Careful Path",
                "thesis": (
                    "Route test samples into a fast no-update path or a careful TTT path, so expensive adaptation is reserved for uncertain or shifted samples."
                ),
                "operator_explanation": "Use resource allocation to decide when TTT is worth paying for.",
                "novelty_claim": "The method makes adaptation conditional on expected value, creating a deployable cost-aware TTT policy.",
                "expected_contribution": "A practical CLIP few-shot method with explicit compute throttling.",
                "insight": "Most test samples should not pay the same adaptation cost; uncertainty should buy extra computation.",
                "conceptual_takeaway": "Do not adapt every image; adapt only the images that can repay the cost.",
                "sharp_reframing": "TTT is an allocation policy over test examples.",
                "mechanism_design": [
                    "Use zero-shot CLIP confidence, cache agreement, and augmentation stability to estimate sample difficulty.",
                    "Send easy samples through a fast path with no updates.",
                    "Send uncertain samples through prompt/adapter TTT with a step cap.",
                    "Report accuracy and cost as the routing threshold changes.",
                ],
                "why_it_might_work": [
                    "It preserves most of CLIP's speed on easy samples.",
                    "It concentrates updates where domain shift is likely.",
                    "It naturally produces an accuracy-cost curve for resource-limited labs.",
                ],
                "minimal_experiment": "Run routing thresholds on four datasets first, then evaluate the chosen policy on the full benchmark matrix.",
                "validation_protocol": [
                    "Compare always-adapt, never-adapt, and routed-adapt policies.",
                    "Report routed fraction, accuracy, GPU hours, and wall-clock.",
                    "Ablate difficulty signals used by the router.",
                ],
                "baselines": baselines,
                "metrics": [*metrics, "adaptation routing rate"],
                "failure_modes": [
                    "Router may misclassify hard examples as easy.",
                    "Careful path may overfit if too few examples are routed.",
                    "Cost savings may disappear on uniformly hard datasets.",
                ],
                "ranking_scores": {
                    "goal_relevance": 0.89,
                    "novelty": 0.77,
                    "principle_confidence": 0.45,
                    "testability": 0.9,
                    "feasibility": 0.88,
                    "expected_signal": 0.64,
                },
            },
            {
                "title": "ViT^3-Inspired Tri-View Consistency for Few-Shot CLIP",
                "thesis": (
                    "Use three synchronized views of each test image, support prototype view, CLIP text view, and ViT patch-token view, and update only when all three agree on a useful direction."
                ),
                "operator_explanation": "Use contradiction resolution between visual evidence, text semantics, and support-set prototypes.",
                "novelty_claim": "The idea turns ViT-style multi-view test-time reasoning into a concrete CLIP few-shot adaptation gate.",
                "expected_contribution": "A high-level but testable strategy inspired by ViT^3-style test-time training, with explicit benchmark and cost reporting.",
                "insight": "Test-time updates are safest when visual patches, text priors, and support prototypes point in the same direction.",
                "conceptual_takeaway": "Use agreement among three evidence views as the permission to adapt.",
                "sharp_reframing": "The innovation is not a larger adapter; it is a stricter condition for when adaptation is allowed.",
                "mechanism_design": [
                    "Compute support prototype logits, CLIP text logits, and patch-token routed logits.",
                    "Measure tri-view agreement and only update prompt/router parameters when agreement is high but confidence is improvable.",
                    "Reject updates when the three views disagree strongly.",
                    "Log agreement groups to explain where gains occur.",
                ],
                "why_it_might_work": [
                    "It reduces semantic drift by requiring multiple evidence sources.",
                    "It makes ViT token evidence useful without full encoder training.",
                    "It gives interpretable failure buckets for analysis.",
                ],
                "minimal_experiment": "Evaluate tri-view gating against TPT and Tip-Adapter on 4/8/16-shot settings under a fixed 4090-hour budget.",
                "validation_protocol": [
                    "Report performance by high/medium/low tri-view agreement.",
                    "Ablate each view and the agreement threshold.",
                    "Compare compute cost to always-on prompt TTT.",
                ],
                "baselines": baselines,
                "metrics": [*metrics, "tri-view agreement calibration"],
                "failure_modes": [
                    "Agreement may be high for spurious background cues.",
                    "The gate may reject useful updates on fine-grained classes.",
                    "ViT^3-style assumptions may not transfer to all CLIP backbones.",
                ],
                "ranking_scores": {
                    "goal_relevance": 0.91,
                    "novelty": 0.83,
                    "principle_confidence": 0.45,
                    "testability": 0.82,
                    "feasibility": 0.76,
                    "expected_signal": 0.62,
                },
            },
        ]

    def _generic_idea_templates(
        self,
        domain: str,
        first: dict[str, Any],
        second: dict[str, Any],
    ) -> list[dict[str, Any]]:
        first_name = first.get("name", "source principle")
        second_name = second.get("name", "source principle")
        return [
            {
                "title": f"Crux Ledger for {domain.title()}",
                "thesis": (
                    f"Recast {domain} as a small ledger of decisive cruxes, then let {first_name} decide which crux deserves implementation first."
                ),
                "operator_explanation": (
                    f"Use '{first_name}' to turn a broad research goal into a ranked list of pressure points rather than a larger pipeline."
                ),
                "novelty_claim": "The novelty is a method-selection discipline: the method grows only from the crux that would most change the conclusion.",
                "expected_contribution": "A compact candidate method plus a reusable crux ledger that explains why this candidate was chosen.",
                "insight": "Many research ideas fail because they optimize an available module instead of the bottleneck that would actually change the result.",
                "conceptual_takeaway": "Start from the crux, not from the component list.",
                "sharp_reframing": f"{domain} becomes a question of which assumption is worth spending a method on.",
                "mechanism_design": [
                    "Write 3-5 crux statements that would change the design if answered differently.",
                    f"Map '{first_name}' to the crux with the largest expected impact.",
                    "Implement one narrow intervention tied to that crux.",
                    "Keep all other components identical to the nearest baseline.",
                ],
                "why_it_might_work": [
                    "It prevents attractive but irrelevant principles from driving the design.",
                    "It makes the contribution legible because the method answers a named crux.",
                    "It can produce a useful negative result if the crux turns out to be false.",
                ],
                "minimal_experiment": "Run baseline and one crux-driven variant on a small stratified split; report whether the target crux moved.",
                "validation_protocol": [
                    "Freeze the crux ledger before implementation.",
                    "Measure the crux proxy before the final task metric.",
                    "Compare against the nearest direct baseline under equal cost.",
                    "Archive cases where the final metric improves without moving the crux.",
                ],
                "baselines": ["nearest direct baseline", "baseline plus equal compute", "ablation without the crux intervention"],
                "metrics": ["primary task metric", "crux proxy movement", "cost-normalized improvement", "ablation delta"],
                "failure_modes": [
                    "The chosen crux is measurable but not causally important.",
                    "The intervention changes multiple cruxes at once.",
                    "The baseline already answers the same crux implicitly.",
                ],
                "ranking_scores": {
                    "goal_relevance": 0.82,
                    "novelty": 0.7,
                    "principle_confidence": 0.42,
                    "testability": 0.86,
                    "feasibility": 0.8,
                    "expected_signal": 0.59,
                },
            },
            {
                "title": f"Invariant Transfer Lens for {domain.title()}",
                "thesis": (
                    f"Use {first_name} to identify what must remain invariant across settings, then apply {second_name} only where that invariant breaks."
                ),
                "operator_explanation": (
                    f"Separate stable structure from context-specific correction by assigning '{first_name}' and '{second_name}' different roles."
                ),
                "novelty_claim": (
                    "The contribution is a transfer rule that says what should be preserved before it says what should be changed."
                ),
                "expected_contribution": "A method variant with clear invariants, explicit adaptation points, and interpretable failure slices.",
                "insight": (
                    "Generalization often improves less by adding flexibility than by protecting the small structure that should not move."
                ),
                "conceptual_takeaway": "Protect the invariant first; adapt only the residue.",
                "sharp_reframing": f"{domain} becomes a residue-modeling problem after the invariant is declared.",
                "mechanism_design": [
                    "Name the invariant implied by the strongest source principle.",
                    "Build the baseline so this invariant is directly inspectable.",
                    "Add a small correction module that acts only on invariant violations.",
                    "Report success by invariant-preserving and invariant-breaking cases.",
                ],
                "why_it_might_work": [
                    "It reduces uncontrolled adaptation.",
                    "It gives a natural ablation: invariant only, correction only, and combined.",
                    "It turns failures into interpretable categories instead of aggregate noise.",
                ],
                "minimal_experiment": (
                    "Create a small split that separates invariant-preserving and invariant-breaking examples, then compare the correction module only on the second slice."
                ),
                "validation_protocol": [
                    "Declare the invariant in writing before model design.",
                    "Measure whether the baseline already preserves it.",
                    "Run three ablations: invariant only, correction only, combined.",
                    "Inspect cases where correction violates the invariant.",
                ],
                "baselines": ["standard end-to-end baseline", "invariant-only variant", "correction-only variant"],
                "metrics": ["primary task metric", "invariant violation rate", "slice-wise improvement", "runtime overhead"],
                "failure_modes": [
                    "The declared invariant is too vague to measure.",
                    "The correction module becomes an unconstrained second model.",
                    "The split does not contain enough invariant-breaking cases.",
                ],
                "ranking_scores": {
                    "goal_relevance": 0.8,
                    "novelty": 0.72,
                    "principle_confidence": 0.44,
                    "testability": 0.84,
                    "feasibility": 0.82,
                    "expected_signal": 0.58,
                },
            },
            {
                "title": f"Bottleneck Thermometer for {domain.title()}",
                "thesis": (
                    f"Before expanding {domain}, build a lightweight thermometer that reveals whether the dominant bottleneck is data, representation, search, alignment, or evaluation."
                ),
                "operator_explanation": (
                    f"Use '{first_name}' to define the bottleneck measurement and '{second_name}' to choose the first intervention."
                ),
                "novelty_claim": (
                    "The novelty is not a heavier method; it is a diagnostic layer that tells which simple method should exist."
                ),
                "expected_contribution": "A bottleneck-aware method proposal with a diagnostic artifact other researchers can reuse.",
                "insight": (
                    "When the bottleneck is unknown, method complexity is often just a bet disguised as design."
                ),
                "conceptual_takeaway": "Measure the bottleneck temperature before prescribing the medicine.",
                "sharp_reframing": f"{domain} becomes a diagnosis problem before it becomes an architecture problem.",
                "mechanism_design": [
                    "Create 4-6 probes, one for each plausible bottleneck.",
                    "Run the nearest baseline and assign each failure to a bottleneck bucket.",
                    "Select the smallest intervention that targets the largest bucket.",
                    "Keep the thermometer as an analysis panel in the final results.",
                ],
                "why_it_might_work": [
                    "It prevents solving the wrong failure mode.",
                    "It makes negative results informative because they update the bottleneck map.",
                    "It can reveal that a simpler baseline is the right first contribution.",
                ],
                "minimal_experiment": (
                    "Run the thermometer on 30-100 examples or tasks, then test one intervention against the bucket it targets."
                ),
                "validation_protocol": [
                    "Publish the probe definitions.",
                    "Report bucket distribution before and after the intervention.",
                    "Compare against a randomly chosen intervention with the same budget.",
                    "Track whether gains concentrate in the intended bucket.",
                ],
                "baselines": ["nearest baseline", "same-budget random intervention", "strong simple heuristic"],
                "metrics": ["primary task metric", "bottleneck bucket shift", "targeted-slice gain", "cost-normalized gain"],
                "failure_modes": [
                    "The probes are too correlated to separate bottlenecks.",
                    "The largest bucket is easy to measure but hard to improve.",
                    "The intervention improves the metric without changing the diagnosed bucket.",
                ],
                "ranking_scores": {
                    "goal_relevance": 0.81,
                    "novelty": 0.74,
                    "principle_confidence": 0.43,
                    "testability": 0.88,
                    "feasibility": 0.86,
                    "expected_signal": 0.61,
                },
            },
            {
                "title": f"Counterfactual Baseline Pair for {domain.title()}",
                "thesis": (
                    f"Design the new {domain} method together with a counterfactual baseline that differs by exactly one causal assumption."
                ),
                "operator_explanation": f"Turn '{first_name}' into a causal contrast instead of a standalone module.",
                "novelty_claim": "The contribution is stronger because the baseline is built to challenge the claimed mechanism directly.",
                "expected_contribution": "A method plus a paired baseline that makes the contribution hard to overclaim.",
                "insight": "A good baseline should be the nearest world where the idea's central assumption is false.",
                "conceptual_takeaway": "Make the baseline argue against the idea.",
                "sharp_reframing": f"{domain} evaluation becomes a causal contrast, not a leaderboard entry.",
                "mechanism_design": [
                    "Write the candidate's central causal assumption in one sentence.",
                    "Construct a baseline that keeps all capacity and cost but removes that assumption.",
                    "Run both under identical data, compute, and tuning budgets.",
                    "Analyze cases where both succeed, both fail, or only the candidate succeeds.",
                ],
                "why_it_might_work": [
                    "It reduces accidental novelty from extra capacity.",
                    "It gives reviewers a clearer reason to believe the mechanism.",
                    "It often reveals a cheaper variant that preserves the useful part.",
                ],
                "minimal_experiment": "Implement the paired baseline first, then run candidate and pair on one representative benchmark slice.",
                "validation_protocol": [
                    "Match parameter count, data access, and tuning budget.",
                    "Report aggregate and paired-example deltas.",
                    "Include at least one case study where the pair distinguishes the mechanism.",
                ],
                "baselines": ["nearest published baseline", "counterfactual matched baseline", "capacity-matched ablation"],
                "metrics": ["paired improvement", "primary task metric", "parameter/cost parity", "case-level mechanism evidence"],
                "failure_modes": [
                    "The counterfactual baseline is accidentally weaker.",
                    "The central assumption is too broad to remove cleanly.",
                    "Both variants improve for the same unrelated reason.",
                ],
                "ranking_scores": {
                    "goal_relevance": 0.78,
                    "novelty": 0.71,
                    "principle_confidence": 0.42,
                    "testability": 0.9,
                    "feasibility": 0.8,
                    "expected_signal": 0.6,
                },
            },
            {
                "title": f"Signal-to-Cost Router for {domain.title()}",
                "thesis": (
                    f"Allocate expensive {domain} computation only to cases where {first_name} predicts a high value of information."
                ),
                "operator_explanation": "Convert scarce compute into a routing decision rather than a uniform architecture choice.",
                "novelty_claim": "The method is novel if it learns when the expensive mechanism is worth invoking, not merely how to invoke it.",
                "expected_contribution": "A cost-aware method with an explicit routing policy and accuracy-cost curve.",
                "insight": "Uniform computation wastes budget on easy cases and hides whether the idea is actually useful on hard ones.",
                "conceptual_takeaway": "Spend reasoning or model capacity only where it can repay its cost.",
                "sharp_reframing": f"{domain} becomes resource allocation over examples, not one fixed pipeline.",
                "mechanism_design": [
                    "Compute a cheap uncertainty, disagreement, or difficulty score.",
                    "Route low-risk cases through the simple path.",
                    "Route high-value cases through the principle-inspired mechanism.",
                    "Sweep the route threshold to trace an accuracy-cost frontier.",
                ],
                "why_it_might_work": [
                    "It can preserve speed while improving hard cases.",
                    "It creates a clear tradeoff curve instead of one opaque number.",
                    "It exposes whether the expensive module has positive marginal value.",
                ],
                "minimal_experiment": "Run never-expensive, always-expensive, and routed variants on the same split.",
                "validation_protocol": [
                    "Report routed fraction, cost, and metric by difficulty slice.",
                    "Ablate each routing signal.",
                    "Check that the router does not simply learn dataset shortcuts.",
                ],
                "baselines": ["simple path only", "expensive path always", "random routing at equal cost"],
                "metrics": ["primary metric", "cost-normalized gain", "routed fraction", "hard-slice improvement"],
                "failure_modes": [
                    "The router mistakes easy-looking failures for safe cases.",
                    "Routing overhead erases cost savings.",
                    "The expensive path does not outperform the simple path even on hard cases.",
                ],
                "ranking_scores": {
                    "goal_relevance": 0.8,
                    "novelty": 0.72,
                    "principle_confidence": 0.43,
                    "testability": 0.86,
                    "feasibility": 0.84,
                    "expected_signal": 0.59,
                },
            },
            {
                "title": f"Failure Cartography for {domain.title()}",
                "thesis": (
                    f"Map failures in {domain} into a small causal atlas, then let {first_name} and {second_name} propose interventions for different regions."
                ),
                "operator_explanation": "Use principle composition as a map of when each mechanism should be trusted.",
                "novelty_claim": "The novelty lies in conditional method design: different failure regions get different mechanisms.",
                "expected_contribution": "A method whose behavior is explained by a failure atlas rather than a single aggregate score.",
                "insight": "A single method can look mediocre because it helps one failure family and hurts another.",
                "conceptual_takeaway": "Do not average away the place where the idea works.",
                "sharp_reframing": f"{domain} becomes a geography of failure families.",
                "mechanism_design": [
                    "Cluster baseline failures by observable cause.",
                    f"Assign '{first_name}' to the region it best explains.",
                    f"Assign '{second_name}' to a distinct region or to a conflict case.",
                    "Use a lightweight dispatcher to choose the regional intervention.",
                ],
                "why_it_might_work": [
                    "It avoids forcing one mechanism onto incompatible failures.",
                    "It can reveal a narrower but stronger contribution.",
                    "It gives a natural path for future extensions.",
                ],
                "minimal_experiment": "Tag 50-100 baseline failures, implement one regional intervention, and report gains only on the targeted region plus the full set.",
                "validation_protocol": [
                    "Define failure labels before seeing candidate results.",
                    "Report per-region and aggregate performance.",
                    "Test whether the dispatcher chooses the intended region.",
                ],
                "baselines": ["single global intervention", "baseline without regional dispatch", "oracle region labels if available"],
                "metrics": ["per-region gain", "aggregate metric", "dispatcher accuracy", "negative transfer rate"],
                "failure_modes": [
                    "Failure labels are subjective.",
                    "Dispatcher errors dominate the regional method.",
                    "Regional gains are too narrow to matter.",
                ],
                "ranking_scores": {
                    "goal_relevance": 0.79,
                    "novelty": 0.76,
                    "principle_confidence": 0.41,
                    "testability": 0.82,
                    "feasibility": 0.78,
                    "expected_signal": 0.57,
                },
            },
            {
                "title": f"Assumption Budget for {domain.title()}",
                "thesis": (
                    f"Treat each added assumption in {domain} as a budgeted liability, and allow {first_name} to spend that budget only where it buys measurable robustness."
                ),
                "operator_explanation": "Invert the usual novelty search: penalize assumptions until evidence justifies them.",
                "novelty_claim": "The contribution is an assumption-minimal method whose added complexity is traceable to measured need.",
                "expected_contribution": "A lean method with an assumption ledger, ablations, and a robustness-focused contribution claim.",
                "insight": "The best idea is sometimes the one that spends fewer assumptions while preserving the same explanatory force.",
                "conceptual_takeaway": "Every assumption should earn its place.",
                "sharp_reframing": f"{domain} design becomes assumption accounting.",
                "mechanism_design": [
                    "List the baseline assumptions and the candidate's new assumptions.",
                    "Rank assumptions by expected risk and expected benefit.",
                    "Implement only the top assumption as a removable module.",
                    "Evaluate robustness on the slice where that assumption should matter.",
                ],
                "why_it_might_work": [
                    "It makes novelty less brittle.",
                    "It discourages over-designed systems.",
                    "It produces clearer limitations and cleaner ablations.",
                ],
                "minimal_experiment": "Run baseline, assumption-added, and assumption-removed variants on one main split and one stress split.",
                "validation_protocol": [
                    "Publish the assumption ledger.",
                    "Run a stress test tied to the riskiest assumption.",
                    "Report whether the method fails gracefully when the assumption is violated.",
                ],
                "baselines": ["baseline without new assumption", "full candidate", "candidate with top assumption removed"],
                "metrics": ["main metric", "stress-slice metric", "assumption violation sensitivity", "complexity cost"],
                "failure_modes": [
                    "The assumption ledger becomes rhetorical rather than measurable.",
                    "The stress slice is too weak.",
                    "The method needs multiple assumptions interacting at once.",
                ],
                "ranking_scores": {
                    "goal_relevance": 0.77,
                    "novelty": 0.69,
                    "principle_confidence": 0.42,
                    "testability": 0.84,
                    "feasibility": 0.86,
                    "expected_signal": 0.56,
                },
            },
            {
                "title": f"Mechanism Attribution Harness for {domain.title()}",
                "thesis": (
                    f"Build {domain} so every claimed gain can be attributed to a named mechanism from the principle pool, independent insight pool, or novelty pool."
                ),
                "operator_explanation": "Treat principles, insights, and novelty facts as independent causes that must earn separate evidence.",
                "novelty_claim": "The idea is novel as an attribution discipline: it composes sources without letting one source explain every gain.",
                "expected_contribution": "A method plus attribution harness showing which source fact actually drove improvement.",
                "insight": "Composed ideas become more credible when principle, insight, and novelty each leave a measurable fingerprint.",
                "conceptual_takeaway": "Composition should create attribution, not blur it.",
                "sharp_reframing": f"{domain} becomes a source-attribution problem for research mechanisms.",
                "mechanism_design": [
                    "Assign one module or decision to a principle, one to an insight, and one to a novelty fact.",
                    "Create switches that independently remove each source contribution.",
                    "Measure main effect and interaction effect under equal cost.",
                    "Use the attribution table to decide the final method story.",
                ],
                "why_it_might_work": [
                    "It prevents local ideas from being mixed into unrelated queries without evidence.",
                    "It makes source lineage auditable.",
                    "It can discover that an insight or novelty fact matters more than the principle itself.",
                ],
                "minimal_experiment": "Run full, principle-only, insight-only, novelty-only, and pairwise-composition variants on a small fixed split.",
                "validation_protocol": [
                    "Freeze source assignments before implementation.",
                    "Report main and interaction effects.",
                    "Reject source facts with no measurable effect on the target query.",
                ],
                "baselines": ["nearest baseline", "single-source variants", "full composed variant"],
                "metrics": ["main effect", "interaction effect", "primary metric", "source attribution confidence"],
                "failure_modes": [
                    "Source assignments are arbitrary.",
                    "Switches change capacity as well as mechanism.",
                    "Interactions are too noisy to estimate on a small split.",
                ],
                "ranking_scores": {
                    "goal_relevance": 0.82,
                    "novelty": 0.75,
                    "principle_confidence": 0.44,
                    "testability": 0.88,
                    "feasibility": 0.76,
                    "expected_signal": 0.6,
                },
            },
        ]

    def _fallback_idea(
        self,
        goal: dict[str, Any],
        principles: list[dict[str, Any]],
        idx: int,
        *,
        model_mode: str = "auto",
    ) -> dict[str, Any]:
        if not principles:
            principles = [
                {
                    "principle_id": stable_id("P", goal["raw_query"], "fallback"),
                    "name": "Fallback principle",
                    "mechanism": "Turn a research pressure into a measurable first validation slice.",
                }
            ]
        first = principles[idx % len(principles)]
        second = principles[(idx + 1) % len(principles)] if len(principles) > 1 else first
        operator = OPERATORS[idx % len(OPERATORS)]
        domain = goal.get("target_domain", "the target task")
        is_recon = "3d reconstruction" in domain.lower() or any(
            "3d-reconstruction" in tag for tag in first.get("domain_tags", [])
        )
        if self._is_time_series_goal(goal, first):
            templates = self._time_series_idea_templates(domain, first, second)
        elif is_recon:
            templates = self._reconstruction_idea_templates(domain, first, second)
        elif self._is_vision_ttt_goal(goal):
            templates = self._vision_ttt_idea_templates(domain, first, second)
        elif self._is_mas_goal(goal):
            templates = self._mas_idea_templates(domain, first, second)
        else:
            templates = self._generic_idea_templates(domain, first, second)
        selected = dict(templates[idx % len(templates)])
        if idx >= len(templates):
            operator_label = operator.replace("_", " ").title()
            selected["title"] = compact_text(f"{selected['title']} via {operator_label}", 140)
        perspective = self._model_perspective(model_mode)
        if perspective["angle"]:
            selected["thesis"] = compact_text(f"{perspective['angle']} {selected['thesis']}", 560)
            selected["insight"] = compact_text(
                f"{perspective['angle']} {selected['insight']}",
                520,
            )
        if goal.get("query_kind") == "idea_draft" and goal.get("idea_draft"):
            selected = {
                **selected,
                "thesis": compact_text(
                    f"Refine the draft idea by grounding it in principle lineage: {selected['thesis']}",
                    520,
                ),
                "insight": compact_text(
                    "The supplied draft should be treated as a hypothesis: preserve its strongest mechanism, "
                    "replace weak assumptions with mined principles, and validate the revised version cheaply.",
                    420,
                ),
            }
        return {
            "title": selected["title"],
            "one_sentence_thesis": selected["thesis"],
            "source_principles": [first["principle_id"], second["principle_id"]],
            "operator_trace": [
                {
                    "operator": operator,
                    "explanation": selected["operator_explanation"],
                }
            ],
            "novelty_claim": selected["novelty_claim"],
            "prior_art_overlap": [first["principle_id"], second["principle_id"]],
            "expected_contribution": selected["expected_contribution"],
            "insight": selected["insight"],
            "conceptual_takeaway": selected.get("conceptual_takeaway", selected["insight"]),
            "sharp_reframing": selected.get("sharp_reframing", selected["thesis"]),
            "mechanism_design": selected["mechanism_design"],
            "why_it_might_work": selected["why_it_might_work"],
            "minimal_experiment": selected["minimal_experiment"],
            "validation_protocol": selected["validation_protocol"],
            "baselines": selected["baselines"],
            "metrics": selected["metrics"] or goal.get("success_metrics") or ["task success at fixed budget"],
            "failure_modes": selected["failure_modes"],
            "ranking_scores": selected["ranking_scores"],
            "estimate": self._fallback_estimate(first, second),
        }

    def _fallback_estimate(self, first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
        seed = int(stable_id("", first.get("principle_id", ""), second.get("principle_id", ""))[-4:], 16)
        rng = random.Random(seed)
        confidence = (
            float(first.get("confidence_score", 0.4)) + float(second.get("confidence_score", 0.4))
        ) / 2
        mean = round(0.8 + confidence * 4.2 + rng.random(), 2)
        useful = clamp(0.35 + confidence * 0.42 + rng.random() * 0.08, 0.2, 0.82)
        return {
            "primary_metric": "task success at fixed budget",
            "mean": mean,
            "lower_90": round(mean - 3.4, 2),
            "upper_90": round(mean + 4.6, 2),
            "probability_useful_signal": round(useful, 2),
            "probability_negative_result": round(0.18 + (1 - confidence) * 0.24, 2),
            "probability_implementation_failure": round(0.12 + (1 - confidence) * 0.22, 2),
            "compute_cost_estimate": "API-only smoke test; optional 2-6 GPU-hour validation",
            "time_to_first_signal": "2-4 hours",
            "key_risks": [
                "The source principle may not transfer cleanly.",
                "Benchmark variance may hide small gains.",
                "Implementation overhead may dominate on small tasks.",
            ],
        }

    def _fallback_goal(self, query: str, constraints: dict[str, str], complexity: float) -> ResearchGoal:
        terms = keyword_terms(enrich_query(query), 7)
        expansions = query_expansions(query)
        query_kind = self._detect_query_kind(query)
        normalized = enrich_query(query).lower().replace("_", " ")
        if any("3d reconstruction" in phrase for phrase in expansions):
            domain = "sparse-view 3D reconstruction"
        elif any(
            phrase in {
                "time series foundation model",
                "time series representation learning",
                "multisensor fusion",
                "remaining useful life prediction",
                "RUL prediction",
            }
            for phrase in expansions
        ):
            domain = "TimesFM cross-sensor RUL prediction"
        elif any(term in normalized for term in ["machine dialect", "dialect", "token efficient", "token cost"]):
            domain = "machine-dialect MAS for token-efficient reasoning"
        elif any(term in normalized for term in ["symbolic compactness", "intrinsic reward", "scientific discovery"]):
            domain = "symbolic-compactness reward for MAS scientific discovery"
        elif any(term in normalized for term in ["mas", "multi-agent", "multi agent", "llm agents"]):
            domain = "LLM multi-agent reasoning system"
        elif any(
            term in normalized
            for term in [
                "few-shot",
                "few shot",
                "few-shot learning",
                "test-time training",
                "test time training",
                "test-time adaptation",
                "test time adaptation",
                "clip",
                "vision-language",
                "vision transformer",
                "vit",
                "4090",
                "视觉模型",
                "小样本",
                "少样本",
            ]
        ):
            domain = "resource-aware CLIP/ViT few-shot test-time training"
        else:
            domain = " ".join(terms[:4]) if terms else "AI research"
        return ResearchGoal(
            goal_id=stable_id("G", query, str(constraints), query_kind),
            raw_query=query,
            target_domain=domain,
            contribution_type=["method", "evaluation"],
            success_metrics=[
                "task success at fixed budget",
                "time to first validation signal",
                "implementation difficulty",
            ],
            constraints={
                "compute_budget": constraints.get("compute_budget", "unrestricted demo default"),
                "timeline": constraints.get("timeline", "open"),
                "privacy_mode": constraints.get("privacy_mode", "local only"),
                "target_venue": constraints.get("target_venue", "workshop or open-source demo"),
            },
            search_terms=terms,
            complexity=complexity,
            query_kind=query_kind,
            idea_draft=query if query_kind == "idea_draft" else "",
        )

    def _detect_query_kind(self, query: str) -> str:
        lower = query.lower()
        draft_markers = [
            "my idea",
            "idea draft",
            "i propose",
            "we propose",
            "i plan",
            "method draft",
            "algorithm draft",
            "具体想法",
            "我的idea",
            "我的 idea",
            "方案",
            "草案",
        ]
        if any(marker in lower for marker in draft_markers):
            return "idea_draft"
        if len(query) > 220 and any(word in lower for word in ["use", "combine", "train", "validate", "module", "pipeline"]):
            return "idea_draft"
        return "task"

    def _complexity(self, query: str, constraints: dict[str, str]) -> float:
        tokens = keyword_terms(enrich_query(query), 40)
        hard_terms = {
            "theorem",
            "proof",
            "multi-agent",
            "long-context",
            "architecture",
            "benchmark",
            "training",
            "optimization",
            "mechanistic",
            "validation",
        }
        score = 0.28 + min(len(tokens), 40) / 100
        score += 0.08 * sum(1 for token in tokens if token in hard_terms)
        if constraints.get("timeline", "").lower() in {"1 month", "month"}:
            score += 0.08
        return clamp(score, 0.18, 0.92)

    def _list(self, value: Any, default: list[str]) -> list[str]:
        if isinstance(value, list):
            cleaned = [str(item).strip() for item in value if str(item).strip()]
            return cleaned or default
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return default
