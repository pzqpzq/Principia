from __future__ import annotations

import hashlib
import json
import re
import ssl
from html import unescape as html_unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import unquote

import certifi
import httpx

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
    pattern = (
        r"(?<![a-z0-9])" + r"[\s_\-]+".join(re.escape(part) for part in parts) + r"(?![a-z0-9])"
    )
    return bool(re.search(pattern, lower))


def llm_available(llm: Any | None) -> bool:
    if llm is None:
        return False
    if not hasattr(llm, "available"):
        return False
    available = llm.available
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


def call_llm_json(
    llm: Any, system: str, user: str, *, mode: str, max_tokens: int, temperature: float
) -> dict[str, Any]:
    chat_json = llm.chat_json
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
    tokens: list[str] = []
    pattern = r"[a-zA-Z][a-zA-Z0-9_\-]{1,}|\d+[a-zA-Z][a-zA-Z0-9_\-]*|[\u4e00-\u9fff]+"
    for token in re.findall(pattern, text.lower()):
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            tokens.extend(token[index : index + 2] for index in range(max(1, len(token) - 1)))
            continue
        normalized = canonical_token(token)
        if normalized not in STOPWORDS:
            tokens.append(normalized)
        # Preserve the compound for exact matching and also index its parts so
        # "sparse-view" matches "sparse view" and domain routing can see both.
        if "-" in token or "_" in token:
            for part in re.split(r"[-_]+", token):
                normalized_part = canonical_token(part)
                if len(normalized_part) >= 2 and normalized_part not in STOPWORDS:
                    tokens.append(normalized_part)
    return tokens


def canonical_token(token: str) -> str:
    if token.endswith("ies") and len(token) > 4:
        return f"{token[:-3]}y"
    if (
        token.endswith("s")
        and len(token) > 4
        and not token.endswith(("ss", "is", "us", "ics", "ysis"))
    ):
        return token[:-1]
    return token


def normalize_text(text: str) -> str:
    return " ".join(re.findall(r"[a-zA-Z0-9]+|[\u4e00-\u9fff]", str(text or "").lower()))


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


_HTML_ENTITY_RE = re.compile(r"&(?:#[0-9]+|#x[0-9a-f]+|[a-z][a-z0-9]+);", re.IGNORECASE)
_MARKUP_TAG_RE = re.compile(
    r"<!--.*?-->|<![a-z][^>]*>|</?\s*[a-z][\w:.-]*(?:\s[^<>]*?)?/?>",
    re.IGNORECASE | re.DOTALL,
)


class _ScholarlyTitleHTMLParser(HTMLParser):
    """Collect rendered title text while discarding document markup."""

    _BLOCK_TAGS = {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "div",
        "figcaption",
        "figure",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "p",
        "section",
        "table",
        "td",
        "th",
        "tr",
    }
    _HIDDEN_TAGS = {"script", "style"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._hidden_depth = 0

    @staticmethod
    def _local_name(tag: str) -> str:
        return str(tag or "").rsplit(":", 1)[-1].lower()

    def _separator(self) -> None:
        if self.parts and not self.parts[-1].endswith((" ", "\n", "\t")):
            self.parts.append(" ")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        local_name = self._local_name(tag)
        if self._hidden_depth:
            self._hidden_depth += 1
            return
        if local_name in self._HIDDEN_TAGS:
            self._hidden_depth = 1
            return
        if local_name in self._BLOCK_TAGS:
            self._separator()

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if not self._hidden_depth and self._local_name(tag) in self._BLOCK_TAGS:
            self._separator()

    def handle_endtag(self, tag: str) -> None:
        if self._hidden_depth:
            self._hidden_depth -= 1
            return
        if self._local_name(tag) in self._BLOCK_TAGS:
            self._separator()

    def handle_data(self, data: str) -> None:
        if not self._hidden_depth:
            self.parts.append(data)


def normalize_scholarly_title(value: Any) -> str:
    """Return the rendered text of a scholarly title.

    Metadata providers sometimes embed inline HTML, XML, or namespaced MathML
    in title fields.  Decode explicit character references and remove only
    syntactically tag-like markup, retaining its visible text.  Plain text,
    comparison operators, and existing LaTeX commands/delimiters are left
    intact apart from normal whitespace collapsing.
    """

    text = str(value or "")
    text = _HTML_ENTITY_RE.sub(lambda match: html_unescape(match.group(0)), text)
    if not _MARKUP_TAG_RE.search(text):
        return clean_text(text)
    parser = _ScholarlyTitleHTMLParser()
    parser.feed(text)
    parser.close()
    return clean_text("".join(parser.parts))


def strip_tags(value: str) -> str:
    return clean_text(re.sub(r"<[^>]+>", " ", str(value or "")))


def title_key(title: str) -> str:
    return normalize_text(title)


def stable_id(prefix: str, *parts: Any, length: int = 12) -> str:
    payload = "\n".join(str(part) for part in parts if part)
    return f"{prefix}-{hashlib.sha1(payload.encode('utf-8')).hexdigest()[:length].upper()}"


def clean_doi(value: Any) -> str:
    text = unquote(str(value or "")).strip()
    # Providers and legacy workspaces expose the same DOI as a bare value,
    # ``doi:...``, or an http(s) resolver URL with arbitrary casing.  Normalize
    # those transport forms before identity matching while leaving the DOI
    # suffix itself intact.
    prefix = re.compile(
        r"^(?:(?:https?://)?(?:(?:dx|www)\.)?doi\.org/|doi\s*:\s*)",
        flags=re.I,
    )
    previous = None
    while text and text != previous:
        previous = text
        text = prefix.sub("", text, count=1).strip()
    return text.strip().lower()


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
    # Supplying certifi explicitly avoids platform-dependent trust-store
    # failures (notably on fresh macOS Python installations).
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    with httpx.Client(
        verify=ssl_context,
        follow_redirects=True,
        timeout=max(0.1, float(timeout or 12.0)),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json,application/atom+xml,*/*"},
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.content


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
