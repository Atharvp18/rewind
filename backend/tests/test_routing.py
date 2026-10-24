"""Routing tests (technical spec 3.5 and the 4.5 matrix), using the demo numbers:
$340.00 / $15.00 HSA, $12.99 Advil, $5.49 bandages, $4.99 kettle corn."""
import itertools

import pytest

from payments.routing import Card, apply_moves, plan_checkout, route_item

ADVIL, BANDAGES, KETTLE = 1299, 549, 499


def hsa(balance=34000, **kw):
    return Card(id=kw.pop("id", "card_hsa_1"), type=kw.pop("type", "hsa"), nickname="HSA card",
                balance_cents=balance, **kw)


def visa(balance=500000, **kw):
    return Card(id=kw.pop("id", "card_visa_1"), type="general", nickname="Visa credit",
                balance_cents=balance, **kw)


def route(label="eligible", amount=ADVIL, cards=None, basis="shelf_price", copay_confirmed=False):
    cards = [hsa(), visa()] if cards is None else cards
    return route_item(label, amount, basis, cards, copay_confirmed, scan_id="s1")


# --- one item: the 4.5 matrix -----------------------------------------------------------------

def test_eligible_with_enough_balance_goes_to_the_hsa():
    r = route()
    assert (r.decision, r.card_id, r.reason_code) == ("route_to_hsa", "card_hsa_1", "eligible_sufficient_balance")
    assert (r.balance_before_cents, r.balance_after_cents) == (34000, 32701)
    assert r.amount_cents == ADVIL and r.amount_basis == "shelf_price" and r.scan_id == "s1"


def test_balance_exactly_equal_is_sufficient():
    r = route(cards=[hsa(ADVIL), visa()])
    assert r.decision == "route_to_hsa" and r.balance_after_cents == 0


def test_run2_insufficient_balance_asks_and_proposes_the_visa_without_choosing_it():
    r = route(amount=1848, cards=[hsa(1500), visa()])
    assert (r.decision, r.reason_code) == ("ask_user", "eligible_insufficient_balance")
    assert r.card_id is None and r.card_options == ["card_visa_1"]
    assert (r.reroute.from_card_id, r.reroute.to_card_id, r.reroute.reason) == (
        "card_hsa_1", "card_visa_1", "insufficient_balance")
    assert r.balance_before_cents == 1500 and r.balance_after_cents is None


@pytest.mark.parametrize("balance", [0, -500])
def test_zero_or_negative_balance_is_insufficient(balance):
    assert route(cards=[hsa(balance), visa()]).reason_code == "eligible_insufficient_balance"


def test_not_eligible_goes_to_the_general_card():
    r = route("not_eligible", KETTLE)
    assert (r.decision, r.card_id, r.reason_code) == ("route_to_general", "card_visa_1", "not_eligible")
    assert r.balance_after_cents == 500000 - KETTLE


def test_not_eligible_with_only_an_hsa_is_blocked_never_the_hsa():
    r = route("not_eligible", KETTLE, cards=[hsa()])
    assert (r.decision, r.card_id, r.reason_code) == ("blocked", None, "no_card_covers")


def test_could_not_confirm_asks_and_offers_every_active_card():
    r = route("could_not_confirm", cards=[hsa(), visa(), visa(id="old", status="closed")])
    assert (r.decision, r.card_id, r.reason_code) == ("ask_user", None, "eligibility_unconfirmed")
    assert r.card_options == ["card_hsa_1", "card_visa_1"]


def test_no_cards_is_blocked():
    r = route(cards=[])
    assert (r.decision, r.reason_code) == ("blocked", "no_card_linked")


def test_cards_that_are_not_active_count_as_not_linked():
    r = route(cards=[hsa(status="frozen"), visa(status="expired")])
    assert r.reason_code == "no_card_linked"


def test_frozen_hsa_sends_an_eligible_item_to_the_visa():
    r = route(cards=[hsa(status="frozen"), visa()])
    assert (r.decision, r.card_id, r.reason_code) == ("route_to_general", "card_visa_1", "no_health_card_linked")


