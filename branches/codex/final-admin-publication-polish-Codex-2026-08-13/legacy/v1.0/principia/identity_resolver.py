from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from .utils import stable_id
from .work_versioning import normalize_title, text_hash


@dataclass
class IdentityResolution:
    work_id: str
    confidence: float
    status: str
    reason: str
    existing: dict[str, Any] | None = None


def clean_external_id(value: Any) -> str:
    text = str(value or "").strip()
    return text.removeprefix("https://doi.org/").removeprefix("http://dx.doi.org/").strip()


def extract_arxiv_id(work: dict[str, Any]) -> str:
    candidates = [
        work.get("arxiv_id"),
        work.get("url_or_doi"),
        *(work.get("source_urls") or []),
    ]
    for value in candidates:
        match = re.search(r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5}(?:v\d+)?)", str(value or ""), re.I)
        if match:
            return match.group(1).split("v", 1)[0]
    return ""


class WorkIdentityResolver:
    def resolve(self, incoming: dict[str, Any], candidates: list[dict[str, Any]]) -> IdentityResolution:
        doi = clean_external_id(incoming.get("doi") or incoming.get("DOI") or incoming.get("url_or_doi"))
        arxiv_id = extract_arxiv_id(incoming)
        raw_id = str(incoming.get("id", ""))
        openalex_id = clean_external_id(incoming.get("openalex_id") or (raw_id if "openalex" in raw_id.lower() else ""))
        crossref_id = clean_external_id(incoming.get("crossref_id"))
        title_norm = normalize_title(str(incoming.get("title") or ""))
        title_hash = text_hash(title_norm)

        for candidate in candidates:
            if doi and doi == clean_external_id(candidate.get("doi")):
                return IdentityResolution(candidate["work_id"], 1.0, "resolved", "doi_exact", candidate)
            if arxiv_id and arxiv_id == clean_external_id(candidate.get("arxiv_id")):
                return IdentityResolution(candidate["work_id"], 1.0, "resolved", "arxiv_exact", candidate)
            if openalex_id and openalex_id == clean_external_id(candidate.get("openalex_id")):
                return IdentityResolution(candidate["work_id"], 1.0, "resolved", "openalex_exact", candidate)
            if crossref_id and crossref_id == clean_external_id(candidate.get("crossref_id")):
                return IdentityResolution(candidate["work_id"], 1.0, "resolved", "crossref_exact", candidate)
            if title_hash and title_hash == candidate.get("title_hash"):
                return IdentityResolution(candidate["work_id"], 0.96, "resolved", "title_hash", candidate)

        best: tuple[float, dict[str, Any] | None] = (0.0, None)
        incoming_year = str(incoming.get("year") or "")
        incoming_authors = {str(author).lower() for author in incoming.get("authors", [])[:8]}
        for candidate in candidates:
            score = SequenceMatcher(None, title_norm, normalize_title(candidate.get("canonical_title", ""))).ratio()
            if incoming_year and incoming_year == str(candidate.get("year") or ""):
                score += 0.04
            candidate_authors = {str(author).lower() for author in (candidate.get("metadata", {}).get("authors") or [])[:8]}
            if incoming_authors and candidate_authors:
                score += min(0.08, len(incoming_authors & candidate_authors) / max(len(incoming_authors), 1) * 0.08)
            if score > best[0]:
                best = (score, candidate)

        if best[1] and best[0] >= 0.95:
            return IdentityResolution(best[1]["work_id"], min(best[0], 0.99), "resolved", "fuzzy_title_author_year", best[1])
        if best[1] and best[0] >= 0.80:
            return IdentityResolution(best[1]["work_id"], min(best[0], 0.94), "ambiguous_review", "medium_confidence_identity", best[1])

        generated = stable_id("W", doi or arxiv_id or title_norm or str(incoming))
        return IdentityResolution(generated, 1.0, "new", "no_existing_identity", None)
