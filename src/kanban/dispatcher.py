"""Kanban task dispatcher — claims ready tasks and spawns workers."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from config.models import EmperorConfig
from constants import (
    ENV_EMPEROR_KANBAN_TASK,
    ENV_EMPEROR_KANBAN_WORKSPACE,
    ENV_EMPEROR_PROVIDER_OVERRIDE,
    get_emperor_home,
    normalize_profile,
)
from kanban.db import KanbanDB

logger = logging.getLogger(__name__)


class KanbanDispatcher:
    """Poll kanban.db and spawn emperor worker processes."""

    def __init__(
        self,
        db: KanbanDB,
        config: EmperorConfig,
        *,
        profile: str | None = None,
    ) -> None:
        self.db = db
        self.config = config
        self.profile = profile or "default"
        self._running = False
        self._active: dict[str, subprocess.Popen[Any]] = {}

    def _workspace_dir(self, task_id: str) -> Path:
        home = get_emperor_home(normalize_profile(self.profile))
        ws = home / "kanban" / "workspaces" / task_id
        ws.mkdir(parents=True, exist_ok=True)
        return ws

    def _build_env(self, task_id: str, assignee: str | None, model_override: dict | None) -> dict[str, str]:
        env = os.environ.copy()
        env[ENV_EMPEROR_KANBAN_TASK] = task_id
        env[ENV_EMPEROR_KANBAN_WORKSPACE] = str(self._workspace_dir(task_id))
        if assignee:
            env["EMPEROR_PROFILE"] = assignee
        if model_override:
            env[ENV_EMPEROR_PROVIDER_OVERRIDE] = json.dumps(model_override)
        return env

    def _spawn_worker(self, task_id: str, assignee: str | None, model_override: dict | None) -> subprocess.Popen[Any]:
        src = Path(__file__).resolve().parent.parent
        cmd = [
            sys.executable,
            "-m",
            "cli.main",
            "chat",
            "-q",
            "Execute the assigned kanban task using kanban tools.",
        ]
        if assignee and assignee != "default":
            cmd.extend(["-p", assignee])

        env = self._build_env(task_id, assignee, model_override)
        env["PYTHONPATH"] = str(src)
        return subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(self._workspace_dir(task_id)),
        )

    async def tick(self, *, max_tasks: int = 5, dry_run: bool = False) -> dict[str, Any]:
        await self.db.initialize()
        await self.db.promote_ready()
        claimed: list[str] = []
        errors: list[str] = []

        ready = await self.db.list_tasks(status="ready")
        for task in ready[:max_tasks]:
            if task.id in self._active:
                continue
            if dry_run:
                claimed.append(task.id)
                continue
            run = await self.db.claim_task(task.id, profile=task.assignee)
            if not run:
                continue
            try:
                proc = self._spawn_worker(task.id, task.assignee, task.model_override)
                self._active[task.id] = proc
                claimed.append(task.id)
            except Exception as exc:  # noqa: BLE001
                logger.exception("spawn failed for %s", task.id)
                await self.db.record_spawn_failure(
                    task.id,
                    str(exc),
                    max_retries=self.config.kanban.failure_limit,
                )
                errors.append(f"{task.id}: {exc}")

        return {"claimed": claimed, "errors": errors, "dry_run": dry_run}

    async def _poll_active(self) -> None:
        dead: list[str] = []
        for task_id, proc in self._active.items():
            rc = proc.poll()
            if rc is None:
                continue
            dead.append(task_id)
            task = await self.db.get_task(task_id)
            if task and task.status == "running":
                if rc == 0:
                    await self.db.complete_task(task_id, summary="Worker exited without kanban_complete")
                else:
                    err = (proc.stderr.read() if proc.stderr else b"").decode(errors="replace")[:500]
                    await self.db.reclaim_task(task_id, reason="crashed")
                    await self.db.record_spawn_failure(
                        task_id,
                        err or f"exit code {rc}",
                        max_retries=self.config.kanban.failure_limit,
                    )
        for tid in dead:
            self._active.pop(tid, None)

    async def run_loop(self) -> None:
        self._running = True
        interval = self.config.kanban.dispatch_interval_seconds
        while self._running:
            try:
                await self._poll_active()
                await self.tick(max_tasks=5)
            except Exception:  # noqa: BLE001
                logger.exception("dispatcher tick failed")
            await asyncio.sleep(interval)

    def stop(self) -> None:
        self._running = False
        for proc in self._active.values():
            if proc.poll() is None:
                proc.terminate()


async def start_dispatcher(
    config: EmperorConfig,
    profile: str | None = None,
) -> tuple[KanbanDispatcher, asyncio.Task[None]]:
    db = KanbanDB.for_profile(profile)
    dispatcher = KanbanDispatcher(db, config, profile=profile)
    task = asyncio.create_task(dispatcher.run_loop())
    return dispatcher, task
