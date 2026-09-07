from __future__ import annotations

import json
import math
import re
import shutil
from pathlib import Path
from typing import Any

from ..cloud import CloudSearchRequest, ResearchGoalRunRequest
from ..domain import canonical_sha256, monotonic_ulid
from ..models import utc_now
from ..persistence import V14WorkspaceRepository
from .project_description import describe_project

_TERMINAL_RUN_STATES = {"succeeded", "partial", "failed", "cancelled"}


class ResearchSessionService:
    """Durable, graph-first research sessions grouped into one-level projects.

    The goal-run coordinator remains responsible for scientific work.  This
    service gives every run a stable home, snapshots its result memberships,
    and owns the small, optimistic graph-editing contract used by the UI.
    """

    def __init__(
        self, repository: V14WorkspaceRepository, goal_runs: Any, global_cloud: Any,
        *, artifacts_root: Path | None = None, outputs_root: Path | None = None,
    ) -> None:
        self.repository = repository
        self.goal_runs = goal_runs
        self.global_cloud = global_cloud
        self.artifacts_root = artifacts_root
        self.outputs_root = outputs_root
        self.goal_runs.set_session_projection_writer(self.finalize_goal_run)

    @staticmethod
    def _title(goal: str) -> str:
        compact = " ".join(goal.split())
        return compact if len(compact) <= 72 else compact[:69].rstrip() + "…"

    @staticmethod
    def _decode(row: Any) -> dict[str, Any]:
        columns = set(row.keys())
        return {
            "session_id": str(row["session_id"]),
            "project_id": row["project_id"],
            "title": str(row["title"]),
            "active_run_id": str(row["active_run_id"] or ""),
            "state": str(row["state"]),
            "revision": int(row["revision"]),
            "graph_revision": int(row["graph_revision"]),
            "source_ids": json.loads(row["source_ids_json"] or "[]"),
            "provider_profile_id": str(row["provider_profile_id"]),
            "model": str(row["model"]),
            "archived": bool(row["archived_at"]),
            "archived_at": str(row["archived_at"]),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "kind": str(row["kind"] if "kind" in columns else "research"),
            "source_set_digest": str(
                row["source_set_digest"] if "source_set_digest" in columns else ""
            ),
            "summary": str(row["summary"] if "summary" in columns else ""),
            "canonical_session_id": str(
                row["canonical_session_id"]
                if "canonical_session_id" in columns
                else row["session_id"]
            ),
        }

    def source_set_digest(self, source_ids: list[str]) -> str:
        """Identify a data project by canonical local roots, not UI registrations.

        A folder can be connected more than once and receive different source
        IDs.  Source-ID hashing therefore created duplicate projects for the
        same bytes.  Resolved root identities keep the digest stable while the
        digest itself remains path-free outside persistence.
        """

        normalized: list[str] = []
        for source_id in dict.fromkeys(
            str(value).strip() for value in source_ids if str(value).strip()
        ):
            root = self.repository.source_root(source_id)
            normalized.append(
                f"root:{root.expanduser().resolve()}" if root is not None else f"source:{source_id}"
            )
        normalized = sorted(set(normalized))
        return canonical_sha256(
            {"schema": "principia.data-source-set/v2", "source_roots": normalized}
        )

    def projects(self, *, include_archived: bool = False) -> list[dict[str, Any]]:
        where = "" if include_archived else "WHERE p.archived_at=''"
        with self.repository.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT p.*, COUNT(s.session_id) AS session_count
                FROM research_projects p
                LEFT JOIN research_sessions s ON s.project_id=p.project_id AND s.archived_at=''
                {where}
                GROUP BY p.project_id
                ORDER BY p.sort_order, p.updated_at DESC, p.project_id
                """
            ).fetchall()
        return [
            {
                "project_id": row["project_id"],
                "title": row["title"],
                "sort_order": int(row["sort_order"]),
                "session_count": int(row["session_count"]),
                "archived": bool(row["archived_at"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def create_project(self, title: str) -> dict[str, Any]:
        now = utc_now()
        project_id = f"project:{monotonic_ulid()}"
        with self.repository.connect() as conn:
            next_order = int(
                conn.execute(
                    "SELECT COALESCE(MAX(sort_order),-1)+1 FROM research_projects"
                ).fetchone()[0]
            )
            conn.execute(
                "INSERT INTO research_projects VALUES (?,?,?,?,?,?)",
                (project_id, title.strip(), next_order, "", now, now),
            )
        return next(item for item in self.projects() if item["project_id"] == project_id)

    def update_project(
        self, project_id: str, *, title: str | None = None, archived: bool | None = None
    ) -> dict[str, Any]:
        now = utc_now()
        with self.repository.connect() as conn:
            row = conn.execute(
                "SELECT * FROM research_projects WHERE project_id=?", (project_id,)
            ).fetchone()
            if row is None:
                raise KeyError(project_id)
            conn.execute(
                "UPDATE research_projects SET title=?, archived_at=?, updated_at=? WHERE project_id=?",
                (
                    title.strip() if title is not None else row["title"],
                    now if archived is True else "" if archived is False else row["archived_at"],
                    now,
                    project_id,
                ),
            )
        return next(
            item
            for item in self.projects(include_archived=True)
            if item["project_id"] == project_id
        )

    def delete_project(self, project_id: str) -> dict[str, Any]:
        """Permanently remove an empty organizational project."""
        with self.repository.connect() as conn:
            row = conn.execute(
                "SELECT title FROM research_projects WHERE project_id=?", (project_id,)
            ).fetchone()
            if row is None:
                raise KeyError(project_id)
            count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM research_sessions WHERE project_id=?", (project_id,)
                ).fetchone()[0]
            )
            if count:
                raise ValueError("delete or move the research sessions in this project first")
            conn.execute("DELETE FROM research_projects WHERE project_id=?", (project_id,))
        return {"deleted": True, "project_id": project_id, "title": str(row["title"])}

    def sessions(
        self,
        *,
        project_id: str | None = None,
        include_archived: bool = False,
        include_aliases: bool = False,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        if session_id:
            clauses.append("session_id=?")
            values.append(session_id)
        if not include_archived:
            clauses.append("archived_at='' ")
        if not include_aliases:
            clauses.append(
                "(canonical_session_id='' OR canonical_session_id=session_id)"
            )
        if project_id == "ungrouped":
            clauses.append("project_id IS NULL")
        elif project_id:
            clauses.append("project_id=?")
            values.append(project_id)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        with self.repository.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM research_sessions {where} "
                "ORDER BY updated_at DESC, session_id DESC",
                tuple(values),
            ).fetchall()
            session_ids = [str(row["session_id"]) for row in rows]
            if not session_ids:
                return []
            placeholders = ",".join("?" for _ in session_ids)
            source_labels = {
                str(row["source_id"]): str(row["display_name"])
                for row in conn.execute(
                    "SELECT source_id, display_name FROM local_sources_v14 "
                    "WHERE status!='removed'"
                ).fetchall()
            }
            graph_counts = {
                str(row["session_id"]): int(row["count"])
                for row in conn.execute(
                    f"SELECT session_id, COUNT(*) count FROM research_graph_items "
                    f"WHERE visible=1 AND session_id IN ({placeholders}) GROUP BY session_id",
                    tuple(session_ids),
                ).fetchall()
            }
            goal_result_counts = {
                str(row["session_id"]): int(row["count"])
                for row in conn.execute(
                    f"SELECT session_id, COUNT(*) count FROM research_session_results "
                    f"WHERE session_id IN ({placeholders}) GROUP BY session_id",
                    tuple(session_ids),
                ).fetchall()
            }
            data_run_counts = {
                str(row["session_id"]): int(row["count"])
                for row in conn.execute(
                    f"SELECT session_id, COUNT(*) count FROM data_discovery_runs "
                    f"WHERE session_id IN ({placeholders}) GROUP BY session_id",
                    tuple(session_ids),
                ).fetchall()
            }
            latest_studies: dict[str, Any] = {}
            for study_row in conn.execute(
                f"SELECT r.session_id AS project_session_id, d.state, json_object('target_bindings', json_extract(b.payload_json,'$.target_bindings')) AS blueprint_json, "
                "json_object('asset_count',json_extract(d.coverage_json,'$.asset_count'),"
                "'executed_test_count',json_extract(d.coverage_json,'$.executed_test_count'),"
                "'validated_rule_count',json_extract(d.coverage_json,'$.validated_rule_count'),"
                "'rule_count',json_extract(d.coverage_json,'$.rule_count'),"
                "'surviving_finding_count',json_extract(d.coverage_json,'$.surviving_finding_count'),"
                "'scientific_program_execution',json_object('promoted_rule_count',"
                "json_extract(d.coverage_json,'$.scientific_program_execution.promoted_rule_count'))) AS coverage_json, "
                "json_object('objective',json_extract(d.request_json,'$.objective')) AS request_json "
                f"FROM data_discovery_runs r JOIN data_studies d ON d.study_id=r.study_id "
                "LEFT JOIN study_blueprints b ON b.study_id=d.study_id "
                f"WHERE r.session_id IN ({placeholders}) "
                "ORDER BY r.session_id, "
                "r.sequence DESC",
                tuple(session_ids),
            ).fetchall():
                latest_studies.setdefault(str(study_row["project_session_id"]), study_row)
            finding_counts = {
                str(row["session_id"]): int(row["count"])
                for row in conn.execute(
                    f"SELECT r.session_id, COUNT(*) count FROM data_findings f "
                    f"JOIN data_discovery_runs r ON r.study_id=f.study_id "
                    f"WHERE r.session_id IN ({placeholders}) "
                    "GROUP BY r.session_id",
                    tuple(session_ids),
                ).fetchall()
            }
            test_counts = {
                str(row["session_id"]): int(row["count"])
                for row in conn.execute(
                    f"SELECT r.session_id, COUNT(*) count FROM data_tests t "
                    f"JOIN data_discovery_runs r ON r.study_id=t.study_id "
                    f"WHERE r.session_id IN ({placeholders}) "
                    "GROUP BY r.session_id",
                    tuple(session_ids),
                ).fetchall()
            }

        items: list[dict[str, Any]] = []
        for row in rows:
            item = self._decode(row)
            session_id = str(item["session_id"])
            labels = [
                source_labels.get(str(source_id), "")
                for source_id in list(item.get("source_ids") or [])
            ]
            labels = [label for label in labels if label]
            study_row = latest_studies.get(session_id)
            coverage: dict[str, Any] = {}
            objective = ""
            if study_row is not None:
                item["state"] = str(study_row["state"])
                try:
                    coverage = json.loads(str(study_row["coverage_json"] or "{}"))
                    request = json.loads(str(study_row["request_json"] or "{}"))
                except json.JSONDecodeError:
                    coverage, request = {}, {}
                objective = str(request.get("objective") or "").strip()
            scientific_program_execution = dict(
                coverage.get("scientific_program_execution") or {}
            )
            scientific_rule_count = int(
                scientific_program_execution.get("promoted_rule_count") or 0
            )
            rule_count = int(coverage.get("rule_count") or 0)
            counts = {
                "graph": graph_counts.get(session_id, 0),
                "goal_results": goal_result_counts.get(session_id, 0),
                "findings": finding_counts.get(session_id, 0),
                "tests": max(
                    test_counts.get(session_id, 0),
                    int(coverage.get("executed_test_count") or 0),
                ),
                "assets": int(coverage.get("asset_count") or 0),
                "rules": max(
                    int(coverage.get("validated_rule_count") or 0),
                    scientific_rule_count,
                ),
                "legacy_rules": max(
                    0,
                    rule_count - scientific_rule_count,
                ),
                "supported_findings": int(coverage.get("surviving_finding_count") or 0),
                "runs": data_run_counts.get(session_id, 0),
            }
            has_content = any(
                counts[key] > 0 for key in ("graph", "goal_results", "findings", "tests")
            )
            looks_generated = False
            if study_row is not None and labels:
                label = " + ".join(labels[:2])
                if len(labels) > 2:
                    label += f" +{len(labels) - 2}"
                generated_title = self._title(f"Discovery · {label}")
                stored_title = str(item.get("title") or "").strip()
                looks_generated = (
                    not stored_title
                    or stored_title == objective
                    or stored_title.casefold().startswith("discover data")
                    or stored_title.casefold().startswith("data discovery")
                    or stored_title.casefold().startswith("autonomously discover")
                    or len(stored_title) > 96
                )
                item["display_title"] = generated_title if looks_generated else stored_title
            else:
                item["display_title"] = item["title"]
            dataset_summary = ""
            if study_row is not None or item.get("kind") == "data_discovery":
                blueprint = json.loads(study_row["blueprint_json"] or "{}") if study_row is not None else {}
                descriptive_title, dataset_summary = describe_project(labels, blueprint)
                if str(item["display_title"]).startswith("Discovery ·") or looks_generated:
                    item["display_title"] = descriptive_title
            summary_parts: list[str] = []
            if counts["runs"] > 1:
                summary_parts.append(f"{counts['runs']} runs")
            if counts["assets"]:
                summary_parts.append(f"{counts['assets']} assets")
            if counts["tests"]:
                summary_parts.append(
                    f"{counts['tests']} tests total"
                    if counts["runs"] > 1
                    else f"{counts['tests']} tests"
                )
            if counts["supported_findings"]:
                summary_parts.append(f"{counts['supported_findings']} supported")
            if counts["rules"]:
                summary_parts.append(f"{counts['rules']} rules")
            elif counts["legacy_rules"]:
                summary_parts.append(
                    f"{counts['legacy_rules']} exploratory equations"
                )
            item.update(
                {
                    "kind": "data_discovery" if study_row is not None or item.get("kind") == "data_discovery" else "research",
                    "source_labels": labels,
                    "objective": objective,
                    "summary": (
                        item.get("summary")
                        if item.get("summary") not in {None, "", "Ready for the first local-data discovery run"}
                        else dataset_summary or " · ".join(summary_parts)
                    ),
                    "activity_summary": " · ".join(summary_parts),
                    "content_counts": counts,
                    "has_content": has_content,
                    "is_empty": not has_content,
                }
            )
            items.append(item)
        return items

    def create(
        self,
        request: ResearchGoalRunRequest,
        *,
        title: str = "",
        project_id: str | None = None,
        egress_confirmed: bool = False,
    ) -> dict[str, Any]:
        if project_id:
            with self.repository.connect() as conn:
                if (
                    conn.execute(
                        "SELECT 1 FROM research_projects WHERE project_id=? AND archived_at=''",
                        (project_id,),
                    ).fetchone()
                    is None
                ):
                    raise KeyError(project_id)
        run = self.goal_runs.start(request, egress_confirmed=egress_confirmed)
        session_id = f"session:{monotonic_ulid()}"
        now = utc_now()
        with self.repository.connect() as conn:
            conn.execute(
                """
                INSERT INTO research_sessions(
                    session_id, project_id, title, active_run_id, state, revision,
                    graph_revision, source_ids_json, provider_profile_id, model,
                    archived_at, created_at, updated_at
                ) VALUES (?,?,?,?,?,1,0,?,?,?,'',?,?)
                """,
                (
                    session_id,
                    project_id,
                    title.strip() or self._title(request.goal),
                    run["run_id"],
                    "running" if run["state"] in _TERMINAL_RUN_STATES else run["state"],
                    json.dumps(request.source_ids),
                    request.provider_profile_id,
                    request.model,
                    now,
                    now,
                ),
            )
            conn.execute(
                "INSERT INTO research_session_runs VALUES (?,?,1,?)",
                (session_id, run["run_id"], now),
            )
            conn.execute(
                "INSERT INTO research_graph_state VALUES (?,?,?,0,?)",
                (session_id, json.dumps({}), "daylight", now),
            )
        job = self.repository.get_job(str(run.get("job_id") or ""))
        if job is not None:
            job.checkpoint = {**job.checkpoint, "session_id": session_id}
            self.repository.save_job(job)
        current_run = self.goal_runs.detail(str(run["run_id"])) or run
        if str(current_run.get("state") or "") in _TERMINAL_RUN_STATES:
            self.finalize_goal_run(str(run["run_id"]))
        return self.detail(session_id, synchronize=False) or {}

    def create_data_discovery_home(
        self,
        *,
        source_ids: list[str],
        title: str,
        provider_profile_id: str,
        model: str,
        force_new: bool = False,
    ) -> dict[str, Any]:
        """Resolve one canonical, graph-empty home for a dataset source set."""

        clean_title = self._title(title or "Data discovery")
        digest = self.source_set_digest(source_ids)
        with self.repository.connect() as conn:
            # Serialize source-set resolution and insertion across processes.
            # No reader can race between a successful lookup and this write.
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT session_id FROM research_sessions "
                "WHERE kind='data_discovery' AND source_set_digest=? "
                "AND archived_at='' AND canonical_session_id=session_id "
                "ORDER BY updated_at DESC, session_id DESC LIMIT 1",
                (digest,),
            ).fetchone()
            if existing is not None and not force_new:
                conn.commit()
                resolved = self.detail(str(existing[0]), synchronize=False) or {}
                resolved["created_project"] = False
                return resolved
            session_id = f"session:{monotonic_ulid()}"
            now = utc_now()
            conn.execute(
                """
                INSERT INTO research_sessions(
                    session_id, project_id, title, active_run_id, state, revision,
                    graph_revision, source_ids_json, provider_profile_id, model,
                    archived_at, created_at, updated_at,
                    kind, source_set_digest, summary, canonical_session_id
                ) VALUES (?,?,?,NULL,'queued',1,0,?,?,?,'',?,?,
                          'data_discovery',?,?,?)
                """,
                (
                    session_id,
                    None,
                    clean_title,
                    json.dumps(source_ids),
                    provider_profile_id,
                    model,
                    now,
                    now,
                    digest,
                    "",
                    session_id,
                ),
            )
            conn.execute(
                "INSERT INTO research_graph_state VALUES (?,?,?,0,?)",
                (session_id, json.dumps({}), "daylight", now),
            )
        created = self.detail(session_id, synchronize=False) or {}
        created["created_project"] = True
        return created

    def consolidate_data_sessions(self) -> dict[str, Any]:
        """Collapse duplicate data homes into aliases without deleting history."""

        now = utc_now()
        groups: dict[str, list[Any]] = {}
        with self.repository.connect() as conn:
            rows = conn.execute(
                """
                SELECT s.*,
                       (SELECT COUNT(*) FROM data_studies d WHERE d.session_id=s.session_id
                        AND d.state!='cancelled') AS retained_runs,
                       (SELECT COUNT(*) FROM data_findings f JOIN data_studies d
                        ON d.study_id=f.study_id WHERE d.session_id=s.session_id
                        AND f.status='supported_candidate') AS supported_findings
                FROM research_sessions s WHERE s.kind='data_discovery'
                AND NOT EXISTS (SELECT 1 FROM data_studies explicit_run
                    WHERE explicit_run.session_id=s.session_id
                    AND json_extract(explicit_run.request_json,'$.project_mode')='new')
                ORDER BY s.created_at, s.session_id
                """
            ).fetchall()
            for row in rows:
                try:
                    source_ids = [str(item) for item in json.loads(row["source_ids_json"] or "[]")]
                except (TypeError, ValueError, json.JSONDecodeError):
                    source_ids = []
                digest = self.source_set_digest(source_ids) if source_ids else str(row["source_set_digest"] or "")
                if digest:
                    groups.setdefault(digest, []).append(row)
                    if digest != str(row["source_set_digest"] or ""):
                        conn.execute(
                            "UPDATE research_sessions SET source_set_digest=? WHERE session_id=?",
                            (digest, str(row["session_id"])),
                        )

            # Aliases are a projection of the current canonical source-root
            # groups, not immutable run history. Rebuilding them prevents a
            # former canonical from retaining a stale reverse/self alias after
            # two legacy source-ID groups are merged by the v2 root identity.
            data_session_ids = [
                str(row["session_id"])
                for candidates in groups.values()
                for row in candidates
            ]
            if data_session_ids:
                placeholders = ",".join("?" for _ in data_session_ids)
                conn.execute(
                    f"DELETE FROM research_session_aliases "
                    f"WHERE alias_session_id IN ({placeholders})",
                    tuple(data_session_ids),
                )

            aliased = 0
            canonical_count = 0
            for digest, candidates in groups.items():
                canonical = max(
                    candidates,
                    key=lambda row: (
                        int(row["retained_runs"]),
                        int(row["supported_findings"]),
                        str(row["updated_at"]),
                        str(row["session_id"]),
                    ),
                )
                canonical_id = str(canonical["session_id"])
                canonical_count += 1
                conn.execute(
                    "UPDATE research_sessions SET canonical_session_id=? WHERE session_id=?",
                    (canonical_id, canonical_id),
                )
                for row in candidates:
                    alias_id = str(row["session_id"])
                    if alias_id == canonical_id:
                        continue
                    preferred = conn.execute(
                        "SELECT study_id FROM data_studies WHERE session_id=? "
                        "ORDER BY updated_at DESC, study_id DESC LIMIT 1",
                        (alias_id,),
                    ).fetchone()
                    conn.execute(
                        """
                        INSERT INTO research_session_aliases(
                            alias_session_id, canonical_session_id, preferred_study_id,
                            source_set_digest, reason, created_at
                        ) VALUES (?, ?, ?, ?, 'duplicate_source_set', ?)
                        ON CONFLICT(alias_session_id) DO UPDATE SET
                            canonical_session_id=excluded.canonical_session_id,
                            preferred_study_id=excluded.preferred_study_id,
                            source_set_digest=excluded.source_set_digest
                        """,
                        (
                            alias_id,
                            canonical_id,
                            str(preferred[0]) if preferred is not None else "",
                            digest,
                            now,
                        ),
                    )
                    conn.execute(
                        "UPDATE research_sessions SET canonical_session_id=? WHERE session_id=?",
                        (canonical_id, alias_id),
                    )
                    aliased += 1

                candidate_ids = [str(row["session_id"]) for row in candidates]
                placeholders = ",".join("?" for _ in candidate_ids)
                studies = conn.execute(
                    f"SELECT study_id, created_at, state, updated_at FROM data_studies "
                    f"WHERE session_id IN ({placeholders}) "
                    "ORDER BY created_at, study_id",
                    tuple(candidate_ids),
                ).fetchall()
                if studies:
                    study_ids = [str(study["study_id"]) for study in studies]
                    study_placeholders = ",".join("?" for _ in study_ids)
                    # Rebuild only this source set's immutable run links. The
                    # DataStudy rows and their original session URLs remain
                    # untouched; the canonical project owns the ordered history.
                    conn.execute(
                        f"DELETE FROM data_discovery_runs "
                        f"WHERE study_id IN ({study_placeholders})",
                        tuple(study_ids),
                    )
                    for sequence, study in enumerate(studies, start=1):
                        conn.execute(
                            "INSERT INTO data_discovery_runs "
                            "(session_id, study_id, sequence, created_at) VALUES (?, ?, ?, ?)",
                            (
                                canonical_id,
                                str(study["study_id"]),
                                sequence,
                                str(study["created_at"]),
                            ),
                        )
                    latest = max(
                        studies,
                        key=lambda study: (
                            str(study["updated_at"]), str(study["study_id"])
                        ),
                    )
                    conn.execute(
                        "UPDATE research_sessions SET state=? WHERE session_id=?",
                        (str(latest["state"]), canonical_id),
                    )
        return {
            "schema_version": "principia.data-project-consolidation/v1",
            "canonical_projects": canonical_count,
            "aliases": aliased,
            "source_sets": len(groups),
            "canonical_run_links": sum(
                len(candidates) for candidates in groups.values()
            ),
            "applied_at": now,
        }

    def start_run(
        self,
        session_id: str,
        request: ResearchGoalRunRequest,
        *,
        egress_confirmed: bool = False,
    ) -> dict[str, Any]:
        current = self.detail(session_id, synchronize=False)
        if current is None:
            raise KeyError(session_id)
        active = current.get("active_run") or {}
        if active and current.get("state") not in _TERMINAL_RUN_STATES:
            raise ValueError("the current research run is still active")
        run = self.goal_runs.start(request, egress_confirmed=egress_confirmed)
        now = utc_now()
        with self.repository.connect() as conn:
            sequence = int(
                conn.execute(
                    "SELECT COALESCE(MAX(sequence),0)+1 FROM research_session_runs WHERE session_id=?",
                    (session_id,),
                ).fetchone()[0]
            )
            conn.execute(
                "INSERT INTO research_session_runs VALUES (?,?,?,?)",
                (session_id, run["run_id"], sequence, now),
            )
            conn.execute(
                "UPDATE research_sessions SET active_run_id=?, state=?, source_ids_json=?, "
                "provider_profile_id=?, model=?, revision=revision+1, updated_at=? WHERE session_id=?",
                (
                    run["run_id"],
                    "running" if run["state"] in _TERMINAL_RUN_STATES else run["state"],
                    json.dumps(request.source_ids),
                    request.provider_profile_id,
                    request.model,
                    now,
                    session_id,
                ),
            )
        job = self.repository.get_job(str(run.get("job_id") or ""))
        if job is not None:
            job.checkpoint = {**job.checkpoint, "session_id": session_id}
            self.repository.save_job(job)
        current_run = self.goal_runs.detail(str(run["run_id"])) or run
        if str(current_run.get("state") or "") in _TERMINAL_RUN_STATES:
            self.finalize_goal_run(str(run["run_id"]))
        return self.detail(session_id, synchronize=False) or {}

    def update_session(
        self,
        session_id: str,
        *,
        title: str | None = None,
        project_id: str | None | object = ...,
        archived: bool | None = None,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        with self.repository.connect() as conn:
            row = conn.execute(
                "SELECT * FROM research_sessions WHERE session_id=?", (session_id,)
            ).fetchone()
            if row is None:
                raise KeyError(session_id)
            if expected_revision is not None and int(row["revision"]) != expected_revision:
                raise ValueError("session revision conflict; reload before saving")
            new_project = row["project_id"] if project_id is ... else project_id
            if (
                new_project
                and conn.execute(
                    "SELECT 1 FROM research_projects WHERE project_id=? AND archived_at=''",
                    (new_project,),
                ).fetchone()
                is None
            ):
                raise KeyError(str(new_project))
            conn.execute(
                "UPDATE research_sessions SET project_id=?, title=?, archived_at=?, "
                "revision=revision+1, updated_at=? WHERE session_id=?",
                (
                    new_project,
                    title.strip() if title is not None else row["title"],
                    now if archived is True else "" if archived is False else row["archived_at"],
                    now,
                    session_id,
                ),
            )
        return self.detail(session_id) or {}

    def delete_session(
        self, session_id: str, *, expected_revision: int | None = None
    ) -> dict[str, Any]:
        """Permanently delete a research session and its run/job storage.

        Deletion is deliberately unavailable while work is active.  Completed
        runs, graph state, result memberships, virtual artifacts, job events,
        and provider accounting are removed in one transaction so a deleted
        research does not continue accumulating in hidden archives.
        """
        with self.repository.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT title, state, revision FROM research_sessions WHERE session_id=?",
                (session_id,),
            ).fetchone()
            if row is None:
                raise KeyError(session_id)
            if expected_revision is not None and int(row["revision"]) != expected_revision:
                raise ValueError("session revision conflict; reload before deleting")
            if str(row["state"]) not in _TERMINAL_RUN_STATES | {"queued", "ready", "draft"}:
                raise ValueError("wait for the active research run to finish or cancel it first")
            session_ids = [str(item[0]) for item in conn.execute(
                "SELECT session_id FROM research_sessions WHERE session_id=? OR canonical_session_id=? "
                "OR session_id IN (SELECT alias_session_id FROM research_session_aliases WHERE canonical_session_id=?)",
                (session_id, session_id, session_id),
            ).fetchall()]
            session_placeholders = ",".join("?" for _ in session_ids)

            # ASD runs are separate from literature goal runs. They must be
            # checked and removed too; otherwise foreign keys reject deletion
            # or invisible studies continue occupying storage.
            study_rows = conn.execute(
                "SELECT d.study_id, d.job_id, d.state, j.state AS job_state "
                "FROM data_studies d LEFT JOIN v14_jobs j ON j.job_id=d.job_id "
                f"WHERE d.session_id IN ({session_placeholders})", tuple(session_ids),
            ).fetchall()
            if any(str(item["state"]) not in _TERMINAL_RUN_STATES | {"interrupted", "data_insufficient"}
                   or (item["job_state"] and str(item["job_state"]) not in _TERMINAL_RUN_STATES | {"interrupted"})
                   for item in study_rows):
                raise ValueError("wait for the active data discovery run to finish or cancel it first")
            study_ids = [str(item["study_id"]) for item in study_rows]
            # These names are schema constants, never user-provided SQL.
            for study_id in study_ids:
                for table in (
                    "scientific_law_evaluations", "scientific_law_calibrations",
                    "scientific_law_candidates", "scientific_decisions", "scientific_law_families",
                    "scientific_programs", "scientific_split_manifests", "scientific_transform_graphs",
                    "data_principle_links", "data_derived_principle_drafts", "data_evidence_links",
                    "data_tests", "data_hypotheses", "data_findings", "data_extra_principles",
                    "data_alignments", "data_views", "data_assets", "data_job_units",
                    "study_blueprints", "data_discovery_runs", "data_studies",
                ):
                    conn.execute(f"DELETE FROM {table} WHERE study_id=?", (study_id,))
            conn.execute(f"DELETE FROM research_session_aliases WHERE canonical_session_id=? OR alias_session_id IN ({session_placeholders})", (session_id, *session_ids))

            run_rows = conn.execute(
                f"""
                SELECT sr.run_id, gr.job_id, gr.state, j.state AS job_state
                FROM research_session_runs sr
                JOIN research_goal_runs gr ON gr.run_id=sr.run_id
                LEFT JOIN v14_jobs j ON j.job_id=gr.job_id
                WHERE sr.session_id IN ({session_placeholders})
                ORDER BY sr.sequence
                """,
                tuple(session_ids),
            ).fetchall()
            if any(str(item["state"]) not in _TERMINAL_RUN_STATES
                   or (item["job_state"] and str(item["job_state"]) not in _TERMINAL_RUN_STATES)
                   for item in run_rows):
                raise ValueError("wait for the active research run to finish or cancel it first")
            run_ids = [str(item["run_id"]) for item in run_rows]
            job_ids = list({str(item["job_id"]) for item in [*run_rows, *study_rows] if item["job_id"]})

            for table in (
                "research_artifacts",
                "research_graph_items",
                "research_graph_state",
                "research_session_results",
                "research_session_runs",
                "workspace_edges",
                "workspace_records",
                "data_discovery_runs",
            ):
                conn.execute(f"DELETE FROM {table} WHERE session_id IN ({session_placeholders})", tuple(session_ids))
            conn.execute(f"DELETE FROM research_sessions WHERE session_id IN ({session_placeholders})", tuple(session_ids))

            for run_id in run_ids:
                conn.execute("DELETE FROM research_goal_memberships WHERE run_id=?", (run_id,))
                conn.execute("DELETE FROM research_goal_runs WHERE run_id=?", (run_id,))

            # The coordinator job is owned by the deleted run.  Child branch
            # jobs remain independent because they may also own reusable local
            # extraction results.
            for job_id in job_ids:
                conn.execute("DELETE FROM provider_attempts WHERE job_id=?", (job_id,))
                conn.execute("DELETE FROM provider_usage WHERE job_id=?", (job_id,))
                conn.execute("DELETE FROM literature_search_attempts WHERE job_id=?", (job_id,))
                conn.execute("DELETE FROM literature_search_tasks WHERE job_id=?", (job_id,))
                conn.execute("DELETE FROM local_extraction_selections WHERE job_id=?", (job_id,))
                conn.execute("DELETE FROM v14_job_events WHERE job_id=?", (job_id,))
                conn.execute("DELETE FROM v14_job_units WHERE job_id=?", (job_id,))
                conn.execute("DELETE FROM v14_jobs WHERE job_id=?", (job_id,))

        cleanup_pending = 0
        for study_id in study_ids:
            if not re.fullmatch(r"study:[A-Za-z0-9_:-]+", study_id):
                cleanup_pending += 1
                continue
            for base in (self.artifacts_root / "data-discovery" if self.artifacts_root else None, self.outputs_root):
                if base is None:
                    continue
                target = base / study_id
                # Never follow a symlink into source data or another project.
                try:
                    safe_parent = self.repository.db_path.parent.resolve() if base.name == "data-discovery" else self.repository.db_path.parent.parent.parent.resolve()
                    if not base.resolve().is_relative_to(safe_parent):
                        cleanup_pending += 1
                        continue
                    if target.is_symlink():
                        target.unlink()
                    elif target.exists():
                        shutil.rmtree(target)
                except OSError:
                    cleanup_pending += 1

        from ..storage_maintenance import reclaim_deleted_pages

        space = reclaim_deleted_pages(self.repository.db_path)
        return {
            "deleted": True,
            "storage": space,
            "session_id": session_id,
            "title": str(row["title"]),
            "deleted_run_count": len(run_ids),
            "deleted_study_count": len(study_ids),
            "artifact_cleanup_pending": cleanup_pending,
        }

    def _copy_results(self, session_id: str, run: dict[str, Any]) -> None:
        run_id = str(run["run_id"])
        now = utc_now()
        pages: dict[str, list[dict[str, Any]]] = {}
        for membership in ("global", "local", "combined"):
            pages[membership] = self.goal_runs.results(run_id, membership, limit=200, offset=0)[
                "items"
            ]
        with self.repository.connect() as conn:
            for membership, items in pages.items():
                conn.execute(
                    "DELETE FROM research_session_results WHERE session_id=? AND run_id=? AND membership=?",
                    (session_id, run_id, membership),
                )
                for rank, item in enumerate(items):
                    item_id = str(
                        item.get("id")
                        or item.get("principle_id")
                        or item.get("candidate_id")
                        or rank
                    )
                    conn.execute(
                        "INSERT INTO research_session_results VALUES (?,?,?,?,?,?,?)",
                        (
                            session_id,
                            run_id,
                            membership,
                            item_id,
                            rank,
                            json.dumps(item, ensure_ascii=False, sort_keys=True),
                            now,
                        ),
                    )
        # Meta results are a separately typed tray, never silently mixed with
        # the ordinary top-five policy.  They are snapshotted against the same
        # release as soon as the session is synchronized.
        meta = self.global_cloud.search(
            CloudSearchRequest(entity="meta_principle", query=run["goal"], limit=100)
        )["items"]
        with self.repository.connect() as conn:
            conn.execute(
                "DELETE FROM research_session_results WHERE session_id=? AND run_id=? AND membership='meta'",
                (session_id, run_id),
            )
            for rank, item in enumerate(meta):
                conn.execute(
                    "INSERT INTO research_session_results VALUES (?,?,?,?,?,?,?)",
                    (
                        session_id,
                        run_id,
                        "meta",
                        str(item["id"]),
                        rank,
                        json.dumps(item, ensure_ascii=False, sort_keys=True),
                        now,
                    ),
                )
        self._seed_graph(session_id, run_id)

    def finalize_goal_run(self, run_id: str) -> None:
        """Atomically project a terminal goal run into every owning session.

        This is the only ordinary runtime path that snapshots memberships and
        seeds the initial graph.  It is invoked by the goal-run worker after
        durable terminal results are written.  The explicit migration-only
        synchronization flag in :meth:`detail` remains available for old
        workspaces, but API reads stay side-effect free.
        """

        run = self.goal_runs.detail(run_id)
        if run is None or str(run.get("state") or "") not in _TERMINAL_RUN_STATES:
            return
        with self.repository.connect() as conn:
            session_ids = [
                str(row[0])
                for row in conn.execute(
                    "SELECT session_id FROM research_session_runs WHERE run_id=? "
                    "ORDER BY session_id",
                    (run_id,),
                ).fetchall()
            ]
        for session_id in session_ids:
            self._copy_results(session_id, run)
            self._ensure_meta_graph_presence(session_id, run_id)
            with self.repository.connect() as conn:
                conn.execute(
                    "UPDATE research_sessions SET state=?, updated_at=? "
                    "WHERE session_id=? AND active_run_id=?",
                    (str(run["state"]), str(run["updated_at"]), session_id, run_id),
                )

    def _seed_graph(self, session_id: str, run_id: str) -> None:
        now = utc_now()
        with self.repository.connect() as conn:
            if int(
                conn.execute(
                    "SELECT COUNT(*) FROM research_graph_items "
                    "WHERE session_id=? AND record_kind='ordinary'",
                    (session_id,),
                ).fetchone()[0]
            ):
                return
            ordinary_rows = conn.execute(
                "SELECT payload_json FROM research_session_results WHERE session_id=? AND run_id=? "
                "AND membership='global' ORDER BY rank LIMIT 5",
                (session_id, run_id),
            ).fetchall()
            meta_rows = conn.execute(
                "SELECT payload_json FROM research_session_results WHERE session_id=? AND run_id=? "
                "AND membership='meta' ORDER BY rank LIMIT 3",
                (session_id, run_id),
            ).fetchall()
        ordinary = [json.loads(row[0]) for row in ordinary_rows]
        relevant_meta = [json.loads(row[0]) for row in meta_rows]
        if not ordinary:
            return
        additions: list[tuple[dict[str, Any], str, str]] = []
        for item in ordinary:
            detail = self.global_cloud.principle(str(item["id"])) or item
            additions.append((detail, "ordinary", "initial_top_five"))
            foundation = self.global_cloud.foundations(str(item["id"])) or {}
            for linked in foundation.get("foundations") or []:
                meta = linked.get("meta_principle") or {}
                if meta and str(meta.get("status") or "active") == "active":
                    additions.append((meta, "meta_principle", "linked_foundation"))
        # The map always presents both scientific layers. Relevant Meta roots
        # can provide conceptual context without asserting a FoundationLink;
        # only validated links returned above are rendered as foundation edges.
        for item in relevant_meta:
            detail = self.global_cloud.principle(str(item["id"])) or item
            additions.append((detail, "meta_principle", "relevant_meta"))
        unique: dict[str, tuple[dict[str, Any], str, str]] = {}
        for payload, kind, origin in additions:
            identifier = str(payload.get("principle_id") or payload.get("id") or "")
            if identifier:
                unique.setdefault(identifier, (payload, kind, origin))
        kind_indexes: dict[str, int] = {}
        with self.repository.connect() as conn:
            for index, (identifier, (payload, kind, origin)) in enumerate(unique.items()):
                kind_index = kind_indexes.get(kind, 0)
                kind_indexes[kind] = kind_index + 1
                if kind == "ordinary" and kind_index == 0:
                    x, y = 0.0, 0.0
                else:
                    # Golden-angle shells resemble an organic neural field and
                    # avoid the rigid line/ring layout used by early dev builds.
                    shell_index = kind_index if kind != "ordinary" else kind_index - 1
                    angle = (shell_index * 2.399963229728653) + (
                        0.72 if kind != "ordinary" else -0.32
                    )
                    base_radius = 225.0 if kind == "ordinary" else 340.0
                    radius = base_radius + math.sqrt(max(0, shell_index)) * (
                        48.0 if kind == "ordinary" else 42.0
                    )
                    x, y = math.cos(angle) * radius, math.sin(angle) * radius
                conn.execute(
                    """
                    INSERT OR IGNORE INTO research_graph_items(
                        session_id, principle_id, record_kind, origin, visible,
                        x, y, position_source, z_index, payload_json, updated_at
                    ) VALUES (?,?,?,?,1,?,?,?, ?,?,?)
                    """,
                    (
                        session_id,
                        identifier,
                        kind,
                        origin,
                        x,
                        y,
                        "initial_layout_v2",
                        index,
                        json.dumps(payload, ensure_ascii=False, sort_keys=True),
                        now,
                    ),
                )
            if unique:
                conn.execute(
                    "UPDATE research_sessions SET graph_revision=graph_revision+1, updated_at=? "
                    "WHERE session_id=?",
                    (now, session_id),
                )

    def _ensure_meta_graph_presence(self, session_id: str, run_id: str) -> None:
        """One-time migration for sessions seeded before Meta coexistence.

        A user's explicit removal remains respected because a hidden Meta row
        still counts as present. Only sessions that never had a Meta graph item
        receive the three strongest semantically relevant roots.
        """

        now = utc_now()
        with self.repository.connect() as conn:
            if int(
                conn.execute(
                    "SELECT COUNT(*) FROM research_graph_items "
                    "WHERE session_id=? AND record_kind='meta_principle'",
                    (session_id,),
                ).fetchone()[0]
            ):
                return
            rows = conn.execute(
                "SELECT payload_json FROM research_session_results WHERE session_id=? AND run_id=? "
                "AND membership='meta' ORDER BY rank LIMIT 3",
                (session_id, run_id),
            ).fetchall()
            if not rows:
                return
            top_z = int(
                conn.execute(
                    "SELECT COALESCE(MAX(z_index),-1) FROM research_graph_items WHERE session_id=?",
                    (session_id,),
                ).fetchone()[0]
            )
            inserted = 0
            for index, row in enumerate(rows):
                result = json.loads(row[0])
                identifier = str(result.get("principle_id") or result.get("id") or "")
                if not identifier:
                    continue
                payload = self.global_cloud.principle(identifier) or result
                angle = (index * 2.399963229728653) + 0.72
                radius = 340.0 + math.sqrt(index) * 42.0
                conn.execute(
                    """
                    INSERT OR IGNORE INTO research_graph_items(
                        session_id, principle_id, record_kind, origin, visible,
                        x, y, position_source, z_index, payload_json, updated_at
                    ) VALUES (?,?,?,'relevant_meta',1,?,?,'initial_layout_v3',?,?,?)
                    """,
                    (
                        session_id,
                        identifier,
                        "meta_principle",
                        math.cos(angle) * radius,
                        math.sin(angle) * radius,
                        top_z + index + 1,
                        json.dumps(payload, ensure_ascii=False, sort_keys=True),
                        now,
                    ),
                )
                inserted += 1
            if inserted:
                conn.execute(
                    "UPDATE research_sessions SET graph_revision=graph_revision+1, updated_at=? "
                    "WHERE session_id=?",
                    (now, session_id),
                )

    def detail(
        self,
        session_id: str,
        *,
        synchronize: bool = False,
        _alias_chain: frozenset[str] | None = None,
    ) -> dict[str, Any] | None:
        """Return a session projection without repairing or reseeding stored state.

        ``synchronize=True`` is retained solely for explicit migration tooling;
        API reads and ordinary application calls are deliberately read-only.
        """
        with self.repository.connect() as conn:
            alias = conn.execute(
                "SELECT canonical_session_id, preferred_study_id FROM research_session_aliases "
                "WHERE alias_session_id=?",
                (session_id,),
            ).fetchone()
        if alias is not None:
            canonical_id = str(alias["canonical_session_id"])
            seen = _alias_chain or frozenset()
            if canonical_id == session_id or canonical_id in seen:
                alias = None
            else:
                resolved = self.detail(
                    canonical_id,
                    synchronize=synchronize,
                    _alias_chain=seen | {session_id},
                )
                if resolved is not None:
                    resolved.update(
                        {
                            "requested_session_id": session_id,
                            "canonical_session_id": canonical_id,
                            "redirect_session_id": canonical_id,
                            "preferred_study_id": str(alias["preferred_study_id"] or ""),
                            "is_alias": True,
                        }
                    )
                return resolved
        with self.repository.connect() as conn:
            row = conn.execute(
                "SELECT * FROM research_sessions WHERE session_id=?", (session_id,)
            ).fetchone()
            run_rows = conn.execute(
                "SELECT run_id, sequence, created_at FROM research_session_runs "
                "WHERE session_id=? ORDER BY sequence DESC",
                (session_id,),
            ).fetchall()
        if row is None:
            return None
        item = self._decode(row)
        active = self.goal_runs.detail(item["active_run_id"]) if item["active_run_id"] else None
        if active:
            # A terminal run is not visible as terminal in its owning session
            # until the write-side projector has committed memberships, graph
            # items, and the session state.  This prevents readers from seeing
            # a succeeded shell whose durable Results or graph is still empty.
            if str(active["state"]) not in _TERMINAL_RUN_STATES:
                item["state"] = active["state"]
            if synchronize:
                with self.repository.connect() as conn:
                    goal_counts = {
                        str(value["membership"]): int(value["count"])
                        for value in conn.execute(
                            "SELECT membership, COUNT(*) count FROM research_goal_memberships "
                            "WHERE run_id=? GROUP BY membership",
                            (active["run_id"],),
                        )
                    }
                    session_counts = {
                        str(value["membership"]): int(value["count"])
                        for value in conn.execute(
                            "SELECT membership, COUNT(*) count FROM research_session_results "
                            "WHERE session_id=? AND run_id=? GROUP BY membership",
                            (session_id, active["run_id"]),
                        )
                    }
                    stored_meta_rows = conn.execute(
                        "SELECT payload_json FROM research_session_results "
                        "WHERE session_id=? AND run_id=? AND membership='meta' LIMIT 200",
                        (session_id, active["run_id"]),
                    ).fetchall()
                memberships_changed = any(
                    goal_counts.get(name, 0) != session_counts.get(name, 0)
                    for name in ("global", "local", "combined")
                )
                invalid_meta_membership = any(
                    str(json.loads(value[0]).get("principle_class") or "literature") != "meta"
                    for value in stored_meta_rows
                )
                if memberships_changed or "meta" not in session_counts or invalid_meta_membership:
                    self._copy_results(session_id, active)
                self._ensure_meta_graph_presence(session_id, str(active["run_id"]))
            if synchronize and str(row["state"]) != str(active["state"]):
                with self.repository.connect() as conn:
                    conn.execute(
                        "UPDATE research_sessions SET state=?, updated_at=? WHERE session_id=?",
                        (active["state"], active["updated_at"], session_id),
                    )
        item["active_run"] = active
        item["runs"] = [dict(value) for value in run_rows]
        item["data_runs"] = self.repository.data_discovery_runs(session_id)
        data_study = max(item["data_runs"], key=lambda run: run["sequence"], default=None)
        item["active_data_study"] = data_study
        if data_study is not None and not active:
            item["state"] = str(data_study["state"])
        return item

    def results(
        self,
        session_id: str,
        membership: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        if membership not in {"global", "local", "combined", "meta"}:
            raise ValueError("membership must be global, local, combined, or meta")
        session = self.detail(session_id, synchronize=False)
        if session is None:
            raise KeyError(session_id)
        run_id = session["active_run_id"]
        with self.repository.connect() as conn:
            total = int(
                conn.execute(
                    "SELECT COUNT(*) FROM research_session_results WHERE session_id=? AND run_id=? AND membership=?",
                    (session_id, run_id, membership),
                ).fetchone()[0]
            )
            rows = conn.execute(
                "SELECT payload_json FROM research_session_results WHERE session_id=? AND run_id=? "
                "AND membership=? ORDER BY rank LIMIT ? OFFSET ?",
                (session_id, run_id, membership, max(1, min(limit, 200)), max(0, offset)),
            ).fetchall()
        return {"items": [json.loads(row[0]) for row in rows], "total": total}

    def graph(self, session_id: str, *, session: dict[str, Any] | None = None, include_hidden: bool = False) -> dict[str, Any]:
        session = session or self.detail(session_id, synchronize=False)
        if session is None:
            raise KeyError(session_id)
        session_id = str(session.get("canonical_session_id") or session.get("session_id") or session_id)
        with self.repository.connect() as conn:
            state = conn.execute(
                "SELECT * FROM research_graph_state WHERE session_id=?", (session_id,)
            ).fetchone()
            rows = conn.execute(
                "SELECT * FROM research_graph_items WHERE session_id=? "
                "AND (visible=1 OR ?=1) ORDER BY z_index, principle_id",
                (session_id, int(include_hidden)),
            ).fetchall()
        items = [
            {
                "principle_id": row["principle_id"],
                **({"visible": bool(row["visible"])} if include_hidden else {}),
                "record_kind": row["record_kind"],
                "origin": row["origin"],
                "x": float(row["x"]),
                "y": float(row["y"]),
                "position_source": row["position_source"],
                "z_index": int(row["z_index"]),
                "payload": json.loads(row["payload_json"]),
            }
            for row in rows
        ]
        # v1.4.1-dev sessions created before the graph redesign stored the
        # first five nodes on one horizontal line. Keep user-dragged positions,
        # but present those legacy seed nodes in a stable neural-field layout.
        # This response-level migration is deterministic and does not turn a
        # read into a database mutation.
        legacy_groups = {
            kind: [
                item
                for item in items
                if item["position_source"] == "initial_rank" and item["record_kind"] == kind
            ]
            for kind in {str(item["record_kind"]) for item in items}
        }
        has_nonlegacy = any(item["position_source"] != "initial_rank" for item in items)
        for kind, candidates in legacy_groups.items():
            count = len(candidates)
            if not count:
                continue
            for index, item in enumerate(candidates):
                if kind == "ordinary" and index == 0 and not has_nonlegacy:
                    x, y = 0.0, 0.0
                else:
                    shell_index = index if kind != "ordinary" else max(0, index - 1)
                    angle = (shell_index * 2.399963229728653) + (
                        0.72 if kind != "ordinary" else -0.32
                    )
                    radius = (225.0 if kind == "ordinary" else 340.0) + math.sqrt(shell_index) * (
                        48.0 if kind == "ordinary" else 42.0
                    )
                    x, y = math.cos(angle) * radius, math.sin(angle) * radius
                item["x"] = x
                item["y"] = y
                item["position_source"] = "initial_layout_v3"
        return {
            "session_id": session_id,
            "revision": int(state["revision"]) if state else 0,
            "theme": str(state["theme"]) if state else "daylight",
            "viewport": json.loads(state["viewport_json"] or "{}") if state else {},
            "items": items,
            "edges": self._graph_cloud_edges(
                [str(item["principle_id"]) for item in items]
            ),
        }

    def _graph_cloud_edges(self, identifiers: list[str]) -> list[dict[str, Any]]:
        try:
            return self.global_cloud.principle_edges(identifiers)
        except FileNotFoundError:
            # Local maps and saved evidence remain usable before Cloud setup.
            return []

    def workspace_graph(
        self, session_id: str, projection: dict[str, Any], *, session: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Compose immutable run evidence with explicit user context and layout.

        This is a read-only projection. Hiding evidence on the map never removes
        it from Results, and context added by the user is never a new finding.
        """
        saved = self.graph(session_id, session=session, include_hidden=True)
        overlays = {item["principle_id"]: item for item in saved["items"]}
        records = list(projection.get("records", []))
        canonical_ids = {item["record_id"] for item in records}
        for item in saved["items"]:
            origin = str(item["origin"])
            if (item["principle_id"] in canonical_ids or not item["visible"]
                    or not item["payload"]
                    or not (origin in {"add_global", "virtual_principle"} or origin.startswith("foundation:"))):
                continue
            records.append({
                "record_id": item["principle_id"],
                "record_kind": "meta_principle" if item["record_kind"] == "meta_principle" else "principle",
                "category": "global_principles",
                "origin": "user_added",
                "payload": {**item["payload"], "workspace_origin": "user_added"},
            })
        items = []
        for index, item in enumerate(records):
            identifier = item["record_id"]
            overlay = overlays.get(identifier, {})
            # Results retains the complete scientific audit in its expandable
            # limitations section. The default map should not turn rejected or
            # unfinished candidates into discovery nodes merely because they
            # have durable evidence records.
            if (item["record_kind"] == "discovery_finding"
                    and str(item.get("payload", {}).get("status") or "")
                    in {"held_back", "inconclusive", "refuted"}):
                continue
            if overlay.get("visible") is False:
                continue
            positioned = overlay.get("position_source") != "canonical_projection" and bool(overlay)
            items.append({
                "principle_id": identifier,
                "record_kind": "ordinary" if item["record_kind"] == "principle" else item["record_kind"],
                "origin": ("data_discovery_explanation" if item["origin"] == "cloud_grounding" else
                           str(overlay.get("origin") or "add_global") if item["origin"] == "user_added" else item["origin"]),
                "x": overlay["x"] if positioned else math.cos(index * 2.399963) * (180 + 45 * math.sqrt(index)),
                "y": overlay["y"] if positioned else math.sin(index * 2.399963) * (180 + 45 * math.sqrt(index)),
                "position_source": overlay.get("position_source", "canonical_projection"),
                "z_index": index,
                "payload": item["payload"],
            })
        record_ids = {item["record_id"] for item in records}
        edges = list(projection.get("edges", []))
        edge_ids = {item["edge_id"] for item in edges}
        for edge in self._graph_cloud_edges(sorted(record_ids)):
            edge = {**edge, "source_id": edge.get("source_id") or edge.get("source_principle_id") or edge.get("source"),
                    "target_id": edge.get("target_id") or edge.get("target_principle_id") or edge.get("target")}
            if edge.get("edge_id") not in edge_ids:
                edges.append(edge)
                edge_ids.add(edge.get("edge_id"))
        visible_ids = {item["principle_id"] for item in items}
        graph_edges = [edge for edge in edges if
                       str(edge.get("source_id") or edge.get("source")) in visible_ids and
                       str(edge.get("target_id") or edge.get("target")) in visible_ids]
        counts: dict[str, int] = {}
        for item in records:
            counts[item["category"]] = counts.get(item["category"], 0) + 1
        return ({**projection, "records": records, "edges": edges, "counts": counts},
                {**saved, "items": items, "edges": graph_edges})

    def mutate_graph(
        self, session_id: str, operations: list[dict[str, Any]], *, expected_revision: int
    ) -> dict[str, Any]:
        session = self.detail(session_id, synchronize=False)
        if session is None:
            raise KeyError(session_id)
        session_id = str(session.get("canonical_session_id") or session.get("session_id") or session_id)
        now = utc_now()
        outcomes: list[dict[str, Any]] = []
        with self.repository.connect() as conn:
            # Serialize the revision check and write across browser tabs.
            conn.execute("BEGIN IMMEDIATE")
            state = conn.execute(
                "SELECT * FROM research_graph_state WHERE session_id=?", (session_id,)
            ).fetchone()
            if state is None:
                raise KeyError(session_id)
            if int(state["revision"]) != expected_revision:
                raise ValueError("graph revision conflict; reload before saving")
            viewport = json.loads(state["viewport_json"] or "{}")
            theme = str(state["theme"])
            for operation in operations:
                action = str(operation.get("action") or "")
                identifier = str(operation.get("principle_id") or "")
                if action == "add":
                    existing = conn.execute(
                        "SELECT 1 FROM research_graph_items WHERE session_id=? AND principle_id=?",
                        (session_id, identifier),
                    ).fetchone()
                    try:
                        payload = self.global_cloud.principle(identifier)
                    except FileNotFoundError:
                        payload = None
                    if payload is None:
                        payload = dict(operation.get("payload") or {})
                    if not payload:
                        raise KeyError(identifier)
                    x = float(operation.get("x") or 0)
                    y = float(operation.get("y") or 0)
                    if not identifier or not math.isfinite(x) or not math.isfinite(y):
                        raise ValueError("a node identifier and finite coordinates are required")
                    conn.execute(
                        """
                        INSERT INTO research_graph_items(
                            session_id, principle_id, record_kind, origin, visible, x, y,
                            position_source, z_index, payload_json, updated_at
                        ) VALUES (?,?,?,?,1,?,?,?,0,?,?)
                        ON CONFLICT(session_id, principle_id) DO UPDATE SET visible=1,
                            x=excluded.x, y=excluded.y, position_source='user',
                            origin=excluded.origin, record_kind=excluded.record_kind,
                            payload_json=excluded.payload_json, updated_at=excluded.updated_at
                        """,
                        (
                            session_id,
                            identifier,
                            "meta_principle"
                            if payload.get("principle_class") == "meta"
                            else "ordinary",
                            str(operation.get("origin") or "add_global"),
                            x,
                            y,
                            "user",
                            json.dumps(payload, ensure_ascii=False, sort_keys=True),
                            now,
                        ),
                    )
                    outcomes.append({"principle_id": identifier, "already_present": bool(existing)})
                elif action in {"remove", "move"}:
                    if not identifier:
                        raise ValueError("a graph node identifier is required")
                    # Canonical discovery nodes need not have a saved graph row.
                    # Persist an overlay instead of silently updating zero rows.
                    if action == "remove":
                        conn.execute(
                            """INSERT INTO research_graph_items(
                                session_id, principle_id, record_kind, origin, visible,
                                x, y, position_source, z_index, payload_json, updated_at
                            ) VALUES (?,?,'ordinary','user_layout',0,0,0,'canonical_projection',0,'{}',?)
                            ON CONFLICT(session_id, principle_id) DO UPDATE
                                SET visible=0, updated_at=excluded.updated_at""",
                            (session_id, identifier, now),
                        )
                    else:
                        x, y = float(operation["x"]), float(operation["y"])
                        if not math.isfinite(x) or not math.isfinite(y):
                            raise ValueError("graph coordinates must be finite")
                        conn.execute(
                            """INSERT INTO research_graph_items(
                                session_id, principle_id, record_kind, origin, visible,
                                x, y, position_source, z_index, payload_json, updated_at
                            ) VALUES (?,?,'ordinary','user_layout',1,?,?,'user',0,'{}',?)
                            ON CONFLICT(session_id, principle_id) DO UPDATE
                                SET x=excluded.x, y=excluded.y, position_source='user',
                                    updated_at=excluded.updated_at""",
                            (session_id, identifier, x, y, now),
                        )
                elif action == "viewport":
                    viewport = dict(operation.get("viewport") or {})
                elif action == "theme":
                    requested_theme = str(operation.get("theme") or "daylight")
                    if requested_theme not in {"daylight", "deep-space"}:
                        raise ValueError("unknown graph theme")
                    theme = requested_theme
                else:
                    raise ValueError(f"unknown graph action: {action}")
            revision = expected_revision + 1
            conn.execute(
                "UPDATE research_graph_state SET viewport_json=?, theme=?, revision=?, updated_at=? "
                "WHERE session_id=?",
                (json.dumps(viewport, sort_keys=True), theme, revision, now, session_id),
            )
            conn.execute(
                "UPDATE research_sessions SET graph_revision=?, updated_at=? WHERE session_id=?",
                (revision, now, session_id),
            )
        return {"session_id": session_id, "revision": revision, "outcomes": outcomes}

    def artifacts(self, session_id: str) -> list[dict[str, Any]]:
        if self.detail(session_id, synchronize=False) is None:
            raise KeyError(session_id)
        with self.repository.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM research_artifacts WHERE session_id=? AND state!='deleted' "
                "ORDER BY updated_at DESC, artifact_id",
                (session_id,),
            ).fetchall()
        return [
            {
                "artifact_id": row["artifact_id"],
                "kind": row["kind"],
                "state": row["state"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def save_artifact(self, session_id: str, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        if kind not in {"virtual_principle", "virtual_connection"}:
            raise ValueError("unknown research artifact kind")
        if self.detail(session_id, synchronize=False) is None:
            raise KeyError(session_id)
        now = utc_now()
        artifact_id = f"artifact:{monotonic_ulid()}"
        with self.repository.connect() as conn:
            conn.execute(
                "INSERT INTO research_artifacts VALUES (?,?,?,?,?,?,?)",
                (
                    artifact_id,
                    session_id,
                    kind,
                    "active",
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    now,
                    now,
                ),
            )
        return next(
            item for item in self.artifacts(session_id) if item["artifact_id"] == artifact_id
        )

    def delete_artifact(self, session_id: str, artifact_id: str) -> dict[str, Any]:
        now = utc_now()
        with self.repository.connect() as conn:
            changed = conn.execute(
                "UPDATE research_artifacts SET state='deleted', updated_at=? "
                "WHERE session_id=? AND artifact_id=? AND state!='deleted'",
                (now, session_id, artifact_id),
            ).rowcount
        if not changed:
            raise KeyError(artifact_id)
        return {"artifact_id": artifact_id, "deleted": True}

    def delete_virtual_principle(
        self, session_id: str, virtual_id: str, *, candidate_id: str = ""
    ) -> dict[str, Any]:
        """Remove one generated hypothesis instead of its whole generation batch.

        A saved virtual Principle has two durable representations: the research
        artifact that explains how it was generated and, after the user saves
        it, a local Candidate Principle.  Deleting it must remove both views so
        that the drawer, graph, and local search cannot disagree about whether
        the hypothesis still exists.  The scientific mutation log remains
        intact through ``archive_candidate``.
        """

        if self.detail(session_id, synchronize=False) is None:
            raise KeyError(session_id)
        virtual_id = virtual_id.strip()
        candidate_id = candidate_id.strip()
        if not virtual_id and not candidate_id:
            raise ValueError("virtual_id or candidate_id is required")

        now = utc_now()
        removed_items = 0
        affected_sessions: set[str] = set()
        discovered_candidate_ids: set[str] = {candidate_id} if candidate_id else set()
        with self.repository.connect() as conn:
            artifact_rows = conn.execute(
                "SELECT artifact_id, session_id, payload_json FROM research_artifacts "
                "WHERE kind='virtual_principle' AND state!='deleted'"
            ).fetchall()
            for row in artifact_rows:
                payload = json.loads(row["payload_json"] or "{}")
                items = payload.get("items")
                if not isinstance(items, list):
                    continue
                retained: list[Any] = []
                changed = False
                for item in items:
                    value = item if isinstance(item, dict) else {}
                    item_virtual_id = str(value.get("virtual_id") or "")
                    item_candidate_id = str(value.get("candidate_id") or "")
                    matches = bool(virtual_id and item_virtual_id == virtual_id) or bool(
                        candidate_id and item_candidate_id == candidate_id
                    )
                    if not matches:
                        retained.append(item)
                        continue
                    changed = True
                    removed_items += 1
                    if item_candidate_id:
                        discovered_candidate_ids.add(item_candidate_id)
                if not changed:
                    continue
                affected_sessions.add(str(row["session_id"]))
                if retained:
                    payload["items"] = retained
                    conn.execute(
                        "UPDATE research_artifacts SET payload_json=?, updated_at=? "
                        "WHERE artifact_id=?",
                        (
                            json.dumps(payload, ensure_ascii=False, sort_keys=True),
                            now,
                            row["artifact_id"],
                        ),
                    )
                else:
                    conn.execute(
                        "UPDATE research_artifacts SET state='deleted', updated_at=? "
                        "WHERE artifact_id=?",
                        (now, row["artifact_id"]),
                    )

            for identifier in sorted(discovered_candidate_ids):
                graph_sessions = conn.execute(
                    "SELECT DISTINCT session_id FROM research_graph_items "
                    "WHERE principle_id=? AND visible=1",
                    (identifier,),
                ).fetchall()
                affected_sessions.update(str(row["session_id"]) for row in graph_sessions)
                conn.execute(
                    "UPDATE research_graph_items SET visible=0, updated_at=? WHERE principle_id=?",
                    (now, identifier),
                )

            for affected_session_id in sorted(affected_sessions):
                state = conn.execute(
                    "SELECT revision FROM research_graph_state WHERE session_id=?",
                    (affected_session_id,),
                ).fetchone()
                if state is None:
                    continue
                revision = int(state["revision"]) + 1
                conn.execute(
                    "UPDATE research_graph_state SET revision=?, updated_at=? WHERE session_id=?",
                    (revision, now, affected_session_id),
                )
                conn.execute(
                    "UPDATE research_sessions SET graph_revision=?, updated_at=? "
                    "WHERE session_id=?",
                    (revision, now, affected_session_id),
                )

        if not removed_items and not discovered_candidate_ids:
            raise KeyError(virtual_id)

        archived_candidates: list[str] = []
        for identifier in sorted(discovered_candidate_ids):
            try:
                self.repository.archive_candidate(identifier)
            except KeyError:
                continue
            archived_candidates.append(identifier)
        return {
            "virtual_id": virtual_id,
            "deleted": True,
            "removed_items": removed_items,
            "candidate_ids": archived_candidates,
        }
