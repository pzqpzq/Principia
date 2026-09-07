"""Portable public ASD projects: inert records, derived artifacts, no raw folders.

Export is explicit. Bundled projects are installed once, at UI startup, only in
an empty workspace. Deleting a demo never causes it to reappear on restart.
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import json
import re
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from .models import utc_now

SCHEMA = "principia.public-discovery-demos/v1"
# SQL identifiers are fixed application constants, never supplied by a bundle.
TABLES = (
    "local_sources_v14", "research_projects", "research_sessions", "v14_jobs",
    "data_studies", "data_discovery_runs", "data_assets", "data_views", "data_alignments",
    "data_hypotheses", "data_tests", "data_findings", "data_extra_principles",
    "data_evidence_links", "data_principle_links", "data_derived_principle_drafts",
    "data_job_units", "study_blueprints", "scientific_programs", "scientific_split_manifests",
    "scientific_transform_graphs", "scientific_law_families", "scientific_law_calibrations",
    "scientific_law_candidates", "scientific_law_evaluations", "scientific_decisions",
    "research_graph_items", "research_graph_state", "research_artifacts",
    "workspace_records", "workspace_edges", "v14_job_events", "provider_attempts", "provider_usage",
)
PRIVATE_PATH = re.compile(r"(?:(?:[A-Za-z]:\\)|/(?:Users|home|private|var|tmp)/)[^\s\"'<>]+")
SECRET = re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")
SECRET_KEYS = {"api_key", "authorization", "access_token", "password", "credential", "credentials"}
MAX_EXPANDED_BYTES = 96 * 1024**2


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items() if k.casefold() not in SECRET_KEYS}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    if isinstance(value, str):
        if SECRET.search(value):
            raise ValueError("A credential-like value was found in exportable demo content")
        return PRIVATE_PATH.sub("[local path omitted]", value)
    return value


def _encode(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


def _select(conn, table: str, column: str, ids: set[str]) -> list[dict]:
    if not ids:
        return []
    marks = ",".join("?" for _ in ids)
    return [dict(r) for r in conn.execute(
        f'SELECT * FROM "{table}" WHERE "{column}" IN ({marks})', sorted(ids))]


def export_knowledge(product, destination: Path) -> dict:
    """Package the exact verified public knowledge used by the demo campaign."""
    from .cloud.canonical import PCG_ENTRIES, verify_cloud_snapshot

    active = product.global_cloud.active()
    if not active or destination.exists():
        raise ValueError("A verified public Cloud and a new snapshot destination are required")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(PCG_ENTRIES):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, (active["release_root"] / name).read_bytes())
    manifest = verify_cloud_snapshot(destination)
    return {"file": destination.name, "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            "release_id": manifest.release_id, "content_digest": manifest.content_digest,
            "principle_count": manifest.total_principle_count or manifest.principle_count}


def export_demos(product, destination: Path, projects: list[dict[str, Any]], *,
                 public_source_uris: dict[str, str] | None = None) -> dict:
    """Export explicitly reviewed public studies; never copy the runtime DB."""
    if destination.exists():
        raise ValueError("Demo export destination already exists")
    studies = {str(p["study_id"]) for p in projects}
    if not studies or len(studies) != len(projects):
        raise ValueError("Select distinct completed public studies")
    with product.repository.connect() as conn:
        conn.execute("BEGIN")
        study_rows = _select(conn, "data_studies", "study_id", studies)
        if len(study_rows) != len(studies) or any(r["state"] not in {"succeeded", "partial"} for r in study_rows):
            raise ValueError("Every demo must be a completed discovery")
        sessions = {r["session_id"] for r in study_rows}
        jobs = {r["job_id"] for r in study_rows}
        sources = {s for r in study_rows for s in json.loads(r["source_ids_json"])}
        source_rows = _select(conn, "local_sources_v14", "source_id", sources)
        # Publishing an ordinary local project requires an explicit, reviewed
        # public-source mapping. Change only the exported copy, never a user's
        # connected folder or its discovery receipts.
        mappings = public_source_uris or {}
        if not set(mappings) <= sources or any(
            not re.fullmatch(r"public-corpus://[A-Za-z0-9][A-Za-z0-9_.-]*", uri)
            for uri in mappings.values()
        ):
            raise ValueError("Public source mappings must identify selected public-corpus sources")
        for row in source_rows:
            if row["source_id"] in mappings:
                row["portable_uri"] = mappings[row["source_id"]]
        if len(source_rows) != len(sources) or any(not r["portable_uri"].startswith("public-corpus://") for r in source_rows):
            raise ValueError("Only explicitly identified public-corpus sources can be bundled")
        session_rows = _select(conn, "research_sessions", "session_id", sessions)
        if len(sessions) != len(studies) or any(r["active_run_id"] for r in session_rows):
            raise ValueError("Select one standalone data study per demo project")
        project_ids = {r["project_id"] for r in session_rows if r["project_id"]}
        tables = {}
        for table in TABLES:
            columns = {r["name"] for r in conn.execute(f'PRAGMA table_info("{table}")')}
            if table == "local_sources_v14":
                rows = source_rows
            elif table == "research_projects":
                rows = _select(conn, table, "project_id", project_ids)
            elif table == "research_sessions":
                rows = session_rows
            elif "study_id" in columns:
                rows = _select(conn, table, "study_id", studies)
            elif "session_id" in columns:
                rows = _select(conn, table, "session_id", sessions)
            elif "job_id" in columns:
                rows = _select(conn, table, "job_id", jobs)
            else:
                raise ValueError(f"No portable scope for {table}")
            tables[table] = rows
    by_study = {p["study_id"]: p for p in projects}
    for row in tables["data_studies"]:
        request = json.loads(row["request_json"])
        request["portable_demo"] = {
            "raw_data_included": False, "source_access": by_study[row["study_id"]]["source_access"],
            "description": by_study[row["study_id"]]["summary"],
            "editorial_review": by_study[row["study_id"]].get("editorial_review", ""),
            "evidence_boundary": "Recorded evidence is available offline. Reconnect source data to run a new discovery.",
        }
        request["egress_confirmed"] = False  # consent is never transferred to another user
        row["request_json"] = json.dumps(request)
    session_metadata = {r["session_id"]: by_study[r["study_id"]] for r in study_rows}
    for row in tables["research_sessions"]:
        metadata = session_metadata[row["session_id"]]
        row.update(title=metadata["title"], summary=metadata["summary"], archived_at="")
    for row in tables["local_sources_v14"]:
        row.update(absolute_root="", status="demo", source_kind="demo",
                   display_location="Bundled public demo · connect local data to rerun")
        payload = json.loads(row["payload_json"])
        payload.update(status="demo", portable_uri=row["portable_uri"], display_location=row["display_location"])
        row["payload_json"] = json.dumps(payload)
    for table, rows in tables.items():
        for row in rows:
            if table == "v14_job_events":
                row.pop("sequence", None)  # preserve event identity without reusing global autoincrements
            for key, value in list(row.items()):
                row[key] = (json.dumps(_clean(json.loads(value)), ensure_ascii=False, allow_nan=False)
                            if key.endswith("_json") else _clean(value))
        rows.sort(key=lambda row: _encode(row))
    artifacts = []
    omitted = []
    for study in sorted(studies):
        root = product.workspace.storage.artifacts_dir / "data-discovery" / study
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(root).as_posix()
            # Preserve analysis receipts and visual evidence; exclude extracted
            # inputs and bulk numerical intermediates. Never execute imported code.
            if ("response-panels" in path.relative_to(root).parts
                    or any(part.endswith(".batches") for part in path.relative_to(root).parts)
                    or path.name == "input.json"
                    or path.suffix not in {".json", ".jsonl", ".md", ".png", ".svg", ".py"}
                    or path.stat().st_size > 8 * 1024**2):
                omitted.append({"study_id": study, "name": relative, "bytes": path.stat().st_size})
                continue
            original = path.read_bytes()
            body = original
            if path.suffix != ".png":
                if path.suffix == ".json":
                    body = _encode(_clean(json.loads(original)))
                elif path.suffix == ".jsonl":
                    body = b"\n".join(_encode(_clean(json.loads(line))) for line in original.splitlines() if line)
                else:
                    body = _clean(original.decode()).encode()
            artifacts.append({"study_id": study, "path": relative,
                              "original_sha256": hashlib.sha256(original).hexdigest(),
                              "sha256": hashlib.sha256(body).hexdigest(),
                              "content": base64.b64encode(body).decode()})
    body = _encode({"schema": SCHEMA, "projects": _clean(projects), "tables": tables,
                    "artifacts": artifacts, "omitted_artifacts": omitted,
                    "provenance": "Scientific digests refer to original receipts. Export hashes cover path-redacted copies; equations, numerical evidence, gates and negative outcomes are unchanged."})
    if len(body) > MAX_EXPANDED_BYTES:
        raise ValueError("Demo bundle exceeds the expanded size budget")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(gzip.compress(body, mtime=0))
    manifest = {"schema": SCHEMA, "bundle": destination.name,
                "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                "bytes": destination.stat().st_size, "expanded_bytes": len(body),
                "projects": _clean(projects), "project_count": len(projects),
                "source_count": len(sources), "raw_data_included": False}
    knowledge = destination.with_name("knowledge.pcg")
    if knowledge.is_file():
        from .cloud.canonical import verify_cloud_snapshot

        verified = verify_cloud_snapshot(knowledge)
        manifest["knowledge"] = {"file": knowledge.name, "sha256": hashlib.sha256(knowledge.read_bytes()).hexdigest(),
                                 "release_id": verified.release_id, "content_digest": verified.content_digest}
    destination.with_name("manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return manifest


def install_demos(product, bundle: Path, *, only_if_empty: bool = True) -> dict:
    """Validate inert data, then install records and mark completion atomically."""
    manifest = json.loads(bundle.with_name("manifest.json").read_text())
    compressed = bundle.read_bytes()
    if hashlib.sha256(compressed).hexdigest() != manifest["sha256"]:
        raise ValueError("Demo bundle integrity check failed")
    with gzip.open(bundle, "rb") as stream:
        body = stream.read(MAX_EXPANDED_BYTES + 1)
    if len(body) > MAX_EXPANDED_BYTES:
        raise ValueError("Demo bundle exceeds the expanded size budget")
    payload = json.loads(body)
    if payload.get("schema") != SCHEMA or set(payload["tables"]) != set(TABLES):
        raise ValueError("Unsupported demo bundle schema")
    studies = {r["study_id"] for r in payload["tables"]["data_studies"]}
    artifacts = []
    for item in payload["artifacts"]:
        name = PurePosixPath(item["path"])
        study = item["study_id"]
        if (study not in studies or not re.fullmatch(r"study:[A-Za-z0-9_-]+", study)
                or name.is_absolute() or ".." in name.parts or "\\" in item["path"]):
            raise ValueError("Invalid demo artifact path")
        content = base64.b64decode(item["content"], validate=True)
        if hashlib.sha256(content).hexdigest() != item["sha256"]:
            raise ValueError("Demo artifact integrity check failed")
        artifacts.append((study, name, content))
    written: list[Path] = []
    try:
        with product.repository.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("CREATE TABLE IF NOT EXISTS demo_bundle_installations (bundle_id TEXT PRIMARY KEY, digest TEXT NOT NULL, state TEXT NOT NULL, installed_at TEXT NOT NULL)")
            # A stable release ID, rather than a content hash, respects deletions
            # even after a minor packaging update.
            bundle_id = "public-v1.4.2"
            if conn.execute("SELECT 1 FROM demo_bundle_installations WHERE bundle_id=?", (bundle_id,)).fetchone():
                return {"state": "already_handled"}
            occupied = conn.execute("SELECT 1 FROM research_sessions LIMIT 1").fetchone()
            if occupied and only_if_empty:
                conn.execute("INSERT INTO demo_bundle_installations VALUES (?,?,?,?)",
                             (bundle_id, manifest["sha256"], "skipped_existing_workspace", utc_now()))
                return {"state": "skipped_existing_workspace"}
            conn.execute("PRAGMA defer_foreign_keys=ON")
            for table in TABLES:
                allowed = {r["name"] for r in conn.execute(f'PRAGMA table_info("{table}")')}
                for row in payload["tables"][table]:
                    if not set(row) <= allowed:
                        raise ValueError(f"Unknown demo columns for {table}")
                    keys = list(row)
                    columns = ",".join(f'"{k}"' for k in keys)
                    marks = ",".join("?" for _ in keys)
                    conn.execute(f'INSERT INTO "{table}" ({columns}) VALUES ({marks})', [row[k] for k in keys])
            violations = conn.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise ValueError("Demo evidence contains broken references")
            for study, relative, content in artifacts:
                root = product.workspace.storage.artifacts_dir / "data-discovery" / study
                target = root.joinpath(*relative.parts)
                if (target.exists() or not root.resolve().is_relative_to(product.workspace.storage.artifacts_dir.resolve())
                        or not target.resolve().is_relative_to(root.resolve())):
                    raise ValueError("Demo artifact target already exists or escapes its study")
                target.parent.mkdir(parents=True, exist_ok=True)
                written.append(target)
                target.write_bytes(content)
            conn.execute("INSERT INTO demo_bundle_installations VALUES (?,?,?,?)",
                         (bundle_id, manifest["sha256"], "installed", utc_now()))
    except BaseException:
        for path in reversed(written):
            path.unlink(missing_ok=True)
        raise
    return {"state": "installed", "projects": len(payload["projects"])}


def install_bundled_demos(product) -> dict:
    bundle = Path(__file__).parent / "demo_projects/public-v142.json.gz"
    if not bundle.is_file():
        return {"state": "not_bundled"}
    manifest = json.loads(bundle.with_name("manifest.json").read_text())
    knowledge = manifest.get("knowledge")
    if knowledge and not product.global_cloud.active():
        product.global_cloud.install_snapshot(bundle.with_name("knowledge.pcg"), expected_sha256=knowledge["sha256"])
    return install_demos(product, bundle)
