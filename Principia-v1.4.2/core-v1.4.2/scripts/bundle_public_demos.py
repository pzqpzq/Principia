"""Create a curated, portable demo package from an explicit review selection."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from principia import Principia
from principia.demo_bundle import export_demos, export_knowledge


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--working-directory", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()
    selection = json.loads(args.selection.read_text())
    projects = selection["projects"]
    if len(projects) < 3:
        raise ValueError("This release requires at least three reviewed public demo projects")
    app = Principia.open(working_directory=args.working_directory)
    try:
        for project in projects:
            study = app.repository.data_study(project["study_id"])
            if not study:
                raise ValueError("A selected study is missing")
            attempts = app.repository.provider_attempts(study["job_id"])
            if not any(a.get("model") == "deepseek-ai/DeepSeek-V4-Pro" and a.get("state") == "succeeded"
                       and a.get("endpoint_class") == "typed_reasoning" for a in attempts):
                raise ValueError("Every selected project must have successful Pro scientific reasoning")
            if not any(law.get("promoted") and law.get("gate_summary", {}).get("passed")
                       for law in app.data_discovery.laws(project["study_id"])):
                raise ValueError("Every selected project must contain a gate-passing executable law")
        export_knowledge(app, args.output_directory / "knowledge.pcg")
        manifest = export_demos(app, args.output_directory / "public-v142.json.gz", projects,
                                public_source_uris=selection.get("public_source_uris"))
        print(json.dumps(manifest, indent=2))
    finally:
        app.close()


if __name__ == "__main__":
    main()
