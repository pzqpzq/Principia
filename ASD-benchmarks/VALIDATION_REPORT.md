# Validation report

Status: corpus acquisition checks passed with explicit reader and scientific-scope limitations. The owner accepted publication on 2026-09-15; publication-specific checks are recorded in `PUBLICATION_REPORT.json`.

## Collection and sizes

- 100 unique source records; 50 additions. Added origins: {'mixed_measured_and_computational': 5, 'measured_or_observed': 44, 'computational_experiment': 1}.
- Source assets: 1,685; 4.672 GB. Source archive expansion equivalent: 7.310 GB.
- New installed folders: 2.380 GB. Largest installed case: 496.808 MB; largest expanded source case: 496.765 MB.
- 852 publisher checksums reverified against retained bytes; 708 additional internal publisher SHA-256 entries verified in case 80. Local hashes cover every allowlisted asset.
- No shared raw-file hashes between different cases. Distinct records and source/group descriptions were reviewed for experiment identity; alternate representations remain within a case.

## Stored exceptions above 100 MB

| Case | Stored MB | Reason |
|---|---:|---|
| P100-003 | 129.237 | Complete source-defined selection; below 500 MB stored and expanded. |
| P100-012 | 146.032 | Complete source-defined selection; below 500 MB stored and expanded. |
| P100-035 | 287.356 | Complete source-defined selection; below 500 MB stored and expanded. |
| P100-036 | 127.384 | Complete source-defined selection; below 500 MB stored and expanded. |
| P100-052 | 272.315 | Complete source-defined selection; below 500 MB stored and expanded. |
| P100-069 | 496.808 | Complete source-defined selection; below 500 MB stored and expanded. |
| P100-071 | 227.647 | Complete source-defined selection; below 500 MB stored and expanded. |
| P100-099 | 399.551 | Complete source-defined selection; below 500 MB stored and expanded. |

## Coverage and limitations

- Recorded format labels: 7Z, ABF, DICOM, DOCX, EDF, Excel_OpenXML, FCS, FITS, GIF, GZIP, HDF5, JPEG, JSON, JSONL, MATLAB, NASA_CDF, NPZ, NWB/HDF5, NetCDF, ODS, PDF, PNG, Parquet, QuakeML, RAR, RDS, ROOT, Rigaku RASX/ZIP, TAR, TIFF, WAVE, XML, ZIP, preserved_native, publisher_OS_metadata, source_OS_resource_fork, text_or_instrument_native, video.
- Archive CRCs, streamed sizes, safe member paths and local hashes are distinct from domain correctness. Per-file reports disclose complete, sampled, metadata-only and opaque-reader coverage. Native scientific variable/unit information remains anchored to headers, sheets, channels and dictionaries.
- The current reader decodes all 3,181 WAV calls in case 35. Case 60 uses bounded numeric MAT inspection after the full SciPy object reader fails on authenticated Octave-exported structures. Case 87 has opaque MCOS table semantics and accompanying source workbooks.
- Vendor/project formats, waveform record descriptors, exact symbolic object files and illustrative media retain stated reader limits. Some source collections contain fitted or author-derived products. These are not independent instrument measurements.
- Sample checks include the 28,395-by-24 RNA matrix aligned to four donors, 18 FCS files aligned to the supplied list, and all 708 internal case-80 publisher hashes. Case 86 has 50,536 rows over 406 batches, contradicting the source average batch-length description; the discrepancy is preserved.
- No Principia ingestion compatibility, scientific equation, discovery novelty, industrial deployment or comparative performance was evaluated. Missing dates/units and unmeasured/confounded variables constrain later claims.

## Provenance and release scope

- Per-asset source URLs, version/record identifiers, checksums, citations and reuse evidence are frozen. Full repository snapshots with unresolved context rights are excluded from public assembly; factual metadata is retained instead.
- Three inaccessible additions use reserves (86, 93, 99). Original 05 is preserved locally and replaced only in the benchmark release. Case 19 retains the complete three date-scoped archives and omits the oversized all-history combination.
- 1,575 assets have direct URLs; 110 require frozen-copy replay (including curator profiles/metadata snapshots). Current source drift is rejected rather than silently accepted.
- All 1,473 original files and 1,371 listed checksums remain unchanged.
- Final release assembly, mutation tests, schema validation, privacy/allowlist inspection and exact release hash verification are recorded in ACCEPTANCE_REPORT.md and FINAL_CHECKS.json.

The supplemental WFDB audit decoded all 11,616 signal records and 3,888 QRS annotation files in case 33. This supersedes the earlier QRS-reader limitation in per-member legacy reports. The audit also flags 96 source headers with many channels and one sample, a scientific interpretation limitation retained explicitly. The portable native-reader smoke test passed for all 39 selected case-60 assets/context files.
