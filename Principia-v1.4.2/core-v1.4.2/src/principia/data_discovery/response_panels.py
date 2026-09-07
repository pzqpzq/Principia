"""Executable response searches for measured arrays with explicit sampling contracts.

Adapters expose measurement coordinates and genuine acquisition blocks. They never
use filenames for applicability or turn a row index into a scientific predictor.
"""

from __future__ import annotations

import csv
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from ..domain import EquationNode, canonical_sha256
from .collection_operators import _collection_outcome, _safe_path
from .expression_program import _raw_ast
from .expression_search import LawSearchSpec, search_expressions
from .law_ast import ast_digest, evaluate, infer_dimension, render_latex
from .rule_presentation import response_description

PANEL_VERSION = "principia-measured-response-panels/2"


@dataclass
class ResponsePanel:
    assets: list[Any]
    x: np.ndarray
    y: np.ndarray
    groups: np.ndarray
    inputs: list[str]
    target: str
    title: str
    scope: str
    unit_kind: str
    strategy: str = "group"
    persistence_input: int | None = None
    units: dict[str, str] = field(default_factory=dict)
    locator: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)


def evaluate_panel(
    panel: ResponsePanel,
    *,
    study_id: str,
    artifact_root: Path,
    check_control: Callable[[], None],
    max_candidates: int = 1500,
):
    valid = np.isfinite(panel.y) & np.all(np.isfinite(panel.x), axis=1)
    x, y, groups = panel.x[valid], panel.y[valid], panel.groups[valid]
    identity = canonical_sha256(
        {
            "version": PANEL_VERSION,
            "sources": sorted(a.byte_sha256 for a in panel.assets),
            "inputs": panel.inputs,
            "target": panel.target,
            "sampling": panel.locator,
        }
    )
    receipt = {
        "panel_identity": identity,
        "target": panel.target,
        "asset_ids": [a.asset_id for a in panel.assets],
        "sampling": panel.locator,
        "state": "data_insufficient",
        "reason": "Insufficient complete measurement blocks.",
    }
    if len(y) < 30 or len(np.unique(groups)) < 10 or np.std(y) < 1e-14:
        return [], receipt
    spec = LawSearchSpec(
        target=panel.target,
        inputs=panel.inputs,
        units=panel.units,
        independent_unit_kind=panel.unit_kind,
        strategy=panel.strategy,
        persistence_input=panel.persistence_input,
        max_candidates=max_candidates,
        max_terms=3,
        max_finalists=1,
    )
    result = search_expressions(
        spec,
        x,
        y,
        groups,
        source_digest=identity,
        checkpoint=artifact_root / "response-panels" / f"{identity[:24]}.json",
        check_control=check_control,
    )
    receipt.update(
        state=result["state"],
        reason="",
        evaluated_count=result.get("evaluated_count", 0),
        final_candidates=len(result.get("finalists", [])),
        assignment_digest=result["manifest"]["assignment_digest"],
    )
    outcomes = []
    for finalist in result.get("finalists", []):
        if "ast" not in finalist:
            continue
        normalized_ast = EquationNode.model_validate(finalist["ast"])
        ast = _raw_ast(normalized_ast)
        parameters = {
            **finalist["parameters"],
            **{f"s_{i}": result["normalization"][name] for i, name in enumerate(panel.inputs)},
        }
        with np.errstate(all="ignore"):
            predicted = evaluate(ast, {f"x_{i}": x[:, i] for i in range(x.shape[1])}, parameters)
            reference = evaluate(
                normalized_ast,
                {f"x_{i}": x[:, i] / parameters[f"s_{i}"] for i in range(x.shape[1])},
                finalist["parameters"],
            )
        replay = bool(np.allclose(predicted, reference, equal_nan=False, rtol=1e-10, atol=1e-10))
        signatures = {name: {"target": 1.0} for name in finalist["parameters"]}
        for i in range(x.shape[1]):
            signatures[f"x_{i}"] = signatures[f"s_{i}"] = {f"input_{i}": 1.0}
        dimensional = infer_dimension(ast, signatures) == {"target": 1.0}
        passed = bool(finalist["passed"] and replay and dimensional)
        baseline = finalist["baseline_kind"]
        checks = {
            "strategy": panel.strategy,
            "target": panel.target,
            "independent_unit_kind": panel.unit_kind,
            "frozen_manifest": result["manifest"],
            "selection_lock": result["selected_ordinals"],
            "equation_ast": ast.model_dump(mode="json"),
            "development": {"normalized_rmse": finalist["development_nrmse"]},
            "validation": {"normalized_rmse": finalist["validation_nrmse"]},
            "test": {
                "passed": passed,
                "frozen_predictions": True,
                "normalized_rmse": finalist["test_nrmse"],
                "prediction_digest": finalist["prediction_digest"],
                "worst_unit_nrmse": finalist["worst_unit_nrmse"],
            },
            "baseline_comparison": {
                "executed": True,
                "passed": finalist["test_nrmse"] < 0.98 * finalist["baseline_test_nrmse"]
                and finalist["validation_nrmse"] < 0.98 * finalist["baseline_validation_nrmse"],
                "model": baseline,
                "test_nrmse": finalist["baseline_test_nrmse"],
                "validation_nrmse": finalist["baseline_validation_nrmse"],
            },
            "parameter_stability": {
                "executed": True,
                "passed": finalist["direction_stability"] >= 0.7,
                "fraction": finalist["direction_stability"],
                "method": "development-block coefficient direction stability",
            },
            "negative_control": {
                "executed": True,
                "passed": finalist["negative_control_p"] <= finalist["multiplicity_threshold"],
                "method": finalist["negative_control_method"],
                "p_value": finalist["negative_control_p"],
                "threshold": finalist["multiplicity_threshold"],
            },
            "dimensional_check": {
                "executed": True,
                "passed": dimensional,
                "method": "AST dimensional inference in source-native quantities with matched normalization scales",
                "signatures": signatures,
                "physical_units": panel.units,
            },
            "ast_replay": {
                "executed": True,
                "passed": replay,
                "method": "raw-input AST against frozen normalized predictor",
                "ast_digest": ast_digest(ast),
            },
        }
        outcomes.append(
            _collection_outcome(
                study_id=study_id,
                assets=panel.assets,
                operator=f"measured_{panel.strategy}_response",
                hypothesis_claim=f"A compact response law predicts {panel.target} from measured {', '.join(panel.inputs)}.",
                expected_relationship="A development-fitted equation improves frozen validation and test predictions over the declared baseline.",
                confounders=[
                    "unmeasured acquisition state",
                    "dependence remaining across acquisition blocks",
                ],
                falsifier="The sealed equation loses its improvement in a separated acquisition or under input intervention.",
                sample_definition=f"{len(np.unique(groups))} {panel.unit_kind}; {len(y)} complete measurements",
                independent_unit_count=len(np.unique(groups)),
                parameters={"spec": spec.model_dump(), "panel_identity": identity},
                estimate={
                    "equation_parameters": parameters,
                    "test_nrmse": finalist["test_nrmse"],
                    "baseline_test_nrmse": finalist["baseline_test_nrmse"],
                },
                uncertainty=finalist["uncertainty"],
                sensitivities=[checks["parameter_stability"]],
                diagnostics=[
                    f"{receipt['evaluated_count']} development-fitted expressions; frozen validation selection."
                ],
                negative_evidence=[]
                if passed
                else [
                    "The frozen candidate did not pass every prediction, stability, and falsification check."
                ],
                title=panel.title,
                claim=f"The frozen equation has normalized RMSE {finalist['test_nrmse']:.4g}, versus {finalist['baseline_test_nrmse']:.4g} for the {baseline} baseline.",
                interpretation=response_description({"title": panel.title, "target": panel.target,
                    "equation_ast": ast.model_dump(mode="json"),
                    "equation_variables": [{"symbol": f"x_{i}", "meaning": name} for i, name in enumerate(panel.inputs)],
                    "test": checks["test"], "baseline_comparison": checks["baseline_comparison"]}),
                mechanism="A compact empirical response model. Algebraic terms are inspectable; predictive success alone does not identify a causal mechanism.",
                supported=passed,
                validation_level="internal_holdout",
                robustness=[
                    "development-only fitting",
                    "frozen validation selection",
                    "blocked falsification",
                    "exact equation replay",
                ],
                limits=[
                    "Retrospective internal prediction; prospective replication is pending.",
                    "Validation blocks are not independent subjects or instruments.",
                    *panel.limitations,
                ],
                next_validation="Freeze the equation and test on a new acquisition with the same input and response definitions.",
                units=panel.units,
                expression_latex=render_latex(ast),
                equation_variables=[
                    {"symbol": f"x_{i}", "meaning": name, "unit": panel.units.get(name, "native")}
                    for i, name in enumerate(panel.inputs)
                ],
                split_validation=checks,
                rule_gate={"interpretable_law_family": True},
                transfer_scope=panel.scope,
                locators={a.asset_id: panel.locator for a in panel.assets},
            )
        )
    return outcomes, receipt


