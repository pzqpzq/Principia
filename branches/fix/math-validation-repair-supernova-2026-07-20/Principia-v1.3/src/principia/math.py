from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from pylatexenc.latexwalker import (  # type: ignore[import-untyped]
    LatexWalker,
    LatexWalkerParseError,
)


class MathValidationError(ValueError):
    """Raised when generated mathematical markup is unsafe or malformed."""


@dataclass(frozen=True)
class MathSpan:
    """One dollar-delimited mathematical span in a larger text value."""

    start: int
    end: int
    content: str
    display: bool


_UNICODE_MATH = {
    "α": r"\alpha",
    "β": r"\beta",
    "γ": r"\gamma",
    "δ": r"\delta",
    "ε": r"\epsilon",
    "ζ": r"\zeta",
    "η": r"\eta",
    "θ": r"\theta",
    "ι": r"\iota",
    "κ": r"\kappa",
    "λ": r"\lambda",
    "μ": r"\mu",
    "ν": r"\nu",
    "ξ": r"\xi",
    "π": r"\pi",
    "ρ": r"\rho",
    "σ": r"\sigma",
    "τ": r"\tau",
    "υ": r"\upsilon",
    "φ": r"\phi",
    "χ": r"\chi",
    "ψ": r"\psi",
    "ω": r"\omega",
    "Γ": r"\Gamma",
    "Δ": r"\Delta",
    "Θ": r"\Theta",
    "Λ": r"\Lambda",
    "Ξ": r"\Xi",
    "Π": r"\Pi",
    "Σ": r"\Sigma",
    "Φ": r"\Phi",
    "Ψ": r"\Psi",
    "Ω": r"\Omega",
    "∫": r"\int",
    "∑": r"\sum",
    "∏": r"\prod",
    "∂": r"\partial",
    "∇": r"\nabla",
    "ℏ": r"\hbar",
    "ħ": r"\hbar",
    "±": r"\pm",
    "×": r"\cdot",
    "⋅": r"\cdot",
    "≤": r"\le",
    "≥": r"\ge",
    "≠": r"\ne",
    "≈": r"\approx",
    "≡": r"\equiv",
    "∝": r"\propto",
    "∞": r"\infty",
    "−": "-",
    "→": r"\to",
}
_FORBIDDEN_CONTROLS = re.compile(r"[\x00-\x1f\x7f]")
_UNSUPPORTED_DELIMITERS = re.compile(r"\\[\[(]|\\[])]")
_UNICODE_SUPERSCRIPT_VALUES = {
    "⁰": "0",
    "¹": "1",
    "²": "2",
    "³": "3",
    "⁴": "4",
    "⁵": "5",
    "⁶": "6",
    "⁷": "7",
    "⁸": "8",
    "⁹": "9",
    "⁺": "+",
    "⁻": "-",
}
_UNICODE_SUBSCRIPT_VALUES = {
    "₀": "0",
    "₁": "1",
    "₂": "2",
    "₃": "3",
    "₄": "4",
    "₅": "5",
    "₆": "6",
    "₇": "7",
    "₈": "8",
    "₉": "9",
    "₊": "+",
    "₋": "-",
}
_UNBRACED_SCRIPT = re.compile(
    r"(?<!\\)(?P<operator>[_^])"
    r"(?P<argument>\\[A-Za-z]+\{[^{}]*\}|\\[A-Za-z]+|-[0-9]+|[A-Za-z0-9]+|[*])"
    r"(?![A-Za-z0-9])"
)
_SCRIPT_ARGUMENT = r"(?:\{[^{}]*\}|\\[A-Za-z]+\{[^{}]*\}|\\[A-Za-z]+|-[0-9]+|[A-Za-z0-9]+|[*])"
_REPEATED_SCRIPT = re.compile(
    rf"(?<!\\)(?P<operator>[_^]){_SCRIPT_ARGUMENT}(?P=operator){_SCRIPT_ARGUMENT}"
)
_ASCII_GREEK = {
    "alpha": r"\alpha",
    "beta": r"\beta",
    "gamma": r"\gamma",
    "delta": r"\delta",
    "epsilon": r"\epsilon",
    "eta": r"\eta",
    "theta": r"\theta",
    "kappa": r"\kappa",
    "lambda": r"\lambda",
    "mu": r"\mu",
    "nu": r"\nu",
    "pi": r"\pi",
    "rho": r"\rho",
    "sigma": r"\sigma",
    "tau": r"\tau",
    "phi": r"\phi",
    "chi": r"\chi",
    "psi": r"\psi",
    "omega": r"\omega",
}
_ASCII_OPERATOR_CALL = re.compile(
    r"(?<![\\A-Za-z0-9_])"
    r"(?P<name>Var|Cov|Tr|exp|log|ln|sin|cos|tan|sinh|cosh|tanh|min|max|det)"
    r"(?=\s*\()"
)
_NAMED_OPERATORS = frozenset({"Var", "Cov", "Tr"})


