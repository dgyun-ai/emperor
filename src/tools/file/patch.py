"""File patch (search/replace) tool."""

from __future__ import annotations

from pathlib import Path

from context.tool_context import ToolContext
from tools.approval import check_tool_approval
from tools.base import ToolResult
from tools.registry import register_tool


@register_tool(
    name="file_patch",
    description="Replace old_string with new_string in a file (must be unique).",
    toolset="file",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "old_string": {"type": "string"},
            "new_string": {"type": "string"},
        },
        "required": ["path", "old_string", "new_string"],
    },
)
async def file_patch(input: dict, ctx: ToolContext) -> ToolResult:
    approved, reason = await check_tool_approval("file_patch", input)
    if not approved:
        return ToolResult(content=reason or "Denied", is_error=True)

    path = Path(input["path"]).expanduser()
    if not path.exists():
        return ToolResult(content=f"Error: file not found: {path}", is_error=True)

    text = path.read_text(encoding="utf-8")
    old = input["old_string"]
    new = input["new_string"]
    count = text.count(old)
    if count == 0:
        return ToolResult(content="Error: old_string not found", is_error=True)
    if count > 1:
        return ToolResult(content=f"Error: old_string found {count} times; must be unique", is_error=True)
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return ToolResult(content=f"Patched {path}")
