"""The PROPOSED endpoints Nak's app calls: card scan, link card, cart review, history list, check-in.

Fake database, stub vision, no network (same setup as test_api_flow.py).
"""
import pytest
from fastapi.testclient import TestClient

from api import memory, scan as scan_api
from main import create_app
from models.schemas import VisionExtract
from payments import store_checkin
from tests.fakes.fake_db import FakeDB
from vision import payment_card_reader
from vision.card_reader import CardExtract, PrintedCopay

FSA, HSA, VISA = "card_fsa_1", "card_hsa_1", "card_visa_1"
WALMART = {"lat": 37.8044, "lng": -122.2712}


@pytest.fixture
def fake(monkeypatch):
    memory.forget()
    store_checkin.check_out()
    return FakeDB(1).install(monkeypatch)


@pytest.fixture
def client(fake, monkeypatch):
    c = TestClient(create_app(), raise_server_exceptions=False)
    c.mp = monkeypatch
    return c


def scan(client, name, cents, medication, category):
    extract = VisionExtract(name=name, upc=None, shelf_price_cents=cents, is_medication=medication, category=category)
    client.mp.setattr(scan_api, "extract_product", lambda img: extract)
    r = client.post("/v1/scan", files={"image": ("f.jpg", b"jpeg", "image/jpeg")})
    assert r.status_code == 200, r.text
    return r.json()


def add(client, s):
    r = client.post("/v1/cart/items", json={"scan_id": s["scan"]["scan_id"], "prompt_id": s["voice"]["prompt_id"]})
    assert r.status_code == 200, r.text
    return r.json()["cart"]


def fill(client):
    add(client, scan(client, "Advil Ibuprofen 200mg", 1299, True, "pain_relief"))
    add(client, scan(client, "Bandages", 549, False, "first_aid"))
    return add(client, scan(client, "Kettle Corn", 499, False, "grocery"))


def items(cart):
    return sorted((i for g in cart["groups"] for i in g["items"]), key=lambda i: i["seq"])


def say(client, text, prompt_id):
    r = client.post("/v1/command", json={"transcript": text, "prompt_id": prompt_id})
    assert r.status_code == 200, r.text
    return r.json()


def checkout(client, key="k1"):
    preview = client.post("/v1/checkout/preview").json()
    r = client.post("/v1/checkout/confirm", json={"idempotency_key": key, "prompt_id": preview["voice"]["prompt_id"]})
    assert r.status_code == 200, r.text
    return r.json()


# --- card scan ---------------------------------------------------------------------------------

def card_scan(client, kind, data=b"jpeg"):
    return client.post("/v1/onboarding/card-scan", files={"image": ("c.jpg", data, "image/jpeg")}, data={"kind": kind})


def test_insurance_card_returns_name_plan_and_copays_but_no_ids(client, monkeypatch):
    from api import onboarding
    monkeypatch.setattr(onboarding, "read_card", lambda img: CardExtract(
        first_name="Alex", last_name="Rivera", insurer="UnitedHealthcare", plan_name="Student Resources",
        has_rx_section=True, printed_rx_copays=[PrintedCopay(label="Generic", amount_dollars=10.0)]))
    body = card_scan(client, "insurance").json()
    assert body["state"] == "read"
    ins = body["insurance"]
    assert (ins["member_first_name"], ins["insurer_name"]) == ("Alex", "UnitedHealthcare")
    assert ins["member_id_last4"] is None
    assert ins["rx"] == {"bin": None, "pcn": None, "group": None, "copays": [{"label": "Generic", "amount_cents": 1000}]}


def test_unreadable_insurance_card_is_unclear_not_an_error(client, monkeypatch):
    from api import onboarding
    monkeypatch.setattr(onboarding, "read_card", lambda img: CardExtract(has_rx_section=False))
    body = card_scan(client, "insurance").json()
    assert body["state"] == "unclear" and body["framing_hint"]


