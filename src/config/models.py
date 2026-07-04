"""Pydantic models for config.yaml."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ProviderConfig(BaseModel):
    provider: str = "openrouter"
    model: str = "anthropic/claude-sonnet-4"
    base_url: str | None = None
    api_key: str | None = None
    api_key_env: str | None = None


class FallbackProviderConfig(BaseModel):
    provider: str
    model: str
    base_url: str | None = None
    api_key: str | None = None
    api_key_env: str | None = None


class AgentConfig(BaseModel):
    max_turns: int = Field(default=90, ge=1)
    max_consecutive_tool_failures: int = Field(
        default=3,
        ge=1,
        description="Max consecutive failures per tool before disabling it and prompting a summary",
    )
    loop_guard_enabled: bool = Field(default=True)
    protect_last_n: int = Field(default=20, ge=1)
    compress_threshold: float = Field(default=0.5, ge=0.1, le=1.0)
    max_context_tokens: int = Field(default=128_000, ge=1_000)
    language: str = Field(default="zh", description="Response language: zh or en")
    auto_title: bool = Field(
        default=True,
        description="LLM-generate session title after the first conversation turn",
    )


class UiConfig(BaseModel):
    language: str = Field(default="zh", description="CLI UI language: zh or en")
    skin: str = Field(default="default", description="CLI skin name (default, slate, mono, crimson, or user YAML)")
    fixed_input: bool = Field(default=True, description="Use bottom-fixed prompt_toolkit input area")
    continue_last_session: bool = Field(
        default=True,
        description="On startup, resume the most recent session with messages",
    )


class ToolConfig(BaseModel):
    enabled_toolsets: list[str] = Field(default_factory=lambda: ["core", "file", "terminal", "web", "todo"])
    disabled_toolsets: list[str] = Field(default_factory=list)
    require_approval: bool = True


class TerminalConfig(BaseModel):
    backend: str = "local"
    docker_image: str = "python:3.11-slim"
    timeout_seconds: int = 120


class CompressionConfig(BaseModel):
    enabled: bool = True
    threshold: float = 0.5
    protect_last_n: int = 20


class MemoryConfig(BaseModel):
    max_memory_chars: int = 50_000
    max_user_chars: int = 10_000


class GatewayConfig(BaseModel):
    enabled: bool = False
    host: str = "0.0.0.0"
    port: int = 8080
    telegram_token: str | None = None
    telegram_token_env: str = "TELEGRAM_BOT_TOKEN"
    webhook_secret: str | None = None
    wecom_enabled: bool = False
    wecom_corp_id: str | None = None
    wecom_agent_id: str | None = None
    wecom_secret: str | None = None
    wecom_token: str | None = None
    wecom_encoding_aes_key: str | None = None


class ApiServerConfig(BaseModel):
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 9118


class DelegationConfig(BaseModel):
    max_iterations: int = 50


class KanbanConfig(BaseModel):
    dispatch_in_gateway: bool = True
    dispatch_interval_seconds: int = Field(default=60, ge=1)
    failure_limit: int = Field(default=2, ge=1)
    dispatch_stale_timeout_seconds: int = Field(default=14400, ge=60)


class DashboardKanbanConfig(BaseModel):
    lane_by_profile: bool = True
    render_markdown: bool = True
    default_tenant: str = ""
    include_archived_by_default: bool = False


class DashboardChatConfig(BaseModel):
    default_toolsets: list[str] = Field(
        default_factory=lambda: ["core", "file", "terminal", "web", "todo", "kanban", "cron"]
    )
    persist_sessions: bool = True
    ask_user_questions: bool = Field(
        default=True,
        description="After each assistant reply, LLM may suggest up to 3 follow-up questions",
    )
    a2ui_enabled: bool = Field(
        default=False,
        description="Enable A2UI rich interactive UI via render_a2ui tool",
    )


class DashboardConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 9119
    kanban: DashboardKanbanConfig = Field(default_factory=DashboardKanbanConfig)
    chat: DashboardChatConfig = Field(default_factory=DashboardChatConfig)


class EmperorConfig(BaseModel):
    provider: ProviderConfig = Field(default_factory=ProviderConfig)
    fallback_providers: list[FallbackProviderConfig] = Field(default_factory=list)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    ui: UiConfig = Field(default_factory=UiConfig)
    tools: ToolConfig = Field(default_factory=ToolConfig)
    terminal: TerminalConfig = Field(default_factory=TerminalConfig)
    compression: CompressionConfig = Field(default_factory=CompressionConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    api_server: ApiServerConfig = Field(default_factory=ApiServerConfig)
    delegation: DelegationConfig = Field(default_factory=DelegationConfig)
    kanban: KanbanConfig = Field(default_factory=KanbanConfig)
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)
    log_level: str = "WARNING"
