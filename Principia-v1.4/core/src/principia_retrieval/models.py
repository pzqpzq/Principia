from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

WorkSource = Callable[[str, int, float], Sequence[dict[str, Any] | Any]]


class RetrievalControl(Protocol):
    """Optional cooperative control surface used by long retrieval operations.

    The protocol is deliberately structural: ``principia_retrieval`` remains
    usable on its own, while :class:`principia.run.RunControlToken` can be
    supplied directly by the high-level framework. Legacy cancel tokens that
    expose only ``raise_if_cancelled`` continue to work through the helpers
    below.
    """

    def checkpoint(self) -> None: ...

    def check_cancelled(self) -> None: ...

    def wait(self, seconds: float, *, checkpoint: bool = True) -> None: ...

    def register_stop_callback(self, callback: Callable[[], None]) -> Callable[[], None]: ...


def control_check_cancelled(control: Any | None) -> None:
    """Raise promptly for a stop request without blocking on pause."""

    if control is None:
        return
    check = getattr(control, "check_cancelled", None)
    if callable(check):
        check()
        return
    check = getattr(control, "raise_if_cancelled", None)
    if callable(check):
        check()


def control_checkpoint(control: Any | None) -> None:
    """Enter a safe pause boundary before scheduling another paid request."""

    if control is None:
        return
    checkpoint = getattr(control, "checkpoint", None)
    if callable(checkpoint):
        checkpoint()
        return
    control_check_cancelled(control)


def control_wait(control: Any | None, seconds: float, *, checkpoint: bool = True) -> None:
    """Wait interruptibly, falling back to short polling for legacy tokens."""

    duration = max(0.0, float(seconds or 0.0))
    if control is not None:
        wait = getattr(control, "wait", None)
        if callable(wait):
            try:
                wait(duration, checkpoint=checkpoint)
            except TypeError:
                wait(duration)
            return
    deadline = time.monotonic() + duration
    while True:
        if checkpoint:
            control_checkpoint(control)
        else:
            control_check_cancelled(control)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(0.1, remaining))


def control_register_stop_callback(
    control: Any | None,
    callback: Callable[[], None],
) -> Callable[[], None]:
    """Register best-effort active-I/O cancellation and return an unregister."""

    if control is None:
        return lambda: None
    register = getattr(control, "register_stop_callback", None)
    if not callable(register):
        return lambda: None
    unregister = register(callback)
    if not callable(unregister):
        return lambda: None

    def safe_unregister() -> None:
        with suppress(Exception):
            unregister()

    return safe_unregister


@dataclass
class RetrievalConfig:
    use_llm_planner: bool = True
    rerank_mode: str = ""
    max_raw_candidates: int = 240
    min_relevance: float = 0.08
    source_names: list[str] | None = None
    max_queries: int = 6
    embedding_model: str = "Qwen/Qwen3-Embedding-4B"
    embedding_dimensions: int = 1024
    # Conservative for long scholarly abstracts and provider payload limits.
    embedding_batch_size: int = 8
    embedding_timeout: float = 30.0
    embedding_max_retries: int = 2
    embedding_rerank_candidate_limit: int = 0
    source_max_retries: int = 2
    source_backoff_seconds: float = 0.5
    source_max_backoff_seconds: float = 8.0
    source_min_interval_seconds: dict[str, float] = field(
        default_factory=lambda: {
            "arxiv": 3.0,
            "openalex": 1.0,
            "crossref": 0.2,
            "semantic_scholar": 1.0,
            "europe_pmc": 0.2,
            "openreview": 0.5,
        }
    )
    max_retrieval_rounds: int = 3
    # A three-times cohort prevents a transiently underfilled provider from
    # changing whether an otherwise identical strict 50-work search performs
    # an additional adaptive round. This materially improves fresh-run rank
    # stability while retaining bounded top-up behavior.
    candidate_oversample: float = 3.0
    max_results_per_source_query: int = 100
    require_target: bool = False
    stabilize_repeated_searches: bool = True
    stability_window: int = 20
    stability_min_jaccard: float = 0.70


