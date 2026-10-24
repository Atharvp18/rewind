"""Session shape, seed values, and mock insurance plans for the Rewind agents.

The orchestrator keeps one session per user in its uAgents ctx.storage.
Workers receive the session in a request and return an updated copy; they
never store it. Cards, balances and the cart are not here: they live in
Supabase (Atharv's data layer) and are loaded per request by agents/store.py.

Nothing in a session identifies the person. The name read from an insurance
card is held only in the orchestrator's memory, never here.
"""
from __future__ import annotations

import copy
from typing import Any

LOW_BALANCE_CENTS = 2000

# --- mock insurance plans -----------------------------------------------------
#
# All plan details are synthetic (tech spec decision 1). One plan is modeled on the
# structure of UnitedHealthcare Student Resources with OptumRx (tiers + pharmacy
# deductible); its numbers are illustrative, not that plan's real benefits.
#
# cost_sharing:
#   "copay"            flat amount per tier; the agent may give an ESTIMATE
#   "coinsurance"      a percentage of the drug's price; no dollar estimate possible
#   "deductible_first" member pays the full negotiated price until the deductible is met; no estimate
#   None               no prescription benefit
#
# formulary keys are "<drug>_<strength>" (medical vocabulary, matched exactly).
# A tier-0 drug has a $0 copay (e.g. some preventive generics).

_FORMULARY = {
    "omeprazole_20mg": {"tier": 1, "prior_auth": False},
    "atorvastatin_20mg": {"tier": 1, "prior_auth": False},
    "lisinopril_10mg": {"tier": 0, "prior_auth": False},
    "metformin_500mg": {"tier": 0, "prior_auth": False},
    "sumatriptan_50mg": {"tier": 2, "prior_auth": False},
    "semaglutide_0.5mg": {"tier": 3, "prior_auth": True},
}

INSURERS: dict[str, dict[str, Any]] = {
    "uhc_student": {
        "display_name": "UnitedHealthcare Student Resources plan",
        "short_name": "UnitedHealthcare plan",
        "modeled_on": "UnitedHealthcare Student Resources with OptumRx (illustrative numbers)",
        "has_rx_benefit": True,
        "rx_manager": "OptumRx",
        "cost_sharing": "copay",
        "pharmacy_deductible_cents": 12500,
        "tier_copays_cents": {0: 0, 1: 1500, 2: 4000, 3: 8000},
        "formulary": _FORMULARY,
    },
    "sunrise_ppo": {
        "display_name": "Sunrise PPO",
        "short_name": "Sunrise PPO",
        "modeled_on": "a typical employer PPO with flat copays",
        "has_rx_benefit": True,
        "rx_manager": "Sunrise Pharmacy Services",
        "cost_sharing": "copay",
        "pharmacy_deductible_cents": 0,
        "tier_copays_cents": {0: 0, 1: 1000, 2: 3500, 3: 7000},
        "formulary": _FORMULARY,
    },
    "evergreen_hsa": {
        "display_name": "Evergreen HSA Plan",
        "short_name": "Evergreen HSA Plan",
        "modeled_on": "a high-deductible health plan paired with an HSA",
        "has_rx_benefit": True,
        "rx_manager": "Evergreen Rx",
        "cost_sharing": "deductible_first",
        "pharmacy_deductible_cents": 165000,
        "tier_copays_cents": {},
        "formulary": _FORMULARY,
    },
    "harbor_choice": {
        "display_name": "Harbor Choice Plan",
        "short_name": "Harbor Choice Plan",
        "modeled_on": "a plan with prescription coinsurance",
        "has_rx_benefit": True,
        "rx_manager": "Harbor Rx",
        "cost_sharing": "coinsurance",
        "pharmacy_deductible_cents": 0,
        "tier_copays_cents": {},
        "formulary": _FORMULARY,
    },
    "basic_medical": {
        "display_name": "Basic Medical Plan",
        "short_name": "Basic Medical Plan",
        "modeled_on": "a medical-only plan without a pharmacy benefit",
        "has_rx_benefit": False,
        "rx_manager": None,
        "cost_sharing": None,
        "pharmacy_deductible_cents": 0,
        "tier_copays_cents": {},
        "formulary": {},
    },
}

PLAN_IDS = tuple(INSURERS)


def plan_profile(plan_id: str, source: str) -> dict[str, Any]:
    """A session-safe copy of a plan: no personal data, JSON-serializable keys."""
    p = copy.deepcopy(INSURERS[plan_id])
    p["tier_copays_cents"] = {str(k): v for k, v in p["tier_copays_cents"].items()}
    p.pop("modeled_on", None)
    p.pop("formulary", None)  # looked up by plan_id when needed, not copied per user
    return {"plan_id": plan_id, "source": source, **p}


def formulary_for(profile: dict) -> dict[str, Any]:
    plan = INSURERS.get(profile.get("plan_id", ""))
    return plan["formulary"] if plan else {}


def new_session() -> dict[str, Any]:
    """Conversation state only. Cards and cart live in Supabase (agents/store.py)."""
    return {
        "last_scan": None,
        "pending": None,
        "last_reply": "",
        "greeted": False,
        "insurance": None,   # a plan_profile(), from a card scan or the user naming a plan
    }