def test_payment_card_keeps_only_four_digits(client, monkeypatch):
    from api import onboarding
    extract = payment_card_reader.PaymentExtract(is_payment_card=True, network="visa", funding="debit",
                                                 last4="4111111111111111")
    monkeypatch.setattr(onboarding, "read_payment_card", lambda img: payment_card_reader.scrub(extract))
    body = card_scan(client, "payment").json()
    assert body["payment"] == {"network": "visa", "card_type": "general", "funding": "debit", "last4": None}


def test_payment_card_with_hsa_printed_is_an_hsa_card(client):
    body = card_scan(client, "payment").json()          # stub vision: a Visa HSA ending 4242
    assert body["payment"]["card_type"] == "hsa" and body["payment"]["last4"] == "4242"


def test_card_scan_rejects_a_bad_kind_and_an_empty_image(client):
    assert card_scan(client, "passport").status_code == 422
    assert card_scan(client, "payment", data=b"").json()["error"]["code"] == "E_BAD_REQUEST"


# --- link a card -------------------------------------------------------------------------------

def test_linking_an_hsa_updates_the_seeded_card_and_keeps_its_balance(client, fake):
    before = fake.cards[HSA]["balance_cents"]
    r = client.post("/v1/cards", json={"type": "hsa", "nickname": "Visa HSA", "last4": "4242", "network": "visa"})
    assert r.status_code == 200, r.text
    card = r.json()
    assert (card["id"], card["last4"], card["balance_cents"]) == (HSA, "4242", before)
    listed = {c["id"]: c for c in client.get("/v1/cards").json()}
    assert listed[HSA]["network"] == "visa"


def test_link_card_rejects_more_than_four_digits(client):
    r = client.post("/v1/cards", json={"type": "general", "nickname": "Visa", "last4": "41111", "network": "visa"})
    assert r.status_code == 422


# --- cart review -------------------------------------------------------------------------------

def test_tap_an_item_then_yes_removes_it_and_offers_the_rest(client):
    first = items(fill(client))[0]
    r = client.post(f"/v1/cart/items/{first['id']}/review").json()
    assert r["item_id"] == first["id"]
    assert r["voice"]["response_scope"] == "confirm_remove_item"
    assert first["display_name"] in r["voice"]["text"]
    res = say(client, "yes", r["voice"]["prompt_id"])
    assert res["action"] == "review_item" and len(items(res["result"]["cart"])) == 2
    assert "two other items" in res["voice"]["text"]
    assert res["voice"]["response_scope"] == "confirm_review_rest"


def test_keep_then_no_closes_the_review(client):
    first = items(fill(client))[0]
    r = client.post(f"/v1/cart/items/{first['id']}/review").json()
    kept = say(client, "no, keep it", r["voice"]["prompt_id"])
    assert len(items(kept["result"]["cart"])) == 3 and kept["voice"]["text"].startswith("Keeping")
    done = say(client, "no", kept["voice"]["prompt_id"])
    assert done["action"] == "review_done" and "ready to check out" in done["voice"]["text"]


def test_yes_to_the_rest_reads_the_next_unreviewed_item(client):
    cart = items(fill(client))
    r = client.post(f"/v1/cart/items/{cart[0]['id']}/review").json()
    kept = say(client, "keep", r["voice"]["prompt_id"])
    nxt = say(client, "yes", kept["voice"]["prompt_id"])
    assert nxt["result"]["item_id"] == cart[1]["id"]
    assert nxt["voice"]["response_scope"] == "confirm_remove_item"


def test_remove_on_a_review_removes_that_item_not_the_last_one(client):
    cart = items(fill(client))
    r = client.post(f"/v1/cart/items/{cart[0]['id']}/review").json()
    res = say(client, "remove it", r["voice"]["prompt_id"])
    left = [i["id"] for i in items(res["result"]["cart"])]
    assert cart[0]["id"] not in left and cart[2]["id"] in left


