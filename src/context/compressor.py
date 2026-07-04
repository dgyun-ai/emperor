"""Context compression for long conversations."""

from __future__ import annotations

from typing import Any


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """Rough token estimate (chars / 4)."""
    total = 0
    for msg in messages:
        content = msg.get("content") or ""
        if isinstance(content, str):
            total += len(content)
        tool_calls = msg.get("tool_calls")
        if tool_calls:
            total += len(str(tool_calls))
    return max(1, total // 4) if total else 0


def should_compress(
    messages: list[dict[str, Any]],
    *,
    threshold: float = 0.5,
    max_context_tokens: int = 100_000,
) -> bool:
    """Return True if messages exceed threshold of max context."""
    return estimate_tokens(messages) >= int(max_context_tokens * threshold)


def compress_messages(
    messages: list[dict[str, Any]],
    *,
    protect_last_n: int = 20,
    summary: str | None = None,
) -> list[dict[str, Any]]:
    """Compress message history, protecting last N messages."""
    if len(messages) <= protect_last_n:
        return messages

    protected = messages[-protect_last_n:]
    to_summarize = messages[:-protect_last_n]

    if summary is None:
        parts: list[str] = []
        for msg in to_summarize:
            role = msg.get("role", "?")
            content = msg.get("content") or ""
            if isinstance(content, str) and content.strip():
                parts.append(f"[{role}]: {content[:500]}")
        summary = "Previous conversation summary:\n" + "\n".join(parts[-30:])

    compressed = [{"role": "user", "content": f"[COMPRESSED CONTEXT]\n{summary}"}]
    return compressed + protected
