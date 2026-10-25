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


def is_unlisted(elig: EligibilityResult) -> bool:
    """Treated as not eligible only because no listing was found. The shopper is never told that."""
    return elig.label == "not_eligible" and elig.basis in ("no_match", "index_unavailable")


def eligibility_line(product: ProductResolution, elig: EligibilityResult) -> str:
    if elig.label == "could_not_confirm":
        return "I could not confirm eligibility."
    # The confidence phrase is not spoken or captioned (Nak, 2026-10-24): just the result.
    # confidence_phrase() stays for anything that wants to show it.
    if elig.label == "eligible":
        return "HSA eligible."
    if is_unlisted(elig):
        return ""          # not in our data: say nothing about the list, just name it, price it and route it
    return "Not HSA eligible."


def scope_for(rec: PaymentRecommendation | None) -> str:
    if rec is None:
        return "none"
    if rec.decision in ("route_to_hsa", "route_to_general"):
        return "confirm_add"
    if rec.decision == "ask_user":
        return "choose_card"
    return "none"


def _card_line(rec: PaymentRecommendation, cards: dict[str, Card], unlisted: bool = False) -> str:
    name = lambda cid: card_name(cid, cards)
    options = _join(f"your {name(c)}" for c in rec.card_options)
    reason = rec.reason_code
    if reason in ("eligible_sufficient_balance", "not_eligible", "no_health_card_linked", "routed_to_next_card"):
        lead = "No HSA or FSA card is linked, so " if reason == "no_health_card_linked" else ""
        if reason == "not_eligible" and not unlisted:
            return f"Please use your {name(rec.card_id)}, not an HSA or FSA card. Add it to your cart?"
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


def product_unresolved(request_id: str | None = None, warnings: Iterable[str] = ()) -> VoiceRequest:
    """Nothing usable was found. Say what to do about it: one item, more light, less glare, or hold still."""
    w = set(warnings)
    if "E_MULTIPLE_PRODUCTS" in w:
        text = "I see more than one item. Please hold up just one item in front of the camera."
    elif "E_TOO_DARK" in w:
        text = "It is too dark to read this. I'll turn on the light. Please hold the item steady."
    elif "E_GLARE" in w:
        text = "There is glare on the label. Tilt the item a little and hold it steady."
    elif "E_BLURRY" in w:
        text = "The picture is blurry. Please hold the item still for a moment."
    else:
        text = "I do not see an item in the frame. Please hold the item steady in front of the camera."
    return _request(text, request_id=request_id)


def compose_speech(
    product: ProductResolution,
    elig: EligibilityResult,
    rec: PaymentRecommendation | None,
    cards: Iterable[Card | dict[str, Any]] | None = None,
    prompt_id: str | None = None,
    request_id: str | None = None,
    already_in_cart: bool = False,
) -> VoiceRequest:
    """The line spoken after a scan: product, price, eligibility, then the card to pay with."""
    if product.amount_cents is None:
        text = (f"I read {product.name}. {eligibility_line(product, elig)} "
                "I could not read the price. Please move closer to the price tag.")
        return _request(text, request_id=request_id)

    by_id = _cards_by_id(cards)
    unlisted = is_unlisted(elig)
    parts = [f"{product.name}, {money(product.amount_cents)}."]
    if "E_TAG_NEIGHBOUR" in product.warnings:
        parts.append("The shelf tag may belong to another item, so this is a typical price.")
    if already_in_cart:
        parts.append("You already have one in your cart.")
    if line := eligibility_line(product, elig):
        parts.append(line)
    if rec is not None:
        line = _card_line(rec, by_id, unlisted)
        parts.append(line.replace("Add it to your cart?", "Add another one?") if already_in_cart else line)
    scope = scope_for(rec)
    # Not HSA/FSA eligible is an alert: the shopper should not put it on a health card.
    priority = "alert" if elig.label == "not_eligible" and not unlisted else "normal"
    return _request(" ".join(parts), scope=scope, priority=priority,
                    prompt_id=prompt_id if scope != "none" else None, request_id=request_id)


# --- the cart --------------------------------------------------------------------------------------

def item_added(name: str, card_id: str | None, cards: Iterable[Card | dict[str, Any]] | None = None) -> VoiceRequest:
    return _request(f"Added {name} to your {card_name(card_id, _cards_by_id(cards))}.")


