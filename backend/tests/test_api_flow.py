"""The cart, scan, command, checkout and reset endpoints, end to end over HTTP.

The database is tests/fakes/fake_db.py and vision is replaced with fixed extracts, so nothing
touches the network. Demo numbers: HSA/FSA $340.00 or $15.00, Advil $12.99, bandages $5.49,
kettle corn $4.99.
"""
import pytest
from fastapi.testclient import TestClient

from api import memory, scan as scan_api
from data import db, seed
from main import create_app
from models.schemas import VisionExtract
from tests.fakes.fake_db import FakeDB

FSA, HSA, VISA = "card_fsa_1", "card_hsa_1", "card_visa_1"


@pytest.fixture
def fake(monkeypatch):
    memory.forget()
    return FakeDB(1).install(monkeypatch)


@pytest.fixture
def client(fake, monkeypatch):
    c = TestClient(create_app(), raise_server_exceptions=False)
    c.mp = monkeypatch
    return c


def scan(client, name="Advil Ibuprofen 200mg", cents=1299, upc=None, medication=True,
         category="pain_relief", **form):
    extract = VisionExtract(name=name, upc=upc, shelf_price_cents=cents, is_medication=medication,
                            category=category)
    client.mp.setattr(scan_api, "extract_product", lambda img: extract)
    r = client.post("/v1/scan", files={"image": ("f.jpg", b"jpeg", "image/jpeg")}, data=form)
    assert r.status_code == 200, r.text
    return r.json()


def add(client, s, card_id=None):
    return client.post("/v1/cart/items", json={"scan_id": s["scan"]["scan_id"], "card_id": card_id,
                                                 "prompt_id": s["voice"]["prompt_id"]})


def advil(client):
    return scan(client)


def bandages(client):
    return scan(client, "Bandages", 549, None, False, "first_aid")


def kettle(client):
    return scan(client, "Kettle Corn", 499, None, False, "grocery")


def fill_run1(client):
    for item in (advil, bandages, kettle):
        assert add(client, item(client)).status_code == 200


def say(client, transcript, prompt_id=None, **extra):
    return client.post("/v1/command", json={"transcript": transcript, "prompt_id": prompt_id, **extra})


# --- /v1/scan -------------------------------------------------------------------------------------

def test_scan_advil_routes_to_the_default_fsa_and_asks(client, fake):
    body = scan(client)
    assert body["scan"]["state"] == "resolved" and body["scan"]["eligibility"]["label"] == "eligible"
    rec = body["recommendation"]
    assert (rec["decision"], rec["card_id"], rec["reason_code"]) == ("route_to_hsa", FSA, "eligible_sufficient_balance")
    voice = body["voice"]
    assert "Advil" in voice["text"] and "$12.99" in voice["text"] and "HSA eligible" in voice["text"]
    assert "FSA card" in voice["text"] and voice["response_scope"] == "confirm_add" and voice["prompt_id"]
    assert fake.scans[body["scan"]["scan_id"]]["product_json"]["name"].startswith("Advil")


def test_scan_kettle_corn_goes_to_the_visa(client):
    body = kettle(client)
    assert body["recommendation"]["card_id"] == VISA and "Not HSA eligible" in body["voice"]["text"]


def test_a_scan_without_a_price_asks_for_it_and_opens_no_prompt(client, fake):
    body = scan(client, "Kleenex", None, upc=None, medication=False, category="other")
    assert body["scan"]["state"] == "partial" and body["recommendation"] is None
    assert "closer to the price tag" in body["voice"]["text"] and body["voice"]["prompt_id"] is None
    assert fake.prompts == {}


def test_hint_price_fills_a_missing_price(client):
    body = scan(client, "Kleenex", None, upc=None, medication=False, category="other", hint_price_cents="349")
    assert body["scan"]["product"]["amount_cents"] == 349 and "$3.49" in body["voice"]["text"]


@pytest.mark.parametrize("bad", ["0", "-5", "999999999999"])
def test_a_silly_hint_price_is_rejected(client, bad):
    client.mp.setattr(scan_api, "extract_product", lambda img: VisionExtract(name="x"))
    r = client.post("/v1/scan", files={"image": ("f.jpg", b"j", "image/jpeg")}, data={"hint_price_cents": bad})
    assert r.status_code == 422 and r.json()["error"]["code"] == "E_BAD_REQUEST"


def test_an_unidentifiable_product_is_unresolved(client):
    extract = VisionExtract()
    client.mp.setattr(scan_api, "extract_product", lambda img: extract)
    r = client.post("/v1/scan", files={"image": ("f.jpg", b"j", "image/jpeg")})
    body = r.json()
    assert body["scan"]["state"] == "unresolved" and body["recommendation"] is None
    assert "tell me what it is" in body["voice"]["text"] and body["voice"]["prompt_id"] is None