def tokenize_math_spans(value: str) -> list[MathSpan]:
    """Tokenize strict ``$...$`` and ``$$...$$`` spans.

    The scanner deliberately rejects nesting and mismatched delimiters instead
    of guessing what an LLM intended. Escaped dollar signs remain prose.
    """

    text = str(value or "")
    if "```" in text:
        raise MathValidationError("Markdown code fences are not valid mathematical markup")
    if _FORBIDDEN_CONTROLS.search(text):
        raise MathValidationError("Mathematical markup contains a control character")
    if _UNSUPPORTED_DELIMITERS.search(text):
        raise MathValidationError(
            "Use dollar-delimited inline or display math; "
            "parenthesis/bracket LaTeX delimiters are unsupported"
        )

    spans: list[MathSpan] = []
    index = 0
    while index < len(text):
        if text[index] != "$" or _escaped(text, index):
            index += 1
            continue
        display = text.startswith("$$", index)
        delimiter = "$$" if display else "$"
        content_start = index + len(delimiter)
        cursor = content_start
        closing = -1
        while cursor < len(text):
            if text[cursor] != "$" or _escaped(text, cursor):
                cursor += 1
                continue
            if text.startswith(delimiter, cursor):
                closing = cursor
                break
            raise MathValidationError("Nested or mismatched dollar delimiters")
        if closing < 0:
            raise MathValidationError("Unbalanced dollar delimiter")
        content = text[content_start:closing].strip()
        if not content:
            raise MathValidationError("Empty mathematical span")
        end = closing + len(delimiter)
        spans.append(MathSpan(start=index, end=end, content=content, display=display))
        index = end
    return spans


def normalize_latex_formula(value: str, *, display: bool = True) -> str:
    """Normalize and validate a formula, returning one exact math span."""

    raw_text = str(value or "")
    if _FORBIDDEN_CONTROLS.search(raw_text):
        raise MathValidationError("Mathematical markup contains a control character")
    text = raw_text.strip()
    if not text:
        return ""
    spans = tokenize_math_spans(text)
    if spans:
        if len(spans) != 1 or text[: spans[0].start].strip() or text[spans[0].end :].strip():
            raise MathValidationError("A formula field must contain exactly one mathematical span")
        body = spans[0].content
    else:
        body = text
    normalized = _normalize_body(body)
    delimiter = "$$" if display else "$"
    return f"{delimiter}{normalized}{delimiter}"


def normalize_latex_symbol(value: str) -> str:
    """Normalize and validate a mathematical symbol as inline LaTeX."""

    return normalize_latex_formula(value, display=False)


