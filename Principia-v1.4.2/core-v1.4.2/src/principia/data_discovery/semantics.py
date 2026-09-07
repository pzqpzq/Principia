from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from typing import Any

from ..domain import DatasetAlignment, DataView, StudyBlueprintV2, canonical_sha256


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^a-z0-9]+", value.casefold())
        if token
    }


_WEIGHT = {"weight", "weights", "pweight", "perwt", "surveyweight", "sampleweight"}
_TIME = {
    "time", "timestamp", "date", "datetime", "year", "month", "day", "hour",
    "mjd", "jd", "epoch", "period", "frame", "duration",
}
_COORDINATE = {
    "lat", "latitude", "lon", "longitude", "ra", "dec", "radius", "depth",
    "altitude", "elevation", "wavelength", "frequency", "energy", "slice",
}
_UNIT_IDENTIFIERS = {
    "subject", "participant", "patient", "sample", "specimen", "wafer", "device",
    "sensor", "station", "site", "chamber", "household", "respondent", "target",
    "star", "event", "visit", "session", "animal", "cell", "barcode", "hardware",
}
_CATEGORY = {
    "group", "condition", "treatment", "control", "class", "type", "status", "state",
    "region", "area", "species", "sex", "gender", "race", "ethnicity", "occupation",
    "industry", "process", "recipe", "modality", "instrument", "diagnosis", "severity",
}
_MEASUREMENT = {
    "signal", "strain", "flux", "intensity", "amplitude", "power", "phase", "expression",
    "abundance", "count", "counts", "concentration", "temperature", "pressure", "thickness",
    "index", "score", "value", "response", "outcome", "rate", "ratio", "damage", "injury",
    "fatality", "employment", "price", "latency", "throughput", "performance", "cadence",
    "force", "velocity", "acceleration", "conductance", "conversion", "viscosity", "modulus",
}
_ID_SHAPES = re.compile(r"(^id$|_id$|^id_|uuid|identifier|accession|serial|record_?number|index$)")

_DOMAIN_SIGNALS: dict[str, set[str]] = {
    "semiconductor_process": {
        "pecvd", "deposition", "wafer", "film", "thickness", "chamber", "recipe",
        "plasma", "rf", "shd", "uniformity", "refractive", "hafnia", "hfo2",
    },
    "materials_kinetics": {
        "cure", "conversion", "rheology", "raman", "ftir", "calorimetry", "viscosity",
        "modulus", "kinetic", "temperature", "encapsulant", "polymer",
    },
    "astronomy": {
        "tess", "tic", "stellar", "star", "flux", "lightcurve", "cadence", "sector",
        "mjd", "ra", "dec", "periodicity",
    },
    "neuroscience": {
        "eeg", "emg", "nwb", "neuron", "axon", "pupil", "cortical", "gait",
        "electrode", "acetylcholine", "brain",
    },
    "biology_multiomics": {
        "barcode", "gene", "expression", "microbial", "cell", "protein", "feature",
        "matrix", "infection", "specimen",
    },
    "medicine": {
        "patient", "clinical", "diagnosis", "dicom", "mri", "imaging", "hospital",
        "treatment", "outcome", "visit",
    },
    "economics_social_science": {
        "survey", "respondent", "household", "weight", "employment", "income", "cpi",
        "housing", "financial", "questionnaire",
    },
    "earth_environment": {
        "latitude", "longitude", "earthquake", "climate", "ocean", "storm", "coral",
        "anomaly", "netcdf", "geospatial",
    },
    "computer_systems_security": {
        "vulnerability", "cve", "cvss", "cwe", "latency", "throughput", "accelerator",
        "benchmark", "inference", "power",
    },
    "transportation_safety": {
        "vehicle", "automotive", "recall", "complaint", "nhtsa", "manufacturer",
        "crash", "fire", "injury", "defect", "model year",
    },
    "mathematics": {"sequence", "integer", "recurrence", "generating", "oeis", "term"},
    "physics": {
        "strain", "detector", "gravitational", "event", "energy", "particle", "root",
        "higgs", "lepton",
    },
}

_MISSING_LABELS = {
    "missing", "not_available", "not_applicable", "unknown", "refused", "dont_know",
    "suppressed", "blank", "na", "n_a",
}


