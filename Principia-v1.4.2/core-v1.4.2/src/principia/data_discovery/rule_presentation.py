"""Read-only labels for executed Rules; never used for selection or identity."""
from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

from .interpretation import explain_rule


def _nodes(node: dict[str, Any]) -> list[dict[str, Any]]:
    return [node, *(entry for child in node.get("children", []) for entry in _nodes(child))]


def response_title(rule: dict[str, Any]) -> str:
    """Describe the selected structure, ignoring powers of normalization scales."""
    title = str(rule.get("title") or "Measured response")
    if not title.startswith("Short-horizon "):
        return title
    quantity = title.removeprefix("Short-horizon ").removesuffix(" response")
    nodes = _nodes(dict(rule.get("equation_ast") or {}))
    variables = {node.get("symbol") for node in nodes if node.get("op") == "variable"}
    ops = {node.get("op") for node in nodes}
    powers = {
        child[1].get("value") for node in nodes
        if node.get("op") == "power" and len(child := node.get("children", [])) == 2
        and any(n.get("op") == "variable" for n in _nodes(child[0]))
    }
    interaction = any(
        node.get("op") == "multiply" and
        sum(any(n.get("op") == "variable" for n in _nodes(factor))
            for factor in node.get("children", [])) > 1 and
        len({n.get("symbol") for n in _nodes(node) if n.get("op") == "variable"}) > 1
        for node in nodes
    )
    if -3 in powers:
        structure = "inverse-cubic response"
    elif -2 in powers:
        structure = "inverse-quadratic response"
    elif 3 in powers:
        structure = "cubic response"
    elif 2 in powers:
        structure = "quadratic response"
    elif "sigmoid" in ops:
        structure = "sigmoidal response"
    elif -1 in powers:
        structure = "rational response"
    elif ops <= {"add", "multiply", "power", "constant", "variable", "parameter"} and not powers:
        structure = "linear response"
    else:
        structure = "nonlinear response"
    if interaction:
        if structure == "linear response":
            structure = "nonlinear response"
        structure += " with lag interaction"
    elif variables == {"x_0", "x_2"}:
        structure += " with two-step history"
    elif variables == {"x_0", "x_1"}:
        structure += " with one-step history"
    elif len(variables) > 1:
        structure += " with observed history"
    return f"{quantity[:1].upper()}{quantity[1:]}: {structure}"


def response_description(rule: dict[str, Any], context: str = "") -> str:
    """Describe actual inputs and measured performance, never infer causality."""
    nodes = _nodes(dict(rule.get("equation_ast") or {}))
    active = {node.get("symbol") for node in nodes if node.get("op") == "variable"}
    inputs = [str(item.get("meaning") or item.get("role") or item["symbol"])
              for item in rule.get("equation_variables", [])
              if item.get("symbol") in active]
    target = str(rule.get("target") or "the measured response")
    structure = response_title(rule).split(": ", 1)[-1]
    scope = f"For {context}, " if context else ""
    description = f"{scope}{structure[:1].lower()}{structure[1:]} predicts {target}"
    if inputs:
        description += f" from {', '.join(inputs)}"
    description += "."
    test = dict(rule.get("test") or {})
    baseline = dict(rule.get("baseline_comparison") or {})
    error, reference = test.get("normalized_rmse"), baseline.get("test_nrmse")
    if isinstance(error, (float, int)):
        description += f" Held-out normalized RMSE is {error:.4g}"
        if isinstance(reference, (float, int)) and reference > 0:
            gain = 100 * (1 - error / reference)
            comparison = f"{abs(gain):.3g}% {'lower' if gain >= 0 else 'higher'}"
            description += f", {comparison} than {str(baseline.get('model') or 'the declared baseline').replace('_', ' ')}"
        description += "."
    return description[:1200]


