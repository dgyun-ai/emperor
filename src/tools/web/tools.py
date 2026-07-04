"""Web search and extract tools."""

from __future__ import annotations

import asyncio
import html
import json
import logging
import re
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from context.tool_context import ToolContext
from tools.base import ToolResult
from tools.registry import register_tool

logger = logging.getLogger(__name__)

# Limit concurrent searches so ddgs/thread pool and upstream APIs are not flooded.
_WEB_SEARCH_SEM = asyncio.Semaphore(3)
_DDGS_TIMEOUT = 20.0
_HTML_TIMEOUT = 15.0
_SEARCH_TOTAL_TIMEOUT = _DDGS_TIMEOUT + _HTML_TIMEOUT
_DDGS_BACKENDS = ("auto", "bing", "brave")

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
}

_LITE_LINK_RE = re.compile(
    r"<a\b(?P<tag>[^>]*\bclass=['\"]result-link['\"][^>]*)>(?P<title>[^<]*)</a>",
    re.IGNORECASE,
)
_HTML_RESULT_RE = re.compile(
    r'<a[^>]*class="result__a"[^>]*href="(?P<url>[^"]+)"[^>]*>(?P<title>[^<]+)</a>',
    re.IGNORECASE,
)
_HREF_RE = re.compile(r"""href=['"](?P<url>[^'"]+)['"]""", re.IGNORECASE)
_LITE_SNIPPET_RE = re.compile(
    r"""class=['"]result-snippet['"][^>]*>\s*(?P<snippet>[^<]+)""",
    re.IGNORECASE,
)
_HTML_SNIPPET_RE = re.compile(
    r'class="result__snippet"[^>]*>(?P<snippet>[^<]+)',
    re.IGNORECASE,
)


def _decode_ddg_redirect(url: str) -> str:
    """Resolve DuckDuckGo redirect URLs to the target page."""
    if "uddg=" not in url:
        return url
    parsed = urlparse(url)
    uddg = parse_qs(parsed.query).get("uddg", [""])[0]
    return unquote(uddg) if uddg else url


def _clean_text(value: str) -> str:
    return html.unescape(value).strip()


def _parse_ddg_lite(html_text: str, max_results: int) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    snippets = [
        _clean_text(match.group("snippet"))
        for match in _LITE_SNIPPET_RE.finditer(html_text)
        if _clean_text(match.group("snippet"))
    ]

    for index, match in enumerate(_LITE_LINK_RE.finditer(html_text)):
        if len(results) >= max_results:
            break
        href_match = _HREF_RE.search(match.group("tag"))
        if not href_match:
            continue
        title = _clean_text(match.group("title"))
        url = _decode_ddg_redirect(href_match.group("url"))
        if not title or not url:
            continue
        item: dict[str, str] = {"title": title, "url": url}
        if index < len(snippets):
            item["snippet"] = snippets[index]
        results.append(item)
    return results


def _parse_ddg_html(html_text: str, max_results: int) -> list[dict[str, str]]:
    links = list(_HTML_RESULT_RE.finditer(html_text))
    snippets = [_clean_text(match.group("snippet")) for match in _HTML_SNIPPET_RE.finditer(html_text)]

    results: list[dict[str, str]] = []
    for index, match in enumerate(links):
        if len(results) >= max_results:
            break
        title = _clean_text(match.group("title"))
        url = _decode_ddg_redirect(match.group("url"))
        if not title or not url:
            continue
        item: dict[str, str] = {"title": title, "url": url}
        if index < len(snippets) and snippets[index]:
            item["snippet"] = snippets[index]
        results.append(item)
    return results


def _normalize_ddgs_results(raw: list[dict[str, str]], max_results: int) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for item in raw:
        title = _clean_text(str(item.get("title") or ""))
        url = str(item.get("href") or item.get("url") or "").strip()
        if not title or not url:
            continue
        entry: dict[str, str] = {"title": title, "url": url}
        snippet = _clean_text(str(item.get("body") or item.get("snippet") or ""))
        if snippet:
            entry["snippet"] = snippet
        results.append(entry)
        if len(results) >= max_results:
            break
    return results


