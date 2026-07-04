"""Interactive clarify tool."""

from __future__ import annotations

import json

from context.tool_context import ToolContext
from tools.base import ToolResult
from tools.registry import register_tool

_clarify_handler = None


def set_clarify_handler(handler) -> None:
    global _clarify_handler
    _clarify_handler = handler


@register_tool(
    name="clarify",
    description="向用户提出澄清问题并等待回答（请使用简体中文提问）。",
    toolset="core",
    input_schema={
        "type": "object",
        "properties": {
            "question": {"type": "string"},
            "options": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["question"],
    },
    is_interactive=True,
)
async def clarify_tool(input: dict, ctx: ToolContext) -> ToolResult:
    question = input["question"]
    options = input.get("options", [])

    if _clarify_handler is not None:
        answer = await _clarify_handler(question, options)
        return ToolResult(content=json.dumps({"question": question, "answer": answer}))

    if options:
        opts = ", ".join(f"{i+1}. {o}" for i, o in enumerate(options))
        return ToolResult(
            content=json.dumps({"question": question, "options": options, "prompt": f"{question}\n{opts}"})
        )
    return ToolResult(content=json.dumps({"question": question, "answer": "(no handler configured)"}))
