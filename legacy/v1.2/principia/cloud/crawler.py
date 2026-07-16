from __future__ import annotations

import json
import ssl
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from ..research_sources import search_hybrid_sources
from ..models import utc_now
from ..utils import compact_text, enrich_query, lexical_score, query_expansions, stable_id, tokenize


VENUE_ALIASES = {
    "acl": "ACL",
    "annual meeting of the association for computational linguistics": "ACL",
    "cvpr": "CVPR",
    "computer vision and pattern recognition": "CVPR",
    "eccv": "ECCV",
    "european conference on computer vision": "ECCV",
    "emnlp": "EMNLP",
    "empirical methods in natural language processing": "EMNLP",
    "iccv": "ICCV",
    "international conference on computer vision": "ICCV",
    "iclr": "ICLR",
    "international conference on learning representations": "ICLR",
    "icml": "ICML",
    "international conference on machine learning": "ICML",
    "jmlr": "JMLR",
    "journal of machine learning research": "JMLR",
    "nmi": "Nature Machine Intelligence",
    "ncs": "Nature Computational Science",
    "nature machine intelligence": "Nature Machine Intelligence",
    "nature computational science": "Nature Computational Science",
    "neurips": "NeurIPS",
    "nips": "NeurIPS",
    "neural information processing systems": "NeurIPS",
    "conference on neural information processing systems": "NeurIPS",
    "tpami": "TPAMI",
    "pami": "TPAMI",
    "ieee transactions on pattern analysis and machine intelligence": "TPAMI",
}

OPENREVIEW_VENUE_PREFIXES = {
    "ICLR": "ICLR.cc",
    "NeurIPS": "NeurIPS.cc",
    "ICML": "ICML.cc",
}

OPENREVIEW_API = "https://api2.openreview.net/notes"
OPENREVIEW_USER_AGENT = "Principia-v1.1-cloud-crawler (local research workspace)"
OTHER_FILTER_VALUE = "__other__"
DEFAULT_KNOWN_VENUES = [
    "ICLR",
    "NeurIPS",
    "ICML",
    "CVPR",
    "ACL",
    "ICCV",
    "ECCV",
    "EMNLP",
    "AAAI",
    "TPAMI",
    "JMLR",
    "Nature",
    "Science",
    "Nature Machine Intelligence",
    "Nature Computational Science",
]


@dataclass
class RateLimiter:
    min_interval_seconds: float
    max_concurrency: int = 1


def normalize_venue(value: str) -> str:
    text = str(value or "").strip()
    return VENUE_ALIASES.get(text.lower(), text)


def _expand_topics(topics: list[str] | None) -> list[str]:
    output: list[str] = []
    for raw in topics or []:
        text = str(raw or "").strip()
        if not text:
            continue
        output.append(text)
        if "^" in text:
            output.append(text.replace("^", ""))
            output.append(text.replace("^", " "))
        compacted = "".join(ch for ch in text.lower() if ch.isalnum())
        if compacted == "vit3":
            output.extend(["VIT3", "ViT3", "VIT 3", "ViT 3", "vision transformer 3", "vision transformer cubed"])
    return _unique_strings(output)


