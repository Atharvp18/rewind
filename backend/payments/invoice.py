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


# --- purchase history (PROPOSED: GET /v1/payments, business spec 6.6) ----------------------------

# A fixed-rate tax ESTIMATE for one state, labeled as an estimate (business spec 6.6). Tax on
# groceries and medicine varies and is unverified, so the note says so.
TAX_BASIS_POINTS = 725
TAX_NOTE = "Estimated sales tax at 7.25% (one fixed rate). Estimate only: tax on medicine varies."


def store_contact() -> dict:
    return {**store(), "phone": os.environ.get("REWIND_STORE_PHONE") or seed.STORE["phone"]}


def history_invoice(payment: dict, cards: list[dict]) -> dict:
    """One payment as the History list shows it: store, items with eligibility and card, an
    estimated tax, which card paid what, and the possible-reimbursement total (an HSA/FSA-eligible
    item paid with the everyday card). Rewind prepares this; it never files a claim."""
    by_id = {c["id"]: c for c in cards}
    items = _items(payment)
    tagged = next((i["store"] for i in items if i.get("store")), None)   # the store checked in to, if any
    lines = []
    for item in items:
        card_id = next(s["card_id"] for s in payment["splits"] if item in s.get("items", []))
        lines.append({
            "name": item["display_name"], "qty": 1, "unit_cents": item["amount_cents"],
            "amount_cents": item["amount_cents"], "eligibility_label": item.get("eligibility_label", "could_not_confirm"),
            "card_id": card_id, "card_type": by_id.get(card_id, {}).get("type", "general"),
        })
    subtotal = payment["total_cents"]
    tax = (subtotal * TAX_BASIS_POINTS + 5000) // 10000            # integer cents, rounded half up
    created = payment.get("created_at") or datetime.now().astimezone().isoformat()
    return {
        "invoice_id": payment["payment_id"],
        "date": created,
        "store": tagged or store_contact(),
        "lines": lines,
        "subtotal_cents": subtotal,
        "tax_cents": tax,
        "tax_note": TAX_NOTE,
        "total_cents": subtotal + tax,
        "payments": [{"card_id": s["card_id"], "nickname": by_id.get(s["card_id"], {}).get("nickname", ""),
                      "type": by_id.get(s["card_id"], {}).get("type", "general"),
                      "last4": by_id.get(s["card_id"], {}).get("last4"), "amount_cents": s["amount_cents"]}
                     for s in payment["splits"]],
        "reimbursable_cents": sum(l["amount_cents"] for l in lines
                                  if l["eligibility_label"] == "eligible" and l["card_type"] == "general"),
    }
