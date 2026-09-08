from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from principia.application import PrincipleSearchService
from principia.cloud import CloudRegistry
from principia.domain import (
    CandidatePrinciple,
    ChallengeDecisionBatch,
    EvidenceClaimAtomBatch,
    PrincipleKind,
    PrincipleScope,
    ScientificArgumentBatch,
)
from principia.local import LocalDiscoveryService
from principia.persistence import V14WorkspaceRepository
from principia.providers import ModelPolicy, OpenAICompatibleProvider, ProviderRequestError
from principia.storage import WorkspaceStorage


def _candidate(candidate_id: str) -> dict[str, object]:
    return CandidatePrinciple(
        candidate_id=candidate_id,
        area="demo-local",
        title="Bounded fixture candidate",
        claim="A deterministic fixture claim.",
        kind=PrincipleKind.HYPOTHESIS,
        scope=PrincipleScope(statement="Synthetic local files"),
        falsifier="A repeated fixture run disagrees.",
    ).model_dump(mode="json")


def test_model_policy_requires_explicit_egress_and_loopback_local() -> None:
    with pytest.raises(ValidationError, match="egress confirmation"):
        ModelPolicy(
            mode="remote",
            provider="siliconflow",
            model="fixture-model",
            base_url="https://api.siliconflow.com/v1",
        )
    with pytest.raises(ValidationError, match="loopback"):
        ModelPolicy(
            mode="local",
            provider="local",
            model="fixture-model",
            base_url="https://example.com/v1",
        )
    assert (
        ModelPolicy(
            mode="local",
            provider="local",
            model="fixture-model",
            base_url="http://127.0.0.1:11434/v1",
        ).mode
        == "local"
    )


def test_provider_profile_accepts_safe_custom_model_ids(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path / "workspace")
    repository = V14WorkspaceRepository(storage.db_path)
    service = LocalDiscoveryService(
        storage,
        repository,
        PrincipleSearchService(CloudRegistry(tmp_path / "cloud"), repository),
    )
    service.save_provider_credential("siliconflow", "fixture-secret-value")
    _, policy, key = service.provider_configuration(
        "siliconflow", "custom-lab/Reasoning-Model.v2", egress_confirmed=True
    )
    assert policy.model == "custom-lab/Reasoning-Model.v2"
    assert key == "fixture-secret-value"
    with pytest.raises(ValueError, match="valid provider model ID"):
        service.provider_configuration(
            "siliconflow", "https://attacker.example/model", egress_confirmed=True
        )


def test_connection_discovers_and_persists_working_siliconflow_region(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = WorkspaceStorage(tmp_path / "workspace")
    repository = V14WorkspaceRepository(storage.db_path)
    service = LocalDiscoveryService(
        storage,
        repository,
        PrincipleSearchService(CloudRegistry(tmp_path / "cloud"), repository),
    )
    secret = "regional-fixture-secret"
    service.save_provider_credential("siliconflow", secret)
    requests: list[tuple[str, str]] = []

    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        headers = kwargs.get("headers")
        assert isinstance(headers, dict)
        requests.append((url, str(headers.get("Authorization"))))
        return httpx.Response(401 if "siliconflow.com" in url else 200)

    monkeypatch.setattr("principia.local.service.httpx.get", fake_get)
    result = service.test_provider_connection("siliconflow")

    assert result == {
        "ok": True,
        "category": "connected",
        "retryable": False,
        "base_url": "https://api.siliconflow.cn/v1",
    }
    assert [item[0] for item in requests] == [
        "https://api.siliconflow.com/v1/models",
        "https://api.siliconflow.cn/v1/models",
    ]
    assert all(item[1] == f"Bearer {secret}" for item in requests)
    assert service.provider_profile().base_url == "https://api.siliconflow.cn/v1"

    reopened = LocalDiscoveryService(
        storage,
        repository,
        PrincipleSearchService(CloudRegistry(tmp_path / "cloud"), repository),
    )
    assert reopened.provider_profile().base_url == "https://api.siliconflow.cn/v1"
    assert secret not in json.dumps(reopened.provider_profile().model_dump(mode="json"))


def test_provider_repairs_invalid_json_once_and_records_hashes() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        content = "not-json" if len(calls) == 1 else json.dumps(_candidate("cand:fixture"))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": content}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20},
            },
        )

    policy = ModelPolicy(
        mode="remote",
        provider="siliconflow",
        model="fixture-model",
        base_url="https://api.siliconflow.com/v1",
        remote_egress_confirmed=True,
    )
    result = OpenAICompatibleProvider(
        policy,
        api_key="fixture-secret",
        transport=httpx.MockTransport(handler),
    ).generate_candidate(
        candidate_id="cand:fixture",
        area="demo-local",
        goal="Extract a bounded fixture",
        source_records=[{"work_id": "local:1", "title": "Fixture", "summary": "Text"}],
    )
    assert result.candidate.assessment_status == "unassessed"
    assert result.trace.repair_attempted is True
    assert result.trace.attempts == 2
    assert len(result.trace.output_sha256) == 64
    assert all(request.headers["authorization"] == "Bearer fixture-secret" for request in calls)


