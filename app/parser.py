"""Turns one WhatsApp text into a validated ParsedMessage using Claude.

Structured output is forced through a tool call, then validated by Pydantic.
One retry on invalid output; after that the caller forwards the raw text to the owner.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from pydantic import ValidationError

from app.catalog import CATALOG, MAX_PACKS_SANITY_LIMIT
from app.config import settings
from app.schema import ParsedMessage

log = logging.getLogger(__name__)


class ParseError(Exception):
    """The model did not return a usable result."""


TOOL = {
    "name": "record_message",
    "description": "Record the structured interpretation of the customer's WhatsApp message.",
    "input_schema": {
        "type": "object",
        "properties": {
            "intent": {"type": "string", "enum": ["order", "follow_up", "cancel", "same_as_last", "non_order"]},
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "product_id": {"type": ["string", "null"], "description": "One of the catalog product ids, or null if the flavour is unclear."},
                        "packs": {"type": ["integer", "null"], "description": "Number of packs, or null if unclear."},
                        "raw_text": {"type": "string", "description": "The customer's exact words for this line."},
                        "confidence": {"type": "number"},
                        "action": {"type": "string", "enum": ["add", "set", "remove"]},
                    },
                    "required": ["product_id", "packs", "raw_text", "confidence", "action"],
                },
            },
            "language": {"type": "string", "enum": ["en", "pa-Guru", "pa-Latn", "mixed"]},
            "notes": {"type": "string", "description": "Anything the owner should see, in English. Empty if nothing."},
        },
        "required": ["intent", "items", "language", "notes"],
    },
}


def build_system_prompt(catalog: dict[str, list[str]]) -> str:
    lines = [f'- "{pid}": {", ".join(aliases)}' for pid, aliases in catalog.items()]
    return f"""You read WhatsApp messages sent by shopkeepers to Chai Hai, a tea distributor, and extract orders.

Messages are in English, Punjabi in Gurmukhi script, Punjabi in Roman letters, or a mix. Expect spelling mistakes, no punctuation and numbers written as words (ik/ikk/ek=1, do=2, tin/tinn=3, char=4, panj=5, che/chhe=6, sat/satt=7, ath/atth=8, nau=9, das=10, and Gurmukhi equivalents).

CATALOG (product_id: names customers use). These are the ONLY products:
{chr(10).join(lines)}

The only unit is packs. Words like pack, packs, packet, pkt, dabba, dabbe, ਪੈਕ, ਡੱਬੇ all mean packs. A bare number next to a flavour means packs.

INTENT
- order: the message orders products and there is no pending order.
- follow_up: there IS a pending order (given below) and the message adds to it or changes it.
- cancel: the customer wants to cancel their order (cancel, cancel kardo, rehn do, nahi chahida, ਕੈਂਸਲ ...).
- same_as_last: the customer asks for their usual / same as last time (same as last time, pehle wala, ohi order, ਪਹਿਲਾਂ ਵਾਲਾ ...). Return no items.
- non_order: anything else: greetings, payment, delivery questions, complaints, thanks.

ITEMS
- One item per flavour mentioned.
- action: "add" for ordering or adding more; "set" when the customer states a new exact quantity for a flavour ("make masala 5", "3 di jagah 5"); "remove" when they drop a flavour.
- For intent "order", every action is "add".

HARD RULES
- Never guess a flavour. If the message says only "chai", "tea", "patti", or gives a quantity with no flavour, or names something not in the catalog, set product_id to null.
- Never invent a quantity. If no quantity is given for a flavour, set packs to null.
- Match misspellings and phonetic variants to the catalog when the intended flavour is clear (e.g. "elachi", "ilachi", "adrk", "msala", "karrak", "cofee").
- "kadak masala" or similar phrases that could be two flavours: product_id null, explain in notes.
- If packs for a line is above {MAX_PACKS_SANITY_LIMIT}, still return it but mention it in notes.
- confidence is 0 to 1 for that line.
- raw_text is copied from the message, not translated.

Always answer by calling the record_message tool."""


def build_user_prompt(text: str, pending_items: Optional[list[dict]], is_correction: bool = False) -> str:
    if pending_items:
        pending = json.dumps(pending_items, ensure_ascii=False)
        context = f"This customer HAS a pending order awaiting review: {pending}"
    else:
        context = "This customer has NO pending order."
    if is_correction:
        context += (
            "\nThe message below is a CORRECTION written by the business owner about that pending order, "
            "not by the customer. Use intent follow_up. Quantities the owner states are exact: use action "
            '"set" (or "remove"). The owner may name the flavour for a line that was unknown.'
        )
    return f"{context}\n\nCustomer message:\n<message>\n{text}\n</message>"


def _sanitize(data: dict) -> dict:
    """A product the model made up becomes 'unknown' (flagged to the owner) instead of an error."""
    data = dict(data)
    items = []
    for item in data.get("items") or []:
        item = dict(item)
        if item.get("product_id") is not None and item["product_id"] not in CATALOG:
            data["notes"] = (data.get("notes", "") + f" Model returned unknown product '{item['product_id']}'.").strip()
            item["product_id"] = None
        if isinstance(item.get("packs"), int) and item["packs"] <= 0:
            item["packs"] = None
        items.append(item)
    data["items"] = items
    return data


class ClaudeParser:
    def __init__(self, client=None, model: Optional[str] = None):
        if client is None:
            import anthropic

            headers = {"anthropic-workspace-id": settings.anthropic_workspace_id} if settings.anthropic_workspace_id else None
            client = anthropic.Anthropic(api_key=settings.anthropic_api_key, default_headers=headers)
        self.client = client
        self.model = model or settings.anthropic_model

    def parse(
        self,
        text: str,
        pending_items: Optional[list[dict]] = None,
        catalog: Optional[dict[str, list[str]]] = None,
        is_correction: bool = False,
    ) -> ParsedMessage:
        system = build_system_prompt(catalog or CATALOG)
        user = build_user_prompt(text, pending_items, is_correction)
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=1024,
                    system=system,
                    tools=[TOOL],
                    tool_choice={"type": "tool", "name": "record_message"},
                    messages=[{"role": "user", "content": user}],
                )
                data = next(b.input for b in response.content if b.type == "tool_use")
                return ParsedMessage.model_validate(_sanitize(data))
            except (ValidationError, StopIteration) as exc:
                last_error = exc
                log.warning("parser attempt %s returned invalid output: %s", attempt + 1, exc)
        raise ParseError(str(last_error))
