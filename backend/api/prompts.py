"""POST /v1/prompts/reissue: a fresh question for an item the user answered too late.

PROPOSED for tech spec 0.6 (Nak's app already calls it). A scan's yes / no prompt is single use
and expires (spec 0.7). When the user says "yes" after it expired, the app asks for a new prompt
for the same scan instead of making them scan the item again.

Routing runs again against today's balances, so a card that has run short since the scan is
skipped (FSA, then HSA, then the everyday card). The new prompt carries the same payload a scan
prompt does, so POST /v1/cart/items works with it unchanged.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.envelope import ApiError
from data import db
from models.schemas import EligibilityResult, ProductResolution
from payments import cart_store
from payments.routing import route_item
from speech import compose

router = APIRouter(prefix="/v1")

# The app's "Time to answer" setting (spec 1.2): 15, 30 or 60 seconds, sent on every request.
ALLOWED_TTL_S = (15, 30, 60)


class ReissueRequest(BaseModel):
    scan_id: str
    scope: Literal["confirm_add", "choose_card"]


class ReissueResponse(BaseModel):
    prompt_id: str
    expires_in_s: int
    # The scope the new prompt actually has. It can differ from the one asked for when the
    # balances changed (a single suggested card becomes a choice, or the other way round).
    scope: Literal["confirm_add", "choose_card"]


def ttl_from_header(value: str | None) -> int:
    try:
        seconds = int(value) if value is not None else db.PROMPT_TTL_SECONDS
    except ValueError:
        return db.PROMPT_TTL_SECONDS
    return seconds if seconds in ALLOWED_TTL_S else db.PROMPT_TTL_SECONDS


@router.post("/prompts/reissue", response_model=ReissueResponse)
def reissue(
    body: ReissueRequest,
    x_rewind_prompt_ttl: str | None = Header(None),
) -> ReissueResponse:
    saved = db.get_scan(body.scan_id)
    if saved is None:
        raise ApiError("E_NOT_FOUND", "unknown scan_id")
    product = ProductResolution(**saved["product_json"])
    elig = EligibilityResult(**saved["eligibility_json"])
    if product.state == "unresolved" or product.amount_cents is None:
        raise ApiError("E_BAD_REQUEST", "this scan has nothing to confirm")

    # Never ask again about an item that is already in the cart: a second yes would add it twice.
    cart = db.get_cart()
    if any(i.get("scan_id") == body.scan_id for g in cart["groups"] for i in g["items"]):
        raise ApiError("E_BAD_REQUEST", "this item is already in the cart")

    rec = route_item(elig.label, product.amount_cents, "shelf_price", db.get_cards(), scan_id=body.scan_id)
    scope = compose.scope_for(rec)
    if scope not in ("confirm_add", "choose_card"):
        raise ApiError("E_BAD_REQUEST", "no card can take this item")

    ttl = ttl_from_header(x_rewind_prompt_ttl)
    prompt_id = db.create_prompt(scope, body.scan_id, cart_store.prompt_payload(product, elig.label, rec),
                                 ttl_seconds=ttl)
    return ReissueResponse(prompt_id=prompt_id, expires_in_s=ttl, scope=scope)
