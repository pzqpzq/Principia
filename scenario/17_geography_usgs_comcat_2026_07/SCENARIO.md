# USGS ComCat July 2026 global M2.5+ earthquakes

## Source and payload

- Publisher: U.S. Geological Survey
- Authoritative landing page: https://earthquake.usgs.gov/fdsnws/event/1
- Version/release: FDSN Event service snapshot
- Identifier(s): See PROVENANCE.json
- License/access: U.S. Government public domain
- Installed official/source-metadata files: 4
- Installed official/source-metadata bytes: 8179735

Selection rule: Query 2026-07-01 inclusive to 2026-08-01 exclusive, eventtype=earthquake, minmagnitude=2.5, orderby=time-asc; retain GeoJSON, QuakeML, count, and service version.

## Intended analysis challenge

Separate physical space-time clustering from catalog completeness, contributor, review-status, and uncertainty effects.

## Known confounders and failure modes

Network coverage, magnitude type, review latency, duplicate/contributed solutions, depth and location uncertainty, and aftershock dependence.

## Evidence boundary

This scenario is hypothesis-generation material, not a precomputed answer. A pattern is not a novel finding until it has exact file/row/time provenance, units and computation, uncertainty, missingness and confounder analysis, falsifiers and negative evidence, comparison with source publications, robustness checks, and a current literature novelty review.

No source values were normalized, imputed, filtered, or converted for this corpus. Archives remain archives unless the publisher supplied ordinary files directly. USER_BRIEF.txt is generated simulation context and is not scientific evidence.
