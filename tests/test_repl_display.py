"""Tests for Claude-style REPL display helpers."""

from cli.repl_display import (
    format_tool_input_preview,
    format_tool_result_preview,
    tool_display_name,
)


def test_tool_display_name():
    assert tool_display_name("terminal_run") == "Bash"
    assert tool_display_name("unknown_tool") == "unknown_tool"


def test_format_tool_input_terminal():
    preview = format_tool_input_preview("terminal_run", {"command": "ls -la"})
    assert preview == "ls -la"


def test_format_tool_input_path():
    preview = format_tool_input_preview("file_read", {"path": "/tmp/foo.py"})
    assert preview == "/tmp/foo.py"


def test_format_tool_result_preview_truncates():
    lines = format_tool_result_preview("line1\nline2\nline3\nline4\nline5", max_lines=2)
    assert lines[0] == "line1"
    assert lines[1] == "line2"
    assert any("+3 lines" in line for line in lines)


def test_format_tool_result_empty():
    assert format_tool_result_preview("") == []
