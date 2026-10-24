"""Eligibility classifier: determines whether a product is HSA/FSA eligible.

Classification chain:
1. Exact UPC match in eligibility_items
2. IRS category rules
3. "could_not_confirm" fallback
4. Cross-check against package marking
"""
from __future__ import annotations

import logging

from models.schemas import EligibilityResult, ProductResolution
from eligibility.irs_rules import lookup_category

logger = logging.getLogger(__name__)

_eligibility_lookup_upc = None


def _get_db_lookup():
    """Lazy import to avoid circular dependency with data.db."""
    global _eligibility_lookup_upc
    if _eligibility_lookup_upc is None:
        from data.db import eligibility_lookup_upc
        _eligibility_lookup_upc = eligibility_lookup_upc
    return _eligibility_lookup_upc


def classify_eligibility(
    product: ProductResolution,
    package_marking: str | None,
) -> EligibilityResult:
    """Classify a product's HSA/FSA eligibility.

    Args:
        product: The resolved product from the lookup chain.
        package_marking: "eligible" or "none_seen" from vision, or None.
    """
    # Step 1: Exact UPC match
    if product.upc:
        try:
            db_lookup = _get_db_lookup()
            row = db_lookup(product.upc)
            if row is not None:
                label = "eligible" if row["eligible"] else "not_eligible"
                result = EligibilityResult(
                    label=label,
                    confidence=None,
                    basis="upc_match",
                    source=row.get("basis", "retailer_index"),
                    collected_at=row.get("collected_at"),
                    matched_name=row.get("name"),
                )
                return _cross_check_package(result, package_marking)
        except Exception:
            logger.exception("DB eligibility lookup failed for UPC %s", product.upc)

    # Medication rule: without an exact UPC match, medications get could_not_confirm
    if product.is_medication:
        return EligibilityResult(
            label="could_not_confirm",
            confidence=None,
            basis="no_match",
            source=None,
            collected_at=None,
            matched_name=None,
        )

    # Step 2: IRS category rules
    rule = lookup_category(product.category)
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
