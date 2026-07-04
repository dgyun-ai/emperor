"""OpenAI-compatible chat completions provider."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI

from provider.thinking import build_disable_thinking_extra_body, merge_extra_body


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ModelResponse:
    """Single chunk or final aggregated model output."""

    delta_text: str = ""
    reasoning_delta: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str | None = None
    is_final: bool = False
    assistant_message: dict[str, Any] | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class OpenAICompatProvider:
    """Streaming chat completions via OpenAI SDK with configurable base_url."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str | None = None,
    ) -> None:
        self.model = model
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def stream_chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        abort_event: Any | None = None,
        extra_body: dict[str, Any] | None = None,
        disable_thinking: bool = False,
        max_tokens: int | None = None,
    ) -> AsyncIterator[ModelResponse]:
        """Stream chat completion chunks; yields deltas then a final message."""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            kwargs["tools"] = tools
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        merged_extra = merge_extra_body(
            build_disable_thinking_extra_body() if disable_thinking else None,
            extra_body,
        )
        if merged_extra:
            kwargs["extra_body"] = merged_extra

        stream = await self._client.chat.completions.create(**kwargs)

        accumulated_text = ""
        tool_calls_acc: dict[int, dict[str, Any]] = {}
        usage_prompt = 0
        usage_completion = 0
        usage_total = 0

        async for chunk in stream:
            if abort_event is not None and abort_event.is_set():
                break

            if chunk.usage is not None:
                usage_prompt = chunk.usage.prompt_tokens or 0
                usage_completion = chunk.usage.completion_tokens or 0
                usage_total = chunk.usage.total_tokens or (usage_prompt + usage_completion)

            choice = chunk.choices[0] if chunk.choices else None
            if choice is None:
                continue

            delta = choice.delta
            delta_text = delta.content or ""
            reasoning_text = getattr(delta, "reasoning_content", None) or ""
            if reasoning_text:
                yield ModelResponse(reasoning_delta=reasoning_text)
            if delta_text:
                accumulated_text += delta_text
                yield ModelResponse(delta_text=delta_text)

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_acc:
                        tool_calls_acc[idx] = {
                            "id": tc.id or "",
                            "name": tc.function.name if tc.function else "",
                            "arguments": "",
                        }
                    entry = tool_calls_acc[idx]
                    if tc.id:
                        entry["id"] = tc.id
                    if tc.function and tc.function.name:
                        entry["name"] = tc.function.name
                    if tc.function and tc.function.arguments:
                        entry["arguments"] += tc.function.arguments

            if choice.finish_reason:
                parsed_calls = _parse_tool_calls(tool_calls_acc)
                assistant: dict[str, Any] = {"role": "assistant", "content": accumulated_text or None}
                if parsed_calls:
                    assistant["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments),
                            },
                        }
                        for tc in parsed_calls
                    ]
                yield ModelResponse(
                    delta_text="",
                    tool_calls=parsed_calls,
                    finish_reason=choice.finish_reason,
                    is_final=True,
                    assistant_message=assistant,
                    prompt_tokens=usage_prompt,
                    completion_tokens=usage_completion,
                    total_tokens=usage_total,
                )


def _parse_tool_calls(acc: dict[int, dict[str, Any]]) -> list[ToolCall]:
    result: list[ToolCall] = []
    for idx in sorted(acc.keys()):
        entry = acc[idx]
        raw_args = entry.get("arguments") or "{}"
        try:
            arguments = json.loads(raw_args)
        except json.JSONDecodeError:
            arguments = {"raw": raw_args}
        result.append(
            ToolCall(
                id=entry.get("id") or f"call_{idx}",
                name=entry.get("name") or "",
                arguments=arguments if isinstance(arguments, dict) else {"value": arguments},
            )
        )
    return [tc for tc in result if tc.name]
