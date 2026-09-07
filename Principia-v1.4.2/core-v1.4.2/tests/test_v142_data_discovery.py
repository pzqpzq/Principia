from __future__ import annotations

import gzip
import hashlib
import json
import sys
import time
import zipfile
from concurrent.futures import Future
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from principia import Principia
from principia.api import create_app
from principia.data_discovery import AssetInventory
from principia.data_discovery.adapters import AdapterRegistry
from principia.data_discovery.collection_operators import analyze_collection
from principia.data_discovery.operators import analyze_asset, benjamini_hochberg, load_numeric
from principia.data_discovery.previews import build_preview
from principia.data_discovery.sandbox import AnalysisSandbox, SandboxAudit
from principia.data_discovery.service import (
    DataDiscoveryService,
    DiscoverySynthesis,
    ExtraPrincipleProposal,
    FindingInterpretation,
    _extra_principle_duplicates_finding,
    _foundation_ids_for_finding,
    _principle_relevant_to_finding,
    _prior_art_title_relevant,
    _scientific_text_duplicate,
)
from principia.domain.data_discovery import DataFinding
from principia.models import utc_now


def _tree_receipt(root: Path) -> dict[str, tuple[int, int, str]]:
    return {
        path.relative_to(root).as_posix(): (
            path.stat().st_size,
            path.stat().st_mtime_ns,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _scenario(root: Path) -> Path:
    source = root / "scenario"
    raw = source / "raw"
    raw.mkdir(parents=True)
    (raw / "measurements.csv").write_text(
        "temperature,response,group\n"
        + "".join(f"{index},{2 * index + 3},{index % 4}\n" for index in range(1, 121)),
        encoding="utf-8",
    )
    (source / "USER_BRIEF.txt").write_text(
        "I think temperature might matter, but please check.", encoding="utf-8"
    )
    (source / "PROVENANCE.json").write_text(
        json.dumps(
            {
                "schema": "principia.local-scenario/v1",
                "files": [
                    {"path": "raw/measurements.csv", "role": "official_payload"},
                    {"path": "USER_BRIEF.txt", "role": "context"},
                ],
            }
        ),
        encoding="utf-8",
    )
    return source


def test_inventory_preserves_roles_and_user_brief_is_not_evidence(tmp_path: Path) -> None:
    source = _scenario(tmp_path)
    result = AssetInventory().inventory(
        root=source, source_id="src:test", study_id="study:test"
    )
    by_name = {
        str(item.metadata["relative_path"]): item for item in result.assets
    }
    assert by_name["raw/measurements.csv"].role == "raw"
    assert by_name["raw/measurements.csv"].metadata["evidence_eligible"] is True
    assert by_name["USER_BRIEF.txt"].role == "user_context"
    assert by_name["USER_BRIEF.txt"].metadata["evidence_eligible"] is False
    assert result.coverage["read_only"] is True


def test_unmanifested_scientific_workbooks_are_data_but_lock_and_finder_files_are_not(
    tmp_path: Path,
) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    source = tmp_path / "user-folder"
    source.mkdir()
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["temperature", "response"])
    for index in range(80):
        sheet.append([index, 2 * index + 1])
    workbook.save(source / "experiment.xlsx")
    (source / "~$experiment.xlsx").write_bytes(b"office lock")
    (source / ".DS_Store").write_bytes(b"finder metadata")

    result = AssetInventory().inventory(
        root=source, source_id="src:user-folder", study_id="study:user-folder"
    )
    by_name = {str(item.metadata["relative_path"]): item for item in result.assets}
    assert by_name["experiment.xlsx"].role == "raw"
    assert by_name["experiment.xlsx"].status == "analyzable"
    assert by_name["~$experiment.xlsx"].role == "metadata"
    assert by_name["~$experiment.xlsx"].status == "metadata_only"
    assert by_name[".DS_Store"].role == "metadata"
    assert by_name[".DS_Store"].status == "metadata_only"


def test_extra_principles_require_real_literature_and_surviving_finding_links() -> None:
    synthesis = DiscoverySynthesis(
        principle_gap_detected=True,
        principle_gap_reason="The established cards do not explain the regime boundary.",
        extra_principles=[
            ExtraPrincipleProposal(
                title="Boundary-limited transport coupling",
                claim="Transport and reaction observables couple only inside a bounded process regime.",
                explanatory_gap="Existing cards omit the observed process boundary.",
                mechanism="A rate-limiting interface changes across the recipe boundary.",
                boundary_conditions=["fixed chamber geometry"],
                falsifiers=["the coupling remains invariant after recipe crossover"],
                supporting_source_keys=["doi:10.1000/example"],
                related_finding_ids=["finding:kept"],
            ),
            ExtraPrincipleProposal(
                title="Unsupported invention",
                claim="This must not be retained.",
                explanatory_gap="No supported explanatory gap is actually documented here.",
                mechanism="No literature-grounded mechanism is available for this proposal.",
                boundary_conditions=[],
                falsifiers=["any"],
                supporting_source_keys=["made-up-source"],
                related_finding_ids=["finding:kept"],
            ),
            ExtraPrincipleProposal(
                title="Measured boundary response",
                claim="The observed response changes across a calibrated process boundary.",
                explanatory_gap="This proposal only relabels the retained finding and closes no new explanatory gap.",
                mechanism="The measured boundary response changes across the calibrated process boundary.",
                boundary_conditions=["the supplied calibration"],
                falsifiers=["the measured response does not change"],
                supporting_source_keys=["doi:10.1000/duplicate"],
                related_finding_ids=["finding:kept"],
            ),
        ],
    )
    retained = DataDiscoveryService._materialize_extra_principles(
        study_id="study:extra",
        synthesis=synthesis,
        literature_sources={
            "doi:10.1000/example": {
                "source_key": "doi:10.1000/example",
                "title": "Boundary-limited transport and reaction coupling across process regimes",
                "doi": "10.1000/example",
            },
            "doi:10.1000/duplicate": {
                "source_key": "doi:10.1000/duplicate",
                "title": "Measured boundary response across a calibrated process boundary",
                "doi": "10.1000/duplicate",
            },
        },
        findings=[
            SimpleNamespace(
                finding_id="finding:kept",
                title="Measured boundary response",
                claim="The observed response changes across a calibrated process boundary.",
            )
        ],
    )
    assert len(retained) == 1
    assert retained[0].record_kind == "extra_principle"
    assert retained[0].status == "provisional_research_synthesis"
    assert retained[0].supporting_sources[0]["doi"] == "10.1000/example"


def test_extra_principle_paraphrase_does_not_duplicate_a_tess_finding() -> None:
    extra_claim = (
        "In single-sector TESS light curves, a periodogram peak with false-alarm "
        "probability below 10^-4 is not sufficient evidence for a persistent period; "
        "candidates must reproduce the same harmonic period in two contiguous halves, "
        "otherwise they should be treated as aliases or non-stationary artifacts."
    )
    finding_statement = (
        "In single-sector TESS light curves, a periodogram peak with false-alarm "
        "probability below 10^-4 is not sufficient evidence for a persistent period; "
        "a candidate must reproduce the same harmonic period in two contiguous halves, "
        "otherwise it should be treated as an alias or non-stationary artifact."
    )
    assert _scientific_text_duplicate(extra_claim, finding_statement)
    assert _extra_principle_duplicates_finding(
        extra_claim,
        SimpleNamespace(
            claim="Three of eight targets retained a coherent period.",
            principle_statement=finding_statement,
            mechanism="",
        ),
    )


def test_archive_traversal_is_blocked_without_extracting(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("../escape.csv", "a,b\n1,2\n")
    inspection = AdapterRegistry().inspect(archive)
    assert inspection.status == "blocked"
    assert any("traversal" in warning for warning in inspection.warnings)
    assert not (tmp_path.parent / "escape.csv").exists()


def test_operator_is_exploratory_and_multiple_testing_is_deterministic(
    tmp_path: Path,
) -> None:
    source = _scenario(tmp_path)
    inventory = AssetInventory().inventory(
        root=source, source_id="src:test", study_id="study:test"
    )
    asset = next(item for item in inventory.assets if item.role == "raw")
    outcome = analyze_asset(study_id="study:test", asset=asset, root=source)
    assert outcome is not None
    assert outcome.plan.operator == "mechanistic_response_curve"
    assert outcome.finding.status == "supported_candidate"
    assert outcome.finding.validation_level == "exploratory"
    assert outcome.result.sensitivities
    assert benjamini_hochberg([0.01, 0.04, None, 0.03]) == [0.03, 0.04, None, 0.04]


def test_hypothesis_guidance_cannot_displace_deterministic_asset_backbone() -> None:
    assets = [
        SimpleNamespace(asset_id=f"asset:{index}", byte_size=index + 1)
        for index in range(8)
    ]
    ordered = DataDiscoveryService._balanced_asset_order(
        assets,
        {"asset:7": 0, "asset:6": 1},
    )
    assert [item.asset_id for item in ordered] == [
        "asset:0",
        "asset:1",
        "asset:2",
        "asset:7",
        "asset:3",
        "asset:4",
        "asset:5",
        "asset:6",
    ]
    assert DataDiscoveryService._balanced_asset_order(assets, {}) == assets


def test_fits_light_curve_uses_periodicity_not_time_flux_or_pixel_order(
    tmp_path: Path,
) -> None:
    numpy = pytest.importorskip("numpy")
    fits = pytest.importorskip("astropy.io.fits")
    pillow = pytest.importorskip("PIL.Image")
    source = tmp_path / "astronomy"
    source.mkdir()
    time_values = numpy.linspace(0.0, 32.0, 4_096)
    period_days = 4.25
    flux_values = 1.0 + 0.025 * numpy.sin(2 * numpy.pi * time_values / period_days)
    primary = fits.PrimaryHDU()
    primary.header["TICID"] = 123456789
    primary.header["SECTOR"] = 96
    primary.header["TESSMAG"] = 12.4
    table = fits.BinTableHDU.from_columns(
        [
            fits.Column(name="TIME", format="D", unit="d", array=time_values),
            fits.Column(name="FLUX", format="E", array=flux_values),
        ],
        name="LIGHTCURVE",
    )
    table.header["PER1"] = period_days
    table.header["POW1"] = 0.9
    fits.HDUList([primary, table]).writeto(source / "lightcurve.fits")
    pillow.new("L", (32, 32), color=128).save(source / "preview.png")

    inventory = AssetInventory().inventory(
        root=source, source_id="src:astronomy", study_id="study:astronomy"
    )
    by_format = {item.format: item for item in inventory.assets}
    outcome = analyze_asset(
        study_id="study:astronomy", asset=by_format["fits"], root=source
    )
    assert outcome is not None
    assert outcome.plan.operator == "light_curve_periodicity"
    assert outcome.finding.status == "supported_candidate"
    assert outcome.finding.validation_level == "exploratory"
    assert "rotation-like" in outcome.finding.title
    assert "TIME and FLUX had Pearson" not in outcome.finding.claim
    assert outcome.result.estimate["period_days"] == pytest.approx(period_days, rel=0.02)
    assert analyze_asset(
        study_id="study:astronomy", asset=by_format["png"], root=source
    ) is None


def test_domain_operators_replace_row_order_with_signal_spatial_and_diffraction_tests(
    tmp_path: Path,
) -> None:
    numpy = pytest.importorskip("numpy")
    h5py = pytest.importorskip("h5py")
    xarray = pytest.importorskip("xarray")
    source = tmp_path / "scientific-formats"
    source.mkdir()

    sample_rate = 128.0
    time_values = numpy.arange(8_192) / sample_rate
    with h5py.File(source / "detector.hdf5", "w") as handle:
        signal = handle.create_dataset(
            "strain/Strain",
            data=numpy.sin(2 * numpy.pi * 12.0 * time_values)
            + 0.05 * numpy.sin(2 * numpy.pi * 3.0 * time_values),
        )
        signal.attrs["Xspacing"] = 1.0 / sample_rate

    coordinates = numpy.linspace(-2.5, 2.5, 64)
    xx, yy = numpy.meshgrid(coordinates, coordinates)
    field = numpy.exp(-((xx - 0.7) ** 2 + (yy + 0.4) ** 2) / 0.6)
    xarray.Dataset(
        {"sea_surface_temperature_anomaly": (("lat", "lon"), field)}
    ).to_netcdf(source / "anomaly.nc")

    angles = numpy.linspace(20.0, 60.0, 1_200)
    intensity = 30.0 + 900.0 * numpy.exp(-0.5 * ((angles - 36.25) / 0.22) ** 2)
    (source / "scan.ras").write_text(
        "\n".join(f"{angle:.8f} {value:.8f}" for angle, value in zip(angles, intensity, strict=True)),
        encoding="utf-8",
    )

    inventory = AssetInventory().inventory(
        root=source, source_id="src:formats", study_id="study:formats"
    )
    by_format = {item.format: item for item in inventory.assets}
    outcomes = {
        name: analyze_asset(study_id="study:formats", asset=by_format[name], root=source)
        for name in ("hdf5", "netcdf", "ras")
    }
    assert outcomes["hdf5"] is not None
    assert outcomes["hdf5"].plan.operator == "ordered_signal_spectrum"
    assert outcomes["hdf5"].result.estimate["peak_frequency_hz"] == pytest.approx(12.0, rel=0.02)
    assert r"\arg\max" in outcomes["hdf5"].result.expression_latex
    assert outcomes["hdf5"].result.split_validation["rule_gate"]["negative_control"] is False
    assert outcomes["netcdf"] is not None
    assert outcomes["netcdf"].plan.operator == "spatial_field_coherence"
    assert outcomes["netcdf"].result.estimate["largest_upper_tail_component_cells"] >= 8
    assert r"\rho_{\mathrm{NN}}" in outcomes["netcdf"].result.expression_latex
    assert outcomes["netcdf"].result.split_validation["rule_gate"]["transfer_boundary_declared"] is True
    assert outcomes["netcdf"].result.split_validation["negative_control"]["passed"] is True
    assert outcomes["netcdf"].result.uncertainty["mask_preserving_permutation_p"] <= 0.05
    assert outcomes["netcdf"].result.uncertainty["permutation_replicates"] == 19
    assert outcomes["ras"] is not None
    assert outcomes["ras"].plan.operator == "diffraction_peak_profile"
    assert outcomes["ras"].result.estimate["peak_angle"] == pytest.approx(36.25, abs=0.05)
    assert all(
        outcome.finding.status == "supported_candidate"
        for outcome in outcomes.values()
        if outcome is not None
    )


def test_ordered_signal_does_not_call_shifted_half_peaks_persistent(
    tmp_path: Path,
) -> None:
    numpy = pytest.importorskip("numpy")
    h5py = pytest.importorskip("h5py")
    source = tmp_path / "shifted-signal"
    source.mkdir()
    sample_rate = 128.0
    half_size = 16_384
    half_time = numpy.arange(half_size) / sample_rate
    shifted = numpy.concatenate(
        [
            numpy.sin(2 * numpy.pi * 5.0 * half_time),
            numpy.sin(2 * numpy.pi * 5.3125 * half_time),
        ]
    )
    with h5py.File(source / "shifted.hdf5", "w") as handle:
        signal = handle.create_dataset("strain/Strain", data=shifted)
        signal.attrs["Xspacing"] = 1.0 / sample_rate
    inventory = AssetInventory().inventory(
        root=source, source_id="src:shifted", study_id="study:shifted"
    )
    outcome = analyze_asset(
        study_id="study:shifted",
        asset=next(item for item in inventory.assets if item.format == "hdf5"),
        root=source,
    )
    assert outcome is not None
    assert outcome.plan.operator == "ordered_signal_spectrum"
    assert outcome.finding.status == "held_back"
    assert outcome.plan.parameters["contiguous_half_tolerance_hz"] < 0.1
    assert any("not stable" in item for item in outcome.result.negative_evidence)


def test_identifier_and_record_order_patterns_do_not_become_scientific_tests(
    tmp_path: Path,
) -> None:
    source = tmp_path / "identifier-only"
    source.mkdir()
    (source / "records.csv").write_text(
        "record_id,sequence_number\n"
        + "".join(f"{10_000 + index},{index}\n" for index in range(100)),
        encoding="utf-8",
    )
    (source / "PROVENANCE.json").write_text(
        json.dumps(
            {
                "schema": "principia.local-scenario/v1",
                "files": [{"path": "records.csv", "role": "official_payload"}],
            }
        ),
        encoding="utf-8",
    )
    product = Principia.open(
        working_directory=tmp_path / "identifier-working",
        cloud_root=tmp_path / "identifier-cloud",
    )
    try:
        product.repository.register_source(
            "src:identifiers", source, "external://identifiers", "Identifiers", "External/Test"
        )
        study = product.data_discovery.create(
            source_ids=["src:identifiers"],
            provider="",
            budget="fast",
            egress_confirmed=False,
            defer=False,
        )
        assert product.data_discovery.findings(study["study_id"]) == []
        assert study["coverage"]["executed_test_count"] == 0
        assert study["coverage"]["screened_test_count"] == 0
        tests = json.loads(
            (product.workspace.outputs_dir / study["study_id"] / "tests.json").read_text(
                encoding="utf-8"
            )
        )
        assert tests["items"] == []
    finally:
        product.close()


def test_challenge_preserves_a_screened_candidate_as_an_inspectable_finding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _scenario(tmp_path)
    inventory = AssetInventory().inventory(
        root=source, source_id="src:screened", study_id="study:screened"
    )
    outcome = analyze_asset(
        study_id="study:screened",
        asset=next(item for item in inventory.assets if item.role == "raw"),
        root=source,
    )
    assert outcome is not None and outcome.finding.status == "supported_candidate"
    outcome = replace(
        outcome,
        result=outcome.result.model_copy(
            update={"uncertainty": {"p_value_uncorrected": 0.8}}
        ),
    )
    product = Principia.open(
        working_directory=tmp_path / "screened-working",
        cloud_root=tmp_path / "screened-cloud",
    )
    try:
        monkeypatch.setattr(product.repository, "save_data_test", lambda _payload: None)
        survivors, screened = product.data_discovery._challenge([outcome])
        assert survivors == []
        assert len(screened) == 1
        assert screened[0].status == "held_back"
        assert screened[0].insight_level == "observational"
        assert screened[0].test_ids == [outcome.result.test_id]
        assert any("Benjamini-Hochberg" in item for item in screened[0].negative_evidence)
        assert screened[0].promotion_eligible is False
    finally:
        product.close()


def test_challenge_holds_back_supported_candidate_without_uncertainty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _scenario(tmp_path)
    inventory = AssetInventory().inventory(
        root=source, source_id="src:no-uncertainty", study_id="study:no-uncertainty"
    )
    outcome = analyze_asset(
        study_id="study:no-uncertainty",
        asset=next(item for item in inventory.assets if item.role == "raw"),
        root=source,
    )
    assert outcome is not None and outcome.finding.status == "supported_candidate"
    outcome = replace(
        outcome,
        result=outcome.result.model_copy(update={"uncertainty": {}}),
    )
    product = Principia.open(
        working_directory=tmp_path / "no-uncertainty-working",
        cloud_root=tmp_path / "no-uncertainty-cloud",
    )
    try:
        monkeypatch.setattr(product.repository, "save_data_test", lambda _payload: None)
        survivors, screened = product.data_discovery._challenge([outcome])
        assert survivors == []
        assert len(screened) == 1
        assert screened[0].status == "held_back"
        assert screened[0].promotion_eligible is False
        assert any(
            "uncertainty receipt" in item for item in screened[0].negative_evidence
        )
    finally:
        product.close()


def test_repeated_source_runs_keep_views_and_tests_scoped_to_each_project(
    tmp_path: Path,
) -> None:
    source = _scenario(tmp_path)
    product = Principia.open(
        working_directory=tmp_path / "rerun-working",
        cloud_root=tmp_path / "rerun-cloud",
    )
    try:
        product.repository.register_source(
            "src:rerun", source, "external://rerun", "Rerun", "External/Test"
        )
        first = product.data_discovery.create(
            source_ids=["src:rerun"],
            provider="",
            budget="fast",
            egress_confirmed=False,
            defer=False,
        )
        first_study_id = first["study_id"]
        first_view_ids = {
            item.view_id for item in product.repository.data_views(first_study_id)
        }
        first_test_ids = {
            str(item["test_id"])
            for item in product.repository.data_tests(first_study_id)
        }
        first_finding = next(
            item
            for item in product.repository.data_findings(first_study_id)
            if item.test_ids
        )
        assert first_view_ids
        assert first_test_ids

        second = product.data_discovery.create(
            source_ids=["src:rerun"],
            provider="",
            budget="fast",
            egress_confirmed=False,
            defer=False,
        )
        second_study_id = second["study_id"]
        second_view_ids = {
            item.view_id for item in product.repository.data_views(second_study_id)
        }
        second_test_ids = {
            str(item["test_id"])
            for item in product.repository.data_tests(second_study_id)
        }

        assert {item.view_id for item in product.repository.data_views(first_study_id)} == first_view_ids
        assert {
            str(item["test_id"])
            for item in product.repository.data_tests(first_study_id)
        } == first_test_ids
        assert second_view_ids
        assert second_test_ids
        assert first_view_ids.isdisjoint(second_view_ids)
        assert first_test_ids.isdisjoint(second_test_ids)

        # Compatibility for workspaces created before test IDs became
        # study-scoped: the immutable export keeps the earlier project usable.
        with product.repository.connect() as connection:
            connection.execute(
                "UPDATE data_tests SET study_id=? WHERE study_id=?",
                (second_study_id, first_study_id),
            )
        assert {
            str(item["test_id"])
            for item in product.repository.data_tests(first_study_id)
        } == first_test_ids
        reopened_finding = product.repository.data_finding(
            first_study_id, first_finding.finding_id
        )
        assert reopened_finding is not None
        assert {
            str(item["test_id"])
            for item in reopened_finding["tests"]
        } == set(first_finding.test_ids)
    finally:
        product.close()


def test_cancelling_a_queued_discovery_is_immediate(tmp_path: Path) -> None:
    source = _scenario(tmp_path)
    product = Principia.open(
        working_directory=tmp_path / "cancel-working",
        cloud_root=tmp_path / "cancel-cloud",
    )
    original_executor = product.data_discovery._executor

    class DeferredExecutor:
        def submit(self, *_args: object, **_kwargs: object) -> Future[object]:
            return Future()

    try:
        product.repository.register_source(
            "src:cancel", source, "external://cancel", "Cancel", "External/Test"
        )
        product.data_discovery._executor = DeferredExecutor()  # type: ignore[assignment]
        study = product.data_discovery.create(
            source_ids=["src:cancel"], provider="", egress_confirmed=False, defer=True
        )
        cancelled = product.data_discovery.cancel(study["study_id"])
        assert cancelled["state"] == "cancelled"
        assert cancelled["job"]["state"] == "cancelled"
        assert cancelled["execution"]["queue_position"] == 0
        assert "no analysis started" in cancelled["job"]["status_message"]
    finally:
        product.data_discovery._executor = original_executor
        product.close()


def test_public_use_sentinels_are_masked_and_large_zip_members_stream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "public-use"
    source.mkdir()
    rows = ["age,income,response"]
    rows.extend(
        f"{20 + index % 50},{-9 if index < 8 else 30000 + index * 10},{2 * index + 1}"
        for index in range(120)
    )
    with zipfile.ZipFile(source / "survey.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("official_public_use.csv", "\n".join(rows) + "\n")
    inventory = AssetInventory().inventory(
        root=source, source_id="src:public-use", study_id="study:public-use"
    )
    asset = next(item for item in inventory.assets if item.format == "zip")
    # Prove the archive path is governed by the safe member/row bounds, not by
    # the much smaller whole-text-file threshold.
    import principia.data_discovery.operators as operators

    monkeypatch.setattr(operators, "MAX_TEXT_BYTES", 32)
    loaded = load_numeric(asset, source)
    assert loaded is not None
    assert loaded.values.shape[0] == 120
    assert loaded.locator["archive_member"] == "official_public_use.csv"
    assert loaded.locator["masked_public_use_sentinels"]["income"] == [-9.0]
    assert int((loaded.values[:, loaded.variables.index("income")] != loaded.values[:, loaded.variables.index("income")]).sum()) == 8


def test_rule_projection_rejects_a_test_linked_to_another_finding(
    tmp_path: Path,
) -> None:
    source = _scenario(tmp_path)
    inventory = AssetInventory().inventory(
        root=source, source_id="src:lineage", study_id="study:lineage"
    )
    outcome = analyze_asset(
        study_id="study:lineage",
        asset=next(item for item in inventory.assets if item.role == "raw"),
        root=source,
    )
    assert outcome is not None
    payload = outcome.result.model_dump(mode="json")
    payload["analysis_plan"] = outcome.plan.model_dump(mode="json")
    payload["finding_id"] = "finding:another"
    assert DataDiscoveryService._rule_from_test(outcome.finding, payload) is None


def test_generated_scientific_null_cannot_strengthen_a_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _scenario(tmp_path)
    product = Principia.open(
        working_directory=tmp_path / "generated-working",
        cloud_root=tmp_path / "generated-cloud",
    )
    try:
        product.repository.register_source(
            "src:generated", source, "external://generated", "Generated challenge", "External/Test"
        )
        study = product.data_discovery.create(
            source_ids=["src:generated"],
            provider="",
            budget="fast",
            egress_confirmed=False,
            defer=False,
        )
        study_id = study["study_id"]
        asset = next(
            item
            for item in product.repository.data_assets(study_id=study_id, limit=50)["items"]
            if item["role"] == "raw"
        )
        from principia.domain import DataAsset

        outcome = analyze_asset(
            study_id=study_id,
            asset=DataAsset.model_validate(asset),
            root=source,
        )
        assert outcome is not None
        finding = next(item for item in product.repository.data_findings(study_id)
                       if item.finding_id == outcome.finding.finding_id)
        table_id = f"table:{asset['asset_id'].split(':')[-1]}"

        class FakeProvider:
            calls = 0

            def generate_typed(self, **_kwargs: object) -> SimpleNamespace:
                self.calls += 1
                target_finding_ids = (
                    ["finding:semantic-placeholder"]
                    if self.calls == 1
                    else [finding.finding_id]
                )
                target_test_ids = (
                    ["test:semantic-placeholder"]
                    if self.calls == 1
                    else [outcome.result.test_id]
                )
                return SimpleNamespace(
                    value={
                        "scientific_intent": "Test whether the held-out direction remains stable.",
                        "target_finding_ids": target_finding_ids,
                        "target_test_ids": target_test_ids,
                        "required_table_ids": [table_id],
                        "stability_check": "Both predeclared splits retain the fitted direction.",
                        "code": "RESULT = {'schema_version': 'principia.generated-analysis-result/v1'}",
                        "expected_output": "A stability-gated result or an explicit null.",
                    },
                    trace=SimpleNamespace(model_dump=lambda **_kwargs: {}),
                )

        null_result = {
            "schema_version": "principia.generated-analysis-result/v1",
            "target_finding_ids": [finding.finding_id],
            "target_test_ids": [outcome.result.test_id],
            "stability_check_passed": True,
            "diagnostics": ["direction changed in the second split"],
            "finding": {
                "claim": "A malformed generated result must not crash the study.",
                "effect_size": 0.3,
                "independent_unit_count": 20,
                "uncertainty": "not a structured uncertainty receipt",
                "sensitivities": [],
                "falsifier": "A future split reverses the direction.",
            },
        }
        audit = SandboxAudit(
            available=True,
            isolated=True,
            fallback_required=False,
            code_digest="a" * 64,
            ast_digest="b" * 64,
            violations=(),
        )
        monkeypatch.setattr(
            AnalysisSandbox,
            "run",
            lambda self, **kwargs: (null_result, audit),
        )
        updated, receipt, warning = product.data_discovery._run_generated_challenge(
            study_id=study_id,
            provider=FakeProvider(),  # type: ignore[arg-type]
            findings=[finding],
            outcomes=[outcome],
        )
        assert receipt["state"] == "scientific_null"
        assert receipt["lineage_repair"]["attempted"] is True
        assert receipt["lineage_repair"]["final_errors"] == []
        assert updated[0].robustness == finding.robustness
        assert "without strengthening" in warning
    finally:
        product.close()


def test_reasoning_review_can_only_demote_a_supported_candidate(tmp_path: Path) -> None:
    source = _scenario(tmp_path)
    inventory = AssetInventory().inventory(
        root=source, source_id="src:demote", study_id="study:demote"
    )
    outcome = analyze_asset(
        study_id="study:demote",
        asset=next(item for item in inventory.assets if item.role == "raw"),
        root=source,
    )
    assert outcome is not None and outcome.finding.status == "supported_candidate"
    interpretation = FindingInterpretation(
        finding_id=outcome.finding.finding_id,
        interpretation="The split evidence conflicts with the proposed stable relationship.",
        mechanism="No domain mechanism can be defended from the supplied diagnostics.",
        recommended_disposition="hold_back",
        hold_back_reason="A predeclared sensitivity reverses the effect direction.",
    )
    product = Principia.open(
        working_directory=tmp_path / "demote-working",
        cloud_root=tmp_path / "demote-cloud",
    )
    try:
        retained, holdbacks = product.data_discovery._apply_reasoning_interpretations(
            findings=[outcome.finding],
            interpretations={outcome.finding.finding_id: interpretation},
            allowed_principles=set(),
        )
        assert retained == []
        assert holdbacks == [
            {
                "finding_id": outcome.finding.finding_id,
                "reason": "A predeclared sensitivity reverses the effect direction.",
            }
        ]
    finally:
        product.close()


def test_template_similarity_compares_offset_shingles_without_crashing(
    tmp_path: Path,
) -> None:
    source = _scenario(tmp_path)
    inventory = AssetInventory().inventory(
        root=source, source_id="src:similarity", study_id="study:similarity"
    )
    outcome = analyze_asset(
        study_id="study:similarity",
        asset=next(item for item in inventory.assets if item.role == "raw"),
        root=source,
    )
    assert outcome is not None
    near_duplicate = outcome.finding.model_copy(
        update={
            "finding_id": "finding:near-duplicate",
            "title": outcome.finding.title.replace("temperature", "pressure"),
        }
    )
    score = DataDiscoveryService._template_similarity(
        outcome.finding, near_duplicate
    )
    assert 0.0 <= score <= 1.0


def test_official_nonstandard_tables_and_oeis_gzip_remain_executable(
    tmp_path: Path,
) -> None:
    source = tmp_path / "bulk"
    source.mkdir()
    bls = source / "ce.data.00a.TotalNonfarm.Employment"
    bls.write_text(
        "series_id\tyear\tperiod\tvalue\n"
        + "".join(
            f"CES0000000001\t{2020 + index // 12}\tM{index % 12 + 1:02d}\t{100 + index}\n"
            for index in range(36)
        ),
        encoding="utf-8",
    )
    oeis = source / "stripped.gz"
    with gzip.open(oeis, "wt", encoding="utf-8") as stream:
        stream.write("# Official sequence rows\n")
        for index in range(1, 20):
            stream.write(
                f"A{index:06d} ,"
                + ",".join(
                    str(index * (10 ** (200 + value)))
                    for value in range(1, 15)
                )
                + ",\n"
            )
    inventory = AssetInventory().inventory(
        root=source, source_id="src:bulk", study_id="study:bulk"
    )
    by_name = {Path(str(item.metadata["relative_path"])).name: item for item in inventory.assets}
    assert by_name[bls.name].format == "delimited"
    assert analyze_asset(
        study_id="study:bulk", asset=by_name[bls.name], root=source
    ) is not None
    assert analyze_asset(
        study_id="study:bulk", asset=by_name[oeis.name], root=source
    ) is not None


def test_collection_operator_uses_holdout_and_keeps_each_input_anchor(
    tmp_path: Path,
) -> None:
    numpy = pytest.importorskip("numpy")
    source = tmp_path / "bls"
    raw = source / "raw"
    raw.mkdir(parents=True)
    specifications = {
        "cu.data.1.AllItems": ("CUSR0000SA0", 0.031, 0.17, 0.0),
        "cu.data.12.USHousing": ("CUSR0000SAH", 0.029, 0.16, 0.0),
        "cu.data.15.USMedical": ("CUSR0000SAM", 0.026, 0.13, 0.0),
        "ce.data.00a.TotalNonfarm.Employment": ("CES0000000001", 0.018, 0.11, 2.0),
        "ce.data.30a.Manufacturing.Employment": ("CES3000000001", 0.015, 0.16, 7.0),
        "ce.data.50a.Information.Employment": ("CES5000000001", 0.021, 0.13, -3.0),
    }
    for filename, (series_id, trend, amplitude, shift) in specifications.items():
        rows = ["series_id\tyear\tperiod\tvalue"]
        for index in range(19 * 12):
            year = 2008 + index // 12
            month = index % 12 + 1
            value = 100.0 * numpy.exp(trend * index / 12 + amplitude * numpy.sin((index - shift) / 8))
            rows.append(f"{series_id}\t{year}\tM{month:02d}\t{value:.8f}")
        (raw / filename).write_text("\n".join(rows) + "\n", encoding="utf-8")

    inventory = AssetInventory().inventory(
        root=source, source_id="src:bls", study_id="study:bls"
    )
    outcomes, limitations = analyze_collection(
        study_id="study:bls", assets=inventory.assets, root=source
    )
    assert limitations == []
    assert len(outcomes) == 3
    assert all(item.plan.operator == "bls_preregistered_lead_lag_holdout" for item in outcomes)
    assert all(item.result.sensitivities[0]["specification"] == "training" for item in outcomes)
    assert all(item.result.sensitivities[1]["specification"] == "chronological_holdout" for item in outcomes)
    for outcome in outcomes:
        anchors = (outcome.evidence, *outcome.additional_evidence)
        assert len(anchors) == 2
        assert len({item.asset_id for item in anchors}) == 2
        assert len(outcome.finding.evidence_ids) == 2
        assert {item.evidence_id for item in anchors} == set(outcome.finding.evidence_ids)


def test_oeis_collection_operator_recovers_only_exact_held_out_recurrences(
    tmp_path: Path,
) -> None:
    source = tmp_path / "oeis"
    raw = source / "raw"
    raw.mkdir(parents=True)
    stripped = raw / "stripped.gz"
    names = raw / "names.gz"
    with gzip.open(stripped, "wt", encoding="utf-8") as sequence_stream, gzip.open(
        names, "wt", encoding="utf-8"
    ) as name_stream:
        for index in range(1, 101):
            accession = f"A{29 * index:06d}"
            terms = [index + 2 * position + position * position for position in range(20)]
            sequence_stream.write(
                f"{accession} ," + ",".join(str(value) for value in terms) + ",\n"
            )
            name_stream.write(f"{accession} Synthetic quadratic family member {index}\n")

    inventory = AssetInventory().inventory(
        root=source, source_id="src:oeis", study_id="study:oeis"
    )
    outcomes, limitations = analyze_collection(
        study_id="study:oeis", assets=inventory.assets, root=source
    )
    assert limitations == []
    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome.plan.operator == "oeis_exact_recurrence_family"
    assert outcome.result.expression_latex == "a_n = 3a_{n-1} - 3a_{n-2} + a_{n-3}"
    assert outcome.result.split_validation["test"] == {
        "passed": True,
        "frozen_predictions": True,
        "held_out_prediction_errors": 0,
        "minimum_held_out_terms": 6,
    }
    rule_gate = outcome.result.split_validation["rule_gate"]
    assert rule_gate["interpretable_law_family"]
    assert rule_gate["held_out_baseline_improvement"]
    assert rule_gate["parameter_stability"]
    assert rule_gate["unit_plausibility"]
    assert rule_gate["negative_control"] is True
    assert outcome.result.split_validation["negative_control"]["passed"] is True
    assert outcome.finding.status == "supported_candidate"
    assert outcome.finding.insight_level == "principle_level"
    assert "zero third finite difference" in outcome.finding.principle_statement
    assert outcome.finding.validation_level == "internal_holdout"
    assert 1 + len(outcome.additional_evidence) == 2


def test_matrix_market_coordinates_never_become_generic_correlations(
    tmp_path: Path,
) -> None:
    source = tmp_path / "matrix-market"
    source.mkdir()
    matrix = source / "matrix.mtx.gz"
    with gzip.open(matrix, "wt", encoding="utf-8") as stream:
        stream.write("%%MatrixMarket matrix coordinate integer general\n")
        stream.write("100 20 40\n")
        for index in range(1, 41):
            stream.write(f"{index} {(index % 20) + 1} {index * 3}\n")
    inventory = AssetInventory().inventory(
        root=source, source_id="src:matrix", study_id="study:matrix"
    )
    asset = next(item for item in inventory.assets if item.format == "matrix_market_gzip")
    assert analyze_asset(study_id="study:matrix", asset=asset, root=source) is None


def test_repeated_same_label_workbook_columns_do_not_create_self_correlations(
    tmp_path: Path,
) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    source = tmp_path / "repeated-measurement-columns"
    source.mkdir()
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Spectra"
    sheet.append(["Intensity (arb. units)", "Intensity (arb. units)"])
    for index in range(1, 81):
        sheet.append([float(index), float(index * 2)])
    workbook.save(source / "spectra.xlsx")

    inventory = AssetInventory().inventory(
        root=source,
        source_id="src:repeated-measurement-columns",
        study_id="study:repeated-measurement-columns",
    )
    asset = next(item for item in inventory.assets if item.format == "xlsx")
    assert (
        analyze_asset(
            study_id="study:repeated-measurement-columns",
            asset=asset,
            root=source,
        )
        is None
    )


def test_promotion_gate_rejects_exploratory_unassessed_and_confounded_results() -> None:
    finding = DataFinding(
        finding_id="finding:gate",
        study_id="study:gate",
        title="A fluent claim that must remain held back",
        claim="A seemingly strong relationship survived several local checks.",
        interpretation="The pattern may be meaningful.",
        mechanism="A concrete but still unverified mechanism is proposed.",
        insight_level="principle_level",
        principle_statement="A proposed transferable relationship.",
        transfer_scope="Related systems under the same conditions.",
        status="supported_candidate",
        validation_level="exploratory",
        novelty_status="not_assessed",
        evidence_ids=["evidence:1"],
        robustness=["check one", "check two", "check three"],
        confounders=["The result remains confounded by collection batch."],
        falsifiers=["It fails in an independent batch."],
    )
    eligible, blockers = DataDiscoveryService._promotion_gate(finding)
    assert eligible is False
    assert "an independent holdout or cross-modal replication is required" in blockers
    assert "current prior art has not been assessed" in blockers
    assert "a declared design confounder remains unresolved" in blockers

    eligible_finding = finding.model_copy(
        update={
            "validation_level": "internal_holdout",
            "novelty_status": "no_close_prior_art_found",
            "confounders": [],
        }
    )
    assert DataDiscoveryService._promotion_gate(eligible_finding) == (True, [])


def test_hafnia_collection_operator_preserves_wafer_identity_and_spatial_controls(
    tmp_path: Path,
) -> None:
    numpy = pytest.importorskip("numpy")
    source = tmp_path / "hafnia"
    for wafer, offset in (("02", 0.0), ("08", 0.015)):
        folder = source / "raw" / "CHIPS-6-02-25-00-set" / f"25-{wafer}"
        folder.mkdir(parents=True)
        rows = [
            "X (cm),Y (cm),MSE,Thickness # 1 (nm),n of Cauchy @ 632.8 nm"
        ]
        for y_value in numpy.linspace(-9, 9, 17):
            for x_value in numpy.linspace(-6, 6, 7):
                residual = 0.04 * numpy.sin(1.7 * x_value + 0.9 * y_value)
                thickness = 9.6 - 0.056 * y_value + residual + offset
                refractive_index = 2.2 + 0.001 * y_value - 0.012 * residual
                rows.append(
                    f"{x_value:.4f},{y_value:.4f},6.0,{thickness:.8f},{refractive_index:.8f}"
                )
        (folder / f"CHIPS-6-02-25-{wafer}-parameters.csv").write_text(
            "\n".join(rows) + "\n", encoding="utf-8"
        )

    inventory = AssetInventory().inventory(
        root=source, source_id="src:hafnia", study_id="study:hafnia"
    )
    outcomes, limitations = analyze_collection(
        study_id="study:hafnia", assets=inventory.assets, root=source
    )
    assert limitations == []
    by_operator = {item.plan.operator: item for item in outcomes}
    assert {
        "hafnia_nonradial_wafer_gradient_replication",
        "hafnia_se_thickness_index_identifiability",
    } <= set(by_operator)
    gradient = by_operator["hafnia_nonradial_wafer_gradient_replication"]
    assert gradient.finding.status == "supported_candidate"
    assert r"T_w(x,y)" in gradient.result.expression_latex
    assert gradient.result.split_validation["rule_gate"]["transfer_boundary_declared"] is True
    assert gradient.result.split_validation["negative_control"]["passed"] is True
    assert {item["wafer"] for item in gradient.result.estimate["wafer_results"]} == {
        "25-02",
        "25-08",
    }
    assert len(gradient.finding.evidence_ids) == 2


def test_geojson_uses_space_time_geometry_and_zip_prefers_main_puf(
    tmp_path: Path,
) -> None:
    source = tmp_path / "semantic-loaders"
    source.mkdir()
    features = [
        {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [float(index % 20), float(index % 10), 5.0],
            },
            "properties": {
                "mag": 2.5 + (index % 5) * 0.1,
                "time": 1_700_000_000_000 + index * 3_600_000,
                "sig": 100 + index,
                "gap": 45.0,
                "rms": 0.3,
                "nst": 20,
                "dmin": 0.1,
            },
        }
        for index in range(240)
    ]
    (source / "events.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": features}),
        encoding="utf-8",
    )
    with zipfile.ZipFile(source / "survey.zip", "w") as archive:
        archive.writestr(
            "SURVEY_REPWGT_PUF.csv",
            "PWEIGHT0,PWEIGHT1\n" + "1,1\n" * 1_000,
        )
        archive.writestr(
            "SURVEY_PUF.csv",
            "AGE,INCOME,AI_USE\n" + "30,50000,1\n" * 100,
        )
    inventory = AssetInventory().inventory(
        root=source, source_id="src:semantic", study_id="study:semantic"
    )
    by_format = {item.format: item for item in inventory.assets}
    geojson_outcome = analyze_asset(
        study_id="study:semantic", asset=by_format["json"], root=source
    )
    assert geojson_outcome is not None
    assert geojson_outcome.plan.operator == "earthquake_space_time_clustering"
    assert "mag" not in geojson_outcome.finding.title.casefold()
    assert r"\mathcal R" in geojson_outcome.result.expression_latex
    assert geojson_outcome.result.split_validation["rule_gate"]["transfer_boundary_declared"] is True
    survey = load_numeric(by_format["zip"], source)
    assert survey is not None
    assert survey.locator["archive_member"] == "SURVEY_PUF.csv"
    assert survey.variables == ["AGE", "INCOME", "AI_USE"]


