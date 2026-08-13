from __future__ import annotations

import hashlib
import inspect
import json
import math
import threading
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from copy import deepcopy
from dataclasses import asdict
from typing import Any

from .models import (
    AllSourcesFailedError,
    InsufficientResultsError,
    QueryPlan,
    RetrievalConfig,
    RetrievalResult,
    SearchDiagnostics,
    SourceReport,
    WorkSource,
    control_check_cancelled,
    control_checkpoint,
)
from .planner import QueryPlanner
from .ranking import (
    bm25_rank,
    embedding_rerank,
    final_select,
    has_exact_entity,
    selection_key,
    stratified_embedding_candidates,
)
from .sources import default_sources, fetch_source_with_report
from .utils import clean_text, ordered_unique, strip_internal, truncate
from .works import dedupe_works

_QUERY_PLAN_CACHE_SCHEMA = "principia-query-plan-v1"
_QUERY_PLAN_CACHE_MAX_SIZE = 128
_QUERY_PLAN_CACHE: OrderedDict[str, QueryPlan] = OrderedDict()
_QUERY_PLAN_CACHE_LOCK = threading.RLock()
_RANKING_STABILITY_CACHE_SCHEMA = "principia-ranking-stability-v1"
_RANKING_STABILITY_CACHE_MAX_SIZE = 128
_RANKING_STABILITY_CACHE: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
_RANKING_STABILITY_CACHE_LOCK = threading.RLock()


