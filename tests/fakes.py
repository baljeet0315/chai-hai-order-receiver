"""Stand-ins for Claude and WhatsApp so the order logic can be tested offline."""

from app.parser import ParseError
from app.schema import ParsedMessage
from app.whatsapp import InboundMessage

OWNER = "16040000000"
CUSTOMER = "16041111111"


class FakeParser:
    """Returns a scripted ParsedMessage for each text."""

    def __init__(self, script: dict):
        self.script = script
        self.calls = []

    def parse(self, text, pending_items=None, catalog=None, is_correction=False):
        self.calls.append({"text": text, "pending": pending_items, "is_correction": is_correction})
        if text not in self.script:
            raise ParseError("no script for: " + text)
        return ParsedMessage.model_validate(self.script[text])


class FakeMessenger:
    def __init__(self):
        self.sent = []

    def _record(self, kind, to, body, extra=None):
        wa_id = f"wamid.out{len(self.sent) + 1}"
        self.sent.append({"kind": kind, "to": to, "body": body, "extra": extra, "id": wa_id})
        return wa_id

    def send_text(self, to, body, reply_to=""):
        return self._record("text", to, body)

    def send_buttons(self, to, body, buttons):
        return self._record("buttons", to, body, buttons)

    def send_template(self, to, name, lang, body_params):
        return self._record("template", to, " ".join(body_params), name)

    def to(self, phone):
        return [m for m in self.sent if m["to"] == phone]


class FakeSheet:
    def __init__(self):
        self.rows = []

    def append_order(self, order, customer):
        from app.sheets import order_to_row
        self.rows.append(order_to_row(order, customer))


_n = 0


def text(body, phone=CUSTOMER, context_id="", name="Sharma Store"):
    global _n
    _n += 1
    return InboundMessage(wa_message_id=f"wamid.in{_n}", from_phone=phone, profile_name=name, type="text",
                          text=body, context_id=context_id)


def tap(button_id, phone=OWNER):
    global _n
    _n += 1
    return InboundMessage(wa_message_id=f"wamid.in{_n}", from_phone=phone, profile_name="Owner", type="button",
                          button_id=button_id)


def item(product_id, packs, action="add", raw="x", confidence=0.9):
    return {"product_id": product_id, "packs": packs, "raw_text": raw, "confidence": confidence, "action": action}
