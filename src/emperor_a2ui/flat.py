"""Convert CopilotKit flat render_a2ui args into A2UI v0.9 messages."""

from __future__ import annotations

import json
from typing import Any

BASIC_COMPONENTS = frozenset(
    {
        "AudioPlayer",
        "Button",
        "Card",
        "CheckBox",
        "ChoicePicker",
        "Column",
        "DateTimeInput",
        "Divider",
        "Icon",
        "Image",
        "List",
        "Modal",
        "Row",
        "Slider",
        "Tabs",
        "Text",
        "TextField",
        "Video",
    }
)

_COMPONENT_ALIASES = {
    "box": "Column",
    "checkbox": "CheckBox",
    "container": "Column",
    "flex": "Row",
    "gallery": "List",
    "grid": "Column",
    "heading": "Text",
    "input": "TextField",
    "paragraph": "Text",
    "progress": "Slider",
    "select": "ChoicePicker",
    "stack": "Column",
}


def _pick_string(data: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _maybe_parse_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return value
    if text[0] not in "[{":
        return value
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


def _normalize_component_name(name: Any) -> Any:
    if not isinstance(name, str):
        return name
    if name in BASIC_COMPONENTS:
        return name
    mapped = _COMPONENT_ALIASES.get(name.lower())
    return mapped or name


def normalize_component(component: Any) -> Any:
    """Normalize CopilotKit nested component objects to flat component records."""
    if not isinstance(component, dict):
        return component

    component_name = component.get("component")
    if not component_name or isinstance(component_name, str):
        normalized = dict(component)
        if isinstance(normalized.get("component"), str):
            normalized["component"] = _normalize_component_name(normalized["component"])
        return normalized

    if isinstance(component_name, dict) and len(component_name) == 1:
        name, props = next(iter(component_name.items()))
        normalized: dict[str, Any] = {
            "component": _normalize_component_name(name),
        }
        comp_id = component.get("id")
        if comp_id is not None:
            normalized["id"] = comp_id
        if isinstance(props, dict):
            normalized.update(props)
        return normalized

    return component


def _child_references(component: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    for key in ("child", "children"):
        value = component.get(key)
        if isinstance(value, str):
            refs.add(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    refs.add(item)
                elif isinstance(item, dict):
                    component_id = item.get("componentId")
                    if isinstance(component_id, str):
                        refs.add(component_id)
        elif isinstance(value, dict):
            component_id = value.get("componentId")
            if isinstance(component_id, str):
                refs.add(component_id)
    return refs


def ensure_root_component(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ensure exactly one component uses id=root, as required by A2UI renderers."""
    if any(comp.get("id") == "root" for comp in components):
        return components

    if len(components) == 1:
        only = dict(components[0])
        only["id"] = "root"
        return [only]

    referenced: set[str] = set()
    for comp in components:
        referenced.update(_child_references(comp))

    top_level = [comp for comp in components if comp.get("id") not in referenced]
    if len(top_level) == 1:
        top = dict(top_level[0])
        top["id"] = "root"
        others = [comp for comp in components if comp is not top_level[0]]
        return [top, *others]

    top_ids = [
        str(comp.get("id"))
        for comp in top_level
        if isinstance(comp.get("id"), str) and str(comp.get("id")).strip()
    ]
    if not top_ids:
        top_ids = [
            str(comp.get("id"))
            for comp in components
            if isinstance(comp.get("id"), str) and str(comp.get("id")).strip()
        ]

    return [
        {
            "id": "root",
            "component": "Column",
            "children": top_ids,
        },
        *components,
    ]


def flat_render_input_to_messages(input_data: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Return v0.9 messages from either messages[] or CopilotKit flat args."""
    raw_messages = _maybe_parse_json(input_data.get("messages"))
    if isinstance(raw_messages, list) and raw_messages:
        messages = [m for m in raw_messages if isinstance(m, dict)]
        return messages or None

    surface_id = _pick_string(input_data, "surfaceId", "surface_id")
    components = _maybe_parse_json(input_data.get("components"))
    if isinstance(components, dict):
        components = [components]
    if not surface_id or not isinstance(components, list) or not components:
        return None

    normalized_components = [
        comp
        for comp in (normalize_component(item) for item in components)
        if isinstance(comp, dict)
    ]
    if not normalized_components:
        return None
    normalized_components = ensure_root_component(normalized_components)

    catalog_id = _pick_string(input_data, "catalogId", "catalog_id") or "basic"
    create_surface: dict[str, Any] = {
        "surfaceId": surface_id,
        "catalogId": catalog_id,
    }

    theme = input_data.get("theme")
    if isinstance(theme, dict) and theme:
        create_surface["theme"] = theme

    send_data_model = input_data.get("sendDataModel")
    if send_data_model is None:
        send_data_model = input_data.get("send_data_model")
    if isinstance(send_data_model, bool):
        create_surface["sendDataModel"] = send_data_model

    messages: list[dict[str, Any]] = [
        {"version": "v0.9", "createSurface": create_surface},
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": surface_id,
                "components": normalized_components,
            },
        },
    ]

    data = _maybe_parse_json(input_data.get("data"))
    if isinstance(data, dict) and data:
        messages.append(
            {
                "version": "v0.9",
                "updateDataModel": {
                    "surfaceId": surface_id,
                    "path": "/",
                    "value": data,
                },
            }
        )

    return messages
