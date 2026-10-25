"""Insurance rules for counter prescriptions. No network."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from agents import insurance, payment_agent, product_agent
from agents.session import INSURERS, plan_profile
from tests.helpers import new_session
from tests.test_agents import go, scan
from vision.card_reader import CardExtract, PrintedCopay, scrub


def rx(name="Omeprazole", size="20mg"):
    s = scan(name, None, "could_not_confirm", medication=True)
    s["product"]["is_prescription_only"] = True
    s["product"]["size"] = size
    return s


def start(session, item=None):
    return payment_agent.recommend(session, item or rx())


def with_plan(plan_id):
    s = new_session()
    s["insurance"] = plan_profile(plan_id, source="spoken")
    return s


# --- shelf items never involve insurance -------------------------------------

def test_shelf_item_never_mentions_insurance():
    s = with_plan("uhc_student")
    f, s = payment_agent.recommend(s, scan("Tylenol Extra Strength", 999, "eligible", medication=True))
    assert "insurance" not in f.template.lower() and "plan" not in f.template.lower()
    assert "HSA eligible" in f.must_say


def test_otc_box_of_prescription_drug_mentions_counter_version():
    f, _ = payment_agent.recommend(new_session(), scan("Omeprazole 20mg OTC", 1499, "eligible", medication=True))
    assert "pharmacy counter version may cost less" in f.template


# --- read-back comes first ------------------------------------------------------

def test_prescription_is_read_back_before_anything():
    f, s = start(with_plan("uhc_student"))
    assert f.template == "I read Omeprazole, 20mg. Is that right?"
    assert s["pending"]["scope"] == "confirm_rx" and s["cart"] == []


def test_wrong_read_back_forgets_drug():
    _, s = start(with_plan("uhc_student"))
    f, s = go("deny", s)
    assert "pharmacist" in f.must_say and s["last_scan"] is None


def test_missing_strength_asks_and_forgets():
    f, s = start(new_session(), rx(size=None))
    assert "couldn't read the strength" in f.template and s["last_scan"] is None


# --- plan rules -------------------------------------------------------------------

def test_no_plan_asks_then_unknown_sends_to_pharmacist():
    _, s = start(new_session())
    f, s = go("confirm", s)
    assert s["pending"]["scope"] == "ask_plan"
    f, s = go("choose_plan", s, plan="unknown")
    assert "pharmacist will tell you your share" in f.template and "HSA card" in f.template
    assert s["cart"] == [] and s["last_scan"] is None


def test_copay_plan_gives_labelled_estimate_and_soft_hsa():
    _, s = start(with_plan("uhc_student"))
    f, s = go("confirm", s)
    assert {"$15.00", "estimate", insurance.PHARMACIST, insurance.COPAY_HSA, "HSA card"} <= set(f.must_say)
    assert "after any deductible" in f.template
    assert s["pending"]["suggested"] == "card_hsa_1"
    f, s = go("confirm", s)
    item = s["cart"][0]
    assert item["assigned_card_id"] == "card_hsa_1" and item["amount_cents"] == 1500
    assert item["amount_basis"] == "remaining_after_copay"


def test_plan_named_mid_flow_continues_to_estimate():
    _, s = start(new_session())
    _, s = go("confirm", s)
    f, s = go("choose_plan", s, plan="sunrise_ppo")
    assert "$10.00" in f.must_say and "after any deductible" not in f.template


def test_copay_can_go_on_visa_instead():
    _, s = start(with_plan("uhc_student"))
    _, s = go("confirm", s)
    _, s = go("choose_card", s, card="visa")
    assert s["cart"][0]["assigned_card_id"] == "card_visa_1"


@pytest.mark.parametrize("plan_id,phrase", [
    ("basic_medical", "may not include prescription coverage"),
    ("harbor_choice", "pays a percentage"),
    ("evergreen_hsa", "until your deductible is met"),
])
def test_plans_that_allow_no_estimate(plan_id, phrase):
    _, s = start(with_plan(plan_id))
    f, s = go("confirm", s)
    assert phrase in f.template and "$" not in f.template
    assert s["cart"] == [] and s["last_scan"] is None


def test_prior_auth_drug_gives_no_estimate():
    _, s = start(with_plan("uhc_student"), rx("Semaglutide", "0.5mg"))
    f, s = go("confirm", s)
    assert "approval from your plan" in f.template and s["cart"] == []


def test_zero_copay_adds_nothing():
    _, s = start(with_plan("uhc_student"), rx("Lisinopril", "10mg"))
    f, s = go("confirm", s)
    assert "no copay" in f.template and s["cart"] == []


def test_drug_not_on_formulary():
    _, s = start(with_plan("uhc_student"), rx("Amoxicillin", "500mg"))
    f, s = go("confirm", s)
    assert "drug list" in f.template and s["cart"] == []


def test_strength_must_match_exactly():
    _, s = start(with_plan("uhc_student"), rx("Omeprazole", "40mg"))
    f, s = go("confirm", s)
    assert "drug list" in f.template and "$" not in f.template


def test_hsa_too_low_for_copay_offers_the_visa_quietly():
    s = with_plan("uhc_student")
    s["cards"][0]["balance_cents"] = 900            # $9.00: cannot cover the $15.00 copay
    _, s = start(s)
    f, s = go("confirm", s)
    assert s["pending"]["suggested"] == "card_visa_1"
    assert f.alert is None and "$9.00" not in f.template and "can't cover" not in f.template


# --- privacy -----------------------------------------------------------------------

def test_drug_name_is_not_kept_after_the_answer():
    _, s = start(with_plan("uhc_student"))
    _, s = go("confirm", s)
    _, s = go("confirm", s)
    blob = str(s).lower()
    assert "omeprazole" not in blob and "20mg" not in blob
    assert s["cart"][0]["display_name"] == "your prescription"


def test_card_scrub_drops_id_shaped_values():
    card = scrub(CardExtract(first_name="Alex", last_name="Rivera 987654321", insurer="UnitedHealthcare",
                             has_rx_section=True, rx_manager="OptumRx",
                             printed_rx_copays=[PrintedCopay(label="Group 0705214", amount_dollars=10)]))
    assert card.first_name == "Alex" and card.last_name is None and card.printed_rx_copays == []


def test_card_schema_has_no_identifier_fields():
    fields = set(CardExtract.model_fields)
    for banned in ("member_id", "group", "group_number", "rx_bin", "rx_pcn", "date_of_birth", "dob"):
        assert banned not in fields


def test_uhc_card_maps_to_modeled_plan_without_personal_data():
    card = CardExtract(first_name="Alex", last_name="Rivera", insurer="UnitedHealthcare",
                       plan_name="Student Resources", has_rx_section=True, rx_manager="OptumRx")
    profile = insurance.card_to_profile(card)
    assert profile["plan_id"] == "uhc_student" and profile["rx_manager"] == "OptumRx"
    assert "alex" not in str(profile).lower() and "rivera" not in str(profile).lower()


def test_unknown_insurer_card_with_rx_gives_no_estimate():
    card = CardExtract(insurer="Acme Health", has_rx_section=True, rx_manager="Acme Rx")
    s = new_session()
    s["insurance"] = insurance.card_to_profile(card)
    _, s = start(s)
    f, s = go("confirm", s)
    assert "covers prescriptions through Acme Rx" in f.template and "$" not in f.template


@pytest.mark.asyncio
async def test_product_agent_reads_card(monkeypatch):
    monkeypatch.setenv("REWIND_STUB_IMAGE", "card")

    async def fake_download(url):
        return b"jpeg"
    monkeypatch.setattr(product_agent, "download_image", fake_download)
    facts, scan_, profile, name = await product_agent.handle_full(image_url="http://x/card.jpg")
    assert scan_ is None and profile["plan_id"] == "uhc_student"
    assert name == "Alex Rivera" and "Alex" in facts.must_say
    assert "OptumRx" in facts.template


@pytest.mark.asyncio
async def test_product_agent_reads_pharmacy_label(monkeypatch):
    monkeypatch.setenv("REWIND_STUB_IMAGE", "rx_label")

    async def fake_download(url):
        return b"jpeg"
    monkeypatch.setattr(product_agent, "download_image", fake_download)
    _, scan_, profile, _ = await product_agent.handle_full(image_url="http://x/bottle.jpg")
    assert profile is None and scan_["product"]["is_prescription_only"] is True
    assert scan_["product"]["size"] == "20mg"


@pytest.mark.asyncio
async def test_spoken_prescription_parses_strength():
    _, scan_, _, _ = await product_agent.handle_full(product_hint="omeprazole 20mg", is_prescription=True)
    p = scan_["product"]
    assert p["name"] == "omeprazole" and p["size"] == "20mg" and p["is_prescription_only"] is True


def test_five_plans_exist():
    assert len(INSURERS) == 5
