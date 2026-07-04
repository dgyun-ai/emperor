"""Welcome banner and startup status (Hermes hermes_cli/banner.py pattern)."""

from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING

from cli.skin import get_active_skin
from constants import PACKAGE_VERSION
from tools.registry import list_tools

if TYPE_CHECKING:
    from config.models import EmperorConfig
    from rich.console import Console


def _short_model(model: str) -> str:
    short = model.split("/")[-1] if "/" in model else model
    if len(short) > 28:
        return short[:25] + "..."
    return short


def build_welcome_banner(
    console: Console,
    *,
    config: EmperorConfig,
    session_id: str | None = None,
    tool_count: int | None = None,
) -> None:
    """Render a compact two-column welcome banner."""
    from rich.panel import Panel
    from rich.table import Table

    skin = get_active_skin()
    border = skin.get_color("banner_border", "yellow")
    title = skin.get_color("banner_title", "#FFD700")
    accent = skin.get_color("banner_accent", "cyan")
    dim = skin.get_color("banner_dim", "dim")
    ok = skin.get_color("ui_ok", "green")
    err = skin.get_color("ui_error", "red")

    model = _short_model(config.provider.model)
    cwd = os.getcwd()
    tools_n = tool_count if tool_count is not None else len(list_tools())
    toolsets = ", ".join(config.tools.enabled_toolsets) if config.tools.enabled_toolsets else "all"
    ctx = f"{config.agent.max_context_tokens:,}"

    api_ok = bool(config.provider.api_key)
    api_dot = f"[{ok}]●[/]" if api_ok else f"[{err}]●[/]"

    left = Table.grid(padding=(0, 1))
    left.add_column()
    agent = skin.get_branding("agent_name", "emperor")
    left.add_row(f"[bold {title}]{agent}[/] [dim]v{PACKAGE_VERSION}[/]")
    left.add_row(f"{api_dot} [bold]{model}[/] [dim {dim}]·[/] [dim {dim}]{ctx} ctx[/]")
    left.add_row(f"[dim {dim}]{cwd}[/]")
    if session_id:
        left.add_row(f"[dim {dim}]Session: {session_id[:8]}…[/]")

    right = Table.grid(padding=(0, 1))
    right.add_column()
    right.add_row(f"[bold {accent}]Tools[/] [dim]({tools_n})[/]")
    right.add_row(f"[dim {dim}]toolsets:[/] {toolsets}")
    right.add_row(f"[dim {dim}]provider:[/] {config.provider.provider}")
    right.add_row(f"[dim {dim}]skin:[/] {skin.name}")

    grid = Table.grid(padding=(0, 2))
    grid.add_column()
    grid.add_column()
    grid.add_row(left, right)

    console.print(
        Panel(
            grid,
            border_style=border,
            title=f"[bold {title}]{agent}[/]",
            subtitle=f"[dim {dim}]/help · /skin · Enter 发送[/]",
        )
    )


def build_compact_banner(console: Console, *, config: EmperorConfig) -> None:
    skin = get_active_skin()
    title = skin.get_color("banner_title", "#FFD700")
    ok = skin.get_color("ui_ok", "green")
    err = skin.get_color("ui_error", "red")
    model = _short_model(config.provider.model)
    api_ok = bool(config.provider.api_key)
    api_dot = f"[{ok}]●[/]" if api_ok else f"[{err}]●[/]"
    agent = skin.get_branding("agent_name", "emperor")
    console.print(
        f"[bold {title}]{agent}[/] {api_dot} [bold]{model}[/] "
        f"[dim]· {len(list_tools())} tools · skin:{skin.name} · /help[/]"
    )


def show_startup_banner(
    console: Console,
    *,
    config: EmperorConfig,
    session_id: str | None = None,
) -> None:
    width = shutil.get_terminal_size((80, 24)).columns
    if width < 72:
        build_compact_banner(console, config=config)
    else:
        build_welcome_banner(
            console,
            config=config,
            session_id=session_id,
        )


def format_status_bar(config: EmperorConfig, snapshot: dict) -> str:
    """One-line footer status (Hermes TUI status bar style)."""
    ctx = snapshot.get("context", {})
    session = snapshot.get("session", {})
    percent = ctx.get("percent")
    pct = f"{percent}%" if percent is not None else "--"
    model = _short_model(config.provider.model)
    used = ctx.get("used_tokens", 0)
    max_tokens = ctx.get("max_tokens", 0)
    total = session.get("total_tokens", 0)
    skin = get_active_skin().name
    return (
        f"⚜ {model} · ctx {used:,}/{max_tokens:,} ({pct}) · "
        f"session {total:,} tok · {skin}"
    )
