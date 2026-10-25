"""Which store the user said they are in (PROPOSED, prototype only).

Spec conflict: tech spec decision 8 and business spec 6.6 / 12 say store addresses are never
derived from location. This module is the prototype Nak asked for, kept small on purpose: the
phone's position is compared with three seeded mock stores and thrown away. Nothing about the
position is stored, logged, or put in an invoice; only the store the user confirmed is kept, in
memory, for this single-user demo server.
"""
from __future__ import annotations

import math

from data import seed

ARRIVE_METERS = 150          # this close to a store counts as "at the store"
LEAVE_METERS = 250           # leaving is judged wider, so standing at the door does not flicker

_current: dict | None = None


def public(store: dict) -> dict:
    """A store as the app sees it: no coordinates."""
    return {k: store[k] for k in ("id", "name", "address", "phone")}


def by_id(store_id: str | None) -> dict | None:
    return next((s for s in seed.CHECKIN_STORES if s["id"] == store_id), None)


def meters_between(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def nearest(lat: float, lng: float, within: float = ARRIVE_METERS) -> dict | None:
    scored = [(meters_between(lat, lng, s["lat"], s["lng"]), s) for s in seed.CHECKIN_STORES]
    close = [x for x in scored if x[0] <= within]
    return min(close, key=lambda x: x[0])[1] if close else None


def current() -> dict | None:
    return _current


def check_in(store: dict) -> None:
    global _current
    _current = store


def check_out() -> None:
    global _current
    _current = None
