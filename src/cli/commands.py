"""Slash command handlers — dispatches via command_registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from rich.console import Console

from cli.command_registry import format_help_text, resolve_command
from i18n.locale import format_usage_line, get_cli_strings
from session.time_util import format_local_timestamp, format_session_age

if TYPE_CHECKING:
    from cli.repl import ChatRepl
    from engine.query_engine import QueryEngine
    from session.store import SessionStore


@dataclass
class SlashCommandContext:
    repl: ChatRepl | None
    engine: QueryEngine
    store: SessionStore
    console: Console
    profile: str = "default"
    locale: str | None = None


async def handle_slash_command(cmd: str, ctx: SlashCommandContext) -> bool:
    """Handle slash command. Returns True if handled."""
    strings = get_cli_strings(ctx.locale or ctx.engine.config.ui.language)
    parts = cmd.strip().split(maxsplit=1)
    raw_name = parts[0].lstrip("/")
    arg = parts[1].strip() if len(parts) > 1 else ""

    command = resolve_command(raw_name)
    if command is None:
        return False

    name = command.name

    if name == "help":
        ctx.console.print(format_help_text(locale=ctx.locale))
        return True

    if name == "model":
        cfg = ctx.engine.config
        ctx.console.print(f"[dim]{strings.provider_label}:[/dim] {cfg.provider.provider}")
        ctx.console.print(f"[dim]{strings.model_label}:[/dim] {cfg.provider.model}")
        ctx.console.print(f"[dim]{strings.base_url_label}:[/dim] {cfg.provider.base_url}")
        ctx.console.print(
            f"[dim]{strings.max_context_label}:[/dim] {cfg.agent.max_context_tokens}"
        )
        ctx.console.print(f"[dim]language:[/dim] {cfg.agent.language}")
        return True

    if name == "skin":
        from cli.skin import format_skin_list, get_active_skin_name, set_active_skin

        if not arg:
            ctx.console.print(format_skin_list(active=get_active_skin_name(), locale=ctx.locale))
            return True
        set_active_skin(arg, profile=ctx.profile)
        if ctx.repl and ctx.repl._tui_ref:
            ctx.repl._tui_ref.refresh_styles()
        ctx.console.print(f"[green]{strings.skin_switched.format(name=arg)}[/green]")
        return True

    if name == "new":
        title = arg or None
        session_id = await ctx.engine.new_session(title=title)
        msg = strings.new_session.format(session_id=session_id[:8])
        ctx.console.print(f"[green]{msg}[/green]")
        return True

    if name == "clear":
        if hasattr(ctx.console, "clear"):
            ctx.console.clear()
        elif ctx.repl is not None:
            await ctx.repl.clear_screen()
        return True

    if name == "resume":
        await ctx.store.initialize()
        if arg:
            await ctx.engine.resume_session(arg)
            ctx.console.print(f"[green]{strings.resumed_session.format(session_id=arg[:8])}[/green]")
        else:
            latest = await ctx.store.get_latest_session(profile=ctx.profile)
            if latest:
                await ctx.engine.resume_session(latest)
                ctx.console.print(f"[green]{strings.resumed_session.format(session_id=latest[:8])}[/green]")
            else:
                ctx.console.print(f"[yellow]{strings.no_sessions}[/yellow]")
        return True

    if name == "sessions":
        await _pick_session(ctx)
        return True

    if name == "search":
        query = arg or cmd.replace("/search", "").strip()
        if not query:
            ctx.console.print(f"[yellow]{strings.search_usage}[/yellow]")
            return True
        await ctx.store.initialize()
        results = await ctx.store.search_messages(query, limit=10)
        if not results:
            ctx.console.print(f"[dim]{strings.no_results}[/dim]")
        for r in results:
            content = (r.get("content") or "")[:120]
            ctx.console.print(f"  [{r.get('session_id', '?')[:8]}] {content}")
        return True

    if name in {"status", "usage"}:
        await ctx.engine.initialize()
        snap = ctx.engine.current_usage_snapshot()
        ctx.console.print(format_usage_line(strings, snap))
        sid = ctx.engine.session_id or "?"
        ctx.console.print(f"[dim]session:[/dim] {sid[:8]}… · [dim]messages:[/dim] {len(ctx.engine.messages)}")
        return True

    if name == "compress":
        protect = int(arg) if arg.isdigit() else None
        summary = await ctx.engine.compress_context(protect_last_n=protect)
        ctx.console.print(f"[green]{strings.compressed.format(summary=summary[:80])}[/green]")
        return True

    if name == "verbose":
        if ctx.repl is None:
            ctx.console.print(f"[yellow]{strings.cli_only_command}[/yellow]")
            return True
        mode = ctx.repl.cycle_tool_progress()
        labels = {
            "off": strings.verbose_off,
            "normal": strings.verbose_normal,
            "verbose": strings.verbose_verbose,
        }
        ctx.console.print(labels.get(mode, mode))
        return True

    if name == "statusbar":
        if ctx.repl is None:
            ctx.console.print(f"[yellow]{strings.cli_only_command}[/yellow]")
            return True
        visible = ctx.repl.toggle_statusbar()
        ctx.console.print(
            strings.statusbar_on if visible else strings.statusbar_off
        )
        return True

    if name == "stop":
        ctx.console.print(f"[yellow]{strings.stop_hint}[/yellow]")
        return True

    if name in {"quit", "exit"}:
        return True

    return False


async def _pick_session(ctx: SlashCommandContext) -> None:
    strings = get_cli_strings(ctx.locale)
    await ctx.store.initialize()
    sessions = await ctx.store.list_sessions(profile=ctx.profile, limit=20)
    sessions = await ctx.store.backfill_missing_titles(
        sessions,
        language=ctx.locale or ctx.engine.config.ui.language,
    )
    if not sessions:
        ctx.console.print(f"[yellow]{strings.no_sessions}[/yellow]")
        return

    ctx.console.print(strings.sessions_header)
    for i, s in enumerate(sessions, start=1):
        title = s.title or strings.session_untitled
        local_time = format_local_timestamp(s.updated_at)
        age = format_session_age(s.updated_at)
        if s.message_count:
            msgs = strings.session_message_count.format(count=s.message_count)
        else:
            msgs = strings.session_empty_label
        ctx.console.print(
            f"  {i:2}. {s.id[:8]}…  {title[:36]}  "
            f"[dim]{msgs} · {local_time} · {age}[/dim]"
        )

    if ctx.repl is None:
        ctx.console.print(f"[dim]{strings.sessions_resume_hint}[/dim]")
        return

    ctx.console.print(f"[dim]{strings.sessions_pick_prompt.strip()}[/dim]")
    choice = await ctx.repl.read_user_line(strings.sessions_pick_prompt)
    choice = choice.strip()
    if not choice:
        return
    session_id: str | None = None
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(sessions):
            session_id = sessions[idx].id
    else:
        for s in sessions:
            if s.id.startswith(choice) or (s.title and choice in s.title):
                session_id = s.id
                break
    if session_id:
        await ctx.engine.resume_session(session_id)
        ctx.console.print(f"[green]{strings.resumed_session.format(session_id=session_id[:8])}[/green]")
    else:
        ctx.console.print(f"[yellow]{strings.no_results}[/yellow]")
