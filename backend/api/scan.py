"""POST /v1/scan: the main endpoint (technical spec 3.11).

frame -> vision -> lookup -> eligibility -> save -> routing -> prompt -> spoken line.
The image is read into memory and never written to disk.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, UploadFile

from api import memory
from api.envelope import ApiError
from data import db
from eligibility.classify import classify_eligibility
from lookup.chain import resolve_product
from lookup.moss_index import MossUnavailable, find_match
from lookup.normalize import normalize_key
from lookup import demo_items
from lookup.web_price import find_price_online
from models.schemas import EligibilityResult, ProductResolution, ScanResponse, ScanResult
from payments import cart_store
from payments.routing import route_item
from speech import compose
from vision.claude_vision import extract_product

router = APIRouter(prefix="/v1")

SCAN_BUDGET_S = 11.0               # whole /v1/scan (spec 0.7)
MAX_IMAGE_BYTES = 10 * 1024 * 1024
PRICE_MAX_CENTS = 50_000_000       # $500,000.00: anything above is a typo, not a shelf price


def save_prescription(extract, insurer: str | None = None) -> ScanResponse:
    """A pharmacy label (tech spec 2.3): read the drug name and strength back and wait for a yes.

    Nothing is priced, routed, or added from a label. The patient's name, Rx number, prescriber and
    dates are never extracted (vision/prompts.py), so none of them can be stored here.
    """
    scan_id = str(uuid.uuid4())
    name = extract.name or "this prescription"
    product = ProductResolution(product_key=normalize_key(None, name, extract.size), name=name, size=extract.size,
                                category=extract.category or "otc_medicine", is_medication=True,
                                is_prescription_only=True, state="partial", warnings=list(extract.warnings))
    elig = EligibilityResult(label="could_not_confirm", basis="no_match")
    db.save_scan(scan_id, product.model_dump(), elig.model_dump())
    prompt_id = db.create_prompt("confirm_strength", scan_id, {"name": name, "strength": extract.size, "insurer": insurer})
    scan = ScanResult(scan_id=scan_id, timestamp=datetime.now(timezone.utc).isoformat(), state=product.state,
                      product=product, eligibility=elig, warnings=list(product.warnings))
    return ScanResponse(scan=scan, recommendation=None, voice=compose.strength_question(name, extract.size, prompt_id))


async def identify(img: bytes, hint_price_cents: int | None, extract=None):
    """Vision, lookup and eligibility, in the same order as the Fetch.ai product agent."""
    extract = extract or await asyncio.to_thread(extract_product, img)
    if hint_price_cents is not None and extract.shelf_price_cents is None:
        extract = extract.model_copy(update={"shelf_price_cents": hint_price_cents})
    product = await asyncio.to_thread(resolve_product, extract)
    retailer = demo_items.match(product)                         # the three demo products, exactly
    checked = True
    if retailer is None:
        try:
            retailer = await find_match(product)                 # closest store listing, or None
        except MossUnavailable:
            checked = False                                      # the index could not answer
    if retailer and retailer.get("pinned") and retailer.get("price_cents"):
        # A demo item: the same price every time, not whatever the tag, cache or web shows today.
        product.amount_cents, product.price_source, product.state = retailer["price_cents"], "seeded", "resolved"
        product.warnings = [w for w in product.warnings if w != "E_NO_PRICE"]
    if (product.amount_cents is None and retailer and retailer.get("price_cents")
            and product.name != "Unknown product"):
        # no readable shelf tag: fall back to the price the store lists
        product.amount_cents, product.price_source = retailer["price_cents"], "seeded"
        product.state = "resolved"
        product.warnings = [w for w in product.warnings if w != "E_NO_PRICE"]
    if product.amount_cents is None and product.name != "Unknown product":
        online = await asyncio.to_thread(find_price_online, product)    # last resort: search the web
        if online:
            product.amount_cents, product.price_source, product.state = online, "online", "resolved"
            product.warnings = [w for w in product.warnings if w != "E_NO_PRICE"]
    elig = classify_eligibility(product, extract.package_eligibility_marking, retailer, checked)
    return product, elig


def save_and_route(product, elig) -> ScanResponse:
    """Everything after identification: save the scan, route, open the prompt, word the reply."""
    scan_id = str(uuid.uuid4())
    scan = ScanResult(scan_id=scan_id, timestamp=datetime.now(timezone.utc).isoformat(),
                      state=product.state, product=product, eligibility=elig, warnings=list(product.warnings))
    db.save_scan(scan_id, product.model_dump(), elig.model_dump())

    if product.state == "unresolved":
        return ScanResponse(scan=scan, recommendation=None, voice=compose.product_unresolved())

    cards = db.get_cards()
    rec = None
    if product.amount_cents is not None:
        rec = route_item(elig.label, product.amount_cents, "shelf_price", cards, scan_id=scan_id)

    prompt_id = None
    scope = compose.scope_for(rec)
    if rec is not None and scope != "none":
        prompt_id = db.create_prompt(scope, scan_id, cart_store.prompt_payload(product, elig.label, rec))
    voice = compose.compose_speech(product, elig, rec, cards, prompt_id=prompt_id)
    return ScanResponse(scan=scan, recommendation=rec, voice=voice)


async def run_scan(img: bytes, hint_price_cents: int | None, insurer: str | None = None) -> ScanResponse:
    extract = await asyncio.to_thread(extract_product, img)
    if extract.image_kind == "pharmacy_label":
        return await asyncio.to_thread(save_prescription, extract, insurer)
    product, elig = await identify(img, hint_price_cents, extract)
    return await asyncio.to_thread(save_and_route, product, elig)


@router.post("/scan", response_model=ScanResponse)
async def scan(
    image: UploadFile = File(...),
    barcode: str | None = Form(None),       # accepted for the app's contract (spec 0.6) but unused: no barcodes
    hint_price_cents: int | None = Form(None),
    insurer: str | None = Form(None),       # the insurer on the shopper's card, for the prescription copay tip
) -> ScanResponse:
    img = await image.read(MAX_IMAGE_BYTES + 1)
    if not img or len(img) > MAX_IMAGE_BYTES:
        raise ApiError("E_BAD_REQUEST", "image missing or over 10 MB")
    if hint_price_cents is not None and not 0 < hint_price_cents <= PRICE_MAX_CENTS:
        raise ApiError("E_BAD_REQUEST", "hint_price_cents out of range")
    try:
        response = await asyncio.wait_for(run_scan(img, hint_price_cents, (insurer or "").strip()[:80] or None), SCAN_BUDGET_S)
    except asyncio.TimeoutError:
        raise ApiError("E_UPSTREAM_TIMEOUT", "scan exceeded its budget") from None
    memory.remember(response.voice)
    return response
