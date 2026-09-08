from __future__ import annotations

import json
from typing import Any

from ..global_store import GlobalStore
from ..models import ProjectMembership, to_dict, utc_now
from ..storage import Store
from ..utils import compact_text, stable_id
from ..work_versioning import model_key as build_model_key


LEGACY_BUCKET_BY_CONCEPT = {
    "principle": ("principles", "principle_id"),
    "existed_idea": ("existed_ideas", "canonical_id"),
    "takeaway_message": ("takeaway_messages", "canonical_id"),
    "benchmark": ("benchmark_records", "benchmark_id"),
    "baseline": ("baseline_records", "baseline_id"),
    "result_fact": ("result_records", "result_id"),
}


class CloudHydrator:
    def __init__(self, global_store: GlobalStore, store: Store | None = None):
        self.global_store = global_store
        self.store = store

    def hydrate_work_bundle(self, bundle: dict[str, Any], *, snapshot_id: str = "", model_key: str = "", project_id: str = "default") -> dict[str, Any]:
        work_record = bundle.get("work") if bundle.get("record_type") == "work_bundle" else bundle
        work_record = dict(work_record or {})
        origin = self._origin(snapshot_id, model_key, work_record)
        work_payload = self._work_payload(work_record, origin)
        saved_work = self.global_store.upsert_work(work_payload)
        if self.store:
            legacy = {**work_payload, "work_id": saved_work.get("work_id") or work_payload.get("work_id"), "cloud_origin": origin}
            self.store.upsert("source_works", legacy, "work_id")
            self._add_legacy_project_membership(project_id, "source_works", str(legacy.get("work_id") or ""))
        for version in work_record.get("work_versions") or bundle.get("work_versions") or []:
            self.global_store.upsert_work({**work_payload, **self._version_payload(version), "work_id": saved_work.get("work_id")})
        for extraction in work_record.get("extraction_runs") or bundle.get("extraction_runs") or []:
            self._hydrate_extraction(extraction, saved_work, model_key)
        hydrated_concepts = []
        for concept in work_record.get("concepts") or bundle.get("concepts") or []:
            hydrated = self.hydrate_concept(concept, snapshot_id=snapshot_id, model_key=model_key, project_id=project_id)
            if hydrated:
                hydrated_concepts.append(hydrated)
        relation_records = bundle.get("relation_records") or bundle.get("relations") or []
        if not isinstance(relation_records, list):
            relation_records = []
        for relation in relation_records:
            self.hydrate_relation(relation, snapshot_id=snapshot_id)
        return {"work": saved_work, "concepts": hydrated_concepts, "cloud_origin": origin}

    def hydrate_concept(self, record: dict[str, Any], *, snapshot_id: str = "", model_key: str = "", project_id: str = "default") -> dict[str, Any]:
        payload = dict(record.get("payload") or record)
        origin = self._origin(snapshot_id, model_key, record)
        payload.setdefault("concept_id", record.get("concept_id") or payload.get("concept_id"))
        payload.setdefault("title", record.get("canonical_label") or payload.get("title") or payload.get("name"))
        payload["cloud_origin"] = origin
        support = record.get("support") or {}
        evidence = []
        for link in record.get("evidence") or record.get("evidence_records") or []:
            evidence.append(
                {
                    "evidence_id": link.get("evidence_id"),
                    "work_id": link.get("work_id"),
                    "work_version_id": link.get("work_version_id"),
                    "evidence_type": link.get("evidence_type") or "cloud_evidence",
                    "evidence_span": link.get("snippet") or link.get("claim_text") or link.get("evidence_span") or "",
                    "source_url": (link.get("locator") or {}).get("source_url") or link.get("source_url") or "",
                    "confidence": link.get("confidence") or support.get("confidence_score") or 0.5,
                }
            )
        if not evidence:
            support_work_ids = self._supporting_work_ids(record, payload, support)
            if support_work_ids:
                payload.setdefault("source_work_ids", support_work_ids)
                payload.setdefault("source_works", support_work_ids)
            evidence_text = (
                payload.get("evidence")
                or payload.get("abstract_signature")
                or payload.get("core_idea")
                or payload.get("idea_text")
                or payload.get("message_text")
                or payload.get("argument")
                or payload.get("summary")
                or record.get("canonical_label")
                or payload.get("title")
                or payload.get("name")
                or ""
            )
            for work_id in support_work_ids:
                evidence.append(
                    {
                        "work_id": work_id,
                        "evidence_type": "cloud_supporting_work",
                        "evidence_span": compact_text(str(evidence_text or ""), 1200),
                        "source_url": (payload.get("source_paper_link") or (payload.get("source_paper_links") or [""])[0]) if isinstance(payload.get("source_paper_links"), list) else payload.get("source_paper_link") or "",
                        "confidence": support.get("confidence_score") or payload.get("confidence_score") or 0.5,
                    }
                )
        concept = self.global_store.upsert_concept(
            str(record.get("concept_type") or payload.get("concept_type") or "takeaway_message"),
            payload,
            key_text=str(record.get("canonical_key") or record.get("canonical_label") or payload.get("title") or payload.get("name") or ""),
            source_origin="cloud_literature_extracted",
            validation_level=support.get("validation_level") or payload.get("validation_level") or "extracted_unverified",
            verification_status=support.get("verification_status") or payload.get("verification_status") or "cloud_imported",
            public_scope="public_cloud",
            llm_provider=record.get("llm_provider") or "",
            llm_model=record.get("llm_model") or "",
            model_mode=record.get("model_mode") or "auto",
            prompt_version=record.get("prompt_version") or "",
            schema_version=record.get("schema_version") or "principia-cloud-1.1",
            evidence=evidence,
        )
        if self.store:
            bucket_info = LEGACY_BUCKET_BY_CONCEPT.get(str(record.get("concept_type") or ""))
            if bucket_info:
                bucket, id_key = bucket_info
                legacy = {**payload, id_key: payload.get(id_key) or concept.get("concept_id"), "concept_id": concept.get("concept_id"), "field_id": project_id, "cloud_origin": origin}
                if bucket in {"existed_ideas", "takeaway_messages"}:
                    legacy["canonical_id"] = legacy.get("canonical_id") or concept.get("concept_id")
                self.store.upsert(bucket, legacy, id_key)
                self._add_legacy_project_membership(project_id, bucket, str(legacy.get(id_key) or ""))
                for link in evidence:
                    work_id = str(link.get("work_id") or "")
                    if not work_id:
                        continue
                    self.store.upsert(
                        "evidence_links",
                        {
                            "link_id": stable_id("EL", project_id, bucket, legacy[id_key], work_id),
                            "field_id": project_id,
                            "target_bucket": bucket,
                            "target_id": legacy[id_key],
                            "source_bucket": "source_works",
                            "source_id": work_id,
                            "evidence": compact_text(str(link.get("evidence_span") or ""), 500),
                            "created_at": utc_now(),
                            "updated_at": utc_now(),
                            "cloud_origin": origin,
                        },
                        "link_id",
                    )
        return concept

    def _supporting_work_ids(self, record: dict[str, Any], payload: dict[str, Any], support: dict[str, Any]) -> list[str]:
        ids: list[str] = []
        for value in (
            support.get("supporting_work_ids"),
            record.get("supporting_work_ids"),
            record.get("source_work_ids"),
            record.get("source_works"),
            payload.get("source_work_ids"),
            payload.get("source_works"),
        ):
            if isinstance(value, list):
                ids.extend(str(item) for item in value if item)
            elif value:
                ids.append(str(value))
        return list(dict.fromkeys([item for item in ids if item]))

    def _add_legacy_project_membership(self, project_id: str, bucket: str, record_id: str) -> None:
        if not self.store or not project_id or project_id == "default" or not bucket or not record_id:
            return
        existing = self.store.get_item("project_memberships", stable_id("PM", project_id, bucket, record_id))
        if existing and not existing.get("hidden"):
            return
        now = utc_now()
        membership = to_dict(
            ProjectMembership(
                membership_id=stable_id("PM", project_id, bucket, record_id),
                field_id=project_id,
                bucket=bucket,
                record_id=record_id,
                display_order=0,
                source="cloud_hydrate",
                hidden=False,
                created_at=existing.get("created_at") if existing else now,
                updated_at=now,
            )
        )
        self.store.upsert("project_memberships", membership, "membership_id")

    def hydrate_relation(self, record: dict[str, Any], *, snapshot_id: str = "") -> dict[str, Any]:
        relation_id = str(record.get("relation_id") or "")
        if not relation_id:
            return {}
        with self.global_store._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO cloud_relation(
                    relation_id, subject_id, predicate, object_id, evidence_ids_json,
                    confidence, source, model_key, snapshot_id, payload_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    relation_id,
                    record.get("subject_id") or "",
                    record.get("predicate") or "",
                    record.get("object_id") or "",
                    json.dumps(record.get("evidence_ids") or [], ensure_ascii=False),
                    float(record.get("confidence") or 0.5),
                    record.get("source") or "cloud_import",
                    record.get("model_key") or "",
                    snapshot_id,
                    json.dumps(record, ensure_ascii=False),
                    record.get("created_at") or utc_now(),
                ),
            )
        return record

    def _hydrate_extraction(self, record: dict[str, Any], saved_work: dict[str, Any], model_key: str) -> None:
        work_id = saved_work.get("work_id") or record.get("work_id")
        work_version_id = saved_work.get("work_version_id") or record.get("work_version_id")
        if not work_id or not work_version_id:
            return
        run = self.global_store.ensure_extraction_run(
            work_id,
            work_version_id,
            llm_provider=record.get("llm_provider") or "",
            llm_model=record.get("llm_model") or "",
            model_mode=record.get("model_mode") or "auto",
            prompt_version=record.get("prompt_version") or "",
            schema_version=record.get("schema_version") or "principia-cloud-1.1",
            extraction_task_type=record.get("extraction_task_type") or "work_concepts",
        )
        self.global_store.complete_extraction_run(run.get("extraction_run_id") or record.get("extraction_run_id"), result=record.get("result_summary") or record.get("result_refs") or {})

    def _origin(self, snapshot_id: str, model_key: str, record: dict[str, Any]) -> dict[str, Any]:
        resolved_model_key = model_key or self._record_model_key(record)
        return {
            "cloud_snapshot_id": snapshot_id,
            "cloud_record_id": record.get("work_id") or record.get("concept_id") or record.get("record_id") or "",
            "cloud_model_key": resolved_model_key,
            "cloud_payload_sha256": record.get("payload_sha256") or "",
            "cloud_updated_at": ((record.get("timestamps") or {}).get("updated_at") or record.get("updated_at") or utc_now()),
        }

    def _record_model_key(self, record: dict[str, Any]) -> str:
        direct = record.get("model_key")
        if direct:
            return str(direct)
        model_keys = record.get("model_keys")
        if isinstance(model_keys, list) and model_keys:
            return str(model_keys[0])
        runs = record.get("extraction_runs") or record.get("extractions") or []
        if isinstance(runs, list) and runs:
            run = runs[0] or {}
            return build_model_key(
                str(run.get("llm_provider") or run.get("provider") or ""),
                str(run.get("llm_model") or run.get("model_name") or ""),
                str(run.get("model_mode") or "auto"),
                str(run.get("prompt_version") or ""),
                str(run.get("schema_version") or "principia-cloud-1.1"),
                str(run.get("extraction_task_type") or "work_concepts"),
            )
        payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
        if payload:
            return build_model_key(
                str(payload.get("provider") or payload.get("llm_provider") or ""),
                str(payload.get("model_name") or payload.get("llm_model") or ""),
                str(payload.get("model_mode") or "auto"),
                str(payload.get("prompt_version") or "principia-work-extract-v1"),
                str(payload.get("schema_version") or "principia-cloud-1.1"),
                str(payload.get("extraction_task_type") or "work_concepts"),
            )
        return ""

    def _work_payload(self, record: dict[str, Any], origin: dict[str, Any]) -> dict[str, Any]:
        identity = record.get("identity") or record
        payload = {
            "work_id": record.get("work_id") or identity.get("work_id"),
            "title": identity.get("canonical_title") or record.get("title") or record.get("canonical_title") or "Untitled work",
            "canonical_title": identity.get("canonical_title") or record.get("title") or "Untitled work",
            "abstract": record.get("abstract") or identity.get("abstract") or "",
            "authors": identity.get("authors") or record.get("authors") or [],
            "year": identity.get("year") or record.get("year"),
            "venue_or_source": identity.get("venue_or_source") or record.get("venue_or_source") or "",
            "source_type": identity.get("source_type") or record.get("source_type") or "paper",
            "source_urls": identity.get("source_urls") or record.get("source_urls") or [],
            "doi": identity.get("doi") or "",
            "arxiv_id": identity.get("arxiv_id") or "",
            "openalex_id": identity.get("openalex_id") or "",
            "crossref_id": identity.get("crossref_id") or "",
            "semantic_scholar_id": identity.get("semantic_scholar_id") or "",
            "source_provider": (record.get("source_state") or {}).get("source_provider") or "",
            "source_record_id": (record.get("source_state") or {}).get("source_record_id") or "",
            "source_modified_at": (record.get("source_state") or {}).get("source_modified_at") or "",
            "source_updated_at": (record.get("source_state") or {}).get("source_updated_at") or "",
            "cloud_origin": origin,
        }
        return payload

    def _version_payload(self, record: dict[str, Any]) -> dict[str, Any]:
        metadata = record.get("metadata") or {}
        return {
            "title": record.get("title") or metadata.get("title") or "",
            "abstract": record.get("abstract") or metadata.get("abstract") or "",
            "source_provider": record.get("source_provider") or "",
            "source_record_id": record.get("source_record_id") or "",
            "source_modified_at": record.get("source_modified_at") or "",
            "source_updated_at": record.get("source_updated_at") or "",
            "metadata": metadata,
        }
