"""Price and pack size for a product the store index does not list, found on the internet by Claude.

The order for any item (see agents/product_agent.py):
  1. the store listing in the Moss index (scraped by Apify) is the primary price;
  2. a price found here earlier, so the same product always gets the same price and size;
  3. the shelf tag, if the photo shows one;
  4. only then a new internet search, whose answer is saved (step 2) for next time.

Claude only reads the web and reports what it found. A price outside the sane range, or an answer
that is not valid JSON, counts as "not found": the agent then asks the person, as before.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re

from lookup.normalize import normalize_key

logger = logging.getLogger(__name__)

SOURCE = "web_search"                      # product_cache.source; kept by reset_demo (data/functions.sql)
MODEL = os.environ.get("WEB_LOOKUP_MODEL", "claude-sonnet-5-5")
TIMEOUT_S = float(os.environ.get("WEB_LOOKUP_TIMEOUT_S", "25"))    # a web search takes longer than the 10 s other calls get
TOOL = {"type": "web_search_20260209", "name": "web_search", "max_uses": 3}
PRICE_MIN_CENTS, PRICE_MAX_CENTS = 1, 50000

SYSTEM = ("You find the current price of one retail product for a pharmacy shopper. Search the web, prefer a "
          "large US retailer, and report the price of one standard package and that package's size. "
          'Reply with JSON only: {"price_dollars": number or null, "size": string or null}. '
          "Use null for anything you could not find. Do not guess.")


def key_for(product) -> str:
    """Size is left out on purpose: the same product read with a different size still hits the same row.
    The prefix keeps it apart from the per-scan rows lookup/chain.py writes."""
    return "web:" + normalize_key(product.brand, product.name, None)


def _stubbed() -> bool:
    return os.environ.get("REWIND_STUB_WEB", "false").lower() == "true" or not os.environ.get("ANTHROPIC_API_KEY")


async def stored(product) -> dict | None:
    """A price saved by an earlier search: {"price_cents", "size"}. No expiry, so it never changes."""
    try:
        from data.db import cache_get
        row = await asyncio.to_thread(cache_get, key_for(product))
    except Exception as exc:
        logger.warning("saved online price not read: %s", exc)
        return None
    if row and row.get("source") == SOURCE and row.get("shelf_price_cents"):
        return {"price_cents": int(row["shelf_price_cents"]), "size": row.get("size")}
    return None


def _parse(text: str) -> dict | None:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        dollars = float(data["price_dollars"])
    except (ValueError, KeyError, TypeError):
        return None
    cents = round(dollars * 100)
    if not PRICE_MIN_CENTS <= cents <= PRICE_MAX_CENTS:
        return None
    size = data.get("size")
    return {"price_cents": cents, "size": size.strip() if isinstance(size, str) and size.strip() else None}


_client = None


def _get_client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.AsyncAnthropic()
    return _client


async def _ask(product) -> dict | None:
    wanted = " ".join(p for p in (product.brand, product.name, product.size) if p)
    messages = [{"role": "user", "content": f"Product: {wanted}"}]
    for _ in range(3):                                   # a long search can pause; continue it
        response = await _get_client().messages.create(
            model=MODEL, max_tokens=1024, system=SYSTEM, tools=[TOOL], messages=messages)
        if response.stop_reason != "pause_turn":
            break
        messages.append({"role": "assistant", "content": response.content})
    text = "".join(b.text for b in response.content if b.type == "text")
    return _parse(text)


async def search_and_save(product) -> dict | None:
    """Ask Claude to find the price and size online, save the answer, return it. None if not found."""
    if _stubbed() or not product.name:
        return None
    try:
        found = await asyncio.wait_for(_ask(product), TIMEOUT_S)
    except asyncio.TimeoutError:
        logger.warning("online price search timed out after %ss", TIMEOUT_S)
        return None
    except Exception:
        logger.exception("online price search failed")
        return None
    if not found:
        return None
    try:
        from data.db import cache_put
        await asyncio.to_thread(cache_put, key_for(product), {
            "normalized_name": product.name, "brand": product.brand, "size": found["size"] or product.size,
            "category": product.category, "shelf_price_cents": found["price_cents"], "source": SOURCE})
    except Exception as exc:
        logger.warning("online price not saved: %s", exc)
    return found
