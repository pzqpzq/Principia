# Domain Review Checklist

Use this checklist before importing a Meta-Principle into a reviewed Global package.

## Identity and scope

- [ ] The title denotes one reusable Principle rather than a paper topic.
- [ ] The argument does not exceed the cited work or accepted disciplinary interpretation.
- [ ] Conditions and failure regimes are explicit.
- [ ] The type distinguishes theorem, mechanism, empirical law, heuristic, and hypothesis.
- [ ] The application list is broad enough for retrieval but does not claim universal validity.

## Evidence

- [ ] Every source URL resolves to the intended public work.
- [ ] Original works are included when accessible; later refinements are labelled.
- [ ] Formal results are linked to a proof-bearing source.
- [ ] Empirical claims include replication, review, or an explicit contested status where appropriate.
- [ ] No paper title or URL is used as a substitute for checking the underlying claim.

## Relations

- [ ] Relation direction follows `LINKING_PROTOCOL.md`.
- [ ] `supports` and `contradicts` are used only when scopes overlap.
- [ ] `generalizes` is used sparingly and reviewed for hidden assumptions.
- [ ] Analogies are not converted into evidence.
- [ ] Cross-area dependencies use stable IDs and contain a rationale.

## Publication

- [ ] A canonical `prn:<area>:<ULID>` is assigned without discarding the external `meta:*` identity.
- [ ] Generation and human-review trace is complete.
- [ ] Content digest is regenerated after edits.
- [ ] Package schema, relation integrity, and SQLite checks pass.
- [ ] The publication record states that broad Meta-Principles remain scope-bounded foundations, not truth certificates.
