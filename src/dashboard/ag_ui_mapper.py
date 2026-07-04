"""Map Emperor AgentEvent stream to AG-UI protocol events."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from ag_ui.core.events import (
    ActivitySnapshotEvent,
    CustomEvent,
    EventType,
    MessagesSnapshotEvent,
    RunErrorEvent,
    RunFinishedEvent,
    RunFinishedSuccessOutcome,
    ReasoningEndEvent,
    ReasoningMessageContentEvent,
    ReasoningMessageEndEvent,
    ReasoningMessageStartEvent,
    ReasoningStartEvent,
    RunStartedEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from ag_ui.encoder import EventEncoder

from agent.types import AgentEvent
from emperor_a2ui.normalize import normalize_a2ui_messages

A2UI_CUSTOM_EVENT_NAME = "a2ui"
A2UI_ACTIVITY_TYPE = "a2ui-surface"
A2UI_OPERATIONS_KEY = "a2ui_operations"


class AgUiStreamState:
    """Track AG-UI message/tool IDs while mapping a single run."""

    def __init__(self, *, thread_id: str, run_id: str) -> None:
        self.thread_id = thread_id
        self.run_id = run_id
        self.encoder = EventEncoder()
        self.assistant_message_id = f"msg_{uuid.uuid4().hex[:12]}"
        self.role_sent = False
        self.content_streamed = False
        self.reasoning_open = False
        self.reasoning_phase_id: str | None = None
        self.reasoning_message_id: str | None = None
        self.reasoning_seen = False
        self.open_tool_calls: dict[str, str] = {}
        self.a2ui_message_id = f"a2ui_{uuid.uuid4().hex[:12]}"
        self.a2ui_operations: list[dict[str, Any]] = []

    def encode(self, event: Any) -> str:
        return self.encoder.encode(event)


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts)


def _reasoning_start_events(state: AgUiStreamState) -> list[Any]:
    if state.reasoning_open:
        return []
    state.reasoning_open = True
    state.reasoning_seen = True
    state.reasoning_phase_id = f"reason_{uuid.uuid4().hex[:12]}"
    state.reasoning_message_id = f"reason_msg_{uuid.uuid4().hex[:12]}"
    return [
        ReasoningStartEvent(
            type=EventType.REASONING_START,
            message_id=state.reasoning_phase_id,
        ),
        ReasoningMessageStartEvent(
            type=EventType.REASONING_MESSAGE_START,
            message_id=state.reasoning_message_id,
            role="reasoning",
        ),
    ]


def _reasoning_end_events(state: AgUiStreamState) -> list[Any]:
    events: list[Any] = []
    if state.reasoning_open and state.reasoning_message_id and state.reasoning_phase_id:
        events.append(
            ReasoningMessageEndEvent(
                type=EventType.REASONING_MESSAGE_END,
                message_id=state.reasoning_message_id,
            )
        )
        events.append(
            ReasoningEndEvent(
                type=EventType.REASONING_END,
                message_id=state.reasoning_phase_id,
            )
        )
        state.reasoning_open = False
        state.reasoning_phase_id = None
        state.reasoning_message_id = None
    return events


def _ensure_text_message_started(state: AgUiStreamState) -> list[Any]:
    if state.role_sent:
        return []
    state.role_sent = True
    return [
        TextMessageStartEvent(
            type=EventType.TEXT_MESSAGE_START,
            message_id=state.assistant_message_id,
            role="assistant",
        )
    ]


def _terminal_finish_reason(reason: Any) -> str | None:
    if reason in ("complete", "stop"):
        return "success"
    if reason in ("aborted", "error", "max_iterations", "loop_detected"):
        return str(reason)
    return None


async def agent_events_to_ag_ui_sse(
    events: AsyncIterator[AgentEvent],
    *,
    thread_id: str,
    run_id: str,
) -> AsyncIterator[str]:
    """Convert AgentEvent async stream into AG-UI SSE chunks."""
    state = AgUiStreamState(thread_id=thread_id, run_id=run_id)
    sent_finished = False

    yield state.encode(
        RunStartedEvent(
            type=EventType.RUN_STARTED,
            thread_id=thread_id,
            run_id=run_id,
        )
    )

    async for ev in events:
        if ev.kind == "stream_delta":
            payload = ev.payload if isinstance(ev.payload, dict) else {"text": str(ev.payload)}
            text = payload.get("text", "")
            if not isinstance(text, str) or not text:
                continue
            for end_event in _reasoning_end_events(state):
                yield state.encode(end_event)
            for start_event in _ensure_text_message_started(state):
                yield state.encode(start_event)
            state.content_streamed = True
            yield state.encode(
                TextMessageContentEvent(
                    type=EventType.TEXT_MESSAGE_CONTENT,
                    message_id=state.assistant_message_id,
                    delta=text,
                )
            )

        elif ev.kind == "thinking":
            payload = ev.payload if isinstance(ev.payload, dict) else {"text": str(ev.payload)}
            text = payload.get("text", "")
            if not isinstance(text, str) or not text:
                continue
            for start_event in _reasoning_start_events(state):
                yield state.encode(start_event)
            yield state.encode(
                ReasoningMessageContentEvent(
                    type=EventType.REASONING_MESSAGE_CONTENT,
                    message_id=state.reasoning_message_id or f"reason_msg_{uuid.uuid4().hex[:12]}",
                    delta=text,
                )
            )

        elif ev.kind == "message":
            msg = ev.payload if isinstance(ev.payload, dict) else {}
            if msg.get("role") != "assistant" or msg.get("tool_calls"):
                continue
            thinking = msg.get("_thinking")
            if (
                isinstance(thinking, str)
                and thinking.strip()
                and not state.reasoning_seen
            ):
                for start_event in _reasoning_start_events(state):
                    yield state.encode(start_event)
                yield state.encode(
                    ReasoningMessageContentEvent(
                        type=EventType.REASONING_MESSAGE_CONTENT,
                        message_id=state.reasoning_message_id or f"reason_msg_{uuid.uuid4().hex[:12]}",
                        delta=thinking,
                    )
                )
            text = _message_text(msg.get("content"))
            if text.strip() and not state.content_streamed:
                for end_event in _reasoning_end_events(state):
                    yield state.encode(end_event)
                for start_event in _ensure_text_message_started(state):
                    yield state.encode(start_event)
                state.content_streamed = True
                yield state.encode(
                    TextMessageContentEvent(
                        type=EventType.TEXT_MESSAGE_CONTENT,
                        message_id=state.assistant_message_id,
                        delta=text,
                    )
                )

        elif ev.kind == "tool_start":
            for end_event in _reasoning_end_events(state):
                yield state.encode(end_event)
            payload = ev.payload if isinstance(ev.payload, dict) else {}
            name = str(payload.get("name") or "")
            tool_input = payload.get("input")
            args = json.dumps(tool_input, ensure_ascii=False) if tool_input is not None else "{}"
            tool_call_id = f"call_{uuid.uuid4().hex[:12]}"
            state.open_tool_calls[name] = tool_call_id
            yield state.encode(
                ToolCallStartEvent(
                    type=EventType.TOOL_CALL_START,
                    tool_call_id=tool_call_id,
                    tool_call_name=name,
                    parent_message_id=state.assistant_message_id,
                )
            )
            yield state.encode(
                ToolCallArgsEvent(
                    type=EventType.TOOL_CALL_ARGS,
                    tool_call_id=tool_call_id,
                    delta=args,
                )
            )
            yield state.encode(
                ToolCallEndEvent(
                    type=EventType.TOOL_CALL_END,
                    tool_call_id=tool_call_id,
                )
            )

        elif ev.kind == "tool_end":
            payload = ev.payload if isinstance(ev.payload, dict) else {}
            name = str(payload.get("name") or "")
            tool_call_id = state.open_tool_calls.pop(name, "")
            if not tool_call_id:
                continue
            result = payload.get("result")
            content = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
            yield state.encode(
                ToolCallResultEvent(
                    type=EventType.TOOL_CALL_RESULT,
                    message_id=state.assistant_message_id,
                    tool_call_id=tool_call_id,
                    content=content,
                    role="tool",
                )
            )

        elif ev.kind == "a2ui":
            payload = ev.payload if isinstance(ev.payload, dict) else {}
            messages = payload.get("messages")
            if not isinstance(messages, list):
                messages = []
            batch = normalize_a2ui_messages([m for m in messages if isinstance(m, dict)])
            if not batch:
                continue
            state.a2ui_operations.extend(batch)
            yield state.encode(
                ActivitySnapshotEvent(
                    type=EventType.ACTIVITY_SNAPSHOT,
                    message_id=state.a2ui_message_id,
                    activity_type=A2UI_ACTIVITY_TYPE,
                    content={A2UI_OPERATIONS_KEY: list(state.a2ui_operations)},
                    replace=True,
                )
            )
            yield state.encode(
                CustomEvent(
                    type=EventType.CUSTOM,
                    name=A2UI_CUSTOM_EVENT_NAME,
                    value={"messages": batch},
                )
            )

        elif ev.kind == "status" and isinstance(ev.payload, dict) and "terminal" in ev.payload:
            terminal = ev.payload["terminal"]
            reason = terminal.get("reason")
            message = terminal.get("message")
            if (
                isinstance(message, str)
                and message.strip()
                and not state.content_streamed
            ):
                for end_event in _reasoning_end_events(state):
                    yield state.encode(end_event)
                for start_event in _ensure_text_message_started(state):
                    yield state.encode(start_event)
                state.content_streamed = True
                yield state.encode(
                    TextMessageContentEvent(
                        type=EventType.TEXT_MESSAGE_CONTENT,
                        message_id=state.assistant_message_id,
                        delta=message,
                    )
                )

            for end_event in _reasoning_end_events(state):
                yield state.encode(end_event)

            if state.content_streamed:
                yield state.encode(
                    TextMessageEndEvent(
                        type=EventType.TEXT_MESSAGE_END,
                        message_id=state.assistant_message_id,
                    )
                )

            finish = _terminal_finish_reason(reason)
            if finish == "success":
                yield state.encode(
                    RunFinishedEvent(
                        type=EventType.RUN_FINISHED,
                        thread_id=thread_id,
                        run_id=run_id,
                        outcome=RunFinishedSuccessOutcome(),
                    )
                )
            else:
                error_text = str(terminal.get("error") or terminal.get("message") or reason or "error")
                yield state.encode(
                    RunErrorEvent(
                        type=EventType.RUN_ERROR,
                        message=error_text,
                    )
                )
            sent_finished = True

    if not sent_finished:
        for end_event in _reasoning_end_events(state):
            yield state.encode(end_event)
        if state.content_streamed:
            yield state.encode(
                TextMessageEndEvent(
                    type=EventType.TEXT_MESSAGE_END,
                    message_id=state.assistant_message_id,
                )
            )
        yield state.encode(
            RunFinishedEvent(
                type=EventType.RUN_FINISHED,
                thread_id=thread_id,
                run_id=run_id,
                outcome=RunFinishedSuccessOutcome(),
            )
        )


def openai_messages_to_ag_ui_snapshot(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert Emperor/OpenAI messages to AG-UI Message dicts for connect snapshots."""
    snapshot: list[dict[str, Any]] = []
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        if role not in ("user", "assistant", "system", "developer"):
            continue
        if role == "assistant":
            thinking = message.get("_thinking")
            if isinstance(thinking, str) and thinking.strip():
                snapshot.append(
                    {
                        "id": f"reasoning_{index}_{uuid.uuid4().hex[:8]}",
                        "role": "reasoning",
                        "content": thinking,
                    }
                )
        content = message.get("content")
        text = _message_text(content)
        if not text.strip() and role == "assistant":
            text = str(content or "")
        if text.strip():
            entry: dict[str, Any] = {
                "id": f"msg_{index}_{uuid.uuid4().hex[:8]}",
                "role": role,
                "content": text,
            }
            tool_calls = message.get("tool_calls")
            if role == "assistant" and isinstance(tool_calls, list) and tool_calls:
                entry["toolCalls"] = tool_calls
            snapshot.append(entry)

        if role != "assistant":
            continue

        a2ui_messages = message.get("a2ui_messages")
        if not isinstance(a2ui_messages, list) or not a2ui_messages:
            continue

        operations = normalize_a2ui_messages(
            [item for item in a2ui_messages if isinstance(item, dict)]
        )
        if not operations:
            continue

        snapshot.append(
            {
                "id": f"a2ui_{index}_{uuid.uuid4().hex[:8]}",
                "role": "activity",
                "activityType": A2UI_ACTIVITY_TYPE,
                "content": {
                    A2UI_OPERATIONS_KEY: operations,
                },
            }
        )
    return snapshot


async def connect_to_ag_ui_sse(
    *,
    thread_id: str,
    run_id: str,
    messages: list[dict[str, Any]],
) -> AsyncIterator[str]:
    """Replay session history to CopilotKit on agent/connect (no new agent run)."""
    encoder = EventEncoder()
    yield encoder.encode(
        RunStartedEvent(
            type=EventType.RUN_STARTED,
            thread_id=thread_id,
            run_id=run_id,
        )
    )
    ag_ui_messages = openai_messages_to_ag_ui_snapshot(messages)
    if ag_ui_messages:
        yield encoder.encode(
            MessagesSnapshotEvent(
                type=EventType.MESSAGES_SNAPSHOT,
                messages=ag_ui_messages,
            )
        )
    yield encoder.encode(
        RunFinishedEvent(
            type=EventType.RUN_FINISHED,
            thread_id=thread_id,
            run_id=run_id,
            outcome=RunFinishedSuccessOutcome(),
        )
    )
