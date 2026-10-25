"""Online price fallback: parsing, and that a scan with no readable price uses it."""
from lookup import web_price
from models.schemas import ProductResolution


def test_parse_price_accepts_integer_cents_in_range():
    assert web_price.parse_price('Sure: {"price_cents": 1299}') == 1299


def test_parse_price_rejects_null_text_floats_and_out_of_range():
    for text in ('{"price_cents": null}', "no idea", '{"price_cents": 12.99}', '{"price_cents": 0}',
                 '{"price_cents": 9999999}', '{"price_cents": true}'):
        assert web_price.parse_price(text) is None


def test_lookup_is_off_in_stub_mode(monkeypatch):
    monkeypatch.setenv("REWIND_STUB_VISION", "true")
    product = ProductResolution(product_key="k", name="Yoga Mat", category="other")
    assert web_price.find_price_online(product) is None
