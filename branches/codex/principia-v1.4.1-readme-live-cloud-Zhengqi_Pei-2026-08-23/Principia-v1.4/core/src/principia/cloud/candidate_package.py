from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..persistence import V14WorkspaceRepository
from ..storage import WorkspaceStorage
from .package import PackageBuildReceipt, build_candidate_pcp


@dataclass(frozen=True)
class CandidatePackageSpec:
    source_id: str
    package_id: str
    display_name: str


class CandidatePackageBuilder:
    """Publish paper-free folder collections through the verified package channel."""

    def __init__(self, storage: WorkspaceStorage, repository: V14WorkspaceRepository) -> None:
        self.storage = storage
        self.repository = repository

    @staticmethod
    def _rows(path: Path) -> list[dict[str, Any]]:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]

    def build(
        self,
        output_root: str | Path,
        *,
        specs: list[CandidatePackageSpec],
        package_version: str = "1.0.0",
    ) -> dict[str, Any]:
        root = Path(output_root).expanduser().resolve()
        packages = root / "packages"
        packages.mkdir(parents=True, exist_ok=True)
        if not specs:
            raise ValueError("at least one Candidate package specification is required")
        source_ids = [item.source_id for item in specs]
        package_ids = [item.package_id for item in specs]
        if len(source_ids) != len(set(source_ids)) or len(package_ids) != len(set(package_ids)):
            raise ValueError("source and package identifiers must be unique")

        from ..local.portable import PortablePrincipleLibrary

        snapshots: dict[str, dict[str, Any]] = {}
        principle_package: dict[str, str] = {}
        portable = PortablePrincipleLibrary(self.storage, self.repository)
        with tempfile.TemporaryDirectory(prefix="principia-candidate-catalog-") as temporary:
            temporary_root = Path(temporary)
            for spec in specs:
                snapshot_root = temporary_root / spec.package_id
                manifest = portable.export(
                    snapshot_root,
                    source_id=spec.source_id,
                    label=f"{spec.display_name} · Public literature · Unassessed",
                )
                principles = self._rows(snapshot_root / "principles.jsonl")
                if not principles:
                    raise ValueError(f"source contains no ready-to-review Principles: {spec.source_id}")
                for principle in principles:
                    identity = str(principle["principle_id"])
                    if identity in principle_package:
                        raise ValueError(f"Principle belongs to multiple release packages: {identity}")
                    principle_package[identity] = spec.package_id
                snapshots[spec.package_id] = {
                    "manifest": manifest,
                    "principles": principles,
                    "works": self._rows(snapshot_root / "works.jsonl"),
                }

        all_relations = self.repository.current_validated_relations()
        receipts: list[PackageBuildReceipt] = []
        for spec in specs:
            snapshot = snapshots[spec.package_id]
            ids = {str(item["principle_id"]) for item in snapshot["principles"]}
            relations = []
            for relation in all_relations:
                if str(relation["source_principle_id"]) not in ids:
                    continue
                target_id = str(relation["target_principle_id"])
                relations.append(
                    {
                        "relation_id": str(relation["relation_id"]),
                        "source_principle_id": str(relation["source_principle_id"]),
                        "target_principle_id": target_id,
                        "target_area": principle_package.get(target_id),
                        "relation_type": str(relation["relation_type"]),
                        "direction": str(relation["direction"]),
                        "rationale": str(relation["rationale"]),
                        "evidence_digest": str(relation["evidence_digest"]),
                        "validation_state": "validated",
                    }
                )
            package_path = packages / f"{spec.package_id}-{package_version}.pcp"
            receipt = build_candidate_pcp(
                package_path,
                package_id=spec.package_id,
                display_name=spec.display_name,
                package_version=package_version,
                principles=snapshot["principles"],
                works=snapshot["works"],
                relations=relations,
                readme=(
                    f"{spec.display_name}\n\n"
                    "Paper-free Candidate Principle package derived from public literature.\n"
                    "The Principles passed automated evidence checks but remain unassessed by humans.\n"
                    "PDFs, abstracts, quotations, normalized text, credentials, and local paths are excluded.\n"
                    "Public DOI/arXiv/HTTPS links remain available in each Principle record."
                ),
            )
            receipts.append(receipt)

        catalog = {
            "schema_version": "principia-catalog-v1",
            "label": "Principia v1.4.0 public-literature Candidate Principles",
            "content_notice": (
                "Downloaded packages are stored locally. They contain paper-free, unassessed "
                "Candidate Principles and public references, not reviewed Global Capsules."
            ),
            "areas": [
                receipt.catalog_entry(f"packages/{receipt.path.name}").model_dump(mode="json")
                for receipt in receipts
            ],
        }
        (root / "catalog.json").write_text(
            json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        build_receipt = {
            "schema_version": "principia-candidate-catalog-build-v1",
            "package_count": len(receipts),
            "principle_count": sum(item.manifest.principle_count for item in receipts),
            "work_reference_count": sum(item.manifest.work_count for item in receipts),
            "relation_count": sum(item.manifest.relation_count for item in receipts),
            "artifact_bytes": sum(item.artifact_bytes for item in receipts),
            "packages": [
                {
                    "package_id": item.manifest.area,
                    "display_name": item.manifest.display_name,
                    "artifact": f"packages/{item.path.name}",
                    "artifact_sha256": item.artifact_sha256,
                    "artifact_bytes": item.artifact_bytes,
                    "content_digest": item.manifest.content_digest,
                    "principle_count": item.manifest.principle_count,
                    "work_reference_count": item.manifest.work_count,
                    "relation_count": item.manifest.relation_count,
                    "content_class": item.manifest.content_class,
                    "source_text_included": item.manifest.source_text_included,
                }
                for item in receipts
            ],
        }
        (root / "build-receipt.json").write_text(
            json.dumps(build_receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (root / "README.md").write_text(
            "# Principia downloadable Principle packages\n\n"
            "This directory is a paper-free, local distribution channel for Principle "
            "collections. It contains immutable `.pcp` packages, the local catalog that "
            "routes them, and cryptographic build evidence.\n\n"
            "The packages contain unassessed Candidate Principles and public DOI, arXiv, "
            "or HTTPS paper links. They contain no PDFs, abstracts, quotations, normalized "
            "source text, credentials, or private filesystem paths. Downloading or installing "
            "a package stores it locally; the word Global describes its distribution channel, "
            "not a different data type and not a human-review decision. Runtime registry files "
            "are rebuildable under `.principia/` and are intentionally excluded from Git.\n\n"
            "From the adjacent Core checkout, open any private working directory against this "
            "shared package library:\n\n"
            "```bash\n"
            "principia open --working-directory /path/to/my-principia "
            "--package-library /absolute/path/to/principle-packages\n"
            "```\n\n"
            "Existing catalog packages are verified and activated automatically. The Library "
            "UI provides install, verify, pin, rollback, and Explorer controls.\n",
            encoding="utf-8",
        )
        (root / ".gitignore").write_text(
            "/.principia/\n/.DS_Store\n",
            encoding="utf-8",
        )
        return build_receipt
