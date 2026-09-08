from __future__ import annotations

import math
import re
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from ..domain import JobRecord, canonical_sha256, event_id, monotonic_ulid
from ..models import utc_now
from ..persistence import V14WorkspaceRepository

_TOKEN = re.compile(r"[a-z0-9][a-z0-9_-]+")
_POSITIVE = {
    "activate",
    "activates",
    "increase",
    "increases",
    "improve",
    "improves",
    "enhance",
    "enhances",
    "promote",
    "promotes",
    "raise",
    "raises",
    "support",
    "supports",
    "stabilize",
    "stabilizes",
}
_NEGATIVE = {
    "decrease",
    "decreases",
    "degrade",
    "degrades",
    "impair",
    "impairs",
    "inhibit",
    "inhibits",
    "limit",
    "limits",
    "lower",
    "lowers",
    "reduce",
    "reduces",
    "suppress",
    "suppresses",
    "destabilize",
    "destabilizes",
}


def _tokens(value: Any) -> frozenset[str]:
    return frozenset(_TOKEN.findall(str(value or "").casefold()))


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _direction(argument: dict[str, Any]) -> int:
    tokens = _tokens(argument.get("direction_or_qualifier")) | _tokens(
        argument.get("canonical_claim")
    )
    positive = len(tokens & _POSITIVE)
    negative = len(tokens & _NEGATIVE)
    if positive == negative:
        return 0
    return 1 if positive > negative else -1


def wilson_lower_bound(
    successes: int, failures: int, *, z: float = 1.959963984540054
) -> float | None:
    """Return the 95% Wilson lower bound, or None when no relation evidence exists."""

    total = successes + failures
    if total <= 0:
        return None
    proportion = successes / total
    denominator = 1 + (z * z / total)
    centre = proportion + (z * z / (2 * total))
    margin = z * math.sqrt((proportion * (1 - proportion) + z * z / (4 * total)) / total)
    return max(0.0, (centre - margin) / denominator)


