"""Eligibility classifier: is this product HSA/FSA eligible?

One source: the scraped store listings (Apify rows, searched with Moss, lookup/moss_index.py), plus the
products Claude judged from a general store (prefetch/extra_products.py). No IRS category table
(Nak, 2026-10-24: it contradicted the index).

- a listing was found: its eligible flag is the answer
- the index answered but found nothing: not in our data, so NOT eligible (the item goes to the Visa)
- the index could not answer: also NOT eligible, so an outage can never overstate eligibility
"""
from __future__ import annotations

from models.schemas import EligibilityResult, ProductResolution


def classify_eligibility(
    product: ProductResolution,
    package_marking: str | None = None,
    retailer: dict | None = None,
    index_checked: bool = False,
) -> EligibilityResult:
    """`product` and `package_marking` are accepted for the callers' sake; only the listing decides."""
    if retailer is not None:
        return EligibilityResult(label="eligible" if retailer["eligible"] else "not_eligible",
                                 confidence=retailer["score"], basis="semantic_match", source="retailer_index",
                                 collected_at=retailer["collected_at"], matched_name=retailer["name"])
    return EligibilityResult(label="not_eligible", basis="no_match" if index_checked else "index_unavailable")
