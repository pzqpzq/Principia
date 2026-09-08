from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable

_WORD_RE = re.compile(r"[A-Za-z0-9]+")


def short_hash(*parts: object, length: int = 8) -> str:
    payload = "\n".join(str(part) for part in parts if part is not None)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:length].upper()


def normalize_key(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or ""))
    value = value.encode("ascii", "ignore").decode("ascii")
    return " ".join(_WORD_RE.findall(value.lower()))


def readable_id(
    text: str,
    *,
    existing: Iterable[str] | None = None,
    max_len: int = 96,
    min_hash_len: int = 6,
) -> str:
    """Create a readable, stable-ish identifier with a collision suffix when needed.

    The base form keeps title-case tokens joined by underscores:
    `Cooperation_Without_Governance_Risks_Manipulative_Equilibria`.
    """

    raw = unicodedata.normalize("NFKD", str(text or ""))
    raw = raw.encode("ascii", "ignore").decode("ascii")
    words = _WORD_RE.findall(raw)
    if not words:
        words = ["Principia", short_hash(text, length=min_hash_len)]
    base = "_".join(word[:1].upper() + word[1:] for word in words)
    base = re.sub(r"_+", "_", base).strip("_")
    if len(base) > max_len:
        base = base[:max_len].rstrip("_")
    seen = set(existing or [])
    if base not in seen:
        return base
    suffix = short_hash(text, len(seen), length=min_hash_len)
    trim = max(8, max_len - len(suffix) - 1)
    candidate = f"{base[:trim].rstrip('_')}_{suffix}"
    counter = 2
    while candidate in seen:
        suffix = short_hash(text, counter, length=min_hash_len)
        candidate = f"{base[:trim].rstrip('_')}_{suffix}"
        counter += 1
    return candidate


def stable_prefixed_id(prefix: str, *parts: object, length: int = 12) -> str:
    return f"{prefix}_{short_hash(*parts, length=length)}"

