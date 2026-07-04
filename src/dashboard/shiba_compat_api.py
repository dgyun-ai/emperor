"""ShibaClaw-compatible REST API layer over Emperor dashboard backends."""

from __future__ import annotations

import asyncio
import copy
import os
import shutil
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from config.loader import load_config, save_config
from config.models import EmperorConfig, ProviderConfig
from context.usage import build_history_usage_snapshot
from session.convert import events_to_openai_messages
from session.visibility import should_show_in_dashboard
from dashboard.config_api import MASK, PRESETS, _mask_provider
from dashboard.context import (
    ensure_workspace_path,
    get_request_config,
    get_request_profile,
    get_request_store,
    get_websocket_profile,
    get_workspace_root,
)
from dashboard.session_meta import get_meta, mark_archived, set_meta
from dashboard.status_state import build_status_payload, build_status_snapshot
from dashboard.state import (
    bootstrap_dashboard,
    list_profiles,
    load_dashboard_state,
    load_profile_meta,
    profile_home,
    save_profile_meta,
    verify_token,
)
from engine.query_engine import QueryEngine
from prompt.builder import PromptBuilder
from mcp.config import load_mcp_configs
from constants import get_emperor_home, normalize_profile
from session.time_util import format_local_timestamp, session_to_dict

router = APIRouter(prefix="/api", tags=["shiba-compat"])

MASKED = "***"
STATUS_STREAM_POLL_SECONDS = 1.0
STATUS_STREAM_HEARTBEAT_SECONDS = 25.0


# ── Auth ──────────────────────────────────────────────────────


@router.get("/auth/status")
async def auth_status():
    state = load_dashboard_state()
    return {
        "auth_required": state.initialized,
        "authenticated": False,
        "initialized": state.initialized,
    }


class AuthVerifyRequest(BaseModel):
    token: str = Field(min_length=1)


@router.post("/auth/verify")
async def auth_verify(req: AuthVerifyRequest):
    state = load_dashboard_state()
    if not state.initialized:
        raise HTTPException(400, "Dashboard not initialized")
    if not verify_token(req.token, state=state):
        raise HTTPException(401, "Invalid token")
    return {"ok": True, "last_profile": state.last_profile}


# ── Status ──────────────────────────────────────────────────


@router.get("/status")
async def api_status(request: Request):
    profile = get_request_profile(request)
    config = get_request_config(request)
    return build_status_payload(profile, config)


@router.websocket("/status/stream")
async def status_stream(websocket: WebSocket):
    state = load_dashboard_state()
    token = websocket.query_params.get("token")
    if not state.initialized or not token or not verify_token(token, state=state):
        await websocket.close(code=4401)
        return

    profile = get_websocket_profile(websocket)
    await websocket.accept()

    seq = 1
    heartbeat_elapsed = 0.0
    previous = build_status_snapshot(profile, load_config(profile=profile))

    try:
        await websocket.send_json({"type": "snapshot", "seq": seq, "data": previous})
        seq += 1

        while True:
            await asyncio.sleep(STATUS_STREAM_POLL_SECONDS)
            current = build_status_snapshot(profile, load_config(profile=profile))
            diff = {
                key: value
                for key, value in current.items()
                if previous.get(key) != value
            }
            if diff:
                await websocket.send_json({"type": "update", "seq": seq, "data": diff})
                previous = current
                heartbeat_elapsed = 0.0
                seq += 1
                continue

            heartbeat_elapsed += STATUS_STREAM_POLL_SECONDS
            if heartbeat_elapsed >= STATUS_STREAM_HEARTBEAT_SECONDS:
                await websocket.send_json({"type": "heartbeat", "seq": seq})
                heartbeat_elapsed = 0.0
                seq += 1
    except (WebSocketDisconnect, RuntimeError):
        return


# ── Settings ────────────────────────────────────────────────


