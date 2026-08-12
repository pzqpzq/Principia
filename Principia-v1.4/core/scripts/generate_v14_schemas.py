from __future__ import annotations

import argparse
import json
from pathlib import Path

from principia.domain import (
    AreaManifest,
    CandidateDraftBatch,
    CandidatePrinciple,
    CatalogEntry,
    PrincipleCapsule,
    PublicationChangeset,
)

MODELS = {
    "principle-capsule-v1.schema.json": PrincipleCapsule,
    "candidate-principle-v1.schema.json": CandidatePrinciple,
    "area-manifest-v1.schema.json": AreaManifest,
    "catalog-entry-v1.schema.json": CatalogEntry,
    "publication-changeset-v1.schema.json": PublicationChangeset,
    "candidate-draft-batch-v1.schema.json": CandidateDraftBatch,
}


def render(model: type) -> str:
    schema = model.model_json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    return json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    target = Path(__file__).resolve().parents[1] / "src" / "principia" / "schemas"
    target.mkdir(parents=True, exist_ok=True)
    changed: list[str] = []
    for filename, model in MODELS.items():
        expected = render(model)
        path = target / filename
        actual = path.read_text(encoding="utf-8") if path.exists() else ""
        if actual != expected:
            changed.append(filename)
            if not args.check:
                path.write_text(expected, encoding="utf-8")
    if args.check and changed:
        print("Schema drift: " + ", ".join(changed))
        return 1
    print(("Checked" if args.check else "Generated") + f" {len(MODELS)} schemas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
