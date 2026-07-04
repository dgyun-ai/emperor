"""Tests for OpenAI SSE conversion."""

from __future__ import annotations

import pytest

from agent.types import AgentEvent
from dashboard.openai_sse import agent_events_to_openai_sse, format_done, steer_queued_sse


async def _collect_sse(events):
    chunks = []
    async for chunk in agent_events_to_openai_sse(events):
        chunks.append(chunk)
    return chunks


async def _events_from_list(items):
    for item in items:
        yield item


@pytest.mark.asyncio
async def test_terminal_does_not_resend_streamed_content():
    events = _events_from_list(
        [
            AgentEvent("stream_delta", "Hello"),
            AgentEvent(
                "status",
                {"terminal": {"reason": "complete", "message": "Hello", "error": None}},
            ),
        ]
    )
    chunks = await _collect_sse(events)
    body = "".join(chunks)
    assert body.count('"content": "Hello"') == 1


@pytest.mark.asyncio
async def test_terminal_sends_content_when_not_streamed():
    events = _events_from_list(
        [
            AgentEvent(
                "status",
                {"terminal": {"reason": "complete", "message": "Hello", "error": None}},
            ),
        ]
    )
    chunks = await _collect_sse(events)
    body = "".join(chunks)
    assert '"content": "Hello"' in body


@pytest.mark.asyncio
async def test_stream_delta_to_chunk():
    events = _events_from_list(
        [
            AgentEvent("stream_delta", "Hello"),
            AgentEvent(
                "status",
                {"terminal": {"reason": "complete", "message": "Hello", "error": None}},
            ),
        ]
    )
    chunks = await _collect_sse(events)
    body = "".join(chunks)
    assert "chat.completion.chunk" in body
    assert "Hello" in body
    assert format_done().strip() in body


@pytest.mark.asyncio
async def test_usage_update_includes_full_snapshot():
    snapshot = {
        "turn": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        "session": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        "context": {"used_tokens": 82, "max_tokens": 128000, "percent": 0.1},
    }
    events = _events_from_list(
        [
            AgentEvent("usage_update", snapshot),
            AgentEvent(
                "status",
                {"terminal": {"reason": "complete", "message": "done", "error": None}},
            ),
        ]
    )
    chunks = await _collect_sse(events)
    body = "".join(chunks)
    assert '"usage_snapshot"' in body
    assert '"max_tokens": 128000' in body


@pytest.mark.asyncio
async def test_usage_update_in_stream():
    events = _events_from_list(
        [
            AgentEvent(
                "usage_update",
                {
                    "turn": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                    "session": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                    "context": {"used_tokens": 100, "max_tokens": 1000, "percent": 10},
                },
            ),
            AgentEvent(
                "status",
                {"terminal": {"reason": "complete", "message": "done", "error": None}},
            ),
        ]
    )
    chunks = await _collect_sse(events)
    body = "".join(chunks)
    assert '"prompt_tokens": 10' in body


@pytest.mark.asyncio
async def test_message_after_tool_turn_emitted_when_not_streamed():
    events = _events_from_list(
        [
            AgentEvent("stream_delta", "searching"),
            AgentEvent(
                "message",
                {
                    "role": "assistant",
                    "content": "searching",
                    "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "web_search"}}],
                },
            ),
            AgentEvent("tool_start", {"name": "web_search", "input": {"q": "shenzhen"}}),
            AgentEvent("tool_end", {"name": "web_search", "result": "ok"}),
            AgentEvent("message", {"role": "assistant", "content": "深圳必去景点：世界之窗"}),
            AgentEvent(
                "status",
                {
                    "terminal": {
                        "reason": "complete",
                        "message": "深圳必去景点：世界之窗",
                        "error": None,
                    }
                },
            ),
        ]
    )
    chunks = await _collect_sse(events)
    body = "".join(chunks)
    assert body.count("深圳必去景点") >= 1
    assert body.count('"content": "searching"') == 1


def test_steer_queued_sse():
    chunks = steer_queued_sse("next message")
    body = "".join(chunks)
    assert "emperor.event" in body
    assert "steer_queued" in body
    assert "[DONE]" in body


@pytest.mark.asyncio
async def test_ask_user_questions_before_terminal_and_done():
    events = _events_from_list(
        [
            AgentEvent("stream_delta", "Hello"),
            AgentEvent(
                "ask_user_questions",
                {"questions": ["Tell me more", "What else?"]},
            ),
            AgentEvent(
                "status",
                {"terminal": {"reason": "complete", "message": "Hello", "error": None}},
            ),
        ]
    )
    chunks = await _collect_sse(events)
    body = "".join(chunks)
    ask_idx = body.find("ask_user_questions")
    stop_idx = body.find('"finish_reason": "stop"')
    done_idx = body.find("[DONE]")
    assert ask_idx >= 0
    assert '"questions"' in body
    assert "Tell me more" in body
    assert stop_idx > ask_idx
    assert done_idx > stop_idx


@pytest.mark.asyncio
async def test_a2ui_event_before_terminal():
    messages = [
        {
            "version": "v0.9",
            "createSurface": {
                "surfaceId": "turn-main",
                "catalogId": "https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json",
            },
        }
    ]
    events = _events_from_list(
        [
            AgentEvent("a2ui", {"messages": messages}),
            AgentEvent(
                "status",
                {"terminal": {"reason": "complete", "message": "done", "error": None}},
            ),
        ]
    )
    chunks = await _collect_sse(events)
    body = "".join(chunks)
    assert '"type": "a2ui"' in body
    assert "turn-main" in body
    assert "[DONE]" in body
