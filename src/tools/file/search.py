"""File search (grep) tool."""

from __future__ import annotations

import re
from pathlib import Path

from context.tool_context import ToolContext
from tools.base import ToolResult
from tools.registry import register_tool


@register_tool(
    name="file_search",
    description="Search for a pattern in files under a directory.",
    toolset="file",
    input_schema={
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Regex pattern to search"},
            "path": {"type": "string", "description": "Directory or file to search", "default": "."},
            "glob": {"type": "string", "description": "File glob filter", "default": "**/*"},
            "max_results": {"type": "integer", "default": 50},
        },
        "required": ["pattern"],
    },
    is_read_only=True,
)
async def file_search(input: dict, ctx: ToolContext) -> ToolResult:
    pattern = input["pattern"]
    root = Path(input.get("path", ".")).expanduser().resolve()
    glob = input.get("glob", "**/*")
    max_results = int(input.get("max_results", 50))

    try:
        regex = re.compile(pattern)
    except re.error as exc:
        return ToolResult(content=f"Invalid regex: {exc}", is_error=True)

    if not root.exists():
        return ToolResult(content=f"Error: path not found: {root}", is_error=True)

    matches: list[str] = []
    files = [root] if root.is_file() else root.glob(glob)
    for fp in files:
        if not fp.is_file():
            continue
        try:
            for i, line in enumerate(fp.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if regex.search(line):
                    matches.append(f"{fp}:{i}:{line[:200]}")
                    if len(matches) >= max_results:
                        break
        except OSError:
            continue
        if len(matches) >= max_results:
            break

    if not matches:
        return ToolResult(content="No matches found.")
    return ToolResult(content="\n".join(matches))
