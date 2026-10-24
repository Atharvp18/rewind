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
from models.schemas import ScanResponse, ScanResult
from payments import cart_store
from payments.routing import route_item
from speech import compose
from vision.claude_vision import extract_product

router = APIRouter(prefix="/v1")

SCAN_BUDGET_S = 8.0                # whole /v1/scan (spec 0.7)
MAX_IMAGE_BYTES = 10 * 1024 * 1024
PRICE_MAX_CENTS = 50_000_000       # $500,000.00: anything above is a typo, not a shelf price


def run_scan(img: bytes, barcode: str | None, hint_price_cents: int | None) -> ScanResponse:
    extract = extract_product(img, barcode)
    if hint_price_cents is not None and extract.shelf_price_cents is None:
        extract = extract.model_copy(update={"shelf_price_cents": hint_price_cents})
    product = resolve_product(extract)
    elig = classify_eligibility(product, extract.package_eligibility_marking)

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


@router.post("/scan", response_model=ScanResponse)
async def scan(
    image: UploadFile = File(...),
    barcode: str | None = Form(None),
    hint_price_cents: int | None = Form(None),
) -> ScanResponse:
    img = await image.read(MAX_IMAGE_BYTES + 1)
    if not img or len(img) > MAX_IMAGE_BYTES:
        raise ApiError("E_BAD_REQUEST", "image missing or over 10 MB")
    if hint_price_cents is not None and not 0 < hint_price_cents <= PRICE_MAX_CENTS:
        raise ApiError("E_BAD_REQUEST", "hint_price_cents out of range")
    try:
        response = await asyncio.wait_for(
            asyncio.to_thread(run_scan, img, barcode, hint_price_cents), SCAN_BUDGET_S)
    except asyncio.TimeoutError:
        raise ApiError("E_UPSTREAM_TIMEOUT", "scan exceeded its budget") from None
    memory.remember(response.voice)
    return response
