from __future__ import annotations

import hashlib
import json
import re
from collections import deque
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel

from .math import normalize_latex_formula, normalize_latex_symbol, normalize_math_text
from .models import EvidencePacket, ExtractedFeatures, Idea, WorkFeatures, WorkItem

FEATURE_KINDS = ("ideas", "principles", "takeaways", "baselines", "benchmarks", "result_facts")
MAX_SOURCE_EVIDENCE_REFERENCES = 24
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
    "comparator": "baselines",
    "comparators": "baselines",
    "control": "baselines",
    "controls": "baselines",
    "standard_method": "baselines",
    "standard_methods": "baselines",
    "reference_theory": "baselines",
    "reference_theories": "baselines",
    "benchmark": "benchmarks",
    "benchmarks": "benchmarks",
    "evaluation_context": "benchmarks",
    "evaluation_contexts": "benchmarks",
    "experimental_system": "benchmarks",
    "experimental_systems": "benchmarks",
    "instrument": "benchmarks",
    "instruments": "benchmarks",
    "observable": "benchmarks",
    "observables": "benchmarks",
    "standard_task": "benchmarks",
    "standard_tasks": "benchmarks",
    "result_fact": "result_facts",
    "result_facts": "result_facts",
}

TITLE_KEYS = {
    "ideas": ("title", "name", "idea_title", "core_idea", "idea_text", "summary"),
    "principles": ("name", "title", "principle", "argument", "abstract_signature"),
    "takeaways": ("title", "name", "main_results", "message_text", "message", "actionable_lesson"),
    "baselines": (
        "name",
        "title",
        "baseline_name",
        "comparator_name",
        "control_name",
        "core_idea",
        "description",
        "summary",
    ),
    "benchmarks": (
        "name",
        "title",
        "benchmark_name",
        "context_name",
        "system_name",
        "task",
        "description",
    ),
    "result_facts": ("title", "name", "fact", "finding", "result"),
}

BODY_KEYS = {
    "ideas": (
        "core_idea",
        "idea_text",
        "mechanism",
        "description",
        "summary",
        "discussion",
        "evidence",
    ),
    "principles": (
        "argument",
        "principle",
        "abstract_signature",
        "discussion",
        "boundary_conditions",
        "evidence",
    ),
    "takeaways": (
        "main_results",
        "message_text",
        "message",
        "actionable_lesson",
        "condition",
        "discussion",
        "evidence",
    ),
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
    global_kind_limits: dict[str, int] | None = None,
    max_per_work: int | None = None,
    require_exact: bool = False,
    user_note: str = "",
) -> EvidencePacket:
    source_features = _feature_list(features)
    selected_kinds = _normalize_kinds(kinds)
    selected_work_ids = {str(item) for item in (work_ids or [])}
    selected_feature_ids = {str(item) for item in (feature_ids or [])}
    if limit_per_kind is not None and int(limit_per_kind) < 0:
        raise ValueError("limit_per_kind must be non-negative")
    if max_per_work is not None and int(max_per_work) < 0:
        raise ValueError("max_per_work must be non-negative")
    normalized_global_limits = _normalize_global_limits(global_kind_limits)
    if require_exact and not normalized_global_limits:
        raise ValueError("require_exact=True requires global_kind_limits")
    eligible: list[tuple[WorkFeatures, dict[str, list[dict[str, Any]]]]] = []
    for item in source_features:
        if selected_work_ids and item.work_id not in selected_work_ids:
            continue
        updates: dict[str, list[dict[str, Any]]] = {}
        for kind in FEATURE_KINDS:
            records = list(getattr(item, kind))
            if kind not in selected_kinds:
                records = []
            if selected_feature_ids:
                records = [
                    record
                    for record in records
                    if str(record.get("id", "")) in selected_feature_ids
                ]
            if limit_per_kind is not None:
                records = records[: max(0, int(limit_per_kind))]
            updates[kind] = records
        if any(updates[kind] for kind in FEATURE_KINDS):
            eligible.append((item, updates))
    if normalized_global_limits or max_per_work is not None:
        selected = _select_with_global_constraints(
            eligible,
            global_kind_limits=normalized_global_limits,
            max_per_work=max_per_work,
        )
    else:
        selected = [item.model_copy(update=updates) for item, updates in eligible]
    if require_exact:
        actual = feature_counts_by_kind(selected)
        missing = {
            kind: {"expected": expected, "actual": actual.get(kind, 0)}
            for kind, expected in normalized_global_limits.items()
            if actual.get(kind, 0) != expected
        }
        if missing:
            raise ValueError(f"Unable to satisfy exact global evidence counts: {missing}")
    note = user_note or (features.user_note if isinstance(features, EvidencePacket) else "")
    query = features.query if isinstance(features, EvidencePacket) else ""
    return EvidencePacket(query=query, features=selected, user_note=note)