def test_discovery_service_writes_only_outside_source(tmp_path: Path) -> None:
    source = _scenario(tmp_path)
    before = _tree_receipt(source)
    working = tmp_path / "working"
    product = Principia.open(working_directory=working, cloud_root=tmp_path / "cloud")
    try:
        product.repository.register_source(
            "src:test", source, "external://test", "Synthetic data", "External/Synthetic"
        )
        study = product.data_discovery.create(
            source_ids=["src:test"],
            provider="",
            budget="fast",
            egress_confirmed=False,
            defer=False,
        )
        assert study["state"] == "partial"
        assert study["coverage"]["executed_test_count"] >= 1
        findings = product.data_discovery.findings(study["study_id"])
        assert findings
        assert all(item["novelty_status"] == "not_assessed" for item in findings)
        rules = product.data_discovery.rules(study["study_id"])
        assert rules == []
        output = product.workspace.outputs_dir / study["study_id"]
        assert {"report.md", "report.json", "findings.json", "tests.json", "rules.json", "provenance.json"} <= {
            item.name for item in output.iterdir()
        }
        exported = "\n".join(
            path.read_text(encoding="utf-8")
            for path in output.iterdir()
            if path.is_file()
        )
        assert str(source) not in exported
        assert _tree_receipt(source) == before
    finally:
        product.close()


