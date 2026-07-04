"""Tests for session local timestamps and title backfill."""

from __future__ import annotations

from datetime import datetime

import pytest

from agent.deps import AgentDeps
from engine.query_engine import QueryEngine
from helpers import make_sequential_mock, mock_text_response
from session.store import SessionStore
from session.time_util import format_local_timestamp, format_session_age, session_to_dict


def test_format_local_timestamp_matches_datetime():
    ts = 1_700_000_000.0
    expected = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    assert format_local_timestamp(ts) == expected


def test_format_session_age():
    now = 1_700_000_000.0
    assert format_session_age(now - 120, now=now) == "2m"
    assert format_session_age(now - 7200, now=now) == "2h"


@pytest.mark.asyncio
async def test_backfill_title_from_history(tmp_path):
    store = SessionStore(tmp_path / "state.db")
    await store.initialize()
    sid = await store.create_session(profile="default")
    await store.append_message(sid, {"role": "user", "content": "帮我写一个 Python 脚本"})
    assert await store.backfill_title_from_history(sid)
    assert await store.get_title(sid) == "帮我写一个 Python 脚本"


@pytest.mark.asyncio
async def test_resume_backfills_truncated_title(tmp_path):
    store = SessionStore(tmp_path / "state.db")
    await store.initialize()
    sid = await store.create_session(profile="default")
    await store.append_message(sid, {"role": "user", "content": "旧会话没有标题"})
    await store.append_message(sid, {"role": "assistant", "content": "好的"})

    engine = QueryEngine(
        deps=AgentDeps.with_call_model(make_sequential_mock([lambda: mock_text_response("ok")])),
        session_store=store,
        profile="default",
        max_turns=1,
    )
    await engine.resume_session(sid)
    assert await store.get_title(sid) == "旧会话没有标题"


@pytest.mark.asyncio
async def test_session_to_dict_includes_local_time(tmp_path):
    store = SessionStore(tmp_path / "state.db")
    await store.initialize()
    sid = await store.create_session(profile="default", title="测试")
    sessions = await store.list_sessions(profile="default")
    data = session_to_dict(sessions[0])
    assert data["id"] == sid
    assert "updated_at_local" in data
    assert data["updated_at_local"] == format_local_timestamp(sessions[0].updated_at)
