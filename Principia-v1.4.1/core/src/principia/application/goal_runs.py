from __future__ import annotations

import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from ..cloud import CloudSearchRequest, GlobalCloudSnapshotStore, ResearchGoalRunRequest
from ..domain import JobRecord, LiteratureRunLimits, event_id, monotonic_ulid
from ..models import utc_now
from ..persistence import V14WorkspaceRepository


class ResearchGoalRunService:
    """Persisted coordinator for independent Global, Local, and online branches."""

    def __init__(
        self,
        repository: V14WorkspaceRepository,
        local: Any,
        global_cloud: GlobalCloudSnapshotStore,
    ) -> None:
        self.repository = repository
        self.local = local
        self.global_cloud = global_cloud
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="principia-goal")
        self._cancel: dict[str, threading.Event] = {}

    def start(self, request: ResearchGoalRunRequest, *, egress_confirmed: bool = False) -> dict[str, Any]:
        for source_id in request.source_ids:
            if self.repository.source(source_id) is None:
                raise KeyError(f"unknown Local source: {source_id}")
        if not request.include_global and not request.source_ids and not request.include_online:
            raise ValueError("select at least one research-goal branch")
        run_id = f"goalrun:{monotonic_ulid()}"
        job = JobRecord(
            job_id=f"job:{monotonic_ulid()}",
            kind="research_goal_run",
            state="queued",
            stage="Preparing branches",
            progress=0,
            provider=request.provider_profile_id,
            model=request.model,
            total_units=int(request.include_global) + len(request.source_ids) + int(request.include_online),
            checkpoint={"run_id": run_id, "request": request.model_dump(mode="json")},
            status_message="Preparing independent Global and Local branches",
        )
        branches: dict[str, Any] = {}
        if request.include_global:
            branches["global"] = {"state": "queued", "job_id": ""}
        for source_id in request.source_ids:
            branches[f"local:{source_id}"] = {"state": "queued", "job_id": "", "source_id": source_id}
        if request.include_online:
            branches["online"] = {"state": "awaiting_selection", "job_id": ""}
        self.repository.save_job(job)
        self._save_run(
            run_id,
            job.job_id,
            "queued",
            request,
            branches,
            {},
        )
        cancel = threading.Event()
        self._cancel[run_id] = cancel
        self._executor.submit(self._run, run_id, job.job_id, request, branches, cancel, egress_confirmed)
        return self.detail(run_id) or {}

    def _save_run(
        self,
        run_id: str,
        job_id: str,
        state: str,
        request: ResearchGoalRunRequest,
        branches: dict[str, Any],
        results: dict[str, Any],
    ) -> None:
        now = utc_now()
        status = self.global_cloud.status()
        with self.repository.connect() as conn:
            conn.execute(
                """
                INSERT INTO research_goal_runs(
                    run_id, job_id, state, goal, cloud_release_id, request_json,
                    branches_json, results_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET state=excluded.state,
                    branches_json=excluded.branches_json, results_json=excluded.results_json,
                    updated_at=excluded.updated_at
                """,
                (
                    run_id, job_id, state, request.goal, status.get("release_id") or "",
                    request.model_dump_json(), json.dumps(branches, sort_keys=True),
                    json.dumps(results, sort_keys=True), now, now,
                ),
            )

    def _persist_memberships(self, run_id: str, memberships: dict[str, list[dict[str, Any]]]) -> None:
        with self.repository.connect() as conn:
            conn.execute("DELETE FROM research_goal_memberships WHERE run_id=?", (run_id,))
            for membership, items in memberships.items():
                for item in items:
                    identifier = str(item.get("id") or item.get("candidate_id") or item.get("principle_id"))
                    digest = str(item.get("content_digest") or "")
                    if not digest:
                        digest = hashlib.sha256(
                            json.dumps(item, ensure_ascii=False, sort_keys=True).encode()
                        ).hexdigest()
                    conn.execute(
                        "INSERT INTO research_goal_memberships VALUES (?,?,?,?,?,?)",
                        (
                            run_id, membership, identifier, str(item.get("source") or membership),
                            digest, json.dumps(item, ensure_ascii=False, sort_keys=True),
                        ),
                    )

    def _run(
        self,
        run_id: str,
        job_id: str,
        request: ResearchGoalRunRequest,
        branches: dict[str, Any],
        cancel: threading.Event,
        egress_confirmed: bool,
    ) -> None:
        job = self.repository.get_job(job_id)
        if job is None:
            return
        job.state = "running"
        job.stage = "Running independent branches"
        job.status_message = "Global and Local branches are running independently"
        job.updated_at = utc_now()
        self.repository.save_job(job)
        started = time.monotonic()
        results: dict[str, Any] = {}

        def global_branch() -> dict[str, Any]:
            branches["global"]["state"] = "running"
            self._save_run(run_id, job_id, "running", request, branches, results)
            result = self.global_cloud.search(
                CloudSearchRequest(entity="principle", query=request.goal, limit=request.global_limit)
            )
            return {"items": result["items"], "ranking_mode": result["ranking_mode"]}

        def local_branch(source_id: str) -> dict[str, Any]:
            name = f"local:{source_id}"
            branches[name]["state"] = "running"
            self._save_run(run_id, job_id, "running", request, branches, results)
            source = self.repository.source(source_id)
            assert source is not None
            documents = self.repository.source_documents(
                source_id, limit=min(100, request.local_limit), extractable=True
            )["items"]
            if not documents:
                return {"items": [], "message": "No extractable documents in this source"}
            if not egress_confirmed:
                raise ValueError("Local LLM extraction requires explicit remote-egress confirmation")
            _, policy, api_key = self.local.provider_configuration(
                request.provider_profile_id, request.model, egress_confirmed=True
            )
            child = self.local.start_extraction(
                source_id=source_id,
                source_revision=int(source["revision"]),
                document_ids=[str(item["document_id"]) for item in documents],
                selection_mode="exact",
                goal=request.goal,
                area="",
                policy=policy,
                limits=LiteratureRunLimits(),
                api_key=api_key,
            )
            branches[name]["job_id"] = child.job_id
            while True:
                child = self.repository.get_job(child.job_id)
                if child is None or child.state in {"succeeded", "failed", "cancelled", "interrupted"}:
                    break
                if cancel.wait(0.2):
                    self.local.cancel(child.job_id)
                branches[name].update(
                    {"state": child.state, "stage": child.stage, "progress": child.progress}
                )
            if child is None or child.state != "succeeded":
                raise RuntimeError((child.error or {}).get("message") if child else "child job disappeared")
            ids = list((child.result or {}).get("candidate_ids") or [])
            items = [self.repository.candidate_detail(identifier) for identifier in ids]
            return {"items": [{**item, "id": item["candidate_id"], "source": "local"} for item in items if item]}

        futures: dict[Any, str] = {}
        with ThreadPoolExecutor(
            max_workers=max(1, min(4, int(request.include_global) + len(request.source_ids))),
            thread_name_prefix=f"principia-goal-{run_id[-6:]}",
        ) as pool:
            if request.include_global:
                futures[pool.submit(global_branch)] = "global"
            for source_id in request.source_ids:
                futures[pool.submit(local_branch, source_id)] = f"local:{source_id}"
            for future in as_completed(futures):
                name = futures[future]
                try:
                    results[name] = future.result()
                    branches[name]["state"] = "succeeded"
                except Exception as exc:
                    results[name] = {"items": [], "error": {"category": type(exc).__name__}}
                    branches[name]["state"] = "failed"
                job.completed_units += 1
                job.progress = job.completed_units / max(1, job.total_units)
                job.elapsed_seconds = round(time.monotonic() - started, 1)
                job.status_message = f"Completed {job.completed_units} of {job.total_units} branches"
                job.updated_at = utc_now()
                self.repository.save_job(job)
                self._save_run(run_id, job_id, "running", request, branches, results)
        if request.include_online:
            results["online"] = {
                "items": [],
                "state": "awaiting_selection",
                "message": "Start the existing online paper-selection flow before downloading.",
            }
            job.completed_units += 1
        global_items = list(results.get("global", {}).get("items") or [])
        local_items = [
            item
            for name, result in results.items()
            if name.startswith("local:")
            for item in result.get("items") or []
        ]
        global_by_digest = {str(item.get("content_digest") or ""): item for item in global_items if item.get("content_digest")}
        combined = [{**item, "source": "global"} for item in global_items]
        for item in local_items:
            digest = str(item.get("content_digest") or "")
            if digest and digest in global_by_digest:
                for existing in combined:
                    if str(existing.get("content_digest") or "") == digest:
                        existing["source"] = "both"
                        break
            else:
                combined.append(item)
        memberships = {"global": global_items, "local": local_items, "combined": combined}
        self._persist_memberships(run_id, memberships)
        failed = sum(1 for value in branches.values() if value["state"] == "failed")
        succeeded = sum(1 for value in branches.values() if value["state"] in {"succeeded", "awaiting_selection"})
        state = "cancelled" if cancel.is_set() else "partial" if failed and succeeded else "failed" if failed else "succeeded"
        job.state = "cancelled" if state == "cancelled" else "failed" if state == "failed" else "succeeded"
        job.stage = "Complete" if state in {"succeeded", "partial"} else state
        job.progress = 1
        job.result = {"run_id": run_id, "state": state, "counts": {key: len(value) for key, value in memberships.items()}}
        job.status_message = "Research-goal results are ready" if state != "failed" else "All branches failed"
        job.updated_at = utc_now()
        self.repository.save_job(job)
        self._save_run(run_id, job_id, state, request, branches, job.result)
        self.repository.append_job_event(job_id, "completed", job.result, event_id=event_id())

    def detail(self, run_id: str) -> dict[str, Any] | None:
        with self.repository.connect() as conn:
            row = conn.execute("SELECT * FROM research_goal_runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            return None
        return {
            "run_id": row["run_id"], "job_id": row["job_id"], "state": row["state"],
            "goal": row["goal"], "cloud_release_id": row["cloud_release_id"],
            "request": json.loads(row["request_json"]), "branches": json.loads(row["branches_json"]),
            "result": json.loads(row["results_json"]), "created_at": row["created_at"], "updated_at": row["updated_at"],
        }

    def results(self, run_id: str, membership: str, *, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        if membership not in {"global", "local", "combined"}:
            raise ValueError("membership must be global, local, or combined")
        with self.repository.connect() as conn:
            total = int(conn.execute(
                "SELECT COUNT(*) FROM research_goal_memberships WHERE run_id=? AND membership=?",
                (run_id, membership),
            ).fetchone()[0])
            rows = conn.execute(
                "SELECT payload_json FROM research_goal_memberships WHERE run_id=? AND membership=? "
                "ORDER BY rowid LIMIT ? OFFSET ?",
                (run_id, membership, max(1, min(limit, 200)), max(0, offset)),
            ).fetchall()
        return {"items": [json.loads(row[0]) for row in rows], "total": total}

    def cancel(self, run_id: str) -> dict[str, Any]:
        run = self.detail(run_id)
        if run is None:
            raise KeyError(run_id)
        event = self._cancel.get(run_id)
        if event:
            event.set()
        return {**run, "control_state": "cancelling"}

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
