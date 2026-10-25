"""The only module that talks to Supabase (technical spec 3.1).

Everything else imports from here: the API layer, Tiea's lookup and eligibility modules, and
the offline prefetch. No Supabase call and no SQL appears anywhere else.

Money is integer cents. Every call has a 1.5 s budget and one retry; after that it raises
DBUnavailable (E_DB_UNAVAILABLE). Atomic work (prompts, checkout, reset) is a Postgres function
in functions.sql, called through rpc().
"""
from __future__ import annotations

import logging
import os
import re
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Callable

import httpx
from dotenv import load_dotenv
from postgrest.exceptions import APIError
from supabase import Client, ClientOptions, create_client

logger = logging.getLogger(__name__)

DB_TIMEOUT_S = 1.5          # per attempt (spec 0.7: other Supabase reads and writes)
DB_ATTEMPTS = 2             # one retry
BULK_CHUNK = 500
PROMPT_TTL_SECONDS = 15
# The app's "Time to answer" setting for this request (15, 30 or 60 s), set by main.py from the
# X-Rewind-Prompt-TTL header. None means the default above.
REQUEST_PROMPT_TTL: ContextVar[int | None] = ContextVar("REQUEST_PROMPT_TTL", default=None)

_CACHE_COLUMNS = (
    "upc", "normalized_name", "brand", "size", "category", "shelf_price_cents",
    "eligibility_label", "eligibility_confidence", "eligibility_basis", "source",
)
_ELIGIBILITY_COLUMNS = (
    "product_key", "upc", "name", "brand", "size", "category_path",
    "eligible", "source_url", "collected_at", "basis",
)
_CART_COLUMNS = (
    "id", "scan_id", "product_key", "display_name", "amount_cents", "amount_basis",
    "assigned_card_id", "eligibility_label", "user_overrode_card",
)


class DBUnavailable(Exception):
    """Supabase failed or exceeded its budget. Maps to E_DB_UNAVAILABLE."""


class PromptExpired(Exception):
    """Unknown, expired, already used, or wrong-scope prompt. Maps to E_PROMPT_EXPIRED."""


class CheckoutFailed(Exception):
    """The checkout function refused. `code` is the E_* prefix raised in functions.sql."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code


_client: Client | None = None


def _sb() -> Client:
    global _client
    if _client is None:
        load_dotenv()
        url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_KEY")
        if not url or not key:
            raise DBUnavailable("SUPABASE_URL and SUPABASE_SERVICE_KEY are not set")
        _client = create_client(url, key, ClientOptions(postgrest_client_timeout=DB_TIMEOUT_S))
    return _client


def _call(fn: Callable[[], Any]) -> Any:
    """Run one Supabase request with a retry on transport errors.

    Transport failures (timeout, connection reset) are retried once and then become
    DBUnavailable. A database error (APIError: bad data, constraint, raised exception) is a real
    answer, not an outage, so it propagates untouched and is never retried.
    """
    last: Exception | None = None
    for attempt in range(1, DB_ATTEMPTS + 1):
        try:
            return fn()
        except httpx.HTTPError as e:
            last = e
            logger.warning("Supabase attempt %d/%d failed: %s", attempt, DB_ATTEMPTS, type(e).__name__)
    raise DBUnavailable(f"Supabase unreachable: {type(last).__name__}") from last


def _rpc(name: str, params: dict) -> Any:
    return _call(lambda: _sb().rpc(name, params).execute()).data


def _cents(value: Any, field: str) -> int:
    """Reject floats and bools: a float in a money field is a bug even if the demo passes."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field} must be an integer number of cents, got {value!r}")
    return value


def _pick(row: dict, columns: tuple[str, ...]) -> dict:
    return {c: row[c] for c in columns if c in row}


# --- health ---------------------------------------------------------------------------------

def health() -> dict:
    """{reachable, latency_ms}. Single attempt, never raises."""
    t0 = time.perf_counter()
    try:
        _sb().table("cards").select("id").limit(1).execute()
        return {"reachable": True, "latency_ms": round((time.perf_counter() - t0) * 1000)}
    except Exception as e:  # noqa: BLE001 - health must never raise
        return {"reachable": False, "latency_ms": round((time.perf_counter() - t0) * 1000),
                "error": type(e).__name__}