@dataclass
class QueryPlan:
    goal_text: str
    search_queries: list[str]
    entities: list[str] = field(default_factory=list)
    key_phrases: list[str] = field(default_factory=list)
    domain_hints: list[str] = field(default_factory=list)
    exclude_terms: list[str] = field(default_factory=list)
    ai_intent: bool = False
    trace: dict[str, Any] = field(default_factory=dict)
    acronyms: list[str] = field(default_factory=list)
    scientific_terms: list[str] = field(default_factory=list)
    synonyms: dict[str, list[str]] = field(default_factory=dict)
    complementary_intents: list[str] = field(default_factory=list)


@dataclass
class SourceReport:
    """Observable outcome of one source/query request.

    ``status`` is one of ``success``, ``empty``, or ``failed``.  Empty is kept
    distinct from failed so a legitimate zero-result response never looks like
    an infrastructure outage.
    """

    source: str
    query: str
    normalized_query: str
    requested_count: int
    returned_count: int = 0
    normalized_count: int = 0
    status: str = "success"
    latency_ms: float = 0.0
    attempts: int = 1
    retries: int = 0
    error_type: str = ""
    error: str = ""
    retry_errors: list[str] = field(default_factory=list)
    http_status: int | None = None
    retry_after_seconds: float | None = None
    retrieval_round: int = 1

    @property
    def succeeded(self) -> bool:
        return self.status in {"success", "empty"}

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SearchDiagnostics:
    """Structured, serializable diagnostics for a complete retrieval run."""

    complete: bool = False
    completeness: float = 0.0
    degraded: bool = False
    target_count: int = 0
    selected_count: int = 0
    raw_count: int = 0
    candidate_count: int = 0
    bm25_scored_count: int = 0
    bm25_prefiltered_count: int = 0
    embedding_input_count: int = 0
    retrieval_rounds: int = 0
    query_plan: dict[str, Any] = field(default_factory=dict)
    ranking_trace: list[dict[str, Any]] = field(default_factory=list)
    source_reports: list[SourceReport] = field(default_factory=list)
    rerank_mode_requested: str = "bm25"
    rerank_mode_applied: str = "bm25"
    rerank_fallback_reason: str = ""
    stability_anchor_applied: bool = False
    stability_anchor_window: int = 0
    stability_anchor_retained: int = 0
    stability_anchor_restored: int = 0
    warnings: list[str] = field(default_factory=list)
    counts_by_source: dict[str, int] = field(default_factory=dict)

    @property
    def successful_sources(self) -> list[str]:
        return sorted({report.source for report in self.source_reports if report.succeeded})

    @property
    def failed_sources(self) -> list[str]:
        successful = set(self.successful_sources)
        return sorted(
            {
                report.source
                for report in self.source_reports
                if report.status == "failed" and report.source not in successful
            }
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["successful_sources"] = self.successful_sources
        payload["failed_sources"] = self.failed_sources
        return payload


@dataclass
class RetrievalResult:
    query_plan: QueryPlan
    candidates: list[dict[str, Any]]
    selected_works: list[dict[str, Any]]
    ranking_trace: list[dict[str, Any]]
    diagnostics: SearchDiagnostics = field(default_factory=SearchDiagnostics)


class RetrievalError(RuntimeError):
    """Base class for surfaced retrieval failures."""


class SourceFetchError(RetrievalError):
    def __init__(self, report: SourceReport) -> None:
        self.report = report
        message = report.error or "unknown source error"
        super().__init__(
            f"{report.source} search failed after {report.attempts} attempt(s): {message}"
        )


class AllSourcesFailedError(RetrievalError):
    def __init__(self, diagnostics: SearchDiagnostics) -> None:
        self.diagnostics = diagnostics
        details = "; ".join(
            f"{report.source}: {report.error}"
            for report in diagnostics.source_reports
            if report.status == "failed"
        )
        super().__init__(f"Every configured metadata source failed. {details}".strip())


class InsufficientResultsError(RetrievalError):
    def __init__(self, result: RetrievalResult) -> None:
        self.result = result
        self.diagnostics = result.diagnostics
        super().__init__(
            f"Strict retrieval requested {result.diagnostics.target_count} unique works, "
            f"but only {result.diagnostics.selected_count} were available after "
            f"{result.diagnostics.retrieval_rounds} round(s)."
        )