def classify_variable(name: str) -> dict[str, Any]:
    """Conservatively infer a planning role from a schema label, never evidence."""

    normalized = re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")
    tokens = _tokens(name)
    if normalized in _WEIGHT or tokens & _WEIGHT:
        return {
            "name": name, "role": "survey_weight", "confidence": 0.98,
            "scientific_use": "design_only", "reason": "weight-labelled field",
        }
    if normalized.endswith("_index") and tokens & {"sample", "frame", "time", "epoch"}:
        return {
            "name": name, "role": "time_coordinate", "confidence": 0.80,
            "scientific_use": "coordinate_or_split",
            "reason": "ordered sample/frame index",
        }
    unit_tokens = tokens & _UNIT_IDENTIFIERS
    if unit_tokens and (_ID_SHAPES.search(normalized) or "barcode" in tokens):
        return {
            "name": name, "role": "independent_unit_identifier", "confidence": 0.90,
            "scientific_use": "grouping_only",
            "reason": f"identifier for {sorted(unit_tokens)[0]}",
        }
    if _ID_SHAPES.search(normalized):
        return {
            "name": name, "role": "identifier", "confidence": 0.92,
            "scientific_use": "prohibited_as_variable", "reason": "identifier-shaped field",
        }
    if tokens & _TIME:
        return {
            "name": name, "role": "time_coordinate", "confidence": 0.88,
            "scientific_use": "coordinate_or_split", "reason": "time-labelled field",
        }
    if tokens & _COORDINATE:
        return {
            "name": name, "role": "spatial_or_physical_coordinate", "confidence": 0.82,
            "scientific_use": "coordinate_or_split", "reason": "coordinate-labelled field",
        }
    if tokens & _CATEGORY:
        return {
            "name": name, "role": "group_or_condition", "confidence": 0.78,
            "scientific_use": "stratification_or_adjustment",
            "reason": "condition/category-labelled field",
        }
    if tokens & _MEASUREMENT:
        return {
            "name": name, "role": "measurement_candidate", "confidence": 0.74,
            "scientific_use": "requires_unit_and_design_validation",
            "reason": "measurement-labelled field",
        }
    return {
        "name": name, "role": "unknown", "confidence": 0.25,
        "scientific_use": "requires_semantic_binding",
        "reason": "schema label is not scientifically self-describing",
    }


def compile_dataset_semantics(views: Iterable[DataView]) -> dict[str, Any]:
    cards: list[dict[str, Any]] = []
    role_counts: Counter[str] = Counter()
    independent_candidates: list[dict[str, str]] = []
    split_votes: Counter[str] = Counter()
    prohibited: list[dict[str, str]] = []
    for view in views:
        variables = list(dict.fromkeys([*view.variables, *view.keys]))[:5_000]
        bindings = [classify_variable(name) for name in variables]
        for binding in bindings:
            role = str(binding["role"])
            role_counts[role] += 1
            if role == "independent_unit_identifier":
                independent_candidates.append(
                    {"view_id": view.view_id, "variable": str(binding["name"])}
                )
                split_votes["group"] += 3
            elif role == "time_coordinate":
                split_votes["chronological"] += 2
            elif role == "spatial_or_physical_coordinate":
                split_votes["spatial_block"] += 1
            if binding["scientific_use"] == "prohibited_as_variable":
                prohibited.append(
                    {"view_id": view.view_id, "variable": str(binding["name"])}
                )
        if view.kind == "signal":
            split_votes["contiguous_epoch"] += 2
        cards.append(
            {
                "view_id": view.view_id,
                "name": view.name[:240],
                "kind": view.kind,
                "dimensions": view.dimensions,
                "unit_coverage": {"declared": len(view.units), "variables": len(variables)},
                "variable_bindings": bindings[:300],
                "binding_complete": bool(variables)
                and all(item["role"] != "unknown" for item in bindings),
            }
        )
    split_strategy = "none"
    if split_votes:
        split_strategy = max(
            split_votes,
            key=lambda name: (split_votes[name], name == "group", name),
        )
    return {
        "schema_version": "principia.dataset-semantics/v1",
        "views": cards[:500],
        "role_counts": dict(sorted(role_counts.items())),
        "independent_unit_candidates": independent_candidates[:100],
        "recommended_split_strategy": split_strategy,
        "prohibited_scientific_variables": prohibited[:500],
        "warnings": [
            "Schema-derived roles guide plan binding but are not computed evidence.",
            "Unknown fields require a codebook or explicit context before analysis.",
            "Identifiers and weights cannot become scientific drivers or outcomes.",
        ],
    }


