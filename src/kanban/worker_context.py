"""Build worker_context for kanban_show."""

from __future__ import annotations

from typing import Any

from kanban.db import KanbanDB
from kanban.models import Task


async def build_worker_context(db: KanbanDB, task: Task) -> str:
    lines: list[str] = [
        f"# Task {task.id}: {task.title}",
        "",
        "## Description",
        task.body or "(no body)",
        "",
    ]

    if task.parent_ids:
        lines.append("## Parent handoffs")
        for pid in task.parent_ids:
            parent = await db.get_task(pid)
            if not parent:
                continue
            lines.append(f"### Parent {pid}: {parent.title}")
            for run in reversed(parent.runs):
                if run.outcome == "completed":
                    if run.summary:
                        lines.append(f"Summary: {run.summary}")
                    if run.metadata:
                        lines.append(f"Metadata: {run.metadata}")
                    break
        lines.append("")

    if task.runs:
        lines.append("## Prior attempts on this task")
        for run in task.runs:
            if run.outcome == "active":
                continue
            lines.append(f"- Run {run.id}: {run.outcome}")
            if run.error:
                lines.append(f"  Error: {run.error}")
            if run.summary:
                lines.append(f"  Summary: {run.summary}")
        lines.append("")

    if task.comments:
        lines.append("## Comments")
        for c in task.comments:
            author = c.author or "unknown"
            lines.append(f"- @{author}: {c.body}")
        lines.append("")

    return "\n".join(lines)


def task_summary_dict(task: Task) -> dict[str, Any]:
    return {
        "id": task.id,
        "title": task.title,
        "status": task.status,
        "assignee": task.assignee,
        "tenant": task.tenant,
        "priority": task.priority,
        "body": task.body,
        "parent_ids": task.parent_ids,
        "child_ids": task.child_ids,
    }
