"""HSA/FSA rules: FSA first for eligible items, and the claim tip for eligible items paid on Visa."""
from agents import payment_agent
from agents.intent import Entities, Intent
from tests.helpers import new_session

def with_fsa(balance=25000):
    s = new_session(fsa=True)
    next(c for c in s["cards"] if c["type"] == "fsa")["balance_cents"] = balance
    return s


def scan(name="Advil", cents=1299, label="eligible"):
    return {"scan_id": "s1", "state": "resolved",
            "product": {"product_key": "k", "name": name, "amount_cents": cents, "is_medication": True},
            "eligibility": {"label": label, "basis": "upc_match"}}


def confirm(s):
    return payment_agent.handle_intent(Intent(intent="confirm"), s)


def test_eligible_medicine_goes_on_fsa_before_hsa():
    f, s = payment_agent.recommend(with_fsa(), scan())
    assert s["pending"] == {"scope": "confirm_add", "card_id": "card_fsa_1"}
    assert "expires" in f.template and "FSA card" in f.template
    _, s = confirm(s)
    assert s["cart"][0]["assigned_card_id"] == "card_fsa_1"


def test_fsa_too_low_falls_back_to_hsa():
    f, s = payment_agent.recommend(with_fsa(balance=500), scan())
    assert s["pending"]["card_id"] == "card_hsa_1" and "expires" not in f.template


def test_only_hsa_behaves_as_before():
    f, s = payment_agent.recommend(new_session(), scan())
    assert s["pending"]["card_id"] == "card_hsa_1" and "FSA" not in f.template


def test_not_eligible_never_goes_on_fsa():
    _, s = payment_agent.recommend(with_fsa(), scan("Kettle Corn", 499, "not_eligible"))
    assert s["pending"]["card_id"] == "card_visa_1"


def test_user_can_still_name_the_hsa():
    _, s = payment_agent.recommend(with_fsa(), scan())
    _, s = payment_agent.handle_intent(Intent(intent="choose_card", entities=Entities(card="hsa")), s)
    assert s["cart"][0]["assigned_card_id"] == "card_hsa_1"


def checkout(s):
    _, s = payment_agent.handle_intent(Intent(intent="checkout"), s)
    return confirm(s)


def test_eligible_medicine_on_visa_gets_claim_tip_at_checkout():
    _, s = payment_agent.recommend(new_session(), scan())
    _, s = payment_agent.handle_intent(Intent(intent="choose_card", entities=Entities(card="visa")), s)
    f, _ = checkout(s)
    assert "file a claim" in f.template and "Optum Financial or HealthEquity" in f.template
    assert "$12.99 for Advil" in f.template and "receipt" in f.template
    assert "HSA provider" in f.template and f.fixed


def test_claim_tip_names_both_accounts_when_both_cards_exist():
    _, s = payment_agent.recommend(with_fsa(), scan())
    _, s = payment_agent.handle_intent(Intent(intent="choose_card", entities=Entities(card="visa")), s)
    f, _ = checkout(s)
    assert "FSA or HSA provider" in f.template


def test_no_claim_tip_for_non_eligible_items_or_health_card_purchases():
    _, s = payment_agent.recommend(new_session(), scan("Kettle Corn", 499, "not_eligible"))
    _, s = confirm(s)
    _, s2 = payment_agent.recommend(s, scan("Bandages", 549))
    _, s2 = confirm(s2)          # eligible, on the HSA
    f, _ = checkout(s2)
    assert "file a claim" not in f.template


# --- eligibility without barcodes: Claude Vision reads the product -------------------------

def product(category, medication=True):
    from models.schemas import ProductResolution
    return ProductResolution(product_key="k", name="x", category=category, is_medication=medication,
                             state="resolved", amount_cents=999)


def test_shelf_medicine_in_irs_category_is_eligible_without_a_barcode():
    from eligibility.classify import classify_eligibility
    for category in ("pain_relief", "cold_flu_allergy", "digestive_health", "otc_medicine"):
        r = classify_eligibility(product(category), None)
        assert r.label == "eligible" and r.basis == "irs_category_rule"