def _settings_payload(profile: str, config: EmperorConfig) -> dict[str, Any]:
    meta = load_profile_meta(profile)
    provider = _mask_provider(config.provider)
    home = get_emperor_home(normalize_profile(profile))
    mcp_servers = load_mcp_configs(home=home)
    return {
        "provider": provider.get("provider"),
        "model": provider.get("model"),
        "base_url": provider.get("base_url"),
        "api_key": provider.get("api_key"),
        "api_key_env": provider.get("api_key_env"),
        "profile": meta,
        "toolsets": config.dashboard.chat.default_toolsets,
        "ui_language": config.ui.language,
        "lane_by_profile": config.dashboard.kanban.lane_by_profile,
        "ask_user_questions": config.dashboard.chat.ask_user_questions,
        "a2ui_enabled": config.dashboard.chat.a2ui_enabled,
        "workspace": str(get_workspace_root()),
        "mcp": {
            "enabled": len(mcp_servers) > 0,
            "servers": [
                {
                    "name": s.name,
                    "command": s.command,
                    "args": s.args,
                    "env": s.env,
                }
                for s in mcp_servers
            ],
        },
        "gateway": {
            "channels": [
                *([] if not config.gateway.enabled else ["webhook"]),
                *([] if not config.gateway.wecom_enabled else ["wecom"]),
            ]
            or ["dashboard"],
            "wecom_enabled": config.gateway.wecom_enabled,
            "wecom_corp_id": config.gateway.wecom_corp_id,
            "wecom_agent_id": config.gateway.wecom_agent_id,
            "wecom_secret": config.gateway.wecom_secret,
            "wecom_token": config.gateway.wecom_token,
            "wecom_encoding_aes_key": config.gateway.wecom_encoding_aes_key,
        },
        "voice": {"tts_enabled": False},
    }


@router.get("/settings")
async def get_settings(request: Request):
    profile = get_request_profile(request)
    config = load_config(home=profile_home(profile), profile=profile)
    return _settings_payload(profile, config)


class SettingsPost(BaseModel):
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    api_key_env: str | None = None
    toolsets: list[str] | None = None
    ui_language: str | None = None
    lane_by_profile: bool | None = None
    ask_user_questions: bool | None = None
    a2ui_enabled: bool | None = None
    profile_meta: dict[str, Any] | None = None
    gateway: dict[str, Any] | None = None


@router.post("/settings")
async def post_settings(request: Request, body: SettingsPost):
    profile = get_request_profile(request)
    home = profile_home(profile)
    config = load_config(home=home, profile=profile)
    data = body.model_dump(exclude_none=True)
    profile_meta = data.pop("profile_meta", None)
    current = config.provider.model_dump()
    for key in ("provider", "model", "base_url", "api_key", "api_key_env"):
        if key in data:
            val = data[key]
            if key == "api_key" and val == MASKED:
                continue
            current[key] = val
    config.provider = ProviderConfig.model_validate(current)
    if body.toolsets:
        config.dashboard.chat.default_toolsets = body.toolsets
    if body.ui_language:
        config.ui.language = body.ui_language
    if body.lane_by_profile is not None:
        config.dashboard.kanban.lane_by_profile = body.lane_by_profile
    if body.ask_user_questions is not None:
        config.dashboard.chat.ask_user_questions = body.ask_user_questions
    if body.a2ui_enabled is not None:
        config.dashboard.chat.a2ui_enabled = body.a2ui_enabled
    if body.gateway:
        for source, target in (
            ("wecom_enabled", "wecom_enabled"),
            ("wecom_corp_id", "wecom_corp_id"),
            ("wecom_agent_id", "wecom_agent_id"),
            ("wecom_secret", "wecom_secret"),
            ("wecom_token", "wecom_token"),
            ("wecom_encoding_aes_key", "wecom_encoding_aes_key"),
        ):
            if source in body.gateway:
                setattr(config.gateway, target, body.gateway[source])
    save_config(config, home)
    if profile_meta:
        save_profile_meta(
            profile,
            display_name=profile_meta.get("display_name"),
            description=profile_meta.get("description"),
            avatar_color=profile_meta.get("avatar_color"),
        )
    return {"ok": True, "settings": _settings_payload(profile, config)}