def test_an_empty_image_is_rejected(client):
    r = client.post("/v1/scan", files={"image": ("f.jpg", b"", "image/jpeg")})
    assert r.status_code == 422 and r.json()["error"]["code"] == "E_BAD_REQUEST"


def test_a_slow_scan_hits_the_budget(client):
    import time
    client.mp.setattr(scan_api, "SCAN_BUDGET_S", 0.05)
    client.mp.setattr(scan_api, "extract_product", lambda img: time.sleep(0.3))
    r = client.post("/v1/scan", files={"image": ("f.jpg", b"j", "image/jpeg")})
    assert r.status_code == 504 and r.json()["error"]["code"] == "E_UPSTREAM_TIMEOUT"


def test_a_product_not_in_our_data_is_treated_as_not_eligible_and_goes_to_the_visa(client):
    body = scan(client, "Yoga Mat", 2500, upc=None, medication=False, category="other")
    rec = body["recommendation"]
    assert body["scan"]["eligibility"]["label"] == "not_eligible"
    assert rec["decision"] == "route_to_general" and rec["card_id"] == VISA
    assert body["voice"]["priority"] == "alert" and "Visa" in body["voice"]["text"]
    assert "not eligible" in body["voice"]["text"]


# --- adding to the cart ------------------------------------------------------------------------------

def test_add_item_puts_it_in_the_cart_on_the_proposed_card(client):
    r = add(client, advil(client))
    assert r.status_code == 200
    cart = r.json()["cart"]
    assert cart["total_cents"] == 1299 and cart["groups"][0]["card_id"] == FSA
    assert r.json()["voice"]["text"] == "Added Advil Ibuprofen 200mg to your FSA card."
    assert client.get("/v1/cart").json() == cart


def test_a_prompt_cannot_be_used_twice(client):
    s = advil(client)
    assert add(client, s).status_code == 200
    again = add(client, s)
    assert again.status_code == 409 and again.json()["error"]["code"] == "E_PROMPT_EXPIRED"
    assert client.get("/v1/cart").json()["total_cents"] == 1299


def test_an_expired_prompt_is_rejected(client, fake):
    s = advil(client)
    fake.advance(16)
    r = add(client, s)
    assert r.status_code == 409 and r.json()["error"]["retryable"] is True
    assert client.get("/v1/cart").json()["groups"] == []


def test_a_prompt_for_another_scan_is_rejected(client):
    s, other = advil(client), bandages(client)
    r = client.post("/v1/cart/items", json={"scan_id": other["scan"]["scan_id"], "prompt_id": s["voice"]["prompt_id"]})
    assert r.status_code == 409 and client.get("/v1/cart").json()["groups"] == []


def test_an_add_prompt_cannot_authorize_a_checkout(client):
    s = advil(client)
    r = client.post("/v1/checkout/confirm", json={"idempotency_key": "k", "prompt_id": s["voice"]["prompt_id"]})
    assert r.status_code == 409
    assert add(client, s).status_code == 200            # the wrong-scope attempt did not use it up


def test_a_not_eligible_item_is_never_added_to_a_health_card(client):
    s = kettle(client)
    r = add(client, s, FSA)
    assert r.status_code == 422 and r.json()["error"]["code"] == "E_BAD_REQUEST"
    assert client.get("/v1/cart").json()["groups"] == []


def test_an_unlisted_item_cannot_go_on_a_health_card(client):
    s = scan(client, "Yoga Mat", 2500, upc=None, medication=False, category="other")
    assert add(client, s, FSA).status_code == 422
    s = scan(client, "Yoga Mat", 2500, upc=None, medication=False, category="other")
    r = add(client, s)
    assert r.status_code == 200 and r.json()["cart"]["groups"][0]["card_id"] == VISA


def test_a_scan_with_no_readable_price_uses_the_online_price_and_says_so(client, monkeypatch):
    import api.scan as scan_api
    monkeypatch.setattr(scan_api, "find_price_online", lambda product: 349)
    r = client.post("/v1/scan", files={"image": ("a.jpg", b"stub:tissues_far", "image/jpeg")})
    body = r.json()
    assert body["scan"]["product"]["price_source"] == "online" and body["scan"]["product"]["amount_cents"] == 349
    assert "online" not in body["voice"]["text"].lower()          # the simulation never mentions where a price came from
    assert body["recommendation"]["card_id"] == VISA


