"""Order logic tests. No network, no API keys."""

import pytest

from app.service import OrderService, merge_items
from app.schema import OrderItem
from app.store import MemoryStore
from app.whatsapp import InboundMessage
from tests.fakes import CUSTOMER, OWNER, FakeMessenger, FakeParser, FakeSheet, item, tap, text

SCRIPT = {
    "3 masala 2 adrak": {"intent": "order", "language": "pa-Latn", "items": [item("masala", 3), item("ginger", 2)]},
    "also 2 elaichi": {"intent": "follow_up", "language": "pa-Latn", "items": [item("cardamom", 2)]},
    "2 more masala": {"intent": "follow_up", "language": "en", "items": [item("masala", 2)]},
    "make masala 5": {"intent": "follow_up", "language": "en", "items": [item("masala", 5, "set")]},
    "remove ginger": {"intent": "follow_up", "language": "en", "items": [item("ginger", None, "remove")]},
    "cancel": {"intent": "cancel", "language": "en", "items": []},
    "5 pack chai": {"intent": "order", "language": "en", "items": [item(None, 5, raw="5 pack chai", confidence=0.3)]},
    "those are classic": {"intent": "follow_up", "language": "en", "items": [item("classic", None, "set")]},
    "when is delivery?": {"intent": "non_order", "language": "en", "items": []},
    "same as last time": {"intent": "same_as_last", "language": "en", "items": []},
    "ginger 4": {"intent": "follow_up", "language": "en", "items": [item("ginger", 4, "set")]},
}


@pytest.fixture
def env():
    store, wa, sheet = MemoryStore(), FakeMessenger(), FakeSheet()
    parser = FakeParser(SCRIPT)
    svc = OrderService(store, parser, wa, sheet, owner_phone=OWNER)
    return svc, store, wa, sheet, parser


def pending(store):
    return [o for o in store.orders.values() if o["status"] == "pending_review"]


def test_new_order_goes_to_owner_not_customer(env):
    svc, store, wa, sheet, _ = env
    svc.handle(text("3 masala 2 adrak"))
    assert len(pending(store)) == 1
    approval = wa.to(OWNER)[0]
    assert approval["kind"] == "buttons"
    assert "Masala × 3" in approval["body"] and "Ginger × 2" in approval["body"]
    assert approval["extra"][0][0].startswith("approve:")
    assert wa.to(CUSTOMER) == []            # customer hears nothing until approval
    assert sheet.rows == []


def test_approve_confirms_customer_and_writes_sheet(env):
    svc, store, wa, sheet, _ = env
    svc.handle(text("3 masala 2 adrak"))
    order_id = pending(store)[0]["id"]
    svc.handle(tap(f"approve:{order_id}"))
    assert store.orders[order_id]["status"] == "approved"
    assert "3 Masala, 2 Ginger" in wa.to(CUSTOMER)[0]["body"]
    assert wa.to(CUSTOMER)[0]["kind"] == "text"
    row = sheet.rows[0]
    assert row[4] == 3 and row[5] == 2 and row[-2] == 5      # Masala, Ginger, Total


def test_duplicate_webhook_delivery_creates_one_order(env):
    svc, store, wa, _, _ = env
    msg = text("3 masala 2 adrak")
    svc.handle(msg)
    svc.handle(msg)
    assert len(store.orders) == 1
    assert len(wa.to(OWNER)) == 1


def test_follow_up_merges_into_pending_order(env):
    svc, store, wa, _, _ = env
    svc.handle(text("3 masala 2 adrak"))
    svc.handle(text("also 2 elaichi"))
    svc.handle(text("2 more masala"))
    assert len(store.orders) == 1
    items = {i["product_id"]: i["packs"] for i in pending(store)[0]["items"]}
    assert items == {"masala": 5, "ginger": 2, "cardamom": 2}
    assert len(wa.to(OWNER)) == 3           # a fresh approval message after each change
    assert "UPDATED" in wa.to(OWNER)[-1]["body"]


def test_set_and_remove(env):
    svc, store, _, _, _ = env
    svc.handle(text("3 masala 2 adrak"))
    svc.handle(text("make masala 5"))
    svc.handle(text("remove ginger"))
    assert pending(store)[0]["items"] == [
        {"product_id": "masala", "packs": 5, "raw_text": "x", "confidence": 0.9}]


def test_cancel_cancels_whole_pending_order(env):
    svc, store, wa, _, _ = env
    svc.handle(text("3 masala 2 adrak"))
    svc.handle(text("cancel"))
    assert pending(store) == []
    assert list(store.orders.values())[0]["status"] == "cancelled"
    assert "CANCELLED" in wa.to(OWNER)[-1]["body"]


def test_old_approve_button_after_cancel_does_nothing(env):
    svc, store, wa, sheet, _ = env
    svc.handle(text("3 masala 2 adrak"))
    order_id = pending(store)[0]["id"]
    svc.handle(text("cancel"))
    svc.handle(tap(f"approve:{order_id}"))
    assert store.orders[order_id]["status"] == "cancelled"
    assert sheet.rows == [] and wa.to(CUSTOMER) == []


