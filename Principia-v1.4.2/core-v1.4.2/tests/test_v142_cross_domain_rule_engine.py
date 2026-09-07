from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from principia import Principia
from principia.data_discovery.adapters import AssetInventory
from principia.data_discovery.collection_operators import (
    _collection_outcome,
    analyze_collection,
)
from principia.data_discovery.operators import analyze_asset
from principia.data_discovery.rule_engine import (
    GATE_CONTRACT_VERSION,
    _executor_for,
    _family_kind,
    _law_ast,
    outcomes_to_law_bundle,
)
from principia.domain import ScientificProgram


def _program(study_id: str) -> ScientificProgram:
    return ScientificProgram(
        program_id=f"program:{study_id}",
        study_id=study_id,
        track="predictive_closure",
        title="Cross-domain scientific program",
        scientific_intent="Evaluate evidence-bearing scientific law candidates.",
        program_digest="0" * 64,
    )


def test_executor_dispatch_does_not_misread_square_root_as_root_file() -> None:
    assert _executor_for("rydberg_efield_square_root_power_law") == "response_curve_law"
    assert _executor_for("root_transverse_vector_kinematic_identity") == "scientific_invariant"
    assert _executor_for("htops_ai_breadth_replication_law") == "survey_law"
    assert _family_kind("rydberg_efield_square_root_power_law") == "scaling"
    assert r"f/f_0" in _law_ast(
        "masked_hdf5_spectral_power_envelope", []
    ).model_dump_json()


def test_generic_single_sweep_cannot_claim_independent_replication(tmp_path: Path) -> None:
    source = tmp_path / "generic"
    source.mkdir()
    rows = ["temperature,response"]
    for index in range(1, 301):
        response = 2.5 * index**1.7 * (1 + 0.002 * math.sin(index))
        rows.append(f"{index},{response:.12g}")
    (source / "renamed.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    inventory = AssetInventory().inventory(
        root=source, source_id="source:generic", study_id="study:generic"
    )
    outcome = analyze_asset(
        study_id="study:generic",
        asset=next(item for item in inventory.assets if item.role == "raw"),
        root=source,
    )
    assert outcome is not None
    assert outcome.plan.operator == "typed_nonlinear_law_selection"
    bundle = outcomes_to_law_bundle(
        study_id="study:generic",
        program=_program("study:generic"),
        outcomes=[outcome],
    )
    assert len(bundle.laws) == 1
    law = bundle.laws[0]
    assert law.evidence_tier == "candidate"
    assert law.gate_summary["gate_contract_version"] == GATE_CONTRACT_VERSION
    replication = next(
        item for item in law.gate_receipts if item.metric == "independent_replication"
    )
    assert replication.passed is False
    assert replication.observed == 2
    baseline_receipt = next(item for item in law.gate_receipts if item.metric == "baseline_dominance")
    assert baseline_receipt.execution_state == "unfinished"


def test_structure_bound_rydberg_law_excludes_stored_fit_columns(tmp_path: Path) -> None:
    source = tmp_path / "renamed-experiment"
    source.mkdir()
    rows = [
        "sqrt(P_sig) EIT,E_RF EIT,Fit_EIT,sqrt(P_sig) Ion,E_RF Ion,Fit_Ion"
    ]
    for index in range(24):
        x = 0.2 + 0.15 * index
        eit = 0.04 + 0.78 * x + 0.008 * math.sin(index)
        ion = -0.03 + 0.84 * x + 0.008 * math.cos(index)
        rows.append(f"{x},{eit},{999 + index},{x},{ion},{1999 + index}")
    (source / "arbitrary.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    inventory = AssetInventory().inventory(
        root=source, source_id="source:rydberg", study_id="study:rydberg"
    )
    outcomes, limitations = analyze_collection(
        study_id="study:rydberg", assets=inventory.assets, root=source
    )
    assert limitations == []
    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome.plan.operator == "rydberg_efield_square_root_power_law"
    assert outcome.finding.status == "supported_candidate"
    assert outcome.result.estimate["calibrations"]
    assert outcome.result.split_validation["negative_control"]["passed"] is True
    assert all(
        "Fit" not in pair
        for calibration in outcome.result.estimate["calibrations"]
        for pair in (calibration["readout"], calibration["power_coordinate"])
    )
    bundle = outcomes_to_law_bundle(
        study_id="study:rydberg",
        program=_program("study:rydberg"),
        outcomes=outcomes,
    )
    law = bundle.laws[0]
    assert law.executor_id == "response_curve_law"
    assert law.rule_kind == "empirical_predictive"
    assert law.gate_summary["passed"] is True
    assert law.evidence_tier == "internal_locked_validation"
    assert all(item.execution_state == "passed" for item in law.gate_receipts)
    assert all(item.input_digest and item.code_digest for item in law.gate_receipts)
    # Correlated readouts share power-setting partitions. Locked responses
    # cannot alter coefficients or predictions, even when they falsify the law.
    assignments = outcome.result.split_validation["frozen_manifest"]["assignments"]
    assert len(assignments) == 24
    original_calibrations = outcome.result.estimate["calibrations"]
    modified = [rows[0]]
    for index, row in enumerate(rows[1:]):
        values = row.split(",")
        if index % 5 == 4:
            values[1], values[4] = "1000", "-1000"
        modified.append(",".join(values))
    (source / "arbitrary.csv").write_text("\n".join(modified) + "\n")
    changed, _ = analyze_collection(study_id="study:rydberg", assets=inventory.assets, root=source)
    assert changed[0].finding.status != "supported_candidate"
    for before, after in zip(original_calibrations, changed[0].result.estimate["calibrations"], strict=True):
        assert before["equation_parameters"] == after["equation_parameters"]
        assert [r["prediction"] for r in before["frozen_predictions"]] == [r["prediction"] for r in after["frozen_predictions"]]


