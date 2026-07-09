from __future__ import annotations

import json
import mimetypes
import os
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .cloud.admin_ops import create_admin_operation, write_admin_operation
from .cloud.auth import (
    admin_session_status,
    check_admin_key,
    clear_admin_session_cookie,
    cloud_admin_status,
    create_admin_session_cookie,
    require_admin_authorization,
)
from .cloud.contribution import log_upload_status, prepare_contribution, upload_status
from .cloud.crawler import plan_crawl
from .cloud.github_client import maintainer_direct_push, publish_cloud_contribution
from .cloud.manifest import CloudManifestClient
from .cloud.resolver import CloudResolver
from .cloud.search import CloudSearch
from .config import ROOT_DIR, STATIC_DIR, get_settings
from .engine import CancelledRun, PrincipiaEngine
from .llm_client import LLMClient
from .models import to_dict, utc_now
from .storage import Store
from .utils import lexical_score


OTHER_FILTER_VALUE = "__other__"


def _json_bytes(data: object, status: int = 200) -> tuple[int, bytes, str]:
    return status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8"


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 10:
        return value[:2] + "..." + value[-2:]
    return value[:6] + "..." + value[-4:]


def _payload_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _payload_strings(value: Any, *, exclude_other: bool = True) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in _payload_list(value):
        text = str(item or "").strip()
        if not text:
            continue
        if exclude_other and text == OTHER_FILTER_VALUE:
            continue
        if text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def _payload_ints(value: Any) -> list[int]:
    output: list[int] = []
    seen: set[int] = set()
    for item in _payload_list(value):
        text = str(item or "").strip()
        if not text or text == OTHER_FILTER_VALUE:
            continue
        try:
            number = int(text)
        except Exception:
            continue
        if number in seen:
            continue
        seen.add(number)
        output.append(number)
    return output


def _payload_has_other(value: Any) -> bool:
    return any(str(item or "").strip() == OTHER_FILTER_VALUE for item in _payload_list(value))


def _cloud_crawl_goal_text(plan: dict[str, object], payload: dict[str, object]) -> str:
    topics = ", ".join(str(item) for item in (plan.get("topics") or []) if item) or "AI research"
    venues = ", ".join(str(item) for item in (plan.get("venues") or []) if item) or "public metadata venues"
    years = ", ".join(str(item) for item in (plan.get("years") or []) if item) or "recent years"
    rules = ", ".join(str(item) for item in (plan.get("priority_rules") or []) if item) or "venue, recency, topic"
    reason = str(payload.get("reason") or "").strip()
    text = f"Cloud crawl research for {topics}. Venues: {venues}. Years: {years}. Priority: {rules}."
    return f"{text} Reason: {reason}" if reason else text


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


def _openai_model_env_value(value: object) -> str:
    model = str(value or "").strip()
    if not model:
        return ""
    if model.startswith("model:"):
        model = model.removeprefix("model:")
    if ":" not in model:
        model = f"openai:{model}"
    return model


