"""Tests for TUI-safe user line reading."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cli.repl import ChatRepl
from config.models import EmperorConfig


@pytest.mark.asyncio
async def test_read_user_line_uses_tui_when_available():
    engine = MagicMock()
    engine.config = EmperorConfig()
    repl = ChatRepl(engine=engine, config=engine.config, profile="default")
    tui = MagicMock()
    tui.read_line = AsyncMock(return_value="2")
    repl._tui_ref = tui

    result = await repl.read_user_line("选择会话> ")
    assert result == "2"
    tui.read_line.assert_awaited_once()


@pytest.mark.asyncio
async def test_read_user_line_falls_back_to_prompt_session():
    engine = MagicMock()
    engine.config = EmperorConfig()
    repl = ChatRepl(engine=engine, config=engine.config, profile="default")
    repl._tui_ref = None

    with patch("cli.repl.asyncio.to_thread", new=AsyncMock(return_value="hello")) as to_thread:
        result = await repl.read_user_line("> ")
        assert result == "hello"
        to_thread.assert_awaited_once()
