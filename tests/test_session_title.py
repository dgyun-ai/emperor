"""Tests for LLM session title generation."""

from __future__ import annotations

import pytest

from agent.deps import AgentDeps
from engine.query_engine import QueryEngine
from helpers import make_sequential_mock, mock_text_response
from session.store import SessionStore
from session.title import (
    build_title_prompt,
    extract_title_from_model_output,
    generate_session_title,
    is_acceptable_title,
    is_garbage_title,
    is_placeholder_title,
    max_title_len,
    normalize_title,
    should_use_direct_title,
    truncate_title,
)


def test_normalize_title_strips_quotes():
    assert normalize_title('「Python 脚本调试」') == "Python 脚本调试"
    assert normalize_title('"Hello world"') == "Hello world"


def test_should_use_direct_title_for_short_zh():
    assert should_use_direct_title("你是谁")
    assert should_use_direct_title("a" * max_title_len("en"), language="en")
    assert not should_use_direct_title("帮我写一个完整的 Python 爬虫脚本来抓取多个新闻网站")


def test_truncate_title_respects_language_limit():
    long_zh = "帮我写一个完整的 Python 爬虫脚本来抓取多个新闻网站"
    assert len(truncate_title(long_zh, language="zh")) <= max_title_len("zh")
    long_en = "a" * 40
    assert len(truncate_title(long_en, language="en")) <= max_title_len("en")


def test_is_garbage_title_rejects_reasoning_tokens():
    assert is_garbage_title("p2")
    assert is_garbage_title("P2")
    assert not is_garbage_title("部署文档整理")


def test_is_placeholder_title():
    assert is_placeholder_title("新会话")
    assert is_placeholder_title("New Session")
    assert not is_placeholder_title("部署文档整理")


def test_extract_title_prefers_final_text_over_stream_garbage():
    title = extract_title_from_model_output(
        "p2",
        "部署文档整理",
        message="帮我整理项目的部署文档",
        language="zh",
    )
    assert title == "部署文档整理"


def test_extract_title_rejects_both_garbage_candidates():
    assert extract_title_from_model_output(
        "p2",
        "p2",
        message="帮我整理项目的部署文档",
        language="zh",
    ) is None


@pytest.mark.asyncio
async def test_backfill_repairs_garbage_title(tmp_path):
    store = SessionStore(tmp_path / "state.db")
    await store.initialize()
    sid = await store.create_session(profile="default", title="p2")
    await store.append_message(
        sid,
        {"role": "user", "content": "帮我整理项目的部署文档并写一份详细的检查清单"},
    )
    sessions = await store.list_sessions(profile="default")
    repaired = await store.backfill_missing_titles(sessions, language="zh")
    assert repaired[0].title != "p2"
    assert repaired[0].title.startswith("帮我整理项目的部署")


def test_is_acceptable_title_rejects_reasoning_garbage():
    assert not is_acceptable_title("p2", "你是谁")
    assert is_acceptable_title("身份介绍", "你是谁")


def test_build_title_prompt_zh():
    prompt = build_title_prompt("帮我写爬虫", language="zh", assistant_reply="好的")
    assert "帮我写爬虫" in prompt
    assert "好的" in prompt
    assert "15个字" in prompt
    assert "首轮对话" in prompt


@pytest.mark.asyncio
async def test_generate_session_title_rejects_reasoning_garbage():
    call_model = make_sequential_mock([lambda: mock_text_response("p2")])
    title = await generate_session_title(
        AgentDeps.with_call_model(call_model),
        "帮我写一个完整的 Python 爬虫脚本来抓取新闻网站",
        language="zh",
    )
    assert title is None


@pytest.mark.asyncio
async def test_generate_session_title_mock():
    call_model = make_sequential_mock([lambda: mock_text_response("Python爬虫开发")])
    title = await generate_session_title(
        AgentDeps.with_call_model(call_model),
        "帮我写一个 Python 爬虫脚本",
        language="zh",
    )
    assert title == "Python爬虫开发"


@pytest.mark.asyncio
async def test_short_message_title_is_user_text_not_llm_garbage(tmp_path):
    store = SessionStore(tmp_path / "state.db")
    call_model = make_sequential_mock([lambda: mock_text_response("我是 Emperor 助手。")])
    engine = QueryEngine(
        deps=AgentDeps.with_call_model(call_model),
        session_store=store,
        profile="default",
        max_turns=5,
    )
    await engine.chat("你是谁")

    sessions = await store.list_sessions(profile="default")
    assert sessions[0].title == "你是谁"


@pytest.mark.asyncio
async def test_long_message_rejects_garbage_llm_title(tmp_path):
    store = SessionStore(tmp_path / "state.db")
    long_msg = "帮我写一个完整的 Python 爬虫脚本来抓取多个新闻网站"
    call_model = make_sequential_mock(
        [
            lambda: mock_text_response("好的。"),
            lambda: mock_text_response("p2"),
        ]
    )
    engine = QueryEngine(
        deps=AgentDeps.with_call_model(call_model),
        session_store=store,
        profile="default",
        max_turns=5,
    )
    await engine.chat(long_msg)

    sessions = await store.list_sessions(profile="default")
    assert sessions[0].title != "p2"
    assert sessions[0].title.startswith("帮我写一个完整的")
    assert len(sessions[0].title or "") <= max_title_len("zh")


@pytest.mark.asyncio
async def test_first_message_generates_llm_title(tmp_path):
    store = SessionStore(tmp_path / "state.db")
    call_model = make_sequential_mock(
        [
            lambda: mock_text_response("好的，我来帮你。"),
            lambda: mock_text_response("部署文档整理"),
        ]
    )
    engine = QueryEngine(
        deps=AgentDeps.with_call_model(call_model),
        session_store=store,
        profile="default",
        max_turns=5,
    )
    await engine.chat("帮我整理项目的部署文档并写一份详细的检查清单")

    sessions = await store.list_sessions(profile="default")
    assert len(sessions) == 1
    assert sessions[0].title == "部署文档整理"


@pytest.mark.asyncio
async def test_placeholder_title_replaced_after_first_turn(tmp_path):
    store = SessionStore(tmp_path / "state.db")
    await store.initialize()
    sid = await store.create_session(profile="default", title="新会话")
    call_model = make_sequential_mock([lambda: mock_text_response("你好，我是助手。")])
    engine = QueryEngine(
        deps=AgentDeps.with_call_model(call_model),
        session_store=store,
        profile="default",
        max_turns=5,
        session_id=sid,
    )
    await engine.initialize()
    await engine.chat("你是谁")

    assert await store.get_title(sid) == "你是谁"