def normalize_math_text(value: str) -> str:
    """Normalize explicit math spans in prose without guessing new spans."""

    text = " ".join(str(value or "").split())
    spans = tokenize_math_spans(text)
    if not spans:
        return text
    output: list[str] = []
    cursor = 0
    for span in spans:
        output.append(text[cursor : span.start])
        output.append(normalize_latex_formula(span.content, display=span.display))
        cursor = span.end
    output.append(text[cursor:])
    return "".join(output)


def normalize_math_value(value: Any) -> Any:
    """Recursively canonicalize explicit math in generated scientific content.

    This deliberately operates only on strings containing explicit dollar
    delimiters. It never guesses that prose, identifiers, paths, or provider
    metadata are mathematical expressions.
    """

    if isinstance(value, str):
        return normalize_math_text(value)
    if isinstance(value, dict):
        return {key: normalize_math_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_math_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(normalize_math_value(item) for item in value)
    return value


def validate_math_text(value: str) -> None:
    """Validate that every explicit span is both parseable and canonical."""

    text = str(value or "")
    for span in tokenize_math_spans(text):
        normalized = _normalize_body(span.content)
        original = " ".join(span.content.split())
        if normalized != original:
            raise MathValidationError(
                f"Non-canonical LaTeX; use {normalized!r} inside the math delimiters"
            )


def math_issues(value: Any, *, path: str = "value") -> list[str]:
    """Return stable, field-addressed issues for all explicit math markup."""

    issues: list[str] = []
    if isinstance(value, str):
        try:
            validate_math_text(value)
        except MathValidationError as exc:
            issues.append(f"{path}: {exc}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            issues.extend(math_issues(item, path=f"{path}[{index}]"))
    elif isinstance(value, dict):
        for key, item in value.items():
            issues.extend(math_issues(item, path=f"{path}.{key}"))
    return issues


def generated_math_issues(value: Any, *, path: str = "value") -> list[str]:
    """Audit generated scientific text, including math left outside delimiters."""

    issues = math_issues(value, path=path)
    if isinstance(value, str):
        try:
            spans = tokenize_math_spans(value)
        except MathValidationError:
            return issues
        prose_parts: list[str] = []
        cursor = 0
        for span in spans:
            prose_parts.append(value[cursor : span.start])
            cursor = span.end
        prose_parts.append(value[cursor:])
        prose = " ".join(prose_parts)
        unicode_tokens = {
            *(_UNICODE_MATH.keys()),
            *(_UNICODE_SUPERSCRIPT_VALUES.keys()),
            *(_UNICODE_SUBSCRIPT_VALUES.keys()),
        }
        if any(token in prose for token in unicode_tokens):
            issues.append(f"{path}: mathematical Unicode must be inside canonical $...$ markup")
        # A portable-artifact audit may encounter a Windows path before the
        # path sanitizer runs (for example ``C:\\Users\\name\\file.txt``).
        # Backslash-separated path components are not LaTeX commands, so mask
        # the complete absolute path before looking for bare commands.  This
        # keeps the scientific-text check strict without misclassifying local
        # filesystem data.
        prose_without_windows_paths = re.sub(
            r"(?i)(?<![A-Za-z0-9_])[A-Z]:\\(?:[^\\\s]+\\)*[^\\\s]*",
            "",
            prose,
        )
        if re.search(r"(?<!\\)\\[A-Za-z]+", prose_without_windows_paths):
            issues.append(f"{path}: LaTeX commands must be inside canonical $...$ markup")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            issues.extend(generated_math_issues(item, path=f"{path}[{index}]"))
    elif isinstance(value, dict):
        for key, item in value.items():
            issues.extend(generated_math_issues(item, path=f"{path}.{key}"))
    return list(dict.fromkeys(issues))


def omit_invalid_math_strings(value: Any, *, path: str = "value") -> Any:
    """Remove invalid generated strings from an LLM repair draft.

    The surrounding record structure and valid fields are preserved so a
    repair model can reconstruct only the rejected value without copying it.
    """

    if isinstance(value, str):
        return None if generated_math_issues(value, path=path) else value
    if isinstance(value, list):
        return [
            omit_invalid_math_strings(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, dict):
        return {
            key: omit_invalid_math_strings(item, path=f"{path}.{key}")
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return tuple(
            omit_invalid_math_strings(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        )
    return value


def math_repair_guidance(issues: list[str], *, context: str = "prose") -> str:
    """Return concise, issue-specific instructions for one strict repair call."""

    issue_text = " ".join(str(issue) for issue in issues).casefold()
    math_issue = any(
        marker in issue_text
        for marker in (
            "mathematical",
            "latex",
            "dollar delimiter",
            "subscript",
            "superscript",
            "programming conditionals",
            "mathematical equality",
            "integral(",
        )
    )
    if not math_issue:
        return ""

    guidance = ["Mathematical validation failed; repair only the listed fields."]
    if "mathematical unicode" in issue_text:
        guidance.append(
            "Never copy Unicode mathematical symbols, operators, superscripts, or subscripts; "
            "rewrite U+03C3 as `sigma`, U+2264 as `less than or equal to`, and superscript two as `squared`."
        )
    if "programming conditionals" in issue_text:
        guidance.append(
            "Never use `if`, `elif`, `else`, or ternary syntax in an equation; use a source-grounded "
            r"LaTeX cases form such as $$f(x)=\begin{cases}1,&x>0\\0,&\text{otherwise}\end{cases}$$."
        )
        if context == "idea":
            guidance.append(
                "If the evidence does not support the exact formula, return the complete Idea Card with "
                "methodological_details.equations set to an empty list."
            )
    if "mathematical equality" in issue_text:
        guidance.append("Use `=` for mathematical equality, never `==`.")
    if "integral(" in issue_text:
        guidance.append(r"Use a canonical `\int` expression, never programming-style `integral(...)`.")
    if "repeated subscript or superscript" in issue_text:
        guidance.append(
            "Use exactly one braced subscript and one braced superscript per base symbol, or paraphrase the claim."
        )
    if any(
        marker in issue_text
        for marker in (
            "delimiter",
            "backslash",
            "control character",
            "malformed latex",
            "unsafe characters",
            "latex parser",
        )
    ):
        guidance.append(
            "Use only balanced $...$ or $$...$$ spans with correctly JSON-escaped LaTeX backslashes; "
            "otherwise paraphrase in plain language."
        )
    guidance.append("Before returning JSON, verify that none of the listed mathematical defects remains.")
    return " ".join(guidance)


def _normalize_body(value: str) -> str:
    body = str(value or "").strip()
    if not body:
        raise MathValidationError("Empty mathematical expression")
    if "```" in body or _FORBIDDEN_CONTROLS.search(body):
        raise MathValidationError("Mathematical expression contains unsafe characters")
    if "$" in body:
        raise MathValidationError("Nested dollar delimiters are not allowed")
    if "==" in body:
        raise MathValidationError("Use = for mathematical equality, not ==")
    if re.search(r"\b(?:if|elif|else)\b", body, flags=re.IGNORECASE):
        raise MathValidationError("Use a LaTeX cases expression instead of programming conditionals")
    if re.search(r"\bintegral\s*\(", body, flags=re.IGNORECASE):
        raise MathValidationError("Use the LaTeX \\int command instead of integral(...)")
    if _REPEATED_SCRIPT.search(body):
        raise MathValidationError(
            "Repeated subscript or superscript requires an evidence-grounded rewrite"
        )
    body = _normalize_unicode_scripts(body)
    body = unicodedata.normalize("NFKC", body)
    if _REPEATED_SCRIPT.search(body):
        raise MathValidationError(
            "Repeated subscript or superscript requires an evidence-grounded rewrite"
        )
    for source, target in _UNICODE_MATH.items():
        body = body.replace(source, f"{target} " if target.startswith("\\") else target)
    body = re.sub(r"<=", r"\\le ", body)
    body = re.sub(r">=", r"\\ge ", body)
    body = re.sub(r"!=", r"\\ne ", body)
    body = re.sub(r"\bAND\b", r"\\land ", body)
    body = re.sub(r"\bOR\b", r"\\lor ", body)
    body = re.sub(r"(?<!\^)(?<!\^\{)\s*\*\s*", r" \\cdot ", body)
    body = _normalize_ascii_greek(body)
    body = _UNBRACED_SCRIPT.sub(r"\g<operator>{\g<argument>}", body)
    body = _normalize_ascii_operators(body)
    # A command must touch its script or closing delimiter, but whitespace
    # around binary operators is meaningful canonical formatting and should
    # remain symmetric (``\\alpha + \\beta``, not ``\\alpha+ \\beta``).
    body = re.sub(r"(\\[A-Za-z]+)\s+(?=[_^}\)\],.;:])", r"\1", body)
    body = " ".join(body.split())
    _validate_backslashes(body)
    _validate_braces(body)
    try:
        _, position, length = LatexWalker(body).get_latex_nodes(pos=0)
    except (LatexWalkerParseError, ValueError) as exc:
        raise MathValidationError(f"Malformed LaTeX: {exc}") from exc
    if position + length != len(body):
        raise MathValidationError("LaTeX parser did not consume the complete expression")
    return body


def _normalize_unicode_scripts(body: str) -> str:
    superscripts = "".join(re.escape(value) for value in _UNICODE_SUPERSCRIPT_VALUES)
    subscripts = "".join(re.escape(value) for value in _UNICODE_SUBSCRIPT_VALUES)

    def replace_super(match: re.Match[str]) -> str:
        value = "".join(_UNICODE_SUPERSCRIPT_VALUES[char] for char in match.group(0))
        return f"^{{{value}}}"

    def replace_sub(match: re.Match[str]) -> str:
        value = "".join(_UNICODE_SUBSCRIPT_VALUES[char] for char in match.group(0))
        return f"_{{{value}}}"

    body = re.sub(f"[{superscripts}]+", replace_super, body)
    return re.sub(f"[{subscripts}]+", replace_sub, body)


def _normalize_ascii_greek(body: str) -> str:
    for name, command in _ASCII_GREEK.items():
        def replace_greek(_match: re.Match[str], replacement: str = command) -> str:
            return replacement

        body = re.sub(
            rf"(?<![\\A-Za-z]){name}(?![A-Za-z])",
            replace_greek,
            body,
        )
    return body


def _normalize_ascii_operators(body: str) -> str:
    def replace(match: re.Match[str]) -> str:
        # Preserve already canonical ``\operatorname{...}`` content.
        if body[: match.start()].endswith(r"\operatorname{"):
            return match.group(0)
        name = match.group("name")
        if name in _NAMED_OPERATORS:
            return rf"\operatorname{{{name}}}"
        return rf"\{name}"

    return _ASCII_OPERATOR_CALL.sub(replace, body)


def _validate_backslashes(body: str) -> None:
    index = 0
    while index < len(body):
        if body[index] != "\\":
            index += 1
            continue
        if index + 1 >= len(body):
            raise MathValidationError("Trailing backslash in LaTeX expression")
        following = body[index + 1]
        if following.isalpha():
            match = re.match(r"[A-Za-z]+", body[index + 1 :])
            assert match is not None
            index += 1 + len(match.group(0))
            continue
        if following not in r"{}_$%&#,;:!| \\":
            raise MathValidationError(f"Malformed LaTeX escape: \\{following}")
        index += 2


def _validate_braces(body: str) -> None:
    depth = 0
    for index, char in enumerate(body):
        if _escaped(body, index):
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                raise MathValidationError("Unmatched closing brace")
    if depth:
        raise MathValidationError("Unmatched opening brace")


def _escaped(text: str, index: int) -> bool:
    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return bool(backslashes % 2)
