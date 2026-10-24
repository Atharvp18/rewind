"""Product key normalization (tech spec 2.4).

One key function shared by the runtime lookup and the offline prefetch,
so cache keys match across both paths.
"""
from __future__ import annotations

import hashlib
import re


def normalize_key(brand: str | None, name: str | None, size: str | None) -> str:
    """Return "n:<16-char hex>" from a cleaned brand|name|size string."""
    combined = " ".join([brand or "", name or "", size or ""]).lower()
    combined = re.sub(r"[^\w\s]", "", combined)
    combined = re.sub(r"\s+", " ", combined).strip()
    return "n:" + hashlib.sha1(combined.encode()).hexdigest()[:16]


def product_key_from_upc(upc: str) -> str:
    return "upc:" + re.sub(r"\D", "", upc)


def build_product_key(upc: str | None, brand: str | None, name: str | None, size: str | None) -> str:
    """UPC key if a barcode is known, else the normalized hash."""
    if upc:
        return product_key_from_upc(upc)
    return normalize_key(brand, name, size)
