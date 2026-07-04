"""ShareGPT JSONL trajectory export."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def messages_to_sharegpt(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Convert OpenAI messages to ShareGPT conversation format."""
    conv: list[dict[str, str]] = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content") or ""
        if role == "user":
            conv.append({"from": "human", "value": str(content)})
        elif role == "assistant" and content:
            conv.append({"from": "gpt", "value": str(content)})
    return conv


def export_sharegpt_jsonl(messages: list[dict[str, Any]], path: Path) -> None:
    """Write ShareGPT JSONL to path."""
    entry = {"conversations": messages_to_sharegpt(messages)}
    with path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
