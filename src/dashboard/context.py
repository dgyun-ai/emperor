"""Dashboard request-scoped helpers."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import HTTPException, Request, WebSocket

from config.loader import load_config
from constants import ENV_EMPEROR_KANBAN_WORKSPACE, normalize_profile
from dashboard.state import load_dashboard_state
from kanban.db import KanbanDB
from session.store import SessionStore

PROFILE_HEADER = "X-Emperor-Profile"


def get_workspace_root() -> Path:
    raw = os.environ.get(ENV_EMPEROR_KANBAN_WORKSPACE)
    root = Path(raw).expanduser() if raw else Path.cwd()
    return root.resolve()


def resolve_profile_name(profile: str | None) -> str:
    if profile:
        return normalize_profile(profile)
    state = load_dashboard_state()
    return normalize_profile(state.last_profile or "default")


def get_request_profile(request: Request) -> str:
    return resolve_profile_name(request.headers.get(PROFILE_HEADER))


def get_websocket_profile(websocket: WebSocket) -> str:
    return resolve_profile_name(websocket.query_params.get("profile"))


def get_request_config(request: Request):
    return load_config(profile=get_request_profile(request))


def get_request_db(request: Request) -> KanbanDB:
    return KanbanDB.for_profile(get_request_profile(request))


def get_request_store(request: Request) -> SessionStore:
    return SessionStore.for_profile(get_request_profile(request))


def get_ws_db(websocket: WebSocket) -> KanbanDB:
    return KanbanDB.for_profile(get_websocket_profile(websocket))


def ensure_workspace_path(raw_path: str | None) -> tuple[Path, Path]:
    root = get_workspace_root()
    relative = raw_path or "."
    candidate = (root / relative).resolve()
    if candidate != root and root not in candidate.parents:
        raise HTTPException(400, "Path escapes workspace root")
    return root, candidate
