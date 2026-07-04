"""Full-screen REPL with bottom-fixed input (Hermes CLI Application layout)."""

from __future__ import annotations

import asyncio
import shutil
import sys
from typing import TYPE_CHECKING

from prompt_toolkit.application import Application
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import ConditionalContainer, HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import TextArea

from cli.banner import show_startup_banner
from cli.chat_io import normalize_user_command
from cli.commands import SlashCommandContext, handle_slash_command
from cli.prompt import SlashCommandCompleter
from cli.skin import build_prompt_toolkit_style, get_active_skin, get_prompt_symbol
from cli.tui_console import TuiConsole
from constants import get_emperor_home

if TYPE_CHECKING:
    from cli.repl import ChatRepl


class FixedBottomTui:
    """prompt_toolkit Application with input pinned to the bottom."""

    def __init__(self, repl: ChatRepl) -> None:
        self.repl = repl
        self._console = TuiConsole()
        self._submit_queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._should_exit = False
        self._agent_running = False
        self._spinner_text = ""
        self._status_fragments: list[tuple[str, str]] = []
        self._status_visible = repl.statusbar_visible
        self._input_area: TextArea | None = None
        self._app: Application | None = None
        self._consumer_task: asyncio.Task[None] | None = None
        self._line_future: asyncio.Future[str] | None = None

        home = get_emperor_home(repl.profile)
        home.mkdir(parents=True, exist_ok=True)

    async def run(self) -> int:
        if not sys.stdin.isatty():
            return await self.repl.run_simple_loop()

        await self.repl.store.initialize()
        self.repl._setup_clarify_handler(self._console, self.read_line)
        resumed = await self.repl.maybe_auto_resume()

        self._app = self._build_application()
        self._consumer_task = asyncio.create_task(self._consume_submissions())

        # Single patch_stdout for banner + entire interactive session.
        with patch_stdout():
            show_startup_banner(
                self._console,
                config=self.repl.config,
                session_id=self.repl.engine.session_id,
            )
            skin = get_active_skin()
            welcome = skin.get_branding("welcome", self.repl.strings.welcome_hint)
            self._console.print(f"[dim]{welcome}[/dim]")
            self._console.print(
                f"[dim]{self.repl.strings.chat_banner} · skin: {skin.name}[/dim]"
            )
            self._console.print(f"[dim]{self.repl.strings.input_hint}[/dim]")
            if resumed:
                self._console.print(
                    f"[dim]{self.repl.strings.resumed_session.format(session_id=resumed[:8])}[/dim]"
                )
            self._console.print()

            try:
                await self._app.run_async()
            finally:
                await self._submit_queue.put(None)
                if self._consumer_task:
                    await self._consumer_task
        return 0

    def _enqueue_submit(self, text: str) -> None:
        loop = asyncio.get_running_loop()
        loop.create_task(self._submit_queue.put(text))

    def _submit_input(self) -> None:
        if self._agent_running or self._input_area is None:
            return
        text = self._input_area.buffer.text.strip()
        if not text:
            return
        self._input_area.buffer.text = ""
        self._enqueue_submit(text)

    def _maybe_show_slash_completions(self) -> None:
        if self._input_area is None or self._agent_running:
            return
        text = self._input_area.buffer.text
        if text.startswith("/") and " " not in text[1:]:
            self._input_area.buffer.start_completion(select_first=False)

    def _build_application(self) -> Application:
        kb = KeyBindings()
        completer = SlashCommandCompleter()

        def get_prompt() -> FormattedText:
            symbol = get_prompt_symbol(self.repl.strings.you_prompt.strip())
            style = "class:prompt-working" if self._agent_running else "class:prompt"
            return FormattedText([(style, symbol)])

        self._input_area = TextArea(
            height=Dimension(min=1, max=4, preferred=1),
            prompt=get_prompt,
            multiline=False,
            wrap_lines=True,
            style="class:input-area",
            read_only=Condition(lambda: self._agent_running),
            completer=completer,
            complete_while_typing=True,
            focus_on_click=True,
        )
        self._input_area.buffer.on_text_changed += lambda _: self._maybe_show_slash_completions()

        @kb.add("enter")
        def submit(event) -> None:  # type: ignore[no-untyped-def]
            if event.app.layout.has_focus(self._input_area):
                self._submit_input()

        @kb.add("c-j")
        def submit_ctrl_j(event) -> None:  # type: ignore[no-untyped-def]
            self._submit_input()

        @kb.add("c-c")
        def interrupt(event) -> None:  # type: ignore[no-untyped-def]
            if self._agent_running:
                self._spinner_text = self.repl.strings.stop_hint
                self._invalidate()
            elif self._line_future is not None and not self._line_future.done():
                # Nested read (e.g. /sessions picker) — abort picker, keep REPL running.
                self._line_future.set_result("")
                self._line_future = None
                self._invalidate()
            else:
                self._should_exit = True
                event.app.exit()

        @kb.add("c-d")
        def eof(event) -> None:  # type: ignore[no-untyped-def]
            if self._input_area and not self._input_area.buffer.text:
                self._should_exit = True
                event.app.exit()

        def spinner_line() -> FormattedText:
            if not self._spinner_text:
                return FormattedText([])
            return FormattedText([("class:spinner", f" {self._spinner_text}")])

        def status_line() -> FormattedText:
            return FormattedText(self._status_fragments or [("class:status-bar-dim", " ")])

        def input_rule() -> FormattedText:
            width = shutil.get_terminal_size((80, 24)).columns
            return FormattedText([("class:input-rule", "─" * max(10, width))])

        spinner_widget = ConditionalContainer(
            Window(content=FormattedTextControl(spinner_line), height=1),
            filter=Condition(lambda: bool(self._spinner_text)),
        )

        status_widget = ConditionalContainer(
            Window(content=FormattedTextControl(status_line), height=1, wrap_lines=False),
            filter=Condition(lambda: self._status_visible and bool(self._status_fragments)),
        )

        rule_top = Window(content=FormattedTextControl(input_rule), height=1)
        rule_bot = Window(content=FormattedTextControl(input_rule), height=1)
        completions_menu = CompletionsMenu(max_height=12, scroll_offset=1)

        layout = Layout(
            HSplit(
                [
                    Window(height=Dimension(weight=1)),
                    spinner_widget,
                    status_widget,
                    rule_top,
                    self._input_area,
                    completions_menu,
                    rule_bot,
                ]
            )
        )

        return Application(
            layout=layout,
            key_bindings=kb,
            style=Style.from_dict(build_prompt_toolkit_style()),
            full_screen=False,
            mouse_support=False,
            erase_when_done=False,
        )

    async def read_line(self) -> str:
        loop = asyncio.get_running_loop()
        self._line_future = loop.create_future()
        self._invalidate()
        try:
            return await self._line_future
        except asyncio.CancelledError:
            self._line_future = None
            return ""

    async def _consume_submissions(self) -> None:
        while True:
            text = await self._submit_queue.get()
            if text is None:
                break
            await self._handle_user_input(text)

    async def _handle_user_input(self, user_input: str) -> None:
        if self._line_future and not self._line_future.done():
            self._line_future.set_result(user_input)
            self._line_future = None
            return

        user_input = normalize_user_command(user_input.strip())
        if not user_input:
            return
        if user_input.lower() in {"exit", "quit"}:
            self._should_exit = True
            if self._app:
                self._app.exit()
            return

        if user_input.startswith("/"):
            ctx = SlashCommandContext(
                repl=self.repl,
                engine=self.repl.engine,
                store=self.repl.store,
                console=self._console,  # type: ignore[arg-type]
                profile=self.repl.profile,
                locale=self.repl.config.ui.language,
            )
            handled = await handle_slash_command(user_input, ctx)
            if handled is False:
                self._console.print(f"[yellow]{self.repl.strings.unknown_command}[/yellow]")
            self._invalidate()
            return

        self.repl._last_user_message = user_input
        await self.repl.run_turn(user_input, console=self._console, tui=self)

    def set_agent_running(self, running: bool) -> None:
        self._agent_running = running
        if not running:
            self._spinner_text = ""
        self._invalidate()

    def set_spinner(self, text: str) -> None:
        self._spinner_text = text
        self._invalidate()

    def set_status_bar(self, text: str) -> None:
        if not text:
            self._status_fragments = []
        else:
            self._status_fragments = [("class:status-bar", f" {text} ")]
        self._invalidate()

    def refresh_styles(self) -> None:
        if self._app:
            self._app.style = Style.from_dict(build_prompt_toolkit_style())
        self._invalidate()

    def _invalidate(self) -> None:
        if self._app:
            self._app.invalidate()
