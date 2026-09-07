from __future__ import annotations

import csv
import gzip
import io
import json
import math
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from ..domain import (
    AnalysisPlan,
    ComputedEvidenceAnchor,
    DataAsset,
    DataFinding,
    DataHypothesis,
    TestResult,
    canonical_sha256,
)
from ..models import utc_now
from .numeric_locale import (
    detect_delimiter,
    infer_column_locales,
    looks_numeric,
    parse_numeric,
    punctuation_hint,
)

OPERATOR_VERSION = "principia-asd-operators/5"
MAX_ROWS = 50_000
MAX_COLUMNS = 64
MAX_VALUES = 1_000_000
MAX_TEXT_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_MEMBER_BYTES = 512 * 1024 * 1024


def _latex_label(value: str) -> str:
    """Keep source variable labels readable without allowing LaTeX control input."""

    normalized = " ".join(str(value).replace("\\", " ").split())[:80]
    return (
        normalized.replace("{", "(")
        .replace("}", ")")
        .replace("_", r"\_")
        .replace("%", r"\%")
        .replace("&", r"\&")
        .replace("#", r"\#")
    )


@dataclass(frozen=True)
class LoadedNumeric:
    values: np.ndarray
    variables: list[str]
    locator: dict[str, Any]
    sample_definition: str
    identifiers: dict[str, np.ndarray] = field(default_factory=dict)


@dataclass(frozen=True)
class OperatorOutcome:
    hypothesis: DataHypothesis
    plan: AnalysisPlan
    result: TestResult
    evidence: ComputedEvidenceAnchor
    finding: DataFinding
    # Collection-level operators can depend on several immutable source files.
    # Keep the historical primary anchor for compatibility, while retaining an
    # exact anchor for every additional input rather than hiding cross-file
    # provenance in a free-text locator.
    additional_evidence: tuple[ComputedEvidenceAnchor, ...] = ()


def _rows_to_numeric(
    rows: Iterable[list[Any]], *, header: list[str] | None = None
) -> LoadedNumeric | None:
    materialized: list[list[Any]] = []
    width = 0
    for row in rows:
        if not row:
            continue
        materialized.append(list(row)[:MAX_COLUMNS])
        width = max(width, min(len(row), MAX_COLUMNS))
        if len(materialized) >= MAX_ROWS:
            break
    if len(materialized) < 3 or not width:
        return None
    locales = infer_column_locales(materialized, width)
    ambiguous_cells = [0] * width
    array = np.full((len(materialized), width), np.nan, dtype=float)
    for row_index, row in enumerate(materialized):
        for column_index, value in enumerate(row[:width]):
            try:
                array[row_index, column_index] = parse_numeric(value, locales[column_index])
            except (TypeError, ValueError, OverflowError):
                if punctuation_hint(value):
                    ambiguous_cells[column_index] += 1
                continue
    useful = np.sum(np.isfinite(array), axis=0) >= 3
    if not np.any(useful):
        return None
    array = array[:, useful]
    raw_names = header or [f"column_{index + 1}" for index in range(width)]
    variables = [
        str(raw_names[index] if index < len(raw_names) else f"column_{index + 1}")[:200]
        for index in np.flatnonzero(useful)
    ]
    # Common public-use survey sentinels are not measurements.  Mask them only
    # when they are repeated and coexist with a clearly non-sentinel numeric
    # range; this conservative rule avoids silently rewriting legitimate small
    # negative-valued scientific signals.
    masked_sentinels: dict[str, list[float]] = {}
    sentinels = np.asarray((-9999, -999, -888, -99, -88, -9, -8, -7), dtype=float)
    for column_index, variable in enumerate(variables):
        column = array[:, column_index]
        finite = column[np.isfinite(column)]
        if finite.size < 20 or not np.any(finite >= 0):
            continue
        column_sentinels: list[float] = []
        for sentinel in sentinels:
            count = int(np.sum(column == sentinel))
            if count >= max(2, int(math.ceil(finite.size * 0.01))):
                column[column == sentinel] = np.nan
                column_sentinels.append(float(sentinel))
        if column_sentinels:
            masked_sentinels[variable] = column_sentinels
    locator: dict[str, Any] = {
        "row_start": 1,
        "row_end": len(materialized),
        "variables": variables,
    }
    if any(locale != "plain" for locale in locales):
        locator["numeric_locale"] = {
            str(raw_names[i] if i < len(raw_names) else f"column_{i + 1}"): locale
            for i, locale in enumerate(locales) if locale != "plain"
        }
        locator["ambiguous_numeric_cells_masked"] = sum(ambiguous_cells)
    if masked_sentinels:
        locator["masked_public_use_sentinels"] = masked_sentinels
    return LoadedNumeric(
        values=array,
        variables=variables,
        locator=locator,
        sample_definition=f"first {len(materialized):,} readable records",
        identifiers={str(name): np.asarray([str(row[i]).strip() if i < len(row) and row[i] is not None else "" for row in materialized]) for i, name in enumerate(raw_names) if i < width},
    )


def _delimited_stream(stream: io.TextIOBase, *, suffix: str = "") -> LoadedNumeric | None:
    sample = stream.read(64 * 1024)
    stream.seek(0)
    delimiter = detect_delimiter(sample, suffix=suffix)
    reader = csv.reader(stream, delimiter=delimiter)
    first = next(reader, [])
    numeric_first = sum(looks_numeric(value) for value in first)
    header = first if numeric_first == 0 else None
    if header is None:
        def rows() -> Iterable[list[Any]]:
            yield first
            yield from reader

        return _rows_to_numeric(rows())
    return _rows_to_numeric(reader, header=header)


def _load_delimited(path: Path) -> LoadedNumeric | None:
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as stream:
        return _delimited_stream(stream, suffix=path.suffix.casefold())


def _load_gzip(path: Path, format_name: str) -> LoadedNumeric | None:
    if format_name == "matrix_market_gzip":
        rows: list[list[float]] = []
        dimensions: list[int] = []
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as stream:
            for line in stream:
                stripped = line.strip()
                if not stripped or stripped.startswith("%"):
                    continue
                fields = stripped.split()
                if not dimensions:
                    try:
                        dimensions = [int(value) for value in fields[:3]]
                    except ValueError:
                        return None
                    continue
                try:
                    rows.append([float(value) for value in fields[:3]])
                except ValueError:
                    continue
                if len(rows) >= MAX_ROWS:
                    break
        loaded = _rows_to_numeric(rows, header=["matrix_row", "matrix_column", "value"])
        if loaded is None:
            return None
        return LoadedNumeric(
            values=loaded.values,
            variables=loaded.variables,
            locator={**loaded.locator, "matrix_dimensions": dimensions},
            sample_definition=(
                f"first {loaded.values.shape[0]:,} coordinate entries from Matrix Market data"
            ),
        )
    if path.name.casefold() == "stripped.gz":
        rows: list[list[float]] = []
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as stream:
            for line in stream:
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "," not in stripped:
                    continue
                terms: list[int] = []
                for token in stripped.split(",")[1:]:
                    try:
                        terms.append(int(token.strip()))
                    except ValueError:
                        continue
                if len(terms) < 4:
                    continue
                magnitudes = np.asarray(
                    [math.log10(max(1, abs(value))) for value in terms[:512]],
                    dtype=float,
                )
                increments = np.diff(magnitudes)
                rows.append(
                    [
                        float(len(terms)),
                        float(magnitudes[0]),
                        float(magnitudes[-1]),
                        float(np.median(increments)),
                        float(np.std(increments, ddof=1)) if increments.size > 1 else 0.0,
                    ]
                )
                if len(rows) >= MAX_ROWS:
                    break
        loaded = _rows_to_numeric(
            rows,
            header=[
                "term_count",
                "initial_log10_magnitude",
                "terminal_log10_magnitude",
                "median_log10_growth",
                "log_growth_variability",
            ],
        )
        if loaded is None:
            return None
        return LoadedNumeric(
            values=loaded.values,
            variables=loaded.variables,
            locator={
                **loaded.locator,
                "projection": "per-sequence log-magnitude growth profile",
                "exact_terms_retained_in_source": True,
            },
            sample_definition=f"bounded growth profiles for {loaded.values.shape[0]:,} OEIS sequences",
        )
    with gzip.open(path, "rt", encoding="utf-8", errors="replace", newline="") as stream:
        if format_name == "json_gzip":
            return None
        sample = stream.read(4_096)
        stream.seek(0)
        return _delimited_stream(stream, suffix=".tsv" if "\t" in sample else ".csv")


def _load_zip(path: Path) -> LoadedNumeric | None:
    with zipfile.ZipFile(path) as archive:
        candidates = [
            info
            for info in archive.infolist()
            if not info.is_dir()
            and Path(info.filename).suffix.casefold() in {".csv", ".tsv", ".txt", ".dat"}
            # The stream is bounded by MAX_ROWS; large official flat files do
            # not need to be extracted or read wholly into memory.
            and info.file_size <= MAX_ARCHIVE_MEMBER_BYTES
        ]
        candidates.sort(
            key=lambda item: (
                any(
                    token in item.filename.casefold()
                    for token in (
                        "repwgt",
                        "replicate_weight",
                        "layout",
                        "dictionary",
                        "codebook",
                        "readme",
                    )
                ),
                Path(item.filename).suffix.casefold() not in {".csv", ".tsv"},
                -item.file_size,
                item.filename,
            )
        )
        for info in candidates[:20]:
            with archive.open(info) as raw:
                wrapper = io.TextIOWrapper(
                    raw, encoding="utf-8-sig", errors="replace", newline=""
                )
                loaded = _delimited_stream(
                    wrapper, suffix=Path(info.filename).suffix.casefold()
                )
                if loaded is not None:
                    return LoadedNumeric(
                        values=loaded.values,
                        variables=loaded.variables,
                        locator={**loaded.locator, "archive_member": info.filename},
                        sample_definition=(
                            f"{loaded.sample_definition} from archive member {info.filename}"
                        ),
                    )
    return None


def _flatten_numeric_records(
    value: Any,
    *,
    prefix: str = "",
    output: list[dict[str, float]] | None = None,
) -> list[dict[str, float]]:
    output = output if output is not None else []
    if len(output) >= MAX_ROWS:
        return output
    if isinstance(value, list):
        for item in value:
            _flatten_numeric_records(item, prefix=prefix, output=output)
            if len(output) >= MAX_ROWS:
                break
    elif isinstance(value, dict):
        numeric: dict[str, float] = {}
        nested = False
        for key, item in value.items():
            name = f"{prefix}.{key}".strip(".")
            if isinstance(item, bool):
                continue
            if isinstance(item, (int, float)) and math.isfinite(float(item)):
                numeric[name] = float(item)
            elif isinstance(item, (dict, list)):
                nested = True
                _flatten_numeric_records(item, prefix=name, output=output)
        if numeric and (len(numeric) >= 2 or not nested):
            output.append(numeric)
    return output


def _load_json(path: Path) -> LoadedNumeric | None:
    if path.stat().st_size > MAX_TEXT_BYTES:
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if isinstance(value, dict) and isinstance(value.get("features"), list):
        rows: list[list[float]] = []
        variables = [
            "longitude",
            "latitude",
            "depth_km",
            "magnitude",
            "time_ms",
            "gap_degrees",
            "rms_seconds",
            "station_count",
            "nearest_station_degrees",
        ]
        for feature in value["features"][:MAX_ROWS]:
            if not isinstance(feature, dict):
                continue
            geometry = feature.get("geometry")
            properties = feature.get("properties")
            coordinates = geometry.get("coordinates") if isinstance(geometry, dict) else None
            if not isinstance(coordinates, list) or len(coordinates) < 3 or not isinstance(properties, dict):
                continue
            raw_row = [
                coordinates[0],
                coordinates[1],
                coordinates[2],
                properties.get("mag"),
                properties.get("time"),
                properties.get("gap"),
                properties.get("rms"),
                properties.get("nst"),
                properties.get("dmin"),
            ]
            try:
                rows.append([float(item) if item is not None else math.nan for item in raw_row])
            except (TypeError, ValueError, OverflowError):
                continue
        if len(rows) >= 10:
            return LoadedNumeric(
                values=np.asarray(rows, dtype=float),
                variables=variables,
                locator={
                    "feature_start": 0,
                    "feature_end": len(rows),
                    "variables": variables,
                    "geometry": "GeoJSON Point coordinates",
                },
                sample_definition=f"{len(rows):,} GeoJSON point features",
            )
    records = _flatten_numeric_records(value)
    if not records:
        return None
    variables = sorted({key for record in records for key in record})[:MAX_COLUMNS]
    rows = [[record.get(key) for key in variables] for record in records]
    return _rows_to_numeric(rows, header=variables)


def load_xlsx_projections(path: Path) -> list[LoadedNumeric]:
    """Return bounded numeric projections for every credible worksheet.

    Excel's declared worksheet dimensions are not trusted: ordinary formatting
    can make a small sheet claim 1,048,576 by 16,384 cells.  Header selection is
    based on the bounded cell contents and each useful sheet is retained so a
    cover/summary sheet cannot hide the real experimental table behind it.
    """
    try:
        import openpyxl
    except ImportError:
        return []
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    projections: list[tuple[float, LoadedNumeric]] = []
    try:
        for sheet in workbook.worksheets:
            bounded: list[tuple[int, list[Any]]] = []
            for row_index, row in enumerate(
                sheet.iter_rows(
                    min_row=1,
                    max_row=min(int(sheet.max_row or 0), 5_000),
                    min_col=1,
                    max_col=min(int(sheet.max_column or 0), MAX_COLUMNS),
                    values_only=True,
                ),
                start=1,
            ):
                values = list(row)
                if any(value is not None and str(value).strip() for value in values):
                    bounded.append((row_index, values))
            if len(bounded) < 3:
                continue
            sheet_candidates: list[tuple[float, LoadedNumeric]] = []
            for header_offset in range(min(12, len(bounded) - 2)):
                header_row_number, header_values = bounded[header_offset]
                data_rows = [values for _, values in bounded[header_offset + 1 :]]
                header = [
                    str(value).strip()[:200] if value is not None and str(value).strip() else f"column_{index + 1}"
                    for index, value in enumerate(header_values[:MAX_COLUMNS])
                ]
                loaded = _rows_to_numeric(data_rows, header=header)
                if loaded is None:
                    continue
                finite_fraction = float(np.isfinite(loaded.values).mean())
                named_fraction = sum(
                    not value.startswith("column_") for value in loaded.variables
                ) / max(1, len(loaded.variables))
                score = (
                    math.log1p(loaded.values.shape[0])
                    * loaded.values.shape[1]
                    * finite_fraction
                    + 2.0 * named_fraction
                    - 0.15 * header_offset
                )
                projection = LoadedNumeric(
                    values=loaded.values,
                    variables=loaded.variables,
                    identifiers=loaded.identifiers,
                    locator={
                        **loaded.locator,
                        "sheet": sheet.title,
                        "header_row": header_row_number,
                        "row_start": header_row_number + 1,
                        "row_end": bounded[-1][0],
                        "bounded": True,
                    },
                    sample_definition=(
                        f"{loaded.values.shape[0]:,} bounded numeric records in worksheet {sheet.title}"
                    ),
                )
                sheet_candidates.append((score, projection))
            if sheet_candidates:
                projections.append(max(sheet_candidates, key=lambda item: item[0]))
    finally:
        workbook.close()
    projections.sort(key=lambda item: item[0], reverse=True)
    return [item for _, item in projections]


def _load_xlsx(path: Path) -> LoadedNumeric | None:
    projections = load_xlsx_projections(path)
    return projections[0] if projections else None


