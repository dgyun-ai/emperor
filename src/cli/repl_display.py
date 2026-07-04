"""Claude Code–style terminal display for emperor chat (Rich spinner + tool blocks)."""

from __future__ import annotations

import json
import platform
from typing import TYPE_CHECKING, Any, Literal

from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner

from cli.chat_io import end_stream_line, flush_tty, stream_write
from cli.skin import get_active_skin
from i18n.locale import CliStrings, format_usage_line

if TYPE_CHECKING:
    from cli.tui_app import FixedBottomTui
    from cli.tui_console import TuiConsole

ToolProgressMode = Literal["off", "normal", "verbose"]

BULLET = "⏺" if platform.system() == "Darwin" else "●"


def _branch_char() -> str:
    return get_active_skin().tool_prefix or "⎿"


def _bullet_markup() -> str:
    color = get_active_skin().get_color("tool_bullet", "cyan")
    return f"[{color}]{BULLET}[/]"


_TOOL_DISPLAY: dict[str, str] = {
    "terminal_run": "Bash",
    "file_read": "Read",
    "file_write": "Write",
    "file_patch": "Edit",
    "file_search": "Grep",
    "web_search": "WebSearch",
    "web_extract": "WebFetch",
    "browser_fetch": "Browser",
    "todo": "Todo",
    "clarify": "Clarify",
    "echo": "Echo",
    "cron": "Cron",
    "execute_code": "Code",
    "memory": "Memory",
    "session_search": "Search",
    "delegate": "Agent",
}


def tool_display_name(name: str) -> str:
    return _TOOL_DISPLAY.get(name, name)


def format_tool_input_preview(name: str, input_data: dict[str, Any]) -> str:
    if not input_data:
        return ""
    if name == "terminal_run":
        return _truncate(str(input_data.get("command", "")), 120)
    path_keys = ("path", "file_path", "file", "directory")
    for key in path_keys:
        if key in input_data and input_data[key]:
            return str(input_data[key])
    if name == "web_search" and "query" in input_data:
        return _truncate(str(input_data["query"]), 80)
    if name == "clarify" and "question" in input_data:
        return _truncate(str(input_data["question"]), 80)
    for key, value in input_data.items():
        if isinstance(value, str) and value.strip():
            return _truncate(value, 80)
        if isinstance(value, (int, float, bool)):
            return f"{key}={value}"
    try:
        return _truncate(json.dumps(input_data, ensure_ascii=False), 80)
    except TypeError:
        return ""


def _truncate(text: str, max_len: int) -> str:
    one_line = " ".join(text.split())
    if len(one_line) <= max_len:
        return one_line
    return one_line[: max_len - 1] + "…"


def format_tool_result_preview(result: str, max_lines: int = 4, max_width: int = 200) -> list[str]:
    if not result or not result.strip():
        return []
    lines: list[str] = []
    for raw in result.strip().splitlines():
        line = raw.rstrip()
        if len(line) > max_width:
            line = line[: max_width - 1] + "…"
        lines.append(line)
        if len(lines) >= max_lines:
            remaining = len(result.strip().splitlines()) - max_lines
            if remaining > 0:
                lines.append(f"… (+{remaining} lines)")
            break
    return lines


