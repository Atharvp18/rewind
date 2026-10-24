"""Atharv's checkout and reset keep History's Moss memory in step (the phone path), and his
low-balance line is $10.00. Uses his fake database and test client; nothing touches the network."""
from lookup import purchase_memory
from tests.test_api_flow import FSA, add, advil, bandages, client, fake, fill_run1, kettle, say  # noqa: F401


def confirm(client, key):
    p = client.post("/v1/checkout/preview").json()
    return client.post("/v1/checkout/confirm", json={"idempotency_key": key, "prompt_id": p["voice"]["prompt_id"]})


def test_a_phone_checkout_copies_its_purchases_into_the_moss_memory(client, fake, monkeypatch):
    mirrored = []
    monkeypatch.setattr(purchase_memory, "mirror_payment", mirrored.append)
    fill_run1(client)
    body = confirm(client, "k1").json()
    assert mirrored == [body["payment_id"]]


def test_a_repeated_checkout_key_does_not_copy_again(client, fake, monkeypatch):
    mirrored = []
    monkeypatch.setattr(purchase_memory, "mirror_payment", mirrored.append)
    fill_run1(client)
    p = client.post("/v1/checkout/preview").json()
    body = {"idempotency_key": "k1", "prompt_id": p["voice"]["prompt_id"]}
    client.post("/v1/checkout/confirm", json=body)
    client.post("/v1/checkout/confirm", json=body)          # replayed: charged nothing new
    assert len(mirrored) == 1


def test_a_refused_checkout_copies_nothing(client, fake, monkeypatch):
    mirrored = []
    monkeypatch.setattr(purchase_memory, "mirror_payment", mirrored.append)
    assert confirm(client, "empty").status_code != 200 or mirrored == []
    assert mirrored == []


def test_a_demo_reset_empties_the_moss_memory_too(client, fake, monkeypatch):
    cleared = []
    monkeypatch.setattr(purchase_memory, "clear_in_background", lambda: cleared.append(True))
    assert client.post("/v1/demo/reset", json={"run": 1}).status_code == 200
    assert cleared == [True]
    client.post("/v1/demo/reset", json={"run": 3})            # a bad run is rejected before anything is cleared
    assert cleared == [True]


def test_the_phone_checkout_alerts_under_ten_dollars_like_the_agents(client, fake):
    from payments import checkout
    from agents.session import LOW_BALANCE_CENTS
    assert checkout.LOW_BALANCE_CENTS == LOW_BALANCE_CENTS == 1000
