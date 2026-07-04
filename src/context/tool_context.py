"""Tool execution context."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from agent.deps import AgentDeps


CanUseToolFn = Callable[[str, dict[str, Any]], bool]


@dataclass
class ToolContext:
    """Unified execution environment for tool calls."""

    messages: list[dict[str, Any]]
    abort_event: asyncio.Event | None = None
    task_id: str = "default"
    chain_id: str | None = None
    depth: int = 0
    can_use_tool: CanUseToolFn | None = None
    agent_deps: AgentDeps | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    _pending_a2ui: list[dict[str, Any]] = field(default_factory=list, repr=False)

    def is_aborted(self) -> bool:
        return self.abort_event is not None and self.abort_event.is_set()

    def allow_tool(self, name: str, input_data: dict[str, Any]) -> bool:
        if self.can_use_tool is None:
            return True
        return self.can_use_tool(name, input_data)

    def emit_a2ui(self, messages: list[dict[str, Any]]) -> None:
        """Queue A2UI messages for streaming to the dashboard client."""
        self._pending_a2ui.extend(messages)

    def drain_a2ui(self) -> list[dict[str, Any]]:
        """Return and clear queued A2UI messages."""
        drained = list(self._pending_a2ui)
        self._pending_a2ui.clear()
        return drained

    def apply_result(self, result: Any) -> list[dict[str, Any]]:
        """Apply loop-state changes emitted by a tool result."""
        appended: list[dict[str, Any]] = []
        context_patch = getattr(result, "context_patch", None) or {}
        if context_patch:
            self.extra.update(context_patch)

        for text in getattr(result, "system_messages", None) or []:
            message = {"role": "system", "content": text}
            self.messages.append(message)
            appended.append(message)
        return appended
