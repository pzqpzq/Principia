from __future__ import annotations

from typing import Any


def pr_export_instructions(contribution_path: str) -> dict[str, Any]:
    return {
        "mode": "pr_export",
        "contribution_path": contribution_path,
        "safe_default": True,
        "instructions": [
            "Create a branch in the GitHub repository.",
            "Add the contribution file under cloud/contributions/ or attach it to the maintainer workflow.",
            "Open a pull request against main.",
            "Wait for principia-cloud-validate to pass before merge.",
        ],
    }