def test_provider_repairs_schema_echo_as_instance_data() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            content = json.dumps(
                {
                    "type": "object",
                    "properties": {"atoms": {"type": "array"}},
                    "required": ["atoms"],
                }
            )
        else:
            prompt = json.loads(request.content)["messages"][-1]["content"]
            assert "schema metadata instead of instance data" in prompt
            content = json.dumps(
                {
                    "atoms": [
                        {
                            "source_key": "source:0",
                            "assertion_type": "observed_result",
                            "evidence_type": "experiment",
                            "epistemic_status": "observed",
                            "support_segment_keys": ["seg:0:span:0"],
                        }
                    ]
                }
            )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": content}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20},
            },
        )

    generation = OpenAICompatibleProvider(
        ModelPolicy(
            mode="remote",
            provider="siliconflow",
            model="fixture-model",
            base_url="https://api.siliconflow.com/v1",
            remote_egress_confirmed=True,
        ),
        api_key="fixture-secret",
        transport=httpx.MockTransport(handler),
    ).extract_evidence_atoms(
        area="demo-local",
        goal="When does verification reduce errors?",
        source_records=[{"source_key": "source:0", "title": "Fixture"}],
        evidence_segments=[
            {
                "segment_key": "seg:0",
                "section": "results",
                "text": "Independent verification reduced selection errors in the test setting.",
            }
        ],
    )
    assert generation.trace.repair_attempted is True
    atoms = EvidenceClaimAtomBatch.model_validate(generation.value)
    assert atoms.atoms[0].support[0].segment_key == "seg:0"


def test_empty_argument_batch_recovers_relationship_bearing_evidence() -> None:
    calls: list[httpx.Request] = []
    atom_id = "atom:formal-relation-fixture"
    faithful_claim = (
        "If a bounded component satisfies the stated scale inequalities, "
        "then its excess decreases with the inverse scale parameter."
    )

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            content: dict[str, object] = {"arguments": []}
        else:
            system = json.loads(request.content)["messages"][0]["content"]
            assert "bounded recovery pass" in system
            content = {
                "arguments": [
                    {
                        "scientific_contract_version": "scientific-principle-v2",
                        "canonical_claim": faithful_claim,
                        "claim_class": "formal_proposition",
                        "subject_system": "bounded formal components",
                        "driver_or_intervention": "the stated scale inequalities",
                        "outcome": "component excess",
                        "direction_or_qualifier": "decreases with inverse scale",
                        "conditions": ["the source-defined inequalities hold"],
                        "boundary": ["limited to the reported formal system"],
                        "boundary_provenance": "conservative_study_limit",
                        "generalization_level": "study_bound",
                        "testability": "Verify the implication under the stated inequalities.",
                        "testability_provenance": "generated_challenge",
                        "atom_ids": [atom_id],
                        "field_support": [
                            {"field": field, "atom_ids": [atom_id]}
                            for field in (
                                "canonical_claim",
                                "subject_system",
                                "driver_or_intervention",
                                "outcome",
                                "direction_or_qualifier",
                                "conditions",
                            )
                        ],
                    }
                ]
            }
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(content)}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20},
            },
        )

    provider = OpenAICompatibleProvider(
        ModelPolicy(
            mode="remote",
            provider="siliconflow",
            model="fixture-model",
            base_url="https://api.siliconflow.com/v1",
            remote_egress_confirmed=True,
        ),
        api_key="fixture-secret",
        transport=httpx.MockTransport(handler),
    )
    generation = provider.normalize_scientific_arguments(
        area="",
        goal="",
        atoms=[
            {
                "atom_id": atom_id,
                "source_key": "source:0",
                "faithful_claim": faithful_claim,
                "assertion_type": "formal_result",
                "evidence_type": "formal_proof",
                "epistemic_status": "derived",
                "support": [
                    {
                        "segment_key": "seg:formal",
                        "quotation": faithful_claim,
                        "supported_fields": [
                            "canonical_claim",
                            "subject_system",
                            "driver_or_intervention",
                            "outcome",
                            "direction_or_qualifier",
                            "conditions",
                        ],
                    }
                ],
            }
        ],
    )

    arguments = ScientificArgumentBatch.model_validate(generation.value).arguments
    assert len(arguments) == 1
    assert arguments[0].canonical_claim == faithful_claim
    assert generation.trace.prompt_template == "scientific-arguments-v2+empty-recovery"
    assert generation.trace.attempts == 2
    assert generation.trace.transport_attempts == 2
    assert generation.trace.input_tokens == 20
    assert generation.trace.output_tokens == 40
    assert len(calls) == 2


