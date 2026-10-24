"""IRS category rule table for HSA/FSA eligibility.

This is the complete fallback if the Apify scrape is a no-go.
Rows marked "eligible" are backed by primary IRS sources (business spec section 23.1).
Everything not backed is "needs_review" → becomes "could_not_confirm" in speech.
"""
from __future__ import annotations

from typing import Literal

RuleResult = Literal["eligible", "not_eligible", "needs_review"]

IRS_CATEGORY_RULES: dict[str, RuleResult] = {
    "otc_medicine": "eligible",           # CARES Act, IRS newsroom
    "pain_relief": "eligible",            # CARES Act
    "cold_flu_allergy": "eligible",       # CARES Act
    "digestive_health": "eligible",       # CARES Act
    "menstrual_care": "eligible",         # CARES Act, IRS newsroom
    "first_aid": "eligible",             # IRS Pub 502, "medical supplies such as bandages"
    "diagnostic_device": "needs_review",  # not yet checked against a primary source
    "eye_care": "needs_review",           # not yet checked against a primary source
    "foot_care": "needs_review",          # medicated versus cosmetic differs
    "sunscreen": "needs_review",          # not verified in this project's sources
    "vitamins_supplements": "needs_review",  # generally needs a medical reason
    "baby_care": "needs_review",
    "other": "needs_review",
    "personal_care": "not_eligible",      # unless medicated
    "cosmetics": "not_eligible",
    "grocery": "not_eligible",            # resolves kettle corn
    "household": "not_eligible",
}


CONTROLLED_CATEGORIES = list(IRS_CATEGORY_RULES.keys())


def lookup_category(category: str) -> RuleResult:
    """Look up the IRS eligibility rule for a product category.

    Returns "needs_review" for unknown categories.
    """
    return IRS_CATEGORY_RULES.get(category, "needs_review")