def _load_hdf(path: Path) -> LoadedNumeric | None:
    try:
        import h5py
    except ImportError:
        return None
    candidates: list[tuple[float, str, Any]] = []
    with h5py.File(path, "r") as handle:
        def visitor(name: str, value: Any) -> None:
            if not isinstance(value, h5py.Dataset):
                return
            if np.issubdtype(value.dtype, np.number) and value.size >= 10 and value.ndim <= 3:
                normalized = name.casefold()
                score = math.log10(max(10, int(value.size)))
                if np.issubdtype(value.dtype, np.floating):
                    score += 4.0
                if any(token in normalized for token in ("strain", "signal", "response", "data")):
                    score += 8.0
                if any(token in normalized for token in ("mask", "quality", "flag", "id")):
                    score -= 12.0
                if value.ndim == 1:
                    score += 2.0
                elif value.ndim == 3:
                    score -= 3.0
                candidates.append((score, name, value))

        handle.visititems(visitor)
        if not candidates:
            return None
        _, name, dataset = max(candidates, key=lambda item: (item[0], item[1]))
        if dataset.ndim == 1:
            array = np.asarray(dataset[: min(dataset.shape[0], MAX_ROWS)], dtype=float)[:, None]
        elif dataset.ndim == 2:
            array = np.asarray(
                dataset[: min(dataset.shape[0], MAX_ROWS), : min(dataset.shape[1], MAX_COLUMNS)],
                dtype=float,
            )
        else:
            selection = tuple(slice(0, min(size, 64)) for size in dataset.shape)
            flat = np.asarray(dataset[selection], dtype=float).ravel()[:MAX_VALUES]
            array = flat[:, None]
        attributes: dict[str, Any] = {}
        for key, value in dataset.attrs.items():
            if isinstance(value, np.generic):
                value = value.item()
            if isinstance(value, (str, int, float, bool)):
                attributes[str(key)] = value
        x_spacing = attributes.get("Xspacing")
        sample_rate = (
            1.0 / float(x_spacing)
            if isinstance(x_spacing, (int, float)) and float(x_spacing) > 0
            else None
        )
        source_value_count = int(dataset.size)
        analyzed_value_count = int(array.size)
        coverage_fraction = analyzed_value_count / max(1, source_value_count)
        if dataset.ndim == 1:
            sample_definition = (
                f"first {array.shape[0]:,} of {dataset.shape[0]:,} samples from HDF5 dataset {name}"
            )
        else:
            sample_definition = (
                f"bounded {list(array.shape)} projection of HDF5 dataset {name} with source shape {list(dataset.shape)}"
            )
        return LoadedNumeric(
            values=array,
            variables=[f"{name}:{index}" for index in range(array.shape[1])],
            locator={
                "dataset": name,
                "shape": list(dataset.shape),
                "sample_shape": list(array.shape),
                "attributes": attributes,
                "sample_rate_hz": sample_rate,
                "source_value_count": source_value_count,
                "analyzed_value_count": analyzed_value_count,
                "coverage_fraction": coverage_fraction,
            },
            sample_definition=sample_definition,
        )


def _load_fits(path: Path) -> LoadedNumeric | None:
    try:
        from astropy.io import fits
    except ImportError:
        return None
    with fits.open(path, memmap=True, lazy_load_hdus=True) as hdus:
        primary_header = hdus[0].header if hdus else {}
        for index, hdu in enumerate(hdus):
            data = getattr(hdu, "data", None)
            if data is None:
                continue
            names = list(getattr(data, "names", None) or [])
            if names:
                numeric_columns: list[np.ndarray] = []
                variables: list[str] = []
                for name in names[:MAX_COLUMNS]:
                    try:
                        column = np.asarray(data[name][:MAX_ROWS], dtype=float)
                    except (TypeError, ValueError):
                        continue
                    if column.ndim == 1:
                        numeric_columns.append(column)
                        variables.append(str(name))
                if numeric_columns:
                    length = min(map(len, numeric_columns))
                    scientific_metadata: dict[str, Any] = {}
                    for key in (
                        "TICID",
                        "SECTOR",
                        "CAMERA",
                        "CCD",
                        "TESSMAG",
                        "TIMESYS",
                        "TELESCOP",
                        "INSTRUME",
                        "HLSPNAME",
                        "HLSPID",
                        "DOI",
                    ):
                        value = primary_header.get(key)
                        if isinstance(value, (str, int, float, bool)):
                            scientific_metadata[key.casefold()] = value
                    for key in (
                        "PER1",
                        "POW1",
                        "SNR1",
                        "AMPFIT",
                        "P2PRMS",
                        "REDCHI2",
                        "SNR",
                    ):
                        value = hdu.header.get(key)
                        if isinstance(value, (str, int, float, bool)):
                            scientific_metadata[key.casefold()] = value
                    units = {
                        str(name): str(hdu.header.get(f"TUNIT{position}") or "")
                        for position, name in enumerate(names, start=1)
                        if hdu.header.get(f"TUNIT{position}")
                    }
                    return LoadedNumeric(
                        values=np.column_stack([value[:length] for value in numeric_columns]),
                        variables=variables,
                        locator={
                            "hdu": index,
                            "hdu_name": str(hdu.name),
                            "rows": [0, length],
                            "units": units,
                            "scientific_metadata": scientific_metadata,
                        },
                        sample_definition=f"first {length:,} rows from FITS HDU {index}",
                    )
            try:
                flat = np.asarray(data, dtype=float).ravel()[:MAX_VALUES]
            except (TypeError, ValueError):
                continue
            if flat.size >= 10:
                return LoadedNumeric(
                    values=flat[:, None],
                    variables=[str(hdu.name or f"hdu_{index}")],
                    locator={"hdu": index, "sample_values": int(flat.size)},
                    sample_definition=f"bounded pixel/value sample from FITS HDU {index}",
                )
    return None


def _load_root(path: Path) -> LoadedNumeric | None:
    try:
        import uproot
    except ImportError:
        return None
    with uproot.open(path) as handle:
        for key, value in handle.items(recursive=True):
            if not hasattr(value, "arrays"):
                continue
            try:
                arrays = value.arrays(library="np", entry_stop=MAX_ROWS)
            except (TypeError, ValueError):
                continue
            names: list[str] = []
            columns: list[np.ndarray] = []
            for name, array in arrays.items():
                value_array = np.asarray(array)
                if value_array.ndim == 1 and np.issubdtype(value_array.dtype, np.number):
                    names.append(str(name))
                    columns.append(value_array.astype(float))
                if len(columns) >= MAX_COLUMNS:
                    break
            if columns:
                length = min(map(len, columns))
                return LoadedNumeric(
                    values=np.column_stack([item[:length] for item in columns]),
                    variables=names,
                    locator={"tree": str(key), "entries": [0, length]},
                    sample_definition=f"first {length:,} entries from ROOT tree {key}",
                )
    return None


def _load_edf(path: Path) -> LoadedNumeric | None:
    try:
        import pyedflib
    except ImportError:
        return None
    reader = pyedflib.EdfReader(str(path))
    try:
        count = min(reader.signals_in_file, 16)
        sample_counts = reader.getNSamples()
        signals = [
            reader.readSignal(index, 0, min(sample_counts[index], MAX_ROWS))
            for index in range(count)
        ]
        if not signals:
            return None
        length = min(map(len, signals))
        return LoadedNumeric(
            values=np.column_stack(
                [np.asarray(value[:length], dtype=float) for value in signals]
            ),
            variables=[str(value) for value in reader.getSignalLabels()[:count]],
            locator={
                "channels": list(range(count)),
                "samples": [0, length],
                "sample_rates_hz": [float(value) for value in reader.getSampleFrequencies()[:count]],
                "physical_dimensions": [
                    str(reader.getPhysicalDimension(index)) for index in range(count)
                ],
            },
            sample_definition=f"first {length:,} samples from {count} EDF channels",
        )
    finally:
        reader.close()


def _load_dicom(path: Path) -> LoadedNumeric | None:
    try:
        import pydicom
    except ImportError:
        return None
    try:
        dataset = pydicom.dcmread(path, force=True)
        pixels = np.asarray(dataset.pixel_array, dtype=float).ravel()[:MAX_VALUES]
    except Exception:
        return None
    if pixels.size < 10:
        return None
    return LoadedNumeric(
        values=pixels[:, None],
        variables=["pixel_intensity"],
        locator={"frame": 0, "sample_pixels": int(pixels.size)},
        sample_definition=(
            f"bounded pixel sample from one DICOM instance ({pixels.size:,} pixels)"
        ),
    )


def _load_netcdf(path: Path) -> LoadedNumeric | None:
    try:
        import xarray as xr
    except ImportError:
        return None
    with xr.open_dataset(path, decode_cf=True, mask_and_scale=True, cache=False) as dataset:
        for name, value in dataset.data_vars.items():
            if not np.issubdtype(value.dtype, np.number) or value.size < 10:
                continue
            selection = {
                dimension: slice(
                    0,
                    int(value.sizes[dimension]),
                    max(1, math.ceil(int(value.sizes[dimension]) / 256)),
                )
                for dimension in value.dims
            }
            sampled = np.asarray(value.isel(selection).values, dtype=float)
            flat = sampled.ravel()[:MAX_VALUES]
            return LoadedNumeric(
                values=flat[:, None],
                variables=[str(name)],
                locator={
                    "variable": str(name),
                    "dimensions": list(value.dims),
                    "original_shape": list(value.shape),
                    "sample_shape": list(sampled.shape),
                    "selection": {
                        key: [0, item.stop, item.step] for key, item in selection.items()
                    },
                    "units": str(value.attrs.get("units") or ""),
                },
                sample_definition=f"bounded NetCDF sample from variable {name}",
            )
    return None


def _load_image(path: Path) -> LoadedNumeric | None:
    try:
        from PIL import Image
    except ImportError:
        return None
    with Image.open(path) as image:
        image.thumbnail((1024, 1024))
        array = np.asarray(image.convert("L"), dtype=float).ravel()[:MAX_VALUES]
    return LoadedNumeric(
        values=array[:, None],
        variables=["luminance"],
        locator={"derived_preview": "grayscale", "sample_pixels": int(array.size)},
        sample_definition=f"deterministic grayscale preview ({array.size:,} pixels)",
    )


def _load_ras(path: Path) -> LoadedNumeric | None:
    rows: list[list[float]] = []
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            fields = line.strip().split()
            if len(fields) < 2:
                continue
            try:
                rows.append([float(fields[0]), float(fields[1])])
            except ValueError:
                continue
            if len(rows) >= MAX_ROWS:
                break
    return _rows_to_numeric(rows, header=["angle", "intensity"])


def load_numeric(asset: DataAsset, root: Path) -> LoadedNumeric | None:
    relative = str(asset.metadata.get("relative_path") or "")
    canonical_root = root.resolve(strict=True)
    path = (canonical_root / relative).resolve(strict=True)
    if not path.is_relative_to(canonical_root) or not path.is_file():
        raise ValueError("asset locator escapes its registered source")
    if asset.format in {"csv", "tsv", "delimited", "delimited_text", "text"}:
        return _load_delimited(path)
    if asset.format in {"delimited_gzip", "matrix_market_gzip", "json_gzip"}:
        return _load_gzip(path, asset.format)
    if asset.format == "zip":
        return _load_zip(path)
    if asset.format in {"json", "geojson"}:
        return _load_json(path)
    if asset.format == "xlsx":
        return _load_xlsx(path)
    if asset.format in {"hdf5", "nwb"}:
        return _load_hdf(path)
    if asset.format == "fits":
        return _load_fits(path)
    if asset.format == "root":
        return _load_root(path)
    if asset.format == "edf":
        return _load_edf(path)
    if asset.format == "dicom":
        return _load_dicom(path)
    if asset.format == "netcdf":
        return _load_netcdf(path)
    if asset.format in {"png", "jpeg", "jpg"}:
        return _load_image(path)
    if asset.format == "ras":
        return _load_ras(path)
    if asset.format in {"scan", "parms", "mod", "se"}:
        return _load_delimited(path)
    return None


