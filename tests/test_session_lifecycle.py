"""Session lifecycle: resume must not create orphan rows."""

from __future__ import annotations

import pytest

from agent.deps import AgentDeps
from engine.query_engine import QueryEngine
from session.store import SessionStore


@pytest.mark.asyncio
async def test_resume_session_does_not_create_orphan(tmp_path):
    store = SessionStore(tmp_path / "state.db")
    await store.initialize()
    sid = await store.create_session(profile="default")
    await store.append_message(sid, {"role": "user", "content": "hello"})

    engine = QueryEngine(
        deps=AgentDeps.with_call_model(lambda **k: (_ for _ in ()).throw(StopIteration)),  # type: ignore[arg-type]
        session_store=store,
        profile="default",
    )
    await engine.resume_session(sid)

    sessions = await store.list_sessions(profile="default")
    assert len(sessions) == 1
    assert sessions[0].id == sid
    assert sessions[0].message_count == 1


@pytest.mark.asyncio
async def test_set_title_if_empty_from_first_message(tmp_path):
    store = SessionStore(tmp_path / "state.db")
    await store.initialize()
    sid = await store.create_session(profile="default")
    await store.set_title_if_empty(sid, "帮我写一个 Python 脚本")
    sessions = await store.list_sessions(profile="default")
    assert sessions[0].title == "帮我写一个 Python 脚本"


@pytest.mark.asyncio
async def test_get_latest_session_skips_empty(tmp_path):
    store = SessionStore(tmp_path / "state.db")
    await store.initialize()
    await store.create_session(profile="default")
    sid = await store.create_session(profile="default")
    await store.append_message(sid, {"role": "user", "content": "hi"})
    assert await store.get_latest_session(profile="default") == sid
