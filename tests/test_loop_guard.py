"""Tests for tool failure guard and recovery."""

from __future__ import annotations

import pytest

from agent.deps import AgentDeps
from agent.loop import AgentLoop
from agent.loop_guard import ToolFailureGuard, format_failure_guidance
from config.models import AgentConfig, EmperorConfig
from engine.query_engine import QueryEngine
from helpers import make_sequential_mock, mock_text_response, mock_tool_then_text
from session.convert import events_to_openai_messages, openai_message_to_event
from tools.base import ToolResult, build_tool


async def _always_fail(_input: dict, _ctx) -> ToolResult:
    return ToolResult(content="failed", is_error=True)


async def _always_fail_a2ui(_input: dict, _ctx) -> ToolResult:
    return ToolResult(
        content='{"ok": false, "error": "messages must be a non-empty array"}',
        is_error=True,
    )


FAILING_TOOL = build_tool(
    name="fail_tool",
    description="Always fails",
    input_schema={"type": "object", "properties": {}},
    call_fn=_always_fail,
)

A2UI_FAILING_TOOL = build_tool(
    name="render_a2ui",
    description="Always fails with a non-recoverable schema error",
    input_schema={"type": "object", "properties": {"messages": {"type": "array"}}},
    call_fn=_always_fail_a2ui,
)


def test_failure_guard_allows_below_max():
    guard = ToolFailureGuard(max_failures=3)
    for _ in range(2):
        guard.record("web_search", success=False)
    hit, tool_name, guidance = guard.exceeded()
    assert hit is False
    assert tool_name is None
    assert guidance is None
    assert guard.failure_count("web_search") == 2


def test_failure_guard_success_resets_streak():
    guard = ToolFailureGuard(max_failures=3)
    guard.record("web_search", success=False)
    guard.record("web_search", success=False)
    guard.record("web_search", success=True)
    guard.record("web_search", success=False)
    guard.record("web_search", success=False)
    hit, _, _ = guard.exceeded()
    assert hit is False
    assert guard.failure_count("web_search") == 2


def test_failure_guard_triggers_after_consecutive_failures():
    guard = ToolFailureGuard(max_failures=3)
    for _ in range(3):
        guard.record("web_search", success=False)
    hit, tool_name, guidance = guard.exceeded()
    assert hit is True
    assert tool_name == "web_search"
    assert guidance is not None
    assert "web_search" in guidance


def test_failure_guard_mark_blocked_prevents_repeat_trigger():
    guard = ToolFailureGuard(max_failures=3)
    for _ in range(3):
        guard.record("web_search", success=False)
    hit, tool_name, guidance = guard.exceeded()
    assert hit is True
    guard.mark_blocked(tool_name or "")
    hit, _, _ = guard.exceeded()
    assert hit is False


def test_failure_guard_disabled():
    guard = ToolFailureGuard(max_failures=3, enabled=False)
    for _ in range(10):
        guard.record("web_search", success=False)
    hit, _, _ = guard.exceeded()
    assert hit is False


def test_format_failure_guidance_zh():
    text = format_failure_guidance("web_extract", max_failures=3, language="zh")
    assert "web_extract" in text
    assert "3" in text
    assert "禁用" in text


@pytest.mark.asyncio
async def test_agent_loop_recovers_after_consecutive_failures():
    call_model = make_sequential_mock(
        [
            lambda: mock_tool_then_text("fail_tool", {}, "c1", ""),
            lambda: mock_tool_then_text("fail_tool", {}, "c2", ""),
            lambda: mock_tool_then_text("fail_tool", {}, "c3", ""),
            lambda: mock_text_response("Summary for the user."),
        ]
    )
    loop = AgentLoop(
        deps=AgentDeps.with_call_model(call_model),
        tools=[FAILING_TOOL],
        max_turns=20,
        max_consecutive_tool_failures=3,
        loop_guard_enabled=True,
    )
    events = []
    async for event in loop.run(messages=[{"role": "user", "content": "try tool"}]):
        events.append(event)

    terminal = next(e.payload["terminal"] for e in events if e.kind == "status")
    assert terminal["reason"] == "complete"
    assert terminal.get("message") == "Summary for the user."

    tool_starts = [e for e in events if e.kind == "tool_start"]
    assert len(tool_starts) == 3

    system_msgs = [
        e.payload
        for e in events
        if e.kind == "message" and e.payload.get("role") == "system"
    ]
    assert system_msgs
    assert "fail_tool" in system_msgs[0]["content"]


