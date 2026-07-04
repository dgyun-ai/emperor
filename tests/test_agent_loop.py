"""Integration tests for AgentLoop and QueryEngine."""

from __future__ import annotations

import asyncio
import json

import pytest

from agent.deps import AgentDeps
from agent.loop import AgentLoop, MessageValidationError, validate_messages
from agent.budget import IterationBudget
from engine.query_engine import QueryEngine
from provider.openai_compat import ModelResponse, ToolCall
from helpers import TEST_CONFIG, make_sequential_mock, mock_text_response, mock_tool_then_text
from tools.base import ToolResult, build_tool
from tools.registry import get_tool


@pytest.mark.asyncio
async def test_pure_conversation_mock_llm():
    call_model = make_sequential_mock([lambda: mock_text_response("Hello!")])
    loop = AgentLoop(deps=AgentDeps.with_call_model(call_model), max_turns=5)

    events = []
    async for event in loop.run(messages=[{"role": "user", "content": "Hi"}]):
        events.append(event)

    deltas = [e.payload for e in events if e.kind == "stream_delta"]
    assert "".join(deltas) == "Hello!"
    terminal = next(e.payload["terminal"] for e in events if e.kind == "status")
    assert terminal["reason"] == "complete"
    assert terminal["message"] == "Hello!"


@pytest.mark.asyncio
async def test_query_engine_chat_wrapper():
    call_model = make_sequential_mock([lambda: mock_text_response("Done.")])
    engine = QueryEngine(deps=AgentDeps.with_call_model(call_model), max_turns=5, config=TEST_CONFIG)
    result = await engine.chat("test")
    assert result == "Done."


@pytest.mark.asyncio
async def test_tool_call_loop():
    echo = get_tool("echo")
    assert echo is not None

    call_model = make_sequential_mock(
        [
            lambda: mock_tool_then_text("echo", {"message": "ping"}, "call_1", ""),
            lambda: mock_text_response("Echo says ping"),
        ]
    )
    loop = AgentLoop(
        deps=AgentDeps.with_call_model(call_model),
        tools=[echo],
        max_turns=5,
    )

    events = []
    async for event in loop.run(messages=[{"role": "user", "content": "echo ping"}]):
        events.append(event)

    kinds = [e.kind for e in events]
    assert "tool_start" in kinds
    assert "tool_end" in kinds
    terminal = next(e.payload["terminal"] for e in events if e.kind == "status")
    assert terminal["reason"] == "complete"


@pytest.mark.asyncio
async def test_tool_context_updates_drive_same_turn_and_next_turn_loop():
    async def set_flag(input: dict, ctx) -> ToolResult:
        return ToolResult(
            content=json.dumps({"set": input["value"]}),
            context_patch={"flag": input["value"]},
            system_messages=[f"Loop state flag={input['value']}"],
        )

    async def read_flag(input: dict, ctx) -> ToolResult:
        return ToolResult(content=json.dumps({"flag": ctx.extra.get("flag")}))

    set_flag_tool = build_tool(
        name="set_flag",
        description="set loop state flag",
        input_schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        },
        call_fn=set_flag,
    )
    read_flag_tool = build_tool(
        name="read_flag",
        description="read loop state flag",
        input_schema={"type": "object", "properties": {}},
        call_fn=read_flag,
    )

    async def first_turn():
        yield ModelResponse(
            is_final=True,
            finish_reason="tool_calls",
            tool_calls=[
                ToolCall(id="c1", name="set_flag", arguments={"value": "ready"}),
                ToolCall(id="c2", name="read_flag", arguments={}),
            ],
            assistant_message={
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "set_flag", "arguments": json.dumps({"value": "ready"})},
                    },
                    {
                        "id": "c2",
                        "type": "function",
                        "function": {"name": "read_flag", "arguments": json.dumps({})},
                    },
                ],
            },
        )

    seen_second_turn_messages: list[dict[str, object]] = []

    async def second_turn():
        for message in seen_second_turn_messages:
            if message.get("role") == "system" and message.get("content") == "Loop state flag=ready":
                break
        else:
            raise AssertionError("expected loop state system message before second model call")
        async for chunk in mock_text_response("loop ok"):
            yield chunk

    call_index = 0

    async def call_model(
        *,
        messages: list[dict[str, object]],
        tools=None,
        abort_event=None,
        extra_body=None,
        disable_thinking=False,
    ):
        nonlocal call_index, seen_second_turn_messages
        if call_index == 0:
            call_index += 1
            async for chunk in first_turn():
                yield chunk
            return
        seen_second_turn_messages = list(messages)
        call_index += 1
        async for chunk in second_turn():
            yield chunk

    loop = AgentLoop(
        deps=AgentDeps.with_call_model(call_model),
        tools=[set_flag_tool, read_flag_tool],
        max_turns=5,
    )

    events = []
    async for event in loop.run(messages=[{"role": "user", "content": "run loop"}]):
        events.append(event)

    tool_messages = [e.payload for e in events if e.kind == "message" and e.payload.get("role") == "tool"]
    read_flag_message = next(msg for msg in tool_messages if msg["tool_call_id"] == "c2")
    assert json.loads(read_flag_message["content"]) == {"flag": "ready"}
    terminal = next(e.payload["terminal"] for e in events if e.kind == "status")
    assert terminal["reason"] == "complete"
    assert terminal["message"] == "loop ok"


