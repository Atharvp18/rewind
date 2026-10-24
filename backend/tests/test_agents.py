"""Agent handler tests. Pure functions, no network, no Agentverse.

Scans are constructed directly: the lookup/eligibility pipeline has its own
tests, and the demo rows live in the database once it is wired in.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from agents import payment_agent, product_agent
from agents.common import Incoming
from agents.intent import Entities, Intent
from tests.helpers import new_session
from uagents_core.contrib.protocols.chat import ChatMessage, TextContent


def incoming(text: str) -> Incoming:
    return Incoming(ChatMessage(timestamp=datetime.now(timezone.utc), msg_id=uuid4(),
                                content=[TextContent(type="text", text=text)]))


def scan(name: str, price_cents: int | None, label: str, medication: bool = False, basis: str = "upc_match") -> dict:
    return {
        "scan_id": str(uuid4()), "timestamp": "2026-10-24T00:00:00+00:00",
        "state": "resolved" if price_cents is not None else "partial",
        "product": {"product_key": f"n:{name}", "upc": None, "name": name, "brand": None, "size": None,
                    "category": "other", "is_medication": medication, "is_prescription_only": False,
                    "amount_cents": price_cents, "price_source": "shelf_tag" if price_cents else None,
                    "state": "resolved" if price_cents is not None else "partial", "warnings": []},
        "eligibility": {"label": label, "confidence": None, "basis": basis, "source": None,
                        "collected_at": None, "matched_name": None},
        "warnings": [],
    }


ADVIL = lambda: scan("Advil Ibuprofen 200mg", 1299, "eligible", medication=True)
BANDAGES = lambda: scan("Bandages", 549, "eligible")
KETTLE_CORN = lambda: scan("Kettle Corn", 499, "not_eligible", basis="irs_category_rule")
YOGA_MAT = lambda: scan("Yoga Mat", 2500, "could_not_confirm", basis="no_match")


def go(name: str, session: dict, **entities):
    return payment_agent.handle_intent(Intent(intent=name, entities=Entities(**entities)), session)


# --- product agent -----------------------------------------------------------

@pytest.mark.asyncio
async def test_unknown_product_by_name_could_not_confirm():
    facts, scan = await product_agent.handle(product_hint="yoga mat")
    assert scan["eligibility"]["label"] == "could_not_confirm"
    assert scan["state"] == "partial"
    assert "I could not confirm eligibility" in facts.must_say


@pytest.mark.asyncio
async def test_no_hint_no_image_gets_help():
    facts, scan = await product_agent.handle()
    assert scan is None and "shelf photo" in facts.template


def test_facts_carry_every_spoken_number():
    from models.schemas import EligibilityResult, ProductResolution
    p = ProductResolution(product_key="x", name="Advil Ibuprofen 200mg", brand="Advil", category="pain_relief",
                          is_medication=True, amount_cents=1299, state="resolved")
    e = EligibilityResult(label="eligible", basis="upc_match")
    f = product_agent.facts_for(p, e)
    assert {"$12.99", "HSA eligible", "Advil Ibuprofen 200mg"} <= set(f.must_say)


# --- payment agent: run 1 ----------------------------------------------------

def test_run_1_happy_path_ends_at_321_52():
    s = new_session()
    for item in (ADVIL(), BANDAGES(), KETTLE_CORN()):
        f, s = payment_agent.recommend(s, item)
        f, s = go("confirm", s)
        assert f.template.startswith("Added")

    f, s = go("checkout", s)
    assert "$18.48" in f.must_say and "HSA card" in f.must_say
    assert "$4.99" in f.must_say and "Visa credit" in f.must_say
    assert f.template.endswith("Ready to check out?")

    f, s = go("confirm", s)
    assert "simulated" in f.must_say and "$18.48" in f.must_say
    assert "$321.52" not in f.template and "$340" not in f.template
    assert s["cards"][0]["balance_cents"] == 32152  # math still exact, just never spoken
    assert s["cart"] == [] and f.alert is None


def test_kettle_corn_routes_to_visa_never_hsa():
    s = new_session()
    f, s = payment_agent.recommend(s, KETTLE_CORN())
    assert "Not HSA eligible" in f.must_say and "Visa credit" in f.must_say
    f, s = go("confirm", s)
    assert s["cart"][0]["assigned_card_id"] == "card_visa_1"


# --- payment agent: run 2 (declined-card moment) ----------------------------

def test_run_2_reroutes_bandages_to_visa():
    s = new_session()
    s["cards"][0]["balance_cents"] = 1500
    for item in (ADVIL(), BANDAGES()):
        _, s = payment_agent.recommend(s, item)
        _, s = go("confirm", s)

    f, s = go("checkout", s)
    assert {"$18.48", "Advil Ibuprofen 200mg", "Bandages", "Visa credit"} <= set(f.must_say)
    assert "$15.00" not in f.template
    assert "keep the Advil Ibuprofen 200mg on your HSA card and move the Bandages to your Visa credit" in f.template

    f, s = go("confirm", s)
    by_card = {i["display_name"]: i["assigned_card_id"] for i in s["cart"]}
    assert by_card == {"Advil Ibuprofen 200mg": "card_hsa_1", "Bandages": "card_visa_1"}
    assert f.template.endswith("Ready to check out?")


def test_insufficient_balance_asks_before_moving_single_item():
    s = new_session()
    s["cards"][0]["balance_cents"] = 900            # $9.00: cannot cover $12.99, and is under the $10 alert line
    f, s = payment_agent.recommend(s, ADVIL())
    assert "$9.00" not in f.template and "another card" in f.must_say
    assert f.alert == "low_balance" and "running low" in f.template
    assert s["pending"]["scope"] == "choose_card"
    f, s = go("confirm", s)
    assert s["cart"][0]["assigned_card_id"] == "card_visa_1" and s["cart"][0]["user_overrode_card"] is True


# --- guardrails ----------------------------------------------------------------

def test_could_not_confirm_never_auto_routes():
    s = new_session()
    f, s = payment_agent.recommend(s, YOGA_MAT())
    assert "could not confirm eligibility" in f.must_say
    assert s["pending"]["scope"] == "choose_card"
    assert set(s["pending"]["card_options"]) == {"card_hsa_1", "card_visa_1"}


def test_scan_without_price_asks_for_it():
    s = new_session()
    f, s = payment_agent.recommend(s, scan("Yoga Mat", None, "could_not_confirm"))
    assert "closer to the price tag" in f.template and f.fixed and s["pending"] is None


def test_confirm_without_a_pending_question_is_not_acted_on():
    s = new_session()
    f, s = go("confirm", s)
    assert s["cart"] == [] and f is payment_agent.HELP


def test_clear_cart_requires_confirmation():
    s = new_session()
    _, s = payment_agent.recommend(s, ADVIL())
    _, s = go("confirm", s)
    f, s = go("clear_cart", s)
    assert s["cart"] and s["pending"]["scope"] == "confirm_clear"
    f, s = go("deny", s)
    assert s["cart"]
    _, s = go("clear_cart", s)
    _, s = go("confirm", s)
    assert s["cart"] == []


def test_balance_is_never_spoken_anywhere():
    """Walk both demo runs and every query; no reply may contain a card balance figure."""
    import re
    def balances(s):
        return {f"${c['balance_cents'] / 100:,.2f}" for c in s["cards"]}
    replies = []
    for start in (34000, 1500, 1000):
        s = new_session()
        s["cards"][0]["balance_cents"] = start
        forbidden = balances(s)
        for item in (ADVIL(), BANDAGES(), KETTLE_CORN(), YOGA_MAT()):
            f, s = payment_agent.recommend(s, item); replies.append((f, forbidden | balances(s)))
            f, s = go("add_to_cart", s, card="visa" if item["eligibility"]["label"] != "eligible" else None)
            replies.append((f, forbidden | balances(s)))
        for intent in ("balance_query", "cart_query", "checkout", "confirm", "checkout", "confirm"):
            f, s = go(intent, s); replies.append((f, forbidden | balances(s)))
    assert len(replies) > 30
    for f, forbidden in replies:
        spoken = set(re.findall(r"\$[\d,]+\.\d{2}", f.template))
        assert not (spoken & forbidden), f"balance spoken: {f.template}"
        assert "balance is" not in f.template, f.template


def test_balance_query_is_refused_for_privacy():
    f, _ = go("balance_query", new_session())
    assert f is payment_agent.BALANCE_PRIVATE and f.fixed and "$" not in f.template


def test_low_balance_after_checkout_beeps_and_warns():
    s = new_session()
    s["cards"][0]["balance_cents"] = 2000          # $20.00 - $12.99 leaves $7.01: under the $10 alert line
    _, s = payment_agent.recommend(s, ADVIL())
    _, s = go("confirm", s)
    _, s = go("checkout", s)
    f, s = go("confirm", s)
    assert f.alert == "low_balance"
    assert "HSA card is running low. You might want to add funds." in f.template
    assert "$7.01" not in f.template                # the balance itself is never spoken


def test_handler_does_not_mutate_input_session():
    s = new_session()
    go("remove_last", s)
    _, out = go("balance_query", s)
    assert out is not s and out == s


def testgreeting_is_full_once_then_short():
    from agents.orchestrator_agent import WELCOME, WELCOME_BACK, greeting
    s = new_session()
    assert greeting(s) is WELCOME and "shopping helper" in WELCOME.template
    assert greeting(s) is WELCOME_BACK and WELCOME_BACK.template == "How may I help you today?"


def test_orchestratornudge_wording():
    from agents.orchestrator_agent import nudge
    s = new_session()
    assert nudge(s) is None
    s["pending"] = {"scope": "confirm_checkout"}
    assert "check out" in nudge(s).must_say
    s["pending"] = {"scope": "confirm_add", "card_id": "card_hsa_1"}
    s["last_scan"] = {"product": {"name": "Advil", "amount_cents": 1299}}
    f = nudge(s)
    assert f.template == "You were looking at Advil, $12.99. Would you like to add it?"
    assert {"Advil", "$12.99"} <= set(f.must_say)


def test_hello_mid_conversation_gets_short_greeting_with_name():
    from agents.orchestrator_agent import greeting
    s = {"greeted": False, "last_reply": "I read Omeprazole, 20mg. Is that right?"}
    assert greeting(s, "Alex").template == "Hi Alex, how may I help you today?"


def test_no_price_ask_is_spoken_word_for_word():
    from agents import product_agent
    from models.schemas import EligibilityResult, ProductResolution
    p = ProductResolution(product_key="k", name="kleenex tissues", category="other", state="partial")
    e = EligibilityResult(label="could_not_confirm", basis="no_match")
    assert product_agent.facts_for(p, e).fixed is True


def test_side_question_is_answered_then_card_question_comes_back():
    from agents.intent import Intent
    s = new_session()
    s["insurance"] = None
    s["last_scan"] = {"scan_id": "x", "state": "resolved",
                      "product": {"product_key": "k", "name": "Advil", "amount_cents": 1299},
                      "eligibility": {"label": "could_not_confirm"}}
    s["pending"] = {"scope": "choose_card", "card_options": ["card_hsa_1", "card_visa_1"], "overrode": True}
    f, s2 = payment_agent.handle_intent(Intent(intent="insurance_question"), s)
    assert "Which card" not in f.template.split(".")[0]      # the question is answered first
    assert "You were looking at Advil" in f.template          # then the open question returns
    assert s2["pending"]["scope"] == "choose_card"


def test_naming_a_card_answers_an_okay_question():
    from agents.intent import Entities, Intent
    s = new_session()
    _, s = payment_agent.recommend(s, scan("Kleenex Facial Tissues", 349, "not_eligible"))
    assert s["pending"]["scope"] == "confirm_add"
    f, s = payment_agent.handle_intent(Intent(intent="choose_card", entities=Entities(card="visa")), s)
    assert s["cart"][0]["assigned_card_id"] == "card_visa_1" and "Added" in f.template


def test_reminder_fires_shortly_after_silence_but_never_for_a_user_who_left():
    from agents.orchestrator_agent import due_for_nudge
    s = {"pending": {"scope": "confirm_add"}, "last_activity": 1000.0}
    assert not due_for_nudge(s, 1005.0)            # still within 10 s
    assert due_for_nudge(s, 1015.0)                # 15 s of silence: remind
    assert not due_for_nudge(s, 1000.0 + 3 * 3600)  # idle for hours (e.g. after a restart): the user has left
    assert not due_for_nudge({**s, "nudges": 1}, 1015.0)   # only once
    assert not due_for_nudge({"last_activity": 1000.0}, 1015.0)  # nothing pending
