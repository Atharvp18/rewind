"""Claude vision: extracts product data from a camera frame.

STUB: Returns hardcoded Advil data so Atharv can build against it from hour 0.
Replace with real Claude API calls at Gate 2.
"""
from __future__ import annotations

import base64
import json
import logging
import os

from models.schemas import VisionExtract
from vision.prompts import VISION_SYSTEM_PROMPT, VISION_USER_PROMPT

logger = logging.getLogger(__name__)

STUB_MODE = os.environ.get("REWIND_STUB_VISION", "true").lower() == "true"


def extract_product(image_bytes: bytes, barcode_hint: str | None = None) -> VisionExtract:
    """Extract product information from a camera frame.

    Args:
        image_bytes: JPEG image data.
        barcode_hint: UPC digits from the app's barcode scanner, if available.
    """
    if STUB_MODE:
        return _stub_extract(barcode_hint)
    return _claude_extract(image_bytes, barcode_hint)


def _stub_extract(barcode_hint: str | None = None) -> VisionExtract:
    """Return hardcoded Advil data for integration testing."""
    return VisionExtract(
        name="Advil Ibuprofen 200mg Tablets",
        brand="Advil",
        size="200mg, 50 count",
        upc=barcode_hint,
        shelf_price_cents=1299,
        category="pain_relief",
        is_medication=True,
        is_prescription_only=False,
        package_eligibility_marking="none_seen",
        field_confidence={"name": 0.95, "price": 0.92, "size": 0.90},
        warnings=[],
        raw_model="claude",
    )


def _claude_extract(image_bytes: bytes, barcode_hint: str | None = None) -> VisionExtract:
    """Call Claude vision API with the image and return structured product data."""
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    user_content = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": image_b64,
            },
        },
        {"type": "text", "text": VISION_USER_PROMPT},
    ]

    if barcode_hint:
        user_content.append({
            "type": "text",
            "text": f"The app's barcode scanner read these digits: {barcode_hint}",
        })

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=VISION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    raw_text = response.content[0].text.strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    data = json.loads(raw_text)

    warnings: list[str] = []
    if data.get("multiple_products_in_frame"):
        warnings.append("E_MULTIPLE_PRODUCTS")
    if not data.get("price_tag_visible"):
        warnings.append("E_NO_PRICE")
    if data.get("unreadable_reason"):
        warnings.append("E_VISION_UNCLEAR")
    if data.get("tag_may_belong_to_neighbour"):
        warnings.append("E_VISION_UNCLEAR")

    name_conf = data.get("field_confidence", {}).get("name", 0.0)
    if name_conf < 0.5 and not barcode_hint:
        warnings.append("E_PRODUCT_UNRESOLVED")

    price_cents = data.get("shelf_price_cents")
    if price_cents is not None and (price_cents < 1 or price_cents > 50000):
        warnings.append("E_NO_PRICE")
        price_cents = None

    return VisionExtract(
        name=data.get("name"),
        brand=data.get("brand"),
        size=data.get("size"),
        upc=barcode_hint or data.get("upc_digits"),
        shelf_price_cents=price_cents,
        category=data.get("category", "other"),
        is_medication=data.get("is_medication", False),
        is_prescription_only=data.get("is_prescription_only"),
        package_eligibility_marking=data.get("package_eligibility_marking"),
        field_confidence=data.get("field_confidence", {}),
        warnings=warnings,
        raw_model="claude",
    )
