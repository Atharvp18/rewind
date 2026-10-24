"""Offline sessions for the pure payment-rule tests: cards from Atharv's seed, empty cart."""
import copy

from agents.session import new_session as _blank
from data.seed import CARDS, FSA_BALANCE_CENTS, HSA_BALANCE_CENTS


def new_session(run: int = 1, fsa: bool = False) -> dict:
    """HSA + Visa by default (the HSA-only rules); fsa=True adds the seed FSA card."""
    s = _blank()
    s["cards"] = [copy.deepcopy(c) for c in CARDS if fsa or c["type"] != "fsa"]
    for c in s["cards"]:
        if c["type"] == "hsa":
            c["balance_cents"] = HSA_BALANCE_CENTS[run]
        if c["type"] == "fsa":
            c["balance_cents"] = FSA_BALANCE_CENTS[run]
    s["cart"] = []
    return s
