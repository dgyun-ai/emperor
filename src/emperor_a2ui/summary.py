"""Compact A2UI summaries for agent context when reloading sessions."""

from __future__ import annotations

import json
from typing import Any


def _summarize_component(comp: dict[str, Any], *, depth: int = 0) -> str:
    if depth > 4:
        return "..."
    comp_id = str(comp.get("id") or "?")
    name = str(comp.get("component") or "?")
    parts = [f"{comp_id}:{name}"]
    value = comp.get("value")
    if isinstance(value, dict) and "path" in value:
        parts.append(f"value@{value['path']}")
    children = comp.get("children")
    if isinstance(children, list) and children:
        child_summaries = []
        for child in children[:8]:
            if isinstance(child, dict):
                child_summaries.append(_summarize_component(child, depth=depth + 1))
            elif isinstance(child, str):
                child_summaries.append(child)
        if len(children) > 8:
            child_summaries.append(f"...+{len(children) - 8}")
        parts.append("[" + ", ".join(child_summaries) + "]")
    return "".join(parts)


def _collect_data_model_keys(messages: list[dict[str, Any]]) -> list[str]:
    keys: list[str] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        update = message.get("updateDataModel")
        if not isinstance(update, dict):
            continue
        path = update.get("path")
        if isinstance(path, str) and path.strip():
            keys.append(path.strip())
    return keys


def summarize_a2ui_messages(
    messages: list[dict[str, Any]],
    *,
    surface_id: str | None = None,
) -> str:
    """Build a short text summary of A2UI surfaces for agent memory."""
    if not messages:
        return ""

    sid = surface_id or "unknown"
    for message in messages:
        if not isinstance(message, dict):
            continue
        for key in ("createSurface", "updateComponents", "updateDataModel", "deleteSurface"):
            block = message.get(key)
            if isinstance(block, dict):
                raw_sid = block.get("surfaceId")
                if isinstance(raw_sid, str) and raw_sid.strip():
                    sid = raw_sid.strip()
                    break

    component_lines: list[str] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        update = message.get("updateComponents")
        if not isinstance(update, dict):
            continue
        components = update.get("components")
        if not isinstance(components, list):
            continue
        for comp in components[:20]:
            if isinstance(comp, dict):
                component_lines.append(_summarize_component(comp))

    data_keys = _collect_data_model_keys(messages)
    lines = [f"[A2UI surface {sid}]"]
    if component_lines:
        lines.append("components: " + "; ".join(component_lines[:12]))
        if len(component_lines) > 12:
            lines.append(f"... and {len(component_lines) - 12} more components")
    if data_keys:
        unique_keys = list(dict.fromkeys(data_keys))[:20]
        lines.append("dataModel paths: " + ", ".join(unique_keys))
    return "\n".join(lines)


def append_a2ui_summary_to_message(message: dict[str, Any]) -> dict[str, Any]:
    """Replace stripped a2ui fields with a compact summary in assistant content."""
    a2ui_messages = message.get("a2ui_messages")
    if not isinstance(a2ui_messages, list) or not a2ui_messages:
        return message

    surface_id = message.get("a2ui_surface_id")
    sid = str(surface_id) if isinstance(surface_id, str) else None
    summary = summarize_a2ui_messages(
        [m for m in a2ui_messages if isinstance(m, dict)],
        surface_id=sid,
    )
    if not summary:
        return message

    result = dict(message)
    result.pop("a2ui_messages", None)
    result.pop("a2ui_surface_id", None)

    existing = result.get("content")
    if isinstance(existing, str) and existing.strip():
        result["content"] = existing.rstrip() + "\n\n" + summary
    else:
        result["content"] = summary
    return result
