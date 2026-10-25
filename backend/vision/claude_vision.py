"""Claude vision: extracts product data from a camera frame.

STUB: Returns hardcoded Advil data so Atharv can build against it from hour 0.
Replace with real Claude API calls at Gate 2.
"""
from __future__ import annotations

import base64
import json
import logging
import os

from pydantic import BaseModel

from models.schemas import VisionExtract
from vision.prompts import VISION_SYSTEM_PROMPT, VISION_USER_PROMPT

logger = logging.getLogger(__name__)

STUB_MODE = os.environ.get("REWIND_STUB_VISION", "true").lower() == "true"
VISION_MODEL = os.environ.get("VISION_MODEL", "claude-opus-5-5")


def extract_product(image_bytes: bytes) -> VisionExtract:
    """Extract product information from a camera frame.

    Args:
        image_bytes: JPEG image data.
    """
    if STUB_MODE:
        return _stub_extract(image_bytes)
    return _claude_extract(image_bytes)


def _stub_extract(image_bytes: bytes = b"") -> VisionExtract:
    """Hardcoded data for testing: advil (default), card, rx_label, tissues_far, tissues_close.

    Picked by a marker in the image bytes (b"stub:card"), else REWIND_STUB_IMAGE.
    """
    kind = os.environ.get("REWIND_STUB_IMAGE", "advil")
    for marker in ("card", "rx_label", "advil", "tissues_far", "tissues_close", "allegra", "excedrin"):
        if f"stub:{marker}".encode() in image_bytes:
            kind = marker
    if kind in ("tissues_far", "tissues_close"):   # same box; only the close photo shows the tag
        return VisionExtract(
            name="Kleenex Facial Tissues", brand="Kleenex", size="160 count", category="personal_care",
            shelf_price_cents=349 if kind == "tissues_close" else None,
            field_confidence={"name": 0.9, "price": 0.9 if kind == "tissues_close" else 0.0},
        )
    if kind == "excedrin":  # an OTC medicine that is NOT in the Moss catalog: eligible by rule, unlisted
        return VisionExtract(
            name="Excedrin Migraine", brand="Excedrin", category="pain_relief", is_medication=True,
            is_prescription_only=False, shelf_price_cents=1299, field_confidence={"name": 0.95, "price": 0.9})
    if kind == "allegra":   # a bottle with no shelf tag in view: price must come from the store listing
        return VisionExtract(
            name="Allegra 24 Hour Allergy Relief", brand="Allegra", category="cold_flu_allergy",
            is_medication=True, is_prescription_only=False,
            field_confidence={"name": 0.95, "price": 0.0},
        )
    if kind == "card":
        return VisionExtract(image_kind="insurance_card")
    if kind == "rx_label":
        return VisionExtract(
            image_kind="pharmacy_label", name="Omeprazole", size="20mg", category="digestive_health",
            is_medication=True, is_prescription_only=True,
            field_confidence={"name": 0.95, "size": 0.93},
        )
    return VisionExtract(
        name="Advil Ibuprofen 200mg Tablets",
        brand="Advil",
        size="200mg, 50 count",
        shelf_price_cents=1299,
        category="pain_relief",
        is_medication=True,
        is_prescription_only=False,
        package_eligibility_marking="none_seen",
        field_confidence={"name": 0.95, "price": 0.92, "size": 0.90},
        warnings=[],
        raw_model="claude",
    )


