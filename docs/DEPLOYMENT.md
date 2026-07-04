# emperor 部署与使用指南

本文档介绍 **emperor 0.1.0**（Phase 0–12 MVP）的安装、配置与运行，覆盖 Phase 2–12 全部子系统：工具、会话、Prompt/压缩、记忆/技能、MCP/插件/Hooks、委托、Terminal/Profile、扩展工具、网关、CLI REPL/API/ACP、Fallback 与故障排查。

## 前置条件

| 项目 | 要求 |
|------|------|
| Python | **3.11+** |
| 包管理 | `pip` 或 uv |
| API Key | OpenRouter / OpenAI 兼容服务 |
| 可选 | Docker（terminal docker 后端）、Telegram Bot Token（网关） |

```bash
python3 --version   # >= 3.11
```

## 安装

```bash
cd /path/to/emperor
pip install -e ".[dev]"
emperor --version    # emperor 0.1.0
pytest tests/ -v    # 验证安装
```

核心依赖：`openai`, `pydantic`, `httpx`, `rich`, `aiosqlite`, `fastapi`, `uvicorn`。

---

## 目录与 Profile 隔离（Phase 0 / Phase 8）

```
~/.emperor/
├── config.yaml           # 主配置
├── state.db              # SQLite 会话（WAL 模式）
├── memory_fts.db         # 跨会话记忆 FTS
├── MEMORY.md / USER.md   # 长期记忆（Phase 5）
├── cron_jobs.json        # 定时任务（Phase 9）
├── mcp_servers.yaml      # MCP 配置（Phase 6，可选）
├── plugins/              # 用户插件（Phase 6）
└── profiles/<name>/      # Profile 独立数据目录
    ├── config.yaml
    └── state.db
```

**Profile 隔离**：每个 profile 拥有独立的 `config.yaml` 与 `state.db`，互不影响。

```bash
emperor -p work chat
EMPEROR_PROFILE=work emperor session list
```

---

## 环境变量

| 变量 | 说明 |
|------|------|
| `EMPEROR_HOME` | 用户数据根目录（默认 `~/.emperor`） |
| `EMPEROR_PROFILE` | Profile 名称 |
| `OPENROUTER_API_KEY` / `OPENAI_API_KEY` | LLM API 密钥 |
| `TELEGRAM_BOT_TOKEN` | Telegram 网关 Bot Token |
| `EMPEROR_LOG_LEVEL` | 日志级别（DEBUG/INFO/WARNING） |

---

## config.yaml

项目内提供完整示例文件：[config.yaml.example](../config.yaml.example)

```bash
cp config.yaml.example ~/.emperor/config.yaml
# 编辑 provider / agent / tools 等项后：
emperor config show
```

以下为精简示例（完整字段与注释见 `config.yaml.example`）：

```yaml
provider:
  provider: openrouter
  model: anthropic/claude-sonnet-4
  base_url: https://openrouter.ai/api/v1

fallback_providers:
  - provider: openai
    model: gpt-4o
    api_key_env: OPENAI_API_KEY

agent:
  max_turns: 90
  max_context_tokens: 128000
  language: zh
  protect_last_n: 20
  compress_threshold: 0.5

ui:
  language: zh

tools:
  enabled_toolsets:
    - core
    - file
    - terminal
    - web
    - todo
    - agent
    - delegation
    - code
    - browser
    - cron
  disabled_toolsets: []
  require_approval: true

terminal:
  backend: local          # local | docker | ssh | modal
  docker_image: python:3.11-slim
  timeout_seconds: 120

compression:
  enabled: true
  threshold: 0.5
  protect_last_n: 20

memory:
  max_memory_chars: 50000
  max_user_chars: 10000

gateway:
  host: 0.0.0.0
  port: 8080
  telegram_token_env: TELEGRAM_BOT_TOKEN
  webhook_secret: change-me

api_server:
  host: 127.0.0.1
  port: 9118

delegation:
  max_iterations: 50

log_level: WARNING
```

---

## Phase 2：工具系统

### 架构

- **Registry**：`@register_tool` 装饰器，模块 import 时自动注册
- **Orchestrator**：连续只读工具并发执行，交互式工具串行
- **Approval**：危险命令（`rm -rf`、`sudo`、写 `/etc` 等）默认拒绝
- **Toolsets**：通过 `enabled_toolsets` / `disabled_toolsets` 白/黑名单过滤

### 已注册工具（16 个）