def test_insight_depth_is_capped_by_executed_evidence_not_model_rhetoric(
    tmp_path: Path,
) -> None:
    source = _scenario(tmp_path)
    inventory = AssetInventory().inventory(
        root=source, source_id="src:depth", study_id="study:depth"
    )
    outcome = analyze_asset(
        study_id="study:depth",
        asset=next(item for item in inventory.assets if item.role == "raw"),
        root=source,
    )
    assert outcome is not None
    shallow = DataDiscoveryService._finalize_insight_contract(
        outcome.finding, requested_level="principle_level"
    )
    assert shallow.insight_level in {"observational", "structural"}

    replicated = outcome.finding.model_copy(
        update={
            "title": "Response regime reversal survives an internal holdout",
            "claim": "The response reverses sign across two regimes (r=0.72 versus r=-0.61).",
            "interpretation": "The pooled relationship hides a stable boundary between regimes.",
            "mechanism": (
                "A change in the limiting process redirects the response pathway, so the same "
                "input perturbation produces opposite effects on either side of the boundary."
            ),
            "significance": "Calibration must be stratified by regime rather than pooled.",
            "principle_chain": [
                "The limiting process changes at the boundary.",
                "The response pathway therefore changes direction.",
                "A pooled calibration erases the sign reversal.",
            ],
            "status": "supported_candidate",
            "validation_level": "internal_holdout",
            "test_ids": ["test:one", "test:two"],
            "robustness": ["holdout", "negative control", "alternative specification"],
            "falsifiers": ["The sign reversal disappears under matched conditions."],
        }
    )
    deep = DataDiscoveryService._finalize_insight_contract(
        replicated, requested_level="principle_level"
    )
    assert deep.insight_level == "principle_level"
    assert deep.principle_statement
    assert deep.nontriviality_basis


