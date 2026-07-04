"""SSE helpers for dashboard and API streaming."""

from __future__ import annotations

from collections.abc import AsyncIterator

from agent.types import AgentEvent
from dashboard.openai_sse import agent_events_to_openai_sse

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


async def agent_events_to_sse(
    events: AsyncIterator[AgentEvent],
    *,
    model: str = "emperor",
) -> AsyncIterator[str]:
    """Convert AgentEvent stream to OpenAI-compatible SSE chunks."""
    async for chunk in agent_events_to_openai_sse(events, model=model):
        yield chunk
