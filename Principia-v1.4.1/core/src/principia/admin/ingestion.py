from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import httpx

from ..cloud import (
    AdminCampaignRequest,
    AdminExtractRequest,
    AdminStagedItem,
    BulkStagingDecisionRequest,
    CloudSync,
    GlobalCloudSnapshotStore,
    PrincipleRevision,
    PrincipleWorkLink,
    StagingDecisionRequest,
    WorkRevision,
)
from ..cloud.canonical import CanonicalCloudRepository, RecordKind, record_identity
from ..domain import (
    ChallengeDecisionBatch,
    EvidenceClaimAtomBatch,
    JobRecord,
    ScientificArgumentBatch,
    canonical_sha256,
    concise_principle_title,
    event_id,
    monotonic_ulid,
    principle_id,
)
from ..local.literature import SafeLiteratureAcquirer, open_access_locations
from ..local.quality import ScientificQualityGate, stable_atom_id
from ..models import WorkItem, utc_now
from ..persistence import V14WorkspaceRepository
from ..providers import (
    ModelPolicy,
    OpenAICompatibleProvider,
    ProviderOutputError,
    ProviderRequestError,
)
from .github import GitHubPublicationAdapter

_TERMINAL_UNIT_STATES = {
    "staged",
    "acquisition_failed",
    "provider_failed",
    "validation_quarantined",
    "cleanup_failed",
    "cancelled",
}


def _diff(current: dict[str, Any], proposed: dict[str, Any]) -> dict[str, Any]:
    return {
        key: {"current": current.get(key), "proposed": proposed.get(key)}
        for key in sorted(set(current) | set(proposed))
        if current.get(key) != proposed.get(key)
    }


