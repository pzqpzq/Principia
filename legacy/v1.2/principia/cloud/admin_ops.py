from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..models import utc_now
from ..utils import stable_id


def create_admin_operation(operation_type: str, target_type: str, payload: dict[str, Any], *, reason: str = "", actor: str = "") -> dict[str, Any]:
    return {
        "operation_id": stable_id("OP", operation_type, target_type, payload, utc_now()),
        "operation_type": operation_type,
        "target_type": target_type,
        "payload": payload,
        "reason": reason,
        "admin_actor": actor,
        "created_at": utc_now(),
    }


def write_admin_operation(out_dir: Path, operation: dict[str, Any]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{operation['operation_id']}.json"
    path.write_text(json.dumps(operation, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return path
