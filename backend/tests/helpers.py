"""Offline sessions for the pure payment-rule tests: cards from Atharv's seed, empty cart."""
from agents.session import new_session as _blank
from data.seed import cards_for_run


def new_session(run: int = 1, fsa: bool = False) -> dict:
    """One HSA (the default) plus the Visa, which is the shape most of these tests were written for.

    The real seed also has an FSA, and the FSA is the default health card. The older tests drive
    the cards by position (cards[0] is the HSA) and by the words "HSA card", so they get the
    two-card shape. fsa=True keeps the seed as it is (HSA + FSA default + Visa) for the
    FSA-first tests in test_hsa_fsa.py; routing with an FSA default is also in test_routing.py.
    """
    s = _blank()
    cards = [c for c in cards_for_run(run) if fsa or c["id"] != "card_fsa_1"]
    if not fsa:
        for card in cards:
            card["is_default"] = card["id"] == "card_hsa_1"
    s["cards"] = cards
    s["cart"] = []
    return s
