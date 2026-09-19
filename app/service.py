"""The order logic: what happens for every inbound WhatsApp message.

OrderService is given its collaborators (store, parser, messenger, sheet), so tests
can pass fakes and production passes the real Supabase / Claude / WhatsApp / Sheets objects.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

from app.catalog import MAX_PACKS_SANITY_LIMIT
from app.parser import ParseError
from app.schema import OrderItem
from app.store import now
from app.whatsapp import InboundMessage

log = logging.getLogger(__name__)

TEXT_ONLY_REPLY = "Please send your order as a text message. / ਕਿਰਪਾ ਕਰਕੇ ਆਪਣਾ ਆਰਡਰ ਲਿਖ ਕੇ ਭੇਜੋ।"
SERVICE_WINDOW = timedelta(hours=23, minutes=30)  # WhatsApp allows free-form replies for 24h


def display_name(product_id: Optional[str]) -> str:
    return product_id.capitalize() if product_id else "UNKNOWN FLAVOUR"


def merge_items(existing: list[dict], changes: list[OrderItem]) -> list[dict]:
    """Apply add / set / remove lines to the items of a pending order."""
    items = [dict(i) for i in existing]
    for ch in changes:
        match = next((i for i in items if ch.product_id and i["product_id"] == ch.product_id), None)
        if ch.action == "remove":
            if match:
                items.remove(match)
            continue
        if match and ch.action == "set":
            match["packs"] = ch.packs
        elif match and ch.action == "add" and match["packs"] is not None and ch.packs is not None:
            match["packs"] += ch.packs
        elif match:
            match["packs"] = ch.packs if ch.packs is not None else match["packs"]
        else:
            items.append(to_item(ch))
    return items


def to_item(item: OrderItem) -> dict:
    return {"product_id": item.product_id, "packs": item.packs, "raw_text": item.raw_text,
            "confidence": item.confidence}


def needs_attention(item: dict) -> bool:
    return item["product_id"] is None or item["packs"] is None


def summary(items: list[dict]) -> str:
    return ", ".join(f'{i["packs"]} {display_name(i["product_id"])}' for i in items)


class OrderService:
    def __init__(self, store, parser, messenger, sheet=None, owner_phone: str = "", confirm_template=("order_confirmed", "en")):
        self.store = store
        self.parser = parser
        self.wa = messenger
        self.sheet = sheet
        self.owner = owner_phone
        self.confirm_template = confirm_template

    # ------------------------------------------------------------------ entry point
    def handle(self, msg: InboundMessage) -> None:
        customer = self.store.get_or_create_customer(msg.from_phone, msg.profile_name)
        message_id = self.store.log_message(msg.wa_message_id, customer["id"], "in", msg.type,
                                            msg.text or msg.button_id, msg.raw)
        if message_id is None:
            log.info("duplicate delivery of %s ignored", msg.wa_message_id)
            return

        if msg.from_phone == self.owner and self._handle_owner(msg, message_id):
            return

        if msg.type != "text":
            if msg.type != "button":
                self._send(msg.from_phone, TEXT_ONLY_REPLY, customer["id"])
            return

        self._handle_customer_text(msg, customer, message_id)

    # ------------------------------------------------------------------ customer side
    def _handle_customer_text(self, msg: InboundMessage, customer: dict, message_id: int) -> None:
        pending = self.store.get_pending_order(customer["id"])
        try:
            parsed = self.parser.parse(msg.text, pending["items"] if pending else None, self.store.get_catalog())
        except ParseError as exc:
            self._notify_owner(f"⚠ Could not parse a message from {self._who(customer)}:\n\"{msg.text}\"\n({exc})")
            return
        except Exception:
            log.exception("parser crashed")
            self._notify_owner(f"⚠ Parser error. Message from {self._who(customer)}:\n\"{msg.text}\"")
            return

        self.store.set_customer_language(customer["id"], parsed.language)

        if parsed.intent == "cancel" and pending:
            self.store.set_status(pending["id"], "cancelled")
            self.store.add_event(pending["id"], "cancelled", message_id, before=pending["items"])
            self._notify_owner(f"✖ Order #{pending['id']} from {self._who(customer)} was CANCELLED by the customer.\n\"{msg.text}\"")
            return

        if parsed.intent == "same_as_last" and not pending:
            last = self.store.last_approved_order(customer["id"])
            if last:
                order = self.store.create_order(customer["id"], last["items"], parsed.language, msg.text)
                self.store.add_event(order["id"], "created_same_as_last", message_id, after=order["items"])
                self._send_approval(order, customer, note=f"Copied from last approved order #{last['id']}. Please check.")
                return
            self._forward_non_order(msg, customer, extra="Asked for 'same as last time' but has no approved order yet.")
            return

        if parsed.items and parsed.intent in ("order", "follow_up", "same_as_last"):
            if pending:
                before = pending["items"]
                after = merge_items(before, parsed.items)
                self.store.replace_items(pending["id"], after, appended_text=msg.text)
                self.store.add_event(pending["id"], "merged", message_id, before=before, after=after)
                order = self.store.get_order(pending["id"])
                self._send_approval(order, customer, note=("UPDATED by customer follow-up. " + parsed.notes).strip())
            else:
                items = [to_item(i) for i in parsed.items if i.action != "remove"]
                order = self.store.create_order(customer["id"], items, parsed.language, msg.text)
                self.store.add_event(order["id"], "created", message_id, after=items)
                self._send_approval(order, customer, note=parsed.notes)
            return

        self._forward_non_order(msg, customer, extra=parsed.notes)

    def _forward_non_order(self, msg: InboundMessage, customer: dict, extra: str = "") -> None:
        text = f"💬 Non-order message from {self._who(customer)}:\n\"{msg.text}\""
        if extra:
            text += f"\nNote: {extra}"
        self._notify_owner(text)

    # ------------------------------------------------------------------ owner side
    def _handle_owner(self, msg: InboundMessage, message_id: int) -> bool:
        """Returns True if the message was a review action. False means: treat it like a customer message."""
        if msg.type == "button" and ":" in msg.button_id:
            action, _, raw_id = msg.button_id.partition(":")
            if action in ("approve", "reject") and raw_id.isdigit():
                self._review(action, int(raw_id), message_id)
                return True
        if msg.type == "text" and msg.context_id:
            order = self.store.get_order_by_approval_message(msg.context_id)
            if order:
                self._correct(order, msg, message_id)
                return True
        return False

    def _review(self, action: str, order_id: int, message_id: int) -> None:
        order = self.store.get_order(order_id)
        if not order:
            self._notify_owner(f"Order #{order_id} not found.")
            return
        if order["status"] != "pending_review":
            self._notify_owner(f"Order #{order_id} is already {order['status']}. Nothing changed.")
            return
        customer = self.store.get_customer(order["customer_id"])

        if action == "reject":
            self.store.set_status(order_id, "rejected")
            self.store.add_event(order_id, "rejected", message_id)
            self._notify_owner(f"Order #{order_id} rejected. The customer was not messaged.")
            return

        if any(needs_attention(i) for i in order["items"]):
            self._notify_owner(f"Order #{order_id} still has unknown lines. Reply to the order message with the "
                               f"correction first (for example: \"the 5 packs are classic\").")
            return

        self.store.set_status(order_id, "approved")
        self.store.add_event(order_id, "approved", message_id, after=order["items"])
        order = self.store.get_order(order_id)

        sheet_note = ""
        if self.sheet:
            try:
                self.sheet.append_order(order, customer)
            except Exception:
                log.exception("sheet write failed for order %s", order_id)
                sheet_note = " ⚠ Could not write to Google Sheet, check logs."
        self._confirm_to_customer(order, customer)
        self._notify_owner(f"✔ Order #{order_id} approved: {summary(order['items'])}. Customer notified.{sheet_note}")

    def _correct(self, order: dict, msg: InboundMessage, message_id: int) -> None:
        if order["status"] != "pending_review":
            self._notify_owner(f"Order #{order['id']} is already {order['status']}. Correction ignored.")
            return
        customer = self.store.get_customer(order["customer_id"])
        try:
            parsed = self.parser.parse(msg.text, order["items"], self.store.get_catalog(), is_correction=True)
        except Exception as exc:
            self._notify_owner(f"Could not understand the correction ({exc}). Try e.g. \"masala 5, remove ginger\".")
            return
        if parsed.intent == "cancel":
            self.store.set_status(order["id"], "rejected")
            self.store.add_event(order["id"], "rejected", message_id)
            self._notify_owner(f"Order #{order['id']} rejected.")
            return
        if not parsed.items:
            self._notify_owner("Could not find any change in that correction. Try e.g. \"masala 5, remove ginger\".")
            return
        before = order["items"]
        changes = list(parsed.items)
        unknown = [i for i in before if i["product_id"] is None]
        named = [c for c in changes if c.product_id and not any(b["product_id"] == c.product_id for b in before)]
        if len(unknown) == 1 and len(named) == 1:
            # The owner told us what the single unknown line was: replace it rather than adding a new line.
            before_wo = [i for i in before if i is not unknown[0]]
            fixed = dict(unknown[0], product_id=named[0].product_id,
                         packs=named[0].packs if named[0].packs is not None else unknown[0]["packs"], confidence=1.0)
            changes = [c for c in changes if c is not named[0]]
            after = merge_items(before_wo + [fixed], changes)
        else:
            after = merge_items(before, changes)
        self.store.replace_items(order["id"], after)
        # before -> after plus the original text is a labelled example for the parser test set.
        self.store.add_event(order["id"], "corrected", message_id, before=before, after=after)
        self._send_approval(self.store.get_order(order["id"]), customer, note="CORRECTED by you.")

    # ------------------------------------------------------------------ outbound helpers
    def _send_approval(self, order: dict, customer: dict, note: str = "") -> None:
        lines = [f"🧾 Order #{order['id']} — {self._who(customer)}"]
        for i in order["items"]:
            flag = "⚠ " if needs_attention(i) else ""
            packs = i["packs"] if i["packs"] is not None else "?"
            line = f"{flag}• {display_name(i['product_id'])} × {packs}"
            if needs_attention(i):
                line += f"   ← \"{i['raw_text']}\""
            elif i["packs"] > MAX_PACKS_SANITY_LIMIT:
                line += "   ⚠ unusually large"
            lines.append(line)
        lines.append(f"\nOriginal:\n\"{order['original_text']}\"")
        if note:
            lines.append(f"\nNote: {note}")
        lines.append("\nTo fix something, reply to this message with the correction.")
        wa_id = self.wa.send_buttons(self.owner, "\n".join(lines),
                                     [(f"approve:{order['id']}", "Approve"), (f"reject:{order['id']}", "Reject")])
        self.store.log_message(wa_id or None, None, "out", "approval", "\n".join(lines))
        if wa_id:
            self.store.set_approval_message(order["id"], wa_id)

    def _confirm_to_customer(self, order: dict, customer: dict) -> None:
        text_summary = summary(order["items"])
        last_in = self.store.last_inbound_at(customer["id"])
        if last_in is None or now() - last_in > SERVICE_WINDOW:
            name, lang = self.confirm_template
            wa_id = self.wa.send_template(customer["phone"], name, lang, [text_summary])
            self.store.log_message(wa_id or None, customer["id"], "out", "template", text_summary)
            return
        if order.get("language") == "pa-Guru":
            body = f"ਤੁਹਾਡਾ ਆਰਡਰ ਪੱਕਾ ਹੋ ਗਿਆ ਹੈ: {text_summary}. ਧੰਨਵਾਦ! — Chai Hai"
        elif order.get("language") in ("pa-Latn", "mixed"):
            body = f"Tuhada order confirm ho gaya hai: {text_summary}. Dhanvaad! — Chai Hai"
        else:
            body = f"Your order is confirmed: {text_summary}. Thank you! — Chai Hai"
        self._send(customer["phone"], body, customer["id"])

    def _notify_owner(self, text: str) -> None:
        self._send(self.owner, text, None)

    def _send(self, to: str, body: str, customer_id: Optional[int]) -> None:
        wa_id = self.wa.send_text(to, body)
        self.store.log_message(wa_id or None, customer_id, "out", "text", body)

    @staticmethod
    def _who(customer: dict) -> str:
        name = customer.get("shop_name") or customer.get("wa_profile_name") or "Unknown"
        return f"{name} (+{customer['phone']})"
