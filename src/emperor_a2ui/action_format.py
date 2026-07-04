"""Format A2UI user actions for agent consumption."""

from __future__ import annotations

import json
from typing import Any

A2UI_ACTION_FENCE = "a2ui_action"


def build_a2ui_action_payload(
    *,
    surface_id: str,
    action: dict[str, Any],
    context: dict[str, Any] | None = None,
    data_model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": "a2ui_action",
        "surfaceId": surface_id,
        "action": action,
        "context": context or {},
    }
    if data_model is not None:
        payload["dataModel"] = data_model
    source = action.get("sourceComponentId")
    if isinstance(source, str) and source:
        payload["sourceComponentId"] = source
    return payload


def format_a2ui_action_message(
    *,
    surface_id: str,
    action: dict[str, Any],
    context: dict[str, Any] | None = None,
    data_model: dict[str, Any] | None = None,
) -> str:
    """Human-readable line plus fenced JSON block for reliable agent parsing."""
    action_name = str(action.get("name") or "unknown")
    ctx = context or {}
    lines = [
        f"[A2UI Action] surface={surface_id} action={action_name}",
        f"context={json.dumps(ctx, ensure_ascii=False)}",
    ]
    if data_model is not None:
        lines.append(f"dataModel={json.dumps(data_model, ensure_ascii=False)}")
    source = action.get("sourceComponentId")
    if isinstance(source, str) and source:
        lines.append(f"sourceComponentId={source}")

    payload = build_a2ui_action_payload(
        surface_id=surface_id,
        action=action,
        context=ctx,
        data_model=data_model,
    )
    lines.append("")
    lines.append(f"```{A2UI_ACTION_FENCE}")
    lines.append(json.dumps(payload, ensure_ascii=False, indent=2))
    lines.append("```")
    return "\n".join(lines)


def parse_a2ui_action_message(content: str) -> dict[str, Any] | None:
    """Extract structured a2ui_action JSON from a user message if present."""
    marker = f"```{A2UI_ACTION_FENCE}"
    start = content.find(marker)
    if start < 0:
        return None
    body_start = start + len(marker)
    if body_start < len(content) and content[body_start] == "\n":
        body_start += 1
    end = content.find("```", body_start)
    if end < 0:
        return None
    raw = content[body_start:end].strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict) and parsed.get("type") == "a2ui_action":
        return parsed
    return None
