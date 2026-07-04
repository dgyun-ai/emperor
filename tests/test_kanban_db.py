"""Tests for kanban database layer."""

from __future__ import annotations

import pytest

from kanban.db import KanbanDB


@pytest.fixture
async def kdb(tmp_path):
    db = KanbanDB(tmp_path / "kanban.db")
    await db.initialize()
    return db


@pytest.mark.asyncio
async def test_create_task_ready_with_assignee(kdb: KanbanDB):
    task = await kdb.create_task("Hello", assignee="dev")
    assert task.status == "ready"
    assert task.assignee == "dev"


@pytest.mark.asyncio
async def test_create_triage_task(kdb: KanbanDB):
    task = await kdb.create_task("Idea", triage=True)
    assert task.status == "triage"


@pytest.mark.asyncio
async def test_dependency_promotion(kdb: KanbanDB):
    parent = await kdb.create_task("Parent", assignee="dev")
    child = await kdb.create_task("Child", assignee="dev", parent_ids=[parent.id])
    assert child.status == "todo"

    board = await kdb.get_board()
    ready_ids = [c["id"] for c in board["columns"]["ready"]]
    assert parent.id in ready_ids
    assert child.id not in ready_ids

    await kdb.complete_task(parent.id, summary="done parent")
    board = await kdb.get_board()
    ready_ids = [c["id"] for c in board["columns"]["ready"]]
    assert child.id in ready_ids


@pytest.mark.asyncio
async def test_claim_and_complete(kdb: KanbanDB):
    task = await kdb.create_task("Work", assignee="dev")
    run = await kdb.claim_task(task.id, profile="dev")
    assert run is not None
    assert run.outcome == "active"

    updated = await kdb.get_task(task.id)
    assert updated is not None
    assert updated.status == "running"

    done = await kdb.complete_task(
        task.id, summary="finished", metadata={"files": ["a.py"]}
    )
    assert done is not None
    assert done.status == "done"
    assert len(done.runs) == 1
    assert done.runs[0].outcome == "completed"
    assert done.runs[0].summary == "finished"


@pytest.mark.asyncio
async def test_block_and_unblock(kdb: KanbanDB):
    task = await kdb.create_task("Review", assignee="reviewer")
    await kdb.claim_task(task.id)
    blocked = await kdb.block_task(task.id, reason="need input")
    assert blocked is not None
    assert blocked.status == "blocked"
    assert blocked.runs[-1].outcome == "blocked"

    unblocked = await kdb.unblock_task(task.id)
    assert unblocked is not None
    assert unblocked.status == "ready"


@pytest.mark.asyncio
async def test_link_cycle_rejected(kdb: KanbanDB):
    a = await kdb.create_task("A")
    b = await kdb.create_task("B", parent_ids=[a.id])
    with pytest.raises(ValueError, match="cycle"):
        await kdb.add_link(b.id, a.id)


@pytest.mark.asyncio
async def test_idempotency_key(kdb: KanbanDB):
    t1 = await kdb.create_task("Once", idempotency_key="key-1")
    t2 = await kdb.create_task("Twice", idempotency_key="key-1")
    assert t1.id == t2.id


@pytest.mark.asyncio
async def test_comments_and_events(kdb: KanbanDB):
    task = await kdb.create_task("Commented")
    await kdb.append_comment(task.id, "hello", author="human")
    full = await kdb.get_task(task.id)
    assert full is not None
    assert len(full.comments) == 1
    assert full.comments[0].body == "hello"

    events = await kdb.list_events(since_id=0)
    assert any(e.kind == "created" for e in events)
