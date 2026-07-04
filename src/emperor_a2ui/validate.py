"""Validate A2UI v0.9 server-to-client messages."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.catalog import A2uiCatalog
from a2ui.schema.constants import VERSION_0_9
from a2ui.schema.manager import A2uiSchemaManager


class A2uiValidationError(ValueError):
    """Raised when A2UI messages fail schema validation."""


@lru_cache(maxsize=1)
def _basic_catalog() -> A2uiCatalog:
    manager = A2uiSchemaManager(
        version=VERSION_0_9,
        catalogs=[BasicCatalog.get_config(version=VERSION_0_9)],
    )
    if not manager._supported_catalogs:
        raise RuntimeError("A2UI basic catalog failed to load")
    return manager._supported_catalogs[0]


def validate_a2ui_messages(messages: list[dict[str, Any]]) -> None:
    """Validate a list of A2UI v0.9 messages against the bundled schema."""
    if not messages:
        raise A2uiValidationError("messages must be a non-empty array")
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            raise A2uiValidationError(f"message[{index}] must be an object")
    try:
        _basic_catalog().validator.validate(messages, strict_integrity=False)
    except ValueError as exc:
        raise A2uiValidationError(str(exc)) from exc


def extract_surface_ids(messages: list[dict[str, Any]]) -> list[str]:
    """Return surface IDs referenced in createSurface messages."""
    ids: list[str] = []
    for message in messages:
        create = message.get("createSurface")
        if isinstance(create, dict):
            surface_id = create.get("surfaceId")
            if isinstance(surface_id, str) and surface_id.strip():
                ids.append(surface_id.strip())
    return ids
