"""Tests for chat terminal I/O helpers."""

from cli.chat_io import normalize_user_command
from cli.prompt import SlashCommandCompleter
from prompt_toolkit.document import Document


def test_slash_completer_help():
    completer = SlashCommandCompleter()
    doc = Document("/he", cursor_position=3)
    names = [c.text for c in completer.get_completions(doc, None)]
    assert "help" in names


def test_slash_completer_all_on_bare_slash():
    from cli.command_registry import completion_items

    items = completion_items("")
    names = {name for name, _ in items}
    assert "help" in names
    assert "sessions" in names
    assert len(names) >= 10


def test_normalize_help():
    assert normalize_user_command("help") == "/help"
    assert normalize_user_command("  HELP  ") == "/help"


def test_normalize_exit():
    assert normalize_user_command("exit") == "exit"
    assert normalize_user_command("quit") == "exit"


def test_normalize_plain_message():
    assert normalize_user_command("你好") == "你好"
