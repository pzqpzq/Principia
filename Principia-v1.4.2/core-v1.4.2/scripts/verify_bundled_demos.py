"""Check the installed showcase in a fresh workspace without connected raw data."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import principia
from principia import Principia


def main() -> None:
    manifest = json.loads((Path(principia.__file__).parent / "demo_projects/manifest.json").read_text())
    assert manifest["project_count"] == 5
    with tempfile.TemporaryDirectory(prefix="principia-demo-qa-") as directory:
        root = Path(directory)
        app = Principia.open(working_directory=root / "reader", cloud_root=root / "cloud",
                             bundled_demos=True)
        try:
            assert len(app.research_sessions.sessions()) == 5
            assert len(app.repository.list_sources()) == 5
            for source in app.repository.list_sources():
                assert source["status"] == "demo"
                assert app.repository.source_root(source["source_id"]) is None
            for project in manifest["projects"]:
                study_id = project["study_id"]
                study = app.data_discovery.get(study_id)
                assert study["request"]["portable_demo"]["raw_data_included"] is False
                assert study["request"]["egress_confirmed"] is False
                session = app.research_sessions.detail(study["session_id"], synchronize=False)
                assert session["title"] == project["title"]
                promoted = [law for law in app.data_discovery.laws(study_id) if law.get("promoted")]
                assert promoted
                for law in promoted:
                    assert law["gate_summary"]["passed"]
                    assert app.data_discovery.law(study_id, law["law_id"])["calibrations"]
                for finding in app.data_discovery.findings(study_id):
                    assert app.data_discovery.finding(study_id, finding["finding_id"])["title"]
                for artifact in app.data_discovery.artifacts(study_id):
                    assert app.data_discovery.artifact(study_id, artifact["artifact_id"])[0].is_file()
            with app.repository.connect() as connection:
                assert not connection.execute("PRAGMA foreign_key_check").fetchall()
            assert app.global_cloud.active()
        finally:
            app.close()
    print(json.dumps({"passed": True, "projects": 5, "connected_source_roots": 0,
                      "bundle_sha256": manifest["sha256"]}))


if __name__ == "__main__":
    main()
