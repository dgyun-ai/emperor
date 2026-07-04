"""Tests for cron, batch, trajectory, gateway."""

from __future__ import annotations

import json
import asyncio

import pytest

from agent.deps import AgentDeps
from cron.scheduler import CronScheduler
from engine.query_engine import QueryEngine
from gateway.session_router import SessionRouter
from helpers import TEST_CONFIG, make_sequential_mock, mock_text_response
from session.convert import events_to_openai_messages
from session.store import SessionStore
from trajectory.export import export_sharegpt_jsonl, messages_to_sharegpt


def test_cron_scheduler_add_list(tmp_path):
    sched = CronScheduler(home=tmp_path)
    job = sched.add_job(
        name="check",
        schedule={"kind": "every", "everyMs": 60000},
        payload={"kind": "agentTurn", "message": "check inbox"},
        target_session_id="sess-1",
    )
    assert job.id
    assert job.schedule["kind"] == "every"
    assert len(sched.list_jobs()) == 1
    assert sched.remove_job(job.id)


@pytest.mark.asyncio
async def test_cron_scheduler_trigger_and_cancel(tmp_path):
    sched = CronScheduler(home=tmp_path)
    job = sched.add_job(
        name="check",
        schedule={"kind": "every", "everyMs": 60000},
        payload={"kind": "agentTurn", "message": "check inbox"},
        target_session_id="sess-1",
    )

    started = asyncio.Event()

    async def executor(_job, _trigger):
        started.set()
        await asyncio.sleep(10)
        return "done"

    sched.set_executor(executor)
    run = await sched.trigger_job(job.id)
    await asyncio.wait_for(started.wait(), timeout=1)
    assert run.status in {"queued", "running"}
    ok = await sched.cancel_run(run.run_id)
    assert ok is True
    updated = sched.get_run(run.run_id)
    assert updated is not None
    assert updated.status == "cancelled"


@pytest.mark.asyncio
async def test_cron_scheduler_runs_once_job_once(tmp_path):
    sched = CronScheduler(home=tmp_path)
    job = sched.add_job(
        name="once-check",
        schedule={"kind": "at", "at": "2099-01-01T00:00:00Z"},
        payload={"kind": "agentTurn", "message": "check once"},
        target_session_id="sess-1",
    )
    job.schedule = {"kind": "at", "at": "2000-01-01T00:00:00Z"}

    calls: list[str] = []

    async def executor(_job, _trigger):
        calls.append("ran")
        return "done"

    sched.set_executor(executor)
    await sched.start()
    try:
        await asyncio.sleep(1.2)
    finally:
        await sched.stop()

    refreshed = sched.get_job(job.id)
    assert refreshed is not None
    assert calls == ["ran"]
    assert refreshed.enabled is False
    assert refreshed.last_run_at is not None


def test_session_router():
    router = SessionRouter()
    router.set_session("user:1", "sess-abc")
    assert router.get_session("user:1") == "sess-abc"
    router.pair("user:1")
    assert router.is_paired("user:1")


def test_sharegpt_export(tmp_path):
    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    conv = messages_to_sharegpt(msgs)
    assert conv[0]["from"] == "human"
    out = tmp_path / "out.jsonl"
    export_sharegpt_jsonl(msgs, out)
    data = json.loads(out.read_text())
    assert "conversations" in data


@pytest.mark.asyncio
async def test_gateway_session_resume(tmp_path, monkeypatch):
    from gateway.runner import GatewayRunner

    home = tmp_path / "gw-profile"
    monkeypatch.setattr("session.store.get_emperor_home", lambda profile=None: home)

    call_count = 0

    def factory(platform_key: str) -> QueryEngine:
        nonlocal call_count
        call_count += 1
        store = SessionStore(home / "state.db")
        call_model = make_sequential_mock([lambda: mock_text_response(f"reply-{call_count}")])
        return QueryEngine(
            deps=AgentDeps.with_call_model(call_model),
            session_store=store,
            profile="gw-profile",
            tools=[],
            max_turns=5,
            config=TEST_CONFIG,
        )

    runner = GatewayRunner(engine_factory=factory)
    r1 = await runner.handle_message("telegram:99", "hello")
    assert r1 == "reply-1"
    sid = runner.router.get_session("telegram:99")
    assert sid is not None

    r2 = await runner.handle_message("telegram:99", "again")
    assert r2 == "reply-2"
    assert runner.router.get_session("telegram:99") == sid

    store = SessionStore(home / "state.db")
    await store.initialize()
    events = await store.load_events(sid)
    messages = events_to_openai_messages(events)
    assert len(messages) >= 4  # 2 user + 2 assistant


@pytest.mark.asyncio
async def test_batch_runner():
    from batch.runner import run_batch

    call_model = make_sequential_mock(
        [lambda: mock_text_response("a"), lambda: mock_text_response("b")]
    )
    results = await run_batch(
        ["p1", "p2"],
        deps=AgentDeps.with_call_model(call_model),
        tools=[],
        config=TEST_CONFIG,
    )
    assert len(results) == 2
    assert results[0].response == "a"
