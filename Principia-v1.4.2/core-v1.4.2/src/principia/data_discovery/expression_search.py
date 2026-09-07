"""Bounded, reproducible symbolic search. Providers never score expressions.

Assignments depend only on independent-unit identities. Development fitting,
validation selection and sealed test evaluation are separate operations. The
search ledger contains summaries, never source rows or absolute source paths.
"""
from __future__ import annotations

import itertools
import math
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, Field

from ..domain import EquationNode, canonical_sha256
from .law_ast import ast_digest, canonicalize, evaluate, infer_dimension, render_latex

SEARCH_VERSION = "principia-expression-search/3"
SEARCH_LIMITS = {"fast": 1_000, "balanced": 10_000, "deep": 50_000}
# Shared by every study: four orchestration threads cannot each create an
# unrestricted fitting pool. NumPy fitting uses bounded small matrices.
CPU_SLOTS = threading.BoundedSemaphore(2)


class LawSearchSpec(BaseModel):
    schema_version: str = SEARCH_VERSION
    target: str
    inputs: list[str] = Field(min_length=1, max_length=8)
    units: dict[str, str] = Field(default_factory=dict)
    principle_ids: list[str] = Field(default_factory=list)
    family_kinds: list[str] = Field(default_factory=list)
    independent_unit_kind: str
    persistence_input: int | None = Field(default=None, ge=0, le=7)
    strategy: Literal["group", "chronological", "spatial_block", "contiguous_signal", "stratified_group"] = "group"
    max_candidates: int = Field(default=10_000, ge=1, le=50_000)
    batch_size: int = Field(default=128, ge=1, le=128)
    max_terms: int = Field(default=4, ge=1, le=4)
    max_finalists: int = Field(default=3, ge=1, le=3)
    selection_policy: str = "development-cv-pareto/validation-admissibility-error-complexity-stability/v2"


def freeze_assignments(groups: np.ndarray, *, strategy: str) -> dict[str, Any]:
    values = np.unique(groups)
    if len(values) < 5:
        raise ValueError("At least five independent units are required for development, validation and locked test.")
    identities = [(value, canonical_sha256({"independent_unit": str(value)})) for value in values]
    if strategy not in {"chronological", "contiguous_signal"}:
        identities.sort(key=lambda item: item[1])
    first = max(3, int(len(values) * 0.6))
    second = min(len(values) - 1, max(first + 1, int(len(values) * 0.8)))
    assignments = [
        {"unit_id": identity, "role": "development" if i < first else "validation" if i < second else "test"}
        for i, (_, identity) in enumerate(identities)
    ]
    return {
        "assignments": assignments,
        "assignment_digest": canonical_sha256(assignments),
        "seed_digest": canonical_sha256({"policy": "target-blind-unit-split/v1", "strategy": strategy}),
        "frozen_before_fitting": True,
    }


def partition_masks(groups: np.ndarray, manifest: dict[str, Any]) -> dict[str, np.ndarray]:
    roles = {item["unit_id"]: item["role"] for item in manifest["assignments"]}
    row_roles = np.asarray([roles[canonical_sha256({"independent_unit": str(value)})] for value in groups])
    return {role: row_roles == role for role in ("development", "validation", "test")}


def _node(op: str, *children: EquationNode, **kwargs: Any) -> EquationNode:
    return EquationNode(op=op, children=list(children), **kwargs)


def enumerate_bases(spec: LawSearchSpec) -> Iterator[EquationNode]:
    # Hints extend a common library; an unfamiliar provider family must never
    # silently reduce a 50,000-candidate search to a few straight lines.
    families = {"scaling", "saturation", "response_kernel", *spec.family_kinds}
    variables = [_node("variable", symbol=f"x_{i}") for i in range(len(spec.inputs))]
    for variable in variables:
        yield variable
        if families & {"scaling", "response_kernel"}:
            yield _node("absolute", variable)
            for power in (-3.0, -2.0, -1.0, -0.5, 0.5, 1.5, 2.0, 3.0):
                yield _node("power", variable, _node("constant", value=power))
        # These are dimensionless normalized inputs, with exact normalization
        # persisted separately and frozen on development data.
        operations = []
        if families & {"scaling", "activation", "response_kernel"}:
            operations.extend(["log", "log1p", "exp"])
        if families & {"saturation", "regime_transition"}:
            operations.append("sigmoid")
        for operation in operations:
            yield _node(operation, variable)
        for scale in (0.25, 1.0, 4.0):
            positive = _node("absolute", variable)
            denominator = _node("add", _node("constant", value=scale), positive)
            yield _node("multiply", variable, _node("power", denominator, _node("constant", value=-1.0)))
            yield _node("exp", _node("multiply", _node("constant", value=-scale), positive))
    for left, right in itertools.combinations(variables, 2):
        yield _node("multiply", left, right)
        yield _node("multiply", left, _node("power", right, _node("constant", value=-1.0)))
        yield _node("multiply", right, _node("power", left, _node("constant", value=-1.0)))


