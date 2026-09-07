"""Evidence-bound explanations for readers, separate from executable receipts.

These projections neither fit a model nor promote a finding. Relationships are
translated from active expression terms; limitations accompany the explanation.
"""
from __future__ import annotations

import math
import re
from typing import Any


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _unique(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    output = []
    for value in values:
        clean = _text(value)
        key = re.sub(r"\W+", "", clean).casefold()
        if key and key not in seen:
            seen.add(key)
            output.append(clean)
    return output


def explain_finding(finding: dict[str, Any]) -> dict[str, Any]:
    """Expose the inference, competing explanations and a discriminating next step."""
    summary = _text(finding.get("interpretation")) or _text(finding.get("claim"))
    explanation = _text(finding.get("mechanism"))
    if explanation in {summary, _text(finding.get("claim"))}:
        explanation = ""
    return {
        "summary": summary,
        "explanation": explanation,
        "explanation_label": "Scientific explanation" if finding.get("validation_level") == "identity_check" else "Possible explanation",
        "implication": _text(finding.get("practical_value")) or _text(finding.get("significance")),
        "boundaries": _unique([*finding.get("confounders", []), *finding.get("limits", [])]),
        "next_check": _text(finding.get("next_validation")),
    }


def _nodes(node: dict[str, Any]) -> list[dict[str, Any]]:
    return [node, *(entry for child in node.get("children", []) for entry in _nodes(child))]


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def explain_rule(rule: dict[str, Any]) -> dict[str, Any]:
    title = _text(rule.get("recorded_title")) or _text(rule.get("title"))
    target = _text(rule.get("target")) or "the measured response"
    nodes = _nodes(dict(rule.get("equation_ast") or {}))
    active = {n.get("symbol") for n in nodes if n.get("op") == "variable"}
    ops = {n.get("op") for n in nodes}
    bindings = [b for b in rule.get("variable_bindings", []) if b.get("symbol") in active]
    transforms = {_text(b.get("transform")) for b in bindings}
    test = dict(rule.get("test") or {})
    summary = _text(rule.get("interpretation"))
    explanation = ""
    implication = ""
    boundaries = [_text(rule.get("sample_definition"))]
    next_check = ""
    if title.startswith("Short-horizon "):
        quantity = re.sub(r"\(t\+1\)$", "", target)
        has_past = bool(active & {"x_1", "x_2"})
        summary = f"The next recorded {quantity} value can be estimated from the current reading"
        summary += " and its recent history." if has_past else "."
        variable_powers = {children[1].get("value") for n in nodes
                           if n.get("op") == "power" and len(children := n.get("children", [])) == 2
                           and any(child.get("op") == "variable" for child in _nodes(children[0]))}
        if "sigmoid" in ops:
            explanation = "The fitted curve allows the response to flatten at its extremes: the same input change need not have the same effect at every signal level."
        elif variable_powers & {2, 3}:
            explanation = "The curved response lets the predicted change depend on the signal level, instead of assuming a constant response across the measured range."
        elif any(power < 0 for power in variable_powers if _finite(power)):
            explanation = "The reciprocal terms let sensitivity vary sharply with signal level. Predictions near a denominator of zero or outside the observed range need particular scrutiny."
        else:
            explanation = "The fitted weights combine the available readings into a local forecast. Their predictive value does not by itself identify what drives the signal."
        if has_past:
            explanation += " Earlier readings supply information about the recent trajectory, so equal current values can have different forecasts."
        baseline = dict(rule.get("baseline_comparison") or {})
        error, reference = test.get("normalized_rmse"), baseline.get("test_nrmse")
        if _finite(error) and _finite(reference) and reference > 0:
            gain = 100 * (1 - error / reference)
            baseline_name = "simply repeating the latest reading" if baseline.get("model") == "persistence" else str(baseline.get("model") or "the declared baseline").replace("_", " ")
            implication = f"On held-out measurements, prediction error was {abs(gain):.3g}% {'lower' if gain >= 0 else 'higher'} than {baseline_name}."
        boundaries.append("This is a forecast at the recorded sampling interval, not evidence of a causal mechanism or reliable long-range prediction.")
        next_check = "Keep the equation fixed and test another acquisition at the same sampling interval, then check whether its advantage over the baseline survives."
    elif rule.get("executor_id") == "spatial_event_law":
        summary = "The equation estimates the response at each measured position, producing a predicted spatial distribution rather than only an overall average."
        terms = []
        if "log_local_driver" in transforms:
            terms.append("the input at that position")
        if any(t.startswith("nonlocal_kernel[") or t == "kernel_x_r2" for t in transforms):
            terms.append("a smoothed view of neighboring input values")
        if transforms & {"r^2", "r^4", "local_x_r2", "kernel_x_r2"}:
            terms.append("distance from the field center")
        if transforms & {"x", "y", "quadrupole_cos", "quadrupole_sin"}:
            terms.append("directional variation across the field")
        if terms:
            explanation = "The active terms combine " + ", ".join(terms) + "."
        if any(t.startswith("regime[") for t in transforms):
            explanation += " Input-defined groups allow different baseline response levels under different measured operating conditions."
        mean, worst = test.get("mean_map_mape_percent"), test.get("worst_map_mape_percent")
        if _finite(mean) and _finite(worst):
            implication = f"For complete held-out fields, mean absolute percentage error averaged {mean:.3g}%; the worst field reached {worst:.3g}%. This describes errors across positions, not a guarantee for every position."
        boundaries.append("Neighboring positions are correlated. The evidence comes from holding out complete field objects; fitted spatial terms do not establish a unique transport or reaction mechanism.")
        next_check = "Test unchanged coefficients on an independently acquired field with matched coordinates and inputs. Check both overall error and whether residuals cluster near edges or particular operating conditions."
    elif rule.get("rule_kind") == "mechanistic_invariant":
        explanation = "The equation expresses a consistency constraint among the recorded quantities. Agreement shows that those quantities respect the constraint within the tested precision."
        implication = "Use the constraint to detect inconsistent records or avoid treating deterministically related quantities as independent measurements."
        boundaries.append("A shared upstream calculation can enforce an identity. This check alone does not independently validate the measurement instrument or establish a new physical law.")
        next_check = "Recompute the related quantities through an independent measurement or reconstruction path and compare the residuals."
    else:
        inputs = _unique([b.get("meaning") or b.get("role") for b in bindings])
        if inputs:
            explanation = f"The equation relates {target} to " + ", ".join(inputs[:4]) + "."
        boundaries.append("Interpret this relationship within its recorded measurement and validation scope; extrapolation requires a separate test.")
    if test.get("passed") is False:
        boundaries.insert(0, "This candidate has not passed every scientific gate and is not a validated Rule.")
    return {"summary": summary, "explanation": explanation.strip(), "explanation_label": "How to read the relationship",
            "implication": implication, "boundaries": _unique(boundaries), "next_check": next_check}
