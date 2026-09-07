from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from pydantic import BaseModel

from principia import Principia
from principia.application.search import PrincipleSearchService
from principia.cloud import CloudRegistry
from principia.cloud.snapshot import _contains_concept
from principia.data_discovery import AssetInventory
from principia.data_discovery.collection_operators import (
    _one_sided_exact_monotonic_order_p,
)
from principia.data_discovery.operators import (
    _computed_anchor_units,
    _typed_nonlinear_law,
)
from principia.data_discovery.semantics import compile_study_blueprint
from principia.data_discovery.service import (
    _foundation_ids_for_text,
    _planning_principle_relevant,
)
from principia.domain import JobRecord
from principia.providers import ProviderTrace


def test_numeric_first_row_is_data_not_a_header(tmp_path: Path) -> None:
    source = tmp_path / "numeric"
    source.mkdir()
    (source / "values").write_text("1,2\n2,4\n3,9\n4,16\n", encoding="utf-8")
    inventory = AssetInventory().inventory(
        root=source, source_id="src:numeric", study_id="study:numeric"
    )
    table = next(view for view in inventory.views if view.kind == "table")
    assert table.variables[:2] == ["column_1", "column_2"]
    asset = next(item for item in inventory.assets if item.role == "raw")
    profile = dict(asset.metadata.get("profile") or {})
    assert profile.get("header_inference") == "synthetic_numeric_columns"


def test_study_blueprint_uses_bounded_multilingual_context_without_evidence_status(
    tmp_path: Path,
) -> None:
    source = tmp_path / "pecvd"
    source.mkdir()
    (source / "measurements.csv").write_text(
        "wafer_id,temperature,pressure,thickness\n"
        "w1,300,2.0,51\nw2,325,2.1,54\nw3,350,2.2,59\n",
        encoding="utf-8",
    )
    inventory = AssetInventory().inventory(
        root=source, source_id="src:pecvd", study_id="study:pecvd"
    )
    blueprint = compile_study_blueprint(
        study_id="study:pecvd",
        views=inventory.views,
        alignments=[],
        asset_profiles=[
            {
                "asset_id": "context:slides",
                "profile": {
                    "slide_text": [
                        {
                            "text": "PECVD 薄膜沉积: SHD aperture, plasma RF power, wafer thickness uniformity"
                        }
                    ]
                },
            }
        ],
    )
    assert blueprint.domain_candidates[0]["domain"] == "semiconductor_process"
    assert any(item["variable"] == "wafer_id" for item in blueprint.independent_units)
    assert blueprint.context_excerpts[0]["evidence_eligible"] is False
    assert len(blueprint.blueprint_digest) == 64
    assert set(blueprint.blueprint_digest) <= set("0123456789abcdef")


def test_nonlinear_law_requires_locked_baseline_and_negative_control() -> None:
    driver = np.linspace(1.0, 20.0, 300)
    random = np.random.default_rng(7)
    response = 2.5 * driver**1.7 * (1 + random.normal(0, 0.012, driver.size))
    law = _typed_nonlinear_law(
        driver=driver, response=response, source_digest="1" * 64
    )
    assert law is not None
    assert law["family"] == "power"
    assert law["passed"] is True
    assert law["held_out_r_squared_improvement"] >= 0.05
    assert law["negative_control_p"] <= 0.05
    assert "1.7" not in law["expression_latex"]

    null = _typed_nonlinear_law(
        driver=driver,
        response=random.normal(size=driver.size),
        source_digest="2" * 64,
    )
    assert null is None or null["passed"] is False


def test_three_trial_monotonic_gait_pattern_cannot_pass_support_gate() -> None:
    assert _one_sided_exact_monotonic_order_p(3, monotonic=True) == 1 / 6
    assert _one_sided_exact_monotonic_order_p(3, monotonic=True) > 0.05
    assert _one_sided_exact_monotonic_order_p(5, monotonic=True) <= 0.05
    assert _one_sided_exact_monotonic_order_p(8, monotonic=False) == 1.0


def test_equation_units_are_preserved_on_computed_evidence_anchors() -> None:
    assert _computed_anchor_units(
        None,
        [
            {"symbol": "x", "unit": "kHz"},
            {"symbol": "y", "unit": "dBm"},
            {"symbol": "A", "unit": ""},
        ],
    ) == {"x": "kHz", "y": "dBm"}
    assert _computed_anchor_units(
        {"frequency": "Hz"}, [{"symbol": "x", "unit": "kHz"}]
    ) == {"frequency": "Hz"}


