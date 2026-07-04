"""Agent-level session search tool."""

from __future__ import annotations

import json

from context.tool_context import ToolContext
from session.store import SessionStore
from tools.base import ToolResult
from tools.registry import register_tool

_store: SessionStore | None = None


def configure_session_store(store: SessionStore) -> None:
    global _store
    _store = store


@register_tool(
    name="session_search",
    description="Search past session messages via FTS5.",
    toolset="agent",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "default": 10},
        },
        "required": ["query"],
    },
    is_read_only=True,
)
async def session_search_tool(input: dict, ctx: ToolContext) -> ToolResult:
    store = _store or SessionStore.for_profile()
    await store.initialize()
    results = await store.search_messages(input["query"], limit=int(input.get("limit", 10)))
    return ToolResult(content=json.dumps(results))