def test_no_health_card_and_no_general_card_is_blocked():
    assert route(cards=[]).decision == "blocked"
    r = route("eligible", cards=[visa(status="closed")])
    assert r.reason_code == "no_card_linked"


def test_nothing_covers_it():
    r = route(amount=1848, cards=[hsa(1500), visa(1000)])
    assert (r.decision, r.card_id, r.reason_code) == ("blocked", None, "no_card_covers")


def test_two_health_cards_with_no_default_asks_which():
    r = route(cards=[hsa(), hsa(id="card_fsa_1", type="fsa"), visa()])
    assert (r.decision, r.reason_code) == ("ask_user", "multiple_health_cards")
    assert r.card_options == ["card_hsa_1", "card_fsa_1"] and r.card_id is None


def test_two_health_cards_with_a_default_uses_it():
    r = route(cards=[hsa(), hsa(id="card_fsa_1", type="fsa", is_default=True), visa()])
    assert (r.decision, r.card_id) == ("route_to_hsa", "card_fsa_1")


def test_an_fsa_alone_is_treated_like_an_hsa():
    r = route(cards=[hsa(type="fsa"), visa()])
    assert r.decision == "route_to_hsa"


def test_default_general_card_is_chosen_over_the_first():
    r = route("not_eligible", KETTLE, cards=[hsa(), visa(id="a"), visa(id="b", is_default=True)])
    assert r.card_id == "b"


# --- insurance copays ---------------------------------------------------------------------------

def test_a_copay_remainder_is_never_routed_until_a_source_confirms_it():
    r = route(amount=1000, basis="remaining_after_copay")
    assert (r.decision, r.reason_code, r.card_id) == ("ask_user", "copay_unconfirmed", None)
    assert r.amount_basis == "remaining_after_copay" and r.card_options == ["card_hsa_1", "card_visa_1"]


def test_zero_copay_adds_nothing_to_any_card():
    r = route(amount=0, basis="remaining_after_copay")
    assert (r.decision, r.reason_code, r.card_id) == ("blocked", "zero_copay_nothing_due", None)


def test_zero_copay_wins_even_with_no_cards_or_confirmation():
    assert route(amount=0, basis="remaining_after_copay", cards=[], copay_confirmed=True
                 ).reason_code == "zero_copay_nothing_due"


def test_a_confirmed_copay_follows_the_normal_rules_on_the_remainder_only():
    r = route(amount=1000, basis="remaining_after_copay", copay_confirmed=True)
    assert (r.decision, r.card_id, r.balance_after_cents) == ("route_to_hsa", "card_hsa_1", 33000)
    short = route(amount=2000, basis="remaining_after_copay", copay_confirmed=True, cards=[hsa(1500), visa()])
    assert short.reason_code == "eligible_insufficient_balance"      # judged on 2000, not on the full price


# --- invariants over every combination -----------------------------------------------------------

CARD_SETS = {
    "both": lambda: [hsa(), visa()],
    "hsa_only": lambda: [hsa()],
    "visa_only": lambda: [visa()],
    "low_hsa": lambda: [hsa(100), visa()],
    "broke": lambda: [hsa(0), visa(0)],
    "frozen_hsa": lambda: [hsa(status="frozen"), visa()],
    "two_health": lambda: [hsa(), hsa(id="f", type="fsa"), visa()],
    "none": lambda: [],
}


@pytest.mark.parametrize("label,basis,copay_ok,cards_name",
                         list(itertools.product(["eligible", "not_eligible", "could_not_confirm"],
                                                ["shelf_price", "remaining_after_copay"], [False, True], CARD_SETS)))
def test_invariants(label, basis, copay_ok, cards_name):
    cards = CARD_SETS[cards_name]()
    r = route_item(label, 1299, basis, cards, copay_ok)
    assert r.requires_confirmation is True
    by_id = {c.id: c for c in cards}
    if r.decision == "route_to_hsa":
        assert label == "eligible" and by_id[r.card_id].type in ("hsa", "fsa")
        assert by_id[r.card_id].status == "active" and by_id[r.card_id].balance_cents >= 1299
    if r.decision in ("route_to_hsa", "route_to_general"):
        assert r.card_id in by_id and by_id[r.card_id].status == "active"
    if r.decision in ("ask_user", "blocked") and r.reroute is None:
        assert r.card_id is None
    if basis == "remaining_after_copay" and not copay_ok:
        assert r.decision != "route_to_hsa"                     # the copay gate holds