# --- cards ----------------------------------------------------------------------------------

def get_cards() -> list[dict]:
    return _call(lambda: _sb().table("cards").select("*").order("id").execute()).data


# --- product cache (Tiea's lookup chain) ---------------------------------------------------

def cache_get(product_key: str) -> dict | None:
    rows = _call(lambda: _sb().table("product_cache").select("*")
                 .eq("product_key", product_key).limit(1).execute()).data
    return rows[0] if rows else None


def cache_put(product_key: str, row: dict) -> None:
    record = _pick(row, _CACHE_COLUMNS)
    if record.get("shelf_price_cents") is not None:
        _cents(record["shelf_price_cents"], "shelf_price_cents")
    record["product_key"] = product_key
    # Set explicitly: an upsert that omits last_updated would keep the old timestamp,
    # and Tiea's 24 hour price-freshness check reads this column.
    record["last_updated"] = datetime.now(timezone.utc).isoformat()
    _call(lambda: _sb().table("product_cache").upsert(record, on_conflict="product_key").execute())


# --- eligibility rows (Tiea's classifier and offline prefetch) ----------------------------

def eligibility_lookup_upc(upc: str) -> dict | None:
    """Exact UPC match in eligibility_items. Newest collection wins if a UPC appears twice."""
    digits = re.sub(r"\D", "", upc or "")
    if not digits:
        return None
    rows = _call(lambda: _sb().table("eligibility_items").select("*").eq("upc", digits)
                 .order("collected_at", desc=True).limit(1).execute()).data
    return rows[0] if rows else None


def eligibility_bulk_insert(rows: list[dict]) -> int:
    """Upsert rows by product_key; returns how many distinct rows were written."""
    by_key: dict[str, dict] = {}
    for row in rows:
        record = _pick(row, _ELIGIBILITY_COLUMNS)
        if not record.get("product_key"):
            raise ValueError(f"eligibility row has no product_key: {row!r}")
        by_key[record["product_key"]] = record          # an upsert batch cannot repeat a key
    records = list(by_key.values())
    for i in range(0, len(records), BULK_CHUNK):
        chunk = records[i:i + BULK_CHUNK]
        _call(lambda chunk=chunk: _sb().table("eligibility_items")
              .upsert(chunk, on_conflict="product_key").execute())
    return len(records)


def eligibility_delete(product_keys: list[str]) -> None:
    """Remove rows by product_key (used to clear retired placeholder rows)."""
    if product_keys:
        _call(lambda: _sb().table("eligibility_items").delete().in_("product_key", product_keys).execute())


# --- scans ----------------------------------------------------------------------------------

def save_scan(scan_id: str, product: dict, eligibility: dict) -> None:
    record = {
        "scan_id": scan_id,
        "state": product.get("state", "unresolved"),
        "product_json": product,
        "eligibility_json": eligibility,
    }
    _call(lambda: _sb().table("scans").upsert(record, on_conflict="scan_id").execute())


def get_scan(scan_id: str) -> dict | None:
    """The saved scan: {scan_id, state, product_json, eligibility_json}, or None."""
    rows = _call(lambda: _sb().table("scans").select("*").eq("scan_id", scan_id).limit(1).execute()).data
    return rows[0] if rows else None


# --- cart -----------------------------------------------------------------------------------

def get_cart() -> dict:
    """{groups:[{card_id, nickname, items, subtotal_cents}], total_cents}, items in add order."""
    items = _call(lambda: _sb().table("cart_items").select("*").order("seq").execute()).data
    cards = get_cards()
    groups = []
    for card in cards:
        card_items = [i for i in items if i["assigned_card_id"] == card["id"]]
        if card_items:
            groups.append({
                "card_id": card["id"],
                "nickname": card["nickname"],
                "items": card_items,
                "subtotal_cents": sum(i["amount_cents"] for i in card_items),
            })
    return {"groups": groups, "total_cents": sum(g["subtotal_cents"] for g in groups)}


