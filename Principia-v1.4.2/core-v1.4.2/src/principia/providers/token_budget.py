"""Process-safe cumulative token accounting; no prompts or credentials stored."""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any


class TokenBudgetExceeded(RuntimeError):
    pass


class TokenBudget:
    def __init__(self, path: Path, limit: int) -> None:
        if limit <= 0:
            raise ValueError("Token limit must be positive")
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS budget (id INTEGER PRIMARY KEY, token_limit INTEGER NOT NULL)")
            conn.execute("CREATE TABLE IF NOT EXISTS attempts (id TEXT PRIMARY KEY, reserved INTEGER NOT NULL, charged INTEGER NOT NULL, state TEXT NOT NULL)")
            conn.execute("INSERT OR IGNORE INTO budget VALUES (1, ?)", (limit,))
            if conn.execute("SELECT token_limit FROM budget WHERE id=1").fetchone()[0] != limit:
                raise ValueError("Existing cumulative token cap differs; it cannot be silently changed")

    def connect(self):
        from contextlib import contextmanager

        @contextmanager
        def connection():
            conn = sqlite3.connect(self.path, timeout=30)
            try:
                with conn:
                    yield conn
            finally:
                conn.close()
        return connection()

    @classmethod
    def from_environment(cls) -> TokenBudget | None:
        path = os.getenv("PRINCIPIA_TOKEN_BUDGET_FILE", "")
        if not path:
            return None
        return cls(Path(path), int(os.getenv("PRINCIPIA_TOKEN_BUDGET_LIMIT", "3000000")))

    def reserve(self, messages: list[dict[str, Any]], max_tokens: int, thinking_budget: int = 0) -> str:
        # UTF-8 bytes provide a conservative text-token allowance; multimodal
        # payload bytes are reserved as well. Unknown usage remains charged.
        amount = len(json.dumps(messages, ensure_ascii=False).encode()) + max_tokens + thinking_budget + 1024
        identifier = uuid.uuid4().hex
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            used = int(conn.execute("SELECT coalesce(sum(charged),0) FROM attempts").fetchone()[0])
            limit = int(conn.execute("SELECT token_limit FROM budget WHERE id=1").fetchone()[0])
            if used + amount > limit:
                raise TokenBudgetExceeded("Cumulative remote token cap reached; no request was sent.")
            conn.execute("INSERT INTO attempts VALUES (?,?,?,'reserved')", (identifier, amount, amount))
        return identifier

    def settle(self, identifier: str, usage: dict[str, Any]) -> None:
        if not all(type(usage.get(key)) is int and usage[key] >= 0 for key in ("prompt_tokens", "completion_tokens")):
            return
        charged = usage["prompt_tokens"] + usage["completion_tokens"]
        with self.connect() as conn:
            conn.execute("UPDATE attempts SET charged=?, state='reported' WHERE id=? AND state='reserved'", (charged, identifier))

    def snapshot(self) -> dict[str, int]:
        with self.connect() as conn:
            limit = int(conn.execute("SELECT token_limit FROM budget WHERE id=1").fetchone()[0])
            row = conn.execute("SELECT count(*),coalesce(sum(charged),0),coalesce(sum(state='reserved'),0) FROM attempts").fetchone()
        return {"limit": limit, "attempts": row[0], "charged_tokens": row[1], "remaining_tokens": max(0, limit-row[1]), "unreported_attempts": row[2]}


def load_credential_environment(path: Path) -> None:
    """Read explicitly authorized dotenv values without shell execution/echo."""
    allowed = {"PRINCIPIA_LLM_API_KEY", "PRINCIPIA_LLM_BASE_URL", "SILICONFLOW_API_KEY", "SILICONFLOW_BASE_URL", "OPENAI_API_KEY", "OPENAI_BASE_URL"}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:]
        key, separator, value = line.partition("=")
        if separator and key.strip() in allowed:
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            os.environ[key.strip()] = value
