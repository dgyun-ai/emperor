"""Sub-agent delegation."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from agent.budget import IterationBudget
from agent.deps import AgentDeps
from agent.loop import AgentLoop
from context.tool_context import ToolContext
from tools.base import Tool, ToolResult
from tools.registry import register_tool


@register_tool(
    name="delegate_task",
    description="Delegate a sub-task to an isolated sub-agent with its own budget.",
    toolset="delegation",
    input_schema={
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "Task description for sub-agent"},
            "max_turns": {"type": "integer", "default": 10},
        },
        "required": ["task"],
    },
)
async def delegate_task(input: dict, ctx: ToolContext) -> ToolResult:
    from tools.registry import get_tools_for_toolsets

    task = input["task"]
    max_turns = int(input.get("max_turns", 10))
    deps = getattr(ctx, "agent_deps", None)
    if deps is None:
        return ToolResult(content="Error: delegation requires agent_deps in context", is_error=True)

    sub_ctx = ToolContext(
        messages=[],
        abort_event=ctx.abort_event,
        task_id=str(uuid.uuid4()),
        chain_id=ctx.chain_id or ctx.task_id,
        depth=ctx.depth + 1,
    )
    tools = get_tools_for_toolsets(enabled=["core", "file", "web"], disabled=["delegation"])
    loop = AgentLoop(deps=deps, tools=tools, max_turns=max_turns)
    messages = [{"role": "user", "content": task}]
    final_text = ""
    async for event in loop.run(messages=messages, abort_event=ctx.abort_event):
        if event.kind == "status" and "terminal" in event.payload:
            terminal = event.payload["terminal"]
            if terminal["reason"] == "complete":
                final_text = terminal.get("message") or ""
            elif terminal["reason"] == "error":
                return ToolResult(content=terminal.get("error") or "Sub-agent error", is_error=True)
    return ToolResult(content=final_text or "(no response from sub-agent)")


def create_subagent_context(parent: ToolContext) -> ToolContext:
    return ToolContext(
        messages=list(parent.messages),
        abort_event=parent.abort_event,
        task_id=str(uuid.uuid4()),
        chain_id=parent.chain_id or parent.task_id,
        depth=parent.depth + 1,
        can_use_tool=parent.can_use_tool,
    )
