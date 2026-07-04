"""Path and environment conventions for emperor."""

from __future__ import annotations

import os
from pathlib import Path

PACKAGE_VERSION = "0.1.0"

ENV_EMPEROR_HOME = "EMPEROR_HOME"
ENV_OPENAI_API_KEY = "OPENAI_API_KEY"
ENV_OPENROUTER_API_KEY = "OPENROUTER_API_KEY"
ENV_EMPEROR_PROFILE = "EMPEROR_PROFILE"
ENV_EMPEROR_KANBAN_TASK = "EMPEROR_KANBAN_TASK"
ENV_EMPEROR_KANBAN_WORKSPACE = "EMPEROR_KANBAN_WORKSPACE"
ENV_EMPEROR_PROVIDER_OVERRIDE = "EMPEROR_PROVIDER_OVERRIDE"

DEFAULT_CONFIG_FILENAME = "config.yaml"
DEFAULT_EMPEROR_HOME_NAME = ".emperor"


def _has_write_access(path: Path) -> bool:
    target = path
    while not target.exists() and target != target.parent:
        target = target.parent
    return os.access(target, os.W_OK)


def get_emperor_home(profile: str | None = None) -> Path:
    """Return EMPEROR_HOME, optionally scoped to a profile subdirectory.

    Resolution order:
    1. ``EMPEROR_HOME`` env when set
    2. ``~/.emperor`` (default user data root)
    3. ``./.emperor`` under cwd when home is not writable

    Session SQLite lives at ``{base}/profiles/{profile}/state.db``.
    """
    configured = os.environ.get(ENV_EMPEROR_HOME)
    base = Path(configured) if configured else Path.home() / DEFAULT_EMPEROR_HOME_NAME
    if configured is None and not _has_write_access(base):
        base = Path.cwd() / DEFAULT_EMPEROR_HOME_NAME
    if profile:
        return base / "profiles" / profile
    return base


def get_config_path(home: Path | None = None) -> Path:
    """Return path to config.yaml under EMPEROR_HOME."""
    root = home or get_emperor_home()
    return root / DEFAULT_CONFIG_FILENAME


def normalize_profile(profile: str | None) -> str:
    """Effective profile for scoped storage (sessions, history, skins)."""
    return profile or "default"
