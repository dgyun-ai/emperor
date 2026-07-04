"""Token usage tracking and context window estimation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from context.compressor import estimate_tokens


@dataclass
class TurnUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class UsageTracker:
    """Accumulates API usage across a conversation session."""

    session_prompt_tokens: int = 0
    session_completion_tokens: int = 0
    last_turn: TurnUsage = field(default_factory=TurnUsage)

    def record_turn(self, prompt_tokens: int, completion_tokens: int) -> TurnUsage:
        self.last_turn = TurnUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        self.session_prompt_tokens += prompt_tokens
        self.session_completion_tokens += completion_tokens
        return self.last_turn

    @property
    def session_total_tokens(self) -> int:
        return self.session_prompt_tokens + self.session_completion_tokens


def estimate_context_tokens(
    messages: list[dict[str, Any]],
    *,
    system_prompt: str = "",
) -> int:
    """Estimate tokens currently occupying the context window."""
    system_msgs = [{"role": "system", "content": system_prompt}] if system_prompt else []
    return estimate_tokens([*system_msgs, *messages])


def _context_block(
    context_tokens: int,
    max_context_tokens: int,
    *,
    compressed: bool = False,
) -> dict[str, Any]:
    percent = (context_tokens / max_context_tokens * 100) if max_context_tokens else 0.0
    block: dict[str, Any] = {
        "used_tokens": context_tokens,
        "max_tokens": max_context_tokens,
        "percent": round(percent, 1),
    }
    if compressed:
        block["compressed"] = True
    return block


def build_usage_snapshot(
    tracker: UsageTracker,
    *,
    context_tokens: int,
    max_context_tokens: int,
    compressed: bool = False,
) -> dict[str, Any]:
    """Build payload for usage_update AgentEvent."""
    return {
        "turn": {
            "prompt_tokens": tracker.last_turn.prompt_tokens,
            "completion_tokens": tracker.last_turn.completion_tokens,
            "total_tokens": tracker.last_turn.total_tokens,
        },
        "session": {
            "prompt_tokens": tracker.session_prompt_tokens,
            "completion_tokens": tracker.session_completion_tokens,
            "total_tokens": tracker.session_total_tokens,
        },
        "context": _context_block(
            context_tokens,
            max_context_tokens,
            compressed=compressed,
        ),
    }


def restore_tracker_from_snapshot(snapshot: dict[str, Any] | None) -> UsageTracker:
    """Rebuild in-memory tracker from persisted session_meta usage."""
    tracker = UsageTracker()
    if not snapshot:
        return tracker
    session = snapshot.get("session") or {}
    turn = snapshot.get("turn") or {}
    tracker.session_prompt_tokens = int(session.get("prompt_tokens") or 0)
    tracker.session_completion_tokens = int(session.get("completion_tokens") or 0)
    tracker.last_turn = TurnUsage(
        prompt_tokens=int(turn.get("prompt_tokens") or 0),
        completion_tokens=int(turn.get("completion_tokens") or 0),
    )
    return tracker


def build_history_usage_snapshot(
    messages: list[dict[str, Any]],
    *,
    system_prompt: str,
    max_context_tokens: int,
    stored_snapshot: dict[str, Any] | None = None,
    compressed: bool = False,
) -> dict[str, Any]:
    """Usage snapshot for a loaded session (context from stored messages)."""
    context_tokens = estimate_context_tokens(messages, system_prompt=system_prompt)
    tracker = restore_tracker_from_snapshot(stored_snapshot)
    if stored_snapshot:
        turn = stored_snapshot.get("turn") or {}
        tracker.last_turn = TurnUsage(
            prompt_tokens=int(turn.get("prompt_tokens") or 0),
            completion_tokens=int(turn.get("completion_tokens") or 0),
        )
    return build_usage_snapshot(
        tracker,
        context_tokens=context_tokens,
        max_context_tokens=max_context_tokens,
        compressed=compressed or bool((stored_snapshot or {}).get("context", {}).get("compressed")),
    )
