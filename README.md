# emperor

Python autonomous agent with OpenAI-compatible LLM providers — Hermes-inspired architecture with Claude Code-style AgentLoop.

## Features (Phases 0–12 MVP)

- **Agent core**: async generator loop, QueryEngine, AgentDeps DI, iteration budget
- **Tools**: file (read/write/patch/search), terminal (local/docker), web, todo, clarify, browser, cron, code exec, delegation, memory, session_search
- **Toolsets**: registry with auto-discovery, enabled/disabled toolsets, concurrent read-only orchestration, approval for dangerous commands
- **Sessions**: SQLite + FTS5, `/resume`, `/search`, `emperor session list|export --jsonl`
- **Prompt**: stable/context/volatile tiers, `.emperor.md` / AGENTS.md / CLAUDE.md / SOUL.md, @file references
- **Compression**: 50% threshold, protect_last_n=20
- **Memory & Skills**: MEMORY.md / USER.md, FTS recall, SKILL.md loader, curator
- **MCP & Plugins**: stdio MCP client stub, plugin discovery, Pre/Post/Stop hooks
- **Gateway**: Telegram long-poll + webhook adapter, session routing
- **API**: OpenAI-compatible `/v1/chat/completions` (FastAPI)
- **Kanban**: SQLite 任务看板、`emperor kanban` CLI、`kanban_*` worker 工具、内嵌 dispatcher
- **Dashboard**: React Web UI（Kanban 六列看板 + SSE Chat + 模型配置），`emperor dashboard start`
- **CLI**: Hermes-style REPL (`emperor` / `emperor chat`) with prompt_toolkit autocomplete, slash commands, banner
- **Fallback**: provider chain on 429/5xx

## Quick start

```bash
cd emperor
pip install -e ".[dev]"

# 复制配置示例并编辑 API Key / 模型
cp config.yaml.example ~/.emperor/config.yaml

export OPENROUTER_API_KEY=sk-or-...
emperor config show
emperor              # 交互式对话（默认）
emperor chat -q "你好"   # 单轮非交互
emperor chat -q "你好" -Q  # 仅输出最终回复（脚本模式）

# Kanban + Dashboard
emperor kanban init
emperor kanban create "Design auth schema" --assignee backend-dev --tenant auth-project
cd dashboard && npm install && npm run build && cd ..
emperor dashboard start   # http://127.0.0.1:9119
```

完整配置项说明见项目根目录 [`config.yaml.example`](config.yaml.example) 与 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)。

## Tests

```bash
pytest tests/ -v   # 133 tests
```

## Docs

- [DEPLOYMENT.md](docs/DEPLOYMENT.md) — 安装、配置、网关、API、MCP、会话
