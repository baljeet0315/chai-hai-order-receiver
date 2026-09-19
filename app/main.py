"""FastAPI app: the WhatsApp webhook. Run with: uvicorn app.main:app --reload"""

from __future__ import annotations

import json
import logging
from functools import lru_cache

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app.config import settings
from app.service import OrderService
from app.whatsapp import WhatsAppClient, parse_webhook, verify_signature

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("chai")

app = FastAPI(title="Chai Hai order receiver")


@lru_cache
def get_service() -> OrderService:
    from app.parser import ClaudeParser

    if settings.supabase_url and settings.supabase_key:
        from app.store_supabase import SupabaseStore
        store = SupabaseStore()
    else:
        from app.store import MemoryStore
        log.warning("SUPABASE_URL not set: using in-memory store, data is lost on restart")
        store = MemoryStore()

    sheet = None
    if settings.google_service_account_json and settings.google_sheet_id:
        from app.sheets import GoogleSheet
        sheet = GoogleSheet()
    else:
        log.warning("Google Sheets not configured: approved orders stay in the database only")

    return OrderService(store, ClaudeParser(), WhatsAppClient(), sheet, owner_phone=settings.owner_phone,
                        confirm_template=(settings.wa_confirm_template, settings.wa_confirm_template_lang))


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/webhook")
def verify(mode: str = Query("", alias="hub.mode"), token: str = Query("", alias="hub.verify_token"),
           challenge: str = Query("", alias="hub.challenge")):
    """Meta calls this once when you save the webhook URL in the developer dashboard."""
    if mode == "subscribe" and token and token == settings.wa_verify_token:
        return PlainTextResponse(challenge)
    raise HTTPException(status_code=403, detail="verify token mismatch")


def process(payload: dict) -> None:
    service = get_service()
    for msg in parse_webhook(payload):
        try:
            service.handle(msg)
        except Exception:
            log.exception("failed to handle message %s", msg.wa_message_id)


@app.post("/webhook")
async def webhook(request: Request, background: BackgroundTasks):
    body = await request.body()
    if not verify_signature(settings.wa_app_secret, body, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(status_code=401, detail="bad signature")
    # Answer Meta immediately, do the slow work (Claude, Supabase, Sheets) afterwards.
    background.add_task(process, json.loads(body))
    return {"received": True}
