"""Dangerous command detection and approval callbacks."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any

ApprovalCallback = Callable[[str, dict[str, Any]], Awaitable[bool]]

DANGEROUS_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\brm\s+(-[^\s]*\s+)*-[^\s]*r", re.I),
    re.compile(r"\brm\s+-rf\b", re.I),
    re.compile(r"\bsudo\b", re.I),
    re.compile(r"\bchmod\s+777\b", re.I),
    re.compile(r"\bmkfs\b", re.I),
    re.compile(r"\bdd\s+if=", re.I),
    re.compile(r"\b>\s*/dev/", re.I),
    re.compile(r"\|\s*sh\b", re.I),
    re.compile(r"\bcurl\b.*\|\s*(ba)?sh", re.I),
]

DANGEROUS_WRITE_PATHS = re.compile(
    r"(^|/)(etc|usr|bin|sbin|boot|sys|proc|dev)(/|$)",
    re.I,
)


def is_dangerous_command(command: str) -> bool:
    """Return True if shell command matches dangerous patterns."""
    for pattern in DANGEROUS_PATTERNS:
        if pattern.search(command):
            return True
    return False


def is_dangerous_path(path: str) -> bool:
    """Return True if file path looks like a system path."""
    return bool(DANGEROUS_WRITE_PATHS.search(path))


async def check_tool_approval(
    tool_name: str,
    input_data: dict[str, Any],
    *,
    require_approval: bool = True,
    approval_callback: ApprovalCallback | None = None,
) -> tuple[bool, str | None]:
    """Check if tool execution needs approval and invoke callback if so."""
    if not require_approval:
        return True, None

    reason: str | None = None
    if tool_name in {"terminal_run", "run_command"}:
        command = input_data.get("command", "")
        if is_dangerous_command(str(command)):
            reason = f"Dangerous command pattern detected: {command[:80]}"
    elif tool_name in {"file_write", "file_patch"}:
        path = input_data.get("path", "")
        if is_dangerous_path(str(path)):
            reason = f"Dangerous write path: {path}"

    if reason is None:
        return True, None

    if approval_callback is None:
        return False, reason

    approved = await approval_callback(tool_name, input_data)
    if not approved:
        return False, f"Approval denied: {reason}"
    return True, None
