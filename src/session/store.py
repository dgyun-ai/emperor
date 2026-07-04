"""SQLite session persistence with openclaw event storage."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiosqlite

from constants import get_emperor_home, normalize_profile
from session.events import message_role, message_text_content
from session.title import is_garbage_title, is_placeholder_title, truncate_title

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    profile TEXT NOT NULL,
    platform TEXT,
    platform_key TEXT,
    title TEXT,
    parent_session_id TEXT,
    created_at REAL,
    updated_at REAL
);

CREATE TABLE IF NOT EXISTS session_events (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    seq INTEGER NOT NULL,
    parent_id TEXT,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at REAL,
    UNIQUE(session_id, seq)
);

CREATE TABLE IF NOT EXISTS compress_events (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    child_session_id TEXT,
    summary TEXT,
    protected_last_n INTEGER,
    created_at REAL
);
"""

MIGRATION_DROP_LEGACY = """
DROP TRIGGER IF EXISTS messages_ai;
DROP TRIGGER IF EXISTS messages_ad;
DROP TRIGGER IF EXISTS messages_au;
DROP TABLE IF EXISTS messages_fts;
DROP TABLE IF EXISTS messages;
"""


@dataclass
class SessionInfo:
    id: str
    profile: str
    title: str | None
    platform: str | None
    created_at: float
    updated_at: float
    parent_session_id: str | None = None
    message_count: int = 0


