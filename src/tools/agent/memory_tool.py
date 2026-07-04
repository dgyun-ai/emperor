"""Agent-level memory tool."""

from __future__ import annotations

import json

from context.tool_context import ToolContext
from memory.manager import MemoryManager
from tools.base import ToolResult
from tools.registry import register_tool

_manager: MemoryManager | None = None


def configure_memory(manager: MemoryManager) -> None:
    global _manager
    _manager = manager


@register_tool(
    name="memory",
    description="Read or update long-term memory (MEMORY.md / USER.md).",
    toolset="agent",
    input_schema={
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["read", "append", "write_user"]},
            "content": {"type": "string"},
            "target": {"type": "string", "enum": ["memory", "user"], "default": "memory"},
        },
        "required": ["action"],
    },
)
async def memory_tool(input: dict, ctx: ToolContext) -> ToolResult:
    mgr = _manager or MemoryManager()
    action = input["action"]

    if action == "read":
        return ToolResult(content=json.dumps({"memory": mgr.read_memory(), "user": mgr.read_user()}))

    content = input.get("content", "")
    if action == "append":
        mgr.append_memory(content)
        return ToolResult(content="Memory appended.")
    if action == "write_user":
        mgr.write_user(content)
        return ToolResult(content="User profile updated.")
    return ToolResult(content="Unknown action", is_error=True)
