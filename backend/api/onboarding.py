"""POST /v1/onboarding/card-scan (PROPOSED for spec 0.6): read an insurance or payment card.

The app sends one photo and `kind` ("insurance" or "payment"). The photo is read in memory and
never stored. What can come back is fixed by the reader schemas (vision/card_reader.py and
vision/payment_card_reader.py): no member ID, group, RxBIN or RxPCN, and from a payment card only
the network, HSA / FSA, credit / debit and the last four digits. When a card can't be read the
reply is state "unclear" with a framing hint, never an error, so the user just tries again.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Literal

from fastapi import APIRouter, File, Form, UploadFile

from api.envelope import ApiError
from vision.card_reader import read_card
from vision.payment_card_reader import read_payment_card

router = APIRouter(prefix="/v1/onboarding")
logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 10 * 1024 * 1024
READ_BUDGET_S = 15.0            # a Claude card read takes about 8 s; onboarding is not in the aisle
FRAMING_HINT = "I couldn't read the card. Hold it flat in good light, about a hand length from the phone."


def unclear(reason: str) -> dict:
    """`reason` is for diagnosis only (the app logs it): model_refused, nothing_readable, not_a_card."""
    logger.info("card scan unclear: %s", reason)
    return {"state": "unclear", "framing_hint": FRAMING_HINT, "insurance": None, "payment": None, "reason": reason}


def insurance_reply(card) -> dict:
    if not (card.insurer or card.first_name or card.last_name):
        return unclear("nothing_readable")
    rx = None
    if card.has_rx_section:
        # The reader keeps no BIN, PCN or group number (privacy), so only printed copays come back.
        rx = {"bin": None, "pcn": None, "group": None,
              "copays": [{"label": c.label, "amount_cents": round(c.amount_dollars * 100)}
                         for c in card.printed_rx_copays]}
    return {"state": "read", "framing_hint": None, "payment": None, "insurance": {
        "insurer_name": card.insurer or "", "plan_name": card.plan_name,
        "member_first_name": card.first_name, "member_last_name": card.last_name,
        "member_id_last4": None, "rx": rx}}


def payment_reply(card) -> dict:
    if not card.is_payment_card:
        return unclear("not_a_card")
    if card.network is None and card.last4 is None:
        return unclear("nothing_readable")
    # HSA / FSA printed on the card decides the type; otherwise a printed CREDIT or DEBIT means an
    # everyday card. With neither, card_type is null and the app asks the user.
    card_type = card.account_type or ("general" if card.funding else None)
    return {"state": "read", "framing_hint": None, "insurance": None, "payment": {
        "network": card.network, "card_type": card_type, "funding": card.funding, "last4": card.last4}}


@router.post("/card-scan")
async def card_scan(image: UploadFile = File(...), kind: Literal["insurance", "payment"] = Form(...)) -> dict:
    img = await image.read(MAX_IMAGE_BYTES + 1)
    if not img or len(img) > MAX_IMAGE_BYTES:
        raise ApiError("E_BAD_REQUEST", "image missing or over 10 MB")
    reader = read_card if kind == "insurance" else read_payment_card
    try:
        card = await asyncio.wait_for(asyncio.to_thread(reader, img), READ_BUDGET_S)
    except asyncio.TimeoutError:
        raise ApiError("E_UPSTREAM_TIMEOUT", "card read exceeded its budget") from None
    except ValueError:                       # the model refused or returned nothing usable
        return unclear("model_refused")
    finally:
        del img                              # the photo is never kept
    return insurance_reply(card) if kind == "insurance" else payment_reply(card)
