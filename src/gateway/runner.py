"""Gateway message dispatch loop."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from engine.query_engine import QueryEngine
from gateway.session_router import SessionRouter

logger = logging.getLogger(__name__)

MessageHandler = Callable[[str, str], Awaitable[str]]
PlatformAdapter = Callable[[], Awaitable[None]]


@dataclass
class GatewayRunner:
    """Dispatch incoming platform messages to QueryEngine."""

    engine_factory: Callable[[str], QueryEngine]
    router: SessionRouter = field(default_factory=SessionRouter)
    adapters: list[Any] = field(default_factory=list)
    _running: bool = False

    async def handle_message(self, platform_key: str, text: str, *, session_id: str | None = None) -> str:
        session_id = session_id or self.router.get_session(platform_key)
        engine = self.engine_factory(platform_key)
        if session_id:
            await engine.resume_session(session_id)
        try:
            response = await engine.chat(text)
            if engine.session_id:
                self.router.set_session(platform_key, engine.session_id)
            return response
        except Exception as exc:  # noqa: BLE001
            logger.exception("Gateway handle_message failed")
            return f"Error: {exc}"

    async def start(self) -> None:
        self._running = True
        tasks = [asyncio.create_task(a.start(self)) for a in self.adapters if hasattr(a, "start")]
        if tasks:
            await asyncio.gather(*tasks)

    async def stop(self) -> None:
        self._running = False
        for a in self.adapters:
            if hasattr(a, "stop"):
                await a.stop()
