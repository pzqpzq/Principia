#!/usr/bin/env python3
"""Generate the public JSON Schemas for Global Cloud v2 records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from principia.cloud.models_v2 import (
    FoundationAssessmentRevision,
    FoundationGapRevision,
    FoundationLinkRevision,
    PrincipleRevisionV2,
    PrincipleWorkLinkV2,
    RelationRevisionV2,
    WorkRevisionV2,
)

MODELS = {
    "work-revision.schema.json": WorkRevisionV2,
    "principle-revision.schema.json": PrincipleRevisionV2,
    "principle-work-link.schema.json": PrincipleWorkLinkV2,
    "relation-revision.schema.json": RelationRevisionV2,
    "foundation-link.schema.json": FoundationLinkRevision,
    "foundation-assessment.schema.json": FoundationAssessmentRevision,
    "foundation-gap.schema.json": FoundationGapRevision,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for name, model in MODELS.items():
        (output / name).write_text(
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
