from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import unicodedata
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

from ..domain import (
    CandidatePrinciple,
    GenerationTrace,
    JobRecord,
    LiteratureRunLimits,
    PrincipleScope,
    TraceOperation,
    WorkReference,
    candidate_id,
    canonical_sha256,
    event_id,
    monotonic_ulid,
)
from ..models import WorkItem, utc_now
from ..persistence import V14WorkspaceRepository
from ..providers import ModelPolicy, OpenAICompatibleProvider
from ..research import ResearchService
from ..storage import WorkspaceStorage
from .literature import (
    SafeLiteratureAcquirer,
    ScholarlySearchService,
    open_access_locations,
    write_private_acquisition,
)

_TEMPLATE_PATTERNS = [
    r"\b(?:template|placeholder|insert (?:text|claim)|lorem ipsum)\b",
    r"\b(?:as an ai|candidate draft batch|source_keys?|segment_keys?)\b",
    r"\b(?:specific mechanism|bounded fixture|generic principle)\b",
    r"\bfurther research is needed\b",
]
_WORD_RE = re.compile(r"[a-z0-9]+", flags=re.IGNORECASE)
_NUMBER_RE = re.compile(r"(?<![A-Za-z])(?:\d+(?:\.\d+)?%?|[<>]=?|=|±)(?![A-Za-z])")
_QUALITY_STOPWORDS = {
    "and",
    "are",
    "cause",
    "causes",
    "conditions",
    "does",
    "for",
    "from",
    "how",
    "improve",
    "improves",
    "mechanism",
    "mechanisms",
    "produce",
    "reliably",
    "the",
    "their",
    "under",
    "what",
    "when",
    "which",
    "with",
}
_GENERIC_CLAIM_PATTERNS = (
    r"\b(?:broader view|well-informed decisions?)\b",
    r"\bwill always have the potential to backfire\b",
    r"\b(?:can|may) (?:help|improve|enable|support) (?:better|more)\b",
)


def _quality_terms(value: str) -> set[str]:
    output: set[str] = set()
    for raw in _WORD_RE.findall(value.casefold()):
        if len(raw) < 3 or raw in _QUALITY_STOPWORDS:
            continue
        if len(raw) > 6 and raw.endswith("ing"):
            raw = raw[:-3]
        elif len(raw) > 5 and raw.endswith("ed"):
            raw = raw[:-2]
        elif len(raw) > 5 and raw.endswith("s"):
            raw = raw[:-1]
        output.add(raw)
    return output


def _claim_symbols(value: str) -> set[str]:
    symbols: set[str] = set()
    for token in re.findall(r"\b[A-Za-z][A-Za-z0-9+/-]*\b", value):
        uppercase_count = sum(1 for character in token if character.isupper())
        if uppercase_count >= 2 or any(character.isdigit() for character in token):
            normalized = re.sub(r"[^a-z0-9]", "", token.casefold())
            if len(normalized) >= 2:
                symbols.add(normalized)
    return symbols


def _semantic_quality_reasons(
    *, draft: Any, work: WorkItem, goal: str, cited_text: str
) -> list[str]:
    reasons: list[str] = []
    claim_terms = _quality_terms(draft.claim)
    evidence_terms = _quality_terms(cited_text)
    if claim_terms and len(claim_terms & evidence_terms) / len(claim_terms) < 0.20:
        reasons.append("insufficient_claim_evidence_overlap")

    cited_normalized = re.sub(r"[^a-z0-9]", "", cited_text.casefold())
    unsupported_symbols = [
        symbol for symbol in _claim_symbols(draft.claim) if symbol not in cited_normalized
    ]
    if unsupported_symbols:
        reasons.append("unsupported_named_entity")

    goal_terms = _quality_terms(goal)
    candidate_terms = _quality_terms(f"{draft.title} {draft.claim} {draft.scope}")
    context_terms = candidate_terms | _quality_terms(f"{work.title} {work.abstract}")
    if goal_terms and (not (candidate_terms & goal_terms) or len(context_terms & goal_terms) < 2):
        reasons.append("off_goal_candidate")

    if any(
        re.search(pattern, draft.claim, flags=re.IGNORECASE) for pattern in _GENERIC_CLAIM_PATTERNS
    ):
        reasons.append("generic_summary_not_principle")
    return reasons


def _normalized_text_with_offsets(value: str) -> tuple[str, list[int]]:
    """Normalize PDF/model typography while retaining offsets into source text."""

    output: list[str] = []
    offsets: list[int] = []
    for index, original in enumerate(value):
        if original in {"\u00ad", "\u200b", "\ufeff"}:
            continue
        expanded = unicodedata.normalize("NFKC", original).casefold()
        for character in expanded:
            if character in {"‐", "‑", "‒", "–", "—", "−"}:
                character = "-"
            if character.isspace():
                if output and output[-1] != " ":
                    output.append(" ")
                    offsets.append(index)
                continue
            output.append(character)
            offsets.append(index)
    while output and output[-1] == " ":
        output.pop()
        offsets.pop()
    return "".join(output), offsets


