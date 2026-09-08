from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from principia import Principia
from principia.cloud import (
    CloudInstaller,
    CloudRegistry,
    PackageIntegrityError,
    build_candidate_pcp,
    build_pcp,
    verify_pcp,
)
from principia.domain import (
    GenerationTrace,
    PrincipleCapsule,
    PrincipleKind,
    PrincipleMaturity,
    PrincipleScope,
    QualityAssessment,
    TraceOperation,
    WorkReference,
    principle_id,
)


def _capsule(identity: str, version: int, claim: str) -> PrincipleCapsule:
    return PrincipleCapsule(
        principle_id=identity,
        area="demo-physics",
        version=version,
        title="Synthetic conservation principle",
        claim=claim,
        kind=PrincipleKind.EMPIRICAL,
        maturity=PrincipleMaturity.SUPPORTED,
        scope=PrincipleScope(statement="Deterministic fixture systems"),
        quality=QualityAssessment(
            grade="B",
            validity=0.8,
            reproducibility=0.8,
            evidence_strength=0.7,
            generality=0.6,
            usefulness=0.7,
            assessed_by="fixture-reviewer",
        ),
        falsifier="The fixture checksum differs under the same inputs.",
        source_references=[
            WorkReference(work_id="fixture:work:1", title="Synthetic fixture evidence")
        ],
        generation_trace=[
            GenerationTrace(
                event_id=f"evt:fixture:{version}",
                operation=TraceOperation.REVIEW,
                actor="fixture-reviewer",
                input_sha256="1" * 64,
                output_sha256="2" * 64,
            )
        ],
        tags=["fixture", "conservation"],
        source_count=1,
        relation_count=0,
        trace_count=1,
    )


def test_package_contains_exact_entries_and_immutable_revisions(tmp_path: Path) -> None:
    identity = principle_id("demo-physics")
    package = tmp_path / "demo-physics-1.0.0.pcp"
    receipt = build_pcp(
        package,
        area="demo-physics",
        display_name="Demo Physics",
        package_version="1.0.0",
        capsules=[
            _capsule(identity, 1, "Fixture claim v1"),
            _capsule(identity, 2, "Fixture claim v2"),
        ],
        readme="Synthetic acceptance data only.",
    )
    assert len(receipt.artifact_sha256) == 64
    with zipfile.ZipFile(package) as archive:
        assert set(archive.namelist()) == {"manifest.json", "area.sqlite", "README.txt"}
    verified = verify_pcp(
        package,
        expected_artifact_sha256=receipt.artifact_sha256,
        expected_artifact_bytes=receipt.artifact_bytes,
    )
    assert verified.manifest.principle_count == 1
    assert verified.manifest.revision_count == 2


