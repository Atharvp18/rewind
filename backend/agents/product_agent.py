"""Rewind Product Agent — a uAgents worker.

Receives a ProductRequest (a shelf-photo URL or a product name), runs the fixed
scan pipeline (vision -> lookup -> eligibility), and returns a ProductResponse
with facts and the ScanResult. Stateless and deterministic: no Claude call
decides anything here except reading the photo.
"""
from __future__ import annotations

import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent.parent))

from uagents import Agent, Context

from agents.addresses import ORCHESTRATOR_AGENT_ADDRESS, PRODUCT_SEED
from agents.common import dollars, download_image
from agents.messages import FactsMsg, ProductRequest, ProductResponse, product_protocol
from agents.speaker import Facts, say, PRICE_RETRY
from models.schemas import EligibilityResult, ProductResolution, ScanResult, VisionExtract

logger = logging.getLogger(__name__)

HELP = say("Send me a shelf photo, or tell me the product's name, and I'll say what it is, "
           "what it costs, and whether it's HSA eligible.")


def _pipeline(extract: VisionExtract) -> tuple[ProductResolution, EligibilityResult]:
    from lookup.chain import resolve_product
    from eligibility.classify import classify_eligibility

    product = resolve_product(extract)
    return product, classify_eligibility(product, extract.package_eligibility_marking)


def facts_for(product: ProductResolution, elig: EligibilityResult) -> Facts:
    if product.state == "unresolved":
        return say("I could not confirm this item. Try another angle, or tell me what it is.",
                   "could not confirm this item")

    name = product.name
    if product.brand and product.brand.lower() not in name.lower():
        name = f"{product.brand} {name}"
    price = dollars(product.amount_cents) if product.amount_cents is not None else None

    if elig.label == "eligible":
        label = "HSA eligible"
    elif elig.label == "not_eligible":
        label = "Not HSA eligible"
    else:
        label = "I could not confirm eligibility"

    parts = [f"I see {name}" + (f", {price}." if price else ". I could not read a price.")]
    parts.append(label + ".")
    if product.state == "resolved":
        parts.append("Would you like to add it?")
    else:
        parts.append(PRICE_RETRY)
    # No price: the ask is spoken word for word. Rephrasing once turned "tell me the
    # price" into "should I read you the price", which the user can't act on.
    return say(" ".join(parts), name, price or "", label, fixed=price is None)


def card_facts(card, profile: dict) -> Facts:
    from agents.insurance import describe_plan
    first = card.first_name
    greeting = f"Thanks, {first}. " if first else "Thanks. "
    plan = describe_plan(profile)
    return say(greeting + f"I see your {card.insurer or 'insurance'} card. " + plan.template
               + " Show me any item to get started.", *([first] if first else []), *plan.must_say)


async def handle_card(image: bytes) -> tuple[Facts, dict | None, str | None]:
    """(facts, plan profile, first name). The profile holds no personal data."""
    from vision.card_reader import read_card
    from agents.insurance import card_to_profile
    try:
        card = read_card(image)
    except Exception:
        logger.exception("card read failed")
        return say("I couldn't read that card. Try again with the front facing the camera, or tell me your plan."), None, None
    profile = card_to_profile(card)
    name = " ".join(p for p in (card.first_name, card.last_name) if p) or None
    return card_facts(card, profile), profile, name


async def handle(image_url: str | None = None, barcode: str | None = None,
                 product_hint: str | None = None, is_prescription: bool | None = None,
                 ) -> tuple[Facts, dict | None]:
    """Pure handler for products and pharmacy labels: (facts, scan dict or None).

    Insurance cards are handled by handle_full(); this keeps the old two-value shape.
    """
    facts, scan, _, _ = await handle_full(image_url, barcode, product_hint, is_prescription)
    return facts, scan


async def handle_full(image_url: str | None = None, barcode: str | None = None,
                      product_hint: str | None = None, is_prescription: bool | None = None,
                      ) -> tuple[Facts, dict | None, dict | None, str | None]:
    """(facts, scan, card profile, person name)."""
    from vision.claude_vision import extract_product
    from eligibility.classify import classify_eligibility
    from lookup.normalize import normalize_key
    from agents.insurance import strength_of

    if image_url:
        try:
            image = await download_image(image_url)
        except Exception as exc:
            logger.warning("image download failed: %s", exc)
            return say("I couldn't open that photo. Please send it again, or tell me the product's name."), None, None, None
        try:
            extract = extract_product(image, barcode_hint=barcode)
        except Exception:
            logger.exception("vision failed")
            return say("I couldn't read that photo. Try again with the label facing the camera."), None, None, None
        if extract.image_kind == "insurance_card":
            facts, profile, name = await handle_card(image)
            return facts, None, profile, name
        product, elig = _pipeline(extract)
    elif product_hint:
        strength = strength_of(product_hint)
        name = re.sub(r"\s*\d+(?:\.\d+)?\s*(mg|mcg|g|ml)\b", "", product_hint, flags=re.I).strip() or product_hint
        product = ProductResolution(
            product_key=normalize_key(None, product_hint, None),
            name=name,
            size=strength,
            category="other",
            is_medication=bool(is_prescription),
            is_prescription_only=bool(is_prescription),
            state="partial",
        )
        elig = classify_eligibility(product, None)
    else:
        return HELP, None, None, None

    scan = ScanResult(
        scan_id=str(uuid4()),
        timestamp=datetime.now(timezone.utc).isoformat(),
        state=product.state,
        product=product,
        eligibility=elig,
        warnings=product.warnings,
    )
    return facts_for(product, elig), scan.model_dump(), None, None


@product_protocol.on_message(ProductRequest, replies=ProductResponse)
async def on_request(ctx: Context, sender: str, msg: ProductRequest):
    if sender != ORCHESTRATOR_AGENT_ADDRESS:
        ctx.logger.warning("ignoring ProductRequest from unknown sender %s", sender)
        return
    facts, scan, profile, name = await handle_full(msg.image_url, msg.barcode, msg.product_hint, msg.is_prescription)
    await ctx.send(sender, ProductResponse(request_id=msg.request_id, facts=FactsMsg.of(facts), scan=scan,
                                           card_profile=profile, person_name=name))


def build_agent(mailbox: bool = True, port: int = 8001) -> Agent:
    agent = Agent(
        name="Rewind Product Agent",
        seed=PRODUCT_SEED,
        port=port,
        mailbox=mailbox,
        publish_agent_details=mailbox,
        description="Identifies a shopping item from a shelf photo or name and checks HSA/FSA eligibility.",
    )
    agent.include(product_protocol, publish_manifest=True)
    return agent


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    build_agent().run()
