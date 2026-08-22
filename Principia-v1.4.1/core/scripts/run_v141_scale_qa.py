#!/usr/bin/env python3
"""Build and measure the v1.4.1 20k Work / 10k Principle acceptance fixture."""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import tempfile
import time
from pathlib import Path

import numpy as np

from principia.cloud import CloudSearchRequest, GlobalCloudSnapshotStore
from principia.cloud.canonical import (
    CanonicalCloudRepository,
    build_cloud_snapshot,
    normalize_record,
)
from principia.domain.hashing import canonical_sha256


def build_fixture(root: Path) -> None:
    repository = CanonicalCloudRepository(root)
    works = []
    for index in range(20_000):
        works.append(
            normalize_record(
                "works",
                {
                    "schema_version": "global-work-v1",
                    "work_id": f"work:scale:{index:05d}",
                    "revision": 1,
                    "title": f"Scale paper {index}: topic{index % 100} mechanism",
                    "abstract": f"Synthetic public metadata for topic{index % 100} boundary mechanism.",
                    "authors": [f"Author {index % 1000}"],
                    "affiliations": [],
                    "institutions": [f"Institution {index % 50}"],
                    "venue": f"Venue {index % 25}",
                    "publication_date": f"{2000 + index % 25}-01-01",
                    "year": 2000 + index % 25,
                    "landing_url": f"https://example.org/works/{index}",
                    "source_urls": [f"https://example.org/works/{index}"],
                    "availability": {
                        "status": "available",
                        "page_count": 10 + index % 30,
                        "pdf_bytes": 1_000_000 + index,
                        "basis": "synthetic QA",
                    },
                    "created_at": "2026-08-13T00:00:00Z",
                    "updated_at": "2026-08-13T00:00:00Z",
                },
            )
        )
    principles = []
    links = []
    relations = []
    for index in range(10_000):
        principle = normalize_record(
            "principles",
            {
                "schema_version": "global-principle-v1",
                "principle_id": f"prn:scale:{index:026d}",
                "revision": 1,
                "area": "scale",
                "title": f"Scale Principle {index}",
                "claim": f"Topic{index % 100} mechanism has a testable boundary under condition {index % 20}.",
                "kind": "empirical",
                "maturity": "supported",
                "scope": {
                    "statement": "synthetic QA",
                    "conditions": [],
                    "exclusions": [],
                    "populations": [],
                },
                "falsifier": "A controlled observation outside the stated boundary.",
                "quality": {"fixture": True},
                "tags": [f"topic{index % 100}"],
                "status": "active",
                "review_status": "reviewed",
                "review_actor": "scale-fixture",
                "reviewed_at": "2026-08-13T00:00:00Z",
                "created_at": "2026-08-13T00:00:00Z",
                "updated_at": "2026-08-13T00:00:00Z",
            },
        )
        principles.append(principle)
        for work_index in (index, index + 10_000):
            links.append(
                {
                    "schema_version": "global-principle-work-v1",
                    "principle_id": principle["principle_id"],
                    "principle_revision": 1,
                    "work_id": f"work:scale:{work_index:05d}",
                    "role": "evidence",
                    "evidence_digest": canonical_sha256({"principle": index, "work": work_index}),
                }
            )
        for offset in range(1, 6):
            target = (index + offset) % 10_000
            relations.append(
                normalize_record(
                    "relations",
                    {
                        "schema_version": "global-relation-v1",
                        "relation_id": f"rel:scale:{index:05d}:{target:05d}",
                        "revision": 1,
                        "source_principle_id": principle["principle_id"],
                        "target_principle_id": f"prn:scale:{target:026d}",
                        "relation_type": "supports" if offset < 3 else "analogous_to",
                        "rationale": "Synthetic bounded-degree graph QA edge.",
                        "strength": 0.5 + offset / 20,
                        "status": "active",
                        "unresolved_target": False,
                        "created_at": "2026-08-13T00:00:00Z",
                    },
                )
            )
    repository.write_records("works", works)
    repository.write_records("principles", principles)
    repository.write_records("principle-work", links)
    repository.write_records("relations", relations)


