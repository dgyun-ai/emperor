"""LLM-generated follow-up questions after an assistant reply."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from agent.deps import AgentDeps

logger = logging.getLogger(__name__)

_MAX_QUESTIONS = 3
# Short JSON payload; cap output so lightweight calls finish quickly.
_FOLLOW_UP_MAX_TOKENS = 512
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
# Assistant-to-user phrasing — not valid as a clickable user message.
_ASSISTANT_PERSPECTIVE_RE = re.compile(
    r"^\s*("
    r"您是否|您想|您有没有|您是否计划|请问您|你想|你有没有|"
    r"Would you|Do you plan|Do you want|Are you planning|Could you tell me if you"
    r")",
    re.IGNORECASE,
)


def looks_like_assistant_perspective(question: str) -> bool:
    """True when the question reads like the assistant asking the user."""
    return bool(_ASSISTANT_PERSPECTIVE_RE.match(question.strip()))


def build_follow_up_prompt(
    user_message: str,
    assistant_reply: str,
    *,
    language: str = "zh",
) -> str:
    user_preview = " ".join(user_message.split()).strip()
    if len(user_preview) > 2000:
        user_preview = user_preview[:1999] + "…"
    assistant_preview = " ".join(assistant_reply.split()).strip()
    if len(assistant_preview) > 4000:
        assistant_preview = assistant_preview[:3999] + "…"

    if language == "zh":
        return (
            "根据下面的对话，判断是否需要向用户推荐后续追问。\n"
            "规则：\n"
            f"- 最多 {_MAX_QUESTIONS} 条\n"
            "- **用户视角**：每条都是用户下一轮会直接发给助手的话，向助手提问或请求帮助\n"
            "- 可用「我」「帮我」「推荐」「还有…吗」等用户常用表达\n"
            "- **禁止回答者视角**：不要反问用户，不要用「您是否…」「您想…」「请问您…」等句式\n"
            "- 错误示例：「您是否计划参观主题乐园？」\n"
            "- 正确示例：「除了世界之窗，深圳还有哪些主题乐园值得去？」\n"
            "- 与当前话题相关、有延伸价值\n"
            "- 若回复已完整结束、无需延伸，或只是错误/拒绝，返回空数组\n"
            '- 只输出 JSON，格式：{"questions": ["...", "..."]} 或 {"questions": []}\n'
            "- 不要 markdown，不要解释\n\n"
            f"用户：\n{user_preview}\n\n"
            f"助手：\n{assistant_preview}"
        )

    return (
        "Based on the exchange below, decide whether to suggest follow-up questions.\n"
        "Rules:\n"
        f"- At most {_MAX_QUESTIONS} questions\n"
        "- **User perspective**: each line is what the user would type next to ask the assistant\n"
        "- Use natural user phrasing (I, help me, recommend, what else, etc.)\n"
        "- **Not assistant perspective**: do not ask the user back; avoid "
        '"Would you like...", "Do you plan to...", "Are you interested in..."\n'
        "- Bad: \"Would you like theme park recommendations?\"\n"
        "- Good: \"Besides Window of the World, what theme parks in Shenzhen are worth visiting?\"\n"
        "- Relevant and useful for continuing the conversation\n"
        "- Return an empty array if no follow-ups are needed\n"
        '- Output JSON only: {"questions": ["...", "..."]} or {"questions": []}\n'
        "- No markdown, no explanation\n\n"
        f"User:\n{user_preview}\n\n"
        f"Assistant:\n{assistant_preview}"
    )


def parse_follow_up_questions(raw: str) -> list[str]:
    """Parse model output into at most 3 non-empty question strings."""
    text = raw.strip()
    if not text:
        return []

    match = _JSON_BLOCK_RE.search(text)
    if match:
        text = match.group(1).strip()

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                payload = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                logger.warning("Failed to parse follow-up questions JSON")
                return []
        else:
            return []

    if not isinstance(payload, dict):
        return []

    questions_raw = payload.get("questions")
    if not isinstance(questions_raw, list):
        return []

    questions: list[str] = []
    for item in questions_raw:
        if not isinstance(item, str):
            continue
        cleaned = " ".join(item.split()).strip()
        if cleaned and cleaned not in questions and not looks_like_assistant_perspective(cleaned):
            questions.append(cleaned)
        if len(questions) >= _MAX_QUESTIONS:
            break
    return questions


async def generate_follow_up_questions(
    deps: AgentDeps,
    user_message: str,
    assistant_reply: str,
    *,
    language: str = "zh",
) -> list[str]:
    """Call the model once to suggest 0-3 follow-up questions."""
    user_message = (user_message or "").strip()
    assistant_reply = (assistant_reply or "").strip()
    if not user_message or not assistant_reply:
        return []

    prompt = build_follow_up_prompt(user_message, assistant_reply, language=language)
    call_model = deps.get_call_model()
    accumulated = ""
    final_text = ""

    try:
        async for chunk in call_model(
            messages=[{"role": "user", "content": prompt}],
            tools=None,
            disable_thinking=True,
            max_tokens=_FOLLOW_UP_MAX_TOKENS,
        ):
            if chunk.delta_text:
                accumulated += chunk.delta_text
            if chunk.is_final and chunk.assistant_message:
                content = chunk.assistant_message.get("content")
                if isinstance(content, str) and content.strip():
                    final_text = content
    except Exception:
        logger.warning("Follow-up questions LLM call failed", exc_info=True)
        return []

    combined = final_text.strip() or accumulated.strip()
    return parse_follow_up_questions(combined)
