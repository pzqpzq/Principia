from __future__ import annotations

import ipaddress
import os
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, model_validator

from ..domain import DomainModel

SILICONFLOW_AUTHORIZED_BASE_URLS = (
    "https://api.siliconflow.com/v1",
    "https://api.siliconflow.cn/v1",
)


class ModelPolicy(DomainModel):
    mode: Literal["local", "remote", "no_llm"]
    provider: str = ""
    model: str = ""
    base_url: str = ""
    remote_egress_confirmed: bool = False

    @model_validator(mode="after")
    def validate_policy(self) -> ModelPolicy:
        if self.mode == "no_llm":
            if self.provider or self.model or self.base_url or self.remote_egress_confirmed:
                raise ValueError("no_llm policy cannot configure a provider")
            return self
        if not self.provider or not self.model or not self.base_url:
            raise ValueError("model policies require provider, model, and base_url")
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("base_url must be an HTTP(S) endpoint")
        if self.mode == "local":
            host = parsed.hostname
            is_loopback = host == "localhost"
            if not is_loopback:
                try:
                    is_loopback = ipaddress.ip_address(host).is_loopback
                except ValueError:
                    is_loopback = False
            if not is_loopback:
                raise ValueError("local model policy requires a loopback endpoint")
        elif not self.remote_egress_confirmed:
            raise ValueError("remote model policy requires explicit egress confirmation")
        return self


class ProviderProfile(DomainModel):
    provider: str
    label: str
    base_url: str
    default_model: str
    configured: bool
    remote: bool
    models: list[str] = Field(default_factory=list)
    json_mode: bool = True
    structured_outputs: bool = False
    max_concurrency: int = Field(default=4, ge=1, le=8)
    credential_source: Literal["workspace", "environment", "none"] = "none"
    saved_at: str = ""

    @classmethod
    def siliconflow(cls) -> ProviderProfile:
        return cls(
            provider="siliconflow",
            label="SiliconFlow",
            base_url=os.getenv(
                "PRINCIPIA_LLM_BASE_URL", SILICONFLOW_AUTHORIZED_BASE_URLS[0]
            ),
            default_model=os.getenv(
                "PRINCIPIA_LLM_MODEL", "deepseek-ai/DeepSeek-V4-Flash"
            ),
            configured=bool(
                os.getenv("PRINCIPIA_LLM_API_KEY") or os.getenv("SILICONFLOW_API_KEY")
            ),
            remote=True,
            models=[
                "deepseek-ai/DeepSeek-V4-Flash",
                "deepseek-ai/DeepSeek-V4-Pro",
                "zai-org/GLM-5.2",
            ],
            json_mode=True,
            structured_outputs=False,
            max_concurrency=8,
        )


class ProviderTrace(DomainModel):
    provider: str
    model: str
    prompt_template: str
    prompt_sha256: str
    input_sha256: str
    output_sha256: str
    latency_ms: int = Field(ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    attempts: int = Field(ge=1, le=4)
    transport_attempts: int = Field(default=1, ge=1, le=12)
    repair_attempted: bool = False
    schema_valid: bool