def _claude_extract(image_bytes: bytes) -> VisionExtract:
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


    response = client.messages.create(
        model=VISION_MODEL,
        max_tokens=1024,
        output_config={"effort": "low"},
        system=VISION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    raw_text = next(b.text for b in response.content if b.type == "text").strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    data = json.loads(raw_text)

    kind = data.get("image_kind") if data.get("image_kind") in ("insurance_card", "pharmacy_label") else "product"
    if kind == "insurance_card":
        return VisionExtract(image_kind="insurance_card", raw_model="claude")

    warnings: list[str] = []
    if data.get("multiple_products_in_frame"):
        warnings.append("E_MULTIPLE_PRODUCTS")
    if not data.get("price_tag_visible"):
        warnings.append("E_NO_PRICE")
    if data.get("unreadable_reason"):
        warnings.append("E_VISION_UNCLEAR")
        # The reason decides what the agent suggests (more light, less glare, hold still).
        specific = {"dark": "E_TOO_DARK", "glare": "E_GLARE", "blurry": "E_BLURRY"}.get(str(data["unreadable_reason"]))
        if specific:
            warnings.append(specific)
    neighbour = bool(data.get("tag_may_belong_to_neighbour"))
    if neighbour:
        warnings.append("E_VISION_UNCLEAR")
        warnings.append("E_TAG_NEIGHBOUR")

    name_conf = data.get("field_confidence", {}).get("name", 0.0)
    if name_conf < 0.5:
        warnings.append("E_PRODUCT_UNRESOLVED")

    price_cents = data.get("shelf_price_cents")
    if neighbour:
        price_cents = None            # the tag may be another item's: never price this item from it
    if price_cents is not None and (price_cents < 1 or price_cents > 50000):
        warnings.append("E_NO_PRICE")
        price_cents = None

    return VisionExtract(
        image_kind=kind,
        name=data.get("name"),
        brand=data.get("brand"),
        size=data.get("size"),
        shelf_price_cents=price_cents,
        category=data.get("category", "other"),
        is_medication=data.get("is_medication", False) or kind == "pharmacy_label",
        is_prescription_only=True if kind == "pharmacy_label" else data.get("is_prescription_only"),
        package_eligibility_marking=data.get("package_eligibility_marking"),
        field_confidence=data.get("field_confidence", {}),
        warnings=warnings,
        raw_model="claude",
    )


# --- a typed product name ------------------------------------------------------

NAME_MODEL = os.environ.get("INTENT_MODEL", "claude-haiku-5-5")
NAME_TIMEOUT_S = float(os.environ.get("INTENT_TIMEOUT_S", "10.0"))
CATEGORIES = ("otc_medicine, first_aid, menstrual_care, pain_relief, cold_flu_allergy, digestive_health, eye_care, "
              "foot_care, diagnostic_device, sunscreen, vitamins_supplements, personal_care, cosmetics, grocery, "
              "household, baby_care, other")


class _NamedProduct(BaseModel):
    brand: str | None = None
    name: str
    category: str
    is_medication: bool = False


_NAME_CLIENT = None


def _name_client():
    global _NAME_CLIENT
    if _NAME_CLIENT is None:
        import anthropic
        _NAME_CLIENT = anthropic.AsyncAnthropic()
    return _NAME_CLIENT


async def name_to_extract(text: str, size: str | None = None, is_prescription: bool = False) -> VisionExtract:
    """What the person typed or said ("Tylenol"), put in the same form a photo gives.

    Claude only names the product and picks its category from the fixed list, the same job as reading
    a photo. Code decides eligibility. If Claude is off or fails, the category is "other", so the
    item is never guessed eligible.
    """
    fallback = VisionExtract(name=text, size=size, category="other", is_medication=is_prescription,
                             is_prescription_only=is_prescription, warnings=["E_NO_PRICE"])
    if os.environ.get("REWIND_STUB_INTENT", "false").lower() == "true":
        return fallback
    import asyncio
    system = ("You turn what a shopper said into a product record for a pharmacy shelf. Give the brand "
              "(null if none), the product name without its strength, and one category from: "
              f"{CATEGORIES}. is_medication is true for medicines. Do not guess a product the shopper did not name.")
    try:
        response = await asyncio.wait_for(_name_client().messages.parse(
            model=NAME_MODEL, max_tokens=256, output_config={"effort": "low"}, system=system,
            messages=[{"role": "user", "content": f"The shopper said: {text!r}"}],
            output_format=_NamedProduct), NAME_TIMEOUT_S)
        got = response.parsed_output
        if response.stop_reason == "refusal" or got is None:
            return fallback
    except Exception:
        logger.warning("naming %r failed; category left as other", text)
        return fallback
    category = got.category if got.category in CATEGORIES.split(", ") else "other"
    return VisionExtract(brand=got.brand, name=got.name, size=size, category=category,
                         is_medication=got.is_medication or is_prescription,
                         is_prescription_only=is_prescription, warnings=["E_NO_PRICE"], raw_model="claude")
