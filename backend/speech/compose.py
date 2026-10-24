"""Everything the app says out loud is worded here (technical spec 3.11).

Templates only, no model call: the same inputs always give the same sentence. Money comes in as
integer cents. Card balances are never spoken (revised spec): the app says whether a card can
cover an item, asks for another card, or plays the low-balance alert. Nothing here reads a
database, calls the network, or decides routing; it words decisions that were already made.
"""
from __future__ import annotations

import uuid
from typing import Any, Iterable

from models.schemas import EligibilityResult, PaymentRecommendation, ProductResolution, VoiceRequest
from payments.routing import Card, CheckoutPlan
from speech.sentences import split_sentences

# A semantic match at or above this score is spoken as "high confidence", below it as "moderate".
HIGH_CONFIDENCE = 0.85

BALANCE_REFUSAL = "For your privacy I don't read out card balances. You can see them in the app."
LOW_BALANCE = "Your {card} is running low. You might want to add funds."
USE_ANOTHER = "Please use another card for this item."


# --- small helpers ---------------------------------------------------------------------------------

def money(cents: int) -> str:
    if isinstance(cents, bool) or not isinstance(cents, int):
        raise ValueError(f"money must be integer cents, got {cents!r}")
    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(cents) // 100:,}.{abs(cents) % 100:02d}"


def _join(parts: Iterable[str]) -> str:
    parts = list(parts)
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def _cards_by_id(cards: Iterable[Card | dict[str, Any]] | None) -> dict[str, Card]:
    return {c.id: c for c in (Card.model_validate(c) if not isinstance(c, Card) else c for c in cards or [])}


def card_name(card_id: str | None, cards: dict[str, Card]) -> str:
    """The name as spoken after "your": the card's own nickname, else its type."""
    card = cards.get(card_id or "")
    if card is None:
        return "card"
    return card.nickname or {"hsa": "HSA card", "fsa": "FSA card"}.get(card.type, "card")


def _request(text: str, *, scope: str = "none", priority: str = "normal", prompt_id: str | None = None,
             request_id: str | None = None) -> VoiceRequest:
    return VoiceRequest(
        request_id=request_id or uuid.uuid4().hex,
        prompt_id=prompt_id,
        text=text,
        priority=priority,
        expects_response=scope != "none",
        response_scope=scope,
        sentences=split_sentences(text),
    )


# --- what was scanned ------------------------------------------------------------------------------

def confidence_phrase(product: ProductResolution, elig: EligibilityResult) -> str:
    """Spec 3.11 wording table; empty when no phrase is called for."""
    if elig.label == "could_not_confirm":
        return ""
    if elig.basis == "upc_match":
        return "" if product.is_medication else "high confidence"
    if elig.basis == "irs_category_rule":
        return "high confidence"
    if elig.basis == "semantic_match":
        return "high confidence" if (elig.confidence or 0.0) >= HIGH_CONFIDENCE else "moderate confidence"
    return ""


def eligibility_line(product: ProductResolution, elig: EligibilityResult) -> str:
    if elig.label == "could_not_confirm":
        return "I could not confirm eligibility."
    label = "HSA eligible" if elig.label == "eligible" else "Not HSA eligible"
    phrase = confidence_phrase(product, elig)
    return f"{label}, {phrase}." if phrase else f"{label}."


def scope_for(rec: PaymentRecommendation | None) -> str:
    if rec is None:
        return "none"
    if rec.decision in ("route_to_hsa", "route_to_general"):
        return "confirm_add"
    if rec.decision == "ask_user":
        return "choose_card"
    return "none"


def _card_line(rec: PaymentRecommendation, cards: dict[str, Card]) -> str:
    name = lambda cid: card_name(cid, cards)
    options = _join(f"your {name(c)}" for c in rec.card_options)
    reason = rec.reason_code
    if reason in ("eligible_sufficient_balance", "not_eligible", "no_health_card_linked"):
        lead = "No HSA or FSA card is linked, so " if reason == "no_health_card_linked" else ""
        return f"{lead}{'use' if lead else 'Use'} your {name(rec.card_id)}. Add it to your cart?"
    if reason == "eligible_insufficient_balance":
        other = name(rec.card_options[0]) if rec.card_options else "other card"
        return (f"Your {name(rec.reroute.from_card_id if rec.reroute else None)} can't cover this item. "
                f"Would you like to use your {other} instead?")
    if reason == "eligibility_unconfirmed":
        return f"Which card would you like to use: {options}?"
    if reason == "copay_unconfirmed":
        return f"Your insurance may cover part of this. Which card would you like to use for the rest: {options}?"
    if reason == "multiple_health_cards":
        return f"Which card would you like to use: {options}?"
    if reason == "zero_copay_nothing_due":
        return "Your insurance covers this, so nothing is due."
    if reason == "no_card_linked":
        return "No card is linked. Please add a card in the app."
    if reason == "no_card_covers":
        return USE_ANOTHER
    return USE_ANOTHER


