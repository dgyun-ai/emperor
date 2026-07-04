"""Message validation and AgentLoop implementation."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from agent.budget import IterationBudget
from agent.callbacks import AgentCallbacks
from agent.deps import AgentDeps
from agent.loop_guard import (
    ToolFailureGuard,
    format_immediate_disable_guidance,
)
from agent.types import AgentEvent, Terminal
from context.tool_context import ToolContext
from context.usage import UsageTracker, build_usage_snapshot, estimate_context_tokens
from hooks.lifecycle import HookManager
from provider.openai_compat import ModelResponse, ToolCall
from context.compressor import estimate_tokens
from tools.approval import check_tool_approval
from tools.base import Tool, ToolResult, tools_to_openai_schema
from tools.orchestrator import execute_partitioned
from tools.registry import get_tool


class MessageValidationError(ValueError):
    """Raised when message history violates alternation rules."""


def validate_messages(messages: list[dict[str, Any]]) -> None:
    """Validate user/assistant/tool alternation rules."""
    first_non_system = next((m for m in messages if m.get("role") != "system"), None)
    if first_non_system is None:
        return

    if first_non_system.get("role") != "user":
        raise MessageValidationError("First message must be user (after optional system)")

    expect_user_side = False
    pending_tool_ids: set[str] = set()
    saw_user = False

    for msg in messages:
        role = msg.get("role")
        if role == "system":
            # System guidance may appear between assistant turns within the same user turn.
            if not pending_tool_ids:
                expect_user_side = False
            continue
        if role == "user":
            if not expect_user_side and saw_user:
                raise MessageValidationError("Unexpected user message; expected assistant")
            saw_user = True
            expect_user_side = False
            pending_tool_ids.clear()
        elif role == "assistant":
            if expect_user_side:
                raise MessageValidationError("Unexpected assistant message; expected user/tool")
            expect_user_side = True
            pending_tool_ids.clear()
            for tc in msg.get("tool_calls") or []:
                tc_id = tc.get("id")
                if tc_id:
                    pending_tool_ids.add(tc_id)
        elif role == "tool":
            if not expect_user_side:
                raise MessageValidationError("Tool message must follow assistant tool_calls")
            tool_call_id = msg.get("tool_call_id")
            if not tool_call_id or tool_call_id not in pending_tool_ids:
                raise MessageValidationError(f"Unknown tool_call_id: {tool_call_id}")
            pending_tool_ids.discard(tool_call_id)
            if not pending_tool_ids:
                expect_user_side = False
        else:
            raise MessageValidationError(f"Unsupported role: {role}")


def _should_immediately_disable_tool(tool_name: str, result: ToolResult) -> tuple[bool, str | None]:
    """Return whether the tool should be blocked for the rest of the current run."""
    if not result.is_error:
        return False, None
    if tool_name != "render_a2ui":
        return False, None

    content = result.content if isinstance(result.content, str) else str(result.content)
    normalized = content.lower()
    markers = (
        "messages must be a non-empty array",
        "messages must contain objects",
        "provide either messages[] or copilotkit flat args",
        "surfaceid and a non-empty components array are required in flat format",
    )
    if any(marker in normalized for marker in markers):
        return True, content
    return False, None


class AgentLoop:
    """Async generator agent loop: user → LLM → tool → loop → terminal."""

    def __init__(
        self,
        *,
        deps: AgentDeps,
        tools: list[Tool] | None = None,
        profile: str = "default",
        system_prompt: str = "你是 emperor，一个有用的助手。请使用简体中文回复。",
        max_turns: int = 10,
        max_context_tokens: int = 128_000,
        usage_tracker: UsageTracker | None = None,
        callbacks: AgentCallbacks | None = None,
        hooks: HookManager | None = None,
        require_approval: bool = True,
        max_consecutive_tool_failures: int = 3,
        loop_guard_enabled: bool = True,
        language: str = "zh",
    ) -> None:
        self.deps = deps
        self.tools = tools or []
        self.profile = profile
        self.system_prompt = system_prompt
        self.max_turns = max_turns
        self.max_context_tokens = max_context_tokens
        self.usage_tracker = usage_tracker or UsageTracker()
        self.callbacks = callbacks or AgentCallbacks()
        self.hooks = hooks or HookManager()
        self.require_approval = require_approval
        self.max_consecutive_tool_failures = max_consecutive_tool_failures
        self.loop_guard_enabled = loop_guard_enabled
        self.language = language
        self._tool_map = {t.name: t for t in self.tools}

    async def run(
        self,
        *,
        messages: list[dict[str, Any]],
        abort_event: asyncio.Event | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """Run conversation until terminal; yields AgentEvent stream."""
        from session.convert import normalize_message_history

        messages = normalize_message_history(messages)
        validate_messages(messages)

        budget = IterationBudget(self.max_turns)
        failure_guard = ToolFailureGuard(
            max_failures=self.max_consecutive_tool_failures,
            enabled=self.loop_guard_enabled,
            language=self.language,
        )
        blocked_tools: set[str] = set()
        history = list(messages)
        call_model = self.deps.get_call_model()
        tool_schemas = tools_to_openai_schema(self.tools) if self.tools else None

        def can_use_tool(name: str, _input_data: dict[str, Any]) -> bool:
            return name not in blocked_tools

        runtime_ctx = ToolContext(
            messages=history,
            abort_event=abort_event,
            task_id="default",
            agent_deps=self.deps,
            can_use_tool=can_use_tool,
            extra={"profile": self.profile},
        )

        while True:
            if abort_event and abort_event.is_set():
                yield AgentEvent("status", {"terminal": Terminal(reason="aborted", message=None, error=None)})
                return

            if budget.exhausted:
                yield AgentEvent(
                    "status",
                    {
                        "terminal": Terminal(
                            reason="max_iterations",
                            message=None,
                            error=f"Reached max_turns={self.max_turns}",
                        )
                    },
                )
                return

            budget.consume()
            api_messages = self._with_system(history)

            final_response: ModelResponse | None = None
            async for chunk in call_model(
                messages=api_messages,
                tools=tool_schemas,
                abort_event=abort_event,
            ):
                if abort_event and abort_event.is_set():
                    yield AgentEvent("status", {"terminal": Terminal(reason="aborted", message=None, error=None)})
                    return
                if chunk.reasoning_delta:
                    yield AgentEvent("thinking", {"text": chunk.reasoning_delta})
                if chunk.delta_text:
                    if self.callbacks.on_stream_delta:
                        self.callbacks.on_stream_delta(chunk.delta_text)
                    yield AgentEvent("stream_delta", chunk.delta_text)
                if chunk.is_final:
                    final_response = chunk

            if final_response is None or final_response.assistant_message is None:
                yield AgentEvent(
                    "status",
                    {
                        "terminal": Terminal(
                            reason="error",
                            message=None,
                            error="Model returned no final response",
                        )
                    },
                )
                return

            assistant_msg = final_response.assistant_message
            history.append(assistant_msg)
            yield AgentEvent("message", assistant_msg)
            yield self._build_usage_event(api_messages, assistant_msg, final_response)

            if final_response.tool_calls:
                async def execute_one(tc: ToolCall, tool_ctx: ToolContext) -> tuple[ToolResult, list[Any]]:
                    events: list[Any] = []
                    result = await self._execute_tool(tc, tool_ctx, events, blocked_tools)
                    return result, events

                results = await execute_partitioned(
                    final_response.tool_calls,
                    runtime_ctx,
                    self._tool_map,
                    execute_one,
                )
                for tc, tool_result, tool_events, appended_messages in results:
                    for ev in tool_events:
                        yield ev
                    a2ui_messages = runtime_ctx.drain_a2ui()
                    if a2ui_messages:
                        yield AgentEvent("a2ui", {"messages": a2ui_messages})
                    for message in appended_messages:
                        yield AgentEvent("message", message)
                    tool_msg = {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": tool_result.content,
                    }
                    history.append(tool_msg)
                    yield AgentEvent("message", tool_msg)
                    if tc.name not in blocked_tools:
                        failure_guard.record(tc.name, success=not tool_result.is_error)
                    should_block_now, block_reason = _should_immediately_disable_tool(tc.name, tool_result)
                    if should_block_now and tc.name not in blocked_tools:
                        blocked_tools.add(tc.name)
                        failure_guard.mark_blocked(tc.name)
                        system_msg = {
                            "role": "system",
                            "content": format_immediate_disable_guidance(
                                tc.name,
                                reason=block_reason,
                                language=self.language,
                            ),
                        }
                        history.append(system_msg)
                        yield AgentEvent("message", system_msg)
                validate_messages(history)
                hit_limit, blocked_tool, guidance = failure_guard.exceeded()
                if hit_limit and blocked_tool and guidance:
                    blocked_tools.add(blocked_tool)
                    failure_guard.mark_blocked(blocked_tool)
                    system_msg = {"role": "system", "content": guidance}
                    history.append(system_msg)
                    yield AgentEvent("message", system_msg)
                continue

            text = assistant_msg.get("content") or ""
            await self.hooks.run_stop("complete")
            yield AgentEvent(
                "status",
                {"terminal": Terminal(reason="complete", message=text, error=None)},
            )
            return

    def _with_system(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if messages and messages[0].get("role") == "system":
            return messages
        return [{"role": "system", "content": self.system_prompt}, *messages]

    def _build_usage_event(
        self,
        api_messages: list[dict[str, Any]],
        assistant_msg: dict[str, Any],
        final_response: ModelResponse,
    ) -> AgentEvent:
        prompt_tokens = final_response.prompt_tokens
        completion_tokens = final_response.completion_tokens
        if prompt_tokens == 0 and completion_tokens == 0:
            prompt_tokens = estimate_tokens(api_messages)
            completion_tokens = estimate_tokens([assistant_msg])

        self.usage_tracker.record_turn(prompt_tokens, completion_tokens)
        conversation = [m for m in api_messages if m.get("role") != "system"] + [assistant_msg]
        context_tokens = estimate_context_tokens(conversation, system_prompt=self.system_prompt)
        snapshot = build_usage_snapshot(
            self.usage_tracker,
            context_tokens=context_tokens,
            max_context_tokens=self.max_context_tokens,
        )
        return AgentEvent("usage_update", snapshot)

    async def _execute_tool(
        self,
        tc: ToolCall,
        ctx: ToolContext,
        events: list[AgentEvent],
        blocked_tools: set[str] | None = None,
    ) -> ToolResult:
        if blocked_tools and tc.name in blocked_tools:
            return ToolResult(
                content=(
                    f"Tool '{tc.name}' is temporarily disabled after repeated failures. "
                    "Respond to the user in text without calling it again."
                ),
                is_error=False,
            )

        tool = self._tool_map.get(tc.name) or get_tool(tc.name)
        if tool is None:
            return ToolResult(content=f"Error: unknown tool '{tc.name}'", is_error=True)

        if not await self.hooks.run_pre_tool_use(tc.name, tc.arguments):
            return ToolResult(content=f"Blocked by hook: {tc.name}", is_error=True)

        approved, reason = await check_tool_approval(
            tc.name, tc.arguments, require_approval=self.require_approval
        )
        if not approved:
            return ToolResult(content=reason or "Approval denied", is_error=True)

        if self.callbacks.on_tool_start:
            self.callbacks.on_tool_start(tc.name, tc.arguments)
        events.append(AgentEvent("tool_start", {"name": tc.name, "input": tc.arguments}))

        try:
            result = await tool.call(tc.arguments, ctx)
        except Exception as exc:  # noqa: BLE001
            result = ToolResult(content=f"Error executing {tc.name}: {exc}", is_error=True)

        await self.hooks.run_post_tool_use(tc.name, tc.arguments, result)

        if self.callbacks.on_tool_end:
            self.callbacks.on_tool_end(tc.name, result)
        events.append(AgentEvent("tool_end", {"name": tc.name, "result": result.content}))
        return result
