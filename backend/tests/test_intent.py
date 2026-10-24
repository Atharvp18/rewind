"""Intent guard, speaker validation, and code-enforced guardrails. No network."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from agents import payment_agent, product_agent
from agents.intent import Entities, Intent, REFUSALS, classify_intent, medical_guard
from tests.helpers import new_session
from agents.speaker import say, validate
from tests.test_agents import ADVIL, KETTLE_CORN, YOGA_MAT, go, incoming, scan


# --- the only hardcoded vocabulary: medical terms ------------------------------

def test_medical_guard_matches_medical_terms_only():
    assert medical_guard("is it safe to take this with alcohol")
    assert medical_guard("how many should I take a day")
    assert medical_guard("does this interact with my blood pressure pills")
    assert not medical_guard("is advil hsa eligible")
    assert not medical_guard("what's in my cart")


@pytest.mark.asyncio
async def test_medical_guard_overrides_classifier():
    i = await classify_intent("is it safe to take two of these", new_session())
    assert i.intent == "medical_advice"


@pytest.mark.asyncio
async def test_stub_mode_never_guesses_from_words():
    for phrase in ("checkout", "yes", "add it", "what's in my cart"):
        assert (await classify_intent(phrase, new_session())).intent == "unclear"


@pytest.mark.asyncio
async def test_bare_image_is_a_scan():
    assert (await classify_intent("", new_session(), has_image=True)).intent == "scan_product"


# --- speaker validation: phrasing is free, facts are not -------------------------

def test_validate_accepts_rephrasing_with_all_facts():
    f = say("Advil, $12.99. HSA eligible. Your HSA card balance is $340.00. Want to use your HSA card?",
            "Advil", "$12.99", "HSA eligible", "HSA card", "$340.00")
    assert validate("That's Advil at $12.99, and it's HSA eligible. You have $340.00 on your HSA card — want to use it?", f)


def test_validate_rejects_missing_fact():
    f = say("Advil, $12.99. HSA eligible.", "Advil", "$12.99", "HSA eligible")
    assert not validate("That's Advil and it's HSA eligible. Want it?", f)


def test_validate_rejects_invented_number():
    f = say("Advil, $12.99. HSA eligible.", "Advil", "$12.99", "HSA eligible")
    assert not validate("Advil is $12.99, HSA eligible, usually about $15 elsewhere.", f)


def test_validate_rejects_changed_price():
    f = say("Advil, $12.99.", "Advil", "$12.99")
    assert not validate("Advil is $12.89.", f)


def test_validate_rejects_empty_or_huge():
    f = say("Hi.")
    assert not validate("", f) and not validate("x" * 401, f)


@pytest.mark.asyncio
async def test_fixed_facts_are_never_rephrased():
    from agents.speaker import render
    assert await render(say(REFUSALS["medical_advice"], fixed=True)) == REFUSALS["medical_advice"]


# --- guardrails enforced in code, regardless of what the classifier says ------

def test_not_eligible_item_cannot_go_on_hsa_even_if_asked():
    s = new_session()
    _, s = payment_agent.recommend(s, KETTLE_CORN())
    f, s = go("add_to_cart", s, card="hsa")
    assert f.template == REFUSALS["route_ineligible_to_hsa"] and f.fixed
    assert s["cart"] == []


def test_route_ineligible_intent_offers_visa():
    s = new_session()
    _, s = payment_agent.recommend(s, KETTLE_CORN())
    f, s = go("route_ineligible_to_hsa", s)
    assert "Visa credit" in f.template and s["pending"]["scope"] == "confirm_add"
    f, s = go("confirm", s)
    assert s["cart"][0]["assigned_card_id"] == "card_visa_1"


def test_medical_advice_is_refused_with_fixed_wording():
    f, _ = go("medical_advice", new_session())
    assert f.template == "I can't give medical advice. Please ask the pharmacist." and f.fixed


def test_eligible_item_on_visa_is_marked_override():
    s = new_session()
    _, s = payment_agent.recommend(s, ADVIL())
    _, s = go("add_to_cart", s, card="visa")
    assert s["cart"][0]["assigned_card_id"] == "card_visa_1" and s["cart"][0]["user_overrode_card"] is True


def test_spoken_price_resolves_unpriced_scan():
    s = new_session()
    _, s = payment_agent.recommend(s, scan("Yoga Mat", None, "could_not_confirm"))
    f, s = go("give_price", s, price_dollars=45.0)
    assert "$45.00" in f.must_say and s["last_scan"]["product"]["price_source"] == "user_spoken"
    assert s["pending"]["scope"] == "choose_card"


def test_spoken_price_never_replaces_shelf_price():
    s = new_session()
    _, s = payment_agent.recommend(s, ADVIL())
    f, s = go("give_price", s, price_dollars=4.5)
    assert s["last_scan"]["product"]["amount_cents"] == 1299
    assert "$12.99" in f.must_say and "$4.50" not in f.template


def test_spoken_price_out_of_range_is_rejected():
    s = new_session()
    _, s = payment_agent.recommend(s, scan("Yoga Mat", None, "could_not_confirm"))
    f, s = go("give_price", s, price_dollars=1299.0)
    assert "doesn't look right" in f.template and s["last_scan"]["product"]["amount_cents"] is None


@pytest.mark.asyncio
async def test_product_hint_from_intent_is_used():
    _, scan = await product_agent.handle(product_hint="yoga mat")
    assert scan["product"]["name"] == "yoga mat"
