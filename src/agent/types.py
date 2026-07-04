"""Agent loop types and iteration budget."""

from __future__ import annotations

from typing import Any, Literal, TypedDict


class Continue(TypedDict):
    reason: Literal["tool_use", "compact_retry", "budget_continue"]


class Terminal(TypedDict):
    reason: Literal["complete", "max_iterations", "aborted", "error", "loop_detected"]
    message: str | None
    error: str | None


class AgentEvent:
    """Streaming event emitted by AgentLoop."""

    __slots__ = ("kind", "payload")

    def __init__(
        self,
        kind: Literal[
            "stream_delta",
            "thinking",
            "tool_start",
            "tool_end",
            "message",
            "status",
            "usage_update",
            "ask_user_questions",
            "a2ui",
        ],
        payload: Any,
    ) -> None:
        self.kind = kind
        self.payload = payload

    def __repr__(self) -> str:
        return f"AgentEvent(kind={self.kind!r}, payload={self.payload!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AgentEvent):
            return NotImplemented
        return self.kind == other.kind and self.payload == other.payload