class SessionStore:
    """SQLite-backed session and openclaw event storage."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    @classmethod
    def for_profile(cls, profile: str | None = None) -> SessionStore:
        home = get_emperor_home(normalize_profile(profile))
        home.mkdir(parents=True, exist_ok=True)
        return cls(home / "state.db")

    async def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(MIGRATION_DROP_LEGACY)
            await db.executescript(SCHEMA)
            await db.commit()

    async def create_session(
        self,
        *,
        profile: str = "default",
        platform: str = "cli",
        platform_key: str | None = None,
        title: str | None = None,
        parent_session_id: str | None = None,
    ) -> str:
        session_id = str(uuid.uuid4())
        now = time.time()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO sessions (id, profile, platform, platform_key, title,
                   parent_session_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (session_id, profile, platform, platform_key, title, parent_session_id, now, now),
            )
            await db.commit()
        return session_id

    async def get_session(self, session_id: str) -> SessionInfo | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """SELECT s.*,
                          (SELECT COUNT(*) FROM session_events e
                           WHERE e.session_id = s.id AND e.event_type = 'message') AS message_count
                   FROM sessions s
                   WHERE s.id = ?""",
                (session_id,),
            )
            row = await cur.fetchone()
        if row is None:
            return None
        return SessionInfo(
            id=row["id"],
            profile=row["profile"],
            title=row["title"],
            platform=row["platform"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            parent_session_id=row["parent_session_id"],
            message_count=int(row["message_count"] or 0),
        )

    async def session_has_title(self, session_id: str) -> bool:
        title = await self.get_title(session_id)
        return (
            bool(title)
            and not is_garbage_title(title)
            and not is_placeholder_title(title)
        )

    async def set_title(self, session_id: str, title: str, *, force: bool = False) -> None:
        """Set session title; force=True overwrites existing titles (e.g. garbage repair)."""
        cleaned = " ".join(title.split()).strip()
        if not cleaned:
            return
        if force:
            query = "UPDATE sessions SET title = ? WHERE id = ?"
            params = (cleaned, session_id)
        else:
            query = (
                "UPDATE sessions SET title = ? WHERE id = ? AND (title IS NULL OR title = '')"
            )
            params = (cleaned, session_id)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(query, params)
            await db.commit()

    async def set_title_if_empty(self, session_id: str, title: str) -> None:
        """Set session title when none exists yet."""
        await self.set_title(session_id, title, force=False)

    async def set_last_assistant_content(self, session_id: str, content: str) -> None:
        """Patch the most recent assistant message event when stream text was missing."""
        if not content.strip():
            return
        events = await self.load_events(session_id)
        for event in reversed(events):
            if event.get("type") != "message":
                continue
            msg = event.get("message")
            if not isinstance(msg, dict) or msg.get("role") != "assistant":
                continue
            blocks = msg.get("content")
            if not isinstance(blocks, list):
                blocks = []
            updated_blocks = [b for b in blocks if not (isinstance(b, dict) and b.get("type") == "text")]
            updated_blocks.append({"type": "text", "text": content})
            msg["content"] = updated_blocks
            await self._update_event_payload(session_id, str(event["id"]), event)
            return

    async def _update_event_payload(
        self,
        session_id: str,
        event_id: str,
        event: dict[str, Any],
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE session_events SET payload = ? WHERE session_id = ? AND id = ?",
                (json.dumps(event, ensure_ascii=False), session_id, event_id),
            )
            await db.commit()

    async def get_first_user_message_content(self, session_id: str) -> str | None:
        events = await self.load_events(session_id)
        for event in events:
            if message_role(event) == "user":
                text = message_text_content(event).strip()
                if text:
                    return text
        return None

    async def get_first_assistant_message_content(self, session_id: str) -> str | None:
        events = await self.load_events(session_id)
        for event in events:
            if message_role(event) == "assistant":
                text = message_text_content(event).strip()
                if text:
                    return text
        return None

    async def get_title(self, session_id: str) -> str | None:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("SELECT title FROM sessions WHERE id = ?", (session_id,))
            row = await cur.fetchone()
        if not row or not row[0]:
            return None
        return str(row[0]).strip() or None

    async def backfill_title_from_history(self, session_id: str) -> bool:
        """Set title from first user message (truncate) when missing."""
        if await self.session_has_title(session_id):
            return False
        content = await self.get_first_user_message_content(session_id)
        if not content:
            return False
        await self.set_title_if_empty(session_id, content)
        return True

    async def backfill_missing_titles(
        self,
        sessions: list[SessionInfo],
        *,
        language: str = "zh",
    ) -> list[SessionInfo]:
        """Fill empty or garbage titles from history for display (no LLM)."""
        updated: list[SessionInfo] = []
        for s in sessions:
            if s.title and not is_garbage_title(s.title) and not is_placeholder_title(s.title):
                updated.append(s)
                continue
            content = await self.get_first_user_message_content(s.id)
            if not content:
                updated.append(s)
                continue
            fallback = truncate_title(content, language=language)
            await self.set_title(s.id, fallback, force=bool(s.title))
            title = await self.get_title(s.id)
            updated.append(
                SessionInfo(
                    id=s.id,
                    profile=s.profile,
                    title=title,
                    platform=s.platform,
                    created_at=s.created_at,
                    updated_at=s.updated_at,
                    parent_session_id=s.parent_session_id,
                    message_count=s.message_count,
                )
            )
        return updated

    async def append_event(
        self,
        session_id: str,
        event: dict[str, Any],
        *,
        seq: int | None = None,
    ) -> str:
        event_id = str(event.get("id") or uuid.uuid4())
        event["id"] = event_id
        now = time.time()
        event_type = str(event.get("type", "unknown"))
        parent_id = event.get("parentId")
        payload = json.dumps(event, ensure_ascii=False)

        async with aiosqlite.connect(self.db_path) as db:
            if seq is None:
                cur = await db.execute(
                    "SELECT COALESCE(MAX(seq), -1) + 1 FROM session_events WHERE session_id = ?",
                    (session_id,),
                )
                row = await cur.fetchone()
                seq = row[0] if row else 0

            await db.execute(
                """INSERT INTO session_events (id, session_id, seq, parent_id, event_type,
                   payload, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (event_id, session_id, seq, parent_id, event_type, payload, now),
            )
            await db.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (now, session_id),
            )
            await db.commit()
        return event_id

    async def append_events(
        self,
        session_id: str,
        events: list[dict[str, Any]],
    ) -> list[str]:
        ids: list[str] = []
        for event in events:
            ids.append(await self.append_event(session_id, event))
        return ids

    async def load_events(self, session_id: str) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT payload FROM session_events WHERE session_id = ? ORDER BY seq",
                (session_id,),
            )
            rows = await cur.fetchall()

        events: list[dict[str, Any]] = []
        for row in rows:
            events.append(json.loads(row["payload"]))
        return events

    async def load_messages(self, session_id: str) -> list[dict[str, Any]]:
        """Backward-compat alias: returns openclaw events (not OpenAI dicts)."""
        return await self.load_events(session_id)

    async def append_message(
        self,
        session_id: str,
        message: dict[str, Any],
        *,
        seq: int | None = None,
    ) -> str:
        """Deprecated: converts OpenAI message to event and appends."""
        from session.convert import openai_message_to_event, parent_for_next_event

        events = await self.load_events(session_id)
        parent_id = parent_for_next_event(events)
        event = openai_message_to_event(message, parent_id=parent_id)
        return await self.append_event(session_id, event, seq=seq)

    async def list_sessions(self, *, profile: str | None = None, limit: int = 50) -> list[SessionInfo]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            sql = """
                SELECT s.*,
                       (SELECT COUNT(*) FROM session_events e
                        WHERE e.session_id = s.id AND e.event_type = 'message') AS message_count
                FROM sessions s
            """
            if profile:
                cur = await db.execute(
                    sql + " WHERE s.profile = ? ORDER BY s.updated_at DESC LIMIT ?",
                    (profile, limit),
                )
            else:
                cur = await db.execute(
                    sql + " ORDER BY s.updated_at DESC LIMIT ?",
                    (limit,),
                )
            rows = await cur.fetchall()
        return [
            SessionInfo(
                id=r["id"],
                profile=r["profile"],
                title=r["title"],
                platform=r["platform"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                parent_session_id=r["parent_session_id"],
                message_count=int(r["message_count"] or 0),
            )
            for r in rows
        ]

    async def search_messages(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """SELECT session_id, event_type, payload, seq
                   FROM session_events
                   WHERE event_type = 'message' AND payload LIKE ?
                   ORDER BY created_at DESC LIMIT ?""",
                (f"%{query}%", limit),
            )
            rows = await cur.fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            event = json.loads(row["payload"])
            results.append(
                {
                    "session_id": row["session_id"],
                    "role": message_role(event),
                    "content": message_text_content(event),
                    "seq": row["seq"],
                }
            )
        return results

    async def export_jsonl(self, session_id: str) -> str:
        events = await self.load_events(session_id)
        lines = [json.dumps(e, ensure_ascii=False) for e in events]
        return "\n".join(lines) + ("\n" if lines else "")

    async def get_latest_session(self, *, profile: str = "default") -> str | None:
        sessions = await self.list_sessions(profile=profile, limit=20)
        for s in sessions:
            if s.message_count > 0:
                return s.id
        return None

    async def has_compress_events(self, session_id: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT 1 FROM compress_events WHERE session_id = ? LIMIT 1",
                (session_id,),
            )
            row = await cursor.fetchone()
        return row is not None

    async def record_compress_event(
        self,
        session_id: str,
        *,
        child_session_id: str | None,
        summary: str,
        protected_last_n: int,
    ) -> str:
        event_id = str(uuid.uuid4())
        now = time.time()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO compress_events (id, session_id, child_session_id, summary,
                   protected_last_n, created_at) VALUES (?, ?, ?, ?, ?, ?)""",
                (event_id, session_id, child_session_id, summary, protected_last_n, now),
            )
            await db.commit()
        return event_id

    async def delete_session(self, session_id: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM session_events WHERE session_id = ?", (session_id,))
            await db.execute("DELETE FROM compress_events WHERE session_id = ?", (session_id,))
            await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            await db.commit()
