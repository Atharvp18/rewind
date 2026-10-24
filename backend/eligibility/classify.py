"""Eligibility classifier: determines whether a product is HSA/FSA eligible.

Classification chain (no barcodes: Claude Vision reads the product):
1. IRS category rules (shelf medicines must be in an IRS-backed category)
2. "could_not_confirm" fallback
3. Cross-check against package marking
4. Cross-check against the scraped retailer listing (Apify), if the exact product is in it
"""
from __future__ import annotations

import logging

from models.schemas import EligibilityResult, ProductResolution
from eligibility.irs_rules import lookup_category

logger = logging.getLogger(__name__)

def _retailer_row(product: ProductResolution) -> dict | None:
    """The scraped retailer listing for this exact product, if the database has one."""
    try:
        from data.db import eligibility_lookup_key
        return eligibility_lookup_key(product.product_key)
    except Exception:   # database down or not configured: the rules alone decide
        return None


def _cross_check_retailer(result: EligibilityResult, product: ProductResolution) -> EligibilityResult:
    """Second source. It can confirm the rule's answer or downgrade it when the two disagree.

    It never upgrades an answer by itself: only the IRS rules can say eligible.
    """
    if result.label == "could_not_confirm":
        return result
    row = _retailer_row(product)
    if row is None or row.get("basis") not in ("retailer_badge", "hand_entered"):
        return result
    retailer_label = "eligible" if row["eligible"] else "not_eligible"
    if retailer_label != result.label:
        return EligibilityResult(label="could_not_confirm", basis="package_disagreement",
                                 source="retailer_index", collected_at=row.get("collected_at"),
                                 matched_name=row.get("name"))
    return EligibilityResult(label=result.label, basis="retailer_match", source="retailer_index",
                             collected_at=row.get("collected_at"), matched_name=row.get("name"))


def classify_eligibility(
    product: ProductResolution,
    package_marking: str | None,
) -> EligibilityResult:
    """Classify a product's HSA/FSA eligibility, then cross-check the retailer listing.

    Args:
        product: The resolved product (name and category read by Claude Vision).
        package_marking: "eligible" or "none_seen" from vision, or None.
    """
    return _cross_check_retailer(_classify_by_rules(product, package_marking), product)


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