class PrincipleRelationService:
    """Build immutable, validated relation revisions and atomic metric snapshots.

    The deterministic pass is deliberately conservative. It can establish a
    relation only when structured argument slots align; text proximity by itself
    never creates a scored relation.
    """

    def __init__(
        self,
        repository: V14WorkspaceRepository,
        *,
        snapshot_export: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self.repository = repository
        self.snapshot_export = snapshot_export
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="principia-relations")
        self._futures: dict[str, Future[None]] = {}

    def start_rebuild(self) -> JobRecord:
        job = JobRecord(
            job_id=f"job:{monotonic_ulid()}",
            kind="relation_index",
            state="queued",
            stage="Waiting to compare Principles",
            progress=0,
            status_message="Preparing a validated relation index",
            last_activity_at=utc_now(),
        )
        self.repository.save_job(job)
        self.repository.append_job_event(
            job.job_id,
            "queued",
            {"stage": job.stage, "message": job.status_message},
            event_id=event_id(),
        )
        self._futures[job.job_id] = self._executor.submit(self._run, job.job_id)
        return job

    def rebuild(self) -> dict[str, Any]:
        """Synchronous entry point for maintenance commands and deterministic tests."""

        return self._build(progress=None)

    def _run(self, job_id: str) -> None:
        job = self.repository.get_job(job_id)
        if job is None:
            return

        def progress(stage: str, value: float, completed: int, total: int) -> None:
            current = self.repository.get_job(job_id)
            if current is None:
                return
            current.state = "running"
            current.stage = stage
            current.progress = max(current.progress, min(value, 0.99))
            current.completed_units = completed
            current.total_units = total
            current.status_message = stage
            current.last_activity_at = utc_now()
            current.updated_at = current.last_activity_at
            self.repository.save_job(current)
            self.repository.append_job_event(
                job_id,
                "progress",
                {
                    "stage": stage,
                    "progress": current.progress,
                    "completed_units": completed,
                    "total_units": total,
                },
                event_id=event_id(),
            )

        try:
            job.state = "running"
            job.stage = "Comparing reusable findings"
            job.progress = 0.05
            job.last_activity_at = utc_now()
            job.updated_at = job.last_activity_at
            self.repository.save_job(job)
            result = self._build(progress=progress)
            job = self.repository.get_job(job_id) or job
            job.state = "succeeded"
            job.stage = "Relations and measures ready"
            job.progress = 1
            job.completed_units = job.total_units
            job.result = result
            job.status_message = (
                f"Validated {result['relation_count']} scientific relations and "
                f"saved measure revision {result['metric_revision']}"
            )
            job.last_activity_at = utc_now()
            job.updated_at = job.last_activity_at
            self.repository.save_job(job)
            self.repository.append_job_event(
                job_id, "succeeded", {"stage": job.stage, "result": result}, event_id=event_id()
            )
        except Exception as exc:
            job = self.repository.get_job(job_id) or job
            job.state = "failed"
            job.stage = "Relation analysis failed"
            job.error = {
                "code": "relation_index_failed",
                "category": "processing",
                "message": "Principia could not complete relation analysis.",
                "retryable": True,
            }
            job.status_message = job.error["message"]
            job.last_activity_at = utc_now()
            job.updated_at = job.last_activity_at
            self.repository.save_job(job)
            self.repository.append_job_event(
                job_id, "failed", {"stage": job.stage, "error": job.error}, event_id=event_id()
            )
            del exc

    def _build(self, *, progress: Any | None) -> dict[str, Any]:
        rows = self.repository.relation_inputs()
        inputs: list[dict[str, Any]] = []
        for row in rows:
            import json

            argument = json.loads(str(row["argument_json"]))
            inputs.append(
                {
                    **row,
                    "argument": argument,
                    "work_ids": frozenset(filter(None, str(row["work_ids"]).split(","))),
                    "subject": _tokens(argument.get("subject_system")),
                    "driver": _tokens(argument.get("driver_or_intervention")),
                    "outcome": _tokens(argument.get("outcome")),
                    "claim": _tokens(argument.get("canonical_claim")),
                    "conditions": _tokens(" ".join(argument.get("conditions") or [])),
                    "direction_sign": _direction(argument),
                }
            )
        relations: list[dict[str, Any]] = []
        total_pairs = len(inputs) * max(0, len(inputs) - 1) // 2
        checked = 0
        for left_index, left in enumerate(inputs):
            for right in inputs[left_index + 1 :]:
                checked += 1
                relation = self._classify(left, right)
                if relation is not None:
                    relations.append(relation)
            if progress and (left_index % 10 == 0 or left_index + 1 == len(inputs)):
                progress(
                    "Comparing reusable findings",
                    0.1 + 0.62 * (checked / max(1, total_pairs)),
                    checked,
                    total_pairs,
                )
        relations.sort(
            key=lambda item: (
                item["source_principle_id"],
                item["target_principle_id"],
                item["relation_type"],
            )
        )
        change = self.repository.replace_validated_relation_set(relations)
        if progress:
            progress("Calculating library measures", 0.82, len(inputs), len(inputs))
        corpus_digest = canonical_sha256(
            {
                "principles": [
                    {"id": row["candidate_id"], "digest": row["content_digest"]} for row in rows
                ],
                "relations": relations,
                "metric_definition": "relation-metrics-v1",
            }
        )
        metrics, maximum_degree = self._metrics(inputs, relations)
        metric_revision = self.repository.save_relation_metric_snapshot(
            corpus_digest=corpus_digest,
            maximum_neighbor_count=maximum_degree,
            metrics=metrics,
            payload={
                "metric_definition": "relation-metrics-v1",
                "principle_count": len(inputs),
                "relation_count": len(relations),
                "score_scope": "installed_library",
            },
        )
        result: dict[str, Any] = {
            "principle_count": len(inputs),
            "relation_count": len(relations),
            "metric_revision": metric_revision,
            "corpus_digest": corpus_digest,
            "maximum_neighbor_count": maximum_degree,
            **change,
        }
        if self.snapshot_export is not None:
            snapshot = self.snapshot_export()
            result["principles_snapshot"] = {
                "location": "workspace/principles",
                "principle_count": int(snapshot.get("principle_count") or 0),
                "relation_count": int(snapshot.get("relation_count") or 0),
                "content_digest": str(snapshot.get("content_digest") or ""),
            }
        return result

    @staticmethod
    def _classify(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any] | None:
        subject = _jaccard(left["subject"], right["subject"])
        driver = _jaccard(left["driver"], right["driver"])
        outcome = _jaccard(left["outcome"], right["outcome"])
        claim = _jaccard(left["claim"], right["claim"])
        analogous_candidate = subject >= 0.55 and claim >= 0.12
        if subject < 0.35 or (
            driver < 0.34 and outcome < 0.34 and not analogous_candidate
        ):
            return None
        # Near-identical records belong to consolidation, not the relation score.
        if claim >= 0.9:
            return None
        left_sign = int(left["direction_sign"])
        right_sign = int(right["direction_sign"])
        relation_type = ""
        source = left
        target = right
        rationale = ""
        if (
            left_sign != 0
            and right_sign != 0
            and left_sign != right_sign
            and driver >= 0.45
            and outcome >= 0.45
        ):
            relation_type = "contradicts"
            rationale = "Aligned scientific slots have opposing supported directions."
        elif (
            left["work_ids"]
            and right["work_ids"]
            and left["work_ids"].isdisjoint(right["work_ids"])
            and (left_sign == right_sign or left_sign == 0 or right_sign == 0)
            and claim >= 0.54
            and driver >= 0.38
            and outcome >= 0.38
        ):
            relation_type = "supports"
            rationale = "Distinct source provenance supports a compatible scientific relationship."
        elif (
            (left_sign == right_sign or left_sign == 0 or right_sign == 0)
            and driver >= 0.45
            and outcome >= 0.45
            and left["conditions"] != right["conditions"]
            and (
                left["conditions"] <= right["conditions"]
                or right["conditions"] <= left["conditions"]
            )
        ):
            relation_type = "specializes"
            if len(left["conditions"]) < len(right["conditions"]):
                source, target = right, left
            rationale = "A compatible relationship is stated under a stricter set of conditions."
        elif (
            subject >= 0.55
            and claim >= 0.12
        ):
            relation_type = "analogous_to"
            rationale = (
                "The arguments concern the same scientific system and share a "
                "non-trivial claim context, but do not supply evidence for one another."
            )
        if not relation_type:
            return None
        relation_key = {
            "source": source["candidate_id"],
            "target": target["candidate_id"],
            "type": relation_type,
            "engine": "relation-engine-v1",
        }
        return {
            "relation_id": "rel:" + canonical_sha256(relation_key)[:26],
            "source_principle_id": source["candidate_id"],
            "target_principle_id": target["candidate_id"],
            "relation_type": relation_type,
            "direction": "undirected" if relation_type == "analogous_to" else "directed",
            "provenance": "deterministic_validated",
            "validation_state": "validated",
            "rationale": rationale,
            "source_version": 0,
            "target_version": 0,
            "evidence_digest": canonical_sha256(
                {
                    "source_digest": source["content_digest"],
                    "target_digest": target["content_digest"],
                    "source_works": sorted(source["work_ids"]),
                    "target_works": sorted(target["work_ids"]),
                }
            ),
            "model_trace": {},
            "engine_version": "relation-engine-v2",
        }

    @staticmethod
    def _metrics(
        inputs: list[dict[str, Any]], relations: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], int | None]:
        ids = [str(item["candidate_id"]) for item in inputs]
        neighbors: dict[str, set[str]] = {identifier: set() for identifier in ids}
        supports: dict[str, set[str]] = {identifier: set() for identifier in ids}
        contradicts: dict[str, set[str]] = {identifier: set() for identifier in ids}
        for relation in relations:
            source = str(relation["source_principle_id"])
            target = str(relation["target_principle_id"])
            if source == target or source not in neighbors or target not in neighbors:
                continue
            neighbors[source].add(target)
            neighbors[target].add(source)
            if relation["relation_type"] == "supports":
                supports[target].add(source)
            elif relation["relation_type"] == "contradicts":
                contradicts[target].add(source)
        maximum = max((len(value) for value in neighbors.values()), default=0)
        metrics: list[dict[str, Any]] = []
        for identifier in ids:
            degree = len(neighbors[identifier])
            support_count = len(supports[identifier])
            contradict_count = len(contradicts[identifier])
            lower = wilson_lower_bound(support_count, contradict_count)
            metrics.append(
                {
                    "principle_id": identifier,
                    "influence_score": round(100 * degree / maximum, 2)
                    if degree and maximum
                    else None,
                    "reliability_score": round(100 * lower, 2) if lower is not None else None,
                    "distinct_neighbor_count": degree,
                    "incoming_support_count": support_count,
                    "incoming_contradict_count": contradict_count,
                }
            )
        return metrics, (maximum or None)
