# Principia v1.4 Import Guide

The canonical editorial records are in `data/meta_principles.jsonl`. The closest current runtime projection is `data/principia_candidate_projection.jsonl`, which maps each record to the existing `CandidatePrinciple` fields and retains richer metadata under `raw_legacy_payload`.

Recommended publication sequence:

```text
JSONL validation
    → domain review
    → relation and evidence review
    → Candidate import
    → Admin approval / editing
    → Principle Capsule promotion
    → area-package build
```

Do not import the corpus directly as `reviewed_capsules`. All records intentionally remain `unassessed` / `curated_draft` until expert review.
