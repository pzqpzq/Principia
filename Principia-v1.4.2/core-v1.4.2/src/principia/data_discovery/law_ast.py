"""Safe canonical runtime for executable scientific-law expressions.

The runtime deliberately implements a small mathematical language.  Scientific
programs may compose this language, but cannot inject Python, filesystem calls,
or opaque serialized estimators into a Rule's identity.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import numpy as np

from ..domain import EquationNode, canonical_sha256

COMMUTATIVE_OPS = {"add", "multiply", "minimum", "maximum"}
LEAF_OPS = {"variable", "parameter", "constant", "kernel", "basis"}


def associative_node(op: str, children: list[EquationNode], **kwargs: Any) -> EquationNode:
    """Represent an arbitrarily wide sum/product with bounded, valid nodes."""
    if op not in COMMUTATIVE_OPS:
        raise ValueError("bounded grouping requires an associative operation")
    if not children:
        return EquationNode(op="constant", value=0.0 if op == "add" else 1.0, metadata=dict(kwargs.get("metadata") or {}))
    if len(children) == 1:
        return children[0].model_copy(update={"metadata": {**children[0].metadata, **dict(kwargs.get("metadata") or {})}})
    while len(children) > 64:
        children = [
            EquationNode(op=op, children=children[i:i + 64])
            if len(children[i:i + 64]) > 1 else children[i]
            for i in range(0, len(children), 64)
        ]
    return EquationNode(op=op, children=children, **kwargs)


def canonicalize(node: EquationNode) -> EquationNode:
    """Return a deterministically ordered, semantically equivalent AST."""

    if node.op in LEAF_OPS:
        return EquationNode.model_validate(node.model_dump(mode="json"))
    children = [canonicalize(child) for child in node.children]
    if node.op in COMMUTATIVE_OPS:
        flattened: list[EquationNode] = []
        def collect(child: EquationNode) -> None:
            if child.op == node.op:
                for descendant in child.children:
                    collect(descendant)
            else:
                flattened.append(child)
        for child in children:
            collect(child)
        children = sorted(flattened, key=lambda child: canonical_sha256(
            child.model_dump(mode="json", exclude_none=True)
        ))
        return associative_node(node.op, children, symbol=node.symbol, value=node.value,
                                metadata=dict(node.metadata))
    return EquationNode(
        op=node.op,
        symbol=node.symbol,
        value=node.value,
        children=children,
        metadata=dict(node.metadata),
    )


def canonical_payload(node: EquationNode) -> dict[str, Any]:
    return canonicalize(node).model_dump(mode="json", exclude_none=True)


def ast_digest(node: EquationNode) -> str:
    return canonical_sha256(canonical_payload(node))


def _value(
    symbol: str,
    variables: Mapping[str, Any],
    parameters: Mapping[str, Any],
    *,
    parameter: bool,
) -> np.ndarray:
    source = parameters if parameter else variables
    if symbol not in source:
        kind = "parameter" if parameter else "variable"
        raise KeyError(f"missing equation {kind}: {symbol}")
    return np.asarray(source[symbol], dtype=float)


def evaluate(
    node: EquationNode,
    variables: Mapping[str, Any],
    parameters: Mapping[str, Any] | None = None,
) -> np.ndarray:
    """Evaluate an AST with NumPy without dynamic code execution."""

    parameters = parameters or {}
    if node.op in {"variable", "kernel", "basis"}:
        return _value(node.symbol, variables, parameters, parameter=False)
    if node.op == "parameter":
        return _value(node.symbol, variables, parameters, parameter=True)
    if node.op == "constant":
        return np.asarray(float(node.value), dtype=float)
    values = [evaluate(child, variables, parameters) for child in node.children]
    if node.op == "add":
        result = values[0]
        for value in values[1:]:
            result = np.add(result, value)
        return result
    if node.op == "multiply":
        result = values[0]
        for value in values[1:]:
            result = np.multiply(result, value)
        return result
    if node.op == "power":
        return np.power(values[0], values[1])
    if node.op == "negative":
        return -values[0]
    if node.op == "exp":
        return np.exp(np.clip(values[0], -700.0, 700.0))
    if node.op == "log":
        return np.log(values[0])
    if node.op == "log1p":
        return np.log1p(values[0])
    if node.op == "sigmoid":
        clipped = np.clip(values[0], -700.0, 700.0)
        return 1.0 / (1.0 + np.exp(-clipped))
    if node.op == "absolute":
        return np.abs(values[0])
    if node.op == "minimum":
        result = values[0]
        for value in values[1:]:
            result = np.minimum(result, value)
        return result
    if node.op == "maximum":
        result = values[0]
        for value in values[1:]:
            result = np.maximum(result, value)
        return result
    raise ValueError(f"unsupported equation operation: {node.op}")


def render_latex(node: EquationNode) -> str:
    """Render canonical presentation LaTeX from the executable AST."""

    node = canonicalize(node)
    if node.op in {"variable", "parameter", "kernel", "basis"}:
        return node.symbol
    if node.op == "constant":
        value = float(node.value)
        return str(int(value)) if value.is_integer() else f"{value:.8g}"
    rendered = [render_latex(child) for child in node.children]
    if node.op == "add":
        return " + ".join(rendered)
    if node.op == "multiply":
        return r" \, ".join(
            f"\\left({item}\\right)" if "+" in item else item for item in rendered
        )
    if node.op == "power":
        return f"\\left({rendered[0]}\\right)^{{{rendered[1]}}}"
    if node.op == "negative":
        return f"-\\left({rendered[0]}\\right)"
    if node.op == "exp":
        return f"\\exp\\left({rendered[0]}\\right)"
    if node.op == "log":
        return f"\\log\\left({rendered[0]}\\right)"
    if node.op == "log1p":
        return f"\\log\\left(1+{rendered[0]}\\right)"
    if node.op == "sigmoid":
        return f"\\sigma\\left({rendered[0]}\\right)"
    if node.op == "absolute":
        return f"\\left|{rendered[0]}\\right|"
    if node.op == "minimum":
        return f"\\min\\left({', '.join(rendered)}\\right)"
    if node.op == "maximum":
        return f"\\max\\left({', '.join(rendered)}\\right)"
    raise ValueError(f"unsupported equation operation: {node.op}")


def _same_dimension(items: list[dict[str, float]]) -> dict[str, float]:
    first = {key: value for key, value in items[0].items() if abs(value) > 1e-12}
    for item in items[1:]:
        normalized = {key: value for key, value in item.items() if abs(value) > 1e-12}
        if normalized != first:
            raise ValueError("dimensionally incompatible additive expression")
    return first


def infer_dimension(
    node: EquationNode,
    signatures: Mapping[str, Mapping[str, float]],
) -> dict[str, float]:
    """Infer physical dimensions and reject invalid compositions."""

    if node.op in {"variable", "parameter", "kernel", "basis"}:
        return {key: float(value) for key, value in signatures.get(node.symbol, {}).items()}
    if node.op == "constant":
        return {}
    children = [infer_dimension(child, signatures) for child in node.children]
    if node.op in {"add", "minimum", "maximum"}:
        return _same_dimension(children)
    if node.op == "multiply":
        result: dict[str, float] = {}
        for child in children:
            for key, value in child.items():
                result[key] = result.get(key, 0.0) + value
        return {key: value for key, value in result.items() if abs(value) > 1e-12}
    if node.op == "power":
        exponent_node = node.children[1]
        if exponent_node.op != "constant" or exponent_node.value is None:
            raise ValueError("dimensional powers require a constant exponent")
        if children[1]:
            raise ValueError("an exponent must be dimensionless")
        return {key: value * float(exponent_node.value) for key, value in children[0].items()}
    if node.op in {"negative", "absolute"}:
        return children[0]
    if node.op in {"exp", "log", "log1p", "sigmoid"}:
        if children[0]:
            raise ValueError(f"{node.op} requires a dimensionless argument")
        return {}
    raise ValueError(f"unsupported equation operation: {node.op}")


def differentiate(node: EquationNode, symbol: str) -> EquationNode:
    """Return an analytic derivative for the differentiable core language."""

    zero = EquationNode(op="constant", value=0.0)
    one = EquationNode(op="constant", value=1.0)
    if node.op in {"variable", "kernel", "basis"}:
        return one if node.symbol == symbol else zero
    if node.op in {"parameter", "constant"}:
        return zero
    if node.op == "add":
        return canonicalize(EquationNode(op="add", children=[differentiate(c, symbol) for c in node.children]))
    if node.op == "negative":
        return EquationNode(op="negative", children=[differentiate(node.children[0], symbol)])
    if node.op == "multiply":
        terms: list[EquationNode] = []
        for index, child in enumerate(node.children):
            factors = [differentiate(child, symbol)] + [
                other for other_index, other in enumerate(node.children) if other_index != index
            ]
            terms.append(EquationNode(op="multiply", children=factors))
        return canonicalize(EquationNode(op="add", children=terms))
    if node.op == "power":
        base, exponent = node.children
        if exponent.op != "constant" or exponent.value is None:
            raise ValueError("analytic derivatives require constant powers")
        return EquationNode(
            op="multiply",
            children=[
                EquationNode(op="constant", value=float(exponent.value)),
                EquationNode(
                    op="power",
                    children=[base, EquationNode(op="constant", value=float(exponent.value) - 1.0)],
                ),
                differentiate(base, symbol),
            ],
        )
    inner = node.children[0]
    derivative = differentiate(inner, symbol)
    if node.op == "exp":
        return EquationNode(op="multiply", children=[node, derivative])
    if node.op == "log":
        return EquationNode(
            op="multiply",
            children=[
                derivative,
                EquationNode(op="power", children=[inner, EquationNode(op="constant", value=-1.0)]),
            ],
        )
    if node.op == "log1p":
        denominator = EquationNode(
            op="add", children=[EquationNode(op="constant", value=1.0), inner]
        )
        return EquationNode(
            op="multiply",
            children=[derivative, EquationNode(op="power", children=[denominator, EquationNode(op="constant", value=-1.0)])],
        )
    if node.op == "sigmoid":
        return EquationNode(
            op="multiply",
            children=[
                node,
                EquationNode(op="add", children=[one, EquationNode(op="negative", children=[node])]),
                derivative,
            ],
        )
    raise ValueError(f"analytic derivative is not defined for {node.op}")


def numerical_derivative(
    node: EquationNode,
    symbol: str,
    variables: Mapping[str, Any],
    parameters: Mapping[str, Any] | None = None,
    *,
    relative_step: float = math.sqrt(np.finfo(float).eps),
) -> np.ndarray:
    """Central finite-difference derivative used for runtime cross-checks."""

    base = np.asarray(variables[symbol], dtype=float)
    step = relative_step * np.maximum(1.0, np.abs(base))
    plus = dict(variables)
    minus = dict(variables)
    plus[symbol] = base + step
    minus[symbol] = base - step
    return (evaluate(node, plus, parameters) - evaluate(node, minus, parameters)) / (2.0 * step)
