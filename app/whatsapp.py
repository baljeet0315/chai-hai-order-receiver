"""WhatsApp Cloud API: read webhook payloads, verify signatures, send messages."""

from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass, field
from typing import Optional

import httpx

from app.config import settings

log = logging.getLogger(__name__)


@dataclass
class InboundMessage:
    wa_message_id: str
    from_phone: str            # digits only, with country code
    profile_name: str
    type: str                  # text | button | audio | image | ...
    text: str = ""             # body for text messages
    button_id: str = ""        # for button taps, e.g. "approve:12"
    context_id: str = ""       # id of the message this one quotes/replies to
    raw: dict = field(default_factory=dict)


def verify_signature(app_secret: str, body: bytes, header: Optional[str]) -> bool:
    """Meta signs every webhook with the app secret. Reject anything that does not match."""
    if not app_secret:
        return True  # not configured (local dev only)
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


def parse_webhook(payload: dict) -> list[InboundMessage]:
    """Pull customer messages out of a Meta webhook payload. Status updates are ignored."""
    out: list[InboundMessage] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            names = {c.get("wa_id"): c.get("profile", {}).get("name", "") for c in value.get("contacts", [])}
            for m in value.get("messages", []):
                msg = InboundMessage(
                    wa_message_id=m.get("id", ""),
                    from_phone=m.get("from", ""),
                    profile_name=names.get(m.get("from"), ""),
                    type=m.get("type", "unknown"),
                    context_id=(m.get("context") or {}).get("id", ""),
                    raw=m,
                )
                if msg.type == "text":
                    msg.text = m.get("text", {}).get("body", "")
                elif msg.type == "interactive":
                    reply = m.get("interactive", {}).get("button_reply", {})
                    msg.type = "button"
                    msg.button_id = reply.get("id", "")
                    msg.text = reply.get("title", "")
                elif msg.type == "button":  # taps on template quick-reply buttons
                    msg.button_id = m.get("button", {}).get("payload", "")
                    msg.text = m.get("button", {}).get("text", "")
                out.append(msg)
    return out


class WhatsAppClient:
    """Sends messages. Every method returns the WhatsApp id of the sent message ('' on failure)."""

    def __init__(self):
        self.url = f"https://graph.facebook.com/{settings.wa_api_version}/{settings.wa_phone_number_id}/messages"
        self.headers = {"Authorization": f"Bearer {settings.wa_token}"}

    def _post(self, payload: dict) -> str:
        payload = {"messaging_product": "whatsapp", **payload}
        try:
            r = httpx.post(self.url, headers=self.headers, json=payload, timeout=20)
            if r.status_code >= 400:
                log.error("WhatsApp send failed %s: %s", r.status_code, r.text)
                return ""
            return r.json().get("messages", [{}])[0].get("id", "")
        except httpx.HTTPError as exc:
            log.error("WhatsApp send error: %s", exc)
            return ""

    def send_text(self, to: str, body: str, reply_to: str = "") -> str:
        payload = {"to": to, "type": "text", "text": {"body": body[:4096]}}
        if reply_to:
            payload["context"] = {"message_id": reply_to}
        return self._post(payload)

    def send_buttons(self, to: str, body: str, buttons: list[tuple[str, str]]) -> str:
        """buttons = [(id, title)], max 3, title max 20 chars."""
        return self._post({
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body[:1024]},
                "action": {"buttons": [{"type": "reply", "reply": {"id": i, "title": t[:20]}} for i, t in buttons]},
            },
        })

    def send_template(self, to: str, name: str, lang: str, body_params: list[str]) -> str:
        return self._post({
            "to": to,
            "type": "template",
            "template": {
                "name": name,
                "language": {"code": lang},
                "components": [{"type": "body", "parameters": [{"type": "text", "text": p} for p in body_params]}],
            },
        })
