"""Tests for kanban dispatcher."""

from __future__ import annotations

import pytest

from config.models import EmperorConfig
from kanban.db import KanbanDB
from kanban.dispatcher import KanbanDispatcher


@pytest.mark.asyncio
async def test_dispatch_dry_run(tmp_path):
    db = KanbanDB(tmp_path / "kanban.db")
    await db.initialize()
    await db.create_task("Ready work", assignee="dev")
    disp = KanbanDispatcher(db, EmperorConfig())
    result = await disp.tick(max_tasks=3, dry_run=True)
    assert len(result["claimed"]) == 1


@pytest.mark.asyncio
async def test_spawn_failure_increments(tmp_path):
    db = KanbanDB(tmp_path / "kanban.db")
    await db.initialize()
    task = await db.create_task("Fragile", assignee="dev", max_retries=1)
    await db.claim_task(task.id)
    await db.record_spawn_failure(task.id, "boom", max_retries=1)
    updated = await db.get_task(task.id)
    assert updated is not None
    assert updated.status == "blocked"
