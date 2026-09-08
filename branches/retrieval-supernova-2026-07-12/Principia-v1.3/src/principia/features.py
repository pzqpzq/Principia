from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel

from .models import EvidencePacket, ExtractedFeatures, Idea, WorkFeatures, WorkItem

FEATURE_KINDS = ("ideas", "principles", "takeaways", "baselines", "benchmarks", "result_facts")
KIND_ALIASES = {
    "idea": "ideas",
    "ideas": "ideas",
    "existed_idea": "ideas",
    "existed_ideas": "ideas",
    "principle": "principles",
    "principles": "principles",
    "takeaway": "takeaways",
    "takeaways": "takeaways",
    "takeaway_message": "takeaways",
    "takeaway_messages": "takeaways",
    "baseline": "baselines",
    "baselines": "baselines",
    "benchmark": "benchmarks",
    "benchmarks": "benchmarks",
    "result_fact": "result_facts",
    "result_facts": "result_facts",
}

TITLE_KEYS = {
    "ideas": ("title", "name", "idea_title", "core_idea", "idea_text", "summary"),
    "principles": ("name", "title", "principle", "argument", "abstract_signature"),
    "takeaways": ("title", "name", "main_results", "message_text", "message", "actionable_lesson"),
    "baselines": ("name", "title", "baseline_name", "core_idea", "description", "summary"),
    "benchmarks": ("name", "title", "benchmark_name", "task", "description"),
    "result_facts": ("title", "name", "fact", "finding", "result"),
}

BODY_KEYS = {
    "ideas": ("core_idea", "idea_text", "mechanism", "description", "summary", "discussion", "evidence"),
    "principles": ("argument", "principle", "abstract_signature", "discussion", "boundary_conditions", "evidence"),
    "takeaways": ("main_results", "message_text", "message", "actionable_lesson", "condition", "discussion", "evidence"),
    "baselines": ("core_idea", "methodology", "description", "summary", "discussion", "evidence"),
    "benchmarks": ("description", "task", "data_form", "scale", "metrics", "evidence"),
    "result_facts": ("fact", "finding", "result", "evidence"),
}


def select_evidence(
    features: ExtractedFeatures | EvidencePacket | list[WorkFeatures],
    *,
    kinds: Iterable[str] | None = None,
    work_ids: Iterable[str] | None = None,
    feature_ids: Iterable[str] | None = None,
    limit_per_kind: int | None = None,
    user_note: str = "",
) -> EvidencePacket:
    source_features = _feature_list(features)
    selected_kinds = _normalize_kinds(kinds)
    selected_work_ids = {str(item) for item in (work_ids or [])}
    selected_feature_ids = {str(item) for item in (feature_ids or [])}
    selected: list[WorkFeatures] = []
    for item in source_features:
        if selected_work_ids and item.work_id not in selected_work_ids:
            continue
        updates: dict[str, list[dict[str, Any]]] = {}
        for kind in FEATURE_KINDS:
            records = list(getattr(item, kind))
            if kind not in selected_kinds:
                records = []
            if selected_feature_ids:
                records = [record for record in records if str(record.get("id", "")) in selected_feature_ids]
            if limit_per_kind is not None:
                records = records[: max(0, int(limit_per_kind))]
            updates[kind] = records
        if any(updates[kind] for kind in FEATURE_KINDS):
            selected.append(item.model_copy(update=updates))
    note = user_note or (features.user_note if isinstance(features, EvidencePacket) else "")
    query = features.query if isinstance(features, EvidencePacket) else ""
    return EvidencePacket(query=query, features=selected, user_note=note)


def feature_summary_rows(features: ExtractedFeatures | EvidencePacket | list[WorkFeatures], *, limit: int = 8) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in _feature_list(features)[: max(0, int(limit))]:
        rows.append(
            {
                "work_id": item.work_id,
                "work_title": item.title,
                "existed_idea": _first_record_text(item.ideas, "ideas"),
                "principle": _first_record_text(item.principles, "principles"),
                "takeaway": _first_record_text(item.takeaways, "takeaways"),
            }
        )
    return rows


def feature_summary_markdown(features: ExtractedFeatures | EvidencePacket | list[WorkFeatures], *, limit: int = 8) -> str:
    rows = feature_summary_rows(features, limit=limit)
    return markdown_table(
        ["Work ID", "Work title", "Existed idea", "Principle", "Takeaway"],
        [
            [
                row["work_id"],
                truncate(row["work_title"], 72),
                truncate(row["existed_idea"], 120),
                truncate(row["principle"], 120),
                truncate(row["takeaway"], 120),
            ]
            for row in rows
        ],
    )


