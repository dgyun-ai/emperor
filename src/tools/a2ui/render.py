"""render_a2ui tool — validate and emit A2UI v0.9 messages to the client."""

from __future__ import annotations

import json
from typing import Any

from emperor_a2ui.flat import flat_render_input_to_messages
from emperor_a2ui.normalize import normalize_a2ui_messages
from emperor_a2ui.validate import A2uiValidationError, extract_surface_ids, validate_a2ui_messages
from context.tool_context import ToolContext
from tools.base import ToolResult
from tools.registry import register_tool


@register_tool(
    name="render_a2ui",
    description=(
        "Render or update an interactive UI surface using the A2UI v0.9 protocol. "
        "Either pass messages[] (createSurface, updateComponents, updateDataModel, deleteSurface) "
        "or CopilotKit flat args: surfaceId, components, and optional data."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "messages": {
                "type": "array",
                "description": "A2UI v0.9 server-to-client messages",
                "items": {"type": "object"},
            },
            "surfaceId": {
                "type": "string",
                "description": "CopilotKit flat format: unique surface ID",
            },
            "components": {
                "type": "array",
                "description": "CopilotKit flat format: component tree (must include id=root)",
                "items": {"type": "object"},
            },
            "data": {
                "type": "object",
                "description": "CopilotKit flat format: optional root data model object",
            },
            "catalogId": {
                "type": "string",
                "description": "Catalog ID for createSurface (defaults to basic)",
            },
        },
    },
    toolset="core",
    is_interactive=True,
)
async def render_a2ui(input: dict[str, Any], ctx: ToolContext) -> ToolResult:
    messages = flat_render_input_to_messages(input)
    if not messages:
        raw = input.get("messages")
        if isinstance(raw, list) and not raw:
            error = "messages must be a non-empty array"
        elif _pick_flat_fields(input):
            error = "surfaceId and a non-empty components array are required in flat format"
        else:
            error = (
                "provide either messages[] or CopilotKit flat args "
                "(surfaceId, components, optional data)"
            )
        return ToolResult(
            content=json.dumps({"ok": False, "error": error}),
            is_error=True,
        )

    try:
        validate_a2ui_messages(messages)
    except A2uiValidationError as exc:
        return ToolResult(
            content=json.dumps({"ok": False, "error": str(exc)}),
            is_error=True,
        )

    messages = normalize_a2ui_messages(messages)

    ctx.emit_a2ui(messages)
    surface_ids = extract_surface_ids(messages)
    return ToolResult(
        content=json.dumps(
            {
                "ok": True,
                "count": len(messages),
                "surfaceIds": surface_ids,
            },
            ensure_ascii=False,
        )
    )


def _pick_flat_fields(input_data: dict[str, Any]) -> bool:
    return any(
        key in input_data
        for key in ("surfaceId", "surface_id", "components", "data", "catalogId", "catalog_id")
    )
