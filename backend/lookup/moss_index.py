"""Moss index of retailer-listed products (tech spec 2.9, decision 2).

Apify collects real product listings from fsastore.com; prefetch/apify_run.py builds this index
from them, plus hand-entered "not eligible" examples so the index can say no. At scan time
find_match() looks up the product Claude Vision read and returns the closest listing. Names
differ between Claude and a store ("Advil 200mg 50ct" vs "Advil Ibuprofen Tablets"), which is
what semantic search is for. Moss is used only here and for the future History agent.

An item is eligible only when the IRS rules say yes AND this index lists the product. If Moss
answers and the product is not listed, eligibility/classify.py returns could_not_confirm. If Moss
cannot answer at all (MossUnavailable), the IRS rules decide alone, so an outage never breaks a scan.
"""
from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger(__name__)

INDEX_NAME = "rewind-eligibility"
MIN_SCORE = 0.75      # spec 2.9 starting value; tune on the real demo shelf
BRAND_FLOOR = 0.40    # lower floor, used only when the product's brand matches the listing's brand
TOP_K = 3
LOAD_TIMEOUT_S = 10.0   # first load downloads the index
QUERY_TIMEOUT_S = 1.0   # spec 0.7: Moss query budget

class MossUnavailable(Exception):
    """Moss is not configured, not loaded, or too slow. The IRS rules then decide alone."""


_client = None
_loaded = False

def doc_text(brand: str | None, name: str | None, size: str | None, category: str | None) -> str:
    return " ".join(p for p in (brand, name, size, category) if p)


def _get_client():
    global _client
    if _client is None:
        from moss import MossClient
        _client = MossClient(os.environ["MOSS_PROJECT_ID"], os.environ["MOSS_PROJECT_KEY"])
    return _client


async def build_index(rows: list[dict]) -> int:
    """Rebuild the whole index from eligibility rows (spec: rebuild rather than update)."""
    from moss import DocumentInfo

    docs = [DocumentInfo(
        id=r["product_key"],
        text=doc_text(r.get("brand"), r["name"], r.get("size"), r.get("category_path")),
        metadata={"eligible": "true" if r["eligible"] else "false", "name": r["name"],
                  "brand": r.get("brand") or "", "category": r.get("category_path") or "", "source_url": r.get("source_url") or "",
                  "collected_at": r.get("collected_at") or "",
                  "price_cents": str(r["price_cents"]) if r.get("price_cents") is not None else "",
                  "pinned": "true" if r.get("pinned") else ""},
    ) for r in rows]
    client = _get_client()
    try:
        await client.delete_index(INDEX_NAME)
    except Exception:   # no index yet
        pass
    await client.create_index(INDEX_NAME, docs)
    global _loaded
    _loaded = False
    return len(docs)


async def warm_up() -> bool:
    """Load the index into memory once. Returns False if Moss is unavailable."""
    global _loaded
    if _loaded:
        return True
    try:
        await asyncio.wait_for(_get_client().load_index(INDEX_NAME), LOAD_TIMEOUT_S)
        _loaded = True
    except Exception as exc:
        logger.warning("Moss index not loaded: %s", exc)
    return _loaded


async def find_match(product) -> dict | None:
    """Closest store listing for a ProductResolution.

    Returns None when Moss answered and nothing clears the floor (the product is not in the index).
    Raises MossUnavailable when Moss could not answer, so "not listed" and "down" stay different.
    """
    if not os.environ.get("MOSS_PROJECT_ID"):
        raise MossUnavailable("MOSS_PROJECT_ID is not set")
    if not product.name:
        return None
    if not await warm_up():
        raise MossUnavailable("index not loaded")
    from moss import QueryOptions

    # Brand and name only: strength and pack size do not change whether an OTC medicine is eligible.
    query = doc_text(product.brand, product.name, None, product.category)
    try:
        result = await asyncio.wait_for(
            _get_client().query(INDEX_NAME, query, QueryOptions(top_k=TOP_K, min_score=BRAND_FLOOR)),
            QUERY_TIMEOUT_S)
    except Exception as exc:
        logger.warning("Moss query skipped: %s", exc)
        raise MossUnavailable(str(exc)) from exc
    said = f"{product.brand or ''} {product.name}".lower()

    def accepted(d) -> bool:
        brand = ((d.metadata or {}).get("brand") or "").lower()
        # Strong match on its own, or a weaker one for the same brand ("Allegra" alone is enough).
        return d.score >= MIN_SCORE or (bool(brand) and brand in said and d.score >= BRAND_FLOOR)

    candidates = [d for d in result.docs if accepted(d)]
    if not candidates:
        return None
    best = max(candidates, key=lambda d: d.score)
    meta = best.metadata or {}
    price = meta.get("price_cents")
    return {
        "eligible": meta.get("eligible") == "true",
        "name": meta.get("name") or best.text,
        "collected_at": meta.get("collected_at") or None,
        "score": float(best.score),
        "price_cents": int(price) if price else None,   # the store's listed price, a fallback only
        "pinned": meta.get("pinned") == "true",         # a demo item: its price is fixed, whatever the shelf tag says
    }
