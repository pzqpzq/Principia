# Import Guide

## Recommended treatment

Meta-Principles should be imported as a distinct curated-draft source class, not silently promoted to reviewed `PrincipleCapsule` records. Their broad scope makes expert review especially important.

## Field mapping

| Meta corpus field | Principia v1.4 destination |
| --- | --- |
| `id` | stable external/meta identity; generate a canonical `prn:<area>:<ULID>` only at package publication |
| `title` | `CandidatePrinciple.title` / `PrincipleCapsule.title` |
| `argument` | `claim`; optionally decompose into `ScientificArgument` slots |
| `epistemic_type` | preserve as extension metadata; map to `PrincipleKind` through `principia_kind` |
| `boundary` | `PrincipleScope.conditions` and `PrincipleScope.exclusions` |
| `applications` | tags, Area facets, and retrieval metadata |
| `evidence` | `WorkReference` records, with role retained |
| `linking.relations` | candidate `PrincipleRelation` types |
| `trace_id` | compact `GenerationTrace` reference |
| `review_status` | keep `curated_draft` until domain review |

## Relation direction

The phrase “child relation” is from the perspective of a newly extracted specific Principle. For example, if a new optimization method instantiates the No-Free-Lunch constraint, the new Principle normally `depends_on` the Meta-Principle; if it provides a narrower quantitative version, it may `specializes` or `refines` it.

## Suggested publication gate

1. Verify every evidence URL and bibliographic identity.
2. Confirm that the argument does not exceed the cited work's scope.
3. Review boundary and failure conditions.
4. Remove duplicate or near-equivalent roots.
5. Validate cross-area relations and directionality.
6. Assign canonical Principle IDs and package versions.
7. Publish as a dedicated `meta-*` Area package or as a reserved foundation layer.
