"""Ctrl+C handling in fixed-bottom TUI."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from cli.tui_app import FixedBottomTui
from config.models import EmperorConfig
from i18n.locale import get_cli_strings


@pytest.mark.asyncio
async def test_read_line_ctrl_c_returns_empty_without_cancelled_error():
    engine = MagicMock()
    engine.config = EmperorConfig()
    strings = get_cli_strings("zh")
    repl = MagicMock()
    repl.config = engine.config
    repl.strings = strings
    repl.profile = "default"

    tui = FixedBottomTui(repl)

    async def read_and_abort() -> str:
        task = asyncio.create_task(tui.read_line())
        await asyncio.sleep(0)
        assert tui._line_future is not None
        tui._line_future.set_result("")
        tui._line_future = None
        return await task

    result = await read_and_abort()
    assert result == ""


@pytest.mark.asyncio
async def test_read_line_task_cancel_returns_empty():
    engine = MagicMock()
    engine.config = EmperorConfig()
    repl = MagicMock()
    repl.config = engine.config
    repl.strings = get_cli_strings("zh")
    repl.profile = "default"

    tui = FixedBottomTui(repl)
    task = asyncio.create_task(tui.read_line())
    await asyncio.sleep(0)
    task.cancel()
    result = await task
    assert result == ""
