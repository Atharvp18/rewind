"""Capital One Nessie adapter (technical spec 3.10). One file, so a different API shape changes
one file. Treated as slow and untrusted: 2 s budget, no retries, and it never blocks the build.

Verified against the live API (2026-10-24):
  * Base URL https://prod-api.nessieisreal.com (https://api.nessieisreal.com also works; plain
    http is refused). The key is the `?key=` query parameter.
  * `balance` is an integer stored exactly as sent. The demo accounts are created in CENTS
    (34000 means $340.00); Nessie itself does not say what the unit is.
  * A balance NEVER changes after an account is created. Withdrawals and deposits are recorded
    but leave `balance` untouched, and PUT /accounts/{id} ignores `balance` (it only renames).
    Resetting a balance means deleting and recreating the account, which gives a new id.
So Nessie reports the starting balance of an account; it cannot follow spending. Anything that
needs the balance after a checkout must read Supabase (cards.balance_cents), not Nessie.

The key travels in the URL, so the httpx logger is silenced below INFO: at INFO it would write
the full request URL, key included, into the logs.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from pydantic import BaseModel, StrictInt

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

DEFAULT_BASE_URL = "https://prod-api.nessieisreal.com"
BUDGET_S = 2.0                      # spec 0.7: Nessie balance
_transport: httpx.AsyncBaseTransport | None = None      # tests inject a mock transport here

# last good Nessie balance per card id: (balance_cents, time.monotonic())
_last_known: dict[str, tuple[int, float]] = {}


class NessieUnavailable(Exception):
    """Nessie failed or exceeded its budget. Maps to E_NESSIE_UNAVAILABLE."""


class NessieAccount(BaseModel):
    id: str
    type: str
    nickname: str
    balance_cents: StrictInt


def _base_url() -> str:
    return (os.environ.get("NESSIE_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


def _demo_mode() -> bool:
    return os.environ.get("REWIND_DEMO_MODE", "").lower() == "true"


async def fetch_account(account_id: str, client: httpx.AsyncClient) -> NessieAccount:
    """GET /accounts/{id}. Raises NessieUnavailable; its message never contains the URL or key."""
    key = os.environ.get("NESSIE_API_KEY")
    if not key:
        raise NessieUnavailable("NESSIE_API_KEY is not set")
    try:
        response = await client.get(f"{_base_url()}/accounts/{account_id}", params={"key": key})
    except httpx.HTTPError as e:                          # timeouts, connection errors, bad URLs
        raise NessieUnavailable(f"request failed: {type(e).__name__}") from None
    if response.status_code != 200:
        raise NessieUnavailable(f"HTTP {response.status_code}")
    try:
        data = response.json()
        return NessieAccount(id=data["_id"], type=data["type"], nickname=data["nickname"],
                             balance_cents=data["balance"])
    except Exception as e:  # noqa: BLE001 - any shape surprise is "unavailable", not a crash
        raise NessieUnavailable(f"unexpected response: {type(e).__name__}") from None


class BalanceReport(BaseModel):
    cards: list[dict[str, Any]]       # the input cards, balance_cents replaced where Nessie answered
    degraded: bool                    # True when any linked card could not be read from Nessie
    warnings: list[str]               # ["E_NESSIE_UNAVAILABLE"] when degraded


async def get_balances_or_last_known(cards: list[dict[str, Any]]) -> BalanceReport:
    """Read each linked card's balance from Nessie, in parallel, inside one 2 s budget.

    A card is "linked" when it has a nessie_account_id. For each one:
      nessie      the live Nessie value (also remembered as the last known value)
      last_known  Nessie failed; the last good Nessie value from this process
      seeded      Nessie failed and nothing is remembered; the card row's own balance. Only
                  allowed when REWIND_DEMO_MODE=true, otherwise NessieUnavailable is raised.
    Cards with no nessie_account_id keep their own balance (source "seeded").
    Each returned card carries `balance_source`. See the module docstring: Nessie balances do
    not move when money is spent, so do not use this as the balance after a checkout.
    """
    linked = [c for c in cards if c.get("nessie_account_id")]
    fetched: dict[str, NessieAccount | NessieUnavailable] = {}

    if linked:
        async with httpx.AsyncClient(transport=_transport, timeout=BUDGET_S) as client:
            async def one(card: dict) -> None:
                try:
                    fetched[card["id"]] = await fetch_account(card["nessie_account_id"], client)
                except NessieUnavailable as e:
                    fetched[card["id"]] = e
            try:
                await asyncio.wait_for(asyncio.gather(*(one(c) for c in linked)), BUDGET_S)
            except asyncio.TimeoutError:
                pass                                       # unfinished cards fall through below
        for card in linked:
            fetched.setdefault(card["id"], NessieUnavailable("timed out"))

    degraded, out = False, []
    for card in cards:
        card = dict(card)
        result = fetched.get(card["id"])
        if isinstance(result, NessieAccount):
            _last_known[card["id"]] = (result.balance_cents, time.monotonic())
            card.update(balance_cents=result.balance_cents, balance_source="nessie")
        elif isinstance(result, NessieUnavailable):
            degraded = True
            logger.warning("Nessie unavailable for card %s: %s", card["id"], result)
            if card["id"] in _last_known:
                card.update(balance_cents=_last_known[card["id"]][0], balance_source="last_known")
            elif _demo_mode():
                card["balance_source"] = "seeded"
            else:
                raise NessieUnavailable(f"no balance for card {card['id']}: {result}") from None
        else:
            card["balance_source"] = "seeded"             # not linked to Nessie
        out.append(card)

    return BalanceReport(cards=out, degraded=degraded, warnings=["E_NESSIE_UNAVAILABLE"] if degraded else [])


# --- payment log -------------------------------------------------------------------------------------
# Nessie keeps a withdrawal list per account even though it never moves the balance (see the top of
# this file). Each simulated checkout writes one withdrawal per card it charged, so the payment is on
# record in Nessie. This is a log only: Supabase holds the balance, and nothing waits on this.

async def _post_withdrawal(client: httpx.AsyncClient, key: str, date: str, entry: dict) -> bool:
    body = {"medium": "balance", "transaction_date": date, "status": "completed",
            "amount": entry["amount_cents"], "description": entry["description"]}
    try:
        response = await client.post(f"{_base_url()}/accounts/{entry['account_id']}/withdrawals",
                                     params={"key": key}, json=body)
    except Exception as e:  # noqa: BLE001 - a log write must never raise into a payment
        logger.warning("Nessie payment log failed: %s", type(e).__name__)
        return False
    if response.status_code not in (200, 201):
        logger.warning("Nessie payment log failed: HTTP %s", response.status_code)
        return False
    return True


async def log_withdrawals(entries: list[dict]) -> list[bool]:
    """Record a completed checkout. entries = [{"account_id", "amount_cents", "description"}].

    Run it after the response is sent (BackgroundTasks). Never raises; returns one bool per entry,
    and an empty list when there is nothing to send or no key. Amounts are integer cents, the same
    unit the demo accounts' balances were created in.
    """
    key = os.environ.get("NESSIE_API_KEY")
    if not key or not entries:
        return []
    date = datetime.now(timezone.utc).date().isoformat()
    try:
        async with httpx.AsyncClient(timeout=BUDGET_S, transport=_transport) as client:
            return list(await asyncio.gather(*(_post_withdrawal(client, key, date, e) for e in entries)))
    except Exception as e:  # noqa: BLE001
        logger.warning("Nessie payment log failed: %s", type(e).__name__)
        return [False] * len(entries)
