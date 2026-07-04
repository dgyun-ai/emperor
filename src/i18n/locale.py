"""Locale strings and response language instructions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CliStrings:
    chat_banner: str
    welcome_hint: str
    you_prompt: str
    input_placeholder: str
    input_hint: str
    thinking_spinner: str
    phase_connecting: str
    tool_running: str
    tool_no_output: str
    usage_line: str
    error_prefix: str
    stopped_prefix: str
    wait_turn: str
    model_line: str
    clarify_prefix: str
    unknown_command: str
    cli_only_command: str
    new_session: str
    compressed: str
    verbose_off: str
    verbose_normal: str
    verbose_verbose: str
    statusbar_on: str
    statusbar_off: str
    skin_switched: str
    no_sessions: str
    resumed_session: str
    search_usage: str
    no_results: str
    stop_hint: str
    sessions_header: str
    sessions_pick_prompt: str
    sessions_resume_hint: str
    session_untitled: str
    session_empty_label: str
    session_message_count: str
    provider_label: str
    model_label: str
    base_url_label: str
    max_context_label: str
    config_via_yaml: str


_CLI_ZH = CliStrings(
    chat_banner="输入 /help 查看命令，exit 退出",
    welcome_hint="欢迎！输入消息或 /help 查看命令。",
    you_prompt="❯ ",
    input_placeholder="输入消息…（/help 查看命令）",
    input_hint="Enter 发送 · 输入 / 显示命令列表",
    thinking_spinner="思考中…",
    phase_connecting="连接模型并等待响应…",
    tool_running="执行 {name}…",
    tool_no_output="(无输出)",
    usage_line=(
        "上下文 {used:,}/{max_tokens:,} ({percent}%) | "
        "本轮 输入/输出 {turn_in:,}/{turn_out:,} | "
        "会话累计 {session_total:,} tokens"
    ),
    error_prefix="错误：",
    stopped_prefix="已停止：",
    wait_turn="请等待当前轮次完成…",
    model_line="模型：{model}",
    clarify_prefix="澄清：",
    unknown_command="未知命令，输入 /help 查看可用命令",
    cli_only_command="此命令仅在交互式 CLI 中可用",
    new_session="已开始新会话 {session_id}…",
    compressed="已压缩：{summary}",
    verbose_off="工具显示：关闭（仅 Spinner）",
    verbose_normal="工具显示：标准（⏺/⎿ 预览）",
    verbose_verbose="工具显示：详细（完整参数与输出）",
    statusbar_on="状态栏：开启（每轮底部显示 ctx/session）",
    statusbar_off="状态栏：关闭（仅显示 usage 摘要）",
    skin_switched="已切换皮肤：{name}",
    no_sessions="没有可恢复的会话",
    resumed_session="已恢复会话 {session_id}…",
    search_usage="用法：/search <关键词>",
    no_results="无匹配结果",
    stop_hint="使用 Ctrl+C 中止当前轮次",
    sessions_header="最近会话（输入编号或 ID 前缀恢复）：",
    sessions_pick_prompt="选择会话> ",
    sessions_resume_hint="使用 /resume [id] 恢复指定会话",
    session_untitled="(无标题)",
    session_empty_label="空会话",
    session_message_count="{count}条",
    provider_label="提供商",
    model_label="模型",
    base_url_label="接口地址",
    max_context_label="上下文上限",
    config_via_yaml="请在 config.yaml 中配置模型",
)

_CLI_EN = CliStrings(
    chat_banner="Type /help for commands, exit to quit",
    welcome_hint="Welcome! Type a message or /help for commands.",
    you_prompt="❯ ",
    input_placeholder="Message… (/help for commands)",
    input_hint="Enter to send · type / for command list",
    thinking_spinner="Thinking…",
    phase_connecting="Connecting to model…",
    tool_running="Running {name}…",
    tool_no_output="(no output)",
    usage_line=(
        "Context {used:,}/{max_tokens:,} ({percent}%) | "
        "Turn in/out {turn_in:,}/{turn_out:,} | "
        "Session {session_total:,} tokens"
    ),
    error_prefix="Error: ",
    stopped_prefix="Stopped: ",
    wait_turn="Wait for the current turn to finish…",
    model_line="Model: {model}",
    clarify_prefix="Clarify: ",
    unknown_command="Unknown command — type /help",
    cli_only_command="This command is only available in interactive CLI",
    new_session="New session {session_id}…",
    compressed="Compressed: {summary}",
    verbose_off="Tool display: off (spinner only)",
    verbose_normal="Tool display: normal (⏺/⎿ preview)",
    verbose_verbose="Tool display: verbose (full args/output)",
    statusbar_on="Status bar: on",
    statusbar_off="Status bar: off",
    skin_switched="Skin switched to: {name}",
    no_sessions="No sessions to resume",
    resumed_session="Resumed session {session_id}…",
    search_usage="Usage: /search <query>",
    no_results="No results",
    stop_hint="Use Ctrl+C to abort",
    sessions_header="Recent sessions (enter number or ID prefix):",
    sessions_pick_prompt="Pick session> ",
    sessions_resume_hint="Use /resume [id] to resume a session",
    session_untitled="(untitled)",
    session_empty_label="empty",
    session_message_count="{count} msgs",
    provider_label="provider",
    model_label="model",
    base_url_label="base_url",
    max_context_label="max_context_tokens",
    config_via_yaml="Model configured via config.yaml",
)


def normalize_locale(locale: str | None) -> str:
    if not locale:
        return "zh"
    lower = locale.lower()
    if lower.startswith("zh"):
        return "zh"
    return "en"


def get_cli_strings(locale: str | None = None) -> CliStrings:
    return _CLI_ZH if normalize_locale(locale) == "zh" else _CLI_EN


def get_base_agent_instructions(locale: str | None = None) -> str:
    if normalize_locale(locale) == "zh":
        return (
            "你是 emperor，一个自主编程与任务执行助手。"
            "你擅长阅读代码、运行命令、修改文件并清晰说明每一步在做什么。"
        )
    return "You are emperor, a helpful autonomous coding and task agent."


def get_response_language_instructions(locale: str | None = None) -> str:
    if normalize_locale(locale) == "zh":
        return (
            "## 语言要求（必须遵守）\n"
            "- 你必须始终使用**简体中文**回复用户的说明性文字、总结、步骤与提问。\n"
            "- 代码、命令、文件路径、API 名称、错误栈等技术内容可保留英文。\n"
            "- 除非用户明确要求使用其他语言，不要使用英语或日语书写回复正文。\n"
            "- 向用户提问（包括 clarify 工具）时也必须使用简体中文。"
        )
    return (
        "## Language\n"
        "- Respond in English unless the user requests another language.\n"
    )


def format_usage_line(strings: CliStrings, snapshot: dict) -> str:
    ctx = snapshot.get("context", {})
    turn = snapshot.get("turn", {})
    session = snapshot.get("session", {})
    return strings.usage_line.format(
        used=ctx.get("used_tokens", 0),
        max_tokens=ctx.get("max_tokens", 0),
        percent=ctx.get("percent", 0),
        turn_in=turn.get("prompt_tokens", 0),
        turn_out=turn.get("completion_tokens", 0),
        session_total=session.get("total_tokens", 0),
    )
