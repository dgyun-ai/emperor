"""Terminal run command tool."""

from __future__ import annotations

import json

from context.tool_context import ToolContext
from tools.approval import check_tool_approval
from tools.base import ToolResult
from tools.environments.backends import get_backend
from tools.registry import register_tool

_backend_name = "local"
_docker_image = "python:3.11-slim"
_timeout = 120


def configure_terminal(*, backend: str = "local", docker_image: str = "python:3.11-slim", timeout: int = 120) -> None:
    global _backend_name, _docker_image, _timeout
    _backend_name = backend
    _docker_image = docker_image
    _timeout = timeout


@register_tool(
    name="terminal_run",
    description="Run a shell command and return stdout/stderr.",
    toolset="terminal",
    input_schema={
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "cwd": {"type": "string"},
        },
        "required": ["command"],
    },
)
async def terminal_run(input: dict, ctx: ToolContext) -> ToolResult:
    approved, reason = await check_tool_approval("terminal_run", input)
    if not approved:
        return ToolResult(content=reason or "Denied", is_error=True)

    backend = get_backend(_backend_name, docker_image=_docker_image)
    result = await backend.run(
        input["command"],
        cwd=input.get("cwd"),
        timeout=_timeout,
    )
    payload = {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
    }
    is_error = result.returncode != 0
    return ToolResult(content=json.dumps(payload), is_error=is_error)
