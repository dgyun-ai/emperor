"""Provider runtime helpers."""

from __future__ import annotations

import json
import os

from config.models import EmperorConfig
from constants import ENV_EMPEROR_PROVIDER_OVERRIDE
from provider.fallback import FallbackProvider
from provider.openai_compat import OpenAICompatProvider


def build_provider(config: EmperorConfig) -> OpenAICompatProvider | FallbackProvider:
    """Construct provider from loaded config, with optional fallback chain."""
    cfg = config
    override_raw = os.environ.get(ENV_EMPEROR_PROVIDER_OVERRIDE)
    if override_raw:
        try:
            override = json.loads(override_raw)
            cfg = config.model_copy(deep=True)
            if override.get("model"):
                cfg.provider.model = override["model"]
            if override.get("base_url"):
                cfg.provider.base_url = override["base_url"]
            if override.get("provider"):
                cfg.provider.provider = override["provider"]
        except json.JSONDecodeError:
            pass

    api_key = cfg.provider.api_key
    if not api_key:
        raise ValueError(
            "No API key configured. Set OPENROUTER_API_KEY, OPENAI_API_KEY, "
            "or provider.api_key in config.yaml"
        )
    primary = OpenAICompatProvider(
        api_key=api_key,
        model=cfg.provider.model,
        base_url=cfg.provider.base_url,
    )
    if cfg.fallback_providers:
        return FallbackProvider.from_config(cfg, primary)
    return primary