def source_evidence_rows(features: EvidencePacket | ExtractedFeatures | list[WorkFeatures], *, limit: int = 24) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in _feature_list(features):
        for kind in FEATURE_KINDS:
            for record in getattr(item, kind):
                rows.append(
                    {
                        "work_id": item.work_id,
                        "work_title": item.title,
                        "kind": kind,
                        "id": record.get("id", ""),
                        "title": feature_record_title(record, kind),
                        "text": feature_record_text(record, kind),
                    }
                )
                if len(rows) >= limit:
                    return rows
    return rows


def work_review_status(work: WorkItem) -> str:
    if work.metadata.get("is_peer_reviewed"):
        return "peer-reviewed"
    if work.metadata.get("is_preprint") or work.metadata.get("has_preprint") or str(work.venue).lower() == "arxiv":
        return "preprint"
    return "unknown"


def feature_record_title(record: dict[str, Any], kind: str) -> str:
    normalized_kind = KIND_ALIASES.get(kind, kind)
    for key in TITLE_KEYS.get(normalized_kind, ()):
        value = _string_value(record.get(key))
        if value:
            return value
    return str(record.get("id") or normalized_kind).strip()


def feature_record_text(record: dict[str, Any], kind: str) -> str:
    normalized_kind = KIND_ALIASES.get(kind, kind)
    for key in BODY_KEYS.get(normalized_kind, ()):
        value = _string_value(record.get(key))
        if value:
            return value
    return feature_record_title(record, normalized_kind)


def idea_markdown(idea: Idea) -> str:
    lines = [
        f"## {idea.title}",
        "",
        f"**ID:** `{idea.id}`  ",
        f"**Mode:** `{idea.mode}`  ",
        f"**Model:** `{idea.model}`",
        "",
        f"**Thesis:** {idea.thesis}",
    ]
    _section(lines, "Novelty Claim", idea.novelty_claim)
    _section(lines, "Mechanistic Design", idea.mechanism_design)
    _methodological_section(lines, idea.methodological_details)
    _section(lines, "Method Variants", idea.method_variants)
    _section(lines, "Derived Principles", idea.derived_principles)
    _section(lines, "Why It Might Work", idea.why_it_might_work)
    _section(lines, "Validation Protocol", idea.validation_protocol)
    _section(lines, "Relevant Baselines", idea.baselines)
    _section(lines, "Metrics", idea.metrics)
    _section(lines, "Risks", idea.risks)
    _section(lines, "Assumptions", idea.assumptions)
    _source_evidence_section(lines, idea.source_evidence)
    _json_section(lines, "Lineage", idea.lineage)
    _json_section(lines, "Trace", idea.trace)
    _json_section(lines, "Generation Metadata", idea.generation_metadata)
    return "\n".join(lines).strip() + "\n"


def schema_markdown(model: type[BaseModel] | BaseModel) -> str:
    cls = model if isinstance(model, type) else type(model)
    rows = []
    for name, field in cls.model_fields.items():
        annotation = str(field.annotation).replace("typing.", "")
        default = "required" if field.is_required() else "optional"
        rows.append([name, annotation, default])
    return markdown_table(["Field", "Type", "Required"], rows)


def markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    def clean(value: Any) -> str:
        text = str(value or "").replace("\n", " ").replace("|", "\\|")
        return " ".join(text.split())

    return "\n".join(
        [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |",
            *["| " + " | ".join(clean(value) for value in row) + " |" for row in rows],
        ]
    )


def truncate(text: str, limit: int) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "..."


def _feature_list(features: ExtractedFeatures | EvidencePacket | list[WorkFeatures]) -> list[WorkFeatures]:
    if isinstance(features, EvidencePacket):
        return list(features.features)
    if isinstance(features, ExtractedFeatures):
        return list(features.items)
    return list(features)


def _normalize_kinds(kinds: Iterable[str] | None) -> set[str]:
    if kinds is None:
        return set(FEATURE_KINDS)
    normalized = {KIND_ALIASES.get(str(kind).lower().strip(), str(kind).lower().strip()) for kind in kinds}
    return {kind for kind in normalized if kind in FEATURE_KINDS}


def _first_record_text(records: list[dict[str, Any]], kind: str) -> str:
    return feature_record_text(records[0], kind) if records else ""


def _string_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, list):
        return "; ".join(_string_value(item) for item in value if _string_value(item))
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def _section(lines: list[str], title: str, value: str | list[str]) -> None:
    values = value if isinstance(value, list) else ([value] if value else [])
    values = [str(item).strip() for item in values if str(item).strip()]
    if not values:
        return
    lines.extend(["", f"### {title}", *[f"- {item}" for item in values]])


