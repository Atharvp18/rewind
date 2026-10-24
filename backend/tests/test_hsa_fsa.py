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


# --- retailer cross-check (Apify catalog, searched with Moss) -----------------------------

def listing(eligible, price_cents=None):
    return {"eligible": eligible, "name": "Advil Ibuprofen 200mg", "collected_at": "2026-10-24",
            "score": 0.9, "price_cents": price_cents}


def classify(category, retailer):
    from eligibility.classify import classify_eligibility
    return classify_eligibility(product(category), None, retailer)


def test_matching_listing_confirms_and_names_the_source():
    r = classify("pain_relief", listing(True))
    assert r.label == "eligible" and r.basis == "semantic_match" and r.source == "retailer_index"
    assert r.confidence == 0.9 and r.matched_name == "Advil Ibuprofen 200mg"


def test_disagreeing_listing_downgrades_to_could_not_confirm():
    r = classify("pain_relief", listing(False))
    assert r.label == "could_not_confirm" and r.basis == "package_disagreement"


def test_listing_never_upgrades_a_could_not_confirm():
    assert classify("vitamins_supplements", listing(True)).label == "could_not_confirm"


def test_no_listing_but_index_not_consulted_leaves_the_rule_answer():
    r = classify("pain_relief", None)
    assert r.label == "eligible" and r.basis == "irs_category_rule"


def test_index_answered_but_product_not_listed_is_could_not_confirm():
    from eligibility.classify import classify_eligibility
    r = classify_eligibility(product("pain_relief"), None, None, index_checked=True)
    assert r.label == "could_not_confirm" and r.basis == "no_match"


def test_not_listed_does_not_change_a_not_eligible_answer():
    from eligibility.classify import classify_eligibility
    r = classify_eligibility(product("grocery", medication=False), None, None, index_checked=True)
    assert r.label == "not_eligible"


# --- the Moss module, with a fake index -----------------------------------------------------

class FakeMoss:
    def __init__(self, docs): self.docs, self.queries = docs, []
    async def load_index(self, name): pass
    async def query(self, name, text, options):
        import types
        self.queries.append((text, options.min_score, options.top_k))
        return types.SimpleNamespace(docs=self.docs)


def doc(text, eligible="true", score=0.9, brand=""):
    import types
    return types.SimpleNamespace(text=text, score=score, metadata={
        "eligible": eligible, "name": text, "collected_at": "2026-10-24", "brand": brand})


async def match(monkeypatch, docs, name="Advil Ibuprofen Tablets", size="200mg", brand="Advil"):
    from lookup import moss_index
    from models.schemas import ProductResolution
    monkeypatch.setenv("MOSS_PROJECT_ID", "p")
    fake = FakeMoss(docs)
    monkeypatch.setattr(moss_index, "_client", fake)
    monkeypatch.setattr(moss_index, "_loaded", False)
    p = ProductResolution(product_key="k", name=name, brand=brand, size=size, category="pain_relief")
    return await moss_index.find_match(p), fake


async def test_find_match_returns_the_best_listing_and_asks_with_the_spec_threshold(monkeypatch):
    got, fake = await match(monkeypatch, [doc("Advil Ibuprofen 200mg", score=0.8), doc("Motrin 200mg", score=0.95)])
    assert got["name"] == "Motrin 200mg" and got["score"] == 0.95 and got["eligible"] is True
    import pytest
    assert fake.queries[0][1] == pytest.approx(0.4) and fake.queries[0][2] == 3 and "Advil" in fake.queries[0][0]


async def test_strength_and_pack_size_do_not_affect_the_match(monkeypatch):
    got, fake = await match(monkeypatch, [doc("Allegra 24 Hour Allergy Relief 90 ct")], name="Allegra", size="180mg", brand="Allegra")
    assert got["eligible"] is True and "180" not in fake.queries[0][0]     # the query leaves size out


