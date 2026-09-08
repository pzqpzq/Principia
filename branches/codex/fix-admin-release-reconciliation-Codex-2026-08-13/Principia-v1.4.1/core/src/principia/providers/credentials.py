from __future__ import annotations

import getpass
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..models import utc_now
from .models import SILICONFLOW_AUTHORIZED_BASE_URLS


class ProviderCredentialStore:
    """Workspace-private provider credentials, deliberately outside SQLite."""

    def __init__(self, workspace_root: str | Path) -> None:
        self.directory = Path(workspace_root) / ".principia" / "secrets"
        self.path = self.directory / "provider_credentials.json"

    def metadata(self, provider_id: str) -> dict[str, Any]:
        record = self._records().get(provider_id) or {}
        if record.get("api_key"):
            return {
                "configured": True,
                "credential_source": "workspace",
                "saved_at": str(record.get("saved_at") or ""),
                "base_url": self.base_url(provider_id),
            }
        environment_key = self._environment_key(provider_id)
        return {
            "configured": bool(environment_key),
            "credential_source": "environment" if environment_key else "none",
            "saved_at": "",
            "base_url": self.base_url(provider_id),
        }

    def base_url(self, provider_id: str) -> str:
        record = self._records().get(provider_id) or {}
        value = str(record.get("base_url") or "").rstrip("/")
        return value if value in SILICONFLOW_AUTHORIZED_BASE_URLS else ""

    def api_key(self, provider_id: str) -> str:
        record = self._records().get(provider_id) or {}
        key = str(record.get("api_key") or "")
        return key or self._environment_key(provider_id)

    def save(self, provider_id: str, api_key: str) -> dict[str, Any]:
        normalized_provider = provider_id.strip().casefold()
        normalized_key = api_key.strip()
        if normalized_provider != "siliconflow":
            raise KeyError(f"unknown provider profile: {provider_id}")
        if len(normalized_key) < 8 or len(normalized_key) > 8_192:
            raise ValueError("the provider credential has an invalid length")
        records = self._records()
        previous = records.get(normalized_provider) or {}
        records[normalized_provider] = {
            "api_key": normalized_key,
            "saved_at": utc_now(),
            **(
                {"base_url": previous["base_url"]}
                if previous.get("base_url") in SILICONFLOW_AUTHORIZED_BASE_URLS
                else {}
            ),
        }
        self._write(records)
        return self.metadata(normalized_provider)

    def remember_base_url(self, provider_id: str, base_url: str) -> None:
        normalized_provider = provider_id.strip().casefold()
        normalized_url = base_url.rstrip("/")
        if normalized_provider != "siliconflow":
            raise KeyError(f"unknown provider profile: {provider_id}")
        if normalized_url not in SILICONFLOW_AUTHORIZED_BASE_URLS:
            raise ValueError("the provider origin is not authorized")
        records = self._records()
        record = records.get(normalized_provider) or {}
        record["base_url"] = normalized_url
        records[normalized_provider] = record
        self._write(records)

    def delete(self, provider_id: str) -> dict[str, Any]:
        normalized_provider = provider_id.strip().casefold()
        records = self._records()
        if normalized_provider in records:
            base_url = records[normalized_provider].get("base_url")
            if self._environment_key(normalized_provider) and base_url:
                records[normalized_provider] = {"base_url": base_url}
            else:
                del records[normalized_provider]
            self._write(records)
        return self.metadata(normalized_provider)

    def _records(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        self._verify_permissions()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise PermissionError("the workspace provider credential file is unreadable") from exc
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise PermissionError("the workspace provider credential file has an invalid format")
        profiles = payload.get("profiles")
        if not isinstance(profiles, dict):
            raise PermissionError("the workspace provider credential file has an invalid format")
        return {
            str(key): dict(value)
            for key, value in profiles.items()
            if isinstance(value, dict)
        }

    def _write(self, records: dict[str, dict[str, Any]]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if sys.platform != "win32":
            os.chmod(self.directory, 0o700)
        payload = json.dumps(
            {"schema_version": 1, "profiles": records},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        partial = self.path.with_name(f".{self.path.name}.{os.getpid()}.partial")
        try:
            descriptor = os.open(partial, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            if sys.platform == "win32":
                self._apply_windows_acl(partial)
            else:
                os.chmod(partial, 0o600)
            os.replace(partial, self.path)
            if sys.platform == "win32":
                self._apply_windows_acl(self.path)
            else:
                os.chmod(self.path, 0o600)
                self._verify_permissions()
        finally:
            partial.unlink(missing_ok=True)

    def _verify_permissions(self) -> None:
        if sys.platform == "win32":
            self._apply_windows_acl(self.path)
            return
        mode = self.path.stat().st_mode & 0o777
        if mode != 0o600:
            raise PermissionError(
                "provider credentials are not owner-only; set file permissions to 0600"
            )

    @staticmethod
    def _apply_windows_acl(path: Path) -> None:
        username = getpass.getuser()
        if not username:
            raise PermissionError("cannot determine the Windows account for credential ACLs")
        try:
            result = subprocess.run(
                [
                    "icacls",
                    str(path),
                    "/inheritance:r",
                    "/grant:r",
                    f"{username}:(R,W)",
                ],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise PermissionError("could not apply a private Windows credential ACL") from exc
        if result.returncode != 0:
            raise PermissionError("could not apply a private Windows credential ACL")

    @staticmethod
    def _environment_key(provider_id: str) -> str:
        if provider_id == "siliconflow":
            return os.getenv("PRINCIPIA_LLM_API_KEY", "") or os.getenv(
                "SILICONFLOW_API_KEY", ""
            )
        return ""
