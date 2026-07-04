"""ACP stdio JSON-RPC adapter skeleton."""

from __future__ import annotations

import json
import sys
from typing import Any


class ACPAdapter:
    """Minimal Agent Client Protocol adapter over stdio."""

    def __init__(self) -> None:
        self._running = False

    async def run_stdio(self, engine_factory) -> None:
        """Read JSON-RPC lines from stdin, dispatch to engine."""
        self._running = True
        while self._running:
            line = sys.stdin.readline()
            if not line:
                break
            try:
                req = json.loads(line)
            except json.JSONDecodeError:
                self._respond({"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}})
                continue
            result = await self._dispatch(req, engine_factory)
            if "id" in req:
                self._respond({"jsonrpc": "2.0", "id": req["id"], "result": result})

    async def _dispatch(self, req: dict[str, Any], engine_factory) -> Any:
        method = req.get("method", "")
        params = req.get("params", {})
        if method == "initialize":
            return {"protocolVersion": "0.1", "capabilities": {"chat": True}}
        if method == "chat/send":
            engine = engine_factory()
            text = params.get("message", "")
            response = await engine.chat(text)
            return {"message": response}
        if method == "shutdown":
            self._running = False
            return {}
        return {"error": f"Unknown method: {method}"}

    def _respond(self, payload: dict[str, Any]) -> None:
        sys.stdout.write(json.dumps(payload) + "\n")
        sys.stdout.flush()
