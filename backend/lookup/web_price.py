"""Find a shelf price online when the camera could not read a tag and the store index has none.

Asks Claude with its web search tool for a typical US retail price. It is an estimate, labeled
price_source="online" so the app and the cart can say so. Any failure returns None, never raises.
"""
from __future__ import annotations

import json
import logging
import os
import re

from models.schemas import ProductResolution

logger = logging.getLogger(__name__)

PRICE_MODEL = os.environ.get("PRICE_MODEL", "claude-sonnet-5-5")
PRICE_TIMEOUT_S = 6.0
PRICE_MIN_CENTS, PRICE_MAX_CENTS = 1, 50000
# Off in stub mode and in tests unless asked for: no network call from a unit test.
ENABLED = os.environ.get("REWIND_ONLINE_PRICE", "true").lower() == "true"


def _stub_mode() -> bool:
    return os.environ.get("REWIND_STUB_VISION", "true").lower() == "true"


def parse_price(text: str) -> int | None:
    """Integer cents from the model's JSON answer, or None when it is missing or out of range."""
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None
    try:
        cents = json.loads(match.group(0)).get("price_cents")
    except (ValueError, AttributeError):
        return None
    if isinstance(cents, bool) or not isinstance(cents, int):
        return None
    return cents if PRICE_MIN_CENTS <= cents <= PRICE_MAX_CENTS else None


def find_price_online(product: ProductResolution) -> int | None:
    if not ENABLED or _stub_mode() or not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    label = " ".join(p for p in (product.brand, product.name, product.size) if p)
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=PRICE_TIMEOUT_S)
        response = client.messages.create(
            model=PRICE_MODEL,
            max_tokens=300,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 2}],
            messages=[{"role": "user", "content": (
                f"What is the typical current US retail price of: {label}? Search once or twice, then "
                'answer with only JSON like {"price_cents": 1299}. Use null if you cannot find it.')}],
        )
        text = next((b.text for b in reversed(response.content) if b.type == "text"), "")
        return parse_price(text)
    except Exception as exc:                                    # network, quota, bad answer: no price
        logger.warning("Online price lookup skipped: %s", exc)
        return None
