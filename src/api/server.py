"""OpenAI-compatible API server."""

from __future__ import annotations

import time
import uuid
import os

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent.deps import AgentDeps
from config.loader import load_config
from constants import ENV_EMPEROR_PROFILE
from dashboard.sse import agent_events_to_sse
from engine.query_engine import QueryEngine
from provider.runtime import build_provider


class ChatMessage(BaseModel):
    role: str
    content: str | None = None


class ChatCompletionRequest(BaseModel):
    model: str = "emperor"
    messages: list[ChatMessage]
    stream: bool = False


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionChoice]


def create_api_app(engine_factory) -> FastAPI:
    app = FastAPI(title="emperor API", version="0.1.0")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post("/v1/chat/completions")
    async def chat_completions(req: ChatCompletionRequest):
        engine = engine_factory()
        last_user = next((m.content for m in reversed(req.messages) if m.role == "user"), "")
        if not last_user:
            return {"error": "No user message"}

        if req.stream:

            async def stream():
                async for chunk in agent_events_to_sse(
                    engine.submit_message(last_user or ""),
                    model=req.model,
                ):
                    yield chunk

            return StreamingResponse(stream(), media_type="text/event-stream")

        text = await engine.chat(last_user)
        return ChatCompletionResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:12]}",
            created=int(time.time()),
            model=req.model,
            choices=[
                ChatCompletionChoice(message=ChatMessage(role="assistant", content=text))
            ],
        )

    return app


def create_dev_api_app() -> FastAPI:
    """Factory for uvicorn --factory --reload local development."""
    profile = os.environ.get(ENV_EMPEROR_PROFILE)
    config = load_config(profile=profile)

    def factory():
        provider = build_provider(config)
        return QueryEngine(
            deps=AgentDeps.from_provider(provider),  # type: ignore[arg-type]
            config=config,
            profile=profile or "default",
        )

    return create_api_app(factory)
