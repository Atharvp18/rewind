"""In-memory test double of data/db.py (technical spec 4.5). Tests only, never used at runtime.

It mirrors the Postgres functions in functions.sql: prompts expire and are single use, checkout is
idempotent and all or nothing and empties the cart, "remove last" takes the highest seq.
`install(monkeypatch)` swaps every public db function for the matching method, so endpoints that
call `db.something()` run unchanged.
"""
from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone

from data import db, seed

PUBLIC = (
    "health", "get_cards", "cache_get", "cache_put", "eligibility_lookup_upc", "save_scan", "get_scan", "get_cart",
    "add_cart_item", "reassign_cart_item", "remove_last_cart_item", "pop_last_cart_item", "clear_cart",
    "create_prompt", "consume_prompt", "get_payment", "get_payment_by_id", "confirm_checkout", "reset_demo",
)


class FakeDB:
    def __init__(self, run: int = 1):
        self.clock = 0.0
        self.down = False                     # True: every call raises DBUnavailable
        self.calls: list[str] = []
        self._load(run)

    def _load(self, run: int) -> None:
        self.cards = {c["id"]: dict(c) for c in seed.cards_for_run(run)}
        self.items: list[dict] = []
        self.scans: dict[str, dict] = {}
        self.prompts: dict[str, dict] = {}
        self.payments: dict[str, dict] = {}
        self.cache: dict[str, dict] = {}
        self._seq = 0

    def install(self, monkeypatch) -> "FakeDB":
        for name in PUBLIC:
            monkeypatch.setattr(db, name, self._wrap(name))
        # Tiea's lookup chain imports these functions once and keeps them
        from lookup import chain
        monkeypatch.setattr(chain, "_cache_get", db.cache_get)
        monkeypatch.setattr(chain, "_cache_put", db.cache_put)
        return self

    def _wrap(self, name):
        method = getattr(self, name)

        def call(*args, **kwargs):
            self.calls.append(name)
            if self.down:
                raise db.DBUnavailable("fake db is down")
            return method(*args, **kwargs)
        return call

    # --- test controls -------------------------------------------------------------------
    def advance(self, seconds: float) -> None:
        self.clock += seconds

    def set_balance(self, card_id: str, cents: int) -> None:
        self.cards[card_id]["balance_cents"] = cents

    # --- the db.py surface ---------------------------------------------------------------
    def health(self):
        return {"reachable": not self.down, "latency_ms": 1}

    def get_cards(self):
        return [dict(c) for _, c in sorted(self.cards.items())]

    def cache_get(self, key):
        return self.cache.get(key)

    def cache_put(self, key, row):
        self.cache[key] = dict(row, product_key=key)

    def eligibility_lookup_upc(self, upc):
        for row in seed.DEMO_ELIGIBILITY:
            if row["upc"] == upc:
                return dict(row)
        return None

    def save_scan(self, scan_id, product, eligibility):
        self.scans[scan_id] = {"scan_id": scan_id, "state": product.get("state", "unresolved"),
                               "product_json": product, "eligibility_json": eligibility}

    def get_scan(self, scan_id):
        s = self.scans.get(scan_id)
        return copy.deepcopy(s) if s else None

    def get_cart(self):
        groups = []
        for card in self.get_cards():
            rows = [copy.deepcopy(i) for i in self.items if i["assigned_card_id"] == card["id"]]
            if rows:
                groups.append({"card_id": card["id"], "nickname": card["nickname"], "items": rows,
                               "subtotal_cents": sum(i["amount_cents"] for i in rows)})
        return {"groups": groups, "total_cents": sum(g["subtotal_cents"] for g in groups)}

    def add_cart_item(self, scan_id, product_key, display_name, amount_cents, amount_basis,
                      assigned_card_id, eligibility_label, user_overrode_card=False, item_id=None):
        if isinstance(amount_cents, bool) or not isinstance(amount_cents, int):
            raise TypeError("amount_cents must be an integer number of cents")
        if scan_id not in self.scans:
            raise AssertionError(f"cart item references a scan that was never saved: {scan_id}")
        if assigned_card_id not in self.cards:
            raise AssertionError(f"unknown card {assigned_card_id}")
        self._seq += 1
        self.items.append({"id": item_id or uuid.uuid4().hex, "seq": self._seq, "scan_id": scan_id,
                           "product_key": product_key, "display_name": display_name,
                           "amount_cents": amount_cents, "amount_basis": amount_basis,
                           "assigned_card_id": assigned_card_id, "eligibility_label": eligibility_label,
                           "user_overrode_card": user_overrode_card})
        return self.get_cart()

    def reassign_cart_item(self, item_id, card_id, user_overrode_card=True):
        for item in self.items:
            if item["id"] == item_id:
                item.update(assigned_card_id=card_id, user_overrode_card=user_overrode_card)

    def pop_last_cart_item(self):
        removed = self.items.pop() if self.items else None
        return removed, self.get_cart()

    def remove_last_cart_item(self):
        return self.pop_last_cart_item()[1]

    def clear_cart(self):
        self.items = []

    def create_prompt(self, scope, scan_id, payload, ttl_seconds=15):
        prompt_id = uuid.uuid4().hex
        self.prompts[prompt_id] = {"scope": scope, "scan_id": scan_id, "payload": payload or {},
                                   "expires_at": self.clock + ttl_seconds, "consumed": False}
        return prompt_id

    def consume_prompt(self, prompt_id, expected_scope):
        p = self.prompts.get(prompt_id)
        if not p or p["consumed"] or p["scope"] != expected_scope or p["expires_at"] <= self.clock:
            raise db.PromptExpired(prompt_id)
        p["consumed"] = True
        return {"prompt_id": prompt_id, "scope": p["scope"], "scan_id": p["scan_id"],
                "payload": copy.deepcopy(p["payload"])}

    def _balances(self):
        return [{"id": c["id"], "nickname": c["nickname"], "balance_cents": c["balance_cents"]}
                for c in self.get_cards()]

    def get_payment(self, key):
        p = self.payments.get(key)
        if not p:
            return None
        return {"payment_id": p["payment_id"], "total_cents": p["total_cents"], "splits": p["splits"],
                "new_balances": self._balances(), "replayed": True, "created_at": p["created_at"]}

    def get_payment_by_id(self, payment_id):
        for key, p in self.payments.items():
            if p["payment_id"] == payment_id:
                return self.get_payment(key)
        return None

    def confirm_checkout(self, idempotency_key, splits):
        if not splits:
            raise db.CheckoutFailed("E_EMPTY_CART")
        if idempotency_key in self.payments:
            return self.get_payment(idempotency_key)
        trial = {k: v["balance_cents"] for k, v in self.cards.items()}
        for s in splits:
            if isinstance(s["amount_cents"], bool) or not isinstance(s["amount_cents"], int):
                raise TypeError("amount_cents must be an integer number of cents")
            if s["amount_cents"] <= 0:
                raise db.CheckoutFailed("E_BAD_AMOUNT", s["card_id"])
            card = self.cards.get(s["card_id"])
            if card is None or card["status"] != "active" or trial[s["card_id"]] < s["amount_cents"]:
                raise db.CheckoutFailed("E_CARD_CANNOT_PAY", s["card_id"])
            trial[s["card_id"]] -= s["amount_cents"]
        for card_id, balance in trial.items():                  # all or nothing: only after every check
            self.cards[card_id]["balance_cents"] = balance
        payment_id = uuid.uuid4().hex
        self.payments[idempotency_key] = {"payment_id": payment_id, "splits": copy.deepcopy(splits),
                                          "total_cents": sum(s["amount_cents"] for s in splits),
                                          "created_at": datetime.now(timezone.utc).isoformat()}
        self.items = []
        return {"payment_id": payment_id, "total_cents": self.payments[idempotency_key]["total_cents"],
                "splits": splits, "new_balances": self._balances(), "replayed": False}

    def reset_demo(self, run=1):
        if run not in (1, 2):
            raise db.CheckoutFailed("E_BAD_RUN")
        self._load(run)
        return {"cards": self.get_cards(), "cart": self.get_cart()}