def test_service_executes_per_file_rule_program_after_collection_pass(
    tmp_path: Path,
) -> None:
    xarray = __import__("xarray")
    source = tmp_path / "field-source"
    source.mkdir()
    axis = np.linspace(-2.0, 2.0, 64)
    xx, yy = np.meshgrid(axis, axis)
    field = np.exp(-0.7 * (xx**2 + yy**2)) + 0.12 * np.cos(2.0 * xx)
    dataset = xarray.Dataset(
        {"temperature_anomaly": (("sample_y", "sample_x"), field)},
        coords={"sample_y": axis, "sample_x": axis},
    )
    dataset["temperature_anomaly"].attrs["units"] = "K"
    dataset.to_netcdf(source / "renamed-field.nc")

    product = Principia.open(
        working_directory=tmp_path / "working",
        cloud_root=tmp_path / "cloud",
    )
    try:
        product.repository.register_source(
            "src:field", source, "external://field", "Field", "External/Test"
        )
        study = product.data_discovery.create(
            source_ids=["src:field"],
            provider="",
            budget="fast",
            egress_confirmed=False,
            defer=False,
        )
        rules = product.data_discovery.rules(study["study_id"])
        assert rules == []
        candidates = product.data_discovery.laws(study["study_id"])
        assert len(candidates) == 1
        assert candidates[0]["executor_id"] == "spatial_event_law"
        assert candidates[0]["gate_summary"]["passed"] is False
        assert product.data_discovery.findings(study["study_id"])
    finally:
        product.close()


def test_acceptance_gate_is_non_vacuous_and_cross_executor() -> None:
    runner = (
        Path(__file__).resolve().parents[1] / "scripts" / "run_v142_acceptance_campaign.py"
    ).read_text(encoding="utf-8")
    summary = (
        Path(__file__).resolve().parents[1] / "scripts" / "summarize_v142_acceptance.py"
    ).read_text(encoding="utf-8")
    assert 'numbered_scenarios_with_qualifying_rules"] >= 10' in runner
    assert 'len(campaign["qualifying_rule_executor_ids"]) >= 5' in runner
    assert 'campaign["supported_finding_contract_gate"]' in runner
    assert "not rule_yield_gate" in summary


def test_collection_outcome_deduplicates_one_asset_used_in_two_split_roles(
    tmp_path: Path,
) -> None:
    source = tmp_path / "one-wave-survey"
    source.mkdir()
    (source / "wave.csv").write_text("region,value\n1,2\n", encoding="utf-8")
    inventory = AssetInventory().inventory(
        root=source, source_id="source:one-wave", study_id="study:one-wave"
    )
    asset = next(item for item in inventory.assets if item.role == "raw")
    outcome = _collection_outcome(
        study_id="study:one-wave",
        assets=[asset, asset],
        operator="survey_geographic_holdout",
        hypothesis_claim="A relationship may transfer across geographic blocks.",
        expected_relationship="The locked geographic block retains the development direction.",
        confounders=["region"],
        falsifier="The direction reverses in the locked block.",
        sample_definition="one official wave split into disjoint geographic blocks",
        independent_unit_count=2,
        parameters={"split": "geographic"},
        estimate={"coefficient": 1.0},
        uncertainty={"standard_error": 0.1},
        sensitivities=[],
        diagnostics=[],
        negative_evidence=[],
        title="Geographic holdout relationship",
        claim="The relationship transferred.",
        interpretation="The split is stored in one payload.",
        mechanism="A shared process may operate across regions.",
        supported=True,
        validation_level="internal_holdout",
        robustness=["disjoint geographic blocks"],
        limits=["single survey wave"],
        next_validation="Repeat in a later wave.",
        units={"value": "arbitrary unit"},
    )
    assert len(outcome.hypothesis.input_view_ids) == 1
    assert len(outcome.finding.evidence_ids) == 1
    assert outcome.additional_evidence == ()