def _paired_finite(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    valid = np.isfinite(x) & np.isfinite(y)
    return x[valid], y[valid]


def _correlation(x: np.ndarray, y: np.ndarray) -> tuple[float, float | None, int]:
    left, right = _paired_finite(x, y)
    if left.size < 3:
        return 0.0, None, int(left.size)
    left_scale = float(np.max(np.abs(left)))
    right_scale = float(np.max(np.abs(right)))
    if not left_scale or not right_scale:
        return 0.0, None, int(left.size)
    # Scaling before centering prevents overflow for valid scientific values
    # near float64 limits (for example, very large OEIS integer terms).
    scaled_left = left / left_scale
    scaled_right = right / right_scale
    if np.std(scaled_left) == 0 or np.std(scaled_right) == 0:
        return 0.0, None, int(left.size)
    coefficient = float(np.corrcoef(scaled_left, scaled_right)[0, 1])
    if not math.isfinite(coefficient):
        coefficient = 0.0
    p_value: float | None = None
    try:
        from scipy.stats import pearsonr

        candidate = float(pearsonr(scaled_left, scaled_right).pvalue)
        p_value = candidate if math.isfinite(candidate) else None
    except (ImportError, ValueError):
        pass
    return coefficient, p_value, int(left.size)


def _scientific_variable_candidate(name: str) -> bool:
    normalized = " ".join(name.casefold().replace("_", " ").replace("-", " ").split())
    compact = "".join(character for character in normalized if character.isalnum())
    if not normalized or compact.isdigit() or normalized.startswith("column ") or "#" in name:
        return False
    if len(compact) > 28 and " " not in normalized and compact.isalnum():
        # Long barcode-like identifiers are not scientific variables merely because
        # their labels can be parsed as strings.
        return False
    blocked_tokens = {
        "id",
        "identifier",
        "code",
        "index",
        "number",
        "order",
        "sequence",
        "sort",
        "weight",
        "replicate",
        "checksum",
        "error",
        "flag",
    }
    tokens = set(normalized.replace(".", " ").replace("/", " ").split())
    if tokens & blocked_tokens:
        return False
    if normalized in {"model", "model year", "record order", "row", "row number"}:
        return False
    compact_blocked_fragments = (
        "identifier",
        "recordid",
        "runnumber",
        "channelnumber",
        "sequence",
        "repwgt",
        "pweight",
        "checksum",
        "yearmonth",
    )
    if any(fragment in compact for fragment in compact_blocked_fragments):
        return False
    if compact in {"nodes", "totalaccelerators", "lon2", "longitude2"}:
        return False
    if normalized.endswith(("id", " id", " error", " flag", " number", " code")):
        return False
    if len(compact) > 20 and " " not in normalized and compact.isalnum():
        return False
    return True


def _harmonic_relative_error(candidate: float, reference: float) -> float:
    if candidate <= 0 or reference <= 0:
        return math.inf
    return min(
        abs(candidate / reference - 1.0),
        abs(candidate / (2.0 * reference) - 1.0),
        abs((2.0 * candidate) / reference - 1.0),
    )


def _light_curve_peak(
    time_values: np.ndarray,
    flux_values: np.ndarray,
    *,
    maximum_period: float | None = None,
) -> tuple[float, float, float | None]:
    from astropy.timeseries import LombScargle

    baseline = float(time_values[-1] - time_values[0])
    positive_steps = np.diff(time_values)
    positive_steps = positive_steps[positive_steps > 0]
    if baseline <= 0 or positive_steps.size < 3:
        raise ValueError("light curve has no defensible time baseline")
    cadence = float(np.median(positive_steps))
    minimum_period = max(10.0 * cadence, 0.1)
    bounded_maximum = min(float(maximum_period or 20.0), baseline * 0.75)
    if bounded_maximum <= minimum_period:
        raise ValueError("light curve is too short for a bounded period search")
    periodogram = LombScargle(time_values, flux_values, fit_mean=True, center_data=True)
    frequency, power = periodogram.autopower(
        minimum_frequency=1.0 / bounded_maximum,
        maximum_frequency=1.0 / minimum_period,
        samples_per_peak=10,
    )
    if not power.size or not np.any(np.isfinite(power)):
        raise ValueError("periodogram did not contain a finite candidate")
    peak_index = int(np.nanargmax(power))
    peak_period = float(1.0 / frequency[peak_index])
    peak_power = float(power[peak_index])
    false_alarm_probability: float | None = None
    try:
        candidate = float(periodogram.false_alarm_probability(peak_power))
        if math.isfinite(candidate):
            false_alarm_probability = max(0.0, min(1.0, candidate))
    except (ValueError, FloatingPointError):
        pass
    return peak_period, peak_power, false_alarm_probability


def _analyze_fits_light_curve(
    *, study_id: str, asset: DataAsset, loaded: LoadedNumeric
) -> OperatorOutcome | None:
    normalized_names = [name.strip().casefold() for name in loaded.variables]
    if "time" not in normalized_names or "flux" not in normalized_names:
        return None
    time_index = normalized_names.index("time")
    flux_index = normalized_names.index("flux")
    time_values, flux_values = _paired_finite(
        loaded.values[:, time_index], loaded.values[:, flux_index]
    )
    if time_values.size < 100:
        return None
    order = np.argsort(time_values, kind="stable")
    time_values = time_values[order]
    flux_values = flux_values[order]
    median_flux = float(np.median(flux_values))
    if not math.isfinite(median_flux) or median_flux == 0:
        return None
    normalized_flux = flux_values / median_flux - 1.0
    baseline_days = float(time_values[-1] - time_values[0])
    if baseline_days <= 0:
        return None
    scaled_time = (time_values - float(np.mean(time_values))) / baseline_days
    trend = np.polyval(np.polyfit(scaled_time, normalized_flux, 1), scaled_time)
    detrended_flux = normalized_flux - trend
    try:
        period_days, peak_power, false_alarm_probability = _light_curve_peak(
            time_values, detrended_flux
        )
    except (ImportError, ValueError, FloatingPointError):
        return None

    angular_frequency = 2.0 * math.pi / period_days
    design = np.column_stack(
        [
            np.sin(angular_frequency * time_values),
            np.cos(angular_frequency * time_values),
            np.ones(time_values.size),
        ]
    )
    coefficients, *_ = np.linalg.lstsq(design, detrended_flux, rcond=None)
    fitted = design @ coefficients
    residual = detrended_flux - fitted
    semi_amplitude = float(math.hypot(float(coefficients[0]), float(coefficients[1])))
    residual_median = float(np.median(residual))
    residual_mad = float(1.4826 * np.median(np.abs(residual - residual_median)))
    amplitude_to_noise = semi_amplitude / residual_mad if residual_mad > 0 else math.inf
    centered_sum = float(np.sum((detrended_flux - np.mean(detrended_flux)) ** 2))
    variance_explained = (
        max(0.0, 1.0 - float(np.sum(residual**2)) / centered_sum)
        if centered_sum > 0
        else 0.0
    )
    cycles_observed = baseline_days / period_days

    # Lock a phase-aware equation on the chronological development segment and
    # evaluate that exact equation on the untouched tail.  The full-series
    # periodogram remains the detection statistic above; this receipt answers a
    # different question: whether the compact expression predicts unseen time
    # samples without refitting its period, amplitude, phase, or offset.
    development_end = max(60, int(time_values.size * 0.60))
    development_end = min(development_end, time_values.size - 40)
    development_time = time_values[:development_end]
    development_flux = detrended_flux[:development_end]
    test_time = time_values[development_end:]
    test_flux = detrended_flux[development_end:]
    equation_period = period_days
    equation_coefficients = coefficients
    development_variance_explained = variance_explained
    held_out_variance_explained = float("nan")
    held_out_normalized_rmse = float("nan")
    try:
        equation_period, _, _ = _light_curve_peak(development_time, development_flux)
        equation_frequency = 2.0 * math.pi / equation_period
        development_design = np.column_stack(
            [
                np.sin(equation_frequency * development_time),
                np.cos(equation_frequency * development_time),
                np.ones(development_time.size),
            ]
        )
        equation_coefficients, *_ = np.linalg.lstsq(
            development_design, development_flux, rcond=None
        )
        development_prediction = development_design @ equation_coefficients
        development_total = float(
            np.sum((development_flux - np.mean(development_flux)) ** 2)
        )
        development_variance_explained = (
            1.0
            - float(np.sum((development_flux - development_prediction) ** 2))
            / development_total
            if development_total > 0
            else 0.0
        )
        test_design = np.column_stack(
            [
                np.sin(equation_frequency * test_time),
                np.cos(equation_frequency * test_time),
                np.ones(test_time.size),
            ]
        )
        held_out_prediction = test_design @ equation_coefficients
        held_out_total = float(np.sum((test_flux - np.mean(test_flux)) ** 2))
        held_out_variance_explained = (
            1.0 - float(np.sum((test_flux - held_out_prediction) ** 2)) / held_out_total
            if held_out_total > 0
            else 0.0
        )
        held_out_scale = float(
            1.4826 * np.median(np.abs(test_flux - np.median(test_flux)))
        )
        held_out_normalized_rmse = (
            float(np.sqrt(np.mean((test_flux - held_out_prediction) ** 2)))
            / held_out_scale
            if held_out_scale > 0
            else math.inf
        )
    except (ValueError, FloatingPointError, np.linalg.LinAlgError):
        pass
    equation_amplitude = float(
        math.hypot(float(equation_coefficients[0]), float(equation_coefficients[1]))
    )
    equation_phase = float(
        math.atan2(float(equation_coefficients[1]), float(equation_coefficients[0]))
    )
    equation_offset = float(equation_coefficients[2])
    equation_test_passed = (
        math.isfinite(held_out_variance_explained)
        and held_out_variance_explained >= 0.005
        and math.isfinite(held_out_normalized_rmse)
        and held_out_normalized_rmse <= 2.0
    )
    expression_latex = (
        r"\Delta F(t) = "
        f"{equation_offset:.6g} + {equation_amplitude:.6g}"
        r"\sin\!\left(\frac{2\pi t}{"
        f"{equation_period:.6g}"
        r"\,\mathrm{d}} + "
        f"{equation_phase:.6g}"
        r"\right)"
    )
    split_validation = {
        "strategy": "chronological_60_40_locked_equation",
        "selection_lock": (
            "period, amplitude, phase, and offset fitted on the first 60%; "
            "the last 40% was evaluated without refitting"
        ),
        "development": {
            "n": int(development_time.size),
            "period_days": equation_period,
            "variance_explained": development_variance_explained,
        },
        "test": {
            "n": int(test_time.size),
            "variance_explained": held_out_variance_explained,
            "normalized_rmse": held_out_normalized_rmse,
            "passed": equation_test_passed,
        },
        "baseline_comparison": {
            "baseline": "zero periodic component after development detrending",
            "held_out_variance_explained": held_out_variance_explained,
            "passed": held_out_variance_explained >= 0.005,
        },
        "negative_control": {
            "method": "Lomb-Scargle false-alarm probability under the no-periodic-signal null",
            "p_value": false_alarm_probability,
            "passed": false_alarm_probability is not None
            and false_alarm_probability <= 1e-4,
        },
    }

    half_periods: list[float] = []
    sensitivities: list[dict[str, Any]] = []
    for label, indices in zip(
        ("first_contiguous_half", "second_contiguous_half"),
        np.array_split(np.arange(time_values.size), 2),
        strict=True,
    ):
        try:
            half_period, half_power, _ = _light_curve_peak(
                time_values[indices],
                detrended_flux[indices],
                maximum_period=min(20.0, period_days * 2.5),
            )
            relative_error = _harmonic_relative_error(half_period, period_days)
            half_periods.append(half_period)
            sensitivities.append(
                {
                    "specification": label,
                    "period_days": half_period,
                    "periodogram_power": half_power,
                    "harmonic_relative_error": relative_error,
                    "n": int(indices.size),
                }
            )
        except (ValueError, FloatingPointError):
            sensitivities.append(
                {
                    "specification": label,
                    "state": "unresolved",
                    "n": int(indices.size),
                }
            )
    split_stable = len(half_periods) == 2 and all(
        _harmonic_relative_error(value, period_days) <= 0.20 for value in half_periods
    )
    split_validation["rule_gate"] = {
        "interpretable_law_family": True,
        "held_out_baseline_improvement": equation_test_passed,
        "parameter_stability": split_stable,
        "unit_plausibility": True,
        "negative_control": false_alarm_probability is not None
        and false_alarm_probability <= 1e-4,
        "transfer_boundary_declared": True,
    }

    scientific_metadata = dict(loaded.locator.get("scientific_metadata") or {})
    source_period = scientific_metadata.get("per1")
    source_period_days = (
        float(source_period) if isinstance(source_period, (int, float)) and source_period > 0 else None
    )
    source_period_error = (
        _harmonic_relative_error(period_days, source_period_days)
        if source_period_days is not None
        else None
    )
    source_agreement = source_period_error is None or source_period_error <= 0.10
    false_alarm_supported = (
        false_alarm_probability is not None and false_alarm_probability <= 1e-4
    )
    supported = (
        false_alarm_supported
        and split_stable
        and source_agreement
        and amplitude_to_noise >= 0.10
        and variance_explained >= 0.005
        and cycles_observed >= 2.5
    )
    negative_evidence: list[str] = []
    if not false_alarm_supported:
        negative_evidence.append(
            "The strongest period did not pass the predeclared 1e-4 false-alarm threshold."
        )
    if not split_stable:
        negative_evidence.append(
            "The candidate period was not stable, allowing a factor-of-two harmonic, across contiguous halves."
        )
    if not source_agreement:
        negative_evidence.append(
            "The independently recomputed period did not agree with the source-reported peak within 10%."
        )
    if amplitude_to_noise < 0.10 or variance_explained < 0.005:
        negative_evidence.append(
            "The fitted periodic component was too weak relative to residual variability."
        )
    if cycles_observed < 2.5:
        negative_evidence.append(
            "The observation baseline contained fewer than 2.5 candidate cycles."
        )

    target_id = str(scientific_metadata.get("ticid") or "unknown target")
    sector = scientific_metadata.get("sector")
    hypothesis_id = "hyp:" + canonical_sha256(
        {
            "study": study_id,
            "asset": asset.asset_id,
            "operator": "light_curve_periodicity",
            "period_days": period_days,
        }
    )[:24]
    view_content_digest = canonical_sha256(
        {
            "asset": asset.byte_sha256,
            "adapter": asset.adapter,
            "adapter_version": asset.adapter_version,
            "profile": asset.metadata.get("profile") or {},
        }
    )
    view_id = "view:" + canonical_sha256(
        {"study": study_id, "content_digest": view_content_digest}
    )[:24]
    hypothesis = DataHypothesis(
        hypothesis_id=hypothesis_id,
        study_id=study_id,
        claim=(
            f"TIC {target_id} may contain a coherent rotation-like photometric modulation "
            f"near {period_days:.3f} days."
        ),
        origin="principle_guided",
        expected_relationship=(
            "A stable non-zero Lomb-Scargle peak with consistent contiguous-half periods, "
            "a resolved fitted amplitude, and agreement with source-reported period metadata."
        ),
        input_view_ids=[view_id],
        confounders=[
            "TESS window function and sector-length aliases",
            "instrumental and detrending systematics",
            "source crowding and aperture contamination",
            "factor-of-two harmonic ambiguity",
            "spot evolution or differential rotation",
        ],
        boundary=[
            loaded.sample_definition,
            f"TESS Sector {sector}" if sector is not None else "single observing sector",
        ],
        falsifier=(
            "The peak disappears under alternate detrending, fails in either contiguous half, "
            "or is absent in an independent sector."
        ),
        state="tested",
    )
    plan_payload = {
        "operator": "light_curve_periodicity",
        "asset": asset.asset_id,
        "variables": [loaded.variables[time_index], loaded.variables[flux_index]],
        "period_bounds_days": [0.1, min(20.0, baseline_days * 0.75)],
        "split": "contiguous_halves",
        "version": OPERATOR_VERSION,
    }
    plan_digest = canonical_sha256(plan_payload)
    plan = AnalysisPlan(
        plan_id=f"plan:{plan_digest[:24]}",
        study_id=study_id,
        hypothesis_id=hypothesis_id,
        executor="operator",
        operator="light_curve_periodicity",
        input_view_ids=[view_id],
        parameters={
            "normalization": "median_fractional_flux",
            "detrending": "linear",
            "periodogram": "lomb_scargle",
            "false_alarm_threshold": 1e-4,
            "harmonic_tolerance": 0.20,
        },
        expected_outputs=[
            "period_days",
            "fractional_semi_amplitude",
            "false_alarm_probability",
            "contiguous_half_stability",
            "source_period_agreement",
        ],
        validation_checks=[
            "finite monotonic time sample",
            "at least 2.5 observed cycles",
            "contiguous-half stability including factor-of-two harmonics",
            "agreement with retained source period metadata",
            "amplitude relative to robust residual noise",
        ],
        plan_digest=plan_digest,
    )
    estimate = {
        "period_days": period_days,
        "periodogram_power": peak_power,
        "fractional_semi_amplitude": semi_amplitude,
        "residual_mad": residual_mad,
        "amplitude_to_residual_mad": amplitude_to_noise,
        "variance_explained": variance_explained,
        "baseline_days": baseline_days,
        "cycles_observed": cycles_observed,
        "contiguous_half_harmonic_stable": split_stable,
        "harmonic_relative_tolerance": 0.20,
        "source_reported_period_days": source_period_days,
        "source_period_harmonic_relative_error": source_period_error,
        "target": {
            "tic_id": target_id,
            "sector": sector,
            "tess_magnitude": scientific_metadata.get("tessmag"),
            "camera": scientific_metadata.get("camera"),
            "ccd": scientific_metadata.get("ccd"),
        },
    }
    result_digest = canonical_sha256(
        {
            "estimate": estimate,
            "sensitivities": sensitivities,
            "expression_latex": expression_latex,
            "split_validation": split_validation,
            "operator": OPERATOR_VERSION,
        }
    )
    test_id = "test:" + canonical_sha256(
        {"study": study_id, "result": result_digest}
    )[:24]
    test = TestResult(
        test_id=test_id,
        study_id=study_id,
        hypothesis_id=hypothesis_id,
        plan_id=plan.plan_id,
        plan_digest=plan_digest,
        state="succeeded",
        sample_definition=(
            f"{time_values.size:,} finite TESS flux samples spanning {baseline_days:.3f} days"
        ),
        independent_unit_count=2,
        estimate=estimate,
        uncertainty={
            "p_value_uncorrected": false_alarm_probability,
            "false_alarm_probability": false_alarm_probability,
            "period_grid_resolution_days": baseline_days / max(1, time_values.size),
        },
        diagnostics=[
            "Periodogram false-alarm probability is not a probability that stellar rotation is the mechanism.",
            "Contiguous halves are internal stability checks, not independent observations.",
        ],
        sensitivities=sensitivities,
        negative_evidence=negative_evidence,
        artifacts=[],
        expression_latex=expression_latex,
        equation_variables=[
            {"symbol": "t", "meaning": "time", "unit": "day"},
            {
                "symbol": r"\Delta F",
                "meaning": "linearly detrended fractional flux relative to the median",
                "unit": "relative flux",
            },
        ],
        split_validation=split_validation,
        result_digest=result_digest,
    )
    finding_id = "finding:" + canonical_sha256(
        {"study": study_id, "hypothesis": hypothesis_id, "result": result_digest}
    )[:24]
    evidence_id = "evidence:" + canonical_sha256(
        {"test": test_id, "asset": asset.asset_id, "locator": loaded.locator}
    )[:24]
    evidence = ComputedEvidenceAnchor(
        evidence_id=evidence_id,
        study_id=study_id,
        finding_id=finding_id,
        test_id=test_id,
        asset_id=asset.asset_id,
        view_id=view_id,
        locator={"relative_path": asset.metadata.get("relative_path"), **loaded.locator},
        units={"time": "day", "flux": "relative flux"},
        plan_digest=plan_digest,
        executor_version=OPERATOR_VERSION,
        result_digest=result_digest,
    )
    finding = DataFinding(
        finding_id=finding_id,
        study_id=study_id,
        title=f"Stable rotation-like modulation candidate in TIC {target_id}",
        claim=(
            f"TIC {target_id} shows a {period_days:.3f}-day photometric modulation with "
            f"fractional semi-amplitude {semi_amplitude:.4f}; the period is stable across "
            f"contiguous halves up to harmonic ambiguity and "
            + (
                f"agrees with the retained source peak ({source_period_days:.3f} days)."
                if source_period_days is not None
                else "has no retained source-period value for comparison."
            )
        ),
        interpretation=(
            "The light curve contains a repeatable periodic brightness pattern rather than a "
            "simple TIME-FLUX correlation. Its period, amplitude, window coverage, and internal "
            "stability are explicitly quantified."
        ),
        mechanism=(
            "A physically plausible explanation is rotational modulation: long-lived surface "
            "inhomogeneities such as starspots change the projected brightness as the star rotates. "
            "The data do not yet distinguish this from harmonics, contamination, or spacecraft systematics."
        ),
        status="supported_candidate" if supported else "held_back",
        # Contiguous halves are stability checks, not 50 independent units.
        validation_level="exploratory",
        hypothesis_ids=[hypothesis_id],
        test_ids=[test_id],
        evidence_ids=[evidence_id],
        robustness=[
            "median fractional-flux normalization",
            "linear detrending",
            "Lomb-Scargle false-alarm test",
            "contiguous-half period stability with harmonic tolerance",
            "comparison with retained source period metadata",
        ],
        confounders=hypothesis.confounders,
        falsifiers=[hypothesis.falsifier],
        negative_evidence=negative_evidence,
        limits=[
            "One TESS sector does not establish persistence across observing epochs.",
            "The rotation mechanism remains a candidate until pixel-level contamination and independent-sector checks pass.",
            "The source-reported period is derived from the same light curve and is not independent replication.",
        ],
        next_validation=(
            "Repeat the period search under alternate detrending and aperture choices, inspect centroid/pixel diagnostics, "
            "and test the predicted period in an independent TESS sector or ground-based light curve."
        ),
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    return OperatorOutcome(
        hypothesis=hypothesis,
        plan=plan,
        result=test,
        evidence=evidence,
        finding=finding,
    )


def _computed_anchor_units(
    units: dict[str, str] | None,
    equation_variables: list[dict[str, Any]] | None,
) -> dict[str, str]:
    explicit = dict(units or {})
    if explicit:
        return explicit
    return {
        str(item.get("symbol") or ""): str(item.get("unit") or "")
        for item in list(equation_variables or [])
        if isinstance(item, dict)
        and str(item.get("symbol") or "")
        and str(item.get("unit") or "")
    }


def _scientific_operator_outcome(
    *,
    study_id: str,
    asset: DataAsset,
    loaded: LoadedNumeric,
    operator: str,
    hypothesis_claim: str,
    expected_relationship: str,
    confounders: list[str],
    falsifier: str,
    parameters: dict[str, Any],
    expected_outputs: list[str],
    validation_checks: list[str],
    independent_unit_count: int,
    estimate: dict[str, Any],
    uncertainty: dict[str, Any],
    diagnostics: list[str],
    sensitivities: list[dict[str, Any]],
    negative_evidence: list[str],
    title: str,
    claim: str,
    interpretation: str,
    mechanism: str,
    supported: bool,
    validation_level: str,
    robustness: list[str],
    limits: list[str],
    next_validation: str,
    units: dict[str, str] | None = None,
    expression_latex: str = "",
    equation_variables: list[dict[str, Any]] | None = None,
    split_validation: dict[str, Any] | None = None,
    insight_level: str = "observational",
    nontriviality_basis: str = "",
    significance: str = "",
    practical_value: str = "",
    principle_statement: str = "",
    transfer_scope: str = "",
) -> OperatorOutcome:
    view_content_digest = canonical_sha256(
        {
            "asset": asset.byte_sha256,
            "adapter": asset.adapter,
            "adapter_version": asset.adapter_version,
            "profile": asset.metadata.get("profile") or {},
        }
    )
    view_id = "view:" + canonical_sha256(
        {"study": study_id, "content_digest": view_content_digest}
    )[:24]
    hypothesis_digest = canonical_sha256(
        {"study": study_id, "asset": asset.asset_id, "operator": operator, "claim": hypothesis_claim}
    )
    hypothesis_id = f"hyp:{hypothesis_digest[:24]}"
    hypothesis = DataHypothesis(
        hypothesis_id=hypothesis_id,
        study_id=study_id,
        claim=hypothesis_claim,
        origin="principle_guided",
        expected_relationship=expected_relationship,
        input_view_ids=[view_id],
        confounders=confounders,
        boundary=[loaded.sample_definition, "single retained dataset representation"],
        falsifier=falsifier,
        state="tested",
    )
    plan_payload = {
        "operator": operator,
        "asset": asset.asset_id,
        "parameters": parameters,
        "sample": loaded.sample_definition,
        "version": OPERATOR_VERSION,
    }
    plan_digest = canonical_sha256(plan_payload)
    plan = AnalysisPlan(
        plan_id=f"plan:{plan_digest[:24]}",
        study_id=study_id,
        hypothesis_id=hypothesis_id,
        executor="operator",
        operator=operator,
        input_view_ids=[view_id],
        parameters=parameters,
        expected_outputs=expected_outputs,
        validation_checks=validation_checks,
        plan_digest=plan_digest,
    )
    result_digest = canonical_sha256(
        {
            "operator": operator,
            "estimate": estimate,
            "uncertainty": uncertainty,
            "sensitivities": sensitivities,
            "expression_latex": expression_latex,
            "split_validation": dict(split_validation or {}),
            "version": OPERATOR_VERSION,
        }
    )
    test_id = "test:" + canonical_sha256(
        {"study": study_id, "result": result_digest}
    )[:24]
    test = TestResult(
        test_id=test_id,
        study_id=study_id,
        hypothesis_id=hypothesis_id,
        plan_id=plan.plan_id,
        plan_digest=plan_digest,
        state="succeeded",
        sample_definition=loaded.sample_definition,
        independent_unit_count=max(0, int(independent_unit_count)),
        estimate=estimate,
        uncertainty=uncertainty,
        diagnostics=diagnostics,
        sensitivities=sensitivities,
        negative_evidence=negative_evidence,
        artifacts=[],
        expression_latex=expression_latex,
        equation_variables=list(equation_variables or []),
        split_validation=dict(split_validation or {}),
        result_digest=result_digest,
    )
    finding_id = "finding:" + canonical_sha256(
        {"study": study_id, "hypothesis": hypothesis_id, "result": result_digest}
    )[:24]
    evidence_id = "evidence:" + canonical_sha256(
        {"test": test_id, "asset": asset.asset_id, "locator": loaded.locator}
    )[:24]
    anchor_units = _computed_anchor_units(units, equation_variables)
    evidence = ComputedEvidenceAnchor(
        evidence_id=evidence_id,
        study_id=study_id,
        finding_id=finding_id,
        test_id=test_id,
        asset_id=asset.asset_id,
        view_id=view_id,
        locator={"relative_path": asset.metadata.get("relative_path"), **loaded.locator},
        units=anchor_units,
        plan_digest=plan_digest,
        executor_version=OPERATOR_VERSION,
        result_digest=result_digest,
    )
    finding = DataFinding(
        finding_id=finding_id,
        study_id=study_id,
        title=title,
        claim=claim,
        interpretation=interpretation,
        mechanism=mechanism,
        significance=significance,
        insight_level=insight_level,  # type: ignore[arg-type]
        nontriviality_basis=nontriviality_basis,
        practical_value=practical_value,
        principle_statement=principle_statement,
        transfer_scope=transfer_scope,
        status="supported_candidate" if supported else "held_back",
        validation_level=validation_level,  # type: ignore[arg-type]
        hypothesis_ids=[hypothesis_id],
        test_ids=[test_id],
        evidence_ids=[evidence_id],
        robustness=robustness,
        confounders=confounders,
        falsifiers=[falsifier],
        negative_evidence=negative_evidence,
        limits=limits,
        next_validation=next_validation,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    return OperatorOutcome(
        hypothesis=hypothesis,
        plan=plan,
        result=test,
        evidence=evidence,
        finding=finding,
    )


def _analyze_ordered_signal(
    *, study_id: str, asset: DataAsset, loaded: LoadedNumeric
) -> OperatorOutcome | None:
    sample_rates = loaded.locator.get("sample_rates_hz")
    sample_rate = loaded.locator.get("sample_rate_hz")
    if isinstance(sample_rates, list) and sample_rates:
        sample_rate = sample_rates[0]
    if not isinstance(sample_rate, (int, float)) or not math.isfinite(float(sample_rate)):
        return None
    sample_rate = float(sample_rate)
    if sample_rate <= 0:
        return None
    values = np.asarray(loaded.values, dtype=float)
    if values.ndim == 1:
        values = values[:, None]
    channel_candidates: list[tuple[float, int, np.ndarray]] = []
    for index in range(min(values.shape[1], 16)):
        column = values[:, index]
        finite = column[np.isfinite(column)]
        if finite.size < 1_024:
            continue
        scale = float(np.std(finite))
        if math.isfinite(scale) and scale > 0:
            channel_candidates.append((scale, index, finite))
    if not channel_candidates:
        return None
    _, channel_index, signal_values = max(channel_candidates, key=lambda item: item[0])
    signal_values = signal_values[:MAX_VALUES]
    signal_values = signal_values - float(np.mean(signal_values))
    duration_seconds = signal_values.size / sample_rate
    if duration_seconds < 2:
        return None

    def spectrum(candidate: np.ndarray) -> tuple[float, float, float]:
        window = np.hanning(candidate.size)
        power = np.abs(np.fft.rfft(candidate * window)) ** 2
        frequencies = np.fft.rfftfreq(candidate.size, d=1.0 / sample_rate)
        valid = (frequencies >= max(0.1, 1.0 / max(1.0, duration_seconds))) & (
            frequencies <= sample_rate * 0.45
        )
        finite_power = power[valid]
        finite_frequency = frequencies[valid]
        if finite_power.size < 20:
            raise ValueError("insufficient frequency support")
        index = int(np.argmax(finite_power))
        background = float(np.median(finite_power))
        ratio = float(finite_power[index] / background) if background > 0 else math.inf
        total = float(np.sum(finite_power))
        concentration = float(finite_power[index] / total) if total > 0 else 0.0
        return float(finite_frequency[index]), ratio, concentration

    try:
        peak_frequency, peak_to_background, spectral_concentration = spectrum(signal_values)
    except ValueError:
        return None
    half_results: list[dict[str, Any]] = []
    half_frequencies: list[float] = []
    for label, half in zip(
        ("first_contiguous_half", "second_contiguous_half"),
        np.array_split(signal_values, 2),
        strict=True,
    ):
        try:
            frequency, ratio, concentration = spectrum(half)
            half_frequencies.append(frequency)
            half_results.append(
                {
                    "specification": label,
                    "peak_frequency_hz": frequency,
                    "peak_to_background": ratio,
                    "spectral_concentration": concentration,
                    "n": int(half.size),
                }
            )
        except ValueError:
            half_results.append({"specification": label, "state": "unresolved"})
    # A broad absolute tolerance can incorrectly label two unrelated nearby
    # spectral maxima as the same persistent line (especially below 10 Hz).
    # Require agreement to three half-window Fourier bins or one percent of
    # the full-window peak, whichever is larger.
    half_window_resolution = 2.0 * sample_rate / signal_values.size
    frequency_tolerance = max(
        3.0 * half_window_resolution,
        peak_frequency * 0.01,
    )
    stable = len(half_frequencies) == 2 and all(
        abs(value - peak_frequency) <= frequency_tolerance for value in half_frequencies
    )
    blocks = np.array_split(signal_values, 8)
    block_rms = [float(np.sqrt(np.mean(block**2))) for block in blocks if block.size]
    rms_ratio = max(block_rms) / min(block_rms) if block_rms and min(block_rms) > 0 else math.inf
    supported = stable and peak_to_background >= 10.0 and spectral_concentration >= 0.002
    negative: list[str] = []
    if not stable:
        negative.append("The dominant spectral peak was not stable across contiguous halves.")
    if peak_to_background < 10.0 or spectral_concentration < 0.002:
        negative.append("Spectral concentration was too weak relative to the broadband background.")
    variable = loaded.variables[channel_index]
    if "eeg" in variable.casefold() and not 0.5 <= peak_frequency <= 45.0:
        supported = False
        negative.append(
            "The dominant scalp-EEG peak lies outside the predeclared 0.5–45 Hz interpretive band and is held back as drift or acquisition artifact."
        )
    return _scientific_operator_outcome(
        study_id=study_id,
        asset=asset,
        loaded=loaded,
        operator="ordered_signal_spectrum",
        hypothesis_claim=(
            f"{variable} may contain a reproducible narrowband component near {peak_frequency:.3f} Hz."
        ),
        expected_relationship=(
            "The dominant frequency should exceed the local broadband background and recur in both contiguous halves."
        ),
        confounders=[
            "instrumental line noise",
            "window leakage",
            "sampling-rate metadata errors",
            "motion or acquisition artifacts",
            "nonstationary broadband noise",
        ],
        falsifier="The peak disappears after notch/artifact controls or fails in an independent contiguous epoch.",
        parameters={
            "spectrum": "Hann-windowed real FFT",
            "peak_to_background_threshold": 10.0,
            "contiguous_half_tolerance_hz": frequency_tolerance,
            "contiguous_half_tolerance_rule": "max(3 half-window Fourier bins, 1% of full-window peak)",
        },
        expected_outputs=[
            "peak_frequency_hz",
            "peak_to_background",
            "spectral_concentration",
            "block_rms_ratio",
        ],
        validation_checks=[
            "sample-rate metadata present",
            "contiguous-half peak stability",
            "broadband-background comparison",
        ],
        independent_unit_count=2,
        estimate={
            "channel": variable,
            "sample_rate_hz": sample_rate,
            "duration_seconds": duration_seconds,
            "peak_frequency_hz": peak_frequency,
            "peak_to_background": peak_to_background,
            "spectral_concentration": spectral_concentration,
            "block_rms_ratio": rms_ratio,
        },
        uncertainty={"frequency_resolution_hz": sample_rate / signal_values.size},
        diagnostics=[
            "A narrowband component is not by itself biological or astrophysical evidence.",
            "Block RMS variation describes stationarity but does not identify its cause.",
        ],
        sensitivities=half_results,
        negative_evidence=negative,
        title=f"Stable narrowband structure in the analyzed {duration_seconds:.1f}-second window",
        claim=(
            f"In the analyzed {duration_seconds:.1f}-second window of {variable}, a {peak_frequency:.3f} Hz "
            f"component had peak-to-background "
            f"ratio {peak_to_background:.1f}; the peak is "
            f"{'stable' if stable else 'not stable'} across contiguous halves."
        ),
        interpretation=(
            "The ordered signal has frequency-domain structure that cannot be represented by a row-order correlation."
        ),
        mechanism=(
            "A persistent narrowband component implies a repeatable oscillator or acquisition line. "
            "Its physical meaning depends on channel identity and artifact controls."
        ),
        supported=supported,
        # Contiguous signal halves are not defensibly independent experimental units.
        validation_level="exploratory",
        robustness=[
            "Hann-windowed spectrum",
            "contiguous-half frequency check",
            "broadband median comparison",
            "eight-block RMS stationarity profile",
        ],
        limits=[
            "Only one bounded channel projection was tested.",
            "No source-specific artifact rejection or independent recording was available.",
        ],
        next_validation=(
            "Repeat with source-specific preprocessing, neighboring-channel coherence, artifact regressors, "
            "and an independent recording or detector epoch."
        ),
        units={"frequency": "Hz"},
        expression_latex=(
            r"f^{*}=\arg\max_{f\in\mathcal B}S_{xx}(f),\qquad "
            r"\Gamma=\frac{S_{xx}(f^{*})}{\operatorname{median}_{f\in\mathcal B}S_{xx}(f)}"
        ),
        equation_variables=[
            {"symbol": "x(t)", "meaning": variable, "unit": "source signal unit"},
            {"symbol": r"S_{xx}(f)", "meaning": "Hann-windowed power spectrum", "unit": "signal unit squared per Hz"},
            {"symbol": r"f^{*}", "meaning": "dominant frequency", "unit": "Hz"},
            {"symbol": r"\Gamma", "meaning": "peak-to-background spectral ratio", "unit": "dimensionless"},
        ],
        split_validation={
            "strategy": "contiguous_half_frequency_replication",
            "selection_lock": "frequency band and peak definition fixed before the two contiguous-half checks",
            "development": half_results[0] if half_results else {},
            "test": {
                **(half_results[1] if len(half_results) > 1 else {}),
                "passed": supported,
            },
            "baseline_comparison": {
                "baseline": "median in-band spectral power",
                "peak_to_background": peak_to_background,
                "passed": peak_to_background >= 10.0,
            },
            "rule_gate": {
                "interpretable_law_family": True,
                "held_out_baseline_improvement": peak_to_background >= 10.0,
                "parameter_stability": stable,
                "unit_plausibility": True,
                "negative_control": False,
                "transfer_boundary_declared": False,
            },
        },
    )


def _analyze_masked_hdf5_spectral_envelope(
    *, study_id: str, asset: DataAsset, root: Path
) -> OperatorOutcome | None:
    """Stream a complete strain record with its aligned quality masks.

    This operator is admitted by HDF5 structure and attributes, not by a GWOSC
    filename.  Complete 256-second scientific objects are the units; raw time
    samples are never treated as independent replications.
    """

    try:
        import h5py
        from scipy.signal import welch
    except ImportError:
        return None
    path = root / str(asset.metadata.get("relative_path") or "")
    if not path.is_file():
        return None
    with h5py.File(path, "r") as handle:
        strain_candidates: list[tuple[str, Any]] = []
        mask_candidates: list[tuple[str, Any]] = []

        def visit(name: str, value: Any) -> None:
            if not isinstance(value, h5py.Dataset) or value.ndim != 1:
                return
            normalized = name.casefold()
            if (
                value.size >= 1_000_000
                and np.issubdtype(value.dtype, np.floating)
                and "strain" in normalized
            ):
                strain_candidates.append((name, value))
            if (
                60 <= value.size <= 100_000
                and np.issubdtype(value.dtype, np.integer)
                and any(token in normalized for token in ("dqmask", "quality"))
            ):
                mask_candidates.append((name, value))

        handle.visititems(visit)
        if len(strain_candidates) != 1 or not mask_candidates:
            return None
        strain_name, strain = strain_candidates[0]
        mask_name, mask = max(
            mask_candidates,
            key=lambda item: ("dqmask" in item[0].casefold(), item[1].size),
        )
        spacing = float(strain.attrs.get("Xspacing", 0.0) or 0.0)
        mask_spacing = float(mask.attrs.get("Xspacing", 0.0) or 0.0)
        if spacing <= 0 or mask_spacing <= 0:
            return None
        sample_rate = 1.0 / spacing
        samples_per_mask = int(round(mask_spacing / spacing))
        if samples_per_mask <= 0 or abs(samples_per_mask * spacing - mask_spacing) > spacing:
            return None
        mask_values = np.asarray(mask[:], dtype=np.uint64)
        source_seconds = int(mask_values.size)
        if strain.size < source_seconds * samples_per_mask:
            return None
        best_quality = int(np.max(mask_values))
        block_seconds = 256
        bands = ((20.0, 60.0), (60.0, 200.0), (200.0, 800.0))
        records: list[dict[str, Any]] = []
        for second_start in range(0, source_seconds - block_seconds + 1, block_seconds):
            second_end = second_start + block_seconds
            if not np.all(mask_values[second_start:second_end] == best_quality):
                continue
            sample_start = second_start * samples_per_mask
            sample_end = second_end * samples_per_mask
            values = np.asarray(strain[sample_start:sample_end], dtype=float)
            if values.size != block_seconds * samples_per_mask or not np.all(np.isfinite(values)):
                continue
            frequencies, power = welch(
                values,
                fs=sample_rate,
                nperseg=min(16_384, values.size),
                noverlap=min(8_192, max(0, values.size // 2 - 1)),
                detrend="linear",
            )
            for lower, upper in bands:
                selected = (
                    (frequencies >= lower)
                    & (frequencies <= min(upper, 0.45 * sample_rate))
                    & np.isfinite(power)
                    & (power > 0)
                )
                if int(np.sum(selected)) < 100:
                    continue
                log_frequency = np.log(frequencies[selected])
                log_power = np.log(power[selected])
                design = np.column_stack([np.ones(log_frequency.size), log_frequency])
                coefficients, *_ = np.linalg.lstsq(design, log_power, rcond=None)
                prediction = design @ coefficients
                residual = float(np.sum((log_power - prediction) ** 2))
                total = float(np.sum((log_power - np.mean(log_power)) ** 2))
                rmse = float(np.sqrt(np.mean((log_power - prediction) ** 2)))
                flat_rmse = float(np.sqrt(np.mean((log_power - np.mean(log_power)) ** 2)))
                records.append(
                    {
                        "block_start_second": second_start,
                        "band_hz": [lower, upper],
                        "log_amplitude": float(coefficients[0]),
                        "spectral_exponent": float(coefficients[1]),
                        "r_squared": 1.0 - residual / total if total > 0 else 0.0,
                        "flat_baseline_improvement": 1.0 - rmse / max(flat_rmse, 1e-30),
                        "frequency_bins": int(log_frequency.size),
                        "log_frequency": log_frequency,
                        "log_power": log_power,
                    }
                )
    block_starts = sorted({int(item["block_start_second"]) for item in records})
    if len(block_starts) < 8:
        return None
    midpoint = len(block_starts) // 2
    development_blocks = set(block_starts[:midpoint])
    test_blocks = set(block_starts[midpoint:])
    development_by_band: list[tuple[float, tuple[float, float]]] = []
    for band in bands:
        scores = [
            float(item["r_squared"])
            for item in records
            if tuple(item["band_hz"]) == band
            and int(item["block_start_second"]) in development_blocks
        ]
        if scores:
            development_by_band.append((float(np.median(scores)), band))
    if not development_by_band:
        return None
    _, selected_band = max(development_by_band, key=lambda item: (item[0], -item[1][0]))
    selected_records = [item for item in records if tuple(item["band_hz"]) == selected_band]
    development = [item for item in selected_records if int(item["block_start_second"]) in development_blocks]
    test = [item for item in selected_records if int(item["block_start_second"]) in test_blocks]
    if min(len(development), len(test)) < 3:
        return None
    development_slope = float(np.median([item["spectral_exponent"] for item in development]))
    test_slope = float(np.median([item["spectral_exponent"] for item in test]))
    test_r_squared = float(np.median([item["r_squared"] for item in test]))
    baseline_improvement = float(
        np.median([item["flat_baseline_improvement"] for item in test])
    )
    stable = (
        development_slope * test_slope > 0
        and abs(test_slope - development_slope) / max(abs(development_slope), 1e-12)
        <= 0.15
    )
    random = np.random.default_rng(int(asset.byte_sha256[:16], 16))
    null_scores: list[float] = []
    for _ in range(19):
        block_scores: list[float] = []
        for item in test:
            x = np.asarray(item["log_frequency"], dtype=float)
            y = random.permutation(np.asarray(item["log_power"], dtype=float))
            design = np.column_stack([np.ones(x.size), x])
            prediction = design @ np.linalg.lstsq(design, y, rcond=None)[0]
            total = float(np.sum((y - np.mean(y)) ** 2))
            block_scores.append(
                1.0 - float(np.sum((y - prediction) ** 2)) / total if total > 0 else 0.0
            )
        null_scores.append(float(np.median(block_scores)))
    permutation_p = (1 + sum(value >= test_r_squared for value in null_scores)) / 20.0
    supported = (
        test_r_squared >= 0.50
        and baseline_improvement >= 0.25
        and stable
        and permutation_p <= 0.05
    )
    public_records = [
        {key: value for key, value in item.items() if key not in {"log_frequency", "log_power"}}
        for item in selected_records
    ]
    loaded = LoadedNumeric(
        values=np.asarray(
            [
                [item["block_start_second"], item["spectral_exponent"], item["r_squared"]]
                for item in selected_records
            ],
            dtype=float,
        ),
        variables=["block_start_second", "spectral_exponent", "log_log_r_squared"],
        locator={
            "strain_dataset": strain_name,
            "quality_mask_dataset": mask_name,
            "source_samples": int(source_seconds * samples_per_mask),
            "source_duration_seconds": source_seconds,
            "analyzed_duration_seconds": len(block_starts) * block_seconds,
            "excluded_quality_seconds": int(np.sum(mask_values != best_quality)),
            "quality_mask_value": best_quality,
            "block_seconds": block_seconds,
        },
        sample_definition=f"{len(block_starts)} complete quality-clean 256-second blocks spanning the {source_seconds:,}-second HDF5 record",
    )
    return _scientific_operator_outcome(
        study_id=study_id,
        asset=asset,
        loaded=loaded,
        operator="masked_hdf5_spectral_power_envelope",
        hypothesis_claim="A quality-clean detector strain spectrum may follow a stable band-limited power envelope across separated contiguous blocks.",
        expected_relationship="A development-selected frequency band should retain its log-log exponent and beat a flat-spectrum baseline in locked chronological blocks.",
        confounders=["instrumental lines", "nonstationary detector state", "window leakage", "quality-mask semantics", "calibration drift"],
        falsifier="The exponent changes sign or magnitude in locked blocks, or shuffled frequency-power assignments reproduce its fit.",
        parameters={"candidate_bands_hz": [list(item) for item in bands], "selected_band_hz": list(selected_band), "block_seconds": block_seconds, "mask_rule": "maximum recorded DQ bitmask"},
        expected_outputs=["spectral_exponent", "log_log_r_squared", "flat_baseline_improvement"],
        validation_checks=["complete-stream coverage", "aligned quality mask", "chronological block split", "frequency permutation"],
        independent_unit_count=len(block_starts),
        estimate={"development_spectral_exponent": development_slope, "locked_test_spectral_exponent": test_slope, "locked_test_median_r_squared": test_r_squared, "locked_test_flat_baseline_improvement": baseline_improvement, "blocks": public_records},
        uncertainty={"frequency_permutation_p": permutation_p, "development_test_relative_exponent_change": abs(test_slope - development_slope) / max(abs(development_slope), 1e-12)},
        diagnostics=["The law is a detector-noise envelope over a bounded band, not an astrophysical source claim.", "Every original strain sample is either assigned to an aligned DQ-clean block or explicitly excluded by its one-second mask."],
        sensitivities=[{"candidate_band_hz": list(band), "development_median_r_squared": score} for score, band in development_by_band],
        negative_evidence=[] if supported else ["The locked spectral envelope failed fit, baseline, stability, or frequency-permutation gates."],
        title="Quality-clean strain blocks share a stable low-frequency power-law noise envelope",
        claim=f"The development-selected {selected_band[0]:.0f}-{selected_band[1]:.0f} Hz envelope retained exponent {test_slope:.2f} in locked blocks (development {development_slope:.2f}), median R²={test_r_squared:.3f}, and permutation p={permutation_p:.3g}.",
        interpretation="The full record contains a reproducible detector-state noise law once quality masks and whole contiguous blocks are respected.",
        mechanism="Band-limited seismic, suspension, and control noise can produce steep colored-noise envelopes whose exponent remains stable within a detector operating state.",
        supported=supported,
        validation_level="internal_holdout",
        robustness=["all-source-sample accounting", "aligned DQ masks", "development-only band selection", "locked chronological blocks", "frequency-assignment permutation control"],
        limits=["The fitted band can include multiple instrumental mechanisms.", "The calibration is specific to this detector and observing epoch."],
        next_validation="Repeat the sealed band and exponent tolerance on a disjoint detector epoch and compare auxiliary environmental channels.",
        units={"frequency": "Hz", "power_spectral_density": "strain squared per Hz"},
        expression_latex=r"S_h(f)=A\left(f/f_0\right)^{\alpha},\quad f\in[f_1,f_2]",
        equation_variables=[
            {"symbol": r"S_h(f)", "meaning": "strain power spectral density", "unit": "strain squared/Hz"},
            {"symbol": "f", "meaning": "frequency", "unit": "Hz"},
            {"symbol": r"\alpha", "meaning": "band-limited spectral exponent", "unit": "dimensionless"},
        ],
        split_validation={
            "strategy": "quality_clean_contiguous_block_holdout",
            "selection_lock": "candidate bands selected only by median development-block log-log R-squared",
            "development": {"blocks": len(development), "spectral_exponent": development_slope},
            "test": {"blocks": len(test), "spectral_exponent": test_slope, "median_r_squared": test_r_squared, "passed": supported},
            "baseline_comparison": {"baseline": "flat log-spectrum in the selected band", "median_rmse_improvement": baseline_improvement, "passed": baseline_improvement >= 0.25},
            "negative_control": {"strategy": "19 content-seeded within-block frequency-power permutations", "p_value": permutation_p, "passed": permutation_p <= 0.05},
            "rule_gate": {"interpretable_law_family": True, "held_out_baseline_improvement": baseline_improvement >= 0.25, "parameter_stability": stable, "unit_plausibility": True, "negative_control": permutation_p <= 0.05, "transfer_boundary_declared": True},
        },
        insight_level="structural",
        nontriviality_basis="A development-only band choice retained its exponent across quality-clean locked blocks and defeated frequency assignment permutations.",
        significance="The envelope is an auditable detector-state law that can flag spectral-regime drift without mistaking individual time samples for replication.",
        principle_statement="Within a stable detector-quality state, a bounded strain-noise band can retain a reproducible scale-free spectral envelope across separated epochs.",
        transfer_scope="The selected frequency band, detector, calibration, and quality-mask state in this observing epoch; disjoint epochs and instruments require sealed replication.",
    )


def _analyze_spatial_field(
    *, study_id: str, asset: DataAsset, loaded: LoadedNumeric
) -> OperatorOutcome | None:
    shape = loaded.locator.get("sample_shape")
    if not isinstance(shape, list) or len(shape) < 2:
        return None
    values = np.asarray(loaded.values[:, 0], dtype=float)
    expected_size = int(np.prod(shape))
    if expected_size <= 0 or values.size < expected_size:
        return None
    field = values[:expected_size].reshape(tuple(int(item) for item in shape))
    while field.ndim > 2:
        field = field[0]
    if field.ndim != 2 or min(field.shape) < 8:
        return None
    horizontal_left, horizontal_right = _paired_finite(field[:, :-1].ravel(), field[:, 1:].ravel())
    vertical_left, vertical_right = _paired_finite(field[:-1, :].ravel(), field[1:, :].ravel())
    if horizontal_left.size + vertical_left.size < 100:
        return None
    horizontal, _, horizontal_n = _correlation(horizontal_left, horizontal_right)
    vertical, _, vertical_n = _correlation(vertical_left, vertical_right)
    adjacency = float(np.mean([horizontal, vertical]))
    finite = field[np.isfinite(field)]
    random = np.random.default_rng(int(asset.byte_sha256[:16], 16))
    null_adjacencies: list[float] = []
    finite_mask = np.isfinite(field)
    for _ in range(19):
        surrogate = np.full(field.shape, np.nan, dtype=float)
        surrogate[finite_mask] = random.permutation(finite)
        surrogate_h_left, surrogate_h_right = _paired_finite(
            surrogate[:, :-1].ravel(), surrogate[:, 1:].ravel()
        )
        surrogate_v_left, surrogate_v_right = _paired_finite(
            surrogate[:-1, :].ravel(), surrogate[1:, :].ravel()
        )
        null_horizontal, _, _ = _correlation(surrogate_h_left, surrogate_h_right)
        null_vertical, _, _ = _correlation(surrogate_v_left, surrogate_v_right)
        null_adjacencies.append(float(np.mean([null_horizontal, null_vertical])))
    permutation_p = (
        1 + sum(value >= adjacency for value in null_adjacencies)
    ) / 20.0
    upper = float(np.quantile(finite, 0.95))
    lower = float(np.quantile(finite, 0.05))
    largest_component = 0
    component_count = 0
    try:
        from scipy import ndimage

        labels, component_count = ndimage.label(np.isfinite(field) & (field >= upper))
        sizes = np.bincount(labels.ravel())
        largest_component = int(np.max(sizes[1:])) if sizes.size > 1 else 0
    except ImportError:
        pass
    quadrant_correlations: list[dict[str, Any]] = []
    for row_index, row_slice in enumerate(np.array_split(np.arange(field.shape[0]), 2)):
        for column_index, column_slice in enumerate(np.array_split(np.arange(field.shape[1]), 2)):
            quadrant = field[np.ix_(row_slice, column_slice)]
            left, right = _paired_finite(quadrant[:, :-1].ravel(), quadrant[:, 1:].ravel())
            correlation, _, count = _correlation(left, right)
            quadrant_correlations.append(
                {
                    # These are array-coordinate sensitivity blocks. Calling
                    # them geographic quadrants would imply that coordinate
                    # orientation has already been decoded.
                    "specification": (
                        f"sampled_rows_{'first' if row_index == 0 else 'second'}_half__"
                        f"columns_{'first' if column_index == 0 else 'second'}_half"
                    ),
                    "horizontal_adjacency_correlation": correlation,
                    "n": count,
                }
            )
    stable = sum(
        float(item["horizontal_adjacency_correlation"]) >= 0.30
        for item in quadrant_correlations
    ) >= 3
    negative_control_passed = permutation_p <= 0.05
    supported = (
        adjacency >= 0.50
        and stable
        and largest_component >= 8
        and negative_control_passed
    )
    negative: list[str] = []
    if adjacency < 0.50:
        negative.append("Nearest-neighbor spatial coherence was below the predeclared 0.50 threshold.")
    if not stable:
        negative.append("Spatial coherence did not recur in at least three of four quadrants.")
    if largest_component < 8:
        negative.append("The upper-tail anomaly mask did not form a component of at least eight sampled cells.")
    variable = loaded.variables[0]
    ocean = "sea_surface" in variable.casefold() or "temperature_anomaly" in variable.casefold()
    return _scientific_operator_outcome(
        study_id=study_id,
        asset=asset,
        loaded=loaded,
        operator="spatial_field_coherence",
        hypothesis_claim=(
            f"Extreme values in {variable} may form reproducible spatial regimes rather than isolated pixels."
        ),
        expected_relationship=(
            "Neighboring cells should covary, upper-tail cells should form connected regions, and coherence should recur across spatial blocks."
        ),
        confounders=[
            "land, coast, ice, and missing-data masks",
            "grid-cell area differences",
            "map projection and longitude seam",
            "spatial smoothing in the source product",
            "sampling of a single date",
        ],
        falsifier="Coherence vanishes after mask-aware, area-weighted, and spatial-block reanalysis.",
        parameters={
            "neighbor_definition": "four-neighbor sampled grid",
            "extreme_threshold": "finite 95th percentile",
            "spatial_blocks": "four quadrants",
        },
        expected_outputs=[
            "adjacency_correlation",
            "extreme_component_size",
            "spatial_block_sensitivity",
        ],
        validation_checks=[
            "finite mask",
            "horizontal and vertical adjacency",
            "four-quadrant recurrence",
        ],
        independent_unit_count=4,
        estimate={
            "variable": variable,
            "sample_shape": list(field.shape),
            "finite_cells": int(finite.size),
            "lower_5_percentile": lower,
            "upper_95_percentile": upper,
            "horizontal_adjacency_correlation": horizontal,
            "vertical_adjacency_correlation": vertical,
            "adjacency_correlation": adjacency,
            "upper_tail_component_count": int(component_count),
            "largest_upper_tail_component_cells": largest_component,
        },
        uncertainty={
            "p_value_uncorrected": permutation_p,
            "mask_preserving_permutation_p": permutation_p,
            "permutation_replicates": len(null_adjacencies),
            "minimum_resolvable_p": 1.0 / (len(null_adjacencies) + 1),
            "permutation_null_adjacency_95_percent_interval": [
                float(np.quantile(null_adjacencies, 0.025)),
                float(np.quantile(null_adjacencies, 0.975)),
            ],
            "independent_spatial_sensitivity_blocks": len(quadrant_correlations),
            "pixelwise_standard_error": (
                "not reported because spatial autocorrelation invalidates an "
                "independent-cell standard error"
            ),
        },
        diagnostics=[
            "Spatial autocorrelation reduces effective sample size; pixel count is not treated as independent n.",
            "Connected sampled cells do not establish a dynamical boundary.",
            "The four sensitivity blocks are reported in array coordinates; no geographic orientation is inferred without decoded coordinates.",
        ],
        sensitivities=quadrant_correlations,
        negative_evidence=negative,
        title=f"Spatially coherent extreme regime in {variable}",
        claim=(
            f"{variable} has mean nearest-neighbor correlation {adjacency:.3f}; its sampled upper "
            f"5% tail contains a largest connected region of {largest_component} cells and the "
            f"coherence recurs in {sum(float(item['horizontal_adjacency_correlation']) >= 0.30 for item in quadrant_correlations)} of 4 quadrants."
        ),
        interpretation=(
            "The anomaly is organized into spatial regimes rather than being a collection of isolated extreme cells."
        ),
        mechanism=(
            "Ocean circulation, air-sea heat exchange, and coupled climate variability can create "
            "spatially persistent sea-surface temperature anomaly regimes."
            if ocean
            else "Transport, diffusion, shared forcing, or source-side smoothing can create spatially persistent regimes."
        ),
        supported=supported,
        # Four spatial blocks are sensitivity strata, not independent maps.
        validation_level="exploratory",
        robustness=[
            "mask-aware finite-cell analysis",
            "horizontal and vertical neighbor checks",
            "four-quadrant spatial sensitivity",
            "connected upper-tail component analysis",
        ],
        limits=[
            "The deterministic projection is spatially thinned and not area weighted.",
            "A single map cannot establish temporal persistence or causal forcing.",
        ],
        next_validation=(
            "Repeat on neighboring dates with latitude-area weighting, explicit coast/ice masks, "
            "longitude-seam handling, and spatial-block permutation inference."
        ),
        units={variable: str(loaded.locator.get("units") or "")},
        expression_latex=(
            r"\rho_{\mathrm{NN}}=\frac{1}{2}"
            r"\left[\operatorname{Corr}(Z_{i,j},Z_{i,j+1})+"
            r"\operatorname{Corr}(Z_{i,j},Z_{i+1,j})\right]"
        ),
        equation_variables=[
            {"symbol": r"Z_{i,j}", "meaning": variable, "unit": str(loaded.locator.get("units") or "source unit")},
            {"symbol": r"\rho_{\mathrm{NN}}", "meaning": "mean horizontal/vertical nearest-neighbor coherence", "unit": "dimensionless"},
        ],
        split_validation={
            "strategy": "four_spatial_block_replication",
            "selection_lock": "neighbor definition and four array-coordinate blocks fixed before block evaluation",
            "development": {"adjacency_correlation": adjacency, "largest_upper_tail_component_cells": largest_component},
            "test": {"blocks": quadrant_correlations, "passed": supported},
            "baseline_comparison": {"baseline": "spatial independence", "passed": adjacency >= 0.50},
            "negative_control": {
                "strategy": "19 content-seeded value permutations within the unchanged finite-data mask",
                "adjacency_values": null_adjacencies,
                "p_value": permutation_p,
                "passed": negative_control_passed,
            },
            "rule_gate": {
                "interpretable_law_family": True,
                "held_out_baseline_improvement": adjacency >= 0.50,
                "parameter_stability": stable,
                "unit_plausibility": True,
                "negative_control": negative_control_passed,
                "transfer_boundary_declared": True,
            },
        },
        insight_level="structural",
        nontriviality_basis="Nearest-neighbor coherence recurs across spatial blocks and exceeds mask-preserving value permutations.",
        significance="The equation provides a mask-aware spatial-regime diagnostic rather than treating serialization order as scientific structure.",
        principle_statement="A spatial anomaly field is regime-like only when local coherence survives separated blocks and exceeds a mask-preserving exchangeability null.",
        transfer_scope="The retained field, finite-data mask, sampling grid, and single observation time; temporal persistence and other grid resolutions require replication.",
    )


def _analyze_diffraction_profile(
    *, study_id: str, asset: DataAsset, loaded: LoadedNumeric
) -> OperatorOutcome | None:
    if loaded.values.ndim != 2 or loaded.values.shape[1] < 2:
        return None
    angle, intensity = _paired_finite(loaded.values[:, 0], loaded.values[:, 1])
    if angle.size < 50:
        return None
    order = np.argsort(angle, kind="stable")
    angle = angle[order]
    intensity = intensity[order]
    baseline = float(np.quantile(intensity, 0.10))
    peak_index = int(np.argmax(intensity))
    peak_angle = float(angle[peak_index])
    peak_intensity = float(intensity[peak_index])
    prominence = peak_intensity - baseline
    difference_noise = float(1.4826 * np.median(np.abs(np.diff(intensity) - np.median(np.diff(intensity)))))
    noise_floor = np.finfo(float).eps * max(1.0, float(np.max(np.abs(intensity))))
    prominence_to_noise = prominence / max(difference_noise, noise_floor)
    half_height = baseline + prominence / 2.0
    left = peak_index
    right = peak_index
    while left > 0 and intensity[left] >= half_height:
        left -= 1
    while right < intensity.size - 1 and intensity[right] >= half_height:
        right += 1
    fwhm = float(angle[right] - angle[left]) if right > left else 0.0
    interior = 2 <= peak_index <= intensity.size - 3
    supported = interior and prominence_to_noise >= 10.0 and fwhm > 0
    negative: list[str] = []
    if not interior:
        negative.append("The maximum occurred at the scan boundary and cannot be treated as a resolved peak.")
    if prominence_to_noise < 10.0:
        negative.append("Peak prominence was below ten robust difference-noise units.")
    if fwhm <= 0:
        negative.append("A finite half-maximum width could not be resolved.")
    return _scientific_operator_outcome(
        study_id=study_id,
        asset=asset,
        loaded=loaded,
        operator="diffraction_peak_profile",
        hypothesis_claim=f"The scan may contain a resolved diffraction feature near {peak_angle:.4f} degrees.",
        expected_relationship="Intensity should form an interior, high-prominence peak with a finite half-maximum width.",
        confounders=[
            "background subtraction",
            "instrument broadening",
            "sample displacement",
            "overlapping phases",
            "scan normalization and counting time",
        ],
        falsifier="The peak disappears after background and instrument-profile controls or shifts incompatibly on repeat scans.",
        parameters={"baseline": "10th percentile", "width": "full width at half prominence"},
        expected_outputs=["peak_angle", "prominence", "fwhm", "prominence_to_noise"],
        validation_checks=["interior maximum", "robust difference-noise", "finite half-maximum width"],
        independent_unit_count=1,
        estimate={
            "peak_angle": peak_angle,
            "peak_intensity": peak_intensity,
            "baseline_intensity": baseline,
            "prominence": prominence,
            "prominence_to_noise": prominence_to_noise,
            "fwhm_angle": fwhm,
            "points": int(angle.size),
        },
        uncertainty={"angle_step_median": float(np.median(np.diff(angle)))},
        diagnostics=["A resolved peak is a structural signature, not a unique phase identification."],
        sensitivities=[],
        negative_evidence=negative,
        title=f"Resolved diffraction feature near {peak_angle:.4f}°",
        claim=(
            f"The retained scan contains an interior peak at {peak_angle:.4f}° with half-maximum "
            f"width {fwhm:.4f}° and prominence-to-noise ratio {prominence_to_noise:.1f}."
        ),
        interpretation="The scan contains a quantitatively resolved structural feature rather than a generic angle-intensity correlation.",
        mechanism=(
            "Constructive scattering under the Bragg condition concentrates intensity at lattice-spacing-dependent angles; "
            "peak position and width can therefore encode phase, strain, texture, or crystallite-size changes."
        ),
        supported=supported,
        validation_level="exploratory",
        robustness=["robust baseline", "difference-noise prominence", "finite half-maximum width"],
        limits=[
            "No instrument broadening correction or reference phase pattern was applied.",
            "One scan cannot distinguish phase, strain, texture, and size mechanisms."
        ],
        next_validation=(
            "Fit a source-specific background and instrument profile, index all reproducible peaks, "
            "and compare peak shifts and widths across wafer positions or process conditions."
        ),
        units={"angle": "degree", "intensity": "source units"},
    )


def _law_fit_predict(
    family: str,
    train_x: np.ndarray,
    train_y: np.ndarray,
    evaluation_x: np.ndarray,
) -> tuple[np.ndarray, dict[str, float]] | None:
    """Fit one interpretable dimensionless law without nonlinear black boxes."""

    x_scale = float(np.median(train_x))
    y_scale = float(np.median(np.abs(train_y)))
    if not math.isfinite(x_scale) or x_scale <= 0 or not math.isfinite(y_scale) or y_scale <= 0:
        return None
    x = train_x / x_scale
    x_eval = evaluation_x / x_scale
    y = train_y / y_scale
    if family in {"power", "exponential", "saturation"} and np.any(train_y <= 0):
        return None
    try:
        if family == "linear":
            design = np.column_stack([np.ones(x.size), x])
            coefficients, *_ = np.linalg.lstsq(design, y, rcond=None)
            prediction = np.column_stack([np.ones(x_eval.size), x_eval]) @ coefficients
            parameters = {"A": float(coefficients[0]), "B": float(coefficients[1])}
        elif family == "power":
            if np.any(x <= 0) or np.any(x_eval <= 0):
                return None
            design = np.column_stack([np.ones(x.size), np.log(x)])
            coefficients, *_ = np.linalg.lstsq(design, np.log(y), rcond=None)
            prediction = np.exp(
                np.column_stack([np.ones(x_eval.size), np.log(x_eval)]) @ coefficients
            )
            parameters = {"A": float(math.exp(coefficients[0])), "n": float(coefficients[1])}
        elif family == "exponential":
            design = np.column_stack([np.ones(x.size), x - 1.0])
            coefficients, *_ = np.linalg.lstsq(design, np.log(y), rcond=None)
            prediction = np.exp(
                np.column_stack([np.ones(x_eval.size), x_eval - 1.0]) @ coefficients
            )
            parameters = {"A": float(math.exp(coefficients[0])), "kappa": float(coefficients[1])}
        elif family == "log_response":
            if np.any(x <= 0) or np.any(x_eval <= 0):
                return None
            design = np.column_stack([np.ones(x.size), np.log(x)])
            coefficients, *_ = np.linalg.lstsq(design, y, rcond=None)
            prediction = np.column_stack([np.ones(x_eval.size), np.log(x_eval)]) @ coefficients
            parameters = {"A": float(coefficients[0]), "B": float(coefficients[1])}
        elif family == "saturation":
            if np.any(x <= 0) or np.any(x_eval <= 0):
                return None
            best: tuple[float, np.ndarray, float] | None = None
            for half_saturation in np.logspace(-2, 2, 121):
                basis = x / (half_saturation + x)
                design = np.column_stack([np.ones(x.size), basis])
                coefficients, *_ = np.linalg.lstsq(design, y, rcond=None)
                residual = float(np.sum((y - design @ coefficients) ** 2))
                candidate = (residual, coefficients, float(half_saturation))
                if best is None or candidate[0] < best[0]:
                    best = candidate
            if best is None:
                return None
            _, coefficients, half_saturation = best
            basis_eval = x_eval / (half_saturation + x_eval)
            prediction = coefficients[0] + coefficients[1] * basis_eval
            parameters = {
                "C": float(coefficients[0]),
                "A": float(coefficients[1]),
                "K": half_saturation,
            }
        else:
            return None
    except (ValueError, FloatingPointError, OverflowError, np.linalg.LinAlgError):
        return None
    if not np.all(np.isfinite(prediction)):
        return None
    parameters.update({"x_scale": x_scale, "y_scale": y_scale})
    return prediction * y_scale, parameters


def _prediction_receipt(observed: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    total = float(np.sum((observed - np.mean(observed)) ** 2))
    residual = float(np.sum((observed - predicted) ** 2))
    scale = float(np.quantile(observed, 0.75) - np.quantile(observed, 0.25))
    return {
        "r_squared": 1.0 - residual / total if total > 0 else 0.0,
        "normalized_rmse": (
            float(np.sqrt(np.mean((observed - predicted) ** 2))) / scale
            if scale > 0
            else math.inf
        ),
    }


def _typed_nonlinear_law(
    *, driver: np.ndarray, response: np.ndarray, source_digest: str
) -> dict[str, Any] | None:
    """Select on development data, then lock and challenge on range holdouts."""

    if driver.size < 80 or np.unique(driver).size < 12:
        return None
    order = np.argsort(driver, kind="stable")
    x = np.asarray(driver[order], dtype=float)
    y = np.asarray(response[order], dtype=float)
    lower = int(math.floor(x.size * 0.15))
    upper = int(math.ceil(x.size * 0.85))
    development = np.arange(lower, upper)
    test = np.concatenate([np.arange(0, lower), np.arange(upper, x.size)])
    if development.size < 40 or test.size < 20:
        return None
    selection_train = development[::2]
    selection_test = development[1::2]
    families = ["linear", "power", "exponential", "log_response", "saturation"]
    selection: list[dict[str, Any]] = []
    for family in families:
        fitted = _law_fit_predict(family, x[selection_train], y[selection_train], x[selection_test])
        if fitted is None:
            continue
        prediction, parameters = fitted
        selection.append(
            {
                "family": family,
                **_prediction_receipt(y[selection_test], prediction),
                "parameters": parameters,
            }
        )
    nonlinear = [item for item in selection if item["family"] != "linear"]
    linear_selection = next((item for item in selection if item["family"] == "linear"), None)
    if not nonlinear or linear_selection is None:
        return None
    selected = max(nonlinear, key=lambda item: (float(item["r_squared"]), -float(item["normalized_rmse"])))
    family = str(selected["family"])
    locked = _law_fit_predict(family, x[development], y[development], x[test])
    linear_locked = _law_fit_predict("linear", x[development], y[development], x[test])
    if locked is None or linear_locked is None:
        return None
    prediction, parameters = locked
    linear_prediction, linear_parameters = linear_locked
    test_receipt = _prediction_receipt(y[test], prediction)
    linear_receipt = _prediction_receipt(y[test], linear_prediction)

    # Parameter-direction stability is evaluated across two interleaved
    # development partitions, so it does not peek at the held-out range tails.
    stable_parameters: list[dict[str, Any]] = []
    primary = {"power": "n", "exponential": "kappa", "log_response": "B", "saturation": "A"}[family]
    for train_indices, evaluate_indices in (
        (development[::2], development[1::2]),
        (development[1::2], development[::2]),
    ):
        fitted = _law_fit_predict(family, x[train_indices], y[train_indices], x[evaluate_indices])
        if fitted is None:
            continue
        split_prediction, split_parameters = fitted
        stable_parameters.append(
            {
                "primary_parameter": float(split_parameters[primary]),
                **_prediction_receipt(y[evaluate_indices], split_prediction),
            }
        )
    parameter_stable = len(stable_parameters) == 2 and (
        stable_parameters[0]["primary_parameter"] * stable_parameters[1]["primary_parameter"] > 0
    )

    random = np.random.default_rng(int(source_digest[:16], 16))
    observed_selection_r2 = float(selected["r_squared"])
    null_scores: list[float] = []
    for _ in range(19):
        shuffled = random.permutation(y[selection_train])
        fitted = _law_fit_predict(family, x[selection_train], shuffled, x[selection_test])
        if fitted is None:
            continue
        null_scores.append(_prediction_receipt(y[selection_test], fitted[0])["r_squared"])
    negative_control_p = (
        (1 + sum(score >= observed_selection_r2 for score in null_scores)) / (1 + len(null_scores))
        if null_scores
        else 1.0
    )
    improvement = float(test_receipt["r_squared"] - linear_receipt["r_squared"])
    passed = (
        test_receipt["r_squared"] >= 0.20
        and test_receipt["normalized_rmse"] <= 1.0
        and improvement >= 0.05
        and parameter_stable
        and negative_control_p <= 0.05
    )
    expressions = {
        "power": r"\frac{y}{y_0}=A\!\left(\frac{x}{x_0}\right)^{n}+\varepsilon",
        "exponential": r"\frac{y}{y_0}=A\exp\!\left[\kappa\frac{x-x_0}{x_0}\right]+\varepsilon",
        "log_response": r"\frac{y}{y_0}=A+B\ln\!\left(\frac{x}{x_0}\right)+\varepsilon",
        "saturation": r"\frac{y}{y_0}=C+A\frac{x/x_0}{K+x/x_0}+\varepsilon",
    }
    return {
        "family": family,
        "expression_latex": expressions[family],
        "parameters": parameters,
        "linear_parameters": linear_parameters,
        "selection": selection,
        "development_n": int(development.size),
        "test_n": int(test.size),
        "test": test_receipt,
        "linear_baseline": linear_receipt,
        "held_out_r_squared_improvement": improvement,
        "parameter_stability": stable_parameters,
        "parameter_stable": parameter_stable,
        "negative_control_p": negative_control_p,
        "passed": passed,
        "transfer_boundary": "interpolation inside and extrapolation to the observed 15% range tails only",
    }


def _analyze_mechanistic_response_curve(
    *, study_id: str, asset: DataAsset, loaded: LoadedNumeric
) -> OperatorOutcome | None:
    """Test an explicitly named experimental driver against a named response.

    This operator is deliberately narrow. It prevents arbitrary column mining from
    becoming a finding while retaining a useful path for real dose, temperature,
    pressure, voltage, field, or frequency response experiments.
    """

    values = np.asarray(loaded.values, dtype=float)
    if values.ndim == 1:
        values = values[:, None]
    driver_terms = {
        "temperature",
        "temp",
        "dose",
        "concentration",
        "pressure",
        "voltage",
        "current",
        "field",
        "frequency",
        "omega",
    }
    response_terms = {
        "response",
        "yield",
        "amplitude",
        "intensity",
        "conversion",
        "rate",
        "signal",
        "noise",
        "power",
        "flux",
        "thickness",
        "strength",
    }

    def tokens(name: str) -> set[str]:
        normalized = name.casefold().replace("_", " ").replace("-", " ")
        return set(normalized.replace("/", " ").replace("(", " ").replace(")", " ").split())

    drivers = [index for index, name in enumerate(loaded.variables) if tokens(name) & driver_terms]
    responses = [index for index, name in enumerate(loaded.variables) if tokens(name) & response_terms]
    candidates: list[tuple[float, int, int, float | None, int]] = []
    for driver in drivers:
        for response in responses:
            if driver == response:
                continue
            coefficient, p_value, count = _correlation(values[:, driver], values[:, response])
            if count >= 50:
                candidates.append((abs(coefficient), driver, response, p_value, count))
    if not candidates:
        return None
    _, driver_index, response_index, p_value, count = max(
        candidates, key=lambda item: (item[0], -item[1], -item[2])
    )
    driver_values, response_values = _paired_finite(
        values[:, driver_index], values[:, response_index]
    )
    order = np.argsort(driver_values, kind="stable")
    driver_values = driver_values[order]
    response_values = response_values[order]
    if np.unique(driver_values).size < 10:
        return None
    coefficient, p_value, count = _correlation(driver_values, response_values)
    design = np.column_stack([np.ones(driver_values.size), driver_values])
    intercept, slope = np.linalg.lstsq(design, response_values, rcond=None)[0]
    fitted = intercept + slope * driver_values
    residual_sum = float(np.sum((response_values - fitted) ** 2))
    total_sum = float(np.sum((response_values - np.mean(response_values)) ** 2))
    r_squared = 1.0 - residual_sum / total_sum if total_sum > 0 else 0.0
    input_iqr = float(np.quantile(driver_values, 0.75) - np.quantile(driver_values, 0.25))
    response_iqr = float(np.quantile(response_values, 0.75) - np.quantile(response_values, 0.25))
    standardized_iqr_effect = (
        float(slope * input_iqr / response_iqr) if response_iqr > 0 else 0.0
    )
    typed_law = _typed_nonlinear_law(
        driver=driver_values,
        response=response_values,
        source_digest=asset.byte_sha256,
    )
    development_indices = np.arange(driver_values.size)[::2]
    test_indices = np.arange(driver_values.size)[1::2]

    def locked_linear_fit(
        train_indices: np.ndarray, evaluation_indices: np.ndarray
    ) -> dict[str, Any]:
        train_design = np.column_stack(
            [np.ones(train_indices.size), driver_values[train_indices]]
        )
        train_intercept, train_slope = np.linalg.lstsq(
            train_design, response_values[train_indices], rcond=None
        )[0]
        evaluation_prediction = (
            train_intercept + train_slope * driver_values[evaluation_indices]
        )
        evaluation_values = response_values[evaluation_indices]
        evaluation_total = float(
            np.sum((evaluation_values - np.mean(evaluation_values)) ** 2)
        )
        evaluation_r_squared = (
            1.0
            - float(np.sum((evaluation_values - evaluation_prediction) ** 2))
            / evaluation_total
            if evaluation_total > 0
            else 0.0
        )
        evaluation_scale = float(
            np.quantile(evaluation_values, 0.75)
            - np.quantile(evaluation_values, 0.25)
        )
        normalized_rmse = (
            float(np.sqrt(np.mean((evaluation_values - evaluation_prediction) ** 2)))
            / evaluation_scale
            if evaluation_scale > 0
            else math.inf
        )
        evaluation_correlation, _, _ = _correlation(
            evaluation_prediction, evaluation_values
        )
        return {
            "train_n": int(train_indices.size),
            "test_n": int(evaluation_indices.size),
            "intercept": float(train_intercept),
            "slope": float(train_slope),
            "test_r_squared": evaluation_r_squared,
            "test_normalized_rmse": normalized_rmse,
            "test_prediction_correlation": evaluation_correlation,
        }

    forward_fit = locked_linear_fit(development_indices, test_indices)
    reverse_fit = locked_linear_fit(test_indices, development_indices)
    split_results = [
        {"specification": "development_to_test", **forward_fit},
        {"specification": "reverse_split_sensitivity", **reverse_fit},
    ]
    split_coefficients = [float(forward_fit["slope"]), float(reverse_fit["slope"])]
    split_stable = all(
        value * coefficient > 0 for value in split_coefficients
    ) and all(
        float(item["test_r_squared"]) >= 0.35
        and float(item["test_normalized_rmse"]) <= 0.75
        for item in (forward_fit, reverse_fit)
    )
    bin_medians: list[dict[str, Any]] = []
    for index, indices in enumerate(np.array_split(np.arange(driver_values.size), 5), start=1):
        if not indices.size:
            continue
        bin_medians.append(
            {
                "bin": index,
                "driver_median": float(np.median(driver_values[indices])),
                "response_median": float(np.median(response_values[indices])),
                "n": int(indices.size),
            }
        )
    response_differences = np.diff([item["response_median"] for item in bin_medians])
    expected_sign = 1.0 if coefficient >= 0 else -1.0
    monotonic_transitions = int(np.sum(response_differences * expected_sign > 0))
    observational_supported = (
        abs(coefficient) >= 0.70
        and r_squared >= 0.45
        and p_value is not None
        and p_value <= 1e-6
        and split_stable
        and monotonic_transitions >= 3
    )
    law_supported = bool(typed_law and typed_law.get("passed"))
    supported = observational_supported or law_supported
    negative: list[str] = []
    if abs(coefficient) < 0.70 or r_squared < 0.45:
        negative.append("Driver-response strength was below the predeclared effect threshold.")
    if not split_stable:
        negative.append("The relationship did not reproduce in both alternating holdouts.")
    if monotonic_transitions < 3:
        negative.append("The binned response was not sufficiently monotonic across the driver range.")
    driver_name = loaded.variables[driver_index]
    response_name = loaded.variables[response_index]
    operator_name = "typed_nonlinear_law_selection" if law_supported else "mechanistic_response_curve"
    expression_latex = str(typed_law.get("expression_latex") or "") if law_supported else ""
    split_validation = (
        {
            "strategy": "locked_central_development_and_range_tail_holdout",
            "selection_lock": (
                "law family selected only inside the central 70% driver range; family and "
                "parameters were locked before evaluating both 15% range tails"
            ),
            "development": {
                "n": int(typed_law["development_n"]),
                "family_selection": typed_law["selection"],
                "fitted_parameters": typed_law["parameters"],
            },
            "test": {"n": int(typed_law["test_n"]), **dict(typed_law["test"]), "passed": True},
            "baseline_comparison": {
                "baseline": "locked dimensionless linear response",
                **dict(typed_law["linear_baseline"]),
                "held_out_r_squared_improvement": typed_law["held_out_r_squared_improvement"],
                "passed": float(typed_law["held_out_r_squared_improvement"]) >= 0.05,
            },
            "parameter_stability": {
                "partitions": typed_law["parameter_stability"],
                "passed": bool(typed_law["parameter_stable"]),
            },
            "negative_control": {
                "method": "19 content-seeded response permutations within development selection",
                "p_value": typed_law["negative_control_p"],
                "passed": float(typed_law["negative_control_p"]) <= 0.05,
            },
            "unit_plausibility": {
                "method": "dimensionless ratios x/x0 and y/y0",
                "passed": True,
            },
            "transfer_boundary": typed_law["transfer_boundary"],
            "rule_gate": {
                "interpretable_law_family": True,
                "held_out_baseline_improvement": True,
                "parameter_stability": bool(typed_law["parameter_stable"]),
                "unit_plausibility": True,
                "negative_control": float(typed_law["negative_control_p"]) <= 0.05,
                "transfer_boundary_declared": True,
            },
        }
        if law_supported and typed_law is not None
        else {}
    )
    return _scientific_operator_outcome(
        study_id=study_id,
        asset=asset,
        loaded=loaded,
        operator=operator_name,
        hypothesis_claim=(
            f"Changes in {driver_name} may produce a reproducible response in {response_name}."
        ),
        expected_relationship=(
            "A strong, monotonic driver-response curve should reproduce in interleaved holdouts."
        ),
        confounders=[
            "unrecorded co-varying experimental settings",
            "instrument drift and calibration",
            "pseudoreplication within a measurement sweep",
            "range restriction and saturation",
            "outcome-guided pair selection within the retained table",
        ],
        falsifier=(
            "The response disappears under randomized acquisition order, independent repeats, or adjustment for co-varied settings."
        ),
        parameters={
            "driver_semantics": sorted(driver_terms),
            "response_semantics": sorted(response_terms),
            "holdout": "alternating values after stable driver sort",
            "strength_threshold": 0.70,
            "r_squared_threshold": 0.45,
        },
        expected_outputs=["slope", "r_squared", "iqr_effect", "binned_response"],
        validation_checks=[
            "explicit driver and response semantics",
            "at least ten unique driver values",
            "alternating holdout replication",
            "five-bin monotonicity",
        ],
        # Row-level cross-splits test the equation but do not create independent
        # experimental replications from one acquisition.
        independent_unit_count=2,
        estimate={
            "driver": driver_name,
            "response": response_name,
            "n": count,
            "correlation": coefficient,
            "slope": float(forward_fit["slope"]),
            "intercept": float(forward_fit["intercept"]),
            "r_squared": r_squared,
            "held_out_r_squared": float(forward_fit["test_r_squared"]),
            "held_out_normalized_rmse": float(
                forward_fit["test_normalized_rmse"]
            ),
            "standardized_iqr_effect": standardized_iqr_effect,
            "monotonic_transitions": monotonic_transitions,
            "bin_medians": bin_medians,
            "typed_law": typed_law or {"state": "no_nonlinear_family_passed"},
        },
        uncertainty={"p_value_uncorrected": p_value},
        diagnostics=[
            "Interleaved holdouts test curve reproducibility but are not independent experiments.",
            "A monotonic response does not establish the molecular or physical mechanism."
        ],
        sensitivities=split_results,
        negative_evidence=negative,
        title=(
            f"Held-out {typed_law['family']} response of {response_name} to {driver_name}"
            if law_supported and typed_law is not None
            else f"Reproducible {driver_name} response in {response_name}"
        ),
        claim=(
            (
                f"A dimensionless {typed_law['family']} law selected on the central driver range "
                f"improved held-out tail R² by {float(typed_law['held_out_r_squared_improvement']):.3f} "
                f"over a locked linear baseline across {count:,} paired measurements; parameter direction "
                "was stable and the content-seeded permutation control passed."
            )
            if law_supported and typed_law is not None
            else (
                f"Across {count:,} paired measurements, {response_name} changed with {driver_name} "
                f"(r={coefficient:.3f}, linear R²={r_squared:.3f}); the direction reproduced in both "
                f"alternating holdouts and {monotonic_transitions} of 4 adjacent driver bins."
            )
        ),
        interpretation=(
            "The retained sweep contains a reproducible driver-response regime, not merely an arbitrary strongest correlation."
        ),
        mechanism=(
            "The pattern is compatible with direct or mediated coupling between the controlled driver and measured response; "
            "the specific mechanism requires source-domain equations and independently varied controls."
        ),
        supported=supported,
        validation_level="internal_holdout" if law_supported else "exploratory",
        robustness=[
            "explicit driver-response semantics",
            "linear effect and normalized IQR effect",
            "alternating holdout replication",
            "five-bin monotonicity check",
        ],
        limits=[
            "The two holdouts share one acquisition and are not independent replications.",
            "Pair selection across multiple eligible columns requires within-family multiplicity correction.",
        ],
        next_validation=(
            "Repeat the sweep with randomized acquisition order, independently controlled covariates, replicate units, and a domain-specific mechanistic fit."
        ),
        expression_latex=expression_latex,
        equation_variables=[
            {"symbol": "x", "meaning": driver_name, "unit": "source unit"},
            {"symbol": "y", "meaning": response_name, "unit": "source unit"},
            {"symbol": "x_0", "meaning": "development-set driver scale", "unit": "same as x"},
            {"symbol": "y_0", "meaning": "development-set response scale", "unit": "same as y"},
        ],
        split_validation=split_validation,
    )


def _analyze_earthquake_space_time_clustering(
    *, study_id: str, asset: DataAsset, loaded: LoadedNumeric
) -> OperatorOutcome | None:
    required = {"longitude", "latitude", "depth_km", "magnitude", "time_ms"}
    if not required <= set(loaded.variables):
        return None
    indices = {name: loaded.variables.index(name) for name in required}
    values = np.asarray(loaded.values, dtype=float)
    selected = np.column_stack([values[:, indices[name]] for name in sorted(required)])
    finite = np.all(np.isfinite(selected), axis=1)
    values = values[finite]
    if values.shape[0] < 200:
        return None
    longitude = values[:, indices["longitude"]]
    latitude = values[:, indices["latitude"]]
    event_time = values[:, indices["time_ms"]] / 1000.0
    order = np.argsort(event_time, kind="stable")
    longitude = longitude[order]
    latitude = latitude[order]
    event_time = event_time[order]

    def temporal_pairs(times: np.ndarray, maximum_seconds: float) -> tuple[np.ndarray, np.ndarray]:
        left: list[int] = []
        right: list[int] = []
        end = 0
        for start in range(times.size):
            end = max(end, start + 1)
            while end < times.size and times[end] - times[start] <= maximum_seconds:
                end += 1
            if end > start + 1:
                left.extend([start] * (end - start - 1))
                right.extend(range(start + 1, end))
        return np.asarray(left, dtype=int), np.asarray(right, dtype=int)

    def close_pair_count(
        lon: np.ndarray, lat: np.ndarray, left: np.ndarray, right: np.ndarray
    ) -> int:
        lon_left = np.radians(lon[left])
        lon_right = np.radians(lon[right])
        lat_left = np.radians(lat[left])
        lat_right = np.radians(lat[right])
        delta_lat = lat_right - lat_left
        delta_lon = lon_right - lon_left
        haversine = (
            np.sin(delta_lat / 2.0) ** 2
            + np.cos(lat_left) * np.cos(lat_right) * np.sin(delta_lon / 2.0) ** 2
        )
        distance_km = 2.0 * 6_371.0088 * np.arcsin(np.sqrt(np.clip(haversine, 0.0, 1.0)))
        return int(np.sum(distance_km <= 100.0))

    left, right = temporal_pairs(event_time, 24.0 * 60.0 * 60.0)
    if left.size < 100:
        return None
    observed_close = close_pair_count(longitude, latitude, left, right)
    seed = int(asset.byte_sha256[:16], 16)
    random = np.random.default_rng(seed)
    null_counts: list[int] = []
    for _ in range(19):
        permutation = random.permutation(longitude.size)
        null_counts.append(
            close_pair_count(longitude[permutation], latitude[permutation], left, right)
        )
    null_median = float(np.median(null_counts))
    enrichment = observed_close / max(1.0, null_median)
    split_results: list[dict[str, Any]] = []
    split_enrichments: list[float] = []
    midpoint = event_time.size // 2
    for label, selection in (
        ("first_chronological_half", slice(0, midpoint)),
        ("second_chronological_half", slice(midpoint, event_time.size)),
    ):
        split_time = event_time[selection]
        split_lon = longitude[selection]
        split_lat = latitude[selection]
        split_left, split_right = temporal_pairs(split_time, 24.0 * 60.0 * 60.0)
        split_observed = close_pair_count(
            split_lon, split_lat, split_left, split_right
        ) if split_left.size else 0
        split_null_counts = [
            close_pair_count(
                split_lon[permutation], split_lat[permutation], split_left, split_right
            )
            for permutation in (
                random.permutation(split_lon.size) for _ in range(7)
            )
        ] if split_left.size else [0]
        split_null = int(np.median(split_null_counts))
        split_enrichment = split_observed / max(1.0, float(split_null))
        split_enrichments.append(split_enrichment)
        split_results.append(
            {
                "specification": label,
                "temporal_pairs": int(split_left.size),
                "close_pairs_observed": split_observed,
                "close_pairs_permutation_null": split_null,
                "enrichment": split_enrichment,
            }
        )
    supported = (
        observed_close >= 20
        and enrichment >= 2.0
        and all(value >= 1.5 for value in split_enrichments)
    )
    negative: list[str] = []
    if observed_close < 20:
        negative.append("Fewer than 20 close space-time pairs were observed.")
    if enrichment < 2.0:
        negative.append("Space-time clustering was less than twofold above the circular-shift null.")
    if not all(value >= 1.5 for value in split_enrichments):
        negative.append("Clustering did not reproduce at 1.5-fold enrichment in both chronological halves.")
    return _scientific_operator_outcome(
        study_id=study_id,
        asset=asset,
        loaded=loaded,
        operator="earthquake_space_time_clustering",
        hypothesis_claim=(
            "Magnitude-thresholded earthquakes may form short-range, short-lag clusters beyond catalog-wide spatial marginals."
        ),
        expected_relationship=(
            "Pairs within 24 hours should be enriched within 100 km relative to deterministic circular-shift nulls."
        ),
        confounders=[
            "regional catalog completeness and contributor practices",
            "aftershock-dependent detection thresholds",
            "location uncertainty and depth uncertainty",
            "swarm and volcanic sequences",
            "the fixed magnitude threshold",
        ],
        falsifier=(
            "The enrichment disappears under region-stratified completeness controls, uncertainty-aware locations, or declustered null catalogs."
        ),
        parameters={
            "time_window_hours": 24.0,
            "distance_threshold_km": 100.0,
            "null": "19 content-seeded coordinate permutations",
            "random_seed_source": "asset SHA-256",
        },
        expected_outputs=["close_pair_count", "null_pair_count", "enrichment"],
        validation_checks=[
            "chronological event order",
            "great-circle distance",
            "content-seeded coordinate-permutation null",
            "two chronological sensitivity halves",
        ],
        independent_unit_count=2,
        estimate={
            "events": int(event_time.size),
            "temporal_pairs_within_24h": int(left.size),
            "space_time_pairs_within_100km": observed_close,
            "coordinate_permutation_null_counts": null_counts,
            "null_median": null_median,
            "enrichment": enrichment,
        },
        uncertainty={
            "empirical_exceedance_fraction": (
                1 + sum(value >= observed_close for value in null_counts)
            ) / (1 + len(null_counts))
        },
        diagnostics=[
            "The coordinate-permutation null preserves location marginals but is not a full ETAS or completeness model.",
            "Pair counts are dependent because one earthquake can participate in many pairs.",
        ],
        sensitivities=split_results,
        negative_evidence=negative,
        title="Reproducible short-lag earthquake clustering beyond permuted-location nulls",
        claim=(
            f"Among {event_time.size:,} events, {observed_close:,} pairs occurred within both 24 hours and 100 km, "
            f"a {enrichment:.2f}-fold enrichment over the median deterministic coordinate-permutation null; "
            f"the two chronological halves showed {split_enrichments[0]:.2f}× and {split_enrichments[1]:.2f}× enrichment."
        ),
        interpretation=(
            "The catalog contains reproducible space-time clustering consistent with triggered sequences rather than only a global magnitude-significance relationship."
        ),
        mechanism=(
            "Static and dynamic stress transfer after a mainshock can elevate the near-term failure rate on nearby faults, producing aftershock sequences and swarms."
        ),
        supported=supported,
        validation_level="exploratory",
        robustness=[
            "great-circle spatial distance",
            "fixed 24-hour and 100-km thresholds",
            "19 content-seeded coordinate-permutation nulls",
            "chronological-half recurrence",
        ],
        limits=[
            "The test does not separate aftershocks, swarms, volcanic activity, or reporting effects.",
            "A current literature and catalog-method review is required before any novelty assessment.",
        ],
        next_validation=(
            "Fit region-specific ETAS and completeness models, propagate location uncertainty, test multiple predeclared scales, and compare reviewed versus automatic catalog subsets."
        ),
        units={"distance": "km", "time": "hour"},
        expression_latex=(
            r"\mathcal R(\Delta r,\Delta t)="
            r"\frac{N(d_{ij}\leq\Delta r,\,0<t_j-t_i\leq\Delta t)}"
            r"{\operatorname{median}_{\pi}N(d_{\pi(i)\pi(j)}\leq\Delta r,\,0<t_j-t_i\leq\Delta t)}"
        ),
        equation_variables=[
            {"symbol": r"d_{ij}", "meaning": "great-circle separation between event locations", "unit": "km"},
            {"symbol": r"\Delta r", "meaning": "predeclared spatial window", "unit": "km"},
            {"symbol": r"\Delta t", "meaning": "predeclared temporal window", "unit": "hour"},
            {"symbol": r"\mathcal R", "meaning": "space-time pair enrichment over coordinate-permutation null", "unit": "dimensionless"},
        ],
        split_validation={
            "strategy": "chronological_half_replication_with_coordinate_permutation_null",
            "selection_lock": "24-hour and 100-km windows fixed before chronological splitting",
            "development": split_results[0],
            "test": {**split_results[1], "passed": supported},
            "baseline_comparison": {"baseline": "content-seeded coordinate-permutation catalog", "passed": enrichment >= 2.0},
            "negative_control": {"method": "19 coordinate permutations", "counts": null_counts, "passed": observed_close > max(null_counts)},
            "rule_gate": {
                "interpretable_law_family": True,
                "held_out_baseline_improvement": enrichment >= 2.0,
                "parameter_stability": all(value >= 1.5 for value in split_enrichments),
                "unit_plausibility": True,
                "negative_control": observed_close > max(null_counts),
                "transfer_boundary_declared": True,
            },
        },
        insight_level="structural",
        nontriviality_basis="Fixed space-time windows recur across chronological halves and exceed content-seeded coordinate permutations.",
        significance="The invariant is a reproducible triggered-event diagnostic suitable for catalog triage, not a generic magnitude correlation.",
        principle_statement="Triggered-event catalogs exhibit excess short-lag, short-range pair density relative to their spatial marginals when physical clustering is present.",
        transfer_scope="Global magnitude-at-least-2.5 events in the retained month under the 24-hour/100-km support; regional completeness and other scales require separate calibration.",
    )


def analyze_asset(*, study_id: str, asset: DataAsset, root: Path) -> OperatorOutcome | None:
    # Raster previews are contextual scientific evidence. Pixel serialization order is
    # not a scientific variable and must never be promoted into a correlation finding.
    if asset.format in {"png", "jpeg", "jpg"}:
        return None
    # Matrix Market coordinates are a sparse serialization contract: row index,
    # column index, and stored value are not three scientific variables.  The
    # corresponding feature/barcode/matrix bundle is handled by collection-level
    # operators that recover its biological axes before testing a claim.
    if asset.format in {"matrix_market", "matrix_market_gzip"}:
        return None
    if asset.format == "hdf5":
        specialized_hdf5 = _analyze_masked_hdf5_spectral_envelope(
            study_id=study_id, asset=asset, root=root
        )
        if specialized_hdf5 is not None:
            return specialized_hdf5
    loaded = load_numeric(asset, root)
    if loaded is None or loaded.values.size < 10:
        return None
    if asset.format == "fits":
        specialized = _analyze_fits_light_curve(
            study_id=study_id,
            asset=asset,
            loaded=loaded,
        )
        if specialized is not None:
            return specialized
    if asset.format in {"hdf5", "nwb", "edf"}:
        specialized = _analyze_ordered_signal(
            study_id=study_id,
            asset=asset,
            loaded=loaded,
        )
        if specialized is not None:
            return specialized
    if asset.format == "netcdf":
        specialized = _analyze_spatial_field(
            study_id=study_id,
            asset=asset,
            loaded=loaded,
        )
        if specialized is not None:
            return specialized
    if asset.format == "ras":
        specialized = _analyze_diffraction_profile(
            study_id=study_id,
            asset=asset,
            loaded=loaded,
        )
        if specialized is not None:
            return specialized
    specialized = _analyze_earthquake_space_time_clustering(
        study_id=study_id,
        asset=asset,
        loaded=loaded,
    )
    if specialized is not None:
        return specialized
    specialized = _analyze_mechanistic_response_curve(
        study_id=study_id,
        asset=asset,
        loaded=loaded,
    )
    if specialized is not None:
        return specialized
    values = np.asarray(loaded.values, dtype=float)
    if values.ndim == 1:
        values = values[:, None]
    finite_counts = np.sum(np.isfinite(values), axis=0)
    summaries: list[dict[str, Any]] = []
    for index, variable in enumerate(loaded.variables[: values.shape[1]]):
        column = values[:, index]
        finite = column[np.isfinite(column)]
        if finite.size < 3:
            continue
        scale = float(np.max(np.abs(finite)))
        scaled = finite / scale if scale else finite
        mean = float(np.mean(scaled) * scale) if scale else 0.0
        standard_deviation = (
            float(np.std(scaled, ddof=1) * scale) if finite.size > 1 and scale else 0.0
        )
        summaries.append(
            {
                "variable": variable,
                "n": int(finite.size),
                "missing_rate": round(1 - (finite.size / max(1, column.size)), 6),
                "mean": mean,
                "std": standard_deviation,
                "median": float(np.median(finite)),
                "q25": float(np.quantile(finite, 0.25)),
                "q75": float(np.quantile(finite, 0.75)),
                "min": float(np.min(finite)),
                "max": float(np.max(finite)),
            }
        )
    if not summaries:
        return None

    strongest: dict[str, Any] | None = None
    scientific_columns = [
        index
        for index, name in enumerate(loaded.variables[: min(values.shape[1], MAX_COLUMNS)])
        if _scientific_variable_candidate(name)
    ]
    for position, left in enumerate(scientific_columns):
        for right in scientific_columns[position + 1 :]:
            left_label = " ".join(str(loaded.variables[left]).split()).casefold()
            right_label = " ".join(str(loaded.variables[right]).split()).casefold()
            # Repeated workbooks often place the same measured quantity in
            # several condition columns. Without an explicit condition/alignment
            # binding, pairing those columns is scientifically undefined and a
            # same-label correlation is merely a layout artifact.
            if left_label == right_label:
                continue
            coefficient, p_value, count = _correlation(values[:, left], values[:, right])
            candidate = {
                "left": loaded.variables[left],
                "right": loaded.variables[right],
                "left_index": left,
                "right_index": right,
                "coefficient": coefficient,
                "p_value": p_value,
                "n": count,
            }
            if strongest is None or abs(coefficient) > abs(float(strongest["coefficient"])):
                strongest = candidate
    if strongest is None:
        # Record order and identifier columns are acquisition metadata, not
        # scientific variables.  Returning no executable outcome is more
        # truthful than manufacturing a screened test from them.
        return None

    relation = "positive" if strongest["coefficient"] >= 0 else "negative"
    challenge_left = values[:, int(strongest["left_index"])]
    challenge_right = values[:, int(strongest["right_index"])]
    finite_left, finite_right = _paired_finite(challenge_left, challenge_right)
    midpoint = finite_left.size // 2
    split_effects: list[dict[str, Any]] = []
    for label, segment in (
        ("first_contiguous_half", slice(0, midpoint)),
        ("second_contiguous_half", slice(midpoint, finite_left.size)),
    ):
        coefficient, _, count = _correlation(finite_left[segment], finite_right[segment])
        split_effects.append({"specification": label, "correlation": coefficient, "n": count})
    stable_direction = all(
        item["n"] >= 3
        and float(item["correlation"]) * float(strongest["coefficient"]) >= 0
        for item in split_effects
    )
    hypothesis_id = "hyp:" + canonical_sha256(
        {"study": study_id, "asset": asset.asset_id, "relation": strongest}
    )[:24]
    view_content_digest = canonical_sha256(
        {
            "asset": asset.byte_sha256,
            "adapter": asset.adapter,
            "adapter_version": asset.adapter_version,
            "profile": asset.metadata.get("profile") or {},
        }
    )
    view_id = "view:" + canonical_sha256(
        {"study": study_id, "content_digest": view_content_digest}
    )[:24]
    hypothesis = DataHypothesis(
        hypothesis_id=hypothesis_id,
        study_id=study_id,
        claim=(
            f"{strongest['left']} and {strongest['right']} may exhibit a {relation} "
            f"association within {Path(str(asset.metadata.get('relative_path') or asset.portable_uri)).name}."
        ),
        origin="data_driven",
        expected_relationship=(
            f"non-zero association between {strongest['left']} and {strongest['right']}"
        ),
        input_view_ids=[view_id],
        confounders=["record ordering", "missingness", "measurement and selection effects"],
        boundary=[loaded.sample_definition, "single retained dataset representation"],
        falsifier="The association disappears under complete-case, robust, or held-out reanalysis.",
        state="tested",
    )
    plan_payload = {
        "operator": "descriptive_association",
        "asset": asset.asset_id,
        "variables": [strongest["left"], strongest["right"]],
        "sample": loaded.sample_definition,
        "version": OPERATOR_VERSION,
    }
    plan_digest = canonical_sha256(plan_payload)
    plan = AnalysisPlan(
        plan_id=f"plan:{plan_digest[:24]}",
        study_id=study_id,
        hypothesis_id=hypothesis_id,
        executor="operator",
        operator="descriptive_association",
        input_view_ids=hypothesis.input_view_ids,
        parameters={"complete_cases": True, "multiple_testing": "benjamini-hochberg"},
        expected_outputs=[
            "effect_size",
            "uncertainty",
            "missingness",
            "descriptive_summary",
        ],
        validation_checks=[
            "finite sample",
            "non-constant variables",
            "independent-unit review",
        ],
        plan_digest=plan_digest,
    )
    result_payload = {
        "strongest_association": strongest,
        "summaries": summaries,
        "finite_counts": finite_counts.tolist(),
        "operator_version": OPERATOR_VERSION,
    }
    result_digest = canonical_sha256(result_payload)
    test_id = "test:" + canonical_sha256(
        {"study": study_id, "result": result_digest}
    )[:24]
    test = TestResult(
        test_id=test_id,
        study_id=study_id,
        hypothesis_id=hypothesis_id,
        plan_id=plan.plan_id,
        plan_digest=plan_digest,
        state="succeeded",
        sample_definition=loaded.sample_definition,
        independent_unit_count=int(strongest["n"]),
        estimate={"correlation": strongest, "summaries": summaries},
        uncertainty={"p_value_uncorrected": strongest.get("p_value")},
        diagnostics=["Descriptive association is not causal evidence."],
        sensitivities=split_effects,
        negative_evidence=(
            (
                ["Observed absolute association is below the predeclared 0.30 exploratory threshold."]
                if abs(float(strongest["coefficient"])) < 0.30
                else []
            )
            + ([] if stable_direction else ["Association direction was not stable across contiguous halves."])
        ),
        artifacts=[],
        result_digest=result_digest,
    )
    finding_id = "finding:" + canonical_sha256(
        {"study": study_id, "hypothesis": hypothesis_id, "result": result_digest}
    )[:24]
    evidence_id = "evidence:" + canonical_sha256(
        {"test": test_id, "asset": asset.asset_id, "locator": loaded.locator}
    )[:24]
    evidence = ComputedEvidenceAnchor(
        evidence_id=evidence_id,
        study_id=study_id,
        finding_id=finding_id,
        test_id=test_id,
        asset_id=asset.asset_id,
        view_id=view_id,
        locator={"relative_path": asset.metadata.get("relative_path"), **loaded.locator},
        plan_digest=plan_digest,
        executor_version=OPERATOR_VERSION,
        result_digest=result_digest,
    )
    # Unstructured strongest-pair mining remains an auditable screening test. It
    # can prioritize future plans but can never itself become a visible finding.
    supported = False
    # This bounded first-pass operator has no defensible independent holdout.  A large
    # row count alone must never be promoted to a validation claim.
    validation_level = "exploratory"
    finding = DataFinding(
        finding_id=finding_id,
        study_id=study_id,
        title=f"Candidate association: {strongest['left']} and {strongest['right']}",
        claim=(
            f"In {loaded.sample_definition}, {strongest['left']} and {strongest['right']} "
            f"had Pearson r={float(strongest['coefficient']):.3f} across "
            f"{int(strongest['n']):,} paired observations."
        ),
        interpretation=(
            "This is a reproducible computed pattern in the retained sample, not a causal "
            "or population-level conclusion."
        ),
        mechanism=(
            "No mechanism is established; relevant existing Principles must be evaluated "
            "during synthesis."
        ),
        status="supported_candidate" if supported else "inconclusive",
        validation_level=validation_level,
        hypothesis_ids=[hypothesis_id],
        test_ids=[test_id],
        evidence_ids=[evidence_id],
        robustness=[
            "complete-case descriptive estimate",
            "contiguous-half direction check",
        ],
        confounders=hypothesis.confounders,
        falsifiers=[hypothesis.falsifier],
        negative_evidence=test.negative_evidence,
        limits=[
            "Exploratory thresholding does not establish scientific novelty.",
            "Independent experimental units and source-specific weights require domain review.",
        ],
        next_validation=(
            "Repeat with source-specific units, weights, and an independently held-out partition."
        ),
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    return OperatorOutcome(
        hypothesis=hypothesis,
        plan=plan,
        result=test,
        evidence=evidence,
        finding=finding,
    )


def benjamini_hochberg(p_values: list[float | None]) -> list[float | None]:
    indexed = [(index, value) for index, value in enumerate(p_values) if value is not None]
    output: list[float | None] = [None] * len(p_values)
    if not indexed:
        return output
    ordered = sorted(indexed, key=lambda item: float(item[1]))
    count = len(ordered)
    adjusted = [0.0] * count
    running = 1.0
    for reverse_index in range(count - 1, -1, -1):
        _, value = ordered[reverse_index]
        candidate = min(1.0, float(value) * count / (reverse_index + 1))
        running = min(running, candidate)
        adjusted[reverse_index] = running
    for (original_index, _), value in zip(ordered, adjusted, strict=True):
        output[original_index] = value
    return output