def add_cart_item(scan_id: str, product_key: str, display_name: str, amount_cents: int,
                  amount_basis: str, assigned_card_id: str, eligibility_label: str,
                  user_overrode_card: bool = False, item_id: str | None = None) -> dict:
    """Insert one item and return the updated cart. item_id lets a caller keep its own id."""
    record = {
        "id": item_id or uuid.uuid4().hex,
        "scan_id": scan_id,
        "product_key": product_key,
        "display_name": display_name,
        "amount_cents": _cents(amount_cents, "amount_cents"),
        "amount_basis": amount_basis,
        "assigned_card_id": assigned_card_id,
        "eligibility_label": eligibility_label,
        "user_overrode_card": user_overrode_card,
    }
    _call(lambda: _sb().table("cart_items").insert(_pick(record, _CART_COLUMNS)).execute())
    return get_cart()


def reassign_cart_item(item_id: str, card_id: str, user_overrode_card: bool = True) -> None:
    """Move one item to another card (the checkout reroute in spec 4.4)."""
    _call(lambda: _sb().table("cart_items")
          .update({"assigned_card_id": card_id, "user_overrode_card": user_overrode_card})
          .eq("id", item_id).execute())


def remove_last_cart_item() -> dict:
    """Remove the most recently added item (highest seq) and return the updated cart."""
    _rpc("remove_last_cart_item", {})
    return get_cart()


def pop_last_cart_item() -> tuple[dict | None, dict]:
    """Remove the most recently added item. Returns (the removed row or None, the updated cart)."""
    removed = _rpc("remove_last_cart_item", {})
    return (removed or None), get_cart()


def remove_cart_item(item_id: str) -> tuple[dict | None, dict]:
    """Remove one item by id. Returns (the removed row or None, the updated cart)."""
    rows = _call(lambda: _sb().table("cart_items").delete().eq("id", item_id).execute()).data
    return (rows[0] if rows else None), get_cart()


def clear_cart() -> None:
    _call(lambda: _sb().table("cart_items").delete().neq("id", "").execute())


# --- purchase history (the History agent reads this) ---------------------------------------

def get_purchases(since: str | None = None, until: str | None = None,
                  card_type: str | None = None, payment_id: str | None = None) -> list[dict]:
    """Purchased items, newest first. since/until are ISO timestamps; card_type is hsa, fsa or general."""
    def run():
        q = _sb().table("purchase_items").select("*")
        if since:
            q = q.gte("purchased_at", since)
        if until:
            q = q.lt("purchased_at", until)
        if card_type:
            q = q.eq("card_type", card_type)
        if payment_id:
            q = q.eq("payment_id", payment_id)
        return q.order("purchased_at", desc=True).execute()
    return _call(run).data


# --- prompts (15 s, single use, scope-bound) ----------------------------------------------

def prompt_ttl(ttl_seconds: int | None = None) -> int:
    return ttl_seconds or REQUEST_PROMPT_TTL.get() or PROMPT_TTL_SECONDS


def create_prompt(scope: str, scan_id: str | None, payload: dict | None,
                  ttl_seconds: int | None = None) -> str:
    ttl_seconds = prompt_ttl(ttl_seconds)
    prompt_id = uuid.uuid4().hex
    _rpc("create_prompt", {"p_prompt_id": prompt_id, "p_scope": scope, "p_scan_id": scan_id,
                           "p_payload": payload or {}, "p_ttl_seconds": ttl_seconds})
    return prompt_id


def consume_prompt(prompt_id: str, expected_scope: str) -> dict:
    """Atomically mark the prompt used. Raises PromptExpired for any reason it cannot be."""
    result = _rpc("consume_prompt", {"p_prompt_id": prompt_id, "p_scope": expected_scope})
    if not result:
        raise PromptExpired(prompt_id)
    return result


# --- checkout and reset (atomic, in Postgres) ---------------------------------------------