def test_a_prescription_scan_with_an_insurer_gets_the_pharmacist_tip(client, monkeypatch):
    monkeypatch.setenv("REWIND_STUB_IMAGE", "rx_label")
    import vision.claude_vision as cv
    monkeypatch.setattr(cv, "STUB_MODE", True)
    r = client.post("/v1/scan", files={"image": ("a.jpg", b"x", "image/jpeg")}, data={"insurer": "Aetna Choice"})
    voice = r.json()["voice"]
    done = say(client, "yes", voice["prompt_id"]).json()
    assert done["action"] == "strength_confirmed"
    assert "Your Aetna plan may cover part of this" in done["voice"]["text"]


def test_a_pinned_demo_item_always_gets_its_fixed_price(client, monkeypatch):
    import api.scan as scan_api

    async def listing(product):
        return {"eligible": True, "name": "Tylenol Extra Strength Caplets", "collected_at": None, "score": 0.9,
                "price_cents": 519, "pinned": True}
    monkeypatch.setattr(scan_api, "find_match", listing)
    r = client.post("/v1/scan", files={"image": ("a.jpg", b"stub:advil", "image/jpeg")})     # the tag reads $12.99
    product = r.json()["scan"]["product"]
    assert product["amount_cents"] == 519 and product["price_source"] == "seeded"


def test_a_scan_of_the_allergy_demo_item_uses_its_price_without_the_index(client, monkeypatch):
    import api.scan as scan_api
    from models.schemas import VisionExtract

    async def no_index(product):
        raise AssertionError("the index must not be asked for a demo item")
    monkeypatch.setattr(scan_api, "find_match", no_index)
    monkeypatch.setattr(scan_api, "extract_product", lambda img: VisionExtract(
        name="Allergy Relief", size="4mg, 100 tablets", category="cold_flu_allergy"))
    body = client.post("/v1/scan", files={"image": ("a.jpg", b"x", "image/jpeg")}).json()
    assert body["scan"]["product"]["amount_cents"] == 399 and body["scan"]["eligibility"]["label"] == "eligible"
    assert "online" not in body["voice"]["text"].lower()


def test_remove_last_item(client):
    add(client, advil(client))
    add(client, bandages(client))
    r = client.delete("/v1/cart/items/last")
    assert r.json()["voice"]["text"] == "Removed Bandages." and r.json()["cart"]["total_cents"] == 1299
    client.delete("/v1/cart/items/last")
    assert client.delete("/v1/cart/items/last").json()["voice"]["text"] == "Your cart is already empty."


def test_clear_cart_needs_a_confirmation_prompt(client):
    add(client, advil(client))
    assert client.request("DELETE", "/v1/cart", json={"prompt_id": "made-up"}).status_code == 409
    asked = say(client, "clear my cart").json()
    assert asked["action"] == "clear_cart_confirm" and asked["voice"]["response_scope"] == "confirm_clear_cart"
    assert client.get("/v1/cart").json()["total_cents"] == 1299          # asking changed nothing
    r = client.request("DELETE", "/v1/cart", json={"prompt_id": asked["voice"]["prompt_id"]})
    assert r.status_code == 200 and r.json()["cart"]["groups"] == []


def test_cards_endpoint_lists_the_cards(client):
    cards = client.get("/v1/cards").json()
    assert {c["id"]: c["balance_cents"] for c in cards} == {HSA: 34000, FSA: 2500, VISA: 500000}
    # last4 and network are null until a card is linked (POST /v1/cards); the app reads them
    assert set(cards[0]) == {"id", "type", "nickname", "balance_cents", "status", "last4", "network"}


def test_database_down_is_a_spoken_503(client, fake):
    fake.down = True
    r = client.get("/v1/cart")
    assert r.status_code == 503 and r.json()["error"]["code"] == "E_DB_UNAVAILABLE"
    assert client.post("/v1/checkout/preview").status_code == 503


# --- checkout: run 1 ---------------------------------------------------------------------------------

def test_run_1_ends_at_321_52_and_speaks_no_balance(client, fake):
    fill_run1(client)
    p = client.post("/v1/checkout/preview").json()
    assert p["total_cents"] == 2347 and p["issues"] == []
    text = p["voice"]["text"]
    assert "$23.47 before tax" in text and "$18.48 on your FSA card" in text and "$4.99 on your Visa credit" in text
    assert text.endswith("Ready to check out?") and p["voice"]["response_scope"] == "confirm_checkout"

    r = client.post("/v1/checkout/confirm", json={"idempotency_key": "run1", "prompt_id": p["voice"]["prompt_id"]})
    assert r.status_code == 200
    body = r.json()
    assert fake.cards[FSA]["balance_cents"] == 652 and fake.cards[VISA]["balance_cents"] == 499501
    assert fake.cards[HSA]["balance_cents"] == 34000
    voice = body["voice"]
    # FSA ends at $6.52: read back plainly, never flagged as low (team decision 2026-10-24)
    assert voice["priority"] == "normal" and "simulated" in voice["text"] and "$18.48" in voice["text"]
    assert "running low" not in voice["text"] and "take your items with you" in voice["text"]
    assert "$6.52" not in voice["text"] and "$340" not in voice["text"]
    assert client.get("/v1/cart").json()["groups"] == []
    assert {b["id"]: b["balance_cents"] for b in body["new_balances"]}[FSA] == 652


