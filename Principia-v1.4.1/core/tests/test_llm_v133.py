from __future__ import annotations

import pytest

from principia.llm import LLMClient, LLMConfig


def test_llm_call_ceiling_and_usage_are_observable() -> None:
    client = LLMClient(LLMConfig.from_model("mock", max_calls=1))

    assert client.chat_text("system", "user")
    assert client.usage_totals() == {
        "calls": 1,
        "successful_calls": 1,
        "failed_calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }

    with pytest.raises(RuntimeError, match="call ceiling reached"):
        client.chat_text("system", "user")


def test_explicit_model_resolution_preserves_call_ceiling() -> None:
    client = LLMClient(
        LLMConfig.from_model(
            "siliconflow:Qwen/Qwen3.6-35B-A3B",
            api_key="test",
            max_calls=60,
        )
    )

    assert client.resolve("siliconflow:Qwen/Qwen3.5-397B-A17B").max_calls == 60