def _resolve_evidence_quotation(source_text: str, proposed: str) -> str | None:
    """Return an exact source substring for an exact or typography-only match.

    The provider may normalize PDF whitespace, ligatures, or dash glyphs.  We
    accept only a contiguous match after those deterministic transformations and
    return the original source bytes for hashing and display.  Paraphrases and
    stitched quotations remain unverifiable.
    """

    quotation = proposed.strip()
    if quotation and quotation in source_text:
        return quotation
    normalized_source, offsets = _normalized_text_with_offsets(source_text)
    normalized_quote, _ = _normalized_text_with_offsets(quotation)
    if len(normalized_quote) < 8:
        return None
    position = normalized_source.find(normalized_quote)
    if position < 0:
        return None
    start = offsets[position]
    end = offsets[position + len(normalized_quote) - 1] + 1
    resolved = source_text[start:end].strip()
    return resolved or None


class _BudgetLedger:
    def __init__(self, limits: LiteratureRunLimits) -> None:
        self.limits = limits
        self.lock = threading.Lock()
        self.http_attempts = 0
        self.reserved_input = 0
        self.reserved_output = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.pro_calls = 0

    def reserve_unit(self, *, input_tokens: int, output_tokens: int, pro: bool = False) -> None:
        with self.lock:
            if self.input_tokens + self.reserved_input + input_tokens > self.limits.max_input_tokens:
                raise RuntimeError("literature input-token budget is exhausted")
            if self.output_tokens + self.reserved_output + output_tokens > self.limits.max_output_tokens:
                raise RuntimeError("literature output-token budget is exhausted")
            if pro and self.pro_calls >= self.limits.max_pro_calls:
                raise RuntimeError("Pro adjudication budget is exhausted")
            self.reserved_input += input_tokens
            self.reserved_output += output_tokens
            if pro:
                self.pro_calls += 1

    def release_unit(self, *, input_tokens: int, output_tokens: int) -> None:
        """Release an in-flight reservation after its actual usage is recorded.

        Reservations protect concurrent dispatch from overspending; they are not
        cumulative consumption. Keeping completed reservations forever caused
        later papers to be rejected even when measured usage remained far below
        the configured budget.
        """
        with self.lock:
            self.reserved_input = max(0, self.reserved_input - max(0, input_tokens))
            self.reserved_output = max(0, self.reserved_output - max(0, output_tokens))

    def reserve_http_attempt(self) -> bool:
        with self.lock:
            if self.http_attempts >= self.limits.max_http_attempts:
                return False
            self.http_attempts += 1
            return True

    def record_usage(self, *, input_tokens: int, output_tokens: int) -> None:
        with self.lock:
            self.input_tokens += max(0, input_tokens)
            self.output_tokens += max(0, output_tokens)
            if self.input_tokens > self.limits.max_input_tokens:
                raise RuntimeError("literature input-token budget was exceeded")
            if self.output_tokens > self.limits.max_output_tokens:
                raise RuntimeError("literature output-token budget was exceeded")

    def snapshot(self) -> dict[str, int]:
        with self.lock:
            return {
                "http_attempts": self.http_attempts,
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "pro_calls": self.pro_calls,
                "reserved_input_tokens": self.reserved_input,
                "reserved_output_tokens": self.reserved_output,
            }


