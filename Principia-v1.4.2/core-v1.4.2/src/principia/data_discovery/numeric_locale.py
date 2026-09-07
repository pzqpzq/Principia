"""Conservative column-level numeric punctuation inference."""
from __future__ import annotations

import csv
import io
import re
from itertools import islice
from typing import Any

_EXP = r"(?:[eE][+-]?\d+)?"
_DECIMAL_COMMA = re.compile(r"^[+-]?(?:\d+|\d{1,3}(?:\.\d{3})+),\d+" + _EXP + r"$")
_GROUPED_COMMA = re.compile(r"^[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?" + _EXP + r"$")


def punctuation_hint(value: Any) -> str:
    if not isinstance(value, str) or "," not in value:
        return ""
    text = value.strip()
    decimal = bool(_DECIMAL_COMMA.fullmatch(text))
    grouped = bool(_GROUPED_COMMA.fullmatch(text))
    if decimal and not grouped:
        return "decimal_comma"
    if grouped and not decimal:
        return "grouped_comma"
    return "ambiguous" if decimal and grouped else ""


def infer_column_locales(rows: list[list[Any]], width: int) -> list[str]:
    hints: list[set[str]] = [set() for _ in range(width)]
    for row in rows:
        for index, value in enumerate(row[:width]):
            hint = punctuation_hint(value)
            if hint:
                hints[index].add(hint)
    result = []
    for values in hints:
        explicit = values - {"ambiguous"}
        result.append(next(iter(explicit)) if len(explicit) == 1 else "conflicting" if len(explicit) > 1 else "ambiguous" if values else "plain")
    return result


def parse_numeric(value: Any, locale: str = "plain") -> float:
    if not isinstance(value, str):
        return float(value)
    text = value.strip()
    if "," not in text:
        return float(text)
    if locale == "decimal_comma" and _DECIMAL_COMMA.fullmatch(text):
        return float(text.replace(".", "").replace(",", "."))
    if locale == "grouped_comma" and _GROUPED_COMMA.fullmatch(text):
        return float(text.replace(",", ""))
    raise ValueError("Numeric punctuation is ambiguous or inconsistent with this column")


def looks_numeric(value: Any) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError, OverflowError):
        return bool(punctuation_hint(value))


def detect_delimiter(sample: str, *, suffix: str = "") -> str:
    delimiter = "\t" if suffix in {".tsv", ".tab"} or "\t" in sample[:4096] else ","
    try:
        delimiter = csv.Sniffer().sniff(sample[:32_000], delimiters=",\t;|").delimiter
    except csv.Error:
        pass
    # Sniffer favors commas in headerless decimal-comma tables. An alternate
    # separator must produce a consistent table with substantially more numeric
    # cells before it can override that decision.
    def confidence(separator: str) -> float:
        rows = list(islice(csv.reader(io.StringIO(sample), delimiter=separator), 20))
        rows = [row for row in rows if row]
        if len(rows) < 3 or len(rows[0]) < 2 or len({len(row) for row in rows}) != 1:
            return 0.0
        if not any(looks_numeric(value) for value in rows[0]):
            rows = rows[1:]
        cells = [value for row in rows for value in row if value.strip()]
        return sum(looks_numeric(value) for value in cells) / max(1, len(cells))

    score = confidence(delimiter)
    for alternate in ("\t", ";", "|"):
        if alternate != delimiter and alternate in sample[:4096]:
            candidate_score = confidence(alternate)
            if candidate_score >= 0.6 and candidate_score > score + 0.25:
                delimiter, score = alternate, candidate_score
    return delimiter
