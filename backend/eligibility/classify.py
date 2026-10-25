"""Eligibility classifier: determines whether a product is HSA/FSA eligible.

Classification chain (no barcodes: Claude Vision reads the product):
1. IRS category rules (shelf medicines must be in an IRS-backed category)
2. "could_not_confirm" fallback
3. Cross-check against package marking
4. Cross-check against the closest scraped store listing (Apify rows, searched with Moss)
"""
from __future__ import annotations

import logging

from models.schemas import EligibilityResult, ProductResolution
from eligibility.irs_rules import lookup_category

logger = logging.getLogger(__name__)

def _cross_check_retailer(result: EligibilityResult, retailer: dict | None,
                          index_checked: bool) -> EligibilityResult:
    """Second source: the closest scraped store listing, found by Moss (lookup/moss_index.py).

    "Eligible" needs two sources: the IRS rules say yes AND the store index lists the product.
    - index answered, product not listed: could_not_confirm (never guess eligible)
    - a listing that disagrees with the rule: could_not_confirm
    Strength and pack size are not compared: they do not change whether an OTC medicine is eligible.
    - index could not answer (index_checked False): the rules decide alone
    Only the IRS rules can say eligible; a listing never upgrades could_not_confirm.
    A "not eligible" rule answer already sends the item to the Visa, so it needs no second source.
    """
    if result.label == "could_not_confirm":
        return result
    if retailer is None:
        if index_checked and result.label == "eligible":
            return EligibilityResult(label="could_not_confirm", basis="no_match")
        return result
    retailer_label = "eligible" if retailer["eligible"] else "not_eligible"
    if retailer_label != result.label:
        return EligibilityResult(label="could_not_confirm", basis="package_disagreement",
                                 source="retailer_index", collected_at=retailer["collected_at"],
                                 matched_name=retailer["name"])
    return EligibilityResult(label=result.label, confidence=retailer["score"], basis="semantic_match",
                             source="retailer_index", collected_at=retailer["collected_at"],
                             matched_name=retailer["name"])


def classify_eligibility(
    product: ProductResolution,
    package_marking: str | None,
    retailer: dict | None = None,
    index_checked: bool = False,
) -> EligibilityResult:
    """Classify a product's HSA/FSA eligibility, then cross-check the retailer listing.

    Args:
        product: The resolved product (name and category read by Claude Vision).
        package_marking: "eligible" or "none_seen" from vision, or None.
        retailer: the closest store listing from moss_index.find_match, or None.
        index_checked: True when Moss answered (so "no listing" is meaningful); False when it
            was not consulted or was unavailable.
    """
    result = _cross_check_retailer(_classify_by_rules(product, package_marking), retailer, index_checked)
    # Not in our data: assume it is NOT eligible, so it goes to the general Visa (team decision
    # 2026-10-24). A listing that disagrees with the rules (package_disagreement) still asks.
    if result.label == "could_not_confirm" and result.basis == "no_match":
        return EligibilityResult(label="not_eligible", basis="no_match")
    return result


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
