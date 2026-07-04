"""MEMORY.md and USER.md management."""

from __future__ import annotations

from pathlib import Path

from constants import get_emperor_home


class MemoryManager:
    """Read/write persistent memory files with size limits."""

    def __init__(
        self,
        home: Path | None = None,
        *,
        max_memory_chars: int = 50_000,
        max_user_chars: int = 10_000,
    ) -> None:
        self.home = home or get_emperor_home()
        self.home.mkdir(parents=True, exist_ok=True)
        self.memory_path = self.home / "MEMORY.md"
        self.user_path = self.home / "USER.md"
        self.max_memory_chars = max_memory_chars
        self.max_user_chars = max_user_chars

    def read_memory(self) -> str:
        if self.memory_path.exists():
            return self.memory_path.read_text(encoding="utf-8")
        return ""

    def read_user(self) -> str:
        if self.user_path.exists():
            return self.user_path.read_text(encoding="utf-8")
        return ""

    def write_memory(self, content: str) -> None:
        trimmed = content[: self.max_memory_chars]
        self.memory_path.write_text(trimmed, encoding="utf-8")

    def append_memory(self, note: str) -> None:
        current = self.read_memory()
        updated = (current + "\n" + note).strip()[: self.max_memory_chars]
        self.write_memory(updated)

    def write_user(self, content: str) -> None:
        trimmed = content[: self.max_user_chars]
        self.user_path.write_text(trimmed, encoding="utf-8")

    def summary_for_prompt(self) -> str:
        parts: list[str] = []
        mem = self.read_memory().strip()
        user = self.read_user().strip()
        if user:
            parts.append(f"User profile:\n{user[:2000]}")
        if mem:
            parts.append(f"Long-term memory:\n{mem[:4000]}")
        return "\n\n".join(parts)