def item_removed(name: str | None) -> VoiceRequest:
    return _request(f"Removed {name}." if name else "Your cart is already empty.")


def confirm_clear(prompt_id: str | None = None) -> VoiceRequest:
    return _request("Clear everything from your cart?", scope="confirm_clear_cart", prompt_id=prompt_id)


def which_card(card_ids: Iterable[str], cards: Iterable[Card | dict[str, Any]],
               prompt_id: str | None = None) -> VoiceRequest:
    by_id = _cards_by_id(cards)
    options = _join(f"your {card_name(c, by_id)}" for c in card_ids)
    return _request(f"Which card would you like to use: {options}?", scope="choose_card", prompt_id=prompt_id)


def card_not_allowed(card_ids: Iterable[str], cards: Iterable[Card | dict[str, Any]],
                     prompt_id: str | None = None) -> VoiceRequest:
    """The user named a card that cannot take this item. Say only that, then ask again."""
    by_id = _cards_by_id(cards)
    options = _join(f"your {card_name(c, by_id)}" for c in card_ids)
    return _request(f"I could not confirm eligibility for that card. Please use another card for this item: "
                    f"{options}?", scope="choose_card", prompt_id=prompt_id)


def skipped(skip: bool = True) -> VoiceRequest:
    return _request("Okay, skipped." if skip else "Okay.")


def open_accessibility() -> VoiceRequest:
    return _request("Opening accessibility settings.")


def nothing_to_repeat() -> VoiceRequest:
    return _request("I haven't said anything yet.")


def no_card_checkout() -> VoiceRequest:
    return _request("No card is linked, so I can't check out. Please add a card in the app.")


def cart_cleared() -> VoiceRequest:
    return _request("Your cart is empty.")


def cart_contents(items: list[dict[str, Any]],
                  cards: Iterable[Card | dict[str, Any]] | None = None) -> VoiceRequest:
    """The cart grouped by card (spec 3.8) with the total before tax."""
    if not items:
        return _request("Your cart is empty.")
    by_id = _cards_by_id(cards)
    total = sum(i["amount_cents"] for i in items)
    count = f"{len(items)} item" + ("" if len(items) == 1 else "s")
    lines: list[str] = []
    for card_id in dict.fromkeys(i["assigned_card_id"] for i in items):
        for n, item in enumerate(i for i in items if i["assigned_card_id"] == card_id):
            lead = f"On your {card_name(card_id, by_id)}: " if n == 0 and by_id else ""
            lines.append(f"{lead}{item['display_name']}, {money(item['amount_cents'])}.")
    return _request(f"You have {count}, {money(total)} before tax. {' '.join(lines)}")


def balance_refusal() -> VoiceRequest:
    return _request(BALANCE_REFUSAL)


# --- checkout --------------------------------------------------------------------------------------

def _group_lines(groups: Iterable[Any], cards: dict[str, Card]) -> str:
    return _join(f"{money(g.subtotal_cents)} on your {card_name(g.card_id, cards)}"
                 for g in groups if g.subtotal_cents > 0)


def _split_line(total_cents: int, groups: list[Any], cards: dict[str, Card]) -> str:
    """"$23.47 before tax: $18.48 on your FSA card and ..." or, for one card, "$12.99 before tax, on your FSA card"."""
    paid = [g for g in groups if g.subtotal_cents > 0]
    if len(paid) == 1:
        return f"{money(total_cents)} before tax, on your {card_name(paid[0].card_id, cards)}"
    return f"{money(total_cents)} before tax: {_group_lines(paid, cards)}"


def checkout_preview(
    plan: CheckoutPlan,
    cards: Iterable[Card | dict[str, Any]],
    items: list[dict[str, Any]],
    prompt_id: str | None = None,
    prefix: str = "",
) -> VoiceRequest:
    by_id = _cards_by_id(cards)
    names = {i["id"]: i["display_name"] for i in items}
    if not plan.groups or plan.total_cents == 0:
        return _request("Your cart is empty, so there is nothing to check out.")
    if plan.ok:
        text = f"Your total is {_split_line(plan.total_cents, plan.groups, by_id)}. Ready to check out?"
        return _request(prefix + text, scope="confirm_checkout", prompt_id=prompt_id)

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
    askable = any(i.moves for i in plan.issues) and not any(i.uncovered_item_ids for i in plan.issues)
    if askable:
        parts.append("Is that okay?")
    return _request(prefix + " ".join(parts), scope="confirm_checkout" if askable else "none",
                    prompt_id=prompt_id if askable else None)


