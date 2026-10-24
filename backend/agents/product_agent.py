"""Rewind Product Agent (Fetch.ai / ASI:One).

Stateless worker. Takes a product description or an attached shelf photo,
runs it through the scan pipeline (vision -> lookup -> eligibility), and
returns a spoken-style summary plus the ScanResult as metadata.

Session state lives in the orchestrator; this agent only receives a
"session" metadata blob and returns a "scan" blob.
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent.parent))

from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import ChatAcknowledgement, ChatMessage, chat_protocol_spec

from agents.common import Incoming, ack, dollars, download_image, reply
from agents.session import find_demo_item
from models.schemas import EligibilityResult, ProductResolution, ScanResult, VisionExtract

logger = logging.getLogger(__name__)

HELP_TEXT = (
    "I'm the Rewind Product Agent. Send me a shelf photo, or ask about a product "
    "by name, and I'll tell you what it is, what it costs, and whether it's HSA/FSA eligible.\n\n"
    "Try: \"Is Advil HSA eligible?\" or attach a photo of a product."
)

ELIGIBILITY_QUESTION = ["eligible", "eligibility", "hsa", "fsa", "cover"]


def _demo_resolution(item: dict) -> tuple[ProductResolution, EligibilityResult]:
    product = ProductResolution(
        product_key=f"upc:{item['upc']}",
        upc=item["upc"],
        name=item["name"],
        brand=item["brand"],
        size=item["size"],
        category=item["category"],
        is_medication=item["is_medication"],
        amount_cents=item["amount_cents"],
        price_source="seeded",
        state="resolved",
    )
    elig = EligibilityResult(
        label="eligible" if item["eligible"] else "not_eligible",
        basis="upc_match" if item["basis"] == "hand_entered" else "irs_category_rule",
        source="hand_entered" if item["basis"] == "hand_entered" else "irs_rules",
        matched_name=item["name"],
    )
    return product, elig


def _pipeline(extract: VisionExtract) -> tuple[ProductResolution, EligibilityResult]:
    from lookup.chain import resolve_product
    from eligibility.classify import classify_eligibility

    product = resolve_product(extract)
    demo = find_demo_item(product.name)
    if demo and product.state != "unresolved":
        # Pre-cached demo shelf (spec 19.3) until eligibility_items is wired to the DB.
        demo_product, elig = _demo_resolution(demo)
        if product.amount_cents is not None:
            demo_product.amount_cents = product.amount_cents
            demo_product.price_source = product.price_source
        return demo_product, elig
    elig = classify_eligibility(product, extract.package_eligibility_marking)
    return product, elig


def _speak(product: ProductResolution, elig: EligibilityResult) -> str:
    if product.state == "unresolved":
        return "I could not confirm this item. Try another angle, or tell me what it is."

    name = product.name
    if product.brand and product.brand.lower() not in name.lower():
        name = f"{product.brand} {name}"
    price = dollars(product.amount_cents) if product.amount_cents is not None else None

    parts = [f"I see {name}" + (f", {price}." if price else ". I could not read a price.")]

    if elig.label == "eligible":
        if product.is_medication and elig.basis == "upc_match":
            parts.append("HSA eligible.")
        else:
            conf = "high confidence" if elig.basis in ("upc_match", "irs_category_rule") else "moderate confidence"
            parts.append(f"HSA eligible, {conf}.")
    elif elig.label == "not_eligible":
        parts.append("Not HSA eligible, high confidence.")
    else:
        parts.append("I could not confirm eligibility.")

    if product.state == "resolved":
        parts.append("Say \"add it\" to put it in your cart, or \"skip it\".")
    else:
        parts.append("Tell me the shelf price and I can add it to your cart.")
    return " ".join(parts)


def _text_to_scan(text: str) -> tuple[ProductResolution, EligibilityResult]:
    demo = find_demo_item(text)
    if demo:
        return _demo_resolution(demo)
    from eligibility.classify import classify_eligibility
    from lookup.normalize import normalize_key

    name = text
    for word in ("is", "are", "the", "hsa", "fsa", "eligible", "eligibility", "covered", "?"):
        name = name.replace(word, " ")
    name = " ".join(name.split()).strip() or text
    product = ProductResolution(
        product_key=normalize_key(None, name, None),
        name=name,
        category="other",
        state="partial",
    )
    return product, classify_eligibility(product, None)


async def handle(inc: Incoming) -> tuple[str, dict | None]:
    """Pure handler: (reply text, scan metadata). Shared by the mailbox agent and the orchestrator."""
    from vision.claude_vision import extract_product

    if inc.image_url:
        try:
            image = await download_image(inc.image_url)
        except Exception as exc:
            logger.warning("image download failed: %s", exc)
            return ("I couldn't open that photo. Please re-attach it, or tell me the product name.", None)
        try:
            extract = extract_product(image, barcode_hint=inc.metadata.get("barcode"))
        except Exception:
            logger.exception("vision failed")
            return ("I couldn't read that photo. Try again with the label facing the camera.", None)
        product, elig = _pipeline(extract)
    elif inc.text and (any(k in inc.text.lower() for k in ELIGIBILITY_QUESTION) or find_demo_item(inc.text)):
        product, elig = _text_to_scan(inc.text)
    else:
        return (HELP_TEXT, None)

    scan = ScanResult(
        scan_id=str(uuid4()),
        timestamp=datetime.now(timezone.utc).isoformat(),
        state=product.state,
        product=product,
        eligibility=elig,
        warnings=product.warnings,
    )
    return (_speak(product, elig), {"scan": scan.model_dump()})


protocol = Protocol(spec=chat_protocol_spec)


@protocol.on_message(ChatMessage)
async def on_message(ctx: Context, sender: str, msg: ChatMessage):
    await ack(ctx, sender, msg)
    inc = Incoming(msg)
    text, meta = await handle(inc)
    passthrough = {"user": inc.metadata["user"]} if "user" in inc.metadata else {}
    await ctx.send(sender, reply(text, {**passthrough, **(meta or {})}))


@protocol.on_message(ChatAcknowledgement)
async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    pass


def build_agent() -> Agent:
    agent = Agent(
        name="Rewind Product Agent",
        seed=os.environ.get("PRODUCT_AGENT_SEED", "rewind-product-agent-dev-seed"),
        port=int(os.environ.get("PRODUCT_AGENT_PORT", "8001")),
        mailbox=True,
        publish_agent_details=True,
    )
    agent.include(protocol, publish_manifest=True)
    return agent


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    build_agent().run()