def get_payment(idempotency_key: str) -> dict | None:
    """The payment already recorded for this key, in confirm_checkout's return shape, or None."""
    rows = _call(lambda: _sb().table("payments").select("*")
                 .eq("idempotency_key", idempotency_key).limit(1).execute()).data
    if not rows:
        return None
    row = rows[0]
    balances = [{"id": c["id"], "nickname": c["nickname"], "balance_cents": c["balance_cents"]}
                for c in get_cards()]
    return {"payment_id": row["payment_id"], "total_cents": row["total_cents"],
            "splits": row["splits_json"], "new_balances": balances, "replayed": True,
            "created_at": row.get("created_at")}


def list_payments(limit: int = 50) -> list[dict]:
    """Completed payments, newest first, in get_payment's shape (without new_balances)."""
    rows = _call(lambda: _sb().table("payments").select("*").eq("status", "simulated_complete")
                 .order("created_at", desc=True).limit(limit).execute()).data
    return [{"payment_id": r["payment_id"], "total_cents": r["total_cents"], "splits": r["splits_json"],
             "created_at": r.get("created_at")} for r in rows]


def link_card(card_type: str, nickname: str, last4: str | None, network: str | None) -> dict:
    """Link a card the user photographed. Needs data/migration_card_details.sql.

    The demo keeps one card per type: linking an HSA updates the seeded HSA card (its demo balance
    stays), so the seeded runs still work. A type with no card yet gets a new row.
    """
    details = {"nickname": nickname, "last4": last4, "network": network}
    cards = get_cards()
    same = next((c for c in cards if c["type"] == card_type), None)
    if same:
        _call(lambda: _sb().table("cards").update(details).eq("id", same["id"]).execute())
        card_id = same["id"]
    else:
        card_id = f"card_{card_type}_{len(cards) + 1}"
        row = {"id": card_id, "type": card_type, "balance_cents": NEW_CARD_BALANCE_CENTS[card_type],
               "status": "active", "is_default": False, **details}
        _call(lambda: _sb().table("cards").insert(row).execute())
    return next(c for c in get_cards() if c["id"] == card_id)


# Demo balance for a card type that had no seeded card (all simulated money).
NEW_CARD_BALANCE_CENTS = {"hsa": 34000, "fsa": 2500, "general": 500000}


def get_payment_by_id(payment_id: str) -> dict | None:
    """Same shape as get_payment, found by payment_id (for re-showing an invoice)."""
    rows = _call(lambda: _sb().table("payments").select("idempotency_key").eq("payment_id", payment_id)
                 .limit(1).execute()).data
    return get_payment(rows[0]["idempotency_key"]) if rows else None


def confirm_checkout(idempotency_key: str, splits: list[dict]) -> dict:
    """Simulated payment. splits = [{"card_id": ..., "amount_cents": ..., "items": [...]}].

    `items` is optional: the cart rows paid by that card, kept in splits_json so the invoice can be
    shown again later (checkout empties the cart). Postgres only reads card_id and amount_cents.

    A repeated idempotency_key returns the original payment with replayed=True and charges
    nothing. Raises CheckoutFailed if any card cannot pay; nothing is changed in that case.
    """
    clean = []
    for s in splits:
        row = {"card_id": s["card_id"], "amount_cents": _cents(s["amount_cents"], "amount_cents")}
        if s.get("items"):
            for item in s["items"]:
                _cents(item["amount_cents"], "item amount_cents")
            row["items"] = s["items"]
        clean.append(row)
    try:
        return _rpc("confirm_checkout", {"p_idempotency_key": idempotency_key, "p_splits": clean})
    except APIError as e:
        message = e.message or ""
        code, _, detail = message.partition(":")
        if code.startswith("E_"):
            raise CheckoutFailed(code.strip(), detail.strip()) from e
        raise


def reset_demo(run: int = 1) -> dict:
    """Restore the seed state in one transaction. Returns {cards, cart}."""
    from data.seed import reset_payload, seeded_details   # imported here so db.py stays importable on its own

    _rpc("reset_demo", reset_payload(run))
    # The Postgres function does not write last4 / network (they came later, migration_card_details.sql),
    # so the seeded FSA card gets its demo details here. Scanned cards keep theirs.
    for card_id, details in seeded_details().items():
        _call(lambda: _sb().table("cards").update(details).eq("id", card_id).execute())
    return {"cards": get_cards(), "cart": get_cart()}
