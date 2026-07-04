"""Injectable dependencies for AgentLoop (test doubles)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

from provider.openai_compat import ModelResponse, OpenAICompatProvider


CallModelFn = Callable[..., AsyncIterator[ModelResponse]]


@dataclass
class AgentDeps:
    """Dependency injection container for agent loop."""

    call_model: CallModelFn | None = None
    provider: OpenAICompatProvider | None = None

    def get_call_model(self) -> CallModelFn:
        if self.call_model is not None:
            return self.call_model
        if self.provider is None:
            raise ValueError("AgentDeps requires call_model or provider")
        return self.provider.stream_chat

    @classmethod
    def from_provider(cls, provider: OpenAICompatProvider) -> AgentDeps:
        return cls(provider=provider)

    @classmethod
    def with_call_model(cls, fn: CallModelFn) -> AgentDeps:
        return cls(call_model=fn)
