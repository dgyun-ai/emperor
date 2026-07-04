"""Dashboard auth/bootstrap state helpers."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from constants import get_emperor_home, normalize_profile

STATE_FILENAME = "dashboard_state.json"
PROFILE_META_FILENAME = "profile.json"


@dataclass
class DashboardState:
    initialized: bool = False
    token_hash: str | None = None
    created_at: float | None = None
    last_profile: str = "default"

    def to_dict(self) -> dict[str, Any]:
        return {
            "initialized": self.initialized,
            "token_hash": self.token_hash,
            "created_at": self.created_at,
            "last_profile": self.last_profile,
        }


def dashboard_home() -> Path:
    root = get_emperor_home()
    root.mkdir(parents=True, exist_ok=True)
    return root


def dashboard_state_path() -> Path:
    return dashboard_home() / STATE_FILENAME


def load_dashboard_state() -> DashboardState:
    path = dashboard_state_path()
    if not path.is_file():
        return DashboardState()
    raw = json.loads(path.read_text(encoding="utf-8"))
    return DashboardState(
        initialized=bool(raw.get("initialized")),
        token_hash=raw.get("token_hash"),
        created_at=raw.get("created_at"),
        last_profile=normalize_profile(raw.get("last_profile")),
    )


def save_dashboard_state(state: DashboardState) -> Path:
    path = dashboard_state_path()
    path.write_text(
        json.dumps(state.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_token(token: str, *, state: DashboardState | None = None) -> bool:
    current = state or load_dashboard_state()
    if not current.initialized or not current.token_hash:
        return False
    return hmac.compare_digest(hash_token(token), current.token_hash)


def bootstrap_dashboard(token: str, *, profile: str) -> DashboardState:
    state = DashboardState(
        initialized=True,
        token_hash=hash_token(token),
        created_at=time.time(),
        last_profile=normalize_profile(profile),
    )
    save_dashboard_state(state)
    return state


def profiles_root() -> Path:
    root = dashboard_home() / "profiles"
    root.mkdir(parents=True, exist_ok=True)
    return root


def profile_home(profile: str | None) -> Path:
    name = normalize_profile(profile)
    home = profiles_root() / name
    home.mkdir(parents=True, exist_ok=True)
    return home


def profile_meta_path(profile: str | None) -> Path:
    return profile_home(profile) / PROFILE_META_FILENAME


def load_profile_meta(profile: str | None) -> dict[str, Any]:
    name = normalize_profile(profile)
    path = profile_meta_path(name)
    if path.is_file():
        raw = json.loads(path.read_text(encoding="utf-8"))
    else:
        raw = {}
    return {
        "name": name,
        "display_name": raw.get("display_name") or name,
        "description": raw.get("description") or "",
        "avatar_color": raw.get("avatar_color") or "",
    }


def save_profile_meta(
    profile: str | None,
    *,
    display_name: str | None = None,
    description: str | None = None,
    avatar_color: str | None = None,
) -> dict[str, Any]:
    current = load_profile_meta(profile)
    if display_name is not None:
        current["display_name"] = display_name.strip() or current["name"]
    if description is not None:
        current["description"] = description
    if avatar_color is not None:
        current["avatar_color"] = avatar_color
    path = profile_meta_path(current["name"])
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return current


def list_profiles() -> list[dict[str, Any]]:
    root = profiles_root()
    profiles: list[dict[str, Any]] = []
    for entry in sorted(root.iterdir(), key=lambda p: p.name):
        if entry.is_dir():
            profiles.append(load_profile_meta(entry.name))
    if not profiles:
        profiles.append(load_profile_meta("default"))
    return profiles

