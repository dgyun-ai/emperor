"""Interactive chat REPL — Hermes hermes_cli + fixed-bottom TUI."""

from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING

from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console

from cli.banner import format_status_bar, show_startup_banner
from cli.chat_io import flush_tty, normalize_user_command
from cli.commands import SlashCommandContext, handle_slash_command
from cli.prompt import create_prompt_session, read_prompt
from cli.repl_display import ReplDisplay, ToolProgressMode
from cli.skin import get_prompt_symbol, init_skin_from_config
from config.models import EmperorConfig
from engine.query_engine import QueryEngine
from i18n.locale import CliStrings, get_cli_strings
from session.store import SessionStore
from tools.clarify import set_clarify_handler

if TYPE_CHECKING:
    from cli.tui_app import FixedBottomTui
    from cli.tui_console import TuiConsole

ToolProgressCycle = ("off", "normal", "verbose")


class ChatRepl:
    """Hermes-style interactive CLI loop."""

    def __init__(
        self,
        *,
        engine: QueryEngine,
        config: EmperorConfig,
        profile: str | None,
        console: Console | None = None,
    ) -> None:
        self.engine = engine
        self.config = config
        self.profile = profile or "default"
        self.console = console or Console()
        self.strings = get_cli_strings(config.ui.language)
        self.store = SessionStore.for_profile(self.profile)
        self.tool_progress: ToolProgressMode = "normal"
        self.statusbar_visible = True
        self._last_user_message = ""
        self._prompt = create_prompt_session(
            profile=self.profile,
            placeholder=self.strings.input_placeholder,
        )
        self._tui_ref: FixedBottomTui | None = None
        init_skin_from_config(config, profile=self.profile)

    async def maybe_auto_resume(self) -> str | None:
        """Resume the latest non-empty session when configured."""
        if not self.config.ui.continue_last_session:
            return None
        if self.engine.session_id and self.engine.messages:
            return self.engine.session_id
        await self.store.initialize()
        latest = await self.store.get_latest_session(profile=self.profile)
        if not latest:
            return None
        await self.engine.resume_session(latest)
        return latest

    async def run(self) -> int:
        use_fixed = self.config.ui.fixed_input and sys.stdin.isatty()
        if use_fixed:
            from cli.tui_app import FixedBottomTui

            tui = FixedBottomTui(self)
            self._tui_ref = tui
            return await tui.run()
        return await self.run_simple_loop()

    async def run_simple_loop(self) -> int:
        await self.store.initialize()
        self._setup_clarify_handler()
        resumed = await self.maybe_auto_resume()

        show_startup_banner(
            self.console,
            config=self.config,
            session_id=self.engine.session_id,
        )
        if resumed:
            self.console.print(
                f"[dim]{self.strings.resumed_session.format(session_id=resumed[:8])}[/dim]"
            )
        self.console.print(f"[dim]{self.strings.welcome_hint}[/dim]")
        self.console.print(f"[dim]{self.strings.chat_banner}[/dim]")
        self.console.print()

        while True:
            try:
                user_input = await asyncio.to_thread(
                    read_prompt,
                    self._prompt,
                    self.strings.you_prompt,
                )
            except (EOFError, KeyboardInterrupt):
                self.console.print()
                break

            user_input = normalize_user_command(user_input.strip())
            if not user_input:
                continue
            if user_input.lower() in {"exit", "quit"}:
                break

            if user_input.startswith("/"):
                ctx = SlashCommandContext(
                    repl=self,
                    engine=self.engine,
                    store=self.store,
                    console=self.console,
                    profile=self.profile,
                    locale=self.config.ui.language,
                )
                handled = await handle_slash_command(user_input, ctx)
                if handled is False:
                    self.console.print(f"[yellow]{self.strings.unknown_command}[/yellow]")
                continue

            self._last_user_message = user_input
            await self.run_turn(user_input)

        return 0

    async def run_single(
        self,
        message: str,
        *,
        quiet: bool = False,
    ) -> int:
        await self.store.initialize()
        if quiet:
            try:
                text = await self.engine.chat(message)
                print(text, end="" if text.endswith("\n") else "\n")
                return 0
            except Exception as exc:
                print(f"{self.strings.error_prefix}{exc}", file=sys.stderr)
                return 1

        with patch_stdout():
            await self.run_turn(message)
        return 0

    async def run_turn(
        self,
        message: str,
        *,
        console: Console | TuiConsole | None = None,
        tui: FixedBottomTui | None = None,
    ) -> None:
        from cli.tui_console import TuiConsole

        out: Console | TuiConsole = console or self.console
        display = ReplDisplay(
            out,  # type: ignore[arg-type]
            self.strings,
            tool_progress=self.tool_progress,
            tui=tui,
        )

        if tui:
            tui.set_agent_running(True)

        self._print_user_message(out, message)
        display.begin_turn()
        async for event in self.engine.submit_message(message):
            if event.kind == "stream_delta":
                display.write_delta(event.payload)
            elif event.kind == "tool_start":
                payload = event.payload
                display.print_tool_invoke(
                    payload.get("name", "?"),
                    payload.get("input") or {},
                )
            elif event.kind == "tool_end":
                payload = event.payload
                display.print_tool_result(
                    payload.get("name", "?"),
                    str(payload.get("result", "")),
                )
            elif event.kind == "usage_update":
                display.print_usage(event.payload)
                if self.statusbar_visible:
                    bar = format_status_bar(self.config, event.payload)
                    display.set_status_bar(bar)
                    if tui:
                        tui.set_status_bar(bar)
            elif event.kind == "status" and "terminal" in event.payload:
                terminal = event.payload["terminal"]
                reason = terminal.get("reason")
                if reason == "complete":
                    display.write_complete_message(terminal.get("message") or "")
                elif reason == "error":
                    display.stop_spinner()
                    out.print(f"[red]{self.strings.error_prefix}[/red]{terminal.get('error')}")
                elif reason == "max_iterations":
                    display.stop_spinner()
                    out.print(
                        f"[yellow]{self.strings.stopped_prefix}[/yellow]{terminal.get('error')}"
                    )
                elif reason == "loop_detected":
                    display.stop_spinner()
                    out.print(
                        f"[yellow]{self.strings.stopped_prefix}[/yellow]{terminal.get('message') or ''}"
                    )

        display.end_turn(show_usage=not self.statusbar_visible)

        if tui:
            tui.set_agent_running(False)
            tui.set_spinner("")
        flush_tty()

    def _print_user_message(self, out: Console | TuiConsole, message: str) -> None:
        symbol = get_prompt_symbol(self.strings.you_prompt.strip())
        out.print(f"[bold green]{symbol.rstrip()}[/bold green] {message}")

    async def read_user_line(self, prompt: str | None = None) -> str:
        """Read one line — bottom input in TUI, PromptSession in simple loop."""
        if self._tui_ref is not None:
            return await self._tui_ref.read_line()
        return await asyncio.to_thread(
            read_prompt,
            self._prompt,
            prompt or self.strings.you_prompt,
        )

    def cycle_tool_progress(self) -> ToolProgressMode:
        idx = ToolProgressCycle.index(self.tool_progress)
        self.tool_progress = ToolProgressCycle[(idx + 1) % len(ToolProgressCycle)]  # type: ignore[assignment]
        return self.tool_progress

    def toggle_statusbar(self) -> bool:
        self.statusbar_visible = not self.statusbar_visible
        return self.statusbar_visible

    async def clear_screen(self) -> None:
        self.console.clear()
        show_startup_banner(
            self.console,
            config=self.config,
            session_id=self.engine.session_id,
        )

    def _setup_clarify_handler(
        self,
        console: Console | TuiConsole | None = None,
        read_line: object | None = None,
    ) -> None:
        from cli.tui_console import TuiConsole

        strings = self.strings
        out = console or self.console
        prompt = self._prompt

        async def clarify_handler(question: str, options: list[str]) -> str:
            out.print(f"[cyan]{strings.clarify_prefix}[/cyan]{question}")
            if options:
                for i, opt in enumerate(options, start=1):
                    out.print(f"  {i}. {opt}")
            if read_line is not None and callable(read_line):
                result = read_line()
                if asyncio.iscoroutine(result):
                    return await result
                return str(result)
            return await asyncio.to_thread(read_prompt, prompt, strings.you_prompt)

        set_clarify_handler(clarify_handler)


class nullcontext:
    def __enter__(self):  # noqa: ANN204
        return None

    def __exit__(self, *args):  # noqa: ANN204, ANN002
        return False