class WorkRetriever:
    def __init__(
        self, *, sources: dict[str, WorkSource] | None = None, config: RetrievalConfig | None = None
    ) -> None:
        self._custom_sources = sources is not None
        self.sources = default_sources() if sources is None else sources
        self.config = config or RetrievalConfig()

    def search(
        self,
        goal_text: str,
        *,
        target_count: int = 50,
        llm: Any | None = None,
        sources: dict[str, WorkSource] | None = None,
        timeout: float = 12,
        embedding_client: Any | None = None,
        require_target: bool | None = None,
        callback: Callable[[str, dict[str, Any]], None] | None = None,
        control_token: Any | None = None,
    ) -> RetrievalResult:
        control_checkpoint(control_token)
        target_count = max(1, min(int(target_count or 50), 200))
        config = self.config
        strict = bool(config.require_target if require_target is None else require_target)
        rerank_mode = resolve_rerank_mode(config)
        source_registry = self.sources if sources is None else sources
        registry_is_explicit = self._custom_sources or sources is not None
        controlled_llm = _ControlBoundLLM(llm, control_token) if llm is not None else None
        planner = QueryPlanner(controlled_llm, use_llm=config.use_llm_planner, model_mode="auto")
        query_budget = max(1, int(config.max_queries or 1))
        plan_cache_key = _query_plan_cache_key(goal_text, config, llm)
        plan = _get_cached_query_plan(plan_cache_key)
        plan_cache_hit = plan is not None
        if plan is None:
            plan = planner.plan(goal_text, max_queries=query_budget)
            _store_cached_query_plan(plan_cache_key, plan)
        plan.trace = deepcopy(plan.trace)
        plan.trace["planner_cache"] = {
            "hit": plan_cache_hit,
            "scope": "process",
            "schema": _QUERY_PLAN_CACHE_SCHEMA,
            "key": plan_cache_key[:16],
        }
        control_checkpoint(control_token)
        source_names = resolve_source_names(
            config, source_registry, plan.domain_hints, registry_is_explicit
        )
        fallback_query = clean_text(goal_text)
        planned_queries = ordered_unique(plan.search_queries or [fallback_query])
        if fallback_query:
            non_fallback_queries = [query for query in planned_queries if query != fallback_query]
            queries = [*non_fallback_queries[: max(0, query_budget - 1)], fallback_query]
        else:
            queries = planned_queries[:query_budget]
        queries = queries or [fallback_query]
        plan.search_queries = queries
        plan.trace["routed_sources"] = source_names
        plan.trace["auto_routed_europe_pmc"] = (
            "europe_pmc" in source_names and config.source_names is None
        )
        if callback:
            callback(
                "query_plan",
                {
                    "queries": queries,
                    "entities": plan.entities,
                    "acronyms": plan.acronyms,
                    "scientific_terms": plan.scientific_terms,
                    "domain_hints": plan.domain_hints,
                    "sources": source_names,
                    "rerank_mode": rerank_mode,
                    "fallback_query": fallback_query,
                    "planner_trace": plan.trace,
                },
            )

        tasks = [
            (name, source_registry[name], query)
            for query in queries
            for name in source_names
            if name in source_registry
        ]
        raw_by_task: list[list[dict[str, Any]]] = [[] for _ in tasks]
        reports: list[SourceReport] = []
        desired_pool = max(
            target_count, int(math.ceil(target_count * max(1.0, config.candidate_oversample)))
        )
        raw_budget = max(desired_pool, int(config.max_raw_candidates or 1))
        initial_limit = max(1, int(math.ceil(raw_budget / max(1, len(tasks)))))
        max_per_task = max(1, min(100, int(config.max_results_per_source_query or 100)))
        rounds_used = 0
        previous_limit = 0

        for retrieval_round in range(1, max(1, int(config.max_retrieval_rounds or 1)) + 1):
            control_checkpoint(control_token)
            if not tasks:
                break
            request_limit = min(max_per_task, initial_limit * (2 ** (retrieval_round - 1)))
            if request_limit <= previous_limit:
                break
            previous_limit = request_limit
            rounds_used = retrieval_round
            # Parallelize across independent providers, not across queries sent
            # to the same provider.  A one-provider retriever must preserve
            # canonical query order across repeated searches; concurrent calls
            # to that provider also undermine its per-source rate limit.
            worker_count = min(8, max(1, len({name for name, _, _ in tasks})))
            executor = ThreadPoolExecutor(max_workers=worker_count)
            pending: dict[Future[tuple[list[dict[str, Any]], SourceReport]], int] = {}
            next_task = 0

            def submit_one(
                index: int,
                *,
                active_executor: ThreadPoolExecutor = executor,
                active_pending: dict[
                    Future[tuple[list[dict[str, Any]], SourceReport]], int
                ] = pending,
                active_limit: int = request_limit,
                active_round: int = retrieval_round,
            ) -> None:
                name, source, query = tasks[index]
                future = active_executor.submit(
                    fetch_source_with_report,
                    name,
                    source,
                    query,
                    active_limit,
                    timeout,
                    max_retries=config.source_max_retries,
                    backoff_seconds=config.source_backoff_seconds,
                    max_backoff_seconds=config.source_max_backoff_seconds,
                    min_interval_seconds=config.source_min_interval_seconds.get(name, 0.0),
                    retrieval_round=active_round,
                    control_token=control_token,
                )
                active_pending[future] = index

            try:
                while next_task < min(worker_count, len(tasks)):
                    submit_one(next_task)
                    next_task += 1
                while pending:
                    control_check_cancelled(control_token)
                    completed, _ = wait(
                        set(pending),
                        timeout=0.1,
                        return_when=FIRST_COMPLETED,
                    )
                    if not completed:
                        continue
                    for future in completed:
                        index = pending.pop(future)
                        rows, report = future.result()
                        reports.append(report)
                        if report.succeeded:
                            # Adaptive rounds are cumulative. Providers can
                            # return a shifted first page under load; replacing
                            # the earlier response would make an identical
                            # search lose valid candidates and destabilize the
                            # top ranks. Strong-id/title deduplication keeps the
                            # union bounded by actual unique works.
                            raw_by_task[index] = dedupe_works(
                                [*raw_by_task[index], *rows[:request_limit]]
                            )
                        if callback:
                            callback(
                                "source_report",
                                {
                                    **report.to_dict(),
                                    # Public metadata only. This enables the
                                    # product to show provisional papers while
                                    # slower providers are still running.
                                    "provisional_results": rows[:request_limit],
                                },
                            )
                        # A completed response is the safe boundary. Pause here
                        # before queuing any additional source request.
                        control_checkpoint(control_token)
                        if next_task < len(tasks):
                            submit_one(next_task)
                            next_task += 1
            except BaseException:
                for future in pending:
                    future.cancel()
                executor.shutdown(wait=False, cancel_futures=True)
                raise
            else:
                executor.shutdown(wait=True)

            raw = [item for rows in raw_by_task for item in rows]
            candidate_count = len(dedupe_works(raw))
            if candidate_count >= desired_pool:
                break
            # Internal retries already exhausted. Repeating a round cannot
            # recover an all-source outage and would only delay a clear error.
            if reports and all(report.status == "failed" for report in reports):
                break

        raw = [item for rows in raw_by_task for item in rows]
        counts_by_source: dict[str, int] = {}
        for (name, _, _), rows in zip(tasks, raw_by_task, strict=True):
            counts_by_source[name] = counts_by_source.get(name, 0) + len(rows)
        diagnostics = SearchDiagnostics(
            target_count=target_count,
            raw_count=len(raw),
            candidate_count=0,
            retrieval_rounds=rounds_used,
            query_plan=asdict(plan),
            source_reports=sorted(
                reports, key=lambda report: (report.retrieval_round, report.source, report.query)
            ),
            rerank_mode_requested=rerank_mode,
            rerank_mode_applied="bm25",
            counts_by_source=counts_by_source,
        )
        if not reports or all(report.status == "failed" for report in reports):
            diagnostics.degraded = True
            diagnostics.warnings.append(
                "All configured metadata source requests failed; no partial result was returned."
            )
            emit_diagnostics(callback, diagnostics)
            raise AllSourcesFailedError(diagnostics)

        failed_reports = [report for report in reports if report.status == "failed"]
        if failed_reports:
            diagnostics.degraded = True
            failed_labels = sorted({report.source for report in failed_reports})
            diagnostics.warnings.append(
                "Partial metadata-source failure: "
                + ", ".join(failed_labels)
                + ". Results use the sources that succeeded."
            )

        candidates = dedupe_works(raw)
        control_checkpoint(control_token)
        diagnostics.candidate_count = len(candidates)
        scored = bm25_rank(goal_text, candidates, plan)
        diagnostics.bm25_scored_count = len(scored)
        prefiltered = [
            item
            for item in scored
            if item["_retrieval_score"] >= config.min_relevance or has_exact_entity(item, plan)
        ]
        # A convenience search may still return the requested count when the
        # relevance threshold leaves too few rows, but the expansion must be
        # explicit. Strict/live acceptance never receives below-threshold
        # top-ups and therefore fails clearly if relevant supply is short.
        if not strict and len(prefiltered) < target_count:
            desired_count = max(target_count, 20) if not prefiltered else target_count
            seen_prefiltered = {selection_key(item) for item in prefiltered}
            low_score_top_up = 0
            for item in scored:
                key = selection_key(item)
                if key in seen_prefiltered:
                    continue
                prefiltered.append(item)
                seen_prefiltered.add(key)
                low_score_top_up += 1
                if len(prefiltered) >= desired_count:
                    break
            if low_score_top_up:
                diagnostics.degraded = True
                diagnostics.warnings.append(
                    "Non-strict retrieval added "
                    f"{low_score_top_up} below-threshold candidate(s) to avoid silent underfill."
                )
        diagnostics.bm25_prefiltered_count = len(prefiltered)
        if rerank_mode == "embedding_rerank":
            diagnostics.embedding_input_count = min(
                len(prefiltered),
                embedding_rerank_candidate_limit(
                    target_count, config.embedding_rerank_candidate_limit
                ),
            )
            embedding_pool = stratified_embedding_candidates(
                prefiltered,
                diagnostics.embedding_input_count,
                plan,
            )
            prefiltered = embedding_rerank(
                goal_text,
                embedding_pool,
                plan,
                model=config.embedding_model,
                dimensions=config.embedding_dimensions,
                batch_size=config.embedding_batch_size,
                timeout=config.embedding_timeout,
                max_retries=config.embedding_max_retries,
                embedding_client=embedding_client,
                control_token=control_token,
            )
            fallback_errors = ordered_unique(
                [
                    str((item.get("community_signals") or {}).get("embedding_rerank_error") or "")
                    for item in prefiltered
                    if (item.get("community_signals") or {}).get("embedding_rerank_error")
                ]
            )
            if fallback_errors:
                diagnostics.rerank_fallback_reason = truncate("; ".join(fallback_errors), 500)
                diagnostics.warnings.append(
                    "Embedding rerank was requested but unavailable; deterministic BM25 ordering was retained."
                )
                diagnostics.degraded = True
            else:
                diagnostics.rerank_mode_applied = "embedding_rerank"

        selected = final_select(prefiltered, target_count, plan)
        stability_key = _ranking_stability_key(
            plan_cache_key,
            source_registry,
            source_names,
            target_count,
            rerank_mode,
        )
        anchor_keys: set[str] = set()
        if config.stabilize_repeated_searches:
            previous_selection = _get_cached_stability_selection(stability_key)
            if previous_selection is None:
                _store_cached_stability_selection(stability_key, selected)
            else:
                selected, anchor_keys, restored = _stabilize_repeated_selection(
                    selected,
                    previous_selection,
                    target_count=target_count,
                    window=config.stability_window,
                    min_jaccard=config.stability_min_jaccard,
                )
                diagnostics.stability_anchor_applied = True
                diagnostics.stability_anchor_window = min(
                    max(1, int(config.stability_window or 20)), target_count
                )
                diagnostics.stability_anchor_retained = len(anchor_keys)
                diagnostics.stability_anchor_restored = restored
                diagnostics.warnings.append(
                    "Same-process ranking stability anchor retained "
                    f"{len(anchor_keys)} prior top-{diagnostics.stability_anchor_window} work(s); "
                    "all metadata sources were still queried afresh."
                )
                plan.trace["ranking_stability"] = {
                    "applied": True,
                    "scope": "process",
                    "schema": _RANKING_STABILITY_CACHE_SCHEMA,
                    "window": diagnostics.stability_anchor_window,
                    "retained": len(anchor_keys),
                    "restored_from_prior_fresh_run": restored,
                }
        control_checkpoint(control_token)
        trace = [
            {
                "rank": index,
                "work_id": item.get("work_id", ""),
                "title": item.get("title", ""),
                "source": item.get("source", ""),
                "score": round(float(item.get("_retrieval_score", 0.0)), 6),
                "bm25_score": round(float(item.get("_bm25_score", 0.0)), 6),
                "embedding_similarity": (
                    round(float(item.get("_embedding_similarity", 0.0)), 6)
                    if "_embedding_similarity" in item
                    else None
                ),
                "embedding_goal_similarity": (
                    round(float(item.get("_embedding_goal_similarity", 0.0)), 6)
                    if "_embedding_goal_similarity" in item
                    else None
                ),
                "embedding_aspect_similarity": (
                    round(float(item.get("_embedding_aspect_similarity", 0.0)), 6)
                    if "_embedding_aspect_similarity" in item
                    else None
                ),
                "aspect_coverage_score": round(float(item.get("_aspect_coverage_score", 0.0)), 6),
                "goal_facet_score": round(float(item.get("_goal_facet_score", 0.0)), 6),
                "query_support_score": round(float(item.get("_query_support_score", 0.0)), 6),
                "evidence_quality_score": round(float(item.get("_evidence_quality_score", 0.0)), 6),
                "abstract_assessability_score": round(
                    float(item.get("_abstract_assessability_score", 0.0)), 6
                ),
                "diversity_score": (item.get("community_signals") or {}).get("diversity_score"),
                "relation_label": item.get("relation_label", ""),
                "rationale": item.get("retrieval_rationale", ""),
                "reject_reason": item.get("reject_reason", ""),
                "stability_anchor": selection_key(item) in anchor_keys,
            }
            for index, item in enumerate(selected, start=1)
        ]
        diagnostics.selected_count = len(selected)
        diagnostics.complete = len(selected) == target_count
        diagnostics.completeness = min(1.0, len(selected) / max(1, target_count))
        diagnostics.ranking_trace = trace
        if not diagnostics.complete:
            diagnostics.degraded = True
            diagnostics.warnings.append(
                f"Retrieval returned {len(selected)} of {target_count} requested unique works after {rounds_used} round(s)."
            )

        public_selected = [strip_internal(item) for item in selected]
        # Keep the candidate pool in ranking order, with the selected cohort
        # first.  The framework/SQLite layer has stronger cross-provider
        # identity knowledge than an isolated retrieval response, so it may
        # need the next ranked candidates to replenish canonical duplicates.
        # Raw provider order is not suitable for that strict-target top-up.
        candidates = dedupe_works([*selected, *prefiltered, *candidates])
        public_candidates = [strip_internal(item) for item in candidates]
        result = RetrievalResult(
            query_plan=plan,
            candidates=public_candidates,
            selected_works=public_selected,
            ranking_trace=trace,
            diagnostics=diagnostics,
        )
        emit_diagnostics(callback, diagnostics)
        if strict and not diagnostics.complete:
            raise InsufficientResultsError(result)
        return result


