"""Iteration budget tracking for AgentLoop."""

from __future__ import annotations


class IterationBudget:
    """Tracks remaining turns before max_iterations terminal."""

    def __init__(self, max_turns: int) -> None:
        if max_turns < 1:
            raise ValueError("max_turns must be >= 1")
        self.max_turns = max_turns
        self.used = 0

    @property
    def remaining(self) -> int:
        return max(0, self.max_turns - self.used)

    @property
    def exhausted(self) -> bool:
        return self.used >= self.max_turns

    def consume(self) -> None:
        self.used += 1

    def __repr__(self) -> str:
        return f"IterationBudget(used={self.used}, max_turns={self.max_turns})"
