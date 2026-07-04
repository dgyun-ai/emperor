"""File read tool."""

from __future__ import annotations

from pathlib import Path

from context.tool_context import ToolContext
from tools.base import ToolResult
from tools.registry import register_tool


@register_tool(
    name="file_read",
    description="Read contents of a file at the given path.",
    toolset="file",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to read"},
            "offset": {"type": "integer", "description": "Start line (1-based)", "default": 1},
            "limit": {"type": "integer", "description": "Max lines to read"},
        },
        "required": ["path"],
    },
    is_read_only=True,
)
async def file_read(input: dict, ctx: ToolContext) -> ToolResult:
    path = Path(input["path"]).expanduser().resolve()
    if not path.exists():
        return ToolResult(content=f"Error: file not found: {path}", is_error=True)
    if not path.is_file():
        return ToolResult(content=f"Error: not a file: {path}", is_error=True)

    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    offset = max(1, int(input.get("offset", 1))) - 1
    limit = input.get("limit")
    if limit is not None:
        lines = lines[offset : offset + int(limit)]
    else:
        lines = lines[offset:]
    numbered = "\n".join(f"{i + offset + 1}|{line}" for i, line in enumerate(lines))
    return ToolResult(content=numbered or "(empty file)")
