from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from typing import Any

from .constants import STOPWORDS, USER_AGENT


def contains_query_trigger(text: str, trigger: str) -> bool:
    lower = str(text or "").lower()
    normalized = str(trigger or "").lower().strip()
    if not normalized:
        return False
    if any("\u4e00" <= char <= "\u9fff" for char in normalized):
        return normalized in lower
    parts = [part for part in re.split(r"[\s_\-]+", normalized) if part]
    if not parts:
        return False
    pattern = r"(?<![a-z0-9])" + r"[\s_\-]+".join(re.escape(part) for part in parts) + r"(?![a-z0-9])"
    return bool(re.search(pattern, lower))


def llm_available(llm: Any | None) -> bool:
    if llm is None:
        return False
    available = getattr(llm, "available", None)
    if not callable(available):
        return False
    try:
        return bool(available())
    except TypeError:
        try:
            return bool(available("auto"))
        except Exception:
            return False
    except Exception:
        return False


def call_llm_json(llm: Any, system: str, user: str, *, mode: str, max_tokens: int, temperature: float) -> dict[str, Any]:
    chat_json = getattr(llm, "chat_json")
    try:
        return chat_json(system, user, mode=mode, max_tokens=max_tokens, temperature=temperature)
    except TypeError:
        return chat_json(system, user, model=mode, max_tokens=max_tokens, temperature=temperature)


def weighted_tokens(text: str) -> dict[str, float]:
    output: dict[str, float] = {}
    for token in tokenize(text):
        output[token] = max(output.get(token, 0.0), token_weight(token))
    return output


def token_weight(token: str) -> float:
    if re.search(r"\d", token) and len(token) >= 5:
        return 3.0
    if len(token) >= 9:
        return 1.6
    if len(token) >= 6:
        return 1.2
    return 1.0


def tokenize(text: str) -> list[str]:
    tokens = []
    for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_\-]{2,}|[\u4e00-\u9fff]+", text.lower()):
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            tokens.extend(token[index : index + 2] for index in range(max(1, len(token) - 1)))
        elif token not in STOPWORDS:
            tokens.append(canonical_token(token))
    return tokens


def canonical_token(token: str) -> str:
    if token.endswith("ies") and len(token) > 4:
        return f"{token[:-3]}y"
    if token.endswith("s") and len(token) > 4:
        return token[:-1]
    return token


def normalize_text(text: str) -> str:
    return " ".join(re.findall(r"[a-zA-Z0-9]+|[\u4e00-\u9fff]", str(text or "").lower()))


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def strip_tags(value: str) -> str:
    return clean_text(re.sub(r"<[^>]+>", " ", str(value or "")))


def title_key(title: str) -> str:
    return normalize_text(title)


def stable_id(prefix: str, *parts: Any, length: int = 12) -> str:
    payload = "\n".join(str(part) for part in parts if part)
    return f"{prefix}-{hashlib.sha1(payload.encode('utf-8')).hexdigest()[:length].upper()}"


def clean_doi(value: Any) -> str:
    text = str(value or "").strip()
    return text.removeprefix("https://doi.org/").removeprefix("http://doi.org/").lower()


def extract_arxiv_id(value: str) -> str:
    match = re.search(r"arxiv\.org/(?:abs|pdf)/([^?#/\s]+)", str(value or ""), flags=re.I)
    if not match:
        match = re.search(r"\barxiv:([0-9]{4}\.[0-9]{4,5}(?:v\d+)?)", str(value or ""), flags=re.I)
    return match.group(1).removesuffix(".pdf") if match else ""


def openalex_abstract(index: dict[str, list[int]]) -> str:
    if not isinstance(index, dict) or not index:
        return ""
    pairs = []
    for token, positions in index.items():
        for pos in positions or []:
            if isinstance(pos, int):
                pairs.append((pos, token))
    pairs.sort()
    return clean_text(" ".join(token for _, token in pairs))


def fetch_json(url: str, timeout: float) -> dict[str, Any]:
    return json.loads(fetch_bytes(url, timeout).decode("utf-8", errors="replace"))


def fetch_bytes(url: str, timeout: float) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json,*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def string_list(value: Any) -> list[str]:
    rows = value if isinstance(value, list) else []
    return [clean_text(row) for row in rows if clean_text(row)]


def ordered_unique(values: list[Any]) -> list[str]:
    output = []
    seen = set()
    for value in values:
        text = clean_text(value)
        if text and text not in seen:
            output.append(text)
            seen.add(text)
    return output


def clamp_float(value: Any, low: float, high: float) -> float:
    try:
        number = float(value)
    except Exception:
        number = low
    return max(low, min(high, number))


def max_int(left: Any, right: Any) -> int | None:
    values = []
    for item in [left, right]:
        try:
            values.append(int(item))
        except Exception:
            pass
    return max(values) if values else None


def truncate(value: Any, limit: int) -> str:
    text = clean_text(value)
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def strip_internal(work: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in work.items() if not key.startswith("_")}
