from __future__ import annotations

from pathlib import Path

import pytest

from principia.application import PrincipleGraphService, PrincipleSearchService
from principia.cloud import CloudInstaller, CloudRegistry, build_pcp
from principia.domain import (
    CandidatePrinciple,
    GenerationTrace,
    PrincipleCapsule,
    PrincipleKind,
    PrincipleMaturity,
    PrincipleRelation,
    PrincipleScope,
    QualityAssessment,
    RelationType,
    TraceOperation,
    WorkReference,
    canonical_sha256,
    file_sha256,
    principle_id,
)
from principia.models import WorkItem
from principia.persistence import V14WorkspaceRepository
from principia.scenario import ScenarioService
from principia.storage import WorkspaceStorage


def _global_capsule(identity: str, ghost: str) -> PrincipleCapsule:
    return PrincipleCapsule(
        principle_id=identity,
        area="demo-computation",
        version=1,
        title="Deterministic search fixture",
        claim="Search fixture outputs are deterministic.",
        kind=PrincipleKind.EMPIRICAL,
        maturity=PrincipleMaturity.SUPPORTED,
        scope=PrincipleScope(statement="Fixture runtime"),
        quality=QualityAssessment(
            grade="A",
            validity=0.9,
            reproducibility=0.9,
            evidence_strength=0.9,
            generality=0.8,
            usefulness=0.9,
            assessed_by="fixture-reviewer",
        ),
        falsifier="Repeated output differs.",
        source_references=[WorkReference(work_id="work:fixture", title="Fixture evidence")],
        relations=[
            PrincipleRelation(
                relation_type=RelationType.DEPENDS_ON,
                target_principle_id=ghost,
                target_area="demo-uninstalled",
                minimum_package_version="1.0.0",
            )
        ],
        generation_trace=[
            GenerationTrace(
                event_id="evt:fixture",
                operation=TraceOperation.REVIEW,
                actor="fixture-reviewer",
                input_sha256="1" * 64,
                output_sha256="2" * 64,
            )
        ],
        tags=["deterministic", "fixture"],
        source_count=1,
        relation_count=1,
        trace_count=1,
    )


def test_combined_search_and_ghost_graph(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path / "workspace")
    local = V14WorkspaceRepository(storage.db_path)
    local.save_candidate(
        CandidatePrinciple(
            candidate_id="cand:local-search",
            area="demo-local",
            title="Local deterministic candidate",
            claim="A local search fixture.",
            kind=PrincipleKind.HYPOTHESIS,
            scope=PrincipleScope(statement="Private fixture"),
        ),
        scientific_contract_version="scientific-principle-v2",
        quality_gate_version="quality-v2",
        quality_state="eligible",
    )
    global_id = principle_id("demo-computation")
    ghost_id = principle_id("demo-uninstalled")
    package_path = tmp_path / "global.pcp"
    receipt = build_pcp(
        package_path,
        area="demo-computation",
        display_name="Demo Computation",
        package_version="1.0.0",
        capsules=[_global_capsule(global_id, ghost_id)],
        readme="Synthetic acceptance data only.",
    )
    cloud = CloudRegistry(tmp_path / "cloud")
    CloudInstaller(cloud).install(receipt.catalog_entry(str(package_path)))
    search = PrincipleSearchService(cloud, local)
    results = search.search("deterministic", scope="combined")
    assert {item["source"] for item in results} == {"global", "local"}
    assert next(item for item in results if item["source"] == "local")["assessment"] == "unassessed"

    graph = PrincipleGraphService(search).neighborhood(global_id, depth=2, limit=60)
    assert graph["nodes"][0]["id"] == ghost_id or graph["nodes"][0]["id"] == global_id
    ghost = next(node for node in graph["nodes"] if node["id"] == ghost_id)
    assert ghost["ghost"] is True
    assert ghost["install_action"] is True
    assert graph["truncated"] is False
    assert graph["total_candidates"] == 0
    assert graph["total_global_principles"] == 1

    overview_service = PrincipleGraphService(search)
    global_overview = overview_service.overview(scope="global", limit=10)
    assert {node["source"] for node in global_overview["nodes"]} == {"global"}
    assert global_overview["counts"]["global_principles"] == 1
    assert global_overview["counts"]["installed_areas"] == 1
    combined_overview = overview_service.overview(scope="combined", limit=10)
    assert {node["source"] for node in combined_overview["nodes"]} == {
        "global",
        "local",
    }


