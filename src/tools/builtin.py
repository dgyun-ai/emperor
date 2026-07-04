"""Built-in tools for testing and demos."""

from __future__ import annotations

import json

from context.tool_context import ToolContext
from tools.base import ToolResult
from tools.registry import register_tool


@register_tool(
    name="echo",
    description="Echo the input message back to the caller.",
    input_schema={
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Text to echo"},
        },
        "required": ["message"],
    },
    is_read_only=True,
)
async def echo_tool(input: dict, ctx: ToolContext) -> ToolResult:
    message = input.get("message", "")
    return ToolResult(content=json.dumps({"echo": message}))
