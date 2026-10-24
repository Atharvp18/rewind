"""Offline sessions for the pure payment-rule tests: cards from Atharv's seed, empty cart."""
import copy

from agents.session import new_session as _blank
from data.seed import CARDS, HSA_BALANCE_CENTS


def new_session(run: int = 1) -> dict:
    s = _blank()
    s["cards"] = copy.deepcopy(CARDS)
    s["cards"][0]["balance_cents"] = HSA_BALANCE_CENTS[run]
    s["cart"] = []
    return s
