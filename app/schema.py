"""The shape of a parsed message.

The LLM must return JSON matching `ParsedMessage`. Pydantic checks it:
wrong types, missing fields or an unknown product_id raise an error
instead of silently flowing into an order.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.catalog import PRODUCT_IDS

Intent = Literal["order", "follow_up", "cancel", "same_as_last", "non_order"]
Language = Literal["en", "pa-Guru", "pa-Latn", "mixed"]
# How a line changes an existing pending order:
#   add    -> add these packs (new line, or on top of an existing line)
#   set    -> make the quantity exactly this ("make it 5 instead of 3")
#   remove -> drop this flavour from the order
Action = Literal["add", "set", "remove"]


class OrderItem(BaseModel):
    # None means "customer ordered something but the flavour is unclear".
    product_id: Optional[str] = None
    # None means "quantity is unclear".
    packs: Optional[int] = Field(default=None, gt=0)
    # The customer's exact words for this line, kept for review and alias learning.
    raw_text: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    action: Action = "add"

    @field_validator("product_id")
    @classmethod
    def product_must_exist(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in PRODUCT_IDS:
            raise ValueError(f"unknown product_id: {value!r}")
        return value

    @property
    def needs_attention(self) -> bool:
        """True when the owner should look closely at this line."""
        return self.product_id is None or self.packs is None


class ParsedMessage(BaseModel):
    intent: Intent
    items: list[OrderItem] = []
    language: Language = "en"
    notes: str = ""