def test_local_overview_derives_shared_paper_edges_in_bulk(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path / "workspace")
    repository = V14WorkspaceRepository(storage.db_path)
    storage.save_work(WorkItem(id="work:shared", title="Shared evidence fixture"))
    for suffix in ("a", "b", "c"):
        repository.save_candidate(
            CandidatePrinciple(
                candidate_id=f"cand:overview:{suffix}",
                area="demo-local",
                title=f"Overview Candidate {suffix}",
                claim=f"Candidate {suffix} has a bounded fixture claim.",
                kind=PrincipleKind.EMPIRICAL,
                scope=PrincipleScope(statement="Overview fixture"),
            ),
            scientific_contract_version="scientific-principle-v2",
            quality_gate_version="quality-v2",
            quality_state="eligible",
        )
    for suffix in ("a", "b"):
        repository.save_candidate_evidence(
            evidence_id=f"evidence:overview:{suffix}",
            candidate_id=f"cand:overview:{suffix}",
            work_id="work:shared",
            excerpt_sha256=suffix * 64,
        )
    graph = PrincipleGraphService(
        PrincipleSearchService(CloudRegistry(tmp_path / "cloud"), repository)
    ).overview(limit=3, include_shared_evidence=True)
    assert graph["edges"] == [
        {
            "id": "cand:overview:a|cand:overview:b|shared_evidence",
            "source": "cand:overview:a",
            "target": "cand:overview:b",
            "type": "shared_evidence",
            "edge_class": "derived",
            "provenance": "derived_shared_evidence",
            "shared_work_count": 1,
            "label": "1 shared evidence work",
        }
    ]
    focused = PrincipleGraphService(
        PrincipleSearchService(CloudRegistry(tmp_path / "cloud"), repository)
    ).neighborhood("cand:overview:a", scope="local")
    assert focused["total_candidates"] == 1
    assert focused["total_global_principles"] == 0


def test_local_search_respects_goal_and_folder_collection_boundaries(
    tmp_path: Path,
) -> None:
    storage = WorkspaceStorage(tmp_path / "workspace")
    repository = V14WorkspaceRepository(storage.db_path)
    source_ids: list[str] = []
    goal_ids: list[str] = []
    for index in range(2):
        root = tmp_path / f"papers-{index}"
        root.mkdir()
        source_id = f"src:filter:{index}"
        repository.register_source(source_id, root, f"local://filter/{index}", f"Folder {index}")
        goal_id = repository.resolve_research_goal(
            source_id=source_id,
            goal=f"How does verification mechanism {index} improve selection reliability?",
            area="machine-intelligence",
        )
        repository.save_candidate(
            CandidatePrinciple(
                candidate_id=f"cand:filter:{index}",
                area="machine-intelligence",
                title=f"Verification mechanism {index}",
                claim="Independent verification improves bounded selection reliability.",
                kind=PrincipleKind.EMPIRICAL,
                scope=PrincipleScope(statement="Collection filter fixture"),
            ),
            goal_id=goal_id,
            source_id=source_id,
            scientific_contract_version="scientific-principle-v2",
            quality_gate_version="quality-v2",
            quality_state="eligible",
        )
        source_ids.append(source_id)
        goal_ids.append(goal_id)

    search = PrincipleSearchService(CloudRegistry(tmp_path / "cloud"), repository)
    by_source = search.search(
        "verification reliability", scope="local", source_id=source_ids[0]
    )
    by_goal = search.search(
        "verification reliability", scope="local", goal_id=goal_ids[1]
    )
    assert [item["id"] for item in by_source] == ["cand:filter:0"]
    assert [item["id"] for item in by_goal] == ["cand:filter:1"]


def test_scenario_replay_branch_compare_and_discard_are_copy_on_write(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path / "workspace")
    repository = V14WorkspaceRepository(storage.db_path)
    canonical_digest = canonical_sha256([])
    scenarios = ScenarioService(repository, canonical_digest)
    scenario = scenarios.create("Counterfactual")
    scenarios.append(
        scenario.scenario_id,
        "add_virtual_principle",
        {"principle_id": "virtual:one", "title": "Virtual fixture"},
    )
    scenarios.append(
        scenario.scenario_id,
        "set_support_pressure",
        {"principle_id": "virtual:one", "value": 0.2},
    )
    first = scenarios.replay(scenario.scenario_id)
    second = scenarios.replay(scenario.scenario_id)
    assert first["overlay_digest"] == second["overlay_digest"]
    assert first["base_content_digest"] == canonical_digest
    assert first["depth"] == 2

    branch = scenarios.create("Branch", parent_scenario_id=scenario.scenario_id)
    assert scenarios.compare(scenario.scenario_id, branch.scenario_id)["equal"] is True
    scenarios.append(
        branch.scenario_id,
        "set_maturity",
        {"principle_id": "virtual:one", "maturity": "contested"},
    )
    assert scenarios.compare(scenario.scenario_id, branch.scenario_id)["equal"] is False
    exported = scenarios.export(branch.scenario_id)
    assert exported["schema_version"] == "principia-scenario-v1"
    scenarios.discard(branch.scenario_id)
    with pytest.raises(ValueError, match="discarded"):
        scenarios.append(
            branch.scenario_id,
            "set_scope",
            {"principle_id": "virtual:one", "scope": {}},
        )


def test_scenario_does_not_modify_immutable_package_bytes(tmp_path: Path) -> None:
    global_id = principle_id("demo-computation")
    ghost_id = principle_id("demo-uninstalled")
    package_path = tmp_path / "global.pcp"
    build_pcp(
        package_path,
        area="demo-computation",
        display_name="Demo Computation",
        package_version="1.0.0",
        capsules=[_global_capsule(global_id, ghost_id)],
        readme="Synthetic acceptance data only.",
    )
    before = file_sha256(package_path)
    storage = WorkspaceStorage(tmp_path / "workspace")
    service = ScenarioService(V14WorkspaceRepository(storage.db_path), canonical_sha256([]))
    scenario = service.create("Byte invariant")
    service.append(
        scenario.scenario_id,
        "pin_version",
        {"principle_id": global_id, "version": 1},
    )
    assert file_sha256(package_path) == before
