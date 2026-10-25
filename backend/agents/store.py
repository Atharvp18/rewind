"""Bridge between the payment agent's session and Supabase.

Cards and cart items live in Atharv's tables (data/schema.sql); every read and
write goes through data/db.py. The payment rules stay pure: load() fills the
session from the database, the rules change the session, save() writes the
difference back, and strip() removes cards and cart before the session goes
back to the orchestrator, so balances are never kept in ctx.storage.
"""
from __future__ import annotations

import copy
import logging

from data import db
from lookup import purchase_memory
from agents.speaker import say

logger = logging.getLogger(__name__)

DB_DOWN = say("I can't reach your cards right now. Please try again in a moment.", fixed=True)
CHECKOUT_FAILED = say("That payment didn't go through, and nothing was charged. Please use another card.",
                      "nothing was charged", "another card", fixed=True)


def load(session: dict) -> dict:
    """Session copy with cards and cart read from Supabase. Raises DBUnavailable."""
    out = copy.deepcopy(session)
    out["cards"] = db.get_cards()
    cart = db.get_cart()
    out["cart"] = sorted((dict(i) for g in cart["groups"] for i in g["items"]), key=lambda i: i.get("seq", 0))
    return out


def strip(session: dict) -> dict:
    out = {k: v for k, v in session.items() if k not in ("cards", "cart", "checkout_splits", "checkout_moves")}
    return out


def save(before: dict, after: dict, request_id: str):
    """Write cart changes and checkout to Supabase. Returns failure Facts, or None."""
    try:
        splits = after.get("checkout_splits")
        if splits:
            # Items the preview moved to the next card are reassigned first: confirm_checkout records
            # each item under the card its cart row names (purchase_items, which History reads).
            for m in after.get("checkout_moves", []):
                db.reassign_cart_item(m["item_id"], m["card_id"], m["user_overrode_card"])
            # Atomic in Postgres: debits every card and empties the cart, or changes nothing.
            # The request id is the idempotency key, so a retried message never charges twice.
            result = db.confirm_checkout(request_id, splits)
            purchase_memory.mirror_payment((result or {}).get("payment_id"))   # background; see lookup/purchase_memory.py
            return None

        old = {i["id"]: i for i in before["cart"]}
        new = {i["id"]: i for i in after["cart"]}
        removed = [i for i in old if i not in new]
        if removed and not new:
            db.clear_cart()
        else:
            for _ in removed:            # the rules only ever remove the most recent item
                db.remove_last_cart_item()
        for item_id, item in new.items():
            if item_id in old and item["assigned_card_id"] != old[item_id]["assigned_card_id"]:
                db.reassign_cart_item(item_id, item["assigned_card_id"], item["user_overrode_card"])
        for item_id, item in new.items():
            if item_id not in old:
                snap = item["_scan"]
                db.save_scan(item["scan_id"], snap["product"], snap["eligibility"])
                db.add_cart_item(item["scan_id"], item["product_key"], item["display_name"],
                                 item["amount_cents"], item["amount_basis"], item["assigned_card_id"],
                                 item["eligibility_label"], item["user_overrode_card"], item_id=item_id)
        return None
    except db.CheckoutFailed as exc:
        logger.warning("checkout refused: %s", exc.code)
        return CHECKOUT_FAILED
    except db.DBUnavailable as exc:
        logger.warning("cart not saved: %s", exc)
        return DB_DOWN
