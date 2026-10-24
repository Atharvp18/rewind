"""Tests for payments/nessie.py. The Nessie API is replaced by httpx.MockTransport."""
import asyncio
import logging
import time

import httpx
import pytest

from payments import nessie

KEY = "secret-nessie-key-123"
HSA_ACCOUNT, VISA_ACCOUNT = "acc-hsa", "acc-visa"


def account_json(account_id, balance, nickname="x", type_="Checking"):
    return {"_id": account_id, "type": type_, "nickname": nickname, "rewards": 0, "balance": balance,
            "account_number": "0" * 16, "customer_id": "cust"}


class FakeNessie:
    """Serves GET /accounts/{id}. `responses` maps an account id to a dict, an int status, an
    exception, or a (delay_seconds, one of those)."""

    def __init__(self, responses):
        self.responses, self.requests = responses, []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        outcome = self.responses[request.url.path.rsplit("/", 1)[-1]]
        if isinstance(outcome, tuple):
            await asyncio.sleep(outcome[0])
            outcome = outcome[1]
        if isinstance(outcome, Exception):
            raise outcome
        if isinstance(outcome, int):
            return httpx.Response(outcome, text="nope")
        return httpx.Response(200, json=outcome)


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("NESSIE_API_KEY", KEY)
    monkeypatch.delenv("NESSIE_BASE_URL", raising=False)
    monkeypatch.delenv("REWIND_DEMO_MODE", raising=False)
    nessie._last_known.clear()
    yield monkeypatch
    nessie._last_known.clear()


def serve(env, responses):
    fake = FakeNessie(responses)
    env.setattr(nessie, "_transport", httpx.MockTransport(fake))
    return fake


def cards(hsa_balance=34000, visa_balance=500000, linked=True):
    return [
        {"id": "card_hsa_1", "type": "hsa", "nickname": "HSA card", "balance_cents": hsa_balance,
         "nessie_account_id": HSA_ACCOUNT if linked else None},
        {"id": "card_visa_1", "type": "general", "nickname": "Visa credit", "balance_cents": visa_balance,
         "nessie_account_id": VISA_ACCOUNT if linked else None},
    ]


def by_id(report):
    return {c["id"]: c for c in report.cards}


# --- fetch_account --------------------------------------------------------------------------

async def fetch(account_id="acc-hsa"):
    async with httpx.AsyncClient(transport=nessie._transport) as client:
        return await nessie.fetch_account(account_id, client)


async def test_fetch_account_reads_the_balance_and_sends_the_key_as_a_query_parameter(env):
    fake = serve(env, {"acc-hsa": account_json("acc-hsa", 34000, "HSA card")})
    account = await fetch()
    assert (account.id, account.nickname, account.type, account.balance_cents) == (
        "acc-hsa", "HSA card", "Checking", 34000)
    request = fake.requests[0]
    assert str(request.url).startswith("https://prod-api.nessieisreal.com/accounts/acc-hsa")
    assert request.url.params["key"] == KEY


async def test_the_base_url_can_be_overridden(env):
    fake = serve(env, {"acc-hsa": account_json("acc-hsa", 1)})
    env.setenv("NESSIE_BASE_URL", "https://api.nessieisreal.com/")
    await fetch()
    assert str(fake.requests[0].url).startswith("https://api.nessieisreal.com/accounts/acc-hsa?")


@pytest.mark.parametrize("outcome", [401, 404, 500, httpx.ConnectTimeout("t"), httpx.ConnectError("c"),
                                     {"unexpected": "shape"}, account_json("a", 12.5), account_json("a", "340"),
                                     account_json("a", True)])
async def test_any_failure_is_nessie_unavailable_and_never_leaks_the_key(env, outcome):
    serve(env, {"acc-hsa": outcome})
    with pytest.raises(nessie.NessieUnavailable) as err:
        await fetch()
    assert KEY not in str(err.value)


async def test_a_missing_key_is_nessie_unavailable_without_a_request(env):
    fake = serve(env, {"acc-hsa": account_json("acc-hsa", 1)})
    env.delenv("NESSIE_API_KEY")
    with pytest.raises(nessie.NessieUnavailable):
        await fetch()
    assert fake.requests == []


# --- get_balances_or_last_known ------------------------------------------------------------------

async def test_linked_cards_take_the_nessie_balance_and_unlinked_cards_keep_their_own(env):
    serve(env, {"acc-hsa": account_json("acc-hsa", 34000), "acc-visa": account_json("acc-visa", 499000)})
    report = await nessie.get_balances_or_last_known(cards(hsa_balance=1, visa_balance=2))
    assert report.degraded is False and report.warnings == []
    assert [(c["balance_cents"], c["balance_source"]) for c in report.cards] == [(34000, "nessie"), (499000, "nessie")]
    unlinked = await nessie.get_balances_or_last_known(cards(hsa_balance=15, linked=False))
    assert [(c["balance_cents"], c["balance_source"]) for c in unlinked.cards][0] == (15, "seeded")
    assert unlinked.degraded is False


async def test_no_linked_cards_means_no_request(env):
    fake = serve(env, {})
    await nessie.get_balances_or_last_known(cards(linked=False))
    assert fake.requests == []


