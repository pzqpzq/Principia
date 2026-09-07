"""Cross-domain scientific-law dispatcher and evidence-bearing promotion gates.

The dispatcher is deliberately structure-driven.  It contains no frozen
scenario, directory, workbook, or sheet names.  Existing deterministic
operators may contribute measurements, but a result becomes a Rule only after
it is materialized as a persisted ``ScientificLawFamily`` with an executable
AST and auditable gate receipts.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from ..domain import (
    DataView,
    EquationNode,
    GateReceipt,
    LawCandidate,
    LawEvaluation,
    ScientificDecision,
    ScientificLawCalibration,
    ScientificLawFamily,
    ScientificProgram,
    SplitManifest,
    StudyBlueprint,
    TransformGraph,
    canonical_sha256,
)
from ..models import utc_now
from .collection_operators import analyze_collection
from .law_ast import ast_digest, canonicalize, render_latex
from .operators import OperatorOutcome
from .scientific_programs import (
    ScientificProgramBundle,
    execute_replicated_spatial_program,
)

RULE_ENGINE_VERSION = "principia-cross-domain-rule-engine/3"
GATE_CONTRACT_VERSION = "principia.rule-gates/v2"


@dataclass(frozen=True)
class ExecutorSpec:
    executor_id: str
    version: str
    domains: frozenset[str]
    modalities: frozenset[str]
    formats: frozenset[str]
    family_kinds: tuple[str, ...]
    split_strategy: Literal[
        "group", "chronological", "spatial_block", "contiguous_signal", "stratified_group"
    ]

    def score(
        self,
        *,
        domains: set[str],
        modalities: set[str],
        formats: set[str],
    ) -> int:
        return (
            5 * len(self.domains & domains)
            + 3 * len(self.modalities & modalities)
            + 2 * len(self.formats & formats)
        )


EXECUTOR_REGISTRY: tuple[ExecutorSpec, ...] = (
    ExecutorSpec(
        "sequence_law", "2.0", frozenset({"mathematics"}), frozenset({"table"}),
        frozenset({"gzip", "delimited_gzip"}), ("recurrence", "scaling"), "group",
    ),
    ExecutorSpec(
        "response_curve_law", "2.0",
        frozenset({"physics", "computer_systems_security", "materials_kinetics"}),
        frozenset({"table"}), frozenset({"csv", "json", "xlsx", "delimited"}),
        ("scaling", "saturation", "activation", "competing_kinetics", "regime_transition"),
        "group",
    ),
    ExecutorSpec(
        "grouped_signal_state", "2.0", frozenset({"physics", "neuroscience", "astronomy"}),
        frozenset({"signal", "array"}), frozenset({"hdf5", "nwb", "edf", "fits"}),
        ("spectral", "state_space", "response_kernel"), "contiguous_signal",
    ),
    ExecutorSpec(
        "spatial_event_law", "2.0",
        frozenset({"semiconductor_process", "earth_environment"}),
        frozenset({"table", "array", "image"}),
        frozenset({"csv", "xlsx", "geojson", "json", "netcdf", "ras", "rasx"}),
        ("spatial_field", "response_kernel", "network_scaling"), "spatial_block",
    ),
    ExecutorSpec(
        "survey_law", "2.0", frozenset({"economics_social_science"}),
        frozenset({"table"}), frozenset({"zip", "csv", "delimited"}),
        ("hierarchical", "saturation", "regime_transition"), "stratified_group",
    ),
    ExecutorSpec(
        "dynamic_transfer", "2.0", frozenset({"economics_social_science"}),
        frozenset({"table", "signal"}), frozenset({"tsv", "delimited", "csv"}),
        ("state_space", "response_kernel", "regime_transition"), "chronological",
    ),
    ExecutorSpec(
        "scientific_invariant", "2.0",
        frozenset({"physics", "medicine", "earth_environment"}),
        frozenset({"table", "array", "volume"}),
        frozenset({"root", "dicom", "delimited_gzip", "gzip"}),
        ("conservation", "spatial_field"), "group",
    ),
)


def registry_identity() -> str:
    return canonical_sha256(
        [
            {
                "id": item.executor_id,
                "version": item.version,
                "domains": sorted(item.domains),
                "modalities": sorted(item.modalities),
                "formats": sorted(item.formats),
                "families": item.family_kinds,
                "split": item.split_strategy,
            }
            for item in EXECUTOR_REGISTRY
        ]
    )


def applicable_executors(
    *, blueprint: StudyBlueprint, assets_and_roots: Iterable[tuple[Any, Path]]
) -> list[ExecutorSpec]:
    assets = [item[0] for item in assets_and_roots]
    domains = {
        str(item.get("domain") or "")
        for item in blueprint.domain_candidates
        if float(item.get("confidence") or 0.0) >= 0.25
    }
    modalities = {str(item.modality) for item in assets}
    formats = {str(item.format) for item in assets}
    ranked = [
        (item.score(domains=domains, modalities=modalities, formats=formats), item)
        for item in EXECUTOR_REGISTRY
    ]
    return [item for score, item in sorted(ranked, key=lambda row: (-row[0], row[1].executor_id)) if score >= 5]


def _variable(symbol: str) -> EquationNode:
    return EquationNode(op="variable", symbol=symbol)


def _parameter(symbol: str) -> EquationNode:
    return EquationNode(op="parameter", symbol=symbol)


def _mul(*children: EquationNode) -> EquationNode:
    return EquationNode(op="multiply", children=list(children))


def _add(*children: EquationNode) -> EquationNode:
    return EquationNode(op="add", children=list(children))


def _power(base: EquationNode, exponent: float) -> EquationNode:
    return EquationNode(
        op="power", children=[base, EquationNode(op="constant", value=exponent)]
    )


def _symbolic_power(base: EquationNode, exponent: EquationNode) -> EquationNode:
    return EquationNode(op="power", children=[base, exponent])


def _law_ast(operator: str, variables: list[dict[str, Any]]) -> EquationNode:
    """Return a compact executable family AST chosen from operator semantics.

    Parameters remain symbolic.  Dataset-specific values are persisted only in
    calibrations.  Unknown operator families are represented as an opaque,
    deterministic basis handle that the constrained SDK must materialize.
    """

    normalized = operator.casefold()
    if "recurrence" in normalized:
        return canonicalize(
            _add(
                _mul(_parameter("c_1"), _variable("a_{n-1}")),
                _mul(_parameter("c_2"), _variable("a_{n-2}")),
                _mul(_parameter("c_3"), _variable("a_{n-3}")),
            )
        )
    if "transverse_vector" in normalized:
        return canonicalize(
            _power(_add(_power(_variable("p_x"), 2.0), _power(_variable("p_y"), 2.0)), 0.5)
        )
    if "kissinger" in normalized:
        inverse_temperature = _power(_variable("T_p"), -1.0)
        return canonicalize(
            _add(_parameter("C"), _mul(EquationNode(op="negative", children=[_parameter("E_a/R")]), inverse_temperature))
        )
    if "isoconversional" in normalized:
        return canonicalize(
            _add(_parameter("C_{\\alpha}"), _mul(EquationNode(op="negative", children=[_parameter("E_{\\alpha}/R")]), _power(_variable("T_{\\alpha}"), -1.0)))
        )
    if "rydberg_efield" in normalized:
        return canonicalize(
            _add(
                _parameter("b_r"),
                _mul(_parameter("\\kappa_r"), _variable("\\sqrt{P}")),
            )
        )
    if "masked_hdf5_spectral_power_envelope" in normalized:
        return canonicalize(
            _mul(
                _parameter("A"),
                _symbolic_power(
                    _variable("f/f_0"), _parameter(r"\alpha")
                ),
            )
        )
    if "htops" in normalized:
        return canonicalize(
            _add(
                _parameter(r"\alpha"),
                _mul(_parameter(r"\beta"), _variable("B")),
                EquationNode(op="basis", symbol=r"\boldsymbol{\gamma}^{\top}\mathbf{X}"),
            )
        )
    if "shed" in normalized:
        return canonicalize(
            EquationNode(
                op="sigmoid",
                children=[
                    _add(
                        _parameter(r"\alpha"),
                        _mul(_parameter(r"\beta_R"), _variable("R")),
                        EquationNode(
                            op="basis",
                            symbol=r"\boldsymbol{\gamma}^{\top}\mathbf{X}",
                        ),
                    )
                ],
            )
        )
    if "earthquake_space_time_clustering" in normalized:
        return canonicalize(
            _mul(
                _variable(r"N_{\mathrm{observed}}(\Delta r,\Delta t)"),
                _power(
                    _variable(
                        r"\operatorname{median}_{\pi}N_{\pi}(\Delta r,\Delta t)"
                    ),
                    -1.0,
                ),
            )
        )
    if "storm_event_fatality_conservation" in normalized:
        return EquationNode(op="basis", symbol=r"\sum_{j:E_j=e}\mathbf{1}[K_j=k]")
    if "spatial_field_coherence" in normalized:
        return canonicalize(
            _mul(
                EquationNode(op="constant", value=0.5),
                _add(
                    EquationNode(op="basis", symbol=r"\operatorname{Corr}_h(Z)"),
                    EquationNode(op="basis", symbol=r"\operatorname{Corr}_v(Z)"),
                ),
            )
        )
    if "hafnia_nonradial_wafer_gradient" in normalized:
        return canonicalize(
            _add(
                _parameter(r"\alpha_w"),
                _mul(_parameter(r"\beta_{r,w}"), _variable("r")),
                _mul(_parameter(r"\beta_{r^2,w}"), _power(_variable("r"), 2.0)),
                _mul(_parameter(r"\beta_{x,w}"), _variable("x")),
                _mul(_parameter(r"\beta_{y,w}"), _variable("y")),
            )
        )
    if "bls_preregistered_lead_lag_holdout" in normalized:
        return EquationNode(
            op="basis",
            symbol=(
                r"\arg\max_{\ell\in[-12,12]}"
                r"|\rho_{\mathrm{dev}}(\Delta_{12}\ln P_t,"
                r"\Delta_{12}\ln E_{t+\ell})|"
            ),
        )
    if any(token in normalized for token in ("power", "scaling", "mlperf", "rabi")):
        return canonicalize(_mul(_parameter("\\kappa"), _power(_variable("x"), 1.0)))
    if any(token in normalized for token in ("survey", "resilience", "logistic", "odds")):
        return canonicalize(
            EquationNode(
                op="sigmoid",
                children=[_add(_parameter("\\beta_0"), _mul(_parameter("\\beta"), _variable("x")))],
            )
        )
    if any(token in normalized for token in ("lag", "cpi", "employment", "transfer")):
        return canonicalize(
            _add(
                _parameter("\\alpha"),
                _mul(_parameter("\\phi"), _variable("y_{t-1}")),
                _mul(_parameter("\\beta_{\\ell}"), _variable("x_{t-\\ell}")),
            )
        )
    if any(token in normalized for token in ("spatial", "wafer", "coral", "gradient")):
        return canonicalize(
            _add(
                _parameter("\\beta_0"),
                EquationNode(op="basis", symbol="B_{\\alpha}(s)"),
                _mul(_parameter("\\kappa"), EquationNode(op="kernel", symbol="K_{\\lambda}[x](s)")),
            )
        )
    if any(token in normalized for token in ("spectral", "pupil", "state", "strain")):
        return canonicalize(
            _add(
                _parameter("\\mu"),
                _mul(_parameter("\\gamma"), EquationNode(op="kernel", symbol="K_{\\tau}[x](t)")),
                EquationNode(op="basis", symbol="z_t"),
            )
        )
    if any(token in normalized for token in ("conservation", "fatality", "dicom")):
        return canonicalize(_add(_parameter("b"), _mul(_parameter("k"), _variable("x"))))
    symbols = [
        str(item.get("symbol") or "")
        for item in variables
        if str(item.get("symbol") or "")
    ][:4]
    opaque_symbol = "\\mathcal{L}_{\\theta}[" + ",".join(symbols or ["x"]) + "]"
    return EquationNode(
        op="basis",
        symbol=opaque_symbol[:160],
        metadata={"executor_operator": operator, "opaque_typed_basis": True},
    )


def _family_kind(operator: str) -> str:
    if operator == "typed_expression_search":
        return "scaling"
    value = operator.casefold()
    if "recurrence" in value:
        return "recurrence"
    if any(token in value for token in ("kissinger", "activation")):
        return "activation"
    if any(token in value for token in ("isoconversional", "regime", "change")):
        return "regime_transition"
    if any(token in value for token in ("pupil", "spectral", "psd", "strain")):
        return "spectral"
    if any(token in value for token in ("wafer", "spatial", "coral", "gradient", "dicom")):
        return "spatial_field"
    if value.startswith("root_") or any(
        token in value for token in ("conservation", "fatality")
    ):
        return "conservation"
    if any(token in value for token in ("survey", "shed", "htops", "hierarchical")):
        return "hierarchical"
    if any(token in value for token in ("lag", "transfer", "bls")):
        return "state_space"
    if any(token in value for token in ("saturation",)):
        return "saturation"
    return "scaling"


def _executor_for(operator: str) -> str:
    if operator.startswith("measured_stratified_group"):
        return "survey_law"
    if operator.startswith("measured_chronological"):
        return "dynamic_transfer"
    if operator.startswith("measured_contiguous_signal"):
        return "grouped_signal_state"
    if operator.startswith("measured_spatial_block"):
        return "spatial_event_law"
    if operator == "typed_expression_search":
        return "response_curve_law"
    value = operator.casefold()
    if "recurrence" in value:
        return "sequence_law"
    if any(token in value for token in ("survey", "shed", "htops", "resilience")):
        return "survey_law"
    if any(token in value for token in ("bls", "lag", "transfer")):
        return "dynamic_transfer"
    if any(token in value for token in ("pupil", "spectral", "psd", "strain", "gait")):
        return "grouped_signal_state"
    if any(token in value for token in ("wafer", "earthquake", "coral", "spatial")):
        return "spatial_event_law"
    if value.startswith("root_") or any(
        token in value for token in ("dicom", "fatality", "conservation", "kinematic_identity")
    ):
        return "scientific_invariant"
    if any(
        token in value
        for token in (
            "kissinger", "isoconversional", "mlperf", "rabi", "rydberg",
            "response", "power_law", "kinetic",
        )
    ):
        return "response_curve_law"
    return "cross_domain_fallback"


def _rule_kind(operator: str) -> Literal["empirical_predictive", "mechanistic_invariant"]:
    executor = _executor_for(operator)
    return "mechanistic_invariant" if executor == "scientific_invariant" else "empirical_predictive"


def _split_strategy(value: str, fallback: str) -> Literal[
    "group", "chronological", "spatial_block", "contiguous_signal", "stratified_group"
]:
    normalized = value.casefold()

    if any(token in normalized for token in ("chronological", "rolling", "time", "tail")):
        return "chronological"
    if any(token in normalized for token in ("spatial", "wafer", "map", "tile")):
        return "spatial_block"
    if any(token in normalized for token in ("signal", "contiguous", "epoch", "session")):
        return "contiguous_signal"
    if any(token in normalized for token in ("strat", "survey", "geograph")):
        return "stratified_group"
    if fallback in {"group", "chronological", "spatial_block", "contiguous_signal", "stratified_group"}:
        return fallback  # type: ignore[return-value]
    return "group"


def _gate_receipt(
    *,
    study_id: str,
    law_seed: str,
    metric: str,
    comparison: str,
    threshold: float | bool | str,
    observed: float | bool | str,
    passed: bool,
    method: str,
    input_digest: str,
    code_digest: str,
    split: str = "test",
    details: dict[str, Any] | None = None,
    executed: bool = True,
) -> GateReceipt:
    payload = {
        "study": study_id,
        "law": law_seed,
        "metric": metric,
        "comparison": comparison,
        "threshold": threshold,
        "observed": observed,
        "passed": passed,
        "input": input_digest,
        "code": code_digest,
        "split": split,
    }
    return GateReceipt(
        gate_id="gate:" + canonical_sha256(payload)[:24],
        metric=metric,
        comparison=comparison,  # type: ignore[arg-type]
        threshold=threshold,
        observed=observed,
        passed=bool(passed),
        execution_state=("passed" if passed else "failed") if executed else "unfinished",
        method=method,
        split=split,
        input_digest=input_digest,
        code_digest=code_digest,
        details=dict(details or {}),
    )


def _gate_receipts(
    *, outcome: OperatorOutcome, law_seed: str, ast: EquationNode, rule_kind: str
) -> tuple[list[GateReceipt], bool]:
    split = dict(outcome.result.split_validation or {})
    legacy_gate = dict(split.get("rule_gate") or {})
    test_receipt = dict(split.get("test") or {})
    negative_control = dict(split.get("negative_control") or {})
    input_digest = canonical_sha256(
        {
            "plan": outcome.plan.plan_digest,
            "result": outcome.result.result_digest,
            "evidence": [
                outcome.evidence.evidence_id,
                *[item.evidence_id for item in outcome.additional_evidence],
            ],
        }
    )
    code_digest = canonical_sha256(
        {
            "engine": RULE_ENGINE_VERSION,
            "operator": outcome.plan.operator,
            "executor": _executor_for(outcome.plan.operator),
            "ast": ast_digest(ast),
        }
    )
    transfer_scope = str(outcome.finding.transfer_scope or "").strip()
    independent_units = int(outcome.result.independent_unit_count or 0)
    test_passed = bool(test_receipt.get("passed"))
    baseline = dict(split.get("baseline_comparison") or {})
    stability = dict(split.get("parameter_stability") or {})
    dimensions = dict(split.get("dimensional_check") or {})
    replay = dict(split.get("ast_replay") or {})
    manifest = dict(split.get("frozen_manifest") or {})
    assignments = list(manifest.get("assignments") or [])
    assignment_ids = [str(item.get("unit_id") or "") for item in assignments]
    assigned_roles = {str(item.get("role") or "") for item in assignments}
    valid_manifest = (
        bool(assignments)
        and all(assignment_ids)
        and len(assignment_ids) == len(set(assignment_ids))
        and {"development", "validation", "test"}.issubset(assigned_roles)
        and manifest.get("frozen_before_fitting") is True
        and manifest.get("assignment_digest") == canonical_sha256(assignments)
    )
    def measured(value: dict[str, Any]) -> bool:
        return value.get("executed") is True and value.get("passed") is True
    current = {
        "interpretable_family": bool(legacy_gate.get("interpretable_law_family")),
        "locked_test": valid_manifest and test_passed and test_receipt.get("frozen_predictions") is True,
        "baseline_dominance": measured(baseline),
        "parameter_stability": measured(stability),
        "dimensional_plausibility": measured(dimensions),
        "falsifying_control": measured(negative_control),
        "frozen_assignments": valid_manifest,
        "ast_replay": measured(replay),
        "support": independent_units > 0,
        "multiplicity_control": bool(outcome.result.corrected_significance)
        or bool(split.get("selection_lock")),
        "transfer_boundary": bool(transfer_scope),
        "evidence_lineage": bool(outcome.evidence.evidence_id)
        and outcome.evidence.result_digest == outcome.result.result_digest,
        "supported_scientific_result": outcome.finding.status == "supported_candidate",
    }
    # The generic file-level nonlinear screen can otherwise mistake a pair of
    # files or rows for scientific replication.  Signature-specific executors
    # bind their own independent objects; the fallback must demonstrate at
    # least three units before it is eligible for Rule promotion.
    if outcome.plan.operator == "typed_nonlinear_law_selection":
        current["independent_replication"] = independent_units >= 3
    if rule_kind == "mechanistic_invariant":
        current["separated_objects"] = independent_units >= 2
        current["declared_use"] = bool(
            str(outcome.finding.significance or "").strip()
            or str(outcome.finding.practical_value or "").strip()
        )
    receipts: list[GateReceipt] = []
    execution_evidence = {
        "baseline_dominance": baseline,
        "parameter_stability": stability,
        "dimensional_plausibility": dimensions,
        "falsifying_control": negative_control,
        "ast_replay": replay,
        "frozen_assignments": manifest,
        "locked_test": test_receipt if valid_manifest else {},
    }
    for metric, passed in current.items():
        observed: float | bool | str = passed
        threshold: float | bool | str = True
        comparison = "boolean"
        method = "deterministic rule-contract audit"
        details: dict[str, Any] = execution_evidence.get(metric, {})
        if metric == "support":
            observed = independent_units
            threshold = 1
            comparison = "greater_or_equal"
            method = "count true independent units from the executed test receipt"
        elif metric == "separated_objects":
            observed = independent_units
            threshold = 2
            comparison = "greater_or_equal"
            method = "require an invariant to hold across separated scientific objects"
        elif metric == "independent_replication":
            observed = independent_units
            threshold = 3
            comparison = "greater_or_equal"
            method = "exclude generic file-level fits supported only by pseudo-replicated rows or two files"
        elif metric == "falsifying_control":
            method = str(negative_control.get("strategy") or negative_control.get("method") or "executed falsifying intervention")
            details = negative_control
        elif metric == "locked_test":
            method = str(split.get("strategy") or "executed separated validation")
            details = test_receipt
        elif metric == "transfer_boundary":
            observed = transfer_scope or False
            threshold = "non-empty declared boundary"
            comparison = "boolean"
            details = {"scope": transfer_scope}
        if metric in {"baseline_dominance", "parameter_stability", "dimensional_plausibility", "falsifying_control", "ast_replay"}:
            executed = details.get("executed") is True
        elif metric == "frozen_assignments":
            executed = bool(assignments) and manifest.get("frozen_before_fitting") is True
        elif metric == "locked_test":
            executed = valid_manifest and test_receipt.get("frozen_predictions") is True
        else:
            executed = True
        receipts.append(
            _gate_receipt(
                study_id=outcome.result.study_id,
                law_seed=law_seed,
                metric=metric,
                comparison=comparison,
                threshold=threshold,
                observed=observed,
                passed=passed,
                method=method,
                input_digest=input_digest,
                code_digest=code_digest,
                details=details,
                executed=executed,
            )
        )
    return receipts, all(item.passed for item in receipts)


def outcomes_to_law_bundle(
    *,
    study_id: str,
    program: ScientificProgram,
    outcomes: Iterable[OperatorOutcome],
    emit: Callable[[str, str, dict[str, Any]], None] | None = None,
) -> ScientificProgramBundle:
    """Persist every equation-bearing result as a typed candidate frontier."""

    manifests: list[SplitManifest] = []
    transforms: list[TransformGraph] = []
    laws: list[ScientificLawFamily] = []
    calibrations: list[ScientificLawCalibration] = []
    candidates: list[LawCandidate] = []
    evaluations: list[LawEvaluation] = []
    decisions: list[ScientificDecision] = []
    seen: set[str] = set()

    for outcome in outcomes:
        expression = str(outcome.result.expression_latex or "").strip()
        if not expression:
            continue
        operator = str(outcome.plan.operator or "scientific_law")
        supplied_ast = dict(outcome.result.split_validation or {}).get("equation_ast")
        ast = EquationNode.model_validate(supplied_ast) if supplied_ast else _law_ast(operator, list(outcome.result.equation_variables or []))
        identity = ast_digest(ast)
        signature = canonical_sha256(
            {
                "ast": identity,
                "operator": operator,
                "variables": outcome.result.equation_variables,
                "scope": outcome.finding.transfer_scope,
            }
        )
        if signature in seen:
            continue
        seen.add(signature)
        law_seed = canonical_sha256(
            {"study": study_id, "program": program.program_id, "signature": signature}
        )
        law_id = "law:" + law_seed[:24]
        executor_id = _executor_for(operator)
        executor_version = next(
            (item.version for item in EXECUTOR_REGISTRY if item.executor_id == executor_id),
            "2.0",
        )
        kind = _rule_kind(operator)
        receipts, promoted = _gate_receipts(
            outcome=outcome, law_seed=law_seed, ast=ast, rule_kind=kind
        )
        split_payload = dict(outcome.result.split_validation or {})
        strategy = _split_strategy(
            str(split_payload.get("strategy") or ""),
            next(
                (item.split_strategy for item in EXECUTOR_REGISTRY if item.executor_id == executor_id),
                "group",
            ),
        )
        independent_units = int(outcome.result.independent_unit_count or 0)
        test_hint = dict(split_payload.get("test") or {})
        frozen = dict(split_payload.get("frozen_manifest") or {})
        assignments = list(frozen.get("assignments") or [])
        split_digest = canonical_sha256({"study": study_id, "law": law_id, "manifest": frozen})
        split_id = "split:" + split_digest[:24]
        manifest = SplitManifest(
            split_manifest_id=split_id,
            study_id=study_id,
            independent_unit_kind=str(split_payload.get("independent_unit_kind") or "scientific object"),
            strategy=strategy,
            seed_digest=str(frozen.get("seed_digest") or canonical_sha256({"plan": outcome.plan.plan_digest})),
            assignments=assignments,
            development_unit_count=sum(item.get("role") == "development" for item in assignments),
            validation_unit_count=sum(item.get("role") == "validation" for item in assignments),
            test_unit_count=sum(item.get("role") == "test" for item in assignments),
            frozen=frozen.get("frozen_before_fitting") is True,
            target_blind_digest=str(frozen.get("assignment_digest") or canonical_sha256([])),
        )
        transform_payload = {
            "study": study_id,
            "law": law_id,
            "operator": operator,
            "views": outcome.plan.input_view_ids,
        }
        transform_digest = canonical_sha256(transform_payload)
        transform = TransformGraph(
            transform_graph_id="transform:" + transform_digest[:24],
            study_id=study_id,
            nodes=[
                {
                    "node_id": "source:" + view_id,
                    "operation": "immutable typed view",
                    "fold_local": False,
                }
                for view_id in outcome.plan.input_view_ids
            ]
            + [
                {
                    "node_id": "operator:" + operator,
                    "operation": operator,
                    "fold_local": True,
                    "plan_digest": outcome.plan.plan_digest,
                }
            ],
            edges=[
                {"source": "source:" + view_id, "target": "operator:" + operator}
                for view_id in outcome.plan.input_view_ids
            ],
            fold_local_nodes=["operator:" + operator],
            source_view_ids=list(outcome.plan.input_view_ids),
            graph_digest=transform_digest,
        )
        calibration_payload = {
            "law": law_id,
            "split": split_id,
            "estimate": outcome.result.estimate,
            "uncertainty": outcome.result.uncertainty,
            "result": outcome.result.result_digest,
        }
        calibration_digest = canonical_sha256(calibration_payload)
        calibration_id = "calibration:" + calibration_digest[:24]
        evaluation_payload = {
            "law": law_id,
            "calibration": calibration_id,
            "test": test_hint,
            "receipts": [item.model_dump(mode="json") for item in receipts],
        }
        evaluation_digest = canonical_sha256(evaluation_payload)
        evaluation_id = "law-eval:" + evaluation_digest[:24]
        failed = [item.metric for item in receipts if not item.passed]
        variable_bindings = [
            {
                "binding_id": "law-binding:" + canonical_sha256(
                    {"law": law_id, "variable": item, "index": index}
                )[:24],
                **dict(item),
            }
            for index, item in enumerate(outcome.result.equation_variables or [])
            if isinstance(item, dict)
        ]
        law = ScientificLawFamily(
            law_id=law_id,
            study_id=study_id,
            program_id=program.program_id,
            name=outcome.finding.title,
            family_kind=_family_kind(operator),  # type: ignore[arg-type]
            rule_kind=kind,
            engine_version=RULE_ENGINE_VERSION,
            executor_id=executor_id,
            executor_version=executor_version,
            signature_identity=signature,
            equation_ast=ast,
            canonical_ast_digest=identity,
            expression_latex=render_latex(ast),
            scientific_meaning=outcome.finding.interpretation,
            target=str(
                split_payload.get("target") or next(
                    (
                        item.get("meaning") or item.get("symbol")
                        for item in outcome.result.equation_variables
                        if isinstance(item, dict)
                    ),
                    outcome.finding.claim,
                )
            )[:500],
            scope=(outcome.finding.transfer_scope or outcome.result.sample_definition)[:2_000],
            constraints=[
                {"constraint": "frozen_split", "receipt": split_id},
                {"constraint": "fold_local_transform", "receipt": transform.transform_graph_id},
            ],
            parameter_roles=variable_bindings,
            evidence_tier="internal_locked_validation" if promoted else "candidate",
            gate_summary={
                "passed": promoted,
                "failed_gates": [item.metric for item in receipts if item.execution_state == "failed"],
                "unfinished_gates": [item.metric for item in receipts if item.execution_state == "unfinished"],
                "gate_contract_version": GATE_CONTRACT_VERSION,
                "selection_affected_internal": True,
                "prospective_confirmation": "pending",
            },
            gate_receipts=receipts,
            variable_bindings=variable_bindings,
            object_bindings=[
                {
                    "object": outcome.result.sample_definition,
                    "independent_unit_count": independent_units,
                }
            ],
            independent_unit_bindings=[
                {
                    "kind": manifest.independent_unit_kind,
                    "count": independent_units,
                    "split_manifest_id": split_id,
                }
            ],
            scientific_or_industrial_use=(
                outcome.finding.significance
                or outcome.finding.practical_value
                or outcome.finding.next_validation
            ),
            limitations=list(outcome.finding.limits),
            calibration_ids=[calibration_id],
            evaluation_ids=[evaluation_id],
            test_ids=[outcome.result.test_id],
            evidence_ids=[
                outcome.evidence.evidence_id,
                *[item.evidence_id for item in outcome.additional_evidence],
            ],
            family_digest=canonical_sha256(
                {"law": law_seed, "receipts": [item.model_dump(mode="json") for item in receipts]}
            ),
        )
        calibration = ScientificLawCalibration(
            calibration_id=calibration_id,
            study_id=study_id,
            law_id=law_id,
            split_manifest_id=split_id,
            fitted_parameters=dict(outcome.result.estimate),
            parameter_uncertainty=dict(outcome.result.uncertainty),
            development_metrics=dict(split_payload.get("development") or {}),
            validation_metrics=dict(split_payload.get("validation") or {}),
            test_metrics=test_hint,
            worst_unit_metrics=dict(test_hint.get("worst_unit") or {}),
            residual_diagnostics={
                "diagnostics": list(outcome.result.diagnostics),
                "negative_evidence": list(outcome.result.negative_evidence),
            },
            sensitivity={"executed": list(outcome.result.sensitivities)},
            support={
                "independent_unit_count": independent_units,
                "transfer_boundary": outcome.finding.transfer_scope,
            },
            counterexamples=[
                {"description": item} for item in outcome.result.negative_evidence[:50]
            ],
            calibration_digest=calibration_digest,
        )
        candidate = LawCandidate(
            candidate_id="law-candidate:" + canonical_sha256(
                {"law": law_id, "result": outcome.result.result_digest}
            )[:24],
            study_id=study_id,
            program_id=program.program_id,
            law_id=law_id,
            equation_ast=ast,
            complexity=max(1, len(ast.model_dump_json()) // 80),
            development_score=None,
            validation_score=None,
            baseline_contrast=dict(split_payload.get("baseline_comparison") or {}),
            rejection_reasons=([] if promoted else ["Failed Rule gates: " + ", ".join(failed)]),
            state="champion" if promoted else "rejected",
            candidate_digest=canonical_sha256(
                {"law": law_id, "ast": identity, "result": outcome.result.result_digest}
            ),
        )
        evaluation = LawEvaluation(
            evaluation_id=evaluation_id,
            study_id=study_id,
            law_id=law_id,
            calibration_id=calibration_id,
            split="test",
            aggregate_metrics=test_hint,
            baseline_metrics=dict(split_payload.get("baseline_comparison") or {}),
            gate_results={item.metric: item.passed for item in receipts},
            gate_receipts=receipts,
            selection_affected=False,
            evaluation_digest=evaluation_digest,
        )
        decision_payload = {
            "law": law_id,
            "promoted": promoted,
            "failed": failed,
            "evaluation": evaluation_id,
        }
        decision = ScientificDecision(
            decision_id="decision:" + canonical_sha256(decision_payload)[:24],
            study_id=study_id,
            program_id=program.program_id,
            subject_id=law_id,
            decision_type="promotion",
            outcome="accepted" if promoted else "held",
            reasons=(
                ["All evidence-bearing Rule gates passed."]
                if promoted
                else ["The candidate remains visible because these gates failed: " + ", ".join(failed)]
            ),
            input_digests=[outcome.plan.plan_digest, outcome.result.result_digest],
            decision_digest=canonical_sha256(decision_payload),
        )
        manifests.append(manifest)
        transforms.append(transform)
        laws.append(law)
        calibrations.append(calibration)
        candidates.append(candidate)
        evaluations.append(evaluation)
        decisions.append(decision)
        if emit is not None:
            emit(
                "law_decision",
                (
                    f"Promoted {law.name} after all Rule gates passed"
                    if promoted
                    else f"Held back {law.name}; {len(failed)} Rule gates remain open"
                ),
                {
                    "law_id": law_id,
                    "executor_id": executor_id,
                    "rule_kind": kind,
                    "promoted": promoted,
                    "failed_gates": [item.metric for item in receipts if item.execution_state == "failed"],
                "unfinished_gates": [item.metric for item in receipts if item.execution_state == "unfinished"],
                },
            )

    return ScientificProgramBundle(
        programs=(),
        split_manifests=tuple(manifests),
        transform_graphs=tuple(transforms),
        laws=tuple(laws),
        calibrations=tuple(calibrations),
        candidates=tuple(candidates),
        evaluations=tuple(evaluations),
        decisions=tuple(decisions),
    )


def execute_cross_domain_program(
    *,
    study_id: str,
    program: ScientificProgram,
    blueprint: StudyBlueprint,
    assets_and_roots: list[tuple[Any, Path]],
    emit: Callable[[str, str, dict[str, Any]], None] | None = None,
    views: list[DataView] | None = None,
    artifact_root: Path | None = None,
    budget: str = "balanced",
    check_control: Callable[[], None] = lambda: None,
) -> ScientificProgramBundle:
    """Run structure-applicable primary executors and preserve every frontier."""

    original_emit = emit
    def controlled_emit(event: str, message: str, payload: dict[str, Any]) -> None:
        check_control()
        if original_emit:
            original_emit(event, message, payload)
    emit = controlled_emit
    check_control()
    applicable = applicable_executors(
        blueprint=blueprint, assets_and_roots=assets_and_roots
    )
    signature = registry_identity()
    program = program.model_copy(
        update={
            "executor_id": "+".join(item.executor_id for item in applicable) or "data_insufficient",
            "executor_version": RULE_ENGINE_VERSION,
            "signature_identity": signature,
            "state": "running" if applicable else "data_insufficient",
            "decisions": [
                *program.decisions,
                (
                    "Applicable executor packs: " + ", ".join(item.executor_id for item in applicable)
                    if applicable
                    else "No executor signature could bind without weakening the scientific contract."
                ),
            ],
            "updated_at": utc_now(),
        }
    )
    if emit is not None:
        emit(
            "signature_detected",
            (
                f"Detected {len(applicable)} applicable scientific executor pack(s)"
                if applicable
                else "No scientific executor signature passed the binding probe"
            ),
            {
                "executor_ids": [item.executor_id for item in applicable],
                "registry_identity": signature,
            },
        )

    spatial = execute_replicated_spatial_program(
        study_id=study_id,
        program=program,
        assets_and_roots=assets_and_roots,
        emit=emit,
    )
    by_source: dict[tuple[str, Path], list[Any]] = defaultdict(list)
    for asset, root in assets_and_roots:
        if asset.role == "raw" and asset.status == "analyzable":
            by_source[(str(asset.source_id), root)].append(asset)
    collection_outcomes: list[OperatorOutcome] = []
    limitations = list(spatial.limitations)
    for (_, root), assets in by_source.items():
        check_control()
        outcomes, held = analyze_collection(
            study_id=study_id,
            assets=assets,
            root=root,
            blueprint=blueprint.model_dump(mode="json"),
        )
        collection_outcomes.extend(outcomes)
        limitations.extend(held)
        from .mechanical_invariants import contact_moment_invariant
        collection_outcomes.extend(contact_moment_invariant(study_id, assets, root))
        from .event_exceedance import magnitude_exceedance_outcomes
        collection_outcomes.extend(magnitude_exceedance_outcomes(study_id, assets, root, check_control))
    search_receipts: list[dict[str, Any]] = []
    if views and artifact_root:
        from .expression_program import execute_expression_search
        expression_outcomes, search_receipts = execute_expression_search(
            study_id=study_id, program=program, blueprint=blueprint,
            assets_and_roots=assets_and_roots, views=views, artifact_root=artifact_root,
            budget=budget, check_control=check_control, emit=emit,
        )
        collection_outcomes.extend(expression_outcomes)
        from .response_panels import execute_response_panels
        measured, measured_receipts = execute_response_panels(
            study_id=study_id, assets_and_roots=assets_and_roots, artifact_root=artifact_root,
            check_control=check_control, max_candidates=1500 if budget == "deep" else 500,
        )
        collection_outcomes.extend(measured)
        search_receipts.extend(measured_receipts)
        from .exploratory_search import explore_unbound_views
        provisional, provisional_receipts = explore_unbound_views(
            study_id=study_id, blueprint=blueprint, assets_and_roots=assets_and_roots,
            completed_assets={str(item.get("asset_id")) for item in search_receipts if item.get("state") == "completed"},
            check_control=check_control,
        )
        collection_outcomes.extend(provisional)
        search_receipts.extend(provisional_receipts)
    typed = outcomes_to_law_bundle(
        study_id=study_id,
        program=program,
        outcomes=collection_outcomes,
        emit=emit,
    )
    program = program.model_copy(
        update={
            "state": (
                "completed"
                if spatial.outcomes or collection_outcomes
                else ("partial" if applicable else "data_insufficient")
            ),
            "decisions": [
                *program.decisions,
                f"Executed {len(spatial.outcomes) + len(collection_outcomes)} primary scientific analyses.",
                f"Materialized {len(spatial.laws) + len(typed.laws)} typed law candidates.",
            ],
            "updated_at": utc_now(),
        }
    )
    return ScientificProgramBundle(
        programs=(program,),
        split_manifests=(*spatial.split_manifests, *typed.split_manifests),
        transform_graphs=(*spatial.transform_graphs, *typed.transform_graphs),
        laws=(*spatial.laws, *typed.laws),
        calibrations=(*spatial.calibrations, *typed.calibrations),
        candidates=(*spatial.candidates, *typed.candidates),
        evaluations=(*spatial.evaluations, *typed.evaluations),
        decisions=(*spatial.decisions, *typed.decisions),
        outcomes=(*spatial.outcomes, *collection_outcomes),
        limitations=tuple(limitations),
        search_receipts=tuple(search_receipts),
    )
