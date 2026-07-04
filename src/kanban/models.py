"""Kanban domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

STATUSES = ("triage", "todo", "ready", "running", "blocked", "done", "archived")
COLUMNS = ("triage", "todo", "ready", "running", "blocked", "done")


@dataclass
class TaskRun:
    id: str
    task_id: str
    profile: str | None
    outcome: str
    summary: str | None
    metadata: dict[str, Any] | None
    error: str | None
    started_at: float
    ended_at: float | None


@dataclass
class TaskComment:
    id: str
    task_id: str
    author: str | None
    body: str
    created_at: float


@dataclass
class TaskEvent:
    id: int
    task_id: str
    run_id: str | None
    kind: str
    payload: dict[str, Any]
    created_at: float


@dataclass
class Task:
    id: str
    title: str
    body: str | None
    status: str
    assignee: str | None
    tenant: str | None
    priority: int
    archived: bool
    current_run_id: str | None
    failure_count: int
    max_retries: int | None
    idempotency_key: str | None
    model_override: dict[str, Any] | None
    created_at: float
    updated_at: float
    parent_ids: list[str] = field(default_factory=list)
    child_ids: list[str] = field(default_factory=list)
    comments: list[TaskComment] = field(default_factory=list)
    events: list[TaskEvent] = field(default_factory=list)
    runs: list[TaskRun] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "body": self.body,
            "status": self.status,
            "assignee": self.assignee,
            "tenant": self.tenant,
            "priority": self.priority,
            "archived": self.archived,
            "current_run_id": self.current_run_id,
            "failure_count": self.failure_count,
            "max_retries": self.max_retries,
            "idempotency_key": self.idempotency_key,
            "model_override": self.model_override,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "parent_ids": self.parent_ids,
            "child_ids": self.child_ids,
            "comments": [
                {
                    "id": c.id,
                    "author": c.author,
                    "body": c.body,
                    "created_at": c.created_at,
                }
                for c in self.comments
            ],
            "runs": [
                {
                    "id": r.id,
                    "profile": r.profile,
                    "outcome": r.outcome,
                    "summary": r.summary,
                    "metadata": r.metadata,
                    "error": r.error,
                    "started_at": r.started_at,
                    "ended_at": r.ended_at,
                }
                for r in self.runs
            ],
        }

    def to_card_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "assignee": self.assignee,
            "tenant": self.tenant,
            "priority": self.priority,
            "archived": self.archived,
            "updated_at": self.updated_at,
            "parent_ids": self.parent_ids,
            "child_ids": self.child_ids,
        }
