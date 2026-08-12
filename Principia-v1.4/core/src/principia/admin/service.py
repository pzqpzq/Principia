from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Literal

from ..domain import (
    CandidatePrinciple,
    ChangesetOperation,
    PrincipleCapsule,
    PublicationChangeset,
    canonical_sha256,
    monotonic_ulid,
)
from ..persistence import V14WorkspaceRepository


class PublicationDisabledError(PermissionError):
    pass


class AdminService:
    def __init__(self, repository: V14WorkspaceRepository) -> None:
        self.repository = repository

    def enqueue(self, candidate: CandidatePrinciple) -> None:
        self.repository.save_candidate(candidate, source_kind="admin_harvest")
        self.repository.enqueue_review(candidate)

    def queue(self, *, status: str | None = None) -> list[dict[str, Any]]:
        return self.repository.review_queue(status=status)

    def decide(
        self,
        candidate_id: str,
        decision: Literal["approve", "edit", "merge", "reject"],
        *,
        capsule: PrincipleCapsule | None = None,
        note: str = "",
        merge_target: str = "",
    ) -> dict[str, Any]:
        if decision == "approve" and capsule is None:
            raise ValueError("approval requires a complete reviewed Principle Capsule")
        if decision == "merge" and not merge_target:
            raise ValueError("merge requires a target Principle ID")
        payload: dict[str, Any] = {
            "decision": decision,
            "note": note,
            "merge_target": merge_target,
            "capsule": capsule.model_dump(mode="json") if capsule else None,
        }
        self.repository.decide_review(candidate_id, decision, payload)
        return payload

    def build_changeset(
        self,
        *,
        area: str,
        base_package_version: str,
        proposed_package_version: str,
        expected_content_digest: str,
        goal: str,
        capsules: list[PrincipleCapsule],
    ) -> PublicationChangeset:
        if not capsules:
            raise ValueError("changeset requires at least one reviewed Capsule")
        if any(capsule.area != area for capsule in capsules):
            raise ValueError("changeset Capsules must match its area")
        changeset = PublicationChangeset(
            changeset_id=f"chg:{monotonic_ulid()}",
            area=area,
            base_package_version=base_package_version,
            proposed_package_version=proposed_package_version,
            expected_content_digest=expected_content_digest,
            goal=goal,
            operations=[
                ChangesetOperation(
                    operation="retire" if item.status == "retired" else "add",
                    principle_id=item.principle_id,
                    expected_version=item.version - 1 if item.version > 1 else None,
                    proposed=item,
                )
                for item in sorted(capsules, key=lambda value: (value.principle_id, value.version))
            ],
            validation_results={
                "schema_valid": True,
                "human_quality_assessment": True,
                "public_source_present": all(
                    any(work.public for work in item.source_references) for item in capsules
                ),
                "trace_complete": all(bool(item.generation_trace) for item in capsules),
            },
        )
        self.repository.save_changeset(changeset)
        return changeset

    def validate_changeset(
        self, changeset_id: str, *, current_content_digest: str
    ) -> dict[str, Any]:
        changeset = self.repository.changeset(changeset_id)
        if changeset is None:
            raise KeyError(f"unknown changeset: {changeset_id}")
        checks = dict(changeset.validation_results)
        checks["base_is_current"] = changeset.expected_content_digest == current_content_digest
        checks["approval_count"] = len(changeset.approvals) >= changeset.required_approvals
        return {
            "changeset_id": changeset_id,
            "valid": all(checks.values()),
            "checks": checks,
            "digest": canonical_sha256(changeset.model_dump(mode="json")),
        }

    def dry_run_publish(
        self, changeset_id: str, *, output: str | Path | None = None
    ) -> dict[str, Any]:
        changeset = self.repository.changeset(changeset_id)
        if changeset is None:
            raise KeyError(f"unknown changeset: {changeset_id}")
        payload = changeset.model_dump(mode="json")
        exported_path = ""
        if output is not None:
            output_path = Path(output).expanduser().resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            exported_path = str(output_path)
        return {
            "mode": "dry_run",
            "changeset_id": changeset_id,
            "changeset_digest": canonical_sha256(payload),
            "operation_count": len(changeset.operations),
            "estimated_json_bytes": len(json.dumps(payload, ensure_ascii=False).encode()),
            "exported_path": exported_path,
            "external_write_performed": False,
        }

    def github_publish(
        self, changeset_id: str, *, confirmation: str
    ) -> dict[str, Any]:
        if os.getenv("PRINCIPIA_ENABLE_GITHUB_WRITE") != "1":
            raise PublicationDisabledError("GitHub publication adapter is disabled")
        if confirmation != f"PUBLISH {changeset_id}":
            raise PublicationDisabledError("typed publication confirmation does not match")
        gh = shutil.which("gh")
        if gh is None:
            raise PublicationDisabledError("authenticated gh CLI is unavailable")
        auth = subprocess.run(
            [gh, "auth", "status"], capture_output=True, text=True, timeout=15, check=False
        )
        if auth.returncode != 0:
            raise PublicationDisabledError("gh CLI is not authenticated")
        raise PublicationDisabledError(
            "The v1.4.0 fixture-first release does not configure a real Cloud repository"
        )

