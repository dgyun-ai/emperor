"""Notification center API."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from dashboard.notifications_store import add_notification, clear_notifications, list_notifications

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.get("")
async def get_notifications():
    return {"notifications": list_notifications()}


class NotificationPost(BaseModel):
    content: str = Field(min_length=1)
    source: str = "webui"
    metadata: dict | None = None


@router.post("")
async def post_notification(req: NotificationPost):
    item = add_notification(content=req.content, source=req.source, metadata=req.metadata)
    return {"notification": item}


@router.delete("")
async def delete_notifications():
    clear_notifications()
    return {"ok": True}