def _equation(bases: list[EquationNode], indices: tuple[int, ...]) -> EquationNode:
    return canonicalize(_node("add", _node("parameter", symbol="b"), *[
        _node("multiply", _node("parameter", symbol=f"c_{i}"), bases[index])
        for i, index in enumerate(indices)
    ]))


def _weights(groups: np.ndarray) -> np.ndarray:
    _, inverse, counts = np.unique(groups, return_inverse=True, return_counts=True)
    return 1.0 / counts[inverse]


def _fit(x: np.ndarray, y: np.ndarray, groups: np.ndarray, ridge: float = 0.0) -> np.ndarray:
    weights = np.sqrt(_weights(groups))
    if ridge:
        gram = x.T @ (x * weights[:, None] ** 2)
        return _solve(gram, x.T @ (y * weights ** 2), ridge)
    return np.linalg.lstsq(x * weights[:, None], y * weights, rcond=1e-10)[0]


def _solve(gram: np.ndarray, cross: np.ndarray, ridge: float) -> np.ndarray:
    # Penalize coefficients in their fold-local feature units; leave the
    # intercept free. Equal-unit weights prevent replication changing shrinkage.
    penalty = np.maximum(np.diag(gram) - gram[0] ** 2 / max(gram[0, 0], 1e-12), 0)
    penalty[0] = 0
    return np.linalg.lstsq(gram + ridge * np.diag(penalty), cross, rcond=1e-10)[0]


def _error(y: np.ndarray, prediction: np.ndarray, scale: float, groups: np.ndarray | None = None) -> float:
    return float(np.sqrt(np.average((prediction - y) ** 2, weights=_weights(groups) if groups is not None else None)) / scale)


def _atomic_json(path: Path, payload: Any) -> None:
    import json
    import os
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".search-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(payload, stream, sort_keys=True, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def _persist(path: Path, ledger: dict[str, Any]) -> None:
    candidates = ledger.get("candidates", [])
    batches = path.with_suffix(".batches")
    batches.mkdir(parents=True, exist_ok=True)
    # Rewriting the final partial batch is safe: it is never read without the
    # checkpoint count and the checkpoint is replaced only after all batches.
    for start in range(0, len(candidates), 128):
        target = batches / f"{start:08d}.json"
        if not target.exists() or start + 128 >= len(candidates):
            _atomic_json(target, candidates[start:start + 128])
    _atomic_json(path, {**ledger, "candidates": [], "candidate_count": len(candidates)})


