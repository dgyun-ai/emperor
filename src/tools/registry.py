"""Import-time tool registry with toolset support."""

from __future__ import annotations

import importlib
import pkgutil
from typing import Any

from tools.base import Tool, build_tool

_REGISTRY: dict[str, Tool] = {}
_TOOLSETS: dict[str, set[str]] = {}
_TOOL_TO_TOOLSET: dict[str, str] = {}
_DISCOVERED = False


def register_tool(
    *,
    name: str,
    description: str,
    input_schema: dict[str, Any],
    toolset: str = "core",
    is_read_only: bool = False,
    is_interactive: bool = False,
) -> Any:
    """Decorator to register a tool at import time."""

    def decorator(fn: Any) -> Any:
        tool = build_tool(
            name=name,
            description=description,
            input_schema=input_schema,
            call_fn=fn,
            is_read_only=is_read_only,
            is_interactive=is_interactive,
        )
        _REGISTRY[name] = tool
        _TOOL_TO_TOOLSET[name] = toolset
        _TOOLSETS.setdefault(toolset, set()).add(name)
        return fn

    return decorator


def get_tool(name: str) -> Tool | None:
    return _REGISTRY.get(name)


def list_tools() -> list[Tool]:
    return list(_REGISTRY.values())


def list_toolsets() -> dict[str, list[str]]:
    return {k: sorted(v) for k, v in _TOOLSETS.items()}


def get_tools_for_toolsets(
    enabled: list[str] | None = None,
    disabled: list[str] | None = None,
) -> list[Tool]:
    """Return tools filtered by toolset allow/deny lists."""
    discover_tools()
    enabled_set = set(enabled or [])
    disabled_set = set(disabled or [])
    result: list[Tool] = []
    for name, tool in _REGISTRY.items():
        toolset = _TOOL_TO_TOOLSET.get(name, "core")
        if enabled_set and toolset not in enabled_set:
            continue
        if toolset in disabled_set:
            continue
        result.append(tool)
    return result


def discover_tools() -> None:
    """Auto-import tool subpackages for registration."""
    global _DISCOVERED
    if _DISCOVERED:
        return
    _DISCOVERED = True
    import tools as tools_pkg

    prefix = tools_pkg.__name__ + "."
    for mod in pkgutil.walk_packages(tools_pkg.__path__, prefix):
        if mod.name.endswith(".base") or mod.name.endswith(".registry"):
            continue
        if mod.name.endswith(".orchestrator") or mod.name.endswith(".approval"):
            continue
        try:
            importlib.import_module(mod.name)
        except ImportError:
            continue

    # Phase 7 delegation tools live outside tools/ package
    try:
        importlib.import_module("delegation.subagent")
    except ImportError:
        pass


def clear_registry() -> None:
    """Clear registry — for tests only."""
    _REGISTRY.clear()
    _TOOLSETS.clear()
    _TOOL_TO_TOOLSET.clear()
    global _DISCOVERED
    _DISCOVERED = False
