"""Tests for follow-up question generation helpers."""

from __future__ import annotations

import pytest

from agent.deps import AgentDeps
from session.follow_up_questions import generate_follow_up_questions, parse_follow_up_questions
from helpers import mock_text_response


def test_parse_empty_array():
    assert parse_follow_up_questions('{"questions": []}') == []


def test_parse_three_questions():
    raw = '{"questions": ["Q1?", "Q2?", "Q3?"]}'
    assert parse_follow_up_questions(raw) == ["Q1?", "Q2?", "Q3?"]


def test_parse_truncates_to_three():
    raw = '{"questions": ["a", "b", "c", "d", "e"]}'
    assert parse_follow_up_questions(raw) == ["a", "b", "c"]


def test_parse_strips_and_dedupes():
    raw = '{"questions": ["  hello  ", "hello", "world"]}'
    assert parse_follow_up_questions(raw) == ["hello", "world"]


def test_parse_json_codeblock():
    raw = '```json\n{"questions": ["one?"]}\n```'
    assert parse_follow_up_questions(raw) == ["one?"]


def test_parse_invalid_returns_empty():
    assert parse_follow_up_questions("not json") == []
    assert parse_follow_up_questions('{"items": ["x"]}') == []


def test_parse_rejects_assistant_perspective_questions():
    raw = (
        '{"questions": ['
        '"您是否计划参观主题乐园？", '
        '"除了世界之窗，深圳还有哪些主题乐园？", '
        '"Would you like hotel tips?", '
        '"帮我推荐深圳本地美食"'
        "]}"
    )
    assert parse_follow_up_questions(raw) == [
        "除了世界之窗，深圳还有哪些主题乐园？",
        "帮我推荐深圳本地美食",
    ]


@pytest.mark.asyncio
async def test_generate_follow_up_questions_passes_disable_thinking_and_max_tokens():
    captured: dict[str, object] = {}

    async def call_model(**kwargs: object) -> object:
        captured.update(kwargs)
        async for chunk in mock_text_response('{"questions": ["Next step?"]}'):
            yield chunk

    questions = await generate_follow_up_questions(
        AgentDeps.with_call_model(call_model),
        "用户问题",
        "助手完整回复",
        language="zh",
    )
    assert questions == ["Next step?"]
    assert captured.get("disable_thinking") is True
    assert captured.get("max_tokens") == 512
