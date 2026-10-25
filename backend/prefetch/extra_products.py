"""Scrape a few more products from a general store with Apify and let Claude judge HSA/FSA eligibility.

RUNS BEFORE THE DEMO, NEVER DURING A SCAN. The demo cart uses 3 items; these extra rows give the
index both answers for products it did not list before. fsastore.com only sells eligible items, so
these come from a mixed store (Walmart search pages) and Claude decides, from the IRS rules, whether each
is eligible. Rows are saved with basis "claude_judged"; prefetch/apify_run.py includes them when it
rebuilds the Moss index.

Usage (needs APIFY_TOKEN and ANTHROPIC_API_KEY in the repo-root .env):
    python -m prefetch.extra_products
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

sys.path.insert(0, str(Path(__file__).parent.parent))

from prefetch.apify_run import scrape  # noqa: E402  (loads the .env files)

logger = logging.getLogger(__name__)

SEARCHES = ["sunscreen spf 50", "potato chips", "vitamin c gummies", "shampoo", "digital thermometer"]
PER_SEARCH = 2
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "claude-sonnet-5-5")
SYSTEM = ("You decide whether a retail product is eligible to buy with a US HSA or FSA card, under the IRS "
          "rules (Publication 502 and the CARES Act). Eligible: medicine and drugs, first aid, medical "
          "devices and tests, sunscreen SPF 15 or higher, menstrual products, eye and dental care for "
          "treatment. Not eligible: food and snacks, general vitamins and supplements, cosmetics, "
          "shampoo and toiletries, household goods. When unsure, answer false. Reply with only JSON: "
          '[{"i": 0, "eligible": true, "category": "sun_care", "reason": "short"}], one entry per product.')


def judge(products: list[dict]) -> list[dict]:
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    listing = "\n".join(f"{i}. {p['name']}" for i, p in enumerate(products))
    response = client.messages.create(model=JUDGE_MODEL, max_tokens=2000, system=SYSTEM,
                                      messages=[{"role": "user", "content": listing}])
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text[text.index("["):text.rindex("]") + 1])


def to_row(item: dict, verdict: dict) -> dict:
    from lookup.normalize import normalize_key

    name = (item.get("name") or item.get("title") or "").strip()
    brand = item.get("brand")
    brand = (brand.get("name") if isinstance(brand, dict) else brand) or None
    try:
        price = round(float((item.get("offers") or {}).get("price")) * 100)
    except (TypeError, ValueError):
        price = None
    return {"product_key": normalize_key(brand, name, None), "upc": None, "name": name, "brand": brand,
            "size": None, "category_path": verdict.get("category") or "other", "price_cents": price,
            "eligible": bool(verdict["eligible"]), "source_url": item.get("url") or item.get("inputUrl") or "",
            "collected_at": datetime.now(timezone.utc).isoformat(), "basis": "claude_judged",
            "reason": verdict.get("reason", "")}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    data = Path(__file__).parent.parent / "data" / "eligibility_data"
    data.mkdir(parents=True, exist_ok=True)
    raw_path, out = data / "extra_raw.json", data / "claude_judged.json"
    verdicts_path = Path(sys.argv[sys.argv.index("--verdicts") + 1]) if "--verdicts" in sys.argv else None

    if "--judge-only" in sys.argv:                      # reuse the saved scrape
        items = json.loads(raw_path.read_text())
    else:
        token = os.environ.get("APIFY_TOKEN")
        if not token:
            sys.exit("APIFY_TOKEN must be set in the repo-root .env")
        items = []
        for term in SEARCHES:                           # one run per search, so each gives its own products
            url = f"https://www.walmart.com/search?q={quote_plus(term)}"
            items += scrape(token, {"listingUrls": [{"url": url}], "maxProductResults": PER_SEARCH,
                                    "scrapeMode": "AUTO"}, PER_SEARCH)
        items = [i for i in items if (i.get("name") or i.get("title"))][: len(SEARCHES) * PER_SEARCH]
        raw_path.write_text(json.dumps(items, indent=2))
        logger.info("Saved %d scraped products to %s", len(items), raw_path)

    if verdicts_path:                                   # eligibility decided elsewhere, as [{"i":0,"eligible":...}]
        verdicts = {v["i"]: v for v in json.loads(verdicts_path.read_text())}
    elif os.environ.get("ANTHROPIC_API_KEY"):
        verdicts = {v["i"]: v for v in judge([{"name": i.get("name") or i.get("title")} for i in items])}
    else:
        for n, item in enumerate(items):
            print(n, item.get("name") or item.get("title"))
        sys.exit("No ANTHROPIC_API_KEY: pass --verdicts <file> (with --judge-only) to finish.")
    rows = [to_row(item, verdicts[n]) for n, item in enumerate(items) if n in verdicts]
    out.write_text(json.dumps(rows, indent=2))
    for r in rows:
        logger.info("%-8s %s ($%s) - %s", "ELIGIBLE" if r["eligible"] else "no", r["name"][:60],
                    (r["price_cents"] or 0) / 100, r["reason"])
    logger.info("Saved %d judged rows to %s. Run `python -m prefetch.apify_run --index-only` to load them.",
                len(rows), out)


if __name__ == "__main__":
    main()
