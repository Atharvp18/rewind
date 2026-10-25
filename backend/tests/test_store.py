"""agents/store.py: session <-> Supabase sync, with data.db replaced by a recorder."""
import pytest

from agents import payment_agent, store
from agents.intent import Entities, Intent
from data import db
from tests.helpers import new_session


@pytest.fixture
def calls(monkeypatch):
    log = []
    for name in ("clear_cart", "remove_last_cart_item", "reassign_cart_item", "save_scan", "add_cart_item"):
        monkeypatch.setattr(db, name, lambda *a, _n=name, **k: log.append((_n, a, k)))
    monkeypatch.setattr(db, "confirm_checkout", lambda key, splits: log.append(("confirm_checkout", key, splits)))
    return log


def scan(name="Bandages", cents=549, label="eligible"):
    return {"scan_id": "s1", "state": "resolved",
            "product": {"product_key": "upc:2", "name": name, "amount_cents": cents, "is_medication": False},
            "eligibility": {"label": label, "basis": "upc_match"}}


def add(session):
    _, s = payment_agent.recommend(session, scan())
    return payment_agent.handle_intent(Intent(intent="confirm"), s)[1]


def test_new_item_saves_scan_then_cart_row_in_atharvs_columns(calls):
    before = new_session()
    after = add(before)
    assert store.save(before, after, "r1") is None
    assert [c[0] for c in calls] == ["save_scan", "add_cart_item"]
    args, kw = calls[1][1], calls[1][2]
    assert args[1:6] == ("upc:2", "Bandages", 549, "shelf_price", "card_hsa_1")
    assert kw["item_id"] == after["cart"][0]["id"]


def test_checkout_goes_through_atomic_function_with_request_id(calls):
    s = add(new_session())
    before = {**s, "pending": {"scope": "confirm_checkout"}}
    after = payment_agent.handle_intent(Intent(intent="confirm"), before)[1]
    store.save(before, after, "req-9")
    assert calls == [("confirm_checkout", "req-9", [{"card_id": "card_hsa_1", "amount_cents": 549}])]


def test_moved_items_are_reassigned_before_the_charge(calls):
    """History reads the card from each cart row, so a move made at checkout must be saved first."""
    s = new_session()
    s["cards"][0]["balance_cents"] = 1500                      # the HSA can take one item, not both
    for item in (scan("Advil", 1299), scan("Bandages", 549)):
        _, s = payment_agent.recommend(s, item)
        _, s = payment_agent.handle_intent(Intent(intent="confirm"), s)
    _, s = payment_agent.handle_intent(Intent(intent="checkout"), s)
    before = s
    after = payment_agent.handle_intent(Intent(intent="confirm"), before)[1]
    calls.clear()
    store.save(before, after, "req-move")
    assert [c[0] for c in calls] == ["reassign_cart_item", "confirm_checkout"]
    moved = calls[0][1]
    assert moved[1] == "card_visa_1" and moved[2] is True       # eligible item on the Visa: possible reimbursement
    assert "checkout_moves" not in store.strip(after)


def test_refused_checkout_says_nothing_was_charged(monkeypatch):
    def refuse(*a):
        raise db.CheckoutFailed("E_CARD_CANNOT_PAY")
    monkeypatch.setattr(db, "confirm_checkout", refuse)
    assert store.save({"cart": []}, {"cart": [], "checkout_splits": [{"card_id": "x", "amount_cents": 1}]}, "r") \
        is store.CHECKOUT_FAILED


def test_remove_last_and_clear(calls):
    s = add(new_session())
    after = payment_agent.handle_intent(Intent(intent="remove_last"), s)[1]
    store.save(s, after, "r")
    assert calls[-1][0] == "clear_cart"


def test_strip_keeps_balances_out_of_orchestrator_storage():
    out = store.strip({**new_session(), "checkout_splits": []})
    assert not {"cards", "cart", "checkout_splits"} & out.keys()


def test_prescription_row_never_carries_the_drug(calls):
    from tests.test_insurance import rx, start
    from agents.session import plan_profile
    s = new_session()
    s["insurance"] = plan_profile("uhc_student", "card")
    _, s = start(s, rx())
    _, s = payment_agent.handle_intent(Intent(intent="confirm"), s)
    before = s
    _, after = payment_agent.handle_intent(Intent(intent="confirm"), s)
    store.save({**before, "cart": []}, after, "r")
    product = calls[0][1][1]
    assert product["name"] == "your prescription" and product["product_key"] == "prescription"
    assert "omeprazole" not in str(calls).lower()
