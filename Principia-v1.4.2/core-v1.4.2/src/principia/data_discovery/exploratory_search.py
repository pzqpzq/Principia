"""Explicitly provisional fits when scientific roles cannot yet be certified.

These fits never supply a selector, split, or success flag to validated search.
They expose executable hypotheses and the missing work instead of silently
abandoning a numeric table at the first unresolved metadata field.
"""
from __future__ import annotations

import csv
import itertools
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from ..domain import EquationNode, StudyBlueprint
from .collection_operators import _collection_outcome, _safe_path
from .expression_search import LawSearchSpec, _equation, enumerate_bases
from .law_ast import evaluate, render_latex
from .operators import (
    OperatorOutcome,
    _scientific_variable_candidate,
    load_numeric,
    load_xlsx_projections,
)


def fit_provisional_expression(x: np.ndarray, y: np.ndarray, inputs: list[str], target: str) -> dict[str, Any] | None:
    """Bounded, descriptive BIC screen; no row is claimed as a replicate."""
    valid = np.isfinite(y) & np.all(np.isfinite(x), axis=1)
    x, y = x[valid], y[valid]
    if len(y) < 12 or np.max(np.abs(y)) > 1e100 or np.max(np.abs(x)) > 1e100 or np.std(y) <= 1e-12:
        return None
    source_rows = len(y)
    if len(y) > 2048:
        order = np.lexsort(x.T[::-1])
        selected = order[np.linspace(0, len(order) - 1, 2048, dtype=int)]
        x, y = x[selected], y[selected]
    scales = np.maximum(np.median(np.abs(x), axis=0), 1e-12)
    values = {f"x_{i}": x[:, i] / scales[i] for i in range(len(inputs))}
    bases, columns = [], []
    spec = LawSearchSpec(target=target, inputs=inputs, independent_unit_kind="unverified")
    for basis in enumerate_bases(spec):
        with np.errstate(all="ignore"):
            column = evaluate(basis, values)
        if np.all(np.isfinite(column)) and np.max(np.abs(column)) < 1e12 and np.std(column) > 1e-10:
            bases.append(basis)
            columns.append(column)
    if not columns:
        return None
    features = np.column_stack([np.ones(len(y)), *columns])
    gram, cross = features.T @ features, features.T @ y
    yy = float(y @ y)
    count = 0
    best: tuple[float, tuple[int, ...], np.ndarray] | None = None

    def score(indices: tuple[int, ...]) -> float:
        nonlocal count, best
        selection = [0, *[i + 1 for i in indices]]
        local = gram[np.ix_(selection, selection)]
        coef = np.linalg.lstsq(local, cross[selection], rcond=1e-10)[0]
        rss = max(0.0, yy - 2 * coef @ cross[selection] + coef @ local @ coef)
        bic = len(y) * np.log(max(rss / len(y), np.var(y) * 1e-12)) + (len(indices) + 1) * np.log(len(y))
        count += 1
        if best is None or (bic, len(indices), indices) < (best[0], len(best[1]), best[1]):
            best = float(bic), indices, coef
        return float(bic)

    singles = sorted((score((i,)), i) for i in range(len(bases)))[:10]
    # The shortlist and all fits use the same explicitly descriptive sample.
    pool = sorted(i for _, i in singles)
    for size in (2, 3):
        for indices in itertools.combinations(pool, size):
            score(indices)
    if best is None:
        return None
    _, indices, _ = best
    design = features[:, [0, *[i + 1 for i in indices]]]
    coef = np.linalg.lstsq(design, y, rcond=1e-10)[0]
    ast = _equation(bases, indices)
    parameters = {"b": float(coef[0]), **{f"c_{i}": float(c) for i, c in enumerate(coef[1:])}}
    prediction = evaluate(ast, values, parameters)
    rmse = float(np.sqrt(np.mean((prediction - y) ** 2)))
    return {"ast": ast.model_dump(mode="json"), "parameters": parameters,
            "normalization": dict(zip(inputs, scales.tolist(), strict=True)),
            "sample_count": len(y), "source_complete_rows": source_rows, "omitted_rows": int((~valid).sum()),
            "in_sample_rmse": rmse, "in_sample_nrmse": rmse / float(np.std(y)),
            "evaluated_count": count, "term_count": len(indices), "selection": "descriptive BIC; all rows selection-affected"}


