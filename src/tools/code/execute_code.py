"""Sandboxed Python code execution."""

from __future__ import annotations

import io
import json
import traceback
from contextlib import redirect_stdout, redirect_stderr

from context.tool_context import ToolContext
from tools.base import ToolResult
from tools.registry import register_tool

SAFE_BUILTINS = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "print": print,
    "range": range,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
}


@register_tool(
    name="execute_code",
    description="Execute Python code in a restricted sandbox.",
    toolset="code",
    input_schema={
        "type": "object",
        "properties": {
            "code": {"type": "string"},
        },
        "required": ["code"],
    },
)
async def execute_code(input: dict, ctx: ToolContext) -> ToolResult:
    code = input["code"]
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    namespace: dict = {"__builtins__": SAFE_BUILTINS}

    try:
        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            exec(code, namespace, namespace)
    except Exception:
        return ToolResult(
            content=json.dumps({"stdout": stdout_buf.getvalue(), "error": traceback.format_exc()}),
            is_error=True,
        )

    return ToolResult(
        content=json.dumps({
            "stdout": stdout_buf.getvalue(),
            "stderr": stderr_buf.getvalue(),
            "result": str(namespace.get("result", "")),
        })
    )
