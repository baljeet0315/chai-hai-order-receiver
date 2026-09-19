"""Storage interface plus an in-memory implementation.

MemoryStore is used by the tests and for running locally without Supabase.
SupabaseStore (store_supabase.py) has the same methods backed by Postgres.
Orders and items are plain dicts so both stores return identical shapes.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Optional

from app.catalog import CATALOG


def now() -> datetime:
    return datetime.now(timezone.utc)


class MemoryStore:
    def __init__(self):
        self.customers: dict[int, dict] = {}
        self.messages: list[dict] = []
        self.orders: dict[int, dict] = {}
        self.events: list[dict] = []
        self.aliases: list[dict] = []
        self._seq = 0

    def _next(self) -> int:
        self._seq += 1
        return self._seq

    # --- customers -------------------------------------------------------
    def get_or_create_customer(self, phone: str, profile_name: str = "") -> dict:
        for c in self.customers.values():
            if c["phone"] == phone:
                return c
        c = {"id": self._next(), "phone": phone, "wa_profile_name": profile_name, "shop_name": None,
             "preferred_language": None}
        self.customers[c["id"]] = c
        return c

    def get_customer(self, customer_id: int) -> dict:
        return self.customers[customer_id]

    def set_customer_language(self, customer_id: int, language: str) -> None:
        self.customers[customer_id]["preferred_language"] = language

    # --- messages --------------------------------------------------------
    def log_message(self, wa_message_id: Optional[str], customer_id: Optional[int], direction: str,
                    msg_type: str, body: str, raw: Optional[dict] = None) -> Optional[int]:
        """Returns the new row id, or None if this wa_message_id was already logged (duplicate delivery)."""
        if wa_message_id and any(m["wa_message_id"] == wa_message_id for m in self.messages):
            return None
        row = {"id": self._next(), "wa_message_id": wa_message_id, "customer_id": customer_id,
               "direction": direction, "type": msg_type, "body": body, "raw_payload": raw, "created_at": now()}
        self.messages.append(row)
        return row["id"]

    def last_inbound_at(self, customer_id: int) -> Optional[datetime]:
        times = [m["created_at"] for m in self.messages
                 if m["customer_id"] == customer_id and m["direction"] == "in"]
        return max(times) if times else None

    # --- orders ----------------------------------------------------------
    def create_order(self, customer_id: int, items: list[dict], language: str, original_text: str) -> dict:
        order = {"id": self._next(), "customer_id": customer_id, "status": "pending_review",
                 "language": language, "original_text": original_text, "approval_wa_message_id": None,
                 "items": copy.deepcopy(items), "created_at": now(), "approved_at": None}
        self.orders[order["id"]] = order
        return copy.deepcopy(order)

    def get_order(self, order_id: int) -> Optional[dict]:
        order = self.orders.get(order_id)
        return copy.deepcopy(order) if order else None

    def get_pending_order(self, customer_id: int) -> Optional[dict]:
        pending = [o for o in self.orders.values()
                   if o["customer_id"] == customer_id and o["status"] == "pending_review"]
        return copy.deepcopy(max(pending, key=lambda o: o["id"])) if pending else None

    def get_order_by_approval_message(self, wa_message_id: str) -> Optional[dict]:
        for o in self.orders.values():
            if wa_message_id in o.get("approval_history", []) or o["approval_wa_message_id"] == wa_message_id:
                return copy.deepcopy(o)
        return None

    def last_approved_order(self, customer_id: int) -> Optional[dict]:
        done = [o for o in self.orders.values() if o["customer_id"] == customer_id and o["status"] == "approved"]
        return copy.deepcopy(max(done, key=lambda o: o["id"])) if done else None

    def replace_items(self, order_id: int, items: list[dict], appended_text: str = "") -> None:
        order = self.orders[order_id]
        order["items"] = copy.deepcopy(items)
        if appended_text:
            order["original_text"] = f'{order["original_text"]}\n{appended_text}'

    def set_status(self, order_id: int, status: str) -> None:
        self.orders[order_id]["status"] = status
        if status == "approved":
            self.orders[order_id]["approved_at"] = now()

    def set_approval_message(self, order_id: int, wa_message_id: str) -> None:
        order = self.orders[order_id]
        order.setdefault("approval_history", []).append(wa_message_id)
        order["approval_wa_message_id"] = wa_message_id

    def add_event(self, order_id: int, event_type: str, message_id: Optional[int] = None,
                  before: Optional[list] = None, after: Optional[list] = None) -> None:
        self.events.append({"id": self._next(), "order_id": order_id, "type": event_type,
                            "message_id": message_id, "before": before, "after": after, "created_at": now()})

    # --- catalog ---------------------------------------------------------
    def get_catalog(self) -> dict[str, list[str]]:
        catalog = {pid: list(names) for pid, names in CATALOG.items()}
        for a in self.aliases:
            if a["customer_id"] is None and a["alias"] not in catalog[a["product_id"]]:
                catalog[a["product_id"]].append(a["alias"])
        return catalog

    def add_alias(self, product_id: str, alias: str, customer_id: Optional[int] = None, source: str = "owner") -> None:
        self.aliases.append({"product_id": product_id, "alias": alias, "customer_id": customer_id, "source": source})