def explore_unbound_views(*, study_id: str, blueprint: StudyBlueprint,
                         assets_and_roots: list[tuple[Any, Path]], completed_assets: set[str],
                         check_control: Callable[[], None]) -> tuple[list[OperatorOutcome], list[dict[str, Any]]]:
    outcomes, receipts = [], []
    # A separate bounded exploration budget cannot consume the certified search
    # budget. No images, identifiers, or arbitrary pixel indices become targets.
    eligible = [(a, r) for a, r in assets_and_roots if a.role == "raw" and a.status == "analyzable"
                and a.asset_id not in completed_assets and a.modality not in {"image", "volume"}]
    unique_assets = {a.byte_sha256: (a, r) for a, r in eligible}
    for asset, root in sorted(unique_assets.values(), key=lambda item: item[0].byte_sha256)[:24]:
        check_control()
        receipt: dict[str, Any] = {"asset_id": asset.asset_id, "state": "binding_required", "evaluated_count": 0}
        receipts.append(receipt)
        try:
            projections = load_xlsx_projections(_safe_path(root, asset)) if asset.format == "xlsx" else [load_numeric(asset, root)]
        except (ValueError, OSError, KeyError, csv.Error) as exc:
            receipt["reason"] = f"Numeric materialization needs repair ({type(exc).__name__})."
            continue
        for loaded in projections[:2]:
            check_control()
            if loaded is None:
                continue
            names = list(dict.fromkeys(n for n in loaded.variables if _scientific_variable_candidate(n)
                         and re.sub(r"[\W_]+", "", n.casefold()) not in {"no", "rowno", "pointno", "serialno", "编号", "序号"}))
            prohibited = {str(t.get("variable") or t.get("name") or "") for t in blueprint.prohibited_leakage_variables}
            names = [name for name in names if name not in prohibited]
            # Preserve explicit roles when labels agree, but never manufacture
            # replication or promote automatic response proposals to evidence.
            targets = [str(t.get("variable") or t.get("name") or "") for t in blueprint.target_bindings]
            bound_targets = [n for n in names if n in targets]
            coordinates = {str(binding.get("variable") or binding.get("name") or "") for binding in blueprint.coordinate_bindings}
            # An unlabelled coordinate table needs a response binding. Do not
            # fill the candidate list with fits of point number or X versus Y.
            automatic_targets = [n for n in names if n not in coordinates and not re.match(
                r"^(?:x|y|z|r|radius|time|date|timestamp)(?:$|[\s_\[(])", n.casefold().strip())]
            targets = bound_targets or automatic_targets[-2:]
            for target in targets[:2]:
                inputs = [n for n in names if n != target][:4]
                if not inputs:
                    continue
                result = fit_provisional_expression(loaded.values[:, [loaded.variables.index(n) for n in inputs]], loaded.values[:, loaded.variables.index(target)], inputs, target)
                if result is None:
                    continue
                from .expression_program import _raw_ast
                ast = _raw_ast(EquationNode.model_validate(result["ast"]))
                parameters = {**result["parameters"], **{f"s_{i}": result["normalization"][n] for i, n in enumerate(inputs)}}
                reason = "Confirm response and predictor roles, physical units, leakage exclusions, and independent experimental units before freezing new validation data."
                receipt.update(state="provisional_fit", reason=reason)
                receipt["evaluated_count"] += result["evaluated_count"]
                outcome = _collection_outcome(
                    study_id=study_id, assets=[asset], operator="typed_expression_search",
                    hypothesis_claim=f"A provisional numeric expression relates {target} to candidate inputs.",
                    expected_relationship="A compact descriptive response; scientific meaning and generalization are unverified.",
                    confounders=["Unconfirmed scientific roles and dependence between records"],
                    falsifier="The expression fails on newly frozen independent observations after binding review.",
                    sample_definition=loaded.sample_definition, independent_unit_count=0,
                    parameters={"mode": "provisional_in_sample", "target": target, "inputs": inputs, "locator": loaded.locator},
                    estimate=parameters, uncertainty={"in_sample_residual_rmse": result["in_sample_rmse"], "independent_units_verified": 0, "predictive_interval": "not estimated"},
                    sensitivities=[], diagnostics=[reason, result["selection"], f"{result['evaluated_count']} expressions fitted; {result['omitted_rows']} incomplete rows omitted."],
                    negative_evidence=["No independent validation or scientific interpretation is established by this fit."],
                    title=f"Provisional expression for {target}",
                    claim=f"In-sample normalized RMSE {result['in_sample_nrmse']:.4g} across {result['sample_count']} records; no held-out score is claimed.",
                    interpretation="An executable proposal for binding review, not a validated Rule.", mechanism="Unverified empirical response hypothesis.",
                    supported=False, validation_level="exploratory", robustness=[], limits=[reason], next_validation=reason,
                    units={}, expression_latex=render_latex(ast),
                    equation_variables=[{"symbol": f"x_{i}", "meaning": n, "unit": "unconfirmed native unit"} for i, n in enumerate(inputs)],
                    split_validation={"equation_ast": ast.model_dump(mode="json"), "development": {"in_sample_nrmse": result["in_sample_nrmse"]}, "test": {"passed": False}, "exploration_only": True},
                    rule_gate={"interpretable_law_family": False}, transfer_scope="Not established; source records are selection-affected.",
                )
                outcomes.append(outcome)
        if receipt["state"] == "binding_required":
            receipt["reason"] = "No admissible multivariate numeric projection; a modality-specific response definition is required."
    return outcomes, receipts
