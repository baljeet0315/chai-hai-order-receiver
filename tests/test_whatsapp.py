import hashlib
import hmac
import json

from app.whatsapp import parse_webhook, verify_signature


def payload(message):
    return {"entry": [{"changes": [{"value": {
        "contacts": [{"wa_id": "16041111111", "profile": {"name": "Sharma Store"}}],
        "messages": [message]}}]}]}


def test_text_message():
    m = parse_webhook(payload({"id": "wamid.1", "from": "16041111111", "type": "text", "text": {"body": "3 masala"}}))[0]
    assert (m.type, m.text, m.profile_name, m.from_phone) == ("text", "3 masala", "Sharma Store", "16041111111")


def test_button_tap():
    m = parse_webhook(payload({"id": "wamid.2", "from": "16041111111", "type": "interactive",
                               "interactive": {"type": "button_reply", "button_reply": {"id": "approve:7", "title": "Approve"}}}))[0]
    assert (m.type, m.button_id) == ("button", "approve:7")


def test_quoted_reply_has_context():
    m = parse_webhook(payload({"id": "wamid.3", "from": "16041111111", "type": "text", "text": {"body": "masala 5"},
                               "context": {"id": "wamid.out9"}}))[0]
    assert m.context_id == "wamid.out9"


def test_status_updates_are_ignored():
    assert parse_webhook({"entry": [{"changes": [{"value": {"statuses": [{"id": "x", "status": "delivered"}]}}]}]}) == []


def test_signature():
    body = json.dumps({"a": 1}).encode()
    good = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    assert verify_signature("secret", body, good)
    assert not verify_signature("secret", body, "sha256=bad")
    assert not verify_signature("secret", body, None)
