"""Insurance rules for counter prescriptions (revised rules, 2026-10-24).

Insurance only applies to a prescription filled at the pharmacy counter. Shelf
items never involve it. Rewind never files a claim and never knows the real
copay: the pharmacy's claim to the plan decides that. Where the plan's
published structure allows, Rewind gives an ESTIMATE, labelled as one, and
every prescription answer ends with the pharmacist.

Drug names and strengths are the one hardcoded vocabulary (medical terms).
"""
from __future__ import annotations

import re
from typing import Any

from agents.common import dollars
from agents.session import INSURERS, formulary_for, plan_profile
from agents.speaker import Facts, say

_STRENGTH = re.compile(r"(\d+(?:\.\d+)?)\s*(mg|mcg|g|ml)\b", re.I)

ALL_FORMULARY_DRUGS = {key.split("_")[0] for plan in INSURERS.values() for key in plan["formulary"]}

PHARMACIST = "The pharmacist will confirm the exact amount."
COPAY_HSA = "Copays are usually HSA eligible."


def strength_of(text: str | None) -> str | None:
    m = _STRENGTH.search(text or "")
    return f"{m.group(1)}{m.group(2).lower()}" if m else None


def drug_word(name: str) -> str | None:
    lowered = name.lower()
    return next((d for d in ALL_FORMULARY_DRUGS if re.search(rf"\b{re.escape(d)}\b", lowered)), None)


def formulary_entry(profile: dict, name: str, size: str | None) -> dict | None:
    drug, strength = drug_word(name), strength_of(size) or strength_of(name)
    if not drug or not strength:
        return None
    return formulary_for(profile).get(f"{drug}_{strength}")


def also_sold_by_prescription(name: str) -> bool:
    """An OTC box of a drug that also comes as a prescription (e.g. omeprazole)."""
    return drug_word(name) is not None


def card_to_profile(card: Any) -> dict:
    """Turn a scrubbed CardExtract into a session-safe plan profile. No personal data."""
    insurer = (card.insurer or "").lower().replace(" ", "")
    if "unitedhealthcare" in insurer:
        profile = plan_profile("uhc_student", source="card")
        profile["has_rx_benefit"] = bool(card.has_rx_section)
        if card.rx_manager:
            profile["rx_manager"] = card.rx_manager
        return profile
    name = " ".join(p for p in (card.insurer, card.plan_name) if p) or "your insurance plan"
    printed = {c.label: round(c.amount_dollars * 100) for c in card.printed_rx_copays}
    return {
        "plan_id": "card_unknown",
        "source": "card",
        "display_name": name,
        "short_name": card.insurer or "your plan",
        "has_rx_benefit": bool(card.has_rx_section),
        "rx_manager": card.rx_manager,
        "cost_sharing": "copay" if printed else "unknown",
        "pharmacy_deductible_cents": 0,
        "tier_copays_cents": {},
        "printed_copays_cents": printed,
    }


def describe_plan(profile: dict | None) -> Facts:
    if not profile:
        return say("I don't have your insurance plan yet. You can show me your insurance card, or tell me your plan.")
    name = profile["short_name"]
    if not profile["has_rx_benefit"]:
        return say(f"You're on the {name}. It doesn't show prescription coverage.", name)
    mgr = profile.get("rx_manager")
    via = f" through {mgr}" if mgr else ""
    return say(f"You're on the {name}. It includes prescription coverage{via}.", name, *( [mgr] if mgr else []))


def coverage(profile: dict | None, name: str, size: str | None) -> tuple[Facts, int | None]:
    """What to say about a confirmed counter prescription, and the estimated copay to offer (or None).

    Never returns an amount unless the plan publishes a flat copay for this exact drug and strength.
    """
    if not profile:
        return say("That's okay. The pharmacist will tell you your share, and you can usually pay it "
                   "with your HSA card.", "pharmacist"), None

    plan = profile["short_name"]
    if not profile["has_rx_benefit"]:
        return say(f"Your {plan} may not include prescription coverage. Please ask the pharmacist.",
                   "pharmacist"), None

    sharing = profile.get("cost_sharing")
    entry = formulary_entry(profile, name, size)
    mgr = profile.get("rx_manager")

    if not formulary_for(profile):
        via = f" through {mgr}" if mgr else ""
        return say(f"Your plan covers prescriptions{via}. The pharmacist will tell you your share. {COPAY_HSA}",
                   "pharmacist", COPAY_HSA, *([mgr] if mgr else [])), None
    if entry is None:
        return say(f"I don't see this medicine on your {plan}'s drug list. Please ask the pharmacist.",
                   "pharmacist"), None
    if entry.get("prior_auth"):
        return say("This may need approval from your plan first. Please ask the pharmacist.", "pharmacist"), None
    if sharing == "coinsurance":
        return say("Your plan pays a percentage of the price, so I can't estimate this one. "
                   "The pharmacist will tell you the amount.", "pharmacist"), None
    if sharing == "deductible_first":
        return say("On your plan you pay the full price until your deductible is met, so I can't estimate this one. "
                   "The pharmacist will tell you the amount.", "pharmacist"), None

    copay = profile["tier_copays_cents"].get(str(entry["tier"]))
    if copay is None:
        return say("I don't have the copay for this. Please ask the pharmacist.", "pharmacist"), None
    if copay == 0:
        return say("Your plan shows no copay for this medicine. Please confirm at the pharmacy counter.",
                   "no copay"), None

    amount = dollars(copay)
    after = " after any deductible" if profile.get("pharmacy_deductible_cents") else ""
    return say(f"Your plan lists {amount} for this medicine{after}. That's an estimate. {PHARMACIST}",
               amount, "estimate", PHARMACIST), copay
