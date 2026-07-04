"""AG-UI FastAPI endpoint — CopilotKit-compatible SSE transport for Emperor."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from ag_ui.core.events import EventType, RunErrorEvent
from ag_ui.core.types import RunAgentInput
from ag_ui.encoder import EventEncoder
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from dashboard.ag_ui_mapper import agent_events_to_ag_ui_sse, connect_to_ag_ui_sse
from dashboard.sse import SSE_HEADERS
from dashboard.chat_api import (
    _abort_events,
    _build_engine,
    _processing,
    _steer_queues,
)
from dashboard.context import get_request_config, get_request_profile, get_request_store
from dashboard.agents_store import agents_for_runtime
from dashboard.session_meta import get_meta, mark_archived, set_meta
from session.convert import events_to_openai_messages
from session.visibility import should_show_in_dashboard
from emperor_a2ui.action_format import (
    build_a2ui_action_payload,
    format_a2ui_action_message,
    parse_a2ui_action_message,
)

router = APIRouter(prefix="/api/ag-ui", tags=["ag-ui"])

AG_UI_RUNTIME_INFO = {
    "version": "0.1.0",
    "agents": {
        "default": {
            "name": "default",
            "className": "EmperorAgent",
            "description": "Emperor dashboard agent with A2UI support",
        }
    },
    "audioFileTranscriptionEnabled": False,
    "mode": "sse",
    "a2ui": {"enabled": True, "agents": ["default"]},
    "threadEndpoints": {
        "list": True,
        "inspect": False,
        "mutations": True,
        "realtimeMetadata": False,
    },
    "telemetryDisabled": True,
}


class SingleRouteEnvelope(BaseModel):
    """CopilotKit single-endpoint transport envelope."""

    method: str
    params: dict[str, Any] = Field(default_factory=dict)
    body: dict[str, Any] | None = None


def _require_a2ui(config) -> None:
    if not config.dashboard.chat.a2ui_enabled:
        raise HTTPException(400, "A2UI is disabled")


def _runtime_info_response(profile: str, config) -> dict[str, Any]:
    runtime_agents = agents_for_runtime(profile, config=config)
    return {
        **AG_UI_RUNTIME_INFO,
        "agents": runtime_agents,
        "a2ui": {"enabled": True, "agents": list(runtime_agents.keys())},
    }


def _iso_timestamp(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _session_to_thread(session: Any, *, profile: str) -> dict[str, Any]:
    meta = get_meta(profile, session.id)
    agent_id = str(meta.get("agent_id") or "default")
    name = meta.get("nickname") or session.title or None
    updated = float(session.updated_at or session.created_at or 0)
    created = float(session.created_at or updated)
    return {
        "id": session.id,
        "agentId": agent_id,
        "name": name,
        "archived": False,
        "createdAt": _iso_timestamp(created),
        "updatedAt": _iso_timestamp(updated),
        "lastRunAt": _iso_timestamp(updated),
    }


@router.get("/info")
async def ag_ui_info(request: Request):
    _ = get_request_profile(request)
    config = get_request_config(request)
    _require_a2ui(config)
    return _runtime_info_response(get_request_profile(request), config)


@router.post("")
async def ag_ui_single_endpoint(request: Request, envelope: SingleRouteEnvelope):
    """CopilotKit single-endpoint transport (POST /api/ag-ui with method envelope)."""
    config = get_request_config(request)
    _require_a2ui(config)

    method = envelope.method
    params = envelope.params or {}

    if method == "info":
        return _runtime_info_response(get_request_profile(request), config)

    agent_id = str(params.get("agentId") or "default")

    if method == "agent/connect":
        if not envelope.body:
            raise HTTPException(400, "Missing body for agent connect")
        connect_body = RunAgentInput.model_validate(envelope.body)
        return await ag_ui_connect(request, connect_body, agent_id=agent_id)

    if method == "agent/run":
        if not envelope.body:
            raise HTTPException(400, "Missing body for agent run")
        run_body = RunAgentInput.model_validate(envelope.body)
        return await ag_ui_run(request, run_body, agent_id=agent_id)

    if method == "agent/stop":
        return JSONResponse({"ok": True})

    raise HTTPException(404, f"Unsupported AG-UI method: {method}")


@router.get("/threads")
async def list_threads(
    request: Request,
    agentId: str = "default",
    includeArchived: bool = False,
    limit: int = 50,
):
    _ = includeArchived
    profile = get_request_profile(request)
    config = get_request_config(request)
    _require_a2ui(config)
    store = get_request_store(request)
    await store.initialize()
    sessions = await store.list_sessions(profile=profile, limit=limit)
    threads = []
    for session in sessions:
        if not should_show_in_dashboard(session):
            continue
        thread = _session_to_thread(session, profile=profile)
        if agentId != "default" and thread["agentId"] != agentId:
            continue
        threads.append(thread)
    return {"threads": threads, "nextCursor": None}


@router.patch("/threads/{thread_id}")
async def rename_thread(request: Request, thread_id: str, payload: dict[str, Any]):
    profile = get_request_profile(request)
    config = get_request_config(request)
    _require_a2ui(config)
    name = payload.get("name")
    if isinstance(name, str) and name.strip():
        set_meta(profile, thread_id, {"nickname": name.strip()})
    return {"ok": True}


@router.post("/threads/{thread_id}/archive")
async def archive_thread(request: Request, thread_id: str):
    profile = get_request_profile(request)
    config = get_request_config(request)
    _require_a2ui(config)
    mark_archived(profile, thread_id)
    return {"ok": True}


@router.delete("/threads/{thread_id}")
async def delete_thread(request: Request, thread_id: str):
    profile = get_request_profile(request)
    config = get_request_config(request)
    _require_a2ui(config)
    store = get_request_store(request)
    await store.initialize()
    await store.delete_session(thread_id)
    _ = profile
    return {"ok": True}


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                block_type = block.get("type")
                if block_type == "text":
                    text = block.get("text")
                    if isinstance(text, str):
                        parts.append(text)
                continue
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text = getattr(block, "text", None)
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return ""


def _extract_user_content(body: RunAgentInput) -> str:
    """Resolve the user turn from AG-UI RunAgentInput."""
    forwarded = body.forwarded_props
    if isinstance(forwarded, dict):
        a2ui = forwarded.get("a2uiAction") or forwarded.get("a2ui_action")
        if isinstance(a2ui, dict):
            surface_id = str(a2ui.get("surfaceId") or a2ui.get("surface_id") or "")
            action = a2ui.get("action")
            if surface_id and isinstance(action, dict):
                return format_a2ui_action_message(
                    surface_id=surface_id,
                    action=action,
                    context=a2ui.get("context") if isinstance(a2ui.get("context"), dict) else {},
                    data_model=a2ui.get("dataModel") if isinstance(a2ui.get("dataModel"), dict) else None,
                )

    for message in reversed(body.messages):
        role = getattr(message, "role", None)
        if role is None and isinstance(message, dict):
            role = message.get("role")
        if role != "user":
            continue
        content = getattr(message, "content", None)
        if content is None and isinstance(message, dict):
            content = message.get("content")
        text = _message_text(content)
        if text.strip():
            parsed = parse_a2ui_action_message(text)
            if parsed:
                return format_a2ui_action_message(
                    surface_id=str(parsed.get("surfaceId") or ""),
                    action=parsed.get("action") if isinstance(parsed.get("action"), dict) else {},
                    context=parsed.get("context") if isinstance(parsed.get("context"), dict) else {},
                    data_model=parsed.get("dataModel") if isinstance(parsed.get("dataModel"), dict) else None,
                )
            return text.strip()

    resume = body.resume or []
    for entry in resume:
        payload = getattr(entry, "payload", None)
        if payload is None and isinstance(entry, dict):
            payload = entry.get("payload")
        if isinstance(payload, dict):
            surface_id = str(payload.get("surfaceId") or "")
            action = payload.get("action")
            if surface_id and isinstance(action, dict):
                return format_a2ui_action_message(
                    surface_id=surface_id,
                    action=action,
                    context=payload.get("context") if isinstance(payload.get("context"), dict) else {},
                    data_model=payload.get("dataModel") if isinstance(payload.get("dataModel"), dict) else None,
                )

    return ""


def _encode_error(message: str) -> str:
    encoder = EventEncoder()
    return encoder.encode(RunErrorEvent(type=EventType.RUN_ERROR, message=message))


async def ag_ui_connect(request: Request, body: RunAgentInput, agent_id: str = "default"):
    """Establish AG-UI connection and replay session history (no agent execution)."""
    _ = agent_id
    profile = get_request_profile(request)
    config = get_request_config(request)
    _require_a2ui(config)

    session_id = body.thread_id
    if not session_id:
        raise HTTPException(400, "threadId is required")

    run_id = body.run_id or f"run_{uuid.uuid4().hex[:12]}"
    store = get_request_store(request)
    await store.initialize()
    events = await store.load_events(session_id)
    messages = events_to_openai_messages(events)

    async def stream():
        async for chunk in connect_to_ag_ui_sse(
            thread_id=session_id,
            run_id=run_id,
            messages=messages,
        ):
            yield chunk

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.post("/run")
@router.post("/agent/{agent_id}/run")
async def ag_ui_run(request: Request, body: RunAgentInput, agent_id: str = "default"):
    profile = get_request_profile(request)
    config = get_request_config(request)
    _require_a2ui(config)
    _ = agent_id

    session_id = body.thread_id
    if not session_id:
        raise HTTPException(400, "threadId is required")

    content = _extract_user_content(body)
    if not content:
        raise HTTPException(400, "No user message in RunAgentInput")

    if _processing.get(session_id):
        raise HTTPException(409, "Session is processing")

    session_meta = get_meta(profile, session_id)
    model_override = None
    if session_meta.get("model"):
        model_override = {"model": session_meta["model"]}
    session_agent_id = str(session_meta.get("agent_id") or agent_id or "default")

    abort = asyncio.Event()
    _abort_events[session_id] = abort
    _processing[session_id] = True
    run_id = body.run_id or f"run_{uuid.uuid4().hex[:12]}"

    engine = _build_engine(
        profile=profile,
        config=config,
        session_id=session_id,
        model_override=model_override,
        agent_id=session_agent_id,
    )
    await engine.initialize()
    await engine.resume_session(session_id)

    async def stream():
        try:
            async for chunk in agent_events_to_ag_ui_sse(
                engine.submit_message(content, abort_event=abort),
                thread_id=session_id,
                run_id=run_id,
            ):
                yield chunk
        except asyncio.CancelledError:
            yield _encode_error("aborted")
        except Exception as exc:  # noqa: BLE001
            yield _encode_error(str(exc))
        finally:
            try:
                snap = engine.current_usage_snapshot()
                set_meta(profile, session_id, {"usage_snapshot": snap})
            except Exception:  # noqa: BLE001
                pass
            _abort_events.pop(session_id, None)
            _processing.pop(session_id, None)
            _steer_queues.pop(session_id, None)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.post("/agent/{agent_id}/connect")
async def ag_ui_connect_route(request: Request, body: RunAgentInput, agent_id: str):
    return await ag_ui_connect(request, body, agent_id=agent_id)


@router.post("/action")
async def ag_ui_action(request: Request, payload: dict[str, Any]):
    """Structured A2UI action shortcut for CopilotKit clients."""
    profile = get_request_profile(request)
    config = get_request_config(request)
    if not config.dashboard.chat.a2ui_enabled:
        raise HTTPException(400, "A2UI is disabled")

    session_id = str(payload.get("threadId") or payload.get("thread_id") or "")
    if not session_id:
        raise HTTPException(400, "threadId is required")

    surface_id = str(payload.get("surfaceId") or payload.get("surface_id") or "")
    action = payload.get("action")
    if not surface_id or not isinstance(action, dict):
        raise HTTPException(400, "surfaceId and action are required")

    run_body = RunAgentInput(
        thread_id=session_id,
        run_id=f"run_{uuid.uuid4().hex[:12]}",
        state={},
        messages=[],
        tools=[],
        context=[],
        forwarded_props={
            "a2uiAction": build_a2ui_action_payload(
                surface_id=surface_id,
                action=action,
                context=payload.get("context") if isinstance(payload.get("context"), dict) else {},
                data_model=payload.get("dataModel") if isinstance(payload.get("dataModel"), dict) else None,
            ),
        },
    )
    return await ag_ui_run(request, run_body)


@router.post("/agent/{agent_id}/stop/{thread_id}")
async def ag_ui_stop(request: Request, agent_id: str, thread_id: str):
    _ = get_request_profile(request)
    config = get_request_config(request)
    _require_a2ui(config)
    _ = agent_id
    ev = _abort_events.get(thread_id)
    if ev:
        ev.set()
    return {"ok": True}
