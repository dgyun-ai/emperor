"""Tool call partitioning and concurrent execution."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from context.tool_context import ToolContext
from provider.openai_compat import ToolCall
from tools.base import Tool, ToolResult


ExecuteFn = Callable[[ToolCall, ToolContext], Awaitable[tuple[ToolResult, list[Any]]]]


@dataclass
class ToolBatch:
    calls: list[ToolCall]
    concurrent: bool


def partition_tool_calls(calls: list[ToolCall], tool_map: dict[str, Tool]) -> list[ToolBatch]:
    """Partition tool calls into batches: consecutive read-only → concurrent batch."""
    batches: list[ToolBatch] = []
    current: list[ToolCall] = []
    current_concurrent = True

    for tc in calls:
        tool = tool_map.get(tc.name)
        is_read_only = tool.is_read_only if tool else False
        is_interactive = tool.is_interactive if tool else False
        can_concurrent = is_read_only and not is_interactive

        if current and can_concurrent != current_concurrent:
            batches.append(ToolBatch(calls=current, concurrent=current_concurrent))
            current = []
        current.append(tc)
        current_concurrent = can_concurrent

    if current:
        batches.append(ToolBatch(calls=current, concurrent=current_concurrent))
    return batches


async def execute_partitioned(
    calls: list[ToolCall],
    ctx: ToolContext,
    tool_map: dict[str, Tool],
    execute_fn: ExecuteFn,
) -> list[tuple[ToolCall, ToolResult, list[Any], list[dict[str, Any]]]]:
    """Execute tool calls with read-only concurrency and mutating serialization."""
    batches = partition_tool_calls(calls, tool_map)
    results: list[tuple[ToolCall, ToolResult, list[Any], list[dict[str, Any]]]] = []

    for batch in batches:
        if ctx.is_aborted():
            break
        if batch.concurrent and len(batch.calls) > 1:

            async def run_one(tc: ToolCall) -> tuple[ToolCall, ToolResult, list[Any]]:
                result, events = await execute_fn(tc, ctx)
                return tc, result, events

            batch_results = await asyncio.gather(*[run_one(tc) for tc in batch.calls])
            for tc, result, events in batch_results:
                appended = ctx.apply_result(result)
                results.append((tc, result, events, appended))
        else:
            for tc in batch.calls:
                if ctx.is_aborted():
                    break
                result, events = await execute_fn(tc, ctx)
                appended = ctx.apply_result(result)
                results.append((tc, result, events, appended))
    return results