def test_unassessed_candidate_package_is_installable_without_claiming_review(
    tmp_path: Path,
) -> None:
    package = tmp_path / "candidate-collection.pcp"
    receipt = build_candidate_pcp(
        package,
        package_id="mas-asd",
        display_name="MAS-ASD",
        package_version="1.0.0",
        principles=[
            {
                "principle_id": "cand:portable-package",
                "title": "Verifier diversity–selection error principle",
                "claim": "Verifier diversity reduces correlated selection errors.",
                "kind": "empirical",
                "claim_class": "empirical_association",
                "conditions": ["distinct verifier failure modes"],
                "boundary": ["evaluated inference tasks"],
                "area_labels": ["machine-intelligence", "multi-agent-systems"],
                "references": [
                    {
                        "work_id": "work:portable-package",
                        "excerpt_sha256": "a" * 64,
                        "role": "evidence",
                    },
                    {
                        "work_id": "work:portable-package",
                        "excerpt_sha256": "c" * 64,
                        "role": "evidence",
                    },
                ],
                "verification": {"evidence_digest": "b" * 64},
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        ],
        works=[
            {
                "work_id": "work:portable-package",
                "title": "Public verifier evidence",
                "url": "https://doi.org/10.0000/portable-package",
                "doi": "10.0000/portable-package",
            }
        ],
        relations=[],
        readme="Paper-free public-literature Candidate package.",
    )
    assert receipt.manifest.content_class == "unassessed_candidates"
    assert receipt.manifest.source_text_included is False
    registry = CloudRegistry(tmp_path / "cloud")
    CloudInstaller(registry).install(receipt.catalog_entry(str(package)))
    row = registry.browse()["items"][0]
    assert row["content_class"] == "unassessed_candidates"
    assert row["supporting_work_count"] == 1
    assert json.loads(row["area_labels"]) == ["machine-intelligence", "multi-agent-systems"]
    detail = registry.principle("cand:portable-package")
    assert detail is not None
    assert detail["assessment_status"] == "unassessed"
    assert detail["source_text_included"] is False
    product = Principia.open(tmp_path / "working", cloud_root=tmp_path / "cloud")
    try:
        scientific_area = product.explorer.browse(
            scope="global", area="machine-intelligence", limit=24
        )
        package_collection = product.explorer.browse(scope="global", area="mas-asd", limit=24)
        explicit_package = product.explorer.browse(
            scope="global", package_id="mas-asd", limit=24
        )
        assert scientific_area["total"] == 1
        assert package_collection["total"] == 1
        assert explicit_package["total"] == 1
        assert scientific_area["items"][0]["human_review_status"] == "pending"
        opened = product.search.principle("cand:portable-package")
        assert opened is not None
        assert len(opened["source_references"]) == 1
        assert opened["source_references"][0]["url"].startswith("https://")
    finally:
        product.close()


def test_package_rejects_unexpected_entry(tmp_path: Path) -> None:
    package = tmp_path / "unsafe.pcp"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("manifest.json", "{}")
        archive.writestr("area.sqlite", b"")
        archive.writestr("README.txt", "fixture")
        archive.writestr("../escape", "unsafe")
    with pytest.raises(PackageIntegrityError, match="exactly"):
        verify_pcp(package)


def test_install_update_pin_rollback_and_registry_rebuild(tmp_path: Path) -> None:
    identity = principle_id("demo-physics")
    first_path = tmp_path / "source-1.pcp"
    first = build_pcp(
        first_path,
        area="demo-physics",
        display_name="Demo Physics",
        package_version="1.0.0",
        capsules=[_capsule(identity, 1, "First searchable conservation claim")],
        readme="Synthetic acceptance data only.",
    )
    second_path = tmp_path / "source-2.pcp"
    second = build_pcp(
        second_path,
        area="demo-physics",
        display_name="Demo Physics",
        package_version="1.1.0",
        capsules=[
            _capsule(identity, 1, "First searchable conservation claim"),
            _capsule(identity, 2, "Updated searchable conservation claim"),
        ],
        readme="Synthetic acceptance data only.",
    )
    registry = CloudRegistry(tmp_path / "cloud")
    installer = CloudInstaller(registry)
    installer.install(first.catalog_entry(str(first_path)))
    assert registry.active_version("demo-physics") == "1.0.0"
    assert registry.search("conservation")[0]["principle_id"] == identity

    registry.pin("demo-physics", "1.0.0")
    with pytest.raises(ValueError, match="pinned"):
        installer.install(second.catalog_entry(str(second_path)))
    registry.pin("demo-physics", "1.0.0", pinned=False)
    installer.install(second.catalog_entry(str(second_path)))
    assert registry.active_version("demo-physics") == "1.1.0"
    assert registry.principle(identity)["version"] == 2

    assert installer.rollback("demo-physics") == "1.0.0"
    assert registry.active_version("demo-physics") == "1.0.0"
    assert registry.rebuild() == 1
    assert registry.search("conservation")


def test_artifact_hash_failure_preserves_active_version(tmp_path: Path) -> None:
    identity = principle_id("demo-physics")
    package = tmp_path / "source.pcp"
    receipt = build_pcp(
        package,
        area="demo-physics",
        display_name="Demo Physics",
        package_version="1.0.0",
        capsules=[_capsule(identity, 1, "Fixture claim")],
        readme="Synthetic acceptance data only.",
    )
    registry = CloudRegistry(tmp_path / "cloud")
    installer = CloudInstaller(registry)
    bad = receipt.catalog_entry(str(package)).model_copy(update={"artifact_sha256": "0" * 64})
    with pytest.raises(PackageIntegrityError, match="SHA-256"):
        installer.install(bad)
    assert registry.active_version("demo-physics") is None
    assert not list(registry.packages_dir.rglob("area.sqlite"))


def test_catalog_cache_survives_clean_runtime_reopen(tmp_path: Path) -> None:
    package = tmp_path / "source.pcp"
    receipt = build_pcp(
        package,
        area="demo-physics",
        display_name="Demo Physics",
        package_version="1.0.0",
        capsules=[_capsule(principle_id("demo-physics"), 1, "Cached catalog fixture")],
        readme="Synthetic acceptance data only.",
    )
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "schema_version": "principia-catalog-v1",
                "areas": [receipt.catalog_entry(str(package)).model_dump(mode="json")],
            }
        ),
        encoding="utf-8",
    )
    cloud_root = tmp_path / "cloud"
    first = Principia.open(tmp_path / "workspace", cloud_root=cloud_root)
    first.cloud.refresh_catalog(catalog)

    reopened = Principia.open(tmp_path / "workspace", cloud_root=cloud_root)
    assert reopened.diagnostics()["cloud"]["catalog_configured"] is True
    assert reopened.cloud.areas()[0]["area"] == "demo-physics"
    cache_state = (cloud_root / "catalog" / "state.json").read_text(encoding="utf-8")
    assert str(tmp_path) not in cache_state