def test_unknown_flavour_is_flagged_and_blocks_approval(env):
    svc, store, wa, sheet, _ = env
    svc.handle(text("5 pack chai"))
    assert "UNKNOWN FLAVOUR" in wa.to(OWNER)[0]["body"]
    order_id = pending(store)[0]["id"]
    svc.handle(tap(f"approve:{order_id}"))
    assert store.orders[order_id]["status"] == "pending_review"
    assert sheet.rows == []


def test_owner_correction_names_the_unknown_line(env):
    svc, store, wa, sheet, parser = env
    svc.handle(text("5 pack chai"))
    approval_id = wa.to(OWNER)[0]["id"]
    svc.handle(text("those are classic", phone=OWNER, context_id=approval_id))
    assert parser.calls[-1]["is_correction"] is True
    order = pending(store)[0]
    assert [(i["product_id"], i["packs"]) for i in order["items"]] == [("classic", 5)]
    assert any(e["type"] == "corrected" for e in store.events)
    svc.handle(tap(f"approve:{order['id']}"))
    assert store.orders[order["id"]]["status"] == "approved"
    assert sheet.rows[0][-2] == 5


def test_owner_correction_on_superseded_approval_message_still_works(env):
    svc, store, wa, _, _ = env
    svc.handle(text("3 masala 2 adrak"))
    first_approval = wa.to(OWNER)[0]["id"]
    svc.handle(text("also 2 elaichi"))
    svc.handle(text("ginger 4", phone=OWNER, context_id=first_approval))
    items = {i["product_id"]: i["packs"] for i in pending(store)[0]["items"]}
    assert items["ginger"] == 4


def test_reject(env):
    svc, store, wa, sheet, _ = env
    svc.handle(text("3 masala 2 adrak"))
    order_id = pending(store)[0]["id"]
    svc.handle(tap(f"reject:{order_id}"))
    assert store.orders[order_id]["status"] == "rejected"
    assert wa.to(CUSTOMER) == [] and sheet.rows == []


def test_non_order_is_forwarded_to_owner_only(env):
    svc, store, wa, _, _ = env
    svc.handle(text("when is delivery?"))
    assert store.orders == {}
    assert "Non-order message" in wa.to(OWNER)[0]["body"]
    assert wa.to(CUSTOMER) == []


def test_unparseable_message_is_forwarded(env):
    svc, store, wa, _, _ = env
    svc.handle(text("asdf qwerty"))
    assert "Could not parse" in wa.to(OWNER)[0]["body"]


def test_voice_note_gets_text_only_reply(env):
    svc, store, wa, _, _ = env
    svc.handle(InboundMessage("wamid.v1", CUSTOMER, "Sharma", "audio"))
    assert "text message" in wa.to(CUSTOMER)[0]["body"]
    assert store.orders == {}


def test_same_as_last_time(env):
    svc, store, wa, _, _ = env
    svc.handle(text("3 masala 2 adrak"))
    svc.handle(tap(f"approve:{pending(store)[0]['id']}"))
    svc.handle(text("same as last time"))
    new = pending(store)[0]
    assert {i["product_id"]: i["packs"] for i in new["items"]} == {"masala": 3, "ginger": 2}
    assert "Copied from last approved order" in wa.to(OWNER)[-1]["body"]


def test_same_as_last_with_no_history_is_forwarded(env):
    svc, store, wa, _, _ = env
    svc.handle(text("same as last time"))
    assert store.orders == {}
    assert "no approved order" in wa.to(OWNER)[0]["body"]


def test_message_after_approval_starts_new_order(env):
    svc, store, _, _, _ = env
    svc.handle(text("3 masala 2 adrak"))
    svc.handle(tap(f"approve:{pending(store)[0]['id']}"))
    svc.handle(text("also 2 elaichi"))
    assert len(store.orders) == 2


def test_owner_can_order_as_a_customer_from_same_phone(env):
    svc, store, wa, _, _ = env
    svc.handle(text("3 masala 2 adrak", phone=OWNER))
    assert len(pending(store)) == 1


def test_late_approval_uses_template(env):
    from datetime import timedelta
    svc, store, wa, _, _ = env
    svc.handle(text("3 masala 2 adrak"))
    for m in store.messages:
        m["created_at"] -= timedelta(hours=30)
    svc.handle(tap(f"approve:{pending(store)[0]['id']}"))
    assert wa.to(CUSTOMER)[0]["kind"] == "template"


def test_merge_add_to_unknown_quantity():
    existing = [{"product_id": "masala", "packs": None, "raw_text": "masala", "confidence": 0.5}]
    out = merge_items(existing, [OrderItem(product_id="masala", packs=4, action="add")])
    assert out[0]["packs"] == 4
