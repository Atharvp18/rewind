"""The invoice shown on screen after a checkout: store, date, one line per item, and a total.

Built from the saved payment alone, so the first response and a retry or a later look-up give the
same invoice. The items live in the payment's splits (db.confirm_checkout keeps them), because
checkout empties the cart. All money is integer cents; the *_display strings are for the screen so
the app never has to turn cents into dollars itself. No tax is computed: the total is before tax,
like every other total in the app.
"""
from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any

from data import seed
from speech.compose import money

ITEM_FIELDS = ("id", "seq", "scan_id", "product_key", "display_name", "amount_cents", "eligibility_label")


def store() -> dict:
    return {"name": os.environ.get("REWIND_STORE_NAME") or seed.STORE["name"],
            "address": os.environ.get("REWIND_STORE_ADDRESS") or seed.STORE["address"]}


def item_snapshot(item: dict) -> dict:
    """The part of a cart row that is saved with the payment."""
    return {k: item[k] for k in ITEM_FIELDS if k in item}


def _day(created_at: str | None) -> date:
    """The payment's date in the server's local time; today when the payment is brand new."""
    if created_at:
        try:
            return datetime.fromisoformat(created_at.replace("Z", "+00:00")).astimezone().date()
        except ValueError:
            pass
    return datetime.now().astimezone().date()


def _items(payment: dict) -> list[dict]:
    rows = [i for split in payment["splits"] for i in split.get("items", [])]
    return sorted(rows, key=lambda r: r.get("seq", 0))


def build_invoice(payment: dict) -> dict:
    """payment is db.confirm_checkout's / db.get_payment's return shape."""
    lines: dict[tuple, dict] = {}
    for item in _items(payment):
        key = (item.get("product_key"), item["amount_cents"])        # the same product at the same price
        line = lines.setdefault(key, {"name": item["display_name"], "quantity": 0,
                                      "unit_price_cents": item["amount_cents"]})
        line["quantity"] += 1
    rows = []
    for line in lines.values():
        total = line["quantity"] * line["unit_price_cents"]
        rows.append({**line, "line_total_cents": total,
                     "unit_price_display": money(line["unit_price_cents"]), "line_total_display": money(total)})
    day = _day(payment.get("created_at"))
    total_cents = payment["total_cents"]
    return {
        "invoice_id": payment["payment_id"],
        "store": store(),
        "date": day.isoformat(),
        "date_display": f"{day:%B} {day.day}, {day.year}",
        "lines": rows,
        "total_cents": total_cents,
        "total_display": money(total_cents),
        "simulated": True,
    }


def cart_groups(payment: dict, cards: list[dict]) -> list[dict]:
    """The paid items grouped by card, in the app's CartGroup shape."""
    nick = {c["id"]: c["nickname"] for c in cards}
    groups = []
    for split in payment["splits"]:
        groups.append({
            "card_id": split["card_id"],
            "nickname": nick.get(split["card_id"], ""),
            "items": [{k: i[k] for k in ("id", "scan_id", "display_name", "amount_cents", "eligibility_label")
                       if k in i} for i in sorted(split.get("items", []), key=lambda r: r.get("seq", 0))],
            "subtotal_cents": split["amount_cents"],
        })
    return groups