class LiteratureDiscoveryService:
    def __init__(
        self,
        storage: WorkspaceStorage,
        repository: V14WorkspaceRepository,
        research: ResearchService,
    ) -> None:
        self.storage = storage
        self.repository = repository
        self.search_service = ScholarlySearchService(research, repository)
        self._executor = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="principia-literature"
        )
        self._cancel: dict[str, threading.Event] = {}
        self._pause: dict[str, threading.Event] = {}
        self._futures: dict[str, Future[None]] = {}

    def search_papers(
        self, goal: str, *, area: str = "", target_count: int = 20, timeout: float = 120.0
    ) -> dict[str, Any]:
        return self.search_service.search(
            goal, area=area, target_count=target_count, timeout=timeout
        )

    def update_selection(self, search_id: str, work_ids: list[str]) -> dict[str, Any]:
        return self.search_service.update_selection(search_id, work_ids)

    def list_searches(self) -> list[dict[str, Any]]:
        return self.repository.list_literature_searches()

    def start(
        self,
        *,
        search_id: str,
        policy: ModelPolicy,
        limits: LiteratureRunLimits | None = None,
        api_key: str | None = None,
        provider_transport: Any | None = None,
        acquirer_transport: Any | None = None,
        resolver: Any | None = None,
        resume_from: str = "",
    ) -> JobRecord:
        search = self.repository.literature_search(search_id)
        if search is None:
            raise KeyError(f"unknown literature search: {search_id}")
        if not search.get("selected_work_ids"):
            raise ValueError("select at least one usable paper before acquisition")
        search = dict(search)
        if resume_from:
            previous = self.repository.get_job(resume_from)
            previous_checkpoint = previous.checkpoint or {} if previous is not None else {}
            completed = set(previous_checkpoint.get("completed_work_ids") or [])
            requested = [str(item) for item in previous_checkpoint.get("requested_work_ids") or []]
            incomplete = [item for item in requested if item not in completed]
            if not incomplete:
                parent_job_id = str(previous_checkpoint.get("resume_from") or "")
                if parent_job_id:
                    incomplete = self.repository.job_unit_work_ids(
                        parent_job_id, states=("failed", "running", "queued")
                    )
            if not incomplete:
                incomplete = self.repository.job_unit_work_ids(
                    resume_from, states=("failed", "running", "queued")
                )
            if incomplete:
                # Retry the previous job's durable failed units, not the full
                # original selection. This remains correct across retry chains
                # where an intermediate job completed zero papers.
                search["selected_work_ids"] = incomplete
            else:
                search["selected_work_ids"] = [
                    item for item in search["selected_work_ids"] if item not in completed
                ]
            search["alternate_work_ids"] = [
                item
                for item in search.get("alternate_work_ids") or []
                if item not in completed and item not in search["selected_work_ids"]
            ]
            if not search["selected_work_ids"]:
                raise ValueError("the previous job has no failed or incomplete paper units")
        resolved_limits = limits or LiteratureRunLimits()
        requested_work_ids = [str(item) for item in search["selected_work_ids"]]
        job = JobRecord(
            job_id=f"job:{monotonic_ulid()}",
            kind="literature_discovery",
            provider=policy.provider,
            model=policy.model,
            checkpoint={
                "search_id": search_id,
                "policy": policy.model_dump(mode="json"),
                "limits": resolved_limits.model_dump(mode="json"),
                "resume_from": resume_from,
                "control_state": "running",
                "requested_work_ids": requested_work_ids,
                "completed_work_ids": [],
            },
        )
        self.repository.save_job(job)
        self.repository.append_job_event(
            job.job_id,
            "queued",
            {"search_id": search_id, "paper_count": len(search["selected_work_ids"])},
            event_id=event_id(),
        )
        cancel = threading.Event()
        pause = threading.Event()
        self._cancel[job.job_id] = cancel
        self._pause[job.job_id] = pause
        self._futures[job.job_id] = self._executor.submit(
            self._run,
            job,
            search,
            policy,
            resolved_limits,
            api_key,
            provider_transport,
            acquirer_transport,
            resolver,
            cancel,
            pause,
        )
        return job

    def _save_job(self, job: JobRecord, *, stage: str, progress: float) -> None:
        job.state = "running"
        job.stage = stage
        job.progress = max(0.0, min(1.0, progress))
        job.updated_at = utc_now()
        self.repository.save_job(job)

    def _checkpoint_control(
        self, job: JobRecord, cancel: threading.Event, pause: threading.Event
    ) -> None:
        if cancel.is_set():
            raise InterruptedError("Literature Discovery cancelled")
        while pause.is_set():
            if cancel.wait(0.25):
                raise InterruptedError("Literature Discovery cancelled")
        if job.checkpoint and job.checkpoint.get("control_state") == "paused":
            job.checkpoint["control_state"] = "running"
            self.repository.save_job(job)

    def _run(
        self,
        job: JobRecord,
        search: dict[str, Any],
        policy: ModelPolicy,
        limits: LiteratureRunLimits,
        api_key: str | None,
        provider_transport: Any | None,
        acquirer_transport: Any | None,
        resolver: Any | None,
        cancel: threading.Event,
        pause: threading.Event,
    ) -> None:
        started = time.monotonic()
        ledger = _BudgetLedger(limits)
        selected_ids = [str(item) for item in search["selected_work_ids"]]
        selected_set = set(selected_ids)
        alternate_ids = [
            str(item)
            for item in search.get("alternate_work_ids") or []
            if str(item) not in selected_set
        ]
        work_queue = list(dict.fromkeys([*selected_ids, *alternate_ids]))
        target_papers = len(selected_ids)
        dataset_id = f"dataset:{monotonic_ulid()}"
        dataset_root = self.storage.artifacts_dir / "literature" / dataset_id.replace(":", "-")
        dataset_payload: dict[str, Any] = {
            "dataset_id": dataset_id,
            "search_id": search["search_id"],
            "goal": search["goal"],
            "area": search["area"],
            "state": "running",
            "label": "Local · Public Literature · Unassessed",
            "work_count": len(selected_ids),
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }
        self.repository.save_dataset(dataset_payload, storage_root=str(dataset_root))
        self.repository.replace_dataset_works(
            dataset_id,
            [
                {
                    "work_id": work_id,
                    "selected": work_id in selected_set,
                    "acquisition_status": "pending",
                }
                for work_id in work_queue
            ],
        )
        acquirer = SafeLiteratureAcquirer(
            transport=acquirer_transport, resolver=resolver, timeout=60.0
        )
        provider = None
        if policy.mode != "no_llm":
            provider = OpenAICompatibleProvider(
                policy,
                api_key=api_key,
                transport=provider_transport,
                timeout=120,
                attempt_reserver=ledger.reserve_http_attempt,
                thinking_budget=limits.reasoning_tokens_per_request,
            )
        metrics: dict[str, int] = {
            "paper_count": target_papers,
            "attempted_papers": 0,
            "top_up_papers": 0,
            "processed_papers": 0,
            "full_text_papers": 0,
            "abstract_fallback_papers": 0,
            "failed_papers": 0,
            "raw_drafts": 0,
            "eligible_candidates": 0,
            "quarantined_candidates": 0,
            "duplicate_drafts": 0,
        }
        candidate_ids: list[str] = []
        consecutive_provider_failures = 0
        dataset_bytes = 0
        try:
            for ordinal, work_id in enumerate(work_queue):
                if metrics["processed_papers"] >= target_papers:
                    break
                self._checkpoint_control(job, cancel, pause)
                if time.monotonic() - started > limits.max_wall_seconds:
                    raise RuntimeError("literature job exceeded its wall-clock budget")
                work = self.storage.get_work(work_id)
                if work is None:
                    metrics["failed_papers"] += 1
                    continue
                metrics["attempted_papers"] += 1
                if work_id not in selected_set:
                    metrics["top_up_papers"] += 1
                unit_id = (
                    f"unit:{hashlib.sha256(f'{job.job_id}:{work_id}'.encode()).hexdigest()[:24]}"
                )
                self.repository.save_job_unit(
                    {
                        "unit_id": unit_id,
                        "job_id": job.job_id,
                        "work_id": work_id,
                        "ordinal": ordinal,
                        "state": "running",
                        "attempt_count": 1,
                        "checkpoint": {"stage": "acquire"},
                    }
                )
                self._save_job(
                    job,
                    stage="Acquire",
                    progress=0.05 + 0.25 * ordinal / max(1, len(work_queue)),
                )
                try:
                    acquired, acquisition_id, segments = self._acquire_work(
                        work,
                        dataset_id=dataset_id,
                        dataset_root=dataset_root,
                        dataset_bytes=dataset_bytes,
                        acquirer=acquirer,
                    )
                    dataset_bytes += int(acquired["byte_size"])
                    if acquired["content_kind"] == "full_text":
                        metrics["full_text_papers"] += 1
                    else:
                        metrics["abstract_fallback_papers"] += 1
                except Exception as exc:  # noqa: BLE001
                    metrics["failed_papers"] += 1
                    self.repository.update_dataset_work_status(dataset_id, work_id, "failed")
                    self.repository.save_job_unit(
                        {
                            "unit_id": unit_id,
                            "job_id": job.job_id,
                            "work_id": work_id,
                            "ordinal": ordinal,
                            "state": "failed",
                            "attempt_count": 1,
                            "checkpoint": {"stage": "acquire"},
                            "error": {
                                "category": "acquisition",
                                "message": str(exc)[:500],
                                "retryable": True,
                            },
                        }
                    )
                    self.repository.append_job_event(
                        job.job_id,
                        "paper_failed",
                        {"work_id": work_id, "category": "acquisition"},
                        event_id=event_id(),
                    )
                    continue
                if provider is not None:
                    self._save_job(
                        job,
                        stage="Extract",
                        progress=0.30 + 0.45 * ordinal / max(1, len(work_queue)),
                    )
                    evidence_segments = _select_evidence_segments(segments, search["goal"])
                    input_payload_chars = len(json.dumps(evidence_segments, ensure_ascii=False))
                    ledger.reserve_unit(
                        input_tokens=(input_payload_chars // 2) + 4_000,
                        output_tokens=3_712,
                    )
                    try:
                        generated = provider.generate_candidate_batch(
                            area=search["area"],
                            goal=search["goal"],
                            source_records=[
                                {
                                    "source_key": "source:0",
                                    "title": work.title,
                                    "content_kind": acquired["content_kind"],
                                }
                            ],
                            evidence_segments=[
                                {
                                    "segment_key": item["segment_key"],
                                    "section": item["section"],
                                    "page_start": item.get("page_start"),
                                    "text": item["text"],
                                }
                                for item in evidence_segments
                            ],
                        )
                        consecutive_provider_failures = 0
                    except Exception as exc:  # noqa: BLE001
                        consecutive_provider_failures += 1
                        metrics["failed_papers"] += 1
                        self.repository.update_dataset_work_status(dataset_id, work_id, "failed")
                        self.repository.save_job_unit(
                            {
                                "unit_id": unit_id,
                                "job_id": job.job_id,
                                "work_id": work_id,
                                "ordinal": ordinal,
                                "state": "failed",
                                "attempt_count": 1,
                                "checkpoint": {
                                    "stage": "extract",
                                    "acquisition_id": acquisition_id,
                                },
                                "error": {
                                    "category": "provider",
                                    "message": str(exc)[:500],
                                    "retryable": True,
                                },
                            }
                        )
                        if consecutive_provider_failures >= 5:
                            raise RuntimeError(
                                "provider circuit opened after five consecutive failed papers"
                            ) from exc
                        continue
                    ledger.record_usage(
                        input_tokens=generated.trace.input_tokens,
                        output_tokens=generated.trace.output_tokens,
                    )
                    self.repository.save_provider_usage(job.job_id, ledger.snapshot())
                    self.repository.save_provider_attempt(
                        {
                            "attempt_id": f"attempt:{monotonic_ulid()}",
                            "job_id": job.job_id,
                            "unit_id": unit_id,
                            **generated.trace.model_dump(mode="json"),
                            "state": "succeeded",
                            "retry_index": max(0, generated.trace.transport_attempts - 1),
                            "error_category": "",
                        }
                    )
                    metrics["raw_drafts"] += len(generated.batch.drafts)
                    for draft in generated.batch.drafts:
                        candidate, anchors, reason = _validate_and_materialize_draft(
                            draft=draft,
                            work=work,
                            area=search["area"],
                            goal=search["goal"],
                            job_id=job.job_id,
                            trace=generated.trace,
                            segments=evidence_segments,
                        )
                        if reason:
                            metrics["quarantined_candidates"] += 1
                            self.repository.save_candidate(
                                candidate,
                                source_kind="literature",
                                discovery_job_id=job.job_id,
                                dataset_id=dataset_id,
                                eligibility_status="quarantined",
                                quarantine_reason=reason,
                            )
                            continue
                        canonical, duplicate = self._deduplicate(candidate)
                        if duplicate:
                            metrics["duplicate_drafts"] += 1
                            candidate = canonical
                            previous = (
                                self.repository.candidate_detail(candidate.candidate_id) or {}
                            )
                            metadata = previous.get("local_metadata") or {}
                            self.repository.save_candidate(
                                candidate,
                                source_kind=str(metadata.get("source_kind") or "literature"),
                                discovery_job_id=str(metadata.get("discovery_id") or job.job_id),
                                dataset_id=str(metadata.get("dataset_id") or dataset_id),
                                eligibility_status="eligible",
                            )
                        else:
                            self.repository.save_candidate(
                                candidate,
                                source_kind="literature",
                                discovery_job_id=job.job_id,
                                dataset_id=dataset_id,
                                eligibility_status="eligible",
                            )
                            metrics["eligible_candidates"] += 1
                            candidate_ids.append(candidate.candidate_id)
                        for anchor in anchors:
                            self.repository.save_candidate_evidence(
                                evidence_id=f"ev:{canonical_sha256({'candidate': candidate.candidate_id, 'work': work.id, 'segment': anchor['segment_id'], 'quote': anchor['quotation']})[:24]}",
                                candidate_id=candidate.candidate_id,
                                work_id=work.id,
                                acquisition_id=acquisition_id,
                                segment_id=anchor["segment_id"],
                                role=anchor["role"],
                                excerpt_sha256=hashlib.sha256(
                                    anchor["quotation"].encode()
                                ).hexdigest(),
                                locator={
                                    "section": anchor["section"],
                                    "page_start": anchor.get("page_start"),
                                    "page_end": anchor.get("page_end"),
                                    "quotation": anchor["quotation"],
                                },
                                extraction_trace=generated.trace.model_dump(mode="json"),
                            )
                metrics["processed_papers"] += 1
                self.repository.update_dataset_work_status(
                    dataset_id, work_id, acquired["content_kind"]
                )
                self.repository.save_job_unit(
                    {
                        "unit_id": unit_id,
                        "job_id": job.job_id,
                        "work_id": work_id,
                        "ordinal": ordinal,
                        "state": "succeeded",
                        "attempt_count": 1,
                        "checkpoint": {"stage": "complete", "acquisition_id": acquisition_id},
                        "result": {"content_kind": acquired["content_kind"]},
                    }
                )
                if job.checkpoint is not None:
                    job.checkpoint.setdefault("completed_work_ids", []).append(work_id)
                self.repository.append_job_event(
                    job.job_id,
                    "paper_completed",
                    {"work_id": work_id, "metrics": dict(metrics)},
                    event_id=event_id(),
                )
                self.repository.save_job(job)
            self._save_job(job, stage="Challenge", progress=0.82)
            self._checkpoint_control(job, cancel, pause)
            self._save_job(job, stage="Map", progress=0.92)
            usable_target_met = metrics["processed_papers"] >= target_papers
            dataset_payload.update(
                {
                    "state": "ready" if usable_target_met else "partial",
                    "metrics": metrics,
                    "updated_at": utc_now(),
                }
            )
            self.repository.save_dataset(dataset_payload, storage_root=str(dataset_root))
            job.state = "succeeded"
            job.stage = "Complete"
            job.progress = 1.0
            job.result = {
                "search_id": search["search_id"],
                "dataset_id": dataset_id,
                **metrics,
                "usable_target_met": usable_target_met,
                "candidate_count": metrics["eligible_candidates"],
                "candidate_ids": candidate_ids[:100],
                "usage": ledger.snapshot(),
                "label": "Local · Public Literature · Unassessed",
                "message": (
                    "No-LLM acquisition completed; prose Candidates were not fabricated."
                    if policy.mode == "no_llm"
                    else "Literature Discovery completed. All displayed Candidates remain unassessed."
                ),
            }
            job.updated_at = utc_now()
            self.repository.save_job(job)
            self.repository.append_job_event(
                job.job_id, "completed", job.result, event_id=event_id()
            )
        except InterruptedError:
            job.state = "cancelled"
            job.stage = "cancelled"
            job.updated_at = utc_now()
            self.repository.save_job(job)
        except Exception as exc:  # noqa: BLE001
            job.state = "failed"
            job.stage = "failed"
            job.error = {
                "code": "literature_discovery_failed",
                "category": "provider" if policy.mode != "no_llm" else "acquisition",
                "message": str(exc)[:500],
                "retryable": True,
            }
            job.updated_at = utc_now()
            self.repository.save_job(job)
            self.repository.append_job_event(
                job.job_id,
                "failed",
                {"error": job.error, "usage": ledger.snapshot()},
                event_id=event_id(),
            )

    def _acquire_work(
        self,
        work: WorkItem,
        *,
        dataset_id: str,
        dataset_root: Path,
        dataset_bytes: int,
        acquirer: SafeLiteratureAcquirer,
    ) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
        acquired: dict[str, Any] | None = None
        location_id: str | None = None
        errors: list[str] = []
        for location in open_access_locations(work):
            location_id = self.repository.save_scholarly_location({**location, "work_id": work.id})
            try:
                acquired = acquirer.download(location, dataset_bytes=dataset_bytes)
                acquired["content_kind"] = "full_text"
                break
            except Exception as exc:  # noqa: BLE001
                errors.append(type(exc).__name__)
        if acquired is None:
            abstract = work.abstract.strip()
            if not abstract:
                raise ValueError("paper has neither permitted full text nor a usable abstract")
            body = abstract.encode()
            acquired = {
                "final_url": work.url if work.url.startswith("https://") else "",
                "mime_type": "text/plain",
                "bytes": body,
                "text": abstract,
                "pages": [{"page": None, "section": "abstract", "text": abstract}],
                "byte_size": len(body),
                "byte_sha256": hashlib.sha256(body).hexdigest(),
                "text_sha256": hashlib.sha256(body).hexdigest(),
                "access_basis": "provider_public_abstract",
                "manuscript_version": "abstract",
                "license": "metadata-provider-terms",
                "content_kind": "abstract",
                "full_text_failures": errors,
            }
            location_id = None
        paths = write_private_acquisition(dataset_root, work_id=work.id, acquired=acquired)
        acquisition_id = f"acq:{canonical_sha256({'dataset': dataset_id, 'work': work.id})[:24]}"
        acquisition_payload = {
            "acquisition_id": acquisition_id,
            "dataset_id": dataset_id,
            "work_id": work.id,
            "location_id": location_id,
            "status": "usable",
            "content_kind": acquired["content_kind"],
            "final_url": acquired["final_url"],
            "mime_type": acquired["mime_type"],
            "byte_sha256": acquired["byte_sha256"],
            "text_sha256": acquired["text_sha256"],
            "byte_size": acquired["byte_size"],
            "access_basis": acquired["access_basis"],
            "manuscript_version": acquired["manuscript_version"],
            "license": acquired["license"],
            "private_paths": paths,
            "created_at": utc_now(),
        }
        self.repository.save_acquisition(acquisition_payload)
        segments = _build_segments(work, acquisition_id, acquired["pages"])
        self.repository.replace_segments(acquisition_id, work.id, segments)
        return acquired, acquisition_id, segments

    def _deduplicate(self, candidate: CandidatePrinciple) -> tuple[CandidatePrinciple, bool]:
        fingerprint = canonical_sha256(
            {
                "claim": " ".join(candidate.claim.casefold().split()),
                "kind": candidate.kind.value,
                "scope": " ".join(candidate.scope.statement.casefold().split()),
            }
        )
        exact = self.repository.candidate_by_fingerprint(fingerprint)
        if exact is not None:
            return _merge_candidate_sources(exact, candidate), True
        candidate_tokens = set(_WORD_RE.findall(candidate.claim.casefold()))
        for row in self.repository.candidate_claims(candidate.area):
            other = set(_WORD_RE.findall(str(row["claim"]).casefold()))
            union = candidate_tokens | other
            similarity = len(candidate_tokens & other) / len(union) if union else 0.0
            if similarity >= 0.92:
                return _merge_candidate_sources(
                    CandidatePrinciple.model_validate_json(row["payload_json"]), candidate
                ), True
        return candidate, False

    def pause(self, job_id: str) -> JobRecord:
        job = self.repository.get_job(job_id)
        if job is None or job.kind != "literature_discovery":
            raise KeyError(f"unknown Literature Discovery job: {job_id}")
        if job.state != "running":
            return job
        self._pause.setdefault(job_id, threading.Event()).set()
        job.stage = "paused"
        if job.checkpoint is not None:
            job.checkpoint["control_state"] = "paused"
        job.updated_at = utc_now()
        self.repository.save_job(job)
        return job

    def continue_job(self, job_id: str) -> JobRecord:
        job = self.repository.get_job(job_id)
        if job is None or job.kind != "literature_discovery":
            raise KeyError(f"unknown Literature Discovery job: {job_id}")
        pause = self._pause.get(job_id)
        if pause is not None and job.state == "running":
            pause.clear()
            job.stage = "running"
            if job.checkpoint is not None:
                job.checkpoint["control_state"] = "running"
            job.updated_at = utc_now()
            self.repository.save_job(job)
        return job

    def retry_failed(self, job_id: str) -> JobRecord:
        job = self.repository.get_job(job_id)
        if job is None or job.kind != "literature_discovery":
            raise KeyError(f"unknown Literature Discovery job: {job_id}")
        retryable_terminal = job.state in {"failed", "interrupted", "cancelled"}
        retryable_partial = (
            job.state == "succeeded" and self.repository.job_unit_count(job_id, state="failed") > 0
        )
        if not (retryable_terminal or retryable_partial):
            raise ValueError(
                "only failed, interrupted, cancelled, or partially succeeded jobs can be retried"
            )
        checkpoint = job.checkpoint or {}
        return self.start(
            search_id=str(checkpoint["search_id"]),
            policy=ModelPolicy.model_validate(checkpoint["policy"]),
            limits=LiteratureRunLimits.model_validate(checkpoint["limits"]),
            resume_from=job_id,
        )

    def cancel(self, job_id: str) -> JobRecord:
        job = self.repository.get_job(job_id)
        if job is None:
            raise KeyError(f"unknown job: {job_id}")
        if job.state in {"succeeded", "failed", "cancelled", "interrupted"}:
            return job
        job.state = "cancelling"
        job.stage = "cancelling"
        job.updated_at = utc_now()
        self.repository.save_job(job)
        self._cancel.setdefault(job_id, threading.Event()).set()
        self._pause.setdefault(job_id, threading.Event()).clear()
        return job


def _build_segments(
    work: WorkItem, acquisition_id: str, pages: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for page in pages:
        text = str(page.get("text") or "").strip()
        for offset in range(0, len(text), 6_000):
            chunk = text[offset : offset + 6_000].strip()
            if not chunk:
                continue
            ordinal = len(output)
            segment_id = (
                f"seg:{hashlib.sha256(f'{acquisition_id}:{ordinal}'.encode()).hexdigest()[:24]}"
            )
            output.append(
                {
                    "segment_id": segment_id,
                    "segment_key": (
                        "evidence:"
                        f"{hashlib.sha256(acquisition_id.encode()).hexdigest()[:12]}:{ordinal}"
                    ),
                    "work_id": work.id,
                    "section": str(page.get("section") or "full_text"),
                    "page_start": page.get("page"),
                    "page_end": page.get("page"),
                    "text": chunk,
                    "text_sha256": hashlib.sha256(chunk.encode()).hexdigest(),
                }
            )
    return output


def _select_evidence_segments(
    segments: list[dict[str, Any]], goal: str, *, max_chars: int = 24_000
) -> list[dict[str, Any]]:
    prompt_segments: list[dict[str, Any]] = []
    for segment in segments:
        text = str(segment["text"])
        cursor = 0
        chunk_index = 0
        while cursor < len(text):
            end = min(len(text), cursor + 1_600)
            if end < len(text):
                boundary = text.rfind(". ", cursor + 800, end)
                if boundary <= cursor:
                    boundary = text.rfind("\n", cursor + 800, end)
                if boundary <= cursor:
                    boundary = text.rfind(" ", cursor + 1_300, end)
                if boundary > cursor:
                    end = boundary + (1 if text[boundary] == "\n" else 2)
            raw = text[cursor:end]
            leading = len(raw) - len(raw.lstrip())
            chunk = raw.strip()
            if chunk:
                prompt_segments.append(
                    {
                        **segment,
                        "segment_key": f"{segment['segment_key']}:chunk:{chunk_index}",
                        "text": chunk,
                        "source_character_start": cursor + leading,
                        "source_character_end": cursor + leading + len(chunk),
                    }
                )
                chunk_index += 1
            cursor = max(end, cursor + 1)
    goal_terms = set(_WORD_RE.findall(goal.casefold()))
    if goal_terms:
        ranked = sorted(
            prompt_segments,
            key=lambda item: (
                -len(goal_terms & set(_WORD_RE.findall(str(item["text"]).casefold()))),
                0
                if _section_bucket(str(item["section"]))
                in {"abstract", "introduction", "results", "discussion", "conclusion"}
                else 1,
                item["segment_key"],
            ),
        )
    else:
        # Broad extraction must not silently become "read the beginning of the
        # file."  Round-robin across scientific sections first, ranking within
        # each section by deterministic relation-bearing language.
        section_order = [
            "abstract",
            "methods",
            "results",
            "discussion",
            "conclusion",
            "introduction",
            "other",
        ]
        buckets: dict[str, list[dict[str, Any]]] = {name: [] for name in section_order}
        for item in prompt_segments:
            buckets[_section_bucket(str(item["section"]))].append(item)
        for items in buckets.values():
            items.sort(
                key=lambda item: (
                    -_scientific_signal_score(str(item["text"])),
                    item["segment_key"],
                )
            )
        ranked = []
        while any(buckets.values()):
            for section in section_order:
                if buckets[section]:
                    ranked.append(buckets[section].pop(0))
    output: list[dict[str, Any]] = []
    used = 0
    for item in ranked:
        remaining = max_chars - used
        if remaining <= 0:
            break
        projected = dict(item)
        projected["text"] = str(item["text"])[:remaining]
        if projected["text"].strip():
            output.append(projected)
            used += len(projected["text"])
    return sorted(output, key=lambda item: item["segment_key"])


def _section_bucket(section: str) -> str:
    normalized = section.casefold().replace("_", " ").strip()
    for name, aliases in (
        ("abstract", ("abstract", "summary")),
        ("methods", ("method", "materials", "experimental", "procedure")),
        ("results", ("result", "finding", "observation")),
        ("discussion", ("discussion", "interpretation")),
        ("conclusion", ("conclusion", "implication")),
        ("introduction", ("introduction", "background")),
    ):
        if any(alias in normalized for alias in aliases):
            return name
    return "other"


def _scientific_signal_score(text: str) -> int:
    tokens = set(_WORD_RE.findall(text.casefold()))
    relation_terms = {
        "associated",
        "causes",
        "decreases",
        "depends",
        "effect",
        "increases",
        "improves",
        "inhibits",
        "mechanism",
        "predicts",
        "reduces",
        "requires",
        "results",
        "significant",
        "tradeoff",
    }
    return len(tokens & relation_terms)


def _validate_and_materialize_draft(
    *,
    draft: Any,
    work: WorkItem,
    area: str,
    goal: str,
    job_id: str,
    trace: Any,
    segments: list[dict[str, Any]],
) -> tuple[CandidatePrinciple, list[dict[str, Any]], str]:
    reasons: list[str] = []
    if set(draft.source_keys) != {"source:0"}:
        reasons.append("unknown_source_reference")
    combined = f"{draft.title}\n{draft.claim}\n{draft.scope}\n{draft.falsifier}".casefold()
    if any(re.search(pattern, combined, flags=re.IGNORECASE) for pattern in _TEMPLATE_PATTERNS):
        reasons.append("template_or_schema_echo")
    if len(_WORD_RE.findall(draft.claim)) < 7:
        reasons.append("insufficient_scientific_specificity")
    segment_by_key = {item["segment_key"]: item for item in segments}
    anchors: list[dict[str, Any]] = []
    discarded_unverifiable_anchors = 0
    for evidence in draft.evidence:
        segment = segment_by_key.get(evidence.segment_key)
        if segment is None:
            reasons.append("unknown_evidence_segment")
            continue
        quotation = _resolve_evidence_quotation(str(segment["text"]), evidence.quotation)
        if quotation is None:
            discarded_unverifiable_anchors += 1
            continue
        anchors.append(
            {
                **segment,
                "quotation": quotation,
                "role": evidence.role,
            }
        )
    if not anchors:
        reasons.append("missing_verified_evidence_anchor")
        if discarded_unverifiable_anchors:
            reasons.append("invented_or_inexact_quotation")
    cited_text = "\n".join(item["quotation"] for item in anchors)
    unsupported = [token for token in _NUMBER_RE.findall(draft.claim) if token not in cited_text]
    if unsupported:
        reasons.append("unsupported_numeric_or_formula_claim")
    reasons.extend(
        _semantic_quality_reasons(
            draft=draft,
            work=work,
            goal=goal,
            cited_text=cited_text,
        )
    )
    now = utc_now()
    candidate = CandidatePrinciple(
        candidate_id=candidate_id(),
        area=area,
        title=draft.title.strip(),
        claim=draft.claim.strip(),
        kind=draft.kind,
        scope=PrincipleScope(statement=draft.scope.strip()),
        falsifier=draft.falsifier.strip(),
        source_references=[
            WorkReference(
                work_id=work.id,
                title=work.title,
                url=work.url if work.url.startswith("https://") else "",
                doi=work.doi,
                role="evidence",
                public=True,
            )
        ],
        generation_trace=[
            GenerationTrace(
                event_id=event_id(),
                operation=TraceOperation.EXTRACT,
                actor="principia-provider",
                provider=trace.provider,
                model=trace.model,
                prompt_template=trace.prompt_template,
                prompt_sha256=trace.prompt_sha256,
                input_sha256=trace.input_sha256,
                output_sha256=trace.output_sha256,
                run_id=job_id,
                latency_ms=trace.latency_ms,
                input_tokens=trace.input_tokens,
                output_tokens=trace.output_tokens,
                retries=min(2, max(0, trace.transport_attempts - trace.attempts)),
            )
        ],
        created_at=now,
        updated_at=now,
    )
    return candidate, anchors, ",".join(dict.fromkeys(reasons))


def _merge_candidate_sources(
    canonical: CandidatePrinciple, duplicate: CandidatePrinciple
) -> CandidatePrinciple:
    known = {item.work_id for item in canonical.source_references}
    additions = [item for item in duplicate.source_references if item.work_id not in known]
    if additions:
        canonical.source_references.extend(additions)
        canonical.updated_at = utc_now()
    return canonical
