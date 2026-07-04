"""Prompt builder with stable/context/volatile tiers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from i18n.locale import get_base_agent_instructions, get_response_language_instructions
from prompt.context_files import ContextFiles, load_context_files


@dataclass
class PromptBuilder:
    """Assemble system prompt in three stable tiers."""

    language: str = "zh"
    base_instructions: str | None = None
    context_files: ContextFiles | None = None
    skills_summary: str = ""
    memory_summary: str = ""
    volatile_notes: list[str] = field(default_factory=list)
    _stable_cache: str | None = None
    _stable_cache_lang: str | None = None

    def build(self, *, reload: bool = False) -> str:
        """Build full system prompt."""
        if self.context_files is None or reload:
            self.context_files = load_context_files()

        parts: list[str] = [self._stable_section(reload=reload)]

        ctx_parts: list[str] = []
        if self.context_files and self.context_files.combined:
            ctx_parts.append(self.context_files.combined)
        if self.memory_summary:
            ctx_parts.append(f"## Memory\n{self.memory_summary}")
        if self.skills_summary:
            ctx_parts.append(f"## Skills\n{self.skills_summary}")
        if ctx_parts:
            parts.append("\n\n".join(ctx_parts))

        if self.volatile_notes:
            parts.append("## Session Notes\n" + "\n".join(self.volatile_notes))

        return "\n\n".join(parts)

    def _stable_section(self, *, reload: bool = False) -> str:
        if self._stable_cache is not None and not reload and self._stable_cache_lang == self.language:
            return self._stable_cache

        base = self.base_instructions or get_base_agent_instructions(self.language)
        lang_rules = get_response_language_instructions(self.language)
        self._stable_cache = f"{base}\n\n{lang_rules}"
        self._stable_cache_lang = self.language
        return self._stable_cache

    def add_volatile(self, note: str) -> None:
        self.volatile_notes.append(note)

    def set_memory(self, text: str) -> None:
        self.memory_summary = text

    def set_skills(self, text: str) -> None:
        self.skills_summary = text

    def set_language(self, language: str) -> None:
        self.language = language
        self._stable_cache = None
