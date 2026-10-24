"""Apify offline prefetch: scrapes fsastore.com for HSA/FSA eligible products.

RUNS BEFORE THE DEMO, NEVER DURING A SCAN. Never imported by the API.

Pipeline (business spec 24.5):
1. Run our Apify Actor over fsastore.com collection pages
2. Export the dataset as JSON
3. Clean and normalize each row
4. Add non-eligible examples so the table can say "no"
5. Bulk-insert into eligibility_items

Usage (needs APIFY_TOKEN and APIFY_ACTOR_ID in backend/.env):
    python -m prefetch.apify_run

The Actor is ours, built with Apify AI chat. At most 15 products are collected.

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


MAX_PRODUCTS = 15   # a small, real catalog for the cross-check; also keeps the credits safe


def run_apify_scrape(max_products: int = MAX_PRODUCTS) -> list[dict]:
    """Run our Apify Actor (built with Apify AI chat) once and return its items.

    The Actor id comes from APIFY_ACTOR_ID (for example "yourname/fsastore-scraper").
    The run is capped three ways: items asked for, memory, and a hard timeout.
    """
    from apify_client import ApifyClient

    token, actor_id = os.environ.get("APIFY_TOKEN"), os.environ.get("APIFY_ACTOR_ID")
    if not token or not actor_id:
        logger.error("APIFY_TOKEN and APIFY_ACTOR_ID must both be set in backend/.env.")
        return []

    client = ApifyClient(token)
    per_collection = max(1, -(-max_products // len(FSA_STORE_CATEGORIES)))   # ceiling division
    run = client.actor(actor_id).call(
        run_input={"maxItemsPerCollection": per_collection},
        memory_mbytes=1024,
        timeout_secs=300,
    )
    logger.info("Actor run %s finished with status %s", run.get("id"), run.get("status"))
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items(limit=max_products))
    logger.info("Got %d products", len(items))
    return items


def normalize_scraped_data(raw_items: list[dict]) -> list[dict]:
    """Actor output -> eligibility_items rows (all eligible, basis retailer_badge).

    fsastore.com only sells HSA/FSA-eligible items, so a listing there is the eligibility evidence.
    Fields from the Actor: name, brand, size, price, url, collection.
    """
    from lookup.normalize import normalize_key

    rows: list[dict] = []
    seen: set[str] = set()
    now = datetime.now(timezone.utc).isoformat()

    for item in raw_items:
        name = (item.get("name") or item.get("title") or "").strip()
        if not name:
            continue
        brand = (item.get("brand") or "").strip() or None
        size = (item.get("size") or item.get("variant") or "").strip() or None
        collection = item.get("collection") or item.get("_source_category", "")
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
            "eligible": True,
            "source_url": item.get("url") or f"https://fsastore.com/collections/{collection}",
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

    raw = run_apify_scrape()
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