| Toolset | 工具 | 说明 |
|---------|------|------|
| `core` | `echo`, `clarify` | 测试/澄清 |
| `file` | `file_read`, `file_write`, `file_patch`, `file_search` | 文件读写/补丁/搜索 |
| `terminal` | `terminal_run` | 命令执行（local/docker） |
| `web` | `web_search`, `web_extract` | 网页搜索与提取（`web_search` 为 `ddgs` 优先，失败时回退 DuckDuckGo HTML） |
| `todo` | `todo` | 任务列表 |
| `agent` | `memory`, `session_search` | Agent 级记忆/会话检索 |
| `delegation` | `delegate_task` | 子 Agent 委托 |
| `code` | `execute_code` | Python 沙箱执行 |
| `browser` | `browser_fetch` | httpx 页面抓取 |
| `cron` | `cron` | 定时任务管理 |

### 验证工具注册

```bash
python -c "
from tools.registry import discover_tools, list_tools, list_toolsets
discover_tools()
print('tools:', sorted(t.name for t in list_tools()))
print('toolsets:', list_toolsets())
"
```

---

## Phase 3：会话持久化

### SQLite Schema

- `sessions` — 会话元数据（profile、platform、title、parent_session_id）
- `messages` — 消息本体（role、content、tool_calls、seq）
- `messages_fts` — FTS5 全文索引
- `compress_events` — 压缩 lineage 记录

### CLI 命令

```bash
emperor chat                          # 交互对话，自动持久化
emperor chat "在项目中搜索 TODO"       # 单轮对话
emperor session list                  # 列出会话
emperor session export <session-id> --jsonl > transcript.jsonl
```

### 交互 Slash 命令

| 命令 | 说明 |
|------|------|
| `/help` | 帮助 |
| `/resume` | 恢复最近会话 |
| `/search <词>` | FTS 搜索历史消息 |
| `/model` | 显示模型信息 |
| `/stop` | 提示使用 Ctrl+C 中断 |
| `exit` | 退出 |

### 端到端持久化流程

1. `QueryEngine.submit_message()` 调用 `SessionStore.initialize()`
2. 若无 `session_id`，创建新 session 并写入 `sessions` 表
3. 每条 user/assistant/tool 消息通过 `append_message()` 原子写入（WAL + 事务）
4. `/resume` 加载最近 session 的全部 messages 到内存
5. `emperor session export` 导出 JSONL 便于调试/训练

---

## Phase 4：Prompt / 上下文 / 压缩

### PromptBuilder 三层

| 层 | 内容 | 稳定性 |
|----|------|--------|
| stable | 基础 system prompt | 对话中不变 |
| context | 上下文文件、技能摘要、记忆摘要 | 会话级稳定 |
| volatile | 动态注入 | 按需更新 |

### 上下文文件

项目根或父目录自动加载：

- `.emperor.md`
- `AGENTS.md`
- `CLAUDE.md`
- `SOUL.md`

用户输入支持 `@path/to/file` 引用展开。

### 压缩

- 阈值默认 **50%**（`compression.threshold`）
- 压缩时保留最近 **20** 条消息（`protect_last_n`）
- 压缩事件写入 `compress_events` 表

---

## Phase 5：记忆与技能

### 记忆文件

| 文件 | 用途 |
|------|------|
| `~/.emperor/MEMORY.md` | 长期记忆（Agent `memory` 工具读写） |
| `~/.emperor/USER.md` | 用户偏好 |

### 技能

- `skills/**/SKILL.md` — 渐进披露加载
- Curator — 使用计数、staleness 检测、归档

### Agent 级工具

- `memory` — 读写 MEMORY.md / USER.md
- `session_search` — FTS 跨会话检索

---

## Phase 6：MCP + 插件 + Hooks

### MCP 配置

`~/.emperor/mcp_servers.yaml`：

```yaml
servers:
  - name: filesystem
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
```

MVP 行为：MCP 工具 schema 转为 `mcp_<server>_<tool>` 注册；完整 stdio 握手与实时调用为后续增强（当前 stub 返回 JSON 状态）。

### 插件

```
~/.emperor/plugins/my-plugin/
├── plugin.json    # {"name":"my-plugin","version":"1.0"}
└── main.py
```

项目级：`.emperor/plugins/`。PluginManager 三源发现（用户目录、项目目录、pip entry_points）。

### Hooks

| Hook | 时机 |
|------|------|
| `PreToolUse` | 工具执行前，返回 False 阻止 |
| `PostToolUse` | 工具执行后 |
| `Stop` | 对话结束 |
| `SessionStart` | 会话开始 |

QueryEngine 接受 `HookManager` 注入。

---

## Phase 7：委托与子 Agent

