"""Tests for file tools."""

from __future__ import annotations

import pytest

from context.tool_context import ToolContext
from tools.registry import discover_tools, get_tool


@pytest.fixture
def ctx():
    return ToolContext(messages=[])


@pytest.mark.asyncio
async def test_file_write_read_patch_search(tmp_path, ctx):
    discover_tools()
    write = get_tool("file_write")
    read = get_tool("file_read")
    patch = get_tool("file_patch")
    search = get_tool("file_search")
    assert all(t is not None for t in [write, read, patch, search])

    fp = tmp_path / "test.txt"
    r = await write.call({"path": str(fp), "content": "hello world\nTODO: fix\n"}, ctx)
    assert not r.is_error

    r = await read.call({"path": str(fp)}, ctx)
    assert "hello world" in r.content

    r = await patch.call({"path": str(fp), "old_string": "hello", "new_string": "hi"}, ctx)
    assert not r.is_error

    r = await search.call({"pattern": "TODO", "path": str(tmp_path)}, ctx)
    assert "TODO" in r.content