def test_reasoning_cannot_replace_a_quantitative_claim_with_generic_prose(
    tmp_path: Path,
) -> None:
    source = _scenario(tmp_path)
    inventory = AssetInventory().inventory(
        root=source, source_id="src:specificity", study_id="study:specificity"
    )
    outcome = analyze_asset(
        study_id="study:specificity",
        asset=next(item for item in inventory.assets if item.role == "raw"),
        root=source,
    )
    assert outcome is not None
    original = outcome.finding.model_copy(
        update={
            "claim": "Response changed by 42% across the threshold (95% CI 31% to 53%)."
        }
    )
    interpretation = FindingInterpretation(
        finding_id=original.finding_id,
        claim="The data suggest that an important relationship may exist.",
        interpretation="The relationship may be useful.",
        mechanism="A sufficiently detailed mechanism remains to be tested in a controlled experiment.",
    )
    retained, _ = DataDiscoveryService._apply_reasoning_interpretations(
        findings=[original],
        interpretations={original.finding_id: interpretation},
        allowed_principles=set(),
    )
    assert retained[0].claim == original.claim


def test_prior_art_gate_rejects_cross_domain_keyword_coincidence(
    tmp_path: Path,
) -> None:
    source = _scenario(tmp_path)
    inventory = AssetInventory().inventory(
        root=source, source_id="src:prior-art", study_id="study:prior-art"
    )
    outcome = analyze_asset(
        study_id="study:prior-art",
        asset=next(item for item in inventory.assets if item.role == "raw"),
        root=source,
    )
    assert outcome is not None
    finding = outcome.finding.model_copy(
        update={
            "title": "Conductance-to-thickness coupling reverses across deposition regimes",
            "claim": "Wafer maps separate into opposite PECVD process regimes.",
            "mechanism": "Precursor transport and plasma deposition change the film-growth response.",
        }
    )
    assert _prior_art_title_relevant(
        finding,
        {
            "title": "Effects of vapor deposition and coating thickness on thermal conductance"
        },
    )
    assert not _prior_art_title_relevant(
        finding,
        {"title": "The reverse relationship between exchange-rate regimes and macro variables"},
    )
    assert not _prior_art_title_relevant(
        finding,
        {"title": "Silk thickness uniformity under microclimate control"},
    )


