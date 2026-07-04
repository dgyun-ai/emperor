"""Dashboard provider configuration API."""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from config.loader import load_config, save_config
from config.models import EmperorConfig, FallbackProviderConfig, ProviderConfig
from dashboard.context import get_request_config, get_request_profile
from dashboard.state import load_profile_meta, save_profile_meta

router = APIRouter(prefix="/api/config", tags=["config"])

MASK = "***"

PRESETS = [
    {
        "id": "openrouter-claude",
        "label": "OpenRouter — Claude Sonnet",
        "provider": "openrouter",
        "model": "anthropic/claude-sonnet-4",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
    },
    {
        "id": "openai-gpt4o",
        "label": "OpenAI — GPT-4o",
        "provider": "openai",
        "model": "gpt-4o",
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
    },
    {
        "id": "ollama-local",
        "label": "Ollama (local)",
        "provider": "local",
        "model": "qwen2.5:7b",
        "base_url": "http://127.0.0.1:11434/v1",
        "api_key": "ollama",
    },
]


def configure_config_api(profile: str | None = None) -> None:
    return None


def _home(profile: str) -> Path:
    from constants import get_emperor_home

    return get_emperor_home(profile)


def _mask_provider(p: ProviderConfig) -> dict[str, Any]:
    data = p.model_dump()
    if data.get("api_key"):
        data["api_key"] = MASK
    return data


def _mask_fallback(f: FallbackProviderConfig) -> dict[str, Any]:
    data = f.model_dump()
    if data.get("api_key"):
        data["api_key"] = MASK
    return data


@router.get("/provider")
async def get_provider(request: Request):
    profile = get_request_profile(request)
    config = load_config(home=_home(profile), profile=profile)
    meta = load_profile_meta(profile)
    return {
        "profile": meta,
        "provider": _mask_provider(config.provider),
        "fallback_providers": [_mask_fallback(f) for f in config.fallback_providers],
        "dashboard": {
            "toolsets": config.dashboard.chat.default_toolsets,
            "ui_language": config.ui.language,
            "lane_by_profile": config.dashboard.kanban.lane_by_profile,
        },
    }


class ProviderUpdate(BaseModel):
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    api_key_env: str | None = None


class ProviderPayload(BaseModel):
    provider: ProviderUpdate
    fallback_providers: list[FallbackProviderConfig] = Field(default_factory=list)
    profile_meta: dict[str, Any] | None = None
    dashboard: dict[str, Any] | None = None


@router.put("/provider")
async def put_provider(request: Request, payload: ProviderPayload):
    profile = get_request_profile(request)
    home = _home(profile)
    config = load_config(home=home, profile=profile)
    incoming = payload.provider.model_dump(exclude_none=True)
    current = config.provider.model_dump()
    for key, val in incoming.items():
        if key == "api_key" and val == MASK:
            continue
        current[key] = val
    config.provider = ProviderConfig.model_validate(current)
    fallbacks: list[FallbackProviderConfig] = []
    for fb in payload.fallback_providers:
        fb_data = fb.model_dump()
        if fb_data.get("api_key") == MASK:
            existing = next(
                (f for f in config.fallback_providers if f.provider == fb.provider and f.model == fb.model),
                None,
            )
            if existing and existing.api_key:
                fb_data["api_key"] = existing.api_key
            else:
                fb_data.pop("api_key", None)
        fallbacks.append(FallbackProviderConfig.model_validate(fb_data))
    config.fallback_providers = fallbacks
    if payload.dashboard:
        toolsets = payload.dashboard.get("toolsets")
        if isinstance(toolsets, list) and toolsets:
            config.dashboard.chat.default_toolsets = [str(t).strip() for t in toolsets if str(t).strip()]
        ui_language = payload.dashboard.get("ui_language")
        if isinstance(ui_language, str) and ui_language.strip():
            config.ui.language = ui_language.strip()
        lane_by_profile = payload.dashboard.get("lane_by_profile")
        if isinstance(lane_by_profile, bool):
            config.dashboard.kanban.lane_by_profile = lane_by_profile
    save_config(config, home)
    if payload.profile_meta:
        save_profile_meta(
            profile,
            display_name=payload.profile_meta.get("display_name"),
            description=payload.profile_meta.get("description"),
            avatar_color=payload.profile_meta.get("avatar_color"),
        )
    return {"ok": True}


@router.get("/models/presets")
async def model_presets():
    return {"presets": PRESETS}


class TestProviderRequest(BaseModel):
    message: str = "Reply with OK only."


@router.post("/provider/test")
async def test_provider(request: Request, req: TestProviderRequest):
    from agent.deps import AgentDeps
    from engine.query_engine import QueryEngine
    from provider.runtime import build_provider

    profile = get_request_profile(request)
    config = get_request_config(request)
    test_config = copy.deepcopy(config)
    test_config.agent.auto_title = False
    provider = build_provider(test_config)
    engine = QueryEngine(
        deps=AgentDeps.from_provider(provider),  # type: ignore[arg-type]
        config=test_config,
        profile=profile,
        tools=[],
        max_turns=1,
    )
    try:
        text = await engine.chat(req.message)
        return {"ok": True, "response": text[:500]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