def test_reviewing_a_missing_item_says_so(client):
    fill(client)
    r = client.post("/v1/cart/items/nope/review").json()
    assert r["item_id"] is None and "no longer" in r["voice"]["text"]


def test_a_late_answer_to_a_review_is_expired(client, fake):
    first = items(fill(client))[0]
    r = client.post(f"/v1/cart/items/{first['id']}/review").json()
    fake.advance(16)
    res = client.post("/v1/command", json={"transcript": "yes", "prompt_id": r["voice"]["prompt_id"]})
    assert res.json()["error"]["code"] == "E_PROMPT_EXPIRED"


# --- purchase history --------------------------------------------------------------------------

def test_history_lists_each_payment_with_cards_tax_and_reimbursement(client):
    fill(client)
    paid = checkout(client)
    inv = client.get("/v1/payments").json()["invoices"]
    assert len(inv) == 1 and inv[0]["invoice_id"] == paid["payment_id"]
    one = inv[0]
    assert one["subtotal_cents"] == 1299 + 549 + 499
    assert one["tax_cents"] == (one["subtotal_cents"] * 725 + 5000) // 10000
    assert one["total_cents"] == one["subtotal_cents"] + one["tax_cents"]
    assert {l["name"] for l in one["lines"]} == {"Advil Ibuprofen 200mg", "Bandages", "Kettle Corn"}
    kettle = next(l for l in one["lines"] if l["name"] == "Kettle Corn")
    assert kettle["card_type"] == "general" and kettle["eligibility_label"] == "not_eligible"
    assert one["reimbursable_cents"] == 0                       # nothing eligible went on the Visa
    assert sum(p["amount_cents"] for p in one["payments"]) == one["subtotal_cents"]
    assert one["store"]["phone"]


def test_history_is_empty_before_any_payment(client):
    assert client.get("/v1/payments").json() == {"invoices": []}


# --- store check-in ------------------------------------------------------------------------------

def test_near_a_store_asks_and_yes_checks_in(client):
    asked = client.post("/v1/checkin/nearby", json={"lat": WALMART["lat"] + 0.0005, "lng": WALMART["lng"]}).json()
    assert asked["store"]["name"] == "Walmart Pharmacy" and "lat" not in asked["store"]
    assert asked["voice"]["response_scope"] == "confirm_checkin"
    res = say(client, "yes", asked["voice"]["prompt_id"])
    assert res["action"] == "checked_in" and "Walmart Pharmacy" in res["voice"]["text"]
    assert client.post("/v1/checkin/nearby", json={"store_id": "store_walmart"}).json() is None   # already in


def test_far_from_every_store_asks_nothing(client):
    assert client.post("/v1/checkin/nearby", json={"lat": 40.0, "lng": -100.0}).json() is None
    assert client.post("/v1/checkin/nearby", json={}).json() is None


def test_no_does_not_check_in(client):
    asked = client.post("/v1/checkin/nearby", json={"store_id": "store_walmart"}).json()
    assert say(client, "no", asked["voice"]["prompt_id"])["action"] == "skip"
    assert store_checkin.current() is None


def test_invoice_names_the_checked_in_store(client):
    asked = client.post("/v1/checkin/nearby", json={"store_id": "store_walmart"}).json()
    say(client, "yes", asked["voice"]["prompt_id"])
    fill(client)
    checkout(client)
    store = client.get("/v1/payments").json()["invoices"][0]["store"]
    assert store["name"] == "Walmart Pharmacy" and set(store) == {"id", "name", "address", "phone"}


def test_leaving_the_store_checks_out(client):
    asked = client.post("/v1/checkin/nearby", json={"store_id": "store_walmart"}).json()
    say(client, "yes", asked["voice"]["prompt_id"])
    assert client.post("/v1/checkin/still-here", json={"store_id": "store_walmart", **WALMART}).json() == {"at_store": True}
    gone = client.post("/v1/checkin/still-here", json={"store_id": "store_walmart", "lat": 37.9, "lng": -122.27}).json()
    assert gone == {"at_store": False} and store_checkin.current() is None