def _bounded_profile_fragments(asset_payloads: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract bounded interpretation text from adapter profiles without paths.

    These fragments can explain a schema but are explicitly not evidence.  The
    adapter has already bounded Office/PDF parsing, and this second boundary
    prevents a remote reasoning context from accidentally becoming a raw-file
    transport.
    """

    fragments: list[dict[str, Any]] = []
    total_characters = 0
    for item in asset_payloads:
        profile = dict(item.get("profile") or {})
        asset_id = str(item.get("asset_id") or "")
        candidates: list[tuple[str, str]] = []
        excerpt = profile.get("text_excerpt")
        if isinstance(excerpt, str):
            candidates.append(("document_text", excerpt))
        for slide in list(profile.get("slide_text") or [])[:20]:
            if isinstance(slide, dict) and isinstance(slide.get("text"), str):
                candidates.append(("presentation_text", str(slide["text"])))
        for sheet in list(profile.get("worksheets") or [])[:40]:
            if not isinstance(sheet, dict):
                continue
            headers = [str(value) for value in list(sheet.get("header_candidates") or [])[:64]]
            cells = [str(value) for value in list(sheet.get("representative_cells") or [])[:64]]
            if headers or cells:
                candidates.append(
                    (
                        "workbook_schema",
                        " | ".join(
                            [
                                str(sheet.get("name") or "worksheet"),
                                *headers,
                                *cells,
                            ]
                        ),
                    )
                )
        for role, value in candidates:
            normalized = " ".join(value.replace("\x00", " ").split())[:2_000]
            if len(normalized) < 3:
                continue
            remaining = 20_000 - total_characters
            if remaining <= 0:
                return fragments
            normalized = normalized[:remaining]
            fragments.append(
                {
                    "asset_id": asset_id,
                    "role": role,
                    "text": normalized,
                    "evidence_eligible": False,
                }
            )
            total_characters += len(normalized)
            if len(fragments) >= 100:
                return fragments
    return fragments


def compile_study_blueprint(
    *,
    study_id: str,
    views: Iterable[DataView],
    alignments: Iterable[DatasetAlignment],
    asset_profiles: Iterable[dict[str, Any]],
) -> StudyBlueprintV2:
    """Compile a path-free scientific binding before hypotheses are proposed."""

    view_list = list(views)
    alignment_list = list(alignments)
    semantics = compile_dataset_semantics(view_list)
    fragments = _bounded_profile_fragments(asset_profiles)
    corpus_text = " ".join(
        [
            *(view.name for view in view_list),
            *(name for view in view_list for name in [*view.variables, *view.keys]),
            *(str(item.get("text") or "") for item in fragments),
        ]
    ).casefold()
    tokens = _tokens(corpus_text)

    domain_candidates: list[dict[str, Any]] = []
    for domain, signals in _DOMAIN_SIGNALS.items():
        matched = sorted(signals & tokens)
        if not matched:
            continue
        score = min(0.99, 0.20 + len(matched) / max(5.0, len(signals) * 0.55))
        domain_candidates.append(
            {"domain": domain, "confidence": round(score, 3), "signals": matched[:20]}
        )
    domain_candidates.sort(key=lambda item: (-float(item["confidence"]), str(item["domain"])))

    bindings: list[dict[str, Any]] = []
    target_bindings: list[dict[str, Any]] = []
    input_bindings: list[dict[str, Any]] = []
    nuisance_bindings: list[dict[str, Any]] = []
    coordinate_bindings: list[dict[str, Any]] = []
    mask_bindings: list[dict[str, Any]] = []
    prohibited_leakage: list[dict[str, Any]] = []
    independent_units: list[dict[str, Any]] = []
    unit_bindings: list[dict[str, Any]] = []
    missing_codes: list[dict[str, Any]] = []
    object_counts: Counter[str] = Counter()
    known = 0
    total = 0
    for view in view_list:
        variables = list(dict.fromkeys([*view.variables, *view.keys]))[:5_000]
        for variable in variables:
            binding = {**classify_variable(variable), "view_id": view.view_id}
            binding["binding_id"] = "binding:" + canonical_sha256(
                {
                    "study": study_id,
                    "view": view.view_id,
                    "variable": variable,
                    "role": binding["role"],
                }
            )[:24]
            bindings.append(binding)
            total += 1
            if binding["role"] != "unknown":
                known += 1
            if binding["role"] == "independent_unit_identifier":
                independent_units.append(
                    {
                        "view_id": view.view_id,
                        "variable": variable,
                        "confidence": binding["confidence"],
                        "binding_id": binding["binding_id"],
                    }
                )
            role = str(binding["role"])
            if role in {"measurement_candidate", "group_or_condition"}:
                object_counts[role] += 1
            variable_tokens = _tokens(variable)
            target_signal = bool(
                variable_tokens
                & {
                    "response", "outcome", "target", "yield", "thickness", "fatality",
                    "injury", "damage", "score", "sensitivity", "latency", "throughput",
                    "conversion", "amplitude", "intensity", "flux", "employment", "price",
                }
            )
            controlled_signal = bool(
                variable_tokens
                & {
                    "input", "driver", "control", "dose", "power", "temperature", "pressure",
                    "rate", "speed", "frequency", "condition", "treatment", "recipe", "group",
                }
            )
            if role == "measurement_candidate":
                role_binding = dict(binding)
                if target_signal and not controlled_signal:
                    role_binding["scientific_role"] = "target"
                    target_bindings.append(role_binding)
                elif controlled_signal and not target_signal:
                    role_binding["scientific_role"] = "controlled_input"
                    input_bindings.append(role_binding)
                else:
                    # Ambiguous measurements remain unresolved.  They are not
                    # duplicated into both roles merely to make a program bind.
                    role_binding["scientific_role"] = "unresolved_measurement"
            elif role in {"group_or_condition", "time_coordinate"}:
                role_binding = {**binding, "scientific_role": "design_input"}
                input_bindings.append(role_binding)
            elif role in {"survey_weight", "identifier", "independent_unit_identifier"}:
                nuisance_bindings.append(
                    {**binding, "scientific_role": "design_or_grouping_only"}
                )
            if role in {"time_coordinate", "spatial_or_physical_coordinate"}:
                coordinate_bindings.append(
                    {**binding, "scientific_role": "coordinate_or_split"}
                )
            if str(binding.get("scientific_use") or "") == "prohibited_as_variable":
                prohibited_leakage.append(
                    {
                        "binding_id": binding["binding_id"],
                        "view_id": view.view_id,
                        "variable": variable,
                        "reason": "identifier or row identity cannot be a scientific predictor",
                    }
                )
            normalized = re.sub(r"[^a-z0-9]+", "_", variable.casefold()).strip("_")
            if normalized in _MISSING_LABELS or _tokens(variable) & _MISSING_LABELS:
                missing_codes.append(
                    {"view_id": view.view_id, "variable": variable, "status": "label_only"}
                )
        for variable, unit in sorted(view.units.items()):
            unit_bindings.append(
                {"view_id": view.view_id, "variable": variable, "unit": unit}
            )
        for mask in view.masks:
            mask_bindings.append(
                {
                    "binding_id": "mask:" + canonical_sha256(
                        {"study": study_id, "view": view.view_id, "mask": mask}
                    )[:24],
                    "view_id": view.view_id,
                    "variable": mask,
                    "scientific_role": "validity_mask",
                }
            )

    scientific_objects = [
        {
            "object": item["domain"],
            "basis": "bounded schema and context signals",
            "confidence": item["confidence"],
        }
        for item in domain_candidates[:5]
    ]
    scientific_objects.extend(
        {
            "object": role,
            "basis": "schema role bindings",
            "count": count,
            "confidence": 0.65,
        }
        for role, count in sorted(object_counts.items())
    )
    object_hierarchy = [
        {
            "object_id": "object:" + canonical_sha256(
                {"study": study_id, "view": view.view_id, "kind": view.kind}
            )[:24],
            "view_id": view.view_id,
            "object_kind": view.kind,
            "dimensions": dict(view.dimensions),
            "parent_object_id": "",
            "independence": "requires_design_binding",
        }
        for view in view_list
    ]

    split_candidates: list[dict[str, Any]] = []
    recommended_split = str(semantics.get("recommended_split_strategy") or "none")
    if recommended_split != "none":
        split_candidates.append(
            {
                "strategy": recommended_split,
                "confidence": 0.78 if independent_units else 0.55,
                "basis": "schema roles and modality structure",
            }
        )
    if any(view.kind == "signal" for view in view_list):
        split_candidates.append(
            {
                "strategy": "contiguous_epoch",
                "confidence": 0.85,
                "basis": "signal views require leakage-safe contiguous evaluation",
            }
        )

    joins = [
        {
            "alignment_id": item.alignment_id,
            "source_view_id": item.source_view_id,
            "target_view_id": item.target_view_id,
            "relation": item.relation,
            "source_keys": item.source_keys,
            "target_keys": item.target_keys,
            "confidence": item.confidence,
            "status": "candidate_requires_cardinality_validation",
        }
        for item in alignment_list
    ]
    binding_coverage = known / max(1, total)
    unit_coverage = len(unit_bindings) / max(1, total)
    confidence = min(
        0.95,
        0.12
        + min(0.35, binding_coverage * 0.35)
        + min(0.20, unit_coverage * 0.60)
        + (0.18 if independent_units else 0.0)
        + (0.12 if domain_candidates else 0.0)
        + (0.08 if fragments else 0.0),
    )
    top_domain = str(domain_candidates[0]["domain"]) if domain_candidates else "unresolved domain"
    summary = (
        f"Detected {len(view_list)} typed views in {top_domain}; bound {known} of {total} "
        f"schema variables, {len(independent_units)} candidate independent-unit fields, "
        f"and {len(alignment_list)} candidate cross-view relationships."
    )
    warnings = [
        "Context excerpts guide interpretation only and cannot support a finding.",
        "Candidate joins require cardinality, orphan, and unit validation before execution.",
        "Unknown fields cannot be substituted with identifier or row-order correlations.",
    ]
    role_complete = bool(target_bindings) and bool(input_bindings) and bool(
        independent_units
    )
    needs_confirmation = (
        confidence < 0.55
        or not domain_candidates
        or (total > 0 and binding_coverage < 0.35)
        or not role_complete
    )
    if needs_confirmation:
        warnings.append(
            "Scientific interpretation confidence is low; show an editable interpretation card and keep analyses exploratory."
        )
    payload = {
        "study_id": study_id,
        "schema_version": "principia.study-blueprint/v2",
        "domain_candidates": domain_candidates[:20],
        "scientific_objects": scientific_objects[:200],
        "object_hierarchy": object_hierarchy[:500],
        "variable_bindings": bindings[:5_000],
        "target_bindings": target_bindings[:1_000],
        "input_bindings": input_bindings[:5_000],
        "nuisance_bindings": nuisance_bindings[:2_000],
        "coordinate_bindings": coordinate_bindings[:1_000],
        "mask_bindings": mask_bindings[:1_000],
        "independent_units": independent_units[:200],
        "joins": joins[:500],
        "unit_bindings": unit_bindings[:2_000],
        "missing_value_codes": missing_codes[:500],
        "split_candidates": split_candidates[:100],
        "prohibited_leakage_variables": prohibited_leakage[:2_000],
        "semantic_resolution": {
            "deterministic_role_binding_complete": role_complete,
            "requires_reasoning_model": not role_complete,
            "reasoning_model_may_change_source_bytes": False,
            "reasoning_model_may_assign_same_measurement_to_target_and_input": False,
        },
        "edit_revision": 0,
        "context_excerpts": fragments[:100],
        "interpretation_summary": summary,
        "confidence": round(confidence, 3),
        "needs_user_confirmation": needs_confirmation,
        "warnings": warnings,
    }
    return StudyBlueprintV2(**payload, blueprint_digest=canonical_sha256(payload))