### delegate_task

```python
# Agent 调用 delegate_task 时：
# - 创建隔离 ToolContext（独立 task_id、depth+1）
# - 子 Agent 使用 core/file/web toolsets（禁用 delegation 防递归）
# - 独立 max_turns budget
```

配置：`delegation.max_iterations`（默认 50）。

### execute_code

Python 沙箱执行，stdout/stderr 捕获，异常返回 is_error。

---

## Phase 8：Terminal 多后端 + 安全

| backend | 说明 |
|---------|------|
| `local` | asyncio subprocess（默认） |
| `docker` | `docker run --rm -v $PWD:/work` |
| `ssh` | stub（返回未配置） |
| `modal` | stub（返回未配置） |

危险命令在 `require_approval: true` 时默认拒绝。Checkpoints 模块提供 shadow git 回滚骨架。

---

## Phase 9：扩展工具

### Cron 定时任务

Agent 通过 `cron` 工具增删任务，持久化到 `~/.emperor/cron_jobs.json`。

```python
from cron.scheduler import CronScheduler
sched = CronScheduler()
sched.add_job("every:3600", "check inbox")
```

### Batch 批量运行

`prompts.json`：

```json
{"prompts": ["总结 README", "列出 TODO"]}
```

```bash
emperor batch prompts.json
# 输出 NDJSON：{"prompt":"...","response":"...","error":null}
```

### Trajectory 导出

ShareGPT JSONL 格式（训练数据）：

```python
from trajectory.export import export_sharegpt_jsonl
export_sharegpt_jsonl(messages, Path("out.jsonl"))
```

---

## Phase 10：消息网关

### 启动

```bash
# Telegram long-polling
export TELEGRAM_BOT_TOKEN=123456:ABC...
export OPENROUTER_API_KEY=sk-or-...
emperor gateway start --telegram

# Webhook HTTP
emperor gateway start --webhook
```

### Telegram

- Long-polling 模式（httpx）
- 首次 DM 自动 pairing
- 消息路由键：`telegram:<chat_id>`
- 同一 chat 复用 session（SQLite 持久化）

### Webhook

默认监听 `0.0.0.0:8080`：

```bash
curl -X POST http://localhost:8080/webhook \
  -H "Content-Type: application/json" \
  -d '{"message":"你好","secret":"change-me"}'
```

返回 `{"reply":"..."}`。健康检查：`GET /health`。

### Session 路由

`SessionRouter` 将 platform_key 映射到 session_id，网关多轮对话共享同一 SQLite session。

---

## Phase 11：CLI REPL + ACP + API Server

### 交互式 CLI（Hermes hermes_cli 风格）

```bash
emperor          # 默认进入交互式对话
emperor chat     # 同上
emperor chat -q "你好"     # 单轮非交互
emperor chat -q "任务" -Q  # 脚本模式：仅 stdout 最终回复
```

