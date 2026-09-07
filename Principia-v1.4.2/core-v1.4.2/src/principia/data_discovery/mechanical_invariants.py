"""Measured contact-force geometry, with acquisition-level validation receipts."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from ..domain import EquationNode, canonical_sha256
from .collection_operators import _collection_outcome, _safe_path
from .law_ast import ast_digest, evaluate, infer_dimension, render_latex


def contact_moment_invariant(study_id, assets, root: Path):
    records = []
    seen = set()
    for asset in assets:
        if (
            asset.format not in {"csv", "delimited"}
            or asset.role != "raw"
            or asset.byte_sha256 in seen
        ):
            continue
        seen.add(asset.byte_sha256)
        with _safe_path(root, asset).open(
            encoding="utf-8-sig", errors="replace", newline=""
        ) as stream:
            reader = csv.DictReader(stream)
            columns = set(reader.fieldnames or [])
            prefixes = sorted(
                {
                    name[:-3]
                    for name in columns
                    if name.endswith(":Fz")
                    and name[:-3] + ":My" in columns
                    and name[:-3] + ":COPx" in columns
                }
            )
            if not prefixes:
                continue
            rows = []
            omitted = 0
            for index, row in enumerate(reader):
                if index >= 50000:
                    break
                for prefix in prefixes:
                    try:
                        values = [
                            float(row[prefix + ":Fz"]),
                            float(row[prefix + ":COPx"]),
                            float(row[prefix + ":My"]),
                        ]
                    except (ValueError, TypeError):
                        omitted += 1
                        continue
                    # Source COP = 0 marks a missing/zeroed contact coordinate.
                    # Applicability uses only the measured predictors, never torque.
                    if np.all(np.isfinite(values)) and values[1] != 0:
                        rows.append(values)
                    else:
                        omitted += 1
            if len(rows) >= 100:
                records.append((asset, np.asarray(rows), omitted))
    if len(records) < 3:
        return []
    records.sort(key=lambda r: r[0].byte_sha256)
    split1 = max(1, int(len(records) * 0.6))
    split2 = min(len(records) - 1, max(split1 + 1, int(len(records) * 0.8)))
    roles = [
        "development" if i < split1 else "validation" if i < split2 else "test"
        for i in range(len(records))
    ]
    assignments = [
        {"unit_id": a.byte_sha256, "role": role}
        for (a, _, _), role in zip(records, roles, strict=True)
    ]
    manifest = {
        "assignments": assignments,
        "assignment_digest": canonical_sha256(assignments),
        "frozen_before_fitting": True,
        "policy": "whole acquisition digest split; parameter-free torque identity",
    }
    ast = EquationNode(
        op="negative",
        children=[
            EquationNode(
                op="multiply",
                children=[
                    EquationNode(op="variable", symbol="F_z"),
                    EquationNode(op="variable", symbol="x_c"),
                ],
            )
        ],
    )
    dimensions = {"F_z": {"force": 1.0}, "x_c": {"length": 1.0}}
    dimension_pass = infer_dimension(ast, dimensions) == {"force": 1.0, "length": 1.0}
    dev = [r for r, role in zip(records, roles, strict=True) if role == "development"]
    baseline = float(np.mean([np.mean(v[:, 2]) for _, v, _ in dev]))
    scale = max(float(np.mean([np.std(v[:, 2]) for _, v, _ in dev])), 1e-9)
    metrics = []
    replay = True
    predictions = []
    for (asset, v, omitted), role in zip(records, roles, strict=True):
        pred = evaluate(ast, {"F_z": v[:, 0], "x_c": v[:, 1]})
        replay = replay and bool(np.allclose(pred, -v[:, 0] * v[:, 1], rtol=1e-12, atol=1e-12))
        predictions.append(pred.tolist())
        metrics.append(
            {
                "role": role,
                "unit_id": asset.byte_sha256,
                "n": len(v),
                "omitted": omitted,
                "nrmse": float(np.sqrt(np.mean((v[:, 2] - pred) ** 2)) / scale),
                "baseline_nrmse": float(np.sqrt(np.mean((v[:, 2] - baseline) ** 2)) / scale),
            }
        )
    evaluation = [m for m in metrics if m["role"] in {"validation", "test"}]
    prediction_pass = all(
        m["nrmse"] < 0.02 and m["nrmse"] < 0.98 * m["baseline_nrmse"] for m in evaluation
    )
    rng = np.random.default_rng(7927)
    null = []
    for _ in range(99):
        errors = []
        for (_, v, _), role in zip(records, roles, strict=True):
            if role != "test":
                continue
            control = evaluate(ast, {"F_z": v[:, 0], "x_c": rng.permutation(v[:, 1])})
            errors.append(float(np.sqrt(np.mean((v[:, 2] - control) ** 2)) / scale))
        null.append(float(np.mean(errors)))
    observed = float(np.mean([m["nrmse"] for m in metrics if m["role"] == "test"]))
    p = (1 + sum(v <= observed for v in null)) / 100
    stable = all(m["nrmse"] < 0.02 for m in metrics if m["role"] == "development")
    passed = prediction_pass and p <= 0.05 and stable and replay and dimension_pass
    checks = {
        "strategy": "group",
        "independent_unit_kind": "separate acquisition recordings",
        "frozen_manifest": manifest,
        "selection_lock": "parameter-free contact moment identity selected before source values",
        "equation_ast": ast.model_dump(mode="json"),
        "development": {"units": sum(r == "development" for r in roles)},
        "validation": {"units": sum(r == "validation" for r in roles)},
        "test": {
            "passed": passed,
            "frozen_predictions": True,
            "normalized_rmse": observed,
            "prediction_digest": canonical_sha256(predictions),
        },
        "baseline_comparison": {
            "executed": True,
            "passed": prediction_pass,
            "method": "development-acquisition mean torque",
            "per_acquisition": metrics,
        },
        "parameter_stability": {
            "executed": True,
            "passed": stable,
            "method": "fixed parameter-free equation verified across development recordings",
        },
        "negative_control": {
            "executed": True,
            "passed": p <= 0.05,
            "p_value": p,
            "method": "99 within-acquisition pressure-center pairing permutations",
        },
        "dimensional_check": {
            "executed": True,
            "passed": dimension_pass,
            "signatures": dimensions,
            "method": "moment = force times contact displacement; source-native calibration",
        },
        "ast_replay": {
            "executed": True,
            "passed": replay,
            "method": "AST versus direct moment reconstruction",
            "ast_digest": ast_digest(ast),
        },
    }
    return [
        _collection_outcome(
            study_id=study_id,
            assets=[a for a, _, _ in records],
            operator="contact_moment_kinematic_identity",
            hypothesis_claim="The measured contact moment obeys the signed force–lever-arm identity.",
            expected_relationship="Moment follows the product of normal load and reported center-of-pressure displacement.",
            confounders=[
                "device coordinate convention",
                "pressure-center values may be derived from the moment channel",
                "source contact censoring",
            ],
            falsifier="The frozen moment equation fails on another acquisition or a channel-pairing intervention reproduces it.",
            sample_definition=f"{len(records)} acquisition recordings; nonzero source pressure-center coordinates",
            independent_unit_count=len(records),
            parameters={"fitted_parameters": False, "source_rows_per_recording_limit": 50000},
            estimate={"equation_parameters": {}, "test_nrmse": observed, "acquisitions": metrics},
            uncertainty={
                "pairing_permutation_p": p,
                "test_acquisitions": sum(r == "test" for r in roles),
            },
            sensitivities=[checks["parameter_stability"]],
            diagnostics=["No values were fitted to this identity."],
            negative_evidence=[]
            if passed
            else ["Contact moment reconstruction failed at least one declared check."],
            title="Contact moment from normal load and pressure-center displacement",
            claim=f"The parameter-free signed product predicts contact torque with locked normalized RMSE {observed:.4g} across the retained acquisition split.",
            interpretation="This is an instrument-coordinate consistency law and a usable torque reconstruction, not a new biological mechanism.",
            mechanism="The mechanical moment of a normal force is its signed lever arm times force.",
            supported=passed,
            validation_level="internal_holdout",
            robustness=[
                "whole acquisition split",
                "fixed mechanical equation",
                "pairing intervention",
                "AST replay",
            ],
            limits=[
                "Subjects may repeat across recordings; this does not establish population-level gait physiology.",
                "Pressure-center coordinates may already be computed from these force and moment channels.",
                "Zero pressure-center rows are outside this declared contact scope.",
            ],
            next_validation="Verify units and the sensor coordinate convention against independent metrology.",
            units={"F_z": "native force", "x_c": "native length", "M_y": "native force × length"},
            expression_latex="M_y = " + render_latex(ast),
            equation_variables=[
                {"symbol": "F_z", "meaning": "normal force"},
                {"symbol": "x_c", "meaning": "reported contact pressure-center displacement"},
            ],
            split_validation=checks,
            rule_gate={"interpretable_law_family": True},
            transfer_scope="The recorded force-plate coordinate convention with a nonzero reported contact coordinate; calibration consistency only.",
            significance="Reconstructs the torque channel and detects channel/unit mismatches.",
        )
    ]