def test_planning_knowledge_rejects_cross_domain_lexical_bridges() -> None:
    cure_context = (
        "thermoset encapsulant cure kinetics conversion activation energy "
        "vitrification diffusion rheology polymer"
    )
    assert _planning_principle_relevant(
        cure_context,
        {
            "title": "Activated rates scale with inverse temperature",
            "claim": "Polymer cure conversion follows Arrhenius kinetics until vitrification.",
        },
    )
    assert not _planning_principle_relevant(
        cure_context,
        {
            "title": "RF power changes PECVD graphene growth",
            "claim": "Plasma deposition changes film thickness on a wafer substrate.",
        },
    )
    assert not _planning_principle_relevant(
        "Rydberg radiofrequency electrometry EIT rubidium atomic response",
        {
            "title": "RF power changes PECVD film growth",
            "claim": "Plasma deposition changes film thickness on a wafer substrate.",
        },
    )
    assert _foundation_ids_for_text(cure_context)[0] == (
        "meta:chemistry-materials:arrhenius-rate"
    )


def test_data_source_set_resolves_one_canonical_project(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "values.csv").write_text("x,y\n1,2\n2,3\n3,5\n", encoding="utf-8")
    product = Principia.open(
        working_directory=tmp_path / "working", cloud_root=tmp_path / "cloud"
    )
    try:
        product.repository.register_source(
            "src:one", source, "external://one", "One dataset", "External/Test"
        )
        first = product.research_sessions.create_data_discovery_home(
            source_ids=["src:one"],
            title="Discovery one",
            provider_profile_id="siliconflow",
            model="deepseek-ai/DeepSeek-V4-Flash",
        )
        second = product.research_sessions.create_data_discovery_home(
            source_ids=["src:one"],
            title="Duplicate attempt",
            provider_profile_id="siliconflow",
            model="deepseek-ai/DeepSeek-V4-Flash",
        )
        assert first["session_id"] == second["session_id"]
        assert first["created_project"] is True
        assert second["created_project"] is False
    finally:
        product.close()


def test_same_local_root_with_new_source_id_reuses_canonical_project(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "values.csv").write_text("x,y\n1,2\n2,3\n3,5\n", encoding="utf-8")
    product = Principia.open(
        working_directory=tmp_path / "working", cloud_root=tmp_path / "cloud"
    )
    try:
        product.repository.register_source(
            "src:first-registration",
            source,
            "external://first",
            "First registration",
            "External/Test",
        )
        first = product.research_sessions.create_data_discovery_home(
            source_ids=["src:first-registration"],
            title="First registration",
            provider_profile_id="siliconflow",
            model="deepseek-ai/DeepSeek-V4-Flash",
        )

        # Reconnecting the same folder can legitimately create a new source ID.
        # Project identity must follow the canonical local root, not that UI ID.
        # Reproduce a legacy duplicate registration. The current source API
        # already reuses the first source ID, so this direct fixture represents
        # rows created by earlier versions without weakening that API guard.
        with product.repository.connect() as conn:
            conn.execute(
                """
                INSERT INTO local_sources_v14(
                    source_id, portable_uri, absolute_root, display_name, status,
                    payload_json, created_at, updated_at, source_kind, revision,
                    display_location
                )
                SELECT ?, ?, absolute_root, ?, status, payload_json, created_at,
                       updated_at, source_kind, revision, ?
                FROM local_sources_v14 WHERE source_id=?
                """,
                (
                    "src:second-registration",
                    "external://second",
                    "Second registration",
                    "External/Test",
                    "src:first-registration",
                ),
            )
        second = product.research_sessions.create_data_discovery_home(
            source_ids=["src:second-registration"],
            title="Second registration",
            provider_profile_id="siliconflow",
            model="deepseek-ai/DeepSeek-V4-Flash",
        )

        assert first["session_id"] == second["session_id"]
        assert first["created_project"] is True
        assert second["created_project"] is False
    finally:
        product.close()