def test_two_explicit_empty_argument_batches_are_a_valid_zero_result() -> None:
    calls: list[httpx.Request] = []
    atom_id = "atom:bounded-zero-fixture"
    faithful_claim = "The workflow reduces runtime under the reported benchmark conditions."

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"arguments":[]}'}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2},
            },
        )

    provider = OpenAICompatibleProvider(
        ModelPolicy(
            mode="remote",
            provider="siliconflow",
            model="fixture-model",
            base_url="https://api.siliconflow.com/v1",
            remote_egress_confirmed=True,
        ),
        api_key="fixture-secret",
        transport=httpx.MockTransport(handler),
    )
    generation = provider.normalize_scientific_arguments(
        area="",
        goal="",
        atoms=[
            {
                "atom_id": atom_id,
                "source_key": "source:0",
                "faithful_claim": faithful_claim,
                "assertion_type": "observed_result",
                "evidence_type": "experiment",
                "epistemic_status": "observed",
                "support": [
                    {
                        "segment_key": "seg:zero",
                        "quotation": faithful_claim,
                        "supported_fields": ["canonical_claim"],
                    }
                ],
            }
        ],
    )
    assert ScientificArgumentBatch.model_validate(generation.value).arguments == []
    assert len(calls) == 2


def test_read_timeout_is_not_immediately_retried_as_a_duplicate_paid_call() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("response is still pending", request=request)

    provider = OpenAICompatibleProvider(
        ModelPolicy(
            mode="remote",
            provider="siliconflow",
            model="fixture-model",
            base_url="https://api.siliconflow.com/v1",
            remote_egress_confirmed=True,
        ),
        api_key="fixture-secret",
        transport=httpx.MockTransport(handler),
        timeout=600,
    )
    try:
        with pytest.raises(ProviderRequestError) as captured:
            provider.extract_evidence_atoms(
                area="engineering-robotics",
                goal="autonomous robotics",
                source_records=[
                    {"source_key": "source:0", "work_id": "W-TIMEOUT", "title": "Robotics"}
                ],
                evidence_segments=[
                    {
                        "segment_key": "segment:0",
                        "section": "results",
                        "page_start": 1,
                        "text": "The autonomous controller reduced manufacturing errors.",
                    }
                ],
            )
    finally:
        provider.close()

    assert calls == 1
    assert captured.value.category == "timeout"
    assert "10 minutes" in str(captured.value)


def test_challenge_repairs_only_missing_argument_decisions() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        index = 0 if len(calls) == 1 else 1
        content = {
            "decisions": [
                {
                    "argument_index": index,
                    "verdict": "supported",
                    "reason_codes": [],
                    "note": "The supplied evidence supports this bounded relation.",
                }
            ]
        }
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(content)}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20},
            },
        )

    generation = OpenAICompatibleProvider(
        ModelPolicy(
            mode="remote",
            provider="siliconflow",
            model="fixture-model",
            base_url="https://api.siliconflow.com/v1",
            remote_egress_confirmed=True,
        ),
        api_key="fixture-secret",
        transport=httpx.MockTransport(handler),
    ).challenge_scientific_arguments(
        area="demo-local",
        goal="When does verification reduce errors?",
        atoms=[{"atom_id": "atom:fixture"}],
        arguments=[{"canonical_claim": "first"}, {"canonical_claim": "second"}],
    )
    decisions = ChallengeDecisionBatch.model_validate(generation.value)
    assert [item.argument_index for item in decisions.decisions] == [0, 1]
    assert generation.trace.repair_attempted is True
    assert generation.trace.attempts == 2
    second_prompt = json.loads(calls[1].content)["messages"][0]["content"]
    assert "missing original indices [1]" in second_prompt


def test_no_llm_discovery_indexes_without_fabricating_candidates(tmp_path: Path) -> None:
    source = tmp_path / "private-source"
    source.mkdir()
    (source / "notes.txt").write_text(
        "Synthetic observations for a deterministic local fixture.", encoding="utf-8"
    )
    storage = WorkspaceStorage(tmp_path / "workspace")
    repository = V14WorkspaceRepository(storage.db_path)
    cloud = CloudRegistry(tmp_path / "cloud")
    service = LocalDiscoveryService(storage, repository, PrincipleSearchService(cloud, repository))
    registered = service.register_source(source)
    assert str(source) not in json.dumps(service.list_sources())
    job = service.start(
        source_id=registered["source_id"],
        goal="Index without LLM",
        area="demo-local",
        policy=ModelPolicy(mode="no_llm"),
    )
    deadline = time.monotonic() + 10
    current = job
    while current.state not in {"succeeded", "failed", "cancelled"} and time.monotonic() < deadline:
        time.sleep(0.02)
        current = service.get(job.job_id) or current
    assert current.state == "succeeded", current.error
    assert current.result is not None
    assert current.result["candidate_count"] == 0
    assert "not fabricated" in current.result["message"]
    assert repository.list_candidates() == []


