"""Nak's app speaks a slightly different contract from these routers. This translates at the edge.

Only requests that send `X-Rewind-Client: app` are translated, so every other caller (the tests,
the Fetch.ai agents, curl) sees the routers' own replies unchanged. main.py installs it.

What changes for the app:
- /v1/command: action names (add_to_cart -> add_item, cart -> read_cart, ...) and `result` is the
  object the app expects (a cart, a preview, a receipt, a store) instead of {cart: ...}.
- /v1/checkout/preview: groups carry their items, like the cart.
- /v1/checkout/confirm: the receipt shape (groups with items, new_balances by card_id, and the
  History invoice).
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from data import db
from payments import cart_store, invoice

HEADER = "x-rewind-client"
PATHS = ("/v1/command", "/v1/checkout/preview", "/v1/checkout/confirm")

ACTIONS = {
    "add_to_cart": "add_item",
    "clear_cart": "cart_cleared",
    "clear_cart_confirm": "confirm_clear_cart",
    "cart": "read_cart",
    "checkout_confirm": "checkout_confirmed",
    "open_accessibility": "open_settings",
}


def preview_groups(groups: list[dict]) -> list[dict]:
    """CheckoutGroup (item_ids) -> the app's CartGroup (items), from the current cart."""
    by_id = {i["id"]: i for i in cart_store.flat_items(db.get_cart())}
    out = []
    for g in groups:
        rows = [by_id[i] for i in g.get("item_ids", []) if i in by_id]
        out.append({"card_id": g["card_id"], "nickname": g["nickname"], "subtotal_cents": g["subtotal_cents"],
                    "items": [{k: r[k] for k in ("id", "scan_id", "display_name", "amount_cents", "eligibility_label")
                               if k in r} for r in rows]})
    return out


def preview(body: dict) -> dict:
    return {**body, "groups": preview_groups(body.get("groups", []))}


def receipt(payment_id: str | None, voice: dict) -> dict | None:
    """The app's CheckoutResult for a saved payment, or None when nothing was charged."""
    payment = db.get_payment_by_id(payment_id) if payment_id else None
    if payment is None:
        return None
    cards = db.get_cards()
    return {
        "payment_id": payment["payment_id"],
        "groups": invoice.cart_groups(payment, cards),
        "new_balances": [{"card_id": b["id"], "balance_cents": b["balance_cents"]} for b in payment["new_balances"]],
        "invoice": invoice.history_invoice(payment, cards),
        "voice": voice,
    }


def command(body: dict) -> dict:
    action, result, voice = body["action"], body.get("result") or {}, body["voice"]
    out: dict[str, Any] = {"action": ACTIONS.get(action, action), "voice": voice, "result": None}
    if action == "checkout_preview":
        out["result"] = {"groups": preview_groups(result.get("groups", [])), "total_cents": result.get("total_cents", 0),
                         "issues": result.get("issues", []), "voice": voice}
    elif action == "checkout_confirm":
        done = receipt(result.get("payment_id"), voice)
        # nothing charged (the cart or balances changed): the voice re-asks with a fresh prompt
        out.update(action="checkout_confirmed", result=done) if done else out.update(action="unknown")
    elif "cart" in result:
        out["result"] = result["cart"]
    elif "store" in result:
        out["result"] = result["store"]
    if "item_id" in result:
        out["item_id"] = result["item_id"]
    return out


def translate(path: str, body: dict) -> dict:
    if path == "/v1/command":
        return command(body)
    if path == "/v1/checkout/preview":
        return preview(body)
    return receipt(body.get("payment_id"), body["voice"]) or body


async def middleware(request: Request, call_next):
    response = await call_next(request)
    if (request.headers.get(HEADER) != "app" or request.url.path not in PATHS
            or response.status_code != 200 or response.headers.get("content-type") != "application/json"):
        return response
    raw = b"".join([chunk async for chunk in response.body_iterator])
    body = await run_in_threadpool(translate, request.url.path, json.loads(raw))
    headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
    return JSONResponse(body, status_code=200, headers=headers, background=response.background)
