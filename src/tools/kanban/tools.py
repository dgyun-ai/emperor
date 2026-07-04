"""Kanban worker and orchestrator tools."""

from __future__ import annotations

import json
import os
from typing import Any

from constants import ENV_EMPEROR_KANBAN_TASK
from context.tool_context import ToolContext
from kanban.db import KanbanDB
from kanban.worker_context import build_worker_context, task_summary_dict
from tools.base import ToolResult
from tools.registry import register_tool


def _db(ctx: ToolContext) -> KanbanDB:
    profile = getattr(ctx, "profile", None) or "default"
    return KanbanDB.for_profile(profile)


def _task_id(input: dict[str, Any]) -> str | None:
    return input.get("task_id") or os.environ.get(ENV_EMPEROR_KANBAN_TASK)


@register_tool(
    name="kanban_show",
    description="Read the current kanban task with full worker_context.",
    toolset="kanban",
    input_schema={
        "type": "object",
        "properties": {"task_id": {"type": "string"}},
    },
    is_read_only=True,
)
async def kanban_show(input: dict, ctx: ToolContext) -> ToolResult:
    db = _db(ctx)
    await db.initialize()
    tid = _task_id(input)
    if not tid:
        return ToolResult(content="Error: task_id required", is_error=True)
    task = await db.get_task(tid)
    if not task:
        return ToolResult(content=f"Error: task {tid} not found", is_error=True)
    ctx_text = await build_worker_context(db, task)
    payload = {**task_summary_dict(task), "worker_context": ctx_text}
    return ToolResult(content=json.dumps(payload, ensure_ascii=False))


@register_tool(
    name="kanban_list",
    description="List kanban tasks with optional filters.",
    toolset="kanban",
    input_schema={
        "type": "object",
        "properties": {
            "status": {"type": "string"},
            "assignee": {"type": "string"},
            "tenant": {"type": "string"},
        },
    },
    is_read_only=True,
)
async def kanban_list(input: dict, ctx: ToolContext) -> ToolResult:
    db = _db(ctx)
    await db.initialize()
    tasks = await db.list_tasks(
        status=input.get("status"),
        assignee=input.get("assignee"),
        tenant=input.get("tenant"),
    )
    return ToolResult(content=json.dumps([t.to_card_dict() for t in tasks], ensure_ascii=False))


@register_tool(
    name="kanban_complete",
    description="Complete the kanban task with structured handoff.",
    toolset="kanban",
    input_schema={
        "type": "object",
        "properties": {
            "task_id": {"type": "string"},
            "summary": {"type": "string"},
            "result": {"type": "string"},
            "metadata": {"type": "object"},
        },
        "required": ["summary"],
    },
)
async def kanban_complete(input: dict, ctx: ToolContext) -> ToolResult:
    db = _db(ctx)
    await db.initialize()
    tid = _task_id(input)
    if not tid:
        return ToolResult(content="Error: task_id required", is_error=True)
    task = await db.complete_task(
        tid,
        summary=input.get("summary"),
        metadata=input.get("metadata"),
        result=input.get("result"),
    )
    if not task:
        return ToolResult(content="Error: task not found", is_error=True)
    return ToolResult(content=json.dumps({"ok": True, "task_id": tid, "status": task.status}))


@register_tool(
    name="kanban_block",
    description="Block the kanban task and request human input.",
    toolset="kanban",
    input_schema={
        "type": "object",
        "properties": {
            "task_id": {"type": "string"},
            "reason": {"type": "string"},
        },
        "required": ["reason"],
    },
)
async def kanban_block(input: dict, ctx: ToolContext) -> ToolResult:
    db = _db(ctx)
    await db.initialize()
    tid = _task_id(input)
    if not tid:
        return ToolResult(content="Error: task_id required", is_error=True)
    task = await db.block_task(tid, reason=input["reason"])
    if not task:
        return ToolResult(content="Error: task not found", is_error=True)
    return ToolResult(content=json.dumps({"ok": True, "status": task.status}))


@register_tool(
    name="kanban_heartbeat",
    description="Signal liveness during long kanban task execution.",
    toolset="kanban",
    input_schema={
        "type": "object",
        "properties": {
            "task_id": {"type": "string"},
            "note": {"type": "string"},
        },
    },
)
async def kanban_heartbeat(input: dict, ctx: ToolContext) -> ToolResult:
    db = _db(ctx)
    await db.initialize()
    tid = _task_id(input)
    if not tid:
        return ToolResult(content="Error: task_id required", is_error=True)
    await db.heartbeat(tid, note=input.get("note"))
    return ToolResult(content=json.dumps({"ok": True}))


@register_tool(
    name="kanban_comment",
    description="Append a comment to a kanban task thread.",
    toolset="kanban",
    input_schema={
        "type": "object",
        "properties": {
            "task_id": {"type": "string"},
            "body": {"type": "string"},
            "author": {"type": "string"},
        },
        "required": ["task_id", "body"],
    },
)
async def kanban_comment(input: dict, ctx: ToolContext) -> ToolResult:
    db = _db(ctx)
    await db.initialize()
    comment = await db.append_comment(
        input["task_id"],
        input["body"],
        author=input.get("author"),
    )
    return ToolResult(content=json.dumps({"id": comment.id}))


@register_tool(
    name="kanban_create",
    description="Create a kanban sub-task (orchestrator).",
    toolset="kanban",
    input_schema={
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "assignee": {"type": "string"},
            "body": {"type": "string"},
            "tenant": {"type": "string"},
            "parents": {"type": "array", "items": {"type": "string"}},
            "priority": {"type": "integer"},
        },
        "required": ["title", "assignee"],
    },
)
async def kanban_create(input: dict, ctx: ToolContext) -> ToolResult:
    db = _db(ctx)
    await db.initialize()
    task = await db.create_task(
        input["title"],
        body=input.get("body"),
        assignee=input.get("assignee"),
        tenant=input.get("tenant"),
        priority=input.get("priority", 3),
        parent_ids=input.get("parents"),
    )
    return ToolResult(content=json.dumps({"task_id": task.id, "status": task.status}))


@register_tool(
    name="kanban_link",
    description="Add parent->child dependency between kanban tasks.",
    toolset="kanban",
    input_schema={
        "type": "object",
        "properties": {
            "parent_id": {"type": "string"},
            "child_id": {"type": "string"},
        },
        "required": ["parent_id", "child_id"],
    },
)
async def kanban_link(input: dict, ctx: ToolContext) -> ToolResult:
    db = _db(ctx)
    await db.initialize()
    try:
        await db.add_link(input["parent_id"], input["child_id"])
    except ValueError as exc:
        return ToolResult(content=f"Error: {exc}", is_error=True)
    return ToolResult(content=json.dumps({"ok": True}))


@register_tool(
    name="kanban_unblock",
    description="Unblock a kanban task and return it to ready.",
    toolset="kanban",
    input_schema={
        "type": "object",
        "properties": {"task_id": {"type": "string"}},
        "required": ["task_id"],
    },
)
async def kanban_unblock(input: dict, ctx: ToolContext) -> ToolResult:
    db = _db(ctx)
    await db.initialize()
    task = await db.unblock_task(input["task_id"])
    if not task:
        return ToolResult(content="Error: task not found", is_error=True)
    return ToolResult(content=json.dumps({"ok": True, "status": task.status}))
