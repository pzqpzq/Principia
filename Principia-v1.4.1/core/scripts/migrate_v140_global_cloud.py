#!/usr/bin/env python3
"""Migrate verified v1.4.0 PCP packages to Global Cloud canonical v1 records."""

from __future__ import annotations

import argparse
import json
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from principia.cloud.canonical import CanonicalCloudRepository, normalize_record
from principia.domain.hashing import canonical_sha256, file_sha256
from principia.models import utc_now

EXPECTED = {"packages": 3, "works": 18, "principles": 62, "relations": 36}


def _rows(database: Path, table: str) -> list[dict[str, Any]]:
    with sqlite3.connect(database) as conn:
        values = conn.execute(f"SELECT payload_json FROM {table}").fetchall()
    return [json.loads(value[0]) for value in values]


def _principle_id(area: str, legacy_id: str) -> str:
    ulid = legacy_id.split(":")[-1]
    return f"prn:{area}:{ulid}"


def migrate(package_directory: Path, output: Path) -> dict[str, Any]:
    packages = sorted(package_directory.glob("*.pcp"))
    if len(packages) != EXPECTED["packages"]:
        raise ValueError(f"expected exactly three verified v1.4.0 packages, found {len(packages)}")
    now = utc_now()
    works: dict[str, dict[str, Any]] = {}
    principles: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    raw_relations: list[tuple[str, dict[str, Any]]] = []
    id_map: dict[str, str] = {}
    package_receipts: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="principia-v140-migration.") as temporary:
        temporary_root = Path(temporary)
        for package in packages:
            with zipfile.ZipFile(package) as archive:
                if set(archive.namelist()) != {"manifest.json", "area.sqlite", "README.txt"}:
                    raise ValueError(f"unexpected v1.4.0 package contents: {package.name}")
                manifest = json.loads(archive.read("manifest.json"))
                database = temporary_root / f"{manifest['area']}.sqlite"
                database.write_bytes(archive.read("area.sqlite"))
            if file_sha256(database) != manifest["area_sqlite_sha256"]:
                raise ValueError(f"package database digest mismatch: {package.name}")
            area = str(manifest["area"])
            package_receipts.append(
                {
                    "package": package.name,
                    "package_sha256": file_sha256(package),
                    "area_sqlite_sha256": manifest["area_sqlite_sha256"],
                    "content_digest": manifest["content_digest"],
                    "content_class": manifest["content_class"],
                }
            )
            for payload in _rows(database, "works"):
                work_id = str(payload["work_id"])
                work = {
                    "schema_version": "global-work-v1",
                    "work_id": work_id,
                    "revision": 1,
                    "title": payload["title"],
                    "abstract": "",
                    "authors": payload.get("authors") or [],
                    "affiliations": [],
                    "institutions": [],
                    "venue": payload.get("venue") or "",
                    "publication_date": "",
                    "year": payload.get("year"),
                    "doi": payload.get("doi") or "",
                    "arxiv_id": "",
                    "pmid": "",
                    "pmcid": "",
                    "openalex_id": "",
                    "semantic_scholar_id": "",
                    "landing_url": payload.get("url") or "",
                    "source_urls": [payload["url"]] if payload.get("url") else [],
                    "availability": {"status": "unknown"},
                    "citation_count": None,
                    "created_at": payload.get("created_at") or now,
                    "updated_at": payload.get("updated_at") or now,
                }
                work = normalize_record("works", work)
                previous = works.setdefault(work_id, work)
                if previous["content_digest"] != work["content_digest"]:
                    raise ValueError(f"conflicting v1.4.0 Work metadata: {work_id}")
            for payload in _rows(database, "principles"):
                legacy_id = str(payload["principle_id"])
                principle_id = _principle_id(area, legacy_id)
                id_map[legacy_id] = principle_id
                principle = {
                    "schema_version": "global-principle-v1",
                    "principle_id": principle_id,
                    "revision": 1,
                    "area": area,
                    "title": payload["title"],
                    "claim": payload["claim"],
                    "kind": payload["kind"],
                    "maturity": "unassessed",
                    "scope": {
                        "statement": payload.get("generalization_level") or "legacy v1.4.0 scope",
                        "conditions": payload.get("conditions") or [],
                        "exclusions": payload.get("boundary") or [],
                        "populations": [],
                    },
                    "falsifier": payload.get("testability") or "Requires owner assessment.",
                    "quality": {
                        "assessment_status": payload.get("assessment_status") or "unassessed",
                        "legacy_verification": payload.get("verification") or {},
                    },
                    "tags": payload.get("area_labels") or [],
                    "status": "active",
                    "review_status": "unassessed",
                    "generation_trace": [
                        {
                            "operation": "import",
                            "actor": "principia-v1.4.0-migration",
                            "source_package": package.name,
                        }
                    ],
                    "review_actor": "",
                    "reviewed_at": "",
                    "legacy_ids": [legacy_id],
                    "migration_provenance": {
                        "source_package": package.name,
                        "source_content_class": manifest["content_class"],
                        "source_content_digest": manifest["content_digest"],
                    },
                    "created_at": payload.get("created_at") or now,
                    "updated_at": payload.get("updated_at") or now,
                }
                principle["content_digest"] = canonical_sha256(principle)
                principles.append(principle)
                for reference in payload.get("references") or []:
                    links.append(
                        {
                            "schema_version": "global-principle-work-v1",
                            "principle_id": principle_id,
                            "principle_revision": 1,
                            "work_id": reference["work_id"],
                            "role": reference.get("role") or "evidence",
                            "page": reference.get("page_start"),
                            "section": reference.get("section") or "",
                            "evidence_digest": reference.get("excerpt_sha256") or "",
                        }
                    )
            raw_relations.extend((area, payload) for payload in _rows(database, "relations"))

    relations: list[dict[str, Any]] = []
    for area, payload in raw_relations:
        source = id_map.get(payload["source_principle_id"])
        target = id_map.get(payload["target_principle_id"])
        if not source:
            source = _principle_id(area, payload["source_principle_id"])
        if not target:
            target_area = payload.get("target_area") or area
            target = _principle_id(target_area, payload["target_principle_id"])
        unresolved_target = target not in set(id_map.values())
        relation = {
            "schema_version": "global-relation-v1",
            "relation_id": payload["relation_id"],
            "revision": 1,
            "source_principle_id": source,
            "target_principle_id": target,
            "relation_type": payload["relation_type"],
            "rationale": payload.get("rationale") or "",
            "strength": 1.0,
            "status": "retired" if unresolved_target else "active",
            "unresolved_target": unresolved_target,
            "migration_provenance": {
                "source_validation_state": payload.get("validation_state") or "",
                "retirement_reason": "dangling v1.4.0 relation target" if unresolved_target else "",
            },
            "created_at": now,
        }
        relation["content_digest"] = canonical_sha256(relation)
        relations.append(relation)

    counts = {
        "works": len(works),
        "principles": len(principles),
        "relations": len(relations),
    }
    if counts != {key: EXPECTED[key] for key in counts}:
        raise ValueError(f"verified migration baseline changed: {counts}")
    repository = CanonicalCloudRepository(output)
    repository.write_records("works", works.values())
    repository.write_records("principles", principles)
    repository.write_records("principle-work", links)
    repository.write_records("relations", relations)
    validation = repository.validate()
    receipt = {
        "schema_version": "principia-v140-cloud-migration-v1",
        "migrated_at": now,
        "source_packages": package_receipts,
        "expected": EXPECTED,
        "actual": {**counts, "principle_work": len(links)},
        "canonical_content_digest": validation["content_digest"],
        "review_status_preserved": "unassessed",
    }
    audit = output / "audit" / "2026" / "08" / "v140-migration.json"
    audit.parent.mkdir(parents=True, exist_ok=True)
    audit.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("package_directory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(migrate(args.package_directory.resolve(), args.output.resolve()), indent=2))


if __name__ == "__main__":
    main()
