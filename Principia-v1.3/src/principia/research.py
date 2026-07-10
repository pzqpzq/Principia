from __future__ import annotations

import io
import json
import re
import urllib.parse
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import httpx
from pypdf import PdfReader
from principia_retrieval import RetrievalConfig, WorkRetriever

from ._llm_progress import call_with_progress
from .ids import normalize_key, readable_id, short_hash
from .llm import LLMClient
from .models import CancelToken, ExtractedFeatures, WorkFeatures, WorkItem, WorkList
from .run import ProgressCallback, RunHandle
from .storage import WorkspaceStorage

SearchSource = Callable[[str, int, float], Sequence[dict[str, Any] | WorkItem]]

SEARCH_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "control",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "large",
    "of",
    "on",
    "or",
    "operating",
    "provide",
    "real",
    "scale",
    "that",
    "the",
    "their",
    "time",
    "to",
    "with",
}

RETRIEVAL_RERANK_MODES = {"", "bm25", "deterministic", "no_llm", "embedding", "embedding_rerank"}


def validate_rerank_mode(value: str | None) -> str:
    mode = str(value or "").strip().lower().replace("-", "_")
    if mode not in RETRIEVAL_RERANK_MODES:
        choices = ", ".join(sorted(option for option in RETRIEVAL_RERANK_MODES if option))
        raise ValueError(f"Unsupported retrieval rerank mode {value!r}. Choose one of: {choices}.")
    return mode


