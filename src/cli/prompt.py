"""prompt_toolkit input session with slash-command autocomplete (Hermes CLI pattern)."""

from __future__ import annotations

from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style

from cli.command_registry import completion_items
from cli.skin import build_prompt_toolkit_style
from constants import get_emperor_home


class SlashCommandCompleter(Completer):
    """Tab-complete slash commands while typing."""

    def get_completions(self, document: Document, complete_event):  # type: ignore[no-untyped-def]
        text = document.text_before_cursor
        if not text.startswith("/"):
            return
        token = text[1:]
        if " " in token:
            return
        for name, description in completion_items(token):
            yield Completion(
                name,
                start_position=-len(token),
                display=f"/{name}",
                display_meta=description,
            )


def create_prompt_session(
    *,
    profile: str | None = None,
    placeholder: str = "",
) -> PromptSession[str]:
    home = get_emperor_home(profile)
    home.mkdir(parents=True, exist_ok=True)
    history_path = Path(home) / "cli_history"
    style = Style.from_dict(build_prompt_toolkit_style())
    return PromptSession(
        history=FileHistory(str(history_path)),
        completer=SlashCommandCompleter(),
        complete_while_typing=True,
        style=style,
        placeholder=placeholder or None,
    )


def read_prompt(session: PromptSession[str], prompt_text: str) -> str:
    """Read one line from the prompt session (sync — call via asyncio.to_thread)."""
    return session.prompt([("class:prompt", prompt_text)])
