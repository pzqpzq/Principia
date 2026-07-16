from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from principia.math import normalize_latex_formula
from scripts.check_release_math import (
    ReleaseMathError,
    compile_with_katex,
    extract_from_json,
    extract_from_notebook,
    extract_math_spans,
)


def test_markdown_extraction_ignores_code_and_finds_visible_math(tmp_path: Path) -> None:
    text = """Visible $x_{1} \\le y$.

`literal $not_math$`

```python
price = "$also_not_math$"
```

$$
\\tau = \\frac{Q}{\\pi f_{0}}
$$
"""
    occurrences = extract_math_spans(
        text, path=tmp_path / "example.md", location="markdown", markdown=True
    )

    assert [(item.expression, item.display) for item in occurrences] == [
        (r"x_{1} \le y", False),
        (r"\tau = \frac{Q}{\pi f_{0}}", True),
    ]


@pytest.mark.parametrize(
    "text, message",
    [
        ("Broken $x", "unbalanced dollar delimiter"),
        ("Broken $x $$ y$", "nested or mismatched dollar delimiter"),
        ("Broken $$x == 1$$", "use = for equality"),
        ("Ambiguous $R_cf$", "non-canonical LaTeX"),
        ("Ambiguous $SNR^2$", "non-canonical LaTeX"),
        (r"Broken \(x\)", "use $...$ or $$...$$"),
    ],
)
def test_structural_math_defects_fail_closed(tmp_path: Path, text: str, message: str) -> None:
    with pytest.raises(ReleaseMathError, match=re_escape(message)):
        extract_math_spans(text, path=tmp_path / "broken.md", location="markdown", markdown=True)


def re_escape(value: str) -> str:
    """Keep parametrized expected messages readable."""

    import re

    return re.escape(value)


def test_json_and_notebook_scan_retained_text_not_code_source(tmp_path: Path) -> None:
    json_path = tmp_path / "artifact.json"
    json_path.write_text(
        json.dumps({"idea": {"formula": r"$$R = \sigma^{2}$$"}}), encoding="utf-8"
    )
    notebook_path = tmp_path / "tutorial.ipynb"
    notebook_path.write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "cell_type": "code",
                        "source": ["ignored = '$not_retained$'"],
                        "outputs": [
                            {
                                "output_type": "display_data",
                                "data": {"text/markdown": [r"Result: $\alpha + \beta$.\n"]},
                            }
                        ],
                    }
                ],
                "metadata": {},
                "nbformat": 4,
                "nbformat_minor": 5,
            }
        ),
        encoding="utf-8",
    )

    json_spans = extract_from_json(json_path)
    notebook_spans = extract_from_notebook(notebook_path)

    assert [item.expression for item in json_spans] == [r"R = \sigma^{2}"]
    assert [item.expression for item in notebook_spans] == [r"\alpha + \beta"]


@pytest.mark.skipif(
    not os.environ.get("PRINCIPIA_NODE") or not os.environ.get("PRINCIPIA_KATEX_MODULE"),
    reason="temporary KaTeX QA runtime was not supplied",
)
def test_real_katex_strict_mode_accepts_valid_and_rejects_invalid(tmp_path: Path) -> None:
    node = Path(os.environ["PRINCIPIA_NODE"])
    katex = Path(os.environ["PRINCIPIA_KATEX_MODULE"])
    valid = extract_math_spans(
        r"$\operatorname{Var}(X) \le \sigma^{2}$",
        path=tmp_path / "valid.md",
        location="markdown",
        markdown=True,
    )
    compile_with_katex(valid, node_executable=node, katex_module=katex)

    invalid = extract_math_spans(
        r"$\notARealCommand{x}$",
        path=tmp_path / "invalid.md",
        location="markdown",
        markdown=True,
    )
    with pytest.raises(ReleaseMathError, match="Strict KaTeX rejected 1"):
        compile_with_katex(invalid, node_executable=node, katex_module=katex)


@pytest.mark.skipif(
    not os.environ.get("PRINCIPIA_NODE") or not os.environ.get("PRINCIPIA_KATEX_MODULE"),
    reason="temporary KaTeX QA runtime was not supplied",
)
def test_live_normalized_physics_formulas_compile_with_strict_katex(tmp_path: Path) -> None:
    node = Path(os.environ["PRINCIPIA_NODE"])
    katex = Path(os.environ["PRINCIPIA_KATEX_MODULE"])
    rendered = "\n".join(
        (
            normalize_latex_formula(
                "SNR^2 = T_int * ∫ (|S_xx(ω)|^2 / N_meas(ω)) dω"
            ),
            normalize_latex_formula(
                r"N_total = ∫ (dN/dx) * exp(-∫ \alpha (T(x)) dx) dx"
            ),
        )
    )
    occurrences = extract_math_spans(
        rendered,
        path=tmp_path / "normalized.md",
        location="markdown",
        markdown=True,
    )

    compile_with_katex(occurrences, node_executable=node, katex_module=katex)
