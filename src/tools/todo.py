"""Todo list tool."""

from __future__ import annotations

import json
from typing import Any

from context.tool_context import ToolContext
from tools.base import ToolResult
from tools.registry import register_tool

_TODOS: list[dict[str, Any]] = []


def _build_loop_state() -> tuple[dict[str, Any], list[str]]:
    open_items = [item["text"] for item in _TODOS if not item["done"]]
    summary = "No open todos." if not open_items else "Open todos: " + "; ".join(open_items)
    return ({"todos": list(_TODOS), "open_todos": open_items}, [summary])


@register_tool(
    name="todo",
    description="Manage a todo list: list, add, complete, remove items.",
    toolset="todo",
    input_schema={
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["list", "add", "complete", "remove"]},
            "text": {"type": "string"},
            "id": {"type": "integer"},
        },
        "required": ["action"],
    },
)
async def todo_tool(input: dict, ctx: ToolContext) -> ToolResult:
    global _TODOS
    action = input["action"]

    if action == "list":
        return ToolResult(content=json.dumps(_TODOS))

    if action == "add":
        text = input.get("text", "").strip()
        if not text:
            return ToolResult(content="Error: text required for add", is_error=True)
        item = {"id": len(_TODOS) + 1, "text": text, "done": False}
        _TODOS.append(item)
        context_patch, system_messages = _build_loop_state()
        return ToolResult(
            content=json.dumps(item),
            context_patch=context_patch,
            system_messages=system_messages,
        )

    item_id = input.get("id")
    if item_id is None:
        return ToolResult(content="Error: id required", is_error=True)

    for item in _TODOS:
        if item["id"] == item_id:
            if action == "complete":
                item["done"] = True
                context_patch, system_messages = _build_loop_state()
                return ToolResult(
                    content=json.dumps(item),
                    context_patch=context_patch,
                    system_messages=system_messages,
                )
            if action == "remove":
                _TODOS.remove(item)
                context_patch, system_messages = _build_loop_state()
                return ToolResult(
                    content=json.dumps({"removed": item_id}),
                    context_patch=context_patch,
                    system_messages=system_messages,
                )
    return ToolResult(content=f"Error: todo {item_id} not found", is_error=True)


def reset_todos() -> None:
    """Reset todos — for tests."""
    global _TODOS
    _TODOS = []