def checkout_result(
    groups: Iterable[Any],
    cards: Iterable[Card | dict[str, Any]],
    low_balance_card_ids: Iterable[str] = (),
) -> VoiceRequest:
    """After a confirmed checkout. Plain and polite; a small balance is never flagged (team decision
    2026-10-24), so low_balance_card_ids is accepted for older callers and not spoken."""
    by_id = _cards_by_id(cards)
    groups = [g for g in groups if g.subtotal_cents > 0]
    total = sum(g.subtotal_cents for g in groups)
    return _request(f"Thank you. Your simulated payment went through: {_split_line(total, groups, by_id)}. "
                    "Please remember to take your items with you. Your receipt is saved in History.")


def low_balance_alert(card_id: str, cards: Iterable[Card | dict[str, Any]]) -> VoiceRequest:
    return _request(LOW_BALANCE.format(card=card_name(card_id, _cards_by_id(cards))), priority="alert")


# --- prescription label read-back (tech spec 2.3) -------------------------------------------------

def strength_question(name: str, strength: str | None, prompt_id: str | None = None) -> VoiceRequest:
    """Read the drug name and strength back. Nothing proceeds until the user confirms."""
    what = f"{name}, {strength}" if strength else name
    return _request(f"This label says {what}. Is this the right medicine and strength?", scope="confirm_strength",
                    prompt_id=prompt_id)


def strength_confirmed(name: str, strength: str | None, insurer_tip: str | None = None) -> VoiceRequest:
    """No copay figure for the member: the pharmacy's claim decides. `insurer_tip` is the mock plan
    sentence from payments/insurers.py (typical generic copay, ask the pharmacist to confirm)."""
    what = f"{name}, {strength}" if strength else name
    if insurer_tip:
        return _request(f"Thank you. {what}. {insurer_tip} Copays are usually HSA eligible. "
                        "Please also ask the pharmacist about dosage or safety.")
    return _request(f"Thank you. {what}. The pharmacist will tell you your share, and copays are usually "
                    "HSA eligible. Please ask the pharmacist about dosage or safety.")


def strength_retry() -> VoiceRequest:
    return _request("Okay. Please hold the label closer to the camera and I'll read it again.")


# --- purchase history (PROPOSED) ---------------------------------------------------------------------

def history_opened() -> VoiceRequest:
    return _request("Here is your purchase history. Scroll to see every receipt.")


def history_closed() -> VoiceRequest:
    return _request("Closing your purchase history.")


# --- reviewing one cart item (PROPOSED: tap an item in the cart) -----------------------------------

def review_item(name: str, amount_cents: int, prompt_id: str | None = None) -> VoiceRequest:
    return _request(f"{name}, {money(amount_cents)}. Do you want to remove it from your cart?",
                    scope="confirm_remove_item", prompt_id=prompt_id)


def review_gone() -> VoiceRequest:
    return _request("That item is no longer in your cart.")


def review_rest(prefix: str, remaining: int, prompt_id: str | None = None) -> VoiceRequest:
    word = ["no", "one", "two", "three", "four", "five"][remaining] if remaining <= 5 else str(remaining)
    items = "item" if remaining == 1 else "items"
    them = "it" if remaining == 1 else "them"
    return _request(f"{prefix} You also have {word} other {items}. Would you like to check {them} too?".strip(),
                    scope="confirm_review_rest", prompt_id=prompt_id)


def review_done(prefix: str = "Okay.") -> VoiceRequest:
    return _request(f"{prefix} Let me know when you're ready to check out.".strip())


# --- store check-in (PROPOSED, prototype) ------------------------------------------------------------

def checkin_question(name: str, address: str, prompt_id: str | None = None) -> VoiceRequest:
    return _request(f"Are you at {name}, {address}? Say yes to check in.", scope="confirm_checkin",
                    prompt_id=prompt_id)


def checked_in(name: str, address: str) -> VoiceRequest:
    return _request(f"You're checked in at {name}, {address}. "
                    "Please point your camera at an item to start shopping.")


def checkin_declined() -> VoiceRequest:
    return _request("Okay. You can still scan items.")
