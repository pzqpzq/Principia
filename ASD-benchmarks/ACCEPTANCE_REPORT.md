# Acceptance report — Principia-100 local release candidate

**Acquisition verification passed; owner acceptance was received on 2026-09-15.** Public version 0.1.1 preserves the accepted scientific assets. The results below describe acquisition-stage verification; see `PUBLICATION_REPORT.json` for publication checks.

## Delivered

- **100 accepted corpus entries**, stable IDs P100-001–P100-100; **50 accepted additions in folders 51–100**.
- Added data origin: **44 measured/observed-only, five mixed, one computational**. Across all 100: 85 measured/observed, eight mixed, six computational and one curated mathematical reference case.
- **2,379,625,826 bytes (2.380 GB)** in the 50 new installed folders.
- **1,685 allowlisted source/context assets**, totaling **4,671,654,376 bytes (4.672 GB)**. Their recursively expanded source equivalent is **7,309,956,744 bytes (7.310 GB)**. Native compound scientific formats remain files in that size measure; it is not a runtime-memory bound.
- Every accepted case is below **500 MB both stored and expanded**. Eight cases exceed the 100 MB stored target, including four additions (52, 69, 71, 99), for complete source-defined selections. Exact canonical and release-folder sizes are in `RELEASE_SIZES.json`.
- English catalog in Markdown/CSV/JSON; 100 task cards; dataset card; grouped evaluation protocol; reviewer guide; input allowlist; output schema; acquisition, citation and per-asset rights registers; validation/replay tools; local release manifest.

## Preservation and substitutions

All **1,473 files** in the original 50 scenario folders match their before inventory. All **1,371 checksum-listed files** also passed re-verification. Neither original scientific data nor original documentation was rewritten.

During this expansion, inaccessible ATUS, Potsdam and EPA candidates were replaced in slots **86, 93 and 99** by industrial fermentation, solute-carrier flow cytometry and hippocampal calcium recordings. Original **05** remains local but its benchmark slot uses the licensed graph-certificate reserve. Case **19** retains complete 2025–2026 complaints, recalls and manufacturer communications; the all-history investigations archive is omitted from the release selection to satisfy the expanded-size limit. Earlier 21–50 substitutions are recorded separately in the same history. These changes do not create extra benchmark cases.

## Verification evidence

- All **1,685 frozen asset sizes and SHA-256 hashes** passed. **852 publisher checksums** were independently rechecked for the retained representation, plus **708 internal publisher SHA-256 checks** in case 80. Ingested Dataverse TAB checksums are not misapplied to original CSV files.
- ZIP CRCs, streamed archive lengths, recursive expanded sizes and safe member paths were inspected; source archives remain intact. No cross-case identical raw-file hashes were found, and each case references a distinct source record. Source-defined paired/alternate representations remain within their original case.
- Native format checks include all **3,181 WAV calls**, **11,616 WFDB signals**, **3,888 QRS annotation files**, FCS/RDS sample alignment and other format-specific readers. The source PPG archive has 96 degenerate header layouts (48 ECG, 48 PPG), which remain explicitly flagged rather than silently transposed. Some formats receive bounded or header-only inspection; proprietary/opaque semantics remain disclosed. The portable case-60 audit passed for all **39** selected files.
- Both JSON schemas are well-formed; the 100-case manifest validates. All case layouts and per-case checksum files passed. The input allowlist contains **1,785 files**, excluding reviewer guidance and task cards.
- Disposable tests detected missing, truncated and same-size corrupt files and rejected traversal; they restored valid frozen copies and refused to overwrite mismatches. Real case-61 assets were reconstructed from the frozen release, and a real pinned case-51 native file reproduced its recorded hash through remote replay.
- Explicit assembly allowlists and an outer-file private-marker scan excluded historical private-reference material, current-machine paths, Finder files, caches and operational logs. Source metadata contacts or site templates lacking a verified reuse basis remain local; factual source profiles replace them in the release layer. Publisher archive members remain unmodified.

## Modalities and scientific scope

Case-level modality coverage is overlapping: audio: 1, computational_or_mathematical_records: 7, images: 17, instrument_signals_or_cell_events: 5, scientific_arrays_or_events: 17, source_native_other: 1, spatial_or_georeferenced: 9, tables_logs_or_structured_text: 88, video: 2. Detailed native formats and reader coverage are in `FORMAT_COVERAGE.json` and `reports/`.

This is an **open, source-aware corpus**, including disclosed published analyses and fitted results. The original 20 cases were used during Principia development; replacement case 05 is separately identified. Measurement dates and deposit dates differ, and unresolved dates remain explicit. Source inconsistencies—including case 86's batch-length description, case 59's unspecified auxiliary weather provider, device/donor/group-count limits, single-system cases and opaque reader formats—bound later claims.

No Principia ingestion campaign, paid discovery runs, system comparison, aggregate discovery score, new scientific law or industrial-deployment validation was performed. Reproduction, validated extension, novelty candidate and justified abstention are distinct future outcomes. Native file authenticity does not establish scientific novelty or universal generalization.

## Review entry points

Read `CATALOG.md`, `DATASET_CARD.md`, `EVALUATION_PROTOCOL.md`, `SUBSTITUTIONS.json`, `LICENSES.md` and `VALIDATION_REPORT.md`. Inspect the assembled `scenarios/` collection using `INPUT_ALLOWLIST.json`. Run `python3 tools/validate_release.py .` and `python3 tools/replay.py --root . --mode verify` from the assembled release root. The release index hashes every shipped file except itself; a separate local receipt records the release-index hash and actual total size.

The owner authorized publication to the Principia repository after inspection. The accepted local package remains unchanged; this public edition adds download documentation and updates publication metadata. Acquisition-stage byte totals are historical; `RELEASE_MANIFEST.json` gives the current public inventory.
