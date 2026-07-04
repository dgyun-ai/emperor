"""Tests for tool registry and orchestrator."""

from __future__ import annotations

import pytest

import tools.builtin  # noqa: F401
from context.tool_context import ToolContext
from provider.openai_compat import ToolCall
from tools.base import build_tool
from tools.cron_tool import cron_tool
from tools.orchestrator import partition_tool_calls
from tools.registry import discover_tools, get_tool, get_tools_for_toolsets, list_toolsets
from tools.approval import is_dangerous_command, is_dangerous_path


def test_discover_tools_registers_file_tools():
    discover_tools()
    assert get_tool("file_read") is not None
    assert get_tool("terminal_run") is not None


def test_toolsets_listing():
    discover_tools()
    toolsets = list_toolsets()
    assert "file" in toolsets
    assert "file_read" in toolsets["file"]


def test_enabled_toolsets_filter():
    discover_tools()
    tools = get_tools_for_toolsets(enabled=["core"])
    names = {t.name for t in tools}
    assert "echo" in names
    assert "file_read" not in names


def test_enabled_toolsets_filter_includes_cron():
    discover_tools()
    tools = get_tools_for_toolsets(enabled=["cron"])
    names = {t.name for t in tools}
    assert "cron" in names


def test_disabled_toolsets_filter():
    discover_tools()
    tools = get_tools_for_toolsets(disabled=["terminal"])
    names = {t.name for t in tools}
    assert "terminal_run" not in names


def test_partition_read_only_concurrent():
    read_tool = build_tool(
        name="r1",
        description="r",
        input_schema={"type": "object", "properties": {}},
        call_fn=lambda i, c: None,
        is_read_only=True,
    )
    write_tool = build_tool(
        name="w1",
        description="w",
        input_schema={"type": "object", "properties": {}},
        call_fn=lambda i, c: None,
    )
    tool_map = {"r1": read_tool, "r2": read_tool, "w1": write_tool}
    calls = [
        ToolCall(id="1", name="r1", arguments={}),
        ToolCall(id="2", name="r2", arguments={}),
        ToolCall(id="3", name="w1", arguments={}),
    ]
    batches = partition_tool_calls(calls, tool_map)
    assert len(batches) == 2
    assert batches[0].concurrent is True
    assert len(batches[0].calls) == 2
    assert batches[1].concurrent is False


def test_dangerous_command_rm_rf():
    assert is_dangerous_command("rm -rf /")


def test_dangerous_command_safe():
    assert not is_dangerous_command("ls -la")


def test_dangerous_path_etc():
    assert is_dangerous_path("/etc/passwd")


def test_dangerous_path_project():
    assert not is_dangerous_path("./src/main.py")


@pytest.mark.asyncio
async def test_cron_tool_uses_profile_scoped_scheduler(tmp_path, monkeypatch):
    monkeypatch.setenv("EMPEROR_HOME", str(tmp_path))
    result = await cron_tool(
        {
            "action": "add",
            "name": "reminder",
            "schedule": {"kind": "every", "everyMs": 300000},
            "payload": {"kind": "agentTurn", "message": "ping"},
            "target_session_id": "sess-1",
        },
        ToolContext(messages=[], extra={"profile": "team-a"}),
    )
    assert result.is_error is False

    default_jobs = tmp_path.joinpath("profiles", "default", "cron_jobs.json")
    scoped_jobs = tmp_path.joinpath("profiles", "team-a", "cron_jobs.json")
    assert not default_jobs.exists()
    assert scoped_jobs.exists()


@pytest.mark.asyncio
async def test_cron_tool_supports_at_job(tmp_path, monkeypatch):
    monkeypatch.setenv("EMPEROR_HOME", str(tmp_path))
    result = await cron_tool(
        {
            "action": "add",
            "name": "reminder",
            "schedule": {"kind": "at", "at": "2099-01-01T00:00:00Z"},
            "payload": {"kind": "agentTurn", "message": "ping"},
            "target_session_id": "sess-1",
        },
        ToolContext(messages=[], extra={"profile": "team-a"}),
    )
    assert result.is_error is False
    assert "\"kind\": \"at\"" in result.content