# --- inputs ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [12.99, "1299", True, None])
def test_money_must_be_an_integer(bad):
    with pytest.raises(TypeError):
        route(amount=bad)


@pytest.mark.parametrize("amount,basis", [(-1, "shelf_price"), (0, "shelf_price"), (-1, "remaining_after_copay")])
def test_out_of_range_amounts_are_rejected(amount, basis):
    with pytest.raises(ValueError):
        route(amount=amount, basis=basis)


def test_unknown_label_and_basis_are_rejected():
    with pytest.raises(ValueError):
        route("maybe")
    with pytest.raises(ValueError):
        route(basis="coupon")


def test_cards_can_be_database_rows_with_extra_columns():
    rows = [{"id": "card_hsa_1", "type": "hsa", "nickname": "HSA card", "balance_cents": 34000,
             "status": "active", "is_default": True, "nessie_account_id": None},
            {"id": "card_visa_1", "type": "general", "nickname": "Visa credit", "balance_cents": 500000,
             "status": "active", "is_default": False, "nessie_account_id": None}]
    assert route(cards=rows).decision == "route_to_hsa"


def test_a_float_balance_is_rejected():
    with pytest.raises(Exception):
        Card(id="x", type="hsa", balance_cents=340.5)


# --- checkout group rules --------------------------------------------------------------------------

def item(id_, name, amount, card="card_hsa_1", label="eligible"):
    return {"id": id_, "display_name": name, "amount_cents": amount, "assigned_card_id": card,
            "eligibility_label": label}


DEMO_CART = [item("a", "Advil", ADVIL), item("b", "Bandages", BANDAGES), item("k", "Kettle corn", KETTLE,
                                                                           "card_visa_1", "not_eligible")]


def test_run1_cart_fits_and_totals_before_tax():
    plan = plan_checkout(DEMO_CART, [hsa(34000), visa()])
    assert plan.ok and plan.issues == []
    assert plan.total_cents == 2347
    assert [(g.card_id, g.subtotal_cents) for g in plan.groups] == [("card_hsa_1", 1848), ("card_visa_1", 499)]


def test_run2_keeps_advil_and_moves_the_bandages_to_the_visa():
    plan = plan_checkout(DEMO_CART, [hsa(1500), visa()])
    assert not plan.ok and len(plan.issues) == 1
    issue = plan.issues[0]
    assert issue.rule == 2 and issue.card_id == "card_hsa_1"
    assert (issue.balance_cents, issue.group_total_cents) == (1500, 1848)
    assert issue.keep_item_ids == ["a"]
    assert [(m.item_id, m.amount_cents, m.from_card_id, m.to_card_id, m.reason) for m in issue.moves] == [
        ("b", BANDAGES, "card_hsa_1", "card_visa_1", "group_exceeds_balance")]
    assert plan.groups[0].subtotal_cents == 1848           # the plan proposes; it does not apply


def test_applying_the_confirmed_move_makes_the_cart_fit():
    cards = [hsa(1500), visa()]
    moved = apply_moves(DEMO_CART, plan_checkout(DEMO_CART, cards).issues[0].moves)
    assert {i["id"]: i["assigned_card_id"] for i in moved} == {
        "a": "card_hsa_1", "b": "card_visa_1", "k": "card_visa_1"}
    assert plan_checkout(moved, cards).ok
    assert DEMO_CART[1]["assigned_card_id"] == "card_hsa_1"       # the original cart is untouched


def test_rule1_a_single_item_larger_than_the_balance_moves_whole():
    cart = [item("big", "Blood pressure monitor", 2000)]
    issue = plan_checkout(cart, [hsa(1500), visa()]).issues[0]
    assert issue.rule == 1 and issue.keep_item_ids == []
    assert issue.moves[0].reason == "insufficient_balance"


