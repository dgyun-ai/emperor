"""Request kwargs to disable thinking/reasoning on compatible providers."""

from __future__ import annotations

from typing import Any


def build_disable_thinking_extra_body() -> dict[str, Any]:
    """
    extra_body fields for lightweight calls (titles, follow-up questions).

    StepFun/DashScope/NIM use enable_thinking/thinking/chat_template_kwargs.
    OpenRouter uses the unified ``reasoning`` object — ``include_reasoning: false``
    only excludes reasoning from the response; the model may still spend minutes
    thinking unless ``reasoning.enabled`` is false / ``effort`` is ``none``.
    """
    return {
        "enable_thinking": False,
        "thinking": False,
        "chat_template_kwargs": {"thinking": False},
        # OpenRouter / OpenAI-style gateways
        "reasoning": {
            "enabled": False,
            "effort": "none",
            "exclude": True,
        },
        "reasoning_effort": "none",
    }


def merge_extra_body(*parts: dict[str, Any] | None) -> dict[str, Any] | None:
    """Deep-merge extra_body dicts (chat_template_kwargs merged shallowly)."""
    merged: dict[str, Any] = {}
    for part in parts:
        if not part:
            continue
        for key, value in part.items():
            if (
                key == "chat_template_kwargs"
                and isinstance(value, dict)
                and isinstance(merged.get(key), dict)
            ):
                merged[key] = {**merged[key], **value}
            else:
                merged[key] = value
    return merged or None
