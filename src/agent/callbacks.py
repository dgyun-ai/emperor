"""Agent callbacks for tool progress and stream deltas."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class AgentCallbacks:
    """Optional hooks invoked during agent execution."""

    on_stream_delta: Callable[[str], None] | None = None
    on_tool_start: Callable[[str, dict[str, Any]], None] | None = None
    on_tool_end: Callable[[str, Any], None] | None = None
