from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from typing import Any


ADMIN_KEY_ENV = "PRINCIPIA_CLOUD_ADMIN_KEY"
UPLOAD_KEY_ENV = "PRINCIPIA_CLOUD_UPLOAD_KEY"
ADMIN_KEY_HASH_ENV = "PRINCIPIA_CLOUD_ADMIN_KEY_SHA256"
ADMIN_SESSION_SECRET_ENV = "PRINCIPIA_ADMIN_SESSION_SECRET"
ADMIN_SESSION_COOKIE = "principia_admin_session"
ADMIN_SESSION_TTL_SECONDS = 12 * 60 * 60


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


def admin_session_status(cookie_header: str = "") -> dict[str, Any]:
    status = cloud_admin_status()
    status["authenticated"] = check_admin_session(cookie_header)
    status["session_ttl_seconds"] = ADMIN_SESSION_TTL_SECONDS
    return status


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


def require_admin_authorization(submitted: str = "", *, cookie_header: str = "", purpose: str = "cloud_admin") -> dict[str, Any]:
    if check_admin_session(cookie_header):
        return {"ok": True, "authorized": True, "purpose": purpose, "mode": "server_session"}
    return require_admin_key(submitted, purpose=purpose)


def create_admin_session_cookie(*, now: float | None = None) -> str:
    secret = _session_secret()
    if not secret:
        raise PermissionError("Cloud admin key is not configured.")
    issued_at = str(int(now if now is not None else time.time()))
    nonce = secrets.token_urlsafe(18)
    signature = _session_signature(issued_at, nonce)
    raw = f"{issued_at}:{nonce}:{signature}".encode("utf-8")
    token = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return (
        f"{ADMIN_SESSION_COOKIE}={token}; Path=/; Max-Age={ADMIN_SESSION_TTL_SECONDS}; "
        "HttpOnly; SameSite=Lax"
    )


def clear_admin_session_cookie() -> str:
    return f"{ADMIN_SESSION_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"


def check_admin_session(cookie_header: str = "", *, now: float | None = None) -> bool:
    token = _cookie_value(cookie_header, ADMIN_SESSION_COOKIE)
    if not token:
        return False
    try:
        padding = "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode((token + padding).encode("ascii")).decode("utf-8")
        issued_at, nonce, signature = raw.split(":", 2)
        issued_ts = int(issued_at)
    except Exception:
        return False
    current_ts = int(now if now is not None else time.time())
    if issued_ts <= 0 or issued_ts > current_ts + 60 or current_ts - issued_ts > ADMIN_SESSION_TTL_SECONDS:
        return False
    expected = _session_signature(issued_at, nonce)
    return bool(expected) and hmac.compare_digest(signature, expected)


def _configured_secret() -> str:
    return os.getenv(ADMIN_KEY_ENV, "").strip() or os.getenv(UPLOAD_KEY_ENV, "").strip()


def _session_secret() -> bytes:
    explicit = os.getenv(ADMIN_SESSION_SECRET_ENV, "").strip()
    if explicit:
        return explicit.encode("utf-8")
    digest = os.getenv(ADMIN_KEY_HASH_ENV, "").strip().lower()
    if digest:
        return f"admin-sha256:{digest}".encode("utf-8")
    secret = _configured_secret()
    if secret:
        return hashlib.sha256(secret.encode("utf-8")).hexdigest().encode("utf-8")
    return b""


def _session_signature(issued_at: str, nonce: str) -> str:
    secret = _session_secret()
    if not secret:
        return ""
    return hmac.new(secret, f"{issued_at}:{nonce}".encode("utf-8"), hashlib.sha256).hexdigest()


def _cookie_value(cookie_header: str, name: str) -> str:
    for part in str(cookie_header or "").split(";"):
        key, _, value = part.strip().partition("=")
        if key == name:
            return value.strip()
    return ""
