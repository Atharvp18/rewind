"""POST /v1/prompts/reissue (proposed for spec 0.6): a fresh question after a late answer."""
import pytest
from fastapi.testclient import TestClient

from api import memory, scan as scan_api
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


def scan(client, name="Advil Ibuprofen 200mg", cents=1299, medication=True, category="pain_relief"):
    extract = VisionExtract(name=name, upc=None, shelf_price_cents=cents, is_medication=medication,
                            category=category)
    client.mp.setattr(scan_api, "extract_product", lambda img: extract)
    r = client.post("/v1/scan", files={"image": ("f.jpg", b"jpeg", "image/jpeg")})
    assert r.status_code == 200, r.text
    return r.json()


def reissue(client, scan_id, scope="confirm_add", ttl=None):
    headers = {"X-Rewind-Prompt-TTL": str(ttl)} if ttl is not None else {}
    return client.post("/v1/prompts/reissue", json={"scan_id": scan_id, "scope": scope}, headers=headers)


def add(client, scan_id, prompt_id, card_id=None):
    return client.post("/v1/cart/items", json={"scan_id": scan_id, "card_id": card_id, "prompt_id": prompt_id})


def test_late_yes_then_reissue_adds_the_same_item(client, fake):
    s = scan(client)
    sid = s["scan"]["scan_id"]
    fake.advance(16)                                            # the scan's 15 s prompt has expired
    assert add(client, sid, s["voice"]["prompt_id"]).json()["error"]["code"] == "E_PROMPT_EXPIRED"
    r = reissue(client, sid)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scope"] == "confirm_add" and body["expires_in_s"] == 15
    added = add(client, sid, body["prompt_id"])
    assert added.status_code == 200, added.text
    assert added.json()["cart"]["total_cents"] == 1299


def test_ttl_follows_the_time_to_answer_setting(client, fake):
    sid = scan(client)["scan"]["scan_id"]
    r = reissue(client, sid, ttl=60).json()
    assert r["expires_in_s"] == 60
    fake.advance(45)
    assert add(client, sid, r["prompt_id"]).status_code == 200   # still open at 45 s


@pytest.mark.parametrize("value", ["7", "abc", "-1"])
def test_unknown_ttl_falls_back_to_the_default(client, value):
    sid = scan(client)["scan"]["scan_id"]
    r = client.post("/v1/prompts/reissue", json={"scan_id": sid, "scope": "confirm_add"},
                    headers={"X-Rewind-Prompt-TTL": value})
    assert r.json()["expires_in_s"] == 15


def test_reissued_prompt_is_single_use(client):
    sid = scan(client)["scan"]["scan_id"]
    pid = reissue(client, sid).json()["prompt_id"]
    assert add(client, sid, pid).status_code == 200
    assert add(client, sid, pid).json()["error"]["code"] == "E_PROMPT_EXPIRED"


def test_item_already_in_the_cart_is_not_asked_again(client):
    s = scan(client)
    sid = s["scan"]["scan_id"]
    assert add(client, sid, s["voice"]["prompt_id"]).status_code == 200
    r = reissue(client, sid)
    assert r.status_code == 422 and r.json()["error"]["code"] == "E_BAD_REQUEST"


def test_routing_reruns_against_todays_balance(client, fake):
    sid = scan(client)["scan"]["scan_id"]                       # Advil $12.99 -> FSA ($25.00)
    fake.set_balance(FSA, 100)                                  # the FSA ran short since the scan
    body = reissue(client, sid).json()
    added = add(client, sid, body["prompt_id"]).json()["cart"]
    assert [g["card_id"] for g in added["groups"]] != [FSA]


def test_unknown_scan_is_not_found(client):
    r = reissue(client, "no-such-scan")
    assert r.status_code == 404 and r.json()["error"]["code"] == "E_NOT_FOUND"


def test_bad_scope_is_rejected(client):
    sid = scan(client)["scan"]["scan_id"]
    r = reissue(client, sid, scope="confirm_checkout")
    assert r.json()["error"]["code"] == "E_BAD_REQUEST"
