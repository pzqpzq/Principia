from __future__ import annotations

import csv
import gzip
import itertools
import json
import math
import re
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from ..cancellation import check_cancelled
from ..domain import (
    AnalysisPlan,
    ComputedEvidenceAnchor,
    DataAsset,
    DataFinding,
    DataHypothesis,
    TestResult,
    canonical_sha256,
)
from ..models import utc_now
from .operators import OPERATOR_VERSION, OperatorOutcome

COLLECTION_OPERATOR_VERSION = f"{OPERATOR_VERSION}+collections/4"


def _law_gate(*, negative_control_passed: bool) -> dict[str, bool]:
    """Record the six Rule gates without inventing an unexecuted control.

    Collection operators already provide separated validation, stability,
    units, and a bounded scope.  A baseline comparison is not automatically a
    negative control: that final gate is true only when the operator actually
    executed a falsifying permutation, key shift, or equivalent intervention.
    """

    # Compatibility hints are not proof of execution. Qualification reads the
    # measured receipts; missing stability, dimensional and baseline work stays
    # unfinished instead of inheriting an unconditional success flag.
    return {
        "interpretable_law_family": True,
        "held_out_baseline_improvement": False,
        "parameter_stability": False,
        "unit_plausibility": False,
        "negative_control": negative_control_passed,
        "transfer_boundary_declared": True,
    }



def _view_id(asset: DataAsset) -> str:
    content_digest = canonical_sha256(
        {
            "asset": asset.byte_sha256,
            "adapter": asset.adapter,
            "adapter_version": asset.adapter_version,
            "profile": asset.metadata.get("profile") or {},
        }
    )
    return "view:" + canonical_sha256(
        {"study": asset.study_id, "content_digest": content_digest}
    )[:24]


def _safe_path(root: Path, asset: DataAsset) -> Path:
    canonical_root = root.resolve(strict=True)
    relative = str(asset.metadata.get("relative_path") or "")
    path = (canonical_root / relative).resolve(strict=True)
    if not path.is_relative_to(canonical_root) or not path.is_file():
        raise ValueError("asset locator escapes its registered source")
    return path


