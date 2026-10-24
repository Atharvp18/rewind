"""Tests for speech/compose.py: the §4.4 must-contain facts, no balances spoken, wording per reason."""
import re

import pytest

from data.seed import cards_for_run
from models.schemas import EligibilityResult, ProductResolution
from payments.routing import plan_checkout, route_item
from speech import compose
from speech.sentences import split_sentences


def product(name="Advil Ibuprofen 200mg", cents=1299, medication=True):
    return ProductResolution(product_key=f"n:{name}", name=name, category="other", is_medication=medication,
                             amount_cents=cents, state="resolved" if cents is not None else "partial")


def elig(label="eligible", basis="upc_match", confidence=None):
    return EligibilityResult(label=label, basis=basis, confidence=confidence)


def say(prod, e, run=1, cards=None, **kw):
    cards = cards_for_run(run) if cards is None else cards
    rec = route_item(e.label, prod.amount_cents, "shelf_price", cards) if prod.amount_cents else None
    return compose.compose_speech(prod, e, rec, cards, **kw), rec


def cart(*rows):
    return [{"id": f"i{n}", "display_name": name, "amount_cents": cents, "assigned_card_id": card,
             "eligibility_label": label} for n, (name, cents, card, label) in enumerate(rows)]


# --- money ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("cents,text", [(0, "$0.00"), (5, "$0.05"), (1299, "$12.99"), (100000, "$1,000.00")])
def test_money(cents, text):
    assert compose.money(cents) == text


@pytest.mark.parametrize("bad", [12.99, True, "1299", None])
def test_money_rejects_non_integer_cents(bad):
    with pytest.raises(ValueError):
        compose.money(bad)


# --- scan: demo steps ------------------------------------------------------------------------------

def test_medication_with_exact_match_has_no_confidence_phrase_and_goes_to_the_default_fsa():
    voice, _ = say(product(), elig())
    assert voice.text.startswith("Advil Ibuprofen 200mg, $12.99. HSA eligible. ")
    assert "confidence" not in voice.text and "your FSA card" in voice.text
    assert voice.response_scope == "confirm_add" and voice.expects_response and voice.priority == "normal"


def test_with_an_hsa_default_the_card_is_spoken_as_the_hsa():
    cards = [c for c in cards_for_run(1) if c["id"] != "card_fsa_1"]
    cards[0]["is_default"] = True
    voice, _ = say(product(), elig(), cards=cards)
    assert "your HSA card" in voice.text


def test_not_eligible_goes_to_the_visa_and_says_so():
    voice, _ = say(product("Kettle Corn", 499, medication=False), elig("not_eligible", "irs_category_rule"))
    assert "Not HSA eligible" in voice.text and "your Visa credit" in voice.text and "$4.99" in voice.text


def test_could_not_confirm_asks_which_card_and_never_picks_one():
    voice, rec = say(product("Yoga Mat", 2500, medication=False), elig("could_not_confirm", "no_match"))
    assert "I could not confirm eligibility" in voice.text and "Which card" in voice.text
    assert voice.response_scope == "choose_card" and rec.decision == "ask_user"


def test_run_2_says_another_card_without_any_amount_of_the_balance():
    voice, _ = say(product(cents=1600), elig(), run=2)
    assert "$15.00" not in voice.text
    assert "can't cover" in voice.text and "Visa credit" in voice.text
    assert "running low. You might want to add funds." in voice.text
    assert voice.priority == "alert" and voice.response_scope == "choose_card"


def test_no_price_asks_for_the_price_tag():
    voice, rec = say(product("Kleenex", None, medication=False), elig("could_not_confirm", "no_match"))
    assert rec is None and "closer to the price tag" in voice.text
    assert voice.response_scope == "none" and not voice.expects_response and voice.prompt_id is None


def test_the_prompt_id_is_only_attached_to_a_question():
    voice, _ = say(product(), elig(), prompt_id="p1")
    assert voice.prompt_id == "p1"
    voice, _ = say(product(), elig(), prompt_id="p1", cards=[])
    assert voice.response_scope == "none" and voice.prompt_id is None


# --- confidence wording table ----------------------------------------------------------------------

