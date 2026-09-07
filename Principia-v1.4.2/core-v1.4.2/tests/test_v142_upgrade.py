from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from principia.data_discovery.expression_search import (
    LawSearchSpec,
    freeze_assignments,
    partition_masks,
    search_expressions,
)
from principia.data_discovery.rule_engine import _gate_receipts, _law_ast


def _outcome(split):
    return SimpleNamespace(
        plan=SimpleNamespace(plan_digest="a" * 64, operator="survey_law"),
        result=SimpleNamespace(
            split_validation=split, result_digest="b" * 64,
            independent_unit_count=12, corrected_significance={"p": 0.01}, study_id="study:test",
        ),
        evidence=SimpleNamespace(evidence_id="evidence:test", result_digest="b" * 64),
        additional_evidence=(),
        finding=SimpleNamespace(transfer_scope="Within the sampled scientific units", status="supported_candidate"),
    )


@pytest.mark.parametrize("baseline", [{}, {"passed": False, "executed": True}])
def test_legacy_flags_cannot_qualify_missing_or_failed_execution(baseline):
    split = {
        "test": {"passed": True},
        "rule_gate": {key: True for key in ("interpretable_law_family", "held_out_baseline_improvement", "negative_control", "parameter_stability", "unit_plausibility")},
        "baseline_comparison": baseline,
    }
    receipts, promoted = _gate_receipts(outcome=_outcome(split), law_seed="c" * 64, ast=_law_ast("linear", []), rule_kind="empirical_predictive")
    assert not promoted
    indexed = {item.metric: item for item in receipts}
    assert indexed["falsifying_control"].execution_state == "unfinished"
    assert not indexed["baseline_dominance"].passed
    assert not indexed["locked_test"].passed
    assert not indexed["ast_replay"].passed


def _data():
    rng = np.random.default_rng(64)
    groups = np.repeat(np.arange(30), 20)
    x = rng.uniform(0.4, 2.5, (len(groups), 1))
    y = 2 + 3 * x[:, 0] ** 2 + rng.normal(0, 0.01, len(groups))
    return x, y, groups


def test_expression_search_recovers_law_and_seals_checkpoint(tmp_path):
    x, y, groups = _data()
    spec = LawSearchSpec(target="response", inputs=["driver"], independent_unit_kind="specimen", max_candidates=100)
    result = search_expressions(spec, x, y, groups, source_digest="a" * 64, checkpoint=tmp_path / "search.json")
    assert result["evaluated_count"] == 100
    assert 1 <= len(result["finalists"]) <= 3
    best = min(result["finalists"], key=lambda item: item["test_nrmse"])
    assert best["test_nrmse"] < 0.02
    assert best["passed"]
    assert result["manifest"]["frozen_before_fitting"]
    # Completed work returns its immutable evidence without evaluating again.
    replay = search_expressions(spec, x, y * 100, groups, source_digest="a" * 64, checkpoint=tmp_path / "search.json")
    assert replay["finalists"] == result["finalists"]
    with pytest.raises(ValueError, match="does not match"):
        search_expressions(spec, x, y, groups, source_digest="b" * 64, checkpoint=tmp_path / "search.json")


def test_locked_target_mutation_cannot_change_selection_or_predictions():
    x, y, groups = _data()
    spec = LawSearchSpec(target="response", inputs=["driver"], independent_unit_kind="specimen", max_candidates=40)
    first = search_expressions(spec, x, y, groups, source_digest="a" * 64)
    masks = partition_masks(groups, first["manifest"])
    changed = y.copy()
    changed[masks["test"]] += 1000
    second = search_expressions(spec, x, changed, groups, source_digest="b" * 64)
    assert first["selected_ordinals"] == second["selected_ordinals"]
    assert [item["prediction_digest"] for item in first["finalists"]] == [item["prediction_digest"] for item in second["finalists"]]
    assert not any(item["passed"] for item in second["finalists"])


def test_group_splits_never_split_repeated_units():
    _, _, groups = _data()
    manifest = freeze_assignments(groups, strategy="group")
    assert manifest == freeze_assignments(groups[::-1], strategy="group")
    masks = partition_masks(groups, manifest)
    assert np.all(sum(mask.astype(int) for mask in masks.values()) == 1)
    for unit in np.unique(groups):
        assert sum(bool(mask[groups == unit].any()) for mask in masks.values()) == 1
    with pytest.raises(ValueError, match="five independent"):
        freeze_assignments(np.repeat([1, 2], 1000), strategy="group")