def normalize_feature_payload_aliases(payload: dict[str, Any]) -> dict[str, Any]:
    """Map domain-neutral extractor keys onto the backward-compatible schema."""

    output = dict(payload)
    output["baselines"] = _merge_payload_records(
        output,
        canonical="baselines",
        canonical_type="comparator",
        aliases={
            "comparators": "comparator",
            "controls": "control",
            "standard_methods": "standard_method",
            "reference_theories": "reference_theory",
        },
    )
    output["benchmarks"] = _merge_payload_records(
        output,
        canonical="benchmarks",
        canonical_type="evaluation_context",
        aliases={
            "evaluation_contexts": "evaluation_context",
            "experimental_systems": "experimental_system",
            "instruments": "instrument",
            "observables": "observable",
            "standard_tasks": "standard_task",
        },
    )
    return output


def feature_counts_by_kind(features: list[WorkFeatures]) -> dict[str, int]:
    return {kind: sum(len(getattr(item, kind)) for item in features) for kind in FEATURE_KINDS}


def _normalize_global_limits(limits: dict[str, int] | None) -> dict[str, int]:
    normalized: dict[str, int] = {}
    for raw_kind, raw_limit in (limits or {}).items():
        kind = KIND_ALIASES.get(str(raw_kind).lower().strip(), str(raw_kind).lower().strip())
        if kind not in FEATURE_KINDS:
            raise ValueError(f"Unsupported evidence kind in global_kind_limits: {raw_kind!r}")
        limit = int(raw_limit)
        if limit < 0:
            raise ValueError("global_kind_limits values must be non-negative")
        normalized[kind] = normalized.get(kind, 0) + limit
    return normalized


def _select_with_global_constraints(
    eligible: list[tuple[WorkFeatures, dict[str, list[dict[str, Any]]]]],
    *,
    global_kind_limits: dict[str, int],
    max_per_work: int | None,
) -> list[WorkFeatures]:
    """Allocate records with deterministic capacitated matching.

    A max-flow allocation prevents an early feature kind from consuming every
    work slot when an exact multi-kind packet is feasible.
    """

    source = "__source__"
    sink = "__sink__"
    capacity: dict[str, dict[str, int]] = {}
    adjacency: dict[str, list[str]] = {}
    original: dict[tuple[str, str], int] = {}

    def add_edge(left: str, right: str, value: int) -> None:
        adjacency.setdefault(left, []).append(right)
        adjacency.setdefault(right, []).append(left)
        capacity.setdefault(left, {})[right] = value
        capacity.setdefault(right, {})[left] = 0
        original[(left, right)] = value

    available_by_kind = {
        kind: sum(len(updates[kind]) for _, updates in eligible) for kind in FEATURE_KINDS
    }
    for kind in FEATURE_KINDS:
        available = available_by_kind[kind]
        # Supplying global limits defines the complete packet contract. Kinds
        # omitted from that mapping must not consume a work's shared capacity,
        # otherwise unrelated baseline/context rows can make an exact 5/5/5
        # ideas/principles/takeaways packet falsely infeasible.
        limit = min(available, global_kind_limits.get(kind, 0))
        add_edge(source, f"kind:{kind}", limit)
    for index, (_, updates) in enumerate(eligible):
        work_node = f"work:{index}"
        total = sum(len(updates[kind]) for kind in FEATURE_KINDS)
        work_capacity = total if max_per_work is None else min(total, int(max_per_work))
        add_edge(work_node, sink, work_capacity)
        for kind in FEATURE_KINDS:
            count = len(updates[kind])
            if count:
                add_edge(f"kind:{kind}", work_node, count)

    while True:
        parent: dict[str, str | None] = {source: None}
        queue: deque[str] = deque([source])
        while queue and sink not in parent:
            node = queue.popleft()
            for neighbor in adjacency.get(node, []):
                if neighbor not in parent and capacity.get(node, {}).get(neighbor, 0) > 0:
                    parent[neighbor] = node
                    queue.append(neighbor)
        if sink not in parent:
            break
        path_capacity = 1 << 30
        node = sink
        while parent[node] is not None:
            previous = parent[node]
            assert previous is not None
            path_capacity = min(path_capacity, capacity[previous][node])
            node = previous
        node = sink
        while parent[node] is not None:
            previous = parent[node]
            assert previous is not None
            capacity[previous][node] -= path_capacity
            capacity[node][previous] += path_capacity
            node = previous

    selected: list[WorkFeatures] = []
    for index, (item, updates) in enumerate(eligible):
        work_node = f"work:{index}"
        selected_updates: dict[str, list[dict[str, Any]]] = {}
        for kind in FEATURE_KINDS:
            kind_node = f"kind:{kind}"
            edge_capacity = original.get((kind_node, work_node), 0)
            chosen = edge_capacity - capacity.get(kind_node, {}).get(work_node, 0)
            selected_updates[kind] = updates[kind][:chosen]
        if any(selected_updates[kind] for kind in FEATURE_KINDS):
            selected.append(item.model_copy(update=selected_updates))
    return selected