def test_self_alias_cannot_break_project_restoration(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    product = Principia.open(
        working_directory=tmp_path / "working", cloud_root=tmp_path / "cloud"
    )
    try:
        product.repository.register_source(
            "src:self-alias", source, "external://self", "Self alias", "External/Test"
        )
        home = product.research_sessions.create_data_discovery_home(
            source_ids=["src:self-alias"],
            title="Self alias guard",
            provider_profile_id="siliconflow",
            model="deepseek-ai/DeepSeek-V4-Flash",
        )
        session_id = str(home["session_id"])
        with product.repository.connect() as conn:
            conn.execute(
                """
                INSERT INTO research_session_aliases(
                    alias_session_id, canonical_session_id, preferred_study_id,
                    source_set_digest, reason, created_at
                ) VALUES (?, ?, '', ?, 'legacy_self_alias', '2026-09-04T00:00:00+00:00')
                """,
                (session_id, session_id, str(home["source_set_digest"])),
            )

        restored = product.research_sessions.detail(session_id, synchronize=False)
        assert restored is not None
        assert restored["session_id"] == session_id

        product.research_sessions.consolidate_data_sessions()
        with product.repository.connect() as conn:
            self_aliases = conn.execute(
                "SELECT COUNT(*) FROM research_session_aliases "
                "WHERE alias_session_id=canonical_session_id"
            ).fetchone()[0]
        assert self_aliases == 0
    finally:
        product.close()


def test_consolidation_moves_every_legacy_study_into_canonical_run_history(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "values.csv").write_text("x,y\n1,2\n2,3\n", encoding="utf-8")
    product = Principia.open(
        working_directory=tmp_path / "working", cloud_root=tmp_path / "cloud"
    )
    try:
        product.repository.register_source(
            "src:history", source, "external://history", "History", "External/Test"
        )
        first = product.research_sessions.create_data_discovery_home(
            source_ids=["src:history"],
            title="First",
            provider_profile_id="siliconflow",
            model="deepseek-ai/DeepSeek-V4-Flash",
        )
        product.research_sessions.update_session(first["session_id"], archived=True)
        second = product.research_sessions.create_data_discovery_home(
            source_ids=["src:history"],
            title="Second",
            provider_profile_id="siliconflow",
            model="deepseek-ai/DeepSeek-V4-Flash",
        )
        product.research_sessions.update_session(first["session_id"], archived=False)

        for ordinal, session in enumerate((first, second), start=1):
            job_id = f"job:history:{ordinal}"
            study_id = f"study:history:{ordinal}"
            product.repository.save_job(
                JobRecord(
                    job_id=job_id,
                    kind="data_discovery",
                    state="succeeded",
                    stage="Synthesize",
                    progress=1,
                )
            )
            product.repository.create_data_study(
                {
                    "study_id": study_id,
                    "job_id": job_id,
                    "session_id": session["session_id"],
                    "source_ids": ["src:history"],
                    "state": "succeeded",
                    "phase": "synthesize",
                    "created_at": f"2026-08-27T00:00:0{ordinal}+00:00",
                }
            )

        receipt = product.research_sessions.consolidate_data_sessions()
        projects = [
            item
            for item in product.research_sessions.sessions()
            if item["kind"] == "data_discovery"
        ]
        assert receipt["aliases"] == 1
        assert len(projects) == 1
        runs = product.repository.data_discovery_runs(projects[0]["session_id"])
        assert {item["study_id"] for item in runs} == {
            "study:history:1",
            "study:history:2",
        }
        assert product.repository.latest_data_study_for_session(
            projects[0]["session_id"]
        )["study_id"] == "study:history:2"
        with product.repository.connect() as conn:
            self_aliases = conn.execute(
                "SELECT COUNT(*) FROM research_session_aliases "
                "WHERE alias_session_id=canonical_session_id"
            ).fetchone()[0]
        assert self_aliases == 0
    finally:
        product.close()


def test_short_ai_query_decomposes_as_scientific_concept(tmp_path: Path) -> None:
    product = Principia.open(
        working_directory=tmp_path / "working", cloud_root=tmp_path / "cloud"
    )
    try:
        search = PrincipleSearchService(
            CloudRegistry(tmp_path / "empty-cloud"), product.repository
        )
        groups = search._concept_groups("PECVD and AI")
        flattened = {term for group in groups for term in group}
        assert "pecvd" in flattened
        assert "ai" in flattened
        assert "machine-learning" in flattened
        receipt = search.search_with_plan("AI", scope="local", limit=5)
        assert receipt["query_plan"]["concept_groups"]
    finally:
        product.close()


def test_short_acronyms_match_tokens_not_substrings() -> None:
    assert _contains_concept("PECVD with AI control", "ai") is True
    assert _contains_concept("advanced materials detail", "ai") is False
    assert _contains_concept("machine-learning interatomic potential", "machine learning") is True


def test_provider_receipt_hashes_typed_values_and_retains_token_usage(tmp_path: Path) -> None:
    class TypedValue(BaseModel):
        claim: str

    product = Principia.open(
        working_directory=tmp_path / "working", cloud_root=tmp_path / "cloud"
    )
    try:
        generation = SimpleNamespace(
            value=TypedValue(claim="A schema-valid scientific interpretation"),
            trace=ProviderTrace(
                provider="siliconflow",
                model="deepseek-ai/DeepSeek-V4-Flash",
                prompt_template="test-v1",
                prompt_sha256="1" * 64,
                input_sha256="2" * 64,
                output_sha256="3" * 64,
                latency_ms=10,
                input_tokens=123,
                output_tokens=45,
                attempts=1,
                transport_attempts=1,
                repair_attempted=False,
                schema_valid=True,
            ),
        )
        receipt = product.data_discovery._provider_receipt(
            study_id="study:not-persisted",
            phase="synthesize",
            provider="siliconflow",
            model="deepseek-ai/DeepSeek-V4-Flash",
            endpoint_class="typed_reasoning",
            state="succeeded",
            started=time.monotonic(),
            prompt_template="test-v1",
            input_payload={"bounded": True},
            generation=generation,
        )
        assert len(receipt["output_sha256"]) == 64
        assert receipt["token_usage"] == {"input_tokens": 123, "output_tokens": 45}
    finally:
        product.close()
