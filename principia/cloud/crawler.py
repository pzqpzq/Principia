from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..models import utc_now
from ..utils import stable_id


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
) -> dict[str, Any]:
    topics = topics or []
    priority_rules = priority_rules or ["venue", "recency", "topic"]
    normalized = [normalize_venue(venue) for venue in venues if venue]
    candidates = []
    for venue in normalized:
        for year in years:
            for idx in range(max(1, min(max_papers, 10))):
                title = f"{venue} {year} candidate {idx + 1}"
                candidate = {
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
                    "crawl_status": "planned",
                }
                candidates.append(candidate)
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
        "execution_mode": "dry_run_plan" if dry_run else "authorized_operation_pack",
        "next_step": "Run the plan through local research/extraction, then export a contribution pack.",
    }


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
