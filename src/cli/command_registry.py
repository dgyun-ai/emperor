"""Slash command registry — single source of truth (Hermes hermes_cli/commands.py pattern)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandDef:
    name: str
    description: str
    category: str
    aliases: tuple[str, ...] = ()
    args_hint: str = ""
    cli_only: bool = False


COMMAND_REGISTRY: list[CommandDef] = [
    CommandDef("help", "Show available slash commands", "Info", aliases=("h",)),
    CommandDef("new", "Start a new session", "Session", aliases=("reset",), args_hint="[title]"),
    CommandDef("clear", "Clear screen (keep current session)", "Session", cli_only=True),
    CommandDef("resume", "Resume a previous session", "Session", args_hint="[session-id]"),
    CommandDef("sessions", "Browse and resume previous sessions", "Session", cli_only=True),
    CommandDef("search", "Search session messages (FTS)", "Session", args_hint="<query>"),
    CommandDef("status", "Show session info (model, tokens, duration)", "Session"),
    CommandDef("usage", "Show token/context usage", "Session"),
    CommandDef("compress", "Compress conversation context", "Session", args_hint="[N]"),
    CommandDef("model", "Show current model and provider", "Configuration"),
    CommandDef("skin", "Show or switch CLI skin/theme", "Configuration", args_hint="[name]", cli_only=True),
    CommandDef("verbose", "Cycle tool display: off → normal → verbose", "Configuration", cli_only=True),
    CommandDef(
        "statusbar",
        "Toggle persistent status bar after each turn",
        "Configuration",
        cli_only=True,
        aliases=("sb",),
    ),
    CommandDef("stop", "Hint for aborting the current turn (Ctrl+C)", "Session"),
    CommandDef("quit", "Exit the chat", "Exit", aliases=("exit", "q")),
]


def _build_lookup() -> dict[str, CommandDef]:
    lookup: dict[str, CommandDef] = {}
    for cmd in COMMAND_REGISTRY:
        lookup[cmd.name] = cmd
        for alias in cmd.aliases:
            lookup[alias] = cmd
    return lookup


_COMMAND_LOOKUP = _build_lookup()


def resolve_command(name: str) -> CommandDef | None:
    return _COMMAND_LOOKUP.get(name.lower().lstrip("/"))


def format_help_text(*, locale: str | None = None) -> str:
    from i18n.locale import normalize_locale

    zh = normalize_locale(locale) == "zh"
    lines: list[str] = []
    lines.append("命令：" if zh else "Commands:")
    by_cat: dict[str, list[CommandDef]] = {}
    for cmd in COMMAND_REGISTRY:
        by_cat.setdefault(cmd.category, []).append(cmd)
    for category, cmds in by_cat.items():
        lines.append("")
        lines.append(f"  [{category}]")
        for cmd in cmds:
            aliases = f" ({', '.join('/' + a for a in cmd.aliases)})" if cmd.aliases else ""
            hint = f" {cmd.args_hint}" if cmd.args_hint else ""
            lines.append(f"    /{cmd.name}{hint}{aliases} — {cmd.description}")
    lines.append("")
    lines.append("  exit — 退出" if zh else "  exit — quit")
    return "\n".join(lines)


def completion_candidates(prefix: str) -> list[str]:
    """Return slash command names matching prefix (without leading /)."""
    return [name for name, _ in completion_items(prefix)]


def completion_items(prefix: str) -> list[tuple[str, str]]:
    """Return (command_name, description) pairs for completion menu."""
    prefix = prefix.lstrip("/").lower()
    items: list[tuple[str, str]] = []
    seen: set[str] = set()
    for cmd in COMMAND_REGISTRY:
        names = (cmd.name, *cmd.aliases)
        if prefix and not any(n.startswith(prefix) for n in names):
            continue
        if cmd.name in seen:
            continue
        seen.add(cmd.name)
        items.append((cmd.name, cmd.description))
    return sorted(items, key=lambda x: x[0])
