"""MCP server configuration API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from constants import get_emperor_home, normalize_profile
from dashboard.context import get_request_profile
from mcp.client import MCPServerConfig
from mcp.config import load_mcp_configs, save_mcp_configs

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


class McpServerPayload(BaseModel):
    name: str
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)


class McpSaveRequest(BaseModel):
    servers: list[McpServerPayload] = Field(default_factory=list)


def _profile_home(profile: str):
    return get_emperor_home(normalize_profile(profile))


@router.get("")
async def get_mcp_config(request: Request):
    profile = get_request_profile(request)
    home = _profile_home(profile)
    servers = load_mcp_configs(home=home)
    return {
        "enabled": len(servers) > 0,
        "servers": [
            {
                "name": s.name,
                "command": s.command,
                "args": s.args,
                "env": s.env,
            }
            for s in servers
        ],
    }


@router.put("")
async def save_mcp_config(request: Request, body: McpSaveRequest):
    profile = get_request_profile(request)
    home = _profile_home(profile)
    configs: list[MCPServerConfig] = []
    seen: set[str] = set()
    for server in body.servers:
        name = server.name.strip()
        command = server.command.strip()
        if not name or not command:
            raise HTTPException(400, "Each server requires name and command")
        if name in seen:
            raise HTTPException(400, f"Duplicate server name: {name}")
        seen.add(name)
        configs.append(
            MCPServerConfig(
                name=name,
                command=command,
                args=list(server.args),
                env=dict(server.env),
            )
        )
    save_mcp_configs(configs, home=home)
    return {
        "ok": True,
        "enabled": len(configs) > 0,
        "servers": [s.model_dump() if hasattr(s, "model_dump") else {
            "name": s.name,
            "command": s.command,
            "args": s.args,
            "env": s.env,
        } for s in configs],
    }