def test_a_repeated_idempotency_key_returns_the_original_payment(client, fake):
    fill_run1(client)
    p = client.post("/v1/checkout/preview").json()
    first = client.post("/v1/checkout/confirm", json={"idempotency_key": "k1", "prompt_id": p["voice"]["prompt_id"]}).json()
    again = client.post("/v1/checkout/confirm", json={"idempotency_key": "k1", "prompt_id": p["voice"]["prompt_id"]})
    assert again.status_code == 200 and again.json()["payment_id"] == first["payment_id"]
    assert fake.cards[FSA]["balance_cents"] == 652                      # charged once


def test_a_new_key_cannot_reuse_a_spent_prompt(client):
    fill_run1(client)
    p = client.post("/v1/checkout/preview").json()
    client.post("/v1/checkout/confirm", json={"idempotency_key": "a", "prompt_id": p["voice"]["prompt_id"]})
    r = client.post("/v1/checkout/confirm", json={"idempotency_key": "b", "prompt_id": p["voice"]["prompt_id"]})
    assert r.status_code == 409


def test_checkout_of_an_empty_cart(client):
    p = client.post("/v1/checkout/preview").json()
    assert p["voice"]["text"].startswith("Your cart is empty") and p["voice"]["prompt_id"] is None


def test_checkout_with_no_active_card_is_blocked(client, fake):
    add(client, advil(client))
    for card in fake.cards.values():
        card["status"] = "frozen"
    p = client.post("/v1/checkout/preview").json()
    assert "can't check out" in p["voice"]["text"] and p["voice"]["prompt_id"] is None


def test_a_balance_change_between_preview_and_confirm_charges_nothing(client, fake):
    fill_run1(client)
    p = client.post("/v1/checkout/preview").json()
    fake.set_balance(FSA, 1500)                           # someone spent from the card meanwhile
    r = client.post("/v1/checkout/confirm", json={"idempotency_key": "x", "prompt_id": p["voice"]["prompt_id"]})
    body = r.json()
    assert r.status_code == 200 and body["payment_id"] is None and fake.payments == {}
    assert body["voice"]["text"].startswith("Something changed") and "Ready to check out?" in body["voice"]["text"]
    assert "can't cover" not in body["voice"]["text"]
    assert fake.cards[FSA]["balance_cents"] == 1500 and len(fake.items) == 3
    assert body["voice"]["prompt_id"] and body["voice"]["prompt_id"] != p["voice"]["prompt_id"]


def test_an_item_added_after_the_preview_forces_a_new_confirmation(client, fake):
    add(client, advil(client))
    p = client.post("/v1/checkout/preview").json()
    add(client, bandages(client))
    r = client.post("/v1/checkout/confirm", json={"idempotency_key": "y", "prompt_id": p["voice"]["prompt_id"]}).json()
    assert r["payment_id"] is None and fake.payments == {} and "$18.48" in r["voice"]["text"]


def test_a_low_balance_after_checkout_is_never_flagged(client, fake):
    fake.set_balance(FSA, 2000)                  # $20.00 - $12.99 leaves $7.01
    add(client, advil(client))
    p = client.post("/v1/checkout/preview").json()
    r = client.post("/v1/checkout/confirm", json={"idempotency_key": "low", "prompt_id": p["voice"]["prompt_id"]}).json()
    assert r["voice"]["priority"] == "normal"
    assert "running low" not in r["voice"]["text"] and "add funds" not in r["voice"]["text"]
    assert "$7.01" not in r["voice"]["text"]


# --- checkout: run 2 ---------------------------------------------------------------------------------

