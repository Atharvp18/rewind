"""Product lookup chain (tech spec 2.6).

Turns a VisionExtract into a ProductResolution: cache first, then the shelf
tag is the product. No retailer API in v1 (decision 7).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from models.schemas import ProductResolution, VisionExtract
from lookup.normalize import build_product_key

logger = logging.getLogger(__name__)

_cache_get = None
_cache_put = None

CACHE_MAX_AGE_HOURS = 24
PRICE_MIN_CENTS, PRICE_MAX_CENTS = 1, 50000


def _get_db():
    global _cache_get, _cache_put
    if _cache_get is None:
        try:
            from data.db import cache_get, cache_put
        except ImportError:
            # data/db.py (Atharv) not present yet: behave as a cache miss.
            cache_get, cache_put = (lambda key: None), (lambda key, row: None)
        _cache_get = cache_get
        _cache_put = cache_put
    return _cache_get, _cache_put


def _cached_price_is_fresh(cached: dict) -> bool:
    last_updated = cached.get("last_updated")
    if not last_updated:
        return False
    try:
        updated = (datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
                   if isinstance(last_updated, str) else last_updated)
        return datetime.now(timezone.utc) - updated < timedelta(hours=CACHE_MAX_AGE_HOURS)
    except Exception:
        return False


def resolve_product(extract: VisionExtract) -> ProductResolution:
    product_key = build_product_key(extract.brand, extract.name, extract.size)
    warnings = list(extract.warnings)

    if not extract.name:
        return ProductResolution(
            product_key=product_key,
            name="Unknown product",
            category=extract.category or "other",
            state="unresolved",
            warnings=warnings + ["E_PRODUCT_UNRESOLVED"],
        )

    cache_get, cache_put = _get_db()
    try:
        cached = cache_get(product_key)
    except Exception as exc:
        logger.warning("Cache read skipped: %s", exc)
        cached = None

    name = extract.name or "Unknown product"
    brand, size = extract.brand, extract.size
    category = extract.category or "other"
    amount_cents = extract.shelf_price_cents
    price_source = "shelf_tag" if amount_cents is not None else None

    if cached:
        name = cached.get("normalized_name", name)
        brand = cached.get("brand", brand)
        size = cached.get("size", size)
        if category in (None, "other"):             # a fresher reading beats an older "other"
            category = cached.get("category", category)
        if amount_cents is None and cached.get("shelf_price_cents") is not None and _cached_price_is_fresh(cached):
            amount_cents = cached["shelf_price_cents"]
            price_source = "cache"

    # A misread decimal point is the most likely shelf-tag error (spec 2.3).
    if amount_cents is not None and not (PRICE_MIN_CENTS <= amount_cents <= PRICE_MAX_CENTS):
        warnings.append("E_NO_PRICE")
        amount_cents, price_source = None, None

    if name == "Unknown product":
        state = "unresolved"
    elif amount_cents is not None:
        state = "resolved"
    else:
        state = "partial"
        if "E_NO_PRICE" not in warnings:
            warnings.append("E_NO_PRICE")

    resolution = ProductResolution(
        product_key=product_key,
        name=name,
        brand=brand,
        size=size,
        category=category,
        is_medication=extract.is_medication,
        is_prescription_only=extract.is_prescription_only or False,
        amount_cents=amount_cents,
        price_source=price_source,
        state=state,
        warnings=warnings,
    )

    if state != "unresolved":
        try:
            cache_put(product_key, {
                "upc": None,
                "normalized_name": name,
                "brand": brand,
                "size": size,
                "category": category,
                "shelf_price_cents": amount_cents,
                "eligibility_label": None,
                "eligibility_confidence": None,
                "eligibility_basis": None,
                "source": price_source or "shelf_tag",
            })
        except Exception as exc:
            logger.warning("Cache write skipped: %s", exc)

    return resolution
