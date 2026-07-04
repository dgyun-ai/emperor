"""Tests for Hermes-style slash command registry."""

from cli.command_registry import completion_candidates, format_help_text, resolve_command


def test_resolve_command_aliases():
    assert resolve_command("help") is not None
    assert resolve_command("/h").name == "help"
    assert resolve_command("reset").name == "new"


def test_completion_candidates():
    from cli.command_registry import completion_candidates, completion_items

    names = completion_candidates("s")
    assert "search" in names
    assert "sessions" in names
    assert "status" in names
    assert completion_items("/")[0]  # bare slash lists commands


def test_format_help_contains_core_commands():
    text = format_help_text(locale="zh")
    assert "/help" in text
    assert "/sessions" in text
    assert "/compress" in text
