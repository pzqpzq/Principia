from __future__ import annotations

from principia.data_discovery.semantics import classify_variable, compile_dataset_semantics
from principia.domain import DataView


def _view(name: str, variables: list[str], *, kind: str = "table") -> DataView:
    return DataView(
        view_id=f"view:{name}",
        study_id="study:semantics",
        asset_ids=[f"asset:{name}"],
        kind=kind,  # type: ignore[arg-type]
        name=name,
        variables=variables,
        content_digest="a" * 64,
    )


def test_semantic_compiler_prohibits_identifiers_and_weights_as_science() -> None:
    assert classify_variable("record_id")["scientific_use"] == "prohibited_as_variable"
    assert classify_variable("PWEIGHT")["scientific_use"] == "design_only"
    compiled = compile_dataset_semantics(
        [_view("survey", ["respondent_id", "PWEIGHT", "year", "income", "outcome_score"])]
    )
    assert compiled["recommended_split_strategy"] == "group"
    assert compiled["independent_unit_candidates"][0]["variable"] == "respondent_id"
    assert {item["variable"] for item in compiled["prohibited_scientific_variables"]} == set()
    roles = compiled["role_counts"]
    assert roles["survey_weight"] == 1
    assert roles["measurement_candidate"] >= 1


def test_semantic_compiler_prefers_contiguous_splits_for_unlabelled_signals() -> None:
    compiled = compile_dataset_semantics(
        [_view("strain", ["strain", "sample_index"], kind="signal")]
    )
    assert compiled["recommended_split_strategy"] == "contiguous_epoch"
    assert compiled["schema_version"] == "principia.dataset-semantics/v1"