def test_run_2_moves_items_to_the_next_card_quietly_and_a_yes_pays_the_split(client, fake):
    client.post("/v1/demo/reset", json={"run": 2})
    fake.set_balance(HSA, 500)                   # the HSA ($5.00) cannot take the $5.49 bandages, so the Visa does
    add(client, advil(client))
    add(client, bandages(client))
    fake.items[1]["assigned_card_id"] = FSA      # both on the FSA, as if the balance changed after adding
    p = client.post("/v1/checkout/preview").json()
    text = p["voice"]["text"]
    # Only where things go, never that a card was short (team decision 2026-10-24)
    assert "$12.99 on your FSA card" in text and "$5.49 on your Visa credit" in text
    assert "can't cover" not in text and "$15.00" not in text and p["issues"] == []
    assert {g["card_id"]: g["subtotal_cents"] for g in p["groups"]} == {FSA: 1299, VISA: 549}
    assert p["voice"]["response_scope"] == "confirm_checkout"

    r = client.post("/v1/checkout/confirm", json={"idempotency_key": "run2", "prompt_id": p["voice"]["prompt_id"]})
    assert r.status_code == 200 and r.json()["payment_id"]
    assert fake.cards[FSA]["balance_cents"] == 201 and fake.cards[VISA]["balance_cents"] == 499451
    assert "$15.00" not in r.json()["voice"]["text"] and r.json()["voice"]["priority"] == "normal"


def test_run_2_with_both_health_cards_short_moves_the_bandages_to_the_visa(client, fake):
    """Spending order is FSA, then HSA, then the Visa: in run 2 the HSA ($5.00) cannot take the $5.49 bandages either, so they go to the Visa."""
    client.post("/v1/demo/reset", json={"run": 2})
    add(client, advil(client))
    add(client, bandages(client))
    fake.items[1]["assigned_card_id"] = FSA      # both on the FSA, as if the balance changed after adding
    p = client.post("/v1/checkout/preview").json()
    assert "$5.49 on your Visa credit" in p["voice"]["text"] and "can't cover" not in p["voice"]["text"]
    assert {g["card_id"]: g["subtotal_cents"] for g in p["groups"]} == {FSA: 1299, VISA: 549}
    r = client.post("/v1/checkout/confirm", json={"idempotency_key": "run2visa", "prompt_id": p["voice"]["prompt_id"]})
    assert r.status_code == 200
    assert fake.cards[FSA]["balance_cents"] == 201 and fake.cards[HSA]["balance_cents"] == 500
    assert fake.cards[VISA]["balance_cents"] == 499451                      # the bandages went to the Visa


def test_nothing_that_covers_an_item_means_no_question(client, fake):
    fake.set_balance(FSA, 100); fake.set_balance(HSA, 100); fake.set_balance(VISA, 100)
    fake.items.append({"id": "i1", "seq": 1, "scan_id": "s", "product_key": "k", "display_name": "Advil",
                       "amount_cents": 1299, "amount_basis": "shelf_price", "assigned_card_id": FSA,
                       "eligibility_label": "eligible", "user_overrode_card": False})
    p = client.post("/v1/checkout/preview").json()
    assert "Please use another card for this item." in p["voice"]["text"] and p["voice"]["prompt_id"] is None


def test_demo_reset_restores_the_seed_state(client, fake):
    fill_run1(client)
    r = client.post("/v1/demo/reset", json={"run": 2})
    assert r.status_code == 200 and r.json()["cart"]["groups"] == []
    assert {c["id"]: c["balance_cents"] for c in r.json()["cards"]}[FSA] == 1500
    assert client.post("/v1/demo/reset", json={"run": 3}).status_code == 422
    assert memory.last() is None


# --- /v1/command ---------------------------------------------------------------------------------------

def test_yes_adds_the_scanned_item_through_its_prompt(client):
    s = advil(client)
    r = say(client, "yes add that", s["voice"]["prompt_id"]).json()
    assert r["action"] == "add_to_cart" and r["voice"]["text"].startswith("Added Advil")
    assert client.get("/v1/cart").json()["total_cents"] == 1299


def test_yes_without_a_live_prompt_is_expired(client):
    r = say(client, "yes")
    assert r.status_code == 409 and r.json()["error"]["code"] == "E_PROMPT_EXPIRED"
    s = advil(client)
    say(client, "yes", s["voice"]["prompt_id"])
    assert say(client, "yes", s["voice"]["prompt_id"]).status_code == 409        # single use
    assert client.get("/v1/cart").json()["total_cents"] == 1299


def test_no_and_skip_discard_without_touching_the_cart(client):
    s = advil(client)
    assert say(client, "skip it", s["voice"]["prompt_id"]).json()["voice"]["text"] == "Okay, skipped."
    assert say(client, "no", s["voice"]["prompt_id"]).json()["action"] == "skip"
    assert client.get("/v1/cart").json()["groups"] == []


def test_dont_add_that_is_a_no_not_a_yes(client):
    s = advil(client)
    assert say(client, "don't add that", s["voice"]["prompt_id"]).json()["action"] == "skip"


