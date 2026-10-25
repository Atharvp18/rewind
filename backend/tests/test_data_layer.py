"""Tests for data/seed.py and data/db.py. No network: Supabase is replaced by a recording fake."""
import types

import httpx
import pytest
from postgrest.exceptions import APIError

from data import db, seed
from lookup.normalize import normalize_key


# --- a recording stand-in for the supabase client -------------------------------------------

class FakeQuery:
    def __init__(self, sb):
        self._sb = sb

    def __getattr__(self, name):
        def method(*args, **kwargs):
            self._sb.calls.append((name, args, kwargs))
            return self
        return method

    def execute(self):
        self._sb.calls.append(("execute", (), {}))
        outcome = self._sb.outcomes.pop(0) if self._sb.outcomes else self._sb.data
        if isinstance(outcome, Exception):
            raise outcome
        return types.SimpleNamespace(data=outcome)


class FakeSB:
    def __init__(self, data=None, outcomes=None):
        self.calls, self.data, self.outcomes = [], data, list(outcomes or [])

    def table(self, name):
        self.calls.append(("table", (name,), {}))
        return FakeQuery(self)

    def rpc(self, name, params):
        self.calls.append(("rpc", (name, params), {}))
        return FakeQuery(self)

    def names(self):
        return [c[0] for c in self.calls]


@pytest.fixture
def sb(monkeypatch):
    fake = FakeSB()
    monkeypatch.setattr(db, "_client", fake)
    return fake


# --- seed: the numbers the demo and the acceptance tests depend on --------------------------

def test_run_balances_and_money_are_integer_cents():
    run1 = {c["id"]: c["balance_cents"] for c in seed.cards_for_run(1)}
    run2 = {c["id"]: c["balance_cents"] for c in seed.cards_for_run(2)}
    assert run1 == {"card_hsa_1": 34000, "card_fsa_1": 2500, "card_visa_1": 500000}
    assert run2 == {"card_hsa_1": 500, "card_fsa_1": 1500, "card_visa_1": 500000}
    for card in seed.CARDS:
        assert type(card["balance_cents"]) is int
    for product in seed.DEMO_PRODUCTS:
        assert type(product["shelf_price_cents"]) is int


def test_demo_arithmetic_matches_the_script():
    prices = {p["normalized_name"]: p["shelf_price_cents"] for p in seed.DEMO_PRODUCTS}
    hsa_total = prices["Advil Ibuprofen 200mg"] + prices["Bandages"]
    assert hsa_total == 1848                       # "Two items totaling $18.48"
    assert 34000 - hsa_total == 32152              # "Your HSA balance is now $321.52"
    assert 1500 < hsa_total                        # run 2: the HSA cannot cover the group
    assert prices["Kettle Corn"] == 499


def test_cards_for_run_does_not_mutate_the_seed_and_rejects_bad_runs():
    seed.cards_for_run(2)
    assert [c["balance_cents"] for c in seed.CARDS] == [34000, 2500, 500000]
    for bad in (0, 4, None):
        with pytest.raises(ValueError):
            seed.cards_for_run(bad)


def test_demo_products_and_eligibility_rows_line_up_with_tiea_key_function():
    product_keys = [p["product_key"] for p in seed.DEMO_PRODUCTS]
    assert product_keys == [e["product_key"] for e in seed.DEMO_ELIGIBILITY]
    for p in seed.DEMO_PRODUCTS:   # no barcodes: keyed by brand|name|size
        assert p["upc"] is None
        assert p["product_key"] == normalize_key(p["brand"], p["normalized_name"], p["size"])
    labels = {e["name"]: e["eligible"] for e in seed.DEMO_ELIGIBILITY}
    assert labels == {"Advil Ibuprofen 200mg": True, "Bandages": True, "Kettle Corn": False}


def test_the_fsa_is_the_only_default_health_card_and_the_visa_is_not_a_default():
    defaults = [c["id"] for c in seed.CARDS if c["is_default"]]
    assert defaults == ["card_fsa_1"]
    assert {c["id"]: c["type"] for c in seed.CARDS} == {
        "card_hsa_1": "hsa", "card_fsa_1": "fsa", "card_visa_1": "general"}


def test_reset_payload_is_deterministic_and_has_two_insurers():
    assert seed.reset_payload(1) == seed.reset_payload(1)
    assert seed.reset_payload(1) != seed.reset_payload(2)
    assert [i["id"] for i in seed.INSURERS] == ["mock_plan_a", "mock_plan_b"]


# --- db: budget, retry, and error rules ------------------------------------------------------

def test_transport_error_is_retried_once_then_succeeds(sb):
    sb.outcomes = [httpx.ConnectTimeout("slow"), [{"id": "card_hsa_1"}]]
    assert db.get_cards() == [{"id": "card_hsa_1"}]


