"""In-memory session state for the Rewind agents.

PLACEHOLDER until data/db.py (Supabase) is wired in. The orchestrator owns
one Session per ASI:One user; worker agents never hold state.
Seed values match tech spec section 3.3 so the demo numbers line up.
"""
from __future__ import annotations

import copy
from typing import Any

SEED_CARDS: list[dict[str, Any]] = [
    {"id": "card_hsa_1", "type": "hsa", "nickname": "HSA card",
     "balance_cents": 34000, "status": "active", "is_default": True},
    {"id": "card_visa_1", "type": "general", "nickname": "Visa credit",
     "balance_cents": 500000, "status": "active", "is_default": False},
]

# Pre-cached demo shelf (spec 19.3). Keyword -> product row. UPCs are placeholders
# until the real packages are scanned; eligibility mirrors the seeded eligibility_items rows.
DEMO_ITEMS: list[dict[str, Any]] = [
    {"keywords": ["advil", "ibuprofen"], "upc": "REPLACE_ADVIL",
     "name": "Advil Ibuprofen 200mg", "brand": "Advil", "size": "200mg",
     "category": "pain_relief", "is_medication": True, "amount_cents": 1299,
     "eligible": True, "basis": "hand_entered",
     "source_url": "https://www.advil.com/products/advil-tablets/"},
    {"keywords": ["bandage", "band-aid", "bandaid"], "upc": "REPLACE_BANDAGES",
     "name": "Bandages", "brand": None, "size": None,
     "category": "first_aid", "is_medication": False, "amount_cents": 549,
     "eligible": True, "basis": "hand_entered",
     "source_url": "https://www.irs.gov/publications/p502"},
    {"keywords": ["kettle corn", "popcorn"], "upc": "REPLACE_KETTLE_CORN",
     "name": "Kettle Corn", "brand": None, "size": None,
     "category": "grocery", "is_medication": False, "amount_cents": 499,
     "eligible": False, "basis": "irs_category_rule",
     "source_url": "https://www.irs.gov/publications/p502"},
]

LOW_BALANCE_CENTS = 2000


def find_demo_item(text: str) -> dict[str, Any] | None:
    lowered = text.lower()
    for item in DEMO_ITEMS:
        if any(kw in lowered for kw in item["keywords"]):
            return item
    return None


def new_session() -> dict[str, Any]:
    return {
        "cards": copy.deepcopy(SEED_CARDS),
        "cart": [],
        "last_scan": None,
        "pending": None,
        "last_reply": "",
    }


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}

    def get(self, user: str) -> dict[str, Any]:
        if user not in self._sessions:
            self._sessions[user] = new_session()
        return self._sessions[user]

    def reset(self, user: str, run: int = 1) -> dict[str, Any]:
        session = new_session()
        if run == 2:
            session["cards"][0]["balance_cents"] = 1500
        self._sessions[user] = session
        return session

    def end(self, user: str) -> None:
        self._sessions.pop(user, None)
