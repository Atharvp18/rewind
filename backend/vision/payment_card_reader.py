"""Reads a payment card photo (PROPOSED, onboarding): network, HSA / FSA, credit / debit, last 4.

Like card_reader.py, the schema has NO field for the full card number, expiry, security code, or
the cardholder's name, so they cannot be returned. As a second guard, last4 is kept only when it
is exactly four digits. The photo is never stored.
"""
from __future__ import annotations

import base64
import os
import re
from typing import Literal

from pydantic import BaseModel, Field

VISION_MODEL = os.environ.get("VISION_MODEL", "claude-opus-5-5")


class PaymentExtract(BaseModel):
    is_payment_card: bool = Field(description="True if the photo shows the front of a credit, debit, HSA or FSA card")
    network: Literal["visa", "mastercard", "amex", "discover", "other"] | None = Field(
        None, description="Card network logo printed on the card")
    account_type: Literal["hsa", "fsa"] | None = Field(
        None, description="'hsa' if the card says HSA or Health Savings, 'fsa' if it says FSA or Flexible "
                          "Spending; otherwise null")
    funding: Literal["credit", "debit"] | None = Field(
        None, description="'credit' or 'debit' only if that word is printed on the card")
    last4: str | None = Field(None, description="ONLY the last four digits of the card number, nothing else")


SYSTEM_PROMPT = """\
You read the front of a payment card for a shopping assistant. Return only the fields in the \
schema. Never return the full card number, the expiry date, the security code, or the \
cardholder's name. last4 is the last four digits of the card number only. If a field is not \
printed or not readable, leave it empty."""

_FOUR_DIGITS = re.compile(r"^\d{4}$")


def scrub(card: PaymentExtract) -> PaymentExtract:
    if card.last4 is not None and not _FOUR_DIGITS.match(card.last4.strip()):
        card = card.model_copy(update={"last4": None})
    elif card.last4 is not None:
        card = card.model_copy(update={"last4": card.last4.strip()})
    return card


def read_payment_card(image_bytes: bytes) -> PaymentExtract:
    if os.environ.get("REWIND_STUB_VISION", "true").lower() == "true":
        return scrub(PaymentExtract(is_payment_card=True, network="visa", account_type="hsa", last4="4242"))
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=VISION_MODEL,
        max_tokens=512,
        output_config={"effort": "low"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                         "data": base64.b64encode(image_bytes).decode()}},
            {"type": "text", "text": "Read this payment card."},
        ]}],
        output_format=PaymentExtract,
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise ValueError("card could not be read")
    return scrub(response.parsed_output)
