"""api/app_contract.py: the replies Nak's app gets when it sends X-Rewind-Client: app."""
import pytest
from fastapi.testclient import TestClient

from api import memory, scan as scan_api
from main import create_app
from models.schemas import VisionExtract
from payments import store_checkin
from tests.fakes.fake_db import FakeDB

APP = {"X-Rewind-Client": "app"}


@pytest.fixture
def client(monkeypatch):
    memory.forget()
    store_checkin.check_out()
    FakeDB(1).install(monkeypatch)
    c = TestClient(create_app(), raise_server_exceptions=False)
    c.mp = monkeypatch
    return c


def scan(client, name="Advil Ibuprofen 200mg", cents=1299, medication=True, category="pain_relief"):
    extract = VisionExtract(name=name, upc=None, shelf_price_cents=cents, is_medication=medication, category=category)
    client.mp.setattr(scan_api, "extract_product", lambda img: extract)
    return client.post("/v1/scan", files={"image": ("f.jpg", b"jpeg", "image/jpeg")}, headers=APP).json()


def say(client, text, prompt_id=None, headers=APP):
    r = client.post("/v1/command", json={"transcript": text, "prompt_id": prompt_id}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_yes_by_voice_is_add_item_with_the_cart_as_result(client):
    s = scan(client)
    res = say(client, "yes", s["voice"]["prompt_id"])
    assert res["action"] == "add_item"
    assert res["result"]["total_cents"] == 1299 and res["result"]["groups"][0]["items"][0]["display_name"]


def test_whats_in_my_cart_is_read_cart(client):
    s = scan(client)
    say(client, "yes", s["voice"]["prompt_id"])
    res = say(client, "what's in my cart")
    assert res["action"] == "read_cart" and res["result"]["total_cents"] == 1299


def test_checkout_by_voice_returns_a_full_preview_and_yes_returns_a_receipt(client):
    for args in (("Advil Ibuprofen 200mg", 1299, True, "pain_relief"), ("Kettle Corn", 499, False, "grocery")):
        s = scan(client, *args)
        say(client, "yes", s["voice"]["prompt_id"])
    pre = say(client, "checkout")
    assert pre["action"] == "checkout_preview"
    groups = pre["result"]["groups"]
    assert {i["display_name"] for g in groups for i in g["items"]} == {"Advil Ibuprofen 200mg", "Kettle Corn"}
    assert pre["result"]["voice"]["prompt_id"] == pre["voice"]["prompt_id"]

    done = say(client, "yes", pre["voice"]["prompt_id"])
    assert done["action"] == "checkout_confirmed"
    r = done["result"]
    assert all("card_id" in b for b in r["new_balances"])
    assert r["invoice"]["subtotal_cents"] == 1299 + 499 and r["invoice"]["tax_cents"] > 0
    assert sum(len(g["items"]) for g in r["groups"]) == 2


def test_rest_preview_and_confirm_use_the_app_shapes(client):
    s = scan(client)
    say(client, "yes", s["voice"]["prompt_id"])
    pre = client.post("/v1/checkout/preview", headers=APP).json()
    assert pre["groups"][0]["items"][0]["display_name"] == "Advil Ibuprofen 200mg"
    paid = client.post("/v1/checkout/confirm", headers=APP,
                       json={"idempotency_key": "k", "prompt_id": pre["voice"]["prompt_id"]}).json()
    assert paid["invoice"]["lines"][0]["name"] == "Advil Ibuprofen 200mg"
    assert paid["new_balances"][0].keys() == {"card_id", "balance_cents"}


def test_review_answer_puts_item_id_at_the_top(client):
    for args in (("Advil Ibuprofen 200mg", 1299, True, "pain_relief"), ("Bandages", 549, False, "first_aid")):
        s = scan(client, *args)
        say(client, "yes", s["voice"]["prompt_id"])
    cart = client.get("/v1/cart").json()
    first = sorted((i for g in cart["groups"] for i in g["items"]), key=lambda i: i["seq"])[0]
    r = client.post(f"/v1/cart/items/{first['id']}/review", headers=APP).json()
    kept = say(client, "keep", r["voice"]["prompt_id"])
    nxt = say(client, "yes", kept["voice"]["prompt_id"])
    assert nxt["action"] == "review_item" and nxt["item_id"] and "groups" in nxt["result"]


def test_check_in_result_is_the_store(client):
    asked = client.post("/v1/checkin/nearby", json={"store_id": "store_walmart"}, headers=APP).json()
    res = say(client, "yes", asked["voice"]["prompt_id"])
    assert res["action"] == "checked_in" and res["result"]["name"] == "Walmart Pharmacy"


def test_without_the_header_replies_are_unchanged(client):
    s = scan(client)
    res = say(client, "yes", s["voice"]["prompt_id"], headers={})
    assert res["action"] == "add_to_cart" and "cart" in res["result"]


def test_errors_pass_through_untranslated(client):
    r = client.post("/v1/command", json={"transcript": "yes", "prompt_id": "gone"}, headers=APP)
    assert r.status_code == 409 and r.json()["error"]["code"] == "E_PROMPT_EXPIRED"
