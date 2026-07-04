"""Browser fetch tool (httpx MVP)."""

from __future__ import annotations

import json

import httpx

from context.tool_context import ToolContext
from tools.base import ToolResult
from tools.registry import register_tool


@register_tool(
    name="browser_fetch",
    description="Fetch a web page and return simplified text content.",
    toolset="browser",
    input_schema={
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "max_chars": {"type": "integer", "default": 10000},
        },
        "required": ["url"],
    },
    is_read_only=True,
)
async def browser_fetch(input: dict, ctx: ToolContext) -> ToolResult:
    url = input["url"]
    max_chars = int(input.get("max_chars", 10000))
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "emperor/0.1"})
            resp.raise_for_status()
            text = resp.text[:max_chars]
    except httpx.HTTPError as exc:
        return ToolResult(content=f"Browser fetch failed: {exc}", is_error=True)
    return ToolResult(content=json.dumps({"url": url, "status": resp.status_code, "content": text}))
