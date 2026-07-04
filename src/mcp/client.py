"""MCP stdio client with tool schema conversion."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from tools.base import Tool, ToolResult, build_tool
from context.tool_context import ToolContext


@dataclass
class MCPServerConfig:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class MCPToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]


class MCPClient:
    """Minimal MCP stdio client (schema-only MVP; connect on demand)."""

    def __init__(self, config: MCPServerConfig) -> None:
        self.config = config
        self._tools: list[MCPToolDefinition] = []
        self._connected = False

    async def connect(self) -> None:
        """MVP: mark connected without full MCP handshake."""
        self._connected = True

    async def list_tools(self) -> list[MCPToolDefinition]:
        if not self._connected:
            await self.connect()
        return list(self._tools)

    def register_external_tools(self, tools: list[MCPToolDefinition]) -> list[Tool]:
        """Convert MCP tool defs to emperor Tool instances."""
        result: list[Tool] = []
        for td in tools:
            prefixed = f"mcp_{self.config.name}_{td.name}"

            async def call_fn(
                input: dict[str, Any],
                ctx: ToolContext,
                _name: str = td.name,
            ) -> ToolResult:
                return ToolResult(
                    content=json.dumps({"mcp": self.config.name, "tool": _name, "input": input, "status": "stub"})
                )

            result.append(
                build_tool(
                    name=prefixed,
                    description=f"[MCP:{self.config.name}] {td.description}",
                    input_schema=td.input_schema,
                    call_fn=call_fn,
                    is_read_only=False,
                )
            )
        return result

    def load_tools_from_schema(self, schema_json: list[dict[str, Any]]) -> list[Tool]:
        defs = [
            MCPToolDefinition(
                name=t["name"],
                description=t.get("description", ""),
                input_schema=t.get("inputSchema", {"type": "object", "properties": {}}),
            )
            for t in schema_json
        ]
        self._tools.extend(defs)
        return self.register_external_tools(defs)