def test_principle_gate_rejects_a_polished_cross_domain_non_sequitur(
    tmp_path: Path,
) -> None:
    source = _scenario(tmp_path)
    inventory = AssetInventory().inventory(
        root=source, source_id="src:principle-link", study_id="study:principle-link"
    )
    outcome = analyze_asset(
        study_id="study:principle-link",
        asset=next(item for item in inventory.assets if item.role == "raw"),
        root=source,
    )
    assert outcome is not None
    finding = outcome.finding.model_copy(
        update={
            "title": "Contiguous-time coherence rejects unstable TESS periods",
            "claim": "A TESS light-curve period must recur across contiguous temporal windows.",
            "mechanism": "Nonstationary stellar signals and instrumental aliases fail temporal coherence.",
        }
    )
    assert _principle_relevant_to_finding(
        finding,
        {
            "title": "Temporal replication across contiguous windows",
            "claim": "Persistent oscillations require coherent frequency structure across time windows.",
        },
    )
    assert not _principle_relevant_to_finding(
        finding,
        {
            "title": "Small aperture size for survey optimization",
            "claim": "Small space-telescope apertures favor wide surveys over detailed nearby science.",
        },
    )
    pecvd = finding.model_copy(
        update={
            "title": "Mean thickness and wafer uniformity expose separable PECVD controls",
            "claim": "Deposition recipe changes film thickness and spatial uniformity independently.",
            "mechanism": "Chamber transport and surface reaction set distinct process axes.",
        }
    )
    assert not _principle_relevant_to_finding(
        pecvd,
        {
            "principle_id": "prn:neuroscience-cognitive-science:example",
            "title": "Exploration and interaction for implicit sensorimotor learning",
            "claim": "Neural motor learning depends on cortical exploration.",
        },
    )
    cure = finding.model_copy(
        update={
            "title": "Conversion-dependent cure activation barrier",
            "claim": "Thermoset cure kinetics change near vitrification.",
            "mechanism": "Polymer conversion changes the apparent thermal activation energy.",
        }
    )
    assert not _principle_relevant_to_finding(
        cure,
        {
            "principle_id": "prn:materials:borophene",
            "title": "Diffusion energy barrier on flat borophene",
            "claim": "Thermal stability and ion diffusion depend on an energy barrier.",
        },
    )
    household = finding.model_copy(
        update={
            "title": "Liquid savings buffer income volatility",
            "claim": "Household savings reduce bill struggle during income shocks.",
            "mechanism": "Liquid reserves smooth timing mismatches between volatile income and fixed obligations.",
        }
    )
    assert _principle_relevant_to_finding(
        household,
        {
            "principle_id": "prn:economics:financial-buffer",
            "title": "Household savings buffer financial shocks",
            "claim": "Liquid savings preserve household financial stability during income volatility.",
        },
    )


