"""LLM-generated session titles after the first conversation turn."""

from __future__ import annotations

import logging
import re

from agent.deps import AgentDeps

logger = logging.getLogger(__name__)

_MAX_TITLE_LEN_ZH = 15
_MAX_TITLE_LEN_EN = 30
_QUOTE_RE = re.compile(r'^["\'「『《（(\[]+|["\'」』》）)\]]+$')
_GARBAGE_TITLE_RE = re.compile(r"^p\d+$", re.I)
_PLACEHOLDER_TITLES = frozenset({"新会话", "New Session", "New Chat"})


def is_placeholder_title(title: str) -> bool:
    """Default titles shown before the first turn is summarized."""
    cleaned = " ".join(title.split()).strip()
    return cleaned in _PLACEHOLDER_TITLES


def max_title_len(language: str = "zh") -> int:
    """Return the max title length for the given UI language."""
    return _MAX_TITLE_LEN_EN if language == "en" else _MAX_TITLE_LEN_ZH


def truncate_title(text: str, *, language: str = "zh") -> str:
    """Truncate fallback titles to the configured length limit."""
    cleaned = " ".join(text.split()).strip()
    if not cleaned:
        return ""
    limit = max_title_len(language)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def build_title_prompt(
    message: str,
    *,
    language: str = "zh",
    assistant_reply: str | None = None,
) -> str:
    """Build a one-shot prompt for concise session title generation."""
    user_preview = " ".join(message.split()).strip()
    if len(user_preview) > 2000:
        user_preview = user_preview[:1999] + "…"
    assistant_preview = ""
    if assistant_reply:
        assistant_preview = " ".join(assistant_reply.split()).strip()
        if len(assistant_preview) > 2000:
            assistant_preview = assistant_preview[:1999] + "…"
    if language == "zh":
        body = f"用户：\n{user_preview}"
        if assistant_preview:
            body += f"\n\n助手：\n{assistant_preview}"
        return (
            "根据下面首轮对话，生成一个简短的会话标题。\n"
            f"要求：不超过{_MAX_TITLE_LEN_ZH}个字；只输出标题本身；不要引号；不要解释；不要标点结尾。\n\n"
            f"{body}"
        )
    body = f"User:\n{user_preview}"
    if assistant_preview:
        body += f"\n\nAssistant:\n{assistant_preview}"
    return (
        "From the first exchange below, write a short conversation title.\n"
        f"Rules: at most {_MAX_TITLE_LEN_EN} characters; title text only; "
        "no quotes; no explanation; no trailing punctuation.\n\n"
        f"{body}"
    )


def should_use_direct_title(message: str, *, language: str = "zh") -> bool:
    """Short first messages are used as-is — avoids reasoning-model garbage titles."""
    return len(" ".join(message.split()).strip()) <= max_title_len(language)


def is_garbage_title(title: str) -> bool:
    """Detect stored titles that should be regenerated (e.g. reasoning-model 'p2')."""
    cleaned = " ".join(title.split()).strip()
    if not cleaned:
        return True
    if _GARBAGE_TITLE_RE.fullmatch(cleaned):
        return True
    return False


def is_acceptable_title(title: str, message: str) -> bool:
    """Reject obvious non-titles from reasoning models (e.g. step-3.7-flash 'p2')."""
    if not title or is_garbage_title(title):
        return False
    if len(title) < 2:
        return False
    if len(title) <= 3 and title.isascii() and any("\u4e00" <= c <= "\u9fff" for c in message):
        return False
    return True


def extract_title_from_model_output(
    accumulated: str,
    final_text: str,
    *,
    message: str,
    language: str = "zh",
) -> str | None:
    """Pick the best acceptable title from streamed/final model output."""
    seen: set[str] = set()
    for raw in (final_text, accumulated):
        if not raw or not raw.strip():
            continue
        normalized = normalize_title(raw, language=language)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        if is_acceptable_title(normalized, message):
            return normalized
    return None


def normalize_title(raw: str, *, language: str = "zh") -> str:
    """Clean model output into a single-line session title."""
    text = " ".join(raw.split()).strip()
    if not text:
        return ""
    text = _QUOTE_RE.sub("", text).strip()
    text = text.strip("\"'`""''「」『』《》")
    return truncate_title(text, language=language)


async def generate_session_title(
    deps: AgentDeps,
    message: str,
    *,
    language: str = "zh",
    assistant_reply: str | None = None,
) -> str | None:
    """Call the model once to summarize the first conversation turn as a title."""
    if should_use_direct_title(message, language=language):
        direct = normalize_title(message, language=language)
        if direct and is_acceptable_title(direct, message):
            return direct

    prompt = build_title_prompt(
        message,
        language=language,
        assistant_reply=assistant_reply,
    )
    call_model = deps.get_call_model()
    accumulated = ""
    final_text = ""

    try:
        async for chunk in call_model(
            messages=[{"role": "user", "content": prompt}],
            tools=None,
            disable_thinking=True,
        ):
            if chunk.delta_text:
                accumulated += chunk.delta_text
            if chunk.is_final and chunk.assistant_message:
                content = chunk.assistant_message.get("content")
                if isinstance(content, str) and content.strip():
                    final_text = content
    except Exception:
        logger.warning("Session title LLM call failed", exc_info=True)
        return None

    title = extract_title_from_model_output(
        accumulated,
        final_text,
        message=message,
        language=language,
    )
    return title
