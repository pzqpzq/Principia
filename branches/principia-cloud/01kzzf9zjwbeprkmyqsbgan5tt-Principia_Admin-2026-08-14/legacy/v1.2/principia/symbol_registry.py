from __future__ import annotations

import re
from typing import Any

from .global_store import GlobalStore
from .models import utc_now
from .utils import stable_id


PREFIX_BY_TYPE = {
    "work": "W",
    "existed_idea": "XI",
    "principle": "P",
    "takeaway_message": "TM",
    "benchmark": "B",
    "baseline": "BL",
    "assumption": "A",
    "failure_mode": "F",
    "derived_concept": "D",
    "argument": "ARG",
    "hypothesis": "H",
    "deduction": "D",
    "generated_idea": "I",
}


def abbreviation(label: str, *, max_chars: int = 5) -> str:
    words = re.findall(r"[A-Za-z0-9]+", label or "")
    if not words:
        return "X"
    caps = "".join(word[0] for word in words if word)
    if len(caps) >= 2:
        return caps[:max_chars].upper()
    return re.sub(r"[^A-Za-z0-9]", "", words[0])[:max_chars].upper() or "X"


class SymbolRegistry:
    def __init__(self, store: GlobalStore):
        self.store = store

    def ensure_symbol(self, concept: dict[str, Any], *, namespace: str = "global", source: str = "deterministic") -> dict[str, Any]:
        concept_id = concept.get("concept_id") or ""
        if not concept_id:
            raise ValueError("Missing concept_id")
        with self.store._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM symbol_registry WHERE concept_id = ? AND namespace = ? AND status = 'active' ORDER BY created_at DESC LIMIT 1",
                (concept_id, namespace),
            ).fetchone()
            if existing:
                return dict(existing)
            prefix = PREFIX_BY_TYPE.get(concept.get("concept_type") or "", "C")
            label = concept.get("canonical_label") or concept.get("payload", {}).get("title") or concept.get("payload", {}).get("name") or concept_id
            base = f"{prefix}.{abbreviation(label)}"
            short_code = base
            counter = 2
            while conn.execute("SELECT 1 FROM symbol_registry WHERE namespace = ? AND short_code = ?", (namespace, short_code)).fetchone():
                short_code = f"{base}{counter}"
                counter += 1
            now = utc_now()
            symbol_id = stable_id("SYM", namespace, short_code, concept_id)
            gloss = concept.get("payload", {}).get("one_sentence_thesis") or concept.get("payload", {}).get("mechanism") or concept.get("payload", {}).get("message_text") or label
            conn.execute(
                """
                INSERT INTO symbol_registry(
                    symbol_id, concept_id, namespace, short_code, label, gloss,
                    symbol_source, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
                """,
                (symbol_id, concept_id, namespace, short_code, label, str(gloss)[:360], source, now, now),
            )
            return dict(conn.execute("SELECT * FROM symbol_registry WHERE symbol_id = ?", (symbol_id,)).fetchone())

    def ensure_symbols(self, concepts: list[dict[str, Any]], *, namespace: str = "global") -> list[dict[str, Any]]:
        return [self.ensure_symbol(concept, namespace=namespace) for concept in concepts]

    def expand(self, symbol_code: str, *, namespace: str = "global") -> dict[str, Any] | None:
        with self.store._connect() as conn:
            row = conn.execute(
                "SELECT * FROM symbol_registry WHERE namespace = ? AND short_code = ? ORDER BY updated_at DESC LIMIT 1",
                (namespace, symbol_code),
            ).fetchone()
        if not row:
            return None
        symbol = dict(row)
        concept = self.store.get_concept(symbol["concept_id"])
        return {"symbol": symbol, "concept": concept}

    def table(self, *, namespace: str = "global", limit: int = 200) -> list[dict[str, Any]]:
        with self.store._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM symbol_registry WHERE namespace = ? ORDER BY updated_at DESC LIMIT ?",
                (namespace, limit),
            ).fetchall()
        return [dict(row) for row in rows]