def _merge_payload_records(
    payload: dict[str, Any],
    *,
    canonical: str,
    canonical_type: str,
    aliases: dict[str, str],
) -> list[dict[str, Any]]:
    records = _tag_payload_records(payload.get(canonical), canonical_type)
    for alias, record_type in aliases.items():
        records.extend(_tag_payload_records(payload.pop(alias, None), record_type))
    return records


def _tag_payload_records(value: Any, record_type: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    output: list[dict[str, Any]] = []
    for item in values:
        if isinstance(item, dict):
            record = dict(item)
        elif str(item).strip():
            record = {"name": str(item).strip()}
        else:
            continue
        record.setdefault("record_type", record_type)
        output.append(record)
    return output


def feature_summary_rows(
    features: ExtractedFeatures | EvidencePacket | list[WorkFeatures], *, limit: int = 8
) -> list[dict[str, str]]:
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


def feature_summary_markdown(
    features: ExtractedFeatures | EvidencePacket | list[WorkFeatures], *, limit: int = 8
) -> str:
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


def canonical_evidence_registry(
    features: EvidencePacket | ExtractedFeatures | list[WorkFeatures],
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return the minimal, canonical record registry accepted by ideation.

    Provider metadata, extraction configuration, paths, model labels, and
    generator traces are intentionally absent. Missing legacy record IDs are
    assigned a stable content-derived identity so every reference remains an
    exact ``(work_id, kind, record_id)`` tuple.
    """

    rows: list[dict[str, Any]] = []
    for item in _feature_list(features):
        for kind in FEATURE_KINDS:
            for record in getattr(item, kind):
                title = feature_record_title(record, kind)
                record_text = feature_record_text(record, kind)
                record_id = str(record.get("record_id") or record.get("id") or "").strip()
                if not record_id:
                    digest = hashlib.sha256(
                        "\0".join((item.work_id, kind, title, record_text)).encode("utf-8")
                    ).hexdigest()[:16]
                    record_id = f"auto_{kind}_{digest}"
                rows.append(
                    {
                        "work_id": item.work_id,
                        "work_title": item.title,
                        "kind": kind,
                        "record_id": record_id,
                        "record_type": str(record.get("record_type") or kind.rstrip("s")),
                        "title": title,
                        "text": record_text,
                    }
                )
                if limit is not None and len(rows) >= max(0, int(limit)):
                    return rows
    return rows


def source_evidence_rows(
    features: EvidencePacket | ExtractedFeatures | list[WorkFeatures],
    *,
    limit: int = 24,
) -> list[dict[str, Any]]:
    """Backward-compatible name for canonical source-evidence rows."""

    return canonical_evidence_registry(features, limit=limit)


def requires_mixed_source_citations(
    features: EvidencePacket | ExtractedFeatures | list[WorkFeatures],
) -> bool:
    """Return whether selected evidence spans local and public work identities."""

    work_ids = {
        str(item.work_id or "").strip()
        for item in _feature_list(features)
        if str(item.work_id or "").strip()
    }
    has_local = any(_is_local_work_id(work_id) for work_id in work_ids)
    has_public = any(not _is_local_work_id(work_id) for work_id in work_ids)
    return has_local and has_public


def validate_evidence_references(
    references: Any,
    features: EvidencePacket | ExtractedFeatures | list[WorkFeatures],
) -> list[str]:
    """Validate model references against the exact canonical registry."""

    if not isinstance(references, list) or not references:
        return ["source_evidence must be a nonempty list of canonical record references"]
    registry = canonical_evidence_registry(features)
    identities = {(row["work_id"], row["kind"], row["record_id"]) for row in registry}
    issues: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    retained_seen: set[tuple[str, str, str]] = set()
    for index, raw in enumerate(references):
        if not isinstance(raw, dict):
            issues.append(f"source_evidence[{index}] must be an object")
            continue
        work_id = str(raw.get("work_id") or "").strip()
        raw_kind = str(raw.get("kind") or "").strip().lower()
        kind = KIND_ALIASES.get(raw_kind, raw_kind)
        record_id = str(raw.get("record_id") or raw.get("id") or "").strip()
        missing = [
            name
            for name, value in (("work_id", work_id), ("kind", kind), ("record_id", record_id))
            if not value
        ]
        if missing:
            issues.append(f"source_evidence[{index}] is missing {', '.join(missing)}")
            continue
        identity = (work_id, kind, record_id)
        if identity not in identities:
            issues.append(
                f"source_evidence[{index}] does not resolve to selected record "
                f"({work_id!r}, {kind!r}, {record_id!r})"
            )
            continue
        if identity in seen:
            issues.append(f"source_evidence[{index}] duplicates canonical record {identity!r}")
            continue
        seen.add(identity)
        if index < MAX_SOURCE_EVIDENCE_REFERENCES:
            retained_seen.add(identity)
    if requires_mixed_source_citations(features):
        cited_work_ids = {work_id for work_id, _, _ in retained_seen}
        if not any(_is_local_work_id(work_id) for work_id in cited_work_ids):
            issues.append(
                "source_evidence must cite at least one canonical local record "
                "whose work_id starts with 'L-' among the first 24 saved references because the selected "
                "packet mixes local and public evidence"
            )
        if not any(not _is_local_work_id(work_id) for work_id in cited_work_ids):
            issues.append(
                "source_evidence must cite at least one canonical public record "
                "whose work_id does not start with 'L-' among the first 24 saved references because the "
                "selected packet mixes local and public evidence"
            )
    return issues


def hydrate_evidence_references(
    references: Any,
    features: EvidencePacket | ExtractedFeatures | list[WorkFeatures],
) -> list[dict[str, Any]]:
    """Replace model-authored evidence text with selected canonical records."""

    issues = validate_evidence_references(references, features)
    if issues:
        raise ValueError("Invalid canonical evidence references: " + "; ".join(issues))
    registry = canonical_evidence_registry(features)
    by_identity = {(row["work_id"], row["kind"], row["record_id"]): row for row in registry}
    output: list[dict[str, Any]] = []
    for raw in references:
        raw_kind = str(raw.get("kind") or "").strip().lower()
        identity = (
            str(raw.get("work_id") or "").strip(),
            KIND_ALIASES.get(raw_kind, raw_kind),
            str(raw.get("record_id") or raw.get("id") or "").strip(),
        )
        output.append(dict(by_identity[identity]))
    return output


def _is_local_work_id(work_id: str) -> bool:
    return str(work_id or "").strip().upper().startswith("L-")


def work_review_status(work: WorkItem) -> str:
    if work.metadata.get("is_peer_reviewed"):
        return "peer-reviewed"
    if (
        work.metadata.get("is_preprint")
        or work.metadata.get("has_preprint")
        or str(work.venue).lower() == "arxiv"
    ):
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


def idea_markdown(
    idea: Idea,
    *,
    include_internal_metadata: bool = False,
    compact: bool = False,
) -> str:
    """Render an Idea Card for notebooks, exports, or detailed inspection.

    ``compact=True`` keeps the scientific thesis, mechanism, equations, and
    validation hand-off while omitting long operational lists. It is intended
    for tutorial output cells and README showcases; the default remains the
    complete backward-compatible card.
    """

    if compact:
        return _compact_idea_markdown(idea)
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
    _section(lines, "Comparators / Controls / Reference Methods", idea.baselines)
    _section(lines, "Metrics", idea.metrics)
    _section(lines, "Risks", idea.risks)
    _section(lines, "Assumptions", idea.assumptions)
    _source_evidence_section(lines, idea.source_evidence)
    if include_internal_metadata:
        _json_section(lines, "Lineage", idea.lineage)
        _json_section(lines, "Trace", idea.trace)
        _json_section(lines, "Generation Metadata", idea.generation_metadata)
    return "\n".join(lines).strip() + "\n"


def _compact_idea_markdown(idea: Idea) -> str:
    details = idea.methodological_details or {}
    lines = [
        f"# {idea.title}",
        "",
        f"**Mode:** `{idea.mode.replace('_', '-')}`  ",
        f"**Model:** `{idea.model}`",
        "",
        f"**Thesis:** {idea.thesis}",
    ]
    if idea.novelty_claim:
        lines.extend(("", f"**Novelty:** {idea.novelty_claim}"))
    mechanisms = [str(item).strip() for item in idea.mechanism_design if str(item).strip()]
    if mechanisms:
        lines.extend(("", "## Mechanism", *[f"- {item}" for item in mechanisms[:3]]))
    equations = details.get("equations", [])
    if not isinstance(equations, list):
        equations = []
    rendered_equations: list[str] = []
    for row in equations[:3]:
        raw = (
            row.get("equation") or row.get("latex") or row.get("formula")
            if isinstance(row, dict)
            else row
        )
        if str(raw or "").strip():
            rendered_equations.append(normalize_latex_formula(_string_value(raw), display=True))
    if rendered_equations:
        lines.extend(("", "## Core equations", *rendered_equations))
    validation = [str(item).strip() for item in idea.validation_protocol if str(item).strip()]
    if validation:
        lines.extend(("", "## Validation", *[f"- {item}" for item in validation[:3]]))
    work_count = len(set(idea.evidence_work_ids))
    if idea.source_evidence:
        record_label = "record" if len(idea.source_evidence) == 1 else "records"
        work_label = "work" if work_count == 1 else "works"
        lines.extend(
            (
                "",
                f"**Evidence:** {len(idea.source_evidence)} canonical {record_label} across "
                f"{work_count} {work_label}.",
            )
        )
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


def _feature_list(
    features: ExtractedFeatures | EvidencePacket | list[WorkFeatures],
) -> list[WorkFeatures]:
    if isinstance(features, EvidencePacket):
        return list(features.features)
    if isinstance(features, ExtractedFeatures):
        return list(features.items)
    return list(features)


def _normalize_kinds(kinds: Iterable[str] | None) -> set[str]:
    if kinds is None:
        return set(FEATURE_KINDS)
    normalized = {
        KIND_ALIASES.get(str(kind).lower().strip(), str(kind).lower().strip()) for kind in kinds
    }
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
                symbol = normalize_latex_symbol(
                    _string_value(row.get("symbol") or row.get("name") or row.get("term"))
                )
                definition = _string_value(
                    row.get("definition") or row.get("description") or row.get("text")
                )
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
                latex = normalize_latex_formula(
                    _string_value(row.get("latex") or row.get("formula") or row.get("equation")),
                    display=True,
                )
                explanation = _string_value(
                    row.get("explanation") or row.get("meaning") or row.get("description")
                )
                lines.append(
                    f"- **{name}:** {latex}" + (f" — {explanation}" if explanation else "")
                )
            else:
                lines.append(f"- {normalize_latex_formula(_string_value(row), display=True)}")
    workflow = details.get("workflow") if isinstance(details.get("workflow"), list) else []
    if workflow:
        lines.extend(["", "#### Workflow"])
        for index, row in enumerate(workflow, start=1):
            if isinstance(row, dict):
                step = clean_method_label(
                    _string_value(row.get("step") or row.get("title") or f"Step {index}")
                )
                detail = clean_method_detail(
                    _string_value(row.get("detail") or row.get("description") or row.get("text"))
                )
                lines.append(f"{index}. **{step}:** {detail}" if detail else f"{index}. {step}")
            else:
                lines.append(f"{index}. {clean_method_detail(_string_value(row))}")
    checks = (
        details.get("reliability_checks")
        if isinstance(details.get("reliability_checks"), list)
        else []
    )
    if checks:
        lines.extend(["", "#### Reliability Checks"])
        for row in checks:
            if isinstance(row, dict):
                check = clean_method_label(
                    _string_value(row.get("check") or row.get("title") or row.get("name"))
                )
                detail = clean_method_detail(
                    _string_value(row.get("detail") or row.get("description") or row.get("text"))
                )
                lines.append(
                    f"- **{check}:** {detail}" if check and detail else f"- {check or detail}"
                )
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
    lines.extend(
        ["", f"### {title}", "```json", json.dumps(value, ensure_ascii=False, indent=2), "```"]
    )


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
    """Backward-compatible formula normalizer using the strict shared parser."""

    return normalize_latex_formula(value, display=False)


def normalize_inline_math_text(value: str) -> str:
    """Normalize explicit math only; never guess that prose tokens are math."""

    return normalize_math_text(value)