class AdminCampaignService:
    """Admin-only discovery, ephemeral extraction, comparison and publication staging."""

    def __init__(
        self,
        repository: V14WorkspaceRepository,
        local: Any,
        global_cloud: GlobalCloudSnapshotStore,
        workspace_root: Path,
    ) -> None:
        self.repository = repository
        self.local = local
        self.global_cloud = global_cloud
        self.temp_root = Path(workspace_root).resolve() / ".principia" / "admin" / "tmp"
        self.temp_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.temp_root, 0o700)
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="principia-admin")
        self._controls: dict[str, dict[str, threading.Event]] = {}
        self._usage_lock = threading.Lock()
        self.sweep_receipt = self.sweep_orphaned_temp()

    def _campaign_row(self, campaign_id: str) -> dict[str, Any] | None:
        with self.repository.connect() as conn:
            row = conn.execute(
                "SELECT * FROM admin_campaigns WHERE campaign_id=?", (campaign_id,)
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["payload_json"])
        payload.update(
            {
                "campaign_id": row["campaign_id"],
                "search_id": row["search_id"] or "",
                "job_id": row["job_id"] or "",
                "state": row["state"],
                "base_release_id": row["base_release_id"],
                "base_commit_sha": row["base_commit_sha"],
                "base_manifest_digest": row["base_manifest_digest"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )
        job_id = str(row["job_id"] or "")
        if job_id:
            job = self.repository.get_job(job_id)
            if job is not None:
                payload["extraction"] = {
                    **dict(payload.get("extraction") or {}),
                    "job_id": job_id,
                    "state": job.state,
                    "stage": job.stage,
                    "progress": job.progress,
                    "completed_units": job.completed_units,
                    "total_units": job.total_units,
                    "status_message": job.status_message,
                    "elapsed_seconds": job.elapsed_seconds,
                    "eta_seconds": job.eta_seconds,
                }
        return payload

    def create(self, request: AdminCampaignRequest) -> dict[str, Any]:
        status = self.global_cloud.status()
        campaign_id = f"campaign:{monotonic_ulid()}"
        now = utc_now()
        payload = {
            "schema_version": "admin-campaign-v1",
            "research_goal": request.research_goal,
            "target_count": request.target_count,
            "provider_profile_id": request.provider_profile_id,
            "model": request.model,
            "concurrency": request.concurrency,
            "discovery": {"state": "queued", "result_count": 0, "degraded_sources": []},
            "extraction": {"state": "not_started", "job_id": ""},
        }
        with self.repository.connect() as conn:
            conn.execute(
                "INSERT INTO admin_campaigns VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    campaign_id,
                    None,
                    None,
                    "discovering",
                    request.research_goal,
                    request.target_count,
                    status.get("release_id") or "",
                    status.get("commit_sha") or "",
                    status.get("content_digest") or "",
                    request.model_dump_json(),
                    json.dumps(payload, sort_keys=True),
                    now,
                    now,
                ),
            )
        self._executor.submit(self._discover, campaign_id, request)
        return self._campaign_row(campaign_id) or {}

    def _discover(self, campaign_id: str, request: AdminCampaignRequest) -> None:
        gathered: dict[str, dict[str, Any]] = {}
        rounds = max(1, min(400, (request.target_count + 49) // 50))
        degraded: list[str] = []
        for round_index in range(rounds):
            if len(gathered) >= request.target_count:
                break
            query = (
                request.research_goal
                if round_index == 0
                else f"{request.research_goal} research {round_index + 1}"
            )
            try:
                page = self.local.search_papers(query, target_count=50, timeout=120)
                for item in page.get("results") or []:
                    gathered.setdefault(str(item["work_id"]), item)
            except Exception as exc:
                degraded.append(type(exc).__name__)
                if not gathered:
                    continue
        works = list(gathered.values())[: request.target_count]
        with self.repository.connect() as conn:
            for rank, work in enumerate(works, start=1):
                proposed = self._work_revision(work)
                match = self.global_cloud.match_work(proposed)
                current = match.get("match") or {}
                availability = proposed["availability"]["status"]
                conn.execute(
                    """
                    INSERT OR REPLACE INTO admin_campaign_works(
                        campaign_id, work_id, rank, selected, state, availability_status,
                        cloud_match_id, cloud_revision, cloud_digest, match_kind,
                        metadata_json, checkpoint_json, error_json, temp_deleted_at
                    ) VALUES (?, ?, ?, 0, 'discovered', ?, ?, ?, ?, ?, ?, '{}', NULL, '')
                    """,
                    (
                        campaign_id,
                        work["work_id"],
                        rank,
                        availability,
                        current.get("work_id") or "",
                        current.get("revision"),
                        current.get("content_digest") or "",
                        match["kind"],
                        json.dumps({**work, "cloud_match_reason": match["reason"]}, sort_keys=True),
                    ),
                )
            row = conn.execute(
                "SELECT payload_json FROM admin_campaigns WHERE campaign_id=?", (campaign_id,)
            ).fetchone()
            payload = json.loads(row[0])
            payload["discovery"] = {
                "state": "ready" if works and not degraded else "degraded" if works else "failed",
                "result_count": len(works),
                "degraded_sources": sorted(set(degraded)),
            }
            state = "discovery_degraded" if degraded else "discovery_ready"
            if not works:
                state = "failed"
            conn.execute(
                "UPDATE admin_campaigns SET state=?, payload_json=?, updated_at=? WHERE campaign_id=?",
                (state, json.dumps(payload, sort_keys=True), utc_now(), campaign_id),
            )

    @staticmethod
    def _work_revision(work: dict[str, Any]) -> dict[str, Any]:
        oa = list(work.get("oa_locations") or [])
        available = bool(oa)
        payload = WorkRevision(
            work_id=str(work["work_id"]),
            revision=1,
            title=str(work["title"]),
            abstract=str(work.get("abstract") or ""),
            authors=list(work.get("authors") or []),
            institutions=list(work.get("institutions") or []),
            venue=str(work.get("venue") or ""),
            year=work.get("year"),
            doi=str(work.get("doi") or ""),
            arxiv_id=str(work.get("arxiv_id") or ""),
            pmid=str(work.get("pmid") or ""),
            openalex_id=str(work.get("openalex_id") or ""),
            semantic_scholar_id=str(work.get("semantic_scholar_id") or ""),
            landing_url=str(work.get("url") or "")
            if str(work.get("url") or "").startswith("https://")
            else "",
            source_urls=[
                url for url in work.get("source_urls") or [] if str(url).startswith("https://")
            ],
            availability={
                "status": "available" if available else "unknown",
                "full_text_url": str(oa[0].get("url") or "") if oa else "",
                "license": str(oa[0].get("license") or "") if oa else "",
                "basis": str(oa[0].get("access_basis") or "") if oa else "",
            },
            citation_count=work.get("citation_count"),
        ).model_dump(mode="json")
        payload["content_digest"] = canonical_sha256(
            {key: value for key, value in payload.items() if key != "content_digest"}
        )
        return payload

    def list_campaigns(self) -> list[dict[str, Any]]:
        with self.repository.connect() as conn:
            ids = [
                str(row[0])
                for row in conn.execute(
                    "SELECT campaign_id FROM admin_campaigns ORDER BY updated_at DESC"
                )
            ]
        return [item for identifier in ids if (item := self._campaign_row(identifier))]

    def papers(
        self,
        campaign_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
        selected: bool | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        venue: str = "",
        author: str = "",
        institution: str = "",
        publication_status: str = "",
        full_text_status: str = "",
        page_min: int | None = None,
        page_max: int | None = None,
        pdf_bytes_min: int | None = None,
        pdf_bytes_max: int | None = None,
        source: str = "",
        cloud_presence: str = "",
    ) -> dict[str, Any]:
        clauses = ["campaign_id=?"]
        values: list[Any] = [campaign_id]
        if selected is not None:
            clauses.append("selected=?")
            values.append(int(selected))
        if year_from is not None:
            clauses.append("CAST(json_extract(metadata_json,'$.year') AS INTEGER)>=?")
            values.append(year_from)
        if year_to is not None:
            clauses.append("CAST(json_extract(metadata_json,'$.year') AS INTEGER)<=?")
            values.append(year_to)
        if venue:
            clauses.append("json_extract(metadata_json,'$.venue')=?")
            values.append(venue)
        if author:
            clauses.append("json_extract(metadata_json,'$.authors') LIKE ?")
            values.append(f"%{author}%")
        if institution:
            clauses.append("json_extract(metadata_json,'$.institutions') LIKE ?")
            values.append(f"%{institution}%")
        if publication_status:
            clauses.append("json_extract(metadata_json,'$.publication_status')=?")
            values.append(publication_status)
        if full_text_status:
            clauses.append("availability_status=?")
            values.append(full_text_status)
        for field, low, high in (
            ("page_count", page_min, page_max),
            ("pdf_bytes", pdf_bytes_min, pdf_bytes_max),
        ):
            if low is not None:
                clauses.append(f"CAST(json_extract(metadata_json,'$.{field}') AS INTEGER)>=?")
                values.append(low)
            if high is not None:
                clauses.append(f"CAST(json_extract(metadata_json,'$.{field}') AS INTEGER)<=?")
                values.append(high)
        if source:
            clauses.append("json_extract(metadata_json,'$.source')=?")
            values.append(source)
        if cloud_presence:
            clauses.append("match_kind=?")
            values.append(cloud_presence)
        where = " AND ".join(clauses)
        with self.repository.connect() as conn:
            total = int(
                conn.execute(
                    f"SELECT COUNT(*) FROM admin_campaign_works WHERE {where}", values
                ).fetchone()[0]
            )
            rows = conn.execute(
                f"SELECT * FROM admin_campaign_works WHERE {where} ORDER BY rank, work_id LIMIT ? OFFSET ?",
                (*values, max(1, min(limit, 200)), max(0, offset)),
            ).fetchall()
        return {
            "items": [
                {
                    **json.loads(row["metadata_json"]),
                    "selected": bool(row["selected"]),
                    "state": row["state"],
                    "error": json.loads(row["error_json"]) if row["error_json"] else None,
                    "availability_status": row["availability_status"],
                    "cloud_presence": row["match_kind"],
                    "cloud_match_id": row["cloud_match_id"],
                }
                for row in rows
            ],
            "total": total,
        }

    def select(self, campaign_id: str, work_ids: list[str]) -> dict[str, Any]:
        if self._campaign_row(campaign_id) is None:
            raise KeyError(campaign_id)
        with self.repository.connect() as conn:
            conn.execute(
                "UPDATE admin_campaign_works SET selected=0 WHERE campaign_id=?", (campaign_id,)
            )
            if work_ids:
                placeholders = ",".join("?" for _ in work_ids)
                found = int(
                    conn.execute(
                        f"SELECT COUNT(*) FROM admin_campaign_works WHERE campaign_id=? AND work_id IN ({placeholders})",
                        (campaign_id, *work_ids),
                    ).fetchone()[0]
                )
                if found != len(set(work_ids)):
                    raise ValueError("selection contains an unknown campaign Work")
                conn.execute(
                    f"UPDATE admin_campaign_works SET selected=1 WHERE campaign_id=? AND work_id IN ({placeholders})",
                    (campaign_id, *work_ids),
                )
        return {"campaign_id": campaign_id, "selected_count": len(set(work_ids))}

    def extract(self, campaign_id: str, request: AdminExtractRequest) -> dict[str, Any]:
        campaign = self._campaign_row(campaign_id)
        if campaign is None:
            raise KeyError(campaign_id)
        with self.repository.connect() as conn:
            rows = conn.execute(
                "SELECT work_id FROM admin_campaign_works WHERE campaign_id=? AND selected=1 "
                "AND state NOT IN ('staged') ORDER BY rank",
                (campaign_id,),
            ).fetchall()
        work_ids = [str(row[0]) for row in rows]
        if len(work_ids) < 4 and not request.retry:
            raise ValueError("a new Admin extraction requires at least four selected papers")
        if not work_ids:
            raise ValueError("no selected papers remain to extract")
        if not request.egress_confirmed:
            raise ValueError("Admin LLM extraction requires explicit remote-egress confirmation")
        connection = self.local.test_provider_connection(campaign["provider_profile_id"])
        if not bool(connection.get("ok")):
            category = str(connection.get("category") or "provider_unavailable")
            guidance = {
                "authentication": "the saved API key was rejected; save a valid key and test it",
                "rate_limited": "the provider is rate-limiting requests; wait briefly and retry",
                "timeout": "the provider connection timed out; test it again when reachable",
                "network": "the provider could not be reached; check the network and retry",
            }.get(category, "the provider is unavailable; test the connection and retry")
            raise ValueError(f"Extraction did not start: {guidance}")
        _, policy, api_key = self.local.provider_configuration(
            campaign["provider_profile_id"], campaign["model"], egress_confirmed=True
        )
        job = JobRecord(
            job_id=f"job:{monotonic_ulid()}",
            kind="admin_extraction",
            state="queued",
            stage="queued",
            progress=0,
            provider=policy.provider,
            model=policy.model,
            total_units=len(work_ids),
            checkpoint={"campaign_id": campaign_id, "work_ids": work_ids},
            status_message="Queued for four-wide Admin extraction",
        )
        self.repository.save_job(job)
        control = {"pause": threading.Event(), "cancel": threading.Event()}
        self._controls[job.job_id] = control
        with self.repository.connect() as conn:
            for ordinal, work_id in enumerate(work_ids):
                self.repository.save_job_unit(
                    {
                        "unit_id": self._unit_id(job.job_id, work_id),
                        "job_id": job.job_id,
                        "work_id": work_id,
                        "ordinal": ordinal,
                        "state": "queued",
                        "attempt_count": 0,
                        "checkpoint": {
                            "campaign_id": campaign_id,
                            "stage": "queued",
                            "temp_deleted": False,
                        },
                    }
                )
            placeholders = ",".join("?" for _ in work_ids)
            conn.execute(
                f"UPDATE admin_campaign_works SET state='queued', error_json=NULL "
                f"WHERE campaign_id=? AND work_id IN ({placeholders})",
                (campaign_id, *work_ids),
            )
            payload = campaign
            payload["extraction"] = {"state": "queued", "job_id": job.job_id}
            conn.execute(
                "UPDATE admin_campaigns SET state='extracting', job_id=?, payload_json=?, updated_at=? WHERE campaign_id=?",
                (job.job_id, json.dumps(payload, sort_keys=True), utc_now(), campaign_id),
            )
        self._executor.submit(
            self._run_extract, campaign_id, job.job_id, work_ids, policy, api_key, control
        )
        return job.model_dump(mode="json")

    @staticmethod
    def _unit_id(job_id: str, work_id: str) -> str:
        return "unit:" + hashlib.sha256(f"{job_id}:{work_id}".encode()).hexdigest()[:26]

    def _run_extract(
        self,
        campaign_id: str,
        job_id: str,
        work_ids: list[str],
        policy: ModelPolicy,
        api_key: str,
        control: dict[str, threading.Event],
    ) -> None:
        job = self.repository.get_job(job_id)
        if job is None:
            return
        job.state = "running"
        job.stage = "dispatching"
        job.updated_at = utc_now()
        self.repository.save_job(job)
        campaign = self._campaign_row(campaign_id) or {}
        concurrency = max(4, min(8, int(campaign.get("concurrency") or 4)))
        started = time.monotonic()
        futures: dict[Future[dict[str, Any]], str] = {}
        with ThreadPoolExecutor(
            max_workers=concurrency, thread_name_prefix="principia-admin-paper"
        ) as pool:
            pending = iter(work_ids)
            exhausted = False
            while futures or not exhausted:
                while (
                    len(futures) < concurrency
                    and not exhausted
                    and not control["pause"].is_set()
                    and not control["cancel"].is_set()
                ):
                    try:
                        work_id = next(pending)
                    except StopIteration:
                        exhausted = True
                        break
                    futures[
                        pool.submit(
                            self._process_work, campaign_id, job_id, work_id, policy, api_key
                        )
                    ] = work_id
                    job.stage = "extracting"
                    job.status_message = (
                        f"{len(futures)} paper worker{'s' if len(futures) != 1 else ''} active"
                    )
                    job.updated_at = utc_now()
                    self.repository.save_job(job)
                if control["cancel"].is_set() and not futures:
                    break
                if control["pause"].is_set() and not futures:
                    job.state = "paused"
                    job.stage = "paused"
                    job.status_message = "Paused after active cleanup"
                    self.repository.save_job(job)
                    while control["pause"].is_set() and not control["cancel"].wait(0.2):
                        pass
                    if control["cancel"].is_set():
                        break
                    job.state = "running"
                    job.stage = "resuming"
                    self.repository.save_job(job)
                    continue
                if not futures:
                    time.sleep(0.05)
                    continue
                done = next(as_completed(list(futures)))
                work_id = futures.pop(done)
                try:
                    outcome = done.result()
                except Exception:
                    outcome = {
                        "state": "provider_failed",
                        "error": {
                            "category": "internal_worker_error",
                            "message": "The paper worker stopped unexpectedly; retry this paper.",
                        },
                    }
                job.completed_units += 1
                job.progress = job.completed_units / max(1, job.total_units)
                job.elapsed_seconds = round(time.monotonic() - started, 1)
                job.status_message = f"Completed {job.completed_units} of {job.total_units} papers"
                job.updated_at = utc_now()
                self.repository.save_job(job)
                self.repository.append_job_event(
                    job_id, "unit_complete", {"work_id": work_id, **outcome}, event_id=event_id()
                )
        if control["cancel"].is_set():
            with self.repository.connect() as conn:
                conn.execute(
                    "UPDATE admin_campaign_works SET state='cancelled' WHERE campaign_id=? "
                    "AND selected=1 AND state IN ('discovered','queued')",
                    (campaign_id,),
                )
            job.state = "cancelled"
            job.stage = "cancelled"
        else:
            with self.repository.connect() as conn:
                counts = dict(
                    conn.execute(
                        "SELECT state, COUNT(*) count FROM admin_campaign_works WHERE campaign_id=? AND selected=1 GROUP BY state",
                        (campaign_id,),
                    ).fetchall()
                )
            job.state = "succeeded" if int(counts.get("staged", 0)) else "failed"
            job.stage = "Review ready" if job.state == "succeeded" else "Needs attention"
            job.result = {"campaign_id": campaign_id, "states": counts}
        job.progress = 1
        job.updated_at = utc_now()
        self.repository.save_job(job)
        with self.repository.connect() as conn:
            conn.execute(
                "UPDATE admin_campaigns SET state=?, updated_at=? WHERE campaign_id=?",
                ("review_ready" if job.state == "succeeded" else job.state, utc_now(), campaign_id),
            )

    def _process_work(
        self,
        campaign_id: str,
        job_id: str,
        work_id: str,
        policy: ModelPolicy,
        api_key: str,
    ) -> dict[str, Any]:
        unit_id = self._unit_id(job_id, work_id)
        job_root = (self.temp_root / hashlib.sha256(job_id.encode()).hexdigest()[:24]).resolve()
        if self.temp_root not in job_root.parents:
            raise PermissionError("Admin temporary path escaped its allowlisted root")
        unit_root = job_root / hashlib.sha256(unit_id.encode()).hexdigest()[:24]
        unit_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(unit_root, 0o700)
        provider: OpenAICompatibleProvider | None = None
        cleanup_ok = False
        state = "provider_failed"
        error: dict[str, Any] | None = None
        acquired: dict[str, Any] | None = None
        phase = "acquisition"
        try:
            with self.repository.connect() as conn:
                row = conn.execute(
                    "SELECT metadata_json FROM admin_campaign_works WHERE campaign_id=? AND work_id=?",
                    (campaign_id, work_id),
                ).fetchone()
            if not row:
                raise KeyError(work_id)
            metadata = json.loads(row[0])
            work = WorkItem.model_validate(
                {
                    "id": work_id,
                    "title": metadata["title"],
                    "authors": metadata.get("authors") or [],
                    "abstract": metadata.get("abstract") or "",
                    "year": metadata.get("year"),
                    "venue": metadata.get("venue") or "",
                    "url": metadata.get("url") or "",
                    "doi": metadata.get("doi") or "",
                    "arxiv_id": metadata.get("arxiv_id") or "",
                    "openalex_id": metadata.get("openalex_id") or "",
                    "semantic_scholar_id": metadata.get("semantic_scholar_id") or "",
                    "pmid": metadata.get("pmid") or "",
                    "pdf_url": metadata.get("pdf_url") or "",
                    "source": metadata.get("source") or "",
                    "source_urls": metadata.get("source_urls") or [],
                    "citation_count": metadata.get("citation_count"),
                    "metadata": metadata.get("metadata") or {},
                }
            )
            locations = list(metadata.get("oa_locations") or open_access_locations(work))
            if not locations:
                raise FileNotFoundError("full text is unavailable; abstract fallback is forbidden")
            self._set_unit(job_id, unit_id, work_id, "downloading", campaign_id)
            acquirer = SafeLiteratureAcquirer()
            try:
                acquired = acquirer.download(locations[0])
            finally:
                acquirer.client.close()
            raw_path = unit_root / "source.bin"
            text_path = unit_root / "normalized.txt"
            raw_path.write_bytes(acquired["bytes"])
            text_path.write_text(acquired["text"], encoding="utf-8")
            os.chmod(raw_path, 0o600)
            os.chmod(text_path, 0o600)
            self._set_unit(job_id, unit_id, work_id, "parsing", campaign_id)
            segments = [
                {
                    "segment_key": f"{work_id}:page:{page.get('page') or index}",
                    "section": page.get("section") or "page",
                    "page_start": page.get("page"),
                    "text": page["text"],
                }
                for index, page in enumerate(acquired["pages"], start=1)
            ]
            phase = "provider"
            provider = OpenAICompatibleProvider(policy, api_key=api_key, timeout=120)
            self._set_unit(job_id, unit_id, work_id, "extracting", campaign_id)
            atoms_result = provider.extract_evidence_atoms(
                area="general",
                goal=(self._campaign_row(campaign_id) or {})["research_goal"],
                source_records=[
                    {"source_key": "source:0", "work_id": work_id, "title": work.title}
                ],
                evidence_segments=segments,
            )
            self._record_provider_trace(job_id, unit_id, atoms_result.trace)
            atoms_batch = EvidenceClaimAtomBatch.model_validate(atoms_result.value)
            atoms = [
                atom.model_copy(
                    update={
                        "atom_id": stable_atom_id(
                            work_id=work_id,
                            source_key=atom.source_key,
                            faithful_claim=atom.faithful_claim,
                        )
                    }
                )
                for atom in atoms_batch.atoms
            ]
            gate = ScientificQualityGate()
            failures = gate.validate_atoms(
                atoms,
                segment_text={item["segment_key"]: item["text"] for item in segments},
                permitted_source_keys={"source:0"},
            )
            atoms = [atom for atom in atoms if atom.atom_id not in failures]
            arguments_result = provider.normalize_scientific_arguments(
                area="general",
                goal=(self._campaign_row(campaign_id) or {})["research_goal"],
                atoms=[atom.model_dump(mode="json") for atom in atoms],
            )
            self._record_provider_trace(job_id, unit_id, arguments_result.trace)
            arguments = ScientificArgumentBatch.model_validate(arguments_result.value)
            self._set_unit(job_id, unit_id, work_id, "challenging", campaign_id)
            challenge_result = provider.challenge_scientific_arguments(
                area="general",
                goal=(self._campaign_row(campaign_id) or {})["research_goal"],
                atoms=[atom.model_dump(mode="json") for atom in atoms],
                arguments=[argument.model_dump(mode="json") for argument in arguments.arguments],
            )
            self._record_provider_trace(job_id, unit_id, challenge_result.trace)
            challenges = ChallengeDecisionBatch.model_validate(challenge_result.value)
            decisions = {item.argument_index: item for item in challenges.decisions}
            self._set_unit(job_id, unit_id, work_id, "validating", campaign_id)
            valid = []
            for index, argument in enumerate(arguments.arguments):
                reasons = gate.validate_argument(
                    argument,
                    atoms=atoms,
                    independent_work_ids={work_id},
                    goal=(self._campaign_row(campaign_id) or {})["research_goal"],
                )
                decision = decisions.get(index)
                if not reasons and decision and decision.verdict == "supported":
                    valid.append(argument)
            self._set_unit(job_id, unit_id, work_id, "staging", campaign_id)
            work_record = self._work_revision(
                {
                    **metadata,
                    "page_count": len(acquired["pages"]),
                    "pdf_bytes": acquired["byte_size"],
                }
            )
            work_record["availability"].update(
                {
                    "status": "available",
                    "page_count": len(acquired["pages"]),
                    "pdf_bytes": acquired["byte_size"],
                    "checked_at": utc_now(),
                }
            )
            work_record["content_digest"] = canonical_sha256(
                {key: value for key, value in work_record.items() if key != "content_digest"}
            )
            self._stage(campaign_id, work_id, "work", work_record)
            for argument in valid:
                selected_atoms = [atom for atom in atoms if atom.atom_id in argument.atom_ids]
                proposal = PrincipleRevision(
                    principle_id=principle_id("general"),
                    revision=1,
                    area="general",
                    title=concise_principle_title(argument),
                    claim=argument.canonical_claim,
                    kind=(
                        "theorem"
                        if argument.claim_class.value == "formal_proposition"
                        else "mechanistic"
                        if argument.claim_class.value == "causal_mechanism"
                        else "heuristic"
                        if argument.claim_class.value == "design_rule_or_intervention"
                        else "empirical"
                    ),
                    maturity="supported",
                    scope={
                        "statement": argument.generalization_level.value,
                        "conditions": argument.conditions,
                        "exclusions": argument.boundary,
                        "populations": [],
                    },
                    falsifier=argument.testability,
                    quality={"quality_gate": "quality-v2", "challenge": "supported"},
                    tags=[],
                    review_status="unassessed",
                    generation_trace=[
                        {
                            "provider": policy.provider,
                            "model": policy.model,
                            "prompt_sha256": arguments_result.trace.prompt_sha256,
                            "output_sha256": arguments_result.trace.output_sha256,
                        }
                    ],
                ).model_dump(mode="json")
                proposal["content_digest"] = canonical_sha256(
                    {key: value for key, value in proposal.items() if key != "content_digest"}
                )
                self._stage(campaign_id, work_id, "principle", proposal)
                for atom in selected_atoms:
                    page = None
                    section = ""
                    if atom.support:
                        key = atom.support[0].segment_key
                        source = next((item for item in segments if item["segment_key"] == key), {})
                        page = source.get("page_start")
                        section = source.get("section") or ""
                    link = PrincipleWorkLink(
                        principle_id=proposal["principle_id"],
                        principle_revision=1,
                        work_id=work_id,
                        role="evidence",
                        page=page,
                        section=section,
                        evidence_digest=hashlib.sha256(atom.faithful_claim.encode()).hexdigest(),
                    ).model_dump(mode="json")
                    self._stage(campaign_id, work_id, "principle_work", link)
            if not valid:
                state = "validation_quarantined"
            else:
                state = "staged"
                self._set_unit(
                    job_id,
                    unit_id,
                    work_id,
                    "deleting_source",
                    campaign_id,
                    temp_deleted=False,
                )
        except FileNotFoundError as exc:
            state = "acquisition_failed"
            error = {"category": "nonextractable", "message": str(exc)}
        except ProviderRequestError as exc:
            state = "provider_failed"
            error = {
                "category": exc.category,
                "message": str(exc),
                "retryable": exc.retryable,
                "status_code": exc.status_code,
            }
        except ProviderOutputError:
            state = "provider_failed"
            error = {
                "category": "invalid_output",
                "message": "The LLM returned invalid structured output after one repair attempt.",
                "retryable": True,
            }
        except httpx.TimeoutException:
            state = "acquisition_failed" if phase == "acquisition" else "provider_failed"
            error = {
                "category": "download_timeout" if phase == "acquisition" else "provider_timeout",
                "message": (
                    "The full-text server timed out; retry this paper later."
                    if phase == "acquisition"
                    else "The LLM request timed out; retry this paper."
                ),
                "retryable": True,
            }
        except httpx.HTTPStatusError as exc:
            state = "acquisition_failed" if phase == "acquisition" else "provider_failed"
            error = {
                "category": "download_http" if phase == "acquisition" else "provider_http",
                "message": (
                    "The full-text server rejected the download request."
                    if phase == "acquisition"
                    else "The LLM provider rejected the extraction request."
                ),
                "status_code": exc.response.status_code,
                "retryable": exc.response.status_code in {408, 409, 429} or exc.response.status_code >= 500,
            }
        except Exception as exc:
            state = "acquisition_failed" if phase == "acquisition" else "provider_failed"
            error = {
                "category": "acquisition_error" if phase == "acquisition" else "provider_error",
                "message": (
                    "The paper could not be downloaded and parsed."
                    if phase == "acquisition"
                    else "The LLM extraction failed; retry this paper or test the provider connection."
                ),
                "retryable": True,
                "exception_type": type(exc).__name__,
            }
        finally:
            if provider is not None:
                provider.close()
            try:
                if unit_root.exists():
                    shutil.rmtree(unit_root)
                cleanup_ok = not unit_root.exists()
                if job_root.exists() and not any(job_root.iterdir()):
                    job_root.rmdir()
            except OSError as exc:
                cleanup_ok = False
                error = {"category": "cleanup_failed", "message": str(exc)}
            if not cleanup_ok:
                state = "cleanup_failed"
            self._set_unit(
                job_id, unit_id, work_id, state, campaign_id, error=error, temp_deleted=cleanup_ok
            )
        return {"state": state, "temp_deleted": cleanup_ok, "error": error}

    def _record_provider_trace(self, job_id: str, unit_id: str, trace: Any) -> None:
        """Persist redacted attempts and atomically aggregate shared-job usage."""
        self.repository.save_provider_attempt(
            {
                "attempt_id": f"attempt:{monotonic_ulid()}",
                "job_id": job_id,
                "unit_id": unit_id,
                "provider": trace.provider,
                "model": trace.model,
                "prompt_template": trace.prompt_template,
                "prompt_sha256": trace.prompt_sha256,
                "input_sha256": trace.input_sha256,
                "output_sha256": trace.output_sha256,
                "state": "succeeded",
                "retry_index": max(0, int(trace.attempts) - 1),
                "latency_ms": int(trace.latency_ms),
                "error_category": "",
                "input_tokens": int(trace.input_tokens),
                "output_tokens": int(trace.output_tokens),
                "transport_attempts": int(trace.transport_attempts),
                "schema_repair_attempted": bool(trace.repair_attempted),
            }
        )
        with self._usage_lock, self.repository.connect() as conn:
            current = conn.execute(
                "SELECT http_attempts, input_tokens, output_tokens, pro_calls "
                "FROM provider_usage WHERE job_id=?",
                (job_id,),
            ).fetchone()
            usage = {
                "http_attempts": (int(current[0]) if current else 0)
                + int(trace.transport_attempts),
                "input_tokens": (int(current[1]) if current else 0) + int(trace.input_tokens),
                "output_tokens": (int(current[2]) if current else 0) + int(trace.output_tokens),
                "pro_calls": (int(current[3]) if current else 0),
            }
            conn.execute(
                """
                INSERT INTO provider_usage(
                    job_id, http_attempts, input_tokens, output_tokens, pro_calls, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    http_attempts=excluded.http_attempts,
                    input_tokens=excluded.input_tokens,
                    output_tokens=excluded.output_tokens,
                    pro_calls=excluded.pro_calls,
                    updated_at=excluded.updated_at
                """,
                (
                    job_id,
                    usage["http_attempts"],
                    usage["input_tokens"],
                    usage["output_tokens"],
                    usage["pro_calls"],
                    utc_now(),
                ),
            )

    def _set_unit(
        self,
        job_id: str,
        unit_id: str,
        work_id: str,
        state: str,
        campaign_id: str,
        *,
        error: dict[str, Any] | None = None,
        temp_deleted: bool = False,
    ) -> None:
        with self.repository.connect() as conn:
            ordinal_row = conn.execute(
                "SELECT ordinal, attempt_count FROM v14_job_units WHERE unit_id=?",
                (unit_id,),
            ).fetchone()
        ordinal = int(ordinal_row["ordinal"]) if ordinal_row else 0
        attempts = max(1, int(ordinal_row["attempt_count"] or 0)) if ordinal_row else 1
        self.repository.save_job_unit(
            {
                "unit_id": unit_id,
                "job_id": job_id,
                "work_id": work_id,
                "ordinal": ordinal,
                "state": state,
                "attempt_count": attempts,
                "checkpoint": {
                    "campaign_id": campaign_id,
                    "stage": state,
                    "temp_deleted": temp_deleted,
                },
                "error": error,
            }
        )
        with self.repository.connect() as conn:
            conn.execute(
                "UPDATE admin_campaign_works SET state=?, checkpoint_json=?, error_json=?, temp_deleted_at=? "
                "WHERE campaign_id=? AND work_id=?",
                (
                    state,
                    json.dumps({"stage": state, "temp_deleted": temp_deleted}),
                    json.dumps(error) if error else None,
                    utc_now() if temp_deleted else "",
                    campaign_id,
                    work_id,
                ),
            )

    def _stage(
        self, campaign_id: str, work_id: str, entity: str, proposed: dict[str, Any]
    ) -> AdminStagedItem:
        if entity == "work":
            match = self.global_cloud.match_work(proposed)
        elif entity == "principle":
            match = self.global_cloud.match_principle(proposed)
        else:
            match = {"kind": "new", "match": None, "reason": "provenance_link", "similarity": 0.0}
        current = match.get("match") or {}
        item = AdminStagedItem(
            stage_id=f"stage:{monotonic_ulid()}",
            campaign_id=campaign_id,
            entity=entity,
            proposed=proposed,
            current=current,
            diff=_diff(current, proposed),
            match_kind=match["kind"],
            match_reason=match.get("reason") or "",
            similarity=float(match.get("similarity") or 0),
            expected_revision=current.get("revision"),
            expected_digest=current.get("content_digest") or "",
        )
        with self.repository.connect() as conn:
            conn.execute(
                "INSERT INTO admin_staged_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    item.stage_id,
                    campaign_id,
                    work_id,
                    entity,
                    item.match_kind,
                    item.similarity,
                    item.decision,
                    int(item.ambiguous_confirmed),
                    item.expected_revision,
                    item.expected_digest,
                    proposed.get("content_digest") or canonical_sha256(proposed),
                    item.model_dump_json(),
                    item.created_at,
                    item.updated_at,
                ),
            )
        return item

    def staging(self, campaign_id: str) -> list[dict[str, Any]]:
        with self.repository.connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM admin_staged_items WHERE campaign_id=? ORDER BY stage_id",
                (campaign_id,),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def decide(self, stage_id: str, request: StagingDecisionRequest) -> dict[str, Any]:
        with self.repository.connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM admin_staged_items WHERE stage_id=?", (stage_id,)
            ).fetchone()
            if not row:
                raise KeyError(stage_id)
            item = AdminStagedItem.model_validate_json(row[0])
            if item.match_kind == "ambiguous" and not request.confirmed_ambiguous:
                raise ValueError("ambiguous matches require individual confirmation")
            item.decision = request.decision
            item.ambiguous_confirmed = request.confirmed_ambiguous
            item.updated_at = utc_now()
            conn.execute(
                "UPDATE admin_staged_items SET decision=?, ambiguous_confirmed=?, payload_json=?, updated_at=? WHERE stage_id=?",
                (
                    item.decision,
                    int(item.ambiguous_confirmed),
                    item.model_dump_json(),
                    item.updated_at,
                    stage_id,
                ),
            )
            # Provenance links are supporting records, not separate human
            # review decisions. Keep them aligned with their Principle so the
            # UI can remain paper/Principle-centered and readable.
            if item.entity == "principle":
                principle_id = str(item.proposed.get("principle_id") or "")
                link_rows = conn.execute(
                    "SELECT stage_id, payload_json FROM admin_staged_items "
                    "WHERE campaign_id=? AND entity='principle_work'",
                    (item.campaign_id,),
                ).fetchall()
                link_decision = (
                    "add" if request.decision in {"add", "update"} else "skip"
                )
                for link_row in link_rows:
                    link = AdminStagedItem.model_validate_json(link_row["payload_json"])
                    if str(link.proposed.get("principle_id") or "") != principle_id:
                        continue
                    link.decision = link_decision
                    link.updated_at = item.updated_at
                    conn.execute(
                        "UPDATE admin_staged_items SET decision=?, payload_json=?, updated_at=? "
                        "WHERE stage_id=?",
                        (
                            link.decision,
                            link.model_dump_json(),
                            link.updated_at,
                            link.stage_id,
                        ),
                    )
        return item.model_dump(mode="json")

    def bulk_decide(self, request: BulkStagingDecisionRequest) -> dict[str, Any]:
        updated: list[str] = []
        for stage_id in request.stage_ids:
            try:
                item = self.decide(stage_id, StagingDecisionRequest(decision=request.decision))
                updated.append(item["stage_id"])
            except ValueError:
                continue
        return {"updated": updated, "excluded_ambiguous": len(request.stage_ids) - len(updated)}

    def pause(self, job_id: str) -> dict[str, Any]:
        control = self._controls.get(job_id)
        if not control:
            raise ValueError("Admin extraction is not active in this runtime")
        control["pause"].set()
        job = self.repository.get_job(job_id)
        assert job is not None
        job.state = "pausing"
        job.stage = "pausing"
        job.status_message = "Stopping after active cleanup"
        self.repository.save_job(job)
        return job.model_dump(mode="json")

    def resume(self, job_id: str) -> dict[str, Any]:
        control = self._controls.get(job_id)
        job = self.repository.get_job(job_id)
        if job is None or job.kind != "admin_extraction":
            raise KeyError(job_id)
        if control:
            control["pause"].clear()
            job.state = "resuming"
            job.stage = "resuming"
            self.repository.save_job(job)
            return job.model_dump(mode="json")
        if job.state not in {"interrupted", "paused", "pausing", "resuming"}:
            raise ValueError("Admin extraction is not recoverable from its current state")
        campaign_id = str((job.checkpoint or {}).get("campaign_id") or "")
        campaign = self._campaign_row(campaign_id)
        if not campaign:
            raise ValueError("Admin campaign recovery metadata is missing")
        remaining: list[str] = []
        completed = 0
        for unit in self.repository.list_job_units(job_id):
            state = str(unit["state"])
            if state == "staged":
                completed += 1
                continue
            if state == "deleting_source":
                # Staging committed before deletion. Startup cleanup removed the
                # allowlisted temp directory, so do not repeat paid LLM stages.
                self._set_unit(
                    job_id,
                    str(unit["unit_id"]),
                    str(unit["work_id"]),
                    "staged",
                    campaign_id,
                    temp_deleted=True,
                )
                completed += 1
                continue
            remaining.append(str(unit["work_id"]))
            self._set_unit(
                job_id,
                str(unit["unit_id"]),
                str(unit["work_id"]),
                "queued",
                campaign_id,
                temp_deleted=True,
            )
        if not remaining:
            job.state = "succeeded"
            job.stage = "Review ready"
            job.progress = 1
            job.completed_units = job.total_units
            job.updated_at = utc_now()
            self.repository.save_job(job)
            return job.model_dump(mode="json")
        _, policy, api_key = self.local.provider_configuration(
            campaign["provider_profile_id"], campaign["model"], egress_confirmed=True
        )
        control = {"pause": threading.Event(), "cancel": threading.Event()}
        self._controls[job_id] = control
        job.state = "resuming"
        job.stage = "reconstructing durable units"
        job.completed_units = completed
        job.progress = completed / max(1, job.total_units)
        job.updated_at = utc_now()
        self.repository.save_job(job)
        self._executor.submit(
            self._run_extract, campaign_id, job_id, remaining, policy, api_key, control
        )
        return job.model_dump(mode="json")

    def cancel(self, job_id: str) -> dict[str, Any]:
        control = self._controls.get(job_id)
        job = self.repository.get_job(job_id)
        if job is None or job.kind != "admin_extraction":
            raise KeyError(job_id)
        if not control:
            if job.state != "interrupted":
                raise ValueError("Admin extraction is not active in this runtime")
            campaign_id = str((job.checkpoint or {}).get("campaign_id") or "")
            with self.repository.connect() as conn:
                conn.execute(
                    "UPDATE admin_campaign_works SET state='cancelled' WHERE campaign_id=? "
                    "AND state NOT IN ('staged','cleanup_failed')",
                    (campaign_id,),
                )
            job.state = "cancelled"
            job.stage = "cancelled"
            job.updated_at = utc_now()
            self.repository.save_job(job)
            return job.model_dump(mode="json")
        control["cancel"].set()
        control["pause"].clear()
        job.state = "cancelling"
        job.stage = "cancelling"
        job.status_message = "Waiting for active cleanup"
        self.repository.save_job(job)
        return job.model_dump(mode="json")

    def create_sync(self, campaign_id: str, *, confirmation: str) -> dict[str, Any]:
        campaign = self._campaign_row(campaign_id)
        if campaign is None:
            raise KeyError(campaign_id)
        items = self.staging(campaign_id)
        # Old campaigns may predate automatic support-record decisions. Infer
        # only the mechanical Principle-Work links; Works and Principles still
        # require explicit Admin review.
        principle_decisions = {
            str(item["proposed"].get("principle_id") or ""): str(item["decision"])
            for item in items
            if item["entity"] == "principle"
        }
        for item in items:
            if item["entity"] != "principle_work" or item["decision"]:
                continue
            inherited = principle_decisions.get(
                str(item["proposed"].get("principle_id") or ""), ""
            )
            if inherited:
                self.decide(
                    str(item["stage_id"]),
                    StagingDecisionRequest(
                        decision="add" if inherited in {"add", "update"} else "skip"
                    ),
                )
        items = self.staging(campaign_id)
        if not items or any(not item["decision"] for item in items):
            raise ValueError("every staged item requires an explicit review decision")
        if any(
            item["match_kind"] == "ambiguous" and not item["ambiguous_confirmed"] for item in items
        ):
            raise ValueError("ambiguous staged items require individual confirmation")
        expected = f"SUBMIT {campaign_id}"
        if confirmation != expected:
            raise ValueError(f"typed confirmation must equal {expected}")
        changes = [item for item in items if item["decision"] != "skip"]
        payload = CloudSync(
            sync_id=f"sync:{monotonic_ulid()}",
            campaign_id=campaign_id,
            state="reviewed",
            base_release_id=campaign["base_release_id"],
            base_commit_sha=campaign["base_commit_sha"],
            base_manifest_digest=campaign["base_manifest_digest"],
            changeset_digest=canonical_sha256(changes),
        )
        with self.repository.connect() as conn:
            conn.execute(
                "INSERT INTO admin_cloud_syncs VALUES (?,?,?,?,?,?)",
                (
                    payload.sync_id,
                    campaign_id,
                    payload.state,
                    payload.model_dump_json(),
                    payload.created_at,
                    payload.updated_at,
                ),
            )
            conn.execute(
                "UPDATE admin_campaigns SET state='syncing', updated_at=? WHERE campaign_id=?",
                (utc_now(), campaign_id),
            )
        return payload.model_dump(mode="json")

    def submit_sync(self, sync_id: str, *, confirmation: str) -> dict[str, Any]:
        with self.repository.connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM admin_cloud_syncs WHERE sync_id=?", (sync_id,)
            ).fetchone()
        if not row:
            raise KeyError(sync_id)
        sync = CloudSync.model_validate_json(row[0])
        if sync.state != "reviewed":
            raise ValueError("only a reviewed draft sync can be submitted")
        expected = f"PUBLISH {sync_id}"
        if confirmation != expected:
            raise ValueError(f"typed confirmation must equal {expected}")
        campaign = self._campaign_row(sync.campaign_id) or {}
        current = self.global_cloud.status()
        if (
            current.get("release_id") != sync.base_release_id
            or current.get("content_digest") != sync.base_manifest_digest
        ):
            sync.state = "needs_resolution"
            sync.error = {
                "category": "base_drift",
                "current_release_id": current.get("release_id") or "",
            }
            self._save_sync(sync)
            return sync.model_dump(mode="json")
        adapter = GitHubPublicationAdapter()
        if not adapter.configured():
            raise ValueError(
                "the fine-grained GitHub credential is not configured in macOS Keychain"
            )
        files = self._reviewed_cloud_files(sync)
        # CI remains the only authority that rebuilds indexes, vectors, snapshot
        # assets and Pages pointers from these canonical records.
        branch = f"principia-cloud/{sync.sync_id.split(':')[-1].lower()}"
        sync.branch = branch
        sync.state = "pr_creating"
        sync.updated_at = utc_now()
        self._save_sync(sync)
        if adapter.credential_mode() == "ssh":
            adapter.create_review_branch_ssh(
                branch=branch,
                base="main",
                files=files,
                message=f"Global Cloud reviewed sync {sync.sync_id}",
            )
            # The repository workflow creates the checked PR and queues
            # auto-merge.  This avoids putting a second GitHub secret in the
            # application when the owner has explicitly configured SSH.
            sync.state = "checks_running"
        else:
            adapter.create_review_branch(
                branch=branch,
                base="main",
                files=files,
                message=f"Global Cloud reviewed sync {sync.sync_id}",
            )
            result = adapter.submit_reviewed_changeset(
                branch=branch,
                base="main",
                title=f"Global Cloud: {campaign.get('research_goal', 'reviewed ingestion')[:80]}",
                body=(
                    "Reviewed in Principia Admin. Changes are restricted to `global-cloud/**`.\n\n"
                    f"Sync: `{sync.sync_id}`\nBase release: `{sync.base_release_id}`\n"
                    f"Changeset: `{sync.changeset_digest}`"
                ),
            )
            sync.pr_number = int(result["pr_number"])
            sync.pr_url = result["pr_url"]
            sync.state = (
                "auto_merge_queued"
                if result["state"] == "auto_merge_queued"
                else "checks_running"
            )
        sync.updated_at = utc_now()
        self._save_sync(sync)
        return sync.model_dump(mode="json")

    def _reviewed_cloud_files(self, sync: CloudSync) -> dict[str, bytes]:
        configured = os.getenv("PRINCIPIA_GLOBAL_CANONICAL_ROOT", "")
        candidates = [Path(configured).expanduser()] if configured else []
        candidates.extend(parent / "global-cloud" for parent in Path(__file__).resolve().parents)
        canonical_root = next(
            (
                candidate.resolve()
                for candidate in candidates
                if (candidate / "CLOUD_VERSION").is_file()
            ),
            (Path(__file__).resolve().parents[3] / "global-cloud").resolve(),
        )
        if not (canonical_root / "CLOUD_VERSION").is_file():
            raise ValueError("the canonical Global Cloud checkout is unavailable")
        source = CanonicalCloudRepository(canonical_root)
        original = source.all_records()
        by_kind: dict[RecordKind, dict[str, dict[str, Any]]] = {
            kind: {record_identity(kind, row): row for row in values}
            for kind, values in original.items()
        }
        items = [AdminStagedItem.model_validate(item) for item in self.staging(sync.campaign_id)]
        identity_map: dict[str, tuple[str, int]] = {}
        now = utc_now()
        # Resolve Work and Principle revisions before their provenance links.
        for item in sorted(
            items, key=lambda value: (value.entity == "principle_work", value.stage_id)
        ):
            if item.decision == "skip":
                continue
            kind: RecordKind = {
                "work": "works",
                "principle": "principles",
                "principle_work": "principle-work",
                "relation": "relations",
            }[item.entity]
            proposed = dict(item.proposed)
            current = dict(item.current)
            if item.decision in {"update", "retire"}:
                if not current:
                    raise ValueError(f"{item.decision} requires a pinned current Cloud record")
                if int(current.get("revision") or 0) != int(item.expected_revision or 0):
                    raise ValueError("staged revision precondition no longer matches")
                if str(current.get("content_digest") or "") != item.expected_digest:
                    raise ValueError("staged digest precondition no longer matches")
                proposed = dict(current if item.decision == "retire" else proposed)
                proposed["revision"] = int(current["revision"]) + 1
                proposed["created_at"] = current.get("created_at") or now
                proposed["updated_at"] = now
                if item.entity == "work":
                    proposed["work_id"] = current["work_id"]
                elif item.entity == "principle":
                    proposed["principle_id"] = current["principle_id"]
                if item.decision == "retire":
                    proposed["status"] = "retired"
            if item.entity == "principle":
                old_id = str(item.proposed["principle_id"])
                proposed["review_status"] = "reviewed"
                proposed["review_actor"] = "principia-admin-confirmation"
                proposed["reviewed_at"] = now
                identity_map[old_id] = (str(proposed["principle_id"]), int(proposed["revision"]))
            if item.entity == "work":
                identity_map[str(item.proposed["work_id"])] = (
                    str(proposed["work_id"]),
                    int(proposed["revision"]),
                )
            if item.entity == "principle_work":
                mapped_principle = identity_map.get(str(proposed["principle_id"]))
                mapped_work = identity_map.get(str(proposed["work_id"]))
                if mapped_principle:
                    proposed["principle_id"], proposed["principle_revision"] = mapped_principle
                if mapped_work:
                    proposed["work_id"] = mapped_work[0]
            if "content_digest" in proposed:
                proposed["content_digest"] = ""
            from ..cloud.canonical import normalize_record

            normalized = normalize_record(kind, proposed)
            by_kind[kind][record_identity(kind, normalized)] = normalized

        with tempfile.TemporaryDirectory(prefix="principia-reviewed-cloud.") as temporary:
            staged_root = Path(temporary) / "global-cloud"
            shutil.copytree(canonical_root, staged_root)
            staged = CanonicalCloudRepository(staged_root)
            for kind, records in by_kind.items():
                staged.write_records(kind, records.values())
            validation = staged.validate()
            changed: dict[str, bytes] = {}
            for kind in by_kind:
                original_dir = canonical_root / "data" / "v1" / kind
                updated_dir = staged_root / "data" / "v1" / kind
                for path in sorted(updated_dir.glob("*.jsonl")):
                    prior = original_dir / path.name
                    if not prior.is_file() or prior.read_bytes() != path.read_bytes():
                        changed[f"global-cloud/data/v1/{kind}/{path.name}"] = path.read_bytes()
            audit = {
                "schema_version": "principia-global-sync-audit-v1",
                "sync_id": sync.sync_id,
                "campaign_id": sync.campaign_id,
                "base_release_id": sync.base_release_id,
                "base_commit_sha": sync.base_commit_sha,
                "base_manifest_digest": sync.base_manifest_digest,
                "changeset_digest": sync.changeset_digest,
                "canonical_content_digest": validation["content_digest"],
                "review_attestation": "Submit reviewed changeset",
                "reviewed_at": now,
                "decisions": [
                    {"stage_id": item.stage_id, "entity": item.entity, "decision": item.decision}
                    for item in items
                ],
            }
            stamp = now[:7].replace("-", "/")
            changed[f"global-cloud/audit/{stamp}/{sync.sync_id.replace(':', '-')}.json"] = (
                json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            ).encode()
        if len(changed) <= 1:
            raise ValueError("the reviewed changeset contains no canonical record change")
        return changed

    def _save_sync(self, sync: CloudSync) -> None:
        with self.repository.connect() as conn:
            conn.execute(
                "UPDATE admin_cloud_syncs SET state=?, payload_json=?, updated_at=? WHERE sync_id=?",
                (sync.state, sync.model_dump_json(), sync.updated_at, sync.sync_id),
            )

    def sync_detail(self, sync_id: str) -> dict[str, Any] | None:
        with self.repository.connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM admin_cloud_syncs WHERE sync_id=?", (sync_id,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def latest_sync(self, campaign_id: str) -> dict[str, Any] | None:
        with self.repository.connect() as conn:
            row = conn.execute(
                "SELECT sync_id FROM admin_cloud_syncs WHERE campaign_id=? "
                "ORDER BY updated_at DESC, sync_id DESC LIMIT 1",
                (campaign_id,),
            ).fetchone()
        return self.refresh_sync(str(row[0])) if row else None

    def refresh_sync(self, sync_id: str) -> dict[str, Any]:
        detail = self.sync_detail(sync_id)
        if detail is None:
            raise KeyError(sync_id)
        sync = CloudSync.model_validate(detail)
        if sync.state in {"published", "failed", "cancelled", "needs_resolution", "reviewed"}:
            return sync.model_dump(mode="json")
        adapter = GitHubPublicationAdapter()
        if not adapter.configured():
            return sync.model_dump(mode="json")
        try:
            if not sync.pr_number and sync.branch:
                branch_outcome = adapter.review_branch_status(branch=sync.branch)
                if branch_outcome.get("pr_number"):
                    sync.pr_number = int(branch_outcome["pr_number"])
                    sync.pr_url = str(branch_outcome.get("pr_url") or "")
                    sync.updated_at = utc_now()
                    self._save_sync(sync)
            if not sync.pr_number:
                return sync.model_dump(mode="json")
            outcome = adapter.publication_status(pr_number=sync.pr_number)
            sync.state = outcome["state"]
            sync.release_id = str(outcome.get("release_id") or sync.release_id)
            sync.error = dict(outcome.get("error") or {})
            sync.updated_at = utc_now()
            self._save_sync(sync)
            if sync.state == "published":
                with self.repository.connect() as conn:
                    conn.execute(
                        "UPDATE admin_campaigns SET state='completed', updated_at=? WHERE campaign_id=?",
                        (utc_now(), sync.campaign_id),
                    )
        except Exception as exc:
            # Transient GitHub/Pages outages must not turn an accepted sync into
            # a terminal failure or expose credential/error details.
            sync.error = {"category": type(exc).__name__}
            sync.updated_at = utc_now()
            self._save_sync(sync)
        return sync.model_dump(mode="json")

    def purge_staging(self, campaign_id: str, *, abandoned: bool = False) -> dict[str, Any]:
        campaign = self._campaign_row(campaign_id)
        if campaign is None:
            raise KeyError(campaign_id)
        with self.repository.connect() as conn:
            active = conn.execute(
                "SELECT 1 FROM v14_jobs WHERE job_id=? AND state NOT IN ('succeeded','failed','cancelled','interrupted')",
                (campaign.get("job_id") or "",),
            ).fetchone()
            published = conn.execute(
                "SELECT 1 FROM admin_cloud_syncs WHERE campaign_id=? AND state='published'",
                (campaign_id,),
            ).fetchone()
            if active:
                raise ValueError("staging cannot be purged while extraction or sync is active")
            if not published and not abandoned:
                raise ValueError(
                    "staging may be purged only after publication or explicit abandonment"
                )
            count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM admin_staged_items WHERE campaign_id=?", (campaign_id,)
                ).fetchone()[0]
            )
            conn.execute("DELETE FROM admin_staged_items WHERE campaign_id=?", (campaign_id,))
        return {"campaign_id": campaign_id, "purged": count, "audit_receipt_retained": True}

    def sweep_orphaned_temp(self) -> dict[str, Any]:
        removed = 0
        for child in self.temp_root.iterdir():
            resolved = child.resolve()
            if self.temp_root not in resolved.parents or not child.is_dir():
                continue
            shutil.rmtree(child)
            removed += 1
        return {"removed_job_directories": removed, "root": ".principia/admin/tmp"}

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
