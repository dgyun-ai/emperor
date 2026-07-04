"""emperor CLI entry point."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time

from rich.console import Console

from agent.deps import AgentDeps
from constants import ENV_EMPEROR_PROFILE, PACKAGE_VERSION as __version__
from config.loader import load_config
from config.models import EmperorConfig
from engine.query_engine import QueryEngine
from logging_setup import setup_logging
from provider.runtime import build_provider
from session.store import SessionStore
from i18n.locale import get_cli_strings
from tools.registry import discover_tools

import tools.builtin  # noqa: F401 — register built-in tools


def main(argv: list[str] | None = None) -> int:
    """CLI entry: emperor [chat] or subcommands."""
    try:
        return asyncio.run(_async_main(argv))
    except KeyboardInterrupt:
        return 130


async def _async_main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    profile = args.profile or os.environ.get(ENV_EMPEROR_PROFILE)
    if args.command is None:
        args.command = "chat"

    config = load_config(profile=profile)
    setup_logging(config.log_level)
    discover_tools()

    handlers = {
        "config": _cmd_config,
        "chat": _cmd_chat,
        "session": _cmd_session,
        "gateway": _cmd_gateway,
        "api": _cmd_api,
        "batch": _cmd_batch,
        "acp": _cmd_acp,
        "kanban": _cmd_kanban,
        "dashboard": _cmd_dashboard,
    }
    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        return 0
    return await handler(config, args, profile)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="emperor",
        description="emperor autonomous agent (Hermes-style CLI)",
    )
    parser.add_argument("-p", "--profile", help="Profile name for isolated EMPEROR_HOME")
    parser.add_argument("--version", action="version", version=f"emperor {__version__}")

    sub = parser.add_subparsers(dest="command")

    config_parser = sub.add_parser("config", help="Configuration commands")
    config_sub = config_parser.add_subparsers(dest="config_cmd")
    config_sub.add_parser("show", help="Show effective configuration")

    chat_parser = sub.add_parser(
        "chat",
        help="Interactive chat (default when no subcommand)",
    )
    chat_parser.add_argument("message", nargs="?", help="Optional single-turn message")
    chat_parser.add_argument("-q", "--query", dest="query", help="One-shot query (non-interactive)")
    chat_parser.add_argument(
        "-Q",
        "--quiet",
        action="store_true",
        help="With -q: print final response only (scripting mode)",
    )

    session_parser = sub.add_parser("session", help="Session management")
    session_sub = session_parser.add_subparsers(dest="session_cmd")
    session_sub.add_parser("list", help="List sessions")
    export_parser = session_sub.add_parser("export", help="Export session as JSONL")
    export_parser.add_argument("session_id")
    export_parser.add_argument("--jsonl", action="store_true", default=True)

    gw_parser = sub.add_parser("gateway", help="Message gateway")
    gw_sub = gw_parser.add_subparsers(dest="gateway_cmd")
    gw_start = gw_sub.add_parser("start", help="Start gateway")
    gw_start.add_argument("--telegram", action="store_true")
    gw_start.add_argument("--webhook", action="store_true")

    api_parser = sub.add_parser("api", help="OpenAI-compatible API server")
    api_sub = api_parser.add_subparsers(dest="api_cmd")
    for name in ("start", "serve"):
        api_cmd = api_sub.add_parser(name, help="Start API server")
        api_cmd.add_argument("--host", default=None)
        api_cmd.add_argument("--port", type=int, default=None)

    batch_parser = sub.add_parser("batch", help="Batch runner")
    batch_parser.add_argument("file", help="JSON file with prompts list")

    sub.add_parser("acp", help="ACP stdio adapter")

    from kanban.cli import add_kanban_parser

    add_kanban_parser(sub)

    dash_parser = sub.add_parser("dashboard", help="Web dashboard (Kanban + Chat)")
    dash_sub = dash_parser.add_subparsers(dest="dashboard_cmd")
    dash_start = dash_sub.add_parser("start", help="Start dashboard server")
    dash_start.add_argument("--host", default=None)
    dash_start.add_argument("--port", type=int, default=None)

    return parser


def _make_engine(config: EmperorConfig, profile: str | None) -> QueryEngine:
    provider = build_provider(config)
    return QueryEngine(
        deps=AgentDeps.from_provider(provider),  # type: ignore[arg-type]
        config=config,
        profile=profile or "default",
    )


async def _cmd_config(config: EmperorConfig, args: argparse.Namespace, profile: str | None) -> int:
    if args.config_cmd != "show":
        print("Usage: emperor config show", file=sys.stderr)
        return 1
    console = Console()
    console.print("[bold]emperor configuration[/bold]")
    console.print(f"  provider: {config.provider.provider}")
    console.print(f"  model: {config.provider.model}")
    console.print(f"  base_url: {config.provider.base_url}")
    console.print(f"  api_key: {'***' if config.provider.api_key else '(not set)'}")
    console.print(f"  max_turns: {config.agent.max_turns}")
    console.print(f"  toolsets: {config.tools.enabled_toolsets}")
    console.print(f"  log_level: {config.log_level}")
    return 0


async def _cmd_chat(config: EmperorConfig, args: argparse.Namespace, profile: str | None) -> int:
    from cli.repl import ChatRepl

    console = Console()
    strings = get_cli_strings(config.ui.language)
    try:
        engine = _make_engine(config, profile)
    except ValueError as exc:
        console.print(f"[red]{strings.error_prefix}[/red]{exc}")
        return 1

    repl = ChatRepl(engine=engine, config=config, profile=profile, console=console)

    query = args.query or args.message
    if query:
        return await repl.run_single(query, quiet=args.quiet)

    return await repl.run()


async def _cmd_session(config: EmperorConfig, args: argparse.Namespace, profile: str | None) -> int:
    from constants import normalize_profile

    effective = normalize_profile(profile)
    store = SessionStore.for_profile(effective)
    await store.initialize()
    console = Console()

    if args.session_cmd == "list":
        from session.time_util import format_local_timestamp, format_session_age, session_to_dict

        strings = get_cli_strings(config.ui.language)
        sessions = await store.list_sessions(profile=effective)
        sessions = await store.backfill_missing_titles(sessions, language=config.ui.language)
        if args.__dict__.get("json"):
            print(json.dumps([session_to_dict(s) for s in sessions], ensure_ascii=False))
        else:
            now = time.time()
            for s in sessions:
                title = s.title or strings.session_untitled
                local_time = format_local_timestamp(s.updated_at)
                age = format_session_age(s.updated_at, now=now)
                console.print(
                    f"  {s.id[:8]}…  {title}  "
                    f"[{strings.session_message_count.format(count=s.message_count)}]  "
                    f"[{local_time}]  [{age}]  [{s.platform}]"
                )
        return 0

    if args.session_cmd == "export":
        data = await store.export_jsonl(args.session_id)
        print(data, end="")
        return 0

    console.print("Usage: emperor session list|export <id>")
    return 1


async def _cmd_gateway(config: EmperorConfig, args: argparse.Namespace, profile: str | None) -> int:
    from gateway.platforms.telegram import TelegramAdapter
    from gateway.platforms.webhook import WebhookAdapter
    from gateway.runner import GatewayRunner

    console = Console()

    def factory(_key: str) -> QueryEngine:
        return _make_engine(config, profile)

    runner = GatewayRunner(engine_factory=factory)

    if args.gateway_cmd == "start":
        dispatcher_task = None
        if config.kanban.dispatch_in_gateway:
            from kanban.db import KanbanDB
            from kanban.dispatcher import KanbanDispatcher

            db = KanbanDB.for_profile(profile)
            dispatcher = KanbanDispatcher(db, config, profile=profile)
            dispatcher_task = asyncio.create_task(dispatcher.run_loop())

        if args.telegram:
            token = config.gateway.telegram_token or os.environ.get(config.gateway.telegram_token_env)
            if not token:
                console.print("[red]Set gateway.telegram_token or TELEGRAM_BOT_TOKEN[/red]")
                return 1
            runner.adapters.append(TelegramAdapter(token))
        if args.webhook:
            wh = WebhookAdapter(secret=config.gateway.webhook_secret)
            wh.attach(runner)
            app = wh.create_app()
            console.print(f"[green]Webhook on {config.gateway.host}:{config.gateway.port}[/green]")
            await _serve_uvicorn(app, host=config.gateway.host, port=config.gateway.port)
            return 0
        if runner.adapters:
            console.print("[green]Starting gateway adapters…[/green]")
            await runner.start()
            return 0
        console.print("Usage: emperor gateway start --telegram|--webhook")
        return 1
    return 1


async def _serve_uvicorn(app, *, host: str, port: int) -> None:
    """Run uvicorn without nesting asyncio.run() inside the CLI event loop."""
    import uvicorn

    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port))
    await server.serve()


async def _cmd_api(config: EmperorConfig, args: argparse.Namespace, profile: str | None) -> int:
    if args.api_cmd not in {"start", "serve"}:
        print("Usage: emperor api start|serve", file=sys.stderr)
        return 1
    from api.server import create_api_app

    host = args.host or config.api_server.host
    port = args.port or config.api_server.port

    def factory():
        return _make_engine(config, profile)

    app = create_api_app(factory)
    await _serve_uvicorn(app, host=host, port=port)
    return 0


async def _cmd_batch(config: EmperorConfig, args: argparse.Namespace, profile: str | None) -> int:
    from pathlib import Path

    from batch.runner import run_batch_file

    provider = build_provider(config)
    deps = AgentDeps.from_provider(provider)  # type: ignore[arg-type]
    results = await run_batch_file(Path(args.file), deps=deps)
    for r in results:
        print(json.dumps({"prompt": r.prompt, "response": r.response, "error": r.error}, ensure_ascii=False))
    return 0


async def _cmd_acp(config: EmperorConfig, args: argparse.Namespace, profile: str | None) -> int:
    from acp.adapter import ACPAdapter

    adapter = ACPAdapter()

    def factory():
        return _make_engine(config, profile)

    await adapter.run_stdio(factory)
    return 0


async def _cmd_kanban(config: EmperorConfig, args: argparse.Namespace, profile: str | None) -> int:
    from kanban.cli import run_kanban_cli

    if not args.kanban_cmd:
        print("Usage: emperor kanban init|create|list|show|...", file=sys.stderr)
        return 1
    return await run_kanban_cli(args, profile)


async def _cmd_dashboard(config: EmperorConfig, args: argparse.Namespace, profile: str | None) -> int:
    if args.dashboard_cmd != "start":
        print("Usage: emperor dashboard start", file=sys.stderr)
        return 1
    import uvicorn

    from dashboard.server import create_dashboard_app

    host = args.host or config.dashboard.host
    port = args.port or config.dashboard.port
    app = create_dashboard_app(
        config,
        profile=profile,
        start_dispatcher_loop=True,
    )

    console = Console()
    console.print(f"[green]Dashboard[/green] http://{host}:{port}/")
    await _serve_uvicorn(app, host=host, port=port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
