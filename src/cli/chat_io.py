"""Terminal I/O for emperor chat — avoids Rich stream + input cursor bugs."""

from __future__ import annotations

import sys

from rich.console import Console


def flush_tty() -> None:
    """Flush stdout/stderr so the next prompt redraws cleanly."""
    sys.stdout.flush()
    sys.stderr.flush()


def stream_write(text: str) -> None:
    """Write streaming assistant text via raw stdout (not Rich print)."""
    sys.stdout.write(text)
    flush_tty()


def end_stream_line() -> None:
    """Finish a streaming assistant line."""
    sys.stdout.write("\n")
    flush_tty()


def read_user_line(console: Console, prompt: str) -> str:
    """Read user input after flushing prior stream output."""
    flush_tty()
    return console.input(f"[bold green]{prompt}[/bold green]")


def normalize_user_command(text: str) -> str:
    """Map common bare words to slash commands."""
    stripped = text.strip()
    lower = stripped.lower()
    if lower in {"help", "h", "?"}:
        return "/help"
    if lower in {"exit", "quit", "q"}:
        return "exit"
    return stripped
