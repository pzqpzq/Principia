from __future__ import annotations

from pathlib import Path

from principia.cloud import CloudSearchRequest, GlobalCloudSnapshotStore
from principia.cloud.canonical import CanonicalCloudRepository, build_cloud_snapshot

ATTESTATION = {
    "actor": "owner",
    "reviewed_at": "2026-08-21T00:00:00+00:00",
    "basis": "test review",
    "source_review_status": "curated_draft",
    "trace_id": "test",
}


def _principle(identifier: str, principle_class: str, title: str) -> dict:
    return {
        "schema_version": "global-principle-v2",
        "principle_id": identifier,
        "principle_class": principle_class,
        "revision": 1,
        "area": "foundations",
        "area_display": "Foundations",
        "title": title,
        "claim": f"{title} supplies a causal scientific foundation.",
        "argument": f"{title} supplies a causal scientific foundation.",
        "interpretation": "Use it within the stated scope.",
        "conditions": ["the evidence model is explicit"],
        "boundary": ["do not extrapolate outside the measured system"],
        "applications": ["scientific discovery"],
        "falsifier": "" if principle_class == "meta" else "A controlled test contradicts the claim.",
        "kind": "empirical",
        "epistemic_type": "scientific principle",
        "maturity": "established",
        "stability": "high",
        "validity_period": "2020-present",
        "significance": {"class": "foundational"},
        "recognition": [],
        "scope": {},
        "quality": {},
        "tags": ["causal", "foundation"],
        "status": "active",
        "review_status": "reviewed",
        "review_attestation": ATTESTATION,
        "generation_trace": [],
        "legacy_ids": [],
        "migration_provenance": {},
        "content_digest": "",
        "created_at": "2026-08-21T00:00:00+00:00",
        "updated_at": "2026-08-21T00:00:00+00:00",
    }


def test_v2_meta_search_foundations_and_viewport(tmp_path: Path) -> None:
    cloud = tmp_path / "canonical"
    (cloud / "data" / "v2").mkdir(parents=True)
    repository = CanonicalCloudRepository(cloud)
    literature_id = "prn:foundations:01ARZ3NDEKTSV4RRFFQ69G5FAV"
    meta_id = "meta:foundations:causal-identification"
    repository.write_records("works", [])
    repository.write_records("principles", [_principle(literature_id, "literature", "Causal transport")])
    repository.write_records("meta-principles", [_principle(meta_id, "meta", "Causal identification")])
    repository.write_records("principle-work", [])
    repository.write_records("relations", [])
    repository.write_records(
        "foundation-links",
        [
            {
                "link_id": "foundation:test",
                "principle_id": literature_id,
                "principle_revision": 1,
                "meta_principle_id": meta_id,
                "meta_principle_revision": 1,
                "relation_type": "specializes",
                "rationale": "The literature result specializes the identification argument.",
                "confidence": 0.9,
                "status": "active",
                "review_status": "reviewed",
                "review_attestation": ATTESTATION,
            }
        ],
    )
    repository.write_records(
        "foundation-assessments",
        [
            {
                "assessment_id": "assessment:test",
                "principle_id": literature_id,
                "principle_revision": 1,
                "verdict": "grounded",
                "rationale": "A compatible reviewed foundation exists.",
                "foundation_link_ids": ["foundation:test"],
                "review_status": "reviewed",
                "review_attestation": ATTESTATION,
            }
        ],
    )
    repository.write_records("foundation-gaps", [])
    assert repository.validate()["counts"]["meta-principles"] == 1

    snapshot = tmp_path / "cloud.pcg"
    manifest = build_cloud_snapshot(cloud, snapshot, release_id="v2-test")
    assert manifest.schema_version == "principia-global-manifest-v2"
    assert manifest.meta_principle_count == 1
    store = GlobalCloudSnapshotStore(tmp_path / "cache")
    store.install_snapshot(snapshot)

    meta = store.search(CloudSearchRequest(entity="meta_principle", query="causal foundation"))
    assert [item["id"] for item in meta["items"]] == [meta_id]
    ordinary = store.search(CloudSearchRequest(entity="principle", query="causal foundation"))
    assert all(item["principle_class"] == "literature" for item in ordinary["items"])
    detail = store.foundations(literature_id)
    assert detail and detail["assessment"]["verdict"] == "grounded"
    assert detail["foundations"][0]["meta_principle"]["principle_id"] == meta_id
    edges = store.principle_edges([literature_id, meta_id])
    assert [(edge["source_principle_id"], edge["target_principle_id"]) for edge in edges] == [
        (literature_id, meta_id)
    ]
    assert edges[0]["edge_class"] == "foundation"
    overview = store.graph_viewport(zoom=0.1)
    assert overview["lod"] == "area"
    viewport = store.graph_viewport(zoom=1.5)
    assert {node["record_kind"] for node in viewport["nodes"]} == {
        "ordinary",
        "meta_principle",
    }