@router.get("/models")
async def get_models():
    presets = PRESETS
    return {
        "models": [
            {"id": p["model"], "label": p["label"], "provider": p["provider"]}
            for p in presets
        ],
        "presets": presets,
    }


# ── Sessions ────────────────────────────────────────────────


@router.get("/sessions")
async def list_sessions(request: Request, limit: int = 50):
    profile = get_request_profile(request)
    store = get_request_store(request)
    await store.initialize()
    sessions = await store.list_sessions(profile=profile, limit=limit)
    result = []
    for s in sessions:
        meta = get_meta(profile, s.id)
        if meta.get("archived"):
            continue
        if not should_show_in_dashboard(s):
            continue
        result.append(
            {
                **session_to_dict(s),
                "updated_local": format_local_timestamp(s.updated_at),
                "nickname": meta.get("nickname"),
                "model": meta.get("model"),
                "agent_id": meta.get("agent_id") or "default",
                "profile_id": profile,
            }
        )
    return {"sessions": result}


@router.get("/sessions/{session_id}")
async def get_session(request: Request, session_id: str):
    profile = get_request_profile(request)
    store = get_request_store(request)
    config = get_request_config(request)
    await store.initialize()
    events = await store.load_events(session_id)
    messages = events_to_openai_messages(events)
    meta = get_meta(profile, session_id)
    system_prompt = PromptBuilder(language=config.agent.language).build()
    compressed = await store.has_compress_events(session_id)
    usage = build_history_usage_snapshot(
        messages,
        system_prompt=system_prompt,
        max_context_tokens=config.agent.max_context_tokens,
        stored_snapshot=meta.get("usage_snapshot"),
        compressed=compressed,
    )
    return {
        "id": session_id,
        "events": events,
        "messages": messages,
        "nickname": meta.get("nickname"),
        "model": meta.get("model"),
        "agent_id": meta.get("agent_id") or "default",
        "profile_id": profile,
        "usage": usage,
        "follow_up_questions": meta.get("last_follow_up_questions") or [],
    }


class SessionPatch(BaseModel):
    nickname: str | None = None
    model: str | None = None
    profile_id: str | None = None
    agent_id: str | None = None


@router.patch("/sessions/{session_id}")
async def patch_session(request: Request, session_id: str, body: SessionPatch):
    profile = get_request_profile(request)
    patch: dict[str, Any] = {}
    if body.nickname is not None:
        patch["nickname"] = body.nickname
    if body.model is not None:
        patch["model"] = body.model
    if body.agent_id is not None:
        patch["agent_id"] = body.agent_id
    meta = set_meta(profile, session_id, patch)
    return {"ok": True, "session_id": session_id, **meta}


@router.delete("/sessions/{session_id}")
async def delete_session(request: Request, session_id: str):
    store = get_request_store(request)
    await store.initialize()
    await store.delete_session(session_id)
    return {"ok": True}


@router.post("/sessions/{session_id}/archive")
async def archive_session(request: Request, session_id: str):
    profile = get_request_profile(request)
    mark_archived(profile, session_id)
    return {"ok": True, "session_id": session_id, "archived": True}


# ── Context ─────────────────────────────────────────────────


@router.get("/context")
async def get_context(request: Request):
    profile = get_request_profile(request)
    config = get_request_config(request)
    builder = PromptBuilder(language=config.ui.language)
    system = builder.build()
    return {
        "system_prompt": system,
        "token_estimate": len(system) // 4,
        "profile": profile,
        "sections": [
            {"name": "stable", "chars": len(builder._stable_section())},
            {"name": "full", "chars": len(system)},
        ],
    }


# ── Filesystem ──────────────────────────────────────────────