def test_yes_adds_an_unlisted_item_to_the_visa(client):
    s = scan(client, "Yoga Mat", 2500, upc=None, medication=False, category="other")
    r = say(client, "yes", s["voice"]["prompt_id"]).json()
    assert r["action"] == "add_to_cart" and "Visa credit" in r["voice"]["text"]


def test_yes_to_the_only_alternative_card(client, fake):
    client.post("/v1/demo/reset", json={"run": 2})
    s = scan(client, "Advil Ibuprofen 200mg", 1600, upc=None, medication=True, category="pain_relief")
    assert s["recommendation"]["reason_code"] == "routed_to_next_card"
    assert s["recommendation"]["card_id"] == VISA and "balance" not in s["voice"]["text"]
    r = say(client, "yes", s["voice"]["prompt_id"]).json()
    assert r["action"] == "add_to_cart" and "Visa credit" in r["voice"]["text"]


def test_naming_a_health_card_for_a_not_eligible_item_is_refused(client):
    s = kettle(client)
    r = say(client, "use my FSA", s["voice"]["prompt_id"]).json()
    assert r["action"] == "choose_card" and "could not confirm eligibility for that card" in r["voice"]["text"]
    assert client.get("/v1/cart").json()["groups"] == []
    assert say(client, "visa", r["voice"]["prompt_id"]).json()["action"] == "add_to_cart"


def test_cart_checkout_and_yes_by_voice(client, fake):
    fill_run1(client)
    cart = say(client, "what's in my cart").json()
    assert cart["voice"]["text"].startswith("You have 3 items, $23.47 before tax. On your FSA card:")
    pre = say(client, "checkout").json()
    assert pre["action"] == "checkout_preview" and pre["result"]["total_cents"] == 2347
    done = say(client, "yes", pre["voice"]["prompt_id"]).json()
    assert done["action"] == "checkout_confirm" and "simulated" in done["voice"]["text"]
    assert fake.cards[FSA]["balance_cents"] == 652 and len(fake.payments) == 1


@pytest.mark.parametrize("phrase", ["I'm ready to checkout", "ready", "checkout", "yeah I'm ready"])
def test_ready_or_checkout_phrase_confirms_the_checkout_question(client, fake, phrase):
    fill_run1(client)
    pre = say(client, "checkout").json()
    done = say(client, phrase, pre["voice"]["prompt_id"]).json()
    assert done["action"] == "checkout_confirm"
    assert len(fake.payments) == 1


def test_not_ready_does_not_confirm_the_checkout_question(client, fake):
    fill_run1(client)
    pre = say(client, "checkout").json()
    say(client, "not ready yet", pre["voice"]["prompt_id"])
    assert len(fake.payments) == 0


def test_remove_last_by_voice_reads_back_what_was_removed(client):
    add(client, advil(client))
    add(client, bandages(client))
    r = say(client, "remove the last item").json()
    assert r["voice"]["text"] == "Removed Bandages."


def test_repeat_says_the_last_thing_again_verbatim(client):
    assert say(client, "read it again").json()["voice"]["text"] == "I haven't said anything yet."
    s = advil(client)
    again = say(client, "repeat that").json()
    assert again["action"] == "repeat" and again["voice"] == s["voice"]


def test_balance_questions_are_declined_without_a_number(client):
    r = say(client, "what is my HSA balance?").json()
    assert r["action"] == "balance_refused" and "$" not in r["voice"]["text"]


def test_accessibility_settings(client):
    assert say(client, "open accessibility settings").json()["action"] == "open_accessibility"


def test_unknown_words_and_low_confidence(client):
    r = say(client, "blah blah")
    assert r.status_code == 422 and r.json()["error"]["code"] == "E_STT_LOW_CONFIDENCE"
    r = say(client, "checkout", confidence=0.2)
    assert r.status_code == 422 and r.json()["error"]["code"] == "E_STT_LOW_CONFIDENCE"
    assert say(client, "checkout", confidence=0.9).status_code == 200
    assert say(client, "checkout").status_code == 200                      # no confidence reported


