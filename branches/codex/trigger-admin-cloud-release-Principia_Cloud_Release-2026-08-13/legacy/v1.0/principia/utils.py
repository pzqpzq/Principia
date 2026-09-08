from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "for", "from", "how",
    "design", "find", "generate", "idea", "ideas", "improve", "improving", "in",
    "into", "is", "it", "its", "like", "method", "novel", "of", "on", "or",
    "our", "please", "proposal", "task", "tasks", "that", "the", "their", "this",
    "to", "testable", "use", "used", "using", "validation", "via", "we", "with", "within",
    "without", "would",
}

VALIDATION_WEIGHTS = {"L0": 0.12, "L1": 0.28, "L2": 0.46, "L3": 0.66, "L4": 0.84, "L5": 1.0}
ZH_QUERY_EXPANSIONS: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("三维重建", "3d reconstruction"),
        (
            "3d reconstruction",
            "three dimensional reconstruction",
            "multi view stereo",
        ),
    ),
    (
        ("稀疏数据", "稀疏视角", "有限视角", "少视角", "有限视图"),
        (
            "sparse view",
            "few view",
            "limited view",
            "sparse-view 3d reconstruction",
            "few-view 3d reconstruction",
        ),
    ),
    (
        ("神经辐射场", "nerf"),
        (
            "neural radiance fields",
            "nerf",
        ),
    ),
    (
        ("高斯", "gaussian"),
        (
            "3d gaussian splatting",
            "gaussian splatting",
        ),
    ),
    (
        ("点云", "point cloud"),
        (
            "point cloud",
            "point cloud completion",
        ),
    ),
    (
        ("timesfm", "时序", "时间序列", "序列特征"),
        (
            "time series foundation model",
            "time series representation learning",
            "time series forecasting",
            "TimesFM",
        ),
    ),
    (
        ("传感器", "多传感器", "跨传感器", "sensor"),
        (
            "multisensor fusion",
            "cross sensor attention",
            "sensor transformer",
            "industrial sensor data",
        ),
    ),
    (
        ("剩余使用寿命", "rul", "remaining useful life", "寿命预测"),
        (
            "remaining useful life prediction",
            "RUL prediction",
            "prognostics",
            "degradation modeling",
        ),
    ),
    (
        ("mas", "multi-agent", "multi agent", "agent society", "agentic", "llm agent"),
        (
            "multi-agent systems",
            "LLM agents",
            "agent communication",
            "agent collaboration",
        ),
    ),
    (
        ("scientific discovery", "science discovery", "research discovery", "科学发现"),
        (
            "AI for scientific discovery",
            "automated scientific discovery",
            "hypothesis generation",
            "scientific reasoning",
        ),
    ),
    (
        ("symbolic compactness", "symbolic", "intrinsic reward", "intrinsic rewards", "compactness reward"),
        (
            "symbolic reasoning",
            "minimum description length",
            "program synthesis",
            "intrinsic motivation",
            "representation compression",
        ),
    ),
    (
        ("machine dialect", "machine dialects", "dialect", "social interaction", "token cost", "completion cost"),
        (
            "agent communication protocol",
            "language model reasoning efficiency",
            "token efficient reasoning",
            "multi-agent debate",
            "emergent communication",
        ),
    ),
    (
        ("few shot", "few-shot", "小样本", "少样本"),
        (
            "few-shot learning",
            "few-shot image classification",
            "few-shot transfer learning",
            "low-shot visual recognition",
        ),
    ),
    (
        ("test time training", "test-time training", "test time adaptation", "test-time adaptation", "ttt", "测试时训练", "测试时适应"),
        (
            "test-time training",
            "test-time adaptation",
            "online adaptation",
            "transductive inference",
        ),
    ),
    (
        ("clip", "视觉模型", "vision model", "vit", "vit^3", "cvpr2026", "4090"),
        (
            "CLIP",
            "vision-language model",
            "Vision Transformer",
            "parameter-efficient tuning",
            "prompt learning",
        ),
    ),
]


def stable_id(prefix: str, *parts: str, length: int = 12) -> str:
    payload = "\n".join(str(part) for part in parts if part)
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:length].upper()
    return f"{prefix}-{digest}"


def slugify(text: str, max_len: int = 72) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return value[:max_len].strip("-") or "principia-idea"


def tokenize(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_\-]{2,}", text.lower())
        if token not in STOPWORDS
    ]


def query_expansions(text: str) -> list[str]:
    lower = text.lower()
    expansions: list[str] = []
    for triggers, phrases in ZH_QUERY_EXPANSIONS:
        def matches(trigger: str) -> bool:
            normalized = trigger.lower()
            if normalized == "rul":
                return bool(re.search(r"(?<![a-z0-9])rul(?![a-z0-9])", lower))
            return normalized in lower

        if any(matches(trigger) for trigger in triggers):
            expansions.extend(phrases)
    deduped: list[str] = []
    for phrase in expansions:
        if phrase not in deduped:
            deduped.append(phrase)
    return deduped


def enrich_query(text: str) -> str:
    expansions = query_expansions(text)
    if not expansions:
        return text
    return " ".join([text, *expansions])


def keyword_terms(text: str, limit: int = 8) -> list[str]:
    counts: dict[str, int] = {}
    for token in tokenize(text):
        counts[token] = counts.get(token, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [token for token, _ in ranked[:limit]]


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def validation_number(level: str) -> int:
    match = re.search(r"\d", level or "")
    return int(match.group(0)) if match else 0


def _repair_json_object_syntax(text: str) -> str:
    repaired = text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
    repaired = re.sub(
        r'([{\[,]\s*)([A-Za-z_][A-Za-z0-9_\-]*)(\s*:)',
        lambda match: f'{match.group(1)}"{match.group(2)}"{match.group(3)}',
        repaired,
    )
    return repaired


def safe_json_loads(text: str) -> Any:
    text = text.strip()
    if not text:
        raise ValueError("empty JSON text")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    repaired = _repair_json_object_syntax(text)
    if repaired != text:
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S | re.I)
    if fenced:
        fenced_text = fenced.group(1).strip()
        try:
            return json.loads(fenced_text)
        except json.JSONDecodeError:
            return json.loads(_repair_json_object_syntax(fenced_text))
    start = min([idx for idx in [text.find("{"), text.find("[")] if idx >= 0], default=-1)
    if start < 0:
        raise ValueError("LLM response did not contain a JSON object or array")
    opening = text[start]
    closing = "}" if opening == "{" else "]"
    end = text.rfind(closing)
    if end <= start:
        raise ValueError("LLM response contained incomplete JSON")
    candidate = text[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return json.loads(_repair_json_object_syntax(candidate))


def sentence_split(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", cleaned) if part.strip()]


def lexical_score(query: str, text: str) -> float:
    q = set(tokenize(enrich_query(query)))
    if not q:
        return 0.0
    t = tokenize(text)
    if not t:
        return 0.0
    tf = {token: t.count(token) for token in set(t)}
    overlap = sum(1.0 + math.log(1 + tf[token]) for token in q if token in tf)
    return overlap / math.sqrt(len(q) + len(t))


def compact_text(text: str, limit: int = 900) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."
