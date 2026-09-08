from __future__ import annotations

import hashlib
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..domain import (
    CandidatePrinciple,
    ChallengeDecisionBatch,
    EvidenceClaimAtom,
    EvidenceClaimAtomBatch,
    GenerationTrace,
    JobRecord,
    LiteratureRunLimits,
    PrincipleKind,
    PrincipleScope,
    QualityEvaluation,
    QualityReason,
    QualityVerdict,
    ScientificArgument,
    ScientificArgumentBatch,
    TraceOperation,
    WorkReference,
    candidate_id,
    canonical_sha256,
    concise_principle_title,
    event_id,
    monotonic_ulid,
)
from ..models import WorkItem, utc_now
from ..persistence import V14WorkspaceRepository
from ..providers import (
    ModelPolicy,
    OpenAICompatibleProvider,
    ProviderBudgetExceeded,
    ProviderOutputError,
    ProviderRequestError,
)
from ..providers.openai_compatible import ScientificGeneration
from ..storage import WorkspaceStorage
from .areas import CandidateAreaSuggestionService
from .consolidation import CandidateConsolidationService
from .literature_discovery import _BudgetLedger, _select_evidence_segments
from .quality import ScientificQualityGate, stable_atom_id

_KIND_BY_CLASS = {
    "empirical_association": PrincipleKind.EMPIRICAL,
    "causal_mechanism": PrincipleKind.MECHANISTIC,
    "design_rule_or_intervention": PrincipleKind.HEURISTIC,
    "boundary_or_tradeoff": PrincipleKind.EMPIRICAL,
    "formal_proposition": PrincipleKind.THEOREM,
}


@dataclass(frozen=True)
class _PrefetchedPaper:
    atoms: list[EvidenceClaimAtom]
    raw_atom_count: int
    atoms_cached: bool
    arguments_generation: ScientificGeneration | None = None
    challenge_generation: ScientificGeneration | None = None