async def test_input_cards_are_not_modified(env):
    serve(env, {"acc-hsa": account_json("acc-hsa", 34000), "acc-visa": account_json("acc-visa", 499000)})
    original = cards(hsa_balance=1)
    await nessie.get_balances_or_last_known(original)
    assert original == cards(hsa_balance=1) and "balance_source" not in original[0]


async def test_a_failure_falls_back_to_the_last_known_balance_and_warns(env):
    serve(env, {"acc-hsa": account_json("acc-hsa", 34000), "acc-visa": account_json("acc-visa", 499000)})
    await nessie.get_balances_or_last_known(cards())                   # remembers 34000 / 499000
    serve(env, {"acc-hsa": httpx.ConnectTimeout("down"), "acc-visa": 503})
    report = await nessie.get_balances_or_last_known(cards(hsa_balance=1, visa_balance=2))
    assert report.degraded is True and report.warnings == ["E_NESSIE_UNAVAILABLE"]
    assert [(c["balance_cents"], c["balance_source"]) for c in report.cards] == [
        (34000, "last_known"), (499000, "last_known")]


async def test_one_card_failing_degrades_only_that_card(env):
    serve(env, {"acc-hsa": account_json("acc-hsa", 34000), "acc-visa": 500})
    env.setenv("REWIND_DEMO_MODE", "true")
    report = await nessie.get_balances_or_last_known(cards(visa_balance=777))
    sources = {c["id"]: (c["balance_cents"], c["balance_source"]) for c in report.cards}
    assert sources == {"card_hsa_1": (34000, "nessie"), "card_visa_1": (777, "seeded")}
    assert report.degraded is True


async def test_in_demo_mode_nothing_known_falls_back_to_seeded_balances(env):
    serve(env, {"acc-hsa": 500, "acc-visa": 500})
    env.setenv("REWIND_DEMO_MODE", "true")
    report = await nessie.get_balances_or_last_known(cards(hsa_balance=1500))
    assert [(c["balance_cents"], c["balance_source"]) for c in report.cards] == [
        (1500, "seeded"), (500000, "seeded")]
    assert report.degraded is True


async def test_outside_demo_mode_nothing_known_is_an_error(env):
    serve(env, {"acc-hsa": 500, "acc-visa": 500})
    with pytest.raises(nessie.NessieUnavailable) as err:
        await nessie.get_balances_or_last_known(cards())
    assert KEY not in str(err.value)


async def test_cards_are_read_in_parallel(env):
    serve(env, {"acc-hsa": (0.3, account_json("acc-hsa", 1)), "acc-visa": (0.3, account_json("acc-visa", 2))})
    t0 = time.perf_counter()
    report = await nessie.get_balances_or_last_known(cards())
    assert time.perf_counter() - t0 < 0.55 and report.degraded is False


async def test_the_whole_read_stays_inside_the_budget(env):
    env.setattr(nessie, "BUDGET_S", 0.1)
    env.setenv("REWIND_DEMO_MODE", "true")
    serve(env, {"acc-hsa": (2.0, account_json("acc-hsa", 1)), "acc-visa": account_json("acc-visa", 499000)})
    t0 = time.perf_counter()
    report = await nessie.get_balances_or_last_known(cards(hsa_balance=15))
    assert time.perf_counter() - t0 < 0.5
    assert {c["id"]: c["balance_source"] for c in report.cards} == {"card_hsa_1": "seeded", "card_visa_1": "nessie"}
    assert report.degraded is True


async def test_the_key_never_reaches_the_logs(env, caplog):
    caplog.set_level(logging.DEBUG)
    serve(env, {"acc-hsa": account_json("acc-hsa", 34000), "acc-visa": 503})
    env.setenv("REWIND_DEMO_MODE", "true")
    await nessie.get_balances_or_last_known(cards())
    assert KEY not in caplog.text


# --- wiring ------------------------------------------------------------------------------------------

def test_a_nessie_failure_surfaces_as_a_retryable_envelope_error(env):
    from fastapi.testclient import TestClient
    from main import create_app

    app = create_app()

    @app.get("/boom/nessie")
    def boom():
        raise nessie.NessieUnavailable("HTTP 503")

    response = TestClient(app, raise_server_exceptions=False).get("/boom/nessie")
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "E_NESSIE_UNAVAILABLE" and error["retryable"] is True and error["speech"]


def test_seed_links_the_cards_to_nessie_accounts_from_the_environment(monkeypatch):
    from data import seed

    monkeypatch.delenv("NESSIE_HSA_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("NESSIE_VISA_ACCOUNT_ID", raising=False)
    assert [c["nessie_account_id"] for c in seed.cards_for_run(1)] == [None, None]
    monkeypatch.setenv("NESSIE_HSA_ACCOUNT_ID", "acc-hsa")
    monkeypatch.setenv("NESSIE_VISA_ACCOUNT_ID", "acc-visa")
    linked = {c["id"]: c["nessie_account_id"] for c in seed.cards_for_run(2)}
    assert linked == {"card_hsa_1": "acc-hsa", "card_visa_1": "acc-visa"}
