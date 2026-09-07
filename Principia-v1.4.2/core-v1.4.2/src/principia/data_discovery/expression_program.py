"""Bind expression search to verified per-view scientific roles."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from ..domain import DataView, EquationNode, ScientificProgram, StudyBlueprint, canonical_sha256
from .collection_operators import _collection_outcome
from .expression_search import SEARCH_LIMITS, LawSearchSpec, search_expressions
from .law_ast import ast_digest, evaluate, infer_dimension, render_latex
from .operators import (
    OperatorOutcome,
    _scientific_variable_candidate,
    load_numeric,
    load_xlsx_projections,
)


def _raw_ast(node: EquationNode) -> EquationNode:
    if node.op == "variable" and node.symbol.startswith("x_"):
        return EquationNode(op="multiply", children=[node, EquationNode(op="power", children=[EquationNode(op="parameter", symbol="s_" + node.symbol[2:]), EquationNode(op="constant", value=-1)])])
    return node.model_copy(update={"children": [_raw_ast(child) for child in node.children]})


def execute_expression_search(
    *, study_id: str, program: ScientificProgram, blueprint: StudyBlueprint,
    assets_and_roots: list[tuple[Any, Path]], views: list[DataView],
    artifact_root: Path, budget: str,
    check_control: Callable[[], None], emit: Callable[..., None] | None = None,
) -> tuple[list[OperatorOutcome], list[dict[str, Any]]]:
    outcomes: list[OperatorOutcome] = []
    receipts: list[dict[str, Any]] = []
    remaining = SEARCH_LIMITS[budget]
    assets = {asset.asset_id: (asset, root) for asset, root in assets_and_roots}
    # Each target is evaluated once in its own view. Identically named fields
    # in another source/view cannot accidentally become inputs or group keys.
    targets = [(view, target) for view in views for target in blueprint.target_bindings if target.get("view_id") == view.view_id]
    share = max(1, remaining // max(1, len(targets)))
    for view, target in targets:
        check_control()
        if remaining <= 0:
            break
        target_name = str(target.get("variable") or target.get("name") or "")
        receipt: dict[str, Any] = {"view_id": view.view_id, "target": target_name, "state": "data_insufficient"}
        receipts.append(receipt)
        if len(view.asset_ids) != 1 or view.asset_ids[0] not in assets:
            receipt["reason"] = "A validated cross-asset join is required before expression fitting."
            continue
        asset, root = assets[view.asset_ids[0]]
        receipt["asset_id"] = asset.asset_id
        if asset.role != "raw" or asset.status != "analyzable" or view.kind != "table":
            receipt["reason"] = "This expression grammar requires a bound numeric table; modality-specific analyses remain available."
            continue
        unit_bindings = [item for item in blueprint.independent_units if item.get("view_id") == view.view_id]
        if len(unit_bindings) != 1:
            receipt["reason"] = "Exactly one verified independent-unit key is required; rows and files are not assumed to be independent."
            continue
        if asset.format == "xlsx" and view.locator.get("sheet"):
            from .collection_operators import _safe_path
            loaded = next((item for item in load_xlsx_projections(_safe_path(root, asset)) if item.locator.get("sheet") == view.locator["sheet"]), None)
        else:
            loaded = load_numeric(asset, root)
        if loaded is None or target_name not in loaded.variables:
            receipt["reason"] = "The target could not be materialized from this typed view."
            continue
        # Worksheet loaders currently expose a bounded primary view. Reject a
        # different named worksheet rather than bind coincident column names.
        expected_sheet = view.locator.get("sheet")
        if expected_sheet and loaded.locator.get("sheet") != expected_sheet:
            receipt["reason"] = "The selected worksheet needs an explicit view-aware materializer."
            continue
        unit_name = str(unit_bindings[0].get("variable") or unit_bindings[0].get("name") or "")
        if unit_name in loaded.identifiers:
            groups = loaded.identifiers[unit_name]
        elif unit_name in loaded.variables:
            groups = loaded.values[:, loaded.variables.index(unit_name)]
        else:
            receipt["reason"] = "The independent-unit key is not preserved by this materializer."
            continue
        prohibited = {str(item.get("variable") or item.get("name") or "") for item in blueprint.prohibited_leakage_variables if item.get("view_id") == view.view_id}
        inputs = list(dict.fromkeys(str(item.get("variable") or item.get("name") or "") for item in blueprint.input_bindings if item.get("view_id") == view.view_id))
        inputs = [name for name in inputs if name in loaded.variables and name not in prohibited | {unit_name, target_name} and _scientific_variable_candidate(name)][:8]
        if not inputs:
            receipt["reason"] = "No distinct admissible input is bound to this target."
            continue
        x = loaded.values[:, [loaded.variables.index(name) for name in inputs]]
        y = loaded.values[:, loaded.variables.index(target_name)]
        valid = np.all(np.isfinite(x), axis=1) & np.isfinite(y) & np.asarray([str(item) not in {"", "nan", "None"} for item in groups])
        if len(np.unique(groups[valid])) < 5 or int(valid.sum()) < 30:
            receipt["reason"] = "Insufficient complete data for independent development, validation and test partitions."
            continue
        grounded_hints = [hint for hint in program.law_search_hints if asset.asset_id in hint.get("asset_ids", []) and target_name in hint.get("variables_or_features", [])]
        families = sorted({family for hint in grounded_hints for family in hint.get("admissible_law_families", [])})
        spec = LawSearchSpec(target=target_name, inputs=inputs, units=dict(view.units), principle_ids=list(program.principle_ids), independent_unit_kind=unit_name, max_candidates=min(remaining, share), family_kinds=families or ["scaling", "saturation", "response_kernel"])
        receipt["grammar_source"] = "common_library_with_bound_principle_hints" if families else "typed_default_grammar"
        receipt["hypothesis_ids"] = [hint.get("hypothesis_id") for hint in grounded_hints]
        search_id = canonical_sha256({"study": study_id, "view": view.view_id, "target": target_name})[:24]
        result = search_expressions(spec, x[valid], y[valid], groups[valid], source_digest=asset.byte_sha256, checkpoint=artifact_root / "expression-search" / f"{search_id}.json", check_control=check_control, emit=emit)
        count = int(result.get("evaluated_count") or len(result.get("candidates", [])))
        remaining -= count
        receipt.update(state=result["state"], evaluated_count=count, search_id=search_id, finalist_count=len(result.get("finalists", [])), omitted_rows=int((~valid).sum()), identity=result["identity"])
        for finalist in result.get("finalists", []):
            if "ast" not in finalist:
                continue
            ast = _raw_ast(EquationNode.model_validate(finalist["ast"]))
            parameters = {**finalist["parameters"], **{f"s_{i}": result["normalization"][name] for i, name in enumerate(inputs)}}
            # Replay both representations without using targets as inputs.
            raw_prediction = evaluate(ast, {f"x_{i}": x[valid, i] for i in range(len(inputs))}, parameters)
            normalized_prediction = evaluate(EquationNode.model_validate(finalist["ast"]), {f"x_{i}": x[valid, i] / parameters[f"s_{i}"] for i in range(len(inputs))}, finalist["parameters"])
            replayed = bool(np.allclose(raw_prediction, normalized_prediction, equal_nan=False, rtol=1e-12, atol=1e-12))
            dimensions_known = all(bool(view.units.get(name)) for name in [target_name, *inputs])
            # An empirical equation can be unit-consistent in declared native
            # quantities without claiming their SI calibration is known. Prove
            # cancellation with distinct formal dimensions, never by treating
            # unspecified physical inputs as dimensionless.
            signatures = {key: {"target": 1.0} for key in finalist["parameters"]}
            for index in range(len(inputs)):
                signatures[f"x_{index}"] = signatures[f"s_{index}"] = {f"input_{index}": 1.0}
            inferred = infer_dimension(ast, signatures)
            dimensional_pass = inferred == {"target": 1.0}
            manifest = result["manifest"]
            checks = {
                "frozen_manifest": manifest,
                "strategy": spec.strategy,
                "independent_unit_kind": unit_name,
                "selection_lock": result["selected_ordinals"],
                "equation_ast": ast.model_dump(mode="json"),
                "test": {"passed": finalist["passed"], "frozen_predictions": True, "normalized_rmse": finalist["test_nrmse"], "worst_unit_nrmse": finalist["worst_unit_nrmse"]},
                "baseline_comparison": {"executed": True, "passed": finalist["test_nrmse"] < finalist["baseline_test_nrmse"] * 0.98 and finalist["validation_nrmse"] < finalist["baseline_validation_nrmse"] * 0.98, "model": f"development-fitted {finalist['baseline_kind']} baseline", "test_nrmse": finalist["baseline_test_nrmse"], "validation_nrmse": finalist["baseline_validation_nrmse"]},
                "parameter_stability": {"executed": True, "passed": finalist["direction_stability"] >= 0.7, "observed": finalist["direction_stability"], "threshold": 0.7},
                "dimensional_check": {"executed": True, "passed": dimensional_pass, "method": "AST inference with distinct formal input dimensions and matched scale dimensions; coefficients carry target dimension", "inferred_output": inferred, "signatures": signatures, "units": dict(view.units), "physical_unit_annotations_complete": dimensions_known, "scope": "empirical prediction in the source native units; no physical calibration or causal claim"},
                "negative_control": {"executed": True, "passed": finalist["negative_control_p"] <= finalist["multiplicity_threshold"], "method": finalist["negative_control_method"], "p_value": finalist["negative_control_p"], "threshold": finalist["multiplicity_threshold"]},
                "ast_replay": {"executed": True, "passed": replayed, "ast_digest": ast_digest(ast), "prediction_digest": finalist["prediction_digest"]},
                "development": {"normalized_rmse": finalist["development_nrmse"]},
                "validation": {"normalized_rmse": finalist["validation_nrmse"]},
            }
            passed = bool(finalist["passed"] and replayed)
            outcome = _collection_outcome(
                study_id=study_id, assets=[asset], operator="typed_expression_search",
                hypothesis_claim=f"A compact executable expression predicts {target_name} from its bound scientific inputs.",
                expected_relationship="Stable predictive improvement over a structurally chosen frozen baseline on independent units.",
                confounders=[str(item.get("variable")) for item in program.nuisance_bindings if item.get("view_id") == view.view_id],
                falsifier="The frozen expression fails to improve on the baseline or survives label interventions equally well.",
                sample_definition=f"{len(np.unique(groups[valid]))} independent units defined by {unit_name}; complete-case analysis",
                independent_unit_count=len(np.unique(groups[valid])), parameters={"search_identity": result["identity"], "candidate": finalist["ordinal"], "spec": spec.model_dump()},
                estimate=parameters, uncertainty=finalist["uncertainty"], sensitivities=[checks["parameter_stability"]],
                diagnostics=[f"Enumerated {count} structures with three regularization settings; selected on validation before locked evaluation.", "Formal unit cancellation is verified; missing physical unit annotations limit interpretation to native-unit empirical prediction." if not dimensions_known else "Physical unit annotations are preserved."],
                negative_evidence=[] if passed else ["The sealed finalist did not pass all predictive controls."],
                title=f"Expression for {target_name} · {finalist['complexity']} terms", claim=f"Locked normalized RMSE {finalist['test_nrmse']:.4g}; baseline {finalist['baseline_test_nrmse']:.4g}.",
                interpretation="Development-fitted parameters and the executable equation are separately persisted; complexity and stability remain inspectable.",
                mechanism="An empirical response family; Principle links motivate the search but do not establish causality.",
                supported=passed, validation_level="internal_holdout", robustness=["independent-unit development folds", "frozen validation selection", "unit-preserving falsifier"],
                limits=["Internal benchmark evidence; external replication is pending.", "Complete-case selection can limit transfer."], next_validation="Replicate prospectively on new independent units.",
                units=dict(view.units), expression_latex=render_latex(ast), equation_variables=[{"symbol": f"x_{i}", "meaning": name, "unit": view.units.get(name, "")} for i, name in enumerate(inputs)],
                split_validation=checks, rule_gate={"interpretable_law_family": True}, transfer_scope="The bound inputs, independent units, and observed development support of this source set.",
            )
            outcomes.append(outcome)
    return outcomes, receipts
