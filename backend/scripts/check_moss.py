"""Live check of the Moss eligibility index (run by hand; the everyday tests never call Moss).

    python scripts/check_moss.py

Queries are written the way Claude Vision would name a product, not the way the store spells it.
Shows the best listing and its score, and whether find_match would accept it (score floor, or
brand-agreement floor), which is what the agent decides on.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents import common  # noqa: F401  (loads backend/.env)
from lookup import moss_index

QUERIES = [
    ("Allegra", "demo: brand only"),
    ("Allegra 24 Hour Allergy Relief 180mg", "demo: with a strength"),
    ("Tylenol", "demo: brand only"),
    ("Tylenol Extra Strength", "demo: brand and line"),
    ("Tums", "demo: brand only"),
    ("Tums antacid", "demo: brand and type"),
    ("Excedrin Tension Headache caplets 100 count", "scraped, spelled differently"),
    ("Advil Ibuprofen 200mg tablets", "scraped Advil 100 ct"),
    ("Pepcid AC acid reducer 75 tablets", "scraped earlier, may be absent"),
    ("Excedrin Migraine", "eligible by rule, likely absent"),
    ("Kettle Corn", "hand-entered NOT eligible"),
    ("Kleenex Facial Tissues", "NOT in index at all"),
    ("Dog food", "unrelated"),
]


async def main() -> None:
    from moss import QueryOptions
    await moss_index.warm_up()
    client = moss_index._get_client()
    print(f"floor MIN_SCORE = {moss_index.MIN_SCORE}\n")
    for text, note in QUERIES:
        res = await client.query(moss_index.INDEX_NAME, text, QueryOptions(top_k=1))
        if not res.docs:
            print(f"{'-':>5}  {text:<46} -> no results   [{note}]")
            continue
        d = res.docs[0]
        from models.schemas import ProductResolution
        got = await moss_index.find_match(ProductResolution(product_key="k", name=text, category="other"))
        verdict = "MATCH" if got else "none "
        elig = (d.metadata or {}).get("eligible")
        price = (d.metadata or {}).get("price_cents")
        shown = f"${int(price) / 100:.2f}" if price else "-"
        print(f"{d.score:5.2f}  {text:<42} -> {d.text[:40]:<40} {shown:>7} eligible={elig:<5} {verdict:<5} [{note}]")


asyncio.run(main())
