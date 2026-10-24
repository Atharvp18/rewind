"""Cart operations that need a confirmation (technical spec 3.7 and 0.7, "Confirmation rules").

Nothing enters the cart or leaves it in bulk without a live prompt_id of the right scope. A prompt
is single use, so every function here consumes it once and works from what the prompt carried:
the scan endpoint stores the item and the proposed card in the prompt payload, so a "yes" can only
ever add exactly what was asked about.
"""
from __future__ import annotations

import uuid
from typing import Any

from api.envelope import ApiError
from data import db
from payments.routing import HEALTH_TYPES

ADD_SCOPES = ("confirm_add", "choose_card")
ALL_SCOPES = ("confirm_add", "choose_card", "confirm_checkout", "confirm_clear_cart")


def consume(prompt_id: str | None, scopes: tuple[str, ...]) -> dict:
    """Consume `prompt_id` under the first scope that matches. A wrong scope never uses the prompt up.

    Raises db.PromptExpired (E_PROMPT_EXPIRED) when there is no prompt or none of the scopes fits.
    """
    if not prompt_id:
        raise db.PromptExpired("no prompt_id")
    for scope in scopes:
        try:
            return db.consume_prompt(prompt_id, scope)
        except db.PromptExpired:
            continue
    raise db.PromptExpired(prompt_id)


def flat_items(cart: dict) -> list[dict]:
    """Every cart row, oldest first."""
    rows = [item for group in cart["groups"] for item in group["items"]]
    return sorted(rows, key=lambda r: r.get("seq", 0))


def allowed_cards(info: dict, cards: list[dict]) -> list[str]:
    """Which cards this prompt may put the item on."""
    payload = info["payload"]
    active = {c["id"]: c for c in cards if c["status"] == "active"}
    if info["scope"] == "choose_card":
        return [c for c in payload.get("card_options", []) if c in active]
    allowed = [payload["card_id"]] if payload.get("card_id") in active else []
    # Saying a different card on a "use this card?" question is allowed, within the routing rules:
    # the general card always, an HSA/FSA only for an item confirmed eligible.
    for card in active.values():
        if card["id"] in allowed:
            continue
        if card["type"] == "general" or (card["type"] in HEALTH_TYPES
                                         and payload.get("eligibility_label") == "eligible"):
            allowed.append(card["id"])
    return allowed


def add_item(info: dict, card_id: str | None) -> tuple[dict, str, dict]:
    """Add the prompt's item to the cart. Returns (cart, card_id used, the item payload).

    Raises ApiError E_BAD_REQUEST when `card_id` is not one this prompt allows. The prompt has
    already been consumed by then; the caller decides whether to ask again.
    """
    payload = info["payload"]
    cards = db.get_cards()
    allowed = allowed_cards(info, cards)
    if card_id is None:
        card_id = payload.get("card_id") or (allowed[0] if len(allowed) == 1 else None)
    if card_id is None or card_id not in allowed:
        raise ApiError("E_BAD_REQUEST", "card not allowed for this prompt")
    cart = db.add_cart_item(
        scan_id=info["scan_id"],
        product_key=payload["product_key"],
        display_name=payload["display_name"],
        amount_cents=payload["amount_cents"],
        amount_basis=payload["amount_basis"],
        assigned_card_id=card_id,
        eligibility_label=payload["eligibility_label"],
        user_overrode_card=card_id != payload.get("card_id"),
        item_id=uuid.uuid4().hex,
    )
    return cart, card_id, payload


def remove_last() -> tuple[dict | None, dict]:
    return db.pop_last_cart_item()


def clear(info: dict) -> None:
    db.clear_cart()


def prompt_payload(product: Any, label: str, rec: Any) -> dict:
    """What a scan prompt carries so a later yes can add exactly this item."""
    return {
        "product_key": product.product_key,
        "display_name": product.name,
        "amount_cents": rec.amount_cents,
        "amount_basis": rec.amount_basis,
        "eligibility_label": label,
        "card_id": rec.card_id,
        "card_options": list(rec.card_options),
        "reason_code": rec.reason_code,
    }
