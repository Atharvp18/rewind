"""Cart and card endpoints (technical spec 0.6)."""
from __future__ import annotations

from fastapi import APIRouter
from typing import Literal

from pydantic import BaseModel, Field

from api import memory
from api.envelope import ApiError
from data import db
from payments import cart_store
from speech import compose

router = APIRouter(prefix="/v1")


class AddItem(BaseModel):
    scan_id: str
    card_id: str | None = None
    prompt_id: str


class ClearCart(BaseModel):
    prompt_id: str


CARD_FIELDS = ("id", "type", "nickname", "balance_cents", "status")


def public_card(c: dict) -> dict:
    # last4 and network exist once data/migration_card_details.sql has run
    return {**{k: c[k] for k in CARD_FIELDS}, "last4": c.get("last4"), "network": c.get("network")}


class LinkCard(BaseModel):
    type: Literal["hsa", "fsa", "general"]
    nickname: str = Field(min_length=1, max_length=40)
    last4: str | None = Field(None, pattern=r"^[0-9]{4}$")
    network: Literal["visa", "mastercard", "amex", "discover", "other"] | None = None


@router.get("/cards")
def get_cards() -> list[dict]:
    return [public_card(c) for c in db.get_cards()]


@router.post("/cards")
def link_card(body: LinkCard) -> dict:
    """PROPOSED: link a card the user photographed at onboarding (only the last 4 digits are kept)."""
    return public_card(db.link_card(body.type, body.nickname, body.last4, body.network))


@router.post("/cart/items/{item_id}/review")
def review_item(item_id: str) -> dict:
    """PROPOSED: the user tapped an item. Read it back and ask whether to remove it.

    The answer goes to POST /v1/command with the returned prompt (scope confirm_remove_item).
    """
    cart = db.get_cart()
    item = next((i for i in cart_store.flat_items(cart) if i["id"] == item_id), None)
    if item is None:
        return {"cart": cart, "voice": memory.remember(compose.review_gone()), "item_id": None}
    prompt_id = db.create_prompt("confirm_remove_item", item.get("scan_id"),
                                 {"item_id": item_id, "reviewed": [item_id]})
    voice = compose.review_item(item["display_name"], item["amount_cents"], prompt_id)
    return {"cart": cart, "voice": memory.remember(voice), "item_id": item_id}


@router.get("/cart")
def get_cart() -> dict:
    return db.get_cart()


@router.post("/cart/items")
def add_item(body: AddItem) -> dict:
    info = cart_store.consume(body.prompt_id, cart_store.ADD_SCOPES)
    if info["scan_id"] != body.scan_id:
        raise ApiError("E_PROMPT_EXPIRED", "prompt belongs to a different scan")
    cart, card_id, payload = cart_store.add_item(info, body.card_id)
    voice = compose.item_added(payload["display_name"], card_id, db.get_cards())
    return {"cart": cart, "voice": memory.remember(voice)}


@router.delete("/cart/items/last")
def remove_last() -> dict:
    removed, cart = cart_store.remove_last()
    voice = compose.item_removed(removed["display_name"] if removed else None)
    return {"cart": cart, "voice": memory.remember(voice)}


@router.delete("/cart")
def clear_cart(body: ClearCart) -> dict:
    info = cart_store.consume(body.prompt_id, ("confirm_clear_cart",))
    cart_store.clear(info)
    return {"cart": db.get_cart(), "voice": memory.remember(compose.cart_cleared())}
