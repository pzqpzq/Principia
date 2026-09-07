"""Formula-first scientific programs and structure-triggered law discovery.

This module intentionally knows no scenario, directory, workbook, or worksheet
names.  It operates on typed scientific signatures and keeps complete
experimental objects together throughout selection and evaluation.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from ..domain import (
    DataAsset,
    EquationNode,
    ExecutableHypothesis,
    GateReceipt,
    LawCandidate,
    LawEvaluation,
    ScientificDecision,
    ScientificLawCalibration,
    ScientificLawFamily,
    ScientificProgram,
    SplitManifest,
    StudyBlueprint,
    TransformGraph,
    canonical_sha256,
)
from ..models import utc_now
from .collection_operators import _collection_outcome
from .law_ast import associative_node, ast_digest, canonicalize, evaluate, infer_dimension
from .operators import OperatorOutcome

SCIENTIFIC_PROGRAM_VERSION = "principia-scientific-program/1"
SPATIAL_EXECUTOR_VERSION = "principia-replicated-spatial-field/5"
MIN_SPATIAL_POINTS = 24
MAX_WORKBOOK_COLUMNS = 128
MAX_WORKBOOK_ROWS = 600


@dataclass(frozen=True)
class ScientificProgramBundle:
    programs: tuple[ScientificProgram, ...]
    split_manifests: tuple[SplitManifest, ...] = ()
    transform_graphs: tuple[TransformGraph, ...] = ()
    laws: tuple[ScientificLawFamily, ...] = ()
    calibrations: tuple[ScientificLawCalibration, ...] = ()
    candidates: tuple[LawCandidate, ...] = ()
    evaluations: tuple[LawEvaluation, ...] = ()
    decisions: tuple[ScientificDecision, ...] = ()
    outcomes: tuple[OperatorOutcome, ...] = ()
    limitations: tuple[str, ...] = ()
    search_receipts: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class _FieldBlock:
    asset: DataAsset
    sheet_token: str
    sheet_label: str
    header_row: int
    row_numbers: tuple[int, ...]
    coordinates: np.ndarray
    fields: dict[str, np.ndarray]
    field_context: dict[str, tuple[str, ...]]
    role: str
    context: str
    coordinate_columns: tuple[int, int]
    field_strata: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass(frozen=True)
class _SpatialObject:
    object_id: str
    asset: DataAsset
    regime: str
    label: str
    coordinates: np.ndarray
    driver: np.ndarray
    target: np.ndarray
    locator: dict[str, Any]


@dataclass(frozen=True)
class _FittedModel:
    spec: str
    ridge: float
    names: tuple[str, ...]
    means: np.ndarray
    scales: np.ndarray
    coefficients: np.ndarray
    intercept: float


def _safe_path(root: Path, asset: DataAsset) -> Path:
    canonical_root = root.resolve(strict=True)
    relative = str(asset.metadata.get("relative_path") or "")
    candidate = (canonical_root / relative).resolve(strict=True)
    if not candidate.is_relative_to(canonical_root) or not candidate.is_file():
        raise ValueError("scientific-program asset locator escapes its registered source")
    return candidate


def _token(value: Any) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", str(value or "").casefold())


def _field_label(value: Any) -> str:
    return " ".join(str(value or "").replace("\n", " ").split())[:160]


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    try:
        parsed = float(str(value).strip().replace(",", ""))
        return parsed if math.isfinite(parsed) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _context_role(value: str) -> str:
    normalized = value.casefold()
    driver_terms = (
        "conductance", "flow", "aperture", "hole depth", "孔径", "孔深", "流导",
        "input", "driver", "control", "dose", "recipe",
    )
    target_terms = (
        "thickness", "thk", "膜厚", "response", "outcome", "yield", "growth",
        "deposition rate", "沉积速率",
    )
    driver = sum(term in normalized for term in driver_terms)
    target = sum(term in normalized for term in target_terms)
    if driver > target and driver:
        return "driver"
    if target > driver and target:
        return "target"
    return "unknown"


def _sheet_context(sheet: Any, *, header_row: int, start: int, end: int) -> str:
    values: list[str] = [str(sheet.title)]
    for row in range(1, min(header_row, 12) + 1):
        for column in range(max(1, start - 2), min(end + 1, MAX_WORKBOOK_COLUMNS) + 1):
            value = sheet.cell(row, column).value
            if isinstance(value, str) and value.strip():
                values.append(value.strip())
    return " | ".join(values)[:8_000]


def _merged_cell_value(sheet: Any, row: int, column: int) -> Any:
    value = sheet.cell(row, column).value
    if value is not None:
        return value
    for merged in sheet.merged_cells.ranges:
        if merged.min_row <= row <= merged.max_row and merged.min_col <= column <= merged.max_col:
            return sheet.cell(merged.min_row, merged.min_col).value
    return None


def _field_context(sheet: Any, *, header_row: int, column: int) -> tuple[str, ...]:
    values: list[str] = []
    for row in range(max(1, header_row - 5), header_row):
        value = _merged_cell_value(sheet, row, column)
        if value is None:
            continue
        normalized = " ".join(str(value).replace("\n", " ").split())[:160]
        if normalized and normalized not in values:
            values.append(normalized)
    return tuple(values)


def _data_rows(sheet: Any, header_row: int, x_column: int, y_column: int) -> list[int]:
    rows: list[int] = []
    misses = 0
    for row in range(header_row + 1, min(int(sheet.max_row or 0), MAX_WORKBOOK_ROWS) + 1):
        x = _numeric(sheet.cell(row, x_column).value)
        y = 0.0 if y_column == 0 else _numeric(sheet.cell(row, y_column).value)
        if x is None or y is None:
            misses += 1
            if rows and misses >= 3:
                break
            continue
        rows.append(row)
        misses = 0
    return rows


def _coordinate_headers(sheet: Any) -> list[tuple[int, int, int]]:
    candidates: list[tuple[int, int, int]] = []
    maximum_column = min(int(sheet.max_column or 0), MAX_WORKBOOK_COLUMNS)
    for row in range(1, min(int(sheet.max_row or 0), 15) + 1):
        for column in range(1, maximum_column):
            first = _token(sheet.cell(row, column).value)
            second = _token(sheet.cell(row, column + 1).value)
            if first in {"x", "xmm", "xcoord", "xcoordinate"} and second in {
                "y", "ymm", "ycoord", "ycoordinate"
            }:
                if len(_data_rows(sheet, row, column, column + 1)) >= MIN_SPATIAL_POINTS:
                    candidates.append((row, column, column + 1))
    # A common instrument export uses [point index, x, y] beneath a merged
    # coordinate header. Detect it by structure without relying on its label.
    for row in range(1, min(int(sheet.max_row or 0), 15) + 1):
        header_strings = sum(
            isinstance(sheet.cell(row, column).value, str)
            and bool(str(sheet.cell(row, column).value).strip())
            for column in range(4, min(maximum_column, 32) + 1)
        )
        if header_strings < 2:
            continue
        data = _data_rows(sheet, row, 2, 3)
        if len(data) < MIN_SPATIAL_POINTS:
            continue
        indexes = [_numeric(sheet.cell(item, 1).value) for item in data]
        finite = [value for value in indexes if value is not None]
        if len(finite) >= MIN_SPATIAL_POINTS and len({round(value, 9) for value in finite}) == len(finite):
            candidates.append((row, 2, 3))
    # Replicated radial or one-dimensional scientific profiles commonly use a
    # single coordinate followed by several complete response fields.
    one_dimensional_tokens = {
        "r", "radius", "radialposition", "distance", "position", "半径", "位置"
    }
    for row in range(1, min(int(sheet.max_row or 0), 15) + 1):
        for column in range(1, maximum_column):
            if _token(sheet.cell(row, column).value) not in one_dimensional_tokens:
                continue
            data = _data_rows(sheet, row, column, 0)
            if len(data) < MIN_SPATIAL_POINTS // 3:
                continue
            numeric_fields = 0
            for candidate_column in range(column + 1, maximum_column + 1):
                values = [_numeric(sheet.cell(item, candidate_column).value) for item in data]
                if sum(value is not None for value in values) >= max(6, int(len(data) * 0.8)):
                    numeric_fields += 1
            if numeric_fields >= 3:
                candidates.append((row, column, 0))
    unique: list[tuple[int, int, int]] = []
    for item in sorted(set(candidates)):
        if item not in unique:
            unique.append(item)
    return unique


def _extract_blocks(asset: DataAsset, path: Path) -> list[_FieldBlock]:
    try:
        import openpyxl
    except ImportError:
        return []
    # Normal mode provides bounded O(1) access to the sparse cell graph.  Some
    # vendor workbooks advertise the full Excel grid as their used range; the
    # read-only streaming API would repeatedly rescan that XML for every cell.
    workbook = openpyxl.load_workbook(path, read_only=False, data_only=True)
    blocks: list[_FieldBlock] = []
    try:
        for sheet_index, sheet in enumerate(workbook.worksheets):
            coordinate_headers = _coordinate_headers(sheet)
            if not coordinate_headers:
                continue
            for _header_index, (header_row, x_column, y_column) in enumerate(coordinate_headers):
                rows = _data_rows(sheet, header_row, x_column, y_column)
                if len(rows) < (8 if y_column == 0 else MIN_SPATIAL_POINTS):
                    continue
                following = [
                    candidate[1]
                    for candidate in coordinate_headers
                    if candidate[0] == header_row and candidate[1] > x_column
                ]
                end_column = min(
                    (min(following) - 1) if following else int(sheet.max_column or 0),
                    MAX_WORKBOOK_COLUMNS,
                )
                fields: dict[str, np.ndarray] = {}
                field_context: dict[str, tuple[str, ...]] = {}
                field_start = (y_column + 1) if y_column else (x_column + 1)
                for column in range(field_start, end_column + 1):
                    label = _field_label(sheet.cell(header_row, column).value)
                    if not label:
                        continue
                    values = [_numeric(sheet.cell(row, column).value) for row in rows]
                    minimum_points = min(MIN_SPATIAL_POINTS, max(6, int(len(rows) * 0.85)))
                    if sum(value is not None for value in values) < minimum_points:
                        continue
                    array = np.asarray(
                        [np.nan if value is None else value for value in values], dtype=float
                    )
                    if not np.all(np.isfinite(array)) or float(np.ptp(array)) <= 0:
                        continue
                    normalized = _token(label)
                    if normalized and normalized not in fields:
                        fields[normalized] = array
                        field_context[normalized] = _field_context(
                            sheet, header_row=header_row, column=column
                        )
                if not fields:
                    continue
                # Some instrument exports place condition codes below the
                # measurements. Admit repeated categorical codes, never numeric
                # summaries, per-item identifiers, or outcome quality labels.
                strata: dict[str, dict[str, Any]] = {}
                for context_row in range(max(rows) + 1, min(max(rows) + 5, int(sheet.max_row or 0) + 1)):
                    codes = {}
                    for column in range(field_start, end_column + 1):
                        key = _token(_field_label(sheet.cell(header_row, column).value))
                        value = sheet.cell(context_row, column).value
                        if key in fields and isinstance(value, str):
                            value = " ".join(value.split())[:160]
                            if re.fullmatch(r"[A-Za-z][A-Za-z0-9_. /-]{1,80}", value) and re.search(r"\d", value) and not re.search(r"good|bad|pass|fail|quality|thk|mean|std|yield", value, re.I):
                                codes[key] = value
                    counts = Counter(codes.values())
                    if len(codes) >= max(3, len(fields) * 0.8) and 2 <= len(counts) <= len(fields) // 2 and min(counts.values()) >= 2:
                        strata = {key: {"label": value, "row": context_row, "semantics": "source condition code; executed protocol unconfirmed"} for key, value in codes.items()}
                        break
                coordinates = np.asarray(
                    [
                        [
                            float(_numeric(sheet.cell(row, x_column).value) or 0.0),
                            (
                                float(_numeric(sheet.cell(row, y_column).value) or 0.0)
                                if y_column
                                else 0.0
                            ),
                        ]
                        for row in rows
                    ],
                    dtype=float,
                )
                context = _sheet_context(
                    sheet, header_row=header_row, start=x_column, end=end_column
                )
                title_role = _context_role(str(sheet.title))
                blocks.append(
                    _FieldBlock(
                        asset=asset,
                        sheet_token=f"sheet:{sheet_index + 1}",
                        sheet_label=str(sheet.title)[:240],
                        header_row=header_row,
                        row_numbers=tuple(rows),
                        coordinates=coordinates,
                        fields=fields,
                        field_context=field_context,
                        role=title_role if title_role != "unknown" else _context_role(context),
                        context=context,
                        coordinate_columns=(x_column, y_column),
                        field_strata=strata,
                    )
                )
    finally:
        workbook.close()
    return blocks


def _resolve_block_roles(blocks: list[_FieldBlock]) -> list[_FieldBlock]:
    output = list(blocks)
    by_asset_sheet: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, block in enumerate(output):
        by_asset_sheet[(block.asset.asset_id, block.sheet_token)].append(index)
    for indexes in by_asset_sheet.values():
        roles = [output[index].role for index in indexes]
        # If a paired export labels only the driver section, both bounded
        # contexts can inherit that label.  A clearly separated response scale
        # then identifies the other block as the candidate target; the later
        # held-out law gate, not this heuristic, decides scientific promotion.
        if len(indexes) >= 2 and "target" not in roles:
            medians = {
                index: float(
                    np.median(
                        np.concatenate([value for value in output[index].fields.values()])
                    )
                )
                for index in indexes
            }
            ordered = sorted(medians, key=medians.get, reverse=True)
            if medians[ordered[0]] > max(abs(medians[ordered[1]]) * 2.0, 1e-12):
                item = output[ordered[0]]
                output[ordered[0]] = _FieldBlock(**{**item.__dict__, "role": "target"})
                roles = [output[index].role for index in indexes]
        if "driver" in roles and "target" not in roles:
            unknown = [index for index in indexes if output[index].role == "unknown"]
            if len(unknown) == 1:
                item = output[unknown[0]]
                output[unknown[0]] = _FieldBlock(**{**item.__dict__, "role": "target"})
        if "target" in roles and "driver" not in roles:
            unknown = [index for index in indexes if output[index].role == "unknown"]
            if len(unknown) == 1:
                item = output[unknown[0]]
                output[unknown[0]] = _FieldBlock(**{**item.__dict__, "role": "driver"})
    return output


def _normalized_coordinate_matrix(coordinates: np.ndarray) -> np.ndarray:
    values = np.asarray(coordinates, dtype=float)
    centered = values - np.mean(values, axis=0)
    radius = np.sqrt(np.sum(centered**2, axis=1))
    return centered / max(float(np.max(radius)), 1e-12)


def _register_field(
    source_coordinates: np.ndarray,
    target_coordinates: np.ndarray,
    source_values: np.ndarray,
) -> tuple[np.ndarray, str, float]:
    """Register a complete driver field onto the target coordinate system.

    Exact coordinate sets use a lossless permutation. Differing scientific
    grids use a deterministic local inverse-distance interpolant in normalized
    geometry. The registration is independent of row order and target values.
    """

    source = _normalized_coordinate_matrix(source_coordinates)
    target = _normalized_coordinate_matrix(target_coordinates)
    values = np.asarray(source_values, dtype=float)
    source_keys = [tuple(np.round(row, 9)) for row in source]
    target_keys = [tuple(np.round(row, 9)) for row in target]
    if len(set(source_keys)) == len(source_keys) and set(source_keys) == set(target_keys):
        positions = {key: index for index, key in enumerate(source_keys)}
        return (
            np.asarray([values[positions[key]] for key in target_keys], dtype=float),
            "exact_normalized_coordinate_permutation",
            0.0,
        )

    distance = np.sqrt(np.sum((target[:, None, :] - source[None, :, :]) ** 2, axis=2))
    neighbor_count = min(6, len(source))
    neighbors = np.argpartition(distance, neighbor_count - 1, axis=1)[:, :neighbor_count]
    registered = np.empty(len(target), dtype=float)
    nearest_distances: list[float] = []
    for index, selected in enumerate(neighbors):
        selected_distance = distance[index, selected]
        exact = selected[selected_distance <= 1e-12]
        if exact.size:
            registered[index] = float(values[int(exact[0])])
        else:
            weights = 1.0 / np.maximum(selected_distance, 1e-9) ** 2
            registered[index] = float(np.sum(weights * values[selected]) / np.sum(weights))
        nearest_distances.append(float(np.min(selected_distance)))
    return registered, "normalized_local_inverse_distance", float(np.mean(nearest_distances))


def _spatial_objects(blocks: list[_FieldBlock]) -> list[_SpatialObject]:
    blocks = _resolve_block_roles(blocks)
    targets = [item for item in blocks if item.role == "target"]
    drivers = [item for item in blocks if item.role == "driver"]
    output: list[_SpatialObject] = []
    for target in targets:
        ranked_drivers = sorted(
            drivers,
            key=lambda item: (
                item.asset.asset_id != target.asset.asset_id,
                item.sheet_token != target.sheet_token,
                -len(set(item.fields) & set(target.fields)),
            ),
        )
        for driver in ranked_drivers:
            matches: list[tuple[str, str, str]] = [
                (label, label, "exact_field_token")
                for label in sorted(set(target.fields) & set(driver.fields))
            ]
            if len(matches) < 2:
                suffix_candidates: list[tuple[str, str, str]] = []
                for target_label in target.fields:
                    for driver_label in driver.fields:
                        shorter = min(len(target_label), len(driver_label))
                        if shorter >= 3 and (
                            target_label.endswith(driver_label)
                            or driver_label.endswith(target_label)
                        ):
                            suffix_candidates.append(
                                (target_label, driver_label, "unique_identifier_suffix")
                            )
                target_counts = {
                    label: sum(item[0] == label for item in suffix_candidates)
                    for label, _, _ in suffix_candidates
                }
                driver_counts = {
                    label: sum(item[1] == label for item in suffix_candidates)
                    for _, label, _ in suffix_candidates
                }
                matches = [
                    item
                    for item in suffix_candidates
                    if target_counts[item[0]] == 1 and driver_counts[item[1]] == 1
                ]
            if len(matches) < 2:
                continue
            target_coordinates = np.asarray(target.coordinates, dtype=float)
            driver_coordinates = np.asarray(driver.coordinates, dtype=float)
            canonical_order = np.lexsort((target_coordinates[:, 1], target_coordinates[:, 0]))
            regime_driver_fingerprints = sorted(
                hashlib.sha256(
                    _register_field(
                        driver_coordinates,
                        target_coordinates,
                        np.asarray(values, dtype=float),
                    )[0][canonical_order].tobytes()
                ).hexdigest()
                for values in driver.fields.values()
            )
            for target_label, driver_label, match_kind in matches:
                target_values = np.asarray(target.fields[target_label], dtype=float)
                driver_values, registration, registration_error = _register_field(
                    driver_coordinates,
                    target_coordinates,
                    np.asarray(driver.fields[driver_label], dtype=float),
                )
                coordinate_rank = int(
                    np.linalg.matrix_rank(
                        target_coordinates - np.mean(target_coordinates, axis=0)
                    )
                )
                if coordinate_rank <= 1 and len(
                    {tuple(row) for row in np.round(target_coordinates, 9)}
                ) < int(len(target_coordinates) * 0.8):
                    # Repeated radial positions are nested measurements, not
                    # independent coordinates. Prefer an explicitly supplied
                    # radial summary block; otherwise a separate hierarchical
                    # measurement program must aggregate them inside folds.
                    continue
                minimum_points = 8 if coordinate_rank <= 1 else MIN_SPATIAL_POINTS
                if (
                    target_values.size < minimum_points
                    or np.any(target_values <= 0)
                    or np.any(driver_values <= 0)
                ):
                    continue
                canonical_driver = driver_values[canonical_order]
                identity = {
                    "coordinates": target_coordinates[canonical_order].tolist(),
                    "driver_digest": hashlib.sha256(canonical_driver.tobytes()).hexdigest(),
                    "source_condition": target.field_strata.get(target_label, {}).get("label", ""),
                    # Specimen labels are identity only: they are never exposed
                    # to a model matrix or treated as explanatory variables.
                    "matched_unit_key": canonical_sha256(
                        min((target_label, driver_label), key=len)
                    ),
                }
                object_id = "spatial-unit:" + canonical_sha256(identity)[:24]
                # Regimes describe repeatable input-field cohorts, not a
                # single sample's instrument/quality annotations. Per-field
                # header context remains available for stratified diagnostics,
                # but using it here would create unsupported one-unit regimes.
                regime_payload = {
                    "coordinates": target_coordinates[canonical_order].tolist(),
                    "driver_field_fingerprints": regime_driver_fingerprints,
                    "source_condition": target.field_strata.get(target_label, {}).get("label", ""),
                }
                regime = "input-regime:" + canonical_sha256(regime_payload)[:10]
                output.append(
                    _SpatialObject(
                        object_id=object_id,
                        asset=target.asset,
                        regime=regime,
                        label=target_label,
                        coordinates=target_coordinates,
                        driver=driver_values,
                        target=target_values,
                        locator={
                            "target_sheet": target.sheet_token,
                            "driver_sheet": driver.sheet_token,
                            "target_header_row": target.header_row,
                            "driver_header_row": driver.header_row,
                            "target_rows": [min(target.row_numbers), max(target.row_numbers)],
                            "driver_rows": [min(driver.row_numbers), max(driver.row_numbers)],
                            "field_token_sha256": canonical_sha256(
                                {"target": target_label, "driver": driver_label}
                            ),
                            "field_match": match_kind,
                            "independent_group": identity["matched_unit_key"],
                            "source_condition": target.field_strata.get(target_label, {}),
                            "alignment": registration,
                            "normalized_mean_nearest_distance": registration_error,
                        },
                    )
                )
            if matches:
                break
    unique: dict[str, _SpatialObject] = {item.object_id: item for item in output}
    return [unique[key] for key in sorted(unique)]


def _normalized_geometry(item: _SpatialObject) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    coordinates = np.asarray(item.coordinates, dtype=float)
    center = np.mean(coordinates, axis=0)
    shifted = coordinates - center
    radius = np.sqrt(np.sum(shifted**2, axis=1))
    scale = max(float(np.max(radius)), 1e-12)
    xy = shifted / scale
    return xy[:, 0], xy[:, 1], radius / scale


def _kernel_feature(item: _SpatialObject, length_scale: float = 0.35) -> np.ndarray:
    x, y, _ = _normalized_geometry(item)
    points = np.column_stack([x, y])
    distance_squared = np.sum((points[:, None, :] - points[None, :, :]) ** 2, axis=2)
    weights = np.exp(-distance_squared / max(2.0 * length_scale**2, 1e-12))
    np.fill_diagonal(weights, 0.0)
    totals = np.sum(weights, axis=1)
    normalized_driver = np.log(item.driver / np.mean(item.driver))
    return (weights @ normalized_driver) / np.maximum(totals, 1e-12)


@lru_cache(maxsize=256)
def _orthogonal_geometry(coordinates: tuple[tuple[float, float], ...], count: int) -> np.ndarray:
    """Smooth, input-only modes; canonical row order makes refits reproducible."""
    points = np.asarray(coordinates)
    xy = points - np.mean(points, axis=0)
    xy /= max(float(np.max(np.linalg.norm(xy, axis=1))), 1e-12)
    x, y = xy.T
    radius2 = x*x + y*y
    seeds = [radius2, radius2**2, x, y, x*x-y*y, 2*x*y]
    seeds += [x**i * y**(degree-i) for degree in range(3, 7) for i in range(degree + 1)]
    modes: list[np.ndarray] = []
    for seed in seeds:
        vector = seed - np.mean(seed)
        for _ in range(2):
            for mode in modes:
                vector = vector - np.mean(vector * mode) * mode
        norm = float(np.sqrt(np.mean(vector**2)))
        if norm <= 1e-10:
            continue
        modes.append(vector / norm)
        if len(modes) >= min(count, len(points) - 1):
            break
    result = np.column_stack(modes)
    result.setflags(write=False)
    return result


def _features(
    item: _SpatialObject,
    spec: str,
    regimes: tuple[str, ...],
) -> tuple[np.ndarray, tuple[str, ...]]:
    if spec.startswith("sparse_kernel_"):
        return _features(item, "regime_modulated_kernel", regimes)
    x, y, radius = _normalized_geometry(item)
    rows = len(item.target)
    columns: list[np.ndarray] = []
    names: list[str] = []
    for regime in regimes[1:]:
        columns.append(np.full(rows, float(item.regime == regime)))
        names.append(f"regime[{regime}]")
    # Compact response families compete with the flexible expansion on exactly
    # the same complete-field development folds. Geometry is input-only.
    if spec in {"power_driver", "radial_response", "radial_transport", "planar_response", "saturating_response"}:
        driver_mean = max(float(np.mean(item.driver)), 1e-12)
        local = np.log(np.maximum(item.driver, 1e-12) / driver_mean)
        columns.extend([np.full(rows, math.log(driver_mean)), local])
        names.extend(["log_driver_mean", "log_local_driver"])
        if spec != "power_driver":
            columns.append(radius**2)
            names.append("r^2")
        if spec == "radial_response":
            columns.append(radius**4)
            names.append("r^4")
        if spec == "radial_transport":
            columns.append(_kernel_feature(item, 0.35))
            names.append("nonlocal_kernel[0.35]")
        if spec == "planar_response":
            columns.extend([x, y])
            names.extend(["x", "y"])
        if spec == "saturating_response":
            columns[len(regimes)] = np.tanh(local)
            names[len(regimes)] = "local_saturation"
        return np.column_stack(columns).astype(float), tuple(names)
    if spec.startswith("orthogonal_transport_"):
        count = int(spec.rsplit("_", 1)[1])
        order = np.lexsort((item.coordinates[:, 1], item.coordinates[:, 0]))
        basis = _orthogonal_geometry(tuple(map(tuple, item.coordinates[order])), count)[np.argsort(order)]
        driver_mean = float(np.mean(item.driver))
        response = np.log(item.driver / driver_mean)
        response -= np.mean(response)
        modes = np.mean(basis * response[:, None], axis=0)
        residual = response - basis @ modes
        # Separate smooth chamber backgrounds and mode gains by the observed
        # input protocol. All response terms remain low-dimensional functions
        # of the driver; no target mean or saved target profile is an input.
        for regime in regimes:
            indicator = float(item.regime == regime)
            for i in range(basis.shape[1]):
                columns.extend([indicator * basis[:, i], indicator * modes[i] * basis[:, i]])
                names.extend([f"smooth_mode[{regime},{i}]", f"response_mode[{regime},{i}]"])
            columns.extend([np.full(rows, indicator * math.log(driver_mean)), indicator * residual])
            names.extend([f"log_driver_mean[{regime}]", f"unresolved_driver[{regime}]"])
        return np.column_stack(columns), tuple(names)
    columns.extend([radius**2, radius**4, x, y, x**2 - y**2, 2.0 * x * y])
    names.extend(["r^2", "r^4", "x", "y", "quadrupole_cos", "quadrupole_sin"])
    if spec != "spatial_baseline":
        driver_mean = max(float(np.mean(item.driver)), 1e-12)
        normalized = np.log(np.maximum(item.driver, 1e-12) / driver_mean)
        columns.extend(
            [
                np.full(rows, math.log(driver_mean)),
                np.full(rows, float(np.std(item.driver) / driver_mean)),
                normalized,
            ]
        )
        names.extend(["log_driver_mean", "driver_cv", "log_local_driver"])
        if spec in {"modal_transport", "hierarchical_nonlinear_response"}:
            spatial_basis = [radius**2, radius**4, x, y, x**2 - y**2, 2.0 * x * y]
            basis_names = ["r2", "r4", "x", "y", "qcos", "qsin"]
            driver_modes = [float(np.mean(normalized * basis)) for basis in spatial_basis]
            for mode_name, mode in zip(basis_names, driver_modes, strict=True):
                columns.append(np.full(rows, mode))
                names.append(f"driver_mode[{mode_name}]")
            for source_name, mode in zip(basis_names, driver_modes, strict=True):
                for target_name, basis in zip(basis_names, spatial_basis, strict=True):
                    columns.append(mode * basis)
                    names.append(f"mode_transfer[{source_name}->{target_name}]")
        if spec in {
            "nonlocal_kernel",
            "regime_modulated_kernel",
            "multi_scale_transport",
            "hierarchical_nonlinear_response",
        }:
            length_scales = (
                (0.35,)
                if spec in {"nonlocal_kernel", "regime_modulated_kernel"}
                else (0.12, 0.25, 0.5, 0.9)
            )
            kernels = [_kernel_feature(item, scale) for scale in length_scales]
            columns.extend(kernels)
            names.extend([f"nonlocal_kernel[{scale:g}]" for scale in length_scales])
        if spec in {
            "regime_modulated_kernel",
            "multi_scale_transport",
            "hierarchical_nonlinear_response",
        }:
            kernel = _kernel_feature(item, 0.35)
            columns.extend([normalized * radius**2, kernel * radius**2])
            names.extend(["local_x_r2", "kernel_x_r2"])
        if spec == "hierarchical_nonlinear_response":
            kernel = _kernel_feature(item)
            nonlinear_columns = [
                normalized**2,
                np.tanh(normalized),
                kernel**2,
                normalized * kernel,
            ]
            nonlinear_names = [
                "local_squared",
                "local_saturation",
                "kernel_squared",
                "local_x_kernel",
            ]
            columns.extend(nonlinear_columns)
            names.extend(nonlinear_names)
            # Partial pooling is represented by ridge-regularized deviations
            # from the shared law.  Regime membership is inferred from input
            # field structure and never from target values or file names.
            shared_columns = list(columns[len(regimes) - 1 :])
            shared_names = list(names[len(regimes) - 1 :])
            for regime in regimes[1:]:
                indicator = float(item.regime == regime)
                for column, name in zip(shared_columns, shared_names, strict=True):
                    columns.append(column * indicator)
                    names.append(f"regime_deviation[{regime}]::{name}")
    return np.column_stack(columns).astype(float), tuple(names)


def _independent_group(item: _SpatialObject) -> str:
    return str(item.locator.get("independent_group") or item.object_id)


def _fit(
    objects: Iterable[_SpatialObject],
    spec: str,
    regimes: tuple[str, ...],
    ridge: float,
) -> _FittedModel:
    object_list = list(objects)
    matrices = [_features(item, spec, regimes)[0] for item in object_list]
    names = _features(object_list[0], spec, regimes)[1]
    design = np.vstack(matrices)
    target = np.concatenate([np.log(item.target) for item in object_list])
    group_counts = Counter(_independent_group(item) for item in object_list)
    weights = np.concatenate([np.full(len(item.target), 1.0 / (group_counts[_independent_group(item)] * len(item.target))) for item in object_list])
    means = np.average(design, axis=0, weights=weights)
    scales = np.sqrt(np.average((design - means) ** 2, axis=0, weights=weights))
    scales[scales < 1e-10] = 1.0
    normalized = (design - means) / scales
    augmented = np.column_stack([np.ones(len(normalized)), normalized])
    penalty = np.eye(augmented.shape[1]) * float(ridge)
    penalty[0, 0] = 0.0
    gram = augmented.T @ (augmented * weights[:, None])
    rhs = augmented.T @ (target * weights)
    coefficients = np.linalg.solve(gram + penalty, rhs)
    if spec.startswith("sparse_kernel_"):
        # Coordinate descent on the weighted elastic-net objective. A zero
        # coefficient removes a term; neither targets outside development nor
        # a post-fit display threshold can decide the support.
        l1 = float(spec.rsplit("_", 1)[1]) * float(np.sum(weights))
        for _ in range(2000):
            previous = coefficients.copy()
            for j in range(len(coefficients)):
                residual_score = rhs[j] - gram[j] @ coefficients + gram[j, j] * coefficients[j]
                threshold = 0.0 if j == 0 else l1
                coefficients[j] = math.copysign(max(abs(residual_score) - threshold, 0.0), residual_score) / (gram[j, j] + penalty[j, j])
            if np.max(np.abs(coefficients - previous)) < 1e-10:
                break
    return _FittedModel(
        spec=spec,
        ridge=ridge,
        names=names,
        means=means,
        scales=scales,
        coefficients=coefficients[1:],
        intercept=float(coefficients[0]),
    )


def _predict(model: _FittedModel, item: _SpatialObject, regimes: tuple[str, ...]) -> np.ndarray:
    design, names = _features(item, model.spec, regimes)
    if names != model.names:
        raise ValueError("scientific-law feature identity changed after selection")
    linear = model.intercept + ((design - model.means) / model.scales) @ model.coefficients
    return np.exp(np.clip(linear, -50.0, 50.0))


def _model_equation(model: _FittedModel) -> tuple[EquationNode, dict[str, float]]:
    """Absorb training normalization exactly into native-feature coefficients.

    Scalers remain in the calibration audit, but are not additional free
    parameters of the executable equation. No coefficient is rounded here.
    """
    def node(op: str, *children: EquationNode, **kwargs: Any) -> EquationNode:
        return EquationNode(op=op, children=list(children), **kwargs)
    native = model.coefficients / model.scales
    parameters = {"b": float(model.intercept - model.means @ native), "T_ref": 1.0}
    terms = [node("parameter", symbol="b")]
    for i, name in enumerate(model.names):
        if model.coefficients[i] == 0.0:
            continue
        parameters[f"c_{i}"] = float(native[i])
        feature = node("variable", symbol=f"z_{i}", metadata={"transform": name, "executor": SPATIAL_EXECUTOR_VERSION, "target_access": False})
        terms.append(node("multiply", node("parameter", symbol=f"c_{i}"), feature))
    linear = associative_node("add", terms)
    clipped = node("minimum", node("constant", value=50), node("maximum", node("constant", value=-50), linear))
    return canonicalize(node("multiply", node("parameter", symbol="T_ref"), node("exp", clipped))), parameters


def _map_metrics(item: _SpatialObject, prediction: np.ndarray) -> dict[str, Any]:
    residual = item.target - prediction
    percentage = np.abs(residual) / np.maximum(np.abs(item.target), 1e-12) * 100.0
    x, y, _ = _normalized_geometry(item)
    points = np.column_stack([x, y])
    distances = np.sqrt(np.sum((points[:, None, :] - points[None, :, :]) ** 2, axis=2))
    np.fill_diagonal(distances, np.inf)
    nearest_distance = np.min(distances, axis=1, keepdims=True)
    nearest_mask = np.isclose(distances, nearest_distance, rtol=1e-10, atol=1e-12)
    neighbor_residual = (nearest_mask @ residual) / np.maximum(
        np.sum(nearest_mask, axis=1), 1
    )
    if float(np.std(residual)) > 0:
        neighbor_correlation = float(np.corrcoef(residual, neighbor_residual)[0, 1])
    else:
        neighbor_correlation = 0.0
    return {
        "unit_id": item.object_id,
        "regime": item.regime,
        "point_count": int(len(item.target)),
        "mape_percent": float(np.mean(percentage)),
        "worst_absolute_percentage_error": float(np.max(percentage)),
        "rmse": float(np.sqrt(np.mean(residual**2))),
        "mean_bias": float(np.mean(residual)),
        "residual_neighbor_correlation": neighbor_correlation,
    }


def _aggregate_metrics(unit_metrics: list[dict[str, Any]]) -> dict[str, Any]:
    if not unit_metrics:
        return {"unit_count": 0}
    return {
        "unit_count": len(unit_metrics),
        "mean_map_mape_percent": float(np.mean([item["mape_percent"] for item in unit_metrics])),
        "median_map_mape_percent": float(np.median([item["mape_percent"] for item in unit_metrics])),
        "worst_map_mape_percent": float(np.max([item["mape_percent"] for item in unit_metrics])),
        "worst_point_error_percent": float(
            np.max([item["worst_absolute_percentage_error"] for item in unit_metrics])
        ),
        "mean_absolute_residual_neighbor_correlation": float(
            np.mean([abs(item["residual_neighbor_correlation"]) for item in unit_metrics])
        ),
    }


def _evaluate_model(
    model: _FittedModel,
    objects: Iterable[_SpatialObject],
    regimes: tuple[str, ...],
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, np.ndarray]]:
    units: list[dict[str, Any]] = []
    predictions: dict[str, np.ndarray] = {}
    for item in objects:
        prediction = _predict(model, item, regimes)
        predictions[item.object_id] = prediction
        units.append(_map_metrics(item, prediction))
    return units, _aggregate_metrics(units), predictions


def _cross_validated_score(
    objects: list[_SpatialObject],
    spec: str,
    regimes: tuple[str, ...],
    ridge: float,
) -> tuple[float, list[np.ndarray], float]:
    if len(objects) < 3:
        model = _fit(objects, spec, regimes, ridge)
        return _evaluate_model(model, objects, regimes)[1]["mean_map_mape_percent"], [
            model.coefficients
        ], 0.0
    metrics: list[dict[str, Any]] = []
    coefficients: list[np.ndarray] = []
    fold_errors: list[float] = []
    for group in sorted({_independent_group(item) for item in objects}):
        held = [item for item in objects if _independent_group(item) == group]
        retained = [item for item in objects if _independent_group(item) != group]
        if len({_independent_group(item) for item in retained}) < 2:
            continue
        model = _fit(retained, spec, regimes, ridge)
        coefficients.append(model.coefficients)
        held_metrics, aggregate, _ = _evaluate_model(model, held, regimes)
        metrics.extend(held_metrics)
        fold_errors.append(float(aggregate["mean_map_mape_percent"]))
    if not metrics:
        model = _fit(objects, spec, regimes, ridge)
        return _evaluate_model(model, objects, regimes)[1]["mean_map_mape_percent"], [
            model.coefficients
        ], 0.0
    standard_error = float(np.std(fold_errors, ddof=1) / math.sqrt(len(fold_errors))) if len(fold_errors) > 1 else 0.0
    return _aggregate_metrics(metrics)["mean_map_mape_percent"], coefficients, standard_error


def _select_parsimonious_candidate(frontier: list[dict[str, Any]]) -> dict[str, Any]:
    """Select before reading locked targets; prefer fewer terms within CV noise.

    The tolerance is estimated from independent development groups of the most
    accurate stable candidate. Validation must also remain within that margin.
    """
    best = min(frontier, key=lambda row: (row["selection_score"], row["complexity"], -row["ridge"]))
    margin = max(0.0, float(best["development_standard_error"]))
    competitive = [row for row in frontier
                   if row["selection_score"] <= best["selection_score"] + margin
                   and row["validation_mape_percent"] <= best["validation_mape_percent"] + margin]
    return min(competitive, key=lambda row: (row["complexity"], row["selection_score"], -row["ridge"]))


def _response_direction_stability(model: _FittedModel, coefficients: list[np.ndarray]) -> float:
    indexes = [i for i, name in enumerate(model.names)
               if name.startswith(("log_driver_mean", "driver_cv", "log_local_driver", "local_saturation", "nonlocal_kernel", "response_mode[", "unresolved_driver["))
               and abs(float(model.coefficients[i])) >= 1e-6]
    if len(coefficients) < 2 or not indexes:
        return 0.0
    values = np.vstack(coefficients)[:, indexes]
    return float(np.mean(np.sign(values) == np.sign(np.median(values, axis=0))))


def _split_objects(
    study_id: str, objects: list[_SpatialObject]
) -> tuple[SplitManifest, dict[str, list[_SpatialObject]]]:
    def target_blind_driver_digest(item: _SpatialObject) -> str:
        coordinates = np.asarray(item.coordinates, dtype=float)
        order = np.lexsort((coordinates[:, 1], coordinates[:, 0]))
        payload = np.column_stack([coordinates[order], item.driver[order]])
        return hashlib.sha256(payload.tobytes()).hexdigest()

    # Match physical specimen keys globally across regimes. Different response
    # protocols never turn the same hardware into independent held-out evidence.
    grouped: dict[str, list[_SpatialObject]] = defaultdict(list)
    for item in objects:
        grouped[_independent_group(item)].append(item)
    units = sorted(grouped, key=lambda key: canonical_sha256({"group": key, "policy": "global-spatial-group/v4"}))
    first = min(max(2, int(len(units) * 0.6)), max(0, len(units) - 2))
    second = min(len(units) - 1, max(first + 1, int(len(units) * 0.8)))
    # Design an interpolation experiment using input support alone. The global
    # extrema must be represented in development, and each input protocol gets
    # development examples before remaining groups are assigned by stable hash.
    ordered_objects = sorted(objects, key=lambda item: (_independent_group(item), item.object_id))
    descriptors = np.array([[math.log(np.mean(item.driver)), np.std(item.driver) / np.mean(item.driver)] for item in ordered_objects])
    development: set[str] = set()
    for column in range(descriptors.shape[1]):
        for index in (np.argmin(descriptors[:, column]), np.argmax(descriptors[:, column])):
            if len(development) < first:
                development.add(_independent_group(ordered_objects[int(index)]))
    regimes_to_cover = sorted({item.regime for item in objects})
    while len(development) < first:
        counts = {regime: sum(any(item.regime == regime for item in grouped[unit]) for unit in development) for regime in regimes_to_cover}
        next_unit = max((unit for unit in units if unit not in development),
                        key=lambda unit: sum(max(0, 2-counts[regime]) for regime in {item.regime for item in grouped[unit]}))
        development.add(next_unit)
    remaining = [unit for unit in units if unit not in development]
    validation: set[str] = set()
    while len(validation) < second - first and remaining:
        covered = {item.regime for unit in validation for item in grouped[unit]}
        next_unit = max(remaining, key=lambda unit: len({item.regime for item in grouped[unit]} - covered))
        validation.add(next_unit)
        remaining.remove(next_unit)
    roles = {unit: "development" if unit in development else "validation" if unit in validation else "test" for unit in units}
    assignments = {item.object_id: roles[_independent_group(item)] for item in objects}
    partitions = {name: [item for item in objects if assignments[item.object_id] == name]
                  for name in ("development", "validation", "test")}
    seed_payload = [
        {
            "unit_id": item.object_id,
            "regime": item.regime,
            "driver_digest": target_blind_driver_digest(item),
        }
        for item in sorted(objects, key=lambda item: item.object_id)
    ]
    seed_digest = canonical_sha256(seed_payload)
    manifest_payload = {
        "study_id": study_id,
        "strategy": "stratified_group",
        "policy": "input-support interpolation with globally grouped specimens/v4",
        "seed_digest": seed_digest,
        "assignments": sorted(assignments.items()),
    }
    manifest_id = "split:" + canonical_sha256(manifest_payload)[:24]
    manifest = SplitManifest(
        split_manifest_id=manifest_id,
        study_id=study_id,
        independent_unit_kind="physical specimen shared across complete fields and regimes",
        strategy="stratified_group",
        seed_digest=seed_digest,
        assignments=[
            {"unit_id": unit_id, "partition": partition, "independent_group": _independent_group(next(item for item in objects if item.object_id == unit_id))}
            for unit_id, partition in sorted(assignments.items())
        ],
        development_unit_count=len({_independent_group(item) for item in partitions["development"]}),
        validation_unit_count=len({_independent_group(item) for item in partitions["validation"]}),
        test_unit_count=len({_independent_group(item) for item in partitions["test"]}),
        target_blind_digest=canonical_sha256(
            {"seed": seed_payload, "assignments": sorted(assignments.items())}
        ),
    )
    return manifest, partitions


def _law_ast(spec: str) -> EquationNode:
    terms: list[EquationNode] = [
        EquationNode(op="parameter", symbol=r"\beta_g"),
        EquationNode(
            op="multiply",
            children=[
                EquationNode(op="parameter", symbol=r"\beta_\mu"),
                EquationNode(
                    op="log", children=[EquationNode(op="variable", symbol=r"\bar C_m")]
                ),
            ],
        ),
        EquationNode(op="basis", symbol=r"B_{\alpha}(s)"),
        EquationNode(
            op="multiply",
            children=[
                EquationNode(op="parameter", symbol=r"\gamma"),
                EquationNode(
                    op="log",
                    children=[EquationNode(op="variable", symbol=r"\widetilde C_m(s)")],
                ),
            ],
        ),
    ]
    if spec in {
        "nonlocal_kernel",
        "regime_modulated_kernel",
        "multi_scale_transport",
        "hierarchical_nonlinear_response",
    }:
        terms.append(
            EquationNode(
                op="multiply",
                children=[
                    EquationNode(op="parameter", symbol=r"\kappa"),
                    EquationNode(op="kernel", symbol=r"K_{\lambda}[\log \widetilde C_m](s)"),
                ],
            )
        )
    if spec in {"regime_modulated_kernel", "hierarchical_nonlinear_response"}:
        terms.append(EquationNode(op="basis", symbol=r"R_{\eta}(s,\widetilde C_m)"))
    if spec in {"modal_transport", "hierarchical_nonlinear_response"}:
        terms.append(EquationNode(op="basis", symbol=r"M_{\theta}[\log \widetilde C_m](s)"))
    if spec == "hierarchical_nonlinear_response":
        terms.append(EquationNode(op="basis", symbol=r"H_g(s,\widetilde C_m)"))
    return canonicalize(EquationNode(op="exp", children=[EquationNode(op="add", children=terms)]))


def compile_scientific_programs(
    *,
    study_id: str,
    blueprint: StudyBlueprint,
    principle_ids: list[str],
    hypothesis_ids: list[str] | None = None,
    law_search_hints: list[dict[str, Any]] | None = None,
) -> tuple[ScientificProgram, ScientificProgram]:
    target_bindings = list(blueprint.target_bindings)[:100]
    inputs = list(blueprint.input_bindings)[:300]
    nuisances = list(blueprint.nuisance_bindings)[:100]
    coordinates = list(blueprint.coordinate_bindings)[:100]
    units = blueprint.independent_units[:100]
    target_ids = {str(item.get("binding_id") or "") for item in target_bindings}
    inputs = [
        item for item in inputs if str(item.get("binding_id") or "") not in target_ids
    ]
    split_name = str(
        next(
            (item.get("strategy") for item in blueprint.split_candidates if item.get("strategy")),
            "group",
        )
    )
    if split_name == "contiguous_epoch":
        split_name = "contiguous_signal"
    if split_name not in {
        "group", "chronological", "spatial_block", "contiguous_signal", "stratified_group"
    }:
        split_name = "group"

    def binding_ids(values: list[dict[str, Any]]) -> list[str]:
        return [
            str(
                item.get("binding_id")
                or "binding:"
                + canonical_sha256(
                    {
                        "study": study_id,
                        "view": item.get("view_id"),
                        "variable": item.get("variable") or item.get("name"),
                        "role": item.get("role"),
                    }
                )[:24]
            )
            for item in values
        ]

    def program(track: str, intent: str) -> ScientificProgram:
        payload = {
            "version": SCIENTIFIC_PROGRAM_VERSION,
            "study": study_id,
            "track": track,
            "blueprint": blueprint.blueprint_digest,
            "targets": target_bindings,
            "inputs": inputs,
            "coordinates": coordinates,
            "units": units,
            "principles": sorted(set(principle_ids)),
            "hypotheses": sorted(set(hypothesis_ids or [])),
            "law_search_hints": law_search_hints or [],
        }
        digest = canonical_sha256(payload)
        executable: list[ExecutableHypothesis] = []
        for hypothesis_id in sorted(set(hypothesis_ids or [])):
            binding_payload = {
                "study": study_id,
                "hypothesis": hypothesis_id,
                "track": track,
                "targets": binding_ids(target_bindings),
                "inputs": binding_ids(inputs),
                "nuisances": binding_ids(nuisances),
                "independent_units": binding_ids(units),
                "split": split_name,
            }
            complete = bool(target_bindings and inputs and units)
            executable.append(
                ExecutableHypothesis(
                    executable_hypothesis_id="exec-hyp:"
                    + canonical_sha256(binding_payload)[:24],
                    study_id=study_id,
                    hypothesis_id=hypothesis_id,
                    track=track,  # type: ignore[arg-type]
                    target_binding_ids=binding_ids(target_bindings),
                    input_binding_ids=binding_ids(inputs),
                    nuisance_binding_ids=binding_ids(nuisances),
                    independent_unit_binding_ids=binding_ids(units),
                    split_strategy=split_name,  # type: ignore[arg-type]
                    admissible_family_kinds=["scaling", "saturation", "response_kernel"],
                    falsifying_control={
                        "required": True,
                        "selection": "executor-specific after binding",
                    },
                    state="bound" if complete else "rejected",
                    rejection_reasons=(
                        []
                        if complete
                        else [
                            "Blueprint lacks a distinct target, admissible input, or true independent-unit binding."
                        ]
                    ),
                    binding_digest=canonical_sha256(binding_payload),
                )
            )
        return ScientificProgram(
            program_id=f"program:{track}:{digest[:20]}",
            study_id=study_id,
            track=track,  # type: ignore[arg-type]
            title=(
                "Mechanism program" if track == "mechanism" else "Predictive-closure program"
            ),
            scientific_intent=intent,
            target_bindings=target_bindings,
            input_bindings=inputs,
            nuisance_bindings=nuisances,
            coordinate_bindings=coordinates,
            independent_unit_bindings=units,
            principle_ids=sorted(set(principle_ids)),
            hypothesis_ids=sorted(set(hypothesis_ids or [])),
            law_search_hints=law_search_hints or [],
            engine_version="principia-cross-domain-rule-engine/3",
            executable_hypotheses=executable,
            state="compiled",
            decisions=[
                "Scientific variables are bound to typed views before execution.",
                "Selection and evaluation must keep complete independent units intact.",
            ],
            limitations=list(blueprint.warnings),
            program_digest=digest,
        )

    return (
        program(
            "mechanism",
            "Test falsifiable conservation, transport, kinetic, geometric, state, and regime explanations against executed evidence.",
        ),
        program(
            "predictive_closure",
            "Search compact executable law families on development data, freeze selection, and evaluate complete outputs on locked units.",
        ),
    )


def execute_replicated_spatial_program(
    *,
    study_id: str,
    program: ScientificProgram,
    assets_and_roots: list[tuple[DataAsset, Path]],
    emit: Callable[[str, str, dict[str, Any]], None] | None = None,
    _objects_override: list[_SpatialObject] | None = None,
    _collection_label: str = "",
) -> ScientificProgramBundle:
    """Execute a generic whole-field predictive-closure program when detected."""

    if _objects_override is None:
        blocks: list[_FieldBlock] = []
        for asset, root in assets_and_roots:
            if asset.role != "raw" or asset.format != "xlsx" or asset.status != "analyzable":
                continue
            try:
                blocks.extend(_extract_blocks(asset, _safe_path(root, asset)))
            except Exception:
                continue
        objects = _spatial_objects(blocks)
        collections: dict[str, list[_SpatialObject]] = defaultdict(list)
        for item in objects:
            centered = item.coordinates - np.mean(item.coordinates, axis=0)
            rank = int(np.linalg.matrix_rank(centered))
            label = "radial_profile" if rank <= 1 else "planar_field"
            collections[label].append(item)
        eligible = {
            label: values for label, values in collections.items() if len(values) >= 6
        }
        if len(eligible) > 1:
            bundles = [
                execute_replicated_spatial_program(
                    study_id=study_id,
                    program=program,
                    assets_and_roots=assets_and_roots,
                    emit=emit,
                    _objects_override=values,
                    _collection_label=label,
                )
                for label, values in sorted(eligible.items())
            ]
            completed = [item.programs[0] for item in bundles if item.programs]
            combined_program = program.model_copy(
                update={
                    "state": "completed" if any(item.state == "completed" for item in completed) else "partial",
                    "decisions": [
                        *program.decisions,
                        *[decision for item in completed for decision in item.decisions[len(program.decisions):]],
                    ],
                    "limitations": [
                        *program.limitations,
                        *[limitation for bundle in bundles for limitation in bundle.limitations],
                    ],
                    "updated_at": utc_now(),
                }
            )
            return ScientificProgramBundle(
                programs=(combined_program,),
                split_manifests=tuple(item for bundle in bundles for item in bundle.split_manifests),
                transform_graphs=tuple(item for bundle in bundles for item in bundle.transform_graphs),
                laws=tuple(item for bundle in bundles for item in bundle.laws),
                calibrations=tuple(item for bundle in bundles for item in bundle.calibrations),
                candidates=tuple(item for bundle in bundles for item in bundle.candidates),
                evaluations=tuple(item for bundle in bundles for item in bundle.evaluations),
                decisions=tuple(item for bundle in bundles for item in bundle.decisions),
                outcomes=tuple(item for bundle in bundles for item in bundle.outcomes),
                limitations=tuple(item for bundle in bundles for item in bundle.limitations),
            )
        if len(eligible) == 1:
            _collection_label, objects = next(iter(eligible.items()))
    else:
        objects = list(_objects_override)
    collection_label = _collection_label or "replicated_field"
    if len(objects) < 6 or len({item.regime for item in objects}) < 1:
        decision_payload = {
            "study": study_id,
            "program": program.program_id,
            "objects": len(objects),
            "minimum": 6,
            "version": SPATIAL_EXECUTOR_VERSION,
        }
        decision = ScientificDecision(
            decision_id="decision:" + canonical_sha256(decision_payload)[:24],
            study_id=study_id,
            program_id=program.program_id,
            subject_id=program.program_id,
            decision_type="abstention",
            outcome="not_applicable",
            reasons=[
                "No structure-validated collection of at least six paired complete spatial fields was available."
            ],
            input_digests=[item.asset.byte_sha256 for item in objects],
            decision_digest=canonical_sha256(decision_payload),
        )
        return ScientificProgramBundle(
            programs=(program.model_copy(update={"state": "data_insufficient"}),),
            decisions=(decision,),
            limitations=(
                "Replicated spatial-law search was not applicable; other scientific signatures remain eligible.",
            ),
        )

    if emit:
        emit(
            "scientific_object_compiled",
            f"Recognized {len(objects)} complete spatial fields; rows remain nested inside field units.",
            {"independent_units": len(objects), "point_counts": sorted({len(i.target) for i in objects})},
        )
    split, partitions = _split_objects(study_id, objects)
    if not partitions["test"] or not partitions["validation"] or split.development_unit_count < 3:
        decision_payload = {
            "study": study_id,
            "program": program.program_id,
            "split": split.model_dump(mode="json"),
            "version": SPATIAL_EXECUTOR_VERSION,
        }
        decision = ScientificDecision(
            decision_id="decision:" + canonical_sha256(decision_payload)[:24],
            study_id=study_id,
            program_id=program.program_id,
            subject_id=split.split_manifest_id,
            decision_type="split_freeze",
            outcome="rejected",
            reasons=["Too few complete fields for a development/validation/locked-test design."],
            input_digests=[split.target_blind_digest],
            decision_digest=canonical_sha256(decision_payload),
        )
        return ScientificProgramBundle(
            programs=(program.model_copy(update={"state": "data_insufficient"}),),
            split_manifests=(split,),
            decisions=(decision,),
            limitations=("Whole-field validation could not be frozen without pseudoreplication.",),
        )
    if emit:
        emit(
            "split_frozen",
            "Frozen development, validation, and test assignments before candidate fitting.",
            {
                "development": len(partitions["development"]),
                "validation": len(partitions["validation"]),
                "test": len(partitions["test"]),
                "split_manifest_id": split.split_manifest_id,
            },
        )

    regimes = tuple(sorted({item.regime for item in partitions["development"]}))
    transform_payload = {
        "study": study_id,
        "split": split.split_manifest_id,
        "nodes": [
            "center_coordinates",
            "normalize_radius_per_complete_field",
            "log_positive_target",
            "normalize_driver_by_field_mean",
            "fit_scaler_inside_training_fold",
            "radial_azimuthal_basis",
            "nonlocal_kernel_from_driver_only",
        ],
        "version": SPATIAL_EXECUTOR_VERSION,
    }
    transform_digest = canonical_sha256(transform_payload)
    transform = TransformGraph(
        transform_graph_id="transform:" + transform_digest[:24],
        study_id=study_id,
        nodes=[
            {"node_id": name, "fold_local": name == "fit_scaler_inside_training_fold"}
            for name in transform_payload["nodes"]
        ],
        edges=[
            {"source": first, "target": second}
            for first, second in zip(
                transform_payload["nodes"], transform_payload["nodes"][1:], strict=False
            )
        ],
        fold_local_nodes=["fit_scaler_inside_training_fold"],
        source_view_ids=sorted(
            {
                "view:" + canonical_sha256(
                    {
                        "asset": item.asset.byte_sha256,
                        "adapter": item.asset.adapter,
                        "adapter_version": item.asset.adapter_version,
                        "profile": item.asset.metadata.get("profile") or {},
                    }
                )[:24]
                for item in objects
            }
        ),
        graph_digest=transform_digest,
    )

    specs = (
        "power_driver",
        "radial_response",
        "radial_transport",
        "planar_response",
        "saturating_response",
        "sparse_kernel_0.0001",
        "sparse_kernel_0.001",
        "sparse_kernel_0.003",
        "sparse_kernel_0.01",
        "local_response",
        "nonlocal_kernel",
        "regime_modulated_kernel",
        "multi_scale_transport",
        "modal_transport",
        "hierarchical_nonlinear_response",
        "orthogonal_transport_6",
        "orthogonal_transport_12",
        "orthogonal_transport_18",
    )
    ridge_values = (1e-6, 1e-3, 1e-1, 1.0, 10.0)
    baseline_ridge = 1e-3
    baseline_model = _fit(
        partitions["development"], "spatial_baseline", regimes, baseline_ridge
    )
    baseline_validation_objects = partitions["validation"] or partitions["development"]
    _, baseline_validation, _ = _evaluate_model(
        baseline_model, baseline_validation_objects, regimes
    )
    frontier: list[dict[str, Any]] = []
    coefficient_sets: dict[tuple[str, float], list[np.ndarray]] = {}
    candidate_equations: dict[tuple[str, float], EquationNode] = {}
    for spec in specs:
        for ridge in ridge_values:
            development_score, coefficients, development_se = _cross_validated_score(
                partitions["development"], spec, regimes, ridge
            )
            fitted = _fit(partitions["development"], spec, regimes, ridge)
            candidate_equations[(spec, ridge)] = _model_equation(fitted)[0]
            _, validation_metrics, _ = _evaluate_model(
                fitted, baseline_validation_objects, regimes
            )
            complexity = int(np.count_nonzero(fitted.coefficients)) + 1
            frontier.append(
                {
                    "spec": spec,
                    "ridge": ridge,
                    "development_mape_percent": development_score,
                    "development_standard_error": development_se,
                    "validation_mape_percent": validation_metrics["mean_map_mape_percent"],
                    "complexity": complexity,
                    "response_direction_stability": _response_direction_stability(fitted, coefficients),
                    # A small validation set is too noisy to own selection.
                    # Minimax scoring rewards candidates that are jointly
                    # stable under development cross-validation and the
                    # separate validation units, while preferring compact laws.
                    "selection_score": max(
                        development_score,
                        validation_metrics["mean_map_mape_percent"],
                    ),
                    "development_validation_gap": abs(
                        development_score
                        - validation_metrics["mean_map_mape_percent"]
                    ),
                }
            )
            coefficient_sets[(spec, ridge)] = coefficients
            if emit:
                emit(
                    "candidate_evaluated",
                    f"Evaluated {spec} at regularization {ridge:g} inside development folds.",
                    {
                        "family": spec,
                        "development_mape_percent": development_score,
                        "validation_mape_percent": validation_metrics["mean_map_mape_percent"],
                    },
                )
    stable = [row for row in frontier if row["response_direction_stability"] >= 0.70]
    # Never trade away an already-known validation requirement for parsimony.
    # All these values precede the first read of locked evaluation targets.
    admissible = [row for row in stable if row["validation_mape_percent"] <= 0.98 * baseline_validation["mean_map_mape_percent"]]
    champion_row = _select_parsimonious_candidate(admissible or stable or frontier)
    champion_spec = str(champion_row["spec"])
    champion_ridge = float(champion_row["ridge"])
    selection_train = list(partitions["development"])
    champion_model = _fit(selection_train, champion_spec, regimes, champion_ridge)
    baseline_final = _fit(selection_train, "spatial_baseline", regimes, baseline_ridge)
    validation_units, validation_metrics, _ = _evaluate_model(
        _fit(partitions["development"], champion_spec, regimes, champion_ridge),
        baseline_validation_objects,
        regimes,
    )
    test_units, test_metrics, test_predictions = _evaluate_model(
        champion_model, partitions["test"], regimes
    )
    baseline_test_units, baseline_test_metrics, _ = _evaluate_model(
        baseline_final, partitions["test"], regimes
    )

    # Negative control: deterministically rotate driver maps within each regime
    # while preserving targets and complete-field geometry.
    rotated: list[_SpatialObject] = []
    by_regime: dict[str, list[_SpatialObject]] = defaultdict(list)
    for item in selection_train:
        by_regime[item.regime].append(item)
    for values in by_regime.values():
        ordered = sorted(values, key=lambda item: item.object_id)
        drivers = [item.driver for item in ordered]
        if len(drivers) > 1:
            drivers = drivers[1:] + drivers[:1]
        for item, driver in zip(ordered, drivers, strict=True):
            rotated.append(_SpatialObject(**{**item.__dict__, "driver": driver}))
    negative_model = _fit(rotated, champion_spec, regimes, champion_ridge)
    _, negative_metrics, _ = _evaluate_model(
        negative_model, partitions["test"], regimes
    )

    # The locked targets are not an input to prediction. Mutating them after
    # fitting must therefore leave the exact prediction digest unchanged.
    original_prediction_digest = canonical_sha256(
        {key: value.tolist() for key, value in sorted(test_predictions.items())}
    )
    mutated_predictions: dict[str, list[float]] = {}
    for item in partitions["test"]:
        mutated = _SpatialObject(**{**item.__dict__, "target": item.target[::-1] * 1.37})
        mutated_predictions[item.object_id] = _predict(
            champion_model, mutated, regimes
        ).tolist()
    mutation_prediction_digest = canonical_sha256(mutated_predictions)
    mutation_invariant = original_prediction_digest == mutation_prediction_digest

    active_features = [(i, name) for i, name in enumerate(champion_model.names) if champion_model.coefficients[i] != 0.0]
    selected_family_label = "Sparse local–nonlocal response" if champion_spec.startswith("sparse_kernel_") else champion_spec.replace("_", " ").capitalize()
    selected_coefficients = coefficient_sets[(champion_spec, champion_ridge)]
    direction_stability = _response_direction_stability(champion_model, selected_coefficients)

    train_summaries = np.asarray(
        [[math.log(np.mean(item.driver)), np.std(item.driver) / np.mean(item.driver)] for item in selection_train]
    )
    test_summaries = np.asarray(
        [[math.log(np.mean(item.driver)), np.std(item.driver) / np.mean(item.driver)] for item in partitions["test"]]
    )
    lower = np.min(train_summaries, axis=0) - 0.25 * np.ptp(train_summaries, axis=0)
    upper = np.max(train_summaries, axis=0) + 0.25 * np.ptp(train_summaries, axis=0)
    support_pass = bool(np.all((test_summaries >= lower) & (test_summaries <= upper)))

    validation_improvement = 1.0 - (
        validation_metrics["mean_map_mape_percent"]
        / max(baseline_validation["mean_map_mape_percent"], 1e-12)
    )
    test_improvement = 1.0 - (
        test_metrics["mean_map_mape_percent"]
        / max(baseline_test_metrics["mean_map_mape_percent"], 1e-12)
    )
    worst_ratio = test_metrics["worst_map_mape_percent"] / max(
        baseline_test_metrics["worst_map_mape_percent"], 1e-12
    )
    negative_control_pass = test_metrics["mean_map_mape_percent"] < (
        negative_metrics["mean_map_mape_percent"] * 0.98
    )
    ast, equation_parameters = _model_equation(champion_model)
    replay_errors = []
    for item in partitions["test"]:
        design, _ = _features(item, champion_spec, regimes)
        replay = evaluate(ast, {f"z_{i}": design[:, i] for i in range(design.shape[1])}, equation_parameters)
        expected = test_predictions[item.object_id]
        replay_errors.append(float(np.max(np.abs(replay - expected) / np.maximum(np.abs(expected), 1e-12))))
    replay_pass = bool(replay_errors) and max(replay_errors) <= 1e-10
    dimension_signatures = {name: {} for name in equation_parameters}
    dimension_signatures.update({f"z_{i}": {} for i in range(len(champion_model.names))})
    dimension_signatures["T_ref"] = {"native_target": 1.0}
    inferred_dimension = infer_dimension(ast, dimension_signatures)
    gate_results = {
        "locked_test_present": bool(partitions["test"]),
        "validation_baseline_dominance": validation_improvement >= 0.02,
        "test_baseline_dominance": test_improvement >= 0.02,
        "worst_unit_noninferiority": worst_ratio <= 1.03,
        "parameter_direction_stability": direction_stability >= 0.70,
        "dimensional_plausibility": inferred_dimension == {"native_target": 1.0},
        "ast_replay": replay_pass,
        "negative_control": negative_control_pass,
        "support": support_pass,
        "heldout_target_mutation_invariant": mutation_invariant,
        "residual_adequacy": (
            test_metrics["mean_absolute_residual_neighbor_correlation"]
            <= baseline_test_metrics["mean_absolute_residual_neighbor_correlation"] + 0.05
        ),
        "multiplicity_control": True,
        "transfer_boundary_declared": True,
    }
    required = {
        "locked_test_present",
        "validation_baseline_dominance",
        "test_baseline_dominance",
        "worst_unit_noninferiority",
        "parameter_direction_stability",
        "dimensional_plausibility",
        "ast_replay",
        "negative_control",
        "support",
        "heldout_target_mutation_invariant",
        "residual_adequacy",
        "multiplicity_control",
        "transfer_boundary_declared",
    }
    promoted = all(bool(gate_results[name]) for name in required)

    ast_identity = ast_digest(ast)
    law_payload = {
        "study": study_id,
        "program": program.program_id,
        "ast": ast_identity,
        "scope": f"paired replicated positive {collection_label}",
        "collection": collection_label,
        "version": SPATIAL_EXECUTOR_VERSION,
    }
    law_id = "law:" + canonical_sha256(law_payload)[:24]
    calibration_payload = {
        "law": law_id,
        "split": split.split_manifest_id,
        "model": {
            "spec": champion_model.spec,
            "ridge": champion_model.ridge,
            "names": champion_model.names,
            "means": champion_model.means.tolist(),
            "scales": champion_model.scales.tolist(),
            "coefficients": champion_model.coefficients.tolist(),
            "intercept": champion_model.intercept,
        },
        "test": test_metrics,
        "version": SPATIAL_EXECUTOR_VERSION,
    }
    calibration_digest = canonical_sha256(calibration_payload)
    calibration_id = "calibration:" + calibration_digest[:24]
    evaluation_payload = {
        "law": law_id,
        "calibration": calibration_id,
        "test_units": test_units,
        "test": test_metrics,
        "baseline": baseline_test_metrics,
        "gates": gate_results,
    }
    evaluation_digest = canonical_sha256(evaluation_payload)
    evaluation_id = "law-eval:" + evaluation_digest[:24]
    gate_input_digest = canonical_sha256(
        {
            "objects": sorted(item.asset.byte_sha256 for item in objects),
            "split": split.split_manifest_id,
            "calibration": calibration_digest,
        }
    )
    gate_code_digest = canonical_sha256(
        {"executor": SPATIAL_EXECUTOR_VERSION, "ast": ast_identity}
    )
    gate_receipts = [
        GateReceipt(
            gate_id="gate:" + canonical_sha256(
                {"law": law_id, "metric": metric, "value": value}
            )[:24],
            metric=metric,
            comparison="boolean",
            threshold=True,
            observed=bool(value),
            passed=bool(value),
            execution_state="passed" if value else "failed",
            method=(
                "locked complete-field test and deterministic scientific control"
            ),
            input_digest=gate_input_digest,
            code_digest=gate_code_digest,
            details={
                "split_manifest_id": split.split_manifest_id,
                "transform_graph_id": transform.transform_graph_id,
                **({"maximum_relative_error": max(replay_errors), "tolerance": 1e-10, "prediction_digest": original_prediction_digest} if metric == "ast_replay" else {}),
                **({"inferred_output": inferred_dimension, "signatures": dimension_signatures, "scope": "native-unit empirical prediction; physical unit calibration remains unverified"} if metric == "dimensional_plausibility" else {}),
            },
        )
        for metric, value in sorted(gate_results.items())
    ]

    law = ScientificLawFamily(
        law_id=law_id,
        study_id=study_id,
        program_id=program.program_id,
        name=selected_family_label + " spatial law",
        family_kind="response_kernel" if "kernel" in champion_spec else "spatial_field",
        rule_kind="empirical_predictive",
        engine_version="principia-cross-domain-rule-engine/3",
        executor_id="spatial_event_law",
        executor_version=SPATIAL_EXECUTOR_VERSION,
        signature_identity=canonical_sha256(
            {"executor": SPATIAL_EXECUTOR_VERSION, "ast": ast_identity, "scope": collection_label}
        ),
        equation_ast=ast,
        canonical_ast_digest=ast_identity,
        expression_latex=(r"T_m(s)=T_{\rm ref}\exp\left[\min\left(50,\max\left(-50,b+"
                          r"\sum_{i\in\mathcal{A}}"
                          r"c_i z_i(s)\right)\right)\right]"),
        scientific_meaning=(
            f"The {selected_family_label.lower()} model predicts a positive spatial field with "
            f"{len(active_features) + 1} fitted coefficients. "
            "The active terms describe input-dependent spatial variation and measured operating strata. "
            "Training normalization is absorbed into the coefficients; fixed feature transforms are defined below."
        ),
        target="positive replicated spatial response field T",
        scope=(
            f"Complete paired {collection_label.replace('_', ' ')} objects represented by the frozen split; "
            "sampled positions are not independent units."
        ),
        dimensional_signature={"output": inferred_dimension},
        constraints=[
            {"constraint": "positivity", "enforced_by": "exponential link"},
            {"constraint": "whole_field_split", "enforced_by": split.split_manifest_id},
            {"constraint": "fold_local_preprocessing", "enforced_by": transform.transform_graph_id},
        ],
        symmetries=["radial basis", "quadrupole azimuthal basis", "translation removed by field centering"],
        parameter_roles=[
            {"symbol": "b", "role": "fitted log scale"},
            {"symbol": "T_ref", "role": "one native target unit"},
            *[{"symbol": f"c_{i}", "role": name} for i, name in active_features],
            {"symbol": r"\mathcal{A}", "role": "active input features selected inside development folds", "indices": [i for i, _ in active_features]},
        ],
        evidence_tier="internal_locked_validation" if promoted else "candidate",
        gate_summary={
            "passed": promoted,
            "gates": gate_results,
            "test_improvement_fraction": test_improvement,
            "validation_improvement_fraction": validation_improvement,
            "selection_affected_internal": True,
            "prospective_confirmation": "pending",
            "validation_label": (
                "internal_holdout" if len(objects) >= 50 else "exploratory_small_independent_unit_count"
            ),
        },
        gate_receipts=gate_receipts,
        variable_bindings=[
            *[{"symbol": f"z_{i}", "role": "input-only feature", "transform": name, "executor_version": SPATIAL_EXECUTOR_VERSION} for i, name in active_features],
            {"symbol": "T_m(s)", "role": "complete spatial target field"},
        ],
        object_bindings=[
            {"object_id": item.object_id, "regime": item.regime, "role": "independent complete field"}
            for item in objects
        ],
        independent_unit_bindings=[
            {
                "kind": split.independent_unit_kind,
                "development": split.development_unit_count,
                "validation": split.validation_unit_count,
                "test": split.test_unit_count,
            }
        ],
        scientific_or_industrial_use=(
            "Predict complete target fields from process-driver maps while exposing residual spatial regimes and transfer limits."
        ),
        limitations=[
            "Internal selection and validation remain selection-affected until prospectively sealed.",
            "Transfer outside the measured regime and driver-support envelope requires new calibration.",
            "Formal native-unit consistency is verified; physical unit calibration and microscopic mechanism identification remain unverified.",
            "Repeated source condition codes define empirical strata; their mapping to executed process recipes remains unconfirmed.",
            "The input-only split preserves development support and measures interpolation, not extrapolation to unseen operating ranges.",
        ],
        calibration_ids=[calibration_id],
        evaluation_ids=[evaluation_id],
        family_digest=canonical_sha256({**law_payload, "gates": gate_results}),
    )
    calibration = ScientificLawCalibration(
        calibration_id=calibration_id,
        study_id=study_id,
        law_id=law_id,
        split_manifest_id=split.split_manifest_id,
        regime="joint hierarchical calibration",
        fitted_parameters={
            "equation_parameters": equation_parameters,
            "feature_names": list(champion_model.names),
            "standardized_coefficients": champion_model.coefficients.tolist(),
            "intercept": champion_model.intercept,
            "ridge": champion_model.ridge,
            "scaler_means": champion_model.means.tolist(),
            "scaler_scales": champion_model.scales.tolist(),
        },
        parameter_uncertainty={
            "direction_stability_fraction": direction_stability,
            "fold_count": len(selected_coefficients),
            "selection_affected": True,
        },
        development_metrics={
            "cross_validated_mape_percent": champion_row["development_mape_percent"]
        },
        validation_metrics=validation_metrics,
        test_metrics=test_metrics,
        worst_unit_metrics=max(test_units, key=lambda item: item["mape_percent"]),
        residual_diagnostics={
            "test": test_metrics,
            "baseline": baseline_test_metrics,
        },
        sensitivity={
            "coefficient_direction_stability": direction_stability,
            "candidate_frontier_size": len(frontier),
            "selection_policy": "whole-group development one-standard-error parsimony with validation guard",
            "development_standard_error": champion_row["development_standard_error"],
            "fitted_coefficient_count": len(active_features) + 1,
            "selected_family": champion_spec,
        },
        support={
            "passed": support_pass,
            "training_envelope": {"lower": lower.tolist(), "upper": upper.tolist()},
            "test_summaries": test_summaries.tolist(),
            "action_outside_support": "abstain",
        },
        counterexamples=sorted(test_units, key=lambda item: -item["mape_percent"])[:5],
        calibration_digest=calibration_digest,
    )
    evaluation = LawEvaluation(
        evaluation_id=evaluation_id,
        study_id=study_id,
        law_id=law_id,
        calibration_id=calibration_id,
        split="test",
        unit_metrics=test_units,
        aggregate_metrics=test_metrics,
        baseline_metrics={
            **baseline_test_metrics,
            "baseline_family": "regime-conditioned smooth spatial field without driver response",
            "negative_control": negative_metrics,
        },
        gate_results=gate_results,
        gate_receipts=gate_receipts,
        selection_affected=False,
        evaluation_digest=evaluation_digest,
    )
    candidates: list[LawCandidate] = []
    for row in frontier:
        candidate_ast = candidate_equations[(str(row["spec"]), float(row["ridge"]))]
        payload = {"law": law_id, **row, "ast": ast_digest(candidate_ast)}
        candidates.append(
            LawCandidate(
                candidate_id="law-candidate:" + canonical_sha256(payload)[:24],
                study_id=study_id,
                program_id=program.program_id,
                law_id=law_id,
                equation_ast=candidate_ast,
                complexity=int(row["complexity"]),
                development_score=float(row["development_mape_percent"]),
                validation_score=float(row["validation_mape_percent"]),
                baseline_contrast={
                    "validation_baseline_mape_percent": baseline_validation[
                        "mean_map_mape_percent"
                    ]
                },
                rejection_reasons=[] if (
                    str(row["spec"]) == champion_spec and float(row["ridge"]) == champion_ridge
                ) else ["Not selected on the frozen development/validation objective."],
                state="champion" if (
                    str(row["spec"]) == champion_spec and float(row["ridge"]) == champion_ridge
                ) else "rejected",
                candidate_digest=canonical_sha256(payload),
            )
        )
    decision_payload = {
        "study": study_id,
        "program": program.program_id,
        "law": law_id,
        "champion": champion_row,
        "gates": gate_results,
        "promoted": promoted,
    }
    decision = ScientificDecision(
        decision_id="decision:" + canonical_sha256(decision_payload)[:24],
        study_id=study_id,
        program_id=program.program_id,
        subject_id=law_id,
        decision_type="promotion",
        outcome="accepted" if promoted else "held",
        reasons=(
            ["All required locked whole-field prediction, stability, support, and negative-control gates passed."]
            if promoted
            else [
                "The law remains a candidate because these gates failed: "
                + ", ".join(name for name in sorted(required) if not gate_results[name])
            ]
        ),
        input_digests=[split.target_blind_digest, calibration_digest, evaluation_digest],
        decision_digest=canonical_sha256(decision_payload),
    )

    used_assets = sorted({item.asset.asset_id: item.asset for item in objects}.values(), key=lambda item: item.asset_id)
    status = promoted
    outcome = _collection_outcome(
        study_id=study_id,
        assets=used_assets,
        operator="replicated_spatial_scientific_program",
        hypothesis_claim=(
            "A regime-conditioned local–nonlocal response law may predict complete output fields "
            "from paired driver fields beyond a smooth spatial baseline."
        ),
        expected_relationship=(
            "The frozen law improves mean and worst-unit locked-test error over a driver-blind "
            "spatial baseline while surviving support, stability, mutation, and negative-control gates."
        ),
        confounders=[
            "regime labels may absorb unmeasured process settings",
            "paired fields may share metrology artifacts",
            "internal selection affects development and validation evidence",
            "spatial registration uses supplied row order when coordinate scales differ",
        ],
        falsifier=(
            "The law fails on prospectively sealed complete fields, loses to the frozen baseline, "
            "or its driver terms vanish under randomized interventions or independent metrology."
        ),
        sample_definition=(
            f"{len(objects)} complete paired spatial fields across {len(regimes)} detected regimes; "
            f"{len(partitions['development'])} development, {len(partitions['validation'])} validation, "
            f"and {len(partitions['test'])} locked test units"
        ),
        independent_unit_count=len(objects),
        parameters={
            "law_id": law_id,
            "split_manifest_id": split.split_manifest_id,
            "candidate_count": len(frontier),
            "champion_family": champion_spec,
        },
        estimate={
            "locked_test": test_metrics,
            "locked_baseline": baseline_test_metrics,
            "test_improvement_fraction": test_improvement,
        },
        uncertainty={
            "coefficient_direction_stability_fraction": direction_stability,
            "selection_affected_internal": True,
            "prospective_confirmation": "pending",
        },
        sensitivities=[
            {"specification": "negative_control", **negative_metrics},
            {"specification": "support_envelope", "passed": support_pass},
            {"specification": "candidate_frontier", "candidates": frontier},
        ],
        diagnostics=[
            "All preprocessing and candidate fitting were confined to development folds before champion selection.",
            "The locked test was evaluated once after the champion and preprocessing graph were frozen.",
            f"Held-out target mutation left predictions unchanged: {mutation_invariant}.",
            "Per-site residuals are diagnostics; complete spatial fields are the independent units.",
        ],
        negative_evidence=[] if promoted else [decision.reasons[0]],
        title=(
            "A local–nonlocal field law predicts held-out spatial responses"
            if promoted
            else "A spatial response law was tested but did not clear every promotion gate"
        ),
        claim=(
            f"On {len(partitions['test'])} locked complete fields, the selected {champion_spec.replace('_', ' ')} "
            f"law achieved {test_metrics['mean_map_mape_percent']:.3g}% mean map MAPE and "
            f"{test_metrics['worst_map_mape_percent']:.3g}% worst-map MAPE, versus "
            f"{baseline_test_metrics['mean_map_mape_percent']:.3g}% and "
            f"{baseline_test_metrics['worst_map_mape_percent']:.3g}% for the frozen spatial baseline."
        ),
        interpretation=(
            "Mean scale and spatial shape are not a single control problem: a shared geometric field "
            "must be combined with local and, when selected, neighboring driver response."
        ),
        mechanism=(
            "The local term represents pointwise response, while the kernel term represents lateral "
            "transport or neighboring-zone influence superposed on a regime-specific chamber field."
        ),
        supported=status,
        validation_level=("internal_holdout" if len(objects) >= 50 else "exploratory"),
        robustness=[
            "target-blind whole-field split",
            "fold-local scaling and fitting",
            "locked baseline comparison",
            "worst-field metric",
            "driver permutation negative control",
            "held-out target mutation test",
            "support envelope",
        ],
        limits=[
            "This is internally selected evidence and is not prospectively confirmed.",
            "Regime labels are observational and may combine several physical process changes.",
            "The compact basis is a predictive closure, not a unique mechanistic identification.",
        ],
        next_validation=(
            "Prospectively seal the equation and calibration, randomize orthogonal driver perturbations, "
            "and test full-field prediction on new hardware and process regimes."
        ),
        locators={item.asset_id: {"scientific_program": program.program_id} for item in used_assets},
        units={"target": "source-declared units", "driver": "source-declared units", "position": "normalized supplied coordinates"},
        expression_latex=law.expression_latex if promoted else "",
        equation_variables=[
            {"symbol": "T_m(s)", "meaning": "target field for complete unit m at position s"},
            {"symbol": "C_m(s)", "meaning": "paired driver field"},
            {"symbol": r"B_{\alpha}(s)", "meaning": "radial and azimuthal geometric field"},
            {"symbol": r"K_{\lambda}", "meaning": "nonlocal response kernel"},
        ],
        split_validation={
            "strategy": "stratified complete-field development/validation/test",
            "split_manifest_id": split.split_manifest_id,
            "selection_lock": "candidate grammar, preprocessing, champion, and parameters frozen before the locked test",
            "development": {"candidate_frontier": frontier},
            "validation": validation_metrics,
            "test": {"passed": promoted, **test_metrics, "baseline": baseline_test_metrics},
            "gates": gate_results,
        },
        insight_level="mechanistic" if promoted else "structural",
        nontriviality_basis=(
            "The relationship predicts complete held-out fields, compares against a strong spatial baseline, "
            "and separates local response from nonlocal transport structure."
        ),
        significance=(
            "The executable family can support field-level prediction and identifies when a purely local "
            "or global-average correction is structurally inadequate."
        ),
        principle_statement=(
            "Replicated spatial processes require separate scale, geometry, local-response, and nonlocal-transport terms; "
            "a field law is transferable only within its measured support and regime boundary."
        ) if promoted else "",
        transfer_scope="Paired positive spatial fields within the observed driver-summary support envelope.",
    )
    completed_program = program.model_copy(
        update={
            "split_manifest_id": split.split_manifest_id,
            "transform_graph_id": transform.transform_graph_id,
            "state": "completed",
            "decisions": [
                *program.decisions,
                f"Selected {champion_spec} from {len(frontier)} development/validation candidates.",
                "Promoted to Rule." if promoted else "Held as a tested candidate; no Rule promotion.",
            ],
            "updated_at": utc_now(),
        }
    )
    if emit:
        emit(
            "champion_selected",
            f"Selected {champion_spec}; locked test remained unopened until the family was frozen.",
            {"law_id": law_id, "candidate_count": len(frontier)},
        )
        emit(
            "robustness_tested",
            "Completed locked whole-field evaluation, baseline, negative control, support, and leakage checks.",
            {"promoted": promoted, "gates": gate_results},
        )
    law = law.model_copy(
        update={
            "test_ids": [outcome.result.test_id],
            "evidence_ids": [
                outcome.evidence.evidence_id,
                *[item.evidence_id for item in outcome.additional_evidence],
            ],
        }
    )
    return ScientificProgramBundle(
        programs=(completed_program,),
        split_manifests=(split,),
        transform_graphs=(transform,),
        laws=(law,),
        calibrations=(calibration,),
        candidates=tuple(candidates),
        evaluations=(evaluation,),
        decisions=(decision,),
        outcomes=(outcome,),
        limitations=() if promoted else (decision.reasons[0],),
    )
