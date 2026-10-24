"""Seed data for the demo (technical spec 3.3). Pure data: no I/O, no network.

The tests and the demo script depend on these exact values. reset_demo() sends them
to the Postgres function in functions.sql, so the numbers live only here.
"""
from __future__ import annotations

import os

from lookup.normalize import normalize_key

# No barcodes: Claude Vision reads the product, so items are keyed by brand|name|size.
KEY_ADVIL = normalize_key("Advil", "Advil Ibuprofen 200mg", "200mg")
KEY_BANDAGES = normalize_key(None, "Bandages", None)
KEY_KETTLE_CORN = normalize_key(None, "Kettle Corn", None)

# The store printed at the top of the invoice. All mock data: override with REWIND_STORE_NAME and
# REWIND_STORE_ADDRESS to match wherever the demo is shown.
STORE = {"name": "Rewind Demo Store", "address": "123 Main Street, Berkeley, CA 94704"}

NESSIE_ACCOUNT_ENV = {"card_hsa_1": "NESSIE_HSA_ACCOUNT_ID", "card_fsa_1": "NESSIE_FSA_ACCOUNT_ID",
                      "card_visa_1": "NESSIE_VISA_ACCOUNT_ID"}

# Starting balance of each health card (HSA and FSA) per demo run:
# run 1: $340.00, run 2: $15.00 (declined-card run). Both cards start the same.
HEALTH_BALANCE_CENTS = {1: 34000, 2: 1500}
HSA_BALANCE_CENTS = HEALTH_BALANCE_CENTS      # old name, kept so existing imports keep working

# The FSA is the default health card (team decision, 2026-10-24; the tech spec still shows the HSA
# as default). With two health cards, an eligible item goes to the default without asking.
CARDS = [
    {"id": "card_hsa_1", "type": "hsa", "nickname": "HSA card",
     "balance_cents": 34000, "nessie_account_id": None, "status": "active", "is_default": False},
    {"id": "card_fsa_1", "type": "fsa", "nickname": "FSA card",
     "balance_cents": 34000, "nessie_account_id": None, "status": "active", "is_default": True},
    {"id": "card_visa_1", "type": "general", "nickname": "Visa credit",
     "balance_cents": 500000, "nessie_account_id": None, "status": "active", "is_default": False},
]

# Pre-cached so the demo cannot fail on a lookup (business spec 19.3).
DEMO_PRODUCTS = [
    {"product_key": KEY_ADVIL, "upc": None,
     "normalized_name": "Advil Ibuprofen 200mg", "brand": "Advil", "size": "200mg",
     "category": "pain_relief", "shelf_price_cents": 1299,
     "eligibility_label": "eligible", "eligibility_basis": "irs_category_rule", "source": "seeded"},
    {"product_key": KEY_BANDAGES, "upc": None,
     "normalized_name": "Bandages", "brand": None, "size": None,
     "category": "first_aid", "shelf_price_cents": 549,   # placeholder: set to the real shelf price
     "eligibility_label": "eligible", "eligibility_basis": "irs_category_rule", "source": "seeded"},
    {"product_key": KEY_KETTLE_CORN, "upc": None,
     "normalized_name": "Kettle Corn", "brand": None, "size": None,
     "category": "grocery", "shelf_price_cents": 499,
     "eligibility_label": "not_eligible", "eligibility_basis": "irs_category_rule",
     "source": "seeded"},
]

# Matching eligibility_items rows for the three demo items (spec 3.3, last paragraph).
# TODO(demo prep): put each item's public source page in source_url.
_DEMO_SOURCE = "hand_entered:demo-shelf"
_DEMO_COLLECTED_AT = "2026-10-24T00:00:00+00:00"

DEMO_ELIGIBILITY = [
    {"product_key": DEMO_PRODUCTS[0]["product_key"], "upc": None,
     "name": "Advil Ibuprofen 200mg", "brand": "Advil", "size": "200mg",
     "category_path": "pain_relief", "eligible": True,
     "source_url": _DEMO_SOURCE, "collected_at": _DEMO_COLLECTED_AT, "basis": "hand_entered"},
    {"product_key": DEMO_PRODUCTS[1]["product_key"], "upc": None,
     "name": "Bandages", "brand": None, "size": None,
     "category_path": "first_aid", "eligible": True,
     "source_url": _DEMO_SOURCE, "collected_at": _DEMO_COLLECTED_AT, "basis": "hand_entered"},
    {"product_key": DEMO_PRODUCTS[2]["product_key"], "upc": None,
     "name": "Kettle Corn", "brand": None, "size": None,
     "category_path": "grocery", "eligible": False,
     "source_url": _DEMO_SOURCE, "collected_at": _DEMO_COLLECTED_AT, "basis": "hand_entered"},
]

INSURERS = [
    {"id": "mock_plan_a", "display_name": "Mock Plan A (synthetic)", "has_rx_benefit": True,
     "copay_rules_json": {"omeprazole_20mg": {"copay_cents": 1000}}},
    {"id": "mock_plan_b", "display_name": "Mock Plan B (synthetic)", "has_rx_benefit": False,
     "copay_rules_json": {}},
]


def cards_for_run(run: int) -> list[dict]:
    """Seed cards with the HSA balance for the given demo run."""
    if run not in HEALTH_BALANCE_CENTS:
        raise ValueError(f"run must be 1 or 2, got {run!r}")
    cards = [dict(c) for c in CARDS]
    for card in cards:
        if card["type"] in ("hsa", "fsa"):
            card["balance_cents"] = HEALTH_BALANCE_CENTS[run]
        # Nessie account ids belong to whoever's sandbox is in use, so they come from the
        # environment (NESSIE_HSA_ACCOUNT_ID, NESSIE_VISA_ACCOUNT_ID); unset means not linked.
        card["nessie_account_id"] = os.environ.get(NESSIE_ACCOUNT_ENV[card["id"]]) or None
    return cards


def reset_payload(run: int) -> dict:
    """Parameters for the reset_demo Postgres function (functions.sql)."""
    return {
        "p_run": run,
        "p_cards": cards_for_run(run),
        "p_products": DEMO_PRODUCTS,
        "p_insurers": INSURERS,
        "p_eligibility": DEMO_ELIGIBILITY,
    }
