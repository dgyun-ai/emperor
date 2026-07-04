"""Tests for disable_thinking on lightweight LLM calls."""

from __future__ import annotations

import pytest

from agent.deps import AgentDeps
from provider.thinking import build_disable_thinking_extra_body, merge_extra_body
from session.title import generate_session_title
from helpers import mock_text_response


def test_build_disable_thinking_extra_body():
    body = build_disable_thinking_extra_body()
    assert body["enable_thinking"] is False
    assert body["thinking"] is False
    assert body["chat_template_kwargs"]["thinking"] is False
    assert body["reasoning"]["enabled"] is False
    assert body["reasoning"]["effort"] == "none"
    assert body["reasoning_effort"] == "none"


def test_merge_extra_body_preserves_disable_flags():
    merged = merge_extra_body(build_disable_thinking_extra_body(), {"foo": 1})
    assert merged is not None
    assert merged["enable_thinking"] is False
    assert merged["foo"] == 1


@pytest.mark.asyncio
async def test_generate_session_title_passes_disable_thinking():
    captured: dict[str, object] = {}

    async def call_model(**kwargs: object) -> object:
        captured.update(kwargs)
        async for chunk in mock_text_response("Python爬虫开发"):
            yield chunk

    title = await generate_session_title(
        AgentDeps.with_call_model(call_model),
        "帮我写一个完整的 Python 爬虫脚本来抓取新闻网站",
        language="zh",
    )
    assert title == "Python爬虫开发"
    assert captured.get("disable_thinking") is True
