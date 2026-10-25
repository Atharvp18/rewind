"""Stand-in for the Moss eligibility index in everyday tests (the real index is the only source).

Matches the demo products by a word in their name. Anything else is "not listed", which the
classifier treats as not eligible. Tests that need a different listing patch find_match themselves.
"""
from __future__ import annotations

LISTED = {                      # word in the product name -> eligible?
    "advil": True, "ibuprofen": True, "bandage": True, "band-aid": True, "tylenol": True,
    "allegra": True, "tums": True, "excedrin": True, "kettle": False,
}


async def find_match(product) -> dict | None:
    text = f"{product.brand or ''} {product.name}".lower()
    for word, eligible in LISTED.items():
        if word in text:
            return {"eligible": eligible, "name": product.name, "collected_at": "2026-10-24T00:00:00+00:00",
                    "score": 0.95, "price_cents": None, "pinned": False}
    return None
