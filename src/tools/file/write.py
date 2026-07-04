"""File write tool."""

from __future__ import annotations

from pathlib import Path

from context.tool_context import ToolContext
from tools.approval import check_tool_approval
from tools.base import ToolResult
from tools.registry import register_tool


@register_tool(
    name="file_write",
    description="Write content to a file, creating parent directories if needed.",
    toolset="file",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["path", "content"],
    },
)
async def file_write(input: dict, ctx: ToolContext) -> ToolResult:
    approved, reason = await check_tool_approval("file_write", input)
    if not approved:
        return ToolResult(content=reason or "Denied", is_error=True)

    path = Path(input["path"]).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(input["content"], encoding="utf-8")
    return ToolResult(content=f"Wrote {len(input['content'])} bytes to {path}")
