"""Convert between OpenClaw session events and OpenAI chat messages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from session.events import (
    a2ui_block,
    epoch_ms,
    event_id,
    iso_timestamp,
    last_event_id,
    text_block,
    thinking_block,
    tool_call_block,
    _short_id,
)


def bootstrap_session_events(
    *,
    session_id: str,
    cwd: str | None = None,
    provider: str = "emperor",
    model_id: str = "default",
    thinking_level: str = "off",
    model_api: str = "openai-completions",
    now: float | None = None,
) -> list[dict[str, Any]]:
    """Build the initial openclaw event chain for a new session."""
    workdir = cwd or str(Path.cwd())
    ts = now
    session_event: dict[str, Any] = {
        "type": "session",
        "version": 3,
        "id": session_id,
        "timestamp": iso_timestamp(ts),
        "cwd": workdir,
    }
    model_change_id = _short_id()
    model_change: dict[str, Any] = {
        "type": "model_change",
        "id": model_change_id,
        "parentId": None,
        "timestamp": iso_timestamp(ts),
        "provider": provider,
        "modelId": model_id,
    }
    thinking_id = _short_id()
    thinking_change: dict[str, Any] = {
        "type": "thinking_level_change",
        "id": thinking_id,
        "parentId": model_change_id,
        "timestamp": iso_timestamp(ts),
        "thinkingLevel": thinking_level,
    }
    snapshot_id = _short_id()
    snapshot: dict[str, Any] = {
        "type": "custom",
        "customType": "model-snapshot",
        "data": {
            "timestamp": epoch_ms(ts),
            "provider": provider,
            "modelApi": model_api,
            "modelId": model_id,
        },
        "id": snapshot_id,
        "parentId": thinking_id,
        "timestamp": iso_timestamp(ts),
    }
    return [session_event, model_change, thinking_change, snapshot]


def build_model_change_events(
    *,
    parent_id: str | None,
    provider: str,
    model_id: str,
    thinking_level: str = "off",
    model_api: str = "openai-completions",
    now: float | None = None,
) -> list[dict[str, Any]]:
    ts = now
    model_change_id = _short_id()
    model_change: dict[str, Any] = {
        "type": "model_change",
        "id": model_change_id,
        "parentId": parent_id,
        "timestamp": iso_timestamp(ts),
        "provider": provider,
        "modelId": model_id,
    }
    thinking_id = _short_id()
    thinking_change: dict[str, Any] = {
        "type": "thinking_level_change",
        "id": thinking_id,
        "parentId": model_change_id,
        "timestamp": iso_timestamp(ts),
        "thinkingLevel": thinking_level,
    }
    snapshot_id = _short_id()
    snapshot: dict[str, Any] = {
        "type": "custom",
        "customType": "model-snapshot",
        "data": {
            "timestamp": epoch_ms(ts),
            "provider": provider,
            "modelApi": model_api,
            "modelId": model_id,
        },
        "id": snapshot_id,
        "parentId": thinking_id,
        "timestamp": iso_timestamp(ts),
    }
    return [model_change, thinking_change, snapshot]


def build_user_event(
    content: str,
    *,
    parent_id: str | None,
    now: float | None = None,
) -> dict[str, Any]:
    ts = now
    return {
        "type": "message",
        "id": _short_id(),
        "parentId": parent_id,
        "timestamp": iso_timestamp(ts),
        "message": {
            "role": "user",
            "content": [text_block(content)],
            "timestamp": epoch_ms(ts),
        },
    }


def build_system_event(
    content: str,
    *,
    parent_id: str | None,
    now: float | None = None,
) -> dict[str, Any]:
    ts = now
    return {
        "type": "message",
        "id": _short_id(),
        "parentId": parent_id,
        "timestamp": iso_timestamp(ts),
        "message": {
            "role": "system",
            "content": [text_block(content)],
            "timestamp": epoch_ms(ts),
        },
    }


def build_assistant_event(
    *,
    content_blocks: list[dict[str, Any]],
    parent_id: str | None,
    provider: str = "emperor",
    model: str = "default",
    api: str = "openai-completions",
    usage: dict[str, Any] | None = None,
    stop_reason: str = "stop",
    now: float | None = None,
) -> dict[str, Any]:
    ts = now
    message: dict[str, Any] = {
        "role": "assistant",
        "content": content_blocks,
        "api": api,
        "provider": provider,
        "model": model,
        "stopReason": stop_reason,
        "timestamp": epoch_ms(ts),
    }
    if usage:
        message["usage"] = usage
    return {
        "type": "message",
        "id": _short_id(),
        "parentId": parent_id,
        "timestamp": iso_timestamp(ts),
        "message": message,
    }


def build_tool_event(
    *,
    tool_call_id: str,
    content: str,
    parent_id: str | None,
    now: float | None = None,
) -> dict[str, Any]:
    ts = now
    return {
        "type": "message",
        "id": _short_id(),
        "parentId": parent_id,
        "timestamp": iso_timestamp(ts),
        "message": {
            "role": "tool",
            "toolCallId": tool_call_id,
            "content": [text_block(content)],
            "timestamp": epoch_ms(ts),
        },
    }


def openai_message_to_event(
    message: dict[str, Any],
    *,
    parent_id: str | None,
    provider: str = "emperor",
    model: str = "default",
    usage: dict[str, Any] | None = None,
    stop_reason: str = "stop",
    streamed_text: str = "",
    now: float | None = None,
) -> dict[str, Any]:
    """Convert an OpenAI-style message dict to an openclaw message event."""
    role = message.get("role", "assistant")
    if role == "system":
        content = message.get("content") or streamed_text or ""
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        return build_system_event(content, parent_id=parent_id, now=now)
    if role == "user":
        content = message.get("content") or streamed_text or ""
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        return build_user_event(content, parent_id=parent_id, now=now)

    if role == "tool":
        tool_call_id = str(message.get("tool_call_id") or "")
        content = message.get("content") or ""
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        return build_tool_event(
            tool_call_id=tool_call_id,
            content=content,
            parent_id=parent_id,
            now=now,
        )

    blocks: list[dict[str, Any]] = []
    thinking = message.get("_thinking")
    if isinstance(thinking, str) and thinking.strip():
        blocks.append(thinking_block(thinking))
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        blocks.append(text_block(content))
    elif streamed_text.strip() and not blocks:
        blocks.append(text_block(streamed_text))

    a2ui_messages = message.get("a2ui_messages")
    if isinstance(a2ui_messages, list) and a2ui_messages:
        surface_id = str(message.get("a2ui_surface_id") or "main")
        blocks.append(a2ui_block(surface_id=surface_id, messages=a2ui_messages))

    tool_calls = message.get("tool_calls") or []
    for tc in tool_calls:
        fn = tc.get("function") or {}
        raw_args = fn.get("arguments") or "{}"
        try:
            arguments = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        except json.JSONDecodeError:
            arguments = raw_args
        blocks.append(
            tool_call_block(
                tool_id=str(tc.get("id") or _short_id()),
                name=str(fn.get("name") or ""),
                arguments=arguments,
            )
        )

    if not blocks:
        blocks.append(text_block(""))

    return build_assistant_event(
        content_blocks=blocks,
        parent_id=parent_id,
        provider=provider,
        model=model,
        usage=usage,
        stop_reason=stop_reason,
        now=now,
    )


def _blocks_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
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


def _assistant_event_to_openai(msg: dict[str, Any]) -> dict[str, Any]:
    content = msg.get("content")
    text_parts: list[str] = []
    thinking_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    a2ui_messages: list[dict[str, Any]] = []
    a2ui_surface_id: str | None = None
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type == "text":
                text = block.get("text")
                if isinstance(text, str):
                    text_parts.append(text)
            elif block_type == "thinking":
                thinking = block.get("thinking")
                if isinstance(thinking, str):
                    thinking_parts.append(thinking)
            elif block_type == "toolCall":
                raw_args = block.get("arguments", {})
                if not isinstance(raw_args, str):
                    raw_args = json.dumps(raw_args, ensure_ascii=False)
                tool_calls.append(
                    {
                        "id": str(block.get("id") or _short_id()),
                        "type": "function",
                        "function": {
                            "name": str(block.get("name") or ""),
                            "arguments": raw_args,
                        },
                    }
                )
            elif block_type == "a2ui":
                messages_list = block.get("messages")
                if isinstance(messages_list, list):
                    a2ui_messages.extend(m for m in messages_list if isinstance(m, dict))
                surface_id = block.get("surfaceId")
                if isinstance(surface_id, str) and surface_id.strip():
                    a2ui_surface_id = surface_id.strip()
    openai_msg: dict[str, Any] = {"role": "assistant"}
    joined = "".join(text_parts)
    if joined:
        openai_msg["content"] = joined
    elif not tool_calls and not a2ui_messages:
        openai_msg["content"] = None
    joined_thinking = "".join(thinking_parts)
    if joined_thinking:
        openai_msg["_thinking"] = joined_thinking
    if tool_calls:
        openai_msg["tool_calls"] = tool_calls
        if "content" not in openai_msg:
            openai_msg["content"] = None
    if a2ui_messages:
        openai_msg["a2ui_messages"] = a2ui_messages
    if a2ui_surface_id:
        openai_msg["a2ui_surface_id"] = a2ui_surface_id
    return openai_msg


def normalize_message_history(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge consecutive user/assistant turns for AgentLoop validation and model input."""
    normalized: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        if normalized and normalized[-1].get("role") == role:
            if role == "assistant":
                normalized[-1] = _merge_consecutive_assistants(normalized[-1], message)
                continue
            if role == "user":
                normalized[-1] = _merge_consecutive_users(normalized[-1], message)
                continue
        normalized.append(message)
    return normalized


