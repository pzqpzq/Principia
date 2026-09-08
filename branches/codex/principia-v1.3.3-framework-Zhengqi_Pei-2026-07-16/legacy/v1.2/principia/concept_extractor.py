from __future__ import annotations

from typing import Any


class ConceptExtractor:
    """Normalize LLM extraction output into v1 concept payload families."""

    def from_work_extraction(self, work: dict[str, Any], extraction: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        work_id = work.get("work_id") or work.get("global_work_id") or ""
        return {
            "existed_idea": [
                {
                    **item,
                    "source_work_ids": [work_id],
                    "source_title": work.get("title") or work.get("canonical_title") or "",
                }
                for item in extraction.get("existed_ideas", []) or []
                if isinstance(item, dict)
            ],
            "principle": [
                {
                    **item,
                    "source_work_ids": item.get("source_works") or [work_id],
                    "source_title": work.get("title") or work.get("canonical_title") or "",
                }
                for item in extraction.get("principles", []) or []
                if isinstance(item, dict)
            ],
            "takeaway_message": [
                {
                    **item,
                    "source_work_ids": [work_id],
                    "source_title": work.get("title") or work.get("canonical_title") or "",
                }
                for item in extraction.get("takeaway_messages", []) or []
                if isinstance(item, dict)
            ],
            "benchmark": [
                {
                    **item,
                    "source_work_ids": [work_id],
                    "source_title": work.get("title") or work.get("canonical_title") or "",
                }
                for item in extraction.get("benchmarks", []) or []
                if isinstance(item, dict)
            ],
            "baseline": [
                {
                    **item,
                    "source_work_ids": [work_id],
                    "source_title": work.get("title") or work.get("canonical_title") or "",
                }
                for item in extraction.get("baselines", []) or []
                if isinstance(item, dict)
            ],
            "result_fact": [
                {
                    **item,
                    "source_work_ids": [work_id],
                    "source_title": work.get("title") or work.get("canonical_title") or "",
                }
                for item in extraction.get("result_facts", []) or extraction.get("results", []) or []
                if isinstance(item, dict)
            ],
        }
