#!/usr/bin/env python3
"""Build a deterministic Global Cloud v2 canonical dataset.

This is a local migration tool. It never contacts GitHub and never publishes.
The input Cloud must be an already pinned canonical checkout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from principia.cloud.canonical import CanonicalCloudRepository
from principia.cloud.models_v2 import WorkRevisionV2
from principia.domain.hashing import canonical_json_bytes

MIGRATED_AT = "2026-08-21T00:00:00+00:00"
META_REVIEW_ACTOR = "Zhengqi MacBook Codex local"
AREA_ALIASES = {
    "mas-asd": "scientific-discovery",
    "hilbert": "mathematics-logic",
    "cognitive": "neuroscience-cognition",
    "computer-science-ai": "ai-ml",
    "economics-finance": "economics-game-theory",
    "neuroscience-cognitive-science": "neuroscience-cognition",
    "biology-medicine": "biology-evolution",
    "chemistry-materials": "chemistry-materials",
    "engineering-robotics": "engineering-optimization",
    "earth-environmental-science": "earth-climate",
    "social-behavioral-science": "socio-technical-systems",
    "interdisciplinary-science": "scientific-discovery",
    "law-policy": "socio-technical-systems",
}
BRACKET_RELATIONS = {
    "[bounded_by]": "bounded_by",
    "[contrasts_with]": "contrasts_with",
    "[approximates]": "approximates",
    "[equivalent_to]": "equivalent_to",
    "[consistent_with]": "consistent_with",
}


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def normalized_url(value: str) -> str:
    return value.strip().rstrip("/").casefold()


def doi_from_url(value: str) -> str:
    match = re.match(r"https://(?:dx\.)?doi\.org/(.+)$", value.strip(), flags=re.IGNORECASE)
    return match.group(1).strip().casefold() if match else ""


def title_key(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def display_area(value: str) -> str:
    return value.replace("-", " ").title().replace("Ai", "AI").replace("Ml", "ML")


def map_area(value: str) -> str:
    return AREA_ALIASES.get(value, value)


def maturity_stability(maturity: str) -> str:
    return {
        "established": "high",
        "replicated": "high",
        "supported": "medium",
        "contested": "low",
    }.get(maturity, "unknown")


def normalized_significance(value: str) -> str:
    lowered = value.casefold()
    if any(term in lowered for term in ("nobel", "turing", "godel", "landmark")):
        return "landmark"
    if any(term in lowered for term in ("consensus", "canonical", "standard", "foundational")):
        return "foundational"
    if any(term in lowered for term in ("modern", "major", "industry")):
        return "major"
    return "established"


def normalized_role(value: str) -> str:
    lowered = value.casefold()
    if any(term in lowered for term in ("proof", "theorem", "formal")):
        return "proof"
    if any(term in lowered for term in ("falsif", "contradict", "counterexample")):
        return "falsifier"
    if any(term in lowered for term in ("context", "history", "reference", "survey")):
        return "context"
    return "evidence"


def relation_type(row: dict[str, Any]) -> tuple[str, str]:
    rationale = str(row.get("rationale") or "").strip()
    for marker, value in BRACKET_RELATIONS.items():
        if rationale.startswith(marker):
            return value, rationale[len(marker) :].strip()
    return str(row["relation_type"]), rationale


def relation_id(source: str, kind: str, target: str) -> str:
    digest = hashlib.sha256(f"{source}\0{kind}\0{target}".encode()).hexdigest()[:24]
    return f"rel:v2:{digest}"


def current_rows(values: list[dict[str, Any]], identifier: str) -> dict[str, dict[str, Any]]:
    current: dict[str, dict[str, Any]] = {}
    for row in values:
        key = str(row[identifier])
        if key not in current or int(row.get("revision") or 1) > int(current[key].get("revision") or 1):
            current[key] = row
    return current


def upgrade_literature_principle(row: dict[str, Any]) -> dict[str, Any]:
    scope = dict(row.get("scope") or {})
    review_status = str(row.get("review_status") or "unassessed")
    attestation = None
    if review_status == "reviewed":
        attestation = {
            "actor": str(row.get("review_actor") or "Principia legacy review"),
            "reviewed_at": str(row.get("reviewed_at") or row.get("updated_at") or MIGRATED_AT),
            "basis": "Preserved reviewed status from the pinned Global Cloud revision.",
            "source_review_status": "reviewed",
            "trace_id": "migration:global-cloud-v1-to-v2",
        }
    provenance = dict(row.get("migration_provenance") or {})
    provenance.update(
        {
            "source_schema_version": row.get("schema_version"),
            "source_content_digest": row.get("content_digest"),
            "migration": "global-cloud-v1-to-v2",
        }
    )
    return {
        "schema_version": "global-principle-v2",
        "principle_id": row["principle_id"],
        "principle_class": "literature",
        "revision": int(row["revision"]),
        "area": map_area(str(row["area"])),
        "area_display": display_area(map_area(str(row["area"]))),
        "title": row["title"],
        "claim": row["claim"],
        "argument": row["claim"],
        "interpretation": str(scope.get("statement") or "").replace("_", " "),
        "conditions": list(scope.get("conditions") or []),
        "boundary": list(scope.get("exclusions") or []),
        "applications": list(scope.get("populations") or []),
        "falsifier": row["falsifier"],
        "kind": row["kind"],
        "epistemic_type": str(row["kind"]),
        "maturity": row["maturity"],
        "stability": maturity_stability(str(row["maturity"])),
        "validity_period": "",
        "significance": {},
        "recognition": [],
        "scope": scope,
        "quality": dict(row.get("quality") or {}),
        "tags": list(row.get("tags") or []),
        "status": row.get("status") or "active",
        "review_status": review_status,
        "review_attestation": attestation,
        "generation_trace": list(row.get("generation_trace") or []),
        "legacy_ids": list(row.get("legacy_ids") or []),
        "migration_provenance": provenance,
        "content_digest": "",
        "created_at": row.get("created_at") or MIGRATED_AT,
        "updated_at": row.get("updated_at") or MIGRATED_AT,
    }


def meta_principle(row: dict[str, Any]) -> dict[str, Any]:
    status = str(row.get("status") or "active")
    maturity = str(row.get("maturity") or "unassessed")
    if maturity == "retired":
        status = "retired"
    raw_significance = str(row.get("significance_class") or "")
    return {
        "schema_version": "global-principle-v2",
        "principle_id": row["id"],
        "principle_class": "meta",
        "revision": int(row.get("version") or 1),
        "area": row["area"],
        "area_display": row.get("area_display") or display_area(row["area"]),
        "title": row["title"],
        "claim": row["argument"],
        "argument": row["argument"],
        "interpretation": row.get("comment") or "",
        "conditions": [],
        "boundary": list(row.get("boundary") or []),
        "applications": list(row.get("applications") or []),
        "falsifier": "",
        "kind": row["principia_kind"],
        "epistemic_type": row.get("epistemic_type") or "",
        "maturity": maturity,
        "stability": {
            "contested": "low",
            "context-dependent": "unknown",
        }.get(str(row.get("stability") or "unknown"), str(row.get("stability") or "unknown")),
        "validity_period": row.get("introduced_period") or "",
        "significance": {
            "class": normalized_significance(raw_significance),
            "source_label": raw_significance,
        },
        "recognition": list(row.get("recognition") or []),
        "scope": {"linking": row.get("linking") or {}, "basics": row.get("basics") or ""},
        "quality": {"owner_reviewed_import": True},
        "tags": list(row.get("tags") or []),
        "status": status,
        "review_status": "reviewed",
        "review_attestation": {
            "actor": META_REVIEW_ACTOR,
            "reviewed_at": MIGRATED_AT,
            "basis": "Explicit owner bulk attestation for the repaired Meta-Principles v2 corpus.",
            "source_review_status": row.get("review_status") or "curated_draft",
            "trace_id": row.get("trace_id") or "migration:meta-principles-v2",
        },
        "generation_trace": [
            {
                "actor": "meta-principles-v2-migration",
                "operation": "repair_validate_and_import",
                "source_trace_id": row.get("trace_id") or "",
            }
        ],
        "legacy_ids": [],
        "migration_provenance": {
            "source_content_digest": row.get("content_digest") or "",
            "source_review_status": row.get("review_status") or "curated_draft",
            "source_epistemic_type": row.get("epistemic_type") or "",
            "source_significance_class": raw_significance,
            "source_stability": row.get("stability") or "",
            "source_basics": row.get("basics") or "",
        },
        "content_digest": "",
        "created_at": MIGRATED_AT,
        "updated_at": MIGRATED_AT,
    }


def merge_works(
    existing: list[dict[str, Any]], meta_rows: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, str], list[dict[str, Any]]]:
    output = []
    for source_row in existing:
        row = dict(source_row)
        row["schema_version"] = "global-work-v2"
        row["legacy_ids"] = list(row.get("legacy_ids") or [])
        row["identifier_observations"] = list(row.get("identifier_observations") or [])
        row["migration_provenance"] = {
            **dict(row.get("migration_provenance") or {}),
            "source_schema_version": source_row.get("schema_version"),
            "source_content_digest": source_row.get("content_digest") or "",
        }
        row["content_digest"] = ""
        output.append(row)
    latest = current_rows(output, "work_id")
    key_to_id: dict[tuple[str, str], str] = {}
    for work_id, row in latest.items():
        if row.get("doi"):
            key_to_id[("doi", str(row["doi"]).casefold())] = work_id
        for url in [row.get("landing_url") or "", *(row.get("source_urls") or [])]:
            if url:
                key_to_id[("url", normalized_url(str(url)))] = work_id
    source_to_canonical: dict[str, str] = {}
    observations: dict[str, list[dict[str, Any]]] = defaultdict(list)
    new_rows: dict[str, dict[str, Any]] = {}
    conflicts: list[dict[str, Any]] = []
    for source in sorted(meta_rows, key=lambda item: str(item["work_id"])):
        url = str(source["url"])
        doi = doi_from_url(url)
        matched = key_to_id.get(("doi", doi)) if doi else None
        matched = matched or key_to_id.get(("url", normalized_url(url)))
        if not matched:
            matched = str(source["work_id"])
            work = WorkRevisionV2(
                work_id=matched,
                revision=1,
                title=str(source["title"]),
                year=source.get("year"),
                doi=doi,
                landing_url=url,
                source_urls=[url],
                legacy_ids=[matched],
                identifier_observations=[
                    {"source_work_id": source["work_id"], "title": source["title"], "url": url}
                ],
                migration_provenance={"source": "Principia_Meta_Principles_v2"},
                content_digest="",
                created_at=MIGRATED_AT,
                updated_at=MIGRATED_AT,
            ).model_dump(mode="json")
            new_rows[matched] = work
            key_to_id[("url", normalized_url(url))] = matched
            if doi:
                key_to_id[("doi", doi)] = matched
        source_to_canonical[str(source["work_id"])] = matched
        observations[matched].append(
            {"source_work_id": source["work_id"], "title": source["title"], "url": url}
        )
    for work_id, row in new_rows.items():
        aliases = observations[work_id]
        row["legacy_ids"] = sorted({str(item["source_work_id"]) for item in aliases})
        row["identifier_observations"] = aliases
        output.append(row)
    for work_id, aliases in observations.items():
        if work_id in new_rows:
            continue
        current = latest[work_id]
        titles = {title_key(str(item["title"])) for item in aliases}
        titles.add(title_key(str(current["title"])))
        if len(titles) > 1:
            conflicts.append({"canonical_work_id": work_id, "observations": aliases})
        updated = dict(current)
        updated["revision"] = int(current["revision"]) + 1
        updated["legacy_ids"] = sorted(
            set(current.get("legacy_ids") or [])
            | {str(item["source_work_id"]) for item in aliases}
        )
        updated["identifier_observations"] = [
            *(current.get("identifier_observations") or []),
            *aliases,
        ]
        updated["source_urls"] = sorted(
            set(current.get("source_urls") or []) | {str(item["url"]) for item in aliases}
        )
        updated["migration_provenance"] = {
            **dict(current.get("migration_provenance") or {}),
            "meta_principle_evidence_merged": True,
        }
        updated["content_digest"] = ""
        updated["updated_at"] = MIGRATED_AT
        output.append(updated)
    return output, source_to_canonical, conflicts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-cloud", type=Path, required=True)
    parser.add_argument("--meta-root", type=Path, required=True)
    parser.add_argument("--output-cloud", type=Path, required=True)
    arguments = parser.parse_args()
    source = CanonicalCloudRepository(arguments.source_cloud)
    if source.schema_generation != 1:
        raise SystemExit("source Cloud must be the pinned v1 canonical dataset")
    source_validation = source.validate()
    source_records = source.all_records()
    meta_root = arguments.meta_root.resolve()
    meta_values = rows(meta_root / "data" / "meta_principles.jsonl")
    meta_works = rows(meta_root / "data" / "works.jsonl")
    meta_relations = rows(meta_root / "data" / "relations.jsonl")
    meta_gaps = rows(meta_root / "data" / "relation_coverage_gaps.jsonl")
    if (len(meta_values), len(meta_works), len(meta_relations), len(meta_gaps)) != (406, 736, 432, 30):
        raise SystemExit("Meta corpus count contract failed")

    output_root = arguments.output_cloud.resolve()
    (output_root / "data" / "v2").mkdir(parents=True, exist_ok=True)
    destination = CanonicalCloudRepository(output_root)

    work_records, work_map, conflicts = merge_works(source_records["works"], meta_works)
    literature = [upgrade_literature_principle(row) for row in source_records["principles"]]
    metas = [meta_principle(row) for row in meta_values]

    evidence_links = []
    for source_meta in meta_values:
        for evidence in source_meta.get("evidence") or []:
            evidence_links.append(
                {
                    "schema_version": "global-principle-work-v2",
                    "principle_id": source_meta["id"],
                    "principle_revision": int(source_meta.get("version") or 1),
                    "work_id": work_map[str(evidence["work_id"])],
                    "role": normalized_role(str(evidence.get("role") or "evidence")),
                    "role_detail": str(evidence.get("role") or ""),
                    "source_observations": [
                        {
                            "source_work_id": evidence["work_id"],
                            "source_title": evidence.get("title") or "",
                            "source_url": evidence.get("url") or "",
                        }
                    ],
                    "page": None,
                    "section": "",
                    "evidence_digest": "",
                }
            )
    existing_links = [
        {
            "schema_version": "global-principle-work-v2",
            **{key: value for key, value in row.items() if key != "schema_version"},
            "role_detail": "",
            "source_observations": [],
        }
        for row in source_records["principle-work"]
    ]
    meta_relation_rows = []
    for row in meta_relations:
        kind, rationale = relation_type(row)
        meta_relation_rows.append(
            {
                "schema_version": "global-relation-v2",
                "relation_id": relation_id(row["source_id"], kind, row["target_id"]),
                "revision": 1,
                "source_principle_id": row["source_id"],
                "target_principle_id": row["target_id"],
                "relation_type": kind,
                "relation_role": "peer",
                "rationale": rationale,
                "strength": None,
                "status": "proposed",
                "review_status": "unassessed",
                "review_attestation": None,
                "unresolved_target": False,
                "migration_provenance": {
                    "source_review_status": row.get("review_status") or "curated_draft",
                    "source_strength": row.get("strength"),
                },
                "content_digest": "",
                "created_at": MIGRATED_AT,
            }
        )
    existing_relations = [
        {
            "schema_version": "global-relation-v2",
            "relation_id": row["relation_id"],
            "revision": row["revision"],
            "source_principle_id": row["source_principle_id"],
            "target_principle_id": row["target_principle_id"],
            "relation_type": row["relation_type"],
            "relation_role": "peer",
            "rationale": row.get("rationale") or "",
            "strength": row.get("strength"),
            "status": row.get("status") or "active",
            "review_status": "unassessed",
            "review_attestation": None,
            "unresolved_target": bool(row.get("unresolved_target")),
            "migration_provenance": {
                **dict(row.get("migration_provenance") or {}),
                "source_content_digest": row.get("content_digest") or "",
            },
            "content_digest": "",
            "created_at": row.get("created_at") or MIGRATED_AT,
        }
        for row in source_records["relations"]
    ]
    gaps = [
        {
            "schema_version": "global-foundation-gap-v1",
            "gap_id": f"gap:meta:{index:03d}",
            "revision": 1,
            "principle_id": row["source_id"],
            "requested_target_id": row.get("requested_target_id") or "",
            "area": str(row["source_id"]).split(":", 2)[1],
            "description": row["rationale"],
            "rationale": f"Requested relation: {row['relation_type']}",
            "status": "open",
            "source_trace": {"source": "relation_coverage_gaps.jsonl"},
            "created_at": MIGRATED_AT,
            "updated_at": MIGRATED_AT,
        }
        for index, row in enumerate(meta_gaps, start=1)
    ]
    assessments = [
        {
            "schema_version": "global-foundation-assessment-v1",
            "assessment_id": f"assessment:{row['principle_id']}",
            "revision": 1,
            "principle_id": row["principle_id"],
            "principle_revision": row["revision"],
            "verdict": "ambiguous",
            "rationale": "Awaiting Meta-aware grounding review; the scientific record remains available.",
            "foundation_link_ids": [],
            "frontier_candidate": False,
            "review_status": "unassessed",
            "review_attestation": None,
            "generation_trace": [{"operation": "v2_migration_pending_grounding"}],
            "content_digest": "",
            "created_at": MIGRATED_AT,
            "updated_at": MIGRATED_AT,
        }
        for row in current_rows(literature, "principle_id").values()
    ]

    destination.write_records("works", work_records)
    destination.write_records("principles", literature)
    destination.write_records("meta-principles", metas)
    merged_links: dict[tuple[Any, ...], dict[str, Any]] = {}
    for link in [*existing_links, *evidence_links]:
        key = (
            link["principle_id"], link["principle_revision"], link["work_id"],
            link["role"], link.get("page"), link.get("section") or "",
            link.get("evidence_digest") or "",
        )
        if key not in merged_links:
            merged_links[key] = link
            continue
        current = merged_links[key]
        details = [value for value in (current.get("role_detail"), link.get("role_detail")) if value]
        current["role_detail"] = " / ".join(dict.fromkeys(details))
        observations = [*(current.get("source_observations") or []), *(link.get("source_observations") or [])]
        current["source_observations"] = list(
            {json.dumps(item, sort_keys=True): item for item in observations}.values()
        )
    destination.write_records("principle-work", merged_links.values())
    destination.write_records("relations", [*existing_relations, *meta_relation_rows])
    destination.write_records("foundation-links", [])
    destination.write_records("foundation-assessments", assessments)
    destination.write_records("foundation-gaps", gaps)
    validation = destination.validate()

    duplicate_titles: dict[str, list[str]] = defaultdict(list)
    for row in [*literature, *metas]:
        duplicate_titles[title_key(str(row["title"]))].append(str(row["principle_id"]))
    duplicate_clusters = [ids for ids in duplicate_titles.values() if len(ids) > 1]
    audit = {
        "schema_version": "principia-global-v2-local-migration-audit-v1",
        "created_at": MIGRATED_AT,
        "source_validation": source_validation,
        "output_validation": validation,
        "meta_source_counts": {
            "meta_principles": len(meta_values),
            "source_works": len(meta_works),
            "evidence_links": len(evidence_links),
            "relation_seeds": len(meta_relations),
            "foundation_gaps": len(meta_gaps),
        },
        "work_identity_conflicts": conflicts,
        "duplicate_title_clusters": duplicate_clusters,
        "publication_allowed": False,
    }
    audit_path = output_root / "audit" / "2026" / "08" / "meta-v2-local-migration.json"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_bytes(canonical_json_bytes(audit) + b"\n")
    print(json.dumps(audit["output_validation"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
