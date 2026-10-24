"""Offline sessions for the pure payment-rule tests: cards from Atharv's seed, empty cart."""
from agents.session import new_session as _blank
from data.seed import cards_for_run


def new_session(run: int = 1) -> dict:
    """One HSA (the default) plus the Visa, which is the shape these tests were written for.

    The real seed now also has an FSA, and the FSA is the default health card. These tests drive
    the cards by position (cards[0] is the HSA) and by the words "HSA card", so they get the
    two-card shape here; routing with an FSA default is covered in test_routing.py.
    """
    s = _blank()
    cards = [c for c in cards_for_run(run) if c["id"] != "card_fsa_1"]
    for card in cards:
        card["is_default"] = card["id"] == "card_hsa_1"
    s["cards"] = cards
    s["cart"] = []
    return s
