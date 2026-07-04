"""Tests for user message echo in REPL."""

from unittest.mock import MagicMock

from cli.repl import ChatRepl
from config.models import EmperorConfig
from i18n.locale import get_cli_strings


def test_print_user_message():
    engine = MagicMock()
    engine.config = EmperorConfig()
    repl = ChatRepl(engine=engine, config=engine.config, profile="default")
    console = MagicMock()
    repl._print_user_message(console, "你好")
    console.print.assert_called_once()
    args = console.print.call_args[0][0]
    assert "你好" in args