def test_token_reservations_are_atomic_and_unknown_usage_stays_charged(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    from principia.providers.token_budget import TokenBudget, TokenBudgetExceeded
    budget = TokenBudget(tmp_path / "budget.sqlite", 5_000)
    def reserve():
        try:
            return budget.reserve([], 1_000)
        except TokenBudgetExceeded:
            return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        attempts = list(pool.map(lambda _: reserve(), range(8)))
    assert sum(item is not None for item in attempts) == 2
    assert budget.snapshot()["charged_tokens"] == 4_052
    identifier = next(item for item in attempts if item)
    budget.settle(identifier, {})
    assert budget.snapshot()["charged_tokens"] == 4_052
    budget.settle(identifier, {"prompt_tokens": 100, "completion_tokens": 50})
    assert budget.snapshot()["charged_tokens"] == 2_176
    with pytest.raises(ValueError, match="cannot be silently changed"):
        TokenBudget(tmp_path / "budget.sqlite", 10_000)


def test_export_edits_cannot_modify_canonical_evidence(tmp_path):
    from principia.data_discovery.artifact_io import copy_artifact
    source, destination = tmp_path / "canonical.json", tmp_path / "export.json"
    source.write_text('{"evidence": true}')
    copy_artifact(source, destination)
    destination.write_text("edited export")
    assert source.read_text() == '{"evidence": true}'
    assert source.stat().st_ino != destination.stat().st_ino


def test_remote_context_is_bounded_without_mutating_local_blueprint():
    import copy
    import json

    from principia.data_discovery.context_budget import compact_scientific_context
    context = {"scientific_focus": "Measure a response law", "study_blueprint": {"target_bindings": [{"view_id": "view:one", "name": "response", "role": "target"}], "independent_units": [{"view_id": "view:one", "name": "specimen"}]}, "asset_profiles": [{"asset_id": f"asset:{index}", "profile": {"first_row_sample": [999, 888], "sheets": [{"units": {f"column_{j}": "K" for j in range(100)}, "description": "x" * 3000} for _ in range(100)]}} for index in range(100)]}
    original = copy.deepcopy(context)
    compacted = compact_scientific_context(context)
    assert len(json.dumps(compacted, ensure_ascii=False).encode()) < 80_000
    assert "first_row_sample" not in json.dumps(compacted)
    assert compacted["study_blueprint"] == context["study_blueprint"]
    assert compacted["context_budget"]["compacted"]
    assert context == original


def test_project_home_resolves_alias_roots_atomically_and_get_is_read_only(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    from fastapi.testclient import TestClient

    from principia import Principia
    from principia.api import create_app
    product = Principia.open(working_directory=tmp_path / "working", cloud_root=tmp_path / "cloud")
    source = tmp_path / "source"
    source.mkdir()
    try:
        for alias in ("src:a", "src:b"):
            registered = source if alias == "src:a" else tmp_path / "historical-alias"
            registered.mkdir(exist_ok=True)
            product.repository.register_source(alias, registered, "fixture://" + alias, "Experiment", "Test")
        with product.repository.connect() as conn:
            conn.execute("UPDATE local_sources_v14 SET absolute_root=? WHERE source_id='src:b'", (str(source.resolve()),))
        assert product.research_sessions.source_set_digest(["src:a"]) == product.research_sessions.source_set_digest(["src:a", "src:b"])
        def create(_):
            return product.research_sessions.create_data_discovery_home(source_ids=["src:a"], title="Experiment", provider_profile_id="", model="")
        with ThreadPoolExecutor(max_workers=6) as pool:
            homes = list(pool.map(create, range(12)))
        assert len({home["session_id"] for home in homes}) == 1
        assert sum(home["created_project"] for home in homes) == 1
        client = TestClient(create_app(product, test_mode=True))
        endpoint = f"/api/v1/research-sessions/{homes[0]['session_id']}/workspace"
        with product.repository.connect() as conn:
            before = list(conn.iterdump())
        response = client.get(endpoint)
        assert response.status_code == 200
        assert client.get(endpoint, headers={"If-None-Match": response.headers["etag"]}).status_code == 304
        body = response.json()
        assert {item["record_id"] for item in body["records"]} == {item["principle_id"] for item in body["graph"]["items"]}
        with product.repository.connect() as conn:
            assert list(conn.iterdump()) == before
    finally:
        product.close()


def test_null_targets_do_not_become_qualified_rules():
    x, y, groups = _data()
    y = np.random.default_rng(12).normal(size=len(y))
    result = search_expressions(LawSearchSpec(target="response", inputs=["driver"], independent_unit_kind="specimen", max_candidates=100), x, y, groups, source_digest="a" * 64)
    assert not any(item["passed"] for item in result["finalists"])


def test_repeated_rows_cannot_create_independent_evidence():
    x, y, groups = _data()
    spec = LawSearchSpec(target="response", inputs=["driver"], independent_unit_kind="specimen", max_candidates=40)
    first = search_expressions(spec, x, y, groups, source_digest="a" * 64)
    repeated = np.tile(np.arange(len(groups)), 3)
    second = search_expressions(spec, x[repeated], y[repeated], groups[repeated], source_digest="b" * 64)
    assert first["manifest"] == second["manifest"]
    assert first["selected_ordinals"] == second["selected_ordinals"]
    assert [item["test_nrmse"] for item in second["finalists"]] == pytest.approx([item["test_nrmse"] for item in first["finalists"]], rel=1e-6)


def test_view_bound_search_persists_executable_qualified_family(tmp_path):
    from principia.data_discovery.adapters import AssetInventory
    from principia.data_discovery.expression_program import execute_expression_search
    from principia.data_discovery.rule_engine import outcomes_to_law_bundle
    from principia.domain import ScientificProgram, StudyBlueprint
    x, y, groups = _data()
    source = tmp_path / "source"
    source.mkdir()
    (source / "renamed.csv").write_text("specimen,driver,response\n" + "\n".join(f"specimen-{unit},{driver[0]},{target}" for driver, target, unit in zip(x, y, groups, strict=True)))
    inventory = AssetInventory().inventory(root=source, source_id="src:test", study_id="study:test")
    view = next(item for item in inventory.views if item.kind == "table").model_copy(update={"units": {"driver": "K", "response": "J"}})
    blueprint = StudyBlueprint(study_id="study:test", blueprint_digest="a" * 64, target_bindings=[{"view_id": view.view_id, "name": "response"}], input_bindings=[{"view_id": view.view_id, "name": "driver"}], independent_units=[{"view_id": view.view_id, "name": "specimen"}])
    program = ScientificProgram(study_id="study:test", program_id="program:test", track="predictive_closure", title="Fixture program", scientific_intent="Test a bound independent-unit response law.", program_digest="b" * 64)
    outcomes, receipts = execute_expression_search(study_id="study:test", program=program, blueprint=blueprint, assets_and_roots=[(asset, source) for asset in inventory.assets], views=[view], artifact_root=tmp_path / "artifacts", budget="fast", check_control=lambda: None)
    assert receipts[0]["evaluated_count"] > 100
    bundle = outcomes_to_law_bundle(study_id="study:test", program=program, outcomes=outcomes)
    qualified = [law for law in bundle.laws if law.gate_summary["passed"]]
    assert qualified
    assert all(gate.execution_state == "passed" for law in qualified for gate in law.gate_receipts)


@pytest.mark.parametrize("delimiter", [",", ";", "\t"])
def test_decimal_comma_materialization_preserves_scale_and_identifiers(delimiter):
    import csv
    import io

    from principia.data_discovery.operators import _delimited_stream
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=delimiter)
    writer.writerow(["specimen", "driver", "response"])
    writer.writerows([[f"unit-{i}", x, y] for i, (x, y) in enumerate([("1,5", "2,25"), ("2,125", "4,5"), ("3,5", "6,25"), ("4,5", "8,25")])])
    buffer.seek(0)
    loaded = _delimited_stream(buffer)
    assert loaded is not None
    assert loaded.values == pytest.approx(np.array([[1.5, 2.25], [2.125, 4.5], [3.5, 6.25], [4.5, 8.25]]))
    assert loaded.identifiers["specimen"].tolist() == [f"unit-{i}" for i in range(4)]
    assert loaded.locator["ambiguous_numeric_cells_masked"] == 0


def test_headerless_decimal_comma_keeps_first_observation():
    import io

    from principia.data_discovery.adapters import _table_profile
    from principia.data_discovery.operators import _delimited_stream
    content = "1,5;2,25\n2,5;4,25\n3,5;6,25\n4,5;8,25\n"
    loaded = _delimited_stream(io.StringIO(content))
    assert loaded is not None
    assert loaded.values.shape == (4, 2)
    assert loaded.values[0].tolist() == [1.5, 2.25]
    profile = _table_profile(content)
    assert not profile["header_inferred"]
    assert profile["column_count"] == 2
    assert profile["sample_rows"] == 4


@pytest.mark.parametrize("numbers", [["1,234.5", "2,345.6", "3,456.7"], ["1.234,5", "2.345,6", "3.456,7"]])
def test_unambiguous_grouping_keeps_physical_scale(numbers):
    from principia.data_discovery.operators import _rows_to_numeric
    loaded = _rows_to_numeric([[value] for value in numbers], header=["response"])
    assert loaded is not None
    assert loaded.values[:, 0] == pytest.approx([1234.5, 2345.6, 3456.7])


@pytest.mark.parametrize("ambiguous", [["1,234"], ["1,5", "1,234.5"]])
def test_unresolved_or_conflicting_punctuation_is_missing_with_receipt(ambiguous):
    from principia.data_discovery.operators import _rows_to_numeric
    loaded = _rows_to_numeric([[value] for value in [*ambiguous, "3", "4", "5"]], header=["response"])
    assert loaded is not None
    assert np.isnan(loaded.values[:len(ambiguous)]).all()
    assert loaded.locator["ambiguous_numeric_cells_masked"] == len(ambiguous)
