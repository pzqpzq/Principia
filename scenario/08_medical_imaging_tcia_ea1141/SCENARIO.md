# EA1141 paired breast MR and mammography DICOM series

## Source and payload

- Publisher: The Cancer Imaging Archive / NCI Imaging Data Commons
- Authoritative landing page: https://www.cancerimagingarchive.net/collection/ea1141/
- Version/release: EA1141 v2; IDC index current at retrieval
- Identifier(s): doi:10.7937/2BAS-HR33, EA1141-1004399
- License/access: CC BY 4.0
- Installed official/source-metadata files: 74
- Installed official/source-metadata bytes: 59837954

Selection rule: Using the official IDC index, choose the first lexicographic patient and series pair with both MR and MG, 32-400 combined instances, and at most 180 MiB; tie-break by MR then MG SeriesInstanceUID.

## Intended analysis challenge

Cross-modal imaging interpretation, DICOM metadata handling, spatial series structure, and acquisition confounders.

## Known confounders and failure modes

Patient positioning, modality physics, laterality and view, compression, resampling assumptions, acquisition date, and non-comparable spatial frames.

## Evidence boundary

This scenario is hypothesis-generation material, not a precomputed answer. A pattern is not a novel finding until it has exact file/row/time provenance, units and computation, uncertainty, missingness and confounder analysis, falsifiers and negative evidence, comparison with source publications, robustness checks, and a current literature novelty review.

No source values were normalized, imputed, filtered, or converted for this corpus. Archives remain archives unless the publisher supplied ordinary files directly. USER_BRIEF.txt is generated simulation context and is not scientific evidence.