def _forecast_panel(asset, times, values, name, unit, locator):
    """One-step prediction with a persistence reference and a boundary embargo."""
    times, values = np.asarray(times, dtype=float), np.asarray(values, dtype=float)
    valid = np.isfinite(times) & np.isfinite(values)
    times, values = times[valid], values[valid]
    order = np.argsort(times, kind="stable")
    times, values = times[order], values[order]
    if len(values) < 300:
        return None
    spacing = float(np.median(np.diff(times)))
    if spacing <= 0:
        return None
    # Input-time blocks, with an embargo longer than the lag history.
    block_size = max(16, int(np.ceil(len(times) / 80)))
    embargo = min(16, max(4, block_size // 4))
    blocks = np.floor((times - times[0]) / (spacing * block_size)).astype(int)
    positions = np.arange(embargo, len(values) - 1)
    usable = (
        (blocks[positions - embargo] == blocks[positions + 1])
        & np.all(
            np.abs(
                times[positions[:, None] + np.arange(-2, 2)]
                - times[positions[:, None] + np.arange(-3, 1)]
                - spacing
            )
            < spacing * 0.1,
            axis=1,
        )
        & (np.abs(times[positions + 1] - times[positions] - spacing) < spacing * 0.1)
    )
    positions = positions[usable]
    # Sampling is bounded by timestamps, never response magnitude.
    if len(positions) > 8000:
        positions = positions[np.linspace(0, len(positions) - 1, 8000, dtype=int)]
    return ResponsePanel(
        [asset],
        np.column_stack([values[positions], values[positions - 1], values[positions - 2]]),
        values[positions + 1],
        blocks[positions],
        [f"{name}(t)", f"{name}(t-1)", f"{name}(t-2)"],
        f"{name}(t+1)",
        f"Short-horizon {name} response",
        f"One-step prediction of {name} at cadence {spacing:.6g} within this acquisition; past observations are available inputs. No multi-step or cross-subject claim.",
        "embargoed time blocks",
        "contiguous_signal",
        0,
        {name: unit},
        {
            **locator,
            "cadence": spacing,
            "embargo_samples": embargo,
            "prediction_task": "one-step, observed-history inputs",
        },
        ["Quality filtering can omit measurements; gaps are excluded from prediction pairs."],
    )


def measured_panels(assets_and_roots, check_control):
    """Select by container schema, units and acquisition coordinates."""
    seen = set()
    for asset, root in assets_and_roots:
        check_control()
        if asset.role != "raw" or asset.status != "analyzable" or asset.byte_sha256 in seen:
            continue
        seen.add(asset.byte_sha256)
        path = _safe_path(root, asset)
        yield from survey_and_series_panels(asset, path)
        yield from coordinate_response_panels(asset, path)
        if asset.format == "fits":
            from astropy.io import fits

            with fits.open(path, memmap=True) as hdus:
                for hdu in hdus:
                    names = set(getattr(getattr(hdu, "columns", None), "names", []) or [])
                    if "TIME" not in names or not ({"PDCSAP_FLUX", "FLUX"} & names):
                        continue
                    data = hdu.data
                    flux_name = "PDCSAP_FLUX" if "PDCSAP_FLUX" in names else "FLUX"
                    good = (
                        np.asarray(data["QUALITY"]) == 0
                        if "QUALITY" in names
                        else np.ones(len(data), dtype=bool)
                    )
                    panel = _forecast_panel(
                        asset,
                        data["TIME"][good],
                        data[flux_name][good],
                        "stellar flux",
                        str(hdu.columns[flux_name].unit or "native flux"),
                        {
                            "hdu": hdu.name,
                            "time": "TIME",
                            "response": flux_name,
                            "mask": "QUALITY = 0"
                            if "QUALITY" in names
                            else "finite observations; no source quality flag supplied",
                        },
                    )
                    if panel:
                        yield panel
                    break
        elif asset.format == "hdf5":
            import h5py
            from scipy.signal import welch

            with h5py.File(path, "r") as handle:
                channels, masks = [], []

                def visit(name, obj, channels=channels, masks=masks):
                    if not isinstance(obj, h5py.Dataset) or obj.ndim != 1:
                        return
                    if (
                        obj.size >= 1000000
                        and np.issubdtype(obj.dtype, np.floating)
                        and str(obj.attrs.get("Ylabel", "")).casefold() == "strain"
                    ):
                        channels.append((name, obj))
                    if "dqmask" in name.casefold() and np.issubdtype(obj.dtype, np.integer):
                        masks.append((name, obj))

                handle.visititems(visit)
                if len(channels) != 1 or len(masks) != 1:
                    continue
                channel_name, channel = channels[0]
                mask_name, mask = masks[0]
                spacing = float(channel.attrs.get("Xspacing", 0))
                ms = float(mask.attrs.get("Xspacing", 0))
                if spacing <= 0 or ms <= 0:
                    continue
                origin = channel.attrs.get("Xstart")
                mask_origin = mask.attrs.get("Xstart")
                if (
                    origin is None
                    or mask_origin is None
                    or abs(float(origin) - float(mask_origin)) > spacing
                ):
                    continue
                ratio = int(round(ms / spacing))
                if ratio < 1 or abs(ratio * spacing - ms) > spacing:
                    continue
                quality = np.asarray(mask[:])
                quality_value = int(np.max(quality))
                x, y, g = [], [], []
                for start in range(0, len(quality) - 64 + 1, 64):
                    if not np.all(quality[start : start + 64] == quality_value):
                        continue
                    v = np.asarray(channel[start * ratio : (start + 64) * ratio], dtype=float)
                    if not np.all(np.isfinite(v)):
                        continue
                    f, p = welch(v, fs=1 / spacing, nperseg=min(16384, len(v)), detrend="linear")
                    selected = (f >= 20) & (f <= 60) & (p > 0)
                    x.extend(np.log(f[selected]).tolist())
                    y.extend(np.log(p[selected]).tolist())
                    g.extend([start] * int(selected.sum()))
                if len(x):
                    yield ResponsePanel(
                        [asset],
                        np.asarray(x)[:, None],
                        np.asarray(y),
                        np.asarray(g),
                        ["log(f / 1 Hz)"],
                        "log(PSD / native reference)",
                        "Low-frequency detector spectrum",
                        "20–60 Hz noise-envelope prediction within quality-clean blocks of this detector acquisition; not an astrophysical source law.",
                        f"{64 * ms:g}-second quality-clean epochs",
                        "contiguous_signal",
                        None,
                        {"frequency": "Hz", "PSD": "strain²/Hz"},
                        {
                            "channel": channel_name,
                            "quality": mask_name,
                            "mask_value": quality_value,
                            "block_mask_samples": 64,
                            "block_seconds": 64 * ms,
                            "aligned_origin": float(origin),
                            "frequency_band_hz": [20, 60],
                        },
                        [
                            "Adjacent epochs may remain correlated; the claimed scope is this acquisition."
                        ],
                    )
        elif asset.format == "nwb":
            import h5py

            with h5py.File(path, "r") as handle:
                containers = []

                def visit(name, obj, containers=containers):
                    if (
                        isinstance(obj, h5py.Group)
                        and "data" in obj
                        and "timestamps" in obj
                        and "RoiResponseSeries" in str(obj.attrs.get("neurodata_type", ""))
                    ):
                        containers.append((name, obj))

                handle.visititems(visit)
                for name, group in containers[:1]:
                    data = group["data"]
                    time = group["timestamps"]
                    if data.shape[0] != len(time) or data.size > 30000000:
                        continue
                    values = np.asarray(data[:], dtype=float).reshape(len(time), -1).mean(axis=1)
                    panel = _forecast_panel(
                        asset,
                        time[:],
                        values,
                        "fluorescence",
                        str(data.attrs.get("unit", "native")),
                        {"series": name, "aggregation": "mean across recorded regions"},
                    )
                    if panel:
                        yield panel
        elif asset.format == "netcdf":
            import xarray as xr

            with xr.open_dataset(path) as ds:
                latitude = next(
                    (
                        n
                        for n in ds.coords
                        if str(ds[n].attrs.get("standard_name", "")) == "latitude"
                        or str(ds[n].attrs.get("units", "")) == "degrees_north"
                    ),
                    None,
                )
                longitude = next(
                    (
                        n
                        for n in ds.coords
                        if str(ds[n].attrs.get("standard_name", "")) == "longitude"
                        or str(ds[n].attrs.get("units", "")) == "degrees_east"
                    ),
                    None,
                )
                if not latitude or not longitude:
                    continue
                for name, v in ds.data_vars.items():
                    if (
                        latitude not in v.dims
                        or longitude not in v.dims
                        or not np.issubdtype(v.dtype, np.number)
                    ):
                        continue
                    if (
                        "temperature"
                        not in (
                            str(v.attrs.get("standard_name", ""))
                            + " "
                            + str(v.attrs.get("long_name", ""))
                        ).casefold()
                    ):
                        continue
                    other = {d: 0 for d in v.dims if d not in {latitude, longitude}}
                    # At most one independent field; block validation is spatial interpolation, not new times.
                    field = v.isel(other).transpose(latitude, longitude)
                    sy = max(1, int(np.ceil(len(ds[latitude]) / 90)))
                    sx = max(1, int(np.ceil(len(ds[longitude]) / 180)))
                    lat, lon = np.meshgrid(
                        ds[latitude].values[::sy], ds[longitude].values[::sx], indexing="ij"
                    )
                    target = field.values[::sy, ::sx]
                    good = np.isfinite(target)
                    b_lat = np.floor((lat + 90) / 15).astype(int)
                    b_lon = np.floor((lon + 180) / 30).astype(int)
                    groups = b_lat * 100 + b_lon
                    yield ResponsePanel(
                        [asset],
                        np.column_stack([lat[good], lon[good]]),
                        target[good],
                        groups[good],
                        ["latitude", "longitude"],
                        str(name),
                        "Spatial temperature response",
                        "Interpolation within the sampled sea-surface field using separated 15° × 30° geographic blocks; no forecast or temporal replication claim.",
                        "geographic blocks",
                        "spatial_block",
                        None,
                        {
                            "latitude": "degrees_north",
                            "longitude": "degrees_east",
                            str(name): str(v.attrs.get("units", "native")),
                        },
                        {
                            "variable": str(name),
                            "slice": other,
                            "sampling_steps": [sy, sx],
                            "block_degrees": [15, 30],
                        },
                        [
                            "Only the first retained time slice is evaluated; coasts and geographic boundaries can limit transfer."
                        ],
                    )
                    break


def execute_response_panels(
    *, study_id, assets_and_roots, artifact_root, check_control, max_candidates=1500
):
    outcomes, receipts = [], []
    # This budget is per study and bounded independently of file count.
    remaining = 12000
    seen = set()
    for asset, root in assets_and_roots:
        if asset.byte_sha256 in seen:
            continue
        seen.add(asset.byte_sha256)
        if remaining <= 0:
            break
        try:
            for panel in measured_panels([(asset, root)], check_control):
                results, receipt = evaluate_panel(
                    panel,
                    study_id=study_id,
                    artifact_root=artifact_root,
                    check_control=check_control,
                    max_candidates=min(remaining, max_candidates),
                )
                outcomes.extend(results)
                receipts.append(receipt)
                remaining -= max(1, int(receipt.get("evaluated_count", 0)))
        except (OSError, ValueError, KeyError, TypeError, csv.Error) as exc:
            receipts.append(
                {
                    "asset_id": asset.asset_id,
                    "state": "data_insufficient",
                    "reason": f"Measurement binding could not be completed ({type(exc).__name__}).",
                }
            )
    return outcomes, receipts


def coordinate_response_panels(asset, path):
    """Spatial response in an explicitly labelled metrology coordinate frame.

    Only coordinates are predictors. Fitted optical parameters, fit errors and
    other target-derived instrument outputs cannot enter the predictor library.
    The blocks and their size depend on coordinates alone, never on thickness.
    """
    import re

    import pandas as pd

    if asset.format not in {"delimited", "csv"}:
        return
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
        header = next(csv.reader(stream), [])
    axes = {}
    for name in header:
        match = re.fullmatch(r"([XY])\s*\((mm|cm|m)\)", name, re.I)
        if match:
            axes[match[1].upper()] = (name, match[2].lower())
    targets = [
        n for n in header if re.fullmatch(r"Thickness(?:\s*#\s*\d+)?\s*\((nm|um|µm|mm)\)", n, re.I)
    ]
    if set(axes) != {"X", "Y"} or not targets:
        return
    columns = [axes["X"][0], axes["Y"][0]]
    frame = pd.read_csv(path, usecols=[*columns, *targets], nrows=50000)
    for name in frame:
        frame[name] = pd.to_numeric(frame[name], errors="coerce")
    frame = frame[np.isfinite(frame[columns]).all(axis=1)]
    if len(frame) < 30 or frame.duplicated(columns).any():
        return
    x = frame[columns].to_numpy(float)
    origin, extent = x.min(axis=0), np.ptp(x, axis=0)
    if np.any(extent <= 0):
        return
    cells = np.minimum(5, np.floor(6 * (x - origin) / extent)).astype(int)
    groups = cells[:, 0] * 6 + cells[:, 1]
    for target in targets[:2]:
        yield ResponsePanel(
            assets=[asset],
            x=x,
            y=frame[target].to_numpy(float),
            groups=groups,
            inputs=columns,
            target=target,
            title="Spatial thin-film thickness response",
            scope="Interpolation across separated spatial regions of this measured specimen; replication on another wafer is pending.",
            unit_kind="spatial metrology regions",
            strategy="spatial_block",
            units={
                **{axes[a][0]: axes[a][1] for a in ("X", "Y")},
                target: target.rsplit("(", 1)[-1].rstrip(")"),
            },
            locator={
                "coordinate_columns": columns,
                "target": target,
                "grid_shape": [6, 6],
                "origin": origin.tolist(),
                "extent": extent.tolist(),
                "selection": "finite coordinates; unique measurement positions",
            },
            limitations=[
                "Thickness is the instrument-reported estimate; the optical inverse model is not independently validated here.",
                "Nearby regions may remain correlated; these blocks are not independent wafers.",
            ],
        )


def survey_and_series_panels(asset, path):
    """Documented instrument fields; no filename or wave-name selection."""
    import csv
    import io
    import zipfile

    import pandas as pd

    if asset.format == "zip":
        with zipfile.ZipFile(path) as archive:
            for member in sorted(archive.infolist(), key=lambda x: x.filename):
                if (
                    not member.filename.casefold().endswith(".csv")
                    or member.file_size > 128 * 1024 * 1024
                ):
                    continue
                with archive.open(member) as raw:
                    header = next(
                        csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace")),
                        [],
                    )
                fields = set(header)
                if {"shedid", "I12", "EF1"}.issubset(fields):
                    with archive.open(member) as raw:
                        frame = pd.read_csv(raw, usecols=["shedid", "I12", "EF1"], low_memory=False)
                    frame = frame[
                        frame["I12"].isin(["Yes", "No"]) & frame["EF1"].isin(["Yes", "No"])
                    ].dropna(subset=["shedid"])
                    if frame["shedid"].duplicated().any():
                        continue
                    order = sorted(
                        range(len(frame)),
                        key=lambda i: canonical_sha256(
                            {"respondent": str(frame.iloc[i]["shedid"])}
                        ),
                    )[:8000]
                    frame = frame.iloc[order]
                    yield ResponsePanel(
                        [asset],
                        (frame["EF1"] == "Yes").to_numpy(float)[:, None],
                        (frame["I12"] == "Yes").to_numpy(float),
                        frame["shedid"].astype(str).to_numpy(),
                        ["rainy-day savings indicator"],
                        "reported bill difficulty indicator",
                        "Financial resilience and reported bill difficulty",
                        "Conditional prediction among complete respondents in this survey release; unweighted sample association, not a population estimate or causal effect.",
                        "survey respondent identifiers",
                        "stratified_group",
                        None,
                        {"response": "binary indicator"},
                        {
                            "archive_member": member.filename,
                            "identifier": "shedid",
                            "inputs": ["EF1"],
                            "target": "I12",
                            "coding": "Yes = 1; No = 0; other responses excluded",
                        },
                        [
                            "Survey weights are not used in this predictive sample calibration.",
                            "Single-predictor association does not adjust for income or other confounding.",
                        ],
                    )
                elif {"SCRAMID", "AIWRK_HOURS", "AI_OCC"}.issubset(fields):
                    tasks = sorted(
                        n
                        for n in fields
                        if n.startswith("AIWRK_") and n not in {"AIWRK_HOURS", "AIWRK_FREQ"}
                    )
                    if len(tasks) < 4:
                        continue
                    with archive.open(member) as raw:
                        frame = pd.read_csv(
                            raw, usecols=["SCRAMID", "AIWRK_HOURS", *tasks], low_memory=False
                        )
                    hours = {1: 0.5, 2: 1.0, 3: 2.0, 4: 3.0, 5: 4.0, 6: 5.0, 7: 0.0}
                    frame["response"] = frame["AIWRK_HOURS"].map(hours)
                    frame["breadth"] = (frame[tasks] == 1).sum(axis=1)
                    frame = frame[(frame["breadth"] > 0)].dropna(subset=["SCRAMID", "response"])
                    if frame["SCRAMID"].duplicated().any():
                        continue
                    order = sorted(
                        range(len(frame)),
                        key=lambda i: canonical_sha256(
                            {"respondent": str(frame.iloc[i]["SCRAMID"])}
                        ),
                    )[:8000]
                    frame = frame.iloc[order]
                    yield ResponsePanel(
                        [asset],
                        frame[["breadth"]].to_numpy(float),
                        frame["response"].to_numpy(float),
                        frame["SCRAMID"].astype(str).to_numpy(),
                        ["number of AI-supported task types"],
                        "reported time-saving score",
                        "AI task breadth and reported time savings",
                        "Predictive association among survey respondents reporting AI task use, with capped hour-equivalent response coding; no objective-productivity or causal claim.",
                        "survey respondent identifiers",
                        "stratified_group",
                        None,
                        {"response": "capped hour-equivalent score"},
                        {
                            "archive_member": member.filename,
                            "identifier": "SCRAMID",
                            "task_fields": tasks,
                            "target": "AIWRK_HOURS",
                            "coding": {str(k): v for k, v in hours.items()},
                        },
                        [
                            "Unweighted respondent prediction; source survey weights and replicate weights are required for population inference.",
                            "Coded ordinal categories are not measured hours.",
                        ],
                    )
    elif asset.format in {"delimited", "tsv", "csv"}:
        with path.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
            header = stream.readline()
            if "\t" not in header:
                return
            names = [n.strip() for n in header.strip().split("\t")]
            if not {"series_id", "year", "period", "value"}.issubset(names):
                return
            reader = csv.DictReader(stream, fieldnames=names, delimiter="\t")
            series = {}
            for row in reader:
                sid = str(row.get("series_id", "")).strip()
                period = str(row.get("period", "")).strip()
                if not period.startswith("M") or len(period) != 3:
                    continue
                try:
                    month = int(period[1:])
                    t = int(row["year"]) * 12 + month - 1
                    v = float(row["value"])
                except (ValueError, TypeError):
                    continue
                if not 1 <= month <= 12:
                    continue
                if sid not in series and len(series) >= 40:
                    continue
                series.setdefault(sid, {})[t] = v
        for sid, rows in sorted(series.items())[:2]:
            times = sorted(rows)
            panel = _forecast_panel(
                asset,
                times,
                [rows[t] for t in times],
                f"monthly series {sid}",
                "native series units",
                {"series_id": sid, "time_fields": ["year", "period"], "response": "value"},
            )
            if panel:
                panel.strategy = "chronological"
                panel.scope = "One-month-ahead prediction for the specified measured economic series, conditional on observed recent values; no multivariate causal or long-run forecast claim."
                yield panel
