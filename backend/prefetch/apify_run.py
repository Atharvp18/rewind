"""Apify offline prefetch: scrapes fsastore.com for HSA/FSA eligible products.

RUNS BEFORE THE DEMO, NEVER DURING A SCAN. Never imported by the API.

Pipeline (business spec 24.5):
1. Run the Apify actor against fsastore.com category listings
2. Export the dataset as JSON
3. Clean and normalize each row
4. Add non-eligible examples so the table can say "no"
5. Bulk-insert into eligibility_items

Usage:
    python -m prefetch.apify_run

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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

FSA_STORE_CATEGORIES = [
    "otc-medicines", "first-aid", "health-devices", "personal-care", "eye-care",
    "foot-care", "digestive-health", "allergy-sinus", "pain-relief", "cold-flu",
]

CATEGORY_MAP = {
    "otc-medicines": "otc_medicine",
    "first-aid": "first_aid",
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


def run_apify_scrape(max_items_per_category: int = 100) -> list[dict]:
    """Run the Apify actor over each fsastore.com category. Returns raw items."""
    from apify_client import ApifyClient

    token = os.environ.get("APIFY_TOKEN")
    if not token:
        logger.error("APIFY_TOKEN not set. Cannot run scrape.")
        return []

    client = ApifyClient(token)
    all_items: list[dict] = []
    for category in FSA_STORE_CATEGORIES:
        logger.info("Scraping category: %s", category)
        run_input = {
            "startUrls": [{"url": f"https://fsastore.com/collections/{category}"}],
            "maxItems": max_items_per_category,
            "proxyConfiguration": {"useApifyProxy": True},
        }
        try:
            run = client.actor("apify/web-scraper").call(run_input=run_input)
            items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
            logger.info("Got %d items from %s", len(items), category)
            for item in items:
                item["_source_category"] = category
            all_items.extend(items)
        except Exception:
            logger.exception("Failed to scrape category %s", category)
    return all_items


def normalize_scraped_data(raw_items: list[dict]) -> list[dict]:
    """Raw actor output -> eligibility_items rows (all eligible, basis retailer_badge)."""
    from lookup.normalize import normalize_key, product_key_from_upc

    rows: list[dict] = []
    seen: set[str] = set()
    now = datetime.now(timezone.utc).isoformat()

    for item in raw_items:
        name = (item.get("title") or item.get("name") or "").strip()
        if not name:
            continue
        brand = (item.get("brand") or "").strip() or None
        size = (item.get("size") or item.get("variant") or "").strip() or None
        upc = (item.get("upc") or item.get("gtin") or item.get("barcode") or "").strip() or None
        source_category = item.get("_source_category", "")
        product_key = product_key_from_upc(upc) if upc else normalize_key(brand, name, size)
        if product_key in seen:
            continue
        seen.add(product_key)
        rows.append({
            "product_key": product_key,
            "upc": upc,
            "name": name,
            "brand": brand,
            "size": size,
            "category_path": CATEGORY_MAP.get(source_category, "other"),
            "eligible": True,
            "source_url": item.get("url") or item.get("pageUrl")
                          or f"https://fsastore.com/collections/{source_category}",
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


def main() -> None:
    out_dir = Path(__file__).parent.parent / "data" / "eligibility_data"

    raw = run_apify_scrape(max_items_per_category=50)
    if not raw:
        logger.warning("No items scraped. Continuing with hand-entered non-eligible rows only.")
    save_json(raw, out_dir / "raw_scrape.json")

    rows = add_non_eligible_examples(normalize_scraped_data(raw))
    save_json(rows, out_dir / "eligibility_items.json")

    try:
        from data.db import eligibility_bulk_insert
        logger.info("Inserted %d rows into eligibility_items", eligibility_bulk_insert(rows))
    except ImportError:
        logger.warning("data/db.py not present; rows saved to JSON only.")
    except Exception:
        logger.exception("Database insert failed; rows saved to JSON.")

    logger.info("Prefetch complete.")


if __name__ == "__main__":
    main()