def _feature_caption(value: str, groups: dict[str, int]) -> str:
    if value.startswith("regime["):
        return f"Input-defined group {groups[value]} indicator"
    labels = {"r^2": "Normalized radius squared", "r^4": "Fourth power of normalized radius",
              "x": "Centered horizontal coordinate", "y": "Centered vertical coordinate",
              "quadrupole_cos": "Directional curvature (x² − y²)",
              "quadrupole_sin": "Diagonal curvature (2xy)",
              "log_driver_mean": "Log mean of the input field", "driver_cv": "Relative spread of the input field",
              "log_local_driver": "Log local input relative to its field mean",
              "local_x_r2": "Local input response × radius squared",
              "kernel_x_r2": "Smoothed input response × radius squared",
              "local_saturation": "Saturating local input response"}
    if value.startswith("nonlocal_kernel["):
        scale = value.removeprefix("nonlocal_kernel[").removesuffix("]")
        return f"Smoothed input response (length {scale} radii)"
    return labels.get(value, value.replace("_", " "))


def _display_calibration(rule: dict[str, Any]) -> dict[str, Any]:
    nodes = _nodes(dict(rule.get("equation_ast") or {}))
    used = {str(node["symbol"]) for node in nodes if node.get("op") == "parameter"}
    parameters = dict(rule.get("parameter_estimates") or {})
    values = dict(parameters.get("equation_parameters") or parameters)
    active = {name: value for name, value in values.items() if name in used and isinstance(value, (float, int))}
    scales = {name: value for name, value in active.items() if re.fullmatch(r"[ms]_\d+", name) or name == "T_ref"}
    fitted = {name: value for name, value in active.items() if name not in scales}
    bindings = rule.get("variable_bindings") or rule.get("equation_variables") or []
    variables = {str(node["symbol"]) for node in nodes if node.get("op") == "variable"}
    group_keys = sorted({str(item.get("transform")) for item in bindings if str(item.get("transform") or "").startswith("regime[")})
    groups = {key: index + 1 for index, key in enumerate(group_keys)}
    symbols = [{**item, "meaning": item.get("meaning") or (_feature_caption(str(item["transform"]), groups) if item.get("transform") else item.get("role")) or item["symbol"]}
               for item in bindings if item.get("symbol") in variables]
    if rule.get("target") and str(rule.get("title") or "").startswith("Short-horizon "):
        symbols.insert(0, {"symbol": r"\widehat{y}", "meaning": "Predicted " + str(rule["target"])})
    return {"coefficients": fitted, "normalization": scales,
            "fitted_coefficient_count": len(fitted), "input_count": len(variables), "symbols": symbols}


def _source_caption(path: str) -> str:
    name = PurePosixPath(path).name
    # Extract explicit acquisition identifiers, without inferring source content.
    match = re.search(r"(?:^|_)ses-([^_]+)", name)
    if match:
        return f"session {match[1]}"
    match = re.search(r"(?:^|_)tess_ffi_s(\d+)-(\d+)_", name)
    if match:
        return f"TESS target {int(match[2])}, sector {int(match[1])}"
    return name


def present_rules(rules: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_test: dict[str, list[dict[str, Any]]] = {}
    for anchor in evidence:
        by_test.setdefault(str(anchor.get("test_id") or ""), []).append(anchor)
    output = []
    for rule in rules:
        locators = [dict(anchor.get("locator") or {})
                    for test_id in rule.get("test_ids", []) for anchor in by_test.get(test_id, [])]
        paths = sorted({str(locator["relative_path"]) for locator in locators if locator.get("relative_path")})
        contexts = list(dict.fromkeys(_source_caption(path) for path in paths))
        context = " · ".join(contexts[:2])
        if len(contexts) > 2:
            context += f" · {len(contexts) - 2} more sources"
        title = response_title(rule)
        interpretation = str(rule.get("interpretation") or "")
        expression = str(rule.get("display_expression_latex") or rule.get("expression_latex") or "")
        if str(rule.get("title") or "").startswith("Short-horizon "):
            # Structure leads; source and target supply identity without pretending
            # that the same functional family is a different scientific mechanism.
            quantity, structure = title.split(": ", 1)
            title = f"{structure.capitalize()} · {context or quantity}"
            interpretation = response_description(rule, context)
            if "=" not in expression:
                expression = r"\widehat{y}=" + expression
        output.append({**rule, "title": title, "interpretation": interpretation,
                       "display_expression_latex": expression,
                       "recorded_title": rule["title"],
                       "recorded_interpretation": rule.get("interpretation", ""),
                       "source_context": context, "source_paths": paths,
                       "display_calibration": _display_calibration(rule),
                       "plain_language_interpretation": explain_rule(rule)})
    return output