def test_demo_reset_forgets_the_check_in(client):
    asked = client.post("/v1/checkin/nearby", json={"store_id": "store_walmart"}).json()
    say(client, "yes", asked["voice"]["prompt_id"])
    client.post("/v1/demo/reset", json={"run": 1})
    assert store_checkin.current() is None


# --- prescription label (tech spec 2.3) ---------------------------------------------------------

def label_scan(client):
    extract = VisionExtract(image_kind="pharmacy_label", name="Omeprazole", size="20mg", is_medication=True,
                            is_prescription_only=True, category="digestive_health")
    client.mp.setattr(scan_api, "extract_product", lambda img: extract)
    return client.post("/v1/scan", files={"image": ("f.jpg", b"jpeg", "image/jpeg")}).json()


def test_a_pharmacy_label_is_read_back_and_never_priced(client):
    s = label_scan(client)
    assert s["voice"]["response_scope"] == "confirm_strength" and s["recommendation"] is None
    assert "Omeprazole, 20mg" in s["voice"]["text"]
    assert s["scan"]["product"]["is_prescription_only"] and s["scan"]["product"]["size"] == "20mg"


def test_yes_confirms_the_strength_and_sends_to_the_pharmacist(client):
    s = label_scan(client)
    res = say(client, "yes", s["voice"]["prompt_id"])
    assert res["action"] == "strength_confirmed" and "pharmacist" in res["voice"]["text"]
    assert "$" not in res["voice"]["text"]                       # no copay figure is ever invented
    assert client.get("/v1/cart").json()["groups"] == []        # nothing added from a label


def test_no_to_the_strength_asks_to_read_it_again(client):
    s = label_scan(client)
    assert say(client, "no", s["voice"]["prompt_id"])["action"] == "skip"


# --- history by voice --------------------------------------------------------------------------

@pytest.mark.parametrize("text, action", [
    ("find invoice history", "open_history"), ("show my receipts", "open_history"),
    ("close history", "close_history"), ("hide my invoices", "close_history")])
def test_history_voice_commands(client, text, action):
    assert say(client, text, None)["action"] == action


# --- time to answer ------------------------------------------------------------------------------

def test_every_question_follows_the_time_to_answer_header(client, fake):
    extract = VisionExtract(name="Advil Ibuprofen 200mg", upc=None, shelf_price_cents=1299, is_medication=True,
                            category="pain_relief")
    client.mp.setattr(scan_api, "extract_product", lambda img: extract)
    s = client.post("/v1/scan", files={"image": ("f.jpg", b"jpeg", "image/jpeg")},
                    headers={"X-Rewind-Prompt-TTL": "60"}).json()
    fake.advance(45)                                             # past the 15 s default, inside 60 s
    r = client.post("/v1/cart/items", json={"scan_id": s["scan"]["scan_id"], "prompt_id": s["voice"]["prompt_id"]})
    assert r.status_code == 200, r.text


# --- declined payment demo -----------------------------------------------------------------------

def test_decline_demo_declines_once_and_charges_nothing(client, fake):
    fill(client)
    before = {k: v["balance_cents"] for k, v in fake.cards.items()}
    client.post("/v1/demo/decline-next")
    pre = client.post("/v1/checkout/preview").json()
    r = client.post("/v1/checkout/confirm", json={"idempotency_key": "d", "prompt_id": pre["voice"]["prompt_id"]})
    assert r.status_code == 402 and r.json()["error"]["code"] == "E_CARD_DECLINED"
    assert {k: v["balance_cents"] for k, v in fake.cards.items()} == before and fake.payments == {}
    again = client.post("/v1/checkout/preview").json()
    ok = client.post("/v1/checkout/confirm", json={"idempotency_key": "d2", "prompt_id": again["voice"]["prompt_id"]})
    assert ok.status_code == 200                                 # only the next payment was declined
