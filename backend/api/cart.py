"""Cart and card endpoints (technical spec 0.6)."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

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


@router.get("/cards")
def get_cards() -> list[dict]:
    return [{k: c[k] for k in ("id", "type", "nickname", "balance_cents", "status")} for c in db.get_cards()]


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
