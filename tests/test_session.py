"""Tests for session store."""

from __future__ import annotations

import json

import pytest

from session.convert import events_to_openai_messages
from session.events import message_role, message_text_content
from session.store import SessionStore


@pytest.fixture
async def store(tmp_path):
    s = SessionStore(tmp_path / "state.db")
    await s.initialize()
    return s


@pytest.mark.asyncio
async def test_create_and_append_messages(store):
    sid = await store.create_session(profile="test", title="Test")
    await store.append_message(sid, {"role": "user", "content": "hello"})
    await store.append_message(sid, {"role": "assistant", "content": "hi"})
    events = await store.load_events(sid)
    assert len(events) == 2
    assert message_role(events[0]) == "user"
    messages = events_to_openai_messages(events)
    assert messages[0]["content"] == "hello"


@pytest.mark.asyncio
async def test_list_sessions(store):
    await store.create_session(profile="test")
    sessions = await store.list_sessions(profile="test")
    assert len(sessions) >= 1


@pytest.mark.asyncio
async def test_search_messages(store):
    sid = await store.create_session(profile="test")
    await store.append_message(sid, {"role": "user", "content": "unique_search_token_xyz"})
    results = await store.search_messages("unique_search_token_xyz")
    assert len(results) >= 1


@pytest.mark.asyncio
async def test_export_jsonl(store):
    sid = await store.create_session(profile="test")
    await store.append_message(sid, {"role": "user", "content": "export me"})
    data = await store.export_jsonl(sid)
    line = json.loads(data.strip())
    assert line["type"] == "message"
    assert message_text_content(line) == "export me"


@pytest.mark.asyncio
async def test_compress_event(store):
    sid = await store.create_session(profile="test")
    eid = await store.record_compress_event(sid, child_session_id=None, summary="test", protected_last_n=20)
    assert eid