def search_expressions(
    spec: LawSearchSpec,
    x: np.ndarray,
    y: np.ndarray,
    groups: np.ndarray,
    *,
    source_digest: str,
    checkpoint: Path | None = None,
    check_control: Callable[[], None] = lambda: None,
    emit: Callable[[str, str, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Search development, select on validation, then seal up to three tests.

Finalized checkpoints return recorded evidence. An incomplete search replays
only development batches; a selected-but-unsealed checkpoint cannot silently
reopen test data after an interruption.
"""
    import json
    check_control()
    if x.ndim != 2 or x.shape != (len(y), len(spec.inputs)) or len(groups) != len(y):
        raise ValueError("Expression search requires aligned input, target and independent-unit rows.")
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
        raise ValueError("Missing-value handling must be declared before expression search.")
    manifest = freeze_assignments(groups, strategy=spec.strategy)
    masks = partition_masks(groups, manifest)
    identity = canonical_sha256({"spec": spec.model_dump(), "source": source_digest, "split": manifest})
    saved: dict[str, Any] = {}
    if checkpoint and checkpoint.exists():
        saved = json.loads(checkpoint.read_text())
        count = int(saved.get("candidate_count", 0))
        saved["candidates"] = [item for batch in sorted(checkpoint.with_suffix(".batches").glob("*.json")) for item in json.loads(batch.read_text())][:count]
        if len(saved["candidates"]) != count:
            raise ValueError("Expression checkpoint candidate ledger is incomplete")
        if saved.get("identity") != identity:
            raise ValueError("Expression checkpoint does not match the frozen source, split and search configuration.")
        if saved.get("state") == "completed":
            return saved
        if saved.get("state") == "test_reserved":
            raise ValueError("Locked evaluation was interrupted; preserve this run and do not reopen its test partition.")
    ledger: dict[str, Any] = {"identity": identity, "spec": spec.model_dump(), "manifest": manifest, "state": "development", "candidates": saved.get("candidates", [])}
    if checkpoint and not saved:
        _persist(checkpoint, ledger)
    if emit:
        emit("split_frozen", "Frozen independent-unit assignments before expression fitting", {"assignment_digest": manifest["assignment_digest"]})
    while not CPU_SLOTS.acquire(timeout=0.2):
        check_control()
    try:
        return _search(spec, x, y, groups, masks, ledger, checkpoint, check_control, emit)
    finally:
        CPU_SLOTS.release()


def _search(spec: LawSearchSpec, x: np.ndarray, y: np.ndarray, groups: np.ndarray, masks: dict[str, np.ndarray], ledger: dict[str, Any], checkpoint: Path | None, check: Callable[[], None], emit: Callable[..., None] | None) -> dict[str, Any]:
    development = masks["development"]
    # Normalization sees development inputs only. Validation/test targets are
    # first read in their separate selection/evaluation stages below.
    scales = np.maximum(np.median(np.abs(x[development]), axis=0), 1e-12)
    normalized = x / scales
    variables = {f"x_{i}": normalized[:, i] for i in range(x.shape[1])}
    dev_weights = _weights(groups[development])
    dev_mean = np.average(y[development], weights=dev_weights)
    target_scale = max(float(np.sqrt(np.average((y[development] - dev_mean) ** 2, weights=dev_weights))), 1e-12)
    dev_groups = np.unique(groups[development])
    folds = [np.isin(groups, dev_groups[i::3]) & development for i in range(3)]
    bases: list[EquationNode] = []
    columns: list[np.ndarray] = []
    seen: set[str] = set()
    for ast in enumerate_bases(spec):
        check()
        digest = ast_digest(ast)
        if digest in seen:
            continue
        seen.add(digest)
        infer_dimension(ast, {key: {} for key in variables})
        with np.errstate(all="ignore"):
            values = evaluate(ast, variables)
        if np.all(np.isfinite(values[development])) and np.std(values[development]) > 1e-10 and np.max(np.abs(values[development])) < 1e12:
            bases.append(ast)
            columns.append(values)
    if not columns:
        ledger.update(state="completed", finalists=[], evaluated_count=0, reason="No finite, varying scientific basis on development units.")
        if checkpoint:
            _persist(checkpoint, ledger)
        return ledger
    features = np.column_stack([np.ones(len(y)), *columns])
    # Fold-local sufficient statistics make thousands of small-model fits
    # independent of the source row count without leaking validation targets.
    moments = []
    for held in folds:
        train = development & ~held
        if not train.any() or not held.any():
            continue
        train_weights, held_weights = _weights(groups[train]), _weights(groups[held])
        moments.append((features[train].T @ (features[train] * train_weights[:, None]), features[train].T @ (y[train] * train_weights), features[held].T @ (features[held] * held_weights[:, None]), features[held].T @ (y[held] * held_weights), float(y[held] @ (y[held] * held_weights)), float(held_weights.sum())))
    if len(moments) < 3:
        raise ValueError("Three development folds with independent units are required.")
    completed = len(ledger["candidates"])
    candidate_sets = itertools.chain.from_iterable(itertools.combinations(range(len(bases)), size) for size in range(1, spec.max_terms + 1))
    for ordinal, indices in enumerate(itertools.islice(candidate_sets, spec.max_candidates)):
        if ordinal < completed:
            continue
        check()
        selection = [0, *[index + 1 for index in indices]]
        fitted_grids = []
        for ridge in (0.0, 0.001, 0.1):
            losses: list[float] = []
            coefficients = []
            for gram, cross, test_gram, test_cross, yy, count in moments:
                coefficients.append(_solve(gram[np.ix_(selection, selection)], cross[selection], ridge))
                coef = coefficients[-1]
                square_error = max(0.0, float(yy - 2 * coef @ test_cross[selection] + coef @ test_gram[np.ix_(selection, selection)] @ coef))
                losses.append(math.sqrt(square_error / count) / target_scale)
            fitted_grids.append((float(np.mean(losses)), ridge, coefficients))
        score, ridge, coefficients = min(fitted_grids, key=lambda item: (round(item[0], 10), -item[1]))
        signs = np.sign(np.asarray(coefficients)[:, 1:])
        stability = float(np.mean(signs == np.sign(np.median(signs, axis=0))))
        affine = all(bases[index].op == "variable" for index in indices)
        ledger["candidates"].append({"ordinal": ordinal, "basis_indices": list(indices), "development_nrmse": score, "ridge": ridge, "baseline_kind": "constant" if affine else "linear", "complexity": len(indices), "direction_stability": stability, "state": "screened"})
        if (ordinal + 1) % spec.batch_size == 0:
            if checkpoint:
                _persist(checkpoint, ledger)
            if emit:
                emit("candidate_batch", "Completed development expression batch", {"evaluated": ordinal + 1, "ceiling": spec.max_candidates})
    # One best development candidate at each complexity/stability tier forms
    # a bounded frontier. The test cannot influence this selection.
    frontier: dict[tuple[int, bool, str], dict[str, Any]] = {}
    for candidate in ledger["candidates"]:
        key = (candidate["complexity"], candidate["direction_stability"] >= 0.7, candidate["baseline_kind"])
        if key not in frontier or (candidate["development_nrmse"], candidate["ordinal"]) < (frontier[key]["development_nrmse"], frontier[key]["ordinal"]):
            frontier[key] = candidate
    validation = masks["validation"]
    baseline_design = np.column_stack([np.ones(len(y)), normalized])
    baseline_coef = _fit(baseline_design[development], y[development], groups[development])
    baseline_validation = _error(y[validation], baseline_design[validation] @ baseline_coef, target_scale, groups[validation])
    selected = []
    for candidate in frontier.values():
        check()
        indices = tuple(candidate["basis_indices"])
        design = features[:, [0, *[index + 1 for index in indices]]]
        if not np.all(np.isfinite(design[validation])):
            candidate.update(state="rejected", rejection_reason="Expression is outside its finite validation domain.")
            continue
        coef = _fit(design[development], y[development], groups[development], candidate["ridge"])
        candidate["validation_nrmse"] = _error(y[validation], design[validation] @ coef, target_scale, groups[validation])
        candidate["parameters"] = {"b": float(coef[0]), **{f"c_{i}": float(value) for i, value in enumerate(coef[1:])}}
        selected.append(candidate)
    # Validation-ineligible improvements must not displace an admissible
    # simpler law before the locked test. All screened candidates remain in
    # the development ledger; this selection sees no test target.
    constant_validation = _error(y[validation], dev_mean, target_scale, groups[validation])
    persistence_validation = _error(y[validation], x[validation, spec.persistence_input], target_scale, groups[validation]) if spec.persistence_input is not None else None
    admissible = [item for item in selected if item["direction_stability"] >= .7 and item["validation_nrmse"] < .98 * (
        persistence_validation if persistence_validation is not None else constant_validation if item["baseline_kind"] == "constant" else baseline_validation)]
    selected = admissible or selected
    selected.sort(key=lambda item: (item["validation_nrmse"], item["complexity"], -item["direction_stability"], item["ordinal"]))
    pareto = [item for item in selected if not any(other["validation_nrmse"] <= item["validation_nrmse"] and other["complexity"] <= item["complexity"] and other["direction_stability"] >= item["direction_stability"] and (other["validation_nrmse"], other["complexity"], -other["direction_stability"]) != (item["validation_nrmse"], item["complexity"], -item["direction_stability"]) for other in selected)]
    finalists = pareto[:spec.max_finalists]
    ledger.update(state="test_reserved", selected_ordinals=[item["ordinal"] for item in finalists], normalization={name: float(scales[i]) for i, name in enumerate(spec.inputs)}, target_scale=target_scale, basis_asts=[ast.model_dump(mode="json") for ast in bases])
    if checkpoint:
        _persist(checkpoint, ledger)
    # All finalists and controls are frozen before any locked target scoring.
    test = masks["test"]
    baseline_test = _error(y[test], baseline_design[test] @ baseline_coef, target_scale, groups[test])
    evaluated = []
    for candidate in finalists:
        check()
        # A linear law tests the no-input null. Nonlinear additions must still
        # beat a development-fitted linear reference. This choice is structural,
        # fixed before seeing either validation or locked-test scores.
        reference_development = baseline_design[development] @ baseline_coef
        reference_validation = baseline_validation
        reference_test = baseline_test
        if candidate["baseline_kind"] == "constant":
            reference_development = np.full(int(development.sum()), dev_mean)
            reference_validation = _error(y[validation], dev_mean, target_scale, groups[validation])
            reference_test = _error(y[test], dev_mean, target_scale, groups[test])
        if spec.persistence_input is not None:
            # One-step forecasts must beat the last observed response, including
            # for affine models. This reference is fixed in the search identity.
            reference_development = x[development, spec.persistence_input]
            reference_validation = _error(y[validation], x[validation, spec.persistence_input], target_scale, groups[validation])
            reference_test = _error(y[test], x[test, spec.persistence_input], target_scale, groups[test])
            candidate["baseline_kind"] = "persistence"
        ast = _equation(bases, tuple(candidate["basis_indices"]))
        parameters = candidate["parameters"]
        with np.errstate(all="ignore"):
            prediction = evaluate(ast, {key: value[test] for key, value in variables.items()}, parameters)
        if not np.all(np.isfinite(prediction)):
            evaluated.append({**candidate, "passed": False, "reason": "Locked inputs fall outside the finite expression domain."})
            continue
        test_error = _error(y[test], prediction, target_scale, groups[test])
        design = features[:, [0, *[index + 1 for index in candidate["basis_indices"]]]]
        # Deterministic development-label interventions use no locked labels
        # for fitting. All permutations were fixed by policy before testing.
        rng = np.random.default_rng(1729)
        null_errors = []
        for _ in range(99):
            check()
            unit_signs = {unit: rng.choice([-1.0, 1.0]) for unit in np.unique(groups[development])}
            signs = np.asarray([unit_signs[unit] for unit in groups[development]])
            null_target = reference_development + signs * (y[development] - reference_development)
            null_coef = _fit(design[development], null_target, groups[development], candidate["ridge"])
            null_errors.append(_error(y[test], design[test] @ null_coef, target_scale, groups[test]))
        control_p = (1 + sum(error <= test_error for error in null_errors)) / 100
        threshold = 0.05 / max(1, len(finalists))
        unit_errors = [_error(y[test & (groups == unit)], prediction[groups[test] == unit], target_scale) for unit in np.unique(groups[test])]
        evaluated.append({
            **candidate, "ast": ast.model_dump(mode="json"), "ast_digest": ast_digest(ast), "expression_latex": render_latex(ast),
            "test_nrmse": test_error, "baseline_test_nrmse": reference_test, "baseline_validation_nrmse": reference_validation,
            "worst_unit_nrmse": max(unit_errors), "uncertainty": {"unit_nrmse_range": [min(unit_errors), max(unit_errors)], "independent_test_units": len(unit_errors), "permutation_p": control_p},
            "negative_control_method": f"independent-unit residual sign intervention around frozen {candidate['baseline_kind']} baseline", "negative_control_p": control_p, "multiplicity_threshold": threshold,
            "prediction_digest": canonical_sha256(prediction.tolist()),
            "passed": test_error < reference_test * 0.98 and candidate["validation_nrmse"] < reference_validation * 0.98 and candidate["direction_stability"] >= 0.7 and control_p <= threshold,
        })
    ledger.update(state="completed", finalists=evaluated, evaluated_count=len(ledger["candidates"]))
    if checkpoint:
        _persist(checkpoint, ledger)
    return ledger
