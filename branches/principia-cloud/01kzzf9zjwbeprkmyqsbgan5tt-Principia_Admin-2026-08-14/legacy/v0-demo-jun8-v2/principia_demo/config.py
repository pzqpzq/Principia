from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
STATIC_DIR = ROOT_DIR / "static"
STORE_PATH = DATA_DIR / "store.json"
STORE_DB_PATH = DATA_DIR / "principia.sqlite"


def load_dotenv(path: Path | None = None) -> None:
    env_path = path or ROOT_DIR / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str
    openai_api_key: str
    openai_base_url: str
    efficient_model: str
    strong_model: str
    model_aliases: dict[str, str]
    cost_limit_cny: float
    request_timeout: int
    ssl_verify: bool

    @property
    def llm_available(self) -> bool:
        return bool(self.api_key or self.openai_api_key)


def get_settings() -> Settings:
    load_dotenv()
    api_key = (
        os.getenv("SILICONFLOW_API_KEY")
        or os.getenv("PRINCIPIA_API_KEY")
        or ""
    )
    return Settings(
        api_key=api_key,
        base_url=os.getenv("PRINCIPIA_LLM_BASE_URL", "https://api.siliconflow.cn/v1").rstrip("/"),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_base_url=os.getenv("PRINCIPIA_OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        efficient_model=os.getenv("PRINCIPIA_EFFICIENT_MODEL", "Qwen/Qwen2.5-7B-Instruct"),
        strong_model=os.getenv("PRINCIPIA_STRONG_MODEL", "deepseek-ai/DeepSeek-V3"),
        model_aliases={
            "efficient": os.getenv("PRINCIPIA_EFFICIENT_MODEL", "Qwen/Qwen2.5-7B-Instruct"),
            "strong": os.getenv("PRINCIPIA_STRONG_MODEL", "deepseek-ai/DeepSeek-V3"),
            "kimi": os.getenv("PRINCIPIA_KIMI_MODEL", "Pro/moonshotai/Kimi-K2.6"),
            "deepseek_pro": os.getenv("PRINCIPIA_DEEPSEEK_PRO_MODEL", "deepseek-ai/DeepSeek-V4-Pro"),
            "qwen_35b": os.getenv("PRINCIPIA_QWEN_35B_MODEL", "Qwen/Qwen3.6-35B-A3B"),
            "qwen_122b": os.getenv("PRINCIPIA_QWEN_122B_MODEL", "Qwen/Qwen3.5-122B-A10B"),
            "glm": os.getenv("PRINCIPIA_GLM_MODEL", "Pro/zai-org/GLM-5.1"),
            "openai_gpt5_pro": os.getenv("PRINCIPIA_OPENAI_GPT5_PRO_MODEL", "openai:gpt-5-pro"),
            "openai_gpt52_pro": os.getenv("PRINCIPIA_OPENAI_GPT52_PRO_MODEL", "openai:gpt-5.2-pro"),
            "openai_gpt55": os.getenv("PRINCIPIA_OPENAI_GPT55_MODEL", "openai:gpt-5.5"),
            "openai_gpt55_pro_20260423": os.getenv(
                "PRINCIPIA_OPENAI_GPT55_PRO_20260423_MODEL",
                "openai:gpt-5.5-pro-2026-04-23",
            ),
        },
        cost_limit_cny=float(os.getenv("PRINCIPIA_COST_LIMIT_CNY", "1000")),
        request_timeout=int(os.getenv("PRINCIPIA_REQUEST_TIMEOUT", "180")),
        ssl_verify=os.getenv("PRINCIPIA_SSL_VERIFY", "1").strip().lower() not in {"0", "false", "no"},
    )
