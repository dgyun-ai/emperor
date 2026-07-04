"""Kanban REST and WebSocket API routes."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from config.models import EmperorConfig
from dashboard.context import get_request_config, get_request_db, get_request_profile, get_ws_db
from dashboard.state import load_dashboard_state, verify_token
from kanban.db import KanbanDB

router = APIRouter(prefix="/api/kanban", tags=["kanban"])

_db: KanbanDB | None = None
_config: EmperorConfig | None = None
_dispatcher_tick: Any = None


def configure_kanban_api(
    db: KanbanDB,
    config: EmperorConfig,
    *,
    dispatcher_tick: Any = None,
) -> None:
    global _db, _config, _dispatcher_tick
    _db = db
    _config = config
    _dispatcher_tick = dispatcher_tick


def _get_db() -> KanbanDB:
    if _db is None:
        raise HTTPException(503, "Kanban DB not initialized")
    return _db


class CreateTaskRequest(BaseModel):
    title: str
    body: str | None = None
    assignee: str | None = None
    tenant: str | None = None
    priority: int = 3
    triage: bool = False
    parents: list[str] = Field(default_factory=list)
    idempotency_key: str | None = None
    max_retries: int | None = None
    model_override: dict[str, Any] | None = None


class UpdateTaskRequest(BaseModel):
    title: str | None = None
    body: str | None = None
    status: str | None = None
    assignee: str | None = None
    tenant: str | None = None
    priority: int | None = None
    archived: bool | None = None
    model_override: dict[str, Any] | None = None
    summary: str | None = None
    metadata: dict[str, Any] | None = None
    reason: str | None = None


class BulkUpdateRequest(BaseModel):
    ids: list[str]
    patch: UpdateTaskRequest


class CommentRequest(BaseModel):
    body: str
    author: str | None = None


class LinkRequest(BaseModel):
    parent_id: str
    child_id: str


@router.get("/board")
async def get_board(
    request: Request,
    tenant: str | None = None,
    assignee: str | None = None,
    search: str | None = None,
    include_archived: bool = False,
):
    db = get_request_db(request)
    return await db.get_board(
        tenant=tenant,
        assignee=assignee,
        search=search,
        include_archived=include_archived,
    )


@router.get("/config")
async def get_kanban_ui_config(request: Request):
    cfg = get_request_config(request)
    k = cfg.dashboard.kanban
    return {
        "default_tenant": k.default_tenant,
        "lane_by_profile": k.lane_by_profile,
        "include_archived_by_default": k.include_archived_by_default,
        "render_markdown": k.render_markdown,
    }


@router.get("/profiles")
async def list_profiles():
    from dashboard.state import list_profiles as list_dashboard_profiles

    return {"profiles": sorted({p["name"] for p in list_dashboard_profiles()})}


@router.get("/tasks/{task_id}")
async def get_task(request: Request, task_id: str):
    db = get_request_db(request)
    task = await db.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return task.to_dict()


@router.post("/tasks")
async def create_task(request: Request, req: CreateTaskRequest):
    db = get_request_db(request)
    task = await db.create_task(
        req.title,
        body=req.body,
        assignee=req.assignee,
        tenant=req.tenant,
        priority=req.priority,
        triage=req.triage,
        parent_ids=req.parents or None,
        idempotency_key=req.idempotency_key,
        max_retries=req.max_retries,
        model_override=req.model_override,
    )
    return task.to_dict()


@router.patch("/tasks/{task_id}")
async def update_task(request: Request, task_id: str, req: UpdateTaskRequest):
    db = get_request_db(request)
    patch = req.model_dump(exclude_none=True)
    status = patch.pop("status", None)
    summary = patch.pop("summary", None)
    metadata = patch.pop("metadata", None)
    reason = patch.pop("reason", None)

    if status == "done" or (summary or metadata):
        task = await db.complete_task(task_id, summary=summary, metadata=metadata)
    elif status == "blocked" or reason:
        task = await db.block_task(task_id, reason=reason or "blocked")
    elif status == "ready" and not patch:
        task = await db.unblock_task(task_id)
    else:
        if status:
            patch["status"] = status
        task = await db.update_task(task_id, patch)

    if not task:
        raise HTTPException(404, "Task not found")
    return task.to_dict()


@router.post("/tasks/bulk")
async def bulk_update(request: Request, req: BulkUpdateRequest):
    db = get_request_db(request)
    results: list[dict[str, Any]] = []
    patch = req.patch.model_dump(exclude_none=True)
    for tid in req.ids:
        try:
            task = await db.update_task(tid, patch)
            results.append({"id": tid, "ok": task is not None})
        except Exception as exc:  # noqa: BLE001
            results.append({"id": tid, "ok": False, "error": str(exc)})
    return {"results": results}


@router.post("/tasks/{task_id}/comments")
async def add_comment(request: Request, task_id: str, req: CommentRequest):
    db = get_request_db(request)
    task = await db.get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    comment = await db.append_comment(task_id, req.body, author=req.author)
    return {
        "id": comment.id,
        "author": comment.author,
        "body": comment.body,
        "created_at": comment.created_at,
    }


@router.post("/links")
async def add_link(request: Request, req: LinkRequest):
    db = get_request_db(request)
    try:
        await db.add_link(req.parent_id, req.child_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True}


@router.delete("/links")
async def remove_link(request: Request, parent_id: str, child_id: str):
    db = get_request_db(request)
    await db.remove_link(parent_id, child_id)
    return {"ok": True}


@router.post("/dispatch")
async def dispatch_nudge(max_tasks: int = 5, dry_run: bool = False):
    if _dispatcher_tick is None:
        raise HTTPException(503, "Dispatcher not running")
    result = await _dispatcher_tick(max_tasks=max_tasks, dry_run=dry_run)
    return result


@router.get("/stats")
async def stats(request: Request):
    db = get_request_db(request)
    return await db.stats()


@router.websocket("/events")
async def events_ws(websocket: WebSocket, since: int = 0):
    state = load_dashboard_state()
    token = websocket.query_params.get("token")
    if not state.initialized or not token or not verify_token(token, state=state):
        await websocket.close(code=4401)
        return
    await websocket.accept()
    db = get_ws_db(websocket)
    last_id = since
    try:
        while True:
            events = await db.list_events(since_id=last_id)
            for ev in events:
                await websocket.send_json(
                    {
                        "id": ev.id,
                        "task_id": ev.task_id,
                        "run_id": ev.run_id,
                        "kind": ev.kind,
                        "payload": ev.payload,
                        "created_at": ev.created_at,
                    }
                )
                last_id = ev.id
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        return
