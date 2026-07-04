"""Load and persist config.yaml from EMPEROR_HOME."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from config.models import EmperorConfig
from constants import (
    ENV_OPENAI_API_KEY,
    ENV_OPENROUTER_API_KEY,
    get_config_path,
    get_emperor_home,
)


def ensure_home(home: Path | None = None) -> Path:
    """Create EMPEROR_HOME if missing and return its path."""
    root = home or get_emperor_home()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _resolve_api_key(config: EmperorConfig) -> str | None:
    """Resolve API key from config or environment."""
    if config.provider.api_key:
        return config.provider.api_key

    env_name = config.provider.api_key_env
    if env_name:
        return os.environ.get(env_name)

    provider = config.provider.provider.lower()
    if provider == "openrouter":
        return os.environ.get(ENV_OPENROUTER_API_KEY) or os.environ.get(ENV_OPENAI_API_KEY)
    return os.environ.get(ENV_OPENAI_API_KEY)


def _default_base_url(provider: str) -> str | None:
    if provider.lower() == "openrouter":
        return "https://openrouter.ai/api/v1"
    return None


def load_config(
    home: Path | None = None,
    profile: str | None = None,
) -> EmperorConfig:
    """Load config.yaml from EMPEROR_HOME (optionally profile-scoped)."""
    root = get_emperor_home(profile) if profile else (home or get_emperor_home())
    ensure_home(root)
    path = get_config_path(root)

    if path.exists():
        with path.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        config = EmperorConfig.model_validate(raw)
    else:
        config = EmperorConfig()
        save_config(config, root)

    if not config.provider.base_url:
        config.provider.base_url = _default_base_url(config.provider.provider)

    resolved_key = _resolve_api_key(config)
    if resolved_key and not config.provider.api_key:
        config.provider.api_key = resolved_key

    return config


def save_config(config: EmperorConfig, home: Path | None = None) -> Path:
    """Write config.yaml to EMPEROR_HOME."""
    root = home or get_emperor_home()
    ensure_home(root)
    path = get_config_path(root)
    data = config.model_dump(exclude_none=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True)
    return path