class CandidateExtractionService:
    def __init__(
        self,
        storage: WorkspaceStorage,
        repository: V14WorkspaceRepository,
        *,
        principles_export_root: str | Path | None = None,
        relation_rebuild: Callable[[], JobRecord] | None = None,
    ) -> None:
        self.storage = storage
        self.repository = repository
        self.quality = ScientificQualityGate()
        self.consolidation = CandidateConsolidationService(repository)
        self.area_suggestions = CandidateAreaSuggestionService(repository)
        self.relation_rebuild = relation_rebuild
        self.principles_export_root = (
            Path(principles_export_root).expanduser().resolve()
            if principles_export_root is not None
            else None
        )
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="principia-extract")
        self._cancel: dict[str, threading.Event] = {}
        self._pause: dict[str, threading.Event] = {}
        self._futures: dict[str, Future[None]] = {}

    def revalidate_deterministic_quality(self) -> dict[str, int]:
        """Fail closed when current deterministic safeguards reject older output."""

        checked = 0
        held_back = 0
        for record in self.repository.deterministic_revalidation_inputs():
            atoms = record["atoms"]
            if not atoms:
                continue
            checked += 1
            reasons = self.quality.validate_argument(
                record["argument"],
                atoms=atoms,
                independent_work_ids=record["work_ids"],
                goal="",
            )
            if record["research_focus"]:
                focus_reasons = self.quality.validate_argument(
                    record["argument"],
                    atoms=atoms,
                    independent_work_ids=record["work_ids"],
                    goal=record["research_focus"],
                )
                self.repository.set_candidate_context_relevance(
                    record["candidate_id"],
                    goal_id=record["goal_id"],
                    relevance=(
                        "outside_focus" if QualityReason.OFF_GOAL in focus_reasons else "matches"
                    ),
                )
            if not reasons:
                continue
            evidence_digest = canonical_sha256([atom.model_dump(mode="json") for atom in atoms])
            self.repository.save_quality_evaluation(
                QualityEvaluation(
                    evaluation_id=f"eval:{monotonic_ulid()}",
                    candidate_id=record["candidate_id"],
                    argument_revision=record["revision"],
                    verdict=QualityVerdict.QUARANTINED,
                    reason_codes=reasons,
                    evidence_digest=evidence_digest,
                    assessor="deterministic",
                    note="Rechecked after deterministic scientific safeguards were strengthened.",
                    created_at=utc_now(),
                )
            )
            self.repository.set_candidate_quality_state(
                record["candidate_id"],
                quality_state="quarantined",
                eligibility_status="quarantined",
                reason=",".join(item.value for item in reasons),
            )
            held_back += 1
        return {"checked": checked, "held_back": held_back}

    def start(
        self,
        *,
        source_id: str,
        source_revision: int,
        document_ids: list[str],
        selection_mode: str,
        goal: str,
        area: str,
        policy: ModelPolicy,
        limits: LiteratureRunLimits,
        goal_id: str = "",
        api_key: str | None = None,
        provider_transport: Any | None = None,
        resume_from: str = "",
    ) -> JobRecord:
        source = self.repository.source(source_id)
        if source is None:
            raise KeyError(f"unknown Local source: {source_id}")
        if int(source["revision"]) != int(source_revision):
            raise ValueError(
                "the Local source changed; review and confirm the paper selection again"
            )
        if selection_mode not in {"exact", "all"}:
            raise ValueError("selection_mode must be exact or all")
        research_focus = " ".join(goal.split())
        category = area or "uncategorized"
        resolved_goal_id = ""
        if goal_id:
            selected_goal = self.repository.research_goal(goal_id)
            if selected_goal is None or selected_goal["status"] == "archived":
                raise ValueError("the selected Research Goal no longer exists")
            if selected_goal["source_id"] and selected_goal["source_id"] != source_id:
                raise ValueError("the selected Research Goal belongs to another private folder")
            research_focus = research_focus or str(selected_goal["goal"])
            category = str(selected_goal["area"] or category)
            resolved_goal_id = self.repository.resolve_research_goal(
                source_id=source_id,
                goal=str(selected_goal["goal"]),
                area=str(selected_goal["area"]),
                goal_id=goal_id,
            )
        elif research_focus:
            resolved_goal_id = self.repository.resolve_research_goal(
                source_id=source_id,
                goal=research_focus,
                area=category,
            )
        extraction_mode = "focus_guided" if research_focus else "source_driven"
        if selection_mode == "all":
            page = self.repository.source_documents(source_id, limit=100, extractable=True)
            selected = [str(item["document_id"]) for item in page["items"]]
            while page["next_cursor"]:
                page = self.repository.source_documents(
                    source_id,
                    limit=100,
                    cursor=str(page["next_cursor"]),
                    extractable=True,
                )
                selected.extend(str(item["document_id"]) for item in page["items"])
        else:
            selected = list(dict.fromkeys(document_ids))
        if not selected:
            raise ValueError("select at least one extractable paper")
        documents = self.repository.extraction_documents(source_id, selected)
        if any(not item["extraction_eligible"] or not item["segments"] for item in documents):
            raise ValueError("the selection contains a paper without extractable text")
        completed: list[str] = []
        if resume_from:
            previous = self.repository.get_job(resume_from)
            if previous is None or previous.kind != "local_extraction":
                raise KeyError(f"unknown Local extraction job: {resume_from}")
            completed = list((previous.checkpoint or {}).get("completed_document_ids") or [])
            documents = [item for item in documents if item["document_id"] not in completed]
            if not documents:
                raise ValueError("the selected extraction has no incomplete documents to retry")
        initial_metrics = {
            "selected_documents": len(documents),
            "processed_documents": 0,
            "raw_atoms": 0,
            "cached_atom_documents": 0,
            "raw_arguments": 0,
            "eligible_candidates": 0,
            "quarantined_candidates": 0,
            "duplicate_candidates": 0,
            "failed_documents": 0,
            "candidate_count": 0,
            "candidate_ids": [],
            "usage": {
                "http_attempts": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "pro_calls": 0,
            },
            "quality_policy": "scientific-principle-v2",
        }
        job = JobRecord(
            job_id=f"job:{monotonic_ulid()}",
            kind="local_extraction",
            state="queued",
            stage="queued",
            progress=0,
            provider=policy.provider,
            model=policy.model,
            total_units=len(documents),
            last_activity_at=utc_now(),
            status_message="Waiting to extract selected papers",
            checkpoint={
                "source_id": source_id,
                "source_revision": source_revision,
                "document_ids": selected,
                "goal": research_focus,
                "goal_id": resolved_goal_id,
                "area": category,
                "extraction_mode": extraction_mode,
                "policy": policy.model_dump(mode="json"),
                "limits": limits.model_dump(mode="json"),
                "quality_policy": "scientific-principle-v2",
                "completed_document_ids": completed,
                "resume_from": resume_from,
            },
            result=initial_metrics,
        )
        self.repository.save_job(job)
        self.repository.append_job_event(
            job.job_id,
            "queued",
            {"stage": job.stage, "message": job.status_message},
            event_id=event_id(),
        )
        selection_id = f"selection:{monotonic_ulid()}"
        selection_digest = canonical_sha256(
            {
                "source_id": source_id,
                "source_revision": source_revision,
                "document_ids": selected,
            }
        )
        with self.repository.connect() as conn:
            conn.execute(
                """
                INSERT INTO local_extraction_selections(
                    selection_id, job_id, source_id, source_revision,
                    selection_mode, document_ids_json, selection_digest,
                    goal_id, goal, area, quality_policy, created_at,
                    research_focus, extraction_mode, context_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          'scientific-principle-v2', ?, ?, ?, ?)
                """,
                (
                    selection_id,
                    job.job_id,
                    source_id,
                    source_revision,
                    selection_mode,
                    __import__("json").dumps(selected, separators=(",", ":")),
                    selection_digest,
                    resolved_goal_id or None,
                    research_focus,
                    category,
                    utc_now(),
                    research_focus,
                    extraction_mode,
                    __import__("json").dumps(
                        {
                            "research_goal_id": resolved_goal_id or None,
                            "research_focus": research_focus or None,
                        },
                        separators=(",", ":"),
                    ),
                ),
            )
        cancel = threading.Event()
        pause = threading.Event()
        self._cancel[job.job_id] = cancel
        self._pause[job.job_id] = pause
        self._futures[job.job_id] = self._executor.submit(
            self._run,
            job,
            documents,
            source_id,
            resolved_goal_id,
            research_focus,
            category,
            policy,
            limits,
            resume_from,
            api_key,
            provider_transport,
            cancel,
            pause,
        )
        return job

    def _run(
        self,
        job: JobRecord,
        documents: list[dict[str, Any]],
        source_id: str,
        goal_id: str,
        goal: str,
        area: str,
        policy: ModelPolicy,
        limits: LiteratureRunLimits,
        resume_from: str,
        api_key: str | None,
        provider_transport: Any | None,
        cancel: threading.Event,
        pause: threading.Event,
    ) -> None:
        started = time.monotonic()
        ledger = _BudgetLedger(limits)
        provider = (
            OpenAICompatibleProvider(
                policy,
                api_key=api_key,
                transport=provider_transport,
                timeout=120,
                attempt_reserver=ledger.reserve_http_attempt,
                thinking_budget=limits.reasoning_tokens_per_request,
            )
            if policy.mode != "no_llm"
            else None
        )
        metrics = {
            "selected_documents": len(documents),
            "processed_documents": 0,
            "raw_atoms": 0,
            "cached_atom_documents": 0,
            "raw_arguments": 0,
            "eligible_candidates": 0,
            "quarantined_candidates": 0,
            "duplicate_candidates": 0,
            "failed_documents": 0,
            "parallel_workers": min(max(1, limits.concurrency), max(1, len(documents))),
        }
        candidate_ids: list[str] = []
        parallel_workers = int(metrics["parallel_workers"])
        atom_pool: ThreadPoolExecutor | None = None
        provider_futures: dict[str, Future[_PrefetchedPaper]] = {}

        def unit_id_for(document: dict[str, Any]) -> str:
            return (
                "unit:"
                + canonical_sha256({"job": job.job_id, "document": document["document_id"]})[:24]
            )

        # Provider traces reference these units. Create every foreign-key target
        # before any concurrent request can finish and persist its trace.
        for ordinal, document in enumerate(documents):
            self.repository.save_job_unit(
                {
                    "unit_id": unit_id_for(document),
                    "job_id": job.job_id,
                    "work_id": document["work_id"],
                    "ordinal": ordinal,
                    "state": "queued",
                    "attempt_count": 0,
                    "checkpoint": {
                        "document_id": document["document_id"],
                        "stage": "queued",
                    },
                }
            )

        def prefetch_provider_stages(document: dict[str, Any]) -> _PrefetchedPaper:
            """Run every paid, paper-local stage concurrently and persist its trace."""

            if cancel.is_set():
                raise InterruptedError
            while pause.is_set() and not cancel.is_set():
                cancel.wait(0.2)
            existing_atoms = self.repository.evidence_atoms_for_document(document["document_id"])
            work = WorkItem.model_validate(document["work"])
            segments = _select_evidence_segments(document["segments"], goal)
            estimated_input = max(1, sum(len(str(item["text"])) for item in segments) // 3)
            reserved_input = estimated_input * (3 if existing_atoms else 4)
            reserved_output = 13_000 if existing_atoms else 18_000
            ledger.reserve_unit(
                input_tokens=reserved_input,
                output_tokens=reserved_output,
            )
            worker_provider = OpenAICompatibleProvider(
                policy,
                api_key=api_key,
                transport=provider_transport,
                timeout=120,
                attempt_reserver=ledger.reserve_http_attempt,
                thinking_budget=limits.reasoning_tokens_per_request,
            )
            unit_id = unit_id_for(document)
            try:
                if existing_atoms:
                    atoms = existing_atoms
                    raw_atom_count = len(atoms)
                else:
                    atoms_generation = worker_provider.extract_evidence_atoms(
                        area=area,
                        goal=goal,
                        source_records=[
                            {
                                "source_key": "source:0",
                                "work_id": work.id,
                                "title": work.title,
                            }
                        ],
                        evidence_segments=segments,
                    )
                    ledger.record_usage(
                        input_tokens=atoms_generation.trace.input_tokens,
                        output_tokens=atoms_generation.trace.output_tokens,
                    )
                    self._save_provider_trace(
                        job_id=job.job_id,
                        unit_id=unit_id,
                        trace=atoms_generation.trace,
                    )
                    batch = EvidenceClaimAtomBatch.model_validate(atoms_generation.value)
                    raw_atom_count = len(batch.atoms)
                    atoms = [
                        atom.model_copy(
                            update={
                                "atom_id": stable_atom_id(
                                    work_id=work.id,
                                    source_key=atom.source_key,
                                    faithful_claim=atom.faithful_claim,
                                )
                            }
                        )
                        for atom in batch.atoms
                    ]
                failures = self.quality.validate_atoms(
                    atoms,
                    segment_text={str(item["segment_key"]): str(item["text"]) for item in segments},
                    permitted_source_keys={"source:0"},
                )
                valid_atoms = [atom for atom in atoms if atom.atom_id not in failures]
                for atom in valid_atoms:
                    self.repository.save_evidence_atom(
                        atom,
                        work_id=work.id,
                        source_document_id=document["document_id"],
                    )
                if not valid_atoms:
                    return _PrefetchedPaper(
                        atoms=[],
                        raw_atom_count=raw_atom_count,
                        atoms_cached=bool(existing_atoms),
                    )
                arguments_generation = worker_provider.normalize_scientific_arguments(
                    area=area,
                    goal=goal,
                    atoms=[atom.model_dump(mode="json") for atom in valid_atoms],
                )
                ledger.record_usage(
                    input_tokens=arguments_generation.trace.input_tokens,
                    output_tokens=arguments_generation.trace.output_tokens,
                )
                self._save_provider_trace(
                    job_id=job.job_id,
                    unit_id=unit_id,
                    trace=arguments_generation.trace,
                )
                argument_batch = ScientificArgumentBatch.model_validate(arguments_generation.value)
                if not argument_batch.arguments:
                    return _PrefetchedPaper(
                        atoms=valid_atoms,
                        raw_atom_count=raw_atom_count,
                        atoms_cached=bool(existing_atoms),
                        arguments_generation=arguments_generation,
                    )
                challenge_generation = worker_provider.challenge_scientific_arguments(
                    area=area,
                    goal=goal,
                    atoms=[atom.model_dump(mode="json") for atom in valid_atoms],
                    arguments=[
                        argument.model_dump(mode="json") for argument in argument_batch.arguments
                    ],
                )
                ledger.record_usage(
                    input_tokens=challenge_generation.trace.input_tokens,
                    output_tokens=challenge_generation.trace.output_tokens,
                )
                self._save_provider_trace(
                    job_id=job.job_id,
                    unit_id=unit_id,
                    trace=challenge_generation.trace,
                )
                self.repository.append_job_event(
                    job.job_id,
                    "provider_unit_ready",
                    {
                        "document_id": document["document_id"],
                        "message": f"Model stages finished for {work.title}",
                        "atom_count": len(valid_atoms),
                        "argument_count": len(argument_batch.arguments),
                    },
                    event_id=event_id(),
                )
                return _PrefetchedPaper(
                    atoms=valid_atoms,
                    raw_atom_count=raw_atom_count,
                    atoms_cached=bool(existing_atoms),
                    arguments_generation=arguments_generation,
                    challenge_generation=challenge_generation,
                )
            finally:
                worker_provider.close()
                ledger.release_unit(
                    input_tokens=reserved_input,
                    output_tokens=reserved_output,
                )

        if provider is not None and documents:
            atom_pool = ThreadPoolExecutor(
                max_workers=parallel_workers,
                thread_name_prefix="principia-extract-api",
            )
            for document in documents:
                provider_futures[document["document_id"]] = atom_pool.submit(
                    prefetch_provider_stages, document
                )

        def failure_payload(exc: Exception, *, code: str) -> dict[str, Any]:
            if isinstance(exc, ProviderRequestError):
                return {
                    "code": code,
                    "category": exc.category,
                    "message": str(exc),
                    "retryable": exc.retryable,
                }
            if isinstance(exc, ProviderBudgetExceeded):
                return {
                    "code": "extraction_budget_exhausted",
                    "category": "budget",
                    "message": (
                        "The extraction request budget was exhausted. Review the limits, then "
                        "retry only the unfinished papers."
                    ),
                    "retryable": False,
                }
            if isinstance(exc, ProviderOutputError):
                if "relationship-bearing evidence" in str(exc):
                    return {
                        "code": "argument_normalization_empty",
                        "category": "output_validation",
                        "message": (
                            "The model found source evidence but could not convert it into a "
                            "supported reusable finding after a recovery pass. Retry this paper "
                            "or enter another compatible model ID."
                        ),
                        "retryable": True,
                    }
                return {
                    "code": "provider_output_invalid",
                    "category": "output_validation",
                    "message": (
                        "The model did not return valid structured evidence after one repair. "
                        "Retry this paper or enter another compatible model ID."
                    ),
                    "retryable": True,
                }
            return {
                "code": code,
                "category": "provider",
                "message": str(exc),
                "retryable": True,
            }

        def persist_progress(completed_units: int) -> None:
            job.progress = min(0.99, completed_units / max(1, len(documents)))
            job.completed_units = completed_units
            job.total_units = len(documents)
            job.elapsed_seconds = round(time.monotonic() - started, 1)
            job.eta_seconds = (
                round(job.elapsed_seconds / completed_units * (len(documents) - completed_units), 1)
                if completed_units >= 2 and completed_units < len(documents)
                else None
            )
            job.last_activity_at = utc_now()
            job.status_message = f"Checked {completed_units} of {len(documents)} selected papers"
            job.result = {
                **metrics,
                "candidate_count": len(set(candidate_ids)),
                "candidate_ids": list(dict.fromkeys(candidate_ids)),
                "usage": ledger.snapshot(),
                "quality_policy": "scientific-principle-v2",
            }
            job.updated_at = job.last_activity_at
            self.repository.save_job(job)
            self.repository.append_job_event(
                job.job_id,
                "progress",
                {
                    "stage": job.stage,
                    "message": job.status_message,
                    "progress": job.progress,
                    "completed_units": job.completed_units,
                    "total_units": job.total_units,
                    "eta_seconds": job.eta_seconds,
                },
                event_id=event_id(),
            )

        heartbeat_stop = threading.Event()

        def heartbeat() -> None:
            while not heartbeat_stop.wait(3.0):
                self.repository.heartbeat_job(
                    job.job_id,
                    elapsed_seconds=time.monotonic() - started,
                )

        heartbeat_thread = threading.Thread(
            target=heartbeat,
            name=f"principia-extract-heartbeat-{job.job_id[-8:]}",
            daemon=True,
        )
        heartbeat_thread.start()

        try:
            if provider is None:
                for ordinal, document in enumerate(documents):
                    self.repository.save_job_unit(
                        {
                            "unit_id": unit_id_for(document),
                            "job_id": job.job_id,
                            "work_id": document["work_id"],
                            "ordinal": ordinal,
                            "state": "succeeded",
                            "attempt_count": 1,
                            "checkpoint": {
                                "document_id": document["document_id"],
                                "stage": "complete",
                            },
                            "result": {
                                "atom_count": 0,
                                "candidate_count": 0,
                                "no_llm": True,
                            },
                        }
                    )
                job.state = "succeeded"
                job.stage = "Complete"
                job.progress = 1.0
                job.completed_units = len(documents)
                job.total_units = len(documents)
                job.eta_seconds = 0
                job.status_message = "Indexing completed without generating prose"
                job.result = {
                    **metrics,
                    "candidate_count": 0,
                    "candidate_ids": [],
                    "message": "No-LLM indexing completed; prose Principles were not fabricated.",
                }
                job.updated_at = utc_now()
                job.last_activity_at = job.updated_at
                job.elapsed_seconds = round(time.monotonic() - started, 1)
                self.repository.save_job(job)
                self.repository.append_job_event(
                    job.job_id,
                    "completed",
                    {"stage": job.stage, "message": job.status_message, "progress": 1.0},
                    event_id=event_id(),
                )
                return
            for ordinal, document in enumerate(documents):
                while pause.is_set() and not cancel.is_set():
                    cancel.wait(0.2)
                if cancel.is_set():
                    raise InterruptedError
                unit_id = unit_id_for(document)
                self.repository.save_job_unit(
                    {
                        "unit_id": unit_id,
                        "job_id": job.job_id,
                        "work_id": document["work_id"],
                        "ordinal": ordinal,
                        "state": "running",
                        "attempt_count": 1,
                        "checkpoint": {"document_id": document["document_id"], "stage": "atoms"},
                    }
                )
                job.state = "running"
                job.stage = "Extract evidence"
                job.status_message = (
                    f"Extracting reusable findings from paper {ordinal + 1} of {len(documents)}"
                )
                job.progress = ordinal / max(1, len(documents))
                job.updated_at = utc_now()
                self.repository.save_job(job)
                try:
                    work = WorkItem.model_validate(document["work"])
                    segments = _select_evidence_segments(document["segments"], goal)
                    estimated_input = max(1, sum(len(str(item["text"])) for item in segments) // 3)
                    prefetched = provider_futures.get(document["document_id"])
                    provider_result = prefetched.result() if prefetched is not None else None
                    if provider_result is not None:
                        atoms = provider_result.atoms
                        raw_atom_count = provider_result.raw_atom_count
                        if provider_result.atoms_cached:
                            metrics["cached_atom_documents"] += 1
                    else:
                        ledger.reserve_unit(
                            input_tokens=estimated_input * 4,
                            output_tokens=18_000,
                        )
                        atoms_generation = provider.extract_evidence_atoms(
                            area=area,
                            goal=goal,
                            source_records=[
                                {
                                    "source_key": "source:0",
                                    "work_id": work.id,
                                    "title": work.title,
                                }
                            ],
                            evidence_segments=segments,
                        )
                        ledger.record_usage(
                            input_tokens=atoms_generation.trace.input_tokens,
                            output_tokens=atoms_generation.trace.output_tokens,
                        )
                        self._save_provider_trace(
                            job_id=job.job_id,
                            unit_id=unit_id,
                            trace=atoms_generation.trace,
                        )
                        atom_batch = EvidenceClaimAtomBatch.model_validate(atoms_generation.value)
                        raw_atom_count = len(atom_batch.atoms)
                        atoms = [
                            atom.model_copy(
                                update={
                                    "atom_id": stable_atom_id(
                                        work_id=work.id,
                                        source_key=atom.source_key,
                                        faithful_claim=atom.faithful_claim,
                                    )
                                }
                            )
                            for atom in atom_batch.atoms
                        ]
                    atom_failures = self.quality.validate_atoms(
                        atoms,
                        segment_text={
                            str(item["segment_key"]): str(item["text"]) for item in segments
                        },
                        permitted_source_keys={"source:0"},
                    )
                    atoms = [atom for atom in atoms if atom.atom_id not in atom_failures]
                    metrics["raw_atoms"] += raw_atom_count
                    for atom in atoms:
                        self.repository.save_evidence_atom(
                            atom,
                            work_id=work.id,
                            source_document_id=document["document_id"],
                        )
                    if not atoms:
                        metrics["processed_documents"] += 1
                        self.repository.save_job_unit(
                            {
                                "unit_id": unit_id,
                                "job_id": job.job_id,
                                "work_id": work.id,
                                "ordinal": ordinal,
                                "state": "succeeded",
                                "attempt_count": 1,
                                "checkpoint": {
                                    "document_id": document["document_id"],
                                    "stage": "complete",
                                },
                                "result": {"atom_count": 0, "candidate_count": 0},
                            }
                        )
                        if job.checkpoint is not None:
                            job.checkpoint["completed_document_ids"].append(document["document_id"])
                        persist_progress(ordinal + 1)
                        continue
                    arguments_generation = (
                        provider_result.arguments_generation
                        if provider_result is not None
                        else None
                    )
                    if arguments_generation is None:
                        arguments_generation = provider.normalize_scientific_arguments(
                            area=area,
                            goal=goal,
                            atoms=[atom.model_dump(mode="json") for atom in atoms],
                        )
                        ledger.record_usage(
                            input_tokens=arguments_generation.trace.input_tokens,
                            output_tokens=arguments_generation.trace.output_tokens,
                        )
                        self._save_provider_trace(
                            job_id=job.job_id,
                            unit_id=unit_id,
                            trace=arguments_generation.trace,
                        )
                    argument_batch = ScientificArgumentBatch.model_validate(
                        arguments_generation.value
                    )
                    metrics["raw_arguments"] += len(argument_batch.arguments)
                    if not argument_batch.arguments:
                        metrics["processed_documents"] += 1
                        self.repository.save_job_unit(
                            {
                                "unit_id": unit_id,
                                "job_id": job.job_id,
                                "work_id": work.id,
                                "ordinal": ordinal,
                                "state": "succeeded",
                                "attempt_count": 1,
                                "checkpoint": {
                                    "document_id": document["document_id"],
                                    "stage": "complete",
                                },
                                "result": {
                                    "atom_count": len(atoms),
                                    "argument_count": 0,
                                    "candidate_count": 0,
                                },
                            }
                        )
                        if job.checkpoint is not None:
                            job.checkpoint["completed_document_ids"].append(document["document_id"])
                        persist_progress(ordinal + 1)
                        continue
                    challenge_generation = (
                        provider_result.challenge_generation
                        if provider_result is not None
                        else None
                    )
                    if challenge_generation is None:
                        challenge_generation = provider.challenge_scientific_arguments(
                            area=area,
                            goal=goal,
                            atoms=[atom.model_dump(mode="json") for atom in atoms],
                            arguments=[
                                argument.model_dump(mode="json")
                                for argument in argument_batch.arguments
                            ],
                        )
                        ledger.record_usage(
                            input_tokens=challenge_generation.trace.input_tokens,
                            output_tokens=challenge_generation.trace.output_tokens,
                        )
                        self._save_provider_trace(
                            job_id=job.job_id,
                            unit_id=unit_id,
                            trace=challenge_generation.trace,
                        )
                    challenges = ChallengeDecisionBatch.model_validate(challenge_generation.value)
                    challenge_by_index = {
                        item.argument_index: item for item in challenges.decisions
                    }
                    for argument_index, argument in enumerate(argument_batch.arguments):
                        reasons = self.quality.validate_argument(
                            argument,
                            atoms=atoms,
                            independent_work_ids={work.id},
                            goal=goal,
                        )
                        outside_focus = QualityReason.OFF_GOAL in reasons
                        # Research focus controls prioritization and collection
                        # membership, never scientific validity.
                        reasons = [item for item in reasons if item != QualityReason.OFF_GOAL]
                        decision = challenge_by_index.get(argument_index)
                        if decision is None:
                            challenge_reasons = [QualityReason.CHALLENGE_UNAVAILABLE]
                        elif decision.verdict != "supported":
                            challenge_reasons = decision.reason_codes or [
                                QualityReason.CHALLENGE_INCONCLUSIVE
                            ]
                        else:
                            challenge_reasons = []
                        final_reasons = list(dict.fromkeys([*reasons, *challenge_reasons]))
                        candidate, fingerprint = self._candidate_from_argument(
                            argument,
                            work=work,
                            area=area,
                            job_id=job.job_id,
                            trace=arguments_generation.trace,
                        )
                        existing = (
                            self.repository.candidate_by_fingerprint(fingerprint)
                            if not final_reasons
                            else None
                        )
                        semantic_match = (
                            self.consolidation.find_equivalent(argument, area=area, work_id=work.id)
                            if not final_reasons and existing is None
                            else None
                        )
                        alias_candidate_id = candidate.candidate_id
                        if semantic_match is not None:
                            existing = semantic_match.candidate
                            fingerprint = semantic_match.fingerprint
                            self.consolidation.record_merge(
                                alias_candidate_id=alias_candidate_id,
                                canonical_candidate_id=existing.candidate_id,
                                similarity=semantic_match.similarity,
                            )
                        is_duplicate = existing is not None
                        if existing is not None:
                            candidate = existing
                            if work.id not in {
                                item.work_id for item in candidate.source_references
                            }:
                                candidate.source_references.append(
                                    WorkReference(
                                        work_id=work.id,
                                        title=work.title,
                                        url=work.url if work.url.startswith("https://") else "",
                                        doi=work.doi,
                                        role="evidence",
                                        public=True,
                                    )
                                )
                                candidate.updated_at = utc_now()
                            metrics["duplicate_candidates"] += 1
                        self.repository.save_candidate(
                            candidate,
                            source_kind="scientific_argument_v2",
                            discovery_job_id=job.job_id,
                            goal_id=goal_id,
                            source_id=source_id,
                            eligibility_status=("eligible" if is_duplicate else "pending"),
                            candidate_fingerprint=fingerprint,
                            quarantine_reason=",".join(item.value for item in final_reasons),
                            scientific_contract_version="scientific-principle-v2",
                            quality_gate_version="quality-v2",
                            quality_state=("eligible" if is_duplicate else "pending_challenge"),
                            extraction_mode=("focus_guided" if goal else "source_driven"),
                            context_relevance=(
                                "outside_focus"
                                if outside_focus
                                else ("matches" if goal else "not_evaluated")
                            ),
                        )
                        for atom in atoms:
                            if atom.atom_id in argument.atom_ids:
                                self.repository.save_evidence_atom(
                                    atom,
                                    candidate_id=candidate.candidate_id,
                                    work_id=work.id,
                                    source_document_id=document["document_id"],
                                )
                        revision = self.repository.save_scientific_argument(
                            candidate.candidate_id,
                            argument,
                            atoms=[atom for atom in atoms if atom.atom_id in argument.atom_ids],
                        )
                        evidence_digest = canonical_sha256(
                            [
                                atom.model_dump(mode="json")
                                for atom in atoms
                                if atom.atom_id in argument.atom_ids
                            ]
                        )
                        deterministic = QualityEvaluation(
                            evaluation_id=f"eval:{monotonic_ulid()}",
                            candidate_id=candidate.candidate_id,
                            argument_revision=revision,
                            verdict=(
                                QualityVerdict.ELIGIBLE
                                if not reasons
                                else QualityVerdict.QUARANTINED
                            ),
                            reason_codes=reasons,
                            evidence_digest=evidence_digest,
                            assessor="deterministic",
                            created_at=utc_now(),
                        )
                        self.repository.save_quality_evaluation(deterministic)
                        challenge_evaluation = QualityEvaluation(
                            evaluation_id=f"eval:{monotonic_ulid()}",
                            candidate_id=candidate.candidate_id,
                            argument_revision=revision,
                            verdict=(
                                QualityVerdict.ELIGIBLE
                                if not challenge_reasons
                                else QualityVerdict.QUARANTINED
                            ),
                            reason_codes=challenge_reasons,
                            evidence_digest=evidence_digest,
                            assessor="challenge",
                            provider=challenge_generation.trace.provider,
                            model=challenge_generation.trace.model,
                            prompt_sha256=challenge_generation.trace.prompt_sha256,
                            output_sha256=challenge_generation.trace.output_sha256,
                            note=decision.note if decision else "Challenge decision was missing.",
                            created_at=utc_now(),
                        )
                        self.repository.save_quality_evaluation(challenge_evaluation)
                        self._save_support_evidence(
                            candidate_id=candidate.candidate_id,
                            argument=argument,
                            atoms=atoms,
                            document=document,
                            trace=arguments_generation.trace.model_dump(mode="json"),
                        )
                        self.repository.set_candidate_quality_state(
                            candidate.candidate_id,
                            quality_state=("eligible" if not final_reasons else "quarantined"),
                            eligibility_status=("eligible" if not final_reasons else "quarantined"),
                            reason=",".join(item.value for item in final_reasons),
                        )
                        if not final_reasons:
                            self.area_suggestions.suggest_for_candidate(
                                candidate.candidate_id,
                                argument=argument.model_dump(mode="json"),
                                claim=candidate.claim,
                                work_titles=[work.title],
                                research_focus=goal,
                            )
                        candidate_ids.append(candidate.candidate_id)
                        if final_reasons:
                            metrics["quarantined_candidates"] += 1
                        else:
                            metrics["eligible_candidates"] += 1
                    with self.repository.connect() as conn:
                        conn.execute(
                            """
                            UPDATE local_source_documents SET principle_count=(
                                SELECT COUNT(DISTINCT e.candidate_id)
                                FROM candidate_work_evidence e
                                WHERE e.work_id=local_source_documents.work_id
                            ), updated_at=? WHERE document_id=?
                            """,
                            (utc_now(), document["document_id"]),
                        )
                    metrics["processed_documents"] += 1
                    self.repository.save_job_unit(
                        {
                            "unit_id": unit_id,
                            "job_id": job.job_id,
                            "work_id": work.id,
                            "ordinal": ordinal,
                            "state": "succeeded",
                            "attempt_count": 1,
                            "checkpoint": {
                                "document_id": document["document_id"],
                                "stage": "complete",
                            },
                            "result": {
                                "atom_count": len(atoms),
                                "argument_count": len(argument_batch.arguments),
                            },
                        }
                    )
                    if job.checkpoint is not None:
                        job.checkpoint["completed_document_ids"].append(document["document_id"])
                    persist_progress(ordinal + 1)
                except Exception as exc:  # noqa: BLE001
                    metrics["failed_documents"] += 1
                    unit_error = failure_payload(exc, code="document_extraction_failed")
                    self.repository.save_job_unit(
                        {
                            "unit_id": unit_id,
                            "job_id": job.job_id,
                            "work_id": document["work_id"],
                            "ordinal": ordinal,
                            "state": "failed",
                            "attempt_count": 1,
                            "checkpoint": {
                                "document_id": document["document_id"],
                                "stage": "failed",
                            },
                            "error": unit_error,
                        }
                    )
                    persist_progress(ordinal + 1)
                    # Authentication, configuration, and hard-budget failures cannot
                    # improve on the next document. Stop before wasting more calls.
                    if (isinstance(exc, ProviderRequestError) and not exc.retryable) or isinstance(
                        exc, ProviderBudgetExceeded
                    ):
                        raise
            all_failed = metrics["processed_documents"] == 0 and metrics["failed_documents"] > 0
            job.state = "failed" if all_failed else "succeeded"
            job.stage = "Needs attention" if all_failed else "Complete"
            job.progress = 1.0
            job.completed_units = len(documents)
            job.total_units = len(documents)
            job.eta_seconds = 0
            if all_failed:
                job.status_message = (
                    f"No papers were processed; {metrics['failed_documents']} need attention"
                )
                job.error = {
                    "code": "local_extraction_failed",
                    "category": "provider",
                    "message": (
                        "Principia could not process any selected paper. Open the failed-paper "
                        "details, correct the provider issue, then retry."
                    ),
                    "retryable": True,
                }
            elif metrics["failed_documents"]:
                job.status_message = (
                    f"{metrics['eligible_candidates']} findings are ready; "
                    f"{metrics['failed_documents']} "
                    f"{'paper needs' if metrics['failed_documents'] == 1 else 'papers need'} retry"
                )
            elif metrics["eligible_candidates"]:
                job.status_message = (
                    f"{metrics['eligible_candidates']} findings are ready to review"
                )
            else:
                job.status_message = (
                    "Extraction finished, but no reusable finding passed the evidence checks"
                )
            job.result = {
                **metrics,
                "candidate_count": len(set(candidate_ids)),
                "candidate_ids": list(dict.fromkeys(candidate_ids)),
                "usage": ledger.snapshot(),
                "quality_policy": "scientific-principle-v2",
            }
        except InterruptedError:
            job.state = "cancelled"
            job.stage = "cancelled"
        except Exception as exc:  # noqa: BLE001
            job.state = "failed"
            job.stage = "Needs attention"
            job.error = failure_payload(exc, code="local_extraction_failed")
            job.status_message = str(job.error["message"])
            job.result = {
                **metrics,
                "candidate_count": len(set(candidate_ids)),
                "candidate_ids": list(dict.fromkeys(candidate_ids)),
                "usage": ledger.snapshot(),
                "quality_policy": "scientific-principle-v2",
            }
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=0.5)
            if atom_pool is not None:
                atom_pool.shutdown(wait=True, cancel_futures=True)
            if provider is not None:
                provider.close()
        job.updated_at = utc_now()
        job.last_activity_at = job.updated_at
        job.elapsed_seconds = round(time.monotonic() - started, 1)
        if job.state == "succeeded":
            # Extraction-focus memberships and acquired-dataset provenance are
            # orthogonal. Reconcile both so a paper acquired for a question is
            # visible in that Library collection even when extraction ran in
            # broad, source-driven mode.
            self.repository.backfill_acquired_research_goals()
            self.repository.repair_candidate_goal_memberships()
        self.repository.save_provider_usage(job.job_id, ledger.snapshot())
        self.repository.save_job(job)
        if job.state == "succeeded" and self.principles_export_root is not None:
            try:
                from .portable import PortablePrincipleLibrary

                snapshot = PortablePrincipleLibrary(self.storage, self.repository).export(
                    self.principles_export_root
                )
                if job.result is not None:
                    job.result["principles_snapshot"] = {
                        "location": "workspace/principles",
                        "principle_count": snapshot["principle_count"],
                        "content_digest": snapshot["content_digest"],
                    }
                    self.repository.save_job(job)
            except Exception as exc:  # noqa: BLE001
                self.repository.append_job_event(
                    job.job_id,
                    "snapshot_warning",
                    {
                        "message": "Principles were saved, but the readable snapshot needs refresh.",
                        "category": type(exc).__name__,
                    },
                    event_id=event_id(),
                )
        if (
            job.state == "succeeded"
            and self.relation_rebuild is not None
            and int((job.result or {}).get("eligible_candidates") or 0) > 0
        ):
            try:
                relation_job = self.relation_rebuild()
                if job.result is not None:
                    job.result["relation_job_id"] = relation_job.job_id
                    self.repository.save_job(job)
                self.repository.append_job_event(
                    job.job_id,
                    "relation_index_queued",
                    {
                        "relation_job_id": relation_job.job_id,
                        "message": "Scientific relation analysis was queued.",
                    },
                    event_id=event_id(),
                )
            except Exception as exc:  # noqa: BLE001
                self.repository.append_job_event(
                    job.job_id,
                    "relation_index_warning",
                    {
                        "message": "Principles are ready, but relation analysis needs retry.",
                        "category": type(exc).__name__,
                    },
                    event_id=event_id(),
                )
        self.repository.append_job_event(
            job.job_id,
            "completed" if job.state == "succeeded" else job.state,
            {
                "stage": job.stage,
                "message": job.status_message,
                "progress": job.progress,
                "completed_units": job.completed_units,
                "total_units": job.total_units,
            },
            event_id=event_id(),
        )

    def _save_provider_trace(self, *, job_id: str, unit_id: str, trace: Any) -> None:
        self.repository.save_provider_attempt(
            {
                "attempt_id": f"attempt:{monotonic_ulid()}",
                "job_id": job_id,
                "unit_id": unit_id,
                "provider": trace.provider,
                "model": trace.model,
                "prompt_template": trace.prompt_template,
                "prompt_sha256": trace.prompt_sha256,
                "input_sha256": trace.input_sha256,
                "output_sha256": trace.output_sha256,
                "state": "succeeded",
                "retry_index": max(0, trace.attempts - 1),
                "latency_ms": trace.latency_ms,
                "error_category": "",
                "input_tokens": trace.input_tokens,
                "output_tokens": trace.output_tokens,
                "transport_attempts": trace.transport_attempts,
                "schema_repair_attempted": trace.repair_attempted,
            }
        )

    def pause(self, job_id: str) -> JobRecord:
        job = self.repository.get_job(job_id)
        if job is None or job.kind != "local_extraction":
            raise KeyError(f"unknown Local extraction job: {job_id}")
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
        if job is None or job.kind != "local_extraction":
            raise KeyError(f"unknown Local extraction job: {job_id}")
        pause = self._pause.get(job_id)
        if pause is not None and job.state == "running":
            pause.clear()
            job.stage = "running"
            if job.checkpoint is not None:
                job.checkpoint["control_state"] = "running"
            job.updated_at = utc_now()
            self.repository.save_job(job)
        return job

    def retry_failed(
        self,
        job_id: str,
        *,
        api_key: str | None = None,
        policy: ModelPolicy | None = None,
    ) -> JobRecord:
        job = self.repository.get_job(job_id)
        if job is None or job.kind != "local_extraction":
            raise KeyError(f"unknown Local extraction job: {job_id}")
        retryable_terminal = job.state in {"failed", "interrupted", "cancelled"}
        retryable_partial = (
            job.state == "succeeded" and self.repository.job_unit_count(job_id, state="failed") > 0
        )
        if not (retryable_terminal or retryable_partial):
            raise ValueError("this extraction has no failed or interrupted work to retry")
        checkpoint = job.checkpoint or {}
        return self.start(
            source_id=str(checkpoint["source_id"]),
            source_revision=int(checkpoint["source_revision"]),
            document_ids=list(checkpoint["document_ids"]),
            selection_mode="exact",
            goal=str(checkpoint["goal"]),
            goal_id=str(checkpoint.get("goal_id") or ""),
            area=str(checkpoint["area"]),
            policy=policy or ModelPolicy.model_validate(checkpoint["policy"]),
            limits=LiteratureRunLimits.model_validate(checkpoint["limits"]),
            resume_from=job_id,
            api_key=api_key,
        )

    @staticmethod
    def _candidate_from_argument(
        argument: ScientificArgument,
        *,
        work: WorkItem,
        area: str,
        job_id: str,
        trace: Any,
    ) -> tuple[CandidatePrinciple, str]:
        now = utc_now()
        title = concise_principle_title(argument)
        candidate = CandidatePrinciple(
            candidate_id=candidate_id(),
            area=area,
            title=title,
            claim=argument.canonical_claim,
            kind=_KIND_BY_CLASS[argument.claim_class.value],
            scope=PrincipleScope(
                statement="; ".join(argument.conditions),
                conditions=argument.conditions,
                exclusions=argument.boundary,
            ),
            falsifier=argument.testability,
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
                    retries=max(0, min(2, trace.transport_attempts - trace.attempts)),
                )
            ],
            created_at=now,
            updated_at=now,
        )
        fingerprint = canonical_sha256(
            {
                "claim": " ".join(argument.canonical_claim.casefold().split()),
                "claim_class": argument.claim_class.value,
                "subject": " ".join(argument.subject_system.casefold().split()),
                "driver": " ".join(argument.driver_or_intervention.casefold().split()),
                "outcome": " ".join(argument.outcome.casefold().split()),
                "conditions": sorted(
                    " ".join(item.casefold().split()) for item in argument.conditions
                ),
                "boundary": sorted(" ".join(item.casefold().split()) for item in argument.boundary),
            }
        )
        return candidate, fingerprint

    def _save_support_evidence(
        self,
        *,
        candidate_id: str,
        argument: ScientificArgument,
        atoms: list[Any],
        document: dict[str, Any],
        trace: dict[str, Any],
    ) -> None:
        acquisition_id = str(document.get("acquisition_id") or "") or None
        segment_ids = (
            {str(item["segment_key"]): str(item["segment_id"]) for item in document["segments"]}
            if acquisition_id
            else {}
        )
        for span in argument.support:
            base_key = span.segment_key.split(":chunk:", 1)[0]
            atom_id = next(
                (
                    atom.atom_id
                    for atom in atoms
                    if atom.atom_id in argument.atom_ids
                    and any(item.segment_key == span.segment_key for item in atom.support)
                ),
                "",
            )
            digest = hashlib.sha256(span.quotation.encode()).hexdigest()
            evidence_id = (
                "ev:"
                + canonical_sha256(
                    {
                        "candidate": candidate_id,
                        "work": document["work_id"],
                        "atom": atom_id,
                        "quotation_sha256": digest,
                    }
                )[:24]
            )
            self.repository.save_candidate_evidence(
                evidence_id=evidence_id,
                candidate_id=candidate_id,
                work_id=document["work_id"],
                excerpt_sha256=digest,
                segment_id=segment_ids.get(base_key),
                acquisition_id=acquisition_id,
                locator={
                    "section": next(
                        (
                            item.get("section")
                            for item in document["segments"]
                            if item["segment_key"] == base_key
                        ),
                        "",
                    ),
                    "quotation": span.quotation,
                    "supported_fields": span.supported_fields,
                    "source_document_id": document["document_id"],
                    "atom_id": atom_id,
                },
                extraction_trace=trace,
            )

    def cancel(self, job_id: str) -> JobRecord:
        job = self.repository.get_job(job_id)
        if job is None or job.kind != "local_extraction":
            raise KeyError(f"unknown extraction job: {job_id}")
        if job.state not in {"succeeded", "failed", "cancelled", "interrupted"}:
            job.state = "cancelling"
            job.stage = "cancelling"
        job.updated_at = utc_now()
        self.repository.save_job(job)
        self._cancel.setdefault(job_id, threading.Event()).set()
        self._pause.setdefault(job_id, threading.Event()).clear()
        return job
