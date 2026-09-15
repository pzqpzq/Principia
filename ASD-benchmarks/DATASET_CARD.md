# Principia-100 dataset card

## Identity and status

Principia-100, version 0.1.1, is the owner-accepted public research corpus and evaluation protocol released on 2026-09-15. It contains 100 scenarios under `scenarios/`, with immutable asset hashes and a versioned release manifest.

The unit of collection is a coherent scientific scenario with source data and context. It is not one file, one observation, one discipline or one discovered rule. Stable benchmark IDs are P100-001 through P100-100. Case revisions distinguish source replacements from a change to the original local folder.

## Composition and intended uses

The collection combines the retained earlier corpus with 50 additional cases spanning experimental engineering, physics, biology, neuroscience, environmental science, social science, computing and mathematics. `CATALOG.csv` and `BENCHMARK_MANIFEST.json` provide exact versions, origins, formats, sizes, source links and eligibility. The additions include at least 40 measured/observed-only cases; mixed/model products are labeled separately.

It supports data interpretation, quantitative relationship discovery, independent reproduction, falsification and carefully scoped extensions from realistic heterogeneous local inputs. Native spreadsheets, text tables, archives, instrument binaries, images, videos, audio, hierarchical arrays, spatial products and computational records retain source organization and imperfections.

It does not establish clinical effectiveness, causal effects, deployment readiness, system rankings or previously unknown universal laws. No scored ASD campaign, reference coefficients or aggregate discovery score accompanies this release.

## Acquisition and curation

Datasets were selected from authoritative institutions/researcher deposits and source-defined experiments or modality/condition blocks, with explicit size and redistribution checks. Selection was not based on observed correlations, fit quality, favorable outcomes or claimed novelty. Recent deposit dates are recorded separately from measurement dates; many recent releases contain older experiments.

Source-native bytes and archives were retained. The curator did not normalize, impute, filter scientific observations, resample, denoise or run publisher analysis code. Author calibration, alignment, derived tables, image extraction and simulation are documented. Historical duplicate representations in the old corpus remain labeled rather than counted as independent samples.

The original 50 local folders remain preserved. The GEO case in original slot 05 is retained locally but excluded from this release because public access did not establish depositor redistribution permission. The release layer substitutes the CC BY 4.0 graph-certificate reserve and records revision 2. Three planned additions were replaced after public access failures; see `SUBSTITUTIONS.json` for the exact changes and coverage implications. The release selection for case 19 excludes the all-history investigations archive to meet the expanded-size ceiling, retaining all three complete 2025–2026 archives. Full site snapshots without a verified reuse basis are excluded separately, with factual source profiles retained.

## Provenance, rights and privacy

Each allowlisted asset has a local SHA-256, byte size, citation/source version and applicable license or source terms. Publisher checksums are checked where their representation matches the retained file. Dataverse ingested TAB checksums are not asserted to authenticate original CSV downloads. Authoritative metadata snapshots freeze file inventories and rights evidence.

The aggregate has no blanket license over third-party data. Keep per-asset attribution, code notices, share-alike obligations and provider conditions in `LICENSE_REGISTER.json`. Curator-written documentation is CC BY 4.0 and curator tooling is MIT; see `LICENSES.md` and `tools/LICENSE`. Source terms remain controlling.

Public/deidentified human and animal research records retain their original ethical/contextual limitations. Do not attempt re-identification. The release is assembled from an explicit allowlist that excludes private reference material, historical private inventories, local machine paths, Finder files and operational logs. Publisher-provided archive contents remain intact, including original auxiliary or OS metadata; these are distinguished from local additions.

## Quality and known limits

Acceptance checks authentication, transport completeness, hashes, archive safety, interpretable scientific structure, documented reuse terms and bounded quantitative research opportunities. It does not independently recertify every instrument, author assertion or third-party deposition. Per-file reader coverage and limitations are in `reports/`; native format support is separate from Principia application compatibility, which was not exercised in this campaign.

This is an open, source-aware benchmark. Source papers and existing fits may be visible in inputs or model training data. Original cases 01–20 were used in Principia development; replacement case 05 is separately identified. No claim of a hidden unseen test set is made. Independent validation units are uneven, and some cases support only single-system checks. Missing acquisition dates, calibration ambiguity, unequal replicates and author inconsistencies are stated, not filled with guesses.

## Reproducibility and maintenance

`tools/replay.py` verifies assets, reconstructs missing assets from an intact frozen release, or downloads recorded direct URLs and rejects changed bytes. Mutable feeds can drift or disappear; a current download is never silently substituted for a frozen historical snapshot. Older provenance sometimes lacks an exact direct URL, so frozen-copy replay and authoritative context are retained explicitly. Local integrity replay is tested; future remote availability is not guaranteed.

A future maintainer should issue a new case revision for changed scientific assets, record replacements and rights changes, retain negative evidence, and avoid rewriting an accepted manifest. Scientific assets in this release match the accepted acquisition snapshot. New evaluation campaigns and subsequent corpus versions require their own documented scope and release decisions.
