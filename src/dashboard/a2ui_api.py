"""A2UI action API — relay user interactions back to the agent."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from dashboard.chat_api import (
    _abort_events,
    _build_engine,
    _processing,
    _steer_queues,
)
from dashboard.context import get_request_config, get_request_profile
from dashboard.openai_sse import error_sse, steer_dequeued_sse, steer_queued_sse
from dashboard.session_meta import get_meta, set_meta
from dashboard.sse import agent_events_to_sse
from emperor_a2ui.action_format import format_a2ui_action_message as build_a2ui_action_text

router = APIRouter(prefix="/api/chat", tags=["a2ui"])


class A2uiActionRequest(BaseModel):
    surfaceId: str = Field(min_length=1)
    action: dict[str, Any]
    context: dict[str, Any] = Field(default_factory=dict)
    dataModel: dict[str, Any] | None = None
    steer: bool = False


def format_a2ui_action_request(req: A2uiActionRequest) -> str:
    return build_a2ui_action_text(
        surface_id=req.surfaceId,
        action=req.action,
        context=req.context,
        data_model=req.dataModel,
    )


@router.post("/sessions/{session_id}/a2ui-action")
async def post_a2ui_action(request: Request, session_id: str, req: A2uiActionRequest):
    profile = get_request_profile(request)
    config = get_request_config(request)
    if not config.dashboard.chat.a2ui_enabled:
        raise HTTPException(400, "A2UI is disabled")

    content = format_a2ui_action_request(req)

    if _processing.get(session_id) and req.steer:
        _steer_queues.setdefault(session_id, []).append(content)
        ev = _abort_events.get(session_id)
        if ev:
            ev.set()

        async def steer_ack():
            for chunk in steer_queued_sse(content):
                yield chunk

        return StreamingResponse(steer_ack(), media_type="text/event-stream")

    if _processing.get(session_id):
        raise HTTPException(409, "Session is processing; pass steer=true to inject")

    session_meta = get_meta(profile, session_id)
    model_override = None
    if session_meta.get("model"):
        model_override = {"model": session_meta["model"]}

    abort = asyncio.Event()
    _abort_events[session_id] = abort
    _processing[session_id] = True
    engine = _build_engine(
        profile=profile,
        config=config,
        session_id=session_id,
        model_override=model_override,
    )
    await engine.initialize()
    await engine.resume_session(session_id)

    model_name = engine.config.provider.model or "default"

    async def stream():
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
                content_local = queued.pop(0)
                abort_event = asyncio.Event()
                _abort_events[session_id] = abort_event
                yield steer_dequeued_sse(content_local)
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