def test_domain_foundations_resolve_existing_cloud_records_without_quota_padding(
    tmp_path: Path,
) -> None:
    source = _scenario(tmp_path)
    inventory = AssetInventory().inventory(
        root=source, source_id="src:foundation-link", study_id="study:foundation-link"
    )
    outcome = analyze_asset(
        study_id="study:foundation-link",
        asset=next(item for item in inventory.assets if item.role == "raw"),
        root=source,
    )
    assert outcome is not None
    cure = outcome.finding.model_copy(
        update={
            "title": "Conversion-dependent cure activation barrier",
            "claim": "Thermoset cure kinetics change as conversion approaches vitrification.",
            "mechanism": "Heating-rate shifts encode an apparent activation energy.",
        }
    )
    identifiers = _foundation_ids_for_finding(cure)
    assert identifiers[:2] == [
        "meta:chemistry-materials:arrhenius-rate",
        "meta:chemistry-materials:thermodynamics-kinetics",
    ]
    assert _principle_relevant_to_finding(
        cure,
        {
            "principle_id": "meta:chemistry-materials:arrhenius-rate",
            "title": "Reaction rates vary exponentially with inverse temperature",
        },
    )
    unrelated = outcome.finding.model_copy(
        update={
            "title": "Household income survey response",
            "claim": "Weighted household income varies across regions.",
            "mechanism": "Survey weighting adjusts unequal selection probabilities.",
        }
    )
    assert "meta:chemistry-materials:arrhenius-rate" not in _foundation_ids_for_finding(
        unrelated
    )