def test_medicine_outside_irs_categories_is_never_guessed():
    from eligibility.classify import classify_eligibility
    for category in ("vitamins_supplements", "other", "personal_care"):
        assert classify_eligibility(product(category), None).label == "could_not_confirm"


def test_non_medicine_follows_category_rules():
    from eligibility.classify import classify_eligibility
    assert classify_eligibility(product("grocery", medication=False), None).label == "not_eligible"
    assert classify_eligibility(product("first_aid", medication=False), None).label == "eligible"


def test_seed_has_fsa_card_and_run_two_declines_both_health_cards():
    from data import seed
    run2 = {c["id"]: c["balance_cents"] for c in seed.cards_for_run(2)}
    assert run2["card_fsa_1"] < 1848 and run2["card_hsa_1"] < 1848


def test_every_irs_category_has_a_source_and_unverified_rows_never_say_eligible():
    from eligibility.irs_rules import CATEGORY_SOURCES, IRS_CATEGORY_RULES
    assert CATEGORY_SOURCES.keys() == IRS_CATEGORY_RULES.keys()
    for cat, src in CATEGORY_SOURCES.items():
        assert src["url"].startswith("https://www.irs.gov/") and src["quote"]
        if src["status"] == "unverified":
            assert IRS_CATEGORY_RULES[cat] == "needs_review"


def test_rule_rows_fit_the_eligibility_table_and_skip_unknowns():
    from eligibility.irs_rules import IRS_CATEGORY_RULES, rule_rows
    rows = rule_rows("2026-10-24T00:00:00+00:00")
    assert {r["category_path"] for r in rows} == {c for c, v in IRS_CATEGORY_RULES.items() if v != "needs_review"}
    for r in rows:
        assert r["basis"] == "irs_category_rule" and isinstance(r["eligible"], bool)
        assert r["source_url"].startswith("https://www.irs.gov/") and r["product_key"].startswith("rule:")


# --- retailer cross-check (Apify catalog) --------------------------------------------------

def retailer(eligible, basis="retailer_badge"):
    return {"eligible": eligible, "basis": basis, "name": "Advil Ibuprofen 200mg", "collected_at": "2026-10-24"}


def with_row(monkeypatch, row):
    from eligibility import classify
    monkeypatch.setattr(classify, "_retailer_row", lambda p: row)
    return classify


def test_matching_retailer_listing_confirms_and_names_the_source(monkeypatch):
    c = with_row(monkeypatch, retailer(True))
    r = c.classify_eligibility(product("pain_relief"), None)
    assert r.label == "eligible" and r.basis == "retailer_match" and r.source == "retailer_index"


def test_retailer_disagreement_downgrades_to_could_not_confirm(monkeypatch):
    c = with_row(monkeypatch, retailer(False))
    r = c.classify_eligibility(product("pain_relief"), None)
    assert r.label == "could_not_confirm" and r.basis == "package_disagreement"


def test_retailer_never_upgrades_a_could_not_confirm(monkeypatch):
    c = with_row(monkeypatch, retailer(True))
    assert c.classify_eligibility(product("vitamins_supplements"), None).label == "could_not_confirm"


def test_no_listing_or_database_down_leaves_the_rule_answer(monkeypatch):
    c = with_row(monkeypatch, None)
    r = c.classify_eligibility(product("pain_relief"), None)
    assert r.label == "eligible" and r.basis == "irs_category_rule"
    monkeypatch.undo()
    assert c.classify_eligibility(product("pain_relief"), None).label == "eligible"   # offline: db raises, caught


def test_scrape_rows_use_actor_fields_and_the_vision_key():
    from lookup.normalize import normalize_key
    from prefetch.apify_run import normalize_scraped_data
    raw = [{"name": "Advil Ibuprofen 200mg", "brand": "Advil", "size": "200mg", "price": 12.99,
            "url": "https://fsastore.com/p/advil", "collection": "pain-relief"}] * 2
    rows = normalize_scraped_data(raw)
    assert len(rows) == 1 and rows[0]["product_key"] == normalize_key("Advil", "Advil Ibuprofen 200mg", "200mg")
    assert rows[0]["category_path"] == "pain_relief" and rows[0]["basis"] == "retailer_badge" and rows[0]["upc"] is None
