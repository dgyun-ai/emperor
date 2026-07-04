"""Tests for openclaw event conversion."""

from __future__ import annotations

from agent.loop import validate_messages
from session.convert import (
    bootstrap_session_events,
    build_user_event,
    events_to_openai_messages,
    normalize_message_history,
    openai_message_to_event,
    parent_for_next_event,
)
from session.events import has_bootstrap, message_text_content


def test_bootstrap_chain():
    events = bootstrap_session_events(
        session_id="sess-1",
        cwd="/tmp/work",
        provider="westmoon",
        model_id="moon1.0",
    )
    assert len(events) == 4
    assert events[0]["type"] == "session"
    assert events[1]["type"] == "model_change"
    assert has_bootstrap(events)


def test_user_and_assistant_roundtrip():
    bootstrap = bootstrap_session_events(session_id="sess-1", cwd="/tmp")
    parent = parent_for_next_event(bootstrap)
    user_event = build_user_event("hello", parent_id=parent)
    events = [*bootstrap, user_event]
    assistant_openai = {"role": "assistant", "content": "hi there"}
    assistant_event = openai_message_to_event(
        assistant_openai,
        parent_id=parent_for_next_event(events),
        provider="emperor",
        model="default",
    )
    events.append(assistant_event)
    messages = events_to_openai_messages(events)
    assert messages == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]


def test_tool_call_blocks():
    bootstrap = bootstrap_session_events(session_id="sess-1", cwd="/tmp")
    parent = parent_for_next_event(bootstrap)
    assistant_event = openai_message_to_event(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "echo", "arguments": '{"message":"x"}'},
                }
            ],
        },
        parent_id=parent,
    )
    messages = events_to_openai_messages([*bootstrap, assistant_event])
    assert messages[0]["tool_calls"][0]["function"]["name"] == "echo"


def test_thinking_blocks_roundtrip():
    bootstrap = bootstrap_session_events(session_id="sess-1", cwd="/tmp")
    parent = parent_for_next_event(bootstrap)
    assistant_event = openai_message_to_event(
        {
            "role": "assistant",
            "_thinking": "step by step",
            "content": "final answer",
        },
        parent_id=parent,
    )
    messages = events_to_openai_messages([*bootstrap, assistant_event])
    assert messages == [
        {
            "role": "assistant",
            "_thinking": "step by step",
            "content": "final answer",
        }
    ]


def test_message_text_content():
    event = build_user_event("export me", parent_id="abc")
    assert message_text_content(event) == "export me"


def test_a2ui_block_roundtrip():
    bootstrap = bootstrap_session_events(session_id="sess-1", cwd="/tmp")
    parent = parent_for_next_event(bootstrap)
    a2ui_messages = [
        {
            "version": "v0.9",
            "createSurface": {
                "surfaceId": "turn-main",
                "catalogId": "https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json",
            },
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "turn-main",
                "components": [{"id": "root", "component": "Text", "text": "Hi"}],
            },
        },
    ]
    assistant_event = openai_message_to_event(
        {
            "role": "assistant",
            "a2ui_messages": a2ui_messages,
            "a2ui_surface_id": "turn-main",
        },
        parent_id=parent,
    )
    events = [*bootstrap, assistant_event]
    messages = events_to_openai_messages(events)
    assert messages[0]["a2ui_messages"] == a2ui_messages
    assert messages[0]["a2ui_surface_id"] == "turn-main"


def test_consecutive_assistant_a2ui_merged():
    from agent.loop import validate_messages

    bootstrap = bootstrap_session_events(session_id="sess-1", cwd="/tmp")
    parent = parent_for_next_event(bootstrap)
    user_event = build_user_event("hello", parent_id=parent)
    events = [*bootstrap, user_event]
    parent = parent_for_next_event(events)
    text_event = openai_message_to_event(
        {"role": "assistant", "content": "Here is your form."},
        parent_id=parent,
    )
    events.append(text_event)
    parent = parent_for_next_event(events)
    a2ui_event = openai_message_to_event(
        {
            "role": "assistant",
            "a2ui_messages": [{"version": "v0.9", "createSurface": {"surfaceId": "main"}}],
            "a2ui_surface_id": "main",
        },
        parent_id=parent,
    )
    events.append(a2ui_event)
    messages = events_to_openai_messages(events, strip_a2ui=True)
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "Here is your form."
    assert "a2ui_messages" not in messages[1]
    validate_messages(messages)


def test_normalize_message_history_merges_consecutive_assistants():
    messages = normalize_message_history(
        [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "part 1"},
            {"role": "assistant", "content": " part 2"},
        ]
    )
    assert messages == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "part 1 part 2"},
    ]


def test_normalize_message_history_merges_consecutive_users():
    messages = normalize_message_history(
        [
            {"role": "user", "content": "first"},
            {"role": "user", "content": "second"},
            {"role": "assistant", "content": "ok"},
        ]
    )
    assert messages == [
        {"role": "user", "content": "first\n\nsecond"},
        {"role": "assistant", "content": "ok"},
    ]
    validate_messages(messages)


def test_a2ui_stripped_for_agent():
    bootstrap = bootstrap_session_events(session_id="sess-1", cwd="/tmp")
    parent = parent_for_next_event(bootstrap)
    assistant_event = openai_message_to_event(
        {
            "role": "assistant",
            "content": "UI",
            "a2ui_messages": [{"version": "v0.9"}],
            "a2ui_surface_id": "main",
        },
        parent_id=parent,
    )
    events = [*bootstrap, assistant_event]
    messages = events_to_openai_messages(events, strip_a2ui=True)
    assert messages[0]["content"] == "UI"
    assert "a2ui_messages" not in messages[0]