class _ControlBoundLLM:
    """Duck-typed planner adapter that forwards the active retrieval control."""

    def __init__(self, delegate: Any, control_token: Any | None) -> None:
        self._delegate = delegate
        self._control_token = control_token

    def available(self, *args: Any, **kwargs: Any) -> Any:
        return self._delegate.available(*args, **kwargs)

    def chat_json(self, *args: Any, **kwargs: Any) -> Any:
        control_checkpoint(self._control_token)
        method = self._delegate.chat_json
        try:
            parameters = inspect.signature(method).parameters
            supports_control = "control_token" in parameters or any(
                parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()
            )
        except (TypeError, ValueError):
            supports_control = False
        if supports_control:
            kwargs["control_token"] = self._control_token
        result = method(*args, **kwargs)
        control_checkpoint(self._control_token)
        return result


def _query_plan_cache_key(goal_text: str, config: RetrievalConfig, llm: Any | None) -> str:
    """Return a secret-free fingerprint for every input that can shape planning.

    The complete retrieval configuration is included deliberately. Although
    only a subset of its fields currently affects query generation, treating
    any configuration change as a cache miss avoids surprising reuse when a
    future release makes another field planner-relevant.
    """

    payload = {
        "schema": _QUERY_PLAN_CACHE_SCHEMA,
        "goal_text": clean_text(goal_text),
        "retrieval_config": asdict(config),
        "planner": _planner_identity(llm),
    }
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _planner_identity(llm: Any | None) -> dict[str, str]:
    """Describe the planner implementation without credentials or object ids."""

    delegate = getattr(llm, "_delegate", llm)
    if delegate is None:
        return {"implementation": "deterministic"}
    config = getattr(delegate, "config", None)
    return {
        "implementation": (f"{delegate.__class__.__module__}.{delegate.__class__.__qualname__}"),
        "provider": clean_text(getattr(config, "provider", "")),
        "model": clean_text(getattr(config, "model", "")),
        "base_url": clean_text(getattr(config, "base_url", "")),
    }


