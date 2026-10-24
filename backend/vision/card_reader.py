"""Reads an insurance card photo into a fixed, privacy-preserving shape.

The CardExtract schema has NO field for member ID, group number, RxBIN, RxPCN,
date of birth, dependents, or phone numbers, so they cannot be returned. As a
second guard, any extracted value that looks like an identifier (five or more
digits in a row) is dropped in code. The photo is never stored.
"""
from __future__ import annotations

import base64
import logging
import os
import re

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

VISION_MODEL = os.environ.get("VISION_MODEL", "claude-opus-5-5")

_ID_LIKE = re.compile(r"\d{5,}")


class PrintedCopay(BaseModel):
    label: str = Field(description="What the card calls it, e.g. 'Generic', 'Tier 1', 'Brand'")
    amount_dollars: float


class CardExtract(BaseModel):
    first_name: str | None = Field(None, description="Member's first name as printed")
    last_name: str | None = Field(None, description="Member's last name as printed")
    insurer: str | None = Field(None, description="Insurance company, e.g. 'UnitedHealthcare'")
    plan_name: str | None = Field(None, description="Plan name if printed, e.g. 'Student Resources'")
    has_rx_section: bool = Field(description="True if the card prints a pharmacy section (RxBIN / RxPCN / RxGrp or an Rx logo)")
    rx_manager: str | None = Field(None, description="Company that manages prescriptions, e.g. 'OptumRx'")
    printed_rx_copays: list[PrintedCopay] = Field(default_factory=list,
                                                  description="Prescription copays printed on the card, if any")


SYSTEM_PROMPT = """\
You read a health insurance card for a shopping assistant. Return only the fields in the \
schema. Never copy member IDs, group numbers, RxBIN, RxPCN, dates, or phone numbers into \
any field. If a field is not printed, leave it empty. has_rx_section is true only if the \
card shows a pharmacy section (RxBIN, RxPCN, RxGrp, or a pharmacy-benefit logo)."""


def scrub(card: CardExtract) -> CardExtract:
    """Drop any text field that contains an ID-shaped number."""
    data = card.model_dump()
    for key in ("first_name", "last_name", "insurer", "plan_name", "rx_manager"):
        value = data.get(key)
        if value and _ID_LIKE.search(value):
            logger.warning("dropped ID-like value from card field %s", key)
            data[key] = None
    data["printed_rx_copays"] = [c for c in data["printed_rx_copays"]
                                 if not _ID_LIKE.search(c["label"]) and 0 <= c["amount_dollars"] <= 500]
    return CardExtract.model_validate(data)


def read_card(image_bytes: bytes) -> CardExtract:
    if os.environ.get("REWIND_STUB_VISION", "true").lower() == "true":
        return scrub(CardExtract(first_name="Alex", last_name="Rivera", insurer="UnitedHealthcare",
                                 plan_name="Student Resources", has_rx_section=True, rx_manager="OptumRx"))
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=VISION_MODEL,
        max_tokens=1024,
        output_config={"effort": "low"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                         "data": base64.b64encode(image_bytes).decode()}},
            {"type": "text", "text": "Read this insurance card."},
        ]}],
        output_format=CardExtract,
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise ValueError("card could not be read")
    return scrub(response.parsed_output)
