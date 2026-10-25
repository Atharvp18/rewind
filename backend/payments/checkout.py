"""Checkout preview and confirm (technical spec 3.6).

Preview works out who pays what and what to ask. Confirm only charges what the user heard: the
preview stores the exact split in its prompt, and confirm recomputes the split from the current
cart and balances and refuses to charge if anything differs. Balances come from Supabase, which
is the live balance source; Nessie keeps no spending (see payments/nessie.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data import db
from models.schemas import VoiceRequest
from lookup import purchase_memory
from payments import cart_store, invoice, store_checkin
from payments.routing import HEALTH_TYPES, CheckoutGroup, CheckoutPlan, Move, apply_moves, plan_checkout
from speech import compose

# A health card whose balance falls under this after a checkout triggers the low-balance alert.
# $10.00 (team decision 2026-10-24, matching the agents and the spec): under this, the alert plays.
# The run 1 demo ($321.52 left) stays quiet.
LOW_BALANCE_CENTS = 1000

CHANGED = "Something changed since I last checked, so let me read it again. "


@dataclass
class Preview:
    plan: CheckoutPlan | None
    voice: VoiceRequest
    cards: list[dict] = field(default_factory=list)


@dataclass
class Confirmed:
    payment: dict | None            # None when nothing was charged
    voice: VoiceRequest
    groups: list[CheckoutGroup] = field(default_factory=list)
    cards: list[dict] = field(default_factory=list)
    ledger: list[dict] = field(default_factory=list)      # withdrawals to record in Nessie (new payments only)
    invoice: dict | None = None                           # what the screen shows after a charge


def splits_of(groups: list[CheckoutGroup]) -> list[dict]:
    """The charge per card, in a fixed order so two splits compare equal."""
    return sorted(({"card_id": g.card_id, "amount_cents": g.subtotal_cents}
                   for g in groups if g.subtotal_cents > 0), key=lambda s: s["card_id"])


def _solve(items: list[dict], cards: list[dict]) -> tuple[CheckoutPlan, list[Move], CheckoutPlan]:
    """(the plan for the cart as it is, the proposed moves, the plan after those moves)."""
    plan = plan_checkout(items, cards)
    moves = [m for issue in plan.issues for m in issue.moves]
    final = plan_checkout(apply_moves(items, moves), cards) if moves else plan
    return plan, moves, final


def preview(prefix: str = "") -> Preview:
    cart, cards = db.get_cart(), db.get_cards()
    items = cart_store.flat_items(cart)
    if not items:
        return Preview(None, compose.checkout_preview(CheckoutPlan(groups=[], total_cents=0, issues=[], ok=True),
                                                      cards, items), cards)
    if not any(c["status"] == "active" for c in cards):
        return Preview(None, compose.no_card_checkout(), cards)

    plan, moves, final = _solve(items, cards)
    askable = final.ok and not any(i.uncovered_item_ids for i in plan.issues)
    prompt_id = None
    if askable:
        prompt_id = db.create_prompt("confirm_checkout", None, {
            "splits": splits_of(final.groups),
            "moves": [m.model_dump() for m in moves],
        })
    return Preview(plan, compose.checkout_preview(plan, cards, items, prompt_id=prompt_id, prefix=prefix), cards)


def _low_balance_cards(splits: list[dict], cards: list[dict], new_balances: list[dict]) -> list[str]:
    health = {c["id"] for c in cards if c["type"] in HEALTH_TYPES}
    paid = {s["card_id"] for s in splits}
    now = {b["id"]: b["balance_cents"] for b in new_balances}
    return [cid for cid in sorted(paid & health) if now.get(cid, LOW_BALANCE_CENTS) < LOW_BALANCE_CENTS]


def ledger_entries(payment: dict, cards: list[dict]) -> list[dict]:
    """One Nessie withdrawal per charged card that is linked to a Nessie account."""
    account = {c["id"]: c.get("nessie_account_id") for c in cards}
    return [{"account_id": account[s["card_id"]], "amount_cents": s["amount_cents"],
             "description": f"Rewind simulated checkout {payment['payment_id']}"}
            for s in payment["splits"] if account.get(s["card_id"])]


def _result(payment: dict, cards: list[dict]) -> Confirmed:
    splits = payment["splits"]
    nick = {c["id"]: c["nickname"] for c in cards}
    groups = [CheckoutGroup(card_id=s["card_id"], nickname=nick.get(s["card_id"], ""), item_ids=[],
                            subtotal_cents=s["amount_cents"]) for s in splits]
    low = _low_balance_cards(splits, cards, payment["new_balances"])
    ledger = [] if payment.get("replayed") else ledger_entries(payment, cards)   # a retry is not a new payment
    return Confirmed(payment, compose.checkout_result(groups, cards, low), groups, cards, ledger,
                     invoice.build_invoice(payment))


def confirm(idempotency_key: str, prompt_id: str | None) -> Confirmed:
    """Charge the previewed split. Raises db.PromptExpired for a prompt that cannot authorize this."""
    existing = db.get_payment(idempotency_key)
    if existing:                                  # a retry of a payment that already went through
        return _result(existing, db.get_cards())
    info = cart_store.consume(prompt_id, ("confirm_checkout",))
    return charge(idempotency_key, info)


def charge(idempotency_key: str, info: dict) -> Confirmed:
    """Charge using an already consumed confirm_checkout prompt."""
    payload = info["payload"]
    cart, cards = db.get_cart(), db.get_cards()
    items = cart_store.flat_items(cart)
    moves = [Move(**m) for m in payload.get("moves", [])]
    final_items = apply_moves(items, moves)
    plan = plan_checkout(final_items, cards)
    splits = splits_of(plan.groups)

    if not items or not plan.ok or splits != payload.get("splits"):
        again = preview(prefix=CHANGED if items else "")      # cart or balances moved: ask again
        return Confirmed(None, again.voice, cards=cards)

    try:
        for m in moves:                                       # the user agreed to these moves
            db.reassign_cart_item(m.item_id, m.to_card_id)
        # the cart is emptied by the charge, so the paid items travel with it for the invoice
        here = store_checkin.current()
        tag = {"store": store_checkin.public(here)} if here else {}   # the store the user checked in to
        paid = [dict(s, items=[dict(invoice.item_snapshot(i), **tag) for i in final_items
                               if i["assigned_card_id"] == s["card_id"]]) for s in splits]
        payment = db.confirm_checkout(idempotency_key, paid)
        if not payment.get("replayed"):                       # a repeated key charged nothing new
            purchase_memory.mirror_payment(payment.get("payment_id"))   # History's Moss memory, in the background
    except db.CheckoutFailed as e:
        if e.code not in ("E_CARD_CANNOT_PAY", "E_EMPTY_CART"):
            raise
        again = preview(prefix=CHANGED)
        return Confirmed(None, again.voice, cards=cards)
    return _result(payment, cards)
