from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from principia.application import Principia
from principia.domain import JobRecord, LiteratureRunLimits
from principia.local.literature_discovery import (
    _BudgetLedger,
    _build_segments,
    _resolve_evidence_quotation,
    _select_evidence_segments,
    _semantic_quality_reasons,
)
from principia.models import WorkItem, utc_now
from principia.providers import ModelPolicy


def test_evidence_quote_resolver_accepts_typography_only_not_paraphrase() -> None:
    source = "Verifier‑guided search\nreduces errors under independent failure modes."
    proposed = "verifier-guided search reduces errors under independent failure modes."
    assert _resolve_evidence_quotation(source, proposed) == source
    assert _resolve_evidence_quotation(source, "Search gets better when checks differ.") is None


def test_evidence_segment_keys_are_scoped_to_immutable_acquisition() -> None:
    work = WorkItem(id="work:repeat", title="Repeat acquisition")
    pages = [{"page": 1, "section": "results", "text": "A bounded result."}]
    first = _build_segments(work, "acq:first", pages)
    second = _build_segments(work, "acq:second", pages)
    assert first[0]["segment_key"] != second[0]["segment_key"]


def test_prompt_evidence_is_bounded_and_locator_precise() -> None:
    text = "Mechanism evidence sentence. " * 250
    selected = _select_evidence_segments(
        [
            {
                "segment_id": "seg:long",
                "segment_key": "evidence:long:0",
                "section": "results",
                "page_start": 3,
                "text": text,
            }
        ],
        "mechanism evidence",
    )
    assert selected
    assert len({item["segment_key"] for item in selected}) == len(selected)
    assert all(len(item["text"]) <= 1_600 for item in selected)
    assert sum(len(item["text"]) for item in selected) <= 24_000


def test_source_driven_evidence_selection_balances_late_scientific_sections() -> None:
    segments = []
    for index, section in enumerate(
        ["introduction", "methods", "results", "discussion", "conclusion"]
    ):
        text = (f"Background material for {section}. " * 180) + (
            f"Late {section} evidence reduces errors and depends on boundary conditions."
        )
        segments.append(
            {
                "segment_id": f"seg:{index}",
                "segment_key": f"evidence:balanced:{index}",
                "section": section,
                "page_start": index + 1,
                "text": text,
            }
        )

    selected = _select_evidence_segments(segments, "")
    selected_sections = {item["section"] for item in selected}

    assert {"methods", "results", "discussion", "conclusion"}.issubset(selected_sections)
    assert sum(len(item["text"]) for item in selected) <= 24_000


def test_usage_ledger_fails_closed_on_provider_reported_overspend() -> None:
    ledger = _BudgetLedger(LiteratureRunLimits(max_input_tokens=10_000, max_output_tokens=4_000))
    ledger.reserve_unit(input_tokens=5_000, output_tokens=3_712)
    with pytest.raises(RuntimeError, match="output-token budget"):
        ledger.record_usage(input_tokens=1_000, output_tokens=4_001)


def test_completed_reservations_do_not_exhaust_later_parallel_units() -> None:
    ledger = _BudgetLedger(
        LiteratureRunLimits(max_input_tokens=10_000, max_output_tokens=10_000)
    )
    ledger.reserve_unit(input_tokens=3_000, output_tokens=4_000)
    ledger.record_usage(input_tokens=1_000, output_tokens=1_200)
    ledger.release_unit(input_tokens=3_000, output_tokens=4_000)
    ledger.reserve_unit(input_tokens=3_000, output_tokens=4_000)
    snapshot = ledger.snapshot()
    assert snapshot["input_tokens"] == 1_000
    assert snapshot["output_tokens"] == 1_200
    assert snapshot["reserved_input_tokens"] == 3_000
    assert snapshot["reserved_output_tokens"] == 4_000


