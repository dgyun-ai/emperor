"""Query engine — single-session message submission with persistence."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from agent.deps import AgentDeps
from agent.loop import AgentLoop
from agent.types import AgentEvent, Terminal
from dashboard.session_meta import get_meta, set_meta
from config.models import EmperorConfig
from context.compressor import compress_messages, should_compress
from context.usage import (
    UsageTracker,
    build_usage_snapshot,
    estimate_context_tokens,
    restore_tracker_from_snapshot,
)
from hooks.lifecycle import HookManager
from memory.manager import MemoryManager
from prompt.builder import PromptBuilder
from prompt.context_files import parse_file_references
from emperor_a2ui.validate import extract_surface_ids
from session.convert import (
    bootstrap_session_events,
    build_user_event,
    events_to_openai_messages,
    normalize_message_history,
    openai_message_to_event,
    parent_for_next_event,
    _merge_consecutive_assistants,
)
from session.events import has_bootstrap
from session.store import SessionStore
from session.follow_up_questions import generate_follow_up_questions
from session.title import generate_session_title, is_garbage_title, is_placeholder_title, truncate_title
from skills.loader import discover_skills, skills_summary
from skills.recommender import recommend_skills_for_query
from tools.agent.memory_tool import configure_memory
from tools.agent.session_search import configure_session_store
from tools.base import Tool
from tools.registry import discover_tools, get_tools_for_toolsets
from tools.terminal.run import configure_terminal


class QueryEngine:
    """Engine entry point for submitting messages to the agent loop."""

    def __init__(
        self,
        *,
        deps: AgentDeps,
        config: EmperorConfig | None = None,
        tools: list[Tool] | None = None,
        system_prompt: str | None = None,
        max_turns: int | None = None,
        session_store: SessionStore | None = None,
        session_id: str | None = None,
        profile: str = "default",
        hooks: HookManager | None = None,
    ) -> None:
        self.deps = deps
        self.config = config or EmperorConfig()
        self.profile = profile
        self.hooks = hooks or HookManager()
        self.session_store = session_store or SessionStore.for_profile(profile)
        self.session_id = session_id
        self._initialized = False

        discover_tools()
        if tools is not None:
            self.tools = tools
        else:
            enabled = list(self.config.tools.enabled_toolsets)
            if os.environ.get("EMPEROR_KANBAN_TASK"):
                if "kanban" not in enabled:
                    enabled.append("kanban")
            self.tools = get_tools_for_toolsets(
                enabled=enabled,
                disabled=self.config.tools.disabled_toolsets,
            )
        if not self.config.dashboard.chat.a2ui_enabled:
            self.tools = [t for t in self.tools if t.name != "render_a2ui"]

        configure_terminal(
            backend=self.config.terminal.backend,
            docker_image=self.config.terminal.docker_image,
            timeout=self.config.terminal.timeout_seconds,
        )

        memory = MemoryManager(max_memory_chars=self.config.memory.max_memory_chars)
        configure_memory(memory)
        configure_session_store(self.session_store)

        self.prompt_builder = PromptBuilder(language=self.config.agent.language)
        self.prompt_builder.set_memory(memory.summary_for_prompt())
        self._project_dir = Path.cwd()
        self._all_skills = discover_skills(project_dir=self._project_dir)
        self.prompt_builder.set_skills(skills_summary(self._all_skills))

        self.system_prompt = system_prompt or self._compose_system_prompt()
        self._custom_system_prompt = system_prompt
        self.max_turns = max_turns or self.config.agent.max_turns
        self.max_context_tokens = self.config.agent.max_context_tokens
        self.usage_tracker = UsageTracker()
        self._events: list[dict[str, Any]] = []
        self._messages: list[dict[str, Any]] = []
        self._pending_a2ui_payloads: list[tuple[str, list[dict[str, Any]]]] = []
        self._pending_thinking = ""

    def _compose_system_prompt(self) -> str:
        base = self.prompt_builder.build()
        if not self.config.dashboard.chat.a2ui_enabled:
            return base
        from emperor_a2ui.schema import build_a2ui_system_prompt

        return f"{base}\n\n{build_a2ui_system_prompt(language=self.config.agent.language)}"

    async def initialize(self) -> None:
        if self._initialized:
            return
        await self.session_store.initialize()
        if self.session_id:
            await self._reload_session_history(self.session_id)
            await self.hooks.run_session_start(self.session_id)
        self._initialized = True

    async def _reload_session_history(self, session_id: str) -> None:
        self._events = await self.session_store.load_events(session_id)
        # Keep assistant text history for the model, but avoid replaying A2UI surface
        # summaries back into the prompt because they can encourage redundant rerenders.
        self._messages = normalize_message_history(
            events_to_openai_messages(self._events, strip_a2ui=True)
        )

    def _provider_info(self) -> tuple[str, str]:
        provider = self.config.provider.provider or "emperor"
        model = self.config.provider.model or "default"
        return provider, model

    async def _ensure_bootstrap(self, session_id: str) -> None:
        if has_bootstrap(self._events):
            return
        provider, model = self._provider_info()
        bootstrap = bootstrap_session_events(
            session_id=session_id,
            cwd=str(self._project_dir),
            provider=provider,
            model_id=model,
        )
        await self.session_store.append_events(session_id, bootstrap)
        self._events.extend(bootstrap)

    async def _ensure_session(self) -> str:
        """Create a DB session row on first message if needed."""
        await self.initialize()
        if not self.session_id:
            self.session_id = await self.session_store.create_session(profile=self.profile)
            await self.hooks.run_session_start(self.session_id)
        return self.session_id

    @property
    def messages(self) -> list[dict[str, Any]]:
        return list(self._messages)

    def current_usage_snapshot(self) -> dict[str, Any]:
        """Return usage/context snapshot for UI status bar."""
        context_tokens = estimate_context_tokens(self._messages, system_prompt=self.system_prompt)
        return build_usage_snapshot(
            self.usage_tracker,
            context_tokens=context_tokens,
            max_context_tokens=self.max_context_tokens,
        )

    async def submit_message(
        self,
        content: str,
        *,
        abort_event: asyncio.Event | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """Append user message and run agent loop."""
        session_id = await self._ensure_session()

        await self._ensure_bootstrap(session_id)

        expanded, _refs = parse_file_references(content)
        user_msg = {"role": "user", "content": expanded}
        user_event = build_user_event(
            expanded,
            parent_id=parent_for_next_event(self._events),
        )
        self._messages.append(user_msg)
        self._messages = normalize_message_history(self._messages)
        self._events.append(user_event)
        await self.session_store.append_event(session_id, user_event)
        self._refresh_system_prompt_for_query(expanded)

        compressed_this_turn = False
        if self.config.compression.enabled and should_compress(
            self._messages,
            threshold=self.config.compression.threshold,
            max_context_tokens=self.max_context_tokens,
        ):
            self._messages = compress_messages(
                self._messages,
                protect_last_n=self.config.compression.protect_last_n,
            )
            compressed_this_turn = True
            await self.session_store.record_compress_event(
                self.session_id,  # type: ignore[arg-type]
                child_session_id=None,
                summary="Auto-compressed conversation",
                protected_last_n=self.config.compression.protect_last_n,
            )
            context_tokens = estimate_context_tokens(
                self._messages,
                system_prompt=self.system_prompt,
            )
            yield AgentEvent(
                "usage_update",
                build_usage_snapshot(
                    self.usage_tracker,
                    context_tokens=context_tokens,
                    max_context_tokens=self.max_context_tokens,
                    compressed=True,
                ),
            )

        loop = AgentLoop(
            deps=self.deps,
            tools=self.tools,
            profile=self.profile,
            system_prompt=self.system_prompt,
            max_turns=self.max_turns,
            max_context_tokens=self.max_context_tokens,
            usage_tracker=self.usage_tracker,
            hooks=self.hooks,
            require_approval=self.config.tools.require_approval,
            max_consecutive_tool_failures=self.config.agent.max_consecutive_tool_failures,
            loop_guard_enabled=self.config.agent.loop_guard_enabled,
            language=self.config.agent.language,
        )
        streamed_assistant = ""
        pending_thinking = ""
        last_usage: dict[str, Any] | None = None
        title_session: str | None = None
        try:
            async for event in loop.run(messages=self._messages, abort_event=abort_event):
                if event.kind == "stream_delta":
                    streamed_assistant += event.payload
                elif event.kind == "thinking":
                    payload = event.payload if isinstance(event.payload, dict) else {}
                    text = payload.get("text", "")
                    if isinstance(text, str) and text:
                        pending_thinking += text
                elif event.kind == "message":
                    msg = self._coalesce_assistant_message(event.payload, streamed_assistant)
                    if pending_thinking and msg.get("role") == "assistant":
                        msg = dict(msg)
                        msg["_thinking"] = pending_thinking
                        pending_thinking = ""
                    coalesced_text = streamed_assistant
                    streamed_assistant = ""
                    if (
                        msg.get("role") == "assistant"
                        and self._messages
                        and self._messages[-1].get("role") == "assistant"
                    ):
                        self._messages[-1] = _merge_consecutive_assistants(self._messages[-1], msg)
                    else:
                        self._messages.append(msg)
                    await self._append_persisted_message(msg, streamed_text=coalesced_text)
                elif event.kind == "usage_update":
                    last_usage = event.payload
                elif event.kind == "a2ui":
                    payload = event.payload if isinstance(event.payload, dict) else {}
                    messages = payload.get("messages")
                    if isinstance(messages, list) and messages:
                        from emperor_a2ui.normalize import normalize_a2ui_messages

                        normalized = normalize_a2ui_messages(messages)
                        yield AgentEvent("a2ui", {"messages": normalized})
                        await self._persist_a2ui_messages(normalized)
                        continue
                elif event.kind == "status" and "terminal" in event.payload:
                    terminal = event.payload["terminal"]
                    reason = terminal.get("reason")
                    if reason == "complete":
                        assistant_text = terminal.get("message") or streamed_assistant
                        if pending_thinking:
                            self._pending_thinking = pending_thinking
                            pending_thinking = ""
                        await self._ensure_assistant_after_turn(assistant_text)
                        streamed_assistant = ""
                        if self.config.dashboard.chat.ask_user_questions:
                            questions = await generate_follow_up_questions(
                                self.deps,
                                expanded,
                                assistant_text,
                                language=self.config.agent.language,
                            )
                            set_meta(
                                self.profile,
                                session_id,
                                {"last_follow_up_questions": questions},
                            )
                            yield AgentEvent("ask_user_questions", {"questions": questions})
                        if not await self.session_store.session_has_title(session_id):
                            title_session = session_id
                if event.kind == "usage_update" and compressed_this_turn:
                    payload = dict(event.payload)
                    ctx = dict(payload.get("context") or {})
                    ctx["compressed"] = True
                    payload["context"] = ctx
                    yield AgentEvent("usage_update", payload)
                else:
                    yield event

                if title_session is not None:
                    sid = title_session
                    title_session = None
                    asyncio.create_task(
                        self._ensure_session_title(sid, use_llm=self.config.agent.auto_title)
                    )
        except Exception as exc:
            error_text = str(exc) or exc.__class__.__name__
            await self._ensure_failed_turn_has_assistant(error_text)
            yield AgentEvent(
                "status",
                {
                    "terminal": Terminal(
                        reason="error",
                        message=None,
                        error=error_text,
                    )
                },
            )

        await self._flush_pending_a2ui()
        self._persist_usage_snapshot(compressed=compressed_this_turn)

    def _persist_usage_snapshot(self, *, compressed: bool = False) -> None:
        if not self.session_id:
            return
        snap = self.current_usage_snapshot()
        if compressed:
            ctx = dict(snap.get("context") or {})
            ctx["compressed"] = True
            snap["context"] = ctx
        set_meta(self.profile, self.session_id, {"usage_snapshot": snap})

    def _apply_pending_a2ui(self, message: dict[str, Any]) -> dict[str, Any]:
        if message.get("role") != "assistant" or not self._pending_a2ui_payloads:
            return message
        merged = dict(message)
        for surface_id, a2ui_messages in self._pending_a2ui_payloads:
            existing = list(merged.get("a2ui_messages") or [])
            existing.extend(a2ui_messages)
            merged["a2ui_messages"] = existing
            merged["a2ui_surface_id"] = surface_id
        self._pending_a2ui_payloads.clear()
        return merged

    async def _flush_pending_a2ui(self) -> None:
        if not self._pending_a2ui_payloads or not self.session_id:
            return
        a2ui_only = self._apply_pending_a2ui({"role": "assistant", "content": None})
        if self._messages and self._messages[-1].get("role") == "assistant":
            merged = _merge_consecutive_assistants(self._messages[-1], a2ui_only)
            self._messages[-1] = merged
            for idx in range(len(self._events) - 1, -1, -1):
                evt = self._events[idx]
                if evt.get("type") == "message" and evt.get("message", {}).get("role") == "assistant":
                    updated = openai_message_to_event(
                        merged,
                        parent_id=evt.get("parentId"),
                        provider=self._provider_info()[0],
                        model=self._provider_info()[1],
                    )
                    updated["id"] = evt["id"]
                    updated["parentId"] = evt.get("parentId")
                    updated["timestamp"] = evt.get("timestamp")
                    self._events[idx] = updated
                    await self.session_store._update_event_payload(
                        self.session_id,  # type: ignore[arg-type]
                        str(evt["id"]),
                        updated,
                    )
                    break
            return
        self._messages.append(a2ui_only)
        await self._append_persisted_message(a2ui_only)

    async def _append_persisted_message(
        self,
        message: dict[str, Any],
        *,
        streamed_text: str = "",
        usage: dict[str, Any] | None = None,
        stop_reason: str = "stop",
    ) -> None:
        message = self._apply_pending_a2ui(message)
        provider, model = self._provider_info()
        event = openai_message_to_event(
            message,
            parent_id=parent_for_next_event(self._events),
            provider=provider,
            model=model,
            usage=usage,
            stop_reason=stop_reason,
            streamed_text=streamed_text,
        )
        self._events.append(event)
        await self.session_store.append_event(self.session_id, event)  # type: ignore[arg-type]

    async def _persist_a2ui_messages(self, messages: list[dict[str, Any]]) -> None:
        if not self.session_id:
            return
        from emperor_a2ui.normalize import normalize_a2ui_messages

        messages = normalize_a2ui_messages(messages)
        surface_ids = extract_surface_ids(messages)
        surface_id = surface_ids[0] if surface_ids else "main"
        self._pending_a2ui_payloads.append((surface_id, messages))

    def _coalesce_assistant_message(
        self,
        message: dict[str, Any],
        streamed_text: str,
    ) -> dict[str, Any]:
        if message.get("role") != "assistant":
            return message
        content = message.get("content")
        if (content is None or (isinstance(content, str) and not content.strip())) and streamed_text:
            merged = dict(message)
            merged["content"] = streamed_text
            return merged
        return message

    async def _ensure_assistant_after_turn(self, text: str) -> None:
        """Ensure the latest turn ends with an assistant message in history."""
        if not text or not text.strip():
            if self._pending_thinking:
                self._pending_thinking = ""
            return
        if not self._messages:
            assistant = self._apply_pending_a2ui({"role": "assistant", "content": text})
            if self._pending_thinking:
                assistant = dict(assistant)
                assistant["_thinking"] = self._pending_thinking
                self._pending_thinking = ""
            self._messages.append(assistant)
            await self._append_persisted_message(assistant, streamed_text=text)
            return

        last = self._messages[-1]
        if last.get("role") == "tool" or last.get("tool_calls"):
            assistant = self._apply_pending_a2ui({"role": "assistant", "content": text})
            if self._pending_thinking:
                assistant = dict(assistant)
                assistant["_thinking"] = self._pending_thinking
                self._pending_thinking = ""
            self._messages.append(assistant)
            await self._append_persisted_message(assistant, streamed_text=text)
            return

        if last.get("role") == "assistant":
            content = last.get("content")
            if content is None or (isinstance(content, str) and not content.strip()):
                updated = self._apply_pending_a2ui(dict(last))
                updated["content"] = text
                self._messages[-1] = updated
                await self.session_store.set_last_assistant_content(self.session_id, text)  # type: ignore[arg-type]
                if self._events:
                    for idx in range(len(self._events) - 1, -1, -1):
                        evt = self._events[idx]
                        if evt.get("type") == "message" and evt.get("message", {}).get("role") == "assistant":
                            self._events[idx] = openai_message_to_event(
                                updated,
                                parent_id=evt.get("parentId"),
                                provider=self._provider_info()[0],
                                model=self._provider_info()[1],
                                streamed_text=text,
                            )
                            await self.session_store._update_event_payload(
                                self.session_id,  # type: ignore[arg-type]
                                str(self._events[idx]["id"]),
                                self._events[idx],
                            )
                            break
            return

    async def _ensure_failed_turn_has_assistant(self, error_text: str) -> None:
        """Persist an assistant error message when a turn aborts before reply storage."""
        if not error_text.strip() or not self._messages:
            return
        last = self._messages[-1]
        if last.get("role") != "user":
            return
        assistant = {"role": "assistant", "content": error_text}
        self._messages.append(assistant)
        await self._append_persisted_message(assistant, streamed_text=error_text)

    async def chat(
        self,
        content: str,
        *,
        abort_event: asyncio.Event | None = None,
    ) -> str:
        """Thin wrapper returning final assistant text."""
        final_text = ""
        async for event in self.submit_message(content, abort_event=abort_event):
            if event.kind == "status" and "terminal" in event.payload:
                terminal: Terminal = event.payload["terminal"]
                if terminal["reason"] == "complete":
                    final_text = terminal.get("message") or ""
                elif terminal["reason"] == "aborted":
                    raise asyncio.CancelledError("Agent aborted")
                elif terminal["reason"] == "error":
                    raise RuntimeError(terminal.get("error") or "Agent error")
                elif terminal["reason"] == "max_iterations":
                    raise RuntimeError(terminal.get("error") or "Max iterations reached")
        return final_text

    def _refresh_system_prompt_for_query(self, query: str) -> None:
        if self._custom_system_prompt is not None:
            self.system_prompt = self._custom_system_prompt
            return
        selected_skills, result = recommend_skills_for_query(
            query,
            self._all_skills,
            host="emperor",
            limit=10,
        )
        skills_text = skills_summary(selected_skills)
        if result and result.get("context_summary_text"):
            skills_text = f"{result['context_summary_text']}\n\n## Skill Details\n{skills_text}"
        self.prompt_builder.set_skills(skills_text)
        self.system_prompt = self._compose_system_prompt()

    async def resume_session(self, session_id: str) -> None:
        await self.session_store.initialize()
        self.session_id = session_id
        await self._reload_session_history(session_id)
        stored = get_meta(self.profile, session_id).get("usage_snapshot")
        self.usage_tracker = restore_tracker_from_snapshot(stored)
        self._initialized = True
        await self.hooks.run_session_start(session_id)
        await self._ensure_session_title(session_id, use_llm=False)

    @property
    def events(self) -> list[dict[str, Any]]:
        return list(self._events)

    async def new_session(self, *, title: str | None = None) -> str:
        """Start a fresh session (Hermes /new)."""
        await self.session_store.initialize()
        self.session_id = await self.session_store.create_session(
            profile=self.profile,
            title=title,
        )
        self._events = []
        self._messages = []
        self._pending_a2ui_payloads = []
        self.usage_tracker = UsageTracker()
        self._initialized = True
        await self.hooks.run_session_start(self.session_id)
        return self.session_id

    async def compress_context(self, *, protect_last_n: int | None = None) -> str:
        """Manually compress in-memory context (Hermes /compress)."""
        await self.initialize()
        n = protect_last_n if protect_last_n is not None else self.config.compression.protect_last_n
        before = len(self._messages)
        if before <= n:
            return f"No compression needed ({before} messages, protect_last_n={n})"
        self._messages = compress_messages(self._messages, protect_last_n=n)
        summary = f"Compressed {before} → {len(self._messages)} messages (kept last {n})"
        await self.session_store.record_compress_event(
            self.session_id,  # type: ignore[arg-type]
            child_session_id=None,
            summary=summary,
            protected_last_n=n,
        )
        return summary

    async def _ensure_session_title(
        self,
        session_id: str,
        *,
        hint: str | None = None,
        use_llm: bool = True,
    ) -> None:
        """Fill sessions.title after the first turn (LLM summary or truncate)."""
        existing = await self.session_store.get_title(session_id)
        if existing and not is_garbage_title(existing) and not is_placeholder_title(existing):
            return
        replacing = bool(
            existing and (is_garbage_title(existing) or is_placeholder_title(existing))
        )
        source = (hint or "").strip() or await self.session_store.get_first_user_message_content(
            session_id
        )
        if not source:
            return
        language = self.config.agent.language
        assistant_reply = await self.session_store.get_first_assistant_message_content(session_id)
        if use_llm and self.config.agent.auto_title:
            title = await generate_session_title(
                self.deps,
                source,
                language=language,
                assistant_reply=assistant_reply,
            )
            if title:
                await self.session_store.set_title(session_id, title, force=replacing)
                return
        await self.session_store.set_title(
            session_id,
            truncate_title(source, language=language),
            force=replacing or not existing,
        )
