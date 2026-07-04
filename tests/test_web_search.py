"""Tests for web_search HTML parsing."""

from __future__ import annotations

import asyncio
import json
import time

import pytest

from tools.web.tools import (
    _normalize_ddgs_results,
    _parse_ddg_html,
    _parse_ddg_lite,
    _search_ddgs_sync,
    web_search,
)


LITE_SAMPLE = """
<tr>
  <td></td>
  <td>
    <a rel="nofollow" href="https://www.python.org/" class='result-link'>Welcome to Python.org</a>
  </td>
</tr>
<tr>
  <td>&nbsp;</td>
  <td class='result-snippet'>
    Learn the basics of the world&#x27;s fastest growing language.
  </td>
</tr>
<tr>
  <td></td>
  <td>
    <a rel="nofollow" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com" class='result-link'>Example</a>
  </td>
</tr>
<tr>
  <td>&nbsp;</td>
  <td class='result-snippet'>Example snippet text.</td>
</tr>
"""

HTML_SAMPLE = """
<a class="result__a" href="https://www.python.org/">Welcome to Python.org</a>
<a class="result__snippet" href="#">Learn Python basics.</a>
<a class="result__a" href="https://docs.python.org/">Python documentation</a>
<a class="result__snippet" href="#">Official docs.</a>
"""

def test_normalize_ddgs_results():
    raw = [
        {"title": "Example", "href": "https://example.com", "body": "Snippet text."},
        {"title": "", "href": "https://skip.me"},
    ]
    results = _normalize_ddgs_results(raw, max_results=5)
    assert len(results) == 1
    assert results[0]["url"] == "https://example.com"
    assert results[0]["snippet"] == "Snippet text."


def test_parse_ddg_lite_results():
    results = _parse_ddg_lite(LITE_SAMPLE, max_results=5)
    assert len(results) == 2
    assert results[0]["title"] == "Welcome to Python.org"
    assert results[0]["url"] == "https://www.python.org/"
    assert "fastest growing" in results[0]["snippet"]
    assert results[1]["url"] == "https://example.com"


def test_parse_ddg_html_results():
    results = _parse_ddg_html(HTML_SAMPLE, max_results=5)
    assert len(results) == 2
    assert results[0]["title"] == "Welcome to Python.org"
    assert results[0]["snippet"] == "Learn Python basics."
    assert results[1]["url"] == "https://docs.python.org/"


def test_search_ddgs_sync_tries_backends(monkeypatch):
    calls: list[str] = []

    class FakeDDGS:
        def text(self, query: str, **kwargs):
            backend = kwargs.get("backend", "auto")
            calls.append(backend)
            if backend == "auto":
                raise RuntimeError("auto unavailable")
            return [{"title": "Example", "href": "https://example.com", "body": "ok"}]

    monkeypatch.setattr("ddgs.DDGS", FakeDDGS)
    results = _search_ddgs_sync("python", max_results=3)
    assert len(results) == 1
    assert results[0]["url"] == "https://example.com"
    assert calls == ["auto", "bing"]


@pytest.mark.asyncio
async def test_web_search_times_out(monkeypatch):
    from context.tool_context import ToolContext

    async def slow_search(query: str, max_results: int):
        await asyncio.sleep(60)
        return []

    monkeypatch.setattr("tools.web.tools._SEARCH_TOTAL_TIMEOUT", 0.2)
    monkeypatch.setattr("tools.web.tools._search_duckduckgo", slow_search)
    ctx = ToolContext(messages=[])
    start = time.time()
    result = await web_search({"query": "python"}, ctx)
    elapsed = time.time() - start
    assert result.is_error
    assert "timed out" in result.content.lower()
    assert elapsed < 5


@pytest.mark.asyncio
async def test_web_search_tool_uses_parser(monkeypatch):
    from context.tool_context import ToolContext

    async def fake_search(query: str, max_results: int):
        return _parse_ddg_lite(LITE_SAMPLE, max_results)

    monkeypatch.setattr("tools.web.tools._search_duckduckgo", fake_search)
    ctx = ToolContext(messages=[])
    result = await web_search({"query": "python", "max_results": 2}, ctx)
    assert not result.is_error
    payload = json.loads(result.content)
    assert len(payload["results"]) == 2
    assert payload["results"][0]["url"] == "https://www.python.org/"


@pytest.mark.asyncio
async def test_web_search_falls_back_when_ddgs_times_out(monkeypatch):
    from context.tool_context import ToolContext

    async def slow_ddgs(query: str, max_results: int):
        raise asyncio.TimeoutError()

    async def fallback(query: str, max_results: int):
        return _parse_ddg_lite(LITE_SAMPLE, max_results)

    monkeypatch.setattr("tools.web.tools._search_ddgs", slow_ddgs)
    monkeypatch.setattr("tools.web.tools._search_duckduckgo_html", fallback)
    ctx = ToolContext(messages=[])
    result = await web_search({"query": "python", "max_results": 1}, ctx)
    payload = json.loads(result.content)
    assert not result.is_error
    assert payload["results"][0]["url"] == "https://www.python.org/"


@pytest.mark.asyncio
async def test_web_search_falls_back_when_ddgs_errors(monkeypatch):
    from context.tool_context import ToolContext

    async def failing_ddgs(query: str, max_results: int):
        raise RuntimeError("ddgs failed")

    async def fallback(query: str, max_results: int):
        return _parse_ddg_lite(LITE_SAMPLE, max_results)

    monkeypatch.setattr("tools.web.tools._search_ddgs", failing_ddgs)
    monkeypatch.setattr("tools.web.tools._search_duckduckgo_html", fallback)
    ctx = ToolContext(messages=[])
    result = await web_search({"query": "python", "max_results": 1}, ctx)
    payload = json.loads(result.content)
    assert not result.is_error
    assert payload["results"][0]["url"] == "https://www.python.org/"


@pytest.mark.asyncio
async def test_web_search_errors_when_both_backends_fail(monkeypatch):
    from context.tool_context import ToolContext

    async def failing_ddgs(query: str, max_results: int):
        raise RuntimeError("ddgs failed")

    async def failing_html(query: str, max_results: int):
        raise httpx.HTTPError("ddg failed")

    monkeypatch.setattr("tools.web.tools._search_ddgs", failing_ddgs)
    monkeypatch.setattr("tools.web.tools._search_duckduckgo_html", failing_html)
    ctx = ToolContext(messages=[])
    result = await web_search({"query": "python", "max_results": 1}, ctx)
    assert result.is_error
    assert "search failed" in result.content.lower()
