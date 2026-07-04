"""Load project context files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

CONTEXT_FILENAMES = [
    ".emperor.md",
    "AGENTS.md",
    "CLAUDE.md",
    "SOUL.md",
]


@dataclass
class ContextFiles:
    files: dict[str, str]
    combined: str


def load_context_files(cwd: Path | None = None) -> ContextFiles:
    """Load context markdown files from cwd and parents up to git root."""
    root = cwd or Path.cwd()
    found: dict[str, str] = {}

    for directory in [root, *root.parents]:
        for name in CONTEXT_FILENAMES:
            if name in found:
                continue
            path = directory / name
            if path.is_file():
                found[name] = path.read_text(encoding="utf-8", errors="replace")
        if (directory / ".git").exists():
            break

    sections = [f"### {name}\n{content}" for name, content in found.items()]
    combined = "\n\n".join(sections) if sections else ""
    return ContextFiles(files=found, combined=combined)


def parse_file_references(text: str, cwd: Path | None = None) -> tuple[str, list[str]]:
    """Expand @file and @folder references in user input."""
    root = cwd or Path.cwd()
    expanded_parts: list[str] = [text]
    refs: list[str] = []

    import re

    for match in re.finditer(r"@(\S+)", text):
        ref = match.group(1)
        path = (root / ref).resolve()
        refs.append(str(path))
        if path.is_file():
            content = path.read_text(encoding="utf-8", errors="replace")[:9118]
            expanded_parts.append(f"\n\n--- Content of {ref} ---\n{content}")
        elif path.is_dir():
            files = list(path.glob("*"))[:20]
            listing = "\n".join(f.name for f in files if f.is_file())
            expanded_parts.append(f"\n\n--- Directory {ref} ---\n{listing}")

    return "".join(expanded_parts), refs