def compose_speech(
    product: ProductResolution,
    elig: EligibilityResult,
    rec: PaymentRecommendation | None,
    cards: Iterable[Card | dict[str, Any]] | None = None,
    prompt_id: str | None = None,
    request_id: str | None = None,
) -> VoiceRequest:
    """The line spoken after a scan: product, price, eligibility, then the card to pay with."""
    if product.amount_cents is None:
        text = (f"I read {product.name}. {eligibility_line(product, elig)} "
                "I could not read the price. Please move closer to the price tag.")
        return _request(text, request_id=request_id)

    by_id = _cards_by_id(cards)
    parts = [f"{product.name}, {money(product.amount_cents)}.", eligibility_line(product, elig)]
    if rec is not None:
        parts.append(_card_line(rec, by_id))
    low_balance = rec is not None and rec.reason_code == "eligible_insufficient_balance"
    if low_balance and rec.reroute:
        parts.append(LOW_BALANCE.format(card=f"{card_name(rec.reroute.from_card_id, by_id)}"))
    scope = scope_for(rec)
    return _request(" ".join(parts), scope=scope, priority="alert" if low_balance else "normal",
                    prompt_id=prompt_id if scope != "none" else None, request_id=request_id)


# --- the cart --------------------------------------------------------------------------------------

def item_added(name: str, card_id: str | None, cards: Iterable[Card | dict[str, Any]] | None = None) -> VoiceRequest:
    return _request(f"Added {name} to your {card_name(card_id, _cards_by_id(cards))}.")


def item_removed(name: str | None) -> VoiceRequest:
    return _request(f"Removed {name}." if name else "Your cart is already empty.")


def confirm_clear() -> VoiceRequest:
    return _request("Clear everything from your cart?", scope="confirm_clear_cart")


def cart_cleared() -> VoiceRequest:
    return _request("Your cart is empty.")


def cart_contents(items: list[dict[str, Any]]) -> VoiceRequest:
    if not items:
        return _request("Your cart is empty.")
    total = sum(i["amount_cents"] for i in items)
    count = f"{len(items)} item" + ("" if len(items) == 1 else "s")
    lines = " ".join(f"{i['display_name']}, {money(i['amount_cents'])}." for i in items)
    return _request(f"You have {count}, {money(total)} before tax. {lines}")


def balance_refusal() -> VoiceRequest:
    return _request(BALANCE_REFUSAL)


# --- checkout --------------------------------------------------------------------------------------

def _group_lines(groups: Iterable[Any], cards: dict[str, Card]) -> str:
    return _join(f"{money(g.subtotal_cents)} on your {card_name(g.card_id, cards)}"
                 for g in groups if g.subtotal_cents > 0)


def checkout_preview(
    plan: CheckoutPlan,
    cards: Iterable[Card | dict[str, Any]],
    items: list[dict[str, Any]],
    prompt_id: str | None = None,
) -> VoiceRequest:
    by_id = _cards_by_id(cards)
    names = {i["id"]: i["display_name"] for i in items}
    if not plan.groups or plan.total_cents == 0:
        return _request("Your cart is empty, so there is nothing to check out.")
    if plan.ok:
        text = (f"Your total is {money(plan.total_cents)} before tax: {_group_lines(plan.groups, by_id)}. "
                "Ready to check out?")
        return _request(text, scope="confirm_checkout", prompt_id=prompt_id)

    parts: list[str] = []
    for issue in plan.issues:
        card = card_name(issue.card_id, by_id)
        if issue.uncovered_item_ids:
            parts.append(f"No card can cover the {_join(names.get(i, 'item') for i in issue.uncovered_item_ids)}. "
                         + USE_ANOTHER)
            continue
        kept = _join(names.get(i, "item") for i in issue.keep_item_ids)
        moved = _join(m.display_name for m in issue.moves)
        target = _join(dict.fromkeys(f"your {card_name(m.to_card_id, by_id)}" for m in issue.moves))
        if kept:
            parts.append(f"Your {card} can't cover all of this. I can keep the {kept} on your {card} "
                         f"and move the {moved} to {target}.")
        else:
            parts.append(f"Your {card} can't cover this. I can move the {moved} to {target}.")
    if any(i.moves for i in plan.issues):
        parts.append("Is that okay?")
    return _request(" ".join(parts), scope="confirm_checkout" if any(i.moves for i in plan.issues) else "none",
                    prompt_id=prompt_id if any(i.moves for i in plan.issues) else None)


def checkout_result(
    groups: Iterable[Any],
    cards: Iterable[Card | dict[str, Any]],
    low_balance_card_ids: Iterable[str] = (),
) -> VoiceRequest:
    """After a confirmed checkout. Which cards are low is decided by the checkout code, not here."""
    by_id = _cards_by_id(cards)
    groups = [g for g in groups if g.subtotal_cents > 0]
    total = sum(g.subtotal_cents for g in groups)
    text = f"Checked out, simulated. {money(total)} before tax: {_group_lines(groups, by_id)}."
    low = list(low_balance_card_ids)
    for card_id in low:
        text += " " + LOW_BALANCE.format(card=card_name(card_id, by_id))
    return _request(text, priority="alert" if low else "normal")


def low_balance_alert(card_id: str, cards: Iterable[Card | dict[str, Any]]) -> VoiceRequest:
    return _request(LOW_BALANCE.format(card=card_name(card_id, _cards_by_id(cards))), priority="alert")
