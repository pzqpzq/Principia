from __future__ import annotations

from pathlib import Path

import pytest

from principia.application import Principia
from principia.application.explorer import PrincipleExplorerService
from principia.domain import (
    CandidatePrinciple,
    PrincipleKind,
    PrincipleScope,
    VirtualPrincipleBatch,
    VirtualPrincipleProposal,
)
from principia.providers import ModelPolicy, ProviderTrace
from principia.providers.openai_compatible import (
    OpenAICompatibleProvider,
    ScientificGeneration,
)


def _parent(product: Principia, identifier: str, claim: str) -> None:
    product.repository.save_candidate(
        CandidatePrinciple(
            candidate_id=identifier,
            area="machine-intelligence",
            title=claim,
            claim=claim,
            kind=PrincipleKind.MECHANISTIC,
            scope=PrincipleScope(statement="multi-agent scientific reasoning"),
            falsifier="The intervention does not change discovery performance.",
        ),
        eligibility_status="eligible",
        quality_state="eligible",
    )


def test_virtual_principle_generation_is_bounded_and_saves_only_on_request(
    tmp_path: Path, monkeypatch
) -> None:
    product = Principia.open(tmp_path / "workspace", cloud_root=tmp_path / "cloud")
    first = "cand:parent-one"
    second = "cand:parent-two"
    _parent(
        product,
        first,
        "Independent critic agents expose hidden assumptions in scientific hypotheses.",
    )
    _parent(
        product,
        second,
        "Persistent experiment memory prevents repeated low-value scientific trials.",
    )
    proposal = VirtualPrincipleProposal(
        title="Critic-guided memory prioritizes informative experiments",
        claim=(
            "Combining independent critic feedback with persistent experiment memory may "
            "prioritize experiments that resolve previously identified assumptions."
        ),
        area="machine-intelligence",
        derivation_level="mechanistic_bridge",
        scope_statement="Multi-agent discovery workflows with explicit experiment histories.",
        conditions=["critic failures are not perfectly correlated"],
        exclusions=["tasks without measurable experimental feedback"],
        falsifier=(
            "The combined workflow selects no more assumption-resolving experiments than "
            "memory-only and critic-only controls."
        ),
        assumptions=["past experiment outcomes remain comparable"],
        contributing_principle_ids=[first, second],
        synthesis_summary=(
            "Critics identify unresolved assumptions while memory records which tests have "
            "already failed to resolve them."
        ),
        reliability_rationale=(
            "The bridge preserves the scope of both parents and states the transfer assumption."
        ),
        novelty_rationale=(
            "Neither parent alone proposes prioritization by unresolved-assumption coverage."
        ),
        reliability_score=74,
        novelty_score=81,
    )
    trace = ProviderTrace(
        provider="siliconflow",
        model="fixture-model",
        prompt_template="virtual-principles-v1",
        prompt_sha256="a" * 64,
        input_sha256="b" * 64,
        output_sha256="c" * 64,
        latency_ms=20,
        input_tokens=120,
        output_tokens=80,
        attempts=1,
        transport_attempts=1,
        schema_valid=True,
    )

    monkeypatch.setattr(
        product.local,
        "provider_configuration",
        lambda *_args, **_kwargs: (
            None,
            ModelPolicy(
                mode="remote",
                provider="siliconflow",
                model="fixture-model",
                base_url="https://api.siliconflow.com/v1",
                remote_egress_confirmed=True,
            ),
            "fixture-key",
        ),
    )
    monkeypatch.setattr(
        OpenAICompatibleProvider,
        "derive_virtual_principles",
        lambda *_args, **_kwargs: ScientificGeneration(
            value=VirtualPrincipleBatch(
                cross_principle_map=["Critic findings can index unresolved memory entries."],
                proposals=[proposal],
            ),
            trace=trace,
        ),
    )

    generated = product.virtual_principles.generate(
        principle_ids=[first, second],
        provider_profile_id="siliconflow",
        model="fixture-model",
        egress_confirmed=True,
        requested_count=1,
        research_direction="Improve experiment selection",
    )

    assert len(generated["items"]) == 1
    assert generated["items"][0]["virtual_id"].startswith("virtual:")
    assert product.repository.list_candidates(limit=100)[0].candidate_id in {first, second}

    saved = product.virtual_principles.save(
        generated["items"][0]["proposal"],
        provider=generated["provider"],
        model=generated["model"],
        trace=generated["trace"],
    )

    assert saved["candidate_id"] not in {first, second}
    assert saved["raw_legacy_payload"]["virtual_principle"] is True
    assert saved["raw_legacy_payload"]["parent_principle_ids"] == [first, second]
    assert {item["target_principle_id"] for item in saved["relations"]} == {first, second}
    card = next(
        item
        for item in product.explorer.browse(
            scope="local", evidence_status="", limit=100
        )["items"]
        if item["id"] == saved["candidate_id"]
    )
    assert card["virtual"] is True
    assert card["human_review_status"] == "pending"
    saved_view = product.explorer.browse(
        scope="local", evidence_status="checking", virtual_only=True, limit=100
    )
    assert [item["id"] for item in saved_view["items"]] == [saved["candidate_id"]]