def test_rule3_nothing_covers_it_when_there_is_no_other_card():
    issue = plan_checkout([item("big", "Monitor", 2000)], [hsa(1500)]).issues[0]
    assert issue.rule == 3 and issue.uncovered_item_ids == ["big"] and issue.moves == []


def test_rule3_when_the_other_card_cannot_cover_it_either():
    cart = [item("a", "Advil", ADVIL), item("b", "Bandages", BANDAGES)]
    plan = plan_checkout(cart, [hsa(1500), visa(300)])
    assert [i.rule for i in plan.issues] == [3]
    assert plan.issues[0].keep_item_ids == ["a"] and plan.issues[0].uncovered_item_ids == ["b"]


def test_a_moved_item_counts_against_the_destination_balance():
    # The visa holds 800 of its 1500, so only 700 is free: the 900 item cannot move there.
    cart = [item("a", "A", 1000), item("b", "B", 900), item("c", "C", 800, "card_visa_1", "not_eligible")]
    plan = plan_checkout(cart, [hsa(1000), visa(1500)])
    assert [(i.rule, i.keep_item_ids, i.moves, i.uncovered_item_ids) for i in plan.issues] == [
        (3, ["a"], [], ["b"])]


def test_two_moves_share_the_destination_balance():
    cart = [item("a", "A", 600), item("b", "B", 500), item("c", "C", 500)]
    issue = plan_checkout(cart, [hsa(600), visa(1000)]).issues[0]       # visa fits b and c exactly
    assert issue.keep_item_ids == ["a"] and [m.item_id for m in issue.moves] == ["b", "c"]
    over = plan_checkout(cart, [hsa(600), visa(999)]).issues                  # one cent short for the second
    assert [i.rule for i in over] == [2, 3] and over[1].uncovered_item_ids == ["c"]


def test_first_fit_keeps_a_smaller_item_that_still_fits():
    cart = [item("x", "X", 1000), item("y", "Y", 600), item("z", "Z", 400)]
    issue = plan_checkout(cart, [hsa(1500), visa()]).issues[0]
    assert issue.keep_item_ids == ["x", "z"] and [m.item_id for m in issue.moves] == ["y"]


def test_ties_keep_cart_order():
    cart = [item("p", "P", 700), item("q", "Q", 700)]
    issue = plan_checkout(cart, [hsa(1000), visa()]).issues[0]
    assert issue.keep_item_ids == ["p"] and [m.item_id for m in issue.moves] == ["q"]


def test_items_not_confirmed_eligible_are_never_moved_onto_the_hsa():
    cart = [item("n", "Snack", 900, "card_visa_1", "not_eligible"),
            item("m", "Other", 900, "card_visa_1", "not_eligible")]
    plan = plan_checkout(cart, [hsa(34000), visa(1000)])
    assert plan.issues[0].rule == 3 and plan.issues[0].moves == []


def test_eligible_items_may_move_from_an_overdrawn_visa_to_the_hsa():
    cart = [item("a", "Advil", ADVIL, "card_visa_1", "eligible"), item("b", "Bandages", BANDAGES, "card_visa_1")]
    issue = plan_checkout(cart, [hsa(34000), visa(1500)]).issues[0]
    assert issue.keep_item_ids == ["a"] and issue.moves[0].to_card_id == "card_hsa_1"


def test_a_frozen_card_has_no_usable_balance():
    cart = [item("a", "Advil", ADVIL)]
    issue = plan_checkout(cart, [hsa(34000, status="frozen"), visa()]).issues[0]
    assert issue.moves[0].to_card_id == "card_visa_1" and issue.balance_cents == 0


def test_an_item_on_an_unknown_card_is_an_error():
    with pytest.raises(ValueError):
        plan_checkout([item("a", "Advil", ADVIL, "ghost")], [hsa(), visa()])


def test_plan_requires_integer_cents():
    with pytest.raises(TypeError):
        plan_checkout([item("a", "Advil", 12.99)], [hsa(), visa()])


def test_empty_cart_is_ok_with_a_zero_total():
    plan = plan_checkout([], [hsa(), visa()])
    assert plan.ok and plan.total_cents == 0 and plan.groups == []
