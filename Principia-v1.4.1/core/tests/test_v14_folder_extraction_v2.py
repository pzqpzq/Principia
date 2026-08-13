from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from typing import Any

import httpx

from principia.application import Principia
from principia.domain import LiteratureRunLimits
from principia.providers import ModelPolicy


def test_reused_paper_text_is_resolved_by_content_hash_after_work_deduplication(
    tmp_path: Path,
) -> None:
    """A second folder must remain extractable when its Work ID is canonicalized."""

    first_folder = tmp_path / "first"
    second_folder = tmp_path / "second"
    first_folder.mkdir()
    second_folder.mkdir()
    paper = (
        "Independent verifier signals reduced selection errors when verifier failures "
        "differed from generator failures."
    )
    (first_folder / "paper.txt").write_text(paper, encoding="utf-8")
    (second_folder / "paper.txt").write_text(paper, encoding="utf-8")
    product = Principia.open(tmp_path / "workspace", cloud_root=tmp_path / "cloud")
    first = product.local.register_source(first_folder)
    second = product.local.register_source(second_folder)
    assert product.local.index_source(first["source_id"]).state == "succeeded"
    assert product.local.index_source(second["source_id"]).state == "succeeded"
    documents = product.local.source_documents(
        second["source_id"], extractable=True, limit=10
    )["items"]
    assert len(documents) == 1
    extracted = product.repository.extraction_documents(
        second["source_id"], [documents[0]["document_id"]]
    )
    assert extracted[0]["segments"]
    assert paper in extracted[0]["segments"][0]["text"]


def test_evidence_extraction_prefetches_selected_papers_in_parallel(tmp_path: Path) -> None:
    private_folder = tmp_path / "parallel-papers"
    private_folder.mkdir()
    for index in range(2):
        (private_folder / f"paper-{index}.txt").write_text(
            f"Independent verification reduced selection errors under workload {index} "
            "when verifier failures differed from generator failures.",
            encoding="utf-8",
        )
    product = Principia.open(tmp_path / "workspace", cloud_root=tmp_path / "cloud")
    source = product.local.register_source(private_folder)
    assert product.local.index_source(source["source_id"]).state == "succeeded"
    source_detail = product.local.source_detail(source["source_id"])
    document_ids = [
        item["document_id"]
        for item in product.local.source_documents(source["source_id"], extractable=True, limit=10)[
            "items"
        ]
    ]
    assert len(document_ids) == 2

    lock = threading.Lock()
    rendezvous = {
        "atoms": threading.Barrier(2),
        "arguments": threading.Barrier(2),
        "challenge": threading.Barrier(2),
    }
    active = {stage: 0 for stage in rendezvous}
    max_active = {stage: 0 for stage in rendezvous}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        system = body["messages"][0]["content"]
        prompt = body["messages"][-1]["content"]
        if "source-faithful Evidence Atom Proposals" in system:
            stage = "atoms"
            segment_match = re.search(r'"segment_key"\s*:\s*"([^"]+)"', prompt)
            assert segment_match is not None
            content: dict[str, Any] = {
                "atoms": [
                    {
                        "source_key": "source:0",
                        "assertion_type": "observed_result",
                        "evidence_type": "experiment",
                        "epistemic_status": "observed",
                        "support_segment_keys": [segment_match.group(1)],
                    }
                ]
            }
        elif "Normalize eligible Evidence Claim Atoms" in system:
            stage = "arguments"
            atom_match = re.search(r'"atom_id"\s*:\s*"([^"]+)"', prompt)
            claim_match = re.search(r'"faithful_claim"\s*:\s*"([^"]+)"', prompt)
            assert atom_match is not None and claim_match is not None
            atom_id = atom_match.group(1)
            content = {
                "arguments": [
                    {
                        "scientific_contract_version": "scientific-principle-v2",
                        "canonical_claim": claim_match.group(1),
                        "claim_class": "empirical_association",
                        "subject_system": "verifier-guided selection systems",
                        "driver_or_intervention": "independent verification",
                        "outcome": "selection errors",
                        "direction_or_qualifier": "reduced",
                        "conditions": ["verifier failures differ from generator failures"],
                        "boundary": ["limited to the reported workload"],
                        "boundary_provenance": "conservative_study_limit",
                        "generalization_level": "study_bound",
                        "testability": "Compare error rates with and without verification.",
                        "testability_provenance": "generated_challenge",
                        "atom_ids": [atom_id],
                        "field_support": [
                            {"field": field, "atom_ids": [atom_id]}
                            for field in [
                                "canonical_claim",
                                "subject_system",
                                "driver_or_intervention",
                                "outcome",
                                "direction_or_qualifier",
                                "conditions",
                                "boundary",
                            ]
                        ],
                    }
                ]
            }
        else:
            stage = "challenge"
            content = {
                "decisions": [
                    {
                        "argument_index": 0,
                        "verdict": "supported",
                        "reason_codes": [],
                        "note": "The relation and boundary match the evidence.",
                    }
                ]
            }
        with lock:
            active[stage] += 1
            max_active[stage] = max(max_active[stage], active[stage])
        try:
            rendezvous[stage].wait(timeout=2)
        finally:
            with lock:
                active[stage] -= 1
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(content)}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 4},
            },
        )

    job = product.local.start_extraction(
        source_id=source["source_id"],
        source_revision=source_detail["revision"],
        document_ids=document_ids,
        selection_mode="exact",
        goal="",
        area="",
        policy=ModelPolicy(
            mode="remote",
            provider="fixture",
            model="fixture-model",
            base_url="https://example.org/v1",
            remote_egress_confirmed=True,
        ),
        limits=LiteratureRunLimits(max_http_attempts=6, concurrency=2),
        api_key="fixture-key",
        provider_transport=httpx.MockTransport(handler),
    )
    deadline = time.monotonic() + 10
    current = job
    while current.state not in {"succeeded", "failed", "cancelled"} and time.monotonic() < deadline:
        time.sleep(0.02)
        current = product.local.get(job.job_id) or current
    assert current.state == "succeeded", current.error
    assert current.result is not None
    assert current.result["parallel_workers"] == 2
    assert current.result["processed_documents"] == 2, (
        current.result,
        product.repository.list_job_units(job.job_id),
    )
    assert current.result["candidate_count"] == 2
    assert max_active == {"atoms": 2, "arguments": 2, "challenge": 2}


