from __future__ import annotations

import json
import math
from typing import Any

from ..cloud import CloudSearchRequest, ResearchGoalRunRequest
from ..domain import monotonic_ulid
from ..models import utc_now
from ..persistence import V14WorkspaceRepository

_TERMINAL_RUN_STATES = {"succeeded", "partial", "failed", "cancelled"}


class ResearchSessionService:
    """Durable, graph-first research sessions grouped into one-level projects.

    The goal-run coordinator remains responsible for scientific work.  This
    service gives every run a stable home, snapshots its result memberships,
    and owns the small, optimistic graph-editing contract used by the UI.
    """

    def __init__(
        self, repository: V14WorkspaceRepository, goal_runs: Any, global_cloud: Any
    ) -> None:
        self.repository = repository
        self.goal_runs = goal_runs
        self.global_cloud = global_cloud

    @staticmethod
    def _title(goal: str) -> str:
        compact = " ".join(goal.split())
        return compact if len(compact) <= 72 else compact[:69].rstrip() + "…"

    @staticmethod
    def _decode(row: Any) -> dict[str, Any]:
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
        }

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
        self, *, project_id: str | None = None, include_archived: bool = False
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        if not include_archived:
            clauses.append("archived_at='' ")
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
        return [self._decode(row) for row in rows]

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
                    run["state"],
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
                (session_id, json.dumps({"x": 0, "y": 0, "ratio": 1}), "daylight", now),
            )
        job = self.repository.get_job(str(run.get("job_id") or ""))
        if job is not None:
            job.checkpoint = {**job.checkpoint, "session_id": session_id}
            self.repository.save_job(job)
        return self.detail(session_id) or {}

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
        if active and active.get("state") not in _TERMINAL_RUN_STATES:
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
                    run["state"],
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
        return self.detail(session_id) or {}

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
            row = conn.execute(
                "SELECT title, state, revision FROM research_sessions WHERE session_id=?",
                (session_id,),
            ).fetchone()
            if row is None:
                raise KeyError(session_id)
            if expected_revision is not None and int(row["revision"]) != expected_revision:
                raise ValueError("session revision conflict; reload before deleting")
            if str(row["state"]) not in _TERMINAL_RUN_STATES:
                raise ValueError("wait for the active research run to finish or cancel it first")

            run_rows = conn.execute(
                """
                SELECT sr.run_id, gr.job_id
                FROM research_session_runs sr
                JOIN research_goal_runs gr ON gr.run_id=sr.run_id
                WHERE sr.session_id=?
                ORDER BY sr.sequence
                """,
                (session_id,),
            ).fetchall()
            run_ids = [str(item["run_id"]) for item in run_rows]
            job_ids = [str(item["job_id"]) for item in run_rows if item["job_id"]]

            for table in (
                "research_artifacts",
                "research_graph_items",
                "research_graph_state",
                "research_session_results",
                "research_session_runs",
            ):
                conn.execute(f"DELETE FROM {table} WHERE session_id=?", (session_id,))
            conn.execute("DELETE FROM research_sessions WHERE session_id=?", (session_id,))

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

        return {
            "deleted": True,
            "session_id": session_id,
            "title": str(row["title"]),
            "deleted_run_count": len(run_ids),
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

    def detail(self, session_id: str, *, synchronize: bool = True) -> dict[str, Any] | None:
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
            if str(row["state"]) != str(active["state"]):
                with self.repository.connect() as conn:
                    conn.execute(
                        "UPDATE research_sessions SET state=?, updated_at=? WHERE session_id=?",
                        (active["state"], active["updated_at"], session_id),
                    )
        item["active_run"] = active
        item["runs"] = [dict(value) for value in run_rows]
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
        session = self.detail(session_id)
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

    def graph(self, session_id: str) -> dict[str, Any]:
        session = self.detail(session_id)
        if session is None:
            raise KeyError(session_id)
        with self.repository.connect() as conn:
            state = conn.execute(
                "SELECT * FROM research_graph_state WHERE session_id=?", (session_id,)
            ).fetchone()
            rows = conn.execute(
                "SELECT * FROM research_graph_items WHERE session_id=? AND visible=1 "
                "ORDER BY z_index, principle_id",
                (session_id,),
            ).fetchall()
        items = [
            {
                "principle_id": row["principle_id"],
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
            "edges": self.global_cloud.principle_edges(
                [str(item["principle_id"]) for item in items]
            ),
        }

    def mutate_graph(
        self, session_id: str, operations: list[dict[str, Any]], *, expected_revision: int
    ) -> dict[str, Any]:
        now = utc_now()
        outcomes: list[dict[str, Any]] = []
        with self.repository.connect() as conn:
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
                    payload = self.global_cloud.principle(identifier)
                    if payload is None:
                        payload = dict(operation.get("payload") or {})
                    if not payload:
                        raise KeyError(identifier)
                    x = float(operation.get("x") or 0)
                    y = float(operation.get("y") or 0)
                    conn.execute(
                        """
                        INSERT INTO research_graph_items(
                            session_id, principle_id, record_kind, origin, visible, x, y,
                            position_source, z_index, payload_json, updated_at
                        ) VALUES (?,?,?,?,1,?,?,?,0,?,?)
                        ON CONFLICT(session_id, principle_id) DO UPDATE SET visible=1,
                            x=excluded.x, y=excluded.y, position_source='user', updated_at=excluded.updated_at
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
                elif action == "remove":
                    conn.execute(
                        "UPDATE research_graph_items SET visible=0, updated_at=? "
                        "WHERE session_id=? AND principle_id=?",
                        (now, session_id, identifier),
                    )
                elif action == "move":
                    conn.execute(
                        "UPDATE research_graph_items SET x=?, y=?, position_source='user', updated_at=? "
                        "WHERE session_id=? AND principle_id=?",
                        (
                            float(operation["x"]),
                            float(operation["y"]),
                            now,
                            session_id,
                            identifier,
                        ),
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