def _merge_consecutive_users(prev: dict[str, Any], cur: dict[str, Any]) -> dict[str, Any]:
    """Merge back-to-back user messages from interrupted or retried turns."""
    merged = dict(prev)
    prev_content = prev.get("content")
    cur_content = cur.get("content")
    prev_text = prev_content if isinstance(prev_content, str) else str(prev_content or "")
    cur_text = cur_content if isinstance(cur_content, str) else str(cur_content or "")
    if prev_text and cur_text:
        merged["content"] = f"{prev_text}\n\n{cur_text}"
    elif cur_text:
        merged["content"] = cur_text
    else:
        merged["content"] = prev_text
    return merged


def _merge_consecutive_assistants(
    prev: dict[str, Any], cur: dict[str, Any]
) -> dict[str, Any]:
    """Merge two back-to-back assistant messages (e.g. a2ui-only follow-up)."""
    merged = dict(prev)
    prev_content = prev.get("content")
    cur_content = cur.get("content")
    if isinstance(cur_content, str) and cur_content.strip():
        if isinstance(prev_content, str) and prev_content.strip():
            merged["content"] = prev_content + cur_content
        else:
            merged["content"] = cur_content
    if cur.get("tool_calls") and not merged.get("tool_calls"):
        merged["tool_calls"] = cur["tool_calls"]
        if "content" not in merged or merged.get("content") is None:
            merged["content"] = None
    prev_a2ui = list(merged.get("a2ui_messages") or [])
    cur_a2ui = list(cur.get("a2ui_messages") or [])
    if cur_a2ui:
        prev_a2ui.extend(cur_a2ui)
        merged["a2ui_messages"] = prev_a2ui
    if cur.get("a2ui_surface_id") and not merged.get("a2ui_surface_id"):
        merged["a2ui_surface_id"] = cur["a2ui_surface_id"]
    return merged