def test_selected_folder_document_runs_atom_argument_and_challenge_pipeline(
    tmp_path: Path,
) -> None:
    private_folder = tmp_path / "private-papers"
    private_folder.mkdir()
    quotation = (
        "Independent verifier signals reduced selection errors when verifier failures "
        "differed from generator failures."
    )
    (private_folder / "verifier.txt").write_text(quotation, encoding="utf-8")
    product = Principia.open(tmp_path / "workspace", cloud_root=tmp_path / "cloud")
    source = product.local.register_source(private_folder)
    indexed = product.local.index_source(source["source_id"])
    assert indexed.state == "succeeded", indexed.error
    source_detail = product.local.source_detail(source["source_id"])
    documents = product.local.source_documents(source["source_id"], extractable=True, limit=100)
    assert documents["total"] == 1
    document_id = documents["items"][0]["document_id"]
    stages: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        system = body["messages"][0]["content"]
        prompt = body["messages"][-1]["content"]
        content: dict[str, Any]
        if "source-faithful Evidence Atom Proposals" in system:
            stages.append("atoms")
            segment_match = re.search(r'"segment_key"\s*:\s*"([^"]+)"', prompt)
            assert segment_match is not None
            segment_key = segment_match.group(1)
            content = {
                "atoms": [
                    {
                        "source_key": "source:0",
                        "assertion_type": "observed_result",
                        "evidence_type": "experiment",
                        "epistemic_status": "observed",
                        "support_segment_keys": [segment_key],
                    }
                ]
            }
        elif "Normalize eligible Evidence Claim Atoms" in system:
            stages.append("arguments")
            atom_match = re.search(r'"atom_id"\s*:\s*"([^"]+)"', prompt)
            assert atom_match is not None
            atom_id = atom_match.group(1)
            content = {
                "arguments": [
                    {
                        "scientific_contract_version": "scientific-principle-v2",
                        "canonical_claim": quotation,
                        "claim_class": "empirical_association",
                        "subject_system": "verifier-guided selection systems",
                        "driver_or_intervention": "independent verifier signals",
                        "outcome": "selection errors",
                        "direction_or_qualifier": "reduced",
                        "conditions": ["verifier failures differ from generator failures"],
                        "boundary": [
                            "not established when verifier and generator failures are shared"
                        ],
                        "boundary_provenance": "source_grounded",
                        "generalization_level": "study_bound",
                        "testability": (
                            "Compare selection error rates while varying verifier failure independence."
                        ),
                        "testability_provenance": "generated_challenge",
                        "atom_ids": [atom_id],
                        "field_support": [
                            {"field": field, "atom_ids": [atom_id]}
                            for field in [
                                "canonical_claim",
                                "subject_system",
                                "driver_or_intervention",
                                "outcome",
                                "direction_or_qualifier",
                                "conditions",
                                "boundary",
                            ]
                        ],
                    }
                ]
            }
        else:
            stages.append("challenge")
            content = {
                "decisions": [
                    {
                        "argument_index": 0,
                        "verdict": "supported",
                        "reason_codes": [],
                        "note": "The relation, scope, and evidence are aligned.",
                    }
                ]
            }
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(content)}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 100},
            },
        )

    job = product.local.start_extraction(
        source_id=source["source_id"],
        source_revision=source_detail["revision"],
        document_ids=[document_id],
        selection_mode="exact",
        goal="When does independent verification improve inference-time selection?",
        area="machine-intelligence",
        policy=ModelPolicy(
            mode="remote",
            provider="fixture",
            model="fixture-model",
            base_url="https://example.org/v1",
            remote_egress_confirmed=True,
        ),
        limits=LiteratureRunLimits(max_http_attempts=3),
        api_key="fixture-key",
        provider_transport=httpx.MockTransport(handler),
    )
    assert job.result is not None
    assert job.result["selected_documents"] == 1
    assert job.checkpoint is not None
    assert str(job.checkpoint["goal_id"]).startswith("goal:")
    deadline = time.monotonic() + 10
    current = job
    while current.state not in {"succeeded", "failed", "cancelled"} and time.monotonic() < deadline:
        time.sleep(0.02)
        current = product.local.get(job.job_id) or current
    assert current.state == "succeeded", current.error
    assert stages == ["atoms", "arguments", "challenge"]
    assert current.result is not None
    with product.repository.connect() as conn:
        unit_errors = [
            dict(row)
            for row in conn.execute(
                "SELECT state, error_json FROM v14_job_units WHERE job_id=?", (job.job_id,)
            ).fetchall()
        ]
    assert current.result["eligible_candidates"] == 1, (current.result, unit_errors)
    candidate_id = current.result["candidate_ids"][0]
    detail = product.repository.candidate_detail(candidate_id)
    assert detail is not None
    assert detail["local_metadata"]["quality_state"] == "eligible"
    assert detail["local_metadata"]["scientific_contract_version"] == ("scientific-principle-v2")
    assert detail["scientific_argument"]["generalization_level"] == "study_bound"
    assert detail["title"] == "Independent verifier signals–selection errors principle"
    assert detail["title"] != detail["claim"]
    assert len(detail["title"]) < 100
    assert {item["assessor"] for item in detail["quality_evaluations"]} == {
        "deterministic",
        "challenge",
    }
    assert detail["evidence"][0]["quotation"] == quotation
    assert product.search.search("verifier signals", scope="local")[0]["id"] == candidate_id
    with product.repository.connect() as conn:
        selection = conn.execute(
            "SELECT document_ids_json, quality_policy FROM local_extraction_selections "
            "WHERE job_id=?",
            (job.job_id,),
        ).fetchone()
        provider_attempt_count = conn.execute(
            "SELECT COUNT(*) FROM provider_attempts WHERE job_id=?", (job.job_id,)
        ).fetchone()[0]
    assert json.loads(selection["document_ids_json"]) == [document_id]
    assert selection["quality_policy"] == "scientific-principle-v2"
    assert provider_attempt_count == 3
    units = product.repository.list_job_units(job.job_id)
    assert [(item["work_title"], item["state"]) for item in units] == [("verifier", "succeeded")]
    collections = product.repository.library_collections("research_goal")
    assert any(
        item["collection_id"] == job.checkpoint["goal_id"] and item["principle_count"] == 1
        for item in collections
    )
    area_collections = product.repository.library_collections("area")
    assert product.repository.library_summary()["area_count"] >= 1
    assert any(item["principle_count"] == 1 for item in area_collections)


