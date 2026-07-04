"""Webhook HTTP adapter for gateway."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gateway.runner import GatewayRunner

logger = logging.getLogger(__name__)


class WebhookAdapter:
    """FastAPI webhook handler mounted by gateway start."""

    def __init__(self, secret: str | None = None) -> None:
        self.secret = secret
        self._runner: GatewayRunner | None = None

    def attach(self, runner: GatewayRunner) -> None:
        self._runner = runner

    async def handle_webhook(self, body: dict, *, platform_key: str = "webhook:default") -> dict:
        if self._runner is None:
            return {"error": "Gateway not initialized"}
        text = body.get("message") or body.get("text") or ""
        if not text:
            return {"error": "No message in body"}
        reply = await self._runner.handle_message(platform_key, text)
        return {"reply": reply}

    def create_app(self):
        from fastapi import FastAPI, Request

        app = FastAPI(title="emperor webhook")

        @app.post("/webhook")
        async def webhook(request: Request):
            body = await request.json()
            if self.secret and body.get("secret") != self.secret:
                return {"error": "Unauthorized"}
            result = await self.handle_webhook(body)
            return result

        @app.get("/health")
        async def health():
            return {"status": "ok"}

        return app