def _get_cached_query_plan(key: str) -> QueryPlan | None:
    with _QUERY_PLAN_CACHE_LOCK:
        cached = _QUERY_PLAN_CACHE.get(key)
        if cached is None:
            return None
        _QUERY_PLAN_CACHE.move_to_end(key)
        # Search adds routed-source diagnostics and may trim queries. Never let
        # those run-local mutations change the canonical cached plan.
        return deepcopy(cached)


def _store_cached_query_plan(key: str, plan: QueryPlan) -> None:
    with _QUERY_PLAN_CACHE_LOCK:
        _QUERY_PLAN_CACHE[key] = deepcopy(plan)
        _QUERY_PLAN_CACHE.move_to_end(key)
        while len(_QUERY_PLAN_CACHE) > _QUERY_PLAN_CACHE_MAX_SIZE:
            _QUERY_PLAN_CACHE.popitem(last=False)


def _clear_query_plan_cache() -> None:
    """Clear the process cache for isolated tests and long-lived host resets."""

    with _QUERY_PLAN_CACHE_LOCK:
        _QUERY_PLAN_CACHE.clear()
    with _RANKING_STABILITY_CACHE_LOCK:
        _RANKING_STABILITY_CACHE.clear()


def _ranking_stability_key(
    plan_cache_key: str,
    source_registry: dict[str, WorkSource],
    source_names: list[str],
    target_count: int,
    rerank_mode: str,
) -> str:
    source_scope = [
        (name, id(source_registry[name])) for name in source_names if name in source_registry
    ]
    payload = {
        "schema": _RANKING_STABILITY_CACHE_SCHEMA,
        "plan": plan_cache_key,
        "sources": source_scope,
        "target_count": target_count,
        "rerank_mode": rerank_mode,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _get_cached_stability_selection(key: str) -> list[dict[str, Any]] | None:
    with _RANKING_STABILITY_CACHE_LOCK:
        cached = _RANKING_STABILITY_CACHE.get(key)
        if cached is None:
            return None
        _RANKING_STABILITY_CACHE.move_to_end(key)
        return deepcopy(cached)


def _store_cached_stability_selection(key: str, rows: list[dict[str, Any]]) -> None:
    with _RANKING_STABILITY_CACHE_LOCK:
        _RANKING_STABILITY_CACHE[key] = deepcopy(rows)
        _RANKING_STABILITY_CACHE.move_to_end(key)
        while len(_RANKING_STABILITY_CACHE) > _RANKING_STABILITY_CACHE_MAX_SIZE:
            _RANKING_STABILITY_CACHE.popitem(last=False)


def _stabilize_repeated_selection(
    current: list[dict[str, Any]],
    previous: list[dict[str, Any]],
    *,
    target_count: int,
    window: int,
    min_jaccard: float,
) -> tuple[list[dict[str, Any]], set[str], int]:
    effective_window = min(max(1, int(window or 20)), target_count, len(previous))
    bounded_jaccard = min(1.0, max(0.0, float(min_jaccard)))
    required = min(
        effective_window,
        int(math.ceil((2 * effective_window * bounded_jaccard) / (1 + bounded_jaccard))),
    )
    current_by_key = {selection_key(item): item for item in current}
    anchored: list[dict[str, Any]] = []
    anchor_keys: set[str] = set()
    restored = 0
    for previous_item in previous[:required]:
        key = selection_key(previous_item)
        if key in anchor_keys:
            continue
        current_item = current_by_key.get(key)
        if current_item is None:
            current_item = previous_item
            restored += 1
        anchored.append(current_item)
        anchor_keys.add(key)
    merged = list(anchored)
    seen = set(anchor_keys)
    for pool in (current, previous):
        for item in pool:
            key = selection_key(item)
            if key in seen:
                continue
            merged.append(item)
            seen.add(key)
            if len(merged) >= target_count:
                return merged[:target_count], anchor_keys, restored
    return merged[:target_count], anchor_keys, restored


def emit_diagnostics(
    callback: Callable[[str, dict[str, Any]], None] | None, diagnostics: SearchDiagnostics
) -> None:
    if callback:
        callback("retrieval_diagnostics", diagnostics.to_dict())


def resolve_source_names(
    config: RetrievalConfig,
    source_registry: dict[str, WorkSource],
    domain_hints: list[str],
    registry_is_explicit: bool,
) -> list[str]:
    if config.source_names is not None:
        return [name for name in config.source_names if name in source_registry]
    if registry_is_explicit:
        return list(source_registry)
    base = [
        name
        for name in ["arxiv", "openalex", "crossref", "semantic_scholar"]
        if name in source_registry
    ]
    normalized_hints = {clean_text(hint).lower().replace(" ", "_") for hint in domain_hints}
    biomedical = bool(
        normalized_hints
        & {
            "biomedicine",
            "biomedical",
            "medicine",
            "health_science",
            "life_science",
            "life_sciences",
        }
    )
    if biomedical and "europe_pmc" in source_registry:
        base.append("europe_pmc")
    return base


def embedding_rerank_candidate_limit(target_count: int, configured_limit: int = 0) -> int:
    if int(configured_limit or 0) > 0:
        return max(int(target_count or 0), int(configured_limit or 0))
    # A four-times target pool leaves room for complementary facets and
    # metadata-quality filtering without silently collapsing strict 50-work
    # requests to a narrow lexical prefilter.
    return max(int(target_count or 0) * 4, 50)


def source_task_limits(task_count: int, raw_budget: int) -> list[int]:
    """Retained for low-level compatibility with v1.3.2 callers/tests."""

    if task_count <= 0:
        return []
    base, remainder = divmod(max(0, raw_budget), task_count)
    return [base + (1 if index < remainder else 0) for index in range(task_count)]


def resolve_rerank_mode(config: RetrievalConfig) -> str:
    mode = str(getattr(config, "rerank_mode", "") or "").strip().lower()
    if mode in {"embedding", "embedding-rerank", "embedding_rerank"}:
        return "embedding_rerank"
    return "bm25"