def _strip_a2ui_fields(message: dict[str, Any]) -> dict[str, Any]:
    if message.get("role") != "assistant":
        return message
    if "a2ui_messages" not in message and "a2ui_surface_id" not in message:
        return message
    stripped = dict(message)
    stripped.pop("a2ui_messages", None)
    stripped.pop("a2ui_surface_id", None)
    return stripped


def _summarize_a2ui_fields(message: dict[str, Any]) -> dict[str, Any]:
    if message.get("role") != "assistant":
        return message
    if "a2ui_messages" not in message:
        return message
    from emperor_a2ui.summary import append_a2ui_summary_to_message

    return append_a2ui_summary_to_message(message)


def events_to_openai_messages(
    events: list[dict[str, Any]],
    *,
    strip_a2ui: bool = False,
    a2ui_summary: bool = False,
) -> list[dict[str, Any]]:
    """Convert openclaw events to OpenAI chat messages for AgentLoop."""
    messages: list[dict[str, Any]] = []
    for event in events:
        if event.get("type") != "message":
            continue
        msg = event.get("message")
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        if role == "system":
            text = _blocks_to_text(msg.get("content"))
            messages.append({"role": "system", "content": text})
        elif role == "user":
            text = _blocks_to_text(msg.get("content"))
            messages.append({"role": "user", "content": text})
        elif role == "assistant":
            openai_msg = _assistant_event_to_openai(msg)
            if messages and messages[-1].get("role") == "assistant":
                messages[-1] = _merge_consecutive_assistants(messages[-1], openai_msg)
            else:
                messages.append(openai_msg)
        elif role == "tool":
            text = _blocks_to_text(msg.get("content"))
            tool_call_id = msg.get("toolCallId") or msg.get("tool_call_id") or ""
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": text,
                }
            )
    if a2ui_summary:
        messages = [_summarize_a2ui_fields(m) for m in messages]
    elif strip_a2ui:
        messages = [_strip_a2ui_fields(m) for m in messages]
    return messages


def parent_for_next_event(events: list[dict[str, Any]]) -> str | None:
    return last_event_id(events) or event_id(events[-1]) if events else None
