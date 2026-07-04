"""Provider fallback chain on 429/5xx."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from config.models import EmperorConfig, FallbackProviderConfig
from provider.openai_compat import ModelResponse, OpenAICompatProvider

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class FallbackProvider:
    """Wrap primary provider with fallback chain."""

    def __init__(
        self,
        primary: OpenAICompatProvider,
        fallbacks: list[OpenAICompatProvider],
    ) -> None:
        self.primary = primary
        self.fallbacks = fallbacks
        self._providers = [primary, *fallbacks]

    @classmethod
    def from_config(cls, config: EmperorConfig, primary: OpenAICompatProvider) -> FallbackProvider:
        fallbacks: list[OpenAICompatProvider] = []
        for fb in config.fallback_providers:
            key = fb.api_key or config.provider.api_key or ""
            if not key:
                continue
            fallbacks.append(
                OpenAICompatProvider(api_key=key, model=fb.model, base_url=fb.base_url)
            )
        return cls(primary, fallbacks)

    async def stream_chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        abort_event: Any | None = None,
        extra_body: dict[str, Any] | None = None,
        disable_thinking: bool = False,
        max_tokens: int | None = None,
    ) -> AsyncIterator[ModelResponse]:
        last_error: Exception | None = None
        for i, provider in enumerate(self._providers):
            try:
                async for chunk in provider.stream_chat(
                    messages=messages,
                    tools=tools,
                    abort_event=abort_event,
                    extra_body=extra_body,
                    disable_thinking=disable_thinking,
                    max_tokens=max_tokens,
                ):
                    yield chunk
                return
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                status = getattr(exc, "status_code", None)
                if status not in RETRYABLE_STATUS and i == 0:
                    raise
                logger.warning("Provider %s failed (%s), trying fallback", i, exc)
        if last_error:
            raise last_error