class ResearchService:
    def __init__(
        self,
        storage: WorkspaceStorage,
        llm: LLMClient,
        *,
        search_sources: dict[str, SearchSource] | None = None,
    ) -> None:
        self.storage = storage
        self.llm = llm
        self.custom_search_sources = search_sources is not None
        self.search_sources = search_sources or {
            "openalex": search_openalex,
            "crossref": search_crossref,
            "arxiv": search_arxiv,
        }

    def load_works(self, *, limit: int = 200) -> WorkList:
        """Load previously persisted works without searching public sources again."""
        works = self.storage.list_works(limit=max(1, int(limit)))
        return WorkList(
            query="",
            items=works,
            target_count=len(works),
            mode="loaded",
            sources=["workspace"],
        )

    def load_features(
        self,
        *,
        limit: int = 200,
        model: str | None = None,
        work_ids: list[str] | None = None,
        latest_only: bool = True,
    ) -> ExtractedFeatures:
        """Load persisted extraction features without running LLM extraction again."""
        if latest_only:
            items = self.storage.list_latest_extractions(limit=max(1, int(limit)), model=model, work_ids=work_ids)
        else:
            items = self.storage.list_extractions(limit=max(1, int(limit)), model=model, work_ids=work_ids)
        model_label = model or (items[0].model if items else "loaded")
        return ExtractedFeatures(items=items, model=model_label, run_id="")

    def search(
        self,
        query: str,
        *,
        target_count: int = 20,
        mode: str = "hybrid",
        rerank_mode: str | None = None,
        sources: list[str] | None = None,
        persist: bool = True,
        timeout: float = 12.0,
        show_progress: bool = False,
        callback: ProgressCallback | None = None,
        cancel_token: CancelToken | None = None,
    ) -> WorkList:
        selected_names = sources or (
            list(self.search_sources) if self.custom_search_sources else ["arxiv", "openalex", "crossref", "semantic_scholar"]
        )
        target_count = max(1, min(int(target_count or 20), 200))
        with RunHandle(
            self.storage,
            "research.search",
            callback=callback,
            token=cancel_token,
            show_progress=show_progress,
        ) as run:
            run.update("query_planning", "Planning semantic metadata search.", progress=0.05, target_count=target_count)
            source_map = None
            if self.custom_search_sources:
                source_map = {name: self.search_sources[name] for name in selected_names if name in self.search_sources}
            retrieval_llm = self._retrieval_llm()
            config = RetrievalConfig(
                use_llm_planner=retrieval_llm is not None,
                rerank_mode=validate_rerank_mode(rerank_mode),
                max_raw_candidates=max(80, target_count * 4),
                max_queries=8,
                source_names=selected_names,
            )

            def retrieval_callback(stage: str, payload: dict[str, Any]) -> None:
                if stage == "query_plan":
                    run.update(
                        "source_search",
                        "Searching public metadata sources with the shared semantic retriever.",
                        progress=0.15,
                        query_count=len(payload.get("queries") or []),
                        entities=payload.get("entities") or [],
                        sources=selected_names,
                    )

            try:
                retrieval = WorkRetriever(sources=source_map, config=config).search(
                    query,
                    target_count=target_count,
                    llm=retrieval_llm,
                    timeout=timeout,
                    callback=retrieval_callback,
                )
            except Exception as exc:  # noqa: BLE001
                self.storage.log_event(run.status.run_id, "source_warning", f"shared retriever failed: {exc}")
                retrieval = WorkRetriever(sources=source_map, config=RetrievalConfig(use_llm_planner=False, source_names=selected_names)).search(
                    query,
                    target_count=target_count,
                    llm=None,
                    timeout=timeout,
                )
            run.update(
                "dedupe",
                "Normalizing and deduplicating candidate works.",
                progress=0.7,
                raw_candidates=len(retrieval.candidates),
                selected_candidates=len(retrieval.selected_works),
            )
            works = dedupe_works([coerce_work(item) for item in retrieval.selected_works])
            works = works[:target_count]
            if persist:
                existing = self.storage.existing_work_ids()
                saved = []
                for work in works:
                    if not work.id or work.id in existing:
                        work.id = readable_id(work.title, existing=existing)
                    existing.add(work.id)
                    saved.append(self.storage.save_work(work))
                works = saved
            output = WorkList(
                query=query,
                items=works,
                target_count=target_count,
                mode=mode,
                sources=selected_names,
                run_id=run.status.run_id,
            )
            export_path = self.storage.artifacts_dir / "source_json" / f"{run.status.run_id}.json"
            export_path.write_text(json.dumps(output.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
            run.update("complete", f"Found {len(works)} work(s).", progress=0.98, works=len(works))
            return output
        raise RuntimeError("search run ended without producing a result")

    def _retrieval_llm(self) -> LLMClient | None:
        resolve = getattr(self.llm, "resolve", None)
        if callable(resolve):
            try:
                if getattr(resolve("auto"), "provider", "") == "mock":
                    return None
            except Exception:
                pass
        available = getattr(self.llm, "available", None)
        if not callable(available):
            return None
        try:
            return self.llm if available("auto") else None
        except TypeError:
            try:
                return self.llm if available() else None
            except Exception:
                return None
        except Exception:
            return None

    def extract(
        self,
        works: WorkList | list[WorkItem],
        *,
        model: str = "auto",
        overwrite: bool = False,
        retain_pdfs: bool = False,
        pdf_dir: str | Path | None = None,
        max_chars: int = 24_000,
        continue_on_error: bool = False,
        show_progress: bool = False,
        callback: ProgressCallback | None = None,
        cancel_token: CancelToken | None = None,
    ) -> ExtractedFeatures:
        items = list(works.items if isinstance(works, WorkList) else works)
        model_label = self.llm.resolve(model).label
        with RunHandle(
            self.storage,
            "research.extract",
            callback=callback,
            token=cancel_token,
            show_progress=show_progress,
        ) as run:
            features: list[WorkFeatures] = []
            total = max(1, len(items))
            for index, work in enumerate(items, start=1):
                start_progress = (index - 1) / total
                end_progress = index / total
                run.update(
                    "extract_work",
                    f"Extracting {index}/{len(items)}: {work.title[:80]}",
                    progress=start_progress,
                    work_id=work.id,
                    current=index,
                    total=len(items),
                    extracted=len(features),
                )
                self.storage.save_work(work)
                text, retained_path = fetch_transient_full_text(
                    work,
                    retain_pdf_dir=Path(pdf_dir) if pdf_dir else (self.storage.artifacts_dir / "pdfs" if retain_pdfs else None),
                    retain_pdfs=retain_pdfs or bool(pdf_dir),
                    max_chars=max_chars,
                )
                content_hash = self.storage.content_hash(work, text)
                cached = self.storage.get_extraction(work.id, model_label, content_hash)
                if cached and not overwrite:
                    cached.skipped = True
                    features.append(cached)
                    run.update(
                        "extract_work",
                        f"Skipped cached extraction {index}/{len(items)}: {work.title[:80]}",
                        progress=end_progress,
                        current=index,
                        total=len(items),
                        extracted=len(features),
                        skipped=sum(1 for item in features if item.skipped),
                    )
                    continue
                try:
                    extracted = self._extract_one(
                        work,
                        text,
                        model=model,
                        run=run,
                        progress_start=start_progress + (end_progress - start_progress) * 0.15,
                        progress_end=start_progress + (end_progress - start_progress) * 0.95,
                        current=index,
                        total=len(items),
                    )
                except Exception as exc:  # noqa: BLE001
                    if not continue_on_error:
                        raise
                    self.storage.log_event(run.status.run_id, "extract_warning", f"{work.id} failed: {exc}")
                    run.update(
                        "extract_work_failed",
                        f"Skipped failed extraction {index}/{len(items)}: {work.title[:80]}",
                        progress=end_progress,
                        current=index,
                        total=len(items),
                        extracted=len(features),
                        failed=1,
                        error=str(exc)[:500],
                    )
                    continue
                extracted.source_excerpt_chars = len(text)
                extracted.retained_pdf_path = str(retained_path or "")
                extracted.extraction_id = short_hash(work.id, model_label, content_hash, length=16)
                self.storage.save_extraction(extracted, content_hash)
                features.append(extracted)
                run.update(
                    "extract_work",
                    f"Completed extraction {index}/{len(items)}: {work.title[:80]}",
                    progress=end_progress,
                    current=index,
                    total=len(items),
                    extracted=len(features),
                )
            result = ExtractedFeatures(items=features, model=model_label, run_id=run.status.run_id)
            run.update("complete", f"Extracted features for {len(features)} work(s).", progress=0.98, extracted=len(features))
            return result
        raise RuntimeError("extraction run ended without producing a result")

    def _extract_one(
        self,
        work: WorkItem,
        text: str,
        *,
        model: str,
        run: RunHandle | None = None,
        progress_start: float = 0.0,
        progress_end: float = 1.0,
        current: int = 1,
        total: int = 1,
    ) -> WorkFeatures:
        evidence_text = text or work.abstract
        if self.llm.available(model) and self.llm.resolve(model).provider != "mock":
            system = "You extract source-grounded research features from one paper. Return strict JSON only."
            user = (
                "Return keys: ideas, principles, takeaways, benchmarks, baselines, result_facts. "
                "For existed ideas use fields title, core_idea, mechanism, discussion, evidence. "
                "For principles use fields name, argument, boundary_conditions, discussion, evidence. "
                "For takeaways use fields title, message, condition, actionable_lesson, evidence. "
                "Each item must be grounded in the supplied work text and include evidence when possible. "
                "Do not invent performance numbers or citations.\n\n"
                f"Work: {json.dumps(work.model_dump(), ensure_ascii=False)}\n\n"
                f"Source text excerpt:\n{evidence_text[:24000]}"
            )
            def call() -> dict[str, Any]:
                return self.llm.chat_json(system, user, model=model, max_tokens=2600, temperature=0.1)

            if run:
                payload = call_with_progress(
                    run,
                    stage="llm_extract",
                    message=f"Calling LLM for {current}/{total}: {work.title[:72]}",
                    progress_start=progress_start,
                    progress_end=progress_end,
                    estimated_seconds=90,
                    call=call,
                )
            else:
                payload = call()
        elif self.llm.resolve(model).provider == "mock":
            payload = self.llm.chat_json("extract", evidence_text, model=model)
        else:
            payload = deterministic_features(work, evidence_text)
        return WorkFeatures(
            work_id=work.id,
            title=work.title,
            model=self.llm.resolve(model).label,
            ideas=normalize_feature_records(payload.get("ideas") or payload.get("existed_ideas"), "idea"),
            principles=normalize_feature_records(payload.get("principles"), "principle"),
            baselines=normalize_feature_records(payload.get("baselines"), "baseline"),
            benchmarks=normalize_feature_records(payload.get("benchmarks"), "benchmark"),
            takeaways=normalize_feature_records(payload.get("takeaways") or payload.get("takeaway_messages"), "takeaway"),
            result_facts=normalize_feature_records(payload.get("result_facts"), "result_fact"),
        )


def coerce_work(item: dict[str, Any] | WorkItem) -> WorkItem:
    if isinstance(item, WorkItem):
        return item
    title = clean_text(item.get("title") or item.get("display_name") or "Untitled work")
    return WorkItem(
        id=str(item.get("id") or item.get("work_id") or readable_id(title)),
        title=title,
        authors=[clean_text(author) for author in item.get("authors", []) if clean_text(author)],
        abstract=clean_text(item.get("abstract") or ""),
        published_at=str(item.get("published_at") or item.get("published") or ""),
        year=item.get("year"),
        venue=clean_text(item.get("venue") or item.get("venue_or_source") or item.get("source") or ""),
        source=str(item.get("source") or item.get("provider") or ""),
        source_type=str(item.get("source_type") or "paper"),
        url=str(item.get("url") or item.get("url_or_doi") or item.get("paper_link") or ""),
        doi=clean_doi(item.get("doi") or item.get("DOI") or ""),
        arxiv_id=str(item.get("arxiv_id") or extract_arxiv_id(str(item.get("url") or item.get("url_or_doi") or ""))),
        openalex_id=str(item.get("openalex_id") or ""),
        source_urls=list(item.get("source_urls") or []),
        citation_count=item.get("citation_count"),
        metadata=dict(item.get("metadata") or item.get("community_signals") or {}),
    )


def dedupe_works(works: list[WorkItem]) -> list[WorkItem]:
    output: list[WorkItem] = []
    key_to_index: dict[str, int] = {}
    existing_ids: set[str] = set()
    for work in works:
        keys = identity_keys(work)
        if not keys:
            keys = [f"title:{normalize_key(work.title)}"]
        match_index = next((key_to_index[key] for key in keys if key in key_to_index), None)
        if match_index is not None:
            output[match_index] = merge_work_records(output[match_index], work)
            for key in identity_keys(output[match_index]):
                key_to_index[key] = match_index
            continue
        if work.id in existing_ids:
            work.id = readable_id(work.title, existing=existing_ids)
        existing_ids.add(work.id)
        index = len(output)
        output.append(work)
        for key in keys:
            key_to_index[key] = index
    return output


def identity_keys(work: WorkItem) -> list[str]:
    title_key = normalize_key(work.title)
    keys = []
    if work.doi:
        keys.append(f"doi:{work.doi.lower()}")
    if work.arxiv_id:
        keys.append(f"arxiv:{work.arxiv_id.lower()}")
    if work.openalex_id:
        keys.append(f"openalex:{work.openalex_id.lower()}")
    if title_key:
        keys.append(f"title:{title_key}")
    return keys


def merge_work_records(current: WorkItem, candidate: WorkItem) -> WorkItem:
    preferred = preferred_work(current, candidate)
    secondary = candidate if preferred is current else current
    metadata = {**secondary.metadata, **preferred.metadata}
    merged_sources = unique_strings(
        [
            *(current.metadata.get("merged_sources") or []),
            *(candidate.metadata.get("merged_sources") or []),
            current.source,
            candidate.source,
        ]
    )
    metadata["merged_sources"] = merged_sources
    if is_peer_reviewed_work(current) or is_peer_reviewed_work(candidate):
        metadata["is_peer_reviewed"] = True
    if is_preprint_work(current) or is_preprint_work(candidate):
        metadata["has_preprint"] = True
    peer_venue = peer_reviewed_venue(current) or peer_reviewed_venue(candidate)
    if peer_venue:
        metadata["peer_reviewed_venue"] = peer_venue
    source_urls = unique_strings(
        [
            preferred.url,
            secondary.url,
            *preferred.source_urls,
            *secondary.source_urls,
        ]
    )
    return preferred.model_copy(
        update={
            "id": preferred.id or current.id or candidate.id,
            "authors": preferred.authors or secondary.authors,
            "abstract": preferred.abstract if len(preferred.abstract) >= len(secondary.abstract) else secondary.abstract,
            "published_at": preferred.published_at or secondary.published_at,
            "year": preferred.year or secondary.year,
            "venue": peer_venue or preferred.venue or secondary.venue,
            "source": preferred.source or secondary.source,
            "source_type": preferred.source_type or secondary.source_type,
            "url": preferred.url or secondary.url,
            "doi": preferred.doi or secondary.doi,
            "arxiv_id": preferred.arxiv_id or secondary.arxiv_id,
            "openalex_id": preferred.openalex_id or secondary.openalex_id,
            "source_urls": source_urls,
            "citation_count": max_optional_int(preferred.citation_count, secondary.citation_count),
            "metadata": metadata,
        }
    )


def preferred_work(left: WorkItem, right: WorkItem) -> WorkItem:
    left_key = work_preference_key(left)
    right_key = work_preference_key(right)
    return right if right_key > left_key else left


def work_preference_key(work: WorkItem) -> tuple[int, int, int, int]:
    return (
        1 if is_peer_reviewed_work(work) else 0,
        venue_quality(work),
        source_preference(work.source),
        int(work.citation_count or 0),
    )


def venue_quality(work: WorkItem) -> int:
    if is_peer_reviewed_work(work):
        return 3
    venue = normalize_key(work.venue)
    if not venue or venue in {"arxiv", "openalex", "crossref"}:
        return 0
    if is_preprint_work(work):
        return 0
    return 1


def source_preference(source: str) -> int:
    return {"crossref": 3, "openalex": 2, "arxiv": 1}.get(str(source or "").lower(), 0)


def search_rank_score(query: str, work: WorkItem) -> float:
    relevance = lexical_score(query, f"{work.title} {work.abstract}")
    peer_bonus = 0.35 if is_peer_reviewed_work(work) else 0.0
    venue_bonus = 0.12 if venue_quality(work) >= 2 else 0.0
    citation_bonus = min(0.15, (work.citation_count or 0) / 1000)
    arxiv_penalty = 0.12 if is_preprint_work(work) and not is_peer_reviewed_work(work) else 0.0
    return relevance + peer_bonus + venue_bonus + citation_bonus - arxiv_penalty


def is_peer_reviewed_work(work: WorkItem) -> bool:
    value = work.metadata.get("is_peer_reviewed")
    if isinstance(value, bool):
        return value
    publication_type = normalize_key(str(work.metadata.get("publication_type") or work.metadata.get("type") or ""))
    if publication_type in PEER_REVIEWED_TYPES:
        return True
    return bool(peer_reviewed_venue(work))


def is_preprint_work(work: WorkItem) -> bool:
    if bool(work.metadata.get("is_preprint")):
        return True
    source = normalize_key(work.source)
    venue = normalize_key(work.venue)
    publication_type = normalize_key(str(work.metadata.get("publication_type") or work.metadata.get("type") or ""))
    return source == "arxiv" or venue == "arxiv" or publication_type in PREPRINT_TYPES


def is_peer_reviewed_metadata(publication_type: str, venue: str, url: str, source_type: str = "") -> bool:
    venue_key = normalize_key(venue)
    type_key = normalize_key(publication_type)
    source_type_key = normalize_key(source_type)
    if is_preprint_metadata(publication_type, venue, url, source_type):
        return False
    if not venue_key or venue_key in {"openalex", "crossref", "arxiv"}:
        return False
    return type_key in PEER_REVIEWED_TYPES or source_type_key in PEER_REVIEWED_SOURCE_TYPES


def is_preprint_metadata(publication_type: str, venue: str, url: str, source_type: str = "") -> bool:
    type_key = normalize_key(publication_type)
    venue_key = normalize_key(venue)
    source_type_key = normalize_key(source_type)
    url_lower = str(url or "").lower()
    return (
        type_key in PREPRINT_TYPES
        or source_type_key in PREPRINT_TYPES
        or venue_key == "arxiv"
        or "arxiv.org" in url_lower
    )


def peer_reviewed_venue(work: WorkItem) -> str:
    venue = clean_text(work.venue)
    if not venue:
        return ""
    if normalize_key(venue) in {"arxiv", "openalex", "crossref"}:
        return ""
    if is_preprint_work(work) and not bool(work.metadata.get("is_peer_reviewed")):
        return ""
    if work.metadata.get("is_peer_reviewed") or source_preference(work.source) >= 2:
        return venue
    return ""


PEER_REVIEWED_TYPES = {
    "journal article",
    "journal-article",
    "proceedings article",
    "proceedings-article",
    "conference paper",
    "conference-paper",
    "book chapter",
    "book-chapter",
    "book",
    "monograph",
}

PEER_REVIEWED_SOURCE_TYPES = {
    "journal",
    "conference",
    "book",
}

PREPRINT_TYPES = {
    "posted content",
    "posted-content",
    "preprint",
    "repository",
}


def max_optional_int(left: int | None, right: int | None) -> int | None:
    values = [value for value in (left, right) if value is not None]
    return max(values) if values else None


def unique_strings(values: list[Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        output.append(text)
        seen.add(text)
    return output


def normalize_feature_records(value: Any, kind: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    rows = value if isinstance(value, list) else [value]
    output: list[dict[str, Any]] = []
    existing_ids: set[str] = set()
    for row in rows:
        record = normalize_feature_record(row, kind)
        if not record:
            continue
        seed = feature_seed(record, kind)
        if not record.get("id"):
            record["id"] = readable_id(seed, existing=existing_ids, max_len=80)
        elif str(record["id"]) in existing_ids:
            record["id"] = readable_id(str(record["id"]), existing=existing_ids, max_len=80)
        else:
            record["id"] = readable_id(str(record["id"]), existing=existing_ids, max_len=80)
        existing_ids.add(str(record["id"]))
        output.append(record)
    return output


def normalize_feature_record(row: Any, kind: str) -> dict[str, Any]:
    if isinstance(row, dict):
        record = {str(key): value for key, value in row.items() if value is not None}
        return canonical_feature_record(record, kind)
    text = clean_text(row)
    if not text:
        return {}
    if kind == "idea":
        return {"title": text[:120], "core_idea": text}
    if kind == "principle":
        return {"name": text[:120], "argument": text}
    if kind in {"baseline", "benchmark"}:
        return {"name": text[:120], "description": text}
    if kind == "takeaway":
        return {"title": text[:120], "message": text}
    if kind == "result_fact":
        return {"fact": text}
    return {"value": text}


def canonical_feature_record(record: dict[str, Any], kind: str) -> dict[str, Any]:
    if kind == "idea":
        ensure_key(record, "title", ["name", "idea_title", "core_idea", "idea_text", "summary"])
        ensure_key(record, "core_idea", ["idea_text", "description", "summary", "mechanism", "discussion"])
    elif kind == "principle":
        ensure_key(record, "name", ["title", "principle", "abstract_signature", "argument"])
        ensure_key(record, "argument", ["principle", "abstract_signature", "description", "summary", "discussion"])
    elif kind == "takeaway":
        ensure_key(record, "title", ["name", "main_results", "message_text", "message", "actionable_lesson"])
        ensure_key(record, "message", ["message_text", "main_results", "actionable_lesson", "condition", "discussion", "summary"])
    elif kind in {"baseline", "benchmark"}:
        ensure_key(record, "name", ["title", f"{kind}_name", "core_idea", "description", "task"])
        ensure_key(record, "description", ["summary", "core_idea", "methodology", "task", "discussion"])
    elif kind == "result_fact":
        ensure_key(record, "fact", ["finding", "result", "description", "summary"])
    return record


def ensure_key(record: dict[str, Any], target: str, candidates: list[str]) -> None:
    if clean_text(record.get(target)):
        return
    for key in candidates:
        value = clean_text(record.get(key))
        if value:
            record[target] = value
            return


def feature_seed(record: dict[str, Any], kind: str) -> str:
    for key in ("title", "name", "core_idea", "message", "fact", "description", "argument", "value"):
        value = clean_text(record.get(key))
        if value:
            return value
    return kind


def search_arxiv(query: str, limit: int, timeout: float) -> list[dict[str, Any]]:
    import xml.etree.ElementTree as ET

    params = urllib.parse.urlencode(
        {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": max(1, min(limit, 100)),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
    )
    url = f"https://export.arxiv.org/api/query?{params}"
    data = httpx.get(url, timeout=timeout, headers={"User-Agent": "Principia-v1.3"}).content
    root = ET.fromstring(data)
    ns = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    works = []
    for entry in root.findall("a:entry", ns):
        title = clean_text(entry.findtext("a:title", default="", namespaces=ns))
        abstract = clean_text(entry.findtext("a:summary", default="", namespaces=ns))
        published = entry.findtext("a:published", default="", namespaces=ns) or ""
        year_match = re.match(r"(\d{4})", published)
        url_or_doi = entry.findtext("a:id", default="", namespaces=ns) or ""
        authors = [
            clean_text(author.findtext("a:name", default="", namespaces=ns))
            for author in entry.findall("a:author", ns)
        ]
        works.append(
            {
                "id": readable_id(title),
                "title": title,
                "authors": authors,
                "abstract": abstract,
                "published_at": published,
                "year": int(year_match.group(1)) if year_match else None,
                "venue": "arXiv",
                "source": "arxiv",
                "source_type": "preprint",
                "url": url_or_doi,
                "arxiv_id": extract_arxiv_id(url_or_doi),
                "source_urls": [url_or_doi],
                "metadata": {
                    "is_preprint": True,
                    "is_peer_reviewed": False,
                    "publication_type": "preprint",
                },
            }
        )
    return works


def search_openalex(query: str, limit: int, timeout: float) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({"search": query, "per-page": max(1, min(limit, 100)), "sort": "relevance_score:desc"})
    data = httpx.get(f"https://api.openalex.org/works?{params}", timeout=timeout, headers={"User-Agent": "Principia-v1.3"}).json()
    works = []
    for item in data.get("results", []) if isinstance(data, dict) else []:
        title = clean_text(item.get("title") or item.get("display_name") or "")
        if not title:
            continue
        authors = [
            clean_text((authorship.get("author") or {}).get("display_name") or "")
            for authorship in item.get("authorships", [])[:12]
            if isinstance(authorship, dict)
        ]
        primary = item.get("primary_location") or {}
        best_location = best_openalex_location(item)
        source = best_location.get("source") or {}
        primary_source = primary.get("source") or {}
        venue = clean_text(source.get("display_name") or primary_source.get("display_name") or "OpenAlex")
        publication_type = str(item.get("type") or item.get("type_crossref") or "")
        source_type = str(source.get("type") or primary_source.get("type") or "")
        landing_url = best_location.get("landing_page_url") or primary.get("landing_page_url") or item.get("doi") or item.get("id") or ""
        is_preprint = is_preprint_metadata(publication_type, venue, landing_url, source_type)
        is_peer = is_peer_reviewed_metadata(publication_type, venue, landing_url, source_type)
        works.append(
            {
                "id": readable_id(title),
                "title": title,
                "authors": [name for name in authors if name],
                "abstract": openalex_abstract(item.get("abstract_inverted_index") or {}),
                "year": item.get("publication_year"),
                "venue": venue,
                "source": "openalex",
                "source_type": publication_type or source_type or "paper",
                "url": landing_url,
                "doi": item.get("doi") or "",
                "arxiv_id": extract_arxiv_id(landing_url),
                "openalex_id": item.get("id") or "",
                "citation_count": item.get("cited_by_count"),
                "source_urls": unique_strings([landing_url, primary.get("landing_page_url"), item.get("doi"), item.get("id")]),
                "metadata": {
                    "is_peer_reviewed": is_peer,
                    "is_preprint": is_preprint,
                    "publication_type": publication_type,
                    "venue_source_type": source_type,
                },
            }
        )
    return works


def best_openalex_location(item: dict[str, Any]) -> dict[str, Any]:
    primary = item.get("primary_location") or {}
    locations = [loc for loc in [primary, *(item.get("locations") or [])] if isinstance(loc, dict)]
    for location in locations:
        source = location.get("source") or {}
        venue = clean_text(source.get("display_name") or "")
        source_type = str(source.get("type") or "")
        url = str(location.get("landing_page_url") or "")
        if is_peer_reviewed_metadata(str(item.get("type") or ""), venue, url, source_type):
            return location
    return primary if isinstance(primary, dict) else {}


def search_crossref(query: str, limit: int, timeout: float) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({"query": query, "rows": max(1, min(limit, 100)), "sort": "relevance"})
    data = httpx.get(f"https://api.crossref.org/works?{params}", timeout=timeout, headers={"User-Agent": "Principia-v1.3"}).json()
    items = (((data or {}).get("message") or {}).get("items") or []) if isinstance(data, dict) else []
    works = []
    for item in items:
        title = clean_text(" ".join(item.get("title") or []))
        if not title:
            continue
        year_parts = (((item.get("published-print") or item.get("published-online") or item.get("issued") or {}).get("date-parts") or [[]])[0])
        year = year_parts[0] if year_parts and isinstance(year_parts[0], int) else None
        doi = item.get("DOI") or ""
        url = item.get("URL") or (f"https://doi.org/{doi}" if doi else "")
        publication_type = str(item.get("type") or "")
        venue = clean_text(" ".join(item.get("container-title") or []) or item.get("publisher") or "Crossref")
        is_preprint = is_preprint_metadata(publication_type, venue, url, "")
        is_peer = is_peer_reviewed_metadata(publication_type, venue, url, "")
        authors = []
        for author in item.get("author", [])[:12]:
            name = " ".join(part for part in [author.get("given", ""), author.get("family", "")] if part).strip()
            if name:
                authors.append(name)
        works.append(
            {
                "id": readable_id(title),
                "title": title,
                "authors": authors,
                "abstract": strip_tags(item.get("abstract") or ""),
                "year": year,
                "venue": venue,
                "source": "crossref",
                "source_type": publication_type or "paper",
                "url": url,
                "doi": doi,
                "arxiv_id": extract_arxiv_id(url),
                "citation_count": item.get("is-referenced-by-count"),
                "source_urls": [url],
                "metadata": {
                    "is_peer_reviewed": is_peer,
                    "is_preprint": is_preprint,
                    "publication_type": publication_type,
                },
            }
        )
    return works


def fetch_transient_full_text(
    work: WorkItem,
    *,
    retain_pdf_dir: Path | None = None,
    retain_pdfs: bool = False,
    max_chars: int = 24_000,
    timeout: float = 12.0,
) -> tuple[str, Path | None]:
    for url in candidate_full_text_urls(work)[:3]:
        try:
            response = httpx.get(url, timeout=timeout, follow_redirects=True, headers={"User-Agent": "Principia-v1.3", "Accept": "application/pdf,text/html,*/*"})
            response.raise_for_status()
        except Exception:
            continue
        body = response.content[:12_000_000]
        content_type = response.headers.get("Content-Type", "")
        retained_path = None
        if "pdf" in content_type.lower() or url.lower().endswith(".pdf") or body[:4] == b"%PDF":
            if retain_pdfs and retain_pdf_dir:
                retain_pdf_dir.mkdir(parents=True, exist_ok=True)
                retained_path = retain_pdf_dir / f"{readable_id(work.title, max_len=80)}_{short_hash(url, length=8)}.pdf"
                retained_path.write_bytes(body)
            text = pdf_bytes_to_text(body, max_chars=max_chars)
        else:
            text = html_to_text(body.decode("utf-8", errors="replace"))[:max_chars]
        if len(text) >= 400:
            return text, retained_path
    return "", None


def deterministic_features(work: WorkItem, text: str) -> dict[str, Any]:
    body = clean_text(text or work.abstract or work.title)
    summary = body[:520] or work.title
    title_seed = work.title
    return {
        "ideas": [
            {
                "id": readable_id(f"{title_seed} reusable idea"),
                "title": f"Reusable mechanism in {title_seed[:80]}",
                "core_idea": summary,
                "evidence": summary,
            }
        ],
        "principles": [
            {
                "id": readable_id(f"{title_seed} principle"),
                "name": f"Evidence principle from {title_seed[:72]}",
                "argument": "A reusable research mechanism should be tied to source evidence, a target pressure, and a validation condition.",
                "evidence": summary,
            }
        ],
        "takeaways": [
            {
                "id": readable_id(f"{title_seed} takeaway"),
                "title": "Source-grounded takeaway",
                "message": summary,
            }
        ],
        "benchmarks": extract_named_records(body, ["benchmark", "dataset", "evaluation"]),
        "baselines": extract_named_records(body, ["baseline", "compare", "ablation"]),
        "result_facts": [],
    }


def extract_named_records(text: str, triggers: list[str]) -> list[dict[str, str]]:
    lower = text.lower()
    if not any(trigger in lower for trigger in triggers):
        return []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    rows = []
    for sentence in sentences:
        if any(trigger in sentence.lower() for trigger in triggers):
            rows.append({"name": clean_text(sentence[:120]), "evidence": clean_text(sentence[:420])})
        if len(rows) >= 4:
            break
    return rows


def candidate_full_text_urls(work: WorkItem) -> list[str]:
    urls = [work.url, *work.source_urls]
    output = []
    for url in urls:
        url = str(url or "")
        arxiv_id = extract_arxiv_id(url)
        if arxiv_id:
            output.append(f"https://arxiv.org/pdf/{arxiv_id}")
        if url:
            output.append(url)
    return list(dict.fromkeys(output))


def pdf_bytes_to_text(body: bytes, *, max_chars: int) -> str:
    try:
        reader = PdfReader(io.BytesIO(body))
        chunks = []
        for page in reader.pages[:20]:
            chunks.append(page.extract_text() or "")
            if sum(len(chunk) for chunk in chunks) >= max_chars:
                break
        return clean_text(" ".join(chunks))[:max_chars]
    except Exception:
        return ""


def openalex_abstract(index: dict[str, list[int]]) -> str:
    if not isinstance(index, dict) or not index:
        return ""
    pairs = []
    for token, positions in index.items():
        for pos in positions:
            pairs.append((pos, token))
    pairs.sort()
    return clean_text(" ".join(token for _, token in pairs))


def lexical_score(query: str, text: str) -> float:
    q = meaningful_tokens(query)
    t = set(meaningful_tokens(text))
    if not q or not t:
        return 0.0
    matched = [token for token in q if token in t]
    coverage = sum(token_weight(token) for token in matched) / max(1.0, sum(token_weight(token) for token in q))
    phrase_bonus = 0.0
    normalized_text = f" {normalize_key(text)} "
    for phrase in query_phrases(query):
        if f" {phrase} " in normalized_text:
            phrase_bonus += 0.08
    return coverage + min(0.4, phrase_bonus)


def compact_search_query(query: str, *, max_terms: int = 12) -> str:
    tokens = expand_search_tokens(meaningful_tokens(query))
    if not tokens:
        return clean_text(query)
    scored = sorted(dict.fromkeys(tokens), key=lambda token: (-token_weight(token), tokens.index(token)))
    return " ".join(scored[:max_terms])


def expand_search_tokens(tokens: list[str]) -> list[str]:
    expanded = list(tokens)
    token_set = set(tokens)
    if {"coding", "repository"} & token_set or {"code", "repository"} <= token_set:
        expanded.extend(["software", "engineering", "code", "review", "llm", "benchmark"])
    if "agent" in token_set and ("coding" in token_set or "code" in token_set):
        expanded.extend(["llm", "software", "repository", "swe"])
    return expanded


def meaningful_tokens(text: str) -> list[str]:
    tokens = []
    for token in normalize_key(text).split():
        token = canonical_token(token)
        if len(token) < 3 or token in SEARCH_STOPWORDS:
            continue
        tokens.append(token)
    return tokens


def canonical_token(token: str) -> str:
    if token.endswith("ies") and len(token) > 4:
        return f"{token[:-3]}y"
    if token.endswith("s") and len(token) > 4:
        return token[:-1]
    return token


def token_weight(token: str) -> float:
    if token in {"coding", "code", "software", "repository", "repo", "swe"}:
        return 5.0
    if token in {"llm", "review", "engineering"}:
        return 4.0
    if token in {"benchmark", "evaluation"}:
        return 3.0
    if token in {"calibrated", "calibration", "quality", "process", "benchmark", "evaluation"}:
        return 2.0
    if len(token) >= 8:
        return 1.5
    return 1.0


def query_phrases(query: str) -> list[str]:
    normalized = normalize_key(query)
    phrases = []
    for raw in ("coding agents", "software engineering", "large scale repositories", "quality control", "autonomous coding"):
        phrase = normalize_key(raw)
        if phrase in normalized:
            phrases.append(phrase)
    return phrases


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def strip_tags(value: str) -> str:
    return clean_text(re.sub(r"<[^>]+>", " ", str(value or "")))


def html_to_text(value: str) -> str:
    value = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", value)
    return strip_tags(value)


def extract_arxiv_id(value: str) -> str:
    match = re.search(r"arxiv\.org/(?:abs|pdf)/([^?#/\s]+)", value, flags=re.I)
    if not match:
        match = re.search(r"\barxiv:([0-9]{4}\.[0-9]{4,5}(?:v\d+)?)", value, flags=re.I)
    return match.group(1).removesuffix(".pdf") if match else ""


def clean_doi(value: Any) -> str:
    text = str(value or "").strip()
    text = text.removeprefix("https://doi.org/").removeprefix("http://doi.org/")
    return text.lower()