def _display_model_alias(value: str) -> str:
    text = str(value or "").strip()
    if text.startswith("openai:") or text.startswith("siliconflow:"):
        return text.split(":", 1)[1]
    return text


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
                if "openai_model" in payload:
                    model_value = _openai_model_env_value(payload.get("openai_model"))
                    if model_value:
                        updates["PRINCIPIA_OPENAI_GPT55_MODEL"] = model_value
                if "openai_api_style" in payload:
                    style = str(payload.get("openai_api_style") or "auto").strip().lower()
                    if style in {"auto", "chat_completions", "responses"}:
                        updates["PRINCIPIA_OPENAI_API_STYLE"] = style
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
            if result is None:
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
            force_refresh = bool(payload.get("force_refresh", False) or payload.get("force", False))
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
                        force_refresh=force_refresh,
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
        if path == "/api/v1/admin/login":
            auth = check_admin_key(str(payload.get("admin_key") or ""), purpose="homepage_admin_mode")
            if not auth.get("ok") or not auth.get("authorized"):
                self._send_json(
                    {"error": str(auth.get("error") or auth.get("warning") or "Admin mode is not configured."), "authorization": auth},
                    HTTPStatus.FORBIDDEN,
                )
                return None
            self._send_json(
                {**admin_session_status(""), "authenticated": True, "authorization": auth},
                headers={"Set-Cookie": create_admin_session_cookie()},
            )
            return None
        if path == "/api/v1/admin/logout":
            self._send_json(
                {**admin_session_status(""), "authenticated": False},
                headers={"Set-Cookie": clear_admin_session_cookie()},
            )
            return None
        if path.startswith("/api/v1/cloud/"):
            return self._handle_cloud_post(path, payload)
        if path == "/api/v1/research/start":
            field_id = str(payload.get("field_id") or "default")
            goal_text = str(payload.get("goal_text") or payload.get("query") or "")
            model_mode = str(payload.get("model_mode") or "auto")
            target_works = int(payload.get("target_works") or payload.get("paper_count") or 100)
            force_refresh = bool(payload.get("force_refresh", False) or payload.get("force", False))
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
                        force_refresh=force_refresh,
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
        if path == "/api/v1/local-records/compact":
            return self.engine.compact_local_storage(clear_cloud_cache=bool(payload.get("clear_cloud_cache", True)))
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
                    field_id=field_id,
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
            idea_id = params.get("idea_id", [""])[0]
            if not idea_id:
                self._send_json({"error": "idea_id is required"}, HTTPStatus.NOT_FOUND)
                return
            try:
                detail = self.engine.v2_my_idea_detail(
                    field_id,
                    idea_id,
                    model_mode=model_mode,
                    version=params.get("version", [""])[0],
                )
            except KeyError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
                return
            self._send_json(detail)
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
                "model": _display_model_alias(settings.model_aliases.get("openai_gpt55", "")),
                "api_style": settings.openai_api_style,
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
        if path == "/api/v1/admin/session":
            self._send_json(admin_session_status(self.headers.get("Cookie", "")))
            return
        if path.startswith("/api/v1/cloud"):
            self._handle_cloud_get(path, params)
            return
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
                    field_id=field_id,
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
        elif path == "/explore":
            target = STATIC_DIR / "explore.html"
        elif path == "/idea":
            target = STATIC_DIR / "idea.html"
        elif path == "/item":
            target = STATIC_DIR / "item.html"
        elif path == "/cloud":
            target = STATIC_DIR / "cloud.html"
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

    def _handle_cloud_get(self, path: str, params: dict[str, list[str]]) -> None:
        resolver = CloudResolver(self.store)
        if path == "/api/v1/cloud/manifest":
            try:
                self._send_json({"manifest": CloudManifestClient().load_manifest(refresh=params.get("refresh", ["0"])[0] in {"1", "true", "yes"})})
            except Exception as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
            return
        if path == "/api/v1/cloud/stats":
            self._send_json(resolver.stats())
            return
        if path == "/api/v1/cloud/local/summary":
            field_id = params.get("field_id", ["cloud-crawl"])[0] or "cloud-crawl"
            model_mode = params.get("model_mode", ["auto"])[0] or "auto"
            self._send_json({"field_id": field_id, "counts": self.engine.cloud_local_counts(field_id, model_mode=model_mode)})
            return
        if path == "/api/v1/cloud/local/tab":
            field_id = params.get("field_id", ["cloud-crawl"])[0] or "cloud-crawl"
            self._send_json(
                self.engine.build_cloud_local_tab(
                    field_id,
                    params.get("tab", ["works"])[0],
                    offset=int(params.get("offset", ["0"])[0]),
                    limit=int(params.get("limit", ["10"])[0]),
                    query=params.get("query", [""])[0],
                    model_mode=params.get("model_mode", ["auto"])[0] or "auto",
                    sync_state=params.get("sync_state", ["unsynced"])[0] or "unsynced",
                    include_counts=params.get("include_counts", ["1"])[0].lower() not in {"0", "false", "no"},
                )
            )
            return
        if path == "/api/v1/cloud/admin/status":
            self._send_json(cloud_admin_status())
            return
        if path.startswith("/api/v1/cloud/work/"):
            work_id = path.removeprefix("/api/v1/cloud/work/")
            local = self.store.get_item("source_works", work_id)
            cached = self._cloud_payload(work_id)
            if not local and not cached:
                self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return
            self._send_json({"item": local or cached, "cached_payload": cached})
            return
        if path.startswith("/api/v1/cloud/concept/"):
            concept_id = path.removeprefix("/api/v1/cloud/concept/")
            concept = self.engine.global_store.get_concept(concept_id)
            cached = self._cloud_payload(concept_id)
            if not concept and not cached:
                self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return
            self._send_json({"item": concept or cached, "cached_payload": cached})
            return
        if path == "/api/v1/cloud/upload/status":
            self._send_json(upload_status(self.store.path, params.get("upload_id", [""])[0]))
            return
        self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def _handle_cloud_post(self, path: str, payload: dict) -> dict:
        resolver = CloudResolver(self.store)
        if path == "/api/v1/cloud/resolve":
            return {
                "items": resolver.resolve_batch(
                    list(payload.get("candidates") or payload.get("items") or []),
                    str(payload.get("model_key") or ""),
                    hydrate=bool(payload.get("hydrate", True)),
                    project_id=str(payload.get("project_id") or payload.get("field_id") or "default"),
                )
            }
        if path == "/api/v1/cloud/prefetch" or path == "/api/v1/cloud/search":
            search_model_mode = str(payload.get("model_mode") or "")
            limit = int(payload.get("limit") or 20)
            offset = int(payload.get("offset") or 0)
            raw_venues = _payload_list(payload.get("venues"))
            raw_years = _payload_list(payload.get("years"))
            venues = _payload_strings(raw_venues)
            years = _payload_ints(raw_years)
            venue_other = bool(payload.get("venue_other")) or _payload_has_other(raw_venues)
            year_other = bool(payload.get("year_other")) or _payload_has_other(raw_years)
            return CloudSearch(resolver).search(
                str(payload.get("query") or ""),
                limit=limit,
                offset=offset,
                model_key=str(payload.get("model_key") or (self.engine._cloud_model_key(search_model_mode) if search_model_mode else "")),
                venue=str(payload.get("venue") or ""),
                venues=venues,
                venue_other=venue_other,
                known_venues=_payload_strings(payload.get("known_venues")),
                year=(_payload_ints(payload.get("year")) or [None])[0],
                years=years,
                year_other=year_other,
                known_years=_payload_ints(payload.get("known_years")),
                source_type=str(payload.get("source_type") or ""),
                concept_type=str(payload.get("concept_type") or ""),
            )
        if path == "/api/v1/cloud/hydrate":
            items = []
            snapshot_id = str(payload.get("snapshot_id") or "")
            model_key = str(payload.get("model_key") or "")
            project_id = str(payload.get("project_id") or payload.get("field_id") or "default")
            for record in payload.get("records") or []:
                items.append(self.engine.global_store.hydrate_cloud_work(record, snapshot_id=snapshot_id, model_key=model_key, project_id=project_id))
            return {"items": items}
        if path == "/api/v1/cloud/upload/record":
            bucket = str(payload.get("bucket") or "")
            record_id = str(payload.get("id") or payload.get("record_id") or "")
            field_id = str(payload.get("field_id") or "default")
            model_mode = str(payload.get("model_mode") or "auto")
            item: dict[str, Any] = {}
            if bucket == "source_works":
                work_ids = [record_id]
                item = self.store.get_item(bucket, record_id) or {}
            else:
                item = self.store.get_item(bucket, record_id)
                if not item:
                    raise KeyError(f"{bucket}:{record_id} not found")
                work_ids = self.engine._cloud_record_work_ids(bucket, item)
            if not work_ids:
                raise ValueError("No source work IDs are available for this record.")
            item_scoped_quality = self._cloud_record_upload_quality(bucket, item)
            item_scoped_upload = bucket in {"benchmark_records", "baseline_records"}
            if item_scoped_upload and not item_scoped_quality.get("ok"):
                return {
                    "ok": False,
                    "local_work_ids": work_ids,
                    "record_upload_quality": item_scoped_quality,
                    "cloud_publish": {
                        "ok": False,
                        "available_for_search": False,
                        "message": "This benchmark/baseline did not pass item-level cloud upload quality checks.",
                    },
                }
            sync_source = self.engine.sync_cloud_legacy_records_for_upload(
                work_ids,
                field_id=field_id,
                model_mode=model_mode,
            )
            export_work_ids = list(sync_source.get("work_ids") or work_ids)
            prepared = prepare_contribution(
                self.store.path,
                self.store.path.parent / "artifacts" / "cloud" / "contributions",
                model_key=self.engine._cloud_model_key(model_mode),
                work_ids=export_work_ids,
                created_by=dict(payload.get("created_by") or {}),
                upload_mode=str(payload.get("upload_mode") or "normal"),
                admin_key=str(payload.get("admin_key") or ""),
                require_complete_extraction=not item_scoped_upload,
            )
            prepared["record_upload_quality"] = item_scoped_quality
            if not prepared.get("ok"):
                decisions = [dict(item) for item in (prepared.get("upload_decisions") or []) if isinstance(item, dict)]
                cache_decisions = [
                    item
                    for item in decisions
                    if str(item.get("cloud_decision") or "") in {"cloud_cache_hit", "source_unchanged"}
                ]
                hard_rejections = [
                    item
                    for item in decisions
                    if not bool(item.get("upload_allowed")) and str(item.get("cloud_decision") or "") not in {"cloud_cache_hit", "source_unchanged"}
                ]
                if cache_decisions and not hard_rejections:
                    export_to_local = {str(export_id): str(local_id) for local_id, export_id in dict(sync_source.get("work_id_map") or {}).items()}
                    cached_local_ids = self.engine._ordered_unique(
                        [
                            export_to_local.get(str(item.get("work_id") or ""), str(item.get("work_id") or ""))
                            for item in cache_decisions
                            if str(item.get("work_id") or "")
                        ]
                    )
                    sync_result = self.engine.mark_cloud_synced(
                        cached_local_ids or work_ids,
                        field_id=field_id,
                        contribution_path=str(prepared.get("path") or ""),
                        upload_id="",
                        status="synced",
                        model_mode=model_mode,
                    )
                    return {
                        "ok": True,
                        "already_in_cloud": True,
                        "prepared": prepared,
                        "local_work_ids": work_ids,
                        "export_work_ids": export_work_ids,
                        "cloud_publish": {
                            "ok": True,
                            "available_for_search": True,
                            "message": "This paper/model version is already in the searchable cloud snapshot and was marked synced locally.",
                        },
                        "sync_result": sync_result,
                    }
                return {"ok": False, "prepared": prepared, "local_work_ids": work_ids, "export_work_ids": export_work_ids}
            contribution_path = str(prepared.get("path") or "")
            auth = require_admin_authorization(str(payload.get("admin_key") or ""), cookie_header=self.headers.get("Cookie", ""), purpose="cloud_upload_record_submit")
            remote = str(payload.get("remote") or "origin")
            base_branch = str(payload.get("base_branch") or "main")
            target_branch = str(payload.get("branch") or os.getenv("PRINCIPIA_CLOUD_UPLOAD_BRANCH") or "")
            background = self._start_cloud_publish_job(
                contribution_path,
                local_work_ids=work_ids,
                field_id=field_id,
                model_mode=model_mode,
                upload_mode=str(payload.get("upload_mode") or "normal"),
                branch=target_branch,
                remote=remote,
                base_branch=base_branch,
                dry_run=bool(payload.get("dry_run", False)),
            )
            return {
                "ok": True,
                "accepted": True,
                "prepared": prepared,
                "local_work_ids": work_ids,
                "export_work_ids": export_work_ids,
                "authorization": auth,
                **background,
                "cloud_publish": {
                    "ok": False,
                    "available_for_search": False,
                    "background": True,
                    "message": "Contribution accepted. Cloud publication is running in the background.",
                },
            }
        if path == "/api/v1/cloud/upload/prepare":
            upload_model_mode = str(payload.get("model_mode") or "auto")
            local_work_ids = [str(item) for item in (payload.get("work_ids") or []) if str(item).strip()]
            sync_source = self.engine.sync_cloud_legacy_records_for_upload(
                local_work_ids,
                field_id=str(payload.get("field_id") or "cloud-crawl"),
                model_mode=upload_model_mode,
            )
            export_work_ids = list(sync_source.get("work_ids") or local_work_ids)
            prepared = prepare_contribution(
                self.store.path,
                self.store.path.parent / "artifacts" / "cloud" / "contributions",
                model_key=str(payload.get("model_key") or self.engine._cloud_model_key(upload_model_mode)),
                work_ids=export_work_ids,
                created_by=dict(payload.get("created_by") or {}),
                upload_mode=str(payload.get("upload_mode") or "normal"),
                admin_key=str(payload.get("admin_key") or ""),
                require_complete_extraction=True,
            )
            work_id_map = dict(sync_source.get("work_id_map") or {})
            allowed_export_ids = {str(item) for item in (prepared.get("allowed_work_ids") or [])}
            allowed_local_work_ids = [
                local_id
                for local_id, export_id in work_id_map.items()
                if str(export_id) in allowed_export_ids
            ]
            if not allowed_local_work_ids:
                allowed_local_work_ids = [work_id for work_id in local_work_ids if work_id in allowed_export_ids]
            return {
                **prepared,
                "local_work_ids": local_work_ids,
                "allowed_local_work_ids": allowed_local_work_ids,
                "export_work_ids": export_work_ids,
                "legacy_sync": sync_source,
            }
        if path == "/api/v1/cloud/upload/submit":
            contribution_path = str(payload.get("contribution_path") or payload.get("path") or "")
            auth = require_admin_authorization(str(payload.get("admin_key") or ""), cookie_header=self.headers.get("Cookie", ""), purpose="cloud_upload_submit")
            remote = str(payload.get("remote") or "origin")
            base_branch = str(payload.get("base_branch") or "main")
            target_branch = str(payload.get("branch") or os.getenv("PRINCIPIA_CLOUD_UPLOAD_BRANCH") or "")
            direct_push = maintainer_direct_push(
                contribution_path,
                ROOT_DIR,
                branch=target_branch,
                remote=remote,
                base_branch=base_branch,
                push=not bool(payload.get("dry_run", False)),
            )
            direct_submitted = bool(direct_push.get("ok") and (direct_push.get("pushed") or "already exists" in str(direct_push.get("message") or "").lower()))
            cloud_publish = (
                publish_cloud_contribution(
                    contribution_path,
                    ROOT_DIR,
                    direct_push=direct_push,
                    branch=target_branch,
                    remote=remote,
                    base_branch=base_branch,
                    trigger_workflow=not bool(payload.get("dry_run", False)),
                    local_snapshot=not bool(payload.get("dry_run", False)),
                )
                if direct_submitted
                else {}
            )
            upload_state = "published" if cloud_publish.get("ok") and cloud_publish.get("available_for_search") else ("submitted" if direct_submitted else "prepared")
            if not direct_push.get("ok"):
                upload_state = "error"
            status = log_upload_status(
                self.store.path,
                contribution_path=contribution_path,
                status=upload_state,
                upload_mode=str(payload.get("upload_mode") or "normal"),
            )
            sync_result = {}
            if upload_state == "published":
                local_work_ids = [str(item) for item in (payload.get("local_work_ids") or payload.get("work_ids") or []) if str(item).strip()]
                sync_result = self.engine.mark_cloud_synced(
                    self.engine._ordered_unique([*local_work_ids, *self._work_ids_from_contribution(contribution_path)]),
                    field_id=str(payload.get("field_id") or "cloud-crawl"),
                    contribution_path=contribution_path,
                    upload_id=str(status.get("upload_id") or ""),
                    status="synced",
                    model_mode=str(payload.get("model_mode") or "auto"),
                )
            return {**status, "ok": upload_state == "published", "authorization": auth, "direct_push": direct_push, "cloud_publish": cloud_publish, "sync_result": sync_result}
        if path == "/api/v1/cloud/local/queue/add":
            return self.engine.queue_cloud_candidates(
                [dict(item) for item in (payload.get("candidates") or []) if isinstance(item, dict)],
                field_id=str(payload.get("field_id") or "cloud-crawl"),
                model_mode=str(payload.get("model_mode") or "auto"),
                recover_abstracts=bool(payload.get("recover_abstracts")),
                include_tab=payload.get("include_tab", True) is not False,
                include_counts=payload.get("include_counts", True) is not False,
            )
        if path == "/api/v1/cloud/local/queue/remove":
            return self.engine.remove_cloud_queue(
                [str(item) for item in (payload.get("work_ids") or []) if str(item).strip()],
                field_id=str(payload.get("field_id") or "cloud-crawl"),
                model_mode=str(payload.get("model_mode") or "auto"),
            )
        if path == "/api/v1/cloud/local/queue/clear":
            auth = require_admin_authorization(str(payload.get("admin_key") or ""), cookie_header=self.headers.get("Cookie", ""), purpose="cloud_queue_clear")
            result = self.engine.clear_cloud_queue(str(payload.get("field_id") or "cloud-crawl"))
            return {**result, "authorization": auth}
        if path == "/api/v1/cloud/local/tasks/add":
            return self.engine.add_cloud_research_tasks(
                [str(item) for item in (payload.get("work_ids") or []) if str(item).strip()],
                field_id=str(payload.get("field_id") or "cloud-crawl"),
                model_mode=str(payload.get("model_mode") or "auto"),
                include_tab=payload.get("include_tab", True) is not False,
                include_counts=payload.get("include_counts", True) is not False,
            )
        if path == "/api/v1/cloud/local/tasks/add-all":
            return self.engine.add_all_cloud_research_tasks(
                field_id=str(payload.get("field_id") or "cloud-crawl"),
                model_mode=str(payload.get("model_mode") or "all"),
                limit=int(payload.get("limit") or 10000),
                include_tab=payload.get("include_tab", False) is True,
                include_counts=payload.get("include_counts", False) is True,
            )
        if path == "/api/v1/cloud/local/tasks/remove":
            return self.engine.remove_cloud_research_tasks(
                [str(item) for item in (payload.get("work_ids") or []) if str(item).strip()],
                field_id=str(payload.get("field_id") or "cloud-crawl"),
                model_mode=str(payload.get("model_mode") or "auto"),
            )
        if path == "/api/v1/cloud/local/tasks/clear":
            auth = require_admin_authorization(str(payload.get("admin_key") or ""), cookie_header=self.headers.get("Cookie", ""), purpose="cloud_tasks_clear")
            result = self.engine.clear_cloud_research_tasks(
                str(payload.get("field_id") or "cloud-crawl"),
                model_mode=str(payload.get("model_mode") or "auto"),
            )
            return {**result, "authorization": auth}
        if path == "/api/v1/cloud/admin/crawl/plan" or path == "/api/v1/cloud/admin/crawl/run":
            auth = require_admin_authorization(str(payload.get("admin_key") or ""), cookie_header=self.headers.get("Cookie", ""), purpose="cloud_crawl") if path.endswith("/run") else cloud_admin_status()
            model_mode = str(payload.get("model_mode") or payload.get("model_key") or "auto")
            provided_candidates = [dict(item) for item in (payload.get("candidates") or []) if isinstance(item, dict)]
            max_papers = int(payload.get("max_papers") or 100)
            raw_venues = _payload_list(payload.get("venues"))
            raw_years = _payload_list(payload.get("years"))
            venues = _payload_strings(raw_venues)
            years = _payload_ints(raw_years)
            venue_other = bool(payload.get("venue_other")) or _payload_has_other(raw_venues)
            year_other = bool(payload.get("year_other")) or _payload_has_other(raw_years)
            known_venues = _payload_strings(payload.get("known_venues"))
            known_years = _payload_ints(payload.get("known_years"))
            if provided_candidates and path.endswith("/run"):
                plan = {
                    "plan_id": f"CRAWL-SELECTED-{int(time.time() * 1000)}",
                    "created_at": utc_now(),
                    "dry_run": False,
                    "venues": venues,
                    "venue_other": venue_other,
                    "known_venues": known_venues,
                    "years": years,
                    "year_other": year_other,
                    "known_years": known_years,
                    "topics": list(payload.get("topics") or []),
                    "priority_rules": list(payload.get("priority_rules") or []),
                    "model_key": str(payload.get("model_key") or self.engine._cloud_model_key(model_mode)),
                    "max_papers": max_papers,
                    "candidates": provided_candidates[:max(1, min(max_papers, 1000))],
                    "live_metadata": True,
                    "metadata_candidate_count": len(provided_candidates),
                    "metadata_warnings": [],
                    "execution_mode": "selected_local_research_run",
                    "next_step": "Extract the selected candidates and prepare a contribution pack.",
                }
            else:
                plan = plan_crawl(
                    venues=venues,
                    venue_other=venue_other,
                    known_venues=known_venues,
                    years=years,
                    year_other=year_other,
                    known_years=known_years,
                    topics=list(payload.get("topics") or []),
                    priority_rules=list(payload.get("priority_rules") or []),
                    max_papers=max_papers,
                    model_key=str(payload.get("model_key") or self.engine._cloud_model_key(model_mode)),
                    dry_run=path.endswith("/plan") or bool(payload.get("dry_run", True)),
                    live=True,
                    timeout=int(payload.get("timeout") or 12),
                )
            if path.endswith("/run"):
                operation = create_admin_operation(
                    "crawl_run",
                    "crawl_plan",
                    plan,
                    reason=str(payload.get("reason") or "Cloud Library admin crawler run"),
                    actor=str(payload.get("admin_actor") or ""),
                )
                out_path = write_admin_operation(self.store.path.parent / "artifacts" / "cloud" / "contributions", operation)
                run = self._start_cloud_crawl_run(plan, payload, str(out_path))
                return {**plan, "authorization": auth, "operation": operation, "path": str(out_path), **run}
            return {**plan, "authorization": auth}
        if path == "/api/v1/cloud/local/cleanup":
            auth = require_admin_authorization(str(payload.get("admin_key") or ""), cookie_header=self.headers.get("Cookie", ""), purpose="cloud_local_cleanup")
            result = self.engine.clear_cloud_synced_cache(str(payload.get("field_id") or "cloud-crawl"))
            return {**result, "authorization": auth}
        if path == "/api/v1/cloud/local/mark-synced":
            auth = require_admin_authorization(str(payload.get("admin_key") or ""), cookie_header=self.headers.get("Cookie", ""), purpose="cloud_local_mark_synced")
            result = self.engine.mark_cloud_synced(
                [str(item) for item in (payload.get("work_ids") or []) if str(item).strip()],
                field_id=str(payload.get("field_id") or "cloud-crawl"),
                contribution_path=str(payload.get("contribution_path") or ""),
                upload_id=str(payload.get("upload_id") or ""),
                status=str(payload.get("status") or "synced"),
                model_mode=str(payload.get("model_mode") or "auto"),
            )
            return {**result, "authorization": auth}
        if path in {
            "/api/v1/cloud/admin/edit",
            "/api/v1/cloud/admin/delete",
            "/api/v1/cloud/admin/merge-concepts",
            "/api/v1/cloud/admin/split-concept",
        }:
            auth = require_admin_authorization(str(payload.get("admin_key") or ""), cookie_header=self.headers.get("Cookie", ""), purpose="cloud_admin_operation")
            op_type = path.rsplit("/", 1)[-1].replace("-", "_")
            operation = create_admin_operation(
                op_type,
                str(payload.get("target_type") or "record"),
                dict(payload.get("payload") or payload),
                reason=str(payload.get("reason") or ""),
                actor=str(payload.get("admin_actor") or ""),
            )
            out_path = write_admin_operation(self.store.path.parent / "artifacts" / "cloud" / "contributions", operation)
            return {"authorization": auth, "operation": operation, "path": str(out_path)}
        raise ValueError(f"Unknown cloud endpoint: {path}")

    def _start_cloud_crawl_run(self, plan: dict[str, Any], payload: dict[str, Any], operation_path: str) -> dict[str, Any]:
        candidates = [dict(item) for item in plan.get("candidates") or []]
        if not candidates:
            raise ValueError("Crawler plan has no candidates to run.")
        run_id = f"V1CLOUDCRAWL-{int(time.time() * 1000)}"
        field_id = str(payload.get("field_id") or "cloud-crawl").strip() or "cloud-crawl"
        model_mode = str(payload.get("model_mode") or payload.get("model_key") or "auto").strip() or "auto"
        goal_text = _cloud_crawl_goal_text(plan, payload)
        model = self.engine._v2_model_meta(model_mode)
        parallelism = max(1, min(int(payload.get("parallelism") or os.getenv("PRINCIPIA_CLOUD_RESEARCH_PARALLELISM") or 4), 8))
        self.engine._cancelled_runs.discard(run_id)
        self.engine._ensure_field_profile(field_id, goal_text)
        run = {
            "run_id": run_id,
            "field_id": field_id,
            "type": "v1_cloud_crawl_research",
            "status": "queued",
            "stage": "queued",
            "message": "Queued cloud crawler research run.",
            "goal_text": goal_text,
            "model_mode": model_mode,
            "model_name": model.get("model_name", model_mode),
            "provider": model.get("provider", "offline"),
            "target_works": len(candidates),
            "plan_id": plan.get("plan_id", ""),
            "operation_path": operation_path,
            "counts": {
                "planned": len(candidates),
                "stored_works": 0,
                "extracted_works": 0,
                "cloud_hits": 0,
                "failed_works": 0,
                "ready_works": 0,
                "needs_review_works": 0,
                "active_works": 0,
                "parallelism": parallelism,
            },
            "errors": [],
            "warnings": list(plan.get("metadata_warnings") or []),
            "started_at": utc_now(),
            "updated_at": utc_now(),
        }
        self.store.upsert("research_runs", run, "run_id")
        threading.Thread(
            target=self._run_cloud_crawl_job,
            args=(run_id, field_id, goal_text, model_mode, candidates, bool(payload.get("force", False)), parallelism),
            name=f"principia-cloud-crawl-{run_id}",
            daemon=True,
        ).start()
        return {"ok": True, "run_id": run_id, "status_url": f"/api/v1/research/status?run_id={run_id}"}

    def _run_cloud_crawl_job(
        self,
        run_id: str,
        field_id: str,
        goal_text: str,
        model_mode: str,
        candidates: list[dict[str, Any]],
        force: bool,
        parallelism: int = 4,
    ) -> None:
        work_ids: list[str] = []
        errors: list[str] = []
        warnings: list[str] = []
        counts = {
            "planned": len(candidates),
            "stored_works": 0,
            "extracted_works": 0,
            "cloud_hits": 0,
            "skipped_works": 0,
            "failed_works": 0,
            "ready_works": 0,
            "needs_review_works": 0,
            "active_works": 0,
            "parallelism": max(1, min(int(parallelism or 4), 8)),
        }
        progress_lock = threading.RLock()
        active_work_ids: dict[str, int] = {}
        processed_works = 0

        def update(stage: str, message: str, **extra: Any) -> dict[str, Any]:
            with progress_lock:
                run = self.store.get_item("research_runs", run_id) or {"run_id": run_id}
                merged = {**dict(run.get("counts") or {}), **counts, **{key: value for key, value in extra.items() if value is not None}}
                run.update(
                    {
                        "status": "running" if stage not in {"complete", "error", "cancelled"} else stage,
                        "stage": stage,
                        "message": message,
                        "counts": merged,
                        "errors": errors[:20],
                        "warnings": self.engine._ordered_unique([*list(run.get("warnings") or []), *warnings])[:20],
                        "updated_at": utc_now(),
                    }
                )
                self.store.upsert("research_runs", run, "run_id")
                return run

        def process_work(idx: int, work_id: str) -> dict[str, Any]:
            worker_engine = PrincipiaEngine(store=self.store)
            self.engine._raise_if_cancelled(run_id)
            work = self.store.get_item("source_works", work_id) or {}
            with progress_lock:
                active_work_ids[work_id] = idx
                counts["active_works"] = len(active_work_ids)
                update(
                    "llm_extraction",
                    f"Researching {len(active_work_ids)} paper(s) in parallel.",
                    current_work_id=work_id,
                    current_index=idx,
                    active_work_ids=list(active_work_ids),
                    active_works=len(active_work_ids),
                    processed_works=processed_works,
                )
            self.engine._set_cloud_work_research_state(
                work_id,
                "researching",
                model_mode=model_mode,
                run_id=run_id,
                message=f"Researching {idx}/{len(work_ids)}.",
                extra={"cloud_research_index": idx, "cloud_research_total": len(work_ids)},
            )
            self.engine._set_cloud_work_task_state(
                work_id,
                "researching",
                model_mode=model_mode,
                run_id=run_id,
                message=f"Researching {idx}/{len(work_ids)}.",
            )
            try:
                result = worker_engine.v2_extract_single_work(
                    work_id,
                    field_id=field_id,
                    goal_text=goal_text,
                    model_mode=model_mode,
                    run_id=run_id,
                    force=force,
                )
                if result.get("cloud_cache_hit"):
                    outcome = "cloud_hits"
                elif result.get("already_extracted"):
                    outcome = "skipped_works"
                else:
                    outcome = "extracted_works"
                status = self.engine.cloud_work_research_status(work_id, field_id=field_id, model_mode=model_mode)
                if status.get("ready_to_sync"):
                    state = "ready"
                    message = "Extraction complete and ready to sync."
                elif result.get("cloud_cache_hit"):
                    state = "ready" if not status.get("missing_required") else "needs_review"
                    message = "Loaded from cloud cache." if state == "ready" else "Cloud cache hit is missing required local records."
                elif result.get("already_extracted"):
                    state = "ready" if not status.get("missing_required") else "needs_review"
                    message = "Already extracted locally." if state == "ready" else "Existing extraction is missing required records."
                else:
                    state = "needs_review"
                    message = "Extraction finished but required records are incomplete."
                self.engine._set_cloud_work_research_state(
                    work_id,
                    state,
                    model_mode=model_mode,
                    run_id=run_id,
                    message=message,
                    extra={
                        "cloud_required_missing": status.get("missing_required", []),
                        "cloud_required_counts": status.get("required_counts", {}),
                    },
                )
                self.engine._set_cloud_work_task_state(
                    work_id,
                    "done" if state == "ready" else state,
                    model_mode=model_mode,
                    run_id=run_id,
                    message=message,
                )
                return {"work_id": work_id, "outcome": outcome, "state": state, "message": message}
            except CancelledRun:
                raise
            except Exception as exc:
                self.engine._set_cloud_work_research_state(
                    work_id,
                    "failed",
                    model_mode=model_mode,
                    run_id=run_id,
                    message=self.engine._friendly_llm_error(exc),
                )
                self.engine._set_cloud_work_task_state(
                    work_id,
                    "failed",
                    model_mode=model_mode,
                    run_id=run_id,
                    message=self.engine._friendly_llm_error(exc),
                )
                return {"work_id": work_id, "outcome": "failed_works", "state": "failed", "error": f"{work_id}: {exc}"}
            finally:
                with progress_lock:
                    active_work_ids.pop(work_id, None)
                    counts["active_works"] = len(active_work_ids)

        try:
            update("metadata_store", "Storing public metadata candidates from the crawler plan.")
            candidates = self.engine._recover_candidate_abstracts([dict(item) for item in candidates])
            for candidate in candidates:
                self.engine._raise_if_cancelled(run_id)
                candidate = dict(candidate)
                selected_work_id = str(candidate.get("work_id") or "")
                if selected_work_id and self.store.get_item("source_works", selected_work_id):
                    candidate["preserve_work_id"] = True
                candidate.setdefault("cloud_local_origin", "cloud_crawl")
                candidate.setdefault("cloud_sync_status", "unsynced")
                candidate.setdefault("cloud_research_state", "queued")
                candidate.setdefault("cloud_research_run_id", run_id)
                candidate.setdefault("cloud_research_message", "Queued for cloud-page research.")
                work = self.engine._v2_upsert_work(candidate, model_mode="metadata")
                work_ids.append(work["work_id"])
                if self.engine._cloud_generic_queue_state(work) != "removed":
                    self.engine._set_cloud_work_research_state(
                        work["work_id"],
                        "queued",
                        model_mode="all",
                        run_id=run_id,
                        message="Queued for cloud-page research.",
                    )
                self.engine._set_cloud_work_task_state(
                    work["work_id"],
                    "research_task",
                    model_mode=model_mode,
                    run_id=run_id,
                    message="Prepared for cloud-page research.",
                )
                self.engine._set_cloud_work_research_state(
                    work["work_id"],
                    "queued",
                    model_mode=model_mode,
                    run_id=run_id,
                    message="Queued for cloud-page research.",
                )
                counts["stored_works"] = len(work_ids)
            self.engine.add_project_memberships(field_id, "source_works", self.engine._ordered_unique(work_ids), source="cloud_crawl", prepend=True)
            update("metadata_store", f"Stored {len(work_ids)} crawler work candidate(s).", stored_works=len(work_ids))
            if not self.engine.llm.available():
                warnings.append("LLM is not configured; crawler stored metadata but skipped extraction.")
                for work_id in work_ids:
                    self.engine._set_cloud_work_research_state(
                        work_id,
                        "metadata_only",
                        model_mode=model_mode,
                        run_id=run_id,
                        message="Metadata saved. Configure an LLM before extraction.",
                    )
                    self.engine._set_cloud_work_task_state(
                        work_id,
                        "metadata_only",
                        model_mode=model_mode,
                        run_id=run_id,
                        message="Metadata saved. Configure an LLM before extraction.",
                    )
                run = update("complete", "Crawler metadata import complete. Configure an LLM to extract Principles, ideas, benchmarks, baselines, and takeaways.", stored_works=len(work_ids))
                run["completed_at"] = utc_now()
                self.store.upsert("research_runs", run, "run_id")
                return
            max_workers = max(1, min(counts["parallelism"], len(work_ids)))
            update("llm_extraction", f"Starting cloud research with {max_workers} parallel API worker(s).", active_works=0, processed_works=0)
            executor = ThreadPoolExecutor(max_workers=max_workers)
            futures = {executor.submit(process_work, idx, work_id): (idx, work_id) for idx, work_id in enumerate(work_ids, start=1)}
            try:
                for future in as_completed(futures):
                    self.engine._raise_if_cancelled(run_id)
                    result = future.result()
                    with progress_lock:
                        processed_works += 1
                        outcome = str(result.get("outcome") or "")
                        if outcome in counts:
                            counts[outcome] += 1
                        if result.get("state") == "ready":
                            counts["ready_works"] += 1
                        elif result.get("state") == "needs_review":
                            counts["needs_review_works"] += 1
                        if result.get("error"):
                            errors.append(str(result.get("error")))
                        next_index = min(len(work_ids), processed_works + len(active_work_ids) + 1)
                        update(
                            "llm_extraction",
                            f"Processed {processed_works}/{len(work_ids)} crawler work candidate(s).",
                            processed_works=processed_works,
                            active_works=len(active_work_ids),
                            active_work_ids=list(active_work_ids),
                            current_work_id=next(iter(active_work_ids), ""),
                            current_index=next_index,
                        )
            finally:
                cancelled = self.engine._is_run_cancelled(run_id)
                if cancelled:
                    for pending in futures:
                        pending.cancel()
                executor.shutdown(wait=not cancelled, cancel_futures=cancelled)
            final_status = "complete" if not errors else "error"
            final_message = "Cloud crawler research complete." if not errors else "Cloud crawler research finished with per-work failures."
            run = update(final_status, final_message)
            run["completed_at"] = utc_now()
            self.store.upsert("research_runs", run, "run_id")
        except CancelledRun:
            run = self.store.get_item("research_runs", run_id) or {"run_id": run_id}
            for work_id in work_ids:
                status = self.engine.cloud_work_research_status(work_id, field_id=field_id, model_mode=model_mode)
                if status.get("ready_to_sync"):
                    self.engine._set_cloud_work_research_state(work_id, "ready", model_mode=model_mode, run_id=run_id, message="Extraction complete and ready to sync.")
                    self.engine._set_cloud_work_task_state(work_id, "done", model_mode=model_mode, run_id=run_id, message="Extraction complete and ready to sync.")
                    continue
                work = self.store.get_item("source_works", work_id) or {}
                status = self.engine.cloud_work_research_status(work_id, field_id=field_id, model_mode=model_mode)
                if status.get("run_id") == run_id and status.get("state") == "researching":
                    self.engine._set_cloud_work_research_state(work_id, "stopped", model_mode=model_mode, run_id=run_id, message="Research was stopped before this paper finished.")
                    self.engine._set_cloud_work_task_state(work_id, "stopped", model_mode=model_mode, run_id=run_id, message="Research was stopped before this paper finished.")
            self.engine._mark_run_cancelled(run)
        except Exception as exc:
            errors.append(str(exc))
            run = update("error", str(exc))
            run["completed_at"] = utc_now()
            self.store.upsert("research_runs", run, "run_id")

    def _cloud_payload(self, record_id: str) -> dict | None:
        with self.store._connect() as conn:
            row = conn.execute("SELECT payload_json FROM cloud_payload_cache WHERE record_id = ?", (record_id,)).fetchone()
            if not row:
                return None
            try:
                return json.loads(row["payload_json"] or "{}")
            except Exception:
                return None

    def _start_cloud_publish_job(
        self,
        contribution_path: str,
        *,
        local_work_ids: list[str],
        field_id: str,
        model_mode: str,
        upload_mode: str,
        branch: str,
        remote: str,
        base_branch: str,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        status = log_upload_status(
            self.store.path,
            contribution_path=contribution_path,
            status="publishing",
            upload_mode=upload_mode,
        )
        upload_id = str(status.get("upload_id") or "")

        def worker() -> None:
            direct_push: dict[str, Any] = {}
            cloud_publish: dict[str, Any] = {}
            upload_state = "prepared"
            error = ""
            try:
                direct_push = maintainer_direct_push(
                    contribution_path,
                    ROOT_DIR,
                    branch=branch,
                    remote=remote,
                    base_branch=base_branch,
                    push=not dry_run,
                )
                direct_submitted = bool(
                    direct_push.get("ok")
                    and (direct_push.get("pushed") or "already exists" in str(direct_push.get("message") or "").lower())
                )
                cloud_publish = (
                    publish_cloud_contribution(
                        contribution_path,
                        ROOT_DIR,
                        direct_push=direct_push,
                        branch=branch,
                        remote=remote,
                        base_branch=base_branch,
                        trigger_workflow=not dry_run,
                        local_snapshot=not dry_run,
                    )
                    if direct_submitted
                    else {}
                )
                upload_state = "published" if cloud_publish.get("ok") and cloud_publish.get("available_for_search") else ("submitted" if direct_submitted else "prepared")
                if not direct_push.get("ok"):
                    upload_state = "error"
                    error = str(direct_push.get("error") or "direct push did not complete")
                if upload_state == "published":
                    self.engine.mark_cloud_synced(
                        self.engine._ordered_unique([*local_work_ids, *self._work_ids_from_contribution(contribution_path)]),
                        field_id=field_id,
                        contribution_path=contribution_path,
                        upload_id=upload_id,
                        status="synced",
                        model_mode=model_mode,
                    )
            except Exception as exc:
                upload_state = "error"
                error = str(exc)
            self._update_cloud_upload_log(upload_id, upload_state, error=error)

        threading.Thread(
            target=worker,
            name=f"principia-cloud-publish-{upload_id or int(time.time() * 1000)}",
            daemon=True,
        ).start()
        return {
            "upload_id": upload_id,
            "status": "publishing",
            "contribution_path": contribution_path,
            "background_publish": {
                "started": True,
                "upload_id": upload_id,
                "status_url": f"/api/v1/cloud/upload/status?upload_id={upload_id}",
            },
        }

    def _update_cloud_upload_log(self, upload_id: str, status: str, *, error: str = "") -> None:
        if not upload_id:
            return
        completed = utc_now() if status in {"prepared", "submitted", "published", "error"} else None
        github_pr_url = f"error: {error[:480]}" if error else ""
        with sqlite3.connect(self.store.path, timeout=30) as conn:
            if github_pr_url:
                conn.execute(
                    """
                    UPDATE cloud_upload_log
                    SET status = ?, github_pr_url = ?, completed_at = COALESCE(?, completed_at)
                    WHERE upload_id = ?
                    """,
                    (status, github_pr_url, completed, upload_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE cloud_upload_log
                    SET status = ?, completed_at = COALESCE(?, completed_at)
                    WHERE upload_id = ?
                    """,
                    (status, completed, upload_id),
                )

    def _work_ids_from_contribution(self, contribution_path: str) -> list[str]:
        try:
            path = Path(contribution_path)
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        ids: list[str] = []
        for decision in data.get("upload_decisions") or []:
            if decision.get("upload_allowed") and decision.get("work_id"):
                ids.append(str(decision.get("work_id")))
        for work in data.get("work_records") or []:
            if work.get("work_id"):
                ids.append(str(work.get("work_id")))
        return self.engine._ordered_unique(ids)

    def _cloud_record_upload_quality(self, bucket: str, item: dict[str, Any]) -> dict[str, Any]:
        if bucket not in {"benchmark_records", "baseline_records"}:
            return {"ok": True, "score": 1.0, "reasons": []}
        reasons: list[str] = []
        score = 0.0
        if bucket == "benchmark_records":
            name = str(item.get("benchmark_name") or item.get("dataset") or item.get("canonical_label") or "").strip()
            task = str(item.get("task") or item.get("description") or "").strip()
            metrics = item.get("metrics") or item.get("metric") or []
            metric_count = len(metrics) if isinstance(metrics, list) else (1 if metrics else 0)
            links = [item.get("official_url"), item.get("url_or_doi"), *(item.get("candidate_dataset_pages") or []), *(item.get("source_urls") or [])]
            if name:
                score += 0.35
            else:
                reasons.append("missing benchmark name or dataset")
            if task:
                score += 0.25
            else:
                reasons.append("missing benchmark task/description")
            if metric_count:
                score += 0.2
            else:
                reasons.append("missing metric")
            if any(str(link or "").startswith("http") for link in links):
                score += 0.1
            if item.get("source_work_ids") or item.get("work_id") or item.get("source_works"):
                score += 0.1
            else:
                reasons.append("missing source work link")
        else:
            name = str(item.get("baseline_name") or item.get("canonical_label") or "").strip()
            method = str(item.get("core_idea") or item.get("methodology") or item.get("description") or item.get("principle") or "").strip()
            evidence = item.get("performance") or item.get("benchmarks") or item.get("evidence") or item.get("source_work_ids") or item.get("source_works")
            if name:
                score += 0.35
            else:
                reasons.append("missing baseline name")
            if method:
                score += 0.35
            else:
                reasons.append("missing baseline method/core idea")
            if evidence:
                score += 0.2
            else:
                reasons.append("missing benchmark/performance/source evidence")
            if item.get("source_work_ids") or item.get("work_id") or item.get("source_works"):
                score += 0.1
        ok = score >= 0.55
        if not ok and not reasons:
            reasons.append("quality score below upload threshold")
        return {"ok": ok, "score": round(score, 3), "reasons": reasons}

    def _send_json(self, data: object, status: int = 200, *, headers: dict[str, str] | None = None) -> None:
        status_code, body, content_type = _json_bytes(data, status)
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
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
