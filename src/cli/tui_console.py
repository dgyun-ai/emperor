"""Rich console adapter for prompt_toolkit patch_stdout (Hermes ChatConsole pattern)."""

from __future__ import annotations

import re
import shutil
from contextlib import contextmanager
from io import StringIO

from prompt_toolkit import print_formatted_text
from prompt_toolkit.formatted_text import ANSI
from rich.console import Console

_OSC_ESCAPE_RE = re.compile(r"\x1b\][\s\S]*?(?:\x07|\x1b\\)")


class TuiConsole:
    """Drop-in Console.print() that renders above fixed-bottom input."""

    def __init__(self) -> None:
        self._buffer = StringIO()
        self._stream_buf = ""
        self._inner = Console(
            file=self._buffer,
            force_terminal=True,
            color_system="truecolor",
            highlight=False,
        )

    def print(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        self._buffer.seek(0)
        self._buffer.truncate()
        self._inner.width = shutil.get_terminal_size((80, 24)).columns
        self._inner.print(*args, **kwargs)
        output = _OSC_ESCAPE_RE.sub("", self._buffer.getvalue())
        for line in output.rstrip("\n").split("\n"):
            if line:
                print_formatted_text(ANSI(line))
            else:
                print_formatted_text("")

    def write_stream(self, text: str) -> None:
        """Buffer streaming assistant text; emit complete lines via prompt_toolkit."""
        if not text:
            return
        self._stream_buf += text
        while "\n" in self._stream_buf:
            line, self._stream_buf = self._stream_buf.split("\n", 1)
            self._emit_stream_line(line)

    def end_stream_line(self) -> None:
        """Flush any partial streaming buffer and finish the assistant block."""
        if self._stream_buf:
            self._emit_stream_line(self._stream_buf)
            self._stream_buf = ""
        else:
            print_formatted_text("")

    def _emit_stream_line(self, line: str) -> None:
        if line:
            print_formatted_text(line)
        else:
            print_formatted_text("")

    @contextmanager
    def status(self, *_args, **_kwargs):  # noqa: ANN002, ANN003
        yield self

    def clear(self) -> None:
        print_formatted_text("\x1b[2J\x1b[H")
