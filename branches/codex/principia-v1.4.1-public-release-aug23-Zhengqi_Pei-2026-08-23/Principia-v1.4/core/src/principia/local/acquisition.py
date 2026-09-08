from __future__ import annotations

import hashlib
import json
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from ..domain import JobRecord, canonical_sha256, event_id, monotonic_ulid
from ..models import WorkItem, utc_now
from ..persistence import V14WorkspaceRepository
from ..storage import WorkspaceStorage
from .literature import (
    SafeLiteratureAcquirer,
    open_access_locations,
    write_private_acquisition,
)
from .literature_discovery import _build_segments
from .sources import _atomic_private_write


class LiteratureAcquisitionService:
    """Acquire an approved metadata selection into a registered Local folder.

    This service performs no LLM calls and cannot create Candidate Principles.
    """

    def __init__(self, storage: WorkspaceStorage, repository: V14WorkspaceRepository) -> None:
        self.storage = storage
        self.repository = repository
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="principia-acquire")
        self._cancel: dict[str, threading.Event] = {}
        self._futures: dict[str, Future[None]] = {}

    def validate_selection(
        self, search_id: str, work_ids: list[str] | None
    ) -> tuple[dict[str, Any], list[str]]:
        search = self.repository.literature_search(search_id)
        if search is None:
            raise KeyError(f"unknown literature search: {search_id}")
        selected = list(dict.fromkeys(work_ids or search.get("selected_work_ids") or []))
        allowed = set(search.get("selected_work_ids") or []) | set(
            search.get("alternate_work_ids") or []
        )
        if not selected or not set(selected).issubset(allowed):
            raise ValueError("acquisition requires a non-empty selection from this search")
        return search, selected

    def start(
        self,
        *,
        search_id: str,
        source_id: str,
        work_ids: list[str] | None = None,
        transport: Any | None = None,
        resolver: Any | None = None,
    ) -> JobRecord:
        search, selected = self.validate_selection(search_id, work_ids)
        source = self.repository.source(source_id)
        root = self.repository.source_root(source_id)
        if source is None or root is None:
            raise KeyError(f"unknown Local source: {source_id}")
        existing_work_ids = self.repository.source_work_ids(source_id)
        selected = [work_id for work_id in selected if work_id not in existing_work_ids]
        if not selected:
            raise ValueError(
                "every selected paper is already in this private folder; choose new papers"
            )
        # Search remains metadata-only. The user's explicit acquisition is the
        # point at which its question becomes a durable Library collection.
        goal_id = self.repository.bind_research_goal_source(
            search_id=search_id, source_id=source_id
        )
        job = JobRecord(
            job_id=f"job:{monotonic_ulid()}",
            kind="literature_acquisition",
            state="queued",
            stage="queued",
            progress=0,
            total_units=len(selected),
            last_activity_at=utc_now(),
            status_message="Waiting to acquire the selected papers",
            checkpoint={
                "search_id": search_id,
                "source_id": source_id,
                "requested_work_ids": selected,
                "completed_work_ids": [],
                "source_revision": source["revision"],
                "goal_id": goal_id,
                "goal": search["goal"],
                "area": search["area"],
            },
            result={
                "requested_count": len(selected),
                "acquired_count": 0,
                "full_text_count": 0,
                "abstract_only_count": 0,
                "pdf_count": 0,
                "text_full_text_count": 0,
                "failed_count": 0,
                "items": [],
                "candidate_count": 0,
                "extraction_started": False,
            },
        )
        self.repository.save_job(job)
        self.repository.append_job_event(
            job.job_id,
            "queued",
            {"stage": job.stage, "message": job.status_message},
            event_id=event_id(),
        )
        cancel = threading.Event()
        self._cancel[job.job_id] = cancel
        self._futures[job.job_id] = self._executor.submit(
            self._run, job, search, source_id, selected, transport, resolver, cancel
        )
        return job

    def _run(
        self,
        job: JobRecord,
        search: dict[str, Any],
        source_id: str,
        work_ids: list[str],
        transport: Any | None,
        resolver: Any | None,
        cancel: threading.Event,
    ) -> None:
        started = time.monotonic()
        root = self.repository.source_root(source_id)
        source = self.repository.source(source_id)
        if root is None or source is None:
            return
        dataset_id = f"dataset:{monotonic_ulid()}"
        dataset = {
            "dataset_id": dataset_id,
            "search_id": search["search_id"],
            "source_id": source_id,
            "goal": search["goal"],
            "area": search["area"],
            "state": "acquiring",
            "label": "Local · Private Folder · Public Literature",
            "work_count": len(work_ids),
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }
        self.repository.save_dataset(dataset, storage_root=str(root))
        self.repository.replace_dataset_works(
            dataset_id,
            [
                {"work_id": work_id, "selected": True, "acquisition_status": "pending"}
                for work_id in work_ids
            ],
        )
        acquirer = SafeLiteratureAcquirer(transport=transport, resolver=resolver, timeout=60.0)
        dataset_bytes = 0
        completed: list[str] = []
        failed: list[dict[str, str]] = []
        items: list[dict[str, Any]] = []

        def content_counts() -> tuple[int, int, int, int]:
            full_text = sum(
                1
                for item in items
                if item.get("state") == "acquired" and item.get("content_kind") == "full_text"
            )
            abstract_only = sum(
                1
                for item in items
                if item.get("state") == "acquired" and item.get("content_kind") == "abstract"
            )
            pdfs = sum(
                1
                for item in items
                if item.get("state") == "acquired" and item.get("representation") == "pdf"
            )
            text_full_text = sum(
                1
                for item in items
                if item.get("state") == "acquired"
                and item.get("representation") == "full_text_text"
            )
            return full_text, abstract_only, pdfs, text_full_text

        def persist_progress(processed: int) -> None:
            full_text_count, abstract_only_count, pdf_count, text_full_text_count = content_counts()
            job.progress = min(0.99, processed / max(1, len(work_ids)))
            job.completed_units = processed
            job.total_units = len(work_ids)
            job.elapsed_seconds = round(time.monotonic() - started, 1)
            job.eta_seconds = (
                round(job.elapsed_seconds / processed * (len(work_ids) - processed), 1)
                if processed >= 2 and processed < len(work_ids)
                else None
            )
            job.last_activity_at = utc_now()
            job.status_message = (
                f"Prepared {len(completed)} of {len(work_ids)} selected documents "
                f"({full_text_count} full text, {abstract_only_count} abstract only)"
            )
            job.result = {
                "dataset_id": dataset_id,
                "source_id": source_id,
                "requested_count": len(work_ids),
                "acquired_count": len(completed),
                "full_text_count": full_text_count,
                "abstract_only_count": abstract_only_count,
                "pdf_count": pdf_count,
                "text_full_text_count": text_full_text_count,
                "failed_count": len(failed),
                "failures": list(failed),
                "items": list(items),
                "candidate_count": 0,
                "extraction_started": False,
            }
            job.updated_at = job.last_activity_at
            self.repository.save_job(job)
            self.repository.append_job_event(
                job.job_id,
                "progress",
                {
                    "stage": job.stage,
                    "message": job.status_message,
                    "progress": job.progress,
                    "completed_units": job.completed_units,
                    "total_units": job.total_units,
                    "eta_seconds": job.eta_seconds,
                },
                event_id=event_id(),
            )

        try:
            for index, work_id in enumerate(work_ids):
                if cancel.is_set():
                    raise InterruptedError
                job.state = "running"
                job.stage = "Acquire"
                job.status_message = f"Acquiring paper {index + 1} of {len(work_ids)}"
                job.progress = index / max(1, len(work_ids))
                job.updated_at = utc_now()
                self.repository.save_job(job)
                work = self.storage.get_work(work_id)
                if work is None:
                    failed.append({"work_id": work_id, "reason": "work_not_found"})
                    items.append(
                        {
                            "work_id": work_id,
                            "title": "Untitled work",
                            "state": "failed",
                            "reason": "work_not_found",
                        }
                    )
                    persist_progress(index + 1)
                    continue
                try:
                    acquired, location_id = self._acquire(
                        acquirer, work, dataset_bytes=dataset_bytes
                    )
                    dataset_bytes += int(acquired["byte_size"])
                    stem = f"{work.year or 'undated'}-{work.title}"
                    paths = write_private_acquisition(
                        root,
                        work_id=work.id,
                        acquired=acquired,
                        relative_stem=stem,
                        metadata={
                            "title": work.title,
                            "year": work.year,
                            "doi": work.doi,
                            "venue": work.venue,
                            "source": work.source,
                        },
                        derived_root=(
                            self.storage.root
                            / "source_cache"
                            / hashlib.sha256(source_id.encode()).hexdigest()[:24]
                        ),
                    )
                    acquisition_id = (
                        "acq:" + canonical_sha256({"dataset": dataset_id, "work": work.id})[:24]
                    )
                    representation = (
                        "pdf"
                        if acquired["mime_type"] == "application/pdf"
                        else "full_text_text"
                        if acquired["content_kind"] == "full_text"
                        else "abstract"
                    )
                    self.repository.save_acquisition(
                        {
                            "acquisition_id": acquisition_id,
                            "dataset_id": dataset_id,
                            "work_id": work.id,
                            "location_id": location_id,
                            "status": "usable",
                            "content_kind": acquired["content_kind"],
                            "representation": representation,
                            "final_url": acquired["final_url"],
                            "mime_type": acquired["mime_type"],
                            "byte_sha256": acquired["byte_sha256"],
                            "text_sha256": acquired["text_sha256"],
                            "byte_size": acquired["byte_size"],
                            "access_basis": acquired["access_basis"],
                            "manuscript_version": acquired["manuscript_version"],
                            "license": acquired["license"],
                            "private_paths": paths,
                            "created_at": utc_now(),
                        }
                    )
                    segments = _build_segments(work, acquisition_id, acquired["pages"])
                    self.repository.replace_segments(acquisition_id, work.id, segments)
                    document_id = (
                        "doc:" + hashlib.sha256(f"{source_id}:{work.id}".encode()).hexdigest()[:26]
                    )
                    self.repository.save_source_document(
                        {
                            "document_id": document_id,
                            "source_id": source_id,
                            "work_id": work.id,
                            "acquisition_id": acquisition_id,
                            "portable_relative_uri": paths["raw_relative_path"],
                            "content_sha256": acquired["byte_sha256"],
                            "content_byte_size": acquired["byte_size"],
                            "parse_status": "indexed",
                            "extraction_eligible": True,
                            "principle_count": 0,
                            "last_indexed_revision": int(source["revision"]) + 1,
                        }
                    )
                    self.repository.update_dataset_work_status(dataset_id, work.id, "usable")
                    completed.append(work.id)
                    items.append(
                        {
                            "work_id": work.id,
                            "title": work.title,
                            "state": "acquired",
                            "content_kind": acquired["content_kind"],
                            "representation": representation,
                            "access_basis": acquired["access_basis"],
                            "document_id": document_id,
                        }
                    )
                    if job.checkpoint is not None:
                        job.checkpoint["completed_work_ids"] = list(completed)
                except Exception as exc:  # noqa: BLE001
                    self.repository.update_dataset_work_status(dataset_id, work.id, "failed")
                    failed.append({"work_id": work.id, "reason": type(exc).__name__})
                    items.append(
                        {
                            "work_id": work.id,
                            "title": work.title,
                            "state": "failed",
                            "reason": type(exc).__name__,
                        }
                    )
                persist_progress(index + 1)
            with self.repository.connect() as conn:
                conn.execute(
                    "UPDATE research_datasets SET state=?, updated_at=? WHERE dataset_id=?",
                    ("ready" if completed else "failed", utc_now(), dataset_id),
                )
                conn.execute(
                    "UPDATE local_sources_v14 SET revision=revision+1, updated_at=? WHERE source_id=?",
                    (utc_now(), source_id),
                )
            manifest = {
                "schema_version": "principia-local-source-v1",
                "source_id": source_id,
                "display_name": source["display_name"],
                "display_location": source["display_location"],
                "updated_at": utc_now(),
                "documents": self.repository.source_documents(source_id, limit=100)["items"],
            }
            _atomic_private_write(
                root / "manifest.json",
                (
                    json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
                ).encode(),
            )
            job.state = "succeeded" if completed else "failed"
            job.stage = "Acquired" if completed else "failed"
            job.progress = 1.0
            job.completed_units = len(work_ids)
            job.eta_seconds = 0
            full_text_count, abstract_only_count, pdf_count, text_full_text_count = content_counts()
            job.status_message = (
                f"Prepared {len(completed)} documents: {full_text_count} full text, "
                f"{abstract_only_count} abstract only"
                if completed
                else "No selected document could be acquired"
            )
            job.result = {
                "dataset_id": dataset_id,
                "source_id": source_id,
                "requested_count": len(work_ids),
                "acquired_count": len(completed),
                "full_text_count": full_text_count,
                "abstract_only_count": abstract_only_count,
                "pdf_count": pdf_count,
                "text_full_text_count": text_full_text_count,
                "failed_count": len(failed),
                "failures": failed,
                "items": items,
                "candidate_count": 0,
                "extraction_started": False,
            }
            if not completed:
                job.error = {
                    "code": "literature_acquisition_failed",
                    "category": "provider",
                    "message": "No selected paper could be acquired.",
                    "retryable": True,
                }
        except InterruptedError:
            job.state = "cancelled"
            job.stage = "cancelled"
        except Exception as exc:  # noqa: BLE001
            job.state = "failed"
            job.stage = "failed"
            job.error = {
                "code": "literature_acquisition_failed",
                "category": "runtime",
                "message": str(exc),
                "retryable": True,
            }
        job.updated_at = utc_now()
        job.last_activity_at = job.updated_at
        job.elapsed_seconds = round(time.monotonic() - started, 1)
        self.repository.save_job(job)
        self.repository.append_job_event(
            job.job_id,
            job.state,
            {"completed": len(completed), "failed": len(failed)},
            event_id=event_id(),
        )

    def _acquire(
        self, acquirer: SafeLiteratureAcquirer, work: WorkItem, *, dataset_bytes: int
    ) -> tuple[dict[str, Any], str | None]:
        errors: list[str] = []
        for location in open_access_locations(work):
            location_id = self.repository.save_scholarly_location({**location, "work_id": work.id})
            try:
                acquired = acquirer.download(location, dataset_bytes=dataset_bytes)
                acquired["content_kind"] = "full_text"
                return acquired, location_id
            except Exception as exc:  # noqa: BLE001
                errors.append(type(exc).__name__)
        abstract = work.abstract.strip()
        if not abstract:
            raise ValueError("paper has neither permitted full text nor a usable abstract")
        body = abstract.encode()
        return (
            {
                "final_url": work.url if work.url.startswith("https://") else "",
                "mime_type": "text/plain",
                "bytes": body,
                "text": abstract,
                "pages": [{"page": None, "section": "abstract", "text": abstract}],
                "byte_size": len(body),
                "byte_sha256": hashlib.sha256(body).hexdigest(),
                "text_sha256": hashlib.sha256(body).hexdigest(),
                "access_basis": "provider_public_abstract",
                "manuscript_version": "abstract",
                "license": "metadata-provider-terms",
                "content_kind": "abstract",
                "full_text_failures": errors,
            },
            None,
        )

    def cancel(self, job_id: str) -> JobRecord:
        job = self.repository.get_job(job_id)
        if job is None or job.kind != "literature_acquisition":
            raise KeyError(f"unknown acquisition job: {job_id}")
        if job.state not in {"succeeded", "failed", "cancelled", "interrupted"}:
            job.state = "cancelling"
            job.stage = "cancelling"
            job.updated_at = utc_now()
            self.repository.save_job(job)
            self._cancel.setdefault(job_id, threading.Event()).set()
        return job