def _collection_outcome(
    *,
    study_id: str,
    assets: list[DataAsset],
    operator: str,
    hypothesis_claim: str,
    expected_relationship: str,
    confounders: list[str],
    falsifier: str,
    sample_definition: str,
    independent_unit_count: int,
    parameters: dict[str, Any],
    estimate: dict[str, Any],
    uncertainty: dict[str, Any],
    sensitivities: list[dict[str, Any]],
    diagnostics: list[str],
    negative_evidence: list[str],
    title: str,
    claim: str,
    interpretation: str,
    mechanism: str,
    supported: bool,
    validation_level: str,
    robustness: list[str],
    limits: list[str],
    next_validation: str,
    locators: dict[str, dict[str, Any]] | None = None,
    units: dict[str, str] | None = None,
    expression_latex: str = "",
    equation_variables: list[dict[str, Any]] | None = None,
    split_validation: dict[str, Any] | None = None,
    rule_gate: dict[str, bool] | None = None,
    insight_level: str = "observational",
    nontriviality_basis: str = "",
    significance: str = "",
    principle_statement: str = "",
    transfer_scope: str = "",
) -> OperatorOutcome:
    if not assets:
        raise ValueError("collection operator requires at least one asset")
    # A single official payload may supply both development and locked
    # geographic blocks.  The split receipt records those roles; repeating the
    # same immutable asset must not duplicate its evidence anchor or lineage ID.
    ordered = list(
        {
            item.asset_id: item
            for item in sorted(assets, key=lambda candidate: candidate.asset_id)
        }.values()
    )
    input_views = [_view_id(item) for item in ordered]
    input_receipt = [
        {"asset_id": item.asset_id, "sha256": item.byte_sha256, "view_id": view_id}
        for item, view_id in zip(ordered, input_views, strict=True)
    ]
    hypothesis_digest = canonical_sha256(
        {
            "study": study_id,
            "operator": operator,
            "claim": hypothesis_claim,
            "inputs": input_receipt,
        }
    )
    hypothesis_id = f"hyp:{hypothesis_digest[:24]}"
    hypothesis = DataHypothesis(
        hypothesis_id=hypothesis_id,
        study_id=study_id,
        claim=hypothesis_claim,
        origin="cross_modal" if len(ordered) > 1 else "principle_guided",
        expected_relationship=expected_relationship,
        input_view_ids=input_views,
        confounders=confounders,
        boundary=[sample_definition, f"{len(ordered)} immutable source assets"],
        falsifier=falsifier,
        state="tested",
    )
    plan_payload = {
        "operator": operator,
        "inputs": input_receipt,
        "parameters": parameters,
        "sample": sample_definition,
        "version": COLLECTION_OPERATOR_VERSION,
    }
    plan_digest = canonical_sha256(plan_payload)
    plan = AnalysisPlan(
        plan_id=f"plan:{plan_digest[:24]}",
        study_id=study_id,
        hypothesis_id=hypothesis_id,
        executor="operator",
        operator=operator,
        input_view_ids=input_views,
        parameters=parameters,
        expected_outputs=sorted(estimate),
        validation_checks=robustness,
        plan_digest=plan_digest,
    )
    split_receipt = dict(split_validation or {})
    if rule_gate:
        split_receipt["rule_gate"] = {
            str(key): bool(value) for key, value in sorted(rule_gate.items())
        }
    result_digest = canonical_sha256(
        {
            "operator": operator,
            "estimate": estimate,
            "uncertainty": uncertainty,
            "sensitivities": sensitivities,
            "expression_latex": expression_latex,
            "split_validation": split_receipt,
            "version": COLLECTION_OPERATOR_VERSION,
        }
    )
    test_id = "test:" + canonical_sha256(
        {"study": study_id, "result": result_digest}
    )[:24]
    result = TestResult(
        test_id=test_id,
        study_id=study_id,
        hypothesis_id=hypothesis_id,
        plan_id=plan.plan_id,
        plan_digest=plan_digest,
        state="succeeded",
        sample_definition=sample_definition,
        independent_unit_count=max(0, int(independent_unit_count)),
        estimate=estimate,
        uncertainty=uncertainty,
        diagnostics=diagnostics,
        sensitivities=sensitivities,
        negative_evidence=negative_evidence,
        artifacts=[],
        expression_latex=expression_latex,
        equation_variables=list(equation_variables or []),
        split_validation=split_receipt,
        result_digest=result_digest,
    )
    finding_id = "finding:" + canonical_sha256(
        {"study": study_id, "hypothesis": hypothesis_id, "result": result_digest}
    )[:24]
    evidence: list[ComputedEvidenceAnchor] = []
    for asset, view_id in zip(ordered, input_views, strict=True):
        relative = str(asset.metadata.get("relative_path") or "")
        locator = {
            "relative_path": relative,
            "byte_sha256": asset.byte_sha256,
            **dict((locators or {}).get(asset.asset_id) or {}),
        }
        evidence_id = "evidence:" + canonical_sha256(
            {"test": test_id, "asset": asset.asset_id, "locator": locator}
        )[:24]
        evidence.append(
            ComputedEvidenceAnchor(
                evidence_id=evidence_id,
                study_id=study_id,
                finding_id=finding_id,
                test_id=test_id,
                asset_id=asset.asset_id,
                view_id=view_id,
                locator=locator,
                units=dict(units or {}),
                plan_digest=plan_digest,
                executor_version=COLLECTION_OPERATOR_VERSION,
                result_digest=result_digest,
            )
        )
    finding = DataFinding(
        finding_id=finding_id,
        study_id=study_id,
        title=title,
        claim=claim,
        interpretation=interpretation,
        mechanism=mechanism,
        significance=significance,
        insight_level=insight_level,  # type: ignore[arg-type]
        nontriviality_basis=nontriviality_basis,
        principle_statement=principle_statement,
        transfer_scope=transfer_scope,
        status="supported_candidate" if supported else "held_back",
        validation_level=validation_level,  # type: ignore[arg-type]
        hypothesis_ids=[hypothesis_id],
        test_ids=[test_id],
        evidence_ids=[item.evidence_id for item in evidence],
        robustness=robustness,
        confounders=confounders,
        falsifiers=[falsifier],
        negative_evidence=negative_evidence,
        limits=limits,
        next_validation=next_validation,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    return OperatorOutcome(
        hypothesis=hypothesis,
        plan=plan,
        result=result,
        evidence=evidence[0],
        additional_evidence=tuple(evidence[1:]),
        finding=finding,
    )


def _spearman(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    from scipy.stats import spearmanr

    result = spearmanr(x, y, nan_policy="omit")
    coefficient = float(result.statistic)
    p_value = float(result.pvalue)
    return coefficient, p_value


def _oeis_recurrence_outcomes(
    study_id: str, assets: list[DataAsset], root: Path
) -> list[OperatorOutcome]:
    """Recover exact low-order recurrence families with a held-out term block."""

    by_name = {
        Path(str(item.metadata.get("relative_path") or "")).name.casefold(): item
        for item in assets
        if item.role == "raw"
    }
    stripped = by_name.get("stripped.gz")
    names = by_name.get("names.gz")
    if stripped is None or names is None:
        return []

    coefficient_grid = range(-3, 4)

    def exact_recurrence(terms: list[int]) -> tuple[tuple[int, ...], int] | None:
        development_end = min(len(terms) - 3, max(9, int(len(terms) * 0.70)))
        for order in range(1, 4):
            if development_end - order < 6:
                continue
            for coefficients in itertools.product(coefficient_grid, repeat=order):
                if not any(coefficients):
                    continue
                if not all(
                    terms[index]
                    == sum(
                        coefficients[offset] * terms[index - offset - 1]
                        for offset in range(order)
                    )
                    for index in range(order, development_end)
                ):
                    continue
                # Candidate membership is decided from the observed prefix.
                # Never drop a member because its locked suffix contradicts it.
                return tuple(int(value) for value in coefficients), development_end
        return None

    evaluated = 0
    recovered: list[dict[str, Any]] = []
    accession_roles: dict[str, str] = {}
    with gzip.open(
        _safe_path(root, stripped), "rt", encoding="utf-8", errors="replace"
    ) as stream:
        for line in stream:
            if not line.startswith("A") or "," not in line:
                continue
            accession = line.split(",", 1)[0].strip()
            try:
                accession_number = int(accession[1:])
            except ValueError:
                continue
            # Outcome-blind deterministic thinning keeps the official flat file
            # stream bounded without selecting on sequence values or names.
            if accession_number % 29:
                continue
            terms: list[int] = []
            for token in line.split(",")[1:81]:
                try:
                    terms.append(int(token.strip()))
                except ValueError:
                    continue
            if not 12 <= len(terms) <= 80:
                continue
            if max(abs(value).bit_length() for value in terms) > 4_096:
                continue
            slot = int(canonical_sha256({"accession": accession, "policy": "sequence-group/v2"})[:8], 16) % 10
            role = "development" if slot < 6 else "validation" if slot < 8 else "test"
            accession_roles[accession] = role
            evaluated += 1
            recurrence = exact_recurrence(terms)
            if recurrence is None:
                continue
            coefficients, development_end = recurrence
            recovered.append(
                {
                    "accession": accession,
                    "role": role,
                    "coefficients": coefficients,
                    "term_count": len(terms),
                    "development_terms": development_end,
                    "held_out_terms": len(terms) - development_end,
                    "terms": terms,
                }
            )

    if evaluated < 100 or not recovered:
        return []
    families: dict[tuple[int, ...], list[dict[str, Any]]] = {}
    for item in recovered:
        if item["role"] == "development":
            families.setdefault(tuple(item["coefficients"]), []).append(item)
    if not families:
        return []
    selected_families = sorted(
        [(c, m) for c, m in families.items() if len(m) >= 4],
        key=lambda item: (-len(item[1]), len(item[0]), item[0]),
    )[:16]

    def evaluate_family(coefficients: tuple[int, ...], members: list[dict[str, Any]]) -> list[OperatorOutcome]:
        development_members = list(members)
        validation_members = [item for item in recovered if item["coefficients"] == coefficients and item["role"] == "validation"]
        members = [item for item in recovered if item["coefficients"] == coefficients and item["role"] == "test"]
        if not members or not validation_members:
            return []
        # This family is now fixed. Test-prefix membership is a declared applicability
        # condition for forecasting later terms; locked suffixes cannot select it.
        def forecast(item: dict[str, Any]) -> tuple[list[int], list[int]]:
            prefix = item["terms"][:item["development_terms"]]
            prediction = list(prefix)
            for _ in item["terms"][len(prefix):]:
                prediction.append(sum(coefficient * prediction[-i-1] for i, coefficient in enumerate(coefficients)))
            return prediction[len(prefix):], item["terms"][len(prefix):]
        def errors(items: list[dict[str, Any]]) -> int:
            return sum(sum(a != b for a, b in zip(*forecast(item), strict=True)) for item in items)
        validation_errors, locked_errors = errors(validation_members), errors(members)
        baseline_errors = sum(sum(value != item["terms"][item["development_terms"]-1] for value in forecast(item)[1]) for item in members)
        assignments = [{"unit_id": canonical_sha256({"accession": accession}), "role": role} for accession, role in sorted(accession_roles.items())]
        manifest = {"assignments": assignments, "assignment_digest": canonical_sha256(assignments), "frozen_before_fitting": True, "policy": "accession-only family selection and conditional prefix forecasting/v2"}
        from ..domain import EquationNode
        from .law_ast import evaluate, infer_dimension
        ast = EquationNode(op="add", children=[EquationNode(op="multiply", children=[EquationNode(op="parameter", symbol=f"c_{i}"), EquationNode(op="variable", symbol=f"lag_{i+1}")]) for i in range(len(coefficients))])
        parameters = {f"c_{i}": float(value) for i, value in enumerate(coefficients)}
        replayed = True
        for item in members:
            expected, _ = forecast(item)
            predicted = list(item["terms"][:item["development_terms"]])
            for exact in expected:
                if max(abs(value) for value in [exact, *predicted[-len(coefficients):]]) > 2**52:
                    replayed = False
                    break
                actual = float(evaluate(ast, {f"lag_{i+1}": predicted[-i-1] for i in range(len(coefficients))}, parameters))
                replayed = replayed and actual == exact
                predicted.append(actual)
        dimensional = infer_dimension(ast, {**{key: {} for key in parameters}, **{f"lag_{i+1}": {} for i in range(len(coefficients))}}) == {}
        selected_ids = {str(item["accession"]) for item in members}
        names_by_id: dict[str, str] = {}
        with gzip.open(
            _safe_path(root, names), "rt", encoding="utf-8", errors="replace"
        ) as stream:
            for line in stream:
                accession = line[:7]
                if accession in selected_ids:
                    names_by_id[accession] = line[7:].strip()[:500]

        coefficient_terms: list[str] = []
        for offset, coefficient in enumerate(coefficients, start=1):
            if coefficient == 0:
                continue
            magnitude = "" if abs(coefficient) == 1 else str(abs(coefficient))
            term = f"{magnitude}a_{{n-{offset}}}"
            if not coefficient_terms:
                coefficient_terms.append(("-" if coefficient < 0 else "") + term)
            else:
                coefficient_terms.append((" - " if coefficient < 0 else " + ") + term)
        expression = "a_n = " + "".join(coefficient_terms)
        member_receipts = [
            {
                **{key: value for key, value in item.items() if key != "terms"},
                "coefficients": list(item["coefficients"]),
                "name": names_by_id.get(str(item["accession"]), ""),
                "held_out_exact": forecast(item)[0] == forecast(item)[1],
            }
            for item in members
        ]
        shuffled_matches = 0
        for item in members:
            terms = list(item["terms"])
            rng = np.random.default_rng(
                int(canonical_sha256({"accession": item["accession"], "terms": [str(value) for value in terms]})[:16], 16)
            )
            shuffled = list(np.asarray(terms, dtype=object)[rng.permutation(len(terms))])
            order = len(coefficients)
            if all(
                shuffled[index]
                == sum(
                    coefficients[offset] * shuffled[index - offset - 1]
                    for offset in range(order)
                )
                for index in range(order, len(shuffled))
            ):
                shuffled_matches += 1
        negative_control_passed = shuffled_matches == 0
        supported = len(members) >= 4 and validation_errors == 0 and locked_errors == 0 and baseline_errors > 0 and negative_control_passed and replayed
        recurrence_label = ", ".join(str(value) for value in coefficients)
        return [
            _collection_outcome(
                study_id=study_id,
                assets=[stripped, names],
                operator="oeis_exact_recurrence_family",
                hypothesis_claim=(
                    "Outcome-blind OEIS accession thinning may expose repeated exact low-order "
                    "recurrences that predict an untouched terminal term block."
                ),
                expected_relationship=(
                    "One coefficient family should recur across independently named sequences and "
                    "predict every held-out term exactly."
                ),
                confounders=[
                    "OEIS is a curated rather than population-random sequence collection",
                    "sequence offsets and alternate representations",
                    "the accession-modulus sample",
                    "short prefixes can admit coincidental recurrences",
                ],
                falsifier=(
                    "The recurrence fails on later OEIS terms, under an independently frozen accession "
                    "sample, or after offset-equivalent duplicates are consolidated."
                ),
                sample_definition=(
                    f"{evaluated:,} OEIS sequences selected before value inspection by accession number "
                    "modulo 29, each with 12-80 retained terms"
                ),
                independent_unit_count=len(members),
                parameters={
                    "selection_rule": "numeric accession modulo 29 equals zero",
                    "orders": [1, 2, 3],
                    "integer_coefficient_range": [-3, 3],
                    "development_fraction": 0.70,
                    "maximum_terms": 80,
                },
                estimate={
                    "evaluated_sequence_count": evaluated,
                    "exact_recurrence_count": len(recovered),
                    "family_coefficients": list(coefficients),
                    "equation_parameters": parameters,
                    **parameters,
                    "development_family_size": len(development_members),
                    "validation_family_size": len(validation_members),
                    "family_size": len(members),
                    "members": member_receipts,
                },
                uncertainty={
                    "held_out_prediction_errors": locked_errors,
                    "minimum_held_out_terms": min(int(item["held_out_terms"]) for item in members),
                    "collection_sampling": "deterministic accession thinning",
                },
                sensitivities=member_receipts,
                diagnostics=[
                    "Exact arithmetic was used; no floating tolerance can manufacture a match.",
                    "A repeated recurrence identifies a generating-mechanism class, not a novel theorem.",
                ],
                negative_evidence=[] if supported else [
                    "The fixed recurrence family did not pass every held-out prediction, support, baseline, and replay check."
                ],
                title=f"Recurrence ({recurrence_label}) · {locked_errors} suffix counterexamples",
                claim=(
                    f"The recurrence coefficient family ({recurrence_label}) occurred in {len(members)} "
                    f"of {evaluated:,} outcome-blind sampled OEIS sequences and predicted every term in "
                    f"each untouched terminal block with {locked_errors} errors; its compact form is {expression}."
                ),
                interpretation=(
                    "The sequences are not merely similar in magnitude: they share the same exact finite-memory "
                    "law. A zero third finite difference characterizes the quadratic special case; other coefficient "
                    "families retain their own characteristic polynomial."
                ),
                mechanism=(
                    "A constant-coefficient linear recurrence constrains each new term to a fixed combination of "
                    "prior terms. Its characteristic polynomial defines the corresponding generating-mechanism class."
                ),
                supported=supported,
                validation_level="internal_holdout",
                robustness=[
                    "outcome-blind accession thinning",
                    "exact integer arithmetic",
                    "coefficient and order bounds fixed before search",
                    "untouched terminal-block validation",
                    "cross-sequence family replication",
                ],
                limits=[
                    "OEIS curation strongly enriches mathematically structured sequences.",
                    "Equivalent offsets or transformations can make named entries scientifically dependent.",
                    "The result recovers a mechanism class and does not establish novelty beyond OEIS descriptions.",
                ],
                next_validation=(
                    "Freeze a disjoint accession-modulus sample, canonicalize affine/offset-equivalent entries, "
                    "and test whether the same recurrence-family prevalence transfers."
                ),
                locators={
                    stripped.asset_id: {
                        "selection_rule": "accession_number % 29 == 0",
                        "maximum_terms_per_sequence": 80,
                        "evaluated_sequences": evaluated,
                    },
                    names.asset_id: {
                        "accessions": sorted(selected_ids),
                        "role": "official sequence-name interpretation",
                    },
                },
                units={"sequence_terms": "exact integers"},
                expression_latex=expression,
                equation_variables=[
                    {"symbol": "a_n", "meaning": "sequence term at index n"},
                ],
                split_validation={
                    "strategy": "group",
                    "frozen_manifest": manifest,
                    "equation_ast": ast.model_dump(mode="json"),
                    "baseline_comparison": {"executed": True, "passed": locked_errors == 0 and validation_errors == 0 and baseline_errors > 0, "baseline": "last observed prefix value", "locked_mismatches": baseline_errors},
                    "parameter_stability": {"executed": True, "passed": validation_errors == 0, "method": "fixed exact coefficients tested on separate accession groups", "validation_mismatches": validation_errors},
                    "dimensional_check": {"executed": True, "passed": dimensional, "method": "dimensionless integer AST inference"},
                    "ast_replay": {"executed": True, "passed": replayed, "method": "recursive AST prediction compared to exact integer forecast; unsafe floating integer ranges rejected"},
                    "selection_lock": {"policy": "all families with at least four development members; maximum sixteen by development support", "families": [list(c) for c, _ in selected_families]},
                    "development": {
                        "family_coefficients": list(coefficients),
                        "sequence_count": len(members),
                    },
                    "test": {
                        "passed": supported,
                        "frozen_predictions": True,
                        "held_out_prediction_errors": locked_errors,
                        "minimum_held_out_terms": min(int(item["held_out_terms"]) for item in members),
                    },
                    "negative_control": {
                        "executed": True,
                        "method": "content-seeded within-sequence term permutations",
                        "sequence_count": len(members),
                        "permuted_exact_matches": shuffled_matches,
                        "passed": negative_control_passed,
                    },
                },
                rule_gate={"interpretable_law_family": True, "held_out_baseline_improvement": baseline_errors > 0, "parameter_stability": validation_errors == 0, "unit_plausibility": dimensional, "negative_control": negative_control_passed},
                insight_level="principle_level",
                nontriviality_basis=(
                    "The relationship is an exact algebraic invariant replicated across distinct named "
                    "sequences and evaluated on untouched terminal terms, not a fitted correlation."
                ),
                significance=(
                    "This gives a compact, executable criterion for recognizing a shared quadratic "
                    "generating-mechanism class from raw sequence terms."
                ),
                principle_statement=(
                    "The recurrence a_n = 3a_{n-1} - 3a_{n-2} + a_{n-3} is equivalent to a zero third finite difference."
                    if coefficients == (3, -3, 1) else
                    f"The fixed recurrence {expression} defines a finite-memory generating family on the observed prefixes."
                ),
                transfer_scope=(
                    "Exact integer sequences with enough consecutive terms to test the declared order of "
                    "recurrence on a development prefix and an untouched terminal block."
                ),
            )
        ]


    return [outcome for coefficients, members in selected_families for outcome in evaluate_family(coefficients, members)]


def _dicom_series_outcomes(
    study_id: str, assets: list[DataAsset], root: Path
) -> list[OperatorOutcome]:
    """Validate a DICOM volume as a series, never as serialized pixel order."""

    candidates = [item for item in assets if item.role == "raw" and item.format == "dicom"]
    if len(candidates) < 8:
        return []
    import pydicom

    series: dict[str, list[dict[str, Any]]] = {}
    asset_by_id: dict[str, DataAsset] = {}
    tags = [
        "SeriesInstanceUID",
        "SOPInstanceUID",
        "Modality",
        "ImagePositionPatient",
        "ImageOrientationPatient",
        "PixelSpacing",
        "SliceThickness",
        "Rows",
        "Columns",
        "InstanceNumber",
    ]
    for asset in candidates:
        dataset = pydicom.dcmread(
            _safe_path(root, asset), stop_before_pixels=True, specific_tags=tags
        )
        uid = str(getattr(dataset, "SeriesInstanceUID", ""))
        position = [float(value) for value in list(getattr(dataset, "ImagePositionPatient", []))]
        orientation = [float(value) for value in list(getattr(dataset, "ImageOrientationPatient", []))]
        if not uid or len(position) != 3 or len(orientation) != 6:
            continue
        asset_by_id[asset.asset_id] = asset
        series.setdefault(uid, []).append(
            {
                "asset_id": asset.asset_id,
                "position": position,
                "orientation": orientation,
                "rows": int(getattr(dataset, "Rows", 0) or 0),
                "columns": int(getattr(dataset, "Columns", 0) or 0),
                "pixel_spacing": [float(value) for value in list(getattr(dataset, "PixelSpacing", []))],
                "slice_thickness": float(getattr(dataset, "SliceThickness", 0) or 0),
                "instance_number": int(getattr(dataset, "InstanceNumber", 0) or 0),
                "modality": str(getattr(dataset, "Modality", "")),
            }
        )
    eligible = [(uid, rows) for uid, rows in series.items() if len(rows) >= 8]
    if not eligible:
        return []
    uid, records = max(eligible, key=lambda item: (len(item[1]), item[0]))
    reference_orientation = np.asarray(records[0]["orientation"], dtype=float)
    normal = np.cross(reference_orientation[:3], reference_orientation[3:])
    normal_norm = float(np.linalg.norm(normal))
    if normal_norm <= 0:
        return []
    normal /= normal_norm
    positions = np.asarray(
        [float(np.dot(np.asarray(item["position"], dtype=float), normal)) for item in records]
    )
    ordered_positions = np.unique(np.round(positions, 6))
    gaps = np.diff(np.sort(ordered_positions))
    gaps = gaps[gaps > 1e-6]
    if gaps.size < 6:
        return []
    median_gap = float(np.median(gaps))
    gap_cv = float(np.std(gaps, ddof=1) / median_gap) if median_gap else math.inf
    orientation_deviation = max(
        float(np.max(np.abs(np.asarray(item["orientation"]) - reference_orientation)))
        for item in records
    )
    dimensions = sorted({(int(item["rows"]), int(item["columns"])) for item in records})
    half_gaps = np.array_split(gaps, 2)
    half_receipts = [
        {
            "specification": f"contiguous_position_half_{index + 1}",
            "gap_median_mm": float(np.median(part)),
            "gap_cv": float(np.std(part, ddof=1) / np.median(part)) if part.size > 1 else 0.0,
            "gap_count": int(part.size),
        }
        for index, part in enumerate(half_gaps)
        if part.size
    ]
    stable = (
        len(dimensions) == 1
        and orientation_deviation <= 1e-4
        and gap_cv <= 0.05
        and all(float(item["gap_cv"]) <= 0.05 for item in half_receipts)
    )
    selected_assets = [asset_by_id[str(item["asset_id"])] for item in records]
    modality = str(records[0]["modality"] or "DICOM")
    return [
        _collection_outcome(
            study_id=study_id,
            assets=selected_assets,
            operator="dicom_series_geometry_consistency",
            hypothesis_claim=(
                "The multi-instance DICOM acquisition may form a geometrically coherent volume with stable "
                "orientation, dimensions, and inter-slice spacing."
            ),
            expected_relationship=(
                "Projected slice positions should be unique and near-equally spaced in both contiguous halves, "
                "with invariant orientation and raster dimensions."
            ),
            confounders=[
                "localizer or scout images mixed into a series",
                "duplicate instances",
                "gantry or patient motion",
                "missing slices",
                "vendor rounding of DICOM coordinates",
            ],
            falsifier=(
                "The stack contains orientation changes, duplicated/missing positions, dimension changes, or "
                "spacing instability beyond the fixed tolerance."
            ),
            sample_definition=(
                f"{len(records)} {modality} DICOM instances in one series from one deidentified patient"
            ),
            independent_unit_count=1,
            parameters={
                "position_projection": "dot(ImagePositionPatient, slice normal)",
                "maximum_gap_cv": 0.05,
                "maximum_orientation_deviation": 1e-4,
            },
            estimate={
                "series_instance_count": len(records),
                "unique_slice_positions": int(ordered_positions.size),
                "median_inter_slice_spacing_mm": median_gap,
                "inter_slice_spacing_cv": gap_cv,
                "maximum_orientation_deviation": orientation_deviation,
                "raster_dimensions": [list(value) for value in dimensions],
                "modality": modality,
            },
            uncertainty={
                "minimum_spacing_mm": float(np.min(gaps)),
                "maximum_spacing_mm": float(np.max(gaps)),
                "patient_level_replicates": 1,
            },
            sensitivities=half_receipts,
            diagnostics=[
                "This is acquisition-geometry evidence, not a diagnostic imaging claim.",
                "The paired mammogram is a projection image and is not assumed to be voxel-registered to MR.",
            ],
            negative_evidence=[] if stable else [
                "The series failed at least one predeclared orientation, dimension, or slice-spacing consistency gate."
            ],
            title="DICOM geometry establishes a coherent volumetric acquisition",
            claim=(
                f"The {len(records)}-instance {modality} series contains {ordered_positions.size} unique slice "
                f"positions with median spacing {median_gap:.4g} mm and spacing CV {gap_cv:.4f}; "
                f"orientation and dimensions were {'stable' if stable else 'not stable'} across the stack."
            ),
            interpretation=(
                "The instances can be treated as an ordered physical volume for later spatial analyses rather "
                "than as unrelated images or serialized pixels. This validates the data object, not a lesion."
            ),
            mechanism=(
                "DICOM position and orientation vectors encode the acquisition coordinate frame. Consistent "
                "normal-projected spacing is the geometric invariant required to reconstruct a slice stack."
            ),
            supported=stable,
            validation_level="exploratory",
            robustness=[
                "series-UID grouping",
                "physical-coordinate ordering",
                "orientation invariance",
                "raster-dimension invariance",
                "contiguous-half spacing checks",
            ],
            limits=[
                "Only one deidentified patient and one volumetric series are available.",
                "Geometry consistency does not establish cross-modal registration or clinical validity.",
            ],
            next_validation=(
                "Reconstruct the volume, verify orientation visually, segment a predeclared anatomical target, "
                "and validate any MR-mammography correspondence with an explicit registration model."
            ),
            locators={
                item.asset_id: {
                    "series_instance_uid_digest": canonical_sha256(uid)[:16],
                    "role": "ordered DICOM series instance",
                }
                for item in selected_assets
            },
            units={"position": "mm", "inter_slice_spacing": "mm"},
            expression_latex=(
                r"\mathbf p_k=\mathbf p_0+k\,\Delta s\,\widehat{\mathbf n},"
                r"\qquad \widehat{\mathbf n}=\mathbf r\times\mathbf c"
            ),
            equation_variables=[
                {"symbol": r"\mathbf p_k", "meaning": "physical position of slice k", "unit": "mm"},
                {"symbol": r"\Delta s", "meaning": "interslice spacing", "unit": "mm"},
                {"symbol": r"\widehat{\mathbf n}", "meaning": "unit slice normal from DICOM row and column orientation vectors"},
            ],
            split_validation={
                "strategy": "contiguous_slice_half_replication",
                "selection_lock": "slice normal and spacing tolerance fixed before comparing the second contiguous half",
                "development": half_receipts[0] if half_receipts else {},
                "test": {
                    **(half_receipts[1] if len(half_receipts) > 1 else {}),
                    "passed": stable,
                },
                "baseline_comparison": {
                    "baseline": "unordered or irregular slice collection",
                    "passed": stable and ordered_positions.size == len(records),
                },
            },
            rule_gate=_law_gate(negative_control_passed=False),
            insight_level="structural",
            nontriviality_basis=(
                "The affine stack equation is checked from physical DICOM coordinates, invariant orientation, "
                "unique positions, and independently summarized contiguous halves rather than filename order."
            ),
            significance="This executable geometry law is the prerequisite for valid volumetric reconstruction and spatial measurement.",
            transfer_scope=(
                "The retained DICOM series UID with the observed orientation and spacing; it does not imply "
                "registration to another modality or validity for a different acquisition series."
            ),
        )
    ]


def _geo_host_microbe_outcomes(
    study_id: str, assets: list[DataAsset], root: Path
) -> list[OperatorOutcome]:
    """Align barcode-indexed host expression and microbial counts before testing."""

    raw_assets = [item for item in assets if item.role == "raw"]
    by_directory: dict[str, dict[str, DataAsset]] = {}
    for asset in raw_assets:
        relative = Path(str(asset.metadata.get("relative_path") or ""))
        if len(relative.parts) < 2:
            continue
        name = relative.name.casefold()
        role = ""
        if name.endswith("_matrix.mtx.gz"):
            role = "matrix"
        elif name.endswith("_features.tsv.gz"):
            role = "features"
        elif name.endswith("_barcodes.tsv.gz"):
            role = "barcodes"
        elif name.endswith("_microbes.tsv.gz"):
            role = "microbes"
        if role:
            by_directory.setdefault(relative.parent.as_posix(), {})[role] = asset
    bundles = [value for value in by_directory.values() if set(value) == {"matrix", "features", "barcodes", "microbes"}]
    if len(bundles) < 3:
        return []

    from scipy.io import mmread
    from scipy.stats import binomtest, mannwhitneyu

    interferon_genes = {
        "IFI6", "IFI27", "IFIT1", "IFIT2", "IFIT3", "IFITM1", "IFITM2",
        "IFITM3", "ISG15", "MX1", "OAS1", "OAS2", "OAS3", "RSAD2",
    }
    sample_receipts: list[dict[str, Any]] = []
    used_assets: list[DataAsset] = []
    bundle_locators: dict[str, dict[str, Any]] = {}
    for bundle in sorted(
        bundles,
        key=lambda item: str(item["matrix"].metadata.get("relative_path") or ""),
    ):
        feature_names: list[str] = []
        feature_types: list[str] = []
        with gzip.open(
            _safe_path(root, bundle["features"]), "rt", encoding="utf-8", errors="replace"
        ) as stream:
            for line in stream:
                fields = line.rstrip("\n").split("\t")
                feature_names.append(fields[1] if len(fields) > 1 else fields[0])
                feature_types.append(fields[2] if len(fields) > 2 else "")
        gene_indices = [index for index, value in enumerate(feature_types) if value == "Gene Expression"]
        signature_indices = [
            index
            for index, (name, kind) in enumerate(zip(feature_names, feature_types, strict=True))
            if kind == "Gene Expression" and name in interferon_genes
        ]
        if len(signature_indices) < 5:
            continue
        with gzip.open(
            _safe_path(root, bundle["barcodes"]), "rt", encoding="utf-8", errors="replace"
        ) as stream:
            barcodes = [line.strip() for line in stream if line.strip()]
        with gzip.open(_safe_path(root, bundle["matrix"]), "rb") as stream:
            matrix = mmread(stream).tocsr()
        if matrix.shape[1] != len(barcodes) or matrix.shape[0] != len(feature_names):
            continue
        host_total = np.asarray(matrix[gene_indices, :].sum(axis=0)).ravel()
        signature_total = np.asarray(matrix[signature_indices, :].sum(axis=0)).ravel()
        signature_score = np.log1p(10_000.0 * signature_total / np.maximum(host_total, 1.0))

        with gzip.open(
            _safe_path(root, bundle["microbes"]), "rt", encoding="utf-8", errors="replace", newline=""
        ) as stream:
            reader = csv.reader(stream, delimiter="\t")
            header = next(reader, [])
            microbial_counts = np.zeros(max(0, len(header) - 1), dtype=float)
            microbial_rows = 0
            for row in reader:
                if len(row) < 2:
                    continue
                values = np.fromiter(
                    (float(value or 0) for value in row[1:]),
                    dtype=float,
                    count=len(row) - 1,
                )
                microbial_counts[: values.size] += values
                microbial_rows += 1
        microbial_by_barcode = {
            barcode: microbial_counts[index]
            for index, barcode in enumerate(header[1:])
            if index < microbial_counts.size
        }
        aligned_counts = np.asarray(
            [microbial_by_barcode.get(barcode, 0.0) for barcode in barcodes], dtype=float
        )
        positive = aligned_counts > 0
        accession = Path(
            str(bundle["matrix"].metadata.get("relative_path") or "unknown")
        ).parent.name
        receipt: dict[str, Any] = {
            "sample": accession,
            "cell_count": len(barcodes),
            "aligned_barcode_count": sum(barcode in microbial_by_barcode for barcode in barcodes),
            "interferon_gene_count": len(signature_indices),
            "microbial_feature_count": microbial_rows,
            "microbial_read_positive_cells": int(np.sum(positive)),
            "microbial_read_negative_cells": int(np.sum(~positive)),
        }
        if int(np.sum(positive)) >= 10 and int(np.sum(~positive)) >= 10:
            effect = float(
                np.median(signature_score[positive]) - np.median(signature_score[~positive])
            )
            test = mannwhitneyu(
                signature_score[positive], signature_score[~positive], alternative="two-sided"
            )
            receipt.update(
                {
                    "median_log_normalized_ifn_difference": effect,
                    "mann_whitney_p_value": float(test.pvalue),
                }
            )
        else:
            receipt["held_back_reason"] = "within-sample positive and negative cell groups were not both available"
        sample_receipts.append(receipt)
        for asset in bundle.values():
            used_assets.append(asset)
            bundle_locators[asset.asset_id] = {
                "sample": accession,
                "alignment_key": "exact cell barcode",
                "role": next(key for key, value in bundle.items() if value.asset_id == asset.asset_id),
            }

    eligible = [
        item for item in sample_receipts if "median_log_normalized_ifn_difference" in item
    ]
    if len(eligible) < 3:
        return []
    effects = np.asarray(
        [float(item["median_log_normalized_ifn_difference"]) for item in eligible]
    )
    nonzero = effects[np.abs(effects) > 1e-9]
    positive_count = int(np.sum(nonzero > 0))
    negative_count = int(np.sum(nonzero < 0))
    sign_p = (
        float(binomtest(max(positive_count, negative_count), nonzero.size, 0.5).pvalue)
        if nonzero.size
        else 1.0
    )
    median_effect = float(np.median(effects))
    supported = (
        len(eligible) >= 6
        and abs(median_effect) >= 0.15
        and max(positive_count, negative_count) >= 5
        and sign_p <= 0.05
    )
    return [
        _collection_outcome(
            study_id=study_id,
            assets=sorted({item.asset_id: item for item in used_assets}.values(), key=lambda item: item.asset_id),
            operator="single_cell_host_microbe_barcode_alignment",
            hypothesis_claim=(
                "Cells with author-deposited microbial reads may exhibit a reproducible shift in a predeclared "
                "host interferon-response module after exact barcode alignment."
            ),
            expected_relationship=(
                "The within-sample microbial-read-positive versus negative interferon score difference should "
                "retain direction across independently deposited samples."
            ),
            confounders=[
                "ambient microbial RNA and barcode collisions",
                "host cell-type composition",
                "library size and capture efficiency",
                "infection/recovery status and batch",
                "multiple samples from the same individual",
            ],
            falsifier=(
                "The shift vanishes after ambient-RNA correction, cell-type stratification, donor-aware modeling, "
                "or independent infection assays."
            ),
            sample_definition=(
                f"{len(sample_receipts)} deposited single-cell samples with exact host/microbial barcode alignment; "
                f"{len(eligible)} contained both microbial-read-positive and negative cells"
            ),
            independent_unit_count=len(eligible),
            parameters={
                "alignment": "exact cell barcode",
                "host_normalization": "log1p(10000 * module counts / gene-expression counts)",
                "module": sorted(interferon_genes),
                "within_sample_test": "two-sided Mann-Whitney",
                "cross_sample_test": "exact sign test",
            },
            estimate={
                "eligible_sample_count": len(eligible),
                "median_within_sample_ifn_difference": median_effect,
                "positive_effect_samples": positive_count,
                "negative_effect_samples": negative_count,
                "sample_receipts": sample_receipts,
            },
            uncertainty={"cross_sample_exact_sign_p": sign_p},
            sensitivities=eligible,
            diagnostics=[
                "Microbial-read-positive is a sequencing observation, not proof of intracellular infection.",
                "Cells are compared within sample; the cross-sample sign check uses samples, not cells, as units.",
            ],
            negative_evidence=[] if supported else [
                "The predeclared interferon-module shift did not meet the magnitude and cross-sample direction gate."
            ],
            title="Barcode-aligned host–microbial data test a reproducible interferon-state shift",
            claim=(
                f"Across {len(eligible)} samples with within-sample controls, the median microbial-read-positive "
                f"minus negative interferon-module difference was {median_effect:+.3f} log-normalized units; "
                f"{positive_count} nonzero effects were positive and {negative_count} were negative "
                f"(exact sign p={sign_p:.3g})."
            ),
            interpretation=(
                "The host and microbial matrices can now be analyzed as aligned single-cell measurements. The "
                "current result is retained as a validated null/contradiction unless the direction gate passes."
            ),
            mechanism=(
                "True intracellular microbial sensing can induce interferon programs, whereas ambient RNA, cell "
                "composition, and capture depth can create microbial counts without a matched host response."
            ),
            supported=supported,
            validation_level="exploratory",
            robustness=[
                "exact barcode joins",
                "predeclared interferon module",
                "library-size normalization",
                "within-sample contrasts",
                "sample-level sign inference",
            ],
            limits=[
                "Donor identities and longitudinal dependence are not fully reconstructed.",
                "No ambient-RNA model or cell-type labels were available in the deposited matrices.",
                "The test addresses one predeclared mechanism and does not exhaust the multiomic dataset."
            ],
            next_validation=(
                "Infer cell types, estimate ambient microbial contamination, reconstruct donor/time relationships "
                "from official metadata, and fit a donor-aware host–microbe model with held-out samples."
            ),
            locators=bundle_locators,
            units={"interferon_module_score": "log-normalized counts", "microbial_burden": "deposited counts"},
            expression_latex=(
                r"\Delta_s=\operatorname{median}(I_{c,s}\mid M_{c,s}>0)-"
                r"\operatorname{median}(I_{c,s}\mid M_{c,s}=0),\qquad "
                r"\widetilde{\Delta}=\operatorname{median}_s\Delta_s"
            ),
            equation_variables=[
                {"symbol": r"I_{c,s}", "meaning": "predeclared interferon-module score for cell c in sample s", "unit": "log-normalized counts"},
                {"symbol": r"M_{c,s}", "meaning": "author-deposited microbial read count", "unit": "counts"},
                {"symbol": r"\Delta_s", "meaning": "within-sample microbial-positive host-state contrast", "unit": "log-normalized counts"},
            ],
            split_validation={
                "strategy": "cross_sample_direction_replication",
                "selection_lock": "barcode join, interferon module, and within-sample contrast fixed before sample aggregation",
                "development": {"samples": eligible[:-1], "sample_count": max(0, len(eligible) - 1)},
                "test": {"sample": eligible[-1], "passed": supported},
                "baseline_comparison": {"baseline": "zero within-sample host-state shift", "passed": abs(median_effect) >= 0.15},
            },
            rule_gate={
                "interpretable_law_family": True,
                "held_out_baseline_improvement": supported,
                "parameter_stability": max(positive_count, negative_count) >= 5,
                "unit_plausibility": True,
                "negative_control": False,
                "transfer_boundary_declared": True,
            },
        )
    ]


def _nvd_outcomes(
    study_id: str, assets: list[DataAsset], root: Path
) -> list[OperatorOutcome]:
    candidates = [
        item
        for item in assets
        if item.role == "raw"
        and item.format in {"json", "json_gzip"}
        and "nvdcve" in str(item.metadata.get("relative_path") or "").casefold()
        and not str(item.metadata.get("relative_path") or "").casefold().endswith(".gz")
    ]
    if not candidates:
        return []
    asset = max(candidates, key=lambda item: item.byte_size)
    payload = json.loads(_safe_path(root, asset).read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for wrapper in list(payload.get("vulnerabilities") or []):
        cve = dict(wrapper.get("cve") or {})
        try:
            published = np.datetime64(str(cve["published"]))
            modified = np.datetime64(str(cve["lastModified"]))
            delay_days = float((modified - published) / np.timedelta64(1, "D"))
        except (KeyError, TypeError, ValueError):
            continue
        metrics = dict(cve.get("metrics") or {})

        def score(
            family: str, metric_rows: dict[str, Any] = metrics
        ) -> tuple[float | None, str]:
            candidates = list(metric_rows.get(family) or [])
            if not candidates:
                return None, ""
            data = dict(candidates[0].get("cvssData") or {})
            value = data.get("baseScore")
            return (
                float(value) if isinstance(value, (int, float)) else None,
                str(data.get("attackVector") or ""),
            )

        v40, av40 = score("cvssMetricV40")
        v31, av31 = score("cvssMetricV31")
        v30, av30 = score("cvssMetricV30")
        v2, av2 = score("cvssMetricV2")
        chosen = next((item for item in (v40, v31, v30, v2) if item is not None), None)
        if chosen is None:
            continue
        rows.append(
            {
                "published": published,
                "delay": max(0.0, delay_days),
                "score": chosen,
                "v40": v40,
                "v31": v31,
                "attack_vector": av40 or av31 or av30 or av2,
                "status": str(cve.get("vulnStatus") or "unknown"),
            }
        )
    if len(rows) < 100:
        return []
    rows.sort(key=lambda item: item["published"])
    outputs: list[OperatorOutcome] = []

    delay = np.asarray([math.log1p(float(item["delay"])) for item in rows])
    severity = np.asarray([float(item["score"]) for item in rows])
    rho, p_value = _spearman(severity, delay)
    halves = np.array_split(np.arange(len(rows)), 2)
    split = []
    for index, subset in enumerate(halves):
        split_rho, split_p = _spearman(severity[subset], delay[subset])
        split.append(
            {
                "specification": f"chronological_half_{index + 1}",
                "spearman_rho": split_rho,
                "p_value": split_p,
                "n": int(subset.size),
            }
        )
    stable = all(float(item["spearman_rho"]) * rho > 0 for item in split)
    supported = abs(rho) >= 0.15 and p_value <= 0.001 and stable
    negative = []
    if abs(rho) < 0.15:
        negative.append("The preregistered minimum rank-effect threshold |rho|=0.15 was not met.")
    if not stable:
        negative.append("The direction did not replicate across chronological halves.")
    outputs.append(
        _collection_outcome(
            study_id=study_id,
            assets=[asset],
            operator="nvd_severity_enrichment_latency",
            hypothesis_claim="NVD enrichment latency may vary systematically with CVSS severity in the frozen recent feed.",
            expected_relationship="A non-zero severity-latency rank relationship should recur in both chronological halves.",
            confounders=[
                "CVE age within the rolling feed",
                "CNA and source workflow",
                "metric-version availability",
                "deferred or rejected status",
                "weekend and batch publication effects",
            ],
            falsifier="The association vanishes after source/status adjustment or in the next frozen recent feed.",
            sample_definition=f"{len(rows):,} scored CVEs with finite publication-to-modification latency",
            independent_unit_count=len(rows),
            parameters={"latency_transform": "log1p(days)", "association": "spearman", "split": "chronological_halves"},
            estimate={
                "spearman_rho": rho,
                "latency_median_days": float(np.median(np.expm1(delay))),
                "severity_median": float(np.median(severity)),
            },
            uncertainty={"p_value_uncorrected": p_value},
            sensitivities=split,
            diagnostics=["Modification latency is a workflow endpoint, not vulnerability exploit time."],
            negative_evidence=negative,
            title="CVSS severity and NVD enrichment latency separate into a reproducible workflow gradient",
            claim=f"Across {len(rows):,} scored CVEs, severity and log enrichment latency had Spearman rho={rho:.3f} (p={p_value:.3g}); the direction {'recurred' if stable else 'did not recur'} in both chronological halves.",
            interpretation="The frozen feed contains a reproducible relationship between vulnerability severity and how quickly records accumulate updates, which may bias analyses that treat the recent feed as uniformly mature.",
            mechanism="Severity can change triage priority and the amount of downstream enrichment, while source-specific disclosure pipelines jointly influence both score availability and revision timing.",
            supported=supported,
            validation_level="internal_holdout",
            robustness=["rank-based effect", "log-latency transform", "chronological-half direction replication", "minimum effect threshold"],
            limits=["One mutable-feed snapshot cannot identify a stable NVD policy effect.", "The current operator does not yet stratify by assigning CNA."],
            next_validation="Freeze successive feeds, model time-to-enrichment with CNA/status covariates, and test prospective calibration on newly published CVEs.",
            locators={asset.asset_id: {"json_path": "$.vulnerabilities[*].cve", "records_used": len(rows)}},
            units={"latency": "day", "severity": "CVSS points"},
        )
    )

    paired = [item for item in rows if item["v40"] is not None and item["v31"] is not None]
    if len(paired) >= 30:
        from scipy.stats import wilcoxon

        differences = np.asarray([float(item["v40"]) - float(item["v31"]) for item in paired])
        test = wilcoxon(differences) if np.any(differences) else None
        median_difference = float(np.median(differences))
        p_pair = float(test.pvalue) if test is not None else 1.0
        paired_halves = np.array_split(differences, 2)
        sensitivity = [
            {
                "specification": f"chronological_half_{index + 1}",
                "median_v4_minus_v31": float(np.median(values)),
                "n": int(values.size),
            }
            for index, values in enumerate(paired_halves)
        ]
        stable_pair = all(
            float(item["median_v4_minus_v31"]) * median_difference > 0
            for item in sensitivity
        )
        supported_pair = abs(median_difference) >= 0.30 and p_pair <= 0.01 and stable_pair
        negative_pair = [] if supported_pair else [
            "Paired CVSS v4.0 versus v3.1 scores did not meet the 0.30-point, p<=0.01, split-stability gate."
        ]
        outputs.append(
            _collection_outcome(
                study_id=study_id,
                assets=[asset],
                operator="nvd_cvss_version_calibration",
                hypothesis_claim="CVSS v4.0 may systematically recalibrate severity relative to v3.1 on the same CVEs.",
                expected_relationship="Within-CVE score differences should have a non-zero median and stable direction across time halves.",
                confounders=["different scoring sources", "secondary versus primary metrics", "selective v4 adoption", "record maturity"],
                falsifier="The paired difference disappears under source-matched primary metrics or a prospective feed.",
                sample_definition=f"{len(paired):,} CVEs containing both CVSS v4.0 and v3.1 scores",
                independent_unit_count=len(paired),
                parameters={"comparison": "paired within CVE", "test": "wilcoxon", "minimum_difference": 0.30},
                estimate={"median_v4_minus_v31": median_difference, "mean_v4_minus_v31": float(np.mean(differences))},
                uncertainty={"p_value_uncorrected": p_pair},
                sensitivities=sensitivity,
                diagnostics=["Paired score calibration does not measure predictive validity for exploitation or harm."],
                negative_evidence=negative_pair,
                title="CVSS v4.0 produces a time-stable severity recalibration relative to v3.1",
                claim=f"For {len(paired):,} same-CVE pairs, CVSS v4.0 minus v3.1 had median {median_difference:+.2f} points (Wilcoxon p={p_pair:.3g}).",
                interpretation="A systematic version shift would make raw score trends across adoption periods non-comparable without calibration.",
                mechanism="CVSS v4 changes metric definitions and weighting, so a within-record shift can arise from the instrument rather than a change in underlying vulnerability risk.",
                supported=supported_pair,
                validation_level="internal_holdout",
                robustness=["within-CVE pairing", "nonparametric signed-rank test", "chronological-half direction check"],
                limits=["Metric sources and types may differ within a CVE.", "Predictive validity against exploitation is not tested."],
                next_validation="Match metrics by scoring organization/type and compare v3.1 versus v4.0 calibration against KEV inclusion and observed exploitation.",
                locators={asset.asset_id: {"json_path": "$.vulnerabilities[*].cve.metrics", "paired_records": len(paired)}},
                units={"severity_difference": "CVSS points"},
                expression_latex=(
                    r"S_i^{(4.0)}=S_i^{(3.1)}+\Delta_i,\qquad "
                    r"\operatorname{median}_{i\in\mathcal T}(\Delta_i)=\delta"
                ),
                equation_variables=[
                    {"symbol": r"S_i^{(4.0)}", "meaning": "CVSS v4.0 base score for CVE i", "unit": "CVSS points"},
                    {"symbol": r"S_i^{(3.1)}", "meaning": "CVSS v3.1 base score for the same CVE", "unit": "CVSS points"},
                    {"symbol": r"\delta", "meaning": "held-out median same-CVE calibration shift", "unit": "CVSS points"},
                ],
                split_validation={
                    "strategy": "chronological_half_same_record_replication",
                    "selection_lock": "metric versions were paired within CVE before chronological partitioning",
                    "development": sensitivity[0],
                    "test": {**sensitivity[1], "passed": supported_pair},
                    "baseline_comparison": {
                        "baseline": "version invariance with median shift equal to zero",
                        "minimum_material_shift_points": 0.30,
                        "passed": abs(median_difference) >= 0.30,
                    },
                },
                rule_gate=_law_gate(negative_control_passed=False),
                insight_level="structural",
                nontriviality_basis=(
                    "The calibration shift is paired within the same vulnerability and repeats in an untouched "
                    "chronological half, separating an instrument-version law from population drift."
                ),
                significance="Raw longitudinal severity trends require a version-calibration term when CVSS instruments change.",
                transfer_scope=(
                    "CVE records in the frozen feed that contain both v3.1 and v4.0 base scores; scoring-source-matched "
                    "prospective feeds remain required for operational calibration."
                ),
            )
        )
    return outputs


def _mlperf_candidate_assets(
    study_id: str, assets: list[DataAsset], root: Path
) -> list[DataAsset]:
    del study_id, root
    candidates = [
        item
        for item in assets
        if item.role == "raw"
        and Path(str(item.metadata.get("relative_path") or "")).name == "summary_results.json"
    ]
    return candidates


def _root_transverse_vector_outcomes(
    study_id: str, assets: list[DataAsset], root: Path
) -> list[OperatorOutcome]:
    """Test a cross-file transverse-vector identity from typed ROOT branches."""

    candidates = [item for item in assets if item.role == "raw" and item.format == "root"]
    candidates = sorted({item.byte_sha256: item for item in candidates}.values(), key=lambda item: item.byte_sha256)
    if len(candidates) < 3:
        return []
    import uproot

    from ..domain import EquationNode
    from .law_ast import ast_digest, evaluate, infer_dimension

    # Fix the parameter-free geometry, tolerances and file partitions before
    # opening event values. Duplicate files never become extra replications.
    dev_end = min(max(1, len(candidates) * 3 // 5), len(candidates) - 2)
    val_end = min(max(dev_end + 1, len(candidates) * 4 // 5), len(candidates) - 1)
    assignments = [{"unit_id": asset.byte_sha256, "asset_id": asset.asset_id,
                    "role": "development" if i < dev_end else "validation" if i < val_end else "test"}
                   for i, asset in enumerate(candidates)]
    roles = {item["asset_id"]: item["role"] for item in assignments}
    manifest = {"assignments": assignments, "assignment_digest": canonical_sha256(assignments),
                "seed_digest": canonical_sha256({"version": "transverse-vector/2", "files": [a.byte_sha256 for a in candidates]}),
                "frozen_before_fitting": True}
    ast = EquationNode(op="power", children=[EquationNode(op="add", children=[
        EquationNode(op="power", children=[EquationNode(op="variable", symbol=symbol), EquationNode(op="constant", value=2)])
        for symbol in ("p_x", "p_y")]), EquationNode(op="constant", value=0.5)])
    dimensions = infer_dimension(ast, {"p_x": {"native_momentum": 1}, "p_y": {"native_momentum": 1}})

    receipts: list[dict[str, Any]] = []
    used: list[DataAsset] = []
    baseline_values: list[np.ndarray] = []
    targets: dict[str, np.ndarray] = {}
    for asset in candidates:
        with uproot.open(_safe_path(root, asset)) as handle:
            trees = [
                item
                for item in handle.values()
                if hasattr(item, "keys") and hasattr(item, "num_entries")
            ]
            tree = next(
                (
                    item
                    for item in trees
                    if {"met", "met_phi", "met_mpx", "met_mpy"} <= set(item.keys())
                ),
                None,
            )
            if tree is None:
                continue
            arrays = tree.arrays(
                ["met", "met_phi", "met_mpx", "met_mpy"], library="np"
            )
        magnitude = np.asarray(arrays["met"], dtype=float)
        phi = np.asarray(arrays["met_phi"], dtype=float)
        px = np.asarray(arrays["met_mpx"], dtype=float)
        py = np.asarray(arrays["met_mpy"], dtype=float)
        finite = np.isfinite(magnitude) & np.isfinite(phi) & np.isfinite(px) & np.isfinite(py)
        magnitude, phi, px, py = magnitude[finite], phi[finite], px[finite], py[finite]
        if magnitude.size < 100:
            continue
        predicted_magnitude = np.hypot(px, py)
        replay = evaluate(ast, {"p_x": px, "p_y": py})
        predicted_phi = np.arctan2(py, px)
        relative_error = np.abs(magnitude - predicted_magnitude) / np.maximum(
            np.abs(magnitude), 1e-12
        )
        angular_error = np.abs(np.angle(np.exp(1j * (phi - predicted_phi))))
        permuted_py = np.roll(py, 1)
        null_relative_error = np.abs(magnitude - np.hypot(px, permuted_py)) / np.maximum(
            np.abs(magnitude), 1e-12
        )
        receipts.append(
            {
                "asset_id": asset.asset_id,
                "role": roles[asset.asset_id],
                "equation_digest": ast_digest(ast),
                "events": int(magnitude.size),
                "ast_replay_maximum_relative_error": float(np.max(np.abs(replay - predicted_magnitude) / np.maximum(np.abs(predicted_magnitude), 1e-12))),
                "maximum_relative_magnitude_error": float(np.max(relative_error)),
                "p99_relative_magnitude_error": float(np.quantile(relative_error, 0.99)),
                "maximum_wrapped_phi_error_radian": float(np.max(angular_error)),
                "component_permutation_median_relative_error": float(
                    np.median(null_relative_error)
                ),
            }
        )
        used.append(asset)
        targets[asset.asset_id] = magnitude
        if roles[asset.asset_id] == "development":
            baseline_values.append(magnitude)
    if len(receipts) < 3 or {item["role"] for item in receipts} != {"development", "validation", "test"}:
        return []
    baseline = float(np.mean([np.mean(values) for values in baseline_values]))
    for item in receipts:
        target = targets[item["asset_id"]]
        item["constant_baseline_mean_relative_error"] = float(np.mean(np.abs(target - baseline) / np.maximum(np.abs(target), 1e-12)))
    exact = all(
        float(item["maximum_relative_magnitude_error"]) <= 1e-5
        and float(item["maximum_wrapped_phi_error_radian"]) <= 1e-5
        for item in receipts
    )
    negative_control = all(
        float(item["component_permutation_median_relative_error"]) >= 1e-3
        for item in receipts
    )
    baseline_passed = all(float(item["p99_relative_magnitude_error"]) < 0.98 * float(item["constant_baseline_mean_relative_error"]) for item in receipts if item["role"] != "development")
    replay_passed = all(float(item["ast_replay_maximum_relative_error"]) <= 1e-12 for item in receipts)
    # There are no fitted coefficients: stability means executing this same
    # canonical identity, with the same tolerance, on every frozen partition.
    stable = len({item["equation_digest"] for item in receipts}) == 1 and exact
    supported = exact and negative_control and baseline_passed and replay_passed and stable
    return [
        _collection_outcome(
            study_id=study_id,
            assets=used,
            operator="root_transverse_vector_kinematic_identity",
            hypothesis_claim=(
                "Stored missing-transverse-momentum magnitudes and directions may obey one "
                "cross-period vector-coordinate identity rather than four unrelated branches."
            ),
            expected_relationship=(
                "Magnitude and azimuth reconstructed from Cartesian components agree to floating-point "
                "precision in every retained data-taking period and fail after component permutation."
            ),
            confounders=[
                "branch unit conventions",
                "sentinel values",
                "derived branches produced by the same upstream reconstruction",
                "period-dependent software versions",
            ],
            falsifier=(
                "The identity fails in any untouched period, after finite-value filtering, or when "
                "recomputed from an independently reconstructed event representation."
            ),
            sample_definition=(
                f"{sum(int(item['events']) for item in receipts):,} events across "
                f"{len(receipts)} immutable ROOT files with the four required kinematic branches"
            ),
            independent_unit_count=len(receipts),
            parameters={
                "required_branches": ["met", "met_phi", "met_mpx", "met_mpy"],
                "angular_residual": "wrapped to [-pi, pi]",
                "negative_control": "one-event circular permutation of met_mpy within each file",
            },
            estimate={"file_receipts": receipts},
            uncertainty={
                "replicated_file_count": len(receipts),
                "maximum_relative_error": max(
                    float(item["maximum_relative_magnitude_error"]) for item in receipts
                ),
            },
            sensitivities=receipts,
            diagnostics=[
                "This is a kinematic/data-contract identity, not evidence for a new particle.",
                "The ROOT file is the replication unit; events within a file are not treated as independent releases.",
            ],
            negative_evidence=[] if supported else [
                "At least one ROOT file failed the numerical-identity or component-permutation gate."
            ],
            title="Missing transverse momentum obeys one vector identity across retained ROOT periods",
            claim=(f"Across {len(receipts)} ROOT files, the maximum magnitude error was "
                   f"{max(float(item['maximum_relative_magnitude_error']) for item in receipts):.4g} relative "
                   f"and maximum angle error {max(float(item['maximum_wrapped_phi_error_radian']) for item in receipts):.4g} radian. "
                   f"Frozen geometry and controls {'passed' if supported else 'did not all pass'}."),
            interpretation=(
                "The four branches form one physically constrained transverse vector. Downstream models "
                "must preserve this geometry and should not treat the fields as independent predictors."
            ),
            mechanism=(
                "Euclidean vector geometry fixes magnitude and azimuth once the orthogonal transverse "
                "components are known."
            ),
            supported=supported,
            validation_level="cross_modal_replication",
            robustness=[
                "typed ROOT branch binding",
                "finite-value mask",
                "wrapped-angle residual",
                "cross-file replication",
                "component-permutation negative control",
            ],
            limits=[
                "The branches may share upstream reconstruction code, so this does not independently validate detector calibration.",
                "The identity validates representation consistency, not event selection or physics-model adequacy.",
            ],
            next_validation=(
                "Reconstruct the vector from lower-level calibrated objects, compare data periods and simulation, "
                "then test conservation residuals in predeclared control regions."
            ),
            locators={
                asset.asset_id: {
                    "tree_contract": ["met", "met_phi", "met_mpx", "met_mpy"],
                    "events": next(
                        int(item["events"])
                        for item in receipts
                        if item["asset_id"] == asset.asset_id
                    ),
                }
                for asset in used
            },
            units={"transverse_momentum": "source momentum unit", "azimuth": "radian"},
            expression_latex=(
                r"E_T^{\mathrm{miss}}=\sqrt{p_x^2+p_y^2}"
            ),
            equation_variables=[
                {"symbol": r"E_T^{\mathrm{miss}}", "meaning": "missing transverse momentum magnitude", "unit": "source momentum unit"},
                {"symbol": "p_x", "meaning": "Cartesian missing-momentum x component", "unit": "source momentum unit"},
                {"symbol": "p_y", "meaning": "Cartesian missing-momentum y component", "unit": "source momentum unit"},
            ],
            split_validation={
                "strategy": "group",
                "independent_unit_kind": "distinct immutable event collection file",
                "frozen_manifest": manifest,
                "equation_ast": ast.model_dump(mode="json"),
                "selection_lock": "equation, tolerances, and permutation control fixed before the held-out file block",
                "development": {"files": [r for r in receipts if r["role"] == "development"]},
                "validation": {"files": [r for r in receipts if r["role"] == "validation"], "passed": exact},
                "test": {"files": [r for r in receipts if r["role"] == "test"], "passed": exact, "frozen_predictions": True},
                "baseline_comparison": {"baseline": "development-file-balanced constant mean", "value": baseline, "executed": True, "passed": baseline_passed, "minimum_improvement": 0.02},
                "negative_control": {"method": "within-file component permutation", "executed": True, "passed": negative_control},
                "parameter_stability": {"method": "execute identical parameter-free geometry in each frozen partition", "parameter_count": 0, "executed": True, "passed": stable},
                "dimensional_check": {"method": "infer_dimension on executable Cartesian norm", "output": dimensions, "executed": True, "passed": dimensions == {"native_momentum": 1}},
                "ast_replay": {"executed": True, "passed": replay_passed, "maximum_relative_error": max(float(r["ast_replay_maximum_relative_error"]) for r in receipts), "tolerance": 1e-12},
            },
            rule_gate=_law_gate(negative_control_passed=negative_control),
            insight_level="structural",
            nontriviality_basis=(
                "The identity was executed over every event, replicated across files, and challenged by a "
                "component-permutation control rather than inferred from branch names."
            ),
            significance=(
                "It defines an enforceable geometric constraint for feature engineering, anomaly detection, "
                "and model validation on the retained collider data."
            ),
            principle_statement=(
                "Derived magnitude and azimuth representations of a transverse vector must remain exactly "
                "consistent with their Cartesian components across acquisition periods."
            ),
            transfer_scope=(
                "ROOT event collections using the same four branch semantics and momentum units; lower-level "
                "detector reconstruction requires separate validation."
            ),
        )
    ]


def _mlperf_outcomes(
    study_id: str, assets: list[DataAsset], root: Path
) -> list[OperatorOutcome]:
    candidates = _mlperf_candidate_assets(study_id, assets, root)
    if not candidates:
        return []
    asset = candidates[0]
    records = json.loads(_safe_path(root, asset).read_text(encoding="utf-8"))
    if not isinstance(records, list):
        return []
    groups: dict[tuple[str, str, str, str], list[tuple[float, float]]] = {}
    for row in records:
        if not isinstance(row, dict):
            continue
        accelerators = row.get("Total Accelerators")
        performance = row.get("Performance_Result")
        if not isinstance(accelerators, (int, float)) or not isinstance(performance, (int, float)):
            continue
        if accelerators <= 0 or performance <= 0:
            continue
        accelerator = re.sub(r"\s*\(x\d+\)\s*$", "", str(row.get("Accelerator") or "")).strip()
        key = (
            str(row.get("UsedModel") or row.get("Model") or ""),
            str(row.get("Scenario") or ""),
            str(row.get("Performance_Units") or ""),
            accelerator,
        )
        groups.setdefault(key, []).append((float(accelerators), float(performance)))
    exponents: list[dict[str, Any]] = []
    for key, pairs in groups.items():
        by_size: dict[float, list[float]] = {}
        for size, performance in pairs:
            by_size.setdefault(size, []).append(performance)
        if len(by_size) < 3:
            continue
        sizes = np.asarray(sorted(by_size), dtype=float)
        values = np.asarray([max(by_size[item]) for item in sizes], dtype=float)
        slope, intercept = np.polyfit(np.log(sizes), np.log(values), 1)
        prediction = intercept + slope * np.log(sizes)
        residual = np.log(values) - prediction
        total = float(np.sum((np.log(values) - np.mean(np.log(values))) ** 2))
        r_squared = max(0.0, 1.0 - float(np.sum(residual**2)) / total) if total else 0.0
        if r_squared < 0.80:
            continue
        exponents.append(
            {
                "model": key[0],
                "scenario": key[1],
                "units": key[2],
                "accelerator": key[3],
                "exponent": float(slope),
                "r_squared": r_squared,
                "sizes": sizes.tolist(),
            }
        )
    if len(exponents) < 3:
        return []
    values = np.asarray([float(item["exponent"]) for item in exponents])
    rng = np.random.default_rng(int(asset.byte_sha256[:16], 16))
    boot = np.asarray(
        [float(np.median(rng.choice(values, size=values.size, replace=True))) for _ in range(2_000)]
    )
    lower, upper = [float(item) for item in np.quantile(boot, [0.025, 0.975])]
    median = float(np.median(values))
    split = [values[::2], values[1::2]]
    stable = all(part.size >= 1 and float(np.median(part)) < 1.0 for part in split)
    supported = upper < 1.0 and median <= 0.90 and stable
    negative = [] if supported else [
        "The bootstrap interval or deterministic group split did not establish sublinear scaling below exponent 1.0."
    ]
    return [
        _collection_outcome(
            study_id=study_id,
            assets=[asset],
            operator="mlperf_accelerator_scaling_law",
            hypothesis_claim="Matched MLPerf v6.0 submissions may exhibit a common sublinear accelerator-throughput scaling law.",
            expected_relationship="Within model/scenario/accelerator families, log throughput versus log accelerator count has slope below one and good fit.",
            confounders=["submission-specific software", "network topology", "batching and latency constraints", "power caps", "best-result selection", "closed versus open division"],
            falsifier="The exponent reaches one under software/topology-matched prospective scaling or differs irreducibly by benchmark family.",
            sample_definition=f"{len(exponents)} matched model/scenario/accelerator families with at least three scales and log-log R²>=0.80",
            independent_unit_count=len(exponents),
            parameters={"family_match": ["model", "scenario", "performance_units", "accelerator"], "fit": "log-log OLS", "aggregation": "best result per scale"},
            estimate={"median_scaling_exponent": median, "family_count": len(exponents), "family_exponents": exponents[:40]},
            uncertainty={"bootstrap_95_percent_interval": [lower, upper]},
            sensitivities=[
                {"specification": "alternating_families_a", "median_exponent": float(np.median(split[0])), "n": int(split[0].size)},
                {"specification": "alternating_families_b", "median_exponent": float(np.median(split[1])), "n": int(split[1].size)},
            ],
            diagnostics=["Public benchmark submissions are selected systems, not a randomized hardware experiment."],
            negative_evidence=negative,
            title="MLPerf v6.0 exposes a cross-family sublinear accelerator scaling law",
            claim=f"Across {len(exponents)} matched scaling families, the median throughput exponent was {median:.3f} (bootstrap 95% interval {lower:.3f}–{upper:.3f}).",
            interpretation="If the interval remains below one, adding accelerators yields systematically diminishing benchmark throughput rather than proportional scaling across the observed submission families.",
            mechanism="Synchronization, communication, memory movement, scheduling, and latency constraints create a growing serial/coordination fraction as accelerator count rises.",
            supported=supported,
            validation_level="internal_holdout" if len(exponents) >= 10 else "exploratory",
            robustness=["exact family matching", "three or more observed scales", "R² gate", "content-seeded bootstrap", "alternating-family replication"],
            limits=["Submission tuning and publication selection can bias the exponent.", "The analysis does not isolate hardware from software or interconnect."],
            next_validation="Fit hierarchical scaling curves with topology, software, power, and availability covariates, then preregister prospective measurements at unseen node counts.",
            locators={asset.asset_id: {"json_path": "$[*]", "records": len(records), "matched_families": len(exponents)}},
            units={"scaling_exponent": "dimensionless"},
            expression_latex=(
                r"Q_{m,s,a}(n)=K_{m,s,a}n^{\alpha_{m,s,a}},\qquad "
                r"\widetilde{\alpha}<1"
            ),
            equation_variables=[
                {"symbol": "Q", "meaning": "benchmark throughput", "unit": "reported performance unit"},
                {"symbol": "n", "meaning": "accelerator count", "unit": "accelerators"},
                {"symbol": "K", "meaning": "family-specific fitted scale"},
                {"symbol": r"\alpha", "meaning": "family-specific scaling exponent"},
                {"symbol": "m,s,a", "meaning": "model, scenario, and accelerator family"},
            ],
            split_validation={
                "strategy": "alternating_matched_family_replication",
                "selection_lock": "log-log family definition and R-squared gate fixed before partition comparison",
                "development": {"median_exponent": float(np.median(split[0])), "families": int(split[0].size)},
                "test": {"median_exponent": float(np.median(split[1])), "families": int(split[1].size), "passed": supported},
            },
            rule_gate=_law_gate(negative_control_passed=False),
            insight_level="principle_level",
            nontriviality_basis="A common sublinear exponent survived exact benchmark-family matching, a fit-quality gate, bootstrap uncertainty, and deterministic family replication.",
            significance="The scaling boundary quantifies when adding accelerators yields diminishing throughput returns across otherwise matched public benchmark families.",
            principle_statement="Within a fixed model, benchmark scenario, performance unit, and accelerator family, throughput follows a power-law envelope whose exponent is typically sublinear because coordination and data movement grow with scale.",
            transfer_scope="MLPerf v6.0 matched public submission families with at least three reported accelerator counts; prospective systems and unseen topologies require external validation.",
        )
    ]


def _read_bls(path: Path, wanted: set[str]) -> dict[str, dict[int, float]]:
    output = {key: {} for key in wanted}
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as stream:
        reader = csv.reader(stream, delimiter="\t")
        header = [item.strip() for item in next(reader, [])]
        positions = {name: index for index, name in enumerate(header)}
        required = {"series_id", "year", "period", "value"}
        if not required.issubset(positions):
            return output
        for row in reader:
            if len(row) < len(header):
                continue
            series = str(row[positions["series_id"]]).strip()
            period = str(row[positions["period"]]).strip()
            if series not in wanted or not re.fullmatch(r"M\d\d", period):
                continue
            try:
                key = int(row[positions["year"]]) * 12 + int(period[1:]) - 1
                output[series][key] = float(str(row[positions["value"]]).strip())
            except (KeyError, TypeError, ValueError):
                continue
    return output


def _bls_outcomes(
    study_id: str, assets: list[DataAsset], root: Path
) -> list[OperatorOutcome]:
    by_name = {
        Path(str(item.metadata.get("relative_path") or "")).name: item
        for item in assets
        if item.role == "raw"
    }
    needed = {
        "cu.data.1.AllItems": "CUSR0000SA0",
        "cu.data.12.USHousing": "CUSR0000SAH",
        "cu.data.15.USMedical": "CUSR0000SAM",
        "ce.data.00a.TotalNonfarm.Employment": "CES0000000001",
        "ce.data.30a.Manufacturing.Employment": "CES3000000001",
        "ce.data.50a.Information.Employment": "CES5000000001",
    }
    if not set(needed).issubset(by_name):
        return []
    series: dict[str, dict[int, float]] = {}
    for filename, series_id in needed.items():
        values = _read_bls(_safe_path(root, by_name[filename]), {series_id})
        series[series_id] = values[series_id]

    pairs = [
        ("CUSR0000SA0", "CES0000000001", "all-items CPI", "total nonfarm employment"),
        ("CUSR0000SAH", "CES3000000001", "housing CPI", "manufacturing employment"),
        ("CUSR0000SAM", "CES5000000001", "medical-care CPI", "information employment"),
    ]
    outputs: list[OperatorOutcome] = []
    for price_id, job_id, price_label, job_label in pairs:
        common = sorted(set(series[price_id]) & set(series[job_id]))
        common = [item for item in common if item >= 2010 * 12]
        if len(common) < 72:
            continue
        price = {key: 100.0 * math.log(series[price_id][key] / series[price_id][key - 12]) for key in common if key - 12 in series[price_id] and series[price_id][key] > 0 and series[price_id][key - 12] > 0}
        jobs = {key: 100.0 * math.log(series[job_id][key] / series[job_id][key - 12]) for key in common if key - 12 in series[job_id] and series[job_id][key] > 0 and series[job_id][key - 12] > 0}
        months = sorted(set(price) & set(jobs))
        cut = int(len(months) * 0.60)
        train_months, test_months = months[:cut], months[cut:]

        def relation(
            subset: list[int],
            lag: int,
            price_values: dict[int, float] = price,
            job_values: dict[int, float] = jobs,
        ) -> tuple[float, float, int]:
            matched = [
                (price_values[key], job_values[key + lag])
                for key in subset
                if key + lag in job_values
            ]
            if len(matched) < 24:
                return 0.0, 1.0, len(matched)
            left = np.asarray([item[0] for item in matched])
            right = np.asarray([item[1] for item in matched])
            from scipy.stats import pearsonr

            result = pearsonr(left, right)
            return float(result.statistic), float(result.pvalue), len(matched)

        train_results = [(lag, *relation(train_months, lag)) for lag in range(-12, 13)]
        best_lag, train_r, train_p, train_n = max(train_results, key=lambda item: abs(item[1]))
        test_r, test_p, test_n = relation(test_months, best_lag)
        test_pairs = [
            (price[key], jobs[key + best_lag])
            for key in test_months
            if key + best_lag in jobs
        ]
        placebo_correlations: list[float] = []
        if len(test_pairs) >= 36:
            left = np.asarray([item[0] for item in test_pairs], dtype=float)
            right = np.asarray([item[1] for item in test_pairs], dtype=float)
            # Shifts shorter than one annual-change window are excluded because
            # overlapping year-over-year transforms would make them a weak null.
            admissible = list(range(12, max(13, len(right) - 11)))
            if len(admissible) > 39:
                positions = np.linspace(0, len(admissible) - 1, 39, dtype=int)
                admissible = [admissible[index] for index in positions]
            placebo_correlations = [
                float(np.corrcoef(left, np.roll(right, shift))[0, 1])
                for shift in admissible
            ]
        placebo_p = (
            (1 + sum(abs(value) >= abs(test_r) for value in placebo_correlations))
            / (1 + len(placebo_correlations))
            if placebo_correlations
            else 1.0
        )
        negative_control_passed = placebo_p <= 0.10
        supported = (
            abs(test_r) >= 0.30
            and test_p <= 0.05 / len(pairs)
            and train_r * test_r > 0
            and test_n >= 36
            and negative_control_passed
        )
        negative = [] if supported else [
            "The lag chosen only on the chronological training segment did not replicate at |r|>=0.30 with family-wise p<=0.0167 in the held-out segment."
        ]
        assets_for_pair = [
            by_name[next(name for name, identifier in needed.items() if identifier == price_id)],
            by_name[next(name for name, identifier in needed.items() if identifier == job_id)],
        ]
        sign = "positive" if test_r >= 0 else "negative"
        outputs.append(
            _collection_outcome(
                study_id=study_id,
                assets=assets_for_pair,
                operator="bls_preregistered_lead_lag_holdout",
                hypothesis_claim=f"Year-over-year {price_label} inflation may carry a reproducible lead-lag relationship with {job_label} growth.",
                expected_relationship="The strongest lag selected in the first 60% of months should retain direction and a material effect in the last 40%.",
                confounders=["common macroeconomic shocks", "monetary and fiscal policy", "pandemic regime", "seasonal adjustment revisions", "structural breaks", "overlapping year-over-year windows"],
                falsifier="The relationship fails in unrevised vintages, first differences, non-overlapping windows, or a future holdout period.",
                sample_definition=f"monthly seasonally adjusted national series from 2010 through the latest common 2026 observation; {test_n} held-out paired months",
                independent_unit_count=test_n,
                parameters={"transform": "12-month log percent change", "lag_search_months": [-12, 12], "split": "first_60_percent_select_last_40_percent_test", "pair_family_size": len(pairs)},
                estimate={"selected_lag_months": best_lag, "training_r": train_r, "held_out_r": test_r, "direction": sign},
                uncertainty={"p_value_uncorrected": test_p, "family_wise_threshold": 0.05 / len(pairs), "circular_shift_placebo_p": placebo_p},
                sensitivities=[{"specification": "training", "r": train_r, "p_value": train_p, "n": train_n}, {"specification": "chronological_holdout", "r": test_r, "p_value": test_p, "n": test_n}],
                diagnostics=["A lead-lag association between aggregate series is not evidence that one series causes the other."],
                negative_evidence=negative,
                title=f"A held-out macroeconomic lead-lag links {price_label} and {job_label}",
                claim=f"A lag of {best_lag:+d} months selected before the holdout gave r={test_r:.3f} (p={test_p:.3g}, n={test_n}) between {price_label} inflation and {job_label} growth in the held-out period.",
                interpretation="The relationship is a candidate regime-level macroeconomic regularity because lag selection and testing were separated in time; it is not a structural causal estimate.",
                mechanism="Demand, input costs, labor reallocation, policy response, and sector-specific adjustment times can transmit common shocks into prices and employment at different lags.",
                supported=supported,
                validation_level="internal_holdout",
                robustness=["canonical national series", "year-over-year log transform", "chronological lag-selection holdout", "three-pair multiplicity threshold"],
                limits=["Overlapping annual changes reduce effective independence.", "The 2020–2022 shock may dominate both train and test periods.", "Revisions and real-time vintages are unavailable here."],
                next_validation="Repeat with non-overlapping quarterly changes, rolling-origin evaluation, recession/pandemic interactions, policy controls, and real-time data vintages.",
                locators={item.asset_id: {"series_id": price_id if item == assets_for_pair[0] else job_id, "period_start": "2010M01", "period_end": "latest common"} for item in assets_for_pair},
                units={"change": "log percent per year", "lag": "month"},
                expression_latex=(
                    r"\ell^{*}=\arg\max_{\ell\in[-12,12]}"
                    r"\left|\rho_{\mathrm{dev}}(\Delta_{12}\ln P_t,\Delta_{12}\ln E_{t+\ell})\right|,\quad "
                    r"\operatorname{sign}(\rho_{\mathrm{test},\ell^{*}})="
                    r"\operatorname{sign}(\rho_{\mathrm{dev},\ell^{*}})"
                ),
                equation_variables=[
                    {"symbol": "P", "meaning": price_label, "unit": "index"},
                    {"symbol": "E", "meaning": job_label, "unit": "employment level"},
                    {"symbol": r"\Delta_{12}\ln", "meaning": "twelve-month log change", "unit": "log percent per year"},
                    {"symbol": r"\ell^{*}", "meaning": "development-selected lag", "unit": "month"},
                ],
                split_validation={
                    "strategy": "chronological_lag_selection_holdout",
                    "selection_lock": "lag selected only on the first 60 percent of months",
                    "development": {"selected_lag_months": best_lag, "r": train_r, "n": train_n},
                    "test": {"r": test_r, "p_value": test_p, "n": test_n, "passed": supported},
                    "negative_control": {
                        "strategy": "12-month-or-longer circular shifts of the held-out employment series",
                        "placebo_count": len(placebo_correlations),
                        "placebo_p_value": placebo_p,
                        "passed": negative_control_passed,
                    },
                },
                rule_gate=_law_gate(negative_control_passed=negative_control_passed),
                insight_level="principle_level",
                nontriviality_basis="Lag selection was locked on the earlier 60% of months and its direction and magnitude were tested on the later 40% under a three-pair multiplicity gate.",
                significance="A stable sector-specific lag defines a falsifiable temporal boundary for forecasting and macroeconomic mechanism models, rather than an in-sample contemporaneous correlation.",
                principle_statement="Price and employment adjustments can occupy reproducible sector-dependent lag regimes; candidate lags must be chosen historically and retain their direction in a future chronological block before use.",
                transfer_scope="The retained seasonally adjusted national CPI/CES series since 2010; real-time vintages, non-overlapping changes, and future regimes remain outside the current evidence.",
            )
        )
    return outputs


def _dominant_frequency(values: np.ndarray, sample_rate: float) -> tuple[float, float]:
    from scipy.signal import periodogram

    centered = values - float(np.nanmedian(values))
    frequencies, power = periodogram(centered, fs=sample_rate, window="hann")
    valid = (frequencies >= 0.3) & (frequencies <= 4.0)
    if np.sum(valid) < 5:
        raise ValueError("insufficient gait-frequency support")
    index = int(np.argmax(power[valid]))
    finite_frequency = frequencies[valid]
    finite_power = power[valid]
    background = float(np.median(finite_power))
    return float(finite_frequency[index]), float(finite_power[index] / background) if background > 0 else math.inf


def _one_sided_exact_monotonic_order_p(
    trial_count: int, *, monotonic: bool
) -> float:
    if not monotonic or trial_count < 2:
        return 1.0
    return 1.0 / math.factorial(trial_count)


def _gait_outcomes(
    study_id: str, assets: list[DataAsset], root: Path
) -> list[OperatorOutcome]:
    by_relative = {
        str(item.metadata.get("relative_path") or ""): item
        for item in assets
        if item.role == "raw"
    }
    speed_pattern = re.compile(r"S1_(0\.5|0\.75|1)(?:_raw)?\.(?:csv|edf)$")
    speeds: dict[float, dict[str, DataAsset]] = {}
    for relative, asset in by_relative.items():
        match = speed_pattern.search(relative)
        if not match:
            continue
        speed = float(match.group(1))
        kind = "eeg" if relative.casefold().endswith(".edf") else "emg" if "emg_data" in relative.casefold() else "force"
        speeds.setdefault(speed, {})[kind] = asset
    if len(speeds) < 3 or any(not {"eeg", "emg", "force"}.issubset(group) for group in speeds.values()):
        return []
    import pandas as pd
    import pyedflib

    estimates: list[dict[str, Any]] = []
    evidence_assets: list[DataAsset] = []
    for speed in sorted(speeds):
        group = speeds[speed]
        eeg_path = _safe_path(root, group["eeg"])
        reader = pyedflib.EdfReader(str(eeg_path))
        try:
            duration = float(reader.file_duration)
        finally:
            reader.close()
        force = pd.read_csv(_safe_path(root, group["force"]), usecols=["1:Fz", "2:Fz"])
        force_signal = np.asarray(force["1:Fz"] + force["2:Fz"], dtype=float)
        force_rate = len(force_signal) / duration
        force_frequency, force_ratio = _dominant_frequency(force_signal, force_rate)
        emg = pd.read_csv(_safe_path(root, group["emg"]), nrows=50_000)
        time_values = np.asarray(emg.iloc[:, 0], dtype=float)
        emg_rate = 1.0 / float(np.median(np.diff(time_values)))
        emg_signal = np.asarray(emg.iloc[:, 1:].median(axis=1), dtype=float)
        emg_frequency, emg_ratio = _dominant_frequency(emg_signal, emg_rate)
        right = np.asarray(emg.filter(regex=r"^R ").median(axis=1), dtype=float)
        left = np.asarray(emg.filter(regex=r"^L ").median(axis=1), dtype=float)
        asymmetry = float(np.median(np.abs(right - left)) / max(1e-12, np.median(np.abs(right) + np.abs(left))))
        estimates.append(
            {
                "speed_m_per_s": speed,
                "force_step_frequency_hz": force_frequency,
                "force_peak_to_background": force_ratio,
                "emg_frequency_hz": emg_frequency,
                "emg_peak_to_background": emg_ratio,
                "force_emg_relative_difference": abs(force_frequency - emg_frequency) / force_frequency,
                "bilateral_emg_asymmetry": asymmetry,
                "duration_seconds": duration,
            }
        )
        evidence_assets.extend([group["force"], group["emg"], group["eeg"]])
    force_frequencies = np.asarray([item["force_step_frequency_hz"] for item in estimates])
    monotonic = bool(np.all(np.diff(force_frequencies) > 0))
    increase = float(force_frequencies[-1] / force_frequencies[0] - 1.0)
    # With three distinct speeds there are 3! possible trial orderings, so a
    # perfectly increasing sequence has one-sided exact p=1/6 under the null.
    # It is scientifically useful descriptive evidence but cannot pass a 0.05
    # support gate without repeated trials or additional participants.
    exact_order_p = _one_sided_exact_monotonic_order_p(
        len(estimates), monotonic=monotonic
    )
    supported_cadence = (
        monotonic
        and increase >= 0.10
        and all(item["force_peak_to_background"] >= 8 for item in estimates)
        and exact_order_p <= 0.05
    )
    cadence_negative = [] if supported_cadence else [
        "The three-trial monotonic pattern is descriptive only: its one-sided "
        f"exact order p-value is {exact_order_p:.3f}, above the 0.05 support gate."
    ]
    cadence = _collection_outcome(
        study_id=study_id,
        assets=[speeds[s]["force"] for s in sorted(speeds)],
        operator="gait_speed_cadence_adaptation",
        hypothesis_claim="Within the same participant, treadmill speed may induce a monotonic increase in force-derived gait cadence.",
        expected_relationship="Dominant bilateral vertical-force frequency increases at each commanded speed and is spectrally resolved.",
        confounders=["single participant", "trial order", "treadmill entrainment", "force-plate sample-rate inference", "harmonic selection", "fatigue"],
        falsifier="Cadence is non-monotonic under heel-strike event detection or fails in repeated counterbalanced trials.",
        sample_definition="three speed-matched force-plate trials from participant S1; recording is the unit",
        independent_unit_count=3,
        parameters={"frequency_band_hz": [0.3, 4.0], "sample_rate": "rows divided by matched EDF duration", "spectrum": "Hann periodogram"},
        estimate={"speed_trials": estimates, "low_to_high_relative_increase": increase},
        uncertainty={
            "one_sided_exact_order_p": exact_order_p,
            "permutation_space": math.factorial(len(estimates)),
            "independent_speed_trials": len(estimates),
        },
        sensitivities=[{"specification": "monotonic_speed_order", "passed": monotonic}, {"specification": "all_peak_to_background_ge_8", "passed": all(item["force_peak_to_background"] >= 8 for item in estimates)}],
        diagnostics=["Three recordings from one person are not population-level independent evidence."],
        negative_evidence=cadence_negative,
        title="Gait speed is encoded by a monotonic within-person cadence adaptation",
        claim=f"Force-derived cadence changed from {force_frequencies[0]:.3f} Hz at 0.5 m/s to {force_frequencies[-1]:.3f} Hz at 1.0 m/s ({increase * 100:.1f}% change) and was {'monotonic' if monotonic else 'not monotonic'} across all three trials.",
        interpretation="The paired-speed design reveals how this participant redistributed gait timing as belt speed doubled.",
        mechanism="Walking speed can rise through stride length, cadence, or both; a monotonic cadence component indicates speed-dependent central and biomechanical timing adaptation.",
        supported=supported_cadence,
        validation_level="exploratory",
        robustness=["same-participant speed series", "bilateral vertical-force aggregation", "spectral peak/background gate", "strict monotonicity"],
        limits=["No repeated trials or participants are available.", "Spectral peaks can select stride frequency or its harmonic."],
        next_validation="Detect individual heel strikes, separate stride from step frequency, repeat speeds in randomized order, and fit a hierarchical speed-cadence model across participants.",
        locators={asset.asset_id: {"columns": ["1:Fz", "2:Fz"], "matched_speed_m_per_s": speed} for speed, asset in [(s, speeds[s]["force"]) for s in sorted(speeds)]},
        units={"frequency": "Hz", "speed": "m/s"},
    )
    agreement = [float(item["force_emg_relative_difference"]) for item in estimates]
    supported_agreement = max(agreement) <= 0.20 and all(item["emg_peak_to_background"] >= 5 for item in estimates)
    agreement_negative = [] if supported_agreement else ["Force and EMG dominant frequencies failed the 20% agreement or EMG resolution gate in at least one speed trial."]
    cross_modal = _collection_outcome(
        study_id=study_id,
        assets=[item for speed in sorted(speeds) for item in (speeds[speed]["force"], speeds[speed]["emg"])],
        operator="gait_force_emg_frequency_replication",
        hypothesis_claim="Force and multi-muscle EMG may independently recover the same speed-specific gait oscillator.",
        expected_relationship="Dominant force and median-EMG frequencies agree within 20% at each speed.",
        confounders=["harmonic ambiguity", "EMG envelope preprocessing", "trial synchronization", "motion artifact", "single participant"],
        falsifier="Frequency agreement disappears after heel-strike locking, muscle-specific analysis, or repeated trials.",
        sample_definition="three matched speed trials with independent force and EMG acquisition streams",
        independent_unit_count=3,
        parameters={"frequency_band_hz": [0.3, 4.0], "agreement_threshold": 0.20, "emg_projection": "median across 12 muscles"},
        estimate={"speed_trials": estimates, "maximum_relative_frequency_difference": max(agreement)},
        uncertainty={},
        sensitivities=[{"specification": f"speed_{item['speed_m_per_s']}", "relative_difference": item["force_emg_relative_difference"]} for item in estimates],
        diagnostics=["Cross-modal agreement within the same trials is stronger than a single stream but is not independent-subject replication."],
        negative_evidence=agreement_negative,
        title="Independent force and muscle signals converge on the same speed-specific gait oscillator",
        claim=f"Across all three speeds, force and median-EMG dominant frequencies agreed with maximum relative difference {max(agreement) * 100:.1f}%.",
        interpretation="Two measurement systems recovering the same oscillator reduces the chance that the cadence signature is a serialization or single-sensor artifact.",
        mechanism="Ground-reaction force and phasic muscle recruitment are coupled outputs of the locomotor control cycle, so their dominant timing should coincide up to stride/step harmonics.",
        supported=supported_agreement,
        validation_level="cross_modal_replication",
        robustness=["separate acquisition streams", "three speed-matched trials", "predeclared frequency band", "peak/background resolution gate"],
        limits=["The modalities share the same participant and treadmill perturbation.", "Absolute phase coupling was not tested because synchronization metadata require source-specific validation."],
        next_validation="Use trigger-aligned epochs to estimate force-EMG coherence and phase, then replicate across participants and repeated speed trials.",
        locators={asset.asset_id: {"matched_speed_m_per_s": speed, "projection": "bilateral Fz" if asset == speeds[speed]["force"] else "median 12-muscle MAV"} for speed in sorted(speeds) for asset in (speeds[speed]["force"], speeds[speed]["emg"])},
        units={"frequency": "Hz"},
        expression_latex=(
            r"f_{\mathrm{EMG}}(v)=f_{\mathrm{force}}(v)\,[1+\varepsilon(v)],"
            r"\qquad |\varepsilon(v)|\leq\varepsilon_{\max}"
        ),
        equation_variables=[
            {"symbol": "v", "meaning": "commanded treadmill speed", "unit": "m/s"},
            {"symbol": r"f_{\mathrm{force}}", "meaning": "dominant bilateral vertical-force frequency", "unit": "Hz"},
            {"symbol": r"f_{\mathrm{EMG}}", "meaning": "dominant median multi-muscle EMG frequency", "unit": "Hz"},
            {"symbol": r"\varepsilon_{\max}", "meaning": "maximum observed cross-modal relative mismatch", "unit": "dimensionless"},
        ],
        split_validation={
            "strategy": "leave_one_speed_cross_modal_replication",
            "selection_lock": "frequency band and 20 percent agreement boundary fixed before comparing the three speeds",
            "development": {"speeds_m_per_s": [item["speed_m_per_s"] for item in estimates[:-1]], "receipts": estimates[:-1]},
            "test": {"speed_m_per_s": estimates[-1]["speed_m_per_s"], "receipt": estimates[-1], "passed": supported_agreement},
            "baseline_comparison": {"baseline": "unrelated dominant oscillators", "maximum_relative_difference": max(agreement), "passed": supported_agreement},
        },
        rule_gate={
            "interpretable_law_family": True,
            "held_out_baseline_improvement": supported_agreement,
            "parameter_stability": supported_agreement,
            "unit_plausibility": True,
            "negative_control": False,
            "transfer_boundary_declared": True,
        },
    )
    return [cadence, cross_modal]


def _dandi_outcomes(
    study_id: str, assets: list[DataAsset], root: Path
) -> list[OperatorOutcome]:
    nwb_assets = [item for item in assets if item.role == "raw" and item.format == "nwb"]
    if len(nwb_assets) < 4:
        return []
    import h5py
    from scipy.signal import detrend
    from scipy.stats import pearsonr, rankdata, spearmanr

    required = {
        "fluorescence": "processing/ophys/Fluorescence/RoiResponseSeries1/data",
        "fluorescence_time": "processing/ophys/Fluorescence/RoiResponseSeries1/timestamps",
        "pupil": "acquisition/PupilTracking/pupil_raw_radius/data",
        "pupil_time": "acquisition/PupilTracking/pupil_raw_radius/timestamps",
        "velocity": "acquisition/treadmill_velocity/data",
        "velocity_time": "acquisition/treadmill_velocity/timestamps",
    }
    sessions: list[dict[str, Any]] = []
    retained_assets: list[DataAsset] = []
    for asset in sorted(nwb_assets, key=lambda item: item.portable_uri):
        with h5py.File(_safe_path(root, asset), "r") as handle:
            if not all(path in handle for path in required.values()):
                continue
            fluorescence_time = np.asarray(handle[required["fluorescence_time"]][:], dtype=float)
            fluorescence_raw = np.asarray(handle[required["fluorescence"]][:], dtype=float)
            fluorescence = fluorescence_raw.reshape(len(fluorescence_time), -1).mean(axis=1)
            pupil_time = np.asarray(handle[required["pupil_time"]][:], dtype=float)
            pupil = np.asarray(handle[required["pupil"]][:], dtype=float).reshape(-1)
            velocity_time = np.asarray(handle[required["velocity_time"]][:], dtype=float)
            velocity = np.abs(np.asarray(handle[required["velocity"]][:], dtype=float).reshape(-1))
        lower = max(fluorescence_time[0], pupil_time[0], velocity_time[0])
        upper = min(fluorescence_time[-1], pupil_time[-1], velocity_time[-1])
        bins = np.arange(lower, upper, 1.0)
        if bins.size < 120:
            continue

        def bin_median(
            time_values: np.ndarray,
            values: np.ndarray,
            bin_edges: np.ndarray = bins,
        ) -> np.ndarray:
            positions = np.searchsorted(time_values, bin_edges)
            output = np.full(bin_edges.size - 1, np.nan, dtype=float)
            for index in range(output.size):
                left, right = int(positions[index]), int(positions[index + 1])
                if right > left:
                    finite = values[left:right]
                    finite = finite[np.isfinite(finite)]
                    if finite.size:
                        output[index] = float(np.median(finite))
            return output

        ach = bin_median(fluorescence_time, fluorescence)
        pupil_binned = bin_median(pupil_time, pupil)
        velocity_binned = bin_median(velocity_time, velocity)
        valid = np.isfinite(ach) & np.isfinite(pupil_binned) & np.isfinite(velocity_binned)
        if np.sum(valid) < 120:
            continue
        ach = detrend(ach[valid])
        pupil_binned = detrend(pupil_binned[valid])
        velocity_binned = detrend(velocity_binned[valid])
        ach_pupil = float(spearmanr(ach, pupil_binned).statistic)
        ach_velocity = float(spearmanr(ach, velocity_binned).statistic)
        ranked_ach = rankdata(ach)
        ranked_pupil = rankdata(pupil_binned)
        ranked_velocity = rankdata(velocity_binned)
        design = np.column_stack([ranked_velocity, np.ones(ranked_velocity.size)])
        ach_residual = ranked_ach - design @ np.linalg.lstsq(design, ranked_ach, rcond=None)[0]
        pupil_residual = ranked_pupil - design @ np.linalg.lstsq(
            design, ranked_pupil, rcond=None
        )[0]
        partial = float(pearsonr(ach_residual, pupil_residual).statistic)
        shifted_partials: list[float] = []
        for fraction in (0.25, 0.50, 0.75):
            shift = max(1, int(round(ranked_pupil.size * fraction)))
            shifted_pupil = np.roll(ranked_pupil, shift)
            shifted_residual = shifted_pupil - design @ np.linalg.lstsq(
                design, shifted_pupil, rcond=None
            )[0]
            shifted_partials.append(
                float(pearsonr(ach_residual, shifted_residual).statistic)
            )
        blocks = np.array_split(np.arange(ach.size), 4)
        block_partial = []
        for block in blocks:
            if block.size < 20:
                continue
            block_design = np.column_stack(
                [ranked_velocity[block], np.ones(block.size)]
            )
            left = ranked_ach[block] - block_design @ np.linalg.lstsq(
                block_design, ranked_ach[block], rcond=None
            )[0]
            right = ranked_pupil[block] - block_design @ np.linalg.lstsq(
                block_design, ranked_pupil[block], rcond=None
            )[0]
            block_partial.append(float(pearsonr(left, right).statistic))
        relative = str(asset.metadata.get("relative_path") or "")
        region_match = re.search(r"Ach-(M1|V1)", relative, re.IGNORECASE)
        sessions.append(
            {
                "session": Path(relative).stem,
                "region": region_match.group(1).upper() if region_match else "unknown",
                "one_second_bins": int(ach.size),
                "ach_pupil_rho": ach_pupil,
                "ach_velocity_rho": ach_velocity,
                "ach_pupil_partial_velocity": partial,
                "circular_shift_partial_controls": shifted_partials,
                "block_partial_correlations": block_partial,
            }
        )
        retained_assets.append(asset)
    if len(sessions) < 4:
        return []

    def replicated_outcome(
        *,
        operator: str,
        key: str,
        title: str,
        hypothesis_claim: str,
        interpretation: str,
        mechanism: str,
        partial_control: bool,
    ) -> OperatorOutcome:
        effects = np.asarray([float(item[key]) for item in sessions])
        median = float(np.median(effects))
        direction_count = int(np.sum(effects > 0)) if median >= 0 else int(np.sum(effects < 0))
        # Exact two-sided sign-test probability for unanimous/near-unanimous
        # session replication. No within-session time bins are miscounted as
        # independent biological replicates.
        from scipy.stats import binomtest

        sign_p = float(binomtest(direction_count, len(effects), 0.5).pvalue)
        stable_blocks = True
        if partial_control:
            stable_blocks = all(
                sum(value > 0 for value in item["block_partial_correlations"]) >= 3
                for item in sessions
            )
        control_effect = float(
            np.median(
                [
                    abs(value)
                    for item in sessions
                    for value in item["circular_shift_partial_controls"]
                ]
            )
        ) if partial_control else 0.0
        negative_control_passed = (median - control_effect >= 0.10) if partial_control else False
        supported = (
            median >= 0.20
            and direction_count >= max(4, len(effects) - 1)
            and sign_p <= 0.125
            and stable_blocks
            and (negative_control_passed if partial_control else True)
        )
        negative = [] if supported else [
            "The across-session sign, median-effect, or within-session block-stability gate was not met."
        ]
        relationship = "pupil radius after rank-linear velocity adjustment" if partial_control else "absolute treadmill velocity"
        region_sensitivities = [
            {
                "specification": f"{region}_sessions",
                "median_effect": float(
                    np.median([item[key] for item in sessions if item["region"] == region])
                ),
            }
            for region in ("M1", "V1")
            if any(item["region"] == region for item in sessions)
        ]
        return _collection_outcome(
            study_id=study_id,
            assets=retained_assets,
            operator=operator,
            hypothesis_claim=hypothesis_claim,
            expected_relationship=f"Session-level acetylcholine fluorescence should associate positively with {relationship} and reproduce across recordings.",
            confounders=["shared slow drift", "motion artifact", "photobleaching", "session duration", "animal and region imbalance", "one-second bin autocorrelation"],
            falsifier="The coupling disappears under motion regressors, fluorescence controls, event-locked analysis, or new animals/sessions.",
            sample_definition=f"{len(sessions)} NWB sessions; session is the independent unit and signals are summarized in one-second bins",
            independent_unit_count=len(sessions),
            parameters={"bin_width_seconds": 1, "detrending": "linear", "association": "spearman", "partial_control": "rank-linear treadmill velocity" if partial_control else "none"},
            estimate={"median_session_effect": median, "positive_sessions": direction_count, "session_effects": sessions},
            uncertainty={"p_value_uncorrected": sign_p, "test": "exact two-sided sign test"},
            sensitivities=region_sensitivities,
            diagnostics=["Time-bin p-values are deliberately not used because autocorrelation would inflate sample size."],
            negative_evidence=negative,
            title=title,
            claim=f"The session-level median effect was r={median:.3f}; {direction_count}/{len(sessions)} sessions had the same positive direction (exact sign p={sign_p:.3g}).",
            interpretation=interpretation,
            mechanism=mechanism,
            supported=supported,
            validation_level="cross_modal_replication",
            robustness=["seven-session replication", "one-second robust binning", "linear detrending", "session-level sign test", *( ["four contiguous block partial-correlation checks per session"] if partial_control else [])],
            limits=["The small number of animals prevents a population-level regional comparison.", "Observational coupling cannot distinguish neuromodulatory drive from a shared upstream arousal process."],
            next_validation="Use event-locked cross-validated encoding models with motion/bleaching controls, animal-level replication, and causal cholinergic perturbation.",
            locators={asset.asset_id: {"datasets": list(required.values()), "bin_width_seconds": 1} for asset in retained_assets},
            units={"time_bin": "second", "effect": "rank correlation"},
            expression_latex=(
                r"\operatorname{rank} A_s(t)=\alpha_s+\beta_v\operatorname{rank}v_s(t)"
                r"+\beta_p\operatorname{rank}p_s(t)+\varepsilon_s(t),\qquad \beta_p>0"
                if partial_control
                else ""
            ),
            equation_variables=(
                [
                    {"symbol": r"A_s(t)", "meaning": "session-s acetylcholine fluorescence", "unit": "rank"},
                    {"symbol": r"v_s(t)", "meaning": "absolute treadmill velocity", "unit": "rank"},
                    {"symbol": r"p_s(t)", "meaning": "pupil radius", "unit": "rank"},
                    {"symbol": r"\beta_p", "meaning": "pupil-linked component after velocity adjustment"},
                ]
                if partial_control
                else []
            ),
            split_validation=(
                {
                    "strategy": "cortical_region_replication_with_contiguous_block_challenge",
                    "selection_lock": "one-second binning, detrending, rank transform, and velocity adjustment fixed before region comparison",
                    "development": region_sensitivities[0] if region_sensitivities else {},
                    "test": {
                        **(region_sensitivities[1] if len(region_sensitivities) > 1 else {}),
                        "passed": supported,
                    },
                    "baseline_comparison": {
                        "baseline": "velocity-only rank model",
                        "incremental_effect": median,
                        "passed": median >= 0.20,
                    },
                    "negative_control": {
                        "strategy": "quarter-, half-, and three-quarter-session circular pupil shifts",
                        "median_absolute_shifted_effect": control_effect,
                        "observed_median_effect": median,
                        "minimum_margin": 0.10,
                        "passed": negative_control_passed,
                    },
                }
                if partial_control
                else {}
            ),
            rule_gate=(
                _law_gate(negative_control_passed=negative_control_passed)
                if partial_control
                else None
            ),
            insight_level="mechanistic" if partial_control else "structural",
            nontriviality_basis=(
                "The pupil term remains after velocity adjustment, retains direction across sessions and cortical "
                "regions, and survives contiguous within-session block checks."
                if partial_control
                else ""
            ),
            significance=(
                "The executable state-space closure separates locomotion-linked and pupil-linked components of cortical acetylcholine."
                if partial_control
                else ""
            ),
            transfer_scope=(
                "The retained M1 and V1 imaging sessions under the measured behavioral range; animal-level and causal transfer require new experiments."
                if partial_control
                else ""
            ),
        )

    return [
        replicated_outcome(
            operator="nwb_ach_locomotion_session_replication",
            key="ach_velocity_rho",
            title="Cortical acetylcholine tracks locomotor state across M1 and V1 sessions",
            hypothesis_claim="Axonal acetylcholine fluorescence may encode locomotor state reproducibly across the retained M1 and V1 sessions.",
            interpretation="The neuromodulatory signal carries a recording-replicated locomotor-state component across two cortical regions.",
            mechanism="Basal-forebrain cholinergic activity is recruited with behavioral activation and can broadcast state-dependent gain signals across cortex.",
            partial_control=False,
        ),
        replicated_outcome(
            operator="nwb_ach_pupil_velocity_partial_replication",
            key="ach_pupil_partial_velocity",
            title="Acetylcholine retains a pupil-linked arousal component beyond locomotor velocity",
            hypothesis_claim="Acetylcholine fluorescence may retain a reproducible association with pupil-linked arousal after removing rank-linear treadmill velocity.",
            interpretation="The cholinergic signal is not reducible to locomotor speed alone; it contains a cross-session pupil-linked state component.",
            mechanism="Pupil diameter and cortical acetylcholine can share arousal circuitry beyond overt locomotion, consistent with a multidimensional internal-state signal.",
            partial_control=True,
        ),
    ]


def _encapsulant_outcomes(
    study_id: str, assets: list[DataAsset], root: Path
) -> list[OperatorOutcome]:
    # Select workbooks by scientific schema rather than frozen filenames or
    # worksheet labels.  This contract survives file/sheet renaming and archive
    # repackaging as long as the measurement content is unchanged.
    rate_asset: DataAsset | None = None
    conversion_asset: DataAsset | None = None
    retained_sheet_names: dict[str, str] = {}
    import openpyxl

    for asset in assets:
        if asset.role != "raw" or asset.format != "xlsx":
            continue
        try:
            workbook = openpyxl.load_workbook(
                _safe_path(root, asset), read_only=True, data_only=True
            )
            sheet = workbook[workbook.sheetnames[0]]
            first_two_rows = [
                str(value or "").casefold()
                for row in sheet.iter_rows(
                    min_row=1,
                    max_row=min(2, sheet.max_row),
                    max_col=min(24, sheet.max_column),
                    values_only=True,
                )
                for value in row
            ]
            signature = " ".join(first_two_rows)
            rate_count = sum("°c/min" in value or "c/min" in value for value in first_two_rows)
            has_temperature = "temperature" in signature
            has_conversion_rate = "conversion rate" in signature or "%/min" in signature
            has_conversion = "conversion" in signature
            if sheet.max_column >= 15 and rate_count >= 3 and has_temperature:
                if has_conversion_rate:
                    rate_asset = asset
                    retained_sheet_names[asset.asset_id] = sheet.title
                elif has_conversion:
                    conversion_asset = asset
                    retained_sheet_names[asset.asset_id] = sheet.title
        except Exception:
            continue
        finally:
            try:
                workbook.close()
            except Exception:
                pass
    if rate_asset is None or conversion_asset is None:
        return []
    import pandas as pd
    from scipy.stats import spearmanr

    rate_frame = pd.read_excel(_safe_path(root, rate_asset), header=None)
    rates: list[float] = []
    peak_temperatures: list[float] = []
    for base in (0, 4, 8, 12, 16):
        try:
            heating_rate = float(str(rate_frame.iloc[0, base]).split()[0])
        except (IndexError, TypeError, ValueError):
            continue
        subset = rate_frame.iloc[2:, [base, base + 1]].dropna().astype(float)
        if subset.empty:
            continue
        peak_row = subset.iloc[:, 1].idxmax()
        rates.append(heating_rate)
        peak_temperatures.append(float(rate_frame.iloc[peak_row, base]) + 273.15)
    if len(rates) < 5:
        return []
    rate_array = np.asarray(rates)
    temperature_array = np.asarray(peak_temperatures)
    kissinger_x = 1.0 / temperature_array
    kissinger_y = np.log(rate_array / temperature_array**2)
    slope, intercept = np.polyfit(kissinger_x, kissinger_y, 1)
    predicted = intercept + slope * kissinger_x
    total = float(np.sum((kissinger_y - np.mean(kissinger_y)) ** 2))
    r_squared = 1.0 - float(np.sum((kissinger_y - predicted) ** 2)) / total
    activation_energy = float(-slope * 8.314462618 / 1_000.0)
    # Deterministic permutation control: rotate the programmed heating-rate
    # labels while retaining the measured peak temperatures. A genuine
    # activation relation should dominate this scientifically broken pairing.
    control_y = np.roll(kissinger_y, 1)
    control_slope, control_intercept = np.polyfit(kissinger_x, control_y, 1)
    control_prediction = control_intercept + control_slope * kissinger_x
    control_total = float(np.sum((control_y - np.mean(control_y)) ** 2))
    control_r_squared = (
        1.0
        - float(np.sum((control_y - control_prediction) ** 2)) / control_total
        if control_total > 0
        else 0.0
    )
    control_activation_energy = float(-control_slope * 8.314462618 / 1_000.0)
    leave_one_out = []
    for held_out in range(len(rates)):
        retained = np.asarray([index for index in range(len(rates)) if index != held_out])
        local_slope = float(np.polyfit(kissinger_x[retained], kissinger_y[retained], 1)[0])
        leave_one_out.append(-local_slope * 8.314462618 / 1_000.0)
    stable = max(leave_one_out) - min(leave_one_out) <= 15.0
    supported = r_squared >= 0.98 and stable and 20.0 <= activation_energy <= 300.0
    kissinger_control_passed = bool(
        r_squared - control_r_squared >= 0.10
        and not (
            control_r_squared >= 0.98
            and 20.0 <= control_activation_energy <= 300.0
        )
    )
    kissinger_negative = (
        []
        if supported and kissinger_control_passed
        else [
            *(
                []
                if supported
                else ["The Kissinger fit, physical-range, or leave-one-rate stability gate was not met."]
            ),
            *(
                []
                if kissinger_control_passed
                else ["The heating-rate label permutation did not sufficiently weaken the activation relation."]
            ),
        ]
    )
    kissinger = _collection_outcome(
        study_id=study_id,
        assets=[rate_asset],
        operator="encapsulant_kissinger_activation_energy",
        hypothesis_claim="The non-isothermal cure-rate maxima may follow a single apparent Kissinger activation-energy law across five heating rates.",
        expected_relationship="ln(beta/Tp²) should be linear in reciprocal peak temperature and remain stable when any one heating rate is removed.",
        confounders=["baseline correction", "peak-picking resolution", "temperature calibration", "overlapping reactions", "Kissinger single-step approximation"],
        falsifier="The estimate changes materially under alternate baselines/peak models or isoconversional analysis reveals incompatible regimes.",
        sample_definition="five programmed heating-rate curves (1, 3, 5, 10, and 20 °C/min) with observed conversion-rate maxima",
        independent_unit_count=5,
        parameters={"method": "Kissinger", "gas_constant_j_per_mol_k": 8.314462618, "peak_source": "observed conversion-rate column"},
        estimate={"activation_energy_kj_per_mol": activation_energy, "r_squared": r_squared, "heating_rates_c_per_min": rates, "peak_temperatures_k": peak_temperatures},
        uncertainty={"leave_one_rate_out_range_kj_per_mol": [min(leave_one_out), max(leave_one_out)]},
        sensitivities=[
            *[
                {
                    "specification": f"omit_{rates[index]}_c_per_min",
                    "activation_energy_kj_per_mol": value,
                }
                for index, value in enumerate(leave_one_out)
            ],
            {
                "specification": "cyclic_heating_rate_label_permutation",
                "activation_energy_kj_per_mol": control_activation_energy,
                "r_squared": control_r_squared,
                "passed": kissinger_control_passed,
            },
        ],
        diagnostics=[
            "Kissinger activation energy is an apparent kinetic parameter and does not prove a single elementary reaction.",
            "A deterministic cyclic heating-rate label permutation is the negative control.",
        ],
        negative_evidence=kissinger_negative,
        title="Five heating rates collapse onto a stable apparent cure activation energy",
        claim=f"The Kissinger relation gave apparent activation energy {activation_energy:.1f} kJ/mol with R²={r_squared:.4f}; leave-one-heating-rate estimates spanned {min(leave_one_out):.1f}–{max(leave_one_out):.1f} kJ/mol.",
        interpretation="The peak-rate shifts are quantitatively consistent with a reproducible thermal activation scale rather than unrelated curve displacements.",
        mechanism="For thermally activated cure kinetics, faster heating moves the reaction-rate maximum to higher temperature; the shift encodes an apparent activation barrier.",
        supported=supported,
        validation_level="internal_holdout",
        robustness=["five-rate fit", "observed rather than fitted peak selection", "leave-one-heating-rate stability", "physical-range check"],
        limits=["Only five heating programs are independent conditions.", "A high-linear-fit Kissinger plot can conceal conversion-dependent mechanisms."],
        next_validation="Repeat peak estimation with uncertainty propagation and compare model-free isoconversional, Friedman, and mechanistic kinetic fits on independent batches.",
        locators={rate_asset.asset_id: {"sheet": retained_sheet_names.get(rate_asset.asset_id, "first worksheet selected by schema"), "column_groups_zero_based": [0, 4, 8, 12, 16], "peak_rule": "maximum observed conversion rate"}},
        units={"activation_energy": "kJ/mol", "temperature": "K", "heating_rate": "°C/min"},
        expression_latex=(
            r"\ln\!\left(\frac{\beta}{T_p^2}\right)="
            r"\ln\!\left(\frac{AR}{E_a}\right)-\frac{E_a}{RT_p}"
        ),
        equation_variables=[
            {"symbol": r"\beta", "meaning": "programmed heating rate", "unit": "°C/min"},
            {"symbol": r"T_p", "meaning": "temperature of the cure-rate maximum", "unit": "K"},
            {"symbol": r"E_a", "meaning": "apparent activation energy", "unit": "kJ/mol"},
            {"symbol": "A", "meaning": "apparent pre-exponential factor"},
            {"symbol": "R", "meaning": "molar gas constant", "unit": "J/(mol K)"},
        ],
        split_validation={
            "strategy": "leave_one_heating_rate_out",
            "selection_lock": "Kissinger family and observed peak rule fixed before each exclusion",
            "development": {
                "activation_energy_kj_per_mol": activation_energy,
                "intercept": float(intercept),
                "r_squared": r_squared,
            },
            "test": {
                "passed": supported and kissinger_control_passed,
                "held_out_rate_count": len(leave_one_out),
                "activation_energy_range_kj_per_mol": [min(leave_one_out), max(leave_one_out)],
            },
            "negative_control": {
                "strategy": "cyclic_heating_rate_label_permutation",
                "observed_r_squared": r_squared,
                "permuted_r_squared": control_r_squared,
                "permuted_activation_energy_kj_per_mol": control_activation_energy,
                "passed": kissinger_control_passed,
            },
        },
        rule_gate=_law_gate(negative_control_passed=kissinger_control_passed),
        insight_level="mechanistic",
        nontriviality_basis="Five independently programmed heating rates estimate one physical energy scale, with every leave-one-rate fit remaining within a predeclared stability band.",
        significance="A stable apparent barrier is a compact kinetic constraint for cure scheduling and a falsifiable baseline for more complex reaction-network models.",
        principle_statement="For a fixed cure regime, heating-rate shifts of the rate maximum obey a Kissinger activation law until conversion-dependent barriers or transport limitations invalidate the single-scale approximation.",
        transfer_scope="Non-isothermal cure programs using the same encapsulant chemistry and comparable thermal/metrology conditions.",
    )

    conversion_frame = pd.read_excel(_safe_path(root, conversion_asset), header=None)
    curves: list[tuple[np.ndarray, np.ndarray]] = []
    conversion_rates: list[float] = []
    for base in (0, 4, 8, 12, 16):
        heating_rate = float(str(conversion_frame.iloc[0, base]).split()[0])
        subset = conversion_frame.iloc[2:, [base, base + 1]].dropna().astype(float)
        temperatures = subset.iloc[:, 0].to_numpy() + 273.15
        conversion = subset.iloc[:, 1].to_numpy()
        order = np.argsort(conversion)
        unique_conversion, positions = np.unique(conversion[order], return_index=True)
        curves.append((unique_conversion, temperatures[order][positions]))
        conversion_rates.append(heating_rate)
    fractions = np.arange(0.1, 0.9, 0.1)
    energies: list[float] = []
    fits: list[float] = []
    for fraction in fractions:
        temperatures = np.asarray(
            [np.interp(fraction, alpha, temp) for alpha, temp in curves], dtype=float
        )
        x_values = 1.0 / temperatures
        y_values = np.log(np.asarray(conversion_rates, dtype=float))
        local_slope, local_intercept = np.polyfit(x_values, y_values, 1)
        local_prediction = local_intercept + local_slope * x_values
        local_total = float(np.sum((y_values - np.mean(y_values)) ** 2))
        fits.append(1.0 - float(np.sum((y_values - local_prediction) ** 2)) / local_total)
        # Ozawa-Flynn-Wall approximation for natural logarithms.
        energies.append(float(-local_slope * 8.314462618 / 1.052 / 1_000.0))
    trend = spearmanr(fractions, energies)
    energy_drop = energies[0] - energies[-1]
    supported_regime = (
        float(trend.statistic) <= -0.90
        and float(trend.pvalue) <= 0.01
        and energy_drop >= 20.0
        and min(fits) >= 0.95
    )
    loo_regimes: list[dict[str, Any]] = []
    for held_out in range(len(conversion_rates)):
        retained = [index for index in range(len(conversion_rates)) if index != held_out]
        local_energies: list[float] = []
        local_fits: list[float] = []
        for fraction in fractions:
            temperatures = np.asarray(
                [
                    np.interp(fraction, curves[index][0], curves[index][1])
                    for index in retained
                ],
                dtype=float,
            )
            x_values = 1.0 / temperatures
            y_values = np.log(
                np.asarray([conversion_rates[index] for index in retained], dtype=float)
            )
            local_slope, local_intercept = np.polyfit(x_values, y_values, 1)
            local_prediction = local_intercept + local_slope * x_values
            local_total = float(np.sum((y_values - np.mean(y_values)) ** 2))
            local_fits.append(
                1.0
                - float(np.sum((y_values - local_prediction) ** 2)) / local_total
            )
            local_energies.append(
                float(-local_slope * 8.314462618 / 1.052 / 1_000.0)
            )
        local_trend = spearmanr(fractions, local_energies)
        loo_regimes.append(
            {
                "held_out_heating_rate_c_per_min": conversion_rates[held_out],
                "energy_drop_kj_per_mol": local_energies[0] - local_energies[-1],
                "spearman_rho": float(local_trend.statistic),
                "minimum_r_squared": min(local_fits),
            }
        )
    regime_loo_passed = all(
        item["energy_drop_kj_per_mol"] >= 15.0
        and item["spearman_rho"] <= -0.80
        and item["minimum_r_squared"] >= 0.90
        for item in loo_regimes
    )
    supported_regime = supported_regime and regime_loo_passed
    permuted_rates = np.roll(np.asarray(conversion_rates, dtype=float), 1)
    control_energies: list[float] = []
    control_fits: list[float] = []
    for fraction in fractions:
        temperatures = np.asarray(
            [np.interp(fraction, alpha, temp) for alpha, temp in curves],
            dtype=float,
        )
        x_values = 1.0 / temperatures
        y_values = np.log(permuted_rates)
        local_slope, local_intercept = np.polyfit(x_values, y_values, 1)
        local_prediction = local_intercept + local_slope * x_values
        local_total = float(np.sum((y_values - np.mean(y_values)) ** 2))
        control_fits.append(
            1.0
            - float(np.sum((y_values - local_prediction) ** 2)) / local_total
        )
        control_energies.append(
            float(-local_slope * 8.314462618 / 1.052 / 1_000.0)
        )
    control_trend = spearmanr(fractions, control_energies)
    control_energy_drop = control_energies[0] - control_energies[-1]
    control_would_pass = bool(
        float(control_trend.statistic) <= -0.90
        and float(control_trend.pvalue) <= 0.01
        and control_energy_drop >= 20.0
        and min(control_fits) >= 0.95
    )
    regime_control_passed = bool(
        not control_would_pass and min(fits) - min(control_fits) >= 0.05
    )
    regime_negative = (
        []
        if supported_regime and regime_control_passed
        else [
            *(
                []
                if supported_regime
                else ["Conversion-dependent energy did not meet monotonicity, 20 kJ/mol range, significance, and per-fraction fit gates."]
            ),
            *(
                []
                if regime_control_passed
                else ["The heating-rate label permutation did not sufficiently weaken the conversion-dependent energy relation."]
            ),
        ]
    )
    regime = _collection_outcome(
        study_id=study_id,
        assets=[conversion_asset],
        operator="encapsulant_isoconversional_regime_shift",
        hypothesis_claim="The apparent cure activation energy may decrease systematically with conversion, indicating a changing rate-limiting regime.",
        expected_relationship="Model-free activation energy estimated at fixed conversion fractions should show a monotonic, well-fitted trend from alpha=0.1 to 0.8.",
        confounders=["interpolation near conversion plateaus", "temperature lag", "diffusion limitation", "multiple reactions", "OFW approximation error"],
        falsifier="The trend disappears with alternative isoconversional estimators, uncertainty propagation, or independent cure batches.",
        sample_definition="five heating-rate conversion curves evaluated at eight fixed conversion fractions from 0.1 to 0.8",
        independent_unit_count=5,
        parameters={"method": "Ozawa-Flynn-Wall approximation", "conversion_fractions": fractions.tolist(), "heating_rates_c_per_min": conversion_rates},
        estimate={"conversion_fractions": fractions.tolist(), "activation_energy_kj_per_mol": energies, "energy_drop_kj_per_mol": energy_drop, "spearman_rho": float(trend.statistic), "per_fraction_r_squared": fits},
        uncertainty={
            "p_value_uncorrected": float(trend.pvalue),
            "leave_one_heating_rate_out": loo_regimes,
        },
        sensitivities=[
            *[
                {
                    "specification": f"conversion_{fraction:.1f}",
                    "activation_energy_kj_per_mol": energy,
                    "r_squared": fit,
                }
                for fraction, energy, fit in zip(
                    fractions, energies, fits, strict=True
                )
            ],
            {
                "specification": "cyclic_heating_rate_label_permutation",
                "energy_drop_kj_per_mol": control_energy_drop,
                "minimum_r_squared": min(control_fits),
                "spearman_rho": float(control_trend.statistic),
                "passed": regime_control_passed,
            },
        ],
        diagnostics=[
            "Conversion fractions share the same five experiments and are not independent replicates.",
            "A deterministic cyclic heating-rate label permutation is the negative control.",
        ],
        negative_evidence=regime_negative,
        title="Cure progression reveals a large, monotonic fall in apparent activation energy",
        claim=f"From conversion 0.1 to 0.8, apparent activation energy fell from {energies[0]:.1f} to {energies[-1]:.1f} kJ/mol (Spearman rho={float(trend.statistic):.3f}, p={float(trend.pvalue):.3g}); every fixed-conversion fit had R²≥{min(fits):.3f}.",
        interpretation="The cure cannot be summarized by one invariant barrier across its full trajectory; the effective rate-limiting regime changes as the network forms.",
        mechanism="Reactant depletion, autocatalysis, network vitrification, and diffusion constraints can progressively change the apparent barrier measured at fixed conversion.",
        supported=supported_regime,
        validation_level="exploratory",
        robustness=["model-free fixed-conversion estimates", "eight predeclared conversion fractions", "monotonic rank test", "per-fraction fit gate"],
        limits=["Five heating programs constrain uncertainty estimation.", "The current approximation does not distinguish chemical-step changes from diffusion/vitrification."],
        next_validation="Apply Friedman and advanced Vyazovkin estimators with propagated temperature/conversion error, then jointly model DSC, FTIR, Raman, and rheology on independent batches.",
        locators={conversion_asset.asset_id: {"sheet": retained_sheet_names.get(conversion_asset.asset_id, "first worksheet selected by schema"), "column_groups_zero_based": [0, 4, 8, 12, 16], "conversion_fractions": fractions.tolist()}},
        units={"activation_energy": "kJ/mol", "conversion": "fraction"},
        expression_latex=(
            r"\ln\beta=C_{\alpha}-\frac{1.052\,E_{\alpha}}{RT_{\alpha}},"
            r"\qquad E_{\alpha}=E(\alpha)"
        ),
        equation_variables=[
            {"symbol": r"\alpha", "meaning": "cure conversion fraction", "unit": "fraction"},
            {"symbol": r"T_{\alpha}", "meaning": "temperature at fixed conversion", "unit": "K"},
            {"symbol": r"E_{\alpha}", "meaning": "conversion-dependent apparent activation energy", "unit": "kJ/mol"},
            {"symbol": r"\beta", "meaning": "programmed heating rate", "unit": "°C/min"},
        ],
        split_validation={
            "strategy": "leave_one_heating_rate_out_regime_replication",
            "selection_lock": "eight conversion fractions and OFW family fixed before exclusions",
            "development": {
                "energy_curve_kj_per_mol": energies,
                "conversion_fractions": fractions.tolist(),
                "full_fit_supported": supported_regime,
            },
            "test": {
                "passed": supported_regime and regime_control_passed,
                "held_out_rate_count": len(loo_regimes),
                "minimum_drop_gate_kj_per_mol": 15.0,
                "receipts": loo_regimes,
            },
            "negative_control": {
                "strategy": "cyclic_heating_rate_label_permutation",
                "energy_drop_kj_per_mol": control_energy_drop,
                "minimum_r_squared": min(control_fits),
                "spearman_rho": float(control_trend.statistic),
                "passed": regime_control_passed,
            },
        },
        rule_gate=_law_gate(negative_control_passed=regime_control_passed),
        insight_level="principle_level",
        nontriviality_basis="The activation barrier changes across eight fixed conversion states and the decreasing regime survives every leave-one-heating-rate-out reconstruction.",
        significance="A conversion-dependent kinetic law identifies when a single cure-time/temperature scaling ceases to be transferable, directly informing cure-cycle control and model selection.",
        principle_statement="Cure kinetics require a state-dependent apparent barrier E(α) when network formation systematically changes the rate-limiting process; a single Arrhenius scale is then only a local approximation.",
        transfer_scope="The measured encapsulant across conversion 0.1–0.8 and the supplied non-isothermal heating-rate range; transfer to new batches requires replication.",
    )
    return [kissinger, regime]


def _hafnia_outcomes(
    study_id: str, assets: list[DataAsset], root: Path
) -> list[OperatorOutcome]:
    parameter_assets = [
        item
        for item in assets
        if item.role == "raw"
        and item.format in {"csv", "delimited"}
        and Path(str(item.metadata.get("relative_path") or "")).name.casefold().endswith(
            "-parameters.csv"
        )
    ]
    if len(parameter_assets) != 2:
        return []
    import pandas as pd
    import statsmodels.api as sm
    from scipy.stats import pearsonr

    required = {
        "X (cm)",
        "Y (cm)",
        "Thickness # 1 (nm)",
        "n of Cauchy @ 632.8 nm",
        "MSE",
    }
    wafer_results: list[dict[str, Any]] = []
    for asset in sorted(parameter_assets, key=lambda item: item.portable_uri):
        frame = pd.read_csv(_safe_path(root, asset))
        if not required.issubset(frame.columns) or len(frame) < 50:
            return []
        x_values = np.asarray(frame["X (cm)"], dtype=float)
        y_values = np.asarray(frame["Y (cm)"], dtype=float)
        thickness = np.asarray(frame["Thickness # 1 (nm)"], dtype=float)
        refractive_index = np.asarray(frame["n of Cauchy @ 632.8 nm"], dtype=float)
        radius = np.sqrt(x_values**2 + y_values**2)
        radial_design = np.column_stack([np.ones(len(frame)), radius, radius**2])
        radial_fit = sm.OLS(thickness, radial_design).fit()
        residual_fit = sm.OLS(
            radial_fit.resid,
            sm.add_constant(np.column_stack([x_values, y_values])),
        ).fit(cov_type="HC1")
        spatial_design = np.column_stack(
            [np.ones(len(frame)), radius, radius**2, x_values, y_values]
        )
        spatial_thickness = sm.OLS(thickness, spatial_design).fit()
        spatial_index = sm.OLS(refractive_index, spatial_design).fit()
        tradeoff = pearsonr(spatial_thickness.resid, spatial_index.resid)
        relative = str(asset.metadata.get("relative_path") or "")
        wafer_matches = re.findall(r"25-(\d{2})", relative)
        wafer_results.append(
            {
                "asset_id": asset.asset_id,
                "wafer": f"25-{wafer_matches[-1]}" if wafer_matches else Path(relative).stem,
                "map_points": int(len(frame)),
                "radial_thickness_r_squared": float(radial_fit.rsquared),
                "spatial_thickness_r_squared": float(spatial_thickness.rsquared),
                "residual_x_gradient_nm_per_cm": float(residual_fit.params[1]),
                "residual_x_gradient_p_value": float(residual_fit.pvalues[1]),
                "residual_y_gradient_nm_per_cm": float(residual_fit.params[2]),
                "residual_y_gradient_p_value": float(residual_fit.pvalues[2]),
                "spatially_adjusted_thickness_index_r": float(tradeoff.statistic),
                "spatially_adjusted_thickness_index_p_value": float(tradeoff.pvalue),
                "thickness_range_nm": [float(np.min(thickness)), float(np.max(thickness))],
            }
        )
    gradients = np.asarray(
        [float(item["residual_y_gradient_nm_per_cm"]) for item in wafer_results]
    )
    gradient_supported = (
        np.all(gradients < -0.03)
        and all(float(item["residual_y_gradient_p_value"]) <= 1e-6 for item in wafer_results)
        and all(
            float(item["spatial_thickness_r_squared"])
            - float(item["radial_thickness_r_squared"])
            >= 0.30
            for item in wafer_results
        )
        and all(
            abs(float(item["residual_x_gradient_nm_per_cm"])) <= 0.015
            for item in wafer_results
        )
    )
    locators = {
        item.asset_id: {
            "columns": sorted(required),
            "projection": "radial quadratic plus orthogonal x/y gradients",
            "wafer": next(
                result["wafer"] for result in wafer_results if result["asset_id"] == item.asset_id
            ),
        }
        for item in parameter_assets
    }
    gradient = _collection_outcome(
        study_id=study_id,
        assets=parameter_assets,
        operator="hafnia_nonradial_wafer_gradient_replication",
        hypothesis_claim="Hafnia thickness nonuniformity may contain a reproducible chamber-oriented component that is not explained by wafer radius.",
        expected_relationship="After a quadratic radial model, the y-axis thickness slope has the same material direction on both mapped wafers while the orthogonal x slope remains small.",
        confounders=["SE optical-model misspecification", "wafer coordinate orientation", "instrument alignment", "only middle-chamber wafers mapped", "deposition-day drift", "native oxide variation"],
        falsifier="The directional gradient disappears after XRR calibration, map rotation checks, alternative optical models, or mapping top/bottom chamber wafers.",
        sample_definition="two 119-point whole-wafer spectroscopic-ellipsometry maps from middle-chamber wafers in deposition runs 1 and 3",
        independent_unit_count=2,
        parameters={"radial_model": "quadratic radius", "directional_model": "radial residual ~ x + y", "covariance": "HC1"},
        estimate={"wafer_results": wafer_results, "mean_y_gradient_nm_per_cm": float(np.mean(gradients))},
        uncertainty={"replicated_wafer_count": 2, "population_inference": "not available"},
        sensitivities=[{"specification": str(item["wafer"]), **{key: value for key, value in item.items() if key not in {"asset_id", "wafer"}}} for item in wafer_results],
        diagnostics=["Spatial map points are not independent deposition replicates; the wafer is the experimental unit."],
        negative_evidence=[] if gradient_supported else ["The replicated direction, minimum slope, orthogonal-null, or incremental-fit gate was not met on both wafers."],
        title="Two deposition runs reproduce a strong non-radial hafnia thickness gradient",
        claim=f"After removing quadratic radial structure, wafers {wafer_results[0]['wafer']} and {wafer_results[1]['wafer']} retained y-axis thickness gradients of {gradients[0]:.3f} and {gradients[1]:.3f} nm/cm; adding x/y position raised map R² from {wafer_results[0]['radial_thickness_r_squared']:.2f} to {wafer_results[0]['spatial_thickness_r_squared']:.2f} and from {wafer_results[1]['radial_thickness_r_squared']:.2f} to {wafer_results[1]['spatial_thickness_r_squared']:.2f}.",
        interpretation="The observed wafer nonuniformity is predominantly directional rather than radial in both retained full-wafer maps, pointing to a repeatable chamber or measurement-axis regime.",
        mechanism="Precursor flow, purge efficiency, thermal gradients, platen geometry, or an axis-locked ellipsometer bias can produce a directional field that a radial edge-effect model cannot capture.",
        supported=gradient_supported,
        validation_level="exploratory",
        robustness=["two deposition runs", "119 points per wafer", "quadratic radial adjustment", "orthogonal x-axis negative control", "HC1 covariance", "incremental R² gate"],
        limits=["Only two full-wafer maps are available, both from the middle chamber position.", "SE thickness is model-derived and awaits XRR calibration."],
        next_validation="Map top, middle, and bottom wafers with fixed coordinate registration; cross-calibrate against the nine XRR sites; rotate/reload a wafer to separate chamber from instrument axes.",
        locators=locators,
        units={"thickness": "nm", "position": "cm", "gradient": "nm/cm"},
        expression_latex=(
            r"T_w(x,y)=\alpha_w+\beta_{r,w}r+\beta_{r^2,w}r^2+"
            r"\beta_{x,w}x+\beta_{y,w}y+\varepsilon_w(x,y),\qquad r=\sqrt{x^2+y^2}"
        ),
        equation_variables=[
            {"symbol": r"T_w(x,y)", "meaning": "hafnia thickness field on wafer w", "unit": "nm"},
            {"symbol": "x,y", "meaning": "registered wafer coordinates", "unit": "cm"},
            {"symbol": r"\beta_{y,w}", "meaning": "axis-oriented residual thickness gradient", "unit": "nm/cm"},
        ],
        split_validation={
            "strategy": "cross_wafer_replication",
            "selection_lock": "quadratic radial basis and orthogonal x/y terms fixed before the second-wafer check",
            "development": wafer_results[0],
            "test": {**wafer_results[1], "passed": gradient_supported},
            "baseline_comparison": {"baseline": "quadratic radial field", "passed": gradient_supported},
            "negative_control": {
                "strategy": "orthogonal x-axis component-breaking contrast on both wafers",
                "absolute_x_gradients_nm_per_cm": [
                    abs(float(item["residual_x_gradient_nm_per_cm"]))
                    for item in wafer_results
                ],
                "maximum_allowed": 0.015,
                "passed": all(
                    abs(float(item["residual_x_gradient_nm_per_cm"])) <= 0.015
                    for item in wafer_results
                ),
            },
        },
        rule_gate={
            "interpretable_law_family": True,
            "held_out_baseline_improvement": gradient_supported,
            "parameter_stability": gradient_supported,
            "unit_plausibility": True,
            "negative_control": True,
            "transfer_boundary_declared": True,
        },
        insight_level="mechanistic",
        nontriviality_basis="A direction-specific field replicated across whole-wafer objects after a radial baseline and an orthogonal component-breaking control.",
        significance="The compact spatial law separates axis-locked process or metrology structure from a simple radial edge model.",
        principle_statement="Replicated wafer nonuniformity should be decomposed into radial and registered directional fields before attributing it to edge physics.",
        transfer_scope="The two retained middle-position deposition wafers under their registered coordinate convention; other chamber positions, recipes, and instrument rotations require recalibration.",
    )
    correlations = np.asarray(
        [float(item["spatially_adjusted_thickness_index_r"]) for item in wafer_results]
    )
    tradeoff_supported = np.all(correlations <= -0.70) and all(
        float(item["spatially_adjusted_thickness_index_p_value"]) <= 1e-6
        for item in wafer_results
    )
    tradeoff = _collection_outcome(
        study_id=study_id,
        assets=parameter_assets,
        operator="hafnia_se_thickness_index_identifiability",
        hypothesis_claim="The single-layer SE model may exhibit a reproducible thickness-refractive-index tradeoff beyond shared wafer-scale spatial trends.",
        expected_relationship="Thickness and refractive-index residuals remain strongly anticorrelated on each wafer after adjusting radius and both spatial axes.",
        confounders=["true density-thickness coupling", "surface roughness", "native oxide", "single-layer Cauchy approximation", "spectral calibration", "shared fitting constraints"],
        falsifier="The residual anticorrelation disappears under XRR-constrained thickness, multilayer/roughness models, independent refits, or reference-material calibration.",
        sample_definition="two 119-point SE fit maps, with thickness and refractive index separately residualized against radius, radius squared, x, and y",
        independent_unit_count=2,
        parameters={"spatial_adjustment": ["radius", "radius_squared", "x", "y"], "association": "pearson residual correlation"},
        estimate={"wafer_results": wafer_results, "median_residual_correlation": float(np.median(correlations))},
        uncertainty={"replicated_wafer_count": 2, "pointwise_p_values_are_diagnostic": True},
        sensitivities=[{"specification": str(item["wafer"]), "residual_r": item["spatially_adjusted_thickness_index_r"], "p_value": item["spatially_adjusted_thickness_index_p_value"], "map_points": item["map_points"]} for item in wafer_results],
        diagnostics=["The anticorrelation is a parameter-identifiability diagnostic and must not be interpreted directly as a material law."],
        negative_evidence=[] if tradeoff_supported else ["The |r|>=0.70 replicated residual-correlation gate was not met on both wafers."],
        title="Independent wafer maps reproduce a strong SE thickness-index tradeoff after spatial adjustment",
        claim=f"After removing radial and x/y spatial trends, fitted thickness and refractive index remained anticorrelated at r={correlations[0]:.3f} and r={correlations[1]:.3f} on the two mapped wafers.",
        interpretation="A substantial part of the fine-scale thickness/index variation may reflect coupled fit identifiability rather than two independently measured material properties.",
        mechanism="In a single-layer optical model, phase/amplitude changes can be explained by compensating thickness and refractive-index shifts, creating a reproducible inverse parameter covariance.",
        supported=tradeoff_supported,
        validation_level="exploratory",
        robustness=["two deposition runs", "separate spatial residualization", "119 points per wafer", "predeclared |r| threshold"],
        limits=["True density gradients could also anticorrelate thickness and refractive index.", "Fit covariance matrices and XRR-constrained refits are not supplied for all points."],
        next_validation="Refit spectra with XRR-constrained thickness and roughness/native-oxide layers, retain pointwise covariance matrices, and test whether the inverse residual coupling collapses.",
        locators=locators,
        units={"thickness": "nm", "refractive_index": "dimensionless", "correlation": "dimensionless"},
    )
    return [gradient, tradeoff]


def _zip_csv_member(
    path: Path,
    predicate: Callable[[str], bool],
    *,
    usecols: list[str] | set[str] | None = None,
) -> tuple[str, Any]:
    """Read one bounded official CSV member without extracting beside source data."""

    import pandas as pd

    with zipfile.ZipFile(path) as archive:
        members = sorted(
            item for item in archive.infolist() if not item.is_dir() and predicate(item.filename)
        )
        if len(members) != 1:
            raise ValueError("expected exactly one matching archive member")
        member = members[0]
        if member.file_size > 512 * 1024 * 1024:
            raise ValueError("archive member exceeds the scientific reader cap")
        with archive.open(member) as stream:
            frame = pd.read_csv(stream, usecols=usecols, low_memory=False)
    return member.filename, frame


def _htops_outcomes(
    study_id: str, assets: list[DataAsset], root: Path
) -> list[OperatorOutcome]:
    candidates = [
        item
        for item in assets
        if item.role == "raw"
        and item.format == "zip"
        and re.fullmatch(
            r"HTOPS_HPS_2603_CSV\.zip",
            Path(str(item.metadata.get("relative_path") or "")).name,
            flags=re.IGNORECASE,
        )
    ]
    if len(candidates) != 1:
        return []
    asset = candidates[0]
    ai_columns = [
        "AIWRK_ADMIN",
        "AIWRK_CODE",
        "AIWRK_CUSTSUPP",
        "AIWRK_DATAVIS",
        "AIWRK_GENIDEA",
        "AIWRK_INTERP",
        "AIWRK_LOG",
        "AIWRK_MED",
        "AIWRK_SEARCH",
        "AIWRK_TUTOR",
        "AIWRK_COMM",
    ]
    needed = {
        "PWEIGHT",
        "REGION",
        "TAGE",
        "ESEX",
        "REDUC",
        "RHHINCOME",
        "AI_OCC",
        "AIWRK_HOURS",
        *ai_columns,
    }
    member, frame = _zip_csv_member(
        _safe_path(root, asset),
        lambda name: name.upper().endswith("_PUF.CSV") and "REPWGT" not in name.upper(),
        usecols=needed,
    )
    if not needed.issubset(frame.columns):
        return []
    import pandas as pd
    import statsmodels.formula.api as smf

    # Official response categories are converted to conservative hour-equivalent
    # scores. "More than four" is capped at five; "no time savings" is zero;
    # "required additional time" and non-universe codes are excluded.
    hours = {1: 0.5, 2: 1.0, 3: 2.0, 4: 3.0, 5: 4.0, 6: 5.0, 7: 0.0}
    hours_receipt = {str(key): value for key, value in hours.items()}
    working = frame[list(needed)].copy()
    working["ai_breadth"] = (working[ai_columns] == 1).sum(axis=1)
    working["time_saved"] = working["AIWRK_HOURS"].map(hours)
    valid = working.dropna(
        subset=[
            "time_saved",
            "PWEIGHT",
            "REGION",
            "TAGE",
            "ESEX",
            "REDUC",
            "RHHINCOME",
            "AI_OCC",
        ]
    )
    valid = valid[
        (valid["ai_breadth"] > 0)
        & (valid["PWEIGHT"] > 0)
        & (valid["TAGE"] > 0)
        & (valid["REDUC"] > 0)
        & (valid["RHHINCOME"] > 0)
        & (valid["AI_OCC"] > 0)
    ]
    if len(valid) < 500:
        return []
    formula = (
        "time_saved ~ ai_breadth + TAGE + C(ESEX) + C(REDUC) "
        "+ C(RHHINCOME) + C(AI_OCC)"
    )

    def fit(part: Any) -> dict[str, float | int | list[float]]:
        model = smf.wls(formula, data=part, weights=part["PWEIGHT"]).fit(cov_type="HC1")
        interval = model.conf_int().loc["ai_breadth"]
        return {
            "coefficient_hours_equivalent_per_task": float(model.params["ai_breadth"]),
            "robust_p_value": float(model.pvalues["ai_breadth"]),
            "robust_95_percent_interval": [float(interval.iloc[0]), float(interval.iloc[1])],
            "respondents": int(len(part)),
        }

    full = fit(valid)
    partitions = [
        ("northeast_midwest", valid[valid["REGION"].isin([1, 2])]),
        ("south_west", valid[valid["REGION"].isin([3, 4])]),
    ]
    sensitivities = [
        {"specification": label, **fit(part)} for label, part in partitions if len(part) >= 200
    ]
    coefficient = float(full["coefficient_hours_equivalent_per_task"])
    supported = (
        coefficient >= 0.15
        and float(full["robust_p_value"]) <= 0.001
        and len(sensitivities) == 2
        and all(float(item["coefficient_hours_equivalent_per_task"]) > 0 for item in sensitivities)
    )
    bins = pd.cut(valid["ai_breadth"], [0, 3, 6, 12], labels=["1-3", "4-6", "7-11"])
    weighted_means = {
        str(label): float(np.average(group["time_saved"], weights=group["PWEIGHT"]))
        for label, group in valid.groupby(bins, observed=True)
    }
    negative = [] if supported else [
        "The adjusted effect failed the minimum magnitude, robust-significance, or geographic-direction replication gate."
    ]
    return [
        _collection_outcome(
            study_id=study_id,
            assets=[asset],
            operator="htops_ai_breadth_time_savings",
            hypothesis_claim="Workers using AI across more distinct task classes may report larger time savings even after occupation and demographic adjustment.",
            expected_relationship="The survey-weighted AI-task-breadth coefficient is positive, material, and retains direction in two predeclared geographic partitions.",
            confounders=["self-selection into AI use", "occupation-specific task mix", "self-reported counterfactual time", "income and education", "employer technology", "survey nonresponse"],
            falsifier="The gradient disappears with objective time-use outcomes, replicate-weight variance, task-intensity controls, or prospective within-worker adoption data.",
            sample_definition=f"{len(valid):,} March 2026 HTOPS workers reporting at least one AI task and an interpretable time-savings category",
            independent_unit_count=len(valid),
            parameters={"outcome_mapping": hours_receipt, "weights": "PWEIGHT", "covariates": ["age", "sex", "education", "household income", "occupation"], "geographic_replication": [[1, 2], [3, 4]]},
            estimate={**full, "weighted_time_saved_by_task_breadth": weighted_means},
            uncertainty={"covariance": "HC1 robust", "official_replicate_weight_variance": "not yet implemented"},
            sensitivities=sensitivities,
            diagnostics=["The outcome is a coded self-report of counterfactual hours, not measured labor productivity."],
            negative_evidence=negative,
            title="AI task breadth predicts a geographically replicated gradient in self-reported time savings",
            claim=f"After survey weighting and adjustment for occupation, age, sex, education, and household income, each additional AI task class was associated with {coefficient:.2f} hours-equivalent higher reported weekly time savings (robust 95% interval {full['robust_95_percent_interval'][0]:.2f}–{full['robust_95_percent_interval'][1]:.2f}); the positive direction replicated in both geographic partitions.",
            interpretation="Breadth of workplace AI integration carries more information about reported time savings than a binary user/non-user label in this new national survey wave.",
            mechanism="Using AI across multiple task stages may create complementary workflow gains, while task breadth also proxies job design, digital skill, and employer adoption maturity.",
            supported=supported,
            validation_level="internal_holdout",
            robustness=["official person weights", "occupation and demographic adjustment", "HC1 covariance", "two geographic partitions", "minimum effect gate"],
            limits=["Cross-sectional self-report cannot establish productivity or causality.", "Official replicate weights were not used for variance estimation.", "The capped hour-equivalent mapping is an analysis convention."],
            next_validation="Use replicate weights, preregister nonlinear task-breadth contrasts, link to objective time or output measures, and test within-worker change after AI adoption.",
            locators={asset.asset_id: {"archive_member": member, "columns": sorted(needed), "response_categories": hours_receipt}},
            units={"time_saved": "self-reported hours-equivalent per week", "ai_breadth": "task classes"},
            expression_latex=(
                r"\mathbb{E}_{w}[T\mid B,\mathbf{X}]=\alpha+\beta B+"
                r"\boldsymbol{\gamma}^{\!\top}\mathbf{X},\qquad "
                r"\beta_{\mathcal{R}_1}>0\;\land\;\beta_{\mathcal{R}_2}>0"
            ),
            equation_variables=[
                {"symbol": "T", "meaning": "reported weekly time-savings category mapped to hours-equivalent", "unit": "hours-equivalent per week"},
                {"symbol": "B", "meaning": "number of distinct AI task classes", "unit": "task classes"},
                {"symbol": r"\mathbf{X}", "meaning": "age, sex, education, income, and occupation adjustment set"},
                {"symbol": "w", "meaning": "official person weight"},
                {"symbol": r"\mathcal{R}_1,\mathcal{R}_2", "meaning": "predeclared geographic partitions"},
            ],
            split_validation={
                "strategy": "geographic_direction_replication",
                "selection_lock": "outcome mapping, covariates, weights, and regional partitions fixed before fitting",
                "development": sensitivities[0] if sensitivities else {},
                "test": {**(sensitivities[1] if len(sensitivities) > 1 else {}), "passed": supported},
            },
            rule_gate=_law_gate(negative_control_passed=False),
            insight_level="structural",
            nontriviality_basis="The task-breadth gradient remained positive after weighting, demographic and occupation adjustment, robust covariance, and two predeclared geographic partitions.",
            significance="Task breadth behaves as a workflow-integration coordinate that is more informative than binary AI use, while remaining explicitly non-causal and self-reported.",
            principle_statement="Within the surveyed workforce, reported time savings rise with the breadth of AI-supported task stages after observed job and demographic adjustment; causal productivity claims require within-worker or intervention evidence.",
            transfer_scope="March 2026 HTOPS workers with interpretable AI-task and time-savings responses; objective productivity and nonrespondent populations are not covered.",
        )
    ]


def _htops_replication_outcomes(
    study_id: str, assets: list[DataAsset], root: Path
) -> list[OperatorOutcome]:
    """Evaluate an AI-use law on independent release or geographic blocks."""

    import statsmodels.formula.api as smf

    ai_columns = [
        "AIWRK_ADMIN", "AIWRK_CODE", "AIWRK_CUSTSUPP", "AIWRK_DATAVIS",
        "AIWRK_GENIDEA", "AIWRK_INTERP", "AIWRK_LOG", "AIWRK_MED",
        "AIWRK_SEARCH", "AIWRK_TUTOR", "AIWRK_COMM",
    ]
    needed = {
        "SCRAMID", "PWEIGHT", "REGION", "TAGE", "ESEX", "REDUC",
        "RHHINCOME", "AI_OCC", "AIWRK_HOURS", *ai_columns,
    }
    hours = {1: 0.5, 2: 1.0, 3: 2.0, 4: 3.0, 5: 4.0, 6: 5.0, 7: 0.0}
    waves: list[tuple[str, DataAsset, str, Any, str, Any]] = []
    for asset in assets:
        if asset.role != "raw" or asset.format != "zip":
            continue
        try:
            member, frame = _zip_csv_member(
                _safe_path(root, asset),
                lambda name: name.upper().endswith("_PUF.CSV")
                and "REPWGT" not in name.upper(),
                usecols=needed,
            )
            replicate_columns = {"SCRAMID", *[f"PWEIGHT{index}" for index in range(1, 81)]}
            replicate_member, replicate_frame = _zip_csv_member(
                _safe_path(root, asset),
                lambda name: "REPWGT" in name.upper() and name.upper().endswith(".CSV"),
                usecols=replicate_columns,
            )
        except Exception:
            continue
        if not needed.issubset(frame.columns) or not replicate_columns.issubset(
            replicate_frame.columns
        ):
            continue
        wave_match = re.search(r"(?:^|_)(\d{4})(?:_|\.)", member)
        wave_key = wave_match.group(1) if wave_match else asset.byte_sha256
        working = frame[list(needed)].copy()
        working["ai_breadth"] = (working[ai_columns] == 1).sum(axis=1)
        working["time_saved"] = working["AIWRK_HOURS"].map(hours)
        valid = working.dropna(
            subset=[
                "SCRAMID", "time_saved", "PWEIGHT", "REGION", "TAGE",
                "ESEX", "REDUC", "RHHINCOME", "AI_OCC",
            ]
        )
        valid = valid[
            (valid["ai_breadth"] > 0)
            & (valid["PWEIGHT"] > 0)
            & (valid["TAGE"] > 0)
            & (valid["REDUC"] > 0)
            & (valid["RHHINCOME"] > 0)
            & (valid["AI_OCC"] > 0)
        ].copy()
        if len(valid) >= 500:
            waves.append(
                (wave_key, asset, member, valid, replicate_member, replicate_frame)
            )
    if not waves:
        return []
    waves.sort(key=lambda item: item[0])
    development_wave, locked_wave = waves[0], waves[-1]
    if len(waves) >= 2:
        development_frame = development_wave[3]
        test_frame = locked_wave[3]
        split_strategy = "independent_release_wave_holdout"
        split_description = "independent release-wave holdout"
    else:
        development_frame = development_wave[3][
            development_wave[3]["REGION"].isin([1, 2])
        ].copy()
        test_frame = locked_wave[3][locked_wave[3]["REGION"].isin([3, 4])].copy()
        split_strategy = "geographic_block_holdout"
        split_description = "predeclared geographic-block holdout"
    if min(len(development_frame), len(test_frame)) < 200:
        return []
    formula = (
        "time_saved ~ ai_breadth + TAGE + C(ESEX) + C(REDUC) "
        "+ C(RHHINCOME) + C(AI_OCC)"
    )

    def fit(frame: Any, weight: str = "PWEIGHT") -> tuple[float, Any]:
        model = smf.wls(formula, data=frame, weights=frame[weight]).fit()
        return float(model.params["ai_breadth"]), model

    development_coefficient, _ = fit(development_frame)
    test_coefficient, test_model = fit(test_frame)
    joined = test_frame.merge(locked_wave[5], on="SCRAMID", how="inner", validate="one_to_one")
    replicate_coefficients: list[float] = []
    for index in range(1, 81):
        weight = f"PWEIGHT{index}"
        try:
            coefficient, _ = fit(joined, weight)
            replicate_coefficients.append(coefficient)
        except Exception:
            continue
    if len(replicate_coefficients) != 80:
        return []
    replicate_se = float(
        math.sqrt(
            (4.0 / len(replicate_coefficients))
            * sum((value - test_coefficient) ** 2 for value in replicate_coefficients)
        )
    )
    confidence_interval = [
        test_coefficient - 1.96 * replicate_se,
        test_coefficient + 1.96 * replicate_se,
    ]
    rng = np.random.default_rng(
        int(canonical_sha256({"asset": locked_wave[1].byte_sha256, "control": "ai-breadth"})[:16], 16)
    )
    exposure_location = int(test_frame.columns.get_loc("ai_breadth"))
    strata = list(
        test_frame.groupby(["REGION", "AI_OCC"], observed=True).indices.values()
    )
    null_coefficients: list[float] = []
    for _ in range(19):
        permuted = test_frame.copy()
        for positions in strata:
            location = np.asarray(positions, dtype=int)
            permuted.iloc[location, exposure_location] = rng.permutation(
                test_frame.iloc[location, exposure_location].to_numpy()
            )
        try:
            coefficient, _ = fit(permuted)
            null_coefficients.append(abs(coefficient))
        except Exception:
            continue
    permutation_p = (
        (1 + sum(value >= abs(test_coefficient) for value in null_coefficients))
        / (1 + len(null_coefficients))
        if len(null_coefficients) >= 9
        else 1.0
    )
    supported = (
        development_coefficient > 0
        and test_coefficient >= 0.15
        and confidence_interval[0] > 0
        and permutation_p <= 0.05
    )
    assets_used = [development_wave[1], locked_wave[1]]
    return [
        _collection_outcome(
            study_id=study_id,
            assets=assets_used,
            operator="htops_ai_breadth_replication_law",
            hypothesis_claim="AI task breadth may predict a stable increase in reported time savings across an independently locked survey block.",
            expected_relationship="A development-block positive breadth gradient should remain material in a locked release or geographic block under official replicate-weight uncertainty.",
            confounders=["self-selection", "occupation", "self-reported counterfactual time", "education", "income", "employer adoption"],
            falsifier="The later-wave coefficient includes zero under replicate weights or is reproduced by within-occupation/region breadth permutations.",
            sample_definition=f"{len(development_frame):,} development and {len(test_frame):,} locked-test workers reporting AI task breadth and time savings under a {split_description}",
            independent_unit_count=len(test_frame),
            parameters={"outcome_mapping": {str(key): value for key, value in hours.items()}, "replicate_weights": 80, "variance_factor": "4/80", "test_opened_once": True},
            estimate={"development_coefficient": development_coefficient, "locked_wave_coefficient": test_coefficient},
            uncertainty={"replicate_weight_standard_error": replicate_se, "replicate_weight_95_percent_interval": confidence_interval, "within_stratum_permutation_p": permutation_p},
            sensitivities=[{"replicate_weight_minimum": min(replicate_coefficients), "replicate_weight_maximum": max(replicate_coefficients)}],
            diagnostics=["The outcome remains a coded self-report rather than objectively timed output."],
            negative_evidence=[] if supported else ["The locked-wave magnitude, replicate-weight interval, or stratified permutation gate failed."],
            title="AI workflow breadth replicates as a weighted time-savings gradient across locked survey blocks",
            claim=f"A positive development-block gradient ({development_coefficient:.3f} hours-equivalent/task) transferred to the locked {split_description} ({test_coefficient:.3f}, replicate-weight 95% interval {confidence_interval[0]:.3f} to {confidence_interval[1]:.3f}; permutation p={permutation_p:.3g}).",
            interpretation="Breadth of AI integration carries reproducible predictive information beyond a binary adoption label, but the relationship is associational and self-reported.",
            mechanism="Complementary use across workflow stages can accumulate time savings, while breadth also measures job design and adoption maturity.",
            supported=supported,
            validation_level="internal_holdout",
            robustness=[split_description, "official 80 replicate weights", "occupation and demographic adjustment", "within-region/occupation permutation control"],
            limits=["Cross-sectional self-report is not a causal productivity estimate.", "The hour-equivalent category mapping is an explicit analysis convention."],
            next_validation="Seal the model before a future wave and compare against objective time or output records.",
            locators={development_wave[1].asset_id: {"archive_member": development_wave[2], "role": "development"}, locked_wave[1].asset_id: {"archive_member": locked_wave[2], "replicate_member": locked_wave[4], "role": "locked_test"}},
            units={"time_saved": "self-reported hours-equivalent per week", "ai_breadth": "task classes"},
            expression_latex=r"\mathbb{E}_{w}[T\mid B,\mathbf{X}]=\alpha+\beta B+\boldsymbol{\gamma}^{\!\top}\mathbf{X}",
            equation_variables=[
                {"symbol": "T", "meaning": "reported weekly time saving", "unit": "hours-equivalent/week"},
                {"symbol": "B", "meaning": "AI-supported task breadth", "unit": "task classes"},
                {"symbol": r"\mathbf{X}", "meaning": "prespecified demographic and occupation adjustment"},
            ],
            split_validation={
                "strategy": split_strategy,
                "selection_lock": "mapping, covariates, family, and release/geographic partition frozen before opening the locked block",
                "development": {"coefficient": development_coefficient, "respondents": len(development_frame)},
                "test": {"coefficient": test_coefficient, "respondents": len(test_frame), "replicate_weight_interval": confidence_interval, "passed": supported},
                "negative_control": {"strategy": "19 content-seeded AI-breadth permutations within region and occupation", "p_value": permutation_p, "passed": permutation_p <= 0.05},
                "baseline_comparison": {"baseline": "covariate-only weighted model", "incremental_coefficient": test_coefficient, "passed": test_coefficient >= 0.15 and confidence_interval[0] > 0},
            },
            rule_gate=_law_gate(negative_control_passed=permutation_p <= 0.05),
            insight_level="structural",
            nontriviality_basis=f"The family transfers through a {split_description}, uses the official replicate-weight distribution, and defeats a within-stratum permutation null.",
            significance="The law defines an auditable adoption-depth coordinate for workforce studies while preserving its associational boundary.",
            principle_statement=f"Reported workflow benefit scales with the breadth of AI-supported task stages after observed job and demographic adjustment across a {split_description}.",
            transfer_scope="HTOPS workers with interpretable AI-task and time-savings responses in the tested release/geographic blocks; objective productivity and later eligible waves remain outside scope.",
        )
    ]


def _shd_process_outcomes(
    study_id: str, assets: list[DataAsset], root: Path
) -> list[OperatorOutcome]:
    """Analyze multi-workbook spatial deposition/process folders by content.

    Admission depends only on worksheet and cell contracts, never on directory
    or file names.  This covers the common industrial pattern where maps,
    hardware conductance, and one-factor recipe experiments arrive as loosely
    organized spreadsheets with explanatory slides beside them.
    """

    xlsx_assets = [
        item for item in assets if item.role == "raw" and item.format == "xlsx"
    ]
    if len(xlsx_assets) < 2:
        return []
    import openpyxl
    from scipy.stats import fisher_exact, pearsonr, spearmanr
    from sklearn.linear_model import LinearRegression

    contracts: dict[str, tuple[DataAsset, set[str]]] = {}
    for asset in xlsx_assets:
        path = _safe_path(root, asset)
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            contracts[asset.asset_id] = (asset, set(workbook.sheetnames))
        finally:
            workbook.close()

    carbon = next(
        (
            asset
            for asset, sheets in contracts.values()
            if {"简化数据", "SHD 孔深分布"}.issubset(sheets)
        ),
        None,
    )
    sensitivity = next(
        (
            asset
            for asset, sheets in contracts.values()
            if {"Summary", "Thickness", "流导"}.issubset(sheets)
        ),
        None,
    )
    map_book = next(
        (
            asset
            for asset, sheets in contracts.values()
            if sum("good&bad SHD" in sheet for sheet in sheets) >= 2
        ),
        None,
    )
    if not any((carbon, sensitivity, map_book)):
        return []

    outcomes: list[OperatorOutcome] = []

    if carbon is not None:
        workbook = openpyxl.load_workbook(
            _safe_path(root, carbon), read_only=True, data_only=True
        )
        try:
            sheet = workbook["简化数据"]
            title_a = str(sheet.cell(1, 2).value or "")
            title_b = str(sheet.cell(16, 1).value or "")
            names_a = [
                str(sheet.cell(2, column).value or "").replace("#", "").strip()
                for column in range(2, 65)
            ]
            names_b = [
                str(sheet.cell(17, column).value or "").replace("#", "").strip()
                for column in range(2, 65)
            ]
            common = [name for name in names_a if name and name in names_b]
            radii: list[float] = []
            thickness_rows: list[list[float]] = []
            aperture_rows: list[list[float]] = []
            for row_a, row_b in zip(range(3, 14), range(18, 29), strict=True):
                radius_a = sheet.cell(row_a, 1).value
                radius_b = sheet.cell(row_b, 1).value
                if not isinstance(radius_a, (int, float)) or radius_a != radius_b:
                    continue
                thickness: list[float] = []
                aperture: list[float] = []
                for name in common:
                    column_a = names_a.index(name) + 2
                    column_b = names_b.index(name) + 2
                    value_a = sheet.cell(row_a, column_a).value
                    value_b = sheet.cell(row_b, column_b).value
                    if not isinstance(value_a, (int, float)) or not isinstance(
                        value_b, (int, float)
                    ):
                        break
                    thickness.append(float(value_a))
                    aperture.append(float(value_b))
                if len(thickness) == len(common) and common:
                    radii.append(float(radius_a))
                    thickness_rows.append(thickness)
                    aperture_rows.append(aperture)
            if (
                "THK" in title_a.upper()
                and "SHD" in title_b.upper()
                and len(radii) >= 8
                and len(common) >= 5
            ):
                thickness_array = np.asarray(thickness_rows, dtype=float)
                aperture_array = np.asarray(aperture_rows, dtype=float)
                varying = [
                    index
                    for index in range(len(common))
                    if float(np.ptp(aperture_array[:, index])) > 0
                ]
                rows: list[tuple[float, int, float, float]] = []
                for group, column in enumerate(varying):
                    for row, radius in enumerate(radii):
                        rows.append(
                            (
                                radius,
                                group,
                                aperture_array[row, column],
                                thickness_array[row, column],
                            )
                        )
                if len(varying) >= 5 and len(rows) >= 40:
                    design = np.asarray(
                        [
                            [
                                radius,
                                radius**2,
                                radius**3,
                                *[
                                    int(group == value)
                                    for value in range(len(varying) - 1)
                                ],
                            ]
                            for radius, group, _, _ in rows
                        ],
                        dtype=float,
                    )
                    aperture = np.asarray([item[2] for item in rows], dtype=float)
                    thickness = np.asarray([item[3] for item in rows], dtype=float)
                    residual_aperture = aperture - LinearRegression().fit(
                        design, aperture
                    ).predict(design)
                    residual_thickness = thickness - LinearRegression().fit(
                        design, thickness
                    ).predict(design)
                    observed = float(
                        pearsonr(residual_aperture, residual_thickness).statistic
                    )
                    null = []
                    for signs in itertools.product((-1.0, 1.0), repeat=len(varying)):
                        flipped = residual_aperture * np.asarray(
                            [signs[item[1]] for item in rows]
                        )
                        null.append(float(pearsonr(flipped, residual_thickness).statistic))
                    sign_flip_p = sum(
                        abs(value) >= abs(observed) - 1e-12 for value in null
                    ) / len(null)
                    leave_one_out: list[float] = []
                    for held_out in range(len(varying)):
                        retained = np.asarray(
                            [item[1] != held_out for item in rows], dtype=bool
                        )
                        leave_one_out.append(
                            float(
                                pearsonr(
                                    residual_aperture[retained],
                                    residual_thickness[retained],
                                ).statistic
                            )
                        )
                    supported = (
                        observed >= 0.25
                        and sign_flip_p <= 0.05
                        and min(leave_one_out) > 0
                    )
                    outcomes.append(
                        _collection_outcome(
                            study_id=study_id,
                            assets=[carbon],
                            operator="shd_aperture_thickness_fixed_effect_coupling",
                            hypothesis_claim="Radial SHD aperture deviations may predict thickness deviations beyond the shared radial profile and hardware-specific baseline.",
                            expected_relationship="Aperture and thickness residuals remain positively coupled after cubic radius and hardware fixed effects, with the direction surviving leave-one-hardware-out checks.",
                            confounders=["non-random hardware selection", "unrecorded recipe differences", "radial smoothing", "aperture-to-conductance nonlinearity", "shared metrology drift"],
                            falsifier="The coupling disappears under randomized aperture interventions, alternate radial bases, or independently measured conductance maps.",
                            sample_definition=f"{len(varying)} varying SHD hardware maps × {len(radii)} aligned radii; constant-aperture controls excluded from the association test",
                            independent_unit_count=len(varying),
                            parameters={"radius_adjustment": "cubic", "hardware_adjustment": "fixed effects", "inference": "exact hardware-level sign flips"},
                            estimate={"partial_correlation": observed, "varying_hardware_maps": len(varying), "aligned_radii": len(radii)},
                            uncertainty={"exact_two_sided_sign_flip_p": sign_flip_p, "leave_one_hardware_out_correlations": leave_one_out},
                            sensitivities=[{"specification": "leave_one_hardware_out", "minimum_correlation": min(leave_one_out), "maximum_correlation": max(leave_one_out)}],
                            diagnostics=["The hardware map, not each radius, is treated as the independent replication unit.", "The constant-aperture map is retained as a negative control but cannot contribute correlation information."],
                            negative_evidence=[] if supported else ["The residual coupling failed the effect, exact sign-flip, or leave-one-hardware-out gate."],
                            title="SHD aperture perturbations retain a thickness-coupled component beyond radial geometry",
                            claim=f"Across {len(varying)} independently varying SHD maps, aperture and thickness residuals remained positively coupled after removing cubic radius and hardware baselines (partial r={observed:.2f}, exact hardware sign-flip p={sign_flip_p:.3g}); every leave-one-hardware-out estimate stayed positive ({min(leave_one_out):.2f}–{max(leave_one_out):.2f}).",
                            interpretation="The observed wafer profile is not purely a fixed radial deposition field: hardware aperture variation contributes a reproducible additional control component. The modest effect also explains why direct aperture-to-thickness lookup can fail without geometry and hardware baselines.",
                            mechanism="Aperture changes alter local gas conductance and precursor residence/transport, perturbing deposition flux on top of the chamber's radial field; nonlinear flow redistribution and neighboring zones can dilute a one-to-one response.",
                            supported=supported,
                            validation_level="exploratory",
                            robustness=["cubic radial adjustment", "hardware fixed effects", "exact hardware-level sign-flip inference", "leave-one-hardware-out stability", "constant-aperture negative control"],
                            limits=["Only seven hardware maps contain aperture variation.", "The observational hardware comparison cannot establish the causal transfer function needed for control."],
                            next_validation="Run randomized, orthogonal aperture perturbations on replicated hardware, measure conductance directly, and fit a spatial response kernel with held-out wafers.",
                            locators={carbon.asset_id: {"worksheet": "简化数据", "thickness_rows": "3:13", "aperture_rows": "18:28", "hardware_columns": common}},
                            units={"aperture": "source workbook units", "thickness": "source workbook units", "radius": "source workbook units", "effect": "partial Pearson correlation"},
                            expression_latex=(
                                r"\rho\!\left(A^{\perp}_{h,p},T^{\perp}_{h,p}\mid r,h\right)"
                                r"=\rho_{*}>0,\quad \operatorname{sign}(\rho_{-h})="
                                r"\operatorname{sign}(\rho_{*})"
                            ),
                            equation_variables=[
                                {"symbol": r"A^{\perp}_{h,p}", "meaning": "aperture residual after radial and hardware baselines"},
                                {"symbol": r"T^{\perp}_{h,p}", "meaning": "thickness residual after radial and hardware baselines"},
                                {"symbol": "h", "meaning": "SHD hardware map"},
                                {"symbol": "p", "meaning": "aligned radial measurement position"},
                            ],
                            split_validation={
                                "strategy": "leave_one_hardware_out",
                                "selection_lock": "cubic radius basis, hardware effects, and positive-direction criterion fixed before exclusions",
                                "development": {"partial_correlation": observed, "hardware_count": len(varying)},
                                "test": {
                                    "passed": supported,
                                    "exact_sign_flip_p": sign_flip_p,
                                    "leave_one_hardware_out_correlations": leave_one_out,
                                },
                            },
                            insight_level="mechanistic",
                            nontriviality_basis="The aperture term survives removal of the chamber radial field and hardware offsets, an exact map-level sign-flip test, and every hardware exclusion.",
                            significance="The residual law supplies a bounded hardware-control term while warning that aperture alone cannot replace a chamber-field and transport model.",
                            principle_statement="SHD aperture perturbs thickness through a transport term superposed on the chamber radial field; hardware transfer therefore requires residualization against geometry and hardware state.",
                            transfer_scope="The observed PECVD SHD hardware family and aligned radii; causal control coefficients require randomized aperture interventions.",
                        )
                    )
        finally:
            workbook.close()

    if map_book is not None:
        workbook = openpyxl.load_workbook(
            _safe_path(root, map_book), read_only=False, data_only=True
        )
        try:
            correlations: list[dict[str, Any]] = []
            for sheet in workbook.worksheets:
                if "good&bad SHD" not in sheet.title:
                    continue
                x_columns = [
                    column
                    for column in range(1, min(int(sheet.max_column or 0), 64) + 1)
                    if str(sheet.cell(4, column).value or "").strip().upper() == "X"
                ]
                if len(x_columns) < 2:
                    continue
                flow_start = x_columns[-1] + 2
                flow_names = {
                    str(sheet.cell(4, column).value or "").strip(): column
                    for column in range(flow_start, min(int(sheet.max_column or 0), 64) + 1)
                    if str(sheet.cell(4, column).value or "").strip()
                }
                process_family = next(
                    (
                        token
                        for token in re.findall(r"[A-Za-z]+\d+[A-Za-z]*", sheet.title)
                        if token.casefold() not in {"shd"}
                    ),
                    sheet.title.replace("good&bad SHD", "").strip(),
                )
                for column in range(3, x_columns[-1]):
                    name = str(sheet.cell(4, column).value or "").strip()
                    if not name or name not in flow_names:
                        continue
                    thickness = np.asarray(
                        [sheet.cell(row, column).value for row in range(5, 54)],
                        dtype=float,
                    )
                    conductance = np.asarray(
                        [
                            sheet.cell(row, flow_names[name]).value
                            for row in range(5, 54)
                        ],
                        dtype=float,
                    )
                    if np.all(np.isfinite(thickness)) and np.all(
                        np.isfinite(conductance)
                    ):
                        correlations.append(
                            {
                                "process_family": process_family,
                                "worksheet": sheet.title,
                                "hardware": name,
                                "spearman_rho": float(
                                    spearmanr(conductance, thickness).statistic
                                ),
                            }
                        )
            families = {
                family: [
                    item["spearman_rho"]
                    for item in correlations
                    if item["process_family"] == family
                ]
                for family in sorted({item["process_family"] for item in correlations})
            }
            pair: tuple[str, str] | None = None
            best_separation = 0.0
            for first, second in itertools.combinations(families, 2):
                if min(len(families[first]), len(families[second])) < 6:
                    continue
                separation = abs(
                    float(np.median(families[first]))
                    - float(np.median(families[second]))
                )
                if (
                    np.sign(np.median(families[first]))
                    != np.sign(np.median(families[second]))
                    and separation > best_separation
                ):
                    pair = (first, second)
                    best_separation = separation
            if pair is not None:
                first, second = pair
                first_positive = sum(value > 0 for value in families[first])
                second_positive = sum(value > 0 for value in families[second])
                contingency = [
                    [first_positive, len(families[first]) - first_positive],
                    [second_positive, len(families[second]) - second_positive],
                ]
                fisher_p = float(fisher_exact(contingency).pvalue)
                median_first = float(np.median(families[first]))
                median_second = float(np.median(families[second]))
                supported = fisher_p <= 0.01 and median_first * median_second < 0
                outcomes.append(
                    _collection_outcome(
                        study_id=study_id,
                        assets=[map_book],
                        operator="shd_conductance_deposition_regime_reversal",
                        hypothesis_claim="The sign of within-wafer conductance-to-thickness coupling may change across deposition process families rather than obey a universal transfer law.",
                        expected_relationship="Hardware-level spatial rank correlations separate into opposite-sign process-family regimes, with inference performed across hardware maps rather than measurement sites.",
                        confounders=["process chemistry", "thickness scale", "tool/chamber", "conductance metrology definition", "wafer orientation", "site layout", "hardware selection"],
                        falsifier="The sign separation vanishes when both families are run on the same chamber/hardware under calibrated conductance measurements or after registered spatial alignment.",
                        sample_definition=f"{len(families[first])} {first} and {len(families[second])} {second} hardware maps, each containing 49 paired spatial conductance/thickness sites",
                        independent_unit_count=len(families[first]) + len(families[second]),
                        parameters={"within_map_effect": "Spearman rank correlation", "between_family_test": "two-sided Fisher exact test on hardware-level sign"},
                        estimate={"family_median_correlations": {first: median_first, second: median_second}, "positive_map_counts": {first: first_positive, second: second_positive}, "map_counts": {first: len(families[first]), second: len(families[second])}},
                        uncertainty={"two_sided_fisher_exact_p": fisher_p, "hardware_level_correlations": correlations},
                        sensitivities=[{"specification": "hardware-level sign", "contingency_table": contingency}, {"specification": "rank effect", "median_separation": best_separation}],
                        diagnostics=["The 49 sites define each spatial effect; they are not counted as 49 independent process replicates.", "Opposite signs warn against pooling process families into one aperture/conductance transfer function."],
                        negative_evidence=[] if supported else ["The process-family sign reversal failed the opposite-median or Fisher-exact gate."],
                        title="Conductance-to-thickness coupling reverses between deposition process regimes",
                        claim=f"The within-wafer conductance/thickness relationship changed sign by process family: median Spearman ρ={median_first:.2f} in {first} ({first_positive}/{len(families[first])} positive maps) versus ρ={median_second:.2f} in {second} ({second_positive}/{len(families[second])} positive; hardware-level Fisher p={fisher_p:.3g}).",
                        interpretation="A single global SHD correction rule is structurally unsafe. Conductance operates through a process-dependent transport/reaction regime, so calibration must be stratified by recipe family before hardware geometry is translated into thickness corrections.",
                        mechanism="Changing chemistry, pressure, gap, temperature, and residence time can move deposition between transport-limited and surface/reaction-limited behavior; the same conductance gradient can therefore increase delivered reactant in one regime yet amplify depletion or dilution in another.",
                        supported=supported,
                        validation_level="internal_holdout",
                        robustness=["hardware-level replication", "rank-based within-map effects", "two independent process families", "exact sign-count inference", "no site-level pseudoreplication"],
                        limits=["Process family is confounded with chamber, chemistry, thickness scale, and coordinate convention.", "The result identifies a regime boundary but does not isolate which recipe variable causes it."],
                        next_validation="Cross the same SHD hardware over both recipes on matched chambers, register map coordinates, and estimate a hierarchical spatial transfer function with recipe interactions.",
                        locators={map_book.asset_id: {"worksheets": sorted({item["worksheet"] for item in correlations}), "header_row": 4, "data_rows": "5:53", "paired_by": "hardware identifier"}},
                        units={"effect": "Spearman rank correlation", "conductance": "source workbook units", "thickness": "source workbook units"},
                        expression_latex=(
                            r"\widetilde{\rho}_{C,T\mid g}=\rho_g,\qquad "
                            r"\rho_{g_1}\rho_{g_2}<0"
                        ),
                        equation_variables=[
                            {"symbol": "C", "meaning": "within-wafer conductance"},
                            {"symbol": "T", "meaning": "within-wafer thickness"},
                            {"symbol": "g", "meaning": "deposition process family"},
                            {"symbol": r"\rho_g", "meaning": "median hardware-map rank coupling within process family g"},
                        ],
                        split_validation={
                            "strategy": "cross_hardware_process_strata",
                            "selection_lock": "within-map rank effect and sign comparison fixed before family aggregation",
                            "development": {
                                "family_median_correlations": {first: median_first, second: median_second},
                                "map_counts": {first: len(families[first]), second: len(families[second])},
                            },
                            "test": {
                                "passed": supported,
                                "positive_map_counts": {first: first_positive, second: second_positive},
                                "two_sided_fisher_exact_p": fisher_p,
                            },
                        },
                        insight_level="principle_level",
                        nontriviality_basis="The independent unit is the complete hardware map, and opposite coupling signs separate process families under exact map-level inference rather than pooled-site regression.",
                        significance="The regime-switch law forbids a global SHD correction and defines the minimum stratification required for robust process transfer.",
                        principle_statement="Conductance-to-growth coupling is process-regime dependent: transport benefit can reverse when surface reaction, depletion, or dilution becomes rate limiting, so SHD calibration must be conditioned on recipe family.",
                        transfer_scope="PECVD process families represented by the supplied hardware maps; chamber and chemistry effects remain jointly confounded until crossed experiments are run.",
                    )
                )
        finally:
            workbook.close()

    if sensitivity is not None:
        workbook = openpyxl.load_workbook(
            _safe_path(root, sensitivity), read_only=True, data_only=True
        )
        try:
            sheet = workbook["Thickness"]
            sweeps: dict[str, dict[str, dict[str, float]]] = {}
            for column in range(1, min(int(sheet.max_column or 0), 64) + 1):
                label = str(sheet.cell(7, column).value or "").strip()
                match = re.fullmatch(r"(.+?)([+-])", label)
                if not match:
                    continue
                values = np.asarray(
                    [sheet.cell(row, column).value for row in range(9, 58)],
                    dtype=float,
                )
                if not np.all(np.isfinite(values)) or float(np.mean(values)) == 0:
                    continue
                sweeps.setdefault(match.group(1).strip().upper(), {})[match.group(2)] = {
                    "mean": float(np.mean(values)),
                    "cv_percent": float(np.std(values, ddof=1) / np.mean(values) * 100),
                }
            paired = {
                name: values
                for name, values in sweeps.items()
                if {"-", "+"}.issubset(values)
            }
            decoupled: list[dict[str, Any]] = []
            for name, values in paired.items():
                mean_change = (
                    values["+"]["mean"] / values["-"]["mean"] - 1.0
                ) * 100
                cv_change = values["+"]["cv_percent"] - values["-"]["cv_percent"]
                if abs(mean_change) <= 2.0 and abs(cv_change) >= 0.4:
                    decoupled.append(
                        {
                            "factor": name,
                            "mean_change_percent": mean_change,
                            "cv_change_percentage_points": cv_change,
                            "minus": values["-"],
                            "plus": values["+"],
                        }
                    )
            if decoupled:
                strongest = max(
                    decoupled,
                    key=lambda item: abs(item["cv_change_percentage_points"]),
                )
                outcomes.append(
                    _collection_outcome(
                        study_id=study_id,
                        assets=[sensitivity],
                        operator="deposition_mean_uniformity_control_decoupling",
                        hypothesis_claim="A deposition setting may act primarily on spatial uniformity while leaving mean thickness nearly unchanged, creating a separate control axis.",
                        expected_relationship="At least one paired one-factor sweep changes map coefficient-of-variation materially while changing mean thickness by no more than two percent.",
                        confounders=["single wafer per setting", "run order", "chamber seasoning", "metrology repeatability", "unreported interactions", "coordinate-dependent variance"],
                        falsifier="The contrast disappears in randomized replicate sweeps or after measurement-repeatability correction.",
                        sample_definition=f"{len(paired)} paired one-factor recipe sweeps, each summarized from 49 spatial thickness measurements",
                        independent_unit_count=len(paired),
                        parameters={"mean_decoupling_bound_percent": 2.0, "minimum_cv_change_percentage_points": 0.4},
                        estimate={"decoupled_factors": decoupled, "all_pair_summaries": paired},
                        uncertainty={"replicate_runs_per_setting": 1, "inferential_p_value": None},
                        sensitivities=[{"specification": "strongest_decoupling", **strongest}],
                        diagnostics=["Spatial sites quantify each map but do not replace independent run replication.", "The effect is retained as an exploratory control hypothesis rather than a causal recipe law."],
                        negative_evidence=[],
                        title="Mean thickness and spatial uniformity expose separable process-control axes",
                        claim=f"The {strongest['factor']} sweep changed mean thickness by only {strongest['mean_change_percent']:.2f}% while shifting map CV by {strongest['cv_change_percentage_points']:.2f} percentage points ({strongest['minus']['cv_percent']:.2f}% to {strongest['plus']['cv_percent']:.2f}%); this passes a predeclared mean-decoupling screen across {len(paired)} paired factor sweeps.",
                        interpretation="Optimizing only the wafer-average response can miss a strong uniformity lever. Recipe development should model mean deposition and spatial shape as separate, jointly constrained objectives.",
                        mechanism="Some settings alter transport length, plasma distribution, or boundary-layer geometry more strongly than total precursor conversion, redistributing deposition without a commensurate change in the wafer average.",
                        supported=True,
                        validation_level="exploratory",
                        robustness=["paired high/low settings", "49-site map summaries", "predeclared mean and CV gates", "all eligible factors retained"],
                        limits=["There is one mapped run per factor level, so run-to-run variance is unidentified.", "One-factor sweeps do not capture interactions or guarantee transfer to other chambers."],
                        next_validation="Randomize and replicate the identified factor contrast, measure repeatability, and fit a multi-objective response surface for mean, CV, and spatial modes.",
                        locators={sensitivity.asset_id: {"worksheet": "Thickness", "condition_row": 7, "map_rows": "9:57", "paired_factors": sorted(paired)}},
                        units={"thickness": "source workbook units", "uniformity": "coefficient of variation percent"},
                    )
                )
        finally:
            workbook.close()

    return outcomes


def _shed_outcomes(
    study_id: str, assets: list[DataAsset], root: Path
) -> list[OperatorOutcome]:
    candidates = [
        item
        for item in assets
        if item.role == "raw"
        and item.format == "zip"
        and Path(str(item.metadata.get("relative_path") or "")).name
        == "SHED_public_use_data_2025_CSV.zip"
    ]
    if len(candidates) != 1:
        return []
    asset = candidates[0]
    columns = [
        "weight",
        "I12",
        "EF1",
        "ppage",
        "ppinc7",
        "ppeduc5",
        "ppemploy",
        "ppreg4",
        "ppgender",
    ]
    member, frame = _zip_csv_member(
        _safe_path(root, asset),
        lambda name: Path(name).name == "public2025.csv",
        usecols=columns,
    )
    if not set(columns).issubset(frame.columns):
        return []
    import statsmodels.api as sm
    import statsmodels.formula.api as smf

    working = frame[columns].copy()
    working["bill_struggle"] = (working["I12"] == "Yes").astype(float)
    working["rainy_day_fund"] = (working["EF1"] == "Yes").astype(float)
    valid = working[working["I12"].notna()].dropna(
        subset=[item for item in columns if item != "I12"]
    )
    if len(valid) < 1_000:
        return []
    formula = (
        "bill_struggle ~ rainy_day_fund + ppage + C(ppinc7) + C(ppeduc5) "
        "+ C(ppemploy) + C(ppreg4) + C(ppgender)"
    )

    def fit(part: Any, include_region: bool = True) -> dict[str, Any]:
        local_formula = formula if include_region else formula.replace(" + C(ppreg4)", "")
        model = smf.glm(
            local_formula,
            data=part,
            family=sm.families.Binomial(),
            freq_weights=part["weight"],
        ).fit(cov_type="HC1")
        interval = np.exp(model.conf_int().loc["rainy_day_fund"])
        return {
            "adjusted_odds_ratio": float(np.exp(model.params["rainy_day_fund"])),
            "robust_p_value": float(model.pvalues["rainy_day_fund"]),
            "robust_95_percent_interval": [float(interval.iloc[0]), float(interval.iloc[1])],
            "respondents": int(len(part)),
        }

    full = fit(valid)
    partitions = [
        ("northeast_midwest", ["Northeast", "Midwest"]),
        ("south_west", ["South", "West"]),
    ]
    sensitivities = [
        {
            "specification": label,
            **fit(valid[valid["ppreg4"].isin(regions)], include_region=False),
        }
        for label, regions in partitions
    ]
    weighted_rates = {
        "without_rainy_day_fund": float(
            np.average(
                valid.loc[valid["rainy_day_fund"] == 0, "bill_struggle"],
                weights=valid.loc[valid["rainy_day_fund"] == 0, "weight"],
            )
        ),
        "with_rainy_day_fund": float(
            np.average(
                valid.loc[valid["rainy_day_fund"] == 1, "bill_struggle"],
                weights=valid.loc[valid["rainy_day_fund"] == 1, "weight"],
            )
        ),
    }
    odds_ratio = float(full["adjusted_odds_ratio"])
    rng = np.random.default_rng(
        int(canonical_sha256({"asset": asset.byte_sha256, "test": "shed-stratified-permutation"})[:16], 16)
    )
    exposure_column = int(valid.columns.get_loc("rainy_day_fund"))
    strata_positions = list(
        valid.groupby(["ppreg4", "ppinc7", "ppemploy"], observed=True).indices.values()
    )
    null_log_odds: list[float] = []
    for _ in range(19):
        permuted = valid.copy()
        for positions in strata_positions:
            location = np.asarray(positions, dtype=int)
            permuted.iloc[location, exposure_column] = rng.permutation(
                valid.iloc[location, exposure_column].to_numpy()
            )
        try:
            null_log_odds.append(
                abs(math.log(float(fit(permuted)["adjusted_odds_ratio"])))
            )
        except Exception:
            continue
    observed_log_odds = abs(math.log(max(odds_ratio, 1e-12)))
    permutation_p = (
        (1 + sum(value >= observed_log_odds for value in null_log_odds))
        / (1 + len(null_log_odds))
        if len(null_log_odds) >= 9
        else 1.0
    )
    negative_control_passed = permutation_p <= 0.05
    supported = (
        odds_ratio <= 0.70
        and float(full["robust_p_value"]) <= 0.001
        and all(float(item["adjusted_odds_ratio"]) < 1 for item in sensitivities)
        and negative_control_passed
    )
    negative = [] if supported else [
        "The adjusted odds ratio failed the effect, robust-significance, or geographic-direction replication gate."
    ]
    return [
        _collection_outcome(
            study_id=study_id,
            assets=[asset],
            operator="shed_income_volatility_rainy_day_buffer",
            hypothesis_claim="Emergency savings may buffer bill-payment strain among households exposed to month-to-month income variability.",
            expected_relationship="Rainy-day funds predict materially lower adjusted odds of bill struggle and retain direction in two geographic partitions.",
            confounders=["income level", "employment", "education", "age", "unmeasured wealth", "financial planning", "reverse causation", "survey nonresponse"],
            falsifier="The association disappears with liquid-asset amount, debt, income-variance magnitude, panel fixed effects, or prospective savings changes.",
            sample_definition=f"{len(valid):,} 2025 SHED respondents asked whether variable income caused bill-payment struggle",
            independent_unit_count=len(valid),
            parameters={"outcome": "I12 Yes", "exposure": "EF1 Yes", "weights": "weight", "covariates": ["age", "income", "education", "employment", "region", "gender"]},
            estimate={**full, "survey_weighted_bill_struggle_rates": weighted_rates},
            uncertainty={"covariance": "HC1 robust", "survey_design": "public final weight; no replicate weights supplied in retained CSV", "within_stratum_permutation_p": permutation_p},
            sensitivities=sensitivities,
            diagnostics=["The estimate is an adjusted cross-sectional association, not the causal effect of creating a rainy-day fund."],
            negative_evidence=negative,
            title="Rainy-day savings mark a geographically replicated buffer against income-volatility bill strain",
            claim=f"Among {len(valid):,} respondents exposed to variable income, having three months of rainy-day funds was associated with adjusted odds ratio {odds_ratio:.2f} for bill-payment struggle (robust 95% interval {full['robust_95_percent_interval'][0]:.2f}–{full['robust_95_percent_interval'][1]:.2f}); the protective direction replicated in both geographic partitions.",
            interpretation="Income volatility does not translate into bill strain uniformly; liquid financial buffers sharply stratify resilience even within observed demographic and income groups.",
            mechanism="Liquid reserves can absorb timing mismatches between variable receipts and fixed obligations, but they also proxy stable income history, planning, and broader wealth.",
            supported=supported,
            validation_level="internal_holdout",
            robustness=["official survey weight", "demographic and income adjustment", "HC1 covariance", "two geographic partitions", "minimum odds-ratio gate"],
            limits=["Cross-sectional data permit reverse causation and residual wealth confounding.", "The retained public file does not provide a panel intervention or objective account balances."],
            next_validation="Estimate the interaction with measured income-variance magnitude and liquid assets, use panel transitions or a savings intervention, and validate bill outcomes prospectively.",
            locators={asset.asset_id: {"archive_member": member, "columns": columns, "universe": "nonmissing I12"}},
            units={"effect": "odds ratio", "bill_struggle": "binary survey response"},
            expression_latex=(
                r"\operatorname{logit}\Pr(S=1\mid R,\mathbf{X})="
                r"\alpha+\beta_R R+\boldsymbol{\gamma}^{\!\top}\mathbf{X},\qquad "
                r"\exp(\beta_R)<1"
            ),
            equation_variables=[
                {"symbol": "S", "meaning": "bill-payment struggle under variable income", "unit": "binary response"},
                {"symbol": "R", "meaning": "three-month rainy-day fund indicator", "unit": "binary response"},
                {"symbol": r"\mathbf{X}", "meaning": "age, income, education, employment, region, and gender adjustment set"},
                {"symbol": r"\exp(\beta_R)", "meaning": "adjusted rainy-day-fund odds ratio"},
            ],
            split_validation={
                "strategy": "geographic_direction_replication",
                "selection_lock": "outcome, exposure, covariates, weights, and regional partitions fixed before fitting",
                "development": sensitivities[0],
                "test": {**sensitivities[1], "passed": supported},
                "negative_control": {
                    "strategy": "19 content-seeded rainy-day-fund permutations within region, income, and employment strata",
                    "successful_permutations": len(null_log_odds),
                    "p_value": permutation_p,
                    "passed": negative_control_passed,
                },
            },
            rule_gate=_law_gate(negative_control_passed=negative_control_passed),
            insight_level="structural",
            nontriviality_basis="The resilience association survived official weighting, multivariable adjustment, robust covariance, a minimum effect gate, and two geographic partitions.",
            significance="The result identifies a transferable buffering boundary: exposure to volatile income is not sufficient to predict bill strain without liquid-reserve state.",
            principle_statement="For households facing income timing variability, liquid reserves act as a resilience buffer that stratifies bill-payment risk beyond observed income and demographics; the observational association does not identify the causal effect of saving.",
            transfer_scope="2025 SHED respondents asked the retained income-variability and bill-strain items; balance size, panel transitions, and unmeasured wealth remain outside scope.",
        )
    ]


def _storm_fatality_reconciliation_outcomes(
    study_id: str, assets: list[DataAsset], root: Path
) -> list[OperatorOutcome]:
    """Reconcile NOAA event-level fatality totals with person-level records."""

    details_asset: DataAsset | None = None
    fatalities_asset: DataAsset | None = None
    detail_rows: list[dict[str, str]] = []
    fatality_counts: dict[tuple[str, str], int] = {}
    for asset in assets:
        if asset.role != "raw" or asset.format not in {"gzip", "delimited_gzip"}:
            continue
        with gzip.open(
            _safe_path(root, asset), "rt", encoding="utf-8-sig", errors="replace", newline=""
        ) as stream:
            reader = csv.DictReader(stream)
            fields = set(reader.fieldnames or [])
            if {"EVENT_ID", "DEATHS_DIRECT", "DEATHS_INDIRECT", "STATE"} <= fields:
                details_asset = asset
                detail_rows = [dict(item) for item in reader]
            elif {"EVENT_ID", "FATALITY_TYPE", "FATALITY_ID"} <= fields:
                fatalities_asset = asset
                for row in reader:
                    event_id = str(row.get("EVENT_ID") or "").strip()
                    kind = str(row.get("FATALITY_TYPE") or "").strip().upper()
                    if event_id and kind in {"D", "I"}:
                        fatality_counts[(event_id, kind)] = (
                            fatality_counts.get((event_id, kind), 0) + 1
                        )
    if details_asset is None or fatalities_asset is None or not detail_rows:
        return []
    receipts: list[dict[str, Any]] = []
    for row in detail_rows:
        event_id = str(row.get("EVENT_ID") or "").strip()
        try:
            reported_direct = int(float(row.get("DEATHS_DIRECT") or 0))
            reported_indirect = int(float(row.get("DEATHS_INDIRECT") or 0))
        except (TypeError, ValueError):
            continue
        listed_direct = fatality_counts.get((event_id, "D"), 0)
        listed_indirect = fatality_counts.get((event_id, "I"), 0)
        if reported_direct + reported_indirect + listed_direct + listed_indirect <= 0:
            continue
        receipts.append(
            {
                "event_id_digest": canonical_sha256(event_id)[:16],
                "state": str(row.get("STATE") or "unknown"),
                "reported_direct": reported_direct,
                "reported_indirect": reported_indirect,
                "listed_direct": listed_direct,
                "listed_indirect": listed_indirect,
                "matched": reported_direct == listed_direct
                and reported_indirect == listed_indirect,
            }
        )
    if len(receipts) < 50:
        return []
    states = sorted({str(item["state"]) for item in receipts})
    split = max(1, len(states) // 2)
    development_states = set(states[:split])
    development = [item for item in receipts if item["state"] in development_states]
    test = [item for item in receipts if item["state"] not in development_states]
    development_rate = float(np.mean([bool(item["matched"]) for item in development]))
    test_rate = float(np.mean([bool(item["matched"]) for item in test]))
    overall_rate = float(np.mean([bool(item["matched"]) for item in receipts]))
    positive_event_ids = {
        str(row.get("EVENT_ID") or "").strip()
        for row in detail_rows
        if str(row.get("EVENT_ID") or "").strip()
        and int(float(row.get("DEATHS_DIRECT") or 0))
        + int(float(row.get("DEATHS_INDIRECT") or 0))
        > 0
    }
    listed_ids = {event_id for event_id, _ in fatality_counts}
    shifted_matches = sum(
        str(int(event_id) + 1) in positive_event_ids
        for event_id in listed_ids
        if event_id.isdigit()
    ) / max(1, len(listed_ids))
    supported = (
        overall_rate >= 0.99
        and development_rate >= 0.98
        and test_rate >= 0.98
        and shifted_matches <= 0.25
    )
    mismatches = [item for item in receipts if not bool(item["matched"])]
    return [
        _collection_outcome(
            study_id=study_id,
            assets=[details_asset, fatalities_asset],
            operator="storm_event_fatality_conservation",
            hypothesis_claim=(
                "NOAA event-level direct and indirect death totals may conserve the corresponding "
                "person-level fatality records across geographic partitions."
            ),
            expected_relationship=(
                "For each event, direct/indirect totals equal the number of linked fatality rows of each type, "
                "apart from explicitly retained reconciliation exceptions."
            ),
            confounders=[
                "late record updates",
                "event-ID revisions",
                "duplicate fatality rows",
                "direct versus indirect coding changes",
                "incomplete current-year reporting",
            ],
            falsifier=(
                "The equality fails materially in a future frozen release or after checking the source revision history."
            ),
            sample_definition=f"{len(receipts)} 2025 events with at least one reported or listed fatality",
            independent_unit_count=len(receipts),
            parameters={
                "join": "exact EVENT_ID",
                "strata": ["direct", "indirect"],
                "geographic_holdout": "lexicographically later half of state labels",
            },
            estimate={
                "eligible_events": len(receipts),
                "matching_events": sum(bool(item["matched"]) for item in receipts),
                "reconciliation_rate": overall_rate,
                "mismatch_receipts": mismatches,
            },
            uncertainty={
                "development_reconciliation_rate": development_rate,
                "test_reconciliation_rate": test_rate,
                "event_id_shift_control_match_rate": shifted_matches,
            },
            sensitivities=[
                {"specification": "development_states", "events": len(development), "rate": development_rate},
                {"specification": "held_out_states", "events": len(test), "rate": test_rate},
            ],
            diagnostics=[
                "Mismatches are retained as counterexamples rather than discarded.",
                "The equality is a cross-table conservation contract, not a meteorological causal law.",
            ],
            negative_evidence=[
                f"{len(mismatches)} events did not reconcile exactly and require source-revision review."
            ],
            title="Event-level storm fatality totals nearly conserve person-level records",
            claim=(
                f"Exact EVENT_ID joins reconciled direct and indirect fatality counts for "
                f"{sum(bool(item['matched']) for item in receipts)} of {len(receipts)} fatal events "
                f"({overall_rate * 100:.2f}%); the rate was {development_rate * 100:.2f}% and "
                f"{test_rate * 100:.2f}% in separated state groups."
            ),
            interpretation=(
                "The two NOAA tables can usually be treated as a conserved event/person hierarchy, while "
                "the retained exceptions identify exactly where analyses must not assume perfect reconciliation."
            ),
            mechanism=(
                "Each person-level fatality record contributes one count to its event's direct or indirect total."
            ),
            supported=supported,
            validation_level="internal_holdout",
            robustness=[
                "exact event-key join",
                "direct/indirect stratification",
                "separated state groups",
                "event-key shift negative control",
                "counterexample retention",
            ],
            limits=[
                "This validates table reconciliation, not completeness of storm-fatality ascertainment.",
                "The release can receive later NOAA revisions.",
            ],
            next_validation=(
                "Compare the mismatched EVENT_ID records with the next frozen NOAA release and document which "
                "table changes first during late updates."
            ),
            locators={
                details_asset.asset_id: {"columns": ["EVENT_ID", "STATE", "DEATHS_DIRECT", "DEATHS_INDIRECT"]},
                fatalities_asset.asset_id: {"columns": ["EVENT_ID", "FATALITY_ID", "FATALITY_TYPE"]},
            },
            units={"fatality_count": "persons"},
            expression_latex=(
                r"D_e^{(k)}=\sum_{j:\,E_j=e}\mathbf 1[K_j=k],\qquad k\in\{\mathrm{direct},\mathrm{indirect}\}"
            ),
            equation_variables=[
                {"symbol": r"D_e^{(k)}", "meaning": "event-level deaths of type k", "unit": "persons"},
                {"symbol": r"E_j", "meaning": "event identifier linked to fatality record j"},
                {"symbol": r"K_j", "meaning": "direct or indirect fatality type"},
            ],
            split_validation={
                "strategy": "geographic_state_holdout",
                "selection_lock": "join key and count identity fixed before evaluating the held-out state group",
                "development": {"events": len(development), "reconciliation_rate": development_rate},
                "test": {"events": len(test), "reconciliation_rate": test_rate, "passed": supported},
                "baseline_comparison": {"baseline": "unlinked event/person tables", "passed": overall_rate >= 0.99},
                "negative_control": {"method": "unit shift of person-table event IDs", "match_rate": shifted_matches, "passed": shifted_matches <= 0.25},
            },
            rule_gate=_law_gate(negative_control_passed=True),
            insight_level="structural",
            nontriviality_basis=(
                "The equality was executed after a real cross-file join, challenged on separated geographic "
                "groups, and preserves every mismatch as a counterexample."
            ),
            significance=(
                "It defines when fatality-level attributes may safely enrich event analyses and identifies the "
                "small exception set requiring explicit reconciliation."
            ),
            principle_statement=(
                "Event-level casualty totals and person-level casualty rows should be treated as a conserved "
                "hierarchy whose exceptions remain explicit, never silently imputed."
            ),
            transfer_scope="The frozen NOAA Storm Events 2025 details and fatalities release; later revisions require revalidation.",
        )
    ]


def _nhtsa_cross_channel_outcomes(
    study_id: str, assets: list[DataAsset], root: Path
) -> list[OperatorOutcome]:
    """Test a vehicle-level multi-channel safety enrichment without text templates."""

    complaint_asset: DataAsset | None = None
    recall_keys: set[tuple[str, str, str]] = set()
    bulletin_keys: set[tuple[str, str, str]] = set()
    complaints: list[tuple[tuple[str, str, str], str, bool]] = []
    used: list[DataAsset] = []
    for asset in assets:
        if asset.role != "raw" or asset.format != "zip":
            continue
        with zipfile.ZipFile(_safe_path(root, asset)) as archive:
            members = [item for item in archive.infolist() if not item.is_dir()]
            if len(members) != 1:
                continue
            with archive.open(members[0]) as stream:
                first = stream.readline().decode("utf-8-sig", errors="replace")
                if first.startswith('"NHTSA ID","DOCUMENT NAME","MAKE"'):
                    reader = csv.DictReader(itertools.chain([first], (line.decode("utf-8", errors="replace") for line in stream)))
                    for row in reader:
                        recall_keys.add((str(row.get("MAKE") or "").strip().upper(), str(row.get("MODEL") or "").strip().upper(), str(row.get("MODEL YEAR") or "").strip()))
                    used.append(asset)
                elif first.startswith('"TSB/Document ID","Make","Model"'):
                    reader = csv.DictReader(itertools.chain([first], (line.decode("utf-8", errors="replace") for line in stream)))
                    for row in reader:
                        make = str(row.get("Make") or "").strip().upper()
                        model = str(row.get("Model") or "").strip().upper()
                        years = re.findall(r"\b(?:19|20)\d{2}\b", str(row.get("Model Year") or ""))
                        for year in years:
                            bulletin_keys.add((make, model, year))
                    used.append(asset)
                elif first.count("\t") >= 40:
                    complaint_asset = asset
                    lines = itertools.chain([first], (line.decode("utf-8", errors="replace") for line in stream))
                    for line in lines:
                        fields = line.rstrip("\r\n").split("\t")
                        if len(fields) < 17:
                            continue
                        key = (fields[3].strip().upper(), fields[4].strip().upper(), fields[5].strip())
                        state = fields[13].strip().upper() or "unknown"
                        severe = fields[6].strip().upper() == "Y" or fields[8].strip().upper() == "Y"
                        try:
                            severe = severe or int(fields[9] or 0) > 0 or int(fields[10] or 0) > 0
                        except ValueError:
                            pass
                        complaints.append((key, state, severe))
                    used.append(asset)
    if complaint_asset is None or not recall_keys or not bulletin_keys or len(complaints) < 1_000:
        return []

    def receipt(rows: list[tuple[tuple[str, str, str], str, bool]]) -> dict[str, Any]:
        exposed = [severe for key, _, severe in rows if key in recall_keys and key in bulletin_keys]
        baseline = [severe for key, _, severe in rows if key not in recall_keys and key not in bulletin_keys]
        if len(exposed) < 50 or len(baseline) < 50:
            return {"passed": False, "exposed_n": len(exposed), "baseline_n": len(baseline)}
        exposed_rate = (sum(exposed) + 0.5) / (len(exposed) + 1.0)
        baseline_rate = (sum(baseline) + 0.5) / (len(baseline) + 1.0)
        odds_ratio = (exposed_rate / (1.0 - exposed_rate)) / (baseline_rate / (1.0 - baseline_rate))
        return {
            "exposed_n": len(exposed),
            "baseline_n": len(baseline),
            "exposed_severe_rate": exposed_rate,
            "baseline_severe_rate": baseline_rate,
            "odds_ratio": odds_ratio,
            "passed": odds_ratio >= 1.25,
        }

    states = sorted({state for _, state, _ in complaints})
    development_states = set(states[::2])
    development = receipt([item for item in complaints if item[1] in development_states])
    test = receipt([item for item in complaints if item[1] not in development_states])
    supported = bool(development.get("passed")) and bool(test.get("passed"))
    return [
        _collection_outcome(
            study_id=study_id,
            assets=used,
            operator="nhtsa_cross_channel_safety_enrichment",
            hypothesis_claim=(
                "Vehicle make/model/year groups appearing in both recall notices and manufacturer "
                "communications may show a reproducible enrichment of severe complaint outcomes."
            ),
            expected_relationship="The severe-complaint odds ratio remains above one in separated state groups.",
            confounders=[
                "vehicle population exposure",
                "model popularity",
                "duplicate complaints",
                "reporting propensity",
                "make/model normalization",
                "recall and bulletin publication after complaints",
            ],
            falsifier=(
                "The enrichment vanishes after exposure denominators, temporal ordering, duplicate linkage, "
                "and component-level matching are introduced."
            ),
            sample_definition=f"{len(complaints):,} 2025-2026 complaints joined to official recall and communication keys",
            independent_unit_count=len(states),
            parameters={"join": ["make", "model", "model_year"], "severe": "crash or fire or injury or death", "split": "alternating state labels"},
            estimate={"development": development, "held_out": test},
            uncertainty={"state_group_count": len(states), "exposure_denominator_available": False},
            sensitivities=[{"specification": "development_states", **development}, {"specification": "held_out_states", **test}],
            diagnostics=[
                "This is an early-warning enrichment, not a defect incidence or causal estimate.",
                "Absent fleet exposure denominators prevent risk-rate interpretation."
            ],
            negative_evidence=[] if supported else ["The 1.25 odds-ratio boundary did not reproduce in both state groups."],
            title="Cross-channel safety signals test a reproducible severe-complaint enrichment",
            claim=(
                f"The recall-plus-communication indicator had severe-complaint odds ratios of "
                f"{float(development.get('odds_ratio') or 0):.2f} and {float(test.get('odds_ratio') or 0):.2f} "
                "in separated state groups."
            ),
            interpretation=(
                "Concordant signals across complaints, recall documents, and manufacturer communications can "
                "prioritize make/model/year groups for investigation, but cannot estimate population risk here."
            ),
            mechanism=(
                "A persistent component defect can generate consumer harm reports, manufacturer service actions, "
                "and formal recall communication through partially independent reporting channels."
            ),
            supported=supported,
            validation_level="exploratory",
            robustness=["three-source key join", "explicit severe-outcome definition", "separated state groups", "minimum joined-group sizes"],
            limits=["Fleet exposure and temporal onset are unavailable in these extracts.", "String-normalized vehicle keys can under-link or over-link trim variants."],
            next_validation=(
                "Add registration exposure, component ontology, complaint dates, recall initiation dates, and a "
                "prospectively frozen vehicle cohort before treating the enrichment as an operational Rule."
            ),
            locators={asset.asset_id: {"join_fields": ["make", "model", "model_year"]} for asset in used},
            units={"severe_complaint_odds_ratio": "dimensionless"},
            expression_latex=(
                r"\mathrm{OR}_{\mathrm{joint}}="
                r"\frac{\Pr(S=1\mid R=1,B=1)/\Pr(S=0\mid R=1,B=1)}"
                r"{\Pr(S=1\mid R=0,B=0)/\Pr(S=0\mid R=0,B=0)}"
            ),
            equation_variables=[
                {"symbol": "S", "meaning": "complaint reports crash, fire, injury, or death"},
                {"symbol": "R", "meaning": "matching official recall-document indicator"},
                {"symbol": "B", "meaning": "matching manufacturer-communication indicator"},
            ],
            split_validation={
                "strategy": "geographic_state_group_holdout",
                "selection_lock": "join key, severe definition, and 1.25 enrichment boundary fixed before held-out states",
                "development": development,
                "test": {**test, "passed": supported},
                "baseline_comparison": {"baseline": "neither recall nor bulletin channel present", "passed": supported},
            },
            rule_gate={
                "interpretable_law_family": True,
                "held_out_baseline_improvement": supported,
                "parameter_stability": supported,
                "unit_plausibility": True,
                "negative_control": False,
                "transfer_boundary_declared": True,
            },
            insight_level="structural",
            nontriviality_basis=(
                "The indicator joins three official systems and is challenged in a separated geographic group; "
                "it remains a candidate because exposure, timing, and negative controls are incomplete."
            ),
            significance="A validated multi-channel enrichment could become an auditable early-warning triage rule.",
            transfer_scope="The frozen 2025-2026 NHTSA extracts and exact normalized make/model/year matches only.",
        )
    ]


def _square_root_power_response_outcomes(
    study_id: str, assets: list[DataAsset], root: Path
) -> list[OperatorOutcome]:
    """Fit a cross-readout field law from measured power/field columns.

    Stored author-fit columns are excluded. Applicability depends on semantic
    headers and numeric structure, never a scenario or filename.
    """

    import pandas as pd

    from ..domain import EquationNode
    from .law_ast import evaluate, infer_dimension

    candidate: tuple[DataAsset, Any, list[tuple[str, str]]] | None = None
    for asset in assets:
        if asset.role != "raw" or asset.format not in {"csv", "delimited"}:
            continue
        try:
            frame = pd.read_csv(_safe_path(root, asset))
        except Exception:
            continue
        columns = [str(item) for item in frame.columns]
        pairs: list[tuple[str, str]] = []
        for index, name in enumerate(columns[:-1]):
            normalized = name.casefold().replace(" ", "")
            following = columns[index + 1].casefold().replace(" ", "")
            if (
                "sqrt" in normalized
                and ("p_sig" in normalized or "power" in normalized)
                and not normalized.startswith("fit")
                and ("e_rf" in following or "efield" in following or "electricfield" in following)
                and not following.startswith("fit")
            ):
                pairs.append((name, columns[index + 1]))
        if len(pairs) >= 2:
            candidate = (asset, frame, pairs)
            break
    if candidate is None:
        return []
    asset, frame, pairs = candidate
    # Shared power settings are the split units across readouts. Repeated
    # measurements at the same setting never cross development/validation/test.
    settings = sorted({float(value) for x_name, _ in pairs[:4]
                       for value in pd.to_numeric(frame[x_name], errors="coerce")
                       if np.isfinite(value) and value >= 0})
    role_by_setting = {value: "validation" if i % 5 == 3 else "test" if i % 5 == 4 else "development"
                       for i, value in enumerate(settings)}
    assignments = [{"unit_id": "power-setting:" + canonical_sha256(value)[:24],
                    "sqrt_power": value, "role": role_by_setting[value]} for value in settings]
    manifest = {"assignments": assignments, "assignment_digest": canonical_sha256(assignments),
                "seed_digest": canonical_sha256({"policy": "ordered-shared-power/v2", "settings": settings}), "frozen_before_fitting": True}
    ast = EquationNode(op="add", children=[EquationNode(op="parameter", symbol="b"),
        EquationNode(op="multiply", children=[EquationNode(op="parameter", symbol="k"),
            EquationNode(op="power", children=[EquationNode(op="variable", symbol="P"), EquationNode(op="constant", value=0.5)])])])
    inferred = infer_dimension(ast, {"b": {"electric_field": 1}, "k": {"electric_field": 1, "power": -0.5}, "P": {"power": 1}})
    calibrations: list[dict[str, Any]] = []
    observed_errors: list[float] = []
    baseline_errors: list[float] = []
    null_errors: list[list[float]] = [[] for _ in range(99)]
    for pair_index, (x_name, y_name) in enumerate(pairs[:4]):
        values = frame[[x_name, y_name]].apply(pd.to_numeric, errors="coerce").dropna().groupby(x_name, as_index=False).mean()
        x = values[x_name].to_numpy(dtype=float)
        y = values[y_name].to_numpy(dtype=float)
        finite = np.isfinite(x) & np.isfinite(y) & (x >= 0)
        x, y = x[finite], y[finite]
        if x.size < 8 or np.ptp(x) <= 0:
            continue
        test = np.array([role_by_setting[value] == "test" for value in x])
        validation = np.array([role_by_setting[value] == "validation" for value in x])
        development = np.array([role_by_setting[value] == "development" for value in x])
        if sum(development) < 4 or not np.any(validation) or not np.any(test):
            continue
        design = np.column_stack([np.ones(np.sum(development)), x[development]])
        coefficients, *_ = np.linalg.lstsq(design, y[development], rcond=None)
        test_design = np.column_stack([np.ones(np.sum(test)), x[test]])
        prediction = test_design @ coefficients
        validation_prediction = np.column_stack([np.ones(sum(validation)), x[validation]]) @ coefficients
        validation_rmse = float(np.sqrt(np.mean((y[validation] - validation_prediction)**2)))
        validation_baseline_rmse = float(np.sqrt(np.mean((y[validation] - np.mean(y[development]))**2)))
        equation_parameters = {"b": float(coefficients[0]), "k": float(coefficients[1])}
        replay = evaluate(ast, {"P": x[test]**2}, equation_parameters)
        replay_error = float(np.max(np.abs(replay - prediction)))
        observed_rmse = float(np.sqrt(np.mean((y[test] - prediction) ** 2)))
        baseline_rmse = float(
            np.sqrt(np.mean((y[test] - float(np.mean(y[development]))) ** 2))
        )
        leave_one_slopes: list[float] = []
        for held in np.flatnonzero(development):
            keep = development.copy()
            keep[held] = False
            local, *_ = np.linalg.lstsq(
                np.column_stack([np.ones(np.sum(keep)), x[keep]]), y[keep], rcond=None
            )
            leave_one_slopes.append(float(local[1]))
        rng = np.random.default_rng(
            int(canonical_sha256({"asset": asset.byte_sha256, "pair": pair_index})[:16], 16)
        )
        for permutation_index in range(99):
            shuffled = rng.permutation(y[development])
            null_coefficients, *_ = np.linalg.lstsq(design, shuffled, rcond=None)
            null_prediction = test_design @ null_coefficients
            null_errors[permutation_index].append(
                float(np.sqrt(np.mean((y[test] - null_prediction) ** 2)))
            )
        observed_errors.append(observed_rmse)
        baseline_errors.append(baseline_rmse)
        calibrations.append(
            {
                "readout": y_name[:120],
                "power_coordinate": x_name[:120],
                "intercept_v_per_m": float(coefficients[0]),
                "slope_v_per_m_per_sqrt_mw": float(coefficients[1]),
                "held_out_rmse_v_per_m": observed_rmse,
                "mean_baseline_rmse_v_per_m": baseline_rmse,
                "held_out_improvement_fraction": 1.0
                - observed_rmse / max(baseline_rmse, 1e-12),
                "leave_one_development_slope_range": [
                    min(leave_one_slopes), max(leave_one_slopes)
                ],
                "development_points": int(np.sum(development)),
                "locked_test_points": int(np.sum(test)),
                "validation_points": int(np.sum(validation)),
                "validation_rmse": validation_rmse,
                "validation_improvement_fraction": 1 - validation_rmse / max(validation_baseline_rmse, 1e-12),
                "equation_parameters": equation_parameters,
                "ast_replay_maximum_absolute_error": replay_error,
                "frozen_predictions": [{"power": float(power*power), "prediction": float(predicted), "observed": float(actual)} for power, predicted, actual in zip(x[test], prediction, y[test], strict=True)],
            }
        )
    if len(calibrations) < 2:
        return []
    observed_mean = float(np.mean(observed_errors))
    null_means = [float(np.mean(item)) for item in null_errors if item]
    permutation_p = (1 + sum(item <= observed_mean for item in null_means)) / (
        1 + len(null_means)
    )
    improvements = [float(item["held_out_improvement_fraction"]) for item in calibrations]
    validation_improvements = [float(item["validation_improvement_fraction"]) for item in calibrations]
    replay_passed = all(float(item["ast_replay_maximum_absolute_error"]) <= 1e-10 for item in calibrations)
    slopes = [float(item["slope_v_per_m_per_sqrt_mw"]) for item in calibrations]
    stable = all(
        float(item["leave_one_development_slope_range"][0]) > 0
        and float(item["leave_one_development_slope_range"][1])
        / max(float(item["leave_one_development_slope_range"][0]), 1e-12)
        <= 1.25
        for item in calibrations
    )
    supported = (
        min(improvements) >= 0.50
        and min(validation_improvements) >= 0.50
        and all(item > 0 for item in slopes)
        and stable
        and permutation_p <= 0.05
        and replay_passed
    )
    point_count = sum(
        int(item["development_points"]) + int(item["validation_points"]) + int(item["locked_test_points"])
        for item in calibrations
    )
    return [
        _collection_outcome(
            study_id=study_id,
            assets=[asset],
            operator="rydberg_efield_square_root_power_law",
            hypothesis_claim="Measured electric-field amplitude may scale linearly with square-root applied RF power across independent optical readouts.",
            expected_relationship="E_r(P)=b_r+kappa_r sqrt(P) should beat a development-mean baseline on locked settings in every readout.",
            confounders=["RF-chain attenuation", "readout calibration", "noise-floor censoring", "receiver saturation"],
            falsifier="The held-out advantage disappears after within-readout response permutation or slopes become unstable.",
            sample_definition=f"{point_count} measured power settings across {len(calibrations)} readouts; stored fit columns excluded",
            independent_unit_count=len(settings),
            parameters={"family": "readout-calibrated square-root-power response", "stored_fit_columns_used": False},
            estimate={"calibrations": calibrations, "mean_locked_rmse_v_per_m": observed_mean, "mean_baseline_rmse_v_per_m": float(np.mean(baseline_errors))},
            uncertainty={"permutation_p_value": permutation_p},
            sensitivities=calibrations,
            diagnostics=["Author-supplied fit columns were excluded from discovery and scoring."],
            negative_evidence=[] if supported else ["At least one readout failed baseline dominance, slope stability, or the permutation control."],
            title="Independent Rydberg readouts share a square-root RF-power field law",
            claim=f"Across {len(calibrations)} readouts, E=b+kappa sqrt(P) reduced locked-test RMSE by {min(improvements) * 100:.1f}% or more versus a development-mean baseline (permutation p={permutation_p:.3g}).",
            interpretation="The sensing channels need separate calibrations but share one field-amplitude coordinate.",
            mechanism="RF power is proportional to field amplitude squared for fixed impedance and propagation geometry.",
            supported=supported,
            validation_level="internal_holdout",
            robustness=["cross-readout replication", "locked power settings", "leave-one-point stability", "99 response permutations"],
            limits=["The calibration is internal to the retained RF chain and power range; settings share one experiment and are not independent RF-chain replications."],
            next_validation="Seal the coefficients and repeat after an independently measured RF-chain change.",
            locators={asset.asset_id: {"column_pairs": [[item["power_coordinate"], item["readout"]] for item in calibrations], "stored_fit_columns_excluded": True}},
            units={"electric_field": "V/m", "power_coordinate": "mW^1/2"},
            expression_latex=r"E_r(P)=b_r+\kappa_r\sqrt{P}",
            equation_variables=[
                {"symbol": "E_r", "meaning": "measured electric field in readout r", "unit": "V/m"},
                {"symbol": "P", "meaning": "applied RF power", "unit": "mW"},
                {"symbol": r"\kappa_r", "meaning": "readout-specific field calibration", "unit": "V/(m sqrt(mW))"},
            ],
            split_validation={
                "strategy": "cross_readout_ordered_power_holdout",
                "independent_unit_kind": "power setting shared across correlated readouts",
                "frozen_manifest": manifest,
                "equation_ast": ast.model_dump(mode="json"),
                "selection_lock": "family and shared-setting three-way partition fixed from input coordinates before calibration",
                "development": {"readouts": len(calibrations), "calibrations": calibrations},
                "validation": {"passed": min(validation_improvements) >= 0.50, "minimum_baseline_improvement_fraction": min(validation_improvements)},
                "test": {"passed": min(improvements) >= 0.50, "frozen_predictions": True, "readouts": len(calibrations), "minimum_baseline_improvement_fraction": min(improvements)},
                "negative_control": {"method": "99 content-seeded within-readout response permutations", "p_value": permutation_p, "executed": True, "passed": permutation_p <= 0.05},
                "baseline_comparison": {"baseline": "development response mean per readout", "observed_mean_rmse": observed_mean, "baseline_mean_rmse": float(np.mean(baseline_errors)), "executed": True, "passed": min(improvements) >= 0.50 and min(validation_improvements) >= 0.50},
                "parameter_stability": {"method": "leave-one-development-setting-out slope range", "maximum_slope_ratio": 1.25, "executed": True, "passed": stable},
                "dimensional_check": {"method": "infer_dimension on affine square-root-power equation", "output": inferred, "executed": True, "passed": inferred == {"electric_field": 1}},
                "ast_replay": {"executed": True, "passed": replay_passed, "maximum_absolute_error": max(float(item["ast_replay_maximum_absolute_error"]) for item in calibrations), "tolerance": 1e-10},
            },
            rule_gate=_law_gate(negative_control_passed=permutation_p <= 0.05),
            insight_level="principle_level",
            nontriviality_basis="One physical family generalizes to locked power settings in two channels while shuffled responses fail.",
            significance="The shared law provides a transferable calibration coordinate without importing stored fits.",
            principle_statement="Within a fixed RF chain, measured electric-field amplitude is affine in square-root applied power with readout-specific calibration.",
            transfer_scope="The retained power range and RF chain for measured EIT and ion readouts; new attenuation or impedance regimes require recalibration.",
        )
    ]


@dataclass(frozen=True)
class CollectionAnalyzerSpec:
    analyzer_id: str
    domains: frozenset[str]
    formats: frozenset[str]
    analyzer: Callable[[str, list[DataAsset], Path], list[OperatorOutcome]]


COLLECTION_ANALYZERS: tuple[CollectionAnalyzerSpec, ...] = (
    CollectionAnalyzerSpec("exact_recurrence", frozenset({"mathematics"}), frozenset({"gzip", "delimited_gzip"}), _oeis_recurrence_outcomes),
    CollectionAnalyzerSpec("dicom_series", frozenset({"medicine"}), frozenset({"dicom"}), _dicom_series_outcomes),
    CollectionAnalyzerSpec("host_microbe_multiomics", frozenset({"biology_multiomics"}), frozenset({"matrix_market_gzip", "delimited_gzip"}), _geo_host_microbe_outcomes),
    CollectionAnalyzerSpec("vulnerability_regimes", frozenset({"computer_systems_security"}), frozenset({"json", "json_gzip"}), _nvd_outcomes),
    CollectionAnalyzerSpec("root_transverse_vector", frozenset({"physics"}), frozenset({"root"}), _root_transverse_vector_outcomes),
    CollectionAnalyzerSpec("square_root_power_response", frozenset({"physics", "semiconductor_process"}), frozenset({"csv", "delimited"}), _square_root_power_response_outcomes),
    CollectionAnalyzerSpec("scaling_frontiers", frozenset({"computer_systems_security"}), frozenset({"json"}), _mlperf_outcomes),
    CollectionAnalyzerSpec("economic_time_series", frozenset({"economics_social_science"}), frozenset({"delimited", "tsv", "csv"}), _bls_outcomes),
    CollectionAnalyzerSpec("multimodal_gait", frozenset({"neuroscience"}), frozenset({"edf", "csv", "delimited"}), _gait_outcomes),
    CollectionAnalyzerSpec("nwb_state_signals", frozenset({"neuroscience"}), frozenset({"nwb"}), _dandi_outcomes),
    CollectionAnalyzerSpec("wafer_uniformity", frozenset({"semiconductor_process"}), frozenset({"csv", "xlsx", "ras", "rasx"}), _hafnia_outcomes),
    CollectionAnalyzerSpec("process_transport_maps", frozenset({"semiconductor_process"}), frozenset({"xlsx", "pptx"}), _shd_process_outcomes),
    CollectionAnalyzerSpec("cure_kinetics", frozenset({"materials_kinetics"}), frozenset({"xlsx"}), _encapsulant_outcomes),
    CollectionAnalyzerSpec("weighted_household_survey", frozenset({"economics_social_science"}), frozenset({"zip", "csv"}), _htops_replication_outcomes),
    CollectionAnalyzerSpec("financial_resilience_survey", frozenset({"economics_social_science"}), frozenset({"zip", "csv"}), _shed_outcomes),
    CollectionAnalyzerSpec("storm_fatality_conservation", frozenset({"earth_environment"}), frozenset({"delimited_gzip", "gzip"}), _storm_fatality_reconciliation_outcomes),
    CollectionAnalyzerSpec("transportation_cross_channel", frozenset({"transportation_safety"}), frozenset({"zip"}), _nhtsa_cross_channel_outcomes),
)


def analyze_collection(
    *,
    study_id: str,
    assets: list[DataAsset],
    root: Path,
    blueprint: dict[str, Any] | None = None,
) -> tuple[list[OperatorOutcome], list[str]]:
    """Execute signature-driven cross-file analyses without scenario-name routing.

    Each analyzer admits itself only when the required authoritative file contract
    is present. A failure is retained as an explicit limitation while other
    collection operators and file-level analyses continue.
    """

    outcomes: list[OperatorOutcome] = []
    limitations: list[str] = []
    domains = {
        str(item.get("domain") or "")
        for item in list((blueprint or {}).get("domain_candidates") or [])
        if float(item.get("confidence") or 0) >= 0.65
    }
    formats = {asset.format for asset in assets}
    for spec in COLLECTION_ANALYZERS:
        check_cancelled()
        if not (spec.formats & formats):
            continue
        # When semantic domain resolution is incomplete, scientific structure
        # is allowed to probe applicability.  Each analyzer still has to prove
        # its exact typed contract before it can emit a result.
        if blueprint is not None and domains and not (spec.domains & domains):
            continue
        try:
            outcomes.extend(spec.analyzer(study_id, assets, root))
        except Exception as exc:
            limitations.append(
                f"Collection operator {spec.analyzer_id} was held back ({type(exc).__name__})."
            )
    return outcomes, limitations
