from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from ..domain import CandidatePrinciple, PrincipleKind, PrincipleScope, WorkReference
from ..domain.hashing import canonical_sha256
from ..models import WorkItem, utc_now
from ..persistence import V14WorkspaceRepository
from ..storage import WorkspaceStorage

SCHEMA_VERSION = "principia-portable-principles-v1"
_PRIVATE_PATH = re.compile(r"^(?:[A-Za-z]:\\|/(?:Users|home|private|var|tmp)/)")
_FORBIDDEN_KEYS = {
    "absolute_path",
    "abstract",
    "private_paths",
    "quotation",
    "raw_path",
    "text_path",
    "metadata_path",
}


def _json_line(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _strict_json(body: str) -> Any:
    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in pairs:
            if key in output:
                raise ValueError(f"duplicate JSON key in portable Principle library: {key}")
            output[key] = value
        return output

    return json.loads(
        body,
        object_pairs_hook=object_pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"non-finite JSON value in portable Principle library: {value}")
        ),
    )


def _atomic_write(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _public_link(work: dict[str, Any]) -> str:
    doi = str(work.get("doi") or "").strip()
    if doi:
        return f"https://doi.org/{doi}"
    arxiv_id = str(work.get("arxiv_id") or "").strip()
    if arxiv_id:
        return f"https://arxiv.org/abs/{arxiv_id}"
    url = str(work.get("url") or "").strip()
    return url if url.startswith("https://") else ""


def _assert_public(value: Any, *, path: str = "root") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key) in _FORBIDDEN_KEYS:
                raise ValueError(
                    f"portable Principle payload contains forbidden field: {path}.{key}"
                )
            _assert_public(item, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_public(item, path=f"{path}[{index}]")
    elif isinstance(value, str) and _PRIVATE_PATH.match(value):
        raise ValueError(f"portable Principle payload contains a private path at {path}")


class PortablePrincipleLibrary:
    """Export and import path-independent, paper-free Principle showcase data."""

    def __init__(self, storage: WorkspaceStorage, repository: V14WorkspaceRepository) -> None:
        self.storage = storage
        self.repository = repository

    def export(
        self,
        output: str | Path,
        *,
        source_id: str = "",
        label: str = "Local Principles Showcase · Paper files not included",
    ) -> dict[str, Any]:
        root = Path(output).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        principle_rows: list[dict[str, Any]] = []
        work_rows: dict[str, dict[str, Any]] = {}
        eligible_ids: set[str] = set()
        for row in self.repository.principle_card_rows(source_id=source_id):
            candidate_id = str(row["candidate_id"])
            detail = self.repository.candidate_detail(candidate_id)
            if detail is None:
                continue
            metadata = dict(detail.get("local_metadata") or {})
            if metadata.get("quality_state") != "eligible":
                continue
            eligible_ids.add(candidate_id)
            argument = dict(detail.get("scientific_argument") or {})
            references: list[dict[str, Any]] = []
            for evidence in detail.get("evidence") or []:
                work_id = str(evidence.get("work_id") or "")
                work = self.repository.work_detail(work_id)
                if not work:
                    continue
                link = _public_link(work)
                work_rows.setdefault(
                    work_id,
                    {
                        "work_id": work_id,
                        "title": str(work.get("title") or work_id),
                        "authors": list(work.get("authors") or [])[:24],
                        "year": work.get("year"),
                        "venue": str(work.get("venue") or ""),
                        "doi": str(work.get("doi") or ""),
                        "url": link,
                        "created_at": str(work.get("created_at") or ""),
                        "updated_at": str(work.get("updated_at") or ""),
                    },
                )
                references.append(
                    {
                        "work_id": work_id,
                        "excerpt_sha256": str(evidence.get("excerpt_sha256") or ""),
                        "section": str(evidence.get("section") or ""),
                        "page_start": evidence.get("page_start"),
                        "role": str(evidence.get("role") or "evidence"),
                    }
                )
            evaluations = list(detail.get("quality_evaluations") or [])
            latest_evaluation = evaluations[-1] if evaluations else {}
            area_labels = [
                str(item.get("area"))
                for item in detail.get("area_suggestions") or []
                if item.get("state") in {"confirmed", "suggested"}
            ]
            if not area_labels and detail.get("area") not in {"", "uncategorized"}:
                area_labels = [str(detail["area"])]
            principle_rows.append(
                {
                    "principle_id": candidate_id,
                    "title": str(detail.get("title") or ""),
                    "claim": str(detail.get("claim") or ""),
                    "kind": str(detail.get("kind") or "empirical"),
                    "claim_class": str(argument.get("claim_class") or "empirical_association"),
                    "conditions": list(argument.get("conditions") or []),
                    "boundary": list(argument.get("boundary") or []),
                    "testability": str(
                        argument.get("testability") or detail.get("falsifier") or ""
                    ),
                    "generalization_level": str(
                        argument.get("generalization_level") or "study_bound"
                    ),
                    "area_labels": sorted(set(area_labels)),
                    "human_review_status": str(detail.get("assessment_status") or "unassessed"),
                    "references": sorted(
                        references, key=lambda item: (item["work_id"], item["excerpt_sha256"])
                    ),
                    "verification": {
                        "scientific_contract_version": str(
                            metadata.get("scientific_contract_version") or ""
                        ),
                        "quality_gate_version": str(metadata.get("quality_gate_version") or ""),
                        "evidence_digest": str(latest_evaluation.get("evidence_digest") or ""),
                        "checked_at": str(
                            latest_evaluation.get("created_at") or detail.get("updated_at") or ""
                        ),
                    },
                    "updated_at": str(detail.get("updated_at") or ""),
                    "created_at": str(detail.get("created_at") or detail.get("updated_at") or ""),
                }
            )
        relation_rows = [
            {
                "relation_id": str(row["relation_id"]),
                "source_principle_id": str(row["source_principle_id"]),
                "target_principle_id": str(row["target_principle_id"]),
                "relation_type": str(row["relation_type"]),
                "direction": str(row["direction"]),
                "provenance": "validated_showcase_receipt",
                "validation_state": "validated",
                "rationale": str(row["rationale"]),
                "source_version": int(row["source_version"]),
                "target_version": int(row["target_version"]),
                "evidence_digest": str(row["evidence_digest"]),
                "model_trace": {},
            }
            for row in self.repository.current_validated_relations()
            if row["source_principle_id"] in eligible_ids
            and row["target_principle_id"] in eligible_ids
        ]
        principle_rows.sort(key=lambda item: item["principle_id"])
        relations_sorted = sorted(relation_rows, key=lambda item: str(item["relation_id"]))
        files = {
            "principles.jsonl": principle_rows,
            "works.jsonl": [work_rows[key] for key in sorted(work_rows)],
            "relations.jsonl": relations_sorted,
        }
        digests: dict[str, str] = {}
        for name, rows in files.items():
            for row in rows:
                _assert_public(row)
            body = "".join(f"{_json_line(row)}\n" for row in rows).encode()
            _atomic_write(root / name, body)
            digests[name] = hashlib.sha256(body).hexdigest()
        logical_timestamp = (
            max(
                (str(item.get("updated_at") or "") for item in principle_rows),
                default="",
            )
            or "1970-01-01T00:00:00Z"
        )
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "label": label,
            "collection_kind": "private_folder" if source_id else "workspace",
            "principle_count": len(principle_rows),
            "work_reference_count": len(work_rows),
            "relation_count": len(relations_sorted),
            "files": digests,
            "content_digest": canonical_sha256(
                {
                    "principles": principle_rows,
                    "works": files["works.jsonl"],
                    "relations": relations_sorted,
                }
            ),
            # Derived from the data so repeated exports of an unchanged corpus are byte-identical.
            "created_at": logical_timestamp,
        }
        _assert_public(manifest)
        _atomic_write(
            root / "manifest.json",
            (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(),
        )
        return manifest

    def import_showcase(self, source: str | Path) -> dict[str, Any]:
        root = Path(source).expanduser().resolve(strict=True)
        expected_files = {"manifest.json", "principles.jsonl", "works.jsonl", "relations.jsonl"}
        if {path.name for path in root.iterdir()} != expected_files:
            raise ValueError("portable Principle library must contain exactly four data files")
        manifest = _strict_json((root / "manifest.json").read_text(encoding="utf-8"))
        _assert_public(manifest)
        if manifest.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("unsupported portable Principle library")

        def read_rows(name: str) -> list[dict[str, Any]]:
            body = (root / name).read_bytes()
            if hashlib.sha256(body).hexdigest() != manifest["files"][name]:
                raise ValueError(f"portable Principle file digest mismatch: {name}")
            rows = [_strict_json(line) for line in body.decode("utf-8").splitlines() if line]
            for row in rows:
                _assert_public(row)
            return rows

        works = {str(row["work_id"]): row for row in read_rows("works.jsonl")}
        principles = read_rows("principles.jsonl")
        relations = read_rows("relations.jsonl")
        computed_content_digest = canonical_sha256(
            {"principles": principles, "works": list(works.values()), "relations": relations}
        )
        if computed_content_digest != manifest.get("content_digest"):
            raise ValueError("portable Principle content digest mismatch")
        for row in works.values():
            self.storage.save_work(
                WorkItem(
                    id=row["work_id"],
                    title=row["title"],
                    authors=row.get("authors") or [],
                    year=row.get("year"),
                    venue=row.get("venue") or "",
                    source="public_showcase",
                    url=row.get("url") or "",
                    doi=row.get("doi") or "",
                    metadata={"showcase_reference_only": True},
                    created_at=row.get("created_at") or manifest["created_at"],
                    updated_at=row.get("updated_at") or manifest["created_at"],
                )
            )
        imported = 0
        for row in principles:
            area_labels = list(row.get("area_labels") or [])
            area = str(area_labels[0] if area_labels else "uncategorized")
            work_references = [
                WorkReference(
                    work_id=work_id,
                    title=str(works[work_id]["title"]),
                    url=str(works[work_id].get("url") or ""),
                    doi=str(works[work_id].get("doi") or ""),
                )
                for work_id in sorted(
                    {str(item["work_id"]) for item in row.get("references") or []}
                )
                if work_id in works
            ]
            candidate = CandidatePrinciple(
                candidate_id=row["principle_id"],
                area=area,
                title=row["title"],
                claim=row["claim"],
                kind=PrincipleKind(row.get("kind") or "empirical"),
                scope=PrincipleScope(
                    statement="; ".join(row.get("conditions") or []) or "See recorded conditions.",
                    conditions=row.get("conditions") or [],
                    exclusions=row.get("boundary") or [],
                ),
                falsifier=row.get("testability") or "",
                source_references=work_references,
                assessment_status="unassessed",
                raw_legacy_payload={
                    "portable_showcase_verification": row.get("verification") or {}
                },
                created_at=row.get("created_at") or row.get("updated_at") or manifest["created_at"],
                updated_at=row.get("updated_at") or utc_now(),
            )
            verification = dict(row.get("verification") or {})
            self.repository.save_candidate(
                candidate,
                source_kind="public_showcase",
                eligibility_status="eligible",
                scientific_contract_version=str(
                    verification.get("scientific_contract_version") or "scientific-principle-v2"
                ),
                quality_gate_version=str(verification.get("quality_gate_version") or "quality-v2"),
                quality_state="eligible",
                extraction_mode="showcase_import",
                context_relevance="not_evaluated",
            )
            public_argument = {
                "canonical_claim": row["claim"],
                "claim_class": row.get("claim_class") or "empirical_association",
                "conditions": row.get("conditions") or [],
                "boundary": row.get("boundary") or [],
                "testability": row.get("testability") or "",
                "generalization_level": row.get("generalization_level") or "study_bound",
                "public_showcase": True,
            }
            with self.repository.connect() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO candidate_argument_revisions(candidate_id, revision, "
                    "scientific_contract_version, generalization_level, claim_class, payload_json, "
                    "content_digest, created_at) VALUES (?, 1, ?, ?, ?, ?, ?, ?)",
                    (
                        row["principle_id"],
                        verification.get("scientific_contract_version")
                        or "scientific-principle-v2",
                        public_argument["generalization_level"],
                        public_argument["claim_class"],
                        json.dumps(public_argument, ensure_ascii=False, sort_keys=True),
                        canonical_sha256(public_argument),
                        row.get("updated_at") or utc_now(),
                    ),
                )
            for index, evidence in enumerate(row.get("references") or []):
                self.repository.save_candidate_evidence(
                    evidence_id=f"showcase:{canonical_sha256({'candidate': row['principle_id'], 'index': index})[:26]}",
                    candidate_id=row["principle_id"],
                    work_id=evidence["work_id"],
                    excerpt_sha256=evidence.get("excerpt_sha256") or "",
                    role=evidence.get("role") or "evidence",
                    locator={
                        "section": evidence.get("section") or "",
                        "page_start": evidence.get("page_start"),
                        "source_text_included": False,
                    },
                    visibility="public_reference_only",
                )
            current_detail = self.repository.candidate_detail(row["principle_id"]) or {}
            current_labels = {
                str(item.get("area"))
                for item in current_detail.get("area_suggestions") or []
                if item.get("state") == "confirmed"
            }
            for label in area_labels:
                if label not in current_labels:
                    self.repository.set_candidate_area(
                        row["principle_id"],
                        label,
                        state="confirmed",
                        provenance="portable_showcase",
                        rationale="Imported verified organizational label",
                    )
            imported += 1
        if relations:
            self.repository.replace_validated_relation_set(relations)
        return {
            "schema_version": SCHEMA_VERSION,
            "imported_principles": imported,
            "imported_work_references": len(works),
            "imported_relations": len(relations),
            "content_digest": manifest["content_digest"],
        }