def test_semantic_gate_rejects_unsupported_entities_and_off_goal_summaries() -> None:
    unsupported = _semantic_quality_reasons(
        draft=SimpleNamespace(
            title="Compensatory checkpoints",
            claim="TIM-3, LAG-3, and TIGIT mediate acquired checkpoint resistance.",
            scope="Checkpoint blockade in tumors",
        ),
        work=WorkItem(
            id="work:checkpoint",
            title="Checkpoint resistance",
            abstract="TIM-3 and LAG-3 are compensatory checkpoints.",
        ),
        goal="Which mechanisms cause acquired PD-1 checkpoint-blockade resistance?",
        cited_text="TIM-3 and LAG-3 are compensatory checkpoints.",
    )
    assert "unsupported_named_entity" in unsupported

    off_goal = _semantic_quality_reasons(
        draft=SimpleNamespace(
            title="Handedness distribution",
            claim="Handedness development maintains a minority of left-handed people.",
            scope="Population handedness",
        ),
        work=WorkItem(
            id="work:handedness",
            title="Handedness development and hemispheric specialization",
            abstract="A developmental model of handedness.",
        ),
        goal="Which coordination and memory mechanisms improve multi-agent scientific discovery?",
        cited_text="Handedness development maintains a minority of left-handed people.",
    )
    assert "off_goal_candidate" in off_goal

    generic = _semantic_quality_reasons(
        draft=SimpleNamespace(
            title="Agent communication",
            claim="Agents communicate observations to gain a broader view and make informed decisions.",
            scope="Multi-agent systems",
        ),
        work=WorkItem(
            id="work:agents",
            title="Communication in multi-agent systems",
            abstract="Agents share observations.",
        ),
        goal="Which coordination mechanisms improve multi-agent scientific discovery?",
        cited_text="Agents communicate observations to gain a broader view and make informed decisions.",
    )
    assert "generic_summary_not_principle" in generic


def test_retry_failed_accepts_partially_succeeded_literature_job(tmp_path: Path) -> None:
    principia = Principia.open(tmp_path)
    work = WorkItem(
        id="work:partial-retry",
        title="Partial retry fixture",
        abstract="A public abstract remains usable for deterministic no-LLM acquisition.",
    )
    principia.workspace.storage.save_work(work)
    now = utc_now()
    principia.repository.save_literature_search(
        {
            "search_id": "search:partial-retry",
            "goal": "Acquire a previously failed public paper unit",
            "area": "machine-intelligence",
            "target_count": 1,
            "state": "ready",
            "sources": ["fixture"],
            "unavailable_sources": [],
            "results": [{"work_id": work.id}],
            "selected_work_ids": [work.id],
            "alternate_work_ids": [],
            "pool_count": 1,
            "diagnostics": {},
            "created_at": now,
            "updated_at": now,
        }
    )
    old = JobRecord(
        job_id="job:partial-retry",
        kind="literature_discovery",
        state="succeeded",
        stage="Complete",
        progress=1,
        result={"failed_papers": 1},
        checkpoint={
            "search_id": "search:partial-retry",
            "policy": ModelPolicy(mode="no_llm").model_dump(mode="json"),
            "limits": LiteratureRunLimits().model_dump(mode="json"),
            "completed_work_ids": [],
        },
    )
    principia.repository.save_job(old)
    principia.repository.save_job_unit(
        {
            "unit_id": "unit:partial-retry",
            "job_id": old.job_id,
            "work_id": work.id,
            "ordinal": 0,
            "state": "failed",
            "error": {"category": "provider", "retryable": True},
        }
    )
    assert principia.local.literature is not None
    retried = principia.local.literature.retry_failed(old.job_id)
    assert retried.job_id != old.job_id
    assert retried.checkpoint is not None
    assert retried.checkpoint["resume_from"] == old.job_id


def test_unusable_selected_paper_is_topped_up_from_ranked_alternates(
    tmp_path: Path,
) -> None:
    principia = Principia.open(tmp_path)
    works = [
        WorkItem(id="work:missing", title="Missing evidence"),
        WorkItem(
            id="work:selected",
            title="Selected evidence",
            abstract="A selected public abstract provides usable evidence.",
        ),
        WorkItem(
            id="work:alternate",
            title="Alternate evidence",
            abstract="A ranked alternate provides usable evidence when acquisition fails.",
        ),
    ]
    for work in works:
        principia.workspace.storage.save_work(work)
    now = utc_now()
    principia.repository.save_literature_search(
        {
            "search_id": "search:top-up",
            "goal": "Acquire two usable public papers",
            "area": "machine-intelligence",
            "target_count": 2,
            "state": "ready",
            "sources": ["fixture"],
            "unavailable_sources": [],
            "results": [{"work_id": work.id} for work in works],
            "selected_work_ids": [works[0].id, works[1].id],
            "alternate_work_ids": [works[2].id],
            "pool_count": 3,
            "diagnostics": {},
            "created_at": now,
            "updated_at": now,
        }
    )
    job = principia.local.start_literature_discovery(
        search_id="search:top-up", policy=ModelPolicy(mode="no_llm")
    )
    deadline = time.monotonic() + 10
    current = job
    while current.state not in {"succeeded", "failed"} and time.monotonic() < deadline:
        time.sleep(0.02)
        current = principia.local.get(job.job_id) or current
    assert current.state == "succeeded", current.error
    assert current.result is not None
    assert current.result["paper_count"] == 2
    assert current.result["attempted_papers"] == 3
    assert current.result["processed_papers"] == 2
    assert current.result["failed_papers"] == 1
    assert current.result["top_up_papers"] == 1
    assert current.result["usable_target_met"] is True


