"""Tests for TuiConsole streaming via print_formatted_text."""

from unittest.mock import patch

from cli.tui_console import TuiConsole


def test_write_stream_flushes_on_end_stream_line():
    console = TuiConsole()
    printed: list[str] = []

    def capture(text, **kwargs):  # noqa: ANN003
        printed.append(str(text))

    with patch("cli.tui_console.print_formatted_text", side_effect=capture):
        console.write_stream("你好")
        assert printed == []
        console.end_stream_line()
        assert printed == ["你好"]


def test_write_stream_emits_complete_lines():
    console = TuiConsole()
    printed: list[str] = []

    with patch("cli.tui_console.print_formatted_text", side_effect=lambda t, **k: printed.append(str(t))):
        console.write_stream("line1\nline2\n")
        assert printed == ["line1", "line2"]
