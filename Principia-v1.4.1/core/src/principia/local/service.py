from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx

from principia_retrieval.embeddings import SiliconFlowEmbeddingClient

from ..application.search import PrincipleSearchService
from ..domain import JobRecord, LiteratureRunLimits, event_id, monotonic_ulid
from ..models import utc_now
from ..persistence import V14WorkspaceRepository
from ..providers import ModelPolicy, ProviderCredentialStore, ProviderProfile
from ..providers.models import SILICONFLOW_AUTHORIZED_BASE_URLS
from ..research import ResearchService, coerce_work
from ..run import RunCancelledError, RunControlToken
from ..storage import WorkspaceStorage
from .acquisition import LiteratureAcquisitionService
from .areas import CandidateAreaSuggestionService
from .extraction import CandidateExtractionService
from .literature import rank_literature_for_goal
from .literature_discovery import LiteratureDiscoveryService
from .sources import LocalSourceService

_MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+\-]{1,199}$")


class LocalDiscoveryService:
    def __init__(
        self,
        storage: WorkspaceStorage,
        repository: V14WorkspaceRepository,
        search: PrincipleSearchService,
        research: ResearchService | None = None,
        *,
        local_data_root: str | Path | None = None,
        principles_export_root: str | Path | None = None,
        working_directory_root: str | Path | None = None,
        relation_rebuild: Callable[[], JobRecord] | None = None,
        global_cloud: Any | None = None,
    ) -> None:
        self.storage = storage
        self.repository = repository
        self.search = search
        self.local_data_root = (
            Path(local_data_root).expanduser().resolve() if local_data_root is not None else None
        )
        self.working_directory_root = (
            Path(working_directory_root).expanduser().resolve()
            if working_directory_root is not None
            else storage.root
        )
        self.principles_export_root = (
            Path(principles_export_root).expanduser().resolve()
            if principles_export_root is not None
            else storage.root / "principles"
        )
        self.literature = (
            LiteratureDiscoveryService(storage, repository, research)
            if research is not None
            else None
        )
        self.sources = LocalSourceService(storage, repository, local_data_root=local_data_root)
        self.acquisition = LiteratureAcquisitionService(storage, repository)
        self.extraction = CandidateExtractionService(
            storage,
            repository,
            principles_export_root=principles_export_root,
            relation_rebuild=relation_rebuild,
            global_cloud=global_cloud,
        )
        self.credentials = ProviderCredentialStore(storage.root)
        self.source_alias_receipt = self.repository.reconcile_duplicate_source_roots()
        self.root_reconciliation_receipt = self.sources.reconcile_working_directory_roots()
        self.materialization_receipt = self.sources.materialize_pending()
        self.layout_receipt = self.sources.consolidate_legacy_layouts()
        self.sidecar_isolation_receipt = self.sources.isolate_derived_sidecars()
        self.acquired_goal_receipt = self.repository.backfill_acquired_research_goals()
        self.membership_receipt = self.repository.repair_candidate_goal_memberships()
        self.area_suggestion_receipt = CandidateAreaSuggestionService(self.repository).backfill()
        self.runtime_lease_id = self.repository.acquire_runtime_lease()
        self.interrupted_orphan_count = (
            self.repository.interrupt_orphaned_jobs() if self.runtime_lease_id else 0
        )
        self.corrected_extraction_count = (
            self.repository.reconcile_misreported_extraction_jobs() if self.runtime_lease_id else 0
        )
        self.normalized_title_count = (
            self.repository.repair_generated_candidate_titles() if self.runtime_lease_id else 0
        )
        self.deterministic_revalidation_receipt = (
            self.extraction.revalidate_deterministic_quality()
            if self.runtime_lease_id
            else {"checked": 0, "held_back": 0}
        )
        self.principles_snapshot_receipt: dict[str, Any] = {}
        if principles_export_root is not None:
            from .portable import PortablePrincipleLibrary

            self.principles_snapshot_receipt = PortablePrincipleLibrary(storage, repository).export(
                principles_export_root
            )
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="principia-local")
        self._cancel: dict[str, threading.Event] = {}
        self._futures: dict[str, Future[Any]] = {}
        self._search_tokens: dict[str, RunControlToken] = {}
        self._search_deadlines: dict[str, threading.Event] = {}

    def close(self) -> None:
        """Release this workspace before a runtime-level directory switch."""

        self._executor.shutdown(wait=True, cancel_futures=False)
        for owned_service in (self.acquisition, self.extraction, self.literature):
            executor = getattr(owned_service, "_executor", None)
            if executor is not None:
                executor.shutdown(wait=True, cancel_futures=False)
        if self.runtime_lease_id:
            self.repository.release_runtime_lease(self.runtime_lease_id)

    @staticmethod
    def choose_working_directory() -> str:
        capability = LocalDiscoveryService.picker_capability()
        if not capability["available"]:
            raise RuntimeError(
                "native folder picker is unavailable; use the manual working-directory path"
            )
        if sys.platform == "darwin":
            command = [
                "osascript",
                "-e",
                'POSIX path of (choose folder with prompt "Choose a Principia working directory")',
            ]
        elif sys.platform == "win32":
            command = [
                "powershell",
                "-NoProfile",
                "-Command",
                "Add-Type -AssemblyName System.Windows.Forms; $d=New-Object "
                "System.Windows.Forms.FolderBrowserDialog; $d.Description='Choose a "
                "Principia working directory'; if($d.ShowDialog() -eq 'OK'){$d.SelectedPath}",
            ]
        else:
            command = [
                "zenity",
                "--file-selection",
                "--directory",
                "--title=Choose a Principia working directory",
            ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
        if result.returncode != 0 or not result.stdout.strip():
            raise RuntimeError("working-directory selection was cancelled")
        return result.stdout.strip()

    def provider_profile(self, provider_id: str = "siliconflow") -> ProviderProfile:
        if provider_id != "siliconflow":
            raise KeyError(f"unknown provider profile: {provider_id}")
        profile = ProviderProfile.siliconflow()
        metadata = self.credentials.metadata(provider_id)
        saved_base_url = str(metadata.get("base_url") or "")
        return profile.model_copy(
            update={
                "base_url": saved_base_url or profile.base_url,
                "configured": metadata["configured"],
                "credential_source": metadata["credential_source"],
                "saved_at": metadata["saved_at"],
            }
        )

    def provider_configuration(
        self, provider_id: str, model: str, *, egress_confirmed: bool
    ) -> tuple[ProviderProfile, ModelPolicy, str]:
        profile = self.provider_profile(provider_id)
        if not profile.configured:
            raise ValueError(f"{profile.label} is not configured in this workspace")
        model = model.strip()
        if not _MODEL_ID.fullmatch(model) or "://" in model:
            raise ValueError(
                "enter a valid provider model ID using letters, numbers, '.', '-', '_', ':', or '/'"
            )
        policy = ModelPolicy(
            mode="remote",
            provider=profile.provider,
            model=model,
            base_url=profile.base_url,
            remote_egress_confirmed=egress_confirmed,
        )
        return profile, policy, self.credentials.api_key(provider_id)

    def save_provider_credential(self, provider_id: str, api_key: str) -> dict[str, Any]:
        return self.credentials.save(provider_id, api_key)

    def delete_provider_credential(self, provider_id: str) -> dict[str, Any]:
        return self.credentials.delete(provider_id)

    def test_provider_connection(self, provider_id: str) -> dict[str, Any]:
        profile = self.provider_profile(provider_id)
        api_key = self.credentials.api_key(provider_id)
        if not api_key:
            raise ValueError(f"{profile.label} is not configured in this workspace")
        preferred = profile.base_url.rstrip("/")
        origins = [preferred]
        if preferred in SILICONFLOW_AUTHORIZED_BASE_URLS:
            origins.extend(
                origin for origin in SILICONFLOW_AUTHORIZED_BASE_URLS if origin != preferred
            )
        failures: list[dict[str, Any]] = []
        for origin in origins:
            try:
                response = httpx.get(
                    f"{origin}/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=httpx.Timeout(15.0, connect=10.0),
                    follow_redirects=False,
                )
            except httpx.TimeoutException:
                failures.append({"category": "timeout", "retryable": True})
                continue
            except httpx.HTTPError:
                failures.append({"category": "network", "retryable": True})
                continue
            if response.status_code < 400:
                self.credentials.remember_base_url(provider_id, origin)
                return {
                    "ok": True,
                    "category": "connected",
                    "retryable": False,
                    "base_url": origin,
                }
            if response.status_code == 429:
                self.credentials.remember_base_url(provider_id, origin)
                return {
                    "ok": False,
                    "category": "rate_limited",
                    "retryable": True,
                    "base_url": origin,
                }
            failures.append(
                {
                    "category": (
                        "authentication"
                        if response.status_code in {401, 403}
                        else "provider_unavailable"
                    ),
                    "retryable": response.status_code >= 500,
                }
            )
        if failures and all(item["category"] == "authentication" for item in failures):
            return {"ok": False, "category": "authentication", "retryable": False}
        return (
            failures[-1]
            if failures
            else {
                "ok": False,
                "category": "network",
                "retryable": True,
            }
        )

    def register_source(self, folder: str | Path) -> dict[str, Any]:
        try:
            root = Path(folder).expanduser().resolve(strict=True)
        except OSError as exc:
            raise FileNotFoundError(
                "selected Local source does not exist or is inaccessible"
            ) from exc
        if not root.is_dir():
            raise NotADirectoryError("selected Local source is not a directory")
        stat = root.stat()
        identity = hashlib.sha256(f"{stat.st_dev}:{stat.st_ino}:{root.name}".encode()).hexdigest()[
            :24
        ]
        source_id = f"src:{identity}"
        display_location = root.name
        if self.local_data_root is not None and root.is_relative_to(self.local_data_root):
            display_location = (
                Path("local_data") / root.relative_to(self.local_data_root)
            ).as_posix()
        return self.repository.register_source(
            source_id,
            root,
            f"local-source://{identity}",
            root.name,
            display_location,
        )

    def list_sources(self) -> list[dict[str, Any]]:
        return self.repository.list_sources()

    def create_managed_source(self, **kwargs: Any) -> dict[str, Any]:
        return self.sources.create_managed(**kwargs)

    def rename_source(self, source_id: str, display_name: str) -> dict[str, Any]:
        return self.sources.rename(source_id, display_name)

    def disconnect_source(self, source_id: str) -> dict[str, Any]:
        return self.sources.disconnect(source_id)

    def restore_source(self, source_id: str) -> dict[str, Any]:
        return self.sources.restore(source_id)

    def source_detail(self, source_id: str) -> dict[str, Any]:
        item = self.repository.source(source_id)
        if item is None:
            raise KeyError(f"unknown Local source: {source_id}")
        return item

    def source_location_disclosures(self, source_ids: list[str]) -> list[dict[str, Any]]:
        disclosures: list[dict[str, Any]] = []
        for source_id in dict.fromkeys(source_ids):
            root = self.repository.source_root(source_id)
            if root is None or self.repository.source(source_id) is None:
                raise KeyError(f"unknown Local source: {source_id}")
            available = root.is_dir()
            disclosures.append(
                {
                    "source_id": source_id,
                    "absolute_path": str(root.absolute()),
                    "available": available,
                    "readable": available and os.access(root, os.R_OK),
                    "writable": available and os.access(root, os.W_OK),
                }
            )
        return disclosures

    def storage_layout_disclosure(self) -> dict[str, Any]:
        """Disclose the canonical product boundaries only to the protected Local UI."""

        canonical = (
            self.local_data_root is not None
            and self.local_data_root.parent == self.working_directory_root
            and self.storage.root == self.working_directory_root / "workspace"
        )
        return {
            "layout": "working_directory" if canonical else "legacy_workspace",
            "working_directory": str(self.working_directory_root),
            "workspace": str(self.storage.root),
            "local_data": str(self.local_data_root or self.storage.root / "Principia Local Data"),
            "principles": str(self.principles_export_root),
            "raw_data_removable": canonical,
        }

    def reveal_storage_path(self, target: str) -> dict[str, Any]:
        paths = {
            "working_directory": self.working_directory_root,
            "workspace": self.storage.root,
            "local_data": self.local_data_root,
            "principles": self.principles_export_root,
        }
        path = paths.get(target)
        if path is None:
            raise KeyError("unknown storage-layout target")
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        if sys.platform == "darwin":
            command = ["open", str(path)]
        elif sys.platform == "win32":
            command = ["explorer", str(path)]
        elif shutil.which("xdg-open"):
            command = ["xdg-open", str(path)]
        else:
            raise RuntimeError("Open Folder is unavailable on this system")
        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"target": target, "revealed": True}

    def index_source(self, source_id: str) -> JobRecord:
        return self.sources.index(source_id)

    def start_source_index(self, source_id: str) -> JobRecord:
        job = self.sources.index(source_id, defer=True)
        self._futures[job.job_id] = self._executor.submit(self.sources.run_index, job.job_id)
        return job

    def source_documents(self, source_id: str, **kwargs: Any) -> dict[str, Any]:
        if self.repository.source(source_id) is None:
            raise KeyError(f"unknown Local source: {source_id}")
        return self.repository.source_documents(source_id, **kwargs)

    def reveal_source(self, source_id: str) -> dict[str, Any]:
        return self.sources.reveal(source_id)

    def start_literature_acquisition(
        self,
        *,
        search_id: str,
        source_id: str | None = None,
        folder_name: str | None = None,
        work_ids: list[str] | None = None,
        **kwargs: Any,
    ) -> JobRecord:
        """Acquire into an existing source (compatibility) or a new managed folder.

        The product UI uses ``folder_name`` so every public-literature dataset
        becomes a distinct, visible child of the working directory's
        ``local_data/`` boundary.  Supplying an existing source remains
        available for the v1.4 Python/CLI compatibility surface.
        """

        if bool(source_id) == bool(folder_name):
            raise ValueError("provide exactly one of source_id or folder_name")
        if folder_name:
            # Validate before creating a visible folder so a stale or empty
            # selection cannot leave an orphan directory behind.
            self.acquisition.validate_selection(search_id, work_ids)
            created = self.create_managed_source(name=folder_name)
            source_id = str(created["source_id"])
        assert source_id is not None
        return self.acquisition.start(
            search_id=search_id,
            source_id=source_id,
            work_ids=work_ids,
            **kwargs,
        )

    def start_extraction(self, **kwargs: Any) -> JobRecord:
        return self.extraction.start(**kwargs)

    def search_papers(
        self, query: str, *, area: str = "", target_count: int = 20, timeout: float = 120.0
    ) -> dict[str, Any]:
        if self.literature is None:
            raise RuntimeError("literature search is unavailable in this embedded runtime")
        return self.literature.search_papers(
            query, area=area, target_count=target_count, timeout=timeout
        )

    def start_literature_search(
        self,
        query: str,
        *,
        target_count: int = 20,
        deadline_seconds: int = 120,
        semantic_ranking: bool = True,
        source_id: str = "",
    ) -> JobRecord:
        if self.literature is None:
            raise RuntimeError("literature search is unavailable in this embedded runtime")
        normalized = " ".join(query.split())
        if len(normalized) < 8:
            raise ValueError("literature search requires a specific research question")
        target = max(1, min(int(target_count), 50))
        if source_id and self.repository.source(source_id) is None:
            raise KeyError(f"unknown Local source: {source_id}")
        excluded_work_ids = self.repository.source_work_ids(source_id) if source_id else set()
        deadline = max(30, min(int(deadline_seconds), 120))
        search_id = f"search:{monotonic_ulid()}"
        job = JobRecord(
            job_id=f"job:{monotonic_ulid()}",
            kind="literature_search",
            state="queued",
            stage="Query preparation",
            progress=0,
            total_units=0,
            last_activity_at=utc_now(),
            status_message="Preparing a deterministic literature query",
            checkpoint={
                "search_id": search_id,
                "query": normalized,
                "target_count": target,
                "deadline_seconds": deadline,
                "semantic_ranking": semantic_ranking,
                "source_id": source_id,
                "excluded_work_count": len(excluded_work_ids),
                "control_state": "running",
            },
            result={
                "search_id": search_id,
                "provisional_results": [],
                "provisional_count": 0,
                "selection_finalized": False,
            },
        )
        placeholder = {
            "search_id": search_id,
            "job_id": job.job_id,
            "query": normalized,
            "goal": normalized,
            "area": "",
            "target_count": target,
            "source_id": source_id,
            "state": "queued",
            "sources": [],
            "unavailable_sources": [],
            "results": [],
            "selected_work_ids": [],
            "alternate_work_ids": [],
            "pool_count": 0,
            "selection_finalized": False,
            "result_revision": 0,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
        }
        self.repository.save_job(job)
        self.repository.save_literature_search(placeholder, create_goal=False)
        self.repository.save_literature_search_task(
            search_id=search_id,
            job_id=job.job_id,
            query=normalized,
            target_count=target,
            deadline_seconds=deadline,
            state="queued",
            checkpoint={"provider_reports_completed": 0},
        )
        self.repository.append_job_event(
            job.job_id,
            "queued",
            {"stage": job.stage, "message": job.status_message},
            event_id=event_id(),
        )
        token = RunControlToken()
        deadline_hit = threading.Event()
        self._search_tokens[job.job_id] = token
        self._search_deadlines[job.job_id] = deadline_hit
        self._futures[job.job_id] = self._executor.submit(
            self._run_literature_search,
            job,
            normalized,
            target,
            deadline,
            semantic_ranking,
            excluded_work_ids,
            token,
            deadline_hit,
        )
        return job

    def _run_literature_search(
        self,
        job: JobRecord,
        query: str,
        target_count: int,
        deadline_seconds: int,
        semantic_ranking: bool,
        excluded_work_ids: set[str],
        token: RunControlToken,
        deadline_hit: threading.Event,
    ) -> None:
        literature = self.literature
        if literature is None:
            raise RuntimeError("literature search is unavailable in this embedded runtime")
        search_id = str((job.checkpoint or {}).get("search_id") or "")
        if not search_id:
            raise RuntimeError("literature search job has no search identifier")
        started = time.monotonic()
        provisional: dict[str, dict[str, Any]] = {}

        def stop_at_deadline() -> None:
            deadline_hit.set()
            token.cancel()

        timer = threading.Timer(deadline_seconds, stop_at_deadline)
        timer.daemon = True
        timer.start()

        def persist_job(stage: str, message: str, progress: float) -> None:
            job.state = "running"
            job.stage = stage
            job.progress = max(job.progress, min(0.99, progress))
            job.elapsed_seconds = round(time.monotonic() - started, 1)
            job.last_activity_at = utc_now()
            job.updated_at = job.last_activity_at
            job.status_message = message
            if job.completed_units >= 3 and job.total_units > job.completed_units:
                per_unit = job.elapsed_seconds / max(1, job.completed_units)
                job.eta_seconds = round(per_unit * (job.total_units - job.completed_units), 1)
            else:
                job.eta_seconds = None
            self.repository.save_job(job)
            self.repository.append_job_event(
                job.job_id,
                "progress",
                {
                    "stage": stage,
                    "message": message,
                    "progress": job.progress,
                    "completed_units": job.completed_units,
                    "total_units": job.total_units,
                    "elapsed_seconds": job.elapsed_seconds,
                    "eta_seconds": job.eta_seconds,
                    "retry_after_seconds": job.retry_after_seconds,
                    "provisional_count": len(provisional),
                },
                event_id=event_id(),
            )

        def on_progress(stage: str, payload: dict[str, Any]) -> None:
            if stage == "query_planning":
                persist_job("Query preparation", "Preparing source-specific queries", 0.05)
                return
            if stage == "source_search":
                report = payload.get("source_report") or {}
                query_count = int(payload.get("query_count") or 0)
                sources = list(payload.get("sources") or [])
                if query_count and sources:
                    job.total_units = query_count * len(sources)
                if report:
                    job.completed_units += 1
                    job.retry_after_seconds = report.get("retry_after_seconds")
                    self.repository.save_literature_search_attempt(
                        {
                            "attempt_id": event_id("attempt"),
                            "search_id": search_id,
                            "job_id": job.job_id,
                            "provider": report.get("source", ""),
                            "query_key": hashlib.sha256(
                                str(report.get("query") or "").encode()
                            ).hexdigest()[:24],
                            "status": report.get("status", ""),
                            "result_count": report.get("returned_count", 0),
                            "retry_after_seconds": report.get("retry_after_seconds"),
                            "latency_ms": int(report.get("latency_ms") or 0),
                            "error_category": report.get("error_type", ""),
                            "started_at": utc_now(),
                            "completed_at": utc_now(),
                        }
                    )
                for raw in payload.get("provisional_results") or []:
                    try:
                        saved = self.storage.save_work(coerce_work(raw))
                    except (TypeError, ValueError):
                        continue
                    projection = literature.search_service._work_projection(saved, rank=0)
                    provisional[saved.id] = projection
                ranked = [
                    item
                    for item in rank_literature_for_goal(query, list(provisional.values()))
                    if str(item.get("work_id") or "") not in excluded_work_ids
                ]
                for rank, item in enumerate(ranked, start=1):
                    item["rank"] = rank
                if job.result is not None:
                    job.result["provisional_results"] = ranked[: target_count + 10]
                    job.result["provisional_count"] = len(ranked)
                total = max(job.total_units, job.completed_units, 1)
                progress = 0.1 + 0.55 * job.completed_units / total
                provider = str(report.get("source") or payload.get("last_source") or "source")
                message = f"Received {len(ranked)} provisional papers; checked {provider}"
                if report.get("status") == "failed":
                    message = f"{provider} is unavailable; keeping results from other sources"
                # Publish the durable job stage before exposing provisional
                # results so clients never observe papers paired with a stale
                # "Query preparation" status.
                persist_job("Searching sources", message, progress)
                search_payload = self.repository.literature_search(search_id) or {}
                search_payload.update(
                    {
                        "state": "searching",
                        "results": ranked[: target_count + 10],
                        "pool_count": len(ranked),
                        "selection_finalized": False,
                        "updated_at": utc_now(),
                    }
                )
                self.repository.save_literature_search(search_payload, create_goal=False)
                revision = self.repository.save_literature_search_revision(
                    search_id, search_payload, state="searching"
                )
                search_payload["result_revision"] = revision
                self.repository.save_literature_search(search_payload, create_goal=False)
                return
            if stage == "dedupe":
                persist_job("Deduplicating", "Merging duplicate scholarly records", 0.72)
                return
            if stage == "ranking":
                persist_job("Ranking", "Ranking the most relevant papers", 0.84)
                return
            if stage == "saving":
                persist_job("Saving", "Saving the ranked paper preview", 0.96)

        try:
            embedding_client = None
            if semantic_ranking:
                profile = self.provider_profile("siliconflow")
                key = self.credentials.api_key("siliconflow")
                if key:
                    embedding_client = SiliconFlowEmbeddingClient(
                        api_key=key,
                        base_url=profile.base_url,
                        timeout=25.0,
                        max_retries=1,
                    )
            final = literature.search_service.search(
                query,
                area="",
                target_count=target_count,
                timeout=float(deadline_seconds),
                search_id=search_id,
                progress_callback=on_progress,
                cancel_token=token,
                embedding_client=embedding_client,
                excluded_work_ids=excluded_work_ids,
            )
            ranked_new = [
                item
                for item in final["results"]
                if str(item.get("work_id") or "") not in excluded_work_ids
            ]
            final["results"] = ranked_new[: target_count + 10]
            final["selected_work_ids"] = [
                str(item["work_id"]) for item in ranked_new[:target_count]
            ]
            final["alternate_work_ids"] = [
                str(item["work_id"]) for item in ranked_new[target_count : target_count + 10]
            ]
            final["excluded_existing_count"] = len(excluded_work_ids)
            final["job_id"] = job.job_id
            final["selection_finalized"] = True
            final["updated_at"] = utc_now()
            revision = self.repository.save_literature_search_revision(
                search_id, final, state=final["state"]
            )
            final["result_revision"] = revision
            self.repository.save_literature_search(final, create_goal=False)
            job.state = "succeeded"
            job.stage = "Ready"
            job.progress = 1.0
            job.completed_units = max(job.completed_units, job.total_units)
            job.eta_seconds = 0
            job.status_message = f"{len(final['selected_work_ids'])} papers are ready to review"
            job.result = {
                "search_id": final["search_id"],
                "selected_count": len(final["selected_work_ids"]),
                "alternate_count": len(final["alternate_work_ids"]),
                "provisional_count": len(final["results"]),
                "selection_finalized": True,
            }
        except (RunCancelledError, KeyboardInterrupt):
            if deadline_hit.is_set() and provisional:
                ranked = [
                    item
                    for item in rank_literature_for_goal(query, list(provisional.values()))
                    if str(item.get("work_id") or "") not in excluded_work_ids
                ]
                selected = [str(item["work_id"]) for item in ranked[:target_count]]
                partial = self.repository.literature_search(search_id) or {}
                partial.update(
                    {
                        "state": "degraded",
                        "results": ranked[: target_count + 10],
                        "selected_work_ids": selected,
                        "alternate_work_ids": [
                            str(item["work_id"])
                            for item in ranked[target_count : target_count + 10]
                        ],
                        "pool_count": len(ranked),
                        "selection_finalized": True,
                        "degraded_reason": "The 120-second interactive deadline was reached.",
                        "updated_at": utc_now(),
                    }
                )
                revision = self.repository.save_literature_search_revision(
                    search_id, partial, state="degraded"
                )
                partial["result_revision"] = revision
                self.repository.save_literature_search(partial, create_goal=False)
                job.state = "succeeded"
                job.stage = "Ready with partial results"
                job.progress = 1.0
                job.eta_seconds = 0
                job.status_message = f"{len(selected)} papers are ready; some sources timed out"
                job.result = {
                    "search_id": partial["search_id"],
                    "selected_count": len(selected),
                    "alternate_count": len(partial["alternate_work_ids"]),
                    "provisional_count": len(ranked),
                    "selection_finalized": True,
                    "degraded": True,
                }
            else:
                job.state = "cancelled"
                job.stage = "Cancelled"
                job.status_message = "Literature search was cancelled"
                job.eta_seconds = None
        except Exception as exc:
            job.state = "failed"
            job.stage = "Could not complete search"
            job.status_message = "Literature search could not be completed"
            job.error = {
                "code": "literature_search_failed",
                "category": "provider" if provisional else "network",
                "message": "Public literature providers did not complete the search.",
                "retryable": True,
                "technical_category": type(exc).__name__,
            }
        finally:
            timer.cancel()
            job.elapsed_seconds = round(time.monotonic() - started, 1)
            job.last_activity_at = utc_now()
            job.updated_at = job.last_activity_at
            self.repository.save_job(job)
            self.repository.append_job_event(
                job.job_id,
                "completed" if job.state == "succeeded" else job.state,
                {
                    "stage": job.stage,
                    "message": job.status_message,
                    "progress": job.progress,
                    "elapsed_seconds": job.elapsed_seconds,
                },
                event_id=event_id(),
            )

    def update_literature_selection(self, search_id: str, work_ids: list[str]) -> dict[str, Any]:
        if self.literature is None:
            raise RuntimeError("literature search is unavailable in this embedded runtime")
        return self.literature.update_selection(search_id, work_ids)

    def list_literature_searches(self) -> list[dict[str, Any]]:
        searches = self.repository.list_literature_searches()
        if self.literature is None:
            return searches
        return [
            self.literature.search_service.refresh_publication_metadata(item) for item in searches
        ]

    def literature_search(self, search_id: str) -> dict[str, Any] | None:
        payload = self.repository.literature_search(search_id)
        if payload is None or self.literature is None:
            return payload
        return self.literature.search_service.refresh_publication_metadata(payload)

    def start_literature_discovery(self, **kwargs: Any) -> JobRecord:
        if self.literature is None:
            raise RuntimeError("literature discovery is unavailable in this embedded runtime")
        return self.literature.start(**kwargs)

    def acquire_and_discover(
        self, search_id: str, *, policy: ModelPolicy, **kwargs: Any
    ) -> JobRecord:
        """Canonical Python API for an approved literature selection."""

        return self.start_literature_discovery(search_id=search_id, policy=policy, **kwargs)

    @staticmethod
    def picker_capability() -> dict[str, Any]:
        if sys.platform == "darwin":
            available = shutil.which("osascript") is not None
            provider = "macos"
        elif sys.platform == "win32":
            available = shutil.which("powershell") is not None
            provider = "windows"
        else:
            available = shutil.which("zenity") is not None
            provider = "zenity"
        return {"available": available, "provider": provider, "manual_path_fallback": True}

    @staticmethod
    def choose_folder() -> str:
        capability = LocalDiscoveryService.picker_capability()
        if not capability["available"]:
            raise RuntimeError("native folder picker is unavailable; use the manual path field")
        if sys.platform == "darwin":
            command = [
                "osascript",
                "-e",
                'POSIX path of (choose folder with prompt "Choose a private Principia source")',
            ]
        elif sys.platform == "win32":
            command = [
                "powershell",
                "-NoProfile",
                "-Command",
                "Add-Type -AssemblyName System.Windows.Forms; $d=New-Object "
                "System.Windows.Forms.FolderBrowserDialog; if($d.ShowDialog() -eq 'OK'){$d.SelectedPath}",
            ]
        else:
            command = [
                "zenity",
                "--file-selection",
                "--directory",
                "--title=Choose Principia source",
            ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
        if result.returncode != 0 or not result.stdout.strip():
            raise RuntimeError("folder selection was cancelled")
        return result.stdout.strip()

    @staticmethod
    def choose_folders() -> list[str]:
        """Choose one or more Local sources with the native system picker.

        macOS and Zenity support a true multi-select picker.  Windows' stock
        folder dialog returns one folder, so the same endpoint still returns a
        one-item list and the user can invoke it again.
        """

        capability = LocalDiscoveryService.picker_capability()
        if not capability["available"]:
            raise RuntimeError("native folder picker is unavailable; use the manual path field")
        if sys.platform == "darwin":
            script = """
set chosenFolders to choose folder with prompt "Choose one or more private Principia sources" with multiple selections allowed
set output to ""
repeat with chosenFolder in chosenFolders
    set output to output & POSIX path of chosenFolder & linefeed
end repeat
return output
""".strip()
            command = ["osascript", "-e", script]
        elif sys.platform == "win32":
            command = [
                "powershell",
                "-NoProfile",
                "-Command",
                "Add-Type -AssemblyName System.Windows.Forms; $d=New-Object "
                "System.Windows.Forms.FolderBrowserDialog; if($d.ShowDialog() -eq 'OK'){$d.SelectedPath}",
            ]
        else:
            command = [
                "zenity",
                "--file-selection",
                "--directory",
                "--multiple",
                "--separator=\n",
                "--title=Choose Principia sources",
            ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
        folders = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if result.returncode != 0 or not folders:
            raise RuntimeError("folder selection was cancelled")
        return folders

    def start(
        self,
        *,
        source_id: str,
        goal: str,
        area: str,
        policy: ModelPolicy,
        api_key: str | None = None,
        provider_transport: Any | None = None,
    ) -> JobRecord:
        index_job = self.sources.index(source_id)
        if index_job.state != "succeeded":
            raise RuntimeError("the Local source could not be indexed")
        source = self.repository.source(source_id)
        if source is None:
            raise KeyError(f"unknown Local source: {source_id}")
        return self.extraction.start(
            source_id=source_id,
            source_revision=int(source["revision"]),
            document_ids=[],
            selection_mode="all",
            goal=goal,
            area=area,
            policy=policy,
            limits=LiteratureRunLimits(),
            api_key=api_key,
            provider_transport=provider_transport,
        )

    def get(self, job_id: str) -> JobRecord | None:
        return self.repository.get_job(job_id)

    def cancel(self, job_id: str) -> JobRecord:
        job = self.repository.get_job(job_id)
        if job is None:
            raise KeyError(f"unknown job: {job_id}")
        if job.kind == "literature_discovery" and self.literature is not None:
            return self.literature.cancel(job_id)
        if job.kind == "literature_acquisition":
            return self.acquisition.cancel(job_id)
        if job.kind == "local_extraction":
            return self.extraction.cancel(job_id)
        if job.kind == "literature_search":
            if job.state in {"succeeded", "failed", "cancelled", "interrupted"}:
                return job
            job.state = "cancelling"
            job.stage = "Cancelling"
            job.status_message = "Stopping after the current provider response"
            job.updated_at = utc_now()
            self.repository.save_job(job)
            token = self._search_tokens.get(job_id)
            if token is not None:
                token.cancel()
            return job
        if job.state in {"succeeded", "failed", "cancelled", "interrupted"}:
            return job
        job.state = "cancelling"
        job.stage = "cancelling"
        job.updated_at = utc_now()
        self.repository.save_job(job)
        cancel = self._cancel.get(job_id)
        if cancel:
            cancel.set()
        return job

    def pause(self, job_id: str) -> JobRecord:
        job = self.repository.get_job(job_id)
        if job is None:
            raise KeyError(f"unknown job: {job_id}")
        if job.kind == "local_extraction":
            return self.extraction.pause(job_id)
        if job.kind == "literature_search":
            token = self._search_tokens.get(job_id)
            if token is None:
                raise ValueError("this literature search is not active in the current runtime")
            token.request_pause()
            if job.checkpoint is not None:
                job.checkpoint["control_state"] = "paused"
            job.status_message = "Paused before the next provider request"
            job.updated_at = utc_now()
            self.repository.save_job(job)
            return job
        if self.literature is None:
            raise RuntimeError("literature discovery is unavailable in this embedded runtime")
        return self.literature.pause(job_id)

    def continue_job(self, job_id: str) -> JobRecord:
        job = self.repository.get_job(job_id)
        if job is None:
            raise KeyError(f"unknown job: {job_id}")
        if job.kind == "local_extraction":
            return self.extraction.continue_job(job_id)
        if job.kind == "literature_search":
            token = self._search_tokens.get(job_id)
            if token is None:
                checkpoint = job.checkpoint or {}
                return self.start_literature_search(
                    str(checkpoint.get("query") or ""),
                    target_count=int(checkpoint.get("target_count") or 20),
                    deadline_seconds=int(checkpoint.get("deadline_seconds") or 120),
                )
            token.resume()
            if job.checkpoint is not None:
                job.checkpoint["control_state"] = "running"
            job.status_message = "Resuming public literature search"
            job.updated_at = utc_now()
            self.repository.save_job(job)
            return job
        if self.literature is None:
            raise RuntimeError("literature discovery is unavailable in this embedded runtime")
        return self.literature.continue_job(job_id)

    def retry_failed(self, job_id: str) -> JobRecord:
        job = self.repository.get_job(job_id)
        if job is None:
            raise KeyError(f"unknown job: {job_id}")
        if job.kind == "local_extraction":
            checkpoint = job.checkpoint or {}
            policy = ModelPolicy.model_validate(checkpoint.get("policy") or {"mode": "no_llm"})
            api_key = None
            retry_policy = policy
            if policy.mode == "remote" and policy.provider == "siliconflow":
                _, retry_policy, api_key = self.provider_configuration(
                    policy.provider,
                    policy.model,
                    egress_confirmed=policy.remote_egress_confirmed,
                )
            return self.extraction.retry_failed(job_id, api_key=api_key, policy=retry_policy)
        if job.kind == "literature_search":
            checkpoint = job.checkpoint or {}
            return self.start_literature_search(
                str(checkpoint.get("query") or ""),
                target_count=int(checkpoint.get("target_count") or 20),
                deadline_seconds=int(checkpoint.get("deadline_seconds") or 120),
            )
        if self.literature is None:
            raise RuntimeError("literature discovery is unavailable in this embedded runtime")
        return self.literature.retry_failed(job_id)


def policy_from_payload(payload: dict[str, Any]) -> ModelPolicy:
    return ModelPolicy.model_validate(json.loads(json.dumps(payload)))
