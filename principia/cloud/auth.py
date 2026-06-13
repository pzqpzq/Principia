from __future__ import annotations

import hashlib
import hmac
import os
from typing import Any


ADMIN_KEY_ENV = "PRINCIPIA_CLOUD_ADMIN_KEY"
UPLOAD_KEY_ENV = "PRINCIPIA_CLOUD_UPLOAD_KEY"
ADMIN_KEY_HASH_ENV = "PRINCIPIA_CLOUD_ADMIN_KEY_SHA256"


def cloud_admin_status() -> dict[str, Any]:
    configured = bool(_configured_secret() or os.getenv(ADMIN_KEY_HASH_ENV, "").strip())
    return {
        "configured": configured,
        "mode": "server_key" if configured else "local_pr_export",
        "secret_exposed_to_browser": False,
        "message": (
            "Cloud admin key is configured on the server."
            if configured
            else "No server admin key is configured; local PR-export packs can still be prepared for maintainer review."
        ),
    }


def check_admin_key(submitted: str = "", *, purpose: str = "cloud_admin") -> dict[str, Any]:
    submitted = str(submitted or "")
    secret = _configured_secret()
    digest = os.getenv(ADMIN_KEY_HASH_ENV, "").strip().lower()
    if secret:
        if hmac.compare_digest(submitted, secret):
            return {"ok": True, "authorized": True, "purpose": purpose, "mode": "server_key"}
        return {"ok": False, "authorized": False, "purpose": purpose, "error": "Invalid cloud admin key."}
    if digest:
        submitted_digest = hashlib.sha256(submitted.encode("utf-8")).hexdigest()
        if hmac.compare_digest(submitted_digest, digest):
            return {"ok": True, "authorized": True, "purpose": purpose, "mode": "server_key_hash"}
        return {"ok": False, "authorized": False, "purpose": purpose, "error": "Invalid cloud admin key."}
    return {
        "ok": True,
        "authorized": False,
        "purpose": purpose,
        "mode": "local_pr_export",
        "warning": "Server admin key is not configured; output is a local PR-export artifact, not a direct GitHub write.",
    }


def require_admin_key(submitted: str = "", *, purpose: str = "cloud_admin") -> dict[str, Any]:
    auth = check_admin_key(submitted, purpose=purpose)
    if not auth.get("ok"):
        raise PermissionError(str(auth.get("error") or "Cloud admin key rejected."))
    return auth


def _configured_secret() -> str:
    return os.getenv(ADMIN_KEY_ENV, "").strip() or os.getenv(UPLOAD_KEY_ENV, "").strip()
