"""Enterprise WeCom webhook adapter."""

from __future__ import annotations

import hashlib
import logging
import time
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING

from gateway.bindings import GatewayBindingStore

if TYPE_CHECKING:
    from gateway.runner import GatewayRunner

logger = logging.getLogger(__name__)


def _xml_text(root: ET.Element, tag: str) -> str:
    node = root.find(tag)
    return (node.text or "").strip() if node is not None and node.text else ""


class WeComAdapter:
    """Plaintext WeCom callback adapter with profile-scoped bindings."""

    def __init__(
        self,
        *,
        token: str,
        corp_id: str,
        agent_id: str,
        secret: str,
        binding_store: GatewayBindingStore,
    ) -> None:
        self.token = token
        self.corp_id = corp_id
        self.agent_id = agent_id
        self.secret = secret
        self.binding_store = binding_store
        self._runner: GatewayRunner | None = None
        self._access_token: str | None = None
        self._access_token_expiry = 0.0

    def attach(self, runner: "GatewayRunner") -> None:
        self._runner = runner

    def verify_callback(self, *, msg_signature: str, timestamp: str, nonce: str, echostr: str) -> bool:
        payload = "".join(sorted([self.token, timestamp, nonce, echostr]))
        signature = hashlib.sha1(payload.encode("utf-8")).hexdigest()
        return signature == msg_signature

    def _build_external_key(self, xml_root: ET.Element) -> str:
        from_user = _xml_text(xml_root, "FromUserName")
        return from_user or _xml_text(xml_root, "ChatId") or "unknown"

    async def _get_access_token(self) -> str:
        if self._access_token and time.time() < self._access_token_expiry:
            return self._access_token
        import httpx

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
                params={"corpid": self.corp_id, "corpsecret": self.secret},
            )
            data = resp.json()
        self._access_token = str(data.get("access_token") or "")
        expires_in = int(data.get("expires_in") or 7200)
        self._access_token_expiry = time.time() + max(60, expires_in - 60)
        if not self._access_token:
            raise RuntimeError(str(data.get("errmsg") or "Failed to get WeCom access token"))
        return self._access_token

    async def _send_text(self, user_id: str, text: str) -> None:
        import httpx

        token = await self._get_access_token()
        body = {
            "touser": user_id,
            "msgtype": "text",
            "agentid": int(self.agent_id),
            "text": {"content": text[:2048]},
            "safe": 0,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            await client.post(
                "https://qyapi.weixin.qq.com/cgi-bin/message/send",
                params={"access_token": token},
                json=body,
            )

    async def handle_callback(self, body: bytes) -> dict[str, str]:
        if self._runner is None:
            return {"error": "Gateway not initialized"}
        xml_root = ET.fromstring(body.decode("utf-8"))
        if _xml_text(xml_root, "MsgType") != "text":
            return {"ok": "ignored"}
        external_key = self._build_external_key(xml_root)
        binding = self.binding_store.get_by_external_key("wecom", external_key)
        if binding is None:
            return {"error": "Unbound WeCom source"}
        content = _xml_text(xml_root, "Content")
        if not content:
            return {"error": "No text content"}
        reply = await self._runner.handle_message(
            f"wecom:{binding.binding_id}",
            content,
            session_id=binding.session_id,
        )
        try:
            await self._send_text(_xml_text(xml_root, "FromUserName"), reply)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to send WeCom reply")
        return {"ok": "success"}
