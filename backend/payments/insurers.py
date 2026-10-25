"""Mock prescription benefits for the insurers on the shopper's card (data/insurer_benefits.json).

The app does not know the member's real plan or copay, so the agent only says what that insurer's
plans TYPICALLY charge for a generic and sends the shopper to the pharmacist to confirm the copay
and coverage for this exact medication (the pharmacy's claim decides the amount).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from speech.compose import money

PATH = Path(__file__).parent.parent / "data" / "insurer_benefits.json"


@lru_cache(maxsize=1)
def _insurers() -> list[dict]:
    try:
        return json.loads(PATH.read_text())["insurers"]
    except (OSError, ValueError, KeyError):
        return []


def find(insurer_name: str | None) -> dict | None:
    """The insurer whose name (or a known alias) appears in what the card says, else None."""
    text = (insurer_name or "").lower()
    if not text:
        return None
    return next((i for i in _insurers() if any(m in text for m in i["match"])), None)


def pharmacist_tip(insurer_name: str | None) -> str | None:
    """One spoken sentence for a prescription, or None for an insurer we have no data on."""
    insurer = find(insurer_name)
    if insurer is None:
        return None
    generic = next((t for t in insurer["tiers"] if t.get("copay_cents") is not None), None)
    typical = f" Generics are often around {money(generic['copay_cents'])}." if generic else ""
    return (f"Your {insurer['name']} plan may cover part of this.{typical} "
            "Please ask the pharmacist to confirm your copay and coverage for this medication before you pay, "
            "since it can cost you less.")
