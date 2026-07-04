from __future__ import annotations

import asyncio
import json

from agent.types import AgentEvent
from dashboard.ag_ui_mapper import agent_events_to_ag_ui_sse, openai_messages_to_ag_ui_snapshot


def _decode_sse(chunk: str) -> dict:
    payload = chunk.removeprefix("data: ").strip()
    return json.loads(payload)


async def _collect(events: list[AgentEvent]) -> list[dict]:
    async def gen():
        for event in events:
            yield event

    chunks: list[dict] = []
    async for chunk in agent_events_to_ag_ui_sse(gen(), thread_id="thread-1", run_id="run-1"):
        chunks.append(_decode_sse(chunk))
    return chunks


def test_thinking_events_are_wrapped_with_step_lifecycle():
    chunks = asyncio.run(
        _collect(
            [
                AgentEvent("thinking", {"text": "analyzing"}),
                AgentEvent("stream_delta", {"text": "done"}),
            ]
        )
    )

    event_types = [chunk["type"] for chunk in chunks]
    assert event_types == [
        "RUN_STARTED",
        "REASONING_START",
        "REASONING_MESSAGE_START",
        "REASONING_MESSAGE_CONTENT",
        "REASONING_MESSAGE_END",
        "REASONING_END",
        "TEXT_MESSAGE_START",
        "TEXT_MESSAGE_CONTENT",
        "TEXT_MESSAGE_END",
        "RUN_FINISHED",
    ]


def test_a2ui_events_emit_activity_snapshot():
    chunks = asyncio.run(
        _collect(
            [
                AgentEvent(
                    "a2ui",
                    {
                        "messages": [
                            {
                                "createSurface": {
                                    "surfaceId": "login-form",
                                    "catalogId": (
                                        "https://a2ui.org/specification/v0_9/"
                                        "catalogs/basic/catalog.json"
                                    ),
                                }
                            }
                        ]
                    },
                ),
            ]
        )
    )

    assert chunks[1]["type"] == "ACTIVITY_SNAPSHOT"
    assert chunks[1]["activityType"] == "a2ui-surface"
    assert chunks[1]["content"]["a2ui_operations"][0]["createSurface"]["catalogId"] == (
        "https://a2ui.org/specification/v0_9/basic_catalog.json"
    )
    assert chunks[2] == {
        "type": "CUSTOM",
        "name": "a2ui",
        "value": {
            "messages": [
                {
                    "createSurface": {
                        "surfaceId": "login-form",
                        "catalogId": (
                            "https://a2ui.org/specification/v0_9/basic_catalog.json"
                        ),
                    }
                }
            ]
        },
    }


def test_tool_events_emit_result_after_tool_call_end():
    chunks = asyncio.run(
        _collect(
            [
                AgentEvent("tool_start", {"name": "terminal_run", "input": {"command": "date"}}),
                AgentEvent(
                    "tool_end",
                    {
                        "name": "terminal_run",
                        "result": '{"stdout":"Tue Jul 1","stderr":"","returncode":0}',
                    },
                ),
            ]
        )
    )

    event_types = [chunk["type"] for chunk in chunks]
    assert event_types == [
        "RUN_STARTED",
        "TOOL_CALL_START",
        "TOOL_CALL_ARGS",
        "TOOL_CALL_END",
        "TOOL_CALL_RESULT",
        "RUN_FINISHED",
    ]
    assert chunks[4]["role"] == "tool"
    assert chunks[4]["content"] == '{"stdout":"Tue Jul 1","stderr":"","returncode":0}'


def test_snapshot_preserves_a2ui_activity_messages():
    snapshot = openai_messages_to_ag_ui_snapshot(
        [
            {
                "role": "assistant",
                "content": "Here is the form.",
                "a2ui_messages": [
                    {"createSurface": {"surfaceId": "login-form", "catalogId": "basic"}},
                    {"updateComponents": {"surfaceId": "login-form", "components": []}},
                ],
            }
        ]
    )

    assert len(snapshot) == 2
    assert snapshot[0]["role"] == "assistant"
    assert snapshot[0]["content"] == "Here is the form."
    assert snapshot[1]["role"] == "activity"
    assert snapshot[1]["activityType"] == "a2ui-surface"
    assert snapshot[1]["content"]["a2ui_operations"] == [
        {
            "createSurface": {
                "surfaceId": "login-form",
                "catalogId": "https://a2ui.org/specification/v0_9/basic_catalog.json",
            }
        },
        {"updateComponents": {"surfaceId": "login-form", "components": []}},
    ]


def test_snapshot_preserves_reasoning_messages():
    snapshot = openai_messages_to_ag_ui_snapshot(
        [
            {
                "role": "assistant",
                "_thinking": "step by step",
                "content": "final answer",
            }
        ]
    )

    assert len(snapshot) == 2
    assert snapshot[0]["role"] == "reasoning"
    assert snapshot[0]["content"] == "step by step"
    assert snapshot[1]["role"] == "assistant"
    assert snapshot[1]["content"] == "final answer"
