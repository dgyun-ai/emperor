"""Plugin discovery API."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from dashboard.context import get_workspace_root
from plugins.manager import PluginManager

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


def _manager() -> PluginManager:
    return PluginManager(project_dir=get_workspace_root().parent)


@router.get("")
async def list_plugins():
    plugins = _manager().discover()
    return {
        "plugins": [
            {"name": p.name, "version": p.version, "path": str(p.path)}
            for p in plugins
        ]
    }


class InstallRequest(BaseModel):
    name: str = Field(min_length=1)
    source: str | None = None


@router.post("/install")
async def install_plugin(req: InstallRequest):
    mgr = _manager()
    target = mgr.user_plugins / req.name
    target.mkdir(parents=True, exist_ok=True)
    manifest = target / "plugin.json"
    if not manifest.exists():
        manifest.write_text(
            f'{{"name": "{req.name}", "version": "0.1.0"}}',
            encoding="utf-8",
        )
    return {"ok": True, "name": req.name}


class UninstallRequest(BaseModel):
    name: str = Field(min_length=1)


@router.post("/uninstall")
async def uninstall_plugin(req: UninstallRequest):
    mgr = _manager()
    for base in [mgr.user_plugins, mgr.project_plugins]:
        target = base / req.name
        if target.is_dir():
            import shutil

            shutil.rmtree(target)
            return {"ok": True}
    raise HTTPException(404, "Plugin not found")
