"""Physically constrained magnitude survival laws with day-separated evaluation.

The exponential survival family is motivated by magnitude-frequency scaling,
not by catalogue filenames. Magnitude scales are never pooled. The source's
declared lower query bound defines conditioning, not catalogue completeness.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np

from ..domain import EquationNode, canonical_sha256
from .collection_operators import _collection_outcome, _safe_path
from .expression_search import freeze_assignments, partition_masks
from .law_ast import ast_digest, evaluate, infer_dimension, render_latex

VERSION = "principia-exponential-survival/1"


def fit_exceedance(days, fractions, offsets, *, check_control=lambda: None):
    """Fit 320 admissible exponents; select on validation, then seal predictions."""
    manifest = freeze_assignments(days, strategy="chronological")
    masks = partition_masks(days, manifest)
    # Every candidate is monotone and bounded before any measurements are fitted.
    rates = np.geomspace(0.05, 10.0, 320)
    curves = np.exp(-rates[:, None] * offsets[None, :])
    dev = fractions[masks["development"]]
    costs = np.mean((dev[:, None, :] - curves[None, :, :]) ** 2, axis=(0, 2))
    frontier = np.argsort(costs, kind="stable")[:5]
    val_cost = np.mean(
        (fractions[masks["validation"], None, :] - curves[frontier][None, :, :]) ** 2, axis=(0, 2)
    )
    selected = int(frontier[np.argmin(val_cost)])
    rate = float(rates[selected])
    prediction = curves[selected]
    basis = np.column_stack([np.ones(len(offsets)), offsets])
    coefficient = np.linalg.lstsq(basis, dev.mean(axis=0), rcond=None)[0]
    baseline = np.clip(basis @ coefficient, 0, 1)
    scale = max(float(np.std(dev)), 1e-12)
    metrics = {
        role: {
            "normalized_rmse": float(np.sqrt(np.mean((fractions[mask] - prediction) ** 2)) / scale),
            "baseline_nrmse": float(np.sqrt(np.mean((fractions[mask] - baseline) ** 2)) / scale),
            "days": int(mask.sum()),
        }
        for role, mask in masks.items()
    }
    folded = []
    for fold in range(5):
        retained = dev[np.arange(len(dev)) % 5 != fold]
        loss = np.mean((retained[:, None, :] - curves[None, :, :]) ** 2, axis=(0, 2))
        folded.append(float(rates[np.argmin(loss)]))
    spread = float(np.std(folded) / max(np.mean(folded), 1e-12))
    rng = np.random.default_rng(73281)
    null_errors = []
    for iteration in range(99):
        if iteration % 10 == 0:
            check_control()
        signs = rng.choice([-1.0, 1.0], size=(len(dev), 1))
        null = baseline + signs * (dev - baseline)
        loss = np.mean((null[:, None, :] - curves[None, :, :]) ** 2, axis=(0, 2))
        fitted = curves[int(np.argmin(loss))]
        null_errors.append(
            float(np.sqrt(np.mean((fractions[masks["test"]] - fitted) ** 2)) / scale)
        )
    p = (1 + sum(error <= metrics["test"]["normalized_rmse"] for error in null_errors)) / 100
    dominates = all(
        metrics[role]["normalized_rmse"] < 0.98 * metrics[role]["baseline_nrmse"]
        for role in ("validation", "test")
    )
    return {
        "manifest": manifest,
        "rate": rate,
        "selected_ordinal": selected,
        "frontier": frontier.tolist(),
        "evaluated_count": len(rates),
        "prediction": prediction.tolist(),
        "prediction_digest": canonical_sha256(prediction.tolist()),
        "metrics": metrics,
        "rate_fold_cv": spread,
        "fold_rates": folded,
        "negative_control_p": p,
        "baseline_dominance": dominates,
        "passed": bool(dominates and spread <= 0.5 and p <= 0.05),
    }


def magnitude_exceedance_outcomes(study_id, assets, root: Path, check_control=lambda: None):
    outcomes, seen = [], set()
    for asset in assets:
        if (
            asset.format not in {"geojson", "json"}
            or asset.role != "raw"
            or asset.byte_sha256 in seen
        ):
            continue
        seen.add(asset.byte_sha256)
        check_control()
        path = _safe_path(root, asset)
        if path.stat().st_size > 64 * 1024 * 1024:
            continue
        try:
            payload = json.loads(path.read_text())
        except (UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
            continue
        metadata = payload.get("metadata")
        if not isinstance(metadata, dict) or not isinstance(payload.get("features"), list):
            continue
        query = parse_qs(urlparse(str(metadata.get("url", ""))).query)
        try:
            minimum = float(query["minmagnitude"][0])
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        if not np.isfinite(minimum) or not -3 <= minimum <= 9:
            continue
        grouped = {}
        seen_events = set()
        for feature in payload.get("features", []):
            if not isinstance(feature, dict):
                continue
            properties = feature.get("properties") or {}
            identity = feature.get("id")
            if not isinstance(properties, dict) or not isinstance(identity, (str, int)):
                continue
            if identity in seen_events or properties.get("type") != "earthquake":
                continue
            seen_events.add(identity)
            try:
                magnitude = float(properties["mag"])
                time = float(properties["time"])
            except (KeyError, TypeError, ValueError):
                continue
            if not np.isfinite(magnitude) or not np.isfinite(time) or magnitude < minimum:
                continue
            kind = str(properties.get("magType") or "")
            if kind:
                grouped.setdefault(kind, {}).setdefault(int(time // 86400000), []).append(magnitude)
        offsets = np.arange(0, 3.01, 0.25)
        eligible = [
            (kind, {day: values for day, values in daily.items() if len(values) >= 3})
            for kind, daily in sorted(grouped.items())
        ]
        eligible = [(kind, daily) for kind, daily in eligible if len(daily) >= 10]
        threshold = 0.05 / max(1, len(eligible))
        for kind, daily in eligible:
            days = np.asarray(sorted(daily))
            fractions = np.asarray(
                [
                    [(np.asarray(daily[day]) >= minimum + offset).mean() for offset in offsets]
                    for day in days
                ]
            )
            fitted = fit_exceedance(days, fractions, offsets, check_control=check_control)
            rate = fitted["rate"]
            ast = EquationNode(
                op="exp",
                children=[
                    EquationNode(
                        op="negative",
                        children=[
                            EquationNode(
                                op="multiply",
                                children=[
                                    EquationNode(op="parameter", symbol="beta"),
                                    EquationNode(
                                        op="add",
                                        children=[
                                            EquationNode(op="variable", symbol="M"),
                                            EquationNode(
                                                op="negative",
                                                children=[
                                                    EquationNode(op="parameter", symbol="M_0")
                                                ],
                                            ),
                                        ],
                                    ),
                                ],
                            )
                        ],
                    )
                ],
            )
            parameters = {"beta": rate, "M_0": minimum}
            replayed = evaluate(ast, {"M": minimum + offsets}, parameters)
            replay = bool(np.allclose(replayed, fitted["prediction"], rtol=1e-12, atol=1e-12))
            dimensional = infer_dimension(ast, {"beta": {}, "M": {}, "M_0": {}}) == {}
            # The derivative is -beta * P, with beta > 0 and M >= M_0.
            physical = rate > 0 and bool(
                np.all((replayed >= 0) & (replayed <= 1)) and np.all(np.diff(replayed) <= 0)
            )
            passed = bool(
                fitted["passed"]
                and fitted["negative_control_p"] <= threshold
                and replay
                and dimensional
                and physical
            )
            metrics = fitted["metrics"]
            checks = {
                "strategy": "chronological",
                "independent_unit_kind": "calendar days within one magnitude scale",
                "frozen_manifest": fitted["manifest"],
                "selection_lock": {
                    "candidate": fitted["selected_ordinal"],
                    "development_frontier": fitted["frontier"],
                },
                "equation_ast": ast.model_dump(mode="json"),
                "development": metrics["development"],
                "validation": metrics["validation"],
                "test": {
                    "passed": passed,
                    "frozen_predictions": True,
                    **metrics["test"],
                    "prediction_digest": fitted["prediction_digest"],
                },
                "baseline_comparison": {
                    "executed": True,
                    "passed": fitted["baseline_dominance"],
                    "model": "development-fitted bounded affine survival curve",
                    "metrics": metrics,
                },
                "parameter_stability": {
                    "executed": True,
                    "passed": fitted["rate_fold_cv"] <= 0.5,
                    "method": "five development-day deletion folds",
                    "coefficient_of_variation": fitted["rate_fold_cv"],
                    "fold_rates": fitted["fold_rates"],
                },
                "negative_control": {
                    "executed": True,
                    "passed": fitted["negative_control_p"] <= threshold,
                    "method": "99 day-level residual sign interventions around the frozen affine baseline; magnitude-scale Bonferroni correction",
                    "p_value": fitted["negative_control_p"],
                    "threshold": threshold,
                },
                "dimensional_check": {
                    "executed": True,
                    "passed": dimensional,
                    "method": "dimensionless magnitude exponent",
                    "signatures": {"beta": {}, "M": {}, "M_0": {}},
                },
                "ast_replay": {
                    "executed": True,
                    "passed": replay,
                    "method": "AST against frozen exponential survival predictions",
                    "ast_digest": ast_digest(ast),
                },
                "physical_shape": {
                    "executed": True,
                    "passed": physical,
                    "method": "P(M_0)=1, 0<P<=1 and dP/dM=-beta*P<0 for all M>=M_0",
                },
            }
            scope = f"Conditional magnitude exceedance fractions on recorded days with at least three {kind} events above the source cutoff {minimum:g}; this catalogue only."
            outcomes.append(
                _collection_outcome(
                    study_id=study_id,
                    assets=[asset],
                    operator="measured_chronological_exceedance",
                    hypothesis_claim="A positive exponential decay describes conditional magnitude exceedance within a single magnitude scale.",
                    expected_relationship="P(Magnitude >= M | Magnitude >= M_0) = exp(-beta (M-M_0)).",
                    confounders=[
                        "catalogue detection completeness",
                        "regional mixture",
                        "aftershock dependence across days",
                    ],
                    falsifier="The locked magnitude-survival curve loses predictive improvement in later days or under day-level residual intervention.",
                    sample_definition=f"{len(days)} calendar days; magnitude scale {kind}; at least three events per included day; thresholds {minimum:g}–{minimum + 3:g}",
                    independent_unit_count=len(days),
                    parameters={
                        "version": VERSION,
                        "magnitude_type": kind,
                        "minimum": minimum,
                        "candidate_rates": 320,
                    },
                    estimate={
                        "equation_parameters": parameters,
                        **parameters,
                        "gutenberg_richter_b": rate / np.log(10),
                        "test_nrmse": metrics["test"]["normalized_rmse"],
                        "baseline_test_nrmse": metrics["test"]["baseline_nrmse"],
                    },
                    uncertainty={
                        "fold_rate_cv": fitted["rate_fold_cv"],
                        "permutation_p": fitted["negative_control_p"],
                        "test_days": metrics["test"]["days"],
                    },
                    sensitivities=[checks["parameter_stability"]],
                    diagnostics=[
                        "320 physically admissible exponent candidates; five development finalists; sealed later-day test."
                    ],
                    negative_evidence=[]
                    if passed
                    else [
                        "The constrained survival law did not pass every prediction, stability and falsification check."
                    ],
                    title=f"Magnitude exceedance decay · {kind} scale",
                    claim=f"A frozen exponential survival law has later-day normalized RMSE {metrics['test']['normalized_rmse']:.4g}, versus {metrics['test']['baseline_nrmse']:.4g} for a bounded affine baseline.",
                    interpretation="The formula predicts the conditional distribution of recorded magnitudes, not the time or location of individual earthquakes.",
                    mechanism="A positive exponential survival curve is the magnitude-frequency scaling family associated with Gutenberg–Richter; its calibration is specific to the retained catalogue scale.",
                    supported=passed,
                    validation_level="internal_holdout",
                    robustness=[
                        "single magnitude scale",
                        "chronological days",
                        "bounded monotone equation",
                        "AST replay",
                        "scale-adjusted falsification",
                    ],
                    limits=[
                        "The source query cutoff is not a verified magnitude of completeness.",
                        "Geographic mixture and aftershock sequences can change the fitted distribution; calendar days may remain dependent.",
                        "Days with fewer than three recorded events of this scale are outside the declared scope.",
                        "The threshold bins are correlated responses, not independent replicates; fitting and controls operate on whole days.",
                    ],
                    next_validation="Test the frozen curve on a new month with matched reporting completeness, region and magnitude scale.",
                    units={"M": "source magnitude scale", "P": "conditional fraction"},
                    expression_latex="P(M) = " + render_latex(ast),
                    equation_variables=[
                        {"symbol": "M", "meaning": f"threshold on the {kind} magnitude scale"},
                        {"symbol": "M_0", "meaning": "source lower query bound"},
                        {
                            "symbol": "beta",
                            "meaning": "positive decay rate fitted on development days",
                        },
                    ],
                    split_validation=checks,
                    rule_gate={"interpretable_law_family": True},
                    transfer_scope=scope,
                    locators={
                        asset.asset_id: {
                            "fields": ["mag", "magType", "time", "type"],
                            "magnitude_type": kind,
                            "minimum": minimum,
                            "threshold_offsets": offsets.tolist(),
                        }
                    },
                )
            )
    return outcomes