def test_shared_package_library_auto_activates_downloaded_packages_across_workspaces(
    tmp_path: Path,
) -> None:
    library = tmp_path / "principle-packages"
    artifacts = library / "packages"
    artifacts.mkdir(parents=True)
    package = artifacts / "demo-physics-1.0.0.pcp"
    receipt = build_pcp(
        package,
        area="demo-physics",
        display_name="Demo Physics",
        package_version="1.0.0",
        capsules=[
            _capsule(
                principle_id("demo-physics"),
                1,
                "A shared verified Principle remains available across private workspaces.",
            )
        ],
        readme="Paper-free shared package fixture.",
    )
    entry = receipt.catalog_entry("packages/demo-physics-1.0.0.pcp")
    (library / "catalog.json").write_text(
        json.dumps(
            {
                "schema_version": "principia-catalog-v1",
                "areas": [entry.model_dump(mode="json")],
            }
        ),
        encoding="utf-8",
    )

    first = Principia.open(
        working_directory=tmp_path / "first-working-directory",
        package_library=library,
    )
    second = Principia.open(
        working_directory=tmp_path / "second-working-directory",
        package_library=library,
    )
    try:
        assert first.cloud.registry.root == library / ".principia"
        assert second.cloud.registry.root == first.cloud.registry.root
        assert first.cloud.areas()[0]["installed"] is True
        assert second.cloud.areas()[0]["installed"] is True
        assert first.cloud.areas()[0]["downloaded"] is True
        assert second.explorer.browse(scope="global", package_id="demo-physics")[
            "total"
        ] == 1
        assert not (tmp_path / "first-working-directory" / "workspace" / ".principia" / "cloud").exists()
        assert not (tmp_path / "second-working-directory" / "workspace" / ".principia" / "cloud").exists()
    finally:
        first.close()
        second.close()
def test_broad_registry_search_is_bounded_and_deterministic(tmp_path: Path) -> None:
    registry = CloudRegistry(tmp_path / "cloud")
    with registry.connect() as conn:
        conn.executemany(
            "INSERT INTO principle_index(principle_id, version, area, package_version, "
            "title, claim, kind, maturity, quality, freshness, tags) VALUES "
            "(?,1,'fixture','1.0.0',?,?,'empirical','supported',0.8,"
            "'2026-01-01T00:00:00Z','fixture')",
            (
                (
                    f"prn:fixture:{index:026d}",
                    f"Broad deterministic Principle {index}",
                    f"Shared lexical fixture observation {index}",
                )
                for index in range(2_100)
            ),
        )
        conn.executemany(
            "INSERT INTO principle_fts VALUES (?,?,?,'fixture','fixture')",
            (
                (
                    f"prn:fixture:{index:026d}",
                    f"Broad deterministic Principle {index}",
                    f"Shared lexical fixture observation {index}",
                )
                for index in range(2_100)
            ),
        )

    first = registry.search("shared lexical", limit=100)
    second = registry.search("shared lexical", limit=100)
    assert [item["principle_id"] for item in first] == [
        item["principle_id"] for item in second
    ]
    assert len(first) == 100
