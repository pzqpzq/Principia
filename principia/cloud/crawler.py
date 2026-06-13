from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..research_sources import search_hybrid_sources
from ..models import utc_now
from ..utils import compact_text, lexical_score, stable_id


VENUE_ALIASES = {
    "acl": "ACL",
    "cvpr": "CVPR",
    "eccv": "ECCV",
    "emnlp": "EMNLP",
    "iccv": "ICCV",
    "iclr": "ICLR",
    "icml": "ICML",
    "jmlr": "JMLR",
    "nmi": "Nature Machine Intelligence",
    "ncs": "Nature Computational Science",
    "neurips": "NeurIPS",
    "tpami": "TPAMI",
    "pami": "TPAMI",
}


@dataclass
class RateLimiter:
    min_interval_seconds: float
    max_concurrency: int = 1


def normalize_venue(value: str) -> str:
    text = str(value or "").strip()
    return VENUE_ALIASES.get(text.lower(), text)


def plan_crawl(
    *,
    venues: list[str],
    years: list[int],
    topics: list[str] | None = None,
    priority_rules: list[str] | None = None,
    max_papers: int = 100,
    model_key: str = "",
    dry_run: bool = True,
    live: bool = False,
    timeout: int = 12,
) -> dict[str, Any]:
    topics = topics or []
    priority_rules = priority_rules or ["venue", "recency", "topic"]
    normalized = [normalize_venue(venue) for venue in venues if venue]
    max_papers = max(1, min(int(max_papers or 100), 1000))
    metadata_warnings: list[str] = []
    candidates = _live_metadata_candidates(
        venues=normalized,
        years=years,
        topics=topics,
        priority_rules=priority_rules,
        max_papers=max_papers,
        timeout=timeout,
        warnings=metadata_warnings,
    ) if live else []
    if not candidates:
        candidates = _fallback_candidates(normalized, years, topics, priority_rules, max_papers, live=live)
    candidates.sort(key=lambda item: item["priority_score"], reverse=True)
    candidates = candidates[:max_papers]
    return {
        "plan_id": stable_id("CRAWL", ",".join(normalized), ",".join(map(str, years)), max_papers, model_key),
        "created_at": utc_now(),
        "dry_run": dry_run,
        "venues": normalized,
        "years": years,
        "topics": topics,
        "priority_rules": priority_rules,
        "model_key": model_key,
        "max_papers": max_papers,
        "candidates": candidates,
        "live_metadata": live,
        "metadata_candidate_count": len(candidates),
        "metadata_warnings": metadata_warnings,
        "execution_mode": "live_metadata_plan" if dry_run else "local_research_run",
        "next_step": "Run local extraction for selected candidates, then prepare a contribution pack for PR export.",
    }


def _live_metadata_candidates(
    *,
    venues: list[str],
    years: list[int],
    topics: list[str],
    priority_rules: list[str],
    max_papers: int,
    timeout: int,
    warnings: list[str],
) -> list[dict[str, Any]]:
    queries = _metadata_queries(venues, years, topics)
    if not queries:
        return []
    seen: set[str] = set()
    candidates: list[dict[str, Any]] = []
    per_query = max(20, min(100, max_papers * 3))
    for query in queries:
        try:
            works = search_hybrid_sources(query["query"], max_results=per_query, timeout=max(3, min(int(timeout or 12), 30)))
        except Exception as exc:
            warnings.append(f"Metadata search failed for {query['query']}: {exc}")
            continue
        for idx, work in enumerate(works):
            title = compact_text(work.get("title") or "", 240)
            if not title:
                continue
            dedupe_key = str(work.get("work_id") or "").strip() or title.lower()
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            candidate = dict(work)
            venue = str(candidate.get("venue_or_source") or query["venue"] or "").strip()
            year = _safe_int(candidate.get("year")) or _safe_int(query["year"])
            candidate.update(
                {
                    "work_id": candidate.get("work_id") or stable_id("W", title),
                    "title": title,
                    "abstract": compact_text(candidate.get("abstract") or "", 2400),
                    "year": year,
                    "venue_or_source": venue or query["venue"],
                    "source_type": candidate.get("source_type") or "paper",
                    "source_provider": candidate.get("source_provider") or "hybrid_public_metadata",
                    "source_record_id": candidate.get("source_record_id") or stable_id("SRC", title, venue, year),
                    "priority_score": _metadata_priority(candidate, query, idx, topics, priority_rules),
                    "priority_reason": _priority_reason(candidate, query, topics, priority_rules),
                    "target_venue": query["venue"],
                    "target_year": query["year"],
                    "crawl_status": "metadata_candidate",
                    "cloud_crawl_query": query["query"],
                }
            )
            candidates.append(candidate)
            if len(candidates) >= max_papers * 5:
                return candidates
    return candidates


