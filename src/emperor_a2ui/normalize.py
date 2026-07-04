"""Normalize A2UI messages before persist/emit (value path bindings)."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

# CopilotKit's @a2ui-renderer registers the basic catalog under this ID.
COPILOTKIT_BASIC_CATALOG_ID = (
    "https://a2ui.org/specification/v0_9/basic_catalog.json"
)

# Python a2ui SDK and older payloads may use these aliases.
_BASIC_CATALOG_ALIASES = {
    "basic": COPILOTKIT_BASIC_CATALOG_ID,
    COPILOTKIT_BASIC_CATALOG_ID: COPILOTKIT_BASIC_CATALOG_ID,
    "https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json": (
        COPILOTKIT_BASIC_CATALOG_ID
    ),
}

VALUE_COMPONENTS = frozenset(
    {"TextField", "CheckBox", "Slider", "DateTimeInput", "ChoicePicker"}
)


def _has_path_binding(value: Any) -> bool:
    return isinstance(value, dict) and "path" in value


def _default_value_for_component(component: str) -> Any:
    if component == "CheckBox":
        return False
    if component == "ChoicePicker":
        return []
    if component == "Slider":
        return 0
    return ""


def normalize_catalog_id(catalog_id: str) -> str:
    """Map bundled/legacy basic catalog IDs to the CopilotKit renderer catalog ID."""
    return _BASIC_CATALOG_ALIASES.get(catalog_id, catalog_id)


def _normalize_create_surface_message(message: dict[str, Any]) -> dict[str, Any]:
    create = message.get("createSurface")
    if not isinstance(create, dict):
        return message
    catalog_id = create.get("catalogId")
    if not isinstance(catalog_id, str):
        return message
    normalized_id = normalize_catalog_id(catalog_id)
    if normalized_id == catalog_id:
        return message
    return {
        **message,
        "createSurface": {
            **create,
            "catalogId": normalized_id,
        },
    }


def _is_list_template_children(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("componentId"), str)
        and isinstance(value.get("path"), str)
    )


def _collect_child_ids(component: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    for key in ("child", "children"):
        value = component.get(key)
        if isinstance(value, str):
            refs.add(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    refs.add(item)
    return refs


def _collect_template_subtree(root_id: str, by_id: dict[str, dict[str, Any]]) -> set[str]:
    seen: set[str] = set()
    queue = [root_id]
    while queue:
        component_id = queue.pop()
        if component_id in seen or component_id not in by_id:
            continue
        seen.add(component_id)
        queue.extend(_collect_child_ids(by_id[component_id]))
    return seen


def _rewrite_single_segment_template_path(value: Any) -> Any:
    if not isinstance(value, dict) or "path" not in value:
        return value
    path = value.get("path")
    if not isinstance(path, str):
        return value
    if path.startswith("/") and "/" not in path[1:]:
        return {"path": path[1:]}
    return value


def _normalize_paths_in_template_component(component: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(component)
    for key, value in list(normalized.items()):
        if key in {"id", "component"}:
            continue
        if isinstance(value, dict):
            normalized[key] = _rewrite_single_segment_template_path(value)
    return normalized


def _normalize_list_template_paths(components: list[Any]) -> list[Any]:
    """Rewrite `/field` bindings to `field` inside List template subtrees."""
    by_id: dict[str, dict[str, Any]] = {
        str(comp["id"]): comp
        for comp in components
        if isinstance(comp, dict) and isinstance(comp.get("id"), str)
    }
    template_ids: set[str] = set()
    for comp in components:
        if not isinstance(comp, dict):
            continue
        children = comp.get("children")
        if _is_list_template_children(children):
            template_ids.update(_collect_template_subtree(str(children["componentId"]), by_id))

    if not template_ids:
        return components

    normalized: list[Any] = []
    for comp in components:
        if isinstance(comp, dict) and comp.get("id") in template_ids:
            normalized.append(_normalize_paths_in_template_component(comp))
        else:
            normalized.append(comp)
    return normalized


def _normalize_update_components_message(message: dict[str, Any]) -> list[dict[str, Any]]:
    update = message.get("updateComponents")
    if not isinstance(update, dict):
        return [message]

    surface_id = update.get("surfaceId")
    components = update.get("components")
    if not isinstance(surface_id, str) or not isinstance(components, list):
        return [message]

    next_components: list[Any] = []
    data_model_patches: list[tuple[str, Any]] = []

    for raw in components:
        if not isinstance(raw, dict):
            next_components.append(raw)
            continue
        comp = deepcopy(raw)
        component_name = str(comp.get("component") or "")
        if component_name in VALUE_COMPONENTS and not _has_path_binding(comp.get("value")):
            comp_id = str(comp.get("id") or "").strip()
            if comp_id:
                path = f"/fields/{comp_id}"
                comp["value"] = {"path": path}
                data_model_patches.append((path, _default_value_for_component(component_name)))
        next_components.append(comp)

    next_components = _normalize_list_template_paths(next_components)

    normalized_update = {
        **message,
        "updateComponents": {
            **update,
            "surfaceId": surface_id,
            "components": next_components,
        },
    }

    if not data_model_patches:
        return [normalized_update]

    data_model_messages: list[dict[str, Any]] = [
        {
            "version": "v0.9",
            "updateDataModel": {
                "surfaceId": surface_id,
                "path": path,
                "value": value,
            },
        }
        for path, value in data_model_patches
    ]

    return [normalized_update, *data_model_messages]


def normalize_a2ui_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ensure interactive components have data-model paths so inputs remain editable."""
    normalized: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            normalized.append(message)
            continue
        if "createSurface" in message:
            normalized.append(_normalize_create_surface_message(message))
            continue
        if "updateComponents" in message:
            normalized.extend(_normalize_update_components_message(message))
            continue
        normalized.append(message)
    return normalized
