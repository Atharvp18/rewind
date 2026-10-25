"""POST /v1/frame-check (PROPOSED): is there an item in the camera frame right now?

The app sends one photo when the shopper has paused after a scan, to choose between "Would you like
me to repeat?" (the item is still there) and "Is there anything else you'd like me to scan?" (it was
taken away). The photo is read in memory and never saved. If Claude cannot answer, the app falls
back to the phone's motion sensor.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os

from fastapi import APIRouter, File, UploadFile

from api.envelope import ApiError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1")

MAX_IMAGE_BYTES = 10 * 1024 * 1024
FRAME_MODEL = os.environ.get("FRAME_MODEL", "claude-haiku-5-5")
FRAME_TIMEOUT_S = 6.0
PROMPT = ("Look at this camera frame from a shopping app. Is there a single product (a box, bottle, tube or "
          "package) held up or placed in view, close enough to read? Answer with only the word yes or no.")


def _stub() -> bool:
    return os.environ.get("REWIND_STUB_VISION", "true").lower() == "true"


def item_in_frame(image: bytes) -> bool:
    if _stub():
        return b"stub:empty" not in image
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=FRAME_TIMEOUT_S)
    response = client.messages.create(
        model=FRAME_MODEL, max_tokens=5,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                         "data": base64.b64encode(image).decode()}},
            {"type": "text", "text": PROMPT}]}])
    answer = next((b.text for b in response.content if b.type == "text"), "").strip().lower()
    return answer.startswith("yes")


@router.post("/frame-check")
async def frame_check(image: UploadFile = File(...)) -> dict:
    img = await image.read(MAX_IMAGE_BYTES + 1)
    if not img or len(img) > MAX_IMAGE_BYTES:
        raise ApiError("E_BAD_REQUEST", "image missing or over 10 MB")
    try:
        found = await asyncio.wait_for(asyncio.to_thread(item_in_frame, img), FRAME_TIMEOUT_S + 1)
    except Exception as exc:  # noqa: BLE001 - the app has a motion-sensor fallback
        logger.warning("frame check failed: %s", type(exc).__name__)
        raise ApiError("E_UPSTREAM_TIMEOUT", "frame check unavailable") from exc
    return {"item_in_frame": found}
