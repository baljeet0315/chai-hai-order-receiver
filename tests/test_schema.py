"""Tests for the schema. These need no API key and run instantly."""

import pytest
from pydantic import ValidationError

from app.schema import OrderItem, ParsedMessage


def test_valid_order_is_accepted():
    msg = ParsedMessage(
        intent="order",
        language="pa-Latn",
        items=[{"product_id": "masala", "packs": 3, "raw_text": "3 masale wali", "confidence": 0.95}],
    )
    assert msg.items[0].product_id == "masala"
    assert msg.items[0].needs_attention is False


def test_unknown_flavour_is_allowed_but_flagged():
    item = OrderItem(product_id=None, packs=5, raw_text="5 pack chai", confidence=0.4)
    assert item.needs_attention is True


def test_invented_product_is_rejected():
    with pytest.raises(ValidationError):
        OrderItem(product_id="lemon", packs=2, raw_text="2 lemon", confidence=0.9)


def test_zero_or_negative_packs_rejected():
    with pytest.raises(ValidationError):
        OrderItem(product_id="masala", packs=0, raw_text="0 masala", confidence=0.9)


def test_bad_intent_rejected():
    with pytest.raises(ValidationError):
        ParsedMessage(intent="refund", language="en")
