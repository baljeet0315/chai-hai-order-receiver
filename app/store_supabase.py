"""Supabase (Postgres) implementation of the store. Same methods and return shapes as MemoryStore."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from supabase import create_client

from app.config import settings
from app.store import now

ITEM_FIELDS = ("product_id", "packs", "raw_text", "confidence")


def _ts(value) -> Optional[datetime]:
    return datetime.fromisoformat(value) if isinstance(value, str) else value


class SupabaseStore:
    def __init__(self):
        self.db = create_client(settings.supabase_url, settings.supabase_key)

    # --- customers -------------------------------------------------------
    def get_or_create_customer(self, phone: str, profile_name: str = "") -> dict:
        rows = self.db.table("customers").select("*").eq("phone", phone).execute().data
        if rows:
            return rows[0]
        return self.db.table("customers").insert({"phone": phone, "wa_profile_name": profile_name}).execute().data[0]

    def get_customer(self, customer_id: int) -> dict:
        return self.db.table("customers").select("*").eq("id", customer_id).execute().data[0]

    def set_customer_language(self, customer_id: int, language: str) -> None:
        self.db.table("customers").update({"preferred_language": language}).eq("id", customer_id).execute()

    # --- messages --------------------------------------------------------
    def log_message(self, wa_message_id, customer_id, direction, msg_type, body, raw=None) -> Optional[int]:
        if wa_message_id:
            seen = self.db.table("messages").select("id").eq("wa_message_id", wa_message_id).execute().data
            if seen:
                return None
        row = {"wa_message_id": wa_message_id, "customer_id": customer_id, "direction": direction,
               "type": msg_type, "body": body, "raw_payload": raw}
        try:
            return self.db.table("messages").insert(row).execute().data[0]["id"]
        except Exception as exc:  # unique violation when Meta delivers twice at the same instant
            if "duplicate" in str(exc).lower() or "23505" in str(exc):
                return None
            raise

    def last_inbound_at(self, customer_id: int) -> Optional[datetime]:
        rows = (self.db.table("messages").select("created_at").eq("customer_id", customer_id)
                .eq("direction", "in").order("created_at", desc=True).limit(1).execute().data)
        return _ts(rows[0]["created_at"]) if rows else None

    # --- orders ----------------------------------------------------------
    def _hydrate(self, order: Optional[dict]) -> Optional[dict]:
        if not order:
            return None
        items = self.db.table("order_items").select("*").eq("order_id", order["id"]).order("id").execute().data
        order["items"] = [{f: i[f] for f in ITEM_FIELDS} for i in items]
        order["created_at"] = _ts(order["created_at"])
        order["approved_at"] = _ts(order.get("approved_at"))
        return order

    def _insert_items(self, order_id: int, items: list[dict]) -> None:
        if items:
            self.db.table("order_items").insert(
                [{"order_id": order_id, **{f: i.get(f) for f in ITEM_FIELDS}} for i in items]).execute()

    def create_order(self, customer_id: int, items: list[dict], language: str, original_text: str) -> dict:
        order = self.db.table("orders").insert(
            {"customer_id": customer_id, "language": language, "original_text": original_text}).execute().data[0]
        self._insert_items(order["id"], items)
        return self._hydrate(order)

    def get_order(self, order_id: int) -> Optional[dict]:
        rows = self.db.table("orders").select("*").eq("id", order_id).execute().data
        return self._hydrate(rows[0] if rows else None)

    def get_pending_order(self, customer_id: int) -> Optional[dict]:
        rows = (self.db.table("orders").select("*").eq("customer_id", customer_id)
                .eq("status", "pending_review").order("id", desc=True).limit(1).execute().data)
        return self._hydrate(rows[0] if rows else None)

    def get_order_by_approval_message(self, wa_message_id: str) -> Optional[dict]:
        rows = self.db.table("orders").select("*").contains("approval_history", [wa_message_id]).execute().data
        return self._hydrate(rows[0] if rows else None)

    def last_approved_order(self, customer_id: int) -> Optional[dict]:
        rows = (self.db.table("orders").select("*").eq("customer_id", customer_id)
                .eq("status", "approved").order("id", desc=True).limit(1).execute().data)
        return self._hydrate(rows[0] if rows else None)

    def replace_items(self, order_id: int, items: list[dict], appended_text: str = "") -> None:
        self.db.table("order_items").delete().eq("order_id", order_id).execute()
        self._insert_items(order_id, items)
        if appended_text:
            current = self.db.table("orders").select("original_text").eq("id", order_id).execute().data[0]
            self.db.table("orders").update(
                {"original_text": f'{current["original_text"]}\n{appended_text}'}).eq("id", order_id).execute()

    def set_status(self, order_id: int, status: str) -> None:
        patch = {"status": status}
        if status == "approved":
            patch["approved_at"] = now().isoformat()
        self.db.table("orders").update(patch).eq("id", order_id).execute()

    def set_approval_message(self, order_id: int, wa_message_id: str) -> None:
        current = self.db.table("orders").select("approval_history").eq("id", order_id).execute().data[0]
        history = (current["approval_history"] or []) + [wa_message_id]
        self.db.table("orders").update(
            {"approval_wa_message_id": wa_message_id, "approval_history": history}).eq("id", order_id).execute()

    def add_event(self, order_id, event_type, message_id=None, before=None, after=None) -> None:
        self.db.table("order_events").insert({"order_id": order_id, "type": event_type, "message_id": message_id,
                                              "before": before, "after": after}).execute()

    # --- catalog ---------------------------------------------------------
    def get_catalog(self) -> dict[str, list[str]]:
        products = self.db.table("products").select("id").eq("active", True).execute().data
        catalog: dict[str, list[str]] = {p["id"]: [] for p in products}
        aliases = self.db.table("product_aliases").select("product_id, alias").is_("customer_id", "null").execute().data
        for a in aliases:
            if a["product_id"] in catalog:
                catalog[a["product_id"]].append(a["alias"])
        return catalog

    def add_alias(self, product_id: str, alias: str, customer_id: Optional[int] = None, source: str = "owner") -> None:
        self.db.table("product_aliases").upsert(
            {"product_id": product_id, "alias": alias, "customer_id": customer_id, "source": source},
            on_conflict="product_id,alias,customer_id").execute()
