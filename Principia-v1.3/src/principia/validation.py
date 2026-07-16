from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator, model_validator

from .math import MathValidationError, generated_math_issues, normalize_math_value
from .models import Idea, PipelineResult, PrincipiaModel, utc_now


class ValidationEvidenceReference(PrincipiaModel):
    """A portable reference to evidence used by an Idea Card."""

    work_id: str
    record_id: str = ""
    kind: str = ""
    title: str = ""
    text: str = ""

    @field_validator("work_id", "record_id", "kind", "text")
    @classmethod
    def canonical_reference_fields_required(cls, value: str) -> str:
        cleaned = " ".join(str(value or "").split())
        if not cleaned:
            raise ValueError(
                "Validation evidence references require work_id, record_id, kind, and text"
            )
        return cleaned


class ValidationPlan(PrincipiaModel):
    """A standalone, serializable experiment hand-off for a generated idea.

    The plan is derived entirely from an existing :class:`~principia.Idea`.
    Building or rendering it never calls an LLM.
    """

    schema_version: str = "1.0"
    idea_id: str
    idea_title: str
    goal: str
    thesis: str
    validation_protocol: list[str] = Field(default_factory=list)
    baselines: list[str] = Field(default_factory=list)
    comparators: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    evidence_references: list[ValidationEvidenceReference] = Field(default_factory=list)
    model: str = ""
    mode: str
    run_id: str = ""
    idea_created_at: str = ""
    created_at: str = Field(default_factory=utc_now)

    @model_validator(mode="before")
    @classmethod
    def canonicalize_validation_math(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        for field in (
            "idea_title",
            "goal",
            "thesis",
            "validation_protocol",
            "baselines",
            "comparators",
            "metrics",
            "risks",
            "assumptions",
            "evidence_references",
        ):
            if field in data:
                try:
                    data[field] = normalize_math_value(data[field])
                except MathValidationError as exc:
                    raise ValueError(f"invalid LaTeX in validation plan: {exc}") from exc
        return data

    @field_validator("idea_id", "idea_title", "goal", "thesis")
    @classmethod
    def required_text(cls, value: str) -> str:
        cleaned = " ".join(str(value or "").split())
        if not cleaned:
            raise ValueError("Validation plan identity, goal, and thesis fields must not be empty")
        return cleaned

    def to_markdown(self) -> str:
        """Render this plan as deterministic, human-readable Markdown."""

        return render_validation_plan_markdown(self)

    def to_json(self, *, indent: int = 2) -> str:
        """Render this plan as UTF-8-safe JSON with a trailing newline."""

        return validation_plan_json(self, indent=indent)


def build_validation_plan(
    source: Idea | PipelineResult,
    *,
    goal: str | None = None,
    comparators: Iterable[str] | None = None,
    created_at: str | None = None,
) -> ValidationPlan:
    """Build a standalone validation plan without performing another LLM call.

    ``source`` may be an Idea Card or a full pipeline result. When an Idea is
    supplied directly, ``goal`` is required because an Idea intentionally does
    not duplicate the research query.
    """

    plan_goal: str | None
    if isinstance(source, PipelineResult):
        idea = source.idea
        plan_goal = goal if goal is not None else source.goal
    else:
        idea = source
        plan_goal = goal
    if not str(plan_goal or "").strip():
        raise ValueError("goal is required when building a validation plan from an Idea")

    baseline_values = _unique_text(idea.baselines)
    comparator_values = _unique_text(comparators if comparators is not None else baseline_values)
    plan = ValidationPlan(
        idea_id=idea.id,
        idea_title=idea.title,
        goal=str(plan_goal),
        thesis=idea.thesis,
        validation_protocol=_unique_text(idea.validation_protocol),
        baselines=baseline_values,
        comparators=comparator_values,
        metrics=_unique_text(idea.metrics),
        risks=_unique_text(idea.risks),
        assumptions=_unique_text(idea.assumptions),
        evidence_references=_evidence_references(idea),
        model=idea.model,
        mode=idea.mode,
        run_id=idea.run_id,
        idea_created_at=idea.created_at,
        created_at=created_at or utc_now(),
    )
    issues = generated_math_issues(
        {
            "goal": plan.goal,
            "thesis": plan.thesis,
            "validation_protocol": plan.validation_protocol,
            "baselines": plan.baselines,
            "comparators": plan.comparators,
            "metrics": plan.metrics,
            "risks": plan.risks,
            "assumptions": plan.assumptions,
            "evidence_references": [item.model_dump() for item in plan.evidence_references],
        },
        path="validation_plan",
    )
    if issues:
        raise ValueError("Validation plan contains invalid LaTeX: " + "; ".join(issues))
    return plan


def validation_plan_json(plan: ValidationPlan, *, indent: int = 2) -> str:
    """Serialize a validation plan using its stable public schema."""

    return json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, indent=indent) + "\n"