def vectors(count: int, dimensions: int, multiplier: int) -> bytes:
    matrix = np.zeros((count, dimensions), dtype="<f2")
    matrix[np.arange(count), (np.arange(count) * multiplier) % dimensions] = 1
    return matrix.tobytes()


def percentile95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--workspace",
        type=Path,
        help="Optional persistent QA workspace; existing canonical data is reused.",
    )
    args = parser.parse_args()
    manager = (
        contextlib.nullcontext(str(args.workspace.expanduser().resolve()))
        if args.workspace
        else tempfile.TemporaryDirectory(prefix="principia-v141-scale.")
    )
    with manager as temporary:
        root = Path(temporary)
        root.mkdir(parents=True, exist_ok=True)
        canonical = root / "canonical"
        started = time.perf_counter()
        if not (canonical / "data" / "v1" / "works").is_dir():
            build_fixture(canonical)
        snapshot = root / "scale.pcg"
        manifest = build_cloud_snapshot(
            canonical,
            snapshot,
            release_id="scale-20k-10k",
            commit_sha="synthetic",
            created_at="2026-08-13T00:00:00Z",
            work_vectors=vectors(20_000, 1024, 1),
            principle_vectors=vectors(10_000, 1024, 7),
        )
        store = GlobalCloudSnapshotStore(root / "cache")
        store.install_snapshot(snapshot)
        cursor = ""
        seen = 0
        pages = 0
        while True:
            result = store.search(CloudSearchRequest(entity="paper", limit=200, cursor=cursor))
            seen += len(result["items"])
            pages += 1
            cursor = result["next_cursor"] or ""
            if not cursor:
                break
        query_vector = [0.0] * 1024
        query_vector[42] = 1.0
        request = CloudSearchRequest(entity="principle", query="topic42 mechanism", limit=50)
        store.search(request, query_vector=query_vector)
        timings = []
        for _ in range(20):
            tick = time.perf_counter()
            response = store.search(request, query_vector=query_vector)
            timings.append(time.perf_counter() - tick)
        graph_timings = []
        graph_response = {}
        for _ in range(30):
            tick = time.perf_counter()
            graph_response = store.graph_viewport(
                min_x=-10_000,
                max_x=10_000,
                min_y=-10_000,
                max_y=10_000,
                zoom=0.7,
                limit=2_500,
            )
            graph_timings.append(time.perf_counter() - tick)
        report = {
            "schema_version": "principia-v141-scale-qa-v1",
            "works": manifest.work_count,
            "principles": manifest.principle_count,
            "principle_revisions": manifest.principle_revision_count,
            "principle_work_links": manifest.principle_work_count,
            "graph_edges": manifest.relation_count,
            "pagination_items_seen": seen,
            "pagination_pages": pages,
            "snapshot_bytes": snapshot.stat().st_size,
            "snapshot_mib": round(snapshot.stat().st_size / 1024 / 1024, 3),
            "vectors_complete": manifest.vectors_complete,
            "vector_files_memory_mapped": True,
            "warm_hybrid_p95_seconds": round(percentile95(timings), 4),
            "warm_hybrid_max_seconds": round(max(timings), 4),
            "ranking_mode": response["ranking_mode"],
            "graph_tile_nodes": len(graph_response["nodes"]),
            "graph_tile_edges": len(graph_response["edges"]),
            "graph_viewport_p95_seconds": round(percentile95(graph_timings), 4),
            "graph_viewport_max_seconds": round(max(graph_timings), 4),
            "fixture_build_seconds": round(time.perf_counter() - started, 3),
            "acceptance": {
                "complete_pagination": seen == 20_000,
                "snapshot_at_most_250_mib": snapshot.stat().st_size <= 250 * 1024 * 1024,
                "warm_p95_at_most_one_second": percentile95(timings) <= 1.0,
                "graph_has_fifty_thousand_edges": manifest.relation_count == 50_000,
                "graph_viewport_p95_at_most_100ms": percentile95(graph_timings) <= 0.1,
                "graph_viewport_max_at_most_200ms": max(graph_timings) <= 0.2,
                "graph_tile_is_bounded": len(graph_response["nodes"]) <= 2_500,
            },
        }
        if not all(report["acceptance"].values()):
            raise RuntimeError(json.dumps(report, indent=2))
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
