"""End-to-end check of the order flow against the REAL Supabase database.

Uses a fake parser and fake WhatsApp, so it costs nothing and messages nobody.
Test rows use phone numbers starting with 1999000 and are deleted at the end.
Run:  python -m scripts.check_supabase
"""

import time
from datetime import datetime

from app.service import OrderService
from app.store_supabase import SupabaseStore
from tests.fakes import FakeMessenger, FakeParser, FakeSheet, item
from app.whatsapp import InboundMessage

OWNER, CUST = "19990000001", "19990000002"
RUN = str(int(time.time()))
SCRIPT = {
    "3 masala 2 adrak": {"intent": "order", "language": "pa-Latn", "items": [item("masala", 3), item("ginger", 2)]},
    "also 5 chai": {"intent": "follow_up", "language": "en", "items": [item(None, 5, raw="5 chai")]},
    "those are classic": {"intent": "follow_up", "language": "en", "items": [item("classic", None, "set")]},
    "1 coffee": {"intent": "order", "language": "en", "items": [item("coffee", 1)]},
    "cancel": {"intent": "cancel", "language": "en", "items": []},
}
n = 0


def msg(phone, body="", button="", context=""):
    global n
    n += 1
    return InboundMessage(f"wamid.check.{RUN}.{n}", phone, "Check", "button" if button else "text",
                          text=body, button_id=button, context_id=context)


def cleanup(store):
    db = store.db
    ids = []
    for phone in (OWNER, CUST, "10000000000"):
        ids += [c["id"] for c in db.table("customers").select("id").eq("phone", phone).execute().data]
    # Order matters: events point at messages, so orders (and their events) go first.
    for cid in ids:
        db.table("orders").delete().eq("customer_id", cid).execute()
    for cid in ids:
        db.table("messages").delete().eq("customer_id", cid).execute()
    for cid in ids:
        db.table("customers").delete().eq("id", cid).execute()
    # fake outbound ids look like wamid.out.<run>.<n>; real WhatsApp ids never do
    db.table("messages").delete().like("wa_message_id", "wamid.out.%").execute()


def main():
    store, wa, sheet = SupabaseStore(), FakeMessenger(), FakeSheet()
    cleanup(store)
    # make fake outbound ids unique per run
    wa._record_orig = wa._record
    wa._record = lambda kind, to, body, extra=None: _rec(wa, kind, to, body, extra)
    svc = OrderService(store, FakeParser(SCRIPT), wa, sheet, owner_phone=OWNER)

    def check(label, ok):
        print(("PASS  " if ok else "FAIL  ") + label)
        return ok

    results = []
    svc.handle(msg(CUST, "3 masala 2 adrak"))
    cust = store.get_or_create_customer(CUST)
    order = store.get_pending_order(cust["id"])
    results.append(check("order created as pending_review", bool(order) and len(order["items"]) == 2))

    dup = msg(CUST, "3 masala 2 adrak"); dup.wa_message_id = f"wamid.check.{RUN}.1"
    svc.handle(dup)
    results.append(check("duplicate delivery ignored", len(wa.to(OWNER)) == 1))

    svc.handle(msg(CUST, "also 5 chai"))
    order = store.get_pending_order(cust["id"])
    results.append(check("follow-up merged, unknown line stored", len(order["items"]) == 3
                         and any(i["product_id"] is None for i in order["items"])))

    first_approval = wa.to(OWNER)[0]["id"]
    svc.handle(msg(OWNER, "those are classic", context=first_approval))
    order = store.get_order(order["id"])
    got = {i["product_id"]: i["packs"] for i in order["items"]}
    results.append(check("owner correction via quoted (older) approval message", got == {"masala": 3, "ginger": 2, "classic": 5}))

    svc.handle(msg(OWNER, button=f"approve:{order['id']}"))
    order = store.get_order(order["id"])
    results.append(check("approved + approved_at is a datetime", order["status"] == "approved"
                         and isinstance(order["approved_at"], datetime)))
    results.append(check("sheet row built", len(sheet.rows) == 1 and sheet.rows[0][-2] == 10))
    results.append(check("customer confirmed by free-form text (inside 24h)", wa.to(CUST) and wa.to(CUST)[0]["kind"] == "text"))

    svc.handle(msg(CUST, "1 coffee"))
    svc.handle(msg(CUST, "cancel"))
    results.append(check("second order cancelled", store.get_pending_order(cust["id"]) is None))
    results.append(check("last_approved_order found", store.last_approved_order(cust["id"])["id"] == order["id"]))
    events = store.db.table("order_events").select("type").eq("order_id", order["id"]).execute().data
    results.append(check("events recorded: " + ", ".join(e["type"] for e in events),
                         {e["type"] for e in events} >= {"created", "merged", "corrected", "approved"}))

    cleanup(store)
    print("\nALL GOOD" if all(results) else "\nSOMETHING FAILED - paste this output to Claude")


def _rec(wa, kind, to, body, extra):
    wa_id = f"wamid.out.{RUN}.{len(wa.sent) + 1}"
    wa.sent.append({"kind": kind, "to": to, "body": body, "extra": extra, "id": wa_id})
    return wa_id


if __name__ == "__main__":
    main()
