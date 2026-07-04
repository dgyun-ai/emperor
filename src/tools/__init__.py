"""Tool framework."""

from tools.base import Tool, ToolResult, build_tool, tools_to_openai_schema
from tools.registry import get_tool, list_tools, register_tool

# Import builtins to register echo tool
import tools.builtin  # noqa: F401

__all__ = [
    "Tool",
    "ToolResult",
    "build_tool",
    "tools_to_openai_schema",
    "register_tool",
    "get_tool",
    "list_tools",
]
