from __future__ import annotations

import numpy as np

from principia.application.project_description import describe_project
from principia.data_discovery.expression_search import (
    LawSearchSpec,
    partition_masks,
    search_expressions,
)
from principia.data_discovery.response_panels import _forecast_panel, coordinate_response_panels


def test_project_descriptions_explain_contents_and_drop_batch_codes():
    title, summary = describe_project(["03_physics_gwosc_o4a_h1_strain"], {})
    assert title == "Gravitational-wave strain"
    assert "frequency" in summary and "03" not in title
    title, summary = describe_project(
        ["42_reactor_temperature"], {"target_bindings": [{"variable": "conversion"}]}
    )
    assert title == "Reactor temperature"
    assert "conversion" in summary


def test_forecast_panel_embargo_and_gap_handling():
    times = np.arange(3000, dtype=float)
    times[1200:] += 20
    values = np.arange(3000, dtype=float)
    panel = _forecast_panel(None, times, values, "signal", "V", {})
    assert panel is not None and panel.persistence_input == 0
    assert not np.any(np.isin(panel.x[:, 0], [1200, 1201, 1202]))
    np.testing.assert_array_equal(panel.y, panel.x[:, 0] + 1)
    manifest = __import__(
        "principia.data_discovery.expression_search", fromlist=["freeze_assignments"]
    ).freeze_assignments(panel.groups, strategy=panel.strategy)
    masks = partition_masks(panel.groups, manifest)
    assert max(panel.x[masks["development"], 0]) + panel.locator["embargo_samples"] < min(
        panel.x[masks["validation"], 0]
    )
    assert max(panel.x[masks["validation"], 0]) + panel.locator["embargo_samples"] < min(
        panel.x[masks["test"], 0]
    )


def test_persistence_baseline_and_locked_target_mutation(tmp_path):
    rng = np.random.default_rng(143)
    x = rng.uniform(0.5, 2, (800, 1))
    y = 0.25 + 1.8 * x[:, 0]
    groups = np.repeat(np.arange(80), 10)
    spec = LawSearchSpec(
        target="response",
        inputs=["previous"],
        independent_unit_kind="acquisition block",
        persistence_input=0,
        max_candidates=30,
        max_finalists=1,
    )
    first = search_expressions(
        spec, x, y, groups, source_digest="a", checkpoint=tmp_path / "first.json"
    )
    masks = partition_masks(groups, first["manifest"])
    changed = y.copy()
    changed[masks["test"]] -= 20
    second = search_expressions(
        spec, x, changed, groups, source_digest="b", checkpoint=tmp_path / "second.json"
    )
    assert first["selected_ordinals"] == second["selected_ordinals"]
    a, b = first["finalists"][0], second["finalists"][0]
    assert a["baseline_kind"] == "persistence"
    assert a["parameters"] == b["parameters"] and a["prediction_digest"] == b["prediction_digest"]
    assert a["passed"] and not b["passed"]


def test_coordinate_binding_ignores_names_and_target_derived_columns(tmp_path):
    from types import SimpleNamespace

    asset = SimpleNamespace(format="csv")
    path = tmp_path / "anonymous.csv"
    lines = ["X (cm),Y (cm),Thickness # 1 (nm),MSE,A"]
    for i in range(12):
        for j in range(12):
            lines.append(f"{i},{j},{5 + i * i * 0.01},{i + j},{i * j}")
    path.write_text("\n".join(lines))
    [panel] = list(coordinate_response_panels(asset, path))
    assert panel.inputs == ["X (cm)", "Y (cm)"]
    assert len(np.unique(panel.groups)) == 36
    renamed = tmp_path / "unrelated.csv"
    # Change only response and nuisance columns, leaving the sampling contract fixed.
    changed = [lines[0], *[",".join([*line.split(",")[:2], "99", "0", "0"]) for line in lines[1:]]]
    renamed.write_text("\n".join(changed))
    [other] = list(coordinate_response_panels(asset, renamed))
    np.testing.assert_array_equal(panel.x, other.x)
    np.testing.assert_array_equal(panel.groups, other.groups)
    assert panel.locator == other.locator


def test_survival_law_is_physical_and_sealed_against_test_mutation():
    from principia.data_discovery.event_exceedance import fit_exceedance

    days = np.arange(50)
    offsets = np.arange(0, 3.01, 0.25)
    rng = np.random.default_rng(631)
    fractions = np.clip(
        np.exp(-2 * offsets)[None, :] + rng.normal(0, 0.01, (50, len(offsets))), 0, 1
    )
    first = fit_exceedance(days, fractions, offsets)
    mask = partition_masks(days, first["manifest"])["test"]
    changed = fractions.copy()
    changed[mask] = 1 - changed[mask]
    second = fit_exceedance(days, changed, offsets)
    assert first["rate"] == second["rate"]
    assert first["selected_ordinal"] == second["selected_ordinal"]
    assert first["prediction_digest"] == second["prediction_digest"]
    assert first["passed"] and not second["passed"]
    predicted = np.asarray(first["prediction"])
    assert predicted[0] == 1 and np.all((predicted > 0) & (predicted <= 1))
    assert np.all(np.diff(predicted) < 0)
