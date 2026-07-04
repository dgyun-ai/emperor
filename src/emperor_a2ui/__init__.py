"""Emperor A2UI protocol helpers (distinct from the a2ui-agent-sdk package)."""

from emperor_a2ui.normalize import (
    COPILOTKIT_BASIC_CATALOG_ID,
    normalize_a2ui_messages,
    normalize_catalog_id,
)
from emperor_a2ui.schema import build_a2ui_system_prompt
from emperor_a2ui.validate import extract_surface_ids, validate_a2ui_messages

__all__ = [
    "COPILOTKIT_BASIC_CATALOG_ID",
    "build_a2ui_system_prompt",
    "extract_surface_ids",
    "normalize_a2ui_messages",
    "normalize_catalog_id",
    "validate_a2ui_messages",
]
