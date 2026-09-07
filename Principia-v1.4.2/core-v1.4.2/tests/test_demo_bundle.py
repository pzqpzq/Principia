from __future__ import annotations

import gzip
import hashlib
import json
import shutil

import pytest

from principia import Principia
from principia.demo_bundle import export_demos, install_demos


@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    root = tmp_path_factory.mktemp("public-demo")
    raw = root / "raw"
    raw.mkdir()
    (raw / "measurements.csv").write_text("temperature,response\n" + "".join(
        f"{i},{3*i+2}\n" for i in range(120)))
    app = Principia.open(working_directory=root / "author", cloud_root=root / "cloud")
    try:
        app.repository.register_source("public:test", raw, "public-corpus://test", "Fixture")
        session = app.research_sessions.create_data_discovery_home(
            source_ids=["public:test"], title="Fixture", provider_profile_id="siliconflow", model="")
        study = app.data_discovery.create(source_ids=["public:test"], provider="", budget="fast",
                                          session_id=session["session_id"], defer=False)
        artifact = app.workspace.storage.artifacts_dir / "data-discovery" / study["study_id"] / "audit.json"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(json.dumps({"local_path": str(raw), "slope": 3.0}))
        bundle = root / "export/public-v142.json.gz"
        export_demos(app, bundle, [{"study_id": study["study_id"], "title": "Response scaling",
                                   "summary": "A synthetic portability fixture, not scientific evidence.",
                                   "source_access": [{"url": "https://example.org", "license": "Fixture"}]}])
        expected = {"tests": app.repository.data_tests(study["study_id"]),
                    "laws": app.data_discovery.laws(study["study_id"])}
    finally:
        app.close()
    shutil.rmtree(raw)
    shutil.rmtree(root / "author")
    return bundle, study["study_id"], session["session_id"], expected


def test_demo_is_complete_without_original_workspace_or_data(tmp_path, exported):
    bundle, study, session, expected = exported
    app = Principia.open(working_directory=tmp_path / "reader", cloud_root=tmp_path / "cloud")
    try:
        assert install_demos(app, bundle) == {"state": "installed", "projects": 1}
        assert app.repository.source_root("public:test") is None
        assert app.repository.source("public:test")["status"] == "demo"
        assert app.research_sessions.detail(session, synchronize=False)["title"] == "Response scaling"
        assert len(app.repository.data_tests(study)) == len(expected["tests"])
        laws = app.data_discovery.laws(study)
        assert [r["canonical_ast_digest"] for r in laws] == [r["canonical_ast_digest"] for r in expected["laws"]]
        for law in laws:
            assert app.data_discovery.law(study, law["law_id"])["calibrations"]
        for finding in app.data_discovery.findings(study):
            assert app.data_discovery.finding(study, finding["finding_id"])["title"]
        for artifact in app.data_discovery.artifacts(study):
            assert app.data_discovery.artifact(study, artifact["artifact_id"])[0].is_file()
        with pytest.raises(KeyError, match="unavailable Local source"):
            app.data_discovery.create(source_ids=["public:test"], provider="", defer=False)
        assert app.data_discovery.get(study)["request"]["egress_confirmed"] is False
        assert install_demos(app, bundle)["state"] == "already_handled"
        app.research_sessions.delete_session(session)
        assert install_demos(app, bundle)["state"] == "already_handled"
        assert app.research_sessions.detail(session, synchronize=False) is None
        # A demo installation must leave ordinary local discovery operational.
        own = tmp_path / "own-data"
        own.mkdir()
        (own / "values.csv").write_text("x,y\n" + "".join(f"{i},{2*i+5}\n" for i in range(80)))
        app.repository.register_source("own", own, "external://own", "My data")
        new = app.data_discovery.create(source_ids=["own"], provider="", budget="fast", defer=False)
        assert new["state"] in {"partial", "succeeded"}
        assert app.repository.data_tests(new["study_id"])
    finally:
        app.close()


def test_existing_user_projects_are_not_changed(tmp_path, exported):
    bundle, *_ = exported
    app = Principia.open(working_directory=tmp_path / "reader", cloud_root=tmp_path / "cloud")
    try:
        app.research_sessions.create_data_discovery_home(source_ids=["mine"], title="My project",
                                                        provider_profile_id="siliconflow", model="")
        assert install_demos(app, bundle)["state"] == "skipped_existing_workspace"
        assert app.repository.list_sources() == []
    finally:
        app.close()


def test_local_project_publication_requires_explicit_mapping_without_changing_source(tmp_path, exported):
    bundle, study, _, _ = exported
    app = Principia.open(working_directory=tmp_path / "author", cloud_root=tmp_path / "cloud")
    try:
        install_demos(app, bundle)
        folder = tmp_path / "public-data"
        folder.mkdir()
        app.repository.register_source("public:test", folder, "local-source://test", "Public data")
        # Model a local source; re-registering an imported ID preserves its URI.
        with app.repository.connect() as conn:
            conn.execute("UPDATE local_sources_v14 SET portable_uri=? WHERE source_id=?",
                         ("local-source://test", "public:test"))
        projects = json.loads(bundle.with_name("manifest.json").read_text())["projects"]
        target = tmp_path / "publication/public-v142.json.gz"
        with pytest.raises(ValueError, match="public-corpus"):
            export_demos(app, target, projects)
        for mapping in ({"unknown": "public-corpus://test"}, {"public:test": "local-source://test"}):
            with pytest.raises(ValueError, match="Public source mappings"):
                export_demos(app, target, projects, public_source_uris=mapping)
        export_demos(app, target, projects, public_source_uris={"public:test": "public-corpus://test"})
        assert app.repository.source_root("public:test") == folder
        assert app.repository.source("public:test")["portable_uri"] == "local-source://test"
        rows = json.loads(gzip.decompress(target.read_bytes()))["tables"]["local_sources_v14"]
        assert rows[0]["portable_uri"] == "public-corpus://test"
        assert rows[0]["absolute_root"] == ""
        assert rows[0]["status"] == "demo"
    finally:
        app.close()


def test_tampered_and_escaping_bundles_are_rejected(tmp_path, exported):
    bundle, *_ = exported
    copied = tmp_path / "bundle"
    shutil.copytree(bundle.parent, copied)
    target = copied / bundle.name
    app = Principia.open(working_directory=tmp_path / "reader", cloud_root=tmp_path / "cloud")
    try:
        target.write_bytes(target.read_bytes() + b"tampered")
        with pytest.raises(ValueError, match="integrity"):
            install_demos(app, target)
        data = json.loads(gzip.decompress(bundle.read_bytes()))
        data["artifacts"][0]["path"] = "../../escape.json"
        target.write_bytes(gzip.compress(json.dumps(data).encode()))
        manifest_path = copied / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(manifest))
        with pytest.raises(ValueError, match="artifact path"):
            install_demos(app, target)
        assert app.repository.list_sources() == []
    finally:
        app.close()
