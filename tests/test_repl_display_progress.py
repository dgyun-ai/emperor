"""Tests for REPL display progress and streaming."""

from io import StringIO
from unittest.mock import MagicMock

from cli.repl_display import ReplDisplay
from i18n.locale import get_cli_strings


class _FakeConsole:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.stream = StringIO()

    def print(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        self.lines.append(" ".join(str(a) for a in args))

    def write_stream(self, text: str) -> None:
        self.stream.write(text)

    def end_stream_line(self) -> None:
        self.stream.write("\n")


def test_log_phase_prints_to_scrollback():
    console = _FakeConsole()
    tui = MagicMock()
    display = ReplDisplay(console, get_cli_strings("zh"), tui=tui)  # type: ignore[arg-type]
    display.log_phase("连接模型…")
    assert any("连接模型" in line for line in console.lines)
    tui.set_spinner.assert_called_with("连接模型…")


def test_write_complete_message_when_no_stream():
    console = MagicMock()
    console.__class__.__name__ = "TuiConsole"
    written: list[str] = []
    console.write_stream = written.append
    console.end_stream_line = MagicMock()
    display = ReplDisplay(console, get_cli_strings("zh"))  # type: ignore[arg-type]
    display.write_complete_message("你好，世界")
    assert written == ["你好，世界"]
    display.end_turn()
    console.end_stream_line.assert_called_once()
