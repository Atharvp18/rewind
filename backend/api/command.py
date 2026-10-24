"""POST /v1/command: turn a spoken transcript into an action (technical spec 3.8).

A deterministic keyword matcher, not a model call, so the same words always do the same thing.
A "yes" only acts through a live prompt_id; with none, it is E_PROMPT_EXPIRED and the app asks
again. Anything that spends or removes is read back in the reply.
"""
from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

from api import memory
from api.envelope import ApiError
from data import db
from payments import cart_store, checkout, nessie
from speech import compose

router = APIRouter(prefix="/v1")

MIN_CONFIDENCE = 0.5       # applies only when the speech service reports a confidence


class Command(BaseModel):
    transcript: str
    confidence: float | None = None
    prompt_id: str | None = None


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9' ]+", " ", text.lower()).strip()


def has(pattern: str, text: str) -> bool:
    return re.search(pattern, text) is not None


BALANCE = r"\bbalance\b|\bhow much (money|do i have|is left|left)\b"
REPEAT = r"\bagain\b|\brepeat\b"
CLEAR = r"\b(clear|empty)\b.*\bcart\b"
REMOVE = r"\b(remove|delete|undo)\b|\btake (that|it|the last \w+) off\b"
ACCESSIBILITY = r"\baccessibility\b"
CHECKOUT = r"\bcheck ?out\b|\bpay\b|\bi'?m done\b"
CART = r"\bcart\b"
NO = r"^(no|nope|nah|skip|cancel|stop)\b|\bskip (it|that|this)\b|\bnever ?mind\b|\bdon'?t\b|\bnot now\b"
YES = (r"^(yes|yeah|yep|yup|sure|ok|okay|please|correct|right|confirm)\b|\badd (that|it|this)\b"
       r"|\bgo ahead\b|\bdo it\b|\bthat'?s right\b")
CARD_WORDS = {"hsa": "hsa", "fsa": "fsa", "visa": "general", "credit": "general", "general": "general"}


def named_card(text: str, cards: list[dict]) -> str | None:
    """The card id the user named, e.g. "put it on my visa", or None."""
    for word, card_type in CARD_WORDS.items():
        if has(rf"\b{word}\b", text):
            matches = [c for c in cards if c["type"] == card_type and c["status"] == "active"]
            if card_type == "general" or len(matches) == 1:
                return matches[0]["id"] if matches else None
            return next((c["id"] for c in matches if c["is_default"]), matches[0]["id"] if matches else None)
    return None


def reply(action: str, voice, **result: Any) -> dict:
    return {"action": action, "result": result, "voice": memory.remember(voice)}


@router.post("/command")
def command(body: Command, background: BackgroundTasks) -> dict:
    if body.confidence is not None and body.confidence < MIN_CONFIDENCE:
        raise ApiError("E_STT_LOW_CONFIDENCE", "transcript below the confidence threshold")
    text = normalize(body.transcript)

    if has(BALANCE, text):
        return reply("balance_refused", compose.balance_refusal())
    if has(REPEAT, text):
        last = memory.last()
        return reply("repeat", last or compose.nothing_to_repeat())
    if has(CLEAR, text):
        return clear_cart_prompt()
    if has(REMOVE, text):
        removed, cart = cart_store.remove_last()
        return reply("remove_last", compose.item_removed(removed["display_name"] if removed else None), cart=cart)
    if has(ACCESSIBILITY, text):
        return reply("open_accessibility", compose.open_accessibility())
    if has(CHECKOUT, text):
        result = checkout.preview()
        return reply("checkout_preview", result.voice, total_cents=result.plan.total_cents if result.plan else 0)
    if has(CART, text):
        cart = db.get_cart()
        return reply("cart", compose.cart_contents(cart_store.flat_items(cart), db.get_cards()), cart=cart)
    if has(NO, text):
        return reply("skip", compose.skipped(skip=has(r"\bskip\b", text)))

    cards = db.get_cards()
    card_id = named_card(text, cards)
    if has(YES, text) or card_id:
        return act_on_prompt(body.prompt_id, card_id, cards, background)
    raise ApiError("E_STT_LOW_CONFIDENCE", "transcript did not match a command")


def clear_cart_prompt() -> dict:
    if not db.get_cart()["groups"]:
        return reply("clear_cart", compose.cart_cleared())
    prompt_id = db.create_prompt("confirm_clear_cart", None, {})
    return reply("clear_cart_confirm", compose.confirm_clear(prompt_id), prompt_id=prompt_id)


def act_on_prompt(prompt_id: str | None, card_id: str | None, cards: list[dict],
                  background: BackgroundTasks) -> dict:
    """A yes, or a card name, answering whatever question prompt_id belongs to."""
    if prompt_id:                                       # a checkout retried with the same prompt is idempotent
        existing = db.get_payment(f"command-{prompt_id}")
        if existing:
            done = checkout._result(existing, cards)
            return reply("checkout_confirm", done.voice, payment_id=existing["payment_id"])
    info = cart_store.consume(prompt_id, cart_store.ALL_SCOPES)
    scope = info["scope"]

    if scope == "confirm_checkout":
        done = checkout.charge(f"command-{prompt_id}", info)
        if done.ledger:
            background.add_task(nessie.log_withdrawals, done.ledger)
        return reply("checkout_confirm", done.voice,
                     payment_id=done.payment["payment_id"] if done.payment else None)
    if scope == "confirm_clear_cart":
        cart_store.clear(info)
        return reply("clear_cart", compose.cart_cleared(), cart=db.get_cart())

    # confirm_add or choose_card
    payload = info["payload"]
    if scope == "choose_card" and card_id is None:
        options = cart_store.allowed_cards(info, cards)
        if len(options) != 1:                           # a bare yes is not an answer to "which card?"
            return ask_again(info, options, cards, refused=False)
        card_id = options[0]
    try:
        cart, used, _ = cart_store.add_item(info, card_id)
    except ApiError:
        return ask_again(info, cart_store.allowed_cards(info, cards), cards, refused=True)
    return reply("add_to_cart", compose.item_added(payload["display_name"], used, cards), cart=cart)


def ask_again(info: dict, options: list[str], cards: list[dict], refused: bool) -> dict:
    """Put the question back with a fresh prompt: the old one was used up answering it."""
    payload = dict(info["payload"], card_options=options)
    prompt_id = db.create_prompt("choose_card", info["scan_id"], payload)
    voice = (compose.card_not_allowed if refused else compose.which_card)(options, cards, prompt_id)
    return reply("choose_card", voice, prompt_id=prompt_id)
