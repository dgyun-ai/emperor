"""Dashboard bootstrap/auth/profile/file/monitor API."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from config.loader import load_config, save_config
from config.models import EmperorConfig, ProviderConfig
from constants import normalize_profile
from dashboard.context import (
    PROFILE_HEADER,
    ensure_workspace_path,
    get_request_config,
    get_request_db,
    get_request_profile,
    get_request_store,
    get_workspace_root,
)
from dashboard.state import (
    bootstrap_dashboard,
    list_profiles,
    load_dashboard_state,
    load_profile_meta,
    profile_home,
    save_dashboard_state,
    save_profile_meta,
    verify_token,
)
from tools.cron_tool import get_scheduler

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _soul_path(profile: str) -> Path:
    return profile_home(profile) / "SOUL.md"


def _default_soul(name: str, display_name: str, description: str) -> str:
    summary = description.strip() or f"{display_name} 的默认工作人格。"
    return (
        f"# {display_name}\n\n"
        f"你当前运行在 Emperor 的 profile `{name}` 下。\n\n"
        "## Persona\n"
        f"{summary}\n\n"
        "## Working Style\n"
        "- 默认使用中文回复。\n"
        "- 优先最小增量修改与可验证结果。\n"
        "- 先确认边界，再执行实现。\n"
    )


class BootstrapStatus(BaseModel):
    initialized: bool
    requires_login: bool
    last_profile: str
    profiles: list[dict[str, Any]]


@router.get("/bootstrap/status", response_model=BootstrapStatus)
async def bootstrap_status():
    state = load_dashboard_state()
    return BootstrapStatus(
        initialized=state.initialized,
        requires_login=state.initialized,
        last_profile=normalize_profile(state.last_profile),
        profiles=list_profiles(),
    )


class ProviderSetup(BaseModel):
    provider: str = "openrouter"
    model: str = ""
    base_url: str | None = None
    api_key: str | None = None
    api_key_env: str | None = None


class BootstrapRequest(BaseModel):
    token: str = Field(min_length=4)
    profile_name: str = Field(default="default", min_length=1)
    profile_display_name: str | None = None
    profile_description: str | None = None
    avatar_color: str | None = None
    provider: ProviderSetup = Field(default_factory=ProviderSetup)


@router.post("/bootstrap")
async def bootstrap(req: BootstrapRequest):
    state = load_dashboard_state()
    if state.initialized:
        raise HTTPException(409, "Dashboard already initialized")

    profile = normalize_profile(req.profile_name)
    home = profile_home(profile)
    config = EmperorConfig()
    config.provider = ProviderConfig.model_validate(req.provider.model_dump(exclude_none=True))
    save_config(config, home)

    meta = save_profile_meta(
        profile,
        display_name=req.profile_display_name or profile,
        description=req.profile_description or "",
        avatar_color=req.avatar_color or "",
    )
    soul = _soul_path(profile)
    if not soul.exists():
        soul.write_text(
            _default_soul(profile, meta["display_name"], meta["description"]),
            encoding="utf-8",
        )

    new_state = bootstrap_dashboard(req.token, profile=profile)
    return {
        "ok": True,
        "initialized": new_state.initialized,
        "last_profile": new_state.last_profile,
        "profile": {**meta, "soul": soul.read_text(encoding="utf-8")},
    }


class LoginRequest(BaseModel):
    token: str = Field(min_length=1)


@router.post("/auth/login")
async def login(req: LoginRequest):
    state = load_dashboard_state()
    if not state.initialized:
        raise HTTPException(400, "Dashboard not initialized")
    if not verify_token(req.token, state=state):
        raise HTTPException(401, "Invalid token")
    return {"ok": True, "last_profile": state.last_profile}


@router.get("/app-state")
async def app_state(request: Request):
    profile = get_request_profile(request)
    config = get_request_config(request)
    state = load_dashboard_state()
    return {
        "initialized": state.initialized,
        "current_profile": profile,
        "last_profile": state.last_profile,
        "provider": config.provider.model_dump(exclude={"api_key"}),
        "workspace_root": str(get_workspace_root()),
        "nav": ["chat", "files", "kanban", "profiles", "settings", "monitor"],
    }


class ProfileCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    display_name: str | None = None
    description: str | None = None
    avatar_color: str | None = None
    soul: str | None = None


class ProfileUpdateRequest(BaseModel):
    display_name: str | None = None
    description: str | None = None
    avatar_color: str | None = None
    soul: str | None = None


def _profile_payload(name: str) -> dict[str, Any]:
    meta = load_profile_meta(name)
    soul_path = _soul_path(name)
    return {
        **meta,
        "soul": soul_path.read_text(encoding="utf-8") if soul_path.is_file() else "",
        "initial": meta["display_name"][:1].upper() or name[:1].upper(),
    }


@router.get("/profiles")
async def get_profiles():
    return {"profiles": [_profile_payload(p["name"]) for p in list_profiles()]}


@router.post("/profiles")
async def create_profile(req: ProfileCreateRequest):
    name = normalize_profile(req.name)
    home = profile_home(name)
    if any(p["name"] == name for p in list_profiles()):
        raise HTTPException(409, "Profile already exists")
    save_config(load_config(), home)
    meta = save_profile_meta(
        name,
        display_name=req.display_name or name,
        description=req.description or "",
        avatar_color=req.avatar_color or "",
    )
    soul_text = req.soul or _default_soul(name, meta["display_name"], meta["description"])
    _soul_path(name).write_text(soul_text, encoding="utf-8")
    state = load_dashboard_state()
    state.last_profile = name
    save_dashboard_state(state)
    return {"profile": _profile_payload(name)}


@router.get("/profiles/{name}")
async def get_profile(name: str):
    normalized = normalize_profile(name)
    return {"profile": _profile_payload(normalized)}


@router.put("/profiles/{name}")
async def update_profile(name: str, req: ProfileUpdateRequest):
    normalized = normalize_profile(name)
    meta = save_profile_meta(
        normalized,
        display_name=req.display_name,
        description=req.description,
        avatar_color=req.avatar_color,
    )
    if req.soul is not None:
        _soul_path(normalized).write_text(req.soul, encoding="utf-8")
    return {"profile": _profile_payload(meta["name"])}


@router.get("/files/tree")
async def files_tree(path: str | None = None):
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


@router.get("/files/content")
async def file_content(path: str):
    root, target = ensure_workspace_path(path)
    if not target.is_file():
        raise HTTPException(404, "File not found")
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(400, "Only UTF-8 text files are supported") from exc
    return {
        "root": str(root),
        "path": "." if target == root else str(target.relative_to(root)),
        "content": content,
        "updated_at": target.stat().st_mtime,
    }


class FileWriteRequest(BaseModel):
    path: str
    content: str


@router.put("/files/content")
async def save_file(req: FileWriteRequest):
    root, target = ensure_workspace_path(req.path)
    if target.exists() and not target.is_file():
        raise HTTPException(400, "Path is not a file")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(req.content, encoding="utf-8")
    return {
        "ok": True,
        "root": str(root),
        "path": "." if target == root else str(target.relative_to(root)),
        "size": target.stat().st_size,
        "updated_at": target.stat().st_mtime,
    }


@router.get("/monitor")
async def monitor(request: Request):
    profile = get_request_profile(request)
    config = get_request_config(request)
    db = get_request_db(request)
    store = get_request_store(request)
    scheduler = get_scheduler(profile)
    await db.initialize()
    await store.initialize()
    sessions = await store.list_sessions(profile=profile, limit=500)
    stats = await db.stats()
    return {
        "health": {"status": "ok", "service": "dashboard"},
        "profile": profile,
        "provider": {
            "provider": config.provider.provider,
            "model": config.provider.model,
            "base_url": config.provider.base_url,
        },
        "kanban_stats": stats,
        "dispatcher_enabled": config.kanban.dispatch_in_gateway,
        "session_count": len(sessions),
        "automation": {
            "job_count": len(scheduler.list_jobs()),
            "running_count": scheduler.running_count(),
            "failed_count": scheduler.failed_count(),
        },
        "workspace_root": str(get_workspace_root()),
        "timestamp": time.time(),
        "profile_header": PROFILE_HEADER,
    }