def test_no_response_anywhere_speaks_a_balance(client, fake):
    """Walk both runs through the API and check every spoken line against the real balances."""
    import re
    spoken = []
    for run in (1, 2):
        client.post("/v1/demo/reset", json={"run": run})
        forbidden = {f"${c['balance_cents'] / 100:,.2f}" for c in fake.cards.values()
                     if c["balance_cents"] not in (1299, 549, 499, 1848)}
        for item in (advil, bandages, kettle):
            s = item(client); spoken.append(s["voice"]["text"])
            r = add(client, s); spoken.append(r.json()["voice"]["text"])
        for words in ("what's in my cart", "what is my balance", "checkout"):
            r = say(client, words).json(); spoken.append(r["voice"]["text"])
        pre = client.post("/v1/checkout/preview").json(); spoken.append(pre["voice"]["text"])
        done = client.post("/v1/checkout/confirm", json={"idempotency_key": f"w{run}",
                                                         "prompt_id": pre["voice"]["prompt_id"]}).json()
        spoken.append(done["voice"]["text"])
        for text in spoken:
            assert not (set(re.findall(r"\$[\d,]+\.\d{2}", text)) & forbidden), text
    assert len(spoken) > 20


# --- Nessie payment log --------------------------------------------------------------------------------

@pytest.fixture
def nessie_log(fake, monkeypatch):
    """Link the FSA and the Visa to Nessie accounts and capture the withdrawals posted."""
    import httpx
    from payments import nessie
    monkeypatch.setenv("NESSIE_API_KEY", "test-key")
    fake.cards[FSA]["nessie_account_id"], fake.cards[VISA]["nessie_account_id"] = "acc-fsa", "acc-visa"
    sent = []

    async def handler(request):
        sent.append(request)
        return httpx.Response(201, json={"code": 201})
    monkeypatch.setattr(nessie, "_transport", httpx.MockTransport(handler))
    return sent


def amounts(sent):
    import json
    return {r.url.path.split("/")[2]: json.loads(r.content)["amount"] for r in sent}


def test_a_checkout_is_recorded_in_nessie_once_per_card(client, nessie_log):
    fill_run1(client)
    p = client.post("/v1/checkout/preview").json()
    body = {"idempotency_key": "n1", "prompt_id": p["voice"]["prompt_id"]}
    first = client.post("/v1/checkout/confirm", json=body).json()
    assert amounts(nessie_log) == {"acc-fsa": 1848, "acc-visa": 499}
    import json
    assert first["payment_id"] in json.loads(nessie_log[0].content)["description"]
    client.post("/v1/checkout/confirm", json=body)                      # a retry is not a second payment
    assert len(nessie_log) == 2


def test_an_unlinked_card_is_left_out_of_the_log(client, nessie_log, fake):
    fake.cards[VISA]["nessie_account_id"] = None
    fill_run1(client)
    p = client.post("/v1/checkout/preview").json()
    client.post("/v1/checkout/confirm", json={"idempotency_key": "n2", "prompt_id": p["voice"]["prompt_id"]})
    assert amounts(nessie_log) == {"acc-fsa": 1848}


def test_a_voice_checkout_is_recorded_too(client, nessie_log):
    fill_run1(client)
    pre = say(client, "checkout").json()
    say(client, "yes", pre["voice"]["prompt_id"])
    assert amounts(nessie_log) == {"acc-fsa": 1848, "acc-visa": 499}


def test_run_2_logs_the_split_that_was_actually_charged(client, nessie_log, fake):
    client.post("/v1/demo/reset", json={"run": 2})          # a reset reloads the cards, so link them after
    fake.set_balance(HSA, 500)                              # the HSA cannot take the bandages, so the Visa does
    fake.cards[FSA]["nessie_account_id"], fake.cards[VISA]["nessie_account_id"] = "acc-fsa", "acc-visa"
    add(client, advil(client)); add(client, bandages(client))
    p = client.post("/v1/checkout/preview").json()
    client.post("/v1/checkout/confirm", json={"idempotency_key": "n3", "prompt_id": p["voice"]["prompt_id"]})
    assert amounts(nessie_log) == {"acc-fsa": 1299, "acc-visa": 549}


def test_nothing_is_logged_when_nothing_was_charged(client, nessie_log, fake):
    fill_run1(client)
    p = client.post("/v1/checkout/preview").json()
    fake.set_balance(FSA, 1500)                                         # forces a re-confirmation
    client.post("/v1/checkout/confirm", json={"idempotency_key": "n4", "prompt_id": p["voice"]["prompt_id"]})
    assert nessie_log == []


def test_a_nessie_outage_does_not_affect_the_payment(client, fake, monkeypatch):
    import httpx
    from payments import nessie
    monkeypatch.setenv("NESSIE_API_KEY", "test-key")
    fake.cards[FSA]["nessie_account_id"] = "acc-fsa"

    async def down(request):
        raise httpx.ConnectTimeout("nessie is down")
    monkeypatch.setattr(nessie, "_transport", httpx.MockTransport(down))
    fill_run1(client)
    p = client.post("/v1/checkout/preview").json()
    r = client.post("/v1/checkout/confirm", json={"idempotency_key": "n5", "prompt_id": p["voice"]["prompt_id"]})
    assert r.status_code == 200 and r.json()["payment_id"] and fake.cards[FSA]["balance_cents"] == 652