def test_retry_chain_processes_only_failed_units_and_ranked_top_up(tmp_path: Path) -> None:
    principia = Principia.open(tmp_path)
    completed_work = WorkItem(
        id="work:completed", title="Completed", abstract="Already processed evidence."
    )
    failed_work = WorkItem(id="work:failed", title="Failed without evidence")
    alternate_work = WorkItem(
        id="work:retry-alternate",
        title="Retry alternate",
        abstract="A ranked alternate replaces an unusable failed paper.",
    )
    for work in (completed_work, failed_work, alternate_work):
        principia.workspace.storage.save_work(work)
    now = utc_now()
    principia.repository.save_literature_search(
        {
            "search_id": "search:retry-chain",
            "goal": "Retry only a failed durable paper unit",
            "area": "machine-intelligence",
            "target_count": 2,
            "state": "ready",
            "sources": ["fixture"],
            "unavailable_sources": [],
            "results": [
                {"work_id": completed_work.id},
                {"work_id": failed_work.id},
                {"work_id": alternate_work.id},
            ],
            "selected_work_ids": [completed_work.id, failed_work.id],
            "alternate_work_ids": [alternate_work.id],
            "pool_count": 3,
            "diagnostics": {},
            "created_at": now,
            "updated_at": now,
        }
    )
    previous = JobRecord(
        job_id="job:retry-chain",
        kind="literature_discovery",
        state="succeeded",
        stage="Complete",
        progress=1,
        result={"failed_papers": 1, "usable_target_met": False},
        checkpoint={
            "search_id": "search:retry-chain",
            "policy": ModelPolicy(mode="no_llm").model_dump(mode="json"),
            "limits": LiteratureRunLimits().model_dump(mode="json"),
            "completed_work_ids": [completed_work.id],
        },
    )
    principia.repository.save_job(previous)
    for ordinal, (work, state) in enumerate(
        ((completed_work, "succeeded"), (failed_work, "failed"))
    ):
        principia.repository.save_job_unit(
            {
                "unit_id": f"unit:retry-chain:{ordinal}",
                "job_id": previous.job_id,
                "work_id": work.id,
                "ordinal": ordinal,
                "state": state,
                "error": {"category": "acquisition", "retryable": True}
                if state == "failed"
                else None,
            }
        )
    assert principia.local.literature is not None
    retried = principia.local.literature.retry_failed(previous.job_id)
    deadline = time.monotonic() + 10
    current = retried
    while current.state not in {"succeeded", "failed"} and time.monotonic() < deadline:
        time.sleep(0.02)
        current = principia.local.get(retried.job_id) or current
    assert current.state == "succeeded", current.error
    assert current.result is not None
    assert current.result["paper_count"] == 1
    assert current.result["processed_papers"] == 1
    assert current.result["top_up_papers"] == 1
    assert current.result["usable_target_met"] is True
    retried_ids = principia.repository.job_unit_work_ids(retried.job_id)
    assert completed_work.id not in retried_ids
    assert retried_ids == [failed_work.id, alternate_work.id]