def _search_ddgs_sync(query: str, max_results: int) -> list[dict[str, str]]:
    from ddgs import DDGS

    for backend in _DDGS_BACKENDS:
        try:
            raw = DDGS().text(query, max_results=max_results, backend=backend)
            results = _normalize_ddgs_results(list(raw), max_results)
            if results:
                return results
        except Exception:
            logger.debug("ddgs backend %s failed for query=%r", backend, query, exc_info=True)
    return []


async def _search_ddgs(query: str, max_results: int) -> list[dict[str, str]]:
    loop = asyncio.get_running_loop()
    return await asyncio.wait_for(
        loop.run_in_executor(None, _search_ddgs_sync, query, max_results),
        timeout=_DDGS_TIMEOUT,
    )


async def _search_duckduckgo_html(query: str, max_results: int) -> list[dict[str, str]]:
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(_HTML_TIMEOUT, connect=10.0),
        follow_redirects=True,
        headers=_BROWSER_HEADERS,
    ) as client:
        try:
            lite_resp = await client.post(
                "https://lite.duckduckgo.com/lite/",
                data={"q": query, "kl": "wt-wt"},
            )
            lite_resp.raise_for_status()
            results = _parse_ddg_lite(lite_resp.text, max_results)
            if results:
                return results
        except httpx.HTTPError:
            logger.debug("ddg lite search failed for query=%r", query, exc_info=True)

        html_resp = await client.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query, "b": ""},
        )
        html_resp.raise_for_status()
        return _parse_ddg_html(html_resp.text, max_results)


async def _search_duckduckgo(query: str, max_results: int) -> list[dict[str, str]]:
    try:
        results = await _search_ddgs(query, max_results)
        if results:
            return results
    except asyncio.TimeoutError:
        logger.warning("ddgs search timed out after %.0fs; falling back to HTML scrape", _DDGS_TIMEOUT)
    except Exception:
        logger.warning("ddgs search failed; falling back to HTML scrape", exc_info=True)

    return await asyncio.wait_for(
        _search_duckduckgo_html(query, max_results),
        timeout=_HTML_TIMEOUT,
    )


@register_tool(
    name="web_search",
    description="Search the web via ddgs first, then DuckDuckGo HTML fallback, and return titles, URLs, and snippets.",
    toolset="web",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 5},
        },
        "required": ["query"],
    },
    is_read_only=True,
)
async def web_search(input: dict, ctx: ToolContext) -> ToolResult:
    query = input["query"]
    max_results = int(input.get("max_results", 5))
    try:
        async with _WEB_SEARCH_SEM:
            results = await asyncio.wait_for(
                _search_duckduckgo(query, max_results),
                timeout=_SEARCH_TOTAL_TIMEOUT,
            )
    except asyncio.TimeoutError:
        return ToolResult(
            content=(
                f"Search timed out after {_SEARCH_TOTAL_TIMEOUT:.0f}s for query: {query!r}. "
                "Try fewer parallel searches or a simpler query."
            ),
            is_error=True,
        )
    except httpx.HTTPError as exc:
        detail = str(exc) or exc.__class__.__name__
        return ToolResult(content=f"Search failed: {detail}", is_error=True)
    except Exception as exc:
        detail = str(exc) or exc.__class__.__name__
        return ToolResult(content=f"Search failed: {detail}", is_error=True)

    if not results:
        return ToolResult(
            content=json.dumps(
                {
                    "query": query,
                    "results": [],
                    "note": "No search results returned; try rephrasing the query.",
                }
            )
        )
    return ToolResult(content=json.dumps({"query": query, "results": results[:max_results]}))


@register_tool(
    name="web_extract",
    description="Fetch a URL and return text content (truncated).",
    toolset="web",
    input_schema={
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "max_chars": {"type": "integer", "default": 9118},
        },
        "required": ["url"],
    },
    is_read_only=True,
)
async def web_extract(input: dict, ctx: ToolContext) -> ToolResult:
    url = input["url"]
    max_chars = int(input.get("max_chars", 9118))
    try:
        async with httpx.AsyncClient(
            timeout=20.0,
            follow_redirects=True,
            headers=_BROWSER_HEADERS,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            text = resp.text[:max_chars]
    except httpx.HTTPError as exc:
        return ToolResult(content=f"Fetch failed: {exc}", is_error=True)
    return ToolResult(content=json.dumps({"url": url, "content": text, "truncated": len(resp.text) > max_chars}))