# --- invoice ---------------------------------------------------------------------------------------------

def checkout_run1(client, key="inv"):
    fill_run1(client)
    p = client.post("/v1/checkout/preview").json()
    return client.post("/v1/checkout/confirm", json={"idempotency_key": key, "prompt_id": p["voice"]["prompt_id"]}).json()


def test_the_invoice_has_store_date_lines_and_total(client):
    from datetime import datetime
    body = checkout_run1(client)
    inv = body["invoice"]
    today = datetime.now().astimezone().date()
    assert inv["store"] == {"name": "Rewind Demo Store", "address": "123 Main Street, Berkeley, CA 94704"}
    assert inv["date"] == today.isoformat() and inv["date_display"] == f"{today:%B} {today.day}, {today.year}"
    assert [(l["name"], l["quantity"], l["unit_price_cents"], l["line_total_cents"]) for l in inv["lines"]] == [
        ("Advil Ibuprofen 200mg", 1, 1299, 1299), ("Bandages", 1, 549, 549), ("Kettle Corn", 1, 499, 499)]
    assert [l["line_total_display"] for l in inv["lines"]] == ["$12.99", "$5.49", "$4.99"]
    assert inv["total_cents"] == 2347 and inv["total_display"] == "$23.47" and inv["simulated"] is True
    assert inv["invoice_id"] == body["payment_id"]


def test_the_same_product_twice_is_one_line_with_a_quantity(client):
    for _ in range(2):
        add(client, bandages(client))
    add(client, advil(client))
    p = client.post("/v1/checkout/preview").json()
    inv = client.post("/v1/checkout/confirm", json={"idempotency_key": "q", "prompt_id": p["voice"]["prompt_id"]}).json()["invoice"]
    assert [(l["name"], l["quantity"], l["unit_price_cents"], l["line_total_cents"]) for l in inv["lines"]] == [
        ("Bandages", 2, 549, 1098), ("Advil Ibuprofen 200mg", 1, 1299, 1299)]
    assert inv["total_cents"] == 2397 == sum(l["line_total_cents"] for l in inv["lines"])


def test_the_invoice_comes_back_unchanged_on_a_retry_and_by_id(client):
    fill_run1(client)
    p = client.post("/v1/checkout/preview").json()
    body = {"idempotency_key": "r", "prompt_id": p["voice"]["prompt_id"]}
    first = client.post("/v1/checkout/confirm", json=body).json()
    assert client.get("/v1/cart").json()["groups"] == []                    # the cart is gone; the invoice is not
    again = client.post("/v1/checkout/confirm", json=body).json()
    assert again["invoice"] == first["invoice"]
    looked_up = client.get(f"/v1/payments/{first['payment_id']}/invoice")
    assert looked_up.status_code == 200 and looked_up.json() == first["invoice"]
    missing = client.get("/v1/payments/nope/invoice")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "E_NOT_FOUND"


def test_the_invoice_follows_the_run_2_reroute(client):
    client.post("/v1/demo/reset", json={"run": 2})
    add(client, advil(client)); add(client, bandages(client))
    p = client.post("/v1/checkout/preview").json()
    body = client.post("/v1/checkout/confirm", json={"idempotency_key": "r2", "prompt_id": p["voice"]["prompt_id"]}).json()
    assert body["invoice"]["total_cents"] == 1848 and len(body["invoice"]["lines"]) == 2


def test_a_voice_checkout_returns_the_invoice(client):
    fill_run1(client)
    pre = say(client, "checkout").json()
    done = say(client, "yes", pre["voice"]["prompt_id"]).json()
    assert done["result"]["invoice"]["total_display"] == "$23.47" and len(done["result"]["invoice"]["lines"]) == 3


def test_no_invoice_when_nothing_was_charged(client, fake):
    fill_run1(client)
    p = client.post("/v1/checkout/preview").json()
    fake.set_balance(FSA, 1500)
    body = client.post("/v1/checkout/confirm", json={"idempotency_key": "none", "prompt_id": p["voice"]["prompt_id"]}).json()
    assert body["payment_id"] is None and body["invoice"] is None


def test_the_store_can_be_changed_without_code(client, monkeypatch):
    monkeypatch.setenv("REWIND_STORE_NAME", "Corner Pharmacy")
    monkeypatch.setenv("REWIND_STORE_ADDRESS", "9 Elm Street")
    assert checkout_run1(client)["invoice"]["store"] == {"name": "Corner Pharmacy", "address": "9 Elm Street"}