@pytest.mark.asyncio
async def test_query_engine_persists_summary_after_tool_failures(tmp_path, monkeypatch):
    monkeypatch.setenv("EMPEROR_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)

    call_model = make_sequential_mock(
        [
            lambda: mock_tool_then_text("fail_tool", {}, "c1", ""),
            lambda: mock_tool_then_text("fail_tool", {}, "c2", ""),
            lambda: mock_tool_then_text("fail_tool", {}, "c3", ""),
            lambda: mock_text_response("Recovered summary."),
        ]
    )
    config = EmperorConfig(agent=AgentConfig(auto_title=False, max_consecutive_tool_failures=3))
    engine = QueryEngine(
        deps=AgentDeps.with_call_model(call_model),
        tools=[FAILING_TOOL],
        config=config,
        profile="test",
        max_turns=20,
    )
    await engine.initialize()
    session_id = await engine.new_session()

    events = []
    async for event in engine.submit_message("fail repeatedly"):
        events.append(event)

    terminal = next(e.payload["terminal"] for e in events if e.kind == "status")
    assert terminal["reason"] == "complete"
    assert terminal.get("message") == "Recovered summary."

    events = await engine.session_store.load_events(session_id)
    messages = events_to_openai_messages(events)
    assistant_messages = [m for m in messages if m.get("role") == "assistant"]
    assert assistant_messages
    final = assistant_messages[-1]
    assert not final.get("tool_calls")
    assert "Recovered summary." in (final.get("content") or "")


@pytest.mark.asyncio
async def test_render_a2ui_is_immediately_blocked_after_schema_failure():
    call_model = make_sequential_mock(
        [
            lambda: mock_tool_then_text("render_a2ui", {"messages": []}, "c1", ""),
            lambda: mock_text_response("我先用文本说明这个登录表单。"),
        ]
    )
    loop = AgentLoop(
        deps=AgentDeps.with_call_model(call_model),
        tools=[A2UI_FAILING_TOOL],
        max_turns=10,
        max_consecutive_tool_failures=5,
        loop_guard_enabled=True,
    )

    events = []
    async for event in loop.run(messages=[{"role": "user", "content": "展示登录表单"}]):
        events.append(event)

    tool_starts = [e for e in events if e.kind == "tool_start"]
    assert len(tool_starts) == 1

    system_msgs = [
        e.payload["content"]
        for e in events
        if e.kind == "message" and e.payload.get("role") == "system"
    ]
    assert system_msgs
    assert "已立即禁用" in system_msgs[0]
    assert "render_a2ui" in system_msgs[0]

    terminal = next(e.payload["terminal"] for e in events if e.kind == "status")
    assert terminal["reason"] == "complete"
    assert "登录表单" in (terminal.get("message") or "")


@pytest.mark.asyncio
async def test_query_engine_history_strips_a2ui_payloads_for_model_context(tmp_path, monkeypatch):
    monkeypatch.setenv("EMPEROR_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)

    engine = QueryEngine(
        deps=AgentDeps.with_call_model(make_sequential_mock([lambda: mock_text_response("ok")])),
        config=EmperorConfig(),
        profile="test",
    )
    await engine.initialize()
    session_id = await engine.new_session()

    assistant_event = openai_message_to_event(
        {
            "role": "assistant",
            "content": "Here is the form.",
            "a2ui_messages": [
                {"createSurface": {"surfaceId": "login-form", "catalogId": "basic"}},
            ],
            "a2ui_surface_id": "login-form",
        },
        parent_id=None,
    )
    await engine.session_store.append_event(session_id, assistant_event)
    await engine._reload_session_history(session_id)

    assistant_messages = [m for m in engine.messages if m.get("role") == "assistant"]
    assert assistant_messages
    restored = assistant_messages[-1]
    assert restored.get("content") == "Here is the form."
    assert "a2ui_messages" not in restored
    assert "[A2UI surface" not in (restored.get("content") or "")