class ReplDisplay:
    """Renders one assistant turn with progress, streaming text, and tool blocks."""

    def __init__(
        self,
        console: Console | TuiConsole,
        strings: CliStrings,
        *,
        tool_progress: ToolProgressMode = "normal",
        tui: FixedBottomTui | None = None,
    ) -> None:
        self.console = console
        self.strings = strings
        self.tool_progress = tool_progress
        self._tui = tui
        self._use_rich_live = tui is None and not _is_tui_console(console)
        self._live: Live | None = None
        self._assistant_streaming = False
        self._streamed_any = False
        self._last_usage: str | None = None
        self._status_bar: str | None = None
        self._last_phase = ""
        self._stream_chars = 0

    def has_streamed(self) -> bool:
        return self._streamed_any

    def begin_turn(self) -> None:
        self._last_usage = None
        self._streamed_any = False
        self._stream_chars = 0
        self.log_phase(self.strings.phase_connecting)

    def log_phase(self, text: str) -> None:
        if not text or text == self._last_phase:
            return
        self._last_phase = text
        self.console.print(f"[dim]⋯ {text}[/dim]")
        if self._tui is not None:
            self._tui.set_spinner(text)
        elif self._use_rich_live:
            self.start_spinner(text)

    def start_spinner(self, text: str) -> None:
        if not self._use_rich_live:
            if self._tui is not None:
                self._tui.set_spinner(text)
            return
        self.stop_spinner()
        self._live = Live(
            Spinner("dots", text=text, style="dim"),
            console=self.console,  # type: ignore[arg-type]
            transient=True,
            refresh_per_second=12,
        )
        self._live.start()

    def stop_spinner(self) -> None:
        if self._live is not None:
            self._live.stop()
            self._live = None
        if self._tui is not None:
            self._tui.set_spinner("")

    def write_delta(self, delta: str) -> None:
        if not delta:
            return
        self.stop_spinner()
        self._streamed_any = True
        self._stream_chars += len(delta)
        if not self._assistant_streaming:
            self._begin_assistant_stream()
        if _is_tui_console(self.console):
            self.console.write_stream(delta)  # type: ignore[union-attr]
        else:
            stream_write(delta)

    def write_complete_message(self, text: str) -> None:
        if not text:
            return
        if self._stream_chars > 0:
            return
        self.stop_spinner()
        self._streamed_any = True
        self._stream_chars = len(text)
        self._begin_assistant_stream()
        if _is_tui_console(self.console):
            self.console.write_stream(text)  # type: ignore[union-attr]
        else:
            stream_write(text)

    def _begin_assistant_stream(self) -> None:
        if not self._assistant_streaming:
            self.console.print()
            self._assistant_streaming = True

    def finish_assistant_text(self) -> None:
        if not self._assistant_streaming:
            return
        if _is_tui_console(self.console):
            self.console.end_stream_line()  # type: ignore[union-attr]
        else:
            end_stream_line()
        self._assistant_streaming = False

    def print_tool_invoke(self, name: str, input_data: dict[str, Any]) -> None:
        self.finish_assistant_text()
        display = tool_display_name(name)
        preview = format_tool_input_preview(name, input_data)
        phase = self.strings.tool_running.format(name=display)
        if preview:
            phase = f"{phase} — {preview}"
        self.log_phase(phase)

        if self.tool_progress == "off":
            return

        if self.tool_progress == "verbose":
            preview_text = _truncate(json.dumps(input_data, ensure_ascii=False), 200)
        else:
            preview_text = preview
        detail = f"({preview_text})" if preview_text else ""
        self.console.print(f"{_bullet_markup()} [bold]{display}[/bold]{detail}")

    def print_tool_result(self, name: str, result: str) -> None:
        self.stop_spinner()
        if self.tool_progress == "off":
            self.log_phase(self.strings.thinking_spinner)
            return
        max_lines = 8 if self.tool_progress == "verbose" else 4
        lines = format_tool_result_preview(result, max_lines=max_lines)
        branch = _branch_char()
        if not lines:
            self.console.print(f"[dim]{branch} {self.strings.tool_no_output}[/dim]")
        else:
            for i, line in enumerate(lines):
                prefix = branch if i == 0 else " "
                self.console.print(f"[dim]{prefix} {line}[/dim]")
        self.log_phase(self.strings.thinking_spinner)

    def set_status_bar(self, line: str) -> None:
        self._status_bar = line

    def print_usage(self, snapshot: dict[str, Any]) -> None:
        self._last_usage = format_usage_line(self.strings, snapshot)

    def end_turn(self, *, show_usage: bool = True) -> None:
        self.finish_assistant_text()
        self.stop_spinner()
        if show_usage and self._last_usage:
            self.console.print(f"[dim]{self._last_usage}[/dim]")
        if self._status_bar:
            self.console.print(f"[dim italic]{self._status_bar}[/dim italic]")
        flush_tty()


def _is_tui_console(console: object) -> bool:
    return console.__class__.__name__ == "TuiConsole"
