"""IRS category rule table for HSA/FSA eligibility.

This is the complete fallback if the Apify scrape is a no-go.
Rows marked "eligible" are backed by primary IRS sources (business spec section 23.1).
Everything not backed is "needs_review" → becomes "could_not_confirm" in speech.
"""
from __future__ import annotations

from typing import Literal

RuleResult = Literal["eligible", "not_eligible", "needs_review"]

IRS_CATEGORY_RULES: dict[str, RuleResult] = {
    "otc_medicine": "eligible",           # CARES Act: OTC medicines, no prescription needed
    "pain_relief": "eligible",            # CARES Act
    "cold_flu_allergy": "eligible",       # CARES Act
    "digestive_health": "eligible",       # CARES Act
    "menstrual_care": "eligible",         # CARES Act; Pub 969 (2025)
    "first_aid": "eligible",              # Pub 502 (2025), "Bandages"
    "diagnostic_device": "needs_review",  # Pub 502 names blood sugar and pregnancy test kits only
    "eye_care": "needs_review",           # Pub 502: contact lenses and saline solution "needed for medical reasons"
    "foot_care": "needs_review",          # no support found in Pub 502 or 969
    "sunscreen": "needs_review",          # no support found in Pub 502 or 969
    "vitamins_supplements": "needs_review",  # Pub 502 "Nutritional Supplements": only if a doctor treats a diagnosed condition
    "baby_care": "needs_review",          # Pub 502 excludes baby sitting and childcare only
    "other": "needs_review",
    "personal_care": "not_eligible",      # Pub 502 "Personal Use Items": toothpaste is a personal expense
    "cosmetics": "not_eligible",          # Pub 502: not primarily for medical care
    "grocery": "not_eligible",            # Pub 502: must be primarily to prevent or treat illness
    "household": "not_eligible",          # Pub 502 "Personal Use Items"
}

# Where each row comes from, checked against the IRS text on 2026-10-24.
# "checked" rows quote the source; "unverified" rows stay needs_review on purpose.
_NEWS = "https://www.irs.gov/newsroom/irs-outlines-changes-to-health-care-spending-available-under-cares-act"
_P502 = "https://www.irs.gov/publications/p502"
_P969 = "https://www.irs.gov/publications/p969"

CATEGORY_SOURCES: dict[str, dict[str, str]] = {
    "otc_medicine": {"status": "checked", "url": _NEWS,
                     "quote": "over-the-counter products and medications are now reimbursable without a prescription"},
    "pain_relief": {"status": "checked", "url": _NEWS, "quote": "over-the-counter products and medications are now reimbursable without a prescription"},
    "cold_flu_allergy": {"status": "checked", "url": _NEWS, "quote": "over-the-counter products and medications are now reimbursable without a prescription"},
    "digestive_health": {"status": "checked", "url": _NEWS, "quote": "over-the-counter products and medications are now reimbursable without a prescription"},
    "menstrual_care": {"status": "checked", "url": _P969,
                       "quote": "Amounts paid for menstrual care products are treated as paid for medical care"},
    "first_aid": {"status": "checked", "url": _P502,
                  "quote": "You can include in medical expenses the cost of medical supplies such as bandages"},
    "diagnostic_device": {"status": "unverified", "url": _P502,
                          "quote": "names a blood sugar test kit and a pregnancy test kit, not the whole category"},
    "eye_care": {"status": "unverified", "url": _P502,
                 "quote": "contact lenses needed for medical reasons, and saline solution and enzyme cleaner"},
    "foot_care": {"status": "unverified", "url": _P502, "quote": "not found in the publication"},
    "sunscreen": {"status": "unverified", "url": _P502, "quote": "not found in the publication"},
    "vitamins_supplements": {"status": "checked", "url": _P502,
                             "quote": "can't include ... vitamins ... unless they are recommended by a medical practitioner as treatment for a specific medical condition"},
    "baby_care": {"status": "unverified", "url": _P502, "quote": "only baby sitting and childcare are excluded"},
    "other": {"status": "unverified", "url": _P502, "quote": "unknown category"},
    "personal_care": {"status": "checked", "url": _P502,
                      "quote": "the cost of a toothbrush and toothpaste is a nondeductible personal expense"},
    "cosmetics": {"status": "checked", "url": _P502,
                  "quote": "Medical care expenses must be primarily to alleviate or prevent a physical or mental disability or illness"},
    "grocery": {"status": "checked", "url": _P502,
                "quote": "They don't include expenses that are merely beneficial to general health"},
    "household": {"status": "checked", "url": _P502,
                  "quote": "Personal Use Items: an item ordinarily used for personal, living, or family purposes"},
}

# Note: Pub 502 is the medical-expense deduction and still says a drug that isn't
# prescribed can't be deducted. HSA/FSA reimbursement is different: the CARES Act
# (effective for amounts paid after Dec. 31, 2019) made OTC medicines eligible there.


CONTROLLED_CATEGORIES = list(IRS_CATEGORY_RULES.keys())


def lookup_category(category: str) -> RuleResult:
    """Look up the IRS eligibility rule for a product category.

    Returns "needs_review" for unknown categories.
    """
    return IRS_CATEGORY_RULES.get(category, "needs_review")


# --- readable form of the table -------------------------------------------------

CATEGORY_LABELS = {
    "otc_medicine": "Over-the-counter medicine", "pain_relief": "Pain relief medicine",
    "cold_flu_allergy": "Cold, flu and allergy medicine", "digestive_health": "Digestive health medicine",
    "menstrual_care": "Menstrual care products", "first_aid": "First aid supplies (bandages)",
    "diagnostic_device": "Diagnostic devices", "eye_care": "Eye care", "foot_care": "Foot care",
    "sunscreen": "Sunscreen", "vitamins_supplements": "Vitamins and supplements", "baby_care": "Baby care",
    "other": "Other / unknown", "personal_care": "Personal care (toothpaste, lotion)",
    "cosmetics": "Cosmetics", "grocery": "Grocery and snacks", "household": "Household items",
}
ANSWER_WORDS = {"eligible": "Eligible", "not_eligible": "Not eligible", "needs_review": "Could not confirm"}


def rule_rows(collected_at: str) -> list[dict]:
    """eligibility_items rows for the categories with a yes/no answer (the table needs a boolean).

    Needs-review categories are left out: the table cannot hold "unknown".
    """
    rows = []
    for category, rule in IRS_CATEGORY_RULES.items():
        if rule == "needs_review":
            continue
        rows.append({
            "product_key": f"rule:{category}", "upc": None, "brand": None, "size": None,
            "name": f"{CATEGORY_LABELS[category]} (IRS category rule)",
            "category_path": category, "eligible": rule == "eligible",
            "source_url": CATEGORY_SOURCES[category]["url"],
            "collected_at": collected_at, "basis": "irs_category_rule",
        })
    return rows


def markdown_table() -> str:
    lines = ["# HSA/FSA category rules", "",
             "Generated from `eligibility/irs_rules.py`. Do not edit by hand.", "",
             "| Category | Answer | Checked | Source | What the source says |", "|---|---|---|---|---|"]
    for category, rule in IRS_CATEGORY_RULES.items():
        src = CATEGORY_SOURCES[category]
        lines.append(f"| {CATEGORY_LABELS[category]} | {ANSWER_WORDS[rule]} | {src['status']} | "
                     f"[IRS]({src['url']}) | {src['quote']} |")
    return "\n".join(lines) + "\n"
