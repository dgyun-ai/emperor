"""SQLite kanban persistence layer."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

import aiosqlite

from constants import get_emperor_home, normalize_profile
from kanban.models import COLUMNS, Task, TaskComment, TaskEvent, TaskRun

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT,
    status TEXT NOT NULL DEFAULT 'todo',
    assignee TEXT,
    tenant TEXT,
    priority INTEGER NOT NULL DEFAULT 3,
    archived INTEGER NOT NULL DEFAULT 0,
    current_run_id TEXT,
    failure_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER,
    idempotency_key TEXT UNIQUE,
    model_override TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS task_links (
    parent_id TEXT NOT NULL REFERENCES tasks(id),
    child_id TEXT NOT NULL REFERENCES tasks(id),
    PRIMARY KEY (parent_id, child_id)
);

CREATE TABLE IF NOT EXISTS task_runs (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    profile TEXT,
    outcome TEXT NOT NULL DEFAULT 'active',
    summary TEXT,
    metadata TEXT,
    error TEXT,
    started_at REAL NOT NULL,
    ended_at REAL
);

CREATE TABLE IF NOT EXISTS task_comments (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    author TEXT,
    body TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS task_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    run_id TEXT,
    kind TEXT NOT NULL,
    payload TEXT,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(assignee);
CREATE INDEX IF NOT EXISTS idx_tasks_tenant ON tasks(tenant);
CREATE INDEX IF NOT EXISTS idx_task_events_id ON task_events(id);
"""


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _parse_json(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _row_to_task(row: aiosqlite.Row, *, links: dict[str, list[str]] | None = None) -> Task:
    parent_ids: list[str] = []
    child_ids: list[str] = []
    if links:
        parent_ids = links.get("parents", {}).get(row["id"], [])
        child_ids = links.get("children", {}).get(row["id"], [])
    return Task(
        id=row["id"],
        title=row["title"],
        body=row["body"],
        status=row["status"],
        assignee=row["assignee"],
        tenant=row["tenant"],
        priority=row["priority"],
        archived=bool(row["archived"]),
        current_run_id=row["current_run_id"],
        failure_count=row["failure_count"],
        max_retries=row["max_retries"],
        idempotency_key=row["idempotency_key"],
        model_override=_parse_json(row["model_override"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        parent_ids=parent_ids,
        child_ids=child_ids,
    )


class KanbanDB:
    """Async SQLite-backed kanban store."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    @classmethod
    def for_profile(cls, profile: str | None = None) -> KanbanDB:
        home = get_emperor_home(normalize_profile(profile))
        home.mkdir(parents=True, exist_ok=True)
        return cls(home / "kanban.db")

    async def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(SCHEMA)
            await db.commit()

    def _connect(self):
        return aiosqlite.connect(self.db_path)

    async def _load_links(self, db: aiosqlite.Connection) -> dict[str, dict[str, list[str]]]:
        parents: dict[str, list[str]] = {}
        children: dict[str, list[str]] = {}
        async with db.execute("SELECT parent_id, child_id FROM task_links") as cur:
            async for row in cur:
                pid, cid = row["parent_id"], row["child_id"]
                parents.setdefault(cid, []).append(pid)
                children.setdefault(pid, []).append(cid)
        return {"parents": parents, "children": children}

    async def append_event(
        self,
        db: aiosqlite.Connection,
        task_id: str,
        kind: str,
        payload: dict[str, Any] | None = None,
        *,
        run_id: str | None = None,
    ) -> int:
        now = time.time()
        cur = await db.execute(
            """
            INSERT INTO task_events (task_id, run_id, kind, payload, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (task_id, run_id, kind, json.dumps(payload or {}), now),
        )
        return cur.lastrowid or 0

    async def create_task(
        self,
        title: str,
        *,
        body: str | None = None,
        assignee: str | None = None,
        tenant: str | None = None,
        priority: int = 3,
        status: str | None = None,
        triage: bool = False,
        parent_ids: list[str] | None = None,
        idempotency_key: str | None = None,
        max_retries: int | None = None,
        model_override: dict[str, Any] | None = None,
    ) -> Task:
        await self.initialize()
        now = time.time()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            if idempotency_key:
                async with db.execute(
                    "SELECT id FROM tasks WHERE idempotency_key = ?", (idempotency_key,)
                ) as cur:
                    row = await cur.fetchone()
                    if row:
                        return await self.get_task(row["id"])  # type: ignore[return-value]

            if status is None:
                if triage:
                    status = "triage"
                elif parent_ids:
                    status = "todo"
                elif assignee:
                    status = "ready"
                else:
                    status = "todo"

            task_id = _new_id("t")
            await db.execute(
                """
                INSERT INTO tasks (
                    id, title, body, status, assignee, tenant, priority,
                    archived, failure_count, max_retries, idempotency_key,
                    model_override, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    title,
                    body,
                    status,
                    assignee,
                    tenant,
                    priority,
                    max_retries,
                    idempotency_key,
                    json.dumps(model_override) if model_override else None,
                    now,
                    now,
                ),
            )
            for pid in parent_ids or []:
                await self._add_link(db, pid, task_id, check_cycle=False)

            await self.append_event(
                db,
                task_id,
                "created",
                {
                    "assignee": assignee,
                    "status": status,
                    "parents": parent_ids or [],
                    "tenant": tenant,
                },
            )
            await db.commit()

        await self.promote_ready()
        return await self.get_task(task_id)  # type: ignore[return-value]

    async def get_task(self, task_id: str) -> Task | None:
        await self.initialize()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            links = await self._load_links(db)
            async with db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)) as cur:
                row = await cur.fetchone()
                if not row:
                    return None
                task = _row_to_task(row, links=links)

            async with db.execute(
                "SELECT * FROM task_comments WHERE task_id = ? ORDER BY created_at",
                (task_id,),
            ) as cur:
                task.comments = [
                    TaskComment(
                        id=r["id"],
                        task_id=r["task_id"],
                        author=r["author"],
                        body=r["body"],
                        created_at=r["created_at"],
                    )
                    async for r in cur
                ]

            async with db.execute(
                "SELECT * FROM task_runs WHERE task_id = ? ORDER BY started_at",
                (task_id,),
            ) as cur:
                task.runs = [
                    TaskRun(
                        id=r["id"],
                        task_id=r["task_id"],
                        profile=r["profile"],
                        outcome=r["outcome"],
                        summary=r["summary"],
                        metadata=_parse_json(r["metadata"]),
                        error=r["error"],
                        started_at=r["started_at"],
                        ended_at=r["ended_at"],
                    )
                    async for r in cur
                ]

            async with db.execute(
                """
                SELECT * FROM task_events WHERE task_id = ?
                ORDER BY id DESC LIMIT 20
                """,
                (task_id,),
            ) as cur:
                task.events = [
                    TaskEvent(
                        id=r["id"],
                        task_id=r["task_id"],
                        run_id=r["run_id"],
                        kind=r["kind"],
                        payload=_parse_json(r["payload"]) or {},
                        created_at=r["created_at"],
                    )
                    async for r in cur
                ]
            return task

    async def list_tasks(
        self,
        *,
        status: str | None = None,
        assignee: str | None = None,
        tenant: str | None = None,
        include_archived: bool = False,
    ) -> list[Task]:
        await self.initialize()
        clauses = ["1=1"]
        params: list[Any] = []
        if not include_archived:
            clauses.append("archived = 0")
        if status:
            clauses.append("status = ?")
            params.append(status)
        if assignee:
            clauses.append("assignee = ?")
            params.append(assignee)
        if tenant:
            clauses.append("tenant = ?")
            params.append(tenant)
        sql = f"SELECT * FROM tasks WHERE {' AND '.join(clauses)} ORDER BY priority, updated_at"
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            links = await self._load_links(db)
            async with db.execute(sql, params) as cur:
                return [_row_to_task(r, links=links) async for r in cur]

    async def get_board(
        self,
        *,
        tenant: str | None = None,
        assignee: str | None = None,
        search: str | None = None,
        include_archived: bool = False,
    ) -> dict[str, Any]:
        tasks = await self.list_tasks(tenant=tenant, assignee=assignee, include_archived=include_archived)
        if search:
            q = search.lower()
            tasks = [t for t in tasks if q in t.title.lower() or (t.body and q in t.body.lower())]

        columns: dict[str, list[dict[str, Any]]] = {c: [] for c in COLUMNS}
        tenants: set[str] = set()
        assignees: set[str] = set()
        for t in tasks:
            if t.archived:
                continue
            col = t.status if t.status in columns else "todo"
            columns[col].append(t.to_card_dict())
            if t.tenant:
                tenants.add(t.tenant)
            if t.assignee:
                assignees.add(t.assignee)

        return {
            "columns": columns,
            "tenants": sorted(tenants),
            "assignees": sorted(assignees),
        }

    async def update_task(self, task_id: str, patch: dict[str, Any]) -> Task | None:
        await self.initialize()
        allowed = {
            "title",
            "body",
            "status",
            "assignee",
            "tenant",
            "priority",
            "archived",
            "model_override",
        }
        updates = {k: v for k, v in patch.items() if k in allowed}
        if not updates:
            return await self.get_task(task_id)

        now = time.time()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            task_row = await self._get_row(db, task_id)
            if not task_row:
                return None

            old_status = task_row["status"]
            run_id = task_row["current_run_id"]

            if "status" in updates and updates["status"] != old_status:
                new_status = updates["status"]
                if old_status == "running" and new_status != "running" and run_id:
                    await self._close_run(db, run_id, outcome="reclaimed")

            set_parts = ["updated_at = ?"]
            params: list[Any] = [now]
            for key, val in updates.items():
                if key == "model_override":
                    set_parts.append("model_override = ?")
                    params.append(json.dumps(val) if val else None)
                elif key == "archived":
                    set_parts.append("archived = ?")
                    params.append(1 if val else 0)
                else:
                    set_parts.append(f"{key} = ?")
                    params.append(val)
            params.append(task_id)
            await db.execute(f"UPDATE tasks SET {', '.join(set_parts)} WHERE id = ?", params)

            if "status" in updates:
                await self.append_event(
                    db,
                    task_id,
                    "status",
                    {"status": updates["status"], "from": old_status},
                    run_id=run_id if old_status == "running" else None,
                )
            if "assignee" in updates:
                await self.append_event(db, task_id, "assigned", {"assignee": updates["assignee"]})
            if "title" in updates or "body" in updates:
                fields = [k for k in ("title", "body") if k in updates]
                await self.append_event(db, task_id, "edited", {"fields": fields})
            if "priority" in updates:
                await self.append_event(
                    db, task_id, "reprioritized", {"priority": updates["priority"]}
                )
            if updates.get("archived"):
                await self.append_event(db, task_id, "archived", {}, run_id=run_id)

            await db.commit()

        if "status" in updates:
            await self.promote_ready()
        return await self.get_task(task_id)

    async def _get_row(self, db: aiosqlite.Connection, task_id: str) -> aiosqlite.Row | None:
        async with db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)) as cur:
            return await cur.fetchone()

    async def _would_create_cycle(
        self, db: aiosqlite.Connection, parent_id: str, child_id: str
    ) -> bool:
        if parent_id == child_id:
            return True
        visited: set[str] = set()
        stack = [child_id]
        while stack:
            node = stack.pop()
            if node == parent_id:
                return True
            if node in visited:
                continue
            visited.add(node)
            async with db.execute(
                "SELECT child_id FROM task_links WHERE parent_id = ?", (node,)
            ) as cur:
                stack.extend([r["child_id"] async for r in cur])
        return False

    async def _add_link(
        self,
        db: aiosqlite.Connection,
        parent_id: str,
        child_id: str,
        *,
        check_cycle: bool = True,
    ) -> None:
        if check_cycle and await self._would_create_cycle(db, parent_id, child_id):
            raise ValueError(f"Link {parent_id} -> {child_id} would create a cycle")
        await db.execute(
            "INSERT OR IGNORE INTO task_links (parent_id, child_id) VALUES (?, ?)",
            (parent_id, child_id),
        )

    async def add_link(self, parent_id: str, child_id: str) -> None:
        await self.initialize()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            await self._add_link(db, parent_id, child_id)
            await db.commit()
        await self.promote_ready()

    async def remove_link(self, parent_id: str, child_id: str) -> None:
        await self.initialize()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                "DELETE FROM task_links WHERE parent_id = ? AND child_id = ?",
                (parent_id, child_id),
            )
            await db.commit()

    async def _parents_done(self, db: aiosqlite.Connection, task_id: str) -> bool:
        async with db.execute(
            """
            SELECT p.status FROM task_links l
            JOIN tasks p ON p.id = l.parent_id
            WHERE l.child_id = ?
            """,
            (task_id,),
        ) as cur:
            parents = [r["status"] async for r in cur]
        if not parents:
            return True
        return all(s == "done" for s in parents)

    async def promote_ready(self) -> int:
        """Promote todo tasks whose parents are all done to ready."""
        await self.initialize()
        promoted = 0
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id FROM tasks WHERE status = 'todo' AND archived = 0"
            ) as cur:
                todo_ids = [r["id"] async for r in cur]
            for tid in todo_ids:
                if await self._parents_done(db, tid):
                    row = await self._get_row(db, tid)
                    if not row or row["status"] != "todo":
                        continue
                    await db.execute(
                        "UPDATE tasks SET status = 'ready', updated_at = ? WHERE id = ?",
                        (time.time(), tid),
                    )
                    await self.append_event(db, tid, "promoted", {})
                    promoted += 1
            await db.commit()
        return promoted

    async def claim_task(
        self,
        task_id: str,
        *,
        profile: str | None = None,
        ttl_seconds: int = 3600,
    ) -> TaskRun | None:
        await self.initialize()
        now = time.time()
        run_id = _new_id("r")
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            async with db.execute(
                "SELECT * FROM tasks WHERE id = ? AND status = 'ready'", (task_id,)
            ) as cur:
                row = await cur.fetchone()
                if not row:
                    await db.execute("ROLLBACK")
                    return None

            await db.execute(
                """
                INSERT INTO task_runs (id, task_id, profile, outcome, started_at)
                VALUES (?, ?, ?, 'active', ?)
                """,
                (run_id, task_id, profile or row["assignee"], now),
            )
            await db.execute(
                """
                UPDATE tasks SET status = 'running', current_run_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (run_id, now, task_id),
            )
            await self.append_event(
                db,
                task_id,
                "claimed",
                {"lock": profile, "expires": now + ttl_seconds, "run_id": run_id},
                run_id=run_id,
            )
            await db.commit()

        return TaskRun(
            id=run_id,
            task_id=task_id,
            profile=profile or row["assignee"],
            outcome="active",
            summary=None,
            metadata=None,
            error=None,
            started_at=now,
            ended_at=None,
        )

    async def _close_run(
        self,
        db: aiosqlite.Connection,
        run_id: str,
        *,
        outcome: str,
        summary: str | None = None,
        metadata: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        now = time.time()
        await db.execute(
            """
            UPDATE task_runs SET outcome = ?, summary = ?, metadata = ?, error = ?, ended_at = ?
            WHERE id = ?
            """,
            (
                outcome,
                summary,
                json.dumps(metadata) if metadata else None,
                error,
                now,
                run_id,
            ),
        )

    async def complete_task(
        self,
        task_id: str,
        *,
        summary: str | None = None,
        metadata: dict[str, Any] | None = None,
        result: str | None = None,
    ) -> Task | None:
        await self.initialize()
        now = time.time()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            row = await self._get_row(db, task_id)
            if not row:
                return None

            run_id = row["current_run_id"]
            if not run_id and (summary or metadata):
                run_id = _new_id("r")
                await db.execute(
                    """
                    INSERT INTO task_runs (id, task_id, profile, outcome, summary, metadata, started_at, ended_at)
                    VALUES (?, ?, ?, 'completed', ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        task_id,
                        row["assignee"],
                        summary,
                        json.dumps(metadata) if metadata else None,
                        now,
                        now,
                    ),
                )
            elif run_id:
                await self._close_run(
                    db, run_id, outcome="completed", summary=summary, metadata=metadata
                )

            body = row["body"] or ""
            if result:
                body = f"{body}\n\nResult: {result}".strip()

            await db.execute(
                """
                UPDATE tasks SET status = 'done', current_run_id = NULL, body = ?, updated_at = ?
                WHERE id = ?
                """,
                (body or None, now, task_id),
            )
            await self.append_event(
                db,
                task_id,
                "completed",
                {"result_len": len(result or ""), "summary": (summary or "")[:400]},
                run_id=run_id,
            )
            await db.commit()

        await self.promote_ready()
        return await self.get_task(task_id)

    async def block_task(
        self,
        task_id: str,
        *,
        reason: str,
        profile: str | None = None,
    ) -> Task | None:
        await self.initialize()
        now = time.time()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            row = await self._get_row(db, task_id)
            if not row:
                return None

            run_id = row["current_run_id"]
            if not run_id:
                run_id = _new_id("r")
                await db.execute(
                    """
                    INSERT INTO task_runs (id, task_id, profile, outcome, error, started_at, ended_at)
                    VALUES (?, ?, ?, 'blocked', ?, ?, ?)
                    """,
                    (run_id, task_id, profile or row["assignee"], reason, now, now),
                )
            else:
                await self._close_run(db, run_id, outcome="blocked", error=reason)

            await db.execute(
                """
                UPDATE tasks SET status = 'blocked', current_run_id = NULL, updated_at = ?
                WHERE id = ?
                """,
                (now, task_id),
            )
            await self.append_event(
                db, task_id, "blocked", {"reason": reason}, run_id=run_id
            )
            await db.commit()
        return await self.get_task(task_id)

    async def unblock_task(self, task_id: str) -> Task | None:
        await self.initialize()
        now = time.time()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            row = await self._get_row(db, task_id)
            if not row or row["status"] != "blocked":
                return await self.get_task(task_id)
            await db.execute(
                "UPDATE tasks SET status = 'ready', updated_at = ? WHERE id = ?",
                (now, task_id),
            )
            await self.append_event(db, task_id, "unblocked", {})
            await db.commit()
        return await self.get_task(task_id)

    async def append_comment(
        self, task_id: str, body: str, *, author: str | None = None
    ) -> TaskComment:
        await self.initialize()
        cid = _new_id("c")
        now = time.time()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                """
                INSERT INTO task_comments (id, task_id, author, body, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (cid, task_id, author, body, now),
            )
            await db.commit()
        return TaskComment(id=cid, task_id=task_id, author=author, body=body, created_at=now)

    async def list_events(self, since_id: int = 0, limit: int = 100) -> list[TaskEvent]:
        await self.initialize()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT * FROM task_events WHERE id > ? ORDER BY id LIMIT ?
                """,
                (since_id, limit),
            ) as cur:
                return [
                    TaskEvent(
                        id=r["id"],
                        task_id=r["task_id"],
                        run_id=r["run_id"],
                        kind=r["kind"],
                        payload=_parse_json(r["payload"]) or {},
                        created_at=r["created_at"],
                    )
                    async for r in cur
                ]

    async def stats(self) -> dict[str, Any]:
        await self.initialize()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            by_status: dict[str, int] = {}
            async with db.execute(
                "SELECT status, COUNT(*) as c FROM tasks WHERE archived = 0 GROUP BY status"
            ) as cur:
                async for r in cur:
                    by_status[r["status"]] = r["c"]
            by_assignee: dict[str, int] = {}
            async with db.execute(
                """
                SELECT assignee, COUNT(*) as c FROM tasks
                WHERE archived = 0 AND assignee IS NOT NULL GROUP BY assignee
                """
            ) as cur:
                async for r in cur:
                    by_assignee[r["assignee"]] = r["c"]
        return {"by_status": by_status, "by_assignee": by_assignee}

    async def record_spawn_failure(self, task_id: str, error: str, *, max_retries: int = 2) -> None:
        await self.initialize()
        now = time.time()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            row = await self._get_row(db, task_id)
            if not row:
                return
            run_id = row["current_run_id"]
            failure_count = row["failure_count"] + 1
            limit = row["max_retries"] if row["max_retries"] is not None else max_retries

            if run_id:
                outcome = "gave_up" if failure_count >= limit else "spawn_failed"
                await self._close_run(db, run_id, outcome=outcome, error=error)
            else:
                outcome = "spawn_failed"

            if failure_count >= limit:
                await db.execute(
                    """
                    UPDATE tasks SET status = 'blocked', current_run_id = NULL,
                    failure_count = ?, updated_at = ? WHERE id = ?
                    """,
                    (failure_count, now, task_id),
                )
                await self.append_event(db, task_id, "gave_up", {"error": error})
            else:
                await db.execute(
                    """
                    UPDATE tasks SET status = 'ready', current_run_id = NULL,
                    failure_count = ?, updated_at = ? WHERE id = ?
                    """,
                    (failure_count, now, task_id),
                )
                await self.append_event(
                    db, task_id, "spawn_failed", {"error": error}, run_id=run_id
                )
            await db.commit()

    async def reclaim_task(self, task_id: str, *, reason: str = "crashed") -> None:
        await self.initialize()
        now = time.time()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            row = await self._get_row(db, task_id)
            if not row or row["status"] != "running":
                return
            run_id = row["current_run_id"]
            if run_id:
                await self._close_run(db, run_id, outcome=reason, error=reason)
            await db.execute(
                "UPDATE tasks SET status = 'ready', current_run_id = NULL, updated_at = ? WHERE id = ?",
                (now, task_id),
            )
            await self.append_event(db, task_id, reason, {"reason": reason}, run_id=run_id)
            await db.commit()

    async def heartbeat(self, task_id: str, *, note: str | None = None) -> None:
        await self.initialize()
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            row = await self._get_row(db, task_id)
            run_id = row["current_run_id"] if row else None
            await self.append_event(
                db, task_id, "heartbeat", {"note": note} if note else {}, run_id=run_id
            )
            await db.commit()
