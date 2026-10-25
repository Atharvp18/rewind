"""Apify offline prefetch: scrapes fsastore.com for HSA/FSA eligible products.

RUNS BEFORE THE DEMO, NEVER DURING A SCAN. Never imported by the API.

Pipeline (business spec 24.5):
1. Run Apify's E-commerce Scraping Tool over fsastore.com collection pages
2. Export the dataset as JSON
3. Clean and normalize each row
4. Add non-eligible examples so the table can say "no"
5. Build the Moss index from the rows (lookup/moss_index.py)

Usage (needs APIFY_TOKEN in backend/.env):
    python -m prefetch.apify_run               # one scrape of the fixed catalog, then rebuild the Moss index
    python -m prefetch.apify_run --index-only  # rebuild the Moss index from the saved rows, no scraping

Uses Apify's ready-made E-commerce Scraping Tool on a fixed list of product pages: one run, same rows every time.

Complete the terms/robots.txt check (business spec 24.4) and the go/no-go
test (24.2) before running at any scale.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents import common  # noqa: F401  (loads backend/.env: APIFY_TOKEN, MOSS_*)
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")   # the repo-root .env, where the keys live

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

FSA_STORE_CATEGORIES = [
    "otc-medicines", "first-aid", "health-devices", "personal-care", "eye-care",
    "foot-care", "digestive-health", "allergy-sinus", "pain-relief", "cold-flu",
]

CATEGORY_MAP = {
    "pain-relief": "pain_relief",
    "cold-and-allergy": "cold_flu_allergy",
    "all-medicine-and-treatments": "otc_medicine",
    "digestive-health": "digestive_health",
    "first-aid": "first_aid",
    "otc-medicines": "otc_medicine",
    "health-devices": "diagnostic_device",
    "personal-care": "personal_care",
    "eye-care": "eye_care",
    "foot-care": "foot_care",
    "digestive-health": "digestive_health",
    "allergy-sinus": "cold_flu_allergy",
    "pain-relief": "pain_relief",
    "cold-flu": "cold_flu_allergy",
}

NON_ELIGIBLE_EXAMPLES = [
    ("Kettle Corn", "Angie's", "grocery"),
    ("Potato Chips", "Lay's", "grocery"),
    ("Chocolate Bar", "Hershey's", "grocery"),
    ("Cola Soda", "Coca-Cola", "grocery"),
    ("Gummy Bears Candy", "Haribo", "grocery"),
    ("Trail Mix Snack", "Planters", "grocery"),
    ("Energy Drink", "Monster", "grocery"),
    ("Protein Bar", "Kind", "grocery"),
    ("Paper Towels", "Bounty", "household"),
    ("Dish Soap", "Dawn", "household"),
    ("Laundry Detergent", "Tide", "household"),
    ("Lipstick", "Maybelline", "cosmetics"),
    ("Face Moisturizer", "Olay", "personal_care"),
    ("Shampoo", "Pantene", "personal_care"),
    ("Body Lotion", "Jergens", "personal_care"),
]


ACTOR_ID = "apify/e-commerce-scraping-tool"   # Apify's ready-made scraper; override with APIFY_ACTOR_ID
_S = "https://fsastore.com/"

# The catalog is a FIXED list of product pages, so every run scrapes the same products: rows are
# replaced by key and the table never grows. Listing pages return a different handful each time,
# which is why they are not used. Excedrin and Pepcid are left out on purpose: they are OTC
# medicines the index does not list, for the "could not confirm, use your Visa" moment.
CATALOG = {
    "https://www.hsastore.com/tylenol-extra-strength-caplets/28870m.html?Count=24+ct": "pain-relief",   # demo item
    _S + "advil-pain-reliever-and-fever-reducer-coated-tablets-200-mg/30429m.html": "pain-relief",
    _S + "preparation-h-hemorrhoidal-cream-original-0-9-oz/42814.html": "pain-relief",
    _S + "allegra-24-hour-indoor-outdoor-allergy-relief-tablets-90-ct/31452.html": "cold-and-allergy",
    _S + "benadryl-ultra-allergy-relief-tablets-100-ct/28272.html": "cold-and-allergy",
    _S + "claritin-24-hour-allergy-medicine-non-drowsy-prescription-strength-allergy-relief-loratadine-antihistamine-tablets-100-ct/40334.html": "cold-and-allergy",
    _S + "caring-mill-24-hour-allergy-relief-cetirizine-hydrochloride-tablets-10mg/40161m.html": "cold-and-allergy",
    _S + "tums-ultra-strength-assorted-fruit-antacid-chewable-tablets-for-heartburn-relief-72-ct/30441.html": "digestive-health",  # demo item
    "https://wellbefore.com/products/foster-thrive-allergy-relief-4-mg-tablets-100-count": "cold-and-allergy",   # demo item
    _S + "band-aid-pro-heal-adhesive-bandages-5-day-protect-14-ct/42388.html": "first-aid",
    _S + "band-aid-flexible-fabric-adhesive-bandages-assorted-sizes/25601m.html": "first-aid",
    _S + "caring-mill-triple-antibiotic-ointment-plus-pain-relief-1-oz/41983.html": "first-aid",
}
# The three demo items (Tums 72 chewables, allergy relief 4 mg 100 tablets, Tylenol Extra Strength 24):
# a typical shelf price from a web search (it wins over the scraped price, which was for another size;
# 2026-10-24 lookups:
# Walmart $5.48, Walmart/Wellbefore $3.99 to $4.28, Pasteur Pharmacy $5.19).
PRICE_FALLBACK_CENTS = {
    _S + "tums-ultra-strength-assorted-fruit-antacid-chewable-tablets-for-heartburn-relief-72-ct/30441.html": 548,
    "https://wellbefore.com/products/foster-thrive-allergy-relief-4-mg-tablets-100-count": 399,
    "https://www.hsastore.com/tylenol-extra-strength-caplets/28870m.html?Count=24+ct": 519,
}
STORE_BRAND = "FSA Store"   # fsastore.com's own label, not a product brand


def run_apify_scrape() -> list[dict]:
    """One Apify run over the whole fixed catalog. Returns the products it could read."""
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        logger.error("APIFY_TOKEN is not set in backend/.env.")
        return []
    items = scrape(token, {"detailsUrls": [{"url": u} for u in CATALOG], "maxProductResults": len(CATALOG),
                           "scrapeMode": "AUTO"}, len(CATALOG))
    logger.info("Scraped %d of %d products", len(items), len(CATALOG))
    return items


def scrape(token: str, run_input: dict, limit: int) -> list[dict]:
    """One run of the e-commerce scraper (apify-client 3.x: Run object, timedelta, Decimal)."""
    from datetime import timedelta
    from decimal import Decimal

    from apify_client import ApifyClient

    client = ApifyClient(token)
    run = client.actor(os.environ.get("APIFY_ACTOR_ID") or ACTOR_ID).call(
        run_input=run_input,
        max_total_charge_usd=Decimal("1.0"),    # the tool's minimum allowed cap; a run costs a few tenths of a cent
        memory_mbytes=1024,
        run_timeout=timedelta(seconds=600),
        logger=None,
    )
    items = list(client.dataset(run.default_dataset_id).iterate_items(limit=limit))
    logger.info("Run %s: %s, %d items", run.id, run.status, len(items))
    return items


def _brand(item: dict) -> str | None:
    brand = item.get("brand")
    brand = (brand.get("slogan") or brand.get("name")) if isinstance(brand, dict) else brand
    brand = (brand or "").strip()
    return None if not brand or brand == STORE_BRAND else brand


def _price_cents(item: dict) -> int | None:
    try:
        return round(float((item.get("offers") or {}).get("price")) * 100)
    except (TypeError, ValueError):
        return None


def normalize_scraped_data(raw_items: list[dict]) -> list[dict]:
    """Scraper output -> eligibility_items rows (all eligible, basis retailer_badge).

    fsastore.com only sells HSA/FSA-eligible items, so a listing there is the eligibility evidence.
    """
    from lookup.normalize import normalize_key

    rows: list[dict] = []
    seen: set[str] = set()
    now = datetime.now(timezone.utc).isoformat()

    for item in raw_items:
        name = (item.get("name") or item.get("title") or "").strip()
        if not name:
            continue
        brand = _brand(item)
        size = (item.get("size") or item.get("variant") or "").strip() or None
        collection = CATALOG.get(item.get("inputUrl", "")) or item.get("collection") or ""
        product_key = normalize_key(brand, name, size)   # the same key a vision read produces
        if product_key in seen:
            continue
        seen.add(product_key)
        rows.append({
            "product_key": product_key,
            "upc": None,
            "name": name,
            "brand": brand,
            "size": size,
            "category_path": CATEGORY_MAP.get(collection, "other"),
            "price_cents": _price_cents(item),   # the store's listed price: a fallback, kept in the Moss index
            "eligible": True,
            "source_url": item.get("inputUrl") or item.get("url") or f"https://fsastore.com/collections/{collection}",
            "collected_at": now,
            "basis": "retailer_badge",
        })
    return rows


def add_non_eligible_examples(eligible_rows: list[dict]) -> list[dict]:
    """Add hand-entered non-eligible rows so the table holds both answers (spec 24.6)."""
    from lookup.normalize import normalize_key

    now = datetime.now(timezone.utc).isoformat()
    negatives = [{
        "product_key": normalize_key(brand, name, None),
        "upc": None,
        "name": name,
        "brand": brand,
        "size": None,
        "category_path": category,
        "eligible": False,
        "source_url": "hand_entered",
        "collected_at": now,
        "basis": "hand_entered",
    } for name, brand, category in NON_ELIGIBLE_EXAMPLES]
    return eligible_rows + negatives


def save_json(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2))
    logger.info("Saved %d rows to %s", len(rows), path)


def load_saved_rows(path: Path) -> list[dict]:
    """Earlier rows for pages still in the catalog (kept if this run could not read a page)."""
    try:
        return [r for r in json.loads(path.read_text())
                if r.get("basis") == "retailer_badge" and r.get("source_url") in CATALOG]
    except (OSError, ValueError):
        return []


def load_judged_rows(path: Path) -> list[dict]:
    """Products scraped from a general store and judged by Claude (prefetch/extra_products.py)."""
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return []


def main() -> None:
    out_dir = Path(__file__).parent.parent / "data" / "eligibility_data"
    saved = out_dir / "eligibility_items.json"
    index_only = "--index-only" in sys.argv

    raw = [] if index_only else run_apify_scrape()
    if not raw and not index_only:
        logger.warning("No items scraped. Keeping the rows saved by earlier runs.")
    if raw:
        save_json(raw, out_dir / "raw_scrape.json")

    # A page can fail on a given run, so keep its earlier row; a row is replaced when its page is read again.
    # Keyed by page address, not by the name-based key: the tool can read a brand differently from
    # one run to the next, which changes the key and would otherwise leave the old row behind.
    merged = {r["source_url"]: r for r in load_saved_rows(saved)}
    for row in normalize_scraped_data(raw):
        if row["source_url"] not in CATALOG:
            continue
        old = merged.get(row["source_url"])
        if row["price_cents"] is None and old and old.get("price_cents") is not None:
            row["price_cents"] = old["price_cents"]   # the tool sometimes omits the price; keep the last one seen
        merged[row["source_url"]] = row
    for url, cents in PRICE_FALLBACK_CENTS.items():
        if url in merged:
            merged[url]["price_cents"] = cents
    rows = add_non_eligible_examples(list(merged.values()))
    rows += load_judged_rows(out_dir / "claude_judged.json")      # prefetch/extra_products.py
    save_json(rows, out_dir / "eligibility_items.json")

    if not os.environ.get("MOSS_PROJECT_ID"):
        logger.warning("MOSS_PROJECT_ID not set; rows saved to JSON only.")
    else:
        import asyncio
        from lookup.moss_index import build_index
        try:
            logger.info("Built the Moss index with %d rows", asyncio.run(build_index(rows)))
        except Exception:
            logger.exception("Moss index build failed; rows saved to JSON.")

    logger.info("Prefetch complete.")


if __name__ == "__main__":
    main()