def test_two_transport_errors_become_db_unavailable(sb):
    sb.outcomes = [httpx.ConnectTimeout("a"), httpx.ConnectTimeout("b")]
    with pytest.raises(db.DBUnavailable):
        db.get_cards()


def test_database_errors_are_not_retried_or_called_an_outage(sb):
    sb.outcomes = [APIError({"message": "duplicate key", "code": "23505"})]
    with pytest.raises(APIError):
        db.get_cards()
    assert sb.names().count("execute") == 1


def test_missing_credentials_raise_db_unavailable(monkeypatch):
    monkeypatch.setattr(db, "_client", None)
    monkeypatch.setattr(db, "load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    with pytest.raises(db.DBUnavailable):
        db.get_cards()


def test_health_never_raises(monkeypatch):
    monkeypatch.setattr(db, "_client", None)
    monkeypatch.setattr(db, "load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    result = db.health()
    assert result["reachable"] is False and "latency_ms" in result


# --- db: money is never a float -------------------------------------------------------------

@pytest.mark.parametrize("bad", [12.99, "1299", True, None])
def test_cart_rejects_non_integer_cents(sb, bad):
    with pytest.raises(TypeError):
        db.add_cart_item("scan1", "upc:1", "Advil", bad, "shelf_price", "card_hsa_1", "eligible")
    assert "execute" not in sb.names()


def test_cache_put_rejects_a_float_price(sb):
    with pytest.raises(TypeError):
        db.cache_put("upc:1", {"normalized_name": "x", "category": "other", "source": "shelf_tag",
                               "shelf_price_cents": 12.99})


# --- db: the helpers Tiea's modules call ----------------------------------------------------

def test_cache_put_sets_key_and_a_fresh_timestamp_and_drops_unknown_fields(sb):
    db.cache_put("upc:1", {"normalized_name": "Advil", "category": "pain_relief",
                           "source": "shelf_tag", "shelf_price_cents": 1299, "bogus": "x"})
    upsert = next(c for c in sb.calls if c[0] == "upsert")
    record = upsert[1][0]
    assert record["product_key"] == "upc:1" and record["shelf_price_cents"] == 1299
    assert "bogus" not in record and record["last_updated"]
    assert upsert[2] == {"on_conflict": "product_key"}


def test_cache_get_returns_row_or_none(sb):
    sb.data = [{"product_key": "upc:1", "normalized_name": "Advil"}]
    assert db.cache_get("upc:1")["normalized_name"] == "Advil"
    sb.data = []
    assert db.cache_get("upc:2") is None


def test_eligibility_lookup_upc_cleans_digits_and_skips_empty(sb):
    sb.data = [{"upc": "000000000001", "eligible": True}]
    assert db.eligibility_lookup_upc("0000-0000-0001")["eligible"] is True
    eq = next(c for c in sb.calls if c[0] == "eq")
    assert eq[1] == ("upc", "000000000001")
    sb.calls.clear()
    assert db.eligibility_lookup_upc("not a upc") is None
    assert sb.calls == []                           # no query for an empty key


def test_bulk_insert_dedupes_chunks_and_counts(sb):
    rows = [{"product_key": f"upc:{i}", "name": "n", "eligible": True, "source_url": "u",
             "collected_at": "2026-10-24T00:00:00+00:00", "basis": "retailer_badge", "junk": 1}
            for i in range(1200)]
    rows.append(dict(rows[0], name="newer"))        # duplicate key inside the batch
    assert db.eligibility_bulk_insert(rows) == 1200
    upserts = [c for c in sb.calls if c[0] == "upsert"]
    assert [len(c[1][0]) for c in upserts] == [500, 500, 200]
    assert all("junk" not in r for c in upserts for r in c[1][0])
    first = upserts[0][1][0][0]
    assert first["name"] == "newer"                 # the later duplicate wins


def test_bulk_insert_rejects_a_row_without_a_key(sb):
    with pytest.raises(ValueError):
        db.eligibility_bulk_insert([{"name": "no key"}])


# --- db: prompts, checkout, reset ------------------------------------------------------------

def test_consume_prompt_raises_when_the_function_returns_nothing(sb):
    sb.data = None
    with pytest.raises(db.PromptExpired):
        db.consume_prompt("p1", "confirm_add")


def test_consume_prompt_returns_the_payload(sb):
    sb.data = {"prompt_id": "p1", "scope": "confirm_add", "scan_id": "s1", "payload": {"a": 1}}
    assert db.consume_prompt("p1", "confirm_add")["payload"] == {"a": 1}


def test_create_prompt_passes_the_ttl_to_postgres(sb):
    prompt_id = db.create_prompt("confirm_add", "s1", {"x": 1})
    rpc = next(c for c in sb.calls if c[0] == "rpc")
    assert rpc[1][0] == "create_prompt" and rpc[1][1]["p_ttl_seconds"] == 15
    assert rpc[1][1]["p_prompt_id"] == prompt_id


def test_checkout_maps_database_codes_to_checkout_failed(sb):
    sb.outcomes = [APIError({"message": "E_CARD_CANNOT_PAY: card_hsa_1"})]
    with pytest.raises(db.CheckoutFailed) as err:
        db.confirm_checkout("key1", [{"card_id": "card_hsa_1", "amount_cents": 1848}])
    assert err.value.code == "E_CARD_CANNOT_PAY"


def test_checkout_does_not_swallow_unrelated_database_errors(sb):
    sb.outcomes = [APIError({"message": "permission denied"})]
    with pytest.raises(APIError):
        db.confirm_checkout("key1", [{"card_id": "c", "amount_cents": 1}])


def test_checkout_rejects_a_float_amount_before_calling_the_database(sb):
    with pytest.raises(TypeError):
        db.confirm_checkout("key1", [{"card_id": "card_hsa_1", "amount_cents": 18.48}])
    assert sb.calls == []


def test_reset_demo_sends_the_seed_and_returns_cards_and_empty_cart(sb):
    sb.outcomes = [{"cards": [{"id": "card_hsa_1", "balance_cents": 500}]},   # rpc
                   [],                                                           # FSA demo last 4 digits
                   [{"id": "card_hsa_1", "nickname": "HSA card"}],              # cards
                   [],                                                           # cart_items
                   [{"id": "card_hsa_1", "nickname": "HSA card"}]]               # cards, for the cart
    result = db.reset_demo(2)
    rpc = next(c for c in sb.calls if c[0] == "rpc")
    assert rpc[1][0] == "reset_demo" and rpc[1][1]["p_run"] == 2
    assert next(c for c in rpc[1][1]["p_cards"] if c["id"] == "card_hsa_1")["balance_cents"] == 500
    assert result["cart"] == {"groups": [], "total_cents": 0}
    update = next(c for c in sb.calls if c[0] == "update")      # the FSA card's demo last 4 digits
    assert update[1][0] == {"last4": "4417", "network": "visa"}


def test_get_cart_groups_by_card_with_subtotals(sb):
    items = [{"id": "a", "assigned_card_id": "card_hsa_1", "amount_cents": 1299},
             {"id": "b", "assigned_card_id": "card_hsa_1", "amount_cents": 549},
             {"id": "c", "assigned_card_id": "card_visa_1", "amount_cents": 499}]
    cards = [{"id": "card_hsa_1", "nickname": "HSA card"},
             {"id": "card_visa_1", "nickname": "Visa credit"}]
    sb.outcomes = [items, cards]
    cart = db.get_cart()
    assert [(g["card_id"], g["subtotal_cents"]) for g in cart["groups"]] == [
        ("card_hsa_1", 1848), ("card_visa_1", 499)]
    assert cart["total_cents"] == 2347


# --- additions for the Fetch.ai payment agent (agents/store.py) ----------------------------

def test_add_cart_item_keeps_a_caller_supplied_id(sb):
    sb.data = []                                    # the cart read after the insert
    db.add_cart_item("scan1", "upc:1", "Advil", 1299, "shelf_price", "card_hsa_1", "eligible",
                     item_id="item-abc")
    insert = next(c for c in sb.calls if c[0] == "insert")
    assert insert[1][0]["id"] == "item-abc"


def test_reassign_cart_item_moves_one_row_and_marks_override(sb):
    db.reassign_cart_item("item-abc", "card_visa_1")
    update = next(c for c in sb.calls if c[0] == "update")
    assert update[1][0] == {"assigned_card_id": "card_visa_1", "user_overrode_card": True}
    assert ("eq", ("id", "item-abc"), {}) in sb.calls


def test_reset_clears_scan_saved_prices_but_keeps_seeded_products():
    from pathlib import Path
    sql = (Path(db.__file__).parent / "functions.sql").read_text()
    reset = sql[sql.index("CREATE OR REPLACE FUNCTION reset_demo"):]
    assert "DELETE FROM product_cache WHERE source NOT IN ('seeded', 'web_search');" in reset
    assert all(p["source"] == "seeded" for p in seed.DEMO_PRODUCTS)


# --- additions for the Fetch.ai payment agent (agents/store.py) ----------------------------

def test_add_cart_item_keeps_a_caller_supplied_id(sb):
    sb.data = []                                    # the cart read after the insert
    db.add_cart_item("scan1", "upc:1", "Advil", 1299, "shelf_price", "card_hsa_1", "eligible",
                     item_id="item-abc")
    insert = next(c for c in sb.calls if c[0] == "insert")
    assert insert[1][0]["id"] == "item-abc"


def test_reassign_cart_item_moves_one_row_and_marks_override(sb):
    db.reassign_cart_item("item-abc", "card_visa_1")
    update = next(c for c in sb.calls if c[0] == "update")
    assert update[1][0] == {"assigned_card_id": "card_visa_1", "user_overrode_card": True}
    assert ("eq", ("id", "item-abc"), {}) in sb.calls


def test_reset_clears_scan_saved_prices_but_keeps_seeded_products():
    from pathlib import Path
    sql = (Path(db.__file__).parent / "functions.sql").read_text()
    reset = sql[sql.index("CREATE OR REPLACE FUNCTION reset_demo"):]
    assert "DELETE FROM product_cache WHERE source NOT IN ('seeded', 'web_search');" in reset
    assert all(p["source"] == "seeded" for p in seed.DEMO_PRODUCTS)


# --- purchase history ------------------------------------------------------------------------

def sql(name):
    from pathlib import Path
    return (Path(db.__file__).parent / name).read_text()


def test_get_purchases_filters_by_date_and_card_type_newest_first(sb):
    sb.data = [{"id": "a"}]
    assert db.get_purchases("2026-10-01T00:00:00Z", "2026-11-01T00:00:00Z", "fsa") == [{"id": "a"}]
    names = [c[0] for c in sb.calls]
    assert ("gte", ("purchased_at", "2026-10-01T00:00:00Z"), {}) in sb.calls
    assert ("lt", ("purchased_at", "2026-11-01T00:00:00Z"), {}) in sb.calls
    assert ("eq", ("card_type", "fsa"), {}) in sb.calls
    assert ("order", ("purchased_at",), {"desc": True}) in sb.calls


def test_checkout_copies_the_cart_into_purchase_items_before_emptying_it():
    f = sql("functions.sql")
    body = f[f.index("CREATE OR REPLACE FUNCTION confirm_checkout"):f.index("CREATE OR REPLACE FUNCTION reset_demo")]
    assert body.index("INSERT INTO purchase_items") < body.index("DELETE FROM cart_items WHERE TRUE")
    assert "JOIN cards c ON c.id = ci.assigned_card_id" in body


def test_reset_clears_purchases_before_payments_because_of_the_foreign_key():
    f = sql("functions.sql")
    reset = f[f.index("CREATE OR REPLACE FUNCTION reset_demo"):]
    assert reset.index("DELETE FROM purchase_items") < reset.index("DELETE FROM payments")


def test_migration_file_holds_the_table_and_both_changed_functions():
    m = sql("migration_purchase_items.sql")
    assert "CREATE TABLE IF NOT EXISTS purchase_items" in m
    assert "CREATE OR REPLACE FUNCTION confirm_checkout" in m and "CREATE OR REPLACE FUNCTION reset_demo" in m
    assert "INSERT INTO purchase_items" in m and "DELETE FROM purchase_items" in m
    schema = sql("schema.sql")
    for col in ("payment_id", "purchased_at", "amount_cents", "card_type", "user_overrode_card"):
        assert col in m and col in schema


def test_purchase_items_keeps_category_and_medicine_flag_and_skips_prescriptions():
    f = sql("functions.sql")
    body = f[f.index("CREATE OR REPLACE FUNCTION confirm_checkout"):f.index("CREATE OR REPLACE FUNCTION reset_demo")]
    assert "s.product_json->>'category'" in body and "is_medication" in body
    assert "LEFT JOIN scans s ON s.scan_id = ci.scan_id" in body
    assert "WHERE ci.product_key <> 'prescription'" in body        # History is over-the-counter only
    m = sql("migration_purchase_items.sql")
    assert "ADD COLUMN IF NOT EXISTS category" in m and "ADD COLUMN IF NOT EXISTS is_medication" in m
    assert "category" in sql("schema.sql") and "is_medication" in sql("schema.sql")


def test_checkout_keeps_the_paid_items_with_the_split_for_the_invoice(sb):
    sb.outcomes = [{"payment_id": "p"}]
    item = {"id": "i1", "seq": 1, "display_name": "Advil", "amount_cents": 1299}
    db.confirm_checkout("key1", [{"card_id": "card_hsa_1", "amount_cents": 1299, "items": [item]}])
    rpc = next(c for c in sb.calls if c[0] == "rpc")
    assert rpc[1][1]["p_splits"] == [{"card_id": "card_hsa_1", "amount_cents": 1299, "items": [item]}]


def test_checkout_rejects_a_float_item_price(sb):
    with pytest.raises(TypeError):
        db.confirm_checkout("key1", [{"card_id": "c", "amount_cents": 1299,
                                      "items": [{"display_name": "x", "amount_cents": 12.99}]}])
    assert sb.calls == []
