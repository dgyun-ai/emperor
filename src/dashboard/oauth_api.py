"""OAuth provider stubs for settings UI."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/oauth", tags=["oauth"])


@router.get("/providers")
async def oauth_providers():
    return {
        "providers": [
            {
                "id": "openrouter",
                "name": "OpenRouter",
                "configured": False,
                "method": "api_key",
            },
            {
                "id": "openai",
                "name": "OpenAI",
                "configured": False,
                "method": "api_key",
            },
        ]
    }


class OAuthLoginRequest(BaseModel):
    provider: str = Field(min_length=1)


@router.post("/login")
async def oauth_login(req: OAuthLoginRequest):
    return {
        "ok": False,
        "job_id": None,
        "message": f"OAuth for {req.provider} not configured; use API key in Provider settings",
    }


@router.get("/job/{job_id}")
async def oauth_job(job_id: str):
    return {"status": "pending", "job_id": job_id}


class OAuthCodeRequest(BaseModel):
    provider: str
    code: str


@router.post("/code")
async def oauth_code(req: OAuthCodeRequest):
    return {"ok": False, "message": "Device code flow not implemented"}