@pytest.mark.asyncio
async def test_abort_during_loop():
    abort = asyncio.Event()
    abort.set()

    call_model = make_sequential_mock([lambda: mock_text_response("never")])
    loop = AgentLoop(deps=AgentDeps.with_call_model(call_model), max_turns=5)
    events = []
    async for event in loop.run(
        messages=[{"role": "user", "content": "go"}],
        abort_event=abort,
    ):
        events.append(event)

    terminal = next(e.payload["terminal"] for e in events if e.kind == "status")
    assert terminal["reason"] == "aborted"


@pytest.mark.asyncio
async def test_max_turns_truncation():
    async def always_tool(**kwargs):
        async for chunk in mock_tool_then_text("echo", {"message": "x"}, "c1", ""):
            yield chunk

    loop = AgentLoop(
        deps=AgentDeps.with_call_model(always_tool),
        tools=[get_tool("echo")],
        max_turns=2,
    )
    events = []
    async for event in loop.run(messages=[{"role": "user", "content": "loop"}]):
        events.append(event)

    terminal = next(e.payload["terminal"] for e in events if e.kind == "status")
    assert terminal["reason"] == "max_iterations"


def test_iteration_budget_exhausted():
    budget = IterationBudget(2)
    budget.consume()
    budget.consume()
    assert budget.exhausted
    assert budget.remaining == 0


def test_message_validation_first_must_be_user():
    with pytest.raises(MessageValidationError, match="First message"):
        validate_messages([{"role": "assistant", "content": "hi"}])


def test_message_validation_user_assistant_alternation():
    validate_messages(
        [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
    )


def test_message_validation_tool_chain():
    validate_messages(
        [
            {"role": "user", "content": "go"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "t1", "type": "function", "function": {"name": "echo"}}],
            },
            {"role": "tool", "tool_call_id": "t1", "content": "{}"},
            {"role": "assistant", "content": "done"},
        ]
    )


def test_message_validation_rejects_consecutive_assistants():
    with pytest.raises(MessageValidationError, match="Unexpected assistant message"):
        validate_messages(
            [
                {"role": "user", "content": "go"},
                {"role": "assistant", "content": "first"},
                {"role": "assistant", "content": "second"},
            ]
        )


def test_message_validation_allows_system_between_assistant_turns():
    validate_messages(
        [
            {"role": "user", "content": "go"},
            {"role": "assistant", "content": "calling tool"},
            {"role": "system", "content": "Tool disabled after repeated failures."},
            {"role": "assistant", "content": "done without tool"},
        ]
    )


def test_message_validation_allows_leading_system_messages():
    validate_messages(
        [
            {"role": "system", "content": "bootstrap"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
    )


def test_message_validation_unknown_tool_call_id():
    with pytest.raises(MessageValidationError, match="Unknown tool_call_id"):
        validate_messages(
            [
                {"role": "user", "content": "go"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{"id": "t1", "type": "function", "function": {"name": "echo"}}],
                },
                {"role": "tool", "tool_call_id": "missing", "content": "{}"},
            ]
        )


@pytest.mark.asyncio
async def test_echo_tool_direct():
    echo = get_tool("echo")
    assert echo is not None
    from context.tool_context import ToolContext

    result = await echo.call({"message": "test"}, ToolContext(messages=[]))
    assert json.loads(result.content) == {"echo": "test"}
