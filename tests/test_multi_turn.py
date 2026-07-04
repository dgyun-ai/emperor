"""Multi-turn conversation persistence tests."""

from __future__ import annotations

import pytest

from agent.deps import AgentDeps
from engine.query_engine import QueryEngine
from helpers import TEST_CONFIG, make_sequential_mock, mock_text_response
from provider.openai_compat import ModelResponse
from session.convert import events_to_openai_messages
from session.store import SessionStore


async def _mock_stream_empty_assistant_content(text: str):
    for char in text:
        yield ModelResponse(delta_text=char)
    yield ModelResponse(
        is_final=True,
        finish_reason="stop",
        assistant_message={"role": "assistant", "content": None},
    )


@pytest.mark.asyncio
async def test_multi_turn_preserves_streamed_assistant_content(tmp_path):
    store = SessionStore(tmp_path / "state.db")
    call_model = make_sequential_mock(
        [
            lambda: _mock_stream_empty_assistant_content("First reply"),
            lambda: mock_text_response("You said hi"),
        ]
    )
    engine = QueryEngine(
        deps=AgentDeps.with_call_model(call_model),
        session_store=store,
        config=TEST_CONFIG,
        max_turns=5,
    )
    await engine.chat("hi")
    assert engine.messages[-1]["content"] == "First reply"
    await engine.chat("again")
    assert len(engine.messages) == 4
    assert engine.messages[-1]["content"] == "You said hi"
    db_events = await store.load_events(engine.session_id)  # type: ignore[arg-type]
    db_messages = events_to_openai_messages(db_events)
    assert db_messages[1]["content"] == "First reply"


@pytest.mark.asyncio
async def test_auto_resume_loads_history(tmp_path):
    store = SessionStore(tmp_path / "state.db")
    call_model = make_sequential_mock([lambda: mock_text_response("ok")])
    engine = QueryEngine(
        deps=AgentDeps.with_call_model(call_model),
        session_store=store,
        config=TEST_CONFIG,
        max_turns=5,
    )
    await engine.chat("hello")
    sid = engine.session_id

    engine2 = QueryEngine(
        deps=AgentDeps.with_call_model(
            make_sequential_mock([lambda: mock_text_response("followed")])
        ),
        session_store=store,
        config=TEST_CONFIG,
        max_turns=5,
    )
    await engine2.resume_session(sid)  # type: ignore[arg-type]
    assert len(engine2.messages) == 2
    await engine2.chat("follow up")
    assert len(engine2.messages) == 4


@pytest.mark.asyncio
async def test_failed_turn_persists_assistant_error_and_allows_next_turn(tmp_path):
    store = SessionStore(tmp_path / "state.db")

    async def fail_once():
        raise RuntimeError("boom")
        yield  # pragma: no cover

    call_model = make_sequential_mock(
        [
            fail_once,
            lambda: mock_text_response("recovered"),
        ]
    )
    engine = QueryEngine(
        deps=AgentDeps.with_call_model(call_model),
        session_store=store,
        config=TEST_CONFIG,
        max_turns=5,
    )

    first_events = [event async for event in engine.submit_message("first")]
    first_terminal = next(e.payload["terminal"] for e in first_events if e.kind == "status")
    assert first_terminal["reason"] == "error"
    assert first_terminal["error"] == "boom"
    assert engine.messages == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "boom"},
    ]

    result = await engine.chat("second")
    assert result == "recovered"
    assert engine.messages[-2:] == [
        {"role": "user", "content": "second"},
        {"role": "assistant", "content": "recovered"},
    ]

    db_events = await store.load_events(engine.session_id)  # type: ignore[arg-type]
    db_messages = events_to_openai_messages(db_events)
    assert db_messages == engine.messages
