"""Tests for kanban worker tools."""

from __future__ import annotations

import json
import os

import pytest

import tools.kanban.tools  # noqa: F401
from context.tool_context import ToolContext
from kanban.db import KanbanDB
from tools.registry import get_tool


@pytest.fixture
async def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("EMPEROR_HOME", str(tmp_path))
    db = KanbanDB(tmp_path / "kanban.db")
    await db.initialize()
    return ToolContext(messages=[])


@pytest.mark.asyncio
async def test_kanban_show_and_complete(ctx: ToolContext, tmp_path, monkeypatch):
    monkeypatch.setenv("EMPEROR_HOME", str(tmp_path))
    db = KanbanDB.for_profile("default")
    await db.initialize()
    task = await db.create_task("Worker task", assignee="dev", body="Do the thing")
    monkeypatch.setenv("EMPEROR_KANBAN_TASK", task.id)

    show = get_tool("kanban_show")
    assert show is not None
    result = await show.call({}, ctx)
    data = json.loads(result.content)
    assert data["id"] == task.id
    assert "worker_context" in data

    complete = get_tool("kanban_complete")
    assert complete is not None
    await complete.call({"summary": "all done", "metadata": {"ok": True}}, ctx)
    updated = await db.get_task(task.id)
    assert updated is not None
    assert updated.status == "done"
