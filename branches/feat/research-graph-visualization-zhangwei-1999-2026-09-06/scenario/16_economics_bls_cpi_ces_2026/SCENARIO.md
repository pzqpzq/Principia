# BLS CPI and CES selected bulk time-series files

## Source and payload

- Publisher: U.S. Bureau of Labor Statistics
- Authoritative landing page: https://download.bls.gov/pub/time.series/
- Version/release: bulk directory snapshot dated 2026-08-12
- Identifier(s): See PROVENANCE.json
- License/access: U.S. Government public data
- Installed official/source-metadata files: 16
- Installed official/source-metadata bytes: 14920354

Selection rule: Retain the fixed CPI AllItems, Housing, and Medical files; CES TotalNonfarm, Manufacturing, and Information employment files; and their selected dictionaries.

## Intended analysis challenge

Test lagged or regime-dependent relationships among prices, sector employment, and structural changes without ignoring revisions or seasonal flags.

## Known confounders and failure modes

Seasonal adjustment, revisions, differing frequency and units, series discontinuities, area coverage, base periods, and spurious lag selection.

## Evidence boundary

This scenario is hypothesis-generation material, not a precomputed answer. A pattern is not a novel finding until it has exact file/row/time provenance, units and computation, uncertainty, missingness and confounder analysis, falsifiers and negative evidence, comparison with source publications, robustness checks, and a current literature novelty review.

No source values were normalized, imputed, filtered, or converted for this corpus. Archives remain archives unless the publisher supplied ordinary files directly. USER_BRIEF.txt is generated simulation context and is not scientific evidence.