def _metadata_queries(venues: list[str], years: list[int], topics: list[str]) -> list[dict[str, Any]]:
    normalized_years = [int(year) for year in years if _safe_int(year)]
    topic_text = " ".join(topics).strip()
    queries: list[dict[str, Any]] = []
    for venue in venues or ["AI machine learning"]:
        for year in normalized_years or []:
            base = " ".join(part for part in [topic_text, venue, str(year), "AI machine learning research paper"] if part)
            queries.append({"query": base, "venue": venue, "year": year})
    if not queries and topic_text:
        queries.append({"query": f"{topic_text} AI machine learning research paper", "venue": "", "year": None})
    return queries[: max(1, min(len(queries), 24))]


def _fallback_candidates(
    venues: list[str],
    years: list[int],
    topics: list[str],
    priority_rules: list[str],
    max_papers: int,
    *,
    live: bool,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for venue in venues or ["AI"]:
        for year in years or [0]:
            for idx in range(max(1, min(max_papers, 10))):
                title = f"{venue} {year} candidate {idx + 1}"
                candidates.append(
                    {
                        "work_id": stable_id("W", venue, year, idx, ",".join(topics)),
                        "title": title,
                        "abstract": "",
                        "year": year,
                        "venue_or_source": venue,
                        "source_type": "paper",
                        "source_provider": "crawler_plan",
                        "source_record_id": stable_id("SRC", venue, year, idx),
                        "priority_score": _priority_score(venue, year, idx, topics, priority_rules),
                        "priority_reason": " / ".join(priority_rules),
                        "crawl_status": "metadata_fallback" if live else "planned",
                    }
                )
    return candidates


def _metadata_priority(candidate: dict[str, Any], query: dict[str, Any], idx: int, topics: list[str], priority_rules: list[str]) -> float:
    venue = str(candidate.get("venue_or_source") or "")
    year = _safe_int(candidate.get("year")) or 0
    score = _priority_score(venue or str(query.get("venue") or ""), year, idx, topics, priority_rules)
    rules = {rule.lower().strip() for rule in priority_rules}
    text = " ".join(
        [
            str(candidate.get("title") or ""),
            str(candidate.get("abstract") or ""),
            str(candidate.get("venue_or_source") or ""),
            str(candidate.get("community_signals") or ""),
        ]
    )
    if query.get("venue") and str(query["venue"]).lower() in text.lower():
        score += 0.12
    if _safe_int(query.get("year")) and _safe_int(query.get("year")) == year:
        score += 0.1
    if topics:
        score += 0.18 * lexical_score(" ".join(topics), text)
    if "citation" in rules or "citations" in rules:
        try:
            score += min(float(candidate.get("citation_count") or 0), 5000.0) / 5000.0 * 0.16
        except Exception:
            pass
    if ("oral" in rules or "spotlight" in rules) and any(term in text.lower() for term in ("oral", "spotlight", "award", "highlight")):
        score += 0.16
    return round(score, 4)


def _priority_reason(candidate: dict[str, Any], query: dict[str, Any], topics: list[str], priority_rules: list[str]) -> str:
    parts = ["/".join(priority_rules)]
    if candidate.get("citation_count") is not None:
        parts.append(f"citations={candidate.get('citation_count')}")
    if topics:
        parts.append("topic_match")
    if query.get("venue"):
        parts.append(f"target={query.get('venue')} {query.get('year') or ''}".strip())
    return " / ".join(part for part in parts if part)


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _priority_score(venue: str, year: int, idx: int, topics: list[str], priority_rules: list[str]) -> float:
    score = 0.0
    rules = {rule.lower().strip() for rule in priority_rules}
    if "venue" in rules:
        score += 0.32 if venue in {"ICML", "NeurIPS", "ICLR", "CVPR", "ACL", "ICCV", "ECCV", "EMNLP"} else 0.22
    if "recency" in rules or "year" in rules:
        score += 0.24 * max(0.0, min(1.0, (year - 2020) / 6))
    if "topic" in rules or "topics" in rules:
        score += 0.18 if topics else 0.08
    if "citation" in rules or "citations" in rules:
        score += 0.12 * (1.0 - idx / 10)
    if "oral" in rules or "spotlight" in rules:
        score += 0.08 * (1.0 - idx / 10)
    return round(score + 0.04 * (1.0 - idx / 10), 4)
