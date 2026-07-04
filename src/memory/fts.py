"""Cross-session memory FTS recall."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import aiosqlite

from constants import get_emperor_home


class MemoryFTS:
    """FTS5 index for memory snippets across sessions."""

    def __init__(self, db_path: Path | None = None) -> None:
        home = get_emperor_home()
        home.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path or home / "memory_fts.db"

    async def initialize(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript("""
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                    source, content
                );
            """)
            await db.commit()

    async def index(self, source: str, content: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO memory_fts (source, content) VALUES (?, ?)",
                (source, content),
            )
            await db.commit()

    async def search(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT source, content FROM memory_fts WHERE memory_fts MATCH ? LIMIT ?",
                (query, limit),
            )
            rows = await cur.fetchall()
        return [dict(r) for r in rows]