async def test_brand_alone_is_enough_at_the_lower_floor_but_a_different_brand_is_not(monkeypatch):
    allegra = doc("Allegra 24-Hour Indoor & Outdoor Allergy Relief", score=0.50, brand="Allegra")
    got, _ = await match(monkeypatch, [allegra], name="Allegra", size=None, brand=None)
    assert got is not None and got["score"] == 0.50                 # same brand, 0.50 >= 0.40
    tylenol = doc("Tylenol Extra Strength Caplets", score=0.67, brand="Tylenol")
    got, _ = await match(monkeypatch, [tylenol], name="Advil Ibuprofen", size=None, brand="Advil")
    assert got is None                                              # 0.67 < 0.75 and another brand
    weak = doc("Allegra Hives", score=0.35, brand="Allegra")
    got, _ = await match(monkeypatch, [weak], name="Allegra", size=None, brand="Allegra")
    assert got is None                                              # below even the brand floor


async def test_the_listed_price_comes_back_in_cents(monkeypatch):
    d = doc("Allegra 24 Hour"); d.metadata["price_cents"] = "4299"
    got, _ = await match(monkeypatch, [d], name="Allegra", size=None, brand="Allegra")
    assert got["price_cents"] == 4299


async def test_not_listed_is_none_but_moss_down_raises(monkeypatch):
    import pytest
    from lookup import moss_index
    from models.schemas import ProductResolution
    got, _ = await match(monkeypatch, [])
    assert got is None                                   # answered: not in the index
    p = ProductResolution(product_key="k", name="x", category="other")
    monkeypatch.delenv("MOSS_PROJECT_ID")
    with pytest.raises(moss_index.MossUnavailable):      # could not answer: not the same thing
        await moss_index.find_match(p)


async def test_not_eligible_listing_reads_as_false(monkeypatch):
    got, _ = await match(monkeypatch, [doc("Kettle Corn", eligible="false")], name="Kettle Corn", size=None, brand=None)
    assert got["eligible"] is False


def test_scrape_rows_use_the_ecommerce_tool_shape_and_the_vision_key():
    from lookup.normalize import normalize_key
    from prefetch.apify_run import normalize_scraped_data
    raw = [
        {"name": "Excedrin Tension Headache Caplets, Aspirin-Free, 100 ct.", "brand": {"slogan": "Excedrin"},
         "offers": {"price": "15.99", "priceCurrency": "USD"},
         "url": "https://fsastore.com/excedrin/42810.html", "collection": "pain-relief"},
        {"name": "Preparation H Hemorrhoidal Cream Original, 0.9 oz.", "brand": {"slogan": "FSA Store"},
         "url": "https://fsastore.com/prep-h/42814.html", "collection": "first-aid"},
    ]
    rows = normalize_scraped_data(raw + raw[:1])             # a duplicate is dropped
    assert len(rows) == 2
    assert rows[0]["product_key"] == normalize_key("Excedrin", raw[0]["name"], None)
    assert rows[0]["category_path"] == "pain_relief" and rows[0]["basis"] == "retailer_badge"
    assert rows[0]["upc"] is None and rows[0]["source_url"].startswith("https://fsastore.com/")
    assert rows[1]["brand"] is None                           # the store's own label is not a brand


# --- price: shelf tag first, the store's listed price as the fallback -----------------------

async def pipeline(monkeypatch, retailer, price_cents=None):
    from agents import product_agent
    from lookup import moss_index
    from models.schemas import VisionExtract

    async def fake_find(product):
        return retailer
    monkeypatch.setattr(moss_index, "find_match", fake_find)
    extract = VisionExtract(name="Allegra 24 Hour Allergy Relief", brand="Allegra", category="cold_flu_allergy",
                            is_medication=True, shelf_price_cents=price_cents)
    return await product_agent._pipeline(extract)


async def test_missing_shelf_price_falls_back_to_the_stores_listed_price(monkeypatch):
    product_, elig = await pipeline(monkeypatch, listing(True, price_cents=4299))
    assert product_.amount_cents == 4299 and product_.price_source == "seeded" and product_.state == "resolved"
    assert "E_NO_PRICE" not in product_.warnings and elig.label == "eligible"


async def test_a_shelf_tag_price_always_beats_the_listing(monkeypatch):
    product_, _ = await pipeline(monkeypatch, listing(True, price_cents=4299), price_cents=3999)
    assert product_.amount_cents == 3999 and product_.price_source == "shelf_tag"


