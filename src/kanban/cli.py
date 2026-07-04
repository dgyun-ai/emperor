"""CLI commands for emperor kanban."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from kanban.db import KanbanDB
from kanban.dispatcher import KanbanDispatcher


async def run_kanban_cli(args: argparse.Namespace, profile: str | None) -> int:
    db = KanbanDB.for_profile(profile)
    await db.initialize()

    if args.kanban_cmd == "init":
        await db.initialize()
        print(f"Kanban initialized at {db.db_path}")
        return 0

    if args.kanban_cmd == "create":
        task = await db.create_task(
            args.title,
            body=args.body,
            assignee=args.assignee,
            tenant=args.tenant,
            priority=args.priority,
            triage=args.triage,
            parent_ids=args.parent or None,
            idempotency_key=args.idempotency_key,
            max_retries=args.max_retries,
        )
        if args.json:
            print(json.dumps(task.to_dict(), ensure_ascii=False))
        else:
            print(f"Created {task.id} ({task.status})")
        return 0

    if args.kanban_cmd == "list":
        tasks = await db.list_tasks(
            status=args.status,
            assignee=args.assignee,
            tenant=args.tenant,
            include_archived=args.archived,
        )
        if args.json:
            print(json.dumps([t.to_card_dict() for t in tasks], ensure_ascii=False))
        else:
            for t in tasks:
                print(f"{t.id}  [{t.status}]  {t.title}  @{t.assignee or '-'}")
        return 0

    if args.kanban_cmd == "show":
        task = await db.get_task(args.task_id)
        if not task:
            print("Task not found", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(task.to_dict(), ensure_ascii=False))
        else:
            print(f"{task.id}: {task.title} [{task.status}]")
            if task.body:
                print(task.body)
        return 0

    if args.kanban_cmd == "complete":
        for tid in args.task_ids:
            await db.complete_task(tid, summary=args.summary, result=args.result)
        return 0

    if args.kanban_cmd == "block":
        await db.block_task(args.task_ids[0], reason=args.reason)
        return 0

    if args.kanban_cmd == "unblock":
        for tid in args.task_ids:
            await db.unblock_task(tid)
        return 0

    if args.kanban_cmd == "link":
        try:
            await db.add_link(args.parent_id, args.child_id)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        return 0

    if args.kanban_cmd == "unlink":
        await db.remove_link(args.parent_id, args.child_id)
        return 0

    if args.kanban_cmd == "comment":
        await db.append_comment(args.task_id, args.text, author=args.author)
        return 0

    if args.kanban_cmd == "runs":
        task = await db.get_task(args.task_id)
        if not task:
            return 1
        if args.json:
            print(json.dumps([r.__dict__ for r in task.runs], ensure_ascii=False))
        else:
            for i, r in enumerate(task.runs, 1):
                print(f"{i}  {r.outcome}  @{r.profile}  {r.summary or r.error or ''}")
        return 0

    if args.kanban_cmd == "dispatch":
        from config.loader import load_config

        config = load_config(profile=profile)
        disp = KanbanDispatcher(db, config, profile=profile)
        result = await disp.tick(max_tasks=args.max, dry_run=args.dry_run)
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(f"Claimed: {result.get('claimed', [])}")
        return 0

    if args.kanban_cmd == "stats":
        stats = await db.stats()
        if args.json:
            print(json.dumps(stats, ensure_ascii=False))
        else:
            for k, v in stats.get("by_status", {}).items():
                print(f"{k}: {v}")
        return 0

    print("Unknown kanban command", file=sys.stderr)
    return 1


def add_kanban_parser(sub: argparse._SubParsersAction) -> None:
    kanban = sub.add_parser("kanban", help="Kanban task board")
    ksub = kanban.add_subparsers(dest="kanban_cmd")

    ksub.add_parser("init", help="Initialize kanban.db")

    create = ksub.add_parser("create", help="Create a task")
    create.add_argument("title")
    create.add_argument("--body")
    create.add_argument("--assignee")
    create.add_argument("--tenant")
    create.add_argument("--priority", type=int, default=3)
    create.add_argument("--parent", action="append")
    create.add_argument("--triage", action="store_true")
    create.add_argument("--idempotency-key")
    create.add_argument("--max-retries", type=int)
    create.add_argument("--json", action="store_true")

    lst = ksub.add_parser("list", help="List tasks")
    lst.add_argument("--status")
    lst.add_argument("--assignee")
    lst.add_argument("--tenant")
    lst.add_argument("--archived", action="store_true")
    lst.add_argument("--json", action="store_true")

    show = ksub.add_parser("show", help="Show task details")
    show.add_argument("task_id")
    show.add_argument("--json", action="store_true")

    complete = ksub.add_parser("complete", help="Complete tasks")
    complete.add_argument("task_ids", nargs="+")
    complete.add_argument("--summary")
    complete.add_argument("--result")

    block = ksub.add_parser("block", help="Block a task")
    block.add_argument("task_ids", nargs="+")
    block.add_argument("reason")

    unblock = ksub.add_parser("unblock", help="Unblock tasks")
    unblock.add_argument("task_ids", nargs="+")

    link = ksub.add_parser("link", help="Add dependency link")
    link.add_argument("parent_id")
    link.add_argument("child_id")

    unlink = ksub.add_parser("unlink", help="Remove dependency link")
    unlink.add_argument("parent_id")
    unlink.add_argument("child_id")

    comment = ksub.add_parser("comment", help="Add comment")
    comment.add_argument("task_id")
    comment.add_argument("text")
    comment.add_argument("--author")

    runs = ksub.add_parser("runs", help="Show run history")
    runs.add_argument("task_id")
    runs.add_argument("--json", action="store_true")

    dispatch = ksub.add_parser("dispatch", help="Run dispatcher tick")
    dispatch.add_argument("--max", type=int, default=5)
    dispatch.add_argument("--dry-run", action="store_true")
    dispatch.add_argument("--json", action="store_true")

    stats = ksub.add_parser("stats", help="Board statistics")
    stats.add_argument("--json", action="store_true")
