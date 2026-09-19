"""Google Sheets output: one row per approved order, one column per flavour."""

from __future__ import annotations

import json
from zoneinfo import ZoneInfo

from app.catalog import CATALOG
from app.config import settings

FLAVOURS = list(CATALOG.keys())
HEADER = ["Date", "Order ID", "Customer", "Phone"] + [f.capitalize() for f in FLAVOURS] + ["Total packs", "Original message"]
LOCAL_TZ = ZoneInfo("America/Vancouver")


def order_to_row(order: dict, customer: dict) -> list:
    packs = {f: 0 for f in FLAVOURS}
    for item in order["items"]:
        packs[item["product_id"]] += item["packs"]
    when = (order.get("approved_at") or order["created_at"]).astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M")
    name = customer.get("shop_name") or customer.get("wa_profile_name") or ""
    return [when, order["id"], name, "+" + customer["phone"]] + [packs[f] or "" for f in FLAVOURS] + \
           [sum(packs.values()), order["original_text"]]


class GoogleSheet:
    def __init__(self):
        import gspread

        creds = json.loads(settings.google_service_account_json)
        book = gspread.service_account_from_dict(creds).open_by_key(settings.google_sheet_id)
        try:
            self.ws = book.worksheet(settings.google_sheet_tab)
        except gspread.WorksheetNotFound:
            self.ws = book.add_worksheet(settings.google_sheet_tab, rows=1000, cols=len(HEADER))
        if self.ws.row_values(1) != HEADER:
            self.ws.update(values=[HEADER], range_name="A1")

    def append_order(self, order: dict, customer: dict) -> None:
        self.ws.append_row(order_to_row(order, customer), value_input_option="USER_ENTERED")