def test_analysis_unit_budget_is_not_truncated_by_hypothesis_cap(
    tmp_path: Path,
) -> None:
    source = tmp_path / "many-assets"
    raw = source / "raw"
    raw.mkdir(parents=True)
    body = "temperature,response\n" + "".join(
        f"{index},{3 * index + 2}\n" for index in range(1, 121)
    )
    for index in range(12):
        (raw / f"replicate-{index:02d}.csv").write_text(body, encoding="utf-8")
    product = Principia.open(
        working_directory=tmp_path / "many-working", cloud_root=tmp_path / "many-cloud"
    )
    try:
        product.repository.register_source(
            "src:many", source, "external://many", "Many assets", "External/Many"
        )
        study = product.data_discovery.create(
            source_ids=["src:many"],
            provider="",
            budget="fast",
            egress_confirmed=False,
            defer=False,
        )
        assert study["coverage"]["executed_test_count"] == 13  # 12 original analyses and one deduplicated provisional fit
    finally:
        product.close()


def test_screened_projection_cannot_reuse_the_next_durable_unit_ordinal(
    tmp_path: Path,
) -> None:
    source = tmp_path / "mixed-projections"
    raw = source / "raw"
    raw.mkdir(parents=True)
    (raw / "labels.csv").write_text("label\na\nb\n", encoding="utf-8")
    (raw / "measurements.csv").write_text(
        "temperature,response\n"
        + "".join(f"{index},{4 * index + 1}\n" for index in range(1, 121)),
        encoding="utf-8",
    )
    product = Principia.open(
        working_directory=tmp_path / "mixed-working", cloud_root=tmp_path / "mixed-cloud"
    )
    try:
        product.repository.register_source(
            "src:mixed", source, "external://mixed", "Mixed projections", "External/Test"
        )
        study = product.data_discovery.create(
            source_ids=["src:mixed"],
            provider="",
            budget="fast",
            egress_confirmed=False,
            defer=False,
        )
        assert study["state"] == "partial"
        with product.repository.connect() as connection:
            ordinals = [
                row[0]
                for row in connection.execute(
                    "SELECT ordinal FROM data_job_units WHERE study_id=? ORDER BY ordinal",
                    (study["study_id"],),
                )
            ]
        assert ordinals == [0, 1]
        assert study["coverage"]["executed_test_count"] == 2  # original analysis plus a provisional fit
    finally:
        product.close()


def test_prior_art_is_conservative_and_findings_keep_graph_identity(
    tmp_path: Path,
) -> None:
    source = _scenario(tmp_path)
    product = Principia.open(
        working_directory=tmp_path / "graph-working", cloud_root=tmp_path / "graph-cloud"
    )
    try:
        inventory = AssetInventory().inventory(
            root=source, source_id="src:graph", study_id="study:graph"
        )
        outcome = analyze_asset(
            study_id="study:graph",
            asset=next(item for item in inventory.assets if item.role == "raw"),
            root=source,
        )
        assert outcome is not None
        product.data_discovery.literature_searcher = lambda *args, **kwargs: {
            "search_id": "search:prior-art",
            "state": "ready",
            "sources": ["crossref"],
            "unavailable_sources": [],
            "results": [
                {
                    "work_id": "doi:10.1000/example",
                    "title": f"Independent replication of {outcome.finding.title}",
                    "year": 2025,
                    "doi": "10.1000/example",
                    "url": "https://doi.org/10.1000/example",
                    "publication_status": "published",
                }
            ],
        }
        reviewed, receipts, warning = product.data_discovery._review_prior_art(
            findings=[outcome.finding], objective="", maximum=1
        )
        assert warning == ""
        assert reviewed[0].novelty_status == "prior_art_found"
        assert reviewed[0].novelty_status != "possibly_novel"
        assert receipts[0]["result_count"] == 1

        now = utc_now()
        with product.repository.connect() as connection:
            connection.execute(
                """
                INSERT INTO research_sessions(
                    session_id, project_id, title, active_run_id, state, revision,
                    graph_revision, source_ids_json, provider_profile_id, model,
                    archived_at, created_at, updated_at
                ) VALUES ('session:data', NULL, 'Data session', NULL, 'ready', 1,
                          0, '[]', 'siliconflow', '', '', ?, ?)
                """,
                (now, now),
            )
            connection.execute(
                "INSERT INTO research_graph_state VALUES ('session:data', '{}', "
                "'daylight', 0, ?)",
                (now,),
            )
        finding = reviewed[0].model_copy(update={"principle_ids": ["principle:known"]})
        receipt = product.repository.seed_data_discovery_graph(
            "session:data",
            [finding],
            [{"id": "principle:known", "title": "Known mechanism"}],
        )
        assert receipt["state"] == "seeded"
        with product.repository.connect() as connection:
            kinds = {
                row[0]: row[1]
                for row in connection.execute(
                    "SELECT principle_id, record_kind FROM research_graph_items "
                    "WHERE session_id='session:data'"
                )
            }
        assert kinds[finding.finding_id] == "discovery_finding"
        assert kinds["principle:known"] == "ordinary"

        planning_receipt = product.repository.seed_data_discovery_graph(
            "session:data",
            [],
            [{"id": "principle:planning", "title": "Planning mechanism"}],
            used_principle_ids=["principle:planning"],
        )
        assert planning_receipt["principle_count"] == 1
        with product.repository.connect() as connection:
            planning_kind = connection.execute(
                "SELECT record_kind FROM research_graph_items "
                "WHERE session_id='session:data' AND principle_id='principle:planning'"
            ).fetchone()
        assert planning_kind is not None
        assert planning_kind[0] == "ordinary"
    finally:
        product.close()


