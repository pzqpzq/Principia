from __future__ import annotations

from typing import Any

from .utils import stable_id


PROMPT_VERSION = "v1-principia-concept-extraction"
SCHEMA_VERSION = "v1-concept-card"


def extraction_cache_key(
    work_version_id: str,
    *,
    llm_provider: str,
    llm_model: str,
    prompt_version: str = PROMPT_VERSION,
    schema_version: str = SCHEMA_VERSION,
    extraction_task_type: str = "work_concepts",
) -> str:
    return stable_id(
        "XRUN",
        work_version_id,
        llm_provider,
        llm_model,
        prompt_version,
        schema_version,
        extraction_task_type,
    )


class ExtractionScheduler:
    def __init__(self, store: Any):
        self.store = store

    def ensure_extraction(
        self,
        work_id: str,
        work_version_id: str,
        *,
        llm_provider: str,
        llm_model: str,
        model_mode: str = "auto",
        extraction_task_type: str = "work_concepts",
    ) -> dict[str, Any]:
        return self.store.ensure_extraction_run(
            work_id,
            work_version_id,
            llm_provider=llm_provider,
            llm_model=llm_model,
            model_mode=model_mode,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            extraction_task_type=extraction_task_type,
        )