def test_multi_draft_pipeline_persists_grounded_evidence_and_deduplicates(tmp_path: Path) -> None:
    principia = Principia.open(tmp_path)
    quotation = (
        "Independent verifier signals reduce selection errors when the verifier "
        "does not share the generator's failure mode."
    )
    works = [
        WorkItem(
            id=f"work:fixture:{index}",
            title=f"Verifier mechanism study {index}",
            abstract=quotation,
            source="fixture",
            url=f"https://example.org/{index}",
        )
        for index in range(2)
    ]
    for work in works:
        principia.workspace.storage.save_work(work)
    search = {
        "search_id": "search:fixture",
        "goal": "When does independent verification improve inference-time decisions?",
        "area": "machine-intelligence",
        "target_count": 2,
        "state": "ready",
        "sources": ["fixture"],
        "unavailable_sources": [],
        "results": [{"work_id": work.id, "title": work.title} for work in works],
        "selected_work_ids": [work.id for work in works],
        "alternate_work_ids": [],
        "pool_count": 2,
        "diagnostics": {},
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    principia.repository.save_literature_search(search)
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        request_body = json.loads(request.content)
        assert request_body["thinking_budget"] == 1_024
        assert request_body["max_tokens"] == 3_200
        segment_key = re.search(
            r'"segment_key"\s*:\s*"([^"]+)"', request_body["messages"][-1]["content"]
        ).group(1)
        call_label = "first" if calls == 1 else "second"
        draft_labels = ["alpha", "beta", "gamma", "delta"]
        drafts = [
            {
                "title": f"Independent verification condition {call_label} {draft_labels[index]}",
                "claim": (
                    f"Independent failure signals improve verifier-guided selection for mechanism "
                    f"class {call_label} {draft_labels[index]} when generator and verifier errors are not shared."
                ),
                "kind": "mechanistic",
                "scope": "Inference-time candidate selection with an independently trained verifier",
                "falsifier": "The effect disappears under held-out failures with independent signals.",
                "source_keys": ["source:0"],
                "evidence": [
                    {
                        "segment_key": segment_key,
                        "quotation": quotation,
                        "role": "evidence",
                    }
                ],
            }
            for index in range(4)
        ]
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps({"drafts": drafts})}}],
                "usage": {"prompt_tokens": 500, "completion_tokens": 600},
            },
        )

    job = principia.local.start_literature_discovery(
        search_id=search["search_id"],
        policy=ModelPolicy(
            mode="remote",
            provider="siliconflow",
            model="fixture-model",
            base_url="https://api.siliconflow.com/v1",
            remote_egress_confirmed=True,
        ),
        api_key="fixture-secret",
        provider_transport=httpx.MockTransport(handler),
    )
    deadline = time.monotonic() + 10
    current = job
    while current.state not in {"succeeded", "failed", "cancelled"} and time.monotonic() < deadline:
        time.sleep(0.02)
        current = principia.local.get(job.job_id) or current
    assert current.state == "succeeded", current.error
    assert current.result is not None
    assert current.result["raw_drafts"] == 8, current.result
    assert current.result["eligible_candidates"] == 8
    assert current.result["quarantined_candidates"] == 0
    page = principia.repository.browse_candidates(discovery_id=job.job_id, limit=100)
    assert page["total"] == 8
    detail = principia.repository.candidate_detail(page["items"][0]["candidate_id"])
    assert detail is not None
    assert detail["evidence"][0]["work_id"].startswith("work:fixture:")
    assert detail["evidence"][0]["quotation"] == quotation
    assert detail["evidence"][0]["excerpt_available"] is True
    assert detail["evidence"][0]["excerpt_sha256"] == hashlib.sha256(quotation.encode()).hexdigest()


def test_batch_provider_quarantines_schema_echo(tmp_path: Path) -> None:
    principia = Principia.open(tmp_path)
    quotation = "A controlled intervention changes the measured response under a bounded condition."
    work = WorkItem(id="work:echo", title="Echo fixture", abstract=quotation)
    principia.workspace.storage.save_work(work)
    now = utc_now()
    principia.repository.save_literature_search(
        {
            "search_id": "search:echo",
            "goal": "Extract a controlled mechanism",
            "area": "machine-intelligence",
            "target_count": 1,
            "state": "ready",
            "sources": ["fixture"],
            "unavailable_sources": [],
            "results": [{"work_id": work.id}],
            "selected_work_ids": [work.id],
            "alternate_work_ids": [],
            "pool_count": 1,
            "diagnostics": {},
            "created_at": now,
            "updated_at": now,
        }
    )

    def echo_handler(request: httpx.Request) -> httpx.Response:
        request_body = json.loads(request.content)
        segment_key = re.search(
            r'"segment_key"\s*:\s*"([^"]+)"', request_body["messages"][-1]["content"]
        ).group(1)
        content = {
            "drafts": [
                {
                    "title": "CandidateDraftBatch template output",
                    "claim": "This generic principle is a placeholder mechanism requiring later completion.",
                    "kind": "hypothesis",
                    "scope": "source_keys and segment_key schema fields",
                    "falsifier": "",
                    "source_keys": ["source:0"],
                    "evidence": [
                        {"segment_key": segment_key, "quotation": quotation, "role": "evidence"}
                    ],
                }
            ]
        }
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(content)}}], "usage": {}},
        )

    transport = httpx.MockTransport(echo_handler)
    job = principia.local.start_literature_discovery(
        search_id="search:echo",
        policy=ModelPolicy(
            mode="remote",
            provider="fixture",
            model="fixture",
            base_url="https://example.org/v1",
            remote_egress_confirmed=True,
        ),
        api_key="fixture",
        provider_transport=transport,
    )
    deadline = time.monotonic() + 10
    current = job
    while current.state not in {"succeeded", "failed"} and time.monotonic() < deadline:
        time.sleep(0.02)
        current = principia.local.get(job.job_id) or current
    assert current.state == "succeeded", current.error
    assert current.result["eligible_candidates"] == 0
    assert current.result["quarantined_candidates"] == 1
    assert principia.search.search("generic", scope="local") == []
