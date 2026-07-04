"""Dashboard chat session API with SSE streaming."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent.deps import AgentDeps
from config.models import EmperorConfig
from dashboard.agents_store import get_agent
from dashboard.context import get_request_config, get_request_profile, get_request_store
from dashboard.schedule_intent import detect_schedule_intent
from dashboard.session_meta import get_meta, set_meta
from dashboard.openai_sse import error_sse, steer_dequeued_sse, steer_queued_sse
from dashboard.sse import agent_events_to_sse
from engine.query_engine import QueryEngine
from provider.runtime import build_provider
from session.convert import bootstrap_session_events, build_user_event, openai_message_to_event, parent_for_next_event
from session.events import has_bootstrap
from session.time_util import format_local_timestamp, session_to_dict
from session.visibility import should_show_in_dashboard
from tools.cron_tool import get_scheduler
from tools.registry import discover_tools, get_tools_for_toolsets
from agent.types import AgentEvent, Terminal

router = APIRouter(prefix="/api/chat", tags=["chat"])

_config: EmperorConfig | None = None
_abort_events: dict[str, asyncio.Event] = {}
_processing: dict[str, bool] = {}
_steer_queues: dict[str, list[str]] = {}


def configure_chat_api(config: EmperorConfig, profile: str | None = None) -> None:
    global _config
    _config = config


def _build_engine(
    *,
    profile: str,
    config: EmperorConfig | None = None,
    session_id: str | None = None,
    toolsets: list[str] | None = None,
    model_override: dict[str, Any] | None = None,
    agent_id: str | None = None,
    system_prompt: str | None = None,
) -> QueryEngine:
    config = config or _config or EmperorConfig()
    resolved_agent_id = agent_id or "default"
    if agent_id or session_id:
        if session_id and not agent_id:
            session_meta = get_meta(profile, session_id)
            resolved_agent_id = str(session_meta.get("agent_id") or "default")
        _, agent_def = get_agent(profile, resolved_agent_id, config=config)
        if not toolsets and agent_def.toolsets:
            toolsets = list(agent_def.toolsets)
        if not model_override and agent_def.model:
            model_override = {"model": agent_def.model}
        if not system_prompt and agent_def.system_prompt:
            system_prompt = agent_def.system_prompt
    if model_override:
        if model_override.get("model"):
            config.provider.model = model_override["model"]
        if model_override.get("base_url"):
            config.provider.base_url = model_override["base_url"]
        if model_override.get("provider"):
            config.provider.provider = model_override["provider"]
    discover_tools()
    ts = toolsets or config.dashboard.chat.default_toolsets
    tools = get_tools_for_toolsets(enabled=ts)
    if os.environ.get("EMPEROR_KANBAN_TASK"):
        if "kanban" not in ts:
            tools = get_tools_for_toolsets(enabled=[*ts, "kanban"])
    if not config.dashboard.chat.a2ui_enabled:
        tools = [t for t in tools if t.name != "render_a2ui"]
    provider = build_provider(config)
    engine = QueryEngine(
        deps=AgentDeps.from_provider(provider),  # type: ignore[arg-type]
        config=config,
        profile=profile,
        tools=tools,
        session_id=session_id,
        system_prompt=system_prompt,
    )
    return engine


@router.get("/sessions")
async def list_sessions(request: Request, limit: int = 50):
    profile = get_request_profile(request)
    store = get_request_store(request)
    await store.initialize()
    sessions = await store.list_sessions(profile=profile, limit=limit)
    return {
        "sessions": [
            {
                **session_to_dict(s),
                "updated_local": format_local_timestamp(s.updated_at),
                "nickname": get_meta(profile, s.id).get("nickname"),
                "model": get_meta(profile, s.id).get("model"),
                "agent_id": get_meta(profile, s.id).get("agent_id") or "default",
            }
            for s in sessions
            if should_show_in_dashboard(s)
        ]
    }


class CreateSessionRequest(BaseModel):
    title: str | None = None
    task_id: str | None = None
    profile: str | None = None
    agent_id: str | None = None


@router.post("/sessions")
async def create_session(request: Request, req: CreateSessionRequest):
    profile = get_request_profile(request)
    store = get_request_store(request)
    await store.initialize()
    sid = await store.create_session(profile=profile, platform="web", title=req.title or "新会话")
    agent_id = req.agent_id or "default"
    get_agent(profile, agent_id, config=get_request_config(request))
    set_meta(profile, sid, {"agent_id": agent_id})
    if req.task_id:
        await store.set_title(sid, f"Task {req.task_id}", force=True)
    return {"session_id": sid}


@router.get("/sessions/{session_id}/messages")
async def get_messages(request: Request, session_id: str):
    store = get_request_store(request)
    await store.initialize()
    events = await store.load_events(session_id)
    return {"events": events}


@router.delete("/sessions/{session_id}")
async def delete_session(request: Request, session_id: str):
    store = get_request_store(request)
    await store.initialize()
    await store.delete_session(session_id)
    return {"ok": True}


class SessionPatchRequest(BaseModel):
    nickname: str | None = None
    model: str | None = None
    agent_id: str | None = None


@router.patch("/sessions/{session_id}")
async def patch_session(request: Request, session_id: str, req: SessionPatchRequest):
    profile = get_request_profile(request)
    patch: dict[str, str | None] = {}
    if req.nickname is not None:
        patch["nickname"] = req.nickname
    if req.model is not None:
        patch["model"] = req.model
    if req.agent_id is not None:
        get_agent(profile, req.agent_id, config=get_request_config(request))
        patch["agent_id"] = req.agent_id
    meta = set_meta(profile, session_id, patch)
    return {"ok": True, "session_id": session_id, **meta}


class ChatMessageRequest(BaseModel):
    content: str
    model_override: dict[str, Any] | None = None
    toolsets: list[str] | None = None
    profile: str | None = None
    steer: bool = False


async def _persist_local_reply(
    *,
    request: Request,
    session_id: str,
    user_content: str,
    assistant_content: str,
) -> None:
    profile = get_request_profile(request)
    store = get_request_store(request)
    await store.initialize()
    events = await store.load_events(session_id)
    if not has_bootstrap(events):
        provider = get_request_config(request).provider.provider or "emperor"
        model = get_request_config(request).provider.model or "default"
        bootstrap = bootstrap_session_events(
            session_id=session_id,
            provider=provider,
            model_id=model,
        )
        await store.append_events(session_id, bootstrap)
        events.extend(bootstrap)

    user_event = build_user_event(user_content, parent_id=parent_for_next_event(events))
    events.append(user_event)
    await store.append_event(session_id, user_event)
    assistant_event = openai_message_to_event(
        {"role": "assistant", "content": assistant_content},
        parent_id=parent_for_next_event(events),
        provider=get_request_config(request).provider.provider or "emperor",
        model=get_request_config(request).provider.model or "default",
        streamed_text=assistant_content,
    )
    await store.append_event(session_id, assistant_event)
    set_meta(profile, session_id, {"last_follow_up_questions": []})


async def _assistant_only_stream(message: str) -> AsyncIterator[AgentEvent]:
    yield AgentEvent("message", {"role": "assistant", "content": message})
    yield AgentEvent(
        "status",
        {
            "terminal": Terminal(
                reason="complete",
                message=message,
                error=None,
            )
        },
    )


async def _handle_schedule_intent(
    request: Request,
    *,
    session_id: str,
    content: str,
) -> StreamingResponse | None:
    parsed = detect_schedule_intent(content, now=datetime.now().astimezone())
    if parsed is None:
        return None

    if parsed.schedule is None or parsed.payload is None:
        reply = parsed.error or "暂时无法创建这个定时任务。"
        await _persist_local_reply(
            request=request,
            session_id=session_id,
            user_content=content,
            assistant_content=reply,
        )
        return StreamingResponse(
            agent_events_to_sse(_assistant_only_stream(reply), model="scheduler"),
            media_type="text/event-stream",
        )

    profile = get_request_profile(request)
    scheduler = get_scheduler(profile)
    try:
        job = scheduler.add_job(
            name=str(parsed.payload.get("message") or parsed.payload.get("text") or "scheduled job")[:80],
            schedule=parsed.schedule,
            payload=parsed.payload,
            target_session_id=session_id,
        )
    except ValueError as exc:
        reply = str(exc)
        await _persist_local_reply(
            request=request,
            session_id=session_id,
            user_content=content,
            assistant_content=reply,
        )
        return StreamingResponse(
            agent_events_to_sse(_assistant_only_stream(reply), model="scheduler"),
            media_type="text/event-stream",
        )
    schedule_kind = str(job.schedule.get("kind") or "")
    if schedule_kind == "at":
        schedule_label = str(job.schedule.get("at") or "")
    elif schedule_kind == "every":
        schedule_label = f"every {job.schedule.get('everyMs')}ms"
    else:
        schedule_label = f"cron {job.schedule.get('expr')} ({job.schedule.get('tz') or 'UTC'})"
    reply = (
        f"已创建定时任务。类型：{schedule_kind}。调度：{schedule_label}。"
        f" 目标会话：{session_id[:8]}。任务 ID：{job.id[:8]}。"
    )
    await _persist_local_reply(
        request=request,
        session_id=session_id,
        user_content=content,
        assistant_content=reply,
    )
    return StreamingResponse(
        agent_events_to_sse(_assistant_only_stream(reply), model="scheduler"),
        media_type="text/event-stream",
    )


@router.post("/sessions/{session_id}/messages")
async def post_message(request: Request, session_id: str, req: ChatMessageRequest):
    profile = get_request_profile(request)
    if _processing.get(session_id) and req.steer:
        _steer_queues.setdefault(session_id, []).append(req.content)
        ev = _abort_events.get(session_id)
        if ev:
            ev.set()

        async def steer_ack():
            for chunk in steer_queued_sse(req.content):
                yield chunk

        return StreamingResponse(steer_ack(), media_type="text/event-stream")

    if _processing.get(session_id):
        raise HTTPException(409, "Session is processing; pass steer=true to inject")

    scheduled = await _handle_schedule_intent(
        request,
        session_id=session_id,
        content=req.content,
    )
    if scheduled is not None:
        return scheduled

    session_meta = get_meta(profile, session_id)
    model_override = req.model_override
    if not model_override and session_meta.get("model"):
        model_override = {"model": session_meta["model"]}

    abort = asyncio.Event()
    _abort_events[session_id] = abort
    _processing[session_id] = True
    engine = _build_engine(
        profile=profile,
        config=get_request_config(request),
        session_id=session_id,
        toolsets=req.toolsets,
        model_override=model_override,
    )
    await engine.initialize()
    await engine.resume_session(session_id)

    model_name = engine.config.provider.model or "default"

    async def stream():
        content = req.content
        abort_event = abort
        try:
            while True:
                async for chunk in agent_events_to_sse(
                    engine.submit_message(content, abort_event=abort_event),
                    model=str(model_name),
                ):
                    yield chunk
                queued = _steer_queues.get(session_id, [])
                if not queued:
                    break
                content = queued.pop(0)
                abort_event = asyncio.Event()
                _abort_events[session_id] = abort_event
                yield steer_dequeued_sse(content)
        except asyncio.CancelledError:
            for chunk in error_sse("aborted"):
                yield chunk
        except Exception as exc:  # noqa: BLE001
            for chunk in error_sse(str(exc)):
                yield chunk
        finally:
            try:
                snap = engine.current_usage_snapshot()
                set_meta(profile, session_id, {"usage_snapshot": snap})
            except Exception:  # noqa: BLE001
                pass
            _abort_events.pop(session_id, None)
            _processing.pop(session_id, None)
            _steer_queues.pop(session_id, None)

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/sessions/{session_id}/abort")
async def abort_session(session_id: str):
    ev = _abort_events.get(session_id)
    if ev:
        ev.set()
        return {"ok": True}
    raise HTTPException(404, "No active stream")
