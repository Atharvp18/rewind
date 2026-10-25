"""Scrape public prescription-benefit pages of health insurers with Apify (mock plan data for the demo).

RUNS BEFORE THE DEMO, NEVER DURING A SCAN. Crawls a few public pages, saves the page text to
data/eligibility_data/insurer_raw.json, and the structured summary lives in data/insurer_benefits.json
(committed: tiers and TYPICAL copays only, never a member's real plan). The agent uses it to suggest
asking the pharmacist to confirm the copay (payments/insurers.py).

Usage (needs APIFY_TOKEN in the repo-root .env):
    python -m prefetch.insurer_benefits
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import prefetch.apify_run  # noqa: E402,F401  (loads the repo-root .env)

logger = logging.getLogger(__name__)

PAGES = {
    "UnitedHealthcare": "https://www.uhc.com/medicare/health-plans/details.html/92104/073/S5921413000/2026",
    "Aetna": "https://benefits.truist.com/benefits/pharmacy",
    "Cigna": "https://hr.miami.edu/benefits-and-wellness/health-care/prescription-drugs/index.html",
}
ACTOR_ID = "apify/website-content-crawler"


def main() -> None:
    from datetime import timedelta
    from decimal import Decimal

    from apify_client import ApifyClient

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        sys.exit("APIFY_TOKEN must be set in the repo-root .env")
    client = ApifyClient(token)
    run = client.actor(ACTOR_ID).call(
        run_input={"startUrls": [{"url": u} for u in PAGES.values()], "maxCrawlDepth": 0,
                   "maxCrawlPages": len(PAGES), "crawlerType": "cheerio"},
        max_total_charge_usd=Decimal("1.0"), memory_mbytes=1024, run_timeout=timedelta(seconds=300), logger=None)
    items = list(client.dataset(run.default_dataset_id).iterate_items(limit=len(PAGES)))
    out = Path(__file__).parent.parent / "data" / "eligibility_data" / "insurer_raw.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps([{"url": i.get("url"), "text": (i.get("text") or "")[:20000]} for i in items], indent=2))
    logger.info("Run %s: %s, saved %d pages to %s", run.id, run.status, len(items), out)


if __name__ == "__main__":
    main()
