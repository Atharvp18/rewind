"""The three demo products resolve exactly, ahead of the fuzzy index."""
from lookup import demo_items
from models.schemas import ProductResolution


def p(name, brand=None, size=None):
    return ProductResolution(product_key="k", name=name, brand=brand, size=size, category="other")


def test_each_demo_item_is_matched_with_its_pinned_price():
    assert demo_items.match(p("Tums Ultra Strength Chewable Tablets", "Tums", "72 count"))["price_cents"] == 548
    assert demo_items.match(p("Allergy Relief", None, "4mg, 100 tablets"))["price_cents"] == 399
    assert demo_items.match(p("Allergy Relief Tablets"))["price_cents"] == 399
    assert demo_items.match(p("Extra Strength Acetaminophen", "Tylenol", "24 count"))["price_cents"] == 519


def test_other_allergy_medicines_are_not_the_demo_item():
    assert demo_items.match(p("Allegra 24 Hour Allergy Relief", "Allegra", "90 count")) is None
    assert demo_items.match(p("Benadryl Ultra Allergy Relief", "Benadryl", "100 count")) is None