def test_virtual_workflows_accept_twenty_selected_principles(tmp_path: Path) -> None:
    product = Principia.open(tmp_path / "workspace", cloud_root=tmp_path / "cloud")
    identifiers = [f"cand:parent-{index:02d}" for index in range(20)]
    for index, identifier in enumerate(identifiers):
        _parent(
            product,
            identifier,
            f"Mechanism {index} contributes a distinct constraint to scientific discovery.",
        )

    connections = product.explorer.potential_relations(identifiers)
    assert connections["analyzed_pair_count"] == 190
    extra = "cand:parent-20"
    _parent(product, extra, "An additional mechanism exceeds the bounded selection tray.")
    with pytest.raises(ValueError, match="two and twenty"):
        product.explorer.potential_relations([*identifiers, extra])

    proposal = VirtualPrincipleProposal(
        title="Twenty-mechanism synthesis defines a composite discovery hypothesis",
        claim=(
            "Combining the twenty independently selected constraints may expose a composite "
            "boundary that is invisible when each Principle is considered alone."
        ),
        area="machine-intelligence",
        derivation_level="cross_context_generalization",
        scope_statement="Scientific discovery systems represented by all selected mechanisms.",
        conditions=["each parent remains applicable in the composite setting"],
        exclusions=["settings where any parent is known to be invalid"],
        falsifier="A complete ablation finds no composite boundary beyond every single parent.",
        assumptions=["the selected scopes can be compared without category error"],
        contributing_principle_ids=identifiers,
        synthesis_summary=(
            "The proposal preserves all twenty selected parents as inspectable provenance."
        ),
        reliability_rationale=(
            "Reliability remains limited because compatibility across all scopes is unverified."
        ),
        novelty_rationale=(
            "The proposed boundary is defined only by the joint twenty-parent configuration."
        ),
        reliability_score=61,
        novelty_score=88,
    )
    saved = product.virtual_principles.save(
        proposal,
        provider="fixture",
        model="fixture-model",
        trace={},
    )
    assert len(saved["raw_legacy_payload"]["parent_principle_ids"]) == 20
    assert len(saved["relations"]) == 20


def test_graph_metrics_vary_with_evidence_and_network_position() -> None:
    nodes = [
        {
            "id": "center",
            "supporting_work_count": 4,
            "evidence_anchor_count": 7,
            "human_review_status": "reviewed",
            "reliability_score": None,
        },
        {
            "id": "supported",
            "supporting_work_count": 2,
            "evidence_anchor_count": 2,
            "human_review_status": "reviewed",
            "reliability_score": None,
        },
        {
            "id": "context",
            "supporting_work_count": 0,
            "evidence_anchor_count": 0,
            "human_review_status": "pending",
            "reliability_score": None,
        },
    ]
    edges = [
        {
            "source": "center",
            "target": "supported",
            "relation_type": "supports",
            "edge_class": "validated",
        },
        {
            "source": "center",
            "target": "context",
            "relation_type": "semantic_affinity",
            "edge_class": "semantic_affinity",
        },
    ]

    PrincipleExplorerService._apply_graph_metrics(nodes, edges)
    by_id = {item["id"]: item for item in nodes}

    assert by_id["center"]["influence_score"] > by_id["supported"]["influence_score"]
    assert by_id["center"]["reliability_score"] > by_id["context"]["reliability_score"]
    assert len({item["reliability_score"] for item in nodes}) == 3