def test_sandbox_rejects_io_and_executes_audited_code(tmp_path: Path) -> None:
    sandbox = AnalysisSandbox(wall_timeout_seconds=10)
    blocked = sandbox.audit("import os\nRESULT={'value': open('/etc/passwd').read()}")
    assert blocked.fallback_required is True
    assert any("import is not allowed" in item for item in blocked.violations)
    assert any("call is not allowed: open" in item for item in blocked.violations)
    for unsafe in (
        "import socket\nRESULT={}",
        "import subprocess\nRESULT={}",
        "import ctypes\nRESULT={}",
        "RESULT=eval('1 + 1')",
        "RESULT=__import__('os').environ",
    ):
        assert AnalysisSandbox().audit(unsafe).fallback_required is True
    if sys.platform != "darwin" or not sandbox.available:
        pytest.skip("verified generated-code isolation is currently macOS sandbox-exec")
    result, audit = sandbox.run(
        code="import math\nRESULT={'root': math.sqrt(INPUT['value'])}",
        inputs={"value": 81},
        artifact_root=tmp_path / "sandbox",
        seed=42,
    )
    assert result == {"root": 9.0}
    assert audit.isolated is True
    assert audit.fallback_required is False
    assert audit.memory_limit_bytes == 4 * 1024 * 1024 * 1024
    assert audit.memory_limit_kind == "resident_set_guard"
    assert audit.max_resident_bytes > 0

    failed_result, failed_audit = sandbox.run(
        code="raise RuntimeError('forced acceptance failure')\nRESULT={}",
        inputs={},
        artifact_root=tmp_path / "failure",
        seed=42,
    )
    stderr = (tmp_path / "failure" / "stderr.log").read_text(encoding="utf-8")
    assert failed_result is None
    assert failed_audit.fallback_required is True
    assert "forced acceptance failure" in stderr
    assert 'File "<local-path>"' in stderr
    assert str(tmp_path) not in stderr
    assert str(Path.home()) not in stderr

    timed_result, timed_audit = AnalysisSandbox(wall_timeout_seconds=1).run(
        code="while True:\n    pass\nRESULT={}",
        inputs={},
        artifact_root=tmp_path / "timeout",
        seed=42,
    )
    assert timed_result is None
    assert timed_audit.timed_out is True
    assert timed_audit.fallback_required is True


def test_dicom_preview_exposes_pixels_but_not_patient_metadata(tmp_path: Path) -> None:
    pydicom = pytest.importorskip("pydicom")
    numpy = pytest.importorskip("numpy")
    from pydicom.dataset import FileDataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid

    source = tmp_path / "dicom"
    source.mkdir()
    path = source / "image.dcm"
    meta = FileMetaDataset()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    dataset = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    dataset.PatientName = "PRIVATE^PERSON"
    dataset.PatientID = "SECRET-ID"
    dataset.SOPClassUID = meta.MediaStorageSOPClassUID
    dataset.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    dataset.Rows = 16
    dataset.Columns = 16
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.BitsAllocated = 16
    dataset.BitsStored = 16
    dataset.HighBit = 15
    dataset.PixelRepresentation = 0
    dataset.PixelData = numpy.arange(256, dtype=numpy.uint16).tobytes()
    pydicom.dcmwrite(path, dataset, enforce_file_format=True)
    inventory = AssetInventory().inventory(
        root=source, source_id="src:dicom", study_id="study:dicom"
    )
    preview = build_preview(inventory.assets[0], source)
    body = json.dumps(preview)
    assert preview["kind"] == "image"
    assert preview["derived"] is True
    assert "PRIVATE" not in body
    assert "SECRET-ID" not in body


def test_additive_api_runs_without_egress_and_returns_no_store_previews(
    tmp_path: Path,
) -> None:
    source = _scenario(tmp_path)
    product = Principia.open(
        working_directory=tmp_path / "api-working", cloud_root=tmp_path / "api-cloud"
    )
    try:
        product.repository.register_source(
            "src:api", source, "external://api", "API data", "External/API"
        )
        app = create_app(product, test_mode=True)
        client = TestClient(app)
        response = client.post(
            "/api/v1/data-discoveries",
            headers={"X-Principia-Session": app.state.session_token},
            json={
                "source_ids": ["src:api"],
                "provider": "siliconflow",
                "egress_confirmed": False,
                "budget": "fast",
            },
        )
        assert response.status_code == 202
        study_id = response.json()["study_id"]
        for _ in range(100):
            detail = client.get(f"/api/v1/data-discoveries/{study_id}").json()
            if detail["state"] in {"succeeded", "partial", "failed", "cancelled"}:
                break
            time.sleep(0.03)
        assert detail["state"] == "partial"
        assert detail["request"]["provider"] == ""
        assets = client.get("/api/v1/local/sources/src:api/assets").json()
        csv_asset = next(item for item in assets["items"] if item["format"] == "csv")
        preview = client.get(
            f"/api/v1/local/sources/src:api/assets/{csv_asset['asset_id']}/preview"
        )
        assert preview.status_code == 200
        assert preview.headers["cache-control"] == "no-store"
        assert preview.json()["kind"] == "table"
        findings = client.get(
            f"/api/v1/data-discoveries/{study_id}/findings"
        ).json()["items"]
        rules_response = client.get(
            f"/api/v1/data-discoveries/{study_id}/rules"
        )
        assert rules_response.status_code == 200
        assert rules_response.json()["schema_version"] == "principia.data-rules/v1"
        # A generic two-column response line remains an executed observation;
        # it must not be promoted into a transferable scientific Rule.
        assert rules_response.json()["items"] == []
        programs_response = client.get(
            f"/api/v1/data-discoveries/{study_id}/programs"
        )
        assert programs_response.status_code == 200
        assert programs_response.json()["schema_version"] == (
            "principia.scientific-program-collection/v1"
        )
        programs = programs_response.json()["items"]
        assert {item["track"] for item in programs} == {
            "mechanism",
            "predictive_closure",
        }
        program_detail = client.get(
            f"/api/v1/data-discoveries/{study_id}/programs/{programs[0]['program_id']}"
        )
        assert program_detail.status_code == 200
        assert "candidate_frontier" in program_detail.json()
        laws_response = client.get(f"/api/v1/data-discoveries/{study_id}/laws")
        assert laws_response.status_code == 200
        assert laws_response.json()["schema_version"] == (
            "principia.scientific-law-collection/v1"
        )
        artifacts_response = client.get(
            f"/api/v1/data-discoveries/{study_id}/artifacts"
        )
        assert artifacts_response.status_code == 200
        assert artifacts_response.json()["schema_version"] == (
            "principia.data-discovery-artifacts/v1"
        )
        finding_detail = client.get(
            f"/api/v1/data-discoveries/{study_id}/findings/{findings[0]['finding_id']}"
        )
        assert finding_detail.status_code == 200
        assert finding_detail.json()["tests"]
        assert finding_detail.json()["evidence"]
        assert finding_detail.json()["insight_level"] in {
            "observational",
            "structural",
            "mechanistic",
            "principle_level",
        }
        draft = client.post(
            f"/api/v1/data-discoveries/{study_id}/findings/{findings[0]['finding_id']}/principle-draft",
            headers={"X-Principia-Session": app.state.session_token},
        )
        assert findings[0]["promotion_eligible"] is False
        assert findings[0]["promotion_blockers"]
        assert draft.status_code == 409
        assert "Principle drafting is blocked" in draft.json()["error"]["message"]
    finally:
        product.close()
