"""Shared test helpers."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import tools.builtin  # noqa: F401 — register echo tool

from config.models import AgentConfig, EmperorConfig
from provider.openai_compat import ModelResponse, ToolCall

# Disable LLM title generation in tests unless explicitly testing titles.
TEST_CONFIG = EmperorConfig(agent=AgentConfig(auto_title=False))


def bootstrap_dashboard(client, *, token: str = "test-token", profile: str = "default") -> dict[str, str]:
    """Initialize dashboard auth and return default auth headers."""
    client.post(
        "/api/dashboard/bootstrap",
        json={
            "token": token,
            "profile_name": profile,
            "profile_display_name": profile,
            "provider": {
                "provider": "openrouter",
                "model": "anthropic/claude-sonnet-4",
                "base_url": "https://openrouter.ai/api/v1",
                "api_key_env": "OPENROUTER_API_KEY",
            },
        },
    )
    return {
        "Authorization": f"Bearer {token}",
        "X-Emperor-Profile": profile,
    }


async def mock_text_response(text: str) -> AsyncIterator[ModelResponse]:
    """Yield streaming deltas then a final assistant message."""
    for char in text:
        yield ModelResponse(delta_text=char)
    yield ModelResponse(
        is_final=True,
        finish_reason="stop",
        assistant_message={"role": "assistant", "content": text},
    )


async def mock_tool_then_text(
    tool_name: str,
    tool_args: dict[str, Any],
    tool_call_id: str,
    final_text: str,
) -> AsyncIterator[ModelResponse]:
    """First turn: assistant with tool_calls; caller should invoke again for final text."""
    yield ModelResponse(
        is_final=True,
        finish_reason="tool_calls",
        tool_calls=[ToolCall(id=tool_call_id, name=tool_name, arguments=tool_args)],
        assistant_message={
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps(tool_args),
                    },
                }
            ],
        },
    )


def make_sequential_mock(
    responses: list[Callable[[], AsyncIterator[ModelResponse]]],
):
    """Return call_model that yields predefined responses in order."""
    index = 0

    async def call_model(
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        abort_event: Any | None = None,
        extra_body: dict[str, Any] | None = None,
        disable_thinking: bool = False,
    ) -> AsyncIterator[ModelResponse]:
        nonlocal index
        if index >= len(responses):
            raise RuntimeError("No more mock responses")
        stream = responses[index]()
        index += 1
        async for chunk in stream:
            if abort_event is not None and abort_event.is_set():
                return
            yield chunk

    return call_model