def render_validation_plan_markdown(plan: ValidationPlan) -> str:
    """Render a validation plan as a collaborator-ready Markdown document."""

    lines = [
        f"# Validation Plan: {_inline(plan.idea_title)}",
        "",
        f"- Schema version: `{_inline(plan.schema_version)}`",
        f"- Idea ID: `{_inline(plan.idea_id)}`",
        f"- Mode: `{_inline(plan.mode)}`",
        f"- Model: `{_inline(plan.model) or 'unspecified'}`",
        f"- Created: `{_inline(plan.created_at)}`",
        "",
        "## Goal",
        "",
        _paragraph(plan.goal),
        "",
        "## Thesis",
        "",
        _paragraph(plan.thesis),
        "",
        "## Validation Protocol",
        "",
        *_markdown_list(plan.validation_protocol, ordered=True),
        "",
        "## Baselines and Comparators",
        "",
        *_markdown_list(plan.comparators or plan.baselines),
        "",
        "## Metrics",
        "",
        *_markdown_list(plan.metrics),
        "",
        "## Risks",
        "",
        *_markdown_list(plan.risks),
        "",
        "## Assumptions",
        "",
        *_markdown_list(plan.assumptions),
        "",
        "## Evidence References",
        "",
        *_evidence_markdown(plan.evidence_references),
        "",
    ]
    return "\n".join(lines).strip() + "\n"


def validation_plan_markdown(plan: ValidationPlan) -> str:
    """Backward-friendly alias for :func:`render_validation_plan_markdown`."""

    return render_validation_plan_markdown(plan)


def write_validation_plan(plan: ValidationPlan, directory: str | Path) -> tuple[Path, Path]:
    """Write JSON and Markdown artifacts to ``directory`` and return their paths."""

    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    markdown_path = target / "validation_plan.md"
    json_path = target / "validation_plan.json"
    markdown_path.write_text(render_validation_plan_markdown(plan), encoding="utf-8")
    json_path.write_text(validation_plan_json(plan), encoding="utf-8")
    return markdown_path, json_path


def _evidence_references(idea: Idea) -> list[ValidationEvidenceReference]:
    references: list[ValidationEvidenceReference] = []
    seen: set[tuple[str, str, str, str]] = set()
    for raw in idea.source_evidence:
        if not isinstance(raw, dict):
            continue
        work_id = _inline(raw.get("work_id"))
        record_id = _inline(raw.get("id") or raw.get("record_id"))
        kind = _inline(raw.get("kind") or raw.get("record_type"))
        title = _inline(raw.get("title") or raw.get("work_title"))
        text = _paragraph(raw.get("text") or raw.get("evidence") or raw.get("claim"))
        missing = [
            name
            for name, value in (
                ("work_id", work_id),
                ("record_id", record_id),
                ("kind", kind),
                ("text", text),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                "Idea contains a non-canonical evidence reference missing " + ", ".join(missing)
            )
        identity = (work_id, record_id, kind, text)
        if identity in seen:
            continue
        seen.add(identity)
        references.append(
            ValidationEvidenceReference(
                work_id=work_id,
                record_id=record_id,
                kind=kind,
                title=title,
                text=text,
            )
        )
    return references


def _evidence_markdown(references: list[ValidationEvidenceReference]) -> list[str]:
    if not references:
        return ["- Not specified."]
    lines: list[str] = []
    for reference in references:
        label_parts = [f"work `{_inline(reference.work_id)}`"]
        if reference.kind:
            label_parts.append(_inline(reference.kind))
        if reference.record_id:
            label_parts.append(f"record `{_inline(reference.record_id)}`")
        detail = _inline(reference.title) or _inline(reference.text)
        line = f"- {', '.join(label_parts)}"
        if detail:
            line += f": {detail}"
        lines.append(line)
    return lines


def _markdown_list(values: Iterable[Any], *, ordered: bool = False) -> list[str]:
    cleaned = _unique_text(values)
    if not cleaned:
        return ["- Not specified."]
    if ordered:
        return [f"{index}. {_paragraph(value)}" for index, value in enumerate(cleaned, start=1)]
    return [f"- {_paragraph(value)}" for value in cleaned]


def _unique_text(values: Iterable[Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _paragraph(value)
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def _inline(value: Any) -> str:
    return " ".join(str(value or "").replace("`", "'").split())


def _paragraph(value: Any) -> str:
    return " ".join(str(value or "").split())