def test_source_driven_extraction_needs_neither_goal_nor_area(tmp_path: Path) -> None:
    private_folder = tmp_path / "broad-private-papers"
    private_folder.mkdir()
    (private_folder / "finding.txt").write_text(
        "A bounded observation links independent checks to lower selection errors.",
        encoding="utf-8",
    )
    product = Principia.open(tmp_path / "workspace", cloud_root=tmp_path / "cloud")
    source = product.local.register_source(private_folder)
    indexed = product.local.index_source(source["source_id"])
    assert indexed.state == "succeeded"
    source_detail = product.local.source_detail(source["source_id"])
    document_id = product.local.source_documents(source["source_id"], extractable=True, limit=10)[
        "items"
    ][0]["document_id"]
    document = product.local.source_documents(source["source_id"], limit=10)["items"][0]
    assert document["content_byte_size"] == (private_folder / "finding.txt").stat().st_size

    job = product.local.start_extraction(
        source_id=source["source_id"],
        source_revision=source_detail["revision"],
        document_ids=[document_id],
        selection_mode="exact",
        goal="",
        area="",
        policy=ModelPolicy(mode="no_llm"),
        limits=LiteratureRunLimits(),
    )
    deadline = time.monotonic() + 10
    current = job
    while current.state not in {"succeeded", "failed", "cancelled"} and time.monotonic() < deadline:
        time.sleep(0.02)
        current = product.local.get(job.job_id) or current

    assert current.state == "succeeded", current.error
    assert current.checkpoint is not None
    assert current.checkpoint["goal_id"] == ""
    assert current.checkpoint["area"] == "uncategorized"
    assert current.checkpoint["extraction_mode"] == "source_driven"
    processed_document = product.local.source_documents(
        source["source_id"], extractable=True, limit=10
    )["items"][0]
    assert processed_document["principle_count"] == 0
    assert processed_document["extraction_status"] == "processed"
    assert processed_document["extraction_attempt_count"] == 1
    with product.repository.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM local_research_goals").fetchone()[0] == 0
        selection = conn.execute(
            "SELECT research_focus, extraction_mode, context_json "
            "FROM local_extraction_selections WHERE job_id=?",
            (job.job_id,),
        ).fetchone()
    assert selection["research_focus"] == ""
    assert selection["extraction_mode"] == "source_driven"
    assert json.loads(selection["context_json"])["research_focus"] is None


