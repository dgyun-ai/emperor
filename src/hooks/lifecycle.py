"""Hook lifecycle: PreToolUse, PostToolUse, Stop, SessionStart."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from tools.base import ToolResult


PreToolUseHook = Callable[[str, dict[str, Any]], Awaitable[bool | None]]
PostToolUseHook = Callable[[str, dict[str, Any], ToolResult], Awaitable[None]]
StopHook = Callable[[str], Awaitable[None]]
SessionStartHook = Callable[[str], Awaitable[None]]


@dataclass
class HookManager:
    pre_tool_use: list[PreToolUseHook] = field(default_factory=list)
    post_tool_use: list[PostToolUseHook] = field(default_factory=list)
    stop: list[StopHook] = field(default_factory=list)
    session_start: list[SessionStartHook] = field(default_factory=list)

    async def run_pre_tool_use(self, name: str, input_data: dict[str, Any]) -> bool:
        for hook in self.pre_tool_use:
            result = await hook(name, input_data)
            if result is False:
                return False
        return True

    async def run_post_tool_use(self, name: str, input_data: dict[str, Any], result: ToolResult) -> None:
        for hook in self.post_tool_use:
            await hook(name, input_data, result)

    async def run_stop(self, reason: str) -> None:
        for hook in self.stop:
            await hook(reason)

    async def run_session_start(self, session_id: str) -> None:
        for hook in self.session_start:
            await hook(session_id)