def test_startup_reconciles_orphaned_job(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path / "workspace")
    repository = V14WorkspaceRepository(storage.db_path)
    from principia.domain import JobRecord

    repository.save_job(JobRecord(job_id="job:orphan", kind="fixture", state="running"))
    LocalDiscoveryService(
        storage,
        repository,
        PrincipleSearchService(CloudRegistry(tmp_path / "cloud"), repository),
    )
    recovered = repository.get_job("job:orphan")
    assert recovered is not None
    assert recovered.state == "interrupted"


def test_startup_reconciles_orphaned_queued_job(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path / "workspace")
    repository = V14WorkspaceRepository(storage.db_path)
    from principia.domain import JobRecord

    repository.save_job(JobRecord(job_id="job:queued-orphan", kind="fixture"))
    LocalDiscoveryService(
        storage,
        repository,
        PrincipleSearchService(CloudRegistry(tmp_path / "cloud"), repository),
    )
    recovered = repository.get_job("job:queued-orphan")
    assert recovered is not None
    assert recovered.state == "interrupted"


def test_job_heartbeat_advances_elapsed_time_without_overwriting_progress(tmp_path: Path) -> None:
    from principia.domain import JobRecord

    storage = WorkspaceStorage(tmp_path / "workspace")
    repository = V14WorkspaceRepository(storage.db_path)
    repository.save_job(
        JobRecord(
            job_id="job:heartbeat",
            kind="local_extraction",
            state="running",
            stage="Extract evidence",
            progress=0.25,
            completed_units=1,
            total_units=4,
            status_message="Waiting for provider output",
        )
    )

    repository.heartbeat_job("job:heartbeat", elapsed_seconds=12.3)
    current = repository.get_job("job:heartbeat")

    assert current is not None
    assert current.elapsed_seconds == 12.3
    assert current.progress == 0.25
    assert current.completed_units == 1
    assert current.status_message == "Waiting for provider output"


def test_startup_corrects_legacy_all_failed_extraction_receipt(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path / "workspace")
    repository = V14WorkspaceRepository(storage.db_path)
    from principia.domain import JobRecord

    repository.save_job(
        JobRecord(
            job_id="job:misreported",
            kind="local_extraction",
            state="succeeded",
            stage="Complete",
            result={"processed_documents": 0, "failed_documents": 3},
        )
    )
    service = LocalDiscoveryService(
        storage,
        repository,
        PrincipleSearchService(CloudRegistry(tmp_path / "cloud"), repository),
    )
    recovered = repository.get_job("job:misreported")
    assert service.corrected_extraction_count == 1
    assert recovered is not None
    assert recovered.state == "failed"
    assert recovered.stage == "Needs attention"
    assert recovered.error is not None
    assert "did not process any" in recovered.error["message"]


def test_retry_uses_current_server_owned_profile_and_saved_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PRINCIPIA_LLM_BASE_URL", "https://current.example/v1")
    storage = WorkspaceStorage(tmp_path / "workspace")
    repository = V14WorkspaceRepository(storage.db_path)
    service = LocalDiscoveryService(
        storage,
        repository,
        PrincipleSearchService(CloudRegistry(tmp_path / "cloud"), repository),
    )
    service.save_provider_credential("siliconflow", "current-private-key")
    from principia.domain import JobRecord

    failed = JobRecord(
        job_id="job:retry-profile",
        kind="local_extraction",
        state="failed",
        checkpoint={
            "policy": {
                "mode": "remote",
                "provider": "siliconflow",
                "model": "custom-lab/custom-model",
                "base_url": "https://stale.example/v1",
                "remote_egress_confirmed": True,
            }
        },
    )
    repository.save_job(failed)
    captured: dict[str, object] = {}

    def retry(job_id: str, **kwargs: object) -> JobRecord:
        captured.update(kwargs)
        return failed

    monkeypatch.setattr(service.extraction, "retry_failed", retry)
    service.retry_failed(failed.job_id)
    retry_policy = captured["policy"]
    assert isinstance(retry_policy, ModelPolicy)
    assert retry_policy.base_url == "https://current.example/v1"
    assert retry_policy.model == "custom-lab/custom-model"
    assert captured["api_key"] == "current-private-key"
