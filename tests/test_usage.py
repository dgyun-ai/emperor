"""Tests for token usage tracking."""

from __future__ import annotations

import pytest

from agent.deps import AgentDeps
from agent.loop import AgentLoop
from context.usage import (
    UsageTracker,
    build_history_usage_snapshot,
    build_usage_snapshot,
    estimate_context_tokens,
    restore_tracker_from_snapshot,
)
from engine.query_engine import QueryEngine
from helpers import mock_text_response


@pytest.mark.asyncio
async def test_usage_tracker_accumulates():
    tracker = UsageTracker()
    tracker.record_turn(100, 50)
    tracker.record_turn(80, 20)
    assert tracker.session_prompt_tokens == 180
    assert tracker.session_completion_tokens == 70
    assert tracker.session_total_tokens == 250
    assert tracker.last_turn.prompt_tokens == 80


def test_build_usage_snapshot_percent():
    tracker = UsageTracker()
    tracker.record_turn(1000, 500)
    snap = build_usage_snapshot(tracker, context_tokens=32_000, max_context_tokens=128_000)
    assert snap["context"]["percent"] == 25.0
    assert snap["turn"]["total_tokens"] == 1500


def test_build_history_usage_snapshot_from_messages():
    messages = [{"role": "user", "content": "hello" * 50}]
    snap = build_history_usage_snapshot(
        messages,
        system_prompt="system",
        max_context_tokens=128_000,
    )
    assert snap["context"]["used_tokens"] > 0
    assert snap["context"]["max_tokens"] == 128_000
    assert snap["session"]["total_tokens"] == 0


def test_restore_tracker_from_snapshot():
    stored = {
        "turn": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        "session": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        "context": {"used_tokens": 500, "max_tokens": 128_000, "percent": 0.4},
    }
    tracker = restore_tracker_from_snapshot(stored)
    assert tracker.session_total_tokens == 150
    assert tracker.last_turn.prompt_tokens == 10


def test_estimate_context_tokens_includes_system():
    messages = [{"role": "user", "content": "hello" * 100}]
    with_system = estimate_context_tokens(messages, system_prompt="system prompt")
    without = estimate_context_tokens(messages, system_prompt="")
    assert with_system > without


@pytest.mark.asyncio
async def test_agent_loop_emits_usage_update():
    async def call_model(**kwargs):
        async for chunk in mock_text_response("hi"):
            yield chunk

    loop = AgentLoop(
        deps=AgentDeps.with_call_model(call_model),
        tools=[],
        max_context_tokens=10_000,
    )
    events = []
    async for event in loop.run(messages=[{"role": "user", "content": "hello"}]):
        events.append(event)

    usage_events = [e for e in events if e.kind == "usage_update"]
    assert len(usage_events) == 1
    snap = usage_events[0].payload
    assert snap["turn"]["completion_tokens"] > 0
    assert snap["context"]["max_tokens"] == 10_000


@pytest.mark.asyncio
async def test_query_engine_current_usage_snapshot():
    engine = QueryEngine(
        deps=AgentDeps.with_call_model(mock_text_response("ok")),
        profile="test",
    )
    await engine.initialize()
    snap = engine.current_usage_snapshot()
    assert snap["context"]["max_tokens"] == engine.max_context_tokens
