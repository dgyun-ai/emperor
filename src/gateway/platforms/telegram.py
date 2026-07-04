"""Telegram platform adapter MVP."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from gateway.runner import GatewayRunner

logger = logging.getLogger(__name__)


class TelegramAdapter:
    """Long-polling Telegram bot adapter using httpx."""

    def __init__(self, token: str) -> None:
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"
        self._offset = 0
        self._running = False
        self._task = None

    async def start(self, runner: GatewayRunner) -> None:
        self._running = True
        self._runner = runner
        import asyncio

        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()

    async def _poll_loop(self) -> None:
        import asyncio

        while self._running:
            try:
                async with httpx.AsyncClient(timeout=35.0) as client:
                    resp = await client.get(
                        f"{self.base_url}/getUpdates",
                        params={"offset": self._offset, "timeout": 30},
                    )
                    data = resp.json()
                    for update in data.get("result", []):
                        self._offset = update["update_id"] + 1
                        msg = update.get("message") or update.get("edited_message")
                        if not msg or "text" not in msg:
                            continue
                        chat_id = str(msg["chat"]["id"])
                        text = msg["text"]
                        if not self._runner.router.is_paired(chat_id):
                            self._runner.router.pair(chat_id)
                        reply = await self._runner.handle_message(f"telegram:{chat_id}", text)
                        await self._send_message(chat_id, reply)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Telegram poll error")
                await asyncio.sleep(5)

    async def _send_message(self, chat_id: str, text: str) -> None:
        async with httpx.AsyncClient(timeout=15.0) as client:
            await client.post(
                f"{self.base_url}/sendMessage",
                json={"chat_id": chat_id, "text": text[:4096]},
            )
