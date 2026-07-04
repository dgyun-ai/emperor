"""MCP server configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from constants import get_emperor_home
from mcp.client import MCPServerConfig


def load_mcp_configs(home: Path | None = None) -> list[MCPServerConfig]:
    root = home or get_emperor_home()
    path = root / "mcp_servers.yaml"
    if not path.exists():
        return []
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    servers = raw.get("servers", [])
    return [
        MCPServerConfig(
            name=s["name"],
            command=s["command"],
            args=s.get("args", []),
            env=s.get("env", {}),
        )
        for s in servers
        if isinstance(s, dict) and s.get("name") and s.get("command")
    ]


def save_mcp_configs(configs: list[MCPServerConfig], home: Path | None = None) -> None:
    root = home or get_emperor_home()
    root.mkdir(parents=True, exist_ok=True)
    path = root / "mcp_servers.yaml"
    payload = {
        "servers": [
            {
                "name": c.name,
                "command": c.command,
                "args": c.args,
                "env": c.env,
            }
            for c in configs
        ]
    }
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