参考 [Hermes hermes_cli](https://github.com/NousResearch/hermes-agent/tree/main/hermes_cli) 的交互模式：

- **prompt_toolkit** 输入：`❯` 提示符、历史记录（`~/.emperor/cli_history`）、`/` 命令 Tab 补全
- **底部固定输入区**：prompt_toolkit Application，输入框固定在终端底部（`ui.fixed_input: true`），**Alt+Enter** 或 **Ctrl+J** 发送
- **皮肤系统**：内置 `default` / `slate` / `mono` / `crimson`，`/skin` 切换；自定义皮肤放 `~/.emperor/skins/<name>.yaml`
- **欢迎 Banner**：模型、工具数、toolsets、会话 ID（窄终端自动紧凑模式）
- **Slash 命令注册表**（`cli/command_registry.py`）：`/help` `/new` `/clear` `/sessions` `/resume` `/search` `/status` `/usage` `/compress` `/verbose` `/statusbar` `/skin` `/model`
- **工具展示**：Claude Code 风格 `⏺`/`⎿`，可通过 `/verbose` 循环 off → normal → verbose
- **状态栏**：`/statusbar` 切换每轮底部的 ctx/session 摘要
- **patch_stdout**：流式输出与输入区不冲突

```yaml
ui:
  language: zh
  skin: default      # default | slate | mono | crimson
  fixed_input: true  # 底部固定输入区；false 回退简单 PromptSession
```

上下文上限：

```yaml
agent:
  max_context_tokens: 128000
```

自定义皮肤示例（`~/.emperor/skins/mine.yaml`）：

```yaml
name: mine
description: My custom theme
colors:
  banner_title: "#a78bfa"
  prompt: "#c4b5fd"
branding:
  prompt_symbol: ">"
```

### API Server

```bash
emperor api start
# 或
emperor api serve
emperor api serve --host 0.0.0.0 --port 9118
```

调用示例：

```bash
curl http://127.0.0.1:9118/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"你好"}]}'
```

健康检查：`GET /health`

### ACP Adapter

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize"}' | emperor acp
```

stdio JSON-RPC 骨架，支持 `initialize`、`chat/send`、`shutdown`。

---

## Phase 12：生产化

### Provider Fallback

配置 `fallback_providers` 后，主 provider 遇 **429/5xx** 自动尝试备用链。

### 日志

`EMPEROR_LOG_LEVEL` 或 `config.yaml` 中 `log_level`。

### 测试

```bash
pytest tests/ -v
```

---

## CLI 命令速查

| 命令 | 说明 |
|------|------|
| `emperor config show` | 显示有效配置 |
| `emperor` / `emperor chat` | Hermes 风格交互 REPL |
| `emperor chat -q "…"` | 单轮非交互 |
| `emperor chat -q "…" -Q` | 脚本模式（仅最终回复） |
| `emperor session list` | 列出会话 |
| `emperor session export <id> --jsonl` | 导出 JSONL |
| `emperor gateway start --telegram` | Telegram 网关 |
| `emperor gateway start --webhook` | Webhook 网关 |
| `emperor api start\|serve` | OpenAI 兼容 API |
| `emperor batch prompts.json` | 批量任务 |
| `emperor acp` | ACP stdio 适配器 |

---

## 架构概览

```
CLI / Gateway / API / Batch / ACP
         ↓
    QueryEngine（会话持久化 + 压缩 + PromptBuilder + Hooks）
         ↓
    AgentLoop（orchestrator 并发只读工具 + approval）
         ↓
    OpenAICompatProvider / FallbackProvider
         ↓
    ToolRegistry（toolsets 自动发现，含 delegation）
         ↓
    SessionStore（SQLite + FTS5 + WAL）
```

---

## 故障排查

### No API key configured

设置 `OPENROUTER_API_KEY` 或在 `config.yaml` 配置 `provider.api_key`。

### 会话无法 resume

1. 确认 `~/.emperor/state.db` 存在
2. `emperor session list` 查看 session id
3. 检查 Profile 是否一致（`-p` 参数）

### /search 无结果

FTS5 需要消息已写入 `messages_fts`；确认 session 有历史消息且查询词匹配。

### Telegram 无响应

1. 检查 `TELEGRAM_BOT_TOKEN` 环境变量
2. 确认网络可访问 `api.telegram.org`
3. 确认 Bot 已与用户建立对话（发送 `/start`）
4. 查看日志：`EMPEROR_LOG_LEVEL=DEBUG emperor gateway start --telegram`

### Webhook 返回 Unauthorized

请求 body 需包含 `"secret"` 字段，值与 `config.yaml` 中 `gateway.webhook_secret` 一致。

### Docker terminal 失败

1. 确认 Docker daemon 运行中
2. 镜像默认可拉取 `python:3.11-slim`
3. 检查 `terminal.docker_image` 配置

### 工具被 approval 拒绝

调整 `tools.require_approval: false`（不推荐生产）或避免危险命令模式（`rm -rf`、`sudo` 等）。

### delegate_task 报错 "requires agent_deps"

确保通过 QueryEngine/AgentLoop 调用（自动注入 `agent_deps`）；不要直接裸调工具。

### MCP 工具返回 stub

MVP 阶段 MCP 为 schema 转换 + stub 调用；完整 stdio 握手待后续版本。

### API serve 与 start

两者等价，`serve` 为 `start` 的别名。

---

## 与 Hermes 完整版差异

| 能力 | Hermes | emperor MVP |
|------|--------|------------|
| 工具数量 | 70+ / 28 toolsets | 16 工具 / 11 toolsets |
| MCP | 完整 stdio/SSE 握手 | schema 转换 + stub |
| 网关平台 | 20+ adapter | Telegram + Webhook |
| Terminal | ssh/modal/daytona 完整 | local/docker 可用 |
| CLI REPL | Ink 完整 | Hermes 风格 REPL（prompt_toolkit + slash 注册表） |
| Browser | 5 backends | httpx fetch |
| Vision/TTS/Kanban | 有 | 未实现 |
| 测试 | ~1250 文件 | 75 集成/单元测试 |
| API 模式 | 3 模式 | OpenAI compat 为主 |

完整路线图见 [ROADMAP.md](ROADMAP.md)。
