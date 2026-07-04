"""Tool protocol, defaults, and registration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from context.tool_context import ToolContext


@dataclass
class ToolResult:
    content: str
    is_error: bool = False
    context_patch: dict[str, Any] = field(default_factory=dict)
    system_messages: list[str] = field(default_factory=list)


@runtime_checkable
class Tool(Protocol):
    name: str
    description: str
    input_schema: dict[str, Any]
    is_read_only: bool
    is_interactive: bool

    async def call(self, input: dict[str, Any], ctx: ToolContext) -> ToolResult: ...


TOOL_DEFAULTS = {
    "is_read_only": False,
    "is_interactive": False,
}


def build_tool(
    *,
    name: str,
    description: str,
    input_schema: dict[str, Any],
    call_fn: Any,
    is_read_only: bool = False,
    is_interactive: bool = False,
) -> Tool:
    """Build a Tool with fail-closed defaults (not concurrency-safe by default)."""

    class BuiltTool:
        pass

    tool = BuiltTool()
    tool.name = name
    tool.description = description
    tool.input_schema = input_schema
    tool.is_read_only = is_read_only
    tool.is_interactive = is_interactive

    async def call(input: dict[str, Any], ctx: ToolContext) -> ToolResult:
        if ctx.is_aborted():
            return ToolResult(content="Aborted", is_error=True)
        if not ctx.allow_tool(name, input):
            return ToolResult(content=f"Permission denied for tool '{name}'", is_error=True)
        return await call_fn(input, ctx)

    tool.call = call  # type: ignore[method-assign]
    return tool  # type: ignore[return-value]


def tools_to_openai_schema(tools: list[Tool]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.input_schema,
            },
        }
        for t in tools
    ]