def _methodological_section(lines: list[str], details: dict[str, Any]) -> None:
    if not details:
        return
    lines.extend(["", "### Methodological Details"])
    summary = _string_value(details.get("summary"))
    if summary:
        lines.extend(["", summary])
    symbols = details.get("symbols") if isinstance(details.get("symbols"), list) else []
    if symbols:
        lines.extend(["", "#### Symbols"])
        for row in symbols:
            if isinstance(row, dict):
                symbol = normalize_latex_markup(_string_value(row.get("symbol") or row.get("name") or row.get("term")))
                definition = _string_value(row.get("definition") or row.get("description") or row.get("text"))
                symbol_text = symbol if symbol.startswith("$") else f"`{symbol}`"
                lines.append(f"- {symbol_text}: {definition}" if symbol else f"- {definition}")
            else:
                lines.append(f"- {_string_value(row)}")
    equations = details.get("equations") if isinstance(details.get("equations"), list) else []
    if equations:
        lines.extend(["", "#### Equations"])
        for row in equations:
            if isinstance(row, dict):
                name = _string_value(row.get("name") or row.get("title") or "Equation")
                latex = normalize_latex_markup(_string_value(row.get("latex") or row.get("formula") or row.get("equation")))
                explanation = _string_value(row.get("explanation") or row.get("meaning") or row.get("description"))
                lines.append(f"- **{name}:** {latex}" + (f" — {explanation}" if explanation else ""))
            else:
                lines.append(f"- {normalize_latex_markup(_string_value(row))}")
    workflow = details.get("workflow") if isinstance(details.get("workflow"), list) else []
    if workflow:
        lines.extend(["", "#### Workflow"])
        for index, row in enumerate(workflow, start=1):
            if isinstance(row, dict):
                step = clean_method_label(_string_value(row.get("step") or row.get("title") or f"Step {index}"))
                detail = clean_method_detail(_string_value(row.get("detail") or row.get("description") or row.get("text")))
                lines.append(f"{index}. **{step}:** {detail}" if detail else f"{index}. {step}")
            else:
                lines.append(f"{index}. {clean_method_detail(_string_value(row))}")
    checks = details.get("reliability_checks") if isinstance(details.get("reliability_checks"), list) else []
    if checks:
        lines.extend(["", "#### Reliability Checks"])
        for row in checks:
            if isinstance(row, dict):
                check = clean_method_label(_string_value(row.get("check") or row.get("title") or row.get("name")))
                detail = clean_method_detail(_string_value(row.get("detail") or row.get("description") or row.get("text")))
                lines.append(f"- **{check}:** {detail}" if check and detail else f"- {check or detail}")
            else:
                lines.append(f"- {_string_value(row)}")


def _source_evidence_section(lines: list[str], rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    lines.extend(["", "### Source Evidence"])
    for row in rows[:24]:
        title = _string_value(row.get("title") or row.get("work_title") or row.get("id"))
        text = truncate(_string_value(row.get("text")), 220)
        lines.append(f"- **{row.get('kind', 'evidence')} / {title}:** {text}")


def _json_section(lines: list[str], title: str, value: dict[str, Any]) -> None:
    if not value:
        return
    lines.extend(["", f"### {title}", "```json", json.dumps(value, ensure_ascii=False, indent=2), "```"])


def clean_method_label(value: str) -> str:
    text = " ".join(str(value or "").split())
    for _ in range(4):
        previous = text
        text = re.sub(r"^\s*(?:step\s*)?\d+[\).:\-]\s*", "", text, flags=re.I)
        text = re.sub(r"^\s*step\s+\d+\s*[:\-]\s*", "", text, flags=re.I)
        if text == previous:
            break
    text = re.sub(r"^\s*step\s+\d+\s*$", "Step", text, flags=re.I)
    return text.strip() or "Step"


def clean_method_detail(value: str) -> str:
    text = " ".join(str(value or "").split())
    for _ in range(4):
        previous = text
        text = re.sub(r"^\s*(?:step\s*)?\d+[\).:\-]\s*", "", text, flags=re.I)
        text = re.sub(r"^\s*step\s+\d+\s*[:\-]\s*", "", text, flags=re.I)
        if text == previous:
            break
    return normalize_inline_math_text(text.strip())


def normalize_latex_markup(value: str) -> str:
    text = " ".join(str(value or "").split())
    if not text or "$" in text:
        return text
    if any(marker in text for marker in ("\\", "^", "_", "=", "\\sum", "\\arg", "\\mid", "\\le", "\\ge")):
        return f"${text}$"
    return text


def normalize_inline_math_text(value: str) -> str:
    text = " ".join(str(value or "").split())
    if not text or "$" in text:
        return text
    text = re.sub(r"(?<![\w$])([A-Za-z]+_[A-Za-z0-9]+)(?![\w$])", r"$\1$", text)
    text = re.sub(r"(?<![\w$])([A-Z])(?=(?:[,.;:)]|\s+(?:and|or|from|to|with|under|for|as)\b))", r"$\1$", text)
    return text
