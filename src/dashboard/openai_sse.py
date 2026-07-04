"""Convert AgentEvent stream to OpenAI-compatible SSE format."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, AsyncIterator

from agent.types import AgentEvent


def format_openai_data(payload: dict[str, Any] | str) -> str:
    if isinstance(payload, str):
        return f"data: {payload}\n\n"
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def format_emperor_event(event_type: str, **fields: Any) -> str:
    payload: dict[str, Any] = {"object": "emperor.event", "type": event_type, **fields}
    return format_openai_data(payload)


def format_done() -> str:
    return "data: [DONE]\n\n"


class OpenAISseState:
    """Track streaming state for a single completion."""

    def __init__(self, *, model: str = "emperor") -> None:
        self.completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        self.model = model
        self.created = int(time.time())
        self.role_sent = False
        self.content_streamed = False
        self.pending_usage: dict[str, Any] | None = None
        self.pending_usage_snapshot: dict[str, Any] | None = None
        self.pending_finish_reason: str | None = None
        self.pending_emperor: dict[str, Any] | None = None

    def chunk(
        self,
        *,
        delta: dict[str, Any] | None = None,
        finish_reason: str | None = None,
        usage: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if delta is None:
            delta = {}
        payload: dict[str, Any] = {
            "id": self.completion_id,
            "object": "chat.completion.chunk",
            "created": self.created,
            "model": self.model,
            "choices": [
                {
                    "index": 0,
                    "delta": delta,
                    "finish_reason": finish_reason,
                }
            ],
        }
        if usage:
            payload["usage"] = usage
        return payload


def _turn_usage(snapshot: dict[str, Any]) -> dict[str, Any]:
    turn = snapshot.get("turn") or {}
    return {
        "prompt_tokens": int(turn.get("prompt_tokens") or 0),
        "completion_tokens": int(turn.get("completion_tokens") or 0),
        "total_tokens": int(turn.get("total_tokens") or 0),
    }


def _terminal_finish_reason(reason: str | None) -> str:
    if reason == "tool_calls":
        return "tool_calls"
    return "stop"


def _attach_usage_snapshot(chunk: dict[str, Any], snapshot: dict[str, Any] | None) -> dict[str, Any]:
    if not snapshot:
        return chunk
    emperor = chunk.get("emperor")
    if isinstance(emperor, dict):
        emperor = dict(emperor)
    else:
        emperor = {}
    emperor["usage_snapshot"] = snapshot
    chunk["emperor"] = emperor
    return chunk


async def agent_events_to_openai_sse(
    events: AsyncIterator[AgentEvent],
    *,
    model: str = "emperor",
) -> AsyncIterator[str]:
    state = OpenAISseState(model=model)
    sent_done = False

    async for ev in events:
        if ev.kind == "stream_delta":
            delta: dict[str, Any] = {}
            if not state.role_sent:
                delta["role"] = "assistant"
                state.role_sent = True
            text = ev.payload if isinstance(ev.payload, str) else str(ev.payload)
            if text:
                delta["content"] = text
                state.content_streamed = True
            if delta:
                yield format_openai_data(state.chunk(delta=delta))

        elif ev.kind == "thinking":
            payload = ev.payload if isinstance(ev.payload, dict) else {"text": str(ev.payload)}
            delta = {}
            if not state.role_sent:
                delta["role"] = "assistant"
                state.role_sent = True
            text = payload.get("text", "")
            if text:
                delta["reasoning_content"] = text
            if delta:
                yield format_openai_data(state.chunk(delta=delta))

        elif ev.kind == "message":
            msg = ev.payload if isinstance(ev.payload, dict) else {}
            if msg.get("role") != "assistant":
                continue
            if msg.get("tool_calls"):
                state.content_streamed = False
                continue
            content = msg.get("content")
            text = content if isinstance(content, str) else ""
            if text.strip() and not state.content_streamed:
                delta: dict[str, Any] = {}
                if not state.role_sent:
                    delta["role"] = "assistant"
                    state.role_sent = True
                delta["content"] = text
                state.content_streamed = True
                yield format_openai_data(state.chunk(delta=delta))

        elif ev.kind == "tool_start":
            state.content_streamed = False
            payload = ev.payload if isinstance(ev.payload, dict) else {}
            name = str(payload.get("name") or "")
            tool_input = payload.get("input")
            args = json.dumps(tool_input, ensure_ascii=False) if tool_input is not None else "{}"
            delta: dict[str, Any] = {}
            if not state.role_sent:
                delta["role"] = "assistant"
                state.role_sent = True
            delta["tool_calls"] = [
                {
                    "index": 0,
                    "id": f"call_{uuid.uuid4().hex[:12]}",
                    "type": "function",
                    "function": {"name": name, "arguments": args},
                }
            ]
            yield format_openai_data(state.chunk(delta=delta))

        elif ev.kind == "tool_end":
            payload = ev.payload if isinstance(ev.payload, dict) else {}
            yield format_emperor_event(
                "tool_end",
                name=payload.get("name"),
                result=payload.get("result"),
            )

        elif ev.kind == "usage_update":
            payload = ev.payload if isinstance(ev.payload, dict) else {}
            state.pending_usage_snapshot = payload
            state.pending_usage = _turn_usage(payload)
            chunk = state.chunk(
                delta={},
                usage=state.pending_usage,
            )
            yield format_openai_data(_attach_usage_snapshot(chunk, payload))

        elif ev.kind == "ask_user_questions":
            payload = ev.payload if isinstance(ev.payload, dict) else {}
            questions = payload.get("questions")
            if not isinstance(questions, list):
                questions = []
            yield format_emperor_event(
                "ask_user_questions",
                questions=[str(q) for q in questions if isinstance(q, str) and str(q).strip()],
            )

        elif ev.kind == "a2ui":
            payload = ev.payload if isinstance(ev.payload, dict) else {}
            messages = payload.get("messages")
            if not isinstance(messages, list):
                messages = []
            yield format_emperor_event("a2ui", messages=messages)

        elif ev.kind == "status" and isinstance(ev.payload, dict) and "terminal" in ev.payload:
            terminal = ev.payload["terminal"]
            reason = terminal.get("reason")
            finish_reason = _terminal_finish_reason(reason)
            delta: dict[str, Any] = {}
            message = terminal.get("message")
            if (
                isinstance(message, str)
                and message.strip()
                and not state.content_streamed
            ):
                if not state.role_sent:
                    delta["role"] = "assistant"
                    state.role_sent = True
                delta["content"] = message
            if delta:
                yield format_openai_data(state.chunk(delta=delta))
            chunk = state.chunk(
                delta={},
                finish_reason=finish_reason,
                usage=state.pending_usage,
            )
            if reason not in ("complete", "tool_calls"):
                chunk["emperor"] = {
                    "reason": reason,
                    "error": terminal.get("error"),
                    "message": terminal.get("message"),
                }
            chunk = _attach_usage_snapshot(chunk, state.pending_usage_snapshot)
            yield format_openai_data(chunk)
            yield format_done()
            sent_done = True

    if not sent_done:
        yield format_openai_data(
            state.chunk(delta={}, finish_reason="stop", usage=state.pending_usage)
        )
        yield format_done()


def steer_queued_sse(content: str) -> list[str]:
    return [
        format_emperor_event("steer_queued", content=content),
        format_emperor_event("steered"),
        format_done(),
    ]


def steer_dequeued_sse(content: str) -> str:
    return format_emperor_event("steer_dequeued", content=content)


def error_sse(message: str) -> list[str]:
    return [
        format_emperor_event("error", message=message),
        format_done(),
    ]