@pytest.mark.parametrize("medication,basis,score,phrase", [
    (True, "upc_match", None, ""),
    (False, "upc_match", None, "high confidence"),
    (False, "irs_category_rule", None, "high confidence"),
    (False, "semantic_match", 0.95, "high confidence"),
    (False, "semantic_match", compose.HIGH_CONFIDENCE, "high confidence"),
    (False, "semantic_match", 0.6, "moderate confidence"),
    (True, "semantic_match", 0.6, "moderate confidence"),
])
def test_confidence_matrix(medication, basis, score, phrase):
    line = compose.eligibility_line(product(medication=medication), elig("eligible", basis, score))
    assert line == (f"HSA eligible, {phrase}." if phrase else "HSA eligible.")


def test_could_not_confirm_has_no_confidence_phrase():
    assert compose.eligibility_line(product(), elig("could_not_confirm", "no_match")) == "I could not confirm eligibility."


# --- every routing reason has wording ---------------------------------------------------------------

def reason_cases():
    both = cards_for_run(1)
    hsa_only = [dict(c, is_default=False) for c in both if c["type"] != "general"]
    visa = [c for c in both if c["type"] == "general"]
    frozen = [dict(c, status="frozen") for c in both]
    no_health = visa
    return {
        "eligible_sufficient_balance": ("eligible", 1299, "shelf_price", both),
        "eligible_insufficient_balance": ("eligible", 1600, "shelf_price", cards_for_run(2)),
        "not_eligible": ("not_eligible", 499, "shelf_price", both),
        "eligibility_unconfirmed": ("could_not_confirm", 499, "shelf_price", both),
        "copay_unconfirmed": ("eligible", 500, "remaining_after_copay", both),
        "zero_copay_nothing_due": ("eligible", 0, "remaining_after_copay", both),
        "no_health_card_linked": ("eligible", 499, "shelf_price", no_health),
        "no_card_linked": ("eligible", 499, "shelf_price", frozen),
        "no_card_covers": ("eligible", 499_999_99, "shelf_price", cards_for_run(2)),
    }


@pytest.mark.parametrize("reason", list(reason_cases()))
def test_every_reason_code_produces_speech(reason):
    label, cents, basis, cards = reason_cases()[reason]
    rec = route_item(label, cents, basis, cards)
    assert rec.reason_code == reason
    voice = compose.compose_speech(product(cents=cents or 1), elig(label, "upc_match"), rec, cards)
    assert voice.text.strip() and voice.sentences == split_sentences(voice.text)
    assert voice.expects_response == (voice.response_scope != "none")


def test_no_card_covers_says_use_another_card():
    label, cents, basis, cards = reason_cases()["no_card_covers"]
    rec = route_item(label, cents, basis, cards)
    voice = compose.compose_speech(product(cents=cents), elig(), rec, cards)
    assert "Please use another card for this item." in voice.text and voice.response_scope == "none"


# --- no balance is ever spoken ----------------------------------------------------------------------

def test_no_balance_figure_is_spoken_in_any_scan_reply():
    leaks = []
    for run in (1, 2):
        cards = cards_for_run(run)
        balances = {compose.money(c["balance_cents"]) for c in cards}
        for label, basis in (("eligible", "upc_match"), ("not_eligible", "irs_category_rule"),
                             ("could_not_confirm", "no_match")):
            for cents in (499, 549, 1299, 2500, 100_000, 600_000):
                if compose.money(cents) in balances:
                    continue                    # the price itself may equal a balance; that is not a leak
                rec = route_item(label, cents, "shelf_price", cards)
                text = compose.compose_speech(product(cents=cents), elig(label, basis), rec, cards).text
                leaks += [(run, label, cents, b) for b in balances if b in text]
    assert leaks == []


# --- cart and checkout -------------------------------------------------------------------------------

def test_cart_contents_gives_the_total_before_tax():
    items = cart(("Advil Ibuprofen 200mg", 1299, "card_fsa_1", "eligible"), ("Bandages", 549, "card_fsa_1", "eligible"))
    text = compose.cart_contents(items).text
    assert "2 items" in text and "$18.48 before tax" in text and "Bandages, $5.49." in text
    grouped = compose.cart_contents(items, cards_for_run(1)).text
    assert "On your FSA card: Advil Ibuprofen 200mg, $12.99. Bandages, $5.49." in grouped
    assert compose.cart_contents([]).text == "Your cart is empty."
    assert "1 item," in compose.cart_contents(items[:1]).text


