"""Shared dashboard status payload builders."""

from __future__ import annotations

import os
from typing import Any

from config.models import EmperorConfig
from dashboard.state import load_dashboard_state


def _wecom_enabled(config: EmperorConfig) -> bool:
    return bool(
        config.gateway.wecom_enabled
        and config.gateway.wecom_token
        and config.gateway.wecom_agent_id
    )


def _wecom_configured(config: EmperorConfig) -> bool:
    return all(
        [
            bool(config.gateway.wecom_corp_id),
            bool(config.gateway.wecom_agent_id),
            bool(config.gateway.wecom_secret),
            bool(config.gateway.wecom_token),
            bool(config.gateway.wecom_encoding_aes_key),
        ]
    )


def _active_channels(config: EmperorConfig) -> list[str]:
    telegram = bool(os.environ.get("TELEGRAM_BOT_TOKEN", "").strip())
    channels = []
    if telegram:
        channels.append("telegram")
    if config.gateway.enabled:
        channels.append("webhook")
    if _wecom_enabled(config):
        channels.append("wecom")
    return channels or ["dashboard"]


def build_status_payload(profile: str, config: EmperorConfig) -> dict[str, Any]:
    state = load_dashboard_state()
    configured = bool(config.provider.model)
    return {
        "version": "0.1.0-emperor",
        "agent_configured": configured,
        "profile": profile,
        "provider": config.provider.provider,
        "model": config.provider.model,
        "initialized": state.initialized,
    }


def build_gateway_health_payload(profile: str, config: EmperorConfig) -> dict[str, Any]:
    return {
        "ok": True,
        "gateway_up": True,
        "profile": profile,
        "channels": _active_channels(config),
        "telegram_configured": bool(os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()),
        "wecom_configured": _wecom_configured(config),
        "wecom_enabled": _wecom_enabled(config),
    }


def build_status_snapshot(profile: str, config: EmperorConfig) -> dict[str, Any]:
    return {
        "status": build_status_payload(profile, config),
        "gateway_health": build_gateway_health_payload(profile, config),
    }
