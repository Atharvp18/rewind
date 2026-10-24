"""Agent handler tests. Pure functions, no network, no Agentverse."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from agents import payment_agent, product_agent
from agents.common import Incoming
from agents.session import new_session
from uagents_core.contrib.protocols.chat import ChatMessage, TextContent
from datetime import datetime, timezone
from uuid import uuid4


def incoming(text: str) -> Incoming:
    return Incoming(ChatMessage(timestamp=datetime.now(timezone.utc), msg_id=uuid4(),
                                content=[TextContent(type="text", text=text)]))


async def scan_for(text: str) -> dict:
    _, meta = await product_agent.handle(incoming(text))
    return meta["scan"]


# --- product agent -----------------------------------------------------------

@pytest.mark.asyncio
async def test_advil_is_eligible_by_upc_match():
    text, meta = await product_agent.handle(incoming("Is Advil HSA eligible?"))
    scan = meta["scan"]
    assert scan["eligibility"]["label"] == "eligible"
    assert scan["eligibility"]["basis"] == "upc_match"
    assert scan["product"]["amount_cents"] == 1299
    assert "HSA eligible." in text and "confidence" not in text  # medication: no confidence phrase


@pytest.mark.asyncio
async def test_kettle_corn_is_never_eligible():
    scan = await scan_for("is kettle corn fsa eligible")
    assert scan["eligibility"]["label"] == "not_eligible"


@pytest.mark.asyncio
async def test_unknown_item_could_not_confirm():
    text, meta = await product_agent.handle(incoming("is a yoga mat hsa eligible"))
    assert meta["scan"]["eligibility"]["label"] == "could_not_confirm"
    assert "could not confirm eligibility" in text


@pytest.mark.asyncio
async def test_non_product_text_gets_help():
    text, meta = await product_agent.handle(incoming("tell me a joke"))
    assert meta is None
    assert "Rewind Product Agent" in text


# --- payment agent: run 1 ----------------------------------------------------

@pytest.mark.asyncio
async def test_run_1_happy_path_ends_at_321_52():
    session = new_session()
    for item in ("advil", "bandages", "kettle corn"):
        text, session = payment_agent.recommend(session, await scan_for(item))
        text, session = payment_agent.handle("yes", session)
        assert text.startswith("Added")

    text, session = payment_agent.handle("checkout", session)
    assert "2 items totaling $18.48 on your HSA card" in text
    assert "1 item totaling $4.99 on your Visa credit" in text
    assert text.endswith("Ready to check out?")

    text, session = payment_agent.handle("yes", session)
    assert "$321.52" in text
    assert session["cart"] == []


@pytest.mark.asyncio
async def test_kettle_corn_routes_to_visa_never_hsa():
    session = new_session()
    text, session = payment_agent.recommend(session, await scan_for("kettle corn"))
    assert "Not HSA eligible" in text and "Visa credit" in text
    text, session = payment_agent.handle("ok", session)
    assert session["cart"][0]["card_id"] == "card_visa_1"


# --- payment agent: run 2 (declined-card moment) ----------------------------

@pytest.mark.asyncio
async def test_run_2_reroutes_bandages_to_visa():
    session = new_session()
    session["cards"][0]["balance_cents"] = 1500
    for item in ("advil", "bandages"):
        _, session = payment_agent.recommend(session, await scan_for(item))
        _, session = payment_agent.handle("yes", session)

    text, session = payment_agent.handle("checkout", session)
    assert "only $15.00, which doesn't cover $18.48" in text
    assert "keep the Advil Ibuprofen 200mg on your HSA card and move the Bandages to your Visa credit" in text

    text, session = payment_agent.handle("yes", session)
    by_card = {i["display_name"]: i["card_id"] for i in session["cart"]}
    assert by_card == {"Advil Ibuprofen 200mg": "card_hsa_1", "Bandages": "card_visa_1"}
    assert text.endswith("Ready to check out?")


@pytest.mark.asyncio
async def test_insufficient_balance_asks_before_moving_single_item():
    session = new_session()
    session["cards"][0]["balance_cents"] = 1000
    text, session = payment_agent.recommend(session, await scan_for("advil"))
    assert "only $10.00" in text and session["pending"]["scope"] == "choose_card"
    text, session = payment_agent.handle("yes", session)
    assert session["cart"][0]["card_id"] == "card_visa_1"
    assert session["cart"][0]["user_overrode_card"] is True


# --- guardrails ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_could_not_confirm_never_auto_routes():
    session = new_session()
    scan = await scan_for("is a yoga mat hsa eligible")
    scan["product"]["amount_cents"] = 2500
    text, session = payment_agent.recommend(session, scan)
    assert "could not confirm eligibility" in text
    assert session["pending"]["scope"] == "choose_card"
    assert set(session["pending"]["card_options"]) == {"card_hsa_1", "card_visa_1"}


def test_yes_without_a_pending_question_is_not_acted_on():
    session = new_session()
    text, session = payment_agent.handle("yes", session)
    assert session["cart"] == [] and "Rewind Payment Agent" in text


def test_clear_cart_requires_confirmation():
    session = new_session()
    session["cart"].append({"id": "x", "scan_id": "s", "display_name": "Advil", "amount_cents": 1299,
                            "card_id": "card_hsa_1", "eligibility_label": "eligible", "user_overrode_card": False})
    text, session = payment_agent.handle("clear cart", session)
    assert session["cart"] and session["pending"]["scope"] == "confirm_clear"
    text, session = payment_agent.handle("no", session)
    assert session["cart"]
    _, session = payment_agent.handle("clear cart", session)
    _, session = payment_agent.handle("yes", session)
    assert session["cart"] == []


@pytest.mark.asyncio
async def test_scan_without_price_asks_for_it():
    session = new_session()
    text, session = payment_agent.recommend(session, await scan_for("is a yoga mat hsa eligible"))
    assert "could not read a price" in text and session["pending"] is None


def test_handler_does_not_mutate_input_session():
    session = new_session()
    payment_agent.handle("remove last item", session)
    _, out = payment_agent.handle("balance", session)
    assert out is not session and out == session


def test_orchestrator_classifier():
    from agents.orchestrator_agent import classify
    s = new_session()
    assert classify(incoming("is advil hsa eligible"), s) == "product"
    assert classify(incoming("what's in my cart"), s) == "payment"
    assert classify(incoming("reset demo run 2"), s) == "reset"
    assert classify(incoming("hello"), s) == "general"
    s["pending"] = {"scope": "confirm_add"}
    assert classify(incoming("yes"), s) == "payment"