@router.get("/fs/explore")
async def fs_explore(path: str | None = None):
    root, current = ensure_workspace_path(path)
    if not current.exists():
        raise HTTPException(404, "Path not found")
    if current.is_file():
        raise HTTPException(400, "Path is a file")
    entries = []
    for entry in sorted(current.iterdir(), key=lambda item: (item.is_file(), item.name.lower())):
        rel = "." if entry == root else str(entry.relative_to(root))
        entries.append(
            {
                "name": entry.name,
                "path": rel,
                "type": "dir" if entry.is_dir() else "file",
                "size": entry.stat().st_size if entry.is_file() else None,
            }
        )
    rel_current = "." if current == root else str(current.relative_to(root))
    return {"root": str(root), "path": rel_current, "entries": entries}


@router.get("/file-get")
async def file_get(path: str):
    root, target = ensure_workspace_path(path)
    if not target.is_file():
        raise HTTPException(404, "File not found")
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(400, "Only UTF-8 text files supported") from exc
    return {
        "path": "." if target == root else str(target.relative_to(root)),
        "content": content,
        "size": target.stat().st_size,
    }


class FileSaveRequest(BaseModel):
    path: str
    content: str


@router.post("/file-save")
async def file_save(req: FileSaveRequest):
    root, target = ensure_workspace_path(req.path)
    if target.exists() and not target.is_file():
        raise HTTPException(400, "Path is not a file")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(req.content, encoding="utf-8")
    return {"ok": True, "path": str(target.relative_to(root))}


@router.post("/upload")
async def upload_files(files: list[UploadFile] = File(...)):
    saved = []
    for upload in files:
        filename = Path(upload.filename or "upload").name
        root, target = ensure_workspace_path(filename)
        if target.is_dir():
            raise HTTPException(400, f"Cannot overwrite directory: {filename}")
        data = await upload.read()
        target.write_bytes(data)
        saved.append({"name": filename, "path": filename, "size": len(data)})
    return {"ok": True, "files": saved}


# ── Profiles (ShibaClaw shape) ──────────────────────────────


@router.get("/profiles")
async def profiles_list():
    return {
        "profiles": [
            {
                "id": p["name"],
                "name": p["name"],
                "display_name": p.get("display_name", p["name"]),
                "description": p.get("description", ""),
                "avatar_color": p.get("avatar_color", ""),
            }
            for p in list_profiles()
        ]
    }


# ── Onboard ─────────────────────────────────────────────────


@router.get("/onboard/providers")
async def onboard_providers():
    return {"providers": PRESETS}


@router.get("/onboard/templates")
async def onboard_templates():
    return {"templates": [{"id": "default", "name": "Default workspace"}]}


class OnboardSubmit(BaseModel):
    token: str = Field(min_length=4)
    profile_name: str = "default"
    provider: str = "openrouter"
    model: str = ""
    base_url: str | None = None
    api_key: str | None = None


@router.post("/onboard/submit")
async def onboard_submit(req: OnboardSubmit):
    state = load_dashboard_state()
    if state.initialized:
        return {"ok": True, "already_initialized": True}
    from dashboard.app_api import BootstrapRequest, ProviderSetup, bootstrap

    return await bootstrap(
        BootstrapRequest(
            token=req.token,
            profile_name=req.profile_name,
            provider=ProviderSetup(
                provider=req.provider,
                model=req.model,
                base_url=req.base_url,
                api_key=req.api_key,
            ),
        )
    )


# ── Update stubs ──────────────────────────────────────────────


@router.get("/update/check")
async def update_check():
    return {"update_available": False, "current": "0.1.0", "latest": "0.1.0"}


@router.get("/update/manifest")
async def update_manifest():
    return {"version": "0.1.0"}


@router.post("/update/apply")
async def update_apply():
    return {"ok": False, "message": "Auto-update not configured for Emperor"}


@router.post("/restart")
async def restart_server():
    return {"ok": True, "message": "Restart dashboard via start.sh"}