def test_run_1_checkout_preview_and_result():
    cards = cards_for_run(1)
    items = cart(("Advil Ibuprofen 200mg", 1299, "card_fsa_1", "eligible"), ("Bandages", 549, "card_fsa_1", "eligible"),
                 ("Kettle Corn", 499, "card_visa_1", "not_eligible"))
    plan = plan_checkout(items, cards)
    preview = compose.checkout_preview(plan, cards, items, prompt_id="p")
    assert "$23.47 before tax" in preview.text and "$18.48 on your FSA card" in preview.text
    assert "$4.99 on your Visa credit" in preview.text and preview.text.endswith("Ready to check out?")
    assert preview.response_scope == "confirm_checkout" and preview.prompt_id == "p"

    done = compose.checkout_result(plan.groups, cards)
    assert "simulated" in done.text and "$18.48 on your FSA card" in done.text and done.priority == "normal"
    assert "$321.52" not in done.text and "$340" not in done.text


def test_run_2_checkout_preview_offers_to_move_the_bandages():
    cards = [dict(c, balance_cents=500) if c["id"] == "card_hsa_1" else c for c in cards_for_run(2)]   # HSA too low: Visa
    items = cart(("Advil Ibuprofen 200mg", 1299, "card_fsa_1", "eligible"), ("Bandages", 549, "card_fsa_1", "eligible"))
    preview = compose.checkout_preview(plan_checkout(items, cards), cards, items, prompt_id="p")
    assert ("keep the Advil Ibuprofen 200mg on your FSA card and move the Bandages to your Visa credit"
            in preview.text)
    assert "$15.00" not in preview.text and preview.text.endswith("Is that okay?")
    assert preview.response_scope == "confirm_checkout" and preview.prompt_id == "p"


def test_an_uncoverable_item_is_not_offered_a_move():
    cards = [dict(c, balance_cents=100) for c in cards_for_run(1)]
    items = cart(("Advil Ibuprofen 200mg", 1299, "card_fsa_1", "eligible"))
    preview = compose.checkout_preview(plan_checkout(items, cards), cards, items, prompt_id="p")
    assert "Please use another card for this item." in preview.text
    assert preview.response_scope == "none" and preview.prompt_id is None


def test_checkout_result_adds_the_low_balance_alert():
    cards = cards_for_run(1)
    items = cart(("Advil Ibuprofen 200mg", 1299, "card_fsa_1", "eligible"))
    done = compose.checkout_result(plan_checkout(items, cards).groups, cards, ["card_fsa_1"])
    assert done.priority == "alert"
    assert done.text.endswith("Your FSA card is running low. You might want to add funds.")


def test_standalone_replies():
    cards = cards_for_run(1)
    assert compose.low_balance_alert("card_hsa_1", cards).text == (
        "Your HSA card is running low. You might want to add funds.")
    assert compose.low_balance_alert("card_hsa_1", cards).priority == "alert"
    assert compose.item_added("Bandages", "card_visa_1", cards).text == "Added Bandages to your Visa credit."
    assert compose.item_removed("Bandages").text == "Removed Bandages."
    assert compose.item_removed(None).text == "Your cart is already empty."
    assert compose.confirm_clear().response_scope == "confirm_clear_cart"
    refusal = compose.balance_refusal().text
    assert "$" not in refusal and "balance" in refusal


def test_sentences_always_match_the_splitter_and_carry_no_dollar_fragments():
    cards = cards_for_run(1)
    voice, _ = say(product(), elig())
    assert voice.sentences == split_sentences(voice.text)
    assert all(re.search(r"[.!?]$", s) for s in voice.sentences)
    assert compose._request("x").request_id != compose._request("x").request_id


def test_run_2_preview_falls_through_to_the_visa_when_both_health_cards_are_short():
    cards = cards_for_run(2)                                   # FSA $15.00, HSA $5.00
    items = cart(("Advil Ibuprofen 200mg", 1299, "card_fsa_1", "eligible"), ("Bandages", 549, "card_fsa_1", "eligible"))
    preview = compose.checkout_preview(plan_checkout(items, cards), cards, items, prompt_id="p")
    assert "keep the Advil Ibuprofen 200mg on your FSA card and move the Bandages to your Visa credit" in preview.text
