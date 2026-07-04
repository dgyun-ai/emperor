"""OpenClaw-style session event types and helpers."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


SESSION_VERSION = 3


def _short_id() -> str:
    return uuid.uuid4().hex[:8]


def iso_timestamp(ts: float | None = None) -> str:
    when = datetime.fromtimestamp(ts or datetime.now(tz=timezone.utc).timestamp(), tz=timezone.utc)
    return when.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def epoch_ms(ts: float | None = None) -> int:
    when = ts or datetime.now(tz=timezone.utc).timestamp()
    return int(when * 1000)


def text_block(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def thinking_block(thinking: str, *, signature: str | None = "reasoning_content") -> dict[str, Any]:
    block: dict[str, Any] = {"type": "thinking", "thinking": thinking}
    if signature:
        block["thinkingSignature"] = signature
    return block


def tool_call_block(*, tool_id: str, name: str, arguments: Any) -> dict[str, Any]:
    return {
        "type": "toolCall",
        "id": tool_id,
        "name": name,
        "arguments": arguments,
    }


def a2ui_block(*, surface_id: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "a2ui",
        "surfaceId": surface_id,
        "messages": messages,
    }


def event_id(event: dict[str, Any]) -> str:
    return str(event.get("id", ""))


def event_type(event: dict[str, Any]) -> str:
    return str(event.get("type", ""))


def message_role(event: dict[str, Any]) -> str | None:
    if event.get("type") != "message":
        return None
    msg = event.get("message")
    if not isinstance(msg, dict):
        return None
    role = msg.get("role")
    return str(role) if role else None


def message_text_content(event: dict[str, Any]) -> str:
    """Extract concatenated text blocks from a message event."""
    if event.get("type") != "message":
        return ""
    msg = event.get("message")
    if not isinstance(msg, dict):
        return ""
    content = msg.get("content")
    if not isinstance(content, list):
        if isinstance(content, str):
            return content
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts)


def last_event_id(events: list[dict[str, Any]]) -> str | None:
    if not events:
        return None
    last = events[-1]
    eid = last.get("id")
    return str(eid) if eid else None


def has_bootstrap(events: list[dict[str, Any]]) -> bool:
    return any(e.get("type") == "session" for e in events)