async def test_no_listing_means_no_price_is_invented(monkeypatch):
    product_, _ = await pipeline(monkeypatch, None)
    assert product_.amount_cents is None and product_.state == "partial"


def test_a_fallback_price_is_spoken_as_listed_online():
    from agents.intent import Intent
    s = new_session()
    sc = scan("Allegra", 4299)
    sc["product"]["price_source"] = "seeded"
    f, _ = payment_agent.recommend(s, sc)
    assert "listed online at $42.99" in f.template
    sc["product"]["price_source"] = "shelf_tag"
    f, _ = payment_agent.recommend(s, sc)
    assert "listed online" not in f.template and "$42.99" in f.template


def test_catalog_is_fixed_and_rows_do_not_pile_up(tmp_path):
    from prefetch import apify_run as job
    url = next(iter(job.CATALOG))
    raw = [{"name": "Tylenol Extra Strength", "brand": {"slogan": "Tylenol"}, "inputUrl": url,
            "offers": {"price": "15.99"}, "url": url}]
    first = job.normalize_scraped_data(raw)
    assert first[0]["category_path"] == job.CATEGORY_MAP[job.CATALOG[url]] and first[0]["price_cents"] == 1599
    # saved rows outside the catalog are dropped; rows for catalog pages are kept
    import json
    saved = tmp_path / "rows.json"
    saved.write_text(json.dumps(first + [{**first[0], "product_key": "n:old", "source_url": "https://fsastore.com/random.html"}]))
    kept = job.load_saved_rows(saved)
    assert [r["product_key"] for r in kept] == [first[0]["product_key"]]
    assert len(job.CATALOG) == len(set(job.CATALOG))


def test_a_page_read_with_a_different_brand_replaces_its_old_row(tmp_path):
    import json
    from prefetch import apify_run as job
    url = next(iter(job.CATALOG))
    old = job.normalize_scraped_data([{"name": "Preparation H", "brand": {"slogan": "FSA Store"}, "inputUrl": url}])
    new = job.normalize_scraped_data([{"name": "Preparation H", "brand": {"slogan": "Preparation H"}, "inputUrl": url}])
    assert old[0]["product_key"] != new[0]["product_key"] and old[0]["source_url"] == new[0]["source_url"] == url
    merged = {r["source_url"]: r for r in old}
    merged.update({r["source_url"]: r for r in new})
    assert list(merged.values()) == new


# --- an item we cannot confirm: say so and suggest the Visa -----------------------------------

def unconfirmed(session=None):
    return payment_agent.recommend(session or new_session(), scan("Excedrin Migraine", 1299, "could_not_confirm"))


def test_unconfirmed_item_is_said_plainly_and_the_visa_is_suggested():
    f, s = unconfirmed()
    assert "I could not confirm eligibility" in f.template and "won't put it on your HSA or FSA by myself" in f.template
    assert "If you need it right away, your Visa credit will work" in f.template
    assert f.template.endswith("Want me to add it to your Visa credit?")
    assert s["pending"]["suggested"] == "card_visa_1" and s["pending"]["scope"] == "choose_card"


def test_yes_puts_an_unconfirmed_item_on_the_visa_and_no_skips_it():
    _, s = unconfirmed()
    _, s2 = confirm(s)
    assert s2["cart"][0]["assigned_card_id"] == "card_visa_1" and s2["cart"][0]["eligibility_label"] == "could_not_confirm"
    _, s3 = payment_agent.handle_intent(Intent(intent="deny"), s)
    assert s3["cart"] == [] and s3["pending"] is None


def test_the_shopper_can_still_name_another_card_for_an_unconfirmed_item():
    _, s = unconfirmed()
    _, s2 = payment_agent.handle_intent(Intent(intent="choose_card", entities=Entities(card="hsa")), s)
    assert s2["cart"][0]["assigned_card_id"] == "card_hsa_1"       # their choice; we never do it on our own


def test_with_no_visa_it_still_asks_which_card():
    s = new_session()
    s["cards"] = [c for c in s["cards"] if c["type"] != "general"]
    f, _ = unconfirmed(s)
    assert "Which card would you like to use" in f.template
