"""Eligibility classifier: determines whether a product is HSA/FSA eligible.

Source order (Nak, 2026-10-24: the scraped Apify data is primary):
1. The closest scraped store listing (Apify rows, searched with Moss). Its flag is the answer.
2. Moss answered but found nothing: not in our data, so NOT eligible (goes to the Visa).
3. Moss unavailable: the IRS category rules decide alone (fallback only).
"""
from __future__ import annotations

import logging

from models.schemas import EligibilityResult, ProductResolution
from eligibility.irs_rules import lookup_category

logger = logging.getLogger(__name__)

def classify_eligibility(
    product: ProductResolution,
    package_marking: str | None,
    retailer: dict | None = None,
    index_checked: bool = False,
) -> EligibilityResult:
    """Classify a product's HSA/FSA eligibility. The scraped listing is the primary source.

    The Apify data (the Moss index of fsastore.com listings, plus Claude-judged products) decides first:
    - a listing was found: its eligible flag is the answer, whatever the category rules say
    - Moss answered but nothing matched: not in our data, so assume NOT eligible (Visa)
    - Moss could not answer (index_checked False): the IRS category rules decide alone
    The IRS rules are the fallback, never an override of a scraped listing.

    Args:
        product: The resolved product (name and category read by Claude Vision).
        package_marking: "eligible" or "none_seen" from vision, or None.
        retailer: the closest store listing from moss_index.find_match, or None.
        index_checked: True when Moss answered (so "no listing" is meaningful).
    """
    if retailer is not None:
        return EligibilityResult(label="eligible" if retailer["eligible"] else "not_eligible",
                                 confidence=retailer["score"], basis="semantic_match", source="retailer_index",
                                 collected_at=retailer["collected_at"], matched_name=retailer["name"])
    ruled = _classify_by_rules(product, package_marking)
    if index_checked:
        return EligibilityResult(label="not_eligible", basis="no_match")       # not in our data
    # Moss was not consulted: the rules decide, and "could not confirm" is treated as not eligible.
    if ruled.label == "could_not_confirm" and ruled.basis == "no_match":
        return EligibilityResult(label="not_eligible", basis="no_match")
    return ruled


def _classify_by_rules(
    product: ProductResolution,
    package_marking: str | None,
) -> EligibilityResult:
    """Classify a product's HSA/FSA eligibility from the IRS category rules.

    Args:
        product: The resolved product (name and category read by Claude Vision).
        package_marking: "eligible" or "none_seen" from vision, or None.
    """
    rule = lookup_category(product.category)

    # Medicines: Claude Vision names the product and its category. Shelf (OTC) medicine
    # in an IRS-backed category is eligible (CARES Act). A medicine in any other
    # category is never guessed: could_not_confirm.
    if product.is_medication and rule != "eligible":
        return EligibilityResult(
            label="could_not_confirm",
            confidence=None,
            basis="no_match",
            source=None,
            collected_at=None,
            matched_name=None,
        )

    # IRS category rules
    if rule == "eligible":
        result = EligibilityResult(
            label="eligible",
            confidence=None,
            basis="irs_category_rule",
            source="irs_rules",
            collected_at=None,
            matched_name=None,
        )
        return _cross_check_package(result, package_marking)
    elif rule == "not_eligible":
        result = EligibilityResult(
            label="not_eligible",
            confidence=None,
            basis="irs_category_rule",
            source="irs_rules",
            collected_at=None,
            matched_name=None,
        )
        return _cross_check_package(result, package_marking)

    # Step 3: fallback
    return EligibilityResult(
        label="could_not_confirm",
        confidence=None,
        basis="no_match",
        source=None,
        collected_at=None,
        matched_name=None,
    )


def _cross_check_package(
    result: EligibilityResult,
    package_marking: str | None,
) -> EligibilityResult:
    """Cross-check the classification against the package marking.

    If the package says "eligible" but the index says "not_eligible",
    downgrade to "could_not_confirm" with basis "package_disagreement".
    """
    if package_marking == "eligible" and result.label == "not_eligible":
        return EligibilityResult(
            label="could_not_confirm",
            confidence=result.confidence,
            basis="package_disagreement",
            source=result.source,
            collected_at=result.collected_at,
            matched_name=result.matched_name,
        )
    return result