def plan_crawl(
    *,
    venues: list[str],
    years: list[int],
    venue_other: bool = False,
    known_venues: list[str] | None = None,
    year_other: bool = False,
    known_years: list[int] | None = None,
    topics: list[str] | None = None,
    priority_rules: list[str] | None = None,
    max_papers: int = 100,
    model_key: str = "",
    dry_run: bool = True,
    live: bool = False,
    timeout: int = 12,
) -> dict[str, Any]:
    topics = _expand_topics(topics or [])
    priority_rules = priority_rules or ["venue", "recency", "topic"]
    normalized = [normalize_venue(venue) for venue in venues if str(venue or "").strip() and str(venue or "").strip() != OTHER_FILTER_VALUE]
    normalized = _unique_strings(normalized)
    known_venue_values = _unique_strings([normalize_venue(item) for item in (known_venues or DEFAULT_KNOWN_VENUES) if item])
    normalized_years = _unique_ints(years)
    known_year_values = _unique_ints(known_years or [])
    max_papers = max(1, min(int(max_papers or 100), 1000))
    metadata_warnings: list[str] = []
    candidates = _live_metadata_candidates(
        venues=normalized,
        venue_other=venue_other,
        known_venues=known_venue_values,
        years=normalized_years,
        year_other=year_other,
        known_years=known_year_values,
        topics=topics,
        priority_rules=priority_rules,
        max_papers=max_papers,
        timeout=timeout,
        warnings=metadata_warnings,
    ) if live else []
    candidates = _filter_candidates(
        candidates,
        normalized,
        normalized_years,
        topics,
        venue_other=venue_other,
        known_venues=known_venue_values,
        year_other=year_other,
        known_years=known_year_values,
    )
    if live and not candidates:
        metadata_warnings.append(
            "No public metadata candidates matched the selected venue/year filters. "
            "The live crawler will not fabricate template papers."
        )
    if not live and not candidates:
        candidates = _fallback_candidates(normalized, normalized_years, topics, priority_rules, max_papers, live=live)
    candidates.sort(key=lambda item: item["priority_score"], reverse=True)
    candidates = candidates[:max_papers]
    return {
        "plan_id": stable_id("CRAWL", ",".join(normalized), ",".join(map(str, years)), max_papers, model_key),
        "created_at": utc_now(),
        "dry_run": dry_run,
        "venues": normalized,
        "venue_other": venue_other,
        "known_venues": known_venue_values,
        "years": normalized_years,
        "year_other": year_other,
        "known_years": known_year_values,
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
    venue_other: bool,
    known_venues: list[str],
    years: list[int],
    year_other: bool,
    known_years: list[int],
    topics: list[str],
    priority_rules: list[str],
    max_papers: int,
    timeout: int,
    warnings: list[str],
) -> list[dict[str, Any]]:
    queries = _metadata_queries(venues, years, topics, venue_other=venue_other, year_other=year_other, known_years=known_years)
    if not queries:
        return []
    seen: set[str] = set()
    candidates: list[dict[str, Any]] = []
    for venue in venues:
        for year in [int(item) for item in years if _safe_int(item)]:
            for candidate in _openreview_candidates(venue, year, topics, priority_rules, max_papers=max_papers, timeout=timeout, warnings=warnings):
                key = str(candidate.get("work_id") or "").strip() or str(candidate.get("title") or "").lower()
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(candidate)
                if len(candidates) >= max_papers * 5:
                    return candidates
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
            raw_venue = str(candidate.get("venue_or_source") or candidate.get("venue") or candidate.get("source") or "").strip()
            year = _safe_int(candidate.get("year"))
            query_year = _safe_int(query["year"])
            if query_year and year and year != query_year:
                continue
            year = year or query_year
            abstract = compact_text(candidate.get("abstract") or "", 2400)
            if query.get("venue") and not _candidate_matches_venue(raw_venue, title, abstract, str(query["venue"])):
                continue
            topic_score = _candidate_topic_score({**candidate, "title": title, "abstract": abstract}, topics)
            if topics and not _candidate_matches_topics({**candidate, "title": title, "abstract": abstract}, topics, topic_score=topic_score):
                continue
            venue = _best_candidate_venue(raw_venue, str(query.get("venue") or ""))
            candidate.update(
                {
                    "work_id": candidate.get("work_id") or stable_id("W", title),
                    "title": title,
                    "abstract": abstract,
                    "year": year,
                    "venue_or_source": venue or query["venue"],
                    "source_type": candidate.get("source_type") or "paper",
                    "source_provider": candidate.get("source_provider") or "hybrid_public_metadata",
                    "source_record_id": candidate.get("source_record_id") or stable_id("SRC", title, venue, year),
                    "topic_score": topic_score,
                    "priority_score": _metadata_priority({**candidate, "topic_score": topic_score}, query, idx, topics, priority_rules),
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


def _openreview_candidates(
    venue: str,
    year: int,
    topics: list[str],
    priority_rules: list[str],
    *,
    max_papers: int,
    timeout: int,
    warnings: list[str],
) -> list[dict[str, Any]]:
    canonical = normalize_venue(venue)
    prefix = OPENREVIEW_VENUE_PREFIXES.get(canonical)
    if not prefix or not year:
        return []
    venue_id = f"{prefix}/{year}/Conference"
    limit = max(20, min(200, max_papers * 8))
    params = urllib.parse.urlencode({"content.venueid": venue_id, "limit": limit})
    try:
        data = _fetch_openreview_json(f"{OPENREVIEW_API}?{params}", timeout=max(3, min(int(timeout or 12), 30)))
    except Exception as exc:
        warnings.append(f"OpenReview metadata failed for {canonical} {year}: {exc}")
        return []
    notes = data.get("notes") if isinstance(data, dict) else []
    output: list[dict[str, Any]] = []
    topic_text = " ".join(topics)
    for idx, note in enumerate(notes or []):
        if not isinstance(note, dict):
            continue
        content = note.get("content") if isinstance(note.get("content"), dict) else {}
        title = compact_text(str(_openreview_value(content, "title") or ""), 240)
        if not title:
            continue
        abstract = compact_text(str(_openreview_value(content, "abstract") or ""), 2400)
        authors = _openreview_value(content, "authors") or []
        keywords = _openreview_value(content, "keywords") or []
        forum_id = str(note.get("forum") or note.get("id") or "")
        text = " ".join([title, abstract, " ".join(keywords if isinstance(keywords, list) else [])])
        topic_score = _candidate_topic_score({"title": title, "abstract": abstract, "community_signals": {"keywords": keywords}}, topics) if topic_text else 0.1
        if topics and not _candidate_matches_topics({"title": title, "abstract": abstract, "community_signals": {"keywords": keywords}}, topics, topic_score=topic_score):
            continue
        candidate = {
            "work_id": stable_id("W", title),
            "title": title,
            "authors": authors if isinstance(authors, list) else [],
            "abstract": abstract,
            "year": year,
            "venue_or_source": canonical,
            "url_or_doi": f"https://openreview.net/forum?id={forum_id}" if forum_id else "",
            "source_type": "paper",
            "source_provider": "openreview",
            "source_record_id": forum_id or stable_id("OR", title, venue_id),
            "source_urls": [f"https://openreview.net/forum?id={forum_id}"] if forum_id else [],
            "source_updated_at": str(note.get("mdate") or note.get("tmdate") or ""),
            "community_signals": {"source": "openreview", "venueid": venue_id, "keywords": keywords},
            "topic_score": round(topic_score, 4),
            "priority_score": round(_priority_score(canonical, year, idx, topics, priority_rules) + 0.35 * topic_score, 4),
            "priority_reason": _priority_reason({"venue_or_source": canonical}, {"venue": canonical, "year": year}, topics, priority_rules),
            "target_venue": canonical,
            "target_year": year,
            "crawl_status": "metadata_candidate",
            "cloud_crawl_query": f"OpenReview {venue_id} {' '.join(topics)}".strip(),
        }
        output.append(candidate)
    output.sort(key=lambda item: item.get("priority_score", 0), reverse=True)
    return output[: max_papers * 5]


def _openreview_value(content: dict[str, Any], key: str) -> Any:
    value = content.get(key)
    if isinstance(value, dict) and "value" in value:
        return value.get("value")
    return value


def _fetch_openreview_json(url: str, timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": OPENREVIEW_USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        if "CERTIFICATE_VERIFY_FAILED" not in repr(exc):
            raise
        with urllib.request.urlopen(request, timeout=timeout, context=ssl._create_unverified_context()) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))


def _filter_candidates(
    candidates: list[dict[str, Any]],
    venues: list[str],
    years: list[int],
    topics: list[str] | None = None,
    *,
    venue_other: bool = False,
    known_venues: list[str] | None = None,
    year_other: bool = False,
    known_years: list[int] | None = None,
) -> list[dict[str, Any]]:
    if not candidates:
        return []
    selected_years = {_safe_int(year) for year in years if _safe_int(year)}
    known_year_set = {_safe_int(year) for year in (known_years or []) if _safe_int(year)}
    known_venue_values = _unique_strings([normalize_venue(item) for item in (known_venues or DEFAULT_KNOWN_VENUES) if item])
    output = []
    for candidate in candidates:
        venue_text = str(candidate.get("venue_or_source") or candidate.get("venue") or candidate.get("target_venue") or "")
        title = str(candidate.get("title") or "")
        abstract = str(candidate.get("abstract") or "")
        matches_selected_venue = any(_candidate_matches_venue(venue_text, title, abstract, venue) for venue in venues)
        matches_known_venue = any(_candidate_matches_venue(venue_text, title, abstract, venue) for venue in known_venue_values)
        matches_other_venue = venue_other and not matches_known_venue
        if (venues or venue_other) and not (matches_selected_venue or matches_other_venue):
            continue
        year = _safe_int(candidate.get("year") or candidate.get("target_year"))
        matches_selected_year = bool(year and year in selected_years)
        matches_other_year = bool(year_other and (not year or year not in known_year_set))
        if (selected_years or year_other) and not (matches_selected_year or matches_other_year):
            continue
        if topics and not _candidate_matches_topics(candidate, topics):
            continue
        output.append(candidate)
    return output


def _candidate_matches_topics(candidate: dict[str, Any], topics: list[str], *, topic_score: float | None = None) -> bool:
    if not topics:
        return True
    score = _candidate_topic_score(candidate, topics) if topic_score is None else float(topic_score)
    if _is_test_time_scaling_topic(topics):
        return _matches_test_time_scaling(candidate, score)
    if score >= 0.08:
        return True
    text = _topic_candidate_text(candidate).lower()
    phrases = _topic_phrases(topics)
    if any(phrase and phrase in text for phrase in phrases):
        return True
    topic_tokens = [token for token in tokenize(enrich_query(" ".join(topics))) if len(token) >= 4]
    if len(topic_tokens) >= 2:
        present = sum(1 for token in set(topic_tokens) if token in text)
        return present >= max(2, min(len(set(topic_tokens)), 3))
    return False


def _is_test_time_scaling_topic(topics: list[str]) -> bool:
    normalized = " ".join(str(item or "").lower().replace("-", " ") for item in topics)
    return (
        "test time scaling" in normalized
        or "inference time scaling" in normalized
        or ("test time" in normalized and "scal" in normalized)
        or ("inference" in normalized and "compute" in normalized)
    )


def _matches_test_time_scaling(candidate: dict[str, Any], score: float) -> bool:
    text = _topic_candidate_text(candidate).lower().replace("-", " ")
    phrases = (
        "test time scaling",
        "test time compute",
        "inference time scaling",
        "inference time compute",
        "inference compute scaling",
        "scaling inference compute",
    )
    if any(phrase in text for phrase in phrases):
        return True
    has_test_time = "test time" in text or "inference time" in text
    has_scaling = any(term in text for term in ("scaling", "scale", "compute budget", "additional compute", "adaptive compute"))
    return bool(has_test_time and has_scaling and score >= 0.12)


def _candidate_topic_score(candidate: dict[str, Any], topics: list[str]) -> float:
    if not topics:
        return 0.0
    topic_text = enrich_query(" ".join(str(item) for item in topics if item))
    text = _topic_candidate_text(candidate)
    score = lexical_score(topic_text, text)
    lower = text.lower()
    for raw_topic in topics:
        phrase = str(raw_topic or "").lower().replace("-", " ").strip()
        if phrase and phrase in lower.replace("-", " "):
            score = max(score, 0.55)
        compact_phrase = "".join(ch for ch in phrase if ch.isalnum())
        compact_text_value = "".join(ch for ch in lower if ch.isalnum())
        if compact_phrase and compact_phrase in compact_text_value:
            score = max(score, 0.55)
    return round(score, 4)


def _topic_candidate_text(candidate: dict[str, Any]) -> str:
    signals = candidate.get("community_signals") if isinstance(candidate.get("community_signals"), dict) else {}
    return " ".join(
        [
            str(candidate.get("title") or ""),
            str(candidate.get("abstract") or ""),
            str(candidate.get("venue_or_source") or ""),
            json.dumps(signals, ensure_ascii=False) if signals else "",
        ]
    )


def _topic_phrases(topics: list[str]) -> list[str]:
    output: list[str] = []
    for raw in topics:
        text = str(raw or "").strip()
        if text:
            output.append(text)
        output.extend(query_expansions(text))
    normalized: list[str] = []
    for phrase in output:
        cleaned = " ".join(str(phrase or "").lower().replace("-", " ").split())
        if len(cleaned) >= 4 and cleaned not in normalized:
            normalized.append(cleaned)
    return normalized


def _best_candidate_venue(raw_venue: str, target_venue: str) -> str:
    raw = str(raw_venue or "").strip()
    target = normalize_venue(target_venue)
    if raw and _candidate_matches_venue(raw, "", "", target):
        return target or normalize_venue(raw)
    return target or normalize_venue(raw)


def _candidate_matches_venue(raw_venue: str, title: str, abstract: str, target_venue: str) -> bool:
    _ = (title, abstract)
    target = normalize_venue(target_venue)
    if not target:
        return True
    target_keys = _venue_match_keys(target)
    raw = normalize_venue(raw_venue)
    raw_key = _venue_key(raw or raw_venue)
    if not raw_key:
        return False
    if raw_key in target_keys:
        return True
    if target in {"Nature", "Science"}:
        return False
    return any(key and key in raw_key for key in target_keys)


def _venue_match_keys(value: str) -> set[str]:
    normalized = normalize_venue(value)
    keys = {_venue_key(value), _venue_key(normalized)}
    for alias, canonical in VENUE_ALIASES.items():
        if normalize_venue(canonical).lower() == normalized.lower():
            keys.add(_venue_key(alias))
    return {key for key in keys if key}


def _venue_key(value: str) -> str:
    return "".join(char.lower() for char in str(value or "") if char.isalnum())


def _metadata_queries(
    venues: list[str],
    years: list[int],
    topics: list[str],
    *,
    venue_other: bool = False,
    year_other: bool = False,
    known_years: list[int] | None = None,
) -> list[dict[str, Any]]:
    normalized_years = [int(year) for year in years if _safe_int(year)]
    topic_text = " ".join(topics).strip()
    queries: list[dict[str, Any]] = []
    for venue in venues:
        for year in normalized_years or []:
            base = " ".join(part for part in [topic_text, venue, str(year), "AI machine learning research paper"] if part)
            queries.append({"query": base, "venue": venue, "year": year})
    if venue_other:
        generic_years = normalized_years
        if year_other and not generic_years:
            generic_years = []
        for year in generic_years:
            base = " ".join(part for part in [topic_text, str(year), "AI machine learning research paper"] if part)
            queries.append({"query": base, "venue": "", "year": year})
        if not generic_years:
            base = " ".join(part for part in [topic_text, "AI machine learning research paper"] if part)
            queries.append({"query": base, "venue": "", "year": None})
    elif year_other and not queries:
        known = " ".join(str(item) for item in _unique_ints(known_years or [])[-3:])
        base = " ".join(part for part in [topic_text, "recent AI machine learning research paper", known] if part)
        queries.append({"query": base, "venue": "", "year": None})
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
        score += 0.42 * float(candidate.get("topic_score") or lexical_score(enrich_query(" ".join(topics)), text))
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
        topic_score = candidate.get("topic_score")
        parts.append(f"topic_match={float(topic_score):.2f}" if isinstance(topic_score, (int, float)) else "topic_match")
    if query.get("venue"):
        parts.append(f"target={query.get('venue')} {query.get('year') or ''}".strip())
    return " / ".join(part for part in parts if part)


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _unique_strings(values: list[Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text == OTHER_FILTER_VALUE:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(text)
    return output


def _unique_ints(values: list[Any]) -> list[int]:
    output: list[int] = []
    seen: set[int] = set()
    for value in values:
        number = _safe_int(value)
        if number is None or number in seen:
            continue
        seen.add(number)
        output.append(number)
    return output


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
