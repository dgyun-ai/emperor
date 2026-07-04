"""Emperor dashboard FastAPI application."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from config.loader import load_config
from config.models import EmperorConfig
from constants import ENV_EMPEROR_PROFILE
from dashboard.a2ui_api import router as a2ui_router
from dashboard.ag_ui_api import router as ag_ui_router
from dashboard.app_api import router as dashboard_router
from dashboard.automation_api import configure_automation_api, router as automation_router
from dashboard.chat_api import configure_chat_api, router as chat_router
from dashboard.config_api import configure_config_api, router as config_router
from dashboard.gateway_api import router as gateway_router
from dashboard.notifications_api import router as notifications_router
from dashboard.oauth_api import router as oauth_router
from dashboard.plugins_api import router as plugins_router
from dashboard.agents_api import router as agents_router
from dashboard.mcp_api import router as mcp_router
from dashboard.shiba_compat_api import router as shiba_compat_router
from dashboard.skills_api import router as skills_router
from tools.cron_tool import get_scheduler
from dashboard.state import load_dashboard_state, verify_token
from kanban.api import configure_kanban_api, router as kanban_router
from kanban.db import KanbanDB
from kanban.dispatcher import KanbanDispatcher

_dispatcher_task: asyncio.Task[Any] | None = None


def _static_dir() -> Path:
    return Path(__file__).resolve().parent / "static"


def create_dashboard_app(
    config: EmperorConfig,
    *,
    profile: str | None = None,
    dispatcher_tick=None,
    start_dispatcher_loop: bool = False,
) -> FastAPI:
    db = KanbanDB.for_profile(profile)
    dispatcher = KanbanDispatcher(db, config, profile=profile)
    tick_fn = dispatcher_tick or dispatcher.tick

    configure_kanban_api(db, config, dispatcher_tick=tick_fn)
    configure_chat_api(config, profile=profile)
    configure_config_api(profile=profile)
    configure_automation_api(profile=profile)
    scheduler = get_scheduler(profile)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        global _dispatcher_task
        await db.initialize()
        await scheduler.start()
        if start_dispatcher_loop and config.kanban.dispatch_in_gateway:
            _dispatcher_task = asyncio.create_task(dispatcher.run_loop())
        yield
        dispatcher.stop()
        await scheduler.stop()
        if _dispatcher_task:
            _dispatcher_task.cancel()

    app = FastAPI(title="emperor dashboard", version="0.1.0", lifespan=lifespan)
    app.state.base_config = config
    app.state.default_profile = profile or "default"

    public_api_paths = {
        "/health",
        "/api/dashboard/bootstrap/status",
        "/api/dashboard/bootstrap",
        "/api/dashboard/auth/login",
        "/api/auth/status",
    }

    @app.middleware("http")
    async def dashboard_auth(request, call_next):
        path = request.url.path
        response = await call_next(request)
        if path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.middleware("http")
    async def dashboard_auth_guard(request, call_next):
        path = request.url.path
        if request.method == "OPTIONS" or not path.startswith("/api"):
            return await call_next(request)
        if path in public_api_paths:
            return await call_next(request)

        state = load_dashboard_state()
        if not state.initialized:
            return JSONResponse(
                {"detail": "Dashboard not initialized"},
                status_code=401,
            )
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return JSONResponse({"detail": "Missing bearer token"}, status_code=401)
        token = auth[7:]
        if not verify_token(token, state=state):
            return JSONResponse({"detail": "Invalid token"}, status_code=401)
        return await call_next(request)

    app.include_router(dashboard_router)
    app.include_router(kanban_router)
    app.include_router(chat_router)
    app.include_router(a2ui_router)
    app.include_router(ag_ui_router)
    app.include_router(config_router)
    app.include_router(shiba_compat_router)
    app.include_router(gateway_router)
    app.include_router(agents_router)
    app.include_router(mcp_router)
    app.include_router(skills_router)
    app.include_router(plugins_router)
    app.include_router(oauth_router)
    app.include_router(automation_router)
    app.include_router(notifications_router)

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "dashboard"}

    static = _static_dir()
    if static.is_dir():
        a2ui_spec = static / "a2ui"
        if a2ui_spec.is_dir():
            app.mount("/a2ui", StaticFiles(directory=a2ui_spec), name="a2ui-spec")

        app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")
        logo_candidates = (
            static / "emperor_logo.webp",
            static / "shibaclaw_logo.webp",
        )
        logo = next((path for path in logo_candidates if path.is_file()), None)
        minister_logo = static / "minister_logo.webp"
        if logo is not None:
            logo_headers = {"Cache-Control": "no-cache, must-revalidate"}

            @app.get("/emperor_logo.webp")
            async def emperor_logo_file():
                return FileResponse(logo, headers=logo_headers)

            @app.get("/shibaclaw_logo.webp")
            async def legacy_logo_file():
                return FileResponse(logo, headers=logo_headers)

        if minister_logo.is_file():
            minister_headers = {"Cache-Control": "no-cache, must-revalidate"}

            @app.get("/minister_logo.webp")
            async def minister_logo_file():
                return FileResponse(minister_logo, headers=minister_headers)


        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str):
            if full_path == "api" or full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not Found")
            index = static / "index.html"
            if index.is_file():
                return FileResponse(
                    index,
                    headers={"Cache-Control": "no-cache"},
                )
            return {
                "message": "Dashboard UI not built. Run: cd dashboard && npm install && npm run build"
            }

    return app


def create_dev_dashboard_app() -> FastAPI:
    """Factory for uvicorn --factory --reload local development."""
    profile = os.environ.get(ENV_EMPEROR_PROFILE)
    config = load_config(profile=profile)
    return create_dashboard_app(
        config,
        profile=profile,
        start_dispatcher_loop=True,
    )
