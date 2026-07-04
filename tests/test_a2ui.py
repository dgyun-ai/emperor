"""Tests for A2UI validation helpers."""

from __future__ import annotations

import pytest

from emperor_a2ui.action_format import format_a2ui_action_message, parse_a2ui_action_message
from emperor_a2ui.flat import flat_render_input_to_messages, normalize_component
from emperor_a2ui.normalize import normalize_a2ui_messages
from emperor_a2ui.summary import summarize_a2ui_messages
from emperor_a2ui.validate import A2uiValidationError, extract_surface_ids, validate_a2ui_messages


def _sample_messages():
    return [
        {
            "version": "v0.9",
            "createSurface": {
                "surfaceId": "turn-main",
                "catalogId": "https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json",
            },
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "turn-main",
                "components": [{"id": "root", "component": "Text", "text": "Hello"}],
            },
        },
    ]


def test_validate_a2ui_messages_accepts_valid_payload():
    validate_a2ui_messages(_sample_messages())


def test_validate_a2ui_messages_rejects_empty():
    with pytest.raises(A2uiValidationError):
        validate_a2ui_messages([])


def test_extract_surface_ids():
    assert extract_surface_ids(_sample_messages()) == ["turn-main"]


def test_normalize_maps_basic_catalog_id_for_copilotkit():
    messages = _sample_messages()
    normalized = normalize_a2ui_messages(messages)
    assert (
        normalized[0]["createSurface"]["catalogId"]
        == "https://a2ui.org/specification/v0_9/basic_catalog.json"
    )


def test_normalize_adds_value_paths_and_data_model():
    messages = [
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "form",
                "components": [
                    {"id": "email", "component": "TextField", "label": "Email"},
                ],
            },
        }
    ]
    normalized = normalize_a2ui_messages(messages)
    assert len(normalized) == 2
    field = normalized[0]["updateComponents"]["components"][0]
    assert field["value"] == {"path": "/fields/email"}
    assert normalized[1]["updateDataModel"]["path"] == "/fields/email"


def test_normalize_rewrites_list_template_paths_to_relative():
    messages = [
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "card-list-showcase",
                "components": [
                    {
                        "id": "root",
                        "component": "Column",
                        "children": ["page-title", "card-list"],
                    },
                    {"id": "page-title", "component": "Text", "text": "精选图集", "variant": "h2"},
                    {
                        "id": "card-list",
                        "component": "List",
                        "children": {"componentId": "card-item", "path": "/items"},
                    },
                    {"id": "card-item", "component": "Card", "child": "card-body"},
                    {
                        "id": "card-body",
                        "component": "Column",
                        "children": ["card-image", "card-title", "card-desc"],
                    },
                    {
                        "id": "card-image",
                        "component": "Image",
                        "url": {"path": "/imageUrl"},
                    },
                    {
                        "id": "card-title",
                        "component": "Text",
                        "text": {"path": "/title"},
                        "variant": "h4",
                    },
                    {
                        "id": "card-desc",
                        "component": "Text",
                        "text": {"path": "/description"},
                        "variant": "body",
                    },
                ],
            },
        }
    ]
    normalized = normalize_a2ui_messages(messages)[0]
    by_id = {c["id"]: c for c in normalized["updateComponents"]["components"]}
    assert by_id["card-image"]["url"] == {"path": "imageUrl"}
    assert by_id["card-title"]["text"] == {"path": "title"}
    assert by_id["card-desc"]["text"] == {"path": "description"}
    assert by_id["page-title"]["text"] == "精选图集"


def test_format_and_parse_a2ui_action_message():
    text = format_a2ui_action_message(
        surface_id="login",
        action={"name": "submit", "sourceComponentId": "btn"},
        context={"form": "login"},
        data_model={"/fields/email": "a@b.c"},
    )
    assert "[A2UI Action]" in text
    assert "```a2ui_action" in text
    parsed = parse_a2ui_action_message(text)
    assert parsed is not None
    assert parsed["surfaceId"] == "login"
    assert parsed["action"]["name"] == "submit"


def test_summarize_a2ui_messages():
    summary = summarize_a2ui_messages(_sample_messages(), surface_id="turn-main")
    assert "turn-main" in summary
    assert "root:Text" in summary


def test_events_to_openai_messages_a2ui_summary():
    from session.convert import events_to_openai_messages

    events = [
        {
            "type": "message",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Here is a form."},
                    {
                        "type": "a2ui",
                        "surfaceId": "turn-main",
                        "messages": _sample_messages(),
                    },
                ],
            },
        }
    ]
    messages = events_to_openai_messages(events, a2ui_summary=True)
    assert len(messages) == 1
    assert "a2ui_messages" not in messages[0]
    assert "[A2UI surface turn-main]" in messages[0]["content"]


def test_flat_render_input_to_messages_builds_v09_protocol():
    messages = flat_render_input_to_messages(
        {
            "surfaceId": "image-gallery",
            "components": [
                {"id": "root", "component": "Column", "children": ["title"]},
                {"id": "title", "component": "Text", "text": "Gallery"},
            ],
            "data": {"items": [{"title": "Photo 1"}]},
        }
    )
    assert messages is not None
    assert messages[0]["createSurface"]["surfaceId"] == "image-gallery"
    assert messages[0]["createSurface"]["catalogId"] == "basic"
    assert messages[1]["updateComponents"]["components"][0]["component"] == "Column"
    assert messages[2]["updateDataModel"]["path"] == "/"
    validate_a2ui_messages(normalize_a2ui_messages(messages))


def test_flat_render_input_parses_json_strings_and_aliases():
    import json

    messages = flat_render_input_to_messages(
        {
            "surfaceId": "gallery",
            "components": json.dumps(
                [
                    {"id": "gallery", "component": "Grid", "children": ["title"]},
                    {"id": "title", "component": "Heading", "text": "Tasks"},
                ]
            ),
            "data": json.dumps({"items": [{"title": "Photo 1"}]}),
        }
    )
    assert messages is not None
    components = messages[1]["updateComponents"]["components"]
    assert components[0]["id"] == "root"
    assert components[0]["component"] == "Column"
    assert components[1]["component"] == "Text"
    validate_a2ui_messages(normalize_a2ui_messages(messages))


def test_flat_render_input_normalizes_nested_component_objects():
    messages = flat_render_input_to_messages(
        {
            "surfaceId": "card",
            "components": [
                {
                    "id": "root",
                    "component": {"Column": {"children": ["heading"]}},
                },
                {"id": "heading", "component": {"Text": {"text": "Hello"}}},
            ],
        }
    )
    assert messages is not None
    components = messages[1]["updateComponents"]["components"]
    assert components[0]["component"] == "Column"
    assert components[1]["component"] == "Text"
    assert components[1]["text"] == "Hello"


def test_normalize_component_passthrough():
    assert normalize_component({"id": "root", "component": "Text", "text": "Hi"}) == {
        "id": "root",
        "component": "Text",
        "text": "Hi",
    }
