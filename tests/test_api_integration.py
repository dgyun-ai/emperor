"""Tests for API, fallback, query engine integration."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent.deps import AgentDeps
from api.server import create_api_app
from config.models import EmperorConfig, FallbackProviderConfig
from engine.query_engine import QueryEngine
from helpers import TEST_CONFIG, make_sequential_mock, mock_text_response
from provider.fallback import FallbackProvider
from provider.openai_compat import OpenAICompatProvider
from session.convert import events_to_openai_messages
from session.store import SessionStore


@pytest.mark.asyncio
async def test_query_engine_with_session(tmp_path):
    store = SessionStore(tmp_path / "state.db")
    call_model = make_sequential_mock([lambda: mock_text_response("Saved.")])
    engine = QueryEngine(
        deps=AgentDeps.with_call_model(call_model),
        session_store=store,
        config=TEST_CONFIG,
        tools=[],
        max_turns=5,
    )
    text = await engine.chat("hello")
    assert text == "Saved."
    assert engine.session_id is not None
    events = await store.load_events(engine.session_id)
    messages = events_to_openai_messages(events)
    assert len(messages) >= 2


def test_api_server_chat_stream():
    call_model = make_sequential_mock([lambda: mock_text_response("Stream reply")])

    def factory():
        return QueryEngine(
            deps=AgentDeps.with_call_model(call_model),
            tools=[],
            max_turns=5,
            config=TEST_CONFIG,
        )

    app = create_api_app(factory)
    client = TestClient(app)
    with client.stream(
        "POST",
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}], "stream": True},
    ) as resp:
        assert resp.status_code == 200
        body = "".join(resp.iter_text())
        assert "chat.completion.chunk" in body
        assert "[DONE]" in body


def test_api_server_chat():
    call_model = make_sequential_mock([lambda: mock_text_response("API reply")])

    def factory():
        return QueryEngine(
            deps=AgentDeps.with_call_model(call_model),
            tools=[],
            max_turns=5,
            config=TEST_CONFIG,
        )

    app = create_api_app(factory)
    client = TestClient(app)
    resp = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 200
    assert "API reply" in resp.json()["choices"][0]["message"]["content"]


def test_fallback_provider_from_config():
    config = EmperorConfig(
        fallback_providers=[FallbackProviderConfig(provider="openai", model="gpt-4o", api_key="sk-test")]
    )
    primary = OpenAICompatProvider(api_key="sk-primary", model="claude")
    fb = FallbackProvider.from_config(config, primary)
    assert len(fb.fallbacks) == 1


@pytest.mark.asyncio
async def test_orchestrator_concurrent_execution():
    from provider.openai_compat import ToolCall
    from tools.orchestrator import execute_partitioned
    from tools.registry import get_tool

    import tools.builtin  # noqa: F401

    echo = get_tool("echo")
    order = []

    async def execute_fn(tc, ctx):
        order.append(tc.id)
        result = await echo.call(tc.arguments, ctx)
        return result, []

    ctx = __import__("context.tool_context", fromlist=["ToolContext"]).ToolContext(messages=[])
    calls = [
        ToolCall(id="a", name="echo", arguments={"message": "1"}),
        ToolCall(id="b", name="echo", arguments={"message": "2"}),
    ]
    results = await execute_partitioned(calls, ctx, {"echo": echo}, execute_fn)
    assert len(results) == 2
