from __future__ import annotations

import json
import socket
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import Settings, get_settings
from .utils import safe_json_loads


@dataclass
class CostTracker:
    limit_cny: float
    estimated_cny: float = 0.0
    calls: list[dict[str, Any]] = field(default_factory=list)

    def estimate_tokens(self, *texts: str) -> int:
        return max(1, sum(len(text or "") for text in texts) // 4)

    def estimate_price(self, model: str, input_tokens: int, output_tokens: int) -> float:
        name = model.lower()
        if "gpt-5.5" in name or "gpt-5.2-pro" in name or "gpt-5-pro" in name:
            per_million = 120.0
        elif "deepseek-v4" in name or "kimi-k2.6" in name or "qwen3.5-122" in name:
            per_million = 16.0
        elif "deepseek" in name or "qwen3-235" in name or "72b" in name or "glm-5" in name:
            per_million = 10.0
        elif "35b" in name or "32b" in name or "14b" in name:
            per_million = 3.0
        else:
            per_million = 1.2
        return ((input_tokens + output_tokens) / 1_000_000) * per_million

    def reserve(self, model: str, prompt: str, max_tokens: int) -> None:
        input_tokens = self.estimate_tokens(prompt)
        estimated = self.estimate_price(model, input_tokens, max_tokens)
        if self.estimated_cny + estimated > self.limit_cny:
            raise RuntimeError(
                f"Cost guard stopped the call: estimated {self.estimated_cny + estimated:.2f} CNY "
                f"would exceed the {self.limit_cny:.2f} CNY limit."
            )
        self.estimated_cny += estimated
        self.calls.append(
            {
                "model": model,
                "estimated_input_tokens": input_tokens,
                "reserved_output_tokens": max_tokens,
                "estimated_cny": round(estimated, 4),
            }
        )


class LLMClient:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.costs = CostTracker(limit_cny=self.settings.cost_limit_cny)

    def choose_model(self, complexity: float = 0.4, mode: str = "auto") -> str:
        return self.resolve_model(complexity=complexity, mode=mode)["model"]

    def model_label(self, mode: str = "auto", complexity: float = 0.4) -> str:
        resolved = self.resolve_model(complexity=complexity, mode=mode)
        return f"{resolved['provider']}:{resolved['model']}"

    def resolve_model(self, complexity: float = 0.4, mode: str = "auto") -> dict[str, str]:
        aliases = self.settings.model_aliases
        if mode.startswith("model:"):
            raw = mode.removeprefix("model:")
        elif mode in aliases:
            raw = aliases[mode]
        else:
            raw = self.settings.strong_model if complexity >= 0.65 else self.settings.efficient_model
        provider = "siliconflow"
        if raw.startswith("openai:"):
            provider = "openai"
            raw = raw.removeprefix("openai:")
        elif raw.startswith("siliconflow:"):
            raw = raw.removeprefix("siliconflow:")
        return {
            "provider": provider,
            "model": raw,
            "base_url": self.settings.openai_base_url if provider == "openai" else self.settings.base_url,
            "api_key": self.settings.openai_api_key if provider == "openai" else self.settings.api_key,
        }

    def available(self) -> bool:
        return self.settings.llm_available

    def chat_json(
        self,
        system: str,
        user: str,
        *,
        complexity: float = 0.4,
        mode: str = "auto",
        max_tokens: int = 2000,
        temperature: float = 0.2,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        try:
            text = self.chat_text(
                system,
                user,
                complexity=complexity,
                mode=mode,
                max_tokens=max_tokens,
                temperature=temperature,
                json_mode=True,
                timeout_seconds=timeout_seconds,
            )
        except RuntimeError as exc:
            resolved = self.resolve_model(complexity=complexity, mode=mode)
            if resolved["provider"] != "openai" or "no text output" not in str(exc).lower():
                raise
            text = self.chat_text(
                system,
                user,
                complexity=complexity,
                mode=mode,
                max_tokens=max(max_tokens * 2, 8000),
                temperature=temperature,
                json_mode=True,
                timeout_seconds=timeout_seconds,
            )
        try:
            parsed = safe_json_loads(text)
        except Exception as exc:
            resolved = self.resolve_model(complexity=complexity, mode=mode)
            repair_floor = 8000 if resolved["provider"] == "openai" else 1200
            repair_mode = mode if resolved["provider"] == "openai" else "strong"
            repair_text = self.chat_text(
                system
                + "\nConvert the supplied malformed provider response into exactly one valid JSON object. "
                "Preserve the response fields and meaning. Do not add scientific content, default ideas, or template text. "
                "Return minified strict JSON only, with no markdown or commentary. All strings must be single-line JSON strings with escaped quotes and no raw line breaks.",
                (
                    "Original user request:\n"
                    f"{user}\n\n"
                    "Malformed provider response:\n"
                    f"{text}"
                ),
                complexity=complexity,
                mode=repair_mode,
                max_tokens=max(max_tokens * 2, repair_floor),
                temperature=0,
                json_mode=True,
                timeout_seconds=timeout_seconds,
            )
            try:
                parsed = safe_json_loads(repair_text)
            except Exception as repair_exc:
                raise ValueError(f"LLM response was not valid JSON: {exc}") from repair_exc
        if not isinstance(parsed, dict):
            raise ValueError("LLM response was not a JSON object")
        return parsed

    def chat_text(
        self,
        system: str,
        user: str,
        *,
        complexity: float = 0.4,
        mode: str = "auto",
        max_tokens: int = 2000,
        temperature: float = 0.2,
        json_mode: bool = False,
        timeout_seconds: int | None = None,
    ) -> str:
        resolved = self.resolve_model(complexity=complexity, mode=mode)
        if not resolved["api_key"]:
            provider_hint = "OPENAI_API_KEY" if resolved["provider"] == "openai" else "SILICONFLOW_API_KEY"
            raise RuntimeError(f"No API key found for {resolved['provider']}. Set {provider_hint} or run with offline=True.")
        model = resolved["model"]
        prompt = system + "\n\n" + user
        self.costs.reserve(model, prompt, max_tokens)
        request_timeout = self._request_timeout(resolved, max_tokens, timeout_seconds=timeout_seconds)
        if resolved["provider"] == "openai" and model.lower().startswith("gpt-5"):
            return self._openai_responses_text(
                resolved,
                system,
                user,
                max_tokens=max_tokens,
                temperature=temperature,
                json_mode=json_mode,
                timeout_seconds=request_timeout,
            )
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        if resolved["provider"] == "siliconflow" and self._should_disable_thinking(model):
            payload["enable_thinking"] = False
        context = self._ssl_context()

        def send(payload_to_send: dict[str, Any]) -> str:
            data = json.dumps(payload_to_send).encode("utf-8")
            req = urllib.request.Request(
                resolved["base_url"] + "/chat/completions",
                data=data,
                headers={
                    "Authorization": f"Bearer {resolved['api_key']}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=request_timeout, context=context) as resp:
                return resp.read().decode("utf-8")

        try:
            raw = send(payload)
        except (TimeoutError, socket.timeout) as exc:
            raise RuntimeError(f"LLM request timed out after {request_timeout}s waiting for {resolved['provider']}:{model}.") from exc
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if json_mode and "response_format" in detail.lower():
                payload.pop("response_format", None)
                try:
                    raw = send(payload)
                except (TimeoutError, socket.timeout) as retry_exc:
                    raise RuntimeError(f"LLM request timed out after {request_timeout}s waiting for {resolved['provider']}:{model}.") from retry_exc
                except urllib.error.HTTPError as retry_exc:
                    retry_detail = retry_exc.read().decode("utf-8", errors="replace")
                    raise RuntimeError(f"LLM HTTP {retry_exc.code}: {retry_detail[:800]}") from retry_exc
                except urllib.error.URLError as retry_exc:
                    if isinstance(getattr(retry_exc, "reason", None), (TimeoutError, socket.timeout)):
                        raise RuntimeError(f"LLM request timed out after {request_timeout}s waiting for {resolved['provider']}:{model}.") from retry_exc
                    raise RuntimeError(f"LLM request failed: {retry_exc}") from retry_exc
            else:
                raise RuntimeError(f"LLM HTTP {exc.code}: {detail[:800]}") from exc
        except urllib.error.URLError as exc:
            if isinstance(getattr(exc, "reason", None), (TimeoutError, socket.timeout)):
                raise RuntimeError(f"LLM request timed out after {request_timeout}s waiting for {resolved['provider']}:{model}.") from exc
            raise RuntimeError(f"LLM request failed: {exc}") from exc
        body = json.loads(raw)
        return body["choices"][0]["message"]["content"]

    def _openai_responses_text(
        self,
        resolved: dict[str, str],
        system: str,
        user: str,
        *,
        max_tokens: int,
        temperature: float,
        json_mode: bool = False,
        timeout_seconds: int | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": resolved["model"],
            "instructions": system,
            "input": user,
            "max_output_tokens": max_tokens,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if resolved["model"].lower().startswith("gpt-5"):
            payload["reasoning"] = {"effort": "minimal"}
        if json_mode:
            payload["text"] = {"format": {"type": "json_object"}}
        body: dict[str, Any] | None = None
        last_error: RuntimeError | None = None
        for _ in range(4):
            try:
                body = self._post_json(
                    resolved["base_url"] + "/responses",
                    resolved["api_key"],
                    payload,
                    timeout_seconds=timeout_seconds,
                )
                break
            except RuntimeError as exc:
                last_error = exc
                detail = str(exc).lower()
                changed = False
                if "temperature" in detail and "temperature" in payload:
                    payload.pop("temperature", None)
                    changed = True
                if "reasoning" in detail and "reasoning" in payload:
                    payload.pop("reasoning", None)
                    changed = True
                if ("text" in detail or "format" in detail or "json_object" in detail) and "text" in payload:
                    payload.pop("text", None)
                    changed = True
                if not changed:
                    raise
        if body is None:
            raise last_error or RuntimeError("OpenAI Responses API request failed")
        text = self._extract_response_text(body)
        if not text:
            status = body.get("status") or "unknown"
            incomplete = body.get("incomplete_details") or {}
            reason = incomplete.get("reason") if isinstance(incomplete, dict) else ""
            raise RuntimeError(f"OpenAI Responses API returned no text output (status={status}, reason={reason or 'none'})")
        return text

    def _post_json(self, url: str, api_key: str, payload: dict[str, Any], *, timeout_seconds: int | None = None) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        context = self._ssl_context()
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        request_timeout = int(timeout_seconds or self.settings.request_timeout)
        try:
            with urllib.request.urlopen(req, timeout=request_timeout, context=context) as resp:
                raw = resp.read().decode("utf-8")
        except (TimeoutError, socket.timeout) as exc:
            raise RuntimeError(f"LLM request timed out after {request_timeout}s.") from exc
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM HTTP {exc.code}: {detail[:800]}") from exc
        except urllib.error.URLError as exc:
            if isinstance(getattr(exc, "reason", None), (TimeoutError, socket.timeout)):
                raise RuntimeError(f"LLM request timed out after {request_timeout}s.") from exc
            raise RuntimeError(f"LLM request failed: {exc}") from exc
        return json.loads(raw)

    def _extract_response_text(self, body: dict[str, Any]) -> str:
        if isinstance(body.get("output_text"), str):
            return body["output_text"]
        chunks: list[str] = []
        for item in body.get("output", []) or []:
            for content in item.get("content", []) or []:
                if isinstance(content, dict):
                    text = content.get("text")
                    if isinstance(text, str):
                        chunks.append(text)
                    elif isinstance(text, dict) and isinstance(text.get("value"), str):
                        chunks.append(text["value"])
        return "\n".join(chunk for chunk in chunks if chunk).strip()

    def _ssl_context(self) -> ssl.SSLContext | None:
        if not self.settings.ssl_verify:
            return ssl._create_unverified_context()
        system_bundle = Path("/etc/ssl/cert.pem")
        if system_bundle.exists():
            return ssl.create_default_context(cafile=str(system_bundle))
        default_paths = ssl.get_default_verify_paths()
        if default_paths.cafile and Path(default_paths.cafile).exists():
            return None
        return None

    def _should_disable_thinking(self, model: str) -> bool:
        name = model.lower()
        return "qwen3" in name or "qwen/qwen3" in name

    def _request_timeout(self, resolved: dict[str, str], max_tokens: int, *, timeout_seconds: int | None = None) -> int:
        if timeout_seconds is not None:
            return max(1, int(timeout_seconds))
        base = max(1, int(self.settings.request_timeout))
        slow = max(base, int(getattr(self.settings, "slow_request_timeout", base)))
        model = (resolved.get("model") or "").lower()
        provider = (resolved.get("provider") or "").lower()
        if provider == "siliconflow" and any(
            marker in model
            for marker in (
                "qwen3.5-122",
                "122b",
                "deepseek-v4",
                "kimi-k2",
                "glm-5",
                "235b",
            )
        ):
            return slow
        if max_tokens >= 2500:
            return max(base, min(slow, 300))
        return base
