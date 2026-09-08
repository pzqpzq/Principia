from __future__ import annotations

import json
import mimetypes
import os
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .config import ROOT_DIR, STATIC_DIR, get_settings
from .engine import PrincipiaEngine
from .llm_client import LLMClient
from .models import to_dict, utc_now
from .storage import Store
from .utils import lexical_score


def _json_bytes(data: object, status: int = 200) -> tuple[int, bytes, str]:
    return status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8"


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 10:
        return value[:2] + "..." + value[-2:]
    return value[:6] + "..." + value[-4:]


def _read_env_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def _write_env_values(updates: dict[str, str]) -> None:
    env_path = ROOT_DIR / ".env"
    lines = _read_env_lines(env_path)
    seen: set[str] = set()
    output: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            output.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in updates:
            output.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            output.append(line)
    for key, value in updates.items():
        if key not in seen:
            output.append(f"{key}={value}")
    env_path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    for key, value in updates.items():
        os.environ[key] = value


class PrincipiaRequestHandler(BaseHTTPRequestHandler):
    server_version = "Principia/1.0"
    work_extract_lock = threading.Lock()
    work_extract_queue: list[dict] = []
    work_extract_active = False

    @classmethod
    def _enqueue_work_extraction(cls, job: dict) -> int:
        with cls.work_extract_lock:
            cls.work_extract_queue.append(job)
            cls._refresh_work_extract_positions_locked()
            cls._start_next_work_extract_locked()
            return int((cls.store.get_item("research_runs", job["run_id"]) or {}).get("queue_position") or 0)

    @classmethod
    def _refresh_work_extract_positions_locked(cls) -> None:
        position = 0
        for job in cls.work_extract_queue:
            run = cls.store.get_item("research_runs", job.get("run_id", "")) or {}
            if run.get("status") != "queued":
                continue
            position += 1
            run.update({"queue_position": position, "updated_at": utc_now()})
            cls.store.upsert("research_runs", run, "run_id")

    @classmethod
    def _start_next_work_extract_locked(cls) -> None:
        if cls.work_extract_active:
            return
        while cls.work_extract_queue:
            job = cls.work_extract_queue.pop(0)
            run = cls.store.get_item("research_runs", job.get("run_id", "")) or {}
            if run.get("status") == "cancelled":
                continue
            cls.work_extract_active = True
            cls._refresh_work_extract_positions_locked()
            threading.Thread(target=cls._run_work_extract_job, args=(job,), name=f"principia-v1-work-{job.get('run_id', '')}", daemon=True).start()
            return
        cls._refresh_work_extract_positions_locked()

    @classmethod
    def _run_work_extract_job(cls, job: dict) -> None:
        run_id = str(job.get("run_id") or "")
        work_id = str(job.get("work_id") or "")
        try:
            run = cls.store.get_item("research_runs", run_id) or {"run_id": run_id}
            if run.get("status") == "cancelled":
                return
            run.update(
                {
                    "status": "running",
                    "stage": "work_extraction",
                    "message": "Extracting this work with the selected LLM.",
                    "queue_position": 0,
                    "updated_at": utc_now(),
                }
            )
            cls.store.upsert("research_runs", run, "run_id")
            result = cls.engine.v2_extract_single_work(
                work_id,
                field_id=str(job.get("field_id") or "default"),
                goal_text=str(job.get("goal_text") or ""),
                model_mode=str(job.get("model_mode") or "auto"),
                run_id=run_id,
                force=bool(job.get("force", False)),
            )
            if cls.engine._is_run_cancelled(run_id):
                return
            run = cls.store.get_item("research_runs", run_id) or {"run_id": run_id}
            run.update(
                {
                    "status": "complete",
                    "stage": "complete",
                    "message": "Work extraction complete.",
                    "result_work_id": work_id,
                    "result_counts": result.get("counts", {}),
                    "completed_at": utc_now(),
                    "updated_at": utc_now(),
                    "queue_position": 0,
                }
            )
            cls.store.upsert("research_runs", run, "run_id")
        except Exception as exc:
            run = cls.store.get_item("research_runs", run_id) or {"run_id": run_id}
            if run.get("status") != "cancelled":
                run.update({"status": "error", "stage": "error", "message": str(exc), "errors": [str(exc)], "updated_at": utc_now(), "queue_position": 0})
                cls.store.upsert("research_runs", run, "run_id")
        finally:
            with cls.work_extract_lock:
                cls.work_extract_active = False
                cls._start_next_work_extract_locked()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._handle_api_get(parsed.path, parse_qs(parsed.query))
            return
        self._serve_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            payload = self._read_json()
            if parsed.path.startswith("/api/v2/"):
                result = self._handle_v2_post(parsed.path, payload)
            elif parsed.path.startswith("/api/v1/"):
                result = self._handle_v1_post(parsed.path, payload)
            elif parsed.path == "/api/ingest":
                result = self.engine.ingest_principles(
                    str(payload.get("query", "")),
                    max_works=int(payload.get("max_works", 6)),
                    constraints=dict(payload.get("constraints") or {}),
                    offline=bool(payload.get("offline", False)),
                    model_mode=str(payload.get("model_mode", "auto")),
                )
            elif parsed.path == "/api/generate":
                progress_id = str(payload.get("progress_id") or "")
                if progress_id:
                    self.progress[progress_id] = {
                        "stage": "starting",
                        "found": 0,
                        "target": int(payload.get("paper_count", payload.get("max_works", 6))),
                        "message": "Starting generation.",
                        "updated_at": time.time(),
                    }

                def progress_callback(update: dict) -> None:
                    if progress_id:
                        self.progress[progress_id] = {**update, "updated_at": time.time()}

                result = self.engine.generate_ideas(
                    str(payload.get("query", "")),
                    max_ideas=int(payload.get("max_ideas", 4)),
                    max_works=int(payload.get("max_works", 6)),
                    paper_count=int(payload.get("paper_count", payload.get("max_works", 6))),
                    min_validation=str(payload.get("min_validation", "L0")),
                    constraints=dict(payload.get("constraints") or {}),
                    offline=bool(payload.get("offline", False)),
                    model_mode=str(payload.get("model_mode", "auto")),
                    source_mode=str(payload.get("source_mode", "online")),
                    persist_sources=bool(payload.get("persist_sources", True)),
                    progress_callback=progress_callback,
                    force_refresh=bool(payload.get("force_refresh", False)),
                    language=str(payload.get("language", "en")),
                    create_project=bool(payload.get("create_project", False)),
                    project_name=str(payload.get("project_name") or ""),
                )
                if progress_id:
                    self.progress[progress_id] = {
                        "stage": "complete",
                        "found": len(result.get("source_works", [])),
                        "target": int(payload.get("paper_count", payload.get("max_works", 6))),
                        "message": "Generation complete.",
                        "updated_at": time.time(),
                    }
            elif parsed.path == "/api/reset":
                self.store.reset()
                result = {"ok": True}
            elif parsed.path == "/api/item/update":
                result = self.store.update_item_flags(
                    str(payload.get("bucket", "")),
                    str(payload.get("id", "")),
                    highlighted=payload.get("highlighted"),
                    validated=payload.get("validated"),
                )
            elif parsed.path == "/api/item/delete":
                self.store.delete_item(str(payload.get("bucket", "")), str(payload.get("id", "")))
                result = {"ok": True}
            elif parsed.path == "/api/cleanup":
                result = self.store.prune_least_used(
                    max_works=int(payload.get("max_works", 500)),
                    max_principles=int(payload.get("max_principles", 1000)),
                    max_ideas=int(payload.get("max_ideas", 100)),
                )
            elif parsed.path == "/api/settings":
                updates: dict[str, str] = {}
                if "siliconflow_api_key" in payload:
                    updates["SILICONFLOW_API_KEY"] = str(payload.get("siliconflow_api_key") or "").strip()
                if "openai_api_key" in payload:
                    updates["OPENAI_API_KEY"] = str(payload.get("openai_api_key") or "").strip()
                if "siliconflow_base_url" in payload:
                    updates["PRINCIPIA_LLM_BASE_URL"] = str(payload.get("siliconflow_base_url") or "").strip()
                if "openai_base_url" in payload:
                    updates["PRINCIPIA_OPENAI_BASE_URL"] = str(payload.get("openai_base_url") or "").strip()
                if updates:
                    _write_env_values(updates)
                    self.engine.llm = LLMClient(get_settings())
                result = self._settings_payload()
            elif parsed.path == "/api/export":
                filename, body, content_type = self.engine.export_report(
                    str(payload.get("query", "")),
                    language=str(payload.get("language", "en")),
                    model_mode=str(payload.get("model_mode", "auto")),
                    fmt=str(payload.get("format", "markdown")),
                )
                self._send_bytes(body, content_type, filename)
                return
            elif parsed.path in {"/api/library/sync", "/api/library/extract_field"}:
                result = self.engine.sync_library_observatory(
                    field_id=str(payload.get("field_id") or "default"),
                    query=str(payload.get("query") or ""),
                    record_run=True,
                )
            elif parsed.path == "/api/library/project/create":
                result = self.engine.create_project(
                    name=str(payload.get("name") or "Untitled Project"),
                    query=str(payload.get("query") or ""),
                    description=str(payload.get("description") or ""),
                )
            elif parsed.path == "/api/library/project/update":
                result = self.engine.update_project(str(payload.get("field_id") or ""), payload)
            elif parsed.path == "/api/library/project/delete":
                result = self.engine.delete_project(
                    str(payload.get("field_id") or ""),
                    delete_orphan_records=bool(payload.get("delete_local_data") or payload.get("delete_orphan_records")),
                )
            elif parsed.path == "/api/library/extract_work":
                field_id = str(payload.get("field_id") or "default")
                work_id = str(payload.get("work_id") or payload.get("id") or "")
                work = self.store.get_item("source_works", work_id)
                if not work:
                    self._send_json({"error": "Work not found"}, HTTPStatus.NOT_FOUND)
                    return
                goal = self.engine._observatory_goal(str(payload.get("query") or ""))
                facts = self.engine.extract_work_facts(goal, work, field_id=field_id, persist=True)
                benchmarks = self.engine.extract_benchmark_records(goal, work, field_id=field_id, persist=True)
                result = {"work": work, "work_facts": facts, **benchmarks}
            elif parsed.path == "/api/library/feedback":
                result = self.engine.assimilate_feedback(
                    payload,
                    field_id=str(payload.get("field_id") or "default"),
                )
            elif parsed.path == "/api/library/assistant_export":
                result = self.engine.build_assistant_export_bundle(
                    str(payload.get("idea_id") or ""),
                    target_agent=str(payload.get("target_agent") or "codex"),
                    field_id=str(payload.get("field_id") or "default"),
                )
            else:
                self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return
            self._send_json(result)
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_v2_post(self, path: str, payload: dict) -> dict:
        if path == "/api/v2/llm/cancel":
            return self.engine.cancel_run(str(payload.get("run_id") or ""))
        if path == "/api/v2/research/start":
            field_id = str(payload.get("field_id") or "default")
            goal_text = str(payload.get("goal_text") or payload.get("query") or "")
            model_mode = str(payload.get("model_mode") or "auto")
            target_works = int(payload.get("target_works") or 100)
            run_id = f"VRUN-{int(time.time() * 1000)}"
            engine = self.engine
            store = self.store
            store.upsert(
                "research_runs",
                {
                    "run_id": run_id,
                    "field_id": field_id,
                    "type": "v2_research",
                    "status": "queued",
                    "stage": "queued",
                    "message": "Research queued.",
                    "goal_text": goal_text,
                    "model_mode": model_mode,
                    "target_works": target_works,
                    "counts": {},
                    "started_at": utc_now(),
                    "updated_at": utc_now(),
                },
                "run_id",
            )

            def worker() -> None:
                try:
                    engine.v2_research_project(
                        field_id,
                        goal_text=goal_text,
                        model_mode=model_mode,
                        target_works=target_works,
                        run_id=run_id,
                    )
                except Exception:
                    # v2_research_project records the failure in research_runs.
                    return

            thread = threading.Thread(target=worker, name=f"principia-v2-research-{run_id}", daemon=True)
            thread.start()
            return {"ok": True, "run_id": run_id}
        if path == "/api/v2/item/update":
            return self.engine.v2_item_update(payload)
        if path == "/api/v2/item/delete":
            return self.engine.v2_item_delete(payload)
        if path == "/api/v2/item/refresh/start":
            field_id = str(payload.get("field_id") or "default")
            bucket = str(payload.get("bucket") or "")
            record_id = str(payload.get("id") or payload.get("record_id") or "")
            model_mode = str(payload.get("model_mode") or "auto")
            run_id = f"VREFRUN-{int(time.time() * 1000)}"
            self.store.upsert(
                "research_runs",
                {
                    "run_id": run_id,
                    "field_id": field_id,
                    "type": "v2_item_refresh",
                    "status": "queued",
                    "stage": "queued",
                    "message": "Item refresh queued.",
                    "bucket": bucket,
                    "record_id": record_id,
                    "model_mode": model_mode,
                    "started_at": utc_now(),
                    "updated_at": utc_now(),
                    "counts": {},
                },
                "run_id",
            )

            def worker() -> None:
                try:
                    run = self.store.get_item("research_runs", run_id) or {"run_id": run_id}
                    run.update({"status": "running", "stage": "llm_refresh", "message": "Refreshing this item with the selected LLM.", "updated_at": utc_now()})
                    self.store.upsert("research_runs", run, "run_id")
                    result = self.engine.v2_item_refresh(payload, run_id=run_id)
                    if self.engine._is_run_cancelled(run_id):
                        return
                    item = result.get("item") or {}
                    run = self.store.get_item("research_runs", run_id) or run
                    run.update(
                        {
                            "status": "complete",
                            "stage": "complete",
                            "message": "Item refreshed.",
                            "result_bucket": item.get("bucket") or bucket,
                            "result_record_id": item.get("canonical_id") or item.get("principle_id") or item.get("benchmark_id") or item.get("baseline_id") or record_id,
                            "result_version_id": item.get("active_variant", {}).get("version_id", ""),
                            "completed_at": utc_now(),
                            "updated_at": utc_now(),
                        }
                    )
                    self.store.upsert("research_runs", run, "run_id")
                except Exception as exc:
                    run = self.store.get_item("research_runs", run_id) or {"run_id": run_id}
                    if run.get("status") == "cancelled":
                        return
                    run.update({"status": "error", "stage": "error", "message": str(exc), "errors": [str(exc)], "updated_at": utc_now()})
                    self.store.upsert("research_runs", run, "run_id")

            threading.Thread(target=worker, name=f"principia-v2-refresh-{run_id}", daemon=True).start()
            return {"ok": True, "run_id": run_id}
        if path == "/api/v2/item/refresh":
            return self.engine.v2_item_refresh(payload)
        if path == "/api/v2/my-idea/generate/start":
            field_id = str(payload.get("field_id") or "default")
            goal_text = str(payload.get("goal_text") or "")
            selected_refs = list(payload.get("selected_refs") or [])
            user_note = str(payload.get("user_note") or "")
            model_mode = str(payload.get("model_mode") or "auto")
            run_id = f"VIRUN-{int(time.time() * 1000)}"
            self.store.upsert(
                "research_runs",
                {
                    "run_id": run_id,
                    "field_id": field_id,
                    "type": "v2_my_idea_generate",
                    "status": "queued",
                    "stage": "queued",
                    "message": "Idea generation queued.",
                    "model_mode": model_mode,
                    "started_at": utc_now(),
                    "updated_at": utc_now(),
                    "counts": {},
                },
                "run_id",
            )

            def worker() -> None:
                try:
                    run = self.store.get_item("research_runs", run_id) or {"run_id": run_id}
                    run.update({"status": "running", "stage": "llm_generation", "message": "Calling the selected LLM to generate the idea.", "updated_at": utc_now()})
                    self.store.upsert("research_runs", run, "run_id")
                    result = self.engine.v2_generate_my_idea(
                        field_id=field_id,
                        goal_text=goal_text,
                        selected_refs=selected_refs,
                        user_note=user_note,
                        model_mode=model_mode,
                        run_id=run_id,
                    )
                    if self.engine._is_run_cancelled(run_id):
                        return
                    idea = result.get("idea") or {}
                    run = self.store.get_item("research_runs", run_id) or run
                    run.update(
                        {
                            "status": "complete",
                            "stage": "complete",
                            "message": "Idea generated.",
                            "result_idea_id": idea.get("idea_id"),
                            "result_version_id": idea.get("active_variant", {}).get("version_id", ""),
                            "completed_at": utc_now(),
                            "updated_at": utc_now(),
                        }
                    )
                    self.store.upsert("research_runs", run, "run_id")
                except Exception as exc:
                    run = self.store.get_item("research_runs", run_id) or {"run_id": run_id}
                    if run.get("status") == "cancelled":
                        return
                    run.update({"status": "error", "stage": "error", "message": str(exc), "errors": [str(exc)], "updated_at": utc_now()})
                    self.store.upsert("research_runs", run, "run_id")

            threading.Thread(target=worker, name=f"principia-v2-idea-{run_id}", daemon=True).start()
            return {"ok": True, "run_id": run_id}
        if path == "/api/v2/my-idea/regenerate/start":
            field_id = str(payload.get("field_id") or "default")
            idea_id = str(payload.get("idea_id") or "")
            model_mode = str(payload.get("model_mode") or "auto")
            version = str(payload.get("version") or "")
            run_id = f"VIRERUN-{int(time.time() * 1000)}"
            self.store.upsert(
                "research_runs",
                {
                    "run_id": run_id,
                    "field_id": field_id,
                    "type": "v2_my_idea_regenerate",
                    "status": "queued",
                    "stage": "queued",
                    "message": "Idea regeneration queued.",
                    "idea_id": idea_id,
                    "model_mode": model_mode,
                    "started_at": utc_now(),
                    "updated_at": utc_now(),
                    "counts": {},
                },
                "run_id",
            )

            def worker() -> None:
                try:
                    run = self.store.get_item("research_runs", run_id) or {"run_id": run_id}
                    run.update({"status": "running", "stage": "llm_regeneration", "message": "Calling the selected LLM to regenerate this idea version.", "updated_at": utc_now()})
                    self.store.upsert("research_runs", run, "run_id")
                    result = self.engine.v2_regenerate_my_idea(
                        field_id=field_id,
                        idea_id=idea_id,
                        model_mode=model_mode,
                        version=version,
                        run_id=run_id,
                    )
                    if self.engine._is_run_cancelled(run_id):
                        return
                    idea = result.get("idea") or {}
                    run = self.store.get_item("research_runs", run_id) or run
                    run.update(
                        {
                            "status": "complete",
                            "stage": "complete",
                            "message": f"Idea version {result.get('version_action', 'updated')}.",
                            "result_idea_id": idea.get("idea_id") or idea_id,
                            "result_version_id": idea.get("active_variant", {}).get("version_id", ""),
                            "version_action": result.get("version_action", ""),
                            "completed_at": utc_now(),
                            "updated_at": utc_now(),
                        }
                    )
                    self.store.upsert("research_runs", run, "run_id")
                except Exception as exc:
                    run = self.store.get_item("research_runs", run_id) or {"run_id": run_id}
                    if run.get("status") == "cancelled":
                        return
                    run.update({"status": "error", "stage": "error", "message": str(exc), "errors": [str(exc)], "updated_at": utc_now()})
                    self.store.upsert("research_runs", run, "run_id")

            threading.Thread(target=worker, name=f"principia-v2-idea-regen-{run_id}", daemon=True).start()
            return {"ok": True, "run_id": run_id}
        if path == "/api/v2/my-idea/generate":
            return self.engine.v2_generate_my_idea(
                field_id=str(payload.get("field_id") or "default"),
                goal_text=str(payload.get("goal_text") or ""),
                selected_refs=list(payload.get("selected_refs") or []),
                user_note=str(payload.get("user_note") or ""),
                model_mode=str(payload.get("model_mode") or "auto"),
            )
        raise ValueError(f"Unknown v2 endpoint: {path}")

    def _handle_v1_post(self, path: str, payload: dict) -> dict:
        if path == "/api/v1/research/start":
            field_id = str(payload.get("field_id") or "default")
            goal_text = str(payload.get("goal_text") or payload.get("query") or "")
            model_mode = str(payload.get("model_mode") or "auto")
            target_works = int(payload.get("target_works") or payload.get("paper_count") or 100)
            run_id = f"V1RUN-{int(time.time() * 1000)}"
            self.store.upsert(
                "research_runs",
                {
                    "run_id": run_id,
                    "field_id": field_id,
                    "type": "v1_research",
                    "status": "queued",
                    "stage": "queued",
                    "message": "Research queued.",
                    "goal_text": goal_text,
                    "model_mode": model_mode,
                    "target_works": target_works,
                    "counts": {},
                    "warnings": [],
                    "started_at": utc_now(),
                    "updated_at": utc_now(),
                },
                "run_id",
            )

            def worker() -> None:
                try:
                    self.engine.v1_research_project(
                        field_id,
                        goal_text=goal_text,
                        model_mode=model_mode,
                        target_works=target_works,
                        run_id=run_id,
                    )
                except Exception as exc:
                    run = self.store.get_item("research_runs", run_id) or {"run_id": run_id}
                    if run.get("status") == "cancelled":
                        return
                    run.update({"status": "error", "stage": "error", "message": str(exc), "errors": [str(exc)], "updated_at": utc_now()})
                    self.store.upsert("research_runs", run, "run_id")

            threading.Thread(target=worker, name=f"principia-v1-research-{run_id}", daemon=True).start()
            return {"ok": True, "run_id": run_id}
        if path == "/api/v1/research/cancel":
            return self.engine.cancel_run(str(payload.get("run_id") or ""))
        if path == "/api/v1/retrieve-concepts":
            return self.engine.v1_retrieve_concepts(
                str(payload.get("query") or payload.get("goal_text") or ""),
                field_id=str(payload.get("field_id") or "default"),
                concept_types=list(payload.get("concept_types") or []),
                limit_per_type=int(payload.get("limit_per_type") or 12),
            )
        if path == "/api/v1/item/update":
            return self.engine.v2_item_update(payload)
        if path == "/api/v1/item/refresh/start":
            payload = dict(payload)
            payload.setdefault("field_id", payload.get("field_id") or "default")
            return self._handle_v2_post("/api/v2/item/refresh/start", payload)
        if path == "/api/v1/work/extract/start":
            field_id = str(payload.get("field_id") or "default")
            work_id = str(payload.get("work_id") or payload.get("id") or "")
            goal_text = str(payload.get("goal_text") or "")
            model_mode = str(payload.get("model_mode") or "auto")
            force = bool(payload.get("force", False))
            existing = self.engine.v2_work_extraction_counts(work_id)
            has_core_coverage = (
                existing.get("existed_ideas", 0) > 0
                and existing.get("principles", 0) > 0
                and existing.get("takeaway_messages", 0) > 0
                and (existing.get("benchmark_records", 0) > 0 or existing.get("baseline_records", 0) > 0)
            )
            if has_core_coverage and not force:
                return {"ok": False, "already_extracted": True, "counts": existing}
            for run in self.store.list_items("research_runs", limit=100000):
                if (
                    run.get("type") == "v1_work_extract"
                    and run.get("work_id") == work_id
                    and run.get("field_id") == field_id
                    and run.get("status") in {"queued", "running"}
                ):
                    return {"ok": True, "run_id": run.get("run_id"), "counts": existing, "queued": run.get("status") == "queued", "status": run.get("status"), "queue_position": run.get("queue_position", 0)}
            run_id = f"V1WORK-{int(time.time() * 1000)}"
            self.store.upsert(
                "research_runs",
                {
                    "run_id": run_id,
                    "field_id": field_id,
                    "type": "v1_work_extract",
                    "status": "queued",
                    "stage": "queued",
                    "message": "Work extraction queued.",
                    "work_id": work_id,
                    "model_mode": model_mode,
                    "started_at": utc_now(),
                    "updated_at": utc_now(),
                    "counts": {},
                    "warnings": [],
                },
                "run_id",
            )
            queue_position = self.__class__._enqueue_work_extraction(
                {
                    "run_id": run_id,
                    "field_id": field_id,
                    "work_id": work_id,
                    "goal_text": goal_text,
                    "model_mode": model_mode,
                    "force": force,
                }
            )
            return {"ok": True, "run_id": run_id, "counts": existing, "queued": queue_position > 0, "queue_position": queue_position}
        if path == "/api/v1/ideas/standard-generate":
            return self.engine.v1_standard_generate(
                field_id=str(payload.get("field_id") or "default"),
                goal_text=str(payload.get("goal_text") or ""),
                selected_refs=list(payload.get("selected_refs") or []),
                user_note=str(payload.get("user_note") or ""),
                model_mode=str(payload.get("model_mode") or "auto"),
            )
        if path in {"/api/v1/ideas/standard-generate/start", "/api/v1/ideas/symbolic-generate/start"}:
            symbolic = path == "/api/v1/ideas/symbolic-generate/start"
            field_id = str(payload.get("field_id") or "default")
            goal_text = str(payload.get("goal_text") or "")
            selected_refs = list(payload.get("selected_refs") or [])
            user_note = str(payload.get("user_note") or "")
            model_mode = str(payload.get("model_mode") or "auto")
            offline = bool(payload.get("offline", False))
            run_id = f"V1IDEA-{int(time.time() * 1000)}"
            self.store.upsert(
                "research_runs",
                {
                    "run_id": run_id,
                    "field_id": field_id,
                    "type": "v1_symbolic_idea_generate" if symbolic else "v1_standard_idea_generate",
                    "status": "queued",
                    "stage": "queued",
                    "message": "Idea generation queued.",
                    "model_mode": model_mode,
                    "started_at": utc_now(),
                    "updated_at": utc_now(),
                    "counts": {},
                    "warnings": [],
                },
                "run_id",
            )

            def worker() -> None:
                try:
                    run = self.store.get_item("research_runs", run_id) or {"run_id": run_id}
                    run.update(
                        {
                            "status": "running",
                            "stage": "principia_calculus_patch" if symbolic else "collecting_evidence",
                            "message": "Preparing selected evidence for Principia Calculus." if symbolic else "Preparing selected evidence for standard generation.",
                            "updated_at": utc_now(),
                        }
                    )
                    self.store.upsert("research_runs", run, "run_id")
                    result = (
                        self.engine.v1_symbolic_generate(
                            field_id=field_id,
                            goal_text=goal_text,
                            selected_refs=selected_refs,
                            user_note=user_note,
                            model_mode=model_mode,
                            offline=offline,
                            run_id=run_id,
                        )
                        if symbolic
                        else self.engine.v1_standard_generate(
                            field_id=field_id,
                            goal_text=goal_text,
                            selected_refs=selected_refs,
                            user_note=user_note,
                            model_mode=model_mode,
                            run_id=run_id,
                        )
                    )
                    if self.engine._is_run_cancelled(run_id):
                        return
                    idea = result.get("idea") or {}
                    run = self.store.get_item("research_runs", run_id) or run
                    run.update(
                        {
                            "status": "complete",
                            "stage": "complete",
                            "message": "Idea generated.",
                            "result_idea_id": idea.get("idea_id"),
                            "result_version_id": idea.get("active_variant", {}).get("version_id", ""),
                            "result_derivation_id": result.get("derivation_id", ""),
                            "completed_at": utc_now(),
                            "updated_at": utc_now(),
                        }
                    )
                    self.store.upsert("research_runs", run, "run_id")
                except Exception as exc:
                    run = self.store.get_item("research_runs", run_id) or {"run_id": run_id}
                    if run.get("status") == "cancelled":
                        return
                    run.update({"status": "error", "stage": "error", "message": str(exc), "errors": [str(exc)], "updated_at": utc_now()})
                    self.store.upsert("research_runs", run, "run_id")

            threading.Thread(target=worker, name=f"principia-v1-idea-{run_id}", daemon=True).start()
            return {"ok": True, "run_id": run_id}
        if path == "/api/v1/ideas/symbolic-generate":
            return self.engine.v1_symbolic_generate(
                field_id=str(payload.get("field_id") or "default"),
                goal_text=str(payload.get("goal_text") or ""),
                selected_refs=list(payload.get("selected_refs") or []),
                user_note=str(payload.get("user_note") or ""),
                model_mode=str(payload.get("model_mode") or "auto"),
                offline=bool(payload.get("offline", False)),
            )
        if path == "/api/v1/ideas/related-comparison/start":
            field_id = str(payload.get("field_id") or "default")
            idea_id = str(payload.get("idea_id") or "")
            model_mode = str(payload.get("model_mode") or "auto")
            version = str(payload.get("version") or "")
            run_id = f"V1REL-{int(time.time() * 1000)}"
            self.store.upsert(
                "research_runs",
                {
                    "run_id": run_id,
                    "field_id": field_id,
                    "type": "v1_related_comparison_generate",
                    "status": "queued",
                    "stage": "queued",
                    "message": "Related-ideas comparison queued.",
                    "idea_id": idea_id,
                    "model_mode": model_mode,
                    "started_at": utc_now(),
                    "updated_at": utc_now(),
                    "counts": {},
                    "warnings": [],
                },
                "run_id",
            )

            def worker() -> None:
                try:
                    run = self.store.get_item("research_runs", run_id) or {"run_id": run_id}
                    run.update({"status": "running", "stage": "collecting_prior_ideas", "message": "Preparing related-ideas comparison.", "updated_at": utc_now()})
                    self.store.upsert("research_runs", run, "run_id")
                    result = self.engine.v2_generate_related_comparison(
                        field_id=field_id,
                        idea_id=idea_id,
                        model_mode=model_mode,
                        version=version,
                        run_id=run_id,
                    )
                    if self.engine._is_run_cancelled(run_id):
                        return
                    run = self.store.get_item("research_runs", run_id) or run
                    run.update(
                        {
                            "status": "complete",
                            "stage": "complete",
                            "message": "Related-ideas comparison generated.",
                            "result_idea_id": idea_id,
                            "result_version_id": result.get("version_id", ""),
                            "counts": {**dict(run.get("counts") or {}), "related_rows": len(result.get("related_existed_ideas") or [])},
                            "completed_at": utc_now(),
                            "updated_at": utc_now(),
                        }
                    )
                    self.store.upsert("research_runs", run, "run_id")
                except Exception as exc:
                    run = self.store.get_item("research_runs", run_id) or {"run_id": run_id}
                    if run.get("status") == "cancelled":
                        return
                    run.update({"status": "error", "stage": "error", "message": str(exc), "errors": [str(exc)], "updated_at": utc_now()})
                    self.store.upsert("research_runs", run, "run_id")

            threading.Thread(target=worker, name=f"principia-v1-related-{run_id}", daemon=True).start()
            return {"ok": True, "run_id": run_id}
        if path == "/api/v1/ideas/redesign-from-comparison/start":
            field_id = str(payload.get("field_id") or "default")
            idea_id = str(payload.get("idea_id") or "")
            model_mode = str(payload.get("model_mode") or "auto")
            version = str(payload.get("version") or "")
            run_id = f"V1REDESIGN-{int(time.time() * 1000)}"
            self.store.upsert(
                "research_runs",
                {
                    "run_id": run_id,
                    "field_id": field_id,
                    "type": "v1_idea_redesign_from_comparison",
                    "status": "queued",
                    "stage": "queued",
                    "message": "Redesign from related comparison queued.",
                    "idea_id": idea_id,
                    "model_mode": model_mode,
                    "started_at": utc_now(),
                    "updated_at": utc_now(),
                    "counts": {},
                    "warnings": [],
                },
                "run_id",
            )

            def worker() -> None:
                try:
                    run = self.store.get_item("research_runs", run_id) or {"run_id": run_id}
                    run.update({"status": "running", "stage": "collecting_evidence", "message": "Preparing comparison-grounded redesign.", "updated_at": utc_now()})
                    self.store.upsert("research_runs", run, "run_id")
                    result = self.engine.v2_redesign_from_related_comparison(
                        field_id=field_id,
                        idea_id=idea_id,
                        model_mode=model_mode,
                        version=version,
                        run_id=run_id,
                    )
                    if self.engine._is_run_cancelled(run_id):
                        return
                    run = self.store.get_item("research_runs", run_id) or run
                    run.update(
                        {
                            "status": "complete",
                            "stage": "complete",
                            "message": "Idea redesigned from related comparison.",
                            "result_idea_id": idea_id,
                            "result_version_id": result.get("version_id", ""),
                            "completed_at": utc_now(),
                            "updated_at": utc_now(),
                        }
                    )
                    self.store.upsert("research_runs", run, "run_id")
                except Exception as exc:
                    run = self.store.get_item("research_runs", run_id) or {"run_id": run_id}
                    if run.get("status") == "cancelled":
                        return
                    run.update({"status": "error", "stage": "error", "message": str(exc), "errors": [str(exc)], "updated_at": utc_now()})
                    self.store.upsert("research_runs", run, "run_id")

            threading.Thread(target=worker, name=f"principia-v1-redesign-{run_id}", daemon=True).start()
            return {"ok": True, "run_id": run_id}
        if path == "/api/v1/feedback/ingest":
            return self.engine.assimilate_feedback(payload, field_id=str(payload.get("field_id") or "default"))
        if path == "/api/v1/migrate":
            source = str(payload.get("source_db_path") or "")
            if source:
                return self.engine.migrate_sqlite_to_v1_memory(source, project_id=str(payload.get("field_id") or "default"))
            return self.engine.migrate_to_v1_memory(project_id=str(payload.get("field_id") or "default"))
        if path == "/api/v1/project/create":
            return self.engine.create_project(
                name=str(payload.get("name") or "Untitled Project"),
                query=str(payload.get("query") or payload.get("goal_text") or ""),
                description=str(payload.get("description") or ""),
                goal_text=str(payload.get("goal_text") or payload.get("query") or ""),
                settings=dict(payload.get("settings") or {}),
            )
        if path == "/api/v1/project/update":
            return self.engine.update_project(str(payload.get("field_id") or ""), payload)
        if path == "/api/v1/project/delete":
            return self.engine.delete_project(
                str(payload.get("field_id") or ""),
                delete_orphan_records=bool(payload.get("delete_local_data") or payload.get("delete_orphan_records")),
            )
        if path == "/api/v1/local-records/cleanup":
            return self.engine.cleanup_local_records()
        if path == "/api/v1/local-records/clear":
            return self.engine.clear_local_records(include_projects=bool(payload.get("include_projects")))
        if path == "/api/v1/project/reorder":
            return {"items": self.engine.reorder_projects([str(item) for item in payload.get("field_ids", [])])}
        if path == "/api/v1/project/generate":
            field_id = str(payload.get("field_id") or "default")
            query = str(payload.get("goal_text") or payload.get("query") or "")
            settings = dict(payload.get("settings") or {})
            result = self.engine.generate_ideas(
                query,
                max_ideas=int(settings.get("max_ideas", payload.get("max_ideas", 4))),
                max_works=int(settings.get("max_works", payload.get("max_works", 6))),
                paper_count=int(settings.get("paper_count", payload.get("paper_count", settings.get("max_works", 6)))),
                constraints=dict(payload.get("constraints") or {}),
                offline=bool(payload.get("offline", False)),
                model_mode=str(settings.get("model_mode", payload.get("model_mode", "auto"))),
                source_mode=str(settings.get("source_mode", payload.get("source_mode", "online"))),
                language=str(settings.get("language", payload.get("language", "en"))),
                force_refresh=bool(payload.get("force_refresh", False)),
            )
            result["project_summary"] = self.engine.attach_generation_to_project(field_id, result, query=query, settings=settings)
            return result
        if path == "/api/v1/project/refresh":
            return self.engine.refresh_project(
                str(payload.get("field_id") or "default"),
                query=str(payload.get("query") or payload.get("goal_text") or ""),
                source_mode=str(payload.get("source_mode") or "online"),
                paper_count=int(payload.get("paper_count") or 10),
                model_mode=str(payload.get("model_mode") or "auto"),
                force=bool(payload.get("force", False)),
            )
        if path == "/api/v1/idea/assemble":
            return self.engine.assemble_idea(
                field_id=str(payload.get("field_id") or "default"),
                goal_text=str(payload.get("goal_text") or ""),
                project_name=str(payload.get("project_name") or ""),
                project_description=str(payload.get("project_description") or ""),
                selected_refs=list(payload.get("selected_refs") or []),
                user_note=str(payload.get("user_note") or ""),
                language=str(payload.get("language") or "en"),
                model_mode=str(payload.get("model_mode") or "auto"),
            )
        if path == "/api/v1/import/v0":
            default_source = ROOT_DIR.parent / "Principia-demo-jun8-v0" / "data" / "principia.sqlite"
            imported = self.engine.import_v0_store(str(payload.get("source_db_path") or default_source))
            migration = self.engine.migrate_to_v1_memory(project_id=str(payload.get("field_id") or "default"))
            return {**imported, "v1_migration": migration}
        raise ValueError(f"Unknown v1 endpoint: {path}")

    def _handle_api_get(self, path: str, params: dict[str, list[str]]) -> None:
        if path.startswith("/api/v2/"):
            self._handle_v2_get(path, params)
            return
        if path.startswith("/api/v1/"):
            self._handle_v1_get(path, params)
            return
        if path.startswith("/api/library/"):
            self._handle_library_get(path, params)
            return
        if path == "/api/state":
            data = self.store.snapshot(limit_per_bucket=80)
            self._repair_snapshot(data)
            counts = self.store.counts()
            self._send_json({"counts": counts, "store": data})
            return
        if path == "/api/settings":
            self._send_json(self._settings_payload())
            return
        if path == "/api/progress":
            progress_id = params.get("id", [""])[0]
            self._send_json(self.progress.get(progress_id, {"stage": "unknown", "found": 0, "target": 0}))
            return
        if path == "/api/principles":
            query = params.get("query", [""])[0]
            top_k = int(params.get("top_k", ["12"])[0])
            min_validation = params.get("min_validation", ["L0"])[0]
            model_mode = params.get("model_mode", ["auto"])[0]
            search_k = top_k if model_mode == "auto" else max(top_k * 12, 100)
            items = self.store.search_principles(query, top_k=search_k, min_validation=min_validation)
            if model_mode != "auto":
                items = [item for item in items if item.get("model_mode") == model_mode]
            if query:
                goal = to_dict(self.engine._fallback_goal(query, {}, self.engine._complexity(query, {})))
                items = self.engine._filter_domain_compatible_principles(goal, items)
            self._send_json(self.engine.repair_language_variants_many(items[:top_k]))
            return
        if path == "/api/ideas":
            query = params.get("query", [""])[0]
            top_k = int(params.get("top_k", ["12"])[0])
            model_mode = params.get("model_mode", ["auto"])[0]
            data = self.store.snapshot(limit_per_bucket=None)
            goal_ids = {
                goal_id
                for goal_id, goal in data.get("goals", {}).items()
                if not query or goal.get("raw_query") == query
            }
            search_k = max(top_k * 8, 40) if model_mode == "auto" else max(top_k * 12, 100)
            principles = self.store.search_principles(query, top_k=search_k, min_validation="L0") if query else []
            if model_mode != "auto":
                principles = [item for item in principles if item.get("model_mode") == model_mode]
            if query:
                goal = to_dict(self.engine._fallback_goal(query, {}, self.engine._complexity(query, {})))
                principles = self.engine._filter_domain_compatible_principles(goal, principles)
            else:
                goal = None
            principle_ids = {item.get("principle_id") for item in principles}
            items = []
            for idea in data.get("ideas", {}).values():
                if model_mode != "auto" and idea.get("model_mode") != model_mode:
                    continue
                if not query:
                    items.append(idea)
                    continue
                if goal and not self.engine._is_domain_compatible(goal, idea):
                    continue
                linked_to_goal = idea.get("research_goal_id") in goal_ids
                linked_to_principles = bool(principle_ids & set(idea.get("source_principles", [])))
                directly_relevant = lexical_score(query, self.engine._material_text(idea)) >= 0.18
                if linked_to_goal or (linked_to_principles and directly_relevant) or directly_relevant:
                    items.append(idea)
            deduped = []
            seen: set[tuple[str, str, str]] = set()
            for idx, raw_idea in enumerate(reversed(items)):
                idea = dict(raw_idea)
                idea["title"] = self.engine._clean_idea_title(str(idea.get("title", "")), idx)
                key = (
                    str(idea.get("model_mode", "")),
                    str(idea.get("research_goal_id", "")),
                    self.engine._idea_title_key(str(idea.get("title", ""))),
                )
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(self.engine.repair_language_variants(idea))
            self._send_json(deduped[:top_k])
            return
        if path == "/api/items":
            bucket = params.get("bucket", [""])[0]
            query = params.get("query", [""])[0]
            limit = int(params.get("limit", ["100"])[0])
            self._send_json(self.engine.repair_language_variants_many(self.store.list_items(bucket, query=query, limit=limit)))
            return
        if path == "/api/item":
            bucket = params.get("bucket", [""])[0]
            item_id = params.get("id", [""])[0]
            item = self.store.get_item(bucket, item_id)
            if item is None:
                self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            else:
                self._send_json(self.engine.repair_language_variants(item))
            return
        if path == "/api/graph":
            query = params.get("query", [""])[0]
            model_mode = params.get("model_mode", ["auto"])[0]
            self._send_json(self.engine.build_graph(query=query, model_mode=model_mode))
            return
        self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def _handle_v2_get(self, path: str, params: dict[str, list[str]]) -> None:
        field_id = params.get("field_id", ["default"])[0] or "default"
        query = params.get("query", [""])[0]
        model_mode = params.get("model_mode", ["auto"])[0] or "auto"
        if path in {"/api/v2/research/status", "/api/v2/llm/status", "/api/v2/my-idea/generate/status", "/api/v2/my-idea/regenerate/status"}:
            run_id = params.get("run_id", [""])[0]
            run = self.store.get_item("research_runs", run_id)
            if not run:
                self._send_json({"error": "Run not found"}, HTTPStatus.NOT_FOUND)
                return
            run = self.engine.recover_stale_research_run(run_id) or run
            run_field_id = str(run.get("field_id") or field_id)
            self._send_json({"run": run, "summary": self.engine.v2_project_summary_or_deleted(run_field_id, run=run)})
            return
        if path == "/api/v2/project/summary":
            self._send_json(self.engine.v2_project_summary_or_deleted(field_id=field_id, query=query))
            return
        if path == "/api/v2/project/tab":
            self._send_json(
                self.engine.build_v2_project_tab(
                    field_id,
                    params.get("tab", ["existed_ideas"])[0],
                    offset=int(params.get("offset", ["0"])[0]),
                    limit=int(params.get("limit", ["10"])[0]),
                    query=query,
                    model_mode=model_mode,
                    sort_mode=params.get("sort", ["composite"])[0] or "composite",
                )
            )
            return
        if path == "/api/v2/item/detail":
            self._send_json(
                self.engine.v2_item_detail(
                    params.get("bucket", [""])[0],
                    params.get("id", [""])[0],
                    version=params.get("version", [""])[0],
                    model_mode=model_mode,
                )
            )
            return
        if path == "/api/v2/assembler/sources":
            self._send_json(
                self.engine.v2_assembler_sources(
                    field_id,
                    params.get("source", ["existed_ideas"])[0],
                    query=query,
                    offset=int(params.get("offset", ["0"])[0]),
                    limit=int(params.get("limit", ["20"])[0]),
                    model_mode=model_mode,
                )
            )
            return
        if path == "/api/v2/my-idea/detail":
            self._send_json(
                self.engine.v2_my_idea_detail(
                    field_id,
                    params.get("idea_id", [""])[0],
                    model_mode=model_mode,
                    version=params.get("version", [""])[0],
                )
            )
            return
        self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def _handle_library_get(self, path: str, params: dict[str, list[str]]) -> None:
        field_id = params.get("field_id", ["default"])[0] or "default"
        query = params.get("query", [""])[0]
        limit = int(params.get("limit", ["200"])[0])
        if path == "/api/library/projects":
            self._send_json({"items": self.engine.list_projects()})
            return
        if path == "/api/library/dashboard":
            self._send_json(self.engine.build_library_dashboard(field_id=field_id, query=query))
            return
        if path == "/api/library/works":
            data = self.store.snapshot(limit_per_bucket=None)
            works = self.engine._project_records(data, field_id, "source_works", query=query)[:limit]
            facts = self._field_records_for_ids(data.get("work_facts", {}), field_id, "work_id", [work.get("work_id", "") for work in works])
            benchmarks = self._field_records_for_ids(data.get("benchmark_records", {}), field_id, "work_id", [work.get("work_id", "") for work in works])
            baselines = self._field_records_for_ids(data.get("baseline_records", {}), field_id, "work_id", [work.get("work_id", "") for work in works])
            results = self._field_records_for_ids(data.get("result_records", {}), field_id, "work_id", [work.get("work_id", "") for work in works])
            self._send_json(
                {
                    "items": self.engine.repair_language_variants_many(works),
                    "work_facts": facts,
                    "benchmark_records": benchmarks,
                    "baseline_records": baselines,
                    "result_records": results,
                }
            )
            return
        if path == "/api/library/work":
            work_id = params.get("id", [""])[0] or params.get("work_id", [""])[0]
            work = self.store.get_item("source_works", work_id)
            if not work:
                self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return
            self.engine.extract_work_facts(self.engine._observatory_goal(query), work, field_id=field_id, persist=True)
            self.engine.extract_benchmark_records(self.engine._observatory_goal(query), work, field_id=field_id, persist=True)
            data = self.store.snapshot(limit_per_bucket=None)
            self._send_json(
                {
                    "item": self.engine.repair_language_variants(work),
                    "work_facts": self._field_records_for_ids(data.get("work_facts", {}), field_id, "work_id", [work_id]),
                    "benchmark_records": self._field_records_for_ids(data.get("benchmark_records", {}), field_id, "work_id", [work_id]),
                    "baseline_records": self._field_records_for_ids(data.get("baseline_records", {}), field_id, "work_id", [work_id]),
                    "result_records": self._field_records_for_ids(data.get("result_records", {}), field_id, "work_id", [work_id]),
                }
            )
            return
        if path == "/api/library/principles":
            data = self.store.snapshot(limit_per_bucket=None)
            principles = self.engine._project_records(data, field_id, "principles", query=query)[:limit]
            ideas = list(data.get("ideas", {}).values())
            works = data.get("source_works", {})
            rows = self.engine._top_principles_payload(principles, ideas, works)
            self._send_json({"items": self.engine.repair_language_variants_many(principles), "summary": rows})
            return
        if path == "/api/library/insights":
            self._send_json(self.engine.build_fact_view("insight", field_id=field_id, query=query))
            return
        if path == "/api/library/novelty":
            self._send_json(self.engine.build_fact_view("novelty", field_id=field_id, query=query))
            return
        if path == "/api/library/ideas":
            data = self.store.snapshot(limit_per_bucket=None)
            ideas = self.engine._project_records(data, field_id, "ideas", query=query)[:limit]
            calibrated = []
            for idea in ideas:
                item = self.engine.repair_language_variants(idea)
                estimate = dict(data.get("estimates", {}).get(item.get("result_estimate_id", ""), {}))
                if estimate:
                    estimate.setdefault("estimate_confidence", "stored")
                    estimate.setdefault("baseline_threat_level", "high" if item.get("baselines") else "unknown")
                    estimate.setdefault("benchmark_risk", "unknown")
                item["_calibrated_estimate"] = estimate
                plan_id = item.get("codex_prompt_plan_id", "")
                item["_prompt_plan"] = data.get("prompt_plans", {}).get(plan_id)
                calibrated.append(item)
            self._send_json({"items": calibrated})
            return
        if path == "/api/library/benchmarks":
            self._send_json(self.engine.build_benchmark_view(field_id=field_id, query=query))
            return
        if path == "/api/library/baselines":
            self._send_json(self.engine.build_baseline_view(field_id=field_id, query=query))
            return
        if path == "/api/library/gaps":
            gaps = self.engine.mine_gap_cards(field_id=field_id, query=query, persist=True, ensure=False)
            self._send_json({"items": gaps})
            return
        if path == "/api/library/graph":
            mode = params.get("mode", ["principle_lineage"])[0]
            self._send_json(self.engine.build_library_graph(field_id=field_id, mode=mode, query=query))
            return
        if path == "/api/library/runs":
            runs = self.store.list_items("runs", query=query, limit=limit)
            self._send_json({"items": runs})
            return
        if path == "/api/library/assistant_export":
            idea_id = params.get("idea_id", [""])[0]
            target_agent = params.get("target_agent", ["codex"])[0]
            self._send_json(self.engine.build_assistant_export_bundle(idea_id, target_agent=target_agent, field_id=field_id))
            return
        self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def _field_records_for_ids(
        self,
        records: dict,
        field_id: str,
        id_key: str,
        ids: list[str],
        *,
        query: str = "",
    ) -> list[dict]:
        wanted = {item for item in ids if item}
        output = []
        for item in records.values():
            if item.get("field_id", "default") != field_id:
                continue
            if wanted and item.get(id_key) not in wanted:
                continue
            if query and lexical_score(query, json.dumps(item, ensure_ascii=False)) <= 0:
                continue
            output.append(item)
        output.sort(key=lambda row: row.get("updated_at") or row.get("created_at") or "", reverse=True)
        return output

    def _repair_snapshot(self, data: dict) -> None:
        for bucket in ("source_works", "principles", "ideas"):
            records = data.get(bucket) or {}
            for key, item in list(records.items()):
                records[key] = self.engine.repair_language_variants(item)

    def _settings_payload(self) -> dict:
        settings = get_settings()
        return {
            "siliconflow": {
                "configured": bool(settings.api_key),
                "masked": _mask_secret(settings.api_key),
                "base_url": settings.base_url,
            },
            "openai": {
                "configured": bool(settings.openai_api_key),
                "masked": _mask_secret(settings.openai_api_key),
                "base_url": settings.openai_base_url,
            },
            "cost_limit_cny": settings.cost_limit_cny,
            "request_timeout": settings.request_timeout,
            "slow_request_timeout": settings.slow_request_timeout,
        }

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw or "{}")

    def _handle_v1_get(self, path: str, params: dict[str, list[str]]) -> None:
        field_id = params.get("field_id", ["default"])[0]
        query = params.get("query", [""])[0]
        if path in {"/api/v1/research/status", "/api/v1/llm/status", "/api/v1/ideas/generate/status"}:
            run_id = params.get("run_id", [""])[0]
            run = self.store.get_item("research_runs", run_id)
            if not run:
                self._send_json({"error": "Run not found"}, HTTPStatus.NOT_FOUND)
                return
            run = self.engine.recover_stale_research_run(run_id) or run
            run_field_id = str(run.get("field_id") or field_id)
            self._send_json({"run": run, "summary": self.engine.v2_project_summary_or_deleted(run_field_id, run=run)})
            return
        if path == "/api/v1/projects":
            self._send_json({"items": self.engine.list_projects()})
            return
        if path == "/api/v1/project/summary":
            self._send_json(self.engine.v2_project_summary_or_deleted(field_id=field_id, query=query))
            return
        if path == "/api/v1/project/tab":
            self._send_json(
                self.engine.build_v2_project_tab(
                    field_id,
                    params.get("tab", ["existed_ideas"])[0],
                    offset=int(params.get("offset", ["0"])[0]),
                    limit=int(params.get("limit", ["10"])[0]),
                    query=query,
                    model_mode=params.get("model_mode", ["auto"])[0] or "auto",
                    sort_mode=params.get("sort", ["composite"])[0] or "composite",
                )
            )
            return
        if path == "/api/v1/item/detail":
            self._send_json(
                self.engine.v2_item_detail(
                    params.get("bucket", [""])[0],
                    params.get("id", [""])[0],
                    version=params.get("version", [""])[0],
                    model_mode=params.get("model_mode", ["auto"])[0] or "auto",
                )
            )
            return
        if path == "/api/v1/symbols/table":
            namespace = params.get("namespace", [field_id or "global"])[0] or "global"
            self._send_json(self.engine.v1_symbols_table(namespace=namespace, limit=int(params.get("limit", ["200"])[0])))
            return
        if path == "/api/v1/symbols/expand":
            namespace = params.get("namespace", [field_id or "global"])[0] or "global"
            try:
                self._send_json(self.engine.v1_symbol_expand(params.get("symbol", [""])[0], namespace=namespace))
            except KeyError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
            return
        if path.startswith("/api/v1/ideas/") and path.endswith("/export"):
            idea_id = path.removeprefix("/api/v1/ideas/").removesuffix("/export")
            filename, body, content_type = self.engine.export_my_idea_markdown(
                field_id,
                idea_id,
                model_mode=params.get("model_mode", ["auto"])[0] or "auto",
                version=params.get("version", [""])[0],
            )
            self._send_bytes(body, content_type, filename)
            return
        if path.startswith("/api/v1/ideas/") and path.endswith("/lineage"):
            idea_id = path.removeprefix("/api/v1/ideas/").removesuffix("/lineage")
            self._send_json(self.engine.v1_idea_lineage(idea_id))
            return
        if path == "/api/v1/global/search":
            self._send_json(
                self.engine.v1_retrieve_concepts(
                    query,
                    field_id=field_id or "default",
                    concept_types=params.get("concept_type", []) or None,
                    limit_per_type=int(params.get("limit", ["12"])[0]),
                )
            )
            return
        self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def _serve_static(self, path: str) -> None:
        if path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        if path in {"", "/"}:
            target = STATIC_DIR / "index.html"
        else:
            clean = path.lstrip("/")
            target = (STATIC_DIR / clean).resolve()
            if STATIC_DIR.resolve() not in target.parents and target != STATIC_DIR.resolve():
                self._send_json({"error": "Forbidden"}, HTTPStatus.FORBIDDEN)
                return
        if not target.exists() or not target.is_file():
            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        mime = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        content = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, data: object, status: int = 200) -> None:
        status_code, body, content_type = _json_bytes(data, status)
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, body: bytes, content_type: str, filename: str) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        print("%s - %s" % (self.address_string(), fmt % args))


def make_handler(store: Store, engine: PrincipiaEngine):
    class BoundHandler(PrincipiaRequestHandler):
        pass

    BoundHandler.store = store
    BoundHandler.engine = engine
    BoundHandler.progress = {}
    return BoundHandler


def run_server(host: str = "127.0.0.1", port: int = 8790) -> None:
    store = Store()
    engine = PrincipiaEngine(store=store)
    handler = make_handler(store, engine)
    httpd = ThreadingHTTPServer((host, port), handler)
    print(f"Principia v1 running at http://{host}:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Principia v1.")
