"""Per-turn consecutive tool failure guard with recovery guidance."""

from __future__ import annotations

from collections import defaultdict


def format_failure_guidance(
    tool_name: str,
    *,
    max_failures: int,
    language: str = "zh",
) -> str:
    """Internal LLM guidance when a tool hits the consecutive failure limit."""
    if language == "en":
        return (
            f"Tool '{tool_name}' has failed {max_failures} times in a row and is temporarily disabled. "
            "Summarize the situation for the user based on existing context, suggest alternatives if any, "
            "and do not call this tool again."
        )
    return (
        f"工具 {tool_name} 已连续失败 {max_failures} 次，已被暂时禁用。"
        "请根据已有上下文向用户总结说明情况与可行替代方案，不要再调用此工具。"
    )


def format_immediate_disable_guidance(
    tool_name: str,
    *,
    reason: str | None = None,
    language: str = "zh",
) -> str:
    """Guidance for tools that should be blocked immediately in the current run."""
    if language == "en":
        details = f" Reason: {reason}." if reason else ""
        return (
            f"Tool '{tool_name}' failed with a non-recoverable error and is disabled for this run."
            f"{details} Summarize the situation for the user, provide a text alternative if possible, "
            "and do not call this tool again in this run."
        )
    details = f" 原因：{reason}。" if reason else ""
    return (
        f"工具 {tool_name} 在当前轮次出现不可恢复错误，已立即禁用。"
        f"{details}请直接向用户总结情况并给出文本替代方案，本轮不要再调用此工具。"
    )


class ToolFailureGuard:
    """Tracks consecutive per-tool failures within a single user-message agent run."""

    def __init__(
        self,
        *,
        max_failures: int = 3,
        enabled: bool = True,
        language: str = "zh",
    ) -> None:
        if max_failures < 1:
            raise ValueError("max_failures must be >= 1")
        self.max_failures = max_failures
        self.enabled = enabled
        self.language = language
        self._streaks: dict[str, int] = defaultdict(int)
        self._handled: set[str] = set()

    def record(self, tool_name: str, *, success: bool) -> None:
        if not self.enabled:
            return
        if success:
            self._streaks[tool_name] = 0
        else:
            self._streaks[tool_name] += 1

    def mark_blocked(self, tool_name: str) -> None:
        """Record that recovery guidance was injected for this tool."""
        self._handled.add(tool_name)
        self._streaks[tool_name] = 0

    def failure_count(self, tool_name: str) -> int:
        return self._streaks.get(tool_name, 0)

    def exceeded(self) -> tuple[bool, str | None, str | None]:
        if not self.enabled:
            return False, None, None
        for tool_name, streak in self._streaks.items():
            if tool_name in self._handled:
                continue
            if streak >= self.max_failures:
                return (
                    True,
                    tool_name,
                    format_failure_guidance(
                        tool_name,
                        max_failures=self.max_failures,
                        language=self.language,
                    ),
                )
        return False, None, None
