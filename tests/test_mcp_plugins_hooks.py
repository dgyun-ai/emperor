"""Tests for MCP, plugins, hooks."""

from __future__ import annotations

import pytest

from hooks.lifecycle import HookManager
from mcp.client import MCPClient, MCPServerConfig
from plugins.manager import PluginManager
from tools.base import ToolResult


@pytest.mark.asyncio
async def test_mcp_client_schema():
    client = MCPClient(MCPServerConfig(name="test", command="echo"))
    tools = client.load_tools_from_schema(
        [{"name": "list_files", "description": "List", "inputSchema": {"type": "object", "properties": {}}}]
    )
    assert len(tools) == 1
    assert tools[0].name.startswith("mcp_test_")


def test_plugin_manager_discover(tmp_path):
    plugins_dir = tmp_path / "plugins" / "demo"
    plugins_dir.mkdir(parents=True)
    (plugins_dir / "plugin.json").write_text('{"name": "demo", "version": "1.0"}')
    mgr = PluginManager(project_dir=tmp_path)
    mgr.user_plugins = tmp_path / "plugins"
    found = mgr.discover()
    assert any(p.name == "demo" for p in found)


@pytest.mark.asyncio
async def test_hook_manager_pre_tool_use():
    hooks = HookManager()
    blocked = False

    async def block_write(name, data):
        return name != "file_write"

    hooks.pre_tool_use.append(block_write)
    assert await hooks.run_pre_tool_use("file_read", {})
    assert not await hooks.run_pre_tool_use("file_write", {})


@pytest.mark.asyncio
async def test_hook_post_and_stop():
    hooks = HookManager()
    called = []

    async def post(name, data, result):
        called.append(name)

    async def stop(reason):
        called.append(reason)

    hooks.post_tool_use.append(post)
    hooks.stop.append(stop)
    await hooks.run_post_tool_use("echo", {}, ToolResult(content="ok"))
    await hooks.run_stop("done")
    assert "echo" in called
    assert "done" in called
