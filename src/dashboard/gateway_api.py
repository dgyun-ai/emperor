"""Gateway health, channel config, and WeCom binding APIs."""

from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from config.loader import load_config, save_config
from dashboard.context import get_request_config, get_request_profile, get_request_store
from dashboard.status_state import build_gateway_health_payload
from gateway.bindings import GatewayBindingStore
from gateway.platforms.wecom import WeComAdapter

router = APIRouter(prefix="/api", tags=["gateway"])


def _binding_store(profile: str) -> GatewayBindingStore:
    from constants import get_emperor_home

    return GatewayBindingStore(home=get_emperor_home(profile))

@router.get("/gateway-health")
async def gateway_health(request: Request):
    config = get_request_config(request)
    profile = get_request_profile(request)
    return build_gateway_health_payload(profile, config)


@router.post("/gateway-restart")
async def gateway_restart():
    return {"ok": True, "message": "Gateway restart requested (restart start.sh gateway process manually)"}


@router.get("/gateway/channels")
async def list_channels(request: Request):
    profile = get_request_profile(request)
    config = get_request_config(request)
    health = build_gateway_health_payload(profile, config)
    callback_base = f"http://{config.dashboard.host}:{config.dashboard.port}"
    return {
        "channels": [
            {
                "id": "wecom",
                "name": "Enterprise WeCom",
                "enabled": health["wecom_enabled"],
                "configured": health["wecom_configured"],
                "callback_url": f"{callback_base}/api/gateway/wecom/callback",
            }
        ],
        "profile": profile,
    }


class WeComBindingCreate(BaseModel):
    external_key: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    enabled: bool = True


class WeComBindingUpdate(BaseModel):
    external_key: str | None = None
    session_id: str | None = None
    enabled: bool | None = None


@router.get("/gateway/wecom/bindings")
async def list_wecom_bindings(request: Request):
    profile = get_request_profile(request)
    store = _binding_store(profile)
    return {"bindings": [binding.to_dict() for binding in store.list_bindings(platform="wecom")]}


@router.post("/gateway/wecom/bindings")
async def create_wecom_binding(request: Request, req: WeComBindingCreate):
    profile = get_request_profile(request)
    sessions = get_request_store(request)
    await sessions.initialize()
    if await sessions.get_session(req.session_id) is None:
        raise HTTPException(400, f"Session not found: {req.session_id}")
    store = _binding_store(profile)
    binding = store.add_binding(
        platform="wecom",
        external_key=req.external_key,
        session_id=req.session_id,
        enabled=req.enabled,
    )
    return {"binding": binding.to_dict()}


@router.patch("/gateway/wecom/bindings/{binding_id}")
async def update_wecom_binding(request: Request, binding_id: str, req: WeComBindingUpdate):
    profile = get_request_profile(request)
    if req.session_id is not None:
        sessions = get_request_store(request)
        await sessions.initialize()
        if await sessions.get_session(req.session_id) is None:
            raise HTTPException(400, f"Session not found: {req.session_id}")
    store = _binding_store(profile)
    binding = store.update_binding(
        binding_id,
        external_key=req.external_key,
        session_id=req.session_id,
        enabled=req.enabled,
    )
    if binding is None:
        raise HTTPException(404, "Binding not found")
    return {"binding": binding.to_dict()}


@router.delete("/gateway/wecom/bindings/{binding_id}")
async def delete_wecom_binding(request: Request, binding_id: str):
    profile = get_request_profile(request)
    store = _binding_store(profile)
    if store.delete_binding(binding_id):
        return {"ok": True}
    raise HTTPException(404, "Binding not found")


class WeComGatewaySettings(BaseModel):
    enabled: bool = False
    corp_id: str | None = None
    agent_id: str | None = None
    secret: str | None = None
    token: str | None = None
    encoding_aes_key: str | None = None


@router.put("/gateway/wecom/settings")
async def update_wecom_settings(request: Request, req: WeComGatewaySettings):
    profile = get_request_profile(request)
    from constants import get_emperor_home

    home = get_emperor_home(profile)
    config = load_config(home=home, profile=profile)
    config.gateway.wecom_enabled = req.enabled
    config.gateway.wecom_corp_id = req.corp_id
    config.gateway.wecom_agent_id = req.agent_id
    config.gateway.wecom_secret = req.secret
    config.gateway.wecom_token = req.token
    config.gateway.wecom_encoding_aes_key = req.encoding_aes_key
    save_config(config, home)
    return {"ok": True}


@router.get("/gateway/wecom/callback")
async def verify_wecom_callback(
    request: Request,
    msg_signature: str = Query(default=""),
    timestamp: str = Query(default=""),
    nonce: str = Query(default=""),
    echostr: str = Query(default=""),
):
    profile = get_request_profile(request)
    config = get_request_config(request)
    if not config.gateway.wecom_token:
        raise HTTPException(400, "WeCom token not configured")
    adapter = WeComAdapter(
        token=config.gateway.wecom_token,
        corp_id=config.gateway.wecom_corp_id or "",
        agent_id=config.gateway.wecom_agent_id or "0",
        secret=config.gateway.wecom_secret or "",
        binding_store=_binding_store(profile),
    )
    if not adapter.verify_callback(
        msg_signature=msg_signature,
        timestamp=timestamp,
        nonce=nonce,
        echostr=echostr,
    ):
        raise HTTPException(401, "Invalid signature")
    return Response(content=echostr, media_type="text/plain")


@router.post("/gateway/wecom/callback")
async def handle_wecom_callback(
    request: Request,
    msg_signature: str = Query(default=""),
    timestamp: str = Query(default=""),
    nonce: str = Query(default=""),
):
    profile = get_request_profile(request)
    config = get_request_config(request)
    if not build_gateway_health_payload(profile, config)["wecom_configured"]:
        raise HTTPException(400, "WeCom not configured")
    body = await request.body()
    adapter = WeComAdapter(
        token=config.gateway.wecom_token or "",
        corp_id=config.gateway.wecom_corp_id or "",
        agent_id=config.gateway.wecom_agent_id or "0",
        secret=config.gateway.wecom_secret or "",
        binding_store=_binding_store(profile),
    )
    expected_signature = hashlib.sha1("".join(sorted([config.gateway.wecom_token or "", timestamp, nonce, body.decode("utf-8")])).encode("utf-8")).hexdigest()
    if msg_signature and msg_signature != expected_signature:
        raise HTTPException(401, "Invalid signature")
    from dashboard.chat_api import _build_engine
    from gateway.runner import GatewayRunner

    def factory(_key: str):
        return _build_engine(profile=profile, config=config)

    runner = GatewayRunner(engine_factory=factory)
    adapter.attach(runner)
    result = await adapter.handle_callback(body)
    if result.get("error"):
        raise HTTPException(400, result["error"])
    return result
