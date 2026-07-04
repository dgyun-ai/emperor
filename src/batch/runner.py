"""Batch runner for multiple prompts."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent.deps import AgentDeps
from config.models import EmperorConfig
from engine.query_engine import QueryEngine
from tools.registry import discover_tools, get_tools_for_toolsets


@dataclass
class BatchResult:
    prompt: str
    response: str
    error: str | None = None


async def run_batch(
    prompts: list[str],
    *,
    deps: AgentDeps,
    tools: list | None = None,
    max_turns: int = 10,
    concurrency: int = 1,
    config: EmperorConfig | None = None,
) -> list[BatchResult]:
    """Run multiple prompts sequentially or with limited concurrency."""
    discover_tools()
    tool_list = tools or get_tools_for_toolsets()
    results: list[BatchResult] = []
    sem = asyncio.Semaphore(concurrency)
    cfg = config or EmperorConfig()

    async def run_one(prompt: str) -> BatchResult:
        async with sem:
            engine = QueryEngine(deps=deps, tools=tool_list, max_turns=max_turns, config=cfg)
            try:
                text = await engine.chat(prompt)
                return BatchResult(prompt=prompt, response=text)
            except Exception as exc:  # noqa: BLE001
                return BatchResult(prompt=prompt, response="", error=str(exc))

    tasks = [run_one(p) for p in prompts]
    return list(await asyncio.gather(*tasks))


async def run_batch_file(
    path: Path,
    *,
    deps: AgentDeps,
    output: Path | None = None,
) -> list[BatchResult]:
    """Run prompts from a JSON file with {prompts: [...]}."""
    data = json.loads(path.read_text(encoding="utf-8"))
    prompts = data.get("prompts", [])
    results = await run_batch(prompts, deps=deps)
    if output:
        out = [{"prompt": r.prompt, "response": r.response, "error": r.error} for r in results]
        output.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    return results
