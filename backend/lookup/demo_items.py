"""The three demo products, matched by name before the fuzzy Moss search.

Scanning here is a simulation (at a real store the price comes from the shelf tag), so the demo
items must resolve the same way every time. A fuzzy match is not enough: "Allergy Relief" ranks
Benadryl and Claritin above the 4 mg listing. Prices are the searched prices pinned in
prefetch/apify_run.py (PRICE_FALLBACK_CENTS); all three are HSA/FSA eligible.
"""
from __future__ import annotations

import re

COLLECTED_AT = "2026-10-24T00:00:00+00:00"

# (name shown, price in cents, test on the lower-cased "brand name size" text)
DEMO_ITEMS = [
    ("TUMS Ultra Strength Chewable Tablets, 72 Count", 548, lambda t: "tums" in t),
    ("Allergy Relief 4 mg Tablets, 100 Count", 399,
     lambda t: "chlorpheniramine" in t or "chlor-trimeton" in t
     or ("allergy relief" in t and re.search(r"\b4 ?mg\b", t) is not None)
     or re.fullmatch(r"\W*allergy relief( tablets)?\W*", t) is not None),
    ("Tylenol Extra Strength Caplets, 24 Count", 519, lambda t: "tylenol" in t),
]


def match(product) -> dict | None:
    """A listing dict in find_match's shape for a demo product, else None."""
    text = " ".join(p for p in (product.brand, product.name, product.size) if p).lower()
    for name, cents, test in DEMO_ITEMS:
        if test(text):
            return {"eligible": True, "name": name, "collected_at": COLLECTED_AT, "score": 1.0,
                    "price_cents": cents, "pinned": True}
    return None
