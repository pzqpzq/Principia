from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, replace
from typing import Any

import httpx

SECRET_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|password|passwd|pwd|bearer)\b\s*[:=]\s*([^\s,;]+)"
)


def redact_secrets(text: str) -> str:
    return SECRET_PATTERN.sub(lambda match: f"{match.group(1)}: [REDACTED]", str(text or ""))


@dataclass(frozen=True)
class LLMConfig:
    provider: str = "auto"
    model: str = "auto"
    api_key: str = ""
    base_url: str = ""
    timeout: float = 180.0
    max_retries: int = 3
    cost_limit_usd: float = 50.0
    disable_thinking: bool = True

    @classmethod
    def from_model(cls, model: str = "auto", **overrides: Any) -> LLMConfig:
        value = str(model or "auto")
        provider = str(overrides.pop("provider", "") or "auto")
        raw_model = value
        if ":" in value and not value.startswith("http"):
            maybe_provider, maybe_model = value.split(":", 1)
            if maybe_provider in {"openai", "siliconflow", "custom", "mock"}:
                provider = maybe_provider
                raw_model = maybe_model
        if raw_model == "mock" or provider == "mock":
            provider = "mock"
            raw_model = "mock"
        if provider == "auto":
            provider = "openai" if os.getenv("OPENAI_API_KEY") else "siliconflow"
        api_key = str(overrides.pop("api_key", "") or "")
        base_url = str(overrides.pop("base_url", "") or "")
        if provider == "openai":
            api_key = api_key or os.getenv("OPENAI_API_KEY", "")
            base_url = (base_url or os.getenv("PRINCIPIA_OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        elif provider == "siliconflow":
            api_key = api_key or os.getenv("SILICONFLOW_API_KEY", "") or os.getenv("PRINCIPIA_API_KEY", "")
            base_url = (base_url or os.getenv("PRINCIPIA_LLM_BASE_URL", "https://api.siliconflow.cn/v1")).rstrip("/")
        else:
            api_key = api_key or os.getenv("PRINCIPIA_LLM_API_KEY", "")
            base_url = (base_url or os.getenv("PRINCIPIA_LLM_BASE_URL", "")).rstrip("/")
        if raw_model == "auto":
            raw_model = os.getenv("PRINCIPIA_MODEL", "gpt-4.1" if provider == "openai" else "Qwen/Qwen3.6-27B")
        return cls(provider=provider, model=raw_model, api_key=api_key, base_url=base_url, **overrides)

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model}"


class LLMClient:
    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig.from_model("auto")

    def available(self, model: str = "auto") -> bool:
        config = self.resolve(model)
        return config.provider == "mock" or bool(config.api_key and config.base_url)

    def resolve(self, model: str = "auto") -> LLMConfig:
        if model and model != "auto":
            resolved = LLMConfig.from_model(
                model,
                timeout=self.config.timeout,
                max_retries=self.config.max_retries,
                cost_limit_usd=self.config.cost_limit_usd,
                disable_thinking=self.config.disable_thinking,
            )
            if resolved.provider == self.config.provider:
                resolved = replace(
                    resolved,
                    api_key=self.config.api_key or resolved.api_key,
                    base_url=self.config.base_url or resolved.base_url,
                )
            return resolved
        return self.config

    def chat_json(
        self,
        system: str,
        user: str,
        *,
        model: str = "auto",
        max_tokens: int = 2400,
        temperature: float = 0.2,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        text = self.chat_text(
            system,
            user,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
            json_mode=True,
        )
        try:
            return self._json_from_text(text)
        except Exception as exc:
            repair_text = self.chat_text(
                "You repair malformed model output into one strict JSON object. Return JSON only.",
                (
                    "Original task:\n"
                    f"{user}\n\n"
                    "Malformed model output:\n"
                    f"{text}\n\n"
                    "Return exactly one valid JSON object. Do not add new facts."
                ),
                model=model,
                max_tokens=max(1200, min(max_tokens * 2, 6000)),
                temperature=0,
                timeout=timeout,
                json_mode=True,
            )
            try:
                return self._json_from_text(repair_text)
            except Exception as repair_exc:
                raise ValueError(f"LLM response was not valid JSON: {exc}") from repair_exc

    def chat_text(
        self,
        system: str,
        user: str,
        *,
        model: str = "auto",
        max_tokens: int = 2400,
        temperature: float = 0.2,
        timeout: float | None = None,
        json_mode: bool = False,
    ) -> str:
        config = self.resolve(model)
        if config.provider == "mock":
            return json.dumps({"ok": True, "message": "mock"})
        if not config.api_key:
            raise RuntimeError(f"No API key configured for {config.provider}; set environment variables or pass LLMConfig.")
        if not config.base_url:
            raise RuntimeError(f"No base URL configured for {config.provider}.")
        headers = {"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"}
        payload: dict[str, Any] = {
            "model": config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": redact_secrets(user)},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        if config.disable_thinking and config.provider == "siliconflow" and "qwen" in config.model.lower():
            payload["enable_thinking"] = False
        last_error: Exception | None = None
        for attempt in range(config.max_retries + 1):
            try:
                with httpx.Client(timeout=timeout or config.timeout) as client:
                    response = client.post(f"{config.base_url}/chat/completions", headers=headers, json=payload)
                    try:
                        response.raise_for_status()
                    except httpx.HTTPStatusError as exc:
                        detail = response.text[:500]
                        raise RuntimeError(
                            f"Provider returned HTTP {response.status_code}: {redact_secrets(detail)}"
                        ) from exc
                    data = response.json()
                choice = (data.get("choices") or [{}])[0]
                message = choice.get("message") or {}
                content = self._message_text(message, choice)
                if not content:
                    raise RuntimeError("LLM response contained no text output")
                return str(content)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt >= config.max_retries:
                    break
                time.sleep(self._retry_delay_seconds(exc, attempt))
        raise RuntimeError(f"LLM call failed: {last_error}") from last_error

    def _retry_delay_seconds(self, exc: Exception, attempt: int) -> float:
        text = str(exc).lower()
        transient = any(fragment in text for fragment in ["http 429", "http 500", "http 502", "http 503", "http 504", "timeout", "temporarily", "rate"])
        base = 3.0 if transient else 0.75
        return min(30.0, base * (2**attempt))

    def _message_text(self, message: Any, choice: dict[str, Any]) -> str:
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content
            if isinstance(content, list):
                parts: list[str] = []
                for item in content:
                    if isinstance(item, dict):
                        value = item.get("text") or item.get("content")
                        if value:
                            parts.append(str(value))
                    elif item:
                        parts.append(str(item))
                if parts:
                    return "\n".join(parts)
            # Some providers expose reasoning separately. Use it only as a last
            # resort because it can contain non-JSON chain-of-thought style text.
            reasoning = message.get("reasoning_content")
            if isinstance(reasoning, str) and reasoning.strip() and not choice.get("finish_reason") == "length":
                return reasoning
        elif isinstance(message, str):
            return message
        text = choice.get("text")
        return str(text or "")

    def _json_from_text(self, text: str) -> dict[str, Any]:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, flags=re.S)
            if not match:
                raise
            parsed = json.loads(match.group(0))
        if not isinstance(parsed, dict):
            raise ValueError("LLM response was not a JSON object")
        return parsed


class MockLLMClient(LLMClient):
    def __init__(self) -> None:
        super().__init__(LLMConfig.from_model("mock"))

    def chat_json(self, system: str, user: str, **kwargs: Any) -> dict[str, Any]:
        if "extract" in system.lower():
            return {
                "ideas": [
                    {
                        "title": "Evidence-gated mechanism transfer",
                        "core_idea": "Activate a mechanism only when source evidence predicts a measurable advantage.",
                        "evidence": "Mock source evidence.",
                    }
                ],
                "principles": [
                    {
                        "name": "Evidence-gated activation",
                        "argument": "A research mechanism should activate only when evidence anchors and validation constraints support it.",
                        "evidence": "Mock source evidence.",
                    }
                ],
                "takeaways": [
                    {
                        "title": "Use evidence gates",
                        "message": "Evidence gates reduce unsupported mechanism transfer.",
                    }
                ],
                "benchmarks": [{"name": "small validation slice", "metric": "accuracy-cost frontier"}],
                "baselines": [{"name": "ungated baseline", "type": "ablation"}],
            }
        if "compare" in system.lower():
            return {
                "rows": [
                    {
                        "work_id": "mock",
                        "title": "Mock prior idea",
                        "mechanistic_similarity": "Both methods use a diagnostic signal to decide when an intervention should run.",
                        "essential_difference": "The new idea treats the diagnostic as an explicit reusable framework primitive.",
                        "potential_advantage": "It can skip unsupported interventions and preserve cost.",
                        "potential_weakness": "The diagnostic may reject a rare but useful mechanism.",
                    }
                ]
            }
        return {
            "title": "Evidence-Gated Research Mechanism",
            "thesis": "Turn selected evidence into a gated mechanism that can be validated against a nearest baseline.",
            "novelty_claim": "The idea makes evidence gating a first-class control loop for research ideation.",
            "mechanism_design": [
                "Represent each source mechanism with evidence anchors, baseline contrast, and validation cost.",
                "Score each mechanism by anchor coverage minus validation cost.",
                "Activate only mechanisms that clear a user-defined evidence threshold.",
            ],
            "method_variants": ["strict evidence threshold", "cost-first threshold"],
            "why_it_might_work": ["It avoids unsupported transfer.", "It creates a clean ablation."],
            "validation_protocol": ["Compare gated and ungated variants on a small validation slice."],
            "baselines": ["ungated transfer", "nearest prior method"],
            "metrics": ["quality", "cost", "time to first signal"],
            "risks": ["A poor evidence gate can suppress useful mechanisms."],
            "derived_principles": ["Evidence gates should precede expensive mechanism activation."],
        }


def siliconflow_config(
    api_key: str,
    model: str = "Qwen/Qwen3.5-397B-A17B",
    **overrides: Any,
) -> LLMConfig:
    api_key = str(api_key or "").strip()
    if api_key in {"", "YOUR_SILICONFLOW_API_KEY", "sk-your-key-here", "sk-..."}:
        raise ValueError('Set API_key to your SiliconFlow key first, for example: API_key = "sk-..."')
    model_name = model if model.startswith("siliconflow:") else f"siliconflow:{model}"
    return LLMConfig.from_model(model_name, api_key=api_key, **overrides)