def test_authentication_failure_stops_immediately_and_never_reports_complete(
    tmp_path: Path,
) -> None:
    private_folder = tmp_path / "private-papers"
    private_folder.mkdir()
    for index in range(3):
        (private_folder / f"paper-{index}.txt").write_text(
            "Independent verification reduced selection errors in the bounded test setting.",
            encoding="utf-8",
        )
    product = Principia.open(tmp_path / "workspace", cloud_root=tmp_path / "cloud")
    source = product.local.register_source(private_folder)
    assert product.local.index_source(source["source_id"]).state == "succeeded"
    detail = product.local.source_detail(source["source_id"])
    document_ids = [
        item["document_id"]
        for item in product.local.source_documents(
            source["source_id"], extractable=True, limit=100
        )["items"]
    ]
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401, json={"message": "invalid credential"})

    job = product.local.start_extraction(
        source_id=source["source_id"],
        source_revision=detail["revision"],
        document_ids=document_ids,
        selection_mode="exact",
        goal="",
        area="",
        policy=ModelPolicy(
            mode="remote",
            provider="siliconflow",
            model="custom-org/custom-model",
            base_url="https://api.siliconflow.com/v1",
            remote_egress_confirmed=True,
        ),
        limits=LiteratureRunLimits(max_http_attempts=20),
        api_key="invalid-fixture-key",
        provider_transport=httpx.MockTransport(handler),
    )
    deadline = time.monotonic() + 10
    current = job
    while current.state not in {"succeeded", "failed", "cancelled"} and time.monotonic() < deadline:
        time.sleep(0.02)
        current = product.local.get(job.job_id) or current

    assert current.state == "failed"
    assert current.stage == "Needs attention"
    assert current.error is not None
    assert current.error["category"] == "authentication"
    assert current.result is not None
    assert current.result["processed_documents"] == 0
    assert current.result["failed_documents"] == 1
    assert calls == 1
    assert "valid API key" in current.status_message
    assert product.repository.list_candidates() == []
