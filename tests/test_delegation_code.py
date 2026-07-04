"""Tests for delegation, code exec, terminal backends."""

from __future__ import annotations

import pytest

from context.tool_context import ToolContext
from tools.environments.backends import DockerBackend, LocalBackend, get_backend
from tools.registry import discover_tools, get_tool


@pytest.mark.asyncio
async def test_execute_code():
    discover_tools()
    tool = get_tool("execute_code")
    assert tool is not None
    ctx = ToolContext(messages=[])
    r = await tool.call({"code": "result = 2 + 2\nprint(result)"}, ctx)
    assert "4" in r.content


@pytest.mark.asyncio
async def test_execute_code_error():
    discover_tools()
    tool = get_tool("execute_code")
    ctx = ToolContext(messages=[])
    r = await tool.call({"code": "raise ValueError('boom')"}, ctx)
    assert r.is_error


@pytest.mark.asyncio
async def test_local_backend_echo():
    backend = LocalBackend()
    result = await backend.run("echo hello")
    assert "hello" in result.stdout
    assert result.returncode == 0


def test_get_backend_local():
    assert isinstance(get_backend("local"), LocalBackend)


def test_get_backend_docker():
    assert isinstance(get_backend("docker"), DockerBackend)


def test_delegate_task_registered():
    discover_tools()
    tool = get_tool("delegate_task")
    assert tool is not None
    assert tool.name == "delegate_task"


@pytest.mark.asyncio
async def test_todo_tool():
    from tools.todo import reset_todos

    reset_todos()
    discover_tools()
    todo = get_tool("todo")
    ctx = ToolContext(messages=[])
    r = await todo.call({"action": "add", "text": "task1"}, ctx)
    assert "task1" in r.content
    r = await todo.call({"action": "list"}, ctx)
    assert "task1" in r.content
